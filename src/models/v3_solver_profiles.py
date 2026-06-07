"""Named solver profiles for v3.0 gap-closure experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class V3SolverProfile:
    """Reproducible Gurobi settings for a v3.0 solver experiment."""

    name: str
    label: str
    time_limit: int
    mip_gap: float = 0.01
    threads: int = 8
    solver_params: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


V3_SOLVER_PROFILES: dict[str, V3SolverProfile] = {
    "baseline_300s": V3SolverProfile(
        name="baseline_300s",
        label="Baseline 300s",
        time_limit=300,
        mip_gap=0.01,
        threads=8,
        note="Matches the default v3.0 baseline run for apples-to-apples comparison.",
    ),
    "bound_focus_60s": V3SolverProfile(
        name="bound_focus_60s",
        label="Bound focus 60s",
        time_limit=60,
        mip_gap=0.01,
        threads=8,
        solver_params={"MIPFocus": 3, "Cuts": 2, "Presolve": 2},
        note="Short bounded run emphasizing bound improvement before longer reruns are authorized.",
    ),
    "incumbent_focus_60s": V3SolverProfile(
        name="incumbent_focus_60s",
        label="Incumbent focus 60s",
        time_limit=60,
        mip_gap=0.01,
        threads=8,
        solver_params={"MIPFocus": 1, "Heuristics": 0.2},
        note="Short bounded run emphasizing incumbent improvement.",
    ),
    "extended_bound_900s": V3SolverProfile(
        name="extended_bound_900s",
        label="Extended bound 900s",
        time_limit=900,
        mip_gap=0.01,
        threads=8,
        solver_params={"MIPFocus": 3, "Cuts": 2, "Presolve": 2},
        note="Longer paper-evidence run; use only when execution time is explicitly acceptable.",
    ),
}


def get_v3_solver_profile(name: str) -> V3SolverProfile:
    try:
        return V3_SOLVER_PROFILES[name]
    except KeyError as exc:
        available = ", ".join(sorted(V3_SOLVER_PROFILES))
        raise ValueError(f"Unknown v3 solver profile '{name}'. Available profiles: {available}") from exc


def list_v3_solver_profiles() -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in V3_SOLVER_PROFILES.values()]
