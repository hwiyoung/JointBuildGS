"""Building outlines that split TIN surfaces (prior_propagation_v2, PHD-STAGE2-R8-FOUR-CASES-v1). Offline only (shapely).

Outline sources, in order (method document 3.3, decision 4 of 2026-10-01):
  1. given by the prior or an accompanying data set (this scene: the LoD2 GroundSurface polygons): a triangle's region is
     the outline that contains its centroid (XY); -1 = outside every outline;
  2. no outline given: the prior's own building classification only decides building against non-building
     (building_triangles: most vertices of the triangle carry the building class). Buildings are not separated from each
     other by the classification; the steep triangles (height breaks) split them (surfaces.tin_surfaces(building=...)),
     so roofs that continue in height stay one surface. Non-building triangles carry no surface number;
  3. no classification either: triangle connectivity only (surfaces.tin_surfaces with building None).
The raster clusters of v1 (classification_clusters, region_from_raster, rings_raster, overlap_table) are kept only to
compare with the given outlines (pre-measurement); they are no longer an outline source."""
import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import Polygon


def region_from_rings(xy, rings):
    """label [N] = index of the first ring (list of [x, y]) containing each point, -1 outside all."""
    xy = np.asarray(xy, np.float64)
    lab = np.full(len(xy), -1, np.int64)
    for i, ring in enumerate(rings):
        inside = shapely.contains_xy(Polygon(ring), xy[:, 0], xy[:, 1]) & (lab < 0)
        lab[inside] = i
    return lab


def grid_index(xy, rect, cell):
    i = np.floor((xy[:, 0] - rect[0][0]) / cell).astype(np.int64)
    j = np.floor((xy[:, 1] - rect[0][1]) / cell).astype(np.int64)
    ni = int(np.ceil((rect[1][0] - rect[0][0]) / cell)); nj = int(np.ceil((rect[1][1] - rect[0][1]) / cell))
    return np.clip(i, 0, ni - 1), np.clip(j, 0, nj - 1), ni, nj


def classification_clusters(xy, cls, rect, cell=0.5, building_class=6, min_share=0.5, close_iter=1, min_cells=8):
    """label raster [ni, nj] (0 = no building, 1.. = cluster) from the points' classes, and a record of the parameters."""
    i, j, ni, nj = grid_index(np.asarray(xy, np.float64), rect, cell)
    tot = np.zeros((ni, nj), np.int64); bld = np.zeros((ni, nj), np.int64)
    np.add.at(tot, (i, j), 1); np.add.at(bld, (i, j), (np.asarray(cls) == building_class).astype(np.int64))
    b = (tot > 0) & (bld >= min_share * tot)
    if close_iter:
        b = ndimage.binary_closing(b, structure=np.ones((3, 3), bool), iterations=close_iter)
    lab, n = ndimage.label(b, structure=np.ones((3, 3), bool))
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    keep = np.nonzero(sizes >= min_cells)[0]; keep = keep[keep > 0]
    out = np.zeros_like(lab)
    for k_new, k in enumerate(keep, start=1):
        out[ndimage.binary_fill_holes(lab == k)] = k_new
    rec = dict(cell_m=cell, building_class=building_class, min_share=min_share, close_iter=close_iter, min_cells=min_cells,
               n_clusters=int(len(keep)), n_empty_cells=int((tot == 0).sum()), n_cells=int(ni * nj))
    return out, rec


def region_from_raster(xy, lab, rect, cell):
    """label [N] of the cluster under each point (-1 = none)."""
    i, j, _, _ = grid_index(np.asarray(xy, np.float64), rect, cell)
    v = lab[i, j].astype(np.int64)
    return np.where(v > 0, v - 1, -1)


def rings_raster(rings, rect, cell):
    """label raster of the ring containing each cell centre (-1 none), same grid as classification_clusters."""
    ni = int(np.ceil((rect[1][0] - rect[0][0]) / cell)); nj = int(np.ceil((rect[1][1] - rect[0][1]) / cell))
    cx = rect[0][0] + (np.arange(ni) + 0.5) * cell; cy = rect[0][1] + (np.arange(nj) + 0.5) * cell
    X, Y = np.meshgrid(cx, cy, indexing="ij")
    return region_from_rings(np.stack([X.ravel(), Y.ravel()], 1), rings).reshape(ni, nj)


def overlap_table(ring_lab, cluster_lab, ring_names, cell, cover_min=0.1):
    """per given outline: the cluster that overlaps it most, intersection over union with it, and the clusters that
    cover this and other outlines (merged neighbours: a cluster covering >= cover_min of two or more outlines)."""
    rows = []
    n_ring = int(ring_lab.max()) + 1 if (ring_lab >= 0).any() else 0
    cover = {}
    for r in range(n_ring):
        m = ring_lab == r
        if not m.any():
            continue
        cl = cluster_lab[m]
        ids, cnt = np.unique(cl[cl > 0], return_counts=True)
        for c, k in zip(ids, cnt):
            if k >= cover_min * m.sum():
                cover.setdefault(int(c), []).append(r)
        if ids.size == 0:
            rows.append(dict(outline=ring_names[r], area_m2=float(m.sum() * cell * cell), cluster=None, iou=0.0, merged_with=[]))
            continue
        c = int(ids[np.argmax(cnt)])
        cm = cluster_lab == c
        inter = int((m & cm).sum()); union = int((m | cm).sum())
        rows.append(dict(outline=ring_names[r], area_m2=float(m.sum() * cell * cell), cluster=c, iou=inter / union if union else 0.0,
                         cluster_area_m2=float(cm.sum() * cell * cell), merged_with=[]))
    for row in rows:
        c = row.get("cluster")
        if c is not None and len(cover.get(c, [])) > 1:
            row["merged_with"] = [ring_names[r] for r in cover[c] if ring_names[r] != row["outline"]]
    return rows


def building_triangles(F, cls, building_class=6):
    """second outline source (v2): True for a triangle when at least two of its three vertices carry the building class."""
    return (np.asarray(cls)[np.asarray(F, np.int64)] == building_class).sum(1) >= 2
