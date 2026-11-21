"""
FastAPI Backend for Edge-Based Two-Stage Industrial Reciprocating Air Compressor.

Provides modular endpoints for:
1. Eight-feature ML inference (/predict) - Preserved contract
2. Unified 5-sensor compressor rule analysis & worker recommendations (/compressor/analyse)
3. Machine status monitoring (/machine/status)
4. System health (/health)
5. Active alerts & worker recommendations (/alerts, /alerts/{alert_id}/acknowledge)
6. Event history retrieval & CSV export (/events, /events/export)
"""

import time
import json
import threading
from io import BytesIO
from collections import OrderedDict
import numpy as np
import pandas as pd
from uuid import uuid4
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal
from fastapi import FastAPI, HTTPException, status, Query, Body, UploadFile
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, FiniteFloat, StrictFloat

from src.predict import predict_reading, REQUIRED_FEATURES, threshold as ml_threshold, model_version, score_readings
from src.sensor_validation import validate_telemetry
from src.compressor_rules import CompressorRuleEngine
from src.recommendation_engine import generate_recommendations
from src.event_store import event_store_instance
from src.cloud_sync import cloud_sync_instance

_rule_engines = OrderedDict()
_rule_lock = threading.Lock()

app = FastAPI(
    title="Edge-Based Compressor Monitoring & Recommendation API",
    description="Local edge processing service for Two-Stage Reciprocating Air Compressor condition monitoring.",
    version="2.1.0",
)

# ----------------------------------------------------------------------
# Pydantic Schemas
# ----------------------------------------------------------------------

# Preserved 8-feature schema for existing /predict contract
class SensorReading8(BaseModel):
    accelerometer1_rms: float = Field(..., description="Vibration Accel 1 RMS (g)")
    accelerometer2_rms: float = Field(..., description="Vibration Accel 2 RMS (g)")
    current: float = Field(..., description="Motor Current (A)")
    pressure: float = Field(..., description="Discharge Pressure (bar)")
    temperature: float = Field(..., description="Process Temperature (°C)")
    thermocouple: float = Field(..., description="Thermocouple Temp (°C)")
    voltage: float = Field(..., description="Line Voltage (V)")
    volume_flow_rate_rms: float = Field(..., description="Volume Flow Rate RMS (L/min)")


class SensorChannel(BaseModel):
    value: StrictFloat = Field(..., description="Current sensor numeric reading")
    unit: str = Field(..., description="Sensor engineering unit")


class CompressorTelemetryPayload(BaseModel):
    message_id: str = Field(..., description="Unique message GUID")
    machine_id: str = Field(default="COMPRESSOR_01", description="Industrial asset identifier")
    timestamp: str = Field(..., description="ISO-8601 acquisition timestamp")
    source: str = Field(default="WOKWI_SIMULATION", description="Data source (WOKWI_SIMULATION or SKAB_REPLAY)")
    sequence: int = Field(default=0, description="Monotonically increasing sequence number")
    sensors: Dict[str, SensorChannel] = Field(..., description="Dictionary of 5 sensor channels")
    stream_id: Optional[str] = None
    run_command: Optional[Literal["RUN", "STOP"]] = None
    raw_eight_features: Optional[Dict[str, float]] = Field(default=None, description="Optional 8-feature payload if SKAB replay")


class AcknowledgeRequest(BaseModel):
    acknowledged_by: str = Field(default="Shift_Operator", description="Operator identifier acknowledging the alert")


# ----------------------------------------------------------------------
# System Information & Health Endpoints
# ----------------------------------------------------------------------

@app.get("/", tags=["Info"])
def home():
    return {
        "service": "Edge-Based Two-Stage Industrial Reciprocating Air Compressor Monitoring System",
        "asset_monitored": "Two-Stage Industrial Reciprocating Air Compressor",
        "status": "online",
        "model_version": model_version,
        "operating_mode": "Offline Local-First Edge Intelligence",
    }


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "model_loaded": True,
        "model_version": model_version,
        "features_monitored": 5,
        "sensors": ["temperature", "vibration", "pressure", "current", "speed"],
        "database_connected": True
    }


