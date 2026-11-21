"""
Automated Pytest for Electric Motor Current Monitoring Rules on Air Compressor.
Tests:
- Normal loaded motor current
- High current / motor overload warning
- Low current / unloaded or belt break warning
- Critical motor overcurrent
- Rapid current spike detection
- Current sensor fault
"""

import pytest
from src.compressor_rules import CompressorRuleEngine

@pytest.fixture
def engine():
    eng = CompressorRuleEngine()
    eng.reset_state()
    return eng

def test_normal_current(engine):
    reading = {"value": 18.5, "unit": "A"}
    res = engine.evaluate_sensor("current", reading)
    assert res["severity"] == "NORMAL"
    assert len(res["alerts"]) == 0

def test_high_current_warning(engine):
    reading = {"value": 24.5, "unit": "A"} # Normal max is 22.0
    res = engine.evaluate_sensor("current", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "HIGH_CURRENT" for a in res["alerts"])

def test_low_current_warning(engine):
    reading = {"value": 11.5, "unit": "A"} # Normal min is 14.0
    res = engine.evaluate_sensor("current", reading)
    assert res["severity"] == "WARNING"
    assert any(a["alert_type"] == "LOW_CURRENT" for a in res["alerts"])

def test_critical_current(engine):
    reading = {"value": 33.5, "unit": "A"} # Critical max is 32.0
    res = engine.evaluate_sensor("current", reading)
    assert res["severity"] == "CRITICAL"
    assert any("CURRENT" in a["alert_type"] for a in res["alerts"])

def test_rapid_current_increase(engine):
    engine.evaluate_sensor("current", {"value": 18.0, "unit": "A"})
    res = engine.evaluate_sensor("current", {"value": 23.0, "unit": "A"}) # +5.0 A > max_rate 4.0
    assert any(a["alert_type"] == "RAPID_CURRENT_INCREASE" for a in res["alerts"])

def test_current_sensor_fault(engine):
    res = engine.evaluate_sensor("current", None)
    assert res["severity"] == "SENSOR_FAULT"
    assert any(a["alert_type"] == "CURRENT_SENSOR_FAULT" for a in res["alerts"])

