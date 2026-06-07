"""Normalized public LRP benchmark manifest helpers.

This module turns the three existing benchmark layers into one unified schema:
inventory collections, parsed single-file samples, and parsed paired samples.
The result is a preparation layer for future solver experiments only. It does
not upgrade public benchmark assets into okra enterprise data.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results" / "experiments"

BENCHMARK_INVENTORY_SUMMARY_PATH = RESULTS_ROOT / "benchmark_inventory" / "benchmark_inventory_summary.json"
BENCHMARK_PARSE_SUMMARY_PATH = RESULTS_ROOT / "benchmark_parse_samples" / "benchmark_parse_samples_summary.json"
BENCHMARK_PARSE_PAIRS_SUMMARY_PATH = RESULTS_ROOT / "benchmark_parse_pairs" / "benchmark_parse_pairs_summary.json"

NORMALIZED_OUT_DIR = RESULTS_ROOT / "benchmark_normalized_manifest"
NORMALIZED_MANIFEST_PATH = NORMALIZED_OUT_DIR / "benchmark_normalized_manifest.json"
NORMALIZED_CSV_PATH = NORMALIZED_OUT_DIR / "benchmark_normalized_manifest.csv"
NORMALIZED_MD_PATH = NORMALIZED_OUT_DIR / "benchmark_normalized_manifest.md"

INVENTORY_ARTIFACTS = [
    str((RESULTS_ROOT / "benchmark_inventory" / "benchmark_inventory.csv").relative_to(PROJECT_ROOT)),
    str((RESULTS_ROOT / "benchmark_inventory" / "benchmark_inventory_summary.json").relative_to(PROJECT_ROOT)),
    str((RESULTS_ROOT / "benchmark_inventory" / "benchmark_inventory.md").relative_to(PROJECT_ROOT)),
]
PARSE_SAMPLE_ARTIFACTS = [
    str((RESULTS_ROOT / "benchmark_parse_samples" / "benchmark_parse_samples.csv").relative_to(PROJECT_ROOT)),
    str((RESULTS_ROOT / "benchmark_parse_samples" / "benchmark_parse_samples_summary.json").relative_to(PROJECT_ROOT)),
    str((RESULTS_ROOT / "benchmark_parse_samples" / "benchmark_parse_samples.md").relative_to(PROJECT_ROOT)),
]
PARSE_PAIR_ARTIFACTS = [
    str((RESULTS_ROOT / "benchmark_parse_pairs" / "benchmark_parse_pairs.csv").relative_to(PROJECT_ROOT)),
    str((RESULTS_ROOT / "benchmark_parse_pairs" / "benchmark_parse_pairs_summary.json").relative_to(PROJECT_ROOT)),
    str((RESULTS_ROOT / "benchmark_parse_pairs" / "benchmark_parse_pairs.md").relative_to(PROJECT_ROOT)),
]


def load_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _stringify_mapping(value: Any) -> str:
    if value in (None, "", {}):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalise_inventory_entries(summary: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    collections = summary.get("collections", {}) if isinstance(summary, dict) else {}
    for collection, stats in sorted(collections.items()):
        entries.append(
            {
                "entry_id": f"inventory:{collection}",
                "entry_kind": "inventory_collection",
                "schema_name": "benchmark_inventory_collection",
                "collection": collection,
                "parser_name": "inventory",
                "instance_name": collection,
                "source_path": str(BENCHMARK_INVENTORY_SUMMARY_PATH.relative_to(PROJECT_ROOT)),
                "source_paths": INVENTORY_ARTIFACTS,
                "customer_count": None,
                "facility_count": None,
                "platform_count": None,
                "depot_count": None,
                "vehicle_capacity": None,
                "lower_bound": None,
                "upper_bound": None,
                "total_demand": None,
                "total_capacity": None,
                "file_count": stats.get("files"),
                "likely_instance_count": stats.get("likely_instances"),
                "format_hints": stats.get("formats", {}),
                "suffixes": stats.get("suffixes", {}),
                "note": "Inventory summary for one public benchmark collection.",
                "research_boundary": summary.get("research_boundary"),
            }
        )
    return entries


def _normalise_parse_sample_entries(summary: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    rows = summary.get("rows", []) if isinstance(summary, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entries.append(
            {
                "entry_id": f"sample:{row.get('parser_name', 'unknown')}:{row.get('instance_name', 'unknown')}",
                "entry_kind": "parsed_sample",
                "schema_name": "single_file_lrp",
                "collection": row.get("parser_name"),
                "parser_name": row.get("parser_name"),
                "instance_name": row.get("instance_name"),
                "source_path": row.get("relative_path"),
                "source_paths": [row.get("relative_path"), *PARSE_SAMPLE_ARTIFACTS],
                "customer_count": row.get("customer_count"),
                "facility_count": row.get("facility_count"),
                "platform_count": row.get("platform_count"),
                "depot_count": None,
                "vehicle_capacity": row.get("vehicle_capacity"),
                "lower_bound": row.get("lower_bound"),
                "upper_bound": row.get("upper_bound"),
                "total_demand": row.get("total_demand"),
                "total_capacity": None,
                "file_count": 1,
                "likely_instance_count": 1,
                "format_hints": {},
                "suffixes": {},
                "note": row.get("note"),
                "research_boundary": summary.get("research_boundary"),
            }
        )
    return entries


def _normalise_parse_pair_entries(summary: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    rows = summary.get("rows", []) if isinstance(summary, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        customer_file = row.get("customer_file")
        depot_file = row.get("depot_file")
        instance_name = Path(customer_file).name if isinstance(customer_file, str) else "unknown"
        entries.append(
            {
                "entry_id": f"pair:{row.get('collection', 'unknown')}:{instance_name}",
                "entry_kind": "parsed_pair",
                "schema_name": "paired_lrp",
                "collection": row.get("collection"),
                "parser_name": row.get("parser_name"),
                "instance_name": instance_name,
                "source_path": customer_file,
                "source_paths": [customer_file, depot_file, *PARSE_PAIR_ARTIFACTS],
                "customer_count": row.get("customer_count"),
                "facility_count": row.get("depot_count"),
                "platform_count": None,
                "depot_count": row.get("depot_count"),
                "vehicle_capacity": None,
                "lower_bound": None,
                "upper_bound": None,
                "total_demand": row.get("total_demand"),
                "total_capacity": row.get("total_capacity"),
                "file_count": 2,
                "likely_instance_count": 2,
                "format_hints": {},
                "suffixes": {},
                "note": row.get("note"),
                "research_boundary": summary.get("research_boundary"),
            }
        )
    return entries


def build_normalized_manifest() -> dict[str, Any]:
    inventory_summary = load_json_payload(BENCHMARK_INVENTORY_SUMMARY_PATH)
    parse_summary = load_json_payload(BENCHMARK_PARSE_SUMMARY_PATH)
    parse_pairs_summary = load_json_payload(BENCHMARK_PARSE_PAIRS_SUMMARY_PATH)

    entries = [
        *_normalise_inventory_entries(inventory_summary),
        *_normalise_parse_sample_entries(parse_summary),
        *_normalise_parse_pair_entries(parse_pairs_summary),
    ]
    entries.sort(key=lambda item: (item.get("entry_kind", ""), item.get("collection", ""), item.get("instance_name", "")))

    summary = {
        "inventory_collections": len(_normalise_inventory_entries(inventory_summary)),
        "inventory_files": inventory_summary.get("total_files"),
        "inventory_likely_instance_files": inventory_summary.get("likely_instance_files"),
        "parse_sample_entries": len(_normalise_parse_sample_entries(parse_summary)),
        "parse_pair_entries": len(_normalise_parse_pair_entries(parse_pairs_summary)),
        "total_entries": len(entries),
        "entry_kinds": dict(Counter(entry.get("entry_kind", "unknown") for entry in entries)),
        "schema_names": sorted({entry.get("schema_name") for entry in entries if entry.get("schema_name")}),
        "collections": sorted({entry.get("collection") for entry in entries if entry.get("collection")}),
        "research_boundary": (
            "Unified manifest only; public benchmark assets remain non-okra datasets and are used for future solver "
            "experiments, parser validation, and scalability comparison."
        ),
    }

    return {
        "manifest_name": "public_lrp_benchmark_normalized_manifest",
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_summary": {
            "inventory": inventory_summary,
            "parse_samples": parse_summary,
            "parse_pairs": parse_pairs_summary,
        },
        "summary": summary,
        "entries": entries,
    }


def load_normalized_manifest(prefer_file: bool = True) -> dict[str, Any]:
    if prefer_file and NORMALIZED_MANIFEST_PATH.exists():
        return load_json_payload(NORMALIZED_MANIFEST_PATH)
    return build_normalized_manifest()


def write_normalized_manifest_artifacts(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = payload or build_normalized_manifest()
    NORMALIZED_OUT_DIR.mkdir(parents=True, exist_ok=True)

    NORMALIZED_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    entries = manifest.get("entries", [])
    csv_fields = [
        "entry_id",
        "entry_kind",
        "schema_name",
        "collection",
        "parser_name",
        "instance_name",
        "source_path",
        "source_paths",
        "customer_count",
        "facility_count",
        "platform_count",
        "depot_count",
        "vehicle_capacity",
        "lower_bound",
        "upper_bound",
        "total_demand",
        "total_capacity",
        "file_count",
        "likely_instance_count",
        "format_hints",
        "suffixes",
        "note",
        "research_boundary",
    ]
    with NORMALIZED_CSV_PATH.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "entry_id": entry.get("entry_id"),
                    "entry_kind": entry.get("entry_kind"),
                    "schema_name": entry.get("schema_name"),
                    "collection": entry.get("collection"),
                    "parser_name": entry.get("parser_name"),
                    "instance_name": entry.get("instance_name"),
                    "source_path": entry.get("source_path"),
                    "source_paths": _stringify_mapping(entry.get("source_paths")),
                    "customer_count": entry.get("customer_count"),
                    "facility_count": entry.get("facility_count"),
                    "platform_count": entry.get("platform_count"),
                    "depot_count": entry.get("depot_count"),
                    "vehicle_capacity": entry.get("vehicle_capacity"),
                    "lower_bound": entry.get("lower_bound"),
                    "upper_bound": entry.get("upper_bound"),
                    "total_demand": entry.get("total_demand"),
                    "total_capacity": entry.get("total_capacity"),
                    "file_count": entry.get("file_count"),
                    "likely_instance_count": entry.get("likely_instance_count"),
                    "format_hints": _stringify_mapping(entry.get("format_hints")),
                    "suffixes": _stringify_mapping(entry.get("suffixes")),
                    "note": entry.get("note"),
                    "research_boundary": entry.get("research_boundary"),
                }
            )

    lines = [
        "# Benchmark Normalized Manifest",
        "",
        f"- Manifest name: `{manifest.get('manifest_name')}`",
        f"- Schema version: `{manifest.get('schema_version')}`",
        f"- Generated at UTC: `{manifest.get('generated_at_utc')}`",
        f"- Total entries: {manifest.get('summary', {}).get('total_entries')}",
        f"- Inventory collections: {manifest.get('summary', {}).get('inventory_collections')}",
        f"- Parsed single-file samples: {manifest.get('summary', {}).get('parse_sample_entries')}",
        f"- Parsed paired samples: {manifest.get('summary', {}).get('parse_pair_entries')}",
        "",
        "## Entry Kinds",
        "",
        "| Kind | Count |",
        "| --- | ---: |",
    ]
    for kind, count in sorted(manifest.get("summary", {}).get("entry_kinds", {}).items()):
        lines.append(f"| {kind} | {count} |")
    lines.extend(
        [
            "",
            "## Unified Entries",
            "",
            "| Kind | Collection | Instance | Schema | Customers | Facilities | Platforms | Demand | Capacity |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for entry in entries:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(entry.get("entry_kind", "")),
                    str(entry.get("collection", "")),
                    str(entry.get("instance_name", "")),
                    str(entry.get("schema_name", "")),
                    str(entry.get("customer_count", "") or ""),
                    str(entry.get("facility_count", "") or ""),
                    str(entry.get("platform_count", "") or ""),
                    str(entry.get("total_demand", "") or ""),
                    str(entry.get("total_capacity", "") or ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Research Boundary",
            "",
            manifest.get("summary", {}).get("research_boundary", ""),
        ]
    )
    NORMALIZED_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest
