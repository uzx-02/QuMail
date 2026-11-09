"""
Metadata-First Encrypted Mailbox Index & Unread State Management.

Implements a local, metadata-first message index stored inside the encrypted
account vault. Supports schema migration from legacy M6 structures, efficient
in-memory caching, authoritative unread tracking, expunge reconciliation,
and substring query filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from email.utils import parsedate_to_datetime, parseaddr
import re
import time
from typing import Any


def sanitize_snippet(text: str, max_length: int = 256) -> str:
    """
    Sanitize and truncate plain-text or preview snippets.

    Strips control characters, bidi overrides, HTML-like tags, and clamps length.
    """
    if not text:
        return ""
    # Strip HTML tags if present
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # Strip bidi overrides and non-printable control characters
    bidi_and_ctrl = (
        "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
        "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
        "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f\x7f"
    )
    cleaned = "".join(c if c not in bidi_and_ctrl else " " for c in cleaned)
    # Normalize multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


@dataclass
class IndexedMessage:
    """
    Metadata-first message record indexed inside the encrypted vault.

    Does not contain the full raw message body or sensitive attachment payloads.
    Contains authoritative flags, sender/recipient metadata, subject, dates,
    and attachment manifests.
    """
    uid: int
    uidvalidity: int
    mailbox: str
    account_id: str
    sender_display: str
    sender_address: str
    recipients: tuple[str, ...] = ()
    subject: str = ""
    date: str = ""
    date_ts: float = 0.0
    message_id: str = ""
    size: int = 0
    flags: tuple[str, ...] = ()
    seen: bool = False
    has_attachments: bool = False
    attachments_meta: tuple[dict[str, Any], ...] = ()
    snippet: str = ""
    in_reply_to: str = ""
    references: tuple[str, ...] = ()
    raw_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.seen and r"\Seen" in self.flags:
            self.seen = True
        elif self.seen and r"\Seen" not in self.flags:
            self.flags = (*self.flags, r"\Seen")

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "uid": self.uid,
            "uidvalidity": self.uidvalidity,
            "mailbox": self.mailbox,
            "account_id": self.account_id,
            "sender_display": self.sender_display,
            "sender_address": self.sender_address,
            "recipients": list(self.recipients),
            "subject": self.subject,
            "date": self.date,
            "date_ts": self.date_ts,
            "message_id": self.message_id,
            "size": self.size,
            "flags": list(self.flags),
            "seen": self.seen,
            "has_attachments": self.has_attachments,
            "attachments_meta": list(self.attachments_meta),
            "snippet": self.snippet,
            "in_reply_to": self.in_reply_to,
            "references": list(self.references),
            "raw_digest": self.raw_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexedMessage:
        """Construct IndexedMessage from dictionary."""
        return cls(
            uid=int(data["uid"]),
            uidvalidity=int(data["uidvalidity"]),
            mailbox=str(data.get("mailbox", "INBOX")),
            account_id=str(data.get("account_id", "")),
            sender_display=str(data.get("sender_display", "")),
            sender_address=str(data.get("sender_address", "")),
            recipients=tuple(data.get("recipients", ())),
            subject=str(data.get("subject", "")),
            date=str(data.get("date", "")),
            date_ts=float(data.get("date_ts", 0.0)),
            message_id=str(data.get("message_id", "")),
            size=int(data.get("size", 0)),
            flags=tuple(data.get("flags", ())),
            seen=bool(data.get("seen", False)),
            has_attachments=bool(data.get("has_attachments", False)),
            attachments_meta=tuple(data.get("attachments_meta", ())),
            snippet=str(data.get("snippet", "")),
            in_reply_to=str(data.get("in_reply_to", "")),
            references=tuple(data.get("references", ())),
            raw_digest=data.get("raw_digest"),
        )


class MailboxIndex:
    """
    Encrypted local mailbox index manager.

    Maintains in-memory map of UIDs to IndexedMessage records with transactional
    persistence into the account vault.
    """

    def __init__(self, account_id: str, mailbox: str = "INBOX", uidvalidity: int = 0) -> None:
        self.account_id = account_id
        self.mailbox = mailbox
        self.uidvalidity = uidvalidity
        self._messages: dict[int, IndexedMessage] = {}

    def clear(self) -> None:
        """Clear all indexed messages (e.g. following UIDVALIDITY rollover)."""
        self._messages.clear()

    def upsert_message(self, msg: IndexedMessage) -> bool:
        """
        Insert or update a message in the index.

        Returns True if newly inserted, False if updated.
        """
        is_new = msg.uid not in self._messages
        self._messages[msg.uid] = msg
        return is_new

    def remove_message(self, uid: int) -> IndexedMessage | None:
        """Remove a message by UID from the index (e.g. after EXPUNGE)."""
        return self._messages.pop(uid, None)

    def get_message(self, uid: int) -> IndexedMessage | None:
        """Retrieve indexed message metadata by UID."""
        return self._messages.get(uid)

    def list_messages(
        self,
        limit: int = 50,
        before_uid: int | None = None,
        unread_only: bool = False,
        query: str = "",
    ) -> list[IndexedMessage]:
        """
        List messages ordered newest-first by UID.

        Supports pagination via before_uid, unread-only filtering, and
        case-insensitive search across sender and subject.
        """
        sorted_msgs = sorted(self._messages.values(), key=lambda m: m.uid, reverse=True)

        if before_uid is not None:
            sorted_msgs = [m for m in sorted_msgs if m.uid < before_uid]

        if unread_only:
            sorted_msgs = [m for m in sorted_msgs if not m.seen]

        if query:
            q = query.strip().lower()
            sorted_msgs = [
                m for m in sorted_msgs
                if q in m.sender_display.lower()
                or q in m.sender_address.lower()
                or q in m.subject.lower()
                or q in m.snippet.lower()
            ]

        return sorted_msgs[:limit]

    def get_unread_count(self) -> int:
        """Return total unread messages in the index."""
        return sum(1 for m in self._messages.values() if not m.seen)

    def get_total_count(self) -> int:
        """Return total messages in the index."""
        return len(self._messages)

    def set_seen(self, uid: int, seen: bool) -> bool:
        """
        Update the seen state for a message locally.

        Returns True if message exists and was updated, False otherwise.
        """
        msg = self._messages.get(uid)
        if not msg:
            return False
        msg.seen = seen
        current_flags = set(msg.flags)
        if seen:
            current_flags.add(r"\Seen")
        else:
            current_flags.discard(r"\Seen")
        msg.flags = tuple(sorted(current_flags))
        return True

    def reconcile_flags(self, flag_map: dict[int, list[str]]) -> list[int]:
        """
        Reconcile message flags from server FETCH responses.

        Returns list of UIDs whose seen or flag state changed.
        """
        changed: list[int] = []
        for uid, raw_flags in flag_map.items():
            msg = self._messages.get(uid)
            if not msg:
                continue
            new_flags = tuple(sorted(set(raw_flags)))
            new_seen = r"\Seen" in new_flags
            if msg.flags != new_flags or msg.seen != new_seen:
                msg.flags = new_flags
                msg.seen = new_seen
                changed.append(uid)
        return changed

    def to_dict(self) -> dict[str, Any]:
        """Serialize index state to dictionary."""
        return {
            "account_id": self.account_id,
            "mailbox": self.mailbox,
            "uidvalidity": self.uidvalidity,
            "messages": [msg.to_dict() for msg in sorted(self._messages.values(), key=lambda m: m.uid, reverse=True)],
        }

    @classmethod
    def load_from_vault(
        cls,
        vault_data: dict[str, Any],
        account_id: str,
        mailbox: str = "INBOX",
    ) -> MailboxIndex:
        """
        Load index from vault dictionary with automatic backward-compatible migration.
        """
        m7_indices = vault_data.get("m7_mailbox_index_v1")
        if isinstance(m7_indices, dict) and mailbox in m7_indices:
            data = m7_indices[mailbox]
            idx = cls(
                account_id=account_id,
                mailbox=mailbox,
                uidvalidity=int(data.get("uidvalidity", 0)),
            )
            for mdata in data.get("messages", []):
                try:
                    msg = IndexedMessage.from_dict(mdata)
                    idx.upsert_message(msg)
                except Exception:
                    continue
            return idx

        # Migration from legacy m6_mailbox_v1
        legacy = vault_data.get("m6_mailbox_v1")
        if isinstance(legacy, dict) and legacy.get("mailbox") == mailbox:
            validity = int(legacy.get("uidvalidity", 0))
            idx = cls(account_id=account_id, mailbox=mailbox, uidvalidity=validity)
            for row in legacy.get("rows", []):
                if not isinstance(row, dict) or "uid" not in row:
                    continue
                uid = int(row["uid"])
                sender = str(row.get("sender", ""))
                disp_name, addr = parseaddr(sender)
                date_str = str(row.get("date", ""))
                try:
                    dt = parsedate_to_datetime(date_str)
                    date_ts = dt.timestamp()
                except Exception:
                    date_ts = 0.0
                seen = bool(row.get("seen", False))
                flags = (r"\Seen",) if seen else ()
                msg = IndexedMessage(
                    uid=uid,
                    uidvalidity=validity,
                    mailbox=mailbox,
                    account_id=account_id,
                    sender_display=disp_name or addr,
                    sender_address=addr,
                    subject=str(row.get("subject", "")),
                    date=date_str,
                    date_ts=date_ts,
                    size=int(row.get("size", 0)),
                    flags=flags,
                    seen=seen,
                )
                idx.upsert_message(msg)
            return idx

        return cls(account_id=account_id, mailbox=mailbox)

    def save_to_vault(self, vault_data: dict[str, Any]) -> None:
        """
        Save index to vault, updating modern m7_mailbox_index_v1 and
        maintaining m6_mailbox_v1 backward compatibility.
        """
        if "m7_mailbox_index_v1" not in vault_data or not isinstance(vault_data["m7_mailbox_index_v1"], dict):
            vault_data["m7_mailbox_index_v1"] = {}
        vault_data["m7_mailbox_index_v1"][self.mailbox] = self.to_dict()

        # Update legacy m6_mailbox_v1 representation for seamless backward compatibility
        if self.mailbox == "INBOX":
            legacy_rows = [
                {
                    "uid": m.uid,
                    "sender": f"{m.sender_display} <{m.sender_address}>" if m.sender_display != m.sender_address else m.sender_address,
                    "subject": m.subject,
                    "date": m.date,
                    "size": m.size,
                    "seen": m.seen,
                }
                for m in sorted(self._messages.values(), key=lambda x: x.uid, reverse=True)[:30]
            ]
            vault_data["m6_mailbox_v1"] = {
                "mailbox": "INBOX",
                "uidvalidity": self.uidvalidity,
                "rows": legacy_rows,
            }
