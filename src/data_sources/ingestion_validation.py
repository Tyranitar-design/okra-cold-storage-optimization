"""Validate raw and cleaned real-data ingestion artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.data_sources.ingestion_manifest import DATASETS, PROJECT_ROOT


RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
VALIDATION_JSON_PATH = RESULT_DIR / "real_data_ingestion_validation.json"
VALIDATION_MD_PATH = RESULT_DIR / "real_data_ingestion_validation.md"


def _csv_columns(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            return [str(col).strip() for col in next(reader, [])]
    except Exception:
        return []


def _json_top_level_keys(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())
    return []


def _file_columns(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if not path.exists():
        return []
    if suffix == ".csv":
        return _csv_columns(path)
    if suffix in {".json", ".geojson"}:
        return _json_top_level_keys(path)
    return []


def _validate_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    raw_path = Path(dataset["raw_path"])
    cleaned_path = Path(dataset["cleaned_path"])
    required_columns = [str(col) for col in dataset.get("required_columns", [])]
    cleaned_columns = _file_columns(cleaned_path)
    missing_required = [
        column for column in required_columns
        if column not in cleaned_columns
    ]
    raw_exists = raw_path.exists()
    cleaned_exists = cleaned_path.exists()

    if cleaned_exists and not missing_required:
        validation_state = "cleaned_valid_ready_for_apply"
        next_action = "Apply cleaned data to PostgreSQL after probe_ok=true and preserve apply logs."
    elif cleaned_exists:
        validation_state = "cleaned_present_missing_required_columns"
        next_action = "Fix cleaned artifact column mapping before any PostgreSQL apply."
    elif raw_exists:
        validation_state = "raw_present_cleaned_missing"
        next_action = "Run the cleaning adapter and generate the cleaned artifact."
    else:
        validation_state = "missing_raw_and_cleaned"
        next_action = "Download or export the raw official/public dataset first."

    return {
        "dataset_id": dataset["dataset_id"],
        "source_id": dataset["source_id"],
        "target_table": dataset["target_table"],
        "raw_path": str(raw_path),
        "cleaned_path": str(cleaned_path),
        "raw_exists": raw_exists,
        "cleaned_exists": cleaned_exists,
        "cleaned_columns": cleaned_columns,
        "required_columns": required_columns,
        "missing_required_columns": missing_required,
        "validation_state": validation_state,
        "next_action": next_action,
        "claim_boundary": (
            "A dataset is ingestion-ready only when the cleaned artifact exists and all required columns are present. "
            "This validator does not prove PostgreSQL apply unless apply logs are also preserved."
        ),
    }


def build_real_data_ingestion_validation() -> dict[str, Any]:
    datasets = [_validate_dataset(dataset) for dataset in DATASETS]
    state_counts: dict[str, int] = {}
    for item in datasets:
        state_counts[item["validation_state"]] = state_counts.get(item["validation_state"], 0) + 1
    ready_count = sum(1 for item in datasets if item["validation_state"] == "cleaned_valid_ready_for_apply")
    return {
        "source_name": "real external data ingestion validation",
        "dataset_count": len(datasets),
        "ready_for_apply_count": ready_count,
        "state_counts": state_counts,
        "datasets": datasets,
        "output_paths": {
            "json": str(VALIDATION_JSON_PATH),
            "markdown": str(VALIDATION_MD_PATH),
        },
        "research_boundary": (
            "This validation checks local raw/cleaned file presence and cleaned-file columns only. "
            "It does not download data, grant authorization, or prove PostgreSQL insertion."
        ),
    }


def render_validation_markdown(report: dict[str, Any]) -> str:
    rows = [
        "| dataset_id | target_table | raw | cleaned | missing_required | state |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("datasets", []):
        rows.append(
            "| {dataset_id} | {target_table} | {raw} | {cleaned} | {missing} | {state} |".format(
                dataset_id=item.get("dataset_id", ""),
                target_table=item.get("target_table", ""),
                raw="yes" if item.get("raw_exists") else "no",
                cleaned="yes" if item.get("cleaned_exists") else "no",
                missing=", ".join(item.get("missing_required_columns", [])) or "-",
                state=item.get("validation_state", ""),
            )
        )
    return "\n".join(
        [
            "# Real Data Ingestion Validation",
            "",
            f"Dataset count: {report.get('dataset_count', 0)}",
            f"Ready for apply: {report.get('ready_for_apply_count', 0)}",
            "",
            "## State Counts",
            "",
            json.dumps(report.get("state_counts", {}), ensure_ascii=False, indent=2),
            "",
            "## Datasets",
            "",
            *rows,
            "",
            "## Boundary",
            "",
            str(report.get("research_boundary", "")),
            "",
        ]
    )


def write_real_data_ingestion_validation(out_dir: Path | None = None) -> dict[str, str]:
    report = build_real_data_ingestion_validation()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / VALIDATION_JSON_PATH.name
    md_path = destination / VALIDATION_MD_PATH.name
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_validation_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
