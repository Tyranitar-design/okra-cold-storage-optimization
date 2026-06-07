"""
Cut feature extraction utilities for Benders cut-ranking.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import torch


CUT_FEATURE_NAMES = [
    "rhs",
    "coef_count",
    "coef_abs_mean",
    "coef_abs_std",
    "coef_abs_max",
    "coef_abs_min",
    "coef_l1",
    "coef_l2",
    "coef_pos_ratio",
    "coef_neg_ratio",
    "iteration_idx",
    "master_obj",
    "subproblem_obj",
    "gap_pct",
    "cut_count",
]


def extract_cut_feature_vector(cut: Dict[str, Any], iteration: Dict[str, Any] | None = None) -> np.ndarray:
    """Extract a numerical feature vector for one Benders cut."""
    coef_values = np.array(list(cut.get("coef", {}).values()), dtype=float)
    if coef_values.size == 0:
        coef_values = np.zeros(1, dtype=float)

    abs_vals = np.abs(coef_values)
    pos_ratio = float(np.mean(coef_values > 0.0))
    neg_ratio = float(np.mean(coef_values < 0.0))

    feature_values = [
        float(cut.get("rhs", 0.0)),
        float(len(coef_values)),
        float(abs_vals.mean()),
        float(abs_vals.std(ddof=0)),
        float(abs_vals.max()),
        float(abs_vals.min()),
        float(np.abs(coef_values).sum()),
        float(np.sqrt(np.square(coef_values).sum())),
        pos_ratio,
        neg_ratio,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    ]

    if iteration is not None:
        feature_values[10] = float(iteration.get("iteration", 0))
        feature_values[11] = float(iteration.get("master_obj", 0.0))
        feature_values[12] = float(iteration.get("subproblem_obj", 0.0))
        feature_values[13] = float(iteration.get("gap_pct", 0.0))
        feature_values[14] = float(iteration.get("cut_count", 0))

    return np.asarray(feature_values, dtype=np.float32)


def build_cut_dataset(cut_history: List[Dict[str, Any]]) -> Tuple[torch.Tensor, torch.Tensor, List[Dict[str, Any]]]:
    """Build feature/label tensors from cut history."""
    if not cut_history:
        return torch.zeros((0, len(CUT_FEATURE_NAMES))), torch.zeros((0,)), []

    features = []
    rewards = []
    prev_gap = None
    for record in cut_history:
        iteration = record.get("iteration", {})
        cut = record.get("cut", {})
        features.append(extract_cut_feature_vector(cut, iteration))
        gap = float(iteration.get("gap_pct", 0.0))
        if prev_gap is None:
            reward = max(0.0, 100.0 - gap)
        else:
            reward = max(0.0, prev_gap - gap)
        rewards.append(reward)
        prev_gap = gap

    x = torch.tensor(np.stack(features, axis=0), dtype=torch.float32)
    y = torch.tensor(np.asarray(rewards, dtype=np.float32), dtype=torch.float32)
    return x, y, cut_history
