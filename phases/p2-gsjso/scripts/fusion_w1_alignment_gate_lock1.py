#!/usr/bin/env python3
"""FUS-W1 Gate A lock1: raw ALS-to-training-image alignment, fail closed.

This is the result-blind implementation of dispatch-v3 section 2.  It:

* reads only the approved LoD2 GroundSurface **XY** footprint exception and
  raw ALS classes 2/6 (never LoD2 Z, RoofSurface, roof type, semantics, or a
  final roof model);
* restricts views to the exact COLMAP-pose/training-image intersection and
  measures every selected 10..30 view;
* reports direct point-to-edge distances from z-buffer-visible class-6
  roof/eave boundary points to subpixel image structural edges in pixels and
  pointwise-Jacobian EPSG:25832 XY metres;
* applies the locked 0.30 m per-building median criterion and the separately
  locked 0.10 m systematic-translation criterion with a building-cluster
  bootstrap confidence interval;
* if the raw gate fails, performs at most one global translation-only XY
  micro-registration fitted from deterministic fit views, remeasures every
  selected view, and evaluates the systematic offset only on held-out views.

The script does not train, reconstruct, read out, score CityGML, or make the
human research judgment.  A non-passing numeric gate exits with status 2 so a
driver cannot enter learning accidentally.
"""
from __future__ import annotations

import argparse
from collections import deque
import copy
import csv
import fcntl
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from projection_datum import (  # noqa: E402
    base_to_canonical_points,
    describe_projection_config,
    load_projection_config,
    projection_geoid_m,
)
from src.stage2.colmap_io import (  # noqa: E402
    Camera,
    Image as ColmapImage,
    read_cameras_bin,
    read_images_bin,
)
from fusion_w1_alignment_checkpoint import (  # noqa: E402
    AlignmentCheckpointStore,
    CheckpointIdentity,
    CheckpointRef,
    canonical_hash_manifest,
)
from fusion_w1_alignment_runtime_guard_lock1 import (  # noqa: E402
    RuntimeGuardError,
    find_named_record,
    revalidate_before_publish,
)


DEFAULT_CONFIG = (
    REPO_ROOT / "phases/p2-gsjso/configs/fusion_w1_alignment_gate_lock1.json"
)
LOCKED_BUILDING_MEDIAN_M = 0.30
LOCKED_SYSTEMATIC_NORM_M = 0.10
RAW_ATTEMPT = "raw"
MICRO_ATTEMPT = "micro1"
CSV_TRUE = "true"
CSV_FALSE = "false"


class GateContractError(RuntimeError):
    """Input, provenance, or locked-protocol contract failure."""


@dataclass(frozen=True)
class Target:
    building_id: str
    processing_order: int
    cohort: str
    tier: str
    queue_status: str = ""
    cohort_resolution_status: str = ""


@dataclass
class TargetCloud:
    building_id: str
    footprint_xy: np.ndarray
    building_xyz: np.ndarray
    ground_xyz: np.ndarray
    source_tiles: tuple[str, ...]

    @property
    def target_xyz(self) -> np.ndarray:
        return np.median(self.building_xyz, axis=0)


@dataclass(frozen=True)
class SelectedView:
    building_id: str
    order: int
    name: str
    image_id: int
    camera_id: int
    selection_source: str
    n_building_inframe_at_selection: int
    frame_radius: float
    view_nadir_deg: float
    observability_p90_m_per_px: float = float("nan")
    predicted_metric_uncertainty_m: float = float("nan")
    azimuth_bin: int = -1
    registration_split: str = ""


@dataclass(frozen=True)
class VisibleBoundary:
    """Projected target boundary with its originating ALS coordinates."""

    xyz: np.ndarray
    source_index: np.ndarray
    uv: np.ndarray
    normal_uv: np.ndarray
    outward_xy: np.ndarray
    camera_depth: np.ndarray
    source_count: int
    visible_fraction: float


