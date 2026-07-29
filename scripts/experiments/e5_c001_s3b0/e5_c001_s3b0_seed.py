#!/usr/bin/env python3
"""S3-B step-0f V1 virtual seed generation and score-only reference readout.

Generation is restricted to image-derived mono normals, cached FM points, and
the supplied footprint/P0 lattice.  LoD2 is opened only after seed NPZ files
have been written and validated, for the separate score artifact.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely.geometry import Point

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.stage2.semantic_seed import load_surface_seed_npz

import e5_c001_s3b0_common as common


SCORE_FIELDS = [
    "row_type",
    "building_id",
    "variant",
    "variant_role",
    "scope",
    "distance_lower_m",
    "distance_upper_m",
    "point_count",
    "signed_delta_z_median_m",
    "signed_delta_z_mad_m",
    "signed_delta_z_q05_m",
    "signed_delta_z_q95_m",
    "abs_delta_z_median_m",
    "rms_delta_z_m",
    "p0_signed_delta_z_median_m",
    "p0_abs_delta_z_median_m",
    "p0_rms_delta_z_m",
    "delta_signed_median_vs_p0_m",
    "delta_abs_median_vs_p0_m",
    "delta_rms_vs_p0_m",
    "plane_ax_local",
    "plane_by_local",
    "plane_c_local",
    "direction_source",
    "direction_view_count",
    "direction_views",
    "height_anchor_source",
    "height_anchor_count",
    "height_anchor_z_median_local_m",
    "seed_npz",
    "seed_npz_sha256",
    "seed_xyz_payload_sha256",
    "reference_source",
    "reference_used_for_seed_generation",
    "gt_used_for_seed_generation",
    "lod2_used_for_seed_generation",
    "als_used_for_seed_generation",
    "gt_used_for_score",
    "lod2_used_for_score",
    "als_used_for_score",
    "learning_runs_started",
    "new_inference_runs",
    "status",
    "note",
]


def payload_sha256(array: np.ndarray) -> str:
    return common.array_payload_sha256(np.ascontiguousarray(array))


def normal_to_slopes(normal: np.ndarray) -> tuple[float, float]:
    value = np.asarray(normal, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(value))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("normal is not finite/nonzero")
    value = value / norm
    if value[2] < 0:
        value = -value
    if value[2] <= 1e-6:
        raise ValueError(f"normal z is too small for z=ax+by+c: {value.tolist()}")
    return float(-value[0] / value[2]), float(-value[1] / value[2])


def robust_view_normal(values: np.ndarray) -> np.ndarray:
    normals = np.asarray(values, dtype=np.float64).reshape(-1, 3)
    valid = np.isfinite(normals).all(axis=1)
    normals = normals[valid]
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals[lengths > 0.5]
    if not len(normals):
        raise ValueError("no finite normal vectors")
    normals = normals / np.linalg.norm(normals, axis=1, keepdims=True)
    normals[normals[:, 2] < 0] *= -1
    median = np.median(normals, axis=0)
    length = float(np.linalg.norm(median))
    if length <= 1e-12:
        raise ValueError("component median normal is zero")
    return median / length


def pool_v1_normal(
    building_id: str,
    gate_rows: Sequence[dict[str, str]],
    prepared_root: Path,
) -> dict[str, Any]:
    """Pool per-view SAM-region mono normals using existing 0-c eligibility."""
    view_medians: list[np.ndarray] = []
    view_records: list[dict[str, Any]] = []
    source_paths: list[Path] = []
    for row in gate_rows:
        if row["building_id"] != building_id or row["row_type"] != "view":
            continue
        if row["existing_mono_fm_angle_gate_eligible"] != "true":
            continue
        stem = row["view_stem"]
        normal_path = prepared_root / building_id / "mono_normal" / f"{stem}.npy"
        mask_path = common.resolve(row["semantic_mask_npz"])
        normal = np.load(normal_path, allow_pickle=False)
        with np.load(mask_path, allow_pickle=False) as archive:
            target = np.asarray(archive["target_mask"], dtype=bool)
        if normal.shape != (*target.shape, 3):
            raise RuntimeError(f"normal/mask shape mismatch: {building_id} {stem}")
        selected = np.asarray(normal[target], dtype=np.float64)
        median = robust_view_normal(selected)
        finite_count = int(
            (
                np.isfinite(selected).all(axis=1)
                & (np.linalg.norm(np.nan_to_num(selected), axis=1) > 0.5)
            ).sum()
        )
        view_medians.append(median)
        view_records.append(
            {
                "view_stem": stem,
                "mono_fm_angle_median_deg": float(row["mono_fm_angle_median_deg"]),
                "target_mask_pixels": int(target.sum()),
                "finite_normal_count": finite_count,
                "view_median_normal_xyz": median.tolist(),
                "normal_path": common.rel(normal_path),
                "normal_sha256": common.sha256_file(normal_path),
                "semantic_mask_path": common.rel(mask_path),
                "semantic_mask_sha256": common.sha256_file(mask_path),
            }
        )
        source_paths.extend([normal_path, mask_path])
    if not view_medians:
        return {
            "normal": None,
            "views": [],
            "view_records": [],
            "source_paths": [],
        }
    pooled = np.median(np.asarray(view_medians), axis=0)
    pooled = pooled / np.linalg.norm(pooled)
    if pooled[2] < 0:
        pooled = -pooled
    return {
        "normal": pooled,
        "views": [row["view_stem"] for row in view_records],
        "view_records": view_records,
        "source_paths": source_paths,
    }


def plane_through_anchor(
    slopes: tuple[float, float],
    anchor_xy_local: np.ndarray,
    anchor_z_local: float,
) -> np.ndarray:
    ax, by = slopes
    x, y = np.asarray(anchor_xy_local, dtype=np.float64).reshape(2)
    c = float(anchor_z_local) - ax * float(x) - by * float(y)
    return np.asarray([ax, by, c], dtype=np.float64)


def plane_from_xyz(points: np.ndarray) -> np.ndarray:
    xyz = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    design = np.column_stack([xyz[:, 0], xyz[:, 1], np.ones(len(xyz))])
    return np.linalg.lstsq(design, xyz[:, 2], rcond=None)[0].astype(np.float64)


def metric_values(errors: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(errors, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {
            "signed_delta_z_median_m": None,
            "signed_delta_z_mad_m": None,
            "signed_delta_z_q05_m": None,
            "signed_delta_z_q95_m": None,
            "abs_delta_z_median_m": None,
            "rms_delta_z_m": None,
        }
    median = float(np.median(values))
    return {
        "signed_delta_z_median_m": median,
        "signed_delta_z_mad_m": float(np.median(np.abs(values - median))),
        "signed_delta_z_q05_m": float(np.quantile(values, 0.05)),
        "signed_delta_z_q95_m": float(np.quantile(values, 0.95)),
        "abs_delta_z_median_m": float(np.median(np.abs(values))),
        "rms_delta_z_m": float(np.sqrt(np.mean(values * values))),
    }


def nearest_distance(xy: np.ndarray, anchors: np.ndarray) -> np.ndarray:
    left = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    right = np.asarray(anchors, dtype=np.float64).reshape(-1, 2)
    if not len(right):
        return np.full(len(left), np.nan, dtype=np.float64)
    return np.sqrt(np.min(np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2), axis=1))


def score_masks(
    xy_utm: np.ndarray,
    footprint: Any,
    fm_xy_local: np.ndarray,
    xy_local: np.ndarray,
    edge_band_m: float,
    far_bins: Sequence[float],
    include_far_field: bool,
) -> list[tuple[str, float | None, float | None, np.ndarray]]:
    boundary_distance = np.asarray(
        [footprint.boundary.distance(Point(float(x), float(y))) for x, y in xy_utm],
        dtype=np.float64,
    )
    scopes: list[tuple[str, float | None, float | None, np.ndarray]] = [
        ("overall", None, None, np.ones(len(xy_utm), dtype=bool)),
        ("edge", None, edge_band_m, boundary_distance <= edge_band_m),
        ("interior", edge_band_m, None, boundary_distance > edge_band_m),
    ]
    if include_far_field:
        distance = nearest_distance(xy_local, fm_xy_local)
        edges = list(float(value) for value in far_bins)
        for index, lower in enumerate(edges):
            upper = edges[index + 1] if index + 1 < len(edges) else None
            mask = distance >= lower
            if upper is not None:
                mask &= distance < upper
            scopes.append(("far_field", lower, upper, mask))
    return scopes


def plot_seed_scores(
    output_path: Path,
    building_id: str,
    footprint: Any,
    offset: np.ndarray,
    xy_local: np.ndarray,
    reference_z: np.ndarray,
    p0_z: np.ndarray,
    v1_z: np.ndarray,
    fm_xy_local: np.ndarray,
) -> None:
    xy_utm = xy_local + offset[None, :2]
    centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
    p0_error = p0_z - reference_z
    v1_error = v1_z - reference_z
    limit = max(
        0.10,
        float(np.quantile(np.abs(np.concatenate([p0_error, v1_error])), 0.98)),
    )
    figure, axes = plt.subplots(1, 3, figsize=(15.5, 4.8))
    scatter = None
    for axis, title, error in (
        (axes[0], "P0 signed dz", p0_error),
        (axes[1], "V1 P0-prime signed dz", v1_error),
    ):
        scatter = axis.scatter(
            xy_utm[:, 0] - centre[0],
            xy_utm[:, 1] - centre[1],
            c=error,
            s=22,
            cmap="coolwarm",
            vmin=-limit,
            vmax=limit,
        )
        for polygon in common.flatten_polygons(footprint):
            ring = np.asarray(polygon.exterior.coords)
            axis.plot(ring[:, 0] - centre[0], ring[:, 1] - centre[1], color="black", linewidth=1.1)
        axis.set_title(
            f"{title}\nmedian={np.median(error):.3f} m, |dz| median={np.median(np.abs(error)):.3f} m"
        )
        axis.set_aspect("equal")
        axis.set_xlabel("E - centroid [m]")
        axis.set_ylabel("N - centroid [m]")
    if scatter is not None:
        color_axis = axes[1].inset_axes([0.88, 0.54, 0.035, 0.36])
        colorbar = figure.colorbar(scatter, cax=color_axis)
        colorbar.set_label("dz [m]", fontsize=8)
        colorbar.ax.tick_params(labelsize=7)

    distance = nearest_distance(xy_local, fm_xy_local)
    order = np.argsort(distance)
    axes[2].scatter(distance[order], p0_error[order], s=11, alpha=0.55, label="P0")
    axes[2].scatter(distance[order], v1_error[order], s=11, alpha=0.55, label="V1")
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set_xlabel("distance to nearest FM anchor [m]")
    axes[2].set_ylabel("candidate - reference [m]")
    axes[2].set_title("Distance profile")
    axes[2].legend()
    figure.suptitle(f"{building_id} virtual-seed score-only readout", fontsize=13)
    figure.subplots_adjust(top=0.84, wspace=0.32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)


def load_gate_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_v1(args: argparse.Namespace) -> None:
    lock = common.load_lock(args.lock)
    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    seed_cfg = lock["seed_0f"]
    if int(lock["learning_runs_allowed"]) != 0:
        raise RuntimeError("learning-zero lock drift")

    run_dir = outputs["seed_run"]
    seed_dir = run_dir / "seeds"
    figure_dir = outputs["seed_figure_dir"]
    seed_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    gate_rows = load_gate_rows(outputs["gate_csv"])
    fm = common.load_fm_summaries(sources["fm_rescore_csv"])
    offset = common.load_world_offset(sources["train_manifest"])
    footprints = common.load_footprints(sources["footprints"], lock["targets"])
    p0 = np.load(sources["p0_fill_npz"], allow_pickle=False)

    generation_sources: set[Path] = {
        args.lock.resolve(),
        Path(__file__).resolve(),
        Path(common.__file__).resolve(),
        common.REPO / "scripts/experiments/e5_c001_s3b0/run_e5_c001_s3b0_seed_v1.sh",
        common.REPO / "tests/experiments/e5_c001_s3b0/test_e5_c001_s3b0_seed.py",
        common.REPO / "src/stage2/semantic_seed.py",
        outputs["gate_csv"],
        sources["fm_rescore_csv"],
        sources["p0_fill_npz"],
        sources["footprints"],
        sources["train_manifest"],
    }
    seed_records: dict[str, dict[str, Any]] = {}
    generated_seeds: list[Path] = []

    # Generation phase: no reference geometry is opened above or inside this loop.
    for short in lock["targets"]:
        building_id = common.full_id(short)
        surface_key = f"{building_id}_local_xyz"
        fm_key = f"{building_id}_fm_local_xyz"
        lattice = np.asarray(p0[surface_key], dtype=np.float64)
        fm_points = np.asarray(p0[fm_key], dtype=np.float64)
        pooled = pool_v1_normal(building_id, gate_rows, sources["prepared_root"])
        generation_sources.update(pooled["source_paths"])
        if pooled["normal"] is not None:
            normal = np.asarray(pooled["normal"], dtype=np.float64)
            slopes = normal_to_slopes(normal)
            direction_source = "mono_normal_region_median"
            fallback_reason = ""
        else:
            source_plane = np.asarray(fm[short]["plane"], dtype=np.float64)
            slopes = (float(source_plane[0]), float(source_plane[1]))
            normal = np.asarray([-slopes[0], -slopes[1], 1.0], dtype=np.float64)
            normal /= np.linalg.norm(normal)
            direction_source = "fm_fitted_plane_normal_fallback"
            fallback_reason = "no view marked eligible by existing mono-FM 22.5deg gate"
        anchor_z = float(fm[short]["inside_z_median_local_m"])
        centroid_utm = np.asarray(footprints[building_id].centroid.coords[0], dtype=np.float64)
        centroid_local = centroid_utm - offset[:2]
        plane = plane_through_anchor(slopes, centroid_local, anchor_z)
        xyz64 = np.column_stack(
            [
                lattice[:, 0],
                lattice[:, 1],
                plane[0] * lattice[:, 0] + plane[1] * lattice[:, 1] + plane[2],
            ]
        )
        source_seed_path = (
            sources["phase1_seed_root"] / f"{building_id}_p0_surface_seed.npz"
        )
        with np.load(source_seed_path, allow_pickle=False) as source_seed:
            scene_rgb = np.asarray(source_seed["rgb"][0], dtype=np.float32)
        generation_sources.add(source_seed_path)
        xyz = np.ascontiguousarray(xyz64, dtype=np.float32)
        rgb = np.repeat(scene_rgb[None, :], len(xyz), axis=0).astype(np.float32)
        sem = np.full(len(xyz), int(seed_cfg["semantic_class"]), dtype=np.int64)
        metadata = {
            "schema": "jointbuildgs.s3ap.surface_seeds.v1",
            "seed_type": "surface",
            "building_id": building_id,
            "seed_variant": "V1",
            "crs": lock["crs"],
            "coordinate_frame": seed_cfg["coordinate_frame"],
            "coordinate_frame_definition": "EPSG:25832 XY minus world_offset; ellipsoidal Z local",
            "lineage": {
                "kind": "s3b0_virtual_seed_v1",
                "direction_source": direction_source,
                "direction_normal_xyz": normal.tolist(),
                "direction_views": pooled["views"],
                "direction_view_records": pooled["view_records"],
                "fallback_reason": fallback_reason,
                "gate_score_artifact": common.rel(outputs["gate_csv"]),
                "gate_score_sha256": common.sha256_file(outputs["gate_csv"]),
                "fm_score_artifact": common.rel(sources["fm_rescore_csv"]),
                "fm_score_sha256": common.sha256_file(sources["fm_rescore_csv"]),
                "xy_lattice_artifact": common.rel(sources["p0_fill_npz"]),
                "xy_lattice_key": surface_key,
                "xy_lattice_payload_sha256": payload_sha256(lattice[:, :2]),
            },
            "grid_m": float(seed_cfg["grid_m"]),
            "grid_spacing_m": float(seed_cfg["grid_m"]),
            "height_anchor_source": "footprint_inside_fm_z_median",
            "height_anchor_count": int(fm[short]["inside_point_count"]),
            "height_anchor_z_median_local_m": anchor_z,
            "height_anchor_location": seed_cfg["height_anchor_location"],
            "height_anchor_xy_local": centroid_local.tolist(),
            "plane_ax_local": float(plane[0]),
            "plane_by_local": float(plane[1]),
            "plane_c_local": float(plane[2]),
            "planned_init_opacity": float(seed_cfg["planned_init_opacity"]),
            "current_loader_surface_opacity_observed": 0.10,
            "rgb_source": "committed Phase-1 C001 sparse-scene mean RGB",
            "seed_semantic": int(seed_cfg["semantic_class"]),
            "footprint_role": "surface extent and height-anchor location only",
            "gt_used_for_seed_generation": False,
            "lod2_used_for_seed_generation": False,
            "als_used_for_seed_generation": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        }
        seed_path = seed_dir / f"{building_id}_v1_surface_seed.npz"
        common.atomic_deterministic_npz(
            seed_path,
            {
                "metadata_json": np.asarray(
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                ),
                "rgb": rgb,
                "sem": sem,
                "xyz": xyz,
            },
        )
        loaded = load_surface_seed_npz(seed_path)
        if not np.array_equal(loaded.xyz, xyz) or not np.array_equal(loaded.rgb, rgb):
            raise RuntimeError(f"engine loader round-trip mismatch: {building_id}")
        if set(np.load(seed_path, allow_pickle=False).files) != set(seed_cfg["required_npz_keys"]):
            raise RuntimeError(f"seed key contract mismatch: {building_id}")
        generated_seeds.append(seed_path)
        seed_records[short] = {
            "building_id": building_id,
            "variant": "V1",
            "direction_source": direction_source,
            "direction_normal_xyz": normal.tolist(),
            "direction_view_count": len(pooled["views"]),
            "direction_views": pooled["views"],
            "direction_view_records": pooled["view_records"],
            "fallback_reason": fallback_reason,
            "height_anchor_source": "footprint_inside_fm_z_median",
            "height_anchor_count": int(fm[short]["inside_point_count"]),
            "height_anchor_z_median_local_m": anchor_z,
            "height_anchor_xy_local": centroid_local.tolist(),
            "plane_ax_by_c": plane.tolist(),
            "grid_m": float(seed_cfg["grid_m"]),
            "seed_count": int(len(xyz)),
            "planned_init_opacity": float(seed_cfg["planned_init_opacity"]),
            "current_loader_surface_opacity_observed": float(loaded.init_opacity[0]),
            "seed_npz": common.rel(seed_path),
            "seed_npz_sha256": common.sha256_file(seed_path),
            "seed_xyz_payload_sha256": payload_sha256(xyz),
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        }

    # Score phase starts only after every V1 NPZ has been written and validated.
    roofs = common.load_lod2_roofs(sources["lod2_dir"], lock["targets"])
    projection = json.loads(sources["projection_datum"].read_text(encoding="utf-8"))
    geoid_m = float(projection["orthometric_geoid_m"])
    score_only_sources = {
        sources["projection_datum"],
        *sorted(sources["lod2_dir"].glob("*.gml")),
    }
    score_rows: list[dict[str, Any]] = []
    figure_paths: list[Path] = []
    for short in lock["targets"]:
        building_id = common.full_id(short)
        lattice = np.asarray(p0[f"{building_id}_local_xyz"], dtype=np.float64)
        fm_points = np.asarray(p0[f"{building_id}_fm_local_xyz"], dtype=np.float64)
        xy_local = lattice[:, :2]
        xy_utm = xy_local + offset[None, :2]
        reference_z = (
            common.reference_roof_z(xy_utm, roofs[short], geoid_m) - offset[2]
        )
        v1_path = common.resolve(seed_records[short]["seed_npz"])
        with np.load(v1_path, allow_pickle=False) as archive:
            v1_xyz = np.asarray(archive["xyz"], dtype=np.float64)
        variants = {
            "P0": {
                "xyz": lattice,
                "role": "existing FM fitted-plane seed",
                "plane": plane_from_xyz(lattice),
                "direction_source": "existing_p0_fm_fitted_plane",
                "direction_views": [],
                "seed_npz": sources["phase1_seed_root"] / f"{building_id}_p0_surface_seed.npz",
            },
            "V1": {
                "xyz": v1_xyz,
                "role": "P0-prime V1 virtual seed",
                "plane": np.asarray(seed_records[short]["plane_ax_by_c"], dtype=np.float64),
                "direction_source": seed_records[short]["direction_source"],
                "direction_views": seed_records[short]["direction_views"],
                "seed_npz": v1_path,
            },
        }
        scopes = score_masks(
            xy_utm,
            footprints[building_id],
            fm_points[:, :2],
            xy_local,
            float(seed_cfg["edge_band_m"]),
            seed_cfg["far_field_distance_bins_m"],
            include_far_field=(short == "4907199"),
        )
        baseline: dict[tuple[str, float | None, float | None], dict[str, Any]] = {}
        raw_rows: list[dict[str, Any]] = []
        for variant in ("P0", "V1"):
            record = variants[variant]
            error = record["xyz"][:, 2] - reference_z
            for scope, lower, upper, mask in scopes:
                metrics = metric_values(error[mask])
                row = {
                    "row_type": "score",
                    "building_id": building_id,
                    "variant": variant,
                    "variant_role": record["role"],
                    "scope": scope,
                    "distance_lower_m": lower,
                    "distance_upper_m": upper,
                    "point_count": int(mask.sum()),
                    **metrics,
                    "plane_ax_local": float(record["plane"][0]),
                    "plane_by_local": float(record["plane"][1]),
                    "plane_c_local": float(record["plane"][2]),
                    "direction_source": record["direction_source"],
                    "direction_view_count": len(record["direction_views"]),
                    "direction_views": ";".join(record["direction_views"]),
                    "height_anchor_source": (
                        "existing P0 FM fitted-plane"
                        if variant == "P0"
                        else seed_records[short]["height_anchor_source"]
                    ),
                    "height_anchor_count": int(fm[short]["inside_point_count"]),
                    "height_anchor_z_median_local_m": float(
                        fm[short]["inside_z_median_local_m"]
                    ),
                    "seed_npz": common.rel(record["seed_npz"]),
                    "seed_npz_sha256": common.sha256_file(record["seed_npz"]),
                    "seed_xyz_payload_sha256": payload_sha256(
                        np.asarray(record["xyz"], dtype=np.float32)
                    ),
                    "reference_source": "CityGML LoD2 RoofSurface + configured orthometric geoid",
                    "reference_used_for_seed_generation": False,
                    "gt_used_for_seed_generation": False,
                    "lod2_used_for_seed_generation": False,
                    "als_used_for_seed_generation": False,
                    "gt_used_for_score": True,
                    "lod2_used_for_score": True,
                    "als_used_for_score": False,
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                    "status": "measured" if int(mask.sum()) else "empty_scope",
                    "note": "reference opened after V1 seed write and engine-loader validation",
                }
                key = (scope, lower, upper)
                if variant == "P0":
                    baseline[key] = metrics
                raw_rows.append(row)
        for row in raw_rows:
            key = (row["scope"], row["distance_lower_m"], row["distance_upper_m"])
            base = baseline[key]
            row["p0_signed_delta_z_median_m"] = base["signed_delta_z_median_m"]
            row["p0_abs_delta_z_median_m"] = base["abs_delta_z_median_m"]
            row["p0_rms_delta_z_m"] = base["rms_delta_z_m"]
            for metric, output in (
                ("signed_delta_z_median_m", "delta_signed_median_vs_p0_m"),
                ("abs_delta_z_median_m", "delta_abs_median_vs_p0_m"),
                ("rms_delta_z_m", "delta_rms_vs_p0_m"),
            ):
                value = row[metric]
                reference = base[metric]
                row[output] = (
                    float(value) - float(reference)
                    if value is not None and reference is not None
                    else None
                )
            score_rows.append(row)
        figure_path = figure_dir / f"{building_id}_v1_score.png"
        plot_seed_scores(
            figure_path,
            building_id,
            footprints[building_id],
            offset,
            xy_local,
            reference_z,
            lattice[:, 2],
            v1_xyz[:, 2],
            fm_points[:, :2],
        )
        figure_paths.append(figure_path)

    common.atomic_csv(outputs["seed_score_csv"], score_rows, SCORE_FIELDS)
    v1_score_archive = run_dir / "v1_scores.csv"
    common.atomic_csv(v1_score_archive, score_rows, SCORE_FIELDS)
    output_paths = [v1_score_archive, *generated_seeds, *figure_paths]
    manifest = {
        "schema": "jointbuildgs.s3b0.virtual_seed.v1",
        "created_utc": common.now(),
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "crs": lock["crs"],
        "variant": "V1",
        "generation_contract": {
            "direction": seed_cfg["mono_pool_rule"],
            "fallback": "FM fitted-plane normal when no existing 22.5deg eligible view",
            "height": "median z of every footprint-inside cached FM point",
            "height_anchor_location": seed_cfg["height_anchor_location"],
            "xy_lattice": "existing P0 0.5m footprint lattice, XY reused exactly",
            "planned_init_opacity": float(seed_cfg["planned_init_opacity"]),
            "current_loader_surface_opacity_observed": 0.10,
            "required_npz_keys": seed_cfg["required_npz_keys"],
        },
        "seed_records": seed_records,
        "score_contract": {
            "reference": "CityGML LoD2 RoofSurface plus configured orthometric geoid",
            "scopes": ["overall", "edge<=1m", "interior>1m"],
            "far_field_target": "4907199",
            "far_field_distance": "nearest footprint-inside FM anchor XY",
            "far_field_bins_m": seed_cfg["far_field_distance_bins_m"],
            "delta_definition": "variant metric minus P0 metric for the identical scope",
        },
        "counts": {
            "seed_artifacts": len(generated_seeds),
            "score_rows": len(score_rows),
            "figures": len(figure_paths),
        },
        "gt_boundary": {
            "generation_gt_used": False,
            "generation_lod2_used": False,
            "generation_als_used": False,
            "score_gt_used": True,
            "score_lod2_used": True,
            "score_als_used": False,
            "ordering": "all V1 NPZ files written and engine-validated before reference load",
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "generation_source_sha256": common.source_hashes(generation_sources),
        "score_only_source_sha256": common.source_hashes(score_only_sources),
        "output_sha256": common.source_hashes(output_paths),
    }
    common.atomic_json(run_dir / "v1_manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "measured",
                "seed_artifacts": len(generated_seeds),
                "score_rows": len(score_rows),
                "figures": len(figure_paths),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


def load_gtfree_segment_anchors(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    output: dict[str, list[dict[str, Any]]] = {}
    positive_statuses = {
        "interior_positive_peak",
        "boundary_positive_peak",
        "tied_positive_peak",
    }
    for row in rows:
        if (
            row.get("gt_used") != "false"
            or row.get("lod2_used") != "false"
            or row.get("als_used") != "false"
            or row.get("learning_runs_started") != "0"
            or row.get("new_inference_runs") != "0"
        ):
            raise RuntimeError(f"GT-free anchor handoff flag drift: {path}")
        if row.get("peak_status") not in positive_statuses:
            raise RuntimeError(
                f"V2 peak condition is not present: {row.get('building_id')} "
                f"segment={row.get('segment_index')} status={row.get('peak_status')}"
            )
        short = common.short_id(row["building_id"])
        output.setdefault(short, []).append(
            {
                "building_id": row["building_id"],
                "segment_index": int(row["segment_index"]),
                "segment_length_m": float(row["segment_length_m"]),
                "segment_midpoint_e_utm": float(row["segment_midpoint_e_utm"]),
                "segment_midpoint_n_utm": float(row["segment_midpoint_n_utm"]),
                "h_est_local_m": float(row["h_est_local_m"]),
                "h_est_above_ground_m": float(row["h_est_above_ground_m"]),
                "peak_score": float(row["peak_score"]),
                "background_median_score": (
                    float(row["background_median_score"])
                    if row["background_median_score"]
                    else None
                ),
                "peak_to_background_ratio": (
                    float(row["peak_to_background_ratio"])
                    if row["peak_to_background_ratio"]
                    else None
                ),
                "peak_status": row["peak_status"],
            }
        )
    for short, values in output.items():
        values.sort(key=lambda row: row["segment_index"])
        if len(values) != 4 or [row["segment_index"] for row in values] != [1, 2, 3, 4]:
            raise RuntimeError(f"V2 requires four ordered segment anchors: {short}: {values}")
    return output


def plot_seed_scores_v2(
    output_path: Path,
    building_id: str,
    footprint: Any,
    offset: np.ndarray,
    xy_local: np.ndarray,
    reference_z: np.ndarray,
    p0_z: np.ndarray,
    v1_z: np.ndarray,
    v2_z: np.ndarray,
    fm_xy_local: np.ndarray,
) -> None:
    xy_utm = xy_local + offset[None, :2]
    centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
    errors = {
        "P0": p0_z - reference_z,
        "V1": v1_z - reference_z,
        "V2": v2_z - reference_z,
    }
    limit = max(
        0.10,
        float(np.quantile(np.abs(np.concatenate(list(errors.values()))), 0.98)),
    )
    figure, axes = plt.subplots(1, 4, figsize=(20, 4.8))
    scatter = None
    for axis, variant in zip(axes[:3], ("P0", "V1", "V2")):
        error = errors[variant]
        scatter = axis.scatter(
            xy_utm[:, 0] - centre[0],
            xy_utm[:, 1] - centre[1],
            c=error,
            s=21,
            cmap="coolwarm",
            vmin=-limit,
            vmax=limit,
        )
        for polygon in common.flatten_polygons(footprint):
            ring = np.asarray(polygon.exterior.coords)
            axis.plot(
                ring[:, 0] - centre[0],
                ring[:, 1] - centre[1],
                color="black",
                linewidth=1.0,
            )
        axis.set_title(
            f"{variant} signed dz\nmedian={np.median(error):.3f} m, "
            f"|dz| median={np.median(np.abs(error)):.3f} m"
        )
        axis.set_aspect("equal")
        axis.set_xlabel("E - centroid [m]")
        axis.set_ylabel("N - centroid [m]")
    if scatter is not None:
        color_axis = axes[2].inset_axes([0.88, 0.54, 0.035, 0.36])
        colorbar = figure.colorbar(scatter, cax=color_axis)
        colorbar.set_label("dz [m]", fontsize=8)
        colorbar.ax.tick_params(labelsize=7)

    distance = nearest_distance(xy_local, fm_xy_local)
    order = np.argsort(distance)
    for variant, color in (("P0", "#1f77b4"), ("V1", "#ff7f0e"), ("V2", "#2ca02c")):
        axes[3].scatter(
            distance[order],
            errors[variant][order],
            s=10,
            alpha=0.48,
            color=color,
            label=variant,
        )
    axes[3].axhline(0.0, color="black", linewidth=0.8)
    axes[3].set_xlabel("distance to nearest FM anchor [m]")
    axes[3].set_ylabel("candidate - reference [m]")
    axes[3].set_title("Distance profile")
    axes[3].legend()
    figure.suptitle(f"{building_id} V1/V2 virtual-seed score-only readout", fontsize=13)
    figure.subplots_adjust(top=0.84, wspace=0.32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)


def score_variant_rows(
    *,
    lock: dict[str, Any],
    building_id: str,
    short: str,
    variants: dict[str, dict[str, Any]],
    xy_local: np.ndarray,
    reference_z: np.ndarray,
    footprint: Any,
    fm_points: np.ndarray,
    fm_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    xy_utm = xy_local + np.asarray(variants["P0"]["offset_xy"])[None, :]
    scopes = score_masks(
        xy_utm,
        footprint,
        fm_points[:, :2],
        xy_local,
        float(lock["seed_0f"]["edge_band_m"]),
        lock["seed_0f"]["far_field_distance_bins_m"],
        include_far_field=(short == "4907199"),
    )
    baseline: dict[tuple[str, float | None, float | None], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for variant in ("P0", "V1", "V2"):
        record = variants[variant]
        error = np.asarray(record["xyz"], dtype=np.float64)[:, 2] - reference_z
        for scope, lower, upper, mask in scopes:
            metrics = metric_values(error[mask])
            row = {
                "row_type": "score",
                "building_id": building_id,
                "variant": variant,
                "variant_role": record["role"],
                "scope": scope,
                "distance_lower_m": lower,
                "distance_upper_m": upper,
                "point_count": int(mask.sum()),
                **metrics,
                "plane_ax_local": float(record["plane"][0]),
                "plane_by_local": float(record["plane"][1]),
                "plane_c_local": float(record["plane"][2]),
                "direction_source": record["direction_source"],
                "direction_view_count": len(record["direction_views"]),
                "direction_views": ";".join(record["direction_views"]),
                "height_anchor_source": record["height_anchor_source"],
                "height_anchor_count": int(record["height_anchor_count"]),
                "height_anchor_z_median_local_m": float(record["height_anchor_z"]),
                "seed_npz": common.rel(record["seed_path"]),
                "seed_npz_sha256": common.sha256_file(record["seed_path"]),
                "seed_xyz_payload_sha256": payload_sha256(
                    np.asarray(record["xyz"], dtype=np.float32)
                ),
                "reference_source": "CityGML LoD2 RoofSurface + configured orthometric geoid",
                "reference_used_for_seed_generation": False,
                "gt_used_for_seed_generation": False,
                "lod2_used_for_seed_generation": False,
                "als_used_for_seed_generation": False,
                "gt_used_for_score": True,
                "lod2_used_for_score": True,
                "als_used_for_score": False,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
                "status": "measured" if int(mask.sum()) else "empty_scope",
                "note": "reference opened after V2 seed write and engine-loader validation",
            }
            key = (scope, lower, upper)
            if variant == "P0":
                baseline[key] = metrics
            rows.append(row)
    for row in rows:
        base = baseline[(row["scope"], row["distance_lower_m"], row["distance_upper_m"])]
        row["p0_signed_delta_z_median_m"] = base["signed_delta_z_median_m"]
        row["p0_abs_delta_z_median_m"] = base["abs_delta_z_median_m"]
        row["p0_rms_delta_z_m"] = base["rms_delta_z_m"]
        for metric, output in (
            ("signed_delta_z_median_m", "delta_signed_median_vs_p0_m"),
            ("abs_delta_z_median_m", "delta_abs_median_vs_p0_m"),
            ("rms_delta_z_m", "delta_rms_vs_p0_m"),
        ):
            value = row[metric]
            reference = base[metric]
            row[output] = (
                float(value) - float(reference)
                if value is not None and reference is not None
                else None
            )
    return rows


def run_v2(args: argparse.Namespace) -> None:
    lock = common.load_lock(args.lock)
    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    seed_cfg = lock["seed_0f"]
    run_dir = outputs["seed_run"]
    seed_dir = run_dir / "seeds"
    figure_dir = outputs["seed_figure_dir"]
    anchor_path = outputs["hsweep_anchor_csv"]
    hsweep_manifest_path = outputs["hsweep_run"] / "manifest.json"
    v1_manifest_path = run_dir / "v1_manifest.json"
    for path in (anchor_path, hsweep_manifest_path, v1_manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    anchors_by_short = load_gtfree_segment_anchors(anchor_path)
    fm = common.load_fm_summaries(sources["fm_rescore_csv"])
    offset = common.load_world_offset(sources["train_manifest"])
    footprints = common.load_footprints(sources["footprints"], lock["targets"])
    p0 = np.load(sources["p0_fill_npz"], allow_pickle=False)

    generation_sources: set[Path] = {
        args.lock.resolve(),
        Path(__file__).resolve(),
        Path(common.__file__).resolve(),
        common.REPO / "scripts/experiments/e5_c001_s3b0/run_e5_c001_s3b0_seed_v2.sh",
        common.REPO / "tests/experiments/e5_c001_s3b0/test_e5_c001_s3b0_seed.py",
        common.REPO / "src/stage2/semantic_seed.py",
        anchor_path,
        hsweep_manifest_path,
        v1_manifest_path,
        sources["fm_rescore_csv"],
        sources["p0_fill_npz"],
        sources["footprints"],
        sources["train_manifest"],
    }
    v2_records: dict[str, dict[str, Any]] = {}
    v2_paths: list[Path] = []

    # Generation phase reads only the dedicated GT-free anchor handoff.
    for short in lock["targets"]:
        building_id = common.full_id(short)
        v1_path = seed_dir / f"{building_id}_v1_surface_seed.npz"
        if not v1_path.is_file():
            raise FileNotFoundError(v1_path)
        generation_sources.add(v1_path)
        with np.load(v1_path, allow_pickle=False) as archive:
            v1_xyz = np.asarray(archive["xyz"], dtype=np.float32)
            v1_rgb = np.asarray(archive["rgb"], dtype=np.float32)
            v1_sem = np.asarray(archive["sem"], dtype=np.int64)
            v1_metadata = json.loads(str(archive["metadata_json"].item()))
        expected_xy = np.asarray(
            p0[f"{building_id}_local_xyz"][:, :2], dtype=np.float32
        )
        if not np.array_equal(v1_xyz[:, :2], expected_xy):
            raise RuntimeError(f"V1/P0 XY lattice drift: {building_id}")
        centroid_local = np.asarray(v1_metadata["height_anchor_xy_local"], dtype=np.float64)
        expected_centroid = (
            np.asarray(footprints[building_id].centroid.coords[0], dtype=np.float64)
            - offset[:2]
        )
        if not np.allclose(centroid_local, expected_centroid, atol=1e-9, rtol=0.0):
            raise RuntimeError(f"V1 centroid anchor drift: {building_id}")
        central_z = float(v1_metadata["height_anchor_z_median_local_m"])
        segment_rows = anchors_by_short.get(short, [])
        if len(segment_rows) != 4:
            raise RuntimeError(f"V2 segment-anchor count drift: {building_id}")
        anchors = np.asarray(
            [
                [centroid_local[0], centroid_local[1], central_z],
                *[
                    [
                        row["segment_midpoint_e_utm"] - offset[0],
                        row["segment_midpoint_n_utm"] - offset[1],
                        row["h_est_local_m"],
                    ]
                    for row in segment_rows
                ],
            ],
            dtype=np.float64,
        )
        design = np.column_stack([anchors[:, 0], anchors[:, 1], np.ones(len(anchors))])
        if np.linalg.matrix_rank(design) < 3:
            raise RuntimeError(f"V2 anchor design rank drift: {building_id}")
        plane = np.linalg.lstsq(design, anchors[:, 2], rcond=None)[0].astype(np.float64)
        residual = anchors[:, 2] - design @ plane
        anchor_rms = float(np.sqrt(np.mean(residual * residual)))
        xyz64 = np.column_stack(
            [
                v1_xyz[:, 0].astype(np.float64),
                v1_xyz[:, 1].astype(np.float64),
                plane[0] * v1_xyz[:, 0]
                + plane[1] * v1_xyz[:, 1]
                + plane[2],
            ]
        )
        xyz = np.ascontiguousarray(xyz64, dtype=np.float32)
        metadata = {
            "schema": "jointbuildgs.s3ap.surface_seeds.v1",
            "seed_type": "surface",
            "building_id": building_id,
            "seed_variant": "V2",
            "crs": lock["crs"],
            "coordinate_frame": seed_cfg["coordinate_frame"],
            "coordinate_frame_definition": "EPSG:25832 XY minus world_offset; ellipsoidal Z local",
            "lineage": {
                "kind": "s3b0_virtual_seed_v2",
                "fit_rule": seed_cfg["v2_fit_rule"],
                "v1_seed_artifact": common.rel(v1_path),
                "v1_seed_sha256": common.sha256_file(v1_path),
                "v1_plane_ax_by_c": [
                    float(v1_metadata["plane_ax_local"]),
                    float(v1_metadata["plane_by_local"]),
                    float(v1_metadata["plane_c_local"]),
                ],
                "centroid_anchor_xy_local": centroid_local.tolist(),
                "centroid_anchor_z_local": central_z,
                "segment_anchor_artifact": common.rel(anchor_path),
                "segment_anchor_sha256": common.sha256_file(anchor_path),
                "segment_anchor_records": segment_rows,
                "anchor_count": int(len(anchors)),
                "anchor_rms_m": anchor_rms,
            },
            "grid_m": float(seed_cfg["grid_m"]),
            "grid_spacing_m": float(seed_cfg["grid_m"]),
            "height_anchor_source": "V1 centroid FM anchor plus GT-free h-sweep segment anchors",
            "height_anchor_count": int(len(anchors)),
            "height_anchor_z_median_local_m": float(np.median(anchors[:, 2])),
            "height_anchor_location": "one footprint centroid plus four segment midpoints",
            "plane_ax_local": float(plane[0]),
            "plane_by_local": float(plane[1]),
            "plane_c_local": float(plane[2]),
            "planned_init_opacity": float(seed_cfg["planned_init_opacity"]),
            "current_loader_surface_opacity_observed": 0.10,
            "rgb_source": "V1 seed RGB copied exactly",
            "seed_semantic": int(seed_cfg["semantic_class"]),
            "footprint_role": "V1 XY lattice and segment anchor address only",
            "gt_used_for_seed_generation": False,
            "lod2_used_for_seed_generation": False,
            "als_used_for_seed_generation": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        }
        v2_path = seed_dir / f"{building_id}_v2_surface_seed.npz"
        common.atomic_deterministic_npz(
            v2_path,
            {
                "metadata_json": np.asarray(
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                ),
                "rgb": v1_rgb,
                "sem": v1_sem,
                "xyz": xyz,
            },
        )
        loaded = load_surface_seed_npz(v2_path)
        if (
            not np.array_equal(loaded.xyz, xyz)
            or not np.array_equal(loaded.rgb, v1_rgb)
            or not np.array_equal(loaded.sem, v1_sem)
        ):
            raise RuntimeError(f"V2 engine loader round-trip mismatch: {building_id}")
        v2_paths.append(v2_path)
        v2_records[short] = {
            "building_id": building_id,
            "variant": "V2",
            "fit_rule": seed_cfg["v2_fit_rule"],
            "v1_seed_npz": common.rel(v1_path),
            "v1_seed_sha256": common.sha256_file(v1_path),
            "segment_anchor_csv": common.rel(anchor_path),
            "segment_anchor_sha256": common.sha256_file(anchor_path),
            "segment_anchor_records": segment_rows,
            "anchor_count": int(len(anchors)),
            "anchor_z_median_local_m": float(np.median(anchors[:, 2])),
            "anchor_rms_m": anchor_rms,
            "plane_ax_by_c": plane.tolist(),
            "seed_count": int(len(xyz)),
            "planned_init_opacity": float(seed_cfg["planned_init_opacity"]),
            "current_loader_surface_opacity_observed": float(loaded.init_opacity[0]),
            "seed_npz": common.rel(v2_path),
            "seed_npz_sha256": common.sha256_file(v2_path),
            "seed_xyz_payload_sha256": payload_sha256(xyz),
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        }

    # Score phase begins after all V2 NPZ files pass the engine loader.
    roofs = common.load_lod2_roofs(sources["lod2_dir"], lock["targets"])
    projection = json.loads(sources["projection_datum"].read_text(encoding="utf-8"))
    geoid_m = float(projection["orthometric_geoid_m"])
    score_only_sources = {
        sources["projection_datum"],
        *sorted(sources["lod2_dir"].glob("*.gml")),
    }
    score_rows: list[dict[str, Any]] = []
    figure_paths: list[Path] = []
    for short in lock["targets"]:
        building_id = common.full_id(short)
        lattice = np.asarray(p0[f"{building_id}_local_xyz"], dtype=np.float64)
        fm_points = np.asarray(p0[f"{building_id}_fm_local_xyz"], dtype=np.float64)
        v1_path = seed_dir / f"{building_id}_v1_surface_seed.npz"
        v2_path = seed_dir / f"{building_id}_v2_surface_seed.npz"
        with np.load(v1_path, allow_pickle=False) as archive:
            v1_xyz = np.asarray(archive["xyz"], dtype=np.float64)
            v1_metadata = json.loads(str(archive["metadata_json"].item()))
        with np.load(v2_path, allow_pickle=False) as archive:
            v2_xyz = np.asarray(archive["xyz"], dtype=np.float64)
            v2_metadata = json.loads(str(archive["metadata_json"].item()))
        xy_local = lattice[:, :2]
        xy_utm = xy_local + offset[None, :2]
        reference_z = (
            common.reference_roof_z(xy_utm, roofs[short], geoid_m) - offset[2]
        )
        variants = {
            "P0": {
                "xyz": lattice,
                "role": "existing FM fitted-plane seed",
                "plane": plane_from_xyz(lattice),
                "direction_source": "existing_p0_fm_fitted_plane",
                "direction_views": [],
                "height_anchor_source": "existing P0 FM fitted-plane",
                "height_anchor_count": int(fm[short]["inside_point_count"]),
                "height_anchor_z": float(fm[short]["inside_z_median_local_m"]),
                "seed_path": sources["phase1_seed_root"] / f"{building_id}_p0_surface_seed.npz",
                "offset_xy": offset[:2],
            },
            "V1": {
                "xyz": v1_xyz,
                "role": "P0-prime V1 virtual seed",
                "plane": np.asarray(
                    [
                        v1_metadata["plane_ax_local"],
                        v1_metadata["plane_by_local"],
                        v1_metadata["plane_c_local"],
                    ],
                    dtype=np.float64,
                ),
                "direction_source": v1_metadata["lineage"]["direction_source"],
                "direction_views": list(v1_metadata["lineage"]["direction_views"]),
                "height_anchor_source": v1_metadata["height_anchor_source"],
                "height_anchor_count": int(v1_metadata["height_anchor_count"]),
                "height_anchor_z": float(v1_metadata["height_anchor_z_median_local_m"]),
                "seed_path": v1_path,
                "offset_xy": offset[:2],
            },
            "V2": {
                "xyz": v2_xyz,
                "role": "P0-prime V2 virtual seed",
                "plane": np.asarray(
                    [
                        v2_metadata["plane_ax_local"],
                        v2_metadata["plane_by_local"],
                        v2_metadata["plane_c_local"],
                    ],
                    dtype=np.float64,
                ),
                "direction_source": "V1 centroid plus h-sweep segment-anchor plane fit",
                "direction_views": list(v1_metadata["lineage"]["direction_views"]),
                "height_anchor_source": v2_metadata["height_anchor_source"],
                "height_anchor_count": int(v2_metadata["height_anchor_count"]),
                "height_anchor_z": float(v2_metadata["height_anchor_z_median_local_m"]),
                "seed_path": v2_path,
                "offset_xy": offset[:2],
            },
        }
        score_rows.extend(
            score_variant_rows(
                lock=lock,
                building_id=building_id,
                short=short,
                variants=variants,
                xy_local=xy_local,
                reference_z=reference_z,
                footprint=footprints[building_id],
                fm_points=fm_points,
                fm_summary=fm[short],
            )
        )
        figure_path = figure_dir / f"{building_id}_v1_v2_score.png"
        plot_seed_scores_v2(
            figure_path,
            building_id,
            footprints[building_id],
            offset,
            xy_local,
            reference_z,
            lattice[:, 2],
            v1_xyz[:, 2],
            v2_xyz[:, 2],
            fm_points[:, :2],
        )
        figure_paths.append(figure_path)

    common.atomic_csv(outputs["seed_score_csv"], score_rows, SCORE_FIELDS)
    output_paths = [outputs["seed_score_csv"], *v2_paths, *figure_paths]
    manifest = {
        "schema": "jointbuildgs.s3b0.virtual_seed.v2",
        "created_utc": common.now(),
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "crs": lock["crs"],
        "variant": "V2",
        "generation_contract": {
            "fit_rule": seed_cfg["v2_fit_rule"],
            "peak_condition": "all four GT-free segment rows carry a positive-peak class",
            "xy_lattice": "V1 XY copied exactly",
            "planned_init_opacity": float(seed_cfg["planned_init_opacity"]),
            "current_loader_surface_opacity_observed": 0.10,
            "required_npz_keys": seed_cfg["required_npz_keys"],
        },
        "seed_records": v2_records,
        "score_contract": {
            "variants": ["P0", "V1", "V2"],
            "reference": "CityGML LoD2 RoofSurface plus configured orthometric geoid",
            "scopes": ["overall", "edge<=1m", "interior>1m"],
            "far_field_target": "4907199",
            "far_field_distance": "nearest footprint-inside FM anchor XY",
            "far_field_bins_m": seed_cfg["far_field_distance_bins_m"],
            "delta_definition": "variant metric minus P0 metric for the identical scope",
        },
        "counts": {
            "seed_artifacts": len(v2_paths),
            "score_rows": len(score_rows),
            "figures": len(figure_paths),
        },
        "gt_boundary": {
            "generation_input": common.rel(anchor_path),
            "generation_input_gt_flags": {
                "gt_used": False,
                "lod2_used": False,
                "als_used": False,
            },
            "score_gt_used": True,
            "score_lod2_used": True,
            "score_als_used": False,
            "ordering": "all V2 NPZ files written and engine-validated before reference load",
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "generation_source_sha256": common.source_hashes(generation_sources),
        "score_only_source_sha256": common.source_hashes(score_only_sources),
        "output_sha256": common.source_hashes(output_paths),
    }
    v2_manifest_path = run_dir / "v2_manifest.json"
    common.atomic_json(v2_manifest_path, manifest)
    bundle = {
        "schema": "jointbuildgs.s3b0.virtual_seed.bundle.v1",
        "created_utc": common.now(),
        "v1_manifest": common.rel(v1_manifest_path),
        "v1_manifest_sha256": common.sha256_file(v1_manifest_path),
        "v2_manifest": common.rel(v2_manifest_path),
        "v2_manifest_sha256": common.sha256_file(v2_manifest_path),
        "score_csv": common.rel(outputs["seed_score_csv"]),
        "score_csv_sha256": common.sha256_file(outputs["seed_score_csv"]),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    common.atomic_json(run_dir / "manifest.json", bundle)
    print(
        json.dumps(
            {
                "status": "measured",
                "seed_artifacts": len(v2_paths),
                "score_rows": len(score_rows),
                "figures": len(figure_paths),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=common.DEFAULT_LOCK)
    parser.add_argument("--variant", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()
    if args.variant == "v1":
        run_v1(args)
    else:
        run_v2(args)


if __name__ == "__main__":
    main()
