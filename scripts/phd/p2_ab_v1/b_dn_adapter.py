"""Prepare same measured A handoff for pinned upstream DN-Splatter.

Supplied sensor_depth is an upstream API name: bytes are selected-candidate
expected depth, not a sensor measurement and never evaluation-only current UAS.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from src.phd.p2_ab_v1.reconstruction import SurfaceGaussians, View, render_view
from scripts.phd.p2_ab_v1.b_run import sha, write_json


def main(source, output, container_output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError("DN adapter output must be newly created")
    output.mkdir(parents=True)
    for sub in ("images", "depths", "masks"):
        (output / sub).mkdir()
    checkpoint = source / "surface_texturing/gaussians.pt"
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    xyz = state["base"].numpy()
    rgb = np.clip(state["sh0"][:, 0].numpy() * .28209479177387814 + .5, 0, 1)
    model = SurfaceGaussians(xyz, state["normal"].numpy(), state["log_scales"][:, 0].exp().numpy(),
                            rgb, state["group"].numpy(), displacement_axis="scene_z")
    model.load_state_dict(state)
    rows = json.loads((source / "views.json").read_text())["views"]
    frames, train, evaluate, receipts = [], [], [], []
    for row in rows:
        if "excluded" in row:
            continue
        iid = row["image_id"]
        image_path = Path(row["path"])
        if sha(image_path) != row["sha256"]:
            raise ValueError(f"Image bytes drift: {image_path}")
        image = cv2.imread(str(image_path))
        x0, y0, x1, y1 = row["crop_xyxy"]
        image = cv2.resize(image[y0:y1, x0:x1], (row["width"], row["height"]), interpolation=cv2.INTER_AREA)
        K, V = np.array(row["K"]), np.array(row["viewmat"])
        view = View(iid, row["role"], torch.zeros(row["height"], row["width"], 3, device="cuda"),
                    torch.tensor(K, dtype=torch.float32, device="cuda"),
                    torch.tensor(V, dtype=torch.float32, device="cuda"), row["width"], row["height"], row)
        with torch.no_grad():
            rendered = render_view(model, view)
        valid = rendered["alpha"].cpu().numpy() >= .5
        depth = np.where(valid, rendered["depth"].cpu().numpy(), 0).astype(np.float32)
        image_name = f"{row['role']}_{iid:04d}.png"
        cv2.imwrite(str(output / "images" / image_name), image)
        cv2.imwrite(str(output / "masks" / image_name), valid.astype(np.uint8) * 255)
        depth_name = f"{iid:04d}.npy"
        np.save(output / "depths" / depth_name, depth)
        path = str(Path(container_output) / "images" / image_name)
        c2w = np.linalg.inv(V) @ np.diag([1., -1., -1., 1.])
        frames.append({"file_path": path, "mask_path": str(Path(container_output) / "masks" / image_name),
                       "depth_file_path": str(Path(container_output) / "depths" / depth_name),
                       "transform_matrix": c2w.tolist(), "fl_x": float(K[0, 0]), "fl_y": float(K[1, 1]),
                       "cx": float(K[0, 2]), "cy": float(K[1, 2]), "w": row["width"], "h": row["height"],
                       "distortion_params": [0., 0., 0., 0., 0., 0.]})
        (train if row["role"] == "train" else evaluate).append(path)
        receipts.append({"image_id": iid, "role": row["role"], "valid_prior_depth_pixels": int(valid.sum()),
                         "depth_sha256": sha(output / "depths" / depth_name), "image_sha256": sha(output / "images" / image_name),
                         "mask_sha256": sha(output / "masks" / image_name)})
    header = f"ply\nformat ascii 1.0\nelement vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    with (output / "selected_source.ply").open("w") as stream:
        stream.write(header)
        for p, c in zip(xyz, (rgb * 255).astype(int)):
            stream.write(f"{p[0]:.9g} {p[1]:.9g} {p[2]:.9g} {c[0]} {c[1]} {c[2]}\n")
    write_json(output / "transforms.json", {"camera_model": "OPENCV", "orientation_override": "none",
               "frames": frames, "train_filenames": train, "val_filenames": evaluate,
               "test_filenames": evaluate, "ply_file_path": "selected_source.ply"})
    write_json(output / "adapter_receipt.json", {"source_run": str(source), "source_gaussians_sha256": sha(checkpoint),
               "source_handoff_sha256": sha(source / "handoff_receipt.json"), "points": len(xyz),
               "train_views": len(train), "eval_views": len(evaluate), "views": receipts,
               "depth_source": "same selected-candidate initial gsplat expected depth, not measured current depth",
               "normal_source": "upstream normal-from-rendered-depth consistency; upstream source-PCA normal initialization",
               "camera_axes": "OpenCV camera-to-world @ diag(1,-1,-1,1), scene XYZ unchanged",
               "scientific_verdict": None})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--container-output", required=True)
    args = parser.parse_args()
    main(args.source, args.output, args.container_output)
