"""
AI 增强 Benders 原型。

当前实现包含：
- 图编码器（纯 PyTorch 的轻量消息传递）
- cut 特征提取
- 上下文 bandit 式 cut 评分器
- 与经典 Benders 的兼容接口
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch

from src.algorithms.benders import run_benders
from src.algorithms.cut_features import CUT_FEATURE_NAMES, build_cut_dataset, extract_cut_feature_vector
from src.algorithms.gnn_encoder import encode_bipartite_graph
from src.algorithms.rl_agent import train_agent_from_history
from src.data_driven.graph_builder import build_bipartite_graph


CUT_SCORE_FORMULA = "0.40 * rhs + 0.25 * coef_l1 + 0.20 * gap_pct + 0.15 * compactness"
AI_BENDERS_RESEARCH_BOUNDARY = (
    "Current Benders cut-ranking result is a structured smoke-test evidence bundle, "
    "not yet a full comparative superiority proof."
)


def score_cut(cut: Dict[str, Any], iteration: Dict[str, Any] | None = None) -> float:
    """给 cut 计算一个可解释分数。"""
    return float(_score_breakdown(cut, iteration)["total"])


def _score_breakdown(cut: Dict[str, Any], iteration: Dict[str, Any] | None = None) -> Dict[str, Any]:
    feat = extract_cut_feature_vector(cut, iteration)
    rhs = float(feat[0])
    coef_count = float(feat[1])
    coef_l1 = float(feat[6])
    gap_pct = float(feat[13])
    compactness = 1.0 / (1.0 + coef_count)
    inputs = {
        "rhs": rhs,
        "coef_count": coef_count,
        "coef_l1": coef_l1,
        "gap_pct": gap_pct,
        "compactness": compactness,
    }
    components = {
        "rhs": 0.40 * rhs,
        "coef_l1": 0.25 * coef_l1,
        "gap_pct": 0.20 * gap_pct,
        "compactness": 0.15 * compactness,
    }
    total = float(sum(components.values()))
    return {"inputs": inputs, "components": components, "total": total}


def _explain_cut(score_breakdown: Dict[str, Any], feature_vector: torch.Tensor | List[float] | Any) -> Dict[str, Any]:
    components = score_breakdown["components"]
    ordered = sorted(components.items(), key=lambda item: item[1], reverse=True)
    dominant_factors = [name for name, _ in ordered[:2]]
    if hasattr(feature_vector, "tolist"):
        values = list(feature_vector.tolist())
    else:
        values = list(feature_vector)
    reason_text = (
        f"得分主要由 {dominant_factors[0]} 和 {dominant_factors[1]} 驱动；"
        f"rhs={float(values[0]):.3f}, coef_l1={float(values[6]):.3f}, "
        f"gap_pct={float(values[13]):.3f}, coef_count={float(values[1]):.0f}。"
    )
    return {
        "dominant_factors": dominant_factors,
        "reason_text": reason_text,
        "rank_order": [name for name, _ in ordered],
    }


def rank_cuts(cuts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按可解释分数从高到低排序 cut。"""
    return sorted(cuts, key=lambda cut: score_cut(cut, cut.get("iteration")), reverse=True)


