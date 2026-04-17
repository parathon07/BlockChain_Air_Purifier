"""Tests for the Compliance Verifier module."""

import pytest

from blockchain_compliance.safety_event import SafetyEvent
from blockchain_compliance.hasher import hash_event, hash_string
from blockchain_compliance.merkle_tree import MerkleTree
from blockchain_compliance.verifier import ComplianceVerifier, AuditResult


def _make_event_data(**overrides):
    base = {
        "event_id": "test-verify-001",
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
    }
    base.update(overrides)
    return base


class TestHashIntegrity:
    """Test Step 1: Hash recomputation."""

    def test_valid_hash(self):
        data = _make_event_data()
        event = SafetyEvent.from_dict(data)
        correct_hash = hash_event(event)
        assert ComplianceVerifier.verify_event_integrity(data, correct_hash) is True

    def test_tampered_data(self):
        data = _make_event_data()
        event = SafetyEvent.from_dict(data)
        correct_hash = hash_event(event)

        # Tamper with the data
        data["mq2"] = 999
        assert ComplianceVerifier.verify_event_integrity(data, correct_hash) is False

    def test_wrong_hash(self):
        data = _make_event_data()
        wrong_hash = "f" * 64
        assert ComplianceVerifier.verify_event_integrity(data, wrong_hash) is False


class TestMerkleInclusion:
    """Test Step 2: Merkle proof verification."""

    def test_valid_inclusion(self):
        hashes = [hash_string(f"event-{i}") for i in range(8)]
        tree = MerkleTree(hashes)
        root = tree.get_root()

        for i, h in enumerate(hashes):
            proof = tree.get_proof(i)
            assert ComplianceVerifier.verify_merkle_inclusion(h, proof, root) is True

    def test_invalid_inclusion(self):
        hashes = [hash_string(f"event-{i}") for i in range(4)]
        tree = MerkleTree(hashes)
        root = tree.get_root()

        proof = tree.get_proof(0)
        fake_hash = hash_string("FAKE")
        assert ComplianceVerifier.verify_merkle_inclusion(fake_hash, proof, root) is False


class TestFullAudit:
    """Test the complete 3-step audit (without Ethereum)."""

    def test_full_audit_pass(self):
        # Create events and their hashes
        events = []
        hashes = []
        for i in range(4):
            data = _make_event_data(event_id=f"audit-{i}", mq2=300 + i)
            events.append(data)
            event = SafetyEvent.from_dict(data)
            hashes.append(hash_event(event))

        # Build Merkle tree
        tree = MerkleTree(hashes)
        root = tree.get_root()

        # Audit event 0
        proof = tree.get_proof(0)
        result = ComplianceVerifier.full_audit(
            event_data=events[0],
            expected_hash=hashes[0],
            proof=proof,
            expected_root=root,
        )

        assert result.hash_valid is True
        assert result.merkle_valid is True
        assert result.on_chain_valid is None  # No Ethereum
        assert result.fully_verified is True  # passes without on-chain

    def test_full_audit_tampered_event(self):
        data = _make_event_data(event_id="tamper-test")
        event = SafetyEvent.from_dict(data)
        correct_hash = hash_event(event)

        tree = MerkleTree([correct_hash])
        root = tree.get_root()
        proof = tree.get_proof(0)

        # Tamper
        data["mq2"] = 999

        result = ComplianceVerifier.full_audit(
            event_data=data,
            expected_hash=correct_hash,
            proof=proof,
            expected_root=root,
        )

        assert result.hash_valid is False
        assert result.fully_verified is False

    def test_audit_result_summary(self):
        result = AuditResult(
            hash_valid=True,
            computed_hash="a" * 64,
            expected_hash="a" * 64,
            merkle_valid=True,
            on_chain_valid=True,
            on_chain_available=True,
        )
        summary = result.summary()
        assert "✅ VERIFIED" in summary
        assert "PASS" in summary
