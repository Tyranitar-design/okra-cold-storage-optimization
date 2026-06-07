"""
实验结果可视化。

输出稳定的 PNG 图，适合汇报和论文初稿整理。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 140,
        "savefig.dpi": 180,
    }
)


def _prepare_path(output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_cost_breakdown_chart(analysis: Dict[str, Any], output_path: Path | str, title: str) -> Path:
    """保存成本结构环形图。"""
    path = _prepare_path(output_path)
    labels = ["建设", "运营", "运输", "损耗", "碳排"]
    values = [
        float(analysis["fixed_cost"]),
        float(analysis["operate_cost"]),
        float(analysis["transport_cost"]),
        float(analysis["loss_cost"]),
        float(analysis["carbon_cost"]),
    ]
    total = sum(values)

    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2"]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        colors=colors,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        textprops={"fontsize": 10},
    )
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(9)

    ax.text(0, 0, f"{total:,.0f}\n元", ha="center", va="center", fontsize=12, fontweight="bold")
    ax.set_title(title, fontsize=13, pad=14)
    ax.axis("equal")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def save_metric_bar_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    output_path: Path | str,
    title: str,
    ylabel: str,
    color: str = "#4C78A8",
) -> Path:
    """保存单指标柱状图。"""
    path = _prepare_path(output_path)
    data = df[[x_col, y_col]].copy()

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    bars = ax.bar(data[x_col], data[y_col], color=color, width=0.6)
    ax.set_title(title, fontsize=13, pad=12)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(x_col)
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    for bar, value in zip(bars, data[y_col]):
        label = f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)
        ax.annotate(
            label,
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def save_sensitivity_curve(
    df: pd.DataFrame,
    x_col: str,
    output_path: Path | str,
    title: str,
    y_col: str = "total_cost",
    secondary_col: str = "num_facilities",
    y_label: str = "总成本 (元)",
    secondary_label: str = "开放设施数",
) -> Path:
    """保存灵敏度折线图。"""
    path = _prepare_path(output_path)
    data = df.sort_values(x_col).copy()

    fig, ax1 = plt.subplots(figsize=(8.8, 4.9))
    color1 = "#4C78A8"
    color2 = "#F58518"

    ax1.plot(data[x_col], data[y_col], marker="o", color=color1, linewidth=2.2, label=y_label)
    ax1.set_xlabel(x_col)
    ax1.set_ylabel(y_label, color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.grid(axis="both", linestyle="--", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(
        data[x_col],
        data[secondary_col],
        marker="s",
        color=color2,
        linewidth=2.0,
        linestyle="--",
        label=secondary_label,
    )
    ax2.set_ylabel(secondary_label, color=color2)
    ax2.tick_params(axis="y", labelcolor=color2)

    ax1.set_title(title, fontsize=13, pad=12)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def save_layout_map(config: Any, analysis: Dict[str, Any], output_path: Path | str, title: str) -> Path:
    """保存冷库布局散点图。"""
    path = _prepare_path(output_path)
    nodes = config.nodes.copy()
    facilities = analysis.get("facilities", [])
    facility_by_id = {item["site"]: item for item in facilities}
    type_colors = {
        "预冷库": "#4C78A8",
        "冷藏库": "#F58518",
        "气调库": "#54A24B",
        "冷冻库": "#E45756",
    }

    fig, ax = plt.subplots(figsize=(8.2, 7.0))

    normal_nodes = nodes[~nodes["node_id"].isin(facility_by_id.keys())]
    ax.scatter(
        normal_nodes["lon"],
        normal_nodes["lat"],
        s=18 + normal_nodes["okra_production_ton"] * 2.5,
        c="#B9C0C9",
        alpha=0.72,
        edgecolors="white",
        linewidths=0.3,
        label="未选中节点",
    )

    for storage_name, color in type_colors.items():
        subset = [
            item
            for item in facilities
            if item["type_name"] == storage_name
        ]
        if not subset:
            continue
        ids = [item["site"] for item in subset]
        picked = nodes[nodes["node_id"].isin(ids)]
        ax.scatter(
            picked["lon"],
            picked["lat"],
            s=220,
            marker="*",
            c=color,
            edgecolors="black",
            linewidths=0.6,
            label=storage_name,
            zorder=5,
        )
        for _, row in picked.iterrows():
            ax.text(
                row["lon"] + 0.005,
                row["lat"] + 0.005,
                row["node_id"],
                fontsize=9,
                weight="bold",
            )

    ax.set_title(title, fontsize=13, pad=12)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, linestyle="--", alpha=0.25)
    ax.legend(loc="best", fontsize=9, frameon=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
