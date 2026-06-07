"""
SPO 端到端管线。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.data_driven.loss_param_learner import LossParameterLearner
from src.data_driven.synthetic_data import generate_synthetic_loss_dataset, save_synthetic_dataset


def run_spo_pipeline(
    config: Any,
    *,
    output_dir: str | Path,
    model_type: str = "lightgbm",
    samples_per_combination: int = 6,
    random_state: int = 42,
) -> Dict[str, Any]:
    """生成训练数据、训练参数学习器并导出结果。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle = generate_synthetic_loss_dataset(
        config,
        samples_per_combination=samples_per_combination,
        random_state=random_state,
    )
    dataset_paths = save_synthetic_dataset(bundle, output_dir / "synthetic_data")

    learner = LossParameterLearner(model_type=model_type, random_state=random_state)
    metrics = learner.fit(bundle.dataframe)
    model_paths = learner.save(output_dir / "models")

    predictions = learner.predict(bundle.dataframe)
    eval_frame = pd.concat([bundle.dataframe.reset_index(drop=True), predictions.reset_index(drop=True)], axis=1)
    eval_frame["alpha_error"] = eval_frame["alpha_pred"] - eval_frame["alpha_target"]
    eval_frame["beta_error"] = eval_frame["beta_pred"] - eval_frame["beta_target"]

    eval_csv = output_dir / "spo_predictions.csv"
    eval_xlsx = output_dir / "spo_predictions.xlsx"
    eval_frame.to_csv(eval_csv, index=False, encoding="utf-8-sig")
    eval_frame.to_excel(eval_xlsx, index=False)

    summary = {
        "dataset_rows": int(len(bundle.dataframe)),
        "feature_columns": bundle.feature_columns,
        "target_columns": bundle.target_columns,
        "metrics": metrics.__dict__,
        "dataset_paths": {k: str(v) for k, v in dataset_paths.items()},
        "model_paths": {k: str(v) for k, v in model_paths.items()},
        "prediction_paths": {"csv": str(eval_csv), "xlsx": str(eval_xlsx)},
    }
    (output_dir / "spo_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
