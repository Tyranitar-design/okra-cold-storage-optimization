"""Manifest for real external data raw/cleaned ingestion artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
MANIFEST_JSON_PATH = RESULT_DIR / "real_data_ingestion_manifest.json"
MANIFEST_MD_PATH = RESULT_DIR / "real_data_ingestion_manifest.md"

DATASETS = [
    {
        "dataset_id": "market_prices_moa",
        "source_id": "SRC-D-002",
        "source_name": "农业农村部数据平台 / 重点农产品市场信息平台",
        "target_table": "okra.market_price_observations",
        "raw_path": PROJECT_ROOT / "data" / "raw" / "official" / "moa_market_prices_raw.csv",
        "cleaned_path": PROJECT_ROOT / "data" / "processed" / "real_data" / "market_price_observations.csv",
        "required_columns": [
            "source_id",
            "observation_date",
            "commodity_name",
            "raw_record_json",
        ],
        "optional_columns": [
            "market_name",
            "province",
            "price_yuan_per_kg",
            "price_index",
            "unit_original",
            "source_url",
        ],
    },
    {
        "dataset_id": "weather_daily_cma_era5",
        "source_id": "SRC-D-003/SRC-D-004",
        "source_name": "中国气象数据网 / ERA5-Land",
        "target_table": "okra.weather_daily_observations",
        "raw_path": PROJECT_ROOT / "data" / "raw" / "official" / "weather_daily_raw.csv",
        "cleaned_path": PROJECT_ROOT / "data" / "processed" / "real_data" / "weather_daily_observations.csv",
        "required_columns": [
            "source_id",
            "observation_date",
            "station_id",
            "lat",
            "lon",
            "raw_record_json",
        ],
        "optional_columns": [
            "station_name",
            "temperature_mean_c",
            "temperature_max_c",
            "temperature_min_c",
            "relative_humidity_pct",
            "precipitation_mm",
            "wind_speed_m_s",
            "source_url",
        ],
    },
    {
        "dataset_id": "osm_features_overpass",
        "source_id": "SRC-E-001",
        "source_name": "Overpass API / OpenStreetMap",
        "target_table": "okra.osm_features",
        "raw_path": PROJECT_ROOT / "data" / "raw" / "osm" / "overpass_features_raw.json",
        "cleaned_path": PROJECT_ROOT / "data" / "processed" / "real_data" / "osm_features.geojson",
        "required_columns": [
            "source_id",
            "osm_id",
            "feature_type",
            "geometry_geojson",
            "tags_json",
        ],
        "optional_columns": [
            "name",
            "highway",
            "amenity",
            "shop",
            "building",
            "lat",
            "lon",
            "source_url",
        ],
    },
    {
        "dataset_id": "road_network_edges_overpass",
        "source_id": "SRC-E-001",
        "source_name": "Overpass API / OpenStreetMap",
        "target_table": "okra.road_network_edges",
        "raw_path": PROJECT_ROOT / "data" / "raw" / "osm" / "overpass_roads_raw.json",
        "cleaned_path": PROJECT_ROOT / "data" / "processed" / "real_data" / "road_network_edges.geojson",
        "required_columns": [
            "source_id",
            "edge_key",
            "geometry_geojson",
            "tags_json",
        ],
        "optional_columns": [
            "from_osm_id",
            "to_osm_id",
            "highway",
            "road_name",
            "length_m",
            "assumed_speed_kmh",
            "travel_time_min",
            "source_url",
        ],
    },
]


def _file_status(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
    }


def build_real_data_ingestion_manifest() -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    for dataset in DATASETS:
        raw_status = _file_status(dataset["raw_path"])
        cleaned_status = _file_status(dataset["cleaned_path"])
        if cleaned_status["exists"]:
            ingestion_state = "cleaned_ready_not_applied"
            next_action = "Validate columns and apply to PostgreSQL after probe_ok=true."
        elif raw_status["exists"]:
            ingestion_state = "raw_ready_needs_cleaning"
            next_action = "Run or implement the cleaning adapter to create the cleaned artifact."
        else:
            ingestion_state = "missing_raw_and_cleaned"
            next_action = "Download or export the official/public raw dataset, then preserve it before cleaning."

        datasets.append(
            {
                "dataset_id": dataset["dataset_id"],
                "source_id": dataset["source_id"],
                "source_name": dataset["source_name"],
                "target_table": dataset["target_table"],
                "raw": raw_status,
                "cleaned": cleaned_status,
                "required_columns": dataset["required_columns"],
                "optional_columns": dataset["optional_columns"],
                "ingestion_state": ingestion_state,
                "next_action": next_action,
                "claim_boundary": (
                    "This manifest tracks expected raw/cleaned artifacts only. It is not evidence of ingestion "
                    "unless cleaned files and PostgreSQL apply logs are present."
                ),
            }
        )

    counts = {}
    for item in datasets:
        counts[item["ingestion_state"]] = counts.get(item["ingestion_state"], 0) + 1
    return {
        "source_name": "real external data ingestion manifest",
        "dataset_count": len(datasets),
        "state_counts": counts,
        "datasets": datasets,
        "output_paths": {
            "json": str(MANIFEST_JSON_PATH),
            "markdown": str(MANIFEST_MD_PATH),
        },
        "research_boundary": (
            "This manifest is a readiness and missing-file audit. It does not download, clean, authorize, "
            "or insert real external data by itself."
        ),
    }


def render_manifest_markdown(manifest: dict[str, Any]) -> str:
    rows = [
        "| dataset_id | target_table | raw | cleaned | state |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in manifest.get("datasets", []):
        rows.append(
            "| {dataset_id} | {target_table} | {raw} | {cleaned} | {state} |".format(
                dataset_id=item.get("dataset_id", ""),
                target_table=item.get("target_table", ""),
                raw="yes" if item.get("raw", {}).get("exists") else "no",
                cleaned="yes" if item.get("cleaned", {}).get("exists") else "no",
                state=item.get("ingestion_state", ""),
            )
        )
    return "\n".join(
        [
            "# Real Data Ingestion Manifest",
            "",
            f"Dataset count: {manifest.get('dataset_count', 0)}",
            "",
            "## State Counts",
            "",
            json.dumps(manifest.get("state_counts", {}), ensure_ascii=False, indent=2),
            "",
            "## Datasets",
            "",
            *rows,
            "",
            "## Boundary",
            "",
            str(manifest.get("research_boundary", "")),
            "",
        ]
    )


def write_real_data_ingestion_manifest(out_dir: Path | None = None) -> dict[str, str]:
    manifest = build_real_data_ingestion_manifest()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / MANIFEST_JSON_PATH.name
    md_path = destination / MANIFEST_MD_PATH.name
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_manifest_markdown(manifest), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
