"""Tests for the SafetyEvent module."""

import json
import pytest

from blockchain_compliance.safety_event import SafetyEvent


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

def _make_event_data(**overrides):
    """Return a valid event data dict with optional overrides."""
    base = {
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


# --------------------------------------------------------------------------- #
#  Tests
# --------------------------------------------------------------------------- #

class TestSafetyEventCreation:
    """Test SafetyEvent creation and validation."""

    def test_from_dict_valid(self):
        data = _make_event_data()
        event = SafetyEvent.from_dict(data)
        assert event.mq2 == 387
        assert event.fan_state == "ON"
        assert event.risk_score == 0.82
        assert event.temperature == 38.5
        assert event.humidity == 65.0
        assert event.ir_detected is True

    def test_from_dict_missing_field(self):
        data = _make_event_data()
        del data["mq2"]
        with pytest.raises(ValueError, match="Missing required fields"):
            SafetyEvent.from_dict(data)

    def test_missing_temperature(self):
        data = _make_event_data()
        del data["temperature"]
        with pytest.raises(ValueError, match="Missing required fields"):
            SafetyEvent.from_dict(data)

    def test_invalid_fan_state(self):
        with pytest.raises(ValueError, match="fan_state"):
            SafetyEvent.from_dict(_make_event_data(fan_state="MAYBE"))

    def test_risk_score_out_of_range(self):
        with pytest.raises(ValueError, match="risk_score"):
            SafetyEvent.from_dict(_make_event_data(risk_score=1.5))

    def test_temperature_out_of_range(self):
        with pytest.raises(ValueError, match="temperature"):
            SafetyEvent.from_dict(_make_event_data(temperature=100.0))

    def test_humidity_out_of_range(self):
        with pytest.raises(ValueError, match="humidity"):
            SafetyEvent.from_dict(_make_event_data(humidity=120.0))

    def test_invalid_risk_level(self):
        with pytest.raises(ValueError, match="risk_level"):
            SafetyEvent.from_dict(_make_event_data(risk_level="UNKNOWN"))

    def test_invalid_action_taken(self):
        with pytest.raises(ValueError, match="action_taken"):
            SafetyEvent.from_dict(_make_event_data(action_taken="EXPLODE"))

    def test_auto_generated_event_id(self):
        data = _make_event_data()
        event = SafetyEvent.from_dict(data)
        assert event.event_id.startswith("evt-")


class TestCanonicalJson:
    """Test canonical JSON serialization determinism."""

    def test_sorted_keys(self):
        event = SafetyEvent.from_dict(_make_event_data(event_id="test-001"))
        canon = event.to_canonical_json()
        parsed = json.loads(canon)
        keys = list(parsed.keys())
        assert keys == sorted(keys), "Keys must be sorted"

    def test_compact_separators(self):
        event = SafetyEvent.from_dict(_make_event_data(event_id="test-002"))
        canon = event.to_canonical_json()
        assert " " not in canon, "Canonical JSON must have no spaces"

    def test_deterministic(self):
        """Same input must always produce the same canonical JSON."""
        data = _make_event_data(event_id="test-003")
        e1 = SafetyEvent.from_dict(data)
        e2 = SafetyEvent.from_dict(data)
        assert e1.to_canonical_json() == e2.to_canonical_json()

    def test_roundtrip(self):
        """Canonical JSON → parse → canonical JSON should be identical."""
        event = SafetyEvent.from_dict(_make_event_data(event_id="test-004"))
        canon1 = event.to_canonical_json()
        reparsed = SafetyEvent.from_dict(json.loads(canon1))
        canon2 = reparsed.to_canonical_json()
        assert canon1 == canon2
