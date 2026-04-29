"""
Stage 3 Step 2: Primitive → Surface Groups.

Two implementations:

(A) groups_from_stage2_grouping() — preferred (Track 1, RESEARCH_CONTEXT §15)
    Use Stage 2's voxel-hash group_id (computed by src/stage2/grouping.py).
    Stage 2 trained primitives toward these groups; reusing them in Stage 3
    closes the C2 interface gap (Stage 2's structural intent flows through).

(B) cluster_primitives() — legacy fallback
    Independent hierarchical clustering on normals (cos>0.92) + spatial split.
    Used when ckpt has no group export (legacy) or caller opts in explicitly.
"""

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN


# ============================================================================
# (A) Stage 2 group passthrough  — Track 1 implementation
# ============================================================================


def groups_from_stage2_grouping(centers, normals, areas, labels,
                                group_ids, rep_normals,
                                min_group_size=3):
    """Convert Stage 2's group_id assignment into Stage 3 surface-group dicts.

    Stage 2 plane convention: rep_n · x + rep_d = 0  (group_primitives)
    Stage 3 plane convention: plane_normal · x = plane_d  (downstream)
    plane_d is recomputed here from this building's centroid (sub-voxel
    correction; rep_d was averaged over Stage 2's global voxel population).

    Args:
        centers, normals, areas, labels: per-primitive arrays already
            restricted to one building (caller filters via prim_ids).
        group_ids: (N,) int64 building-local. -1 = ungrouped.
        rep_normals: (G, 3) Stage 2 representative normals (global G).
        min_group_size: drop groups with fewer building-local primitives than
            this. Stage 2's own min_group_size acts globally; restricting to
            one building can shrink a group below it.

    Returns: list of group dicts compatible with downstream Stage 3 code:
        {'plane_normal', 'plane_d', 'class', 'prim_ids', 'center', 'area'}.
    """
    groups_out = []
    valid_gids = np.unique(group_ids[group_ids >= 0])
    for gid in valid_gids:
        mask = group_ids == gid
        if int(mask.sum()) < min_group_size:
            continue
        cls_members = labels[mask]
        cls = int(np.bincount(cls_members).argmax())
        if cls == 0:
            continue

        n = rep_normals[gid].astype(np.float64)
        n /= np.linalg.norm(n) + 1e-12
        cs = centers[mask].astype(np.float64)
        as_ = areas[mask].astype(np.float64)
        w = as_ / (as_.sum() + 1e-12)
        c_mean = (cs * w[:, None]).sum(0)
        plane_d = float(np.dot(n, c_mean))

        groups_out.append({
            'plane_normal': n,
            'plane_d': plane_d,
            'class': cls,
            'prim_ids': np.where(mask)[0].tolist(),
            'center': c_mean.copy(),
            'area': float(as_.sum()),
        })
    return groups_out


# ============================================================================
# (B) Legacy independent clustering  — fallback
# ============================================================================


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


# ============================================================================
# (D) cluster_primitives_v3 — 2-stage DBSCAN (normals → plane_d)
# ============================================================================


# Default normal-DBSCAN eps: Euclidean distance between unit vectors that span
# 5°. ‖n_i − n_j‖ = 2 sin(θ/2). For θ=5°, eps ≈ 0.0872.
_NORMAL_EPS_5DEG = 2.0 * float(np.sin(np.deg2rad(5.0) / 2.0))


