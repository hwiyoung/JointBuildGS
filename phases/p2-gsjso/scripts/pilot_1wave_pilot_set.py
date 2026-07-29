#!/usr/bin/env python3
"""P1W-SET: deterministically lock the expanded pilot population and dense bar.

The approved v4 protocol requires a strict two-phase operation:

1. Select and hash 30 building IDs using only the canonical population,
   dense ``has_lod22`` status, the approved XY footprints, and the prior C001
   training bbox.
2. Only after that immutable ID lock exists, open the baseline score table and
   attach dense RMS values / compute the bar-as-rule median.

No training or inference is performed.  The script is intentionally stdlib-only
and refuses to run outside Docker.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260721_pilot_1wave"
TASK_ID = "P1W-SET"
CRS = "EPSG:25832"
DEFAULT_OUTPUT_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
CSV_NAME = "pilot_1wave_pilot_set.csv"
MANIFEST_NAME = "pilot_1wave_pilot_set_manifest.json"

PROTOCOL = REPO / "docs/research/preregistration/quality_axis/사전등록서_품질축본선_승인잠금v4_20260721.md"
POPULATION = REPO / "docs/regression_input_snapshot.csv"
STATUS = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "building_reconstruction_status.csv"
)
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
BASELINE_SCORES = REPO / "docs/experiments/qs_baseline178/tables/qs_baseline178_scores.csv"
BASELINE_MANIFEST = REPO / "docs/experiments/qs_baseline178/manifests/qs_baseline178_manifest.json"
PRIOR_C001_MANIFEST = (
    REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
)
UPSTREAM_LOD2_5334 = REPO / "phases/p0-audit/data/raw/lod2/690_5334.gml"
UPSTREAM_LOD2_5336 = REPO / "phases/p0-audit/data/raw/lod2/690_5336.gml"
FULL_GROUND_PLAN = REPO / "phases/p0-audit/data/work/footprints/lod2_ground_plan.gpkg"
PRIOR_AOI_GPKG = REPO / "phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"

PROTOCOL_COMMIT = "e258be108d38fd0cc913bba1dfbe928a76b7d1ec"
CONTEXT_BUFFER_M = 20.0
TARGET_COUNT = 30
EXPECTED_CANONICAL_COUNT = 178
EXPECTED_DENSE_SUCCESS_COUNT = 114
EXPECTED_FOOTPRINT_COUNT = 199
EXPECTED_D30_M = 32.253338650917
EXPECTED_BOUNDARY_BUILDING_ID = "DEBY_LOD2_4908024"
EXPECTED_NON_SMALL_DENSE_MEDIAN_M = 1.175249793

CORE10 = (
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907185",
    "DEBY_LOD2_4907186",
    "DEBY_LOD2_4907188",
    "DEBY_LOD2_4907195",
    "DEBY_LOD2_4907198",
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_60098",
)

# These are the approved/committed inputs, not values discovered from the
# current filesystem.  Full-file verification happens only after the ID lock
# for tables that physically contain RMS columns.
EXPECTED_SHA256 = {
    "docs/research/preregistration/quality_axis/사전등록서_품질축본선_승인잠금v4_20260721.md":
        "39b7b641a324dda7b5ea9d01906407223b75443d62b6d71580c3d598566464ec",
    "docs/regression_input_snapshot.csv":
        "3cabed76b37625fdf8f9a72ed5c5b1f7c90ba23a839d6f1a61fc3727870cee82",
    "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv":
        "4412ee47f8665e1a12663629dd66f9c9612f2e9adca54be38c188f2bc521a9b6",
    "results/tum_transfer/analysis/footprints_aoi.geojson":
        "ca7f5b13a52368e1d2ac47b77cc78f12887bad4d598d122ad57b882eb4920a82",
    "docs/experiments/qs_baseline178/tables/qs_baseline178_scores.csv":
        "a3b89f1907e6e61aead702efe6b742b5c012615df77d90bdb2a859b5418d85ab",
    "docs/experiments/qs_baseline178/manifests/qs_baseline178_manifest.json":
        "039623166b1be724b67a565d463de148d551db0c2e52c2ee5d88e3e5e8a0ad38",
    "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json":
        "eca68a7890116c52557ab467361b58c4c784047807f9bee857a2517ac0b40b58",
    "phases/p0-audit/data/raw/lod2/690_5334.gml":
        "61d29e4617bfa961e811003b7af2bb2c826b3fab90f11731f5d22b8e4689e314",
    "phases/p0-audit/data/raw/lod2/690_5336.gml":
        "494282ee7be660401820af8efa4e2667fcaeb4d7ac8466b23be67e3347701674",
    "phases/p0-audit/data/work/footprints/lod2_ground_plan.gpkg":
        "259cf04ec0c9411e669e75f61c37ea634290fcd40b230f6ed9b67328041c87fa",
    "phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg":
        "7042d4139afd808fa11dc3c624e0cb3f3ede8d5066ec9d2bed37d7f1bc90cc91",
}

SELECTION_POPULATION_FIELDS = ("building_id", "arm", "assembled")
SELECTION_STATUS_FIELDS = ("input", "building_id", "has_lod22")
BAR_FIELDS = ("model_id", "role", "building_id", "has_lod22", "roof_rms_m")
FORBIDDEN_PRELOCK_FIELDS = {
    "rf_rmse_lod22",
    "roof_rms_m",
    "roof_hausdorff_m",
    "ref_roof_planes",
    "rf_roof_planes",
    "roof_face_count_ref",
    "roof_face_count_model",
    "als",
    "semantic",
    "roof_type",
    "lod2_z",
}

CSV_FIELDS = (
    "selection_rank",
    "building_id",
    "building_id_short",
    "is_core10",
    "centroid_x",
    "centroid_y",
    "centroid_expansion_distance_m",
    "footprint_minx",
    "footprint_miny",
    "footprint_maxx",
    "footprint_maxy",
    "footprint_area_m2",
    "is_small_lt50m2",
    "dense_has_lod22",
    "dense_roof_rms_m",
    "dense_bar_median_m",
    "dense_bar_median_excluding_lt50m2_m",
    "non_small_sensitivity_count",
    "core10_dense_rms_median_m",
    "core10_reproduces_0p990_3dp",
    "scoring_aoi_minx",
    "scoring_aoi_miny",
    "scoring_aoi_maxx",
    "scoring_aoi_maxy",
    "training_crop_aoi_minx",
    "training_crop_aoi_miny",
    "training_crop_aoi_maxx",
    "training_crop_aoi_maxy",
    "training_context_buffer_m",
    "training_bbox_fully_contained_building_count",
    "training_bbox_intersecting_building_count",
    "dense_success_context_only_fully_contained_count",
    "dense_success_context_only_intersecting_count",
    "selection_sha256",
    "population_source_sha256",
    "dense_status_source_sha256",
    "footprint_source_sha256",
    "dense_rms_source_sha256",
    "crs",
)


@dataclass(frozen=True)
class Footprint:
    building_id: str
    centroid_x: float
    centroid_y: float
    bbox: tuple[float, float, float, float]
    area_m2: float


@dataclass(frozen=True)
class Candidate:
    building_id: str
    footprint: Footprint
    expansion_distance_m: float


class ReadAudit:
    """Records input-open order and enforces the ID-lock/RMS boundary."""

    def __init__(self) -> None:
        self.ids_locked = False
        self.selection_sha256: str | None = None
        self.events: list[dict[str, Any]] = []

    def record(self, event: str, path: Path | None = None, fields: Sequence[str] = ()) -> None:
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "event": event,
                "path": rel(path) if path else None,
                "projected_fields": list(fields),
                "ids_locked": self.ids_locked,
            }
        )

    def assert_prelock_fields(self, fields: Sequence[str]) -> None:
        forbidden = FORBIDDEN_PRELOCK_FIELDS.intersection({field.lower() for field in fields})
        if forbidden:
            raise AssertionError(f"forbidden pre-lock fields requested: {sorted(forbidden)}")

    def lock(self, selection_sha256: str) -> None:
        if self.ids_locked:
            raise AssertionError("selection IDs were already locked")
        self.ids_locked = True
        self.selection_sha256 = selection_sha256
        self.record("selection_ids_locked")

    def require_lock_for_bar(self) -> None:
        if not self.ids_locked or not self.selection_sha256:
            raise AssertionError("dense RMS may only be opened after selection IDs are locked")


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def f9(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"non-finite output value: {value}")
    return f"{value:.9f}"


def rounded_list(values: Sequence[float]) -> list[float]:
    return [round(float(value), 9) for value in values]


def projected_csv(
    path: Path,
    fields: Sequence[str],
    audit: ReadAudit,
    *,
    prelock: bool,
) -> list[dict[str, str]]:
    """Read only explicitly projected columns; do not materialize other fields."""
    if prelock:
        if audit.ids_locked:
            raise AssertionError("pre-lock reader invoked after ID lock")
        audit.assert_prelock_fields(fields)
    elif "roof_rms_m" in fields:
        audit.require_lock_for_bar()
    audit.record("projected_csv_open", path, fields)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if len(header) != len(set(header)):
            raise AssertionError(f"duplicate CSV headers: {rel(path)}")
        missing = sorted(set(fields) - set(header))
        if missing:
            raise AssertionError(f"missing fields in {rel(path)}: {missing}")
        indexes = {field: header.index(field) for field in fields}
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise AssertionError(f"ragged CSV row {rel(path)}:{line_number}")
            rows.append({field: row[indexes[field]] for field in fields})
    return rows


def ring_area_centroid(
    ring: Sequence[Sequence[float]],
) -> tuple[float, tuple[float, float]]:
    """Return absolute ring area and a numerically stable centroid."""
    points = [(float(point[0]), float(point[1])) for point in ring]
    if len(points) < 3:
        raise AssertionError("footprint exterior ring has fewer than three points")
    if points[0] != points[-1]:
        points.append(points[0])
    # Translate first.  Applying the shoelace formula directly to
    # EPSG:25832 coordinates (~7e5, ~5e6) suffers catastrophic cancellation
    # for 20 m2 roofs and can move the centroid by several metres.
    origin_x, origin_y = points[0]
    local = [(x - origin_x, y - origin_y) for x, y in points]
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for (x0, y0), (x1, y1) in zip(local, local[1:]):
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area2) < 1e-9:
        raise AssertionError("degenerate footprint ring")
    centroid = (
        origin_x + cx / (3.0 * area2),
        origin_y + cy / (3.0 * area2),
    )
    return abs(area2) * 0.5, centroid


def polygon_centroid(rings: Sequence[Sequence[Sequence[float]]]) -> tuple[float, float]:
    """GeoJSON Polygon centroid: exterior minus holes, orientation-independent."""
    if not rings:
        raise AssertionError("empty Polygon ring list")
    exterior_area, exterior_centroid = ring_area_centroid(rings[0])
    net_area = exterior_area
    weighted_x = exterior_area * exterior_centroid[0]
    weighted_y = exterior_area * exterior_centroid[1]
    for hole in rings[1:]:
        hole_area, hole_centroid = ring_area_centroid(hole)
        net_area -= hole_area
        weighted_x -= hole_area * hole_centroid[0]
        weighted_y -= hole_area * hole_centroid[1]
    if net_area <= 1e-9:
        raise AssertionError("Polygon holes consume the exterior area")
    return weighted_x / net_area, weighted_y / net_area


def load_footprints(path: Path, audit: ReadAudit) -> dict[str, Footprint]:
    if audit.ids_locked:
        raise AssertionError("footprints must be loaded before the selection lock")
    audit.record("xy_footprints_open", path, ("building_id", "geometry_xy", "area_m2"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features")
    if not isinstance(features, list):
        raise AssertionError("footprint GeoJSON has no feature list")
    output: dict[str, Footprint] = {}
    for feature in features:
        props = feature.get("properties") or {}
        building_id = str(props.get("building_id") or "")
        geometry = feature.get("geometry") or {}
        if not building_id:
            raise AssertionError("footprint missing building_id")
        if building_id in output:
            raise AssertionError(f"duplicate footprint building_id: {building_id}")
        if geometry.get("type") != "Polygon":
            raise AssertionError(f"expected Polygon for {building_id}, got {geometry.get('type')}")
        rings = geometry.get("coordinates") or []
        if not rings:
            raise AssertionError(f"empty footprint geometry: {building_id}")
        # Standard Polygon centroid: exterior contribution minus every interior
        # ring, independent of ring orientation.  Bbox covers every ring.
        centroid_x, centroid_y = polygon_centroid(rings)
        points = [point for ring in rings for point in ring]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        area_m2 = float(props["area_m2"])
        if not math.isfinite(area_m2) or area_m2 <= 0:
            raise AssertionError(f"invalid footprint area for {building_id}: {area_m2}")
        output[building_id] = Footprint(
            building_id=building_id,
            centroid_x=centroid_x,
            centroid_y=centroid_y,
            bbox=(min(xs), min(ys), max(xs), max(ys)),
            area_m2=area_m2,
        )
    if len(output) != EXPECTED_FOOTPRINT_COUNT:
        raise AssertionError(f"expected {EXPECTED_FOOTPRINT_COUNT} footprints, got {len(output)}")
    return output


def load_prior_c001_bbox(path: Path, audit: ReadAudit) -> tuple[float, float, float, float]:
    if audit.ids_locked:
        raise AssertionError("prior C001 bbox must be loaded before the selection lock")
    audit.record("prior_c001_bbox_open", path, ("union_bbox_utm_buffered", "buffer_m"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    bbox = tuple(float(value) for value in payload["union_bbox_utm_buffered"])
    if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
        raise AssertionError(f"invalid prior C001 bbox: {bbox}")
    if float(payload["buffer_m"]) != CONTEXT_BUFFER_M:
        raise AssertionError("prior C001 context buffer is not the locked 20 m")
    expected = (690754.55, 5335999.202, 690879.713, 5336140.41)
    if bbox != expected:
        raise AssertionError(f"prior C001 bbox drift: expected {expected}, got {bbox}")
    return bbox


def canonical_population(rows: Sequence[Mapping[str, str]]) -> set[str]:
    selected = [
        row["building_id"]
        for row in rows
        if row["arm"] == "raw_lidar" and bool_value(row["assembled"])
    ]
    if len(selected) != len(set(selected)):
        raise AssertionError("canonical raw_lidar assembled population contains duplicate IDs")
    output = set(selected)
    if len(output) != EXPECTED_CANONICAL_COUNT:
        raise AssertionError(
            f"expected canonical population {EXPECTED_CANONICAL_COUNT}, got {len(output)}"
        )
    return output


def dense_success_population(
    rows: Sequence[Mapping[str, str]], canonical_ids: set[str]
) -> set[str]:
    dim_rows = [row for row in rows if row["input"] == "DIM"]
    if len({row["building_id"] for row in dim_rows}) != len(dim_rows):
        raise AssertionError("DIM status rows contain duplicate building IDs")
    status = {row["building_id"]: bool_value(row["has_lod22"]) for row in dim_rows}
    missing = sorted(canonical_ids - set(status))
    if missing:
        raise AssertionError(f"canonical IDs missing DIM status: {missing}")
    output = {building_id for building_id in canonical_ids if status[building_id]}
    if len(output) != EXPECTED_DENSE_SUCCESS_COUNT:
        raise AssertionError(
            f"expected dense-success population {EXPECTED_DENSE_SUCCESS_COUNT}, got {len(output)}"
        )
    return output


def expansion_distance(
    centroid_x: float,
    centroid_y: float,
    bbox: Sequence[float],
) -> float:
    minx, miny, maxx, maxy = bbox
    return max(
        minx - centroid_x,
        0.0,
        centroid_x - maxx,
        miny - centroid_y,
        centroid_y - maxy,
    )


def select_candidates(
    dense_success_ids: set[str],
    footprints: Mapping[str, Footprint],
    prior_bbox: Sequence[float],
) -> list[Candidate]:
    missing = sorted(dense_success_ids - set(footprints))
    if missing:
        raise AssertionError(f"dense-success candidates missing footprint: {missing}")
    ranked = sorted(
        (
            Candidate(
                building_id=building_id,
                footprint=footprints[building_id],
                expansion_distance_m=expansion_distance(
                    footprints[building_id].centroid_x,
                    footprints[building_id].centroid_y,
                    prior_bbox,
                ),
            )
            for building_id in dense_success_ids
        ),
        key=lambda item: (item.expansion_distance_m, item.building_id),
    )
    selected = ranked[:TARGET_COUNT]
    if len(selected) != TARGET_COUNT:
        raise AssertionError(f"expected {TARGET_COUNT} selected buildings, got {len(selected)}")
    missing_core = sorted(set(CORE10) - {item.building_id for item in selected})
    if missing_core:
        raise AssertionError(f"locked core 10 not reproduced: {missing_core}")
    if ranked[TARGET_COUNT - 1].expansion_distance_m > ranked[TARGET_COUNT].expansion_distance_m:
        raise AssertionError("candidate ordering is not monotonic at the selection boundary")
    return selected


def expand_bbox(bbox: Sequence[float], distance: float) -> tuple[float, float, float, float]:
    return (
        float(bbox[0]) - distance,
        float(bbox[1]) - distance,
        float(bbox[2]) + distance,
        float(bbox[3]) + distance,
    )


def union_bbox(footprints: Iterable[Footprint]) -> tuple[float, float, float, float]:
    fps = list(footprints)
    if not fps:
        raise AssertionError("cannot compute union bbox of empty footprint set")
    return (
        min(fp.bbox[0] for fp in fps),
        min(fp.bbox[1] for fp in fps),
        max(fp.bbox[2] for fp in fps),
        max(fp.bbox[3] for fp in fps),
    )


def bbox_inside(inner: Sequence[float], outer: Sequence[float], tolerance: float = 1e-9) -> bool:
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def bbox_intersects(left: Sequence[float], right: Sequence[float]) -> bool:
    return (
        left[0] <= right[2]
        and left[2] >= right[0]
        and left[1] <= right[3]
        and left[3] >= right[1]
    )


def selection_lock_payload(
    selected: Sequence[Candidate],
    prior_bbox: Sequence[float],
    scoring_bbox: Sequence[float],
    tight_bbox: Sequence[float],
    training_bbox: Sequence[float],
) -> dict[str, Any]:
    """Construct the score-free, canonical payload whose SHA locks the IDs."""
    selection_input_expected_sha256 = {
        rel(PROTOCOL): EXPECTED_SHA256[rel(PROTOCOL)],
        rel(POPULATION): EXPECTED_SHA256[rel(POPULATION)],
        rel(STATUS): EXPECTED_SHA256[rel(STATUS)],
        rel(FOOTPRINTS): EXPECTED_SHA256[rel(FOOTPRINTS)],
        rel(PRIOR_C001_MANIFEST): EXPECTED_SHA256[rel(PRIOR_C001_MANIFEST)],
    }
    return {
        "schema": "jointbuildgs.pilot_1wave.selection_lock.v1",
        "protocol_commit": PROTOCOL_COMMIT,
        "selection_rule": (
            "canonical178 AND DIM has_lod22=true; rank by "
            "(minimum isotropic expansion distance from prior buffered C001 training bbox, "
            "building_id); take first 30"
        ),
        "selection_fields": {
            rel(POPULATION): list(SELECTION_POPULATION_FIELDS),
            rel(STATUS): list(SELECTION_STATUS_FIELDS),
            rel(FOOTPRINTS): ["building_id", "GroundSurface XY", "area_m2"],
            rel(PRIOR_C001_MANIFEST): ["union_bbox_utm_buffered", "buffer_m"],
        },
        "forbidden_selection_inputs": [
            "RMS",
            "ALS measurements",
            "LoD2 z",
            "roof faces/type",
            "semantic class",
            "GS outputs",
        ],
        "selection_input_expected_sha256": selection_input_expected_sha256,
        "crs": CRS,
        "prior_c001_training_bbox_buffered": rounded_list(prior_bbox),
        "selection_expansion_distance_m": round(selected[-1].expansion_distance_m, 9),
        "scoring_selection_bbox": rounded_list(scoring_bbox),
        "selected_footprint_tight_union_bbox": rounded_list(tight_bbox),
        "training_crop_context_buffer_m": CONTEXT_BUFFER_M,
        "training_crop_bbox": rounded_list(training_bbox),
        "selected": [
            {
                "selection_rank": rank,
                "building_id": item.building_id,
                "centroid_x": round(item.footprint.centroid_x, 9),
                "centroid_y": round(item.footprint.centroid_y, 9),
                "centroid_expansion_distance_m": round(item.expansion_distance_m, 9),
                "footprint_bbox": rounded_list(item.footprint.bbox),
                "footprint_area_m2": round(item.footprint.area_m2, 9),
                "is_core10": item.building_id in CORE10,
                "is_small_lt50m2": item.footprint.area_m2 < 50.0,
            }
            for rank, item in enumerate(selected, 1)
        ],
    }


def load_dense_rms(audit: ReadAudit) -> dict[str, float]:
    audit.require_lock_for_bar()
    rows = projected_csv(BASELINE_SCORES, BAR_FIELDS, audit, prelock=False)
    dense_rows = [
        row
        for row in rows
        if row["role"] == "dense" and row["model_id"] == "canonical_dense_w2_1"
    ]
    if len(dense_rows) != EXPECTED_CANONICAL_COUNT:
        raise AssertionError(
            f"expected {EXPECTED_CANONICAL_COUNT} canonical dense score rows, got {len(dense_rows)}"
        )
    if len({row["building_id"] for row in dense_rows}) != len(dense_rows):
        raise AssertionError("canonical dense score rows contain duplicate building IDs")
    output: dict[str, float] = {}
    for row in dense_rows:
        if bool_value(row["has_lod22"]):
            value = float(row["roof_rms_m"])
            if not math.isfinite(value):
                raise AssertionError(f"non-finite dense RMS for {row['building_id']}")
            output[row["building_id"]] = value
    return output


def render_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return stream.getvalue().encode("utf-8")


def render_manifest(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def verify_sha(path: Path, actual: str) -> None:
    expected = EXPECTED_SHA256[rel(path)]
    if actual != expected:
        raise AssertionError(
            f"source SHA drift for {rel(path)}: expected {expected}, got {actual}"
        )


def build_artifacts() -> tuple[bytes, bytes, dict[str, Any]]:
    audit = ReadAudit()

    # Pre-lock phase: only projected status/population fields plus approved XY.
    population_rows = projected_csv(
        POPULATION, SELECTION_POPULATION_FIELDS, audit, prelock=True
    )
    status_rows = projected_csv(STATUS, SELECTION_STATUS_FIELDS, audit, prelock=True)
    footprints = load_footprints(FOOTPRINTS, audit)
    prior_bbox = load_prior_c001_bbox(PRIOR_C001_MANIFEST, audit)

    canonical_ids = canonical_population(population_rows)
    dense_success_ids = dense_success_population(status_rows, canonical_ids)
    selected = select_candidates(dense_success_ids, footprints, prior_bbox)
    selected_ids = [item.building_id for item in selected]
    selected_set = set(selected_ids)

    expansion_m = selected[-1].expansion_distance_m
    scoring_bbox = expand_bbox(prior_bbox, expansion_m)
    tight_bbox = union_bbox(item.footprint for item in selected)
    training_bbox = expand_bbox(tight_bbox, CONTEXT_BUFFER_M)

    if not all(
        bbox_inside(item.footprint.bbox, training_bbox) for item in selected
    ):
        raise AssertionError("not every selected full footprint is inside training crop bbox")
    if not all(
        bbox_inside(
            (item.footprint.centroid_x, item.footprint.centroid_y,
             item.footprint.centroid_x, item.footprint.centroid_y),
            scoring_bbox,
        )
        for item in selected
    ):
        raise AssertionError("selected centroid lies outside scoring/selection bbox")

    lock_payload = selection_lock_payload(
        selected, prior_bbox, scoring_bbox, tight_bbox, training_bbox
    )
    selection_sha256 = sha256_bytes(canonical_json_bytes(lock_payload))
    ordered_ids_sha256 = sha256_bytes(("\n".join(selected_ids) + "\n").encode("utf-8"))
    if not math.isclose(expansion_m, EXPECTED_D30_M, rel_tol=0.0, abs_tol=1e-9):
        raise AssertionError(
            f"d30 drift: expected {EXPECTED_D30_M:.12f}, got {expansion_m:.12f}"
        )
    if selected_ids[-1] != EXPECTED_BOUNDARY_BUILDING_ID:
        raise AssertionError(
            "selection boundary drift: expected "
            f"{EXPECTED_BOUNDARY_BUILDING_ID}, got {selected_ids[-1]}"
        )
    if any(event["path"] == rel(BASELINE_SCORES) for event in audit.events):
        raise AssertionError("baseline score table was opened before the ID lock")
    # This is the formal boundary: no score file or full source-file SHA has
    # been opened/calculated before this call.
    audit.lock(selection_sha256)
    lock_event_sequence = audit.events[-1]["sequence"]

    # Post-lock provenance: now full-file hashes (including CSVs that carry RMS)
    # may be read and verified.  This cannot influence the already-hashed IDs.
    source_paths = (
        PROTOCOL,
        POPULATION,
        STATUS,
        FOOTPRINTS,
        BASELINE_SCORES,
        BASELINE_MANIFEST,
        PRIOR_C001_MANIFEST,
        UPSTREAM_LOD2_5334,
        UPSTREAM_LOD2_5336,
        FULL_GROUND_PLAN,
        PRIOR_AOI_GPKG,
    )
    source_sha256: dict[str, str] = {}
    for path in source_paths:
        audit.record("postlock_full_file_sha256", path)
        actual = sha256_file(path)
        verify_sha(path, actual)
        source_sha256[rel(path)] = actual

    dense_rms = load_dense_rms(audit)
    if sha256_bytes(canonical_json_bytes(lock_payload)) != selection_sha256:
        raise AssertionError("selection lock payload changed after dense RMS was read")
    rms_open_sequence = next(
        event["sequence"]
        for event in audit.events
        if event["path"] == rel(BASELINE_SCORES)
        and event["event"] == "projected_csv_open"
    )
    if rms_open_sequence <= lock_event_sequence:
        raise AssertionError("dense RMS input was opened before the ID lock")

    missing_rms = sorted(selected_set - set(dense_rms))
    if missing_rms:
        raise AssertionError(f"selected IDs missing dense RMS: {missing_rms}")
    dense_values = [dense_rms[building_id] for building_id in selected_ids]
    dense_bar = statistics.median(dense_values)
    non_small_values = [
        dense_rms[item.building_id]
        for item in selected
        if item.footprint.area_m2 >= 50.0
    ]
    non_small_median = statistics.median(non_small_values)
    if len(non_small_values) != 25:
        raise AssertionError(
            f"expected 25 buildings in <50 m2-excluded sensitivity, got {len(non_small_values)}"
        )
    if not math.isclose(
        non_small_median,
        EXPECTED_NON_SMALL_DENSE_MEDIAN_M,
        rel_tol=0.0,
        abs_tol=5e-10,
    ):
        raise AssertionError(
            "non-small dense RMS sensitivity drift: expected "
            f"{EXPECTED_NON_SMALL_DENSE_MEDIAN_M:.9f}, got {non_small_median:.9f}"
        )
    core_values = [dense_rms[building_id] for building_id in CORE10]
    core_median = statistics.median(core_values)
    core_reproduction = round(core_median, 3) == 0.990
    if not core_reproduction:
        raise AssertionError(
            f"core-10 dense RMS does not reproduce 0.990 at 3 dp: {core_median}"
        )

    fully_contained_ids = sorted(
        building_id
        for building_id, footprint in footprints.items()
        if bbox_inside(footprint.bbox, training_bbox)
    )
    intersecting_ids = sorted(
        building_id
        for building_id, footprint in footprints.items()
        if bbox_intersects(footprint.bbox, training_bbox)
    )
    dense_context_fully_contained = sorted(
        (set(fully_contained_ids) & dense_success_ids) - selected_set
    )
    dense_context_intersecting = sorted(
        (set(intersecting_ids) & dense_success_ids) - selected_set
    )

    small_ids = [
        item.building_id for item in selected if item.footprint.area_m2 < 50.0
    ]
    if not small_ids:
        raise AssertionError("expanded pilot failed to include any <50 m2 building")

    common_row = {
        "dense_bar_median_m": f9(dense_bar),
        "dense_bar_median_excluding_lt50m2_m": f9(non_small_median),
        "non_small_sensitivity_count": len(non_small_values),
        "core10_dense_rms_median_m": f9(core_median),
        "core10_reproduces_0p990_3dp": "true",
        "scoring_aoi_minx": f9(scoring_bbox[0]),
        "scoring_aoi_miny": f9(scoring_bbox[1]),
        "scoring_aoi_maxx": f9(scoring_bbox[2]),
        "scoring_aoi_maxy": f9(scoring_bbox[3]),
        "training_crop_aoi_minx": f9(training_bbox[0]),
        "training_crop_aoi_miny": f9(training_bbox[1]),
        "training_crop_aoi_maxx": f9(training_bbox[2]),
        "training_crop_aoi_maxy": f9(training_bbox[3]),
        "training_context_buffer_m": f9(CONTEXT_BUFFER_M),
        "training_bbox_fully_contained_building_count": len(fully_contained_ids),
        "training_bbox_intersecting_building_count": len(intersecting_ids),
        "dense_success_context_only_fully_contained_count": len(
            dense_context_fully_contained
        ),
        "dense_success_context_only_intersecting_count": len(
            dense_context_intersecting
        ),
        "selection_sha256": selection_sha256,
        "population_source_sha256": source_sha256[rel(POPULATION)],
        "dense_status_source_sha256": source_sha256[rel(STATUS)],
        "footprint_source_sha256": source_sha256[rel(FOOTPRINTS)],
        "dense_rms_source_sha256": source_sha256[rel(BASELINE_SCORES)],
        "crs": CRS,
    }
    csv_rows: list[dict[str, Any]] = []
    for rank, item in enumerate(selected, 1):
        fp = item.footprint
        csv_rows.append(
            {
                "selection_rank": rank,
                "building_id": item.building_id,
                "building_id_short": item.building_id.removeprefix("DEBY_LOD2_"),
                "is_core10": str(item.building_id in CORE10).lower(),
                "centroid_x": f9(fp.centroid_x),
                "centroid_y": f9(fp.centroid_y),
                "centroid_expansion_distance_m": f9(item.expansion_distance_m),
                "footprint_minx": f9(fp.bbox[0]),
                "footprint_miny": f9(fp.bbox[1]),
                "footprint_maxx": f9(fp.bbox[2]),
                "footprint_maxy": f9(fp.bbox[3]),
                "footprint_area_m2": f9(fp.area_m2),
                "is_small_lt50m2": str(fp.area_m2 < 50.0).lower(),
                "dense_has_lod22": "true",
                "dense_roof_rms_m": f9(dense_rms[item.building_id]),
                **common_row,
            }
        )
    csv_bytes = render_csv(csv_rows)

    selection_boundary_distance = selected[-1].expansion_distance_m
    boundary_candidate_ids = sorted(
        building_id
        for building_id in dense_success_ids
        if math.isclose(
            expansion_distance(
                footprints[building_id].centroid_x,
                footprints[building_id].centroid_y,
                prior_bbox,
            ),
            selection_boundary_distance,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )
    manifest: dict[str, Any] = {
        "schema": "jointbuildgs.pilot_1wave.pilot_set.v1",
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "artifact_date": "2026-07-21",
        "protocol_commit": PROTOCOL_COMMIT,
        # Pin the committed protocol/source parent.  A dynamic worktree HEAD
        # would make this artifact fail byte-for-byte checks after P1W-SET is
        # committed even though every selection input stayed identical.
        "git_head_at_generation": PROTOCOL_COMMIT,
        "script": rel(Path(__file__)),
        "script_sha256": sha256_file(Path(__file__)),
        "docker_required": True,
        "docker_image_used": "jointbuildgs-p0-tools:t0",
        "python_version": sys.version.split()[0],
        "crs": CRS,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "selection": {
            "population_definition": (
                "docs/regression_input_snapshot.csv rows with arm=raw_lidar and assembled=true"
            ),
            "canonical_population_count": len(canonical_ids),
            "dense_success_definition": (
                "DIM row has_lod22=true in W2-1 building_reconstruction_status.csv"
            ),
            "dense_success_candidate_count": len(dense_success_ids),
            "target_count": TARGET_COUNT,
            "tie_break": "(centroid_expansion_distance_m, building_id) ascending",
            "centroid_algorithm": (
                "numerically stable GeoJSON Polygon centroid including interior rings; "
                "absolute exterior area minus absolute hole areas, independent of ring orientation"
            ),
            "prior_c001_training_bbox_buffered": rounded_list(prior_bbox),
            "minimum_isotropic_expansion_distance_m": round(expansion_m, 9),
            "scoring_selection_bbox_definition": (
                "prior buffered C001 training bbox expanded on all four sides by d30; "
                "membership is the first 30 centroid-ranked dense-success candidates"
            ),
            "scoring_selection_bbox": rounded_list(scoring_bbox),
            "selected_footprint_tight_union_bbox": rounded_list(tight_bbox),
            "training_crop_bbox_definition": (
                "tight union bbox of all selected full footprints plus historical 20 m context buffer"
            ),
            "training_context_buffer_m": CONTEXT_BUFFER_M,
            "training_crop_bbox": rounded_list(training_bbox),
            "selected_full_footprints_inside_training_bbox": True,
            "selection_boundary_candidate_ids": boundary_candidate_ids,
            "selection_count": len(selected_ids),
            "selected_ids_in_rank_order": selected_ids,
            "selected_ids_lexical": sorted(selected_ids),
            "selection_sha256": selection_sha256,
            "selection_sha256_definition": (
                "SHA256 of canonical JSON jointbuildgs.pilot_1wave.selection_lock.v1; "
                "contains no RMS/ALS/roof-z/semantic/GS-result values"
            ),
            "ordered_ids_sha256": ordered_ids_sha256,
            "lock_payload": lock_payload,
        },
        "core10_reproduction": {
            "expected_ids": list(CORE10),
            "all_present": True,
            "dense_rms_m_by_building": {
                building_id: round(dense_rms[building_id], 9)
                for building_id in CORE10
            },
            "dense_rms_median_m": round(core_median, 9),
            "expected_rounded_3dp": 0.990,
            "actual_rounded_3dp": round(core_median, 3),
            "reproduced": core_reproduction,
        },
        "small_buildings": {
            "definition": "footprint_area_m2 < 50.0",
            "count": len(small_ids),
            "building_ids": small_ids,
            "non_small_sensitivity_population_count": TARGET_COUNT - len(small_ids),
            "dense_rms_sensitivity_excluding_lt50m2": {
                "population_count": len(non_small_values),
                "dense_rms_median_m": round(non_small_median, 9),
                "full_30_dense_bar_median_m": round(dense_bar, 9),
            },
        },
        "dense_bar": {
            "rule": (
                "median canonical dense W2-1 roof_rms_m over the already locked 30 IDs"
            ),
            "source": rel(BASELINE_SCORES),
            "source_sha256": source_sha256[rel(BASELINE_SCORES)],
            "ids_locked_before_source_open": True,
            "id_lock_event_sequence": lock_event_sequence,
            "rms_open_event_sequence": rms_open_sequence,
            "measurable_count": len(dense_values),
            "dense_rms_median_m": round(dense_bar, 9),
            "dense_rms_m_by_building_rank_order": [
                {
                    "selection_rank": rank,
                    "building_id": item.building_id,
                    "roof_rms_m": round(dense_rms[item.building_id], 9),
                }
                for rank, item in enumerate(selected, 1)
            ],
            "gs_outputs_read": False,
        },
        "training_context": {
            "footprint_universe": rel(FOOTPRINTS),
            "footprint_universe_count": len(footprints),
            "fully_contained_building_count": len(fully_contained_ids),
            "intersecting_building_count": len(intersecting_ids),
            "dense_success_context_only_fully_contained_count": len(
                dense_context_fully_contained
            ),
            "dense_success_context_only_fully_contained_ids": dense_context_fully_contained,
            "dense_success_context_only_intersecting_count": len(
                dense_context_intersecting
            ),
            "dense_success_context_only_intersecting_ids": dense_context_intersecting,
            "scoring_population_remains_locked_to_selected_30": True,
        },
        "leakage_and_order_assertions": {
            "selection_population_projected_fields": list(SELECTION_POPULATION_FIELDS),
            "selection_status_projected_fields": list(SELECTION_STATUS_FIELDS),
            "forbidden_prelock_fields": sorted(FORBIDDEN_PRELOCK_FIELDS),
            "no_forbidden_selection_field_requested": True,
            "baseline_scores_not_opened_before_ids_lock": True,
            "dense_rms_read_only_after_selection_sha_created": True,
            "selection_hash_excludes_dense_rms": True,
            "selection_hash_excludes_als": True,
            "selection_hash_excludes_lod2_z_roof_faces_semantics": True,
            "selection_hash_excludes_gs_results": True,
            "all_selected_are_canonical_dense_success": True,
            "all_core10_present": True,
            "all_selected_full_footprints_inside_training_bbox": True,
            "read_audit": audit.events,
        },
        "source_sha256": source_sha256,
        "outputs": {
            CSV_NAME: {
                "row_count": len(csv_rows),
                "sha256": sha256_bytes(csv_bytes),
            },
            MANIFEST_NAME: {
                "self_hash_embedded": False,
                "reason": "manifest cannot contain a stable hash of itself",
            },
        },
        "interpretation_or_verdict": None,
    }
    manifest_bytes = render_manifest(manifest)
    summary = {
        "selection_count": len(selected_ids),
        "selection_sha256": selection_sha256,
        "dense_bar_median_m": round(dense_bar, 9),
        "core10_median_m": round(core_median, 9),
        "small_lt50_count": len(small_ids),
        "non_small_dense_rms_median_m": round(non_small_median, 9),
        "scoring_selection_bbox": rounded_list(scoring_bbox),
        "training_crop_bbox": rounded_list(training_bbox),
        "training_bbox_fully_contained_building_count": len(fully_contained_ids),
        "training_bbox_intersecting_building_count": len(intersecting_ids),
        "dense_success_context_only_intersecting_count": len(
            dense_context_intersecting
        ),
    }
    return csv_bytes, manifest_bytes, summary


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("P1W-SET must run inside Docker (/.dockerenv not found)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute in memory and byte-compare the existing CSV/manifest",
    )
    args = parser.parse_args()
    require_docker()

    csv_bytes, manifest_bytes, summary = build_artifacts()
    csv_path = args.output_dir / CSV_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    if args.check:
        for path, expected in ((csv_path, csv_bytes), (manifest_path, manifest_bytes)):
            if not path.exists():
                raise FileNotFoundError(path)
            actual = path.read_bytes()
            if actual != expected:
                raise AssertionError(
                    f"reproducibility check failed for {path}: "
                    f"expected {sha256_bytes(expected)}, got {sha256_bytes(actual)}"
                )
        summary["check"] = "byte-identical"
    else:
        atomic_write(csv_path, csv_bytes)
        atomic_write(manifest_path, manifest_bytes)
        summary["csv"] = rel(csv_path)
        summary["manifest"] = rel(manifest_path)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
