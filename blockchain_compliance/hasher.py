"""
Event Hashing Module.

Provides SHA-256 hashing functions for safety events, raw strings, and
raw bytes.  All outputs are lowercase 64-character hex digest strings.
"""

from __future__ import annotations

import hashlib

from .safety_event import SafetyEvent


def hash_event(event: SafetyEvent) -> str:
    """
    Hash a SafetyEvent using its canonical JSON representation.

    Returns a 64-character lowercase hex digest (SHA-256).
    """
    canonical = event.to_canonical_json()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_string(data: str) -> str:
    """SHA-256 of a UTF-8 encoded string → 64-char hex digest."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes → 64-char hex digest."""
    return hashlib.sha256(data).hexdigest()


def hash_pair(left: str, right: str) -> str:
    """
    Hash two hex digest strings together (concatenated).

    Used internally by the Merkle tree for pairwise hashing.

    Parameters
    ----------
    left : str
        64-char hex digest.
    right : str
        64-char hex digest.

    Returns
    -------
    str
        SHA-256( left || right ) as 64-char hex digest.
    """
    combined = left + right
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
