"""
Compliance Pipeline — End-to-End Orchestrator.

Ties all compliance modules together into a single entry point:

  Safety Event → Hash → Local Block → Batch → Merkle Root → Anchor

Also stores raw event data in a SQLite events table for auditor retrieval.

This module can be run as ``python -m blockchain_compliance.compliance_pipeline``
to execute a demonstration with sample events.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

from .safety_event import SafetyEvent
from .hasher import hash_event
from .blockchain import LocalBlockchain
from .merkle_tree import MerkleTree
from .batch_manager import BatchManager, BatchRecord
from .ethereum_anchor import EthereumAnchor
from .verifier import ComplianceVerifier, AuditResult
from . import config

logger = logging.getLogger(__name__)


class CompliancePipeline:
    """
    Orchestrates the full compliance lifecycle for safety events.

    Sequence per event:
        1. Create SafetyEvent from raw dict
        2. Compute SHA-256 hash
        3. Append block to local blockchain
        4. Store raw event + hash in events DB
        5. Feed hash into batch manager
        6. (Async) When batch full → Merkle root → anchor callback
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        events_db_path: Optional[str] = None,
        batch_size: int = 0,
        anchor_client: Optional[EthereumAnchor] = None,
    ) -> None:
        self.blockchain = LocalBlockchain(db_path)
        self._anchor_client = anchor_client
        self._events_db_path = events_db_path or config.EVENTS_DB_PATH

        os.makedirs(os.path.dirname(self._events_db_path), exist_ok=True)
        self._init_events_db()

        # Derive batch store path from the same data directory
        data_dir = os.path.dirname(self._events_db_path)
        batch_store_path = os.path.join(data_dir, "batches.json")

        self.batch_manager = BatchManager(
            batch_size=batch_size or config.BATCH_SIZE,
            anchor_callback=self._on_batch_ready,
            batch_store_path=batch_store_path,
        )
        self.verifier = ComplianceVerifier()

    # ------------------------------------------------------------------ #
    #  Events database
    # ------------------------------------------------------------------ #

    def _init_events_db(self) -> None:
        """Create the events table if it does not exist."""
        with sqlite3.connect(self._events_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id    TEXT PRIMARY KEY,
                    event_json  TEXT NOT NULL,
                    event_hash  TEXT NOT NULL,
                    block_index INTEGER NOT NULL,
                    batch_index INTEGER,
                    created_at  TEXT NOT NULL
                )
            """)

    def _store_event(
        self,
        event: SafetyEvent,
        event_hash: str,
        block_index: int,
    ) -> None:
        """Persist raw event data alongside its hash and block reference."""
        with sqlite3.connect(self._events_db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO events "
                "(event_id, event_json, event_hash, block_index, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.to_canonical_json(),
                    event_hash,
                    block_index,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    # ------------------------------------------------------------------ #
    #  Core processing
    # ------------------------------------------------------------------ #

    def process_event(self, event_data: dict) -> Dict[str, Any]:
        """
        Process a single safety event through the full compliance pipeline.

        Parameters
        ----------
        event_data : dict
            Raw safety event fields (from the Decision Layer).

        Returns
        -------
        dict
            Processing result with event_id, event_hash, block_index,
            and batch status.
        """
        # 1. Create SafetyEvent
        event = SafetyEvent.from_dict(event_data)

        # 2. Compute hash
        event_hash = hash_event(event)

        # 3. Append to local blockchain
        block = self.blockchain.add_block(event_hash)

        # 4. Store raw event
        self._store_event(event, event_hash, block.index)

        # 5. Feed into batch manager
        batch_record = self.batch_manager.add_event_hash(event_hash)

        result = {
            "event_id": event.event_id,
            "event_hash": event_hash,
            "block_index": block.index,
            "block_hash": block.block_hash,
            "batch_triggered": batch_record is not None,
        }

        if batch_record:
            result["batch_index"] = batch_record.batch_index
            result["merkle_root"] = batch_record.merkle_root

        logger.info(
            "Event processed: id=%s hash=%s block=%d",
            event.event_id, event_hash[:16] + "...", block.index,
        )
        return result

    # ------------------------------------------------------------------ #
    #  Batch callback
    # ------------------------------------------------------------------ #

    def _on_batch_ready(self, merkle_root: str, event_hashes: List[str]) -> None:
        """
        Called by BatchManager when a batch is complete.

        Anchors the Merkle root to Ethereum if a client is available.
        """
        logger.info(
            "Batch ready: root=%s, events=%d",
            merkle_root[:16] + "...", len(event_hashes),
        )

        if self._anchor_client:
            result = self._anchor_client.submit_anchor(merkle_root)
            if result.success:
                logger.info(
                    "Anchored to Ethereum: batch_id=%s tx=%s",
                    result.batch_id, result.tx_hash,
                )
            else:
                logger.warning(
                    "Ethereum anchoring failed: %s (will retry later)",
                    result.error,
                )
        else:
            logger.info("No Ethereum client configured — skipping anchoring.")

    # ------------------------------------------------------------------ #
    #  Queries
    # ------------------------------------------------------------------ #

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored event by ID."""
        with sqlite3.connect(self._events_db_path) as conn:
            row = conn.execute(
                "SELECT event_json, event_hash, block_index FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

        if row is None:
            return None
        return {
            "event_data": json.loads(row[0]),
            "event_hash": row[1],
            "block_index": row[2],
        }

    def get_event_by_hash(self, event_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored event by its hash."""
        with sqlite3.connect(self._events_db_path) as conn:
            row = conn.execute(
                "SELECT event_id, event_json, block_index FROM events WHERE event_hash = ?",
                (event_hash,),
            ).fetchone()

        if row is None:
            return None
        return {
            "event_id": row[0],
            "event_data": json.loads(row[1]),
            "block_index": row[2],
            "event_hash": event_hash,
        }

    def get_chain_status(self) -> Dict[str, Any]:
        """Return a summary of the current compliance system state."""
        return {
            "chain_length": self.blockchain.get_chain_length(),
            "chain_valid": self.blockchain.validate_chain(),
            "pending_batch_events": self.batch_manager.pending_count,
            "total_batches": self.batch_manager.total_batches,
            "ethereum_connected": (
                self._anchor_client.is_connected if self._anchor_client else False
            ),
        }

    # ------------------------------------------------------------------ #
    #  Audit
    # ------------------------------------------------------------------ #

    def audit_event(
        self,
        event_id: str,
        batch_index: Optional[int] = None,
    ) -> Optional[AuditResult]:
        """
        Run a full audit on a stored event.

        Parameters
        ----------
        event_id : str
            The event to audit.
        batch_index : int, optional
            The batch that contains this event (for Merkle proof).

        Returns
        -------
        AuditResult or None
            Full audit result, or None if the event is not found.
        """
        record = self.get_event(event_id)
        if record is None:
            logger.warning("Event not found: %s", event_id)
            return None

        event_data = record["event_data"]
        expected_hash = record["event_hash"]

        # If batch_index provided, get Merkle proof
        proof = []
        expected_root = ""

        if batch_index is not None:
            tree = self.batch_manager.get_merkle_tree_for_batch(batch_index)
            batch_record = self.batch_manager.get_batch(batch_index)

            if tree and batch_record:
                try:
                    leaf_idx = batch_record.event_hashes.index(expected_hash)
                    proof = tree.get_proof(leaf_idx)
                    expected_root = tree.get_root()
                except ValueError:
                    logger.warning(
                        "Event hash not found in batch %d", batch_index
                    )

        return self.verifier.full_audit(
            event_data=event_data,
            expected_hash=expected_hash,
            proof=proof,
            expected_root=expected_root,
            batch_id=batch_record.anchor_batch_id if batch_index is not None and batch_record else None,
            anchor_client=self._anchor_client,
        )

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def shutdown(self) -> Optional[BatchRecord]:
        """Flush any pending batch before shutting down."""
        logger.info("Shutting down compliance pipeline...")
        return self.batch_manager.flush()

    def __repr__(self) -> str:
        status = self.get_chain_status()
        return (
            f"CompliancePipeline(chain={status['chain_length']} blocks, "
            f"batches={status['total_batches']}, "
            f"pending={status['pending_batch_events']})"
        )


# --------------------------------------------------------------------------- #
#  Demo / Main
# --------------------------------------------------------------------------- #

def _demo() -> None:
    """Run a quick demonstration of the compliance pipeline."""
    import tempfile

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Use temp directories for demo
    tmpdir = tempfile.mkdtemp(prefix="compliance_demo_")
    db_path = os.path.join(tmpdir, "blocks.db")
    events_db_path = os.path.join(tmpdir, "events.db")

    pipeline = CompliancePipeline(
        db_path=db_path,
        events_db_path=events_db_path,
        batch_size=5,  # Small batch for demo
    )

    print("=" * 70)
    print("  BLOCKCHAIN COMPLIANCE LAYER — DEMONSTRATION")
    print("=" * 70)

    # Generate sample events
    sample_events = [
        {
            "timestamp": "2026-02-14T01:45:18.342Z",
            "tool_detected": True,
            "mq2": 387,
            "mq7": 142,
            "temperature": 38.5,
            "humidity": 65.0,
            "ir_detected": True,
            "fan_state": "ON",
            "risk_score": 0.82,
            "risk_level": "HIGH",
            "action_taken": "FAN_ACTIVATED",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:46:22.100Z",
            "tool_detected": True,
            "mq2": 415,
            "mq7": 158,
            "temperature": 42.0,
            "humidity": 72.0,
            "ir_detected": True,
            "fan_state": "ON",
            "risk_score": 0.91,
            "risk_level": "CRITICAL",
            "action_taken": "FAN_ACTIVATED",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:47:05.550Z",
            "tool_detected": False,
            "mq2": 120,
            "mq7": 45,
            "temperature": 30.0,
            "humidity": 55.0,
            "ir_detected": False,
            "fan_state": "ON",
            "risk_score": 0.35,
            "risk_level": "MEDIUM",
            "action_taken": "NONE",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:48:30.200Z",
            "tool_detected": False,
            "mq2": 55,
            "mq7": 22,
            "temperature": 26.0,
            "humidity": 45.0,
            "ir_detected": False,
            "fan_state": "OFF",
            "risk_score": 0.10,
            "risk_level": "LOW",
            "action_taken": "FAN_DEACTIVATED",
            "sensor_node_id": "ESP32-NODE-01",
        },
        {
            "timestamp": "2026-02-14T01:50:00.000Z",
            "tool_detected": True,
            "mq2": 510,
            "mq7": 200,
            "temperature": 48.0,
            "humidity": 80.0,
            "ir_detected": True,
            "fan_state": "ON",
            "risk_score": 0.95,
            "risk_level": "CRITICAL",
            "action_taken": "FAN_ACTIVATED",
            "sensor_node_id": "ESP32-NODE-02",
        },
    ]

    # Process events
    results = []
    print("\n📥 Processing safety events...\n")
    for i, event_data in enumerate(sample_events, 1):
        result = pipeline.process_event(event_data)
        results.append(result)
        print(f"  Event {i}: id={result['event_id']}")
        print(f"           hash={result['event_hash'][:32]}...")
        print(f"           block={result['block_index']}")
        if result.get("batch_triggered"):
            print(f"           ⚡ BATCH TRIGGERED → root={result['merkle_root'][:32]}...")
        print()

    # Chain status
    status = pipeline.get_chain_status()
    print("📊 Chain Status:")
    print(f"  Blocks:           {status['chain_length']}")
    print(f"  Chain Valid:      {'✅' if status['chain_valid'] else '❌'}")
    print(f"  Total Batches:    {status['total_batches']}")
    print(f"  Pending Events:   {status['pending_batch_events']}")
    print(f"  Ethereum:         {'🟢 Connected' if status['ethereum_connected'] else '🔴 Offline'}")
    print()

    # Audit the first event
    if results and pipeline.batch_manager.total_batches > 0:
        event_id = results[0]["event_id"]
        print(f"🔍 Auditing event: {event_id}")
        audit = pipeline.audit_event(event_id, batch_index=0)
        if audit:
            print(audit.summary())
        print()

    # Validate the chain
    print("🔗 Validating local blockchain integrity...")
    is_valid = pipeline.blockchain.validate_chain()
    print(f"  Result: {'✅ Chain is valid' if is_valid else '❌ Chain is TAMPERED'}")
    print()

    # Shutdown
    pipeline.shutdown()
    print("=" * 70)
    print(f"  Demo complete. Data stored in: {tmpdir}")
    print("=" * 70)


if __name__ == "__main__":
    _demo()
