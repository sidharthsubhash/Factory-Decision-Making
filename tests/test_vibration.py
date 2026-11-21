"""
Automated Pytest for Vibration Monitoring Rules on Two-Stage Air Compressor.
Tests:
- Normal vibration baseline
- High vibration warning
- Critical vibration threshold breach
- Rapid vibration jump
- Persistent vibration over multiple samples
- Vibration sensor fault
"""

import pytest
from src.compressor_rules import CompressorRuleEngine

@pytest.fixture
def engine():
    eng = CompressorRuleEngine()
    eng.reset_state()
    return eng

def test_normal_vibration(engine):
    reading = {"value": 0.18, "unit": "g RMS"}
    res = engine.evaluate_sensor("vibration", reading)
    assert res["severity"] == "NORMAL"
    assert len(res["alerts"]) == 0

def test_high_vibration_warning(engine):
    reading = {"value": 0.38, "unit": "g RMS"} # Normal max is 0.30
    res = engine.evaluate_sensor("vibration", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "HIGH_VIBRATION" for a in res["alerts"])

def test_critical_vibration(engine):
    reading = {"value": 0.85, "unit": "g RMS"} # Critical max is 0.75
    res = engine.evaluate_sensor("vibration", reading)
    assert res["severity"] == "CRITICAL"
    assert any("VIBRATION" in a["alert_type"] for a in res["alerts"])

def test_rapid_vibration_increase(engine):
    engine.evaluate_sensor("vibration", {"value": 0.15, "unit": "g RMS"})
    res = engine.evaluate_sensor("vibration", {"value": 0.40, "unit": "g RMS"}) # Delta is +0.25 > 0.15
    assert any(a["alert_type"] == "RAPID_VIBRATION_INCREASE" for a in res["alerts"])

def test_persistent_vibration(engine):
    # Send high vibration for 3 consecutive samples (configured persistence_samples = 3)
    engine.evaluate_sensor("vibration", {"value": 0.35, "unit": "g RMS"})
    engine.evaluate_sensor("vibration", {"value": 0.35, "unit": "g RMS"})
    res = engine.evaluate_sensor("vibration", {"value": 0.35, "unit": "g RMS"})
    assert any(a["alert_type"] == "PERSISTENT_VIBRATION" for a in res["alerts"])

def test_vibration_sensor_fault(engine):
    res = engine.evaluate_sensor("vibration", None)
    assert res["severity"] == "SENSOR_FAULT"
    assert any(a["alert_type"] == "VIBRATION_SENSOR_FAULT" for a in res["alerts"])

