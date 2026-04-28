"""Group primitives for Mechanism 2 (L_structure).

Two grouping definitions (RESEARCH_CONTEXT §15):

G1 — group_primitives() — patch-level (legacy)
  hash(class, voxel_5cm, dir_bin_12). ~154 groups/building. Fast but
  patch-level, not the surface-level groups the thesis assumes. L_normal_align
  reduces to intra-patch smoothing on G1 (see §16 C3b).

G2 — group_primitives_g2() — surface-level (current target)
  Two-stage: (1) coarse hash (class, voxel_2m, dir_bin_12) yields cells whose
  per-cell rep_n averages out primitive normal noise; (2) cell-level union-find
  merges voxel-adjacent cells that agree in (rep_n, rep_d). One connected
  component = one surface group. ~7 groups/building, matches Stage 3 surface
  unit, restores cycle semantics (f_i → reassignment).

Both share the return signature (group_ids, rep_n, rep_d) so downstream
(loss/structure.py, stage3/clustering.groups_from_stage2_grouping) is unchanged.

Plane convention: n_k · x + d_k = 0 (so d_k = −n_k · c̄_k).
"""
from __future__ import annotations

from typing import Tuple

import torch
import torch.nn.functional as F


# 12 direction basis (half-sphere upper; we'll use |dot| so it's symmetric)
def _fibonacci_directions(n: int = 12, device="cpu") -> torch.Tensor:
    """n evenly distributed unit vectors on sphere (Fibonacci lattice)."""
    indices = torch.arange(n, dtype=torch.float32, device=device) + 0.5
    phi = torch.acos(1 - 2 * indices / n)
    theta = torch.pi * (1 + 5 ** 0.5) * indices
    x = torch.sin(phi) * torch.cos(theta)
    y = torch.sin(phi) * torch.sin(theta)
    z = torch.cos(phi)
    return F.normalize(torch.stack([x, y, z], dim=-1), dim=-1)


