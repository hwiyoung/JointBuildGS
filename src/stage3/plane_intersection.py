"""
Step 3: Building Solid Construction from Plane Intersections

Supports two modes:
  - Convex polytope (general case, pitched roofs)
  - Footprint-based extrusion (flat roofs, handles non-convex footprints)
"""

from collections import defaultdict

import numpy as np
from scipy.spatial import ConvexHull


def intersect_three_planes(n1, d1, n2, d2, n3, d3):
    """Solve n1·x=d1, n2·x=d2, n3·x=d3 for x."""
    A = np.array([n1, n2, n3])
    det = np.linalg.det(A)
    if abs(det) < 1e-10:
        return None
    return np.linalg.solve(A, np.array([d1, d2, d3]))


def build_convex_polytope(groups, prim_centers, hs_tol=0.05, plane_tol=0.1,
                          bbox_margin=None):
    """
    Build building polyhedron as a convex polytope.

    Each surface group defines a half-space: n_i · x <= d_i (outward normal).
    Valid vertices = 3-plane intersections satisfying ALL half-spaces.
    ConvexHull of valid vertices -> manifold solid.

    bbox_margin: if None, auto = max(5.0, 0.5 * building extent). Centroids of
    faces lie inside the building shell; corners can be up to ~half a face
    width outside the centroid bbox, so a too-small margin rejects all valid
    corners and the polytope construction fails (typical symptom on flat
    buildings: "Initial simplex flat" from QHull).

    Returns: {group_idx: polygon_vertices_ndarray} or None
    """
    N = len(groups)
    if N < 4:
        return None

    normals = np.array([g['plane_normal'] for g in groups])
    ds = np.array([g['plane_d'] for g in groups])

    if bbox_margin is None:
        extent = float((prim_centers.max(axis=0) - prim_centers.min(axis=0)).max())
        bbox_margin = max(5.0, 0.5 * extent)

    bbox_min = prim_centers.min(axis=0) - bbox_margin
    bbox_max = prim_centers.max(axis=0) + bbox_margin

    # Enumerate all 3-plane intersection vertices
    valid_verts = []
    for i in range(N):
        for j in range(i + 1, N):
            for k in range(j + 1, N):
                pt = intersect_three_planes(
                    normals[i], ds[i], normals[j], ds[j], normals[k], ds[k])
                if pt is None:
                    continue
                if np.any(normals @ pt - ds > hs_tol):
                    continue
                if np.any(pt < bbox_min) or np.any(pt > bbox_max):
                    continue
                valid_verts.append(pt)

    if len(valid_verts) < 4:
        return None

    valid_verts = np.array(valid_verts)

    # Deduplicate close vertices
    unique = [0]
    for i in range(1, len(valid_verts)):
        if all(np.linalg.norm(valid_verts[i] - valid_verts[j]) > 0.001
               for j in unique):
            unique.append(i)
    valid_verts = valid_verts[unique]

    if len(valid_verts) < 4:
        return None

    try:
        hull = ConvexHull(valid_verts)
    except Exception as e:
        print(f"    ConvexHull failed: {e}")
        return None

    # Map hull triangles to surface groups
    group_tris = defaultdict(list)
    unmatched = 0

    for fi, simplex in enumerate(hull.simplices):
        face_verts = valid_verts[simplex]

        best_gi, best_res = -1, float('inf')
        for gi in range(N):
            max_res = float(np.abs(normals[gi] @ face_verts.T - ds[gi]).max())
            if max_res < best_res:
                best_res = max_res
                best_gi = gi

        if best_res < plane_tol:
            group_tris[best_gi].append(simplex.tolist())
        else:
            eq = hull.equations[fi][:3]
            eq_len = np.linalg.norm(eq)
            if eq_len > 1e-10:
                fn = eq / eq_len
                cos_sims = normals @ fn
                best = int(np.argmax(cos_sims))
                if cos_sims[best] > 0.3:
                    group_tris[best].append(simplex.tolist())
                else:
                    unmatched += 1
            else:
                unmatched += 1

    if unmatched:
        print(f"    WARNING: {unmatched} hull faces unmatched")

    # Merge coplanar triangles into polygons
    polygons = {}
    for gi, tris in group_tris.items():
        pts = _merge_coplanar_triangles(valid_verts, tris, groups[gi]['plane_normal'])
        if pts is not None and len(pts) >= 3:
            polygons[gi] = pts

    print(f"    Polytope: {len(valid_verts)} verts, {len(hull.simplices)} hull tris -> "
          f"{len(polygons)}/{N} groups used")

    return polygons


