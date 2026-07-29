#!/usr/bin/env python3
"""Prepare E5 C001 block training inputs and configs.

Creates a C001-only COLMAP-style data root by cropping images, semantic labels,
and PatchMatch depth/normal maps to the projected block AOI.  It also clips the
three prepared seed point clouds to the same AOI buffer and writes six configs
for {sparse,dense,acmp} x {r1,r2}.  No training is run here.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image as PILImage

from src.stage2.colmap_io import (
    CAMERA_MODEL_NAMES,
    Camera,
    Image,
    read_array,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


SHIFT = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
DEFAULT_BUFFER_M = 20.0
RUN_ID = "e5p_train_20260707_C001"
TARGET = "C001"
RANDOM_SEEDS = {"r1": 1001, "r2": 1002}
ARMS = ("sparse", "dense", "acmp")
BASE_CONFIGS = {
    "sparse": Path("configs/tum_mob/gs_d4_sparse.yaml"),
    "dense": Path("configs/tum_mob/gs_d4_dense.yaml"),
    "acmp": Path("configs/tum_mob/gs_d4_acmp.yaml"),
}
SOURCE_SEEDS = {
    "sparse": Path("results/tum_transfer/mob_analysis/seed/seed_sparse.ply"),
    "dense": Path("results/tum_transfer/mob_analysis/seed/seed_dense.ply"),
    "acmp": Path("results/tum_transfer/mob_analysis/seed/seed_acmp.ply"),
}
SOURCE_DATA = Path("results/tum_transfer/data_geoidfix")
SOURCE_SPARSE = SOURCE_DATA / "sparse/0"
FOOTPRINTS = Path("results/tum_transfer/analysis/footprints_aoi.geojson")
CANDIDATES = Path("docs/experiments/e5_pilot_block/tables/e5_pilot_block_candidates.csv")


def cmd_out(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def read_candidate() -> dict[str, str]:
    with CANDIDATES.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["candidate_id"] == TARGET:
                return row
    raise RuntimeError(f"{TARGET} not found in {CANDIDATES}")


def load_footprint_boxes(building_ids: list[str], buffer_m: float) -> tuple[list[list[float]], list[float]]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    wanted = set(building_ids)
    boxes = []
    for feat in payload["features"]:
        bid = feat["properties"].get("building_id")
        if bid not in wanted:
            continue
        geom = feat["geometry"]
        ring = np.asarray(geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0])
        boxes.append(
            [
                float(ring[:, 0].min() - buffer_m),
                float(ring[:, 1].min() - buffer_m),
                float(ring[:, 0].max() + buffer_m),
                float(ring[:, 1].max() + buffer_m),
            ]
        )
    if len(boxes) != len(wanted):
        got = len(boxes)
        raise RuntimeError(f"found {got}/{len(wanted)} C001 footprints")
    arr = np.asarray(boxes, dtype=np.float64)
    union = [float(arr[:, 0].min()), float(arr[:, 1].min()), float(arr[:, 2].max()), float(arr[:, 3].max())]
    return boxes, union


def project(points: np.ndarray, image: Image, camera: Camera) -> np.ndarray:
    Xc = (image.R() @ points.T).T + image.tvec.reshape(1, 3)
    z = Xc[:, 2]
    out = np.full((len(points), 3), np.nan, dtype=np.float64)
    ok = z > 1e-3
    if not np.any(ok):
        return out
    K = camera.K()
    uvw = (K @ Xc[ok].T).T
    out[ok, 0] = uvw[:, 0] / uvw[:, 2]
    out[ok, 1] = uvw[:, 1] / uvw[:, 2]
    out[ok, 2] = z[ok]
    return out


def sample_block_volume(union_utm: list[float], z_range_local: tuple[float, float]) -> np.ndarray:
    x0, y0, x1, y1 = union_utm
    xs = np.linspace(x0 - SHIFT[0], x1 - SHIFT[0], 5)
    ys = np.linspace(y0 - SHIFT[1], y1 - SHIFT[1], 5)
    zs = np.linspace(z_range_local[0], z_range_local[1], 5)
    pts = np.array([[x, y, z] for x in xs for y in ys for z in zs], dtype=np.float64)
    return pts


def read_ascii_ply_xyz(path: Path) -> np.ndarray:
    import open3d as o3d

    pc = o3d.io.read_point_cloud(str(path))
    xyz = np.asarray(pc.points, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise RuntimeError(f"empty or invalid PLY: {path}")
    return xyz


def write_ascii_ply_xyz(path: Path, xyz: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("ply\nformat ascii 1.0\n")
        fh.write(f"element vertex {len(xyz)}\n")
        fh.write("property float x\nproperty float y\nproperty float z\nend_header\n")
        for x, y, z in xyz:
            fh.write(f"{x:.6f} {y:.6f} {z:.6f}\n")


def clip_seed_clouds(seed_dir: Path, union_utm: list[float], buffer_m: float) -> dict[str, dict[str, Any]]:
    _ = buffer_m
    x0, y0, x1, y1 = union_utm
    lx0, ly0, lx1, ly1 = x0 - SHIFT[0], y0 - SHIFT[1], x1 - SHIFT[0], y1 - SHIFT[1]
    out: dict[str, dict[str, Any]] = {}
    for arm, src in SOURCE_SEEDS.items():
        xyz = read_ascii_ply_xyz(src)
        mask = (xyz[:, 0] >= lx0) & (xyz[:, 0] <= lx1) & (xyz[:, 1] >= ly0) & (xyz[:, 1] <= ly1)
        clipped = xyz[mask]
        if len(clipped) == 0:
            raise RuntimeError(f"{arm} seed clip is empty for {TARGET}")
        dest = seed_dir / f"seed_{arm}_C001_buf20.ply"
        write_ascii_ply_xyz(dest, clipped)
        out[arm] = {
            "source": str(src),
            "path": str(dest),
            "source_points": int(len(xyz)),
            "clipped_points": int(len(clipped)),
            "sha256": sha256_file(dest),
        }
    return out


def write_cameras_bin(path: Path, cameras: dict[int, Camera]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(struct.pack("<Q", len(cameras)))
        for cam_id in sorted(cameras):
            cam = cameras[cam_id]
            model_id, nparams = CAMERA_MODEL_NAMES[cam.model]
            params = np.asarray(cam.params, dtype=np.float64)
            if len(params) != nparams:
                raise RuntimeError(f"{cam.model} expected {nparams} params, got {len(params)}")
            fh.write(struct.pack("<iiQQ", int(cam.id), int(model_id), int(cam.width), int(cam.height)))
            fh.write(struct.pack("<" + "d" * nparams, *params.tolist()))


def write_images_bin(path: Path, images: dict[int, Image]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(struct.pack("<Q", len(images)))
        for image_id in sorted(images):
            im = images[image_id]
            fh.write(struct.pack("<I", int(im.id)))
            fh.write(struct.pack("<dddd", *np.asarray(im.qvec, dtype=np.float64).tolist()))
            fh.write(struct.pack("<ddd", *np.asarray(im.tvec, dtype=np.float64).tolist()))
            fh.write(struct.pack("<I", int(im.camera_id)))
            fh.write(im.name.encode("utf-8") + b"\x00")
            fh.write(struct.pack("<Q", 0))


def write_points3d_bin(path: Path, xyzrgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(struct.pack("<Q", len(xyzrgb)))
        for i, row in enumerate(xyzrgb, 1):
            x, y, z, r, g, b = row
            fh.write(struct.pack("<Q", i))
            fh.write(struct.pack("<ddd", float(x), float(y), float(z)))
            fh.write(struct.pack("<BBB", int(r), int(g), int(b)))
            fh.write(struct.pack("<d", 0.0))
            fh.write(struct.pack("<Q", 0))


def adjust_camera(cam: Camera, cam_id: int, crop: tuple[int, int, int, int]) -> Camera:
    x0, y0, x1, y1 = crop
    params = np.asarray(cam.params, dtype=np.float64).copy()
    if cam.model == "SIMPLE_PINHOLE":
        params[1] -= x0
        params[2] -= y0
    elif cam.model in {"PINHOLE"}:
        params[2] -= x0
        params[3] -= y0
    elif cam.model in {"SIMPLE_RADIAL", "SIMPLE_RADIAL_FISHEYE"}:
        params[1] -= x0
        params[2] -= y0
    elif cam.model in {"RADIAL", "RADIAL_FISHEYE"}:
        params[1] -= x0
        params[2] -= y0
    elif cam.model in {"OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"}:
        params[2] -= x0
        params[3] -= y0
    else:
        raise RuntimeError(f"unsupported camera model for crop: {cam.model}")
    return Camera(cam_id, cam.model, x1 - x0, y1 - y0, params)


def write_colmap_array(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(arr, dtype=np.float32)
    h, w = arr.shape[:2]
    ch = 1 if arr.ndim == 2 else arr.shape[2]
    with path.open("wb") as fh:
        fh.write(f"{w}&{h}&{ch}&".encode("ascii"))
        arr.tofile(fh)


def crop_optional_maps(
    name: str,
    crop: tuple[int, int, int, int],
    image_size_wh: tuple[int, int],
    data_root: Path,
    out_root: Path,
) -> dict[str, int]:
    x0, y0, x1, y1 = crop
    image_w, image_h = image_size_wh
    counts = {"depth": 0, "normal": 0, "semantic": 0}
    for kind, subdir in [("depth", "depth_maps"), ("normal", "normal_maps")]:
        for suffix in [".geometric.bin", ".photometric.bin"]:
            src = data_root / "stereo" / subdir / f"{name}{suffix}"
            if not src.exists():
                continue
            arr = read_array(src)
            ah, aw = arr.shape[:2]
            mx0 = max(0, min(aw - 1, int(math.floor(x0 * aw / image_w))))
            my0 = max(0, min(ah - 1, int(math.floor(y0 * ah / image_h))))
            mx1 = max(mx0 + 1, min(aw, int(math.ceil(x1 * aw / image_w))))
            my1 = max(my0 + 1, min(ah, int(math.ceil(y1 * ah / image_h))))
            write_colmap_array(out_root / "stereo" / subdir / f"{name}{suffix}", arr[my0:my1, mx0:mx1, ...])
            counts[kind] += 1
    sem_src = data_root / "semantic" / f"{Path(name).stem}.png"
    if sem_src.exists():
        sem = PILImage.open(sem_src)
        sem.crop((x0, y0, x1, y1)).save(out_root / "semantic" / f"{Path(name).stem}.png")
        counts["semantic"] += 1
    return counts


def prepare_data_root(out_root: Path, union_utm: list[float], z_range_local: tuple[float, float], buffer_m: float) -> dict[str, Any]:
    cameras = read_cameras_bin(SOURCE_SPARSE / "cameras.bin")
    images = read_images_bin(SOURCE_SPARSE / "images.bin")
    volume = sample_block_volume(union_utm, z_range_local)
    out_images: dict[int, Image] = {}
    out_cameras: dict[int, Camera] = {}
    selected_rows = []
    map_counts = {"depth": 0, "normal": 0, "semantic": 0}
    image_out = out_root / "images"
    image_out.mkdir(parents=True, exist_ok=True)
    (out_root / "semantic").mkdir(parents=True, exist_ok=True)

    for im_id, im in sorted(images.items(), key=lambda kv: kv[1].name):
        cam = cameras[im.camera_id]
        uvz = project(volume, im, cam)
        finite = np.isfinite(uvz[:, 0]) & np.isfinite(uvz[:, 1]) & (uvz[:, 2] > 0)
        if not np.any(finite):
            continue
        uv = uvz[finite, :2]
        in_frame = (uv[:, 0] >= -100) & (uv[:, 0] <= cam.width + 100) & (uv[:, 1] >= -100) & (uv[:, 1] <= cam.height + 100)
        if not np.any(in_frame):
            continue
        uv = uv[in_frame]
        pad_px = 96
        x0 = max(0, int(math.floor(float(uv[:, 0].min()) - pad_px)))
        y0 = max(0, int(math.floor(float(uv[:, 1].min()) - pad_px)))
        x1 = min(cam.width, int(math.ceil(float(uv[:, 0].max()) + pad_px)))
        y1 = min(cam.height, int(math.ceil(float(uv[:, 1].max()) + pad_px)))
        if x1 - x0 < 128 or y1 - y0 < 128:
            continue
        src_img = SOURCE_DATA / "images" / im.name
        if not src_img.exists():
            continue
        crop = (x0, y0, x1, y1)
        PILImage.open(src_img).crop(crop).save(image_out / im.name)
        cam_id = int(im_id)
        out_cameras[cam_id] = adjust_camera(cam, cam_id, crop)
        out_images[im_id] = Image(im.id, im.qvec.copy(), im.tvec.copy(), cam_id, im.name)
        counts = crop_optional_maps(im.name, crop, (cam.width, cam.height), SOURCE_DATA, out_root)
        for key, value in counts.items():
            map_counts[key] += value
        selected_rows.append(
            {
                "image_id": im_id,
                "name": im.name,
                "crop_x0": x0,
                "crop_y0": y0,
                "crop_x1": x1,
                "crop_y1": y1,
                "crop_w": x1 - x0,
                "crop_h": y1 - y0,
                **counts,
            }
        )

    if len(out_images) < 10:
        raise RuntimeError(f"too few C001 crop views: {len(out_images)}")
    sparse_out = out_root / "sparse/0"
    write_cameras_bin(sparse_out / "cameras.bin", out_cameras)
    write_images_bin(sparse_out / "images.bin", out_images)

    pts = read_points3d_bin(SOURCE_SPARSE / "points3D.bin")
    x0, y0, x1, y1 = union_utm
    lx0, ly0, lx1, ly1 = x0 - SHIFT[0], y0 - SHIFT[1], x1 - SHIFT[0], y1 - SHIFT[1]
    mask = (pts[:, 0] >= lx0) & (pts[:, 0] <= lx1) & (pts[:, 1] >= ly0) & (pts[:, 1] <= ly1)
    pts_clip = pts[mask]
    if len(pts_clip) < 10:
        # Keep the model initialisable even in sparse COLMAP holes.  The MVS seed
        # still supplies the arm-specific evidence; these are only base SfM points.
        ctr = np.array([0.5 * (lx0 + lx1), 0.5 * (ly0 + ly1), np.mean(z_range_local)], dtype=np.float64)
        rgb = np.array([128, 128, 128], dtype=np.float64)
        pts_clip = np.column_stack([ctr + np.random.default_rng(0).normal(scale=0.5, size=(32, 3)), np.tile(rgb, (32, 1))])
    write_points3d_bin(sparse_out / "points3D.bin", pts_clip)

    view_csv = out_root.parent / "C001_view_crops.csv"
    with view_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(selected_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected_rows)

    return {
        "data_root": str(out_root),
        "selected_views": len(out_images),
        "sfm_points_clipped": int(len(pts_clip)),
        "view_crop_csv": str(view_csv),
        "map_counts": map_counts,
        "crop_size_median": {
            "w": float(np.median([r["crop_w"] for r in selected_rows])),
            "h": float(np.median([r["crop_h"] for r in selected_rows])),
        },
    }


def infer_z_range(seed_stats: dict[str, dict[str, Any]], pad_m: float = 15.0) -> tuple[float, float]:
    vals = []
    for info in seed_stats.values():
        path = Path(info["path"])
        xyz = read_ascii_ply_xyz(path)
        if len(xyz):
            vals.extend([float(np.percentile(xyz[:, 2], 1)), float(np.percentile(xyz[:, 2], 99))])
    if not vals:
        return -90.0, 50.0
    return float(min(vals) - pad_m), float(max(vals) + pad_m)


def write_configs(config_dir: Path, seed_stats: dict[str, dict[str, Any]], data_root: Path, building_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        base_path = BASE_CONFIGS[arm]
        base_cfg = yaml.safe_load(base_path.read_text(encoding="utf-8"))
        for rep, seed in RANDOM_SEEDS.items():
            run_name = f"gs_e5_C001_{arm}_{rep}"
            cfg = dict(base_cfg)
            cfg["seed"] = seed
            cfg["data_root"] = f"/workspace/JointBuildGS/{data_root.as_posix()}"
            cfg["init_pointcloud"] = f"/workspace/JointBuildGS/{seed_stats[arm]['path']}"
            cfg["seed_log_buildings"] = building_ids
            cfg["out_dir"] = f"/workspace/JointBuildGS/results/tum_transfer/e5_pilot/C001/runs/{run_name}"
            dest = config_dir / f"{run_name}.yaml"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
            diff = "\n".join(
                difflib.unified_diff(
                    base_path.read_text(encoding="utf-8").splitlines(),
                    dest.read_text(encoding="utf-8").splitlines(),
                    fromfile=str(base_path),
                    tofile=str(dest),
                    lineterm="",
                )
            )
            diff_path = config_dir / f"{run_name}.diff"
            diff_path.write_text(diff + "\n", encoding="utf-8")
            out[run_name] = {
                "arm": arm,
                "replicate": rep,
                "seed": seed,
                "config": str(dest),
                "diff": str(diff_path),
                "out_dir": cfg["out_dir"].replace("/workspace/JointBuildGS/", ""),
                "base_config": str(base_path),
            }
    return out


def markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# E5 Pilot Train Prep",
        "",
        "> B단계 준비 재료. 판정 문구 없이 지문과 관찰만 기록한다.",
        "",
        f"- Candidate: `{TARGET}`",
        f"- Buffer: {payload['buffer_m']:.1f} m",
        f"- Data root: `{payload['data_root']['data_root']}`",
        f"- Selected crop views: {payload['data_root']['selected_views']}",
        f"- C001 buildings: {len(payload['building_ids'])}",
        f"- 관측기하 기록: 선정 규칙에는 관측기하 조건이 없었고, 미학습 지역 전체가 관측 열세라는 판정 부속 사실을 기록한다. C001 `frac_views_incidence_le60` 범위는 {payload['view_geometry']['c001_frac_views_incidence_le60_min']:.3f}..{payload['view_geometry']['c001_frac_views_incidence_le60_max']:.3f}; 판정 회신의 미학습 지역 최고값 기록은 0.7이다.",
        "",
        "## Seed Clips",
        "",
        "| seed | source points | clipped points | path |",
        "|---|---:|---:|---|",
    ]
    for arm in ARMS:
        item = payload["seed_clips"][arm]
        lines.append(f"| {arm} | {item['source_points']} | {item['clipped_points']} | `{item['path']}` |")
    lines += [
        "",
        "## Configs",
        "",
        "| run | arm | replicate | random seed | config | out_dir |",
        "|---|---|---|---:|---|---|",
    ]
    for run_name, item in payload["configs"].items():
        lines.append(
            f"| {run_name} | {item['arm']} | {item['replicate']} | {item['seed']} | "
            f"`{item['config']}` | `{item['out_dir']}` |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buffer-m", type=float, default=DEFAULT_BUFFER_M)
    parser.add_argument("--out-root", default="results/tum_transfer/e5_pilot/C001")
    parser.add_argument("--config-dir", default="configs/tum_mob/e5_pilot")
    parser.add_argument("--versions", default=f"phases/p2-gsjso/runs/{RUN_ID}/versions.txt")
    parser.add_argument("--report", default="docs/experiments/e5_pilot/reports/e5_pilot_train_prep.md")
    args = parser.parse_args()

    out_root = Path(args.out_root)
    config_dir = Path(args.config_dir)
    cand = read_candidate()
    building_ids = cand["building_ids"].split(";")
    _, union_utm = load_footprint_boxes(building_ids, args.buffer_m)

    seed_dir = out_root / "seeds"
    seed_stats = clip_seed_clouds(seed_dir, union_utm, args.buffer_m)
    z_range = infer_z_range(seed_stats)
    data_root = out_root / f"data_geoidfix_C001_buf{int(args.buffer_m)}"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_stats = prepare_data_root(data_root, union_utm, z_range, args.buffer_m)
    configs = write_configs(config_dir, seed_stats, data_root, building_ids)

    aux_rows = {r["building_id"]: r for r in csv.DictReader(open("docs/experiments/population_aux/tables/population_aux_v4.csv", newline="", encoding="utf-8"))}
    geom_vals = [float(aux_rows[b]["frac_views_incidence_le60"]) for b in building_ids]
    payload = {
        "run_id": RUN_ID,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": cmd_out(["git", "rev-parse", "HEAD"]),
        "git_branch": cmd_out(["git", "branch", "--show-current"]),
        "candidate": cand,
        "building_ids": building_ids,
        "buffer_m": args.buffer_m,
        "union_bbox_utm_buffered": union_utm,
        "world_offset": SHIFT.tolist(),
        "z_range_local": list(z_range),
        "seed_clips": seed_stats,
        "data_root": data_stats,
        "configs": configs,
        "view_geometry": {
            "selection_rule_had_view_geometry_condition": False,
            "human_note_untrained_region_view_geometry_max": 0.7,
            "c001_frac_views_incidence_le60_min": min(geom_vals),
            "c001_frac_views_incidence_le60_max": max(geom_vals),
            "c001_frac_views_incidence_le60_median": float(np.median(geom_vals)),
            "c001_n_views_nadir_max": max(float(aux_rows[b]["n_views_nadir"]) for b in building_ids),
        },
    }
    manifest = out_root / "C001_train_prep_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_report(Path(args.report), payload)

    versions = Path(args.versions)
    versions.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {payload['created_utc']}",
        "task: E5-B1 train prep C001 block crop",
        "mode: data/config preparation only; no training in this script",
        "crs: EPSG:25832",
        f"git_head: {payload['git_head']}",
        f"git_branch: {payload['git_branch']}",
        "docker_image: jointbuildgs:dev",
        f"python: {cmd_out(['python3', '--version'])}",
        f"buffer_m: {args.buffer_m}",
        f"manifest: {manifest}",
        f"report: {args.report}",
        f"selected_views: {data_stats['selected_views']}",
        f"sfm_points_clipped: {data_stats['sfm_points_clipped']}",
        "",
        "configs:",
    ]
    for run_name, item in configs.items():
        lines.append(f"  {run_name}: {item['config']}")
    versions.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest), "selected_views": data_stats["selected_views"], "configs": len(configs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