def cluster_primitives_v3(centers, normals, areas, labels,
                          normal_eps=_NORMAL_EPS_5DEG,
                          plane_d_eps=0.2,
                          min_samples=10,
                          min_surfaces=4):
    """Surface clustering: class split + 2-stage DBSCAN (normals → plane_d).

    Replaces v2's hard 24-bin normal quantization, which fragments a single
    plane across adjacent bins when normal noise straddles a boundary
    (observed: 71 surfaces on baseline Building 0). Soft DBSCAN on unit
    normals avoids hard boundaries.

    Pipeline:
      1. Split by class (roof=1, wall=2).
      2. Stage-1 normal-DBSCAN on unit normals (Euclidean):
         eps = 2·sin(5°/2) ≈ 0.087, min_samples — primitives whose normals
         lie within ≈5° cluster together. Note: n and -n are distance 2
         apart, so opposite-facing surfaces (east vs west walls, opposing
         roof slopes) become separate clusters. This is correct: they ARE
         different surfaces.
      3. Stage-2 plane_d-DBSCAN per normal cluster:
         a. n_mean = area-weighted mean unit normal (shared axis).
         b. plane_d_i = n_mean · c_i (shared n_mean → noise-free 1-D scalar).
         c. DBSCAN(plane_d, eps=plane_d_eps, min_samples) → surfaces along
            n_mean. Parallel surfaces at different offsets split here.
      4. DBSCAN noise (-1) and tiny clusters → group_id = -1.
      5. Per surface: refit rep_n / rep_off on members.

    G1 σ_coplanar ≈ 2.6 mm so a real plane stays within ~10 mm; parallel
    surfaces differ by metres → eps ∈ [0.1, 0.3] m gives a clean gap.

    Args:
        centers: (N, 3)
        normals: (N, 3)  (will be unit-normalized)
        areas: (N,)
        labels: (N,) int (0=BG, 1=Roof, 2=Wall, 3=Terrain)
        normal_eps: Euclidean DBSCAN eps on unit normals (≈ 2 sin(θ/2)).
        plane_d_eps: DBSCAN eps on plane offset (m).
        min_samples: DBSCAN min_samples (also drops post-DBSCAN tiny clusters).
        min_surfaces: WARN-threshold for surface count (heuristic only).

    Returns:
        group_ids:     (N,)   int64.   -1 = noise / unassigned.
        rep_normals:   (K, 3) float64. Unit-norm.
        rep_offsets:   (K,)   float64. Convention: rep_normals · x = rep_offsets.
        group_classes: (K,)   int64.   Semantic class (1 or 2) per surface.
    """
    centers = np.asarray(centers, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    areas = np.asarray(areas, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    N = len(centers)

    n_unit = normals / (np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12)

    group_ids = -np.ones(N, dtype=np.int64)
    rep_n_list, rep_off_list, cls_list = [], [], []
    next_gid = 0

    for cls in (1, 2):  # roof, wall
        cls_idx = np.where(labels == cls)[0]
        if len(cls_idx) < min_samples:
            continue
        cls_n = n_unit[cls_idx]
        cls_c = centers[cls_idx]
        cls_a = areas[cls_idx]

        # Stage 1: normal-DBSCAN on unit vectors (Euclidean)
        norm_lbl = DBSCAN(eps=normal_eps,
                          min_samples=min_samples).fit_predict(cls_n)

        for nl in np.unique(norm_lbl):
            if nl < 0:
                continue
            nm = norm_lbl == nl
            sub_global = cls_idx[nm]
            sub_n = cls_n[nm]
            sub_c = cls_c[nm]
            sub_a = cls_a[nm]

            # Cluster mean normal (area-weighted; sign already coherent
            # because Stage-1 grouped by Euclidean proximity).
            w = sub_a / (sub_a.sum() + 1e-12)
            n_mean = (sub_n * w[:, None]).sum(0)
            nm_norm = np.linalg.norm(n_mean)
            if nm_norm < 1e-6:
                continue
            n_mean /= nm_norm

            # Stage 2: plane_d-DBSCAN on shared axis
            plane_d = sub_c @ n_mean
            d_lbl = DBSCAN(eps=plane_d_eps,
                           min_samples=min_samples).fit_predict(
                               plane_d.reshape(-1, 1))

            for dl in np.unique(d_lbl):
                if dl < 0:
                    continue
                dm = d_lbl == dl
                if dm.sum() < min_samples:
                    continue

                clu_n = sub_n[dm]
                clu_c = sub_c[dm]
                clu_a = sub_a[dm]
                w2 = clu_a / (clu_a.sum() + 1e-12)

                rep_n = (clu_n * w2[:, None]).sum(0)
                rn = np.linalg.norm(rep_n)
                rep_n = rep_n / rn if rn >= 1e-6 else n_mean
                c_mean = (clu_c * w2[:, None]).sum(0)
                rep_off = float(rep_n @ c_mean)

                group_ids[sub_global[dm]] = next_gid
                rep_n_list.append(rep_n)
                rep_off_list.append(rep_off)
                cls_list.append(cls)
                next_gid += 1

    if rep_n_list:
        rep_normals = np.stack(rep_n_list).astype(np.float64)
        rep_offsets = np.array(rep_off_list, dtype=np.float64)
        group_classes = np.array(cls_list, dtype=np.int64)
    else:
        rep_normals = np.zeros((0, 3), dtype=np.float64)
        rep_offsets = np.zeros((0,), dtype=np.float64)
        group_classes = np.zeros((0,), dtype=np.int64)

    K = len(rep_normals)
    if K < min_surfaces:
        print(f"[cluster_primitives_v3] WARN: only {K} surfaces "
              f"(< min_surfaces={min_surfaces}); clustering may have failed")

    return group_ids, rep_normals, rep_offsets, group_classes


# ============================================================================
# (E1) cluster_primitives_v4_dbscan — earlier attempt: azimuth-DBSCAN + 3D-DBSCAN
# Kept for comparison; superseded by (E2) mode-based v4 because azimuth-DBSCAN
# still density-chains on the equator when L_mutual works (Mutual B0: Wall=2,
# max_wall=89.8% — see RESEARCH_CONTEXT or cluster_primitives_v4 docstring).
# ============================================================================


# 10° angular tolerance, expressed as chord length on the unit circle:
# ‖(cos α, sin α) − (cos β, sin β)‖ = 2 sin(|α−β|/2). For 10° → chord ≈ 0.1743.
_AZIMUTH_EPS_10DEG = 2.0 * float(np.sin(np.deg2rad(5.0)))


def _emit_surfaces_from_normal_cluster(
        sub_global, sub_n, sub_c, sub_a, n_mean,
        plane_d_eps, min_samples,
        cls, next_gid, group_ids,
        rep_n_list, rep_off_list, cls_list):
    """Stage-2 split: run plane_d-DBSCAN within one normal cluster, emit one
    Stage-3 surface per resulting plane_d cluster. Mutates group_ids,
    rep_*/cls_* lists. Returns updated next_gid."""
    plane_d = sub_c @ n_mean
    d_lbl = DBSCAN(eps=plane_d_eps, min_samples=min_samples).fit_predict(
        plane_d.reshape(-1, 1))
    for dl in np.unique(d_lbl):
        if dl < 0:
            continue
        dm = d_lbl == dl
        if dm.sum() < min_samples:
            continue
        clu_n = sub_n[dm]
        clu_c = sub_c[dm]
        clu_a = sub_a[dm]
        w2 = clu_a / (clu_a.sum() + 1e-12)
        rep_n = (clu_n * w2[:, None]).sum(0)
        rn = np.linalg.norm(rep_n)
        rep_n = rep_n / rn if rn >= 1e-6 else n_mean
        c_mean = (clu_c * w2[:, None]).sum(0)
        rep_off = float(rep_n @ c_mean)
        group_ids[sub_global[dm]] = next_gid
        rep_n_list.append(rep_n)
        rep_off_list.append(rep_off)
        cls_list.append(cls)
        next_gid += 1
    return next_gid


def cluster_primitives_v4_dbscan(centers, normals, areas, labels,
                          gravity=(0.0, 1.0, 0.0),
                          wall_vert_thresh=0.15,
                          azimuth_eps=_AZIMUTH_EPS_10DEG,
                          normal_eps=_NORMAL_EPS_5DEG,
                          plane_d_eps=0.2,
                          min_samples=10,
                          min_surfaces=4):
    """Surface clustering (class-aware): vertical walls via azimuth-1D DBSCAN,
    roofs via 3D normal-DBSCAN.

    Fixes v3's "equator chaining": when L_mutual works (~88% wall vert frac),
    wall normals concentrate on the great-circle perpendicular to gravity.
    3D Euclidean DBSCAN with eps≈5° density-chains the entire equator into
    one cluster, fusing all wall directions. v4 sidesteps this by reducing
    wall normals to a single periodic angle (azimuth) and clustering 1-D.

    Pipeline:
      Walls (label==2 AND |n·gravity| < wall_vert_thresh):
        1. Project to azimuth θ = atan2(n_b, n_a) over the two axes
           orthogonal to gravity (auto-selected: gravity-Y → axes X,Z; etc.).
        2. Embed θ → (cos θ, sin θ) so periodic-1D becomes Euclidean-2D
           (avoids precomputed distance matrix).
        3. DBSCAN(embed, eps=azimuth_eps, min_samples). eps=2 sin(5°)≈0.174
           ≈ 10° angular tolerance.
        4. Per azimuth cluster: plane_d-DBSCAN as in v3.

      Roofs (label==1):
        Same as v3 — 3D DBSCAN on unit normals, then plane_d-DBSCAN.

      Non-vertical walls (label==2 AND |n·gravity| >= wall_vert_thresh):
        Dropped (group_id = -1). Per spec, these are noise/spurious in a
        well-trained model; if needed they could be routed through the
        roof path.

    Returns:
        group_ids:     (N,)   int64.   -1 = noise/unassigned.
        rep_normals:   (K, 3) float64. Unit-norm.
        rep_offsets:   (K,)   float64. rep_normals · x = rep_offsets.
        group_classes: (K,)   int64.   1=Roof, 2=Wall.
    """
    centers = np.asarray(centers, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    areas = np.asarray(areas, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    gravity = np.asarray(gravity, dtype=np.float64)
    gravity = gravity / (np.linalg.norm(gravity) + 1e-12)
    N = len(centers)

    n_unit = normals / (np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12)

    # Pick the two axes orthogonal to the dominant gravity component for
    # azimuth projection. Y-dominant (default) → axes (X=0, Z=2).
    g_abs = np.abs(gravity)
    g_dom = int(np.argmax(g_abs))
    horiz_axes = tuple(i for i in (0, 1, 2) if i != g_dom)
    ax_a, ax_b = horiz_axes  # θ = atan2(n[ax_b], n[ax_a])

    group_ids = -np.ones(N, dtype=np.int64)
    rep_n_list, rep_off_list, cls_list = [], [], []
    next_gid = 0

    # === Wall path: vertical walls only, azimuth-1D DBSCAN ===
    wall_global = np.where(labels == 2)[0]
    if len(wall_global) >= min_samples:
        n_dot_g = np.abs(n_unit[wall_global] @ gravity)
        vert_local = n_dot_g < wall_vert_thresh
        vert_global = wall_global[vert_local]
        if len(vert_global) >= min_samples:
            w_n = n_unit[vert_global]
            w_c = centers[vert_global]
            w_a = areas[vert_global]
            theta = np.arctan2(w_n[:, ax_b], w_n[:, ax_a])
            embed = np.stack([np.cos(theta), np.sin(theta)], axis=1)
            az_lbl = DBSCAN(eps=azimuth_eps,
                            min_samples=min_samples).fit_predict(embed)
            for al in np.unique(az_lbl):
                if al < 0:
                    continue
                am = az_lbl == al
                grp_global = vert_global[am]
                grp_n = w_n[am]
                grp_c = w_c[am]
                grp_a = w_a[am]
                w = grp_a / (grp_a.sum() + 1e-12)
                n_mean = (grp_n * w[:, None]).sum(0)
                nm_norm = np.linalg.norm(n_mean)
                if nm_norm < 1e-6:
                    continue
                n_mean /= nm_norm
                next_gid = _emit_surfaces_from_normal_cluster(
                    grp_global, grp_n, grp_c, grp_a, n_mean,
                    plane_d_eps, min_samples, cls=2,
                    next_gid=next_gid, group_ids=group_ids,
                    rep_n_list=rep_n_list, rep_off_list=rep_off_list,
                    cls_list=cls_list)

    # === Roof path: 3D DBSCAN on unit normals (v3 pipeline) ===
    roof_global = np.where(labels == 1)[0]
    if len(roof_global) >= min_samples:
        r_n = n_unit[roof_global]
        r_c = centers[roof_global]
        r_a = areas[roof_global]
        norm_lbl = DBSCAN(eps=normal_eps,
                          min_samples=min_samples).fit_predict(r_n)
        for nl in np.unique(norm_lbl):
            if nl < 0:
                continue
            nm = norm_lbl == nl
            grp_global = roof_global[nm]
            grp_n = r_n[nm]
            grp_c = r_c[nm]
            grp_a = r_a[nm]
            w = grp_a / (grp_a.sum() + 1e-12)
            n_mean = (grp_n * w[:, None]).sum(0)
            nm_norm = np.linalg.norm(n_mean)
            if nm_norm < 1e-6:
                continue
            n_mean /= nm_norm
            next_gid = _emit_surfaces_from_normal_cluster(
                grp_global, grp_n, grp_c, grp_a, n_mean,
                plane_d_eps, min_samples, cls=1,
                next_gid=next_gid, group_ids=group_ids,
                rep_n_list=rep_n_list, rep_off_list=rep_off_list,
                cls_list=cls_list)

    if rep_n_list:
        rep_normals = np.stack(rep_n_list).astype(np.float64)
        rep_offsets = np.array(rep_off_list, dtype=np.float64)
        group_classes = np.array(cls_list, dtype=np.int64)
    else:
        rep_normals = np.zeros((0, 3), dtype=np.float64)
        rep_offsets = np.zeros((0,), dtype=np.float64)
        group_classes = np.zeros((0,), dtype=np.int64)

    K = len(rep_normals)
    if K < min_surfaces:
        print(f"[cluster_primitives_v4_dbscan] WARN: only {K} surfaces "
              f"(< min_surfaces={min_surfaces}); clustering may have failed")

    return group_ids, rep_normals, rep_offsets, group_classes


# ============================================================================
# (E2) cluster_primitives_v4 — mode-based: histogram peak finding on azimuth
# ============================================================================
#
# The DBSCAN family fails on Mutual's wall normals because well-trained walls
# pack the equator (great-circle perpendicular to gravity) without genuine
# valleys: any density-chain method connects everything. eps sweeps (3°→10°)
# couldn't break the chain — there's only one valley on a circle, which is
# not enough to disconnect a topological loop. Mode-based methods (find local
# maxima in the angular histogram) sidestep the topology and recover the 4–5
# discrete wall directions that actually exist.


def _circular_peaks(hist_smooth, prominence_frac, min_distance_bins):
    """Return peak bin indices in a periodic 1-D histogram via 3× replication."""
    n = len(hist_smooth)
    rep = np.concatenate([hist_smooth, hist_smooth, hist_smooth])
    prom = max(prominence_frac * float(hist_smooth.max()), 1e-12)
    peaks_rep, _ = find_peaks(rep, distance=max(1, int(min_distance_bins)),
                              prominence=prom)
    peaks = sorted({int(p - n) for p in peaks_rep if n <= p < 2 * n})
    return np.array(peaks, dtype=np.int64)


def _linear_peaks(hist_smooth, prominence_frac, min_distance_bins):
    """Peak bin indices in a non-periodic 1-D histogram."""
    prom = max(prominence_frac * float(hist_smooth.max()), 1e-12)
    peaks, _ = find_peaks(hist_smooth, distance=max(1, int(min_distance_bins)),
                          prominence=prom)
    return peaks.astype(np.int64)


def _circ_dist_deg(a, b, wrap=360.0):
    d = np.abs(a - b)
    return np.minimum(d, wrap - d)


def _spatial_components_3d(points, threshold):
    """Connected components: vertices linked iff Euclidean distance ≤ threshold.

    Returns (M,) component-id (0..C-1)."""
    M = len(points)
    if M <= 1:
        return np.zeros(M, dtype=np.int64)
    tree = cKDTree(points)
    pairs = tree.query_pairs(threshold, output_type='ndarray')
    parent = list(range(M))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    if len(pairs) > 0:
        for a, b in pairs:
            ra, rb = find(int(a)), find(int(b))
            if ra != rb:
                parent[rb] = ra
    out = np.empty(M, dtype=np.int64)
    root2id = {}
    for i in range(M):
        r = find(i)
        if r not in root2id:
            root2id[r] = len(root2id)
        out[i] = root2id[r]
    return out


def cluster_primitives_v4(centers, normals, areas, labels,
                          gravity=(0.0, 1.0, 0.0),
                          opacities=None,
                          wall_vert_thresh=0.15,
                          # azimuth peak detection
                          az_bin_deg=3.0,
                          az_smooth_sigma_bins=2.0,
                          az_peak_prominence_frac=0.10,
                          az_peak_min_distance_deg=20.0,
                          az_assign_max_dist_deg=25.0,
                          az_signflip_corr_thresh=0.7,
                          # plane_d peak detection
                          plane_d_bin=0.1,
                          plane_d_smooth_sigma_bins=2.0,
                          plane_d_peak_prominence_frac=0.10,
                          plane_d_peak_min_distance=0.4,
                          plane_d_assign_max_dist=0.5,
                          # spatial connected component split.
                          # Empirical: 0.5 m (the spec's nominal value)
                          # over-fragments because 2DGS primitive centres can
                          # sit > 0.5 m apart on a single wall when scales are
                          # coarse. component_dist sweep on Mutual B0:
                          #   0.5 → 87 walls,  1.0 → 13,  2.0 → 9,  ∞ → 9.
                          # 2.0 m essentially recovers the no-CC result and
                          # still splits genuinely disjoint co-planar walls
                          # (different buildings) in practice.
                          component_dist=2.0,
                          # roof / non-vertical wall (3D DBSCAN, v3-style)
                          normal_eps=_NORMAL_EPS_5DEG,
                          plane_d_eps_3d=0.2,
                          min_samples=10,
                          min_surfaces=4):
    """Surface clustering — mode-based for vertical walls, v3-3D for the rest.

    Pipeline:
      WALLS (vertical only, |n·gravity| < wall_vert_thresh):
        1. Azimuth θ = atan2(n_b, n_a) over the two axes ⊥ gravity.
        2. Area×opacity-weighted circular histogram (az_bin_deg bins).
        3. Gaussian smoothing (σ = az_smooth_sigma_bins bins, mode='wrap').
        4. Sign-flip detection: if corr(hist, hist shifted by 180°) >
           az_signflip_corr_thresh, fold to [0,180°) — handles within-wall
           normal sign inconsistencies.
        5. Local maxima with prominence ≥ az_peak_prominence_frac · max(hist)
           and bin-distance ≥ az_peak_min_distance_deg / az_bin_deg.
        6. Each primitive → nearest peak (cap az_assign_max_dist_deg, else -1).
        7. For each azimuth cluster:
             a. n_peak = area-weighted mean (sign-aligned to majority if folded).
             b. d_i = n_peak · c_i.
             c. Mode-based plane_d split (linear histogram + peaks). Each
                primitive → nearest plane_d peak (cap plane_d_assign_max_dist).
             d. Spatial connected component on member centers (cKDTree pairs
                within component_dist); each component = one Stage-3 surface.

      NON-VERTICAL WALLS (label==2 AND |n·g| ≥ wall_vert_thresh):
        Routed through the roof path (3D DBSCAN on unit normals).

      ROOFS (label==1) and the non-vertical walls above:
        v3 pipeline — DBSCAN(unit normals, eps=_NORMAL_EPS_5DEG) →
        DBSCAN(plane_d, eps=plane_d_eps_3d).

    Returns:
        group_ids:     (N,)   int64.   -1 = noise/unassigned.
        rep_normals:   (K, 3) float64. Unit-norm.
        rep_offsets:   (K,)   float64. rep_normals · x = rep_offsets.
        group_classes: (K,)   int64.   1=Roof, 2=Wall.
    """
    centers = np.asarray(centers, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    areas = np.asarray(areas, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    gravity = np.asarray(gravity, dtype=np.float64)
    gravity = gravity / (np.linalg.norm(gravity) + 1e-12)
    if opacities is None:
        opacities = np.ones(len(centers), dtype=np.float64)
    else:
        opacities = np.asarray(opacities, dtype=np.float64)
    N = len(centers)

    n_unit = normals / (np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12)

    g_abs = np.abs(gravity)
    g_dom = int(np.argmax(g_abs))
    horiz_axes = tuple(i for i in (0, 1, 2) if i != g_dom)
    ax_a, ax_b = horiz_axes  # θ = atan2(n[ax_b], n[ax_a])

    group_ids = -np.ones(N, dtype=np.int64)
    rep_n_list, rep_off_list, cls_list = [], [], []
    next_gid = 0

    # ------------------------------------------------------------------ walls
    wall_global = np.where(labels == 2)[0]
    n_dot_g_wall = np.abs(n_unit[wall_global] @ gravity) if len(wall_global) else np.array([])
    vert_global = wall_global[n_dot_g_wall < wall_vert_thresh]
    nonvert_global = wall_global[n_dot_g_wall >= wall_vert_thresh]

    if len(vert_global) >= min_samples:
        v_n = n_unit[vert_global]
        v_c = centers[vert_global]
        v_a = areas[vert_global]
        v_w = v_a * opacities[vert_global]

        theta_deg = np.degrees(np.arctan2(v_n[:, ax_b], v_n[:, ax_a]))  # (-180,180]

        # 360° histogram in [0, 360)
        n_bins_full = max(2, int(round(360.0 / az_bin_deg)))
        bin_full = (((theta_deg + 180.0) / az_bin_deg).astype(np.int64)
                    % n_bins_full)
        hist_full = np.zeros(n_bins_full)
        np.add.at(hist_full, bin_full, v_w)
        hist_full_s = gaussian_filter1d(hist_full, az_smooth_sigma_bins,
                                        mode='wrap')

        # Sign-flip detection: walls have nearly identical mass 180° apart?
        half = n_bins_full // 2
        rolled = np.roll(hist_full_s, half)
        # Pearson corr is well-defined when both have non-zero variance
        var_ok = hist_full_s.std() > 1e-9 and rolled.std() > 1e-9
        corr = (float(np.corrcoef(hist_full_s, rolled)[0, 1])
                if var_ok else 0.0)
        sign_flip = corr > az_signflip_corr_thresh

        if sign_flip:
            hist_for_peaks = hist_full_s[:half] + hist_full_s[half:]
            bin_count = half
            wrap_deg = 180.0
            # bin center θ for [0, 180); fold theta_deg into [0, 180)
            theta_for_assign = theta_deg % 180.0
            offset_deg = 0.0  # peak center = (idx+0.5)*az_bin_deg + 0
        else:
            hist_for_peaks = hist_full_s
            bin_count = n_bins_full
            wrap_deg = 360.0
            # bin centers in [-180, 180): peak center = (idx+0.5)*bin_deg + offset
            theta_for_assign = theta_deg
            offset_deg = -180.0

        peak_bins = _circular_peaks(
            hist_for_peaks,
            prominence_frac=az_peak_prominence_frac,
            min_distance_bins=az_peak_min_distance_deg / az_bin_deg)

        if len(peak_bins):
            peak_centers = (peak_bins.astype(np.float64) + 0.5) * az_bin_deg \
                           + offset_deg
            # Assign each primitive to nearest peak (circular)
            d_mat = _circ_dist_deg(theta_for_assign[:, None],
                                   peak_centers[None, :], wrap=wrap_deg)
            nearest = np.argmin(d_mat, axis=1)
            min_d = d_mat[np.arange(len(theta_for_assign)), nearest]
            peak_assign = np.where(min_d <= az_assign_max_dist_deg,
                                   nearest, -1).astype(np.int64)

            # Within each azimuth peak group: plane_d peaks → spatial CC
            for pk in range(len(peak_bins)):
                mask_pk = peak_assign == pk
                if mask_pk.sum() < min_samples:
                    continue
                pk_global = vert_global[mask_pk]
                pk_n = v_n[mask_pk]
                pk_c = v_c[mask_pk]
                pk_a = v_a[mask_pk]
                pk_w = v_w[mask_pk]

                # Sign-align (only meaningful when folded, but harmless otherwise)
                ref_n = pk_n[np.argmax(pk_a)]
                sign = np.where(pk_n @ ref_n >= 0.0, 1.0, -1.0)
                pk_n_aligned = pk_n * sign[:, None]
                w_norm = pk_a / (pk_a.sum() + 1e-12)
                n_peak = (pk_n_aligned * w_norm[:, None]).sum(0)
                nm = np.linalg.norm(n_peak)
                if nm < 1e-6:
                    continue
                n_peak /= nm

                # plane_d peak detection
                d_i = pk_c @ n_peak
                d_min, d_max = float(d_i.min()), float(d_i.max())
                if d_max - d_min < plane_d_bin:
                    # near-degenerate; one plane
                    d_peak_assign = np.zeros(len(d_i), dtype=np.int64)
                    d_peaks_centers = np.array([0.5 * (d_min + d_max)])
                else:
                    margin = max(plane_d_bin, plane_d_peak_min_distance)
                    lo = d_min - margin
                    hi = d_max + margin
                    n_d_bins = max(8, int(np.ceil((hi - lo) / plane_d_bin)))
                    edges = np.linspace(lo, hi, n_d_bins + 1)
                    d_bin = np.minimum(((d_i - lo) / plane_d_bin).astype(np.int64),
                                       n_d_bins - 1)
                    hist_d = np.zeros(n_d_bins)
                    np.add.at(hist_d, d_bin, pk_w)
                    hist_d_s = gaussian_filter1d(hist_d,
                                                 plane_d_smooth_sigma_bins,
                                                 mode='nearest')
                    d_peak_idx = _linear_peaks(
                        hist_d_s,
                        prominence_frac=plane_d_peak_prominence_frac,
                        min_distance_bins=plane_d_peak_min_distance / plane_d_bin)
                    if len(d_peak_idx) == 0:
                        # fall back: single plane at weighted mean
                        d_peaks_centers = np.array([(d_i * pk_w).sum()
                                                    / (pk_w.sum() + 1e-12)])
                    else:
                        d_peaks_centers = (d_peak_idx + 0.5) * plane_d_bin + lo

                    # Assign to nearest plane_d peak
                    d_dist = np.abs(d_i[:, None] - d_peaks_centers[None, :])
                    d_nearest = np.argmin(d_dist, axis=1)
                    d_min_d = d_dist[np.arange(len(d_i)), d_nearest]
                    d_peak_assign = np.where(d_min_d <= plane_d_assign_max_dist,
                                             d_nearest, -1).astype(np.int64)

                # Per plane_d peak: spatial connected components → emit surfaces
                for dpk in range(len(d_peaks_centers)):
                    mask_d = d_peak_assign == dpk
                    if mask_d.sum() < min_samples:
                        continue
                    sub_global = pk_global[mask_d]
                    sub_n_a = pk_n_aligned[mask_d]
                    sub_c_arr = pk_c[mask_d]
                    sub_a_arr = pk_a[mask_d]

                    comp = _spatial_components_3d(sub_c_arr, component_dist)
                    for ci in np.unique(comp):
                        cm = comp == ci
                        if cm.sum() < min_samples:
                            continue
                        clu_n = sub_n_a[cm]
                        clu_c = sub_c_arr[cm]
                        clu_a = sub_a_arr[cm]
                        w2 = clu_a / (clu_a.sum() + 1e-12)
                        rep_n = (clu_n * w2[:, None]).sum(0)
                        rn = np.linalg.norm(rep_n)
                        rep_n = rep_n / rn if rn >= 1e-6 else n_peak
                        c_mean = (clu_c * w2[:, None]).sum(0)
                        rep_off = float(rep_n @ c_mean)
                        group_ids[sub_global[cm]] = next_gid
                        rep_n_list.append(rep_n)
                        rep_off_list.append(rep_off)
                        cls_list.append(2)
                        next_gid += 1

    # --------------------------- non-vertical walls + roofs through 3D-DBSCAN
    fallback_groups = [
        (1, np.where(labels == 1)[0]),
        (2, nonvert_global),
    ]
    for cls, idx_global in fallback_groups:
        if len(idx_global) < min_samples:
            continue
        sub_n = n_unit[idx_global]
        sub_c = centers[idx_global]
        sub_a = areas[idx_global]
        norm_lbl = DBSCAN(eps=normal_eps,
                          min_samples=min_samples).fit_predict(sub_n)
        for nl in np.unique(norm_lbl):
            if nl < 0:
                continue
            nm = norm_lbl == nl
            grp_global = idx_global[nm]
            grp_n = sub_n[nm]
            grp_c = sub_c[nm]
            grp_a = sub_a[nm]
            w = grp_a / (grp_a.sum() + 1e-12)
            n_mean = (grp_n * w[:, None]).sum(0)
            nm_norm = np.linalg.norm(n_mean)
            if nm_norm < 1e-6:
                continue
            n_mean /= nm_norm
            next_gid = _emit_surfaces_from_normal_cluster(
                grp_global, grp_n, grp_c, grp_a, n_mean,
                plane_d_eps_3d, min_samples, cls=cls,
                next_gid=next_gid, group_ids=group_ids,
                rep_n_list=rep_n_list, rep_off_list=rep_off_list,
                cls_list=cls_list)

    if rep_n_list:
        rep_normals = np.stack(rep_n_list).astype(np.float64)
        rep_offsets = np.array(rep_off_list, dtype=np.float64)
        group_classes = np.array(cls_list, dtype=np.int64)
    else:
        rep_normals = np.zeros((0, 3), dtype=np.float64)
        rep_offsets = np.zeros((0,), dtype=np.float64)
        group_classes = np.zeros((0,), dtype=np.int64)

    K = len(rep_normals)
    if K < min_surfaces:
        print(f"[cluster_primitives_v4] WARN: only {K} surfaces "
              f"(< min_surfaces={min_surfaces}); clustering may have failed")

    return group_ids, rep_normals, rep_offsets, group_classes


# ============================================================================
# Legacy helpers (used by cluster_primitives only)
# ============================================================================


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
