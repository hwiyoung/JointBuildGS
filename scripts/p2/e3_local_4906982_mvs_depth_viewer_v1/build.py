#!/usr/bin/env python3
"""Add COLMAP depth views and a distinct MVS-seed color to the 8878 review UI.

The host side only launches the project Docker image. Scientific raster
interpretation runs in-container; raw depth, images, cameras, and roles are
read-only inputs. The viewer extension is idempotent and records before/after
hashes in its own receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/e3_local_4906982_mvs_depth_viewer_v1/config.yaml"
IMAGE = "jointbuildgs:dev"
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"


def host_main() -> None:
    argv = [
        "docker", "run", "--rm", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "MPLCONFIGDIR=/tmp/matplotlib",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:rw",
        "-w", "/workspace/JointBuildGS", IMAGE,
        "python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvs_depth_viewer_v1/build.py",
        "--inside-docker", "--config", "/workspace/JointBuildGS/configs/p2/e3_local_4906982_mvs_depth_viewer_v1/config.yaml",
    ]
    raise SystemExit(subprocess.run(argv, cwd=REPO).returncode)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_json(path: Path, body: Any) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def colorize(values, mask, vmin: float, vmax: float, cmap_name: str = "turbo"):
    import numpy as np
    from matplotlib import colormaps

    normalized = np.clip((values - vmin) / max(vmax - vmin, 1e-6), 0.0, 1.0)
    rgb = np.rint(colormaps[cmap_name](normalized)[..., :3] * 255.0).astype(np.uint8)
    rgb[~mask] = 0
    return rgb


def labeled_image(rgb, *, title: str, subtitle: str, vmin: float, vmax: float):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    h, w = rgb.shape[:2]
    top, side = 58, 100
    canvas = Image.new("RGB", (w + side, h + top), (7, 11, 18))
    canvas.paste(Image.fromarray(rgb), (0, top))
    draw = ImageDraw.Draw(canvas)
    regular = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    draw.text((10, 6), title, fill=(240, 245, 250), font=bold)
    draw.text((10, 31), subtitle, fill=(185, 200, 218), font=regular)
    gradient = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]
    strip = colorize(gradient, np.ones_like(gradient, dtype=bool), 0.0, 1.0)
    strip = np.repeat(strip, 24, axis=1)
    canvas.paste(Image.fromarray(strip), (w + 12, top))
    draw.text((w + 40, top - 2), f"{vmax:.1f}m", fill=(225, 235, 245), font=regular)
    draw.text((w + 40, top + h - 18), f"{vmin:.1f}m", fill=(225, 235, 245), font=regular)
    return canvas


def inside_main(config_path: Path) -> None:
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import yaml

    from src.stage2.dataloader import ColmapDataset

    cfg = yaml.safe_load(config_path.read_text())
    viewer = Path(cfg["viewer_root"])
    manifest_path = viewer / "viewer_manifest.json"
    index_path = viewer / "index.html"
    app_path = viewer / "app.js"
    source_cfg = yaml.safe_load(Path(cfg["source_config"]).read_text())
    before = {name: sha256(path) for name, path in (("viewer_manifest.json", manifest_path), ("index.html", index_path), ("app.js", app_path))}
    manifest = json.loads(manifest_path.read_text())
    names = [row["view_name"] for row in manifest["views"]]
    if names != source_cfg["visible_views"]:
        raise RuntimeError("viewer/source view order drift")
    dataset = ColmapDataset(
        cfg["data_root"], downscale=1.0, load_depth=True, load_normal=False,
        load_semantic=False, visible_views=names,
    )
    width = int(cfg["render"]["width"]); height = int(cfg["render"]["height"])
    qlo, qhi = map(float, cfg["render"]["camera_depth_percentiles"])
    zmin, zmax = map(float, cfg["render"]["world_z_range_m"])
    depth_dir = viewer / "images/mvs_depth_camera_z"
    elevation_dir = viewer / "images/mvs_world_z_overlay"
    mvs_seed_dir = viewer / "images/mvs_seed_magenta"
    depth_dir.mkdir(parents=True, exist_ok=True); elevation_dir.mkdir(parents=True, exist_ok=True)
    mvs_seed_dir.mkdir(parents=True, exist_ok=True)
    source_by_name = {row["view_name"]: row for row in manifest["views"]}
    output_records = []
    for index, batch in enumerate(dataset, 1):
        name = batch["name"]
        row = source_by_name[name]
        depth_full = batch["depth"].numpy().astype(np.float32)
        mask_full = batch["depth_mask"].numpy().astype(bool) & np.isfinite(depth_full)
        depth = cv2.resize(depth_full, (width, height), interpolation=cv2.INTER_NEAREST)
        mask = cv2.resize(mask_full.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST).astype(bool)
        valid = depth[mask]
        if not len(valid): raise RuntimeError(f"empty depth: {name}")
        dlo, dhi = map(float, np.quantile(valid, [qlo, qhi]))
        camera_rgb = colorize(depth, mask, dlo, dhi)

        full_h, full_w = depth_full.shape
        sx, sy = width / full_w, height / full_h
        k = batch["K"].numpy().astype(np.float64).copy(); k[0, :] *= sx; k[1, :] *= sy
        w2c = batch["w2c"].numpy().astype(np.float64); c2w = np.linalg.inv(w2c)
        yy, xx = np.nonzero(mask); zz = depth[yy, xx].astype(np.float64)
        cam = np.column_stack(((xx - k[0, 2]) / k[0, 0] * zz, (yy - k[1, 2]) / k[1, 1] * zz, zz))
        world_z = np.full(depth.shape, np.nan, dtype=np.float32)
        world_z[yy, xx] = (cam @ c2w[:3, :3].T + c2w[:3, 3])[:, 2] + float(cfg["world_shift_z_m"])
        elevation_rgb = colorize(world_z, mask, zmin, zmax)

        original = np.asarray(Image.open(viewer / row["original"]).convert("RGB").resize((width, height), Image.Resampling.BILINEAR))
        # Preserve the original review raster and recolor only its projected MVS
        # points.  The footprint is shared by the sparse/MVS cards, so pixels
        # common to both overlays are excluded.  Write a separate PNG rather
        # than mutating the legacy JPEG; ``mvs_source`` keeps reruns idempotent.
        mvs_source_rel = row.get("mvs_source", row["mvs"])
        mvs_source = np.asarray(
            Image.open(viewer / mvs_source_rel).convert("RGB").resize(
                (width, height), Image.Resampling.BILINEAR
            )
        )
        sparse_source = np.asarray(
            Image.open(viewer / row["sparse"]).convert("RGB").resize(
                (width, height), Image.Resampling.BILINEAR
            )
        )
        delta_original = np.max(
            np.abs(mvs_source.astype(np.int16) - original.astype(np.int16)), axis=2
        )
        delta_sparse = np.max(
            np.abs(mvs_source.astype(np.int16) - sparse_source.astype(np.int16)), axis=2
        )
        mvs_seed_mask = (delta_original > 20) & (delta_sparse > 15)
        mvs_seed_rgb = original.copy()
        magenta = np.asarray([255, 43, 214], dtype=np.float32)
        mvs_seed_rgb[mvs_seed_mask] = np.rint(
            0.15 * original[mvs_seed_mask].astype(np.float32) + 0.85 * magenta
        ).astype(np.uint8)
        # Restore the exact shared footprint overlay from the legacy MVS card.
        shared_overlay = (delta_original > 20) & (delta_sparse <= 15)
        mvs_seed_rgb[shared_overlay] = mvs_source[shared_overlay]
        mvs_seed_rel = f"images/mvs_seed_magenta/{index:02d}_{Path(name).stem}.png"
        Image.fromarray(mvs_seed_rgb).save(viewer / mvs_seed_rel, optimize=True)
        row["mvs_source"] = mvs_source_rel
        row["mvs"] = mvs_seed_rel
        row["mvs_seed_color"] = "#ff2bd6"
        row["mvs_seed_recolored_pixel_count"] = int(mvs_seed_mask.sum())
        yellow = (original[..., 0] >= 180) & (original[..., 1] >= 130) & (original[..., 2] <= 100)
        camera_rgb[yellow] = (255, 224, 0); elevation_rgb[yellow] = (255, 224, 0)
        overlay = original.copy(); overlay[mask] = np.rint(0.42 * original[mask] + 0.58 * elevation_rgb[mask]).astype(np.uint8); overlay[yellow] = (255, 224, 0)

        wvalid = world_z[mask]
        stem = f"{index:02d}_{Path(name).stem}.jpg"
        depth_rel = f"images/mvs_depth_camera_z/{stem}"
        elev_rel = f"images/mvs_world_z_overlay/{stem}"
        stats = {
            "valid_pixels": int(mask_full.sum()), "valid_fraction": float(mask_full.mean()),
            "camera_depth_min_m": float(valid.min()), "camera_depth_median_m": float(np.median(valid)),
            "camera_depth_p98_m": float(np.quantile(valid, 0.98)), "camera_depth_max_m": float(valid.max()),
            "world_z_min_m": float(np.nanmin(wvalid)), "world_z_median_m": float(np.nanmedian(wvalid)),
            "world_z_p98_m": float(np.nanquantile(wvalid, 0.98)), "world_z_max_m": float(np.nanmax(wvalid)),
            "camera_display_range_m": [dlo, dhi], "world_z_display_range_m": [zmin, zmax],
        }
        depth_img = labeled_image(camera_rgb, title="COLMAP geometric depth · camera Z", subtitle=f"valid {100*stats['valid_fraction']:.1f}% · median {stats['camera_depth_median_m']:.2f}m · invalid=black · yellow=footprint", vmin=dlo, vmax=dhi)
        elev_img = labeled_image(overlay, title="MVS world elevation over RGB", subtitle=f"world Z median {stats['world_z_median_m']:.2f}m · p98 {stats['world_z_p98_m']:.2f}m · fixed scale", vmin=zmin, vmax=zmax)
        depth_img.save(viewer / depth_rel, quality=91, optimize=True)
        elev_img.save(viewer / elev_rel, quality=91, optimize=True)
        row["mvs_depth_camera_z"] = depth_rel
        row["mvs_world_z_overlay"] = elev_rel
        row["mvs_depth_stats"] = stats
        output_records.extend([
            {"path": mvs_seed_rel, "sha256": sha256(viewer / mvs_seed_rel)},
            {"path": depth_rel, "sha256": sha256(viewer / depth_rel)},
            {"path": elev_rel, "sha256": sha256(viewer / elev_rel)},
        ])

    capture_dir = viewer / "captures"; capture_dir.mkdir(exist_ok=True)
    reps = cfg["representative_views"]
    selected = [source_by_name[name] for name in reps]
    cell_w, cell_h = 760, 550
    title_h = 46
    sheet = Image.new("RGB", (cell_w * 3, (cell_h + title_h) * len(selected)), (7, 11, 18))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    for ridx, row in enumerate(selected):
        y = ridx * (cell_h + title_h)
        draw.text((10, y + 9), f"{row['view_name']} · {row['local_role']}", fill=(240, 245, 250), font=font)
        paths = [viewer / row["original"], viewer / row["mvs_depth_camera_z"], viewer / row["mvs_world_z_overlay"]]
        for cidx, path in enumerate(paths):
            image = Image.open(path).convert("RGB").resize((cell_w, cell_h), Image.Resampling.LANCZOS)
            sheet.paste(image, (cidx * cell_w, y + title_h))
    capture_path = capture_dir / "mvs_depth_nadir_oblique.png"
    sheet.save(capture_path, optimize=True)

    manifest["schema"] = "jointbuildgs.p2.e3_local_review_v1.viewer_manifest.mvs_depth.v1"
    manifest["mvs_depth_visualization"] = {
        "source": "COLMAP geometric-consistency depth", "view_count": len(names),
        "camera_depth_scale": "per-view p2-p98; invalid black",
        "world_z_scale_m": [zmin, zmax], "lod2_z_used": False,
        "capture": "captures/mvs_depth_nadir_oblique.png", "scientific_verdict": None,
    }
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    index = index_path.read_text()
    if 'id="mvsDepth"' not in index:
        old = '<article class="card"><h3>MVS seed · 비교용/미사용</h3><img id="mvs"></article>'
        new = old + '<article class="card"><h3>MVS geometric depth · camera Z</h3><img id="mvsDepth"></article><article class="card"><h3>MVS world-Z + RGB · 고정 555–670m</h3><img id="mvsWorldZ"></article>'
        if old not in index: raise RuntimeError("index card anchor drift")
        index = index.replace(old, new)
    index = index.replace('./app.js?v=20260807-3d-init-fix', './app.js?v=20260808-mvs-depth-v1')
    index = index.replace('./app.js?v=20260808-mvs-depth-detail-v2', './app.js?v=20260808-mvs-seed-color-v3')
    index = index.replace('./app.js?v=20260808-mvs-depth-v1', './app.js?v=20260808-mvs-seed-color-v3')
    index = index.replace('./app.js?v=20260808-mvs-seed-color-v2', './app.js?v=20260808-mvs-seed-color-v3')
    atomic_text(index_path, index)

    app = app_path.read_text()
    if "mvs_depth_camera_z" not in app:
        old = "for(const kind of ['original','sparse','mvs']) document.getElementById(kind).src=view[kind];"
        new = old + "\n  document.getElementById('mvsDepth').src=view.mvs_depth_camera_z; document.getElementById('mvsWorldZ').src=view.mvs_world_z_overlay;"
        if old not in app: raise RuntimeError("app image anchor drift")
        app = app.replace(old, new)
        old_meta = "sparse projected ${view.sparse_projected_count.toLocaleString()} · MVS projected ${view.mvs_projected_count.toLocaleString()}`;"
        new_meta = "sparse projected ${view.sparse_projected_count.toLocaleString()} · MVS projected ${view.mvs_projected_count.toLocaleString()}\\nMVS depth valid ${(100*view.mvs_depth_stats.valid_fraction).toFixed(1)}% · camera median ${view.mvs_depth_stats.camera_depth_median_m.toFixed(2)}m · world-Z median ${view.mvs_depth_stats.world_z_median_m.toFixed(2)}m · world-Z max ${view.mvs_depth_stats.world_z_max_m.toFixed(2)}m`;"
        if old_meta not in app: raise RuntimeError("app metadata anchor drift")
        app = app.replace(old_meta, new_meta)
    app = app.replace(
        "const mvs=await points(manifest.seed.mvs_xyz,null,'#fb923c',1.2);",
        "const mvs=await points(manifest.seed.mvs_xyz,null,'#ff2bd6',1.2);",
    )
    atomic_text(app_path, app)

    after = {name: sha256(path) for name, path in (("viewer_manifest.json", manifest_path), ("index.html", index_path), ("app.js", app_path))}
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_depth_viewer_v1.receipt.v1",
        "task_id": cfg["task_id"], "building_id": cfg["building_id"],
        "view_count": len(names), "depth_image_count": len(names),
        "overlay_image_count": len(names), "mvs_seed_recolor_count": len(names),
        "mvs_seed_color": "#ff2bd6", "before_sha256": before,
        "after_sha256": after, "generated_outputs": output_records,
        "capture": {"path": str(capture_path.relative_to(viewer)), "sha256": sha256(capture_path)},
        "raw_inputs_modified": False, "lod2_z_used": False, "scientific_verdict": None,
    }
    atomic_json(viewer / "mvs_depth_viewer_receipt.json", receipt)
    print(json.dumps({"status": "COMPLETE", "views": len(names), "capture": str(capture_path), "scientific_verdict": None}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--inside-docker", action="store_true"); parser.add_argument("--config", type=Path, default=CONFIG); args = parser.parse_args()
    if not args.inside_docker: host_main()
    inside_main(args.config)


if __name__ == "__main__":
    main()
