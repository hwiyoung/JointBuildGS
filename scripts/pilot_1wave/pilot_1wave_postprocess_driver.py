#!/usr/bin/env python3
"""Reproducible, resumable host orchestrator for the P1W 20k read-out.

The program performs orchestration only.  Geometry extraction, classification,
Roofer preparation/finalization, scoring, loss aggregation, and the binding
audit always run in their pinned Docker images.  The scientific programs are
not imported here.

Execution is deliberately barriered:

    ten 20k extracts (serial, seed-pinned across two GPUs) -> one locked roofprint
    -> ten classifications
    -> ten Roofer preparations -> ten exact-once retained Roofer containers
    -> ten finalizations -> ten scores -> numeric aggregate
    -> loss-cursor aggregate + binding batch -> manifest-last publication

The driver never launches Wave 2.  It records ``blocked_missing_wave2_lock``
unless the operator supplies a separately committed lock file and its exact
SHA256; even then the status is only ``external_wave2_lock_verified``.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence, TextIO


REPO = Path(__file__).resolve().parents[3]
SOURCE_RUN_ID = "20260721_pilot_1wave"
READOUT_RUN_ID = "20260722_pilot_1wave_readout"
SOURCE_RUN = REPO / "phases/p2-gsjso/runs" / SOURCE_RUN_ID
TRAINING_ROOT = SOURCE_RUN / "training"
POSTPROCESS_ROOT = TRAINING_ROOT / "postprocess"
POSTPROCESS_FAILED_ATTEMPTS_ROOT = TRAINING_ROOT / "postprocess_failed_attempts"
ATTEMPTS_ROOT = POSTPROCESS_ROOT / "attempts"
PUBLICATION_ROOT = REPO / "phases/p2-gsjso/runs" / READOUT_RUN_ID
CONTAINER_REPO = Path("/workspace/JointBuildGS")

DRIVER_SCHEMA = "jointbuildgs.pilot_1wave.postprocess_driver.v1"
STAGE_MARKER_SCHEMA = "jointbuildgs.pilot_1wave.postprocess_stage.v1"
PUBLICATION_SCHEMA = "jointbuildgs.pilot_1wave.readout_manifest.v1"
PUBLICATION_SNAPSHOT_SCHEMA = (
    "jointbuildgs.pilot_1wave.publication_snapshot.v1"
)
BINDING_SPEC_SCHEMA = "jointbuildgs.pilot_1wave.binding_batch_spec.v1"
FINAL_PREFLIGHT_PROVENANCE_KEYS = (
    "committed_runtime_sources", "crop_lock", "gsplat_extension",
    "gpu_device_probe", "extract_policy_lock",
)

DEV_IMAGE_TAG = "jointbuildgs:dev"
DEV_IMAGE_ID = (
    "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
)
P0_IMAGE_TAG = "jointbuildgs-p0-tools:t0"
P0_IMAGE_ID = (
    "sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
)
ROOFER_IMAGE = (
    "3dgi/roofer@sha256:"
    "dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
)
ROOFER_IMAGE_ID = (
    "sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
)
TRAINING_RUNTIME_HEAD = "d43e64e27ec279dd304a9a7d30b19c6e5c33a429"

PILOT_SET_SHA256 = (
    "db5ecb6c838499dd3a5f96a4b1abae85414c3d38318d976b7ee598982b566ffc"
)
PILOT_MANIFEST_SHA256 = (
    "803d18862db926fff353c641e08a03c5938cedf3fb49cc4859751189e83855e2"
)
SELECTION_SHA256 = (
    "e98daa670a0753198e8a54502b260a07bcefe2bca42976931c0a08b766c5b3cd"
)
ORDERED_IDS_SHA256 = (
    "ae5cbc664941c3b8bb4238767f1d0833a1f7684928a03837047065f85093bb01"
)
FOOTPRINT_SHA256 = (
    "ca7f5b13a52368e1d2ac47b77cc78f12887bad4d598d122ad57b882eb4920a82"
)
INVENTORY_SHA256 = (
    "30a3387275ee9ed29ad75bbdf7cb1979f2b8b2cd52640225e9dbe00895666450"
)
INVENTORY_RECORDS_SHA256 = (
    "b99c38d31b37b59f1827537e520c20c76ca5a0ee0bfbc5baaaa879d4fff57271"
)
CROP_BBOX = (690764.89, 5335918.4, 690964.53, 5336202.0)
CROP_AREA_M2 = 56_617.904
VIEW_COUNT = 481
EXPECTED_STEPS = 20_000
EXPECTED_SEEDS = (1001, 1002)
CONDITIONS = ("01", "02", "03", "04a", "04b")
HONEST_CONDITIONS = ("01", "02", "03", "04a")
EXPECTED_IDS = (
    "DEBY_LOD2_4906966",
    "DEBY_LOD2_4907178",
    "DEBY_LOD2_4907183",
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907185",
    "DEBY_LOD2_4907186",
    "DEBY_LOD2_4907188",
    "DEBY_LOD2_4907195",
    "DEBY_LOD2_4907196",
    "DEBY_LOD2_4907198",
    "DEBY_LOD2_4907201",
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4907204",
    "DEBY_LOD2_4907205",
    "DEBY_LOD2_4907206",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_60098",
    "DEBY_LOD2_4907207",
    "DEBY_LOD2_4907165",
    "DEBY_LOD2_4907177",
    "DEBY_LOD2_4907179",
    "DEBY_LOD2_42364665",
    "DEBY_LOD2_4906965",
    "DEBY_LOD2_42364667",
    "DEBY_LOD2_4907176",
    "DEBY_LOD2_4907180",
    "DEBY_LOD2_4906967",
    "DEBY_LOD2_4908023",
    "DEBY_LOD2_4908024",
)

PILOT_SET = SOURCE_RUN / "pilot_1wave_pilot_set.csv"
PILOT_MANIFEST = SOURCE_RUN / "pilot_1wave_pilot_set_manifest.json"
FOOTPRINT_SOURCE = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
INVENTORY = SOURCE_RUN / "calibration/scaffolds/materialized_input_inventory.json"
PREP_MANIFEST = SOURCE_RUN / "prep_artifacts/prep_manifest.json"
RESOLVED_MANIFEST = TRAINING_ROOT / "resolved_configs/resolved_configs_manifest.json"
TRAINING_DRIVER_MANIFEST = TRAINING_ROOT / "pilot_1wave_driver_manifest.json"
EXTRACT_POLICY_LOCK = (
    REPO / "phases/p2-gsjso/configs/pilot_1wave/pilot_1wave_postprocess_extract_policy_lock.json"
)
EXTRACT_POLICY_LOCK_SHA256 = (
    "ac7d5210b59ac04d5aeb7e853ed93514f1178308a771923f02ccaa33554155c7"
)
EXTRACT_POLICY_SCHEMA = "jointbuildgs.pilot_1wave.extract_policy_lock.v1"
EXTRACT_CONTAINER_MEMORY = "24g"
EXTRACT_CONTAINER_MEMORY_BYTES = 24 * 1024**3

EXTRACTOR = REPO / "scripts/e5_c001/p2_gsjso/e5_c001_readout_extract_ablation.py"
CLASSIFIER = REPO / "scripts/pilot_1wave/pilot_1wave_scene_classify.py"
SCORING = REPO / "scripts/pilot_1wave/pilot_1wave_scoring.py"
LOSS_AGGREGATE = REPO / "scripts/pilot_1wave/pilot_1wave_loss_cursor_aggregate.py"
BINDING_AUDIT = REPO / "scripts/pilot_1wave/pilot_1wave_binding_audit.py"

GSPLAT_RUNTIME = REPO / "results/tum_transfer/e5_s3ap_phase2/runtime"
GSPLAT_EXTENSION = GSPLAT_RUNTIME / "torch_extensions/gsplat_cuda/gsplat_cuda.so"
GSPLAT_EXTENSION_SHA256 = (
    "b291971546d350951760d34863ff96068c8ef018dcdeaaf0d61ec21471baadd5"
)
REQUIRED_COMMITTED_PATHS = (
    Path("phases/p2-gsjso/configs/pilot_1wave/pilot_1wave_postprocess_extract_policy_lock.json"),
    Path("scripts/pilot_1wave/pilot_1wave_postprocess_driver.py"),
    Path("scripts/e5_c001/p2_gsjso/e5_c001_readout_extract_ablation.py"),
    Path("scripts/pilot_1wave/pilot_1wave_readout_lineage.py"),
    Path("scripts/pilot_1wave/pilot_1wave_scene_classify.py"),
    Path("scripts/pilot_1wave/pilot_1wave_scoring.py"),
    Path("scripts/pilot_1wave/pilot_1wave_loss_cursor_aggregate.py"),
    Path("scripts/pilot_1wave/pilot_1wave_binding_audit.py"),
)

FIXED_ROOFER_PARAMETERS = (
    "--id-attribute",
    "building_id",
    "--jobs",
    "3",
    "--srs",
    "EPSG:25832",
    "--bld-class",
    "6",
    "--grnd-class",
    "2",
    "--lod22",
)

SCORE_OUTPUTS = (
    "pilot_1wave_scores.csv",
    "pilot_1wave_summary.csv",
    "pilot_1wave_seg_upperbound_gap.csv",
    "pilot_1wave_winner.csv",
)
LOSS_OUTPUT_NAME = "pilot_1wave_loss_shares.csv"
LOSS_RECEIPT_NAME = "pilot_1wave_loss_shares_receipt.json"
LOSS_OUTPUT_FIELDS = (
    "schema_version", "condition_id", "seed", "checkpoint_step",
    "checkpoint_sha256", "iter", "term", "raw", "weighted", "share",
    "roof_share",
)
LOSS_RUN_RECEIPT_OUTPUTS = tuple(
    f"loss_share_receipts/{condition}_seed{seed}.json"
    for condition in CONDITIONS
    for seed in EXPECTED_SEEDS
)
PUBLISH_ALLOWLIST = (
    "pilot_1wave_pilot_set.csv",
    "pilot_1wave_pilot_set_manifest.json",
    "pilot_1wave_selection_lock.json",
    "pilot_1wave_ordered_30_ids.txt",
    "pilot_1wave_locked_roofprints.geojson",
    *SCORE_OUTPUTS,
    LOSS_OUTPUT_NAME,
    LOSS_RECEIPT_NAME,
    *LOSS_RUN_RECEIPT_OUTPUTS,
    "binding_audit.csv",
    "binding_audit_spatial_matrix.csv",
    "binding_audit_receipt.json",
    "pilot_1wave_scoring_manifest.json",
    "pilot_1wave_machine_gates.json",
    "pilot_1wave_postprocess_receipt.json",
)
FINAL_MANIFEST_NAME = "pilot_1wave_manifest.json"


class DriverError(RuntimeError):
    """A fail-closed P1W postprocess contract violation."""


@dataclass(frozen=True)
class Job:
    sequence: int
    condition: str
    seed: int
    job_id: str
    run_dir: Path
    config_path: Path
    config_sha256: str
    full_state_manifest: Path
    checkpoint: Path
    checkpoint_sha256: str

    @property
    def gpu(self) -> int:
        return 0 if self.seed == 1001 else 1


@dataclass(frozen=True)
class CompletedRun:
    job: Job
    extract_dir: Path
    classify_dir: Path
    roofer_dir: Path
    score_dir: Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriverError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DriverError(f"JSON root must be an object: {path}")
    return value


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_bytes(path, json.dumps(
        value, ensure_ascii=False, indent=2, allow_nan=False
    ).encode("utf-8") + b"\n")


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise DriverError(f"refusing symlink output: {path}")
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o644)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise DriverError(f"path escapes repository: {path}") from exc


def container_path(path: Path) -> str:
    return str(CONTAINER_REPO / repo_relative(path))


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise DriverError(f"{label} mismatch: {actual!r} != {expected!r}")


def require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise DriverError(f"{label} is missing/non-regular: {path}")
    require_equal(sha256_file(path), expected, f"{label} SHA256")


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def run_host(
    command: Sequence[str],
    *,
    cwd: Path = REPO,
    check: bool = True,
    stdout: TextIO | int | None = subprocess.PIPE,
    stderr: TextIO | int | None = subprocess.PIPE,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=stdout,
        stderr=stderr,
        check=False,
    )
    if check and process.returncode != 0:
        raise DriverError(
            f"command failed exit={process.returncode}: {shlex.join(command)}\n"
            f"stdout={process.stdout or ''}\nstderr={process.stderr or ''}"
        )
    return process


def query_git_head(repo: Path = REPO) -> str:
    value = run_host(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise DriverError(f"unexpected git HEAD: {value!r}")
    return value


def require_clean_tracked_tree(repo: Path = REPO) -> None:
    process = run_host(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"], cwd=repo
    )
    lines = [line for line in process.stdout.splitlines() if line]
    if lines:
        raise DriverError("tracked worktree is not clean: " + " | ".join(lines))


def require_committed_runtime(expected_head: str, repo: Path = REPO) -> dict[str, str]:
    if re.fullmatch(r"[0-9a-f]{40}", expected_head) is None:
        raise DriverError("--correction-head must be an exact 40-character commit")
    require_equal(query_git_head(repo), expected_head, "correction commit HEAD")
    require_clean_tracked_tree(repo)
    records: dict[str, str] = {}
    for relative in REQUIRED_COMMITTED_PATHS:
        path = repo / relative
        if not path.is_file() or path.is_symlink():
            raise DriverError(f"required runtime path is missing/non-regular: {relative}")
        tracked = run_host(
            ["git", "ls-files", "--error-unmatch", str(relative)], cwd=repo, check=False
        )
        if tracked.returncode != 0:
            raise DriverError(f"runtime path is not committed at HEAD: {relative}")
        blob = run_host(["git", "rev-parse", f"HEAD:{relative}"], cwd=repo).stdout.strip()
        worktree_blob = run_host(["git", "hash-object", str(relative)], cwd=repo).stdout.strip()
        require_equal(worktree_blob, blob, f"committed runtime blob {relative}")
        records[str(relative)] = sha256_file(path)
    return records


def query_image_id(reference: str) -> str:
    value = run_host(
        ["docker", "image", "inspect", "--format", "{{.Id}}", reference]
    ).stdout.strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise DriverError(f"unexpected image ID for {reference}: {value!r}")
    return value


def require_images() -> dict[str, dict[str, str]]:
    expected = {
        DEV_IMAGE_TAG: DEV_IMAGE_ID,
        P0_IMAGE_TAG: P0_IMAGE_ID,
        ROOFER_IMAGE: ROOFER_IMAGE_ID,
    }
    records: dict[str, dict[str, str]] = {}
    for reference, image_id in expected.items():
        require_equal(query_image_id(reference), image_id, f"image ID {reference}")
        records[reference] = {"reference": reference, "image_id": image_id}
    repo_digests = run_host(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ROOFER_IMAGE]
    ).stdout.strip()
    try:
        digests = json.loads(repo_digests)
    except json.JSONDecodeError as exc:
        raise DriverError("Roofer RepoDigests is not JSON") from exc
    if ROOFER_IMAGE not in (digests or []):
        raise DriverError("local Roofer image lacks the pinned RepoDigest")
    records[ROOFER_IMAGE]["repo_digest"] = ROOFER_IMAGE
    return records


def _resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise DriverError(f"invalid declared path in {declaring_file}: {value!r}")
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            relative = candidate.relative_to(CONTAINER_REPO)
        except ValueError:
            resolved = candidate.resolve()
        else:
            resolved = (REPO / relative).resolve()
    else:
        resolved = (REPO / candidate).resolve()
    repo_relative(resolved)
    return resolved


def validate_crop_locks() -> dict[str, Any]:
    require_sha(PILOT_SET, PILOT_SET_SHA256, "pilot CSV")
    require_sha(PILOT_MANIFEST, PILOT_MANIFEST_SHA256, "pilot manifest")
    require_sha(FOOTPRINT_SOURCE, FOOTPRINT_SHA256, "footprint source")
    require_sha(INVENTORY, INVENTORY_SHA256, "materialized inventory")

    with PILOT_SET.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    require_equal(len(rows), 30, "pilot CSV row count")
    require_equal(
        tuple(row.get("building_id", "") for row in rows), EXPECTED_IDS,
        "pilot ordered IDs",
    )
    require_equal(
        tuple(int(row.get("selection_rank", -1)) for row in rows),
        tuple(range(1, 31)),
        "pilot ranks",
    )
    for row in rows:
        bbox = tuple(float(row[name]) for name in (
            "training_crop_aoi_minx", "training_crop_aoi_miny",
            "training_crop_aoi_maxx", "training_crop_aoi_maxy",
        ))
        require_equal(bbox, CROP_BBOX, f"pilot CSV crop {row['building_id']}")

    manifest = load_json(PILOT_MANIFEST)
    selection = manifest.get("selection")
    if not isinstance(selection, Mapping):
        raise DriverError("pilot manifest selection is missing")
    require_equal(selection.get("selection_count"), 30, "selection count")
    require_equal(tuple(selection.get("selected_ids_in_rank_order", [])), EXPECTED_IDS,
                  "manifest ordered IDs")
    require_equal(selection.get("selection_sha256"), SELECTION_SHA256, "selection SHA")
    require_equal(selection.get("ordered_ids_sha256"), ORDERED_IDS_SHA256,
                  "ordered IDs SHA")
    require_equal(tuple(float(x) for x in selection.get("training_crop_bbox", [])),
                  CROP_BBOX, "manifest crop bbox")

    inventory = load_json(INVENTORY)
    require_equal(inventory.get("schema"),
                  "jointbuildgs.pilot_1wave.materialized_input_inventory.v1",
                  "inventory schema")
    require_equal(inventory.get("records_sha256"), INVENTORY_RECORDS_SHA256,
                  "inventory records SHA")
    require_equal(int(inventory.get("view_count", -1)), VIEW_COUNT,
                  "inventory view count")
    view_ids = inventory.get("view_ids")
    if not isinstance(view_ids, list):
        raise DriverError("inventory view_ids is missing")
    require_equal(len(view_ids), VIEW_COUNT, "inventory view ID count")
    require_equal(len(set(str(x) for x in view_ids)), VIEW_COUNT,
                  "inventory unique view IDs")
    records = inventory.get("records")
    if not isinstance(records, list):
        raise DriverError("materialized inventory records are missing")
    require_equal(len(records), 1_927, "materialized inventory file count")
    require_equal(sha256_bytes(canonical_json(records)), INVENTORY_RECORDS_SHA256,
                  "recomputed inventory records SHA")
    checked_bytes = 0
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise DriverError(f"inventory record {index} is not an object")
        path = (REPO / str(record.get("path", ""))).resolve()
        repo_relative(path)
        if not path.is_file() or path.is_symlink():
            raise DriverError(f"inventory file {index} is missing/non-regular: {path}")
        size = path.stat().st_size
        require_equal(size, int(record.get("size_bytes", -1)),
                      f"inventory file {index} size")
        require_equal(sha256_file(path), record.get("sha256"),
                      f"inventory file {index} SHA")
        checked_bytes += size
    require_equal(checked_bytes, int(inventory.get("total_bytes", -1)),
                  "materialized inventory total bytes")

    prep = load_json(PREP_MANIFEST)
    require_equal(tuple(float(x) for x in prep.get("training_crop_bbox_utm", [])),
                  CROP_BBOX, "prep crop bbox")
    require_equal(prep.get("score_building_ids_rank_order"), list(EXPECTED_IDS),
                  "prep ordered IDs")
    require_equal(
        int((prep.get("view_source_inventory") or {}).get("selected_view_count", -1)),
        VIEW_COUNT,
        "prep view count",
    )
    area = (CROP_BBOX[2] - CROP_BBOX[0]) * (CROP_BBOX[3] - CROP_BBOX[1])
    if abs(area - CROP_AREA_M2) > 1e-6:
        raise DriverError(f"crop area drift: {area} != {CROP_AREA_M2}")
    return {
        "pilot_set_sha256": PILOT_SET_SHA256,
        "pilot_manifest_sha256": PILOT_MANIFEST_SHA256,
        "selection_sha256": SELECTION_SHA256,
        "ordered_ids_sha256": ORDERED_IDS_SHA256,
        "footprint_sha256": FOOTPRINT_SHA256,
        "inventory_sha256": INVENTORY_SHA256,
        "inventory_records_sha256": INVENTORY_RECORDS_SHA256,
        "building_count": 30,
        "view_count": VIEW_COUNT,
        "checked_file_count": len(records),
        "checked_total_bytes": checked_bytes,
        "file_mismatch_count": 0,
        "crop_bbox": list(CROP_BBOX),
        "crop_area_m2": CROP_AREA_M2,
    }


def _job_order() -> tuple[tuple[str, int], ...]:
    return tuple((condition, seed) for condition in CONDITIONS for seed in EXPECTED_SEEDS)


def historical_postprocess_attempt_records(
    root: Path = POSTPROCESS_FAILED_ATTEMPTS_ROOT,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not root.is_dir():
        return records
    for archive in sorted(root.iterdir()):
        if archive.is_symlink() or not archive.is_dir():
            raise DriverError(
                "historical postprocess archive is not a regular directory: "
                f"{archive}"
            )
        state_path = archive / "driver_state.json"
        if state_path.is_symlink() or not state_path.is_file():
            raise DriverError(
                f"historical postprocess archive lacks driver_state.json: {archive}"
            )
        archived_state = load_json(state_path)
        require_equal(archived_state.get("schema"), DRIVER_SCHEMA,
                      f"historical postprocess archive {archive.name} schema")
        require_equal(archived_state.get("state"), "aborted",
                      f"historical postprocess archive {archive.name} state")
        correction_head = str(archived_state.get("correction_head", ""))
        if re.fullmatch(r"[0-9a-f]{40}", correction_head) is None:
            raise DriverError(
                f"historical postprocess archive has invalid correction HEAD: {archive}"
            )
        abort_events = archived_state.get("abort_events")
        if not isinstance(abort_events, list) or not abort_events:
            raise DriverError(
                f"historical postprocess archive has no abort event: {archive}"
            )
        records.append({
            "name": archive.name,
            "path": repo_relative(archive),
            "correction_head": correction_head,
            "driver_state_sha256": sha256_file(state_path),
            "abort_event_count": len(abort_events),
        })
    return records


def validate_extract_policy_lock() -> dict[str, Any]:
    """Validate the committed serial-recovery policy and archived OOM evidence."""

    require_sha(EXTRACT_POLICY_LOCK, EXTRACT_POLICY_LOCK_SHA256,
                "extract policy lock")
    policy = load_json(EXTRACT_POLICY_LOCK)
    require_equal(policy.get("schema"), EXTRACT_POLICY_SCHEMA,
                  "extract policy schema")
    require_equal(policy.get("state"), "locked", "extract policy state")
    require_equal(policy.get("mode"), "serial", "extract policy mode")
    require_equal(policy.get("max_parallel"), 1,
                  "extract policy max parallel")
    expected_job_order = [
        f"{condition}_seed{seed}" for condition, seed in _job_order()
    ]
    require_equal(policy.get("job_order"), expected_job_order,
                  "extract policy job order")
    require_equal(policy.get("physical_gpu_by_seed"), {"1001": 0, "1002": 1},
                  "extract policy physical GPU map")
    require_equal(
        policy.get("docker_device_request_by_seed"),
        {"1001": "device=0", "1002": "device=1"},
        "extract policy Docker device map",
    )
    require_equal(policy.get("container_cuda_visible_devices"), "0",
                  "extract policy container CUDA device")
    require_equal(policy.get("container_memory_limit_bytes"),
                  EXTRACT_CONTAINER_MEMORY_BYTES,
                  "extract policy container memory limit")
    require_equal(policy.get("container_memory_swap_limit_bytes"),
                  EXTRACT_CONTAINER_MEMORY_BYTES,
                  "extract policy container memory+swap limit")
    require_equal(
        policy.get("memory_implementation"),
        "chunked_bitwise_equivalent_decode_and_lifetime_release",
        "extract policy memory implementation",
    )
    require_equal(policy.get("archived_extract_reuse"), False,
                  "extract policy archived reuse")
    require_equal(policy.get("retraining"), False,
                  "extract policy retraining")
    require_equal(policy.get("scientific_configuration_changed"), False,
                  "extract policy scientific configuration")
    require_equal(policy.get("reason_code"), "host_oom_parallel_extract",
                  "extract policy reason")

    superseded = policy.get("superseded_attempt")
    if not isinstance(superseded, Mapping):
        raise DriverError("extract policy superseded attempt is missing")
    archive_name = str(superseded.get("archive_name", ""))
    if re.fullmatch(r"attempt\d+_[0-9a-f]{7}_extract_oom", archive_name) is None:
        raise DriverError(f"invalid extract policy archive name: {archive_name!r}")
    archive = POSTPROCESS_FAILED_ATTEMPTS_ROOT / archive_name
    state_path = archive / "driver_state.json"
    require_sha(state_path, str(superseded.get("driver_state_sha256")),
                "superseded postprocess driver state")
    archived_state = load_json(state_path)
    require_equal(archived_state.get("schema"), DRIVER_SCHEMA,
                  "superseded postprocess schema")
    require_equal(archived_state.get("state"), "aborted",
                  "superseded postprocess state")
    require_equal(archived_state.get("correction_head"),
                  superseded.get("correction_head"),
                  "superseded postprocess correction HEAD")
    abort_events = archived_state.get("abort_events")
    if not isinstance(abort_events, list) or not abort_events:
        raise DriverError("superseded postprocess abort evidence is missing")

    failed_job = str(superseded.get("failed_job_id", ""))
    failed_stage = str(superseded.get("failed_stage", ""))
    failed_attempt = str(superseded.get("failed_attempt", ""))
    evidence = archive / "attempts" / failed_job / failed_stage / failed_attempt
    require_sha(evidence / "started.json",
                str(superseded.get("started_json_sha256")),
                "superseded extract started receipt")
    require_sha(evidence / "stdout.log",
                str(superseded.get("stdout_log_sha256")),
                "superseded extract stdout")
    require_sha(evidence / "failure.json",
                str(superseded.get("failure_json_sha256")),
                "superseded extract failure receipt")
    failure = load_json(evidence / "failure.json")
    require_equal(failure.get("job_id"), failed_job,
                  "superseded extract failure job")
    require_equal(failure.get("stage"), failed_stage,
                  "superseded extract failure stage")
    require_equal(failure.get("return_code"), superseded.get("return_code"),
                  "superseded extract return code")

    result = json.loads(canonical_json(policy))
    result.update({
        "path": repo_relative(EXTRACT_POLICY_LOCK),
        "sha256": EXTRACT_POLICY_LOCK_SHA256,
        "superseded_archive_path": repo_relative(archive),
        "superseded_evidence_checked": True,
    })
    return result


def validate_training_artifacts() -> tuple[list[Job], dict[str, Any]]:
    resolved = load_json(RESOLVED_MANIFEST)
    training = load_json(TRAINING_DRIVER_MANIFEST)
    require_equal(resolved.get("schema"), "jointbuildgs.pilot_1wave.resolved_configs.v1",
                  "resolved manifest schema")
    require_equal(resolved.get("run_id"), SOURCE_RUN_ID, "resolved run ID")
    require_equal(int(resolved.get("config_count", -1)), 10, "resolved config count")
    require_equal(training.get("schema"), "jointbuildgs.pilot_1wave.driver_manifest.v1",
                  "training driver schema")
    require_equal(training.get("state"), "complete", "training driver state")
    guard = training.get("guard") or {}
    require_equal(guard.get("triggered"), False, "training guard triggered")
    require_equal(guard.get("partial"), False, "training guard partial")
    require_equal(guard.get("completion"), True, "training guard completion")
    training_runtime = training.get("runtime") or {}
    require_equal(training_runtime.get("image_id"), DEV_IMAGE_ID,
                  "training image ID")
    require_equal(training_runtime.get("git_head"), TRAINING_RUNTIME_HEAD,
                  "training runtime git HEAD")
    require_equal(int(training.get("learning_runs_started", -1)), 16,
                  "historical training learning_runs_started")
    resolved_binding = training.get("resolved_manifest") or {}
    require_equal(resolved_binding.get("sha256"), sha256_file(RESOLVED_MANIFEST),
                  "training/resolved manifest SHA")
    inventory_binding = (resolved.get("inputs") or {}).get("materialized_input_inventory") or {}
    require_equal(inventory_binding.get("sha256"), INVENTORY_SHA256,
                  "resolved inventory SHA")
    require_equal(inventory_binding.get("records_sha256"), INVENTORY_RECORDS_SHA256,
                  "resolved inventory records SHA")
    require_equal(int(inventory_binding.get("view_count", -1)), VIEW_COUNT,
                  "resolved view count")

    resolved_jobs = resolved.get("jobs")
    training_jobs = training.get("jobs")
    if not isinstance(resolved_jobs, list) or not isinstance(training_jobs, list):
        raise DriverError("training job arrays are missing")
    require_equal(len(resolved_jobs), 10, "resolved job count")
    require_equal(len(training_jobs), 10, "training job count")
    require_equal(sum(int(row.get("learning_runs_started", 0)) for row in training_jobs),
                  16, "historical per-job learning run count")
    indexed_training = {str(row.get("job_id")): row for row in training_jobs}
    jobs: list[Job] = []
    checkpoint_records: list[dict[str, Any]] = []
    for sequence, ((condition, seed), record) in enumerate(
        zip(_job_order(), resolved_jobs, strict=True), 1
    ):
        job_id = f"{condition}_seed{seed}"
        require_equal(int(record.get("sequence", -1)), sequence, f"{job_id} sequence")
        require_equal(record.get("job_id"), job_id, f"{job_id} ID")
        require_equal(record.get("condition"), condition, f"{job_id} condition")
        require_equal(int(record.get("seed", -1)), seed, f"{job_id} seed")
        training_row = indexed_training.get(job_id)
        if not isinstance(training_row, Mapping):
            raise DriverError(f"training driver lacks {job_id}")
        for field, expected in (
            ("state", "completed"), ("return_code", 0), ("partial", False),
            ("completed", True), ("winner_eligible", True),
            ("last_completed_steps", EXPECTED_STEPS),
            ("process_completed_steps", EXPECTED_STEPS),
            ("process_completed", True),
            ("checkpoint_payload_valid", True),
        ):
            require_equal(training_row.get(field), expected, f"{job_id} training {field}")
        require_equal(training_row.get("guard_reason"), None, f"{job_id} guard reason")
        require_equal(training_row.get("manifest_validation_errors"), [],
                      f"{job_id} manifest errors")

        config_path = (REPO / str(record.get("config_path"))).resolve()
        repo_relative(config_path)
        config_sha = str(record.get("config_sha256"))
        require_sha(config_path, config_sha, f"{job_id} config")
        require_equal(training_row.get("config_sha256"), config_sha,
                      f"{job_id} training config SHA")

        run_dir = TRAINING_ROOT / "runs" / condition / f"seed_{seed}"
        full_manifest = run_dir / "full_state_manifest.json"
        require_equal(Path(str(training_row.get("full_state_manifest"))).resolve(),
                      full_manifest.resolve(), f"{job_id} full manifest path")
        full_manifest_sha = str(training_row.get("full_state_manifest_sha256"))
        require_sha(full_manifest, full_manifest_sha, f"{job_id} full manifest")
        full = load_json(full_manifest)
        require_equal(full.get("schema"), "jointbuildgs.stage2.resume_manifest.v1",
                      f"{job_id} full manifest schema")
        require_equal(full.get("last_completed_steps"), EXPECTED_STEPS,
                      f"{job_id} last steps")
        require_equal(full.get("process_completed_steps"), EXPECTED_STEPS,
                      f"{job_id} process steps")
        require_equal(full.get("process_completed"), True, f"{job_id} process completion")
        require_equal(full.get("config_file_sha256"), config_sha, f"{job_id} full config SHA")
        latest = full.get("latest_full_checkpoint")
        if not isinstance(latest, Mapping):
            raise DriverError(f"{job_id} latest checkpoint is missing")
        require_equal(int(latest.get("completed_steps", -1)), EXPECTED_STEPS,
                      f"{job_id} checkpoint steps")
        checkpoint = run_dir / "ckpt/step_020000.pt"
        require_equal(_resolve_declared_path(latest.get("path"), declaring_file=full_manifest),
                      checkpoint.resolve(), f"{job_id} checkpoint path")
        checkpoint_sha = str(latest.get("sha256"))
        require_sha(checkpoint, checkpoint_sha, f"{job_id} checkpoint")
        sidecar = Path(f"{checkpoint}.sha256")
        if sidecar.is_symlink() or not sidecar.is_file():
            raise DriverError(f"{job_id} checkpoint sidecar missing/non-regular")
        require_equal(sidecar.read_text(encoding="ascii"),
                      f"{checkpoint_sha}  step_020000.pt\n",
                      f"{job_id} checkpoint sidecar")
        jobs.append(Job(
            sequence=sequence, condition=condition, seed=seed, job_id=job_id,
            run_dir=run_dir, config_path=config_path, config_sha256=config_sha,
            full_state_manifest=full_manifest, checkpoint=checkpoint,
            checkpoint_sha256=checkpoint_sha,
        ))
        checkpoint_records.append({
            "job_id": job_id,
            "full_state_manifest": repo_relative(full_manifest),
            "full_state_manifest_sha256": full_manifest_sha,
            "checkpoint": repo_relative(checkpoint),
            "checkpoint_sha256": checkpoint_sha,
            "sidecar": repo_relative(sidecar),
            "sidecar_sha256": sha256_file(sidecar),
        })
    require_equal(tuple((job.condition, job.seed) for job in jobs), _job_order(),
                  "validated job order")
    failed_root = TRAINING_ROOT / "failed_attempts"
    failed_attempts = sorted(
        path.name for path in failed_root.iterdir()
        if path.name not in {".", ".."}
    ) if failed_root.is_dir() else []
    failed_postprocess_attempts = historical_postprocess_attempt_records()
    return jobs, {
        "resolved_manifest_sha256": sha256_file(RESOLVED_MANIFEST),
        "resolved_manifest_path": repo_relative(RESOLVED_MANIFEST),
        "training_driver_manifest_sha256": sha256_file(TRAINING_DRIVER_MANIFEST),
        "training_driver_manifest_path": repo_relative(TRAINING_DRIVER_MANIFEST),
        "training_runtime_git_head": TRAINING_RUNTIME_HEAD,
        "training_runtime_image_id": DEV_IMAGE_ID,
        "state": "complete",
        "guard": dict(guard),
        "jobs": checkpoint_records,
        "canonical_completed_20k_count": 10,
        "canonical_collapse_count": 0,
        "canonical_divergence_count": 0,
        "canonical_guard_abort_count": 0,
        "historical_learning_runs_started": 16,
        "historical_failed_attempt_archive_count": len(failed_attempts),
        "historical_failed_attempt_archives": failed_attempts,
        "historical_failed_postprocess_attempt_archive_count": len(
            failed_postprocess_attempts
        ),
        "historical_failed_postprocess_attempt_archives": failed_postprocess_attempts,
    }


def validate_wave2_lock(path: Path | None, expected_sha256: str | None) -> dict[str, Any]:
    if path is None:
        if expected_sha256 is not None:
            raise DriverError("--wave2-lock-sha256 requires --wave2-lock")
        return {"status": "blocked_missing_wave2_lock", "launch_performed": False}
    if expected_sha256 is None or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise DriverError("an exact --wave2-lock-sha256 is required with --wave2-lock")
    resolved = path.resolve()
    relative = Path(repo_relative(resolved))
    require_sha(resolved, expected_sha256, "external Wave 2 lock")
    tracked = run_host(["git", "ls-files", "--error-unmatch", str(relative)], check=False)
    if tracked.returncode != 0:
        raise DriverError("external Wave 2 lock must be committed")
    blob = run_host(["git", "rev-parse", f"HEAD:{relative}"]).stdout.strip()
    worktree = run_host(["git", "hash-object", str(relative)]).stdout.strip()
    require_equal(worktree, blob, "external Wave 2 lock committed blob")
    return {
        "status": "external_wave2_lock_verified",
        "launch_performed": False,
        "path": str(relative),
        "sha256": expected_sha256,
    }


def preflight(expected_head: str, wave2_lock: Path | None = None,
              wave2_lock_sha256: str | None = None) -> tuple[list[Job], dict[str, Any]]:
    sources = require_committed_runtime(expected_head)
    images = require_images()
    gpu_device_probe = probe_gpu_device_bindings()
    crop = validate_crop_locks()
    jobs, training = validate_training_artifacts()
    extract_policy = validate_extract_policy_lock()
    extract_policy["cgroup_probe"] = probe_extract_memory_limit()
    for required in (
        GSPLAT_RUNTIME / "home", GSPLAT_RUNTIME / "xdg_cache",
        GSPLAT_RUNTIME / "torch_extensions",
    ):
        if not required.is_dir():
            raise DriverError(f"gsplat runtime cache path is missing: {required}")
    require_sha(GSPLAT_EXTENSION, GSPLAT_EXTENSION_SHA256,
                "pinned gsplat CUDA extension")
    wave2 = validate_wave2_lock(wave2_lock, wave2_lock_sha256)
    return jobs, {
        "schema": DRIVER_SCHEMA,
        "state": "preflight_passed",
        "checked_utc": now(),
        "correction_head": expected_head,
        "tracked_tree_clean": True,
        "committed_runtime_sources": sources,
        "images": images,
        "gpu_device_probe": gpu_device_probe,
        "crop_lock": crop,
        "gsplat_extension": {
            "path": repo_relative(GSPLAT_EXTENSION),
            "sha256": GSPLAT_EXTENSION_SHA256,
        },
        "training": training,
        "extract_policy_lock": extract_policy,
        "wave2_launch": wave2,
        "learning_runs_started_by_postprocess": 0,
    }


def p0_command(arguments: Sequence[str], *, read_only: bool = False) -> list[str]:
    mount = f"{REPO}:{CONTAINER_REPO}" + (":ro" if read_only else "")
    return [
        "docker", "run", "--rm", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "HOME=/tmp/p1w-home",
        "-e", "XDG_CACHE_HOME=/tmp/p1w-cache",
        "-e", "MPLCONFIGDIR=/tmp/p1w-mpl",
        "-e", "P1W_INSIDE_P0_TOOLS=1",
        "-e", f"P1W_P0_TOOLS_IMAGE_ID={P0_IMAGE_ID}",
        "-e", "NVIDIA_VISIBLE_DEVICES=none",
        "-e", "CUDA_VISIBLE_DEVICES=-1",
        "-v", mount,
        "-w", str(CONTAINER_REPO),
        P0_IMAGE_ID,
        *arguments,
    ]


def docker_gpu_device_request(physical_gpu: int) -> list[str]:
    """Expose exactly one physical GPU through Docker's DeviceRequest API."""

    if type(physical_gpu) is not int or physical_gpu not in (0, 1):
        raise DriverError(
            f"extract physical GPU must be exactly 0 or 1, got {physical_gpu!r}"
        )
    return ["--gpus", f"device={physical_gpu}"]


