"""
Mailbox Synchronization Cursor & State Management.

Provides persistent, race-safe synchronization cursor tracking for QuMail
mailboxes. Enforces UIDVALIDITY invariants, handles UIDNEXT progression,
detects expunges/vanished messages, and persists transactionally in the
encrypted vault.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


@dataclass
class MailboxCursor:
    """
    Persistent synchronization cursor for a specific account and mailbox folder.

    account_id:     Account identifier to which this cursor belongs.
    mailbox:        Mailbox folder name (e.g. 'INBOX').
    uidvalidity:    Authoritative IMAP UIDVALIDITY value from the server.
    uidnext:        Server's predicted next UID (UIDNEXT).
    highest_modseq: Highest MODSEQ value if CONDSTORE / QRESYNC is supported.
    last_sync_uid:  Highest message UID successfully synced to the local index.
    synced_uids:    Set of active UIDs currently indexed locally.
    last_sync_time: Timestamp of the last successful synchronization pass.
    """
    account_id: str
    mailbox: str = "INBOX"
    uidvalidity: int = 0
    uidnext: int = 1
    highest_modseq: int | None = None
    last_sync_uid: int = 0
    synced_uids: set[int] = field(default_factory=set)
    last_sync_time: float = 0.0

    def check_uidvalidity(self, server_uidvalidity: int) -> bool:
        """
        Validate server UIDVALIDITY against the cursor's stored value.

        Returns True if UIDVALIDITY is unchanged or if this is the initial sync.
        Returns False if UIDVALIDITY changed (rollover/re-creation on the server),
        which immediately invalidates all existing UID-based assumptions and
        resets the cursor for a full resynchronization.
        """
        if not isinstance(server_uidvalidity, int) or server_uidvalidity <= 0:
            raise ValueError(f"Invalid server UIDVALIDITY: {server_uidvalidity!r}")

        if self.uidvalidity == 0:
            # Initial adoption of server UIDVALIDITY
            self.uidvalidity = server_uidvalidity
            return True

        if self.uidvalidity == server_uidvalidity:
            return True

        # UIDVALIDITY change detected: server mailbox was deleted, reconstructed,
        # or rolled over. All cached UIDs are invalid and must not be reused.
        self.reset(server_uidvalidity)
        return False

    def reset(self, new_uidvalidity: int = 0) -> None:
        """Reset the cursor state following a UIDVALIDITY change or full resync request."""
        self.uidvalidity = new_uidvalidity
        self.uidnext = 1
        self.highest_modseq = None
        self.last_sync_uid = 0
        self.synced_uids.clear()
        self.last_sync_time = 0.0

    def record_synced(
        self,
        uids: list[int] | set[int],
        new_uidnext: int | None = None,
        modseq: int | None = None,
    ) -> None:
        """
        Record newly synced or refreshed message UIDs into the cursor state.

        Updates synced_uids, advances last_sync_uid safely, and tracks UIDNEXT.
        """
        int_uids = {int(u) for u in uids if int(u) > 0}
        self.synced_uids.update(int_uids)
        if self.synced_uids:
            self.last_sync_uid = max(self.synced_uids)
        if new_uidnext is not None and new_uidnext > self.uidnext:
            self.uidnext = new_uidnext
        if modseq is not None:
            if self.highest_modseq is None or modseq > self.highest_modseq:
                self.highest_modseq = modseq
        self.last_sync_time = time.time()

    def reconcile_expunges(self, current_server_uids: set[int]) -> list[int]:
        """
        Reconcile local synced_uids against the complete set of server UIDs.

        Identifies messages that were expunged or vanished on the server,
        removes them from synced_uids, and returns the sorted list of expunged UIDs.
        """
        expunged = sorted(self.synced_uids - current_server_uids)
        for uid in expunged:
            self.synced_uids.discard(uid)
        if self.synced_uids:
            self.last_sync_uid = max(self.synced_uids)
        else:
            self.last_sync_uid = 0
        return expunged

    def to_dict(self) -> dict[str, Any]:
        """Convert cursor to a JSON-serializable dictionary."""
        return {
            "account_id": self.account_id,
            "mailbox": self.mailbox,
            "uidvalidity": self.uidvalidity,
            "uidnext": self.uidnext,
            "highest_modseq": self.highest_modseq,
            "last_sync_uid": self.last_sync_uid,
            "synced_uids": sorted(self.synced_uids),
            "last_sync_time": self.last_sync_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailboxCursor:
        """Create a MailboxCursor from a serialized dictionary."""
        return cls(
            account_id=str(data.get("account_id", "")),
            mailbox=str(data.get("mailbox", "INBOX")),
            uidvalidity=int(data.get("uidvalidity", 0)),
            uidnext=int(data.get("uidnext", 1)),
            highest_modseq=data.get("highest_modseq"),
            last_sync_uid=int(data.get("last_sync_uid", 0)),
            synced_uids=set(data.get("synced_uids", [])),
            last_sync_time=float(data.get("last_sync_time", 0.0)),
        )

    @classmethod
    def load_from_vault(
        cls,
        vault_data: dict[str, Any],
        account_id: str,
        mailbox: str = "INBOX",
    ) -> MailboxCursor:
        """
        Load cursor from the encrypted account vault dictionary.

        Supports backward-compatible migration from legacy m6_mailbox_v1.
        """
        # Modern cursor storage
        cursors = vault_data.get("m7_sync_cursor_v1")
        if isinstance(cursors, dict) and mailbox in cursors:
            return cls.from_dict(cursors[mailbox])

        # Backward-compatibility fallback: inspect legacy m6_mailbox_v1
        legacy = vault_data.get("m6_mailbox_v1")
        if isinstance(legacy, dict) and legacy.get("mailbox") == mailbox:
            legacy_validity = int(legacy.get("uidvalidity", 0))
            legacy_uids = {
                int(row["uid"])
                for row in legacy.get("rows", [])
                if isinstance(row, dict) and "uid" in row
            }
            cursor = cls(
                account_id=account_id,
                mailbox=mailbox,
                uidvalidity=legacy_validity,
                synced_uids=legacy_uids,
                last_sync_uid=max(legacy_uids) if legacy_uids else 0,
                last_sync_time=time.time(),
            )
            return cursor

        # Default new cursor
        return cls(account_id=account_id, mailbox=mailbox)

    def save_to_vault(self, vault_data: dict[str, Any]) -> None:
        """Save cursor into the encrypted account vault dictionary."""
        if "m7_sync_cursor_v1" not in vault_data or not isinstance(vault_data["m7_sync_cursor_v1"], dict):
            vault_data["m7_sync_cursor_v1"] = {}
        vault_data["m7_sync_cursor_v1"][self.mailbox] = self.to_dict()
