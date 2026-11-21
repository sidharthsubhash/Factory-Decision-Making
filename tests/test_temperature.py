"""
Automated Pytest for Temperature Monitoring Rules on Two-Stage Air Compressor.
Tests:
- Normal temperature operation
- High temperature warning
- Critical temperature alarm
- Rapid temperature rise detection
- Temperature sensor failure / fault detection
"""

import pytest
from src.compressor_rules import CompressorRuleEngine

@pytest.fixture
def engine():
    eng = CompressorRuleEngine()
    eng.reset_state()
    return eng

def test_normal_temperature(engine):
    reading = {"value": 75.0, "unit": "°C"}
    res = engine.evaluate_sensor("temperature", reading)
    assert res["status"] == "NORMAL"
    assert res["severity"] == "NORMAL"
    assert len(res["alerts"]) == 0

def test_high_temperature_warning(engine):
    reading = {"value": 98.0, "unit": "°C"} # Normal max is 95.0
    res = engine.evaluate_sensor("temperature", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "HIGH_TEMPERATURE" for a in res["alerts"])

def test_critical_temperature(engine):
    reading = {"value": 125.0, "unit": "°C"} # Critical max is 120.0
    res = engine.evaluate_sensor("temperature", reading)
    assert res["severity"] == "CRITICAL"
    assert any(a["alert_type"] == "TEMPERATURE_CRITICAL" for a in res["alerts"])

def test_rapid_temperature_rise(engine):
    # Establish baseline
    engine.evaluate_sensor("temperature", {"value": 75.0, "unit": "°C"})
    # Jump by +8.0 °C (max rate is 5.0 °C/s)
    res = engine.evaluate_sensor("temperature", {"value": 83.0, "unit": "°C"})
    assert any("RAPID_TEMPERATURE" in a["alert_type"] for a in res["alerts"])

def test_temperature_sensor_fault(engine):
    res = engine.evaluate_sensor("temperature", None)
    assert res["severity"] == "SENSOR_FAULT"
    assert any(a["alert_type"] == "TEMPERATURE_SENSOR_FAULT" for a in res["alerts"])