def group_primitives(
    centers: torch.Tensor,        # (N, 3)
    normals: torch.Tensor,        # (N, 3) unit
    sem_logits: torch.Tensor,     # (N, K)
    scales: torch.Tensor,         # (N, 3) (not log)
    voxel_size: float = 0.05,
    n_directions: int = 12,
    min_group_size: int = 5,
    exclude_bg: bool = True,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Assign group id per primitive.

    Returns:
        group_ids: (N,) int64, -1 = ungrouped (BG or singleton)
        rep_normals: (G, 3)   representative normals per valid group (G = num groups)
        rep_d: (G,)           plane offsets so that n_k · x + d_k = 0 on plane
    """
    device = centers.device
    N = centers.shape[0]
    with torch.no_grad():
        cls = sem_logits.argmax(dim=-1)           # (N,) in [0..K-1]

        # voxel_3d = floor(c / voxel_size)
        vox = torch.floor(centers / voxel_size).to(torch.int64)  # (N, 3)

        # normal direction bin: argmax |n · b_j|
        basis = _fibonacci_directions(n_directions, device=device)  # (D, 3)
        cos_ib = (normals @ basis.T).abs()                           # (N, D)
        dir_bin = cos_ib.argmax(dim=-1)                              # (N,)

        # Exclude BG (class 0): assign -1 group id
        valid = (cls != 0) if exclude_bg else torch.ones(N, dtype=torch.bool, device=device)

        # Hash: (class, vox_x, vox_y, vox_z, dir) → int64 unique id
        # Use large primes to reduce collision; or just use torch.unique with concatenated key.
        key = torch.stack([
            cls.to(torch.int64),
            vox[:, 0], vox[:, 1], vox[:, 2],
            dir_bin.to(torch.int64),
        ], dim=-1)                                                   # (N, 5)
        # Only valid entries go to unique
        key_valid = key[valid]
        # torch.unique with return_inverse
        uniq, inv = torch.unique(key_valid, return_inverse=True, dim=0)
        G_raw = uniq.shape[0]

        # group_ids for all primitives: init -1, then fill valid with inv
        raw_ids = torch.full((N,), -1, dtype=torch.int64, device=device)
        raw_ids[valid] = inv                                         # 0..G_raw-1

        # Filter groups by min size
        counts = torch.bincount(inv, minlength=G_raw)                # (G_raw,)
        keep = counts >= min_group_size                              # (G_raw,)
        # Remap: kept groups get new 0..G-1; rest get -1.
        remap = torch.full((G_raw,), -1, dtype=torch.int64, device=device)
        kept_idx = torch.nonzero(keep, as_tuple=False).squeeze(-1)
        remap[kept_idx] = torch.arange(kept_idx.numel(), device=device)
        group_ids = torch.full((N,), -1, dtype=torch.int64, device=device)
        valid2 = raw_ids >= 0
        group_ids[valid2] = remap[raw_ids[valid2]]
        group_ids[group_ids < 0] = -1

        # Compute rep_normals and rep_d per kept group
        G = kept_idx.numel()
        if G == 0:
            return group_ids, torch.zeros((0, 3), device=device), torch.zeros((0,), device=device)

        # Weights: max in-plane scale
        w = scales[:, :2].max(dim=-1).values                         # (N,)

        # Accumulate weighted normals + centers per group
        rep_n_acc = torch.zeros((G, 3), dtype=torch.float32, device=device)
        rep_c_acc = torch.zeros((G, 3), dtype=torch.float32, device=device)
        rep_w_acc = torch.zeros((G,), dtype=torch.float32, device=device)
        mask_in_group = group_ids >= 0
        g = group_ids[mask_in_group]
        rep_n_acc.index_add_(0, g, normals[mask_in_group] * w[mask_in_group, None])
        rep_c_acc.index_add_(0, g, centers[mask_in_group] * w[mask_in_group, None])
        rep_w_acc.index_add_(0, g, w[mask_in_group])

        rep_n = F.normalize(rep_n_acc / rep_w_acc[:, None].clamp_min(1e-8), dim=-1)
        rep_c = rep_c_acc / rep_w_acc[:, None].clamp_min(1e-8)
        rep_d = -(rep_n * rep_c).sum(dim=-1)

    return group_ids, rep_n, rep_d


# ============================================================================
# G2: surface-level grouping (RESEARCH_CONTEXT §15.2 candidate A+adjacency)
# ============================================================================


def group_primitives_g2(
    centers: torch.Tensor,        # (N, 3)
    normals: torch.Tensor,        # (N, 3) unit
    sem_logits: torch.Tensor,     # (N, K)
    scales: torch.Tensor,         # (N, 3) (not log)
    voxel_size: float = 2.0,      # coarse voxel for cell hash
    n_directions: int = 12,
    merge_n_cos: float = 0.92,    # ≈23°; match Stage 3 strict_thresh
    merge_d_tol: float = 0.5,     # |Δ rep_d| (m) for cell merge
    min_group_size: int = 30,     # surface-level expects more members
    exclude_bg: bool = True,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Surface-level grouping via coarse-cell hash + cell-level union-find.

    Pipeline:
      1. Coarse cell hash: (class, floor(c/V), dir_bin) → cells (cell rep_n,
         rep_d averaged across N_cell primitives, attenuating noise by 1/√N_cell).
      2. Cell-level union-find: merge cells in same class whose voxels are
         26-neighbours AND |rep_n_a · rep_n_b| > merge_n_cos AND
         |rep_d_a − rep_d_b| < merge_d_tol. Connected component = surface group.
      3. Filter components by total primitive count (min_group_size).
      4. Final rep_n / rep_d weighted-averaged over all member primitives
         (re-fit on the merged set, not the per-cell average).

    Returns same signature as group_primitives() — drop-in replacement.
    """
    device = centers.device
    N = centers.shape[0]
    with torch.no_grad():
        cls = sem_logits.argmax(dim=-1)
        valid = (cls != 0) if exclude_bg else torch.ones(N, dtype=torch.bool, device=device)

        # ---- Step 1: coarse cell hash ------------------------------------
        vox = torch.floor(centers / voxel_size).to(torch.int64)            # (N,3)
        basis = _fibonacci_directions(n_directions, device=device)
        dir_bin = (normals @ basis.T).abs().argmax(dim=-1).to(torch.int64) # (N,)

        key = torch.stack([
            cls.to(torch.int64),
            vox[:, 0], vox[:, 1], vox[:, 2],
            dir_bin,
        ], dim=-1)                                                          # (N,5)
        key_valid = key[valid]
        if key_valid.numel() == 0:
            empty_g = torch.full((N,), -1, dtype=torch.int64, device=device)
            return empty_g, torch.zeros((0, 3), device=device), torch.zeros((0,), device=device)
        uniq, inv = torch.unique(key_valid, return_inverse=True, dim=0)    # uniq:(C,5)
        C = uniq.shape[0]                                                  # cell count

        # primitive → cell_id (-1 if BG/excluded)
        cell_of_prim = torch.full((N,), -1, dtype=torch.int64, device=device)
        cell_of_prim[valid] = inv

        # ---- Step 2a: per-cell rep_n / rep_d -----------------------------
        w = scales[:, :2].max(dim=-1).values                                # (N,)
        rep_n_acc = torch.zeros((C, 3), dtype=torch.float32, device=device)
        rep_c_acc = torch.zeros((C, 3), dtype=torch.float32, device=device)
        rep_w_acc = torch.zeros((C,), dtype=torch.float32, device=device)
        cnt_acc   = torch.zeros((C,), dtype=torch.int64,   device=device)

        m = cell_of_prim >= 0
        c_idx = cell_of_prim[m]
        rep_n_acc.index_add_(0, c_idx, normals[m] * w[m, None])
        rep_c_acc.index_add_(0, c_idx, centers[m] * w[m, None])
        rep_w_acc.index_add_(0, c_idx, w[m])
        cnt_acc.index_add_(0,   c_idx, torch.ones_like(c_idx))

        cell_n = F.normalize(rep_n_acc / rep_w_acc[:, None].clamp_min(1e-8), dim=-1)
        cell_c = rep_c_acc / rep_w_acc[:, None].clamp_min(1e-8)
        cell_cls = uniq[:, 0]                                              # (C,)
        cell_vox = uniq[:, 1:4]                                            # (C,3)

        # ---- Step 2b: cell-level union-find (CPU; C is small) ------------
        # Coplanarity test uses LOCAL point-to-plane distance (Δc projected on
        # rep_n) — origin-invariant. Using global rep_d = −n·c̄ would drift by
        # tan(noise_angle) × |c̄| (e.g. 8° × 30m ≈ 4m) and over-segment large
        # surfaces.
        cell_cls_np = cell_cls.cpu().numpy()
        cell_vox_np = cell_vox.cpu().numpy()
        cell_n_np   = cell_n.cpu().numpy()
        cell_c_np   = cell_c.cpu().numpy()

        # voxel → list of cell indices  (key includes class so cross-class never merge)
        from collections import defaultdict
        vox2cells = defaultdict(list)
        for ci in range(C):
            k = (int(cell_cls_np[ci]),
                 int(cell_vox_np[ci, 0]),
                 int(cell_vox_np[ci, 1]),
                 int(cell_vox_np[ci, 2]))
            vox2cells[k].append(ci)

        parent = list(range(C))

        def _find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(a: int, b: int) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra

        # 26-neighbour offsets (excluding self)
        offsets = [(dx, dy, dz)
                   for dx in (-1, 0, 1)
                   for dy in (-1, 0, 1)
                   for dz in (-1, 0, 1)
                   if not (dx == 0 and dy == 0 and dz == 0)]

        def _coplanar(i: int, j: int) -> bool:
            n_i = cell_n_np[i]; n_j = cell_n_np[j]
            if abs(float(n_i @ n_j)) <= merge_n_cos:
                return False
            dc = cell_c_np[j] - cell_c_np[i]
            # symmetric point-to-plane distance: max of i→j and j→i.
            d_ij = abs(float(n_i @ dc))
            d_ji = abs(float(n_j @ dc))
            return max(d_ij, d_ji) < merge_d_tol

        for ci in range(C):
            cls_i = int(cell_cls_np[ci])
            vx, vy, vz = (int(cell_vox_np[ci, 0]),
                          int(cell_vox_np[ci, 1]),
                          int(cell_vox_np[ci, 2]))
            # self-voxel: same (cls, vox) but different dir_bin → also try merge
            for cj in vox2cells.get((cls_i, vx, vy, vz), []):
                if cj <= ci:
                    continue
                if _coplanar(ci, cj):
                    _union(ci, cj)
            # 26-neighbours
            for dx, dy, dz in offsets:
                for cj in vox2cells.get((cls_i, vx + dx, vy + dy, vz + dz), []):
                    if _coplanar(ci, cj):
                        _union(ci, cj)

        # path-compress all
        roots = [_find(i) for i in range(C)]
        # remap roots → contiguous component ids
        root_to_cid: dict = {}
        cell_comp = [0] * C
        for i, r in enumerate(roots):
            if r not in root_to_cid:
                root_to_cid[r] = len(root_to_cid)
            cell_comp[i] = root_to_cid[r]
        n_comp = len(root_to_cid)

        cell_comp_t = torch.tensor(cell_comp, dtype=torch.int64, device=device)

        # ---- Step 3: assign components to primitives, filter by size -----
        comp_of_prim = torch.full((N,), -1, dtype=torch.int64, device=device)
        comp_of_prim[m] = cell_comp_t[c_idx]

        comp_size = torch.bincount(comp_of_prim[comp_of_prim >= 0], minlength=n_comp)
        keep = comp_size >= min_group_size
        remap = torch.full((n_comp,), -1, dtype=torch.int64, device=device)
        kept_idx = torch.nonzero(keep, as_tuple=False).squeeze(-1)
        remap[kept_idx] = torch.arange(kept_idx.numel(), device=device)

        group_ids = torch.full((N,), -1, dtype=torch.int64, device=device)
        valid2 = comp_of_prim >= 0
        group_ids[valid2] = remap[comp_of_prim[valid2]]
        group_ids[group_ids < 0] = -1

        G = int(kept_idx.numel())
        if G == 0:
            return group_ids, torch.zeros((0, 3), device=device), torch.zeros((0,), device=device)

        # ---- Step 4: final rep_n / rep_d on merged primitive sets --------
        rep_n_g = torch.zeros((G, 3), dtype=torch.float32, device=device)
        rep_c_g = torch.zeros((G, 3), dtype=torch.float32, device=device)
        rep_w_g = torch.zeros((G,),   dtype=torch.float32, device=device)
        mg = group_ids >= 0
        gg = group_ids[mg]
        rep_n_g.index_add_(0, gg, normals[mg] * w[mg, None])
        rep_c_g.index_add_(0, gg, centers[mg] * w[mg, None])
        rep_w_g.index_add_(0, gg, w[mg])

        rep_n = F.normalize(rep_n_g / rep_w_g[:, None].clamp_min(1e-8), dim=-1)
        rep_c = rep_c_g / rep_w_g[:, None].clamp_min(1e-8)
        rep_d = -(rep_n * rep_c).sum(dim=-1)

    return group_ids, rep_n, rep_d
