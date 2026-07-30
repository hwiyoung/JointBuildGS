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
* all training remains blocked until every C001 view has an oracle-ID-split
  semantic-region cache file.

``gate-audit`` merges ``audit/loss_grad_norms.csv``,
``audit/semantic_geometry.csv``, and the post-probe per-view
``audit/pjpl_depth_anchor_views.csv`` into the locked docs CSV.  Its pass/fail
fields are mechanical evaluations of the preregistered thresholds, not a
research verdict.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import io
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO = Path(__file__).resolve().parents[2]
HOST_REPO = Path(os.environ.get("S3_HOST_REPO", str(REPO))).resolve()
SCRIPT_PATH = Path(__file__).resolve()
DEV_IMAGE = "jointbuildgs:dev"
RUN_ID = "20260713_e5_c001_s3_semantic_guided"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID

BASE_CONFIG = REPO / "configs/e5_c001/e5_s2p_interaction/gs_e5_C001_s2p_arm1p_dense_r1.yaml"
CONFIG_DIR = REPO / "configs/e5_c001/e5_s3_semantic_guided"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s3_semantic_guided/C001"
CKPT_ROOT = RESULTS_ROOT / "runs"
TRAIN_LOG_ROOT = RESULTS_ROOT / "train_logs"
TORCH_EXTENSIONS = RESULTS_ROOT / "torch_extensions"
# Produced by the T0 semantic-region/reference-QA harness.  Training outputs
# stay under e5_s3_semantic_guided, while this fixed input cache keeps its own
# T0 provenance root.
SEMANTIC_REGION_CACHE = REPO / "results/tum_transfer/e5_s3/C001/semantic_regions"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"

CSV_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_inventory.csv"
CSV_GATE_AUDIT = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_loss_gate_audit.csv"
CSV_SEED_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_seed_inventory.csv"
CACHE_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_semantic_region_inventory.csv"
CACHE_MANIFEST = (
    REPO
    / "phases/p2-gsjso/runs/e5_c001/20260713_e5_c001_s3_track0/semantic_region_manifest.json"
)
CACHE_PRODUCER = REPO / "scripts/e5_c001/e5_c001_s3_semantic_regions.py"
MANIFEST = RUN_DIR / "config_gate_manifest.json"
VERSIONS = RUN_DIR / "versions.txt"

GATE_RUN = "gs_e5_C001_s3a_semantic_guided_gate"
FULL_RUNS = [
    "gs_e5_C001_s3a_semantic_guided_r1",
    "gs_e5_C001_s3a_semantic_guided_r2",
]
PI_TARGETS = ["4907199", "8568391", "8568392"]
PJPL_FIXED_PJ_TARGETS = {
    "4907202": 1025,
    "4908168": 93,
    "4908178": 419,
}
PJPL_VIEW_AUDIT_FILENAME = "pjpl_depth_anchor_views.csv"
PJPL_VIEW_AUDIT_SCHEMA = "jointbuildgs.s3a.pjpl_depth_anchor_views.v2"
PJPL_VALID_PIXEL_THRESHOLD = 64
PJPL_BOUNDARY_MIN_PIXELS = 32
PJPL_BOUNDARY_MAX_PIXELS = 128
PJPL_MIN_VISIBLE_VIEWS = 3
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
S3_METADATA_KEYS = {
    "s3_gate_attempt",
    "s3_semdepth_scale",
    "s3_nb_scale",
    "s3_claim_scope",
    "s3_no_monocular_depth",
}
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
INACTIVE_ZERO_SOURCE_BUILDINGS = ["DEBY_LOD2_4908179"]
SEED_INVENTORY_COUNTS = {
    "DEBY_LOD2_4907199": (2, 30),
    "DEBY_LOD2_8568391": (0, 9),
    "DEBY_LOD2_8568392": (0, 29),
    "DEBY_LOD2_4907202": (70, 955),
    "DEBY_LOD2_4908168": (2, 91),
    "DEBY_LOD2_4908178": (24, 395),
}
CACHE_SCHEMA = "jointbuildgs.s3a.semantic_regions.v3"
CACHE_ADDRESS_MODE = "oracle_class_plus_raycast_building_id"
CACHE_ADDRESS_GEOID_M = 48.0
CACHE_ADDRESS_SHIFT_Z_M = 556.0
CACHE_CLASS_ALIGNMENT_POLICY = (
    "fixed clean PNG is authoritative; actual-source datum ID map only; "
    "per-view raster-edge mismatch audited"
)
CACHE_GLOBAL_INPUTS = [
    REPO / "results/tum_transfer/analysis/footprints_aoi.geojson",
    REPO / "configs/input_and_alignment/projection_datum.json",
    DATA_ROOT / "sparse/0/cameras.bin",
    DATA_ROOT / "sparse/0/images.bin",
    DATA_ROOT / "sparse/0/points3D.bin",
    REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply",
    BASE_CONFIG,
    REPO / "phases/p0-audit/data/raw/lod2/690_5334.gml",
    REPO / "phases/p0-audit/data/raw/lod2/690_5336.gml",
]


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
    observed = capture(["docker", "image", "inspect", "--format", "{{.Id}}", DEV_IMAGE])
    digest_pattern = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
    supplied_is_digest = bool(digest_pattern.fullmatch(supplied))
    observed_is_digest = bool(digest_pattern.fullmatch(observed))

    if observed_is_digest:
        if supplied and (not supplied_is_digest or supplied.lower() != observed.lower()):
            raise RuntimeError(
                f"S3_DOCKER_IMAGE_ID override {supplied!r} does not match "
                f"docker inspect {observed!r}"
            )
        return observed

    inspect_unavailable = observed == "not_available:docker"
    if inspect_unavailable and supplied_is_digest:
        return supplied

    if inspect_unavailable:
        raise RuntimeError(
            "docker inspect is unavailable in-container and S3_DOCKER_IMAGE_ID "
            "is not a valid host-inspected sha256 digest"
        )

    if supplied:
        raise RuntimeError(
            f"docker inspect did not return a sha256 image ID ({observed!r}); "
            "refusing S3_DOCKER_IMAGE_ID fallback because inspect was executable"
        )
    raise RuntimeError(f"docker inspect did not return a sha256 image ID: {observed!r}")


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
    allowed_keys = (
        set(base)
        | set(SEMANTIC_DELTA_KEYS)
        | S3_METADATA_KEYS
        | set(GATE_CONTROL_KEYS)
        | set(AUDIT_CONTROL_KEYS)
        | set(RECORDING_ONLY_KEYS)
    )
    missing_base = sorted(set(base) - set(config))
    unexpected = sorted(set(config) - allowed_keys)
    if missing_base or unexpected:
        raise RuntimeError(
            "derived config key-set violates the exact Arm 1-prime + S3 delta contract: "
            f"missing_base={missing_base}, unexpected={unexpected}"
        )
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
    elif run_name == f"{GATE_RUN}_half_once":
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
    if attempt == 1 and (semdepth_scale != 1.0 or nb_scale != 1.0):
        raise RuntimeError(f"{run_name}: initial gate must keep both S3 scales at 1.0")
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
        "s3_claim_scope": (
            "oracle class+instance-address mechanism upper bound; not a battlefield win; "
            "S3-B forbids the oracle ID map and owns the FM/paper claim"
        ),
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


def expected_image_paths() -> list[Path]:
    image_dir = DATA_ROOT / "images"
    images = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(images) != 428:
        raise RuntimeError(f"locked C001 view count is 428, found {len(images)} in {rel(image_dir)}")
    return images


def expected_cache_stems() -> list[str]:
    return [path.stem for path in expected_image_paths()]


