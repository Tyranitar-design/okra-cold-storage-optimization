"""Normalize parsed benchmark samples into a unified internal schema.

This is a data-preparation step for future solver experiments. It does not
claim any okra enterprise validity; it standardizes public benchmark assets so
future parsers/solvers can consume one schema.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = PROJECT_ROOT / "lrp-instances"
OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benchmark_normalized_samples"


@dataclass(frozen=True)
class NormalizedInstance:
    parser_name: str
    collection: str
    instance_name: str
    source_path: str
    schema_name: str
    customer_count: int | None
    facility_count: int | None
    satellite_count: int | None
    platform_count: int | None
    vehicle_capacity: float | None
    lower_bound: float | None
    upper_bound: float | None
    total_demand: float | None
    total_capacity: float | None
    node_count: int
    customer_nodes: int
    facility_nodes: int
    depot_nodes: int
    notes: str
    normalized_payload: dict[str, Any]


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


def normalize_akca(path: Path) -> NormalizedInstance:
    rows = numeric_rows(path)
    header = rows[0]
    customer_count = int(header[0])
    facility_count = int(header[1])
    vehicle_capacity = header[2]
    lower_bound = rows[1][0] if len(rows) > 1 else None
    upper_bound = rows[1][1] if len(rows[1]) > 1 else None
    customers = rows[2 : 2 + customer_count]
    facilities = rows[2 + customer_count : 2 + customer_count + facility_count]
    customer_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "demand": r[3], "node_type": "customer"}
        for r in customers
        if len(r) >= 4
    ]
    facility_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "fixed_cost": r[3], "capacity": r[4], "max_vehicles": r[5] if len(r) > 5 else None, "node_type": "facility"}
        for r in facilities
        if len(r) >= 5
    ]
    payload = {
        "metadata": {
            "schema": "akca",
            "header": {"customer_count": customer_count, "facility_count": facility_count, "vehicle_capacity": vehicle_capacity, "lower_bound": lower_bound, "upper_bound": upper_bound},
        },
        "customers": customer_nodes,
        "facilities": facility_nodes,
    }
    return NormalizedInstance(
        parser_name="akca",
        collection="akca",
        instance_name=path.name,
        source_path=str(path.relative_to(PROJECT_ROOT)),
        schema_name="single_file_lrp",
        customer_count=customer_count,
        facility_count=facility_count,
        satellite_count=None,
        platform_count=None,
        vehicle_capacity=vehicle_capacity,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        total_demand=sum(n["demand"] for n in customer_nodes),
        total_capacity=sum(n["capacity"] for n in facility_nodes),
        node_count=len(customer_nodes) + len(facility_nodes),
        customer_nodes=len(customer_nodes),
        facility_nodes=len(facility_nodes),
        depot_nodes=0,
        notes="AKCA single-file normalized sample.",
        normalized_payload=payload,
    )


def normalize_contardo(path: Path) -> NormalizedInstance:
    rows = numeric_rows(path)
    header = rows[0]
    customer_count = int(header[0])
    satellite_count = int(header[1])
    platform_count = int(header[2])
    vehicle_capacity = header[3]
    lower_bound = rows[1][0] if len(rows) > 1 else None
    upper_bound = rows[1][1] if len(rows[1]) > 1 else None
    customers = rows[2 : 2 + customer_count]
    satellites = rows[2 + customer_count : 2 + customer_count + satellite_count]
    platforms = rows[2 + customer_count + satellite_count : 2 + customer_count + satellite_count + platform_count]
    customer_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "demand": r[3], "node_type": "customer"}
        for r in customers
        if len(r) >= 4
    ]
    satellite_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "fixed_cost": r[3], "capacity": r[4], "node_type": "satellite"}
        for r in satellites
        if len(r) >= 5
    ]
    platform_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "fixed_cost": r[3], "capacity": r[4], "node_type": "platform"}
        for r in platforms
        if len(r) >= 5
    ]
    payload = {
        "metadata": {
            "schema": "contardo",
            "header": {"customer_count": customer_count, "satellite_count": satellite_count, "platform_count": platform_count, "vehicle_capacity": vehicle_capacity, "lower_bound": lower_bound, "upper_bound": upper_bound},
        },
        "customers": customer_nodes,
        "satellites": satellite_nodes,
        "platforms": platform_nodes,
    }
    return NormalizedInstance(
        parser_name="contardo",
        collection="contardo",
        instance_name=path.name,
        source_path=str(path.relative_to(PROJECT_ROOT)),
        schema_name="two_echelon_lrp",
        customer_count=customer_count,
        facility_count=satellite_count,
        satellite_count=satellite_count,
        platform_count=platform_count,
        vehicle_capacity=vehicle_capacity,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        total_demand=sum(n["demand"] for n in customer_nodes),
        total_capacity=sum(n["capacity"] for n in satellite_nodes) + sum(n["capacity"] for n in platform_nodes),
        node_count=len(customer_nodes) + len(satellite_nodes) + len(platform_nodes),
        customer_nodes=len(customer_nodes),
        facility_nodes=len(satellite_nodes) + len(platform_nodes),
        depot_nodes=0,
        notes="Contardo normalized sample.",
        normalized_payload=payload,
    )


def normalize_barreto(customer_path: Path, depot_path: Path) -> NormalizedInstance:
    customer_rows = numeric_rows(customer_path)
    depot_rows = numeric_rows(depot_path)
    customer_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "demand": r[3], "node_type": "customer"}
        for r in customer_rows
        if len(r) >= 4
    ]
    depot_nodes = [
        {"node_id": int(r[0]), "x": r[1], "y": r[2], "capacity": r[3], "fixed_cost": r[4] if len(r) > 4 else None, "variable_cost": r[5] if len(r) > 5 else None, "node_type": "depot"}
        for r in depot_rows
        if len(r) >= 4
    ]
    payload = {
        "metadata": {
            "schema": "barreto_pair",
            "customer_file": str(customer_path.relative_to(PROJECT_ROOT)),
            "depot_file": str(depot_path.relative_to(PROJECT_ROOT)),
        },
        "customers": customer_nodes,
        "depots": depot_nodes,
    }
    collection = customer_path.parts[len(BENCH_ROOT.parts)] if len(customer_path.parts) > len(BENCH_ROOT.parts) else "barreto"
    return NormalizedInstance(
        parser_name="barreto_pair",
        collection="barreto",
        instance_name=customer_path.name,
        source_path=str(customer_path.relative_to(PROJECT_ROOT)),
        schema_name="paired_lrp",
        customer_count=len(customer_nodes),
        facility_count=len(depot_nodes),
        satellite_count=None,
        platform_count=None,
        vehicle_capacity=None,
        lower_bound=None,
        upper_bound=None,
        total_demand=sum(n["demand"] for n in customer_nodes),
        total_capacity=sum(n["capacity"] for n in depot_nodes),
        node_count=len(customer_nodes) + len(depot_nodes),
        customer_nodes=len(customer_nodes),
        facility_nodes=len(depot_nodes),
        depot_nodes=len(depot_nodes),
        notes="Barreto paired customer/depot normalized sample.",
        normalized_payload=payload,
    )


def write_csv(rows: list[NormalizedInstance], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "parser_name",
                "collection",
                "instance_name",
                "source_path",
                "schema_name",
                "customer_count",
                "facility_count",
                "satellite_count",
                "platform_count",
                "vehicle_capacity",
                "lower_bound",
                "upper_bound",
                "total_demand",
                "total_capacity",
                "node_count",
                "customer_nodes",
                "facility_nodes",
                "depot_nodes",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            d = asdict(row).copy()
            d.pop("normalized_payload", None)
            writer.writerow(d)


def main() -> int:
    rows: list[NormalizedInstance] = []
    for path in sorted((BENCH_ROOT / "akca" / "instances").glob("*"))[:4]:
        if path.is_file():
            rows.append(normalize_akca(path))
    for path in sorted((BENCH_ROOT / "contardo" / "instances").glob("*"))[:4]:
        if path.is_file():
            rows.append(normalize_contardo(path))
    barreto_customer_dir = BENCH_ROOT / "barreto" / "instances-barreto-format" / "customers-files"
    barreto_depot_dir = BENCH_ROOT / "barreto" / "instances-barreto-format" / "depots-files"
    for customer_path in sorted(barreto_customer_dir.glob("*"))[:4]:
        if not customer_path.is_file():
            continue
        depot_path = barreto_depot_dir / customer_path.name.replace("Cli", "Dep")
        if depot_path.exists():
            rows.append(normalize_barreto(customer_path, depot_path))

    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / "benchmark_normalized_samples.csv")
    (out_dir / "benchmark_normalized_samples.json").write_text(
        json.dumps({"count": len(rows), "rows": [asdict(row) for row in rows]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "benchmark_normalized_samples.md").write_text(
        "\n".join(
            [
                "# Benchmark Normalized Samples",
                "",
                f"- Normalized rows: {len(rows)}",
                f"- Parsers: {', '.join(sorted({row.parser_name for row in rows}))}",
                "",
                "These normalized samples are a preparation layer for later solver experiments, not okra enterprise validation.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"count": len(rows), "parsers": sorted({row.parser_name for row in rows})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
