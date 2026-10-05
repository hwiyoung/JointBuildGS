"""LoD2 faces left out of the prior surface, the outward side of a face and walls shared by two buildings
(prior_propagation_v3, PHD-STAGE2-R9-THREE-FIXES-v1). numpy (+ open3d inside party_wall_cells).

Method document 2026-10-01 (r8 review) 3.1 / 4.3: the bottom face of an LoD2 building (CityGML GroundSurface; a
ClosureSurface when present) lies inside the walls, no view sees it and it is not reconstructed, so it is not part of the
prior surface: neither stage 1 (prior depth render, residuals, tolerance, surface numbers, marks, patches) nor stage 2
(point sampling, planting) takes it. LoD2 without surface types: a face whose normal points down and that lies at the
lowest height of its building is taken as the bottom face, and the caller reports that this rule was used.
Order r9 item 3: inner faces other than the bottom face (walls a building shares with its neighbour) stay in the prior;
they are counted: walls of two buildings that overlap within 0.1 m with opposite normals.

Normals: the winding normal of a polygon (area-weighted mean of its triangles, the normal the stage-1 store uses).
CityGML orients polygons outward; outward_side_outside() checks this for walls against the building's footprint."""
import numpy as np

EXCLUDED_TYPES = ("GroundSurface", "ClosureSurface")
DOWN_NZ = -0.5          # 'the normal points down': n_z <= -0.5 (the roof/wall split |n_z| = 0.5 of conversion.ROOF_NZ)
LOWEST_TOL_M = 0.1      # 'at the lowest height of the building': the face's highest vertex within 0.1 m of the lowest vertex
PARTY_DMAX_M = 0.1      # order r9: overlap within 0.1 m
PARTY_COS = -0.9        # 'opposite normals': cosine <= -0.9 (within about 25 degrees of anti-parallel)


def polygon_table(V, F, tri_poly):
    """per polygon id (sorted unique of tri_poly): winding unit normal, area, area-weighted centroid, lowest and highest
    vertex height. Returns a dict of arrays aligned with 'ids'."""
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64); tp = np.asarray(tri_poly, np.int64)
    cr = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    a = 0.5 * np.linalg.norm(cr, axis=1)
    ids, inv = np.unique(tp, return_inverse=True)
    S = np.zeros((len(ids), 3)); np.add.at(S, inv, cr)
    nrm = S / np.maximum(np.linalg.norm(S, axis=1, keepdims=True), 1e-300)
    area = np.bincount(inv, weights=a, minlength=len(ids))
    C = np.zeros((len(ids), 3)); np.add.at(C, inv, V[F].mean(1) * a[:, None])
    C /= np.maximum(area, 1e-300)[:, None]
    zt = V[F][:, :, 2]
    zmin = np.full(len(ids), np.inf); np.minimum.at(zmin, inv, zt.min(1))
    zmax = np.full(len(ids), -np.inf); np.maximum.at(zmax, inv, zt.max(1))
    return dict(ids=ids, normal=nrm, area=area, centroid=C, zmin=zmin, zmax=zmax)


def excluded_by_type(types):
    """bool per face: its CityGML type is a bottom face (GroundSurface) or a closure face (ClosureSurface)."""
    return np.isin(np.asarray(types).astype(str), EXCLUDED_TYPES)


def bottom_faces_untyped(normal_z, z_max_face, z_min_building):
    """bool per face of LoD2 without surface types: the (outward) normal points down and the face lies at the lowest
    height of its building (its highest vertex within LOWEST_TOL_M of the building's lowest vertex)."""
    return (np.asarray(normal_z) <= DOWN_NZ) & (np.asarray(z_max_face) <= np.asarray(z_min_building) + LOWEST_TOL_M)


def _in_triangles_xy(P, T):
    """bool [N]: P [N, 2] inside (or on) any triangle of T [M, 3, 2]."""
    P = np.asarray(P, np.float64)[:, None, :]; T = np.asarray(T, np.float64)[None]
    if T.shape[1] == 0:
        return np.zeros(P.shape[0], bool)

    def cross(a, b, p):
        return (b[..., 0] - a[..., 0]) * (p[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (p[..., 0] - a[..., 0])
    d1 = cross(T[..., 0, :], T[..., 1, :], P); d2 = cross(T[..., 1, :], T[..., 2, :], P); d3 = cross(T[..., 2, :], T[..., 0, :], P)
    neg = (d1 < 0) | (d2 < 0) | (d3 < 0); pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return (~(neg & pos)).any(1)


def outward_side_outside(centroid, normal, footprint_tris_xy, step=0.05):
    """For wall faces of one building: (outside_plus [N], outside_minus [N]) whether the centroid moved `step` metres along
    +/- the horizontal part of the normal falls outside every footprint triangle (XY). outside_plus & ~outside_minus:
    the normal points out of the building; the reverse: it points in; both equal: undetermined (e.g. a wall between two
    roof levels above the footprint)."""
    c = np.asarray(centroid, np.float64)[:, :2]; n = np.asarray(normal, np.float64)[:, :2]
    nh = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    plus = ~_in_triangles_xy(c + step * nh, footprint_tris_xy)
    minus = ~_in_triangles_xy(c - step * nh, footprint_tris_xy)
    return plus, minus


def party_wall_cells(cell_xyz, cell_building, cell_normal, wall_V, wall_F, wall_tri_building, wall_tri_normal,
                     dmax=PARTY_DMAX_M, cos_opposite=PARTY_COS):
    """Cells (patch centres) of walls that a building shares with another one: the centre lies within dmax of a wall
    triangle of another building whose (outward) normal is opposite (cosine <= cos_opposite).
    Returns (shared [C] bool, distance [C], partner triangle [C] (-1 none))."""
    import open3d as o3d
    cell_xyz = np.asarray(cell_xyz, np.float64); cell_building = np.asarray(cell_building).astype(str)
    wall_tri_building = np.asarray(wall_tri_building).astype(str)
    shared = np.zeros(len(cell_xyz), bool); dist = np.full(len(cell_xyz), np.inf); partner = np.full(len(cell_xyz), -1, np.int64)
    for b in np.unique(cell_building):
        sc_ = cell_building == b
        other = np.nonzero(wall_tri_building != b)[0]
        if len(other) == 0 or not sc_.any():
            continue
        scene = o3d.t.geometry.RaycastingScene()
        scene.add_triangles(o3d.core.Tensor(np.asarray(wall_V, np.float32)), o3d.core.Tensor(np.asarray(wall_F, np.uint32)[other]))
        ans = scene.compute_closest_points(o3d.core.Tensor(cell_xyz[sc_].astype(np.float32)))
        d = np.linalg.norm(ans["points"].numpy().astype(np.float64) - cell_xyz[sc_], axis=1)
        tri = other[ans["primitive_ids"].numpy().astype(np.int64)]
        opp = (np.asarray(wall_tri_normal, np.float64)[tri] * np.asarray(cell_normal, np.float64)[sc_]).sum(1) <= cos_opposite
        shared[sc_] = (d <= dmax) & opp
        dist[sc_] = d
        partner[sc_] = np.where((d <= dmax) & opp, tri, -1)
    return shared, dist, partner
