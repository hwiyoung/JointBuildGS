#!/usr/bin/env python3
"""Publish a corrected nine-building qualitative review of the P0 DIM baseline.

The selector is deliberately isolated from reconstruction outcomes and reference
geometry.  It first reconstructs the locked 114-building dense LoD2
shape-output-success population (``has_lod22``; quality fields remain separate)
population from two independent records, then selects one input-median case in
each size x observation cell using only five preregistered input covariates.
Only after those nine identifiers are frozen does the renderer bind photos,
the canonical DIM/MVS class-6 cloud, the canonical Roofer CityJSON, and the
evaluation-only reference GML.  Photo overlays use an explicit-datum common
projector and the actual XYZ boundary of the filtered class-6 TIN; the retired
single-height footprint projector is not imported.

This is not a GS run.  Every page says NO GS TRAINING, learning_runs=0,
P0 raw dense DIM/MVS -> Roofer, and scientific_verdict: null.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/cache")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patches
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_root in (SCRIPT_DIR, REPO):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from src.artifact_paths import resolve_existing_path  # noqa: E402

DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.config.v2"
MANIFEST_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.manifest.v2"
AUDIT_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.selection_audit.v1"
EXPECTED_DENSE_SET_SHA256 = "5481f13b5741909ea1fd2cb3fd014459410adea60e3febc72ae8ebb149a2814f"
MANDATORY_LABELS = (
    "NO GS TRAINING",
    "learning_runs=0",
    "P0 raw dense DIM/MVS -> Roofer",
    "scientific_verdict: null",
)


class DenseBaselineError(RuntimeError):
    """A contract, provenance, or publication invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DenseBaselineError(message)


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DenseBaselineError(f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    helper_root = str(path.parent)
    inserted = helper_root not in sys.path
    if inserted:
        sys.path.insert(0, helper_root)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(helper_root)
    return module


E5 = load_module(
    REPO / "scripts/e5_c001/e5_c001_8way.py",
    "dense_baseline_e5_helpers",
)
PANEL_V4 = load_module(
    SCRIPT_DIR / "fusion_w1_aprime_job_panel_v4_20260727.py",
    "dense_baseline_panel_v4_helpers",
)
from src.stage2.colmap_io import (  # noqa: E402
    Camera,
    Image as ColmapImage,
    read_cameras_bin,
    read_images_bin,
)
from src.stage2.image_projection import (  # noqa: E402
    ORTHOMETRIC,
    ProjectionResult,
    base_to_canonical,
    in_frame_mask,
    project_base_points,
)
from roof_boundary_overlay import RoofBoundary, build_roof_boundary  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_path(value: str) -> Path:
    path = Path(value)
    require(not path.is_absolute(), f"repo path must be relative: {value}")
    resolved = (REPO / path).resolve()
    require(resolved == REPO or REPO in resolved.parents, f"repo path escapes root: {value}")
    return resolve_existing_path(REPO, value)


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO))
    except ValueError:
        return str(resolved)


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def set_sha256(values: Iterable[str]) -> str:
    return hashlib.sha256(
        ("\n".join(sorted(str(value) for value in values)) + "\n").encode("utf-8")
    ).hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"source file absent: {path}")
    return {"path": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def bundle_record(staging: Path, path: Path) -> dict[str, Any]:
    record = file_record(path)
    record["path"] = str(path.relative_to(staging))
    return record


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"JSON root is not an object: {path}")
    return payload


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def finite_float(value: Any, label: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise DenseBaselineError(f"{label} is not numeric: {value!r}") from exc
    require(math.isfinite(number), f"{label} is not finite")
    return number


def format_number(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.{digits}f}" if math.isfinite(number) else "n/a"


def load_config(path: Path = DEFAULT_CONFIG, *, verify_sources: bool = True) -> dict[str, Any]:
    config = read_json(path)
    require(config.get("schema") == CONFIG_SCHEMA, "config schema drift")
    require(config.get("branch") == "exp/fusion-w1", "branch contract drift")
    population = config.get("population_contract", {})
    require(population.get("expected_count") == 114, "population count contract drift")
    require(
        population.get("expected_set_sha256") == EXPECTED_DENSE_SET_SHA256,
        "population set SHA contract drift",
    )
    selection = config.get("selection_contract", {})
    require(selection.get("sample_count") == 9, "sample count contract drift")
    require(
        [item.get("field") for item in selection.get("cell_axes", [])]
        == ["stratum_size_area", "stratum_observation_recon_score"],
        "selection cell axes drift",
    )
    require(
        [item.get("field") for item in selection.get("covariates", [])]
        == [
            "pt_density_m2",
            "coverage_frac",
            "n_views_nadir",
            "median_incidence_deg",
            "texture_low_gradient_fraction",
        ],
        "selection covariates drift",
    )
    allowed = set(selection.get("allowed_selector_fields", []))
    prohibited = set(selection.get("prohibited_selector_fields", []))
    require(not allowed & prohibited, "allowed/prohibited selection fields overlap")
    require("assembled" not in allowed and "rf_rmse_lod22" not in allowed, "outcome leaked into selector")
    visual = config.get("visual_contract", {})
    require((visual.get("rows"), visual.get("columns")) == (4, 5), "visual grid drift")
    require(tuple(visual.get("mandatory_labels", [])) == MANDATORY_LABELS, "mandatory labels drift")
    camera = visual.get("camera_contract", {})
    require(camera.get("projection") == "orthographic", "camera projection drift")
    require(float(camera.get("z_exaggeration", 0.0)) == 1.0, "Z exaggeration drift")
    require(
        [item.get("key") for item in camera.get("views", [])]
        == ["top", "oblique_a", "oblique_b", "principal_side"],
        "camera view order drift",
    )
    publication = config.get("publication", {})
    require(publication.get("overwrite_allowed") is False, "overwrite policy drift")
    require(publication.get("output_directory_atomic_publish") is True, "atomic publication drift")
    require(publication.get("learning_runs_started") == 0, "learning count drift")
    require(publication.get("scientific_verdict") is None, "scientific verdict must be null")
    require(publication.get("interpretation") is None, "interpretation must be null")
    execution = config.get("execution", {})
    require(execution.get("network") == "none", "network contract drift")
    require(execution.get("gpus_required") is False, "renderer must be CPU-only")
    require(execution.get("nonroot") is True, "renderer must be nonroot")

    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v2_20260728.sh",
        "tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v2_20260728.py",
        "src/artifact_paths.py",
        "src/stage2/image_projection.py",
        "phases/p2-gsjso/scripts/fusion_w1/roof_boundary_overlay.py",
        "scripts/e5_c001/e5_c001_8way.py",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
    ]
    require(config.get("implementation_files") == expected_implementation, "implementation closure drift")
    for value in expected_implementation:
        require(repo_path(value).is_file(), f"implementation absent: {value}")

    photo_projection = config.get("photo_projection_contract", {})
    require(photo_projection.get("projector") == "src/stage2/image_projection.py", "projector contract drift")
    require(photo_projection.get("input_vertical_datum") == ORTHOMETRIC, "photo datum must be explicit orthometric")
    require(photo_projection.get("flat_single_Z_footprint_projection_forbidden") is True, "flat locator ban absent")
    require(photo_projection.get("reference_roof_boundary_forbidden") is True, "reference boundary ban absent")
    require(int(photo_projection.get("additional_pose_transform_application_count", -1)) == 0, "pose reapplication drift")

    if verify_sources:
        for role, source in config.get("sources", {}).items():
            path_value = source.get("path")
            if not isinstance(path_value, str):
                continue
            path_value_resolved = repo_path(path_value)
            require(path_value_resolved.exists(), f"{role} source absent")
            expected_sha = source.get("sha256")
            if expected_sha is not None:
                require(path_value_resolved.is_file(), f"{role} hash source is not a file")
                require(sha256_file(path_value_resolved) == expected_sha, f"{role} source hash drift")
        pose_manifest = read_json(repo_path(config["sources"]["pose_adoption_manifest"]["path"]))
        require(
            pose_manifest.get("derived_sha256", {}).get("cameras.bin")
            == config["sources"]["corrected_colmap_cameras"]["sha256"],
            "adopted cameras hash binding drift",
        )
        require(
            pose_manifest.get("derived_sha256", {}).get("images.bin")
            == config["sources"]["corrected_colmap_images"]["sha256"],
            "adopted images hash binding drift",
        )
        require(
            float(config["sources"]["projection_datum"]["orthometric_geoid_m"])
            == float(pose_manifest["coordinate_datum"]["orthometric_geoid_m"]),
            "projection geoid/pose manifest drift",
        )
    return config


@dataclass(frozen=True)
class SelectionResult:
    population_ids: tuple[str, ...]
    population_set_sha256: str
    selected: tuple[dict[str, Any], ...]
    audit_rows: tuple[dict[str, Any], ...]
    source_records: tuple[dict[str, Any], ...]
    raw_dense_by_id: Mapping[str, Mapping[str, str]]
    boundary_v2_by_id: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True)
