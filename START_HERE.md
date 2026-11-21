# Factory Edge two-screen demonstration

The simulator page controls the inputs. The live dashboard shows received readings, local decisions, worker alerts, and API analysis time. Node-RED is optional. The two programs communicate using localhost HTTP. Wokwi, MQTT and cloud services are not required.

## Start on Windows

1. Extract this ZIP to a new folder. Stop previous servers using ports 8000 and 1880 if you intend to use both supplied launchers.
2. Double-click **Start_Demo.cmd**. Python 3.12 is required. The launcher installs Python dependencies on the first run.
3. For the optional second screen, double-click **Start_Node_RED.cmd**. Node.js LTS is required. The first run installs Node-RED and FlowFuse Dashboard 2.0 from npm.
4. Open the **simulator controls** at <http://127.0.0.1:8000/simulator> and the **live dashboard** at <http://127.0.0.1:8000/live-dashboard>. Keep both server windows open.

### Use an existing Node-RED installation instead

Keep your existing Node-RED server running. In its editor, choose Menu → Import, import `node_red/browser-live-flow.json`, and click Deploy. Use the new dashboard URL above. This is a separate page from the old MQTT-driven dashboard. If the editor flags unknown `ui-*` nodes, install **@flowfuse/node-red-dashboard** from Manage Palette.

## Demonstration

- Start on Normal operation. Enter a numeric reading or choose High pressure and vibration, then Critical temperature. Watch the last received readings, decision, API analysis time, and worker recommendations on the live dashboard or in Node-RED.
- The dashboard shows the most recent simulator decision and labels it last recorded after the stream pauses. Use Download event history on the live dashboard to export logged readings and statuses.
- Use the simulator’s Anomaly model link to open <http://127.0.0.1:8000/model-demo>. It has the saved model, two recorded SKAB examples, and CSV upload. Labelled CSVs produce accuracy, recall, false-positive rate and confusion counts. Live worker decisions use the five-sensor rules. The saved model requires eight features.
- The original MQTT flows and Wokwi assets are included for reference. Use `browser-live-flow.json` for this demo.

## Optional ThingsBoard Cloud summaries

1. Start the API, open the simulator and leave it running.
2. Open <http://127.0.0.1:8000/cloud-setup>. Choose the region shown in your ThingsBoard console URL. Paste your device access token and select **Enable sync**.
3. Select **Send latest reading now**. A **SYNCED** status means the service accepted the HTTPS request. In ThingsBoard, open your device and check **Latest telemetry**.
4. Use temperature, vibration, pressure, current, speed, machine_status, active_alerts_count, latest_alert and edge_latency_ms as keys for cloud widgets.

The API sends the latest summary every 30 seconds when new data is available. A new warning or critical state may trigger an immediate update. After a connection failure, the next scheduled attempt can send the most recent summary. SQLite stores the local event history throughout. Cloud sync is optional and does not replay every missed sample. The token is held in memory and must be entered again after API restart. For scripted setup, set THINGSBOARD_DEVICE_TOKEN and THINGSBOARD_REGION in your local environment before starting the API.

## Evaluate a CSV

Open /model-demo and upload one chronological recording with the eight required sensor columns. The same model evaluates recorded and synthetic files. Include an anomaly column containing 0 or 1 to see accuracy, recall, false-positive rate and the confusion counts.

To retrain from the project directory, run `.venv312\Scripts\python.exe -m models.train_unified`. Add `--external PATH` to score a labeled external CSV after training. The external file is evaluated after model and threshold selection. Use --candidate to save a separate result before replacing the active model. See `reports/unified_anomaly_validation.json` for data splits and per-file metrics.

## Demonstrate a normal stop and an unexpected stop

In the simulator, use **Commanded stop** and **Unexpected zero speed**. Both presets show zero RPM. The local rule engine uses the motor command set by each preset to determine whether zero RPM is expected. Other sensor alerts still apply. The eight-sensor anomaly estimator has no RPM or motor command input.

The browser simulator, local API and live dashboard are the main demonstration. Decisions and acknowledgements are stored locally in SQLite. The starter controls simulate telemetry and show operator advisories.

## Review evidence

| Requirement | Demonstration |
| --- | --- |
| Five live sensor inputs | Stream temperature, vibration, pressure, current, and RPM from /simulator. |
| Instant local decision and action | Send the Critical temperature or Unexpected zero speed preset. FastAPI decides locally and writes a worker alert to SQLite. |
| Dashboard and response time | /live-dashboard shows the received values, API status, worker recommendations, timestamp, and analysis time. |
| Alert and decision history | Use Download event history to see decisions, the motor command, and the local action. The local API also supports alert acknowledgement. |
| Operation without cloud | The localhost HTTP test blocked non-loopback sockets and verified 120 decisions. See `reports/unified_edge_verification.json`. |

For the optional MQTT path, run **Start_Local_Broker.cmd** with Mosquitto installed. The demo broker binds to loopback. Run `.venv312\Scripts\python.exe -m verify_local_mqtt` to reproduce the outage drill using a separate broker and a temporary event database. The drill checks QoS 1 delivery before and after restart, HTTP analysis during the outage, and duplicate rejection. A live LAN installation requires its own secured broker and commissioning.

Factory deployment requires calibrated telemetry, representative machine data and independent physical controls. Version 3.1.0-unified scored 91.95% on the nine-file recorded benchmark and 99.60% on EdgeSentinel_Synthetic_5000.csv. Its accuracy across the eight recorded runs containing anomalies was 83.80%. The external file informed the synthetic fault categories but its rows did not enter training or threshold selection. The model's per-file scores and misses are listed in `reports/unified_anomaly_validation.json`.
