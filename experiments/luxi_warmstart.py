"""芦溪县跨区域验证：v3.0 容量链 MIP + AI warm start V1/V2/V3 对比。

用途：验证 J 县案例上开发的模型与 AI warm start 是否在芦溪县数据上仍然可行且保持加速。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.capacity_chain_assumptions import default_assumptions, CapacityChainAssumptions
from experiments.ai_warmstart_v3 import (
    compute_node_features,
    build_training_table,
    train_ranker,
    predict_top_k,
    build_warm_facilities_for_version,
    solve_v3_with_optional_warm,
    extract_labels_from_priority_runs,
    extract_facility_labels_from_priority_runs,
    summarize_assignment_sources,
    WARM_VERSION_V1, WARM_VERSION_V2, WARM_VERSION_V3,
    WARM_VERSION_LABELS, WARM_STRATEGY_DESCRIPTIONS,
    TOP_K,
)

LUXI_DATA_DIR = PROJECT_ROOT / "data" / "luxi_county"
OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "luxi_warmstart"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TIME_LIMIT = 1200.0
MIP_GAP = 0.02


class DataConfigLuxi(DataConfig):
    def __init__(self):
        super().__init__(str(LUXI_DATA_DIR))


def main():
    print("=== 芦溪县跨区域验证：v3.0 + AI warm start ===\n")

    config = DataConfigLuxi()
    print(f"  节点数: {len(config.nodes)}")
    print(f"  候选点: {len(config.candidates)}")
    print(f"  需求点: {len(config.demands)}")
    print(f"  总产量: {config.nodes['okra_production_ton'].sum():.1f} 吨")

    # ── 计算芦溪专属 max_facilities（J 县 588t→8 个，芦溪 9224t 需更多） ──
    from src.models.capacity_chain_assumptions import _channel_map
    base_assumptions = default_assumptions()
    base_channels = _channel_map(base_assumptions)
    active_types = [c.type_id for c in base_assumptions.channels if c.annual_share > 0]
    demand_ids = list(config.demands["node_id"])
    min_facilities = 0
    for t in active_types:
        ch = base_channels[t]
        peak = sum(
            config.get_demand(d) * ch.annual_share * ch.storage_days
            / base_assumptions.harvest_window_days * base_assumptions.harvest_peak_factor
            for d in demand_ids
        )
        max_cap = config.capacity_index[t][-1]["capacity"]
        min_facilities += int(-(-peak // max_cap))  # ceil division
    luxi_max_facilities = min_facilities + 2  # 留 2 个余量
    print(f"  计算最少设施: {min_facilities}, 设定 max_facilities = {luxi_max_facilities}")

    luxi_assumptions = CapacityChainAssumptions(max_facilities=luxi_max_facilities)

    # ── 训练 AI ranker（复用 J 县 priority runs 的标签作为迁移基线）────────
    print("\n[1] 训练 AI ranker（J 县标签迁移到芦溪特征）...")
    labels = extract_labels_from_priority_runs()
    facility_labels = extract_facility_labels_from_priority_runs()

    # 用芦溪县候选点特征 + J 县标签训练
    # 注意：标签里的 node_id 是 J 县的，芦溪节点会全部匹配不上 → 全负样本
    # 所以更好的策略是：直接用芦溪自身特征做 unsupervised ranking（按产量/距离打分）
    # 这里我们用一个简单策略：把 J 县训练好的模型应用到芦溪特征上（迁移推断）
    from experiments.ai_warmstart_v3 import DataConfigOSM
    j_config = DataConfigOSM()
    j_features = compute_node_features(j_config)
    j_train_df = build_training_table(j_features, labels)
    clf, feat_cols = train_ranker(j_train_df)
    print(f"  J 县训练: {len(j_train_df)} rows, {len(feat_cols)} features")

    # 用训练好的模型对芦溪候选点做迁移推断
    luxi_features = compute_node_features(config)
    top_sites, scored = predict_top_k(clf, luxi_features, feat_cols, k=TOP_K)
    print(f"  芦溪 top-{TOP_K} sites: {top_sites}")

    # ── 构建三版 warm-start 设施组合 ─────────────────────────────────────────
    print("\n[2] 构建 V1/V2/V3 warm-start 设施组合...")
    warm_v1, strategy_v1 = build_warm_facilities_for_version(
        WARM_VERSION_V1, top_sites, luxi_features, scored, facility_labels, config
    )
    warm_v2, strategy_v2 = build_warm_facilities_for_version(
        WARM_VERSION_V2, top_sites, luxi_features, scored, facility_labels, config
    )
    warm_v3, strategy_v3 = build_warm_facilities_for_version(
        WARM_VERSION_V3, top_sites, luxi_features, scored, facility_labels, config
    )
    for version, facilities in [
        (WARM_VERSION_V1, warm_v1),
        (WARM_VERSION_V2, warm_v2),
        (WARM_VERSION_V3, warm_v3),
    ]:
        print(f"    {WARM_VERSION_LABELS[version]}: {len(facilities)} facilities")

    # ── 四组求解 ─────────────────────────────────────────────────────────────
    print(f"\n[3] 四组求解对比 (time_limit={TIME_LIMIT}s, gap_tol={MIP_GAP*100}%)...")
    results = []

    print("\n  [cold_start]...")
    cold = solve_v3_with_optional_warm(config, None, "cold_start", assumptions=luxi_assumptions, time_limit=TIME_LIMIT, mip_gap=MIP_GAP)
    results.append(cold)
    print(f"    obj={cold['objective']}, gap={cold['mip_gap_pct']}%, t={cold['elapsed_sec']}s, status={cold['status']}")

    warm_runs = [
        (WARM_VERSION_V1, "warm_v1_site_only", warm_v1, strategy_v1),
        (WARM_VERSION_V2, "warm_v2_site_type", warm_v2, strategy_v2),
        (WARM_VERSION_V3, "warm_v3_site_type_capacity", warm_v3, strategy_v3),
    ]
    results_by_version = {}
    for version, label, facilities, strategy in warm_runs:
        print(f"\n  [{label}]...")
        row = solve_v3_with_optional_warm(
            config, top_sites, label,
            warm_facilities=facilities,
            warm_strategy_version=version,
            warm_strategy_name=strategy,
            assumptions=luxi_assumptions,
            time_limit=TIME_LIMIT,
            mip_gap=MIP_GAP,
        )
        results.append(row)
        results_by_version[version] = row
        print(f"    obj={row['objective']}, gap={row['mip_gap_pct']}%, t={row['elapsed_sec']}s, status={row['status']}")

    # ── 汇总 ─────────────────────────────────────────────────────────────────
    cold_t = cold.get("elapsed_sec")
    solved_warm = [r for r in results if r.get("warm_strategy_version") and r.get("solved_to_tol") and r.get("elapsed_sec")]
    best_warm = min(solved_warm, key=lambda r: r["elapsed_sec"]) if solved_warm else results_by_version.get(WARM_VERSION_V1, {})
    best_version = best_warm.get("warm_strategy_version", WARM_VERSION_V1)
    best_speedup = round(cold_t / best_warm["elapsed_sec"], 2) if (cold_t and best_warm.get("elapsed_sec")) else None

    report = {
        "experiment": "luxi_cross_region_warmstart",
        "case": "luxi_county",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": {
            "nodes": len(config.nodes),
            "candidates": len(config.candidates),
            "demands": len(config.demands),
            "total_production_ton": round(float(config.nodes["okra_production_ton"].sum()), 1),
            "distance_source": "haversine_detour_factor",
            "data_dir": str(LUXI_DATA_DIR),
        },
        "config": {
            "model": "v3.0_capacity_chain",
            "time_limit": TIME_LIMIT,
            "mip_gap": MIP_GAP,
            "top_k": TOP_K,
            "training_source": "j_county_priority_runs_transfer",
            "max_facilities": luxi_max_facilities,
            "min_facilities_needed": min_facilities,
        },
        "ai_top_k": top_sites,
        "recommended_version": best_version,
        "recommended_label": WARM_VERSION_LABELS.get(best_version, best_version),
        "recommended_speedup": best_speedup,
        "results": results,
        "results_by_version": results_by_version,
        "cold_start": cold,
        "ai_warm": best_warm,
        "claim_boundary": (
            "Cross-region validation of v3.0 capacity-chain MIP + AI warm start on Luxi County data. "
            "AI ranker trained on J County priority scenario labels and applied via transfer inference to Luxi features. "
            f"Best warm-start version: {WARM_VERSION_LABELS.get(best_version, best_version)} with {best_speedup}x speedup. "
            "Distance matrix is Haversine + detour factor (not OSM). "
            "This validates model generalizability, not enterprise-scale deployment."
        ),
    }
    out = OUT_DIR / "luxi_warmstart_summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"  案例: 芦溪县 ({len(config.nodes)} 节点, {config.nodes['okra_production_ton'].sum():.0f} 吨)")
    print(f"  推荐版本: {WARM_VERSION_LABELS.get(best_version, best_version)}")
    print(f"  加速比: {best_speedup}×")
    print(f"  结果: {out}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
