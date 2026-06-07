"""Public LRP benchmark solver smoke test.

This script is the first executable step after the benchmark protocol. It
projects normalized public benchmark samples into a conservative capacitated
facility-location smoke model. The goal is to verify parser-to-solver input
readiness and produce auditable result tables. It is not a full LRP routing
solver and must not be reported as okra enterprise validation.
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from src.api.benchmark_manifest import load_normalized_manifest  # noqa: E402

try:
    import gurobipy as gp  # noqa: E402
    from gurobipy import GRB  # noqa: E402

    GUROBI_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - exercised only when env is incomplete
    gp = None
    GRB = None
    GUROBI_IMPORT_ERROR = str(exc)


OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benchmark_solver_smoke"
BENCH_ROOT = PROJECT_ROOT / "lrp-instances"


@dataclass(frozen=True)
class SmokeInstance:
    entry_id: str
    collection: str
    schema_name: str
    parser_name: str
    instance_name: str
    source_path: str
    customer_count: int
    facility_count: int
    total_demand: float
    total_capacity: float
    customers: list[dict[str, float]]
    facilities: list[dict[str, float]]


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _euclidean(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def parse_akca(entry: dict[str, Any]) -> SmokeInstance:
    path = PROJECT_ROOT / str(entry["source_path"])
    rows = numeric_rows(path)
    customer_count = int(rows[0][0])
    facility_count = int(rows[0][1])
    customers_raw = rows[2 : 2 + customer_count]
    facilities_raw = rows[2 + customer_count : 2 + customer_count + facility_count]
    customers = [
        {"node_id": int(row[0]), "x": row[1], "y": row[2], "demand": row[3]}
        for row in customers_raw
        if len(row) >= 4
    ]
    facilities = [
        {
            "node_id": int(row[0]),
            "x": row[1],
            "y": row[2],
            "fixed_cost": row[3],
            "capacity": row[4],
        }
        for row in facilities_raw
        if len(row) >= 5
    ]
    return SmokeInstance(
        entry_id=str(entry["entry_id"]),
        collection=str(entry["collection"]),
        schema_name=str(entry["schema_name"]),
        parser_name=str(entry["parser_name"]),
        instance_name=str(entry["instance_name"]),
        source_path=str(entry["source_path"]),
        customer_count=len(customers),
        facility_count=len(facilities),
        total_demand=sum(row["demand"] for row in customers),
        total_capacity=sum(row["capacity"] for row in facilities),
        customers=customers,
        facilities=facilities,
    )


def parse_contardo(entry: dict[str, Any]) -> SmokeInstance:
    path = PROJECT_ROOT / str(entry["source_path"])
    rows = numeric_rows(path)
    customer_count = int(rows[0][0])
    facility_count = int(rows[0][1])
    platform_count = int(rows[0][2])
    customers_raw = rows[2 : 2 + customer_count]
    satellite_raw = rows[2 + customer_count : 2 + customer_count + facility_count]
    platform_raw = rows[
        2 + customer_count + facility_count : 2 + customer_count + facility_count + platform_count
    ]
    customers = [
        {"node_id": int(row[0]), "x": row[1], "y": row[2], "demand": row[3]}
        for row in customers_raw
        if len(row) >= 4
    ]
    facilities: list[dict[str, float]] = []
    for row in [*satellite_raw, *platform_raw]:
        if len(row) >= 5:
            facilities.append(
                {
                    "node_id": int(row[0]),
                    "x": row[1],
                    "y": row[2],
                    "fixed_cost": row[3],
                    "capacity": row[4],
                }
            )
    return SmokeInstance(
        entry_id=str(entry["entry_id"]),
        collection=str(entry["collection"]),
        schema_name=str(entry["schema_name"]),
        parser_name=str(entry["parser_name"]),
        instance_name=str(entry["instance_name"]),
        source_path=str(entry["source_path"]),
        customer_count=len(customers),
        facility_count=len(facilities),
        total_demand=sum(row["demand"] for row in customers),
        total_capacity=sum(row["capacity"] for row in facilities),
        customers=customers,
        facilities=facilities,
    )


def parse_barreto(entry: dict[str, Any]) -> SmokeInstance:
    source_paths = entry.get("source_paths", [])
    customer_path = PROJECT_ROOT / str(source_paths[0])
    depot_path = PROJECT_ROOT / str(source_paths[1])
    customer_rows = numeric_rows(customer_path)
    depot_rows = numeric_rows(depot_path)
    customers = [
        {"node_id": int(row[0]), "x": row[1], "y": row[2], "demand": row[3]}
        for row in customer_rows
        if len(row) >= 4
    ]
    facilities = [
        {
            "node_id": int(row[0]),
            "x": row[1],
            "y": row[2],
            "capacity": row[3],
            "fixed_cost": row[4] if len(row) > 4 else 0.0,
        }
        for row in depot_rows
        if len(row) >= 4
    ]
    return SmokeInstance(
        entry_id=str(entry["entry_id"]),
        collection=str(entry["collection"]),
        schema_name=str(entry["schema_name"]),
        parser_name=str(entry["parser_name"]),
        instance_name=str(entry["instance_name"]),
        source_path=str(entry["source_path"]),
        customer_count=len(customers),
        facility_count=len(facilities),
        total_demand=sum(row["demand"] for row in customers),
        total_capacity=sum(row["capacity"] for row in facilities),
        customers=customers,
        facilities=facilities,
    )


def parse_smoke_instance(entry: dict[str, Any]) -> SmokeInstance:
    parser_name = str(entry.get("parser_name", ""))
    if parser_name == "akca":
        return parse_akca(entry)
    if parser_name == "contardo":
        return parse_contardo(entry)
    if parser_name == "barreto_pair":
        return parse_barreto(entry)
    raise ValueError(f"Unsupported parser for smoke solver: {parser_name}")


def select_entries(manifest: dict[str, Any], max_instances: int) -> list[dict[str, Any]]:
    entries = [
        entry
        for entry in manifest.get("entries", [])
        if entry.get("entry_kind") in {"parsed_sample", "parsed_pair"}
        and _safe_float(entry.get("customer_count")) <= 50
        and _safe_float(entry.get("facility_count")) <= 10
        and _safe_float(entry.get("customer_count")) > 0
        and _safe_float(entry.get("facility_count")) > 0
    ]
    priority = {"akca": 0, "contardo": 1, "barreto_pair": 2}
    entries.sort(
        key=lambda entry: (
            priority.get(str(entry.get("parser_name")), 99),
            _safe_float(entry.get("customer_count")),
            str(entry.get("instance_name")),
        )
    )
    selected: list[dict[str, Any]] = []
    seen_parsers: set[str] = set()
    for entry in entries:
        parser_name = str(entry.get("parser_name"))
        if parser_name not in seen_parsers:
            selected.append(entry)
            seen_parsers.add(parser_name)
        if len(selected) >= max_instances:
            return selected
    for entry in entries:
        if entry not in selected:
            selected.append(entry)
        if len(selected) >= max_instances:
            break
    return selected


def solve_facility_projection(instance: SmokeInstance, time_limit: int, mip_gap: float) -> dict[str, Any]:
    if gp is None or GRB is None:
        return {
            "status_name": "GUROBI_IMPORT_FAILED",
            "status_code": None,
            "objective": None,
            "best_bound": None,
            "mip_gap_pct": None,
            "open_facilities": None,
            "elapsed_sec": None,
            "solver_model": "capacitated_facility_location_projection",
            "error": GUROBI_IMPORT_ERROR,
        }

    start = time.time()
    model = gp.Model(f"benchmark_facility_projection_{instance.instance_name}")
    model.setParam("OutputFlag", 0)
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)

    y = {
        j: model.addVar(vtype=GRB.BINARY, name=f"open_{j}")
        for j in range(instance.facility_count)
    }
    x = {
        (i, j): model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"assign_{i}_{j}")
        for i in range(instance.customer_count)
        for j in range(instance.facility_count)
    }

    for i in range(instance.customer_count):
        model.addConstr(
            gp.quicksum(x[i, j] for j in range(instance.facility_count)) == 1.0,
            name=f"assign_once_{i}",
        )
    for i in range(instance.customer_count):
        for j in range(instance.facility_count):
            model.addConstr(x[i, j] <= y[j], name=f"assign_open_{i}_{j}")
    for j, facility in enumerate(instance.facilities):
        model.addConstr(
            gp.quicksum(x[i, j] * instance.customers[i]["demand"] for i in range(instance.customer_count))
            <= facility["capacity"] * y[j],
            name=f"capacity_{j}",
        )

    assignment_cost = gp.quicksum(
        x[i, j]
        * instance.customers[i]["demand"]
        * _euclidean(instance.customers[i], instance.facilities[j])
        for i in range(instance.customer_count)
        for j in range(instance.facility_count)
    )
    fixed_cost = gp.quicksum(
        y[j] * max(0.0, float(instance.facilities[j].get("fixed_cost", 0.0)))
        for j in range(instance.facility_count)
    )
    model.setObjective(fixed_cost + assignment_cost, GRB.MINIMIZE)
    model.optimize()
    elapsed = time.time() - start

    sol_count = int(getattr(model, "SolCount", 0))
    open_count = 0
    if sol_count > 0:
        open_count = sum(1 for j in range(instance.facility_count) if y[j].X > 0.5)
    status_name = {
        2: "OPTIMAL",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        9: "TIME_LIMIT",
        13: "SUBOPTIMAL",
    }.get(int(model.Status), f"STATUS_{model.Status}")

    return {
        "status_name": status_name,
        "status_code": int(model.Status),
        "objective": float(model.ObjVal) if sol_count > 0 else None,
        "best_bound": float(model.ObjBound) if sol_count > 0 else None,
        "mip_gap_pct": float(model.MIPGap * 100.0) if sol_count > 0 else None,
        "open_facilities": open_count,
        "elapsed_sec": float(elapsed),
        "solver_model": "capacitated_facility_location_projection",
        "error": "",
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_empty_csv(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()


def write_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "entry_id",
        "parser_name",
        "instance_name",
        "customer_count",
        "facility_count",
        "total_demand",
        "total_capacity",
        "status_name",
        "objective",
        "mip_gap_pct",
        "elapsed_sec",
    ]
    lines = [
        "# Benchmark Solver Smoke",
        "",
        "This is a capacitated facility-location projection smoke test for public LRP benchmark parser-to-solver readiness.",
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    lines.extend(
        [
            "",
            "## Research Boundary",
            "",
            "This smoke test is not a full LRP routing benchmark and is not okra enterprise validation. "
            "It only checks whether normalized public benchmark samples can be projected into a small solver model.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    manifest = load_normalized_manifest(prefer_file=True)
    selected_entries = select_entries(manifest, max_instances=5)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in selected_entries:
        try:
            instance = parse_smoke_instance(entry)
            solve_result = solve_facility_projection(instance, time_limit=60, mip_gap=0.01)
            rows.append(
                {
                    "source_id": "DS-E-005",
                    "entry_id": instance.entry_id,
                    "collection": instance.collection,
                    "schema_name": instance.schema_name,
                    "parser_name": instance.parser_name,
                    "instance_name": instance.instance_name,
                    "source_path": instance.source_path,
                    "customer_count": instance.customer_count,
                    "facility_count": instance.facility_count,
                    "total_demand": instance.total_demand,
                    "total_capacity": instance.total_capacity,
                    **solve_result,
                }
            )
        except Exception as exc:
            failure = {
                "entry_id": entry.get("entry_id"),
                "parser_name": entry.get("parser_name"),
                "instance_name": entry.get("instance_name"),
                "status_name": "PARSE_OR_SOLVE_FAILED",
                "error": str(exc),
            }
            failures.append(failure)

    write_csv(rows, OUT_DIR / "benchmark_solver_runs.csv")
    write_empty_csv(
        OUT_DIR / "benchmark_benders_iterations.csv",
        [
            "source_id",
            "entry_id",
            "algorithm",
            "iteration",
            "upper_bound",
            "lower_bound",
            "gap_pct",
            "cut_count",
            "elapsed_sec",
            "status_name",
        ],
    )
    write_empty_csv(
        OUT_DIR / "benchmark_ai_cut_scores.csv",
        [
            "source_id",
            "entry_id",
            "algorithm",
            "iteration",
            "cut_id",
            "score",
            "selected",
            "rhs",
            "coef_count",
            "gap_pct",
            "policy_name",
        ],
    )
    write_markdown(rows, OUT_DIR / "benchmark_solver_smoke.md")
    summary = {
        "experiment_name": "benchmark_solver_smoke",
        "solver_model": "capacitated_facility_location_projection",
        "selected_count": len(selected_entries),
        "successful_rows": len([row for row in rows if not row.get("error")]),
        "failure_count": len(failures),
        "failures": failures,
        "output_files": {
            "solver_runs": str(OUT_DIR / "benchmark_solver_runs.csv"),
            "benders_iterations": str(OUT_DIR / "benchmark_benders_iterations.csv"),
            "ai_cut_scores": str(OUT_DIR / "benchmark_ai_cut_scores.csv"),
            "markdown": str(OUT_DIR / "benchmark_solver_smoke.md"),
        },
        "research_boundary": (
            "Capacitated facility-location projection only; not full LRP routing, "
            "not okra enterprise validation, and not AI-Benders superiority evidence."
        ),
    }
    (OUT_DIR / "benchmark_solver_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"rows": len(rows), "failures": len(failures), "out_dir": str(OUT_DIR)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
