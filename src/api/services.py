"""Service helpers for the API layer."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Sequence

import pandas as pd


def load_csv_records(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return pd.read_csv(p).to_dict(orient="records")


def load_text_content(path: str | Path) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def load_csv_text(path: str | Path) -> str:
    return load_text_content(path)


def load_json_records(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    payload = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def load_json_payload(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_pickle_payload(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("rb") as fh:
        payload = pickle.load(fh)
    if isinstance(payload, dict):
        return payload
    return {"value": payload}


def iter_records_with_limit(records: Sequence[dict[str, Any]], limit: int | None = None) -> Iterator[dict[str, Any]]:
    if limit is None or limit < 0:
        yield from records
        return
    for record in records[:limit]:
        yield record


def csv_rows_to_html_table(
    records: Sequence[dict[str, Any]],
    columns: Sequence[str],
    *,
    empty_message: str = "暂无数据",
) -> str:
    if not records:
        return f"<tr><td colspan='{len(columns)}'>{empty_message}</td></tr>"
    body: list[str] = []
    for record in records:
        cells = "".join(f"<td>{record.get(column, '')}</td>" for column in columns)
        body.append(f"<tr>{cells}</tr>")
    return "".join(body)


def safe_unique_values(records: Iterable[dict[str, Any]], field: str) -> list[Any]:
    seen: list[Any] = []
    for record in records:
        value = record.get(field)
        if value not in seen:
            seen.append(value)
    return seen
