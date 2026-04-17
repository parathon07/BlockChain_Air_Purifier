"""Tests for the Compliance Pipeline (integration)."""

import os
import tempfile

import pytest

from blockchain_compliance.compliance_pipeline import CompliancePipeline
from blockchain_compliance.hasher import hash_string


@pytest.fixture
def pipeline():
    """Create a pipeline with small batch size in a temp directory."""
    tmpdir = tempfile.mkdtemp()
    return CompliancePipeline(
        db_path=os.path.join(tmpdir, "blocks.db"),
        events_db_path=os.path.join(tmpdir, "events.db"),
        batch_size=5,
    )


def _sample_event(index=0, **overrides):
    base = {
        "timestamp": f"2026-02-14T01:{index:02d}:00.000Z",
        "tool_detected": True,
        "mq2": 300 + index * 10,
        "mq7": 100 + index * 5,
        "temperature": 35.0 + index * 1.5,
        "humidity": 60.0 + index * 2.0,
        "ir_detected": True,
        "fan_state": "ON",
        "risk_score": min(0.5 + index * 0.1, 1.0),
        "risk_level": "HIGH",
        "action_taken": "FAN_ACTIVATED",
        "sensor_node_id": "ESP32-NODE-01",
    }
    base.update(overrides)
    return base


class TestEventProcessing:
    """Test processing events through the pipeline."""

    def test_single_event(self, pipeline):
        result = pipeline.process_event(_sample_event(0))
        assert "event_id" in result
        assert "event_hash" in result
        assert result["block_index"] == 1  # genesis is 0
        assert result["batch_triggered"] is False

    def test_batch_trigger(self, pipeline):
        """5 events should trigger a batch (batch_size=5)."""
        results = []
        for i in range(5):
            r = pipeline.process_event(_sample_event(i))
            results.append(r)

        assert results[-1]["batch_triggered"] is True
        assert "merkle_root" in results[-1]

    def test_chain_grows(self, pipeline):
        for i in range(3):
            pipeline.process_event(_sample_event(i))
        # genesis + 3 events = 4 blocks
        assert pipeline.blockchain.get_chain_length() == 4

    def test_chain_valid_after_events(self, pipeline):
        for i in range(10):
            pipeline.process_event(_sample_event(i))
        assert pipeline.blockchain.validate_chain() is True


class TestEventRetrieval:
    """Test retrieving stored events."""

    def test_get_event_by_id(self, pipeline):
        result = pipeline.process_event(_sample_event(0))
        event_id = result["event_id"]

        stored = pipeline.get_event(event_id)
        assert stored is not None
        assert stored["event_hash"] == result["event_hash"]
        assert stored["block_index"] == 1

    def test_get_event_by_hash(self, pipeline):
        result = pipeline.process_event(_sample_event(0))
        event_hash = result["event_hash"]

        stored = pipeline.get_event_by_hash(event_hash)
        assert stored is not None
        assert stored["event_id"] == result["event_id"]

    def test_get_nonexistent_event(self, pipeline):
        assert pipeline.get_event("nonexistent-id") is None


class TestChainStatus:
    """Test chain status reporting."""

    def test_initial_status(self, pipeline):
        status = pipeline.get_chain_status()
        assert status["chain_length"] == 1  # genesis only
        assert status["chain_valid"] is True
        assert status["total_batches"] == 0
        assert status["pending_batch_events"] == 0
        assert status["ethereum_connected"] is False

    def test_status_after_events(self, pipeline):
        for i in range(7):
            pipeline.process_event(_sample_event(i))

        status = pipeline.get_chain_status()
        assert status["chain_length"] == 8  # genesis + 7
        assert status["total_batches"] == 1  # batch of 5
        assert status["pending_batch_events"] == 2  # 7 - 5 = 2


class TestAudit:
    """Test audit functionality."""

    def test_audit_event_with_batch(self, pipeline):
        """Process 5 events (triggers batch), then audit the first."""
        results = []
        for i in range(5):
            results.append(pipeline.process_event(_sample_event(i)))

        event_id = results[0]["event_id"]
        audit = pipeline.audit_event(event_id, batch_index=0)

        assert audit is not None
        assert audit.hash_valid is True
        assert audit.merkle_valid is True
        # On-chain not available (no Ethereum)
        assert audit.on_chain_available is False

    def test_audit_nonexistent_event(self, pipeline):
        assert pipeline.audit_event("fake-id") is None


class TestShutdown:
    """Test pipeline shutdown."""

    def test_shutdown_flushes_pending(self, pipeline):
        for i in range(3):
            pipeline.process_event(_sample_event(i))

        assert pipeline.batch_manager.pending_count == 3
        record = pipeline.shutdown()
        assert record is not None
        assert pipeline.batch_manager.pending_count == 0
