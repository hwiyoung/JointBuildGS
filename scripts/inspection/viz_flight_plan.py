"""Visualize the Pix4D-standard UAV mission flight plan over the scene.

Shows:
  - Building ground footprints (scene.obj)
  - All 112 nadir waypoint positions (one dot per waypoint)
  - Each waypoint's ground footprint rectangle at 80m altitude (120×90m FOV) —
    shows how the imagery tiles cover the scene with 80%/70% overlap
  - One highlighted waypoint with its 4 oblique look directions

Output: results/phase2_synthesis/figures/flight_plan.png
"""
from __future__ import annotations

import json
import math
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
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Match render_scene.py constants
ALTITUDE = 80.0
FOV_DEG_H = 74.0
RES_W, RES_H = 2048, 1536
FORWARD_OVERLAP = 0.80
SIDE_OVERLAP = 0.70
OBLIQUE_TILT_DEG = 45.0
OBLIQUE_AZIMUTHS = [0, 90, 180, 270]  # N, E, S, W
TYPE_COLOR = {
    "flat": "#4C9AFF", "shed": "#9B59B6", "gable": "#20A050",
    "hip": "#FFB040", "tri-slope": "#FF6B6B", "complex": "#888888",
}


def parse_obj_ground_polygons():
    """Return list of (polygon_XZ, type) for each building in scene.obj."""
    layout = json.loads((OUT_DIR / "scene_layout.json").read_text())
    name_to_type = {}
    # selected_block has the type info
    sel = json.loads((OUT_DIR / "selected_block.json").read_text())
    for b in sel["buildings"]:
        name_to_type[b["name"]] = b["type"]

    objects = []
    cur = None
    cur_mat = None
    verts_all = []
    for ln in (OUT_DIR / "scene.obj").read_text().splitlines():
        if not ln or ln.startswith("#"): continue
        head, *rest = ln.split()
        if head in ("o", "g"):
            raw = rest[0] if rest else ""
            if cur is not None:
                objects.append(cur)
            cur = {"raw": raw, "v_offset": len(verts_all), "faces": []}
        elif head == "v":
            v = [float(x) for x in rest[:3]]
            verts_all.append(v)
        elif head == "usemtl":
            cur_mat = rest[0] if rest else "?"
        elif head == "f":
            if cur is None: continue
            idxs = [int(t.split("/")[0]) - 1 for t in rest]
            cur["faces"].append((idxs, cur_mat))
    if cur is not None:
        objects.append(cur)

    verts_all = np.array(verts_all)
    out = []
    for o in objects:
        if o["raw"] == "ground_plane":
            continue
        # Find Ground face (material "Ground") = building floor
        ground_poly = None
        for idxs, mat in o["faces"]:
            if mat == "Ground":
                ground_poly = verts_all[idxs]
                break
        if ground_poly is None and o["faces"]:
            # fallback: first face with lowest max Y (Y<0 = above ground, Y=0 ground)
            ground_poly = verts_all[o["faces"][0][0]]
        if ground_poly is None:
            continue
        # XZ plane (Y is vertical in OBJ)
        name_key = o["raw"].rsplit("_", 1)[0]
        btype = name_to_type.get(name_key, "unknown")
        out.append((ground_poly[:, [0, 2]], btype))
    return out


