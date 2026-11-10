"""
services/directory/merkle.py — Cryptographic Binary Merkle Tree for QuMail Directory Transparency.

Conforms to RFC 6962 / RFC 9162 Certificate Transparency principles:
- Domain-separated leaf hashing with byte prefix 0x00: SHA256(0x00 || LeafData)
- Domain-separated internal node hashing with byte prefix 0x01: SHA256(0x01 || Left || Right)
- Generates Signed Tree Heads (STH)
- Computes audit inclusion proofs (O(log N))
- Computes audit consistency proofs (O(log M))
- Independent verification functions for desktop clients and external monitors
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional


def hash_leaf(data: bytes) -> bytes:
    """Compute leaf hash with 0x00 domain separator prefix."""
    return hashlib.sha256(b"\x00" + data).digest()


def hash_children(left: bytes, right: bytes) -> bytes:
    """Compute internal node hash with 0x01 domain separator prefix."""
    return hashlib.sha256(b"\x01" + left + right).digest()


@dataclass
class LogEntry:
    entry_type: str           # "ENROLLMENT", "ROTATION", "REVOCATION", "RECOVERY"
    email_normalized: str
    fingerprint: str
    generation: int
    certificate_armor: str
    timestamp_utc: str
    leaf_index: int = 0

    def serialize(self) -> bytes:
        payload = {
            "type": self.entry_type,
            "email": self.email_normalized,
            "fingerprint": self.fingerprint,
            "generation": self.generation,
            "certificate_armor": self.certificate_armor,
            "timestamp": self.timestamp_utc,
            "leaf_index": self.leaf_index,
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")


@dataclass
class SignedTreeHead:
    tree_size: int
    timestamp_utc: str
    root_hash: str
    signature: str = ""

    def signable_bytes(self) -> bytes:
        return f"QUMAIL-STH-v1:{self.tree_size}:{self.timestamp_utc}:{self.root_hash}".encode("utf-8")


class MerkleTree:
    """
    Append-only binary Merkle tree with history preservation and proof generation.
    """

    def __init__(self) -> None:
        self.entries: list[LogEntry] = []
        self.leaf_hashes: list[bytes] = []

    def append(self, entry: LogEntry) -> int:
        entry.leaf_index = len(self.entries)
        leaf_bytes = entry.serialize()
        lh = hash_leaf(leaf_bytes)

        self.entries.append(entry)
        self.leaf_hashes.append(lh)
        return entry.leaf_index

    @property
    def tree_size(self) -> int:
        return len(self.leaf_hashes)

    def get_root_hash(self) -> bytes:
        if not self.leaf_hashes:
            return hashlib.sha256(b"").digest()
        return self._compute_subtree_root(0, len(self.leaf_hashes))

    def _compute_subtree_root(self, start: int, end: int) -> bytes:
        count = end - start
        if count == 1:
            return self.leaf_hashes[start]
        # Largest power of 2 less than count
        k = 1 << ((count - 1).bit_length() - 1)
        left = self._compute_subtree_root(start, start + k)
        right = self._compute_subtree_root(start + k, end)
        return hash_children(left, right)

    def get_inclusion_proof(self, leaf_index: int) -> list[str]:
        """Compute RFC 6962 audit path from leaf_index to tree root."""
        if leaf_index < 0 or leaf_index >= len(self.leaf_hashes):
            raise IndexError("Leaf index out of bounds")

        proof_hashes: list[bytes] = []
        self._build_inclusion_path(leaf_index, 0, len(self.leaf_hashes), proof_hashes)
        return [h.hex() for h in proof_hashes]

    def _build_inclusion_path(self, index: int, start: int, end: int, proof: list[bytes]) -> None:
        count = end - start
        if count == 1:
            return
        k = 1 << ((count - 1).bit_length() - 1)
        if index < start + k:
            self._build_inclusion_path(index, start, start + k, proof)
            proof.append(self._compute_subtree_root(start + k, end))
        else:
            self._build_inclusion_path(index, start + k, end, proof)
            proof.append(self._compute_subtree_root(start, start + k))

    def get_consistency_proof(self, m: int) -> list[str]:
        """Compute consistency proof showing tree at current size extends tree at size m."""
        n = len(self.leaf_hashes)
        if m < 0 or m > n:
            raise ValueError("Invalid consistency proof boundaries")
        if m == 0 or m == n:
            return []

        proof: list[bytes] = []
        self._build_consistency_proof(m, 0, n, True, proof)
        return [h.hex() for h in proof]

    def _build_consistency_proof(self, m: int, start: int, end: int, b: bool, proof: list[bytes]) -> None:
        count = end - start
        if m == count:
            if not b:
                proof.append(self._compute_subtree_root(start, end))
            return
        k = 1 << ((count - 1).bit_length() - 1)
        if m <= k:
            self._build_consistency_proof(m, start, start + k, b, proof)
            proof.append(self._compute_subtree_root(start + k, end))
        else:
            self._build_consistency_proof(m - k, start + k, end, False, proof)
            proof.append(self._compute_subtree_root(start, start + k))


# ---------------------------------------------------------------------------
# Client Verification Helpers
# ---------------------------------------------------------------------------

def verify_inclusion(leaf_data: bytes, leaf_index: int, tree_size: int, proof_hex: list[str], root_hash_hex: str) -> bool:
    """Verify an RFC 6962 inclusion proof client-side."""
    if leaf_index < 0 or leaf_index >= tree_size:
        return False

    current = hash_leaf(leaf_data)
    idx = leaf_index
    last = tree_size - 1

    for step_hex in proof_hex:
        step = bytes.fromhex(step_hex)
        if idx % 2 == 1 or idx == last:
            current = hash_children(step, current)
            while idx > 0 and idx % 2 == 0:
                idx //= 2
                last //= 2
        else:
            current = hash_children(current, step)
        idx //= 2
        last //= 2

    return current.hex() == root_hash_hex.lower()
