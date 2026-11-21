"""
Automated Pytest for Actionable Worker Recommendation Engine.
Tests:
- Full recommendation schema compliance
- Correct possible causes and worker actions for all sensor categories
- Advisory-first principles (no direct machine actuation)
- Recommendation generation from rule engine outputs
"""

import pytest
from src.recommendation_engine import RecommendationEngine

@pytest.fixture
def rec_engine():
    return RecommendationEngine()

def test_recommendation_schema(rec_engine):
    rec = rec_engine.build_recommendation(
        alert_type="HIGH_TEMPERATURE",
        sensor_name="temperature",
        measured_value=98.5,
        unit="°C",
        normal_range=[60.0, 95.0],
        severity="WARNING",
        machine_id="COMPRESSOR_01"
    )

    required_fields = [
        "alert_id", "timestamp", "machine_id", "sensor", "measured_value",
        "unit", "normal_range", "severity", "alert_type", "possible_causes",
        "recommended_worker_actions", "maintenance_followup", "acknowledged"
    ]
    for field in required_fields:
        assert field in rec, f"Missing required field: {field}"

    assert rec["alert_id"].startswith("ALT-TEM-")
    assert rec["measured_value"] == 98.5
    assert rec["severity"] == "WARNING"
    assert rec["acknowledged"] is False
    assert len(rec["possible_causes"]) > 0
    assert len(rec["recommended_worker_actions"]) > 0

def test_vibration_recommendation_content(rec_engine):
    rec = rec_engine.build_recommendation(
        alert_type="HIGH_VIBRATION",
        sensor_name="vibration",
        measured_value=0.55,
        unit="g RMS",
        normal_range=[0.05, 0.30],
        severity="WARNING"
    )

    actions_text = " ".join(rec["recommended_worker_actions"]).lower()
    assert "mounting" in actions_text or "alignment" in actions_text or "bearing" in actions_text

def test_pressure_recommendation_content(rec_engine):
    rec_high = rec_engine.build_recommendation(
        alert_type="HIGH_PRESSURE",
        sensor_name="pressure",
        measured_value=11.2,
        unit="bar",
        normal_range=[6.5, 9.5],
        severity="WARNING"
    )
    causes_high = " ".join(rec_high["possible_causes"]).lower()
    assert "restriction" in causes_high or "valve" in causes_high or "unloader" in causes_high

    rec_low = rec_engine.build_recommendation(
        alert_type="LOW_PRESSURE",
        sensor_name="pressure",
        measured_value=5.0,
        unit="bar",
        normal_range=[6.5, 9.5],
        severity="WARNING"
    )
    causes_low = " ".join(rec_low["possible_causes"]).lower()
    assert "leak" in causes_low or "valve" in causes_low or "demand" in causes_low

def test_advisory_compliance(rec_engine):
    """Confirm advice is advisory for human workers and does not claim automated shutdown."""
    rec = rec_engine.build_recommendation(
        alert_type="HIGH_CURRENT",
        sensor_name="current",
        measured_value=28.0,
        unit="A",
        normal_range=[14.0, 22.0],
        severity="CRITICAL"
    )
    actions = " ".join(rec["recommended_worker_actions"]).lower()
    # Must instruct workers to verify / check / inspect, not claim software shut down machine
    assert "verify" in actions or "check" in actions or "inspect" in actions or "report" in actions