def compute_waypoint_grid():
    """Recompute waypoint grid positions to match render_scene.py."""
    layout = json.loads((OUT_DIR / "scene_layout.json").read_text())
    bmn = np.array(layout["scene_bbox_min"])
    bmx = np.array(layout["scene_bbox_max"])
    hfov = math.radians(FOV_DEG_H)
    vfov = 2 * math.atan(math.tan(hfov / 2) * RES_H / RES_W)
    fw = 2 * ALTITUDE * math.tan(hfov / 2)
    fh = 2 * ALTITUDE * math.tan(vfov / 2)
    side_s = (1 - SIDE_OVERLAP) * fw
    fwd_s = (1 - FORWARD_OVERLAP) * fh
    extent = bmx - bmn
    # Scene in OBJ frame: X horizontal, Z horizontal. Y is vertical.
    # Render uses Blender frame after OBJ-import axis swap. render_scene.py
    # generates grid via X (side_spacing) × Y (fwd_spacing) in Blender coords.
    # Blender X maps to OBJ X, Blender Y maps to OBJ Z (after axis swap).
    # So grid is in (OBJ.X, OBJ.Z) with side_s along OBJ.X, fwd_s along OBJ.Z.
    n_cols = max(2, int(math.ceil(extent[0] / side_s)) + 1)
    n_rows = max(2, int(math.ceil(extent[2] / fwd_s)) + 1)
    xs = np.linspace(bmn[0], bmx[0], n_cols)
    zs = np.linspace(bmn[2], bmx[2], n_rows)
    return xs, zs, fw, fh


