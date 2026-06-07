"""
损耗参数学习器。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

try:  # optional
    import lightgbm as lgb
except Exception:  # pragma: no cover - optional dependency
    lgb = None

try:  # optional
    import xgboost as xgb
except Exception:  # pragma: no cover - optional dependency
    xgb = None

from src.data_driven.feature_extractor import split_features_targets


@dataclass
class LearnerMetrics:
    """学习器评估结果。"""

    alpha_r2: float
    beta_r2: float
    alpha_rmse: float
    beta_rmse: float
    alpha_mae: float
    beta_mae: float


class LossParameterLearner:
    """学习 α/β 参数的双目标回归器。"""

    def __init__(self, model_type: str = "lightgbm", random_state: int = 42):
        self.model_type = model_type
        self.random_state = random_state
        self.alpha_model = None
        self.beta_model = None
        self.feature_columns: List[str] = []

    def _build_estimator(self):
        if self.model_type == "lightgbm" and lgb is not None:
            return lgb.LGBMRegressor(
                n_estimators=240,
                learning_rate=0.05,
                max_depth=-1,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=self.random_state,
            )
        if self.model_type == "xgboost" and xgb is not None:
            return xgb.XGBRegressor(
                n_estimators=240,
                learning_rate=0.05,
                max_depth=6,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="reg:squarederror",
                random_state=self.random_state,
            )
        if self.model_type in {"sklearn", "gbrt"}:
            return GradientBoostingRegressor(random_state=self.random_state)
        return RandomForestRegressor(
            n_estimators=300,
            random_state=self.random_state,
            min_samples_leaf=2,
            n_jobs=-1,
        )

    def fit(self, df: pd.DataFrame, test_size: float = 0.2) -> LearnerMetrics:
        """训练并返回验证指标。"""
        X, y, feature_columns = split_features_targets(df)
        self.feature_columns = feature_columns
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=self.random_state
        )

        self.alpha_model = self._build_estimator()
        self.beta_model = self._build_estimator()
        self.alpha_model.fit(X_train, y_train["alpha_target"])
        self.beta_model.fit(X_train, y_train["beta_target"])

        alpha_pred = self.alpha_model.predict(X_test)
        beta_pred = self.beta_model.predict(X_test)

        alpha_rmse = float(np.sqrt(mean_squared_error(y_test["alpha_target"], alpha_pred)))
        beta_rmse = float(np.sqrt(mean_squared_error(y_test["beta_target"], beta_pred)))

        return LearnerMetrics(
            alpha_r2=float(r2_score(y_test["alpha_target"], alpha_pred)),
            beta_r2=float(r2_score(y_test["beta_target"], beta_pred)),
            alpha_rmse=alpha_rmse,
            beta_rmse=beta_rmse,
            alpha_mae=float(mean_absolute_error(y_test["alpha_target"], alpha_pred)),
            beta_mae=float(mean_absolute_error(y_test["beta_target"], beta_pred)),
        )

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """预测 α/β。"""
        if self.alpha_model is None or self.beta_model is None:
            raise RuntimeError("Learner has not been fit.")
        X, _, _ = split_features_targets(df)
        X = X.reindex(columns=self.feature_columns, fill_value=0.0)
        return pd.DataFrame(
            {
                "alpha_pred": self.alpha_model.predict(X),
                "beta_pred": self.beta_model.predict(X),
            },
            index=df.index,
        )

    def save(self, output_dir: str | Path) -> Dict[str, Path]:
        """保存模型和元数据。"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        alpha_path = output_dir / "alpha_model.pkl"
        beta_path = output_dir / "beta_model.pkl"
        meta_path = output_dir / "learner_meta.json"
        joblib.dump(self.alpha_model, alpha_path)
        joblib.dump(self.beta_model, beta_path)
        meta_path.write_text(
            json.dumps(
                {"model_type": self.model_type, "feature_columns": self.feature_columns},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"alpha": alpha_path, "beta": beta_path, "meta": meta_path}

    @classmethod
    def load(cls, output_dir: str | Path) -> "LossParameterLearner":
        """加载已保存模型。"""
        output_dir = Path(output_dir)
        meta = json.loads((output_dir / "learner_meta.json").read_text(encoding="utf-8"))
        obj = cls(model_type=meta["model_type"])
        obj.alpha_model = joblib.load(output_dir / "alpha_model.pkl")
        obj.beta_model = joblib.load(output_dir / "beta_model.pkl")
        obj.feature_columns = meta["feature_columns"]
        return obj