class ProjectionView:
    """One adopted binary COLMAP pose bound to its intrinsic camera."""

    pose: ColmapImage
    camera: Camera

    @property
    def name(self) -> str:
        return str(self.pose.name)

    @property
    def center_canonical(self) -> np.ndarray:
        return -self.pose.R().T @ np.asarray(self.pose.tvec, dtype=np.float64)


def projection_parameters(config: Mapping[str, Any]) -> tuple[str, float, Path]:
    source = config["sources"]["projection_datum"]
    datum = str(source["input_vertical_datum"])
    geoid_m = float(source["orthometric_geoid_m"])
    config_path = repo_path(str(source["path"]))
    require(datum == ORTHOMETRIC, "dense photo projection datum is not orthometric")
    require(math.isfinite(geoid_m), "dense photo projection geoid is not finite")
    return datum, geoid_m, config_path


def load_projection_views(config: Mapping[str, Any]) -> dict[str, ProjectionView]:
    cameras = read_cameras_bin(
        repo_path(config["sources"]["corrected_colmap_cameras"]["path"])
    )
    images = read_images_bin(
        repo_path(config["sources"]["corrected_colmap_images"]["path"])
    )
    require(bool(cameras) and bool(images), "adopted binary COLMAP model is empty")
    output: dict[str, ProjectionView] = {}
    for pose in images.values():
        require(pose.camera_id in cameras, f"camera {pose.camera_id} absent for {pose.name}")
        require(pose.name not in output, f"duplicate adopted image name: {pose.name}")
        output[pose.name] = ProjectionView(pose=pose, camera=cameras[pose.camera_id])
    return output


def build_input_roof_boundary(
    config: Mapping[str, Any], points: np.ndarray
) -> RoofBoundary:
    tin = config["photo_projection_contract"]["tin"]
    return build_roof_boundary(
        points,
        maximum_xy_edge_m=float(tin["maximum_xy_edge_m"]),
        maximum_slope_deg=float(tin["maximum_slope_deg"]),
        minimum_xy_triangle_area_m2=float(tin["minimum_xy_triangle_area_m2"]),
    )


def project_boundary_segments(
    boundary: RoofBoundary,
    view: ProjectionView,
    scene_reference: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, ProjectionResult]:
    datum, geoid_m, datum_config_path = projection_parameters(config)
    segments = np.asarray(boundary.boundary_segments_xyz, dtype=np.float64)
    flat = segments.reshape(-1, 3)
    result = project_base_points(
        flat,
        view.pose,
        view.camera,
        scene_reference,
        input_datum=datum,
        geoid_m=geoid_m,
        config_path=datum_config_path,
    )
    endpoint_inframe = in_frame_mask(result, view.camera).reshape(-1, 2)
    return result.uv.reshape(-1, 2, 2), np.all(endpoint_inframe, axis=1), result


def midrank_01(values_by_id: Mapping[str, float]) -> dict[str, float]:
    """Average midranks scaled to [0, 1], with deterministic tie handling."""
    require(bool(values_by_id), "cannot rank an empty population")
    ordered = sorted(values_by_id.items(), key=lambda item: (item[1], item[0]))
    n = len(ordered)
    if n == 1:
        return {ordered[0][0]: 0.5}
    output: dict[str, float] = {}
    index = 0
    while index < n:
        end = index + 1
        while end < n and ordered[end][1] == ordered[index][1]:
            end += 1
        first_rank = index + 1
        last_rank = end
        average_rank = (first_rank + last_rank) / 2.0
        scaled = (average_rank - 1.0) / (n - 1.0)
        for position in range(index, end):
            output[ordered[position][0]] = float(scaled)
        index = end
    return output


def cell_median_scores(
    candidate_ids: Sequence[str],
    ranks: Mapping[str, Mapping[str, float]],
    covariates: Sequence[str],
) -> tuple[dict[str, float], list[tuple[float, str]]]:
    require(bool(candidate_ids), "cannot score an empty selection cell")
    medians = {
        field: float(np.median([ranks[field][building_id] for building_id in candidate_ids]))
        for field in covariates
    }
    scored = [
        (
            float(
                math.sqrt(
                    sum(
                        (ranks[field][building_id] - medians[field]) ** 2
                        for field in covariates
                    )
                )
            ),
            building_id,
        )
        for building_id in candidate_ids
    ]
    scored.sort(key=lambda item: (item[0], item[1]))
    return medians, scored


def _unique_by(rows: Sequence[Mapping[str, str]], key: str, expected: int, label: str) -> dict[str, Mapping[str, str]]:
    output: dict[str, Mapping[str, str]] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        require(bool(value), f"{label} has an empty {key}")
        require(value not in output, f"{label} duplicates {value}")
        output[value] = row
    require(len(output) == expected, f"{label} count {len(output)} != {expected}")
    return output


def reconstruct_population(config: Mapping[str, Any]) -> tuple[tuple[str, ...], dict[str, Mapping[str, str]], tuple[dict[str, Any], ...]]:
    sources = config["sources"]
    inventory_path = repo_path(sources["label_inventory"]["path"])
    snapshot_path = repo_path(sources["regression_snapshot"]["path"])
    inventory = read_json(inventory_path)
    inventory_ids = tuple(str(value) for value in inventory.get("dense_success_buildings", []))
    require(len(inventory_ids) == 114 and len(set(inventory_ids)) == 114, "label inventory dense 114 drift")
    require(tuple(sorted(inventory_ids)) == inventory_ids, "label inventory dense IDs are not sorted")
    require(
        inventory.get("dense_success_set_sha256") == EXPECTED_DENSE_SET_SHA256,
        "label inventory declared dense set SHA drift",
    )
    require(set_sha256(inventory_ids) == EXPECTED_DENSE_SET_SHA256, "label inventory computed set SHA drift")

    snapshot = read_csv(snapshot_path)
    lidar_rows = [row for row in snapshot if row.get("arm") == "raw_lidar"]
    dense_rows = [row for row in snapshot if row.get("arm") == "raw_dense"]
    lidar = _unique_by(lidar_rows, "building_id", 199, "regression raw_lidar")
    dense = _unique_by(dense_rows, "building_id", 199, "regression raw_dense")
    canonical_lidar = {bid for bid, row in lidar.items() if as_bool(row.get("assembled"))}
    all_dense_assembled = {bid for bid, row in dense.items() if as_bool(row.get("assembled"))}
    regression_intersection = canonical_lidar & all_dense_assembled
    population = config["population_contract"]
    require(len(canonical_lidar) == int(population["canonical_raw_lidar_assembled_expected"]), "canonical LiDAR count drift")
    require(len(all_dense_assembled) == int(population["raw_dense_assembled_true_expected"]), "raw dense assembled count drift")
    require(len(regression_intersection) == 114, "regression dense-success intersection count drift")
    require(regression_intersection == set(inventory_ids), "inventory/regression dense-success set mismatch")
    require(set_sha256(regression_intersection) == EXPECTED_DENSE_SET_SHA256, "regression set SHA drift")
    records = (file_record(inventory_path), file_record(snapshot_path))
    return tuple(sorted(regression_intersection)), dense, records


