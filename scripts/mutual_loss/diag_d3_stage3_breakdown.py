"""D3: Stage 3 6-step breakdown — self-explanatory per-step figure.

For 4 buildings (one per major roof type) × 4 conditions, render the
intermediate state at each Stage 3 step. Designed to make divergence
points obvious without external explanation:

  Step 1: filtered primitives (point cloud, semantic-colored)
  Step 2: clusters (one color per group, with rep-plane normal arrows)
  Step 3: representative planes only (centers + normals, before intersection)
  Step 4: convex polytope output (faces with edges)
  Step 5: ground surface added
  Step 6: final CityJSON colored by val3dity validity (blue=valid, red=invalid)

Layout: 4 conditions stacked vertically, 6 steps left-to-right per building.
Each cell has fixed view angle (top-perspective), no Y inversion confusion.
Annotations show key counts (n_groups, n_faces, val3dity codes).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa
from scripts.stage3_readout.run_stage3 import _load_model, _build_primitives_dict  # noqa
from src.stage3.clustering import cluster_primitives  # noqa
from src.stage3.ground_surface import (
    orient_normals_outward, add_ground_surface, add_bbox_planes,  # noqa
)
from src.stage3.plane_intersection import build_convex_polytope  # noqa
from src.stage3.citygml_export import build_cityjson  # noqa


CONDS = ["baseline", "mutual", "structure", "both"]
COND_COLORS = {"baseline": "#888888", "mutual": "#4C9AFF",
               "structure": "#FFB040", "both": "#20A050"}
SEM_COLOR = {1: "#C53030", 2: "#2C5582", 3: "#A0AEC0"}
N_STEPS = 6


# Fixed view: scene.obj uses Y-down (Y=0 ground, Y<0 above). Use a perspective
# that shows building from elevated front.
def _set_view(ax, pts):
    if len(pts) == 0:
        return
    pts = np.asarray(pts)
    mn = pts.min(0); mx = pts.max(0)
    c = (mn + mx) / 2; r = (mx - mn).max() / 2 * 1.1
    if r < 1e-6: r = 1
    # Set X / Z range; Y is vertical (negative = up in scene.obj)
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    # Y goes from mx[1] (low ground) to mn[1] (high roof, more negative)
    ax.set_ylim(mx[1] + 1, mn[1] - 1)  # inverted in axis but values monotonic
    # View: elevated, looking down at building
    ax.view_init(elev=18, azim=-65)
    ax.set_box_aspect((1, 0.5, 1))
    # Hide ticks for compactness
    ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])


def run_stage3_steps(prims, bid, gt):
    b_gt = next(b for b in gt["buildings"] if b["building_id"] == bid)
    all_v = np.concatenate([f["vertices"] for f in b_gt["faces"]], axis=0)
    mn, mx = all_v.min(0) - 2, all_v.max(0) + 2
    mask = ((prims["centers"] >= mn) & (prims["centers"] <= mx)).all(axis=1)
    mask &= prims["opacities"] >= 0.05
    sel = np.where(mask)[0]
    if len(sel) < 10: return None
    centers = prims["centers"][sel]
    normals = prims["normals"][sel]
    areas = prims["areas"][sel]
    sem = prims["semantic_probs"][sel]
    labels = sem.argmax(axis=1)

    state = {"step1": {"centers": centers.copy(), "labels": labels.copy()}}

    # Step 2: cluster
    groups = cluster_primitives(centers, normals, areas, labels, cos_thresh=0.85)
    for g in groups:
        g["prim_ids_local"] = list(g["prim_ids"])  # local ids
        g["prim_ids"] = [int(sel[i]) for i in g["prim_ids"]]
    bc = centers.mean(axis=0)
    orient_normals_outward(groups, bc)
    wall_mask = labels == 2
    add_ground_surface(groups, centers[wall_mask], bc)
    n_bbox = add_bbox_planes(groups, centers)

    # Save step2 + step3 group metadata
    state["groups"] = [{
        "prim_ids_local": g.get("prim_ids_local", []),
        "class": int(g["class"]),
        "plane_normal": [float(x) for x in g["plane_normal"]],
        "plane_d": float(g["plane_d"]),
        "is_ground": bool(g.get("is_ground", False)),
        "is_bbox": bool(g.get("is_bbox", False)),
    } for g in groups]
    state["n_groups_total"] = len(groups)
    state["n_groups_real"] = sum(1 for g in groups if not g.get("is_bbox"))
    state["n_walls_in_clusters"] = sum(1 for g in groups
                                          if g["class"] == 2 and not g.get("is_bbox"))

    # Step 4: convex polytope
    polygons = build_convex_polytope(groups, centers, hs_tol=0.05)
    state["polygons"] = None
    if polygons is not None:
        # Convert to plain dict
        state["polygons"] = {int(k): np.asarray(v).tolist() for k, v in polygons.items()}

    # Step 6: build CityJSON + val3dity
    bdir = ROOT / "results/phase2_ablation_citygml/_diag/d3"
    bdir.mkdir(parents=True, exist_ok=True)
    state["cityjson_path"] = None
    state["val3dity_valid"] = None
    state["val3dity_codes"] = []
    if polygons and len(polygons) >= 4:
        sub = bdir / "tmp"
        sub.mkdir(exist_ok=True)
        result = build_cityjson(bid, groups, polygons, str(sub))
        if result:
            cj = Path(result["cityjson_path"])
            rp = sub / "val3dity.json"
            try:
                subprocess.run(["val3dity", "--report", str(rp), str(cj)],
                                capture_output=True, timeout=60)
                if rp.exists():
                    v3 = json.loads(rp.read_text())
                    feats = v3.get("features", [])
                    if feats:
                        state["val3dity_valid"] = bool(feats[0].get("validity", False))
                        state["val3dity_codes"] = [e.get("code") for e in feats[0].get("errors", [])]
            except Exception:
                pass
    return state


def render_step(ax, step_idx: int, state: dict, gt_bldg: dict, ann_text: str):
    """Render a single step in the given 3D axis."""
    if state is None:
        ax.text2D(0.5, 0.5, "no data", ha="center", transform=ax.transAxes)
        ax.set_title(ann_text, fontsize=8)
        return

    centers = state["step1"]["centers"]
    labels = state["step1"]["labels"]
    groups = state.get("groups", [])
    polygons = state.get("polygons")

    if step_idx == 0:  # Step 1: classified primitives
        for cls, color in SEM_COLOR.items():
            m = labels == cls
            if m.sum() > 0:
                ax.scatter(centers[m, 0], centers[m, 1], centers[m, 2],
                            c=color, s=2, alpha=0.5, edgecolors="none")
        _set_view(ax, centers)

    elif step_idx == 1:  # Step 2: clusters (semantic groups only)
        cmap = plt.get_cmap("tab20")
        i = 0
        for g in groups:
            if g.get("is_bbox") or g.get("is_ground"): continue
            pids = g["prim_ids_local"]
            if not pids: continue
            pts = centers[pids]
            ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2],
                        c=[cmap(i % 20)], s=2.5, alpha=0.6, edgecolors="none")
            i += 1
        _set_view(ax, centers)

    elif step_idx == 2:  # Step 3: representative planes (rep normal quivers)
        for g in groups:
            if g.get("is_bbox"): continue
            pids = g["prim_ids_local"]
            if len(pids) < 2: continue
            c = centers[pids].mean(axis=0)
            n = np.array(g["plane_normal"])
            cls = g["class"]
            color = "#718096" if g.get("is_ground") else SEM_COLOR.get(cls, "#808080")
            scale = (np.ptp(centers, axis=0).max()) * 0.1
            ax.scatter([c[0]], [c[1]], [c[2]], c=[color], s=35,
                        edgecolor="k", linewidth=0.5)
            ax.quiver(c[0], c[1], c[2], n[0]*scale, n[1]*scale, n[2]*scale,
                       color=color, arrow_length_ratio=0.3, linewidth=1.0)
        _set_view(ax, centers)

    elif step_idx == 3:  # Step 4: convex polytope
        if polygons:
            all_v = []
            for gi, pts in polygons.items():
                pts_arr = np.asarray(pts)
                if len(pts_arr) < 3: continue
                all_v.append(pts_arr)
                gi_int = int(gi)
                g_info = groups[gi_int] if gi_int < len(groups) else {}
                color = "#718096" if g_info.get("is_ground") else \
                        SEM_COLOR.get(g_info.get("class", 0), "#888")
                ax.add_collection3d(Poly3DCollection(
                    [pts_arr], alpha=0.55, facecolor=color,
                    edgecolor="k", linewidth=0.5))
            if all_v:
                _set_view(ax, np.vstack(all_v))
            else:
                _set_view(ax, centers)

    elif step_idx == 4:  # Step 5: ground surface (highlighted)
        if polygons:
            all_v = []
            for gi, pts in polygons.items():
                pts_arr = np.asarray(pts)
                if len(pts_arr) < 3: continue
                all_v.append(pts_arr)
                gi_int = int(gi)
                g_info = groups[gi_int] if gi_int < len(groups) else {}
                if g_info.get("is_ground"):
                    color = "#A78BFA"  # purple highlight for ground
                    edge = "#5B21B6"
                    lw = 1.2
                else:
                    color = SEM_COLOR.get(g_info.get("class", 0), "#888")
                    edge = "k"; lw = 0.4
                ax.add_collection3d(Poly3DCollection(
                    [pts_arr], alpha=0.55, facecolor=color,
                    edgecolor=edge, linewidth=lw))
            if all_v:
                _set_view(ax, np.vstack(all_v))

    elif step_idx == 5:  # Step 6: final CityJSON, color by val3dity
        valid = state.get("val3dity_valid")
        if polygons:
            all_v = []
            for gi, pts in polygons.items():
                pts_arr = np.asarray(pts)
                if len(pts_arr) < 3: continue
                all_v.append(pts_arr)
                color = "#3182CE" if valid else "#E53E3E"
                ax.add_collection3d(Poly3DCollection(
                    [pts_arr], alpha=0.6, facecolor=color,
                    edgecolor="k", linewidth=0.5))
            if all_v:
                _set_view(ax, np.vstack(all_v))

    ax.set_title(ann_text, fontsize=7)


def make_figure_for_building(bid: int, gt: dict, prims_cache: dict, out_png: Path):
    """One figure per building: 4 conditions × 6 steps."""
    fig = plt.figure(figsize=(N_STEPS * 3.0, len(CONDS) * 2.6))
    b_gt = next(b for b in gt["buildings"] if b["building_id"] == bid)
    btype = b_gt.get("type", "?")

    states = {}
    for cond in CONDS:
        if cond not in prims_cache:
            ck = ROOT / "results/phase2_ablation_citygml" / cond / "ckpt/final.pt"
            m = _load_model(ck)
            prims_cache[cond] = _build_primitives_dict(m) | {"opacities": m["opacities"]}
        prims = prims_cache[cond]
        st = run_stage3_steps(prims, bid, gt)
        states[cond] = st
        if st:
            print(f"    [{cond}] groups={st.get('n_groups_real')} "
                  f"walls={st.get('n_walls_in_clusters')} "
                  f"polytope_faces={len(st.get('polygons') or {})} "
                  f"valid={st.get('val3dity_valid')} "
                  f"errs={st.get('val3dity_codes')}")

    step_titles_short = [
        "Step 1\nFilter primitives",
        "Step 2\nCluster",
        "Step 3\nRepresentative planes",
        "Step 4\nConvex polytope",
        "Step 5\n+ Ground surface",
        "Step 6\nCityJSON + val3dity",
    ]

    for ri, cond in enumerate(CONDS):
        st = states[cond]
        for ci, title in enumerate(step_titles_short):
            ax = fig.add_subplot(len(CONDS), N_STEPS, ri * N_STEPS + ci + 1, projection="3d")
            # Compose annotation per (cond, step)
            ann = title
            if st:
                if ci == 0:
                    n = len(st["step1"]["labels"])
                    nr = (st["step1"]["labels"] == 1).sum()
                    nw = (st["step1"]["labels"] == 2).sum()
                    ann = f"{title}\nN={n} R={nr} W={nw}"
                elif ci == 1:
                    ann = f"{title}\n{st.get('n_groups_real',0)} groups, walls={st.get('n_walls_in_clusters',0)}"
                elif ci == 2:
                    ann = f"{title}\n(rep n + group center)"
                elif ci == 3:
                    nf = len(st.get('polygons') or {})
                    ann = f"{title}\n{nf} faces"
                elif ci == 4:
                    ann = f"{title}\nshell closing"
                elif ci == 5:
                    valid = st.get('val3dity_valid')
                    codes = st.get('val3dity_codes', [])
                    if valid is None:
                        ann = f"{title}\nN/A"
                    elif valid:
                        ann = f"{title}\n✓ VALID"
                    else:
                        unique_codes = sorted(set(codes))
                        ann = f"{title}\n✗ codes {unique_codes}"
            render_step(ax, ci, st, b_gt, ann)
            if ci == 0:
                ax.text2D(-0.1, 0.5, cond, transform=ax.transAxes,
                          fontsize=11, weight="bold", rotation=90,
                          va="center", ha="center",
                          color=COND_COLORS[cond])

    plt.suptitle(f"D3: Stage 3 pipeline 6 steps for building_{bid:03d} ({btype})\n"
                 f"Each row: condition. Each column: pipeline step. "
                 f"Watch where output diverges across conditions.",
                 fontsize=11, weight="bold", y=1.005)
    plt.tight_layout()
    plt.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {out_png}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--bids", nargs="+", type=int,
                     default=[2, 22, 6, 21],  # flat, gable, hip, complex
                     help="building IDs to render")
    args = ap.parse_args()

    scene = parse_scene_obj(str(ROOT / "results/phase2_synthesis/scene.obj"))
    figures_dir = ROOT / "results/phase2_ablation_citygml/figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    prims_cache = {}
    for bid in args.bids:
        b = next((b for b in scene["buildings"] if b["building_id"] == bid), None)
        if b is None:
            print(f"bid={bid} not in scene"); continue
        print(f"=== bid={bid} ({b['type']}) ===")
        out_png = figures_dir / f"fig_d3_bid{bid:03d}_steps.png"
        make_figure_for_building(bid, scene, prims_cache, out_png)


if __name__ == "__main__":
    main()
