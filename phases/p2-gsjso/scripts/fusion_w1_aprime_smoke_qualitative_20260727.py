#!/usr/bin/env python3
"""Publish the recovered A-prime smoke qualitative panel without placeholders.

The recovered readout and the original training/preprocess trees are immutable
inputs.  This adapter reuses the committed report module's render helpers, but
turns every missing-panel fallback into a hard error.  Only ``qualitative_smoke``
is writable, and its completion receipt is published after both PNG artifacts.
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
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_smoke_qualitative_20260727.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_qualitative.config.v2"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_qualitative.receipt.v1"
STRICT_RECEIPT_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.smoke_qualitative.strict_head_receipt.v1"
)
EXPECTED_COMPONENTS = (
    "input_crop",
    "seed_top",
    "mesh_top",
    "points_top",
    "points_section",
    "assembled",
    "reference",
    "opacity",
)
EXPECTED_SCOPE = {
    "run_id": "20260727_fusion_w1_aprime_smoke_recovery",
    "building_id": "DEBY_LOD2_42364609",
    "arm": "Aprime",
    "replicate": "r1",
    "attempt": 5,
}
EXPECTED_OUTPUT_ROOT = (
    "phases/p2-gsjso/runs/20260727_fusion_w1_aprime_smoke_recovery/"
    "qualitative_smoke"
)
REQUIRED_LOCKED_INPUTS = {
    "report_module",
    "recovery_complete",
    "readout_complete",
    "attempt",
    "tsdf_receipt",
    "tsdf_mesh",
    "tsdf_samples",
    "cityjson",
    "training_complete",
    "training_checkpoint",
    "seed_lineage",
    "seed_initialization",
    "preprocess_manifest",
    "supervision_index",
    "selected_crop_image",
    "selected_crop_prior",
    "seed",
    "reference_gml",
}


class QualitativeContractError(RuntimeError):
    """A locked input, visual component, or publication contract failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualitativeContractError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def repo_relative(path: Path) -> str:
    absolute = path.absolute()
    try:
        return absolute.relative_to(REPO.absolute()).as_posix()
    except ValueError:
        return str(absolute)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualitativeContractError(f"cannot load JSON {repo_relative(path)}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {repo_relative(path)}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    except OSError as exc:
        raise QualitativeContractError(f"cannot load CSV {repo_relative(path)}: {exc}") from exc


def file_record(path: Path, *, output_path: str | None = None) -> dict[str, Any]:
    require(path.is_file(), f"required file absent: {repo_relative(path)}")
    return {
        "path": output_path if output_path is not None else repo_relative(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def iter_locked_records(config: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    for name, value in config["locked_inputs"].items():
        if isinstance(value, list):
            for index, record in enumerate(value):
                yield f"{name}[{index}]", record
        else:
            yield name, value


def verify_record(name: str, record: Mapping[str, Any]) -> dict[str, Any]:
    require(set(record) == {"path", "sha256", "bytes"}, f"{name} record fields drift")
    path_value = record["path"]
    require(isinstance(path_value, str) and path_value, f"{name} path is invalid")
    require(not Path(path_value).is_absolute(), f"{name} must use a repo-relative path")
    require(
        isinstance(record["sha256"], str) and len(record["sha256"]) == 64,
        f"{name} sha256 is invalid",
    )
    require(isinstance(record["bytes"], int) and record["bytes"] > 0, f"{name} bytes invalid")
    actual = file_record(repo_path(path_value))
    require(actual["sha256"] == record["sha256"], f"{name} sha256 drift")
    require(actual["bytes"] == record["bytes"], f"{name} byte-size drift")
    return actual


def source_snapshot(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: verify_record(name, record) for name, record in iter_locked_records(config)}


def git_command(
    repo: Path,
    arguments: Sequence[str],
    *,
    text: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = ""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr_value = exc.stderr
            stderr = (
                stderr_value.strip()
                if isinstance(stderr_value, str)
                else stderr_value.decode("utf-8", errors="replace").strip()
            )
        detail = f": {stderr}" if stderr else ""
        raise QualitativeContractError(
            f"git command failed ({' '.join(arguments)}){detail}"
        ) from exc


def strict_head_context(
    config: Mapping[str, Any], *, repo: Path = REPO
) -> dict[str, Any]:
    """Prove that every rendering implementation byte is committed at HEAD."""
    branch = git_command(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"]).stdout.strip()
    require(branch == config["branch"], f"strict branch mismatch: {branch}")
    head = git_command(repo, ["rev-parse", "--verify", "HEAD^{commit}"]).stdout.strip()
    require(len(head) == 40 and all(character in "0123456789abcdef" for character in head), "invalid git HEAD")

    paths = list(config["implementation_files"])
    report_path = str(config["locked_inputs"]["report_module"]["path"])
    if report_path not in paths:
        paths.append(report_path)
    records: list[dict[str, Any]] = []
    for path_value in paths:
        require(not Path(path_value).is_absolute(), "strict HEAD path must be repo-relative")
        current_path = repo / path_value
        require(current_path.is_file(), f"strict HEAD file absent: {path_value}")

        tracked = git_command(
            repo,
            ["ls-files", "--error-unmatch", "--", path_value],
            check=False,
        )
        require(tracked.returncode == 0, f"implementation is not tracked at HEAD: {path_value}")
        head_file = git_command(
            repo,
            ["show", f"HEAD:{path_value}"],
            text=False,
            check=False,
        )
        require(head_file.returncode == 0, f"implementation is absent from HEAD: {path_value}")
        head_bytes = bytes(head_file.stdout)
        current_bytes = current_path.read_bytes()
        require(current_bytes == head_bytes, f"implementation worktree differs from HEAD: {path_value}")
        diff = git_command(
            repo,
            ["diff", "--quiet", "HEAD", "--", path_value],
            check=False,
        )
        require(diff.returncode == 0, f"implementation mode/content differs from HEAD: {path_value}")
        blob = git_command(repo, ["rev-parse", f"HEAD:{path_value}"]).stdout.strip()
        tree = git_command(repo, ["ls-tree", "HEAD", "--", path_value]).stdout.strip()
        require(bool(tree), f"implementation tree entry absent: {path_value}")
        records.append(
            {
                "path": path_value,
                "sha256": hashlib.sha256(head_bytes).hexdigest(),
                "bytes": len(head_bytes),
                "git_blob": blob,
                "git_mode": tree.split()[0],
                "tracked_at_head": True,
                "worktree_matches_head": True,
            }
        )

    report_record = next(record for record in records if record["path"] == report_path)
    expected_report = config["locked_inputs"]["report_module"]
    require(report_record["sha256"] == expected_report["sha256"], "HEAD report module hash drift")
    require(report_record["bytes"] == expected_report["bytes"], "HEAD report module size drift")
    return {
        "branch": branch,
        "head": head,
        "publication_key": head,
        "files": records,
        "all_tracked_at_head": True,
        "all_worktree_match_head": True,
    }


def load_config(path: Path = DEFAULT_CONFIG, *, verify_files: bool = True) -> dict[str, Any]:
    config = load_json(path)
    require(config.get("schema") == CONFIG_SCHEMA, "qualitative config schema drift")
    require(config.get("task_id") == "FUS-W1-APRIME-SMOKE-QUALITATIVE-001", "task ID drift")
    require(config.get("branch") == "exp/fusion-w1", "branch lock drift")
    require(config.get("scope") == EXPECTED_SCOPE, "single-smoke scope drift")
    require(set(config.get("locked_inputs", {})) == REQUIRED_LOCKED_INPUTS, "locked input set drift")

    implementation = config.get("implementation_files")
    require(isinstance(implementation, list) and len(implementation) == 4, "implementation file set drift")
    for path_value in implementation:
        require(not Path(path_value).is_absolute(), "implementation path must be repo-relative")
        require(repo_path(path_value).is_file(), f"implementation file absent: {path_value}")

    roots = config.get("source_roots", {})
    require(set(roots) == {"recovery", "attempt", "training", "preprocess"}, "source root set drift")
    for name, value in roots.items():
        require(not Path(value).is_absolute(), f"{name} source root must be repo-relative")
        require(repo_path(value).is_dir(), f"{name} source root absent")
    require(is_within(repo_path(roots["attempt"]), repo_path(roots["recovery"])), "attempt escaped recovery")

    publication = config.get("publication", {})
    require(tuple(publication.get("expected_components", [])) == EXPECTED_COMPONENTS, "component set drift")
    require(publication.get("placeholders_allowed") is False, "placeholders must be forbidden")
    require(publication.get("partial_publication_allowed") is False, "partial publication must be forbidden")
    require(publication.get("receipt_written_last") is True, "receipt-last contract drift")
    require(publication.get("source_inputs_rehashed_after_render") is True, "source rehash contract drift")
    require(publication.get("legacy_top_level_append_only") is True, "legacy append-only contract drift")
    strict_publication = publication.get("strict_head_publications", {})
    require(
        strict_publication
        == {
            "directory": "publications",
            "key": "full_git_head",
            "require_branch_match": True,
            "require_implementation_tracked_at_head": True,
            "require_implementation_worktree_matches_head": True,
            "require_report_module_tracked_at_head": True,
            "same_head_is_verify_only": True,
            "overwrite_allowed": False,
            "legacy_top_level_must_remain_unchanged": True,
        },
        "strict HEAD publication contract drift",
    )
    require(publication.get("scientific_verdict") is None, "scientific verdict must remain null")

    outputs = config.get("outputs", {})
    require(
        outputs == {
            "root": EXPECTED_OUTPUT_ROOT,
            "panel": "panel.png",
            "opacity": "opacity.png",
            "receipt": "receipt.json",
            "strict_publications": "publications",
        },
        "output namespace drift",
    )
    output_root = repo_path(outputs["root"])
    recovery_root = repo_path(roots["recovery"])
    require(is_within(output_root, recovery_root) and output_root != recovery_root, "output escaped recovery root")
    for _, record in iter_locked_records(config):
        require(not is_within(repo_path(record["path"]), output_root), "locked input overlaps output root")

    selected = config.get("selected_view", {})
    require(selected.get("image_name") == "DJI_20241217084827_0177_D.JPG", "selected view drift")
    require(selected.get("mask_pixels_n") == 643, "selected M_j cardinality drift")

    visual = config.get("visual_contract", {})
    require(visual.get("transition_iteration") == 15000, "transition iteration drift")
    require(visual.get("surface_ramp_end_iteration") == 20000, "surface ramp end drift")
    require(visual.get("opacity_initial_observation_phase") == "initialization_pre_dynamics", "initial opacity phase drift")
    require(visual.get("opacity_line_observation_phase") == "post_dynamics", "opacity line phase drift")
    require(visual.get("panel_dpi") == 150, "panel DPI drift")

    execution = config.get("execution", {})
    require(execution.get("container_image") == "jointbuildgs:dev", "container image drift")
    require(execution.get("network") == "none", "network contract drift")
    require(execution.get("nonroot") is True, "nonroot contract drift")
    require(execution.get("gpus_required") is False, "qualitative render must not require GPU")

    if verify_files:
        source_snapshot(config)
    return config


def load_report_module(config: Mapping[str, Any]) -> Any:
    record = config["locked_inputs"]["report_module"]
    verify_record("report_module", record)
    path = repo_path(record["path"])
    spec = importlib.util.spec_from_file_location("fusion_w1_aprime_report_locked", path)
    require(spec is not None and spec.loader is not None, "cannot construct report module loader")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def recursive_record_match(value: Any, record: Mapping[str, Any]) -> bool:
    if isinstance(value, Mapping):
        if value.get("path") == record["path"] and value.get("sha256") == record["sha256"]:
            return True
        return any(recursive_record_match(child, record) for child in value.values())
    if isinstance(value, list):
        return any(recursive_record_match(child, record) for child in value)
    return False


def require_record_binding(payload: Mapping[str, Any], record: Mapping[str, Any], label: str) -> None:
    require(recursive_record_match(payload, record), f"{label} provenance binding absent")


def xyz_stats(name: str, xyz: np.ndarray, *, require_z_span: bool = False) -> dict[str, Any]:
    values = np.asarray(xyz, dtype=np.float64)
    require(values.ndim == 2 and values.shape[1] == 3, f"{name} coordinates are not N x 3")
    require(len(values) >= 3, f"{name} has fewer than three points")
    require(bool(np.isfinite(values).all()), f"{name} contains non-finite coordinates")
    minimum = values.min(axis=0)
    maximum = values.max(axis=0)
    span = maximum - minimum
    require(float(max(span[0], span[1])) > 1e-6, f"{name} has no horizontal extent")
    if require_z_span:
        require(float(span[2]) > 1e-6, f"{name} has no vertical extent for a section")
    return {
        "points_n": int(len(values)),
        "minimum_xyz": [float(value) for value in minimum],
        "maximum_xyz": [float(value) for value in maximum],
        "span_xyz": [float(value) for value in span],
    }


def ring_stats(name: str, rings: Sequence[np.ndarray]) -> dict[str, Any]:
    require(bool(rings), f"{name} has no resolved rings")
    vertices_n = 0
    for index, ring in enumerate(rings):
        values = np.asarray(ring, dtype=np.float64)
        require(values.ndim == 2 and values.shape[1] >= 3, f"{name} ring {index} shape invalid")
        require(len(values) >= 3, f"{name} ring {index} is degenerate")
        require(bool(np.isfinite(values[:, :3]).all()), f"{name} ring {index} is non-finite")
        vertices_n += len(values)
    return {"rings_n": len(rings), "vertices_n": int(vertices_n)}


def png_stats(path: Path, *, minimum_size: tuple[int, int]) -> dict[str, Any]:
    require(path.is_file(), f"PNG absent: {repo_relative(path)}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (OSError, ValueError) as exc:
        raise QualitativeContractError(f"invalid PNG {repo_relative(path)}: {exc}") from exc
    height, width = rgb.shape[:2]
    require(width >= minimum_size[0] and height >= minimum_size[1], "PNG dimensions are too small")
    stride = max(1, int(math.sqrt((width * height) / 100000)))
    sample = rgb[::stride, ::stride].reshape(-1, 3)
    unique_colors = int(len(np.unique(sample, axis=0)))
    standard_deviation = float(sample.astype(np.float64).std())
    require(unique_colors >= 32, "PNG is visually blank or placeholder-like")
    require(standard_deviation >= 5.0, "PNG has insufficient visual variation")
    return {
        "width": width,
        "height": height,
        "sampled_unique_colors": unique_colors,
        "sampled_rgb_std": standard_deviation,
    }


def inspect_sources(config: Mapping[str, Any], report: Any) -> dict[str, Any]:
    """Validate exact provenance and all eight source-side panel components."""
    inputs = config["locked_inputs"]
    scope = config["scope"]
    building_id = scope["building_id"]
    arm = scope["arm"]
    replicate = scope["replicate"]
    attempt_number = scope["attempt"]

    recovery = load_json(repo_path(inputs["recovery_complete"]["path"]))
    require(recovery.get("schema") == "jointbuildgs.fusion_w1_aprime.smoke_recovery.complete.v1", "recovery completion schema drift")
    require(recovery.get("state") == "COMPLETE", "recovery is not COMPLETE")
    require(recovery.get("successful_continuation_attempt") == attempt_number, "recovery successful attempt drift")
    recovery_scope = recovery.get("scope", {})
    require(recovery_scope.get("building_id") == building_id, "recovery building drift")
    require(recovery_scope.get("arm") == arm, "recovery arm drift")
    require(recovery_scope.get("replicate") == replicate, "recovery replicate drift")
    require(recovery_scope.get("continuation_attempt") == attempt_number, "recovery attempt scope drift")
    require(recovery.get("primary", {}).get("state") == "MEASURED", "recovery primary is not measured")
    require(recovery.get("scientific_verdict") is None, "recovery contains a scientific verdict")
    require_record_binding(recovery, inputs["readout_complete"], "recovery to readout complete")

    readout = load_json(repo_path(inputs["readout_complete"]["path"]))
    require(readout.get("schema") == "jointbuildgs.fusion_w1_aprime.readout.complete.v1", "readout completion schema drift")
    require(readout.get("state") == "COMPLETE", "readout is not COMPLETE")
    require(readout.get("attempt") == attempt_number, "readout attempt drift")
    identity = readout.get("identity", {})
    require(identity.get("building_id") == building_id, "readout building drift")
    require(identity.get("arm") == arm, "readout arm drift")
    require(identity.get("replicate") == replicate, "readout replicate drift")
    require(readout.get("primary", {}).get("measurement_status") == "MEASURED", "readout primary measurement absent")
    require(readout.get("interpretation_or_verdict") is None, "readout contains interpretation")
    for key in ("attempt", "tsdf_receipt", "tsdf_mesh", "tsdf_samples", "cityjson"):
        require_record_binding(readout, inputs[key], f"readout to {key}")

    attempt = load_json(repo_path(inputs["attempt"]["path"]))
    require(attempt.get("schema") == "jointbuildgs.fusion_w1_aprime.readout.attempt.v1", "attempt schema drift")
    require(attempt.get("attempt") == attempt_number, "attempt number drift")
    attempt_identity = attempt.get("identity", {})
    require(attempt_identity.get("building_id") == building_id, "attempt building drift")
    require(attempt_identity.get("arm") == arm, "attempt arm drift")
    require(attempt_identity.get("replicate") == replicate, "attempt replicate drift")
    require(attempt.get("publication", {}).get("scientific_verdict") is None, "attempt contains a verdict")
    for key in ("training_complete", "training_checkpoint", "preprocess_manifest"):
        require_record_binding(attempt, inputs[key], f"attempt to {key}")

    training = load_json(repo_path(inputs["training_complete"]["path"]))
    require(training.get("schema") == "jointbuildgs.fusion_w1_aprime.training_completed.v1", "training completion schema drift")
    require(training.get("status") == "COMPLETED", "training is not completed")
    require(training.get("building_id") == building_id, "training building drift")
    require(training.get("arm") == arm, "training arm drift")
    require(training.get("replicate") == replicate, "training replicate drift")
    completion = training.get("training_completion", {})
    require(completion.get("status") == "PASSED", "training completion audit did not pass")
    require(completion.get("completed_optimizer_updates") == 30000, "optimizer update count drift")
    for key in ("training_checkpoint", "seed_lineage", "seed_initialization"):
        require_record_binding(training, inputs[key], f"training completion to {key}")

    preprocess = load_json(repo_path(inputs["preprocess_manifest"]["path"]))
    require(preprocess.get("schema") == "jointbuildgs.fusion_w1_aprime.preprocess_building.v1", "preprocess schema drift")
    require(preprocess.get("status") == "PASSED", "preprocess did not pass")
    require(preprocess.get("building", {}).get("building_id") == building_id, "preprocess building drift")
    require(preprocess.get("seed", {}).get("filtered_points_n") == 295, "filtered seed count drift")
    require(preprocess.get("supervision", {}).get("mask_normalization_denominator") == "cardinality_M_j", "M_j normalization drift")
    require_record_binding(preprocess, inputs["seed"], "preprocess to seed")
    require_record_binding(preprocess, inputs["supervision_index"], "preprocess to supervision index")

    tsdf = load_json(repo_path(inputs["tsdf_receipt"]["path"]))
    require(tsdf.get("schema") == "jointbuildgs.fusion_w1_aprime.tsdf.receipt.v1", "TSDF receipt schema drift")
    require(tsdf.get("status") == "COMPLETED", "TSDF receipt is not completed")
    tsdf_identity = tsdf.get("identity", {})
    require(tsdf_identity.get("building_id") == building_id, "TSDF building drift")
    require(tsdf_identity.get("condition") == f"arm_{arm}", "TSDF arm drift")
    require(tsdf_identity.get("replicate") == replicate, "TSDF replicate drift")
    require(tsdf.get("checks", {}).get("marching_cubes_mesh_nonempty") is True, "TSDF mesh gate absent")
    require(tsdf.get("checks", {}).get("surface_sample_nonempty") is True, "TSDF sample gate absent")
    require(tsdf.get("verdict") is None, "TSDF receipt contains a verdict")
    for key in ("training_checkpoint", "seed", "tsdf_mesh", "tsdf_samples"):
        require_record_binding(tsdf, inputs[key], f"TSDF receipt to {key}")

    supervision_rows = read_csv(repo_path(inputs["supervision_index"]["path"]))
    require(bool(supervision_rows), "supervision index is empty")
    selected_row = max(supervision_rows, key=lambda row: int(row.get("mask_pixels_n", "0")))
    selected_view = config["selected_view"]
    require(selected_row.get("image_name") == selected_view["image_name"], "max-M_j image drift")
    require(int(selected_row.get("mask_pixels_n", "0")) == selected_view["mask_pixels_n"], "max-M_j count drift")
    require(selected_row.get("class6_npz_path") == inputs["selected_crop_prior"]["path"], "selected crop prior drift")

    preprocess_root = repo_path(config["source_roots"]["preprocess"])
    crop, crop_label = report.input_crop(preprocess_root)
    require(crop is not None, f"input crop unavailable: {crop_label}")
    crop.load()
    require(crop_label == selected_view["image_name"], "input crop did not use max-M_j view")
    require(crop.width > 0 and crop.height > 0, "input crop is empty")

    job = report.Job(1, building_id, arm, replicate, {})
    opacity_rows, opacity_state, opacity_scope = report.load_opacity_rows(
        job, repo_path(config["source_roots"]["training"])
    )
    require(opacity_state == "measured", f"opacity trajectory is {opacity_state}: {opacity_scope}")
    initial_phase = config["visual_contract"]["opacity_initial_observation_phase"]
    line_phase = config["visual_contract"]["opacity_line_observation_phase"]
    initial = [row for row in opacity_rows if row.get("observation_phase") == initial_phase]
    dynamics = [row for row in opacity_rows if row.get("observation_phase") == line_phase]
    require(bool(initial), "actual initialization opacity marker absent")
    require(len(dynamics) >= 2, "actual opacity dynamics have fewer than two rows")
    require(all(math.isfinite(float(row["opacity_median"])) for row in opacity_rows), "opacity contains non-finite values")
    iterations = sorted({int(row["iteration"]) for row in dynamics})
    require(len(iterations) >= 2, "opacity dynamics have no iteration trajectory")
    require(iterations[0] <= config["visual_contract"]["transition_iteration"], "opacity misses pre-transition observations")
    require(iterations[-1] >= config["visual_contract"]["surface_ramp_end_iteration"], "opacity misses post-ramp observations")
    require(all(row.get("seed_protect_active") is False for row in dynamics), "seed protection was active")
    require(max(int(row.get("cum_pruned") or 0) for row in dynamics) > 0, "prune trajectory is not observed")

    seed_xyz, seed_rgb = report.npz_xyz_rgb(
        repo_path(inputs["seed"]["path"]),
        ("xyz_base_epsg25832_orthometric", "xyz"),
    )
    seed_description = xyz_stats("A-prime class-6 seed", seed_xyz)
    require(seed_rgb is not None and seed_rgb.shape == (len(seed_xyz), 3), "seed RGB is absent or malformed")

    mesh_xyz = report.ply_vertices(repo_path(inputs["tsdf_mesh"]["path"]))
    mesh_description = xyz_stats("filtered TSDF mesh", mesh_xyz, require_z_span=True)

    sample_xyz, sample_rgb = report.npz_xyz_rgb(
        repo_path(inputs["tsdf_samples"]["path"]),
        ("xyz_epsg25832_orthometric", "xyz_canonical_ellipsoidal", "xyz"),
    )
    sample_description = xyz_stats("TSDF surface samples", sample_xyz, require_z_span=True)
    if sample_rgb is not None:
        require(sample_rgb.shape == (len(sample_xyz), 3), "TSDF sample RGB is malformed")

    cityjson_description = ring_stats(
        "Roofer CityJSON", report.cityjson_rings(repo_path(inputs["cityjson"]["path"]))
    )
    reference_paths = [repo_path(record["path"]) for record in inputs["reference_gml"]]
    reference = report.gml_rings_by_building(reference_paths, [building_id])[building_id]
    reference_description = ring_stats("evaluation-only reference GML", reference)

    components = {name: True for name in EXPECTED_COMPONENTS}
    building = preprocess.get("building", {})
    texture_fraction = float(building.get("texture_low_gradient_fraction"))
    return {
        "components": components,
        "input_crop": {
            "image_name": crop_label,
            "width": crop.width,
            "height": crop.height,
            "mask_pixels_n": int(selected_row["mask_pixels_n"]),
        },
        "seed": seed_description,
        "tsdf_mesh": mesh_description,
        "tsdf_samples": sample_description,
        "cityjson": cityjson_description,
        "reference_gml": reference_description,
        "opacity": {
            "state": opacity_state,
            "scope": opacity_scope,
            "rows_n": len(opacity_rows),
            "initial_rows_n": len(initial),
            "dynamics_rows_n": len(dynamics),
            "minimum_iteration": iterations[0],
            "maximum_iteration": iterations[-1],
            "initial_opacity_median": float(initial[0]["opacity_median"]),
            "final_observed_opacity_median": float(dynamics[-1]["opacity_median"]),
            "maximum_cumulative_pruned": max(int(row.get("cum_pruned") or 0) for row in dynamics),
        },
        "metadata": {
            "tier": str(building.get("tier", "")),
            "texture_low_gradient_fraction": texture_fraction,
            "texture_stratum": "textureless" if texture_fraction > 0.804 else "textured",
            "seed_filter_after_n": int(preprocess["seed"]["filtered_points_n"]),
            "mask_pixels_total": int(preprocess["supervision"]["mask_pixels_total"]),
        },
    }


def report_render_config(config: Mapping[str, Any]) -> dict[str, Any]:
    preprocess_root = repo_path(config["source_roots"]["preprocess"])
    run_root = preprocess_root.parents[3]
    cache_namespace = preprocess_root.parents[1].name
    return {
        "visual_contract": config["visual_contract"],
        "outputs": {"panels_dir": "panels", "opacity_dir": "opacity"},
        "locked_inputs": {"reference_gml": config["locked_inputs"]["reference_gml"]},
        "sources": {
            "run_root": repo_relative(run_root),
            "preprocess_cache_namespace": cache_namespace,
        },
    }


def render_into(
    staging: Path,
    config: Mapping[str, Any],
    report: Any,
    inspection: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bool]]:
    scope = config["scope"]
    job = report.Job(
        1,
        scope["building_id"],
        scope["arm"],
        scope["replicate"],
        {},
    )
    metadata = inspection["metadata"]
    score: dict[str, Any] = {
        "building_id": job.building_id,
        "arm": job.arm,
        "run": job.run,
        "job_terminal_state": "measured",
        "primary_measurement_state": "measured",
        "tier": metadata["tier"],
        "texture_stratum": metadata["texture_stratum"],
        "seed_filter_after_n": metadata["seed_filter_after_n"],
        "mask_pixels_total": metadata["mask_pixels_total"],
    }
    locked = config["locked_inputs"]
    runtime = {
        job.key: {
            "job": job,
            "training_dir": repo_path(config["source_roots"]["training"]),
            "readout_paths": {
                "mesh": repo_path(locked["tsdf_mesh"]["path"]),
                "tsdf_npz": repo_path(locked["tsdf_samples"]["path"]),
                "cityjson": repo_path(locked["cityjson"]["path"]),
                "alpha_npz": None,
                "alpha_cityjson": None,
            },
        }
    }
    render_root = staging / "render"

    original_placeholder = report._placeholder

    def forbidden_placeholder(_ax: Any, title: str, reason: str) -> None:
        raise QualitativeContractError(f"placeholder forbidden for {title}: {reason}")

    report._placeholder = forbidden_placeholder
    try:
        opacity_rows = report.generate_visuals(
            [score], runtime, render_root, report_render_config(config)
        )
    finally:
        report._placeholder = original_placeholder

    components = score.get("panel_components_json")
    require(isinstance(components, dict), "report did not return component checks")
    require(tuple(components) == EXPECTED_COMPONENTS, "report component order/set drift")
    require(all(components.values()), "report generated a partial panel")
    require(score.get("panel_state") == "measured", "panel state is not measured")
    require(score.get("opacity_state") == "measured", "opacity state is not measured")
    require(bool(opacity_rows), "report returned no opacity observations")

    slug = job.slug
    rendered_panel = render_root / "panels" / f"{slug}.png"
    rendered_opacity = render_root / "opacity" / f"{slug}.png"
    panel_quality = png_stats(rendered_panel, minimum_size=(1600, 800))
    opacity_quality = png_stats(rendered_opacity, minimum_size=(700, 350))
    rendered_panel.replace(staging / config["outputs"]["panel"])
    rendered_opacity.replace(staging / config["outputs"]["opacity"])
    shutil.rmtree(render_root)
    return panel_quality, opacity_quality, dict(components)


def write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise QualitativeContractError(f"refusing to overwrite {repo_relative(path)}") from exc


def implementation_records(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [file_record(repo_path(path)) for path in config["implementation_files"]]


def output_paths(config: Mapping[str, Any]) -> tuple[Path, Path, Path, Path]:
    root = repo_path(config["outputs"]["root"])
    return (
        root,
        root / config["outputs"]["panel"],
        root / config["outputs"]["opacity"],
        root / config["outputs"]["receipt"],
    )


def strict_publication_paths(
    config: Mapping[str, Any], head: str
) -> tuple[Path, Path, Path, Path]:
    require(len(head) == 40 and all(character in "0123456789abcdef" for character in head), "invalid strict publication key")
    base = repo_path(config["outputs"]["root"])
    root = base / config["outputs"]["strict_publications"] / head
    require(is_within(root, base), "strict publication escaped qualitative root")
    return (
        root,
        root / config["outputs"]["panel"],
        root / config["outputs"]["opacity"],
        root / config["outputs"]["receipt"],
    )


def legacy_top_level_snapshot(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    root, panel_path, opacity_path, receipt_path = output_paths(config)
    require(root.is_dir(), "legacy qualitative output root absent")
    return {
        "panel": file_record(panel_path),
        "opacity": file_record(opacity_path),
        "receipt": file_record(receipt_path),
    }


def verify_publication(config: Mapping[str, Any]) -> dict[str, Any]:
    root, panel_path, opacity_path, receipt_path = output_paths(config)
    require(root.is_dir(), "qualitative_smoke output root absent")
    expected_names = {
        config["outputs"]["panel"],
        config["outputs"]["opacity"],
        config["outputs"]["receipt"],
    }
    actual_names = {path.name for path in root.iterdir()}
    allowed_names = expected_names | {config["outputs"]["strict_publications"]}
    require(expected_names <= actual_names, f"legacy output file set incomplete: {sorted(actual_names)}")
    require(actual_names <= allowed_names, f"legacy output file set drift: {sorted(actual_names)}")
    publications_path = root / config["outputs"]["strict_publications"]
    if publications_path.exists():
        require(publications_path.is_dir(), "strict publications path is not a directory")
    receipt = load_json(receipt_path)
    require(receipt.get("schema") == RECEIPT_SCHEMA, "qualitative receipt schema drift")
    require(receipt.get("state") == "COMPLETE", "qualitative receipt is not COMPLETE")
    require(receipt.get("scope") == config["scope"], "qualitative receipt scope drift")
    require(receipt.get("scientific_verdict") is None, "qualitative receipt contains a verdict")
    require(receipt.get("placeholder_count") == 0, "receipt reports placeholders")
    require(receipt.get("components") == {name: True for name in EXPECTED_COMPONENTS}, "receipt component checks drift")
    require(receipt.get("publication", {}).get("receipt_published_last") is True, "receipt-last flag absent")
    require(receipt.get("publication", {}).get("source_inputs_unchanged") is True, "source immutability flag absent")

    panel_record = file_record(panel_path, output_path=f"{config['outputs']['root']}/{config['outputs']['panel']}")
    opacity_record = file_record(opacity_path, output_path=f"{config['outputs']['root']}/{config['outputs']['opacity']}")
    require(receipt.get("outputs", {}).get("panel") == panel_record, "panel artifact hash drift")
    require(receipt.get("outputs", {}).get("opacity") == opacity_record, "opacity artifact hash drift")
    png_stats(panel_path, minimum_size=(1600, 800))
    png_stats(opacity_path, minimum_size=(700, 350))

    current_snapshot = source_snapshot(config)
    require(receipt.get("source_snapshot_before") == current_snapshot, "source snapshot before drift")
    require(receipt.get("source_snapshot_after") == current_snapshot, "source snapshot after drift")
    return receipt


def build(config: Mapping[str, Any], report: Any) -> dict[str, Any]:
    root, panel_path, opacity_path, receipt_path = output_paths(config)
    if receipt_path.is_file():
        return verify_publication(config)
    root.mkdir(parents=True, exist_ok=True)
    existing = list(root.iterdir())
    require(not existing, f"refusing incomplete/nonempty output root: {[path.name for path in existing]}")
    source_before = source_snapshot(config)
    inspection = inspect_sources(config, report)

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    try:
        panel_quality, opacity_quality, components = render_into(
            staging, config, report, inspection
        )
        source_after = source_snapshot(config)
        require(source_after == source_before, "locked source changed while rendering")

        staged_panel = staging / config["outputs"]["panel"]
        staged_opacity = staging / config["outputs"]["opacity"]
        panel_record = file_record(
            staged_panel,
            output_path=f"{config['outputs']['root']}/{config['outputs']['panel']}",
        )
        opacity_record = file_record(
            staged_opacity,
            output_path=f"{config['outputs']['root']}/{config['outputs']['opacity']}",
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": config["task_id"],
            "state": "COMPLETE",
            "created_at": utc_now(),
            "scope": config["scope"],
            "components": components,
            "placeholder_count": 0,
            "inspection": inspection,
            "render_quality": {
                "panel": panel_quality,
                "opacity": opacity_quality,
            },
            "report_module_reuse": {
                "module": inputs_record(config, "report_module"),
                "functions": [
                    "generate_visuals",
                    "input_crop",
                    "npz_xyz_rgb",
                    "ply_vertices",
                    "cityjson_rings",
                    "gml_rings_by_building",
                    "load_opacity_rows",
                    "plot_opacity",
                ],
                "placeholder_callback_replaced_with_hard_error": True,
            },
            "implementation": implementation_records(config),
            "source_snapshot_before": source_before,
            "source_snapshot_after": source_after,
            "outputs": {"panel": panel_record, "opacity": opacity_record},
            "publication": {
                "partial_publication_allowed": False,
                "receipt_written_after_artifact_validation": True,
                "receipt_published_last": True,
                "source_inputs_unchanged": True,
            },
            "scientific_verdict": None,
            "interpretation": None,
        }
        staged_receipt = staging / config["outputs"]["receipt"]
        write_json_exclusive(staged_receipt, receipt)

        staged_panel.replace(panel_path)
        staged_opacity.replace(opacity_path)
        staged_receipt.replace(receipt_path)
        staging.rmdir()
        return verify_publication(config)
    except Exception:
        if staging.exists() and is_within(staging, root):
            shutil.rmtree(staging)
        raise


def verify_strict_publication(
    config: Mapping[str, Any], *, context: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    strict = dict(context or strict_head_context(config))
    root, panel_path, opacity_path, receipt_path = strict_publication_paths(
        config, strict["head"]
    )
    require(root.is_dir(), f"strict HEAD publication absent: {strict['head']}")
    expected_names = {
        config["outputs"]["panel"],
        config["outputs"]["opacity"],
        config["outputs"]["receipt"],
    }
    actual_names = {path.name for path in root.iterdir()}
    require(actual_names == expected_names, f"strict publication file set drift: {sorted(actual_names)}")
    receipt = load_json(receipt_path)
    require(receipt.get("schema") == STRICT_RECEIPT_SCHEMA, "strict receipt schema drift")
    require(receipt.get("state") == "COMPLETE", "strict receipt is not COMPLETE")
    require(receipt.get("scope") == config["scope"], "strict receipt scope drift")
    require(receipt.get("publication_key") == strict["head"], "strict publication key drift")
    require(receipt.get("execution_head") == strict["head"], "strict execution HEAD drift")
    require(receipt.get("execution_branch") == strict["branch"], "strict execution branch drift")
    require(receipt.get("execution") == config["execution"], "strict execution environment drift")
    require(receipt.get("strict_head_context") == strict, "strict HEAD implementation binding drift")
    require(receipt.get("scientific_verdict") is None, "strict receipt contains a verdict")
    require(receipt.get("placeholder_count") == 0, "strict receipt reports placeholders")
    require(receipt.get("components") == {name: True for name in EXPECTED_COMPONENTS}, "strict receipt components drift")
    publication = receipt.get("publication", {})
    require(publication.get("append_only") is True, "strict append-only flag absent")
    require(publication.get("same_head_verify_only") is True, "strict same-HEAD verify-only flag absent")
    require(publication.get("receipt_published_last") is True, "strict receipt-last flag absent")
    require(publication.get("source_inputs_unchanged") is True, "strict source immutability flag absent")
    require(publication.get("legacy_top_level_unchanged") is True, "legacy preservation flag absent")

    root_relative = repo_relative(root)
    panel_record = file_record(
        panel_path,
        output_path=f"{root_relative}/{config['outputs']['panel']}",
    )
    opacity_record = file_record(
        opacity_path,
        output_path=f"{root_relative}/{config['outputs']['opacity']}",
    )
    require(receipt.get("outputs", {}).get("panel") == panel_record, "strict panel hash drift")
    require(receipt.get("outputs", {}).get("opacity") == opacity_record, "strict opacity hash drift")
    png_stats(panel_path, minimum_size=(1600, 800))
    png_stats(opacity_path, minimum_size=(700, 350))

    current_sources = source_snapshot(config)
    require(receipt.get("source_snapshot_before") == current_sources, "strict source snapshot before drift")
    require(receipt.get("source_snapshot_after") == current_sources, "strict source snapshot after drift")
    current_legacy = legacy_top_level_snapshot(config)
    require(receipt.get("legacy_top_level_before") == current_legacy, "strict legacy snapshot before drift")
    require(receipt.get("legacy_top_level_after") == current_legacy, "strict legacy snapshot after drift")
    return receipt


def build_strict_publication(
    config: Mapping[str, Any], report: Any
) -> dict[str, Any]:
    strict_before = strict_head_context(config)
    verify_publication(config)
    root, panel_path, opacity_path, receipt_path = strict_publication_paths(
        config, strict_before["head"]
    )
    if receipt_path.is_file():
        return verify_strict_publication(config, context=strict_before)
    require(not root.exists(), f"refusing incomplete strict publication: {repo_relative(root)}")
    root.mkdir(parents=True, exist_ok=False)

    source_before = source_snapshot(config)
    legacy_before = legacy_top_level_snapshot(config)
    inspection = inspect_sources(config, report)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    try:
        panel_quality, opacity_quality, components = render_into(
            staging, config, report, inspection
        )
        source_after = source_snapshot(config)
        legacy_after = legacy_top_level_snapshot(config)
        strict_after = strict_head_context(config)
        require(source_after == source_before, "locked source changed during strict render")
        require(legacy_after == legacy_before, "legacy top-level publication changed")
        require(strict_after == strict_before, "strict HEAD context changed during render")

        staged_panel = staging / config["outputs"]["panel"]
        staged_opacity = staging / config["outputs"]["opacity"]
        root_relative = repo_relative(root)
        panel_record = file_record(
            staged_panel,
            output_path=f"{root_relative}/{config['outputs']['panel']}",
        )
        opacity_record = file_record(
            staged_opacity,
            output_path=f"{root_relative}/{config['outputs']['opacity']}",
        )
        receipt = {
            "schema": STRICT_RECEIPT_SCHEMA,
            "task_id": config["task_id"],
            "state": "COMPLETE",
            "created_at": utc_now(),
            "scope": config["scope"],
            "publication_key": strict_before["head"],
            "execution_head": strict_before["head"],
            "execution_branch": strict_before["branch"],
            "execution": config["execution"],
            "strict_head_context": strict_before,
            "components": components,
            "placeholder_count": 0,
            "inspection": inspection,
            "render_quality": {
                "panel": panel_quality,
                "opacity": opacity_quality,
            },
            "report_module_reuse": {
                "module": inputs_record(config, "report_module"),
                "functions": [
                    "generate_visuals",
                    "input_crop",
                    "npz_xyz_rgb",
                    "ply_vertices",
                    "cityjson_rings",
                    "gml_rings_by_building",
                    "load_opacity_rows",
                    "plot_opacity",
                ],
                "placeholder_callback_replaced_with_hard_error": True,
            },
            "source_snapshot_before": source_before,
            "source_snapshot_after": source_after,
            "legacy_top_level_before": legacy_before,
            "legacy_top_level_after": legacy_after,
            "outputs": {"panel": panel_record, "opacity": opacity_record},
            "publication": {
                "append_only": True,
                "same_head_verify_only": True,
                "overwrite_allowed": False,
                "partial_publication_allowed": False,
                "receipt_written_after_artifact_validation": True,
                "receipt_published_last": True,
                "source_inputs_unchanged": True,
                "legacy_top_level_unchanged": True,
            },
            "scientific_verdict": None,
            "interpretation": None,
        }
        staged_receipt = staging / config["outputs"]["receipt"]
        write_json_exclusive(staged_receipt, receipt)
        staged_panel.replace(panel_path)
        staged_opacity.replace(opacity_path)
        staged_receipt.replace(receipt_path)
        staging.rmdir()
        return verify_strict_publication(config, context=strict_before)
    except Exception:
        if staging.exists() and is_within(staging, root):
            shutil.rmtree(staging)
        if root.exists() and not any(root.iterdir()):
            root.rmdir()
        raise


def strict_check(config: Mapping[str, Any], report: Any) -> dict[str, Any]:
    strict_before = strict_head_context(config)
    source_before = source_snapshot(config)
    legacy_before = legacy_top_level_snapshot(config)
    inspection = inspect_sources(config, report)
    strict_after = strict_head_context(config)
    source_after = source_snapshot(config)
    legacy_after = legacy_top_level_snapshot(config)
    require(strict_after == strict_before, "strict HEAD context changed during check")
    require(source_after == source_before, "locked source changed during strict check")
    require(legacy_after == legacy_before, "legacy publication changed during strict check")
    publication_root = strict_publication_paths(config, strict_before["head"])[0]
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.smoke_qualitative.strict_check.v1",
        "state": "READY",
        "scope": config["scope"],
        "strict_head_context": strict_before,
        "publication_root": repo_relative(publication_root),
        "components": inspection["components"],
        "placeholder_count": 0,
        "source_inputs_unchanged": True,
        "legacy_top_level_unchanged": True,
        "scientific_verdict": None,
    }


def inputs_record(config: Mapping[str, Any], name: str) -> dict[str, Any]:
    record = config["locked_inputs"][name]
    require(isinstance(record, dict), f"{name} is not a scalar file record")
    return dict(record)


def check(config: Mapping[str, Any], report: Any) -> dict[str, Any]:
    before = source_snapshot(config)
    inspection = inspect_sources(config, report)
    after = source_snapshot(config)
    require(before == after, "locked source changed during check")
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.smoke_qualitative.check.v1",
        "state": "READY",
        "scope": config["scope"],
        "components": inspection["components"],
        "placeholder_count": 0,
        "inspection": inspection,
        "source_inputs_unchanged": True,
        "scientific_verdict": None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "command",
        choices=(
            "check",
            "build",
            "verify",
            "strict-check",
            "publish-strict",
            "verify-strict",
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        report = load_report_module(config)
        if args.command == "check":
            payload = check(config, report)
        elif args.command == "build":
            payload = build(config, report)
        elif args.command == "verify":
            payload = verify_publication(config)
        elif args.command == "strict-check":
            payload = strict_check(config, report)
        elif args.command == "publish-strict":
            payload = build_strict_publication(config, report)
        else:
            payload = verify_strict_publication(config)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except QualitativeContractError as exc:
        print(f"QUALITATIVE_CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