def select_sample(config: Mapping[str, Any]) -> SelectionResult:
    population_ids, raw_dense_by_id, population_records = reconstruct_population(config)
    v2_path = repo_path(config["sources"]["boundary_map_v2_ladder"]["path"])
    v2_rows = read_csv(v2_path)
    v2_by_id = _unique_by(v2_rows, "building_id", 178, "boundary_map_v2 ladder")
    require(set(population_ids) <= set(v2_by_id), "dense 114 is not covered by boundary_map_v2")

    selection = config["selection_contract"]
    axes = [item["field"] for item in selection["cell_axes"]]
    covariates = [item["field"] for item in selection["covariates"]]
    allowed = set(selection["allowed_selector_fields"])
    expected_allowed = {"building_id", *axes, *covariates}
    require(allowed == expected_allowed, "selector whitelist is not exact")

    sanitized: dict[str, dict[str, Any]] = {}
    for building_id in population_ids:
        dense = raw_dense_by_id[building_id]
        boundary = v2_by_id[building_id]
        row: dict[str, Any] = {
            "building_id": building_id,
            axes[0]: str(dense.get(axes[0], "")).strip(),
            axes[1]: str(dense.get(axes[1], "")).strip(),
            "pt_density_m2": finite_float(dense.get("pt_density_m2"), f"{building_id}.pt_density_m2"),
            "coverage_frac": finite_float(dense.get("coverage_frac"), f"{building_id}.coverage_frac"),
            "n_views_nadir": finite_float(dense.get("n_views_nadir"), f"{building_id}.n_views_nadir"),
            "median_incidence_deg": finite_float(
                dense.get("median_incidence_deg"), f"{building_id}.median_incidence_deg"
            ),
            "texture_low_gradient_fraction": finite_float(
                boundary.get("texture_low_gradient_fraction"),
                f"{building_id}.texture_low_gradient_fraction",
            ),
        }
        require(set(row) == allowed, f"selector row exposes non-whitelisted fields for {building_id}")
        sanitized[building_id] = row

    ranks: dict[str, dict[str, float]] = {}
    for field in covariates:
        ranks[field] = midrank_01({bid: float(row[field]) for bid, row in sanitized.items()})

    level_a = list(selection["cell_axes"][0]["levels"])
    level_b = list(selection["cell_axes"][1]["levels"])
    expected_cells = [(a, b) for a in level_a for b in level_b]
    grouped: dict[tuple[str, str], list[str]] = {cell: [] for cell in expected_cells}
    for building_id, row in sanitized.items():
        cell = (str(row[axes[0]]), str(row[axes[1]]))
        require(cell in grouped, f"unexpected selection cell {cell} for {building_id}")
        grouped[cell].append(building_id)
    require(all(grouped[cell] for cell in expected_cells), "one or more selection cells are empty")

    audit_rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for cell_index, cell in enumerate(expected_cells, start=1):
        candidate_ids = sorted(grouped[cell])
        medians, scored = cell_median_scores(candidate_ids, ranks, covariates)
        winner = scored[0][1]
        candidate_rank = {building_id: index for index, (_distance, building_id) in enumerate(scored, start=1)}
        for distance, building_id in scored:
            source = sanitized[building_id]
            audit: dict[str, Any] = {
                "cell_index": cell_index,
                axes[0]: cell[0],
                axes[1]: cell[1],
                "cell_candidate_count": len(candidate_ids),
                "building_id": building_id,
                "candidate_rank_in_cell": candidate_rank[building_id],
                "selected": building_id == winner,
                "distance_to_cell_median_l2": distance,
            }
            for field in covariates:
                audit[field] = source[field]
                audit[f"rank_{field}"] = ranks[field][building_id]
                audit[f"cell_median_rank_{field}"] = medians[field]
            require(not set(audit) & set(selection["prohibited_selector_fields"]), "prohibited field entered audit")
            audit_rows.append(audit)
        winner_row = dict(next(row for row in audit_rows if row["building_id"] == winner and row["cell_index"] == cell_index))
        selected.append(winner_row)

    selected_ids = [row["building_id"] for row in selected]
    require(len(selected_ids) == 9 and len(set(selected_ids)) == 9, "selector did not produce nine unique buildings")
    require(sum(bool(row["selected"]) for row in audit_rows) == 9, "selection audit winner count drift")
    return SelectionResult(
        population_ids=population_ids,
        population_set_sha256=set_sha256(population_ids),
        selected=tuple(selected),
        audit_rows=tuple(audit_rows),
        source_records=tuple([*population_records, file_record(v2_path)]),
        raw_dense_by_id=raw_dense_by_id,
        boundary_v2_by_id=v2_by_id,
    )


def load_font(config: Mapping[str, Any]) -> tuple[font_manager.FontProperties, dict[str, Any]]:
    execution = config["execution"]
    path = Path(os.environ.get("DENSE_BASELINE_QUAL_FONT", execution["font_container_path"]))
    require(path.is_file(), f"required CJK font absent: {path}")
    record = file_record(path)
    require(record["sha256"] == execution["font_sha256"], "CJK font hash drift")
    require(record["bytes"] == int(execution["font_bytes"]), "CJK font size drift")
    font_manager.fontManager.addfont(str(path))
    font = font_manager.FontProperties(fname=str(path))
    plt.rcParams["axes.unicode_minus"] = False
    return font, record


