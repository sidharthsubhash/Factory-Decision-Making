"""
Automated Pytest for End-to-End System Integration Scenarios.
Covers Section 12 test matrix:
- Multiple abnormal sensors simultaneously
- Sensor failure / invalid data rejection
- ML availability check (5-sensor compressor vs 8-feature SKAB replay)
- Persistence across restarts
- SKAB replay payload handling
"""

from datetime import datetime, timezone

import pytest
import sqlite3
from src.api import analyse_compressor_telemetry, CompressorTelemetryPayload
from src.predict import predict_reading
from src.event_store import EventStore, DB_PATH
from src.compressor_rules import CompressorRuleEngine

@pytest.fixture
def clean_engine():
    eng = CompressorRuleEngine()
    eng.reset_state()
    return eng

def test_scenario_multiple_abnormal_sensors():
    """TEST 7: Multiple abnormal sensors simultaneously."""
    payload = CompressorTelemetryPayload(
        message_id="TEST-INT-MULTI",
        machine_id="COMPRESSOR_01",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="WOKWI_SIMULATION",
        sequence=20,
        sensors={
            "temperature": {"value": 102.0, "unit": "°C"}, # High temp
            "vibration": {"value": 0.52, "unit": "g RMS"},  # High vib
            "pressure": {"value": 11.5, "unit": "bar"},    # High press
            "current": {"value": 27.5, "unit": "A"},        # High current
            "speed": {"value": 1450.0, "unit": "RPM"}
        }
    )
    res = analyse_compressor_telemetry(payload)
    assert res["overall_status"] in ["WARNING", "CRITICAL"]
    assert res["active_alerts_count"] >= 4
    # All 4 abnormal categories should have worker recommendations
    alert_types = [r["alert_type"] for r in res["worker_recommendations"]]
    assert any("TEMPERATURE" in t for t in alert_types)
    assert any("VIBRATION" in t for t in alert_types)
    assert any("PRESSURE" in t for t in alert_types)
    assert any("CURRENT" in t for t in alert_types)

def test_scenario_sensor_failure_invalid_data():
    """TEST 8: Sensor failure / invalid telemetry payload."""
    payload = CompressorTelemetryPayload(
        message_id="TEST-INT-FAULT",
        machine_id="COMPRESSOR_01",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="WOKWI_SIMULATION",
        sequence=21,
        sensors={
            "temperature": {"value": 75.0, "unit": "°C"},
            "vibration": {"value": -99.0, "unit": "bar"}, # Wrong unit for vibration
            "pressure": {"value": 7.5, "unit": "bar"},
            "current": {"value": 18.0, "unit": "A"},
            "speed": {"value": 1450.0, "unit": "RPM"}
        }
    )
    res = analyse_compressor_telemetry(payload)
    assert res["overall_status"] == "SENSOR_FAULT"
    assert "validation_errors" in res
    assert len(res["validation_errors"]) > 0

def test_scenario_skab_replay_integration():
    """TEST 11: SKAB dataset replay with genuine 8 features."""
    raw_8 = {
        "Accelerometer1RMS": 0.15,
        "Accelerometer2RMS": 0.20,
        "Current": 2.0,
        "Pressure": 0.07,
        "Temperature": 88.0,
        "Thermocouple": 26.0,
        "Voltage": 230.0,
        "Volume Flow RateRMS": 105.0
    }
    payload = CompressorTelemetryPayload(
        message_id="SKAB-01-ROW-00100",
        machine_id="SKAB_TESTBED_BENCHMARK",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="SKAB_DATASET_REPLAY",
        sequence=100,
        sensors={
            "temperature": {"value": 88.0, "unit": "°C"},
            "vibration": {"value": 0.15, "unit": "g RMS"},
            "pressure": {"value": 0.07, "unit": "bar"},
            "current": {"value": 2.0, "unit": "A"},
            "speed": {"value": 1450.0, "unit": "RPM"}
        },
        raw_eight_features=raw_8
    )
    res = analyse_compressor_telemetry(payload)
    # ML inference must be active because all 8 features were genuinely provided
    assert res["ml_inference"]["ml_available"] is True
    assert res["ml_inference"]["status"] in ["NORMAL", "ANOMALY"]
    assert "anomaly_probability" in res["ml_inference"]

def test_scenario_restart_and_persistence():
    """TEST 12: Restart and persistence check."""
    store = EventStore()
    events_before = store.get_recent_events(limit=5)
    # Re-instantiate store object to simulate service restart
    restarted_store = EventStore(db_path=DB_PATH)
    events_after = restarted_store.get_recent_events(limit=5)
    assert len(events_after) == len(events_before)
    if len(events_before) > 0:
        assert events_before[0]["id"] == events_after[0]["id"]

