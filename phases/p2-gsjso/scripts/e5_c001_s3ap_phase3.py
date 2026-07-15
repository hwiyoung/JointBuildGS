#!/usr/bin/env python3
"""S3-A-prime Phase-3 read-out and scoring harness.

The top-level ``run`` command is orchestration only.  It starts every geometry,
Roofer, val3dity, scoring, and figure worker in a pinned Docker image with the
host uid/gid.  No training or feature-matching inference is implemented here.

Before either GPU queue is created, the host controller invokes the locked
Phase-2 gsplat prewarm once, verifies its cache/extension attestation, and
shares that already-built TORCH_EXTENSIONS_DIR with every Phase-3 worker.

The data boundary is structural:

1. ``extract-job`` renders only the staged fixed-view COLMAP crop and fuses
   expected and median depth.  It cannot accept a footprint or LoD2 path.
2. ``prepare-roofer-job`` uses the fused GS evidence and the already measured
   Phase-0 observed-ground scalar.  It derives the roofprint from occupied
   point cells and never opens the supplied footprint.
3. ``score-job`` is the first command that opens the supplied footprint and
   LoD2.  They are used only for region masks, error calculation, and overlays.

Each job writes atomically and the controller appends a durable log/status row
after every stage.  A missing final checkpoint is recorded and skipped; a
failed job does not stop later jobs.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_phase3_lock.json"
CONTAINER_REPO = Path("/workspace/JointBuildGS")
SCRIPT_REL = Path("phases/p2-gsjso/scripts/e5_c001_s3ap_phase3.py")
SCRIPT_DIR = Path(__file__).resolve().parent
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"
PHASE0_BASELINE_SCRIPT = SCRIPT_DIR / "e5_c001_s3ap_phase0_baselines.py"
METRICS_SCRIPT = SCRIPT_DIR / "e5_c001_8way.py"

STATUS_FIELDS = [
    "run_id", "building_id", "arm", "replicate", "perturbation_type",
    "perturbation_value", "stage", "status", "reason", "updated_utc",
    "checkpoint", "prepared_root", "job_dir", "gpu_id",
]

SCORE_FIELDS = [
    "run_id", "building_id", "arm", "replicate", "perturbation_type",
    "perturbation_value", "score_status", "score_reason", "checkpoint",
    "checkpoint_sha256", "prepared_root", "fixed_view_count", "fixed_views",
    "alpha_min_inclusive", "voxel_m", "min_observations", "sor_neighbors",
    "sor_std_ratio", "expected_fused_all", "expected_minobs_kept",
    "expected_sor_kept", "median_fused_all", "median_minobs_kept",
    "median_sor_kept", "canonical_depth", "roof_evidence_point_count",
    "ground_z_local_m", "ground_method", "ground_source",
    "minimum_height_above_ground_m", "derived_roofprint_area_m2",
    "supplied_footprint_passed_to_roofer",
    "point_evidence_derived_roofprint_passed_to_roofer",
    "fused_inside_point_count", "coverage_grid_m", "coverage_eligible_cells",
    "coverage_occupied_cells", "coverage_ratio", "edge_width_m",
    "edge_point_count", "edge_coverage_eligible_cells",
    "edge_coverage_occupied_cells", "edge_coverage_ratio",
    "interior_point_count", "interior_coverage_eligible_cells",
    "interior_coverage_occupied_cells", "interior_coverage_ratio",
    "height_error_signed_median_m", "height_error_abs_median_m",
    "height_error_mad_m", "height_error_rms_m",
    "edge_height_error_signed_median_m", "edge_height_error_abs_median_m",
    "edge_height_error_mad_m", "edge_height_error_rms_m",
    "interior_height_error_signed_median_m",
    "interior_height_error_abs_median_m", "interior_height_error_mad_m",
    "interior_height_error_rms_m", "roofer_status", "roofer_reason",
    "rf_extrusion_mode", "rf_roof_planes", "geometry_has_lod22",
    "has_lod22", "val3dity_valid", "citygml_completeness",
    "citygml_roof_rms_m", "substantive_filter", "cityjson_path",
    "citygml_roof_point_count", "citygml_coverage_eligible_cells",
    "citygml_coverage_occupied_cells", "citygml_coverage_ratio",
    "citygml_edge_point_count", "citygml_edge_coverage_eligible_cells",
    "citygml_edge_coverage_occupied_cells", "citygml_edge_coverage_ratio",
    "citygml_interior_point_count", "citygml_interior_coverage_eligible_cells",
    "citygml_interior_coverage_occupied_cells", "citygml_interior_coverage_ratio",
    "citygml_height_error_signed_median_m", "citygml_height_error_abs_median_m",
    "citygml_height_error_mad_m", "citygml_height_error_rms_region_m",
    "citygml_edge_height_error_signed_median_m",
    "citygml_edge_height_error_abs_median_m", "citygml_edge_height_error_mad_m",
    "citygml_edge_height_error_rms_m",
    "citygml_interior_height_error_signed_median_m",
    "citygml_interior_height_error_abs_median_m",
    "citygml_interior_height_error_mad_m", "citygml_interior_height_error_rms_m",
    "p0_height_error_signed_median_m", "p0_height_error_abs_median_m",
    "p0_height_error_mad_m", "p0_height_error_rms_m", "p0_coverage_ratio",
    "p0_edge_point_count", "p0_edge_coverage_ratio",
    "p0_edge_height_error_signed_median_m", "p0_edge_height_error_abs_median_m",
    "p0_edge_height_error_mad_m", "p0_edge_height_error_rms_m",
    "p0_interior_point_count", "p0_interior_coverage_ratio",
    "p0_interior_height_error_signed_median_m",
    "p0_interior_height_error_abs_median_m", "p0_interior_height_error_mad_m",
    "p0_interior_height_error_rms_m", "gs_edge_abs_error_lt_p0",
    "gs_interior_abs_error_lt_p0", "gs_minus_p0_edge_abs_median_m",
    "gs_minus_p0_interior_abs_median_m",
    "p0_has_lod22", "p0_substantive_filter", "gs_abs_error_lt_p0",
    "gs_p0_comparison_metric", "mvs_direct_class6_no_points",
    "mvs_canonical_no_points", "mvs_canonical_reason", "footprint_role",
    "gt_role", "crs", "extraction_manifest", "roofer_input_manifest",
]

PERTURB_FIELDS = [
    "run_id", "building_id", "arm", "replicate", "delta_m", "score_status",
    "p0_signed_median_error_m", "perturbed_p0_signed_median_error_m",
    "perturbed_p0_abs_signed_median_error_m", "post_gs_signed_median_error_m",
    "post_gs_abs_signed_median_error_m", "signed_error_reduction_m",
    "post_minus_perturbed_seed_signed_m", "return_condition_met",
    "trigger_candidate", "trigger_rule",
]

PERTURB_CELL_FIELDS = [
    "run_id", "building_id", "arm", "replicate", "delta_m", "cell_ix",
    "cell_iy", "cell_center_x", "cell_center_y", "region",
    "p0_base_signed_error_m", "perturbed_p0_signed_error_m",
    "perturbed_p0_abs_error_m", "post_gs_point_count",
    "post_gs_signed_error_m", "post_gs_abs_error_m", "return_amount_m",
    "return_condition_met", "coverage_grid_m", "score_status",
]


@dataclass(frozen=True)
class Job:
    run_id: str
    building_id: str
    arm: str
    replicate: str
    perturbation_type: str
    perturbation_value: float
    config_path: str
    prepared_root: str
    checkpoint: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        if str(path).startswith(str(CONTAINER_REPO)):
            return REPO / path.relative_to(CONTAINER_REPO)
        return path
    return REPO / path


def rel(path: str | Path) -> str:
    value = Path(path).resolve()
    try:
        return str(value.relative_to(REPO.resolve()))
    except ValueError:
        return str(value)


def container_path(path: str | Path) -> str:
    value = resolve_repo_path(path).resolve()
    try:
        return str(CONTAINER_REPO / value.relative_to(REPO.resolve()))
    except ValueError as exc:
        raise RuntimeError(f"container path is outside repository: {value}") from exc


def sha256_file(path: str | Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hash_file_bundle(paths: Iterable[Path]) -> dict[str, Any]:
    files = sorted({Path(path).resolve() for path in paths if Path(path).is_file()}, key=str)
    rows = [
        {"path": rel(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in files
    ]
    return {"file_count": len(rows), "files": rows, "digest": canonical_digest({"files": rows})}


def prepared_input_bundle(prepared_root: Path) -> dict[str, Any]:
    sparse = prepared_root / "sparse"
    if (sparse / "0").is_dir():
        sparse = sparse / "0"
    paths = [path for path in sparse.rglob("*") if path.is_file()]
    image_root = prepared_root / "images"
    paths.extend(path for path in image_root.rglob("*") if path.is_file())
    bundle = hash_file_bundle(paths)
    if bundle["file_count"] == 0:
        raise RuntimeError(f"prepared sparse+images bundle is empty: {prepared_root}")
    bundle["prepared_root"] = rel(prepared_root)
    return bundle


def pre_readout_fingerprint(config_path: Path, config: Mapping[str, Any], job: Job) -> dict[str, Any]:
    """Hash only inputs legal before Roofer input finalization."""

    checkpoint = resolve_repo_path(job.checkpoint)
    prepared = resolve_repo_path(job.prepared_root)
    world_offset = resolve_repo_path(config["extraction"]["world_offset_manifest"])
    ground = resolve_repo_path(config["roof_evidence"]["ground_source_csv"])
    prewarm = phase2_prewarm_binding(config)
    colmap_io = REPO / "src/stage2/colmap_io.py"
    required = [Path(__file__), config_path, checkpoint, world_offset, ground, colmap_io]
    job_config = resolve_repo_path(job.config_path) if job.config_path else None
    if job_config is not None:
        required.append(job_config)
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"pre-readout fingerprint inputs missing: {missing}")
    payload = {
        "schema": "jointbuildgs.s3ap.phase3.pre_readout_fingerprint.v1",
        "job": asdict(job),
        "phase3_script_sha256": sha256_file(Path(__file__)),
        "phase3_config_sha256": sha256_file(config_path),
        "pre_readout_code_dependencies": hash_file_bundle([
            colmap_io,
        ]),
        "phase2_job_config": (
            {"path": rel(job_config), "sha256": sha256_file(job_config)}
            if job_config is not None else None
        ),
        "checkpoint_sha256": sha256_file(checkpoint),
        "prepared_sparse_images": prepared_input_bundle(prepared),
        "world_offset_manifest": {"path": rel(world_offset), "sha256": sha256_file(world_offset)},
        "observed_ground_source": {"path": rel(ground), "sha256": sha256_file(ground)},
        "phase2_serialized_gsplat_prewarm": prewarm,
        "locked_docker_image_ids": {
            "render": config["containers"]["render_image_id"],
            "tools": config["containers"]["tools_image_id"],
            "roofer": config["roofer"]["image_id_record"],
        },
    }
    return {"digest": canonical_digest(payload), "payload": payload}


def score_only_fingerprint(config: Mapping[str, Any]) -> dict[str, Any]:
    """Hash score-only inputs. Call only after Roofer input is finalized."""

    scoring = config["scoring"]
    paths = [
        resolve_repo_path(scoring["footprints"]),
        resolve_repo_path(scoring["projection_datum"]),
        resolve_repo_path(scoring["p0_scores"]),
        resolve_repo_path(scoring["p0_points"]),
        resolve_repo_path(scoring["mvs_scores"]),
        resolve_repo_path(scoring["mvs_cityjson"]),
        PHASE0_BASELINE_SCRIPT,
        METRICS_SCRIPT,
        W2_SCRIPT,
    ]
    for row in read_csv(resolve_repo_path(scoring["p0_scores"])):
        if str(row.get("cityjson_path", "")).strip():
            paths.append(resolve_repo_path(row["cityjson_path"]))
    for row in read_csv(resolve_repo_path(scoring["mvs_scores"])):
        if str(row.get("source_path", "")).strip():
            paths.append(resolve_repo_path(row["source_path"]))
    lod2_dir = resolve_repo_path(scoring["lod2_dir"])
    paths.extend(sorted(lod2_dir.glob("*.gml")))
    missing = [rel(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"score-only fingerprint inputs missing: {missing}")
    bundle = hash_file_bundle(paths)
    payload = {
        "schema": "jointbuildgs.s3ap.phase3.score_only_fingerprint.v1",
        "boundary": scoring["gt_open_boundary"],
        "bundle": bundle,
    }
    return {"digest": canonical_digest(payload), "payload": payload}


def full_reuse_fingerprint(pre: Mapping[str, Any], score: Mapping[str, Any]) -> str:
    return canonical_digest({
        "schema": "jointbuildgs.s3ap.phase3.full_reuse_fingerprint.v1",
        "pre_readout_digest": pre["digest"],
        "score_only_digest": score["digest"],
    })


def normalize_image_id(value: Any) -> str:
    """Return the immutable Docker content ID or reject an ambiguous value."""

    normalized = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", normalized):
        normalized = "sha256:" + normalized
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized):
        raise RuntimeError(f"invalid Docker image ID: {value!r}")
    return normalized


def image_id_matches(left: Any, right: Any) -> bool:
    try:
        return normalize_image_id(left) == normalize_image_id(right)
    except RuntimeError:
        return False


def verify_docker_images(config: Mapping[str, Any]) -> dict[str, Any]:
    """Fail before scheduling if any mutable image reference drifted."""

    requested = [
        ("render", config["containers"]["render_image"], config["containers"]["render_image_id"]),
        ("tools", config["containers"]["tools_image"], config["containers"]["tools_image_id"]),
        ("roofer", config["roofer"]["image"], config["roofer"]["image_id_record"]),
    ]
    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for role, reference, expected_raw in requested:
        expected = normalize_image_id(expected_raw)
        proc = subprocess.run(
            ["docker", "image", "inspect", str(reference), "--format", "{{.Id}}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        actual_raw = (proc.stdout or "").strip().splitlines()
        actual = None
        if proc.returncode == 0 and actual_raw:
            try:
                actual = normalize_image_id(actual_raw[-1])
            except RuntimeError:
                actual = None
        matched = bool(proc.returncode == 0 and actual == expected)
        row = {
            "role": role, "reference": str(reference), "expected_id": expected,
            "actual_id": actual, "inspect_exit_code": int(proc.returncode),
            "matched": matched,
        }
        rows.append(row)
        if not matched:
            mismatches.append(role)
    result = {
        "schema": "jointbuildgs.s3ap.phase3.docker_image_verification.v1",
        "created_utc": utc_now(), "status": "complete" if not mismatches else "failed",
        "images": rows, "mismatched_roles": mismatches,
    }
    atomic_json(resolve_repo_path(config["outputs"]["image_verification"]), result)
    if mismatches:
        raise RuntimeError(f"Docker image ID verification failed: {','.join(mismatches)}")
    return result


def _git_commit_is_ancestor(ancestor: str, descendant: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}", ancestor) or not re.fullmatch(r"[0-9a-f]{40}", descendant):
        return False
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, check=False,
    )
    return proc.returncode == 0


def _git_file_sha256(commit: str, path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return None
    proc = subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=REPO,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    return hashlib.sha256(proc.stdout).hexdigest() if proc.returncode == 0 else None


def verify_phase2_prewarm(
    config: Mapping[str, Any], launcher_exit_code: int,
) -> dict[str, Any]:
    """Fail closed on the serialized Phase-2 gsplat cache attestation."""

    spec = config["phase2_prewarm"]
    output_path = resolve_repo_path(config["outputs"]["prewarm_verification"])
    errors: list[str] = []

    def require(condition: bool, reason: str) -> None:
        if not condition:
            errors.append(reason)

    def safe_load(label: str, path: Path) -> dict[str, Any]:
        try:
            return load_json(path)
        except Exception as exc:
            errors.append(f"{label}_invalid_{type(exc).__name__}")
            return {}

    lock_path = resolve_repo_path(spec["lock"])
    prepare_path = resolve_repo_path(spec["prepare_manifest"])
    launcher_path = resolve_repo_path(spec["launcher"])
    script_path = resolve_repo_path(spec["script"])
    manifest_path = resolve_repo_path(spec["manifest"])
    cache_root = resolve_repo_path(spec["shared_torch_extensions"])
    configured_cache = resolve_repo_path(config["outputs"]["torch_extensions"])
    prewarm_log_path = resolve_repo_path(config["outputs"]["prewarm_log"])
    require(int(launcher_exit_code) == 0, f"launcher_exit_{launcher_exit_code}")
    for label, path in (
        ("phase2_lock", lock_path), ("prepare_manifest", prepare_path),
        ("launcher", launcher_path), ("prewarm_script", script_path),
        ("prewarm_manifest", manifest_path), ("prewarm_log", prewarm_log_path),
    ):
        require(path.is_file(), f"{label}_missing")
    require(configured_cache.resolve() == cache_root.resolve(), "phase3_cache_not_shared_phase2_cache")
    implementation = str(spec["implementation_commit"])
    if launcher_path.is_file():
        require(
            sha256_file(launcher_path) == _git_file_sha256(implementation, launcher_path),
            "phase2_launcher_differs_from_implementation_commit",
        )
    if script_path.is_file():
        require(
            sha256_file(script_path) == _git_file_sha256(implementation, script_path),
            "phase2_prewarm_script_differs_from_implementation_commit",
        )

    phase2_lock: dict[str, Any] = {}
    prepare_manifest: dict[str, Any] = {}
    prewarm_manifest: dict[str, Any] = {}
    extension_path: Path | None = None
    extension_sha256: str | None = None
    if lock_path.is_file():
        require(sha256_file(lock_path) == spec["lock_sha256"], "phase2_lock_sha256_mismatch")
        phase2_lock = safe_load("phase2_lock", lock_path)
        locked_cache = resolve_repo_path(
            phase2_lock.get("runtime", {}).get("writable_cache_env", {}).get("TORCH_EXTENSIONS_DIR", "")
        )
        require(locked_cache.resolve() == cache_root.resolve(), "phase2_lock_cache_path_mismatch")
        require(
            image_id_matches(
                phase2_lock.get("runtime", {}).get("docker_image_id"),
                config["containers"]["render_image_id"],
            ),
            "phase2_lock_render_image_id_mismatch",
        )
        locked_contract = phase2_lock.get("runtime", {}).get("gsplat_prewarm", {})
        require(
            resolve_repo_path(locked_contract.get("manifest", "")).resolve() == manifest_path.resolve(),
            "phase2_lock_prewarm_manifest_path_mismatch",
        )
        require(
            resolve_repo_path(locked_contract.get("script", "")).resolve() == script_path.resolve(),
            "phase2_lock_prewarm_script_path_mismatch",
        )
    if prepare_path.is_file():
        require(
            sha256_file(prepare_path) == spec["prepare_manifest_sha256"],
            "phase2_prepare_manifest_sha256_mismatch",
        )
        prepare_manifest = safe_load("phase2_prepare_manifest", prepare_path)
        require(
            str(prepare_manifest.get("lock_sha256", "")) == spec["lock_sha256"],
            "phase2_prepare_manifest_lock_sha256_mismatch",
        )
    if manifest_path.is_file():
        prewarm_manifest = safe_load("prewarm_manifest", manifest_path)
        require(prewarm_manifest.get("schema") == spec["manifest_schema"], "prewarm_schema_mismatch")
        require(prewarm_manifest.get("status") == spec["required_status"], "prewarm_status_not_complete")
        require(prewarm_manifest.get("lock_sha256") == spec["lock_sha256"], "prewarm_lock_sha256_mismatch")
        require(
            image_id_matches(
                prewarm_manifest.get("runtime_attestation", {}).get("docker_image_id"),
                config["containers"]["render_image_id"],
            ),
            "prewarm_render_image_id_mismatch",
        )
        require(
            resolve_repo_path(prewarm_manifest.get("torch_extensions_dir", "")).resolve()
            == cache_root.resolve(),
            "prewarm_cache_path_mismatch",
        )
        require(
            resolve_repo_path(prewarm_manifest.get("script", "")).resolve() == script_path.resolve(),
            "prewarm_script_path_mismatch",
        )
        if script_path.is_file():
            require(
                prewarm_manifest.get("script_sha256") == sha256_file(script_path),
                "prewarm_script_sha256_mismatch",
            )
        manifest_head = str(prewarm_manifest.get("git_head", ""))
        require(
            _git_commit_is_ancestor(implementation, manifest_head),
            "prewarm_git_head_lacks_locked_implementation",
        )
        extension_path = resolve_repo_path(prewarm_manifest.get("extension_path", ""))
        require(extension_path.is_file(), "prewarm_extension_missing")
        try:
            extension_path.resolve().relative_to(cache_root.resolve())
        except ValueError:
            errors.append("prewarm_extension_outside_shared_cache")
        if extension_path.is_file():
            extension_sha256 = sha256_file(extension_path)
            require(
                extension_sha256 == prewarm_manifest.get("extension_sha256"),
                "prewarm_extension_sha256_mismatch",
            )
    result = {
        "schema": "jointbuildgs.s3ap.phase3.gsplat_prewarm_verification.v1",
        "created_utc": utc_now(),
        "status": "complete" if not errors else "failed",
        "launcher_exit_code": int(launcher_exit_code),
        "errors": errors,
        "phase2_lock": rel(lock_path),
        "phase2_lock_sha256": sha256_file(lock_path) if lock_path.is_file() else None,
        "phase2_prepare_manifest": rel(prepare_path),
        "phase2_prepare_manifest_sha256": sha256_file(prepare_path) if prepare_path.is_file() else None,
        "implementation_commit": spec["implementation_commit"],
        "launcher": rel(launcher_path),
        "launcher_sha256": sha256_file(launcher_path) if launcher_path.is_file() else None,
        "prewarm_script": rel(script_path),
        "prewarm_script_sha256": sha256_file(script_path) if script_path.is_file() else None,
        "prewarm_manifest": rel(manifest_path),
        "prewarm_manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        "prewarm_manifest_git_head": prewarm_manifest.get("git_head"),
        "prewarm_log": rel(prewarm_log_path),
        "prewarm_log_sha256": sha256_file(prewarm_log_path) if prewarm_log_path.is_file() else None,
        "render_image_id": config["containers"]["render_image_id"],
        "shared_torch_extensions": rel(cache_root),
        "extension_path": rel(extension_path) if extension_path is not None else None,
        "extension_sha256": extension_sha256,
        "interpretation_or_verdict": None,
    }
    atomic_json(output_path, result)
    if errors:
        raise RuntimeError("Phase-2 gsplat prewarm verification failed: " + ";".join(errors))
    return result


def phase2_prewarm_binding(config: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck the immutable prewarm evidence without writing from workers."""

    spec = config["phase2_prewarm"]
    verification_path = resolve_repo_path(config["outputs"]["prewarm_verification"])
    if not verification_path.is_file():
        raise RuntimeError("Phase-2 prewarm verification is missing")
    verification = load_json(verification_path)
    if verification.get("status") != "complete" or verification.get("errors"):
        raise RuntimeError("Phase-2 prewarm verification is not complete")
    source_expectations = [
        (resolve_repo_path(spec["lock"]), "phase2_lock_sha256", spec["lock_sha256"]),
        (
            resolve_repo_path(spec["prepare_manifest"]),
            "phase2_prepare_manifest_sha256", spec["prepare_manifest_sha256"],
        ),
        (resolve_repo_path(spec["launcher"]), "launcher_sha256", verification.get("launcher_sha256")),
        (resolve_repo_path(spec["script"]), "prewarm_script_sha256", verification.get("prewarm_script_sha256")),
        (resolve_repo_path(spec["manifest"]), "prewarm_manifest_sha256", verification.get("prewarm_manifest_sha256")),
        (
            resolve_repo_path(config["outputs"]["prewarm_log"]),
            "prewarm_log_sha256", verification.get("prewarm_log_sha256"),
        ),
    ]
    paths = [verification_path]
    for path, key, expected in source_expectations:
        if not path.is_file() or sha256_file(path) != expected or verification.get(key) != expected:
            raise RuntimeError(f"Phase-2 prewarm binding mismatch: {key}")
        paths.append(path)
    if verification.get("implementation_commit") != spec["implementation_commit"]:
        raise RuntimeError("Phase-2 prewarm implementation commit mismatch")
    if not image_id_matches(
        verification.get("render_image_id"), config["containers"]["render_image_id"],
    ):
        raise RuntimeError("Phase-2 prewarm render image binding mismatch")
    cache_root = resolve_repo_path(spec["shared_torch_extensions"])
    if resolve_repo_path(config["outputs"]["torch_extensions"]).resolve() != cache_root.resolve():
        raise RuntimeError("Phase-3 TORCH_EXTENSIONS_DIR is not the verified Phase-2 cache")
    extension_path = resolve_repo_path(verification.get("extension_path", ""))
    if not extension_path.is_file():
        raise RuntimeError("verified Phase-2 extension is missing")
    try:
        extension_path.resolve().relative_to(cache_root.resolve())
    except ValueError as exc:
        raise RuntimeError("verified Phase-2 extension lies outside shared cache") from exc
    extension_sha = sha256_file(extension_path)
    if extension_sha != verification.get("extension_sha256"):
        raise RuntimeError("verified Phase-2 extension hash drift")
    paths.append(extension_path)
    bundle = hash_file_bundle(paths)
    return {
        "schema": "jointbuildgs.s3ap.phase3.gsplat_prewarm_binding.v1",
        "verification": rel(verification_path),
        "verification_sha256": sha256_file(verification_path),
        "extension": rel(extension_path),
        "extension_sha256": extension_sha,
        "source_bundle": bundle,
        "digest": canonical_digest({
            "verification_sha256": sha256_file(verification_path),
            "extension_sha256": extension_sha,
            "source_bundle_digest": bundle["digest"],
        }),
    }


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{threading.get_ident()}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def fmt_csv(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.9f}"
    return str(value)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{threading.get_ident()}")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: fmt_csv(row.get(key)) for key in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def finite_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def short_building(value: Any) -> str:
    return str(value or "").strip().removeprefix("DEBY_LOD2_")


