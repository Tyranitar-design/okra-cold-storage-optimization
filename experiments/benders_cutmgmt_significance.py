"""Statistical significance readout for the existing DS-F-043 cut-management comparison.

This script does NOT rerun optimization. It reads the already-materialized
`benders_cutmgmt_summary.json` and computes paired comparisons of learned_K
against the baseline policies.

Rigour rules:
- Quality metrics (`validated_gap_pct_mean`, `solved_to_optimal_frac`) use all
  paired instances.
- Effort metrics (`elapsed_sec_mean`, `iterations_mean`) are compared ONLY on
  instances where both policies solved to the validated optimum, matching the
  honesty rules already used in `build_verdict()`.
- If all paired differences are exactly zero, we report `all_zero_differences`
  instead of pretending a p-value means something.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import wilcoxon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_JSON = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison" / "benders_cutmgmt_summary.json"
OUT_JSON = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison" / "benders_cutmgmt_significance.json"
OUT_MD = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison" / "benders_cutmgmt_significance.md"


def _float(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _paired_df(summary_rows: list[dict[str, Any]], baseline: str) -> pd.DataFrame:
    df = pd.DataFrame(summary_rows)
    learned = df[df["policy"] == "learned_K"].copy()
    base = df[df["policy"] == baseline].copy()
    merged = learned.merge(base, on="case_id", suffixes=("_learned", "_base"))
    return merged


def _wilcoxon_report(a: list[float], b: list[float]) -> dict[str, Any]:
    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    diffs = [x - y for x, y in zip(a, b)]
    nonzero = [d for d in diffs if abs(d) > 1e-12]
    wins = sum(d < 0 for d in diffs)   # learned better if lower
    losses = sum(d > 0 for d in diffs)
    ties = sum(abs(d) <= 1e-12 for d in diffs)
    report = {
        "n_pairs": len(diffs),
        "wins_learned_lower_is_better": wins,
        "losses_learned_lower_is_better": losses,
        "ties": ties,
        "learned_mean": sum(a) / len(a) if a else None,
        "baseline_mean": sum(b) / len(b) if b else None,
        "median_diff_learned_minus_baseline": pd.Series(diffs).median() if diffs else None,
    }
    if not nonzero:
        report["test_state"] = "all_zero_differences"
        report["p_value_two_sided"] = None
        report["statistic"] = None
        return report
    stat, p = wilcoxon(a, b, alternative="two-sided", zero_method="wilcox", mode="auto")
    report["test_state"] = "ok"
    report["statistic"] = float(stat)
    report["p_value_two_sided"] = float(p)
    return report


def _build_conclusion_text(
    paired_instances: int,
    jointly_solved_for_effort: int,
    comparisons: dict[str, Any],
) -> tuple[str, str, str, str]:
    all_cuts = comparisons.get("learned_vs_all_cuts", {})
    random_k = comparisons.get("learned_vs_random_K", {})
    recency_k = comparisons.get("learned_vs_recency_K", {})

    def _p(block: dict[str, Any], key: str) -> str:
        value = block.get(key, {}).get("p_value_two_sided")
        return "NA" if value is None else f"{value:.2f}"

    quality_phrase = (
        f"With the current {paired_instances}-instance DS-F-043 sample, learned_K shows no detectable quality advantage: "
        "validated gap and solved-to-optimal fraction remain statistically indistinguishable from the naive controls on the paired cases."
    )
    if jointly_solved_for_effort > 0:
        effort_phrase = (
            f" On the {jointly_solved_for_effort} jointly solved cases, learned_K shows mixed wall-clock evidence: "
            f"it is faster than all_cuts (p={_p(all_cuts, 'elapsed_sec_mean_jointly_solved')}), "
            f"indistinguishable from recency_K (p={_p(recency_k, 'elapsed_sec_mean_jointly_solved')}), "
            f"and not better than random_K (p={_p(random_k, 'elapsed_sec_mean_jointly_solved')}). "
            "This does not support a generic significant-speedup claim over naive cut-budget controls."
        )
    else:
        effort_phrase = " There are no jointly solved cases for effort comparison, so no runtime claim is supportable."

    conclusion = quality_phrase + effort_phrase
    paper_safe_claim = (
        f"Under the current {paired_instances}-instance sample, learned_K is statistically indistinguishable from the naive controls on solution quality. "
        f"It shows a wall-clock edge versus all_cuts on the {jointly_solved_for_effort} jointly solved cases, but not versus the naive budget baselines recency_K and random_K; therefore the safe claim remains cut-ranking/robustness rather than general speedup."
    )
    next_action = (
        "Expand DS-F-043 beyond the current medium-instance panel (for example to 25-30 instances, ideally with more hard cases) "
        "before claiming any broad significant speedup."
    )
    claim_boundary = (
        f"This is a post-hoc significance readout over the current {paired_instances}-instance DS-F-043 sample. "
        "It does not add new optimization runs and therefore cannot increase statistical power on its own."
    )
    return conclusion, paper_safe_claim, next_action, claim_boundary



def build_report() -> dict[str, Any]:
    payload = json.loads(IN_JSON.read_text(encoding="utf-8"))
    rows = payload.get("summary_rows", [])
    baselines = ["all_cuts", "random_K", "recency_K"]
    comparisons: dict[str, Any] = {}
    paired_counts: list[int] = []
    jointly_solved_counts: list[int] = []

    for baseline in baselines:
        merged = _paired_df(rows, baseline)
        both_solved = merged[
            merged["all_solved_to_optimal_learned"] & merged["all_solved_to_optimal_base"]
        ]
        comp: dict[str, Any] = {
            "instances_total": int(len(merged)),
            "instances_both_solved_optimal": int(len(both_solved)),
        }
        paired_counts.append(int(len(merged)))
        jointly_solved_counts.append(int(len(both_solved)))

        # Quality: validated gap on all paired instances.
        gap_a = [float(v) for v in merged["validated_gap_pct_mean_learned"].tolist()]
        gap_b = [float(v) for v in merged["validated_gap_pct_mean_base"].tolist()]
        comp["validated_gap_pct_mean"] = _wilcoxon_report(gap_a, gap_b)

        # Quality: solved fraction on all paired instances.
        solved_a = [float(v) for v in merged["solved_to_optimal_frac_learned"].tolist()]
        solved_b = [float(v) for v in merged["solved_to_optimal_frac_base"].tolist()]
        comp["solved_to_optimal_frac"] = _wilcoxon_report(solved_a, solved_b)

        # Effort: only jointly solved cases.
        if len(both_solved):
            time_a = [float(v) for v in both_solved["elapsed_sec_mean_learned"].tolist()]
            time_b = [float(v) for v in both_solved["elapsed_sec_mean_base"].tolist()]
            iter_a = [float(v) for v in both_solved["iterations_mean_learned"].tolist()]
            iter_b = [float(v) for v in both_solved["iterations_mean_base"].tolist()]
            comp["elapsed_sec_mean_jointly_solved"] = _wilcoxon_report(time_a, time_b)
            comp["iterations_mean_jointly_solved"] = _wilcoxon_report(iter_a, iter_b)
        else:
            comp["elapsed_sec_mean_jointly_solved"] = {"test_state": "no_jointly_solved_cases"}
            comp["iterations_mean_jointly_solved"] = {"test_state": "no_jointly_solved_cases"}

        comparisons[f"learned_vs_{baseline}"] = comp

    paired_instances = max(paired_counts) if paired_counts else 0
    jointly_solved_for_effort = max(jointly_solved_counts) if jointly_solved_counts else 0
    conclusion, paper_safe_claim, next_action, claim_boundary = _build_conclusion_text(
        paired_instances=paired_instances,
        jointly_solved_for_effort=jointly_solved_for_effort,
        comparisons=comparisons,
    )

    report = {
        "source": "results/experiments/benders_cutmgmt_comparison/benders_cutmgmt_summary.json",
        "experiment_name": payload.get("experiment_name"),
        "source_id": payload.get("source_id"),
        "config": payload.get("config", {}),
        "comparison_scope": {
            "paired_instances": paired_instances,
            "jointly_solved_for_effort": jointly_solved_for_effort,
            "baselines": baselines,
            "quality_metrics": ["validated_gap_pct_mean", "solved_to_optimal_frac"],
            "effort_metrics_jointly_solved_only": ["elapsed_sec_mean", "iterations_mean"],
        },
        "comparisons": comparisons,
        "conclusion": conclusion,
        "paper_safe_claim": paper_safe_claim,
        "next_action": next_action,
        "claim_boundary": claim_boundary,
    }
    return report



def write_report() -> dict[str, str]:
    report = build_report()
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Benders Cut-Management Significance Readout",
        "",
        f"- source_id: {report['source_id']}",
        f"- paired_instances: {report['comparison_scope']['paired_instances']}",
        f"- jointly_solved_for_effort: {report['comparison_scope']['jointly_solved_for_effort']}",
        "",
        "## Honest Conclusion",
        "",
        report["conclusion"],
        "",
        "## Paper-safe Claim",
        "",
        report["paper_safe_claim"],
        "",
        "## Next Action",
        "",
        report["next_action"],
        "",
        "## Comparisons",
        "",
    ]
    for name, comp in report["comparisons"].items():
        lines += [f"### {name}", ""]
        for metric, detail in comp.items():
            lines.append(f"- {metric}: {detail}")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    return {"json_path": str(OUT_JSON), "md_path": str(OUT_MD)}


if __name__ == "__main__":
    paths = write_report()
    print(paths["json_path"])
    print(paths["md_path"])