def build_footprint_solid(groups, prim_centers, hs_tol=0.05, **kwargs):
    """Build building solid from wall/roof/ground groups.

    Uses 2D plane arrangement for footprint extraction (handles non-convex).
    Falls back to convex polytope for pitched roofs.
    """
    roof_groups = [(i, g) for i, g in enumerate(groups)
                   if g['class'] == 1 and not g.get('is_bbox')]
    ground_groups = [(i, g) for i, g in enumerate(groups)
                     if g.get('is_ground')]

    if not roof_groups or not ground_groups:
        return build_convex_polytope(groups, prim_centers, hs_tol=hs_tol)

    roof_normals = [g['plane_normal'] for _, g in roof_groups]
    if len(roof_normals) == 1:
        all_flat = abs(roof_normals[0][1]) > 0.85
    else:
        all_flat = all(abs(np.dot(roof_normals[i], roof_normals[j])) > 0.95
                       for i in range(len(roof_normals))
                       for j in range(i + 1, len(roof_normals)))
        all_flat = all_flat and all(abs(n[1]) > 0.85 for n in roof_normals)

    if not all_flat:
        return build_convex_polytope(groups, prim_centers, hs_tol=hs_tol)

    footprint_poly = _arrangement_footprint(groups, prim_centers)
    if footprint_poly is None:
        return build_convex_polytope(groups, prim_centers, hs_tol=hs_tol)

    footprint = np.array(footprint_poly.exterior.coords[:-1])
    n_fp = len(footprint)

    roof_g = max(roof_groups, key=lambda x: x[1].get('area', 0))
    roof_ny = roof_g[1]['plane_normal'][1]
    roof_y = roof_g[1]['plane_d'] / roof_ny if abs(roof_ny) > 0.1 else roof_g[1]['center'][1]

    ground_ny = ground_groups[0][1]['plane_normal'][1]
    ground_y = ground_groups[0][1]['plane_d'] / ground_ny if abs(ground_ny) > 0.1 else ground_groups[0][1]['center'][1]

    verts_top = [np.array([pt[0], roof_y, pt[1]]) for pt in footprint]
    verts_bot = [np.array([pt[0], ground_y, pt[1]]) for pt in footprint]

    polygons = {}
    polygons[roof_g[0]] = np.array(verts_top[::-1])
    polygons[ground_groups[0][0]] = np.array(verts_bot)

    wall_groups_list = [(i, g) for i, g in enumerate(groups)
                        if g['class'] == 2 and not g.get('is_bbox')]

    for ei in range(n_fp):
        ej = (ei + 1) % n_fp
        quad = np.array([verts_top[ei], verts_top[ej],
                         verts_bot[ej], verts_bot[ei]])

        edge_xz = footprint[ej] - footprint[ei]
        wn_xz = np.array([edge_xz[1], -edge_xz[0]])
        wn_xz /= np.linalg.norm(wn_xz) + 1e-12
        mid = (footprint[ei] + footprint[ej]) / 2
        centroid = footprint.mean(0)
        if np.dot(wn_xz, mid - centroid) < 0:
            wn_xz = -wn_xz
        wn_3d = np.array([wn_xz[0], 0, wn_xz[1]])

        best_gi, best_cos = -1, -1
        for wi, wg in wall_groups_list:
            cos = float(np.dot(wn_3d, wg['plane_normal']))
            if cos > best_cos:
                best_cos = cos
                best_gi = wi

        if best_gi >= 0 and best_cos > 0.5 and best_gi not in polygons:
            polygons[best_gi] = quad
        else:
            vgi = len(groups)
            groups.append({
                'plane_normal': wn_3d, 'plane_d': 0, 'class': 2,
                'prim_ids': [], 'center': quad.mean(0), 'area': 0,
                'is_bbox': True,
            })
            polygons[vgi] = quad

    print(f"    Footprint: {n_fp} corners, {len(polygons)} faces")
    return polygons


