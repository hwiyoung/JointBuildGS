"""Training-time reads of the locations (PHD-STAGE2-R7-PROPAGATION-v1; torch). Used by the stage-2 fork r7.

  seated location : surface = the surface the Gaussian first sat on (carried through split and clone via init_id);
                    cell = the cell of that surface nearest to the current centre (locations.locate on torch tensors)
  re-read of E    : every re-read interval the Gaussian confidence of the occupied locations is measured again with the
                    current render as the occluder: n x n sample points of each cell are projected into the training
                    views; a sample is hidden when it lies more than depth_tol behind the rendered expected depth at its
                    pixel (one-sided; pixels with accumulated opacity < alpha_min hide nothing); a view sees the location
                    when at least one sample is not hidden, supports it when at least half of its unhidden samples fall
                    on pixels with A = 1. E = supporting / seeing views (0 when none sees it).
The first E (initialisation) is the location's own E from the stage-1 product (pixels of the prior render = occlusion by
the prior depth); the marks and propagated judgments are never recomputed from the training surface."""
import torch

from . import locations


def to_torch(store, device="cuda"):
    out = {}
    for k, v in store.items():
        t = torch.as_tensor(v)
        if t.dtype in (torch.float32, torch.float64):
            t = t.to(torch.float64)
        out[k] = t.to(device)
    out["sp"] = float(store["sp"])
    return out


def seat(store_t, s_idx, X):
    """location of each point on its surface (compact index s_idx >= 0), float64 arithmetic."""
    return locations.locate(store_t, s_idx.long(), X.to(torch.float64))


def cell_samples(store_t, loc_ids, n=3):
    """[len(loc_ids), n*n, 3] sample points spread over each cell (extra locations collapse to their centroid)."""
    sp = store_t["sp"]
    a = (torch.arange(n, device=loc_ids.device, dtype=torch.float64) + 0.5) / n - 0.5
    A, B = torch.meshgrid(a, a, indexing="ij")
    A, B = A.reshape(-1), B.reshape(-1)
    c = store_t["loc_center"][loc_ids]
    t1 = store_t["loc_t1"][loc_ids]; t2 = store_t["loc_t2"][loc_ids]
    return c[:, None, :] + sp * (A[None, :, None] * t1[:, None, :] + B[None, :, None] * t2[:, None, :])


@torch.no_grad()
def reread_E(samples, cameras, project, A_maps, D_maps, AL_maps, depth_tol, alpha_min):
    """samples [K, m, 3] (float64); project(xyz float32 [N, 3], camera) -> (u, v, z) as the rasterizer (jbgs_judgment.project_points).
    D_maps / AL_maps: rendered expected depth and accumulated opacity per training view (training resolution); for the
    initial check the prior depth with AL = 1 where it is finite. Returns (E [K], n_seeing [K], n_supporting [K])."""
    K, m, _ = samples.shape
    flat = samples.reshape(-1, 3).to(torch.float32)
    n_seeing = torch.zeros(K, device=samples.device); n_supp = torch.zeros(K, device=samples.device)
    for cam in cameras:
        A = A_maps.get(cam.image_name); D = D_maps.get(cam.image_name); AL = AL_maps.get(cam.image_name)
        if A is None or D is None or AL is None:
            continue
        H, W = A.shape
        u, v, z = project(flat, cam)
        ui = torch.round(u).long(); vi = torch.round(v).long()
        inside = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        idx = vi.clamp(0, H - 1) * W + ui.clamp(0, W - 1)
        Dv = D.reshape(-1)[idx]; av = AL.reshape(-1)[idx]; Av = A.reshape(-1)[idx]
        empty = ~(av >= alpha_min) | ~torch.isfinite(Dv) | (Dv <= 0)
        hidden = ~empty & (z > Dv + depth_tol)
        seen = (inside & ~hidden).reshape(K, m)
        n_seen_s = seen.sum(1)
        a1 = ((Av > 0.5) & (inside & ~hidden)).reshape(K, m).sum(1)
        view_sees = n_seen_s > 0
        view_supports = view_sees & (2 * a1 >= n_seen_s)
        n_seeing += view_sees.float(); n_supp += view_supports.float()
    E = torch.where(n_seeing > 0, n_supp / n_seeing.clamp_min(1.0), torch.zeros_like(n_seeing))
    return E, n_seeing, n_supp
