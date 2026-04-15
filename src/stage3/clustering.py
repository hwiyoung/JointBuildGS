"""
Step 1: Primitive Clustering → Surface Groups

Cluster primitives within same semantic class by normal similarity.
Two-pass approach: strict clustering + merge tiny clusters.
"""

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage


def cluster_primitives(centers, normals, areas, labels, cos_thresh=0.85,
                       min_cluster_fraction=0.05):
    """
    Cluster primitives within same semantic class by normal similarity.
    Same wall/roof plane → same surface group, regardless of spatial distance.

    Two-pass approach:
      1. Strict clustering (cos_thresh=0.92) to separate shallow slopes
      2. Merge tiny clusters (< min_cluster_fraction of class total) into
         nearest large cluster — prevents noise-induced over-segmentation
    """
    groups = []
    for cls in [1, 2]:  # roof=1, wall=2
        cls_mask = labels == cls
        cls_ids = np.where(cls_mask)[0]
        if len(cls_ids) == 0:
            continue

        cls_normals = normals[cls_ids]
        cls_centers = centers[cls_ids]
        cls_areas = areas[cls_ids]

        if len(cls_ids) == 1:
            n = cls_normals[0] / (np.linalg.norm(cls_normals[0]) + 1e-12)
            groups.append({
                'plane_normal': n,
                'plane_d': float(np.dot(n, cls_centers[0])),
                'class': cls,
                'prim_ids': cls_ids.tolist(),
                'center': cls_centers[0].copy(),
                'area': float(cls_areas[0]),
            })
            continue

        # Pass 1: strict clustering
        strict_thresh = max(cos_thresh, 0.92)
        n_hat = cls_normals / (np.linalg.norm(cls_normals, axis=1, keepdims=True) + 1e-12)
        cos_sim = np.clip(n_hat @ n_hat.T, -1, 1)
        condensed = (1.0 - cos_sim)[np.triu_indices(len(cls_ids), k=1)]

        Z = linkage(condensed, method='average')
        cluster_ids = fcluster(Z, t=1.0 - strict_thresh, criterion='distance')

        # Pass 1.5: split clusters with spatially disjoint planes
        cluster_ids = _spatial_split(cluster_ids, cls_centers, cls_normals)

        # Pass 2: merge tiny clusters into nearest large cluster
        cluster_ids = _merge_tiny_clusters(
            cluster_ids, cls_normals, cls_areas, min_cluster_fraction)

        # Pass 3: build surface groups with trimmed weighted mean
        for cid in np.unique(cluster_ids):
            cmask = cluster_ids == cid
            pids = cls_ids[cmask]
            cn = cls_normals[cmask]
            cc = cls_centers[cmask]
            ca = cls_areas[cmask]

            n_hat_c = cn / (np.linalg.norm(cn, axis=1, keepdims=True) + 1e-12)
            w = ca / (ca.sum() + 1e-12)
            init_n = (n_hat_c * w[:, None]).sum(0)
            init_n /= np.linalg.norm(init_n) + 1e-12

            cos_sims = n_hat_c @ init_n
            trim_mask = cos_sims > 0.866  # cos(30°)

            if trim_mask.sum() >= 3:
                w_in = ca[trim_mask] / (ca[trim_mask].sum() + 1e-12)
                mean_n = (cn[trim_mask] * w_in[:, None]).sum(0)
                mean_n /= np.linalg.norm(mean_n) + 1e-12
                mean_c = (cc[trim_mask] * w_in[:, None]).sum(0)
            else:
                mean_n = init_n
                mean_c = (cc * w[:, None]).sum(0)

            groups.append({
                'plane_normal': mean_n,
                'plane_d': float(np.dot(mean_n, mean_c)),
                'class': cls,
                'prim_ids': pids.tolist(),
                'center': mean_c.copy(),
                'area': float(ca.sum()),
            })
    return groups


def _try_gap_split(values, min_gap=1.0, adaptive=False):
    """Find split point by largest gap. Returns bool mask or None."""
    sorted_v = np.sort(values)
    gaps = np.diff(sorted_v)
    if len(gaps) == 0:
        return None
    gi = np.argmax(gaps)
    if adaptive:
        n = len(values)
        vrange = sorted_v[-1] - sorted_v[0]
        if vrange < 1e-6 or n < 4:
            return None
        expected_max = vrange * np.log(n) / n
        threshold = max(min_gap, 3.0 * expected_max)
    else:
        threshold = min_gap
    if gaps[gi] < threshold:
        return None
    split_val = (sorted_v[gi] + sorted_v[gi + 1]) / 2
    hi_mask = values > split_val
    if hi_mask.sum() < 2 or (~hi_mask).sum() < 2:
        return None
    return hi_mask


def _spatial_split(cluster_ids, cls_centers, cls_normals):
    """Split clusters containing spatially disjoint planes."""
    changed = True
    next_cid = cluster_ids.max() + 1
    while changed:
        changed = False
        new_ids = cluster_ids.copy()
        for cid in np.unique(cluster_ids):
            cmask = cluster_ids == cid
            if cmask.sum() < 4:
                continue
            cc = cls_centers[cmask]
            cn = cls_normals[cmask]
            local_idx = np.where(cmask)[0]

            w_n = cn.mean(0)
            w_n /= np.linalg.norm(w_n) + 1e-12

            # (a) plane_d gap
            plane_ds = cc @ w_n
            split = _try_gap_split(plane_ds)
            if split is not None:
                new_ids[local_idx[split]] = next_cid
                next_cid += 1
                changed = True
                continue

            # (b) tangent-direction gap
            proj = cc - np.outer(cc @ w_n, w_n)
            for axis in range(3):
                if abs(w_n[axis]) > 0.7:
                    continue
                split = _try_gap_split(proj[:, axis], adaptive=True)
                if split is not None:
                    new_ids[local_idx[split]] = next_cid
                    next_cid += 1
                    changed = True
                    break
        cluster_ids = new_ids
    return cluster_ids


def _merge_tiny_clusters(cluster_ids, cls_normals, cls_areas,
                         min_cluster_fraction):
    """Merge tiny clusters into nearest large cluster."""
    min_size = max(2, int(len(cls_normals) * min_cluster_fraction))
    unique_cids = np.unique(cluster_ids)
    large_cids = [c for c in unique_cids if (cluster_ids == c).sum() >= min_size]
    small_cids = [c for c in unique_cids if (cluster_ids == c).sum() < min_size]

    if large_cids and small_cids:
        large_normals = {}
        for c in large_cids:
            cm = cluster_ids == c
            ca = cls_areas[cm]
            cn = cls_normals[cm]
            w = ca / (ca.sum() + 1e-12)
            mn = (cn * w[:, None]).sum(0)
            mn /= np.linalg.norm(mn) + 1e-12
            large_normals[c] = mn

        for sc in small_cids:
            sm = cluster_ids == sc
            s_normals = cls_normals[sm]
            s_areas = cls_areas[sm]
            sw = s_areas / (s_areas.sum() + 1e-12)
            s_mean = (s_normals * sw[:, None]).sum(0)
            s_mean /= np.linalg.norm(s_mean) + 1e-12

            best_c, best_sim = large_cids[0], -2.0
            for lc, ln in large_normals.items():
                sim = float(np.dot(s_mean, ln))
                if sim > best_sim:
                    best_sim = sim
                    best_c = lc
            cluster_ids[sm] = best_c

    return cluster_ids
