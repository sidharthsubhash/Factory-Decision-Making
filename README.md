# Factory Edge — Compressor Monitoring Demo

Factory Edge simulates a two-stage industrial air compressor. During the live demo, a browser sends temperature, vibration, pressure, motor current, and speed to a local FastAPI server. The server applies operating rules, records decisions in SQLite, and shows the latest readings and operator advisories on a dashboard. A separate page evaluates saved sensor recordings with a trained anomaly model.

## Run the demo on Windows

You need Python 3.12 with the Windows Python Launcher (`py`), a web browser, and internet access for the first dependency install. Extract the project ZIP or clone the repository before running it.

1. In the folder containing this README, double-click **Start_Demo.cmd**. It creates a Python environment in `.venv312`, installs the packages in `requirements.txt`, and starts the local server on port 8000. Keep that window open.
2. Open the [sensor simulator](http://127.0.0.1:8000/simulator). It starts streaming automatically. Wait until it says **Streaming five readings to the local API**.
3. Click **Open live dashboard** from the simulator so the dashboard follows that simulator tab. Put the two windows side by side. The core demo runs locally after installation and can be shown with Wi-Fi disconnected.

## Walk through the live decisions

Leave streaming on and allow a moment for the dashboard to update after each preset. Keep the noise option off when comparing the two zero-speed cases.

| In the simulator | On the live dashboard |
| --- | --- |
| **Normal operation** | Check the five readings and the normal decision. The starting values include 78.5 °C, 8 bar, and 1,450 RPM. |
| **High pressure and vibration** | Check the change in pressure and vibration, then read the worker alerts alongside the machine status. |
| **Critical temperature** | The temperature rises to 125 °C. Look for the critical decision and read the operator advisory. |
| **Commanded stop** | The motor command is `STOP`. The rules treat 0 RPM as expected for this command. |
| **Unexpected zero speed** | The readings match **Commanded stop**, but the motor command is `RUN`. The rules flag 0 RPM as an unexpected stop. |

The dashboard's **API analysis time** measures local server processing. Browser refresh and dashboard polling add to the time it takes to see a change. After the walkthrough, click **Download event history** and review the saved sensor values, motor commands, decisions, and actions. Use **Pause streaming** in the simulator to stop sending readings, and press **Ctrl+C** in the server window when finished.

## Evaluate a sensor recording

Open [Anomaly model](http://127.0.0.1:8000/model-demo). Click **Run normal sample** and **Run anomaly sample** to compare two included SKAB recordings. The saved model scores recorded samples using eight channels. The five live readings above go through the compressor rules.

To use your own data, select a file under **External CSV** and click **Evaluate CSV**. Upload one recording at a time with numeric readings in chronological order. Use these column names:

```csv
Accelerometer1RMS,Accelerometer2RMS,Current,Pressure,Temperature,Thermocouple,Voltage,Volume Flow RateRMS
```

Add an `anomaly` column with `0` for normal rows and `1` for anomalous rows to get accuracy, anomaly recall, false-positive rate, and confusion counts. Recall is the share of labelled anomalies the model caught. The false-positive rate is the share of labelled normal rows it flagged.

The saved model version `3.1.0-unified` reported **91.95% accuracy across nine held-out SKAB recordings**, **83.80% across the eight recordings containing anomalies**, and **99.60% on a separate synthetic file**. These scores describe those datasets. Use the per-file results and confusion counts to see where the model missed anomalies. The demo simulates telemetry and provides operator advisories. Connecting it to physical equipment would require calibrated sensors and independently commissioned controls. [Model validation report](reports/unified_anomaly_validation.json) · [SKAB dataset license](data/raw/SKAB/LICENSE)

## Inspect or verify the implementation

| Where to look | What it contains |
| --- | --- |
| [src/api.py](src/api.py) and [src/compressor_rules.py](src/compressor_rules.py) | The local API and the rules behind the live decisions. |
| [config/compressor_limits.json](config/compressor_limits.json) | Operating limits used for the simulated compressor. |
| [src/event_store.py](src/event_store.py) | SQLite event logging and history. |
| [models/train_unified.py](models/train_unified.py) | Model training and evaluation. The demo loads `models/unified_anomaly.joblib`. |
| [reports/unified_edge_verification.json](reports/unified_edge_verification.json) | Recorded evidence from the localhost decision test with non-loopback connections blocked. |

After the first successful launch, open PowerShell in the repository folder to run the test suite:

```powershell
.\.venv312\Scripts\python.exe -m pytest -q
```

[START_HERE.md](START_HERE.md) covers optional Node-RED, Mosquitto MQTT, ThingsBoard cloud summaries, and model retraining.

## If the demo does not start

- **Python is missing.** Run `py -3.12 --version` in PowerShell to check that the launcher can find Python 3.12. After installing it, reopen PowerShell and run `Start_Demo.cmd` again.
- **Dependency installation fails.** Check the error in the launcher window and confirm the machine can reach the Python package index. Run the launcher again after resolving the error.
- **Port 8000 is already in use.** Close the previous demo server and start the launcher again. If you're unsure whether the server is running, open the [health endpoint](http://127.0.0.1:8000/health).
- **The dashboard is waiting for a reading.** Resume streaming in the simulator and reopen the dashboard using **Open live dashboard** from that same tab.