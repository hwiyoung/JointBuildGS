"""Render a paper-page-style 2DGS camera trajectory for the web viewer.

This does not draw surfel primitives in WebGL. It renders each frame with the
actual gsplat 2DGS rasterizer from existing MatrixCity camera poses, then the
browser plays those frames as a synchronized 4-way turntable/trajectory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml

sys.path.insert(0, ".")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


DEFAULT_CONDITIONS = [
    {
        "slug": "baseline",
        "label": "Baseline (Step 1-3)",
        "ckpt": "results/phase1_semantic/run/ckpt/final.pt",
    },
    {
        "slug": "mutual",
        "label": "Mutual (Step 1-4)",
        "ckpt": "results/phase1_mutual/run/ckpt/final.pt",
    },
    {
        "slug": "structure",
        "label": "Structure (Step 1-5)",
        "ckpt": "results/phase1_structure/run/ckpt/final.pt",
    },
    {
        "slug": "both",
        "label": "Both (Step 1-6)",
        "ckpt": "results/phase1_ablation/run/ckpt/final.pt",
    },
]


def resolve_repo_path(path: str | Path) -> Path:
    """Map historical /workspace/JointBuildGS paths to this checkout."""
    p = Path(path)
    if p.exists():
        return p
    text = str(path)
    prefix = "/workspace/JointBuildGS/"
    if text.startswith(prefix):
        local = Path(text[len(prefix):])
        if local.exists():
            return local
    return p


def load_model(ckpt: str | Path, cfg: dict, device: str, ds: ColmapDataset) -> GaussianModel2D:
    model = GaussianModel2D(
        ds.points_xyz,
        ds.points_rgb,
        sh_degree=cfg.get("sh_degree", 3),
        device=device,
    ).to(device)

    state = torch.load(resolve_repo_path(ckpt), map_location=device, weights_only=False)["state_dict"]
    for name, param in list(model.named_parameters()):
        tensor = state.get(name)
        if tensor is None:
            continue
        if param.shape != tensor.shape:
            obj = model
            parts = name.split(".")
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], torch.nn.Parameter(tensor.clone()))
        else:
            param.data.copy_(tensor)
    model.eval()
    return model


def selected_views(args: argparse.Namespace, n_dataset: int) -> list[int]:
    if args.views:
        views = args.views
    else:
        views = np.rint(np.linspace(args.start, args.end, args.frames)).astype(int).tolist()
    clamped = [max(0, min(n_dataset - 1, int(v))) for v in views]
    if len(set(clamped)) != len(clamped):
        print("warning: duplicate frame indices in selected trajectory", flush=True)
    return clamped


def write_jpeg(path: Path, rgb_float: np.ndarray, quality: int) -> None:
    rgb_u8 = (np.clip(rgb_float, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    imageio.imwrite(path, rgb_u8, quality=quality)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/input_and_alignment/matrixcity_step1_6.yaml")
    parser.add_argument("--out-dir", default="tools/gs3d_4way_viewer/assets/turntable_2dgs")
    parser.add_argument("--start", type=int, default=5083)
    parser.add_argument("--end", type=int, default=5528)
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument("--views", nargs="+", type=int)
    parser.add_argument("--scale", type=float, default=0.5, help="Output scale relative to config downscale.")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--white-bg", action="store_true")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    data_root = resolve_repo_path(cfg["data_root"])
    render_downscale = float(cfg.get("downscale", 1.0)) * float(args.scale)
    ds = ColmapDataset(
        data_root,
        downscale=render_downscale,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
    )
    views = selected_views(args, len(ds))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"dataset: {data_root} ({len(ds)} views)")
    print(f"rendering {len(views)} frames at downscale {render_downscale:g}")

    device = args.device
    bg = torch.ones(3, device=device) if args.white_bg else torch.zeros(3, device=device)
    manifest_conditions = []

    for condition in DEFAULT_CONDITIONS:
        slug = condition["slug"]
        label = condition["label"]
        frame_dir = out_dir / slug
        frame_dir.mkdir(parents=True, exist_ok=True)

        print(f"loading {label}: {condition['ckpt']}", flush=True)
        model = load_model(condition["ckpt"], cfg, device, ds)
        frame_files = []

        with torch.no_grad():
            for frame_no, view_idx in enumerate(views):
                batch = ds[view_idx]
                w2c = batch["w2c"].to(device)
                K = batch["K"].to(device)
                width = int(batch["width"])
                height = int(batch["height"])
                result = render(
                    model,
                    w2c,
                    K,
                    width,
                    height,
                    sh_degree=model.max_sh_degree,
                    render_mode="RGB+ED",
                    bg_color=bg,
                )
                frame_name = f"frame_{frame_no:03d}.jpg"
                frame_path = frame_dir / frame_name
                rgb = result["rgb"].detach().clamp(0, 1).cpu().numpy()
                write_jpeg(frame_path, rgb, args.quality)
                frame_files.append(f"{slug}/{frame_name}")
                print(f"  {label} frame {frame_no + 1:02d}/{len(views)} view {view_idx}", flush=True)

        del model
        torch.cuda.empty_cache()
        manifest_conditions.append(
            {
                "slug": slug,
                "label": label,
                "frames": frame_files,
            }
        )

    sample = ds[views[0]]
    manifest = {
        "type": "2dgs_rasterized_trajectory",
        "description": "Frames rendered by gsplat rasterization_2dgs from MatrixCity camera poses.",
        "config": args.config,
        "data_root": str(data_root),
        "start": views[0],
        "end": views[-1],
        "views": views,
        "frame_count": len(views),
        "width": int(sample["width"]),
        "height": int(sample["height"]),
        "scale": args.scale,
        "quality": args.quality,
        "conditions": manifest_conditions,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