def probe_gpu_device_bindings() -> dict[str, Any]:
    """Verify each DeviceRequest exposes one distinct GPU in the pinned image."""

    devices: list[dict[str, Any]] = []
    for physical_gpu in (0, 1):
        command = [
            "docker", "run", "--rm", "--network", "none",
            *docker_gpu_device_request(physical_gpu),
            "-e", "CUDA_VISIBLE_DEVICES=0",
            "--entrypoint", "nvidia-smi",
            DEV_IMAGE_ID,
            "--query-gpu=uuid", "--format=csv,noheader",
        ]
        process = run_host(command)
        lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
        candidate = lines[0] if len(lines) == 1 else ""
        if re.fullmatch(
            r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
            candidate,
        ) is None:
            raise DriverError(
                f"physical GPU {physical_gpu} probe did not expose one UUID: {lines!r}"
            )
        devices.append({
            "physical_gpu": physical_gpu,
            "docker_device_request": f"device={physical_gpu}",
            "container_cuda_visible_devices": "0",
            "visible_gpu_count": 1,
            "visible_gpu_uuid": candidate,
            "command": command,
        })
    uuids = {record["visible_gpu_uuid"] for record in devices}
    if len(uuids) != 2:
        raise DriverError(
            f"physical GPU DeviceRequests did not expose two distinct UUIDs: {sorted(uuids)}"
        )
    return {
        "schema": "jointbuildgs.pilot_1wave.gpu_device_probe.v1",
        "state": "pass",
        "image_id": DEV_IMAGE_ID,
        "device_count": 2,
        "unique_visible_uuid_count": len(uuids),
        "devices": devices,
        "nvidia_smi_only": True,
        "learning_runs_started": 0,
        "gpu_work_started": 0,
    }


