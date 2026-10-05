"""Read-only, saved-array causal trace. Reference is diagnostic/evaluation only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--image-id", required=True)
    args = ap.parse_args()
    root = args.source
    cfg = json.loads(args.config.read_text())
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    if (out / "da3_evidence.json").exists():
        raise FileExistsError("Refuse to overwrite prior analysis")
    ledger = {}

    def record(path):
        key = str(path.relative_to(root))
        if key not in ledger:
            ledger[key] = sha(path)
        return path

    def read_json(path):
        return json.loads(record(path).read_text())

    def array(path):
        record(path)
        if path.suffix == ".npy":
            return np.load(path, allow_pickle=False)
        with Image.open(path) as im:
            if im.mode != "F":
                raise ValueError(f"Depth TIFF is not floating point: {path}, {im.mode}")
            return np.array(im)

    rows, probes, inventories = [], [], {}
    for region in sorted({p["region"] for p in cfg["probes"]}):
        input_root = root / "inputs" / region
        split_path = input_root / "scene/split_manifest_da3_v2.json"
        split = read_json(split_path)
        manifest = read_json(input_root / "input_manifest.json")
        assert sha(split_path) == manifest["split_sha256"]
        train = sorted(split["train"], key=lambda v: v["name"])
        eval_names = {v["name"] for v in split["evaluation"]}
        assert not eval_names & {v["name"] for v in train}
        prior_receipt = read_json(input_root / "prior/receipt.json")
        assert prior_receipt["depth_frame"] == "CAMERA_Z_METERS"
        da3_receipt = read_json(input_root / "da3/receipt.json")
        priors = {r["name"]: r for r in prior_receipt["rows"]}
        da3s = {r["name"]: r for r in da3_receipt["images"]}
        calibration = read_json(input_root / "scene/jbgs_calibration.json")
        refpath = root / cfg["reference_path"].format(region=region)
        record(refpath)
        with np.load(refpath, allow_pickle=False) as ref:
            refs = ref["reference_points"]
            original_ids = ref["reference_original_indices"]
        anchor = root / cfg["anchor_path"].format(region=region)
        receipt_anchor = read_json(anchor.parents[2] / "receipt.json")
        model_dirs = {"anchor8000": anchor}
        for condition in cfg["final_conditions"]:
            run = root / "runs_allocator_v2" / region / condition
            rec = read_json(run / "render_receipt.json")
            assert rec["region"] == region and rec["condition"] == condition
            for name in ["render.py", "utils/camera_utils.py", "jbgs_camera_adapter.py", "utils/mesh_utils.py", "utils/render_utils.py", "gaussian_renderer/__init__.py"]:
                p = root / cfg["source_camera_path"] / name
                record(p)
                assert sha(p) == rec["implementation_hashes"][name], name
            model_dirs[condition] = run / "model/train/ours_30000"
        inventories[region] = {"train_views": len(train), "evaluation_views": len(eval_names),
            "saved_train_depths": {k: len(list(p.glob("vis/depth_*.tiff"))) for k, p in model_dirs.items()},
            "prior_maps": len(priors), "da3_maps": len(da3s),
            "anchor_receipt_status": receipt_anchor.get("status"),
            "reference_role": "EVALUATION_ONLY; no fitting, parameter selection, or training mask"}
        for spec in [p for p in cfg["probes"] if p["region"] == region]:
            bounds = np.array(spec["bounds"])
            inside = np.all((refs >= bounds[:, 0]) & (refs < bounds[:, 1]), axis=1)
            candidates = np.flatnonzero(inside)
            if not len(candidates):
                raise ValueError("No reference sample within fixed probe window")
            target = np.array(spec["target_xyz"])
            idx = int(candidates[np.argmin(np.sum((refs[candidates] - target) ** 2, axis=1))])
            point = refs[idx].astype(np.float64)
            selected = []
            for train_idx, v in enumerate(train):
                R, t, K = np.array(v["R"]), np.array(v["t"]), np.array(v["K"])
                pcam = R @ point + t
                if pcam[2] <= 0:
                    continue
                uv = (K @ pcam)[:2] / pcam[2]
                if not (10 <= uv[0] < v["width"] - 10 and 10 <= uv[1] < v["height"] - 10):
                    continue
                center = -R.T @ t
                ray = point - center
                vertical_cos = float(-ray[2] / np.linalg.norm(ray))
                selected.append((vertical_cos, v["name"], train_idx, v, pcam, uv))
            selected.sort(key=lambda item: (-item[0], item[1]))
            probes.append(dict(spec, selected_reference_xyz=point.tolist(), reference_array_row=idx,
                reference_original_index=int(original_ids[idx]), reference_window_samples=len(candidates),
                eligible_train_views=len(selected)))
            for rank, (vcos, name, train_idx, view, pcam, uv) in enumerate(selected[:cfg["n_cameras"]]):
                stem = Path(name).stem
                K, R, t = np.array(view["K"]), np.array(view["R"]), np.array(view["t"])
                assert np.array_equal(K, np.array(calibration["images"][stem]["K"]))
                pix = np.rint(uv).astype(int)
                x, y = pix
                rgb_path = input_root / "scene/images" / name
                assert sha(record(rgb_path)) == view["sha256"]
                actual = np.array(Image.open(rgb_path).convert("RGB"))
                for stage, path in model_dirs.items():
                    saved_gt = np.array(Image.open(record(path / "gt" / f"{train_idx:05d}.png")).convert("RGB"))
                    if not np.array_equal(actual, saved_gt):
                        raise ValueError(f"Training camera order/GT pixel mismatch: {region}/{stage}/{name}")
                paths = {
                    "prior": input_root / "prior/raw_depth" / (stem + ".npy"),
                    "DA3": input_root / "da3/raw_depth" / (stem + ".npy"),
                    **{stage: path / "vis" / f"depth_{train_idx:05d}.tiff" for stage, path in model_dirs.items()}}
                assert sha(paths["prior"]) == priors[name]["sha256"]
                assert sha(paths["DA3"]) == da3s[name]["files"][f"raw_depth/{stem}.npy"]["sha256"]
                base = {"probe": spec["id"], "region": region, "selection_rank": rank,
                    "train_index": train_idx, "image_id": view["image_id"], "image_name": name,
                    "da3_batch": da3s[name]["batch_id"], "downward_ray_vertical_cosine": vcos,
                    "reference_array_row": idx, "reference_original_index": int(original_ids[idx]),
                    "reference_x": point[0], "reference_y": point[1], "reference_z": point[2],
                    "projected_u": float(uv[0]), "projected_v": float(uv[1]), "sample_u": int(x), "sample_v": int(y),
                    "reference_camera_z_m": float(pcam[2]), "train_gt_pixel_identity": True,
                    "visibility_status": "NOT_RAYCAST_VERIFIED; evaluate RGB crop and competing first hits"}
                for label, path in paths.items():
                    depth = array(path)
                    assert depth.shape == (view["height"], view["width"])
                    value = float(depth[y, x])
                    rad = cfg["patch_radius_pixels"]
                    patch = depth[y-rad:y+rad+1, x-rad:x+rad+1]
                    pos = patch[np.isfinite(patch) & (patch > 0)]
                    ray_offset = .5 if label == "prior" else 0.
                    end = R.T @ (np.linalg.inv(K) @ [x + ray_offset, y + ray_offset, 1] * value - t)
                    row = dict(base, source=label, source_path=str(path.relative_to(root)),
                        array_pixel_ray_offset=ray_offset,
                        ray_convention=("OPEN3D_U_PLUS_HALF" if label == "prior" else "INTEGER_GRID_OR_RESAMPLED_DA3"),
                        camera_z_m=value, camera_z_minus_reference_m=value - float(pcam[2]),
                        world_endpoint_z_m=float(end[2]), world_endpoint_z_minus_reference_m=float(end[2] - point[2]),
                        patch_positive_count=int(pos.size), patch_min_m=float(pos.min()) if pos.size else None,
                        patch_median_m=float(np.median(pos)) if pos.size else None,
                        patch_max_m=float(pos.max()) if pos.size else None)
                    rows.append(row)
                print(json.dumps({"probe": spec["id"], "train_image": name,
                    "ref_depth": float(pcam[2]), "values": {r["source"]: r["camera_z_m"] for r in rows[-len(paths):]}}), flush=True)
    for name, digest in ledger.items():
        if sha(root / name) != digest:
            raise ValueError(f"Input changed while reading: {name}")
    with (out / "da3_probe_depths.csv").open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    value = {"task_id": cfg["task_id"], "scientific_verdict": None,
        "status": "PASS_SAVED_INPUT_DEPTH_TRACE", "config": cfg,
        "runtime_image_id": args.image_id, "numpy_version": np.__version__,
        "config_sha256": sha(args.config), "script_sha256": sha(__file__),
        "regions": inventories, "probes": probes, "rows": rows, "input_sha256": ledger,
        "inputs_unchanged": True,
        "limitations": ["Projection into an image is not independent first-hit visibility proof.",
            "Prior array values use Open3D u+0.5,v+0.5 rays; GS calibration uses integer u,v. DA3 resizing has its own pixel interpolation. Same stored array pixel is not exactly the same ray, especially near depth discontinuities.",
            "Reference camera-Z is for the exact projected 3D sample; the reported stored map is sampled at its nearest integer pixel.",
            "5x5 patch may straddle multiple surfaces; min/max are recorded, not used as a recovery claim.",
            "DA3 errors can arise in upstream scale/pose/context or depth prediction; this trace cannot isolate the cause.",
            "Learned surf_depth is the stored rendering quantity, not a TSDF mesh raycast or proof of Gaussian topology.",
            "Point and view selection is post hoc; no population/generalization or scientific verdict."]}
    (out / "da3_evidence.json").write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": value["status"], "rows": len(rows), "input_files": len(ledger)}))


if __name__ == "__main__":
    main()
