"""Overpass API download and cleaning helpers for real external OSM data.

The module is intentionally conservative:
- it preserves raw Overpass JSON responses;
- it cleans to GeoJSON aligned with the existing seed pipeline;
- it uses local case-node coordinates to infer a county bbox when possible;
- it does not invent results when the network is unavailable.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from src.api.services import load_csv_records
from src.data_sources.ingestion_manifest import DATASETS
from src.data_sources.real_data_registry import DATA_SOURCE_REGISTRY_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_NODES_PATH = PROJECT_ROOT / "data" / "nodes.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
OVERPASS_INGESTION_PREVIEW_JSON_PATH = RESULT_DIR / "overpass_ingestion_preview.json"
OVERPASS_INGESTION_PREVIEW_MD_PATH = RESULT_DIR / "overpass_ingestion_preview.md"
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_SEC = 180
DEFAULT_USER_AGENT = "OkraColdStorage/1.0 (research download helper)"
DEFAULT_BBOX = (29.00, 111.20, 29.70, 112.20)

OVERPASS_QUERY_TIMEOUT = 180
OVERPASS_FEATURE_TAGS: List[Dict[str, str]] = [
    {"building": "warehouse"},
    {"building": "storage"},
    {"industrial": "warehouse"},
    {"building": "industrial"},
    {"amenity": "marketplace"},
    {"shop": "supermarket"},
    {"shop": "greengrocer"},
    {"shop": "convenience"},
]

ROAD_SPEED_KMH = {
    "motorway": 80.0,
    "trunk": 70.0,
    "primary": 50.0,
    "secondary": 40.0,
    "tertiary": 35.0,
    "unclassified": 25.0,
    "residential": 25.0,
    "service": 15.0,
    "living_street": 15.0,
    "track": 12.0,
    "path": 10.0,
}


@dataclass(frozen=True)
class OverpassDatasetSpec:
    dataset_id: str
    source_id: str
    source_name: str
    target_table: str
    raw_path: Path
    cleaned_path: Path
    query_kind: str


def _dataset_by_id(dataset_id: str) -> Dict[str, Any]:
    for dataset in DATASETS:
        if dataset.get("dataset_id") == dataset_id:
            return dataset
    raise KeyError(f"Unknown Overpass dataset_id: {dataset_id}")


def _spec_for_dataset(dataset_id: str) -> OverpassDatasetSpec:
    dataset = _dataset_by_id(dataset_id)
    return OverpassDatasetSpec(
        dataset_id=dataset_id,
        source_id=str(dataset.get("source_id", "SRC-E-001")),
        source_name=str(dataset.get("source_name", "Overpass API / OpenStreetMap")),
        target_table=str(dataset.get("target_table", "")),
        raw_path=Path(dataset.get("raw_path", "")),
        cleaned_path=Path(dataset.get("cleaned_path", "")),
        query_kind="road_network" if dataset_id == "road_network_edges_overpass" else "osm_features",
    )


def infer_case_bbox(padding_deg: float = 0.05) -> tuple[float, float, float, float]:
    rows = load_csv_records(CASE_NODES_PATH)
    lats: list[float] = []
    lons: list[float] = []
    for row in rows:
        try:
            lat = float(row.get("lat"))
            lon = float(row.get("lon"))
        except Exception:
            continue
        if math.isfinite(lat) and math.isfinite(lon):
            lats.append(lat)
            lons.append(lon)
    if not lats or not lons:
        return DEFAULT_BBOX
    south = max(min(lats) - padding_deg, -90.0)
    west = max(min(lons) - padding_deg, -180.0)
    north = min(max(lats) + padding_deg, 90.0)
    east = min(max(lons) + padding_deg, 180.0)
    if south >= north or west >= east:
        return DEFAULT_BBOX
    return (south, west, north, east)


def describe_case_bbox(padding_deg: float = 0.05) -> Dict[str, Any]:
    bbox = infer_case_bbox(padding_deg=padding_deg)
    south, west, north, east = bbox
    return {
        "bbox": bbox,
        "south": south,
        "west": west,
        "north": north,
        "east": east,
        "padding_deg": padding_deg,
        "bbox_clause": bbox_to_overpass_clause(bbox),
        "source": str(CASE_NODES_PATH),
    }


def bbox_to_overpass_clause(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    return f"({south:.6f},{west:.6f},{north:.6f},{east:.6f})"


def build_overpass_query(dataset_id: str, bbox: tuple[float, float, float, float] | None = None) -> str:
    bbox = bbox or infer_case_bbox()
    bbox_clause = bbox_to_overpass_clause(bbox)
    if dataset_id == "road_network_edges_overpass":
        return f"""[out:json][timeout:{OVERPASS_QUERY_TIMEOUT}];
