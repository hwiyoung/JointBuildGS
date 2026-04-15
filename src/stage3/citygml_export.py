"""
Step 4: CityJSON Output + PLY Export
"""

import json
import os

import numpy as np


def compute_signed_volume(surfaces):
    """Signed volume of a closed solid from its face polygons."""
    volume = 0.0
    for verts in surfaces:
        if len(verts) < 3:
            continue
        v0 = verts[0]
        for i in range(1, len(verts) - 1):
            volume += np.dot(v0, np.cross(verts[i], verts[i + 1]))
    return volume / 6.0


def build_cityjson(building_id, groups, polygons, out_dir):
    """Build CityJSON 2.0 Solid with shared vertices and proper topology."""
    scale = 0.0001
    vert_map = {}
    all_verts = []

    def add_vertex(pt):
        ix = round(pt[0] / scale)
        iy = round(pt[1] / scale)
        iz = round(pt[2] / scale)
        key = (ix, iy, iz)
        if key not in vert_map:
            vert_map[key] = len(vert_map)
            all_verts.append([ix, iy, iz])
        return vert_map[key]

    surface_data = []
    for gi in sorted(polygons.keys()):
        verts = polygons[gi]
        indices = [add_vertex(v) for v in verts]

        # Remove consecutive duplicates
        cleaned = [indices[0]]
        for idx in indices[1:]:
            if idx != cleaned[-1]:
                cleaned.append(idx)
        if len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
            cleaned = cleaned[:-1]
        if len(cleaned) < 3:
            continue

        cls = groups[gi]['class']
        if groups[gi].get('is_ground'):
            stype = "GroundSurface"
        else:
            stype = {1: "RoofSurface", 2: "WallSurface"}.get(cls, "GroundSurface")

        surface_data.append({
            'group_idx': gi,
            'indices': cleaned,
            'type': stype,
            'normal': groups[gi]['plane_normal'].copy(),
        })

    if len(surface_data) < 4:
        print(f"  WARNING: Building {building_id}: only {len(surface_data)} surfaces, skip")
        return None

    # Ensure at least one GroundSurface exists
    has_ground = any(sd['type'] == 'GroundSurface' for sd in surface_data)
    if not has_ground:
        best_idx = max(range(len(surface_data)), key=lambda i: surface_data[i]['normal'][1])
        if surface_data[best_idx]['normal'][1] > 0.3:
            surface_data[best_idx]['type'] = 'GroundSurface'

    # Check signed volume, flip all windings if negative
    surf_verts = [np.array([np.array(all_verts[i]) * scale for i in sd['indices']])
                  for sd in surface_data]
    vol = compute_signed_volume(surf_verts)
    if vol < 0:
        for sd in surface_data:
            sd['indices'] = sd['indices'][::-1]
        vol = -vol

    # CityJSON structure
    translate = [min(v[j] for v in all_verts) * scale for j in range(3)]
    t_ijk = [round(translate[j] / scale) for j in range(3)]
    adjusted_verts = [[v[j] - t_ijk[j] for j in range(3)] for v in all_verts]

    boundaries = []
    sem_surfaces = []
    sem_values = []
    for i, sd in enumerate(surface_data):
        boundaries.append([sd['indices']])
        sem_surfaces.append({"type": sd['type']})
        sem_values.append(i)

    building_name = (f"building_{building_id:03d}" if isinstance(building_id, int)
                     else f"building_{building_id}")
    cityjson = {
        "type": "CityJSON",
        "version": "2.0",
        "transform": {"scale": [scale] * 3, "translate": translate},
        "CityObjects": {
            building_name: {
                "type": "Building",
                "attributes": {
                    "building_id": building_id if isinstance(building_id, int) else str(building_id),
                    "n_surfaces": len(surface_data),
                    "signed_volume": float(vol),
                },
                "geometry": [{
                    "type": "Solid",
                    "lod": "2",
                    "boundaries": [boundaries],
                    "semantics": {
                        "surfaces": sem_surfaces,
                        "values": [sem_values],
                    },
                }],
            }
        },
        "vertices": adjusted_verts,
    }

    os.makedirs(out_dir, exist_ok=True)
    cj_path = os.path.join(out_dir, "building.city.json")
    with open(cj_path, 'w') as f:
        json.dump(cityjson, f, indent=2)

    save_lod2_ply(os.path.join(out_dir, "lod2.ply"), surface_data, all_verts,
                  scale, translate)

    # Edge sharing diagnostics
    edges = {}
    for i, sd in enumerate(surface_data):
        ring = sd['indices']
        for j in range(len(ring)):
            v1, v2 = ring[j], ring[(j + 1) % len(ring)]
            edge = (min(v1, v2), max(v1, v2))
            edges.setdefault(edge, []).append(i)

    n_shared = sum(1 for faces in edges.values() if len(faces) == 2)
    n_boundary = sum(1 for faces in edges.values() if len(faces) == 1)
    n_nonmanifold = sum(1 for faces in edges.values() if len(faces) > 2)

    return {
        'building_id': building_id if isinstance(building_id, int) else str(building_id),
        'n_surfaces': len(surface_data),
        'n_vertices': len(all_verts),
        'signed_volume': float(vol),
        'n_edges_shared': n_shared,
        'n_edges_boundary': n_boundary,
        'n_edges_nonmanifold': n_nonmanifold,
        'surface_types': {
            'RoofSurface': sum(1 for s in surface_data if s['type'] == 'RoofSurface'),
            'WallSurface': sum(1 for s in surface_data if s['type'] == 'WallSurface'),
            'GroundSurface': sum(1 for s in surface_data if s['type'] == 'GroundSurface'),
        },
        'cityjson_path': cj_path,
    }


def save_lod2_ply(path, surface_data, all_verts, scale, translate):
    """Save LOD2 model as colored PLY (triangulated)."""
    type_colors = {
        'RoofSurface': [255, 0, 0],
        'WallSurface': [0, 0, 255],
        'GroundSurface': [128, 128, 128],
    }
    tris, colors = [], []
    for sd in surface_data:
        c = type_colors.get(sd['type'], [200, 200, 200])
        idx = sd['indices']
        for i in range(1, len(idx) - 1):
            tris.append([idx[0], idx[i], idx[i + 1]])
            colors.append(c)
    if not tris:
        return
    with open(path, 'w') as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(all_verts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write(f"element face {len(tris)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for v in all_verts:
            f.write(f"{v[0]*scale+translate[0]:.6f} {v[1]*scale+translate[1]:.6f} "
                    f"{v[2]*scale+translate[2]:.6f}\n")
        for tri, c in zip(tris, colors):
            f.write(f"3 {tri[0]} {tri[1]} {tri[2]} {c[0]} {c[1]} {c[2]}\n")
