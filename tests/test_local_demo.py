from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api import app
from src import api


NORMAL = {"temperature": 78.5, "vibration": 0.18, "pressure": 8, "current": 18, "speed": 1450, "noise": False}


def test_local_simulator_and_machine_status():
    with TestClient(app) as client:
        page = client.get("/simulator")
        assert page.status_code == 200
        assert "Sensor controls" in page.text
        assert "Latest local decision" not in page.text
        assert 'href="/live-dashboard"' in page.text
        dashboard = client.get("/live-dashboard")
        assert dashboard.status_code == 200
        assert "Latest local decision" in dashboard.text
        assert 'id="decision-latency"' in dashboard.text
        assert "Sensor controls" not in dashboard.text
        assert "/demo-assets/simulator.js" in page.text
        assert "/simulator/analyse" in client.get("/demo-assets/simulator.js").text
        ok = client.post("/simulator/analyse", json={**NORMAL, "feed_id": "test-paired-feed"})
        assert ok.status_code == 200
        assert ok.json()["overall_status"] == "NORMAL"
        assert len(ok.json()["readings"]) == 5
        assert client.get("/simulator/latest").json() == ok.json()

        fault = client.post("/simulator/analyse", json={**NORMAL, "temperature": 125})
        assert fault.json()["overall_status"] == "CRITICAL"
        assert fault.json()["worker_recommendations"]
        paired = client.get("/simulator/latest", params={"feed_id": "test-paired-feed"})
        assert paired.json()["overall_status"] == "NORMAL"
        assert client.get("/simulator/latest").json()["overall_status"] == "CRITICAL"
        assert client.get("/machine/status", params={"machine_id": uuid4().hex}).json()["overall_status"] == "NO_DATA"


def test_invalid_messages_preserve_high_water_mark():
    units = dict(temperature="°C", vibration="g RMS", pressure="bar", current="A", speed="RPM")
    machine = uuid4().hex

    def packet(seq, age=0):
        stamp = datetime.now(timezone.utc) - timedelta(seconds=age)
        return {
            "message_id": uuid4().hex,
            "machine_id": machine,
            "timestamp": stamp.isoformat(),
            "sequence": seq,
            "source": "REGRESSION_TEST",
            "sensors": {key: {"unit": unit, "value": NORMAL[key]} for key, unit in units.items()},
        }

    with TestClient(app) as client:
        def post(packet):
            return client.post("/compressor/analyse", json=packet).json()

        accepted = packet(10)
        assert post(accepted)["overall_status"] == "NORMAL"
        assert post(accepted)["overall_status"] == "SENSOR_FAULT"
        assert post(packet(8))["overall_status"] == "SENSOR_FAULT"
        assert post(packet(9))["overall_status"] == "SENSOR_FAULT"
        assert post(packet(100, age=120))["overall_status"] == "SENSOR_FAULT"
        assert post(packet(100, age=-120))["overall_status"] == "SENSOR_FAULT"
        assert post(packet(11))["overall_status"] == "NORMAL"
        invalid = packet(12)
        invalid["sensors"]["current"]["value"] = True
        assert client.post("/compressor/analyse", json=invalid).status_code == 422


def test_publish_reports_broker_unavailability(monkeypatch):
    monkeypatch.setattr(api, "get_sim_mqtt_client", lambda: None)
    with TestClient(app) as client:
        assert client.post("/simulator/publish", json=NORMAL).status_code == 503



def test_zero_speed_uses_motor_command(monkeypatch, tmp_path):
    from src.event_store import EventStore

    database = tmp_path / "events.db"
    monkeypatch.setattr(api, "event_store_instance", EventStore(database))
    monkeypatch.setattr(api.cloud_sync_instance, "record_decision", lambda *_: None)
    monkeypatch.setattr(api, "get_sim_mqtt_client", lambda: None)
    with TestClient(app) as client:
        stopped = client.post("/simulator/analyse", json={**NORMAL, "speed": 0, "run_command": "STOP"})
        stalled = client.post("/simulator/analyse", json={**NORMAL, "speed": 0, "run_command": "RUN"})
        assert stopped.status_code == stalled.status_code == 200
        assert stopped.json()["overall_status"] == "NORMAL"
        fault = stalled.json()
        assert fault["overall_status"] == "CRITICAL"
        assert fault["ml_inference"]["status"] == "UNAVAILABLE"
        alert_id = fault["worker_recommendations"][0]["alert_id"]
        acknowledged = client.post(f"/alerts/{alert_id}/acknowledge", json={"acknowledged_by": "Demo"})
        assert acknowledged.status_code == 200
        exported = client.get("/events/export")
        assert exported.status_code == 200
        assert "run_command,local_action,model_version" in exported.text
        assert "RUN,WORKER_ALERT" in exported.text
        assert "STOP,MONITOR" in exported.text

    with closing(EventStore(database).get_connection()) as connection:
        assert connection.execute("SELECT count(*) FROM telemetry_events").fetchone()[0] == 2
        assert connection.execute("SELECT acknowledged FROM alerts WHERE alert_id = ?",
                                  (alert_id,)).fetchone()[0] == 1


def test_unified_upload_uses_version_and_ignores_ground_truth_as_input():
    import pandas as pd
    from src.predict import model_version

    path = api.WEB_ROOT.parents[1] / "data/raw/SKAB/data/other/11.csv"
    frame = pd.read_csv(path, sep=";").head(20)
    with TestClient(app) as client:
        def upload(data):
            response = client.post("/demo/model/csv", files={
                "file": ("sample.csv", data.to_csv(index=False), "text/csv")
            })
            assert response.status_code == 200, response.text
            return response.json()

        labeled = upload(frame)
        unlabeled = upload(frame.drop(columns=["anomaly"]))
        assert labeled["model_version"] == unlabeled["model_version"] == model_version
        assert labeled["profile"] == "unified"
        assert labeled["preview"] == unlabeled["preview"]
        assert labeled["counts"] is not None
        assert unlabeled["counts"] is None
        assert client.get("/model-demo").status_code == 200
