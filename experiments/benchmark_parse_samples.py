"""Parse a conservative subset of local LRP benchmark instances.

This script intentionally starts with single-file formats whose headers encode
the instance size. It produces a manifest for later solver experiments; it does
not claim any okra-specific validation.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = PROJECT_ROOT / "lrp-instances"
OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benchmark_parse_samples"


@dataclass(frozen=True)
class ParsedBenchmark:
    parser_name: str
    relative_path: str
    instance_name: str
    customer_count: int | None
    facility_count: int | None
    platform_count: int | None
    vehicle_capacity: float | None
    total_demand: float | None
    lower_bound: float | None
    upper_bound: float | None
    parse_status: str
    note: str


def numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            rows.append([float(part) for part in stripped.split()])
        except ValueError:
            continue
    return rows


def parse_akca(path: Path) -> ParsedBenchmark:
    rows = numeric_rows(path)
    if len(rows) < 3 or len(rows[0]) < 5:
        return failure("akca", path, "not enough numeric rows")
    customer_count = int(rows[0][0])
    facility_count = int(rows[0][1])
    vehicle_capacity = rows[0][2]
    lower_bound = rows[1][0] if len(rows[1]) > 0 else None
    upper_bound = rows[1][1] if len(rows[1]) > 1 else None
    customers = rows[2 : 2 + customer_count]
    facilities = rows[2 + customer_count : 2 + customer_count + facility_count]
    if len(customers) != customer_count or len(facilities) != facility_count:
        return failure("akca", path, "row count mismatch")
    total_demand = sum(row[3] for row in customers if len(row) >= 4)
    return ParsedBenchmark(
        parser_name="akca",
        relative_path=str(path.relative_to(PROJECT_ROOT)),
        instance_name=path.name,
        customer_count=customer_count,
        facility_count=facility_count,
        platform_count=None,
        vehicle_capacity=vehicle_capacity,
        total_demand=total_demand,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        parse_status="ok",
        note="single-file AKCA parser",
    )


def parse_contardo(path: Path) -> ParsedBenchmark:
    rows = numeric_rows(path)
    if len(rows) < 3 or len(rows[0]) < 8:
        return failure("contardo", path, "not enough numeric rows")
    customer_count = int(rows[0][0])
    satellite_count = int(rows[0][1])
    platform_count = int(rows[0][2])
    vehicle_capacity = rows[0][3]
    lower_bound = rows[1][0] if len(rows[1]) > 0 else None
    upper_bound = rows[1][1] if len(rows[1]) > 1 else None
    customers = rows[2 : 2 + customer_count]
    facilities = rows[2 + customer_count : 2 + customer_count + satellite_count]
    platforms = rows[2 + customer_count + satellite_count : 2 + customer_count + satellite_count + platform_count]
    if len(customers) != customer_count or len(facilities) != satellite_count or len(platforms) != platform_count:
        return failure("contardo", path, "row count mismatch")
    total_demand = sum(row[3] for row in customers if len(row) >= 4)
    return ParsedBenchmark(
        parser_name="contardo",
        relative_path=str(path.relative_to(PROJECT_ROOT)),
        instance_name=path.name,
        customer_count=customer_count,
        facility_count=satellite_count,
        platform_count=platform_count,
        vehicle_capacity=vehicle_capacity,
        total_demand=total_demand,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        parse_status="ok",
        note="single-file Contardo two-echelon parser summary",
    )


def failure(parser_name: str, path: Path, note: str) -> ParsedBenchmark:
    return ParsedBenchmark(
        parser_name=parser_name,
        relative_path=str(path.relative_to(PROJECT_ROOT)),
        instance_name=path.name,
        customer_count=None,
        facility_count=None,
        platform_count=None,
        vehicle_capacity=None,
        total_demand=None,
        lower_bound=None,
        upper_bound=None,
        parse_status="failed",
        note=note,
    )


def sample_paths() -> list[tuple[str, Path, Callable[[Path], ParsedBenchmark]]]:
    specs: list[tuple[str, Path, Callable[[Path], ParsedBenchmark]]] = []
    for path in sorted((BENCH_ROOT / "akca" / "instances").glob("*"))[:6]:
        if path.is_file():
            specs.append(("akca", path, parse_akca))
    for path in sorted((BENCH_ROOT / "contardo" / "instances").glob("*"))[:6]:
        if path.is_file():
            specs.append(("contardo", path, parse_contardo))
    return specs


def write_csv(rows: list[ParsedBenchmark], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()) if rows else ["parser_name"])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_markdown(rows: list[ParsedBenchmark], path: Path) -> None:
    ok_count = sum(1 for row in rows if row.parse_status == "ok")
    lines = [
        "# Benchmark Parse Samples",
        "",
        f"- Parsed sample count: {len(rows)}",
        f"- Successful parses: {ok_count}",
        "- Scope: AKCA and Contardo single-file benchmark samples only.",
        "",
        "| Parser | Instance | Customers | Facilities | Platforms | Demand | UB | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.parser_name,
                    row.instance_name,
                    str(row.customer_count or ""),
                    str(row.facility_count or ""),
                    str(row.platform_count or ""),
                    f"{row.total_demand:.2f}" if row.total_demand is not None else "",
                    f"{row.upper_bound:.2f}" if row.upper_bound is not None else "",
                    row.parse_status,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Research Boundary",
            "",
            "These parsed samples support parser validation and later solver scalability experiments. "
            "They are not okra enterprise data and should not be used for okra business performance claims.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows: list[ParsedBenchmark] = []
    for _, path, parser in sample_paths():
        rows.append(parser(path))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(rows, OUT_DIR / "benchmark_parse_samples.csv")
    summary = {
        "sample_count": len(rows),
        "successful_parses": sum(1 for row in rows if row.parse_status == "ok"),
        "failed_parses": sum(1 for row in rows if row.parse_status != "ok"),
        "parsers": sorted({row.parser_name for row in rows}),
        "research_boundary": (
            "Parser validation samples only; not okra enterprise validation."
        ),
        "rows": [asdict(row) for row in rows],
    }
    (OUT_DIR / "benchmark_parse_samples_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(rows, OUT_DIR / "benchmark_parse_samples.md")
    print(json.dumps({k: summary[k] for k in ["sample_count", "successful_parses", "failed_parses", "parsers"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
