"""Inventory local public LRP benchmark assets.

The goal is provenance and scalability planning, not claiming that these
benchmarks are okra enterprise data. The script records what is locally
available, detects likely instance files, and writes auditable CSV/JSON/MD
summaries for later solver experiments.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = PROJECT_ROOT / "lrp-instances"
OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benchmark_inventory"


FORMAT_HINTS = {
    "akca": "akca",
    "barreto": "barreto/prodhon",
    "contardo": "contardo",
    "duhamel": "duhamel",
    "harks": "harks",
    "nguyen": "nguyen",
    "prins": "prins",
    "prodhon": "prodhon",
    "schneider": "schneider",
    "tuzun": "tuzun",
}

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache"}
DOCUMENT_SUFFIXES = {".md", ".txt", ".cff", ".jpg", ".jpeg", ".png", ".pdf"}
DOCUMENT_NAMES = {"readme.md", "citation.cff"}


@dataclass(frozen=True)
class BenchmarkFile:
    collection: str
    relative_path: str
    file_name: str
    suffix: str
    size_bytes: int
    likely_instance: bool
    format_hint: str


def is_likely_instance(path: Path) -> bool:
    name = path.name.lower()
    if name in DOCUMENT_NAMES:
        return False
    if "format" in name or name.endswith(".jpg") or name.endswith(".png"):
        return False
    if path.suffix.lower() in DOCUMENT_SUFFIXES:
        return False
    return True


def detect_collection(path: Path) -> str:
    rel = path.relative_to(BENCH_ROOT)
    return rel.parts[0] if rel.parts else "root"


def detect_format_hint(path: Path) -> str:
    parts = [part.lower() for part in path.relative_to(BENCH_ROOT).parts]
    joined = "/".join(parts)
    for key, hint in FORMAT_HINTS.items():
        if key in joined:
            return hint
    return "unknown"


def read_text_head(path: Path, max_chars: int = 2000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def inventory_files() -> list[BenchmarkFile]:
    if not BENCH_ROOT.exists():
        return []
    rows: list[BenchmarkFile] = []
    for path in sorted(BENCH_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(BENCH_ROOT).parts):
            continue
        rows.append(
            BenchmarkFile(
                collection=detect_collection(path),
                relative_path=str(path.relative_to(PROJECT_ROOT)),
                file_name=path.name,
                suffix=path.suffix.lower() or "(none)",
                size_bytes=path.stat().st_size,
                likely_instance=is_likely_instance(path),
                format_hint=detect_format_hint(path),
            )
        )
    return rows


def build_summary(rows: list[BenchmarkFile]) -> dict[str, Any]:
    total_files = len(rows)
    likely_instances = [row for row in rows if row.likely_instance]
    by_collection: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[BenchmarkFile]] = defaultdict(list)
    for row in rows:
        grouped[row.collection].append(row)
    for collection, items in sorted(grouped.items()):
        by_collection[collection] = {
            "files": len(items),
            "likely_instances": sum(1 for item in items if item.likely_instance),
            "formats": dict(Counter(item.format_hint for item in items)),
            "suffixes": dict(Counter(item.suffix for item in items)),
        }
    citation_path = BENCH_ROOT / "CITATION.cff"
    readme_path = BENCH_ROOT / "README.md"
    return {
        "benchmark_root": str(BENCH_ROOT),
        "total_files": total_files,
        "likely_instance_files": len(likely_instances),
        "collections": by_collection,
        "citation_exists": citation_path.exists(),
        "readme_exists": readme_path.exists(),
        "citation_preview": read_text_head(citation_path, 1200),
        "readme_preview": read_text_head(readme_path, 1200),
        "research_boundary": (
            "These public LRP benchmarks can support solver scalability and "
            "method comparison experiments. They are not okra enterprise data "
            "and must not be used as evidence of real okra business performance."
        ),
    }


def write_csv(rows: list[BenchmarkFile], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()) if rows else ["collection"])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# LRP Benchmark Inventory",
        "",
        f"- Benchmark root: `{summary['benchmark_root']}`",
        f"- Total files: {summary['total_files']}",
        f"- Likely instance files: {summary['likely_instance_files']}",
        f"- Root README exists: {summary['readme_exists']}",
        f"- CITATION.cff exists: {summary['citation_exists']}",
        "",
        "## Collections",
        "",
        "| Collection | Files | Likely instances | Format hints |",
        "| --- | ---: | ---: | --- |",
    ]
    for collection, item in summary["collections"].items():
        formats = ", ".join(f"{k}:{v}" for k, v in item["formats"].items())
        lines.append(f"| {collection} | {item['files']} | {item['likely_instances']} | {formats} |")
    lines.extend(
        [
            "",
            "## Research Boundary",
            "",
            summary["research_boundary"],
            "",
            "## Next Use",
            "",
            "1. Select a small subset from each format family.",
            "2. Write format-specific parsers with unit checks.",
            "3. Run classic Benders and AI-Benders on matched subsets.",
            "4. Report these as benchmark scalability experiments, not okra enterprise validation.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows = inventory_files()
    summary = build_summary(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(rows, OUT_DIR / "benchmark_inventory.csv")
    (OUT_DIR / "benchmark_inventory_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(summary, OUT_DIR / "benchmark_inventory.md")
    print(json.dumps({k: summary[k] for k in ["total_files", "likely_instance_files", "citation_exists", "readme_exists"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
