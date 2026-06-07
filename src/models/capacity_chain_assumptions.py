"""Shared v3.0 capacity-chain assumptions without solver dependencies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelAssumption:
    """Assumptions that map annual okra flow to a storage service channel."""

    type_id: str
    label: str
    annual_share: float
    storage_days: float
    loss_rate: float
    transport_loss_multiplier: float
    channel_note: str


@dataclass(frozen=True)
class CapacityChainAssumptions:
    """Scenario-level assumptions used until real channel and harvest records exist."""

    harvest_window_days: float = 90.0
    harvest_peak_factor: float = 1.8
    max_facilities: int = 8
    carbon_price: float = 50.0
    loss_price: float = 3000.0
    transport_cost_yuan_per_ton_km: float = 1.2
    transport_carbon_kg_per_ton_km: float = 0.1
    channels: tuple[ChannelAssumption, ...] = (
        ChannelAssumption(
            type_id="precool",
            label="first-mile precooling",
            annual_share=1.0,
            storage_days=2.0 / 24.0,
            loss_rate=0.01,
            transport_loss_multiplier=1.0,
            channel_note="Mandatory first-mile handling within 2 hours; not interpreted as long-term storage.",
        ),
        ChannelAssumption(
            type_id="cold",
            label="fresh cold storage",
            annual_share=0.60,
            storage_days=7.0,
            loss_rate=0.02,
            transport_loss_multiplier=0.45,
            channel_note="Fresh-market channel using 7-10 C literature target; current cost table uses closest cold-storage type.",
        ),
        ChannelAssumption(
            type_id="ca",
            label="controlled-atmosphere storage",
            annual_share=0.30,
            storage_days=20.0,
            loss_rate=0.012,
            transport_loss_multiplier=0.35,
            channel_note="Quality-preserving MAP/CA channel for longer holding.",
        ),
        ChannelAssumption(
            type_id="frozen",
            label="processing/frozen fallback",
            annual_share=0.10,
            storage_days=30.0,
            loss_rate=0.04,
            transport_loss_multiplier=0.35,
            channel_note="Explicitly capped processing or frozen fallback share; not all fresh okra is frozen.",
        ),
    )


def default_assumptions() -> CapacityChainAssumptions:
    return CapacityChainAssumptions()


def channel_map(assumptions: CapacityChainAssumptions) -> dict[str, ChannelAssumption]:
    return {channel.type_id: channel for channel in assumptions.channels}


def annual_flow(demand_ton: float, channel: ChannelAssumption) -> float:
    return demand_ton * channel.annual_share


def peak_capacity_load(
    demand_ton: float,
    channel: ChannelAssumption,
    assumptions: CapacityChainAssumptions,
) -> float:
    return (
        demand_ton
        * channel.annual_share
        * channel.storage_days
        / assumptions.harvest_window_days
        * assumptions.harvest_peak_factor
    )


_channel_map = channel_map
_annual_flow = annual_flow
_peak_capacity_load = peak_capacity_load
