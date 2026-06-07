"""Registry helpers for real data source validation and evidence tracking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.api.services import load_csv_records, load_text_content


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_SOURCE_REGISTRY_PATH = PROJECT_ROOT / "docs" / "data_source_registry.csv"
REAL_DATA_SOURCE_NOTE_PATH = PROJECT_ROOT / "docs" / "真实数据源核验记录_2026-05-27.md"


@dataclass(frozen=True)
class RealDataSourceRecord:
    source_id: str
    source_name: str
    owner: str
    access_url: str
    status: str
    priority: str
    intended_use: str
    notes: str


def load_real_data_source_registry(path: str | Path = DATA_SOURCE_REGISTRY_PATH) -> List[Dict[str, Any]]:
    rows = load_csv_records(path)
    return [row for row in rows if str(row.get("status", "")).strip()]


def iter_real_data_source_records(path: str | Path = DATA_SOURCE_REGISTRY_PATH) -> Iterable[RealDataSourceRecord]:
    for row in load_real_data_source_registry(path):
        yield RealDataSourceRecord(
            source_id=str(row.get("source_id", "")),
            source_name=str(row.get("source_name", "")),
            owner=str(row.get("owner", "")),
            access_url=str(row.get("access_url", "")),
            status=str(row.get("status", "")),
            priority=str(row.get("priority", "")),
            intended_use=str(row.get("intended_use", "")),
            notes=str(row.get("notes", "")),
        )


def build_real_data_source_report(limit: int = 50) -> Dict[str, Any]:
    rows = load_real_data_source_registry()
    preview = rows[: max(0, limit)]
    note_text = load_text_content(REAL_DATA_SOURCE_NOTE_PATH)
    return {
        "count": len(rows),
        "preview": preview,
        "registry_path": str(DATA_SOURCE_REGISTRY_PATH),
        "note_path": str(REAL_DATA_SOURCE_NOTE_PATH),
        "note_exists": REAL_DATA_SOURCE_NOTE_PATH.exists(),
        "note_excerpt": note_text[:1200],
        "statuses": sorted({str(row.get("status", "")) for row in rows if row.get("status")}),
        "priorities": sorted({str(row.get("priority", "")) for row in rows if row.get("priority")}),
    }
