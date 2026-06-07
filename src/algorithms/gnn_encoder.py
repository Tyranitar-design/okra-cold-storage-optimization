"""
Lightweight bipartite graph encoder for Benders cut-ranking.

This implementation uses plain PyTorch so it works even without PyG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F


def _standardize_frame(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    arr = df[columns].copy().astype(float).to_numpy()
    if arr.size == 0:
        return arr
    mean = arr.mean(axis=0, keepdims=True)
    std = arr.std(axis=0, keepdims=True)
    std[std < 1e-8] = 1.0
    return (arr - mean) / std


def build_node_features(graph_bundle: Any) -> Tuple[torch.Tensor, Dict[str, int]]:
    """Build standardized node feature tensor from bipartite graph bundle."""
    nodes = graph_bundle.nodes.copy().reset_index(drop=True)
    feature_columns = [
        "level",
        "okra_production_ton",
        "is_candidate",
        "population",
        "lat",
        "lon",
    ]
    for col in feature_columns:
        if col not in nodes.columns:
            nodes[col] = 0.0

    base = _standardize_frame(nodes, feature_columns)
    type_is_demand = (nodes["node_type"].astype(str) == "demand").astype(float).to_numpy().reshape(-1, 1)
    type_is_facility = (nodes["node_type"].astype(str) == "facility").astype(float).to_numpy().reshape(-1, 1)
    feature_matrix = np.concatenate([base, type_is_demand, type_is_facility], axis=1)

    if "node_key" not in nodes.columns:
        nodes["node_key"] = nodes["node_id"].astype(str)
    node_id_to_idx = {str(row["node_key"]): idx for idx, row in nodes.iterrows()}
    return torch.tensor(feature_matrix, dtype=torch.float32), node_id_to_idx


def build_weighted_adjacency(graph_bundle: Any, node_id_to_idx: Dict[str, int]) -> torch.Tensor:
    """Build weighted adjacency matrix using inverse distance and travel time."""
    n = len(node_id_to_idx)
    adj = np.zeros((n, n), dtype=np.float32)
    edges = graph_bundle.edges.copy().reset_index(drop=True)
    if len(edges) == 0:
        return torch.eye(n, dtype=torch.float32)

    dist = edges["distance_km"].astype(float).to_numpy()
    time_h = edges["travel_time_h"].astype(float).to_numpy()
    demand = edges["demand_ton"].astype(float).to_numpy()
    weight = 1.0 / (1.0 + dist) * 1.0 / (1.0 + time_h) * (1.0 + demand / (demand.mean() + 1e-8))

    for idx, row in edges.iterrows():
        demand_key = str(row.get("demand_key", f"demand::{row['demand_id']}"))
        facility_key = str(row.get("facility_key", f"facility::{row['facility_id']}"))
        i = node_id_to_idx[demand_key]
        j = node_id_to_idx[facility_key]
        w = float(weight[idx])
        adj[i, j] = max(adj[i, j], w)
        adj[j, i] = max(adj[j, i], w)

    adj = adj + np.eye(n, dtype=np.float32)
    row_sum = adj.sum(axis=1, keepdims=True)
    row_sum[row_sum < 1e-8] = 1.0
    adj = adj / row_sum
    return torch.tensor(adj, dtype=torch.float32)


class BipartiteGraphEncoder(nn.Module):
    """A small message-passing encoder for the candidate-demand graph."""

    def __init__(self, input_dim: int, hidden_dim: int = 32, num_layers: int = 2, dropout: float = 0.0):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.self_layers = nn.ModuleList(nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers))
        self.neigh_layers = nn.ModuleList(nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers))
        self.out_proj = nn.Linear(hidden_dim * 3, hidden_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, node_features: torch.Tensor, adjacency: torch.Tensor) -> torch.Tensor:
        h = F.relu(self.input_proj(node_features))
        for self_layer, neigh_layer in zip(self.self_layers, self.neigh_layers):
            neigh = torch.matmul(adjacency, h)
            h = F.relu(self_layer(h) + neigh_layer(neigh))
            h = self.dropout(h)

        pooled = torch.cat(
            [
                h.mean(dim=0),
                h.max(dim=0).values,
                h.std(dim=0, unbiased=False),
            ],
            dim=0,
        )
        return self.out_proj(pooled)


def encode_bipartite_graph(graph_bundle: Any, hidden_dim: int = 32) -> torch.Tensor:
    """Convenience wrapper to obtain a graph embedding."""
    node_features, node_id_to_idx = build_node_features(graph_bundle)
    adjacency = build_weighted_adjacency(graph_bundle, node_id_to_idx)
    encoder = BipartiteGraphEncoder(input_dim=node_features.shape[1], hidden_dim=hidden_dim)
    encoder.eval()
    with torch.no_grad():
        return encoder(node_features, adjacency)
