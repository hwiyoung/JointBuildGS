"""D1: Mutual regression case study — bid=1 (flat) Baseline vs Mutual.

Baseline passes val3dity on bid=1, Mutual fails. Track the Stage 3 pipeline
step-by-step on both conditions, record per-step counts + geometry, save a
side-by-side 5-panel figure + a JSON with per-step diffs.

For each of {Baseline, Mutual} on bid=1:
  Step 1 — filter primitives (opacity, semantic)
  Step 2 — cluster into groups (cos + proximity), log n_groups + size dist
  Step 3 — orient + add ground + bbox planes
  Step 4 — half-space intersection → convex polytope (vertices, faces)
  Step 5 — CityJSON mesh (after Step 6 quantize)
  Step 6 — val3dity outcome + error codes

Save:
  results/phase2_ablation_citygml/_diag/d1/{condition}_step{N}.npz / .json
  results/phase2_ablation_citygml/figures/fig_d1_mutual_regression.png
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
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa
from scripts.phase2_synthesis.run_stage3 import (  # noqa
    _load_model, _build_primitives_dict,
)
from src.stage3.clustering import cluster_primitives  # noqa
from src.stage3.ground_surface import (  # noqa
    orient_normals_outward, add_ground_surface, add_bbox_planes,
)
from src.stage3.plane_intersection import build_convex_polytope  # noqa
from src.stage3.citygml_export import build_cityjson  # noqa

BIDS_DEFAULT = [22, 2]  # gable (most regression), flat (canonical case)
CONDS = ["baseline", "mutual", "structure", "both"]
COND_COLORS = {"baseline": "#888888", "mutual": "#4C9AFF",
               "structure": "#FFB040", "both": "#20A050"}
SEM_COLOR = {1: "#C53030", 2: "#2C5582", 3: "#A0AEC0"}


def _set_3d(ax, pts):
    if len(pts) == 0:
        return
    pts = np.asarray(pts)
    mn = pts.min(0); mx = pts.max(0)
    c = (mn + mx) / 2; r = (mx - mn).max() / 2 * 1.1
    if r < 1e-6: r = 1
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.invert_yaxis()
    ax.set_box_aspect((1, 1, 1))


def run_pipeline(cond: str, bid: int, gt: dict, out_dir: Path):
    """Run Stage 3 step-by-step for one condition+building; save intermediates."""
    R = ROOT / "results/phase2_ablation_citygml"
    ckpt = R / cond / "ckpt/final.pt"
    prims = _load_model(ckpt)
    # assign primitives to this building via GT bbox
    b_gt = next(b for b in gt["buildings"] if b["building_id"] == bid)
    all_v = np.concatenate([f["vertices"] for f in b_gt["faces"]], axis=0)
    mn, mx = all_v.min(0) - 2, all_v.max(0) + 2
    mask_bbox = ((prims["centers"] >= mn) & (prims["centers"] <= mx)).all(axis=1)
    mask_opa = prims["opacities"] >= 0.05
    sel = np.where(mask_bbox & mask_opa)[0]
    if len(sel) < 5:
        print(f"  [{cond}] insufficient primitives: {len(sel)}")
        return None

    prim_dict = _build_primitives_dict(prims)
    centers = prim_dict["centers"][sel]
    normals = prim_dict["normals"][sel]
    areas = prim_dict["areas"][sel]
    sem = prim_dict["semantic_probs"][sel]
    labels = sem.argmax(axis=1)

    record = {"condition": cond, "bid": bid}

    # ----- Step 1: classification + filter -----
    n_per_class = {int(c): int((labels == c).sum()) for c in range(4)}
    record["step1"] = {
        "n_primitives_total": int(len(sel)),
        "n_by_class": n_per_class,
        "n_roof": n_per_class.get(1, 0),
        "n_wall": n_per_class.get(2, 0),
        "n_terrain": n_per_class.get(3, 0),
    }
    # filter: keep Roof + Wall for building; drop BG + Terrain (Terrain handled separately)
    keep_mask = (labels == 1) | (labels == 2)
    if keep_mask.sum() < 5:
        record["error"] = "Step 1: < 5 after filter"
        return record
    # Continue with full (roof+wall+terrain) for clustering
    step1_centers = centers
    step1_normals = normals
    step1_areas = areas
    step1_labels = labels

    # ----- Step 2: clustering -----
    groups = cluster_primitives(step1_centers, step1_normals, step1_areas, step1_labels,
                                 cos_thresh=0.85)
    group_sizes = [len(g["prim_ids"]) for g in groups]
    group_classes = [int(g["class"]) for g in groups]
    sigma_normals = []
    sigma_coplanars = []
    for g in groups:
        pids = g["prim_ids"]
        if len(pids) < 2: continue
        gn = step1_normals[pids]
        gc = step1_centers[pids]
        rep_n = np.asarray(g["plane_normal"])
        rep_d = float(g["plane_d"])
        # flip to rep direction
        dot = gn @ rep_n
        gn = gn * np.sign(dot + 1e-12)[:, None]
        ang = np.degrees(np.arccos(np.clip(gn @ rep_n, -1, 1)))
        offs = np.abs(gc @ rep_n - rep_d)
        sigma_normals.append(float(ang.std()))
        sigma_coplanars.append(float(np.sqrt((offs ** 2).mean())))
    record["step2"] = {
        "n_groups": len(groups),
        "group_sizes": group_sizes,
        "group_classes": group_classes,
        "sigma_normal_mean": float(np.mean(sigma_normals)) if sigma_normals else None,
        "sigma_coplanar_mean": float(np.mean(sigma_coplanars)) if sigma_coplanars else None,
    }

    # ----- Step 3 prep: orient + ground + bbox -----
    for g in groups:
        g["prim_ids"] = [int(sel[i]) for i in g["prim_ids"]]
    bc = step1_centers.mean(axis=0)
    orient_normals_outward(groups, bc)
    wall_mask_full = step1_labels == 2
    add_ground_surface(groups, step1_centers[wall_mask_full], bc)
    n_bbox = add_bbox_planes(groups, step1_centers)
    n_roof_g = sum(1 for g in groups if g["class"] == 1)
    n_wall_g = sum(1 for g in groups if g["class"] == 2)
    n_gnd = sum(1 for g in groups if g.get("is_ground"))
    record["step3_prep"] = {
        "n_roof_groups": n_roof_g,
        "n_wall_groups": n_wall_g,
        "n_ground": n_gnd,
        "n_bbox": n_bbox,
    }

    # ----- Step 3: convex polytope construction -----
    polygons = build_convex_polytope(groups, step1_centers, hs_tol=0.05)
    if polygons is None:
        record["step4_convex"] = {"polytope": None}
    else:
        record["step4_convex"] = {
            "n_faces": len(polygons),
            "n_faces_gte_3v": sum(1 for pts in polygons.values() if len(pts) >= 3),
            "face_vertex_counts": [len(pts) for pts in polygons.values()],
        }

    # ----- Step 4/5: build CityJSON and val3dity -----
    bdir = out_dir / f"{cond}_bid{bid}"
    bdir.mkdir(parents=True, exist_ok=True)
    if polygons and len(polygons) >= 4:
        result = build_cityjson(bid, groups, polygons, str(bdir))
        if result:
            record["step6_cityjson"] = {
                "n_surfaces": result.get("n_surfaces"),
                "n_vertices": result.get("n_vertices"),
                "signed_volume": float(result.get("signed_volume", 0)),
            }
            # val3dity
            cj_path = Path(result["cityjson_path"])
            rp_path = bdir / "val3dity.json"
            try:
                proc = subprocess.run(
                    ["val3dity", "--report", str(rp_path), str(cj_path)],
                    capture_output=True, text=True, timeout=60,
                )
                if rp_path.exists():
                    v3d = json.loads(rp_path.read_text())
                    feats = v3d.get("features", [])
                    if feats:
                        errs = feats[0].get("errors", [])
                        record["step6_val3dity"] = {
                            "valid": bool(feats[0].get("validity", False)),
                            "error_codes": [e.get("code") for e in errs],
                            "error_details": [{"code": e.get("code"), "id": e.get("id")}
                                              for e in errs[:5]],
                        }
            except Exception as e:
                record["step6_val3dity"] = {"error": str(e)}

    # Save primitive data for viz
    np.savez(bdir / "primitives.npz",
             centers=step1_centers, normals=step1_normals,
             labels=step1_labels, areas=step1_areas)
    # Save group assignment as list of arrays
    with open(bdir / "groups.json", "w") as f:
        json.dump({
            "n_groups": len(groups),
            "groups": [{
                "prim_ids_local": [int(i) for i in range(len(step1_centers))
                                    if int(sel[i]) in g["prim_ids"]],
                "class": int(g["class"]),
                "plane_normal": [float(x) for x in g["plane_normal"]],
                "plane_d": float(g["plane_d"]),
                "is_ground": bool(g.get("is_ground", False)),
                "is_bbox": bool(g.get("is_bbox", False)),
            } for g in groups]
        }, f, indent=2)
    if polygons:
        poly_dump = {int(k): [[float(x) for x in p] for p in pts.tolist()]
                      for k, pts in polygons.items()}
        (bdir / "polytope.json").write_text(json.dumps(poly_dump))

    (bdir / "record.json").write_text(json.dumps(record, indent=2, default=str))
    return record


def visualize_both(records: dict, gt_building: dict, out_png: Path, out_dir: Path, bid: int):
    """5-panel figure per condition: step1 points, step2 clusters, step3 planes,
    step4 polytope, step6 cityjson (+ val3dity status). 4 rows × 5 cols."""
    n_rows = len(CONDS)
    fig = plt.figure(figsize=(22, 4.2 * n_rows))
    for ri, cond in enumerate(CONDS):
        rec = records[cond]
        bdir = out_dir / f"{cond}_bid{bid}"
        if not (bdir / "primitives.npz").exists():
            for i in range(5):
                ax = fig.add_subplot(n_rows, 5, ri * 5 + i + 1, projection="3d")
                ax.text2D(0.5, 0.5, "missing", ha="center", transform=ax.transAxes)
            continue
        data = np.load(bdir / "primitives.npz")
        centers = data["centers"]; normals = data["normals"]; labels = data["labels"]
        groups = json.loads((bdir / "groups.json").read_text())["groups"]

        # Panel 1: Step 1 — points colored by semantic
        ax = fig.add_subplot(n_rows, 5, ri * 5 + 1, projection="3d")
        for cls, color in SEM_COLOR.items():
            m = labels == cls
            if m.sum() > 0:
                ax.scatter(centers[m, 0], centers[m, 1], centers[m, 2],
                           c=color, s=3, alpha=0.6, edgecolors="none")
        _set_3d(ax, centers)
        s1 = rec.get("step1", {})
        ax.set_title(f"{cond}\nStep 1: {s1.get('n_primitives_total', '?')} prims\n"
                     f"R={s1.get('n_roof', 0)} W={s1.get('n_wall', 0)} T={s1.get('n_terrain', 0)}",
                     fontsize=8)

        # Panel 2: Step 2 — clusters colored
        ax = fig.add_subplot(n_rows, 5, ri * 5 + 2, projection="3d")
        non_bbox = [g for g in groups if not g.get("is_bbox", False)]
        cmap = plt.get_cmap("tab20")
        for gi, g in enumerate(non_bbox):
            pids = g["prim_ids_local"]
            if not pids: continue
            pts = centers[pids]
            ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2],
                       c=[cmap(gi % 20)], s=4, alpha=0.7, edgecolors="none")
        _set_3d(ax, centers)
        s2 = rec.get("step2", {})
        ax.set_title(f"Step 2: {s2.get('n_groups', '?')} groups\n"
                     f"σn={s2.get('sigma_normal_mean', 0):.1f}°  σcp={s2.get('sigma_coplanar_mean', 0):.2f}m",
                     fontsize=8)

        # Panel 3: Step 3 prep — cluster centers + representative normals (quiver)
        ax = fig.add_subplot(n_rows, 5, ri * 5 + 3, projection="3d")
        for g in groups:
            if g.get("is_bbox"): continue
            pids = g["prim_ids_local"]
            if len(pids) < 2: continue
            c = centers[pids].mean(axis=0)
            n = np.array(g["plane_normal"]) * 2.0
            cls = g["class"]; color = SEM_COLOR.get(cls, "#808080")
            ax.scatter([c[0]], [c[1]], [c[2]], c=[color], s=25, edgecolor="k", linewidth=0.5)
            ax.quiver(c[0], c[1], c[2], n[0], n[1], n[2],
                      color=color, arrow_length_ratio=0.3, linewidth=1.2)
        _set_3d(ax, centers)
        s3 = rec.get("step3_prep", {})
        ax.set_title(f"Step 3: roof={s3.get('n_roof_groups', 0)} wall={s3.get('n_wall_groups', 0)}\n"
                     f"ground={s3.get('n_ground', 0)} bbox={s3.get('n_bbox', 0)}", fontsize=8)

        # Panel 4: Step 4 — convex polytope (polygons)
        ax = fig.add_subplot(n_rows, 5, ri * 5 + 4, projection="3d")
        poly_path = bdir / "polytope.json"
        if poly_path.exists():
            poly_data = json.loads(poly_path.read_text())
            all_v = []
            for gi, pts_list in poly_data.items():
                pts = np.array(pts_list)
                if len(pts) < 3: continue
                all_v.append(pts)
                gi_int = int(gi)
                g_info = groups[gi_int] if gi_int < len(groups) else {}
                if g_info.get("is_ground"):
                    color = "#718096"
                else:
                    cls = g_info.get("class", 0)
                    color = SEM_COLOR.get(cls, "#808080")
                ax.add_collection3d(Poly3DCollection([pts], alpha=0.6,
                                                     facecolor=color, edgecolor="k", linewidth=0.4))
            if all_v:
                _set_3d(ax, np.vstack(all_v))
            s4 = rec.get("step4_convex", {})
            ax.set_title(f"Step 4: convex polytope\n{s4.get('n_faces', 0)} faces", fontsize=8)
        else:
            ax.text2D(0.5, 0.5, "no polytope", ha="center", transform=ax.transAxes)

        # Panel 5: Step 6 — final CityJSON status
        ax = fig.add_subplot(n_rows, 5, ri * 5 + 5, projection="3d")
        v3d = rec.get("step6_val3dity", {})
        valid = v3d.get("valid", False)
        # Re-render the polytope with red/blue based on validity
        if poly_path.exists():
            poly_data = json.loads(poly_path.read_text())
            all_v = []
            for gi, pts_list in poly_data.items():
                pts = np.array(pts_list)
                if len(pts) < 3: continue
                all_v.append(pts)
                color = "#2C5582" if valid else "#C53030"
                ax.add_collection3d(Poly3DCollection([pts], alpha=0.6,
                                                     facecolor=color, edgecolor="k", linewidth=0.4))
            if all_v:
                _set_3d(ax, np.vstack(all_v))
        err_codes = v3d.get("error_codes", [])
        n_errs = len(err_codes)
        status = "✓ VALID" if valid else f"✗ INVALID ({n_errs} errors)"
        ax.set_title(f"Step 6: {status}\n"
                     f"errors: {sorted(set(err_codes)) if err_codes else 'none'}",
                     fontsize=8)

    btype = gt_building.get("type", "?")
    plt.suptitle(f"D1: Stage 3 step-by-step — building_{bid:03d} ({btype})\n"
                 f"4 conditions × 5 pipeline steps. Track where each condition diverges.",
                 fontsize=11, weight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {out_png}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--bids", nargs="+", type=int, default=BIDS_DEFAULT)
    args = ap.parse_args()

    out_dir = ROOT / "results/phase2_ablation_citygml/_diag/d1"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = parse_scene_obj(str(ROOT / "results/phase2_synthesis/scene.obj"))

    for bid in args.bids:
        b_gt = next((b for b in scene["buildings"] if b["building_id"] == bid), None)
        if b_gt is None:
            print(f"bid={bid} not in scene"); continue
        print(f"\n===== bid={bid} ({b_gt.get('type')}) =====")
        records = {}
        for cond in CONDS:
            print(f"[{cond}]")
            rec = run_pipeline(cond, bid, scene, out_dir)
            if rec:
                records[cond] = rec
                s1 = rec.get("step1", {})
                s2 = rec.get("step2", {})
                s4 = rec.get("step4_convex", {})
                v3d = rec.get("step6_val3dity", {})
                print(f"  S1: {s1.get('n_primitives_total','?')} prims R={s1.get('n_roof',0)} "
                      f"W={s1.get('n_wall',0)} | S2: {s2.get('n_groups',0)}g σn={s2.get('sigma_normal_mean',0):.1f}° | "
                      f"S4: {s4.get('n_faces',0)}f | S6: {'VALID' if v3d.get('valid') else 'INVALID'} "
                      f"{v3d.get('error_codes', [])}")
        diff = {k: {c: records.get(c, {}).get(k, {}) for c in CONDS}
                for k in ["step1", "step2", "step3_prep", "step4_convex", "step6_val3dity"]}
        (out_dir / f"comparison_bid{bid}.json").write_text(json.dumps(diff, indent=2, default=str))
        visualize_both(records, b_gt,
                        ROOT / f"results/phase2_ablation_citygml/figures/fig_d1_bid{bid:03d}.png",
                        out_dir, bid)


if __name__ == "__main__":
    main()
