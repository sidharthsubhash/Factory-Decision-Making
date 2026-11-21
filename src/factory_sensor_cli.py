"""
Factory Edge Monitoring System - Two-Stage Industrial Reciprocating Air Compressor
Headless CLI Sensor Simulator & Fault Injector

Runs completely in the terminal without a GUI. Streams standard Section 11 telemetry
over MQTT and allows keyboard-driven fault injection.
"""

import argparse
import json
import random
import time
import sys
from uuid import uuid4
import paho.mqtt.client as mqtt

DEFAULTS = {
    "temperature": {"val": 78.5, "unit": "°C"},
    "vibration":   {"val": 0.180, "unit": "g RMS"},
    "pressure":    {"val": 8.0, "unit": "bar"},
    "current":     {"val": 18.0, "unit": "A"},
    "speed":       {"val": 1450.0, "unit": "RPM"}
}

FAULTS = {
    "valve": {"pressure": 11.2, "temperature": 102.5, "vibration": 0.38, "name": "Valve Leakage / Overpressure"},
    "bearing": {"vibration": 0.58, "current": 24.5, "temperature": 94.0, "name": "Bearing Wear / Mechanical Looseness"},
    "overheat": {"temperature": 112.0, "pressure": 10.1, "name": "Intercooler Fouling / Thermal Runaway"},
    "overload": {"current": 29.5, "temperature": 98.0, "speed": 1390.0, "name": "Motor Overload / High Torque"},
    "slip": {"speed": 1310.0, "pressure": 5.8, "name": "Drive Belt Slippage"}
}

def run_cli_simulator(host="127.0.0.1", port=1883, topic="factory/compressor/sensors", fault=None, interval=5.0):
    client = mqtt.Client(
        client_id=f"Compressor_CLI_Sim_{int(time.time())}",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv311
    )
    print(f"\n[SIMULATOR] Connecting to MQTT broker at {host}:{port}...", flush=True)
    try:
        client.connect(host, port, 60)
        client.loop_start()
        print(f"[SIMULATOR] Connected! Topic: '{topic}'", flush=True)
    except Exception as e:
        print(f"[SIMULATOR ERROR] Could not connect to MQTT: {e}", flush=True)
        return

    values = {k: DEFAULTS[k]["val"] for k in DEFAULTS}
    if fault and fault in FAULTS:
        print(f"\n>>> INJECTING FAULT MODE: {FAULTS[fault]['name']} <<<", flush=True)
        values.update({k: v for k, v in FAULTS[fault].items() if k != "name"})
    else:
        print("\n>>> RUNNING IN NOMINAL FACTORY STATE <<<", flush=True)

    stream_id = uuid4().hex
    seq = 0
    print("\nStarting live sensor broadcast (Press Ctrl+C to stop)...", flush=True)
    print("-" * 75, flush=True)
    print(f"{'Seq':<6} | {'Temp (°C)':<10} | {'Vib (g RMS)':<12} | {'Press (bar)':<12} | {'Current (A)':<12} | {'Speed (RPM)':<10}", flush=True)
    print("-" * 75, flush=True)

    try:
        while True:
            seq += 1
            t_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # Natural drift
            t_val = round(values["temperature"] + random.uniform(-0.15, 0.15), 1)
            v_val = round(max(0.01, values["vibration"] + random.uniform(-0.003, 0.003)), 3)
            p_val = round(max(0.0, values["pressure"] + random.uniform(-0.04, 0.04)), 2)
            c_val = round(max(0.0, values["current"] + random.uniform(-0.1, 0.1)), 1)
            s_val = round(values["speed"] + random.uniform(-1.5, 1.5), 0)

            payload = {
                "message_id": f"{stream_id}-{seq}",
                "machine_id": "COMPRESSOR_01",
                "timestamp": t_iso,
                "source": "EDGE_SENSOR_SIMULATOR",
                "sequence": seq,
                "stream_id": stream_id,
                "sensors": {
                    "temperature": {"value": t_val, "unit": "°C"},
                    "vibration": {"value": v_val, "unit": "g RMS"},
                    "pressure": {"value": p_val, "unit": "bar"},
                    "current": {"value": c_val, "unit": "A"},
                    "speed": {"value": s_val, "unit": "RPM"}
                }
            }

            client.publish(topic, json.dumps(payload), qos=1)
            print(f"{seq:<6} | {t_val:<10.1f} | {v_val:<12.3f} | {p_val:<12.2f} | {c_val:<12.1f} | {s_val:<10.0f}", flush=True)
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[SIMULATOR] Stopped by user.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Two-Stage Compressor Sensor CLI Simulator")
    parser.add_argument("--host", default="127.0.0.1", help="MQTT host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT port")
    parser.add_argument("--fault", choices=["valve", "bearing", "overheat", "overload", "slip"], default=None,
                        help="Inject a specific compressor failure mode")
    parser.add_argument("--interval", type=float, default=5.0, help="Broadcast interval in seconds (default: 5s)")
    args = parser.parse_args()

    run_cli_simulator(host=args.host, port=args.port, fault=args.fault, interval=args.interval)

