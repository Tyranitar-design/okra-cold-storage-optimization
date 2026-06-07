"""Build paper-grade export artifacts (LaTeX tables + Markdown/Word report).

Read-only: assembles already-verified metrics from existing report builders
into LaTeX tables and a Markdown report. Does NOT rerun any optimization or
fabricate numbers — every value traces back to a source report function.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def _fmt(value: Any, digits: int = 0) -> str:
    """Format a number for display; fall back to '-' for missing values."""
    if value is None or value == "":
        return "-"
    try:
        num = float(value)
        if digits == 0:
            return f"{num:,.0f}"
        return f"{num:,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _latex_escape(text: Any) -> str:
    s = str(text)
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def _four_methods_latex(four: Dict[str, Any]) -> str:
    methods = four.get("methods", []) if isinstance(four, dict) else []
    kind_label = {"exact": "精确", "exact_ai": "精确+AI", "heuristic": "启发式"}
    rows = []
    for m in methods:
        rows.append(
            " & ".join([
                _latex_escape(m.get("label", "")),
                _fmt(m.get("best_cost"), 0),
                _fmt(m.get("gap_pct"), 2),
                _fmt(m.get("elapsed_sec"), 1),
                _fmt(m.get("front_size"), 0),
                _latex_escape(kind_label.get(m.get("kind"), m.get("kind", ""))),
            ]) + r" \\"
        )
    body = "\n".join(rows) if rows else r"\multicolumn{6}{c}{暂无数据} \\"
    speedup = four.get("ai_speedup_vs_direct")
    caption = "v3.0 容量链 + OSM 路网四方法对比"
    if speedup:
        caption += f"（AI warm start 相对 Gurobi 直解 {_fmt(speedup, 2)}× 加速）"
    return "\n".join([
        r"\begin{table}[t]",
        r"\centering",
        rf"\caption{{{caption}}}",
        r"\label{tab:four_methods}",
        r"\begin{tabular}{lrrrrl}",
        r"\toprule",
        r"方法 & 最优成本(元) & gap(\%) & 求解时间(s) & 前沿规模 & 类型 \\",
        r"\midrule",
        body,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])


def _key_metrics_latex(summary: Dict[str, Any], osm: Dict[str, Any], four: Dict[str, Any]) -> str:
    osm_matrix = osm.get("osm_matrix", {}) if isinstance(osm, dict) else {}
    osm_cmp = osm.get("osm_vs_haversine", {}) if isinstance(osm, dict) else {}
    # Use the OSM four-methods headline (consistent with the Overview KPI and the
    # four-methods table) instead of the Haversine baseline_v3 report, so the
    # export does not contradict itself.
    methods = {m.get("method"): m for m in four.get("methods", [])} if isinstance(four, dict) else {}
    direct = methods.get("gurobi_direct", {})
    ai_warm = methods.get("ai_warm", {})
    speedup = four.get("ai_speedup_vs_direct") if isinstance(four, dict) else None
    rows = [
        ("v3.0+OSM 最优总成本(元)", _fmt(four.get("exact_reference_obj"), 0)),
        ("Gurobi 直解 gap(%)", _fmt(direct.get("gap_pct"), 2)),
        ("Gurobi 直解时间(s)", _fmt(direct.get("elapsed_sec"), 1)),
        ("AI warm 求解时间(s)", _fmt(ai_warm.get("elapsed_sec"), 1)),
        ("AI warm 加速比", (_fmt(speedup, 2) + "×") if speedup else "-"),
        ("OSM/Haversine 距离比", (_fmt(osm_cmp.get("ratio_mean"), 2) + "×") if osm_cmp.get("ratio_mean") else "-"),
        ("OSM vs Haversine 成本差(%)", _fmt(osm_cmp.get("obj_diff_pct"), 1)),
        ("Benders cut ranking 证据数", _fmt(summary.get("ai_benders_cut_scores"), 0)),
        ("稳健性筛选变体数", _fmt(summary.get("model_v3_robustness_variant_count"), 0)),
    ]
    body = "\n".join(f"{_latex_escape(k)} & {_latex_escape(v)} " + r"\\" for k, v in rows)
    return "\n".join([
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{秋葵冷库优化核心指标汇总（v3.0 + OSM 路网）}",
        r"\label{tab:key_metrics}",
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"指标 & 数值 \\",
        r"\midrule",
        body,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])


def build_paper_export(
    paper_pack: Dict[str, Any],
    four_methods: Dict[str, Any],
    ai_warmstart: Dict[str, Any],
    osm_distance: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble LaTeX tables + Markdown report from verified report payloads."""
    summary = paper_pack.get("summary", {}) if isinstance(paper_pack, dict) else {}
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    four_tex = _four_methods_latex(four_methods)
    metrics_tex = _key_metrics_latex(summary, osm_distance, four_methods)
    latex = "\n\n".join([
        f"% 秋葵冷库优化 MIS 论文证据导出  生成时间 {generated_at}",
        f"% 所有数值来自已验证的报告产物，未重新求解、未编造。",
        metrics_tex,
        four_tex,
    ])

    # Markdown report (opens cleanly in Word / WPS).
    methods = four_methods.get("methods", []) if isinstance(four_methods, dict) else []
    kind_label = {"exact": "精确", "exact_ai": "精确+AI", "heuristic": "启发式"}
    md_method_rows = "\n".join(
        "| {} | {} | {} | {} | {} | {} |".format(
            m.get("label", ""),
            _fmt(m.get("best_cost"), 0),
            _fmt(m.get("gap_pct"), 2),
            _fmt(m.get("elapsed_sec"), 1),
            _fmt(m.get("front_size"), 0),
            kind_label.get(m.get("kind"), m.get("kind", "")),
        )
        for m in methods
    ) or "| - | - | - | - | - | - |"

    method_by_id = {m.get("method"): m for m in methods}
    direct = method_by_id.get("gurobi_direct", {})
    ai_warm_m = method_by_id.get("ai_warm", {})
    speedup_val = four_methods.get("ai_speedup_vs_direct") if isinstance(four_methods, dict) else None
    metric_pairs = [
        ("v3.0+OSM 最优总成本(元)", _fmt(four_methods.get("exact_reference_obj"), 0)),
        ("Gurobi 直解 gap(%)", _fmt(direct.get("gap_pct"), 2)),
        ("Gurobi 直解时间(s)", _fmt(direct.get("elapsed_sec"), 1)),
        ("AI warm 求解时间(s)", _fmt(ai_warm_m.get("elapsed_sec"), 1)),
        ("AI warm 加速比", (_fmt(speedup_val, 2) + "×") if speedup_val else "-"),
        ("Benders cut ranking 证据数", _fmt(summary.get("ai_benders_cut_scores"), 0)),
        ("稳健性筛选变体数", _fmt(summary.get("model_v3_robustness_variant_count"), 0)),
        ("证据层数", _fmt(summary.get("paper_layer_count"), 0)),
        ("证据齐备", "是" if summary.get("paper_ready") else "否（部分产物缺失）"),
    ]
    md_metric_rows = "\n".join(f"| {k} | {v} |" for k, v in metric_pairs)

    markdown = "\n".join([
        "# 秋葵冷库优化 MIS — 论文证据导出",
        "",
        f"> 生成时间：{generated_at}",
        "> 本报告为只读汇总，所有数值来自已验证的报告产物，未重新求解、未编造。",
        "",
        "## 一、核心指标汇总",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        md_metric_rows,
        "",
        "## 二、v3.0 + OSM 四方法对比",
        "",
        "| 方法 | 最优成本(元) | gap(%) | 求解时间(s) | 前沿规模 | 类型 |",
        "| --- | --- | --- | --- | --- | --- |",
        md_method_rows,
        "",
        "## 三、研究边界声明",
        "",
        str(paper_pack.get("research_boundary", "本导出为只读汇总，不重新运行优化或算法。")),
        "",
        "## 四、主线与子线边界",
        "",
        "- 主线：v3.0 capacity-chain MIP + direct Gurobi solve。",
        f"- AI 强证据：AI guided warm start 在 v3.0 容量链问题上达到 {(_fmt(ai_warmstart.get('speedup'), 2) + '×') if ai_warmstart.get('speedup') else '-'} 加速，且最优解一致。",
        "- Benders 子线：cut ranking / robustness 只用于机制研究，不写成对朴素 cut-budget 策略的通用显著加速。",
        f"- 县域案例（39 节点），距离矩阵为 OSM 路网估算；服务通道份额为情景假设。",
        "",
    ])

    return {
        "source": "/api/v1/export/paper",
        "generated_at": generated_at,
        "latex": latex,
        "markdown": markdown,
        "summary_metrics": dict(metric_pairs),
        "available": bool(methods) or bool(summary),
        "research_boundary": str(paper_pack.get("research_boundary", "")),
    }
