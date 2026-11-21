"""
Automated Pytest for Pressure Monitoring Rules on Two-Stage Air Compressor.
Tests:
- Normal delivery pressure range
- High discharge pressure warning
- Low pressure / pipeline leakage warning
- Critical overpressure breach
- Rapid pressure rise and drop
- Pressure sensor fault
"""

import pytest
from src.compressor_rules import CompressorRuleEngine

@pytest.fixture
def engine():
    eng = CompressorRuleEngine()
    eng.reset_state()
    return eng

def test_normal_pressure(engine):
    reading = {"value": 7.8, "unit": "bar"}
    res = engine.evaluate_sensor("pressure", reading)
    assert res["severity"] == "NORMAL"
    assert len(res["alerts"]) == 0

def test_high_pressure_warning(engine):
    reading = {"value": 10.1, "unit": "bar"} # Normal max is 9.5
    res = engine.evaluate_sensor("pressure", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "HIGH_PRESSURE" for a in res["alerts"])

def test_low_pressure_warning(engine):
    reading = {"value": 5.8, "unit": "bar"} # Normal min is 6.5
    res = engine.evaluate_sensor("pressure", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "LOW_PRESSURE" for a in res["alerts"])

def test_critical_overpressure(engine):
    reading = {"value": 12.5, "unit": "bar"} # Critical max is 12.0
    res = engine.evaluate_sensor("pressure", reading)
    assert res["severity"] == "CRITICAL"
    assert any("PRESSURE" in a["alert_type"] for a in res["alerts"])

def test_rapid_pressure_change(engine):
    engine.evaluate_sensor("pressure", {"value": 7.5, "unit": "bar"})
    # Drop from 7.5 to 5.5 bar (delta = -2.0 > max_rate 1.5)
    res = engine.evaluate_sensor("pressure", {"value": 5.5, "unit": "bar"})
    assert any(a["alert_type"] == "PRESSURE_DROP" for a in res["alerts"])

def test_pressure_sensor_fault(engine):
    res = engine.evaluate_sensor("pressure", None)
    assert res["severity"] == "SENSOR_FAULT"
    assert any(a["alert_type"] == "PRESSURE_SENSOR_FAULT" for a in res["alerts"])

