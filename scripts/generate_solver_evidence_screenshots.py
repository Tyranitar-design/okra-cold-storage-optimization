from __future__ import annotations

import csv
import hashlib
import json
import math
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"D:\秋葵冷库优化项目")
OUT_DIR = ROOT / "SRT项目文件" / "python求解结果截图"
INDEX_MD = OUT_DIR / "求解结果截图索引.md"


def load_json(rel_path: str) -> dict[str, Any]:
    path = ROOT / rel_path
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv_rows(rel_path: str) -> list[dict[str, str]]:
    path = ROOT / rel_path
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256_short(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def fmt_num(value: Any, digits: int = 2) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{x:,.{digits}f}"


def fmt_pct(value: Any, digits: int = 4) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{x:.{digits}f}%"


def fmt_sec(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "NA"
    if x >= 60:
        return f"{x:.2f}s ({x / 60:.2f} min)"
    return f"{x:.2f}s"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\consolab.ttf" if bold else r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\CascadiaMono.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap_terminal_line(text: str, width: int = 118) -> list[str]:
    if len(text) <= width:
        return [text]
    prefix = ""
    for marker in ("$ ", ">> ", "[OK] ", "[WARN] ", "[INFO] ", "  "):
        if text.startswith(marker):
            prefix = " " * len(marker)
            break
    wrapped = textwrap.wrap(text, width=width, break_long_words=False, replace_whitespace=False)
    if len(wrapped) <= 1:
        return wrapped
    return [wrapped[0], *[prefix + part for part in wrapped[1:]]]


def render_card(
    filename: str,
    title: str,
    command: str,
    source_rel: str,
    lines: list[tuple[str, str]],
    boundary: str,
) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source_path = ROOT / source_rel
    source_meta = [
        ("info", f"source: {source_rel}"),
        ("info", f"mtime: {mtime(source_path)}"),
        ("info", f"sha256: {sha256_short(source_path)}"),
        ("dim", "mode: evidence replay from existing Python result artifact; no recomputation"),
    ]

    all_lines: list[tuple[str, str]] = [
        ("cmd", f"$ {command}"),
        ("blank", ""),
        *source_meta,
        ("blank", ""),
        *lines,
        ("blank", ""),
        ("warn", f"boundary: {boundary}"),
    ]

    font = get_font(24)
    bold_font = get_font(24, bold=True)
    title_font = get_font(34, bold=True)
    small_font = get_font(20)
    line_h = 34
    wrapped: list[tuple[str, str]] = []
    for kind, text in all_lines:
        if not text:
            wrapped.append((kind, ""))
            continue
        for part in wrap_terminal_line(text):
            wrapped.append((kind, part))

    width = 1680
    height = 170 + max(1, len(wrapped)) * line_h + 56
    image = Image.new("RGB", (width, height), "#0f172a")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=18, fill="#111827", outline="#334155", width=2)
    draw.rounded_rectangle((24, 24, width - 24, 92), radius=18, fill="#1f2937", outline="#334155", width=2)
    for idx, color in enumerate(("#ef4444", "#f59e0b", "#22c55e")):
        draw.ellipse((52 + idx * 34, 50, 72 + idx * 34, 70), fill=color)
    draw.text((170, 43), title, fill="#e5e7eb", font=title_font)
    draw.text((width - 360, 52), "Python Solver Evidence", fill="#94a3b8", font=small_font)

    colors = {
        "cmd": "#93c5fd",
        "info": "#cbd5e1",
        "ok": "#86efac",
        "warn": "#fde68a",
        "dim": "#94a3b8",
        "metric": "#f8fafc",
        "blank": "#f8fafc",
    }
    y = 118
    for kind, text in wrapped:
        if not text:
            y += int(line_h * 0.45)
            continue
        use_font = bold_font if kind in {"cmd", "ok", "metric"} else font
        draw.text((58, y), text, fill=colors.get(kind, "#e5e7eb"), font=use_font)
        y += line_h

    out_path = OUT_DIR / filename
    image.save(out_path, quality=95)
    return out_path


def build_cards() -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []

    direct_rel = r"results\experiments\v3_four_methods\v3_four_methods_summary.json"
    direct_summary = load_json(direct_rel)
    direct = direct_summary.get("results", {}).get("gurobi_direct", {})
    ai_warm_same_run = direct_summary.get("results", {}).get("ai_warm", {})
    cards.append(
        {
            "title": "01 Gurobi Direct Mainline Result",
            "path": str(
                render_card(
                    "01_gurobi_direct_mainline_terminal.png",
                    "01 Gurobi Direct Mainline Result",
                    "python experiments/v3_four_methods.py",
                    direct_rel,
                    [
                        ("ok", f"[OK] method={direct.get('label')} status={direct.get('status')} solved_to_tol={direct.get('solved_to_tol')}"),
                        ("metric", f"objective={fmt_num(direct.get('objective'))}  bound={fmt_num(direct.get('bound'))}  mip_gap={fmt_pct(direct.get('mip_gap_pct'))}"),
                        ("metric", f"elapsed={fmt_sec(direct.get('elapsed_sec'))}  exact_reference_obj={fmt_num(direct_summary.get('exact_reference_obj'))}"),
                        ("metric", f"same-file AI warm objective={fmt_num(ai_warm_same_run.get('objective'))}  elapsed={fmt_sec(ai_warm_same_run.get('elapsed_sec'))}  speedup={fmt_num(float(direct.get('elapsed_sec', 0)) / max(float(ai_warm_same_run.get('elapsed_sec', 1)), 1e-9), 2)}x"),
                        ("info", f"model={direct_summary.get('config', {}).get('model')} distance_matrix={direct_summary.get('config', {}).get('distance_matrix')} time_limit={direct_summary.get('config', {}).get('exact_time_limit')}s"),
                    ],
                    "This is the main report Gurobi-direct baseline matched with AI warm start; not the separate gap-closure scenario artifact.",
                )
            ),
            "source": direct_rel,
            "insert": "Main Gurobi direct evidence, before AI warm start comparison.",
        }
    )

    warm_rel = r"results\experiments\ai_warmstart_v3\ai_warmstart_summary.json"
    warm = load_json(warm_rel)
    cold = warm.get("cold_start", {})
    ai = warm.get("ai_warm", {})
    cards.append(
        {
            "title": "02 AI Warm Start Standalone Run",
            "path": str(
                render_card(
                    "02_ai_warmstart_v3_terminal.png",
                    "02 AI Warm Start Standalone Run",
                    "python experiments/ai_warmstart_v3.py",
                    warm_rel,
                    [
                        ("ok", f"[OK] cold_status={cold.get('status')} warm_status={ai.get('status')} solved_to_tol={ai.get('solved_to_tol')}"),
                        ("metric", f"cold: objective={fmt_num(cold.get('objective'))} gap={fmt_pct(cold.get('mip_gap_pct'))} elapsed={fmt_sec(cold.get('elapsed_sec'))}"),
                        ("metric", f"warm: objective={fmt_num(ai.get('objective'))} gap={fmt_pct(ai.get('mip_gap_pct'))} elapsed={fmt_sec(ai.get('elapsed_sec'))}"),
                        ("metric", f"speedup={fmt_num(warm.get('ai_vs_cold_speedup'), 2)}x  warm_sites={', '.join(ai.get('warm_sites', [])[:8])}"),
                        ("info", f"training_runs={warm.get('training', {}).get('n_runs_used')} features={warm.get('training', {}).get('n_features')} positive_labels={warm.get('training', {}).get('n_positive')}"),
                    ],
                    "AI only seeds Gurobi search; Gurobi remains responsible for feasibility and gap certification.",
                )
            ),
            "source": warm_rel,
            "insert": "Section 4.3 or appendix evidence for AI warm start.",
        }
    )

    opt_rel = r"results\experiments\ai_warmstart_optuna\ai_warmstart_optuna_summary.json"
    opt = load_json(opt_rel)
    best = opt.get("best_trial", {})
    cards.append(
        {
            "title": "03 Optuna AI Warm Start Search",
            "path": str(
                render_card(
                    "03_optuna_warmstart_terminal.png",
                    "03 Optuna AI Warm Start Search",
                    "python experiments/ai_warmstart_optuna.py --fresh --n-trials 24 --timeout 7200",
                    opt_rel,
                    [
                        ("ok", f"[OK] single_trials={opt.get('single_trial_complete_count')}/{opt.get('single_trial_count')} multi_trials={opt.get('multi_trial_complete_count')}/{opt.get('multi_trial_count')}"),
                        ("metric", f"best_trial=#{best.get('number')} elapsed={fmt_sec(best.get('elapsed_sec'))} gap={fmt_pct(best.get('gap_pct'))} speedup={fmt_num(best.get('speedup_vs_cold'), 4)}x"),
                        ("metric", f"objective={fmt_num(best.get('objective'))} objective_consistent={best.get('objective_consistent')} solved_to_tol={best.get('solved_to_tol')}"),
                        ("metric", f"strategy={best.get('warm_strategy_label')} top_k={best.get('params', {}).get('top_k')} historical_best={fmt_num(opt.get('historical_best_speedup'), 2)}x exceeded={opt.get('exceeds_historical_best')}"),
                        ("info", "top_sites=" + ", ".join(best.get("top_sites", []))),
                    ],
                    "Optuna tunes warm-start and selected Gurobi parameters; it does not replace exact optimization.",
                )
            ),
            "source": opt_rel,
            "insert": "Section 4.6 Optuna, or appendix evidence.",
        }
    )

    exact_rel = r"results\experiments\exact_vs_heuristic\exact_vs_heuristic_summary.json"
    exact = load_json(exact_rel)
    verdict = exact.get("verdict", {})
    gaps = verdict.get("mean_cost_gap_vs_exact_pct", {})
    hvs = verdict.get("mean_hypervolume_ratio_vs_exact", {})
    rt = verdict.get("mean_runtime_sec", {})
    cards.append(
        {
            "title": "04 Exact Epsilon vs NSGA-III and ALNS",
            "path": str(
                render_card(
                    "04_exact_vs_heuristic_terminal.png",
                    "04 Exact Epsilon vs NSGA-III and ALNS",
                    "python experiments/exact_vs_heuristic.py",
                    exact_rel,
                    [
                        ("ok", f"[OK] scenarios={', '.join(exact.get('config', {}).get('scenarios', []))} seeds={exact.get('config', {}).get('seeds')}"),
                        ("metric", f"NSGA-III: mean_cost_gap={fmt_pct(gaps.get('nsga3'))} hypervolume_ratio={fmt_num(hvs.get('nsga3'), 3)} runtime={fmt_sec(rt.get('nsga3'))}"),
                        ("metric", f"ALNS:     mean_cost_gap={fmt_pct(gaps.get('alns'))} hypervolume_ratio={fmt_num(hvs.get('alns'), 3)} runtime={fmt_sec(rt.get('alns'))}"),
                        ("metric", f"Exact epsilon: runtime={fmt_sec(rt.get('exact_epsilon'))} hypervolume_ratio=1.000 certified_frontier"),
                        ("info", f"grid={exact.get('config', {}).get('n_grid')} nsga_pop={exact.get('config', {}).get('nsga_pop')} nsga_gen={exact.get('config', {}).get('nsga_gen')} alns_iters={exact.get('config', {}).get('alns_iters')}"),
                    ],
                    "Hypervolume comparisons are relative to the shared reference point and county-scale scenario.",
                )
            ),
            "source": exact_rel,
            "insert": "Section 4.5 or experiment-results appendix.",
        }
    )

    cut_rel = r"results\experiments\benders_cutmgmt_comparison\benders_cutmgmt_summary.json"
    cut = load_json(cut_rel)
    q = cut.get("verdict", {}).get("quality", {})
    findings = cut.get("verdict", {}).get("findings", {})
    cards.append(
        {
            "title": "05 Benders Cut Management Ablation",
            "path": str(
                render_card(
                    "05_benders_cutmgmt_terminal.png",
                    "05 Benders Cut Management Ablation",
                    "python experiments/benders_cutmgmt_comparison.py",
                    cut_rel,
                    [
                        ("ok", f"[OK] source_id={cut.get('source_id')} policies={', '.join(cut.get('policies', []))} instances={len(cut.get('config', {}).get('instances', []))}"),
                        ("metric", f"all_cuts: solved={q.get('all_cuts', {}).get('all_solved_to_optimal_count')}/{q.get('all_cuts', {}).get('instances')} mean_gap={fmt_pct(q.get('all_cuts', {}).get('mean_validated_gap_pct'))}"),
                        ("metric", f"learned_K: solved={q.get('learned_K', {}).get('all_solved_to_optimal_count')}/{q.get('learned_K', {}).get('instances')} mean_gap={fmt_pct(q.get('learned_K', {}).get('mean_validated_gap_pct'))}"),
                        ("metric", f"recency_K: solved={q.get('recency_K', {}).get('all_solved_to_optimal_count')}/{q.get('recency_K', {}).get('instances')}  random_K: solved={q.get('random_K', {}).get('all_solved_to_optimal_count')}/{q.get('random_K', {}).get('instances')}"),
                        ("info", f"conclusion={cut.get('verdict', {}).get('conclusion')} recommendation={findings.get('practical_recommendation', '')[:110]}"),
                    ],
                    "Supports cut prioritisation / robustness evidence, not universal AI-Benders acceleration.",
                )
            ),
            "source": cut_rel,
            "insert": "Section 4.4 Benders evidence, or appendix.",
        }
    )

    ab_rel = r"results\experiments\ai_benders_comparison\ai_benders_comparison_summary.json"
    ab = load_json(ab_rel)
    cut_scores = ab.get("cut_score_rows", [])
    rows = ab.get("summary_rows", [])
    case_count = len(ab.get("cases", []))
    ai_rows = [r for r in rows if r.get("method") == "ai_benders"]
    classic_rows = [r for r in rows if r.get("method") == "classic_benders"]
    max_ai = max(ai_rows, key=lambda r: float(r.get("upper_bound", 0))) if ai_rows else {}
    cards.append(
        {
            "title": "06 AI-Benders Cut Score Prototype",
            "path": str(
                render_card(
                    "06_ai_benders_comparison_terminal.png",
                    "06 AI-Benders Cut Score Prototype",
                    "python experiments/ai_benders_comparison.py",
                    ab_rel,
                    [
                        ("ok", f"[OK] cases={case_count} methods=classic_benders, ai_benders cut_score_rows={len(cut_scores)}"),
                        ("metric", f"classic_rows={len(classic_rows)} ai_rows={len(ai_rows)} selected_cut_rows={sum(1 for r in cut_scores if str(r.get('selected')).lower() == 'true')}"),
                        ("metric", f"largest_ai_case={max_ai.get('case_id')} upper_bound={fmt_num(max_ai.get('upper_bound'))} final_gap={fmt_pct(max_ai.get('final_gap_pct'))} cuts={max_ai.get('cut_count')}"),
                        ("info", "selected_cuts=" + ", ".join(f"{r.get('case_id')}:{r.get('cut_id')}" for r in cut_scores if str(r.get('selected')).lower() == "true")),
                        ("info", "output_csv=" + str(ab.get("files", {}).get("csv", ""))),
                    ],
                    "Controlled small-to-medium prototype; not a full benchmark superiority proof.",
                )
            ),
            "source": ab_rel,
            "insert": "Appendix evidence for AI-Benders mechanism details.",
        }
    )

    luxi_rel = r"results\experiments\luxi_warmstart\luxi_warmstart_summary.json"
    luxi = load_json(luxi_rel)
    luxi_cold = luxi.get("cold_start", {})
    luxi_ai = luxi.get("ai_warm", {})
    cards.append(
        {
            "title": "07 Luxi Cross-Region Warm Start Validation",
            "path": str(
                render_card(
                    "07_luxi_warmstart_terminal.png",
                    "07 Luxi Cross-Region Warm Start Validation",
                    "python experiments/luxi_warmstart.py",
                    luxi_rel,
                    [
                        ("ok", f"[OK] case={luxi.get('case')} nodes={luxi.get('data', {}).get('nodes')} candidates={luxi.get('data', {}).get('candidates')}"),
                        ("metric", f"cold: objective={fmt_num(luxi_cold.get('objective'))} gap={fmt_pct(luxi_cold.get('mip_gap_pct'))} elapsed={fmt_sec(luxi_cold.get('elapsed_sec'))}"),
                        ("metric", f"warm: objective={fmt_num(luxi_ai.get('objective'))} gap={fmt_pct(luxi_ai.get('mip_gap_pct'))} elapsed={fmt_sec(luxi_ai.get('elapsed_sec'))}"),
                        ("metric", f"recommended_speedup={fmt_num(luxi.get('recommended_speedup'), 2)}x top_k={luxi.get('config', {}).get('top_k')} distance_source={luxi.get('data', {}).get('distance_source')}"),
                        ("info", "ai_top_k=" + ", ".join(luxi.get("ai_top_k", []))),
                    ],
                    "Cross-region validation uses Haversine + detour distance, not OSM; not enterprise deployment proof.",
                )
            ),
            "source": luxi_rel,
            "insert": "Results section or appendix for cross-region validation.",
        }
    )

    return cards


def build_contact_sheet(cards: list[dict[str, str]]) -> Path:
    thumbs: list[tuple[dict[str, str], Image.Image]] = []
    for card in cards:
        img = Image.open(card["path"]).convert("RGB")
        img.thumbnail((520, 260))
        thumbs.append((card, img.copy()))
        img.close()

    cols = 2
    pad = 34
    label_h = 62
    cell_w = 560
    cell_h = 350
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), "#f8fafc")
    draw = ImageDraw.Draw(sheet)
    font = get_font(18, bold=True)
    small = get_font(15)
    for idx, (card, img) in enumerate(thumbs):
        row = idx // cols
        col = idx % cols
        x = pad + col * cell_w
        y = pad + row * cell_h
        draw.rounded_rectangle((x - 10, y - 10, x + cell_w - 30, y + cell_h - 24), radius=12, fill="#ffffff", outline="#cbd5e1", width=2)
        sheet.paste(img, (x, y + label_h))
        draw.text((x, y), card["title"], fill="#0f172a", font=font)
        draw.text((x, y + 28), Path(card["path"]).name, fill="#475569", font=small)
    out = OUT_DIR / "solver_evidence_contact_sheet.png"
    sheet.save(out, quality=95)
    return out


