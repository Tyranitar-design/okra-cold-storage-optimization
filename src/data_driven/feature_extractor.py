"""
SPO 特征工程。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd


SEASON_ORDER = ["spring", "summer", "autumn", "winter"]
STORAGE_ORDER = ["precool", "cold", "ca", "frozen"]


def encode_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """把结构化训练表编码为数值特征。"""
    work = df.copy()
    work["season"] = pd.Categorical(work["season"], categories=SEASON_ORDER, ordered=True)
    work["storage_type"] = pd.Categorical(work["storage_type"], categories=STORAGE_ORDER, ordered=True)

    encoded = pd.get_dummies(
        work,
        columns=["season", "storage_type"],
        prefix=["season", "stype"],
        dtype=float,
    )

    feature_columns = [
        "level",
        "lat",
        "lon",
        "production_ton",
        "is_candidate",
        "nearest_candidate_distance_km",
        "nearest_candidate_time_h",
        "ambient_temp_c",
        "humidity",
        "storage_temp_low_c",
        "storage_temp_high_c",
        "storage_temp_mid_c",
        "storage_capacity_mean_ton",
        *[col for col in encoded.columns if col.startswith("season_") or col.startswith("stype_")],
    ]

    for col in feature_columns:
        if col not in encoded.columns:
            encoded[col] = 0.0

    return encoded, feature_columns


def split_features_targets(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """拆分 X / y。"""
    encoded, feature_columns = encode_features(df)
    X = encoded[feature_columns].astype(float)
    y = df[["alpha_target", "beta_target"]].astype(float)
    return X, y, feature_columns