@app.get("/machine/status", tags=["Status"])
def machine_status(machine_id: str = "COMPRESSOR_01"):
    recent_events = event_store_instance.get_recent_events(limit=1, machine_id=machine_id)
    active_alerts = event_store_instance.get_alerts(active_only=True, limit=10, machine_id=machine_id)

    latest_event = recent_events[0] if recent_events else {}
    overall_status = latest_event.get("rule_status", "NO_DATA")

    return {
        "machine_id": machine_id,
        "asset_name": "Two-Stage Industrial Reciprocating Air Compressor",
        "overall_status": overall_status,
        "active_alerts_count": len(active_alerts),
        "latest_telemetry_timestamp": latest_event.get("timestamp"),
        "latest_readings": {
            "temperature": latest_event.get("temperature"),
            "vibration": latest_event.get("vibration"),
            "pressure": latest_event.get("pressure"),
            "current": latest_event.get("current"),
            "speed": latest_event.get("speed"),
        },
        "ml_inference_status": latest_event.get("ml_status", "NOT_EVALUATED"),
        "active_alerts": active_alerts
    }


# ----------------------------------------------------------------------
# ML Model Prediction Endpoint (Preserves Existing 8-Feature Contract)
# ----------------------------------------------------------------------

@app.post("/predict", tags=["Inference"])
def predict(data: SensorReading8):
    reading_dict = {
        "Accelerometer1RMS": data.accelerometer1_rms,
        "Accelerometer2RMS": data.accelerometer2_rms,
        "Current": data.current,
        "Pressure": data.pressure,
        "Temperature": data.temperature,
        "Thermocouple": data.thermocouple,
        "Voltage": data.voltage,
        "Volume Flow RateRMS": data.volume_flow_rate_rms,
    }

    try:
        t0 = time.perf_counter()
        result = predict_reading(reading_dict)
        latency = (time.perf_counter() - t0) * 1000
        result["latency_ms"] = round(latency, 2)
        return result
    except (ValueError, TypeError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err


# ----------------------------------------------------------------------
# Unified 5-Sensor Compressor Telemetry Analysis & Decision Endpoint
# ----------------------------------------------------------------------

@app.post("/compressor/analyse", tags=["Compressor Analysis"])
def analyse_compressor_telemetry(payload: CompressorTelemetryPayload):
    start_time = time.perf_counter()
    raw_dict = payload.model_dump()

    # 1. Sensor Validation Layer
    is_valid, validation_errors, sanitized_data = validate_telemetry(raw_dict)
    
    if not is_valid and any(error.startswith("Duplicate message_id detected:") for error in validation_errors):
        return {
            "message_id": payload.message_id,
            "machine_id": payload.machine_id,
            "overall_status": "SENSOR_FAULT",
            "validation_errors": validation_errors,
            "worker_recommendations": [],
        }
    if not is_valid:
        fault_id = f"ALT-VAL-{uuid4().hex}"
        event_store_instance.log_alert({
            "alert_id": fault_id, "machine_id": payload.machine_id, "sensor": "telemetry",
            "alert_type": "TELEMETRY_VALIDATION_ERROR", "severity": "SENSOR_FAULT",
            "possible_causes": validation_errors,
            "recommended_worker_actions": ["Check the source clock and sensor payload."],
        })
        # Invalid data is never classified as normal
        event_store_instance.log_event(
            machine_id=payload.machine_id,
            source=payload.source,
            sensors=raw_dict.get("sensors", {}),
            rule_status="SENSOR_FAULT",
            ml_status="UNAVAILABLE",
            latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
            raw_payload=raw_dict
        )
        return {
            "machine_id": payload.machine_id,
            "overall_status": "SENSOR_FAULT",
            "message": "Telemetry rejected by sensor validation layer.",
            "validation_errors": validation_errors,
            "worker_recommendations": [{
                "alert_id": fault_id,
                "severity": "SENSOR_FAULT",
                "alert_type": "TELEMETRY_VALIDATION_ERROR",
                "possible_causes": ["Corrupted MQTT packet", "Sensor out-of-range", "Incorrect unit format"],
                "recommended_worker_actions": ["Check sensor transmitter wiring", "Inspect network gateway"],
                "maintenance_followup": "Verify sensor signal conditioning module."
            }]
        }

    # 2. Five-Sensor Compressor Rule Engine
    sensors_dict = sanitized_data["sensors"]
    with _rule_lock:
        key = (payload.machine_id, payload.source, payload.stream_id)
        if key not in _rule_engines:
            _rule_engines[key] = CompressorRuleEngine()
            if len(_rule_engines) > 128:
                _rule_engines.popitem(last=False)
        _rule_engines.move_to_end(key)
        rule_results = _rule_engines[key].evaluate_telemetry(sensors_dict, run_command=payload.run_command)
    rule_status = rule_results["machine_status"]

    # 3. Actionable Worker Recommendation Engine
    recommendations = generate_recommendations(
        rule_results,
        machine_id=payload.machine_id,
        timestamp=sanitized_data.get("timestamp")
    )

    # 4. Optional ML Inference (Strict Feature Contract)
    ml_result = {}
    if payload.raw_eight_features:
        # Genuine 8-feature payload provided (e.g. SKAB Replay)
        try:
            ml_result = predict_reading(payload.raw_eight_features)
        except (ValueError, TypeError) as error:
            ml_result = {"status": "UNAVAILABLE", "ml_available": False, "message": str(error)}
    else:
        # Check if the 8 features are supplied inside sensors
        ml_result = predict_reading(sensors_dict)

    ml_status = ml_result.get("status", "UNAVAILABLE")
    ml_prob = ml_result.get("anomaly_probability")

    # 5. Persistent Local Event & Alert Logging
    local_action = "WORKER_ALERT" if recommendations else "MONITOR"
    audit_payload = {
        **raw_dict,
        "edge_decision": {"local_action": local_action, "model_version": ml_result.get("model_version")},
    }
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    event_store_instance.log_event(
        machine_id=payload.machine_id,
        source=payload.source,
        sensors=sensors_dict,
        rule_status=rule_status,
        ml_status=ml_status,
        ml_probability=ml_prob,
        latency_ms=latency_ms,
        raw_payload=audit_payload,
        timestamp=sanitized_data.get("timestamp")
    )

    for rec in recommendations:
        event_store_instance.log_alert(rec)

    # 6. Combined Response
    response_data = {
        "message_id": payload.message_id,
        "machine_id": payload.machine_id,
        "timestamp": sanitized_data.get("timestamp"),
        "source": payload.source,
        "overall_status": rule_status,
        "run_command": payload.run_command,
        "local_action": local_action,
        "sensor_evaluations": rule_results["sensor_evaluations"],
        "ml_inference": ml_result,
        "active_alerts_count": len(rule_results["alerts"]),
        "worker_recommendations": recommendations,
        "timing": {
            "edge_processing_latency_ms": latency_ms,
            "boundary": "API analysis before SQLite writes"
        }
    }

    # 7. Occasional Cloud Synchronization (ThingsBoard Hybrid Sync)
    cloud_sync_instance.record_decision(raw_dict, response_data)

    return response_data


# ----------------------------------------------------------------------
# Alerts & Event Management Endpoints
# ----------------------------------------------------------------------

@app.get("/alerts", tags=["Alerts"])
def get_alerts(active_only: bool = True, limit: int = 50):
    return {
        "active_only": active_only,
        "count": len(event_store_instance.get_alerts(active_only=active_only, limit=limit)),
        "alerts": event_store_instance.get_alerts(active_only=active_only, limit=limit)
    }


@app.post("/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def acknowledge_alert(alert_id: str, payload: AcknowledgeRequest):
    success = event_store_instance.acknowledge_alert(
        alert_id=alert_id,
        acknowledged_by=payload.acknowledged_by
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{alert_id}' not found."
        )
    return {
        "alert_id": alert_id,
        "acknowledged": True,
        "acknowledged_by": payload.acknowledged_by,
        "message": "Alert successfully acknowledged."
    }


@app.get("/events", tags=["Events"])
def get_events(limit: int = 50):
    events = event_store_instance.get_recent_events(limit=limit)
    return {
        "limit": limit,
        "count": len(events),
        "events": events
    }


@app.get("/events/export", response_class=PlainTextResponse, tags=["Events"])
def export_events():
    return event_store_instance.export_events_csv()


# ----------------------------------------------------------------------
# Cloud Synchronization Endpoints (ThingsBoard Cloud)
# ----------------------------------------------------------------------

class CloudTokenRequest(BaseModel):
    token: str = Field(..., max_length=512, description="ThingsBoard Device Access Token")
    region: Literal["eu", "us"] = "eu"


@app.get("/cloud/status", tags=["Cloud Synchronization"])
def get_cloud_status():
    """Get current ThingsBoard cloud synchronization status and metrics."""
    return cloud_sync_instance.get_status()


@app.post("/cloud/sync", tags=["Cloud Synchronization"])
def trigger_cloud_sync():
    """Force immediate manual sync to ThingsBoard Cloud."""
    return cloud_sync_instance.sync_now()


@app.post("/cloud/token", tags=["Cloud Synchronization"])
def update_cloud_token(payload: CloudTokenRequest):
    """Update ThingsBoard device access token."""
    cloud_sync_instance.set_token(payload.token, payload.region)
    return {
        "success": True,
        "message": "ThingsBoard settings updated for this API session.",
        "cloud_status": cloud_sync_instance.get_status()
    }


# ===========================================================================
# BROWSER-BASED SENSOR SIMULATOR CONTROL PANEL
# Opens at http://127.0.0.1:8000/simulator
# Replaces tkinter GUI — works in any browser, no extra install
# ===========================================================================

SIMULATOR_STATE = {
    "temperature": 78.5,
    "vibration": 0.180,
    "pressure": 8.0,
    "current": 18.0,
    "speed": 1450.0,
    "streaming": False,
    "noise": True,
    "sequence": 0,
}
_sim_thread = None


class SimulatorValues(BaseModel):
    feed_id: Optional[str] = Field(default=None, max_length=64)
    temperature: FiniteFloat = 78.5
    vibration: FiniteFloat = 0.180
    pressure: FiniteFloat = 8.0
    current: FiniteFloat = 18.0
    speed: FiniteFloat = 1450.0
    run_command: Optional[Literal["RUN", "STOP"]] = None
    noise: bool = False
    stream_id: Optional[str] = None


WEB_ROOT = Path(__file__).resolve().parent / "web"
app.mount("/demo-assets", StaticFiles(directory=WEB_ROOT), name="demo-assets")


@app.get("/simulator", response_class=HTMLResponse, tags=["Simulator"])
def simulator_panel():
    return FileResponse(WEB_ROOT / "simulator.html")


@app.get("/live-dashboard", response_class=HTMLResponse, tags=["Simulator"])
def live_dashboard():
    return FileResponse(WEB_ROOT / "live-dashboard.html")


@app.get("/cloud-setup", response_class=HTMLResponse, tags=["Cloud Synchronization"])
def cloud_setup_page():
    return FileResponse(WEB_ROOT / "cloud.html")


@app.get("/model-demo", response_class=HTMLResponse, tags=["Demonstration"])
def model_demo_page():
    return FileResponse(WEB_ROOT / "model.html")


_latest_simulator_decision = None
_simulator_feeds = OrderedDict()
_latest_simulator_lock = threading.Lock()


@app.get("/simulator/latest", tags=["Simulator"])
def simulator_latest(feed_id: Optional[str] = None):
    with _latest_simulator_lock:
        if feed_id is not None:
            return _simulator_feeds.get(feed_id)
        return _latest_simulator_decision


@app.get("/demo/model/sample/{case}", tags=["Demonstration"])
def model_sample(case: Literal["normal", "anomaly"]):
    row_index = {"normal": 0, "anomaly": 600}[case]
    path = WEB_ROOT.parents[1] / "data/raw/SKAB/data/other/11.csv"
    frame = pd.read_csv(path, sep=";")
    score = float(score_readings(frame)[row_index])
    return {"status": "ANOMALY" if score >= ml_threshold else "NORMAL",
            "anomaly_probability": round(score, 4), "threshold": ml_threshold,
            "model_version": model_version,
            "label": int(frame["anomaly"].iloc[row_index]), "row": row_index}


@app.post("/demo/model/csv", tags=["Demonstration"])
def model_csv(file: UploadFile):
    decision_threshold = ml_threshold
    data = file.file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "CSV must be 2 MB or smaller")
    try:
        row_limit = 20_000
        frame = pd.read_csv(BytesIO(data), sep=None, engine="python", nrows=row_limit + 1)
        frame.columns = frame.columns.str.strip()
        values = frame[REQUIRED_FEATURES].apply(pd.to_numeric, errors="raise")
        if not 1 <= len(values) <= row_limit or not np.isfinite(values.to_numpy()).all():
            raise ValueError(f"Use 1 to {row_limit:,} rows with finite numeric features")
        labels = None
        if "anomaly" in frame:
            labels = pd.to_numeric(frame["anomaly"], errors="raise")
            if not labels.isin([0, 1]).all():
                raise ValueError("The anomaly column must contain only 0 or 1")
        scores = score_readings(values)
    except (ValueError, KeyError, pd.errors.ParserError) as error:
        raise HTTPException(422, f"Invalid CSV: {error}") from error
    flags = scores >= decision_threshold
    counts = None
    if labels is not None:
        actual = labels.to_numpy() == 1
        counts = dict(tp=int((flags & actual).sum()), tn=int((~flags & ~actual).sum()),
                      fp=int((flags & ~actual).sum()), fn=int((~flags & actual).sum()))
    return {"rows": len(values), "anomalies": int(flags.sum()), "threshold": decision_threshold, "profile": "unified", "model_version": model_version, "counts": counts,
            "preview": [{"row": i + 1, "score": round(float(scores[i]), 4), "anomaly": bool(flags[i])}
                        for i in range(min(len(values), 10))]}


# Persistent MQTT Client for Web Simulator
MQTT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/mqtt_config.json"
_sim_mqtt_client = None
_sim_mqtt_lock = threading.Lock()

def get_sim_mqtt_client():
    global _sim_mqtt_client
    with _sim_mqtt_lock:
        if _sim_mqtt_client is None:
            try:
                import paho.mqtt.client as mqtt
                client = mqtt.Client(
                    client_id=f"FastAPI_WebSim_{int(time.time())}",
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    protocol=mqtt.MQTTv311
                )
                cfg = json.loads(MQTT_CONFIG_PATH.read_text(encoding="utf-8"))
                broker = cfg["local_broker"]
                from threading import Event

                ready = Event()
                client.on_connect = lambda *_: ready.set()
                client.connect(broker["host"], broker["port"], broker["keepalive"])
                client.loop_start()
                if not ready.wait(timeout=1) or not client.is_connected():
                    client.disconnect()
                    client.loop_stop()
                    return None
                _sim_mqtt_client = client
            except Exception as e:
                print(f"[MQTT ERROR] {e}")
        return _sim_mqtt_client


def simulator_packet(values: SimulatorValues):
    import random

    with _sim_mqtt_lock:
        SIMULATOR_STATE["sequence"] += 1
        seq = SIMULATOR_STATE["sequence"]

    temp = values.temperature + (random.uniform(-0.1, 0.1) if values.noise else 0)
    vib  = values.vibration + (random.uniform(-0.003, 0.003) if values.noise else 0)
    press = values.pressure + (random.uniform(-0.03, 0.03) if values.noise else 0)
    curr  = values.current + (random.uniform(-0.08, 0.08) if values.noise else 0)
    speed = values.speed + (random.uniform(-1.0, 1.0) if values.noise and values.speed != 0 else 0)

    import time as _time
    payload = {
        "message_id": uuid4().hex,
        "machine_id": "COMPRESSOR_01",
        "timestamp":  _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "source":     "WEB_SENSOR_SIMULATOR",
        "sequence":   0,
        "stream_id": values.stream_id,
        "run_command": values.run_command,
        "sensors": {
            "temperature": {"value": temp,  "unit": "°C"},
            "vibration":   {"value": vib,   "unit": "g RMS"},
            "pressure":    {"value": press, "unit": "bar"},
            "current":     {"value": curr,  "unit": "A"},
            "speed":       {"value": speed, "unit": "RPM"},
        }
    }

    return payload, seq


@app.post("/simulator/analyse", tags=["Simulator"])
def simulator_analyse(values: SimulatorValues):
    payload, _ = simulator_packet(values)
    global _latest_simulator_decision
    decision = analyse_compressor_telemetry(CompressorTelemetryPayload.model_validate(payload))
    latest = {**decision, "readings": payload["sensors"]}
    latest.setdefault("timestamp", payload["timestamp"])
    with _latest_simulator_lock:
        _latest_simulator_decision = latest
        if values.feed_id:
            _simulator_feeds[values.feed_id] = latest
            _simulator_feeds.move_to_end(values.feed_id)
            if len(_simulator_feeds) > 128:
                _simulator_feeds.popitem(last=False)
    return latest


@app.post("/simulator/publish", tags=["Simulator"])
def simulator_publish(values: SimulatorValues):
    payload, seq = simulator_packet(values)
    mqtt_client = get_sim_mqtt_client()
    if mqtt_client is None or not mqtt_client.is_connected():
        raise HTTPException(status_code=503, detail="Local MQTT broker unavailable")
    topic = "factory/compressor/sensors"
    publication = mqtt_client.publish(topic, json.dumps(payload), qos=1)
    try:
        publication.wait_for_publish(timeout=2)
        confirmed = publication.is_published()
    except RuntimeError:
        confirmed = False
    if not confirmed:
        raise HTTPException(status_code=503, detail="MQTT delivery was not acknowledged")
    return {"ok": True, "sequence": seq, "published_to": topic}
