#!/usr/bin/env python3
"""S3-A semantic-guided config, launch, and 1k-gate audit orchestrator.

The script is intentionally non-automatic: ``generate-configs`` and
``generate-regate-config`` only write configs, while training starts only from
an explicit ``train-one`` invocation.  ``train-one --dry-run`` prints the exact
Docker command without starting a container.

Locked experiment shape
-----------------------
* exact base: S2p Arm 1-prime r1;
* gate: max_iter=2500, active semantic updates 1500..2499,
  generic model-parameter gradient audit every 100 updates, rendered-depth
  P-I audit every 10 updates;
* full r1/r2: max_iter=30000, generic audit every 500, semantic audit every
  5000;
* weights: smooth=0.25, plane=0.25, boundary-normal=0.01;
* no monocular depth;
* all training remains blocked until every C001 view has a footprint-split
  semantic-region cache file.

``gate-audit`` merges ``audit/loss_grad_norms.csv`` and
``audit/semantic_geometry.csv`` into the locked docs CSV.  Its pass/fail fields
are mechanical evaluations of the preregistered thresholds, not a research
verdict.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[3]
HOST_REPO = Path(os.environ.get("S3_HOST_REPO", str(REPO))).resolve()
SCRIPT_PATH = Path(__file__).resolve()
DEV_IMAGE = "jointbuildgs:dev"
RUN_ID = "20260713_e5_c001_s3_semantic_guided"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID

BASE_CONFIG = REPO / "configs/tum_mob/e5_s2p_interaction/gs_e5_C001_s2p_arm1p_dense_r1.yaml"
CONFIG_DIR = REPO / "configs/tum_mob/e5_s3_semantic_guided"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s3_semantic_guided/C001"
CKPT_ROOT = RESULTS_ROOT / "runs"
TRAIN_LOG_ROOT = RESULTS_ROOT / "train_logs"
TORCH_EXTENSIONS = RESULTS_ROOT / "torch_extensions"
# Produced by the T0 semantic-region/reference-QA harness.  Training outputs
# stay under e5_s3_semantic_guided, while this fixed input cache keeps its own
# T0 provenance root.
SEMANTIC_REGION_CACHE = REPO / "results/tum_transfer/e5_s3/C001/semantic_regions"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"

CSV_INVENTORY = REPO / "docs/e5_c001_s3_inventory.csv"
CSV_GATE_AUDIT = REPO / "docs/e5_c001_s3_loss_gate_audit.csv"
CSV_SEED_INVENTORY = REPO / "docs/e5_c001_s3_seed_inventory.csv"
MANIFEST = RUN_DIR / "config_gate_manifest.json"
VERSIONS = RUN_DIR / "versions.txt"

GATE_RUN = "gs_e5_C001_s3a_semantic_guided_gate"
FULL_RUNS = [
    "gs_e5_C001_s3a_semantic_guided_r1",
    "gs_e5_C001_s3a_semantic_guided_r2",
]
PI_TARGETS = ["4907199", "8568391", "8568392"]
DENSIFY_AUDIT_BUILDINGS = [
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_8568392",
]
DENSIFY_AUDIT_ADDED_BUILDINGS = DENSIFY_AUDIT_BUILDINGS[4:]

ACTIVE_START = 1500
GATE_MAX_ITER = 2500
FULL_MAX_ITER = 30000
GATE_GENERIC_AUDIT_EVERY = 100
GATE_SEMANTIC_AUDIT_EVERY = 10
FULL_GENERIC_AUDIT_EVERY = 500
FULL_SEMANTIC_AUDIT_EVERY = 5000
GRAD_SHARE_MAX = 0.40
PRIMARY_AUDIT_COMPONENTS = {
    "photo",
    "depth",
    "mono_depth",
    "normal",
    "nc",
    "distort",
    "semantic",
    "mvc",
    "mutual",
    "structure",
    "semdepth",
    "boundary_normal",
}
DETAIL_AUDIT_COMPONENTS = {"semdepth_smooth", "semdepth_plane"}

SEMANTIC_DELTA = {
    "w_semdepth_smooth": 0.25,
    "w_semdepth_plane": 0.25,
    "w_boundary_normal": 0.01,
    "semantic_geometry_warmup": ACTIVE_START,
    "semantic_roof_class": 1,
    "semantic_alpha_threshold": 0.5,
    "semantic_source_component_min_pixels": 256,
    "semantic_component_connectivity": 8,
    "semantic_footprint_buffer_m": 20.0,
    "semantic_cutline_half_width_px": 7,
    "semantic_plane_min_pixels": 64,
    "semantic_plane_refit_every": 500,
    "semantic_huber_delta": 1.0,
    "semantic_plane_irls_iterations": 5,
    "semantic_boundary_band_px": 5,
    "semantic_pi_target_buildings": PI_TARGETS,
    "semantic_pi_event_until_positive": False,
}
SEMANTIC_DELTA_KEYS = tuple(SEMANTIC_DELTA)
GATE_CONTROL_KEYS = ("max_iter",)
AUDIT_CONTROL_KEYS = ("loss_grad_audit_every", "semantic_geometry_audit_every")
# Per dispatch: these are the only path/routing changes and are not scientific
# hyperparameter deltas.
RECORDING_ONLY_KEYS = (
    "out_dir",
    "semantic_region_cache",
    "densify_audit_buildings",
)
ALLOWED_BASE_OVERRIDES = set(GATE_CONTROL_KEYS + AUDIT_CONTROL_KEYS + RECORDING_ONLY_KEYS)

REQUIRED_BASE_VALUES = {
    "seed": 2001,
    "max_iter": 30000,
    "w_distort": 100.0,
    "w_normal": 0.05,
    "w_nc": 0.05,
    "final_prune_opa": 0.0,
    "prune_opa": 0.05,
    "w_mono_depth": 0.0,
    "load_semantic": True,
    "sem_detach_geometry": False,
    "ckpt_every": 5000,
}


def rel(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def ws(path: Path | str) -> str:
    return f"/workspace/JointBuildGS/{rel(path)}"


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture(cmd: list[str]) -> str:
    try:
        process = subprocess.run(
            cmd,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return (process.stdout or "").strip()


def committed_unchanged(path: Path) -> dict[str, Any]:
    """Report whether ``path`` exists in HEAD and matches the working tree."""

    relative = rel(path)
    tracked = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{relative}"],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    unchanged = tracked and subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", relative],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    return {
        "path": relative,
        "exists": path.exists(),
        "tracked_in_head": tracked,
        "matches_head": unchanged,
        "committed_unchanged": path.exists() and tracked and unchanged,
    }


def docker_image_id() -> str:
    supplied = os.environ.get("S3_DOCKER_IMAGE_ID", "").strip()
    return supplied or capture(["docker", "image", "inspect", "--format", "{{.Id}}", DEV_IMAGE])


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"YAML root must be a mapping: {rel(path)}")
    return payload


def dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )


def same_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        try:
            return math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return actual == expected


def locked_base() -> dict[str, Any]:
    base = load_yaml(BASE_CONFIG)
    mismatches = {
        key: {"actual": base.get(key), "expected": expected}
        for key, expected in REQUIRED_BASE_VALUES.items()
        if not same_value(base.get(key), expected)
    }
    if mismatches:
        raise RuntimeError(f"Arm 1-prime exact-base lock mismatch: {json.dumps(mismatches, ensure_ascii=False)}")
    return base


def invariant_payload(config: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    invariant_keys = sorted(set(base) - ALLOWED_BASE_OVERRIDES)
    return {key: config.get(key) for key in invariant_keys}


def verify_exact_base(config: dict[str, Any], base: dict[str, Any]) -> tuple[str, str, int]:
    base_payload = invariant_payload(base, base)
    derived_payload = invariant_payload(config, base)
    base_fingerprint = sha256_json(base_payload)
    derived_fingerprint = sha256_json(derived_payload)
    if base_fingerprint != derived_fingerprint:
        changed = [key for key in base_payload if base_payload[key] != derived_payload[key]]
        raise RuntimeError(f"non-S3 Arm 1-prime base keys changed: {changed}")
    return base_fingerprint, derived_fingerprint, len(base_payload)


def validate_s3_config(config: dict[str, Any], run_name: str) -> None:
    """Enforce the preregistered S3 config shape before any launch command."""

    attempt = int(config.get("s3_gate_attempt", -1))
    if run_name == GATE_RUN:
        expected_attempt = 1
        expected_max_iter = GATE_MAX_ITER
        expected_generic_every = GATE_GENERIC_AUDIT_EVERY
        expected_semantic_every = GATE_SEMANTIC_AUDIT_EVERY
    elif run_name.startswith(f"{GATE_RUN}_"):
        expected_attempt = 2
        expected_max_iter = GATE_MAX_ITER
        expected_generic_every = GATE_GENERIC_AUDIT_EVERY
        expected_semantic_every = GATE_SEMANTIC_AUDIT_EVERY
    elif run_name in FULL_RUNS:
        expected_attempt = 0
        expected_max_iter = FULL_MAX_ITER
        expected_generic_every = FULL_GENERIC_AUDIT_EVERY
        expected_semantic_every = FULL_SEMANTIC_AUDIT_EVERY
    else:
        raise RuntimeError(f"run is outside the locked S3-A cells: {run_name}")
    if attempt != expected_attempt:
        raise RuntimeError(
            f"{run_name}: s3_gate_attempt={attempt}, expected {expected_attempt}"
        )

    semdepth_scale = float(config.get("s3_semdepth_scale", float("nan")))
    nb_scale = float(config.get("s3_nb_scale", float("nan")))
    if semdepth_scale not in {0.5, 1.0} or nb_scale not in {0.5, 1.0}:
        raise RuntimeError(f"{run_name}: S3 scales must be exactly 0.5 or 1.0")
    if attempt in {0, 1} and (semdepth_scale != 1.0 or nb_scale != 1.0):
        raise RuntimeError(f"{run_name}: initial/full cells must keep both S3 scales at 1.0")
    if attempt == 2 and semdepth_scale == 1.0 and nb_scale == 1.0:
        raise RuntimeError(f"{run_name}: second gate attempt must halve an offending loss")

    expected_semantic = dict(SEMANTIC_DELTA)
    expected_semantic["w_semdepth_smooth"] *= semdepth_scale
    expected_semantic["w_semdepth_plane"] *= semdepth_scale
    expected_semantic["w_boundary_normal"] *= nb_scale
    expected_semantic["semantic_pi_event_until_positive"] = attempt > 0
    expected = {
        **expected_semantic,
        "max_iter": expected_max_iter,
        "loss_grad_audit_every": expected_generic_every,
        "semantic_geometry_audit_every": expected_semantic_every,
        "semantic_region_cache": ws(SEMANTIC_REGION_CACHE),
        "out_dir": ws(CKPT_ROOT / run_name),
        "densify_audit_buildings": DENSIFY_AUDIT_BUILDINGS,
        "s3_claim_scope": "oracle-label mechanism upper bound; not the FM/paper claim",
        "s3_no_monocular_depth": True,
    }
    mismatches = {
        key: {"actual": config.get(key), "expected": value}
        for key, value in expected.items()
        if not same_value(config.get(key), value)
    }
    if mismatches:
        raise RuntimeError(
            f"{run_name}: locked S3 config mismatch: "
            f"{json.dumps(mismatches, ensure_ascii=False, sort_keys=True)}"
        )


def expected_cache_stems() -> list[str]:
    image_dir = DATA_ROOT / "images"
    images = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(images) != 428:
        raise RuntimeError(f"locked C001 view count is 428, found {len(images)} in {rel(image_dir)}")
    return [path.stem for path in images]


def cache_status() -> dict[str, Any]:
    expected = expected_cache_stems()
    directory_exists = SEMANTIC_REGION_CACHE.is_dir()
    present = {path.stem for path in SEMANTIC_REGION_CACHE.glob("*.npz")} if directory_exists else set()
    missing = [stem for stem in expected if stem not in present]
    extra = sorted(present - set(expected))
    return {
        "path": rel(SEMANTIC_REGION_CACHE),
        "container_path": ws(SEMANTIC_REGION_CACHE),
        "directory_exists": directory_exists,
        "expected_files": len(expected),
        "present_expected_files": len(expected) - len(missing),
        "missing_files": len(missing),
        "missing_preview": [f"{stem}.npz" for stem in missing[:10]],
        "extra_files": len(extra),
        "extra_preview": [f"{stem}.npz" for stem in extra[:10]],
        "ready": directory_exists and not missing and not extra,
    }


def loader_cache_preflight(limit: int | None = None) -> dict[str, Any]:
    """Load cache files through the training loader and enforce its metadata contract."""

    from src.stage2.loss.semantic_guided import SemanticRegionCache

    status = cache_status()
    expected = expected_cache_stems()
    present = [stem for stem in expected if (SEMANTIC_REGION_CACHE / f"{stem}.npz").exists()]
    if limit is None:
        if not status["ready"]:
            raise RuntimeError(
                f"428-view loader preflight requires a complete cache; status={status}"
            )
        selected = expected
    else:
        if limit <= 0:
            raise RuntimeError("loader preflight --limit must be positive")
        if len(present) < limit:
            raise RuntimeError(f"loader preflight requested {limit} files, only {len(present)} exist")
        selected = present[:limit]

    cache = SemanticRegionCache(SEMANTIC_REGION_CACHE)
    required_top = {
        "regions",
        "source_component_min_pixels",
        "connectivity",
        "cutline_half_width_px",
        "raycast_assignment_check",
    }
    required_region = {
        "building_id",
        "source_component_id",
        "source_component_pixel_count",
        "pre_split_overlap_count",
    }
    required_raycast_scopes = {
        "primary_actual_label_source",
        "secondary_official_v2",
    }
    required_raycast_fields = {
        "comparable_true_roof_pixels",
        "misassigned_building_pixels",
        "misassignment_rate",
    }
    region_total = 0
    for stem in selected:
        frame = cache._load_cpu(stem)  # task-scoped preflight of the production loader.
        metadata = frame.metadata
        missing_top = sorted(required_top - set(metadata))
        if missing_top:
            raise RuntimeError(f"{stem}.npz metadata missing top-level keys: {missing_top}")
        if int(metadata["source_component_min_pixels"]) != 256:
            raise RuntimeError(f"{stem}.npz source_component_min_pixels is not 256")
        if int(metadata["connectivity"]) != 8:
            raise RuntimeError(f"{stem}.npz connectivity is not 8")
        if int(metadata["cutline_half_width_px"]) != 7:
            raise RuntimeError(f"{stem}.npz cutline_half_width_px is not 7")
        regions = metadata["regions"]
        if not isinstance(regions, dict):
            raise RuntimeError(f"{stem}.npz metadata regions must be a mapping")
        positive_ids = {
            int(value)
            for value in frame.region_ids.unique().tolist()
            if int(value) > 0
        }
        mapped_ids = {int(value) for value in regions}
        if positive_ids != mapped_ids:
            raise RuntimeError(
                f"{stem}.npz region id mapping mismatch: raster={sorted(positive_ids)} metadata={sorted(mapped_ids)}"
            )
        for region_id, region in regions.items():
            if not isinstance(region, dict):
                raise RuntimeError(f"{stem}.npz region {region_id} metadata must be a mapping")
            missing_region = sorted(required_region - set(region))
            if missing_region:
                raise RuntimeError(
                    f"{stem}.npz region {region_id} metadata missing keys: {missing_region}"
                )
        raycast = metadata["raycast_assignment_check"]
        if not isinstance(raycast, dict):
            raise RuntimeError(f"{stem}.npz raycast_assignment_check must be a mapping")
        missing_scopes = sorted(required_raycast_scopes - set(raycast))
        if missing_scopes:
            raise RuntimeError(
                f"{stem}.npz raycast_assignment_check missing canonical scopes: {missing_scopes}"
            )
        for scope_name in sorted(required_raycast_scopes):
            scope = raycast[scope_name]
            if not isinstance(scope, dict):
                raise RuntimeError(
                    f"{stem}.npz raycast_assignment_check.{scope_name} must be a mapping"
                )
            missing_fields = sorted(required_raycast_fields - set(scope))
            if missing_fields:
                raise RuntimeError(
                    f"{stem}.npz raycast_assignment_check.{scope_name} missing canonical "
                    f"fields: {missing_fields}"
                )
            numerator = finite_number(scope["misassigned_building_pixels"])
            denominator = finite_number(scope["comparable_true_roof_pixels"])
            if (
                numerator is None
                or denominator is None
                or numerator < 0
                or denominator < 0
                or numerator > denominator
            ):
                raise RuntimeError(
                    f"{stem}.npz invalid raycast assignment audit values for {scope_name}"
                )
            rate = finite_number(scope["misassignment_rate"])
            if denominator == 0:
                if numerator != 0 or scope["misassignment_rate"] is not None:
                    raise RuntimeError(
                        f"{stem}.npz zero-denominator raycast assignment values are "
                        f"inconsistent for {scope_name}"
                    )
            elif rate is None or not 0.0 <= rate <= 1.0 or not math.isclose(
                rate,
                numerator / denominator,
                rel_tol=1e-9,
                abs_tol=1e-12,
            ):
                raise RuntimeError(
                    f"{stem}.npz inconsistent raycast assignment rate for {scope_name}: "
                    f"rate={rate}, numerator={numerator}, denominator={denominator}"
                )
        region_total += len(regions)
        # The production loader is deliberately lazy and memoizes frames for
        # training.  A 428-view validation should not retain the entire cache
        # (~multi-GiB CPU tensors) merely to prove the contract once.
        cache._cpu_cache.pop(stem, None)
    return {
        "cache": status,
        "loader": "src.stage2.loss.semantic_guided.SemanticRegionCache",
        "validated_files": len(selected),
        "validated_regions": region_total,
        "metadata_contract": {
            "top_level": sorted(required_top),
            "per_region": sorted(required_region),
            "raycast_assignment_check_scopes": sorted(required_raycast_scopes),
            "raycast_assignment_check_fields_per_scope": sorted(required_raycast_fields),
        },
        "status": "pass",
    }


def run_name_config_path(run_name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_name):
        raise RuntimeError(f"unsafe run name: {run_name!r}")
    return CONFIG_DIR / f"{run_name}.yaml"


def make_config(
    *,
    base: dict[str, Any],
    run_name: str,
    max_iter: int,
    generic_audit_every: int,
    semantic_audit_every: int,
    semdepth_scale: float,
    nb_scale: float,
    gate_attempt: int,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    config = dict(base)
    config.update(SEMANTIC_DELTA)
    config["w_semdepth_smooth"] = SEMANTIC_DELTA["w_semdepth_smooth"] * semdepth_scale
    config["w_semdepth_plane"] = SEMANTIC_DELTA["w_semdepth_plane"] * semdepth_scale
    config["w_boundary_normal"] = SEMANTIC_DELTA["w_boundary_normal"] * nb_scale
    config["max_iter"] = int(max_iter)
    config["loss_grad_audit_every"] = int(generic_audit_every)
    config["semantic_geometry_audit_every"] = int(semantic_audit_every)
    # Gate-only audit routing: every P-I target keeps emitting event rows until
    # a nonzero rendered-depth gradient is actually observed.  Full runs keep
    # the locked 5k periodic audit and do not pay this event-audit overhead.
    config["semantic_pi_event_until_positive"] = bool(gate_attempt > 0)
    config["semantic_region_cache"] = ws(SEMANTIC_REGION_CACHE)
    config["out_dir"] = ws(CKPT_ROOT / run_name)
    config["densify_audit_buildings"] = list(DENSIFY_AUDIT_BUILDINGS)
    config["s3_gate_attempt"] = int(gate_attempt)
    config["s3_semdepth_scale"] = float(semdepth_scale)
    config["s3_nb_scale"] = float(nb_scale)
    config["s3_claim_scope"] = "oracle-label mechanism upper bound; not the FM/paper claim"
    config["s3_no_monocular_depth"] = True
    if float(config.get("w_mono_depth", 0.0) or 0.0) != 0.0:
        raise RuntimeError("S3-A config would enable monocular depth")
    validate_s3_config(config, run_name)
    base_fp, derived_fp, invariant_count = verify_exact_base(config, base)
    path = run_name_config_path(run_name)
    dump_yaml(path, config)
    metadata = {
        "base_invariant_fingerprint": base_fp,
        "derived_invariant_fingerprint": derived_fp,
        "base_invariant_key_count": invariant_count,
    }
    return path, config, metadata


def config_inventory_row(
    *,
    phase: str,
    replicate: str,
    run_name: str,
    path: Path,
    config: dict[str, Any],
    metadata: dict[str, Any],
    cache: dict[str, Any],
) -> dict[str, Any]:
    active_updates = max(0, int(config["max_iter"]) - int(config["semantic_geometry_warmup"]))
    return {
        "record_type": "training_config",
        "phase": phase,
        "replicate": replicate,
        "run_name": run_name,
        "config": rel(path),
        "config_sha256": sha256_file(path),
        "base_config": rel(BASE_CONFIG),
        "base_config_sha256": sha256_file(BASE_CONFIG),
        "base_invariant_key_count": metadata["base_invariant_key_count"],
        "base_invariant_fingerprint": metadata["base_invariant_fingerprint"],
        "derived_invariant_fingerprint": metadata["derived_invariant_fingerprint"],
        "invariant_match": str(
            metadata["base_invariant_fingerprint"] == metadata["derived_invariant_fingerprint"]
        ).lower(),
        "seed": config["seed"],
        "max_iter": config["max_iter"],
        "semantic_active_start": config["semantic_geometry_warmup"],
        "semantic_active_end": int(config["max_iter"]) - 1,
        "semantic_active_updates": active_updates,
        "w_semdepth_smooth": config["w_semdepth_smooth"],
        "w_semdepth_plane": config["w_semdepth_plane"],
        "w_semdepth_total": float(config["w_semdepth_smooth"]) + float(config["w_semdepth_plane"]),
        "w_boundary_normal": config["w_boundary_normal"],
        "semdepth_scale": config["s3_semdepth_scale"],
        "nb_scale": config["s3_nb_scale"],
        "gate_attempt": config["s3_gate_attempt"],
        "loss_grad_audit_every": config["loss_grad_audit_every"],
        "semantic_geometry_audit_every": config["semantic_geometry_audit_every"],
        "semantic_pi_event_until_positive": str(
            config["semantic_pi_event_until_positive"]
        ).lower(),
        "semantic_delta_keys": ";".join(SEMANTIC_DELTA_KEYS),
        "gate_control_keys": ";".join(GATE_CONTROL_KEYS),
        "audit_control_keys": ";".join(AUDIT_CONTROL_KEYS),
        "recording_only_keys": ";".join(RECORDING_ONLY_KEYS),
        "densify_audit_buildings": ";".join(config["densify_audit_buildings"]),
        "densify_audit_added_buildings": ";".join(DENSIFY_AUDIT_ADDED_BUILDINGS),
        "out_dir": config["out_dir"],
        "semantic_region_cache": config["semantic_region_cache"],
        "cache_expected_files": cache["expected_files"],
        "cache_present_files": cache["present_expected_files"],
        "cache_ready_at_generation": str(cache["ready"]).lower(),
        "claim_scope": config["s3_claim_scope"],
        "denominator_contract": "primary effective components include combined semdepth and boundary_normal once; smooth/plane audit_only",
    }


def update_inventory(rows: list[dict[str, Any]], replace_run_names: set[str]) -> None:
    existing = read_csv(CSV_INVENTORY)
    # Config regeneration may happen for the one allowed half-weight re-gate.
    # Replace only config rows; downstream checkpoint/readout/score inventory
    # rows sharing the run name are immutable evidence and must survive.
    preserved = [
        row
        for row in existing
        if not (
            row.get("record_type") == "training_config"
            and row.get("run_name", "") in replace_run_names
        )
    ]
    write_csv(CSV_INVENTORY, preserved + rows)


def manifest_payload() -> dict[str, Any]:
    config_rows = [row for row in read_csv(CSV_INVENTORY) if row.get("record_type") == "training_config"]
    return {
        "run_id": RUN_ID,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": capture(["git", "rev-parse", "HEAD"]),
        "git_branch": capture(["git", "branch", "--show-current"]),
        "training_started_by_generate_configs": False,
        "orchestrator": rel(SCRIPT_PATH),
        "orchestrator_sha256": sha256_file(SCRIPT_PATH),
        "base_config": rel(BASE_CONFIG),
        "base_config_sha256": sha256_file(BASE_CONFIG),
        "claim_scope": "S3-A oracle/clean-label mechanism upper bound; S3-B FM claim excluded",
        "no_monocular_depth": True,
        "semantic_delta_keys": list(SEMANTIC_DELTA_KEYS),
        "gate_control_keys": list(GATE_CONTROL_KEYS),
        "audit_control_keys": list(AUDIT_CONTROL_KEYS),
        "recording_only_keys": list(RECORDING_ONLY_KEYS),
        "densify_audit_buildings": DENSIFY_AUDIT_BUILDINGS,
        "densify_audit_added_buildings": DENSIFY_AUDIT_ADDED_BUILDINGS,
        "gate": {
            "active_steps_inclusive": [ACTIVE_START, GATE_MAX_ITER - 1],
            "active_updates": GATE_MAX_ITER - ACTIVE_START,
            "generic_grad_audit_every": GATE_GENERIC_AUDIT_EVERY,
            "semantic_pi_audit_every": GATE_SEMANTIC_AUDIT_EVERY,
            "semantic_pi_event_until_positive": True,
            "grad_share_max": GRAD_SHARE_MAX,
            "half_weight_once": True,
        },
        "full": {
            "max_iter": FULL_MAX_ITER,
            "generic_grad_audit_every": FULL_GENERIC_AUDIT_EVERY,
            "semantic_geometry_audit_every": FULL_SEMANTIC_AUDIT_EVERY,
            "semantic_pi_event_until_positive": False,
            "replicates": 2,
            "seed_each": 2001,
        },
        "cache_status": cache_status(),
        "configs": config_rows,
        "outputs": {
            "inventory": rel(CSV_INVENTORY),
            "gate_audit": rel(CSV_GATE_AUDIT),
            "versions": rel(VERSIONS),
        },
    }


def write_manifest_and_versions() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    payload = manifest_payload()
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    docker_id = docker_image_id()
    lines = [
        f"run_id: {RUN_ID}",
        f"updated_utc: {payload['updated_utc']}",
        f"git_head: {payload['git_head']}",
        f"git_branch: {payload['git_branch']}",
        f"docker_image: {DEV_IMAGE}",
        f"docker_image_id: {docker_id}",
        "crs: EPSG:25832",
        "training_started: no (config/orchestrator generation only)",
        "claim_scope: S3-A oracle-label mechanism upper bound; not S3-B FM/paper claim",
        f"base_config: {rel(BASE_CONFIG)}",
        f"base_config_sha256: {sha256_file(BASE_CONFIG)}",
        f"orchestrator_sha256: {sha256_file(SCRIPT_PATH)}",
        f"train_py_sha256: {sha256_file(REPO / 'src/stage2/train.py')}",
        f"semantic_loss_py_sha256: {sha256_file(REPO / 'src/stage2/loss/semantic_guided.py') if (REPO / 'src/stage2/loss/semantic_guided.py').exists() else 'missing'}",
        f"inventory: {rel(CSV_INVENTORY)}",
        f"manifest: {rel(MANIFEST)}",
        f"cache_ready: {str(payload['cache_status']['ready']).lower()}",
        f"cache_present_expected: {payload['cache_status']['present_expected_files']}/{payload['cache_status']['expected_files']}",
    ]
    VERSIONS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_configs(_args: argparse.Namespace) -> None:
    base = locked_base()
    cache = cache_status()
    specs = [
        ("gate", "gate", GATE_RUN, GATE_MAX_ITER, GATE_GENERIC_AUDIT_EVERY, GATE_SEMANTIC_AUDIT_EVERY, 1),
        ("full", "r1", FULL_RUNS[0], FULL_MAX_ITER, FULL_GENERIC_AUDIT_EVERY, FULL_SEMANTIC_AUDIT_EVERY, 0),
        ("full", "r2", FULL_RUNS[1], FULL_MAX_ITER, FULL_GENERIC_AUDIT_EVERY, FULL_SEMANTIC_AUDIT_EVERY, 0),
    ]
    rows: list[dict[str, Any]] = []
    for phase, replicate, run_name, max_iter, generic_every, semantic_every, attempt in specs:
        path, config, metadata = make_config(
            base=base,
            run_name=run_name,
            max_iter=max_iter,
            generic_audit_every=generic_every,
            semantic_audit_every=semantic_every,
            semdepth_scale=1.0,
            nb_scale=1.0,
            gate_attempt=attempt,
        )
        rows.append(
            config_inventory_row(
                phase=phase,
                replicate=replicate,
                run_name=run_name,
                path=path,
                config=config,
                metadata=metadata,
                cache=cache,
            )
        )
    update_inventory(rows, {row["run_name"] for row in rows})
    write_manifest_and_versions()
    print(
        json.dumps(
            {
                "configs": [row["config"] for row in rows],
                "inventory": rel(CSV_INVENTORY),
                "cache": cache_status(),
                "training_started": False,
            },
            ensure_ascii=False,
        )
    )


def generate_regate_config(args: argparse.Namespace) -> None:
    allowed = {0.5, 1.0}
    if args.semdepth_scale not in allowed or args.nb_scale not in allowed:
        raise RuntimeError("re-gate scales must each be exactly 0.5 or 1.0")
    if args.semdepth_scale == 1.0 and args.nb_scale == 1.0:
        raise RuntimeError("re-gate must halve at least one offending loss")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.tag):
        raise RuntimeError("--tag must match [a-z0-9][a-z0-9_-]*")
    run_name = f"{GATE_RUN}_{args.tag}"
    base = locked_base()
    path, config, metadata = make_config(
        base=base,
        run_name=run_name,
        max_iter=GATE_MAX_ITER,
        generic_audit_every=GATE_GENERIC_AUDIT_EVERY,
        semantic_audit_every=GATE_SEMANTIC_AUDIT_EVERY,
        semdepth_scale=args.semdepth_scale,
        nb_scale=args.nb_scale,
        gate_attempt=2,
    )
    row = config_inventory_row(
        phase="gate_regate",
        replicate="gate2",
        run_name=run_name,
        path=path,
        config=config,
        metadata=metadata,
        cache=cache_status(),
    )
    update_inventory([row], {run_name})
    write_manifest_and_versions()
    print(json.dumps({"config": rel(path), "run_name": run_name, "training_started": False}, ensure_ascii=False))


def docker_base(gpu: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--gpus",
        "all",
        "-e",
        "HOME=/tmp",
        "-e",
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-e",
        "XDG_CACHE_HOME=/tmp",
        "-e",
        f"CUDA_VISIBLE_DEVICES={gpu}",
        "-e",
        f"TORCH_EXTENSIONS_DIR={ws(TORCH_EXTENSIONS)}",
        "-v",
        f"{HOST_REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
        DEV_IMAGE,
    ]


def train_command(run_name: str, gpu: str) -> tuple[Path, list[str]]:
    config = run_name_config_path(run_name)
    if not config.exists():
        raise FileNotFoundError(f"generate the config first: {rel(config)}")
    base = locked_base()
    derived = load_yaml(config)
    verify_exact_base(derived, base)
    validate_s3_config(derived, run_name)
    command = docker_base(gpu) + [
        "python",
        "-m",
        "src.stage2.train",
        "--config",
        ws(config),
    ]
    return config, command


def track_a_preconditions() -> dict[str, Any]:
    seed_rows = read_csv(CSV_SEED_INVENTORY)
    seed_data_complete = (
        len(seed_rows) == 6
        and all(row.get("qa_match_expected") == "true" for row in seed_rows)
    )
    seed_commit = committed_unchanged(CSV_SEED_INVENTORY)
    gate_rows = read_csv(CSV_GATE_AUDIT)
    gate_summaries = [row for row in gate_rows if row.get("record_type") == "gate_summary"]
    # A half-weight re-gate is attempt 2 and supersedes attempt 1 regardless of
    # CSV append order.  Within the same attempt the latest row wins.
    latest_gate = max(
        enumerate(gate_summaries),
        key=lambda item: (int(item[1].get("gate_attempt") or 0), item[0]),
        default=(-1, {}),
    )[1]
    gate_commit = committed_unchanged(CSV_GATE_AUDIT)
    gate_data_pass = latest_gate.get("gate_status") == "pass"
    seed_complete = seed_data_complete and seed_commit["committed_unchanged"]
    gate_pass = gate_data_pass and gate_commit["committed_unchanged"]
    gate_effective_status = latest_gate.get("gate_status", "missing")
    if gate_data_pass and not gate_commit["committed_unchanged"]:
        gate_effective_status = "pass_uncommitted"
    return {
        "t0_2_seed_inventory": rel(CSV_SEED_INVENTORY),
        "t0_2_rows": len(seed_rows),
        "t0_2_data_complete": seed_data_complete,
        "t0_2_commit_state": seed_commit,
        "t0_2_complete": seed_complete,
        "t0_4_gate_audit": rel(CSV_GATE_AUDIT),
        "t0_4_gate_run": latest_gate.get("run_name", ""),
        "t0_4_gate_data_status": latest_gate.get("gate_status", "missing"),
        "t0_4_gate_commit_state": gate_commit,
        "t0_4_gate_status": gate_effective_status,
        "track_a_ready": seed_complete and gate_pass,
    }


def write_launch_versions(
    run_name: str,
    gpu: str,
    config: Path,
    command: list[str],
    preflight_log: Path,
) -> Path:
    status = cache_status()
    path = RUN_DIR / "versions" / f"{run_name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"run_name: {run_name}",
        f"launch_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        f"docker_image: {DEV_IMAGE}",
        f"docker_image_id: {docker_image_id()}",
        f"host_gpu_selector: {gpu}",
        f"config: {rel(config)}",
        f"config_sha256: {sha256_file(config)}",
        f"base_config_sha256: {sha256_file(BASE_CONFIG)}",
        f"orchestrator_sha256: {sha256_file(SCRIPT_PATH)}",
        f"train_py_sha256: {sha256_file(REPO / 'src/stage2/train.py')}",
        f"semantic_loss_py_sha256: {sha256_file(REPO / 'src/stage2/loss/semantic_guided.py')}",
        f"cache_ready: {str(status['ready']).lower()}",
        f"cache_present_expected: {status['present_expected_files']}/{status['expected_files']}",
        f"cache_loader_preflight_log: {rel(preflight_log)}",
        f"cache_loader_preflight_sha256: {sha256_file(preflight_log)}",
        f"command: {shlex.join(command)}",
    ]
    with path.open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def workspace_path_to_host(value: str | Path) -> Path:
    text = str(value)
    prefix = "/workspace/JointBuildGS"
    if text == prefix:
        return REPO
    if text.startswith(f"{prefix}/"):
        return REPO / text[len(prefix) + 1 :]
    return Path(text)


def launch_artifact_state(run_name: str, config: dict[str, Any]) -> dict[str, Any]:
    out_dir = workspace_path_to_host(config["out_dir"])
    out_dir_exists = out_dir.exists()
    if out_dir_exists and out_dir.is_dir():
        out_dir_entries = sum(1 for _ in out_dir.iterdir())
        out_dir_nonempty = out_dir_entries > 0
    elif out_dir_exists:
        out_dir_entries = -1
        out_dir_nonempty = True
    else:
        out_dir_entries = 0
        out_dir_nonempty = False
    train_log = TRAIN_LOG_ROOT / f"{run_name}.log"
    launch_versions = RUN_DIR / "versions" / f"{run_name}.txt"
    collision = out_dir_nonempty or train_log.exists() or launch_versions.exists()
    return {
        "out_dir": rel(out_dir),
        "out_dir_exists": out_dir_exists,
        "out_dir_entry_count": out_dir_entries,
        "out_dir_nonempty": out_dir_nonempty,
        "train_log": rel(train_log),
        "train_log_exists": train_log.exists(),
        "launch_versions": rel(launch_versions),
        "launch_versions_exists": launch_versions.exists(),
        "collision": collision,
    }


def train_one(args: argparse.Namespace) -> None:
    config, command = train_command(args.run_name, args.gpu)
    config_payload = load_yaml(config)
    status = cache_status()
    track_a = track_a_preconditions()
    artifacts = launch_artifact_state(args.run_name, config_payload)
    committed_inputs = {
        key: committed_unchanged(path)
        for key, path in {
            "config": config,
            "orchestrator": SCRIPT_PATH,
            "base_config": BASE_CONFIG,
            "train": REPO / "src/stage2/train.py",
            "semantic_loss": REPO / "src/stage2/loss/semantic_guided.py",
        }.items()
    }
    preflight_command = docker_base(args.gpu) + [
        "python",
        ws(SCRIPT_PATH),
        "check-cache",
        "--loader-preflight",
    ]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "run_name": args.run_name,
                    "config": rel(config),
                    "config_sha256": sha256_file(config),
                    "cache": status,
                    "track_a_preconditions": track_a,
                    "committed_training_inputs": committed_inputs,
                    "launch_artifact_state": artifacts,
                    "cache_loader_preflight_command": shlex.join(preflight_command),
                    "command": shlex.join(command),
                    "training_started": False,
                },
                ensure_ascii=False,
            )
        )
        return
    dirty_inputs = [
        key for key, state in committed_inputs.items() if not state["committed_unchanged"]
    ]
    if dirty_inputs:
        raise RuntimeError(
            "training input commit gate failed; commit and keep unchanged: "
            f"{dirty_inputs}; states={committed_inputs}"
        )
    if artifacts["collision"]:
        raise RuntimeError(
            "immutable run artifact gate failed; existing nonempty out_dir/log/versions "
            f"must never be overwritten. Use a new run_name. state={artifacts}"
        )
    if not status["ready"]:
        raise RuntimeError(
            "semantic-region cache gate failed: "
            f"{status['present_expected_files']}/{status['expected_files']} expected files present; "
            f"missing preview={status['missing_preview']}"
        )
    if args.run_name in FULL_RUNS and not track_a["track_a_ready"]:
        raise RuntimeError(
            "Track A precondition gate failed: T0-2 completion and a passing T0-4 "
            f"gate summary are both required; observed={track_a}"
        )
    preflight_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    preflight_log = (
        RUN_DIR / "cache_preflight" / f"{args.run_name}_{preflight_stamp}.log"
    )
    preflight_log.parent.mkdir(parents=True, exist_ok=True)
    preflight = subprocess.run(
        preflight_command,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    with preflight_log.open("x", encoding="utf-8") as handle:
        handle.write(
            f"COMMAND={shlex.join(preflight_command)}\nRETURN_CODE={preflight.returncode}\n"
            + (preflight.stdout or "")
        )
    if preflight.stdout:
        print(preflight.stdout, end="", flush=True)
    if preflight.returncode != 0:
        raise RuntimeError(
            f"semantic-region 428-view loader preflight failed; see {rel(preflight_log)}"
        )
    artifacts_after_preflight = launch_artifact_state(args.run_name, config_payload)
    if artifacts_after_preflight["collision"]:
        raise RuntimeError(
            "immutable run artifact gate changed during cache preflight; aborting: "
            f"{artifacts_after_preflight}"
        )
    version_path = write_launch_versions(
        args.run_name,
        args.gpu,
        config,
        command,
        preflight_log,
    )
    log_path = TRAIN_LOG_ROOT / f"{args.run_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with log_path.open("x", encoding="utf-8") as log:
        log.write(
            f"START_UTC={started}\nHOST_GPU={args.gpu}\nCONFIG={rel(config)}\n"
            f"CONFIG_SHA256={sha256_file(config)}\nVERSIONS={rel(version_path)}\n"
            f"COMMAND={shlex.join(command)}\n"
        )
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return_code = int(process.wait())
        log.write(
            f"\nEND_UTC={datetime.now(timezone.utc).isoformat()}\nRETURN_CODE={return_code}\n"
        )
    print(
        json.dumps(
            {
                "run_name": args.run_name,
                "gpu": args.gpu,
                "return_code": return_code,
                "log": rel(log_path),
            },
            ensure_ascii=False,
        )
    )
    if return_code != 0:
        raise SystemExit(return_code)


def finite_number(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def percentile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def expected_audit_steps(start: int, max_iter: int, every: int) -> set[int]:
    steps = set(range(start, max_iter, every))
    steps.add(max_iter - 1)
    return steps


def parse_return_code(path: Path) -> int | None:
    if not path.exists():
        return None
    match = re.search(r"(?:^|\n)RETURN_CODE=(-?\d+)(?:\n|$)", path.read_text(encoding="utf-8", errors="replace"))
    return int(match.group(1)) if match else None


def component_rows(rows: list[dict[str, str]], component: str, start: int, end: int) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("component") == component
        and start <= int(row["step"]) <= end
    ]


def component_share_stats(rows: list[dict[str, str]]) -> dict[str, Any]:
    shares = [value for value in (finite_number(row.get("grad_norm_share")) for row in rows) if value is not None]
    return {
        "count": len(shares),
        "p50": percentile(shares, 0.50),
        "p95": percentile(shares, 0.95),
        "max": max(shares) if shares else None,
    }


def component_audit_complete(
    rows: list[dict[str, str]],
    expected_count: int,
    expected_weight: float,
) -> bool:
    if len(rows) != expected_count:
        return False
    for row in rows:
        grad_norm = finite_number(row.get("grad_norm"))
        grad_share = finite_number(row.get("grad_norm_share"))
        if (
            finite_number(row.get("raw_loss")) is None
            or finite_number(row.get("weighted_loss")) is None
            or not same_value(row.get("weight"), expected_weight)
            or grad_norm is None
            or grad_norm < 0.0
            or grad_share is None
            or not 0.0 <= grad_share <= 1.0
            or str(row.get("grad_status", "")).strip()
        ):
            return False
    return True


def validate_denominator_contract(rows: list[dict[str, str]], active_steps: set[int]) -> list[str]:
    reasons: list[str] = []
    for step in sorted(active_steps):
        part = [row for row in rows if int(row["step"]) == step]
        for component in PRIMARY_AUDIT_COMPONENTS:
            matches = [row for row in part if row.get("component") == component]
            if len(matches) != 1 or any(row.get("denominator_role", "primary") != "primary" for row in matches):
                reasons.append(f"step {step} {component} primary row count/role invalid")
        for component in DETAIL_AUDIT_COMPONENTS:
            matches = [row for row in part if row.get("component") == component]
            if len(matches) != 1 or any(row.get("denominator_role") != "audit_only" for row in matches):
                reasons.append(f"step {step} {component} audit_only row count/role invalid")
        primary = [row for row in part if row.get("denominator_role", "primary") == "primary"]
        names = [row.get("component", "") for row in primary]
        if len(names) != len(set(names)):
            reasons.append(f"step {step} duplicate primary components")
        unexpected = sorted(set(names) - PRIMARY_AUDIT_COMPONENTS)
        if unexpected:
            reasons.append(f"step {step} unexpected primary components: {unexpected}")
    return reasons


def normalize_source_rows(
    run_name: str,
    loss_path: Path,
    semantic_path: Path,
    loss_rows: list[dict[str, str]],
    semantic_rows: list[dict[str, str]],
    active_start: int,
    active_end: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source_path, record_type, rows in (
        (loss_path, "loss_component", loss_rows),
        (semantic_path, "semantic_region", semantic_rows),
    ):
        for source_row_index, row in enumerate(rows, start=2):
            step = int(row["step"])
            if not (active_start <= step <= active_end):
                continue
            output.append(
                {
                    "run_name": run_name,
                    "record_type": record_type,
                    "source_csv": rel(source_path),
                    "source_row": source_row_index,
                    "active": 1,
                    **row,
                }
            )
    return output


def gate_audit(args: argparse.Namespace) -> None:
    config_path = run_name_config_path(args.run_name)
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    config = load_yaml(config_path)
    base = locked_base()
    verify_exact_base(config, base)
    validate_s3_config(config, args.run_name)
    max_iter = int(config["max_iter"])
    active_start = int(config["semantic_geometry_warmup"])
    active_end = max_iter - 1
    if max_iter != GATE_MAX_ITER or active_start != ACTIVE_START:
        raise RuntimeError(
            f"gate config must have max_iter={GATE_MAX_ITER}, warmup={ACTIVE_START}; "
            f"got {max_iter}/{active_start}"
        )
    out_dir = Path(str(config["out_dir"]).replace("/workspace/JointBuildGS", str(REPO), 1))
    loss_path = Path(args.loss_csv) if args.loss_csv else out_dir / "audit/loss_grad_norms.csv"
    semantic_path = Path(args.semantic_csv) if args.semantic_csv else out_dir / "audit/semantic_geometry.csv"
    train_log = Path(args.train_log) if args.train_log else TRAIN_LOG_ROOT / f"{args.run_name}.log"
    output_path = Path(args.output) if args.output else CSV_GATE_AUDIT
    for path in (loss_path, semantic_path):
        if not path.exists():
            raise FileNotFoundError(path)
    loss_rows = read_csv(loss_path)
    semantic_rows = read_csv(semantic_path)
    if not loss_rows or not semantic_rows:
        raise RuntimeError("gate audit inputs must both contain data rows")
    for row in loss_rows + semantic_rows:
        try:
            int(row["step"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid audit step row: {row}") from exc

    generic_every = int(config["loss_grad_audit_every"])
    semantic_every = int(config["semantic_geometry_audit_every"])
    expected_generic = expected_audit_steps(active_start, max_iter, generic_every)
    expected_semantic = expected_audit_steps(active_start, max_iter, semantic_every)
    observed_generic = {int(row["step"]) for row in loss_rows if active_start <= int(row["step"]) <= active_end}
    observed_semantic = {int(row["step"]) for row in semantic_rows if active_start <= int(row["step"]) <= active_end}

    reasons: list[str] = []
    missing_generic = sorted(expected_generic - observed_generic)
    missing_semantic = sorted(expected_semantic - observed_semantic)
    if missing_generic:
        reasons.append(f"missing generic audit steps: {missing_generic[:10]}")
    if missing_semantic:
        reasons.append(f"missing semantic audit steps: {missing_semantic[:10]}")
    reasons.extend(validate_denominator_contract(loss_rows, expected_generic & observed_generic))

    active_loss_rows = [row for row in loss_rows if active_start <= int(row["step"]) <= active_end]
    total_values = [finite_number(row.get("total_loss")) for row in active_loss_rows]
    total_values_finite = bool(total_values) and all(value is not None for value in total_values)
    nonfinite_path = out_dir / "audit/nonfinite_loss.jsonl"
    nonfinite_records = 0
    if nonfinite_path.exists():
        nonfinite_records = sum(1 for line in nonfinite_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
    return_code = parse_return_code(train_log)
    total_finite_pass = total_values_finite and nonfinite_records == 0 and return_code == 0
    if not total_finite_pass:
        reasons.append(
            "total-loss completion check failed "
            f"(sampled_finite={total_values_finite}, nonfinite_records={nonfinite_records}, return_code={return_code})"
        )

    semdepth_rows = component_rows(loss_rows, "semdepth", active_start, active_end)
    boundary_rows = component_rows(loss_rows, "boundary_normal", active_start, active_end)
    smooth_rows = component_rows(loss_rows, "semdepth_smooth", active_start, active_end)
    plane_rows = component_rows(loss_rows, "semdepth_plane", active_start, active_end)
    stats = {
        "semdepth": component_share_stats(semdepth_rows),
        "boundary_normal": component_share_stats(boundary_rows),
        "semdepth_smooth": component_share_stats(smooth_rows),
        "semdepth_plane": component_share_stats(plane_rows),
    }
    expected_component_rows = len(expected_generic)
    semdepth_rows_complete = component_audit_complete(
        semdepth_rows, expected_component_rows, 1.0
    )
    boundary_rows_complete = component_audit_complete(
        boundary_rows, expected_component_rows, float(config["w_boundary_normal"])
    )
    smooth_rows_complete = component_audit_complete(
        smooth_rows,
        expected_component_rows,
        float(config["w_semdepth_smooth"]),
    )
    plane_rows_complete = component_audit_complete(
        plane_rows,
        expected_component_rows,
        float(config["w_semdepth_plane"]),
    )
    semdepth_pass = (
        semdepth_rows_complete
        and stats["semdepth"]["max"] is not None
        and stats["semdepth"]["max"] <= GRAD_SHARE_MAX
    )
    boundary_pass = (
        boundary_rows_complete
        and stats["boundary_normal"]["max"] is not None
        and stats["boundary_normal"]["max"] <= GRAD_SHARE_MAX
    )
    detail_pass = smooth_rows_complete and plane_rows_complete
    if not semdepth_rows_complete:
        reasons.append("semdepth audit rows are missing, non-finite, invalid, or report grad_status")
    elif not semdepth_pass:
        reasons.append(
            f"semdepth max grad share {stats['semdepth']['max']} exceeds threshold {GRAD_SHARE_MAX}"
        )
    if not boundary_rows_complete:
        reasons.append(
            "boundary_normal audit rows are missing, non-finite, invalid, or report grad_status"
        )
    elif not boundary_pass:
        reasons.append(
            f"boundary_normal max grad share {stats['boundary_normal']['max']} exceeds threshold {GRAD_SHARE_MAX}"
        )
    if not detail_pass:
        reasons.append("smooth/plane separated audit rows are incomplete or invalid")

    pi_rows: list[dict[str, Any]] = []
    pi_all_pass = True
    active_semantic_rows = [
        row for row in semantic_rows if active_start <= int(row["step"]) <= active_end
    ]
    for building_id in PI_TARGETS:
        part = [row for row in active_semantic_rows if row.get("building_id", "") == building_id]
        positive = [
            row
            for row in part
            if (finite_number(row.get("semdepth_depth_grad_norm")) or 0.0) > 0.0
            and (finite_number(row.get("semdepth_depth_grad_norm_share")) or 0.0) > 0.0
            and (finite_number(row.get("semdepth_depth_grad_nonzero_pixel_count")) or 0.0) > 0.0
        ]
        grad_norms = [
            value
            for value in (finite_number(row.get("semdepth_depth_grad_norm")) for row in part)
            if value is not None
        ]
        nonzero_pixels = [
            value
            for value in (
                finite_number(row.get("semdepth_depth_grad_nonzero_pixel_count")) for row in part
            )
            if value is not None
        ]
        grad_shares = [
            value
            for value in (
                finite_number(row.get("semdepth_depth_grad_norm_share")) for row in part
            )
            if value is not None
        ]
        pi_pass = bool(positive)
        pi_all_pass = pi_all_pass and pi_pass
        if not pi_pass:
            reasons.append(f"P-I nonzero rendered-depth gradient not observed for {building_id}")
        pi_rows.append(
            {
                "run_name": args.run_name,
                "record_type": "pi_summary",
                "building_id": building_id,
                "active": 1,
                "active_start": active_start,
                "active_end": active_end,
                "pi_observed_region_rows": len(part),
                "pi_positive_region_rows": len(positive),
                "pi_grad_norm_max": max(grad_norms) if grad_norms else "",
                "pi_grad_norm_share_max": max(grad_shares) if grad_shares else "",
                "pi_nonzero_pixel_count_max": max(nonzero_pixels) if nonzero_pixels else "",
                "pi_status": "pass" if pi_pass else "fail",
            }
        )

    gate_pass = (
        not missing_generic
        and not missing_semantic
        and not validate_denominator_contract(loss_rows, expected_generic & observed_generic)
        and total_finite_pass
        and semdepth_pass
        and boundary_pass
        and detail_pass
        and pi_all_pass
    )
    attempt = int(config.get("s3_gate_attempt", 1))
    suggested_semdepth_scale = (
        0.5 if attempt == 1 and not semdepth_pass and stats["semdepth"]["max"] is not None else 1.0
    )
    suggested_nb_scale = (
        0.5
        if attempt == 1 and not boundary_pass and stats["boundary_normal"]["max"] is not None
        else 1.0
    )
    regate_command = ""
    if attempt == 1 and (suggested_semdepth_scale == 0.5 or suggested_nb_scale == 0.5):
        regate_command = (
            "python phases/p2-gsjso/scripts/e5_c001_s3_semantic_guided.py "
            "generate-regate-config --tag half_once "
            f"--semdepth-scale {suggested_semdepth_scale:g} --nb-scale {suggested_nb_scale:g}"
        )

    normalized = normalize_source_rows(
        args.run_name,
        loss_path,
        semantic_path,
        loss_rows,
        semantic_rows,
        active_start,
        active_end,
    )
    normalized.extend(pi_rows)
    normalized.append(
        {
            "run_name": args.run_name,
            "record_type": "gate_summary",
            "active": 1,
            "active_start": active_start,
            "active_end": active_end,
            "active_update_count": max_iter - active_start,
            "generic_audit_every": generic_every,
            "generic_expected_step_count": len(expected_generic),
            "generic_observed_step_count": len(observed_generic),
            "semantic_audit_every": semantic_every,
            "semantic_expected_step_count": len(expected_semantic),
            "semantic_observed_step_count": len(observed_semantic),
            "total_loss_finite_status": "pass" if total_finite_pass else "fail",
            "train_return_code": "" if return_code is None else return_code,
            "nonfinite_loss_records": nonfinite_records,
            "semdepth_grad_share_p50": stats["semdepth"]["p50"],
            "semdepth_grad_share_p95": stats["semdepth"]["p95"],
            "semdepth_grad_share_max": stats["semdepth"]["max"],
            "semdepth_grad_share_threshold": GRAD_SHARE_MAX,
            "semdepth_audit_rows_complete": str(semdepth_rows_complete).lower(),
            "semdepth_status": "pass" if semdepth_pass else "fail",
            "boundary_normal_grad_share_p50": stats["boundary_normal"]["p50"],
            "boundary_normal_grad_share_p95": stats["boundary_normal"]["p95"],
            "boundary_normal_grad_share_max": stats["boundary_normal"]["max"],
            "boundary_normal_grad_share_threshold": GRAD_SHARE_MAX,
            "boundary_normal_audit_rows_complete": str(boundary_rows_complete).lower(),
            "boundary_normal_status": "pass" if boundary_pass else "fail",
            "smooth_grad_share_p50_audit_only": stats["semdepth_smooth"]["p50"],
            "smooth_grad_share_max_audit_only": stats["semdepth_smooth"]["max"],
            "smooth_audit_rows_complete": str(smooth_rows_complete).lower(),
            "plane_grad_share_p50_audit_only": stats["semdepth_plane"]["p50"],
            "plane_grad_share_max_audit_only": stats["semdepth_plane"]["max"],
            "plane_audit_rows_complete": str(plane_rows_complete).lower(),
            "smooth_plane_detail_status": "pass" if detail_pass else "fail",
            "pi_all_targets_status": "pass" if pi_all_pass else "fail",
            "gate_status": "pass" if gate_pass else "fail",
            "gate_reasons": "; ".join(dict.fromkeys(reasons)),
            "gate_attempt": attempt,
            "suggested_semdepth_scale": suggested_semdepth_scale,
            "suggested_nb_scale": suggested_nb_scale,
            "regate_config_command_not_executed": regate_command,
            "config": rel(config_path),
            "config_sha256": sha256_file(config_path),
            "denominator_contract": "combined semdepth and boundary_normal are primary once; smooth/plane are audit_only",
            "judgment_scope": "mechanical preregistered gate fields only; human verdict excluded",
        }
    )
    # Preserve the first-attempt material when a differently named half-weight
    # re-gate is normalised; rerunning the same run replaces only that run.
    existing_output = read_csv(output_path)
    preserved_output = [row for row in existing_output if row.get("run_name") != args.run_name]
    write_csv(output_path, preserved_output + normalized)
    summary = normalized[-1]
    print(
        json.dumps(
            {
                "output": rel(output_path) if output_path.is_relative_to(REPO) else str(output_path),
                "rows": len(normalized),
                "gate_status": summary["gate_status"],
                "semdepth_max": summary["semdepth_grad_share_max"],
                "boundary_normal_max": summary["boundary_normal_grad_share_max"],
                "pi_all_targets_status": summary["pi_all_targets_status"],
                "regate_config_command_not_executed": regate_command,
            },
            ensure_ascii=False,
        )
    )


def check_cache(args: argparse.Namespace) -> None:
    status = cache_status()
    if args.loader_preflight:
        result = loader_cache_preflight(args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not status["ready"]:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate-configs")

    regate = subparsers.add_parser("generate-regate-config")
    regate.add_argument("--tag", required=True)
    regate.add_argument("--semdepth-scale", type=float, required=True)
    regate.add_argument("--nb-scale", type=float, required=True)

    train = subparsers.add_parser("train-one")
    train.add_argument("--run-name", required=True)
    train.add_argument("--gpu", default="0")
    train.add_argument("--dry-run", action="store_true")

    audit = subparsers.add_parser("gate-audit")
    audit.add_argument("--run-name", default=GATE_RUN)
    audit.add_argument("--loss-csv")
    audit.add_argument("--semantic-csv")
    audit.add_argument("--train-log")
    audit.add_argument("--output")

    cache = subparsers.add_parser("check-cache")
    cache.add_argument("--loader-preflight", action="store_true")
    cache.add_argument("--limit", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "generate-configs":
        generate_configs(args)
    elif args.command == "generate-regate-config":
        generate_regate_config(args)
    elif args.command == "train-one":
        train_one(args)
    elif args.command == "gate-audit":
        gate_audit(args)
    elif args.command == "check-cache":
        check_cache(args)
    else:  # pragma: no cover - argparse makes this unreachable.
        raise RuntimeError(args.command)


if __name__ == "__main__":
    main()
