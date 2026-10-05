"""Recover and audit estimated ALS origins from immutable multi-return pulses."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import time
import traceback

import numpy as np
import scipy

from src.phd.wu_vallet_p3_v2.trajectory import (
    ROLE, TrajectoryConfig, fit_trajectory_window, json_safe, predict_origins,
)


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(json_safe(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def record(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def sample_longest_pulses(times, separation, rows, interval):
    if len(rows) == 0:
        return rows
    bins = np.floor((times[rows] - times[rows].min()) / interval).astype(np.int64)
    order = np.lexsort((times[rows], -separation[rows], bins))
    first = np.r_[True, np.diff(bins[order]) != 0]
    selected = rows[order[first]]
    return selected[np.argsort(times[selected], kind="stable")]


def stats(values):
    values = np.asarray(values)
    return {"count": len(values), "min": float(values.min()), "median": float(np.median(values)),
            "p90": float(np.quantile(values, .9)), "max": float(values.max())} if len(values) else {"count": 0}


def main(config_path, output_override=None):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Project processing must run in Docker")
    cfg = json.loads(Path(config_path).read_text())
    artifact_root = Path(cfg["artifact_root"])
    output = Path(output_override) if output_override else artifact_root / cfg["output_relative_path"]
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write(output / "STARTED.json", {"utc": datetime.now(timezone.utc).isoformat(), "task_id": cfg["task_id"], "scientific_verdict": None})
    try:
        path = artifact_root / cfg["acquisition_relative_path"]
        inputs = [record(path), record(config_path), record(__file__), record("src/phd/wu_vallet_p3_v2/trajectory.py")]
        acquisition = np.load(path, allow_pickle=False)
        pulse_time = acquisition["pulse_gps_time"]
        pulse_strip = acquisition["pulse_strip"]
        first_xyz, last_xyz = acquisition["pulse_first_xyz"], acquisition["pulse_last_xyz"]
        separation = np.linalg.norm(last_xyz-first_xyz, axis=1)
        eligible = acquisition["pulse_complete"] & ~acquisition["pulse_ambiguous"] & (acquisition["pulse_return_count"] > 1)
        context_time, context_strip = acquisition["context_gps_time"], acquisition["context_strip"]
        pulse_id = acquisition["context_pulse_id"]
        observed_rows = np.flatnonzero(eligible[pulse_id] & (separation[pulse_id] > 0))
        observed_id = pulse_id[observed_rows]
        observed_direction = (last_xyz[observed_id]-first_xyz[observed_id]) / separation[observed_id, None]
        perpendicular = np.linalg.norm(np.cross(acquisition["context_xyz"][observed_rows]-first_xyz[observed_id], observed_direction), axis=1)
        pulse_max_error = np.zeros(len(pulse_time), dtype=np.float64)
        np.maximum.at(pulse_max_error, observed_id, perpendicular)
        angle = acquisition["context_scan_angle_rank"]
        pulse_angle_min = np.full(len(pulse_time), np.inf)
        pulse_angle_max = np.full(len(pulse_time), -np.inf)
        np.minimum.at(pulse_angle_min, pulse_id, angle)
        np.maximum.at(pulse_angle_max, pulse_id, angle)
        bad_line = eligible & (pulse_max_error > cfg["max_pulse_collinearity_error_m"])
        bad_angle = eligible & (pulse_angle_min != pulse_angle_max)
        pulse_audit = {"initial_complete_multireturn_pulses": int(eligible.sum()),
                       "intermediate_return_max_line_error_m": stats(pulse_max_error[eligible]),
                       "line_error_excluded_pulses": int(bad_line.sum()),
                       "inconsistent_recorded_scan_angle_pulses": int(bad_angle.sum()),
                       "line_or_angle_exclusion_counts_may_overlap": True}
        eligible &= ~bad_line
        if cfg["require_same_recorded_scan_angle_per_pulse"]:
            eligible &= ~bad_angle
        del observed_direction, observed_rows, observed_id, perpendicular
        p3_row = acquisition["p3_context_row"]
        p3_time, p3_strip = acquisition["p3_gps_time"], acquisition["p3_strip"]
        if not np.array_equal(context_time[p3_row], p3_time) or not np.array_equal(context_strip[p3_row], p3_strip):
            raise ValueError("P3-to-context membership mismatch")
        variants = cfg["variants"]
        if len({v["name"] for v in variants}) != len(variants):
            raise ValueError("Variant names must be unique")
        main_index = [v["name"] for v in variants].index(cfg["main_variant"])
        p3_variant_origins = np.full((len(variants), len(p3_row), 3), np.nan, dtype=np.float64)
        p3_variant_valid = np.zeros((len(variants), len(p3_row)), dtype=bool)
        context_origins = np.full((len(context_time), 3), np.nan, dtype=np.float64)
        context_valid = np.zeros(len(context_time), dtype=bool)
        fits, fit_pulse_indices = [], {}
        for variant_index, variant in enumerate(variants):
            for strip in np.unique(p3_strip):
                target = np.flatnonzero(p3_strip == strip)
                lo, hi = float(p3_time[target].min() - variant["padding_s"]), float(p3_time[target].max() + variant["padding_s"])
                rows = np.flatnonzero(eligible & (pulse_strip == strip) & (pulse_time >= lo) & (pulse_time <= hi)
                                     & (separation >= variant["min_return_separation_m"]))
                selected = sample_longest_pulses(pulse_time, separation, rows, cfg["multiple_pulse_sampling_interval_s"])
                fit_cfg = dict(cfg["fit_config"], min_return_separation_m=variant["min_return_separation_m"], objective=variant["objective"])
                fit = fit_trajectory_window(pulse_time[selected], first_xyz[selected], last_xyz[selected], TrajectoryConfig(**fit_cfg), strip_id=str(strip))
                fit_id = f"{variant['name']}_strip{strip}"
                fit.update(fit_id=fit_id, variant=variant["name"], requested_gps_window_s=[lo, hi],
                           eligible_complete_multireturn_pulses=len(rows), sampled_longest_pulses=len(selected),
                           sampling_rule=cfg["sampling_rule"])
                fit_pulse_indices[fit_id+"_sampled_pulse_ids"] = selected
                for name in ("train_input_rows", "holdout_input_rows", "holdout_validated_input_rows"):
                    if name in fit:
                        fit_pulse_indices[fit_id+"_"+name] = fit.pop(name)
                fits.append(fit)
                if fit["accepted"]:
                    support_lo, support_hi = fit["support_gps_time_s"]
                    valid_p3 = target[(p3_time[target] >= support_lo) & (p3_time[target] <= support_hi)]
                    p3_variant_origins[variant_index, valid_p3] = predict_origins(fit, p3_time[valid_p3])
                    p3_variant_valid[variant_index, valid_p3] = True
                    if variant_index == main_index:
                        valid_context = np.flatnonzero((context_strip == strip) & (context_time >= support_lo) & (context_time <= support_hi))
                        context_origins[valid_context] = predict_origins(fit, context_time[valid_context])
                        context_valid[valid_context] = True
                print(json.dumps(json_safe({"fit": fit_id, "accepted": fit["accepted"], "reason": fit["rejection_reasons"],
                                           "sampled": len(selected), "holdout": fit.get("holdout"), "bootstrap": fit.get("bootstrap")})), flush=True)
        if not np.array_equal(context_valid[p3_row], p3_variant_valid[main_index]):
            raise ValueError("P3 validity differs from original context row validity")
        if not np.array_equal(context_origins[p3_row], p3_variant_origins[main_index], equal_nan=True):
            raise ValueError("P3 origins differ from original context row origins")
        p3_main = p3_variant_origins[main_index]
        sensitivities = []
        for index, variant in enumerate(variants):
            common = p3_variant_valid[index] & p3_variant_valid[main_index]
            delta = np.linalg.norm(p3_variant_origins[index, common] - p3_main[common], axis=1)
            point = acquisition["p3_xyz"][common]
            a, b = p3_variant_origins[index, common] - point, p3_main[common] - point
            a /= np.linalg.norm(a, axis=1, keepdims=True)
            b /= np.linalg.norm(b, axis=1, keepdims=True)
            angle = np.degrees(np.arccos(np.clip(np.sum(a*b, axis=1), -1., 1.)))
            sensitivities.append({"variant": variant["name"], "valid_p3_points": int(p3_variant_valid[index].sum()),
                                  "common_p3_points": int(common.sum()), "origin_difference_m": stats(delta),
                                  "direction_at_same_p3_point_difference_degrees": stats(angle)})
        arrays = dict(context_origins=context_origins, context_valid=context_valid, p3_origins=p3_main,
                      p3_valid=p3_variant_valid[main_index], p3_context_row=p3_row,
                      alternate_p3_origins=p3_variant_origins, alternate_p3_valid=p3_variant_valid,
                      alternate_names=np.asarray([v["name"] for v in variants]), main_variant_index=np.asarray(main_index),
                      origin_role=np.asarray(ROLE))
        np.savez_compressed(output / "estimated_origins.npz", **arrays)
        np.savez_compressed(output / "fit_pulse_membership.npz", **fit_pulse_indices)
        write(output / "fits.json", fits)
        for source, name in ((config_path, "config.json"), (__file__, "recover_trajectory.py"),
                             ("src/phd/wu_vallet_p3_v2/trajectory.py", "trajectory.py")):
            shutil.copyfile(source, output / name)
        report = {"task_id": cfg["task_id"], "status": "ESTIMATED_TRAJECTORY_DEVELOPMENT_COMPLETE",
                  "origin_role": ROLE, "native_Wu_Vallet_reproduction": False, "scientific_verdict": None,
                  "input_records": inputs, "main_variant": cfg["main_variant"], "configuration": cfg,
                  "main_valid_context_points": int(context_valid.sum()), "total_context_points": len(context_time),
                  "main_valid_p3_points": int(p3_variant_valid[main_index].sum()), "total_p3_points": len(p3_row),
                  "fit_count": len(fits), "accepted_fits": sum(fit["accepted"] for fit in fits),
                  "pulse_line_input_audit": pulse_audit,
                  "sensitivity": sensitivities, "p3_origin_bounds_xyz": {"min": np.nanmin(p3_main, axis=0).tolist(), "max": np.nanmax(p3_main, axis=0).tolist()} if p3_variant_valid[main_index].any() else None,
                  "no_external_height_attitude_or_ground_truth_used": True,
                  "limitations": ["Actual historical sensor trajectory remains unavailable", "Local linear motion is an approximation", "Internal holdout and block bootstrap do not bound systematic pulse/georeferencing errors", "Unaccepted fits or out-of-support times have unavailable NaN origins", "No parameter selected by image, UAS reference, GT or downstream Wu labels"],
                  "runtime": {"elapsed_seconds": time.monotonic()-started, "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "git_head": os.environ.get("JBGS_SOURCE_GIT_HEAD"), "docker_image": os.environ.get("JBGS_CONTAINER_IMAGE_ID")},
                  "output_records": [record(output / name) for name in ("estimated_origins.npz", "fits.json", "fit_pulse_membership.npz", "config.json", "recover_trajectory.py", "trajectory.py")]}
        write(output / "receipt.json", report)
        print(json.dumps({"output": str(output), "status": report["status"], "valid_p3": report["main_valid_p3_points"], "accepted_fits": report["accepted_fits"]}), flush=True)
    except Exception as error:
        write(output / "FAILED.json", {"error": repr(error), "traceback": traceback.format_exc(), "scientific_verdict": None})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/phd/wu_vallet_p3_v2/trajectory_v2.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    main(args.config, args.output)