(
  way["highway"]{bbox_clause};
);
out body geom;
"""
    if dataset_id == "osm_features_overpass":
        tag_filters = "\n".join(
            f'  nwr["{key}"="{value}"]{bbox_clause};'
            for tags in OVERPASS_FEATURE_TAGS
            for key, value in tags.items()
        )
        return f"""[out:json][timeout:{OVERPASS_QUERY_TIMEOUT}];
(
{tag_filters}
);
out body geom;
"""
    raise KeyError(f"Unknown Overpass dataset_id: {dataset_id}")


def build_overpass_request_preview(
    dataset_id: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    bbox: tuple[float, float, float, float] | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, Any]:
    bbox = bbox or infer_case_bbox()
    query = build_overpass_query(dataset_id, bbox)
    return {
        "dataset_id": dataset_id,
        "endpoint": endpoint,
        "bbox": bbox,
        "bbox_clause": bbox_to_overpass_clause(bbox),
        "timeout_sec": timeout_sec,
        "user_agent": user_agent,
        "query": query,
        "request_method": "POST",
        "request_content_type": "application/x-www-form-urlencoded",
        "request_body_key": "data",
        "source_url": endpoint,
        "research_boundary": (
            "This is a request preview only. It shows the exact Overpass request that would be sent, "
            "but it does not perform network I/O."
        ),
    }


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _raw_meta_path(raw_path: Path) -> Path:
    return raw_path.with_suffix(".meta.json")


def _feature_collection(features: list[dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": metadata,
    }


def _get_tags(element: Dict[str, Any]) -> Dict[str, Any]:
    tags = element.get("tags")
    return dict(tags) if isinstance(tags, dict) else {}


def _coord_pairs(geometry: Any) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    if not isinstance(geometry, list):
        return coords
    for point in geometry:
        if not isinstance(point, dict):
            continue
        try:
            lat = float(point.get("lat"))
            lon = float(point.get("lon"))
        except Exception:
            continue
        if math.isfinite(lat) and math.isfinite(lon):
            coords.append((lon, lat))
    return coords


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    sin_dphi = math.sin(dphi / 2.0)
    sin_dlambda = math.sin(dlambda / 2.0)
    aa = sin_dphi * sin_dphi + math.cos(phi1) * math.cos(phi2) * sin_dlambda * sin_dlambda
    return 2.0 * r * math.atan2(math.sqrt(aa), math.sqrt(max(0.0, 1.0 - aa)))


def _line_length_meters(coords: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for left, right in zip(coords, coords[1:]):
        total += _haversine_meters(left, right)
    return total


def _feature_type_from_tags(tags: Dict[str, Any], element_type: str) -> str:
    building = str(tags.get("building", "")).strip().lower()
    amenity = str(tags.get("amenity", "")).strip().lower()
    shop = str(tags.get("shop", "")).strip().lower()
    highway = str(tags.get("highway", "")).strip().lower()
    industrial = str(tags.get("industrial", "")).strip().lower()
    if building == "warehouse" or industrial == "warehouse":
        return "warehouse"
    if amenity == "marketplace":
        return "marketplace"
    if shop:
        return shop
    if highway:
        return "road"
    if building:
        return building
    return f"osm_{element_type}"


def _polygon_coordinates(coords: Sequence[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    ring = list(coords)
    if not ring:
        return []
    if ring[0] != ring[-1]:
        ring = [*ring, ring[0]]
    return [ring]


def _node_feature(element: Dict[str, Any], spec: OverpassDatasetSpec, raw_path: Path) -> Dict[str, Any] | None:
    try:
        lat = float(element.get("lat"))
        lon = float(element.get("lon"))
    except Exception:
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    tags = _get_tags(element)
    osm_id = f"node:{element.get('id')}"
    feature_type = _feature_type_from_tags(tags, "node")
    properties = {
        "source_id": spec.source_id,
        "osm_id": osm_id,
        "feature_type": feature_type,
        "name": tags.get("name"),
        "highway": tags.get("highway"),
        "amenity": tags.get("amenity"),
        "shop": tags.get("shop"),
        "building": tags.get("building"),
        "lat": lat,
        "lon": lon,
        "raw_file_path": str(raw_path),
        "source_url": DEFAULT_ENDPOINT,
    }
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def _way_feature(
    element: Dict[str, Any],
    spec: OverpassDatasetSpec,
    raw_path: Path,
    *,
    road_mode: bool = False,
) -> Dict[str, Any] | None:
    coords = _coord_pairs(element.get("geometry"))
    if len(coords) < 2:
        return None
    tags = _get_tags(element)
    osm_id = f"way:{element.get('id')}"
    feature_type = "road_edge" if road_mode else _feature_type_from_tags(tags, "way")
    geometry: Dict[str, Any]
    if road_mode:
        geometry = {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in coords]}
    else:
        is_closed = len(coords) >= 4 and coords[0] == coords[-1]
        if is_closed and (tags.get("building") or tags.get("amenity") or tags.get("shop") or tags.get("landuse")):
            geometry = {"type": "Polygon", "coordinates": _polygon_coordinates(coords)}
        else:
            geometry = {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in coords]}

    properties: Dict[str, Any] = {
        "source_id": spec.source_id,
        "osm_id": osm_id,
        "feature_type": feature_type,
        "name": tags.get("name"),
        "highway": tags.get("highway"),
        "amenity": tags.get("amenity"),
        "shop": tags.get("shop"),
        "building": tags.get("building"),
        "raw_file_path": str(raw_path),
        "source_url": DEFAULT_ENDPOINT,
    }
    if road_mode:
        highway = str(tags.get("highway", "")).strip().lower()
        speed_kmh = ROAD_SPEED_KMH.get(highway, 25.0)
        length_m = _line_length_meters(coords)
        node_ids = element.get("nodes") if isinstance(element.get("nodes"), list) else []
        properties.update(
            {
                "edge_key": osm_id,
                "from_osm_id": f"node:{node_ids[0]}" if node_ids else None,
                "to_osm_id": f"node:{node_ids[-1]}" if node_ids else None,
                "road_name": tags.get("name"),
                "length_m": round(length_m, 3),
                "assumed_speed_kmh": speed_kmh,
                "travel_time_min": round((length_m / 1000.0) / speed_kmh * 60.0, 3) if speed_kmh > 0 else None,
            }
        )
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def download_overpass_raw(
    dataset_id: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    bbox: tuple[float, float, float, float] | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    user_agent: str = DEFAULT_USER_AGENT,
    write_raw: bool = True,
) -> Dict[str, Any]:
    spec = _spec_for_dataset(dataset_id)
    bbox = bbox or infer_case_bbox()
    query = build_overpass_query(dataset_id, bbox)
    encoded = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=encoded,
        method="POST",
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    started_at = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload_bytes = response.read()
            status_code = getattr(response, "status", 200)
            headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        payload_bytes = exc.read()
        status_code = exc.code
        headers = dict(exc.headers.items()) if exc.headers else {}
        if write_raw:
            _ensure_parent(spec.raw_path)
            spec.raw_path.write_bytes(payload_bytes)
        meta = {
            "dataset_id": dataset_id,
            "source_id": spec.source_id,
            "source_name": spec.source_name,
            "target_table": spec.target_table,
            "endpoint": endpoint,
            "bbox": bbox,
            "query": query,
            "status_code": status_code,
            "headers": headers,
            "fetched_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "response_bytes": len(payload_bytes),
            "write_raw": write_raw,
            "raw_path": str(spec.raw_path),
        }
        if write_raw:
            _write_json(_raw_meta_path(spec.raw_path), meta)
        raise RuntimeError(f"Overpass download failed for {dataset_id}: HTTP {status_code}") from exc

    if write_raw:
        _ensure_parent(spec.raw_path)
        spec.raw_path.write_bytes(payload_bytes)

    meta = {
        "dataset_id": dataset_id,
        "source_id": spec.source_id,
        "source_name": spec.source_name,
        "target_table": spec.target_table,
        "endpoint": endpoint,
        "bbox": bbox,
        "query": query,
        "status_code": status_code,
        "headers": headers,
        "fetched_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "response_bytes": len(payload_bytes),
        "write_raw": write_raw,
        "raw_path": str(spec.raw_path),
    }
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        if write_raw:
            _ensure_parent(spec.raw_path)
            spec.raw_path.write_bytes(payload_bytes)
        raise RuntimeError(f"Overpass download for {dataset_id} returned non-JSON payload") from exc
    if write_raw:
        _write_json(_raw_meta_path(spec.raw_path), meta)
    return {
        "dataset_id": dataset_id,
        "source_id": spec.source_id,
        "source_name": spec.source_name,
        "target_table": spec.target_table,
        "endpoint": endpoint,
        "bbox": bbox,
        "query": query,
        "status_code": status_code,
        "response_bytes": len(payload_bytes),
        "raw_path": str(spec.raw_path),
        "meta": meta,
        "payload": payload,
    }


def clean_overpass_raw(
    dataset_id: str,
    *,
    raw_path: Path | None = None,
    cleaned_path: Path | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    preserve_relations: bool = False,
) -> Dict[str, Any]:
    spec = _spec_for_dataset(dataset_id)
    raw_path = raw_path or spec.raw_path
    cleaned_path = cleaned_path or spec.cleaned_path
    raw_meta = {}
    meta_path = _raw_meta_path(raw_path)
    if meta_path.exists():
        try:
            loaded_meta = _load_json(meta_path)
            if isinstance(loaded_meta, dict):
                raw_meta = loaded_meta
        except Exception:
            raw_meta = {}
    payload = _load_json(raw_path)
    elements = payload.get("elements", []) if isinstance(payload, dict) else []
    if not isinstance(elements, list):
        elements = []

    features: list[dict[str, Any]] = []
    counts = Counter()
    for element in elements:
        if not isinstance(element, dict):
            counts["skipped_non_dict"] += 1
            continue
        element_type = str(element.get("type", "")).strip().lower()
        if element_type == "node":
            feature = _node_feature(element, spec, raw_path) if dataset_id == "osm_features_overpass" else None
            if feature is None:
                counts["skipped_node_missing_geometry"] += 1
                continue
            features.append(feature)
            counts["node_features"] += 1
        elif element_type == "way":
            feature = _way_feature(
                element,
                spec,
                raw_path,
                road_mode=dataset_id == "road_network_edges_overpass",
            )
            if feature is None:
                counts["skipped_way_missing_geometry"] += 1
                continue
            features.append(feature)
            counts["way_features"] += 1
        elif element_type == "relation":
            if preserve_relations and dataset_id == "osm_features_overpass":
                coords = _coord_pairs(element.get("geometry"))
                if coords:
                    tags = _get_tags(element)
                    properties = {
                        "source_id": spec.source_id,
                        "osm_id": f"relation:{element.get('id')}",
                        "feature_type": _feature_type_from_tags(tags, "relation"),
                        "name": tags.get("name"),
                        "highway": tags.get("highway"),
                        "amenity": tags.get("amenity"),
                        "shop": tags.get("shop"),
                        "building": tags.get("building"),
                        "raw_file_path": str(raw_path),
                        "source_url": endpoint,
                    }
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in coords]},
                            "properties": properties,
                        }
                    )
                    counts["relation_features"] += 1
                else:
                    counts["skipped_relation_no_geometry"] += 1
            else:
                counts["skipped_relation"] += 1
        else:
            counts["skipped_unknown_type"] += 1

    bbox = tuple(raw_meta.get("bbox", infer_case_bbox()))
    metadata = {
        "dataset_id": dataset_id,
        "source_id": spec.source_id,
        "source_name": spec.source_name,
        "target_table": spec.target_table,
        "raw_path": str(raw_path),
        "cleaned_path": str(cleaned_path),
        "endpoint": endpoint,
        "bbox": bbox,
        "feature_count": len(features),
        "counts": dict(counts),
        "raw_meta": raw_meta,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "This cleaned artifact is produced from a raw Overpass JSON response. "
            "It remains limited to the bbox and tag filters used by the query."
        ),
    }
    cleaned_payload = _feature_collection(features, metadata)
    _ensure_parent(cleaned_path)
    cleaned_path.write_text(json.dumps(cleaned_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "dataset_id": dataset_id,
        "source_id": spec.source_id,
        "source_name": spec.source_name,
        "target_table": spec.target_table,
        "raw_path": str(raw_path),
        "cleaned_path": str(cleaned_path),
        "feature_count": len(features),
        "counts": dict(counts),
        "metadata": metadata,
    }


def download_and_clean_overpass_dataset(
    dataset_id: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    bbox: tuple[float, float, float, float] | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    user_agent: str = DEFAULT_USER_AGENT,
    preserve_relations: bool = False,
) -> Dict[str, Any]:
    spec = _spec_for_dataset(dataset_id)
    download_result = download_overpass_raw(
        dataset_id,
        endpoint=endpoint,
        bbox=bbox,
        timeout_sec=timeout_sec,
        user_agent=user_agent,
        write_raw=True,
    )
    clean_result = clean_overpass_raw(
        dataset_id,
        raw_path=Path(download_result["raw_path"]),
        cleaned_path=spec.cleaned_path,
        endpoint=endpoint,
        preserve_relations=preserve_relations,
    )
    return {
        "dataset_id": dataset_id,
        "source_id": spec.source_id,
        "source_name": spec.source_name,
        "target_table": spec.target_table,
        "endpoint": endpoint,
        "bbox": download_result["bbox"],
        "raw_path": str(spec.raw_path),
        "cleaned_path": str(spec.cleaned_path),
        "download": {
            "status_code": download_result["status_code"],
            "response_bytes": download_result["response_bytes"],
        },
        "clean": {
            "feature_count": clean_result["feature_count"],
            "counts": clean_result["counts"],
        },
    }


def build_overpass_ingestion_preview(limit: int = 2) -> Dict[str, Any]:
    dataset_ids = [dataset["dataset_id"] for dataset in DATASETS if dataset["dataset_id"] in {"osm_features_overpass", "road_network_edges_overpass"}]
    selected = dataset_ids[: max(0, limit)]
    bbox_info = describe_case_bbox()
    bbox = bbox_info["bbox"]
    datasets: list[Dict[str, Any]] = []
    for dataset_id in selected:
        spec = _spec_for_dataset(dataset_id)
        datasets.append(
            {
                "dataset_id": dataset_id,
                "source_id": spec.source_id,
                "source_name": spec.source_name,
                "target_table": spec.target_table,
                "raw_path": str(spec.raw_path),
                "cleaned_path": str(spec.cleaned_path),
                "query": build_overpass_query(dataset_id, bbox),
                "query_kind": spec.query_kind,
                "bbox": bbox,
                "bbox_clause": bbox_info["bbox_clause"],
                "source_url": DEFAULT_ENDPOINT,
            }
        )
    return {
        "source_name": "Overpass ingestion preview",
        "registry_path": str(DATA_SOURCE_REGISTRY_PATH),
        "case_nodes_path": str(CASE_NODES_PATH),
        "case_nodes_exists": CASE_NODES_PATH.exists(),
        "bbox": bbox,
        "bbox_info": bbox_info,
        "dataset_count": len(datasets),
        "datasets": datasets,
        "research_boundary": (
            "This is an ingestion preview for the Overpass path only. It does not fetch network data on its own, "
            "but its query and cleaning path are aligned with the existing seed pipeline."
        ),
    }


def write_overpass_request_preview(
    dataset_id: str,
    out_dir: Path | None = None,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, str]:
    report = build_overpass_request_preview(
        dataset_id,
        endpoint=endpoint,
        timeout_sec=timeout_sec,
        user_agent=user_agent,
    )
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / f"overpass_request_preview_{dataset_id}.json"
    md_path = destination / f"overpass_request_preview_{dataset_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Request Preview",
                "",
                f"Dataset ID: {report.get('dataset_id', '')}",
                f"Endpoint: {report.get('endpoint', '')}",
                f"BBox: {report.get('bbox', [])}",
                f"BBox clause: {report.get('bbox_clause', '')}",
                f"Timeout sec: {report.get('timeout_sec', 0)}",
                f"User-Agent: {report.get('user_agent', '')}",
                "",
                "## Query",
                "",
                "```overpass",
                str(report.get("query", "")),
                "```",
                "",
                "## Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}


def render_overpass_ingestion_preview_markdown(report: Dict[str, Any]) -> str:
    rows = [
        "| dataset_id | target_table | query_kind | raw_path | cleaned_path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.get("datasets", []):
        rows.append(
            "| {dataset_id} | {target_table} | {query_kind} | {raw_path} | {cleaned_path} |".format(
                dataset_id=item.get("dataset_id", ""),
                target_table=item.get("target_table", ""),
                query_kind=item.get("query_kind", ""),
                raw_path=item.get("raw_path", ""),
                cleaned_path=item.get("cleaned_path", ""),
            )
        )
    bbox = report.get("bbox", [])
    return "\n".join(
        [
            "# Overpass Ingestion Preview",
            "",
            f"Dataset count: {report.get('dataset_count', 0)}",
            f"BBox: {bbox}",
            f"BBox clause: {report.get('bbox_info', {}).get('bbox_clause', '')}",
            f"Case nodes: {report.get('case_nodes_path', '')}",
            f"Case nodes exists: {report.get('case_nodes_exists', False)}",
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


def write_overpass_ingestion_preview(out_dir: Path | None = None) -> Dict[str, str]:
    report = build_overpass_ingestion_preview()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / OVERPASS_INGESTION_PREVIEW_JSON_PATH.name
    md_path = destination / OVERPASS_INGESTION_PREVIEW_MD_PATH.name
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_overpass_ingestion_preview_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
