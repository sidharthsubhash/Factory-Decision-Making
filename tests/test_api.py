"""
Automated Pytest for FastAPI Microservice Endpoints.
Tests:
- GET /health
- GET /machine/status
- POST /predict (8-feature contract)
- POST /compressor/analyse (5-sensor telemetry)
- GET /alerts & POST /alerts/{alert_id}/acknowledge
- GET /events & GET /events/export
"""

from datetime import datetime, timezone

import pytest
from src.api import (
    health, machine_status, predict, analyse_compressor_telemetry,
    get_alerts, acknowledge_alert, get_events, export_events,
    SensorReading8, CompressorTelemetryPayload, AcknowledgeRequest
)

def test_api_health():
    res = health()
    assert res["status"] == "healthy"
    assert res["model_loaded"] is True
    assert res["features_monitored"] == 5

def test_api_machine_status():
    res = machine_status()
    assert res["machine_id"] == "COMPRESSOR_01"
    assert "Two-Stage" in res["asset_name"]

def test_api_predict_8_features():
    reading = SensorReading8(
        accelerometer1_rms=0.15,
        accelerometer2_rms=0.20,
        current=2.0,
        pressure=0.07,
        temperature=88.0,
        thermocouple=26.0,
        voltage=230.0,
        volume_flow_rate_rms=105.0
    )
    res = predict(reading)
    assert res["status"] in ["NORMAL", "ANOMALY"]
    assert res["ml_available"] is True
    assert "latency_ms" in res

def test_api_compressor_analyse_normal():
    payload = CompressorTelemetryPayload(
        message_id="TEST-API-NORM",
        machine_id="COMPRESSOR_01",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="WOKWI_SIMULATION",
        sequence=10,
        sensors={
            "temperature": {"value": 75.0, "unit": "°C"},
            "vibration": {"value": 0.18, "unit": "g RMS"},
            "pressure": {"value": 7.5, "unit": "bar"},
            "current": {"value": 18.0, "unit": "A"},
            "speed": {"value": 1450.0, "unit": "RPM"}
        }
    )
    res = analyse_compressor_telemetry(payload)
    assert res["overall_status"] == "NORMAL"
    assert res["active_alerts_count"] == 0
    assert res["ml_inference"]["status"] == "UNAVAILABLE"

def test_api_compressor_analyse_abnormal():
    payload = CompressorTelemetryPayload(
        message_id="TEST-API-ABNORM",
        machine_id="COMPRESSOR_01",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="WOKWI_SIMULATION",
        sequence=11,
        sensors={
            "temperature": {"value": 98.0, "unit": "°C"}, # High temp
            "vibration": {"value": 0.50, "unit": "g RMS"}, # High vibration
            "pressure": {"value": 7.5, "unit": "bar"},
            "current": {"value": 18.0, "unit": "A"},
            "speed": {"value": 1450.0, "unit": "RPM"}
        }
    )
    res = analyse_compressor_telemetry(payload)
    assert res["overall_status"] in ["WARNING", "CRITICAL"]
    assert len(res["worker_recommendations"]) >= 2

def test_api_alerts_and_acknowledgement():
    # Fetch alerts
    alerts_res = get_alerts(active_only=False)
    assert "alerts" in alerts_res
    if len(alerts_res["alerts"]) > 0:
        target_alert = alerts_res["alerts"][0]
        alert_id = target_alert["alert_id"]
        ack_res = acknowledge_alert(alert_id, AcknowledgeRequest(acknowledged_by="Test_Operator"))
        assert ack_res["acknowledged"] is True

def test_api_events_and_export():
    events_res = get_events(limit=10)
    assert "events" in events_res
    csv_text = export_events()
    assert "timestamp" in csv_text
    assert "machine_id" in csv_text

def test_api_cloud_endpoints():
    from src.api import get_cloud_status, trigger_cloud_sync, update_cloud_token, CloudTokenRequest
    status = get_cloud_status()
    assert "provider" in status
    assert status["provider"] == "ThingsBoard Cloud"

    sync_res = trigger_cloud_sync()
    assert "status" in sync_res

    token_res = update_cloud_token(CloudTokenRequest(token="TEST_TB_TOKEN_12345"))
    assert token_res["success"] is True
    assert token_res["cloud_status"]["token_configured"] is True

