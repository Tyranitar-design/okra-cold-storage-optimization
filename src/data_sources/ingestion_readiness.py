"""Readiness report for real external data ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"
MAPPING_DOC_PATH = PROJECT_ROOT / "docs" / "真实数据字段映射与入库验收清单_v1.md"

REAL_DATA_TABLES = [
    {
        "table_name": "okra.market_price_observations",
        "source_id": "SRC-D-002",
        "source_name": "农业农村部数据平台 / 重点农产品市场信息平台",
        "target_data": "market prices and price indexes",
        "paper_use": "loss-value parameterization and market scenarios",
    },
    {
        "table_name": "okra.weather_daily_observations",
        "source_id": "SRC-D-003/SRC-D-004",
        "source_name": "中国气象数据网 / ERA5-Land",
        "target_data": "daily weather observations and reanalysis variables",
        "paper_use": "loss parameter learning, seasonality, and extreme-weather sensitivity",
    },
    {
        "table_name": "okra.osm_features",
        "source_id": "SRC-E-001",
        "source_name": "Overpass API / OpenStreetMap",
        "target_data": "OSM features, POI, warehouses, markets, and road tags",
        "paper_use": "map layers, candidate discovery, and spatial evidence",
    },
    {
        "table_name": "okra.road_network_edges",
        "source_id": "SRC-E-001",
        "source_name": "Overpass API / OpenStreetMap",
        "target_data": "road network edges and travel-time assumptions",
        "paper_use": "distance/time matrix calibration and logistics linkage",
    },
]


def _schema_contains_table(schema_text: str, table_name: str) -> bool:
    return table_name.replace("okra.", "okra.").lower() in schema_text.lower()


def build_real_data_ingestion_readiness() -> dict[str, Any]:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
    tables: list[dict[str, Any]] = []
    for table in REAL_DATA_TABLES:
        schema_ready = _schema_contains_table(schema_text, table["table_name"])
        tables.append(
            {
                **table,
                "schema_ready": schema_ready,
                "ingestion_state": "schema_ready_not_ingested" if schema_ready else "schema_missing",
                "requires_raw_file": True,
                "requires_cleaned_file": True,
                "requires_postgres_apply": True,
                "claim_boundary": (
                    "Schema and mapping are ready, but no downloaded raw file, cleaned artifact, or database row "
                    "has been verified yet."
                    if schema_ready
                    else "Schema table is missing and must be added before ingestion."
                ),
            }
        )

    schema_ready_count = sum(1 for item in tables if item["schema_ready"])
    return {
        "source_name": "real external data ingestion readiness",
        "schema_path": str(SCHEMA_PATH),
        "mapping_doc_path": str(MAPPING_DOC_PATH),
        "table_count": len(tables),
        "schema_ready_count": schema_ready_count,
        "ingested_table_count": 0,
        "tables": tables,
        "research_boundary": (
            "This report only verifies schema and mapping readiness. It does not prove that external real data "
            "has been downloaded, cleaned, authorized, or inserted into PostgreSQL."
        ),
    }
