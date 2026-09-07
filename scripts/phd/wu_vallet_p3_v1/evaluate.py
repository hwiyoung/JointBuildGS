#!/usr/bin/env python3
"""Post-training P3 reference evaluation; never imported by fitting or judgment.

Fixed scene-local crop, raw UAS minus the recorded world shift, native point
distances, and a fixed XY grid. No fitted registration or error-based filtering.
Run this project tool in Docker. The output directory must not already exist.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import time

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import numpy as np
from scipy.spatial import cKDTree


LOW = np.array([-60.0, -42.0, -49.223], dtype=np.float64)
HIGH = np.array([-20.0, 12.0, -16.993], dtype=np.float64)
SHIFT = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
CELL = 0.5
NX, NY = 80, 108
TOTAL_CELLS = NX * NY
SECTION_HALF_WIDTH = 0.25
DISPLAY_MAX_POINTS = 200_000
UAS_BASENAME = "TUM_Downtown_ULS_20241217_nadir.laz"


def sha256(path: Path) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def source_commit() -> str:
    if os.environ.get("JBGS_SOURCE_GIT_HEAD"):
        return os.environ["JBGS_SOURCE_GIT_HEAD"]
    return subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[3]), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def point_array(value: np.ndarray, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 3 or not np.isfinite(result).all():
        raise ValueError(f"{label}: expected finite Nx3 xyz; invalid values are not discarded")
    return result


def crop(points: np.ndarray) -> tuple[np.ndarray, dict]:
    keep = ((points >= LOW) & (points < HIGH)).all(axis=1)
    return points[keep], {
        "input_points": len(points), "inside_fixed_crop": int(keep.sum()),
        "outside_fixed_crop": int((~keep).sum()),
    }


def summary(values: np.ndarray, signed: bool = False) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if len(values) == 0:
        return {"count": 0, "mean_m": None, "median_m": None, "rmse_m": None,
                "p90_m": None, "p95_m": None, "max_abs_m": None}
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite values cannot be removed from evaluation statistics")
    result = {
        "count": len(values), "mean_m": float(np.mean(values)),
        "median_m": float(np.median(values)),
        "rmse_m": float(np.sqrt(np.mean(values * values))),
        "p90_m": float(np.quantile(values, .9)), "p95_m": float(np.quantile(values, .95)),
        "max_abs_m": float(np.max(np.abs(values))),
    }
    if signed:
        result["min_m"] = float(np.min(values))
        result["max_m"] = float(np.max(values))
        result["mae_m"] = float(np.mean(np.abs(values)))
        result["p90_abs_m"] = float(np.quantile(np.abs(values), .9))
    return result


def median_grid(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    count = np.zeros(TOTAL_CELLS, dtype=np.int64)
    height = np.full(TOTAL_CELLS, np.nan, dtype=np.float64)
    if len(points):
        if not np.isfinite(points).all() or not (((points >= LOW) & (points < HIGH)).all()):
            raise ValueError("XY grid requires finite points inside the fixed half-open crop")
        ij = np.floor((points[:, :2] - LOW[:2]) / CELL).astype(np.int64)
        # A representable point just below HIGH may round to NX/NY after subtraction.
        # Coordinates were checked above; keep that mathematical last-cell membership.
        ij = np.minimum(ij, np.array([NX - 1, NY - 1]))
        ids = ij[:, 1] * NX + ij[:, 0]
        order = np.argsort(ids, kind="stable")
        unique, starts, counts = np.unique(ids[order], return_index=True, return_counts=True)
        count[unique] = counts
        z = points[order, 2]
        for index, start, size in zip(unique, starts, counts):
            height[index] = np.median(z[start:start + size])
    return height.reshape(NY, NX), count.reshape(NY, NX)


def measure(points: np.ndarray, reference: np.ndarray, reference_tree: cKDTree,
            reference_height: np.ndarray, reference_count: np.ndarray) -> tuple[dict, dict]:
    height, count = median_grid(points)
    occupied = count > 0
    ref_occupied = reference_count > 0
    overlap = occupied & ref_occupied
    signed_delta = height[overlap] - reference_height[overlap]
    if len(points):
        to_reference, _ = reference_tree.query(points, workers=4)
        from_reference, _ = cKDTree(points).query(reference, workers=4)
        directed = {
            "prediction_to_reference": summary(to_reference),
            "reference_to_prediction": summary(from_reference),
            "symmetric_mean_distance_m": float((to_reference.mean() + from_reference.mean()) / 2),
            "reference_distance_unavailable_points": 0,
            "within_distance": [
                {"threshold_m": t,
                 "prediction_numerator": int((to_reference <= t).sum()),
                 "prediction_denominator": len(points),
                 "reference_numerator": int((from_reference <= t).sum()),
                 "reference_denominator": len(reference)}
                for t in (0.1, 0.25, 0.5, 1.0)
            ],
        }
    else:
        directed = {
            "prediction_to_reference": summary(np.empty(0)),
            "reference_to_prediction": summary(np.empty(0)),
            "symmetric_mean_distance_m": None,
            "reference_distance_unavailable_points": len(reference),
            "within_distance": [
                {"threshold_m": t, "prediction_numerator": 0, "prediction_denominator": 0,
                 "reference_numerator": 0, "reference_denominator": len(reference)}
                for t in (0.1, 0.25, 0.5, 1.0)
            ],
        }
    grid = {
        "spacing_m": CELL, "fixed_domain_cells": TOTAL_CELLS,
        "prediction_occupied_cells": int(occupied.sum()),
        "prediction_missing_fixed_domain_cells": int((~occupied).sum()),
        "prediction_coverage_fixed_domain": float(occupied.sum() / TOTAL_CELLS),
        "reference_occupied_cells": int(ref_occupied.sum()),
        "reference_missing_fixed_domain_cells": int((~ref_occupied).sum()),
        "matched_reference_cells": int(overlap.sum()),
        "missing_prediction_on_reference_cells": int((ref_occupied & ~occupied).sum()),
        "prediction_cells_without_reference": int((occupied & ~ref_occupied).sum()),
        "prediction_coverage_reference_cells": float(overlap.sum() / ref_occupied.sum()),
        "signed_height_difference_prediction_minus_reference": summary(signed_delta, signed=True),
        "height_difference_denominator": "All cells occupied by both, paired with explicit missing counts",
        "height_statistic": "Median Z of all native points in each fixed XY cell; no top-layer selection",
    }
    delta = np.full_like(height, np.nan)
    delta[overlap] = signed_delta
    return {"native_3d_nearest_distances": directed, "xy_height_grid": grid}, {
        "median_z": height, "count": count, "delta_z": delta,
    }


def header_crs_metadata(header) -> dict:
    """Read GeoTIFF scalar CRS keys without invoking optional pyproj.

    This records header metadata only. It never transforms coordinates or infers a
    vertical datum from a projected CRS code. WKT is retained as a digest rather
    than interpreted by an unavailable projection library.
    """
    keys = {}
    records = []
    vlrs = list(header.vlrs) + list(getattr(header, "evlrs", None) or [])
    for vlr in vlrs:
        if vlr.user_id.lower() != "lasf_projection":
            continue
        payload = vlr.record_data_bytes()
        record_id = int(vlr.record_id)
        records.append({"record_id": record_id, "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()})
        if record_id != 34735:
            continue
        if len(payload) < 8:
            raise ValueError("Truncated GeoKeyDirectory VLR")
        _, _, _, number = struct.unpack_from("<4H", payload, 0)
        if len(payload) < 8 + 8 * number:
            raise ValueError("Truncated GeoKeyDirectory entries")
        for i in range(number):
            key, location, count, value = struct.unpack_from("<4H", payload, 8 + 8 * i)
            if location == 0 and count == 1:
                keys[str(key)] = value
    projected = keys.get("3072")
    return {
        "header_crs": f"EPSG:{projected}" if projected and projected != 32767 else None,
        "header_crs_reading": "GeoKeyDirectory scalar keys, no pyproj or coordinate conversion",
        "header_geokey_scalars": keys,
        "header_projection_vlrs": records,
        "header_vertical_datum_calibrated": False,
    }


def read_reference(path: Path) -> tuple[np.ndarray, dict]:
    chunks = []
    rows = []
    cursor = 0
    with laspy.open(path) as reader:
        total = int(reader.header.point_count)
        crs = header_crs_metadata(reader.header)
        for chunk in reader.chunk_iterator(1_000_000):
            xyz = np.column_stack((chunk.x, chunk.y, chunk.z)).astype(np.float64)
            if not np.isfinite(xyz).all():
                raise ValueError("Raw UAS contains nonfinite coordinates")
            local = xyz - SHIFT
            keep = ((local >= LOW) & (local < HIGH)).all(axis=1)
            chunks.append(local[keep])
            rows.append(np.flatnonzero(keep).astype(np.int64) + cursor)
            cursor += len(xyz)
    if cursor != total:
        raise ValueError("Raw UAS header/read point count mismatch")
    reference = np.concatenate(chunks) if chunks else np.empty((0, 3), dtype=np.float64)
    original_rows = np.concatenate(rows) if rows else np.empty(0, dtype=np.int64)
    if not len(reference):
        raise ValueError("No UAS reference points in fixed P3 domain")
    return reference, {
        "raw_point_count": total, "crop_point_count": len(reference),
        **crs,
        "raw_rows_sha256": hashlib.sha256(original_rows.tobytes()).hexdigest(),
        "raw_rows": original_rows,
        "transform": "raw XYZ minus [690953, 5336071, 604], no registration or extra Z offset",
    }


def save_grid_plot(path: Path, fields: dict[str, np.ndarray], *, difference: bool = False) -> None:
    columns = min(3, len(fields))
    nrows = (len(fields) + columns - 1) // columns
    fig, axes = plt.subplots(nrows, columns, figsize=(5 * columns, 6 * nrows), squeeze=False)
    finite = [g[np.isfinite(g)] for g in fields.values()]
    all_values = np.concatenate(finite) if finite else np.empty(0)
    if difference:
        limit = max(float(np.max(np.abs(all_values))) if len(all_values) else 1, 1e-6)
        lower, upper, cmap = -limit, limit, "coolwarm"
    else:
        lower, upper, cmap = LOW[2], HIGH[2], "viridis"
    for ax, (name, grid) in zip(axes.flat, fields.items()):
        img = ax.imshow(np.ma.masked_invalid(grid), origin="lower",
                        extent=[LOW[0], HIGH[0], LOW[1], HIGH[1]],
                        interpolation="nearest", cmap=cmap, vmin=lower, vmax=upper)
        ax.set(title=name, xlabel="Local X (m)", ylabel="Local Y (m)")
        ax.set_aspect("equal")
        fig.colorbar(img, ax=ax, label="Median Z difference (m)" if difference else "Median local Z (m)")
    for ax in list(axes.flat)[len(fields):]:
        ax.set_visible(False)
    fig.suptitle("Fixed 0.5 m XY cells; white = missing; all finite differences retained" if difference
                 else "Fixed 0.5 m XY median height; white = missing")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_source_map(path: Path, mvs_count: np.ndarray, als_count: np.ndarray) -> None:
    source = (mvs_count > 0).astype(np.uint8) + 2 * (als_count > 0).astype(np.uint8)
    fig, ax = plt.subplots(figsize=(7, 8))
    img = ax.imshow(source, origin="lower", extent=[LOW[0], HIGH[0], LOW[1], HIGH[1]],
                    cmap=ListedColormap(["#eeeeee", "#2185c5", "#e79723", "#8c5dc4"]),
                    norm=BoundaryNorm(np.arange(-.5, 4.5), 4), interpolation="nearest")
    bar = fig.colorbar(img, ax=ax, ticks=[0, 1, 2, 3])
    bar.ax.set_yticklabels(["Neither", "MVS only", "ALS only", "Both"])
    ax.axvline(-40, color="black", linewidth=.7, linestyle="--")
    ax.axhline(-15, color="black", linewidth=.7, linestyle="--")
    ax.set(title="Native source occupancy, not source authority", xlabel="Local X (m)", ylabel="Local Y (m)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_native_3d(path: Path, clouds: dict[str, np.ndarray]) -> dict:
    columns = min(3, len(clouds))
    nrows = (len(clouds) + columns - 1) // columns
    fig = plt.figure(figsize=(6 * columns, 5 * nrows))
    display = {}
    for number, (name, xyz) in enumerate(clouds.items(), 1):
        stride = max(1, int(np.ceil(len(xyz) / DISPLAY_MAX_POINTS)))
        shown = xyz[::stride]
        display[name] = {"native_count": len(xyz), "display_count": len(shown), "stride": stride}
        ax = fig.add_subplot(nrows, columns, number, projection="3d")
        ax.scatter(shown[:, 0], shown[:, 1], shown[:, 2], c=shown[:, 2], s=.2,
                   cmap="viridis", vmin=LOW[2], vmax=HIGH[2], rasterized=True)
        ax.set(xlim=(LOW[0], HIGH[0]), ylim=(LOW[1], HIGH[1]), zlim=(LOW[2], HIGH[2]),
               xlabel="Local X (m)", ylabel="Local Y (m)", zlabel="Local Z (m)", title=name)
        ax.set_box_aspect(HIGH - LOW)
        ax.view_init(elev=25, azim=-55)
    fig.suptitle("Native-source 3D points; display stride only; metrics use all cropped points")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return display


def save_sections(path: Path, clouds: dict[str, np.ndarray]) -> dict:
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    counts = {}
    for name, xyz in clouds.items():
        in_x = (xyz[:, 0] >= -40 - SECTION_HALF_WIDTH) & (xyz[:, 0] < -40 + SECTION_HALF_WIDTH)
        in_y = (xyz[:, 1] >= -15 - SECTION_HALF_WIDTH) & (xyz[:, 1] < -15 + SECTION_HALF_WIDTH)
        axes[0].scatter(xyz[in_x, 1], xyz[in_x, 2], s=1, label=name, alpha=.6, rasterized=True)
        axes[1].scatter(xyz[in_y, 0], xyz[in_y, 2], s=1, label=name, alpha=.6, rasterized=True)
        counts[name] = {"x_minus_40": int(in_x.sum()), "y_minus_15": int(in_y.sum())}
    axes[0].set(title="X = -40 m, width 0.5 m, half-open", xlabel="Local Y (m)", xlim=(LOW[1], HIGH[1]))
    axes[1].set(title="Y = -15 m, width 0.5 m, half-open", xlabel="Local X (m)", xlim=(LOW[0], HIGH[0]))
    for ax in axes:
        ax.set(ylabel="Local Z (m)", ylim=(LOW[2], HIGH[2]))
        ax.grid(alpha=.2)
        ax.legend(fontsize=7, markerscale=3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return counts


def main(common: Path, b_root: Path, config_path: Path, output: Path) -> None:
    started = time.monotonic()
    config = json.loads(config_path.read_text())
    if config.get("schema") != "jointbuildgs.phd.wu_vallet_p3.reference_evaluation.config.v1":
        raise ValueError("Evaluation config schema mismatch")
    if config.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must be null")
    if common.resolve() != Path(config["expected_common"]).resolve():
        raise ValueError("Evaluation common input path differs from the frozen config")
    if b_root.resolve() != Path(config["expected_b_root"]).resolve():
        raise ValueError("Evaluation B root differs from the frozen config")
    configured_bounds = np.array([config["crop"][axis] for axis in ("x", "y", "z")], dtype=float)
    if not np.array_equal(configured_bounds, np.column_stack((LOW, HIGH))):
        raise ValueError("P3 crop does not match frozen half-open domain")
    reference_cfg = config["reference"]
    if reference_cfg.get("additional_vertical_shift_m") != 0:
        raise ValueError("Additional UAS vertical correction is prohibited")
    if config.get("xy_cell_m") != CELL or config.get("xy_total_cells") != TOTAL_CELLS:
        raise ValueError("Fixed XY evaluation grid mismatch")
    if config.get("sections") != {"x_m": -40.0, "y_m": -15.0, "width_m": .5, "membership": "half-open"}:
        raise ValueError("Fixed cross-section definition mismatch")
    if not np.array_equal(np.asarray(reference_cfg["world_shift_xyz"], dtype=float), SHIFT):
        raise ValueError("UAS world shift mismatch")
    reference_path = Path(reference_cfg["path"])
    if reference_path.name != UAS_BASENAME:
        raise ValueError("Unexpected UAS reference filename")
    # This gate is checked before opening the evaluation-only reference.
    b_result_path = b_root / "result.json"
    b_result = json.loads(b_result_path.read_text())
    required_status = config.get("b_completion_status", "B_RECONSTRUCTION_COMPLETE")
    if b_result.get("status") != required_status or b_result.get("scientific_verdict", "missing") is not None:
        raise ValueError("B completion receipt is absent, incomplete, or not scientific_verdict:null")
    arms = [row["arm"] if isinstance(row, dict) else row for row in b_result["arms"]]
    if not arms or len(set(arms)) != len(arms):
        raise ValueError("B result must declare unique completed arms")
    for arm in arms:
        if not isinstance(arm, str) or Path(arm).name != arm or arm in {".", "..", "MVS", "ALS", "UAS"}:
            raise ValueError("Invalid or reserved arm name")
    input_paths = [config_path, common, b_result_path]
    for arm in arms:
        input_paths.extend([b_root / arm / "extracted_surface.npz",
                            b_root / arm / "initial" / "extracted_surface.npz"])
    input_hashes = {str(path): sha256(path) for path in input_paths}
    if reference_path.stat().st_size != reference_cfg["bytes"]:
        raise ValueError("Raw UAS byte count mismatch")
    reference_hash = sha256(reference_path)
    if reference_hash != reference_cfg["sha256"]:
        raise ValueError("Raw UAS checksum mismatch")
    reference_stat = (reference_path.stat().st_size, reference_path.stat().st_mtime_ns)
    output.mkdir(parents=True, exist_ok=False)
    try:
        with np.load(common, allow_pickle=False) as native:
            clouds = {name: point_array(native[f"{name.lower()}_xyz"], name) for name in ("MVS", "ALS")}
            membership = {}
            for name in ("MVS", "ALS"):
                rows = native[f"{name.lower()}_tile_rows"]
                if rows.ndim != 1 or len(rows) != len(clouds[name]):
                    raise ValueError("Native source membership length mismatch")
                membership[name] = {"rows": len(rows), "sha256": hashlib.sha256(np.ascontiguousarray(rows).tobytes()).hexdigest()}
        for arm in arms:
            with np.load(b_root / arm / "initial" / "extracted_surface.npz", allow_pickle=False) as surface:
                clouds[f"{arm}__initial"] = point_array(surface["xyz"], f"{arm} initial")
            with np.load(b_root / arm / "extracted_surface.npz", allow_pickle=False) as surface:
                clouds[arm] = point_array(surface["xyz"], arm)
        crop_counts = {}
        for name in clouds:
            clouds[name], crop_counts[name] = crop(clouds[name])
        reference, reference_meta = read_reference(reference_path)
        if reference_meta["raw_point_count"] != reference_cfg["point_count"]:
            raise ValueError("Raw UAS point count mismatch")
        raw_rows = reference_meta.pop("raw_rows")
        np.savez_compressed(output / "evaluation_reference.npz", uas_xyz=reference, uas_raw_rows=raw_rows)
        reference_height, reference_count = median_grid(reference)
        reference_tree = cKDTree(reference)
        metrics, fields = {}, {}
        for name, points in clouds.items():
            metrics[name], fields[name] = measure(points, reference, reference_tree, reference_height, reference_count)
            metrics[name]["crop_counts"] = crop_counts[name]
            print(json.dumps({"arm": name, "crop_points": len(points),
                              "coverage_reference_cells": metrics[name]["xy_height_grid"]["prediction_coverage_reference_cells"]}), flush=True)
        save_source_map(output / "source_occupancy.png", fields["MVS"]["count"], fields["ALS"]["count"])
        save_grid_plot(output / "median_heights.png", {"UAS reference": reference_height,
                                                      **{name: field["median_z"] for name, field in fields.items()}})
        save_grid_plot(output / "height_differences.png", {name: field["delta_z"] for name, field in fields.items()}, difference=True)
        display_clouds = {"UAS": reference, **clouds}
        display = save_native_3d(output / "native_3d.png", display_clouds)
        section_counts = save_sections(output / "cross_sections.png",
                                       {"UAS": reference, **{name: xyz for name, xyz in clouds.items() if not name.endswith("__initial")}})
        arm_comparisons = {}
        for arm in arms:
            initial = fields[f"{arm}__initial"]
            final = fields[arm]
            initial_exists, final_exists = initial["count"] > 0, final["count"] > 0
            common_cells = initial_exists & final_exists
            triple_cells = common_cells & (reference_count > 0)
            arm_comparisons[arm] = {
                "initial_method_key": f"{arm}__initial", "final_method_key": arm,
                "initial_final_common_cells": int(common_cells.sum()),
                "initial_final_and_reference_common_cells": int(triple_cells.sum()),
                "lost_initial_cells": int((initial_exists & ~final_exists).sum()),
                "gained_final_cells": int((~initial_exists & final_exists).sum()),
                "final_minus_initial_height_on_common_cells": summary(
                    final["median_z"][common_cells] - initial["median_z"][common_cells], signed=True),
                "initial_reference_error_on_triple_common_cells": summary(
                    initial["median_z"][triple_cells] - reference_height[triple_cells], signed=True),
                "final_reference_error_on_triple_common_cells": summary(
                    final["median_z"][triple_cells] - reference_height[triple_cells], signed=True),
            }
            save_sections(output / f"cross_sections_{arm}.png", {
                "UAS": reference, "MVS": clouds["MVS"], "ALS": clouds["ALS"],
                f"{arm} initial": clouds[f"{arm}__initial"], f"{arm} final": clouds[arm],
            })
        np.savez_compressed(output / "fixed_grid.npz", reference_median_z=reference_height,
                            reference_count=reference_count,
                            **{f"{name}__{field}": value for name, item in fields.items() for field, value in item.items()})
        if any(sha256(path) != expected for path, expected in input_hashes.items()):
            raise ValueError("Evaluation input changed during evaluation")
        if (reference_path.stat().st_size, reference_path.stat().st_mtime_ns) != reference_stat:
            raise ValueError("Raw UAS file metadata changed during evaluation")
        write_json(output / "evaluation.json", {
            "schema": "jointbuildgs.phd.wu_vallet_p3.reference_evaluation.v1",
            "task_id": config["task_id"],
            "status": "REFERENCE_ONLY_DEVELOPMENT_EVALUATION_COMPLETE",
            "scientific_verdict": None, "created_utc": datetime.now(timezone.utc).isoformat(),
            "input_hashes": {**input_hashes, str(reference_path): reference_hash},
            "source_hashes": {str(Path(__file__)): sha256(Path(__file__))},
            "source_git_commit": source_commit(),
            "tool_versions": {"python": platform.python_version(),
                              **{name: version(name) for name in ("numpy", "scipy", "laspy", "matplotlib")}},
            "b_completion_status": required_status, "native_source_membership": membership,
            "coordinates": {"frame": "SCENE_LOCAL_XYZ", "horizontal_crs": "EPSG:25832",
                            "world_shift_xyz": SHIFT.tolist()},
            "crop": {axis: [float(LOW[i]), float(HIGH[i])] for i, axis in enumerate(("x", "y", "z"))},
            "crop_membership": "half-open on all axes, fixed before reference observation",
            "reference": reference_meta, "methods": metrics, "own_initial_final_comparisons": arm_comparisons,
            "display_only_sampling": display, "section_point_counts": section_counts,
            "elapsed_seconds": time.monotonic() - started,
            "limits": [
                "UAS datum, epoch and measurement precision are not newly calibrated; numerical common-frame discrepancy only.",
                "Evaluation-only raw UAS is read after the B completion receipt; no fitted registration, oracle filtering or training feedback.",
                "All finite native points in the frozen crop enter nearest-distance metrics; no distance cutoff discards large errors.",
                "Fixed crop exclusions are reported separately and are not evidence of full-scene accuracy.",
                "Median XY height is a 2.5D diagnostic; overhangs, walls and thin features can share one cell.",
                "Missing cells remain in fixed-domain and reference-occupied accounting; height error is measured only where both exist.",
                "Source occupancy describes provenance, not currentness, reliability or source authority.",
                "3D figure subsampling is display-only; image-like scatter and grid plots are not camera renders.",
            ],
        })
    except Exception as error:
        write_json(output / "failure.json", {"status": "FAILED", "error": str(error),
                                             "exception": type(error).__name__, "scientific_verdict": None})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common", type=Path, required=True)
    parser.add_argument("--b-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.common, args.b_root, args.config, args.output)
