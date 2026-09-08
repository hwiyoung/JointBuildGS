"""Run the fixed SRDM comparison in Docker and seal outputs before evaluation."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import time

import cv2
import numpy as np

ARMS = {"image_only": "SRDM_IMAGE_ONLY", "all_prior": "SRDM_FILTER_OFF", "srdm": "SRDM_NATIVE"}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def load(path):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def world_cloud(disparity, selected, pair):
    """Q returns rectified left-camera coordinates; undo rectification and pose."""
    coords = cv2.reprojectImageTo3D(np.asarray(disparity, np.float32), pair["Q"])
    v, u = np.nonzero(selected)
    rectified = coords[v, u].astype(np.float64)
    camera = rectified @ pair["R1"]
    xyz = (camera - pair["world_to_left_t"]) @ pair["world_to_left_R"]
    finite = np.isfinite(xyz).all(axis=1) & (camera[:, 2] > 0)
    return xyz[finite], np.column_stack((u[finite], v[finite])).astype(np.int32)


def geometric_right_prior(pair):
    """Rasterize actual right-camera projections, avoiding left rounding twice."""
    sparse = pair["sparse_disparity"]
    selected = pair["sparse_source_index"] >= 0
    indices = pair["sparse_source_index"][selected].astype(np.int64)
    uv = np.rint(pair["als_right_pixel_xy"][indices]).astype(np.int64)
    if np.any(uv < 0) or np.any(uv[:, 0] >= sparse.shape[1]) or np.any(uv[:, 1] >= sparse.shape[0]):
        raise ValueError("Pair-visible ALS seed projects outside right raster")
    if len(np.unique(uv, axis=0)) != len(uv):
        raise ValueError("Right ALS projection was not z-buffered uniquely")
    result = np.full(sparse.shape, np.nan, np.float32)
    result[uv[:, 1], uv[:, 0]] = -sparse[selected]
    return result


def run_region(task, rid, cfg):
    from src.phd.srdm_p1p2p3_v1.core import run_srdm
    cfg = dict(cfg, core_config=dict(cfg["core_config"]))
    cfg["core_config"]["storage"] = cfg["core_storage_by_region"][rid]
    cfg["core_config"]["max_total_volume_gib"] = 24.0
    if cfg["core_config"].get("pending_exact_api_mapping"):
        raise RuntimeError("Seal actual core settings before regional matching")
    started = time.monotonic()
    output = task / "run" / rid
    output.mkdir(exist_ok=False)
    inputs = task / "inputs" / rid
    metadata = json.loads((inputs / "metadata.json").read_text())
    if sha(inputs / "pair.npz") != metadata["pair_npz"]["sha256"]:
        raise ValueError("Prepared pair hash differs from its receipt")
    shutil.copy2(inputs / "pair.npz", output / "pair.npz")
    shutil.copy2(inputs / "metadata.json", output / "input_metadata.json")
    pair = load(output / "pair.npz")
    write_json(output / "execution_config.json", cfg)
    print(json.dumps({"stage": "matching_start", "region": rid, "shape": list(pair["left_rgb"].shape),
                      "disparity_min": int(pair["disparity_min"]), "disparity_max": int(pair["disparity_max"]),
                      "sparse_pixels": int(np.isfinite(pair["sparse_disparity"]).sum())}), flush=True)
    computed = run_srdm(pair["left_rgb"], pair["right_rgb"], pair["sparse_disparity"],
                        int(pair["disparity_min"]), int(pair["disparity_max"]), cfg["core_config"],
                        work_dir=task / "scratch" / rid,
                        left_valid_mask=pair["left_valid_mask"], right_valid_mask=pair["right_valid_mask"],
                        sparse_right_disparity=geometric_right_prior(pair))
    sparse_indices = pair["sparse_source_index"]
    seed = sparse_indices >= 0
    indices = sparse_indices[seed].astype(np.int64)
    n = len(pair["als_xyz"])
    keep, rejected = np.zeros(n, bool), np.zeros(n, bool)
    keep[indices] = computed["prior_keep"][seed]
    rejected[indices] = computed["prior_reject"][seed]
    unassessed = ~(keep | rejected)
    if np.any(keep & rejected):
        raise ValueError("Prior decision masks overlap")
    weak_values = np.full(n, np.nan, np.float32)
    prior_values = np.full(n, np.nan, np.float32)
    weak_values[indices] = computed["weak_disparity"][seed]
    prior_values[indices] = pair["sparse_disparity"][seed]
    np.savez_compressed(output / "decision.npz", als_xyz=pair["als_xyz"], source_row=pair["als_source_row"],
        als_ids=pair["als_source_row"], source_file_index=pair["als_source_file_index"],
        keep=keep, rejected=rejected, unassessed=unassessed, pixel_xy=pair["als_pixel_xy"],
        als_projection_state=pair["als_projection_state"], als_disparity=prior_values,
        weak_disparity_values=weak_values, disparity_difference=weak_values-prior_values,
        weak_disparity=computed["weak_disparity"], weak_valid=computed["weak_valid"],
        prior_keep=computed["prior_keep"], prior_reject=computed["prior_reject"],
        prior_untestable=computed["prior_untestable"],
        prior_disparity_difference=computed["weak_disparity"]-pair["sparse_disparity"])
    arm_stats = {}
    for internal, name in ARMS.items():
        a = computed["arms"][internal]
        out = output / name
        out.mkdir()
        valid = np.asarray(a["valid"], bool)
        interpolated = np.asarray(a["interpolated_mask"], bool)
        if np.any(valid & interpolated):
            raise ValueError("Observed and interpolated masks overlap")
        selected = (valid | interpolated) & pair["left_valid_mask"] & np.isfinite(a["disparity"])
        xyz, uv = world_cloud(a["disparity"], selected, pair)
        rgb = pair["left_rgb"][uv[:, 1], uv[:, 0]]
        inside = np.all((xyz >= pair["bbox_min"]) & (xyz < pair["bbox_max"]), axis=1)
        np.savez_compressed(out / "result.npz", xyz=xyz, rgb=rgb, pixel_uv=uv, pixel_xy=uv,
            disparity=a["disparity"], valid=valid, interpolated_mask=interpolated,
            point_interpolated=interpolated[uv[:, 1], uv[:, 0]], in_roi=inside)
        arm_stats[name] = {"all_points": len(xyz), "points_in_roi": int(inside.sum()),
                           "original_valid_pixels": int(valid.sum()), "interpolated_pixels": int(interpolated.sum())}
        print(json.dumps({"stage": "arm_saved", "region": rid, "arm": name, **arm_stats[name]}), flush=True)
    runmeta = {"region": rid, "scientific_verdict": None, "reference_accessed": False,
        "implementation": "SRDM two-stage paper reimplementation with documented choices",
        "input_sha256": sha(output / "pair.npz"), "config": cfg,
        "core_metadata": computed["receipt"],
        "right_prior_input": "actual calibrated right-image projections of the same pair-visible ALS seeds; not independent observations",
        "source_hashes": {str(p): sha(p) for p in [Path(__file__), Path("src/phd/srdm_p1p2p3_v1/core.py"), Path("src/phd/srdm_p1p2p3_v1/inm_backend.cpp")]},
        "arms": arm_stats, "prior": {"keep": int(keep.sum()), "rejected": int(rejected.sum()), "unassessed": int(unassessed.sum())},
        "elapsed_seconds": time.monotonic()-started, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    write_json(output / "receipt.json", runmeta)
    print(json.dumps({"stage": "region_complete", "region": rid, "elapsed_seconds": runmeta["elapsed_seconds"]}), flush=True)


def seal(task, cfg):
    out = task / "run"
    hashes = {}
    for rid in cfg["regions"]:
        receipt = json.loads((out / rid / "receipt.json").read_text())
        if receipt["reference_accessed"] or receipt["scientific_verdict"] is not None:
            raise ValueError("Unexpected regional reference access or verdict")
        for rel in ["pair.npz", "decision.npz", "input_metadata.json", "execution_config.json", "receipt.json", *[a+"/result.npz" for a in ARMS.values()]]:
            hashes[f"{rid}/{rel}"] = sha(out / rid / rel)
    write_json(out / "CANDIDATE_SEAL.json", {"task_id": cfg["task_id"], "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_verdict": None, "reference_accessed": False, "outputs": hashes, "expected_regions": cfg["regions"], "expected_arms": list(ARMS.values())})
    print(json.dumps({"stage": "sealed", "files": len(hashes), "reference_accessed": False}))


if __name__ == "__main__":
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run scientific processing in Docker")
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["run", "seal"])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--task-root", type=Path, required=True)
    ap.add_argument("--region", choices=["P1", "P2", "P3"])
    args = ap.parse_args()
    config = json.loads(args.config.read_text())
    if args.stage == "run":
        if not args.region:
            ap.error("--region required")
        run_region(args.task_root, args.region, config)
    else:
        seal(args.task_root, config)
