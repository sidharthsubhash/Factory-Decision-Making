# Factory Decision Making

Factory Edge is a local prototype for monitoring a simulated two-stage industrial air compressor. It processes five live sensor readings, displays advisory decisions and timing, and records events in SQLite. One trained model evaluates compatible eight-channel CSV recordings.

## Run on Windows

1. Install Python 3.12 and run `Start_Demo.cmd` from the repository root. The first run installs the pinned Python dependencies.
2. Open the [sensor simulator](http://127.0.0.1:8000/simulator) and use **Open live dashboard** to follow that tab in a separate window.
3. Try **Critical temperature**, **Commanded stop**, and **Unexpected zero speed**. Download the event history from the dashboard.
4. Open [Anomaly model](http://127.0.0.1:8000/model-demo) to evaluate a compatible CSV. The bundled SKAB recordings and generated examples can be used as inputs.

See [START_HERE.md](START_HERE.md) for optional Node-RED, local MQTT, and cloud summary setup. The browser simulator and live dashboard use localhost after dependencies have been installed.

## Results and verification

- The active model is `models/unified_anomaly.joblib`. Retrain with `python -m models.train_unified`. The [validation report](reports/unified_anomaly_validation.json) records the train and test splits and per-file metrics.
- Run `python -m pytest -q` after installing `requirements.txt`.
- With Mosquitto installed, run `python -m verify_local_mqtt` for the optional broker interruption and recovery test.
- The live simulator produces alerts and operator advisories. CSV anomaly scores describe the recordings used in evaluation. Physical controls require independent commissioning.

The bundled SKAB data includes its [upstream notice and license](data/raw/SKAB/LICENSE).
