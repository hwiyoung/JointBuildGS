"""Frozen-input SOR diagnostic, separate from the Wu--Vallet update method.

Neither UAS references nor Wu decisions participate in computing the SOR masks.
Both context and cropped runs use the same fixed Open3D tutorial parameters.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import traceback

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def sor(points, cfg):
    if not np.isfinite(points).all():
        raise ValueError("Nonfinite source points require explicit prior handling")
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    filtered, indices = cloud.remove_statistical_outlier(
        nb_neighbors=cfg["nb_neighbors"], std_ratio=cfg["std_ratio"], print_progress=False)
    indices = np.asarray(indices, dtype=np.int64)
    if len(indices) != len(np.unique(indices)) or (indices < 0).any() or (indices >= len(points)).any():
        raise ValueError("Invalid or repeated library inlier indices")
    if not np.array_equal(np.asarray(filtered.points), points[indices]):
        raise ValueError("Library point output does not replay source indices exactly")
    keep = np.zeros(len(points), dtype=bool)
    keep[indices] = True
    return keep


def discrepancy_counts(keep, distances, threshold):
    far = distances > threshold
    return {
        "total": len(keep), "retained": int(keep.sum()), "removed": int((~keep).sum()),
        "reference_far_total": int(far.sum()),
        "reference_far_removed": int((far & ~keep).sum()),
        "reference_far_retained": int((far & keep).sum()),
        "reference_near_removed": int((~far & ~keep).sum()),
        "reference_far_removed_fraction": float((far & ~keep).sum() / max(1, far.sum())),
    }


def run(config_path, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    output.mkdir(parents=True, exist_ok=False)
    cfg = json.loads(config_path.read_text())
    write(output / "config.json", cfg)
    started = time.monotonic()
    try:
        mesh_path, common_path = Path(cfg["mesh_npz"]), Path(cfg["common_npz"])
        inputs = {str(p): sha(p) for p in (mesh_path, common_path, config_path)}
        with np.load(mesh_path) as data:
            full = data["new_xyz"].copy()
            full_pixels = data["new_pixel_id"].copy()
        with np.load(common_path) as data:
            p3 = data["new_xyz"].copy()
            p3_pixels = data["new_pixel_id"].copy()
        order = np.argsort(full_pixels)
        if len(np.unique(full_pixels)) != len(full_pixels):
            raise ValueError("Full sensor native pixels must be unique")
        offsets = np.searchsorted(full_pixels[order], p3_pixels)
        if (offsets >= len(full_pixels)).any():
            raise ValueError("P3 pixel outside full sensor support")
        p3_full_indices = order[offsets]
        if not np.array_equal(full_pixels[p3_full_indices], p3_pixels):
            raise ValueError("P3 to full pixel mapping failed")
        if not np.array_equal(full[p3_full_indices], p3):
            raise ValueError("P3 coordinates do not replay full sensor coordinates")
        full_keep = sor(full, cfg["sor"])
        with_context = full_keep[p3_full_indices]
        without_context = sor(p3, cfg["sor"])
        mask_path = output / "masks.npz"
        np.savez_compressed(mask_path,
                            full_keep=full_keep,
                            full_native_pixel_id=full_pixels,
                            p3_full_indices=p3_full_indices,
                            p3_native_pixel_id=p3_pixels,
                            p3_keep_with_context=with_context,
                            p3_keep_without_context=without_context)
        mask_hash = sha(mask_path)
        mask_frozen_at = utc()
        write(output / "MASKS_FROZEN.json", {
            "time_utc": mask_frozen_at, "sha256": mask_hash,
            "reference_accessed": False, "Wu_decisions_accessed": False,
            "parameters": cfg["sor"], "input_hashes": inputs,
            "full_count": len(full), "full_removed": int((~full_keep).sum()),
            "p3_count": len(p3), "scientific_verdict": None,
        })
        print(json.dumps({"phase": "masks_frozen", "full_count": len(full), "p3_count": len(p3),
                          "masks_sha256": mask_hash}), flush=True)
        # Evaluation begins only after the immutable parameter/source-only masks exist.
        reference_opened_at = utc()
        ref_path = Path(cfg["reference_npz"])
        if sha(ref_path) != cfg["reference_sha256"]:
            raise ValueError("Reference hash mismatch")
        with np.load(ref_path) as data:
            reference = data["uas_xyz"].copy()
        distance = cKDTree(reference).query(p3, workers=cfg["workers"])[0]
        np.savez_compressed(output / "evaluation_only.npz", p3_reference_distance_m=distance)
        threshold = cfg["diagnostic_reference_distance_m"]
        results = {"with_context": discrepancy_counts(with_context, distance, threshold),
                   "without_context": discrepancy_counts(without_context, distance, threshold)}
        if sha(mask_path) != mask_hash:
            raise ValueError("Frozen masks changed during evaluation")
        for path, expected in inputs.items():
            if sha(path) != expected:
                raise ValueError("An input changed during this run")
        receipt = {
            "status": "SPATIAL_SOR_DIAGNOSTIC_COMPLETE", "task_id": cfg["task_id"],
            "scientific_verdict": None, "Wu_Vallet_method_modified": False,
            "paper_specified_SOR": False, "parameters": cfg["sor"],
            "parameter_basis": cfg["parameter_basis"], "full_sensor_count": len(full),
            "full_sensor_removed": int((~full_keep).sum()), "p3_count": len(p3),
            "p3_context_disagreements": int((with_context != without_context).sum()),
            "results": results, "diagnostic_reference_distance_m": threshold,
            "mask_sha256": mask_hash, "masks_frozen_utc": mask_frozen_at,
            "reference_first_access_utc": reference_opened_at,
            "reference_access_before_mask_freeze": False,
            "reference_points": len(reference), "reference_crs_header": "EPSG:32632",
            "working_crs": "EPSG:25832", "reprojection_or_registration_performed": False,
            "interpretation": "Post-hoc numerical reference discrepancy, not certified error or true/false positive labels. SOR measures local sampling isolation, not correspondence to the current physical surface.",
            "input_hashes": {**inputs, str(ref_path): cfg["reference_sha256"]},
            "source_git_head": os.environ.get("JBGS_SOURCE_GIT_HEAD"),
            "container_image": os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
            "source_snapshot_manifest": os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
            "resources": {"cpus": 4, "memory_gib": 8, "network": "none", "gpu": False},
            "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "open3d")},
            "elapsed_seconds": time.monotonic() - started,
            "outputs": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
        }
        write(output / "receipt.json", receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
    except Exception as error:
        write(output / "FAILED.json", {"error": repr(error), "traceback": traceback.format_exc(),
                                       "scientific_verdict": None})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.output)
