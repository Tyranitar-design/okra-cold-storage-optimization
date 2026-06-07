"""Download adapter skeletons for real external data sources.

This module turns the current registry and ingestion manifest into a structured
plan for future real-data downloads. It does not execute network I/O.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.api.services import load_csv_records
from src.data_sources.ingestion_manifest import DATASETS
from src.data_sources.real_data_registry import DATA_SOURCE_REGISTRY_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
DOWNLOAD_ADAPTER_JSON_PATH = RESULT_DIR / "real_data_download_adapters.json"
DOWNLOAD_ADAPTER_MD_PATH = RESULT_DIR / "real_data_download_adapters.md"


def _normalize_text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def _source_tags(text: str) -> set[str]:
    lowered = text.lower()
    tags: set[str] = set()
    if "overpass" in lowered:
        tags.add("overpass")
    if "openstreetmap" in lowered or "osm" in lowered:
        tags.add("osm")
    if "农业农村部" in lowered or "农产品市场" in lowered or "data.moa.gov.cn" in lowered or "ncpscxx.moa.gov.cn" in lowered:
        tags.add("moa")
    if "cma" in lowered or "中国气象数据网" in lowered or "气象" in lowered:
        tags.add("cma")
    if "era5" in lowered or "copernicus" in lowered:
        tags.add("era5")
    if "fao" in lowered or "faostat" in lowered:
        tags.add("fao")
    return tags


def _registry_match_rows(source_name: str, access_hint: str = "") -> List[Dict[str, Any]]:
    dataset_tags = _source_tags(_normalize_text(source_name, access_hint))
    matches: List[Dict[str, Any]] = []
    for row in load_csv_records(DATA_SOURCE_REGISTRY_PATH):
        row_tags = _source_tags(
            _normalize_text(
                row.get("source_name", ""),
                row.get("access_url", ""),
                row.get("owner", ""),
                row.get("intended_use", ""),
                row.get("notes", ""),
            )
        )
        if dataset_tags & row_tags:
            matches.append(
                {
                    "source_id": row.get("source_id", ""),
                    "source_name": row.get("source_name", ""),
                    "owner": row.get("owner", ""),
                    "access_url": row.get("access_url", ""),
                    "status": row.get("status", ""),
                    "priority": row.get("priority", ""),
                }
            )
    return matches


def _adapter_kind_for_dataset(source_name: str) -> Dict[str, Any]:
    tags = _source_tags(source_name)
    if "overpass" in tags:
        return {
            "adapter_kind": "overpass_query_export",
            "download_mode": "overpass_api_query",
            "expected_raw_format": "json",
            "expected_cleaned_format": "geojson",
            "requires_manual_review": False,
            "next_action": "Implement Overpass request execution and preserve the raw JSON before GeoJSON cleaning.",
            "adapter_notes": "Spatial features and road edges are expected to come from query export, not file download.",
        }
    if "era5" in tags and "cma" in tags:
        return {
            "adapter_kind": "hybrid_weather_extract",
            "download_mode": "portal_and_api_extract",
            "expected_raw_format": "csv_or_netcdf",
            "expected_cleaned_format": "csv",
            "requires_manual_review": True,
            "next_action": "Implement the CMA / ERA5 acquisition branch, including credential handling and regridding or station matching.",
            "adapter_notes": "This is a hybrid meteorology adapter because the dataset is expected to combine station and reanalysis sources.",
        }
    if "cma" in tags:
        return {
            "adapter_kind": "weather_portal_extract",
            "download_mode": "portal_export",
            "expected_raw_format": "csv_or_xlsx",
            "expected_cleaned_format": "csv",
            "requires_manual_review": True,
            "next_action": "Implement the meteorology portal export branch and keep station metadata with the raw artifact.",
            "adapter_notes": "The source may require a portal account or manual export step.",
        }
    if "moa" in tags:
        return {
            "adapter_kind": "official_market_price_download",
            "download_mode": "portal_or_api_export",
            "expected_raw_format": "csv_or_html",
            "expected_cleaned_format": "csv",
            "requires_manual_review": True,
            "next_action": "Implement the market-price portal extraction branch and preserve source URLs, dates, and unit metadata.",
            "adapter_notes": "The source may need manual export, portal parsing, or a later API client.",
        }
    if "fao" in tags:
        return {
            "adapter_kind": "public_api_extract",
            "download_mode": "api_extract",
            "expected_raw_format": "json_or_csv",
            "expected_cleaned_format": "csv",
            "requires_manual_review": False,
            "next_action": "Implement the public API client and keep the raw response alongside the cleaned table.",
            "adapter_notes": "This branch is reserved for later international comparison data.",
        }
    return {
        "adapter_kind": "manual_adapter_review",
        "download_mode": "manual_review",
        "expected_raw_format": "unknown",
        "expected_cleaned_format": "csv",
        "requires_manual_review": True,
        "next_action": "Review the source manually and define a concrete downloader before adding network code.",
        "adapter_notes": "Fallback branch for sources that do not match the current heuristics.",
    }


def _build_dataset_adapter(dataset: Dict[str, Any]) -> Dict[str, Any]:
    source_name = str(dataset.get("source_name", ""))
    source_id = str(dataset.get("source_id", ""))
    target_table = str(dataset.get("target_table", ""))
    raw_path = Path(dataset.get("raw_path", ""))
    cleaned_path = Path(dataset.get("cleaned_path", ""))
    match_rows = _registry_match_rows(source_name, source_id)
    adapter_meta = _adapter_kind_for_dataset(source_name)
    source_tags = sorted(_source_tags(_normalize_text(source_name, source_id)))
    return {
        "dataset_id": str(dataset.get("dataset_id", "")),
        "source_id": source_id,
        "source_name": source_name,
        "target_table": target_table,
        "raw_path": str(raw_path),
        "cleaned_path": str(cleaned_path),
        "source_tags": source_tags,
        "registry_matches": match_rows,
        "registry_match_count": len(match_rows),
        "source_backend": "registry_adapter_skeleton",
        "adapter_kind": adapter_meta["adapter_kind"],
        "download_mode": adapter_meta["download_mode"],
        "expected_raw_format": adapter_meta["expected_raw_format"],
        "expected_cleaned_format": adapter_meta["expected_cleaned_format"],
        "requires_manual_review": adapter_meta["requires_manual_review"],
        "adapter_steps": [
            "Check access policy and keep the registry entry as the provenance anchor.",
            "Download or export the raw artifact to the declared raw path.",
            "Preserve checksums and access metadata before any cleaning step.",
            "Transform the raw artifact into the schema-ready cleaned file.",
            "Validate required columns and row counts before PostgreSQL apply.",
        ],
        "next_action": adapter_meta["next_action"],
        "adapter_notes": adapter_meta["adapter_notes"],
        "claim_boundary": (
            "This is a download-adapter skeleton only. It does not perform network I/O, does not create raw data, "
            "and does not imply that the underlying source has already been downloaded or authorized."
        ),
    }


def build_real_data_download_adapter_plan(limit: int = 20) -> Dict[str, Any]:
    datasets = DATASETS[: max(0, limit)]
    adapters = [_build_dataset_adapter(dataset) for dataset in datasets]
    adapter_kind_counts = Counter(item["adapter_kind"] for item in adapters if item.get("adapter_kind"))
    download_mode_counts = Counter(item["download_mode"] for item in adapters if item.get("download_mode"))
    manual_review_count = sum(1 for item in adapters if item.get("requires_manual_review"))
    registry_match_count = sum(item.get("registry_match_count", 0) for item in adapters)
    return {
        "source_name": "real external data download adapter plan",
        "registry_path": str(DATA_SOURCE_REGISTRY_PATH),
        "manifest_path": str(DOWNLOAD_ADAPTER_JSON_PATH),
        "dataset_count": len(adapters),
        "adapter_count": len(adapters),
        "manual_review_count": manual_review_count,
        "registry_match_count": registry_match_count,
        "adapter_kind_counts": dict(adapter_kind_counts),
        "download_mode_counts": dict(download_mode_counts),
        "standard_steps": [
            "Anchor every download to a registry record and the ingestion manifest.",
            "Preserve the raw artifact before any cleaning or schema mapping.",
            "Validate the cleaned artifact against the required columns.",
            "Only apply to PostgreSQL after the cleaned file is present and reviewed.",
        ],
        "datasets": adapters,
        "output_paths": {
            "json": str(DOWNLOAD_ADAPTER_JSON_PATH),
            "markdown": str(DOWNLOAD_ADAPTER_MD_PATH),
        },
        "research_boundary": (
            "This plan is a skeleton for future download implementation. It does not request network access, "
            "does not download external data, and does not replace source-specific legal or credential review."
        ),
    }


def render_download_adapter_plan_markdown(plan: Dict[str, Any]) -> str:
    rows = [
        "| dataset_id | target_table | adapter_kind | raw | cleaned | registry_matches |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in plan.get("datasets", []):
        rows.append(
            "| {dataset_id} | {target_table} | {adapter_kind} | {raw} | {cleaned} | {registry_matches} |".format(
                dataset_id=item.get("dataset_id", ""),
                target_table=item.get("target_table", ""),
                adapter_kind=item.get("adapter_kind", ""),
                raw="yes" if item.get("raw_path") else "no",
                cleaned="yes" if item.get("cleaned_path") else "no",
                registry_matches=item.get("registry_match_count", 0),
            )
        )

    return "\n".join(
        [
            "# Real Data Download Adapter Plan",
            "",
            f"Dataset count: {plan.get('dataset_count', 0)}",
            f"Manual review count: {plan.get('manual_review_count', 0)}",
            "",
            "## Adapter Kind Counts",
            "",
            json.dumps(plan.get("adapter_kind_counts", {}), ensure_ascii=False, indent=2),
            "",
            "## Download Mode Counts",
            "",
            json.dumps(plan.get("download_mode_counts", {}), ensure_ascii=False, indent=2),
            "",
            "## Standard Steps",
            "",
            *[f"- {step}" for step in plan.get("standard_steps", [])],
            "",
            "## Datasets",
            "",
            *rows,
            "",
            "## Boundary",
            "",
            str(plan.get("research_boundary", "")),
            "",
        ]
    )


def write_real_data_download_adapter_plan(out_dir: Path | None = None) -> Dict[str, str]:
    plan = build_real_data_download_adapter_plan()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / DOWNLOAD_ADAPTER_JSON_PATH.name
    md_path = destination / DOWNLOAD_ADAPTER_MD_PATH.name
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_download_adapter_plan_markdown(plan), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}

