"""Shared eight-sensor anomaly inference for CSV, replay, and API readings."""

from pathlib import Path
import json
import joblib
import pandas as pd
import numpy as np
from typing import Dict, Any

from src.recorded_csv import inference_features

ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT_DIR / "models" / "unified_anomaly.joblib"
bundle = joblib.load(MODEL_PATH)
model = bundle["model"]
REQUIRED_FEATURES = bundle["features"]
threshold = float(bundle["threshold"])
model_version = bundle["model_version"]
ANOMALY_INDEX = list(model.classes_).index(1)


def score_readings(values: pd.DataFrame) -> np.ndarray:
    """Score an ordered recording, or a single reading when history is absent."""
    values = values[REQUIRED_FEATURES]
    features = (values.reindex(columns=model.feature_names_in_)
                if len(values) == 1 else inference_features(values))
    return model.predict_proba(features)[:, ANOMALY_INDEX]


def predict_reading(sensor_reading: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform model inference ONLY when all 8 required features are present.
    If features are missing, gracefully report UNAVAILABLE without failing.
    """
    if not isinstance(sensor_reading, dict):
        raise ValueError("sensor_reading must be a dictionary")

    # Map snake_case variants to standard PascalCase names if needed
    field_alias_map = {
        "accelerometer1_rms": "Accelerometer1RMS",
        "accelerometer2_rms": "Accelerometer2RMS",
        "current": "Current",
        "pressure": "Pressure",
        "temperature": "Temperature",
        "thermocouple": "Thermocouple",
        "voltage": "Voltage",
        "volume_flow_rate_rms": "Volume Flow RateRMS"
    }

    normalized_input = {}
    for k, v in sensor_reading.items():
        standard_key = field_alias_map.get(k, k)
        normalized_input[standard_key] = v

    missing = [f for f in REQUIRED_FEATURES if f not in normalized_input or normalized_input[f] is None]

    if missing:
        return {
            "status": "UNAVAILABLE",
            "ml_available": False,
            "message": "ML INFERENCE NOT AVAILABLE – REQUIRED FEATURES MISSING",
            "missing_features": missing,
            "provided_features": list(normalized_input.keys()),
            "anomaly_probability": None,
            "threshold": round(threshold, 4),
            "model_version": model_version
        }

    try:
        row = pd.DataFrame(
            [[float(normalized_input[f]) for f in REQUIRED_FEATURES]],
            columns=REQUIRED_FEATURES,
        )
    except (TypeError, ValueError) as err:
        raise ValueError(f"All 8 sensor feature values must be numeric: {err}") from err

    if not np.isfinite(row.to_numpy()).all():
        raise ValueError("Sensor reading contains non-finite values.")

    anomaly_probability = float(score_readings(row)[0])
    is_anomaly = anomaly_probability >= threshold

    return {
        "status": "ANOMALY" if is_anomaly else "NORMAL",
        "ml_available": True,
        "message": "Inference completed successfully using the eight-sensor model",
        "anomaly_probability": round(anomaly_probability, 4),
        "threshold": round(threshold, 4),
        "model_version": model_version,
        "top_contributor": "N/A",
        "contributing_features": [],
    }


if __name__ == "__main__":
    # Test 1: Incomplete 5-sensor compressor reading
    five_sensor_sample = {
        "temperature": 75.0,
        "vibration": 0.22,
        "pressure": 7.2,
        "current": 18.0,
        "speed": 1450.0
    }
    print("5-Sensor Test:")
    print(json.dumps(predict_reading(five_sensor_sample), indent=2))

    # Test 2: Complete 8-feature SKAB reading
    eight_feature_sample = {
        "Accelerometer1RMS": 0.15,
        "Accelerometer2RMS": 0.20,
        "Current": 2.0,
        "Pressure": 0.07,
        "Temperature": 88.0,
        "Thermocouple": 26.0,
        "Voltage": 230.0,
        "Volume Flow RateRMS": 105.0,
    }
    print("\n8-Feature SKAB Test:")
    print(json.dumps(predict_reading(eight_feature_sample), indent=2))
