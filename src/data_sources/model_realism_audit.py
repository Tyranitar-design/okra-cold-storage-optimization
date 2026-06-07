"""Audit whether the current optimization model can support strong paper claims."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict

from src.api.services import load_json_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
DATA_ROOT = PROJECT_ROOT / "data"
NODES_CSV = DATA_ROOT / "nodes.csv"
PARAMS_JSON = DATA_ROOT / "params.json"
BASELINE_REPORT_JSON = RESULTS_ROOT / "baseline_v2_1_report.json"
ANALYSIS_VISUALIZATION_JSON = RESULTS_ROOT / "analysis_visualization_report.json"
INGESTION_VALIDATION_JSON = RESULTS_ROOT / "real_data_sources" / "real_data_ingestion_validation.json"
MODEL_SOURCE = PROJECT_ROOT / "src" / "models" / "single_level_mip_v2_1.py"
MODEL_REALISM_AUDIT_JSON_PATH = RESULTS_ROOT / "model_realism_audit.json"
MODEL_REALISM_AUDIT_MD_PATH = RESULTS_ROOT / "model_realism_audit.md"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_nodes() -> list[dict[str, Any]]:
    if not NODES_CSV.exists():
        return []
    with NODES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _pct(part: float, total: float) -> float:
    return part / total * 100.0 if total else 0.0


def _ratio(part: float, total: float) -> float:
    return part / total if total else 0.0


def _severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1, "info": 0}.get(severity, 0)


def _state_from_severity(severity: str) -> str:
    if severity == "high":
        return "needs_v3_before_strong_claim"
    if severity == "medium":
        return "caution"
    if severity == "low":
        return "watch"
    return "informational"


def _check(
    *,
    check_id: str,
    name: str,
    severity: str,
    detail: str,
    evidence: str,
    claim_boundary: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "state": _state_from_severity(severity),
        "severity": severity,
        "detail": detail,
        "evidence": evidence,
        "claim_boundary": claim_boundary,
        "next_action": next_action,
    }


def build_model_realism_audit() -> Dict[str, Any]:
    nodes = _read_nodes()
    params = load_json_payload(PARAMS_JSON) if PARAMS_JSON.exists() else {}
    baseline = load_json_payload(BASELINE_REPORT_JSON) if BASELINE_REPORT_JSON.exists() else {}
    analysis = load_json_payload(ANALYSIS_VISUALIZATION_JSON) if ANALYSIS_VISUALIZATION_JSON.exists() else {}
    ingestion = load_json_payload(INGESTION_VALIDATION_JSON) if INGESTION_VALIDATION_JSON.exists() else {}
    model_source = MODEL_SOURCE.read_text(encoding="utf-8") if MODEL_SOURCE.exists() else ""

    total_production = sum(_float(row.get("okra_production_ton")) for row in nodes)
    candidate_count = sum(1 for row in nodes if str(row.get("is_candidate", "")).lower() == "true")
    demand_node_count = sum(1 for row in nodes if _float(row.get("okra_production_ton")) > 0)

    baseline_summary = baseline.get("summary", {}) if isinstance(baseline, dict) else {}
    facilities = baseline.get("facilities", []) if isinstance(baseline, dict) else []
    total_capacity = sum(_float(item.get("capacity")) for item in facilities)
    assigned_demand = sum(_float(item.get("assigned_demand")) for item in facilities)
    storage_types = [str(item.get("type", "")) for item in facilities if item.get("type")]
    unique_storage_types = sorted(set(storage_types))
    frozen_count = sum(1 for item in storage_types if item == "frozen")

    total_cost = _float(baseline_summary.get("total_cost"))
    fixed_cost = _float(baseline_summary.get("fixed_cost"))
    operate_cost = _float(baseline_summary.get("operate_cost"))
    transport_cost = _float(baseline_summary.get("transport_cost"))
    loss_cost = _float(baseline_summary.get("loss_cost"))
    carbon_cost = _float(baseline_summary.get("carbon_cost"))
    fixed_operating_share = _pct(fixed_cost + operate_cost, total_cost)
    variable_share = _pct(transport_cost + loss_cost + carbon_cost, total_cost)

    analysis_summary = analysis.get("summary", {}) if isinstance(analysis, dict) else {}
    scenario_spread = _float(analysis_summary.get("scenario_cost_spread_pct"))
    scenario_stable = bool(analysis_summary.get("scenario_stable_open_sites"))
    sensitivity_stable = bool(analysis_summary.get("sensitivity_all_groups_stable_open_sites"))

    cold_types = params.get("cold_storage_types", {}) if isinstance(params, dict) else {}
    preservation = params.get("okra_preservation", {}) if isinstance(params, dict) else {}
    ready_for_apply_count = int(_float(ingestion.get("ready_for_apply_count", 0))) if isinstance(ingestion, dict) else 0

    annual_capacity_ratio = _ratio(total_capacity, total_production)
    assigned_capacity_ratio = _ratio(assigned_demand, total_capacity)
    frozen_share = _pct(frozen_count, len(facilities))
    model_uses_annual_demand_capacity = "total_assigned <= total_capacity" in model_source and "okra_production_ton" in model_source
    frozen_loss_proxy_detected = "frozen': pp['cold_storage_loss_weekly'] * 0.5" in model_source

    checks = [
        _check(
            check_id="capacity_semantics",
            name="容量口径",
            severity="high" if 0.9 <= annual_capacity_ratio <= 1.2 and model_uses_annual_demand_capacity else "medium",
            detail=(
                f"annual_production={total_production:.3f}t, selected_capacity={total_capacity:.3f}t, "
                f"capacity_to_annual_production={annual_capacity_ratio:.3f}, assigned_to_capacity={assigned_capacity_ratio:.3f}"
            ),
            evidence="data/nodes.csv; results/baseline_v2_1_report.json; src/models/single_level_mip_v2_1.py",
            claim_boundary=(
                "Current v2.1 can be described as an annual-volume capacity proxy, but not yet as a validated inventory/throughput capacity model."
            ),
            next_action=(
                "Build v3.0 capacity semantics with peak harvest days, turnover days, storage duration, service mode shares, and capacity utilization constraints."
            ),
        ),
        _check(
            check_id="temperature_chain",
            name="秋葵温度链表达",
            severity="high" if len(unique_storage_types) == 1 and unique_storage_types == ["frozen"] else "medium",
            detail=f"selected_storage_types={unique_storage_types}, frozen_facility_share={frozen_share:.1f}%, preservation_keys={sorted(preservation.keys())}",
            evidence="data/params.json; results/baseline_v2_1_report.json",
            claim_boundary=(
                "A frozen-only optimum should be treated as a signal that service-chain constraints or product-channel shares are incomplete."
            ),
            next_action=(
                "Add service-chain variables or constraints for precooling, fresh cold storage, controlled-atmosphere storage, and frozen processing channels."
            ),
        ),
        _check(
            check_id="frozen_loss_proxy",
            name="冷冻损耗代理",
            severity="high" if frozen_loss_proxy_detected else "medium",
            detail=f"frozen_loss_proxy_detected={frozen_loss_proxy_detected}, cold_storage_types={list(cold_types.keys())}",
            evidence="src/models/single_level_mip_v2_1.py; data/params.json",
            claim_boundary=(
                "The current frozen loss assumption is a proxy and should not be treated as a validated okra postharvest loss model."
            ),
            next_action=(
                "Separate fresh-market loss, chilling injury risk, frozen processing quality loss, energy intensity, and market value by storage channel."
            ),
        ),
        _check(
            check_id="objective_dominance",
            name="目标函数成本主导",
            severity="medium" if fixed_operating_share >= 95.0 else "low",
            detail=(
                f"fixed_operating_share={fixed_operating_share:.3f}%, variable_share={variable_share:.3f}%, "
                f"transport={transport_cost:.2f}, loss={loss_cost:.2f}, carbon={carbon_cost:.2f}"
            ),
            evidence="results/baseline_v2_1_report.json",
            claim_boundary=(
                "Current cost results are dominated by fixed and operating cost, so route/loss/carbon tradeoffs are weakly expressed."
            ),
            next_action=(
                "Calibrate transport, loss, carbon, product value, service-level penalties, and unmet-demand costs before claiming robust multi-objective tradeoffs."
            ),
        ),
        _check(
            check_id="scenario_discrimination",
            name="场景/灵敏度区分度",
            severity="medium" if scenario_stable and sensitivity_stable and scenario_spread < 0.01 else "low",
            detail=(
                f"scenario_stable_open_sites={scenario_stable}, sensitivity_stable_open_sites={sensitivity_stable}, "
                f"scenario_cost_spread_pct={scenario_spread:.6f}"
            ),
            evidence="results/analysis_visualization_report.json",
            claim_boundary=(
                "Stability is a current-file observation, not a proof that the model generalizes across real enterprise cases."
            ),
            next_action=(
                "Add v3.0 stress cases with different harvest concentration, road-time matrices, service-channel shares, and facility availability."
            ),
        ),
        _check(
            check_id="real_data_generalization",
            name="真实外部数据泛化",
            severity="high" if ready_for_apply_count == 0 else "medium",
            detail=f"ready_for_apply_count={ready_for_apply_count}, ingestion_state_counts={ingestion.get('state_counts', {}) if isinstance(ingestion, dict) else {}}",
            evidence="results/real_data_sources/real_data_ingestion_validation.json",
            claim_boundary=(
                "Current external data preparation supports schema/readiness claims, not completed real external data ingestion or enterprise validation."
            ),
            next_action=(
                "Download or manually stage official/public raw files, produce cleaned files with required columns, then apply to PostgreSQL after probe_ok=true."
            ),
        ),
        _check(
            check_id="algorithm_claim_boundary",
            name="算法优势边界",
            severity="medium",
            detail="KKT, epsilon, Benders, Benders cut-ranking, and SPO have runnable evidence, but several are smoke/prototype layers.",
            evidence="results/algorithm_evidence_report.json; results/experiments/benchmark_benders_comparison/ai_active_validation.json",
            claim_boundary=(
                "The project can claim runnable algorithm prototypes and AI-active cut-selection evidence, not statistically established Benders cut-ranking superiority."
            ),
            next_action=(
                "Expand benchmark instances, record classic-vs-AI active cut budgets, and compare gap/runtime curves before making acceleration claims."
            ),
        ),
    ]

    high_risk_count = sum(1 for item in checks if item["severity"] == "high")
    medium_risk_count = sum(1 for item in checks if item["severity"] == "medium")
    top_risks = sorted(checks, key=lambda item: _severity_rank(item["severity"]), reverse=True)

    return {
        "source_name": "model realism audit",
        "source_backend": "current_files_read_only",
        "result_paths": {
            "json": str(MODEL_REALISM_AUDIT_JSON_PATH),
            "md": str(MODEL_REALISM_AUDIT_MD_PATH),
            "nodes_csv": str(NODES_CSV),
            "params_json": str(PARAMS_JSON),
            "baseline_report": str(BASELINE_REPORT_JSON),
            "analysis_visualization_report": str(ANALYSIS_VISUALIZATION_JSON),
            "ingestion_validation": str(INGESTION_VALIDATION_JSON),
            "model_source": str(MODEL_SOURCE),
        },
        "summary": {
            "node_count": len(nodes),
            "candidate_count": candidate_count,
            "demand_node_count": demand_node_count,
            "total_annual_production_ton": total_production,
            "baseline_facility_count": len(facilities),
            "baseline_capacity_ton": total_capacity,
            "baseline_assigned_demand_ton": assigned_demand,
            "capacity_to_annual_production_ratio": annual_capacity_ratio,
            "assigned_to_capacity_ratio": assigned_capacity_ratio,
            "selected_storage_types": unique_storage_types,
            "frozen_facility_share_pct": frozen_share,
            "fixed_operating_cost_share_pct": fixed_operating_share,
            "variable_cost_share_pct": variable_share,
            "scenario_cost_spread_pct": scenario_spread,
            "scenario_stable_open_sites": scenario_stable,
            "sensitivity_all_groups_stable_open_sites": sensitivity_stable,
            "real_external_ready_for_apply_count": ready_for_apply_count,
            "high_risk_count": high_risk_count,
            "medium_risk_count": medium_risk_count,
            "readiness_state": "needs_model_v3_before_strong_claims" if high_risk_count else "caution_ready",
        },
        "checks": checks,
        "top_risks": top_risks[:3],
        "v3_actions": [
            "Replace annual-volume capacity proxy with peak-inventory/throughput semantics.",
            "Add temperature-chain or channel-share constraints so precooling, cold storage, CA storage, and frozen processing have distinct roles.",
            "Recalibrate loss, carbon, market value, and energy parameters with literature-backed or real external data.",
            "Create stress scenarios that change harvest concentration, service mix, road travel time, and demand nodes.",
            "Only after v3.0 reruns should manuscript claims move from baseline feasibility to robust decision support.",
        ],
        "claim_boundaries": [
            "v2.1 is a useful exact-MIP baseline and engineering scaffold.",
            "v2.1 is not yet the final paper model for okra cold-chain service-chain decisions.",
            "Current stability results are local to existing parameters and files.",
            "Enterprise-grade claims require real external data ingestion, PostgreSQL-backed operation, and broader scenario validation.",
        ],
        "research_boundary": (
            "This audit is a scientific quality gate built from current project files. It does not rerun optimization; "
            "it identifies which current conclusions are safe and which require a v3.0 model before strong paper or enterprise claims."
        ),
    }


def write_model_realism_audit(report: Dict[str, Any], out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "model_realism_audit.json"
    md_path = destination / "model_realism_audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Model Realism Audit",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Checks",
                "",
                *[
                    (
                        f"- {item.get('id')}: severity={item.get('severity')}, "
                        f"state={item.get('state')}, detail={item.get('detail')}"
                    )
                    for item in report.get("checks", [])
                ],
                "",
                "## V3 Actions",
                "",
                *[f"- {item}" for item in report.get("v3_actions", [])],
                "",
                "## Claim Boundaries",
                "",
                *[f"- {item}" for item in report.get("claim_boundaries", [])],
                "",
                "## Research Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}