def load_locked_footprints(
    config: Mapping[str, Any], building_ids: Iterable[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the hash-locked GeoPackage itself; never substitute its GeoJSON cache."""
    source = config["sources"]["approved_footprint_xy"]
    locator_config = {
        "input_locator_contract": {
            "footprint_xy": source["path"],
            "footprint_sha256": source["sha256"],
            "footprint_layer": source["layer"],
            "footprint_id_field": source["id_field"],
        }
    }
    output: dict[str, Any] = {}
    record: dict[str, Any] | None = None
    for building_id in sorted(set(building_ids)):
        ring, observed = PANEL_V4.load_approved_footprint_xy(locator_config, building_id)
        polygon = E5.Polygon(np.asarray(ring, dtype=np.float64))
        require(polygon.is_valid and not polygon.is_empty and polygon.area > 0.0, f"invalid footprint: {building_id}")
        output[building_id] = polygon
        if record is None:
            record = observed
        else:
            require(observed == record, "footprint GeoPackage record changed during load")
    require(bool(output) and record is not None, "no locked footprints loaded")
    return output, record


def polygon_area_uv(values: np.ndarray) -> float:
    ring = np.asarray(values, dtype=np.float64)
    require(ring.ndim == 2 and ring.shape[1] == 2 and len(ring) >= 3, "projected ring malformed")
    return 0.5 * abs(
        float(
            np.dot(ring[:, 0], np.roll(ring[:, 1], -1))
            - np.dot(ring[:, 1], np.roll(ring[:, 0], -1))
        )
    )


def circular_separation_deg(first: float, second: float) -> float:
    return abs((float(first) - float(second) + 180.0) % 360.0 - 180.0)


def select_geometry_photo_views(
    points: np.ndarray,
    boundary: RoofBoundary,
    views_by_name: Mapping[str, ProjectionView],
    scene_reference: Mapping[str, Any],
    image_directory: Path,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Choose three datum-safe, boundary-visible photo addresses.

    The selector projects actual XYZ from the DIM class-6 TIN support boundary.
    It never flattens a GroundSurface footprint to one height.  The first view
    is nadir-first among sufficiently large boundary projections; the next two
    maximize camera-azimuth separation.  Image pixels and reference geometry
    remain outside this post-building-selection address binding.
    """
    require(len(points) > 0, "photo selection requires class-6 points")
    contract = config["photo_projection_contract"]
    datum, geoid_m, datum_config_path = projection_parameters(config)
    target_base = np.median(np.asarray(points, dtype=np.float64), axis=0).reshape(1, 3)
    target_canonical = base_to_canonical(
        target_base,
        scene_reference,
        input_datum=datum,
        geoid_m=geoid_m,
        config_path=datum_config_path,
    )[0]
    selection_points = downsample(
        np.asarray(points, dtype=np.float64),
        min(5000, int(config["visual_contract"]["maximum_projected_points"])),
    )
    candidates: list[dict[str, Any]] = []
    for name in sorted(views_by_name):
        view = views_by_name[name]
        camera = view.camera
        image_path = image_directory / name
        if not image_path.is_file():
            continue
        boundary_uv, boundary_edges_inframe, _boundary_result = project_boundary_segments(
            boundary, view, scene_reference, config
        )
        boundary_fraction = float(np.mean(boundary_edges_inframe))
        if boundary_fraction < float(contract["minimum_boundary_inframe_fraction"]):
            continue
        visible_boundary_uv = boundary_uv[boundary_edges_inframe].reshape(-1, 2)
        if len(visible_boundary_uv) < 3:
            continue
        lower = visible_boundary_uv.min(axis=0)
        upper = visible_boundary_uv.max(axis=0)
        area = float(np.prod(np.maximum(upper - lower, 0.0)))
        if (
            not math.isfinite(area)
            or area < float(contract["minimum_projected_boundary_bbox_area_px2"])
        ):
            continue
        point_result = project_base_points(
            selection_points,
            view.pose,
            view.camera,
            scene_reference,
            input_datum=datum,
            geoid_m=geoid_m,
            config_path=datum_config_path,
        )
        point_inframe = in_frame_mask(point_result, view.camera)
        point_fraction = float(np.mean(point_inframe))
        if point_fraction < float(contract["minimum_dense_points_inframe_fraction"]):
            continue
        width, height = int(camera.width), int(camera.height)
        frame_center = np.asarray([width / 2.0, height / 2.0], dtype=np.float64)
        frame_scale = float(np.hypot(width / 2.0, height / 2.0))
        projected_center = np.mean(visible_boundary_uv, axis=0)
        frame_radius = float(np.linalg.norm(projected_center - frame_center) / frame_scale)
        delta = np.asarray(view.center_canonical, dtype=np.float64) - target_canonical
        horizontal = float(np.linalg.norm(delta[:2]))
        vertical = abs(float(delta[2]))
        nadir = float(math.degrees(math.atan2(horizontal, max(vertical, 1.0e-9))))
        azimuth = float(math.degrees(math.atan2(delta[1], delta[0])) % 360.0)
        candidates.append(
            {
                "name": name,
                "projected_boundary_bbox_area_px2": area,
                "boundary_edges_inframe_fraction": boundary_fraction,
                "dense_points_inframe_fraction": point_fraction,
                "frame_radius": frame_radius,
                "nadir_deg": nadir,
                "camera_azimuth_deg": azimuth,
                "boundary_edges_n": int(len(boundary.boundary_edge_vertex_indices)),
            }
        )
    require(len(candidates) >= 3, "fewer than three datum-safe boundary-visible COLMAP views")
    maximum_area = max(float(item["projected_boundary_bbox_area_px2"]) for item in candidates)
    eligible = [
        item
        for item in candidates
        if float(item["projected_boundary_bbox_area_px2"]) >= 0.35 * maximum_area
    ]
    if len(eligible) < 3:
        eligible = list(candidates)
    first = min(
        eligible,
        key=lambda item: (
            float(item["nadir_deg"]),
            float(item["frame_radius"]),
            -float(item["projected_boundary_bbox_area_px2"]),
            str(item["name"]),
        ),
    )
    selected = [first]
    remaining = [item for item in eligible if item["name"] != first["name"]]
    while len(selected) < 3:
        require(bool(remaining), "geometry view diversity selection exhausted")
        ranked = sorted(
            remaining,
            key=lambda item: (
                -min(
                    circular_separation_deg(
                        float(item["camera_azimuth_deg"]),
                        float(chosen["camera_azimuth_deg"]),
                    )
                    for chosen in selected
                ),
                float(item["frame_radius"]),
                -float(item["projected_boundary_bbox_area_px2"]),
                str(item["name"]),
            ),
        )
        selected.append(ranked[0])
        remaining = [item for item in remaining if item["name"] != ranked[0]["name"]]
    for index, item in enumerate(selected, start=1):
        image_path = image_directory / str(item["name"])
        view = views_by_name[str(item["name"])]
        expected_size = (int(view.camera.width), int(view.camera.height))
        with Image.open(image_path) as source:
            observed_size = tuple(int(value) for value in source.size)
        require(
            observed_size == expected_size,
            (
                f"COLMAP-bound image dimensions differ for {image_path.name}: "
                f"image={observed_size}, camera={expected_size}"
            ),
        )
        item["selection_order"] = index
        item["candidate_count"] = len(candidates)
        item["area_eligible_count"] = len(eligible)
        item["maximum_projected_boundary_bbox_area_px2"] = maximum_area
        item["selection_method"] = (
            "postselection_actual_class6_TIN_boundary_adopted_pose_nadir_then_azimuth_diversity"
        )
        item["image_pixels_used_for_ranking"] = False
        item["reference_geometry_used_for_ranking"] = False
        item["flat_single_Z_footprint_used"] = False
        item["camera_bound_image_dimensions"] = list(observed_size)
    return selected


def load_cityjson_surfaces_for_building(
    payload: Mapping[str, Any], building_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Target-filtered variant of the v4 CityJSON surface loader."""
    require(payload.get("type") == "CityJSON", "canonical Roofer artifact is not CityJSON")
    vertices = np.asarray(payload.get("vertices") or [], dtype=np.float64)
    require(vertices.ndim == 2 and vertices.shape[1] == 3, "CityJSON vertices malformed")
    transform = payload.get("transform") or {}
    vertices = vertices * np.asarray(transform.get("scale", [1, 1, 1]), dtype=np.float64)
    vertices = vertices + np.asarray(transform.get("translate", [0, 0, 0]), dtype=np.float64)
    city_objects = payload.get("CityObjects") or {}
    parent = city_objects.get(building_id) or {}
    object_ids = {building_id, *[str(value) for value in parent.get("children") or []]}
    object_ids.update(
        str(object_id)
        for object_id, city_object in city_objects.items()
        if building_id in (city_object.get("parents") or [])
    )
    candidates: list[tuple[float, str, Mapping[str, Any]]] = []
    for object_id in sorted(object_ids):
        city_object = city_objects.get(object_id)
        if not isinstance(city_object, Mapping):
            continue
        for geometry in city_object.get("geometry") or []:
            lod = PANEL_V4.numeric_lod(geometry.get("lod"))
            if geometry.get("type") == "Solid" and lod >= 2.0:
                candidates.append((lod, object_id, geometry))
    require(bool(candidates), f"canonical Roofer has no target LoD2 Solid for {building_id}")
    selected_lod = max(item[0] for item in candidates)
    surfaces: list[dict[str, Any]] = []
    used_vertices: set[int] = set()
    for lod, object_id, geometry in candidates:
        if lod != selected_lod:
            continue
        semantics = geometry.get("semantics") or {}
        semantic_surfaces = semantics.get("surfaces") or []
        semantic_values = semantics.get("values") or []
        for shell_index, shell in enumerate(geometry.get("boundaries") or []):
            if not isinstance(shell, list):
                continue
            shell_values = semantic_values[shell_index] if shell_index < len(semantic_values) else []
            for surface_index, rings in enumerate(shell):
                if not isinstance(rings, list) or not rings:
                    continue
                rings_xyz: list[np.ndarray] = []
                for ring in rings:
                    require(isinstance(ring, list) and len(ring) >= 3, "CityJSON ring malformed")
                    indices = [int(value) for value in ring]
                    require(min(indices) >= 0 and max(indices) < len(vertices), "CityJSON index out of range")
                    used_vertices.update(indices)
                    rings_xyz.append(vertices[indices])
                semantic_index = shell_values[surface_index] if surface_index < len(shell_values) else None
                semantic_type = "UnknownSurface"
                if isinstance(semantic_index, int) and 0 <= semantic_index < len(semantic_surfaces):
                    semantic_type = str(semantic_surfaces[semantic_index].get("type", semantic_type))
                surfaces.append(
                    {
                        "xyz": rings_xyz[0],
                        "rings_xyz": rings_xyz,
                        "semantic_type": semantic_type,
                        "object_id": object_id,
                        "lod": lod,
                    }
                )
    require(bool(surfaces), f"target LoD2 Solid has no surfaces for {building_id}")
    counts = Counter(str(surface["semantic_type"]) for surface in surfaces)
    rings_n = sum(len(surface["rings_xyz"]) for surface in surfaces)
    return surfaces, {
        "lod": selected_lod,
        "surfaces_n": len(surfaces),
        "semantic_counts": dict(counts),
        "vertices_n": len(used_vertices),
        "rings_n": rings_n,
        "interior_rings_n": rings_n - len(surfaces),
    }


def render_config(config: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(config)
    visual = dict(config["visual_contract"])
    visual["semantic_palette"] = dict(visual["palette"])
    copied["visual_contract"] = visual
    return copied


def scene_frame(
    points: np.ndarray,
    surfaces: Sequence[Mapping[str, Any]],
    reference_rings: Sequence[np.ndarray],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    arrays = [np.asarray(points, dtype=np.float64)]
    arrays.extend(np.asarray(item["xyz"], dtype=np.float64) for item in surfaces)
    arrays.extend(np.asarray(ring, dtype=np.float64)[:, :3] for ring in reference_rings)
    xyz = np.vstack(arrays)
    require(np.isfinite(xyz).all(), "scene contains non-finite coordinates")
    minimum = xyz.min(axis=0)
    maximum = xyz.max(axis=0)
    origin = np.asarray(
        [
            round(float((minimum[0] + maximum[0]) / 2.0), 3),
            round(float((minimum[1] + maximum[1]) / 2.0), 3),
            round(float(minimum[2]), 3),
        ]
    )
    local_minimum = minimum - origin
    local_maximum = maximum - origin
    span = local_maximum - local_minimum
    require(np.all(span > 1.0e-8), "scene has degenerate bounds")
    camera_contract = config["visual_contract"]["camera_contract"]
    padding = span * float(camera_contract["bounds_padding_fraction"])
    bounds = np.column_stack((local_minimum - padding, local_maximum + padding))
    axis = PANEL_V4.principal_axis(surfaces, config)
    cameras: list[dict[str, Any]] = []
    for view in camera_contract["views"]:
        azimuth = (
            float(view["azimuth_deg"])
            if view["azimuth_mode"] == "fixed"
            else axis["azimuth_deg_from_east"] + float(view["azimuth_offset_deg"])
        )
        cameras.append(
            {
                "key": view["key"],
                "title_ko": view["title_ko"],
                "title_en": view["title_en"],
                "elevation_deg": float(view["elevation_deg"]),
                "azimuth_deg": float(azimuth % 360.0),
                "projection": "orthographic",
            }
        )
    return {
        "crs": "EPSG:25832",
        "bounds_source": "DIM_class6_plus_canonical_output_plus_evaluation_only_reference",
        "view_orientation_source": axis["source"],
        "reference_view_orientation_influence": False,
        "reference_shared_bounds_influence": True,
        "local_origin_epsg25832_xyz": [float(value) for value in origin],
        "local_bounds_xyz": [[float(value) for value in pair] for pair in bounds],
        "z_exaggeration": 1.0,
        "axis": axis,
        "cameras": cameras,
    }


def downsample(values: np.ndarray, maximum: int) -> np.ndarray:
    array = np.asarray(values)
    if len(array) <= maximum:
        return array
    indices = np.linspace(0, len(array) - 1, maximum, dtype=np.int64)
    return array[indices]


def plot_dense_points(
    ax: Any,
    points: np.ndarray,
    frame: Mapping[str, Any],
    config: Mapping[str, Any],
) -> int:
    shown = downsample(points, int(config["visual_contract"]["maximum_scatter_points"]))
    local = PANEL_V4.local_xyz(shown, frame)
    ax.scatter(
        local[:, 0],
        local[:, 1],
        local[:, 2],
        s=3.0,
        c=local[:, 2],
        cmap="Blues",
        edgecolors="none",
        depthshade=False,
        rasterized=True,
    )
    return len(shown)


def text_panel(
    ax: Any,
    title: str,
    lines: Sequence[str],
    font: font_manager.FontProperties,
) -> None:
    ax.axis("off")
    ax.set_title(title, fontproperties=font, fontsize=9.2, color="#252a31", pad=6)
    ax.text(
        0.035,
        0.955,
        "\n".join(lines),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=7.7,
        color="#252a31",
        fontproperties=font,
        linespacing=1.38,
    )
    ax.add_patch(
        patches.Rectangle(
            (0.01, 0.01),
            0.98,
            0.98,
            transform=ax.transAxes,
            fill=False,
            edgecolor="#d7dce1",
            linewidth=0.8,
        )
    )


def projected_photo_panel(
    ax: Any,
    image_path: Path,
    view: ProjectionView,
    scene_reference: Mapping[str, Any],
    points: np.ndarray,
    boundary: RoofBoundary,
    config: Mapping[str, Any],
    font: font_manager.FontProperties,
    index: int,
) -> dict[str, Any]:
    maximum = int(config["visual_contract"]["maximum_projected_points"])
    shown = downsample(points, maximum)
    datum, geoid_m, datum_config_path = projection_parameters(config)
    point_result = project_base_points(
        shown,
        view.pose,
        view.camera,
        scene_reference,
        input_datum=datum,
        geoid_m=geoid_m,
        config_path=datum_config_path,
    )
    point_uv = point_result.uv
    point_inframe = in_frame_mask(point_result, view.camera)
    boundary_uv, boundary_edge_inframe, _boundary_result = project_boundary_segments(
        boundary, view, scene_reference, config
    )
    require(
        float(np.mean(boundary_edge_inframe))
        >= float(config["photo_projection_contract"]["minimum_boundary_inframe_fraction"]),
        f"actual class-6 TIN boundary is insufficiently visible in {image_path.name}",
    )
    visible_boundary_uv = boundary_uv[boundary_edge_inframe]
    require(len(visible_boundary_uv) > 0, f"actual class-6 TIN boundary absent in {image_path.name}")
    width, height = int(view.camera.width), int(view.camera.height)
    crop_values = [visible_boundary_uv.reshape(-1, 2)]
    if np.any(point_inframe):
        crop_values.append(point_uv[point_inframe])
    crop = np.vstack(crop_values)
    lower = np.floor(crop.min(axis=0)).astype(int)
    upper = np.ceil(crop.max(axis=0)).astype(int) + 1
    padding_fraction = float(config["visual_contract"]["photo_crop_padding_fraction"])
    pad_x = max(18, int((upper[0] - lower[0]) * padding_fraction))
    pad_y = max(18, int((upper[1] - lower[1]) * padding_fraction))
    box = (
        max(0, int(lower[0]) - pad_x),
        max(0, int(lower[1]) - pad_y),
        min(width, int(upper[0]) + pad_x),
        min(height, int(upper[1]) + pad_y),
    )
    require(box[2] > box[0] and box[3] > box[1], "photo crop is empty")
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        require(image.size == (width, height), f"camera/image dimensions differ for {image_path.name}")
        cropped = np.asarray(image.crop(box))
    offset = np.asarray([box[0], box[1]], dtype=np.float64)
    palette = config["visual_contract"]["palette"]
    ax.imshow(cropped)
    for segment_index, segment in enumerate(visible_boundary_uv):
        local_segment = segment - offset
        ax.plot(
            local_segment[:, 0],
            local_segment[:, 1],
            color=palette["target_locator"],
            linewidth=2.0,
            linestyle="-",
            label="actual DIM class-6 TIN boundary" if segment_index == 0 else None,
        )
    visible_points = point_uv[point_inframe] - offset
    if len(visible_points):
        ax.scatter(
            visible_points[:, 0],
            visible_points[:, 1],
            s=5.0,
            c=palette["dense_projection"],
            linewidths=0,
            alpha=0.82,
            rasterized=True,
            label="actual DIM class 6 projection",
        )
    ax.axis("off")
    ax.set_title(
        f"기하 선택 사진 {index} · {image_path.name}\nDatum-safe photo {index} · actual class-6 TIN boundary + points",
        fontproperties=font,
        fontsize=8.2,
        color="#252a31",
        pad=5,
    )
    ax.legend(loc="lower left", fontsize=5.2, framealpha=0.86, markerscale=1.2)
    return {
        "image_name": image_path.name,
        "image_record": file_record(image_path),
        "crop_xyxy": list(box),
        "dense_points_projected": len(shown),
        "dense_points_in_frame": int(np.count_nonzero(point_inframe)),
        "boundary_edges_total": int(len(boundary.boundary_edge_vertex_indices)),
        "boundary_edges_in_frame": int(np.count_nonzero(boundary_edge_inframe)),
        "boundary_components_n": int(boundary.tin_stats["boundary_components_n"]),
        "projector": "src/stage2/image_projection.py",
        "input_vertical_datum": datum,
        "geoid_m": geoid_m,
        "flat_single_Z_footprint_used": False,
        "independent_RGB_alignment_gate": "not_run_projection_source_audit_only",
    }


def output_reference_facts(
    surfaces: Sequence[Mapping[str, Any]], reference_rings: Sequence[np.ndarray]
) -> dict[str, Any]:
    output_xyz = np.vstack([np.asarray(item["xyz"], dtype=np.float64) for item in surfaces])
    reference_xyz = np.vstack([np.asarray(item, dtype=np.float64)[:, :3] for item in reference_rings])
    output_xy = np.unique(np.round(output_xyz[:, :2], 9), axis=0)
    reference_xy = np.unique(np.round(reference_xyz[:, :2], 9), axis=0)
    output_xyz_unique = np.unique(np.round(output_xyz[:, :3], 9), axis=0)
    reference_xyz_unique = np.unique(np.round(reference_xyz[:, :3], 9), axis=0)
    return {
        "output_unique_xy_n": len(output_xy),
        "reference_unique_xy_n": len(reference_xy),
        "output_unique_xyz_n": len(output_xyz_unique),
        "reference_unique_xyz_n": len(reference_xyz_unique),
        "exact_XY_coordinate_set_equal": bool(
            output_xy.shape == reference_xy.shape and np.array_equal(output_xy, reference_xy)
        ),
        "exact_XYZ_coordinate_set_equal": bool(
            output_xyz_unique.shape == reference_xyz_unique.shape
            and np.array_equal(output_xyz_unique, reference_xyz_unique)
        ),
        "output_z_min_m": float(output_xyz[:, 2].min()),
        "output_z_max_m": float(output_xyz[:, 2].max()),
        "reference_z_min_m": float(reference_xyz[:, 2].min()),
        "reference_z_max_m": float(reference_xyz[:, 2].max()),
    }


def render_building(
    staging: Path,
    pdf: PdfPages,
    config: Mapping[str, Any],
    selection_row: Mapping[str, Any],
    points: np.ndarray,
    boundary: RoofBoundary,
    surfaces: Sequence[Mapping[str, Any]],
    surface_stats: Mapping[str, Any],
    reference_rings: Sequence[np.ndarray],
    status_row: Mapping[str, str],
    photo_views: Sequence[Mapping[str, Any]],
    projection_views_by_name: Mapping[str, ProjectionView],
    scene_reference: Mapping[str, Any],
    font: font_manager.FontProperties,
) -> dict[str, Any]:
    building_id = str(selection_row["building_id"])
    require(len(points) > 0, f"{building_id} has no DIM class-6 points")
    require(bool(reference_rings), f"{building_id} has no reference roof rings")
    frame = scene_frame(points, surfaces, reference_rings, config)
    evidence = {"cityjson_surfaces": surfaces, "reference_rings": reference_rings}
    helper_config = render_config(config)
    comparison = output_reference_facts(surfaces, reference_rings)

    visual = config["visual_contract"]
    fig = plt.figure(figsize=tuple(visual["panel_inches"]))
    grid = fig.add_gridspec(
        4,
        5,
        left=0.043,
        right=0.987,
        bottom=0.060,
        top=0.902,
        wspace=0.16,
        hspace=0.25,
    )
    size_field = "stratum_size_area"
    obs_field = "stratum_observation_recon_score"
    fig.suptitle(
        f"{building_id} | size={selection_row[size_field]} × observation={selection_row[obs_field]}\n"
        "P0 raw dense DIM/MVS -> Roofer | NO GS TRAINING | learning_runs=0 | scientific_verdict: null",
        fontproperties=font,
        fontsize=15,
        color="#252a31",
    )
    for y, label in (
        (0.790, "1  입력 사진 / Input photos"),
        (0.575, "2  DIM class 6 / Dense points"),
        (0.360, "3  P0 Roofer / Canonical output"),
        (0.145, "4  평가 전용 / Evaluation-only overlay"),
    ):
        fig.text(
            0.008,
            y,
            label,
            rotation=90,
            va="center",
            ha="center",
            fontsize=8.0,
            color="#252a31",
            fontproperties=font,
        )

    photo_receipts: list[dict[str, Any]] = []
    image_directory = repo_path(config["sources"]["image_directory"]["path"])
    require(len(photo_views) == 3, f"{building_id} photo view count is not three")
    for column, view in enumerate(photo_views):
        image_name = str(view.get("name", ""))
        require(image_name in projection_views_by_name, f"camera absent for frozen view: {image_name}")
        image_path = image_directory / image_name
        require(image_path.is_file(), f"image absent for frozen view: {image_name}")
        photo_receipt = projected_photo_panel(
            fig.add_subplot(grid[0, column]),
            image_path,
            projection_views_by_name[image_name],
            scene_reference,
            points,
            boundary,
            config,
            font,
            column + 1,
        )
        photo_receipt["geometry_selection"] = dict(view)
        photo_receipts.append(photo_receipt)

    covariates = [item["field"] for item in config["selection_contract"]["covariates"]]
    input_lines = [
        "표본선정 입력 / selection inputs only",
        f"cell: size={selection_row[size_field]}, observation={selection_row[obs_field]}",
        f"cell candidates: {selection_row['cell_candidate_count']}",
        f"global-rank L2 to cell median: {selection_row['distance_to_cell_median_l2']:.6f}",
        "",
    ]
    input_lines.extend(
        f"{field}: {format_number(selection_row[field], 4)}  "
        f"(rank {format_number(selection_row['rank_' + field], 4)})"
        for field in covariates
    )
    input_lines.extend(
        [
            "",
            f"DIM class 6 points: {len(points)}",
            f"actual class-6 TIN boundary edges: {len(boundary.boundary_edge_vertex_indices)}",
            "photo addresses: adopted binary pose + explicit orthometric datum after sample lock",
            "view rank: actual TIN boundary visibility; nadir-first, then azimuth diversity",
            "yellow segments: actual DIM class-6 TIN support boundary (real XYZ)",
            "cyan dots: actual classified DIM/MVS class 6 projection",
            "single-height footprint projection: forbidden / not used",
            "RGB-independent semantic alignment gate: not run; projection-source audit only",
            "sample selection used no RMSE, roof count/type, output geometry, or reference geometry",
            "NO GS TRAINING | learning_runs=0",
            "scientific_verdict: null",
        ]
    )
    text_panel(fig.add_subplot(grid[0, 3:5]), "입력·선정 요약 / Input and selection audit", input_lines, font)

    displayed_points = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[1, column], projection="3d")
        displayed_points = plot_dense_points(ax, points, frame, config)
        PANEL_V4.configure_3d_axis(ax, frame, camera)
        PANEL_V4.short_title(
            ax,
            f"DIM/MVS class 6 · {camera['title_ko']}",
            f"Raw dense building points · {camera['title_en']}",
            font,
            fontsize=8.2,
        )
    ax = fig.add_subplot(grid[1, 4])
    shown = downsample(points, int(visual["maximum_scatter_points"]))
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    principal = np.asarray(frame["axis"]["vector_east_north"], dtype=np.float64)
    horizontal = (shown[:, :2] - origin[:2]) @ principal
    vertical = shown[:, 2] - origin[2]
    ax.scatter(horizontal, vertical, s=2.0, color=visual["palette"]["dense_points"], linewidths=0, rasterized=True)
    ax.set_xlabel("principal horizontal (m)", fontsize=7)
    ax.set_ylabel("ΔZ (m)", fontsize=7)
    ax.grid(True, color=visual["palette"]["light_grey"], linewidth=0.45)
    ax.tick_params(labelsize=6)
    ax.set_aspect("equal", adjustable="datalim")
    PANEL_V4.short_title(ax, "DIM class 6 주축 단면", "Principal section · raw dense points", font, fontsize=8.2)

    cityjson_render = PANEL_V4.cityjson_render_parts(surfaces, frame)["stats"]
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[2, column], projection="3d")
        PANEL_V4.plot_cityjson(ax, evidence, frame, helper_config, alpha=0.92)
        PANEL_V4.configure_3d_axis(ax, frame, camera)
        PANEL_V4.short_title(
            ax,
            f"P0 DIM Roofer · {camera['title_ko']}",
            f"Canonical CityJSON · {camera['title_en']}",
            font,
            fontsize=8.2,
        )
    semantic = surface_stats["semantic_counts"]
    output_lines = [
        "canonical P0 DIM Roofer CityJSON LoD2.2",
        "source_model_id: canonical_dense_w2_1",
        "raw dense DIM/MVS -> Roofer",
        "NO GS TRAINING | learning_runs=0",
        "",
        f"LoD: {format_number(surface_stats['lod'], 1)} Solid",
        f"surfaces / vertices: {surface_stats['surfaces_n']} / {surface_stats['vertices_n']}",
        f"RoofSurface: {semantic.get('RoofSurface', 0)}",
        f"WallSurface: {semantic.get('WallSurface', 0)}",
        f"GroundSurface: {semantic.get('GroundSurface', 0)}",
        f"interior rings: {surface_stats['interior_rings_n']}",
        f"wireframe-only hole surfaces: {cityjson_render['wireframe_only_surfaces_n']}",
        f"canonical status / has_lod22: {status_row.get('status', 'n/a')} / {status_row.get('has_lod22', 'n/a')}",
        f"val3dity valid: {status_row.get('val3dity_valid', 'n/a')}",
        "scientific_verdict: null",
    ]
    text_panel(fig.add_subplot(grid[2, 4]), "정본 출력 요약 / Canonical output summary", output_lines, font)

    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[3, column], projection="3d")
        PANEL_V4.plot_cityjson(ax, evidence, frame, helper_config, alpha=0.38)
        PANEL_V4.plot_reference(ax, evidence, frame, helper_config)
        PANEL_V4.configure_3d_axis(ax, frame, camera)
        PANEL_V4.short_title(
            ax,
            f"출력+참조 · {camera['title_ko']} (평가 전용)",
            f"Output + reference · {camera['title_en']} (evaluation only)",
            font,
            fontsize=8.0,
        )
    comparison_lines = [
        "filled blue/grey/brown: canonical Roofer output",
        "orange dashed rings: reference GML (evaluation only)",
        "reference opened after sample and output binding",
        "reference never selects the view orientation",
        "reference affects shared comparison bounds only",
        "projection: orthographic | Z exaggeration: 1.0×",
        "",
        f"exact XY coordinate set equal: {comparison['exact_XY_coordinate_set_equal']}",
        f"exact XYZ coordinate set equal: {comparison['exact_XYZ_coordinate_set_equal']}",
        f"unique XY output/ref: {comparison['output_unique_xy_n']} / {comparison['reference_unique_xy_n']}",
        f"unique XYZ output/ref: {comparison['output_unique_xyz_n']} / {comparison['reference_unique_xyz_n']}",
        f"output Z: {comparison['output_z_min_m']:.3f}–{comparison['output_z_max_m']:.3f} m",
        f"reference Z: {comparison['reference_z_min_m']:.3f}–{comparison['reference_z_max_m']:.3f} m",
        "CRS: EPSG:25832",
        "NO GS TRAINING | learning_runs=0",
        "scientific_verdict: null",
    ]
    text_panel(fig.add_subplot(grid[3, 4]), "중첩·카메라 요약 / Overlay and camera receipt", comparison_lines, font)

    fig.text(
        0.5,
        0.022,
        "P0 raw dense DIM/MVS -> Roofer · reference GML is evaluation only · no interpretation · scientific_verdict: null",
        ha="center",
        va="center",
        fontsize=7.6,
        color="#252a31",
        fontproperties=font,
    )
    panel_directory = staging / config["outputs"]["panel_directory"]
    panel_directory.mkdir(parents=True, exist_ok=True)
    panel_name = config["outputs"]["panel_template"].format(building_id=building_id)
    panel_path = panel_directory / panel_name
    require(not panel_path.exists(), f"panel overwrite refused: {panel_path}")
    fig.savefig(
        panel_path,
        dpi=int(visual["panel_dpi"]),
        facecolor="white",
        metadata={"Software": "JointBuildGS P0 dense baseline qualitative v2"},
    )
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)
    with Image.open(panel_path) as rendered:
        width, height = rendered.size
    minimum = visual["minimum_panel_pixels"]
    require(width >= int(minimum[0]) and height >= int(minimum[1]), "panel resolution below contract")
    return {
        "building_id": building_id,
        "cell": {size_field: selection_row[size_field], obs_field: selection_row[obs_field]},
        "panel": bundle_record(staging, panel_path),
        "photo_receipts": photo_receipts,
        "dense_class6_points_n": len(points),
        "dense_class6_tin_boundary": dict(boundary.tin_stats),
        "dense_class6_points_displayed_per_geometry_view": displayed_points,
        "cityjson": dict(surface_stats),
        "comparison": comparison,
        "frame": frame,
        "render_pixels": [width, height],
        "mandatory_labels": list(MANDATORY_LABELS),
        "scientific_verdict": None,
        "interpretation": None,
    }


def write_csv_new(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    require(not path.exists(), f"output overwrite refused: {path}")
    require(bool(rows), f"cannot write empty CSV: {path}")
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json_new(path: Path, payload: Mapping[str, Any]) -> None:
    require(not path.exists(), f"output overwrite refused: {path}")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def selection_audit_payload(config: Mapping[str, Any], result: SelectionResult) -> dict[str, Any]:
    return {
        "schema": AUDIT_SCHEMA,
        "created_utc": utc_now(),
        "population": {
            "count": len(result.population_ids),
            "set_sha256": result.population_set_sha256,
            "formula": config["population_contract"]["formula"],
            "dual_source_exact_match": True,
        },
        "selection_contract": config["selection_contract"],
        "selected_buildings": [dict(row) for row in result.selected],
        "selected_building_ids": [row["building_id"] for row in result.selected],
        "selected_set_sha256": set_sha256(row["building_id"] for row in result.selected),
        "candidate_audit_row_count": len(result.audit_rows),
        "outcome_or_reference_fields_used_after_population_lock": [],
        "scientific_verdict": None,
        "interpretation": None,
    }


def render_overview(
    staging: Path,
    config: Mapping[str, Any],
    panel_receipts: Sequence[Mapping[str, Any]],
    font: font_manager.FontProperties,
) -> dict[str, Any]:
    visual = config["visual_contract"]
    fig, axes = plt.subplots(3, 3, figsize=tuple(visual["overview_inches"]))
    for ax, receipt in zip(axes.ravel(), panel_receipts):
        panel_path = staging / str(receipt["panel"]["path"])
        require(panel_path.is_file(), f"overview source panel absent: {panel_path}")
        with Image.open(panel_path) as source:
            preview = source.convert("RGB")
            preview.thumbnail((1600, 1100), Image.Resampling.LANCZOS)
            pixels = np.asarray(preview)
        ax.imshow(pixels)
        cell = receipt["cell"]
        ax.set_title(
            f"{receipt['building_id']} · size={cell['stratum_size_area']} × obs={cell['stratum_observation_recon_score']}",
            fontproperties=font,
            fontsize=9.0,
            color="#252a31",
        )
        ax.axis("off")
    fig.suptitle(
        "Canonical P0 raw dense DIM/MVS -> Roofer · 3×3 input-stratified overview\n"
        "NO GS TRAINING | learning_runs=0 | scientific_verdict: null",
        fontproperties=font,
        fontsize=16,
        color="#252a31",
    )
    fig.tight_layout(rect=(0.01, 0.01, 0.99, 0.94))
    path = staging / config["outputs"]["overview"]
    require(not path.exists(), "overview overwrite refused")
    fig.savefig(path, dpi=int(visual["overview_dpi"]), facecolor="white")
    plt.close(fig)
    return bundle_record(staging, path)


def fixed_source_snapshot(
    config: Mapping[str, Any], selected_image_paths: Sequence[Path], reference_paths: Sequence[Path]
) -> dict[str, dict[str, Any]]:
    paths: dict[str, Path] = {}
    for source in config["sources"].values():
        value = source.get("path")
        if isinstance(value, str):
            path = repo_path(value)
            if path.is_file():
                paths[rel(path)] = path
    for value in config["implementation_files"]:
        path = repo_path(value)
        paths[rel(path)] = path
    for path in [*selected_image_paths, *reference_paths]:
        paths[rel(path)] = path
    return {key: file_record(path) for key, path in sorted(paths.items())}


def output_records(staging: Path, manifest_name: str) -> list[dict[str, Any]]:
    records = []
    for path in sorted(candidate for candidate in staging.rglob("*") if candidate.is_file()):
        if path.name == manifest_name:
            continue
        record = file_record(path)
        record["path"] = str(path.relative_to(staging))
        records.append(record)
    return records


def verify_source_records(records: Any) -> int:
    """Rehash every provenance-bound repo file recorded by a bundle."""

    require(isinstance(records, list) and records, "manifest source ledger absent")
    seen: set[str] = set()
    for index, record in enumerate(records):
        require(isinstance(record, Mapping), f"source record {index} is not an object")
        logical = record.get("path")
        require(isinstance(logical, str) and logical, f"source record {index} path absent")
        require(logical not in seen, f"duplicate source record: {logical}")
        seen.add(logical)
        path = repo_path(logical)
        require(path.is_file(), f"published source absent: {logical}")
        require(path.stat().st_size == int(record["bytes"]), f"published source size drift: {logical}")
        require(sha256_file(path) == record["sha256"], f"published source hash drift: {logical}")
    return len(seen)


def publish(config: Mapping[str, Any], output_root: Path | None = None) -> dict[str, Any]:
    result = select_sample(config)
    root = repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    require(not root.exists(), f"output root exists; overwrite refused: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging.", dir=root.parent))
    try:
        font, font_record = load_font(config)
        selection_csv = staging / config["outputs"]["selection_audit_csv"]
        selection_json = staging / config["outputs"]["selection_audit_json"]
        write_csv_new(selection_csv, result.audit_rows)
        write_json_new(selection_json, selection_audit_payload(config, result))

        selected_ids = {str(row["building_id"]) for row in result.selected}
        footprints, footprint_record = load_locked_footprints(config, selected_ids)
        dense_source = E5.Source(
            source_group="raw_dense",
            source_run="raw_dense",
            display_label="raw dense (DIM/MVS)",
            status_role="baseline",
            status_path=None,
            status_input="DIM",
            cityjson_path=None,
            pointcloud_path=repo_path(config["sources"]["dense_classified_laz"]["path"]),
        )
        cloud_cache = E5.PointCloudCache(footprints)
        points_by_id = {
            building_id: cloud_cache.read_roof_points(dense_source, building_id)
            for building_id in sorted(selected_ids)
        }
        for building_id, points in points_by_id.items():
            require(len(points) > 0, f"selected building has no class-6 points: {building_id}")
            require(
                100000.0 <= float(np.median(points[:, 0])) <= 900000.0
                and 5_000_000.0 <= float(np.median(points[:, 1])) <= 6_200_000.0,
                f"{building_id} point coordinates are not EPSG:25832-like",
            )
        boundaries_by_id = {
            building_id: build_input_roof_boundary(config, points)
            for building_id, points in points_by_id.items()
        }

        cityjson_path = repo_path(config["sources"]["canonical_roofer_cityjson"]["path"])
        cityjson_payload = read_json(cityjson_path)
        output_by_id: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {
            building_id: load_cityjson_surfaces_for_building(cityjson_payload, building_id)
            for building_id in sorted(selected_ids)
        }
        # Evaluation-only reference is intentionally opened after sample and output binding.
        reference_directory = repo_path(config["sources"]["reference_gml_directory"]["path"])
        reference_surfaces = E5.parse_lod2_roofs(reference_directory, selected_ids)
        reference_rings_by_id = {
            building_id: E5.surface_polys_3d(reference_surfaces[building_id])
            for building_id in sorted(selected_ids)
        }
        reference_paths = sorted(reference_directory.glob("*.gml"))
        require(bool(reference_paths), "reference GML files absent")

        scene_reference = read_json(repo_path(config["sources"]["scene_reference_frame"]["path"]))
        projection_views_by_name = load_projection_views(config)
        image_directory = repo_path(config["sources"]["image_directory"]["path"])
        require(image_directory.is_dir(), "image directory absent")
        photo_views_by_id: dict[str, list[dict[str, Any]]] = {}
        selected_image_paths: list[Path] = []
        for row in result.selected:
            building_id = str(row["building_id"])
            views = select_geometry_photo_views(
                points_by_id[building_id],
                boundaries_by_id[building_id],
                projection_views_by_name,
                scene_reference,
                image_directory,
                config,
            )
            photo_views_by_id[building_id] = views
            for view in views:
                path = image_directory / str(view["name"])
                require(path.is_file(), f"geometry-selected image absent: {path.name}")
                selected_image_paths.append(path)

        sources_before = fixed_source_snapshot(config, selected_image_paths, reference_paths)
        status_rows = [
            row
            for row in read_csv(repo_path(config["sources"]["canonical_roofer_status"]["path"]))
            if row.get("input") == "DIM" and row.get("building_id") in selected_ids
        ]
        status_by_id = _unique_by(status_rows, "building_id", 9, "canonical DIM Roofer status sample")

        pdf_path = staging / config["outputs"]["multipage_pdf"]
        require(not pdf_path.exists(), "PDF overwrite refused")
        panel_receipts: list[dict[str, Any]] = []
        with PdfPages(
            pdf_path,
            metadata={
                "Title": "P0 raw dense DIM/MVS to Roofer qualitative review",
                "Subject": "NO GS TRAINING; learning_runs=0; scientific_verdict null",
                "Creator": "JointBuildGS",
            },
        ) as pdf:
            for row in result.selected:
                building_id = str(row["building_id"])
                surfaces, stats = output_by_id[building_id]
                panel_receipts.append(
                    render_building(
                        staging,
                        pdf,
                        config,
                        row,
                        points_by_id[building_id],
                        boundaries_by_id[building_id],
                        surfaces,
                        stats,
                        reference_rings_by_id[building_id],
                        status_by_id[building_id],
                        photo_views_by_id[building_id],
                        projection_views_by_name,
                        scene_reference,
                        font,
                    )
                )
        require(pdf_path.is_file() and pdf_path.stat().st_size > 0, "multipage PDF absent")
        overview_record = render_overview(staging, config, panel_receipts, font)
        sources_after = fixed_source_snapshot(config, selected_image_paths, reference_paths)
        require(sources_after == sources_before, "source inputs changed while rendering")

        outputs = output_records(staging, config["outputs"]["manifest"])
        output_set_hash = set_sha256(
            f"{record['path']}|{record['sha256']}|{record['bytes']}" for record in outputs
        )
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "created_utc": utc_now(),
            "state": "COMPLETE",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "branch": config["branch"],
            "population": {
                "count": len(result.population_ids),
                "set_sha256": result.population_set_sha256,
                "inventory_regression_exact_match": True,
                "display_name": config["population_contract"]["display_name"],
                "success_definition": config["population_contract"]["success_definition"],
            },
            "selection": {
                "sample_count": len(result.selected),
                "selected_building_ids": [row["building_id"] for row in result.selected],
                "selected_set_sha256": set_sha256(row["building_id"] for row in result.selected),
                "cells": [
                    {
                        "stratum_size_area": row["stratum_size_area"],
                        "stratum_observation_recon_score": row["stratum_observation_recon_score"],
                        "building_id": row["building_id"],
                    }
                    for row in result.selected
                ],
                "outcome_or_reference_fields_used": [],
                "reference_open_stage": "after_sample_selection_and_canonical_output_binding",
            },
            "render_contract": {
                "layout": "4_rows_x_5_columns",
                "individual_panel_count": len(panel_receipts),
                "single_multipage_pdf": True,
                "overview": overview_record,
                "camera_projection": "orthographic",
                "z_exaggeration": 1.0,
                "reference_view_orientation_influence": False,
                "mandatory_labels": list(MANDATORY_LABELS),
                "photo_projection": config["photo_projection_contract"],
            },
            "panel_receipts": panel_receipts,
            "source_records": list(sources_before.values()),
            "footprint_GeoPackage_record": footprint_record,
            "font": font_record,
            "outputs": outputs,
            "output_set_sha256": output_set_hash,
            "reference_role": "evaluation_only",
            "learning_runs_started": 0,
            "new_training_runs": 0,
            "scientific_verdict": None,
            "interpretation": None,
        }
        write_json_new(staging / config["outputs"]["manifest"], manifest)
        require(not root.exists(), "output appeared before atomic publication")
        os.replace(staging, root)
        return manifest
    except Exception:
        if staging.exists() and staging.parent == root.parent and staging.name.startswith(f".{root.name}.staging."):
            shutil.rmtree(staging)
        raise


def verify_bundle(config: Mapping[str, Any], output_root: Path | None = None) -> dict[str, Any]:
    root = repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    require(root.is_dir(), f"output bundle absent: {root}")
    manifest_path = root / config["outputs"]["manifest"]
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == MANIFEST_SCHEMA, "manifest schema drift")
    require(manifest.get("state") == "COMPLETE", "manifest is not COMPLETE")
    require(manifest.get("scientific_verdict") is None, "manifest contains a verdict")
    require(manifest.get("interpretation") is None, "manifest contains interpretation")
    require(manifest.get("learning_runs_started") == 0, "manifest learning count drift")
    require(manifest.get("population", {}).get("set_sha256") == EXPECTED_DENSE_SET_SHA256, "manifest population drift")
    source_records_n = verify_source_records(manifest.get("source_records"))
    records = manifest.get("outputs") or []
    require(isinstance(records, list) and records, "manifest output ledger absent")
    for record in records:
        path = root / str(record["path"])
        require(path.is_file(), f"published output absent: {record['path']}")
        require(path.stat().st_size == int(record["bytes"]), f"published size drift: {record['path']}")
        require(sha256_file(path) == record["sha256"], f"published hash drift: {record['path']}")
    observed_set_hash = set_sha256(
        f"{record['path']}|{record['sha256']}|{record['bytes']}" for record in records
    )
    require(observed_set_hash == manifest.get("output_set_sha256"), "output set hash drift")
    panels = sorted((root / config["outputs"]["panel_directory"]).glob("*.png"))
    require(len(panels) == 9, "published panel count drift")
    require((root / config["outputs"]["multipage_pdf"]).is_file(), "multipage PDF absent")
    require((root / config["outputs"]["overview"]).is_file(), "overview absent")
    require((root / config["outputs"]["selection_audit_csv"]).is_file(), "selection audit CSV absent")
    require((root / config["outputs"]["selection_audit_json"]).is_file(), "selection audit JSON absent")
    return {
        "state": "VERIFIED",
        "root": str(root),
        "panels": len(panels),
        "outputs": len(records),
        "source_records": source_records_n,
        "selected_building_ids": manifest["selection"]["selected_building_ids"],
        "scientific_verdict": None,
    }


def check(config: Mapping[str, Any]) -> dict[str, Any]:
    result = select_sample(config)
    selected_ids = [str(row["building_id"]) for row in result.selected]
    footprints, _footprint_record = load_locked_footprints(config, selected_ids)
    dense_source = E5.Source(
        source_group="raw_dense",
        source_run="raw_dense",
        display_label="raw dense (DIM/MVS)",
        status_role="baseline",
        status_path=None,
        status_input="DIM",
        cityjson_path=None,
        pointcloud_path=repo_path(config["sources"]["dense_classified_laz"]["path"]),
    )
    cloud_cache = E5.PointCloudCache(footprints)
    points_by_id = {
        building_id: cloud_cache.read_roof_points(dense_source, building_id)
        for building_id in selected_ids
    }
    boundaries_by_id = {
        building_id: build_input_roof_boundary(config, points)
        for building_id, points in points_by_id.items()
    }
    image_directory = repo_path(config["sources"]["image_directory"]["path"])
    require(image_directory.is_dir(), "image directory absent")
    scene_reference = read_json(repo_path(config["sources"]["scene_reference_frame"]["path"]))
    projection_views_by_name = load_projection_views(config)
    photo_views = {
        building_id: select_geometry_photo_views(
            points_by_id[building_id],
            boundaries_by_id[building_id],
            projection_views_by_name,
            scene_reference,
            image_directory,
            config,
        )
        for building_id in selected_ids
    }
    return {
        "state": "CHECKED_READ_ONLY",
        "population_count": len(result.population_ids),
        "population_set_sha256": result.population_set_sha256,
        "selected_building_ids": selected_ids,
        "cells": [
            [row["stratum_size_area"], row["stratum_observation_recon_score"]]
            for row in result.selected
        ],
        "photo_binding": {
            "stage": "after_sample_selection_and_class6_clipping",
            "method": "adopted_pose_explicit_datum_actual_class6_TIN_boundary_nadir_then_azimuth_diversity",
            "image_pixels_used_for_ranking": False,
            "flat_single_Z_footprint_used": False,
            "independent_RGB_alignment_gate": "not_run_projection_source_audit_only",
            "views": {
                building_id: [str(view["name"]) for view in views]
                for building_id, views in photo_views.items()
            },
        },
        "learning_runs_started": 0,
        "scientific_verdict": None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate inputs and print the deterministic sample; write nothing")
    subparsers.add_parser("render", help="atomically publish the complete nine-panel bundle")
    subparsers.add_parser("verify", help="verify a previously published bundle; write nothing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config.resolve())
    if args.command == "check":
        payload = check(config)
    elif args.command == "render":
        payload = publish(config, args.output_root)
    else:
        payload = verify_bundle(config, args.output_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