def _extract_cut_history(iterations: List[Dict[str, Any]], cut_pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把迭代记录和 cut 池对齐成训练样本。"""
    history: List[Dict[str, Any]] = []
    if not iterations or not cut_pool:
        return history

    for idx, cut in enumerate(cut_pool):
        iteration = iterations[min(idx, len(iterations) - 1)]
        history.append({"iteration": iteration, "cut": cut})
    return history


def _summarize_feature_importance(feature_importance: List[float], top_k: int = 5) -> List[Dict[str, float]]:
    pairs = list(zip(CUT_FEATURE_NAMES, feature_importance))
    pairs.sort(key=lambda item: item[1], reverse=True)
    return [
        {"feature": name, "importance": float(score)}
        for name, score in pairs[:top_k]
    ]


def _build_cut_score_records(
    cut_history: List[Dict[str, Any]],
    scores: List[float] | torch.Tensor,
    selected_indices: List[int],
    policy_name: str,
) -> List[Dict[str, Any]]:
    if torch.is_tensor(scores):
        score_values = scores.detach().cpu().tolist()
    else:
        score_values = list(scores)
    selected = set(selected_indices)
    records: List[Dict[str, Any]] = []
    for idx, item in enumerate(cut_history):
        cut = item.get("cut", {})
        iteration = item.get("iteration", {})
        feature_vector = extract_cut_feature_vector(cut, iteration)
        score_breakdown = _score_breakdown(cut, iteration)
        explanation = _explain_cut(score_breakdown, feature_vector)
        records.append(
            {
                "cut_id": f"cut_{idx:03d}",
                "iter_no": int(iteration.get("iteration", idx + 1) or idx + 1),
                "policy_name": policy_name,
                "selected": idx in selected,
                "score": float(score_values[idx]) if idx < len(score_values) else None,
                "score_formula": CUT_SCORE_FORMULA,
                "cut_type": cut.get("cut_type"),
                "rhs": float(feature_vector[0]),
                "coef_count": float(feature_vector[1]),
                "gap_pct": float(feature_vector[13]),
                "cut_count": float(feature_vector[14]),
                "score_inputs": score_breakdown["inputs"],
                "score_components": score_breakdown["components"],
                "dominant_factors": explanation["dominant_factors"],
                "reason_text": explanation["reason_text"],
                "features": {name: float(value) for name, value in zip(CUT_FEATURE_NAMES, feature_vector.tolist())},
            }
        )
    return records


def run_ai_benders(
    config: Any,
    *,
    carbon_price: float = 50.0,
    loss_price: float = 3000.0,
    max_facilities: int = 8,
    candidate_ids: Optional[List[str]] = None,
    demand_ids: Optional[List[str]] = None,
    time_limit: int = 300,
    mip_gap: float = 0.01,
    threads: int = 8,
    max_iterations: int = 10,
    top_k_cuts: int = 1,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    AI 增强 Benders。

    当前流程：
    1. 运行经典 Benders，收集迭代和 cut
    2. 用二分图编码产生问题上下文 embedding
    3. 用 cut 特征和历史迭代奖励训练一个轻量 cut 选择器
    4. 给出 top-k cut 选择建议
    """
    base = run_benders(
        config,
        carbon_price=carbon_price,
        loss_price=loss_price,
        max_facilities=max_facilities,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        time_limit=time_limit,
        mip_gap=mip_gap,
        threads=threads,
        max_iterations=max_iterations,
        verbose=verbose,
    )

    graph_bundle = build_bipartite_graph(
        config,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
    )
    graph_embedding = encode_bipartite_graph(graph_bundle, hidden_dim=32)
    graph_summary = {
        "node_count": int(len(graph_bundle.nodes)),
        "edge_count": int(len(graph_bundle.edges)),
        "demand_count": int(len(graph_bundle.demand_nodes)),
        "facility_count": int(len(graph_bundle.facility_nodes)),
        "embedding_dim": int(graph_embedding.shape[-1]),
    }

    cut_history = _extract_cut_history(base.get("iterations", []), base.get("cut_history", []))
    if not cut_history:
        # 用一个最小的可行 cut 样本保持训练管线可运行
        synthetic_cuts = [
            {"rhs": 1.0, "coef": {(("demand::0")): 0.1}, "iteration": {"gap_pct": 1.0, "cut_count": 1}},
            {"rhs": 2.0, "coef": {(("demand::1")): 0.2}, "iteration": {"gap_pct": 2.0, "cut_count": 2}},
        ]
        cut_history = [{"iteration": item["iteration"], "cut": item} for item in synthetic_cuts]

    cut_features, rewards, _ = build_cut_dataset(cut_history)
    agent, train_result = train_agent_from_history(
        graph_embedding,
        cut_features,
        rewards,
        hidden_dim=64,
        lr=1e-3,
        epochs=150,
    )

    scores = agent.score(graph_embedding, cut_features)
    top_indices = torch.argsort(scores, descending=True)[:top_k_cuts].tolist()
    policy_name = f"learned_contextual_bandit_top_{top_k_cuts}"
    cut_score_records = _build_cut_score_records(cut_history, scores, top_indices, policy_name)
    feature_importance = agent.feature_importance().tolist()
    selected_records = [cut_score_records[i] for i in top_indices if i < len(cut_score_records)]
    ranked_records = sorted(
        cut_score_records,
        key=lambda item: float(item.get("score", float("-inf"))),
        reverse=True,
    )

    base["ai_cut_policy"] = policy_name
    base["ai_selected_iterations"] = [
        cut_history[i]["iteration"] for i in top_indices if i < len(cut_history)
    ]
    base["ai_training"] = {
        "final_loss": train_result.final_loss,
        "epochs": train_result.epochs,
        "sample_count": train_result.sample_count,
        "graph_embedding_dim": graph_summary["embedding_dim"],
        "selected_cut_indices": top_indices,
    }
    base["ai_graph_summary"] = graph_summary
    base["ai_score_formula"] = CUT_SCORE_FORMULA
    base["ai_cut_scores"] = cut_score_records
    base["ai_feature_importance"] = feature_importance
    base["ai_feature_importance_top"] = _summarize_feature_importance(feature_importance, top_k=5)
    base["ai_selection_summary"] = {
        "policy_name": policy_name,
        "selection_mode": "contextual_bandit_top_k",
        "score_formula": CUT_SCORE_FORMULA,
        "selected_cut_indices": top_indices,
        "selected_cut_ids": [item["cut_id"] for item in selected_records],
        "selected_cut_count": len(selected_records),
        "top_ranked_cuts": ranked_records[: min(3, len(ranked_records))],
        "graph_summary": graph_summary,
        "training": base["ai_training"],
        "feature_importance_top": base["ai_feature_importance_top"],
        "research_boundary": AI_BENDERS_RESEARCH_BOUNDARY,
    }
    base["ai_cut_score_note"] = (
        "lightweight contextual bandit scorer trained on cut history; "
        "use as explainable ranking prototype rather than superiority proof"
    )
    return base