def probe_extract_memory_limit() -> dict[str, Any]:
    """Prove that Docker enforces the locked no-swap 24 GiB cgroup."""

    command = [
        "docker", "run", "--rm", "--network", "none",
        "--memory", EXTRACT_CONTAINER_MEMORY,
        "--memory-swap", EXTRACT_CONTAINER_MEMORY,
        "--entrypoint", "/bin/sh", DEV_IMAGE_ID,
        "-c", "cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.swap.max",
    ]
    process = run_host(command)
    lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
    require_equal(lines, [str(EXTRACT_CONTAINER_MEMORY_BYTES), "0"],
                  "extract cgroup memory probe")
    return {
        "schema": "jointbuildgs.pilot_1wave.extract_memory_probe.v1",
        "state": "pass",
        "memory_max_bytes": EXTRACT_CONTAINER_MEMORY_BYTES,
        "swap_max_bytes": 0,
        "command": command,
        "gpu_work_started": 0,
        "learning_runs_started": 0,
    }


def dev_extract_command(job: Job, attempt: Path) -> list[str]:
    command = [
        "docker", "run", "--rm", "--network", "none",
        "--memory", EXTRACT_CONTAINER_MEMORY,
        "--memory-swap", EXTRACT_CONTAINER_MEMORY,
        *docker_gpu_device_request(job.gpu),
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "CUDA_VISIBLE_DEVICES=0",
        "-e", f"HOME={container_path(GSPLAT_RUNTIME / 'home')}",
        "-e", f"XDG_CACHE_HOME={container_path(GSPLAT_RUNTIME / 'xdg_cache')}",
        "-e", f"TORCH_EXTENSIONS_DIR={container_path(GSPLAT_RUNTIME / 'torch_extensions')}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", (
            "PYTHONPATH="
            f"{CONTAINER_REPO / 'scripts/pilot_1wave'}:"
            f"{CONTAINER_REPO}"
        ),
        "-v", f"{REPO}:{CONTAINER_REPO}",
        "-w", str(CONTAINER_REPO),
        DEV_IMAGE_ID,
        "python3", container_path(EXTRACTOR),
        "--ckpt", container_path(job.checkpoint),
        "--out", container_path(attempt / "scene_geometry.npz"),
        "--downscale", "1.0",
        "--voxel", "0.05",
        "--alpha", "0.5",
        "--min-obs", "3",
        "--sor", "on",
        "--sor-std", "2.0",
        "--sor-neighbors", "20",
        "--sh-degree", "3",
        "--no-sem",
        "--coverage-csv", container_path(attempt / "coverage.csv"),
        "--metrics-json", container_path(attempt / "metrics.json"),
        "--provenance-json", container_path(attempt / "provenance.json"),
        "--condition", job.condition,
        "--seed", str(job.seed),
        "--checkpoint-step", str(EXPECTED_STEPS),
        "--full-state-manifest", container_path(job.full_state_manifest),
        "--coverage-grid", "0.5",
    ]
    forbidden = {"--targets", "--buffer", "--geojson", "--data-root", "--max-views"}
    if forbidden.intersection(command):
        raise DriverError("verified extract command contains a legacy crop argument")
    return command


def classify_command(job: Job, attempt: Path, roofprints: Path) -> list[str]:
    return p0_command([
        "python3", container_path(CLASSIFIER),
        "--scene-npz", container_path(extract_attempt(job) / "scene_geometry.npz"),
        "--roofprints", container_path(roofprints),
        "--output", container_path(attempt / "scene_classified.las"),
        "--raw-las", container_path(attempt / "scene_raw.las"),
        "--pipeline", container_path(attempt / "pdal_pipeline.json"),
        "--receipt", container_path(attempt / "classification_receipt.json"),
    ])


def stage_root(job: Job, stage: str) -> Path:
    return ATTEMPTS_ROOT / job.job_id / stage


def global_stage_root(stage: str) -> Path:
    return ATTEMPTS_ROOT / "_global" / stage


