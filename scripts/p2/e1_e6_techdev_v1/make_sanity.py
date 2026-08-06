from __future__ import annotations

import argparse
import json
from pathlib import Path

import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np

from src.stage2.dataloader import ColmapDataset


TASK_REL = Path("phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1")


def base_figure(rgb: np.ndarray, title: str):
    figure, axis = plt.subplots(figsize=(14, 10), dpi=120)
    axis.imshow(rgb)
    axis.set_title(title)
    axis.axis("off")
    return figure, axis


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    task = artifacts / TASK_REL
    prep = task / "prep"
    roles = json.loads((prep / "view_roles.json").read_text(encoding="utf-8"))
    name = roles["train_views"][0]
    dataset = ColmapDataset(
        artifacts / "phase-payloads/p0-audit/data/work/mvs/colmap_dense",
        downscale=1.0,
        load_depth=True,
        load_normal=True,
        load_semantic=False,
        visible_views=[name],
    )
    sample = dataset[0]
    rgb = sample["rgb"].numpy()
    stem = Path(name).stem
    outputs = {}

    out = task / "runs/E3_GS_IMAGE/sanity/mvs_depth_normal.png"
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        figure, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=120)
        axes[0].imshow(rgb); axes[0].set_title(f"E3 image: {name}")
        depth = sample["depth"].numpy(); mask = sample["depth_mask"].numpy()
        axes[1].imshow(np.where(mask, depth, np.nan), cmap="viridis"); axes[1].set_title("MVS depth c_mvs=1")
        normal = (sample["normal"].numpy() + 1.0) * 0.5
        axes[2].imshow(np.where(sample["normal_mask"].numpy()[..., None], normal, 0)); axes[2].set_title("MVS normal")
        for axis in axes: axis.axis("off")
        figure.tight_layout(); figure.savefig(out); plt.close(figure)
    outputs["E3"] = str(out)

    als_path = prep / f"als_prior/views/{stem}.npz"
    with np.load(als_path, allow_pickle=False) as als:
        for condition, label, weighted in (("E4_GS_ALS_UNWEIGHTED", "E4 w=1", False), ("E5_GS_ALS_WB", "E5 x w_b", True)):
            out = task / f"runs/{condition}/sanity/als_depth_weight_overlay.png"
            if not out.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                figure, axis = base_figure(rgb, f"{label}: {name}")
                value = als["building_weight"] if weighted else np.ones(len(als["pixel_x"]))
                scatter = axis.scatter(als["pixel_x"], als["pixel_y"], c=value, s=2, cmap="RdYlGn", vmin=0, vmax=1, alpha=0.7)
                figure.colorbar(scatter, ax=axis, label="prior weight")
                figure.tight_layout(); figure.savefig(out); plt.close(figure)
            outputs[condition[:2]] = str(out)

    lod_path = prep / f"lod_prior/views/{stem}.npz"
    with np.load(lod_path, allow_pickle=False) as lod:
        out = task / "runs/E6_GS_LOD2_PLANES_DIAGNOSTIC/sanity/lod_plane_correspondence_vectors.png"
        if not out.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            figure, axis = base_figure(rgb, f"E6 LoD plane correspondences: {name}")
            stride = max(1, len(lod["pixel_x"]) // 1500)
            x = lod["pixel_x"][::stride]; y = lod["pixel_y"][::stride]
            normal = lod["plane_normal_camera"][::stride]
            colour = np.where(lod["plane_kind"][::stride] == 1, "#7b2cbf", "#c77dff")
            axis.quiver(x, y, normal[:, 0], normal[:, 1], color=colour, angles="xy", scale_units="xy", scale=0.03, width=0.0015)
            figure.tight_layout(); figure.savefig(out); plt.close(figure)
        outputs["E6"] = str(out)
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.sanity.v1",
        "view": name,
        "outputs": outputs,
        "human_qa_required_but_nonblocking": True,
        "scientific_verdict": None,
    }
    (prep / "sanity_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
