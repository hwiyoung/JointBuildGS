#!/usr/bin/env python3
"""A-5 Omnidata mono-normal precheck for C001 roof crops."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import e5_c001_8way as eight  # noqa: E402
import e5_c001_pipeline_strips as strips  # noqa: E402


DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
PYDEPS = REPO / "results/tum_transfer/e5_s1_full_factor/C001/python_deps/timm_0_4_12"
TORCH_HOME = REPO / "results/tum_transfer/e5_s1_full_factor/C001/torch_hub"
FIG_DIR = REPO / "docs/figs/e5_c001_s1_full_factor/normal_precheck"
CSV_NORMAL = REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_normal_precheck.csv"
CSV_INSTALL = REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_normal_precheck_runtime.csv"
CSV_ISSUES = REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_normal_precheck_issues.csv"
TARGETS = {
    "textureless": ["4907199", "8568391", "8568392"],
    "defect": ["60098", "4907186", "4907188", "4907194", "4907195"],
    "normal": ["4907184", "4907202"],
}


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    text = str(p)
    prefix = "/workspace/JointBuildGS/"
    return text[len(prefix) :] if text.startswith(prefix) else text


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not fields:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def short_id(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def append_issue(rows: list[dict[str, Any]], building_id: str, message: str, path: Path | None = None) -> None:
    rows.append({"building_id": building_id, "message": message, "path": rel(path)})
    issues_md = REPO / "phases/p2-gsjso/docs/issues.md"
    if issues_md.exists():
        line = f"- 2026-07-09 A-5 normal precheck: {message}"
        if building_id:
            line += f" ({building_id})"
        if path:
            line += f" [{rel(path)}]"
        text = issues_md.read_text(encoding="utf-8")
        if line not in text:
            with issues_md.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def roof_normal_world(surface: eight.RoofSurface) -> np.ndarray:
    n = np.asarray([-surface.ax, -surface.by, 1.0], dtype=np.float64)
    n = n / max(np.linalg.norm(n), 1e-9)
    if n[2] < 0:
        n = -n
    return n


def square_crop(crop: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = crop
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    side = max(x1 - x0, y1 - y0, 128)
    x0 = int(round(cx - side / 2))
    y0 = int(round(cy - side / 2))
    x1 = x0 + int(side)
    y1 = y0 + int(side)
    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > width:
        x0 -= x1 - width
        x1 = width
    if y1 > height:
        y0 -= y1 - height
        y1 = height
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def normal_mode_count(normals_world: np.ndarray) -> int:
    if len(normals_world) < 64:
        return 0
    n = normals_world.copy()
    flip = n[:, 2] < 0
    n[flip] *= -1
    tilt = np.degrees(np.arccos(np.clip(n[:, 2], -1, 1)))
    sloped = tilt > 10.0
    if np.count_nonzero(sloped) < 40:
        return 0
    az = (np.degrees(np.arctan2(n[sloped, 1], n[sloped, 0])) + 360.0) % 180.0
    hist, _ = np.histogram(az, bins=np.linspace(0, 180, 19))
    threshold = max(8, 0.25 * float(hist.max()))
    peaks = 0
    for i, val in enumerate(hist):
        if val >= threshold and val >= hist[(i - 1) % len(hist)] and val >= hist[(i + 1) % len(hist)]:
            peaks += 1
    return peaks


def classify_angle(angle: float | None) -> str:
    if angle is None:
        return "not_measured"
    if angle < 15.0:
        return "good_lt15"
    if angle <= 30.0:
        return "borderline_15_30"
    return "bad_gt30"


def load_model(device_name: str) -> tuple[Any, Any, str]:
    if str(PYDEPS) not in sys.path:
        sys.path.insert(0, str(PYDEPS))
    os.environ.setdefault("TORCH_HOME", str(TORCH_HOME))
    import torch

    device = torch.device(device_name if device_name == "cpu" or torch.cuda.is_available() else "cpu")
    model = torch.hub.load("alexsax/omnidata_models", "surface_normal_dpt_hybrid_384", pretrained=True, trust_repo=True)
    model.to(device).eval()
    return model, device, torch.__version__


def run(args: argparse.Namespace) -> None:
    import torch
    import torch.nn.functional as F
    from PIL import Image
    from torchvision import transforms
    from src.stage2.dataloader import ColmapDataset

    model, device, torch_version = load_model(args.device)
    transform = transforms.Compose(
        [
            transforms.Resize(args.image_size, interpolation=Image.BILINEAR),
            transforms.CenterCrop(args.image_size),
            transforms.ToTensor(),
        ]
    )
    ids = [sid for group in TARGETS.values() for sid in group]
    group_by_id = {full_id(sid): group for group, group_ids in TARGETS.items() for sid in group_ids}
    footprints = strips.load_footprints(ids)
    refs_by_id = eight.parse_lod2_roofs(eight.LOD2_DIR, {full_id(x) for x in ids})
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=args.downscale, load_depth=False, load_normal=False, load_semantic=False)
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        bid = full_id(sid)
        fp = footprints.get(bid)
        refs = refs_by_id.get(bid, [])
        if fp is None or not refs:
            append_issue(issues, bid, "footprint or reference roof missing")
            continue
        view_idx, crop0 = strips.select_view(ds, fp, refs)
        batch = ds[view_idx]
        image = (batch["rgb"].numpy() * 255).astype(np.uint8)
        h, w = image.shape[:2]
        crop = square_crop(crop0, w, h)
        x0, y0, x1, y1 = crop
        crop_img = Image.fromarray(image[y0:y1, x0:x1]).convert("RGB")
        inp = transform(crop_img)[:3].unsqueeze(0).to(device)
        with torch.no_grad():
            pred = model(inp).clamp(0, 1)
        normal_cam = pred[0].permute(1, 2, 0).detach().cpu().numpy() * 2.0 - 1.0
        normal_cam = normal_cam / np.maximum(np.linalg.norm(normal_cam, axis=-1, keepdims=True), 1e-6)
        r = batch["w2c"].numpy()[:3, :3]
        flat_cam = normal_cam.reshape(-1, 3)
        flat_world = flat_cam @ r
        flat_world = flat_world / np.maximum(np.linalg.norm(flat_world, axis=1, keepdims=True), 1e-6)
        margin = int(args.image_size * 0.18)
        mask = np.zeros((args.image_size, args.image_size), dtype=bool)
        mask[margin : args.image_size - margin, margin : args.image_size - margin] = True
        sample_cam = flat_cam[mask.ravel()]
        sample_world = flat_world[mask.ravel()]
        ref_normals_world = np.vstack([roof_normal_world(s) for s in refs])
        ref_normals_cam = ref_normals_world @ r.T
        ref_normals_cam = ref_normals_cam / np.maximum(np.linalg.norm(ref_normals_cam, axis=1, keepdims=True), 1e-6)
        dots = np.abs(sample_cam @ ref_normals_cam.T)
        angles = np.degrees(np.arccos(np.clip(np.max(dots, axis=1), -1.0, 1.0))) if len(sample_cam) else np.asarray([])
        angle_med = float(np.median(angles)) if len(angles) else None
        angle_p75 = float(np.percentile(angles, 75)) if len(angles) else None
        mode_count = normal_mode_count(sample_world)
        normal_png = FIG_DIR / f"{short_id(bid)}_omnidata_normal.png"
        crop_png = FIG_DIR / f"{short_id(bid)}_image_crop.png"
        Image.fromarray(np.clip((normal_cam + 1.0) * 127.5, 0, 255).astype(np.uint8)).save(normal_png)
        crop_img.resize((args.image_size, args.image_size)).save(crop_png)
        fig, axes = plt.subplots(1, 2, figsize=(6.0, 3.0))
        axes[0].imshow(crop_img.resize((args.image_size, args.image_size)))
        axes[0].axis("off")
        axes[0].set_title("image crop")
        axes[1].imshow(np.clip((normal_cam + 1.0) / 2.0, 0, 1))
        axes[1].axis("off")
        axes[1].set_title("Omnidata normal")
        fig.suptitle(f"{sid} angle50={angle_med:.1f}" if angle_med is not None else sid, fontsize=10)
        fig.tight_layout()
        pair_png = FIG_DIR / f"{short_id(bid)}_normal_pair.png"
        fig.savefig(pair_png, dpi=160)
        plt.close(fig)
        rows.append(
            {
                "building_id": bid,
                "group": group_by_id.get(bid, ""),
                "model": "Omnidata DPT-Hybrid surface_normal_dpt_hybrid_384",
                "view_idx": view_idx,
                "image_name": str(batch.get("name", "")),
                "crop_xyxy": ",".join(str(v) for v in crop),
                "angle_error_median_deg_absdot": "" if angle_med is None else f"{angle_med:.4f}",
                "angle_error_p75_deg_absdot": "" if angle_p75 is None else f"{angle_p75:.4f}",
                "quality_bin_locked": classify_angle(angle_med),
                "normal_mode_count": mode_count,
                "gable_two_mode_proxy": str(mode_count >= 2).lower(),
                "normal_png": rel(normal_png),
                "image_crop_png": rel(crop_png),
                "pair_png": rel(pair_png),
                "note": "crop-level central pixels; camera-normal assumption; abs-dot angle to closest LoD2 roof-face normal",
            }
        )
        print(json.dumps({"building_id": bid, "angle_median": angle_med, "mode_count": mode_count}, ensure_ascii=False), flush=True)
    write_csv(CSV_NORMAL, rows)
    write_csv(CSV_ISSUES, issues, ["building_id", "message", "path"])
    write_csv(
        CSV_INSTALL,
        [
            {
                "runtime": "Omnidata torch.hub",
                "repo": "alexsax/omnidata_models",
                "model": "surface_normal_dpt_hybrid_384",
                "torch": torch_version,
                "timm_path": rel(PYDEPS),
                "torch_home": rel(TORCH_HOME),
                "weights_cached": str((TORCH_HOME / "hub/checkpoints/omnidata_normal_dpt_hybrid.pth").exists()).lower(),
                "dependency_note": "timm==0.4.12 installed run-locally with --no-deps; base image unchanged",
            }
        ],
    )
    print(json.dumps({"normal_precheck": rel(CSV_NORMAL), "rows": len(rows), "issues": len(issues)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--downscale", type=float, default=0.5)
    parser.add_argument("--image-size", type=int, default=384)
    return parser


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