def expected_cache_provenance() -> dict[str, Any]:
    """Derive the immutable cache-input contract from the current locked inputs."""

    base = locked_base()
    building_ids = list(base.get("seed_log_buildings") or [])
    if len(building_ids) != 18 or len(set(building_ids)) != 18:
        raise RuntimeError(
            "Arm 1-prime cache candidate list must contain exactly 18 unique buildings"
        )
    missing_inputs = [rel(path) for path in CACHE_GLOBAL_INPUTS if not path.is_file()]
    if missing_inputs:
        raise FileNotFoundError(f"cache provenance inputs missing: {missing_inputs}")
    list_hash = hashlib.sha256(
        json.dumps(building_ids, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "config_order": building_ids,
        "assignment_order": sorted(building_ids),
        "list_sha256": list_hash,
        "global_hashes": {rel(path): sha256_file(path) for path in CACHE_GLOBAL_INPUTS},
    }


def cache_inventory_contract(*, require_complete: bool) -> dict[str, Any]:
    """Validate the producer inventory and return its sorted cache fingerprint."""

    rows = read_csv(CACHE_INVENTORY)
    if not rows:
        if require_complete:
            raise RuntimeError(f"missing canonical cache inventory: {rel(CACHE_INVENTORY)}")
        return {"rows": {}, "aggregate_sha256": "", "inventory_sha256": ""}
    expected = expected_cache_stems()
    by_stem: dict[str, dict[str, str]] = {}
    for row in rows:
        stem = row.get("view_stem", "")
        if not stem or stem in by_stem:
            raise RuntimeError(f"cache inventory has empty/duplicate view_stem: {stem!r}")
        by_stem[stem] = row
    missing = sorted(set(expected) - set(by_stem))
    extra = sorted(set(by_stem) - set(expected))
    if require_complete and (missing or extra or len(rows) != 428):
        raise RuntimeError(
            f"cache inventory must be exact 428 views: rows={len(rows)}, "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )
    usable = [stem for stem in expected if stem in by_stem]
    pairs: list[list[str]] = []
    for stem in usable:
        row = by_stem[stem]
        cache_path = SEMANTIC_REGION_CACHE / f"{stem}.npz"
        semantic_path = DATA_ROOT / "semantic" / f"{stem}.png"
        expected_fields = {
            "cache_path": rel(cache_path),
            "semantic_mask_path": rel(semantic_path),
            "status": "ok",
        }
        mismatches = {
            key: {"actual": row.get(key), "expected": value}
            for key, value in expected_fields.items()
            if row.get(key) != value
        }
        digest = row.get("cache_sha256", "")
        semantic_digest = row.get("semantic_mask_sha256", "")
        if mismatches or not re.fullmatch(r"[0-9a-f]{64}", digest) or not re.fullmatch(
            r"[0-9a-f]{64}", semantic_digest
        ):
            raise RuntimeError(
                f"cache inventory row {stem} violates path/status/hash contract: {mismatches}"
            )
        pairs.append([stem, digest])
    return {
        "rows": by_stem,
        "aggregate_sha256": sha256_json(pairs),
        "inventory_sha256": sha256_file(CACHE_INVENTORY),
    }


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

    import numpy as np
    from PIL import Image

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

    inventory_contract = cache_inventory_contract(require_complete=limit is None)
    inventory_rows = inventory_contract["rows"]
    image_by_stem = {path.stem: path for path in expected_image_paths()}
    cache = SemanticRegionCache(SEMANTIC_REGION_CACHE)
    provenance = expected_cache_provenance()
    required_top = {
        "schema",
        "regions",
        "source_component_min_pixels",
        "connectivity",
        "cutline_half_width_px",
        "raycast_assignment_check",
        "oracle_address_check",
        "footprint_rule_defect_baseline",
        "candidate_building_source",
        "candidate_building_ids_config_order",
        "candidate_building_ids_assignment_order",
        "candidate_building_list_sha256",
        "candidate_buildings_inactive_for_loss_address",
        "zero_initial_point_buildings_audit_only",
        "loss_address_mode",
        "raycast_building_id_loss_role",
        "loss_address_datum",
        "official_datum_audit",
        "loss_value_contract",
        "raycast_building_id_is_loss_input",
        "input_hashes",
        "l_nb_boundary_source",
    }
    required_region = {
        "building_id",
        "source_component_id",
        "source_component_pixel_count",
        "pre_split_overlap_count",
        "pre_split_oracle_instance_count",
        "address_source",
        "lod2_depth_or_height_loss_input",
    }
    required_raycast_scopes = {
        "primary_actual_label_source",
        "secondary_official_v2",
    }
    required_assignment_count_fields = {
        "true_roof_total",
        "eligible_ge256_true_roof",
        "correct",
        "wrong",
        "unassigned_no_owner",
        "cutline_excluded",
        "inactive_veto_excluded",
        "assigned",
    }

    def validate_assignment_partition(
        stem: str, scope_name: str, label: str, counts: dict[str, Any]
    ) -> None:
        missing_counts = sorted(required_assignment_count_fields - set(counts))
        if missing_counts:
            raise RuntimeError(
                f"{stem}.npz {scope_name}.{label} missing assignment counts: {missing_counts}"
            )
        parsed: dict[str, int] = {}
        for key in required_assignment_count_fields:
            value = finite_number(counts[key])
            if value is None or value < 0 or not float(value).is_integer():
                raise RuntimeError(
                    f"{stem}.npz {scope_name}.{label}.{key} is not a nonnegative integer"
                )
            parsed[key] = int(value)
        if parsed["eligible_ge256_true_roof"] != (
            parsed["correct"]
            + parsed["wrong"]
            + parsed["unassigned_no_owner"]
            + parsed["cutline_excluded"]
            + parsed["inactive_veto_excluded"]
        ):
            raise RuntimeError(
                f"{stem}.npz {scope_name}.{label} raycast partition is inconsistent"
            )
        if parsed["true_roof_total"] < parsed["eligible_ge256_true_roof"]:
            raise RuntimeError(
                f"{stem}.npz {scope_name}.{label} true-roof visibility is smaller than eligible support"
            )
        if parsed["assigned"] != parsed["correct"] + parsed["wrong"]:
            raise RuntimeError(
                f"{stem}.npz {scope_name}.{label} assigned count is inconsistent"
            )

    region_total = 0
    validated_cache_pairs: list[list[str]] = []
    for stem in selected:
        cache_path = SEMANTIC_REGION_CACHE / f"{stem}.npz"
        with np.load(cache_path, allow_pickle=False) as raw:
            required_arrays = {"region_ids", "cutline_mask", "metadata_json"}
            missing_arrays = sorted(required_arrays - set(raw.files))
            if missing_arrays:
                raise RuntimeError(f"{stem}.npz missing raw arrays: {missing_arrays}")
            extra_arrays = sorted(set(raw.files) - required_arrays)
            if extra_arrays:
                raise RuntimeError(
                    f"{stem}.npz has forbidden loss-value side-channel arrays: {extra_arrays}"
                )
            raw_region_ids = raw["region_ids"]
            raw_cutline = raw["cutline_mask"]
            if raw_region_ids.dtype != np.dtype(np.int32):
                raise RuntimeError(f"{stem}.npz raw region_ids dtype must be int32")
            if raw_cutline.dtype != np.dtype(np.bool_):
                raise RuntimeError(f"{stem}.npz raw cutline_mask dtype must be bool")
            if raw_region_ids.ndim != 2 or raw_cutline.shape != raw_region_ids.shape:
                raise RuntimeError(f"{stem}.npz raw arrays must share an HxW shape")
            raw_shape = [int(raw_region_ids.shape[0]), int(raw_region_ids.shape[1])]
        image_path = image_by_stem[stem]
        with Image.open(image_path) as image:
            image_width, image_height = image.size
        expected_shape = [int(image_height), int(image_width)]
        if raw_shape != expected_shape:
            raise RuntimeError(
                f"{stem}.npz raw shape {raw_shape} does not match current image {expected_shape}"
            )
        cache_digest = sha256_file(cache_path)
        semantic_path = DATA_ROOT / "semantic" / f"{stem}.png"
        semantic_digest = sha256_file(semantic_path)
        inventory_row = inventory_rows.get(stem)
        if inventory_row is not None:
            expected_inventory = {
                "image_name": image_path.name,
                "height_px": str(image_height),
                "width_px": str(image_width),
                "cache_sha256": cache_digest,
                "semantic_mask_sha256": semantic_digest,
            }
            mismatches = {
                key: {"actual": inventory_row.get(key), "expected": value}
                for key, value in expected_inventory.items()
                if inventory_row.get(key) != value
            }
            if mismatches:
                raise RuntimeError(f"{stem}.npz differs from canonical cache inventory: {mismatches}")
        validated_cache_pairs.append([stem, cache_digest])
        frame = cache._load_cpu(stem)  # task-scoped preflight of the production loader.
        metadata = frame.metadata
        missing_top = sorted(required_top - set(metadata))
        if missing_top:
            raise RuntimeError(f"{stem}.npz metadata missing top-level keys: {missing_top}")
        if metadata["schema"] != CACHE_SCHEMA:
            raise RuntimeError(f"{stem}.npz cache schema is not {CACHE_SCHEMA}")
        if metadata.get("image_stem") != stem or metadata.get("image_name") != image_path.name:
            raise RuntimeError(f"{stem}.npz image identity metadata mismatch")
        if metadata.get("shape_hw") != expected_shape:
            raise RuntimeError(f"{stem}.npz shape_hw metadata mismatch")
        if int(metadata["source_component_min_pixels"]) != 256:
            raise RuntimeError(f"{stem}.npz source_component_min_pixels is not 256")
        if int(metadata["connectivity"]) != 8:
            raise RuntimeError(f"{stem}.npz connectivity is not 8")
        if int(metadata["cutline_half_width_px"]) != 7:
            raise RuntimeError(f"{stem}.npz cutline_half_width_px is not 7")
        if metadata["candidate_building_source"] != rel(BASE_CONFIG):
            raise RuntimeError(f"{stem}.npz candidate building source is not the locked Arm 1-prime config")
        if metadata["candidate_building_ids_config_order"] != provenance["config_order"]:
            raise RuntimeError(f"{stem}.npz candidate config-order list is not exact C00118")
        if metadata["candidate_building_ids_assignment_order"] != provenance["assignment_order"]:
            raise RuntimeError(f"{stem}.npz candidate assignment-order list is not exact C00118")
        if metadata["candidate_building_list_sha256"] != provenance["list_sha256"]:
            raise RuntimeError(f"{stem}.npz candidate building list hash mismatch")
        if metadata["candidate_buildings_inactive_for_loss_address"] != []:
            raise RuntimeError(f"{stem}.npz oracle ID address must not deactivate zero-source buildings")
        if metadata["zero_initial_point_buildings_audit_only"] != INACTIVE_ZERO_SOURCE_BUILDINGS:
            raise RuntimeError(f"{stem}.npz zero-source audit inventory mismatch")
        if metadata["loss_address_mode"] != CACHE_ADDRESS_MODE:
            raise RuntimeError(f"{stem}.npz loss address mode is not {CACHE_ADDRESS_MODE}")
        if metadata["raycast_building_id_is_loss_input"] is not True:
            raise RuntimeError(f"{stem}.npz actual-source raycast building ID must address R")
        if metadata["raycast_building_id_loss_role"] != "region address only":
            raise RuntimeError(f"{stem}.npz raycast building ID role exceeds address-only")
        if metadata["l_nb_boundary_source"] != "class boundary only; cutline_mask is forbidden for L_nb":
            raise RuntimeError(f"{stem}.npz L_nb source improperly includes instance cutlines")
        address_datum = metadata["loss_address_datum"]
        if (
            not isinstance(address_datum, dict)
            or address_datum.get("provenance") != "actual_clean_label_source_legacy48p0"
            or not math.isclose(float(address_datum.get("orthometric_geoid_m", float("nan"))), CACHE_ADDRESS_GEOID_M)
            or not math.isclose(float(address_datum.get("shift_z_m", float("nan"))), CACHE_ADDRESS_SHIFT_Z_M)
            or address_datum.get("class_mask_alignment") != CACHE_CLASS_ALIGNMENT_POLICY
        ):
            raise RuntimeError(f"{stem}.npz loss address datum is not exact actual label source")
        official_audit = metadata["official_datum_audit"]
        if (
            not isinstance(official_audit, dict)
            or official_audit.get("role") != "audit_only"
            or official_audit.get("is_loss_input") is not False
            or not math.isclose(float(official_audit.get("orthometric_geoid_m", float("nan"))), 45.7)
            or not math.isclose(float(official_audit.get("shift_z_m", float("nan"))), 558.3)
        ):
            raise RuntimeError(f"{stem}.npz official datum must remain a 45.7/558.3 audit")
        value_contract = metadata["loss_value_contract"]
        expected_value_contract = {
            "raycast_building_id_role": "region membership only",
            "raycast_hit_distance_stored": False,
            "raycast_intersection_xyz_stored": False,
            "lod2_depth_or_height_loss_input": False,
            "official_datum_is_loss_input": False,
            "absolute_height_source": "existing L_depth supervision only",
            "npz_loss_address_arrays": ["region_ids", "cutline_mask"],
        }
        if not isinstance(value_contract, dict) or any(
            value_contract.get(key) != expected
            for key, expected in expected_value_contract.items()
        ):
            raise RuntimeError(f"{stem}.npz loss-value isolation contract mismatch")
        baseline = metadata["footprint_rule_defect_baseline"]
        if not isinstance(baseline, dict) or not str(baseline.get("role", "")).startswith("audit_only"):
            raise RuntimeError(f"{stem}.npz footprint-rule baseline is not audit-only")
        height_policy = baseline.get("projection_height_policy")
        if (
            not isinstance(height_policy, dict)
            or height_policy.get("uses_lod2_height") is not False
            or height_policy.get("is_loss_address_input") is not False
        ):
            raise RuntimeError(f"{stem}.npz footprint projection-height baseline leaked into R")
        inventory = baseline.get("projection_height_candidate_inventory_c00118")
        if not isinstance(inventory, dict) or sorted(inventory) != provenance["assignment_order"]:
            raise RuntimeError(f"{stem}.npz footprint-audit projection inventory is not exact C00118")
        derived_inactive: list[str] = []
        for building_id, row in inventory.items():
            if not isinstance(row, dict):
                raise RuntimeError(f"{stem}.npz projection-height row for {building_id} is not a mapping")
            count_values: dict[str, int] = {}
            for key in ("source_count", "sparse_points3d_count", "dense_init_point_count"):
                value = finite_number(row.get(key))
                if value is None or value < 0 or not float(value).is_integer():
                    raise RuntimeError(f"{stem}.npz invalid {key} for {building_id}")
                count_values[key] = int(value)
            count = count_values["source_count"]
            if count != count_values["sparse_points3d_count"] + count_values["dense_init_point_count"]:
                raise RuntimeError(f"{stem}.npz source-count decomposition mismatch for {building_id}")
            active = row.get("active_for_loss_address")
            if row.get("fallback_used") is not False or active is not (count > 0):
                raise RuntimeError(f"{stem}.npz invalid no-fallback source policy for {building_id}")
            if count == 0 and row.get("estimated_z_local_m") is not None:
                raise RuntimeError(f"{stem}.npz inactive {building_id} has an active projection height")
            if count == 0:
                derived_inactive.append(building_id)
        if derived_inactive != metadata["zero_initial_point_buildings_audit_only"]:
            raise RuntimeError(f"{stem}.npz zero-source audit inventory/top-level mismatch")
        hashes = metadata["input_hashes"]
        if not isinstance(hashes, dict) or hashes.get("global") != provenance["global_hashes"]:
            raise RuntimeError(f"{stem}.npz global input hashes do not match current locked inputs")
        expected_semantic_hash = {rel(semantic_path): semantic_digest}
        if hashes.get("semantic_mask") != expected_semantic_hash:
            raise RuntimeError(f"{stem}.npz semantic-mask hash does not match current input")
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
            if region.get("address_source") != "actual_label_source_raycast_building_id_only":
                raise RuntimeError(f"{stem}.npz region {region_id} is not oracle-ID addressed")
            if region.get("lod2_depth_or_height_loss_input") is not False:
                raise RuntimeError(f"{stem}.npz region {region_id} permits LoD2 value supervision")
            forbidden_region_fields = {
                "projection_z_local_m",
                "reference_roof_z_local_m",
                "depth_target",
                "height_target",
                "raycast_hit_distance",
                "raycast_intersection_xyz",
            }
            leaked = sorted(forbidden_region_fields & set(region))
            if leaked:
                raise RuntimeError(
                    f"{stem}.npz region {region_id} exposes forbidden value fields: {leaked}"
                )
        oracle_check = metadata["oracle_address_check"]
        if (
            not isinstance(oracle_check, dict)
            or oracle_check.get("provenance") != "actual_label_source_legacy48p0_oracle_address"
            or oracle_check.get("raycast_building_id_is_loss_input") is not True
            or not math.isclose(float(oracle_check.get("shift_z_m", float("nan"))), CACHE_ADDRESS_SHIFT_Z_M)
        ):
            raise RuntimeError(f"{stem}.npz oracle-address integrity provenance mismatch")
        oracle_totals = oracle_check.get("totals")
        oracle_by_building = oracle_check.get("by_building")
        if not isinstance(oracle_totals, dict) or not isinstance(oracle_by_building, dict):
            raise RuntimeError(f"{stem}.npz oracle-address integrity counts are missing")
        validate_assignment_partition(stem, "oracle_address_check", "totals", oracle_totals)
        if int(oracle_totals["wrong"]) != 0:
            raise RuntimeError(f"{stem}.npz oracle-address integrity has nonzero misassignment")
        if sorted(oracle_by_building) != provenance["assignment_order"]:
            raise RuntimeError(f"{stem}.npz oracle-address integrity is not exact C00118")
        for building_id, counts in oracle_by_building.items():
            validate_assignment_partition(stem, "oracle_address_check", building_id, counts)
            if int(counts["wrong"]) != 0:
                raise RuntimeError(
                    f"{stem}.npz oracle-address integrity wrong pixels for {building_id}"
                )
        raycast = metadata["raycast_assignment_check"]
        if not isinstance(raycast, dict):
            raise RuntimeError(f"{stem}.npz raycast_assignment_check must be a mapping")
        if raycast != baseline.get("raycast_assignment_check"):
            raise RuntimeError(f"{stem}.npz footprint-rule baseline/compatibility audit mismatch")
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
            if scope.get("raycast_building_id_is_loss_input") is not False:
                raise RuntimeError(f"{stem}.npz {scope_name} raycast IDs are not audit-only")
            totals = scope.get("totals")
            by_building = scope.get("by_building")
            if not isinstance(totals, dict) or not isinstance(by_building, dict):
                raise RuntimeError(f"{stem}.npz {scope_name} totals/by_building must be mappings")
            if sorted(by_building) != provenance["assignment_order"]:
                raise RuntimeError(f"{stem}.npz {scope_name} by-building audit is not exact C00118")
            validate_assignment_partition(stem, scope_name, "totals", totals)
            for building_id, counts in by_building.items():
                if not isinstance(counts, dict):
                    raise RuntimeError(f"{stem}.npz {scope_name}.{building_id} is not a mapping")
                validate_assignment_partition(stem, scope_name, building_id, counts)
            for key in required_assignment_count_fields:
                if int(totals[key]) != sum(int(counts[key]) for counts in by_building.values()):
                    raise RuntimeError(
                        f"{stem}.npz {scope_name} totals/by-building sum mismatch for {key}"
                    )
            expected_rate = (
                float(totals["wrong"]) / float(totals["assigned"])
                if int(totals["assigned"])
                else None
            )
            actual_rate = totals.get("conditional_misassignment_rate")
            if expected_rate is None:
                if actual_rate is not None:
                    raise RuntimeError(f"{stem}.npz {scope_name} zero-assigned rate must be null")
            elif finite_number(actual_rate) is None or not math.isclose(
                float(actual_rate), expected_rate, rel_tol=1e-9, abs_tol=1e-12
            ):
                raise RuntimeError(f"{stem}.npz {scope_name} misassignment rate mismatch")
        region_total += len(regions)
        # The production loader is deliberately lazy and memoizes frames for
        # training.  A 428-view validation should not retain the entire cache
        # (~multi-GiB CPU tensors) merely to prove the contract once.
        cache._cpu_cache.pop(stem, None)
    cache_aggregate_sha256 = sha256_json(validated_cache_pairs)
    if limit is None and cache_aggregate_sha256 != inventory_contract["aggregate_sha256"]:
        raise RuntimeError("validated cache aggregate does not match canonical inventory aggregate")
    return {
        "cache": status,
        "loader": "src.stage2.loss.semantic_guided.SemanticRegionCache",
        "validated_files": len(selected),
        "validated_regions": region_total,
        "cache_aggregate_sha256": cache_aggregate_sha256,
        "cache_inventory": rel(CACHE_INVENTORY),
        "cache_inventory_sha256": inventory_contract["inventory_sha256"],
        "metadata_contract": {
            "top_level": sorted(required_top),
            "per_region": sorted(required_region),
            "raycast_assignment_check_scopes": sorted(required_raycast_scopes),
            "raycast_assignment_count_fields": sorted(required_assignment_count_fields),
            "cache_schema": CACHE_SCHEMA,
            "candidate_building_list_sha256": provenance["list_sha256"],
            "global_input_hashes": provenance["global_hashes"],
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
    config["s3_claim_scope"] = (
        "oracle class+instance-address mechanism upper bound; not a battlefield win; "
        "S3-B forbids the oracle ID map and owns the FM/paper claim"
    )
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
        "claim_scope": (
            "S3-A oracle class+instance-address mechanism upper bound; not a battlefield "
            "win; S3-B forbids the oracle ID map and owns the FM/paper claim"
        ),
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
            "pjpl_classification": {
                "targets": PI_TARGETS,
                "measurement": "post_probe_full_training_view_sweep",
                "valid_pixel_rule": "alpha>=0.5 AND existing_L_depth_valid",
                "building_aggregation": "visible_view_median",
                "pj_threshold_pixels": PJPL_VALID_PIXEL_THRESHOLD,
                "pl_rule": f"median<{PJPL_VALID_PIXEL_THRESHOLD}",
                "boundary_case_inclusive_pixels": [
                    PJPL_BOUNDARY_MIN_PIXELS,
                    PJPL_BOUNDARY_MAX_PIXELS,
                ],
                "min_visible_views": PJPL_MIN_VISIBLE_VIEWS,
                "fixed_collapse_pj_targets": PJPL_FIXED_PJ_TARGETS,
                "raycast_id_role": "region_membership_only",
                "raycast_id_depth_or_height_supervision": False,
            },
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
            "pjpl_view_audit_per_gate_attempt": (
                f"<gate_run_out>/audit/{PJPL_VIEW_AUDIT_FILENAME}"
            ),
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
        (
            "claim_scope: S3-A oracle class+instance-address mechanism upper bound; "
            "not a battlefield win; S3-B forbids the oracle ID map and owns the FM/paper claim"
        ),
        f"base_config: {rel(BASE_CONFIG)}",
        f"base_config_sha256: {sha256_file(BASE_CONFIG)}",
        f"orchestrator_sha256: {sha256_file(SCRIPT_PATH)}",
        f"train_py_sha256: {sha256_file(REPO / 'src/stage2/train.py')}",
        f"densification_py_sha256: {sha256_file(REPO / 'src/stage2/densification.py')}",
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
    if args.tag != "half_once":
        raise RuntimeError("the only permitted second-attempt tag is exactly 'half_once'")
    run_name = f"{GATE_RUN}_{args.tag}"
    gate_commit = committed_unchanged(CSV_GATE_AUDIT)
    if not gate_commit["committed_unchanged"]:
        raise RuntimeError(f"half-once config requires committed attempt-1 audit: {gate_commit}")
    selection = canonical_gate_selection()
    initial = selection["by_run"].get(GATE_RUN)
    if selection["errors"] or initial is None:
        raise RuntimeError(f"attempt-1 gate provenance is invalid: {selection['errors']}")
    if initial.get("gate_status") != "fail":
        raise RuntimeError("half-once is forbidden unless canonical attempt 1 failed")
    expected_semdepth_scale = 0.5 if initial.get("semdepth_over_threshold") == "true" else 1.0
    expected_nb_scale = 0.5 if initial.get("boundary_normal_over_threshold") == "true" else 1.0
    if expected_semdepth_scale == 1.0 and expected_nb_scale == 1.0:
        raise RuntimeError("attempt 1 has no complete over-threshold loss eligible for halving")
    if not same_value(args.semdepth_scale, expected_semdepth_scale) or not same_value(
        args.nb_scale, expected_nb_scale
    ):
        raise RuntimeError(
            "half-once scales must exactly follow attempt-1 sampled maxima: "
            f"expected semdepth={expected_semdepth_scale}, nb={expected_nb_scale}"
        )
    existing_attempt2_rows = [
        row
        for row in read_csv(CSV_INVENTORY)
        if row.get("record_type") == "training_config"
        and row.get("gate_attempt") == "2"
    ]
    attempt2_artifacts = launch_artifact_state(
        run_name,
        {
            "out_dir": ws(CKPT_ROOT / run_name),
        },
    )
    if (
        run_name_config_path(run_name).exists()
        or existing_attempt2_rows
        or selection["by_run"].get(run_name) is not None
        or attempt2_artifacts["collision"]
    ):
        raise RuntimeError(
            "half-once is globally create-only and attempt-2 material already exists: "
            f"config={run_name_config_path(run_name).exists()}, inventory_rows={len(existing_attempt2_rows)}, "
            f"summary={selection['by_run'].get(run_name) is not None}, artifacts={attempt2_artifacts}"
        )
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


def sync_full_configs_from_gate(_args: argparse.Namespace) -> None:
    """Carry the mechanically selected gate weights into both full cells."""

    gate_commit = committed_unchanged(CSV_GATE_AUDIT)
    if not gate_commit["committed_unchanged"]:
        raise RuntimeError(f"full-config sync requires committed gate evidence: {gate_commit}")
    selection = canonical_gate_selection()
    selected = selection["selected"]
    if selection["errors"] or selected.get("gate_status") != "pass":
        raise RuntimeError(
            f"full-config sync requires one valid passing selected gate: errors={selection['errors']}, "
            f"status={selected.get('gate_status', 'missing')}"
        )
    semdepth_scale = finite_number(selected.get("effective_semdepth_scale"))
    nb_scale = finite_number(selected.get("effective_nb_scale"))
    if semdepth_scale not in {0.5, 1.0} or nb_scale not in {0.5, 1.0}:
        raise RuntimeError(f"selected gate scales are invalid: {semdepth_scale}/{nb_scale}")
    for run_name in FULL_RUNS:
        config_path = run_name_config_path(run_name)
        existing = load_yaml(config_path) if config_path.is_file() else {}
        if existing and same_value(existing.get("s3_semdepth_scale"), semdepth_scale) and same_value(
            existing.get("s3_nb_scale"), nb_scale
        ):
            continue
        state = launch_artifact_state(
            run_name,
            {"out_dir": ws(CKPT_ROOT / run_name)},
        )
        if state["collision"]:
            raise RuntimeError(f"cannot rescale a full config after launch material exists: {state}")

    base = locked_base()
    cache = cache_status()
    rows: list[dict[str, Any]] = []
    for replicate, run_name in zip(("r1", "r2"), FULL_RUNS):
        path, config, metadata = make_config(
            base=base,
            run_name=run_name,
            max_iter=FULL_MAX_ITER,
            generic_audit_every=FULL_GENERIC_AUDIT_EVERY,
            semantic_audit_every=FULL_SEMANTIC_AUDIT_EVERY,
            semdepth_scale=float(semdepth_scale),
            nb_scale=float(nb_scale),
            gate_attempt=0,
        )
        rows.append(
            config_inventory_row(
                phase="full_selected_gate",
                replicate=replicate,
                run_name=run_name,
                path=path,
                config=config,
                metadata=metadata,
                cache=cache,
            )
        )
    update_inventory(rows, set(FULL_RUNS))
    write_manifest_and_versions()
    print(
        json.dumps(
            {
                "selected_gate_run": selected["run_name"],
                "semdepth_scale": semdepth_scale,
                "nb_scale": nb_scale,
                "configs": [rel(run_name_config_path(run_name)) for run_name in FULL_RUNS],
                "training_started": False,
            },
            ensure_ascii=False,
        )
    )


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


def recompute_gate_mechanical_summary(run_name: str) -> dict[str, str]:
    """Re-run the pure CSV gate calculation into an isolated test-only file."""

    config = load_yaml(run_name_config_path(run_name))
    out_dir = workspace_path_to_host(config["out_dir"])
    with tempfile.TemporaryDirectory(prefix="jointbuildgs_s3_gate_recheck_") as tmp:
        output = Path(tmp) / "gate_recheck.csv"
        args = argparse.Namespace(
            run_name=run_name,
            loss_csv=str(out_dir / "audit/loss_grad_norms.csv"),
            semantic_csv=str(out_dir / "audit/semantic_geometry.csv"),
            pjpl_csv=str(out_dir / f"audit/{PJPL_VIEW_AUDIT_FILENAME}"),
            train_log=str(TRAIN_LOG_ROOT / f"{run_name}.log"),
            output=str(output),
            test_mode=True,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            gate_audit(args)
        summaries = [
            row for row in read_csv(output) if row.get("record_type") == "gate_summary"
        ]
    if len(summaries) != 1:
        raise RuntimeError(f"mechanical gate recheck emitted {len(summaries)} summaries")
    return summaries[0]


def validate_gate_summary_provenance(summary: dict[str, str]) -> list[str]:
    """Rebind one canonical summary to current gate inputs and raw evidence."""

    errors: list[str] = []
    run_name = summary.get("run_name", "")
    attempt_by_run = {GATE_RUN: 1, f"{GATE_RUN}_half_once": 2}
    if run_name not in attempt_by_run:
        return [f"unrecognised canonical gate run: {run_name!r}"]
    try:
        attempt = int(summary.get("gate_attempt", ""))
    except ValueError:
        return [f"{run_name}: non-integer gate_attempt"]
    if attempt != attempt_by_run[run_name]:
        errors.append(f"{run_name}: gate_attempt/run-name mismatch")
    if summary.get("evidence_scope") != "canonical":
        errors.append(f"{run_name}: evidence_scope is not canonical")

    config_path = run_name_config_path(run_name)
    if not config_path.is_file():
        return errors + [f"{run_name}: config is missing"]
    try:
        config = load_yaml(config_path)
        verify_exact_base(config, locked_base())
        validate_s3_config(config, run_name)
    except Exception as exc:
        return errors + [f"{run_name}: config validation failed: {exc}"]
    out_dir = workspace_path_to_host(config["out_dir"])
    current_pjpl_path = out_dir / f"audit/{PJPL_VIEW_AUDIT_FILENAME}"
    if attempt == 2:
        attempt1_config_path = run_name_config_path(GATE_RUN)
        if not attempt1_config_path.is_file():
            return errors + [f"{run_name}: attempt-1 config is missing"]
        attempt1_config = load_yaml(attempt1_config_path)
        authoritative_pjpl_path = (
            workspace_path_to_host(attempt1_config["out_dir"])
            / f"audit/{PJPL_VIEW_AUDIT_FILENAME}"
        )
    else:
        authoritative_pjpl_path = current_pjpl_path
    expected_paths = {
        "config": config_path,
        "loss_source_csv": out_dir / "audit/loss_grad_norms.csv",
        "semantic_source_csv": out_dir / "audit/semantic_geometry.csv",
        "pjpl_source_csv": authoritative_pjpl_path,
        "pjpl_diagnostic_source_csv": current_pjpl_path,
        "train_log": TRAIN_LOG_ROOT / f"{run_name}.log",
        "launch_versions": RUN_DIR / "versions" / f"{run_name}.txt",
    }
    for field, path in expected_paths.items():
        if summary.get(field) != rel(path):
            errors.append(f"{run_name}: {field} canonical path mismatch")
        digest_field = f"{field}_sha256"
        if not path.is_file() or summary.get(digest_field) != sha256_file(path):
            errors.append(f"{run_name}: {digest_field} missing or stale")

    try:
        cache_inventory = cache_inventory_contract(require_complete=True)
    except Exception as exc:
        return errors + [f"{run_name}: cache inventory validation failed: {exc}"]
    current_hashes = {
        "orchestrator_sha256": sha256_file(SCRIPT_PATH),
        "train_py_sha256": sha256_file(REPO / "src/stage2/train.py"),
        "densification_py_sha256": sha256_file(REPO / "src/stage2/densification.py"),
        "semantic_loss_py_sha256": sha256_file(REPO / "src/stage2/loss/semantic_guided.py"),
        "cache_producer_sha256": sha256_file(CACHE_PRODUCER),
        "cache_manifest_sha256": sha256_file(CACHE_MANIFEST),
        "cache_inventory_sha256": cache_inventory["inventory_sha256"],
        "cache_aggregate_sha256": cache_inventory["aggregate_sha256"],
    }
    for field, expected in current_hashes.items():
        if summary.get(field) != expected:
            errors.append(f"{run_name}: {field} differs from current locked input")
    expected_scalars = {
        "effective_semdepth_scale": float(config["s3_semdepth_scale"]),
        "effective_nb_scale": float(config["s3_nb_scale"]),
        "effective_w_semdepth_smooth": float(config["w_semdepth_smooth"]),
        "effective_w_semdepth_plane": float(config["w_semdepth_plane"]),
        "effective_w_boundary_normal": float(config["w_boundary_normal"]),
    }
    for field, expected in expected_scalars.items():
        if not same_value(summary.get(field), expected):
            errors.append(f"{run_name}: {field} does not match its config")
    preflight_path = REPO / summary.get("cache_preflight_log", "")
    if (
        not preflight_path.is_file()
        or summary.get("cache_preflight_log_sha256") != sha256_file(preflight_path)
    ):
        errors.append(f"{run_name}: cache preflight evidence is missing or stale")
    try:
        recomputed = recompute_gate_mechanical_summary(run_name)
        mechanical_fields = {
            "active_start",
            "active_end",
            "active_update_count",
            "generic_audit_every",
            "generic_expected_step_count",
            "generic_observed_step_count",
            "semantic_audit_every",
            "semantic_expected_step_count",
            "semantic_observed_step_count",
            "total_loss_finite_status",
            "train_return_code",
            "nonfinite_loss_records",
            "semdepth_grad_share_p50",
            "semdepth_grad_share_p95",
            "semdepth_grad_share_max",
            "semdepth_grad_share_threshold",
            "semdepth_audit_rows_complete",
            "semdepth_status",
            "boundary_normal_grad_share_p50",
            "boundary_normal_grad_share_p95",
            "boundary_normal_grad_share_max",
            "boundary_normal_grad_share_threshold",
            "boundary_normal_audit_rows_complete",
            "boundary_normal_status",
            "smooth_grad_share_p50_audit_only",
            "smooth_grad_share_max_audit_only",
            "smooth_audit_rows_complete",
            "plane_grad_share_p50_audit_only",
            "plane_grad_share_max_audit_only",
            "plane_audit_rows_complete",
            "smooth_plane_detail_status",
            "pi_all_targets_status",
            "pjpl_classification_status",
            "pjpl_diagnostic_status",
            "pjpl_target_rule",
            "pjpl_boundary_case_rule",
            "pjpl_min_visible_views",
            "pjpl_target_classifications",
            "pjpl_diagnostic_target_classifications",
            "pjpl_boundary_case_buildings",
            "pjpl_diagnostic_boundary_case_buildings",
            "pjpl_fixed_collapse_pj_targets",
            "pjpl_source_view_rows",
            "pjpl_diagnostic_source_view_rows",
            "pjpl_authority",
            "pjpl_frozen_from_run",
            "pjpl_attempt1_lock_sha256",
            "gate_status",
            "gate_reasons",
            "gate_attempt",
            "effective_semdepth_scale",
            "effective_nb_scale",
            "effective_w_semdepth_smooth",
            "effective_w_semdepth_plane",
            "effective_w_boundary_normal",
            "semdepth_over_threshold",
            "boundary_normal_over_threshold",
            "suggested_semdepth_scale",
            "suggested_nb_scale",
            "regate_config_command_not_executed",
            "config",
            "config_sha256",
            "loss_source_csv",
            "loss_source_csv_sha256",
            "semantic_source_csv",
            "semantic_source_csv_sha256",
            "pjpl_source_csv",
            "pjpl_source_csv_sha256",
            "pjpl_diagnostic_source_csv",
            "pjpl_diagnostic_source_csv_sha256",
            "train_log",
            "train_log_sha256",
            "grad_share_sampling",
            "denominator_contract",
        }
        mismatched = sorted(
            field for field in mechanical_fields if summary.get(field, "") != recomputed.get(field, "")
        )
        if mismatched:
            errors.append(f"{run_name}: committed summary differs from mechanical recheck: {mismatched}")
    except Exception as exc:
        errors.append(f"{run_name}: mechanical gate recheck failed: {exc}")
    return errors


def canonical_gate_selection() -> dict[str, Any]:
    """Select only the preregistered attempt1/half-once evidence."""

    summaries = [
        row for row in read_csv(CSV_GATE_AUDIT) if row.get("record_type") == "gate_summary"
    ]
    by_run: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    allowed = {GATE_RUN, f"{GATE_RUN}_half_once"}
    for row in summaries:
        run_name = row.get("run_name", "")
        if run_name not in allowed:
            errors.append(f"unexpected gate summary run_name: {run_name!r}")
        elif run_name in by_run:
            errors.append(f"duplicate gate summary for {run_name}")
        else:
            by_run[run_name] = row
    initial = by_run.get(GATE_RUN)
    half = by_run.get(f"{GATE_RUN}_half_once")
    if initial is None:
        errors.append("canonical attempt-1 gate summary is missing")
    else:
        errors.extend(validate_gate_summary_provenance(initial))
    if half is not None:
        errors.extend(validate_gate_summary_provenance(half))

    selected = half or initial or {}
    if initial is not None:
        if initial.get("gate_status") == "pass" and half is not None:
            errors.append("half-once evidence exists even though attempt 1 passed")
        if half is not None:
            expected_sem = 0.5 if initial.get("semdepth_over_threshold") == "true" else 1.0
            expected_nb = 0.5 if initial.get("boundary_normal_over_threshold") == "true" else 1.0
            if expected_sem == 1.0 and expected_nb == 1.0:
                errors.append("half-once evidence exists without an over-threshold loss")
            if not same_value(half.get("effective_semdepth_scale"), expected_sem):
                errors.append("half-once semdepth scale does not match attempt-1 over-threshold result")
            if not same_value(half.get("effective_nb_scale"), expected_nb):
                errors.append("half-once boundary-normal scale does not match attempt-1 over-threshold result")
    return {"by_run": by_run, "selected": selected, "errors": errors}


def validate_seed_inventory(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        building_id = row.get("building_id", "")
        if not building_id or building_id in by_id:
            errors.append(f"empty/duplicate T0-2 building id: {building_id!r}")
        else:
            by_id[building_id] = row
    if set(by_id) != set(SEED_INVENTORY_COUNTS):
        errors.append(
            f"T0-2 building set mismatch: observed={sorted(by_id)}, "
            f"expected={sorted(SEED_INVENTORY_COUNTS)}"
        )
    source_contract = {
        "sfm_source": rel(DATA_ROOT / "sparse/0/points3D.bin"),
        "sfm_source_sha256": sha256_file(DATA_ROOT / "sparse/0/points3D.bin"),
        "dense_init_source": rel(
            REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
        ),
        "dense_init_source_sha256": sha256_file(
            REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
        ),
        "footprint_source": rel(REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"),
        "footprint_source_sha256": sha256_file(
            REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
        ),
        "arm1p_config": rel(BASE_CONFIG),
        "arm1p_config_sha256": sha256_file(BASE_CONFIG),
        "footprint_crs": "EPSG:25832",
        "init_pointcloud_mode": "concat_sfm_plus_dense",
        "qa_match_expected": "true",
    }
    for building_id, expected_counts in SEED_INVENTORY_COUNTS.items():
        row = by_id.get(building_id)
        if row is None:
            continue
        for field, expected in source_contract.items():
            if row.get(field) != expected:
                errors.append(f"{building_id}: T0-2 {field} mismatch")
        try:
            sfm = int(row["sfm_seed_points_in_footprint"])
            dense = int(row["dense_init_points_in_footprint"])
            initial = int(row["initial_gaussians_in_footprint"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{building_id}: invalid T0-2 point counts")
            continue
        if (sfm, dense) != expected_counts or initial != sfm + dense:
            errors.append(
                f"{building_id}: T0-2 count mismatch observed={(sfm, dense, initial)}, "
                f"expected={(*expected_counts, sum(expected_counts))}"
            )
    return errors


def track_a_preconditions() -> dict[str, Any]:
    seed_rows = read_csv(CSV_SEED_INVENTORY)
    seed_errors = validate_seed_inventory(seed_rows)
    seed_data_complete = not seed_errors
    seed_commit = committed_unchanged(CSV_SEED_INVENTORY)
    gate_commit = committed_unchanged(CSV_GATE_AUDIT)
    gate_selection = canonical_gate_selection()
    selected = gate_selection["selected"]
    selected_pass = selected.get("gate_status") == "pass"
    selected_scales = {
        "semdepth": finite_number(selected.get("effective_semdepth_scale")),
        "boundary_normal": finite_number(selected.get("effective_nb_scale")),
    }
    full_config_states: dict[str, Any] = {}
    full_scales_match = bool(selected) and selected_scales["semdepth"] is not None and selected_scales[
        "boundary_normal"
    ] is not None
    for run_name in FULL_RUNS:
        path = run_name_config_path(run_name)
        state: dict[str, Any] = {"path": rel(path), "commit": committed_unchanged(path)}
        try:
            config = load_yaml(path)
            verify_exact_base(config, locked_base())
            validate_s3_config(config, run_name)
            scale_match = same_value(config.get("s3_semdepth_scale"), selected_scales["semdepth"]) and same_value(
                config.get("s3_nb_scale"), selected_scales["boundary_normal"]
            )
            state.update(
                {
                    "valid": True,
                    "semdepth_scale": config.get("s3_semdepth_scale"),
                    "nb_scale": config.get("s3_nb_scale"),
                    "selected_scale_match": scale_match,
                }
            )
            full_scales_match = full_scales_match and scale_match and state["commit"][
                "committed_unchanged"
            ]
        except Exception as exc:
            state.update({"valid": False, "error": str(exc), "selected_scale_match": False})
            full_scales_match = False
        full_config_states[run_name] = state
    seed_complete = seed_data_complete and seed_commit["committed_unchanged"]
    gate_pass = (
        selected_pass
        and not gate_selection["errors"]
        and gate_commit["committed_unchanged"]
        and full_scales_match
    )
    gate_effective_status = selected.get("gate_status", "missing")
    if gate_selection["errors"]:
        gate_effective_status = "invalid_provenance"
    elif selected_pass and not gate_commit["committed_unchanged"]:
        gate_effective_status = "pass_uncommitted"
    elif selected_pass and not full_scales_match:
        gate_effective_status = "pass_full_scale_unsynced"
    return {
        "t0_2_seed_inventory": rel(CSV_SEED_INVENTORY),
        "t0_2_rows": len(seed_rows),
        "t0_2_data_complete": seed_data_complete,
        "t0_2_validation_errors": seed_errors,
        "t0_2_commit_state": seed_commit,
        "t0_2_complete": seed_complete,
        "t0_4_gate_audit": rel(CSV_GATE_AUDIT),
        "t0_4_gate_run": selected.get("run_name", ""),
        "t0_4_gate_data_status": selected.get("gate_status", "missing"),
        "t0_4_gate_commit_state": gate_commit,
        "t0_4_gate_status": gate_effective_status,
        "t0_4_gate_validation_errors": gate_selection["errors"],
        "selected_scales": selected_scales,
        "full_config_states": full_config_states,
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
    cache_inventory = cache_inventory_contract(require_complete=True)
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
        f"densification_py_sha256: {sha256_file(REPO / 'src/stage2/densification.py')}",
        f"semantic_loss_py_sha256: {sha256_file(REPO / 'src/stage2/loss/semantic_guided.py')}",
        f"cache_producer: {rel(CACHE_PRODUCER)}",
        f"cache_producer_sha256: {sha256_file(CACHE_PRODUCER)}",
        f"cache_manifest: {rel(CACHE_MANIFEST)}",
        f"cache_manifest_sha256: {sha256_file(CACHE_MANIFEST)}",
        f"cache_inventory: {rel(CACHE_INVENTORY)}",
        f"cache_inventory_sha256: {cache_inventory['inventory_sha256']}",
        f"cache_aggregate_sha256: {cache_inventory['aggregate_sha256']}",
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
            "densification": REPO / "src/stage2/densification.py",
            "semantic_loss": REPO / "src/stage2/loss/semantic_guided.py",
            "experiment_inventory": CSV_INVENTORY,
            "cache_producer": CACHE_PRODUCER,
            "cache_manifest": CACHE_MANIFEST,
            "cache_inventory": CACHE_INVENTORY,
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
    if HOST_REPO != REPO:
        raise RuntimeError(
            f"non-dry launch forbids alternate S3_HOST_REPO mounts: HOST_REPO={HOST_REPO}, REPO={REPO}"
        )
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
    if args.run_name == f"{GATE_RUN}_half_once":
        gate_commit = committed_unchanged(CSV_GATE_AUDIT)
        selection = canonical_gate_selection()
        initial = selection["by_run"].get(GATE_RUN)
        attempt2_rows = [
            row
            for row in read_csv(CSV_INVENTORY)
            if row.get("record_type") == "training_config"
            and row.get("run_name") == args.run_name
            and row.get("gate_attempt") == "2"
        ]
        expected_sem = 0.5 if initial and initial.get("semdepth_over_threshold") == "true" else 1.0
        expected_nb = 0.5 if initial and initial.get("boundary_normal_over_threshold") == "true" else 1.0
        if (
            not gate_commit["committed_unchanged"]
            or selection["errors"]
            or initial is None
            or initial.get("gate_status") != "fail"
            or len(attempt2_rows) != 1
            or not same_value(config_payload.get("s3_semdepth_scale"), expected_sem)
            or not same_value(config_payload.get("s3_nb_scale"), expected_nb)
        ):
            raise RuntimeError(
                "half-once launch precondition failed: "
                f"gate_commit={gate_commit}, errors={selection['errors']}, "
                f"initial_status={None if initial is None else initial.get('gate_status')}, "
                f"attempt2_inventory_rows={len(attempt2_rows)}, "
                f"expected_scales={expected_sem}/{expected_nb}"
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
        out_dir = workspace_path_to_host(config_payload["out_dir"])
        for label, audit_path in (
            ("AUDIT_LOSS_CSV", out_dir / "audit/loss_grad_norms.csv"),
            ("AUDIT_SEMANTIC_CSV", out_dir / "audit/semantic_geometry.csv"),
            ("AUDIT_PJPL_CSV", out_dir / f"audit/{PJPL_VIEW_AUDIT_FILENAME}"),
        ):
            log.write(f"{label}={rel(audit_path)}\n")
            log.write(
                f"{label}_SHA256={sha256_file(audit_path) if audit_path.is_file() else 'missing'}\n"
            )
        log.flush()
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


PJPL_VIEW_AUDIT_FIELDS = {
    "schema",
    "building_id",
    "view",
    "view_stem",
    "measurement_step",
    "source_region_count",
    "retained_region_present",
    "oracle_visible_roof_pixel_count",
    "visibility_source",
    "address_pixel_count",
    "alpha_valid_pixel_count",
    "ldepth_valid_pixel_count",
    "alpha_and_ldepth_valid_pixel_count",
    "alpha_threshold",
    "depth_mask_present",
    "depth_valid_source",
    "valid_pixel_rule",
    "view_aggregation_snapshot",
    "region_address_mode",
    "raycast_building_id_role",
    "raycast_id_depth_or_height_supervision",
    "cutline_policy",
}


def summarize_pjpl_view_rows(
    rows: list[dict[str, str]],
    *,
    active_end: int,
) -> dict[str, Any]:
    """Validate and lock the P-J/P-L median classification table.

    Classification itself is observational and never a pass/fail target: a
    valid median may yield either P-J or P-L.  Completeness/provenance of the
    three preregistered no-texture buildings is required before the 1k gate can
    be considered mechanically complete.
    """

    errors: list[str] = []
    by_building: dict[str, dict[str, int]] = {bid: {} for bid in PI_TARGETS}
    for source_row, row in enumerate(rows, start=2):
        if set(row) != PJPL_VIEW_AUDIT_FIELDS:
            errors.append(
                f"P-J/P-L source row {source_row} schema fields mismatch: "
                f"missing={sorted(PJPL_VIEW_AUDIT_FIELDS - set(row))}, "
                f"extra={sorted(set(row) - PJPL_VIEW_AUDIT_FIELDS)}"
            )
            continue
        bid = row.get("building_id", "")
        if bid not in by_building:
            errors.append(f"P-J/P-L source row {source_row} unexpected building_id={bid!r}")
            continue
        view = row.get("view", "")
        view_stem = row.get("view_stem", "")
        if not view or view_stem != Path(view).stem:
            errors.append(f"P-J/P-L source row {source_row} invalid view/view_stem")
            continue
        if view_stem in by_building[bid]:
            errors.append(f"P-J/P-L duplicate building/view row: {bid}/{view_stem}")
            continue
        constant_contract = {
            "schema": PJPL_VIEW_AUDIT_SCHEMA,
            "depth_valid_source": "batch.depth_mask_existing_L_depth",
            "valid_pixel_rule": "alpha>=0.5 AND existing_L_depth_valid",
            "view_aggregation_snapshot": "post_probe_full_training_view_sweep",
            "visibility_source": "oracle_address_check.by_building.true_roof_total",
            "region_address_mode": CACHE_ADDRESS_MODE,
            "raycast_building_id_role": "region_membership_only",
            "raycast_id_depth_or_height_supervision": "false",
            "cutline_policy": "exclude_instance_cutline_plus_minus_7px",
        }
        mismatches = [
            field for field, expected in constant_contract.items() if row.get(field) != expected
        ]
        if mismatches:
            errors.append(
                f"P-J/P-L source row {source_row} contract mismatch: {mismatches}"
            )
            continue
        try:
            step = int(row["measurement_step"])
            source_regions = int(row["source_region_count"])
            visible_roof = int(row["oracle_visible_roof_pixel_count"])
            address = int(row["address_pixel_count"])
            alpha_valid = int(row["alpha_valid_pixel_count"])
            depth_valid = int(row["ldepth_valid_pixel_count"])
            joint = int(row["alpha_and_ldepth_valid_pixel_count"])
            alpha_threshold = float(row["alpha_threshold"])
        except (TypeError, ValueError) as exc:
            errors.append(f"P-J/P-L source row {source_row} invalid numeric field: {exc}")
            continue
        if step != active_end:
            errors.append(
                f"P-J/P-L source row {source_row} is not the post-probe step {active_end}"
            )
        retained_present = row.get("retained_region_present")
        if retained_present not in {"true", "false"}:
            errors.append(f"P-J/P-L source row {source_row} retained_region_present is invalid")
        if source_regions < 0 or visible_roof <= 0 or min(address, alpha_valid, depth_valid, joint) < 0:
            errors.append(f"P-J/P-L source row {source_row} has invalid nonnegative counts")
        if (retained_present == "true") != (source_regions > 0):
            errors.append(f"P-J/P-L source row {source_row} retained-region/count mismatch")
        if retained_present == "false" and any(
            value != 0 for value in (address, alpha_valid, depth_valid, joint)
        ):
            errors.append(f"P-J/P-L source row {source_row} zero-region row has nonzero address counts")
        if alpha_valid > address or depth_valid > address or joint > min(alpha_valid, depth_valid):
            errors.append(f"P-J/P-L source row {source_row} count partition is impossible")
        if joint < alpha_valid + depth_valid - address:
            errors.append(f"P-J/P-L source row {source_row} intersection is below set lower bound")
        if not math.isclose(alpha_threshold, 0.5, rel_tol=0.0, abs_tol=1e-12):
            errors.append(f"P-J/P-L source row {source_row} alpha threshold is not 0.5")
        if row.get("depth_mask_present") not in {"true", "false"}:
            errors.append(f"P-J/P-L source row {source_row} depth_mask_present is invalid")
        elif row.get("depth_mask_present") == "false" and (depth_valid != 0 or joint != 0):
            errors.append(
                f"P-J/P-L source row {source_row} missing depth mask has nonzero depth/joint count"
            )
        if errors and any(f"row {source_row} " in error for error in errors):
            continue
        by_building[bid][view_stem] = joint

    summary_rows: list[dict[str, Any]] = []
    classifications: dict[str, str] = {}
    boundary_cases: list[str] = []
    for bid in PI_TARGETS:
        counts = list(by_building[bid].values())
        median = percentile(counts, 0.5)
        view_count = len(counts)
        complete = median is not None and view_count >= PJPL_MIN_VISIBLE_VIEWS
        if not complete:
            errors.append(
                f"P-J/P-L {bid} needs >={PJPL_MIN_VISIBLE_VIEWS} visible post-probe views; "
                f"observed={view_count}"
            )
        classification = (
            "P-J"
            if median is not None and median >= PJPL_VALID_PIXEL_THRESHOLD
            else "P-L" if median is not None else "unclassified"
        )
        boundary_case = bool(
            median is not None
            and PJPL_BOUNDARY_MIN_PIXELS <= median <= PJPL_BOUNDARY_MAX_PIXELS
        )
        classifications[bid] = classification
        if boundary_case:
            boundary_cases.append(bid)
        summary_rows.append(
            {
                "record_type": "pjpl_classification",
                "building_id": bid,
                "pjpl_basis": "post_probe_view_median_alpha_and_existing_ldepth_valid",
                "pjpl_visible_view_count": view_count,
                "pjpl_view_median_valid_pixel_count": "" if median is None else median,
                "pjpl_threshold_pixels": PJPL_VALID_PIXEL_THRESHOLD,
                "pjpl_classification": classification,
                "pjpl_boundary_case": str(boundary_case).lower(),
                "pjpl_boundary_case_range_pixels": (
                    f"{PJPL_BOUNDARY_MIN_PIXELS}..{PJPL_BOUNDARY_MAX_PIXELS}"
                ),
                "pjpl_min_visible_views": PJPL_MIN_VISIBLE_VIEWS,
                "pjpl_lock_status": "locked_after_gate_audit" if complete else "incomplete",
            }
        )
    for bid, initial_count in PJPL_FIXED_PJ_TARGETS.items():
        summary_rows.append(
            {
                "record_type": "pjpl_classification",
                "building_id": bid,
                "pjpl_basis": "preregistered_collapse_target_seed_inventory_and_z_error_lt1m",
                "pjpl_initial_gaussian_count": initial_count,
                "pjpl_visible_view_count": "",
                "pjpl_view_median_valid_pixel_count": "",
                "pjpl_threshold_pixels": "not_applicable_fixed_target",
                "pjpl_classification": "P-J",
                "pjpl_boundary_case": "false",
                "pjpl_boundary_case_range_pixels": (
                    f"{PJPL_BOUNDARY_MIN_PIXELS}..{PJPL_BOUNDARY_MAX_PIXELS}"
                ),
                "pjpl_min_visible_views": "",
                "pjpl_lock_status": "preregistered_fixed",
            }
        )
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "summary_rows": summary_rows,
        "classifications": classifications,
        "boundary_cases": boundary_cases,
        "source_view_rows": sum(len(values) for values in by_building.values()),
    }


def pjpl_summary_values(pjpl: dict[str, Any]) -> dict[str, Any]:
    """Return the preregistered P-J/P-L aggregate fields in one canonical form."""

    return {
        "pjpl_classification_status": pjpl["status"],
        "pjpl_target_classifications": ";".join(
            f"{bid}:{pjpl['classifications'].get(bid, 'unclassified')}"
            for bid in PI_TARGETS
        ),
        "pjpl_boundary_case_buildings": ";".join(pjpl["boundary_cases"]),
        "pjpl_fixed_collapse_pj_targets": ";".join(PJPL_FIXED_PJ_TARGETS),
        "pjpl_source_view_rows": pjpl["source_view_rows"],
    }


def pjpl_attempt1_lock_sha256(
    pjpl: dict[str, Any],
    *,
    source_csv: Path,
    source_csv_sha256: str,
) -> str:
    """Fingerprint only attempt-1 authority fields, independent of later CSV appends."""

    return sha256_json(
        {
            "source_csv": rel(source_csv),
            "source_csv_sha256": source_csv_sha256,
            "summary": pjpl_summary_values(pjpl),
            "classification_rows": sorted(
                pjpl["summary_rows"], key=lambda row: str(row["building_id"])
            ),
        }
    )


def _csv_text(value: Any) -> str:
    return "" if value is None else str(value)


def load_frozen_attempt1_pjpl() -> dict[str, Any]:
    """Rebind half-once classification to committed, hashed attempt-1 evidence.

    Attempt 2 may produce a fresh diagnostic sweep, but that sweep must never
    change the preregistered median, boundary tag, or P-J/P-L classification.
    """

    commit_state = committed_unchanged(CSV_GATE_AUDIT)
    if not commit_state.get("committed_unchanged"):
        raise RuntimeError(
            "half-once P-J/P-L freeze requires the attempt-1 gate CSV committed "
            f"and unchanged: {commit_state}"
        )

    attempt1_config_path = run_name_config_path(GATE_RUN)
    if not attempt1_config_path.is_file():
        raise FileNotFoundError(attempt1_config_path)
    attempt1_config = load_yaml(attempt1_config_path)
    if int(attempt1_config.get("s3_gate_attempt", -1)) != 1:
        raise RuntimeError("attempt-1 freeze source config is not s3_gate_attempt=1")
    attempt1_out_dir = workspace_path_to_host(attempt1_config["out_dir"])
    source_path = attempt1_out_dir / f"audit/{PJPL_VIEW_AUDIT_FILENAME}"
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    source_sha = sha256_file(source_path)
    pjpl = summarize_pjpl_view_rows(
        read_csv(source_path), active_end=GATE_MAX_ITER - 1
    )
    if pjpl["status"] != "pass":
        raise RuntimeError(
            f"attempt-1 frozen P-J/P-L source is invalid: {pjpl['errors']}"
        )

    committed_rows = read_csv(CSV_GATE_AUDIT)
    gate_summaries = [
        row
        for row in committed_rows
        if row.get("run_name") == GATE_RUN and row.get("record_type") == "gate_summary"
    ]
    classification_rows = [
        row
        for row in committed_rows
        if row.get("run_name") == GATE_RUN
        and row.get("record_type") == "pjpl_classification"
    ]
    if len(gate_summaries) != 1:
        raise RuntimeError(
            f"attempt-1 freeze requires exactly one committed gate summary, found {len(gate_summaries)}"
        )
    expected_rows = {
        str(row["building_id"]): row for row in pjpl["summary_rows"]
    }
    actual_rows: dict[str, dict[str, str]] = {}
    for row in classification_rows:
        bid = row.get("building_id", "")
        if bid in actual_rows:
            raise RuntimeError(f"attempt-1 committed P-J/P-L row is duplicated: {bid}")
        actual_rows[bid] = row
    if set(actual_rows) != set(expected_rows):
        raise RuntimeError(
            "attempt-1 committed P-J/P-L building set mismatch: "
            f"observed={sorted(actual_rows)}, expected={sorted(expected_rows)}"
        )

    aggregate = pjpl_summary_values(pjpl)
    lock_sha = pjpl_attempt1_lock_sha256(
        pjpl, source_csv=source_path, source_csv_sha256=source_sha
    )
    expected_summary = {
        **aggregate,
        "pjpl_diagnostic_status": pjpl["status"],
        "pjpl_diagnostic_target_classifications": aggregate[
            "pjpl_target_classifications"
        ],
        "pjpl_diagnostic_boundary_case_buildings": aggregate[
            "pjpl_boundary_case_buildings"
        ],
        "pjpl_diagnostic_source_view_rows": pjpl["source_view_rows"],
        "pjpl_source_csv": rel(source_path),
        "pjpl_source_csv_sha256": source_sha,
        "pjpl_diagnostic_source_csv": rel(source_path),
        "pjpl_diagnostic_source_csv_sha256": source_sha,
        "pjpl_authority": "attempt1_self",
        "pjpl_frozen_from_run": "",
        "pjpl_attempt1_lock_sha256": lock_sha,
    }
    committed_summary = gate_summaries[0]
    summary_mismatches = sorted(
        key
        for key, expected in expected_summary.items()
        if committed_summary.get(key, "") != _csv_text(expected)
    )
    if summary_mismatches:
        raise RuntimeError(
            "attempt-1 committed P-J/P-L summary differs from raw source: "
            f"{summary_mismatches}"
        )
    for bid, expected in expected_rows.items():
        actual = actual_rows[bid]
        mismatches = sorted(
            key
            for key, expected_value in expected.items()
            if actual.get(key, "") != _csv_text(expected_value)
        )
        expected_row_provenance = {
            "source_csv": rel(source_path),
            "pjpl_authority": "attempt1_self",
            "pjpl_frozen_from_run": "",
            "pjpl_attempt1_lock_sha256": lock_sha,
        }
        mismatches.extend(
            key
            for key, expected_value in expected_row_provenance.items()
            if actual.get(key, "") != expected_value
        )
        if mismatches:
            raise RuntimeError(
                f"attempt-1 committed P-J/P-L row {bid} differs from raw source: "
                f"{sorted(set(mismatches))}"
            )
    return {
        "pjpl": pjpl,
        "source_path": source_path,
        "source_sha256": source_sha,
        "lock_sha256": lock_sha,
    }


def expected_audit_steps(start: int, max_iter: int, every: int) -> set[int]:
    steps = set(range(start, max_iter, every))
    steps.add(max_iter - 1)
    return steps


def parse_return_code(path: Path) -> int | None:
    if not path.exists():
        return None
    match = re.search(r"(?:^|\n)RETURN_CODE=(-?\d+)(?:\n|$)", path.read_text(encoding="utf-8", errors="replace"))
    return int(match.group(1)) if match else None


def unique_equals_value(path: Path, key: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    values = re.findall(
        rf"^{re.escape(key)}=(.*)$",
        path.read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    if len(values) != 1:
        raise RuntimeError(f"{rel(path)} must contain exactly one {key}= line, found {len(values)}")
    return values[0].strip()


def unique_colon_value(path: Path, key: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    values = re.findall(
        rf"^{re.escape(key)}:\s*(.*)$",
        path.read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    if len(values) != 1:
        raise RuntimeError(f"{rel(path)} must contain exactly one {key}: line, found {len(values)}")
    return values[0].strip()


def validate_canonical_gate_launch(
    run_name: str,
    config_path: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Bind canonical gate CSVs to one immutable orchestrated training launch."""

    out_dir = workspace_path_to_host(config["out_dir"])
    loss_path = out_dir / "audit/loss_grad_norms.csv"
    semantic_path = out_dir / "audit/semantic_geometry.csv"
    pjpl_path = out_dir / f"audit/{PJPL_VIEW_AUDIT_FILENAME}"
    train_log = TRAIN_LOG_ROOT / f"{run_name}.log"
    version_path = RUN_DIR / "versions" / f"{run_name}.txt"
    for path in (loss_path, semantic_path, pjpl_path, train_log, version_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    current_config_sha = sha256_file(config_path)
    expected_log = {
        "CONFIG": rel(config_path),
        "CONFIG_SHA256": current_config_sha,
        "VERSIONS": rel(version_path),
        "RETURN_CODE": "0",
        "AUDIT_LOSS_CSV": rel(loss_path),
        "AUDIT_LOSS_CSV_SHA256": sha256_file(loss_path),
        "AUDIT_SEMANTIC_CSV": rel(semantic_path),
        "AUDIT_SEMANTIC_CSV_SHA256": sha256_file(semantic_path),
        "AUDIT_PJPL_CSV": rel(pjpl_path),
        "AUDIT_PJPL_CSV_SHA256": sha256_file(pjpl_path),
    }
    log_values = {key: unique_equals_value(train_log, key) for key in expected_log}
    log_mismatches = {
        key: {"actual": log_values[key], "expected": expected}
        for key, expected in expected_log.items()
        if log_values[key] != expected
    }
    if log_mismatches:
        raise RuntimeError(f"canonical gate train-log binding mismatch: {log_mismatches}")

    cache_inventory = cache_inventory_contract(require_complete=True)
    expected_versions = {
        "run_name": run_name,
        "config": rel(config_path),
        "config_sha256": current_config_sha,
        "base_config_sha256": sha256_file(BASE_CONFIG),
        "orchestrator_sha256": sha256_file(SCRIPT_PATH),
        "train_py_sha256": sha256_file(REPO / "src/stage2/train.py"),
        "densification_py_sha256": sha256_file(REPO / "src/stage2/densification.py"),
        "semantic_loss_py_sha256": sha256_file(REPO / "src/stage2/loss/semantic_guided.py"),
        "cache_producer_sha256": sha256_file(CACHE_PRODUCER),
        "cache_manifest_sha256": sha256_file(CACHE_MANIFEST),
        "cache_inventory_sha256": cache_inventory["inventory_sha256"],
        "cache_aggregate_sha256": cache_inventory["aggregate_sha256"],
    }
    version_values = {key: unique_colon_value(version_path, key) for key in expected_versions}
    version_mismatches = {
        key: {"actual": version_values[key], "expected": expected}
        for key, expected in expected_versions.items()
        if version_values[key] != expected
    }
    if version_mismatches:
        raise RuntimeError(f"canonical gate launch-version binding mismatch: {version_mismatches}")

    command = unique_equals_value(train_log, "COMMAND")
    if command != unique_colon_value(version_path, "command"):
        raise RuntimeError("canonical gate command differs between train log and launch versions")
    gpu = unique_colon_value(version_path, "host_gpu_selector")
    if command != shlex.join(train_command(run_name, gpu)[1]):
        raise RuntimeError("canonical gate command no longer matches the locked orchestrator command")

    preflight_path = REPO / unique_colon_value(version_path, "cache_loader_preflight_log")
    preflight_sha = unique_colon_value(version_path, "cache_loader_preflight_sha256")
    if not preflight_path.is_file() or sha256_file(preflight_path) != preflight_sha:
        raise RuntimeError("canonical gate cache preflight log/hash mismatch")
    if unique_equals_value(preflight_path, "RETURN_CODE") != "0":
        raise RuntimeError("canonical gate cache preflight did not return zero")
    preflight_text = preflight_path.read_text(encoding="utf-8", errors="replace")
    json_start = preflight_text.find("{")
    if json_start < 0:
        raise RuntimeError("canonical gate cache preflight JSON is missing")
    preflight_payload = json.loads(preflight_text[json_start:])
    if (
        preflight_payload.get("status") != "pass"
        or int(preflight_payload.get("validated_files", -1)) != 428
        or preflight_payload.get("cache_aggregate_sha256") != cache_inventory["aggregate_sha256"]
    ):
        raise RuntimeError("canonical gate cache preflight payload is incomplete or stale")

    launch_git_head = unique_colon_value(version_path, "git_head")
    if launch_git_head != capture(["git", "rev-parse", "HEAD"]):
        raise RuntimeError("git HEAD changed between canonical gate launch and gate audit")
    return {
        "loss_path": loss_path,
        "semantic_path": semantic_path,
        "pjpl_path": pjpl_path,
        "train_log": train_log,
        "version_path": version_path,
        "launch_git_head": launch_git_head,
        "train_log_sha256": sha256_file(train_log),
        "launch_versions_sha256": sha256_file(version_path),
        "cache_preflight_log": preflight_path,
        "cache_preflight_log_sha256": preflight_sha,
        **expected_versions,
    }


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
    *,
    require_unit_share: bool = True,
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
            or grad_share < 0.0
            or (require_unit_share and grad_share > 1.0)
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
        primary_norms = [finite_number(row.get("grad_norm")) for row in primary]
        if not primary_norms or any(value is None or value < 0.0 for value in primary_norms):
            reasons.append(f"step {step} primary grad_norm values are invalid")
            continue
        denominator = sum(float(value) for value in primary_norms if value is not None)
        if denominator <= 0.0:
            reasons.append(f"step {step} primary gradient denominator is not positive")
            continue
        primary_shares: list[float] = []
        for row, norm in zip(primary, primary_norms):
            reported = finite_number(row.get("grad_norm_share"))
            expected_share = float(norm) / denominator  # type: ignore[arg-type]
            if reported is None or not math.isclose(
                reported, expected_share, rel_tol=1e-6, abs_tol=1e-9
            ):
                reasons.append(
                    f"step {step} {row.get('component')} grad share does not match primary norms"
                )
            else:
                primary_shares.append(reported)
        if len(primary_shares) == len(primary) and not math.isclose(
            sum(primary_shares), 1.0, rel_tol=1e-6, abs_tol=1e-9
        ):
            reasons.append(f"step {step} primary grad shares do not sum to one")
        for row in part:
            if row.get("denominator_role") != "audit_only":
                continue
            norm = finite_number(row.get("grad_norm"))
            reported = finite_number(row.get("grad_norm_share"))
            if norm is None or norm < 0.0 or reported is None or reported < 0.0 or not math.isclose(
                reported, norm / denominator, rel_tol=1e-6, abs_tol=1e-9
            ):
                reasons.append(
                    f"step {step} {row.get('component')} audit-only share does not match primary denominator"
                )
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
                    **row,
                    "run_name": run_name,
                    "record_type": record_type,
                    "source_csv": rel(source_path),
                    "source_row": source_row_index,
                    "active": 1,
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
    attempt = int(config.get("s3_gate_attempt", -1))
    if attempt not in {1, 2}:
        raise RuntimeError(f"gate audit accepts only s3_gate_attempt 1 or 2, got {attempt}")
    if max_iter != GATE_MAX_ITER or active_start != ACTIVE_START:
        raise RuntimeError(
            f"gate config must have max_iter={GATE_MAX_ITER}, warmup={ACTIVE_START}; "
            f"got {max_iter}/{active_start}"
        )
    out_dir = Path(str(config["out_dir"]).replace("/workspace/JointBuildGS", str(REPO), 1))
    override_values = [
        args.loss_csv,
        args.semantic_csv,
        args.pjpl_csv,
        args.train_log,
        args.output,
    ]
    if args.test_mode:
        if not all(override_values):
            raise RuntimeError(
                "--test-mode requires explicit --loss-csv, --semantic-csv, --pjpl-csv, "
                "--train-log, and --output"
            )
        loss_path = Path(args.loss_csv).resolve()
        semantic_path = Path(args.semantic_csv).resolve()
        pjpl_path = Path(args.pjpl_csv).resolve()
        train_log = Path(args.train_log).resolve()
        output_path = Path(args.output).resolve()
        if output_path == CSV_GATE_AUDIT.resolve():
            raise RuntimeError("--test-mode may not write the canonical gate audit CSV")
        launch_evidence: dict[str, Any] = {}
        evidence_scope = "test_only"
    else:
        if any(override_values):
            raise RuntimeError(
                "canonical gate-audit forbids path overrides; use --test-mode with all five paths"
            )
        launch_evidence = validate_canonical_gate_launch(args.run_name, config_path, config)
        loss_path = launch_evidence["loss_path"]
        semantic_path = launch_evidence["semantic_path"]
        pjpl_path = launch_evidence["pjpl_path"]
        train_log = launch_evidence["train_log"]
        output_path = CSV_GATE_AUDIT
        evidence_scope = "canonical"
        existing_same_run = [
            row for row in read_csv(output_path) if row.get("run_name") == args.run_name
        ]
        if existing_same_run:
            raise RuntimeError(
                f"canonical gate evidence is create-only; {args.run_name} already has "
                f"{len(existing_same_run)} rows in {rel(output_path)}"
            )
    for path in (loss_path, semantic_path, pjpl_path):
        if not path.exists():
            raise FileNotFoundError(path)
    loss_rows = read_csv(loss_path)
    semantic_rows = read_csv(semantic_path)
    pjpl_rows = read_csv(pjpl_path)
    if not loss_rows or not semantic_rows:
        raise RuntimeError("loss and semantic gate audit CSV inputs must contain data rows")
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
    denominator_reasons = validate_denominator_contract(
        loss_rows, expected_generic & observed_generic
    )
    reasons.extend(denominator_reasons)

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
        require_unit_share=False,
    )
    plane_rows_complete = component_audit_complete(
        plane_rows,
        expected_component_rows,
        float(config["w_semdepth_plane"]),
        require_unit_share=False,
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

    pjpl_diagnostic = summarize_pjpl_view_rows(pjpl_rows, active_end=active_end)
    if pjpl_diagnostic["status"] != "pass":
        reasons.extend(
            f"attempt-{attempt} diagnostic P-J/P-L sweep: {error}"
            for error in pjpl_diagnostic["errors"]
        )
    if attempt == 1:
        pjpl = pjpl_diagnostic
        pjpl_source_path = pjpl_path
        pjpl_source_sha = sha256_file(pjpl_path)
        pjpl_authority = "attempt1_self"
        pjpl_frozen_from_run = ""
        pjpl_lock_sha = pjpl_attempt1_lock_sha256(
            pjpl,
            source_csv=pjpl_source_path,
            source_csv_sha256=pjpl_source_sha,
        )
    else:
        frozen = load_frozen_attempt1_pjpl()
        pjpl = frozen["pjpl"]
        pjpl_source_path = frozen["source_path"]
        pjpl_source_sha = frozen["source_sha256"]
        pjpl_authority = "attempt1_frozen"
        pjpl_frozen_from_run = GATE_RUN
        pjpl_lock_sha = frozen["lock_sha256"]
    pjpl_complete = (
        pjpl["status"] == "pass" and pjpl_diagnostic["status"] == "pass"
    )

    gate_pass = (
        not missing_generic
        and not missing_semantic
        and not denominator_reasons
        and total_finite_pass
        and semdepth_pass
        and boundary_pass
        and detail_pass
        and pi_all_pass
        and pjpl_complete
    )
    semdepth_over_threshold = bool(
        not denominator_reasons
        and semdepth_rows_complete
        and stats["semdepth"]["max"] is not None
        and stats["semdepth"]["max"] > GRAD_SHARE_MAX
    )
    boundary_over_threshold = bool(
        not denominator_reasons
        and boundary_rows_complete
        and stats["boundary_normal"]["max"] is not None
        and stats["boundary_normal"]["max"] > GRAD_SHARE_MAX
    )
    suggested_semdepth_scale = 0.5 if attempt == 1 and semdepth_over_threshold else 1.0
    suggested_nb_scale = (
        0.5 if attempt == 1 and boundary_over_threshold else 1.0
    )
    regate_command = ""
    if attempt == 1 and (suggested_semdepth_scale == 0.5 or suggested_nb_scale == 0.5):
        regate_command = (
            "python scripts/e5_c001/e5_c001_s3_semantic_guided.py "
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
    for source_row, row in enumerate(pjpl_rows, start=2):
        normalized.append(
            {
                **row,
                "run_name": args.run_name,
                "record_type": (
                    "pjpl_view_measurement"
                    if attempt == 1
                    else "pjpl_view_measurement_diagnostic"
                ),
                "step": row.get("measurement_step", ""),
                "source_csv": rel(pjpl_path),
                "source_row": source_row,
                "active": 1,
                "pjpl_authority": (
                    "attempt1_self" if attempt == 1 else "attempt2_diagnostic_only"
                ),
                "pjpl_frozen_from_run": pjpl_frozen_from_run,
                "pjpl_attempt1_lock_sha256": pjpl_lock_sha,
            }
        )
    normalized.extend(
        {
            **row,
            "run_name": args.run_name,
            "active": 1,
            "source_csv": rel(pjpl_source_path),
            "pjpl_authority": pjpl_authority,
            "pjpl_frozen_from_run": pjpl_frozen_from_run,
            "pjpl_attempt1_lock_sha256": pjpl_lock_sha,
        }
        for row in pjpl["summary_rows"]
    )
    normalized.extend(pi_rows)
    normalized.append(
        {
            "run_name": args.run_name,
            "record_type": "gate_summary",
            "evidence_scope": evidence_scope,
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
            "pjpl_classification_status": pjpl["status"],
            "pjpl_diagnostic_status": pjpl_diagnostic["status"],
            "pjpl_target_rule": (
                "median_over_visible_training_views(alpha>=0.5 AND existing_L_depth_valid) "
                f">={PJPL_VALID_PIXEL_THRESHOLD} => P-J; "
                f"<{PJPL_VALID_PIXEL_THRESHOLD} => P-L"
            ),
            "pjpl_boundary_case_rule": (
                f"{PJPL_BOUNDARY_MIN_PIXELS}<=median<={PJPL_BOUNDARY_MAX_PIXELS}"
            ),
            "pjpl_min_visible_views": PJPL_MIN_VISIBLE_VIEWS,
            "pjpl_target_classifications": ";".join(
                f"{bid}:{pjpl['classifications'].get(bid, 'unclassified')}"
                for bid in PI_TARGETS
            ),
            "pjpl_diagnostic_target_classifications": ";".join(
                f"{bid}:{pjpl_diagnostic['classifications'].get(bid, 'unclassified')}"
                for bid in PI_TARGETS
            ),
            "pjpl_boundary_case_buildings": ";".join(pjpl["boundary_cases"]),
            "pjpl_diagnostic_boundary_case_buildings": ";".join(
                pjpl_diagnostic["boundary_cases"]
            ),
            "pjpl_fixed_collapse_pj_targets": ";".join(PJPL_FIXED_PJ_TARGETS),
            "pjpl_source_view_rows": pjpl["source_view_rows"],
            "pjpl_diagnostic_source_view_rows": pjpl_diagnostic["source_view_rows"],
            "pjpl_authority": pjpl_authority,
            "pjpl_frozen_from_run": pjpl_frozen_from_run,
            "pjpl_attempt1_lock_sha256": pjpl_lock_sha,
            "gate_status": "pass" if gate_pass else "fail",
            "gate_reasons": "; ".join(dict.fromkeys(reasons)),
            "gate_attempt": attempt,
            "effective_semdepth_scale": config["s3_semdepth_scale"],
            "effective_nb_scale": config["s3_nb_scale"],
            "effective_w_semdepth_smooth": config["w_semdepth_smooth"],
            "effective_w_semdepth_plane": config["w_semdepth_plane"],
            "effective_w_boundary_normal": config["w_boundary_normal"],
            "semdepth_over_threshold": str(semdepth_over_threshold).lower(),
            "boundary_normal_over_threshold": str(boundary_over_threshold).lower(),
            "suggested_semdepth_scale": suggested_semdepth_scale,
            "suggested_nb_scale": suggested_nb_scale,
            "regate_config_command_not_executed": regate_command,
            "config": rel(config_path),
            "config_sha256": sha256_file(config_path),
            "loss_source_csv": rel(loss_path),
            "loss_source_csv_sha256": sha256_file(loss_path),
            "semantic_source_csv": rel(semantic_path),
            "semantic_source_csv_sha256": sha256_file(semantic_path),
            "pjpl_source_csv": rel(pjpl_source_path),
            "pjpl_source_csv_sha256": pjpl_source_sha,
            "pjpl_diagnostic_source_csv": rel(pjpl_path),
            "pjpl_diagnostic_source_csv_sha256": sha256_file(pjpl_path),
            "train_log": rel(train_log),
            "train_log_sha256": sha256_file(train_log),
            "launch_versions": (
                rel(launch_evidence["version_path"]) if launch_evidence else ""
            ),
            "launch_versions_sha256": launch_evidence.get("launch_versions_sha256", ""),
            "launch_git_head": launch_evidence.get("launch_git_head", ""),
            "orchestrator_sha256": launch_evidence.get("orchestrator_sha256", ""),
            "train_py_sha256": launch_evidence.get("train_py_sha256", ""),
            "densification_py_sha256": launch_evidence.get("densification_py_sha256", ""),
            "semantic_loss_py_sha256": launch_evidence.get("semantic_loss_py_sha256", ""),
            "cache_producer_sha256": launch_evidence.get("cache_producer_sha256", ""),
            "cache_manifest_sha256": launch_evidence.get("cache_manifest_sha256", ""),
            "cache_inventory_sha256": launch_evidence.get("cache_inventory_sha256", ""),
            "cache_aggregate_sha256": launch_evidence.get("cache_aggregate_sha256", ""),
            "cache_preflight_log": (
                rel(launch_evidence["cache_preflight_log"]) if launch_evidence else ""
            ),
            "cache_preflight_log_sha256": launch_evidence.get(
                "cache_preflight_log_sha256", ""
            ),
            "grad_share_sampling": (
                f"sampled max at {generic_every}-update cadence plus final; "
                "nonfinite_loss.jsonl covers all updates"
            ),
            "denominator_contract": "combined semdepth and boundary_normal are primary once; smooth/plane are audit_only",
            "judgment_scope": "mechanical preregistered gate fields only; human verdict excluded",
        }
    )
    # Canonical evidence is create-only. Test-only output may be regenerated in
    # an explicitly separate path, while other run rows remain intact.
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
                "pjpl_classification_status": summary["pjpl_classification_status"],
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
    subparsers.add_parser("sync-full-configs-from-gate")

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
    audit.add_argument("--pjpl-csv")
    audit.add_argument("--train-log")
    audit.add_argument("--output")
    audit.add_argument("--test-mode", action="store_true")

    cache = subparsers.add_parser("check-cache")
    cache.add_argument("--loader-preflight", action="store_true")
    cache.add_argument("--limit", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "generate-configs":
        generate_configs(args)
    elif args.command == "sync-full-configs-from-gate":
        sync_full_configs_from_gate(args)
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
