"""Parse paired benchmark files (customer / depot formats) conservatively.

This covers datasets like Barreto/Gaskell/Daskin/Ch69 where customer and depot
files are separate. The script produces a manifest with parsed counts and a
research boundary for later solver experiments.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = PROJECT_ROOT / "lrp-instances"
OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benchmark_parse_pairs"


@dataclass(frozen=True)
class ParsedPair:
    collection: str
    customer_file: str
    depot_file: str
    parser_name: str
    customer_count: int | None
    depot_count: int | None
    total_demand: float | None
    total_capacity: float | None
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


def guess_counts_from_name(name: str) -> tuple[int | None, int | None]:
    match = re.search(r"Cli(\d+)x(\d+)", name)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def parse_customer_file(path: Path) -> tuple[int | None, float | None, str]:
    rows = numeric_rows(path)
    if not rows:
        return None, None, "no numeric rows"
    expected = None
    customer_count = len(rows)
    total_demand = sum(row[3] for row in rows if len(row) >= 4)
    return customer_count, total_demand, "ok"


def parse_depot_file(path: Path) -> tuple[int | None, float | None, str]:
    rows = numeric_rows(path)
    if not rows:
        return None, None, "no numeric rows"
    depot_count = len(rows)
    total_capacity = sum(row[3] for row in rows if len(row) >= 4)
    return depot_count, total_capacity, "ok"


def paired_entries() -> list[tuple[str, Path, Path]]:
    pairs: list[tuple[str, Path, Path]] = []
    for collection in sorted([p.name for p in BENCH_ROOT.iterdir() if p.is_dir()]):
        customer_dir = BENCH_ROOT / collection / "instances-barreto-format" / "customers-files"
        depot_dir = BENCH_ROOT / collection / "instances-barreto-format" / "depots-files"
        if customer_dir.exists() and depot_dir.exists():
            for customer_file in sorted(customer_dir.iterdir()):
                if not customer_file.is_file():
                    continue
                depot_file = depot_dir / customer_file.name.replace("Cli", "Dep")
                if depot_file.exists() and depot_file.is_file():
                    pairs.append((collection, customer_file, depot_file))
    return pairs


def write_csv(rows: list[ParsedPair], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()) if rows else ["collection"])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_markdown(rows: list[ParsedPair], path: Path) -> None:
    lines = [
        "# Benchmark Parse Pairs",
        "",
        f"- Parsed pair count: {len(rows)}",
        f"- Successful parses: {sum(1 for row in rows if row.parse_status == 'ok')}",
        "",
        "| Collection | Customer file | Depot file | Customers | Depots | Demand | Capacity | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.collection} | {row.customer_file} | {row.depot_file} | "
            f"{row.customer_count or ''} | {row.depot_count or ''} | "
            f"{row.total_demand:.2f}" if row.total_demand is not None else "" + " | "
        )
    # Rebuild table in a simpler way to avoid formatting pitfalls.
    lines = [
        "# Benchmark Parse Pairs",
        "",
        f"- Parsed pair count: {len(rows)}",
        f"- Successful parses: {sum(1 for row in rows if row.parse_status == 'ok')}",
        "",
        "| Collection | Customer file | Depot file | Customers | Depots | Demand | Capacity | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.collection,
                    row.customer_file,
                    row.depot_file,
                    str(row.customer_count or ""),
                    str(row.depot_count or ""),
                    f"{row.total_demand:.2f}" if row.total_demand is not None else "",
                    f"{row.total_capacity:.2f}" if row.total_capacity is not None else "",
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
            "These pair parses only validate input handling for later solver experiments. "
            "They are not okra enterprise data and must not be used for business performance claims.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows: list[ParsedPair] = []
    for collection, customer_file, depot_file in paired_entries():
        customer_count, total_demand, customer_status = parse_customer_file(customer_file)
        depot_count, total_capacity, depot_status = parse_depot_file(depot_file)
        parse_status = "ok" if customer_status == "ok" and depot_status == "ok" else "failed"
        rows.append(
            ParsedPair(
                collection=collection,
                customer_file=str(customer_file.relative_to(PROJECT_ROOT)),
                depot_file=str(depot_file.relative_to(PROJECT_ROOT)),
                parser_name="barreto_pair",
                customer_count=customer_count,
                depot_count=depot_count,
                total_demand=total_demand,
                total_capacity=total_capacity,
                parse_status=parse_status,
                note="paired customer/depot format",
            )
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(rows, OUT_DIR / "benchmark_parse_pairs.csv")
    summary = {
        "pair_count": len(rows),
        "successful_parses": sum(1 for row in rows if row.parse_status == "ok"),
        "collections": sorted({row.collection for row in rows}),
        "research_boundary": "Pair parser validation only; not okra enterprise validation.",
        "rows": [asdict(row) for row in rows],
    }
    (OUT_DIR / "benchmark_parse_pairs_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(rows, OUT_DIR / "benchmark_parse_pairs.md")
    print(json.dumps({k: summary[k] for k in ["pair_count", "successful_parses", "collections"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
