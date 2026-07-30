"""Compose Phase 2 scene from a natural 200x200m Amsterdam Jordaan block.

Reads selected_block.json (from select_block.py) and writes scene.obj with:
  - World (EPSG:7415) positions preserved RELATIVELY (block recentered to origin);
    buildings keep their real relative positions -> real urban block topology
  - Ground at Y=0 (COLMAP -Y up convention), roofs at Y<0
  - Per-face material tags: Roof / Wall / Ground / Terrain
  - Large Terrain quad covering the 200x200m extent
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "synthetic_a"))

from buildings_3dbag import parse_tile  # noqa: E402

OUT_DIR = ROOT / "results/phase2_synthesis"

# Mapping: buildings_3dbag.py label {1=Roof, 2=Wall, 3=Ground}
LABEL_TO_NAME = {1: "Roof", 2: "Wall", 3: "Ground"}

# Pad the ground plane around the block
GROUND_PAD = 15.0  # meters beyond window edge


def load_selected_buildings_with_world_geometry(block_meta):
    """For each building in the selected block, recover full mesh (vertices,
    faces, labels) in WORLD coords (EPSG:7415).

    `parse_tile` centers each building at origin; we have to re-read the raw
    CityJSON to reconstruct the world-position version.
    """
    target_names = {b["name"] for b in block_meta["buildings"]}
    tiles_by_source = {}
    for b in block_meta["buildings"]:
        tiles_by_source.setdefault(b["source_tile"], []).append(b["name"])

    result = []
    for tile_name, names in tiles_by_source.items():
        tile_path = ROOT / "results/synthetic_a/3dbag_raw/amsterdam_jordaan" / tile_name
        # Parsed (centered) version — already has classified faces / labels
        parsed = {b["name"]: b for b in parse_tile(str(tile_path))}
        # Raw CityJSON — for world coords
        cj = json.load(open(tile_path))
        scale = np.array(cj["transform"]["scale"])
        translate = np.array(cj["transform"]["translate"])
        raw_verts = np.array(cj["vertices"], dtype=np.float64)
        world_verts = raw_verts * scale + translate

        for name in names:
            if name not in parsed:
                continue
            b = parsed[name]
            # 3D BAG structure: Building "X" has only LOD0 MultiSurface.
            # The LOD2.2 Solid lives in BuildingPart "X-0" (child).
            # parse_tile merges both; we need the LOD2.2 geometry from the
            # BuildingPart child.
            chosen = None
            for cand_name in [name] + [f"{name}-{i}" for i in range(5)]:
                obj = cj["CityObjects"].get(cand_name)
                if obj is None:
                    continue
                for g in obj.get("geometry", []):
                    if str(g.get("lod", "")) in ("2.2", "2"):
                        chosen = g
                        break
                if chosen is not None:
                    break
            if chosen is None:
                continue

            # Collect global vertex indices used by this geometry
            global_idxs = []
            def walk(b):
                if isinstance(b, list):
                    if b and isinstance(b[0], int):
                        global_idxs.extend(b)
                    else:
                        for x in b: walk(x)
            walk(chosen.get("boundaries", []))
            if not global_idxs:
                continue

            # Keep unique indices, build local index map
            unique_idxs = sorted(set(global_idxs))
            g2l = {g: i for i, g in enumerate(unique_idxs)}
            v_world = world_verts[unique_idxs]  # (V, 3) EPSG:7415 meters

            # Rebuild faces using the hierarchy: boundaries -> shells -> surfaces -> rings
            # chosen["boundaries"] for Solid: [shell0, shell1, ...] each shell = [surf, surf, ...]
            #                                    surf = [ring0, ring1, ...] ring = [v_idx, ...]
            bnds = chosen["boundaries"]
            if not bnds: continue
            # For Solid, outer shell = bnds[0]. For MultiSurface, bnds = [surf, ...].
            shell = bnds[0] if (bnds and isinstance(bnds[0], list) and
                                bnds[0] and isinstance(bnds[0][0], list) and
                                bnds[0][0] and isinstance(bnds[0][0][0], list)) else bnds

            faces_local = []
            labels = []
            # Pull semantic labels from parsed (same face order maintained by parse_tile).
            parsed_labels = list(b["labels"])
            parsed_faces = list(b["faces"])

            # parse_tile's face ordering should match our outer-shell traversal.
            for i, surf in enumerate(shell):
                ring = surf[0]  # outer ring
                fi = [g2l[g] for g in ring if g in g2l]
                if len(fi) < 3:
                    continue
                faces_local.append(fi)
                # Use parsed label if available, else guess from face normal.
                if i < len(parsed_labels):
                    labels.append(int(parsed_labels[i]))
                else:
                    labels.append(2)  # fallback = Wall

            # Drop buildings with mismatched faces
            if len(faces_local) != len(parsed_faces):
                # fallback: use parsed faces, but then vertices don't match.
                # Safer to drop this building to avoid broken meshes.
                continue

            result.append({
                "name": name,
                "type": b["type"],
                "world_vertices": v_world,   # (V, 3) meters EPSG:7415
                "faces": faces_local,
                "labels": labels,
                "ground_area": float(b.get("ground_area", 0.0)),
            })

    return result


def world_to_colmap_frame(v_world, x0, y0, z_ground):
    """Transform WORLD coords (EPSG:7415 Z-up, meters) → OBJ/COLMAP frame (-Y up).

    - Recenter XY to block center (x0, y0)
    - Use ground as reference: z_world - z_ground -> up amount in meters
    - COLMAP convention: Y is up-axis (negative = up). So:
        obj_x = world_x - x0     (east/west, unchanged)
        obj_y = -(world_z - z_ground)   (height: z_world>z_ground → obj_y<0 = above)
        obj_z = world_y - y0     (north/south, unchanged; COLMAP Z horizontal)
    """
    out = np.empty_like(v_world, dtype=np.float32)
    out[:, 0] = v_world[:, 0] - x0
    out[:, 1] = -(v_world[:, 2] - z_ground)
    out[:, 2] = v_world[:, 1] - y0
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    block = json.loads((OUT_DIR / "selected_block.json").read_text())
    window = block["window"]
    cx_world, cy_world = window["center"]

    print(f"[compose] loading full geometry for {block['n_buildings']} buildings …")
    buildings = load_selected_buildings_with_world_geometry(block)
    print(f"[compose] reconstructed meshes for {len(buildings)} buildings")
    if len(buildings) < 0.8 * block["n_buildings"]:
        print(f"[compose] WARN: only {len(buildings)}/{block['n_buildings']} reconstructed")

    # Determine ground Z (EPSG:7415 Z) from the lowest vertex across all buildings.
    # Using global min keeps ground level consistent.
    z_min = min(float(b["world_vertices"][:, 2].min()) for b in buildings)

    # Build OBJ
    mtls = {
        "Roof":    (0.86, 0.24, 0.24),
        "Wall":    (0.24, 0.31, 0.78),
        "Ground":  (0.35, 0.62, 0.35),
        "Terrain": (0.50, 0.55, 0.45),
    }
    lines = ["# Phase 2 scene: natural Amsterdam Jordaan 200x200m block",
             f"# block center EPSG:7415 = ({cx_world:.2f}, {cy_world:.2f})",
             f"# ground Z (EPSG:7415) = {z_min:.3f}m  (mapped to OBJ Y=0)",
             "mtllib scene.mtl"]
    v_offset = 1  # OBJ 1-based
    scene_info = []
    total_verts = 0
    total_faces = 0

    for b in buildings:
        v_obj = world_to_colmap_frame(b["world_vertices"], cx_world, cy_world, z_min)
        lines.append(f'o {b["name"]}_{b["type"]}')
        for vx, vy, vz in v_obj:
            lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}")
        for fi, face in enumerate(b["faces"]):
            mtl_name = LABEL_TO_NAME.get(b["labels"][fi], "Wall")
            lines.append(f"usemtl {mtl_name}")
            lines.append("s off")
            lines.append("f " + " ".join(str(idx + v_offset) for idx in face))
        scene_info.append({
            "name": b["name"], "type": b["type"],
            "n_vertices": int(len(v_obj)), "n_faces": int(len(b["faces"])),
            "bbox_min": v_obj.min(axis=0).tolist(),
            "bbox_max": v_obj.max(axis=0).tolist(),
        })
        v_offset += len(v_obj)
        total_verts += len(v_obj)
        total_faces += len(b["faces"])

    # Ground plane: 200x200 + GROUND_PAD
    half = window["size"] / 2 + GROUND_PAD
    lines.append("# Ground plane (Terrain)")
    lines.append("o ground_plane")
    ground_corners = [
        (-half, 0.0, -half),
        ( half, 0.0, -half),
        ( half, 0.0,  half),
        (-half, 0.0,  half),
    ]
    for vx, vy, vz in ground_corners:
        lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}")
    lines.append("usemtl Terrain")
    lines.append("s off")
    lines.append(f"f {v_offset} {v_offset+1} {v_offset+2} {v_offset+3}")
    v_offset += 4
    total_verts += 4

    # Scene-level bbox
    sbbmin = np.min([si["bbox_min"] for si in scene_info], axis=0).tolist()
    sbbmax = np.max([si["bbox_max"] for si in scene_info], axis=0).tolist()
    sbbmin[0] = min(sbbmin[0], -half)
    sbbmax[0] = max(sbbmax[0],  half)
    sbbmin[2] = min(sbbmin[2], -half)
    sbbmax[2] = max(sbbmax[2],  half)
    sbbmax[1] = max(sbbmax[1], 0.0)

    # Write OBJ / MTL
    (OUT_DIR / "scene.obj").write_text("\n".join(lines))
    (OUT_DIR / "scene.mtl").write_text("\n".join(
        f"newmtl {name}\nKd {r:.3f} {g:.3f} {b:.3f}\nKa 0.100 0.100 0.100\nKs 0.000 0.000 0.000\nNs 1\nd 1"
        for name, (r, g, b) in mtls.items()
    ))

    layout = {
        "source": "Amsterdam Jordaan natural block",
        "window_center_epsg7415": [cx_world, cy_world],
        "window_size_m": window["size"],
        "ground_z_epsg7415_m": z_min,
        "n_buildings": len(buildings),
        "type_counts": block["type_counts"],
        "total_vertices": total_verts,
        "total_faces": total_faces,
        "ground_pad_m": GROUND_PAD,
        "scene_bbox_min": [float(x) for x in sbbmin],
        "scene_bbox_max": [float(x) for x in sbbmax],
        "buildings": scene_info,
    }
    (OUT_DIR / "scene_layout.json").write_text(json.dumps(layout, indent=2))

    print(f"[compose] wrote scene.obj: {total_verts} verts, {total_faces} faces + 1 ground quad")
    print(f"[compose] scene bbox:")
    print(f"          X: [{sbbmin[0]:.1f}, {sbbmax[0]:.1f}]  (width  {sbbmax[0]-sbbmin[0]:.1f} m)")
    print(f"          Y: [{sbbmin[1]:.1f}, {sbbmax[1]:.1f}]  (height {sbbmax[1]-sbbmin[1]:.1f} m, ground=0, roofs <0)")
    print(f"          Z: [{sbbmin[2]:.1f}, {sbbmax[2]:.1f}]  (depth  {sbbmax[2]-sbbmin[2]:.1f} m)")


if __name__ == "__main__":
    main()
