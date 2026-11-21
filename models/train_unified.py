"""Train one anomaly estimator for SKAB recordings and generated scenarios."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, confusion_matrix
from threadpoolctl import threadpool_limits

from src.recorded_csv import inference_features

FEATURES = ["Accelerometer1RMS", "Accelerometer2RMS", "Current", "Pressure",
            "Temperature", "Thermocouple", "Voltage", "Volume Flow RateRMS"]
VERSION = "3.1.0-unified"

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/SKAB/data"
MODELS = ROOT / "models"
VALIDATION = {"other/5.csv", "other/10.csv", "valve1/3.csv", "valve1/8.csv",
              "valve1/13.csv", "valve2/1.csv"}
TEST = {"other/11.csv", "other/12.csv", "other/13.csv", "other/14.csv",
        "valve1/2.csv", "valve1/7.csv", "valve1/12.csv", "valve2/3.csv",
        "anomaly-free/anomaly-free.csv"}


def metrics(actual, scores, threshold):
    tn, fp, fn, tp = (int(n) for n in confusion_matrix(
        actual, scores >= threshold, labels=[0, 1]
    ).ravel())
    return {
        "accuracy": (tp + tn) / len(actual),
        "f1": 2 * tp / max(1, 2 * tp + fp + fn),
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
    }


def generated(seed):
    rng = np.random.default_rng(seed)
    normal = np.array([.24, .29, 2.88, .055, 85.65, 31.4, 239.22, 128])
    spread = [.022, .025, .13, .04, 1.4, .65, .65, 2.5]
    offsets = [
        [0] * 8, [.14, .19, -.18, -.325, 0, 2.1, 0, 4],
        [0, 0, 0, 0, 10.35, 8.1, 0, 0], [0, 0, 0, -.375, 0, 0, 0, -22],
        [.16, .18, 0, 0, 0, 0, 0, 0], [0, 0, .70, 0, 0, 0, -7.5, 0],
    ]
    for index, offset in enumerate(offsets):
        values = pd.DataFrame(normal + np.asarray(offset) * rng.uniform(.55, 1.25, (1200, 1)) + rng.uniform(-1, 1, (1200, 8)) * spread,
                              columns=FEATURES)
        yield values, np.full(len(values), int(index != 0))


def generated_recordings(seed):
    cases = list(generated(seed))
    yield from cases
    # Include transitions and different anomaly frequencies in complete uploads.
    rng = np.random.default_rng(seed + 1)
    for fault_count in (40, 160, 400):
        values = [cases[0][0].sample(n=600, random_state=seed)]
        for fault, _ in cases[1:]:
            values.append(fault.sample(n=fault_count, random_state=seed))
        joined = pd.concat(values, ignore_index=True)
        labels = np.repeat([0, 1], [len(values[0]), (len(cases) - 1) * fault_count])
        order = rng.permutation(len(joined))
        yield joined.iloc[order].reset_index(drop=True), labels[order]


def unpack(frame):
    labels = frame["anomaly"].to_numpy(dtype=int) if "anomaly" in frame else np.zeros(len(frame), dtype=int)
    return frame[FEATURES], labels


def evaluate(cases, estimator, threshold):
    parts = [(name, labels, estimator.predict_proba(inference_features(values))[:, 1])
             for name, (values, labels) in cases.items()]
    actual = np.concatenate([labels for _, labels, _ in parts])
    scores = np.concatenate([scores for _, _, scores in parts])
    return {
        "overall": {**metrics(actual, scores, threshold),
                    "average_precision": float(average_precision_score(actual, scores))},
        "per_file": {name: metrics(labels, scores, threshold) for name, labels, scores in parts},
    }


def main(external, candidate):
    recordings = {path.relative_to(DATA).as_posix(): unpack(pd.read_csv(path, sep=";"))
                  for path in sorted(DATA.glob("*/*.csv"))}
    training = {name: case for name, case in recordings.items() if name not in VALIDATION | TEST}
    train_cases = list(training.values()) + list(generated_recordings(2026))
    rng = np.random.default_rng(2026)
    train_features, train_labels = [], []
    for values, labels in train_cases:
        train_features.append(inference_features(values))
        train_labels.append(labels)
        anomalies = np.flatnonzero(labels)
        prefix = int(anomalies[0]) if len(anomalies) else len(labels)
        if prefix >= 64:
            train_features.append(inference_features(values.iloc[:prefix]))
            train_labels.append(labels[:prefix])
        sample = rng.choice(len(values), len(values) // 3, replace=False)
        train_features.append(inference_features(values.iloc[sample], independent=True))
        train_labels.append(labels[sample])
    validation = {name: recordings[name] for name in sorted(VALIDATION)}
    sets = [list(validation.values()), list(generated_recordings(2040))]
    validation_matrices = [
        (pd.concat([inference_features(values) for values, _ in cases]),
         np.concatenate([labels for _, labels in cases]))
        for cases in sets
    ]
    normal_prefixes = []
    for values, labels in validation.values():
        anomalous = np.flatnonzero(labels)
        prefix = int(anomalous[0]) if len(anomalous) else len(labels)
        if prefix >= 64:
            normal_prefixes.append(inference_features(values.iloc[:prefix]))
    normal_validation = pd.concat(normal_prefixes)
    best = None
    for leaves in (15, 31):
        model = HistGradientBoostingClassifier(max_iter=200, max_leaf_nodes=leaves,
                                               min_samples_leaf=25, random_state=42)
        model.fit(pd.concat(train_features), np.concatenate(train_labels))
        scores = [model.predict_proba(values)[:, 1] for values, _ in validation_matrices]
        normal_scores = model.predict_proba(normal_validation)[:, 1]
        for threshold in np.arange(.15, .86, .025).round(3):
            results = [metrics(labels, score, threshold)
                       for (_, labels), score in zip(validation_matrices, scores)]
            normal_fpr = float((normal_scores >= threshold).mean())
            objective = (max(normal_fpr, *(result["false_positive_rate"] for result in results)) <= .025,
                         min(result["recall"] for result in results) >= .75,
                         min(result["accuracy"] for result in results),
                         -normal_fpr)
            if best is None or objective > best[0]:
                best = (objective, model, float(threshold), results, normal_fpr)
    _, model, threshold, results, normal_fpr = best
    synthetic = {path.name: unpack(pd.read_csv(path))
                 for path in sorted((ROOT / "synthetic_tests/random_forest").glob("*.csv"))}
    bench = {name: recordings[name] for name in sorted(TEST)}
    report = dict(
        model_version=VERSION, estimator=type(model).__name__, features=FEATURES,
        threshold=threshold, training_files=list(training),
        training_sha256={name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in training}, generated_train_seed=2026,
        validation_files=list(validation), generated_validation_seed=2040,
        validation_metrics=dict(recorded=results[0], generated=results[1], normal_prefix_false_positive_rate=normal_fpr),
        recorded_benchmark=evaluate(bench, model, threshold),
        recorded_with_anomalies=evaluate({name: case for name, case in bench.items() if case[1].any()},
                                         model, threshold),
        bundled_synthetic=evaluate(synthetic, model, threshold),
    )
    if external:
        report["external"] = evaluate({external.name: unpack(pd.read_csv(external))}, model, threshold)
        report["external_note"] = "This previously evaluated file informed the categories included in the synthetic generator. Its rows were excluded from fitting and threshold selection."
        report["external_sha256"] = hashlib.sha256(external.read_bytes()).hexdigest()
    artifact_name = "unified_anomaly_candidate" if candidate else "unified_anomaly"
    with NamedTemporaryFile(dir=MODELS, suffix=".tmp", delete=False) as temporary:
        artifact = Path(temporary.name)
    try:
        joblib.dump(dict(model=model, features=FEATURES, threshold=threshold, model_version=VERSION),
                    artifact, compress=3)
        artifact.replace(MODELS / f"{artifact_name}.joblib")
    finally:
        artifact.unlink(missing_ok=True)
    report["model_sha256"] = hashlib.sha256((MODELS / f"{artifact_name}.joblib").read_bytes()).hexdigest()
    (ROOT / f"reports/{artifact_name}_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for key in ("recorded_benchmark", "recorded_with_anomalies", "bundled_synthetic", "external"):
        if key in report:
            print(key, json.dumps(report[key]["overall"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external", type=Path, help="Optional labeled evaluation CSV")
    parser.add_argument("--candidate", action="store_true", help="Save separately from the active model")
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        main(args.external, args.candidate)


