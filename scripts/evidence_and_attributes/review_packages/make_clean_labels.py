#!/usr/bin/env python3
"""P2 make-or-break — clean semantic labels by raycasting reference LoD2 into the 937 GS poses.

Projects the reference CityGML LoD2 SEMANTIC SURFACES ONLY (RoofSurface->1, WallSurface->2,
GroundSurface->3; background/no-hit->0) into every training camera, producing
`<out>/<stem>.png` (uint8, 0..3) that the engine's ColmapDataset.load_semantic consumes.

NO geometry is imported into training — only per-pixel semantic class. The trained geometry
comes from images; these labels just tell the engine which Gaussians are roof/wall/ground.

Frame / coordinate convention (validated against prep-3/4):
  - GS-LOCAL = EPSG:25832 - SHIFT, SHIFT = [690953, 5336071, 604] (pure translation, orthometric).
  - Poses are COLMAP w2c (x_cam = R X + t, +Z forward, +Y down); camera centre C = -R^T t;
    ray dir for pixel (u,v) = R^T K^-1 [u, v, 1].

Outputs:
  - <out>/<stem>.png                 per-frame label (uint8 0..3) at the chosen downscale
  - <qa>/coverage.csv                per-frame class pixel fractions
  - <qa>/coverage_summary.json       aggregate coverage + per-target-building hit stats
  - <qa>/overlay_<stem>.png          RGB | colorized-label | blend, for sampled frames

Runs in the `dev` container (open3d 0.18 RaycastingScene + numpy + PIL). Engine code untouched.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image as PILImage
import open3d as o3d

# import COLMAP readers from the engine (read-only use)
_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402

GML_NS_GML = "http://www.opengis.net/gml"
CLASS_OF = {"RoofSurface": 1, "WallSurface": 2, "GroundSurface": 3}
CLASS_NAME = {0: "bg", 1: "roof", 2: "wall", 3: "ground"}
# colorize: bg black, roof red, wall green, ground blue
PALETTE = np.array([[0, 0, 0], [220, 40, 40], [40, 200, 60], [50, 90, 230]], dtype=np.uint8)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_poslist(text: str) -> np.ndarray:
    vals = [float(x) for x in text.split()]
    a = np.asarray(vals, dtype=np.float64).reshape(-1, 3)
    if len(a) >= 2 and np.allclose(a[0], a[-1]):
        a = a[:-1]
    return a


def extract_rings(gml_files, shift, aoi_min, aoi_max):
    """Yield (building_id, class_int, ring_xyz_local) for surfaces inside the AOI bbox."""
    rings = []
    counts = {1: 0, 2: 0, 3: 0}
    n_buildings = 0
    for gml in gml_files:
        ctx = ET.iterparse(str(gml), events=("end",))
        for _, elem in ctx:
            if _localname(elem.tag) != "Building":
                continue
            n_buildings += 1
            bid = elem.get("{%s}id" % GML_NS_GML)
            for surf in elem.iter():
                ln = _localname(surf.tag)
                if ln not in CLASS_OF:
                    continue
                cls = CLASS_OF[ln]
                for pl in surf.iter("{%s}posList" % GML_NS_GML):
                    if not pl.text:
                        continue
                    ring = parse_poslist(pl.text)
                    if len(ring) < 3:
                        continue
                    ring -= shift  # EPSG -> GS local
                    c = ring.mean(axis=0)
                    if (c[0] < aoi_min[0] or c[0] > aoi_max[0]
                            or c[1] < aoi_min[1] or c[1] > aoi_max[1]):
                        continue
                    rings.append((bid, cls, ring.astype(np.float64)))
                    counts[cls] += 1
            elem.clear()
    return rings, counts, n_buildings


def _point_in_tri(p, a, b, c):
    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(d) < 1e-18:
        return False
    s = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / d
    t = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / d
    return (s >= -1e-9) and (t >= -1e-9) and (s + t <= 1 + 1e-9)


def earclip(poly: np.ndarray):
    """Ear-clip a simple 2D polygon (n,2) -> list of index triples into poly. Handles concave."""
    n = len(poly)
    if n < 3:
        return []
    area = 0.5 * np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1])
    idxs = list(range(n))
    if area < 0:
        idxs = idxs[::-1]
    tris = []
    guard = 0
    while len(idxs) > 3 and guard < 100000:
        guard += 1
        m = len(idxs)
        ear = False
        for ii in range(m):
            i0, i1, i2 = idxs[(ii - 1) % m], idxs[ii], idxs[(ii + 1) % m]
            a, b, c = poly[i0], poly[i1], poly[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 1e-12:  # reflex or collinear
                continue
            ok = True
            for jj in idxs:
                if jj in (i0, i1, i2):
                    continue
                if _point_in_tri(poly[jj], a, b, c):
                    ok = False
                    break
            if ok:
                tris.append((i0, i1, i2))
                del idxs[ii]
                ear = True
                break
        if not ear:
            break
    if len(idxs) == 3:
        tris.append((idxs[0], idxs[1], idxs[2]))
    elif len(idxs) > 3:  # fallback fan for any remainder
        for k in range(1, len(idxs) - 1):
            tris.append((idxs[0], idxs[k], idxs[k + 1]))
    return tris


def newell_normal(ring: np.ndarray) -> np.ndarray:
    n = np.zeros(3)
    m = len(ring)
    for i in range(m):
        cur, nxt = ring[i], ring[(i + 1) % m]
        n[0] += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
        n[1] += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
        n[2] += (cur[0] - nxt[0]) * (cur[1] + nxt[1])
    nrm = np.linalg.norm(n)
    return n / nrm if nrm > 1e-12 else np.array([0.0, 0.0, 1.0])


def triangulate(ring: np.ndarray):
    nrm = newell_normal(ring)
    drop = int(np.argmax(np.abs(nrm)))
    keep = [i for i in range(3) if i != drop]
    poly2d = ring[:, keep]
    tri_idx = earclip(poly2d)
    return [(ring[i], ring[j], ring[k]) for (i, j, k) in tri_idx]


def build_scene(rings):
    V, T, tri_class, tri_bid = [], [], [], []
    voff = 0
    bids = []
    bid_index = {}
    n_degenerate = 0
    for (bid, cls, ring) in rings:
        if bid not in bid_index:
            bid_index[bid] = len(bids)
            bids.append(bid)
        bidx = bid_index[bid]
        tris = triangulate(ring)
        if not tris:
            n_degenerate += 1
            continue
        for (p, q, r) in tris:
            V.extend([p, q, r])
            T.append([voff, voff + 1, voff + 2])
            voff += 3
            tri_class.append(cls)
            tri_bid.append(bidx)
    V = np.asarray(V, dtype=np.float32)
    T = np.asarray(T, dtype=np.uint32)
    tri_class = np.asarray(tri_class, dtype=np.uint8)
    tri_bid = np.asarray(tri_bid, dtype=np.int32)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(V), o3d.core.Tensor(T))
    return scene, tri_class, tri_bid, bids, n_degenerate


def frame_rays(K, R, t, W, H):
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    us = np.arange(W, dtype=np.float64) + 0.5
    vs = np.arange(H, dtype=np.float64) + 0.5
    uu, vv = np.meshgrid(us, vs)
    x = (uu - cx) / fx
    y = (vv - cy) / fy
    z = np.ones_like(x)
    d_cam = np.stack([x, y, z], axis=-1).reshape(-1, 3)
    d_world = d_cam @ R  # row-vec: (R^T d_cam)^T
    d_world /= np.linalg.norm(d_world, axis=1, keepdims=True) + 1e-12
    C = -R.T @ t
    origins = np.broadcast_to(C, d_world.shape)
    rays = np.concatenate([origins, d_world], axis=1).astype(np.float32)
    return rays


def cast_labels(scene, tri_class, tri_bid, rays, H, W):
    ans = scene.cast_rays(o3d.core.Tensor(rays))
    prim = ans["primitive_ids"].numpy()
    hit = prim != o3d.t.geometry.RaycastingScene.INVALID_ID
    label = np.zeros(prim.shape[0], dtype=np.uint8)
    bidmap = np.full(prim.shape[0], -1, dtype=np.int32)
    label[hit] = tri_class[prim[hit].astype(np.int64)]
    bidmap[hit] = tri_bid[prim[hit].astype(np.int64)]
    return label.reshape(H, W), bidmap.reshape(H, W)


def colorize(label):
    return PALETTE[label]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gml", nargs="+", required=True)
    ap.add_argument("--data-root", required=True, help="contains images/ and sparse/[0]/")
    ap.add_argument("--out", required=True, help="output semantic/ dir (data_root/semantic)")
    ap.add_argument("--qa", required=True, help="QA output dir")
    ap.add_argument("--shift", nargs=3, type=float, default=[690953.0, 5336071.0, 604.0])
    ap.add_argument("--downscale", type=float, default=1.0)
    ap.add_argument("--aoi-margin", type=float, default=200.0)
    ap.add_argument("--targets", nargs="*", default=[
        "42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
        "4908166", "4908176", "4906969", "4908023", "4906972"])
    ap.add_argument("--n-overlay", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N frames")
    args = ap.parse_args()

    shift = np.asarray(args.shift, dtype=np.float64)
    out_dir = Path(args.out)
    qa_dir = Path(args.qa)
    out_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)
    target_bids = {f"DEBY_LOD2_{t}" for t in args.targets}

    # ---- poses ----
    root = Path(args.data_root)
    sparse = root / "sparse"
    if (sparse / "0" / "cameras.bin").exists():
        sparse = sparse / "0"
    cams = read_cameras_bin(sparse / "cameras.bin")
    imgs = read_images_bin(sparse / "images.bin")
    img_dir = root / "images"
    frames = []
    for img in imgs.values():
        if not (img_dir / img.name).exists():
            continue
        cam = cams[img.camera_id]
        frames.append((img.name, cam, img.R(), img.tvec.copy()))
    frames.sort(key=lambda f: f[0])
    if args.limit:
        frames = frames[:args.limit]
    print(f"[poses] {len(frames)} frames; camera model={frames[0][1].model}")

    # ---- AOI bbox from camera centres ----
    centres = np.array([(-fr[2].T @ fr[3]) for fr in frames])
    aoi_min = centres[:, :2].min(axis=0) - args.aoi_margin
    aoi_max = centres[:, :2].max(axis=0) + args.aoi_margin
    print(f"[aoi] camera-centre bbox (local XY) min={aoi_min} max={aoi_max} margin={args.aoi_margin}")

    # ---- mesh ----
    rings, counts, n_b = extract_rings(args.gml, shift, aoi_min, aoi_max)
    print(f"[gml] {n_b} buildings scanned; rings kept roof={counts[1]} wall={counts[2]} ground={counts[3]}")
    scene, tri_class, tri_bid, bids, n_deg = build_scene(rings)
    print(f"[mesh] {len(tri_class)} triangles ({(tri_class==1).sum()} roof / "
          f"{(tri_class==2).sum()} wall / {(tri_class==3).sum()} ground); "
          f"{len(bids)} buildings; degenerate-rings-skipped={n_deg}")
    bidx_of = {b: i for i, b in enumerate(bids)}
    target_idx = {b: bidx_of[b] for b in target_bids if b in bidx_of}
    print(f"[mesh] target buildings present in mesh: {len(target_idx)}/{len(target_bids)}")
    missing = sorted(target_bids - set(target_idx))
    if missing:
        print(f"[mesh] WARNING targets NOT in AOI mesh: {missing}")

    # ---- raycast all frames ----
    rows = []
    agg = np.zeros(4, dtype=np.float64)
    total_px = 0
    # per-target: best frame by hit count, and total frames seen
    best_frame = {b: ("", 0) for b in target_idx}
    frames_seen = {b: 0 for b in target_idx}
    for fi, (name, cam, R, t) in enumerate(frames):
        K = cam.K().copy()
        K[:2, :] *= args.downscale
        W = int(round(cam.width * args.downscale))
        H = int(round(cam.height * args.downscale))
        rays = frame_rays(K, R, t, W, H)
        label, bidmap = cast_labels(scene, tri_class, tri_bid, rays, H, W)
        PILImage.fromarray(label).save(out_dir / f"{Path(name).stem}.png")
        npx = H * W
        total_px += npx
        cls_counts = np.bincount(label.reshape(-1), minlength=4)[:4]
        agg += cls_counts
        rows.append([name, npx] + [int(c) for c in cls_counts]
                    + [round(float(cls_counts[k]) / npx, 5) for k in range(4)])
        # per-target stats
        for b, bidx in target_idx.items():
            hc = int((bidmap == bidx).sum())
            if hc > 0:
                frames_seen[b] += 1
                if hc > best_frame[b][1]:
                    best_frame[b] = (name, hc)
        if (fi + 1) % 100 == 0 or fi == len(frames) - 1:
            print(f"[raycast] {fi+1}/{len(frames)}")

    # ---- coverage csv ----
    with (qa_dir / "coverage.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "npx", "bg_px", "roof_px", "wall_px", "ground_px",
                    "bg_frac", "roof_frac", "wall_frac", "ground_frac"])
        w.writerows(rows)

    summary = {
        "n_frames": len(frames),
        "downscale": args.downscale,
        "mesh_triangles": int(len(tri_class)),
        "mesh_buildings": len(bids),
        "ring_counts": {CLASS_NAME[k]: int(counts[k]) for k in (1, 2, 3)},
        "aggregate_fraction": {CLASS_NAME[k]: round(float(agg[k] / total_px), 5) for k in range(4)},
        "mean_frame_fraction": {
            CLASS_NAME[k]: round(float(np.mean([r[6 + k] for r in rows])), 5) for k in range(4)},
        "frames_with_roof_gt_1pct": int(sum(1 for r in rows if r[7] > 0.01)),
        "frames_with_wall_gt_1pct": int(sum(1 for r in rows if r[8] > 0.01)),
        "targets_in_mesh": sorted(target_idx.keys()),
        "targets_missing_from_mesh": missing,
        "target_frames_seen": {b: frames_seen[b] for b in target_idx},
        "target_best_frame": {b: {"frame": best_frame[b][0], "hit_px": best_frame[b][1]}
                              for b in target_idx},
    }
    (qa_dir / "coverage_summary.json").write_text(json.dumps(summary, indent=2))
    print("[summary]\n" + json.dumps(summary, indent=2))

    # ---- overlays for sampled frames ----
    overlay_names = []
    for b in target_idx:
        if best_frame[b][0]:
            overlay_names.append(best_frame[b][0])
    roof_sorted = sorted(rows, key=lambda r: r[7], reverse=True)
    for r in roof_sorted:
        if r[0] not in overlay_names:
            overlay_names.append(r[0])
        if len(overlay_names) >= args.n_overlay:
            break
    overlay_names = list(dict.fromkeys(overlay_names))[:args.n_overlay]
    fr_by_name = {fr[0]: fr for fr in frames}
    for name in overlay_names:
        _, cam, R, t = fr_by_name[name]
        K = cam.K().copy(); K[:2, :] *= args.downscale
        W = int(round(cam.width * args.downscale)); H = int(round(cam.height * args.downscale))
        rays = frame_rays(K, R, t, W, H)
        label, _ = cast_labels(scene, tri_class, tri_bid, rays, H, W)
        rgb = PILImage.open(img_dir / name).convert("RGB").resize((W, H), PILImage.BILINEAR)
        rgb = np.asarray(rgb, dtype=np.uint8)
        col = colorize(label)
        blend = rgb.copy()
        m = label > 0
        blend[m] = (0.45 * rgb[m] + 0.55 * col[m]).astype(np.uint8)
        panel = np.concatenate([rgb, col, blend], axis=1)
        PILImage.fromarray(panel).save(qa_dir / f"overlay_{Path(name).stem}.png")
    print(f"[overlay] wrote {len(overlay_names)} overlays -> {qa_dir}")


if __name__ == "__main__":
    main()
