"""Measure Wu point-update sensitivity to independently estimated ALS origins."""
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
import open3d

from src.phd.wu_vallet_p3_v2.ray_runtime import RuntimeConfig, SensorMesh, classify_and_update
from src.phd.wu_vallet_p3_v2.trajectory import ROLE, json_safe, predict_origins


def write(path, data):
    with Path(path).open("x") as stream:
        json.dump(json_safe(data), stream, indent=2, allow_nan=False)
        stream.write("\n")


def record(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def label_counts(labels):
    keys, counts = np.unique(labels, return_counts=True)
    return dict(zip(keys.tolist(), counts.tolist()))


def disagreement(candidate, baseline):
    report = {}
    for side in ("old", "new"):
        a, b = candidate[f"{side}_labels"], baseline[f"{side}_labels"]
        changed = a != b
        transitions, counts = np.unique(np.char.add(np.char.add(b[changed], "->"), a[changed]), return_counts=True)
        ak, bk = candidate[f"{side}_keep_mask"], baseline[f"{side}_keep_mask"]
        report[side] = {"points": len(a), "label_disagreements": int(changed.sum()),
                        "label_disagreement_fraction": float(changed.mean()),
                        "label_transitions_baseline_to_candidate": dict(zip(transitions.tolist(), counts.tolist())),
                        "keep_disagreements": int((ak != bk).sum()),
                        "keep_to_drop": int((bk & ~ak).sum()), "drop_to_keep": int((~bk & ak).sum())}
    return report


def origins_for_variant(fits, variant, times, strips):
    origins = np.full((len(times), 3), np.nan, dtype=np.float64)
    seen = set()
    for fit in fits:
        if fit["variant"] != variant:
            continue
        strip = int(fit["strip_id"])
        if strip in seen:
            raise ValueError("Multiple fits for one variant/strip require an explicit piecewise selection policy")
        seen.add(strip)
        if not fit["accepted"]:
            continue
        lo, hi = fit["support_gps_time_s"]
        take = np.flatnonzero((strips == strip) & (times >= lo) & (times <= hi))
        origins[take] = predict_origins(fit, times[take])
    return origins


def main(config_path, output_override=None):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run scientific processing in Docker")
    cfg = json.loads(Path(config_path).read_text())
    root = Path(cfg["artifact_root"])
    output = Path(output_override) if output_override else root/cfg["output_relative_path"]
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write(output/"STARTED.json", {"utc": datetime.now(timezone.utc).isoformat(), "task_id": cfg["task_id"], "scientific_verdict": None})
    try:
        update = root/cfg["update_relative_root"]
        trajectory = root/cfg["trajectory_relative_root"]
        paths = [root/cfg["acquisition_relative_path"], trajectory/"fits.json", trajectory/"estimated_origins.npz",
                 update/"meshes.npz", update/"common.npz", update/"receipt.json",
                 update/cfg["baseline_arm"]/"updated_points.npz", update/cfg["baseline_arm"]/"face_decisions.npz",
                 Path(config_path), Path(__file__), Path("src/phd/wu_vallet_p3_v2/ray_runtime.py"),
                 Path("src/phd/wu_vallet_p3_v2/trajectory.py"), Path("src/phd/wu_vallet_p3_v1/ray_update.py")]
        inputs = [record(path) for path in paths]
        acq = np.load(paths[0], allow_pickle=False)
        fits = json.loads(paths[1].read_text())
        original_origins = np.load(paths[2], allow_pickle=False)
        meshes, common = np.load(paths[3], allow_pickle=False), np.load(paths[4], allow_pickle=False)
        baseline_file = np.load(paths[6], allow_pickle=False)
        baseline = {key: baseline_file[key] for key in ("old_labels", "new_labels", "old_keep_mask", "new_keep_mask")}
        baseline_faces = np.load(paths[7], allow_pickle=False)
        old_xyz, old_triangles = meshes["old_xyz"], meshes["old_triangles"]
        context_indices, p3_lookup = meshes["old_context_indices"], meshes["old_p3_lookup"]
        old_meshed = np.zeros(len(old_xyz), dtype=bool)
        old_meshed[old_triangles.ravel()] = True
        new_pixels = meshes["new_pixel_id"]
        new_inside = np.isin(new_pixels, common["new_pixel_id"])
        if not np.array_equal(new_pixels[new_inside], common["new_pixel_id"]):
            raise ValueError("New P3 pixel membership/order differs from frozen common")
        if not np.array_equal(meshes["new_xyz"][new_inside], common["new_xyz"]):
            raise ValueError("New P3 XYZ membership/order differs from frozen common")
        if not np.array_equal(old_xyz[p3_lookup], common["old_xyz"]):
            raise ValueError("Old P3 XYZ differs from frozen common")
        times, strips = acq["context_gps_time"][context_indices], acq["context_strip"][context_indices]
        new_mesh = SensorMesh(meshes["new_xyz"], meshes["new_triangles"], meshes["new_optical_origins"], new_pixels)
        algorithm = RuntimeConfig(**cfg["runtime_config"])
        origins = {variant: origins_for_variant(fits, variant, times, strips) for variant in cfg["variants"]}
        main_origins = origins[cfg["main_variant"]]
        if not np.array_equal(main_origins, original_origins["context_origins"][context_indices], equal_nan=True):
            raise ValueError("Recomputed main origins differ from original trajectory output")
        main_support = np.isfinite(main_origins).all(axis=1)
        arms, result_labels = [], {}
        main_reproduced = False

        def run(name, sensor_origins, control_role):
            nonlocal main_reproduced
            old_mesh = SensorMesh(old_xyz, old_triangles, sensor_origins, context_indices)
            result = classify_and_update(old_mesh, new_mesh, algorithm)
            old_labels = result["old_vertex_labels"][p3_lookup].copy()
            old_labels[~old_meshed[p3_lookup]] = "unassessed"
            new_labels = result["new_vertex_labels"][new_inside]
            labels = {"old_labels": old_labels, "new_labels": new_labels,
                      "old_keep_mask": old_labels != "changed", "new_keep_mask": new_labels != "consistent"}
            valid = np.isfinite(sensor_origins).all(axis=1)
            common_valid = valid & main_support
            origin_delta = np.linalg.norm(sensor_origins[common_valid]-main_origins[common_valid], axis=1)
            row = {"name": name, "control_role": control_role,
                   "same_original_baseline": disagreement(labels, baseline),
                   "old_label_counts": label_counts(old_labels), "new_label_counts": label_counts(new_labels),
                   "old_retained": int(labels["old_keep_mask"].sum()), "new_admitted": int(labels["new_keep_mask"].sum()),
                   "context_origin_support": int(valid.sum()), "context_points": len(valid),
                   "meshed_vertex_origin_support": int((valid & old_meshed).sum()),
                   "faces_with_all_origins_supported": int(valid[old_triangles].all(axis=1).sum()),
                   "p3_origin_support": int(valid[p3_lookup].sum()),
                   "origin_support_added_vs_main_on_meshed_vertices": int((valid & ~main_support & old_meshed).sum()),
                   "origin_support_lost_vs_main_on_meshed_vertices": int((~valid & main_support & old_meshed).sum()),
                   "maximum_origin_difference_on_common_context_support_m": float(origin_delta.max()) if len(origin_delta) else None,
                   "same_unassessed_old_points_and_keep": bool(np.array_equal(old_labels == "unassessed", baseline["old_labels"] == "unassessed") and labels["old_keep_mask"][old_labels == "unassessed"].all()),
                   "runtime_diagnostics": result["diagnostics"], "scientific_verdict": None}
            if not row["same_unassessed_old_points_and_keep"]:
                raise ValueError("Unmeshed old preservation changed")
            if name == cfg["main_variant"]:
                main_reproduced = all(np.array_equal(labels[key], baseline[key]) for key in labels)
                row["baseline_face_labels_exactly_equal"] = all(np.array_equal(result[f"{side}_face_labels"], baseline_faces[f"{side}_face_labels"]) for side in ("old", "new"))
                if not main_reproduced or not row["baseline_face_labels_exactly_equal"]:
                    raise ValueError("Main variant failed exact old/new point and face label replay")
            dest = output/name
            dest.mkdir(exist_ok=False)
            np.savez_compressed(dest/"labels.npz", **labels,
                                old_changed_input_indices=np.flatnonzero(labels["old_labels"] != baseline["old_labels"]),
                                new_changed_input_indices=np.flatnonzero(labels["new_labels"] != baseline["new_labels"]),
                                old_original_row=common["old_original_row"], old_original_file_index=common["old_original_file_index"],
                                new_pixel_id=common["new_pixel_id"])
            row["output_record"] = record(dest/"labels.npz")
            write(dest/"receipt.json", row)
            arms.append(row)
            result_labels[name] = labels
            print(json.dumps(json_safe({key: row[key] for key in ("name", "same_original_baseline", "origin_support_lost_vs_main_on_meshed_vertices", "maximum_origin_difference_on_common_context_support_m")})), flush=True)

        for variant in cfg["variants"]:
            run(variant, origins[variant], "estimated_origin_variant_with_own_supported_time_interval")
        support_controls = []
        for variant in cfg["variants"]:
            alternate_support = np.isfinite(origins[variant]).all(axis=1)
            if np.any((alternate_support != main_support) & old_meshed):
                if np.any(alternate_support & ~main_support & old_meshed):
                    raise ValueError("Additional alternate support needs an explicit both-arms common-support rerun")
                name = f"main_with_{variant}_support"
                reduced = main_origins.copy()
                reduced[~alternate_support] = np.nan
                run(name, reduced, "main_origin_positions_with_alternate_time_support")
                support_controls.append({"variant": variant, "main_with_same_support_control": name,
                                         "origin_position_effect_at_matched_support": disagreement(result_labels[variant], result_labels[name]),
                                         "main_origin_support_removal_effect": disagreement(result_labels[name], baseline)})
            else:
                support_controls.append({"variant": variant, "main_with_same_support_control": cfg["main_variant"],
                                         "origin_position_effect_at_matched_support": disagreement(result_labels[variant], baseline),
                                         "main_origin_support_removal_effect": disagreement(baseline, baseline)})
        for source, name in ((config_path, "config.json"), (__file__, "origin_sensitivity.py")):
            shutil.copyfile(source, output/name)
        report = {"task_id": cfg["task_id"], "status": "ORIGIN_ESTIMATOR_DECISION_SENSITIVITY_COMPLETE",
                  "origin_role": ROLE, "scientific_verdict": None, "reference_accessed": False,
                  "full_author_reproduction": False, "main_exact_point_and_face_replay": main_reproduced,
                  "input_records": inputs, "configuration": cfg, "arms": arms, "matched_support_analysis": support_controls,
                  "limitations": ["Estimated origins remain unverified against the actual sensor trajectory", "This measures estimator setting stability for one frozen mesh, master image, ray algorithm and parameter set", "Temporal support differences are separated by matched-support control", "No reference geometry, RGB or downstream outcome was used to fit or choose origins"],
                  "runtime": {"elapsed_seconds": time.monotonic()-started, "python": platform.python_version(), "numpy": np.__version__, "open3d": open3d.__version__, "git_head": os.environ.get("JBGS_SOURCE_GIT_HEAD"), "docker_image": os.environ.get("JBGS_CONTAINER_IMAGE_ID")}}
        write(output/"receipt.json", report)
        print(json.dumps({"status": report["status"], "runs": len(arms), "output": str(output)}), flush=True)
    except Exception as error:
        write(output/"FAILED.json", {"error": repr(error), "traceback": traceback.format_exc(), "scientific_verdict": None})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/phd/wu_vallet_p3_v2/origin_sensitivity_v2.json")
    parser.add_argument("--output")
    arguments = parser.parse_args()
    main(arguments.config, arguments.output)