def main():
    polys = parse_obj_ground_polygons()
    xs, zs, fw, fh = compute_waypoint_grid()
    layout = json.loads((OUT_DIR / "scene_layout.json").read_text())
    bmn = np.array(layout["scene_bbox_min"])
    bmx = np.array(layout["scene_bbox_max"])
    type_counts = json.loads((OUT_DIR / "selected_block.json").read_text())["type_counts"]
    print(f"[fp] {len(polys)} buildings; waypoint grid {len(xs)}×{len(zs)} = {len(xs)*len(zs)}")

    fig = plt.figure(figsize=(22, 10))
    ax1 = fig.add_subplot(1, 2, 1)
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")

    # -------- Panel 1: Flight plan with all waypoints and footprints --------
    pc = PolyCollection([p for p, _ in polys],
                         facecolor=[TYPE_COLOR.get(t, "#ccc") for _, t in polys],
                         edgecolor="#333", linewidth=0.3, alpha=0.85)
    ax1.add_collection(pc)

    # All waypoint footprints (nadir) — each covers fw × fh (120 × 90 m)
    footprints = []
    waypts = []
    for z in zs:
        for x in xs:
            # nadir footprint rectangle centered on waypoint
            fp = [(x - fw/2, z - fh/2), (x + fw/2, z - fh/2),
                  (x + fw/2, z + fh/2), (x - fw/2, z + fh/2)]
            footprints.append(fp)
            waypts.append((x, z))
    fp_coll = PolyCollection(footprints, facecolor="none",
                              edgecolor="#3182ce", linewidth=0.4, alpha=0.35)
    ax1.add_collection(fp_coll)

    # Waypoint positions
    wp = np.array(waypts)
    ax1.scatter(wp[:, 0], wp[:, 1], s=22, c="#2b6cb0", edgecolor="white",
                linewidths=0.8, zorder=5, label=f"Nadir waypoints ({len(waypts)})")

    # Scene window
    ax1.add_patch(mpatches.Rectangle(
        (bmn[0], bmn[2]), bmx[0] - bmn[0], bmx[2] - bmn[2],
        fill=False, edgecolor="#E53E3E", linewidth=2, label="Scene bounds (230 × 230 m)"))

    pad = 15
    ax1.set_xlim(bmn[0] - pad, bmx[0] + pad)
    ax1.set_ylim(bmn[2] - pad, bmx[2] + pad)
    ax1.set_aspect("equal")
    ax1.set_xlabel("X (m, east)")
    ax1.set_ylabel("Z (m, north)")
    ax1.set_title(f"(1) UAV flight plan — {len(waypts)} nadir waypoints\n"
                  f"Each image covers {fw:.0f}×{fh:.0f}m ground at {ALTITUDE:.0f}m alt "
                  f"(80%/70% overlap)")
    handles = [mpatches.Patch(color=c, label=f"{t} ({type_counts.get(t, 0)})")
               for t, c in TYPE_COLOR.items() if type_counts.get(t, 0) > 0]
    handles.append(mpatches.Patch(facecolor="none", edgecolor="#3182ce",
                                    label="Image footprint (120×90 m)"))
    handles.append(ax1.collections[-1])
    ax1.legend(handles=handles, loc="upper left", fontsize=8, ncol=2)

    # -------- Panel 2: 3D view of a central waypoint with 5 camera frustums --------
    # Axes: X east, Y north (matplotlib Y), Z up (height). Ground at Z=0.
    cx = xs[len(xs) // 2]
    cz = zs[len(zs) // 2]   # OBJ Z = "north" in mpl Y
    tilt = math.radians(OBLIQUE_TILT_DEG)
    oblique_r = ALTITUDE * math.tan(tilt)
    hfov = math.radians(FOV_DEG_H)
    vfov = 2 * math.atan(math.tan(hfov / 2) * RES_H / RES_W)

    # Buildings as 3D flat polygons at z=0 — show all within scene bounds
    # (clipped frustums now stay within scene, so show full scene footprint)
    for poly_xz, btype in polys:
        poly3d = np.column_stack([poly_xz[:, 0], poly_xz[:, 1],
                                   np.zeros(len(poly_xz))])
        ax2.add_collection3d(Poly3DCollection(
            [poly3d.tolist()], facecolor=TYPE_COLOR.get(btype, "#ccc"),
            edgecolor="#333", linewidth=0.3, alpha=0.75))

    def draw_frustum(camera_xyz, look_at_xyz, color, label=None, alpha=0.2,
                      clip_bounds=None):
        """Draw a camera frustum: 4 rays from camera to the 4 ground corners
        defined by FOV. Rays clipped at scene bounds if provided.

        clip_bounds: (x_min, x_max, y_min, y_max) — clip ground-plane corners
          so frustum doesn't extend infinitely beyond the scene area.
        """
        cam = np.array(camera_xyz, dtype=np.float64)
        la = np.array(look_at_xyz, dtype=np.float64)
        forward = la - cam
        d = np.linalg.norm(forward)
        forward /= d
        # Build local camera frame (OpenCV: x right, y down, z forward)
        # Here just need 'right' and 'up'.
        world_up = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(forward, world_up)) > 0.999:
            world_up = np.array([1.0, 0.0, 0.0])
        right = np.cross(forward, world_up); right /= np.linalg.norm(right)
        up = np.cross(right, forward); up /= np.linalg.norm(up)
        # Corners on ground plane (z=0): project camera corners onto ground
        # Extend rays from camera in direction = forward ± right*tan(hfov/2) ± up*tan(vfov/2)
        tan_h = math.tan(hfov / 2)
        tan_v = math.tan(vfov / 2)
        corners = []
        for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            ray = forward + sx * tan_h * right + sy * tan_v * up
            # Intersect with ground z=0: cam.z + t*ray.z = 0 -> t = -cam.z/ray.z
            if abs(ray[2]) < 1e-6: continue
            t_ground = -cam[2] / ray[2]
            if t_ground < 0: continue
            # Clip by scene bounds (horizontal)
            if clip_bounds is not None:
                x_min, x_max, y_min, y_max = clip_bounds
                t_clip = t_ground
                # X planes
                if abs(ray[0]) > 1e-6:
                    t_xmin = (x_min - cam[0]) / ray[0]
                    t_xmax = (x_max - cam[0]) / ray[0]
                    for tc in (t_xmin, t_xmax):
                        if 0 < tc < t_clip: t_clip = tc
                # Y planes
                if abs(ray[1]) > 1e-6:
                    t_ymin = (y_min - cam[1]) / ray[1]
                    t_ymax = (y_max - cam[1]) / ray[1]
                    for tc in (t_ymin, t_ymax):
                        if 0 < tc < t_clip: t_clip = tc
                t_used = min(t_ground, t_clip)
            else:
                t_used = t_ground
            corners.append(cam + t_used * ray)
        if len(corners) != 4:
            return
        corners = np.array(corners)
        # Ground rectangle outline
        ax2.add_collection3d(Poly3DCollection(
            [corners.tolist()], facecolor=color, edgecolor=color,
            linewidth=1.3, alpha=alpha))
        # Side rays (frustum edges)
        for c in corners:
            ax2.plot([cam[0], c[0]], [cam[1], c[1]], [cam[2], c[2]],
                      color=color, linewidth=0.8, alpha=0.65)
        # Camera body marker
        ax2.scatter([cam[0]], [cam[1]], [cam[2]], c=color, s=90,
                     edgecolor="white", linewidths=1.2, zorder=6)
        if label:
            ax2.text(cam[0], cam[1], cam[2] + 3, label, fontsize=9, color=color,
                      ha="center", fontweight="bold")

    # Waypoint at altitude (height = ALTITUDE above ground z=0)
    camera_xyz = (cx, cz, ALTITUDE)
    # Clip frustums to scene bounds so far-edge rays don't extend infinitely
    clip = (bmn[0], bmx[0], bmn[2], bmx[2])
    # Nadir
    draw_frustum(camera_xyz, (cx, cz, 0.0), color="#2b6cb0",
                  label="Nadir", alpha=0.22, clip_bounds=clip)
    # 4 oblique
    for az_deg in OBLIQUE_AZIMUTHS:
        az = math.radians(az_deg)
        tx = cx + oblique_r * math.sin(az)
        tz = cz + oblique_r * math.cos(az)
        color = {0: "#38a169", 90: "#d69e2e",
                 180: "#b83280", 270: "#805ad5"}[az_deg]
        label = {0: "N", 90: "E", 180: "S", 270: "W"}[az_deg]
        draw_frustum(camera_xyz, (tx, tz, 0.0), color=color,
                      label=f"Obl {label}", alpha=0.14, clip_bounds=clip)

    # Scene-bounds rectangle at ground
    ax2.plot([bmn[0], bmx[0], bmx[0], bmn[0], bmn[0]],
              [bmn[2], bmn[2], bmx[2], bmx[2], bmn[2]],
              [0, 0, 0, 0, 0], color="#e53e3e", linewidth=1.5)

    ax2.set_xlim(bmn[0] - 10, bmx[0] + 10)
    ax2.set_ylim(bmn[2] - 10, bmx[2] + 10)
    ax2.set_zlim(0, ALTITUDE * 1.15)
    span = (bmx[0] - bmn[0])
    ax2.set_box_aspect((1, 1, ALTITUDE * 1.15 / span))
    ax2.view_init(elev=25, azim=-55)
    ax2.set_xlabel("X east (m)")
    ax2.set_ylabel("Y north (m)")
    ax2.set_zlabel("altitude (m)")
    ax2.set_title(f"(2) 3D: 5 captures at central waypoint (altitude {ALTITUDE:.0f}m)\n"
                   f"1 nadir (straight down) + 4 oblique (45° tilt toward N/E/S/W)")
    # Legend via proxy patches
    from matplotlib.lines import Line2D
    legend_items = [
        Line2D([0], [0], color="#2b6cb0", lw=3, label="Nadir cam + frustum"),
        Line2D([0], [0], color="#38a169", lw=3, label="Oblique N (45° tilt, look north)"),
        Line2D([0], [0], color="#d69e2e", lw=3, label="Oblique E"),
        Line2D([0], [0], color="#b83280", lw=3, label="Oblique S"),
        Line2D([0], [0], color="#805ad5", lw=3, label="Oblique W"),
    ]
    ax2.legend(handles=legend_items, loc="upper left", fontsize=8)

    plt.suptitle(
        f"Phase 2 Pix4D-standard UAV mission plan  "
        f"(alt {ALTITUDE:.0f}m, FOV {FOV_DEG_H:.0f}°, "
        f"GSD ~{fw/RES_W*100:.1f} cm, 80%/70% overlap, 4-oblique)",
        fontsize=13, y=1.00)
    plt.tight_layout()
    out = FIG_DIR / "flight_plan.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"[fp] saved: {out}")


if __name__ == "__main__":
    main()