def next_attempt(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    existing = []
    for path in root.glob("attempt_[0-9][0-9][0-9]"):
        match = re.fullmatch(r"attempt_(\d{3})", path.name)
        if match:
            existing.append(int(match.group(1)))
    attempt = root / f"attempt_{max(existing, default=0) + 1:03d}"
    attempt.mkdir()
    return attempt


def latest_attempt(root: Path) -> Path | None:
    candidates = sorted(root.glob("attempt_[0-9][0-9][0-9]")) if root.is_dir() else []
    return candidates[-1] if candidates else None


def marker_outputs(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise DriverError(f"stage output is missing/non-regular: {path}")
        records.append({
            "path": repo_relative(path),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return records


def current_runtime_binding() -> dict[str, str]:
    state_path = POSTPROCESS_ROOT / "driver_state.json"
    if not state_path.is_file():
        raise DriverError("driver state is missing while writing a stage marker")
    state = load_json(state_path)
    head = state.get("correction_head")
    sources = ((state.get("preflight") or {}).get("committed_runtime_sources"))
    if not isinstance(head, str) or not isinstance(sources, Mapping):
        raise DriverError("driver state lacks the correction/runtime source binding")
    return {
        "correction_head": head,
        "runtime_sources_sha256": sha256_bytes(canonical_json(dict(sources))),
    }


def write_stage_marker(attempt: Path, stage: str, job_id: str,
                       outputs: Iterable[Path], extra: Mapping[str, Any] | None = None) -> Path:
    path = attempt / "stage_complete.json"
    payload = {
        "schema": STAGE_MARKER_SCHEMA,
        "state": "complete",
        "stage": stage,
        "job_id": job_id,
        "completed_utc": now(),
        "outputs": marker_outputs(outputs),
        **current_runtime_binding(),
        **dict(extra or {}),
    }
    payload["contract_sha256"] = sha256_bytes(canonical_json({
        "stage": stage, "job_id": job_id, "outputs": payload["outputs"],
        "correction_head": payload["correction_head"],
        "runtime_sources_sha256": payload["runtime_sources_sha256"],
        "extra": dict(extra or {}),
    }))
    atomic_json(path, payload)
    return path


def valid_stage_attempt(attempt: Path, stage: str, job_id: str) -> bool:
    marker = attempt / "stage_complete.json"
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        payload = load_json(marker)
        require_equal(payload.get("schema"), STAGE_MARKER_SCHEMA, "stage marker schema")
        require_equal(payload.get("state"), "complete", "stage marker state")
        require_equal(payload.get("stage"), stage, "stage marker stage")
        require_equal(payload.get("job_id"), job_id, "stage marker job")
        state_path = POSTPROCESS_ROOT / "driver_state.json"
        if state_path.is_file():
            binding = current_runtime_binding()
            require_equal(payload.get("correction_head"), binding["correction_head"],
                          "stage marker correction HEAD")
            require_equal(payload.get("runtime_sources_sha256"),
                          binding["runtime_sources_sha256"],
                          "stage marker runtime source SHA")
        for record in payload.get("outputs", []):
            path = REPO / str(record["path"])
            require_equal(path.stat().st_size, int(record["size"]), "stage output size")
            require_equal(sha256_file(path), record["sha256"], "stage output SHA")
    except (DriverError, OSError, KeyError, TypeError, ValueError):
        return False
    return True


def completed_attempt(root: Path, stage: str, job_id: str) -> Path | None:
    candidates = sorted(root.glob("attempt_[0-9][0-9][0-9]")) if root.is_dir() else []
    complete = [path for path in candidates if valid_stage_attempt(path, stage, job_id)]
    if len(complete) > 1:
        raise DriverError(f"multiple complete attempts for {job_id}/{stage}")
    return complete[0] if complete else None


def extract_attempt(job: Job) -> Path:
    result = completed_attempt(stage_root(job, "extract"), "extract", job.job_id)
    if result is None:
        raise DriverError(f"extract is incomplete for {job.job_id}")
    return result


def classify_attempt(job: Job) -> Path:
    result = completed_attempt(stage_root(job, "classify"), "classify", job.job_id)
    if result is None:
        raise DriverError(f"classification is incomplete for {job.job_id}")
    return result


def roofer_attempt(job: Job) -> Path:
    result = completed_attempt(stage_root(job, "finalize"), "finalize", job.job_id)
    if result is None:
        raise DriverError(f"Roofer finalize is incomplete for {job.job_id}")
    prepare = Path(load_json(result / "stage_complete.json")["prepare_attempt"])
    return prepare if prepare.is_absolute() else REPO / prepare


def score_attempt(job: Job) -> Path:
    result = completed_attempt(stage_root(job, "score"), "score", job.job_id)
    if result is None:
        raise DriverError(f"score is incomplete for {job.job_id}")
    return result


def validate_crop_contract(contract: Mapping[str, Any]) -> None:
    require_equal(contract.get("schema"),
                  "jointbuildgs.pilot_1wave.readout_crop_contract.v1",
                  "crop contract schema")
    crop = contract.get("crop") or {}
    require_equal(crop.get("mode"), "single_locked_global_bbox", "crop mode")
    require_equal(tuple(float(x) for x in crop.get("bbox_utm", [])), CROP_BBOX,
                  "crop contract bbox")
    require_equal(float(crop.get("area_m2", -1)), CROP_AREA_M2, "crop contract area")
    population = contract.get("population") or {}
    require_equal(int(population.get("count", -1)), 30, "crop population count")
    require_equal(tuple(population.get("ordered_building_ids", [])), EXPECTED_IDS,
                  "crop population IDs")
    require_equal(population.get("ordered_ids_sha256"), ORDERED_IDS_SHA256,
                  "crop ordered IDs SHA")
    inventory = contract.get("materialized_input_inventory") or {}
    require_equal(inventory.get("sha256"), INVENTORY_SHA256, "crop inventory SHA")
    require_equal(inventory.get("records_sha256"), INVENTORY_RECORDS_SHA256,
                  "crop inventory records SHA")
    require_equal(int(inventory.get("view_count", -1)), VIEW_COUNT,
                  "crop view count")


def validate_extract(job: Job, attempt: Path) -> None:
    npz = attempt / "scene_geometry.npz"
    metrics_path = attempt / "metrics.json"
    provenance_path = attempt / "provenance.json"
    coverage_path = attempt / "coverage.csv"
    for path in (npz, metrics_path, provenance_path, coverage_path):
        if not path.is_file() or path.stat().st_size <= 0:
            raise DriverError(f"extract output is missing/empty: {path}")
    metrics = load_json(metrics_path)
    require_equal(metrics.get("sor"), "on", f"{job.job_id} SOR recipe")
    require_equal(metrics.get("sor_status"), "on", f"{job.job_id} SOR status")
    if int(metrics.get("sor_kept", 0)) <= 0:
        raise DriverError(f"{job.job_id} extract has no SOR-kept points")
    provenance = load_json(provenance_path)
    require_equal(provenance.get("schema"),
                  "jointbuildgs.pilot_1wave.readout_extraction.v1",
                  f"{job.job_id} extract provenance schema")
    require_equal(provenance.get("state"), "complete", f"{job.job_id} extract state")
    require_equal(provenance.get("geometry_only"), True, f"{job.job_id} geometry-only")
    require_equal(provenance.get("crs"), "EPSG:25832", f"{job.job_id} CRS")
    output = provenance.get("output_npz") or {}
    require_equal(_resolve_declared_path(output.get("path"), declaring_file=provenance_path),
                  npz.resolve(),
                  f"{job.job_id} NPZ path")
    require_equal(output.get("sha256"), sha256_file(npz), f"{job.job_id} NPZ SHA")
    lineage = provenance.get("readout_lineage") or {}
    require_equal(lineage.get("condition_id"), job.condition, f"{job.job_id} lineage condition")
    require_equal(int(lineage.get("seed", -1)), job.seed, f"{job.job_id} lineage seed")
    require_equal(lineage.get("verified_full_state"), True, f"{job.job_id} full-state verification")
    require_equal(lineage.get("eligible_20k_full_state"), True, f"{job.job_id} 20k eligibility")
    checkpoint = lineage.get("checkpoint") or {}
    require_equal(checkpoint.get("sha256"), job.checkpoint_sha256,
                  f"{job.job_id} lineage checkpoint SHA")
    require_equal(int(checkpoint.get("completed_steps", -1)), EXPECTED_STEPS,
                  f"{job.job_id} lineage checkpoint step")
    encoded = provenance.get("crop_contract_json")
    if not isinstance(encoded, str):
        raise DriverError(f"{job.job_id} extraction lacks crop contract JSON")
    require_equal(provenance.get("crop_contract_sha256"),
                  sha256_bytes(encoded.encode("utf-8")),
                  f"{job.job_id} crop contract SHA")
    contract = json.loads(encoded)
    if not isinstance(contract, Mapping):
        raise DriverError(f"{job.job_id} crop contract is not an object")
    validate_crop_contract(contract)
    with coverage_path.open(newline="", encoding="utf-8") as stream:
        coverage = list(csv.DictReader(stream))
    require_equal(len(coverage), 90, f"{job.job_id} coverage rows")
    require_equal(Counter(row.get("stage") for row in coverage), Counter({
        "voxel_all_pre_minobs": 30,
        "minobs_post_gate_pre_sor": 30,
        "sor_post_clean": 30,
    }), f"{job.job_id} coverage stages")
    for stage in ("voxel_all_pre_minobs", "minobs_post_gate_pre_sor", "sor_post_clean"):
        require_equal(tuple(row["building_id"] for row in coverage if row["stage"] == stage),
                      EXPECTED_IDS, f"{job.job_id} coverage IDs {stage}")


def validate_classification(job: Job, attempt: Path, roofprints: Path) -> None:
    receipt_path = attempt / "classification_receipt.json"
    receipt = load_json(receipt_path)
    require_equal(receipt.get("schema"), "jointbuildgs.pilot_1wave.scene_classification.v1",
                  f"{job.job_id} classification schema")
    require_equal(receipt.get("state"), "complete", f"{job.job_id} classification state")
    require_equal(receipt.get("crs"), "EPSG:25832", f"{job.job_id} classification CRS")
    roof = receipt.get("roofprints") or {}
    require_equal(_resolve_declared_path(roof.get("path"), declaring_file=receipt_path),
                  roofprints.resolve(),
                  f"{job.job_id} roofprint path")
    require_equal(roof.get("sha256"), sha256_file(roofprints),
                  f"{job.job_id} roofprint SHA")
    require_equal(tuple(roof.get("building_ids", [])), EXPECTED_IDS,
                  f"{job.job_id} roofprint order")
    validate_crop_contract(receipt.get("crop_contract") or {})
    lineage = receipt.get("readout_lineage") or {}
    require_equal(lineage.get("condition_id"), job.condition,
                  f"{job.job_id} classification condition")
    require_equal(int(lineage.get("seed", -1)), job.seed,
                  f"{job.job_id} classification seed")
    classified = receipt.get("classified_las") or {}
    las = attempt / "scene_classified.las"
    require_equal(_resolve_declared_path(classified.get("path"), declaring_file=receipt_path),
                  las.resolve(),
                  f"{job.job_id} classified LAS path")
    require_equal(classified.get("sha256"), sha256_file(las),
                  f"{job.job_id} classified LAS SHA")
    require_equal(int(classified.get("epsg", -1)), 25832,
                  f"{job.job_id} classified LAS EPSG")
    counts = classified.get("class_counts") or {}
    if int(counts.get("2", 0)) <= 0 or int(counts.get("6", 0)) <= 0:
        raise DriverError(f"{job.job_id} classified LAS lacks class 2/6")


def roofprint_ordered_geometry_sha256(path: Path) -> str:
    payload = load_json(path)
    features = payload.get("features")
    if not isinstance(features, list):
        raise DriverError("locked roofprint features are missing")
    ids = tuple(
        str((feature.get("properties") or {}).get("building_id"))
        for feature in features
    )
    require_equal(ids, EXPECTED_IDS, "locked roofprint ID order")
    ordered = [
        {"building_id": building_id, "geometry": feature.get("geometry")}
        for building_id, feature in zip(ids, features, strict=True)
    ]
    return sha256_bytes(canonical_json(ordered))


def validate_cross_run_roofprint_binding(jobs: Sequence[Job], roofprints: Path) -> dict[str, Any]:
    expected_path = roofprints.resolve()
    expected_sha = sha256_file(roofprints)
    geometry_sha = roofprint_ordered_geometry_sha256(roofprints)
    receipts = []
    observed_paths: set[str] = set()
    observed_shas: set[str] = set()
    for job in jobs:
        attempt = classify_attempt(job)
        validate_classification(job, attempt, roofprints)
        receipt_path = attempt / "classification_receipt.json"
        payload = load_json(receipt_path)
        record = payload.get("roofprints") or {}
        declared = _resolve_declared_path(record.get("path"), declaring_file=receipt_path)
        observed_paths.add(str(declared))
        observed_shas.add(str(record.get("sha256")))
        receipts.append({
            "job_id": job.job_id,
            "classification_receipt": repo_relative(receipt_path),
            "classification_receipt_sha256": sha256_file(receipt_path),
            "roofprint_path": repo_relative(declared),
            "roofprint_sha256": str(record.get("sha256")),
        })
    require_equal(observed_paths, {str(expected_path)}, "cross-run roofprint path set")
    require_equal(observed_shas, {expected_sha}, "cross-run roofprint SHA set")
    result = {
        "schema": "jointbuildgs.pilot_1wave.cross_run_roofprint_binding.v1",
        "state": "complete",
        "run_count": 10,
        "roofprint_path": repo_relative(expected_path),
        "roofprint_sha256": expected_sha,
        "ordered_geometry_sha256": geometry_sha,
        "ordered_ids_sha256": ORDERED_IDS_SHA256,
        "unique_path_count": len(observed_paths),
        "unique_sha256_count": len(observed_shas),
        "receipts": receipts,
    }
    atomic_json(POSTPROCESS_ROOT / "roofprint_binding_receipt.json", result)
    return result


def stage_command(command: Sequence[str], attempt: Path, label: str) -> None:
    atomic_json(attempt / "started.json", {
        "schema": STAGE_MARKER_SCHEMA, "state": "started", "stage": label,
        "started_utc": now(), "command": list(command),
    })
    with (attempt / "stdout.log").open("w", encoding="utf-8") as log:
        process = run_host(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if process.returncode != 0:
        atomic_json(attempt / "failure.json", {
            "schema": STAGE_MARKER_SCHEMA, "state": "error", "stage": label,
            "ended_utc": now(), "return_code": process.returncode,
        })
        raise DriverError(f"{label} failed exit={process.returncode}; see {attempt/'stdout.log'}")


def gpu_waves(pending: Sequence[Job]) -> list[list[Job]]:
    """Return deterministic singleton waves in canonical job order."""

    canonical = [f"{condition}_seed{seed}" for condition, seed in _job_order()]
    positions = {job_id: index for index, job_id in enumerate(canonical)}
    job_ids = [job.job_id for job in pending]
    if len(job_ids) != len(set(job_ids)):
        raise DriverError("serial GPU scheduler received a duplicate job")
    if any(job_id not in positions for job_id in job_ids):
        raise DriverError("serial GPU scheduler received a noncanonical job")
    if job_ids != sorted(job_ids, key=positions.__getitem__):
        raise DriverError("serial GPU scheduler input is not in canonical order")
    waves = [[job] for job in pending]
    if [wave[0].job_id for wave in waves] != job_ids:
        raise DriverError("serial GPU scheduler lost or reordered a job")
    return waves


def run_extract_barrier(jobs: Sequence[Job],
                        extract_policy: Mapping[str, Any]) -> None:
    require_equal(extract_policy.get("sha256"), EXTRACT_POLICY_LOCK_SHA256,
                  "extract barrier policy SHA")
    require_equal(extract_policy.get("mode"), "serial",
                  "extract barrier policy mode")
    require_equal(extract_policy.get("max_parallel"), 1,
                  "extract barrier max parallel")
    policy_order = extract_policy.get("job_order")
    require_equal(policy_order,
                  [f"{condition}_seed{seed}" for condition, seed in _job_order()],
                  "extract barrier policy job order")
    pending = [job for job in jobs if completed_attempt(
        stage_root(job, "extract"), "extract", job.job_id
    ) is None]
    for wave in gpu_waves(pending):
        require_equal(len(wave), 1, "extract serial wave size")
        running: list[tuple[Job, Path, subprocess.Popen[str], TextIO]] = []
        for job in wave:
            serial_ordinal = list(policy_order).index(job.job_id) + 1
            attempt = next_attempt(stage_root(job, "extract"))
            command = dev_extract_command(job, attempt)
            atomic_json(attempt / "started.json", {
                "schema": STAGE_MARKER_SCHEMA, "state": "started", "stage": "extract",
                "job_id": job.job_id, "gpu": job.gpu, "started_utc": now(),
                "extract_policy_sha256": EXTRACT_POLICY_LOCK_SHA256,
                "extract_max_parallel": 1, "serial_ordinal": serial_ordinal,
                "container_memory_limit_bytes": EXTRACT_CONTAINER_MEMORY_BYTES,
                "command": command,
            })
            log = (attempt / "stdout.log").open("w", encoding="utf-8")
            process = subprocess.Popen(command, cwd=REPO, text=True, stdout=log,
                                       stderr=subprocess.STDOUT)
            running.append((job, attempt, process, log))
        reconciled: list[tuple[Job, Path, int]] = []
        for job, attempt, process, log in running:
            return_code = process.wait()
            log.close()
            reconciled.append((job, attempt, return_code))
        failures: list[str] = []
        # Every child is reaped and every log is closed before validation can
        # raise.  A bad first output can therefore never orphan the second GPU.
        for job, attempt, return_code in reconciled:
            if return_code != 0:
                atomic_json(attempt / "failure.json", {
                    "schema": STAGE_MARKER_SCHEMA, "state": "error", "stage": "extract",
                    "job_id": job.job_id, "return_code": return_code, "ended_utc": now(),
                })
                failures.append(f"{job.job_id}:exit={return_code}")
                continue
            try:
                validate_extract(job, attempt)
                write_stage_marker(attempt, "extract", job.job_id, (
                    attempt / "scene_geometry.npz", attempt / "coverage.csv",
                    attempt / "metrics.json", attempt / "provenance.json",
                ), {
                    "gpu": job.gpu,
                    "checkpoint_sha256": job.checkpoint_sha256,
                    "extract_policy_sha256": EXTRACT_POLICY_LOCK_SHA256,
                    "extract_max_parallel": 1,
                    "serial_ordinal": serial_ordinal,
                    "container_memory_limit_bytes": EXTRACT_CONTAINER_MEMORY_BYTES,
                })
            except Exception as exc:
                atomic_json(attempt / "failure.json", {
                    "schema": STAGE_MARKER_SCHEMA, "state": "error",
                    "stage": "extract_validation", "job_id": job.job_id,
                    "error_type": type(exc).__name__, "error": str(exc),
                    "ended_utc": now(),
                })
                failures.append(f"{job.job_id}:validation={type(exc).__name__}:{exc}")
        if failures:
            raise DriverError("extract wave failed: " + ", ".join(failures))
    for job in jobs:
        extract_attempt(job)


def prepare_global_roofprint() -> Path:
    root = global_stage_root("roofprint")
    complete = completed_attempt(root, "roofprint", "global")
    if complete is not None:
        return complete / "locked_roofprints.geojson"
    attempt = next_attempt(root)
    output = attempt / "locked_roofprints.geojson"
    command = p0_command([
        "python3", container_path(SCORING), "prepare-roofprints",
        "--output", container_path(output),
    ])
    stage_command(command, attempt, "roofprint")
    if not output.is_file() or output.stat().st_size <= 0:
        raise DriverError("global roofprint output is missing/empty")
    payload = load_json(output)
    features = payload.get("features")
    if not isinstance(features, list):
        raise DriverError("global roofprint features are missing")
    require_equal(len(features), 30, "global roofprint feature count")
    require_equal(tuple(str((feature.get("properties") or {}).get("building_id"))
                        for feature in features), EXPECTED_IDS, "global roofprint order")
    write_stage_marker(attempt, "roofprint", "global", (output,), {
        "source_sha256": FOOTPRINT_SHA256, "ordered_ids_sha256": ORDERED_IDS_SHA256,
    })
    return output


def run_classify_barrier(jobs: Sequence[Job], roofprints: Path) -> None:
    for job in jobs:
        if completed_attempt(stage_root(job, "classify"), "classify", job.job_id):
            continue
        attempt = next_attempt(stage_root(job, "classify"))
        command = classify_command(job, attempt, roofprints)
        stage_command(command, attempt, "classify")
        validate_classification(job, attempt, roofprints)
        write_stage_marker(attempt, "classify", job.job_id, (
            attempt / "scene_raw.las", attempt / "scene_classified.las",
            attempt / "pdal_pipeline.json", attempt / "classification_receipt.json",
            attempt / "classification_receipt.log",
        ), {"roofprint_sha256": sha256_file(roofprints)})
    for job in jobs:
        classify_attempt(job)
    validate_cross_run_roofprint_binding(jobs, roofprints)


def run_prepare_barrier(jobs: Sequence[Job]) -> dict[str, Path]:
    prepared: dict[str, Path] = {}
    for job in jobs:
        root = stage_root(job, "prepare")
        complete = completed_attempt(root, "prepare", job.job_id)
        if complete is None:
            attempt = next_attempt(root)
            runtime = attempt / "runtime"
            command = p0_command([
                "python3", container_path(SCORING), "prepare-roofer",
                "--condition", job.condition, "--seed", str(job.seed),
                "--pointcloud", container_path(classify_attempt(job) / "scene_classified.las"),
                "--classification-receipt",
                container_path(classify_attempt(job) / "classification_receipt.json"),
                "--output-dir", container_path(runtime),
            ])
            stage_command(command, attempt, "prepare")
            receipt = load_json(runtime / "roofer_prepare.json")
            require_equal(receipt.get("schema"),
                          "jointbuildgs.pilot_1wave.roofer_prepare.v1",
                          f"{job.job_id} Roofer prepare schema")
            require_equal(receipt.get("state"), "prepared", f"{job.job_id} prepare state")
            require_equal(receipt.get("condition_id"), job.condition,
                          f"{job.job_id} prepare condition")
            require_equal(int(receipt.get("seed", -1)), job.seed,
                          f"{job.job_id} prepare seed")
            argv = load_json(runtime / "roofer_argv.json")
            require_equal(argv.get("schema"), "jointbuildgs.pilot_1wave.roofer_argv.v1",
                          f"{job.job_id} Roofer argv schema")
            require_equal(argv.get("image"), ROOFER_IMAGE, f"{job.job_id} Roofer image")
            arguments = argv.get("arguments")
            if not isinstance(arguments, list):
                raise DriverError(f"{job.job_id} Roofer argv is missing")
            require_equal(tuple(arguments[:len(FIXED_ROOFER_PARAMETERS)]),
                          FIXED_ROOFER_PARAMETERS, f"{job.job_id} Roofer parameters")
            require_equal(len(arguments), len(FIXED_ROOFER_PARAMETERS) + 3,
                          f"{job.job_id} Roofer argv length")
            write_stage_marker(attempt, "prepare", job.job_id, (
                runtime / "roofer_prepare.json", runtime / "roofer_argv.json",
            ), {"runtime": repo_relative(runtime)})
            complete = attempt
        prepared[job.job_id] = complete / "runtime"
    return prepared


def retained_action(container_state: str | None, *, launch_record_exists: bool,
                    finalized: bool, exit_code: int | None = None) -> str:
    """Pure fail-closed transition used by Roofer and mocked tests."""
    if finalized:
        return "skip"
    if container_state is None:
        return "fail_missing_after_launch" if launch_record_exists else "create"
    if container_state == "created":
        return "start"
    if container_state == "running":
        return "wait"
    if container_state == "exited":
        return "finalize_process" if exit_code == 0 else "fail_nonzero"
    return "fail_unsupported_state"


def inspect_container(name: str) -> dict[str, Any] | None:
    process = run_host(["docker", "inspect", name], check=False)
    if process.returncode != 0:
        text = f"{process.stdout or ''}\n{process.stderr or ''}"
        if "No such object" in text or "No such container" in text:
            return None
        raise DriverError(f"cannot inspect container {name}: {text}")
    try:
        values = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise DriverError(f"invalid docker inspect output for {name}") from exc
    if not isinstance(values, list) or len(values) != 1:
        raise DriverError(f"unexpected docker inspect cardinality for {name}")
    return values[0]


def _container_state(record: Mapping[str, Any]) -> tuple[str, int | None]:
    state = record.get("State") or {}
    status = str(state.get("Status", ""))
    exit_code = int(state.get("ExitCode", -1)) if status == "exited" else None
    return status, exit_code


def _validate_retained_contract(record: Mapping[str, Any], *, name: str,
                                job_id: str, contract_sha: str,
                                image_id: str) -> str:
    require_equal(record.get("Name"), f"/{name}", f"{job_id} container name")
    require_equal(record.get("Image"), image_id, f"{job_id} container image ID")
    labels = ((record.get("Config") or {}).get("Labels") or {})
    require_equal(labels.get("jointbuildgs.p1w.job"), job_id, f"{job_id} container job label")
    require_equal(labels.get("jointbuildgs.p1w.contract"), contract_sha,
                  f"{job_id} container contract label")
    container_id = str(record.get("Id", ""))
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise DriverError(f"{job_id} container ID is invalid")
    return container_id


def _validate_inspect_command(record: Mapping[str, Any], contract: Mapping[str, Any],
                              job_id: str) -> None:
    config = record.get("Config") or {}
    expected_image = contract.get("image")
    if expected_image is not None:
        require_equal(config.get("Image"), expected_image,
                      f"{job_id} immutable Config.Image")
    expected_arguments = contract.get("arguments")
    if expected_arguments is not None:
        require_equal(config.get("Cmd"), list(expected_arguments),
                      f"{job_id} immutable Config.Cmd")
    host = record.get("HostConfig") or {}
    require_equal(host.get("NetworkMode"), "none",
                  f"{job_id} immutable network mode")


def run_retained_container(
    *,
    name: str,
    job_id: str,
    contract: Mapping[str, Any],
    create_command: Sequence[str],
    state_dir: Path,
    expected_image_id: str,
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    launch_path = state_dir / "container_launch.json"
    contract_sha = sha256_bytes(canonical_json(contract))
    record = inspect_container(name)
    status, exit_code = (None, None) if record is None else _container_state(record)
    action = retained_action(status, launch_record_exists=launch_path.is_file(),
                             finalized=False, exit_code=exit_code)
    if action == "create":
        process = run_host(create_command, check=False)
        if process.returncode != 0:
            raise DriverError(f"container create failed for {job_id}: {process.stderr}")
        record = inspect_container(name)
        if record is None:
            raise DriverError(f"created container disappeared for {job_id}")
        container_id = _validate_retained_contract(
            record, name=name, job_id=job_id, contract_sha=contract_sha,
            image_id=expected_image_id,
        )
        _validate_inspect_command(record, contract, job_id)
        atomic_json(launch_path, {
            "schema": STAGE_MARKER_SCHEMA, "state": "container_created",
            "job_id": job_id, "container_name": name, "container_id": container_id,
            "contract_sha256": contract_sha, "created_utc": now(),
            "create_command": list(create_command),
        })
        status, exit_code = _container_state(record)
        action = retained_action(status, launch_record_exists=True,
                                 finalized=False, exit_code=exit_code)
    elif record is not None:
        container_id = _validate_retained_contract(
            record, name=name, job_id=job_id, contract_sha=contract_sha,
            image_id=expected_image_id,
        )
        _validate_inspect_command(record, contract, job_id)
        if launch_path.is_file():
            launch = load_json(launch_path)
            require_equal(launch.get("container_id"), container_id,
                          f"{job_id} retained container ID")
            require_equal(launch.get("contract_sha256"), contract_sha,
                          f"{job_id} retained contract SHA")
        else:
            # Crash recovery for the narrow create-success / receipt-write
            # window.  The immutable labels and image ID above are the
            # authority; no second container is created.
            atomic_json(launch_path, {
                "schema": STAGE_MARKER_SCHEMA,
                "state": "container_created_recovered",
                "job_id": job_id,
                "container_name": name,
                "container_id": container_id,
                "contract_sha256": contract_sha,
                "created_utc": now(),
                "create_command": list(create_command),
                "start_attempts": [],
            })
    if action == "start":
        launch = load_json(launch_path)
        attempts = launch.get("start_attempts")
        if attempts is None:
            attempts = []
        if not isinstance(attempts, list):
            raise DriverError(f"{job_id} start-attempt ledger is invalid")
        if attempts:
            raise DriverError(
                f"{job_id} is still created after a recorded start request; "
                "the crash window is ambiguous and automatic retry is forbidden"
            )
        attempts.append({"ordinal": len(attempts) + 1, "requested_utc": now()})
        launch["start_attempts"] = attempts
        launch["start_attempt_count"] = len(attempts)
        launch["state"] = "start_requested"
        atomic_json(launch_path, launch)
        run_host(["docker", "start", name])
        action = "wait"
    if action == "wait":
        waited = run_host(["docker", "wait", name]).stdout.strip()
        if not re.fullmatch(r"-?\d+", waited):
            raise DriverError(f"invalid docker wait result for {job_id}: {waited!r}")
        exit_code = int(waited)
        action = "finalize_process" if exit_code == 0 else "fail_nonzero"
    if action in {"fail_missing_after_launch", "fail_unsupported_state"}:
        raise DriverError(f"retained container {job_id} cannot continue: {action}")
    logs = run_host(["docker", "logs", name], check=False)
    atomic_bytes(state_dir / "container.log",
                 ((logs.stdout or "") + (logs.stderr or "")).encode("utf-8"))
    if action != "finalize_process":
        raise DriverError(f"retained container {job_id} cannot continue: {action}")
    atomic_json(state_dir / "process_complete.json", {
        "schema": STAGE_MARKER_SCHEMA, "state": "process_complete",
        "job_id": job_id, "container_name": name, "contract_sha256": contract_sha,
        "exit_code": 0, "wait_exit_code": 0, "completed_utc": now(),
    })


def write_roofer_execution_receipt(job: Job, runtime: Path) -> Path:
    """Bind the actual retained-container execution before p0 finalization."""

    prepare = runtime / "roofer_prepare.json"
    argv = runtime / "roofer_argv.json"
    launch_path = runtime / "container_launch.json"
    process_path = runtime / "process_complete.json"
    log_path = runtime / "container.log"
    for path in (prepare, argv, launch_path, process_path, log_path):
        if not path.is_file() or path.is_symlink():
            raise DriverError(f"{job.job_id} Roofer execution evidence missing: {path}")
    launch = load_json(launch_path)
    process = load_json(process_path)
    name = roofer_container_name(job)
    inspect = inspect_container(name)
    if inspect is None:
        raise DriverError(f"{job.job_id} Roofer container vanished before receipt")
    status, exit_code = _container_state(inspect)
    require_equal(status, "exited", f"{job.job_id} Roofer receipt state")
    require_equal(exit_code, 0, f"{job.job_id} Roofer receipt exit code")
    require_equal(process.get("exit_code"), 0, f"{job.job_id} process receipt exit code")
    container_id = _validate_retained_contract(
        inspect,
        name=name,
        job_id=job.job_id,
        contract_sha=str(launch.get("contract_sha256")),
        image_id=ROOFER_IMAGE_ID,
    )
    require_equal(launch.get("container_id"), container_id,
                  f"{job.job_id} execution receipt container ID")
    require_equal(len(launch.get("start_attempts") or []), 1,
                  f"{job.job_id} execution receipt start attempt count")
    state = inspect.get("State") or {}
    config = inspect.get("Config") or {}
    host_config = inspect.get("HostConfig") or {}
    receipt = {
        "schema": "jointbuildgs.pilot_1wave.roofer_execution.v1",
        "state": "complete",
        "condition_id": job.condition,
        "seed": job.seed,
        "job_id": job.job_id,
        "prepare_receipt": {
            "path": repo_relative(prepare), "sha256": sha256_file(prepare),
        },
        "roofer_argv": {"path": repo_relative(argv), "sha256": sha256_file(argv)},
        "container": {
            "id": container_id,
            "name": name,
            "image_reference": ROOFER_IMAGE,
            "image_id": str(inspect.get("Image")),
            "config_image": config.get("Image"),
            "entrypoint": config.get("Entrypoint"),
            "cmd": config.get("Cmd"),
            "labels": config.get("Labels") or {},
            "binds": host_config.get("Binds") or [],
            "network_mode": host_config.get("NetworkMode"),
            "restart_count": int(inspect.get("RestartCount", 0)),
        },
        "execution": {
            # The state machine calls docker start only from Docker's `created`
            # state and never from `exited`; every request is durably recorded
            # before the Docker call.  A crash may yield >1 request while the
            # process invocation itself remains exactly one.
            "start_attempt_count": len(launch.get("start_attempts") or []),
            "start_attempts": launch.get("start_attempts") or [],
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "wait_exit_code": exit_code,
            "docker_state": status,
        },
        "logs": {
            "path": repo_relative(log_path),
            "sha256": sha256_file(log_path),
            "size": log_path.stat().st_size,
        },
        "launch_receipt": {
            "path": repo_relative(launch_path), "sha256": sha256_file(launch_path),
        },
        "process_receipt": {
            "path": repo_relative(process_path), "sha256": sha256_file(process_path),
        },
        "created_utc": now(),
        "roofer_invocation_count": 1,
    }
    receipt_path = runtime / "roofer_execution_receipt.json"
    if receipt_path.exists():
        existing = load_json(receipt_path)
        # Timestamps make byte identity inappropriate; all immutable execution
        # bindings must nevertheless remain exact.
        for field in (
            "schema", "state", "condition_id", "seed", "job_id",
            "prepare_receipt", "roofer_argv", "container", "execution", "logs",
            "launch_receipt", "process_receipt", "roofer_invocation_count",
        ):
            require_equal(existing.get(field), receipt.get(field),
                          f"{job.job_id} existing execution receipt {field}")
        return receipt_path
    atomic_json(receipt_path, receipt)
    return receipt_path


def roofer_container_name(job: Job) -> str:
    return f"jointbuildgs-p1w-20260722-{job.condition}-seed{job.seed}-roofer"


def score_container_name(job: Job) -> str:
    return f"jointbuildgs-p1w-20260722-{job.condition}-seed{job.seed}-score"


def run_roofer_barrier(jobs: Sequence[Job], prepared: Mapping[str, Path]) -> None:
    for job in jobs:
        runtime = prepared[job.job_id]
        final_marker = runtime / "roofer_invocation.json"
        if final_marker.is_file():
            continue
        execution_receipt = runtime / "roofer_execution_receipt.json"
        if execution_receipt.is_file():
            # The execution receipt is the immutable boundary between the
            # retained Roofer process and the idempotent p0 finalizer.  On a
            # crash after receipt creation but before finalization, re-open
            # all bound evidence without touching the log/process files whose
            # hashes are already sealed by that receipt.
            write_roofer_execution_receipt(job, runtime)
            continue
        argv_path = runtime / "roofer_argv.json"
        argv = load_json(argv_path)
        arguments = argv.get("arguments")
        if not isinstance(arguments, list):
            raise DriverError(f"{job.job_id} Roofer arguments are missing")
        contract = {
            "job_id": job.job_id,
            "prepare_sha256": sha256_file(runtime / "roofer_prepare.json"),
            "argv_sha256": sha256_file(argv_path),
            "image": ROOFER_IMAGE,
            "arguments": arguments,
        }
        contract_sha = sha256_bytes(canonical_json(contract))
        name = roofer_container_name(job)
        create = [
            "docker", "create", "--name", name, "--network", "none",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--label", f"jointbuildgs.p1w.job={job.job_id}",
            "--label", f"jointbuildgs.p1w.contract={contract_sha}",
            "-v", f"{REPO}:{CONTAINER_REPO}",
            "-w", str(CONTAINER_REPO),
            ROOFER_IMAGE, *[str(value) for value in arguments],
        ]
        run_retained_container(
            name=name, job_id=job.job_id, contract=contract, create_command=create,
            state_dir=runtime, expected_image_id=ROOFER_IMAGE_ID,
        )
        write_roofer_execution_receipt(job, runtime)
    for job in jobs:
        runtime = prepared[job.job_id]
        if not (runtime / "process_complete.json").is_file() and not (
            runtime / "roofer_invocation.json"
        ).is_file():
            raise DriverError(f"Roofer process barrier incomplete for {job.job_id}")


def validate_finalized_runtime(job: Job, runtime: Path) -> tuple[Path, Path]:
    marker_path = runtime / "roofer_invocation.json"
    execution_path = runtime / "roofer_execution_receipt.json"
    marker = load_json(marker_path)
    require_equal(marker.get("schema"),
                  "jointbuildgs.pilot_1wave.roofer_invocation.v2",
                  f"{job.job_id} Roofer marker schema")
    require_equal(marker.get("state"), "complete", f"{job.job_id} Roofer state")
    require_equal(marker.get("condition_id"), job.condition,
                  f"{job.job_id} Roofer marker condition")
    require_equal(int(marker.get("seed", -1)), job.seed,
                  f"{job.job_id} Roofer marker seed")
    execution_binding = marker.get("execution_receipt")
    if not isinstance(execution_binding, Mapping):
        raise DriverError(f"{job.job_id} Roofer marker lacks execution receipt")
    require_equal(
        _resolve_declared_path(execution_binding.get("path"), declaring_file=marker_path),
        execution_path.resolve(),
        f"{job.job_id} marker execution receipt path",
    )
    require_equal(execution_binding.get("sha256"), sha256_file(execution_path),
                  f"{job.job_id} marker execution receipt SHA")
    normalized = marker.get("roofer_execution") or {}
    require_equal(normalized.get("schema"),
                  "jointbuildgs.pilot_1wave.roofer_execution.v1",
                  f"{job.job_id} normalized Roofer execution schema")
    require_equal(int(normalized.get("roofer_invocation_count", -1)), 1,
                  f"{job.job_id} normalized Roofer invocation count")
    require_equal(int(normalized.get("wait_exit_code", -1)), 0,
                  f"{job.job_id} normalized Roofer wait exit")
    require_equal(int(normalized.get("start_attempt_count", -1)), 1,
                  f"{job.job_id} normalized Roofer start count")
    cityjson = runtime / "assembled.city.json"
    require_equal(marker.get("cityjson_sha256"), sha256_file(cityjson),
                  f"{job.job_id} CityJSON SHA")
    return marker_path, cityjson


def finalize_command(job: Job, runtime: Path, execution_receipt: Path) -> list[str]:
    return p0_command([
        "python3", container_path(SCORING), "finalize-roofer",
        "--condition", job.condition, "--seed", str(job.seed),
        "--prepare-receipt", container_path(runtime / "roofer_prepare.json"),
        "--execution-receipt", container_path(execution_receipt),
    ])


def run_finalize_barrier(jobs: Sequence[Job], prepared: Mapping[str, Path]) -> None:
    for job in jobs:
        root = stage_root(job, "finalize")
        if completed_attempt(root, "finalize", job.job_id):
            continue
        runtime = prepared[job.job_id]
        execution_receipt = write_roofer_execution_receipt(job, runtime)
        attempt = next_attempt(root)
        # The pinned finalizer is intentionally idempotent: on marker-existing
        # recovery it re-opens raw JSONSeq, merged CityJSON, and execution
        # receipt without invoking Roofer again.
        command = finalize_command(job, runtime, execution_receipt)
        stage_command(command, attempt, "finalize")
        marker_path, cityjson = validate_finalized_runtime(job, runtime)
        write_stage_marker(attempt, "finalize", job.job_id, (
            runtime / "roofer_prepare.json", runtime / "roofer_argv.json",
            execution_receipt, marker_path, cityjson,
        ), {"prepare_attempt": repo_relative(runtime), "roofer_invocation_count": 1})
        container = inspect_container(roofer_container_name(job))
        if container is not None:
            status, exit_code = _container_state(container)
            if status != "exited" or exit_code != 0:
                raise DriverError(f"cannot remove non-success Roofer container for {job.job_id}")
            run_host(["docker", "rm", roofer_container_name(job)])
    for job in jobs:
        roofer_attempt(job)


def _p0_retained_create(name: str, job: Job, contract_sha: str,
                        arguments: Sequence[str]) -> list[str]:
    return [
        "docker", "create", "--name", name, "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--label", f"jointbuildgs.p1w.job={job.job_id}",
        "--label", f"jointbuildgs.p1w.contract={contract_sha}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "HOME=/tmp/p1w-home", "-e", "XDG_CACHE_HOME=/tmp/p1w-cache",
        "-e", "MPLCONFIGDIR=/tmp/p1w-mpl",
        "-e", "P1W_INSIDE_P0_TOOLS=1",
        "-e", f"P1W_P0_TOOLS_IMAGE_ID={P0_IMAGE_ID}",
        "-e", "NVIDIA_VISIBLE_DEVICES=none", "-e", "CUDA_VISIBLE_DEVICES=-1",
        "-v", f"{REPO}:{CONTAINER_REPO}", "-w", str(CONTAINER_REPO),
        P0_IMAGE_ID, *arguments,
    ]


def validate_score(job: Job, attempt: Path) -> None:
    marker = load_json(attempt / "score_invocation.json")
    require_equal(marker.get("schema"), "jointbuildgs.pilot_1wave.score_invocation.v1",
                  f"{job.job_id} score marker schema")
    require_equal(marker.get("state"), "complete", f"{job.job_id} score state")
    require_equal(marker.get("condition_id"), job.condition, f"{job.job_id} score condition")
    require_equal(int(marker.get("seed", -1)), job.seed, f"{job.job_id} score seed")
    require_equal(int(marker.get("score_invocation_count", -1)), 1,
                  f"{job.job_id} score invocation count")
    require_equal(int(marker.get("val3dity_invocation_count", -1)), 1,
                  f"{job.job_id} val3dity invocation count")
    score = attempt / "scores.csv"
    require_equal(marker.get("score_output_sha256"), sha256_file(score),
                  f"{job.job_id} score SHA")
    require_equal(int(marker.get("score_output_row_count", -1)), 30,
                  f"{job.job_id} score row count")
    with score.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    require_equal(len(rows), 30, f"{job.job_id} score CSV rows")
    require_equal(tuple(row.get("building_id") for row in rows), EXPECTED_IDS,
                  f"{job.job_id} score building IDs")


def run_score_barrier(jobs: Sequence[Job]) -> None:
    # The caller must have crossed the all-ten-finalized barrier first.
    for job in jobs:
        roofer_attempt(job)
    for job in jobs:
        root = stage_root(job, "score")
        if completed_attempt(root, "score", job.job_id):
            continue
        attempt = latest_attempt(root)
        if attempt is None:
            attempt = next_attempt(root)
        elif (attempt / "failure.json").is_file():
            raise DriverError(
                f"{job.job_id} score has a prior failure; exact-once automatic retry is forbidden"
            )
        score_marker = attempt / "score_invocation.json"
        if score_marker.is_file():
            marker_state = load_json(score_marker).get("state")
            if marker_state == "complete":
                validate_score(job, attempt)
                write_stage_marker(attempt, "score", job.job_id, (
                    attempt / "scores.csv", score_marker,
                    attempt / "scores.val3dity.json",
                ), {"score_invocation_count": 1, "val3dity_invocation_count": 1,
                    "recovered_complete_marker": True})
                container = inspect_container(score_container_name(job))
                if container is not None:
                    status, exit_code = _container_state(container)
                    if status != "exited" or exit_code != 0:
                        raise DriverError(
                            f"completed score marker has non-success container for {job.job_id}"
                        )
                    run_host(["docker", "rm", score_container_name(job)])
                continue
            if marker_state == "error":
                raise DriverError(
                    f"{job.job_id} score marker is error; exact-once retry is forbidden"
                )
        runtime = roofer_attempt(job)
        arguments = [
            "python3", container_path(SCORING), "score-cityjson",
            "--condition", job.condition, "--seed", str(job.seed),
            "--cityjson", container_path(runtime / "assembled.city.json"),
            "--roofer-marker", container_path(runtime / "roofer_invocation.json"),
            "--full-state-manifest", container_path(job.full_state_manifest),
            "--output", container_path(attempt / "scores.csv"),
            "--score-marker", container_path(attempt / "score_invocation.json"),
            "--guard-status", "not_triggered",
        ]
        contract = {
            "job_id": job.job_id,
            "cityjson_sha256": sha256_file(runtime / "assembled.city.json"),
            "roofer_marker_sha256": sha256_file(runtime / "roofer_invocation.json"),
            "full_state_manifest_sha256": sha256_file(job.full_state_manifest),
            "image": P0_IMAGE_ID,
            "arguments": arguments,
        }
        contract_sha = sha256_bytes(canonical_json(contract))
        create = _p0_retained_create(score_container_name(job), job, contract_sha, arguments)
        run_retained_container(
            name=score_container_name(job), job_id=job.job_id, contract=contract,
            create_command=create, state_dir=attempt, expected_image_id=P0_IMAGE_ID,
        )
        validate_score(job, attempt)
        write_stage_marker(attempt, "score", job.job_id, (
            attempt / "scores.csv", attempt / "score_invocation.json",
            attempt / "scores.val3dity.json",
        ), {"score_invocation_count": 1, "val3dity_invocation_count": 1})
        container = inspect_container(score_container_name(job))
        if container is not None:
            status, exit_code = _container_state(container)
            if status != "exited" or exit_code != 0:
                raise DriverError(f"cannot remove non-success score container for {job.job_id}")
            run_host(["docker", "rm", score_container_name(job)])
    for job in jobs:
        score_attempt(job)


def validate_loss_aggregate_outputs(loss_dir: Path) -> dict[str, Any]:
    """Re-open the complete 10-run loss cursor bundle and its SHA ledger."""

    output = loss_dir / LOSS_OUTPUT_NAME
    receipt_path = loss_dir / LOSS_RECEIPT_NAME
    receipt = load_json(receipt_path)
    require_equal(
        receipt.get("schema"),
        "jointbuildgs.pilot_1wave.loss_cursor_aggregate_receipt.v1",
        "loss aggregate receipt schema",
    )
    require_equal(receipt.get("state"), "complete", "loss aggregate state")
    require_equal(int(receipt.get("aggregate_row_count", -1)), 14_000,
                  "loss aggregate row count")
    require_equal(int(receipt.get("run_count", -1)), 10,
                  "loss aggregate run count")
    aggregate = receipt.get("aggregate_output") or {}
    require_equal(
        _resolve_declared_path(aggregate.get("path"), declaring_file=receipt_path),
        output.resolve(),
        "loss aggregate output path",
    )
    require_equal(aggregate.get("sha256"), sha256_file(output),
                  "loss aggregate output SHA")
    with output.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    require_equal(tuple(reader.fieldnames or ()), LOSS_OUTPUT_FIELDS,
                  "loss aggregate CSV fields")
    require_equal(len(rows), 14_000, "loss aggregate CSV rows")
    require_equal(tuple(aggregate.get("fields", ())), LOSS_OUTPUT_FIELDS,
                  "loss aggregate receipt fields")

    records = receipt.get("run_receipts")
    if not isinstance(records, list):
        raise DriverError("loss aggregate run receipt ledger is missing")
    require_equal(len(records), 10, "loss cursor run receipt count")
    normalized: list[dict[str, Any]] = []
    for (condition, seed), record in zip(_job_order(), records, strict=True):
        if not isinstance(record, Mapping):
            raise DriverError("loss aggregate run receipt record is not an object")
        require_equal(record.get("condition_id"), condition,
                      "loss run receipt condition")
        require_equal(int(record.get("seed", -1)), seed,
                      "loss run receipt seed")
        expected_path = loss_dir / "run_receipts" / f"{condition}_seed{seed}.json"
        declared = _resolve_declared_path(record.get("path"), declaring_file=receipt_path)
        require_equal(declared, expected_path.resolve(), "loss run receipt path")
        require_sha(declared, str(record.get("sha256")), "loss run receipt")
        normalized.append({
            "condition_id": condition,
            "seed": seed,
            "path": declared,
            "sha256": str(record.get("sha256")),
        })
    return {
        "output": output,
        "output_sha256": sha256_file(output),
        "receipt": receipt_path,
        "receipt_sha256": sha256_file(receipt_path),
        "run_receipts": normalized,
    }


def validate_numeric_loss_binding(output_dir: Path, loss_dir: Path) -> dict[str, Any]:
    """Prove the scoring manifest attests the exact 14k loss cursor bytes."""

    loss = validate_loss_aggregate_outputs(loss_dir)
    aggregate_copy = output_dir / LOSS_OUTPUT_NAME
    require_equal(sha256_file(aggregate_copy), loss["output_sha256"],
                  "numeric/loss cursor SHA")
    with aggregate_copy.open(newline="", encoding="utf-8") as stream:
        require_equal(len(list(csv.DictReader(stream))), 14_000,
                      "numeric loss cursor rows")
    scoring_manifest = load_json(output_dir / "pilot_1wave_manifest.json")
    record = (scoring_manifest.get("outputs") or {}).get(LOSS_OUTPUT_NAME)
    if not isinstance(record, Mapping):
        raise DriverError("scoring manifest lacks the loss cursor output record")
    require_equal(record.get("sha256"), loss["output_sha256"],
                  "scoring manifest loss cursor SHA")
    require_equal(int(record.get("row_count", -1)), 14_000,
                  "scoring manifest loss cursor rows")
    return loss


def run_numeric_aggregate(jobs: Sequence[Job], loss_dir: Path) -> Path:
    root = global_stage_root("aggregate")
    complete = completed_attempt(root, "aggregate", "global")
    if complete is not None:
        output = complete / "output"
        validate_numeric_loss_binding(output, loss_dir)
        return output
    attempt = next_attempt(root)
    output = attempt / "output"
    init = p0_command([
        "python3", container_path(SCORING), "init-schemas",
        "--output-dir", container_path(output),
    ])
    stage_command(init, attempt, "aggregate_init")
    loss = validate_loss_aggregate_outputs(loss_dir)
    atomic_bytes(output / LOSS_OUTPUT_NAME, loss["output"].read_bytes())
    require_equal(sha256_file(output / LOSS_OUTPUT_NAME), loss["output_sha256"],
                  "copied loss cursor SHA")
    aggregate_args = [
        "python3", container_path(SCORING), "aggregate-scores",
        "--output-dir", container_path(output),
    ]
    for job in jobs:
        aggregate_args.extend(["--run-score", container_path(score_attempt(job) / "scores.csv")])
    command = p0_command(aggregate_args)
    with (attempt / "aggregate.log").open("w", encoding="utf-8") as log:
        process = run_host(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if process.returncode != 0:
        raise DriverError(f"numeric aggregate failed; see {attempt/'aggregate.log'}")
    expected = [
        output / name
        for name in (*SCORE_OUTPUTS, LOSS_OUTPUT_NAME, "pilot_1wave_manifest.json")
    ]
    for path in expected:
        if not path.is_file() or path.stat().st_size <= 0:
            raise DriverError(f"numeric aggregate output missing/empty: {path}")
    with (output / "pilot_1wave_scores.csv").open(newline="", encoding="utf-8") as stream:
        require_equal(len(list(csv.DictReader(stream))), 390, "aggregate score rows")
    with (output / "pilot_1wave_seg_upperbound_gap.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        require_equal(len(list(csv.DictReader(stream))), 60, "segmentation gap rows")
    with (output / "pilot_1wave_winner.csv").open(newline="", encoding="utf-8") as stream:
        require_equal(len(list(csv.DictReader(stream))), 4, "winner rows")
    validate_numeric_loss_binding(output, loss_dir)
    write_stage_marker(attempt, "aggregate", "global", expected, {
        "run_score_count": 10,
        "loss_cursor_rows": 14_000,
        "loss_cursor_sha256": loss["output_sha256"],
    })
    return output


def run_loss_aggregate() -> Path:
    root = global_stage_root("loss_cursor")
    complete = completed_attempt(root, "loss_cursor", "global")
    if complete is not None:
        validate_loss_aggregate_outputs(complete)
        return complete
    attempt = next_attempt(root)
    output = attempt / LOSS_OUTPUT_NAME
    receipt = attempt / LOSS_RECEIPT_NAME
    receipts = attempt / "run_receipts"
    command = p0_command([
        "python3", container_path(LOSS_AGGREGATE),
        "--training-root", container_path(TRAINING_ROOT / "runs"),
        "--output", container_path(output),
        "--receipt", container_path(receipt),
        "--run-receipt-dir", container_path(receipts),
    ])
    stage_command(command, attempt, "loss_cursor")
    loss = validate_loss_aggregate_outputs(attempt)
    run_receipts = tuple(record["path"] for record in loss["run_receipts"])
    write_stage_marker(attempt, "loss_cursor", "global",
                       (output, receipt, *run_receipts), {"run_receipt_count": 10})
    return attempt


def binding_spec(jobs: Sequence[Job], path: Path) -> dict[str, Any]:
    runs = []
    for job in jobs:
        extract = extract_attempt(job)
        classify = classify_attempt(job)
        roofer = roofer_attempt(job)
        score = score_attempt(job)
        runs.append({
            "condition_id": job.condition,
            "seed": job.seed,
            "pilot_set": container_path(PILOT_SET),
            "pilot_manifest": container_path(PILOT_MANIFEST),
            "scene_npz": container_path(extract / "scene_geometry.npz"),
            "scene_provenance": container_path(extract / "provenance.json"),
            "classification_receipt": container_path(classify / "classification_receipt.json"),
            "roofprint_prepare_marker": container_path(roofer / "roofer_prepare.json"),
            "roofer_execution_receipt": container_path(
                roofer / "roofer_execution_receipt.json"
            ),
            "roofer_marker": container_path(roofer / "roofer_invocation.json"),
            "merged_cityjson": container_path(roofer / "assembled.city.json"),
            "score_marker": container_path(score / "score_invocation.json"),
            "score_csv": container_path(score / "scores.csv"),
        })
    payload = {"schema": BINDING_SPEC_SCHEMA, "runs": runs}
    atomic_json(path, payload)
    return payload


def validate_binding_batch_outputs(output: Path) -> dict[str, Any]:
    """Validate a complete binding batch without requiring its G1 to pass."""

    files = (
        output / "binding_audit.csv",
        output / "binding_audit_spatial_matrix.csv",
        output / "binding_audit_receipt.json",
    )
    with files[0].open(newline="", encoding="utf-8") as stream:
        require_equal(len(list(csv.DictReader(stream))), 300, "binding audit rows")
    with files[1].open(newline="", encoding="utf-8") as stream:
        require_equal(len(list(csv.DictReader(stream))), 9000, "binding matrix rows")
    receipt = load_json(files[2])
    require_equal(receipt.get("schema"),
                  "jointbuildgs.pilot_1wave.binding_batch_receipt.v1",
                  "binding batch receipt schema")
    require_equal(receipt.get("state"), "complete", "binding batch state")
    hard_gate = receipt.get("hard_gate_passed")
    global_g1 = receipt.get("global_g1")
    if not isinstance(hard_gate, bool):
        raise DriverError("binding batch hard_gate_passed must be boolean")
    if not isinstance(global_g1, Mapping) or not isinstance(global_g1.get("pass"), bool):
        raise DriverError("binding batch global_g1.pass must be boolean")
    require_equal(hard_gate, global_g1["pass"],
                  "binding batch hard gate/global G1 consistency")
    return receipt


def run_binding_batch(jobs: Sequence[Job]) -> Path:
    root = global_stage_root("binding")
    complete = completed_attempt(root, "binding", "global")
    if complete is not None:
        return complete / "output"
    attempt = next_attempt(root)
    output = attempt / "output"
    spec = attempt / "binding_batch_spec.json"
    binding_spec(jobs, spec)
    command = p0_command([
        "python3", container_path(BINDING_AUDIT), "batch",
        "--spec", container_path(spec), "--output-dir", container_path(output),
    ])
    stage_command(command, attempt, "binding")
    files = (
        output / "binding_audit.csv",
        output / "binding_audit_spatial_matrix.csv",
        output / "binding_audit_receipt.json",
    )
    receipt = validate_binding_batch_outputs(output)
    write_stage_marker(attempt, "binding", "global", (spec, *files), {
        "building_rows": 300, "matrix_rows": 9000,
        "hard_gate_passed": receipt["hard_gate_passed"],
    })
    return output


def evaluate_g1(binding_dir: Path) -> dict[str, Any]:
    with (binding_dir / "binding_audit.csv").open(newline="", encoding="utf-8") as stream:
        buildings = list(csv.DictReader(stream))
    with (binding_dir / "binding_audit_spatial_matrix.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        matrix = list(csv.DictReader(stream))
    mismatch_fields = ("crop_contract_sha_match", "classification_receipt_sha_match")
    sha_mismatches = sum(
        not bool_value(row.get(field)) for row in buildings for field in mismatch_fields
    )
    xy_owner_mismatches = sum(
        not bool_value(row.get("spatial_owner_matches_parent"))
        or not bool_value(row.get("cityjson_owner_match"))
        for row in buildings
    )
    containment_mismatches = sum(
        not bool_value(row.get("owner_contained")) for row in buildings
    )
    run_checks: list[dict[str, Any]] = []
    for condition, seed in _job_order():
        rows = [row for row in matrix if row.get("condition_id") == condition
                and int(row.get("seed", -1)) == seed]
        assigned = [row for row in rows if bool_value(row.get("owner_assignment"))]
        row_sums = Counter(row["locked_building_id"] for row in assigned)
        col_sums = Counter(row["output_parent_id"] for row in assigned)
        diagonal = sum(bool_value(row.get("is_diagonal")) for row in assigned)
        offdiag = len(assigned) - diagonal
        passed = (
            len(rows) == 900 and len(assigned) == 30
            and set(row_sums) == set(EXPECTED_IDS)
            and set(col_sums) == set(EXPECTED_IDS)
            and all(value == 1 for value in row_sums.values())
            and all(value == 1 for value in col_sums.values())
            and diagonal == 30 and offdiag == 0
        )
        run_checks.append({
            "condition_id": condition, "seed": seed, "matrix_rows": len(rows),
            "owner_assignments": len(assigned), "row_sum_one_count": sum(
                value == 1 for value in row_sums.values()),
            "column_sum_one_count": sum(value == 1 for value in col_sums.values()),
            "diagonal_assignments": diagonal, "offdiagonal_assignments": offdiag,
            "pass": passed,
        })
    passed = (
        len(buildings) == 300 and len(matrix) == 9000
        and sha_mismatches == 0 and xy_owner_mismatches == 0
        and containment_mismatches == 0
        and len(run_checks) == 10 and all(row["pass"] for row in run_checks)
    )
    return {
        "gate": "G1", "status": "pass" if passed else "fail",
        "binding_rows": len(buildings), "spatial_rows": len(matrix),
        "crop_or_receipt_sha_mismatch_count": sha_mismatches,
        "cityjson_xy_owner_argmax_mismatch_count": xy_owner_mismatches,
        "assigned_owner_containment_mismatch_count": containment_mismatches,
        "runs": run_checks,
    }


def evaluate_g2_g3(winner_csv: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with winner_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    conditions = tuple(row.get("condition_id") for row in rows)
    honest_set_ok = len(rows) == 4 and set(conditions) == set(HONEST_CONDITIONS) and "04b" not in conditions
    minima = [row for row in rows if bool_value(row.get("eligible_two_seed_rule"))
              and bool_value(row.get("is_minimum_worst_rms"))]
    unique = (
        honest_set_ok and len(minima) == 1
        and int(minima[0].get("co_minimum_count", 0)) == 1
        and bool_value(minima[0].get("seed_1001_rule_abcd"))
        and bool_value(minima[0].get("seed_1002_rule_abcd"))
        and int(minima[0].get("rule_abcd_seed_count", 0)) == 2
    )
    best = None if not minima else float(minima[0]["worst_seed_roof_rms_median_m"])
    g2 = {
        "gate": "G2", "status": "pass" if unique else "fail",
        "honest_row_count": len(rows), "honest_condition_set_exact": honest_set_ok,
        "unique_minimum_count": len(minima),
        "winner_condition_id": None if not minima else minima[0]["condition_id"],
        "co_minimum_count": None if not minima else int(minima[0]["co_minimum_count"]),
        "both_seeds_rule_abcd": False if not minima else (
            bool_value(minima[0]["seed_1001_rule_abcd"])
            and bool_value(minima[0]["seed_1002_rule_abcd"])
        ),
    }
    g3_pass = best is not None and best < 2.0
    g3 = {
        "gate": "G3", "status": "pass" if g3_pass else "fail",
        "best_honest_worst_seed_rms_median_m": best,
        "threshold_m": 2.0, "strictly_below_threshold": g3_pass,
    }
    return g2, g3


def evaluate_g4(training: Mapping[str, Any], abort_events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw = training.get("training") or {}
    jobs = raw.get("jobs") or []
    guard = raw.get("guard") or {}
    completed_20k = int(raw.get("canonical_completed_20k_count", -1))
    collapse = int(raw.get("canonical_collapse_count", -1))
    divergence = int(raw.get("canonical_divergence_count", -1))
    guard_abort = int(raw.get("canonical_guard_abort_count", -1))
    complete = (
        len(jobs) == 10 and completed_20k == 10
        and collapse == 0 and divergence == 0 and guard_abort == 0
        and guard.get("triggered") is False
        and guard.get("partial") is False and guard.get("completion") is True
        and len(abort_events) == 0
    )
    return {
        "gate": "G4", "status": "pass" if complete else "fail",
        "canonical_definition": (
            "exact 10 bound manifests completed at 20k; collapse=0; divergence=0; "
            "guard_abort=0; postprocess_abort=0"
        ),
        "canonical_training_run_count": len(jobs),
        "canonical_training_completed_20k_count": completed_20k,
        "canonical_training_collapse_count": collapse,
        "canonical_training_divergence_count": divergence,
        "canonical_training_guard_abort_count": guard_abort,
        "postprocess_abort_count": len(abort_events),
        "historical_learning_runs_started": raw.get("historical_learning_runs_started"),
        "historical_failed_attempt_archive_count": raw.get(
            "historical_failed_attempt_archive_count"
        ),
        "historical_failed_attempt_archives": raw.get(
            "historical_failed_attempt_archives", []
        ),
        "historical_failed_postprocess_attempt_archive_count": raw.get(
            "historical_failed_postprocess_attempt_archive_count"
        ),
        "historical_failed_postprocess_attempt_archives": raw.get(
            "historical_failed_postprocess_attempt_archives", []
        ),
        "history_excluded_from_canonical_gate_counts": True,
    }


def machine_gates(binding_dir: Path, aggregate_dir: Path,
                  preflight_payload: Mapping[str, Any],
                  abort_events: Sequence[Mapping[str, Any]], *,
                  created_utc: str | None = None) -> dict[str, Any]:
    g1 = evaluate_g1(binding_dir)
    g2, g3 = evaluate_g2_g3(aggregate_dir / "pilot_1wave_winner.csv")
    g4 = evaluate_g4(preflight_payload, abort_events)
    return {
        "schema": "jointbuildgs.pilot_1wave.machine_gates.v1",
        "created_utc": created_utc or now(),
        "G1": g1, "G2": g2, "G3": g3, "G4": g4,
        "raw_numeric_status_only": True, "interpretation_or_verdict": None,
    }


def publication_gate_inputs(binding_dir: Path, aggregate_dir: Path,
                            preflight_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Hash every byte/value from which the frozen machine gates are derived."""

    paths = {
        "binding_audit": binding_dir / "binding_audit.csv",
        "binding_spatial_matrix": binding_dir / "binding_audit_spatial_matrix.csv",
        "winner": aggregate_dir / "pilot_1wave_winner.csv",
    }
    records: dict[str, Any] = {}
    for name, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise DriverError(f"publication gate input is missing/non-regular: {path}")
        records[name] = {
            "path": repo_relative(path),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
    training = preflight_payload.get("training")
    if not isinstance(training, Mapping):
        raise DriverError("preflight training record is missing")
    records["training_record_sha256"] = sha256_bytes(canonical_json(dict(training)))
    return records


def freeze_publication_snapshot(
    state: dict[str, Any],
    *,
    binding_dir: Path,
    aggregate_dir: Path,
    preflight_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Create once, then re-open the immutable inputs to publication bytes.

    Abort events accumulated before this boundary participate in G4.  Events
    caused by an interrupted partial publication remain visible in driver
    state, but cannot mutate already-published gate/receipt bytes on resume.
    """

    gate_inputs = publication_gate_inputs(
        binding_dir, aggregate_dir, preflight_payload
    )
    current_wave2 = preflight_payload.get("wave2_launch")
    if not isinstance(current_wave2, Mapping):
        raise DriverError("preflight Wave 2 launch record is missing")
    existing = state.get("publication_snapshot")
    if existing is not None:
        if not isinstance(existing, Mapping):
            raise DriverError("publication snapshot is not an object")
        require_equal(existing.get("schema"), PUBLICATION_SNAPSHOT_SCHEMA,
                      "publication snapshot schema")
        require_equal(existing.get("correction_head"),
                      preflight_payload.get("correction_head"),
                      "publication snapshot correction HEAD")
        require_equal(existing.get("gate_inputs"), gate_inputs,
                      "publication snapshot gate inputs")
        require_equal(existing.get("wave2_launch"), dict(current_wave2),
                      "publication snapshot Wave 2 lock")
        timestamps = existing.get("timestamps")
        if not isinstance(timestamps, Mapping):
            raise DriverError("publication snapshot timestamps are missing")
        require_equal(set(timestamps), {
            "machine_gates_created_utc", "postprocess_completed_utc", "published_utc"
        }, "publication snapshot timestamp keys")
        if any(not isinstance(value, str) or not value for value in timestamps.values()):
            raise DriverError("publication snapshot timestamps must be non-empty strings")
        abort_events = existing.get("abort_events")
        if not isinstance(abort_events, list) or any(
            not isinstance(value, Mapping) for value in abort_events
        ):
            raise DriverError("publication snapshot abort event ledger is invalid")
        expected_gates = machine_gates(
            binding_dir,
            aggregate_dir,
            preflight_payload,
            abort_events,
            created_utc=str(timestamps["machine_gates_created_utc"]),
        )
        require_equal(existing.get("machine_gates"), expected_gates,
                      "publication snapshot machine gates")
        return dict(existing)

    abort_events = state.get("abort_events", [])
    if not isinstance(abort_events, list) or any(
        not isinstance(value, Mapping) for value in abort_events
    ):
        raise DriverError("driver abort event ledger is invalid")
    # Round-trip through canonical JSON to ensure later mutation of driver
    # state cannot mutate the snapshot's nested event records by reference.
    frozen_aborts = json.loads(canonical_json(abort_events))
    timestamps = {
        "machine_gates_created_utc": now(),
        "postprocess_completed_utc": now(),
        "published_utc": now(),
    }
    gates = machine_gates(
        binding_dir,
        aggregate_dir,
        preflight_payload,
        frozen_aborts,
        created_utc=timestamps["machine_gates_created_utc"],
    )
    snapshot = {
        "schema": PUBLICATION_SNAPSHOT_SCHEMA,
        "correction_head": preflight_payload.get("correction_head"),
        "gate_inputs": gate_inputs,
        "timestamps": timestamps,
        "abort_events": frozen_aborts,
        "machine_gates": gates,
        "wave2_launch": json.loads(canonical_json(dict(current_wave2))),
    }
    state["publication_snapshot"] = snapshot
    return snapshot


def publish_immutable(source: Path, target: Path) -> str:
    if not source.is_file() or source.is_symlink():
        raise DriverError(f"publication source is missing/non-regular: {source}")
    data = source.read_bytes()
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise DriverError(f"publication target is not a regular file: {target}")
        if target.read_bytes() != data:
            raise DriverError(f"refusing to replace different publication: {target}")
        return "already_present_identical"
    atomic_bytes(target, data)
    return "published"


def publish_allowlisted_files(
    sources: Mapping[str, Path],
    target_root: Path,
    *,
    publisher: Callable[[Path, Path], str] = publish_immutable,
) -> dict[str, dict[str, Any]]:
    """Publish deterministic bytes; records never depend on crash position."""

    require_equal(set(sources), set(PUBLISH_ALLOWLIST), "publication allowlist")
    target_root.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    for name in PUBLISH_ALLOWLIST:
        source = sources[name]
        publisher(source, target_root / name)
        records[name] = {
            "sha256": sha256_file(source),
            "size": source.stat().st_size,
            "source": repo_relative(source),
            "publication_state": "published_or_verified_identical",
        }
    return records


def postprocess_receipt_payload(
    *,
    jobs: Sequence[Job],
    preflight_payload: Mapping[str, Any],
    publication_snapshot: Mapping[str, Any],
    roofer_execution_receipts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build bytes only from the pre-publication immutable snapshot."""

    timestamps = publication_snapshot.get("timestamps")
    abort_events = publication_snapshot.get("abort_events")
    wave2 = publication_snapshot.get("wave2_launch")
    if not isinstance(timestamps, Mapping):
        raise DriverError("publication snapshot timestamps are missing")
    if not isinstance(abort_events, list):
        raise DriverError("publication snapshot abort events are missing")
    if not isinstance(wave2, Mapping):
        raise DriverError("publication snapshot Wave 2 record is missing")
    return {
        "schema": DRIVER_SCHEMA,
        "state": "complete",
        "completed_utc": timestamps["postprocess_completed_utc"],
        "source_run_id": SOURCE_RUN_ID,
        "readout_run_id": READOUT_RUN_ID,
        "correction_head": preflight_payload["correction_head"],
        "learning_runs_started_by_postprocess": 0,
        "roofer_invocation_count": 10,
        "score_invocation_count": 10,
        "roofer_execution_receipts": dict(roofer_execution_receipts),
        "job_order": [job.job_id for job in jobs],
        "wave2_launch": dict(wave2),
        "abort_events": list(abort_events),
    }


def final_preflight_provenance(preflight_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Select the complete verified preflight facts required by the package."""

    require_equal(preflight_payload.get("tracked_tree_clean"), True,
                  "published preflight tracked tree")
    correction_head = str(preflight_payload.get("correction_head", ""))
    if re.fullmatch(r"[0-9a-f]{40}", correction_head) is None:
        raise DriverError("published preflight correction HEAD is invalid")
    result: dict[str, Any] = {"correction_head": correction_head}
    for key in FINAL_PREFLIGHT_PROVENANCE_KEYS:
        value = preflight_payload.get(key)
        if not isinstance(value, Mapping) or not value:
            raise DriverError(f"published preflight {key} is missing")
        result[key] = json.loads(canonical_json(dict(value)))
    return result


def publish_results(
    *, jobs: Sequence[Job], preflight_payload: Mapping[str, Any],
    aggregate_dir: Path, loss_dir: Path, binding_dir: Path,
    publication_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    gates = publication_snapshot.get("machine_gates")
    wave2 = publication_snapshot.get("wave2_launch")
    publication_timestamps = publication_snapshot.get("timestamps")
    if not isinstance(gates, Mapping):
        raise DriverError("publication snapshot machine gates are missing")
    if not isinstance(wave2, Mapping):
        raise DriverError("publication snapshot Wave 2 record is missing")
    if not isinstance(publication_timestamps, Mapping):
        raise DriverError("publication snapshot timestamps are missing")
    provenance = final_preflight_provenance(preflight_payload)
    loss = validate_numeric_loss_binding(aggregate_dir, loss_dir)
    existing_manifest = PUBLICATION_ROOT / FINAL_MANIFEST_NAME
    if existing_manifest.is_file():
        existing = load_json(existing_manifest)
        require_equal(existing.get("schema"), PUBLICATION_SCHEMA,
                      "existing publication schema")
        require_equal(existing.get("state"), "complete",
                      "existing publication state")
        require_equal(existing.get("correction_head"),
                      preflight_payload["correction_head"],
                      "existing publication correction HEAD")
        for key in FINAL_PREFLIGHT_PROVENANCE_KEYS:
            require_equal(existing.get(key), provenance[key],
                          f"existing publication {key}")
        outputs = existing.get("outputs")
        if not isinstance(outputs, Mapping):
            raise DriverError("existing publication output ledger is missing")
        require_equal(set(outputs), set(PUBLISH_ALLOWLIST),
                      "existing publication allowlist")
        for name, record in outputs.items():
            if not isinstance(record, Mapping):
                raise DriverError(f"existing publication record is invalid: {name}")
            path = PUBLICATION_ROOT / name
            require_equal(path.stat().st_size, int(record.get("size", -1)),
                          f"existing publication size {name}")
            require_equal(sha256_file(path), record.get("sha256"),
                          f"existing publication SHA {name}")
        return existing
    staging = global_stage_root("publication") / "payload"
    staging.mkdir(parents=True, exist_ok=True)
    pilot_manifest = load_json(PILOT_MANIFEST)
    selection = pilot_manifest.get("selection") or {}
    lock_payload = selection.get("lock_payload")
    if not isinstance(lock_payload, Mapping):
        raise DriverError("pilot manifest selection lock payload is missing")
    selection_lock_path = staging / "pilot_1wave_selection_lock.json"
    selection_lock_bytes = canonical_json(lock_payload)
    require_equal(sha256_bytes(selection_lock_bytes), SELECTION_SHA256,
                  "materialized selection lock SHA")
    atomic_bytes(selection_lock_path, selection_lock_bytes)
    ordered_ids_path = staging / "pilot_1wave_ordered_30_ids.txt"
    ordered_ids_bytes = ("\n".join(EXPECTED_IDS) + "\n").encode("utf-8")
    require_equal(sha256_bytes(ordered_ids_bytes), ORDERED_IDS_SHA256,
                  "materialized ordered 30 IDs SHA")
    atomic_bytes(ordered_ids_path, ordered_ids_bytes)
    roofprint_attempt = completed_attempt(
        global_stage_root("roofprint"), "roofprint", "global"
    )
    if roofprint_attempt is None:
        raise DriverError("global locked roofprint stage is incomplete")
    roofprints = roofprint_attempt / "locked_roofprints.geojson"
    ordered_geometry_sha256 = roofprint_ordered_geometry_sha256(roofprints)
    roofprint_sha256 = sha256_file(roofprints)
    for job in jobs:
        classification = load_json(
            classify_attempt(job) / "classification_receipt.json"
        )
        require_equal((classification.get("roofprints") or {}).get("sha256"),
                      roofprint_sha256,
                      f"{job.job_id} publication roofprint SHA")
    roofprint_binding_path = POSTPROCESS_ROOT / "roofprint_binding_receipt.json"
    roofprint_binding = load_json(roofprint_binding_path)
    require_equal(roofprint_binding.get("roofprint_sha256"), roofprint_sha256,
                  "published cross-run roofprint SHA")
    require_equal(roofprint_binding.get("ordered_geometry_sha256"),
                  ordered_geometry_sha256,
                  "published cross-run roofprint geometry SHA")
    sources: dict[str, Path] = {
        "pilot_1wave_pilot_set.csv": PILOT_SET,
        "pilot_1wave_pilot_set_manifest.json": PILOT_MANIFEST,
        "pilot_1wave_selection_lock.json": selection_lock_path,
        "pilot_1wave_ordered_30_ids.txt": ordered_ids_path,
        "pilot_1wave_locked_roofprints.geojson": roofprints,
        **{name: aggregate_dir / name for name in SCORE_OUTPUTS},
        LOSS_OUTPUT_NAME: aggregate_dir / LOSS_OUTPUT_NAME,
        LOSS_RECEIPT_NAME: loss["receipt"],
        "binding_audit.csv": binding_dir / "binding_audit.csv",
        "binding_audit_spatial_matrix.csv": binding_dir / "binding_audit_spatial_matrix.csv",
        "binding_audit_receipt.json": binding_dir / "binding_audit_receipt.json",
        "pilot_1wave_scoring_manifest.json": aggregate_dir / "pilot_1wave_manifest.json",
    }
    for published_name, record in zip(
        LOSS_RUN_RECEIPT_OUTPUTS, loss["run_receipts"], strict=True
    ):
        sources[published_name] = record["path"]
    gates_path = staging / "pilot_1wave_machine_gates.json"
    atomic_json(gates_path, gates)
    sources[gates_path.name] = gates_path
    roofer_execution_receipts: dict[str, dict[str, Any]] = {}
    for job in jobs:
        execution_path = roofer_attempt(job) / "roofer_execution_receipt.json"
        execution = load_json(execution_path)
        require_equal(execution.get("schema"),
                      "jointbuildgs.pilot_1wave.roofer_execution.v1",
                      f"{job.job_id} published Roofer execution schema")
        require_equal(execution.get("state"), "complete",
                      f"{job.job_id} published Roofer execution state")
        require_equal(int(execution.get("roofer_invocation_count", -1)), 1,
                      f"{job.job_id} published Roofer invocation count")
        roofer_execution_receipts[job.job_id] = {
            "path": repo_relative(execution_path),
            "sha256": sha256_file(execution_path),
        }
    receipt_path = staging / "pilot_1wave_postprocess_receipt.json"
    receipt = postprocess_receipt_payload(
        jobs=jobs,
        preflight_payload=preflight_payload,
        publication_snapshot=publication_snapshot,
        roofer_execution_receipts=roofer_execution_receipts,
    )
    atomic_json(receipt_path, receipt)
    sources[receipt_path.name] = receipt_path
    publication_records = publish_allowlisted_files(sources, PUBLICATION_ROOT)
    publication_records["pilot_1wave_locked_roofprints.geojson"][
        "ordered_geometry_sha256"
    ] = ordered_geometry_sha256
    final_manifest = {
        "schema": PUBLICATION_SCHEMA, "state": "complete",
        "published_utc": publication_timestamps["published_utc"],
        "source_run_id": SOURCE_RUN_ID,
        "readout_run_id": READOUT_RUN_ID,
        **provenance,
        "selection_sha256": SELECTION_SHA256,
        "ordered_ids_sha256": ORDERED_IDS_SHA256,
        "pilot_set_sha256": PILOT_SET_SHA256,
        "pilot_manifest_sha256": PILOT_MANIFEST_SHA256,
        "locked_roofprint_sha256": roofprint_sha256,
        "locked_roofprint_ordered_geometry_sha256": ordered_geometry_sha256,
        "cross_run_roofprint_binding_receipt": {
            "path": repo_relative(roofprint_binding_path),
            "sha256": sha256_file(roofprint_binding_path),
        },
        "crop_bbox": list(CROP_BBOX), "view_count": VIEW_COUNT,
        "images": preflight_payload["images"],
        "training": preflight_payload["training"],
        "roofer_execution_receipts": roofer_execution_receipts,
        "machine_gates": gates,
        "wave2_launch": dict(wave2),
        "outputs": publication_records,
        "loss_share_run_receipts": [
            {
                "condition_id": condition,
                "seed": seed,
                "published_path": published_name,
                "source": publication_records[published_name]["source"],
                "sha256": publication_records[published_name]["sha256"],
            }
            for (condition, seed), published_name in zip(
                _job_order(), LOSS_RUN_RECEIPT_OUTPUTS, strict=True
            )
        ],
        "manifest_published_last": True,
        "learning_runs_started_by_postprocess": 0,
        "interpretation_or_verdict": None,
    }
    manifest_target = PUBLICATION_ROOT / FINAL_MANIFEST_NAME
    manifest_bytes = json.dumps(final_manifest, ensure_ascii=False, indent=2,
                                allow_nan=False).encode("utf-8") + b"\n"
    if manifest_target.exists():
        if manifest_target.read_bytes() != manifest_bytes:
            raise DriverError("different final readout manifest already exists")
    else:
        atomic_bytes(manifest_target, manifest_bytes)
    return final_manifest


def barrier_status(jobs: Sequence[Job]) -> dict[str, Any]:
    stages = ("extract", "classify", "prepare", "finalize", "score")
    result: dict[str, Any] = {}
    for stage in stages:
        complete = 0
        for job in jobs:
            if completed_attempt(stage_root(job, stage), stage, job.job_id):
                complete += 1
        result[stage] = {"complete": complete, "expected": 10,
                         "state": "complete" if complete == 10 else "pending"}
    return result


def dry_run_plan(jobs: Sequence[Job], preflight_payload: Mapping[str, Any]) -> dict[str, Any]:
    commands = []
    policy = preflight_payload.get("extract_policy_lock") or {}
    require_equal(policy.get("max_parallel"), 1, "dry-run extract max parallel")
    require_equal(policy.get("sha256"), EXTRACT_POLICY_LOCK_SHA256,
                  "dry-run extract policy SHA")
    for serial_ordinal, job in enumerate(jobs, 1):
        placeholder = stage_root(job, "extract") / "attempt_NNN"
        commands.append({"stage": "extract", "job_id": job.job_id, "gpu": job.gpu,
                         "serial_ordinal": serial_ordinal, "max_parallel": 1,
                         "command": dev_extract_command(job, placeholder)})
    commands.append({
        "stage": "roofprint", "job_id": "global",
        "command": p0_command(["python3", container_path(SCORING), "prepare-roofprints",
                               "--output", "<attempt>/locked_roofprints.geojson"]),
    })
    return {
        "schema": DRIVER_SCHEMA, "mode": "dry-run", "preflight": preflight_payload,
        "barriers": ["extract_10_serial_seed_pinned", "classify_10_one_roofprint", "prepare_10",
                     "roofer_10_exact_once", "finalize_10", "score_10_after_finalize",
                     "loss_cursor", "aggregate_with_bound_loss", "binding",
                     "publish_manifest_last"],
        "extract_schedule": {
            "mode": "serial", "max_parallel": 1,
            "policy_sha256": EXTRACT_POLICY_LOCK_SHA256,
            "job_order": [job.job_id for job in jobs],
        },
        "commands": commands,
        "gpu_work_started": 0, "roofer_invocations_started": 0,
        "score_invocations_started": 0,
    }


@contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load_state() -> dict[str, Any]:
    path = POSTPROCESS_ROOT / "driver_state.json"
    if not path.is_file():
        return {
            "schema": DRIVER_SCHEMA, "state": "not_started", "abort_events": [],
            "learning_runs_started_by_postprocess": 0,
        }
    return load_json(path)


def require_resume_contract(state: Mapping[str, Any],
                            preflight_payload: Mapping[str, Any], *,
                            has_stage_outputs: bool) -> None:
    current_head = str(preflight_payload.get("correction_head", ""))
    previous_head = state.get("correction_head")
    if previous_head is not None and previous_head != current_head:
        raise DriverError(
            f"postprocess correction HEAD changed: {previous_head} != {current_head}"
        )
    if has_stage_outputs and previous_head is None:
        raise DriverError("existing postprocess outputs have no correction HEAD binding")
    previous_sources = ((state.get("preflight") or {}).get("committed_runtime_sources"))
    current_sources = preflight_payload.get("committed_runtime_sources")
    if previous_sources is not None and previous_sources != current_sources:
        raise DriverError("postprocess runtime source SHA map changed across resume")
    previous_policy = ((state.get("preflight") or {}).get("extract_policy_lock"))
    current_policy = preflight_payload.get("extract_policy_lock")
    if previous_policy is not None and previous_policy != current_policy:
        raise DriverError("postprocess extract policy changed across resume")


def save_state(state: Mapping[str, Any]) -> None:
    atomic_json(POSTPROCESS_ROOT / "driver_state.json", state)


def execute_resume(jobs: Sequence[Job], preflight_payload: Mapping[str, Any]) -> dict[str, Any]:
    state = load_state()
    has_stage_outputs = ATTEMPTS_ROOT.is_dir() and any(
        path.is_dir() for path in ATTEMPTS_ROOT.rglob("attempt_[0-9][0-9][0-9]")
    )
    require_resume_contract(state, preflight_payload,
                            has_stage_outputs=has_stage_outputs)
    state.update({
        "schema": DRIVER_SCHEMA, "state": "running", "updated_utc": now(),
        "correction_head": preflight_payload["correction_head"],
        "preflight": preflight_payload,
        "learning_runs_started_by_postprocess": 0,
    })
    state.setdefault("started_utc", now())
    state.setdefault("abort_events", [])
    save_state(state)
    try:
        run_extract_barrier(jobs, preflight_payload["extract_policy_lock"])
        state["barriers"] = barrier_status(jobs); save_state(state)
        roofprints = prepare_global_roofprint()
        run_classify_barrier(jobs, roofprints)
        state["barriers"] = barrier_status(jobs); save_state(state)
        prepared = run_prepare_barrier(jobs)
        state["barriers"] = barrier_status(jobs); save_state(state)
        run_roofer_barrier(jobs, prepared)
        run_finalize_barrier(jobs, prepared)
        state["barriers"] = barrier_status(jobs); save_state(state)
        run_score_barrier(jobs)
        state["barriers"] = barrier_status(jobs); save_state(state)
        loss = run_loss_aggregate()
        aggregate = run_numeric_aggregate(jobs, loss)
        binding = run_binding_batch(jobs)
        publication_snapshot = freeze_publication_snapshot(
            state,
            binding_dir=binding,
            aggregate_dir=aggregate,
            preflight_payload=preflight_payload,
        )
        # This durable write is the publication boundary.  Any later abort is
        # appended to live driver state but cannot alter the frozen gate or
        # receipt bytes when a partial publication resumes.
        save_state(state)
        gates = publication_snapshot["machine_gates"]
        wave2 = publication_snapshot["wave2_launch"]
        publication_timestamps = publication_snapshot["timestamps"]
        final = publish_results(
            jobs=jobs, preflight_payload=preflight_payload, aggregate_dir=aggregate,
            loss_dir=loss, binding_dir=binding,
            publication_snapshot=publication_snapshot,
        )
        state.update({
            "state": "complete",
            "completed_utc": publication_timestamps["postprocess_completed_utc"],
            "machine_gates": gates,
            "wave2_launch": wave2,
            "publication_manifest": repo_relative(PUBLICATION_ROOT / FINAL_MANIFEST_NAME),
            "publication_manifest_sha256": sha256_file(
                PUBLICATION_ROOT / FINAL_MANIFEST_NAME
            ),
        })
        save_state(state)
        return final
    except Exception as exc:
        event = {"at": now(), "type": type(exc).__name__, "message": str(exc)}
        state.setdefault("abort_events", []).append(event)
        state.update({"state": "aborted", "updated_utc": now(), "last_error": event})
        save_state(state)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="mode", required=True)
    status = sub.add_parser("status", help="read state and Docker container status only")
    status.add_argument("--correction-head")
    for name in ("preflight", "dry-run", "resume"):
        command = sub.add_parser(name)
        command.add_argument("--correction-head", required=True)
        command.add_argument("--wave2-lock", type=Path)
        command.add_argument("--wave2-lock-sha256")
    return result


def status_payload(expected_head: str | None = None) -> dict[str, Any]:
    state = load_state()
    jobs = [Job(i, condition, seed, f"{condition}_seed{seed}",
                TRAINING_ROOT / "runs" / condition / f"seed_{seed}", Path(), "",
                Path(), Path(), "")
            for i, (condition, seed) in enumerate(_job_order(), 1)]
    containers = {}
    for job in jobs:
        for role, name in (("roofer", roofer_container_name(job)),
                           ("score", score_container_name(job))):
            record = inspect_container(name)
            containers[f"{job.job_id}:{role}"] = None if record is None else {
                "name": name, "state": _container_state(record)[0],
                "exit_code": _container_state(record)[1], "id": record.get("Id"),
            }
    return {
        "schema": DRIVER_SCHEMA, "mode": "status", "git_head": query_git_head(),
        "expected_head_match": None if expected_head is None else query_git_head() == expected_head,
        "driver_state": state, "barriers": barrier_status(jobs),
        "retained_containers": containers,
        "publication_manifest_exists": (PUBLICATION_ROOT / FINAL_MANIFEST_NAME).is_file(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.mode == "status":
        print(json.dumps(status_payload(args.correction_head), ensure_ascii=False,
                         indent=2, allow_nan=False))
        return 0
    jobs, checked = preflight(args.correction_head, args.wave2_lock,
                              args.wave2_lock_sha256)
    if args.mode == "preflight":
        print(json.dumps(checked, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if args.mode == "dry-run":
        print(json.dumps(dry_run_plan(jobs, checked), ensure_ascii=False,
                         indent=2, allow_nan=False))
        return 0
    with exclusive_lock(POSTPROCESS_ROOT / "driver.lock"):
        final = execute_resume(jobs, checked)
    print(json.dumps({
        "state": final["state"], "manifest": repo_relative(
            PUBLICATION_ROOT / FINAL_MANIFEST_NAME
        ), "machine_gates": final["machine_gates"],
        "wave2_launch": final["wave2_launch"],
    }, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
