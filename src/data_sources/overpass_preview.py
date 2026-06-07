"""Shared Overpass / OpenStreetMap preview helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_SOURCE_REGISTRY_PATH = PROJECT_ROOT / "docs" / "data_source_registry.csv"


OVERPASS_QUERIES: List[Dict[str, str]] = [
    {
        "name": "candidate_warehouses",
        "description": "Search warehouses / cold storage around the county centroid.",
        "query": '[out:json][timeout:60];node["building"="warehouse"](29.00,111.20,29.70,112.20);out body;',
    },
    {
        "name": "road_network",
        "description": "Fetch road network segments for route feature extraction.",
        "query": '[out:json][timeout:60];way["highway"](29.00,111.20,29.70,112.20);out body;>;out skel qt;',
    },
    {
        "name": "market_pois",
        "description": "Fetch market / wholesale POIs for last-mile supply context.",
        "query": '[out:json][timeout:60];node["shop"="supermarket"](29.00,111.20,29.70,112.20);out body;',
    },
]


def build_overpass_preview_report() -> Dict[str, Any]:
    return {
        "source_name": "Overpass API / OpenStreetMap",
        "registry_path": str(DATA_SOURCE_REGISTRY_PATH),
        "registry_exists": DATA_SOURCE_REGISTRY_PATH.exists(),
        "query_count": len(OVERPASS_QUERIES),
        "queries": OVERPASS_QUERIES,
        "research_boundary": (
            "This is a query preview and readiness artifact only. It does not download external data "
            "and does not prove route quality or enterprise coverage."
        ),
    }
