"""Qualitative check of the G2-validation table.

For a given building, render ONE PNG per top-K group. Each PNG has 4 panels
(perspective + top-down + front + side) at large size. The GT face that this
group matches best is drawn in BLUE (filled polygon + blue edge); the other
GT faces are in thin black for context.

Visual interpretation:
  - High match% (e.g. g206 97%): RED dots tightly cover the BLUE face → clean
    surface group.
  - Medium match% (e.g. g386 44%): RED dots span the BLUE face but bleed onto
    adjacent faces → group covers one wall but with slight scatter.
  - Low match% (e.g. g204 1%): RED dots far from the BLUE face → floater /
    misclassified group; not a real surface.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import quat_to_rotmat  # noqa: E402
from src.stage2.grouping import group_primitives_g2  # noqa: E402
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
from scripts.phase2_synthesis.run_stage3 import _assign_primitives_to_buildings  # noqa: E402

CLS_NAME = {0: "BG", 1: "Roof", 2: "Wall", 3: "Terrain"}
FACE_BLUE = (0.20, 0.55, 0.90)


def _closest_gt_face(group_centers, group_n, faces):
    n_unit = group_n / (np.linalg.norm(group_n) + 1e-9)
    cands = []
    for fi, f in enumerate(faces):
        fn = np.asarray(f['normal']); fn /= (np.linalg.norm(fn) + 1e-9)
        if abs(float(fn @ n_unit)) > 0.7:
            cands.append((fi, fn, np.asarray(f['centroid'])))
    if not cands:
        return -1, 0.0
    best_fi = np.full(group_centers.shape[0], -1, dtype=np.int64)
    best_d  = np.full(group_centers.shape[0], np.inf)
    for fi, fn, fc in cands:
        d = np.abs((group_centers - fc[None, :]) @ fn)
        m = d < best_d
        best_d[m] = d[m]
        best_fi[m] = fi
    if (best_fi >= 0).any():
        mode = int(np.bincount(best_fi[best_fi >= 0]).argmax())
        f = faces[mode]
        fn = np.asarray(f['normal']); fn /= np.linalg.norm(fn) + 1e-9
        fc = np.asarray(f['centroid'])
        d = np.abs((group_centers - fc[None, :]) @ fn)
        frac = float((d < 1.0).mean())
        return mode, frac
    return -1, 0.0


def _draw_2d(ax, axis_pair, cs_grp, cs_ctx, bldg, matched_face, lims):
    a, b = axis_pair
    # context primitives (other groups in same bldg) — light grey
    ax.scatter(cs_ctx[:, a], cs_ctx[:, b], c='lightgrey', s=4.0,
               alpha=0.3, edgecolor='none', zorder=1)
    # other GT faces — thin black outlines
    other = LineCollection(
        [seg for fi, f in enumerate(bldg['faces']) if fi != matched_face
         for seg in [
             [(f['vertices'][i, a], f['vertices'][i, b]),
              (f['vertices'][(i+1)%len(f['vertices']), a],
               f['vertices'][(i+1)%len(f['vertices']), b])]
             for i in range(len(f['vertices']))]],
        colors='black', linewidths=0.8, alpha=0.6, zorder=2)
    ax.add_collection(other)
    # matched GT face — blue filled polygon + thicker blue edges
    if matched_face >= 0:
        vs = bldg['faces'][matched_face]['vertices']
        poly = PolyCollection([np.column_stack([vs[:, a], vs[:, b]])],
                              facecolors=[(*FACE_BLUE, 0.25)],
                              edgecolors=[FACE_BLUE], linewidths=2.0, zorder=3)
        ax.add_collection(poly)
    # group primitives — red on top
    ax.scatter(cs_grp[:, a], cs_grp[:, b], c='red', s=18.0,
               alpha=0.9, edgecolor='none', zorder=4)
    ax.set_xlim(*lims[0]); ax.set_ylim(*lims[1])
    ax.set_aspect('equal'); ax.grid(alpha=0.3)


def render_one_group(out_path, bldg, gid, sz, cls_dom, n_norm,
                     matched_face, frac_match, cs_grp, cs_ctx):
    fig = plt.figure(figsize=(20, 6.5))
    face_n = bldg['faces'][matched_face]['normal'] if matched_face >= 0 else (0,0,0)
    face_mat = bldg['faces'][matched_face]['material'] if matched_face >= 0 else "—"
    face_area = bldg['faces'][matched_face]['area'] if matched_face >= 0 else 0
    title = (f"group g{gid}  size={sz}  class={CLS_NAME[cls_dom]}  "
             f"rep_n=({n_norm[0]:+.2f},{n_norm[1]:+.2f},{n_norm[2]:+.2f})\n"
             f"matched GT face #{matched_face} ({face_mat}, "
             f"n=({face_n[0]:+.2f},{face_n[1]:+.2f},{face_n[2]:+.2f}), "
             f"area={face_area:.1f}m²)   "
             f"→ {frac_match*100:.0f}% of red points within 1m of blue face plane")
    fig.suptitle(title, fontsize=12, family='monospace')

    gt_v = np.concatenate([f['vertices'] for f in bldg['faces']], axis=0)
    gt_mn = gt_v.min(0); gt_mx = gt_v.max(0); pad = 1.0
    xlim = (gt_mn[0]-pad, gt_mx[0]+pad)
    ylim = (gt_mn[1]-pad, gt_mx[1]+pad)
    zlim = (gt_mn[2]-pad, gt_mx[2]+pad)

    # 1) 3D perspective
    ax = fig.add_subplot(141, projection='3d')
    ax.scatter(cs_ctx[:, 0], cs_ctx[:, 1], cs_ctx[:, 2],
               c='lightgrey', s=2.0, alpha=0.25, edgecolor='none', depthshade=False)
    # other GT face edges
    other_segs = []
    for fi, f in enumerate(bldg['faces']):
        if fi == matched_face: continue
        vs = f['vertices']
        for i in range(len(vs)):
            other_segs.append([tuple(vs[i]), tuple(vs[(i+1)%len(vs)])])
    ax.add_collection3d(Line3DCollection(other_segs, colors='black', linewidths=0.8, alpha=0.5))
    # matched face — filled polygon + blue edges
    if matched_face >= 0:
        vs = bldg['faces'][matched_face]['vertices']
        poly3 = Poly3DCollection([vs], facecolors=[(*FACE_BLUE, 0.25)],
                                 edgecolors=[FACE_BLUE], linewidths=1.8)
        ax.add_collection3d(poly3)
    ax.scatter(cs_grp[:, 0], cs_grp[:, 1], cs_grp[:, 2],
               c='red', s=10.0, alpha=0.95, edgecolor='none', depthshade=False)
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_zlim(*zlim)
    ax.view_init(elev=22, azim=-50)
    ax.set_xlabel('X'); ax.set_ylabel('Y(UP)'); ax.set_zlabel('Z')
    ax.set_title("perspective", fontsize=11)

    # 2) top-down (XZ)
    ax = fig.add_subplot(142)
    _draw_2d(ax, (0, 2), cs_grp, cs_ctx, bldg, matched_face, (xlim, zlim))
    ax.set_title("top-down (XZ — both horizontal)", fontsize=11)
    ax.set_xlabel('X'); ax.set_ylabel('Z')

    # 3) front (XY)
    ax = fig.add_subplot(143)
    _draw_2d(ax, (0, 1), cs_grp, cs_ctx, bldg, matched_face, (xlim, ylim))
    ax.set_title("front (XY — Y vertical)", fontsize=11)
    ax.set_xlabel('X'); ax.set_ylabel('Y(UP)')

    # 4) side (ZY)
    ax = fig.add_subplot(144)
    _draw_2d(ax, (2, 1), cs_grp, cs_ctx, bldg, matched_face, (zlim, ylim))
    ax.set_title("side (ZY — Y vertical)", fontsize=11)
    ax.set_xlabel('Z'); ax.set_ylabel('Y(UP)')

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out_path, dpi=120, bbox_inches='tight')
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--scene", default="results/phase2_synthesis/scene.obj")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bid", type=int, default=21)
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--opa-thresh", type=float, default=0.30)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    sd = torch.load(args.ckpt, map_location="cpu")["state_dict"]
    means = sd["means"].float()
    quats = sd["quats"].float()
    log_scales = sd["log_scales"].float()
    sem_logits = sd["sem_logits"].float()
    opacities = torch.sigmoid(sd["opacities_raw"]).float()
    R = quat_to_rotmat(quats)
    normals = R[..., :, 2]
    scales = torch.exp(log_scales)
    labels_all = sem_logits.argmax(dim=-1).numpy()

    print(f"[table_check] running G2 ...")
    gid, rep_n, _ = group_primitives_g2(
        centers=means, normals=normals, sem_logits=sem_logits, scales=scales,
        voxel_size=2.0, merge_n_cos=0.92, merge_d_tol=0.5, min_group_size=30,
    )
    gid_np = gid.numpy()
    rep_n_np = rep_n.numpy()
    centers_np = means.numpy()
    opa_np = opacities.numpy()

    gt = parse_scene_obj(Path(args.scene))
    bldg = next((b for b in gt['buildings'] if b['building_id']==args.bid), None)
    if bldg is None:
        raise SystemExit(f"bid={args.bid} not found")
    prims_np = {"centers": centers_np, "opacities": opa_np}
    asgn = _assign_primitives_to_buildings(prims_np, gt, pad=2.0, opacity_thresh=0.05)
    idxs = asgn[args.bid]
    keep = opa_np[idxs] >= args.opa_thresh
    idxs = idxs[keep]

    cs_b = centers_np[idxs]
    gids_b = gid_np[idxs]
    labels_b = labels_all[idxs]

    valid = gids_b >= 0
    ug, cnt = np.unique(gids_b[valid], return_counts=True)
    order = np.argsort(-cnt)
    K = min(args.top_k, ug.size)
    print(f"[table_check] bid={args.bid}: {ug.size} groups, rendering top {K}")

    summary_rows = []
    for k in range(K):
        g = int(ug[order[k]])
        sz = int(cnt[order[k]])
        mg = gids_b == g
        cs_g = cs_b[mg]
        cs_ctx = cs_b[~mg]
        cls_b = labels_b[mg]
        cls_dom = int(np.bincount(cls_b).argmax())
        n_norm = rep_n_np[g]

        matched, frac = _closest_gt_face(cs_g, n_norm, bldg['faces'])
        out_path = out_dir / f"bldg_{args.bid:03d}_rank{k+1}_g{g}.png"
        render_one_group(out_path, bldg, g, sz, cls_dom, n_norm,
                         matched, frac, cs_g, cs_ctx)
        face_mat = bldg['faces'][matched]['material'] if matched >= 0 else "—"
        face_n = bldg['faces'][matched]['normal'] if matched >= 0 else (0,0,0)
        summary_rows.append((k+1, g, sz, CLS_NAME[cls_dom],
                             tuple(np.round(n_norm, 2)),
                             matched, face_mat, tuple(np.round(face_n, 2)),
                             frac))
        print(f"  rank {k+1}  g{g}  size={sz}  cls={CLS_NAME[cls_dom]}  "
              f"matched face #{matched}({face_mat})  "
              f"{frac*100:.0f}% within 1m  →  {out_path.name}")

    # also write a small summary text file
    sf = out_dir / f"bldg_{args.bid:03d}_summary.txt"
    with open(sf, "w") as f:
        f.write(f"bid={args.bid}  type={bldg.get('type','')}  "
                f"N_prims={idxs.size}  N_groups={ug.size}\n\n")
        f.write(f"{'rank':>4} {'gid':>5} {'size':>5} {'class':>7} "
                f"{'rep_n':>22} {'gt_face':>9} {'face_n':>22} {'match%':>7}\n")
        for r in summary_rows:
            rk, g, sz, cls, rn, mfi, mfm, fn, frac = r
            f.write(f"{rk:>4} {g:>5} {sz:>5} {cls:>7} "
                    f"({rn[0]:+.2f},{rn[1]:+.2f},{rn[2]:+.2f})  "
                    f"#{mfi}({mfm:>5}) "
                    f"({fn[0]:+.2f},{fn[1]:+.2f},{fn[2]:+.2f})  "
                    f"{frac*100:>5.0f}%\n")
    print(f"[table_check] summary → {sf}")


if __name__ == "__main__":
    main()
