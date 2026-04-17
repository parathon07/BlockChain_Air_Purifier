"""Tests for the Batch Manager module."""

import os
import tempfile

import pytest

from blockchain_compliance.batch_manager import BatchManager
from blockchain_compliance.hasher import hash_string


@pytest.fixture
def tmpdir():
    return tempfile.mkdtemp()


class TestBatchTrigger:
    """Test batch triggering at the correct size."""

    def test_triggers_at_batch_size(self, tmpdir):
        results = []

        def callback(root, hashes):
            results.append({"root": root, "count": len(hashes)})

        mgr = BatchManager(
            batch_size=5,
            anchor_callback=callback,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )

        for i in range(4):
            record = mgr.add_event_hash(hash_string(f"e{i}"))
            assert record is None  # Not triggered yet

        # 5th event should trigger
        record = mgr.add_event_hash(hash_string("e4"))
        assert record is not None
        assert record.batch_index == 0
        assert len(record.event_hashes) == 5
        assert len(results) == 1
        assert results[0]["count"] == 5

    def test_no_trigger_below_size(self, tmpdir):
        mgr = BatchManager(
            batch_size=10,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )
        for i in range(9):
            assert mgr.add_event_hash(hash_string(f"e{i}")) is None
        assert mgr.pending_count == 9

    def test_multiple_batches(self, tmpdir):
        batches = []

        def callback(root, hashes):
            batches.append(root)

        mgr = BatchManager(
            batch_size=3,
            anchor_callback=callback,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )

        for i in range(9):
            mgr.add_event_hash(hash_string(f"event-{i}"))

        assert len(batches) == 3
        assert mgr.total_batches == 3
        assert mgr.pending_count == 0


class TestFlush:
    """Test manual flush behavior."""

    def test_flush_partial_batch(self, tmpdir):
        results = []

        def callback(root, hashes):
            results.append(root)

        mgr = BatchManager(
            batch_size=100,  # Won't trigger naturally
            anchor_callback=callback,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )

        for i in range(7):
            mgr.add_event_hash(hash_string(f"e{i}"))

        record = mgr.flush()
        assert record is not None
        assert len(record.event_hashes) == 7
        assert len(results) == 1
        assert mgr.pending_count == 0

    def test_flush_empty(self, tmpdir):
        mgr = BatchManager(
            batch_size=10,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )
        assert mgr.flush() is None


class TestBatchPersistence:
    """Test batch record persistence to disk."""

    def test_records_saved(self, tmpdir):
        store_path = os.path.join(tmpdir, "batches.json")
        mgr = BatchManager(
            batch_size=3,
            batch_store_path=store_path,
        )

        for i in range(3):
            mgr.add_event_hash(hash_string(f"e{i}"))

        assert os.path.exists(store_path)
        assert mgr.total_batches == 1

        # Load from same file
        mgr2 = BatchManager(
            batch_size=3,
            batch_store_path=store_path,
        )
        assert mgr2.total_batches == 1
        batch = mgr2.get_batch(0)
        assert batch is not None
        assert len(batch.event_hashes) == 3


class TestBatchQueries:
    """Test batch record queries."""

    def test_get_batch(self, tmpdir):
        mgr = BatchManager(
            batch_size=2,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )
        mgr.add_event_hash(hash_string("a"))
        mgr.add_event_hash(hash_string("b"))

        batch = mgr.get_batch(0)
        assert batch is not None
        assert batch.merkle_root  # non-empty

    def test_get_merkle_tree_for_batch(self, tmpdir):
        mgr = BatchManager(
            batch_size=4,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )
        hashes = [hash_string(f"e{i}") for i in range(4)]
        for h in hashes:
            mgr.add_event_hash(h)

        tree = mgr.get_merkle_tree_for_batch(0)
        assert tree is not None
        batch = mgr.get_batch(0)
        assert tree.get_root() == batch.merkle_root

    def test_get_nonexistent_batch(self, tmpdir):
        mgr = BatchManager(
            batch_size=10,
            batch_store_path=os.path.join(tmpdir, "batches.json"),
        )
        assert mgr.get_batch(999) is None