def _arrangement_footprint(groups, centers, bbox_margin=5.0):
    """Extract 2D footprint via plane arrangement + cell labeling."""
    from shapely.geometry import Polygon as SPoly, LineString as SLine, Point as SPoint
    from shapely.ops import split as shapely_split, unary_union

    wall_groups = [(i, g) for i, g in enumerate(groups)
                   if g['class'] == 2 and not g.get('is_bbox')]
    if len(wall_groups) < 3:
        return None

    xz = centers[:, [0, 2]]
    bmin = xz.min(0) - bbox_margin
    bmax = xz.max(0) + bbox_margin

    lines = []
    for _, g in wall_groups:
        nx, nz = g['plane_normal'][0], g['plane_normal'][2]
        if abs(nx) < 1e-6 and abs(nz) < 1e-6:
            continue
        d = g['plane_d']
        if abs(nx) > abs(nz):
            z1, z2 = bmin[1] - 5, bmax[1] + 5
            x1, x2 = (d - nz * z1) / nx, (d - nz * z2) / nx
        else:
            x1, x2 = bmin[0] - 5, bmax[0] + 5
            z1, z2 = (d - nx * x1) / nz, (d - nx * x2) / nz
        lines.append(SLine([(x1, z1), (x2, z2)]))

    bbox_poly = SPoly([
        (bmin[0], bmin[1]), (bmax[0], bmin[1]),
        (bmax[0], bmax[1]), (bmin[0], bmax[1]),
    ])
    cells = [bbox_poly]
    for line in lines:
        new_cells = []
        for cell in cells:
            try:
                parts = shapely_split(cell, line)
                new_cells.extend(parts.geoms)
            except Exception:
                new_cells.append(cell)
        cells = new_cells

    prim_xz_pts = [SPoint(p) for p in xz]
    inside_cells = []
    for cell in cells:
        if cell.area < 0.01:
            continue
        if any(cell.contains(p) for p in prim_xz_pts):
            inside_cells.append(cell)

    if not inside_cells:
        return None

    footprint = unary_union(inside_cells)
    if footprint.geom_type == 'MultiPolygon':
        footprint = max(footprint.geoms, key=lambda g: g.area)
    if footprint.geom_type != 'Polygon' or footprint.area < 0.1:
        return None

    footprint = footprint.simplify(0.01, preserve_topology=True)
    return footprint


def _merge_coplanar_triangles(vertices, tris, group_normal):
    """Merge coplanar triangles from ConvexHull into a single polygon."""
    if len(tris) == 1:
        pts = vertices[tris[0]]
        e1, e2 = pts[1] - pts[0], pts[2] - pts[0]
        if np.dot(np.cross(e1, e2), group_normal) < 0:
            pts = pts[::-1]
        return pts

    edge_count = defaultdict(int)
    for tri in tris:
        for a in range(3):
            e = tuple(sorted([tri[a], tri[(a + 1) % 3]]))
            edge_count[e] += 1

    boundary = [e for e, c in edge_count.items() if c == 1]
    if len(boundary) < 3:
        if len(tris) == 1:
            return vertices[tris[0]]
        return None

    adj = defaultdict(set)
    for a, b in boundary:
        adj[a].add(b)
        adj[b].add(a)

    start = boundary[0][0]
    polygon = [start]
    visited = {start}
    current = start
    for _ in range(len(adj) + 1):
        nbs = adj[current] - visited
        if not nbs:
            break
        nxt = next(iter(nbs))
        polygon.append(nxt)
        visited.add(nxt)
        current = nxt

    if len(polygon) < 3:
        return None

    pts = vertices[polygon]
    center = pts.mean(axis=0)
    area_normal = sum(
        np.cross(pts[i] - center, pts[(i + 1) % len(pts)] - center)
        for i in range(len(pts)))
    if np.dot(area_normal, group_normal) < 0:
        pts = pts[::-1]

    return pts