def full_building(value: Any) -> str:
    short = short_building(value)
    if not short:
        raise RuntimeError("empty building id")
    return f"DEBY_LOD2_{short}"


def first_value(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def infer_arm(run_id: str, row: Mapping[str, Any]) -> str:
    value = first_value(row, "arm", "arm_name", "cell").lower()
    if value:
        return value
    match = re.search(r"(?:^|[_-])(a[012])(?:[_-]|$)", run_id.lower())
    return match.group(1) if match else ""


def infer_replicate(run_id: str, row: Mapping[str, Any]) -> str:
    value = first_value(row, "replicate", "rep", "run_rep").lower()
    if value:
        return value
    match = re.search(r"(?:^|[_-])(r[12])(?:[_-]|$)", run_id.lower())
    return match.group(1) if match else ""


def infer_perturbation(row: Mapping[str, Any]) -> tuple[str, float]:
    kind = first_value(
        row, "perturbation_type", "perturbation_kind", "perturb_kind", "job_class",
    ).lower()
    height = first_value(row, "height_delta_m", "seed_height_delta_m", "delta_m")
    tilt = first_value(row, "tilt_delta_deg", "tilt_deg", "seed_tilt_delta_deg", "theta_deg")
    generic = first_value(row, "perturbation_value", "perturbation_value_m", "perturb_value")
    if kind in {"tilt", "theta", "tilt_perturbation"}:
        return "tilt", float(tilt or generic or 0.0)
    if kind in {"height", "height_perturbation", "dz"}:
        return "height", float(height or generic or 0.0)
    if kind in {"base", "none", "unperturbed", "base_arm"}:
        return "none", 0.0
    if height and float(height) != 0.0:
        return "height", float(height)
    if tilt and float(tilt) != 0.0:
        return "tilt", float(tilt)
    if generic:
        return kind or "height", float(generic)
    return "none", 0.0


def _training_config_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    metadata = dict(payload.get("s3ap_job") or payload.get("phase2_job") or {})
    for key in (
        "data_root", "output", "out_dir", "building_id", "arm", "replicate",
        "height_delta_m", "tilt_delta_deg", "perturbation_type",
    ):
        if key in payload and key not in metadata:
            metadata[key] = payload[key]
    return metadata


def job_from_row(row: Mapping[str, Any], config: Mapping[str, Any]) -> Job:
    run_id = first_value(row, "run_id", "run_name", "name", "job_id")
    if not run_id:
        raise RuntimeError(f"job inventory row lacks run id: {dict(row)}")
    config_path = first_value(row, "config_path", "config", "generated_config")
    metadata = _training_config_metadata(resolve_repo_path(config_path)) if config_path else {}
    merged: dict[str, Any] = dict(metadata)
    merged.update({key: value for key, value in row.items() if value not in (None, "")})
    building = short_building(first_value(merged, "building_id", "building", "target"))
    if not building:
        match = re.search(r"(?:DEBY_LOD2_)?(4907199|8568391|8568392)", run_id)
        building = match.group(1) if match else ""
    if building not in set(config["targets"]):
        raise RuntimeError(f"run {run_id} has out-of-scope building {building!r}")
    arm = infer_arm(run_id, merged)
    replicate = infer_replicate(run_id, merged)
    kind, perturbation_value = infer_perturbation(merged)
    prepared = first_value(merged, "prepared_root", "data_root", "dataset_root")
    if not prepared:
        prepared = config["phase2"]["prepared_template"].format(building=building)
    checkpoint = first_value(merged, "checkpoint", "final_checkpoint")
    if not checkpoint:
        checkpoint = config["phase2"]["checkpoint_template"].format(run_id=run_id)
    return Job(
        run_id=run_id,
        building_id=building,
        arm=arm,
        replicate=replicate,
        perturbation_type=kind,
        perturbation_value=float(perturbation_value),
        config_path=rel(resolve_repo_path(config_path)) if config_path else "",
        prepared_root=rel(resolve_repo_path(prepared)),
        checkpoint=rel(resolve_repo_path(checkpoint)),
    )


def discover_jobs(config: Mapping[str, Any], inventories: Sequence[str] | None = None) -> list[Job]:
    rows: list[dict[str, str]] = []
    sources = list(inventories or config["phase2"]["job_inventories"])
    for source in sources:
        path = resolve_repo_path(source)
        rows.extend(read_csv(path))
    if not rows:
        root = resolve_repo_path(config["phase2"]["training_root"])
        for checkpoint in sorted(root.glob("*/ckpt/final.pt")):
            run_id = checkpoint.parents[1].name
            effective = checkpoint.parents[1] / "effective_config.json"
            rows.append({"run_id": run_id, "config_path": rel(effective) if effective.exists() else ""})
    jobs = [job_from_row(row, config) for row in rows]
    by_id: dict[str, Job] = {}
    for job in jobs:
        if job.run_id in by_id and by_id[job.run_id] != job:
            raise RuntimeError(f"conflicting duplicate run id in inventories: {job.run_id}")
        by_id[job.run_id] = job
    return [by_id[key] for key in sorted(by_id)]


def inventory_contract(
    config: Mapping[str, Any], jobs: Sequence[Job], inventories: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate the exact locked Phase-2 inventory; never infer completion from files."""

    run_ids = [job.run_id for job in jobs]
    raw_run_ids: list[str] = []
    inventory_sources = list(inventories or config["phase2"]["job_inventories"])
    for source in inventory_sources:
        source_path = resolve_repo_path(source)
        if source_path.is_file():
            raw_run_ids.extend(
                first_value(row, "run_id", "run_name", "name", "job_id")
                for row in read_csv(source_path)
            )
    base = [job for job in jobs if job.perturbation_type == "none"]
    height = [
        job for job in jobs
        if job.perturbation_type == "height" and float(job.perturbation_value) != 0.0
    ]
    tilt = [job for job in jobs if job.perturbation_type == "tilt"]
    recognized = {job.run_id for job in [*base, *height, *tilt]}
    unexpected = sorted(job.run_id for job in jobs if job.run_id not in recognized)
    expected = {
        "base": int(config["phase2"]["base_expected_jobs"]),
        "height_nonzero": int(config["phase2"]["height_nonzero_expected_jobs"]),
        "tilt_when_present": int(config["phase2"]["tilt_expected_jobs_when_inventory_present"]),
    }
    tilt_file_present = any(
        "tilt" in Path(str(source)).name.lower() and resolve_repo_path(source).is_file()
        for source in inventory_sources
    )
    tilt_inventory_present = bool(tilt) or tilt_file_present
    errors: list[str] = []
    if len(run_ids) != len(set(run_ids)):
        errors.append("duplicate_run_ids")
    if raw_run_ids and len(raw_run_ids) != len(set(raw_run_ids)):
        errors.append("duplicate_raw_inventory_run_ids")
    if raw_run_ids and set(raw_run_ids) != set(run_ids):
        errors.append("raw_inventory_ids_do_not_match_discovered_ids")
    if len(base) != expected["base"]:
        errors.append(f"base_count_{len(base)}_expected_{expected['base']}")
    if len(height) != expected["height_nonzero"]:
        errors.append(f"height_count_{len(height)}_expected_{expected['height_nonzero']}")
    if tilt_inventory_present and len(tilt) != expected["tilt_when_present"]:
        errors.append(f"tilt_count_{len(tilt)}_expected_{expected['tilt_when_present']}")
    if unexpected:
        errors.append(f"unexpected_job_classes_{len(unexpected)}")
    targets = {str(value) for value in config["targets"]}
    expected_base_grid = {
        (building, arm, replicate)
        for building in targets for arm in ("a0", "a1", "a2")
        for replicate in ("r1", "r2")
    }
    actual_base_grid = {
        (job.building_id, job.arm.lower(), job.replicate.lower()) for job in base
    }
    expected_height_values = {
        float(value) for value in config["perturbation"]["height_deltas_m"]
        if float(value) != 0.0
    }
    expected_height_grid = {
        (building, "a1", "r1", value)
        for building in targets for value in expected_height_values
    }
    actual_height_grid = {
        (job.building_id, job.arm.lower(), job.replicate.lower(), float(job.perturbation_value))
        for job in height
    }
    expected_tilt_values = {float(value) for value in config["perturbation"]["tilt_deltas_deg"]}
    expected_tilt_grid = {
        (building, "a1", "r1", value)
        for building in targets for value in expected_tilt_values
    }
    actual_tilt_grid = {
        (job.building_id, job.arm.lower(), job.replicate.lower(), float(job.perturbation_value))
        for job in tilt
    }
    if actual_base_grid != expected_base_grid or len(base) != len(actual_base_grid):
        errors.append("base_tuple_grid_mismatch")
    if actual_height_grid != expected_height_grid or len(height) != len(actual_height_grid):
        errors.append("height_tuple_grid_mismatch")
    if tilt_inventory_present and (
        actual_tilt_grid != expected_tilt_grid or len(tilt) != len(actual_tilt_grid)
    ):
        errors.append("tilt_tuple_grid_mismatch")
    return {
        "status": "complete" if not errors else "failed",
        "errors": errors, "current_run_ids": sorted(run_ids),
        "raw_inventory_row_count": len(raw_run_ids),
        "counts": {
            "total": len(jobs), "base": len(base),
            "height_nonzero": len(height), "tilt": len(tilt),
        },
        "expected": expected, "tilt_inventory_present": tilt_inventory_present,
        "tilt_inventory_file_present": tilt_file_present,
        "tuple_grid": {
            "base_expected": len(expected_base_grid), "base_actual": len(actual_base_grid),
            "height_expected": len(expected_height_grid), "height_actual": len(actual_height_grid),
            "tilt_expected_when_present": len(expected_tilt_grid),
            "tilt_actual": len(actual_tilt_grid),
        },
        "unexpected_run_ids": unexpected,
    }


def run_gpu_serial_queues(
    jobs: Sequence[Job], gpu_ids: Sequence[str], run_fn: Any,
) -> list[tuple[Job, str, BaseException]]:
    """Consume one shared queue with exactly one worker thread per GPU."""

    if not gpu_ids:
        raise RuntimeError("at least one GPU queue is required")
    work: queue.Queue[Job] = queue.Queue()
    for job in jobs:
        work.put(job)
    errors: list[tuple[Job, str, BaseException]] = []
    error_lock = threading.Lock()

    def worker(gpu_id: str) -> None:
        while True:
            try:
                job = work.get_nowait()
            except queue.Empty:
                return
            try:
                run_fn(job, gpu_id)
            except BaseException as exc:  # keep other jobs running by contract
                with error_lock:
                    errors.append((job, gpu_id, exc))
            finally:
                work.task_done()

    threads = [
        threading.Thread(target=worker, args=(str(gpu_id),), name=f"s3ap-gpu-{gpu_id}")
        for gpu_id in gpu_ids
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def occupied_cell_union(points_xy: Any, grid_m: float) -> Any:
    """Union globally aligned occupied cells; accepts no footprint geometry."""

    import numpy as np
    from shapely import make_valid
    from shapely.geometry import GeometryCollection, box
    from shapely.ops import unary_union

    xy = np.asarray(points_xy, dtype=np.float64).reshape(-1, 2)
    keys = sorted({
        (math.floor(float(x) / grid_m), math.floor(float(y) / grid_m))
        for x, y in xy if math.isfinite(float(x)) and math.isfinite(float(y))
    })
    if not keys:
        return GeometryCollection()
    return make_valid(unary_union([
        box(ix * grid_m, iy * grid_m, (ix + 1) * grid_m, (iy + 1) * grid_m)
        for ix, iy in keys
    ]))


def coverage_by_region(points_xy: Any, footprint: Any, grid_m: float, edge_width_m: float) -> dict[str, Any]:
    """Globally aligned 0.5 m coverage split by <=1 m boundary distance."""

    import numpy as np
    from shapely.geometry import Point, box

    xy = np.asarray(points_xy, dtype=np.float64).reshape(-1, 2)
    minx, miny, maxx, maxy = footprint.bounds
    eligible: dict[tuple[int, int], str] = {}
    for ix in range(math.floor(minx / grid_m), math.ceil(maxx / grid_m)):
        for iy in range(math.floor(miny / grid_m), math.ceil(maxy / grid_m)):
            cell = box(ix * grid_m, iy * grid_m, (ix + 1) * grid_m, (iy + 1) * grid_m)
            overlap = footprint.intersection(cell)
            if overlap.is_empty or overlap.area <= 1e-12:
                continue
            representative = overlap.representative_point()
            region = "edge" if representative.distance(footprint.boundary) <= edge_width_m else "interior"
            eligible[(ix, iy)] = region
    occupied = {
        (math.floor(float(x) / grid_m), math.floor(float(y) / grid_m))
        for x, y in xy
        if math.isfinite(float(x)) and math.isfinite(float(y))
        and footprint.covers(Point(float(x), float(y)))
    } & set(eligible)

    def summary(region: str | None) -> tuple[int, int, float]:
        allowed = {key for key, value in eligible.items() if region is None or value == region}
        count = len(occupied & allowed)
        return len(allowed), count, count / len(allowed) if allowed else 0.0

    all_stats = summary(None)
    edge_stats = summary("edge")
    interior_stats = summary("interior")
    return {
        "all": {"eligible": all_stats[0], "occupied": all_stats[1], "ratio": all_stats[2]},
        "edge": {"eligible": edge_stats[0], "occupied": edge_stats[1], "ratio": edge_stats[2]},
        "interior": {"eligible": interior_stats[0], "occupied": interior_stats[1], "ratio": interior_stats[2]},
    }


def substantive_classification(
    *,
    roofer_status: str,
    extrusion_mode: str,
    roof_planes: Any,
    geometry_has_lod22: bool,
    val3dity_valid: bool,
    completeness: float | None,
    roof_rms_m: float | None,
    lock: Mapping[str, Any],
) -> dict[str, bool]:
    """Keep raw LoD2.2 geometry distinct from accepted/substantive output."""

    try:
        plane_count = int(float(str(roof_planes)))
    except (TypeError, ValueError):
        plane_count = 0
    canonical = bool(
        str(roofer_status) == str(lock["roofer_status"])
        and str(extrusion_mode) not in set(lock["forbidden_extrusion_modes"])
        and plane_count >= int(lock["minimum_roof_planes"])
    )
    accepted = bool(geometry_has_lod22 and canonical)
    substantive = bool(
        accepted
        and val3dity_valid
        and completeness is not None
        and completeness >= float(lock["minimum_completeness"])
        and roof_rms_m is not None
        and roof_rms_m <= float(lock["maximum_roof_rms_m"])
    )
    return {
        "geometry_has_lod22": bool(geometry_has_lod22),
        "canonical_readout": canonical,
        "has_lod22": accepted,
        "substantive_filter": substantive,
    }


def perturbation_trigger(rows: Sequence[Mapping[str, Any]], rule: str) -> dict[str, Any]:
    """Exact, tolerance-free conditional tilt trigger."""

    candidates: list[dict[str, Any]] = []
    for row in rows:
        delta = finite_float(row.get("delta_m"))
        post = finite_float(row.get("post_gs_signed_median_error_m"))
        seed = finite_float(row.get("perturbed_p0_signed_median_error_m"))
        eligible = bool(
            str(row.get("arm", "")).lower() == "a1"
            and str(row.get("replicate", "")).lower() == "r1"
            and delta is not None and delta != 0.0
            and post is not None and seed is not None
            and str(row.get("score_status", "")) == "complete"
        )
        condition = bool(eligible and abs(post) < abs(seed))
        if eligible:
            candidates.append({
                "run_id": str(row.get("run_id", "")),
                "building_id": str(row.get("building_id", "")),
                "delta_m": delta,
                "post_gs_abs_signed_median_error_m": abs(post),
                "perturbed_p0_abs_signed_median_error_m": abs(seed),
                "condition_met": condition,
            })
    qualifying = [row for row in candidates if row["condition_met"]]
    return {
        "schema": "jointbuildgs.s3ap.return_signal.v1",
        "created_utc": utc_now(),
        "return_signal": bool(qualifying),
        "rule": rule,
        "equality_counts_as_return": False,
        "numeric_tolerance": None,
        "candidate_count": len(candidates),
        "qualifying_count": len(qualifying),
        "candidates": candidates,
        "qualifying": qualifying,
    }


def _load_job_spec(path: Path) -> tuple[Job, dict[str, Any]]:
    payload = load_json(path)
    job_payload = payload.get("job", payload)
    job = Job(
        run_id=str(job_payload["run_id"]),
        building_id=short_building(job_payload["building_id"]),
        arm=str(job_payload.get("arm", "")),
        replicate=str(job_payload.get("replicate", "")),
        perturbation_type=str(job_payload.get("perturbation_type", "none")),
        perturbation_value=float(job_payload.get("perturbation_value", 0.0)),
        config_path=str(job_payload.get("config_path", "")),
        prepared_root=str(job_payload["prepared_root"]),
        checkpoint=str(job_payload["checkpoint"]),
    )
    return job, payload


def _load_world_offset(config: Mapping[str, Any]) -> Any:
    import numpy as np

    manifest = load_json(resolve_repo_path(config["extraction"]["world_offset_manifest"]))
    offset = np.asarray(manifest["world_offset"], dtype=np.float64)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise RuntimeError("world_offset must be a finite three-vector")
    return offset


def _sor(points: Any, counts: Any, neighbors: int, std_ratio: float) -> tuple[Any, Any, str]:
    import numpy as np

    xyz = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    obs = np.asarray(counts, dtype=np.int64).reshape(-1)
    if len(xyz) != len(obs):
        raise RuntimeError("SOR point/count length mismatch")
    if len(xyz) == 0:
        return xyz, obs, "empty"
    try:
        import open3d as o3d

        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(xyz)
        cleaned, indices = cloud.remove_statistical_outlier(
            nb_neighbors=int(neighbors), std_ratio=float(std_ratio),
        )
        index = np.asarray(indices, dtype=np.int64)
        return np.asarray(cleaned.points, dtype=np.float64), obs[index], "applied"
    except Exception as exc:  # preserve an auditable partial extraction.
        return xyz, obs, f"error:{type(exc).__name__}:{exc}"


def _decode_voxel_keys(keys: Any, voxel_m: float, world_offset: Any) -> Any:
    import numpy as np

    off = 1 << 20
    mul = 1 << 21
    packed = np.asarray(keys, dtype=np.int64).copy()
    iz = (packed % mul) - off
    packed //= mul
    iy = (packed % mul) - off
    ix = (packed // mul) - off
    local = (np.stack([ix, iy, iz], axis=1).astype(np.float64) + 0.5) * float(voxel_m)
    return local + np.asarray(world_offset, dtype=np.float64)[None, :]


def _fuse_key_chunks(
    chunks: Sequence[Any],
    *,
    voxel_m: float,
    min_observations: int,
    world_offset: Any,
    sor_neighbors: int,
    sor_std_ratio: float,
) -> dict[str, Any]:
    import numpy as np
    import torch

    if not chunks:
        empty_xyz = np.empty((0, 3), dtype=np.float64)
        empty_count = np.empty(0, dtype=np.int64)
        return {
            "all": empty_xyz, "all_counts": empty_count,
            "minobs": empty_xyz.copy(), "minobs_counts": empty_count.copy(),
            "clean": empty_xyz.copy(), "clean_counts": empty_count.copy(),
            "sor_status": "empty",
        }
    all_keys = torch.cat([chunk.to(torch.int64).cpu() for chunk in chunks])
    unique, counts = torch.unique(all_keys, return_counts=True)
    keep = counts >= int(min_observations)
    all_xyz = _decode_voxel_keys(unique.numpy(), voxel_m, world_offset)
    minobs_xyz = _decode_voxel_keys(unique[keep].numpy(), voxel_m, world_offset)
    all_counts = counts.numpy().astype(np.int64)
    minobs_counts = counts[keep].numpy().astype(np.int64)
    clean_xyz, clean_counts, sor_status = _sor(
        minobs_xyz, minobs_counts, sor_neighbors, sor_std_ratio,
    )
    return {
        "all": all_xyz, "all_counts": all_counts,
        "minobs": minobs_xyz, "minobs_counts": minobs_counts,
        "clean": clean_xyz, "clean_counts": clean_counts,
        "sor_status": sor_status,
    }


def extract_job(args: argparse.Namespace) -> None:
    """GPU worker: fixed-view render and footprint-free multi-view fusion."""

    import numpy as np
    import torch

    sys.path.insert(0, str(REPO))
    from gsplat import rasterization_2dgs
    from src.stage2.colmap_io import read_cameras_bin, read_images_bin

    config_path = Path(args.config)
    config = load_json(config_path)
    job, _ = _load_job_spec(Path(args.job_spec))
    pre_fingerprint = pre_readout_fingerprint(config_path, config, job)
    checkpoint = resolve_repo_path(job.checkpoint)
    prepared_root = resolve_repo_path(job.prepared_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "extract_progress.json"
    output_npz = output_dir / "fused_depth.npz"
    metrics_path = output_dir / "extraction_manifest.json"
    atomic_json(progress_path, {
        "schema": "jointbuildgs.s3ap.phase3.extract.progress.v1",
        "run_id": job.run_id, "stage": "checkpoint_load", "status": "started",
        "updated_utc": utc_now(),
    })
    if not checkpoint.exists():
        raise FileNotFoundError(checkpoint)
    sparse = prepared_root / "sparse"
    if (sparse / "0" / "cameras.bin").exists():
        sparse = sparse / "0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    images = sorted(read_images_bin(sparse / "images.bin").values(), key=lambda item: item.name)
    if not images:
        raise RuntimeError(f"prepared crop contains zero COLMAP views: {prepared_root}")
    payload = torch.load(checkpoint, map_location="cuda", weights_only=False)
    if not isinstance(payload, dict) or "state_dict" not in payload:
        raise RuntimeError("checkpoint lacks state_dict")
    state = payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "shN"}
    missing = sorted(required - set(state))
    if missing:
        raise RuntimeError(f"checkpoint missing render tensors: {missing}")
    device = torch.device("cuda")
    means = state["means"].to(device)
    quats = state["quats"].to(device)
    scales = torch.exp(state["log_scales"]).to(device)
    opacities = torch.sigmoid(state["opacities_raw"]).to(device).reshape(-1)
    colors = torch.cat([state["sh0"], state["shN"]], dim=1).to(device)
    ext = config["extraction"]
    alpha_min = float(ext["alpha_min_inclusive"])
    depth_min = float(ext["depth_min_m_exclusive"])
    depth_max = float(ext["depth_max_m_exclusive"])
    voxel_m = float(ext["voxel_m"])
    min_obs = int(ext["min_observations"])
    off = 1 << 20
    mul = 1 << 21
    chunks: dict[str, list[Any]] = {"expected": [], "median": []}
    view_rows: list[dict[str, Any]] = []

    def add_unique_keys(points: Any, variant: str) -> None:
        q = torch.floor(points / voxel_m).to(torch.int64) + off
        if torch.any(q < 0) or torch.any(q >= mul):
            raise RuntimeError(f"voxel key range exceeded for {variant}")
        packed = (q[:, 0] * mul + q[:, 1]) * mul + q[:, 2]
        chunks[variant].append(torch.unique(packed).cpu())

    for index, image in enumerate(images):
        camera = cameras[image.camera_id]
        width, height = int(camera.width), int(camera.height)
        k_np = camera.K().astype(np.float64)
        k = torch.tensor(k_np, dtype=torch.float32, device=device)
        r = torch.tensor(image.R(), dtype=torch.float32, device=device)
        t = torch.tensor(image.tvec, dtype=torch.float32, device=device)
        viewmat = torch.eye(4, dtype=torch.float32, device=device)
        viewmat[:3, :3] = r
        viewmat[:3, 3] = t
        with torch.no_grad():
            output = rasterization_2dgs(
                means=means, quats=quats, scales=scales, opacities=opacities,
                colors=colors, viewmats=viewmat.unsqueeze(0), Ks=k.unsqueeze(0),
                width=width, height=height, near_plane=0.01, far_plane=1e10,
                render_mode="RGB+ED", depth_mode="expected",
                sh_degree=int(ext["sh_degree"]),
            )
        alpha = output[1][0, ..., 0]
        expected = output[0][0, ..., 3]
        median = output[5][0, ..., 0]
        v, u = torch.meshgrid(
            torch.arange(height, dtype=torch.float32, device=device),
            torch.arange(width, dtype=torch.float32, device=device),
            indexing="ij",
        )
        row: dict[str, Any] = {
            "view_index": index, "view_name": image.name,
            "width": width, "height": height,
            "alpha_ge_threshold_pixels": int((alpha >= alpha_min).sum().item()),
        }
        for variant, depth in (("expected", expected), ("median", median)):
            valid = (
                torch.isfinite(alpha) & torch.isfinite(depth)
                & (alpha >= alpha_min) & (depth > depth_min) & (depth < depth_max)
            )
            row[f"{variant}_valid_pixels"] = int(valid.sum().item())
            if not torch.any(valid):
                continue
            z = depth[valid]
            x = (u[valid] - k[0, 2]) / k[0, 0] * z
            y = (v[valid] - k[1, 2]) / k[1, 1] * z
            camera_xyz = torch.stack([x, y, z], dim=1)
            world_local = (camera_xyz - t) @ r
            finite = torch.isfinite(world_local).all(dim=1)
            selected_world_local = world_local[finite]  # exactly one selection; no duplicate [keep].
            row[f"{variant}_finite_world_pixels"] = int(len(selected_world_local))
            if len(selected_world_local):
                add_unique_keys(selected_world_local, variant)
        view_rows.append(row)
        atomic_json(progress_path, {
            "schema": "jointbuildgs.s3ap.phase3.extract.progress.v1",
            "run_id": job.run_id, "stage": "render_views", "status": "running",
            "completed_views": index + 1, "total_views": len(images),
            "last_view": image.name, "updated_utc": utc_now(),
        })

    world_offset = _load_world_offset(config)
    fused = {
        variant: _fuse_key_chunks(
            chunks[variant], voxel_m=voxel_m, min_observations=min_obs,
            world_offset=world_offset,
            sor_neighbors=int(ext["sor_neighbors"]),
            sor_std_ratio=float(ext["sor_std_ratio"]),
        )
        for variant in ("expected", "median")
    }
    save: dict[str, Any] = {
        "world_offset": world_offset,
        "voxel_m": np.asarray(voxel_m),
        "min_observations": np.asarray(min_obs),
        "alpha_min_inclusive": np.asarray(alpha_min),
        "view_names": np.asarray([image.name for image in images]),
    }
    for variant, result in fused.items():
        for stage in ("all", "minobs", "clean"):
            save[f"P_utm_{variant}_{stage}"] = result[stage]
            save[f"observation_count_{variant}_{stage}"] = result[f"{stage}_counts"]
    tmp_npz = output_npz.with_name(output_npz.name + ".tmp.npz")
    np.savez_compressed(tmp_npz, **save)
    os.replace(tmp_npz, output_npz)
    manifest = {
        "schema": "jointbuildgs.s3ap.phase3.extraction.v1",
        "created_utc": utc_now(), "job": asdict(job),
        "checkpoint": rel(checkpoint), "checkpoint_sha256": sha256_file(checkpoint),
        "pre_readout_fingerprint": pre_fingerprint,
        "prepared_root": rel(prepared_root),
        "fixed_view_count": len(images), "fixed_views": [image.name for image in images],
        "render": {
            "alpha_rule": f"alpha >= {alpha_min}",
            "depth_variants": ["expected", "median"],
            "canonical_depth": ext["canonical_depth"],
            "depth_valid_range_m": [depth_min, depth_max],
            "sh_degree": int(ext["sh_degree"]),
        },
        "fusion": {
            "voxel_m": voxel_m, "min_observations": min_obs,
            "observation_definition": "per-view unique voxel occurrence",
            "sor_neighbors": int(ext["sor_neighbors"]),
            "sor_std_ratio": float(ext["sor_std_ratio"]),
            "expected": {
                "fused_all": len(fused["expected"]["all"]),
                "minobs_kept": len(fused["expected"]["minobs"]),
                "sor_kept": len(fused["expected"]["clean"]),
                "sor_status": fused["expected"]["sor_status"],
            },
            "median": {
                "fused_all": len(fused["median"]["all"]),
                "minobs_kept": len(fused["median"]["minobs"]),
                "sor_kept": len(fused["median"]["clean"]),
                "sor_status": fused["median"]["sor_status"],
            },
        },
        "spatial_filter": "none; no footprint/LoD2/ALS opened",
        "gt_used": False, "lod2_used": False, "als_used": False,
        "view_rows": view_rows,
        "output_npz": rel(output_npz), "output_sha256": sha256_file(output_npz),
    }
    atomic_json(metrics_path, manifest)
    atomic_json(progress_path, {
        "schema": "jointbuildgs.s3ap.phase3.extract.progress.v1",
        "run_id": job.run_id, "stage": "complete", "status": "complete",
        "updated_utc": utc_now(), "manifest": rel(metrics_path),
    })
    print(json.dumps({
        "run_id": job.run_id, "status": "complete", "manifest": rel(metrics_path),
        "median_sor_kept": len(fused["median"]["clean"]),
    }, ensure_ascii=False))


def _observed_ground(path: Path, building: str) -> dict[str, Any]:
    matches: list[dict[str, str]] = []
    for row in read_csv(path):
        if row.get("row_type") != "building_summary":
            continue
        if short_building(row.get("building_id")) == short_building(building):
            matches.append(row)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one observed-ground building_summary for {building}, got {len(matches)}"
        )
    row = matches[0]
    z_local = finite_float(row.get("ground_z_local_m"))
    if z_local is None:
        raise RuntimeError(f"non-finite observed ground for {building}")
    return {
        "z_local_m": z_local,
        "method": row.get("ground_method", ""),
        "source": row.get("ground_source", ""),
        "source_csv": rel(path),
        "source_sha256": sha256_file(path),
    }


def _write_las(path: Path, xyz: Any, classification: Any, crs_epsg: int = 25832) -> None:
    import laspy
    import numpy as np
    from pyproj import CRS

    points = np.asarray(xyz, dtype=np.float64).reshape(-1, 3)
    classes = np.asarray(classification, dtype=np.uint8).reshape(-1)
    if len(points) != len(classes) or not len(points):
        raise RuntimeError("LAS requires nonempty equal-length xyz/classification")
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.floor(points.min(axis=0))
    header.add_crs(CRS.from_epsg(crs_epsg))
    cloud = laspy.LasData(header)
    cloud.x, cloud.y, cloud.z = points[:, 0], points[:, 1], points[:, 2]
    cloud.classification = classes
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.las")
    cloud.write(tmp)
    os.replace(tmp, path)


def prepare_roofer_job(args: argparse.Namespace) -> None:
    """CPU worker: construct footprint-free Roofer LAS and derived roofprint."""

    import numpy as np
    from shapely.geometry import mapping

    config_path = Path(args.config)
    config = load_json(config_path)
    job, _ = _load_job_spec(Path(args.job_spec))
    output_dir = Path(args.output_dir)
    extraction_path = output_dir / "fused_depth.npz"
    extraction_manifest_path = output_dir / "extraction_manifest.json"
    input_npz = output_dir / "roofer_input.npz"
    las_path = output_dir / "gs_roof_with_observed_ground_classified.las"
    roofprint_path = output_dir / "gs_point_evidence_derived_roofprint.geojson"
    manifest_path = output_dir / "roofer_input_manifest.json"
    if not extraction_path.exists() or not extraction_manifest_path.exists():
        raise RuntimeError("extraction outputs missing")
    extraction_manifest = load_json(extraction_manifest_path)
    current_pre_fingerprint = pre_readout_fingerprint(config_path, config, job)
    if extraction_manifest.get("pre_readout_fingerprint", {}).get("digest") != current_pre_fingerprint["digest"]:
        raise RuntimeError("pre-readout inputs changed between extraction and Roofer input preparation")
    canonical = str(config["extraction"]["canonical_depth"])
    archive = np.load(extraction_path, allow_pickle=False)
    key = f"P_utm_{canonical}_clean"
    if key not in archive.files:
        raise RuntimeError(f"canonical fusion key missing: {key}")
    fused = np.asarray(archive[key], dtype=np.float64).reshape(-1, 3)
    offset = np.asarray(archive["world_offset"], dtype=np.float64)
    ground_spec = _observed_ground(
        resolve_repo_path(config["roof_evidence"]["ground_source_csv"]),
        job.building_id,
    )
    ground_world_z = float(ground_spec["z_local_m"]) + float(offset[2])
    clearance = float(config["roof_evidence"]["minimum_height_above_observed_ground_m"])
    finite = np.isfinite(fused).all(axis=1)
    roof = fused[finite & (fused[:, 2] >= ground_world_z + clearance)]
    grid_m = float(config["roof_evidence"]["derived_roofprint_grid_m"])
    geom = occupied_cell_union(roof[:, :2], grid_m)
    status = "prepared" if len(roof) and not geom.is_empty else "no_roof_evidence"
    ground = roof.copy()
    if len(ground):
        ground[:, 2] = ground_world_z
    tmp_npz = input_npz.with_name(input_npz.name + ".tmp.npz")
    np.savez_compressed(
        tmp_npz,
        P_roof_utm=roof,
        P_ground_utm=ground,
        ground_world_z_m=np.asarray(ground_world_z),
        canonical_depth=np.asarray(canonical),
    )
    os.replace(tmp_npz, input_npz)
    if status == "prepared":
        feature = {
            "type": "Feature",
            "properties": {
                "building_id": full_building(job.building_id),
                "source": "gs_fused_roof_evidence_occupied_cell_union",
                "grid_m": grid_m,
                "point_count": int(len(roof)),
            },
            "geometry": mapping(geom),
        }
        atomic_json(roofprint_path, {
            "type": "FeatureCollection",
            "name": "gs_point_evidence_derived_roofprint",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
            "features": [feature],
        })
        xyz = np.vstack([roof, ground])
        classification = np.concatenate([
            np.full(len(roof), int(config["roof_evidence"]["roof_class"]), dtype=np.uint8),
            np.full(len(ground), int(config["roof_evidence"]["ground_class"]), dtype=np.uint8),
        ])
        _write_las(las_path, xyz, classification)
    else:
        for stale in (las_path, roofprint_path):
            if stale.exists():
                stale.unlink()
    manifest = {
        "schema": "jointbuildgs.s3ap.phase3.roofer_input.v1",
        "created_utc": utc_now(), "job": asdict(job), "status": status,
        "source_extraction_manifest": rel(extraction_manifest_path),
        "source_extraction_sha256": sha256_file(extraction_path),
        "pre_readout_fingerprint": current_pre_fingerprint,
        "canonical_depth": canonical,
        "canonical_fused_clean_point_count": int(len(fused)),
        "roof_evidence_point_count": int(len(roof)),
        "roof_evidence_rule": f"z_world >= observed_ground_world + {clearance} m",
        "observed_ground": ground_spec,
        "ground_world_z_m": ground_world_z,
        "derived_roofprint_rule": config["roof_evidence"]["derived_roofprint_rule"],
        "derived_roofprint_grid_m": grid_m,
        "derived_roofprint_area_m2": float(geom.area) if not geom.is_empty else 0.0,
        "supplied_footprint_opened": False,
        "supplied_footprint_passed_to_roofer": False,
        "lod2_opened": False,
        "als_opened": False,
        "point_evidence_derived_roofprint_passed_to_roofer": status == "prepared",
        "roofer_las": rel(las_path) if status == "prepared" else "",
        "roofer_las_sha256": sha256_file(las_path) if las_path.exists() else "",
        "derived_roofprint": rel(roofprint_path) if status == "prepared" else "",
        "derived_roofprint_sha256": sha256_file(roofprint_path) if roofprint_path.exists() else "",
        "roofer_input_npz": rel(input_npz),
        "roofer_input_npz_sha256": sha256_file(input_npz),
        "gt_used": False, "lod2_used": False, "als_used": False,
        "extraction_contract": {
            "fixed_view_count": extraction_manifest["fixed_view_count"],
            "alpha_rule": extraction_manifest["render"]["alpha_rule"],
            "voxel_m": extraction_manifest["fusion"]["voxel_m"],
            "min_observations": extraction_manifest["fusion"]["min_observations"],
        },
    }
    atomic_json(manifest_path, manifest)
    print(json.dumps({
        "run_id": job.run_id, "status": status,
        "roof_evidence_point_count": len(roof), "manifest": rel(manifest_path),
    }, ensure_ascii=False))


def _height_metrics(residuals: Any) -> dict[str, float | None]:
    import numpy as np

    dz = np.asarray(residuals, dtype=np.float64).reshape(-1)
    dz = dz[np.isfinite(dz)]
    if not len(dz):
        return {"signed_median": None, "abs_median": None, "mad": None, "rms": None}
    median = float(np.median(dz))
    return {
        "signed_median": median,
        "abs_median": float(np.median(np.abs(dz))),
        "mad": float(np.median(np.abs(dz - median))),
        "rms": float(np.sqrt(np.mean(dz * dz))),
    }


def _inside_and_region(points: Any, footprint: Any, edge_width_m: float) -> tuple[Any, Any, Any]:
    import numpy as np
    from shapely import contains_xy
    from shapely.geometry import Point, box

    xyz = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if not len(xyz):
        empty = np.zeros(0, dtype=bool)
        return empty, empty, empty
    inside = contains_xy(footprint, xyz[:, 0], xyz[:, 1])
    # Include exact boundary samples as score-region points.
    boundary_candidates = np.flatnonzero(~inside)
    for index in boundary_candidates:
        inside[index] = footprint.covers(Point(float(xyz[index, 0]), float(xyz[index, 1])))
    edge = np.zeros(len(xyz), dtype=bool)
    for index in np.flatnonzero(inside):
        edge[index] = Point(float(xyz[index, 0]), float(xyz[index, 1])).distance(footprint.boundary) <= edge_width_m
    interior = inside & ~edge
    return inside, edge, interior


def _sample_citygml_roof(surfaces: Sequence[Any], footprint: Any, grid_m: float) -> Any:
    """Sample assembled roof faces on the locked globally aligned score grid."""

    import numpy as np
    from shapely.geometry import Point, box

    if not surfaces:
        return np.empty((0, 3), dtype=np.float64)
    minx, miny, maxx, maxy = footprint.bounds
    rows: list[tuple[float, float, float]] = []
    for ix in range(math.floor(minx / grid_m), math.ceil(maxx / grid_m)):
        for iy in range(math.floor(miny / grid_m), math.ceil(maxy / grid_m)):
            cell = box(ix * grid_m, iy * grid_m, (ix + 1) * grid_m, (iy + 1) * grid_m)
            overlap = footprint.intersection(cell)
            if overlap.is_empty or overlap.area <= 1e-12:
                continue
            representative = overlap.representative_point()
            x, y = float(representative.x), float(representative.y)
            candidate_z: list[float] = []
            for surface in surfaces:
                if surface.polygon.covers(Point(x, y)):
                    value = float(surface.z_at(np.asarray([x]), np.asarray([y]))[0])
                    if math.isfinite(value):
                        candidate_z.append(value)
            if candidate_z:
                rows.append((x, y, max(candidate_z)))
    return np.asarray(rows, dtype=np.float64).reshape(-1, 3)


def perturbation_cell_rows(
    *,
    job: Job,
    p0_points: Any,
    p0_residuals: Any,
    gs_points: Any,
    gs_residuals: Any,
    footprint: Any,
    edge_width_m: float,
    grid_m: float,
    score_status: str,
) -> list[dict[str, Any]]:
    """Measure seed return on the same globally aligned spatial cells."""

    import numpy as np
    from shapely.geometry import Point, box

    p0_xyz = np.asarray(p0_points, dtype=np.float64).reshape(-1, 3)
    p0_dz = np.asarray(p0_residuals, dtype=np.float64).reshape(-1)
    gs_xyz = np.asarray(gs_points, dtype=np.float64).reshape(-1, 3)
    gs_dz = np.asarray(gs_residuals, dtype=np.float64).reshape(-1)
    if len(p0_xyz) != len(p0_dz) or len(gs_xyz) != len(gs_dz):
        raise RuntimeError("cell residual arrays do not match point arrays")

    def groups(xyz: Any, dz: Any) -> dict[tuple[int, int], list[float]]:
        result: dict[tuple[int, int], list[float]] = {}
        for point, value in zip(xyz, dz):
            x, y = float(point[0]), float(point[1])
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(float(value))):
                continue
            if not footprint.covers(Point(x, y)):
                continue
            result.setdefault((math.floor(x / grid_m), math.floor(y / grid_m)), []).append(float(value))
        return result

    p0_cells = groups(p0_xyz, p0_dz)
    gs_cells = groups(gs_xyz, gs_dz)
    delta = float(job.perturbation_value if job.perturbation_type == "height" else 0.0)
    rows: list[dict[str, Any]] = []
    for (ix, iy), base_values in sorted(p0_cells.items()):
        x = (ix + 0.5) * grid_m
        y = (iy + 0.5) * grid_m
        representative = Point(x, y)
        if not footprint.covers(representative):
            overlap = footprint.intersection(box(
                ix * grid_m, iy * grid_m, (ix + 1) * grid_m, (iy + 1) * grid_m,
            ))
            if overlap.is_empty:
                continue
            representative = overlap.representative_point()
            x, y = float(representative.x), float(representative.y)
        base = float(np.median(np.asarray(base_values, dtype=np.float64)))
        perturbed = base + delta
        post_values = gs_cells.get((ix, iy), [])
        post = float(np.median(np.asarray(post_values, dtype=np.float64))) if post_values else None
        return_amount = abs(perturbed) - abs(post) if post is not None else None
        condition = bool(
            score_status == "complete" and delta != 0.0
            and post is not None and abs(post) < abs(perturbed)
        )
        rows.append({
            "run_id": job.run_id, "building_id": full_building(job.building_id),
            "arm": job.arm, "replicate": job.replicate, "delta_m": delta,
            "cell_ix": ix, "cell_iy": iy, "cell_center_x": x, "cell_center_y": y,
            "region": "edge" if representative.distance(footprint.boundary) <= edge_width_m else "interior",
            "p0_base_signed_error_m": base,
            "perturbed_p0_signed_error_m": perturbed,
            "perturbed_p0_abs_error_m": abs(perturbed),
            "post_gs_point_count": len(post_values),
            "post_gs_signed_error_m": post,
            "post_gs_abs_error_m": abs(post) if post is not None else None,
            "return_amount_m": return_amount, "return_condition_met": condition,
            "coverage_grid_m": grid_m, "score_status": score_status,
        })
    return rows


def _combine_and_validate_roofer(
    output_dir: Path,
    building_id: str,
    roofer_exit_code: int,
) -> tuple[Path | None, dict[str, Any], Path | None, Path | None]:
    """Finalize Roofer before any GT or supplied footprint is opened."""

    cityjson = output_dir / "cityjson" / f"{output_dir.name}.city.json"
    val_report = output_dir / "val3dity" / f"{output_dir.name}.report.json"
    val_log = output_dir / "val3dity" / f"{output_dir.name}.log"
    jsonl = sorted((output_dir / "roofer").glob("**/*.city.jsonl"))
    empty_status = {
        "building_id": building_id, "status": "not_run", "reason": "",
        "rf_extrusion_mode": "", "rf_roof_planes": "", "has_lod22": False,
        "val3dity_valid": False,
    }
    if roofer_exit_code != 0:
        empty_status.update(status="failed", reason=f"roofer_exit_{roofer_exit_code}")
        return None, empty_status, None, None
    if not jsonl:
        empty_status.update(status="failed", reason="missing_roofer_cityjsonseq")
        return None, empty_status, None, None
    w2 = load_module(f"s3ap_phase3_w2_{os.getpid()}_{threading.get_ident()}", W2_SCRIPT)
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    roofer_feature = _combine_roofer_component_cityjsonseq(
        jsonl, cityjson, building_id, w2,
    )
    val_report.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["val3dity", str(cityjson), "--report", str(val_report)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    atomic_text(
        val_log,
        "+ val3dity " + str(cityjson) + " --report " + str(val_report) + "\n"
        + (proc.stdout or ""),
    )
    val_by_id: dict[str, Any] = {}
    if val_report.exists():
        payload = load_json(val_report)
        val_by_id = {
            str(feature.get("id")): feature
            for feature in payload.get("features", [])
            if feature.get("id") is not None
        }
    roofer_features = {building_id: roofer_feature}
    rows = w2.classify_buildings("GS", [building_id], roofer_features, val_by_id)
    if len(rows) != 1:
        raise RuntimeError(f"Roofer status row mismatch for {building_id}: {len(rows)}")
    status = dict(rows[0])
    status["val3dity_exit_code"] = int(proc.returncode)
    return cityjson, status, val_report if val_report.exists() else None, val_log


def _roofer_component_extent(
    current: list[float] | None,
    value: Any,
    role: str,
) -> list[float]:
    if not isinstance(value, list) or len(value) != 6:
        raise RuntimeError(f"{role} geographicalExtent must contain six values")
    extent = [finite_float(item) for item in value]
    if any(item is None for item in extent):
        raise RuntimeError(f"{role} geographicalExtent is non-finite")
    numeric = [float(item) for item in extent]
    if current is None:
        return numeric
    return [
        min(current[0], numeric[0]), min(current[1], numeric[1]),
        min(current[2], numeric[2]), max(current[3], numeric[3]),
        max(current[4], numeric[4]), max(current[5], numeric[5]),
    ]


def _aggregate_roofer_component_attributes(
    components: list[Mapping[str, Any]],
) -> dict[str, Any]:
    if not components:
        raise RuntimeError("Roofer component attribute list is empty")
    identity_keys = ("building_id", "source", "grid_m", "point_count")
    for key in identity_keys:
        values = [component.get(key) for component in components]
        if any(value != values[0] for value in values[1:]):
            raise RuntimeError(f"Roofer component attribute drift: {key}")
    common_keys = set(components[0]).intersection(*(set(item) for item in components[1:]))
    result = {
        key: copy.deepcopy(components[0][key])
        for key in sorted(common_keys)
        if all(item[key] == components[0][key] for item in components[1:])
    }
    result["s3ap_component_count"] = len(components)
    result["rf_success"] = all(parse_bool(item.get("rf_success")) for item in components)
    result["rf_pointcloud_unusable"] = any(
        parse_bool(item.get("rf_pointcloud_unusable")) for item in components
    )
    result["rf_force_lod11"] = any(
        parse_bool(item.get("rf_force_lod11")) for item in components
    )
    modes = [str(item.get("rf_extrusion_mode", "")) for item in components]
    allowed_modes = {"standard", "lod11_fallback", "skip"}
    if any(mode not in allowed_modes for mode in modes):
        result["rf_extrusion_mode"] = "mixed_components"
        result["rf_success"] = False
    elif all(mode == modes[0] for mode in modes):
        result["rf_extrusion_mode"] = modes[0]
    elif "skip" in modes:
        result["rf_extrusion_mode"] = "skip"
    elif "lod11_fallback" in modes:
        result["rf_extrusion_mode"] = "lod11_fallback"
    else:
        result["rf_extrusion_mode"] = "mixed_components"
        result["rf_success"] = False
    result["s3ap_component_extrusion_modes"] = sorted(set(modes))
    roof_types = [str(item.get("rf_roof_type", "")) for item in components]
    result["rf_roof_type"] = (
        roof_types[0] if all(value == roof_types[0] for value in roof_types)
        else "mixed_components"
    )

    def numeric_values(key: str) -> list[float] | None:
        values = [finite_float(item.get(key)) for item in components]
        return None if any(value is None for value in values) else [float(value) for value in values]

    roof_planes = numeric_values("rf_roof_planes")
    result["rf_roof_planes"] = (
        int(sum(roof_planes)) if roof_planes is not None else None
    )
    for key, reducer in (
        ("rf_volume_lod22", sum),
        ("rf_rmse_lod22", max),
        ("rf_pt_density", min),
        ("rf_nodata_frac", max),
    ):
        values = numeric_values(key)
        result[key] = reducer(values) if values is not None else None
    return result


def _validate_cityjson_ring(
    ring: Any,
    upper_bound: int,
    role: str,
) -> None:
    if not isinstance(ring, list) or len(ring) < 3:
        raise RuntimeError(f"{role} must contain at least three vertex indices")
    for value in ring:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(f"{role} contains a non-integer index")
        if value < 0 or value >= upper_bound:
            raise RuntimeError(f"{role} index out of range: {value} not in [0,{upper_bound})")


def _validate_cityjson_multisurface_boundaries(
    boundaries: Any,
    upper_bound: int,
    role: str,
) -> None:
    if not isinstance(boundaries, list) or not boundaries:
        raise RuntimeError(f"{role} must contain at least one surface")
    for surface_index, surface in enumerate(boundaries):
        if not isinstance(surface, list) or not surface:
            raise RuntimeError(f"{role} surface {surface_index} has no rings")
        for ring_index, ring in enumerate(surface):
            _validate_cityjson_ring(
                ring, upper_bound,
                f"{role} surface {surface_index} ring {ring_index}",
            )


def _validate_cityjson_solid_boundaries(
    boundaries: Any,
    upper_bound: int,
    role: str,
) -> None:
    if not isinstance(boundaries, list) or not boundaries:
        raise RuntimeError(f"{role} must contain at least one shell")
    for shell_index, shell in enumerate(boundaries):
        _validate_cityjson_multisurface_boundaries(
            shell, upper_bound, f"{role} shell {shell_index}",
        )


def _validate_cityjson_solid_semantics(
    semantics: Any,
    boundaries: list[Any],
    role: str,
) -> None:
    if not isinstance(semantics, dict):
        raise RuntimeError(f"{role} semantics missing")
    surfaces = semantics.get("surfaces")
    values = semantics.get("values")
    if not isinstance(surfaces, list) or not surfaces:
        raise RuntimeError(f"{role} semantic surfaces missing")
    if not isinstance(values, list) or len(values) != len(boundaries):
        raise RuntimeError(f"{role} semantic shell shape mismatch")
    for shell_index, shell_values in enumerate(values):
        shell_boundaries = boundaries[shell_index]
        if not isinstance(shell_values, list) or len(shell_values) != len(shell_boundaries):
            raise RuntimeError(
                f"{role} semantic surface shape mismatch at shell {shell_index}"
            )
        for value in shell_values:
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuntimeError(f"{role} semantics contains a non-integer index")
            if value < 0 or value >= len(surfaces):
                raise RuntimeError(
                    f"{role} semantic index out of range: {value} not in [0,{len(surfaces)})"
                )


def _validate_roofer_cityjsonseq_header(header: Any, path: Path) -> None:
    if not isinstance(header, dict):
        raise RuntimeError(f"Roofer CityJSONSeq header is not an object: {path}")
    if (
        header.get("type") != "CityJSON"
        or header.get("version") != "2.0"
        or header.get("CityObjects") != {}
        or header.get("vertices") != []
    ):
        raise RuntimeError(f"unexpected Roofer CityJSONSeq header: {path}")
    transform = header.get("transform")
    if not isinstance(transform, dict):
        raise RuntimeError(f"Roofer CityJSONSeq transform missing: {path}")
    for key in ("scale", "translate"):
        values = transform.get(key)
        if (
            not isinstance(values, list) or len(values) != 3
            or any(isinstance(item, bool) or finite_float(item) is None for item in values)
        ):
            raise RuntimeError(f"Roofer CityJSONSeq {key} is invalid: {path}")
    metadata = header.get("metadata")
    reference = metadata.get("referenceSystem") if isinstance(metadata, dict) else None
    if str(reference) != "https://www.opengis.net/def/crs/EPSG/0/25832":
        raise RuntimeError(f"Roofer CityJSONSeq CRS is not EPSG:25832: {path}")


def _combine_roofer_component_cityjsonseq(
    jsonl_files: list[Path],
    output: Path,
    building_id: str,
    w2: Any,
) -> dict[str, Any]:
    """Merge repeated Roofer MultiPolygon features into one Building.

    Roofer emits one CityJSONFeature per disconnected polygon but repeats the
    source ``building_id`` and ``building_id-0`` identifiers for each feature.
    Every LoD0 footprint component and LoD2.2 BuildingPart is retained; only
    the BuildingPart identifiers are normalized deterministically.
    """

    top: dict[str, Any] | None = None
    vertices: list[list[int]] = []
    merged_parent: dict[str, Any] | None = None
    merged_lod0: dict[str, Any] | None = None
    children: dict[str, dict[str, Any]] = {}
    component_attributes: list[Mapping[str, Any]] = []
    extent: list[float] | None = None
    component_index = 0

    if len(jsonl_files) != 1:
        raise RuntimeError(
            f"Phase 3 expects exactly one Roofer CityJSONSeq file, got {len(jsonl_files)}"
        )
    for path in jsonl_files:
        with path.open("r", encoding="utf-8") as handle:
            try:
                header = json.loads(handle.readline())
            except json.JSONDecodeError as error:
                raise RuntimeError(f"invalid Roofer CityJSONSeq header: {path}") from error
            _validate_roofer_cityjsonseq_header(header, path)
            if top is None:
                top = copy.deepcopy(header)
                top["CityObjects"] = {}
                top["vertices"] = []
            source_transform = header.get("transform")
            target_transform = top.get("transform")
            for line_number, line in enumerate(handle, start=2):
                if not line.strip():
                    continue
                try:
                    feature = json.loads(line)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        f"invalid Roofer CityJSONFeature: {path}:{line_number}"
                    ) from error
                if feature.get("type") != "CityJSONFeature" or str(feature.get("id")) != building_id:
                    raise RuntimeError(
                        f"unexpected Roofer feature identity: {path}:{line_number}"
                    )
                objects = feature.get("CityObjects")
                if not isinstance(objects, dict):
                    raise RuntimeError(f"Roofer feature lacks CityObjects: {path}:{line_number}")
                parent_source = objects.get(building_id)
                if not isinstance(parent_source, dict) or parent_source.get("type") != "Building":
                    raise RuntimeError(f"Roofer feature lacks expected Building: {path}:{line_number}")
                source_children = parent_source.get("children")
                if not isinstance(source_children, list) or len(source_children) != 1:
                    raise RuntimeError(
                        f"Roofer component must contain exactly one BuildingPart: {path}:{line_number}"
                    )
                source_child_id = str(source_children[0])
                child_source = objects.get(source_child_id)
                if (
                    not isinstance(child_source, dict)
                    or child_source.get("type") != "BuildingPart"
                    or child_source.get("parents") != [building_id]
                    or set(objects) != {building_id, source_child_id}
                ):
                    raise RuntimeError(
                        f"unexpected Roofer BuildingPart graph: {path}:{line_number}"
                    )
                feature_vertices = feature.get("vertices")
                if not isinstance(feature_vertices, list) or not feature_vertices:
                    raise RuntimeError(f"Roofer component has no vertices: {path}:{line_number}")
                child_geometries = child_source.get("geometry")
                if not isinstance(child_geometries, list) or len(child_geometries) != 1:
                    raise RuntimeError(
                        f"Roofer component must contain one child LoD2.2 Solid: {path}:{line_number}"
                    )
                child_geometry = child_geometries[0]
                if (
                    child_geometry.get("type") != "Solid"
                    or str(child_geometry.get("lod")) != "2.2"
                    or not isinstance(child_geometry.get("boundaries"), list)
                    or not child_geometry["boundaries"]
                ):
                    raise RuntimeError(
                        f"unexpected Roofer child geometry: {path}:{line_number}"
                    )
                _validate_cityjson_solid_boundaries(
                    child_geometry["boundaries"], len(feature_vertices),
                    f"Roofer child boundaries {path}:{line_number}",
                )
                semantics = child_geometry.get("semantics")
                _validate_cityjson_solid_semantics(
                    semantics, child_geometry["boundaries"],
                    f"Roofer child {path}:{line_number}",
                )
                source_parent_geometries = parent_source.get("geometry")
                if (
                    not isinstance(source_parent_geometries, list)
                    or len(source_parent_geometries) != 1
                    or not isinstance(source_parent_geometries[0].get("boundaries"), list)
                ):
                    raise RuntimeError(
                        f"Roofer component must contain one parent LoD0 geometry: {path}:{line_number}"
                    )
                _validate_cityjson_multisurface_boundaries(
                    source_parent_geometries[0]["boundaries"], len(feature_vertices),
                    f"Roofer parent boundaries {path}:{line_number}",
                )
                converted = w2.convert_vertices(
                    feature_vertices, source_transform, target_transform,
                )
                offset = len(vertices)
                vertices.extend(converted)
                parent = copy.deepcopy(parent_source)
                child = copy.deepcopy(child_source)
                w2.shift_cityobject_boundaries(parent, offset)
                w2.shift_cityobject_boundaries(child, offset)
                parent_geometries = parent.pop("geometry", None)
                if not isinstance(parent_geometries, list) or len(parent_geometries) != 1:
                    raise RuntimeError(
                        f"Roofer component must contain one parent LoD0 geometry: {path}:{line_number}"
                    )
                parent_geometry = parent_geometries[0]
                if (
                    parent_geometry.get("type") != "MultiSurface"
                    or str(parent_geometry.get("lod")) != "0"
                    or not isinstance(parent_geometry.get("boundaries"), list)
                    or not parent_geometry["boundaries"]
                ):
                    raise RuntimeError(
                        f"unexpected Roofer parent geometry: {path}:{line_number}"
                    )
                if merged_lod0 is None:
                    merged_lod0 = copy.deepcopy(parent_geometry)
                    merged_lod0["boundaries"] = []
                elif {
                    key: value for key, value in parent_geometry.items() if key != "boundaries"
                } != {
                    key: value for key, value in merged_lod0.items() if key != "boundaries"
                }:
                    raise RuntimeError(
                        f"Roofer parent geometry contract drift: {path}:{line_number}"
                    )
                merged_lod0["boundaries"].extend(parent_geometry["boundaries"])
                attributes = parent.get("attributes")
                if not isinstance(attributes, dict):
                    raise RuntimeError(f"Roofer parent attributes missing: {path}:{line_number}")
                component_attributes.append(attributes)
                child["attributes"] = copy.deepcopy(attributes)
                extent = _roofer_component_extent(
                    extent, parent.get("geographicalExtent"),
                    f"Roofer component {component_index}",
                )
                if merged_parent is None:
                    merged_parent = parent
                    merged_parent["children"] = []
                    merged_parent["geometry"] = []
                new_child_id = f"{building_id}-{component_index}"
                if new_child_id in children:
                    raise RuntimeError(f"Roofer normalized BuildingPart collision: {new_child_id}")
                child["parents"] = [building_id]
                children[new_child_id] = child
                merged_parent["children"].append(new_child_id)
                component_index += 1

    if top is None or merged_parent is None or merged_lod0 is None or extent is None:
        raise RuntimeError("Roofer CityJSONSeq contains no components")
    merged_parent["attributes"] = _aggregate_roofer_component_attributes(
        component_attributes,
    )
    merged_parent["geographicalExtent"] = extent
    merged_parent["geometry"] = [merged_lod0]
    top["CityObjects"] = {building_id: merged_parent, **children}
    top["vertices"] = vertices
    top.setdefault("metadata", {})["geographicalExtent"] = extent
    atomic_text(
        output,
        json.dumps(top, ensure_ascii=False, separators=(",", ":")) + "\n",
    )
    return {
        "attributes": merged_parent["attributes"],
        "has_lod22": w2.has_lod22_geometry(top["CityObjects"]),
        "jsonl_file": ";".join(path.name for path in jsonl_files),
        "component_count": component_index,
    }


def _row_lookup(path: Path, building: str) -> dict[str, str]:
    matches = [row for row in read_csv(path) if short_building(row.get("building_id")) == building]
    if len(matches) != 1:
        raise RuntimeError(f"expected one row for {building} in {rel(path)}, got {len(matches)}")
    return matches[0]


def score_job(args: argparse.Namespace) -> None:
    """CPU worker: score only after Roofer inputs and read-out are finalized."""

    import numpy as np

    config_path = Path(args.config)
    config = load_json(config_path)
    job, _ = _load_job_spec(Path(args.job_spec))
    output_dir = Path(args.output_dir)
    extraction_manifest_path = output_dir / "extraction_manifest.json"
    roofer_input_manifest_path = output_dir / "roofer_input_manifest.json"
    input_npz_path = output_dir / "roofer_input.npz"
    if not extraction_manifest_path.exists() or not roofer_input_manifest_path.exists() or not input_npz_path.exists():
        raise RuntimeError("score boundary requires finalized extraction and Roofer input manifests")
    extraction = load_json(extraction_manifest_path)
    roofer_input = load_json(roofer_input_manifest_path)
    if parse_bool(roofer_input.get("supplied_footprint_opened")):
        raise RuntimeError("Roofer input manifest reports premature supplied-footprint access")
    if parse_bool(roofer_input.get("lod2_opened")) or parse_bool(roofer_input.get("als_opened")):
        raise RuntimeError("Roofer input manifest reports premature GT/ALS access")
    current_pre_fingerprint = pre_readout_fingerprint(config_path, config, job)
    if roofer_input.get("pre_readout_fingerprint", {}).get("digest") != current_pre_fingerprint["digest"]:
        raise RuntimeError("pre-readout inputs changed before score stage")
    building_id = full_building(job.building_id)
    roofer_exit_code = int(args.roofer_exit_code)
    cityjson, roofer_status, val_report, val_log = _combine_and_validate_roofer(
        output_dir, building_id, roofer_exit_code,
    )
    current_score_fingerprint = score_only_fingerprint(config)
    reuse_fingerprint = full_reuse_fingerprint(current_pre_fingerprint, current_score_fingerprint)

    # GT/supplied-footprint boundary: every extraction and Roofer input above is
    # already serialized and hashed before these files are opened.
    baseline = load_module(
        f"s3ap_phase3_baseline_{os.getpid()}_{threading.get_ident()}",
        PHASE0_BASELINE_SCRIPT,
    )
    metrics = load_module(
        f"s3ap_phase3_metrics_{os.getpid()}_{threading.get_ident()}",
        METRICS_SCRIPT,
    )
    footprints = baseline.load_footprints([job.building_id])
    footprint = footprints[job.building_id]
    roofs = baseline.load_lod2([job.building_id])
    geoid = float(load_json(resolve_repo_path(config["scoring"]["projection_datum"]))["orthometric_geoid_m"])
    input_archive = np.load(input_npz_path, allow_pickle=False)
    roof_points = np.asarray(input_archive["P_roof_utm"], dtype=np.float64).reshape(-1, 3)
    edge_width = float(config["scoring"]["edge_width_m"])
    inside, edge, interior = _inside_and_region(roof_points, footprint, edge_width)
    inside_points = roof_points[inside]
    reference = baseline.reference_z(inside_points[:, :2], roofs[job.building_id], geoid) if len(inside_points) else np.empty(0)
    residual = inside_points[:, 2] - reference if len(inside_points) else np.empty(0)
    inside_indices = np.flatnonzero(inside)
    edge_inside = edge[inside_indices]
    interior_inside = interior[inside_indices]
    overall_metrics = _height_metrics(residual)
    edge_metrics = _height_metrics(residual[edge_inside])
    interior_metrics = _height_metrics(residual[interior_inside])
    coverage = coverage_by_region(
        inside_points[:, :2], footprint,
        float(config["scoring"]["coverage_grid_m"]), edge_width,
    )

    predicted_surfaces: list[Any] = []
    comparison: dict[str, Any] = {"completeness": None, "ref_rms_m": None}
    if cityjson is not None and cityjson.exists():
        parsed = metrics.parse_cityjson_roofs(cityjson, {building_id})
        predicted_surfaces = metrics.shift_surface_z(parsed.get(building_id, []), -geoid)
        reference_surfaces = metrics.parse_lod2_roofs(
            resolve_repo_path(config["scoring"]["lod2_dir"]), {building_id},
        )
        comparison = metrics.compare_building(reference_surfaces.get(building_id, []), predicted_surfaces)
    city_points = _sample_citygml_roof(
        predicted_surfaces, footprint, float(config["scoring"]["coverage_grid_m"]),
    )
    city_inside, city_edge, city_interior = _inside_and_region(city_points, footprint, edge_width)
    city_points = city_points[city_inside]
    city_indices = np.flatnonzero(city_inside)
    city_edge_inside = city_edge[city_indices]
    city_interior_inside = city_interior[city_indices]
    city_reference_ellip = (
        baseline.reference_z(city_points[:, :2], roofs[job.building_id], geoid)
        if len(city_points) else np.empty(0)
    )
    city_reference_ortho = city_reference_ellip - geoid
    city_residual = city_points[:, 2] - city_reference_ortho if len(city_points) else np.empty(0)
    city_height = _height_metrics(city_residual)
    city_edge_height = _height_metrics(city_residual[city_edge_inside])
    city_interior_height = _height_metrics(city_residual[city_interior_inside])
    city_coverage = coverage_by_region(
        city_points[:, :2], footprint,
        float(config["scoring"]["coverage_grid_m"]), edge_width,
    )
    completeness = finite_float(comparison.get("completeness"))
    city_rms = finite_float(comparison.get("ref_rms_m"))
    raw_geometry = parse_bool(roofer_status.get("has_lod22"))
    valid = parse_bool(roofer_status.get("val3dity_valid"))
    classification = substantive_classification(
        roofer_status=str(roofer_status.get("status", "")),
        extrusion_mode=str(roofer_status.get("rf_extrusion_mode", "")),
        roof_planes=roofer_status.get("rf_roof_planes", 0),
        geometry_has_lod22=raw_geometry,
        val3dity_valid=valid,
        completeness=completeness,
        roof_rms_m=city_rms,
        lock=config["roofer"]["substantive_filter"],
    )
    p0 = _row_lookup(resolve_repo_path(config["scoring"]["p0_scores"]), job.building_id)
    mvs = _row_lookup(resolve_repo_path(config["scoring"]["mvs_scores"]), job.building_id)
    p0_archive = np.load(resolve_repo_path(config["scoring"]["p0_points"]), allow_pickle=False)
    p0_local = np.asarray(p0_archive[f"{building_id}_local_xyz"], dtype=np.float64).reshape(-1, 3)
    p0_world = p0_local + _load_world_offset(config)[None, :]
    p0_inside_mask, p0_edge_mask, p0_interior_mask = _inside_and_region(
        p0_world, footprint, edge_width,
    )
    p0_inside_points = p0_world[p0_inside_mask]
    p0_inside_indices = np.flatnonzero(p0_inside_mask)
    p0_edge_inside = p0_edge_mask[p0_inside_indices]
    p0_interior_inside = p0_interior_mask[p0_inside_indices]
    p0_reference = (
        baseline.reference_z(p0_inside_points[:, :2], roofs[job.building_id], geoid)
        if len(p0_inside_points) else np.empty(0)
    )
    p0_residual = p0_inside_points[:, 2] - p0_reference if len(p0_inside_points) else np.empty(0)
    p0_metrics = _height_metrics(p0_residual)
    p0_edge_metrics = _height_metrics(p0_residual[p0_edge_inside])
    p0_interior_metrics = _height_metrics(p0_residual[p0_interior_inside])
    p0_coverage = coverage_by_region(
        p0_inside_points[:, :2], footprint,
        float(config["scoring"]["coverage_grid_m"]), edge_width,
    )
    p0_abs = p0_metrics["abs_median"]
    gs_abs = overall_metrics["abs_median"]
    compare_arms = {str(value).lower() for value in config["scoring"]["comparison_arms"]}
    gs_lt_p0: bool | None = None
    gs_edge_lt_p0: bool | None = None
    gs_interior_lt_p0: bool | None = None
    if job.arm.lower() in compare_arms and gs_abs is not None and p0_abs is not None:
        gs_lt_p0 = bool(gs_abs < p0_abs)
    if (
        job.arm.lower() in compare_arms and edge_metrics["abs_median"] is not None
        and p0_edge_metrics["abs_median"] is not None
    ):
        gs_edge_lt_p0 = bool(edge_metrics["abs_median"] < p0_edge_metrics["abs_median"])
    if (
        job.arm.lower() in compare_arms and interior_metrics["abs_median"] is not None
        and p0_interior_metrics["abs_median"] is not None
    ):
        gs_interior_lt_p0 = bool(interior_metrics["abs_median"] < p0_interior_metrics["abs_median"])
    score_status = "complete" if len(inside_points) else "partial_no_scored_roof_points"
    score_reason = "" if len(inside_points) else str(roofer_input.get("status", "no_inside_points"))
    row: dict[str, Any] = {
        "run_id": job.run_id, "building_id": building_id, "arm": job.arm,
        "replicate": job.replicate, "perturbation_type": job.perturbation_type,
        "perturbation_value": job.perturbation_value, "score_status": score_status,
        "score_reason": score_reason, "checkpoint": job.checkpoint,
        "checkpoint_sha256": extraction.get("checkpoint_sha256", ""),
        "prepared_root": job.prepared_root,
        "fixed_view_count": extraction.get("fixed_view_count"),
        "fixed_views": ";".join(extraction.get("fixed_views", [])),
        "alpha_min_inclusive": config["extraction"]["alpha_min_inclusive"],
        "voxel_m": config["extraction"]["voxel_m"],
        "min_observations": config["extraction"]["min_observations"],
        "sor_neighbors": config["extraction"]["sor_neighbors"],
        "sor_std_ratio": config["extraction"]["sor_std_ratio"],
        "expected_fused_all": extraction["fusion"]["expected"]["fused_all"],
        "expected_minobs_kept": extraction["fusion"]["expected"]["minobs_kept"],
        "expected_sor_kept": extraction["fusion"]["expected"]["sor_kept"],
        "median_fused_all": extraction["fusion"]["median"]["fused_all"],
        "median_minobs_kept": extraction["fusion"]["median"]["minobs_kept"],
        "median_sor_kept": extraction["fusion"]["median"]["sor_kept"],
        "canonical_depth": extraction["render"]["canonical_depth"],
        "roof_evidence_point_count": roofer_input["roof_evidence_point_count"],
        "ground_z_local_m": roofer_input["observed_ground"]["z_local_m"],
        "ground_method": roofer_input["observed_ground"]["method"],
        "ground_source": roofer_input["observed_ground"]["source"],
        "minimum_height_above_ground_m": config["roof_evidence"]["minimum_height_above_observed_ground_m"],
        "derived_roofprint_area_m2": roofer_input["derived_roofprint_area_m2"],
        "supplied_footprint_passed_to_roofer": False,
        "point_evidence_derived_roofprint_passed_to_roofer": roofer_input["point_evidence_derived_roofprint_passed_to_roofer"],
        "fused_inside_point_count": len(inside_points),
        "coverage_grid_m": config["scoring"]["coverage_grid_m"],
        "coverage_eligible_cells": coverage["all"]["eligible"],
        "coverage_occupied_cells": coverage["all"]["occupied"],
        "coverage_ratio": coverage["all"]["ratio"],
        "edge_width_m": edge_width, "edge_point_count": int(edge_inside.sum()),
        "edge_coverage_eligible_cells": coverage["edge"]["eligible"],
        "edge_coverage_occupied_cells": coverage["edge"]["occupied"],
        "edge_coverage_ratio": coverage["edge"]["ratio"],
        "interior_point_count": int(interior_inside.sum()),
        "interior_coverage_eligible_cells": coverage["interior"]["eligible"],
        "interior_coverage_occupied_cells": coverage["interior"]["occupied"],
        "interior_coverage_ratio": coverage["interior"]["ratio"],
        "height_error_signed_median_m": overall_metrics["signed_median"],
        "height_error_abs_median_m": overall_metrics["abs_median"],
        "height_error_mad_m": overall_metrics["mad"],
        "height_error_rms_m": overall_metrics["rms"],
        "edge_height_error_signed_median_m": edge_metrics["signed_median"],
        "edge_height_error_abs_median_m": edge_metrics["abs_median"],
        "edge_height_error_mad_m": edge_metrics["mad"],
        "edge_height_error_rms_m": edge_metrics["rms"],
        "interior_height_error_signed_median_m": interior_metrics["signed_median"],
        "interior_height_error_abs_median_m": interior_metrics["abs_median"],
        "interior_height_error_mad_m": interior_metrics["mad"],
        "interior_height_error_rms_m": interior_metrics["rms"],
        "roofer_status": roofer_status.get("status", ""),
        "roofer_reason": roofer_status.get("reason", ""),
        "rf_extrusion_mode": roofer_status.get("rf_extrusion_mode", ""),
        "rf_roof_planes": roofer_status.get("rf_roof_planes", ""),
        "geometry_has_lod22": classification["geometry_has_lod22"],
        "has_lod22": classification["has_lod22"],
        "val3dity_valid": valid,
        "citygml_completeness": completeness,
        "citygml_roof_rms_m": city_rms,
        "substantive_filter": classification["substantive_filter"],
        "cityjson_path": rel(cityjson) if cityjson else "",
        "citygml_roof_point_count": len(city_points),
        "citygml_coverage_eligible_cells": city_coverage["all"]["eligible"],
        "citygml_coverage_occupied_cells": city_coverage["all"]["occupied"],
        "citygml_coverage_ratio": city_coverage["all"]["ratio"],
        "citygml_edge_point_count": int(city_edge_inside.sum()),
        "citygml_edge_coverage_eligible_cells": city_coverage["edge"]["eligible"],
        "citygml_edge_coverage_occupied_cells": city_coverage["edge"]["occupied"],
        "citygml_edge_coverage_ratio": city_coverage["edge"]["ratio"],
        "citygml_interior_point_count": int(city_interior_inside.sum()),
        "citygml_interior_coverage_eligible_cells": city_coverage["interior"]["eligible"],
        "citygml_interior_coverage_occupied_cells": city_coverage["interior"]["occupied"],
        "citygml_interior_coverage_ratio": city_coverage["interior"]["ratio"],
        "citygml_height_error_signed_median_m": city_height["signed_median"],
        "citygml_height_error_abs_median_m": city_height["abs_median"],
        "citygml_height_error_mad_m": city_height["mad"],
        "citygml_height_error_rms_region_m": city_height["rms"],
        "citygml_edge_height_error_signed_median_m": city_edge_height["signed_median"],
        "citygml_edge_height_error_abs_median_m": city_edge_height["abs_median"],
        "citygml_edge_height_error_mad_m": city_edge_height["mad"],
        "citygml_edge_height_error_rms_m": city_edge_height["rms"],
        "citygml_interior_height_error_signed_median_m": city_interior_height["signed_median"],
        "citygml_interior_height_error_abs_median_m": city_interior_height["abs_median"],
        "citygml_interior_height_error_mad_m": city_interior_height["mad"],
        "citygml_interior_height_error_rms_m": city_interior_height["rms"],
        "p0_height_error_signed_median_m": p0_metrics["signed_median"],
        "p0_height_error_abs_median_m": p0_abs,
        "p0_height_error_mad_m": p0_metrics["mad"],
        "p0_height_error_rms_m": p0_metrics["rms"],
        "p0_coverage_ratio": p0_coverage["all"]["ratio"],
        "p0_edge_point_count": int(p0_edge_inside.sum()),
        "p0_edge_coverage_ratio": p0_coverage["edge"]["ratio"],
        "p0_edge_height_error_signed_median_m": p0_edge_metrics["signed_median"],
        "p0_edge_height_error_abs_median_m": p0_edge_metrics["abs_median"],
        "p0_edge_height_error_mad_m": p0_edge_metrics["mad"],
        "p0_edge_height_error_rms_m": p0_edge_metrics["rms"],
        "p0_interior_point_count": int(p0_interior_inside.sum()),
        "p0_interior_coverage_ratio": p0_coverage["interior"]["ratio"],
        "p0_interior_height_error_signed_median_m": p0_interior_metrics["signed_median"],
        "p0_interior_height_error_abs_median_m": p0_interior_metrics["abs_median"],
        "p0_interior_height_error_mad_m": p0_interior_metrics["mad"],
        "p0_interior_height_error_rms_m": p0_interior_metrics["rms"],
        "gs_edge_abs_error_lt_p0": gs_edge_lt_p0,
        "gs_interior_abs_error_lt_p0": gs_interior_lt_p0,
        "gs_minus_p0_edge_abs_median_m": (
            edge_metrics["abs_median"] - p0_edge_metrics["abs_median"]
            if edge_metrics["abs_median"] is not None and p0_edge_metrics["abs_median"] is not None else None
        ),
        "gs_minus_p0_interior_abs_median_m": (
            interior_metrics["abs_median"] - p0_interior_metrics["abs_median"]
            if interior_metrics["abs_median"] is not None and p0_interior_metrics["abs_median"] is not None else None
        ),
        "p0_has_lod22": parse_bool(p0.get("has_lod22")),
        "p0_substantive_filter": parse_bool(p0.get("substantive_filter")),
        "gs_abs_error_lt_p0": gs_lt_p0,
        "gs_p0_comparison_metric": config["scoring"]["gs_p0_comparison_metric"],
        "mvs_direct_class6_no_points": parse_bool(mvs.get("direct_class6_no_points")),
        "mvs_canonical_no_points": parse_bool(mvs.get("canonical_roofer_no_points")),
        "mvs_canonical_reason": mvs.get("canonical_roofer_reason", ""),
        "footprint_role": "score-region and coverage mask opened after Roofer input finalization",
        "gt_role": config["scoring"]["gt_open_boundary"],
        "crs": config["crs"],
        "extraction_manifest": rel(extraction_manifest_path),
        "roofer_input_manifest": rel(roofer_input_manifest_path),
    }
    score_path = output_dir / "score_row.json"
    atomic_json(score_path, row)
    perturbation_row_path: Path | None = None
    perturbation_cells_path: Path | None = None
    if job.arm.lower() == str(config["perturbation"]["height_arm"]).lower() and job.replicate.lower() == str(config["perturbation"]["height_replicate"]).lower() and job.perturbation_type in {"none", "height"}:
        delta = float(job.perturbation_value if job.perturbation_type == "height" else 0.0)
        p0_signed = p0_metrics["signed_median"]
        post_signed = overall_metrics["signed_median"]
        perturbed_signed = p0_signed + delta if p0_signed is not None else None
        condition = bool(
            score_status == "complete" and delta != 0.0
            and post_signed is not None and perturbed_signed is not None
            and abs(post_signed) < abs(perturbed_signed)
        )
        perturb_row = {
            "run_id": job.run_id, "building_id": building_id, "arm": job.arm,
            "replicate": job.replicate, "delta_m": delta, "score_status": score_status,
            "p0_signed_median_error_m": p0_signed,
            "perturbed_p0_signed_median_error_m": perturbed_signed,
            "perturbed_p0_abs_signed_median_error_m": abs(perturbed_signed) if perturbed_signed is not None else None,
            "post_gs_signed_median_error_m": post_signed,
            "post_gs_abs_signed_median_error_m": abs(post_signed) if post_signed is not None else None,
            "signed_error_reduction_m": (
                abs(perturbed_signed) - abs(post_signed)
                if perturbed_signed is not None and post_signed is not None else None
            ),
            "post_minus_perturbed_seed_signed_m": (
                post_signed - perturbed_signed
                if perturbed_signed is not None and post_signed is not None else None
            ),
            "return_condition_met": condition,
            "trigger_candidate": bool(delta != 0.0 and score_status == "complete"),
            "trigger_rule": config["perturbation"]["trigger_rule"],
        }
        perturbation_row_path = output_dir / "perturbation_row.json"
        atomic_json(perturbation_row_path, perturb_row)
        cell_rows = perturbation_cell_rows(
            job=job, p0_points=p0_inside_points, p0_residuals=p0_residual,
            gs_points=inside_points, gs_residuals=residual, footprint=footprint,
            edge_width_m=edge_width, grid_m=float(config["scoring"]["coverage_grid_m"]),
            score_status=score_status,
        )
        perturbation_cells_path = output_dir / "perturbation_cells.csv"
        atomic_csv(perturbation_cells_path, cell_rows, PERTURB_CELL_FIELDS)
    score_manifest = {
        "schema": "jointbuildgs.s3ap.phase3.score.v1", "created_utc": utc_now(),
        "job": asdict(job), "score_row": rel(score_path),
        "score_row_sha256": sha256_file(score_path),
        "phase3_script_sha256": sha256_file(Path(__file__)),
        "phase3_config_sha256": sha256_file(Path(args.config)),
        "pre_readout_fingerprint": current_pre_fingerprint,
        "score_only_fingerprint": current_score_fingerprint,
        "full_reuse_fingerprint": reuse_fingerprint,
        "roofer_input_manifest": rel(roofer_input_manifest_path),
        "roofer_input_manifest_sha256": sha256_file(roofer_input_manifest_path),
        "perturbation_row": rel(perturbation_row_path) if perturbation_row_path else None,
        "perturbation_row_sha256": (
            sha256_file(perturbation_row_path) if perturbation_row_path else None
        ),
        "perturbation_cells": rel(perturbation_cells_path) if perturbation_cells_path else None,
        "perturbation_cells_sha256": (
            sha256_file(perturbation_cells_path) if perturbation_cells_path else None
        ),
        "gt_opened_after_roofer_input_finalized": True,
        "roofer_exit_code": roofer_exit_code,
        "cityjson": rel(cityjson) if cityjson else None,
        "cityjson_sha256": sha256_file(cityjson) if cityjson else None,
        "val3dity_report": rel(val_report) if val_report else None,
        "val3dity_report_sha256": sha256_file(val_report) if val_report else None,
        "val3dity_log": rel(val_log) if val_log else None,
        "val3dity_log_sha256": sha256_file(val_log) if val_log else None,
        "interpretation_or_verdict": None,
    }
    atomic_json(output_dir / "score_manifest.json", score_manifest)
    print(json.dumps({
        "run_id": job.run_id, "status": score_status,
        "inside_points": len(inside_points), "score_row": rel(score_path),
    }, ensure_ascii=False))


def _select_a1_base(rows: Sequence[Mapping[str, Any]], building_id: str) -> Mapping[str, Any] | None:
    candidates = [
        row for row in rows
        if str(row.get("building_id")) == building_id
        and str(row.get("arm", "")).lower() == "a1"
        and str(row.get("replicate", "")).lower() == "r1"
        and abs(finite_float(row.get("perturbation_value")) or 0.0) == 0.0
        and str(row.get("perturbation_type", "none")) in {"none", "height"}
    ]
    return sorted(candidates, key=lambda row: str(row.get("run_id", "")))[0] if candidates else None


def _plot_outline(ax: Any, geometry: Any, **kwargs: Any) -> None:
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

    if isinstance(geometry, Polygon):
        rings = [geometry]
    elif isinstance(geometry, MultiPolygon):
        rings = list(geometry.geoms)
    elif isinstance(geometry, GeometryCollection):
        rings = [part for part in geometry.geoms if isinstance(part, Polygon)]
    else:
        rings = []
    for polygon in rings:
        xy = polygon.exterior.xy
        ax.plot(xy[0], xy[1], **kwargs)


def _original_frame_overlay(
    *,
    config: Mapping[str, Any],
    selected: Mapping[str, Any],
    short: str,
    gs_inside: Any,
    roofs: Sequence[Mapping[str, Any]],
    offset: Any,
    geoid: float,
    output: Path,
) -> None:
    """Score-stage-only original-frame overlay; raises when no view is resolvable."""

    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    sys.path.insert(0, str(REPO))
    from src.stage2.colmap_io import read_cameras_bin, read_images_bin

    data_root = resolve_repo_path(config["scoring"]["original_data_root"])
    sparse = data_root / "sparse/0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    images = list(read_images_bin(sparse / "images.bin").values())
    lookup: dict[str, Any] = {}
    for image in images:
        lookup[image.name] = image
        lookup[Path(image.name).name] = image
        lookup[Path(image.name).stem] = image
    requested = [value for value in str(selected.get("fixed_views", "")).split(";") if value]
    image = next((lookup.get(value) or lookup.get(Path(value).stem) for value in requested if lookup.get(value) or lookup.get(Path(value).stem)), None)
    if image is None:
        raise RuntimeError("no fixed view resolved in original COLMAP model")
    image_path = data_root / "images" / image.name
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    camera = cameras[image.camera_id]
    k = camera.K().astype(np.float64)
    r = image.R().astype(np.float64)
    t = np.asarray(image.tvec, dtype=np.float64)

    def project(local_xyz: Any) -> tuple[Any, Any]:
        xyz = np.asarray(local_xyz, dtype=np.float64).reshape(-1, 3)
        camera_xyz = xyz @ r.T + t[None, :]
        valid = np.isfinite(camera_xyz).all(axis=1) & (camera_xyz[:, 2] > 1e-6)
        uvw = camera_xyz @ k.T
        uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-12)
        valid &= (
            (uv[:, 0] >= 0) & (uv[:, 0] < camera.width)
            & (uv[:, 1] >= 0) & (uv[:, 1] < camera.height)
        )
        return uv[valid], valid

    gs = np.asarray(gs_inside, dtype=np.float64).reshape(-1, 3)
    gs_local = gs - np.asarray(offset, dtype=np.float64)[None, :]
    uv_gs, valid_gs = project(gs_local)
    gs_visible = gs[valid_gs]
    if len(gs_visible):
        # LoD2 is opened in this score-stage figure only.
        baseline = load_module(f"s3ap_overlay_base_{os.getpid()}_{short}", PHASE0_BASELINE_SCRIPT)
        ref_z = baseline.reference_z(gs_visible[:, :2], roofs, geoid)
        color = np.abs(gs_visible[:, 2] - ref_z)
    else:
        color = np.empty(0)
    figure, axis = plt.subplots(figsize=(12.0, 8.0), constrained_layout=True)
    axis.imshow(Image.open(image_path).convert("RGB"))
    scatter = None
    if len(uv_gs):
        stride = max(1, len(uv_gs) // 5000)
        scatter = axis.scatter(
            uv_gs[::stride, 0], uv_gs[::stride, 1], c=color[::stride], s=7,
            cmap="viridis", alpha=0.75, linewidths=0,
        )
    for roof in roofs:
        ring = np.asarray(roof["ring"], dtype=np.float64).copy()
        ring[:, 2] += geoid
        uv, valid = project(ring - np.asarray(offset, dtype=np.float64)[None, :])
        if valid.all() and len(uv):
            axis.plot(uv[:, 0], uv[:, 1], color="#f28e2b", linewidth=1.2)
    if scatter is not None:
        figure.colorbar(scatter, ax=axis, label="GS |height residual| [m]", shrink=0.7)
    axis.set_title(
        f"{full_building(short)} original frame {Path(image.name).stem} | "
        "GS points + LoD2 score outline",
        fontsize=10,
    )
    axis.set_axis_off()
    figure.savefig(output, dpi=170)
    plt.close(figure)


def _phase3_figures(
    config: Mapping[str, Any],
    score_rows: Sequence[Mapping[str, Any]],
    perturb_rows: Sequence[Mapping[str, Any]],
    perturbation_cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    import laspy
    import matplotlib
    import numpy as np
    from shapely import contains_xy

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    baseline = load_module(f"s3ap_phase3_figure_base_{os.getpid()}", PHASE0_BASELINE_SCRIPT)
    metrics = load_module(f"s3ap_phase3_figure_metrics_{os.getpid()}", METRICS_SCRIPT)
    fig_dir = resolve_repo_path(config["outputs"]["figure_dir"])
    fig_dir.mkdir(parents=True, exist_ok=True)
    offset = _load_world_offset(config)
    geoid = float(load_json(resolve_repo_path(config["scoring"]["projection_datum"]))["orthometric_geoid_m"])
    p0_archive = np.load(resolve_repo_path(config["scoring"]["p0_points"]), allow_pickle=False)
    p0_by_id = {short_building(row["building_id"]): row for row in read_csv(resolve_repo_path(config["scoring"]["p0_scores"]))}
    mvs_by_id = {short_building(row["building_id"]): row for row in read_csv(resolve_repo_path(config["scoring"]["mvs_scores"]))}
    generated: list[str] = []
    skipped: list[dict[str, str]] = []

    for short in config["targets"]:
        bid = full_building(short)
        selected = _select_a1_base(score_rows, bid)
        if selected is None:
            skipped.append({"figure": f"height_{short}", "reason": "A1_r1_delta0_score_missing"})
            continue
        job_dir = resolve_repo_path(config["outputs"]["job_root"]) / str(selected["run_id"])
        input_path = job_dir / "roofer_input.npz"
        if not input_path.exists():
            skipped.append({"figure": f"height_{short}", "reason": "roofer_input_missing"})
            continue
        footprint = baseline.load_footprints([short])[short]
        roofs = baseline.load_lod2([short])[short]
        p0_local = np.asarray(p0_archive[f"{bid}_local_xyz"], dtype=np.float64)
        p0_world = p0_local + offset[None, :]
        gs_world = np.asarray(np.load(input_path, allow_pickle=False)["P_roof_utm"], dtype=np.float64)
        gs_inside = gs_world[contains_xy(footprint, gs_world[:, 0], gs_world[:, 1])] if len(gs_world) else gs_world
        gt_z = baseline.reference_z(p0_world[:, :2], roofs, geoid)
        all_z = np.concatenate([p0_world[:, 2], gt_z, gs_inside[:, 2] if len(gs_inside) else np.empty(0)])
        vmin, vmax = (float(np.percentile(all_z, 2)), float(np.percentile(all_z, 98))) if len(all_z) else (0.0, 1.0)
        if vmax <= vmin:
            vmax = vmin + 1.0
        figure, axes = plt.subplots(1, 3, figsize=(12.0, 3.8), constrained_layout=True)
        panels = [
            (p0_world, "P0 plane fill"),
            (gs_inside, "A1 r1 fused GS roof"),
            (np.column_stack([p0_world[:, :2], gt_z]), "LoD2 score surface"),
        ]
        scatter = None
        for axis, (points, title) in zip(axes, panels):
            _plot_outline(axis, footprint, color="black", linewidth=0.8)
            if len(points):
                scatter = axis.scatter(points[:, 0], points[:, 1], c=points[:, 2], s=9, cmap="viridis", vmin=vmin, vmax=vmax)
            axis.set_aspect("equal")
            axis.set_title(f"{title} | N={len(points)}", fontsize=9)
            axis.set_xlabel("E [m]")
            axis.set_ylabel("N [m]")
        if scatter is not None:
            figure.colorbar(scatter, ax=axes, label="ellipsoidal z [m]", shrink=0.8)
        figure.suptitle(f"{bid} height maps | LoD2 used for score panel only", fontsize=10)
        output = fig_dir / f"height_p0_a1_gt_{short}.png"
        figure.savefig(output, dpi=180)
        plt.close(figure)
        generated.append(rel(output))

        try:
            overlay = fig_dir / f"original_frame_overlay_{short}.png"
            _original_frame_overlay(
                config=config, selected=selected, short=short, gs_inside=gs_inside,
                roofs=roofs, offset=offset, geoid=geoid, output=overlay,
            )
            generated.append(rel(overlay))
        except Exception as exc:
            skipped.append({
                "figure": f"original_frame_overlay_{short}",
                "reason": f"{type(exc).__name__}:{exc}",
            })

        # MVS/P0/GS/CityGML panels.  Each panel retains its recorded source frame.
        try:
            mvs_row = mvs_by_id[short]
            cloud = laspy.read(resolve_repo_path(mvs_row["source_path"]))
            mvs_xyz = np.column_stack([np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z)])
            mvs_class = np.asarray(cloud.classification)
            mvs_xyz = mvs_xyz[(mvs_class == 6) & contains_xy(footprint, mvs_xyz[:, 0], mvs_xyz[:, 1])]
            cityjson_path = resolve_repo_path(str(selected.get("cityjson_path", ""))) if selected.get("cityjson_path") else None
            city_surfaces = []
            if cityjson_path is not None and cityjson_path.exists():
                city_surfaces = metrics.parse_cityjson_roofs(cityjson_path, {bid}).get(bid, [])
            figure = plt.figure(figsize=(12.5, 3.5), constrained_layout=True)
            point_panels = [(mvs_xyz, "MVS class 6"), (p0_world, "P0"), (gs_inside, "A1 GS")]
            for index, (points, title) in enumerate(point_panels, start=1):
                axis = figure.add_subplot(1, 4, index, projection="3d")
                if len(points):
                    take = points[::max(1, len(points) // 5000)]
                    axis.scatter(take[:, 0], take[:, 1], take[:, 2], s=2, alpha=0.65)
                axis.set_title(f"{title} | N={len(points)}", fontsize=8)
            axis = figure.add_subplot(1, 4, 4, projection="3d")
            for surface in city_surfaces:
                polygon = max(baseline.flatten_polygons(surface.polygon), key=lambda item: item.area)
                xy = np.asarray(polygon.exterior.coords, dtype=np.float64)
                z = surface.z_at(xy[:, 0], xy[:, 1])
                axis.plot(xy[:, 0], xy[:, 1], z, linewidth=1.1)
            axis.set_title(f"CityGML roof faces | N={len(city_surfaces)}", fontsize=8)
            figure.suptitle(f"{bid} source/read-out geometry panels", fontsize=10)
            output = fig_dir / f"mvs_p0_gs_citygml_3d_{short}.png"
            figure.savefig(output, dpi=180)
            plt.close(figure)
            generated.append(rel(output))
        except Exception as exc:
            skipped.append({"figure": f"3d_{short}", "reason": f"{type(exc).__name__}:{exc}"})

        # Required assembled read-out comparison.  Missing/filtered baselines
        # remain explicit unavailable panels; point clouds never substitute.
        try:
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection

            p0_row = p0_by_id[short]
            panel_specs = [
                (
                    "MVS CityGML", resolve_repo_path(config["scoring"]["mvs_cityjson"]),
                    str(mvs_by_id[short].get("canonical_roofer_reason", "unavailable")),
                    "#777777",
                ),
                (
                    "P0 CityGML", resolve_repo_path(str(p0_row.get("cityjson_path", ""))),
                    str(p0_row.get("roofer_reason") or p0_row.get("roofer_block_reason") or "unavailable"),
                    "#d9922e",
                ),
                (
                    "GS CityGML", resolve_repo_path(str(selected.get("cityjson_path", ""))),
                    str(selected.get("roofer_reason") or selected.get("score_reason") or "unavailable"),
                    "#3d78b5",
                ),
            ]
            figure = plt.figure(figsize=(12.0, 3.8), constrained_layout=True)
            for index, (title, path, reason, color) in enumerate(panel_specs, start=1):
                axis = figure.add_subplot(1, 3, index, projection="3d")
                surfaces: list[Any] = []
                try:
                    if str(path) not in {"", "."} and path.is_file():
                        surfaces = metrics.parse_cityjson_roofs(path, {bid}).get(bid, [])
                    elif not path.is_file():
                        reason = f"{reason};file_missing"
                except Exception as exc:
                    surfaces = []
                    reason = f"{reason};parse_{type(exc).__name__}:{exc}"
                vertices: list[Any] = []
                for surface in surfaces:
                    for polygon in baseline.flatten_polygons(surface.polygon):
                        xy = np.asarray(polygon.exterior.coords[:-1], dtype=np.float64)
                        if len(xy) < 3:
                            continue
                        z = np.asarray(surface.z_at(xy[:, 0], xy[:, 1]), dtype=np.float64)
                        vertices.append(np.column_stack([xy, z]))
                if vertices:
                    axis.add_collection3d(Poly3DCollection(
                        vertices, facecolor=color, edgecolor="black", linewidth=0.5, alpha=0.75,
                    ))
                    merged = np.vstack(vertices)
                    axis.set_xlim(float(merged[:, 0].min()), float(merged[:, 0].max()))
                    axis.set_ylim(float(merged[:, 1].min()), float(merged[:, 1].max()))
                    axis.set_zlim(float(merged[:, 2].min()) - 0.5, float(merged[:, 2].max()) + 0.5)
                    axis.set_title(f"{title} | roof faces={len(vertices)}", fontsize=8)
                else:
                    axis.text2D(
                        0.5, 0.5, f"unavailable | {reason}", transform=axis.transAxes,
                        ha="center", va="center", wrap=True, fontsize=9,
                    )
                    axis.set_title(f"{title} | unavailable", fontsize=8)
                axis.set_xlabel("E")
                axis.set_ylabel("N")
                axis.set_zlabel("z")
            figure.suptitle(f"{bid} assembled CityGML read-outs", fontsize=10)
            output = fig_dir / f"citygml_mvs_p0_gs_{short}.png"
            figure.savefig(output, dpi=180)
            plt.close(figure)
            generated.append(rel(output))
        except Exception as exc:
            skipped.append({
                "figure": f"citygml_mvs_p0_gs_{short}",
                "reason": f"{type(exc).__name__}:{exc}",
            })

    deltas = sorted({finite_float(row.get("delta_m")) for row in perturb_rows if finite_float(row.get("delta_m")) not in (None, 0.0)})
    if deltas:
        matrix = np.full((len(config["targets"]), len(deltas)), np.nan, dtype=np.float64)
        for row in perturb_rows:
            short = short_building(row.get("building_id"))
            delta = finite_float(row.get("delta_m"))
            value = finite_float(row.get("signed_error_reduction_m"))
            if short in config["targets"] and delta in deltas and value is not None:
                matrix[list(config["targets"]).index(short), deltas.index(delta)] = value
        figure, axis = plt.subplots(figsize=(9.0, 3.2), constrained_layout=True)
        finite_values = matrix[np.isfinite(matrix)]
        bound = max(float(np.max(np.abs(finite_values))) if len(finite_values) else 1.0, 1e-6)
        image = axis.imshow(matrix, cmap="coolwarm", vmin=-bound, vmax=bound, aspect="auto")
        axis.set_xticks(range(len(deltas)), [f"{value:+g}" for value in deltas])
        axis.set_yticks(range(len(config["targets"])), list(config["targets"]))
        axis.set_xlabel("injected height delta [m]")
        axis.set_ylabel("building")
        axis.set_title("abs(seed signed error) - abs(post-GS signed error) [m]")
        for iy in range(matrix.shape[0]):
            for ix in range(matrix.shape[1]):
                if np.isfinite(matrix[iy, ix]):
                    axis.text(ix, iy, f"{matrix[iy, ix]:.2f}", ha="center", va="center", fontsize=7)
        figure.colorbar(image, ax=axis, label="signed-error reduction [m]")
        output = fig_dir / "perturbation_return_map.png"
        figure.savefig(output, dpi=180)
        plt.close(figure)
        generated.append(rel(output))

        for short in config["targets"]:
            by_delta = {
                delta: [
                    row for row in perturbation_cells
                    if short_building(row.get("building_id")) == short
                    and finite_float(row.get("delta_m")) == delta
                ]
                for delta in deltas
            }
            if not any(by_delta.values()):
                skipped.append({
                    "figure": f"perturbation_spatial_return_{short}",
                    "reason": "no_spatial_cell_rows",
                })
                continue
            footprint = baseline.load_footprints([short])[short]
            finite_return = [
                value for rows in by_delta.values() for row in rows
                for value in [finite_float(row.get("return_amount_m"))] if value is not None
            ]
            spatial_bound = max(max((abs(value) for value in finite_return), default=1.0), 1e-6)
            ncols = 4
            nrows = math.ceil(len(deltas) / ncols)
            figure, axes = plt.subplots(
                nrows, ncols, figsize=(12.0, 3.1 * nrows), constrained_layout=True,
                squeeze=False,
            )
            spatial_scatter = None
            for axis, delta in zip(axes.flat, deltas):
                rows = by_delta[delta]
                _plot_outline(axis, footprint, color="black", linewidth=0.8)
                available = [row for row in rows if finite_float(row.get("return_amount_m")) is not None]
                missing = [row for row in rows if finite_float(row.get("return_amount_m")) is None]
                if missing:
                    axis.scatter(
                        [float(row["cell_center_x"]) for row in missing],
                        [float(row["cell_center_y"]) for row in missing],
                        c="#bdbdbd", marker="s", s=13,
                    )
                if available:
                    spatial_scatter = axis.scatter(
                        [float(row["cell_center_x"]) for row in available],
                        [float(row["cell_center_y"]) for row in available],
                        c=[float(row["return_amount_m"]) for row in available],
                        cmap="coolwarm", vmin=-spatial_bound, vmax=spatial_bound,
                        marker="s", s=16,
                    )
                axis.set_aspect("equal")
                axis.set_title(f"delta={delta:+g} m | cells={len(rows)}", fontsize=8)
                axis.set_xlabel("E [m]")
                axis.set_ylabel("N [m]")
            for axis in list(axes.flat)[len(deltas):]:
                axis.set_axis_off()
            if spatial_scatter is not None:
                figure.colorbar(
                    spatial_scatter, ax=axes, shrink=0.75,
                    label="abs(perturbed P0 error) - abs(post-GS error) [m]",
                )
            figure.suptitle(
                f"{full_building(short)} spatial perturbation return | grey=no post-GS cell",
                fontsize=10,
            )
            output = fig_dir / f"perturbation_spatial_return_{short}.png"
            figure.savefig(output, dpi=180)
            plt.close(figure)
            generated.append(rel(output))
    else:
        skipped.append({"figure": "perturbation_return_map", "reason": "no_nonzero_height_rows"})
    return {"generated": generated, "skipped": skipped}


def _report_number(value: Any) -> str:
    number = finite_float(value)
    return "unavailable" if number is None else f"{number:.3f}"


def _write_wave_report(
    config: Mapping[str, Any],
    contract: Mapping[str, Any],
    score_rows: Sequence[Mapping[str, Any]],
    perturb_rows: Sequence[Mapping[str, Any]],
    figures: Mapping[str, Any],
    trigger: Mapping[str, Any],
    stale: Sequence[str],
) -> Path:
    """Write a measurement-only Phase-3 wave report with explicit gaps."""

    report_path = resolve_repo_path(config["outputs"]["report_md"])
    p0_by_id = {
        short_building(row.get("building_id")): row
        for row in read_csv(resolve_repo_path(config["scoring"]["p0_scores"]))
    }
    lines = [
        "# E5 C001 S3-A-prime Phase 3 read-out measurement (2026-07-15)",
        "",
        "> Measurement output only. Interpretation and verdict: none. GT was opened only after Roofer input finalization.",
        "",
        "## Run contract",
        "",
        f"- Aggregate status: `{contract['status']}`",
        f"- Current inventory: base `{contract['inventory']['counts']['base']}` / height `{contract['inventory']['counts']['height_nonzero']}` / tilt `{contract['inventory']['counts']['tilt']}`",
        f"- Score rows: `{contract['score_row_count']}/{contract['expected_score_row_count']}`; complete rows `{contract['complete_score_count']}`",
        f"- Nonzero-height perturbation rows: `{contract['nonzero_height_row_count']}/{contract['expected_nonzero_height_rows']}`",
        f"- Stale job directories excluded: `{len(stale)}`",
        f"- Serialized Phase-2 gsplat prewarm: `complete`; extension `{contract['prewarm']['extension_sha256']}`.",
        f"- Aggregate reasons: `{'; '.join(contract['errors']) if contract['errors'] else 'none'}`",
        "- Locked read-out: alpha >= 0.5; voxel 0.05 m; min observations 3; SOR 20 / 2.0; canonical depth median.",
        "- Learning runs started by Phase 3: 0; new MASt3R inference: 0.",
        "",
        "## Base A1 r1 measurements",
        "",
        "| building | score status | MVS assembly | P0 raw/accepted/substantive | P0 completeness/rms m | GS raw/accepted/substantive | GS valid/completeness/rms m | P0/GS abs median m | edge P0/GS m | interior P0/GS m | P0/GS coverage |",
        "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for short in config["targets"]:
        bid = full_building(short)
        row = _select_a1_base(score_rows, bid)
        p0 = p0_by_id.get(short, {})
        if row is None:
            lines.append(f"| {bid} | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |")
            continue
        lines.append(
            "| {bid} | {status} | unavailable: {mvs_reason} | {p0raw}/{p0accepted}/{p0sub} | "
            "{p0complete}/{p0rms} | {gsraw}/{gsaccepted}/{gssub} | {gsvalid}/{gscomplete}/{gsrms} | "
            "{p0abs}/{gsabs} | {p0edge}/{gsedge} | "
            "{p0interior}/{gsinterior} | {p0cov}/{gscov} |".format(
                bid=bid, status=row.get("score_status", ""),
                mvs_reason=row.get("mvs_canonical_reason", "unavailable"),
                p0raw=str(parse_bool(p0.get("geometry_has_lod22"))).lower(),
                p0accepted=str(parse_bool(p0.get("has_lod22"))).lower(),
                p0sub=str(parse_bool(p0.get("substantive_filter"))).lower(),
                p0complete=_report_number(p0.get("citygml_completeness")),
                p0rms=_report_number(p0.get("citygml_roof_rms_m")),
                gsraw=str(parse_bool(row.get("geometry_has_lod22"))).lower(),
                gsaccepted=str(parse_bool(row.get("has_lod22"))).lower(),
                gssub=str(parse_bool(row.get("substantive_filter"))).lower(),
                gsvalid=str(parse_bool(row.get("val3dity_valid"))).lower(),
                gscomplete=_report_number(row.get("citygml_completeness")),
                gsrms=_report_number(row.get("citygml_roof_rms_m")),
                p0abs=_report_number(row.get("p0_height_error_abs_median_m")),
                gsabs=_report_number(row.get("height_error_abs_median_m")),
                p0edge=_report_number(row.get("p0_edge_height_error_abs_median_m")),
                gsedge=_report_number(row.get("edge_height_error_abs_median_m")),
                p0interior=_report_number(row.get("p0_interior_height_error_abs_median_m")),
                gsinterior=_report_number(row.get("interior_height_error_abs_median_m")),
                p0cov=_report_number(row.get("p0_coverage_ratio")),
                gscov=_report_number(row.get("coverage_ratio")),
            )
        )
    lines.extend([
        "",
        "## Height perturbation measurements",
        "",
        f"- Exact trigger evaluation complete: `{str(trigger['evaluation_complete']).lower()}`",
        f"- Return-signal field: `{str(trigger['return_signal']).lower()}`; qualifying rows `{trigger['qualifying_count']}`.",
        "",
        "| building | delta m | score status | perturbed P0 signed m | post-GS signed m | return amount m | condition |",
        "|---|---:|---|---:|---:|---:|---|",
    ])
    for row in perturb_rows:
        delta = finite_float(row.get("delta_m"))
        if delta in (None, 0.0):
            continue
        lines.append(
            f"| {row.get('building_id', '')} | {delta:+g} | {row.get('score_status', '')} | "
            f"{_report_number(row.get('perturbed_p0_signed_median_error_m'))} | "
            f"{_report_number(row.get('post_gs_signed_median_error_m'))} | "
            f"{_report_number(row.get('signed_error_reduction_m'))} | "
            f"{str(parse_bool(row.get('return_condition_met'))).lower()} |"
        )
    lines.extend(["", "## Figures", ""])
    for path_text in figures.get("generated", []):
        path = Path(str(path_text))
        try:
            target = path.relative_to("docs")
        except ValueError:
            target = path
        lines.append(f"- [{path.name}]({target.as_posix()})")
    for item in figures.get("skipped", []):
        lines.append(f"- unavailable | `{item.get('figure')}` | `{item.get('reason')}`")
    lines.extend([
        "",
        "## Boundary record",
        "",
        f"- {config['scoring']['gt_open_boundary']}",
        "- Supplied footprint passed to Roofer: `false`.",
        "- LoD2, ALS, footprint roles: score/overlay only.",
        "- Interpretation or verdict: none.",
        "",
    ])
    atomic_text(report_path, "\n".join(lines))
    return report_path


def aggregate(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    config = load_json(config_path)
    prewarm_binding = phase2_prewarm_binding(config)
    job_root = resolve_repo_path(config["outputs"]["job_root"])
    jobs = discover_jobs(config)
    inventory = inventory_contract(config, jobs)
    current_ids = {job.run_id for job in jobs}
    stale = sorted(
        path.name for path in job_root.iterdir()
        if path.is_dir() and path.name not in current_ids
    ) if job_root.is_dir() else []
    score_rows: list[dict[str, Any]] = []
    perturb_rows: list[dict[str, Any]] = []
    perturbation_cells: list[dict[str, Any]] = []
    invalid_current: list[dict[str, str]] = []
    current_score_fingerprint: dict[str, Any] | None = None
    for job in jobs:
        job_dir = job_root / job.run_id
        score_path = job_dir / "score_row.json"
        score_manifest_path = job_dir / "score_manifest.json"
        input_manifest_path = job_dir / "roofer_input_manifest.json"
        if not (score_path.is_file() and score_manifest_path.is_file() and input_manifest_path.is_file()):
            invalid_current.append({"run_id": job.run_id, "reason": "current_score_bundle_missing"})
            continue
        try:
            row = load_json(score_path)
            manifest = load_json(score_manifest_path)
            input_manifest = load_json(input_manifest_path)
            current_pre = pre_readout_fingerprint(config_path, config, job)
            boundary_finalized = bool(
                input_manifest.get("pre_readout_fingerprint", {}).get("digest")
                == current_pre["digest"]
                and input_manifest.get("supplied_footprint_opened") is False
                and input_manifest.get("lod2_opened") is False
                and input_manifest.get("als_opened") is False
            )
            if not boundary_finalized:
                raise RuntimeError("roofer_input_not_finalized_for_current_pre_fingerprint")
            if current_score_fingerprint is None:
                # Score-only sources are hashed only after the first current
                # read-out input is proven finalized and GT-free.
                current_score_fingerprint = score_only_fingerprint(config)
            expected_full = full_reuse_fingerprint(current_pre, current_score_fingerprint)
            valid = bool(
                str(row.get("run_id", "")) == job.run_id
                and manifest.get("job") == asdict(job)
                and manifest.get("score_row_sha256") == sha256_file(score_path)
                and manifest.get("full_reuse_fingerprint") == expected_full
                and manifest.get("roofer_input_manifest_sha256")
                == sha256_file(input_manifest_path)
                and boundary_finalized
            )
            current_input_npz = job_dir / "roofer_input.npz"
            valid = bool(
                valid and current_input_npz.is_file()
                and input_manifest.get("roofer_input_npz_sha256") == sha256_file(current_input_npz)
            )
            if manifest.get("cityjson"):
                current_cityjson = resolve_repo_path(manifest["cityjson"])
                valid = bool(
                    valid and current_cityjson.is_file()
                    and manifest.get("cityjson_sha256") == sha256_file(current_cityjson)
                )
            for path_key, hash_key in (
                ("val3dity_report", "val3dity_report_sha256"),
                ("val3dity_log", "val3dity_log_sha256"),
            ):
                if manifest.get(path_key):
                    artifact = resolve_repo_path(manifest[path_key])
                    valid = bool(
                        valid and artifact.is_file()
                        and manifest.get(hash_key) == sha256_file(artifact)
                    )
            if not valid:
                raise RuntimeError("fingerprint_or_boundary_mismatch")
            score_rows.append(row)
            perturbation_expected = bool(
                job.arm.lower() == str(config["perturbation"]["height_arm"]).lower()
                and job.replicate.lower() == str(config["perturbation"]["height_replicate"]).lower()
                and job.perturbation_type in {"none", "height"}
            )
            perturb_path = job_dir / "perturbation_row.json"
            if perturbation_expected:
                if not perturb_path.is_file():
                    raise RuntimeError("perturbation_row_missing")
                perturb = load_json(perturb_path)
                if (
                    str(perturb.get("run_id", "")) != job.run_id
                    or manifest.get("perturbation_row_sha256") != sha256_file(perturb_path)
                ):
                    raise RuntimeError("perturbation_run_id_mismatch")
                perturb_rows.append(perturb)
                cells_path = job_dir / "perturbation_cells.csv"
                if not cells_path.is_file() or manifest.get("perturbation_cells_sha256") != sha256_file(cells_path):
                    raise RuntimeError("perturbation_cells_missing_or_hash_mismatch")
                perturbation_cells.extend(read_csv(cells_path))
        except Exception as exc:
            invalid_current.append({"run_id": job.run_id, "reason": f"{type(exc).__name__}:{exc}"})
            score_rows = [row for row in score_rows if str(row.get("run_id")) != job.run_id]
            perturb_rows = [row for row in perturb_rows if str(row.get("run_id")) != job.run_id]
            perturbation_cells = [
                row for row in perturbation_cells if str(row.get("run_id")) != job.run_id
            ]

    score_rows.sort(key=lambda row: (
        str(row.get("building_id", "")), str(row.get("arm", "")),
        str(row.get("replicate", "")), finite_float(row.get("perturbation_value")) or 0.0,
        str(row.get("run_id", "")),
    ))
    perturb_rows.sort(key=lambda row: (
        str(row.get("building_id", "")), finite_float(row.get("delta_m")) or 0.0,
        str(row.get("run_id", "")),
    ))
    perturbation_cells.sort(key=lambda row: (
        str(row.get("building_id", "")), finite_float(row.get("delta_m")) or 0.0,
        int(float(row.get("cell_ix", 0))), int(float(row.get("cell_iy", 0))),
    ))
    scores_path = resolve_repo_path(config["outputs"]["scores_csv"])
    perturbation_path = resolve_repo_path(config["outputs"]["perturbation_csv"])
    cells_path = resolve_repo_path(config["outputs"]["perturbation_cells_csv"])
    atomic_csv(scores_path, score_rows, SCORE_FIELDS)
    atomic_csv(perturbation_path, perturb_rows, PERTURB_FIELDS)
    atomic_csv(cells_path, perturbation_cells, PERTURB_CELL_FIELDS)

    expected_score_rows = len(jobs)
    complete_score_count = sum(str(row.get("score_status")) == "complete" for row in score_rows)
    nonzero_rows = [
        row for row in perturb_rows if finite_float(row.get("delta_m")) not in (None, 0.0)
    ]
    complete_nonzero = sum(str(row.get("score_status")) == "complete" for row in nonzero_rows)
    expected_nonzero = int(config["phase2"]["height_nonzero_expected_jobs"])
    errors = list(inventory["errors"])
    if len(score_rows) != expected_score_rows:
        errors.append(f"score_rows_{len(score_rows)}_expected_{expected_score_rows}")
    if invalid_current:
        errors.append(f"invalid_current_rows_{len(invalid_current)}")
    if complete_score_count == 0:
        errors.append("zero_complete_score_rows_forbidden")
    if len(nonzero_rows) != expected_nonzero:
        errors.append(f"height_rows_{len(nonzero_rows)}_expected_{expected_nonzero}")
    aggregate_status = "complete" if not errors else "partial_fail_closed"
    evaluation_complete = bool(
        aggregate_status == "complete" and complete_nonzero == expected_nonzero
    )
    trigger = perturbation_trigger(perturb_rows, config["perturbation"]["trigger_rule"])
    raw_return_signal = bool(trigger["return_signal"])
    trigger.update({
        "raw_return_signal": raw_return_signal,
        "return_signal": bool(raw_return_signal and evaluation_complete),
        "expected_nonzero_height_rows": expected_nonzero,
        "observed_nonzero_height_rows": len(nonzero_rows),
        "complete_nonzero_height_rows": complete_nonzero,
        "evaluation_complete": evaluation_complete,
        "scores_csv": config["outputs"]["scores_csv"],
        "perturbation_csv": config["outputs"]["perturbation_csv"],
        "perturbation_cells_csv": config["outputs"]["perturbation_cells_csv"],
        "source_score_sha256": sha256_file(scores_path),
        "source_perturbation_sha256": sha256_file(perturbation_path),
        "source_perturbation_cells_sha256": sha256_file(cells_path),
        "tilt_deltas_deg": config["perturbation"]["tilt_deltas_deg"],
    })
    atomic_json(resolve_repo_path(config["outputs"]["tilt_trigger"]), trigger)
    figures = {"generated": [], "skipped": [{"figure": "all", "reason": "--no-figures"}]}
    if not args.no_figures:
        figures = _phase3_figures(config, score_rows, perturb_rows, perturbation_cells)
    contract = {
        "status": aggregate_status, "errors": errors, "inventory": inventory,
        "prewarm": prewarm_binding,
        "expected_score_row_count": expected_score_rows, "score_row_count": len(score_rows),
        "complete_score_count": complete_score_count,
        "expected_nonzero_height_rows": expected_nonzero,
        "nonzero_height_row_count": len(nonzero_rows),
        "complete_nonzero_height_row_count": complete_nonzero,
        "invalid_current_rows": invalid_current, "stale_job_directories": stale,
    }
    report_path = _write_wave_report(
        config, contract, score_rows, perturb_rows, figures, trigger, stale,
    )
    status_rows = read_csv(resolve_repo_path(config["outputs"]["status_csv"]))
    source_paths = [
        config_path, Path(__file__),
        resolve_repo_path(config["scoring"]["p0_scores"]),
        resolve_repo_path(config["scoring"]["mvs_scores"]),
        resolve_repo_path(config["outputs"]["image_verification"]),
        resolve_repo_path(config["outputs"]["prewarm_verification"]),
        resolve_repo_path(config["outputs"]["prewarm_log"]),
        resolve_repo_path(config["phase2_prewarm"]["lock"]),
        resolve_repo_path(config["phase2_prewarm"]["prepare_manifest"]),
        resolve_repo_path(config["phase2_prewarm"]["manifest"]),
        resolve_repo_path(config["phase2_prewarm"]["script"]),
        resolve_repo_path(config["phase2_prewarm"]["launcher"]),
    ]
    outputs = {
        "prewarm_verification": config["outputs"]["prewarm_verification"],
        "prewarm_verification_sha256": sha256_file(
            resolve_repo_path(config["outputs"]["prewarm_verification"])
        ),
        "prewarm_log": config["outputs"]["prewarm_log"],
        "prewarm_log_sha256": sha256_file(
            resolve_repo_path(config["outputs"]["prewarm_log"])
        ),
        "scores_csv": config["outputs"]["scores_csv"],
        "scores_sha256": sha256_file(scores_path),
        "perturbation_csv": config["outputs"]["perturbation_csv"],
        "perturbation_sha256": sha256_file(perturbation_path),
        "perturbation_cells_csv": config["outputs"]["perturbation_cells_csv"],
        "perturbation_cells_sha256": sha256_file(cells_path),
        "report_md": config["outputs"]["report_md"],
        "report_sha256": sha256_file(report_path),
        "tilt_trigger": config["outputs"]["tilt_trigger"],
        "tilt_trigger_sha256": sha256_file(resolve_repo_path(config["outputs"]["tilt_trigger"])),
    }
    manifest = {
        "schema": "jointbuildgs.s3ap.phase3.aggregate.v2",
        "created_utc": utc_now(), "status": aggregate_status,
        "aggregate_contract": contract, "status_row_count": len(status_rows),
        "phase2_serialized_gsplat_prewarm": prewarm_binding,
        "trigger": trigger, "figures": figures, "training_runs_started": 0,
        "new_mast3r_inference_runs": 0,
        "gt_boundary": config["scoring"]["gt_open_boundary"],
        "supplied_footprint_passed_to_roofer": False,
        "source_sha256": {
            rel(path): sha256_file(path) for path in source_paths if path.is_file()
        },
        "outputs": outputs, "interpretation_or_verdict": None,
    }
    atomic_json(resolve_repo_path(config["outputs"]["manifest"]), manifest)
    print(json.dumps({
        "status": aggregate_status, "scores": len(score_rows),
        "complete_scores": complete_score_count, "perturbations": len(perturb_rows),
        "return_signal": trigger["return_signal"],
        "evaluation_complete": trigger["evaluation_complete"], "errors": errors,
    }, ensure_ascii=False))
    if aggregate_status != "complete":
        raise RuntimeError("aggregate fail-closed: " + ";".join(errors))


class Controller:
    """Host-only Docker orchestrator; scientific work remains containerized."""

    def __init__(self, config_path: Path, config: Mapping[str, Any], args: argparse.Namespace):
        self.config_path = config_path.resolve()
        self.config = config
        self.args = args
        self.status_path = resolve_repo_path(config["outputs"]["status_csv"])
        self.log_path = resolve_repo_path(config["outputs"]["run_log"])
        self.job_root = resolve_repo_path(config["outputs"]["job_root"])
        self.status_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.status_rows = read_csv(self.status_path) if args.resume else []
        self.prewarm_verification: dict[str, Any] | None = None
        if not args.resume:
            atomic_text(self.log_path, "")

    def log(self, message: str) -> None:
        line = f"{utc_now()} {message}"
        with self.log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        print(line, flush=True)

    def status(self, job: Job, stage: str, status: str, reason: str = "", gpu_id: str = "") -> None:
        row = {
            "run_id": job.run_id, "building_id": full_building(job.building_id),
            "arm": job.arm, "replicate": job.replicate,
            "perturbation_type": job.perturbation_type,
            "perturbation_value": job.perturbation_value,
            "stage": stage, "status": status, "reason": reason,
            "updated_utc": utc_now(), "checkpoint": job.checkpoint,
            "prepared_root": job.prepared_root,
            "job_dir": rel(self.job_root / job.run_id), "gpu_id": gpu_id,
        }
        with self.status_lock:
            self.status_rows.append(row)
            atomic_csv(self.status_path, self.status_rows, STATUS_FIELDS)
        self.log(f"run={job.run_id} stage={stage} status={status} reason={reason or '-'} gpu={gpu_id or '-'}")

    def _docker_command(
        self,
        image: str,
        worker_args: Sequence[str],
        *,
        gpu_id: str | None = None,
    ) -> list[str]:
        extension_root = resolve_repo_path(self.config["outputs"]["torch_extensions"])
        extension_root.mkdir(parents=True, exist_ok=True)
        command = [
            "docker", "run", "--rm", "-i", "--user", f"{os.getuid()}:{os.getgid()}",
            "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp/matplotlib",
            "-e", "XDG_CACHE_HOME=/tmp",
            "-e", f"TORCH_EXTENSIONS_DIR={container_path(extension_root)}",
            "-v", f"{REPO}:{CONTAINER_REPO}",
            "-w", str(CONTAINER_REPO),
        ]
        if gpu_id is not None:
            command.extend(["--gpus", f"device={gpu_id}"])
        command.extend([image, "python3", str(SCRIPT_REL), *worker_args])
        return command

    def _run_command(self, command: Sequence[str], log_path: Path) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("+ " + " ".join(command) + "\n")
            handle.flush()
            proc = subprocess.run(
                list(command), text=True, stdout=handle, stderr=subprocess.STDOUT,
                check=False,
            )
            handle.write(f"[exit] {proc.returncode}\n")
            handle.flush()
            os.fsync(handle.fileno())
        return int(proc.returncode)

    def run_phase2_prewarm(self) -> dict[str, Any]:
        """Run exactly one serialized gsplat import before GPU queues exist."""

        if self.prewarm_verification is not None:
            raise RuntimeError("Phase-2 gsplat prewarm was already invoked by this controller")
        launcher = resolve_repo_path(self.config["phase2_prewarm"]["launcher"])
        log_path = resolve_repo_path(self.config["outputs"]["prewarm_log"])
        self.log(f"phase2_prewarm start launcher={rel(launcher)} serialized=true")
        exit_code = self._run_command(["bash", str(launcher), "prewarm"], log_path)
        try:
            verification = verify_phase2_prewarm(self.config, exit_code)
        except Exception as exc:
            self.log(f"phase2_prewarm status=failed reason={type(exc).__name__}:{exc}")
            raise
        self.log(
            "phase2_prewarm status=complete "
            f"extension_sha256={verification['extension_sha256']} "
            f"verification={self.config['outputs']['prewarm_verification']}"
        )
        self.prewarm_verification = verification
        return verification

    def _worker(self, command_name: str, job: Job, job_dir: Path, image: str, gpu_id: str | None = None, extra: Sequence[str] = ()) -> int:
        command = self._docker_command(
            image,
            [
                command_name,
                "--config", container_path(self.config_path),
                "--job-spec", container_path(job_dir / "job_spec.json"),
                "--output-dir", container_path(job_dir),
                *extra,
            ],
            gpu_id=gpu_id,
        )
        return self._run_command(command, job_dir / "logs" / f"{command_name}.log")

    def _roofer(self, job: Job, job_dir: Path) -> int:
        roofer_dir = job_dir / "roofer"
        if roofer_dir.exists():
            shutil.rmtree(roofer_dir)
        roofer_dir.mkdir(parents=True, exist_ok=True)
        roof = self.config["roof_evidence"]
        spec = self.config["roofer"]
        command = [
            "docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{REPO}:{CONTAINER_REPO}", "-w", container_path(job_dir),
            spec["image"],
            "--id-attribute", spec["id_attribute"],
            "--jobs", str(spec["jobs"]), "--srs", spec["srs"],
            "--bld-class", str(roof["roof_class"]),
            "--grnd-class", str(roof["ground_class"]), "--lod22",
            container_path(job_dir / "gs_roof_with_observed_ground_classified.las"),
            container_path(job_dir / "gs_point_evidence_derived_roofprint.geojson"),
            container_path(roofer_dir),
        ]
        return self._run_command(command, job_dir / "logs" / "roofer.log")

    def run_job(self, job: Job, gpu_id: str) -> None:
        job_dir = self.job_root / job.run_id
        job_dir.mkdir(parents=True, exist_ok=True)
        job_spec = {
            "schema": "jointbuildgs.s3ap.phase3.job.v1", "created_utc": utc_now(),
            "job": asdict(job), "phase3_config": rel(self.config_path),
            "phase3_config_sha256": sha256_file(self.config_path),
        }
        atomic_json(job_dir / "job_spec.json", job_spec)
        checkpoint = resolve_repo_path(job.checkpoint)
        prepared = resolve_repo_path(job.prepared_root)
        if not checkpoint.exists():
            self.status(job, "checkpoint_gate", "skipped_final_missing", "final.pt missing", gpu_id)
            return
        if not prepared.exists():
            self.status(job, "prepared_gate", "failed", "prepared crop root missing", gpu_id)
            return
        current_pre_fingerprint = pre_readout_fingerprint(self.config_path, self.config, job)
        job_spec["pre_readout_fingerprint"] = current_pre_fingerprint
        atomic_json(job_dir / "job_spec.json", job_spec)
        self.status(job, "checkpoint_gate", "complete", "", gpu_id)
        score_manifest_path = job_dir / "score_manifest.json"
        score_row_path = job_dir / "score_row.json"
        roofer_input_manifest_path = job_dir / "roofer_input_manifest.json"
        if (
            self.args.resume and not self.args.force and score_manifest_path.exists()
            and score_row_path.exists() and roofer_input_manifest_path.exists()
        ):
            try:
                previous_manifest = load_json(score_manifest_path)
                previous_row = load_json(score_row_path)
                previous_input = load_json(roofer_input_manifest_path)
                readout_was_finalized = bool(
                    previous_input.get("pre_readout_fingerprint", {}).get("digest")
                    == current_pre_fingerprint["digest"]
                    and previous_input.get("supplied_footprint_opened") is False
                    and previous_input.get("lod2_opened") is False
                    and previous_input.get("als_opened") is False
                )
                # Score-only inputs are opened here only after an existing manifest
                # proves that the read-out input was already finalized unchanged.
                current_score_fingerprint = (
                    score_only_fingerprint(self.config) if readout_was_finalized else None
                )
                current_full = (
                    full_reuse_fingerprint(current_pre_fingerprint, current_score_fingerprint)
                    if current_score_fingerprint is not None else None
                )
                perturbation_expected = bool(
                    job.arm.lower() == str(self.config["perturbation"]["height_arm"]).lower()
                    and job.replicate.lower() == str(self.config["perturbation"]["height_replicate"]).lower()
                    and job.perturbation_type in {"none", "height"}
                )
                perturbation_integrity = True
                if perturbation_expected:
                    perturbation_row_path = job_dir / "perturbation_row.json"
                    perturbation_cells_path = job_dir / "perturbation_cells.csv"
                    perturbation_integrity = bool(
                        perturbation_row_path.is_file() and perturbation_cells_path.is_file()
                        and previous_manifest.get("perturbation_row_sha256")
                        == sha256_file(perturbation_row_path)
                        and previous_manifest.get("perturbation_cells_sha256")
                        == sha256_file(perturbation_cells_path)
                    )
                input_npz = job_dir / "roofer_input.npz"
                readout_integrity = bool(
                    input_npz.is_file()
                    and previous_input.get("roofer_input_npz_sha256") == sha256_file(input_npz)
                    and previous_manifest.get("roofer_input_manifest_sha256")
                    == sha256_file(roofer_input_manifest_path)
                )
                if previous_input.get("status") == "prepared":
                    las_path = job_dir / "gs_roof_with_observed_ground_classified.las"
                    roofprint_path = job_dir / "gs_point_evidence_derived_roofprint.geojson"
                    readout_integrity = bool(
                        readout_integrity and las_path.is_file() and roofprint_path.is_file()
                        and previous_input.get("roofer_las_sha256") == sha256_file(las_path)
                        and previous_input.get("derived_roofprint_sha256") == sha256_file(roofprint_path)
                    )
                cityjson_integrity = True
                if previous_manifest.get("cityjson"):
                    previous_cityjson = resolve_repo_path(previous_manifest["cityjson"])
                    cityjson_integrity = bool(
                        previous_cityjson.is_file()
                        and previous_manifest.get("cityjson_sha256") == sha256_file(previous_cityjson)
                    )
                for path_key, hash_key in (
                    ("val3dity_report", "val3dity_report_sha256"),
                    ("val3dity_log", "val3dity_log_sha256"),
                ):
                    if previous_manifest.get(path_key):
                        artifact = resolve_repo_path(previous_manifest[path_key])
                        cityjson_integrity = bool(
                            cityjson_integrity and artifact.is_file()
                            and previous_manifest.get(hash_key) == sha256_file(artifact)
                        )
                complete_reuse = bool(
                    readout_was_finalized
                    and previous_manifest.get("full_reuse_fingerprint") == current_full
                    and str(previous_row.get("run_id", "")) == job.run_id
                    and previous_manifest.get("score_row_sha256") == sha256_file(score_row_path)
                    and perturbation_integrity
                    and readout_integrity and cityjson_integrity
                )
            except Exception:
                complete_reuse = False
            if complete_reuse:
                self.status(job, "pipeline", "reused", "full pre-readout and score-only fingerprints matched", gpu_id)
                return
        extraction_manifest = job_dir / "extraction_manifest.json"
        reuse_extract = False
        if self.args.resume and not self.args.force and extraction_manifest.exists():
            try:
                old = load_json(extraction_manifest)
                fused_path = job_dir / "fused_depth.npz"
                reuse_extract = bool(
                    old.get("pre_readout_fingerprint", {}).get("digest")
                    == current_pre_fingerprint["digest"]
                    and fused_path.is_file()
                    and old.get("output_sha256") == sha256_file(fused_path)
                )
            except Exception:
                reuse_extract = False
        if reuse_extract:
            self.status(job, "extract", "reused", "pre-readout fingerprint and fused hash matched", gpu_id)
        else:
            code = self._worker(
                "extract-job", job, job_dir,
                self.config["containers"]["render_image"], gpu_id,
            )
            if code != 0:
                self.status(job, "extract", "failed", f"exit_{code}", gpu_id)
                return
            self.status(job, "extract", "complete", "", gpu_id)
        code = self._worker(
            "prepare-roofer-job", job, job_dir,
            self.config["containers"]["tools_image"], None,
        )
        if code != 0:
            self.status(job, "prepare_roofer", "failed", f"exit_{code}", gpu_id)
            return
        input_manifest = load_json(job_dir / "roofer_input_manifest.json")
        self.status(job, "prepare_roofer", str(input_manifest["status"]), "", gpu_id)
        if input_manifest["status"] == "prepared":
            roofer_exit = self._roofer(job, job_dir)
            self.status(
                job, "roofer", "complete" if roofer_exit == 0 else "failed",
                "" if roofer_exit == 0 else f"exit_{roofer_exit}", gpu_id,
            )
        else:
            roofer_exit = 125
            self.status(job, "roofer", "not_run", str(input_manifest["status"]), gpu_id)
        code = self._worker(
            "score-job", job, job_dir, self.config["containers"]["tools_image"], None,
            ["--roofer-exit-code", str(roofer_exit)],
        )
        if code != 0:
            self.status(job, "score", "failed", f"exit_{code}", gpu_id)
            return
        score = load_json(job_dir / "score_row.json")
        self.status(job, "score", str(score["score_status"]), str(score.get("score_reason", "")), gpu_id)

    def run_aggregate(self) -> int:
        command = self._docker_command(
            self.config["containers"]["tools_image"],
            [
                "aggregate", "--config", container_path(self.config_path),
                *(["--no-figures"] if self.args.no_figures else []),
            ],
        )
        return self._run_command(command, resolve_repo_path(self.config["outputs"]["phase3_root"]) / "aggregate.log")


def run_controller(args: argparse.Namespace) -> None:
    if Path("/.dockerenv").exists():
        raise RuntimeError("run is host orchestration; invoke it from the repository host shell")
    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    image_verification = verify_docker_images(config)
    jobs = discover_jobs(config, args.inventory)
    contract = inventory_contract(config, jobs, args.inventory)
    if contract["status"] != "complete":
        raise RuntimeError(f"Phase-2 inventory contract failed: {contract['errors']}")
    if args.run_id:
        wanted = set(args.run_id)
        jobs = [job for job in jobs if job.run_id in wanted]
    if args.arm:
        wanted = {value.lower() for value in args.arm}
        jobs = [job for job in jobs if job.arm.lower() in wanted]
    if args.building:
        wanted = {short_building(value) for value in args.building}
        jobs = [job for job in jobs if job.building_id in wanted]
    if not jobs:
        raise RuntimeError("no Phase-2 jobs selected")
    controller = Controller(config_path, config, args)
    controller.log(
        f"start jobs={len(jobs)} workers={args.max_workers} training=0 mast3r_inference=0 "
        f"image_verification={image_verification['status']}"
    )
    gpu_ids = [value.strip() for value in args.gpu_ids.split(",") if value.strip()]
    if not gpu_ids:
        raise RuntimeError("--gpu-ids must contain at least one id")
    prewarm_verification = controller.run_phase2_prewarm()
    workers = max(1, min(int(args.max_workers), len(gpu_ids), len(jobs)))
    active_gpu_ids = gpu_ids[:workers]
    controller.log(
        f"gpu_serial_queues={','.join(active_gpu_ids)} one_worker_per_gpu=true "
        f"prewarm_verification={prewarm_verification['status']}"
    )
    errors = run_gpu_serial_queues(jobs, active_gpu_ids, controller.run_job)
    for job, gpu_id, exc in errors:
        controller.status(
            job, "pipeline", "failed", f"{type(exc).__name__}:{exc}", gpu_id,
        )
    aggregate_exit = controller.run_aggregate()
    controller.log(f"aggregate exit={aggregate_exit}")
    if aggregate_exit != 0:
        raise RuntimeError(f"aggregate worker failed: exit {aggregate_exit}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="host Docker orchestration")
    run.add_argument("--config", default=str(DEFAULT_CONFIG))
    run.add_argument("--inventory", action="append", default=None)
    run.add_argument("--run-id", action="append", default=None)
    run.add_argument("--arm", action="append", default=None)
    run.add_argument("--building", action="append", default=None)
    run.add_argument("--gpu-ids", default="0,1")
    run.add_argument("--max-workers", type=int, default=2)
    run.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--force", action="store_true")
    run.add_argument("--no-figures", action="store_true")
    for name in ("extract-job", "prepare-roofer-job", "score-job"):
        worker = sub.add_parser(name)
        worker.add_argument("--config", required=True)
        worker.add_argument("--job-spec", required=True)
        worker.add_argument("--output-dir", required=True)
        if name == "score-job":
            worker.add_argument("--roofer-exit-code", type=int, required=True)
    agg = sub.add_parser("aggregate")
    agg.add_argument("--config", required=True)
    agg.add_argument("--no-figures", action="store_true")
    plan = sub.add_parser("plan", help="print resolved Phase-2 jobs without processing")
    plan.add_argument("--config", default=str(DEFAULT_CONFIG))
    plan.add_argument("--inventory", action="append", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        run_controller(args)
    elif args.command == "extract-job":
        extract_job(args)
    elif args.command == "prepare-roofer-job":
        prepare_roofer_job(args)
    elif args.command == "score-job":
        score_job(args)
    elif args.command == "aggregate":
        aggregate(args)
    elif args.command == "plan":
        config = load_json(Path(args.config))
        print(json.dumps([asdict(job) for job in discover_jobs(config, args.inventory)], ensure_ascii=False, indent=2))
    else:  # pragma: no cover
        raise RuntimeError(args.command)


if __name__ == "__main__":
    main()
