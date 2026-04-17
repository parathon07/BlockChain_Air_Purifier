"""Tests for the Hasher module."""

import hashlib

from blockchain_compliance.safety_event import SafetyEvent
from blockchain_compliance.hasher import hash_event, hash_string, hash_bytes, hash_pair


def _make_event(**overrides):
    base = {
        "event_id": "test-hash-001",
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
    return SafetyEvent.from_dict(base)


class TestHashEvent:
    """Test SHA-256 hashing of safety events."""

    def test_deterministic(self):
        e1 = _make_event()
        e2 = _make_event()
        assert hash_event(e1) == hash_event(e2)

    def test_hex_length(self):
        event = _make_event()
        h = hash_event(event)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_avalanche(self):
        """Changing a single field should produce a completely different hash."""
        e_original = _make_event(mq2=387)
        e_modified = _make_event(mq2=388)
        assert hash_event(e_original) != hash_event(e_modified)

    def test_matches_manual_sha256(self):
        event = _make_event()
        canon = event.to_canonical_json()
        expected = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        assert hash_event(event) == expected


class TestHashString:
    """Test raw string hashing."""

    def test_known_value(self):
        # SHA-256 of "" is well-known
        assert hash_string("") == hashlib.sha256(b"").hexdigest()

    def test_hello(self):
        expected = hashlib.sha256(b"hello").hexdigest()
        assert hash_string("hello") == expected


class TestHashBytes:
    """Test raw bytes hashing."""

    def test_known(self):
        data = b"\x00\x01\x02"
        assert hash_bytes(data) == hashlib.sha256(data).hexdigest()


class TestHashPair:
    """Test pairwise hashing for Merkle tree."""

    def test_concatenation(self):
        a = "a" * 64
        b = "b" * 64
        expected = hashlib.sha256((a + b).encode("utf-8")).hexdigest()
        assert hash_pair(a, b) == expected

    def test_order_matters(self):
        a = hash_string("left")
        b = hash_string("right")
        assert hash_pair(a, b) != hash_pair(b, a)
