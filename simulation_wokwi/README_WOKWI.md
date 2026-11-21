# Wokwi ESP32 telemetry demo

Use the local browser simulator by default. The Wokwi option needs a private gateway that can reach the development broker. The sketch points to host.wokwi.internal on port 1883. Broker startup instructions are in [START_HERE.md](../START_HERE.md).

Load diagram.json and sketch.ino into an ESP32 project with PubSubClient, DHT sensor library, and ArduinoJson. The firmware sends a five-sensor telemetry packet once per second on factory/compressor/sensors.

| Pin | Simulated measurement |
| --- | --- |
| GPIO 15 | DHT22 temperature |
| GPIO 33 | Vibration |
| GPIO 34 | Pressure |
| GPIO 35 | Current |
| GPIO 32 | Shaft speed |

The readings feed the local compressor alert rules through the optional MQTT dashboard flow. The simulation uses five sensor channels. Eight-feature machine learning evaluation is available on /model-demo using a compatible CSV.

The broker reconnect check exercises the local API and a subscriber. Running Wokwi itself requires a configured private gateway.
