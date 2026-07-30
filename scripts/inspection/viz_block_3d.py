"""Visualize the selected Phase 2 scene block with ACTUAL footprint polygons.

Three panels:
  (1) Amsterdam Jordaan context — all 2888 buildings as footprint polygons in
      EPSG:7415 world coords, with the selected 200×200m window highlighted.
  (2) Selected block zoom — each building's real ground footprint polygon,
      colored by roof type. No bboxes (they overlap falsely).
  (3) Single 3D isometric of the block — roofs in red, walls in blue, ground
      quad in gray. Buildings rendered from actual face polygons.

Output: results/phase2_synthesis/block_3d.png
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results/phase2_synthesis"
sys.path.insert(0, str(ROOT / "scripts" / "synthetic_a"))

TYPE_COLOR = {
    "flat":      "#4C9AFF",
    "shed":      "#9B59B6",
    "gable":     "#20A050",
    "hip":       "#FFB040",
    "tri-slope": "#FF6B6B",
    "complex":   "#888888",
}
MAT_COLOR = {"Roof": "#C53030", "Wall": "#2C5282",
             "Ground": "#718096", "Terrain": "#A0AEC0"}


def extract_world_ground_polygons():
    """For every building across Jordaan 4 tiles, extract its ground-level
    footprint polygon in EPSG:7415 world coords.

    Strategy: read raw CityJSON. For each Building's LOD2.2 geometry in its
    BuildingPart child, find the face whose centroid is LOWEST (= ground face),
    take its outer ring → world polygon.
    """
    import_tiles = sorted(glob.glob(
        str(ROOT / "results/synthetic_a/3dbag_raw/amsterdam_jordaan/*.city.json")))
    result = []
    for tp in import_tiles:
        cj = json.load(open(tp))
        scale = np.array(cj["transform"]["scale"])
        translate = np.array(cj["transform"]["translate"])
        world_verts = np.array(cj["vertices"], dtype=np.float64) * scale + translate

        for obj_name, obj in cj["CityObjects"].items():
            if obj.get("type") != "Building":
                continue
            # Find child BuildingPart with LOD2.2 solid
            chosen = None
            for cand in [obj_name] + [f"{obj_name}-{i}" for i in range(5)]:
                cand_obj = cj["CityObjects"].get(cand)
                if cand_obj is None:
                    continue
                for g in cand_obj.get("geometry", []):
                    if str(g.get("lod", "")) == "2.2" and g.get("type") == "Solid":
                        chosen = g; break
                if chosen is not None:
                    break
            if chosen is None:
                continue
            shell = chosen["boundaries"][0]  # outer shell
            # Find face with lowest centroid Z (world)
            ground_face = None
            ground_z_min = float("inf")
            for surf in shell:
                ring = surf[0]
                if len(ring) < 3:
                    continue
                pts = world_verts[ring]
                cz = float(pts[:, 2].mean())
                if cz < ground_z_min:
                    ground_z_min = cz
                    ground_face = pts
            if ground_face is None:
                continue
            result.append({
                "name": obj_name,
                "world_footprint_xy": ground_face[:, :2],  # (N, 2) EPSG:7415
                "ground_z": ground_z_min,
            })
    return result


def load_selected_block_meta():
    sel = json.loads((OUT_DIR / "selected_block.json").read_text())
    # Build name → type dict
    name_to_type = {b["name"]: b["type"] for b in sel["buildings"]}
    return sel, name_to_type


def parse_scene_obj_faces():
    """Parse scene.obj into per-building faces with material + per-object type.

    Returns list of {name, type, faces: [(verts Nx3, mat)], vertices: (V,3)}.
    """
    layout = json.loads((OUT_DIR / "scene_layout.json").read_text())
    name_to_type = {}
    for b in layout["buildings"]:
        # "name" from scene_layout has suffix "_<type>"; store both keys
        name_to_type[b["name"]] = "unknown"
    # We also have selected_block.json with per-name type
    sel, sb_type = load_selected_block_meta()

    objects = []
    cur = None
    cur_mat = None
    verts_all = []
    for ln in (OUT_DIR / "scene.obj").read_text().splitlines():
        if not ln or ln.startswith("#"): continue
        head, *rest = ln.split()
        if head in ("o", "g"):
            raw = rest[0] if rest else f"obj_{len(objects)}"
            if cur is not None:
                objects.append(cur)
            # Name format: "<bag_name>_<type>" OR "ground_plane"
            parts = raw.rsplit("_", 1)
            if len(parts) == 2 and parts[1] in TYPE_COLOR:
                bname = parts[0]; btype = parts[1]
            else:
                bname = raw; btype = sb_type.get(raw, "unknown")
            cur = {"name": bname, "type": btype,
                   "v_offset": len(verts_all), "vertices": [], "faces": []}
        elif head == "v":
            v = [float(x) for x in rest[:3]]
            verts_all.append(v)
            if cur is not None:
                cur["vertices"].append(v)
        elif head == "usemtl":
            cur_mat = rest[0] if rest else "?"
        elif head == "f":
            if cur is None: continue
            idxs_local = [int(t.split("/")[0]) - 1 - cur["v_offset"] for t in rest]
            cur["faces"].append((idxs_local, cur_mat))
    if cur is not None:
        objects.append(cur)
    for o in objects:
        o["vertices"] = np.array(o["vertices"], dtype=np.float64)
    return objects


def main():
    layout = json.loads((OUT_DIR / "scene_layout.json").read_text())
    sel, name_to_type = load_selected_block_meta()
    cx_world, cy_world = sel["window"]["center"]
    half = sel["window"]["size"] / 2

    # 2 rows: top row = 2D context + zoom (small), bottom row = big 3D (spans full width)
    fig = plt.figure(figsize=(18, 16))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.8])

    # ---------- Panel 1: Amsterdam Jordaan context ----------
    ax1 = fig.add_subplot(gs[0, 0])
    # 2D panels occupy row 0, 3D panel occupies row 1 (full width)
    print("[viz] extracting ground footprints for all Jordaan buildings …")
    all_polys = extract_world_ground_polygons()
    print(f"[viz] loaded {len(all_polys)} ground polygons")
    pc_all = PolyCollection(
        [p["world_footprint_xy"] for p in all_polys],
        facecolor="#cdd3db", edgecolor="#555", linewidth=0.15, alpha=0.85)
    ax1.add_collection(pc_all)

    # Highlighted window
    rect = mpatches.Rectangle(
        (cx_world - half, cy_world - half), 2 * half, 2 * half,
        linewidth=2.5, edgecolor="#E53E3E", facecolor="#E53E3E", alpha=0.15,
        label=f"Selected 200×200m window")
    ax1.add_patch(rect)

    # Scale + labels
    xs = np.concatenate([p["world_footprint_xy"][:, 0] for p in all_polys])
    ys = np.concatenate([p["world_footprint_xy"][:, 1] for p in all_polys])
    pad = 30
    ax1.set_xlim(xs.min() - pad, xs.max() + pad)
    ax1.set_ylim(ys.min() - pad, ys.max() + pad)
    ax1.set_aspect("equal")
    ax1.set_xlabel("EPSG:7415 X (m east)")
    ax1.set_ylabel("EPSG:7415 Y (m north)")
    ax1.set_title(f"(1) Amsterdam Jordaan context\n"
                  f"{len(all_polys)} buildings total, selected window in red")
    ax1.legend(loc="lower left", fontsize=9)

    # ---------- Panel 2: Zoomed block with REAL footprints colored by type ----------
    ax2 = fig.add_subplot(gs[0, 1])
    # placed in row 0, col 1
    # Buildings inside window
    inside_polys = []
    inside_types = []
    for p in all_polys:
        c = p["world_footprint_xy"].mean(axis=0)
        if cx_world - half <= c[0] <= cx_world + half \
           and cy_world - half <= c[1] <= cy_world + half:
            inside_polys.append(p["world_footprint_xy"])
            inside_types.append(name_to_type.get(p["name"], "unknown"))
    print(f"[viz] window contains {len(inside_polys)} ground polygons")
    type_colors = [TYPE_COLOR.get(t, "#ccc") for t in inside_types]
    pc2 = PolyCollection(inside_polys, facecolor=type_colors,
                         edgecolor="#000", linewidth=0.5, alpha=0.95)
    ax2.add_collection(pc2)
    # Mark window
    rect2 = mpatches.Rectangle(
        (cx_world - half, cy_world - half), 2 * half, 2 * half,
        fill=False, edgecolor="#E53E3E", linewidth=2.5)
    ax2.add_patch(rect2)
    ax2.set_xlim(cx_world - half - 15, cx_world + half + 15)
    ax2.set_ylim(cy_world - half - 15, cy_world + half + 15)
    ax2.set_aspect("equal")
    ax2.set_xlabel("EPSG:7415 X (m east)")
    ax2.set_ylabel("EPSG:7415 Y (m north)")
    type_summary = ", ".join(f"{t}: {sel['type_counts'].get(t, 0)}"
                              for t in ["flat", "gable", "hip", "tri-slope", "complex", "shed"]
                              if sel['type_counts'].get(t, 0) > 0)
    ax2.set_title(f"(2) Selected block — REAL ground footprints\n[{type_summary}]")
    lp = [mpatches.Patch(color=c, label=f"{t} ({sel['type_counts'].get(t, 0)})")
          for t, c in TYPE_COLOR.items() if sel['type_counts'].get(t, 0) > 0]
    ax2.legend(handles=lp, loc="upper left", fontsize=8)

    # ---------- Panel 3: 3D isometric of the block, roofs colored by TYPE ----------
    # matplotlib 3D convention: X right, Y depth-into-screen, Z up.
    # Our OBJ: X east, Z north, Y with gravity=+Y (so roofs at Y<0).
    # Mapping: mpl_x = obj_x, mpl_y = obj_z, mpl_z = -obj_y (so up is +mpl_z).
    ax3 = fig.add_subplot(gs[1, :], projection="3d")  # full-width bottom row
    objects = parse_scene_obj_faces()
    n_bldgs = sum(1 for o in objects if o["name"] != "ground_plane")

    polys_roof = []; colors_roof = []
    polys_wall = []
    polys_ground_face = []   # per-building ground faces (inside meshes)
    for o in objects:
        if o["name"] == "ground_plane":
            continue
        roof_color = TYPE_COLOR.get(o["type"], "#aaa")
        for idxs, mat in o["faces"]:
            if len(idxs) < 3:
                continue
            p = o["vertices"][idxs]
            # OBJ -> matplotlib: (x, y, z) -> (x, z, -y)
            p_mpl = np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)
            if mat == "Roof":
                polys_roof.append(p_mpl); colors_roof.append(roof_color)
            elif mat == "Wall":
                polys_wall.append(p_mpl)
            else:
                polys_ground_face.append(p_mpl)

    # Order: draw walls first (backdrop), then roofs on top
    if polys_wall:
        ax3.add_collection3d(Poly3DCollection(
            [w.tolist() for w in polys_wall],
            facecolor="#d8dde4", edgecolor="#4a5568",
            linewidth=0.2, alpha=0.85))
    if polys_ground_face:
        ax3.add_collection3d(Poly3DCollection(
            [g.tolist() for g in polys_ground_face],
            facecolor="#a0aec0", edgecolor="#4a5568",
            linewidth=0.2, alpha=0.6))
    if polys_roof:
        ax3.add_collection3d(Poly3DCollection(
            [r.tolist() for r in polys_roof],
            facecolor=colors_roof, edgecolor="#1a202c",
            linewidth=0.35, alpha=0.98))

    # Ground plane (large terrain quad in mpl frame)
    gq = np.array([[-half, -half, 0], [half, -half, 0],
                   [half, half, 0],   [-half, half, 0]])
    ax3.add_collection3d(Poly3DCollection(
        [gq.tolist()], facecolor="#f0f2f5", edgecolor="#718096",
        linewidth=0.4, alpha=0.5))

    # Axes & view: keep 1:1:1 aspect so heights look realistic
    all_pts = np.vstack([np.vstack(polys_roof + polys_wall + polys_ground_face), gq])
    cx = (all_pts[:, 0].min() + all_pts[:, 0].max()) / 2
    cy = (all_pts[:, 1].min() + all_pts[:, 1].max()) / 2
    cz = (all_pts[:, 2].min() + all_pts[:, 2].max()) / 2
    span_xy = max(all_pts[:, 0].ptp(), all_pts[:, 1].ptp()) / 2
    ax3.set_xlim(cx - span_xy, cx + span_xy)
    ax3.set_ylim(cy - span_xy, cy + span_xy)
    ax3.set_zlim(0, all_pts[:, 2].max() * 1.1)
    ax3.set_box_aspect((1, 1, all_pts[:, 2].max() * 1.1 / (2 * span_xy)))
    ax3.view_init(elev=55, azim=-60)  # high angle -> roofs visible
    ax3.set_xlabel("X east (m)"); ax3.set_ylabel("Y north (m)"); ax3.set_zlabel("height (m)")
    ax3.grid(False)
    ax3.set_title(f"(3) 3D bird's-eye — roofs colored by TYPE, walls gray\n"
                  f"{n_bldgs} buildings, max height {all_pts[:, 2].max():.0f} m")
    # Legend: roof types
    lp3 = [mpatches.Patch(color=c, label=f"{t} roof ({sel['type_counts'].get(t, 0)})")
           for t, c in TYPE_COLOR.items() if sel['type_counts'].get(t, 0) > 0]
    lp3.append(mpatches.Patch(color="#d8dde4", label="Walls"))
    ax3.legend(handles=lp3, loc="upper left", fontsize=8)

    plt.suptitle(
        "Phase 2 selected block — Amsterdam Jordaan 200×200m natural region",
        fontsize=14, y=1.02)
    plt.tight_layout()
    out_path = OUT_DIR / "block_3d.png"
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"[viz] saved: {out_path}")


if __name__ == "__main__":
    main()
