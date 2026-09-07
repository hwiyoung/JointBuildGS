"""Separate reference-only measurements of completed, GS-free point updates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree

from scripts.phd.wu_vallet_p3_v1.evaluate import measure, median_grid, summary
from scripts.phd.wu_vallet_p3_v2.update_points import sha, write


def run(config_path, output):
    cfg = json.loads(Path(config_path).read_text())
    output.mkdir(parents=True, exist_ok=False)
    write(output / "config.json", cfg)
    started = time.monotonic()
    root = Path(cfg["update_root"])
    receipt = json.loads((root / "receipt.json").read_text())
    assert receipt["status"] == "PAPER_BASED_POINT_UPDATE_COMPLETE"
    assert receipt["scientific_verdict"] is None and receipt["reference_accessed"] is False
    ref_path = Path(cfg["reference_npz"])
    if sha(ref_path) != cfg["reference_sha256"]:
        raise ValueError("Frozen reference crop hash mismatch")
    reference = np.load(ref_path)["uas_xyz"]
    reference_tree = cKDTree(reference)
    ref_height, ref_count = median_grid(reference)
    common = np.load(root / "common.npz")
    old, new = common["old_xyz"], common["new_xyz"]
    methods, grids, decisions, inputs = {}, {}, {}, {
        str(root / "receipt.json"): sha(root / "receipt.json"),
        str(root / "common.npz"): sha(root / "common.npz"),
        str(ref_path): sha(ref_path), str(Path(cfg["reference_receipt"])): sha(cfg["reference_receipt"])}
    for name, points in (("native_als", old), ("current_image_sensor", new)):
        methods[name], grids[name] = measure(points, reference, reference_tree, ref_height, ref_count)
        methods[name]["point_count"] = len(points)
    old_ref_distance = reference_tree.query(old, workers=4)[0]
    new_ref_distance = reference_tree.query(new, workers=4)[0]
    primary = None
    for arm in receipt["arms"]:
        name = arm["name"]; path = root / name / "updated_points.npz"
        inputs[str(path)] = sha(path); data = np.load(path)
        points = data["updated_points"]
        methods[name], grids[name] = measure(points, reference, reference_tree, ref_height, ref_count)
        methods[name]["point_count"] = len(points)
        decisions[name] = {
            "removed_old_reference_discrepancy": summary(old_ref_distance[~data["old_keep_mask"]]),
            "retained_old_reference_discrepancy": summary(old_ref_distance[data["old_keep_mask"]]),
            "admitted_new_reference_discrepancy": summary(new_ref_distance[data["new_keep_mask"]]),
            "excluded_new_reference_discrepancy": summary(new_ref_distance[~data["new_keep_mask"]]),
            "interpretation": "Post-hoc numerical discrepancy, not ground-truth change labels or false-positive rates",
        }
        if name == cfg["primary_display_arm"]:
            primary = points
        print(json.dumps({"evaluated": name, "points": len(points)}), flush=True)
    if primary is None:
        fallback = "image_direction_d0.3_a0"
        primary = np.load(root / fallback / "updated_points.npz")["updated_points"]
        cfg["display_fallback"] = fallback
    changes = []
    for tolerance in (0.1, 0.3, 0.6):
        for area in (0.0, 1.0):
            names = [f"{prefix}_d{tolerance:g}_a{area:g}" for prefix in ("image_direction", "estimated_bidir")]
            if all((root / name / "updated_points.npz").is_file() for name in names):
                a, b = [np.load(root / name / "updated_points.npz") for name in names]
                changes.append({"tolerance_m": tolerance, "small_region_area_m2": area,
                                "old_keep_disagreements": int(np.count_nonzero(a["old_keep_mask"] != b["old_keep_mask"])),
                                "new_keep_disagreements": int(np.count_nonzero(a["new_keep_mask"] != b["new_keep_mask"])),
                                "old_label_disagreements": int(np.count_nonzero(a["old_labels"] != b["old_labels"])),
                                "new_label_disagreements": int(np.count_nonzero(a["new_labels"] != b["new_labels"]))})
    fig, axes = plt.subplots(2, 4, figsize=(17, 8), sharey=True)
    sources = [("Old ALS", old), ("Current image sensor mesh vertices", new),
               ("Wu paper-based point update", primary), ("Evaluation-only UAS", reference)]
    section_counts = {}
    for row, (axis, center) in enumerate(((0, cfg["sections"]["x"]), (1, cfg["sections"]["y"]))):
        width = cfg["sections"]["half_width_m"]
        for column, (name, points) in enumerate(sources):
            keep = (points[:, axis] >= center - width) & (points[:, axis] < center + width)
            section = points[keep]
            axes[row, column].scatter(section[:, 1-axis], section[:, 2], s=1, rasterized=True)
            axes[row, column].set_title(name)
            axes[row, column].set_xlabel(f"Scene {'Y' if axis == 0 else 'X'} (m)")
            axes[row, column].set_ylim(-50, -16)
            axes[row, column].grid(alpha=.2)
            section_counts[f"{name}_axis{axis}"] = len(section)
        axes[row, 0].set_ylabel(f"Z (m); {'X' if axis == 0 else 'Y'}={center} +/- {width}m")
    fig.suptitle("Fixed P3 sections: native point update; numerical raw-shift UAS comparison")
    fig.tight_layout(); fig.savefig(output / "cross_sections.png", dpi=150); plt.close(fig)
    primary_name = cfg.get("display_fallback", cfg["primary_display_arm"])
    fig, axes = plt.subplots(2, 3, figsize=(13, 9))
    extent = [-60, -20, -42, 12]
    for col, name in enumerate(("native_als", "current_image_sensor", primary_name)):
        axes[0, col].imshow(grids[name]["median_z"], origin="lower", extent=extent, vmin=-50, vmax=-17, cmap="viridis")
        image = axes[1, col].imshow(grids[name]["delta_z"], origin="lower", extent=extent, vmin=-2, vmax=2, cmap="coolwarm")
        axes[0, col].set_title(name); axes[1, col].set_title("Median Z minus UAS (display clipped +/-2m)")
        for row in range(2): axes[row, col].set(xlabel="Scene X (m)", ylabel="Scene Y (m)")
    fig.colorbar(image, ax=axes[1, :].tolist(), shrink=.7)
    fig.savefig(output / "height_comparison.png", dpi=150, bbox_inches="tight"); plt.close(fig)
    result = {"status": "REFERENCE_ONLY_POINT_UPDATE_EVALUATION_COMPLETE", "task_id": cfg["task_id"],
              "scientific_verdict": None, "methods": methods, "decision_diagnostics": decisions,
              "trajectory_direction_comparisons": changes, "reference_points": len(reference),
              "reference_occupied_cells": int((ref_count > 0).sum()),
              "input_hashes": inputs, "scope": cfg["scope"], "reference_crs_header": "EPSG:32632",
              "working_crs": "EPSG:25832", "reprojection_or_registration_performed": False,
              "primary_display_arm": primary_name, "section_point_counts": section_counts,
              "elapsed_seconds": time.monotonic() - started,
              "source_snapshot_manifest": os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
              "source_git_head": os.environ.get("JBGS_SOURCE_GIT_HEAD"),
              "container_image": os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
              "outputs": {p.name: sha(p) for p in output.iterdir() if p.is_file()}}
    for path, expected in inputs.items():
        assert sha(path) == expected
    write(output / "evaluation.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    run(args.config, args.output)
