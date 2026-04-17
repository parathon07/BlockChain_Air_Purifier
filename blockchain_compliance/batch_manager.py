"""
Batch Manager Module.

Accumulates event hashes and triggers Merkle root generation + anchoring
when the batch is full or a time threshold is exceeded.  Thread-safe.
"""

from __future__ import annotations

import logging
import threading
import time
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Callable, Optional, Dict, Any
from pathlib import Path

from .merkle_tree import MerkleTree
from . import config

logger = logging.getLogger(__name__)


@dataclass
class BatchRecord:
    """Metadata for a completed batch."""
    batch_index: int
    merkle_root: str
    event_hashes: List[str]
    created_at: str
    anchored: bool = False
    anchor_tx_hash: Optional[str] = None
    anchor_batch_id: Optional[int] = None


class BatchManager:
    """
    Manages the batching of event hashes and triggers anchoring.

    When the number of accumulated hashes reaches ``batch_size``, the manager
    builds a Merkle tree, computes the root, and invokes the
    ``anchor_callback`` with the root.  A time-based fallback ensures that
    small batches are still anchored within ``time_trigger_seconds``.
    """

    def __init__(
        self,
        batch_size: int = 0,
        time_trigger_seconds: int = 0,
        anchor_callback: Optional[Callable[[str, List[str]], Any]] = None,
        batch_store_path: Optional[str] = None,
    ) -> None:
        self.batch_size = batch_size or config.BATCH_SIZE
        self.time_trigger_seconds = time_trigger_seconds or config.BATCH_TIME_TRIGGER_SECONDS
        self.anchor_callback = anchor_callback

        self._pending_hashes: List[str] = []
        self._lock = threading.Lock()
        self._batch_counter = 0
        self._last_flush_time = time.time()

        # Persist batch records to disk
        self._batch_store_path = batch_store_path or str(
            Path(config.BASE_DIR) / "data" / "batches.json"
        )
        self._batch_records: List[BatchRecord] = []
        self._load_batch_records()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def add_event_hash(self, event_hash: str) -> Optional[BatchRecord]:
        """
        Add an event hash to the pending batch.

        Returns a BatchRecord if the batch was triggered, else None.
        """
        with self._lock:
            self._pending_hashes.append(event_hash)

            if self._should_trigger():
                return self._process_batch()

        return None

    def flush(self) -> Optional[BatchRecord]:
        """
        Force-process whatever is accumulated, regardless of batch size.

        Returns a BatchRecord if there were pending hashes, else None.
        """
        with self._lock:
            if self._pending_hashes:
                return self._process_batch()
        return None

    def check_time_trigger(self) -> Optional[BatchRecord]:
        """
        If the time threshold has elapsed, flush the current batch.

        This should be called periodically (e.g., from a timer thread).
        """
        with self._lock:
            elapsed = time.time() - self._last_flush_time
            if elapsed >= self.time_trigger_seconds and self._pending_hashes:
                return self._process_batch()
        return None

    # ------------------------------------------------------------------ #
    #  Internals
    # ------------------------------------------------------------------ #

    def _should_trigger(self) -> bool:
        """Check if the batch size threshold has been reached."""
        return len(self._pending_hashes) >= self.batch_size

    def _process_batch(self) -> BatchRecord:
        """
        Build Merkle tree from pending hashes, invoke callback, record batch.

        Must be called while holding ``self._lock``.
        """
        hashes = list(self._pending_hashes)
        self._pending_hashes.clear()
        self._last_flush_time = time.time()

        # Build Merkle tree
        tree = MerkleTree(hashes)
        root = tree.get_root()

        # Record
        record = BatchRecord(
            batch_index=self._batch_counter,
            merkle_root=root,
            event_hashes=hashes,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._batch_counter += 1
        self._batch_records.append(record)
        self._save_batch_records()

        logger.info(
            "Batch %d processed: %d events → root=%s",
            record.batch_index, len(hashes), root[:16] + "...",
        )

        # Invoke anchor callback (async — does not block safety path)
        if self.anchor_callback:
            try:
                self.anchor_callback(root, hashes)
            except Exception as e:
                logger.error("Anchor callback failed for batch %d: %s",
                             record.batch_index, e)

        return record

    # ------------------------------------------------------------------ #
    #  Batch persistence
    # ------------------------------------------------------------------ #

    def _load_batch_records(self) -> None:
        """Load existing batch records from disk."""
        if os.path.exists(self._batch_store_path):
            try:
                with open(self._batch_store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._batch_records = [
                    BatchRecord(**item) for item in data
                ]
                self._batch_counter = len(self._batch_records)
            except Exception as e:
                logger.warning("Could not load batch records: %s", e)

    def _save_batch_records(self) -> None:
        """Persist batch records to disk."""
        os.makedirs(os.path.dirname(self._batch_store_path), exist_ok=True)
        try:
            with open(self._batch_store_path, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "batch_index": r.batch_index,
                            "merkle_root": r.merkle_root,
                            "event_hashes": r.event_hashes,
                            "created_at": r.created_at,
                            "anchored": r.anchored,
                            "anchor_tx_hash": r.anchor_tx_hash,
                            "anchor_batch_id": r.anchor_batch_id,
                        }
                        for r in self._batch_records
                    ],
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.error("Could not save batch records: %s", e)

    # ------------------------------------------------------------------ #
    #  Queries
    # ------------------------------------------------------------------ #

    def get_batch(self, batch_index: int) -> Optional[BatchRecord]:
        """Retrieve a batch record by index."""
        if 0 <= batch_index < len(self._batch_records):
            return self._batch_records[batch_index]
        return None

    def get_all_batches(self) -> List[BatchRecord]:
        """Return all completed batch records."""
        return list(self._batch_records)

    @property
    def pending_count(self) -> int:
        """Number of event hashes waiting in the current batch."""
        with self._lock:
            return len(self._pending_hashes)

    @property
    def total_batches(self) -> int:
        """Total number of processed batches."""
        return self._batch_counter

    def get_merkle_tree_for_batch(self, batch_index: int) -> Optional[MerkleTree]:
        """Rebuild the Merkle tree for a specific batch (for proof generation)."""
        record = self.get_batch(batch_index)
        if record is None:
            return None
        return MerkleTree(record.event_hashes)

    def __repr__(self) -> str:
        return (
            f"BatchManager(batch_size={self.batch_size}, "
            f"pending={self.pending_count}, total_batches={self.total_batches})"
        )
