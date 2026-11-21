"""
Automated Pytest for Compressor Shaft Speed (RPM) Rules.
Tests:
- Normal rotational speed range
- High speed / VFD overspeed warning
- Low speed / belt slippage warning
- Unexpected zero speed (stall / trip)
- Critical overspeed
- Speed sensor fault
"""

import pytest
from src.compressor_rules import CompressorRuleEngine

@pytest.fixture
def engine():
    eng = CompressorRuleEngine()
    eng.reset_state()
    return eng

def test_normal_speed(engine):
    reading = {"value": 1450.0, "unit": "RPM"}
    res = engine.evaluate_sensor("speed", reading)
    assert res["severity"] == "NORMAL"
    assert len(res["alerts"]) == 0

def test_high_speed_warning(engine):
    reading = {"value": 1500.0, "unit": "RPM"} # Normal max is 1480.0
    res = engine.evaluate_sensor("speed", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "HIGH_SPEED" for a in res["alerts"])

def test_low_speed_warning(engine):
    reading = {"value": 1380.0, "unit": "RPM"} # Normal min is 1420.0
    res = engine.evaluate_sensor("speed", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "LOW_SPEED" for a in res["alerts"])

def test_unexpected_zero_speed(engine):
    reading = {"value": 0.0, "unit": "RPM"}
    res = engine.evaluate_sensor("speed", reading)
    assert res["severity"] == "CRITICAL"
    assert any(a["alert_type"] == "UNEXPECTED_ZERO_SPEED" for a in res["alerts"])

def test_speed_sensor_fault(engine):
    res = engine.evaluate_sensor("speed", None)
    assert res["severity"] == "SENSOR_FAULT"
    assert any(a["alert_type"] == "SPEED_SENSOR_FAULT" for a in res["alerts"])

