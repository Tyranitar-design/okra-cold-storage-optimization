"""
秋葵冷库布局问题的共享数据与系数工具。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class LayoutProblemData:
    """布局优化问题的共享数据。"""

    config: Any
    candidate_ids: List[str]
    demand_ids: List[str]
    storage_types: List[str]
    demand: Dict[str, float]
    storage_loss_rate: Dict[str, float]
    transport_unit_cost: float = 1.2
    transport_carbon_factor: float = 0.1  # kgCO2 / ton-km


def build_layout_data(config: Any, candidate_ids: Optional[List[str]] = None, demand_ids: Optional[List[str]] = None) -> LayoutProblemData:
    """构造共享问题数据。"""
    if candidate_ids is None:
        candidate_ids = list(config.candidates["node_id"])
    if demand_ids is None:
        demand_ids = list(config.demands["node_id"])

    pp = config.get_preservation_params()
    storage_loss_rate = {
        "precool": pp["precool_loss_rate"],
        "cold": pp["cold_storage_loss_weekly"] * 2,
        "ca": pp["ca_storage_loss_weekly"] * 2,
        "frozen": pp["cold_storage_loss_weekly"] * 0.5,
    }

    return LayoutProblemData(
        config=config,
        candidate_ids=list(candidate_ids),
        demand_ids=list(demand_ids),
        storage_types=list(config.storage_types),
        demand={i: config.get_demand(i) for i in demand_ids},
        storage_loss_rate=storage_loss_rate,
    )


def get_capacity(data: LayoutProblemData, storage_type: str, capacity_idx: int) -> float:
    """获取某类型某容量等级的容量。"""
    return float(data.config.capacity_index[storage_type][capacity_idx]["capacity"])


def get_fixed_cost(data: LayoutProblemData, storage_type: str, capacity_idx: int) -> float:
    """获取建设成本(万元)。"""
    return float(data.config.capacity_index[storage_type][capacity_idx]["fixed_cost"])


def get_operate_cost(data: LayoutProblemData, storage_type: str, capacity_idx: int) -> float:
    """获取运营成本(万元/年)。"""
    return float(data.config.capacity_index[storage_type][capacity_idx]["operate_cost"])


def get_lower_level_unit_cost(
    data: LayoutProblemData,
    i: str,
    j: str,
    storage_type: str,
    carbon_price: float,
    loss_price: float,
    include_loss: bool = True,
    include_carbon: bool = True,
) -> float:
    """获取下层每吨分配的单位成本。"""
    dist = data.config.get_dist(i, j)
    travel_time = data.config.get_time(i, j)
    sp = data.config.get_storage_params(storage_type)

    transport_cost = dist * data.transport_unit_cost
    loss_cost = 0.0
    if include_loss:
        loss_cost = (travel_time * data.config.get_preservation_params()["transport_loss_per_hour"] + data.storage_loss_rate[storage_type]) * loss_price

    carbon_cost = 0.0
    if include_carbon:
        carbon_cost = (
            sp["energy_cost_per_ton"] * sp["carbon_factor"] / 1000.0
            + dist * data.transport_carbon_factor / 1000.0
        ) * carbon_price

    return transport_cost + loss_cost + carbon_cost


def get_loss_ton_per_ton(data: LayoutProblemData, i: str, j: str, storage_type: str) -> float:
    """获取每吨分配产生的损耗吨数。"""
    travel_time = data.config.get_time(i, j)
    return travel_time * data.config.get_preservation_params()["transport_loss_per_hour"] + data.storage_loss_rate[storage_type]


def get_carbon_ton_per_ton(data: LayoutProblemData, i: str, j: str, storage_type: str) -> float:
    """获取每吨分配产生的碳排放吨数。"""
    dist = data.config.get_dist(i, j)
    sp = data.config.get_storage_params(storage_type)
    return sp["energy_cost_per_ton"] * sp["carbon_factor"] / 1000.0 + dist * data.transport_carbon_factor / 1000.0


def get_social_cost_components(
    data: LayoutProblemData,
    i: str,
    j: str,
    storage_type: str,
    carbon_price: float,
    loss_price: float,
) -> Dict[str, float]:
    """返回分配给某设施时的成本分解。"""
    dist = data.config.get_dist(i, j)
    travel_time = data.config.get_time(i, j)
    sp = data.config.get_storage_params(storage_type)
    transport_cost = dist * data.transport_unit_cost
    loss_ton = get_loss_ton_per_ton(data, i, j, storage_type)
    carbon_ton = get_carbon_ton_per_ton(data, i, j, storage_type)
    return {
        "transport_cost": transport_cost,
        "loss_cost": loss_ton * loss_price,
        "carbon_cost": carbon_ton * carbon_price,
        "loss_ton": loss_ton,
        "carbon_ton": carbon_ton,
        "travel_time": travel_time,
        "energy_cost_per_ton": float(sp["energy_cost_per_ton"]),
    }
