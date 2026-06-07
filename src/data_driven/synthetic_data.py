"""
基于真实节点数据与文献先验生成损耗参数训练样本。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


SEASON_PROFILES = {
    "spring": {"temp_shift": -2.0, "humidity_shift": 0.04, "risk_shift": -0.02},
    "summer": {"temp_shift": 4.5, "humidity_shift": 0.10, "risk_shift": 0.06},
    "autumn": {"temp_shift": 0.5, "humidity_shift": 0.00, "risk_shift": 0.00},
    "winter": {"temp_shift": -5.0, "humidity_shift": -0.06, "risk_shift": -0.03},
}


@dataclass
class SyntheticDatasetBundle:
    """生成的数据集与元信息。"""

    dataframe: pd.DataFrame
    feature_columns: List[str]
    target_columns: List[str]


def _nearest_candidate_distance(config: Any, node_id: str) -> float:
    candidates = list(config.candidates["node_id"])
    return min(config.get_dist(node_id, j) for j in candidates if j != node_id or len(candidates) == 1)


def _season_seed(season: str, node_id: str, storage_type: str, sample_idx: int) -> int:
    payload = f"{season}|{node_id}|{storage_type}|{sample_idx}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:16], 16) % (2**32)


def generate_synthetic_loss_dataset(
    config: Any,
    *,
    seasons: Optional[List[str]] = None,
    samples_per_combination: int = 6,
    random_state: int = 42,
) -> SyntheticDatasetBundle:
    """
    生成用于学习 α/β 的合成样本。

    每个样本对应“节点-季节-冷库类型”的组合，目标是学习
    文献先验参数在不同场景下的修正值。
    """
    if seasons is None:
        seasons = ["spring", "summer", "autumn", "winter"]

    rng = np.random.default_rng(random_state)
    pp = config.get_preservation_params()
    rows: List[Dict[str, float]] = []

    base_alpha = float(pp["loss_alpha_1"])
    base_beta = float(pp["loss_beta_1"])

    for _, node in config.nodes.iterrows():
        node_id = node["node_id"]
        level = float(node["level"])
        production = float(node["okra_production_ton"])
        lat = float(node["lat"])
        lon = float(node["lon"])
        candidate_flag = 1.0 if bool(node["is_candidate"]) else 0.0
        nearest_dist = _nearest_candidate_distance(config, node_id)
        nearest_time = nearest_dist / 40.0

        for season in seasons:
            season_profile = SEASON_PROFILES.get(season, SEASON_PROFILES["autumn"])
            for storage_type, storage_cfg in config.params["cold_storage_types"].items():
                storage_temp_low, storage_temp_high = storage_cfg["temp_range"]
                storage_temp_mid = (float(storage_temp_low) + float(storage_temp_high)) / 2.0
                storage_capacity_mean = float(np.mean(storage_cfg["capacity_levels"]))

                for sample_idx in range(samples_per_combination):
                    local_rng = np.random.default_rng(_season_seed(season, node_id, storage_type, sample_idx))
                    ambient_temp = float(35.0 + season_profile["temp_shift"] + local_rng.normal(0, 1.2))
                    humidity = float(0.68 + season_profile["humidity_shift"] + local_rng.normal(0, 0.04))
                    humidity = float(np.clip(humidity, 0.25, 0.98))

                    distance_factor = min(nearest_dist / 100.0, 1.8)
                    time_factor = min(nearest_time / 2.0, 1.5)
                    production_factor = min(production / 100.0, 1.0)
                    level_factor = (level - 1.0) / 2.0
                    temp_gap = max(ambient_temp - storage_temp_mid, 0.0)
                    season_risk = season_profile["risk_shift"]

                    alpha_noise = local_rng.normal(0, 0.03)
                    beta_noise = local_rng.normal(0, 0.02)

                    alpha = base_alpha * (
                        1.0
                        + 0.10 * distance_factor
                        + 0.05 * time_factor
                        + 0.04 * level_factor
                        + 0.03 * production_factor
                        + 0.015 * temp_gap / 10.0
                        + season_risk
                        + alpha_noise
                    )
                    beta = base_beta * (
                        1.0
                        + 0.12 * distance_factor
                        + 0.08 * humidity
                        + 0.06 * time_factor
                        + 0.025 * (storage_capacity_mean / 100.0)
                        + beta_noise
                    )

                    alpha = float(np.clip(alpha, 0.05, 2.0))
                    beta = float(np.clip(beta, 0.01, 1.0))

                    rows.append(
                        {
                            "node_id": node_id,
                            "season": season,
                            "storage_type": storage_type,
                            "level": level,
                            "lat": lat,
                            "lon": lon,
                            "production_ton": production,
                            "is_candidate": candidate_flag,
                            "nearest_candidate_distance_km": nearest_dist,
                            "nearest_candidate_time_h": nearest_time,
                            "ambient_temp_c": ambient_temp,
                            "humidity": humidity,
                            "storage_temp_low_c": float(storage_temp_low),
                            "storage_temp_high_c": float(storage_temp_high),
                            "storage_temp_mid_c": storage_temp_mid,
                            "storage_capacity_mean_ton": storage_capacity_mean,
                            "alpha_target": alpha,
                            "beta_target": beta,
                        }
                    )

    df = pd.DataFrame(rows)
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
    ]
    target_columns = ["alpha_target", "beta_target"]
    return SyntheticDatasetBundle(df, feature_columns, target_columns)


def save_synthetic_dataset(bundle: SyntheticDatasetBundle, output_dir: str | Path) -> Dict[str, Path]:
    """保存合成训练数据。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "synthetic_loss_dataset.csv"
    xlsx_path = output_dir / "synthetic_loss_dataset.xlsx"
    bundle.dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    bundle.dataframe.to_excel(xlsx_path, index=False)
    return {"csv": csv_path, "xlsx": xlsx_path}
