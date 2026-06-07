"""Planning helpers for official real data source integration."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from src.api.services import load_csv_records


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_SOURCE_REGISTRY_PATH = PROJECT_ROOT / "docs" / "data_source_registry.csv"


def _infer_next_action(source_name: str, access_url: str) -> str:
    text = f"{source_name} {access_url}".lower()
    if "openstreetmap" in text or "overpass" in text:
        return "prepare_overpass_query_and_geojson_export"
    if "fao" in text or "faostat" in text:
        return "prepare_api_query_and_tabular_extract"
    if "copernicus" in text or "era5" in text:
        return "prepare_dataset_download_and_regrid"
    if "cma" in text or "气象" in text:
        return "prepare_portal_export_and_station_mapping"
    if "stats" in text or "统计" in text or "moa" in text or "农" in text:
        return "prepare_portal_extract_and_manual_mapping"
    return "review_source_and_define_ingestion_adapter"


def build_official_source_plan(limit: int = 20) -> Dict[str, Any]:
    rows = load_csv_records(DATA_SOURCE_REGISTRY_PATH)
    official_rows = [
        row for row in rows
        if str(row.get("source_category", "")).strip().lower() == "official"
        or str(row.get("status", "")).strip() in {"entry_verified", "available"}
    ]
    sources: List[Dict[str, Any]] = []
    for row in official_rows[: max(0, limit)]:
        source_name = str(row.get("source_name", ""))
        access_url = str(row.get("access_url", ""))
        sources.append(
            {
                "source_id": row.get("source_id"),
                "source_name": source_name,
                "source_category": row.get("source_category"),
                "owner": row.get("owner"),
                "access_url": access_url,
                "status": row.get("status"),
                "priority": row.get("priority"),
                "intended_use": row.get("intended_use"),
                "next_action": _infer_next_action(source_name, access_url),
                "planning_mode": "inferred_from_registry",
            }
        )
    priority_counts = Counter(str(row.get("priority", "")) for row in official_rows if row.get("priority"))
    status_counts = Counter(str(row.get("status", "")) for row in official_rows if row.get("status"))
    return {
        "source_name": "Official real data sources",
        "registry_path": str(DATA_SOURCE_REGISTRY_PATH),
        "count": len(official_rows),
        "preview_count": len(sources),
        "priority_counts": dict(priority_counts),
        "status_counts": dict(status_counts),
        "sources": sources,
        "research_boundary": (
            "This is an ingestion planning artifact inferred from the registry only. "
            "It does not download data, does not imply authorization, and does not replace manual review."
        ),
    }