def write_index(cards: list[dict[str, str]], contact_sheet: Path) -> None:
    lines = [
        "# Python 求解结果截图索引",
        "",
        "这些图片是从已落盘的 Python 求解结果 JSON/CSV 生成的终端截图式证据卡，用于放入结题报告附录或答辩材料。生成过程只读取既有结果产物，不重新运行 Gurobi、Optuna 或 Benders 正式实验。",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 输出目录：`{OUT_DIR}`",
        f"- 联系表：`{contact_sheet}`",
        "",
        "| 序号 | 截图 | 来源结果 | 建议插入位置 |",
        "|---|---|---|---|",
    ]
    for idx, card in enumerate(cards, start=1):
        lines.append(
            f"| {idx} | `{Path(card['path']).name}` | `{card['source']}` | {card['insert']} |"
        )
    lines.extend(
        [
            "",
            "## 使用建议",
            "",
            "1. 在正文中保留关键图表和结论，把这些终端截图式证据卡放入附录，标题可用“附录C Python求解与实验结果证据截图”。",
            "2. 每张截图下方建议配一句话说明：该图由对应 JSON/CSV 结果文件自动生成，显示命令、关键数值、文件哈希和声明边界。",
            "3. 不建议把这些图放得过大；每页放 1-2 张，保持可读即可。",
        ]
    )
    INDEX_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cards = build_cards()
    contact = build_contact_sheet(cards)
    write_index(cards, contact)
    print(f"generated {len(cards)} evidence screenshots")
    print(f"output_dir={OUT_DIR}")
    print(f"contact_sheet={contact}")
    print(f"index={INDEX_MD}")


if __name__ == "__main__":
    main()
