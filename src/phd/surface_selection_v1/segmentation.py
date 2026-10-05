"""Source-only connected planar surfaces with immutable native point membership.

The 3-D voxel grid is a computational index. Its representative is an actual
source point, and all final fits, residuals and membership use the original XYZ.
No reference geometry, source preference or currentness evidence enters here.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

import numpy as np
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class SegmentationConfig:
    voxel_size_m: float = 0.30
    normal_radius_m: float = 1.20
    normal_neighbors: int = 24
    min_normal_neighbors: int = 6
    max_surface_variation: float = 0.08
    minimum_second_spread_m: float = 0.10
    connectivity_radius_m: float = 0.80
    connectivity_neighbors: int = 20
    normal_angle_deg: float = 18.0
    local_plane_distance_m: float = 0.18
    surface_distance_m: float = 0.22
    min_voxels: int = 12
    min_native_points: int = 30
    min_area_xy_m2: float = 1.0
    occupancy_grid_m: float = 0.50
    adjacency_radius_m: float = 1.25
    adjacency_neighbors: int = 24
    adjacency_min_contacts: int = 3
    coplanar_angle_deg: float = 10.0
    coplanar_distance_m: float = 0.20
    query_chunk: int = 4096


def _config(value):
    if value is None:
        result = SegmentationConfig()
    elif isinstance(value, SegmentationConfig):
        result = value
    else:
        unknown = set(value) - set(asdict(SegmentationConfig()))
        if unknown:
            raise ValueError(f"Unknown segmentation keys: {sorted(unknown)}")
        result = SegmentationConfig(**value)
    for name, number in asdict(result).items():
        if not np.isfinite(number) or number <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if result.min_normal_neighbors > result.normal_neighbors:
        raise ValueError("min_normal_neighbors exceeds normal_neighbors")
    if result.normal_angle_deg >= 90 or result.coplanar_angle_deg >= 90:
        raise ValueError("Normal angle thresholds must be below 90 degrees")
    return result


def _orient(normal, up):
    normal = np.asarray(normal, dtype=np.float64)
    dot = float(normal @ up)
    if dot < -1e-12 or (abs(dot) <= 1e-12 and normal[np.argmax(np.abs(normal))] < 0):
        normal = -normal
    return normal


def _fit(points, up):
    center = np.mean(points, axis=0)
    centered = points - center
    values, vectors = np.linalg.eigh(centered.T @ centered / max(1, len(points)))
    return center, _orient(vectors[:, 0], up), np.maximum(values, 0)


def _representatives(points, size):
    # Input-relative origin keeps voxel membership invariant to XYZ translation.
    origin = np.min(points, axis=0)
    keys = np.floor((points - origin) / size + 1e-9).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    # Representatives are native rows, never voxel centroids or synthetic points.
    return points[first], first, inverse.astype(np.int32), origin


def _local_normals(points, up, cfg, tree):
    n = len(points)
    normals = np.zeros((n, 3), dtype=np.float64)
    variation = np.ones(n, dtype=np.float64)
    planar = np.zeros(n, dtype=bool)
    for start in range(0, n, cfg.query_chunk):
        stop = min(n, start + cfg.query_chunk)
        distance, index = tree.query(points[start:stop], k=cfg.normal_neighbors,
                                     distance_upper_bound=cfg.normal_radius_m, workers=1)
        valid = np.isfinite(distance)
        neighbors = points[np.minimum(index, n - 1)]
        count = valid.sum(axis=1)
        # Work relative to each query point; avoid geospatial large-coordinate loss.
        delta = neighbors - points[start:stop, None, :]
        delta[~valid] = 0
        mean = delta.sum(axis=1) / np.maximum(count[:, None], 1)
        centered = (delta - mean[:, None, :]) * valid[:, :, None]
        covariance = np.einsum("nki,nkj->nij", centered, centered)
        covariance /= np.maximum(count[:, None, None], 1)
        values, vectors = np.linalg.eigh(covariance)
        values = np.maximum(values, 0)
        local = vectors[:, :, 0]
        signs = np.where(local @ up < 0, -1.0, 1.0)
        local *= signs[:, None]
        normals[start:stop] = local
        variation[start:stop] = values[:, 0] / np.maximum(values.sum(axis=1), 1e-12)
        planar[start:stop] = ((count >= cfg.min_normal_neighbors)
                             & (variation[start:stop] <= cfg.max_surface_variation)
                             & (np.sqrt(values[:, 1]) >= cfg.minimum_second_spread_m))
    return normals, variation, planar


def _compatible_graph(points, normals, planar, tree, cfg):
    n = len(points)
    rows, cols = [], []
    cosine = np.cos(np.deg2rad(cfg.normal_angle_deg))
    for start in range(0, n, cfg.query_chunk):
        stop = min(n, start + cfg.query_chunk)
        distance, index = tree.query(points[start:stop], k=cfg.connectivity_neighbors,
                                     distance_upper_bound=cfg.connectivity_radius_m, workers=1)
        source = np.broadcast_to(np.arange(start, stop)[:, None], index.shape)
        safe = np.minimum(index, n - 1)
        delta = points[safe] - points[source]
        good = (np.isfinite(distance) & (index != source)
                & planar[source] & planar[safe]
                & (np.abs(np.einsum("nki,nki->nk", normals[source], normals[safe])) >= cosine)
                & (np.abs(np.einsum("nki,nki->nk", delta, normals[source])) <= cfg.local_plane_distance_m)
                & (np.abs(np.einsum("nki,nki->nk", delta, normals[safe])) <= cfg.local_plane_distance_m))
        rows.append(source[good].astype(np.int32))
        cols.append(index[good].astype(np.int32))
    row, col = np.concatenate(rows), np.concatenate(cols)
    graph = csr_matrix((np.ones(len(row), dtype=bool), (row, col)), shape=(n, n))
    graph = graph.maximum(graph.T).tocsr()
    graph.sort_indices()
    return graph


def _grow(points, normals, variation, planar, graph, up, cfg):
    """Deterministic connected growth, guarded by a fitted whole-surface plane.

    Local normal compatibility alone could chain around a curved surface. The
    growing plane additionally bounds accumulated normal-direction displacement.
    Plane moments use coordinates relative to the seed for numerical stability.
    """
    assigned = np.full(len(points), -1, dtype=np.int32)
    groups = []
    priority = np.lexsort((np.arange(len(points)), variation))
    cosine = np.cos(np.deg2rad(cfg.normal_angle_deg))
    for seed in priority:
        if not planar[seed] or assigned[seed] >= 0:
            continue
        group_id = len(groups)
        origin = points[seed]
        center = origin.copy()
        normal = normals[seed].copy()
        members = [int(seed)]
        assigned[seed] = group_id
        frontier = deque([int(seed)])
        moment = np.zeros(3)
        second = np.zeros((3, 3))
        while frontier:
            node = frontier.popleft()
            for neighbor in graph.indices[graph.indptr[node]:graph.indptr[node + 1]]:
                if assigned[neighbor] >= 0:
                    continue
                if abs(normals[neighbor] @ normal) < cosine:
                    continue
                if abs((points[neighbor] - center) @ normal) > cfg.surface_distance_m:
                    continue
                assigned[neighbor] = group_id
                members.append(int(neighbor))
                frontier.append(int(neighbor))
                delta = points[neighbor] - origin
                moment += delta
                second += np.outer(delta, delta)
                if len(members) % 32 == 0:
                    mean = moment / len(members)
                    covariance = second / len(members) - np.outer(mean, mean)
                    _, vectors = np.linalg.eigh(covariance)
                    center = origin + mean
                    normal = _orient(vectors[:, 0], up)
        groups.append(np.asarray(members, dtype=np.int32))
    return groups, assigned


def _occupancy(points, step, origin):
    keys = np.floor((points[:, :2] - origin[:2]) / step + 1e-9).astype(np.int64)
    return np.unique(keys, axis=0)


def _surface_adjacency(points, labels, components, up, cfg, occupancy_origin):
    """Graph contacts come only from finite occupied surface boundaries.

    Close infinite planes or overlapping bounding boxes are insufficient. XY
    occupancy boundaries are conservative for roofs; vertical surfaces may expose
    most occupied columns as boundary and are explicitly labelled by their tilt.
    """
    nodes = [{k: component[k] for k in ("id", "native_count", "area_xy_m2", "center",
                                      "normal", "valid", "reason")} for component in components]
    edges = []
    if not components:
        return nodes, edges
    candidate_rows = []
    for component in components:
        cid = component["id"]
        occupied = {tuple(v) for v in component["occupancy_xy"]}
        boundary = {key for key in occupied
                    if any((key[0] + dx, key[1] + dy) not in occupied
                           for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))}
        ids = np.flatnonzero(labels == cid)
        keys = np.floor((points[ids, :2] - occupancy_origin[:2]) / cfg.occupancy_grid_m + 1e-9).astype(np.int64)
        candidate_rows.extend(int(row) for row, key in zip(ids, keys) if tuple(key) in boundary)
    if not candidate_rows:
        return nodes, edges
    rows = np.asarray(candidate_rows, dtype=np.int64)
    boundary_points, boundary_labels = points[rows], labels[rows]
    tree = cKDTree(boundary_points)
    contacts = {}
    for start in range(0, len(rows), cfg.query_chunk):
        stop = min(len(rows), start + cfg.query_chunk)
        distance, index = tree.query(boundary_points[start:stop], k=cfg.adjacency_neighbors,
                                     distance_upper_bound=cfg.adjacency_radius_m, workers=1)
        safe = np.minimum(index, len(rows) - 1)
        source = np.broadcast_to(np.arange(start, stop)[:, None], index.shape)
        good = (np.isfinite(distance) & (source < index)
                & (boundary_labels[source] != boundary_labels[safe]))
        for a, b, d in zip(source[good], index[good], distance[good]):
            ca, cb = sorted((int(boundary_labels[a]), int(boundary_labels[b])))
            entry = contacts.setdefault((ca, cb), {"count": 0, "gap": float("inf"), "sites": set()})
            entry["count"] += 1
            entry["gap"] = min(entry["gap"], float(d))
            # Distinct spatial contacts stop one dense point pair implying a seam.
            midpoint = (boundary_points[a] + boundary_points[b]) / 2
            site = tuple(np.floor((midpoint - occupancy_origin) / cfg.occupancy_grid_m + 1e-9).astype(int))
            entry["sites"].add(site)
    for (a, b), value in sorted(contacts.items()):
        ca, cb = components[a], components[b]
        na, nb = np.asarray(ca["normal"]), np.asarray(cb["normal"])
        delta = np.asarray(cb["center"]) - np.asarray(ca["center"])
        angle = float(np.rad2deg(np.arccos(np.clip(abs(na @ nb), 0, 1))))
        offset = float(max(abs(delta @ na), abs(delta @ nb)))
        contact_count = len(value["sites"])
        if contact_count < cfg.adjacency_min_contacts:
            relation = "UNCERTAIN"
        elif angle <= cfg.coplanar_angle_deg and offset <= cfg.coplanar_distance_m:
            relation = "COPLANAR_CONTINUATION"
        else:
            relation = "CREASE_OR_STEP"
        edges.append(dict(source=a, target=b, normal_angle_deg=angle,
                          plane_offset_m=offset, height_delta_m=float(delta @ up),
                          boundary_gap_m=value["gap"], boundary_contact_pairs=value["count"],
                          boundary_contact_sites=contact_count, relation=relation,
                          label_propagation=False))
    return nodes, edges


def segment_source(xyz, up, config=None):
    """Return accepted components, per-native-row membership, and adjacency graph.

    Membership ``-1`` explicitly retains unsupported/rejected/nonfinite rows. IDs
    are deterministic for identical input and start at zero. A component is a
    geometric hypothesis, never an assertion of a roof class or current validity.
    ``up`` must be supplied from the frozen gravity estimate; no axis is assumed.
    """
    cfg = _config(config)
    points = np.asarray(xyz, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("xyz must have shape (N, 3)")
    if up.shape != (3,) or not np.isfinite(up).all() or np.linalg.norm(up) < 1e-9:
        raise ValueError("up must be a finite nonzero 3-D gravity-derived vector")
    up = up / np.linalg.norm(up)
    membership = np.full(len(points), -1, dtype=np.int32)
    finite = np.isfinite(points).all(axis=1)
    native_ids = np.flatnonzero(finite)
    finite_points = points[finite]
    rejected = dict(NONFINITE=int((~finite).sum()), NO_PLANAR_NEIGHBORHOOD=0,
                    SMALL_OR_NARROW_SURFACE=0, PLANE_RESIDUAL=0)
    summary = dict(native_count=len(points), finite_native_count=int(finite.sum()),
                   assigned_native_count=0, unassigned_native_count=len(points),
                   component_count=0, edge_count=0, scientific_verdict=None,
                   native_geometry_replaced=False, decision_propagation=False,
                   unassigned_native_reason_counts=rejected)
    graph = dict(nodes=[], edges=[], summary=summary, config=asdict(cfg),
                 coordinate_contract="input XYZ unchanged; normal-direction plane distances",
                 component_semantics="connected source-only planar hypotheses; not semantic ground truth")
    if not len(finite_points):
        summary["voxel_count"] = 0
        return [], membership, graph
    representatives, representative_native, inverse, origin = _representatives(finite_points, cfg.voxel_size_m)
    summary["voxel_count"] = len(representatives)
    tree = cKDTree(representatives)
    normals, variation, planar = _local_normals(representatives, up, cfg, tree)
    connectivity = _compatible_graph(representatives, normals, planar, tree, cfg)
    groups, provisional = _grow(representatives, normals, variation, planar, connectivity, up, cfg)
    native_provisional = provisional[inverse]
    rejected["NO_PLANAR_NEIGHBORHOOD"] = int((native_provisional < 0).sum())
    # Group native IDs once instead of scanning a million rows per component.
    order = np.argsort(native_provisional, kind="stable")
    starts = np.searchsorted(native_provisional[order], np.arange(len(groups)), side="left")
    stops = np.searchsorted(native_provisional[order], np.arange(len(groups)), side="right")
    accepted = []
    for group_id, voxel_ids in enumerate(groups):
        local_ids = order[starts[group_id]:stops[group_id]]
        if len(voxel_ids) < cfg.min_voxels or len(local_ids) < cfg.min_native_points:
            rejected["SMALL_OR_NARROW_SURFACE"] += len(local_ids)
            continue
        selected = local_ids
        # Native rows are fitted, checked and retained without coordinate averaging.
        for _ in range(3):
            center, normal, values = _fit(finite_points[selected], up)
            residual = np.abs((finite_points[local_ids] - center) @ normal)
            selected = local_ids[residual <= cfg.surface_distance_m]
            if len(selected) < cfg.min_native_points:
                break
        if len(selected) < cfg.min_native_points:
            rejected["SMALL_OR_NARROW_SURFACE"] += len(local_ids)
            continue
        center, normal, values = _fit(finite_points[selected], up)
        residual = np.abs((finite_points[selected] - center) @ normal)
        selected = selected[residual <= cfg.surface_distance_m]
        if len(selected) < cfg.min_native_points:
            rejected["SMALL_OR_NARROW_SURFACE"] += len(local_ids)
            continue
        chosen = finite_points[selected]
        center, normal, values = _fit(chosen, up)
        residual = np.abs((chosen - center) @ normal)
        occupancy = _occupancy(chosen, cfg.occupancy_grid_m, origin)
        area = len(occupancy) * cfg.occupancy_grid_m ** 2
        if area < cfg.min_area_xy_m2 or np.sqrt(values[1]) < cfg.minimum_second_spread_m:
            rejected["SMALL_OR_NARROW_SURFACE"] += len(local_ids)
            continue
        rejected["PLANE_RESIDUAL"] += len(local_ids) - len(selected)
        component = dict(native_count=len(selected), computational_voxel_count=len(voxel_ids),
                         center=center.tolist(), normal=normal.tolist(), rms_m=float(np.sqrt(np.mean(residual ** 2))),
                         p90_m=float(np.quantile(residual, 0.9)), max_residual_m=float(residual.max()),
                         bbox=[chosen.min(axis=0).tolist(), chosen.max(axis=0).tolist()],
                         bbox_xy=[float(chosen[:, 0].min()), float(chosen[:, 1].min()),
                                  float(chosen[:, 0].max()), float(chosen[:, 1].max())],
                         area_xy_m2=float(area), occupancy_grid_m=cfg.occupancy_grid_m,
                         occupancy_origin_xy=origin[:2].tolist(), occupancy_xy=occupancy.tolist(),
                         tilt_from_up_deg=float(np.rad2deg(np.arccos(np.clip(abs(normal @ up), 0, 1)))),
                         minimum_native_row=int(native_ids[selected].min()),
                         valid=True, reason="CONNECTED_PLANAR_NATIVE_SUPPORT",
                         currentness="UNASSESSED", native_geometry_replaced=False)
        accepted.append((component, native_ids[selected]))
    accepted.sort(key=lambda item: tuple(np.round(item[0]["center"], 8)))
    components = []
    for cid, (component, ids) in enumerate(accepted):
        component["id"] = cid
        membership[ids] = cid
        components.append(component)
    # Boundary search uses representative native coordinates only; final geometry
    # and per-native-row labels remain exact and separately available above.
    rep_labels = membership[native_ids[representative_native]]
    keep = rep_labels >= 0
    nodes, edges = _surface_adjacency(representatives[keep], rep_labels[keep], components,
                                     up, cfg, origin)
    summary.update(assigned_native_count=int((membership >= 0).sum()),
                   unassigned_native_count=int((membership < 0).sum()),
                   component_count=len(components), edge_count=len(edges),
                   normal_supported_voxels=int(planar.sum()), provisional_component_count=len(groups))
    if sum(rejected.values()) != summary["unassigned_native_count"]:
        raise RuntimeError("Unassigned native row accounting is inconsistent")
    graph.update(nodes=nodes, edges=edges, occupancy_origin_xy=origin[:2].tolist())
    return components, membership, graph
