"""Exercise the local Mosquitto transport across a broker interruption."""
import json
import os
from pathlib import Path
import socket
import subprocess
from tempfile import TemporaryDirectory
from threading import Event
import time

from fastapi.testclient import TestClient
import paho.mqtt.client as mqtt

from src import api
from src.event_store import EventStore


def main():
    exe = Path(os.environ["ProgramFiles"]) / "Mosquitto/mosquitto.exe"
    root = Path(__file__).resolve().parent
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        address = probe.getsockname()
    packet = dict(temperature=78.5, vibration=.18, pressure=8, current=18, speed=1450, run_command="RUN")
    broker = None
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    ready, received = Event(), Event()
    packets = []

    def collect(_client, _userdata, message):
        packets.append(json.loads(message.payload))
        received.set()

    def start():
        process = subprocess.Popen([str(exe), "-c", str(config)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(30):
            try:
                with socket.create_connection(address, timeout=.2):
                    return process
            except OSError:
                if process.poll() is not None:
                    break
                time.sleep(.1)
        process.terminate()
        raise RuntimeError("The owned local broker did not start")

    def expect_delivery(client):
        received.clear()
        response = client.post("/simulator/publish", json=packet)
        assert response.status_code == 200, response.text
        assert received.wait(4), "QoS 1 publication did not reach subscriber"
        analysis = client.post("/compressor/analyse", json=packets[-1])
        assert analysis.status_code == 200 and analysis.json()["overall_status"] == "NORMAL"

    subscriber.on_connect = lambda client, *_: client.subscribe("factory/compressor/sensors", qos=1)
    subscriber.on_subscribe = lambda *_: ready.set()
    subscriber.on_message = collect
    temp = TemporaryDirectory()
    config = Path(temp.name) / "mosquitto.conf"
    config.write_text((root / "config/mosquitto-local.conf").read_text().replace("1883", str(address[1])),
                      encoding="ascii")
    mqtt_config = json.loads(api.MQTT_CONFIG_PATH.read_text(encoding="utf-8"))
    mqtt_config["local_broker"]["port"] = address[1]
    api_config = Path(temp.name) / "mqtt.json"
    api_config.write_text(json.dumps(mqtt_config), encoding="utf-8")
    api.MQTT_CONFIG_PATH = api_config
    original = api.event_store_instance
    api.event_store_instance = EventStore(Path(temp.name) / "events.sqlite")
    try:
        broker = start()
        subscriber.connect(*address)
        subscriber.loop_start()
        assert ready.wait(4)
        with TestClient(api.app) as client:
            expect_delivery(client)
            broker.terminate()
            broker.wait(5)
            ready.clear()
            offline = client.post("/simulator/publish", json=packet)
            assert offline.status_code == 503, offline.text
            local = client.post("/simulator/analyse", json=packet)
            assert local.status_code == 200 and local.json()["overall_status"] == "NORMAL"
            broker = start()
            assert ready.wait(7), "Subscriber did not recover"
            for _ in range(30):
                if api._sim_mqtt_client.is_connected():
                    break
                time.sleep(.2)
            expect_delivery(client)
            assert len(packets) == 2
            duplicate = client.post("/compressor/analyse", json=packets[-1])
            assert duplicate.json()["overall_status"] == "SENSOR_FAULT"
            assert len(api.event_store_instance.get_recent_events()) == 3
            assert not duplicate.json()["worker_recommendations"]
        verified = dict(broker="Mosquitto", address=f"127.0.0.1:{address[1]}", qos=1, messages_received=len(packets),
                        broker_down_publish_status=offline.status_code, local_analysis_during_outage="NORMAL",
                        reconnect_delivery=True, duplicate_rejected=True)
        (root / "reports/local_mqtt_verification.json").write_text(
            json.dumps(verified, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(verified, indent=2))
    finally:
        subscriber.disconnect()
        subscriber.loop_stop()
        if api._sim_mqtt_client:
            api._sim_mqtt_client.disconnect()
            api._sim_mqtt_client.loop_stop()
        if broker and broker.poll() is None:
            broker.terminate()
            broker.wait(5)
        api.event_store_instance = original
        temp.cleanup()


if __name__ == "__main__":
    main()


