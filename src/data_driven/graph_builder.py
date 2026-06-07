"""
二分图特征构建。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd


@dataclass
class BipartiteGraphBundle:
    """二分图数据。"""

    nodes: pd.DataFrame
    edges: pd.DataFrame
    demand_nodes: pd.DataFrame
    facility_nodes: pd.DataFrame


def build_bipartite_graph(config: Any, candidate_ids: List[str] | None = None, demand_ids: List[str] | None = None) -> BipartiteGraphBundle:
    """构建候选点-需求点二分图。"""
    if candidate_ids is None:
        candidate_ids = list(config.candidates["node_id"])
    if demand_ids is None:
        demand_ids = list(config.demands["node_id"])

    demand_rows = config.nodes[config.nodes["node_id"].isin(demand_ids)].copy().reset_index(drop=True)
    facility_rows = config.nodes[config.nodes["node_id"].isin(candidate_ids)].copy().reset_index(drop=True)

    demand_rows["node_type"] = "demand"
    facility_rows["node_type"] = "facility"
    demand_rows["node_key"] = demand_rows["node_id"].map(lambda x: f"demand::{x}")
    facility_rows["node_key"] = facility_rows["node_id"].map(lambda x: f"facility::{x}")

    nodes = pd.concat([demand_rows, facility_rows], ignore_index=True)

    edge_rows = []
    for i in demand_ids:
        for j in candidate_ids:
            edge_rows.append(
                {
                    "demand_id": i,
                    "demand_key": f"demand::{i}",
                    "facility_id": j,
                    "facility_key": f"facility::{j}",
                    "distance_km": float(config.get_dist(i, j)),
                    "travel_time_h": float(config.get_time(i, j)),
                    "demand_ton": float(config.get_demand(i)),
                    "is_self": 1.0 if i == j else 0.0,
                }
            )

    edges = pd.DataFrame(edge_rows)
    return BipartiteGraphBundle(nodes=nodes, edges=edges, demand_nodes=demand_rows, facility_nodes=facility_rows)
