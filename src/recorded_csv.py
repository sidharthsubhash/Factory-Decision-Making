"""Sensor features for independently scored, chronological CSV recordings."""

import numpy as np
import pandas as pd


def recording_features(values: pd.DataFrame, *, reference_features: bool = False) -> pd.DataFrame:
    """Use only the current row and earlier rows in the same recording."""
    features = [values]
    baseline = values.expanding().mean()
    first = values.iloc[:1].to_numpy()
    features.append((values - first).add_suffix("_change_from_first"))
    features.append((values - baseline).add_suffix("_change_from_running_mean"))
    for window in (8, 32, 128):
        rolling = values.rolling(window, min_periods=1)
        mean = rolling.mean()
        features.extend([
            mean.add_suffix(f"_mean_{window}"),
            rolling.std(ddof=0).add_suffix(f"_std_{window}"),
            (values - mean).add_suffix(f"_residual_{window}"),
            mean.diff(window).fillna(0).add_suffix(f"_trend_{window}"),
        ])
    if reference_features:
        # Freeze the reference once 120 readings are available.
        reference = values.iloc[:120].expanding()
        reference_mean = reference.mean().reindex(values.index).ffill()
        reference_std = reference.std(ddof=0).reindex(values.index).ffill()
        scale = reference_std.clip(lower=reference_mean.abs() * 0.0001 + 0.000001)
        for window in (16, 64, 256):
            rolling = values.rolling(window, min_periods=1)
            shift = (rolling.mean() - reference_mean) / scale
            spread = rolling.std(ddof=0) / scale
            features.extend([
                shift.clip(-100, 100).add_suffix(f"_reference_shift_{window}"),
                np.log1p(spread).add_suffix(f"_reference_spread_{window}"),
            ])
    return pd.concat(features, axis=1)



def batch_features(values: pd.DataFrame) -> pd.DataFrame:
    """Summarize local behavior relative to the complete uploaded recording."""
    features = [recording_features(values)]
    for window in (24, 96):
        rolling = values.rolling(window, min_periods=1, center=True)
        for name, stat in (("level", rolling.mean()), ("spread", rolling.std(ddof=0))):
            median = stat.median()
            scale = (stat.quantile(0.9) - stat.quantile(0.1)).clip(
                lower=median.abs() * 0.0001 + 0.000001
            )
            features.extend([
                stat.add_suffix(f"_centered_{name}_{window}"),
                ((stat - median) / scale).clip(-100, 100).add_suffix(f"_relative_{name}_{window}"),
            ])
    return pd.concat(features, axis=1)


def inference_features(values: pd.DataFrame, *, independent: bool = False) -> pd.DataFrame:
    """Use missing context for independent readings with no recording history."""
    if independent or len(values) == 1:
        schema = batch_features(values.iloc[:1]).columns
        return values.reindex(columns=schema)
    return batch_features(values)
