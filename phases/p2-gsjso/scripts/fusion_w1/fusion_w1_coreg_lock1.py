#!/usr/bin/env python3
"""FUS-W1 ALS-fixed camera/photo co-registration.

The script deliberately separates locked preparation from measurement:

  prepare-controls  -> select and publish fit/trigger/check + capture blocks
  prepare-als       -> materialize immutable class-2/6 ALS at fixed zeta
  fit               -> read fit controls only and estimate one global SE(3)
  select            -> read trigger controls only and freeze identity/global
  check             -> read independent check controls once
  publish-poses     -> write a derived COLMAP model after a passed check

No command modifies the source ALS or source COLMAP model.

Lock2's pre-role availability screen does not form correspondences or distance
residuals, but it does use the nominal shared frame to test joint support. Its
fit/trigger/check evidence is therefore explicitly conditional on that support
screen; the predeclared core-building Gate A2 remains the final alignment gate.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = ROOT / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_coreg_lock1.json"


class CoregError(RuntimeError):
    """Fail-closed protocol or measurement error."""


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve()))
    except ValueError:
        return str(resolved)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def write_json(path: str | Path, payload: Any, *, exclusive: bool = False) -> None:
    target = repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and target.exists():
        raise CoregError(f"exact-once output already exists: {relative(target)}")
    mode = "x" if exclusive else "w"
    with target.open(mode) as handle:
        handle.write(
            json.dumps(
                json_safe(payload),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = repo_path(path)
    if config_path.resolve() != DEFAULT_CONFIG.resolve():
        raise CoregError("alternate coreg config paths are forbidden")
    payload = json.loads(config_path.read_text())
    if payload.get("schema") != "jointbuildgs.fusion_w1.camera_coreg_config.v1":
        raise CoregError("unexpected coreg config schema")
    if payload.get("implementation_variant") != "lock1":
        raise CoregError("only lock1 config is allowed")
    locks = payload["input_locks"]
    if float(locks["orthometric_to_ellipsoidal_zeta_m"]) != 45.7:
        raise CoregError("zeta must remain exactly 45.7 m")
    if float(locks["scale"]) != 1.0:
        raise CoregError("scale must remain exactly 1")
    if locks["transform_direction"] != (
        "photo_ellipsoidal_global_to_als_ellipsoidal_global"
    ):
        raise CoregError("transform direction differs from locked contract")
    return payload


def validate_recovery_predecessor(
    config: Mapping[str, Any], section: Mapping[str, Any]
) -> dict[str, str]:
    """Bind lock2 exposure claims to lock1's committed compact publication."""

    contract = section.get("predecessor_contract")
    if not isinstance(contract, Mapping):
        raise CoregError("recovery predecessor contract is missing")
    locked_files = contract.get("file_sha256")
    if not isinstance(locked_files, Mapping) or not locked_files:
        raise CoregError("recovery predecessor file hashes are missing")
    observed: dict[str, str] = {}
    for raw_path, expected in locked_files.items():
        path = repo_path(str(raw_path))
        if not path.is_file():
            raise CoregError(f"recovery predecessor file is missing: {relative(path)}")
        actual = sha256_file(path)
        if actual != str(expected):
            raise CoregError(
                f"recovery predecessor hash mismatch for {relative(path)}"
            )
        observed[str(raw_path)] = actual

    manifest_path = repo_path(str(contract["publication_manifest"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_artifacts = dict(contract["published_artifact_sha256"])
    if manifest.get("schema") != "jointbuildgs.fusion_w1.coreg_publication.v1":
        raise CoregError("unexpected recovery predecessor publication schema")
    if manifest.get("artifacts") != expected_artifacts:
        raise CoregError("recovery predecessor publication inventory mismatch")
    if int(manifest.get("learning_runs_started", -1)) != 0:
        raise CoregError("recovery predecessor unexpectedly started learning")
    if manifest.get("source_als_sha256_after") != config["input_locks"][
        "expected_sha256"
    ][config["inputs"]["als_aoi_laz"]]:
        raise CoregError("recovery predecessor ALS lineage mismatch")

    previous = section["previous_run"]
    fit_open = json.loads(
        repo_path(str(contract["fit_open"])).read_text(encoding="utf-8")
    )
    select_open = json.loads(
        repo_path(str(contract["select_open"])).read_text(encoding="utf-8")
    )
    expected_head = str(previous["head"])
    if (
        fit_open.get("stage") != "fit"
        or fit_open.get("status") != "OPENED_EXACT_ONCE"
        or fit_open.get("stage_binding", {}).get("head") != expected_head
    ):
        raise CoregError("recovery predecessor fit receipt mismatch")
    if (
        select_open.get("stage") != "select"
        or select_open.get("status") != "OPENED_EXACT_ONCE"
        or select_open.get("stage_binding", {}).get("head") != expected_head
    ):
        raise CoregError("recovery predecessor select receipt mismatch")
    fit_candidate_path = str(contract["fit_candidate"])
    if select_open.get("parent_receipt_sha256", {}).get(
        "fit_candidate"
    ) != expected_artifacts.get(fit_candidate_path):
        raise CoregError("recovery predecessor fit-to-select chain mismatch")

    failure_path = repo_path(str(contract["failures"]))
    failure_rows = [
        json.loads(line)
        for line in failure_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not failure_rows:
        raise CoregError("recovery predecessor failure receipt is empty")
    last_failure = failure_rows[-1]
    if (
        last_failure.get("command") != "select"
        or last_failure.get("head") != expected_head
        or last_failure.get("error") != previous["failure"]
        or int(last_failure.get("learning_runs_started", -1)) != 0
    ):
        raise CoregError("recovery predecessor failure receipt mismatch")
    if int(previous["trigger_residual_buildings_evaluated"]) != 0:
        raise CoregError("recovery predecessor trigger exposure is not zero")
    forbidden_outputs = set(contract["forbidden_published_outputs"])
    published_names = {Path(path).name for path in expected_artifacts}
    if published_names & forbidden_outputs:
        raise CoregError("recovery predecessor unexpectedly published later-stage output")
    return observed


def activate_recovery_lock2(config: Mapping[str, Any]) -> dict[str, Any]:
    section = config.get("recovery_lock2")
    if not isinstance(section, Mapping) or section.get("enabled") is not True:
        raise CoregError("coreg recovery lock2 is not enabled")
    if section.get("geometry_feasibility_screen_required") is not True:
        raise CoregError("recovery requires a pre-role geometry feasibility screen")
    if section.get("geometry_feasibility_screen_uses_correspondence_residuals") is not False:
        raise CoregError("recovery feasibility screen must not use alignment residuals")
    if section.get("geometry_feasibility_screen_nominal_alignment_sensitive") is not True:
        raise CoregError("recovery must disclose nominal-frame support sensitivity")
    if section.get("alignment_judgment_scope") != (
        "coreg evidence conditional on support screen; final decision is "
        "predeclared core-building Gate A2"
    ):
        raise CoregError("recovery conditional judgment scope is not locked")
    validate_recovery_predecessor(config, section)
    activated = copy.deepcopy(dict(config))
    activated["task_id"] = str(section["task_id"])
    activated["inputs"].update(dict(section["input_overrides"]))
    activated["split"]["excluded_calibration_split_csvs"] = list(
        section["excluded_split_csvs"]
    )
    activated["split"]["prior_exposure_split_csv"] = str(
        section["prior_exposure_split_csv"]
    )
    activated["split"]["prior_fit_residual_exposure_policy"] = str(
        section["prior_fit_residual_exposure_policy"]
    )
    activated["split"]["prior_trigger_check_residuals_evaluated"] = int(
        section["prior_trigger_check_residuals_evaluated"]
    )
    activated["split"]["geometry_feasibility_screen_required"] = True
    activated["split"]["geometry_feasibility_screen_nominal_alignment_sensitive"] = True
    activated["split"]["alignment_judgment_scope"] = str(
        section["alignment_judgment_scope"]
    )
    activated["split"]["calibration_tiers"] = list(
        section["calibration_tiers"]
    )
    activated["split"]["stable_tie_seed"] = str(section["stable_tie_seed"])
    activated["input_locks"]["generated_lock_sha256"] = dict(
        section["generated_lock_sha256"]
    )
    activated["git_lock"]["implementation_files"].extend(
        str(value) for value in section["implementation_files_append"]
    )
    activated["_prereg_manifest_path"] = str(section["prereg_manifest"])
    activated["_prereg_figure_path"] = str(section["prereg_figure"])
    activated["_active_recovery_lock2"] = dict(section)
    return activated


def verify_recovery_prereg_ledger_separation(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    section = config.get("_active_recovery_lock2")
    if not isinstance(section, Mapping):
        return {"active": False}
    prereg_path = repo_path(str(section["prereg_failure_ledger"]))
    if not prereg_path.is_file():
        raise CoregError("recovery prereg failure ledger is missing")
    actual = sha256_file(prereg_path)
    if actual != section["prereg_failure_ledger_sha256"]:
        raise CoregError("recovery prereg failure ledger hash mismatch")
    rows = [
        json.loads(line)
        for line in prereg_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 2 or any(
        row.get("command") != "prepare-controls"
        or row.get("error") != "only 18 eligible controls for required 36"
        or int(row.get("learning_runs_started", -1)) != 0
        for row in rows
    ):
        raise CoregError("unexpected recovery prereg failure ledger contents")
    formal_path = repo_path(config["inputs"]["runtime_dir"]) / "failures.jsonl"
    if formal_path.exists():
        raise CoregError(
            "formal lock2 measurement failure ledger is not fresh before launch"
        )
    return {
        "active": True,
        "prereg_failure_count": len(rows),
        "prereg_failure_ledger_sha256": actual,
        "formal_measurement_failure_ledger_absent": True,
    }


def verify_input_hashes(
    config: Mapping[str, Any], *, verify_depth_set: bool = False
) -> dict[str, str]:
    observed: dict[str, str] = {}
    for logical, expected in config["input_locks"]["expected_sha256"].items():
        path = repo_path(logical)
        if not path.is_file():
            raise CoregError(f"locked input missing: {logical}")
        actual = sha256_file(path)
        if actual != expected:
            raise CoregError(
                f"locked input hash mismatch: {logical}: {actual} != {expected}"
            )
        observed[logical] = actual
    if verify_depth_set:
        depth_dir = repo_path(config["inputs"]["geometric_depth_dir"])
        depth_expected = config["input_locks"]["expected_geometric_depth_set"]
        depth_files = sorted(
            depth_dir.glob("*.geometric.bin"), key=lambda path: path.name
        )
        count = len(depth_files)
        total_bytes = sum(path.stat().st_size for path in depth_files)
        if count != int(depth_expected["file_count"]):
            raise CoregError(f"geometric depth count {count} != locked value")
        if total_bytes != int(depth_expected["total_bytes"]):
            raise CoregError(f"geometric depth bytes {total_bytes} != locked value")
        stream = hashlib.sha256()
        for path in depth_files:
            logical = relative(path)
            stream.update(f"{sha256_file(path)}  {logical}\n".encode())
        aggregate = stream.hexdigest()
        if aggregate != depth_expected["sha256sum_stream_aggregate"]:
            raise CoregError(
                f"geometric depth aggregate {aggregate} != locked value"
            )
        observed[f"{relative(depth_dir)}/*.geometric.bin"] = aggregate
    return observed


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout.strip()


def verify_committed_implementation(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = _git("branch", "--show-current")
    expected_branch = config["git_lock"]["expected_branch"]
    if branch != expected_branch:
        raise CoregError(f"branch {branch!r} != locked {expected_branch!r}")
    status = _git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise CoregError("tracked/untracked worktree is not clean before measurement")
    head = _git("rev-parse", "HEAD")
    hashes: dict[str, str] = {}
    for logical in config["git_lock"]["implementation_files"]:
        path = repo_path(logical)
        if not path.is_file():
            raise CoregError(f"implementation file missing: {logical}")
        tracked = _git("ls-files", "--error-unmatch", logical)
        if tracked != logical:
            raise CoregError(f"implementation file is not tracked: {logical}")
        head_blob = subprocess.run(
            ["git", "show", f"HEAD:{logical}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        work_blob = path.read_bytes()
        if head_blob != work_blob:
            raise CoregError(f"implementation differs from HEAD: {logical}")
        hashes[logical] = hashlib.sha256(work_blob).hexdigest()
    return {"branch": branch, "head": head, "implementation_sha256": hashes}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with repo_path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: str | Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    target = repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _load_footprints(path: str | Path) -> dict[str, Any]:
    from shapely.geometry import shape

    payload = json.loads(repo_path(path).read_text())
    output: dict[str, Any] = {}
    for feature in payload["features"]:
        bid = str(feature["properties"]["building_id"])
        geometry = shape(feature["geometry"])
        if geometry.geom_type == "MultiPolygon":
            geometry = max(geometry.geoms, key=lambda part: part.area)
        if geometry.geom_type != "Polygon":
            continue
        output[bid] = geometry
    return output


def _stable_tie(building_id: str, seed: str = "FUS-W1-COREG-SPLIT-LOCK1") -> str:
    return hashlib.sha256(
        f"{seed}:{building_id}".encode()
    ).hexdigest()


def screen_geometry_availability(
    config: Mapping[str, Any],
    candidate_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Check sample/normal availability only; never form cross-cloud residuals."""

    runtime = repo_path(config["inputs"]["runtime_dir"])
    als_path = runtime / "als_fixed_class2_6_ellipsoidal_zeta45p7.npz"
    receipt_path = runtime / "als_materialization_receipt.json"
    if not als_path.is_file() or not receipt_path.is_file():
        raise CoregError(
            "recovery geometry screen requires prepare-als in its own runtime"
        )
    receipt = json.loads(receipt_path.read_text())
    if (
        sha256_file(als_path) != receipt.get("output_sha256")
        or sha256_file(repo_path(config["inputs"]["als_aoi_laz"]))
        != receipt.get("source_sha256")
    ):
        raise CoregError("recovery geometry screen ALS receipt mismatch")
    with np.load(als_path) as payload:
        als_xyz = np.asarray(payload["xyz"], dtype=np.float64)
        als_cls = np.asarray(payload["classification"], dtype=np.uint8)
    with np.load(repo_path(config["inputs"]["photo_dense_npz"])) as payload:
        dense_xyz = np.asarray(payload["P_utm"], dtype=np.float64)
    als_index = XIndex(als_xyz, als_cls)
    dense_index = XIndex(dense_xyz)
    footprints = _load_footprints(config["inputs"]["footprints_geojson"])
    sampling = config["surface_sampling"]
    minimum = int(sampling["minimum_points_per_building_surface"])
    ground_class = int(config["input_locks"]["als_ground_class"])
    building_class = int(config["input_locks"]["als_building_class"])
    output: dict[str, dict[str, Any]] = {}
    for bid in sorted(candidate_ids):
        polygon = footprints[bid]
        definitions = {
            "roof": _inner_polygon(polygon, sampling["roof_inner_buffer_m"]),
            "ground": polygon.buffer(
                sampling["ground_outer_buffer_m"]
            ).difference(
                polygon.buffer(sampling["ground_inner_exclusion_buffer_m"])
            ),
        }
        record: dict[str, Any] = {
            "building_id": bid,
            "screen_uses_correspondence_residuals": False,
        }
        both_pass = True
        for surface, geometry in definitions.items():
            class_value = building_class if surface == "roof" else ground_class
            fixed = als_index.query_bounds(geometry.bounds, class_value)
            fixed = fixed[polygon_mask(geometry, fixed)]
            moving = dense_index.query_bounds(geometry.bounds)
            moving = moving[polygon_mask(geometry, moving)]
            if len(fixed) > 0 and len(moving) > 0:
                if surface == "roof":
                    lo, hi = np.quantile(fixed[:, 2], [0.01, 0.99])
                    margin = float(sampling["dense_roof_vertical_margin_m"])
                else:
                    lo, hi = np.quantile(fixed[:, 2], [0.02, 0.98])
                    margin = float(sampling["dense_ground_vertical_margin_m"])
                moving = moving[
                    (moving[:, 2] >= lo - margin)
                    & (moving[:, 2] <= hi + margin)
                ]
            fixed = deterministic_voxel(
                fixed,
                sampling["voxel_m"],
                sampling["maximum_points_per_building_surface"],
            )
            moving = deterministic_voxel(
                moving,
                sampling["voxel_m"],
                sampling["maximum_points_per_building_surface"],
            )
            fixed_valid_count = 0
            moving_valid_count = 0
            if len(fixed) >= minimum:
                _, fixed_valid = estimate_normals(
                    fixed,
                    sampling["normal_knn"],
                    sampling["normal_radius_m"],
                    sampling["minimum_normal_neighbors"],
                    sampling["maximum_surface_variation"],
                )
                fixed_valid_count = int(np.sum(fixed_valid))
            if len(moving) >= minimum:
                _, moving_valid = estimate_normals(
                    moving,
                    sampling["normal_knn"],
                    sampling["normal_radius_m"],
                    sampling["minimum_normal_neighbors"],
                    sampling["maximum_surface_variation"],
                )
                moving_valid_count = int(np.sum(moving_valid))
            surface_pass = (
                len(fixed) >= minimum
                and len(moving) >= minimum
                and fixed_valid_count >= minimum
                and moving_valid_count >= minimum
            )
            record[f"screen_{surface}_fixed_points"] = len(fixed)
            record[f"screen_{surface}_moving_points"] = len(moving)
            record[f"screen_{surface}_fixed_valid_normals"] = fixed_valid_count
            record[f"screen_{surface}_moving_valid_normals"] = moving_valid_count
            record[f"screen_{surface}_pass"] = str(surface_pass).lower()
            both_pass = both_pass and surface_pass
        record["geometry_feasibility_pass"] = str(both_pass).lower()
        output[bid] = record
    return output


def select_control_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    from shapely.ops import unary_union

    targets = {
        row["building_id"]: row for row in _read_csv(config["inputs"]["targets_csv"])
    }
    status = {
        row["building_id"]: row for row in _read_csv(config["inputs"]["w2_status_csv"])
    }
    footprints = _load_footprints(config["inputs"]["footprints_geojson"])
    split_cfg = config["split"]
    core_ids = {bid for bid, row in targets.items() if row["cohort"] == "core"}
    excluded_calibration_ids: set[str] = set()
    for split_path in split_cfg.get("excluded_calibration_split_csvs", []):
        excluded_calibration_ids.update(
            row["building_id"] for row in _read_csv(split_path)
        )
    if len(core_ids) != 28:
        raise CoregError(f"expected 28 core ids, observed {len(core_ids)}")
    core_geometries = [footprints[bid] for bid in sorted(core_ids) if bid in footprints]
    if len(core_geometries) != len(core_ids):
        missing = sorted(core_ids - footprints.keys())
        raise CoregError(f"core footprints missing: {missing}")
    core_union = unary_union(core_geometries)

    eligible: list[dict[str, Any]] = []
    for bid, target in targets.items():
        if target["cohort"] != split_cfg["calibration_cohort"]:
            continue
        allowed_tiers = set(
            split_cfg.get(
                "calibration_tiers", [split_cfg["calibration_tier"]]
            )
        )
        if target["tier"] not in allowed_tiers:
            continue
        if (
            bid in core_ids
            or bid in excluded_calibration_ids
            or bid not in footprints
            or bid not in status
        ):
            continue
        current = status[bid]
        if current.get("als_has_lod22") != "True":
            continue
        if current.get("dim_has_lod22") != "True":
            continue
        als_density = float(current.get("als_rf_pt_density") or 0.0)
        dim_density = float(current.get("dim_rf_pt_density") or 0.0)
        if als_density < float(split_cfg["minimum_als_density_pts_m2"]):
            continue
        if dim_density < float(split_cfg["minimum_dim_density_pts_m2"]):
            continue
        geometry = footprints[bid]
        if geometry.intersects(core_union):
            continue
        distance = float(geometry.distance(core_union))
        if distance + 1e-9 < float(split_cfg["minimum_core_footprint_distance_m"]):
            continue
        centroid = geometry.centroid
        support = math.sqrt(als_density * dim_density)
        eligible.append(
            {
                "building_id": bid,
                "tier": target["tier"],
                "centroid_x_m": float(centroid.x),
                "centroid_y_m": float(centroid.y),
                "core_footprint_distance_m": distance,
                "als_density_pts_m2": als_density,
                "dim_density_pts_m2": dim_density,
                "support_geomean_pts_m2": support,
                "stable_tie_sha256": _stable_tie(
                    bid,
                    str(
                        split_cfg.get(
                            "stable_tie_seed", "FUS-W1-COREG-SPLIT-LOCK1"
                        )
                    ),
                ),
            }
        )
    if bool(split_cfg.get("geometry_feasibility_screen_required", False)):
        screen = screen_geometry_availability(
            config, [row["building_id"] for row in eligible]
        )
        screened: list[dict[str, Any]] = []
        for row in eligible:
            evidence = screen[row["building_id"]]
            if evidence["geometry_feasibility_pass"] != "true":
                continue
            row.update(evidence)
            screened.append(row)
        eligible = screened
    count = int(split_cfg["selected_count"])
    if len(eligible) < count:
        raise CoregError(f"only {len(eligible)} eligible controls for required {count}")

    def pop_maximin(
        pool: list[dict[str, Any]], selected_rows: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        if not pool:
            raise CoregError("maximin role pool exhausted")
        if not selected_rows:
            pool.sort(
                key=lambda row: (
                    -row["support_geomean_pts_m2"],
                    row["stable_tie_sha256"],
                )
            )
            selected_row = pool.pop(0)
            selected_row["maximin_distance_m"] = float("nan")
            return selected_row
        for row in pool:
            row["maximin_distance_m"] = min(
                math.hypot(
                    row["centroid_x_m"] - other["centroid_x_m"],
                    row["centroid_y_m"] - other["centroid_y_m"],
                )
                for other in selected_rows
            )
        pool.sort(
            key=lambda row: (
                -row["maximin_distance_m"],
                -row["support_geomean_pts_m2"],
                row["stable_tie_sha256"],
            )
        )
        return pool.pop(0)

    chosen: list[dict[str, Any]] = []
    prior_split_path = split_cfg.get("prior_exposure_split_csv")
    if prior_split_path:
        if split_cfg.get("prior_fit_residual_exposure_policy") != "fit_only":
            raise CoregError("prior fit-residual exposure must remain fit-only")
        if int(split_cfg.get("prior_trigger_check_residuals_evaluated", -1)) != 0:
            raise CoregError("prior trigger/check residual exposure is not zero")
        prior_roles = {
            row["building_id"]: row["role"]
            for row in _read_csv(prior_split_path)
        }
        for row in eligible:
            prior_role = prior_roles.get(row["building_id"], "")
            row["prior_lock1_role"] = prior_role
            row["prior_fit_residual_exposed"] = str(
                prior_role == "fit"
            ).lower()
        fit_count = int(split_cfg["role_counts"]["fit"])
        prior_fit_pool = [
            row for row in eligible if row["prior_fit_residual_exposed"] == "true"
        ]
        other_pool = [
            row for row in eligible if row["prior_fit_residual_exposed"] != "true"
        ]
        while len(chosen) < fit_count and prior_fit_pool:
            selected = pop_maximin(prior_fit_pool, chosen)
            selected["role"] = "fit"
            chosen.append(selected)
        while len(chosen) < fit_count:
            selected = pop_maximin(other_pool, chosen)
            selected["role"] = "fit"
            chosen.append(selected)
        holdout_pool = [
            row
            for row in other_pool + prior_fit_pool
            if row["building_id"]
            not in {chosen_row["building_id"] for chosen_row in chosen}
        ]
        holdout_roles = ["trigger", "check"] * int(
            split_cfg["role_counts"]["trigger"]
        )
        for role in holdout_roles:
            selected = pop_maximin(holdout_pool, chosen)
            selected["role"] = role
            chosen.append(selected)
    else:
        remaining = list(eligible)
        while len(chosen) < count:
            selected = pop_maximin(remaining, chosen)
            pattern = split_cfg["role_pattern"]
            selected["role"] = pattern[len(chosen) % len(pattern)]
            chosen.append(selected)

    for index, selected in enumerate(chosen, 1):
        selected["selection_rank"] = index
        selected["calibration_exposed"] = "true"
        selected["later_extension_judgment_eligible"] = "false"
        selected["selection_reason"] = (
            "extension_allowed_tier_both_assembled;positive_density;"
            "no_core_overlap;core_distance_ge_20m;"
            + (
                "pre_role_geometry_feasibility_pass;"
                if split_cfg.get("geometry_feasibility_screen_required")
                else ""
            )
            + "support_seed_then_centroid_maximin"
        )

    observed_roles: dict[str, int] = {}
    for row in chosen:
        observed_roles[row["role"]] = observed_roles.get(row["role"], 0) + 1
    expected_roles = {key: int(value) for key, value in split_cfg["role_counts"].items()}
    if observed_roles != expected_roles:
        raise CoregError(f"role counts {observed_roles} != {expected_roles}")
    if core_ids & {row["building_id"] for row in chosen}:
        raise CoregError("core id leaked into calibration split")
    return chosen


@dataclass
class ColmapImageRecord:
    image_id: int
    qvec: np.ndarray
    tvec: np.ndarray
    camera_id: int
    name: str
    points2d_tail: bytes


def _read_c_string(handle: Any) -> str:
    value = bytearray()
    while True:
        byte = handle.read(1)
        if not byte:
            raise CoregError("truncated COLMAP string")
        if byte == b"\x00":
            return value.decode("utf-8")
        value.extend(byte)


def read_images_bin_complete(path: str | Path) -> dict[int, ColmapImageRecord]:
    output: dict[int, ColmapImageRecord] = {}
    with repo_path(path).open("rb") as handle:
        raw_count = handle.read(8)
        if len(raw_count) != 8:
            raise CoregError("truncated images.bin header")
        count = struct.unpack("<Q", raw_count)[0]
        for _ in range(count):
            fixed = handle.read(64)
            if len(fixed) != 64:
                raise CoregError("truncated images.bin image record")
            unpacked = struct.unpack("<IdddddddI", fixed)
            image_id = int(unpacked[0])
            qvec = np.asarray(unpacked[1:5], dtype=np.float64)
            tvec = np.asarray(unpacked[5:8], dtype=np.float64)
            camera_id = int(unpacked[8])
            name = _read_c_string(handle)
            raw_n = handle.read(8)
            if len(raw_n) != 8:
                raise CoregError("truncated points2D count")
            n_points = struct.unpack("<Q", raw_n)[0]
            payload = handle.read(24 * n_points)
            if len(payload) != 24 * n_points:
                raise CoregError("truncated points2D payload")
            output[image_id] = ColmapImageRecord(
                image_id, qvec, tvec, camera_id, name, raw_n + payload
            )
        if handle.read(1):
            raise CoregError("unexpected trailing bytes in images.bin")
    return output


def write_images_bin_complete(
    path: str | Path, images: Mapping[int, ColmapImageRecord]
) -> None:
    target = repo_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.write(struct.pack("<Q", len(images)))
        for image_id in sorted(images):
            image = images[image_id]
            handle.write(struct.pack("<I", int(image.image_id)))
            handle.write(struct.pack("<dddd", *np.asarray(image.qvec, dtype=float)))
            handle.write(struct.pack("<ddd", *np.asarray(image.tvec, dtype=float)))
            handle.write(struct.pack("<I", int(image.camera_id)))
            handle.write(image.name.encode("utf-8") + b"\x00")
            handle.write(image.points2d_tail)


def build_camera_block_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    camera_list = json.loads(repo_path(config["inputs"]["opf_camera_list"]).read_text())
    input_cameras = json.loads(
        repo_path(config["inputs"]["opf_input_cameras"]).read_text()
    )
    id_to_name = {
        int(row["id"]): Path(row["uri"]).name for row in camera_list["cameras"]
    }
    capture_times: dict[str, datetime] = {}
    for capture in input_cameras["captures"]:
        camera_id = int(capture["reference_camera_id"])
        name = id_to_name.get(camera_id)
        if name is None:
            continue
        capture_times[name] = datetime.fromisoformat(capture["time"])

    sparse = repo_path(config["inputs"]["colmap_sparse_dir"])
    images = read_images_bin_complete(sparse / "images.bin")
    ordered: list[tuple[str, datetime]] = []
    for image in images.values():
        name = image.name
        time = capture_times.get(name)
        if time is None:
            time = capture_times.get(Path(name).with_suffix(".JPG").name)
        if time is None:
            raise CoregError(f"no OPF capture time for COLMAP image {name}")
        ordered.append((name, time))
    ordered.sort(key=lambda item: (item[1], item[0]))
    gap = float(config["conditional_blocks"]["gap_seconds"])
    block_index = 0
    previous: datetime | None = None
    assignments: list[tuple[str, datetime, int]] = []
    for name, time in ordered:
        if previous is None or (time - previous).total_seconds() > gap:
            block_index += 1
        assignments.append((name, time, block_index))
        previous = time
    block_times: dict[int, tuple[datetime, datetime]] = {}
    counts: dict[int, int] = {}
    for _, time, index in assignments:
        if index not in block_times:
            block_times[index] = (time, time)
        else:
            block_times[index] = (block_times[index][0], time)
        counts[index] = counts.get(index, 0) + 1
    rows: list[dict[str, Any]] = []
    for name, time, index in assignments:
        rows.append(
            {
                "image_name": name,
                "capture_time": time.isoformat(),
                "block_id": f"capture_block_{index:02d}",
                "block_start": block_times[index][0].isoformat(),
                "block_end": block_times[index][1].isoformat(),
                "block_image_count": counts[index],
                "definition": f"OPF capture time gap > {gap:.0f} seconds",
                "result_blind": "true",
            }
        )
    if len(rows) != int(
        config["input_locks"].get("expected_training_pose_image_intersection", 937)
    ):
        if len(rows) != 937:
            raise CoregError(f"expected 937 camera block rows, observed {len(rows)}")
    return rows


def render_prereg_split(
    config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], output: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    footprints = _load_footprints(config["inputs"]["footprints_geojson"])
    targets = {
        row["building_id"]: row for row in _read_csv(config["inputs"]["targets_csv"])
    }
    fig, ax = plt.subplots(figsize=(9, 10), constrained_layout=True)
    for bid, geometry in footprints.items():
        x, y = geometry.exterior.xy
        is_core = targets.get(bid, {}).get("cohort") == "core"
        ax.plot(
            x,
            y,
            color="#a0a0a0" if not is_core else "#252525",
            linewidth=0.35 if not is_core else 0.9,
            alpha=0.45 if not is_core else 0.9,
        )
    colors = {"fit": "#1976d2", "trigger": "#f57c00", "check": "#7b1fa2"}
    for role, color in colors.items():
        subset = [row for row in rows if row["role"] == role]
        ax.scatter(
            [float(row["centroid_x_m"]) for row in subset],
            [float(row["centroid_y_m"]) for row in subset],
            s=42,
            c=color,
            label=f"{role} (n={len(subset)})",
            edgecolors="white",
            linewidths=0.5,
            zorder=4,
        )
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (EPSG:25832, m)")
    ax.set_ylabel("Northing (EPSG:25832, m)")
    ax.set_title("FUS-W1 camera co-registration preregistered controls")
    ax.legend(loc="best")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def prepare_controls(config: Mapping[str, Any]) -> dict[str, Any]:
    locked_inputs = verify_input_hashes(config, verify_depth_set=True)
    rows = select_control_rows(config)
    split_path = repo_path(config["inputs"]["splits_csv"])
    fields = [
        "selection_rank",
        "building_id",
        "tier",
        "role",
        "calibration_exposed",
        "later_extension_judgment_eligible",
        "centroid_x_m",
        "centroid_y_m",
        "core_footprint_distance_m",
        "als_density_pts_m2",
        "dim_density_pts_m2",
        "support_geomean_pts_m2",
        "maximin_distance_m",
        "stable_tie_sha256",
        "selection_reason",
    ]
    screen_fields = [
        "screen_uses_correspondence_residuals",
        "screen_roof_fixed_points",
        "screen_roof_moving_points",
        "screen_roof_fixed_valid_normals",
        "screen_roof_moving_valid_normals",
        "screen_roof_pass",
        "screen_ground_fixed_points",
        "screen_ground_moving_points",
        "screen_ground_fixed_valid_normals",
        "screen_ground_moving_valid_normals",
        "screen_ground_pass",
        "geometry_feasibility_pass",
    ]
    if config["split"].get("geometry_feasibility_screen_required"):
        fields.extend(screen_fields)
    if config["split"].get("prior_exposure_split_csv"):
        fields.extend(
            ["prior_lock1_role", "prior_fit_residual_exposed"]
        )
    serial_rows: list[dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        for key in (
            "centroid_x_m",
            "centroid_y_m",
            "core_footprint_distance_m",
            "als_density_pts_m2",
            "dim_density_pts_m2",
            "support_geomean_pts_m2",
            "maximin_distance_m",
        ):
            value = float(current[key])
            current[key] = "" if not math.isfinite(value) else f"{value:.9f}"
        serial_rows.append(current)
    _write_csv(split_path, fields, serial_rows)

    block_rows = build_camera_block_rows(config)
    block_path = repo_path(config["inputs"]["camera_blocks_csv"])
    _write_csv(
        block_path,
        [
            "image_name",
            "capture_time",
            "block_id",
            "block_start",
            "block_end",
            "block_image_count",
            "definition",
            "result_blind",
        ],
        block_rows,
    )
    run_root = split_path.parent
    figure = repo_path(
        config.get("_prereg_figure_path", run_root / "w1_coreg_prereg_split.png")
    )
    render_prereg_split(config, rows, figure)
    manifest_path = repo_path(
        config.get(
            "_prereg_manifest_path",
            run_root / "w1_coreg_prereg_manifest.json",
        )
    )
    manifest = {
        "schema": "jointbuildgs.fusion_w1.coreg_prereg_manifest.v1",
        "status": "PREPARED_BEFORE_RESIDUAL_MEASUREMENT",
        "task_id": config["task_id"],
        "treatment_name": config["treatment_name"],
        "selection": {
            "count": len(rows),
            "role_counts": {
                role: sum(row["role"] == role for row in rows)
                for role in ("fit", "trigger", "check")
            },
            "tier_counts": {
                tier: sum(row["tier"] == tier for row in rows)
                for tier in sorted({row["tier"] for row in rows})
            },
            "core_count_used": 0,
            "minimum_core_distance_m": min(
                float(row["core_footprint_distance_m"]) for row in rows
            ),
            "geometry_feasibility_screen_required": bool(
                config["split"].get("geometry_feasibility_screen_required")
            ),
            "geometry_feasibility_screen_uses_correspondence_residuals": False,
            "geometry_feasibility_screen_nominal_alignment_sensitive": bool(
                config["split"].get(
                    "geometry_feasibility_screen_nominal_alignment_sensitive"
                )
            ),
            "alignment_judgment_scope": config["split"].get(
                "alignment_judgment_scope"
            ),
            "excluded_prior_calibration_count": len(
                {
                    prior["building_id"]
                    for path in config["split"].get(
                        "excluded_calibration_split_csvs", []
                    )
                    for prior in _read_csv(path)
                }
            ),
            "prior_fit_residual_exposed_reused_as_fit_count": sum(
                row.get("prior_fit_residual_exposed") == "true"
                and row["role"] == "fit"
                for row in rows
            ),
            "prior_fit_residual_exposed_in_holdout_count": sum(
                row.get("prior_fit_residual_exposed") == "true"
                and row["role"] in {"trigger", "check"}
                for row in rows
            ),
        },
        "capture_blocks": {
            "row_count": len(block_rows),
            "counts": {
                block: sum(row["block_id"] == block for row in block_rows)
                for block in sorted({row["block_id"] for row in block_rows})
            },
            "gap_seconds": config["conditional_blocks"]["gap_seconds"],
        },
        "artifacts": {
            relative(split_path): sha256_file(split_path),
            relative(block_path): sha256_file(block_path),
            relative(figure): sha256_file(figure),
        },
        "input_sha256": locked_inputs,
        "new_residuals_read": 0,
        "learning_runs_started": 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def prepare_als(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        import laspy
    except ImportError as exc:
        raise CoregError("prepare-als must run in the pinned tools image") from exc
    verify_input_hashes(config)
    source = repo_path(config["inputs"]["als_aoi_laz"])
    runtime = repo_path(config["inputs"]["runtime_dir"])
    runtime.mkdir(parents=True, exist_ok=True)
    receipt_path = runtime / "als_materialization_receipt.json"
    if receipt_path.is_file():
        existing = json.loads(receipt_path.read_text())
        output = repo_path(existing["output"])
        if (
            existing.get("source_sha256") == sha256_file(source)
            and output.is_file()
            and existing.get("output_sha256") == sha256_file(output)
            and existing.get("zeta_m")
            == float(config["input_locks"]["orthometric_to_ellipsoidal_zeta_m"])
        ):
            return existing
        raise CoregError("existing ALS materialization receipt is stale or tampered")
    las = laspy.read(source)
    classes = np.asarray(las.classification, dtype=np.uint8)
    unique = set(int(value) for value in np.unique(classes))
    expected = {
        int(config["input_locks"]["als_ground_class"]),
        int(config["input_locks"]["als_building_class"]),
    }
    if unique != expected:
        raise CoregError(f"ALS classes {unique} != locked {expected}")
    xyz = np.column_stack(
        [
            np.asarray(las.x, dtype=np.float64),
            np.asarray(las.y, dtype=np.float64),
            np.asarray(las.z, dtype=np.float64)
            + float(config["input_locks"]["orthometric_to_ellipsoidal_zeta_m"]),
        ]
    )
    target = runtime / "als_fixed_class2_6_ellipsoidal_zeta45p7.npz"
    np.savez(target, xyz=xyz, classification=classes)
    receipt = {
        "schema": "jointbuildgs.fusion_w1.coreg_als_materialization.v1",
        "source": relative(source),
        "source_sha256": sha256_file(source),
        "source_bytes_after": source.stat().st_size,
        "output": relative(target),
        "output_sha256": sha256_file(target),
        "point_count": int(len(xyz)),
        "class_counts": {
            str(value): int(np.sum(classes == value)) for value in sorted(unique)
        },
        "zeta_m": float(config["input_locks"]["orthometric_to_ellipsoidal_zeta_m"]),
        "source_als_modified": False,
    }
    write_json(receipt_path, receipt, exclusive=True)
    if sha256_file(source) != config["input_locks"]["expected_sha256"][relative(source)]:
        raise CoregError("source ALS hash changed during materialization")
    return receipt


class XIndex:
    def __init__(self, xyz: np.ndarray, classification: np.ndarray | None = None):
        xyz = np.asarray(xyz, dtype=np.float64)
        order = np.argsort(xyz[:, 0], kind="mergesort")
        self.xyz = xyz[order]
        self.x = self.xyz[:, 0]
        self.classification = (
            None
            if classification is None
            else np.asarray(classification, dtype=np.uint8)[order]
        )

    def query_bounds(
        self, bounds: Sequence[float], classification: int | None = None
    ) -> np.ndarray:
        xmin, ymin, xmax, ymax = map(float, bounds)
        lo = int(np.searchsorted(self.x, xmin, side="left"))
        hi = int(np.searchsorted(self.x, xmax, side="right"))
        subset = self.xyz[lo:hi]
        mask = (subset[:, 1] >= ymin) & (subset[:, 1] <= ymax)
        if classification is not None:
            if self.classification is None:
                raise CoregError("classification requested from unclassified cloud")
            mask &= self.classification[lo:hi] == classification
        return subset[mask]


def polygon_mask(geometry: Any, points: np.ndarray) -> np.ndarray:
    from shapely import contains_xy

    return np.asarray(contains_xy(geometry, points[:, 0], points[:, 1]), dtype=bool)


def deterministic_voxel(points: np.ndarray, voxel: float, cap: int) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 0:
        return points.reshape(0, 3)
    cells = np.floor(points / float(voxel)).astype(np.int64)
    order = np.lexsort((points[:, 2], points[:, 1], points[:, 0]))
    cells_ordered = cells[order]
    _, first = np.unique(cells_ordered, axis=0, return_index=True)
    selected = points[order[np.sort(first)]]
    if len(selected) > int(cap):
        indices = np.linspace(0, len(selected) - 1, int(cap)).astype(int)
        selected = selected[indices]
    return selected


def estimate_normals(
    points: np.ndarray,
    knn: int,
    radius: float,
    minimum_neighbors: int,
    maximum_surface_variation: float,
) -> tuple[np.ndarray, np.ndarray]:
    from scipy.spatial import cKDTree

    points = np.asarray(points, dtype=np.float64)
    tree = cKDTree(points)
    normals = np.full_like(points, np.nan)
    valid_normals = np.zeros(len(points), dtype=bool)
    for start in range(0, len(points), 1024):
        query = points[start : start + 1024]
        distances, indices = tree.query(
            query, k=min(int(knn), len(points)), distance_upper_bound=float(radius)
        )
        if distances.ndim == 1:
            distances = distances[:, None]
            indices = indices[:, None]
        for offset, (dist, idx) in enumerate(zip(distances, indices)):
            valid = np.isfinite(dist) & (idx < len(points))
            neighbors = points[idx[valid]]
            if len(neighbors) < int(minimum_neighbors):
                continue
            centered = neighbors - neighbors.mean(axis=0)
            covariance = centered.T @ centered / max(1, len(centered) - 1)
            values, vectors = np.linalg.eigh(covariance)
            variation = float(values[0] / max(float(np.sum(values)), 1e-12))
            if not math.isfinite(variation) or variation > float(
                maximum_surface_variation
            ):
                continue
            normal = vectors[:, 0]
            if normal[2] < 0:
                normal = -normal
            normals[start + offset] = normal / max(np.linalg.norm(normal), 1e-12)
            valid_normals[start + offset] = True
    return normals, valid_normals


@dataclass
class SurfaceGroup:
    building_id: str
    role: str
    surface: str
    fixed: np.ndarray
    moving: np.ndarray
    fixed_normals: np.ndarray
    moving_normals: np.ndarray
    block_id: str = ""
    observation_count: int = 0


def _inner_polygon(polygon: Any, amount: float) -> Any:
    inner = polygon.buffer(-float(amount))
    if inner.is_empty:
        return polygon
    if inner.geom_type == "MultiPolygon":
        inner = max(inner.geoms, key=lambda part: part.area)
    return inner


def build_surface_groups(
    config: Mapping[str, Any], roles: set[str]
) -> tuple[list[SurfaceGroup], dict[str, Any]]:
    runtime = repo_path(config["inputs"]["runtime_dir"])
    als_path = runtime / "als_fixed_class2_6_ellipsoidal_zeta45p7.npz"
    if not als_path.is_file():
        raise CoregError("materialized ALS is missing; run prepare-als first")
    receipt_path = runtime / "als_materialization_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if sha256_file(als_path) != receipt["output_sha256"]:
        raise CoregError("materialized ALS hash differs from receipt")
    source_als = repo_path(config["inputs"]["als_aoi_laz"])
    if sha256_file(source_als) != receipt["source_sha256"]:
        raise CoregError("source ALS changed after materialization")
    with np.load(als_path) as payload:
        als_xyz = np.asarray(payload["xyz"], dtype=np.float64)
        als_cls = np.asarray(payload["classification"], dtype=np.uint8)
    dense_path = repo_path(config["inputs"]["photo_dense_npz"])
    with np.load(dense_path) as payload:
        dense_xyz = np.asarray(payload["P_utm"], dtype=np.float64)
    als_index = XIndex(als_xyz, als_cls)
    dense_index = XIndex(dense_xyz)
    footprints = _load_footprints(config["inputs"]["footprints_geojson"])
    controls = [
        row
        for row in _read_csv(config["inputs"]["splits_csv"])
        if row["role"] in roles
    ]
    sampling = config["surface_sampling"]
    groups: list[SurfaceGroup] = []
    audit_rows: list[dict[str, Any]] = []
    ground_class = int(config["input_locks"]["als_ground_class"])
    building_class = int(config["input_locks"]["als_building_class"])
    for control in controls:
        bid = control["building_id"]
        polygon = footprints[bid]
        definitions = {
            "roof": _inner_polygon(polygon, sampling["roof_inner_buffer_m"]),
            "ground": polygon.buffer(sampling["ground_outer_buffer_m"]).difference(
                polygon.buffer(sampling["ground_inner_exclusion_buffer_m"])
            ),
        }
        for surface, geometry in definitions.items():
            class_value = building_class if surface == "roof" else ground_class
            fixed = als_index.query_bounds(geometry.bounds, class_value)
            fixed = fixed[polygon_mask(geometry, fixed)]
            moving = dense_index.query_bounds(geometry.bounds)
            moving = moving[polygon_mask(geometry, moving)]
            if len(fixed) > 0 and len(moving) > 0:
                if surface == "roof":
                    lo, hi = np.quantile(fixed[:, 2], [0.01, 0.99])
                    margin = float(sampling["dense_roof_vertical_margin_m"])
                else:
                    lo, hi = np.quantile(fixed[:, 2], [0.02, 0.98])
                    margin = float(sampling["dense_ground_vertical_margin_m"])
                moving = moving[
                    (moving[:, 2] >= lo - margin) & (moving[:, 2] <= hi + margin)
                ]
            fixed = deterministic_voxel(
                fixed,
                sampling["voxel_m"],
                sampling["maximum_points_per_building_surface"],
            )
            moving = deterministic_voxel(
                moving,
                sampling["voxel_m"],
                sampling["maximum_points_per_building_surface"],
            )
            minimum = int(sampling["minimum_points_per_building_surface"])
            audit_rows.append(
                {
                    "building_id": bid,
                    "role": control["role"],
                    "surface": surface,
                    "fixed_als_points": len(fixed),
                    "moving_photo_points": len(moving),
                    "used": str(len(fixed) >= minimum and len(moving) >= minimum).lower(),
                }
            )
            if len(fixed) < minimum or len(moving) < minimum:
                continue
            fixed_normals, fixed_normal_valid = estimate_normals(
                fixed,
                sampling["normal_knn"],
                sampling["normal_radius_m"],
                sampling["minimum_normal_neighbors"],
                sampling["maximum_surface_variation"],
            )
            moving_normals, moving_normal_valid = estimate_normals(
                moving,
                sampling["normal_knn"],
                sampling["normal_radius_m"],
                sampling["minimum_normal_neighbors"],
                sampling["maximum_surface_variation"],
            )
            fixed = fixed[fixed_normal_valid]
            fixed_normals = fixed_normals[fixed_normal_valid]
            moving = moving[moving_normal_valid]
            moving_normals = moving_normals[moving_normal_valid]
            audit_rows[-1]["fixed_valid_normals"] = len(fixed)
            audit_rows[-1]["moving_valid_normals"] = len(moving)
            audit_rows[-1]["used"] = str(
                len(fixed) >= minimum and len(moving) >= minimum
            ).lower()
            if len(fixed) < minimum or len(moving) < minimum:
                continue
            groups.append(
                SurfaceGroup(
                    building_id=bid,
                    role=control["role"],
                    surface=surface,
                    fixed=fixed,
                    moving=moving,
                    fixed_normals=fixed_normals,
                    moving_normals=moving_normals,
                )
            )
    required_buildings = {row["building_id"] for row in controls}
    observed_surfaces: dict[str, set[str]] = {}
    for group in groups:
        observed_surfaces.setdefault(group.building_id, set()).add(group.surface)
    required_surfaces = {"roof", "ground"}
    missing = sorted(
        bid
        for bid in required_buildings
        if observed_surfaces.get(bid, set()) != required_surfaces
    )
    if missing:
        raise CoregError(f"controls without both usable roof and ground: {missing}")
    audit = {
        "roles": sorted(roles),
        "surface_groups": len(groups),
        "building_count": len(observed_surfaces),
        "rows": audit_rows,
        "als_materialization_sha256": receipt["output_sha256"],
        "source_als_sha256": receipt["source_sha256"],
        "photo_dense_sha256": sha256_file(dense_path),
    }
    return groups, audit


def build_block_surface_groups(
    config: Mapping[str, Any], roles: set[str]
) -> tuple[list[SurfaceGroup], dict[str, Any]]:
    """Build block-labelled photo clouds from locked-stride geometric depth."""
    from src.stage2.colmap_io import read_array, read_cameras_bin

    verify_input_hashes(config, verify_depth_set=True)
    templates, template_audit = build_surface_groups(config, roles)
    template_map = {
        (group.building_id, group.surface): group for group in templates
    }
    footprints = _load_footprints(config["inputs"]["footprints_geojson"])
    sampling = config["surface_sampling"]
    geometries: dict[tuple[str, str], Any] = {}
    z_windows: dict[tuple[str, str], tuple[float, float]] = {}
    for key, group in template_map.items():
        bid, surface = key
        polygon = footprints[bid]
        if surface == "roof":
            geometry = _inner_polygon(polygon, sampling["roof_inner_buffer_m"])
            margin = float(sampling["dense_roof_vertical_margin_m"])
            low, high = np.quantile(group.fixed[:, 2], [0.01, 0.99])
        else:
            geometry = polygon.buffer(
                sampling["ground_outer_buffer_m"]
            ).difference(
                polygon.buffer(sampling["ground_inner_exclusion_buffer_m"])
            )
            margin = float(sampling["dense_ground_vertical_margin_m"])
            low, high = np.quantile(group.fixed[:, 2], [0.02, 0.98])
        geometries[key] = geometry
        z_windows[key] = (float(low - margin), float(high + margin))

    block_rows = _read_csv(config["inputs"]["camera_blocks_csv"])
    image_to_block = {row["image_name"]: row["block_id"] for row in block_rows}
    sparse = repo_path(config["inputs"]["colmap_sparse_dir"])
    images = read_images_bin_complete(sparse / "images.bin")
    cameras = read_cameras_bin(sparse / "cameras.bin")
    depth_dir = repo_path(config["inputs"]["geometric_depth_dir"])
    shift = np.asarray(
        config["input_locks"]["scene_global_to_canonical_shift_m"],
        dtype=np.float64,
    )
    block_cfg = config["conditional_blocks"]
    stride = int(block_cfg["depth_pixel_stride"])
    minimum_depth = float(block_cfg["minimum_depth_m"])
    maximum_depth = float(block_cfg["maximum_depth_m"])
    accumulated: dict[tuple[str, str, str], list[np.ndarray]] = {}
    observations: dict[tuple[str, str, str], set[str]] = {}

    for image_id in sorted(images):
        image = images[image_id]
        block_id = image_to_block.get(image.name)
        if block_id is None:
            raise CoregError(f"camera block missing for {image.name}")
        depth_path = depth_dir / f"{image.name}.geometric.bin"
        if not depth_path.is_file():
            raise CoregError(f"geometric depth missing for {image.name}")
        depth = np.asarray(read_array(depth_path), dtype=np.float64)
        if depth.ndim == 3:
            depth = np.squeeze(depth)
        if depth.ndim != 2:
            raise CoregError(f"unexpected depth dimensions for {image.name}")
        height, width = depth.shape
        ys = np.arange(stride // 2, height, stride, dtype=np.int64)
        xs = np.arange(stride // 2, width, stride, dtype=np.int64)
        grid_x, grid_y = np.meshgrid(xs, ys)
        sampled_depth = depth[grid_y, grid_x]
        valid = (
            np.isfinite(sampled_depth)
            & (sampled_depth >= minimum_depth)
            & (sampled_depth <= maximum_depth)
        )
        if not np.any(valid):
            continue
        camera = cameras[image.camera_id]
        intrinsic = camera.K()
        u = (grid_x[valid].astype(np.float64) + 0.5) * (
            float(camera.width) / width
        ) - 0.5
        v = (grid_y[valid].astype(np.float64) + 0.5) * (
            float(camera.height) / height
        ) - 0.5
        z = sampled_depth[valid]
        camera_points = np.column_stack(
            [
                (u - intrinsic[0, 2]) * z / intrinsic[0, 0],
                (v - intrinsic[1, 2]) * z / intrinsic[1, 1],
                z,
            ]
        )
        rotation = qvec_to_rotmat(image.qvec)
        canonical = (rotation.T @ (camera_points - image.tvec).T).T
        global_points = canonical - shift
        for key, geometry in geometries.items():
            xmin, ymin, xmax, ymax = geometry.bounds
            low_z, high_z = z_windows[key]
            bounds_mask = (
                (global_points[:, 0] >= xmin)
                & (global_points[:, 0] <= xmax)
                & (global_points[:, 1] >= ymin)
                & (global_points[:, 1] <= ymax)
                & (global_points[:, 2] >= low_z)
                & (global_points[:, 2] <= high_z)
            )
            if not np.any(bounds_mask):
                continue
            subset = global_points[bounds_mask]
            subset = subset[polygon_mask(geometry, subset)]
            if len(subset) == 0:
                continue
            accumulator_key = (block_id, key[0], key[1])
            accumulated.setdefault(accumulator_key, []).append(subset)
            observations.setdefault(accumulator_key, set()).add(image.name)

    output: list[SurfaceGroup] = []
    audit_rows: list[dict[str, Any]] = []
    minimum = int(block_cfg["minimum_points_per_building_surface"])
    for (block_id, bid, surface), chunks in sorted(accumulated.items()):
        template = template_map[(bid, surface)]
        moving = deterministic_voxel(
            np.vstack(chunks),
            sampling["voxel_m"],
            sampling["maximum_points_per_building_surface"],
        )
        moving_normals, valid = estimate_normals(
            moving,
            sampling["normal_knn"],
            sampling["normal_radius_m"],
            sampling["minimum_normal_neighbors"],
            sampling["maximum_surface_variation"],
        )
        moving = moving[valid]
        moving_normals = moving_normals[valid]
        used = len(moving) >= minimum
        audit_rows.append(
            {
                "block_id": block_id,
                "building_id": bid,
                "role": template.role,
                "surface": surface,
                "moving_points": len(moving),
                "observation_views": len(observations[(block_id, bid, surface)]),
                "used": used,
            }
        )
        if not used:
            continue
        output.append(
            SurfaceGroup(
                building_id=bid,
                role=template.role,
                surface=surface,
                fixed=template.fixed,
                moving=moving,
                fixed_normals=template.fixed_normals,
                moving_normals=moving_normals,
                block_id=block_id,
                observation_count=len(observations[(block_id, bid, surface)]),
            )
        )
    return output, {
        "roles": sorted(roles),
        "groups": len(output),
        "buildings": len({group.building_id for group in output}),
        "blocks": sorted({group.block_id for group in output}),
        "depth_stride": stride,
        "template_audit": template_audit,
        "rows": audit_rows,
        "depth_set_lock": config["input_locks"]["expected_geometric_depth_set"],
    }


def skew(vector: Sequence[float]) -> np.ndarray:
    x, y, z = map(float, vector)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def rotation_exp(omega: Sequence[float]) -> np.ndarray:
    value = np.asarray(omega, dtype=np.float64)
    angle = float(np.linalg.norm(value))
    matrix = skew(value)
    if angle < 1e-12:
        return np.eye(3) + matrix + 0.5 * matrix @ matrix
    axis_matrix = matrix / angle
    return (
        np.eye(3)
        + math.sin(angle) * axis_matrix
        + (1.0 - math.cos(angle)) * axis_matrix @ axis_matrix
    )


def transform_points_local(points: np.ndarray, transform: np.ndarray, pivot: np.ndarray) -> np.ndarray:
    local = np.asarray(points, dtype=np.float64) - pivot
    return (transform[:3, :3] @ local.T).T + transform[:3, 3] + pivot


def transform_normals(normals: np.ndarray, transform: np.ndarray) -> np.ndarray:
    return (transform[:3, :3] @ np.asarray(normals, dtype=np.float64).T).T


def pretransform_groups(
    groups: Sequence[SurfaceGroup],
    transforms_by_block: Mapping[str, np.ndarray],
    fallback_transform: np.ndarray,
    pivot: np.ndarray,
) -> list[SurfaceGroup]:
    output: list[SurfaceGroup] = []
    for group in groups:
        transform = transforms_by_block.get(group.block_id, fallback_transform)
        output.append(
            SurfaceGroup(
                building_id=group.building_id,
                role=group.role,
                surface=group.surface,
                fixed=group.fixed,
                moving=transform_points_local(group.moving, transform, pivot),
                fixed_normals=group.fixed_normals,
                moving_normals=transform_normals(group.moving_normals, transform),
                block_id=group.block_id,
                observation_count=group.observation_count,
            )
        )
    return output


def evaluate_transform_bundle(
    groups: Sequence[SurfaceGroup],
    global_transform: np.ndarray,
    block_transforms: Mapping[str, np.ndarray],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pivot = np.asarray(
        config["input_locks"]["rotation_pivot_global_m"], dtype=np.float64
    )
    transformed = pretransform_groups(
        groups, block_transforms, global_transform, pivot
    )
    return evaluate_groups(transformed, np.eye(4), config)


def compose_left_increment(
    transform: np.ndarray, omega: np.ndarray, translation: np.ndarray
) -> np.ndarray:
    increment = np.eye(4)
    increment[:3, :3] = rotation_exp(omega)
    increment[:3, 3] = np.asarray(translation, dtype=np.float64)
    return increment @ transform


def rotation_angle_deg(rotation: np.ndarray) -> float:
    cosine = float(np.clip((np.trace(rotation) - 1.0) * 0.5, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def validate_rigid_transform(transform: np.ndarray, tolerance: float = 1e-8) -> None:
    transform = np.asarray(transform, dtype=np.float64)
    if transform.shape != (4, 4):
        raise CoregError("transform must be 4x4")
    if not np.allclose(transform[3], [0, 0, 0, 1], atol=tolerance):
        raise CoregError("invalid homogeneous transform bottom row")
    rotation = transform[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=tolerance):
        raise CoregError("rotation is not orthonormal")
    if not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=tolerance):
        raise CoregError("rotation determinant is not +1")


def _collect_forward_system(
    groups: Sequence[SurfaceGroup],
    transform: np.ndarray,
    pivot: np.ndarray,
    maximum_distance: float,
    huber_delta: float,
    lever_arm: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    from scipy.spatial import cKDTree

    rows: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    weights: list[np.ndarray] = []
    group_counts: dict[str, int] = {}
    for group in groups:
        moved = transform_points_local(group.moving, transform, pivot)
        tree = cKDTree(group.fixed)
        distances, indices = tree.query(moved, k=1)
        matched = distances <= float(maximum_distance)
        if not np.any(matched):
            continue
        moved_matched = moved[matched]
        fixed_matched = group.fixed[indices[matched]]
        normals = group.fixed_normals[indices[matched]]
        residual = np.einsum(
            "ij,ij->i", normals, moved_matched - fixed_matched
        )
        local = moved_matched - pivot
        rotational = np.cross(local, normals)
        design = np.column_stack([rotational / lever_arm, normals])
        absolute = np.abs(residual)
        robust = np.ones_like(absolute)
        tail = absolute > float(huber_delta)
        robust[tail] = float(huber_delta) / np.maximum(absolute[tail], 1e-12)
        group_key = f"{group.building_id}:{group.surface}"
        balance = np.full(
            len(residual), 1.0 / max(1, len(residual)), dtype=np.float64
        )
        rows.append(design)
        residuals.append(residual)
        weights.append(robust * balance)
        group_counts[group_key] = len(residual)
    if not rows:
        raise CoregError("no correspondences for global registration")
    design = np.vstack(rows)
    residual = np.concatenate(residuals)
    weight = np.concatenate(weights)
    return design, residual, weight, {
        "correspondences": int(len(residual)),
        "group_correspondences": group_counts,
    }


def normalized_design_diagnostics(
    design: np.ndarray, weight: np.ndarray, tolerance: float = 1e-10
) -> tuple[int, float, np.ndarray]:
    weighted = np.asarray(design) * np.sqrt(np.asarray(weight))[:, None]
    singular = np.linalg.svd(weighted, compute_uv=False)
    if singular.size == 0:
        return 0, float("inf"), singular
    threshold = max(weighted.shape) * singular[0] * tolerance
    rank = int(np.sum(singular > threshold))
    condition = (
        float(singular[0] / singular[-1])
        if rank == design.shape[1] and singular[-1] > 0
        else float("inf")
    )
    return rank, condition, singular


def fit_global_transform(
    groups: Sequence[SurfaceGroup], config: Mapping[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    registration = config["global_registration"]
    pivot = np.asarray(
        config["input_locks"]["rotation_pivot_global_m"], dtype=np.float64
    )
    source = np.vstack([group.moving for group in groups])
    lever_arm = float(
        math.sqrt(np.mean(np.sum((source - pivot) ** 2, axis=1)))
    )
    if not math.isfinite(lever_arm) or lever_arm <= 1.0:
        raise CoregError(f"invalid locked-geometry lever arm: {lever_arm}")
    transform = np.eye(4)
    trace: list[dict[str, Any]] = []
    final_design = np.empty((0, 6))
    final_weight = np.empty(0)
    final_level_converged = False
    for level, (distance, delta, iterations) in enumerate(
        zip(
            registration["correspondence_distance_m"],
            registration["huber_delta_m"],
            registration["maximum_iterations"],
        ),
        1,
    ):
        level_converged = False
        for iteration in range(1, int(iterations) + 1):
            design, residual, weight, support = _collect_forward_system(
                groups,
                transform,
                pivot,
                float(distance),
                float(delta),
                lever_arm,
            )
            if len(residual) < int(registration["minimum_correspondences"]):
                raise CoregError(
                    f"only {len(residual)} correspondences at level {level}"
                )
            rank, condition, singular = normalized_design_diagnostics(design, weight)
            sqrt_weight = np.sqrt(weight)
            solution, *_ = np.linalg.lstsq(
                design * sqrt_weight[:, None],
                -residual * sqrt_weight,
                rcond=None,
            )
            omega = solution[:3] / lever_arm
            translation = solution[3:]
            transform = compose_left_increment(transform, omega, translation)
            validate_rigid_transform(transform, tolerance=1e-6)
            trace.append(
                {
                    "level": level,
                    "iteration": iteration,
                    "maximum_distance_m": float(distance),
                    "huber_delta_m": float(delta),
                    "correspondences": support["correspondences"],
                    "rank": rank,
                    "normalized_condition": condition,
                    "median_abs_point_to_plane_m": float(
                        np.median(np.abs(residual))
                    ),
                    "p90_abs_point_to_plane_m": float(
                        np.quantile(np.abs(residual), 0.9)
                    ),
                    "increment_rotation_rad": float(np.linalg.norm(omega)),
                    "increment_translation_m": float(np.linalg.norm(translation)),
                    "singular_values": singular.tolist(),
                }
            )
            final_design, final_weight = design, weight
            if (
                np.linalg.norm(omega)
                <= float(registration["convergence_rotation_rad"])
                and np.linalg.norm(translation)
                <= float(registration["convergence_translation_m"])
            ):
                level_converged = True
                break
        if level == len(registration["correspondence_distance_m"]):
            final_level_converged = level_converged
    final_design, _, final_weight, final_support = _collect_forward_system(
        groups,
        transform,
        pivot,
        float(registration["correspondence_distance_m"][-1]),
        float(registration["huber_delta_m"][-1]),
        lever_arm,
    )
    final_rank, final_condition, final_singular = normalized_design_diagnostics(
        final_design, final_weight
    )
    diagnostics = {
        "lever_arm_m": lever_arm,
        "final_rank": final_rank,
        "final_normalized_condition": final_condition,
        "final_singular_values": final_singular.tolist(),
        "final_correspondences": final_support["correspondences"],
        "final_level_converged": final_level_converged,
        "trace": trace,
    }
    if (
        bool(registration["final_level_convergence_required"])
        and not final_level_converged
    ):
        diagnostics["candidate_valid"] = False
        diagnostics["invalid_reason"] = "final_level_not_converged"
        return transform, diagnostics
    if final_rank != int(registration["required_normalized_design_rank"]):
        diagnostics["candidate_valid"] = False
        diagnostics["invalid_reason"] = "rank_deficient"
        return transform, diagnostics
    if final_condition > float(registration["maximum_normalized_design_condition"]):
        diagnostics["candidate_valid"] = False
        diagnostics["invalid_reason"] = "condition_exceeds_lock"
        return transform, diagnostics
    rotation_deg = rotation_angle_deg(transform[:3, :3])
    translation_m = float(np.linalg.norm(transform[:3, 3]))
    control_displacements = np.linalg.norm(
        transform_points_local(source, transform, pivot) - source, axis=1
    )
    maximum_displacement = float(np.max(control_displacements))
    diagnostics.update(
        {
            "rotation_deg": rotation_deg,
            "pivot_translation_m": translation_m,
            "maximum_control_displacement_m": maximum_displacement,
        }
    )
    bounds_pass = (
        rotation_deg <= float(registration["maximum_rotation_deg"])
        and translation_m <= float(registration["maximum_pivot_translation_m"])
        and maximum_displacement
        <= float(registration["maximum_control_displacement_m"])
    )
    diagnostics["candidate_valid"] = bool(bounds_pass)
    diagnostics["invalid_reason"] = "" if bounds_pass else "micro_coreg_bounds_exceeded"
    return transform, diagnostics


def evaluate_groups(
    groups: Sequence[SurfaceGroup],
    transform: np.ndarray,
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from scipy.spatial import cKDTree

    pivot = np.asarray(
        config["input_locks"]["rotation_pivot_global_m"], dtype=np.float64
    )
    radius = float(config["global_registration"]["correspondence_distance_m"][-1])
    per_group: list[dict[str, Any]] = []
    internal: list[dict[str, Any]] = []
    for group in groups:
        moved = transform_points_local(group.moving, transform, pivot)
        moved_normals = transform_normals(group.moving_normals, transform)

        fixed_tree = cKDTree(group.fixed)
        forward_distance, forward_index = fixed_tree.query(moved, k=1)
        forward_match = forward_distance <= radius
        forward_signed = np.full(len(moved), radius, dtype=np.float64)
        if np.any(forward_match):
            normals = group.fixed_normals[forward_index[forward_match]]
            forward_signed[forward_match] = np.einsum(
                "ij,ij->i",
                normals,
                moved[forward_match] - group.fixed[forward_index[forward_match]],
            )

        moving_tree = cKDTree(moved)
        reverse_distance, reverse_index = moving_tree.query(group.fixed, k=1)
        reverse_match = reverse_distance <= radius
        reverse_signed = np.full(len(group.fixed), radius, dtype=np.float64)
        if np.any(reverse_match):
            normals = moved_normals[reverse_index[reverse_match]]
            reverse_signed[reverse_match] = np.einsum(
                "ij,ij->i",
                normals,
                moved[reverse_index[reverse_match]] - group.fixed[reverse_match],
            )

        absolute = np.concatenate(
            [np.abs(forward_signed), np.abs(reverse_signed)]
        )
        matched_signed = np.concatenate(
            [forward_signed[forward_match], reverse_signed[reverse_match]]
        )
        support_forward = float(np.mean(forward_match))
        support_reverse = float(np.mean(reverse_match))
        public = {
            "building_id": group.building_id,
            "role": group.role,
            "surface": group.surface,
            "fixed_points": len(group.fixed),
            "moving_points": len(group.moving),
            "symmetric_median_m": float(np.median(absolute)),
            "all_support_p90_m": float(np.quantile(absolute, 0.9)),
            "forward_matched_support": support_forward,
            "reverse_matched_support": support_reverse,
            "bidirectional_matched_support": min(
                support_forward, support_reverse
            ),
            "signed_bias_m": (
                float(np.median(matched_signed)) if len(matched_signed) else radius
            ),
            "correspondence_radius_m": radius,
            "unmatched_censored": True,
        }
        per_group.append(public)
        internal.append(
            {
                "public": public,
                "absolute": absolute,
                "matched_signed": matched_signed,
                "forward_matches": int(np.sum(forward_match)),
                "forward_total": int(len(forward_match)),
                "reverse_matches": int(np.sum(reverse_match)),
                "reverse_total": int(len(reverse_match)),
            }
        )
    by_building: dict[str, list[dict[str, Any]]] = {}
    for row in internal:
        by_building.setdefault(row["public"]["building_id"], []).append(row)
    building_rows: list[dict[str, Any]] = []
    gate = config["selection_gate"]
    for bid, rows in sorted(by_building.items()):
        pooled_absolute = np.concatenate([row["absolute"] for row in rows])
        pooled_signed_parts = [
            row["matched_signed"] for row in rows if len(row["matched_signed"])
        ]
        pooled_signed = (
            np.concatenate(pooled_signed_parts)
            if pooled_signed_parts
            else np.empty(0, dtype=np.float64)
        )
        median = float(np.median(pooled_absolute))
        p90 = float(np.quantile(pooled_absolute, 0.9))
        forward_support = sum(row["forward_matches"] for row in rows) / max(
            1, sum(row["forward_total"] for row in rows)
        )
        reverse_support = sum(row["reverse_matches"] for row in rows) / max(
            1, sum(row["reverse_total"] for row in rows)
        )
        support = float(min(forward_support, reverse_support))
        bias = (
            float(abs(np.median(pooled_signed)))
            if len(pooled_signed)
            else radius
        )
        passed = (
            median <= float(gate["absolute_symmetric_median_max_m"])
            and p90 <= float(gate["absolute_all_support_p90_max_m"])
            and support >= float(gate["minimum_bidirectional_matched_support"])
            and bias <= float(gate["absolute_signed_bias_max_m"])
        )
        building_rows.append(
            {
                "building_id": bid,
                "role": rows[0]["public"]["role"],
                "surface_count": len(rows),
                "symmetric_median_m": median,
                "all_support_p90_m": p90,
                "bidirectional_matched_support": support,
                "absolute_signed_bias_m": bias,
                "absolute_criteria_pass": passed,
            }
        )
    summary = {
        "building_count": len(building_rows),
        "all_buildings_pass": all(
            bool(row["absolute_criteria_pass"]) for row in building_rows
        ),
        "building_balanced_median_m": float(
            np.median([row["symmetric_median_m"] for row in building_rows])
        ),
        "building_balanced_p90_m": float(
            np.median([row["all_support_p90_m"] for row in building_rows])
        ),
        "minimum_building_support": float(
            np.min([row["bidirectional_matched_support"] for row in building_rows])
        ),
        "maximum_building_absolute_bias_m": float(
            np.max([row["absolute_signed_bias_m"] for row in building_rows])
        ),
        "per_group": per_group,
    }
    return building_rows, summary


def _serialize_matrix(matrix: np.ndarray) -> list[list[float]]:
    return [[float(value) for value in row] for row in np.asarray(matrix)]


def _write_measurement_table(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "building_id",
        "role",
        "surface_count",
        "symmetric_median_m",
        "all_support_p90_m",
        "bidirectional_matched_support",
        "absolute_signed_bias_m",
        "absolute_criteria_pass",
    ]
    formatted: list[dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        for field in (
            "symmetric_median_m",
            "all_support_p90_m",
            "bidirectional_matched_support",
            "absolute_signed_bias_m",
        ):
            current[field] = f"{float(current[field]):.9f}"
        current["absolute_criteria_pass"] = str(
            bool(current["absolute_criteria_pass"])
        ).lower()
        formatted.append(current)
    _write_csv(path, fields, formatted)


def render_residual_comparison(
    identity_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    output: Path,
    title: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    candidate = {row["building_id"]: row for row in candidate_rows}
    ordered = sorted(identity_rows, key=lambda row: row["building_id"])
    x = np.arange(len(ordered))
    identity_values = [float(row["symmetric_median_m"]) for row in ordered]
    candidate_values = [
        float(candidate[row["building_id"]]["symmetric_median_m"]) for row in ordered
    ]
    fig, ax = plt.subplots(figsize=(max(8, len(ordered) * 0.5), 5), constrained_layout=True)
    ax.plot(x, identity_values, "o-", label="identity", color="#455a64")
    ax.plot(x, candidate_values, "o-", label="global candidate", color="#1976d2")
    ax.axhline(0.15, color="#c62828", linestyle="--", linewidth=1, label="0.15 m")
    ax.set_xticks(x)
    ax.set_xticklabels(
        [row["building_id"].replace("DEBY_LOD2_", "") for row in ordered],
        rotation=60,
        ha="right",
    )
    ax.set_ylabel("symmetric point-to-plane median (m)")
    ax.set_title(title)
    ax.legend()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def render_selected_residuals(
    rows: Sequence[Mapping[str, Any]], output: Path, title: str
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ordered = sorted(rows, key=lambda row: row["building_id"])
    x = np.arange(len(ordered))
    values = [float(row["symmetric_median_m"]) for row in ordered]
    fig, ax = plt.subplots(
        figsize=(max(8, len(ordered) * 0.5), 5), constrained_layout=True
    )
    ax.plot(x, values, "o-", label="frozen transform", color="#2e7d32")
    ax.axhline(0.15, color="#c62828", linestyle="--", linewidth=1, label="0.15 m")
    ax.set_xticks(x)
    ax.set_xticklabels(
        [row["building_id"].replace("DEBY_LOD2_", "") for row in ordered],
        rotation=60,
        ha="right",
    )
    ax.set_ylabel("symmetric point-to-plane median (m)")
    ax.set_title(title)
    ax.legend()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def fit_command(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = verify_committed_implementation(config)
    verify_input_hashes(config)
    verify_generated_locks(config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    runtime.mkdir(parents=True, exist_ok=True)
    fit_json = runtime / "fit_candidate.json"
    if fit_json.exists() or (runtime / "fit_open.json").exists():
        raise CoregError("fit stage is exact-once and already has a receipt")
    stage_binding = current_stage_binding(config, provenance)
    stage_open = open_exact_stage(runtime, "fit", stage_binding)
    groups, sampling_audit = build_surface_groups(config, {"fit"})
    candidate, diagnostics = fit_global_transform(groups, config)
    identity_rows, identity_summary = evaluate_groups(groups, np.eye(4), config)
    candidate_rows, candidate_summary = evaluate_groups(groups, candidate, config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    runtime.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "jointbuildgs.fusion_w1.coreg_fit_candidate.v1",
        "status": "CANDIDATE_ESTIMATED",
        "fit_roles_opened": ["fit"],
        "trigger_or_check_opened": False,
        "candidate_photo_to_als_global_pivot_matrix": _serialize_matrix(candidate),
        "candidate_transform_sha256": canonical_json_sha(_serialize_matrix(candidate)),
        "diagnostics": diagnostics,
        "identity_fit_summary": identity_summary,
        "candidate_fit_summary": candidate_summary,
        "sampling_audit": sampling_audit,
        "provenance": provenance,
        "input_sha256": verify_input_hashes(config),
        "stage_binding": stage_binding,
        "stage_open_receipt_sha256": sha256_file(stage_open),
    }
    write_json(fit_json, payload, exclusive=True)
    _write_measurement_table(runtime / "fit_identity.csv", identity_rows)
    _write_measurement_table(runtime / "fit_candidate.csv", candidate_rows)
    render_residual_comparison(
        identity_rows,
        candidate_rows,
        runtime / "fit_residual_comparison.png",
        "Global SE(3) fit controls (selection not performed on fit)",
    )
    return payload


def verify_generated_locks(config: Mapping[str, Any]) -> dict[str, str]:
    generated = config["input_locks"]["generated_lock_sha256"]
    mapping = {
        "splits_csv": repo_path(config["inputs"]["splits_csv"]),
        "camera_blocks_csv": repo_path(config["inputs"]["camera_blocks_csv"]),
        "prereg_manifest": repo_path(
            config.get(
                "_prereg_manifest_path",
                Path(config["inputs"]["splits_csv"]).parent
                / "w1_coreg_prereg_manifest.json",
            )
        ),
    }
    observed: dict[str, str] = {}
    for key, path in mapping.items():
        expected = generated[key]
        if expected == "PENDING_GENERATION":
            raise CoregError(f"generated lock remains pending: {key}")
        actual = sha256_file(path)
        if actual != expected:
            raise CoregError(f"generated lock mismatch for {key}: {actual} != {expected}")
        observed[key] = actual
    return observed


def current_stage_binding(
    config: Mapping[str, Any], provenance: Mapping[str, Any]
) -> dict[str, Any]:
    runtime = repo_path(config["inputs"]["runtime_dir"])
    als_receipt = runtime / "als_materialization_receipt.json"
    if not als_receipt.is_file():
        raise CoregError("ALS materialization receipt missing from stage binding")
    receipt = json.loads(als_receipt.read_text())
    als_output = repo_path(receipt["output"])
    if not als_output.is_file() or sha256_file(als_output) != receipt["output_sha256"]:
        raise CoregError("ALS materialization output differs from receipt")
    return {
        "head": provenance["head"],
        "branch": provenance["branch"],
        "config_sha256": sha256_file(DEFAULT_CONFIG),
        "input_sha256": verify_input_hashes(config),
        "generated_lock_sha256": verify_generated_locks(config),
        "als_materialization_receipt_sha256": sha256_file(als_receipt),
        "als_materialization_output_sha256": receipt["output_sha256"],
        "source_als_sha256": receipt["source_sha256"],
    }


def verify_parent_binding(
    parent: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    label: str,
) -> None:
    recorded = parent.get("stage_binding")
    if recorded != current:
        raise CoregError(f"{label} stage binding differs from current immutable run")


def verify_stage_open_parent(
    runtime: Path,
    stage: str,
    parent_name: str,
    parent_path: Path,
) -> None:
    open_path = runtime / f"{stage}_open.json"
    if not open_path.is_file():
        raise CoregError(f"{stage} stage-open receipt is missing")
    opened = json.loads(open_path.read_text())
    parents = opened.get("parent_receipt_sha256") or {}
    if parents.get(parent_name) != sha256_file(parent_path):
        raise CoregError(
            f"{stage} stage-open parent hash differs: {parent_name}"
        )


def verify_frozen_selection_chain(runtime: Path, frozen: Mapping[str, Any]) -> None:
    global_selection_path = runtime / "global_selection.json"
    fit_path = runtime / "fit_candidate.json"
    if not global_selection_path.is_file() or not fit_path.is_file():
        raise CoregError("global selection parent chain is incomplete")
    global_selection = json.loads(global_selection_path.read_text())
    if global_selection.get("fit_candidate_sha256") != sha256_file(fit_path):
        raise CoregError("global selection/fit candidate hash mismatch")
    verify_stage_open_parent(
        runtime, "select", "fit_candidate", fit_path
    )
    blocks = frozen.get("block_transforms") or {}
    if not blocks:
        expected = dict(global_selection)
        expected["schema"] = "jointbuildgs.fusion_w1.coreg_frozen_transform.v1"
        expected["global_selection_receipt_sha256"] = sha256_file(
            global_selection_path
        )
        expected["block_transforms"] = {}
        if dict(frozen) != expected:
            raise CoregError("frozen global transform differs from selection receipt")
        return

    block_fit_path = runtime / "block_fit_candidates.json"
    block_selection_path = runtime / "block_selection.json"
    if not block_fit_path.is_file() or not block_selection_path.is_file():
        raise CoregError("conditional block parent chain is incomplete")
    block_selection = json.loads(block_selection_path.read_text())
    if (
        block_selection.get("global_selection_receipt_sha256")
        != sha256_file(global_selection_path)
        or block_selection.get("block_fit_receipt_sha256")
        != sha256_file(block_fit_path)
    ):
        raise CoregError("conditional block selection parent hash mismatch")
    verify_stage_open_parent(
        runtime, "fit_blocks", "global_selection", global_selection_path
    )
    verify_stage_open_parent(
        runtime, "select_blocks", "global_selection", global_selection_path
    )
    verify_stage_open_parent(
        runtime, "select_blocks", "block_fit_candidates", block_fit_path
    )
    expected = dict(block_selection)
    expected["schema"] = "jointbuildgs.fusion_w1.coreg_frozen_transform.v1"
    expected["block_selection_receipt_sha256"] = sha256_file(
        block_selection_path
    )
    if dict(frozen) != expected:
        raise CoregError("frozen block transform differs from selection receipt")


def open_exact_stage(
    runtime: Path,
    stage: str,
    stage_binding: Mapping[str, Any],
    parents: Mapping[str, str] | None = None,
) -> Path:
    path = runtime / f"{stage}_open.json"
    payload = {
        "schema": "jointbuildgs.fusion_w1.coreg_stage_open.v1",
        "stage": stage,
        "status": "OPENED_EXACT_ONCE",
        "stage_binding": stage_binding,
        "parent_receipt_sha256": dict(parents or {}),
        "learning_runs_started": 0,
    }
    write_json(path, payload, exclusive=True)
    return path


def select_command(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = verify_committed_implementation(config)
    verify_input_hashes(config)
    verify_generated_locks(config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    fit_path = runtime / "fit_candidate.json"
    selection_path = runtime / "global_selection.json"
    if (
        selection_path.exists()
        or (runtime / "select_open.json").exists()
        or (runtime / "frozen_transform.json").exists()
    ):
        raise CoregError("trigger selection stage is exact-once and already opened")
    if not fit_path.is_file():
        raise CoregError("fit candidate is missing")
    fit_payload = json.loads(fit_path.read_text())
    if (
        fit_payload.get("schema")
        != "jointbuildgs.fusion_w1.coreg_fit_candidate.v1"
        or fit_payload.get("status") != "CANDIDATE_ESTIMATED"
    ):
        raise CoregError("fit candidate schema/status is invalid")
    if fit_payload.get("trigger_or_check_opened") is not False:
        raise CoregError("fit payload indicates holdout access")
    stage_binding = current_stage_binding(config, provenance)
    verify_parent_binding(
        fit_payload, stage_binding, label="fit-to-trigger"
    )
    stage_open = open_exact_stage(
        runtime,
        "select",
        stage_binding,
        {"fit_candidate": sha256_file(fit_path)},
    )
    candidate = np.asarray(
        fit_payload["candidate_photo_to_als_global_pivot_matrix"], dtype=np.float64
    )
    validate_rigid_transform(candidate, tolerance=1e-6)
    if canonical_json_sha(_serialize_matrix(candidate)) != fit_payload[
        "candidate_transform_sha256"
    ]:
        raise CoregError("fit candidate transform hash mismatch")
    groups, sampling_audit = build_surface_groups(config, {"trigger"})
    identity_rows, identity_summary = evaluate_groups(groups, np.eye(4), config)
    candidate_rows, candidate_summary = evaluate_groups(groups, candidate, config)
    gate = config["selection_gate"]
    identity_pass = bool(identity_summary["all_buildings_pass"])
    candidate_valid = bool(fit_payload["diagnostics"]["candidate_valid"])
    improvements = {
        row["building_id"]: float(row["symmetric_median_m"])
        - float(
            next(
                value["symmetric_median_m"]
                for value in candidate_rows
                if value["building_id"] == row["building_id"]
            )
        )
        for row in identity_rows
    }
    median_identity = float(identity_summary["building_balanced_median_m"])
    median_candidate = float(candidate_summary["building_balanced_median_m"])
    absolute_improvement = median_identity - median_candidate
    relative_improvement = absolute_improvement / max(median_identity, 1e-12)
    maximum_worsening = max(-value for value in improvements.values())
    candidate_adoption_pass = (
        candidate_valid
        and bool(candidate_summary["all_buildings_pass"])
        and absolute_improvement
        >= float(gate["candidate_minimum_median_improvement_m"])
        and relative_improvement
        >= float(gate["candidate_minimum_relative_improvement"])
        and maximum_worsening
        <= float(gate["maximum_per_building_worsening_m"])
    )
    block_base_uses_candidate = (
        candidate_valid
        and absolute_improvement > 0.0
        and maximum_worsening
        <= float(gate["maximum_per_building_worsening_m"])
    )
    block_base = candidate if block_base_uses_candidate else np.eye(4)
    block_base_choice = (
        "global_candidate" if block_base_uses_candidate else "identity"
    )
    if identity_pass:
        status = "FROZEN"
        choice = "identity"
        selected = np.eye(4)
        reason = "identity_meets_locked_absolute_trigger_criteria"
    elif candidate_adoption_pass:
        status = "FROZEN"
        choice = "global_se3"
        selected = candidate
        reason = "global_candidate_meets_all_locked_trigger_adoption_criteria"
    else:
        status = "BLOCK_REQUIRED"
        choice = "none"
        selected = np.eye(4)
        reason = (
            "identity_and_global_candidate_do_not_satisfy_trigger_contract;"
            "conditional_predeclared_capture_block_stage_required"
        )
    selected_matrix = _serialize_matrix(selected)
    selected_bundle = {"global": selected_matrix, "blocks": {}}
    payload = {
        "schema": "jointbuildgs.fusion_w1.coreg_frozen_transform.v1",
        "status": status,
        "choice": choice,
        "reason": reason,
        "selected_photo_to_als_global_pivot_matrix": selected_matrix,
        "selected_transform_sha256": canonical_json_sha(selected_bundle),
        "block_base_choice": block_base_choice,
        "block_base_photo_to_als_global_pivot_matrix": _serialize_matrix(block_base),
        "block_base_transform_sha256": canonical_json_sha(
            _serialize_matrix(block_base)
        ),
        "fit_candidate_sha256": sha256_file(fit_path),
        "identity_trigger_summary": identity_summary,
        "candidate_trigger_summary": candidate_summary,
        "candidate_valid": candidate_valid,
        "candidate_adoption": {
            "pass": candidate_adoption_pass,
            "absolute_median_improvement_m": absolute_improvement,
            "relative_median_improvement": relative_improvement,
            "maximum_building_worsening_m": maximum_worsening,
            "per_building_improvement_m": improvements,
        },
        "sampling_audit": sampling_audit,
        "roles_opened": ["fit", "trigger"],
        "check_opened": False,
        "fallback_after_check_forbidden": True,
        "stage_binding": stage_binding,
        "stage_open_receipt_sha256": sha256_file(stage_open),
    }
    write_json(selection_path, payload, exclusive=True)
    if status == "FROZEN":
        frozen_payload = dict(payload)
        frozen_payload["schema"] = "jointbuildgs.fusion_w1.coreg_frozen_transform.v1"
        frozen_payload["global_selection_receipt_sha256"] = sha256_file(selection_path)
        frozen_payload["block_transforms"] = {}
        write_json(runtime / "frozen_transform.json", frozen_payload, exclusive=True)
    _write_measurement_table(runtime / "trigger_identity.csv", identity_rows)
    _write_measurement_table(runtime / "trigger_candidate.csv", candidate_rows)
    render_residual_comparison(
        identity_rows,
        candidate_rows,
        runtime / "trigger_residual_comparison.png",
        f"Trigger controls — frozen choice: {choice}",
    )
    return payload


def _groups_with_both_surfaces(
    groups: Sequence[SurfaceGroup],
) -> list[SurfaceGroup]:
    surfaces: dict[tuple[str, str], set[str]] = {}
    for group in groups:
        surfaces.setdefault((group.block_id, group.building_id), set()).add(
            group.surface
        )
    valid = {
        key for key, values in surfaces.items() if values == {"roof", "ground"}
    }
    return [
        group for group in groups if (group.block_id, group.building_id) in valid
    ]


def fit_blocks_command(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = verify_committed_implementation(config)
    verify_input_hashes(config)
    verify_generated_locks(config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    frozen_path = runtime / "frozen_transform.json"
    if frozen_path.is_file():
        return {
            "schema": "jointbuildgs.fusion_w1.coreg_block_fit_skip.v1",
            "status": "SKIPPED_GLOBAL_TRANSFORM_ALREADY_FROZEN",
        }
    global_selection_path = runtime / "global_selection.json"
    output_path = runtime / "block_fit_candidates.json"
    if output_path.exists() or (runtime / "fit_blocks_open.json").exists():
        raise CoregError("conditional block fit is exact-once and already opened")
    if not global_selection_path.is_file():
        raise CoregError("global trigger selection receipt is missing")
    global_selection = json.loads(global_selection_path.read_text())
    if global_selection.get("status") != "BLOCK_REQUIRED":
        raise CoregError("conditional block fit opened without BLOCK_REQUIRED")
    stage_binding = current_stage_binding(config, provenance)
    verify_parent_binding(
        global_selection, stage_binding, label="global-selection-to-block-fit"
    )
    stage_open = open_exact_stage(
        runtime,
        "fit_blocks",
        stage_binding,
        {"global_selection": sha256_file(global_selection_path)},
    )
    base = np.asarray(
        global_selection["block_base_photo_to_als_global_pivot_matrix"],
        dtype=np.float64,
    )
    if canonical_json_sha(_serialize_matrix(base)) != global_selection[
        "block_base_transform_sha256"
    ]:
        raise CoregError("conditional block base transform hash mismatch")
    validate_rigid_transform(base, tolerance=1e-6)

    groups, sampling_audit = build_block_surface_groups(config, {"fit"})
    groups = _groups_with_both_surfaces(groups)
    pivot = np.asarray(
        config["input_locks"]["rotation_pivot_global_m"], dtype=np.float64
    )
    block_cfg = config["conditional_blocks"]
    candidates: dict[str, Any] = {}
    for block_id in sorted({row["block_id"] for row in _read_csv(
        config["inputs"]["camera_blocks_csv"]
    )}):
        current = [group for group in groups if group.block_id == block_id]
        buildings = sorted({group.building_id for group in current})
        observations = sum(group.observation_count for group in current)
        record: dict[str, Any] = {
            "block_id": block_id,
            "fit_buildings": buildings,
            "fit_building_count": len(buildings),
            "fit_observations": observations,
        }
        if (
            len(buildings) < int(block_cfg["minimum_fit_buildings"])
            or observations < int(block_cfg["minimum_observations"])
        ):
            record.update(
                {
                    "candidate_valid": False,
                    "invalid_reason": "insufficient_fit_block_support",
                }
            )
            candidates[block_id] = record
            continue
        baseline_groups = pretransform_groups(current, {}, base, pivot)
        delta, diagnostics = fit_global_transform(baseline_groups, config)
        total = delta @ base
        validate_rigid_transform(delta, tolerance=1e-6)
        validate_rigid_transform(total, tolerance=1e-6)
        source_after_base = np.vstack(
            [group.moving for group in baseline_groups]
        )
        displacement = np.linalg.norm(
            transform_points_local(source_after_base, delta, pivot)
            - source_after_base,
            axis=1,
        )
        delta_rotation = rotation_angle_deg(delta[:3, :3])
        delta_translation = float(np.linalg.norm(delta[:3, 3]))
        maximum_displacement = float(np.max(displacement))
        block_bounds_pass = (
            delta_rotation <= float(block_cfg["maximum_rotation_deg"])
            and delta_translation <= float(block_cfg["maximum_translation_m"])
            and maximum_displacement
            <= float(block_cfg["maximum_control_displacement_m"])
        )
        record.update(
            {
                "delta_matrix": _serialize_matrix(delta),
                "total_photo_to_als_matrix": _serialize_matrix(total),
                "delta_transform_sha256": canonical_json_sha(
                    _serialize_matrix(delta)
                ),
                "total_transform_sha256": canonical_json_sha(
                    _serialize_matrix(total)
                ),
                "diagnostics": diagnostics,
                "delta_rotation_deg": delta_rotation,
                "delta_translation_m": delta_translation,
                "maximum_control_displacement_m": maximum_displacement,
                "block_bounds_pass": block_bounds_pass,
                "candidate_valid": bool(
                    diagnostics["candidate_valid"] and block_bounds_pass
                ),
                "invalid_reason": (
                    ""
                    if diagnostics["candidate_valid"] and block_bounds_pass
                    else (
                        diagnostics.get("invalid_reason")
                        or "conditional_block_bounds_exceeded"
                    )
                ),
            }
        )
        candidates[block_id] = record
    payload = {
        "schema": "jointbuildgs.fusion_w1.coreg_block_fit_candidates.v1",
        "status": "BLOCK_CANDIDATES_ESTIMATED",
        "global_selection_receipt_sha256": sha256_file(global_selection_path),
        "block_base_choice": global_selection["block_base_choice"],
        "block_base_photo_to_als_global_pivot_matrix": _serialize_matrix(base),
        "block_base_transform_sha256": global_selection[
            "block_base_transform_sha256"
        ],
        "candidates": candidates,
        "sampling_audit": sampling_audit,
        "roles_opened": ["fit"],
        "trigger_or_check_opened": False,
        "stage_binding": stage_binding,
        "stage_open_receipt_sha256": sha256_file(stage_open),
    }
    write_json(output_path, payload, exclusive=True)
    return payload


def _building_improvements(
    baseline_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    candidate = {row["building_id"]: row for row in candidate_rows}
    return {
        row["building_id"]: float(row["symmetric_median_m"])
        - float(candidate[row["building_id"]]["symmetric_median_m"])
        for row in baseline_rows
    }


def select_blocks_command(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = verify_committed_implementation(config)
    verify_input_hashes(config)
    verify_generated_locks(config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    frozen_path = runtime / "frozen_transform.json"
    if frozen_path.is_file():
        return {
            "schema": "jointbuildgs.fusion_w1.coreg_block_select_skip.v1",
            "status": "SKIPPED_GLOBAL_TRANSFORM_ALREADY_FROZEN",
        }
    output_path = runtime / "block_selection.json"
    if output_path.exists() or (runtime / "select_blocks_open.json").exists():
        raise CoregError("conditional block trigger selection is exact-once")
    global_selection_path = runtime / "global_selection.json"
    block_fit_path = runtime / "block_fit_candidates.json"
    if not global_selection_path.is_file() or not block_fit_path.is_file():
        raise CoregError("conditional block parent receipts are missing")
    global_selection = json.loads(global_selection_path.read_text())
    block_fit = json.loads(block_fit_path.read_text())
    stage_binding = current_stage_binding(config, provenance)
    verify_parent_binding(
        global_selection, stage_binding, label="global-selection-to-block-trigger"
    )
    verify_parent_binding(
        block_fit, stage_binding, label="block-fit-to-block-trigger"
    )
    if block_fit.get("global_selection_receipt_sha256") != sha256_file(
        global_selection_path
    ):
        raise CoregError("block fit/global selection chain mismatch")
    if block_fit.get("trigger_or_check_opened") is not False:
        raise CoregError("block fit receipt indicates holdout access")
    stage_open = open_exact_stage(
        runtime,
        "select_blocks",
        stage_binding,
        {
            "global_selection": sha256_file(global_selection_path),
            "block_fit_candidates": sha256_file(block_fit_path),
        },
    )
    base = np.asarray(
        block_fit["block_base_photo_to_als_global_pivot_matrix"],
        dtype=np.float64,
    )
    groups, sampling_audit = build_block_surface_groups(config, {"trigger"})
    groups = _groups_with_both_surfaces(groups)
    expected_trigger = {
        row["building_id"]
        for row in _read_csv(config["inputs"]["splits_csv"])
        if row["role"] == "trigger"
    }
    observed_trigger = {group.building_id for group in groups}
    if observed_trigger != expected_trigger:
        raise CoregError(
            "block trigger lacks exact nine-building support: "
            f"missing={sorted(expected_trigger-observed_trigger)} "
            f"extra={sorted(observed_trigger-expected_trigger)}"
        )
    block_cfg = config["conditional_blocks"]
    selected_blocks: dict[str, np.ndarray] = {}
    decisions: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []
    for block_id, candidate_record in sorted(block_fit["candidates"].items()):
        current = [group for group in groups if group.block_id == block_id]
        buildings = sorted({group.building_id for group in current})
        observations = sum(group.observation_count for group in current)
        decision: dict[str, Any] = {
            "block_id": block_id,
            "trigger_buildings": buildings,
            "trigger_building_count": len(buildings),
            "trigger_observations": observations,
            "fit_candidate_valid": bool(candidate_record["candidate_valid"]),
        }
        if (
            not candidate_record["candidate_valid"]
            or len(buildings) < int(block_cfg["minimum_trigger_buildings"])
            or observations < int(block_cfg["minimum_trigger_observations"])
        ):
            decision.update(
                {
                    "adopted": False,
                    "reason": "invalid_candidate_or_insufficient_trigger_support",
                }
            )
            decisions[block_id] = decision
            continue
        candidate_total = np.asarray(
            candidate_record["total_photo_to_als_matrix"], dtype=np.float64
        )
        if canonical_json_sha(_serialize_matrix(candidate_total)) != candidate_record[
            "total_transform_sha256"
        ]:
            raise CoregError(f"block candidate hash mismatch: {block_id}")
        baseline_rows, baseline_summary = evaluate_transform_bundle(
            current, base, {}, config
        )
        candidate_rows, candidate_summary = evaluate_transform_bundle(
            current, base, {block_id: candidate_total}, config
        )
        improvements = _building_improvements(baseline_rows, candidate_rows)
        baseline_median = float(
            baseline_summary["building_balanced_median_m"]
        )
        candidate_median = float(
            candidate_summary["building_balanced_median_m"]
        )
        absolute = baseline_median - candidate_median
        relative_improvement = absolute / max(baseline_median, 1e-12)
        maximum_worsening = max(-value for value in improvements.values())
        adopted = (
            bool(candidate_summary["all_buildings_pass"])
            and absolute
            >= float(block_cfg["minimum_trigger_median_improvement_m"])
            and relative_improvement
            >= float(block_cfg["minimum_trigger_relative_improvement"])
            and maximum_worsening
            <= float(block_cfg["maximum_trigger_building_worsening_m"])
        )
        decision.update(
            {
                "adopted": adopted,
                "reason": (
                    "all_locked_block_trigger_criteria_met"
                    if adopted
                    else "block_trigger_adoption_criteria_not_met"
                ),
                "baseline_summary": baseline_summary,
                "candidate_summary": candidate_summary,
                "absolute_median_improvement_m": absolute,
                "relative_median_improvement": relative_improvement,
                "maximum_building_worsening_m": maximum_worsening,
                "per_building_improvement_m": improvements,
            }
        )
        decisions[block_id] = decision
        for row in baseline_rows:
            candidate_row = next(
                item
                for item in candidate_rows
                if item["building_id"] == row["building_id"]
            )
            comparison_rows.append(
                {
                    "block_id": block_id,
                    "building_id": row["building_id"],
                    "baseline_median_m": row["symmetric_median_m"],
                    "candidate_median_m": candidate_row["symmetric_median_m"],
                    "adopted": adopted,
                }
            )
        if adopted:
            selected_blocks[block_id] = candidate_total

    selected_rows, selected_summary = evaluate_transform_bundle(
        groups, base, selected_blocks, config
    )
    frozen_pass = bool(selected_blocks) and bool(
        selected_summary["all_buildings_pass"]
    )
    serialized_blocks = {
        block_id: _serialize_matrix(matrix)
        for block_id, matrix in sorted(selected_blocks.items())
    }
    bundle = {"global": _serialize_matrix(base), "blocks": serialized_blocks}
    payload = {
        "schema": "jointbuildgs.fusion_w1.coreg_block_selection.v1",
        "status": "FROZEN" if frozen_pass else "BLOCKED",
        "choice": (
            "global_plus_conditional_blocks" if frozen_pass else "none"
        ),
        "reason": (
            "adopted_blocks_make_all_trigger_controls_pass"
            if frozen_pass
            else "conditional_blocks_do_not_satisfy_full_trigger_contract"
        ),
        "selected_photo_to_als_global_pivot_matrix": _serialize_matrix(base),
        "block_transforms": serialized_blocks,
        "selected_transform_sha256": canonical_json_sha(bundle),
        "global_selection_receipt_sha256": sha256_file(global_selection_path),
        "block_fit_receipt_sha256": sha256_file(block_fit_path),
        "block_decisions": decisions,
        "selected_trigger_summary": selected_summary,
        "sampling_audit": sampling_audit,
        "roles_opened": ["fit", "trigger"],
        "check_opened": False,
        "fallback_after_check_forbidden": True,
        "stage_binding": stage_binding,
        "stage_open_receipt_sha256": sha256_file(stage_open),
    }
    write_json(output_path, payload, exclusive=True)
    _write_csv(
        runtime / "block_trigger_comparison.csv",
        [
            "block_id",
            "building_id",
            "baseline_median_m",
            "candidate_median_m",
            "adopted",
        ],
        comparison_rows,
    )
    if frozen_pass:
        frozen_payload = dict(payload)
        frozen_payload["schema"] = "jointbuildgs.fusion_w1.coreg_frozen_transform.v1"
        frozen_payload["block_selection_receipt_sha256"] = sha256_file(output_path)
        write_json(frozen_path, frozen_payload, exclusive=True)
        render_selected_residuals(
            selected_rows,
            runtime / "block_trigger_selected.png",
            "Conditional block trigger — frozen bundle",
        )
    return payload


def check_command(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = verify_committed_implementation(config)
    verify_input_hashes(config)
    verify_generated_locks(config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    frozen_path = runtime / "frozen_transform.json"
    check_path = runtime / "independent_check.json"
    if check_path.exists() or (runtime / "check_open.json").exists():
        raise CoregError("independent check is exact-once and already opened")
    if not frozen_path.is_file():
        raise CoregError("frozen transform is missing")
    frozen = json.loads(frozen_path.read_text())
    if (
        frozen.get("schema")
        != "jointbuildgs.fusion_w1.coreg_frozen_transform.v1"
        or frozen.get("status") != "FROZEN"
    ):
        raise CoregError(
            "global stage did not freeze a transform; conditional block stage is required"
        )
    verify_frozen_selection_chain(runtime, frozen)
    stage_binding = current_stage_binding(config, provenance)
    verify_parent_binding(
        frozen, stage_binding, label="frozen-to-independent-check"
    )
    global_selection_path = runtime / "global_selection.json"
    if not global_selection_path.is_file() or sha256_file(
        global_selection_path
    ) != frozen.get("global_selection_receipt_sha256"):
        raise CoregError("frozen/global-selection receipt chain mismatch")
    if frozen.get("block_transforms"):
        block_selection_path = runtime / "block_selection.json"
        if not block_selection_path.is_file() or sha256_file(
            block_selection_path
        ) != frozen.get("block_selection_receipt_sha256"):
            raise CoregError("frozen/block-selection receipt chain mismatch")
    matrix = np.asarray(
        frozen["selected_photo_to_als_global_pivot_matrix"], dtype=np.float64
    )
    frozen_blocks = frozen.get("block_transforms", {})
    bundle_for_hash = {
        "global": _serialize_matrix(matrix),
        "blocks": frozen_blocks,
    }
    if canonical_json_sha(bundle_for_hash) != frozen["selected_transform_sha256"]:
        raise CoregError("frozen transform hash mismatch")
    block_matrices = {
        block_id: np.asarray(value, dtype=np.float64)
        for block_id, value in frozen_blocks.items()
    }
    for block_matrix in block_matrices.values():
        validate_rigid_transform(block_matrix, tolerance=1e-6)
    stage_open = open_exact_stage(
        runtime,
        "check",
        stage_binding,
        {"frozen_transform": sha256_file(frozen_path)},
    )
    block_check_support: dict[str, int] = {}
    if block_matrices:
        groups, sampling_audit = build_block_surface_groups(config, {"check"})
        groups = _groups_with_both_surfaces(groups)
        expected_check = {
            row["building_id"]
            for row in _read_csv(config["inputs"]["splits_csv"])
            if row["role"] == "check"
        }
        observed_check = {group.building_id for group in groups}
        if observed_check != expected_check:
            raise CoregError(
                "block independent check lacks exact nine-building support: "
                f"missing={sorted(expected_check-observed_check)} "
                f"extra={sorted(observed_check-expected_check)}"
            )
        for block_id in block_matrices:
            block_check_support[block_id] = len(
                {
                    group.building_id
                    for group in groups
                    if group.block_id == block_id
                }
            )
        rows, summary = evaluate_transform_bundle(
            groups, matrix, block_matrices, config
        )
        block_support_pass = all(
            count
            >= int(
                config["conditional_blocks"][
                    "minimum_independent_check_buildings_per_adopted_block"
                ]
            )
            for count in block_check_support.values()
        )
    else:
        groups, sampling_audit = build_surface_groups(config, {"check"})
        rows, summary = evaluate_groups(groups, matrix, config)
        block_support_pass = True
    passed = bool(summary["all_buildings_pass"]) and block_support_pass
    payload = {
        "schema": "jointbuildgs.fusion_w1.coreg_independent_check.v1",
        "status": "PASSED" if passed else "BLOCKED",
        "learning_allowed": False,
        "choice": frozen["choice"],
        "selected_transform_sha256": frozen["selected_transform_sha256"],
        "frozen_receipt_sha256": sha256_file(frozen_path),
        "independent_check_summary": summary,
        "sampling_audit": sampling_audit,
        "adopted_block_independent_building_support": block_check_support,
        "adopted_block_support_pass": block_support_pass,
        "roles_opened": ["check"],
        "check_failure_fallback_used": False,
        "stage_binding": stage_binding,
        "stage_open_receipt_sha256": sha256_file(stage_open),
        "next_step": (
            "publish_derived_poses_then_core_gate_a_once"
            if passed
            else "stop_without_transform_fallback_or_retuning"
        ),
    }
    write_json(check_path, payload, exclusive=True)
    _write_measurement_table(runtime / "independent_check.csv", rows)
    render_selected_residuals(
        rows,
        runtime / "independent_check.png",
        f"Independent check — {payload['status']} ({frozen['choice']})",
    )
    return payload


def qvec_to_rotmat(qvec: Sequence[float]) -> np.ndarray:
    q = np.asarray(qvec, dtype=np.float64)
    q = q / np.linalg.norm(q)
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * w * z, 2 * x * z + 2 * w * y],
            [2 * x * y + 2 * w * z, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * w * x],
            [2 * x * z - 2 * w * y, 2 * y * z + 2 * w * x, 1 - 2 * x * x - 2 * y * y],
        ],
        dtype=np.float64,
    )


def rotmat_to_qvec(rotation: np.ndarray) -> np.ndarray:
    rotation = np.asarray(rotation, dtype=np.float64)
    validate = np.eye(4)
    validate[:3, :3] = rotation
    validate_rigid_transform(validate, tolerance=1e-6)
    k = np.array(
        [
            [
                rotation[0, 0] - rotation[1, 1] - rotation[2, 2],
                rotation[0, 1] + rotation[1, 0],
                rotation[0, 2] + rotation[2, 0],
                rotation[2, 1] - rotation[1, 2],
            ],
            [
                rotation[0, 1] + rotation[1, 0],
                rotation[1, 1] - rotation[0, 0] - rotation[2, 2],
                rotation[1, 2] + rotation[2, 1],
                rotation[0, 2] - rotation[2, 0],
            ],
            [
                rotation[0, 2] + rotation[2, 0],
                rotation[1, 2] + rotation[2, 1],
                rotation[2, 2] - rotation[0, 0] - rotation[1, 1],
                rotation[1, 0] - rotation[0, 1],
            ],
            [
                rotation[2, 1] - rotation[1, 2],
                rotation[0, 2] - rotation[2, 0],
                rotation[1, 0] - rotation[0, 1],
                rotation[0, 0] + rotation[1, 1] + rotation[2, 2],
            ],
        ]
    ) / 3.0
    values, vectors = np.linalg.eigh(k)
    q_xyzw = vectors[:, int(np.argmax(values))]
    qvec = np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]])
    if qvec[0] < 0:
        qvec = -qvec
    return qvec / np.linalg.norm(qvec)


def pivot_global_to_homogeneous(
    pivot_transform: np.ndarray, pivot: Sequence[float]
) -> np.ndarray:
    """Convert a=p+R(x-p)+t into the usual homogeneous a=Rx+d."""
    transform = np.asarray(pivot_transform, dtype=np.float64)
    pivot_value = np.asarray(pivot, dtype=np.float64)
    output = transform.copy()
    output[:3, 3] = pivot_value - transform[:3, :3] @ pivot_value + transform[:3, 3]
    return output


def conjugate_global_to_canonical(
    global_transform: np.ndarray, global_to_canonical_shift: Sequence[float]
) -> np.ndarray:
    shift = np.asarray(global_to_canonical_shift, dtype=np.float64)
    scene = np.eye(4)
    scene[:3, 3] = shift
    inverse_scene = np.eye(4)
    inverse_scene[:3, 3] = -shift
    return scene @ global_transform @ inverse_scene


def update_colmap_pose(
    qvec: Sequence[float], tvec: Sequence[float], old_world_to_new_world: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return world(A)->camera pose when A=T*P and old pose maps P->camera."""
    rotation = qvec_to_rotmat(qvec)
    extrinsic = np.eye(4)
    extrinsic[:3, :3] = rotation
    extrinsic[:3, 3] = np.asarray(tvec, dtype=np.float64)
    updated = extrinsic @ np.linalg.inv(old_world_to_new_world)
    return rotmat_to_qvec(updated[:3, :3]), updated[:3, 3]


def transform_points3d_bin(
    source: Path, target: Path, old_world_to_new_world: np.ndarray
) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    count_written = 0
    with source.open("rb") as reader, target.open("wb") as writer:
        raw_count = reader.read(8)
        if len(raw_count) != 8:
            raise CoregError("truncated points3D.bin header")
        count = struct.unpack("<Q", raw_count)[0]
        writer.write(raw_count)
        for _ in range(count):
            prefix = reader.read(8)
            xyz_raw = reader.read(24)
            if len(prefix) != 8 or len(xyz_raw) != 24:
                raise CoregError("truncated points3D record")
            xyz = np.asarray(struct.unpack("<ddd", xyz_raw), dtype=np.float64)
            homogeneous = np.append(xyz, 1.0)
            transformed = (old_world_to_new_world @ homogeneous)[:3]
            fixed_tail = reader.read(11)
            if len(fixed_tail) != 11:
                raise CoregError("truncated points3D RGB/error")
            track_count_raw = reader.read(8)
            if len(track_count_raw) != 8:
                raise CoregError("truncated points3D track count")
            track_count = struct.unpack("<Q", track_count_raw)[0]
            track = reader.read(8 * track_count)
            if len(track) != 8 * track_count:
                raise CoregError("truncated points3D track")
            writer.write(prefix)
            writer.write(struct.pack("<ddd", *transformed))
            writer.write(fixed_tail)
            writer.write(track_count_raw)
            writer.write(track)
            count_written += 1
        if reader.read(1):
            raise CoregError("unexpected trailing bytes in points3D.bin")
    return count_written


def write_empty_points3d_bin(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", 0))


def invalidate_points2d_point3d_ids(tail: bytes) -> bytes:
    """Preserve COLMAP 2D features while detaching invalid shared 3D IDs."""

    if len(tail) < 8:
        raise CoregError("images.bin POINTS2D tail is truncated")
    count = struct.unpack_from("<Q", tail, 0)[0]
    expected = 8 + int(count) * 24
    if len(tail) != expected:
        raise CoregError(
            f"images.bin POINTS2D tail length {len(tail)} != {expected}"
        )
    output = bytearray(tail)
    for index in range(int(count)):
        struct.pack_into("<q", output, 8 + index * 24 + 16, -1)
    return bytes(output)


def verify_projection_invariance(
    old: ColmapImageRecord,
    new: ColmapImageRecord,
    old_world_to_new_world: np.ndarray,
) -> float:
    rotation_old = qvec_to_rotmat(old.qvec)
    center_old = -(rotation_old.T @ old.tvec)
    offsets = np.array(
        [
            [1.0, 0.2, 4.0],
            [-0.7, 1.1, 6.0],
            [0.3, -1.4, 8.0],
            [2.0, 1.0, 12.0],
        ]
    )
    old_points = center_old + (rotation_old.T @ offsets.T).T
    new_points = (
        old_world_to_new_world
        @ np.column_stack([old_points, np.ones(len(old_points))]).T
    ).T[:, :3]
    old_camera = (rotation_old @ old_points.T).T + old.tvec
    rotation_new = qvec_to_rotmat(new.qvec)
    new_camera = (rotation_new @ new_points.T).T + new.tvec
    return float(np.max(np.abs(old_camera - new_camera)))


def verify_camera_center_invariance(
    old: ColmapImageRecord,
    new: ColmapImageRecord,
    old_world_to_new_world: np.ndarray,
) -> float:
    old_rotation = qvec_to_rotmat(old.qvec)
    new_rotation = qvec_to_rotmat(new.qvec)
    old_center = -(old_rotation.T @ old.tvec)
    new_center = -(new_rotation.T @ new.tvec)
    expected = (
        old_world_to_new_world @ np.append(old_center, 1.0)
    )[:3]
    return float(np.max(np.abs(new_center - expected)))


def publish_poses_command(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = verify_committed_implementation(config)
    verify_input_hashes(config)
    verify_generated_locks(config)
    runtime = repo_path(config["inputs"]["runtime_dir"])
    check_path = runtime / "independent_check.json"
    frozen_path = runtime / "frozen_transform.json"
    if not check_path.is_file() or not frozen_path.is_file():
        raise CoregError("independent check or frozen transform is missing")
    manifest_path = runtime / "pose_publication_manifest.json"
    if (
        manifest_path.exists()
        or (runtime / "publish_poses_open.json").exists()
        or (runtime / "derived_sparse").exists()
    ):
        raise CoregError("pose publication is exact-once and already started")
    check = json.loads(check_path.read_text())
    frozen = json.loads(frozen_path.read_text())
    if check.get("status") != "PASSED":
        raise CoregError("derived poses cannot be published from a failed check")
    if check["selected_transform_sha256"] != frozen["selected_transform_sha256"]:
        raise CoregError("check/frozen transform hashes differ")
    if check.get("frozen_receipt_sha256") != sha256_file(frozen_path):
        raise CoregError("check recorded a different frozen receipt")
    stage_binding = current_stage_binding(config, provenance)
    verify_parent_binding(check, stage_binding, label="check-to-pose")
    verify_parent_binding(frozen, stage_binding, label="frozen-to-pose")
    verify_frozen_selection_chain(runtime, frozen)
    check_open_path = runtime / "check_open.json"
    if not check_open_path.is_file() or check.get(
        "stage_open_receipt_sha256"
    ) != sha256_file(check_open_path):
        raise CoregError("independent check stage-open receipt hash mismatch")
    verify_stage_open_parent(
        runtime, "check", "frozen_transform", frozen_path
    )
    stage_open = open_exact_stage(
        runtime,
        "publish_poses",
        stage_binding,
        {
            "independent_check": sha256_file(check_path),
            "frozen_transform": sha256_file(frozen_path),
        },
    )
    pivot_transform = np.asarray(
        frozen["selected_photo_to_als_global_pivot_matrix"], dtype=np.float64
    )
    validate_rigid_transform(pivot_transform, tolerance=1e-6)
    global_transform = pivot_global_to_homogeneous(
        pivot_transform, config["input_locks"]["rotation_pivot_global_m"]
    )
    local_transform = conjugate_global_to_canonical(
        global_transform,
        config["input_locks"]["scene_global_to_canonical_shift_m"],
    )
    validate_rigid_transform(local_transform, tolerance=1e-6)
    block_pivot_transforms = {
        block_id: np.asarray(matrix, dtype=np.float64)
        for block_id, matrix in frozen.get("block_transforms", {}).items()
    }
    block_local_transforms: dict[str, np.ndarray] = {}
    for block_id, block_pivot in block_pivot_transforms.items():
        validate_rigid_transform(block_pivot, tolerance=1e-6)
        block_global = pivot_global_to_homogeneous(
            block_pivot, config["input_locks"]["rotation_pivot_global_m"]
        )
        block_local_transforms[block_id] = conjugate_global_to_canonical(
            block_global,
            config["input_locks"]["scene_global_to_canonical_shift_m"],
        )
        validate_rigid_transform(
            block_local_transforms[block_id], tolerance=1e-6
        )
    source_sparse = repo_path(config["inputs"]["colmap_sparse_dir"])
    derived_sparse = runtime / "derived_sparse" / "0"
    derived_sparse.mkdir(parents=True, exist_ok=True)
    source_images = read_images_bin_complete(source_sparse / "images.bin")
    image_to_block = {
        row["image_name"]: row["block_id"]
        for row in _read_csv(config["inputs"]["camera_blocks_csv"])
    }
    per_image_local_transform = {
        image_id: block_local_transforms.get(
            image_to_block[source_images[image_id].name], local_transform
        )
        for image_id in source_images
    }
    if frozen["choice"] == "identity" and not block_local_transforms:
        shutil.copyfile(source_sparse / "cameras.bin", derived_sparse / "cameras.bin")
        shutil.copyfile(source_sparse / "images.bin", derived_sparse / "images.bin")
        shutil.copyfile(source_sparse / "points3D.bin", derived_sparse / "points3D.bin")
        derived_images = read_images_bin_complete(derived_sparse / "images.bin")
        point_count = None
        sparse_points_usable_for_learning = True
    else:
        shutil.copyfile(source_sparse / "cameras.bin", derived_sparse / "cameras.bin")
        derived_images: dict[int, ColmapImageRecord] = {}
        for image_id, image in source_images.items():
            qvec, tvec = update_colmap_pose(
                image.qvec, image.tvec, per_image_local_transform[image_id]
            )
            derived_images[image_id] = ColmapImageRecord(
                image.image_id,
                qvec,
                tvec,
                image.camera_id,
                image.name,
                (
                    invalidate_points2d_point3d_ids(image.points2d_tail)
                    if block_local_transforms
                    else image.points2d_tail
                ),
            )
        write_images_bin_complete(derived_sparse / "images.bin", derived_images)
        serialized_images = derived_images
        derived_images = read_images_bin_complete(derived_sparse / "images.bin")
        if set(derived_images) != set(serialized_images):
            raise CoregError("on-disk derived images.bin inventory differs")
        for image_id in sorted(serialized_images):
            expected_image = serialized_images[image_id]
            observed_image = derived_images[image_id]
            if (
                observed_image.camera_id != expected_image.camera_id
                or observed_image.name != expected_image.name
                or observed_image.points2d_tail != expected_image.points2d_tail
                or not np.array_equal(observed_image.qvec, expected_image.qvec)
                or not np.array_equal(observed_image.tvec, expected_image.tvec)
            ):
                raise CoregError(
                    f"on-disk derived images.bin record differs: {image_id}"
                )
        if block_local_transforms:
            write_empty_points3d_bin(derived_sparse / "points3D.bin")
            point_count = 0
            sparse_points_usable_for_learning = False
        else:
            point_count = transform_points3d_bin(
                source_sparse / "points3D.bin",
                derived_sparse / "points3D.bin",
                local_transform,
            )
            sparse_points_usable_for_learning = True
    maximum_projection_error = max(
        verify_projection_invariance(
            source_images[image_id],
            derived_images[image_id],
            per_image_local_transform[image_id],
        )
        for image_id in sorted(source_images)
    )
    maximum_center_error = max(
        verify_camera_center_invariance(
            source_images[image_id],
            derived_images[image_id],
            per_image_local_transform[image_id],
        )
        for image_id in sorted(source_images)
    )
    if maximum_projection_error > 1e-8:
        raise CoregError(
            f"projection invariance error {maximum_projection_error} exceeds 1e-8"
        )
    if maximum_center_error > 1e-8:
        raise CoregError(
            f"camera-center error {maximum_center_error} exceeds 1e-8"
        )
    manifest = {
        "schema": "jointbuildgs.fusion_w1.coreg_pose_publication.v1",
        "status": "PASSED",
        "choice": frozen["choice"],
        "treatment_name": config["treatment_name"],
        "transform_direction": config["input_locks"]["transform_direction"],
        "pivot_global_m": config["input_locks"]["rotation_pivot_global_m"],
        "photo_to_als_pivot_matrix": _serialize_matrix(pivot_transform),
        "photo_to_als_global_homogeneous": _serialize_matrix(global_transform),
        "photo_to_als_canonical_homogeneous": _serialize_matrix(local_transform),
        "block_photo_to_als_pivot_matrices": {
            block_id: _serialize_matrix(matrix)
            for block_id, matrix in sorted(block_pivot_transforms.items())
        },
        "block_photo_to_als_canonical_matrices": {
            block_id: _serialize_matrix(matrix)
            for block_id, matrix in sorted(block_local_transforms.items())
        },
        "selected_transform_sha256": frozen["selected_transform_sha256"],
        "independent_check_sha256": sha256_file(check_path),
        "source_sparse": relative(source_sparse),
        "derived_sparse": relative(derived_sparse),
        "source_sha256": {
            name: sha256_file(source_sparse / name)
            for name in ("cameras.bin", "images.bin", "points3D.bin")
        },
        "derived_sha256": {
            name: sha256_file(derived_sparse / name)
            for name in ("cameras.bin", "images.bin", "points3D.bin")
        },
        "image_count": len(derived_images),
        "transformed_point3d_count": point_count,
        "sparse_points3d_usable_for_learning": sparse_points_usable_for_learning,
        "block_pose_requires_als_seed_and_forbids_shared_sparse_points": bool(
            block_local_transforms
        ),
        "block_pose_points2d_point3d_ids_invalidated": bool(
            block_local_transforms
        ),
        "maximum_projection_invariance_error": maximum_projection_error,
        "maximum_camera_center_error": maximum_center_error,
        "on_disk_all_camera_pose_roundtrip_verified": True,
        "als_source_sha256_after": sha256_file(
            repo_path(config["inputs"]["als_aoi_laz"])
        ),
        "als_source_modified": False,
        "arm_pose_contract": {
            "arm_A_required_pose_sha256": sha256_file(derived_sparse / "images.bin"),
            "arm_B_required_pose_sha256": sha256_file(derived_sparse / "images.bin"),
            "identical": True,
        },
        "learning_allowed": False,
        "stage_binding": stage_binding,
        "stage_open_receipt_sha256": sha256_file(stage_open),
        "next_step": "core Gate A lock2 once; learning remains forbidden",
    }
    write_json(manifest_path, manifest, exclusive=True)
    return manifest


def publish_small_artifacts(config: Mapping[str, Any]) -> dict[str, Any]:
    """Copy compact measurement outputs into the tracked run publication tree."""
    runtime = repo_path(config["inputs"]["runtime_dir"])
    publication = repo_path(config["inputs"]["publication_dir"])
    publication.mkdir(parents=True, exist_ok=True)
    names = [
        "fit_candidate.json",
        "fit_identity.csv",
        "fit_candidate.csv",
        "fit_residual_comparison.png",
        "trigger_identity.csv",
        "trigger_candidate.csv",
        "trigger_residual_comparison.png",
        "global_selection.json",
        "block_fit_candidates.json",
        "block_selection.json",
        "block_trigger_comparison.csv",
        "block_trigger_selected.png",
        "frozen_transform.json",
        "independent_check.json",
        "independent_check.csv",
        "independent_check.png",
        "pose_publication_manifest.json",
        "failures.jsonl",
        "fit_open.json",
        "select_open.json",
        "fit_blocks_open.json",
        "select_blocks_open.json",
        "check_open.json",
        "publish_poses_open.json",
    ]
    copied: dict[str, str] = {}
    for name in names:
        source = runtime / name
        if source.is_file():
            target = publication / name
            shutil.copyfile(source, target)
            copied[relative(target)] = sha256_file(target)
    manifest = {
        "schema": "jointbuildgs.fusion_w1.coreg_publication.v1",
        "artifacts": copied,
        "runtime_dir": relative(runtime),
        "source_als_sha256_after": sha256_file(
            repo_path(config["inputs"]["als_aoi_laz"])
        ),
        "learning_runs_started": 0,
    }
    write_json(publication / "publication_manifest.json", manifest)
    return manifest


def record_failure(
    config: Mapping[str, Any], command: str, error: BaseException
) -> None:
    try:
        runtime = repo_path(config["inputs"]["runtime_dir"])
        runtime.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": "jointbuildgs.fusion_w1.coreg_failure.v1",
            "command": command,
            "error_type": type(error).__name__,
            "error": str(error),
            "head": (
                subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=ROOT,
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                ).stdout.strip()
            ),
            "learning_runs_started": 0,
        }
        with (runtime / "failures.jsonl").open("a") as handle:
            handle.write(
                json.dumps(json_safe(record), sort_keys=True, allow_nan=False)
                + "\n"
            )
    except Exception:
        pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="lock1 config path",
    )
    parser.add_argument(
        "--recovery-lock2",
        action="store_true",
        help=(
            "activate the committed fresh-control recovery after lock1's "
            "pre-trigger geometry-availability block"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare-controls")
    sub.add_parser("prepare-als")
    sub.add_parser("fit")
    sub.add_parser("select")
    sub.add_parser("fit-blocks")
    sub.add_parser("select-blocks")
    sub.add_parser("check")
    sub.add_parser("publish-poses")
    sub.add_parser("publish-small")
    sub.add_parser("verify")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        if args.recovery_lock2:
            config = activate_recovery_lock2(config)
        if args.command == "prepare-controls":
            result = prepare_controls(config)
        elif args.command == "prepare-als":
            result = prepare_als(config)
        elif args.command == "fit":
            result = fit_command(config)
        elif args.command == "select":
            result = select_command(config)
        elif args.command == "fit-blocks":
            result = fit_blocks_command(config)
        elif args.command == "select-blocks":
            result = select_blocks_command(config)
        elif args.command == "check":
            result = check_command(config)
        elif args.command == "publish-poses":
            result = publish_poses_command(config)
        elif args.command == "publish-small":
            result = publish_small_artifacts(config)
        elif args.command == "verify":
            result = {
                "input_sha256": verify_input_hashes(
                    config, verify_depth_set=True
                ),
                "generated_sha256": verify_generated_locks(config),
                "implementation": verify_committed_implementation(config),
                "prereg_ledger_separation": (
                    verify_recovery_prereg_ledger_separation(config)
                ),
            }
        else:
            raise CoregError(f"unsupported command {args.command}")
    except Exception as exc:
        if config is not None:
            record_failure(config, args.command, exc)
        print(
            f"[FUS-W1-COREG] BLOCKED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(json_safe(result), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
