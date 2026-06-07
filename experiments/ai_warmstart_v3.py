"""AI guided warm start for v3.0 capacity-chain MIP.

策略
----
1. 从已有 v3.0 priority scenario runs 提取两层标签：
   - site-level: 每个 run 的开放站点集合
   - facility-level: 每个 run 的 (site, type, capacity_idx) 设施组合
2. 计算每个候选点的结构性特征（27 个候选 × ~12 个特征）
3. XGBoost binary classifier 学 (节点特征 → 是否最优开放)
4. 对当前 v3.0 实例预测每个候选点开放概率，取 top-K 个作为 site ranking
5. 再基于历史 facility 标签，为这些 top-K 站点补齐 type + capacity，形成
   site + type + capacity 联合 MIP Start
6. 跑 v3.0 两组对比：
   - cold_start: 无任何 hint
   - ai_warm:    注入 AI 联合 warm-start 设施组合
   比较达到 1% 容差的时间、最终 gap、目标值（应一致）

研究边界
--------
- 标签数据小（priority runs 仅 4 个），AI 用 XGBoost + 轻量 facility template 推断
- 特征是结构性（产量/距离/坐标等），不学完整最优 z 解
- AI 推荐的是站点-类型-容量联合起点，Gurobi 仍做最终决策
- 县域 39 节点案例，需要更多企业级数据才能扩展到大规模
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.capacity_chain_assumptions import default_assumptions

PRIORITY_DIR = PROJECT_ROOT / "results" / "experiments" / "model_v3_priority_scenarios"
OSM_DIST = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
OSM_TIME = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"
OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TIME_LIMIT = 600.0
MIP_GAP = 0.01
TOP_K = 8   # AI 推荐 top-K 节点作为 warm start 设施候选
DEFAULT_WARM_TYPE = "cold"
DEFAULT_WARM_CAPACITY_IDX = 1
WARM_VERSION_V1 = "site_only"
WARM_VERSION_V2 = "site_type"
WARM_VERSION_V3 = "site_type_capacity"
RECOMMENDED_WARM_VERSION = WARM_VERSION_V3
SITE_ONLY_STRATEGY = "site_ranking + default_type_capacity_fallback"
SITE_TYPE_STRATEGY = "site_ranking + site_history_or_nearest_neighbor_type + default_capacity"
JOINT_WARM_STRATEGY = "site_ranking + site_history_or_nearest_neighbor_type_capacity"
WARM_VERSION_LABELS = {
    WARM_VERSION_V1: "V1 site-only",
    WARM_VERSION_V2: "V2 site + type",
    WARM_VERSION_V3: "V3 site + type + capacity",
}
WARM_STRATEGY_DESCRIPTIONS = {
    WARM_VERSION_V1: "Only inject ranked sites; type/capacity fall back to the default cold mid-cap template.",
    WARM_VERSION_V2: "Inject ranked sites plus inferred storage type; capacity falls back to the default slot for that type.",
    WARM_VERSION_V3: "Inject ranked sites plus inferred storage type and capacity using historical facility labels with nearest-neighbor fallback.",
}


def long_to_pivot(path: Path, value_col: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    pivot = df.pivot(index="origin", columns="destination", values=value_col)
    ids = sorted(pivot.index.tolist())
    return pivot.loc[ids, ids]


class DataConfigOSM(DataConfig):
    def __init__(self):
        super().__init__(str(PROJECT_ROOT / "data"))
        dp = long_to_pivot(OSM_DIST, "distance_km")
        tp = long_to_pivot(OSM_TIME, "time_h")
        self.distance = dp.values
        self.transport_time = tp.values
        self.node_ids = list(dp.index)
        self.id2idx = {n: i for i, n in enumerate(self.node_ids)}


# ── 特征工程 ───────────────────────────────────────────────────────────────────

def compute_node_features(config: DataConfig) -> pd.DataFrame:
    """对每个候选点算 ~12 个结构性特征。"""
    candidates = config.candidates
    demands = config.demands

    rows = []
    for _, c in candidates.iterrows():
        nid = c["node_id"]
        prod = float(c.get("okra_production_ton", 0.0))
        pop = float(c.get("population", 0.0))
        lat, lon = float(c["lat"]), float(c["lon"])
        level = int(c.get("level", 1))

        dists = np.array([config.get_dist(nid, d) for d in demands["node_id"]])
        times = np.array([config.get_time(nid, d) for d in demands["node_id"]])
        d_weights = np.array([config.get_demand(d) for d in demands["node_id"]])
        weighted_dist = float((dists * d_weights).sum() / max(1e-6, d_weights.sum()))
        precool_cover = int((times <= 2.0).sum())
        cover_4h = int((times <= 4.0).sum())

        try:
            d_to_c1 = float(config.get_dist(nid, "C1"))
        except KeyError:
            d_to_c1 = 0.0

        rows.append({
            "node_id": nid,
            "production_ton": prod,
            "population": pop,
            "lat": lat,
            "lon": lon,
            "level": level,
            "is_county": int(level == 3),
            "is_town": int(level == 2),
            "weighted_dist": weighted_dist,
            "min_dist": float(dists.min()) if len(dists) else 0.0,
            "max_dist": float(dists.max()) if len(dists) else 0.0,
            "precool_cover_2h": precool_cover,
            "cover_4h": cover_4h,
            "dist_to_C1": d_to_c1,
        })
    return pd.DataFrame(rows)


# ── 标签提取 ───────────────────────────────────────────────────────────────────

def extract_labels_from_priority_runs() -> dict[str, set[str]]:
    """从 priority scenario runs 提取 {variant_name → set of opened sites}。"""
    labels: dict[str, set[str]] = {}
    for f in sorted(PRIORITY_DIR.glob("*_run.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        variant_field = d.get("variant", {})
        if isinstance(variant_field, dict):
            variant = variant_field.get("name") or variant_field.get("variant_id")
        else:
            variant = variant_field
        if not variant:
            variant = f.stem.replace("_bound_focus_60s_run", "")
        opened = {fac["site"] for fac in d.get("facilities", []) if "site" in fac}
        if opened:
            labels[str(variant)] = opened
    return labels


def extract_facility_labels_from_priority_runs() -> dict[str, list[dict[str, Any]]]:
    """从 priority scenario runs 提取 {variant_name → facilities[]} 的联合设施标签。"""
    labels: dict[str, list[dict[str, Any]]] = {}
    for f in sorted(PRIORITY_DIR.glob("*_run.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        variant_field = d.get("variant", {})
        if isinstance(variant_field, dict):
            variant = variant_field.get("name") or variant_field.get("variant_id")
        else:
            variant = variant_field
        if not variant:
            variant = f.stem.replace("_bound_focus_60s_run", "")

        facilities = []
        for fac in d.get("facilities", []):
            site = fac.get("site")
            type_id = fac.get("type")
            capacity_idx = fac.get("capacity_idx")
            if not site or type_id is None or capacity_idx is None:
                continue
            facilities.append(
                {
                    "site": str(site),
                    "type": str(type_id),
                    "capacity_idx": int(capacity_idx),
                    "capacity": fac.get("capacity"),
                    "variant": str(variant),
                }
            )
        if facilities:
            labels[str(variant)] = facilities
    return labels


def build_training_table(features: pd.DataFrame, labels: dict[str, set[str]]) -> pd.DataFrame:
    """给定每个 variant 的 opened 集合，组合为 (variant, node, features..., label)。"""
    rows = []
    for variant, opened in labels.items():
        for _, f in features.iterrows():
            row = f.to_dict()
            row["variant"] = variant
            row["label"] = int(f["node_id"] in opened)
            rows.append(row)
    return pd.DataFrame(rows)


# ── 训练 ───────────────────────────────────────────────────────────────────────

def train_ranker(train_df: pd.DataFrame, xgb_params: dict[str, Any] | None = None):
    """训练 XGBoost binary classifier 预测候选点是否开放。"""
    from xgboost import XGBClassifier

    feature_cols = [c for c in train_df.columns if c not in ("node_id", "variant", "label")]
    X = train_df[feature_cols].values
    y = train_df["label"].values
    params = {
        "n_estimators": 80,
        "max_depth": 4,
        "learning_rate": 0.1,
        "eval_metric": "logloss",
        "random_state": 42,
        "scale_pos_weight": (len(y) - y.sum()) / max(1, y.sum()),
    }
    if xgb_params:
        params.update(xgb_params)
    clf = XGBClassifier(**params)
    clf.fit(X, y)
    return clf, feature_cols


def predict_top_k(clf, features: pd.DataFrame, feature_cols: list[str], k: int) -> tuple[list[str], pd.DataFrame]:
    """对当前实例预测，返回 top-K 概率最高的 node_id。"""
    X = features[feature_cols].values
    probs = clf.predict_proba(X)[:, 1]
    feat_with_score = features.assign(score=probs)
    top = feat_with_score.sort_values("score", ascending=False).head(k)
    return top["node_id"].tolist(), feat_with_score


# ── 联合 warm-start 设施推断 ──────────────────────────────────────────────────

def _most_common_facility_template(facilities: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter((str(f["type"]), int(f["capacity_idx"])) for f in facilities)
    (type_id, capacity_idx), _count = counter.most_common(1)[0]
    sample = next(
        f for f in facilities if str(f["type"]) == type_id and int(f["capacity_idx"]) == capacity_idx
    )
    return {
        "type": type_id,
        "capacity_idx": capacity_idx,
        "capacity": sample.get("capacity"),
    }


def _default_capacity_for_type(config: DataConfig, type_id: str) -> tuple[int, float]:
    cap_idx = min(DEFAULT_WARM_CAPACITY_IDX, len(config.capacity_index[type_id]) - 1)
    capacity = config.capacity_index[type_id][cap_idx]["capacity"]
    return int(cap_idx), capacity


def _most_common_type(facilities: list[dict[str, Any]]) -> str:
    return Counter(str(f["type"]) for f in facilities).most_common(1)[0][0]


def _nearest_observed_site(
    site: str,
    feature_index: pd.DataFrame,
    feature_cols: list[str],
    observed_sites: list[str],
) -> str:
    target = feature_index.loc[site, feature_cols].astype(float).to_numpy()
    return min(
        observed_sites,
        key=lambda obs: float(
            np.linalg.norm(target - feature_index.loc[obs, feature_cols].astype(float).to_numpy())
        ),
    )


def summarize_assignment_sources(facilities: list[dict[str, Any]]) -> dict[str, int]:
    return {str(k): int(v) for k, v in Counter(str(f.get("assignment_source", "unknown")) for f in facilities).items()}


def default_warm_facilities_from_sites(config: DataConfig, warm_sites: list[str] | None) -> list[dict[str, Any]]:
    """旧逻辑兼容：站点 → cold + 中档容量。"""
    if not warm_sites:
        return []
    cap_idx = min(DEFAULT_WARM_CAPACITY_IDX, len(config.capacity_index[DEFAULT_WARM_TYPE]) - 1)
    capacity = config.capacity_index[DEFAULT_WARM_TYPE][cap_idx]["capacity"]
    return [
        {
            "site": str(site),
            "type": DEFAULT_WARM_TYPE,
            "capacity_idx": int(cap_idx),
            "capacity": capacity,
            "assignment_source": "default_site_only_fallback",
            "matched_site": None,
        }
        for site in warm_sites
        if site
    ]


def build_site_type_warm_facilities(
    top_sites: list[str],
    features: pd.DataFrame,
    scored_features: pd.DataFrame,
    facility_labels: dict[str, list[dict[str, Any]]],
    config: DataConfig,
) -> list[dict[str, Any]]:
    """把 top-K 站点升级成 site + type，capacity 保持固定档的 warm-start 设施组合。"""
    if not top_sites:
        return []

    feature_cols = [c for c in features.columns if c != "node_id"]
    feature_index = features.set_index("node_id")
    score_by_site = {
        str(item["node_id"]): float(item["score"])
        for item in scored_features[["node_id", "score"]].to_dict("records")
    }

    site_histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for facilities in facility_labels.values():
        for fac in facilities:
            site_histories[str(fac["site"])].append(fac)

    observed_sites = [site for site in site_histories if site in feature_index.index]
    global_pool = [fac for facilities in site_histories.values() for fac in facilities]
    non_precool_pool = [fac for fac in global_pool if str(fac["type"]) != "precool"]
    fallback_pool = non_precool_pool or global_pool
    default_type = _most_common_type(fallback_pool) if fallback_pool else DEFAULT_WARM_TYPE

    facilities = []
    for rank, site in enumerate(top_sites, start=1):
        source = "site_history_type"
        matched_site = site

        if site in site_histories:
            type_id = _most_common_type(site_histories[site])
        elif observed_sites and site in feature_index.index:
            source = "nearest_neighbor_type"
            matched_site = _nearest_observed_site(site, feature_index, feature_cols, observed_sites)
            type_id = _most_common_type(site_histories[matched_site])
        else:
            source = "global_type_fallback"
            matched_site = None
            type_id = default_type

        capacity_idx, capacity = _default_capacity_for_type(config, str(type_id))
        facilities.append(
            {
                "site": str(site),
                "type": str(type_id),
                "capacity_idx": capacity_idx,
                "capacity": capacity,
                "site_rank": rank,
                "score": round(float(score_by_site.get(site, 0.0)), 6),
                "assignment_source": source,
                "matched_site": matched_site,
            }
        )
    return facilities


def build_joint_warm_facilities(
    top_sites: list[str],
    features: pd.DataFrame,
    scored_features: pd.DataFrame,
    facility_labels: dict[str, list[dict[str, Any]]],
    config: DataConfig,
) -> list[dict[str, Any]]:
    """把 top-K 站点升级成 site + type + capacity 联合 warm-start 设施组合。"""
    if not top_sites:
        return []

    feature_cols = [c for c in features.columns if c != "node_id"]
    feature_index = features.set_index("node_id")
    score_by_site = {
        str(item["node_id"]): float(item["score"])
        for item in scored_features[["node_id", "score"]].to_dict("records")
    }

    site_histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for facilities in facility_labels.values():
        for fac in facilities:
            site_histories[str(fac["site"])].append(fac)

    observed_sites = [site for site in site_histories if site in feature_index.index]
    global_pool = [fac for facilities in site_histories.values() for fac in facilities]
    non_precool_pool = [fac for fac in global_pool if str(fac["type"]) != "precool"]
    fallback_pool = non_precool_pool or global_pool
    default_template = _most_common_facility_template(fallback_pool) if fallback_pool else None

    joint = []
    for rank, site in enumerate(top_sites, start=1):
        source = "site_history"
        matched_site = site

        if site in site_histories:
            chosen = _most_common_facility_template(site_histories[site])
        elif observed_sites and site in feature_index.index:
            source = "nearest_neighbor"
            matched_site = _nearest_observed_site(site, feature_index, feature_cols, observed_sites)
            chosen = _most_common_facility_template(site_histories[matched_site])
        elif default_template is not None:
            source = "global_fallback"
            matched_site = None
            chosen = dict(default_template)
        else:
            source = "default_site_only_fallback"
            matched_site = None
            chosen = default_warm_facilities_from_sites(config, [site])[0]

        type_id = str(chosen["type"])
        capacity_idx = int(chosen["capacity_idx"])
        capacity = config.capacity_index[type_id][capacity_idx]["capacity"]
        joint.append(
            {
                "site": site,
                "type": type_id,
                "capacity_idx": capacity_idx,
                "capacity": capacity,
                "site_rank": rank,
                "score": round(float(score_by_site.get(site, 0.0)), 6),
                "assignment_source": source,
                "matched_site": matched_site,
            }
        )
    return joint


def build_warm_facilities_for_version(
    version: str,
    top_sites: list[str],
    features: pd.DataFrame,
    scored_features: pd.DataFrame,
    facility_labels: dict[str, list[dict[str, Any]]],
    config: DataConfig,
) -> tuple[list[dict[str, Any]], str]:
    if version == WARM_VERSION_V1:
        return default_warm_facilities_from_sites(config, top_sites), SITE_ONLY_STRATEGY
    if version == WARM_VERSION_V2:
        return build_site_type_warm_facilities(top_sites, features, scored_features, facility_labels, config), SITE_TYPE_STRATEGY
    if version == WARM_VERSION_V3:
        return build_joint_warm_facilities(top_sites, features, scored_features, facility_labels, config), JOINT_WARM_STRATEGY
    raise ValueError(f"Unknown warm strategy version: {version}")


# ── v3.0 求解（带可选 MIP Start）─────────────────────────────────────────────

def solve_v3_with_optional_warm(
    config: DataConfigOSM,
    warm_sites: list[str] | None,
    label: str,
    warm_facilities: list[dict[str, Any]] | None = None,
    warm_strategy_version: str | None = None,
    warm_strategy_name: str | None = None,
    assumptions: Any | None = None,
    time_limit: float | None = None,
    mip_gap: float | None = None,
    solver_params: dict[str, Any] | None = None,
) -> dict:
    """跑 v3.0 求解，可选注入 warm start 作为 MIP Start。

    Parameters
    ----------
    assumptions : CapacityChainAssumptions | None
        自定义容量链假设（如跨区域验证时需调整 max_facilities）。
        为 None 时使用 default_assumptions()。
    time_limit : float | None
        自定义求解时间限制（秒）。为 None 时使用模块默认 TIME_LIMIT。
    mip_gap : float | None
        自定义 MIP gap 容差。为 None 时使用模块默认 MIP_GAP。
    """
    from src.models.single_level_mip_v2_1 import GRB, gp
    from src.models.capacity_chain_assumptions import _channel_map

    if assumptions is not None:
        _assumptions = assumptions
    else:
        _assumptions = default_assumptions()
    _time_limit = int(time_limit) if time_limit is not None else int(TIME_LIMIT)
    _mip_gap = mip_gap if mip_gap is not None else MIP_GAP
    channels = _channel_map(_assumptions)
    active_types = [c.type_id for c in _assumptions.channels if c.annual_share > 0]
    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])
    demand = {nid: config.get_demand(nid) for nid in demand_ids}
    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)

    model = gp.Model(f"v3_warm_{label}")
    model.setParam("TimeLimit", _time_limit)
    model.setParam("MIPGap", _mip_gap)
    model.setParam("Threads", 8)
    model.setParam("OutputFlag", 0)
    model.setParam("MIPFocus", 3)
    model.setParam("Cuts", 2)
    for param_name, param_value in (solver_params or {}).items():
        model.setParam(param_name, param_value)

    z: dict[Any, Any] = {}
    for j in candidate_ids:
        for t in active_types:
            for c in range(len(config.capacity_index[t])):
                z[j, t, c] = model.addVar(vtype=GRB.BINARY, name=f"z_{j}_{t}_{c}")

    x: dict[Any, Any] = {}
    for d in demand_ids:
        for j in candidate_ids:
            for t in active_types:
                x[d, j, t] = model.addVar(lb=0.0, ub=1.0, name=f"x_{d}_{j}_{t}")

    model.update()

    applied_warm_facilities = warm_facilities if warm_facilities is not None else default_warm_facilities_from_sites(config, warm_sites)
    warm_sites_used: list[str] = []
    n_warm_set = 0
    if applied_warm_facilities:
        for var in z.values():
            var.Start = 0.0
        for fac in applied_warm_facilities:
            site = str(fac.get("site"))
            type_id = str(fac.get("type"))
            capacity_idx = int(fac.get("capacity_idx", 0))
            if (site, type_id, capacity_idx) in z:
                z[site, type_id, capacity_idx].Start = 1.0
                warm_sites_used.append(site)
                n_warm_set += 1
    warm_sites_used = list(dict.fromkeys(warm_sites_used))

    for d in demand_ids:
        for t in active_types:
            share = channels[t].annual_share
            model.addConstr(
                gp.quicksum(x[d, j, t] for j in candidate_ids) == share,
                name=f"cs_{d}_{t}",
            )

    for d in demand_ids:
        for j in candidate_ids:
            for t in active_types:
                model.addConstr(
                    x[d, j, t] <= gp.quicksum(z[j, t, c] for c in range(len(config.capacity_index[t]))),
                    name=f"ao_{d}_{j}_{t}",
                )

    for j in candidate_ids:
        model.addConstr(
            gp.quicksum(z[j, t, c] for t in active_types for c in range(len(config.capacity_index[t]))) <= 1,
            name=f"one_facility_{j}",
        )
    model.addConstr(
        gp.quicksum(z[j, t, c] for j in candidate_ids for t in active_types for c in range(len(config.capacity_index[t]))) <= _assumptions.max_facilities,
        name="max_facilities",
    )

    for d in demand_ids:
        for j in candidate_ids:
            if config.get_time(d, j) > precool_limit_h:
                model.addConstr(x[d, j, "precool"] == 0.0)

    for j in candidate_ids:
        for t in active_types:
            ch = channels[t]
            peak = gp.quicksum(
                x[d, j, t] * demand[d] * ch.storage_days / _assumptions.harvest_window_days * _assumptions.harvest_peak_factor
                for d in demand_ids
            )
            cap = gp.quicksum(
                z[j, t, c] * config.capacity_index[t][c]["capacity"]
                for c in range(len(config.capacity_index[t]))
            )
            model.addConstr(peak <= cap, name=f"pc_{j}_{t}")

    fixed = gp.quicksum(
        z[j, t, c] * config.capacity_index[t][c]["fixed_cost"] * 10000
        for j in candidate_ids for t in active_types for c in range(len(config.capacity_index[t]))
    )
    operate = gp.quicksum(
        z[j, t, c] * config.capacity_index[t][c]["operate_cost"] * 10000
        for j in candidate_ids for t in active_types for c in range(len(config.capacity_index[t]))
    )
    transport = gp.quicksum(
        x[d, j, t] * demand[d] * config.get_dist(d, j) * _assumptions.transport_cost_yuan_per_ton_km
        for d in demand_ids for j in candidate_ids for t in active_types
    )
    loss = gp.quicksum(
        x[d, j, t] * demand[d]
        * (config.get_time(d, j) * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
           * channels[t].transport_loss_multiplier + channels[t].loss_rate)
        * _assumptions.loss_price
        for d in demand_ids for j in candidate_ids for t in active_types
    )
    carbon = gp.quicksum(
        x[d, j, t] * demand[d]
        * (config.capacity_index[t][0]["energy_cost_per_ton"] * config.capacity_index[t][0]["carbon_factor"] / 1000
           + config.get_dist(d, j) * _assumptions.transport_carbon_kg_per_ton_km / 1000)
        * _assumptions.carbon_price
        for d in demand_ids for j in candidate_ids for t in active_types
    )
    model.setObjective(fixed + operate + transport + loss + carbon, GRB.MINIMIZE)
    model.update()

    t0 = time.time()
    model.optimize()
    elapsed = time.time() - t0

    obj = model.ObjVal if model.SolCount > 0 else None
    bound = model.ObjBound
    gap = model.MIPGap if model.SolCount > 0 else None
    status = {2: "OPTIMAL", 9: "TIME_LIMIT"}.get(model.Status, str(model.Status))

    assignment_source_breakdown = summarize_assignment_sources(applied_warm_facilities)
    return {
        "label": label,
        "status": status,
        "objective": obj,
        "bound": bound,
        "mip_gap_pct": round(gap * 100, 4) if gap is not None else None,
        "elapsed_sec": round(elapsed, 2),
        "warm_sites": warm_sites_used,
        "warm_sites_injected": len(warm_sites_used),
        "warm_facilities": applied_warm_facilities,
        "warm_facilities_injected": n_warm_set,
        "warm_strategy_version": warm_strategy_version,
        "warm_strategy_name": warm_strategy_name,
        "assignment_source_breakdown": assignment_source_breakdown,
        "solved_to_tol": gap is not None and gap <= _mip_gap,
        "solver_params": solver_params or {},
    }


def main():
    print("=== v3.0 AI guided warm start 实验 ===\n")

    config = DataConfigOSM()

    print("[1] 提取训练标签...")
    labels = extract_labels_from_priority_runs()
    facility_labels = extract_facility_labels_from_priority_runs()
    print(f"  Found {len(labels)} priority variant labels")
    for v, sites in labels.items():
        print(f"    {v}: {len(sites)} sites = {sorted(sites)}")

    print("\n[2] 计算节点特征...")
    features = compute_node_features(config)
    print(f"  {len(features)} candidates × {len(features.columns) - 1} features")

    print("\n[3] 构建训练表...")
    train_df = build_training_table(features, labels)
    print(f"  {len(train_df)} rows ({train_df['label'].sum()} positive / {len(train_df) - train_df['label'].sum()} negative)")

    print("\n[4] 训练 XGBoost ranker...")
    clf, feat_cols = train_ranker(train_df)
    importances = sorted(zip(feat_cols, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    print("  Top 5 feature importances:")
    for name, imp in importances[:5]:
        print(f"    {name}: {imp:.4f}")

    print(f"\n[5] 预测 top-{TOP_K} 候选...")
    top_sites, scored = predict_top_k(clf, features, feat_cols, TOP_K)
    print(f"  AI top-{TOP_K} sites: {top_sites}")

    warm_facilities_v1, strategy_v1 = build_warm_facilities_for_version(
        WARM_VERSION_V1, top_sites, features, scored, facility_labels, config
    )
    warm_facilities_v2, strategy_v2 = build_warm_facilities_for_version(
        WARM_VERSION_V2, top_sites, features, scored, facility_labels, config
    )
    warm_facilities_v3, strategy_v3 = build_warm_facilities_for_version(
        WARM_VERSION_V3, top_sites, features, scored, facility_labels, config
    )

    print("  Warm-start versions:")
    for version, facilities in [
        (WARM_VERSION_V1, warm_facilities_v1),
        (WARM_VERSION_V2, warm_facilities_v2),
        (WARM_VERSION_V3, warm_facilities_v3),
    ]:
        print(f"    {WARM_VERSION_LABELS[version]}: {len(facilities)} facilities")

    print("\n[6] 四组求解对比 (time_limit=600s, gap_tol=1%)...")
    results = []
    print("\n  [cold_start: no hint]...")
    cold_start = solve_v3_with_optional_warm(config, None, "cold_start")
    results.append(cold_start)
    print(f"    {cold_start}")

    warm_runs = [
        (WARM_VERSION_V1, "warm_v1_site_only", warm_facilities_v1, strategy_v1),
        (WARM_VERSION_V2, "warm_v2_site_type", warm_facilities_v2, strategy_v2),
        (WARM_VERSION_V3, "warm_v3_site_type_capacity", warm_facilities_v3, strategy_v3),
    ]
    results_by_version: dict[str, dict[str, Any]] = {}
    strategy_payload = {}
    facility_payload = {}
    for version, label, facilities, strategy_name in warm_runs:
        print(f"\n  [{label}]...")
        row = solve_v3_with_optional_warm(
            config,
            top_sites,
            label,
            warm_facilities=facilities,
            warm_strategy_version=version,
            warm_strategy_name=strategy_name,
        )
        print(f"    {row}")
        results.append(row)
        results_by_version[version] = row
        strategy_payload[version] = {
            "label": WARM_VERSION_LABELS[version],
            "strategy": strategy_name,
            "description": WARM_STRATEGY_DESCRIPTIONS[version],
            "assignment_source_breakdown": row.get("assignment_source_breakdown", {}),
        }
        facility_payload[version] = facilities

    cold_t = cold_start.get("elapsed_sec")
    target_result = results_by_version[RECOMMENDED_WARM_VERSION]
    target_time = target_result.get("elapsed_sec")
    target_speedup = round(cold_t / target_time, 2) if (cold_t and target_time and target_time > 0) else None

    warm_results = [row for row in results if row.get("warm_strategy_version")]
    solved_warm_results = [row for row in warm_results if row.get("solved_to_tol") and row.get("elapsed_sec") is not None]
    recommended_result = min(solved_warm_results, key=lambda row: row["elapsed_sec"]) if solved_warm_results else target_result
    recommended_version = recommended_result.get("warm_strategy_version") or RECOMMENDED_WARM_VERSION
    recommended_strategy = next(
        (
            payload["strategy"]
            for version, payload in strategy_payload.items()
            if version == recommended_version
        ),
        strategy_v3,
    )
    recommended_speedup = round(cold_t / recommended_result["elapsed_sec"], 2) if (cold_t and recommended_result.get("elapsed_sec")) else None

    report = {
        "experiment": "v3_ai_warmstart",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "available_versions": [WARM_VERSION_V1, WARM_VERSION_V2, WARM_VERSION_V3],
        "target_version": RECOMMENDED_WARM_VERSION,
        "target_label": WARM_VERSION_LABELS[RECOMMENDED_WARM_VERSION],
        "target_strategy": strategy_v3,
        "recommended_version": recommended_version,
        "recommended_label": WARM_VERSION_LABELS[recommended_version],
        "recommended_strategy": recommended_strategy,
        "recommended_reason": "best elapsed_sec among warm-start strategies solved to the configured tolerance",
        "warm_versions": strategy_payload,
        "training": {
            "n_runs_used": len(labels),
            "variants": list(labels.keys()),
            "n_features": len(feat_cols),
            "n_train_rows": int(len(train_df)),
            "n_positive": int(train_df["label"].sum()),
            "feature_importances": [{"feature": n, "importance": float(i)} for n, i in importances],
            "facility_label_variant_count": len(facility_labels),
            "facility_label_count": int(sum(len(v) for v in facility_labels.values())),
        },
        "joint_strategy": strategy_v3,
        "facility_labels_used": {
            "variants": list(facility_labels.keys()),
            "count": int(sum(len(v) for v in facility_labels.values())),
        },
        "ai_top_k": top_sites,
        "version_facilities": facility_payload,
        "ai_warm_facilities": warm_facilities_v3,
        "site_type_capacity_predictions": warm_facilities_v3,
        "site_type_predictions": warm_facilities_v2,
        "scored_candidates": scored[["node_id", "score"]].sort_values("score", ascending=False).to_dict("records"),
        "results": results,
        "results_by_version": results_by_version,
        "cold_start": cold_start,
        "target_warm": target_result,
        "ai_warm": recommended_result,
        "ai_vs_cold_speedup": recommended_speedup,
        "target_ai_vs_cold_speedup": target_speedup,
        "claim_boundary": (
            "AI guided warm start for v3.0 capacity-chain MIP. "
            f"Trained on {len(labels)} priority scenario runs (small data, XGBoost). "
            "Stage A ranks candidate sites from structural features (production, distance, coverage). "
            "This report then compares V1 site-only, V2 site + type, and V3 site + type + capacity warm-start injection. "
            "Gurobi makes final decisions; AI only seeds search. "
            "County-level case (39 nodes), not enterprise-scale validation."
        ),
    }
    out = OUT_DIR / "ai_warmstart_summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[Done] → {out}")
    if recommended_speedup:
        print(f"\n  Recommended AI warm vs cold start: {recommended_speedup}× speedup")
    if target_speedup:
        print(f"  Target V3 AI warm vs cold start: {target_speedup}× speedup")


if __name__ == "__main__":
    main()
