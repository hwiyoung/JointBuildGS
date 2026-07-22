"""Strict byte inventory for the quality-axis pilot Stage-2 inputs.

The pilot resolves its RGB, COLMAP SfM, geometric MVS depth/normal, and
Omnidata normal files before any optimizer result exists.  This module is the
runtime half of that contract: it rejects a missing, substituted, duplicated,
or mutated file before dataset/model construction and can be called again
before a run is marked complete.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


MATERIALIZED_INPUT_INVENTORY_SCHEMA = (
    "jointbuildgs.pilot_1wave.materialized_input_inventory.v1"
)
PILOT_RUN_ID = "20260721_pilot_1wave"
MATERIALIZED_INPUT_MODE = "result_blind_materialized_stage2_inputs"
MATERIALIZED_INPUT_VERIFICATION_SCHEMA = (
    "jointbuildgs.pilot_1wave.materialized_input_verification.v1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INVENTORY_KEYS = {
    "schema",
    "run_id",
    "mode",
    "data_root",
    "mono_normal_dir",
    "view_ids",
    "view_count",
    "role_counts",
    "file_count",
    "total_bytes",
    "records",
    "records_sha256",
    "learning_runs_started",
    "optimizer_updates",
}
_BASE_RECORD_KEYS = {"role", "path", "size_bytes", "sha256"}


class PilotInputInventoryError(RuntimeError):
    """A published pilot input inventory or one of its bytes drifted."""


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_file_sha256(path: Path, field: str) -> tuple[int, str]:
    if not path.is_file() or path.is_symlink():
        raise PilotInputInventoryError(
            f"{field} must be a regular non-symlink file: {path}"
        )
    try:
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
    except OSError as exc:
        raise PilotInputInventoryError(f"cannot hash {field} at {path}: {exc}") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity:
        raise PilotInputInventoryError(f"{field} changed while it was hashed: {path}")
    return int(after.st_size), digest


def _stable_file_bytes(path: Path, field: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise PilotInputInventoryError(
            f"{field} must be a regular non-symlink file: {path}"
        )
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise PilotInputInventoryError(f"cannot read {field} at {path}: {exc}") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise PilotInputInventoryError(f"{field} changed while it was read: {path}")
    return payload


def _require_nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise PilotInputInventoryError(f"{field} must be a non-negative integer")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PilotInputInventoryError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _repo_relative(repo: Path, path: Path, field: str) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as exc:
        raise PilotInputInventoryError(
            f"{field} escapes the repository root: {path}"
        ) from exc


def _reject_symlink_components(repo: Path, path: Path, field: str) -> Path:
    """Return a normalized in-repo path without accepting symlink aliases.

    Resolving first and checking ``is_symlink`` afterwards loses the fact that
    the configured leaf (or one of its parents) was a symlink.  Pilot input
    identity is path-and-byte based, so reject every symlink component before
    resolving the path.
    """

    repo = repo.resolve()
    lexical = Path(os.path.abspath(path))
    try:
        relative = lexical.relative_to(repo)
    except ValueError as exc:
        raise PilotInputInventoryError(
            f"{field} escapes the repository root: {path}"
        ) from exc
    cursor = repo
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PilotInputInventoryError(
                f"{field} must not contain a symlink component: {cursor}"
            )
    return lexical.resolve()


def _resolve_relative(repo: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PilotInputInventoryError(
            f"{field} must be a nonempty repository-relative path"
        )
    raw = Path(value)
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise PilotInputInventoryError(
            f"{field} must be a repository-relative path: {value!r}"
        )
    path = _reject_symlink_components(repo, repo / raw, field)
    _repo_relative(repo, path, field)
    return path


def _resolve_config_path(repo: Path, value: Any, field: str) -> Path:
    """Resolve one pinned absolute path from a generated pilot config."""

    if not isinstance(value, str) or not value:
        raise PilotInputInventoryError(f"pilot config requires nonempty {field}")
    raw = Path(value)
    if not raw.is_absolute():
        raise PilotInputInventoryError(
            f"pilot config {field} must be an absolute in-repository path"
        )
    return _reject_symlink_components(repo, raw, f"pilot config {field}")


def _input_record(
    repo: Path,
    path: Path,
    role: str,
    view_id: str | None = None,
) -> dict[str, Any]:
    path = _reject_symlink_components(repo, path, role)
    size_bytes, digest = _stable_file_sha256(path, role)
    record: dict[str, Any] = {
        "role": role,
        "path": _repo_relative(repo, path, role),
        "size_bytes": size_bytes,
        "sha256": digest,
    }
    if view_id is not None:
        record["view_id"] = view_id
    return record


def _expected_record_identities(
    *,
    repo: Path,
    data_root: Path,
    mono_dir: Path,
    view_ids: Iterable[str],
) -> list[tuple[str, str, str | None]]:
    expected = [
        ("sfm_cameras", _repo_relative(repo, data_root / "sparse/0/cameras.bin", "data_root"), None),
        ("sfm_images", _repo_relative(repo, data_root / "sparse/0/images.bin", "data_root"), None),
        ("sfm_points3d", _repo_relative(repo, data_root / "sparse/0/points3D.bin", "data_root"), None),
    ]
    for view_id in view_ids:
        stem = Path(view_id).stem
        expected.extend(
            [
                ("rgb", _repo_relative(repo, data_root / "images" / view_id, "data_root"), view_id),
                (
                    "mvs_depth_geometric",
                    _repo_relative(
                        repo,
                        data_root / "stereo/depth_maps" / f"{view_id}.geometric.bin",
                        "data_root",
                    ),
                    view_id,
                ),
                (
                    "mvs_normal_geometric",
                    _repo_relative(
                        repo,
                        data_root / "stereo/normal_maps" / f"{view_id}.geometric.bin",
                        "data_root",
                    ),
                    view_id,
                ),
                (
                    "mono_normal_omnidata",
                    _repo_relative(repo, mono_dir / f"{stem}.npy", "mono_normal_dir"),
                    view_id,
                ),
            ]
        )
    return expected


def build_materialized_input_inventory(
    *,
    repo: Path,
    data_root: Path,
    mono_dir: Path,
    view_ids: Iterable[str],
) -> dict[str, Any]:
    """Hash the exact deterministic Stage-2 files for every registered view."""

    repo = repo.resolve()
    data_root = _reject_symlink_components(repo, Path(data_root), "data_root")
    mono_dir = _reject_symlink_components(repo, Path(mono_dir), "mono_normal_dir")
    _repo_relative(repo, data_root, "data_root")
    _repo_relative(repo, mono_dir, "mono_normal_dir")
    ordered_views = [str(value) for value in view_ids]
    if not ordered_views or ordered_views != sorted(ordered_views):
        raise PilotInputInventoryError("materialized input view IDs must be sorted")
    if len(ordered_views) != len(set(ordered_views)):
        raise PilotInputInventoryError("materialized input view IDs must be unique")

    records: list[dict[str, Any]] = []
    for role, relative, view_id in _expected_record_identities(
        repo=repo,
        data_root=data_root,
        mono_dir=mono_dir,
        view_ids=ordered_views,
    ):
        records.append(_input_record(repo, repo / relative, role, view_id))

    role_counts: dict[str, int] = {}
    total_bytes = 0
    for record in records:
        role = str(record["role"])
        role_counts[role] = role_counts.get(role, 0) + 1
        total_bytes += int(record["size_bytes"])
    return {
        "schema": MATERIALIZED_INPUT_INVENTORY_SCHEMA,
        "run_id": PILOT_RUN_ID,
        "mode": MATERIALIZED_INPUT_MODE,
        "data_root": _repo_relative(repo, data_root, "data_root"),
        "mono_normal_dir": _repo_relative(repo, mono_dir, "mono_normal_dir"),
        "view_ids": ordered_views,
        "view_count": len(ordered_views),
        "role_counts": role_counts,
        "file_count": len(records),
        "total_bytes": total_bytes,
        "records": records,
        "records_sha256": hashlib.sha256(canonical_json_bytes(records)).hexdigest(),
        "learning_runs_started": 0,
        "optimizer_updates": 0,
    }


def _validate_colmap_view_ids(
    images_path: Path,
    *,
    expected_file_sha256: str,
    expected_view_ids: list[str],
) -> None:
    """Prove that the inventory covers every view named by pinned SfM bytes."""

    try:
        before = images_path.stat()
        # Keep this import local so inventory construction remains a lightweight
        # standard-library operation.  Validation happens before dataset/model
        # creation but may safely parse the already-pinned COLMAP metadata.
        from .colmap_io import read_images_bin

        images = read_images_bin(images_path)
        after = images_path.stat()
    except Exception as exc:
        raise PilotInputInventoryError(
            f"cannot parse pinned COLMAP images.bin view inventory: {exc}"
        ) from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity:
        raise PilotInputInventoryError(
            "COLMAP images.bin changed while its view inventory was parsed"
        )
    _size, digest = _stable_file_sha256(images_path, "sfm_images view inventory")
    if digest != expected_file_sha256:
        raise PilotInputInventoryError(
            "COLMAP images.bin drifted while validating its exact view inventory"
        )
    colmap_view_ids = sorted(image.name for image in images.values())
    if len(colmap_view_ids) != len(set(colmap_view_ids)):
        raise PilotInputInventoryError("COLMAP images.bin has duplicate view names")
    if colmap_view_ids != expected_view_ids:
        raise PilotInputInventoryError(
            "materialized inventory view IDs do not equal the pinned COLMAP "
            "images.bin view names"
        )


def validate_materialized_input_inventory(
    *,
    repo: Path,
    inventory_path: Path,
    expected_sha256: str,
    expected_data_root: Path | None = None,
    expected_mono_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate the closed inventory and hash every exact per-view input byte."""

    repo = repo.resolve()
    inventory_path = _reject_symlink_components(
        repo, Path(inventory_path), "materialized input inventory"
    )
    _repo_relative(repo, inventory_path, "materialized input inventory")
    expected_sha256 = _require_sha256(expected_sha256, "inventory SHA256")
    inventory_bytes = _stable_file_bytes(
        inventory_path, "materialized input inventory"
    )
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()
    if inventory_sha != expected_sha256:
        raise PilotInputInventoryError(
            "materialized input inventory SHA256 mismatch: "
            f"expected {expected_sha256}, got {inventory_sha}"
        )
    try:
        payload = json.loads(inventory_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotInputInventoryError(
            f"cannot read materialized input inventory {inventory_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != _INVENTORY_KEYS:
        actual = set(payload) if isinstance(payload, dict) else set()
        raise PilotInputInventoryError(
            "materialized input inventory top-level keys changed: "
            f"missing={sorted(_INVENTORY_KEYS - actual)} "
            f"extra={sorted(actual - _INVENTORY_KEYS)}"
        )
    if payload["schema"] != MATERIALIZED_INPUT_INVENTORY_SCHEMA:
        raise PilotInputInventoryError("materialized input inventory schema mismatch")
    if payload["run_id"] != PILOT_RUN_ID:
        raise PilotInputInventoryError("materialized input inventory run_id mismatch")
    if payload["mode"] != MATERIALIZED_INPUT_MODE:
        raise PilotInputInventoryError("materialized input inventory mode mismatch")
    learning_runs_started = _require_nonnegative_int(
        payload["learning_runs_started"], "learning_runs_started"
    )
    optimizer_updates = _require_nonnegative_int(
        payload["optimizer_updates"], "optimizer_updates"
    )
    if learning_runs_started != 0 or optimizer_updates != 0:
        raise PilotInputInventoryError("materialized inventory must remain result-blind")

    data_root = _resolve_relative(repo, payload["data_root"], "inventory.data_root")
    mono_dir = _resolve_relative(
        repo, payload["mono_normal_dir"], "inventory.mono_normal_dir"
    )
    if expected_data_root is not None:
        pinned_data_root = _reject_symlink_components(
            repo, Path(expected_data_root), "expected data_root"
        )
        if data_root != pinned_data_root:
            raise PilotInputInventoryError(
                f"inventory data_root mismatch: expected {pinned_data_root}, got {data_root}"
            )
    if expected_mono_dir is not None:
        pinned_mono_dir = _reject_symlink_components(
            repo, Path(expected_mono_dir), "expected mono_normal_dir"
        )
        if mono_dir != pinned_mono_dir:
            raise PilotInputInventoryError(
                "inventory mono_normal_dir mismatch: "
                f"expected {pinned_mono_dir}, got {mono_dir}"
            )

    view_ids = payload["view_ids"]
    if (
        not isinstance(view_ids, list)
        or not view_ids
        or any(not isinstance(value, str) or not value for value in view_ids)
        or view_ids != sorted(view_ids)
        or len(view_ids) != len(set(view_ids))
    ):
        raise PilotInputInventoryError("materialized inventory has invalid view IDs")
    if _require_nonnegative_int(payload["view_count"], "view_count") != len(view_ids):
        raise PilotInputInventoryError("materialized inventory view_count mismatch")
    expected_identities = _expected_record_identities(
        repo=repo,
        data_root=data_root,
        mono_dir=mono_dir,
        view_ids=view_ids,
    )
    records = payload["records"]
    if not isinstance(records, list) or len(records) != len(expected_identities):
        raise PilotInputInventoryError("materialized inventory record count mismatch")
    if hashlib.sha256(canonical_json_bytes(records)).hexdigest() != _require_sha256(
        payload["records_sha256"], "records_sha256"
    ):
        raise PilotInputInventoryError("materialized inventory records SHA256 mismatch")

    role_counts: dict[str, int] = {}
    total_bytes = 0
    seen_paths: set[str] = set()
    sfm_images_path: Path | None = None
    sfm_images_sha256: str | None = None
    for index, (record, expected_identity) in enumerate(
        zip(records, expected_identities, strict=True)
    ):
        if not isinstance(record, Mapping):
            raise PilotInputInventoryError(f"inventory record {index} is not an object")
        expected_role, expected_relative, expected_view = expected_identity
        expected_keys = _BASE_RECORD_KEYS | ({"view_id"} if expected_view else set())
        if set(record) != expected_keys:
            raise PilotInputInventoryError(
                f"inventory record {index} keys changed: {sorted(record)}"
            )
        identity = (
            record.get("role"),
            record.get("path"),
            record.get("view_id") if expected_view else None,
        )
        if identity != expected_identity:
            raise PilotInputInventoryError(
                f"inventory record {index} identity mismatch: "
                f"expected {expected_identity!r}, got {identity!r}"
            )
        relative = str(record["path"])
        if relative in seen_paths:
            raise PilotInputInventoryError(f"duplicate inventory path: {relative}")
        path = _resolve_relative(repo, relative, f"records[{index}].path")
        actual_size, actual_sha = _stable_file_sha256(path, f"records[{index}]")
        expected_size = _require_nonnegative_int(
            record["size_bytes"], f"records[{index}].size_bytes"
        )
        if actual_size != expected_size:
            raise PilotInputInventoryError(f"input size drifted: {relative}")
        expected_file_sha = _require_sha256(
            record["sha256"], f"records[{index}].sha256"
        )
        if actual_sha != expected_file_sha:
            raise PilotInputInventoryError(f"input SHA256 drifted: {relative}")
        if expected_role == "sfm_images":
            sfm_images_path = path
            sfm_images_sha256 = expected_file_sha
        role_counts[expected_role] = role_counts.get(expected_role, 0) + 1
        total_bytes += actual_size
        seen_paths.add(relative)

    expected_role_counts = {
        "sfm_cameras": 1,
        "sfm_images": 1,
        "sfm_points3d": 1,
        "rgb": len(view_ids),
        "mvs_depth_geometric": len(view_ids),
        "mvs_normal_geometric": len(view_ids),
        "mono_normal_omnidata": len(view_ids),
    }
    inventory_role_counts = payload["role_counts"]
    if (
        not isinstance(inventory_role_counts, dict)
        or any(
            not isinstance(role, str) or type(count) is not int or count < 0
            for role, count in inventory_role_counts.items()
        )
        or role_counts != expected_role_counts
        or inventory_role_counts != role_counts
    ):
        raise PilotInputInventoryError("materialized inventory role counts mismatch")
    if _require_nonnegative_int(payload["file_count"], "file_count") != len(records):
        raise PilotInputInventoryError("materialized inventory file_count mismatch")
    if _require_nonnegative_int(payload["total_bytes"], "total_bytes") != total_bytes:
        raise PilotInputInventoryError("materialized inventory total_bytes mismatch")
    if sfm_images_path is None or sfm_images_sha256 is None:
        raise PilotInputInventoryError("materialized inventory has no SfM images binding")
    _validate_colmap_view_ids(
        sfm_images_path,
        expected_file_sha256=sfm_images_sha256,
        expected_view_ids=view_ids,
    )
    return payload


def validate_pilot_config_materialized_inputs(
    cfg: Mapping[str, Any],
    *,
    repo: Path | None = None,
) -> dict[str, Any]:
    """Resolve and fully validate the inventory named by a pilot config."""

    repo = (
        Path(__file__).resolve().parents[2]
        if repo is None
        else Path(repo).resolve()
    )
    path_value = cfg.get("pilot_materialized_input_inventory_path")
    sha_value = cfg.get("pilot_materialized_input_inventory_sha256")
    if not isinstance(path_value, str) or not path_value:
        raise PilotInputInventoryError(
            "pilot config requires pilot_materialized_input_inventory_path"
        )
    if not isinstance(sha_value, str):
        raise PilotInputInventoryError(
            "pilot config requires pilot_materialized_input_inventory_sha256"
        )
    inventory_path = _resolve_config_path(
        repo, path_value, "pilot_materialized_input_inventory_path"
    )
    data_root = _resolve_config_path(repo, cfg.get("data_root"), "data_root")
    mono_dir = _resolve_config_path(
        repo, cfg.get("mono_normal_dir"), "mono_normal_dir"
    )
    if cfg.get("normal_dir") is not None:
        raise PilotInputInventoryError(
            "pilot config normal_dir must be null so geometric MVS normals are "
            "resolved only from the pinned data_root inventory"
        )
    if cfg.get("normal_encoding") != "half_range":
        raise PilotInputInventoryError(
            "pilot config normal_encoding must be the explicit half_range contract"
        )
    payload = validate_materialized_input_inventory(
        repo=repo,
        inventory_path=inventory_path,
        expected_sha256=sha_value,
        expected_data_root=data_root,
        expected_mono_dir=mono_dir,
    )
    visible_views = cfg.get("visible_views")
    if visible_views is not None:
        if (
            not isinstance(visible_views, list)
            or any(not isinstance(value, str) for value in visible_views)
            or visible_views != payload["view_ids"]
        ):
            raise PilotInputInventoryError(
                "pilot visible_views, when present, must exactly equal the "
                "materialized inventory view IDs"
            )
    return {
        "schema": MATERIALIZED_INPUT_VERIFICATION_SCHEMA,
        "status": "passed",
        "inventory_schema": payload["schema"],
        "path": str(inventory_path),
        "sha256": _require_sha256(sha_value, "inventory SHA256"),
        "records_sha256": payload["records_sha256"],
        "data_root": str(data_root),
        "mono_normal_dir": str(mono_dir),
        "view_count": payload["view_count"],
        "view_identity": "exact_sorted_colmap_images_bin_names",
        "role_counts": payload["role_counts"],
        "file_count": payload["file_count"],
        "total_bytes": payload["total_bytes"],
        "verification": "full_sha256_all_materialized_files",
    }
