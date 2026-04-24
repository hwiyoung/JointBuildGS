"""Visualize Stage 3 pipeline intermediate outputs per step.

For each selected building, produce 3D visualizations at each step:
  Step 0  — GT scene.obj building (topology preserved, semantic colored)
  Step 2  — Primitive cluster input (points colored by plane_id)
  Step 3  — PolyFit reconstructed mesh (from OFF)
  Step 6+ — CityJSON (with val3dity invalid faces highlighted if any)

Outputs: PNG diagnostic figure with columns = steps, rows = buildings.

Usage (inside container):
  python scripts/phase2_synthesis/viz_stage3_steps.py \
    --test-dir results/phase2_ablation_citygml/_gt_polyfit_test \
    --buildings 1 50 126 \
    --out results/phase2_ablation_citygml/figures/fig_polyfit_steps.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402


SEM_COLOR = {
    1: "#C53030",   # Roof
    2: "#2C5582",   # Wall
    3: "#A0AEC0",   # Terrain
    0: "#808080",   # BG
}
PLANE_CMAP = plt.get_cmap("tab20")


def load_building_from_obj(scene, bid):
    for b in scene["buildings"]:
        if b["building_id"] == bid:
            return b
    return None


def load_polyfit_input(path: Path):
    """Return (points Nx3, normals Nx3, plane_ids N)."""
    lines = path.read_text().splitlines()
    n_pts, n_planes = map(int, lines[0].split())
    pts = np.zeros((n_pts, 3))
    nrm = np.zeros((n_pts, 3))
    pid = np.zeros(n_pts, dtype=int)
    for i in range(n_pts):
        t = lines[1 + i].split()
        pts[i] = [float(t[0]), float(t[1]), float(t[2])]
        nrm[i] = [float(t[3]), float(t[4]), float(t[5])]
        pid[i] = int(t[6])
    return pts, nrm, pid, n_planes


def load_off(path: Path):
    lines = path.read_text().splitlines()
    i = 1
    while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
        i += 1
    n_v, n_f, _ = map(int, lines[i].split())
    i += 1
    while i < len(lines) and not lines[i].strip(): i += 1
    verts = []
    read = 0
    while read < n_v and i < len(lines):
        if not lines[i].strip(): i += 1; continue
        t = lines[i].split()
        verts.append([float(t[0]), float(t[1]), float(t[2])])
        i += 1; read += 1
    faces = []
    read = 0
    while read < n_f and i < len(lines):
        if not lines[i].strip(): i += 1; continue
        t = lines[i].split()
        k = int(t[0])
        faces.append([int(t[1 + j]) for j in range(k)])
        i += 1; read += 1
    return np.array(verts), faces


def load_cityjson(path: Path):
    d = json.loads(path.read_text())
    scale = d["transform"]["scale"][0]
    trans = d["transform"]["translate"]
    verts = np.array([[v[j] * scale + trans[j] for j in range(3)] for v in d["vertices"]])
    b = list(d["CityObjects"].values())[0]
    shell = b["geometry"][0]["boundaries"][0]
    faces = [bnd[0] for bnd in shell]
    return verts, faces


def find_invalid_faces(cityjson_path: Path, val3dity_path: Path):
    """Return set of face indices (0-based) flagged by val3dity."""
    if not val3dity_path.exists(): return set()
    try:
        v = json.loads(val3dity_path.read_text())
        feats = v.get("features", [])
        if not feats: return set()
        bad = set()
        for e in feats[0].get("errors", []):
            eid = e.get("id", "")
            # eid like: coid=building_001|geom=0|shell=0|face=5
            for token in eid.split("|"):
                if token.startswith("face="):
                    bad.add(int(token[5:]))
        return bad
    except Exception:
        return set()


def _set_equal_3d(ax, pts):
    mn = pts.min(0); mx = pts.max(0)
    c = (mn + mx) / 2
    r = (mx - mn).max() / 2 * 1.1
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    # Y-down orientation (scene.obj)
    ax.invert_yaxis()
    ax.set_box_aspect((1, 1, 1))


def plot_gt_building(ax, building):
    verts_all = []
    for f in building["faces"]:
        v = np.array(f["vertices"])
        col = SEM_COLOR.get(f["semantic_class"], "#808080")
        poly = Poly3DCollection([v], alpha=0.7, facecolor=col, edgecolor="black", linewidth=0.3)
        ax.add_collection3d(poly)
        verts_all.append(v)
    if verts_all:
        verts_all = np.vstack(verts_all)
        _set_equal_3d(ax, verts_all)
    ax.set_title(f"Step 0: GT\n({building['type']}, {len(building['faces'])}f)", fontsize=9)


def plot_polyfit_input(ax, pts, pid, n_planes):
    colors = [PLANE_CMAP(p % 20) for p in pid]
    ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], c=colors, s=8, alpha=0.7, edgecolors="none")
    _set_equal_3d(ax, pts)
    ax.set_title(f"Step 2: Clustered input\n({n_planes} planes, {len(pts)} pts)", fontsize=9)


def plot_off_mesh(ax, verts, faces, title):
    if len(faces) == 0:
        ax.text2D(0.5, 0.5, "(no mesh)", ha="center", va="center", transform=ax.transAxes)
        return
    face_colors = [PLANE_CMAP(i % 20) for i in range(len(faces))]
    polys = [verts[f] for f in faces]
    pc = Poly3DCollection(polys, alpha=0.6, facecolors=face_colors,
                          edgecolor="black", linewidth=0.4)
    ax.add_collection3d(pc)
    _set_equal_3d(ax, verts)
    ax.set_title(title, fontsize=9)


def plot_cityjson_with_errors(ax, verts, faces, bad_faces, val3dity_valid):
    if len(faces) == 0:
        ax.text2D(0.5, 0.5, "(no mesh)", ha="center", va="center", transform=ax.transAxes)
        return
    face_colors = []
    for fi in range(len(faces)):
        if fi in bad_faces:
            face_colors.append("#FF3030")  # red = invalid
        else:
            face_colors.append("#68D4FF")  # blue = valid
    polys = [verts[f] for f in faces]
    pc = Poly3DCollection(polys, alpha=0.6, facecolors=face_colors,
                          edgecolor="black", linewidth=0.4)
    ax.add_collection3d(pc)
    _set_equal_3d(ax, verts)
    status = "VALID" if val3dity_valid else f"INVALID ({len(bad_faces)} bad face)"
    ax.set_title(f"Step 6: CityJSON\n{status}", fontsize=9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-dir", default=str(ROOT / "results/phase2_ablation_citygml/_gt_polyfit_test"))
    ap.add_argument("--scene", default=str(ROOT / "results/phase2_synthesis/scene.obj"))
    ap.add_argument("--buildings", nargs="+", type=int, default=[0, 1, 5])
    ap.add_argument("--out", default=str(ROOT / "results/phase2_ablation_citygml/figures/fig_polyfit_steps.png"))
    args = ap.parse_args()

    test_dir = Path(args.test_dir)
    scene = parse_scene_obj(args.scene)
    summary = json.loads((test_dir / "summary.json").read_text())
    per_b = {b["bid"]: b for b in summary["per_building"]}

    n_rows = len(args.buildings)
    n_cols = 4
    fig = plt.figure(figsize=(4.2 * n_cols, 4 * n_rows))

    for row_i, bid in enumerate(args.buildings):
        bdir = test_dir / f"building_{bid:03d}"
        b_gt = load_building_from_obj(scene, bid)
        if b_gt is None:
            print(f"bid={bid} not found in scene")
            continue

        # Step 0 — GT
        ax0 = fig.add_subplot(n_rows, n_cols, row_i * n_cols + 1, projection="3d")
        plot_gt_building(ax0, b_gt)
        ax0.set_ylabel(f"bid={bid}\n{b_gt['type']}", fontsize=9, rotation=0, labelpad=30, va="center")

        # Step 2 — PolyFit input (clustered)
        ax2 = fig.add_subplot(n_rows, n_cols, row_i * n_cols + 2, projection="3d")
        in_path = bdir / "polyfit_input.txt"
        if in_path.exists():
            pts, nrm, pid, n_planes = load_polyfit_input(in_path)
            plot_polyfit_input(ax2, pts, pid, n_planes)
        else:
            ax2.text2D(0.5, 0.5, "(no input)", ha="center", va="center", transform=ax2.transAxes)

        # Step 3 — PolyFit output (OFF)
        ax3 = fig.add_subplot(n_rows, n_cols, row_i * n_cols + 3, projection="3d")
        off_path = bdir / "polyfit_output.off"
        if off_path.exists():
            v, f = load_off(off_path)
            plot_off_mesh(ax3, v, f, f"Step 3: PolyFit\n({len(f)} faces, {len(v)} verts)")
        else:
            ax3.text2D(0.5, 0.5, "(PolyFit fail)", ha="center", va="center", transform=ax3.transAxes)
            ax3.set_title("Step 3: PolyFit FAILED", fontsize=9)

        # Step 6 — CityJSON
        ax6 = fig.add_subplot(n_rows, n_cols, row_i * n_cols + 4, projection="3d")
        cj_path = bdir / "building.city.json"
        v3_path = bdir / "val3dity.json"
        if cj_path.exists():
            v, f = load_cityjson(cj_path)
            bad = find_invalid_faces(cj_path, v3_path)
            b_info = per_b.get(bid, {})
            valid = b_info.get("val3dity_valid", False)
            plot_cityjson_with_errors(ax6, v, f, bad, valid)
        else:
            ax6.text2D(0.5, 0.5, "(no CityJSON)", ha="center", va="center", transform=ax6.transAxes)

    plt.suptitle("Stage 3 Pipeline Steps — GT input → CityJSON\n"
                 "Red = val3dity invalid face, Blue = valid",
                 fontsize=11, y=0.995)
    plt.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print(f"[saved] {out}")


if __name__ == "__main__":
    main()
