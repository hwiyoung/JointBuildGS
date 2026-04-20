"""Offscreen 3D views of primitives for qualitative structural comparison.

No GPU renderer (Open3D EGL/pyrender not available in this container).
Uses custom orthographic rasterizer: project primitive centers → splat as
oriented disks into z-buffered image with Lambertian shading.

Color modes:
  - group:    random palette per group (L_structure assignment)
  - normal:   normal-as-RGB (|n|), highlights alignment
  - semantic: Roof/Wall/Terrain class color

Views:
  - top:      top-down (−gravity direction)
  - oblique:  3/4 perspective
  - wall:     side view of a selected wall-heavy bbox (cross-section)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch


def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)


def load_ckpt(path):
    sd = torch.load(path, map_location="cpu", weights_only=False)["state_dict"]
    means = sd["means"].numpy().astype(np.float32)
    quats = sd["quats"].numpy().astype(np.float32)
    log_scales = sd["log_scales"].numpy().astype(np.float32)
    sem_logits = sd["sem_logits"].numpy().astype(np.float32)
    opacities = torch.sigmoid(sd["opacities_raw"]).numpy().astype(np.float32)
    normals = qn(quats)
    normals = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
    scales = np.exp(log_scales)  # (N,2) for 2DGS
    return means, normals, scales, sem_logits, opacities


def compute_groups(means, normals, sem_logits, scales,
                   voxel_size=0.05, n_directions=12, min_group_size=5):
    import sys; sys.path.insert(0, ".")
    from src.stage2.grouping import group_primitives
    gids, rep_n, rep_d = group_primitives(
        centers=torch.from_numpy(means).cuda(),
        normals=torch.from_numpy(normals).cuda(),
        sem_logits=torch.from_numpy(sem_logits).cuda(),
        scales=torch.from_numpy(scales).cuda(),
        voxel_size=voxel_size, n_directions=n_directions,
        min_group_size=min_group_size,
    )
    return gids.cpu().numpy(), rep_n.cpu().numpy(), rep_d.cpu().numpy()


def make_camera(bbox_min, bbox_max, view, up_world=np.array([0., 0., 1.])):
    """Return (R_wc, t_wc, ortho_half_w, ortho_half_h) for orthographic view.
    R_wc: world→camera (3x3). Camera looks along +Z_cam.
    """
    center = 0.5 * (bbox_min + bbox_max)
    extent = bbox_max - bbox_min
    if view == "top":
        # look -Z (down)
        forward = -up_world
        right = np.array([1., 0., 0.])
        up_cam = np.array([0., 1., 0.])  # image up = +Y world
        half_w = 0.55 * extent[0]; half_h = 0.55 * extent[1]
    elif view == "oblique":
        forward = np.array([1., 1., -0.7]); forward /= np.linalg.norm(forward)
        # right perpendicular to forward in XY
        right = np.cross(forward, up_world); right /= np.linalg.norm(right)
        up_cam = np.cross(right, forward); up_cam /= np.linalg.norm(up_cam)
        half_w = 0.6 * max(extent[0], extent[1])
        half_h = 0.6 * max(extent[0], extent[1]) * 0.75
    elif view == "wall":
        # side view along +X
        forward = np.array([1., 0., 0.])
        right = np.array([0., -1., 0.])
        up_cam = np.array([0., 0., 1.])
        half_w = 0.55 * extent[1]; half_h = 0.55 * extent[2]
    elif view == "slice_y":
        # view along +Y (good for thin-Y slab = wall cross-section seen edge-on)
        forward = np.array([0., 1., 0.])
        right = np.array([1., 0., 0.])
        up_cam = np.array([0., 0., 1.])
        half_w = 0.55 * extent[0]; half_h = 0.55 * extent[2]
    elif view == "slice_x":
        # view along +X (good for thin-X slab = different wall orientation)
        forward = np.array([1., 0., 0.])
        right = np.array([0., 1., 0.])
        up_cam = np.array([0., 0., 1.])
        half_w = 0.55 * extent[1]; half_h = 0.55 * extent[2]
    elif view == "front":
        # 45° front oblique, looks good for single building
        forward = np.array([0.7, 0.7, -0.2]); forward /= np.linalg.norm(forward)
        right = np.cross(forward, up_world); right /= np.linalg.norm(right)
        up_cam = np.cross(right, forward); up_cam /= np.linalg.norm(up_cam)
        half_w = 0.6 * max(extent[0], extent[1])
        half_h = 0.6 * extent[2] * 1.3
    else:
        raise ValueError(view)
    # camera axes in world: x_cam=right, y_cam=up_cam, z_cam=forward
    R_wc = np.stack([right, up_cam, forward], axis=0)  # rows = cam axes in world
    t_wc = -R_wc @ center
    return R_wc, t_wc, half_w, half_h, center


def project_ortho(points, R_wc, t_wc, half_w, half_h, W, H):
    pc = points @ R_wc.T + t_wc  # (N,3)
    u = (pc[:, 0] + half_w) / (2 * half_w) * W
    v = (half_h - pc[:, 1]) / (2 * half_h) * H
    d = pc[:, 2]
    return u, v, d


def lambertian_shade(rgb, normals, light_dir):
    """rgb: (N,3) in [0,1], shade by max(0.25, n·L)."""
    ndl = np.clip(np.abs((normals * light_dir).sum(axis=1)), 0.25, 1.0)
    return rgb * ndl[:, None]


def render(points, normals, colors, opacities, R_wc, t_wc, half_w, half_h,
           W=900, H=720, point_size=1.8, light_dir=np.array([0.4, 0.4, 0.8])):
    """Orthographic splat rasterizer with z-buffer.
    point_size: pixel radius per primitive.
    """
    light_dir = light_dir / np.linalg.norm(light_dir)
    colors_shaded = lambertian_shade(colors, normals, light_dir)

    u, v, d = project_ortho(points, R_wc, t_wc, half_w, half_h, W, H)
    # cull
    r = int(max(1, point_size))
    ok = (u > -r) & (u < W + r) & (v > -r) & (v < H + r) & (opacities > 0.02)
    u, v, d = u[ok], v[ok], d[ok]
    cols = colors_shaded[ok]
    op = opacities[ok]

    img = np.ones((H, W, 3), dtype=np.float32)  # white bg
    zbuf = np.full((H, W), 1e9, dtype=np.float32)

    # sort far→near so near overwrites
    order = np.argsort(-d)
    u = u[order]; v = v[order]; d = d[order]; cols = cols[order]; op = op[order]

    ui = u.astype(np.int32); vi = v.astype(np.int32)
    # splat as r×r filled square per primitive
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            xi = ui + dx; yi = vi + dy
            m = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
            xim = xi[m]; yim = yi[m]; dm = d[m]; cm = cols[m]; om = op[m]
            # z-test
            cur = zbuf[yim, xim]
            winner = dm < cur
            xw = xim[winner]; yw = yim[winner]
            zbuf[yw, xw] = dm[winner]
            img[yw, xw] = cm[winner] * om[winner, None] + img[yw, xw] * (1 - om[winner, None])
    img = np.clip(img, 0, 1)
    return (img * 255).astype(np.uint8)


def color_group(gids, rng_seed=42):
    G = int(gids.max() + 1) if (gids >= 0).any() else 1
    rng = np.random.RandomState(rng_seed)
    palette = rng.uniform(0.2, 0.95, size=(max(G, 1), 3)).astype(np.float32)
    gray = np.array([0.55, 0.55, 0.55], dtype=np.float32)
    out = np.where((gids >= 0)[:, None], palette[np.maximum(gids, 0)], gray)
    return out


def color_normal(normals):
    return 0.5 * (np.abs(normals) + normals.clip(0, 1))  # [0,1]


def color_semantic(sem_logits):
    cls = sem_logits.argmax(axis=1)  # 0 BG, 1 Roof, 2 Wall, 3 Terrain
    pal = np.array([
        [0.55, 0.55, 0.55],  # BG gray
        [0.92, 0.35, 0.20],  # Roof red-orange
        [0.25, 0.55, 0.95],  # Wall blue
        [0.40, 0.75, 0.35],  # Terrain green
    ], dtype=np.float32)
    return pal[cls]


def save_png(img, path):
    from PIL import Image
    Image.fromarray(img).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--bbox", nargs=6, type=float, default=None,
                    help="xmin ymin zmin xmax ymax zmax; if unset → use auto percentile crop")
    ap.add_argument("--wall-bbox", nargs=6, type=float, default=None,
                    help="tight bbox for side cross-section; default: center 20%% slab")
    ap.add_argument("--views", nargs="+", default=["top", "oblique", "wall"])
    ap.add_argument("--modes", nargs="+", default=["group", "normal", "semantic"])
    ap.add_argument("--voxel-size", type=float, default=0.05)
    ap.add_argument("--n-directions", type=int, default=12)
    ap.add_argument("--min-group-size", type=int, default=5)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--point-size", type=float, default=1.8)
    args = ap.parse_args()

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    print(f"[{args.label}] loading {args.ckpt}")
    means, normals, scales, sem_logits, opacities = load_ckpt(args.ckpt)
    print(f"  primitives: {len(means)}")

    # auto bbox (percentile crop, robust to outliers)
    if args.bbox is None:
        lo = np.percentile(means, 1, axis=0)
        hi = np.percentile(means, 99, axis=0)
    else:
        lo = np.array(args.bbox[:3]); hi = np.array(args.bbox[3:])
    print(f"  bbox lo={lo} hi={hi}")

    # crop for rendering (keep outside for shading? we only render inside)
    in_bb = np.all((means >= lo) & (means <= hi), axis=1)
    means_c = means[in_bb]; normals_c = normals[in_bb]
    sem_c = sem_logits[in_bb]; scales_c = scales[in_bb]; op_c = opacities[in_bb]
    print(f"  after crop: {len(means_c)}")

    # groups (on full primitives to match training grouping; then mask)
    if "group" in args.modes:
        print(f"  grouping (voxel={args.voxel_size})...")
        gids_all, _, _ = compute_groups(means, normals, sem_logits, scales,
                                        args.voxel_size, args.n_directions, args.min_group_size)
        gids_c = gids_all[in_bb]
        G = int(gids_all.max() + 1) if (gids_all >= 0).any() else 0
        in_group = int((gids_all >= 0).sum())
        print(f"  groups: {G}, in-group: {in_group}/{len(gids_all)} ({in_group/max(1,len(gids_all))*100:.1f}%)")

    colors = {}
    if "group" in args.modes:    colors["group"] = color_group(gids_c)
    if "normal" in args.modes:   colors["normal"] = color_normal(normals_c)
    if "semantic" in args.modes: colors["semantic"] = color_semantic(sem_c)

    for view in args.views:
        if view == "wall" and args.wall_bbox is not None:
            wlo = np.array(args.wall_bbox[:3]); whi = np.array(args.wall_bbox[3:])
            R_wc, t_wc, hw, hh, _ = make_camera(wlo, whi, view)
            # further crop for wall view
            w_mask = np.all((means_c >= wlo) & (means_c <= whi), axis=1)
            p = means_c[w_mask]; n = normals_c[w_mask]; o = op_c[w_mask]
        else:
            R_wc, t_wc, hw, hh, _ = make_camera(lo, hi, view)
            p = means_c; n = normals_c; o = op_c; w_mask = None

        for mode, col in colors.items():
            c = col if w_mask is None else col[w_mask]
            img = render(p, n, c, o, R_wc, t_wc, hw, hh,
                         W=args.width, H=args.height, point_size=args.point_size)
            fname = f"{args.label}_{view}_{mode}.png"
            save_png(img, out / fname)
            print(f"  wrote {fname}")

    # metadata
    meta = {
        "label": args.label, "ckpt": args.ckpt,
        "n_primitives": int(len(means)), "n_cropped": int(len(means_c)),
        "bbox": {"lo": lo.tolist(), "hi": hi.tolist()},
    }
    if "group" in args.modes:
        meta["groups"] = {"n_groups": G, "in_group_frac": in_group / max(1, len(gids_all))}
    (out / f"{args.label}_meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
