"""Evaluate pinned DN checkpoint on the unchanged B appearance evaluation rays."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
import torch
import yaml
from nerfstudio.utils.eval_utils import eval_setup


def main(task, source, initial=False):
    task, source = Path(task), Path(source)
    output = task / ("evaluation_initial" if initial else "evaluation")
    output.mkdir()
    config_path = task / "outputs/PHD_P2_AB_FIXED_PRIOR/dn-splatter/v1/config.yml"
    start = time.monotonic()
    if initial:
        torch.manual_seed(0)
        config = yaml.load(config_path.read_text(), Loader=yaml.Loader)
        pipeline = config.pipeline.setup(device="cuda", test_mode="test")
        pipeline.eval()
        checkpoint_path, step = None, -1
    else:
        _, pipeline, checkpoint_path, step = eval_setup(config_path, test_mode="test")
    seed = np.load(source / "initial_source_seeds.npz", allow_pickle=False)
    xyz, units = seed["xyz"], seed["unit_index"]
    tree = cKDTree(xyz)
    views = {int(row["image_id"]): row for row in json.loads((source / "views.json").read_text())["views"] if "excluded" not in row}
    files = [Path(path).name for path in pipeline.datamanager.eval_dataset.image_filenames]
    metrics, surfaces = [], []
    for index, (camera, batch) in enumerate(pipeline.datamanager.fixed_indices_eval_dataloader):
        iid = int(Path(files[index]).stem.split("_")[-1])
        row = views[iid]
        if row["role"] != "eval":
            raise ValueError("DN evaluation role mismatch")
        with torch.no_grad():
            result = pipeline.model.get_outputs_for_camera(camera=camera)
        arrays = {}
        for name, field in (("rgb", "rgb"), ("depth", "depth"), ("alpha", "accumulation"), ("normal", "normal")):
            arr = result[field].detach().cpu().numpy()
            if arr.ndim == 4:
                arr = arr[0]
            if name in {"depth", "alpha"} and arr.ndim == 3:
                arr = arr[..., 0]
            arrays[name] = arr
        target = np.asarray(Image.open(source / "surface_texturing" / f"target_{iid}.png")).astype(np.float32) / 255.
        initial = np.load(source / "surface_texturing" / f"render_{iid}.npz", allow_pickle=False)
        mask = initial["alpha"] >= .5
        valid = (arrays["alpha"] >= .5) & np.isfinite(arrays["depth"]) & (arrays["depth"] > 0)
        if arrays["rgb"].shape != target.shape:
            raise ValueError("DN camera output dimensions differ from fixed B crop")
        camera_c2w_gl = camera.camera_to_worlds[0].detach().cpu().numpy()
        extended = np.eye(4)
        extended[:3] = camera_c2w_gl
        V_check = np.linalg.inv(extended @ np.diag([1, -1, -1, 1]))
        V, K = np.array(row["viewmat"]), np.array(row["K"])
        camera_error = float(np.abs(V - V_check).max())
        if camera_error > 1e-3:
            raise ValueError(f"DN source camera transform drift {camera_error}")
        v, u = np.where(valid)
        rays = np.column_stack((u + .5, v + .5, np.ones(len(u)))) @ np.linalg.inv(K).T
        points = (rays * arrays["depth"][v, u, None] - V[:3, 3]) @ V[:3, :3]
        distance, seed_rows = tree.query(points)
        surfaces.append({"xyz": points.astype(np.float32), "unit_index": units[seed_rows],
                         "reference_row": seed_rows, "association_distance_m": distance.astype(np.float32),
                         "image_id": np.full(len(points), iid, dtype=np.int32),
                         "pixel_uv": np.column_stack((u, v)).astype(np.int32), "alpha": arrays["alpha"][v, u]})
        diff = arrays["rgb"][mask] - target[mask]
        overlap = mask & valid
        metrics.append({"image_id": iid, "initial_B_surface_pixels": int(mask.sum()), "final_surface_pixels": int(valid.sum()),
                        "mae_on_initial_B_support": float(np.abs(diff).mean()),
                        "psnr_db_on_initial_B_support": float(-10 * np.log10(max(float(np.square(diff).mean()), 1e-12))),
                        "removed_pixels": int((mask & ~valid).sum()), "added_pixels": int((valid & ~mask).sum()),
                        "max_depth_displacement_from_B_initial_m": float(np.abs(arrays["depth"][overlap] - initial["depth"][overlap]).max()) if overlap.any() else None,
                        "camera_matrix_max_abs_delta": camera_error})
        np.savez_compressed(output / f"render_{iid}.npz", **arrays)
        Image.fromarray((np.clip(arrays["rgb"], 0, 1) * 255).astype(np.uint8)).save(output / f"rgb_{iid}.png")
        Image.fromarray((target * 255).astype(np.uint8)).save(output / f"target_{iid}.png")
    combined = {key: np.concatenate([s[key] for s in surfaces]) for key in surfaces[0]}
    np.savez_compressed(output / "extracted_surface.npz", **combined)
    if initial:
        centers = pipeline.model.means.detach().cpu().numpy()
    else:
        state = torch.load(checkpoint_path, map_location="cpu")["pipeline"]
        centers = state["_model.gauss_params.means"].numpy()
    distance, nearest = tree.query(centers)
    np.savez_compressed(output / "centers.npz", xyz=centers, unit_index=units[nearest], base_xyz=xyz,
                        source_association_distance_m=distance)
    result = {"status": "PINNED_UPSTREAM_BOUNDED_DEVELOPMENT_COMPLETE", "method": "DN_SPLATTER_UPSTREAM_ADAPTED_PRIOR",
              "decision_method": "FIXED_PRIOR", "condition": "REAL", "checkpoint_step": step,
              "upstream_commit": "97588b4290128ce7ba6fdbfaac3020b42b17de4c", "views": metrics,
              "gaussians": len(centers), "surface_points": len(combined["xyz"]),
              "runtime_evaluation_seconds": time.monotonic() - start,
              "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
              "checkpoint_sha256": hashlib.sha256(Path(checkpoint_path).read_bytes()).hexdigest() if checkpoint_path else None,
              "initialization": "fresh exact upstream config/source with seed0 before loading checkpoint" if initial else "checkpoint",
              "interpretation": "96-step source-depth adapted upstream; different 3DGS representation/default optimizer and SH3; not converged paper-reproduction performance",
              "scientific_verdict": None}
    (output / "metrics.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"step": step, "views": len(metrics), "surface_points": len(combined["xyz"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--initial", action="store_true")
    args = parser.parse_args()
    main(args.task, args.source, args.initial)
