"""
Contextual bandit style cut-selection agent.

This is a lightweight RL prototype: it learns to score cuts from
graph context + cut features and then selects the top-k cuts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


class CutScoreNetwork(nn.Module):
    """A simple MLP that predicts cut reward/utility."""

    def __init__(self, input_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class ResidualBlock(nn.Module):
    """Residual MLP block for more stable cut-utility scoring."""

    def __init__(self, hidden_dim: int, dropout: float = 0.1):
        super().__init__()
        self.net = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.relu(x + self.net(x))


class ResidualCutScoreNetwork(nn.Module):
    """Residual scorer with LayerNorm and Dropout for the enhanced AI-Benders branch."""

    def __init__(self, input_dim: int, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.input = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.blocks = nn.ModuleList(ResidualBlock(hidden_dim, dropout=dropout) for _ in range(num_layers))
        self.output = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.input(x)
        for block in self.blocks:
            h = block(h)
        return self.output(h).squeeze(-1)


@dataclass
class AgentTrainingResult:
    final_loss: float
    epochs: int
    sample_count: int
    network_type: str = "mlp"


class CutSelectionAgent:
    """Trainable cut selection policy."""

    def __init__(
        self,
        graph_dim: int,
        cut_dim: int,
        hidden_dim: int = 64,
        lr: float = 1e-3,
        device: str | None = None,
        network_type: str = "mlp",
        num_layers: int = 2,
        dropout: float = 0.1,
    ):
        self.graph_dim = graph_dim
        self.cut_dim = cut_dim
        self.network_type = network_type
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        if network_type == "residual":
            self.model = ResidualCutScoreNetwork(
                graph_dim + cut_dim,
                hidden_dim=hidden_dim,
                num_layers=num_layers,
                dropout=dropout,
            ).to(self.device)
        else:
            self.model = CutScoreNetwork(graph_dim + cut_dim, hidden_dim=hidden_dim).to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

    def _make_input(self, graph_embedding: torch.Tensor, cut_features: torch.Tensor) -> torch.Tensor:
        if graph_embedding.ndim == 1:
            graph_embedding = graph_embedding.unsqueeze(0)
        graph_repeat = graph_embedding.repeat(cut_features.shape[0], 1)
        return torch.cat([graph_repeat, cut_features], dim=1)

    def fit(self, graph_embedding: torch.Tensor, cut_features: torch.Tensor, rewards: torch.Tensor, epochs: int = 200) -> AgentTrainingResult:
        """Train the scorer on contextual bandit feedback."""
        self.model.train()
        graph_embedding = graph_embedding.to(self.device)
        cut_features = cut_features.to(self.device)
        rewards = rewards.to(self.device)
        x = self._make_input(graph_embedding, cut_features)

        final_loss = 0.0
        for _ in range(epochs):
            pred = self.model(x)
            loss = F.mse_loss(pred, rewards)
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 5.0)
            self.optimizer.step()
            final_loss = float(loss.detach().cpu())

        return AgentTrainingResult(
            final_loss=final_loss,
            epochs=epochs,
            sample_count=int(len(rewards)),
            network_type=self.network_type,
        )

    def score(self, graph_embedding: torch.Tensor, cut_features: torch.Tensor) -> torch.Tensor:
        """Score each cut."""
        self.model.eval()
        with torch.no_grad():
            x = self._make_input(graph_embedding.to(self.device), cut_features.to(self.device))
            return self.model(x).detach().cpu()

    def select_top_k(self, graph_embedding: torch.Tensor, cut_features: torch.Tensor, k: int = 1) -> List[int]:
        """Return the indices of top-k cuts."""
        scores = self.score(graph_embedding, cut_features)
        order = torch.argsort(scores, descending=True)
        return order[:k].tolist()

    def feature_importance(self) -> np.ndarray:
        """Approximate feature importance from the first layer weights."""
        first = self.model.net[0]
        weights = first.weight.detach().cpu().numpy()
        cut_weights = np.abs(weights[:, self.graph_dim :])
        if cut_weights.size == 0:
            return np.zeros(self.cut_dim, dtype=float)
        importance = cut_weights.mean(axis=0)
        total = importance.sum()
        if total <= 1e-8:
            return importance
        return importance / total


def train_agent_from_history(
    graph_embedding: torch.Tensor,
    cut_features: torch.Tensor,
    rewards: torch.Tensor,
    hidden_dim: int = 64,
    lr: float = 1e-3,
    epochs: int = 250,
    network_type: str = "mlp",
    num_layers: int = 2,
    dropout: float = 0.1,
) -> Tuple[CutSelectionAgent, AgentTrainingResult]:
    """Train an agent and return the fitted policy."""
    agent = CutSelectionAgent(
        graph_dim=int(graph_embedding.shape[-1]),
        cut_dim=int(cut_features.shape[-1]),
        hidden_dim=hidden_dim,
        lr=lr,
        network_type=network_type,
        num_layers=num_layers,
        dropout=dropout,
    )
    result = agent.fit(graph_embedding, cut_features, rewards, epochs=epochs)
    return agent, result