@dataclass
class _ALSTile:
    path: Path
    bounds: tuple[float, float, float, float]
    x: np.ndarray | None = None
    y: np.ndarray | None = None
    z: np.ndarray | None = None
    classification: np.ndarray | None = None

    def load(self, ground_class: int, building_class: int) -> None:
        if self.x is not None:
            return
        try:
            import laspy
        except ImportError as exc:  # pragma: no cover - environment contract
            raise GateContractError("laspy is required in the pinned tools image") from exc
        las = laspy.read(self.path)
        cls = np.asarray(las.classification, dtype=np.uint8)
        keep = (cls == ground_class) | (cls == building_class)
        if not np.any(keep):
            raise GateContractError(
                f"ALS tile has no locked classes {ground_class}/{building_class}: "
                f"{self.path}"
            )
        x = np.asarray(las.x, dtype=np.float64)[keep]
        y = np.asarray(las.y, dtype=np.float64)[keep]
        z = np.asarray(las.z, dtype=np.float64)[keep]
        cls = cls[keep]
        order = np.argsort(x, kind="mergesort")
        self.x = x[order]
        self.y = y[order]
        self.z = z[order]
        self.classification = cls[order]

    def query(
        self,
        bbox: Sequence[float],
        ground_class: int,
        building_class: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        self.load(ground_class, building_class)
        assert self.x is not None
        assert self.y is not None
        assert self.z is not None
        assert self.classification is not None
        xmin, ymin, xmax, ymax = map(float, bbox)
        lo = int(np.searchsorted(self.x, xmin, side="left"))
        hi = int(np.searchsorted(self.x, xmax, side="right"))
        y = self.y[lo:hi]
        keep = (y >= ymin) & (y <= ymax)
        xyz = np.column_stack(
            [self.x[lo:hi][keep], y[keep], self.z[lo:hi][keep]]
        )
        return xyz, self.classification[lo:hi][keep]


class ALSStore:
    """Lazy, x-sorted access to the four canonical raw ALS tiles."""

    def __init__(
        self,
        paths: Sequence[Path],
        ground_class: int,
        building_class: int,
    ) -> None:
        try:
            import laspy
        except ImportError as exc:  # pragma: no cover - environment contract
            raise GateContractError("laspy is required in the pinned tools image") from exc
        self.ground_class = int(ground_class)
        self.building_class = int(building_class)
        self.tiles: list[_ALSTile] = []
        for path in paths:
            with laspy.open(path) as handle:
                mins = handle.header.mins
                maxs = handle.header.maxs
                bounds = (
                    float(mins[0]),
                    float(mins[1]),
                    float(maxs[0]),
                    float(maxs[1]),
                )
            self.tiles.append(_ALSTile(path=path, bounds=bounds))

    @staticmethod
    def _intersects(a: Sequence[float], b: Sequence[float]) -> bool:
        return not (
            float(a[2]) < float(b[0])
            or float(a[0]) > float(b[2])
            or float(a[3]) < float(b[1])
            or float(a[1]) > float(b[3])
        )

    def target_cloud(
        self,
        building_id: str,
        footprint_xy: np.ndarray,
        evidence_cfg: Mapping[str, Any],
    ) -> TargetCloud:
        ring = np.asarray(footprint_xy, dtype=np.float64)
        if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 4:
            raise GateContractError(f"invalid 2D footprint for {building_id}")
        building_buffer = float(evidence_cfg["footprint_building_buffer_m"])
        if not math.isclose(building_buffer, 0.0, abs_tol=1e-12):
            raise GateContractError(
                "Gate A class-6 evidence must use a strict footprint crop"
            )
        ground_buffer = float(evidence_cfg["ground_context_buffer_m"])
        bbox = (
            float(np.min(ring[:, 0]) - ground_buffer),
            float(np.min(ring[:, 1]) - ground_buffer),
            float(np.max(ring[:, 0]) + ground_buffer),
            float(np.max(ring[:, 1]) + ground_buffer),
        )
        building_chunks: list[np.ndarray] = []
        ground_chunks: list[np.ndarray] = []
        sources: list[str] = []
        path = MplPath(ring, closed=True)
        for tile in self.tiles:
            if not self._intersects(tile.bounds, bbox):
                continue
            xyz, cls = tile.query(
                bbox, self.ground_class, self.building_class
            )
            if len(xyz) == 0:
                continue
            sources.append(repo_relative(tile.path))
            is_building = cls == self.building_class
            if np.any(is_building):
                points = xyz[is_building]
                inside = path.contains_points(points[:, :2], radius=0.0)
                if np.any(inside):
                    building_chunks.append(points[inside])
            is_ground = cls == self.ground_class
            if np.any(is_ground):
                ground_chunks.append(xyz[is_ground])
        building = (
            np.vstack(building_chunks)
            if building_chunks
            else np.zeros((0, 3), dtype=np.float64)
        )
        ground = (
            np.vstack(ground_chunks)
            if ground_chunks
            else np.zeros((0, 3), dtype=np.float64)
        )
        min_building = int(evidence_cfg["minimum_building_class_points"])
        min_ground = int(evidence_cfg["minimum_ground_class_points"])
        if len(building) < min_building:
            raise GateContractError(
                f"{building_id}: ALS class {self.building_class} points "
                f"{len(building)} < {min_building}"
            )
        if len(ground) < min_ground:
            raise GateContractError(
                f"{building_id}: ALS class {self.ground_class} points "
                f"{len(ground)} < {min_ground}"
            )
        return TargetCloud(
            building_id=building_id,
            footprint_xy=ring,
            building_xyz=building,
            ground_xyz=ground,
            source_tiles=tuple(sorted(set(sources))),
        )


def repo_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalized_field(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in str(name)).strip(
        "_"
    )


def canonical_building_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise GateContractError("empty building_id")
    return text if text.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{text}"


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise GateContractError(
            "FUS-W1 Gate A must run inside the pinned Docker tools image"
        )


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "jointbuildgs.fusion_w1.alignment_gate_config.v1":
        raise GateContractError("unexpected Gate A config schema")
    if payload.get("implementation_variant") != "lock1":
        raise GateContractError("Gate A must use the isolated lock1 implementation")
    gate = payload.get("gate", {})
    if not math.isclose(
        float(gate.get("building_median_residual_max_m", math.nan)),
        LOCKED_BUILDING_MEDIAN_M,
        abs_tol=1e-12,
    ):
        raise GateContractError("building gate must remain locked at 0.30 m")
    if not math.isclose(
        float(gate.get("systematic_xy_norm_max_m", math.nan)),
        LOCKED_SYSTEMATIC_NORM_M,
        abs_tol=1e-12,
    ):
        raise GateContractError("systematic gate must remain locked at 0.10 m")
    if not math.isclose(
        float(gate.get("systematic_bootstrap_ci_upper_max_m", math.nan)),
        LOCKED_SYSTEMATIC_NORM_M,
        abs_tol=1e-12,
    ):
        raise GateContractError(
            "systematic bootstrap upper bound must remain locked at 0.10 m"
        )
    micro = payload.get("micro_registration", {})
    if int(micro.get("maximum_attempts", -1)) != 1:
        raise GateContractError("exactly one micro-registration attempt is allowed")
    if not bool(micro.get("second_attempt_forbidden")):
        raise GateContractError("second micro-registration must be forbidden")
    if "global shared" not in str(micro.get("method", "")):
        raise GateContractError("micro-registration must be one global shared shift")
    if not bool(micro.get("same_view_per_building_fit_recheck_forbidden")):
        raise GateContractError("same-view per-building micro-fit/recheck is forbidden")
    if micro.get("post_registration_systematic_evaluation_split") != "heldout":
        raise GateContractError("post-registration systematic gate must be held-out")
    alignment = payload.get("alignment", {})
    if not bool(alignment.get("translation_argmax_norm_as_metric_forbidden")):
        raise GateContractError("translation argmax norm must be forbidden as a metric")
    if "absolute signed-normal distances" not in str(
        alignment.get("metric_method", "")
    ):
        raise GateContractError("Gate A metric must be direct point-to-edge distance")
    if "||n^T J_xy||_2" not in str(alignment.get("metre_conversion", "")):
        raise GateContractError(
            "metre conversion must use the pointwise normal-Jacobian row norm"
        )
    selection = payload.get("view_selection", {})
    required_selection = {
        "minimum_views_per_building",
        "maximum_views_per_building",
        "minimum_als_building_points_in_frame",
        "selection_projection_point_cap",
        "selection_boundary_point_cap",
        "selection_edge_localization_sigma_px",
        "predicted_uncertainty_reference_m",
        "azimuth_bin_count",
        "minimum_selected_azimuth_bins",
        "ranking",
    }
    missing_selection = sorted(required_selection - set(selection))
    if missing_selection:
        raise GateContractError(
            "view-selection lock is incomplete: " + ",".join(missing_selection)
        )
    if not math.isclose(
        float(selection["selection_edge_localization_sigma_px"]),
        0.1,
        abs_tol=1e-12,
    ) or not math.isclose(
        float(selection["predicted_uncertainty_reference_m"]),
        0.3,
        abs_tol=1e-12,
    ):
        raise GateContractError(
            "view selection uncertainty locks must remain 0.1 px and 0.30 m"
        )
    if (
        int(selection["azimuth_bin_count"]) != 8
        or int(selection["minimum_selected_azimuth_bins"]) != 1
        or "observability-first" not in str(selection["ranking"])
    ):
        raise GateContractError(
            "view selection must remain observability-first with an 8-bin "
            "diagnostic round-robin and no unregistered coverage gate"
        )
    confidence = payload.get("confidence", {})
    required_confidence = {
        "maximum_edge_localization_uncertainty_p90_m",
        "translation_diagnostic_search_radius_px",
        "translation_diagnostic_coarse_step_px",
        "translation_diagnostic_fine_radius_px",
        "translation_diagnostic_top_seed_count",
        "translation_diagnostic_minimum_boundary_support_fraction",
        "translation_diagnostic_minimum_hypothesis_separation_px",
        "translation_diagnostic_minimum_relative_margin",
    }
    missing_confidence = sorted(required_confidence - set(confidence))
    if missing_confidence:
        raise GateContractError(
            "confidence lock is incomplete: " + ",".join(missing_confidence)
        )
    if not math.isclose(
        float(confidence["maximum_edge_localization_uncertainty_p90_m"]),
        0.3,
        abs_tol=1e-12,
    ) or not math.isclose(
        float(alignment.get("minimum_reverse_match_fraction", math.nan)),
        0.5,
        abs_tol=1e-12,
    ):
        raise GateContractError(
            "measured localization and reverse-support locks drifted"
        )
    boundary = payload.get("boundary_extraction", {})
    if not bool(boundary.get("radial_star_silhouette_forbidden")):
        raise GateContractError("radial-star silhouettes must be forbidden")
    if (
        "footprint perimeter coordinates and directions are forbidden"
        not in str(boundary.get("footprint_role", ""))
        or "exposed direction"
        not in str(boundary.get("method", ""))
    ):
        raise GateContractError(
            "ALS occupancy must be the sole boundary-direction source"
        )
    if not bool(payload.get("edge_extraction", {}).get("result_blind")):
        raise GateContractError("image edge extraction must be result-blind")
    time_policy = payload.get("time_policy", {})
    if bool(time_policy.get("stop_at_0630")):
        raise GateContractError("06:30 is a snapshot, not a Gate A stop condition")
    footprint_contract = payload.get("input_locks", {}).get(
        "footprint_contract", {}
    )
    if (
        footprint_contract.get("source_kind")
        != "lod2_groundsurface_xy_scoped_exception"
        or footprint_contract.get("gt_derived") is not True
        or footprint_contract.get("approved_components_used")
        != ["GroundSurface XY"]
    ):
        raise GateContractError("approved GroundSurface XY exception is not explicit")
    return payload


def activate_coreg_gate_lock2(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Activate the preregistered corrected-camera Gate without a new config."""

    section = config.get("coreg_gate_lock2")
    if not isinstance(section, Mapping) or section.get("enabled") is not True:
        raise GateContractError("corrected-camera Gate lock2 is not enabled")
    if int(section.get("maximum_post_coreg_xy_micro_registration_attempts", -1)) != 0:
        raise GateContractError(
            "corrected-camera Gate must forbid every additional XY micro-registration"
        )
    activated = copy.deepcopy(dict(config))
    activated["task_id"] = str(section["task_id"])
    activated["inputs"]["colmap_sparse_dir"] = str(
        section["derived_colmap_sparse_dir"]
    )
    activated["outputs"].update(dict(section["output_overrides"]))
    activated["publication"].update(dict(section["publication_overrides"]))
    activated["micro_registration"]["maximum_attempts"] = 0
    activated["micro_registration"]["method"] = (
        "forbidden after the single preregistered ALS-fixed camera "
        "co-registration composite procedure"
    )
    activated["micro_registration"][
        "all_post_coreg_xy_micro_registration_forbidden"
    ] = True
    activated["_active_coreg_gate_lock2"] = dict(section)
    return activated


def validate_pose_publication_contract(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind lock2 to the exact passed coreg receipt and derived COLMAP model."""

    section = config.get("_active_coreg_gate_lock2")
    if not isinstance(section, Mapping):
        raise GateContractError("corrected-camera Gate mode is not active")
    manifest_path = repo_path(str(section["pose_publication_manifest"]))
    coreg_runtime = repo_path(str(section["coreg_runtime_dir"]))
    coreg_config_path = repo_path(str(section["coreg_config"]))
    derived_sparse = repo_path(str(section["derived_colmap_sparse_dir"]))
    if derived_sparse.resolve() != repo_path(
        config["inputs"]["colmap_sparse_dir"]
    ).resolve():
        raise GateContractError("lock2 sparse directory differs from its pose contract")
    if not manifest_path.is_file():
        raise GateContractError("passed coreg pose publication manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema")
        != "jointbuildgs.fusion_w1.coreg_pose_publication.v1"
        or manifest.get("status") != "PASSED"
        or manifest.get("learning_allowed") is not False
        or manifest.get("als_source_modified") is not False
    ):
        raise GateContractError("coreg pose publication status/invariants are invalid")
    if manifest.get("derived_sparse") != repo_relative(derived_sparse):
        raise GateContractError("coreg manifest names a different derived sparse model")

    stage_binding = manifest.get("stage_binding")
    if not isinstance(stage_binding, Mapping):
        raise GateContractError("coreg pose manifest lacks immutable stage binding")
    head = _run_text(["git", "rev-parse", "HEAD"]).stdout.strip()
    branch = _run_text(["git", "branch", "--show-current"]).stdout.strip()
    if stage_binding.get("head") != head or stage_binding.get("branch") != branch:
        raise GateContractError(
            "coreg measurement HEAD/branch differs from corrected-camera Gate HEAD"
        )
    if stage_binding.get("config_sha256") != sha256_file(coreg_config_path):
        raise GateContractError("coreg stage binding config SHA-256 mismatch")

    check_path = coreg_runtime / "independent_check.json"
    frozen_path = coreg_runtime / "frozen_transform.json"
    check_open_path = coreg_runtime / "check_open.json"
    open_path = coreg_runtime / "publish_poses_open.json"
    if (
        not check_path.is_file()
        or not frozen_path.is_file()
        or not check_open_path.is_file()
        or not open_path.is_file()
    ):
        raise GateContractError("coreg check/frozen/stage-open receipt chain is incomplete")
    check = json.loads(check_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    check_opened = json.loads(check_open_path.read_text(encoding="utf-8"))
    opened = json.loads(open_path.read_text(encoding="utf-8"))
    if (
        check.get("status") != "PASSED"
        or check.get("stage_binding") != stage_binding
        or frozen.get("stage_binding") != stage_binding
        or check_opened.get("stage_binding") != stage_binding
        or opened.get("stage_binding") != stage_binding
    ):
        raise GateContractError("coreg check/frozen/publish stages do not share a binding")
    if (
        check.get("stage_open_receipt_sha256") != sha256_file(check_open_path)
        or (check_opened.get("parent_receipt_sha256") or {}).get(
            "frozen_transform"
        )
        != sha256_file(frozen_path)
    ):
        raise GateContractError("coreg independent-check stage-open chain mismatch")
    if manifest.get("independent_check_sha256") != sha256_file(check_path):
        raise GateContractError("coreg independent-check receipt hash mismatch")
    if manifest.get("stage_open_receipt_sha256") != sha256_file(open_path):
        raise GateContractError("coreg pose stage-open receipt hash mismatch")
    parents = opened.get("parent_receipt_sha256") or {}
    if (
        parents.get("independent_check") != sha256_file(check_path)
        or parents.get("frozen_transform") != sha256_file(frozen_path)
    ):
        raise GateContractError("coreg pose stage-open parent chain mismatch")
    if (
        manifest.get("selected_transform_sha256")
        != check.get("selected_transform_sha256")
        or manifest.get("selected_transform_sha256")
        != frozen.get("selected_transform_sha256")
    ):
        raise GateContractError("coreg selected transform hash chain mismatch")

    observed_derived: dict[str, str] = {}
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        path = derived_sparse / name
        if not path.is_file():
            raise GateContractError(f"coreg derived sparse file is missing: {name}")
        observed_derived[name] = sha256_file(path)
        if observed_derived[name] != manifest.get("derived_sha256", {}).get(name):
            raise GateContractError(f"coreg derived sparse SHA-256 mismatch: {name}")
    if int(manifest.get("image_count", -1)) != int(
        config["input_locks"]["expected_training_pose_image_intersection"]
    ):
        raise GateContractError("coreg pose publication does not cover all 937 images")
    arm_contract = manifest.get("arm_pose_contract") or {}
    if (
        arm_contract.get("identical") is not True
        or arm_contract.get("arm_A_required_pose_sha256")
        != observed_derived["images.bin"]
        or arm_contract.get("arm_B_required_pose_sha256")
        != observed_derived["images.bin"]
    ):
        raise GateContractError("arm A/B corrected-camera pose contract is not identical")

    coreg_config = json.loads(coreg_config_path.read_text(encoding="utf-8"))
    als_relative = str(coreg_config["inputs"]["als_aoi_laz"])
    als_sha = sha256_file(repo_path(als_relative))
    expected_als = coreg_config["input_locks"]["expected_sha256"][als_relative]
    if (
        als_sha != expected_als
        or manifest.get("als_source_sha256_after") != expected_als
        or stage_binding.get("source_als_sha256") != expected_als
    ):
        raise GateContractError("ALS changed across coreg and corrected-camera Gate")

    return {
        "status": "PASSED",
        "mode": "coreg_gate_lock2",
        "pose_publication_manifest": repo_relative(manifest_path),
        "pose_publication_manifest_sha256": sha256_file(manifest_path),
        "coreg_measurement_head": head,
        "selected_transform_sha256": manifest["selected_transform_sha256"],
        "choice": manifest["choice"],
        "derived_sparse": repo_relative(derived_sparse),
        "derived_sha256": observed_derived,
        "image_count": manifest["image_count"],
        "als_source_sha256_unchanged": expected_als,
        "post_coreg_xy_micro_registration_attempts_allowed": 0,
        "sparse_points3d_usable_for_learning": manifest[
            "sparse_points3d_usable_for_learning"
        ],
    }


def validate_source_hashes(config: Mapping[str, Any]) -> dict[str, str]:
    expected = config["input_locks"].get("expected_sha256", {})
    actual: dict[str, str] = {}
    for relative, wanted in expected.items():
        path = repo_path(relative)
        if not path.is_file():
            raise GateContractError(f"locked input missing: {relative}")
        got = sha256_file(path)
        actual[relative] = got
        if got != wanted:
            raise GateContractError(
                f"locked input SHA256 mismatch: {relative}: {got} != {wanted}"
            )
    datum_path = repo_path(config["inputs"]["projection_datum_config"])
    wanted_datum = config["input_locks"]["projection_datum_config_sha256"]
    got_datum = sha256_file(datum_path)
    actual[repo_relative(datum_path)] = got_datum
    if got_datum != wanted_datum:
        raise GateContractError(
            f"projection datum config SHA256 mismatch: {got_datum} != {wanted_datum}"
        )
    return actual


def _run_text(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def validate_implementation_provenance(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail before measurement unless the complete implementation is at HEAD."""

    branch = _run_text(["git", "branch", "--show-current"]).stdout.strip()
    expected_branch = str(config["git_lock"]["expected_branch"])
    if branch != expected_branch:
        raise GateContractError(f"branch drift: {branch!r} != {expected_branch!r}")
    head = _run_text(["git", "rev-parse", "HEAD"]).stdout.strip()
    for ancestor in config["git_lock"]["required_ancestor_commits"]:
        check = _run_text(
            ["git", "merge-base", "--is-ancestor", str(ancestor), head],
            check=False,
        )
        if check.returncode != 0:
            raise GateContractError(
                f"required Gate A lineage is absent from HEAD: {ancestor}"
            )
    tracked_dirty = _run_text(
        ["git", "status", "--porcelain", "--untracked-files=no"]
    ).stdout.splitlines()
    if tracked_dirty:
        raise GateContractError(
            "tracked worktree/index must be clean before Gate A: "
            + "; ".join(tracked_dirty[:8])
        )
    files: list[dict[str, Any]] = []
    for relative in config["git_lock"]["implementation_files"]:
        path = repo_path(relative)
        if not path.is_file():
            raise GateContractError(f"implementation file missing: {relative}")
        blob = _run_text(
            ["git", "show", f"HEAD:{relative}"], check=False
        )
        if blob.returncode != 0:
            raise GateContractError(
                f"implementation file is not a committed HEAD blob: {relative}"
            )
        working_bytes = path.read_bytes()
        # git show in text mode is not byte-safe; hash the exact blob through git.
        blob_sha = _run_text(
            ["git", "rev-parse", f"HEAD:{relative}"]
        ).stdout.strip()
        working_git_sha = _run_text(
            ["git", "hash-object", str(path)]
        ).stdout.strip()
        if working_git_sha != blob_sha:
            raise GateContractError(
                f"working implementation differs from HEAD: {relative}"
            )
        files.append(
            {
                "path": relative,
                "git_blob": blob_sha,
                "sha256": hashlib.sha256(working_bytes).hexdigest(),
                "working_and_head_match": True,
            }
        )
    return {
        "branch": branch,
        "head": head,
        "tracked_worktree_changes": [],
        "all_working_and_head_match": True,
        "files": files,
    }


def validate_baseline_preflight(guard_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the immutable, committed 5/5 PASSED receipt without freshness."""

    receipt_path = repo_path(guard_cfg["immutable_baseline_receipt"])
    status_path = repo_path(guard_cfg["immutable_baseline_status"])
    expected = {
        receipt_path: str(guard_cfg["immutable_baseline_receipt_sha256"]),
        status_path: str(guard_cfg["immutable_baseline_status_sha256"]),
    }
    for path, wanted in expected.items():
        if not path.is_file():
            raise GateContractError(f"immutable preflight artifact missing: {path}")
        got = sha256_file(path)
        if got != wanted:
            raise GateContractError(
                f"immutable preflight SHA256 mismatch: {repo_relative(path)}"
            )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if receipt.get("overall_status") != guard_cfg["baseline_required_overall_status"]:
        raise GateContractError("immutable preflight receipt is not PASSED")
    if status.get("status") != guard_cfg["baseline_status_required_status"]:
        raise GateContractError("immutable preflight status is not PASSED")
    if status.get("five_pin_total_count") != 5 or status.get(
        "five_pin_passed_or_caveated_count"
    ) != 5:
        raise GateContractError("immutable preflight does not prove 5/5 pins")
    if bool(guard_cfg["baseline_require_continuation_authorized"]) and not bool(
        status.get("continuation_authorized")
    ):
        raise GateContractError("immutable preflight lacks continuation authorization")
    provenance = status.get("implementation_provenance") or {}
    if bool(
        guard_cfg["baseline_require_implementation_all_working_and_head_match"]
    ) and not bool(provenance.get("all_working_and_head_match")):
        raise GateContractError("immutable preflight implementation lock did not pass")
    return {
        "receipt": repo_relative(receipt_path),
        "receipt_sha256": expected[receipt_path],
        "status": repo_relative(status_path),
        "status_sha256": expected[status_path],
        "overall_status": receipt["overall_status"],
        "five_pin_passed_or_caveated_count": 5,
        "five_pin_total_count": 5,
        "continuation_authorized": bool(status["continuation_authorized"]),
        "freshness_required": False,
        "immutable": True,
    }


def _host_pid_namespace_visible() -> tuple[bool, str]:
    text = Path("/proc/self/status").read_text(encoding="utf-8")
    line = next((row for row in text.splitlines() if row.startswith("NSpid:")), "")
    pids = line.partition(":")[2].split()
    return len(pids) == 1, line


def fresh_execution_probe(guard_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect host PID and Docker command lines immediately at Gate invocation."""

    visible, nspid = _host_pid_namespace_visible()
    if bool(guard_cfg["require_host_pid_namespace_visible"]) and not visible:
        raise GateContractError(
            "Gate A lacks host PID namespace visibility; use the locked wrapper"
        )
    patterns = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in guard_cfg["local_namespace_forbidden_command_regexes"]
    ]
    process_matches: list[dict[str, Any]] = []
    ps = _run_text(["ps", "-eo", "pid=,args="])
    for line in ps.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        matched = [pattern.pattern for pattern in patterns if pattern.search(command)]
        if matched:
            process_matches.append(
                {"pid": pid, "command": command, "matched_regexes": matched}
            )
    docker = _run_text(
        [
            "docker",
            "ps",
            "--no-trunc",
            "--format",
            "{{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Command}}",
        ],
        check=False,
    )
    if bool(guard_cfg["require_docker_container_probe"]) and docker.returncode != 0:
        raise GateContractError(
            f"fresh Docker process probe failed: {docker.stderr.strip()}"
        )
    containers: list[dict[str, Any]] = []
    container_matches: list[dict[str, Any]] = []
    for line in docker.stdout.splitlines():
        fields = line.split("\t", 3)
        if len(fields) != 4:
            continue
        cid, image, name, command = fields
        record = {
            "id": cid,
            "image": image,
            "name": name,
            "command": command,
        }
        containers.append(record)
        matched = [pattern.pattern for pattern in patterns if pattern.search(command)]
        if matched:
            container_matches.append({**record, "matched_regexes": matched})
    if process_matches or container_matches:
        raise GateContractError("fresh host probe found a known training entry point")

    gpu = _run_text(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
    )
    gpu_rows = [row.strip() for row in gpu.stdout.splitlines() if row.strip()]
    gpu_probe_failed = gpu.returncode != 0
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "host_pid_namespace_visible": visible,
        "nspid": nspid,
        "known_training_entry_points_absent": True,
        "matching_processes": [],
        "matching_container_commands": [],
        "running_container_count": len(containers),
        "running_containers": containers,
        "gpu_compute_probe_returncode": gpu.returncode,
        "gpu_compute_probe_stderr": gpu.stderr.strip(),
        "gpu_compute_processes_raw": gpu_rows,
        "unknown_gpu_compute_processes": gpu_rows,
        "downstream_gpu_stage_launch_blocked": bool(gpu_probe_failed or gpu_rows),
        "execution_device": guard_cfg["execution_device"],
        "cuda_used": bool(guard_cfg["cuda_used"]),
        "cpu_gate_unknown_gpu_policy": guard_cfg["cpu_gate_unknown_gpu_policy"],
    }


def validate_runtime_guard_receipt(
    path: Path, config_path: Path
) -> dict[str, Any]:
    if not path.is_file():
        raise GateContractError("runtime guard receipt is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema")
        != "jointbuildgs.fusion_w1.alignment_runtime_guard.v1"
        or payload.get("cpu_gate_authorized") is not True
        or payload.get("status")
        not in {"PASSED", "PASSED_WITH_DOWNSTREAM_GPU_BLOCK"}
    ):
        raise GateContractError("runtime guard did not authorize CPU Gate A")
    config_record = payload.get("config") or {}
    if config_record.get("path") != repo_relative(config_path) or config_record.get(
        "sha256"
    ) != sha256_file(config_path):
        raise GateContractError("runtime guard config binding mismatch")
    probe = find_named_record(payload, "no_active_training_guard")
    if probe.get("evidence", {}).get("known_training_entry_points_absent") is not True:
        raise GateContractError("runtime guard lacks a clean training-process probe")
    return payload


def _reject_forbidden_headers(
    headers: Iterable[str], config: Mapping[str, Any], source: str
) -> None:
    forbidden = {
        normalized_field(value)
        for value in config["input_locks"]["footprint_contract"][
            "forbidden_target_or_view_fields"
        ]
    }
    found = sorted(
        value for value in map(normalized_field, headers) if value in forbidden
    )
    if found:
        raise GateContractError(
            f"{source} exposes forbidden GT fields: {', '.join(found)}"
        )


def load_targets(
    path: Path, config: Mapping[str, Any], cohort: str
) -> list[Target]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise GateContractError("targets CSV has no header")
        _reject_forbidden_headers(reader.fieldnames, config, str(path))
        if "building_id" not in reader.fieldnames:
            raise GateContractError("targets CSV requires building_id")
        queue_contract = config.get("target_queue_contract", {})
        queue_field = str(queue_contract.get("queue_status_field", "queue_status"))
        resolution_field = str(
            queue_contract.get(
                "cohort_resolution_status_field", "cohort_resolution_status"
            )
        )
        if queue_field not in reader.fieldnames:
            raise GateContractError(f"targets CSV requires {queue_field}")
        if resolution_field not in reader.fieldnames:
            raise GateContractError(f"targets CSV requires {resolution_field}")
        rows = list(reader)
    targets: list[Target] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        row_cohort = str(row.get("cohort", "")).strip().lower()
        if cohort != "all" and row_cohort != cohort:
            continue
        building_id = canonical_building_id(row["building_id"])
        if building_id in seen:
            raise GateContractError(f"duplicate target building: {building_id}")
        seen.add(building_id)
        try:
            processing_order = int(row.get("processing_order") or index)
        except ValueError as exc:
            raise GateContractError(
                f"invalid processing_order for {building_id}"
            ) from exc
        targets.append(
            Target(
                building_id=building_id,
                processing_order=processing_order,
                cohort=row_cohort,
                tier=str(row.get("tier", "")).strip(),
                queue_status=str(row.get(queue_field, "")).strip(),
                cohort_resolution_status=str(
                    row.get(resolution_field, "")
                ).strip(),
            )
        )
    targets.sort(key=lambda item: (item.processing_order, item.building_id))
    if not targets:
        raise GateContractError(f"no targets selected for cohort={cohort}")
    required_queue_status = str(
        config.get("target_queue_contract", {}).get(
            "required_queue_status", ""
        )
    )
    if required_queue_status:
        mismatched = [
            target.building_id
            for target in targets
            if target.queue_status != required_queue_status
        ]
        if mismatched:
            raise GateContractError(
                f"target queue status drift from {required_queue_status!r}: "
                + ", ".join(mismatched[:8])
            )
    missing_resolution = [
        target.building_id
        for target in targets
        if not target.cohort_resolution_status
    ]
    if missing_resolution:
        raise GateContractError(
            "targets missing cohort_resolution_status: "
            + ", ".join(missing_resolution[:8])
        )
    return targets


def _coordinate_dimensions(value: Any) -> set[int]:
    if not isinstance(value, list) or not value:
        return set()
    if all(isinstance(v, (int, float)) for v in value):
        return {len(value)}
    out: set[int] = set()
    for child in value:
        out.update(_coordinate_dimensions(child))
    return out


def _ring_area(ring: np.ndarray) -> float:
    q = np.asarray(ring, dtype=np.float64)
    return 0.5 * abs(
        float(
            np.dot(q[:, 0], np.roll(q[:, 1], -1))
            - np.dot(q[:, 1], np.roll(q[:, 0], -1))
        )
    )


def _geometry_largest_ring(geometry: Mapping[str, Any]) -> np.ndarray:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    dims = _coordinate_dimensions(coordinates)
    if dims != {2}:
        raise GateContractError(
            f"footprint geometry must contain XY only; coordinate dimensions={dims}"
        )
    rings: list[np.ndarray] = []
    if kind == "Polygon":
        if coordinates:
            rings.append(np.asarray(coordinates[0], dtype=np.float64))
    elif kind == "MultiPolygon":
        for polygon in coordinates or []:
            if polygon:
                rings.append(np.asarray(polygon[0], dtype=np.float64))
    else:
        raise GateContractError(f"unsupported footprint geometry: {kind}")
    rings = [ring for ring in rings if ring.ndim == 2 and len(ring) >= 4]
    if not rings:
        raise GateContractError("empty footprint polygon")
    ring = max(rings, key=_ring_area)
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack([ring, ring[0]])
    return ring


def _load_footprint_payload(
    path: Path, layer: str | None, id_field: str
) -> dict[str, Any]:
    if path.suffix.lower() in {".json", ".geojson"}:
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() != ".gpkg":
        raise GateContractError("footprints must be GeoJSON or a 2D GPKG layer")
    command = [
        "ogr2ogr",
        "-f",
        "GeoJSON",
        "/vsistdout/",
        str(path),
    ]
    if layer:
        command.append(layer)
    command.extend(["-select", id_field])
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "")
        raise GateContractError(f"failed to read GPKG with ogr2ogr: {detail}") from exc
    return json.loads(completed.stdout)


def load_footprints(
    path: Path,
    target_ids: Sequence[str],
    id_field: str,
    layer: str | None,
    config: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    payload = _load_footprint_payload(path, layer, id_field)
    if payload.get("type") != "FeatureCollection":
        raise GateContractError("footprint source must be a FeatureCollection")
    crs_text = json.dumps(payload.get("crs", {}), ensure_ascii=False)
    if "25832" not in crs_text:
        raise GateContractError(
            "footprint source does not explicitly declare EPSG:25832"
        )
    requested = set(target_ids)
    out: dict[str, np.ndarray] = {}
    forbidden = {
        normalized_field(value)
        for value in config["input_locks"]["footprint_contract"][
            "forbidden_target_or_view_fields"
        ]
    }
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        bad = sorted(
            key
            for key in properties
            if normalized_field(key) in forbidden
            and properties.get(key) not in (None, "")
        )
        if bad:
            raise GateContractError(
                "footprint feature exposes forbidden non-XY GT properties: "
                + ", ".join(bad)
            )
        if id_field not in properties:
            raise GateContractError(f"footprint feature lacks {id_field}")
        building_id = canonical_building_id(properties[id_field])
        if building_id not in requested:
            continue
        ring = _geometry_largest_ring(feature.get("geometry") or {})
        previous = out.get(building_id)
        if previous is None or _ring_area(ring) > _ring_area(previous):
            out[building_id] = ring
    missing = sorted(requested - set(out))
    if missing:
        raise GateContractError(
            f"approved footprint XY missing for {len(missing)} targets: "
            + ", ".join(missing[:8])
        )
    return out


def _safe_image_path(image_dir: Path, name: str) -> Path:
    candidate = (image_dir / name).resolve()
    try:
        candidate.relative_to(image_dir.resolve())
    except ValueError as exc:
        raise GateContractError(f"COLMAP image name escapes image root: {name}") from exc
    return candidate


def load_training_inventory(
    sparse_dir: Path,
    image_dir: Path,
    expected_count: int | None,
) -> tuple[
    dict[int, Camera],
    dict[int, ColmapImage],
    dict[str, ColmapImage],
    dict[str, Path],
]:
    camera_path = sparse_dir / "cameras.bin"
    pose_path = sparse_dir / "images.bin"
    if not camera_path.is_file() or not pose_path.is_file():
        raise GateContractError("Gate A requires COLMAP cameras.bin and images.bin")
    cameras = read_cameras_bin(camera_path)
    images = read_images_bin(pose_path)
    by_name: dict[str, ColmapImage] = {}
    image_paths: dict[str, Path] = {}
    for image in images.values():
        if image.name in by_name:
            raise GateContractError(f"duplicate COLMAP image name: {image.name}")
        path = _safe_image_path(image_dir, image.name)
        if path.is_file():
            by_name[image.name] = image
            image_paths[image.name] = path
    if expected_count is not None and len(by_name) != int(expected_count):
        raise GateContractError(
            "COLMAP-pose/training-image intersection drift: "
            f"{len(by_name)} != {int(expected_count)}"
        )
    return cameras, images, by_name, image_paths


def project_camera_points(camera: Camera, camera_xyz: np.ndarray) -> np.ndarray:
    xyz = np.asarray(camera_xyz, dtype=np.float64)
    z = xyz[:, 2]
    x = xyz[:, 0] / z
    y = xyz[:, 1] / z
    p = np.asarray(camera.params, dtype=np.float64)
    model = camera.model
    if model == "SIMPLE_PINHOLE":
        f, cx, cy = p[:3]
        fx = fy = f
        xd, yd = x, y
    elif model == "PINHOLE":
        fx, fy, cx, cy = p[:4]
        xd, yd = x, y
    elif model == "SIMPLE_RADIAL":
        f, cx, cy, k1 = p[:4]
        fx = fy = f
        r2 = x * x + y * y
        scale = 1.0 + k1 * r2
        xd, yd = x * scale, y * scale
    elif model == "RADIAL":
        f, cx, cy, k1, k2 = p[:5]
        fx = fy = f
        r2 = x * x + y * y
        scale = 1.0 + k1 * r2 + k2 * r2 * r2
        xd, yd = x * scale, y * scale
    elif model == "OPENCV":
        fx, fy, cx, cy, k1, k2, p1, p2 = p[:8]
        r2 = x * x + y * y
        radial = 1.0 + k1 * r2 + k2 * r2 * r2
        xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
        yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
    elif model == "FULL_OPENCV":
        fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = p[:12]
        r2 = x * x + y * y
        r4 = r2 * r2
        r6 = r4 * r2
        denominator = 1.0 + k4 * r2 + k5 * r4 + k6 * r6
        if np.any(np.abs(denominator) < 1e-12):
            raise GateContractError("FULL_OPENCV denominator is singular")
        radial = (1.0 + k1 * r2 + k2 * r4 + k3 * r6) / denominator
        xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
        yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
    else:
        raise GateContractError(
            f"unsupported COLMAP camera model for locked projection: {model}"
        )
    return np.column_stack([fx * xd + cx, fy * yd + cy])


def project_base_points(
    points_base: np.ndarray,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    xy_shift: Sequence[float] = (0.0, 0.0),
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points_base, dtype=np.float64).copy()
    points[:, 0] += float(xy_shift[0])
    points[:, 1] += float(xy_shift[1])
    canonical = base_to_canonical_points(
        points,
        scene_reference,
        input_datum=input_datum,
        geoid_m=geoid_m,
    )
    camera_xyz = (image.R() @ canonical.T).T + image.tvec
    front = camera_xyz[:, 2] > 1.0
    uv = np.full((len(points), 2), np.nan, dtype=np.float64)
    if np.any(front):
        uv[front] = project_camera_points(camera, camera_xyz[front])
    return uv, front


def _view_geometry(
    cloud: TargetCloud,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
) -> tuple[float, float]:
    target = base_to_canonical_points(
        cloud.target_xyz[None],
        scene_reference,
        input_datum=input_datum,
        geoid_m=geoid_m,
    )[0]
    center = -image.R().T @ image.tvec
    ray = center - target
    norm = float(np.linalg.norm(ray))
    nadir = (
        math.degrees(math.acos(min(1.0, abs(float(ray[2])) / norm)))
        if norm > 1e-9
        else float("nan")
    )
    uv, front = project_base_points(
        cloud.building_xyz,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
    )
    inframe = (
        front
        & (uv[:, 0] >= 0)
        & (uv[:, 0] < camera.width)
        & (uv[:, 1] >= 0)
        & (uv[:, 1] < camera.height)
    )
    if not np.any(inframe):
        return nadir, float("inf")
    q = uv[inframe]
    radius = np.sqrt(
        ((q[:, 0] - camera.params[2]) / (0.5 * camera.width)) ** 2
        + ((q[:, 1] - camera.params[3]) / (0.5 * camera.height)) ** 2
    )
    return nadir, float(np.max(radius))


def _deterministic_subsample(points: np.ndarray, cap: int) -> np.ndarray:
    if len(points) <= cap:
        return points
    indices = np.linspace(0, len(points) - 1, cap).astype(np.int64)
    return points[indices]


def auto_select_views(
    targets: Sequence[Target],
    clouds: Mapping[str, TargetCloud],
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    selection_cfg: Mapping[str, Any],
    boundary_cfg: Mapping[str, Any],
    alignment_cfg: Mapping[str, Any],
) -> list[SelectedView]:
    """Choose views by ALS-only metric observability before reading intensities."""

    minimum = int(selection_cfg["minimum_views_per_building"])
    maximum = int(selection_cfg["maximum_views_per_building"])
    min_points = int(selection_cfg["minimum_als_building_points_in_frame"])
    point_cap = int(selection_cfg["selection_projection_point_cap"])
    boundary_cap = int(selection_cfg["selection_boundary_point_cap"])
    sigma_px = float(selection_cfg["selection_edge_localization_sigma_px"])
    uncertainty_reference_m = float(
        selection_cfg["predicted_uncertainty_reference_m"]
    )
    bin_count = int(selection_cfg["azimuth_bin_count"])
    minimum_bins = int(selection_cfg["minimum_selected_azimuth_bins"])
    if not 10 <= minimum <= maximum <= 30:
        raise GateContractError("view-selection count lock must remain within 10..30")
    if boundary_cap < 24 or bin_count != 8 or minimum_bins != 1:
        raise GateContractError("view-selection boundary/azimuth locks drifted")
    selected: list[SelectedView] = []
    ordered_images = sorted(images_by_name.values(), key=lambda item: item.name)
    for target in targets:
        cloud = clouds[target.building_id]
        sample = _deterministic_subsample(cloud.building_xyz, point_cap)
        sample_cloud = TargetCloud(
            building_id=cloud.building_id,
            footprint_xy=cloud.footprint_xy,
            building_xyz=sample,
            ground_xyz=cloud.ground_xyz,
            source_tiles=cloud.source_tiles,
        )
        target_canonical = base_to_canonical_points(
            cloud.target_xyz[None],
            scene_reference,
            input_datum=input_datum,
            geoid_m=geoid_m,
        )[0]
        candidates: list[dict[str, Any]] = []
        for image in ordered_images:
            camera = cameras.get(image.camera_id)
            if camera is None:
                raise GateContractError(
                    f"missing camera {image.camera_id} for {image.name}"
                )
            uv, front = project_base_points(
                sample,
                image,
                camera,
                scene_reference,
                input_datum,
                geoid_m,
            )
            inframe = (
                front
                & (uv[:, 0] >= 0)
                & (uv[:, 0] < camera.width)
                & (uv[:, 1] >= 0)
                & (uv[:, 1] < camera.height)
            )
            count = int(np.sum(inframe))
            if count < min_points:
                continue
            nadir, radius = _view_geometry(
                sample_cloud,
                image,
                camera,
                scene_reference,
                input_datum,
                geoid_m,
            )
            try:
                boundary = visible_eave_boundary(
                    cloud,
                    image,
                    camera,
                    scene_reference,
                    input_datum,
                    geoid_m,
                    (0.0, 0.0),
                    boundary_cfg,
                )
                boundary_indices = np.arange(len(boundary.xyz), dtype=np.int64)
                if len(boundary_indices) > boundary_cap:
                    boundary_indices = np.linspace(
                        0, len(boundary_indices) - 1, boundary_cap
                    ).astype(np.int64)
                xyz = boundary.xyz[boundary_indices]
                normal_uv = boundary.normal_uv[boundary_indices]
                jacobians, conditions = xy_projection_jacobians(
                    xyz,
                    image,
                    camera,
                    scene_reference,
                    input_datum,
                    geoid_m,
                    (0.0, 0.0),
                    float(alignment_cfg["xy_jacobian_step_m"]),
                )
                if (
                    not np.isfinite(conditions).all()
                    or float(np.max(conditions))
                    > float(alignment_cfg["maximum_xy_jacobian_condition"])
                ):
                    continue
                normal_design = np.einsum(
                    "nui,nu->ni", jacobians, normal_uv
                )
                sensitivity = np.linalg.norm(normal_design, axis=1)
                if (
                    not np.isfinite(sensitivity).all()
                    or np.any(
                        sensitivity
                        < float(
                            alignment_cfg[
                                "minimum_normal_sensitivity_px_per_m"
                            ]
                        )
                    )
                ):
                    continue
                metres_per_px = 1.0 / sensitivity
                observability_p90 = float(
                    np.percentile(metres_per_px, 90)
                )
                predicted_uncertainty = sigma_px * observability_p90
                if not np.isfinite(predicted_uncertainty):
                    continue
            except GateContractError:
                continue
            camera_center = -image.R().T @ image.tvec
            azimuth = math.atan2(
                float(camera_center[1] - target_canonical[1]),
                float(camera_center[0] - target_canonical[0]),
            )
            azimuth_bin = int(
                math.floor(((azimuth + 2.0 * math.pi) % (2.0 * math.pi))
                           / (2.0 * math.pi / bin_count))
            ) % bin_count
            candidates.append(
                {
                    "rank": (
                        predicted_uncertainty,
                        observability_p90,
                        -len(boundary.xyz),
                        radius,
                        image.name,
                    ),
                    "name": image.name,
                    "image_id": image.id,
                    "camera_id": image.camera_id,
                    "n_inframe": count,
                    "radius": radius,
                    "nadir": nadir,
                    "observability_p90": observability_p90,
                    "predicted_uncertainty": predicted_uncertainty,
                    "uncertainty_reference_m": uncertainty_reference_m,
                    "azimuth_bin": azimuth_bin,
                }
            )
        if len(candidates) < minimum:
            raise GateContractError(
                f"{target.building_id}: only {len(candidates)} result-blind "
                f"observable training views satisfy the class-6/GSD locks; "
                f"required {minimum}"
            )
        grouped_candidates: dict[int, list[dict[str, Any]]] = {
            index: [] for index in range(bin_count)
        }
        for candidate in candidates:
            grouped_candidates[int(candidate["azimuth_bin"])].append(candidate)
        for values in grouped_candidates.values():
            values.sort(key=lambda value: value["rank"])
        nonempty_bins = [
            index for index in range(bin_count) if grouped_candidates[index]
        ]
        if len(nonempty_bins) < minimum_bins:
            raise GateContractError(
                f"{target.building_id}: observable views span only "
                f"{len(nonempty_bins)} azimuth bins; required {minimum_bins}"
            )
        chosen: list[dict[str, Any]] = []
        while len(chosen) < maximum:
            added = False
            for bin_index in range(bin_count):
                values = grouped_candidates[bin_index]
                if values and len(chosen) < maximum:
                    chosen.append(values.pop(0))
                    added = True
            if not added:
                break
        for order, candidate in enumerate(chosen, 1):
            selected.append(
                SelectedView(
                    building_id=target.building_id,
                    order=order,
                    name=str(candidate["name"]),
                    image_id=int(candidate["image_id"]),
                    camera_id=int(candidate["camera_id"]),
                    selection_source=(
                        "auto_als_observability_azimuth_round_robin"
                    ),
                    n_building_inframe_at_selection=int(candidate["n_inframe"]),
                    frame_radius=float(candidate["radius"]),
                    view_nadir_deg=float(candidate["nadir"]),
                    observability_p90_m_per_px=float(
                        candidate["observability_p90"]
                    ),
                    predicted_metric_uncertainty_m=float(
                        candidate["predicted_uncertainty"]
                    ),
                    azimuth_bin=int(candidate["azimuth_bin"]),
                )
            )
    return selected


def load_provided_views(
    path: Path,
    targets: Sequence[Target],
    config: Mapping[str, Any],
    images_by_name: Mapping[str, ColmapImage],
    cameras: Mapping[int, Camera],
    clouds: Mapping[str, TargetCloud],
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
) -> list[SelectedView]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise GateContractError("views CSV has no header")
        _reject_forbidden_headers(reader.fieldnames, config, str(path))
        if "building_id" not in reader.fieldnames:
            raise GateContractError("views CSV requires building_id")
        view_field = "view" if "view" in reader.fieldnames else "image_name"
        if view_field not in reader.fieldnames:
            raise GateContractError("views CSV requires view or image_name")
        rows = list(reader)
    target_ids = {target.building_id for target in targets}
    grouped: dict[str, list[str]] = {building_id: [] for building_id in target_ids}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        building_id = canonical_building_id(row["building_id"])
        if building_id not in target_ids:
            continue
        name = str(row[view_field]).strip()
        key = (building_id, name)
        if key in seen:
            raise GateContractError(f"duplicate building/view mapping: {key}")
        seen.add(key)
        if name not in images_by_name:
            raise GateContractError(
                f"provided view is outside training pose/image intersection: {name}"
            )
        grouped[building_id].append(name)
    minimum = int(config["view_selection"]["minimum_views_per_building"])
    maximum = int(config["view_selection"]["maximum_views_per_building"])
    selected: list[SelectedView] = []
    for target in targets:
        names = grouped[target.building_id]
        if not minimum <= len(names) <= maximum:
            raise GateContractError(
                f"{target.building_id}: provided view count {len(names)} is "
                f"outside locked range {minimum}..{maximum}"
            )
        for order, name in enumerate(names, 1):
            image = images_by_name[name]
            camera = cameras[image.camera_id]
            uv, front = project_base_points(
                clouds[target.building_id].building_xyz,
                image,
                camera,
                scene_reference,
                input_datum,
                geoid_m,
            )
            inframe = (
                front
                & (uv[:, 0] >= 0)
                & (uv[:, 0] < camera.width)
                & (uv[:, 1] >= 0)
                & (uv[:, 1] < camera.height)
            )
            nadir, radius = _view_geometry(
                clouds[target.building_id],
                image,
                camera,
                scene_reference,
                input_datum,
                geoid_m,
            )
            selected.append(
                SelectedView(
                    building_id=target.building_id,
                    order=order,
                    name=name,
                    image_id=image.id,
                    camera_id=image.camera_id,
                    selection_source="provided_training_intersection_csv",
                    n_building_inframe_at_selection=int(np.sum(inframe)),
                    frame_radius=radius,
                    view_nadir_deg=nadir,
                )
            )
    return selected


def assign_registration_splits(
    views: Sequence[SelectedView], micro_cfg: Mapping[str, Any]
) -> list[SelectedView]:
    """Globally split image names before residuals exist.

    A shared image can never be fit for one building and held out for another.
    """

    seed = str(micro_cfg["split_seed"])
    if not math.isclose(float(micro_cfg["fit_fraction"]), 0.5):
        raise GateContractError("micro fit_fraction must be strictly between 0 and 1")
    assignments = {
        name: (
            "fit"
            if hashlib.sha256(
                f"{seed}\0{name}".encode("utf-8")
            ).digest()[0]
            % 2
            == 0
            else "heldout"
        )
        for name in {view.name for view in views}
    }
    return [
        replace(
            view,
            registration_split=assignments[view.name],
        )
        for view in views
    ]


def _als_eave_boundary(
    cloud: TargetCloud, cfg: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract a non-star external boundary from actual strict class-6 XYZ."""

    points = np.asarray(cloud.building_xyz, dtype=np.float64)
    cell = float(cfg["xy_grid_cell_m"])
    if not 0.0 < cell <= 0.5:
        raise GateContractError("ALS boundary grid cell must remain in (0, 0.5] m")
    origin = np.min(points[:, :2], axis=0) - 2.0 * cell
    keys = np.floor((points[:, :2] - origin) / cell).astype(np.int64)
    width = int(np.max(keys[:, 0])) + 3
    height = int(np.max(keys[:, 1])) + 3
    occupied = np.zeros((height, width), dtype=bool)
    cell_points: dict[tuple[int, int], list[int]] = {}
    for index, key in enumerate(keys):
        x, y = int(key[0]), int(key[1])
        occupied[y, x] = True
        cell_points.setdefault((x, y), []).append(index)

    # Keep only the largest 8-connected class-6 support (tie: lexicographic seed).
    visited = np.zeros_like(occupied)
    components: list[list[tuple[int, int]]] = []
    for y, x in zip(*np.nonzero(occupied)):
        if visited[y, x]:
            continue
        queue: deque[tuple[int, int]] = deque([(int(x), int(y))])
        visited[y, x] = True
        component: list[tuple[int, int]] = []
        while queue:
            cx, cy = queue.popleft()
            component.append((cx, cy))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and occupied[ny, nx]
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        queue.append((nx, ny))
        components.append(component)
    if not components:
        raise GateContractError("strict class-6 crop has no occupied grid support")
    component = min(
        components,
        key=lambda value: (-len(value), min(value)),
    )
    coverage = len(component) / max(1, int(np.sum(occupied)))
    if coverage < float(cfg["minimum_main_component_occupied_fraction"]):
        raise GateContractError(
            f"main class-6 support fraction {coverage:.3f} below lock"
        )
    component_point_count = sum(len(cell_points[key]) for key in component)
    point_coverage = component_point_count / max(1, len(points))
    if point_coverage < float(cfg["minimum_main_component_point_fraction"]):
        raise GateContractError(
            f"main class-6 point fraction {point_coverage:.3f} below lock"
        )
    support = np.zeros_like(occupied)
    for x, y in component:
        support[y, x] = True

    # Locked one-cell binary closing reduces sampling pinholes, but output XYZ
    # remains an actual class-6 return from an originally occupied cell.
    closed = support.copy()
    for _ in range(int(cfg["occupancy_closing_iterations"])):
        dilated = _dilate8(closed)
        padded = np.pad(dilated, 1, mode="constant")
        eroded = np.ones_like(dilated)
        for dy in range(3):
            for dx in range(3):
                eroded &= padded[dy : dy + height, dx : dx + width]
        closed = eroded

    # Flood only exterior empty cells from the raster border.
    exterior = np.zeros_like(closed)
    queue = deque()
    for x in range(width):
        for y in (0, height - 1):
            if not closed[y, x] and not exterior[y, x]:
                exterior[y, x] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if not closed[y, x] and not exterior[y, x]:
                exterior[y, x] = True
                queue.append((x, y))
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if (
                0 <= nx < width
                and 0 <= ny < height
                and not closed[ny, nx]
                and not exterior[ny, nx]
            ):
                exterior[ny, nx] = True
                queue.append((nx, ny))

    boundary_cells: list[tuple[int, int]] = []
    outward_rows: list[np.ndarray] = []
    for x, y in sorted(component, key=lambda value: (value[1], value[0])):
        exposed = [
            np.array([dx, dy], dtype=np.float64)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= x + dx < width
            and 0 <= y + dy < height
            and exterior[y + dy, x + dx]
        ]
        if exposed:
            boundary_cells.append((x, y))
            outward = np.sum(exposed, axis=0)
            outward /= max(float(np.linalg.norm(outward)), 1e-12)
            outward_rows.append(outward)
    xyz_rows: list[np.ndarray] = []
    source_indices: list[int] = []
    for key, outward in zip(boundary_cells, outward_rows):
        indices = cell_points[key]
        center = origin + cell * (np.asarray(key, dtype=np.float64) + 0.5)
        # Preserve an actual return and choose the most exterior source in-cell.
        best = min(
            indices,
            key=lambda index: (
                -float(np.dot(points[index, :2] - center, outward)),
                -float(points[index, 2]),
                index,
            ),
        )
        xyz_rows.append(points[best])
        source_indices.append(best)
    minimum = int(cfg["minimum_boundary_points"])
    if len(xyz_rows) < minimum:
        raise GateContractError(
            f"only {len(xyz_rows)} external ALS class-6 boundary cells; "
            f"required {minimum}"
        )
    xyz = np.asarray(xyz_rows, dtype=np.float64)

    # Local PCA on actual ALS boundary XY yields tangent orientation without
    # any radial ordering or footprint-perimeter substitution.
    tangent_rows: list[np.ndarray] = []
    radius2 = float(cfg["local_tangent_radius_m"]) ** 2
    minimum_neighbors = int(cfg["minimum_local_tangent_neighbors"])
    for index, point in enumerate(xyz):
        delta = xyz[:, :2] - point[:2]
        neighbors = np.flatnonzero(np.sum(delta * delta, axis=1) <= radius2)
        if len(neighbors) < minimum_neighbors:
            distances = np.sum(delta * delta, axis=1)
            neighbors = np.argsort(distances, kind="mergesort")[
                : max(minimum_neighbors, 2)
            ]
        local = xyz[neighbors, :2]
        covariance = np.cov(local.T, bias=True)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        tangent = eigenvectors[:, int(np.argmax(eigenvalues))]
        if tangent[0] < 0 or (math.isclose(tangent[0], 0.0) and tangent[1] < 0):
            tangent = -tangent
        tangent_rows.append(tangent)
    tangent = np.asarray(tangent_rows, dtype=np.float64)
    # The outward vector comes only from the exterior flood around class-6
    # occupancy. GroundSurface XY has no direction or residual role.
    outward = np.asarray(outward_rows, dtype=np.float64)
    source_index = np.asarray(source_indices, dtype=np.int64)
    maximum_points = int(cfg["maximum_boundary_points"])
    if len(xyz) > maximum_points:
        indices = np.linspace(0, len(xyz) - 1, maximum_points).astype(np.int64)
        xyz = xyz[indices]
        tangent = tangent[indices]
        outward = outward[indices]
        source_index = source_index[indices]
    return xyz, tangent, outward, source_index


def project_base_points_with_depth(
    points_base: np.ndarray,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    xy_shift: Sequence[float] = (0.0, 0.0),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.asarray(points_base, dtype=np.float64).copy()
    points[:, 0] += float(xy_shift[0])
    points[:, 1] += float(xy_shift[1])
    canonical = base_to_canonical_points(
        points,
        scene_reference,
        input_datum=input_datum,
        geoid_m=geoid_m,
    )
    camera_xyz = (image.R() @ canonical.T).T + image.tvec
    depth = camera_xyz[:, 2]
    front = depth > 1.0
    uv = np.full((len(points), 2), np.nan, dtype=np.float64)
    if np.any(front):
        uv[front] = project_camera_points(camera, camera_xyz[front])
    return uv, front, depth


def visible_eave_boundary(
    cloud: TargetCloud,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    xy_shift: Sequence[float],
    cfg: Mapping[str, Any],
) -> VisibleBoundary:
    """Project actual ALS external-boundary returns and retain z-buffer winners."""

    eave_xyz, tangent_xy, outward_xy, source_index = _als_eave_boundary(cloud, cfg)
    uv, front, depth = project_base_points_with_depth(
        eave_xyz,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
    )
    roof_uv, roof_front, roof_depth = project_base_points_with_depth(
        cloud.building_xyz,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
    )
    pixel = int(cfg["zbuffer_pixel_size"])
    zbuffer: dict[tuple[int, int], float] = {}
    roof_inframe = (
        roof_front
        & (roof_uv[:, 0] >= 0)
        & (roof_uv[:, 0] < camera.width)
        & (roof_uv[:, 1] >= 0)
        & (roof_uv[:, 1] < camera.height)
    )
    for point_uv, point_depth in zip(roof_uv[roof_inframe], roof_depth[roof_inframe]):
        key = (int(math.floor(point_uv[0] / pixel)), int(math.floor(point_uv[1] / pixel)))
        previous = zbuffer.get(key)
        if previous is None or point_depth < previous:
            zbuffer[key] = float(point_depth)
    inframe = (
        front
        & (uv[:, 0] >= 0)
        & (uv[:, 0] < camera.width)
        & (uv[:, 1] >= 0)
        & (uv[:, 1] < camera.height)
    )
    tolerance = float(cfg["zbuffer_depth_tolerance_m"])
    visible = np.zeros(len(eave_xyz), dtype=bool)
    for index in np.flatnonzero(inframe):
        key = (
            int(math.floor(uv[index, 0] / pixel)),
            int(math.floor(uv[index, 1] / pixel)),
        )
        nearby = [
            zbuffer[(key[0] + dx, key[1] + dy)]
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (key[0] + dx, key[1] + dy) in zbuffer
        ]
        visible[index] = bool(
            nearby and depth[index] <= min(nearby) + tolerance
        )
    fraction = float(np.sum(visible) / max(1, np.sum(inframe)))
    if fraction < float(cfg["minimum_visible_boundary_fraction"]):
        raise GateContractError(
            f"z-buffer-visible eave fraction {fraction:.3f} below lock"
        )
    if int(np.sum(visible)) < int(cfg["minimum_boundary_points"]):
        raise GateContractError("insufficient z-buffer-visible eave points")
    chosen_xyz = eave_xyz[visible]
    chosen_uv = uv[visible]
    chosen_tangent = tangent_xy[visible]
    chosen_outward = outward_xy[visible]
    chosen_source_index = source_index[visible]
    tangent_points = chosen_xyz.copy()
    tangent_points[:, :2] += 0.25 * chosen_tangent
    tangent_uv, tangent_front = project_base_points(
        tangent_points,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
    )
    if not np.all(tangent_front):
        raise GateContractError("eave tangent projection crossed camera plane")
    tangent_image = tangent_uv - chosen_uv
    outward_points = chosen_xyz.copy()
    outward_points[:, :2] += 0.25 * chosen_outward
    outward_uv, outward_front = project_base_points(
        outward_points,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
    )
    if not np.all(outward_front):
        raise GateContractError("eave outward projection crossed camera plane")
    outward_image = outward_uv - chosen_uv
    tangent_norm = np.linalg.norm(tangent_image, axis=1)
    valid_tangent = tangent_norm > 1e-6
    if int(np.sum(valid_tangent)) < int(cfg["minimum_boundary_points"]):
        raise GateContractError("insufficient projected eave tangents")
    chosen_xyz = chosen_xyz[valid_tangent]
    chosen_uv = chosen_uv[valid_tangent]
    chosen_source_index = chosen_source_index[valid_tangent]
    chosen_outward = chosen_outward[valid_tangent]
    outward_image = outward_image[valid_tangent]
    tangent_image = tangent_image[valid_tangent] / tangent_norm[valid_tangent, None]
    normal_uv = np.column_stack([-tangent_image[:, 1], tangent_image[:, 0]])
    flip = np.sum(normal_uv * outward_image, axis=1) < 0
    normal_uv[flip] *= -1.0
    return VisibleBoundary(
        xyz=chosen_xyz,
        source_index=chosen_source_index,
        uv=chosen_uv,
        normal_uv=normal_uv,
        outward_xy=chosen_outward,
        camera_depth=depth[visible][valid_tangent],
        source_count=len(eave_xyz),
        visible_fraction=fraction,
    )


def _convolve_axis(array: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    radius = len(kernel) // 2
    pads = [(0, 0)] * array.ndim
    pads[axis] = (radius, radius)
    padded = np.pad(array, pads, mode="reflect")
    result = np.zeros_like(array, dtype=np.float64)
    for index, weight in enumerate(kernel):
        slices = [slice(None)] * array.ndim
        slices[axis] = slice(index, index + array.shape[axis])
        result += float(weight) * padded[tuple(slices)]
    return result


def _bilinear(array: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    height, width = array.shape
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, width - 1.000001)
    y = np.clip(np.asarray(y, dtype=np.float64), 0.0, height - 1.000001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = x - x0
    wy = y - y0
    return (
        (1 - wx) * (1 - wy) * array[y0, x0]
        + wx * (1 - wy) * array[y0, x1]
        + (1 - wx) * wy * array[y1, x0]
        + wx * wy * array[y1, x1]
    )


def _dilate8(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant")
    out = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            out |= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return out


def extract_subpixel_edges(
    gray: np.ndarray, cfg: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Pure NumPy result-blind NMS, hysteresis, and quadratic localization."""

    image = np.asarray(gray, dtype=np.float64)
    kernel = np.asarray(cfg["gaussian_kernel_1d"], dtype=np.float64)
    if len(kernel) % 2 != 1 or not math.isclose(
        float(np.sum(kernel)), 1.0, abs_tol=1e-9
    ):
        raise GateContractError("locked Gaussian kernel must be odd and sum to one")
    smooth = _convolve_axis(_convolve_axis(image, kernel, 1), kernel, 0)
    gx = (
        10.0 * (np.roll(smooth, -1, 1) - np.roll(smooth, 1, 1))
        + 3.0
        * (
            np.roll(np.roll(smooth, -1, 1), -1, 0)
            - np.roll(np.roll(smooth, 1, 1), -1, 0)
            + np.roll(np.roll(smooth, -1, 1), 1, 0)
            - np.roll(np.roll(smooth, 1, 1), 1, 0)
        )
    ) / 16.0
    gy = (
        10.0 * (np.roll(smooth, -1, 0) - np.roll(smooth, 1, 0))
        + 3.0
        * (
            np.roll(np.roll(smooth, -1, 0), -1, 1)
            - np.roll(np.roll(smooth, 1, 0), -1, 1)
            + np.roll(np.roll(smooth, -1, 0), 1, 1)
            - np.roll(np.roll(smooth, 1, 0), 1, 1)
        )
    ) / 16.0
    magnitude = np.hypot(gx, gy)
    magnitude[[0, -1], :] = 0.0
    magnitude[:, [0, -1]] = 0.0
    angle = (np.rad2deg(np.arctan2(gy, gx)) + 180.0) % 180.0
    direction = ((angle + 22.5) // 45.0).astype(np.int8) % 4
    pairs = [
        (np.roll(magnitude, 1, 1), np.roll(magnitude, -1, 1)),
        (
            np.roll(np.roll(magnitude, 1, 0), 1, 1),
            np.roll(np.roll(magnitude, -1, 0), -1, 1),
        ),
        (np.roll(magnitude, 1, 0), np.roll(magnitude, -1, 0)),
        (
            np.roll(np.roll(magnitude, 1, 0), -1, 1),
            np.roll(np.roll(magnitude, -1, 0), 1, 1),
        ),
    ]
    nms = np.zeros_like(magnitude)
    for orientation, (before, after) in enumerate(pairs):
        keep = (
            (direction == orientation)
            & (magnitude >= before)
            & (magnitude >= after)
        )
        nms[keep] = magnitude[keep]
    positive = nms[nms > 0]
    if not len(positive):
        raise GateContractError("image crop has no non-maximum-suppressed gradients")
    high = max(
        float(cfg["high_gradient_floor_8bit"]),
        float(np.quantile(positive, float(cfg["high_gradient_quantile"]))),
    )
    low = high * float(cfg["low_to_high_ratio"])
    strong = nms >= high
    weak = nms >= low
    connected = strong.copy()
    for _ in range(int(cfg["hysteresis_max_iterations"])):
        expanded = weak & _dilate8(connected)
        if np.array_equal(expanded, connected):
            break
        connected = expanded
    else:
        raise GateContractError("edge hysteresis did not converge")
    ys, xs = np.nonzero(connected)
    minimum = int(cfg["minimum_edge_points"])
    if len(xs) < minimum:
        raise GateContractError(
            f"only {len(xs)} structural edge points; required {minimum}"
        )
    norm = np.maximum(magnitude[ys, xs], 1e-12)
    nx = gx[ys, xs] / norm
    ny = gy[ys, xs] / norm
    center = magnitude[ys, xs]
    before = _bilinear(magnitude, xs - nx, ys - ny)
    after = _bilinear(magnitude, xs + nx, ys + ny)
    denominator = before - 2.0 * center + after
    offset = np.zeros(len(xs), dtype=np.float64)
    stable = denominator < -1e-9
    offset[stable] = (
        0.5 * (before[stable] - after[stable]) / denominator[stable]
    )
    limit = float(cfg["subpixel_quadratic_offset_limit_px"])
    offset = np.clip(offset, -limit, limit)
    xy = np.column_stack([xs + offset * nx, ys + offset * ny])
    normals = np.column_stack([nx, ny])
    noise = max(
        1e-6,
        1.4826
        * float(np.median(np.abs(positive - float(np.median(positive))))),
    )
    curvature = np.maximum(-denominator, 1e-9)
    localization_sigma_px = np.clip(noise / curvature, 0.02, 2.0)
    strength = nms[ys, xs]
    cap = int(cfg["maximum_edge_points"])
    if len(xy) > cap:
        order = np.lexsort((xy[:, 0], xy[:, 1], -strength))[:cap]
        xy = xy[order]
        normals = normals[order]
        localization_sigma_px = localization_sigma_px[order]
        strength = strength[order]
    strength_image = np.zeros_like(image)
    normal_image = np.zeros((*image.shape, 2), dtype=np.float64)
    nearest_x = np.clip(np.rint(xy[:, 0]).astype(np.int64), 0, image.shape[1] - 1)
    nearest_y = np.clip(np.rint(xy[:, 1]).astype(np.int64), 0, image.shape[0] - 1)
    strength_image[nearest_y, nearest_x] = strength
    normal_image[nearest_y, nearest_x] = normals
    return xy, normals, {
        "high_threshold": high,
        "low_threshold": low,
        "edge_point_count": len(xy),
        "strong_seed_count": int(np.sum(strong)),
        "edge_strength": strength,
        "localization_sigma_px": localization_sigma_px,
        "strength_image": strength_image,
        "normal_image": normal_image,
    }


def match_oriented_edges(
    boundary_uv: np.ndarray,
    boundary_normals: np.ndarray,
    edge_xy: np.ndarray,
    edge_normals: np.ndarray,
    cfg: Mapping[str, Any],
    boundary_offset: Sequence[float] = (0.0, 0.0),
) -> dict[str, np.ndarray | float | int]:
    points = np.asarray(boundary_uv, dtype=np.float64) + np.asarray(
        boundary_offset, dtype=np.float64
    )
    normals = np.asarray(boundary_normals, dtype=np.float64)
    cosine = math.cos(math.radians(float(cfg["maximum_edge_normal_angle_deg"])))
    radius2 = float(cfg["edge_search_radius_px"]) ** 2
    tangent_limit = float(cfg["maximum_tangent_offset_px"])
    matched_boundary: list[int] = []
    matched_edge: list[int] = []
    signed: list[float] = []
    euclidean: list[float] = []
    oriented_normals: list[np.ndarray] = []
    censored = np.full(
        len(points), float(cfg["edge_search_radius_px"]), dtype=np.float64
    )
    for start in range(0, len(points), int(cfg["nearest_edge_chunk_size"])):
        stop = min(len(points), start + int(cfg["nearest_edge_chunk_size"]))
        for index in range(start, stop):
            displacement = edge_xy - points[index]
            distance2 = np.sum(displacement * displacement, axis=1)
            dot = edge_normals @ normals[index]
            aligned = np.abs(dot) >= cosine
            candidate_normals = edge_normals * np.where(dot < 0, -1.0, 1.0)[:, None]
            normal_distance = np.sum(displacement * candidate_normals, axis=1)
            tangent_vector = np.column_stack(
                [-candidate_normals[:, 1], candidate_normals[:, 0]]
            )
            tangent_distance = np.abs(np.sum(displacement * tangent_vector, axis=1))
            candidates = np.flatnonzero(
                aligned & (distance2 <= radius2) & (tangent_distance <= tangent_limit)
            )
            if not len(candidates):
                continue
            best = min(candidates, key=lambda value: (float(distance2[value]), int(value)))
            matched_boundary.append(index)
            matched_edge.append(int(best))
            signed.append(float(normal_distance[best]))
            censored[index] = abs(float(normal_distance[best]))
            euclidean.append(float(math.sqrt(distance2[best])))
            oriented_normals.append(candidate_normals[best])
    count = len(matched_boundary)
    reverse_boundary: list[int] = []
    reverse_edge: list[int] = []
    reverse_metric_boundary: list[int] = []
    reverse_metric_normal: list[np.ndarray] = []
    reverse_metric_edge: list[int] = []
    reverse_signed: list[float] = []
    reverse_censored: list[float] = []
    for edge_index, edge_point in enumerate(np.asarray(edge_xy, dtype=np.float64)):
        displacement = points - edge_point
        distance2 = np.sum(displacement * displacement, axis=1)
        if not np.any(distance2 <= radius2):
            continue
        edge_normal = np.asarray(edge_normals[edge_index], dtype=np.float64)
        nearest_any = int(np.argmin(distance2))
        reverse_metric_boundary.append(nearest_any)
        reverse_metric_normal.append(edge_normal)
        reverse_metric_edge.append(edge_index)
        dot = normals @ edge_normal
        aligned = np.abs(dot) >= cosine
        oriented_edge_normal = edge_normal * np.where(
            dot < 0.0, -1.0, 1.0
        )[:, None]
        normal_distance = np.sum(displacement * oriented_edge_normal, axis=1)
        tangent_vector = np.column_stack(
            [-oriented_edge_normal[:, 1], oriented_edge_normal[:, 0]]
        )
        tangent_distance = np.abs(
            np.sum(displacement * tangent_vector, axis=1)
        )
        candidates = np.flatnonzero(
            aligned
            & (distance2 <= radius2)
            & (tangent_distance <= tangent_limit)
        )
        if not len(candidates):
            reverse_censored.append(float(cfg["edge_search_radius_px"]))
            continue
        best = min(
            candidates,
            key=lambda value: (float(distance2[value]), int(value)),
        )
        reverse_boundary.append(int(best))
        reverse_edge.append(edge_index)
        reverse_signed.append(float(normal_distance[best]))
        reverse_censored.append(abs(float(normal_distance[best])))
    reverse_count = len(reverse_boundary)
    reverse_eligible = len(reverse_censored)
    return {
        "boundary_index": np.asarray(matched_boundary, dtype=np.int64),
        "edge_index": np.asarray(matched_edge, dtype=np.int64),
        "signed_normal_px": np.asarray(signed, dtype=np.float64),
        "distance_px": np.abs(np.asarray(signed, dtype=np.float64)),
        "distance_px_all": censored,
        "euclidean_px": np.asarray(euclidean, dtype=np.float64),
        "edge_normal": (
            np.asarray(oriented_normals, dtype=np.float64)
            if oriented_normals
            else np.zeros((0, 2), dtype=np.float64)
        ),
        "matched_count": count,
        "matched_fraction": count / max(1, len(points)),
        "reverse_boundary_index": np.asarray(
            reverse_boundary, dtype=np.int64
        ),
        "reverse_edge_index": np.asarray(reverse_edge, dtype=np.int64),
        "reverse_metric_boundary_index": np.asarray(
            reverse_metric_boundary, dtype=np.int64
        ),
        "reverse_metric_edge_normal": np.asarray(
            reverse_metric_normal, dtype=np.float64
        ),
        "reverse_metric_edge_index": np.asarray(
            reverse_metric_edge, dtype=np.int64
        ),
        "reverse_signed_normal_px": np.asarray(
            reverse_signed, dtype=np.float64
        ),
        "reverse_distance_px_all": np.asarray(
            reverse_censored, dtype=np.float64
        ),
        "reverse_matched_count": reverse_count,
        "reverse_eligible_count": reverse_eligible,
        "reverse_matched_fraction": reverse_count / max(1, reverse_eligible),
    }


def translation_multi_hypothesis_diagnostic(
    boundary_uv: np.ndarray,
    strength_image: np.ndarray,
    cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """Result-blind separated translation hypotheses; never a residual metric."""

    points = np.asarray(boundary_uv, dtype=np.float64)
    strength = np.asarray(strength_image, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or not len(points):
        raise GateContractError("translation diagnostic requires boundary points")
    if strength.ndim != 2 or not np.isfinite(strength).all():
        raise GateContractError("translation diagnostic strength image is invalid")
    radius = int(cfg["translation_diagnostic_search_radius_px"])
    coarse_step = int(cfg["translation_diagnostic_coarse_step_px"])
    fine_radius = int(cfg["translation_diagnostic_fine_radius_px"])
    top_count = int(cfg["translation_diagnostic_top_seed_count"])
    minimum_support = float(
        cfg["translation_diagnostic_minimum_boundary_support_fraction"]
    )
    separation = float(
        cfg["translation_diagnostic_minimum_hypothesis_separation_px"]
    )
    minimum_margin = float(
        cfg["translation_diagnostic_minimum_relative_margin"]
    )
    if (
        radius <= 0
        or coarse_step <= 0
        or fine_radius < 1
        or top_count < 1
        or not 0.0 < minimum_support <= 1.0
    ):
        raise GateContractError("translation diagnostic locks are invalid")

    height, width = strength.shape

    def response(dx: float, dy: float) -> tuple[float, float]:
        shifted = points + np.array([dx, dy], dtype=np.float64)
        inside = (
            (shifted[:, 0] >= 0.0)
            & (shifted[:, 0] < width - 1.0)
            & (shifted[:, 1] >= 0.0)
            & (shifted[:, 1] < height - 1.0)
        )
        support = float(np.mean(inside))
        if support < minimum_support:
            return float("-inf"), support
        values = _bilinear(
            strength, shifted[inside, 0], shifted[inside, 1]
        )
        # Mean preserves support for full building boundaries and is independent
        # of any post-hoc match or residual threshold.
        return float(np.mean(values)), support

    coarse_values = list(range(-radius, radius + 1, coarse_step))
    if coarse_values[-1] != radius:
        coarse_values.append(radius)
    coarse: list[tuple[float, int, int, float]] = []
    for dy in coarse_values:
        for dx in coarse_values:
            score, support = response(float(dx), float(dy))
            if np.isfinite(score):
                coarse.append((score, dx, dy, support))
    if not coarse:
        return {
            "dx_px": 0.0,
            "dy_px": 0.0,
            "score": None,
            "second_score": None,
            "relative_margin": 0.0,
            "support_fraction": 0.0,
            "ambiguous": True,
            "border_hit": True,
        }
    coarse.sort(key=lambda item: (-item[0], item[2], item[1]))
    seeds: list[tuple[float, int, int, float]] = []
    for item in coarse:
        if all(
            math.hypot(item[1] - prior[1], item[2] - prior[2])
            >= coarse_step
            for prior in seeds
        ):
            seeds.append(item)
            if len(seeds) == top_count:
                break
    fine: dict[tuple[int, int], tuple[float, float]] = {}
    for _score, seed_x, seed_y, _support in seeds:
        for dy in range(
            max(-radius, seed_y - fine_radius),
            min(radius, seed_y + fine_radius) + 1,
        ):
            for dx in range(
                max(-radius, seed_x - fine_radius),
                min(radius, seed_x + fine_radius) + 1,
            ):
                if (dx, dy) not in fine:
                    fine[(dx, dy)] = response(float(dx), float(dy))
    ranked = sorted(
        (
            (score, dx, dy, support)
            for (dx, dy), (score, support) in fine.items()
            if np.isfinite(score)
        ),
        key=lambda item: (-item[0], item[2], item[1]),
    )
    if not ranked:
        raise GateContractError("translation diagnostic fine search has no support")
    best_score, best_x, best_y, best_support = ranked[0]

    def parabolic_offset(
        negative: float, center: float, positive: float
    ) -> float:
        denominator = negative - 2.0 * center + positive
        if not np.isfinite([negative, center, positive]).all() or denominator >= -1e-12:
            return 0.0
        return float(
            np.clip(
                0.5 * (negative - positive) / denominator,
                -0.5,
                0.5,
            )
        )

    center_score = best_score
    left = fine.get((best_x - 1, best_y), (float("-inf"), 0.0))[0]
    right = fine.get((best_x + 1, best_y), (float("-inf"), 0.0))[0]
    up = fine.get((best_x, best_y - 1), (float("-inf"), 0.0))[0]
    down = fine.get((best_x, best_y + 1), (float("-inf"), 0.0))[0]
    sub_x = parabolic_offset(left, center_score, right)
    sub_y = parabolic_offset(up, center_score, down)
    refined_x = float(best_x) + sub_x
    refined_y = float(best_y) + sub_y
    second = next(
        (
            item
            for item in ranked[1:]
            if math.hypot(item[1] - refined_x, item[2] - refined_y)
            >= separation
        ),
        None,
    )
    second_score = float(second[0]) if second is not None else None
    if second_score is None:
        relative_margin = float("inf")
    else:
        relative_margin = float(
            (best_score - second_score) / max(abs(best_score), 1e-12)
        )
    border_hit = bool(
        abs(refined_x) >= radius - 0.5 or abs(refined_y) >= radius - 0.5
    )
    ambiguous = bool(
        best_score <= 0.0
        or best_support < minimum_support
        or relative_margin < minimum_margin
    )
    return {
        "dx_px": refined_x,
        "dy_px": refined_y,
        "score": best_score,
        "second_score": second_score,
        "relative_margin": relative_margin,
        "support_fraction": best_support,
        "ambiguous": ambiguous,
        "border_hit": border_hit,
    }


def robust_translation_fit(
    design: np.ndarray, signed_px: np.ndarray, cfg: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    matrix = np.asarray(design, dtype=np.float64)
    target = np.asarray(signed_px, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != 2 or len(matrix) < 3:
        raise GateContractError("robust XY translation requires at least three observations")
    if np.linalg.matrix_rank(matrix) < 2:
        raise GateContractError("normal observations do not constrain both XY axes")
    condition = float(np.linalg.cond(matrix))
    maximum_condition = float(cfg["maximum_robust_design_condition"])
    if not np.isfinite(condition) or condition > maximum_condition:
        raise GateContractError(
            f"robust translation design condition {condition:.3f} exceeds lock"
        )
    estimate = np.linalg.lstsq(matrix, target, rcond=None)[0]
    delta = float(cfg["robust_fit_huber_delta_px"])
    converged = False
    iteration_count = 0
    weighted_condition = condition
    for iteration_count in range(1, int(cfg["robust_fit_max_iterations"]) + 1):
        residual = target - matrix @ estimate
        absolute = np.abs(residual)
        weights = np.ones(len(residual), dtype=np.float64)
        outlier = absolute > delta
        weights[outlier] = delta / np.maximum(absolute[outlier], 1e-12)
        weighted = matrix * np.sqrt(weights)[:, None]
        weighted_target = target * np.sqrt(weights)
        weighted_condition = float(np.linalg.cond(weighted))
        if not np.isfinite(weighted_condition) or weighted_condition > maximum_condition:
            raise GateContractError(
                "robust weighted translation design became ill-conditioned"
            )
        updated = np.linalg.lstsq(weighted, weighted_target, rcond=None)[0]
        if np.linalg.norm(updated - estimate) <= float(
            cfg["robust_fit_convergence_m"]
        ):
            estimate = updated
            converged = True
            break
        estimate = updated
    if not converged:
        raise GateContractError("robust translation IRLS did not converge")
    return estimate, target - matrix @ estimate, {
        "converged": True,
        "iterations": iteration_count,
        "design_condition": condition,
        "weighted_design_condition": weighted_condition,
    }


def deterministic_spatial_null(
    observed_median: float,
    boundary_uv: np.ndarray,
    boundary_normals: np.ndarray,
    edge_xy: np.ndarray,
    edge_normals: np.ndarray,
    alignment_cfg: Mapping[str, Any],
    confidence_cfg: Mapping[str, Any],
    crop_shape: Sequence[int],
) -> dict[str, Any]:
    medians: list[float] = []
    count = int(confidence_cfg["deterministic_null_angles_per_radius"])
    for radius in confidence_cfg["deterministic_null_shift_radii_px"]:
        for angle_index in range(count):
            angle = 2.0 * math.pi * angle_index / count
            offset = np.array(
                [float(radius) * math.cos(angle), float(radius) * math.sin(angle)]
            )
            shifted = boundary_uv + offset
            height, width = int(crop_shape[0]), int(crop_shape[1])
            if not np.all(
                (shifted[:, 0] >= 0.0)
                & (shifted[:, 0] < width)
                & (shifted[:, 1] >= 0.0)
                & (shifted[:, 1] < height)
            ):
                continue
            match = match_oriented_edges(
                boundary_uv,
                boundary_normals,
                edge_xy,
                edge_normals,
                alignment_cfg,
                offset,
            )
            if float(match["matched_fraction"]) >= float(
                alignment_cfg["minimum_oriented_match_fraction"]
            ):
                distances = np.asarray(match["distance_px_all"], dtype=np.float64)
                if len(distances):
                    medians.append(float(np.median(distances)))
    minimum = int(confidence_cfg["minimum_valid_null_trials"])
    if len(medians) < minimum:
        return {
            "valid_trials": len(medians),
            "pvalue": None,
            "null_q10_median_px": None,
            "separation_px": None,
            "passed": False,
            "reason": "insufficient_valid_spatial_null_trials",
        }
    values = np.asarray(medians, dtype=np.float64)
    pvalue = float((1 + np.sum(values <= observed_median)) / (1 + len(values)))
    q10 = float(np.quantile(values, 0.10))
    separation = q10 - observed_median
    passed = bool(
        pvalue <= float(confidence_cfg["maximum_spatial_null_pvalue"])
        and separation >= float(confidence_cfg["minimum_null_median_separation_px"])
    )
    return {
        "valid_trials": len(values),
        "pvalue": pvalue,
        "null_q10_median_px": q10,
        "separation_px": separation,
        "passed": passed,
        "reason": "ok" if passed else "spatial_null_confidence_not_met",
    }


def xy_projection_jacobian(
    target_xyz: np.ndarray,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    xy_shift: Sequence[float],
    step_m: float,
) -> tuple[np.ndarray, float]:
    point = np.asarray(target_xyz, dtype=np.float64)
    columns: list[np.ndarray] = []
    for axis in (0, 1):
        plus = point.copy()
        minus = point.copy()
        plus[axis] += step_m
        minus[axis] -= step_m
        uv_plus, front_plus = project_base_points(
            plus[None],
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
        )
        uv_minus, front_minus = project_base_points(
            minus[None],
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
        )
        if (
            not front_plus[0]
            or not front_minus[0]
            or not np.isfinite(uv_plus[0]).all()
            or not np.isfinite(uv_minus[0]).all()
        ):
            raise GateContractError("target centroid is not projectable for XY Jacobian")
        columns.append((uv_plus[0] - uv_minus[0]) / (2.0 * step_m))
    jacobian = np.column_stack(columns)
    condition = float(np.linalg.cond(jacobian))
    return jacobian, condition


def xy_projection_jacobians(
    points_xyz: np.ndarray,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    xy_shift: Sequence[float],
    step_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Finite-difference d(image uv)/d(E,N) independently at every point."""

    points = np.asarray(points_xyz, dtype=np.float64)
    jacobians = np.empty((len(points), 2, 2), dtype=np.float64)
    for axis in (0, 1):
        plus = points.copy()
        minus = points.copy()
        plus[:, axis] += step_m
        minus[:, axis] -= step_m
        uv_plus, front_plus = project_base_points(
            plus,
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
        )
        uv_minus, front_minus = project_base_points(
            minus,
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
        )
        good = (
            front_plus
            & front_minus
            & np.isfinite(uv_plus).all(axis=1)
            & np.isfinite(uv_minus).all(axis=1)
        )
        if not np.all(good):
            raise GateContractError(
                "a visible eave point is not projectable for pointwise XY Jacobian"
            )
        jacobians[:, :, axis] = (uv_plus - uv_minus) / (2.0 * step_m)
    conditions = np.asarray(
        [np.linalg.cond(jacobian) for jacobian in jacobians],
        dtype=np.float64,
    )
    return jacobians, conditions


def direct_edge_distance_metric(
    match: Mapping[str, Any],
    jacobians: np.ndarray,
    boundary_normals: np.ndarray,
    alignment_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert direct edge distances with the locked pointwise Jacobian norm.

    Matched points use the actual oriented image-edge normal. Unmatched ALS
    boundary points retain the locked search radius. Every pixel distance is
    divided by ``||n.T @ J_xy||_2`` at its actual ALS source. The forward
    ALS-boundary-to-image-edge distribution is the primary metric; reverse
    image-edge support remains a validity diagnostic only.
    """

    matrices = np.asarray(jacobians, dtype=np.float64)
    normals = np.asarray(boundary_normals, dtype=np.float64).copy()
    if matrices.ndim != 3 or matrices.shape[1:] != (2, 2):
        raise GateContractError("pointwise XY Jacobians must have shape (N,2,2)")
    if normals.shape != (len(matrices), 2):
        raise GateContractError("boundary normals must have shape (N,2)")
    boundary_indices = np.asarray(match["boundary_index"], dtype=np.int64)
    edge_normals = np.asarray(match["edge_normal"], dtype=np.float64)
    if edge_normals.shape != (len(boundary_indices), 2):
        raise GateContractError("matched edge normals do not align with indices")
    if np.any(boundary_indices < 0) or np.any(boundary_indices >= len(matrices)):
        raise GateContractError("matched boundary index is out of range")
    normals[boundary_indices] = edge_normals
    design = np.einsum("nui,nu->ni", matrices, normals)
    sensitivity = np.linalg.norm(design, axis=1)
    minimum = float(alignment_cfg["minimum_normal_sensitivity_px_per_m"])
    if (
        not np.isfinite(sensitivity).all()
        or np.any(sensitivity < minimum)
    ):
        raise GateContractError("pointwise normal XY sensitivity below lock")
    distance_px = np.asarray(match["distance_px_all"], dtype=np.float64)
    if distance_px.shape != (len(matrices),):
        raise GateContractError("forward distance vector must cover every boundary point")
    if not np.isfinite(distance_px).all() or np.any(distance_px < 0):
        raise GateContractError("forward distances must be finite and non-negative")
    distance_m = distance_px / sensitivity
    reverse_px = np.asarray(
        match["reverse_distance_px_all"], dtype=np.float64
    )
    reverse_boundary = np.asarray(
        match["reverse_metric_boundary_index"], dtype=np.int64
    )
    reverse_normals = np.asarray(
        match["reverse_metric_edge_normal"], dtype=np.float64
    )
    if not len(reverse_px):
        reverse_px = np.asarray(
            [float(alignment_cfg["edge_search_radius_px"])],
            dtype=np.float64,
        )
        reverse_boundary = np.asarray(
            [int(np.argmin(distance_px))], dtype=np.int64
        )
        reverse_normals = normals[reverse_boundary]
    if (
        reverse_px.shape != (len(reverse_boundary),)
        or reverse_normals.shape != (len(reverse_boundary), 2)
        or np.any(reverse_boundary < 0)
        or np.any(reverse_boundary >= len(matrices))
    ):
        raise GateContractError("reverse metric correspondence vectors disagree")
    reverse_design = np.einsum(
        "nui,nu->ni", matrices[reverse_boundary], reverse_normals
    )
    reverse_sensitivity = np.linalg.norm(reverse_design, axis=1)
    if (
        not np.isfinite(reverse_sensitivity).all()
        or np.any(reverse_sensitivity < minimum)
    ):
        raise GateContractError(
            "reverse pointwise normal XY sensitivity below lock"
        )
    reverse_m = reverse_px / reverse_sensitivity
    forward_median_px = float(np.median(distance_px))
    forward_p90_px = float(np.percentile(distance_px, 90))
    forward_median_m = float(np.median(distance_m))
    forward_p90_m = float(np.percentile(distance_m, 90))
    reverse_median_px = float(np.median(reverse_px))
    reverse_p90_px = float(np.percentile(reverse_px, 90))
    reverse_median_m = float(np.median(reverse_m))
    reverse_p90_m = float(np.percentile(reverse_m, 90))
    return {
        "metric_normals": normals,
        "design": design,
        "sensitivity_px_per_m": sensitivity,
        "distance_px": distance_px,
        "distance_m": distance_m,
        "reverse_sensitivity_px_per_m": reverse_sensitivity,
        "reverse_distance_px": reverse_px,
        "reverse_distance_m": reverse_m,
        "forward_median_px": forward_median_px,
        "forward_p90_px": forward_p90_px,
        "forward_median_m": forward_median_m,
        "forward_p90_m": forward_p90_m,
        "reverse_median_px": reverse_median_px,
        "reverse_p90_px": reverse_p90_px,
        "reverse_median_m": reverse_median_m,
        "reverse_p90_m": reverse_p90_m,
        "median_px": forward_median_px,
        "p90_px": forward_p90_px,
        "median_m": forward_median_m,
        "p90_m": forward_p90_m,
        "metre_denominator_formula": "||n^T J_xy||_2",
        "primary_direction": "als_boundary_to_image_edge",
        "reverse_role": "validity_diagnostic_only",
    }


def _blank_measurement_row(
    view: SelectedView,
    attempt: str,
    reason: str,
    cloud: TargetCloud,
    datum_config_path: Path,
    geoid_m: float,
    xy_shift: Sequence[float],
    pose_source: Path,
    pose_sha256: str,
    camera_source: Path,
    camera_sha256: str,
) -> dict[str, Any]:
    return {
        "building_id": view.building_id,
        "attempt": attempt,
        "is_final": CSV_FALSE,
        "diagnostic_only": CSV_TRUE,
        "view_order": view.order,
        "view": view.name,
        "registration_split": view.registration_split,
        "valid": CSV_FALSE,
        "registration_usable": CSV_FALSE,
        "status_reason": reason,
        "median_residual_px": "",
        "p90_residual_px": "",
        "median_residual_m": "",
        "p90_residual_m": "",
        "residual_px": "",
        "residual_m": "",
        "registration_candidate_e_m": "",
        "registration_candidate_n_m": "",
        "registration_candidate_norm_m": "",
        "equivalent_dE_m": "",
        "equivalent_dN_m": "",
        "coherent_fit_median_abs_error_px": "",
        "coherent_fit_p90_abs_error_px": "",
        "edge_localization_uncertainty_p90_m": "",
        "forward_median_residual_px": "",
        "forward_p90_residual_px": "",
        "reverse_median_residual_px": "",
        "reverse_p90_residual_px": "",
        "forward_median_residual_m": "",
        "forward_p90_residual_m": "",
        "reverse_median_residual_m": "",
        "reverse_p90_residual_m": "",
        "translation_diagnostic_dx_px": "",
        "translation_diagnostic_dy_px": "",
        "translation_diagnostic_relative_margin": "",
        "translation_diagnostic_ambiguous": "",
        "translation_diagnostic_border_hit": "",
        "spatial_null_pvalue": "",
        "spatial_null_q10_median_px": "",
        "spatial_null_separation_px": "",
        "spatial_null_valid_trials": "",
        "building_median_m": "",
        "building_p90_m": "",
        "building_median_px": "",
        "building_p90_px": "",
        "n_selected_views": "",
        "n_valid_views": "",
        "n_als_class6_total": len(cloud.building_xyz),
        "n_als_class6_inframe": "",
        "n_als_class2_total": len(cloud.ground_xyz),
        "n_als_class2_inframe": "",
        "n_boundary": "",
        "n_boundary_source": "",
        "n_boundary_matched": "",
        "boundary_visible_fraction": "",
        "oriented_match_fraction": "",
        "reverse_match_fraction": "",
        "n_edge_points": "",
        "edge_high_threshold": "",
        "edge_low_threshold": "",
        "xy_jacobian_condition_median": "",
        "xy_jacobian_condition_max": "",
        "normal_sensitivity_px_per_m_median": "",
        "view_nadir_deg": _fmt_float(view.view_nadir_deg, 6),
        "frame_radius": _fmt_float(view.frame_radius, 6),
        "observability_p90_m_per_px": _fmt_float(
            view.observability_p90_m_per_px, 6
        ),
        "predicted_metric_uncertainty_m": _fmt_float(
            view.predicted_metric_uncertainty_m, 6
        ),
        "azimuth_bin": view.azimuth_bin,
        "micro_shift_e_m": _fmt_float(float(xy_shift[0]), 6),
        "micro_shift_n_m": _fmt_float(float(xy_shift[1]), 6),
        "micro_shift_norm_m": _fmt_float(
            math.hypot(float(xy_shift[0]), float(xy_shift[1])), 6
        ),
        "crs": "EPSG:25832",
        "input_vertical_datum": "orthometric",
        "orthometric_geoid_m": _fmt_float(geoid_m, 6),
        "projection_datum_config": repo_relative(datum_config_path),
        "pose_source": repo_relative(pose_source),
        "pose_sha256": pose_sha256,
        "camera_source": repo_relative(camera_source),
        "camera_sha256": camera_sha256,
        "footprint_source_kind": "lod2_groundsurface_xy_scoped_exception",
        "footprint_gt_derived": CSV_TRUE,
        "gt_xy_exception_used": CSV_TRUE,
        "als_classes_used": "2;6",
        "edge_residual_driver": "visible_eave_direct_signed_normal_point_to_edge",
        "als_class2_role": "projected_ground_context_and_class_contract_audit",
        "forbidden_gt_used": CSV_FALSE,
        "lod2_z_used": CSV_FALSE,
        "roofsurface_used": CSV_FALSE,
        "roof_type_used": CSV_FALSE,
        "semantic_class_used": CSV_FALSE,
        "final_roof_model_used": CSV_FALSE,
    }


def _fmt_float(value: float, digits: int = 6) -> str:
    if not np.isfinite(value):
        return ""
    return f"{float(value):.{digits}f}"


def measure_view(
    view: SelectedView,
    cloud: TargetCloud,
    image: ColmapImage,
    camera: Camera,
    image_path: Path,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    datum_config_path: Path,
    boundary_cfg: Mapping[str, Any],
    edge_cfg: Mapping[str, Any],
    alignment_cfg: Mapping[str, Any],
    confidence_cfg: Mapping[str, Any],
    xy_shift: Sequence[float],
    attempt: str,
    pose_source: Path,
    pose_sha256: str,
    camera_source: Path,
    camera_sha256: str,
) -> dict[str, Any]:
    row = _blank_measurement_row(
        view,
        attempt,
        "unmeasured",
        cloud,
        datum_config_path,
        geoid_m,
        xy_shift,
        pose_source,
        pose_sha256,
        camera_source,
        camera_sha256,
    )
    try:
        building_uv, building_front = project_base_points(
            cloud.building_xyz,
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
        )
        ground_uv, ground_front = project_base_points(
            cloud.ground_xyz,
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
        )
        building_inframe = (
            building_front
            & (building_uv[:, 0] >= 0)
            & (building_uv[:, 0] < camera.width)
            & (building_uv[:, 1] >= 0)
            & (building_uv[:, 1] < camera.height)
        )
        ground_inframe = (
            ground_front
            & (ground_uv[:, 0] >= 0)
            & (ground_uv[:, 0] < camera.width)
            & (ground_uv[:, 1] >= 0)
            & (ground_uv[:, 1] < camera.height)
        )
        boundary = visible_eave_boundary(
            cloud,
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
            boundary_cfg,
        )
        maximum_null = max(
            map(float, confidence_cfg["deterministic_null_shift_radii_px"])
        )
        pad = int(math.ceil(float(alignment_cfg["edge_search_radius_px"]) + maximum_null + 8))
        x0 = max(0, int(math.floor(float(np.min(boundary.uv[:, 0])) - pad)))
        y0 = max(0, int(math.floor(float(np.min(boundary.uv[:, 1])) - pad)))
        x1 = min(
            camera.width,
            int(math.ceil(float(np.max(boundary.uv[:, 0])) + pad + 1)),
        )
        y1 = min(
            camera.height,
            int(math.ceil(float(np.max(boundary.uv[:, 1])) + pad + 1)),
        )
        if x1 - x0 < 32 or y1 - y0 < 32:
            raise GateContractError("projected ALS crop is too small")
        with Image.open(image_path) as pil:
            pil = pil.convert("RGB")
            if pil.size != (camera.width, camera.height):
                raise GateContractError(
                    f"training image size {pil.size} != COLMAP "
                    f"{(camera.width, camera.height)}"
                )
            rgb_crop = np.asarray(pil)[y0:y1, x0:x1]
        gray = rgb_crop.astype(np.float32) @ np.array(
            [0.299, 0.587, 0.114], dtype=np.float32
        )
        edge_xy, edge_normals, edge_info = extract_subpixel_edges(gray, edge_cfg)
        boundary_local = boundary.uv - np.array([x0, y0], dtype=np.float64)
        match = match_oriented_edges(
            boundary_local,
            boundary.normal_uv,
            edge_xy,
            edge_normals,
            alignment_cfg,
        )
        jacobians, conditions = xy_projection_jacobians(
            boundary.xyz,
            image,
            camera,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
            float(alignment_cfg["xy_jacobian_step_m"]),
        )
        if not np.isfinite(conditions).all() or np.max(conditions) > float(
            alignment_cfg["maximum_xy_jacobian_condition"]
        ):
            raise GateContractError(
                "one or more pointwise XY projection Jacobians are ill-conditioned"
            )
        metric = direct_edge_distance_metric(
            match,
            jacobians,
            boundary.normal_uv,
            alignment_cfg,
        )
        boundary_indices = np.asarray(match["boundary_index"], dtype=np.int64)
        sensitivity = np.asarray(
            metric["sensitivity_px_per_m"], dtype=np.float64
        )
        median_px = float(metric["median_px"])
        p90_px = float(metric["p90_px"])
        median_m = float(metric["median_m"])
        p90_m = float(metric["p90_m"])
        forward_median_px = float(metric["forward_median_px"])
        forward_p90_px = float(metric["forward_p90_px"])
        reverse_median_px = float(metric["reverse_median_px"])
        reverse_p90_px = float(metric["reverse_p90_px"])
        forward_median_m = float(metric["forward_median_m"])
        forward_p90_m = float(metric["forward_p90_m"])
        reverse_median_m = float(metric["reverse_median_m"])
        reverse_p90_m = float(metric["reverse_p90_m"])
        matched_design = np.asarray(metric["design"], dtype=np.float64)[
            boundary_indices
        ]
        signed_px = np.asarray(match["signed_normal_px"], dtype=np.float64)
        candidate, fit_residual, fit_info = robust_translation_fit(
            matched_design, signed_px, alignment_cfg
        )
        coherent_median = float(np.median(np.abs(fit_residual)))
        coherent_p90 = float(np.percentile(np.abs(fit_residual), 90))
        edge_sigma = np.asarray(
            edge_info["localization_sigma_px"], dtype=np.float64
        )
        forward_edge_indices = np.asarray(
            match["edge_index"], dtype=np.int64
        )
        forward_sigma_m = (
            edge_sigma[forward_edge_indices] / sensitivity[boundary_indices]
        )
        reverse_edge_indices = np.asarray(
            match["reverse_metric_edge_index"], dtype=np.int64
        )
        reverse_sigma_m = (
            edge_sigma[reverse_edge_indices]
            / np.asarray(
                metric["reverse_sensitivity_px_per_m"], dtype=np.float64
            )
        )
        localization_sigma_m = np.concatenate(
            [forward_sigma_m, reverse_sigma_m]
        )
        localization_uncertainty_p90_m = float(
            np.percentile(localization_sigma_m, 90)
        )
        diagnostic = translation_multi_hypothesis_diagnostic(
            boundary_local,
            np.asarray(edge_info["strength_image"], dtype=np.float64),
            confidence_cfg,
        )
        null = deterministic_spatial_null(
            median_px,
            boundary_local,
            boundary.normal_uv,
            edge_xy,
            edge_normals,
            alignment_cfg,
            confidence_cfg,
            gray.shape,
        )
        reasons: list[str] = []
        if float(match["matched_fraction"]) < float(
            alignment_cfg["minimum_oriented_match_fraction"]
        ):
            reasons.append("oriented_edge_match_fraction_below_lock")
        if float(match["reverse_matched_fraction"]) < float(
            alignment_cfg["minimum_reverse_match_fraction"]
        ):
            reasons.append("reverse_edge_match_fraction_below_lock")
        if localization_uncertainty_p90_m > float(
            confidence_cfg["maximum_edge_localization_uncertainty_p90_m"]
        ):
            reasons.append("edge_localization_uncertainty_p90_m_above_lock")
        if p90_px - median_px > float(
            confidence_cfg["maximum_view_p90_minus_median_px"]
        ):
            reasons.append("view_p90_minus_median_px_above_lock")
        if bool(diagnostic["ambiguous"]):
            reasons.append("translation_diagnostic_ambiguous")
        if bool(diagnostic["border_hit"]):
            reasons.append("translation_diagnostic_search_border_hit")
        if not bool(null["passed"]):
            reasons.append(str(null["reason"]))
        if coherent_median > float(
            confidence_cfg["coherent_fit_median_abs_error_max_px"]
        ):
            reasons.append("normal_equation_median_coherence_above_lock")
        if coherent_p90 > float(
            confidence_cfg["coherent_fit_p90_abs_error_max_px"]
        ):
            reasons.append("normal_equation_p90_coherence_above_lock")
        registration_usable = bool(
            float(match["matched_fraction"])
            >= float(alignment_cfg["minimum_oriented_match_fraction"])
            and float(match["reverse_matched_fraction"])
            >= float(alignment_cfg["minimum_reverse_match_fraction"])
            and coherent_median
            <= float(confidence_cfg["coherent_fit_median_abs_error_max_px"])
            and coherent_p90
            <= float(confidence_cfg["coherent_fit_p90_abs_error_max_px"])
            and not bool(diagnostic["ambiguous"])
            and not bool(diagnostic["border_hit"])
        )
        valid = not reasons
        row.update(
            {
                "valid": CSV_TRUE if valid else CSV_FALSE,
                "status_reason": "ok" if valid else ";".join(reasons),
                "registration_usable": (
                    CSV_TRUE if registration_usable else CSV_FALSE
                ),
                "median_residual_px": _fmt_float(median_px, 6),
                "p90_residual_px": _fmt_float(p90_px, 6),
                "median_residual_m": _fmt_float(median_m, 6),
                "p90_residual_m": _fmt_float(p90_m, 6),
                # Compatibility aliases are the same signed-normal medians;
                # neither is a translation magnitude.
                "residual_px": _fmt_float(median_px, 6),
                "residual_m": _fmt_float(median_m, 6),
                "registration_candidate_e_m": _fmt_float(float(candidate[0]), 6),
                "registration_candidate_n_m": _fmt_float(float(candidate[1]), 6),
                "registration_candidate_norm_m": _fmt_float(
                    float(np.linalg.norm(candidate)), 6
                ),
                "equivalent_dE_m": _fmt_float(float(candidate[0]), 6),
                "equivalent_dN_m": _fmt_float(float(candidate[1]), 6),
                "coherent_fit_median_abs_error_px": _fmt_float(
                    coherent_median, 6
                ),
                "coherent_fit_p90_abs_error_px": _fmt_float(coherent_p90, 6),
                "edge_localization_uncertainty_p90_m": _fmt_float(
                    localization_uncertainty_p90_m, 6
                ),
                "forward_median_residual_px": _fmt_float(
                    forward_median_px, 6
                ),
                "forward_p90_residual_px": _fmt_float(forward_p90_px, 6),
                "reverse_median_residual_px": _fmt_float(
                    reverse_median_px, 6
                ),
                "reverse_p90_residual_px": _fmt_float(reverse_p90_px, 6),
                "forward_median_residual_m": _fmt_float(
                    forward_median_m, 6
                ),
                "forward_p90_residual_m": _fmt_float(forward_p90_m, 6),
                "reverse_median_residual_m": _fmt_float(
                    reverse_median_m, 6
                ),
                "reverse_p90_residual_m": _fmt_float(reverse_p90_m, 6),
                "translation_diagnostic_dx_px": _fmt_float(
                    float(diagnostic["dx_px"]), 6
                ),
                "translation_diagnostic_dy_px": _fmt_float(
                    float(diagnostic["dy_px"]), 6
                ),
                "translation_diagnostic_relative_margin": _fmt_float(
                    float(diagnostic["relative_margin"]), 6
                ),
                "translation_diagnostic_ambiguous": (
                    CSV_TRUE if diagnostic["ambiguous"] else CSV_FALSE
                ),
                "translation_diagnostic_border_hit": (
                    CSV_TRUE if diagnostic["border_hit"] else CSV_FALSE
                ),
                "spatial_null_pvalue": _fmt_float(
                    float(null["pvalue"])
                    if null["pvalue"] is not None
                    else float("nan"),
                    6,
                ),
                "spatial_null_q10_median_px": _fmt_float(
                    float(null["null_q10_median_px"])
                    if null["null_q10_median_px"] is not None
                    else float("nan"),
                    6,
                ),
                "spatial_null_separation_px": _fmt_float(
                    float(null["separation_px"])
                    if null["separation_px"] is not None
                    else float("nan"),
                    6,
                ),
                "spatial_null_valid_trials": int(null["valid_trials"]),
                "n_als_class6_inframe": int(np.sum(building_inframe)),
                "n_als_class2_inframe": int(np.sum(ground_inframe)),
                "n_boundary": len(boundary.xyz),
                "n_boundary_source": int(boundary.source_count),
                "n_boundary_matched": int(match["matched_count"]),
                "boundary_visible_fraction": _fmt_float(
                    boundary.visible_fraction, 6
                ),
                "oriented_match_fraction": _fmt_float(
                    float(match["matched_fraction"]), 6
                ),
                "reverse_match_fraction": _fmt_float(
                    float(match["reverse_matched_fraction"]), 6
                ),
                "n_edge_points": int(edge_info["edge_point_count"]),
                "edge_high_threshold": _fmt_float(
                    float(edge_info["high_threshold"]), 6
                ),
                "edge_low_threshold": _fmt_float(
                    float(edge_info["low_threshold"]), 6
                ),
                "xy_jacobian_condition_median": _fmt_float(
                    float(np.median(conditions)), 6
                ),
                "xy_jacobian_condition_max": _fmt_float(
                    float(np.max(conditions)), 6
                ),
                "normal_sensitivity_px_per_m_median": _fmt_float(
                    float(np.median(sensitivity)),
                    6,
                ),
                "_normal_design": matched_design,
                "_signed_normal_px": signed_px,
                "_robust_fit": fit_info,
                "_boundary_source_index": boundary.source_index,
            }
        )
    except Exception as exc:
        row["valid"] = CSV_FALSE
        row["status_reason"] = f"{type(exc).__name__}:{exc}"
    return row


def rows_by_building(
    rows: Sequence[Mapping[str, Any]]
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["building_id"]), []).append(row)
    return grouped


def _valid_vectors(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    vectors = [
        [float(row["equivalent_dE_m"]), float(row["equivalent_dN_m"])]
        for row in rows
        if row.get("valid") == CSV_TRUE
        and row.get("equivalent_dE_m") not in ("", None)
        and row.get("equivalent_dN_m") not in ("", None)
    ]
    return (
        np.asarray(vectors, dtype=np.float64)
        if vectors
        else np.zeros((0, 2), dtype=np.float64)
    )


def summarize_buildings(
    targets: Sequence[Target],
    rows: list[dict[str, Any]],
    gate_cfg: Mapping[str, Any],
    selection_cfg: Mapping[str, Any],
    attempt: str,
    evaluation_split: str | None = None,
    micro_cfg: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    grouped = rows_by_building(rows)
    summaries: list[dict[str, Any]] = []
    minimum = int(selection_cfg["minimum_views_per_building"])
    maximum = int(selection_cfg["maximum_views_per_building"])
    required_fraction = float(gate_cfg["required_valid_view_fraction"])
    median_limit = float(gate_cfg["building_median_residual_max_m"])
    for target in targets:
        all_building_rows = list(grouped.get(target.building_id, []))
        building_rows = [
            row
            for row in all_building_rows
            if evaluation_split is None
            or row.get("registration_split") == evaluation_split
        ]
        valid_rows = [
            row
            for row in building_rows
            if row.get("valid") == CSV_TRUE
            and row.get("median_residual_m") not in ("", None)
        ]
        residuals = np.asarray(
            [float(row["median_residual_m"]) for row in valid_rows],
            dtype=np.float64,
        )
        residuals_px = np.asarray(
            [float(row["median_residual_px"]) for row in valid_rows],
            dtype=np.float64,
        )
        selected_count = len(building_rows)
        valid_count = len(valid_rows)
        fraction = valid_count / selected_count if selected_count else 0.0
        median = float(np.median(residuals)) if len(residuals) else float("nan")
        p90 = (
            float(np.percentile(residuals, 90))
            if len(residuals)
            else float("nan")
        )
        median_px = (
            float(np.median(residuals_px)) if len(residuals_px) else float("nan")
        )
        p90_px = (
            float(np.percentile(residuals_px, 90))
            if len(residuals_px)
            else float("nan")
        )
        if evaluation_split == "heldout":
            if micro_cfg is None:
                raise GateContractError("held-out summary requires micro config")
            count_ok = selected_count >= int(
                micro_cfg["minimum_heldout_views_per_building"]
            )
        else:
            count_ok = minimum <= selected_count <= maximum
        completeness_ok = count_ok and fraction >= required_fraction
        median_ok = np.isfinite(median) and median <= median_limit
        numeric_pass = bool(completeness_ok and median_ok)
        vectors = _valid_vectors(valid_rows)
        shift = (
            np.median(vectors, axis=0)
            if len(vectors)
            else np.array([np.nan, np.nan])
        )
        summary = {
            "building_id": target.building_id,
            "attempt": attempt,
            "processing_order": target.processing_order,
            "cohort": target.cohort,
            "tier": target.tier,
            "queue_status": target.queue_status,
            "cohort_resolution_status": target.cohort_resolution_status,
            "selected_view_count": selected_count,
            "selected_view_count_total": len(all_building_rows),
            "evaluation_split": evaluation_split or "all",
            "valid_view_count": valid_count,
            "valid_view_fraction": fraction,
            "median_residual_m": median,
            "p90_residual_m": p90,
            "median_residual_px": median_px,
            "p90_residual_px": p90_px,
            "building_median_limit_m": median_limit,
            "view_count_contract_met": count_ok,
            "all_selected_views_valid": fraction >= required_fraction,
            "building_numeric_gate_met": numeric_pass,
            "equivalent_xy_median_e_m": float(shift[0]),
            "equivalent_xy_median_n_m": float(shift[1]),
            "equivalent_xy_median_norm_m": float(np.linalg.norm(shift)),
            "forbidden_gt_used": False,
        }
        summaries.append(summary)
        for row in all_building_rows:
            row["building_median_m"] = _fmt_float(median, 6)
            row["building_p90_m"] = _fmt_float(p90, 6)
            row["building_median_px"] = _fmt_float(median_px, 6)
            row["building_p90_px"] = _fmt_float(p90_px, 6)
            row["n_selected_views"] = selected_count
            row["n_valid_views"] = valid_count
    return summaries


def systematic_translation(
    rows: Sequence[Mapping[str, Any]],
    gate_cfg: Mapping[str, Any],
    evaluation_split: str | None = None,
) -> dict[str, Any]:
    grouped = {
        building_id: _valid_vectors(
            [
                row
                for row in building_rows
                if evaluation_split is None
                or row.get("registration_split") == evaluation_split
            ]
        )
        for building_id, building_rows in rows_by_building(rows).items()
    }
    grouped = {
        building_id: vectors
        for building_id, vectors in grouped.items()
        if len(vectors)
    }
    building_vectors = (
        np.vstack([np.median(grouped[key], axis=0) for key in sorted(grouped)])
        if grouped
        else np.zeros((0, 2), dtype=np.float64)
    )
    n_views = int(sum(len(value) for value in grouped.values()))
    n_buildings = len(grouped)
    minimum_views = int(gate_cfg["minimum_systematic_valid_views"])
    minimum_buildings = int(gate_cfg["minimum_systematic_valid_buildings"])
    enough = n_views >= minimum_views and n_buildings >= minimum_buildings
    if len(building_vectors):
        estimate = np.median(building_vectors, axis=0)
        estimate_norm = float(np.linalg.norm(estimate))
    else:
        estimate = np.array([np.nan, np.nan])
        estimate_norm = float("nan")
    result: dict[str, Any] = {
        "estimator": gate_cfg["systematic_estimator"],
        "evaluation_split": evaluation_split or "all",
        "building_weighting": "equal_after_per_building_view_median",
        "valid_view_count": n_views,
        "valid_building_count": n_buildings,
        "minimum_valid_views": minimum_views,
        "minimum_valid_buildings": minimum_buildings,
        "global_median_e_m": float(estimate[0]),
        "global_median_n_m": float(estimate[1]),
        "global_median_xy_norm_m": estimate_norm,
        "xy_norm_limit_m": float(gate_cfg["systematic_xy_norm_max_m"]),
        "bootstrap_method": "building_cluster_resample_with_replacement",
        "bootstrap_samples": int(gate_cfg["systematic_bootstrap_samples"]),
        "bootstrap_confidence": float(
            gate_cfg["systematic_bootstrap_confidence"]
        ),
        "bootstrap_ci_low_m": None,
        "bootstrap_ci_upper_m": None,
        "bootstrap_available": False,
        "systematic_negligible": False,
        "reason": "",
    }
    if not enough:
        result["reason"] = "insufficient_valid_views_or_buildings_for_bootstrap"
        return result
    building_ids = sorted(grouped)
    samples = int(gate_cfg["systematic_bootstrap_samples"])
    confidence = float(gate_cfg["systematic_bootstrap_confidence"])
    if samples < 100:
        result["reason"] = "bootstrap_sample_count_below_100"
        return result
    rng = np.random.default_rng(int(gate_cfg["systematic_bootstrap_seed"]))
    norms = np.empty(samples, dtype=np.float64)
    for sample_index in range(samples):
        chosen = rng.integers(0, len(building_ids), size=len(building_ids))
        sample_vectors = np.vstack(
            [
                np.median(grouped[building_ids[int(index)]], axis=0)
                for index in chosen
            ]
        )
        sample_estimate = np.median(sample_vectors, axis=0)
        norms[sample_index] = np.linalg.norm(sample_estimate)
    alpha = (1.0 - confidence) / 2.0
    ci_low = float(np.quantile(norms, alpha))
    ci_upper = float(np.quantile(norms, 1.0 - alpha))
    norm_limit = float(gate_cfg["systematic_xy_norm_max_m"])
    ci_limit = float(gate_cfg["systematic_bootstrap_ci_upper_max_m"])
    negligible = bool(
        np.isfinite(estimate_norm)
        and estimate_norm <= norm_limit
        and ci_upper <= ci_limit
    )
    result.update(
        {
            "bootstrap_ci_low_m": ci_low,
            "bootstrap_ci_upper_m": ci_upper,
            "bootstrap_available": True,
            "systematic_negligible": negligible,
            "reason": "ok" if negligible else "locked_systematic_threshold_not_met",
        }
    )
    return result


def evaluate_gate(
    building_summaries: Sequence[Mapping[str, Any]],
    systematic: Mapping[str, Any],
) -> dict[str, Any]:
    failed = [
        str(row["building_id"])
        for row in building_summaries
        if not bool(row["building_numeric_gate_met"])
    ]
    passed = not failed and bool(systematic["systematic_negligible"])
    return {
        "numeric_gate_met": bool(passed),
        "failed_building_count": len(failed),
        "failed_building_ids": failed,
        "all_requested_buildings_met_0p30m": not failed,
        "systematic_negligible": bool(systematic["systematic_negligible"]),
        "learning_entry_allowed_by_numeric_gate": bool(passed),
        "learning_entry_scope": (
            "numeric_gate_only; GS4 overlap remains unresolved; human judgment unset"
        ),
        "human_research_judgment": None,
    }


def plan_global_micro_shift(
    rows: Sequence[Mapping[str, Any]],
    micro_cfg: Mapping[str, Any],
    alignment_cfg: Mapping[str, Any],
) -> tuple[tuple[float, float] | None, dict[str, Any]]:
    """Fit exactly one cohort-wide shift from deterministic fit views only."""

    fit_rows = [
        row
        for row in rows
        if row.get("registration_split") == "fit"
        and row.get("registration_usable") == CSV_TRUE
        and row.get("registration_candidate_e_m") not in ("", None)
        and row.get("registration_candidate_n_m") not in ("", None)
    ]
    building_ids = sorted({str(row["building_id"]) for row in fit_rows})
    metadata: dict[str, Any] = {
        "fit_view_count": len(fit_rows),
        "fit_building_count": len(building_ids),
        "minimum_fit_views": int(micro_cfg["minimum_fit_views"]),
        "minimum_fit_buildings": int(micro_cfg["minimum_fit_buildings"]),
        "evaluation_split": "fit",
        "same_shift_for_every_building": True,
        "shift": None,
        "reason": "",
    }
    if (
        len(fit_rows) < int(micro_cfg["minimum_fit_views"])
        or len(building_ids) < int(micro_cfg["minimum_fit_buildings"])
    ):
        metadata["reason"] = "insufficient_valid_fit_views_or_buildings"
        return None, metadata
    candidates_by_building: dict[str, list[np.ndarray]] = {}
    for row in fit_rows:
        candidates_by_building.setdefault(str(row["building_id"]), []).append(
            np.array(
                [
                    float(row["registration_candidate_e_m"]),
                    float(row["registration_candidate_n_m"]),
                ],
                dtype=np.float64,
            )
        )
    building_candidates = {
        building_id: np.median(np.vstack(values), axis=0)
        for building_id, values in candidates_by_building.items()
    }
    estimate = np.median(
        np.vstack([building_candidates[key] for key in sorted(building_candidates)]),
        axis=0,
    )
    norm = float(np.linalg.norm(estimate))
    metadata.update(
        {
            "aggregation": "view_robust_candidate_to_building_median_to_equal_building_median",
            "building_candidates": {
                key: {
                    "east_m": float(value[0]),
                    "north_m": float(value[1]),
                    "norm_m": float(np.linalg.norm(value)),
                    "fit_view_count": len(candidates_by_building[key]),
                }
                for key, value in sorted(building_candidates.items())
            },
            "shift": {
                "east_m": float(estimate[0]),
                "north_m": float(estimate[1]),
                "norm_m": norm,
            },
        }
    )
    maximum = float(micro_cfg["maximum_xy_shift_norm_m"])
    if not np.isfinite(norm) or norm > maximum:
        metadata["reason"] = (
            f"global_micro_shift_norm_{norm:.6f}m_exceeds_{maximum:.6f}m"
        )
        return None, metadata
    metadata["reason"] = "ok"
    return (float(estimate[0]), float(estimate[1])), metadata


def _selected_by_building(
    views: Sequence[SelectedView],
) -> dict[str, list[SelectedView]]:
    grouped: dict[str, list[SelectedView]] = {}
    for view in views:
        grouped.setdefault(view.building_id, []).append(view)
    for building_views in grouped.values():
        building_views.sort(key=lambda view: view.order)
    return grouped


def measure_all(
    targets: Sequence[Target],
    views: Sequence[SelectedView],
    clouds: Mapping[str, TargetCloud],
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    datum_config_path: Path,
    boundary_cfg: Mapping[str, Any],
    edge_cfg: Mapping[str, Any],
    alignment_cfg: Mapping[str, Any],
    confidence_cfg: Mapping[str, Any],
    shifts: Mapping[str, tuple[float, float] | None],
    shift_reasons: Mapping[str, str],
    attempt: str,
    pose_source: Path,
    pose_sha256: str,
    camera_source: Path,
    camera_sha256: str,
) -> list[dict[str, Any]]:
    grouped = _selected_by_building(views)
    rows: list[dict[str, Any]] = []
    for target in targets:
        cloud = clouds[target.building_id]
        shift = shifts.get(target.building_id, (0.0, 0.0))
        for view in grouped[target.building_id]:
            if shift is None:
                rows.append(
                    _blank_measurement_row(
                        view,
                        attempt,
                        shift_reasons[target.building_id],
                        cloud,
                        datum_config_path,
                        geoid_m,
                        (0.0, 0.0),
                        pose_source,
                        pose_sha256,
                        camera_source,
                        camera_sha256,
                    )
                )
                continue
            image = images_by_name[view.name]
            camera = cameras[image.camera_id]
            rows.append(
                measure_view(
                    view,
                    cloud,
                    image,
                    camera,
                    image_paths[view.name],
                    scene_reference,
                    input_datum,
                    geoid_m,
                    datum_config_path,
                    boundary_cfg,
                    edge_cfg,
                    alignment_cfg,
                    confidence_cfg,
                    shift,
                    attempt,
                    pose_source,
                    pose_sha256,
                    camera_source,
                    camera_sha256,
                )
            )
        print(
            f"[{attempt}] {target.processing_order:03d} {target.building_id}: "
            f"{len(grouped[target.building_id])} views measured",
            flush=True,
        )
    return rows


def _read_completed_checkpoint_rows(
    store: AlignmentCheckpointStore,
    identity: CheckpointIdentity,
    building_id: str,
    attempt: str,
) -> list[dict[str, Any]]:
    checkpoint = store.verify_completed(identity, building_id, attempt)
    attempt_dir = store.attempt_dir(identity, building_id, attempt)
    record = checkpoint["artifacts"]["residuals_csv"]
    path = attempt_dir / str(record["path"])
    if sha256_file(path) != record["sha256"]:
        raise GateContractError("verified checkpoint residual hash drift")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != RESIDUAL_FIELDS:
            raise GateContractError("checkpoint residual schema drift")
        return [dict(row) for row in reader]


def _representative_overlay_bytes(
    target: Target,
    views: Sequence[SelectedView],
    rows: Sequence[Mapping[str, Any]],
    cloud: TargetCloud,
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    boundary_cfg: Mapping[str, Any],
) -> bytes:
    valid_rows = [
        row
        for row in rows
        if row.get("valid") == CSV_TRUE
        and row.get("median_residual_m") not in ("", None)
    ]
    if valid_rows:
        residuals = np.asarray(
            [float(row["median_residual_m"]) for row in valid_rows]
        )
        centre = float(np.median(residuals))
        chosen_row: Mapping[str, Any] | None = min(
            valid_rows,
            key=lambda row: (
                abs(float(row["median_residual_m"]) - centre),
                int(row["view_order"]),
            ),
        )
    else:
        chosen_row = rows[0] if rows else None
    chosen_view = (
        next(
            (
                view
                for view in views
                if chosen_row is not None and view.name == chosen_row.get("view")
            ),
            None,
        )
        if chosen_row is not None
        else None
    )
    if chosen_view is None:
        image = None
        camera = None
        source_image = None
        shift = (0.0, 0.0)
    else:
        image = images_by_name[chosen_view.name]
        camera = cameras[image.camera_id]
        source_image = image_paths[chosen_view.name]
        shift = (
            float(chosen_row.get("micro_shift_e_m") or 0.0),
            float(chosen_row.get("micro_shift_n_m") or 0.0),
        )
    buffer = io.BytesIO()
    render_overlay(
        buffer,
        target,
        chosen_view,
        chosen_row,
        cloud,
        image,
        camera,
        source_image,
        scene_reference,
        input_datum,
        geoid_m,
        shift,
        boundary_cfg,
    )
    payload = buffer.getvalue()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise GateContractError("representative overlay is not a PNG")
    return payload


def measure_all_checkpointed(
    targets: Sequence[Target],
    views: Sequence[SelectedView],
    clouds: Mapping[str, TargetCloud],
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    datum_config_path: Path,
    boundary_cfg: Mapping[str, Any],
    edge_cfg: Mapping[str, Any],
    alignment_cfg: Mapping[str, Any],
    confidence_cfg: Mapping[str, Any],
    shifts: Mapping[str, tuple[float, float] | None],
    shift_reasons: Mapping[str, str],
    attempt: str,
    pose_source: Path,
    pose_sha256: str,
    camera_source: Path,
    camera_sha256: str,
    checkpoint_store: AlignmentCheckpointStore,
    checkpoint_identity: CheckpointIdentity,
    gate_cfg: Mapping[str, Any],
    selection_cfg: Mapping[str, Any],
    micro_cfg: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[CheckpointRef]]:
    """Measure/resume one building at a time and fsync it before advancing."""

    grouped = _selected_by_building(views)
    all_rows: list[dict[str, Any]] = []
    refs: list[CheckpointRef] = []
    for target in targets:
        building_views = grouped.get(target.building_id, [])
        if not building_views:
            raise GateContractError(
                f"{target.building_id}: selected-view inventory is empty"
            )
        resume = checkpoint_store.resume_status(
            checkpoint_identity, target.building_id, attempt
        )
        stop_stage_after_checkpoint = False
        if resume.state == "completed":
            if (
                resume.checkpoint is None
                or resume.checkpoint.get("overlay_status") != "available"
            ):
                raise GateContractError(
                    f"{target.building_id}: resumed checkpoint has no overlay"
                )
            building_rows = _read_completed_checkpoint_rows(
                checkpoint_store,
                checkpoint_identity,
                target.building_id,
                attempt,
            )
            print(
                f"[{attempt}] {target.processing_order:03d} "
                f"{target.building_id}: resumed durable checkpoint",
                flush=True,
            )
        else:
            building_rows = measure_all(
                [target],
                building_views,
                clouds,
                cameras,
                images_by_name,
                image_paths,
                scene_reference,
                input_datum,
                geoid_m,
                datum_config_path,
                boundary_cfg,
                edge_cfg,
                alignment_cfg,
                confidence_cfg,
                shifts,
                shift_reasons,
                attempt,
                pose_source,
                pose_sha256,
                camera_source,
                camera_sha256,
            )
            exception_rows = [
                row
                for row in building_rows
                if row.get("valid") != CSV_TRUE
                and re.match(r"^[A-Za-z_][A-Za-z0-9_.]*:", str(row.get("status_reason", "")))
            ]
            if exception_rows:
                # The first attempt is already represented by each row. Repeat
                # the same failing view twice so the overnight three-repeat
                # rule is based on actual attempts, not duplicate log entries.
                first = exception_rows[0]
                failing_view = next(
                    item for item in building_views if item.name == first["view"]
                )
                attempts = [first]
                for _retry in range(2):
                    attempts.append(
                        measure_view(
                            failing_view,
                            clouds[target.building_id],
                            images_by_name[failing_view.name],
                            cameras[failing_view.camera_id],
                            image_paths[failing_view.name],
                            scene_reference,
                            input_datum,
                            geoid_m,
                            datum_config_path,
                            boundary_cfg,
                            edge_cfg,
                            alignment_cfg,
                            confidence_cfg,
                            shifts.get(target.building_id) or (0.0, 0.0),
                            attempt,
                            pose_source,
                            pose_sha256,
                            camera_source,
                            camera_sha256,
                        )
                    )
                decision = None
                for failed in attempts:
                    reason = str(failed.get("status_reason", "UnknownError"))
                    error_type = reason.split(":", 1)[0]
                    decision = checkpoint_store.record_error(
                        checkpoint_identity,
                        building_id=target.building_id,
                        attempt=attempt,
                        error_type=error_type,
                        message=reason,
                    )
                assert decision is not None
                stop_stage_after_checkpoint = decision.stop_stage
            else:
                checkpoint_store.mark_building_success(
                    checkpoint_identity, building_id=target.building_id
                )
            summary = summarize_buildings(
                [target],
                building_rows,
                gate_cfg,
                selection_cfg,
                attempt,
                evaluation_split=(
                    "heldout" if attempt == MICRO_ATTEMPT else None
                ),
                micro_cfg=(micro_cfg if attempt == MICRO_ATTEMPT else None),
            )[0]
            checkpoint = checkpoint_store.complete_attempt(
                checkpoint_identity,
                building_id=target.building_id,
                attempt=attempt,
                residual_rows=building_rows,
                residual_fields=RESIDUAL_FIELDS,
                summary=_json_sanitize(summary),
                overlay=lambda: _representative_overlay_bytes(
                    target,
                    building_views,
                    building_rows,
                    clouds[target.building_id],
                    cameras,
                    images_by_name,
                    image_paths,
                    scene_reference,
                    input_datum,
                    geoid_m,
                    boundary_cfg,
                ),
            )
            if checkpoint.get("overlay_status") != "available":
                checkpoint_store.write_blocked_receipt(
                    checkpoint_identity,
                    reason="representative_overlay_failed",
                    details={
                        "building_id": target.building_id,
                        "attempt": attempt,
                        "numeric_evidence_preserved": True,
                    },
                )
                raise GateContractError(
                    f"{target.building_id}: overlay failed; numeric checkpoint "
                    "preserved and Gate A blocked"
                )
        all_rows.extend(building_rows)
        refs.append(CheckpointRef(target.building_id, attempt))
        if stop_stage_after_checkpoint:
            raise GateContractError(
                "same error type reached three consecutive buildings; "
                "durable BLOCKED receipt written"
            )
    return all_rows, refs


RESIDUAL_FIELDS = [
    "building_id",
    "attempt",
    "is_final",
    "view_order",
    "view",
    "registration_split",
    "diagnostic_only",
    "valid",
    "registration_usable",
    "status_reason",
    "median_residual_px",
    "p90_residual_px",
    "median_residual_m",
    "p90_residual_m",
    "residual_px",
    "residual_m",
    "registration_candidate_e_m",
    "registration_candidate_n_m",
    "registration_candidate_norm_m",
    "equivalent_dE_m",
    "equivalent_dN_m",
    "coherent_fit_median_abs_error_px",
    "coherent_fit_p90_abs_error_px",
    "edge_localization_uncertainty_p90_m",
    "forward_median_residual_px",
    "forward_p90_residual_px",
    "reverse_median_residual_px",
    "reverse_p90_residual_px",
    "forward_median_residual_m",
    "forward_p90_residual_m",
    "reverse_median_residual_m",
    "reverse_p90_residual_m",
    "translation_diagnostic_dx_px",
    "translation_diagnostic_dy_px",
    "translation_diagnostic_relative_margin",
    "translation_diagnostic_ambiguous",
    "translation_diagnostic_border_hit",
    "spatial_null_pvalue",
    "spatial_null_q10_median_px",
    "spatial_null_separation_px",
    "spatial_null_valid_trials",
    "building_median_m",
    "building_p90_m",
    "building_median_px",
    "building_p90_px",
    "n_selected_views",
    "n_valid_views",
    "n_als_class6_total",
    "n_als_class6_inframe",
    "n_als_class2_total",
    "n_als_class2_inframe",
    "n_boundary",
    "n_boundary_source",
    "n_boundary_matched",
    "boundary_visible_fraction",
    "oriented_match_fraction",
    "reverse_match_fraction",
    "n_edge_points",
    "edge_high_threshold",
    "edge_low_threshold",
    "xy_jacobian_condition_median",
    "xy_jacobian_condition_max",
    "normal_sensitivity_px_per_m_median",
    "view_nadir_deg",
    "frame_radius",
    "observability_p90_m_per_px",
    "predicted_metric_uncertainty_m",
    "azimuth_bin",
    "micro_shift_e_m",
    "micro_shift_n_m",
    "micro_shift_norm_m",
    "crs",
    "input_vertical_datum",
    "orthometric_geoid_m",
    "projection_datum_config",
    "pose_source",
    "pose_sha256",
    "camera_source",
    "camera_sha256",
    "footprint_source_kind",
    "footprint_gt_derived",
    "gt_xy_exception_used",
    "als_classes_used",
    "edge_residual_driver",
    "als_class2_role",
    "forbidden_gt_used",
    "lod2_z_used",
    "roofsurface_used",
    "roof_type_used",
    "semantic_class_used",
    "final_roof_model_used",
]


def write_csv_rows(
    path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fieldnames), extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: (
                        ""
                        if isinstance(row.get(field), float)
                        and not np.isfinite(float(row[field]))
                        else row.get(field, "")
                    )
                    for field in fieldnames
                }
            )


def _json_sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_sanitize(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            _json_sanitize(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def build_view_rows(
    views: Sequence[SelectedView],
    cameras: Mapping[int, Camera],
    image_paths: Mapping[str, Path],
    pose_source: Path,
    pose_sha: str,
    camera_source: Path,
    camera_sha: str,
) -> list[dict[str, Any]]:
    image_hash_cache: dict[Path, str] = {}
    rows: list[dict[str, Any]] = []
    for view in views:
        camera = cameras[view.camera_id]
        image_path = image_paths[view.name]
        if image_path not in image_hash_cache:
            image_hash_cache[image_path] = sha256_file(image_path)
        rows.append(
            {
                "building_id": view.building_id,
                "view_order": view.order,
                "view": view.name,
                "registration_split": view.registration_split,
                "selection_source": view.selection_source,
                "n_als_class6_inframe_at_selection": (
                    view.n_building_inframe_at_selection
                ),
                "frame_radius": _fmt_float(view.frame_radius, 6),
                "view_nadir_deg": _fmt_float(view.view_nadir_deg, 6),
                "observability_p90_m_per_px": _fmt_float(
                    view.observability_p90_m_per_px, 6
                ),
                "predicted_metric_uncertainty_m": _fmt_float(
                    view.predicted_metric_uncertainty_m, 6
                ),
                "azimuth_bin": view.azimuth_bin,
                "image_id": view.image_id,
                "camera_id": view.camera_id,
                "camera_model": camera.model,
                "width": camera.width,
                "height": camera.height,
                "image_path": repo_relative(image_path),
                "image_sha256": image_hash_cache[image_path],
                "pose_source": repo_relative(pose_source),
                "pose_sha256": pose_sha,
                "camera_source": repo_relative(camera_source),
                "camera_sha256": camera_sha,
                "training_pose_image_intersection": CSV_TRUE,
                "gt_xy_exception_used_for_visibility": CSV_TRUE,
                "forbidden_gt_used": CSV_FALSE,
            }
        )
    return rows


def revalidate_selected_view_inventory(
    view_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    unique: dict[str, str] = {}
    for row in view_rows:
        relative = str(row["image_path"])
        expected = str(row["image_sha256"])
        prior = unique.setdefault(relative, expected)
        if prior != expected:
            raise GateContractError(
                f"selected image has inconsistent hashes: {relative}"
            )
    for relative, expected in sorted(unique.items()):
        if sha256_file(repo_path(relative)) != expected:
            raise GateContractError(
                f"selected image changed before publication: {relative}"
            )
    return {
        "unique_selected_image_count": len(unique),
        "selected_image_hash_manifest_sha256": canonical_hash_manifest(unique),
        "all_selected_images_rehashed_unchanged": True,
    }


def render_overlay(
    path: Path,
    target: Target,
    view: SelectedView | None,
    row: Mapping[str, Any] | None,
    cloud: TargetCloud,
    image: ColmapImage | None,
    camera: Camera | None,
    image_path: Path | None,
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    xy_shift: Sequence[float],
    boundary_cfg: Mapping[str, Any],
) -> None:
    if (
        view is None
        or row is None
        or image is None
        or camera is None
        or image_path is None
    ):
        fig, axis = plt.subplots(figsize=(8, 4))
        axis.axis("off")
        axis.text(
            0.5,
            0.5,
            f"{target.building_id}\nno renderable Gate A view",
            ha="center",
            va="center",
        )
        fig.savefig(path, dpi=130, bbox_inches="tight")
        plt.close(fig)
        return
    building_uv, building_front = project_base_points(
        cloud.building_xyz,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
    )
    ground_uv, ground_front = project_base_points(
        cloud.ground_xyz,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
    )
    building_inframe = (
        building_front
        & (building_uv[:, 0] >= 0)
        & (building_uv[:, 0] < camera.width)
        & (building_uv[:, 1] >= 0)
        & (building_uv[:, 1] < camera.height)
    )
    ground_inframe = (
        ground_front
        & (ground_uv[:, 0] >= 0)
        & (ground_uv[:, 0] < camera.width)
        & (ground_uv[:, 1] >= 0)
        & (ground_uv[:, 1] < camera.height)
    )
    visible = building_uv[building_inframe]
    if not len(visible):
        return render_overlay(
            path,
            target,
            None,
            None,
            cloud,
            None,
            None,
            None,
            scene_reference,
            input_datum,
            geoid_m,
            xy_shift,
            boundary_cfg,
        )
    pad = 45
    x0 = max(0, int(np.min(visible[:, 0])) - pad)
    y0 = max(0, int(np.min(visible[:, 1])) - pad)
    x1 = min(camera.width, int(np.max(visible[:, 0])) + pad + 1)
    y1 = min(camera.height, int(np.max(visible[:, 1])) + pad + 1)
    with Image.open(image_path) as pil:
        rgb = np.asarray(pil.convert("RGB"))[y0:y1, x0:x1]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for axis in axes:
        axis.imshow(rgb)
        axis.axis("off")
    b = visible - np.array([x0, y0])
    g = ground_uv[ground_inframe] - np.array([x0, y0])
    axes[0].scatter(g[:, 0], g[:, 1], s=0.5, c="#ff8c42", alpha=0.20)
    axes[0].scatter(b[:, 0], b[:, 1], s=0.8, c="cyan", alpha=0.40)
    axes[0].set_title("as projected: ALS class 6 cyan, class 2 orange", fontsize=9)
    boundary = visible_eave_boundary(
        cloud,
        image,
        camera,
        scene_reference,
        input_datum,
        geoid_m,
        xy_shift,
        boundary_cfg,
    )
    boundary_local = boundary.uv - np.array([x0, y0])
    axes[1].scatter(
        boundary_local[:, 0],
        boundary_local[:, 1],
        s=4.0,
        c="cyan",
        label="projected ALS boundary",
    )
    axes[1].legend(fontsize=7, loc="best")
    axes[1].set_title(
        f"direct median/P90={row.get('median_residual_px', '?')}/"
        f"{row.get('p90_residual_px', '?')} px | "
        f"{row.get('median_residual_m', '?')}/"
        f"{row.get('p90_residual_m', '?')} m",
        fontsize=9,
    )
    fig.suptitle(
        f"{target.building_id} | {row.get('attempt')} | {view.name}\n"
        "GroundSurface XY scoped GT exception; no LoD2 Z/RoofSurface",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def render_overlays(
    overlay_dir: Path,
    targets: Sequence[Target],
    views: Sequence[SelectedView],
    final_rows: Sequence[Mapping[str, Any]],
    clouds: Mapping[str, TargetCloud],
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    scene_reference: Mapping[str, Any],
    input_datum: str,
    geoid_m: float,
    boundary_cfg: Mapping[str, Any],
) -> None:
    overlay_dir.mkdir(parents=True, exist_ok=False)
    views_grouped = _selected_by_building(views)
    rows_grouped = rows_by_building(final_rows)
    for target in targets:
        valid_rows = [
            row
            for row in rows_grouped.get(target.building_id, [])
            if row.get("valid") == CSV_TRUE and row.get("residual_m") not in ("", None)
        ]
        if valid_rows:
            residuals = np.asarray(
                [float(row["residual_m"]) for row in valid_rows]
            )
            median = float(np.median(residuals))
            chosen_row = min(
                valid_rows,
                key=lambda row: (
                    abs(float(row["residual_m"]) - median),
                    int(row["view_order"]),
                ),
            )
        else:
            chosen_row = (
                rows_grouped.get(target.building_id, [None])[0]
                if rows_grouped.get(target.building_id)
                else None
            )
        chosen_view = None
        if chosen_row is not None:
            chosen_view = next(
                (
                    view
                    for view in views_grouped[target.building_id]
                    if view.name == chosen_row["view"]
                ),
                None,
            )
        if chosen_view is None:
            image = None
            camera = None
            source_image = None
            shift = (0.0, 0.0)
        else:
            image = images_by_name[chosen_view.name]
            camera = cameras[image.camera_id]
            source_image = image_paths[chosen_view.name]
            shift = (
                float(chosen_row.get("micro_shift_e_m") or 0.0),
                float(chosen_row.get("micro_shift_n_m") or 0.0),
            )
        filename = target.building_id.replace("/", "_") + ".png"
        render_overlay(
            overlay_dir / filename,
            target,
            chosen_view,
            chosen_row,
            clouds[target.building_id],
            image,
            camera,
            source_image,
            scene_reference,
            input_datum,
            geoid_m,
            shift,
            boundary_cfg,
        )


def _output_paths(config: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_cfg = config["outputs"]
    return {
        key: output_dir / value
        for key, value in output_cfg.items()
    }


def _prepare_staging(
    output_dir: Path, publication_cfg: Mapping[str, Any]
) -> Path:
    versions = output_dir / str(publication_cfg["versions_dir"])
    if versions.is_symlink():
        raise GateContractError("alignment versions directory may not be a symlink")
    versions.mkdir(parents=False, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    staging = versions / (
        f".version-{stamp}-{os.getpid()}"
        f"{publication_cfg['inprogress_suffix']}"
    )
    if staging.exists():
        raise GateContractError(f"staging path already exists: {staging}")
    staging.mkdir(parents=False)
    return staging


def _fsync_tree(path: Path) -> None:
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink():
            raise GateContractError(
                f"staging publication contains a symlink: {candidate}"
            )
        if candidate.is_file():
            with candidate.open("rb") as handle:
                os.fsync(handle.fileno())
    directories = [candidate for candidate in path.rglob("*") if candidate.is_dir()]
    for directory in reversed(sorted(directories)):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_symlink(link: Path, target: str) -> None:
    temporary = link.parent / f".{link.name}.tmp-{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    os.symlink(target, temporary)
    os.replace(temporary, link)
    descriptor = os.open(link.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_staging(
    staging: Path,
    output_dir: Path,
    names: Mapping[str, str],
    publication_cfg: Mapping[str, Any],
    replace: bool,
) -> dict[str, Any]:
    suffix = str(publication_cfg["inprogress_suffix"])
    if not staging.name.endswith(suffix):
        raise GateContractError("version staging suffix drift")
    final_name = staging.name[1 : -len(suffix)]
    final_dir = staging.parent / final_name
    if final_dir.exists() or final_dir.is_symlink():
        raise GateContractError(f"version destination already exists: {final_dir}")
    _fsync_tree(staging)
    os.replace(staging, final_dir)
    versions_fd = os.open(staging.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(versions_fd)
    finally:
        os.close(versions_fd)

    current_name = str(publication_cfg["current_pointer"])
    current = output_dir / current_name
    if current.exists() and not current.is_symlink():
        if not replace:
            raise GateContractError(
                f"current pointer exists and is not a symlink: {current}"
            )
        if current.is_dir():
            shutil.rmtree(current)
        else:
            current.unlink()
    fixed_targets: dict[str, str] = {}
    for output_name in names.values():
        destination = output_dir / output_name
        wanted = f"{current_name}/{output_name}"
        if destination.is_symlink():
            if os.readlink(destination) != wanted:
                if not replace:
                    raise GateContractError(
                        f"fixed output symlink target drift: {destination}"
                    )
                destination.unlink()
                _atomic_symlink(destination, wanted)
        elif destination.exists():
            if not replace:
                raise GateContractError(
                    f"Gate A output exists; review it or pass --replace: "
                    f"{destination}"
                )
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
            _atomic_symlink(destination, wanted)
        else:
            _atomic_symlink(destination, wanted)
        fixed_targets[output_name] = wanted
    _atomic_symlink(
        current,
        f"{publication_cfg['versions_dir']}/{final_name}",
    )
    return {
        "version": final_name,
        "version_dir": repo_relative(final_dir),
        "current_pointer": repo_relative(current),
        "current_target": os.readlink(current),
        "fixed_output_symlinks": fixed_targets,
        "atomic_switch_complete": True,
    }


def run_gate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    config_path = repo_path(args.config)
    if config_path.resolve() != DEFAULT_CONFIG.resolve():
        raise GateContractError("alternate Gate A config is forbidden")
    config = load_config(config_path)
    if args.coreg_lock2:
        config = activate_coreg_gate_lock2(config)
    implementation_provenance = validate_implementation_provenance(config)
    immutable_preflight = validate_baseline_preflight(config["execution_guard"])
    if args.input_datum is not None and args.input_datum != config["input_locks"][
        "input_vertical_datum"
    ]:
        raise GateContractError(
            "CLI --input-datum conflicts with the locked config datum"
        )
    input_datum = config["input_locks"]["input_vertical_datum"]
    datum_config_path = (
        repo_path(args.datum_config)
        if args.datum_config
        else repo_path(config["inputs"]["projection_datum_config"])
    )
    if datum_config_path.resolve() != repo_path(
        config["inputs"]["projection_datum_config"]
    ).resolve():
        raise GateContractError(
            "CLI --datum-config conflicts with the locked Gate A config"
        )
    datum_payload = load_projection_config(datum_config_path)
    geoid_m = projection_geoid_m(config_path=datum_config_path)
    if input_datum != "orthometric":
        raise GateContractError("W1 raw ALS must use explicit orthometric input datum")
    if datum_payload.get("input_vertical_datum_default") != input_datum:
        raise GateContractError("projection datum config default drift")
    if not args.execution_guard:
        raise GateContractError("Gate A must be launched by the runtime-guard wrapper")
    guard_path = repo_path(args.execution_guard)
    execution_guard = validate_runtime_guard_receipt(guard_path, config_path)
    source_hashes = validate_source_hashes(config)
    pose_publication_contract = (
        validate_pose_publication_contract(config)
        if args.coreg_lock2
        else None
    )
    if pose_publication_contract is not None:
        source_hashes.update(
            {
                f"{pose_publication_contract['derived_sparse']}/{name}": digest
                for name, digest in pose_publication_contract[
                    "derived_sha256"
                ].items()
            }
        )
    output_dir = (
        repo_path(args.output_dir)
        if args.output_dir
        else repo_path(config["inputs"]["output_dir"])
    )
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise GateContractError(
            f"output directory must be an existing non-symlink directory: {output_dir}"
        )

    targets_path = (
        repo_path(args.targets)
        if args.targets
        else repo_path(config["inputs"]["targets_csv"])
    )
    expected_target_sha = config["input_locks"]["expected_sha256"].get(
        repo_relative(targets_path)
    )
    if expected_target_sha is None:
        raise GateContractError(
            "selected targets CSV has no result-blind expected SHA256 lock"
        )
    actual_target_sha = sha256_file(targets_path)
    if actual_target_sha != expected_target_sha:
        raise GateContractError(
            "selected targets CSV SHA256 differs from the Gate A lock"
        )
    cohort = args.cohort or config["inputs"]["default_target_cohort"]
    if cohort != "core":
        raise GateContractError(
            "lock1 implements the preregistered core Gate only; full extension "
            "round-robin remains an explicitly disclosed follow-up"
        )
    targets = load_targets(targets_path, config, cohort)
    targets_manifest_path = repo_path(config["inputs"]["targets_manifest"])
    targets_manifest = json.loads(
        targets_manifest_path.read_text(encoding="utf-8")
    )
    if (
        targets_manifest.get("queue_status")
        != config["target_queue_contract"]["required_queue_status"]
        or targets_manifest.get("core_priority_complete") is not False
        or targets_manifest.get("gs4buildings", {}).get("overlap_resolution")
        != "unknown"
        or targets_manifest.get("resolved_core_lower_bound_count") != 28
    ):
        raise GateContractError(
            "target manifest no longer preserves provisional GS4/core semantics"
        )
    if sha256_file(targets_path) != expected_target_sha:
        raise GateContractError("targets CSV changed while Gate A loaded it")
    footprint_path = repo_path(config["inputs"]["footprint_xy"])
    footprints = load_footprints(
        footprint_path,
        [target.building_id for target in targets],
        config["inputs"]["footprint_id_field"],
        config["inputs"].get("footprint_layer"),
        config,
    )
    als_paths = [repo_path(path) for path in config["inputs"]["als_files"]]
    store = ALSStore(
        als_paths,
        int(config["input_locks"]["als_ground_class"]),
        int(config["input_locks"]["als_building_class"]),
    )
    clouds: dict[str, TargetCloud] = {}
    for target in targets:
        clouds[target.building_id] = store.target_cloud(
            target.building_id,
            footprints[target.building_id],
            config["als_evidence"],
        )
        print(
            f"[ALS] {target.processing_order:03d} {target.building_id}: "
            f"class6={len(clouds[target.building_id].building_xyz)} "
            f"class2={len(clouds[target.building_id].ground_xyz)}",
            flush=True,
        )

    sparse_dir = repo_path(config["inputs"]["colmap_sparse_dir"])
    image_dir = repo_path(config["inputs"]["training_image_dir"])
    expected_intersection = config["input_locks"].get(
        "expected_training_pose_image_intersection"
    )
    cameras, _images, images_by_name, image_paths = load_training_inventory(
        sparse_dir, image_dir, expected_intersection
    )
    pose_source = sparse_dir / "images.bin"
    camera_source = sparse_dir / "cameras.bin"
    pose_sha = sha256_file(pose_source)
    camera_sha = sha256_file(camera_source)
    scene_reference_path = repo_path(config["inputs"]["scene_reference_frame"])
    scene_payload = json.loads(scene_reference_path.read_text(encoding="utf-8"))
    scene_reference = scene_payload.get("base_to_canonical")
    if not isinstance(scene_reference, Mapping):
        raise GateContractError("scene reference lacks base_to_canonical")

    if args.views:
        views = load_provided_views(
            repo_path(args.views),
            targets,
            config,
            images_by_name,
            cameras,
            clouds,
            scene_reference,
            input_datum,
            geoid_m,
        )
    else:
        views = auto_select_views(
            targets,
            clouds,
            cameras,
            images_by_name,
            scene_reference,
            input_datum,
            geoid_m,
            config["view_selection"],
            config["boundary_extraction"],
            config["alignment"],
        )
    views = assign_registration_splits(views, config["micro_registration"])
    view_rows = build_view_rows(
        views,
        cameras,
        image_paths,
        pose_source,
        pose_sha,
        camera_source,
        camera_sha,
    )
    implementation_sha = canonical_hash_manifest(
        {
            str(item["path"]): str(item["sha256"])
            for item in implementation_provenance["files"]
        }
    )
    input_identity_hashes = dict(source_hashes)
    input_identity_hashes["training_images_sha256sum_stream_aggregate"] = str(
        config["input_locks"]["expected_training_image_set"][
            "sha256sum_stream_aggregate"
        ]
    )
    checkpoint_identity = CheckpointIdentity(
        config_sha256=sha256_file(config_path),
        input_sha256=canonical_hash_manifest(input_identity_hashes),
        view_sha256=canonical_json_sha256(view_rows),
        implementation_sha256=implementation_sha,
    )
    checkpoint_store = AlignmentCheckpointStore(
        output_dir
        / str(config["publication"]["per_building_checkpoint_dir"])
    )

    zero_shifts = {
        target.building_id: (0.0, 0.0) for target in targets
    }
    zero_reasons = {target.building_id: "not_applicable" for target in targets}
    raw_rows, raw_checkpoint_refs = measure_all_checkpointed(
        targets,
        views,
        clouds,
        cameras,
        images_by_name,
        image_paths,
        scene_reference,
        input_datum,
        geoid_m,
        datum_config_path,
        config["boundary_extraction"],
        config["edge_extraction"],
        config["alignment"],
        config["confidence"],
        zero_shifts,
        zero_reasons,
        RAW_ATTEMPT,
        pose_source,
        pose_sha,
        camera_source,
        camera_sha,
        checkpoint_store,
        checkpoint_identity,
        config["gate"],
        config["view_selection"],
        config["micro_registration"],
    )
    raw_buildings = summarize_buildings(
        targets,
        raw_rows,
        config["gate"],
        config["view_selection"],
        RAW_ATTEMPT,
    )
    raw_systematic = systematic_translation(raw_rows, config["gate"])
    raw_gate = evaluate_gate(raw_buildings, raw_systematic)

    micro_attempt_count = 0
    micro_rows: list[dict[str, Any]] = []
    micro_buildings: list[dict[str, Any]] = []
    maximum_micro_attempts = int(
        config["micro_registration"]["maximum_attempts"]
    )
    global_micro_metadata: dict[str, Any] = {
        "reason": "raw_gate_met_no_micro_registration",
        "shift": None,
    }
    if maximum_micro_attempts == 0 and not raw_gate["numeric_gate_met"]:
        global_micro_metadata["reason"] = (
            "post_coreg_xy_micro_registration_forbidden"
        )
    if raw_gate["numeric_gate_met"] or maximum_micro_attempts == 0:
        final_rows = raw_rows
        final_buildings = raw_buildings
        final_systematic = raw_systematic
        final_gate = raw_gate
        final_attempt = RAW_ATTEMPT
        global_shift: tuple[float, float] | None = None
        micro_shifts: dict[str, tuple[float, float] | None] = {}
        micro_reasons: dict[str, str] = {}
    else:
        micro_attempt_count = 1
        global_shift, global_micro_metadata = plan_global_micro_shift(
            raw_rows,
            config["micro_registration"],
            config["alignment"],
        )
        micro_shifts = {
            target.building_id: global_shift for target in targets
        }
        micro_reasons = {
            target.building_id: str(global_micro_metadata["reason"])
            for target in targets
        }
        micro_rows, micro_checkpoint_refs = measure_all_checkpointed(
            targets,
            views,
            clouds,
            cameras,
            images_by_name,
            image_paths,
            scene_reference,
            input_datum,
            geoid_m,
            datum_config_path,
            config["boundary_extraction"],
            config["edge_extraction"],
            config["alignment"],
            config["confidence"],
            micro_shifts,
            micro_reasons,
            MICRO_ATTEMPT,
            pose_source,
            pose_sha,
            camera_source,
            camera_sha,
            checkpoint_store,
            checkpoint_identity,
            config["gate"],
            config["view_selection"],
            config["micro_registration"],
        )
        micro_buildings = summarize_buildings(
            targets,
            micro_rows,
            config["gate"],
            config["view_selection"],
            MICRO_ATTEMPT,
            evaluation_split="heldout",
            micro_cfg=config["micro_registration"],
        )
        final_rows = [
            row
            for row in micro_rows
            if row.get("registration_split") == "heldout"
        ]
        final_buildings = micro_buildings
        final_systematic = systematic_translation(
            micro_rows, config["gate"], evaluation_split="heldout"
        )
        final_gate = evaluate_gate(micro_buildings, final_systematic)
        final_attempt = MICRO_ATTEMPT
    if raw_gate["numeric_gate_met"] or maximum_micro_attempts == 0:
        micro_checkpoint_refs = []

    for row in raw_rows:
        row["is_final"] = (
            CSV_TRUE if final_attempt == RAW_ATTEMPT else CSV_FALSE
        )
        row["diagnostic_only"] = (
            CSV_FALSE if final_attempt == RAW_ATTEMPT else CSV_TRUE
        )
    for row in micro_rows:
        heldout = row.get("registration_split") == "heldout"
        row["is_final"] = CSV_TRUE if heldout else CSV_FALSE
        row["diagnostic_only"] = CSV_FALSE if heldout else CSV_TRUE
    all_rows = raw_rows + micro_rows
    all_building_rows = raw_buildings + micro_buildings
    status = (
        "numeric_gate_met"
        if final_gate["numeric_gate_met"]
        else "BLOCKED"
    )
    gate_payload = {
        "schema": "jointbuildgs.fusion_w1.alignment_gate_result.v1",
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "status": status,
        "final_attempt": final_attempt,
        "raw": {
            "gate": raw_gate,
            "systematic_translation": raw_systematic,
        },
        "micro_registration": {
            "attempt_count": micro_attempt_count,
            "maximum_attempts": maximum_micro_attempts,
            "second_attempt_forbidden": True,
            "method": config["micro_registration"]["method"],
            "global_shared_shift": global_micro_metadata,
            "same_shift_for_every_building": micro_attempt_count == 1,
            "post_registration_gate_split": (
                "heldout" if micro_attempt_count == 1 else "not_applicable"
            ),
        },
        "final": {
            "gate": final_gate,
            "systematic_translation": final_systematic,
        },
        "locked_formulas": {
            "building": config["gate"]["building_pass_formula"],
            "systematic": config["gate"]["systematic_negligible_formula"],
            "overall": config["gate"]["overall_pass_formula"],
            "systematic_threshold_rationale": config["gate"][
                "systematic_threshold_rationale"
            ],
        },
        "execution_guard": execution_guard,
        "pose_publication_contract": pose_publication_contract,
        "coreg_evaluation_scope": (
            {
                "primary_untouched_core_count": int(
                    config["_active_coreg_gate_lock2"][
                        "primary_untouched_core_count"
                    ]
                ),
                "run004_exposed_diagnostic_core_ids": list(
                    config["_active_coreg_gate_lock2"][
                        "original_run004_exposed_core_ids"
                    ]
                ),
                "post_coreg_xy_micro_registration_attempts": 0,
            }
            if args.coreg_lock2
            else None
        ),
        "queue_scope": {
            "queue_status": config["target_queue_contract"][
                "required_queue_status"
            ],
            "gs4_overlap_resolution": "unknown",
            "numeric_gate_only": True,
            "does_not_resolve_or_relabel_gs4_overlap": True,
            "learning_entry_field_is_numeric_only": True,
        },
        "human_research_judgment": None,
    }

    staging = _prepare_staging(output_dir, config["publication"])
    output_names = config["outputs"]
    publication_suffix = str(config["publication"]["inprogress_suffix"])
    planned_version = staging.name[1 : -len(publication_suffix)]
    try:
        write_csv_rows(
            staging / output_names["residuals_csv"],
            all_rows,
            RESIDUAL_FIELDS,
        )
        view_fields = list(view_rows[0].keys())
        write_csv_rows(
            staging / output_names["views_csv"], view_rows, view_fields
        )
        building_fields = list(all_building_rows[0].keys())
        write_csv_rows(
            staging / output_names["buildings_csv"],
            all_building_rows,
            building_fields,
        )
        write_json(staging / output_names["gate_json"], gate_payload)
        render_overlays(
            staging / output_names["overlay_dir"],
            targets,
            views,
            final_rows,
            clouds,
            cameras,
            images_by_name,
            image_paths,
            scene_reference,
            input_datum,
            geoid_m,
            config["boundary_extraction"],
        )
        selected_image_revalidation = revalidate_selected_view_inventory(
            view_rows
        )
        try:
            prepublication_revalidation = revalidate_before_publish(
                config_path, guard_path
            )
        except RuntimeGuardError as exc:
            raise GateContractError(
                f"pre-publication runtime revalidation failed: {exc}"
            ) from exc
        gate_payload["prepublication_revalidation"] = (
            prepublication_revalidation
        )
        gate_payload["publication"] = {
            "planned_version": planned_version,
            "current_pointer": config["publication"]["current_pointer"],
            "atomic_version_switch_required": True,
        }
        write_json(staging / output_names["gate_json"], gate_payload)
        manifest = {
            "schema": "jointbuildgs.fusion_w1.alignment_manifest.v1",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "config": {
                "path": repo_relative(config_path),
                "sha256": sha256_file(config_path),
            },
            "implementation_provenance": implementation_provenance,
            "immutable_preflight": immutable_preflight,
            "targets": {
                "path": repo_relative(targets_path),
                "sha256": sha256_file(targets_path),
                "cohort_filter": cohort,
                "count": len(targets),
                "queue_statuses": sorted(
                    {target.queue_status for target in targets}
                ),
                "cohort_resolution_statuses": sorted(
                    {
                        target.cohort_resolution_status
                        for target in targets
                    }
                ),
                "gs4_overlap_interpretation": config[
                    "target_queue_contract"
                ]["gs4_overlap_interpretation"],
            },
            "training_inventory": {
                "image_dir": repo_relative(image_dir),
                "pose_source": repo_relative(pose_source),
                "pose_sha256": pose_sha,
                "camera_source": repo_relative(camera_source),
                "camera_sha256": camera_sha,
                "pose_image_intersection_count": len(images_by_name),
                "selected_building_view_rows": len(views),
                "selected_view_inventory_sha256": canonical_json_sha256(
                    view_rows
                ),
                **selected_image_revalidation,
            },
            "pose_publication_contract": pose_publication_contract,
            "datum": {
                "crs": "EPSG:25832",
                "input_vertical_datum": input_datum,
                "projection_datum_config": repo_relative(datum_config_path),
                "projection_datum_config_sha256": sha256_file(datum_config_path),
                "orthometric_geoid_m": geoid_m,
                "description": describe_projection_config(datum_config_path),
            },
            "inputs_sha256": source_hashes,
            "als": {
                "ground_class": config["input_locks"]["als_ground_class"],
                "building_class": config["input_locks"]["als_building_class"],
                "raw_header_crs_policy": config["input_locks"][
                    "raw_als_missing_crs_vlr_policy"
                ],
            },
            "gt_separation": {
                "footprint_source": repo_relative(footprint_path),
                "footprint_source_sha256": sha256_file(footprint_path),
                "footprint_source_kind": (
                    "lod2_groundsurface_xy_scoped_exception"
                ),
                "footprint_gt_derived": True,
                "approved_components_used": ["GroundSurface XY"],
                "forbidden_inputs_read": [],
                "forbidden_gt_used": False,
                "lod2_z_used": False,
                "roofsurface_used": False,
                "roof_type_used": False,
                "semantic_class_used": False,
                "final_roof_model_used": False,
            },
            "execution": {
                "device": config["execution_guard"]["execution_device"],
                "cuda_used": config["execution_guard"]["cuda_used"],
                "fresh_no_active_training_guard": execution_guard,
                "prepublication_revalidation": prepublication_revalidation,
                "learning_runs_started": 0,
                "reconstruction_runs_started": 0,
                "readout_runs_started": 0,
                "scoring_runs_started": 0,
                "micro_registration_attempt_count": micro_attempt_count,
                "post_coreg_xy_micro_registration_forbidden": bool(
                    args.coreg_lock2
                ),
                "elapsed_seconds": time.monotonic() - started,
                "time_cutoff_applied": False,
                "snapshot_0630_stops_execution": False,
            },
            "checkpointing": {
                "identity_key": checkpoint_identity.key,
                "bindings": checkpoint_identity.as_dict(),
                "root": repo_relative(checkpoint_store.root),
                "raw_checkpoint_count": len(raw_checkpoint_refs),
                "micro_checkpoint_count": len(micro_checkpoint_refs),
                "per_building_fsync_before_advance": True,
                "resume_verifies_hash_bindings": True,
            },
            "publication": {
                "version": planned_version,
                "version_dir": repo_relative(staging.parent / planned_version),
                "current_pointer": repo_relative(
                    output_dir
                    / str(config["publication"]["current_pointer"])
                ),
                "publish_method": config["publication"]["publish_method"],
                "atomic_current_switch": True,
                "fixed_outputs_resolve_through_current_pointer": True,
            },
            "outputs": {
                name: {
                    "path": repo_relative(output_dir / filename),
                    "sha256": (
                        None
                        if name == "manifest_json"
                        or (staging / filename).is_dir()
                        else sha256_file(staging / filename)
                    ),
                    "sha256_note": (
                        "self_hash_not_embedded"
                        if name == "manifest_json"
                        else (
                            "directory_artifact"
                            if (staging / filename).is_dir()
                            else "file_sha256"
                        )
                    ),
                }
                for name, filename in output_names.items()
            },
            "numeric_gate_met": final_gate["numeric_gate_met"],
            "human_research_judgment": None,
        }
        write_json(staging / output_names["manifest_json"], manifest)
        _publish_staging(
            staging,
            output_dir,
            output_names,
            config["publication"],
            args.replace,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return (0 if final_gate["numeric_gate_met"] else 2), gate_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FUS-W1 Gate A raw ALS-to-training-image alignment"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="result-blind Gate A config",
    )
    parser.add_argument(
        "--targets",
        help="optional targets CSV override; IDs still come from the file",
    )
    parser.add_argument(
        "--cohort",
        choices=["core", "extension", "all"],
        help="target cohort filter; defaults to the config lock",
    )
    parser.add_argument(
        "--views",
        help=(
            "optional deterministic building/view CSV; without it views are "
            "selected from the exact training pose/image intersection"
        ),
    )
    parser.add_argument(
        "--input-datum",
        choices=["orthometric", "ellipsoidal"],
        help="explicit datum cross-check; must match the locked config",
    )
    parser.add_argument(
        "--datum-config",
        help="explicit projection datum config cross-check; must match the lock",
    )
    parser.add_argument(
        "--execution-guard",
        help=(
            "fresh host-scope no-active-training receipt; defaults to the "
            "config path and must be no older than five minutes"
        ),
    )
    parser.add_argument("--output-dir", help="existing run output directory")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace only the fixed w1_align_* outputs after explicit review",
    )
    parser.add_argument(
        "--coreg-lock2",
        action="store_true",
        help=(
            "activate the committed corrected-camera Gate A2 contract; "
            "no additional XY micro-registration is permitted"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        require_docker()
        status, payload = run_gate(args)
    except GateContractError as exc:
        print(f"[BLOCKED] Gate A contract failure: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # fail closed, with visible exception type
        print(
            f"[BLOCKED] Gate A unhandled {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(
        "[Gate A] "
        + (
            "locked numeric criteria met; human judgment remains unset"
            if status == 0
            else (
                "BLOCKED with post-coreg XY micro-registration forbidden"
                if args.coreg_lock2
                else "BLOCKED after the single permitted micro-registration attempt"
            )
        )
    )
    print(json.dumps(_json_sanitize(payload["final"]), ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
