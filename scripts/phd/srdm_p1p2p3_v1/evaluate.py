"""Reference-only SRDM development evaluation, after all nine candidates are sealed.

Distances are discrepancies to a sampled UAS reference, not correctness labels.
No metric, reference point, or evaluation mask is returned to matching.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import scipy
from scipy.spatial import cKDTree

ARMS = ("SRDM_IMAGE_ONLY", "SRDM_FILTER_OFF", "SRDM_NATIVE")
REGIONS = ("P1", "P2", "P3")
LIMITATIONS = (
    "Development cases only; scientific_verdict remains null. Distances measure native point "
    "discrepancy, not calibrated absolute accuracy or source correctness. UAS header EPSG:32632 "
    "versus working EPSG:25832 datum/epoch interpretation is unresolved; no new registration "
    "or reprojection is applied. Missing UAS points do not distinguish occlusion, empty space, "
    "reference absence, or crop boundaries. XY-cell support is an evaluation support proxy, "
    "not visibility or validity. Native point density affects nearest-neighbor distances; "
    "voxel sensitivity and cell-median heights are auxiliary results only. No GS PSNR, "
    "SSIM, LPIPS, LoD2 usability, or change labels are inferred."
)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def load_npz(path):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def xyz(value, name):
    value = np.asarray(value, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3 or not np.isfinite(value).all():
        raise ValueError(f"Invalid finite Nx3 point array: {name}")
    return value


def roi_mask(points, domain):
    lower, upper = np.array(domain["bbox_min"]), np.array(domain["bbox_max"])
    if lower.shape != (3,) or upper.shape != (3,) or np.any(upper <= lower):
        raise ValueError("Invalid half-open ROI")
    return np.all((points >= lower) & (points < upper), axis=1)


def nearest(source, target, workers):
    if not len(source):
        return np.empty(0, dtype=np.float64)
    if not len(target):
        return np.full(len(source), np.inf)
    return cKDTree(target).query(source, k=1, workers=workers)[0]


def distribution(values, thresholds, reference_available=True):
    values = np.asarray(values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    result = {"n_total": int(len(values)), "n_finite": int(len(finite)),
              "reference_status": "AVAILABLE" if reference_available else "REFERENCE_ABSENT",
              "n_without_target": int(np.isinf(values).sum())}
    result.update({key: None for key in ("mean_m", "rmse_m", "median_m", "p90_m", "p95_m", "p99_m", "max_m")})
    if len(finite) and reference_available:
        result.update(mean_m=float(finite.mean()), rmse_m=float(np.sqrt(np.mean(finite ** 2))),
                      median_m=float(np.median(finite)), p90_m=float(np.quantile(finite, .9)),
                      p95_m=float(np.quantile(finite, .95)), p99_m=float(np.quantile(finite, .99)),
                      max_m=float(finite.max()))
    result["fraction_within_m"] = {str(t): float(np.mean(values <= t)) if len(values) and reference_available else None for t in thresholds}
    return result


def cell_ids(points, domain, cell):
    lower, upper = np.array(domain["bbox_min"]), np.array(domain["bbox_max"])
    width = int(np.ceil((upper[0] - lower[0]) / cell))
    ij = np.floor((points[:, :2] - lower[:2]) / cell).astype(np.int64)
    return ij[:, 1] * width + ij[:, 0]


def cell_medians(points, ids):
    if not len(points):
        return {}
    order = np.argsort(ids, kind="stable")
    unique, starts = np.unique(ids[order], return_index=True)
    stops = np.r_[starts[1:], len(ids)]
    return {int(key): float(np.median(points[order[start:stop], 2]))
            for key, start, stop in zip(unique, starts, stops)}


def voxel_representatives(points, size, origin):
    """Retain one original point per voxel; never use centroids as native evidence."""
    if not len(points):
        return points
    ijk = np.floor((points - origin) / size).astype(np.int64)
    _, indices = np.unique(ijk, axis=0, return_index=True)
    return points[np.sort(indices)]


def interpolation_flags(payload, n):
    if "point_interpolated" in payload:
        flags = np.asarray(payload["point_interpolated"], dtype=bool)
    else:
        mask = np.asarray(payload["interpolated_mask"], dtype=bool)
        if mask.ndim != 2:
            raise ValueError("interpolated_mask must be a two-dimensional raster")
        uv = np.asarray(payload["pixel_uv"])
        if uv.shape != (n, 2) or not np.isfinite(uv).all() or not np.equal(uv, np.rint(uv)).all():
            raise ValueError("result pixel_uv must be integer Nx2 in u,v order")
        uv = uv.astype(np.int64)
        if np.any(uv < 0) or np.any(uv[:, 0] >= mask.shape[1]) or np.any(uv[:, 1] >= mask.shape[0]):
            raise ValueError("Point pixel_uv outside interpolated_mask")
        if "valid" in payload:
            valid = np.asarray(payload["valid"], dtype=bool)
            if valid.shape != mask.shape or not valid[uv[:, 1], uv[:, 0]].all():
                raise ValueError("Point pixel_uv must address a valid disparity pixel")
        if "disparity" in payload:
            disparity = np.asarray(payload["disparity"])
            if disparity.shape != mask.shape or not np.isfinite(disparity[uv[:, 1], uv[:, 0]]).all():
                raise ValueError("Point pixel_uv must address a finite disparity")
        flags = mask[uv[:, 1], uv[:, 0]]
    if flags.shape != (n,):
        raise ValueError("Interpolation membership is not point aligned")
    return flags


def gz_csv(path, header, rows):
    with gzip.open(path, "xt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def seal_gate(run_root, seal_path):
    seal = read_json(seal_path)
    if seal.get("scientific_verdict", "missing") is not None or seal.get("reference_accessed") is not False:
        raise ValueError("Null-verdict, reference-free candidate seal required")
    outputs = seal["outputs"]
    required = {f"{rid}/{name}" for rid in REGIONS
                for name in ["pair.npz", "decision.npz", *[f"{arm}/result.npz" for arm in ARMS]]}
    if not required.issubset(outputs):
        raise ValueError(f"Incomplete three-region seal: {sorted(required - set(outputs))}")
    verified = {}
    for name, expected in outputs.items():
        path = (run_root / name).resolve()
        if not path.is_relative_to(run_root.resolve()):
            raise ValueError("Candidate seal path escapes run root")
        expected = expected["sha256"] if isinstance(expected, dict) else expected
        actual = sha(path)
        if actual != expected:
            raise ValueError(f"Candidate hash mismatch: {name}")
        verified[name] = actual
    return {"status": "PASS_ALL_CANDIDATES_VERIFIED_BEFORE_REFERENCE", "reference_accessed": False,
            "scientific_verdict": None, "seal_sha256": sha(seal_path), "outputs": verified}


def evaluate_region(run_root, region, cfg, output):
    rid = region["id"]
    directory = output / rid
    directory.mkdir()
    domain, cell = region["domain"], float(cfg["xy_cell_m"])
    thresholds, workers = cfg["distance_thresholds_m"], int(cfg.get("workers", 4))
    pair = load_npz(run_root / rid / "pair.npz")
    for key in ("bbox_min", "bbox_max"):
        if key in pair and not np.allclose(pair[key], domain[key], rtol=0, atol=1e-8):
            raise ValueError(f"Candidate/reference ROI mismatch: {rid}/{key}")
    reference_path = Path(region["frozen_reference_npz"])
    if sha(reference_path) != region["frozen_reference_sha256"]:
        raise ValueError(f"Reference hash mismatch: {rid}")
    reference_payload = load_npz(reference_path)
    reference = xyz(reference_payload["uas_xyz"], rid + "/UAS")
    reference = reference[roi_mask(reference, domain)]
    summarize = lambda values: distribution(values, thresholds, reference_available=bool(len(reference)))
    ref_ids = cell_ids(reference, domain, cell)
    ref_cells = np.unique(ref_ids)
    clouds, interpolation, native_indices = {}, {}, {}
    for arm in ARMS:
        payload = load_npz(run_root / rid / arm / "result.npz")
        points = xyz(payload["xyz"], arm)
        colors = np.asarray(payload["rgb"])
        if colors.shape != points.shape or colors.dtype != np.uint8:
            raise ValueError(f"RGB must be point-aligned uint8: {rid}/{arm}")
        flags = interpolation_flags(payload, len(points))
        valid = roi_mask(points, domain)
        clouds[arm], interpolation[arm], native_indices[arm] = points[valid], flags[valid], np.flatnonzero(valid)
    common_cells = ref_cells.copy()
    for points in clouds.values():
        common_cells = np.intersect1d(common_cells, cell_ids(points, domain, cell))
    ref_common = reference[np.isin(ref_ids, common_cells)]
    result = {"id": rid, "status": "MEASURED" if len(reference) else "REFERENCE_EMPTY",
              "scientific_verdict": None, "domain": domain, "reference_points": len(reference),
              "reference_path": str(reference_path), "reference_sha256": region["frozen_reference_sha256"],
              "reference_xy_cells": len(ref_cells), "common_all_arm_reference_xy_cells": len(common_cells),
              "common_support_definition": "Half-open fixed ROI; intersection of occupied XY cells of UAS and all three arms; no distance threshold",
              "xy_cell_m": cell, "arms": {}}
    plot_cap = int(cfg.get("display_max_points", 200000))
    display_ids = np.arange(len(reference))[::max(1, int(np.ceil(len(reference) / plot_cap)))]
    center = (np.array(domain["bbox_min"]) + np.array(domain["bbox_max"])) / 2
    half_width = float(cfg.get("section_half_width_m", .25))
    np.savez_compressed(directory / "reference_display.npz", xyz=reference[display_ids], source_index=display_ids,
                        section_x=reference[np.abs(reference[:, 0] - center[0]) <= half_width],
                        section_y=reference[np.abs(reference[:, 1] - center[1]) <= half_width])
    summaries = []
    for arm, points in clouds.items():
        adir = directory / arm
        adir.mkdir()
        forward = nearest(points, reference, workers)
        backward = nearest(reference, points, workers)
        ids = cell_ids(points, domain, cell)
        common = np.isin(ids, common_cells)
        original = ~interpolation[arm]
        measurements = {"native": {"candidate_to_reference": summarize(forward),
                                   "reference_to_candidate": summarize(backward)},
                        "original_points_only": {
                            "candidate_to_reference": summarize(forward[original]),
                            "reference_to_candidate": summarize(nearest(reference, points[original], workers))},
                        "common_xy_support": {
                            "candidate_to_reference": summarize(nearest(points[common], ref_common, workers)),
                            "reference_to_candidate": summarize(nearest(ref_common, points[common], workers))}}
        density = {}
        for size in cfg.get("density_voxel_m", [.1, .25, .5]):
            reduced = voxel_representatives(points, float(size), np.array(domain["bbox_min"]))
            reduced_ref = voxel_representatives(reference, float(size), np.array(domain["bbox_min"]))
            density[str(size)] = {"role": "AUXILIARY_DENSITY_SENSITIVITY_ONE_ORIGINAL_POINT_PER_VOXEL",
                                  "candidate_to_reference": summarize(nearest(reduced, reduced_ref, workers)),
                                  "reference_to_candidate": summarize(nearest(reduced_ref, reduced, workers))}
        status = "REFERENCE_ABSENT" if not len(reference) else "EMPTY_PREDICTION" if not len(points) else "MEASURED"
        result["arms"][arm] = {"status": status, "native_points_in_roi": len(points), "original_points": int(original.sum()),
                               "interpolated_points": int(interpolation[arm].sum()), "occupied_xy_cells": len(np.unique(ids)),
                               "reference_xy_supported_candidate_points": int(np.isin(ids, ref_cells).sum()),
                               "measurements": measurements, "density_sensitivity": density}
        np.savez_compressed(adir / "native_distances.npz", candidate_source_index=native_indices[arm],
                            candidate_to_reference=forward, reference_to_candidate=backward,
                            interpolated=interpolation[arm], common_xy_support=common)
        gz_csv(adir / "candidate_distances.csv.gz", ["result_row", "x", "y", "z", "distance_to_reference_m", "interpolated", "common_xy_support"],
               ((int(index), *point, float(dist), int(interp), int(shared)) for index, point, dist, interp, shared in
                zip(native_indices[arm], points, forward, interpolation[arm], common)))
        gz_csv(adir / "reference_distances.csv.gz", ["cropped_reference_row", "x", "y", "z", "distance_to_candidate_m"],
               ((i, *point, float(dist)) for i, (point, dist) in enumerate(zip(reference, backward))))
        for support, both in measurements.items():
            for direction, stats in both.items():
                summaries.append({"region": rid, "arm": arm, "support": support, "direction": direction,
                                  **{k: v for k, v in stats.items() if k != "fraction_within_m"},
                                  **{f"fraction_le_{key}m": value for key, value in stats["fraction_within_m"].items()}})
    medians = {"UAS": cell_medians(reference, ref_ids)}
    medians.update({arm: cell_medians(points, cell_ids(points, domain, cell)) for arm, points in clouds.items()})
    all_cells = sorted(set().union(*(set(values) for values in medians.values())))
    width = int(np.ceil((domain["bbox_max"][0] - domain["bbox_min"][0]) / cell))
    common_set = set(common_cells.tolist())
    grid_rows = []
    for key in all_cells:
        values = [medians[name].get(key) for name in ("UAS", *ARMS)]
        residuals = [value - values[0] if value is not None and values[0] is not None else None for value in values[1:]]
        grid_rows.append([key, domain["bbox_min"][0] + (key % width + .5) * cell,
                          domain["bbox_min"][1] + (key // width + .5) * cell, int(key in common_set), *values, *residuals])
    gz_csv(directory / "height_grid_auxiliary.csv.gz", ["cell_id", "x", "y", "common_all_arm_support", "UAS_median_z", *[a + "_median_z" for a in ARMS], *[a + "_signed_dz" for a in ARMS]], grid_rows)
    result["height_grid_auxiliary"] = {"role": "AUXILIARY_EQUAL_CELL_WEIGHT_MEDIAN_HEIGHT_NOT_NATIVE_SURFACE", "arms": {}}
    for arm in ARMS:
        differences = np.array([medians[arm][key] - medians["UAS"][key] for key in common_cells])
        result["height_grid_auxiliary"]["arms"][arm] = {"absolute_dz": summarize(np.abs(differences)),
                                                            "mean_signed_dz_m": float(differences.mean()) if len(differences) else None}
    decision = load_npz(run_root / rid / "decision.npz")
    prior = xyz(decision["als_xyz"], "decision ALS")
    states = {name: np.asarray(decision[name], dtype=bool) for name in ("keep", "rejected", "unassessed")}
    if any(mask.shape != (len(prior),) for mask in states.values()) or not np.all(sum(mask.astype(int) for mask in states.values()) == 1):
        raise ValueError("Decision states must partition every original ALS row exactly once")
    source_rows = np.asarray(decision["source_row"])
    if source_rows.shape != (len(prior),):
        raise ValueError("ALS source_row must be point aligned")
    if "als_xyz" in pair and not np.array_equal(np.asarray(pair["als_xyz"]), prior):
        raise ValueError("Decision ALS coordinates differ from the preserved pair input")
    if "als_source_row" in pair and not np.array_equal(pair["als_source_row"], source_rows):
        raise ValueError("Decision source membership differs from the preserved pair input")
    source_files = np.asarray(decision.get("source_file_index", pair.get("als_source_file_index", np.full(len(prior), -1))))
    if source_files.shape != source_rows.shape:
        raise ValueError("ALS source file indices must be point aligned")
    in_roi = roi_mask(prior, domain)
    distances = np.full(len(prior), np.nan)
    distances[in_roi] = nearest(prior[in_roi], reference, workers)
    supported = np.zeros(len(prior), dtype=bool)
    supported[in_roi] = np.isin(cell_ids(prior[in_roi], domain, cell), ref_cells)
    decision_stats = {"reference_distance_is_not_correctness_label": True, "states": {}}
    for state, mask in states.items():
        selected = mask & in_roi
        decision_stats["states"][state] = {"count_all_input": int(mask.sum()), "count_in_roi": int(selected.sum()),
                                           "reference_xy_supported": int((selected & supported).sum()),
                                           "reference_xy_absent_unknown": int((selected & ~supported).sum()),
                                           "distance_all_roi": summarize(distances[selected]),
                                           "distance_reference_xy_supported": summarize(distances[selected & supported])}
    label = np.full(len(prior), "unassessed", dtype="U10")
    label[states["keep"]], label[states["rejected"]] = "keep", "rejected"
    gz_csv(directory / "als_decision_reference.csv.gz", ["decision_row", "source_file_index", "source_row", "x", "y", "z", "decision", "in_roi", "reference_xy_support", "distance_to_reference_m"],
           ((i, int(source_files[i]), int(source_rows[i]), *point, label[i], int(in_roi[i]), int(supported[i]), float(distances[i])) for i, point in enumerate(prior)))
    np.savez_compressed(directory / "als_decision_reference.npz", distance_to_reference=distances,
                        in_roi=in_roi, reference_xy_support=supported, **states)
    result["decision"] = decision_stats
    write_json(directory / "evaluation.json", result)
    return result, summaries


def run(run_root, config, seal, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run project evaluation in Docker")
    started = time.monotonic()
    cfg = read_json(config)
    if cfg.get("scientific_verdict", "missing") is not None or [r["id"] for r in cfg["regions"]] != list(REGIONS):
        raise ValueError("Null verdict and all three regions in fixed order required")
    if cfg["frame"]["working_crs"] != "EPSG:25832":
        raise ValueError("Working CRS must be explicit EPSG:25832")
    if float(cfg["xy_cell_m"]) <= 0 or any(float(t) <= 0 for t in cfg["distance_thresholds_m"]):
        raise ValueError("Evaluation scales must be positive")
    gate = seal_gate(run_root, seal)
    output.mkdir(parents=True, exist_ok=False)
    gate.update(evaluation_config_sha256=sha(config), evaluator_sha256=sha(__file__))
    write_json(output / "PRE_REFERENCE_GATE.json", gate)
    regions, table = [], []
    for region in cfg["regions"]:
        measured, rows = evaluate_region(run_root, region, cfg, output)
        regions.append(measured)
        table.extend(rows)
    with (output / "metrics.csv").open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    write_json(output / "evaluation.json", {"task_id": cfg.get("task_id", "PHD-SRDM-P1P2P3-EVALUATION-v1"),
               "scientific_verdict": None, "reference_accessed": True, "created_utc": datetime.now(timezone.utc).isoformat(),
               "run_root": str(run_root), "frame": cfg["frame"], "config": cfg, "limitations": LIMITATIONS,
               "regions": regions, "elapsed_seconds": time.monotonic() - started,
               "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
               "gate": gate})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.run_root, args.config, args.seal, args.output)
