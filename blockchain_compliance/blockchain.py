"""
Local Blockchain Module.

Implements an append-only chain of blocks stored in a local SQLite database.
Each block contains an event hash, a reference to the previous block's hash,
and its own computed block hash — forming a cryptographic chain.
"""

from __future__ import annotations

import hashlib
import sqlite3
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from . import config


# --------------------------------------------------------------------------- #
#  Block data structure
# --------------------------------------------------------------------------- #

@dataclass
class Block:
    """A single block in the local compliance blockchain."""

    index: int
    timestamp: str
    event_hash: str
    previous_hash: str
    block_hash: str = ""

    def compute_hash(self) -> str:
        """
        Compute the SHA-256 hash of this block's contents.

        hash = SHA-256( str(index) + timestamp + event_hash + previous_hash )
        """
        payload = f"{self.index}{self.timestamp}{self.event_hash}{self.previous_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def __post_init__(self) -> None:
        if not self.block_hash:
            self.block_hash = self.compute_hash()


# --------------------------------------------------------------------------- #
#  Local Blockchain
# --------------------------------------------------------------------------- #

ZERO_HASH = "0" * 64  # 64 hex zeros — used for the genesis block


class LocalBlockchain:
    """
    Append-only local blockchain backed by SQLite.

    Provides block creation, chaining, persistence, and chain validation.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

        if self.get_chain_length() == 0:
            self._create_genesis_block()

    # ------------------------------------------------------------------ #
    #  Database setup
    # ------------------------------------------------------------------ #

    def _init_db(self) -> None:
        """Create the blocks table if it does not exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    idx           INTEGER PRIMARY KEY,
                    timestamp     TEXT    NOT NULL,
                    event_hash    TEXT    NOT NULL,
                    previous_hash TEXT    NOT NULL,
                    block_hash    TEXT    NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------ #
    #  Genesis
    # ------------------------------------------------------------------ #

    def _create_genesis_block(self) -> Block:
        """Create and persist the genesis block (index 0, all-zero hashes)."""
        now = datetime.now(timezone.utc).isoformat()
        genesis = Block(
            index=0,
            timestamp=now,
            event_hash=ZERO_HASH,
            previous_hash=ZERO_HASH,
        )
        self._persist_block(genesis)
        return genesis

    # ------------------------------------------------------------------ #
    #  Block operations
    # ------------------------------------------------------------------ #

    def add_block(self, event_hash: str) -> Block:
        """
        Append a new block to the chain.

        Parameters
        ----------
        event_hash : str
            SHA-256 hex digest of the safety event.

        Returns
        -------
        Block
            The newly created and persisted block.
        """
        latest = self.get_latest_block()
        now = datetime.now(timezone.utc).isoformat()

        new_block = Block(
            index=latest.index + 1,
            timestamp=now,
            event_hash=event_hash,
            previous_hash=latest.block_hash,
        )
        self._persist_block(new_block)
        return new_block

    def _persist_block(self, block: Block) -> None:
        """Write a block to the SQLite database."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO blocks (idx, timestamp, event_hash, previous_hash, block_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (block.index, block.timestamp, block.event_hash,
                 block.previous_hash, block.block_hash),
            )

    # ------------------------------------------------------------------ #
    #  Queries
    # ------------------------------------------------------------------ #

    def get_block(self, index: int) -> Optional[Block]:
        """Retrieve a block by index."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT idx, timestamp, event_hash, previous_hash, block_hash "
                "FROM blocks WHERE idx = ?",
                (index,),
            ).fetchone()

        if row is None:
            return None
        return Block(index=row[0], timestamp=row[1], event_hash=row[2],
                     previous_hash=row[3], block_hash=row[4])

    def get_latest_block(self) -> Block:
        """Return the most recent block in the chain."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT idx, timestamp, event_hash, previous_hash, block_hash "
                "FROM blocks ORDER BY idx DESC LIMIT 1"
            ).fetchone()

        if row is None:
            raise RuntimeError("Blockchain is empty — no genesis block found.")
        return Block(index=row[0], timestamp=row[1], event_hash=row[2],
                     previous_hash=row[3], block_hash=row[4])

    def get_chain_length(self) -> int:
        """Return the number of blocks in the chain."""
        with self._connect() as conn:
            result = conn.execute("SELECT COUNT(*) FROM blocks").fetchone()
        return result[0]

    def get_all_blocks(self) -> List[Block]:
        """Return all blocks in the chain, ordered by index."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT idx, timestamp, event_hash, previous_hash, block_hash "
                "FROM blocks ORDER BY idx ASC"
            ).fetchall()

        return [
            Block(index=r[0], timestamp=r[1], event_hash=r[2],
                  previous_hash=r[3], block_hash=r[4])
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #

    def validate_chain(self) -> bool:
        """
        Validate the entire chain.

        Checks:
        1. Each block's stored hash matches its recomputed hash.
        2. Each block's previous_hash matches the preceding block's block_hash.

        Returns True if the chain is valid, False otherwise.
        """
        blocks = self.get_all_blocks()
        if not blocks:
            return True

        for i, block in enumerate(blocks):
            # Verify block hash integrity
            expected_hash = block.compute_hash()
            if block.block_hash != expected_hash:
                return False

            # Verify chain linkage (skip genesis)
            if i > 0:
                if block.previous_hash != blocks[i - 1].block_hash:
                    return False

        return True

    def __repr__(self) -> str:
        return f"LocalBlockchain(length={self.get_chain_length()}, db={self.db_path})"
