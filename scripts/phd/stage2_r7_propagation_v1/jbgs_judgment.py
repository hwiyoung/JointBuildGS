"""Judgment-guided stage-2 optimization for GeoGS, revision r7 (JointBuildGS PHD-STAGE2-R7-PROPAGATION-v1).

r7 = r6 + location-based judgments and their propagation (method document 4.x as transcribed in the r7 order), all
rules in the shared module src/phd/prior_propagation_v1 (copied into the fork at build time, sha256 checked):
  (r7-1) initialisation : every prior point gets its seated location (surface = the prior surface it was sampled on,
                          cell = the nearest cell of that surface), the location's state, first Gaussian confidence (the
                          location's E from the stage-1 product, occlusion by the prior render) and propagated judgment
                          (computed here from the product's states and votes with the configured majority / minimum /
                          maximum distance). Prior points of invisible locations are not planted; prior points of missing
                          locations whose propagated judgment is conflict are not planted unless jbgs_init_plant_conflict.
                          Unplanted pieces are written to monitor/unplanted.npz. Prior points without a location (TIN
                          ground, vertices only on steep triangles) keep the r6 rule (E and visibility from the pixel of
                          the centre, no judgment).
  (r7-2) re-read        : at iteration 1 and every multiple of jbgs_e_interval each prior Gaussian's cell is found again
                          on its initial surface (init_id -> surface, so split/clone children inherit it); E of the
                          occupied cells is measured again with the current render as the occluder (seat.reread_E); the
                          propagated judgment is read from the initial table (never recomputed from the training surface)
  (r7-3) protection     : prior origin, judgment not conflict, E < threshold, drift from the initial disk <= mult x tau
                          of the surface kind (roof-like / wall-like tolerance of the stage-1 product)
  (r7-4) prior term gate: the prior depth term is off at pixels whose prior-surface location carries a propagated conflict
                          (per-view location maps of the product, decided once at initialisation)
  (r7-5) attributes     : surface number, seated location, last E and judgment in the dumps and as PLY columns
  (r7-6) dry run        : jbgs_dry_init 1 writes monitor/init_report.json (and init_points.npz) after the first E and exits

--- r6 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r6 (JointBuildGS PHD-STAGE2-R6-FIX-v1).

r6 = r5 (PHD-STAGE2-CONF-GUIDED-GS-v1, the fork of the 11-condition run) with the five fixes found by the 4.4 audit
(PHD-STAGE2-PROTECTION-AUDIT-v1). Everything not listed here is unchanged from r5, in particular the Adam-proof lock
(post-step update blend on xyz/rotation/scaling), the per-step opacity floor, colour, density control and read-outs.
  (1)  occlusion     : the first E computation uses the prior depth as in r5 (the scene is the prior); every later one
                       renders the 13 training views (expected depth, as the losses use) and counts a view as seeing the
                       centre unless the centre lies more than jbgs_e_depth_tol behind the rendered depth at its pixel;
                       pixels whose accumulated opacity is below jbgs_e_alpha_min occlude nothing (compute_E_render)
  (1a) timing        : E at iteration 1 and at every multiple of jbgs_e_interval, at the start of the iteration (before
                       the render, before that iteration's opacity reset) (due_E_iteration)
  (2)  protection    : prior origin, E < threshold and drift from the initial disk <= jbgs_lock_drift_tau_mult x tau_v,
                       whatever the number of seeing views (lock_rule_r6); the r5 off-prior exception is gone
  (3)  opacity floor : applied the moment the protection mask is set (floor_now), besides after every step as in r5
  (4)  initialisation: prior points that no training view sees (inside the image, in front of the camera, within
                       jbgs_e_depth_tol of the prior depth at their pixel) are removed before training (init_visible_filter)
  (5)  normalisation : both depth terms divide by the pixel count of the view (jbgs_depth_norm = pixels; weights = r5)

Implements ORDER_ko_v1 section 4 on top of the unchanged 2DGS/GeoGS renderer:
  (2) per-pixel weighted losses   : MVS term  sum A |D-M| / n_px,
                                    prior term sum (1-A) rho_tau(D-P) / n_px   (P mode)
                                    prior term plain L1 on every prior pixel / n_px   (P0 mode)
  (3) disk judgment E and locking : see (1)-(3) above; locked disks: Adam update x0.01 on xyz/rot/scale, opacity
                                    floor 0.5, exempt from prune/split/clone/opacity reset
  (4) origin bookkeeping          : GaussianModel.origin (0 = image/SfM, 1 = prior) and GaussianModel.init_id
                                    (index of the initial disk, -1 for none), both inherited by children
  (5) read-outs                   : per-face d_F, e_F, cov_F, g_F every N iterations from rendered surf_depth

Sign convention (stage 1, REPORT section 2): d_F = median((D - P) * f) is positive when the prior lies ABOVE the
rendered surface (camera depth grows downward). A prior raised by +1 m that the render leaves behind gives d_F = +1.
e_F = median((D - M) * f) and g_F = median((D - G) * f) follow the same rule (+ = MVS / GT above the render).

Lock implementation: Adam normalises the gradient, so scaling the gradient of a disk (the native GeoGS
attenuate_*_lr hooks) leaves its step almost unchanged. The lock therefore scales the applied update:
p <- p_old + s * (p_adam - p_old) for locked rows, which is exactly lr x s for that disk.

Modes: off (module inert, native GeoGS path) | P (judgment on) | P0 (judgment off, plain prior L1) | I (image only).
Only cameras of the training split enter the losses; test cameras are used for read-outs only.
"""
import json
import math
import os
import time
from pathlib import Path

import cv2
import numpy as np
import torch

try:  # r7: the shared module is copied into the fork root as src/phd/prior_propagation_v1 (build_fork_r7.py)
    from src.phd.prior_propagation_v1 import locations as ppl
    from src.phd.prior_propagation_v1 import rule as ppr
    from src.phd.prior_propagation_v1 import seat as pps
except ImportError:  # pragma: no cover - r6 behaviour stays available without the module
    ppl = ppr = pps = None

MODES = ("off", "P", "P0", "I")
ORIGIN_IMAGE, ORIGIN_PRIOR = 0, 1
LABELS = ("preserve", "correct", "undecided", "other")
REVISION = "r7"


# ----------------------------------------------------------------------------------------------------------- args
def register_args(parser):
    g = parser.add_argument_group("jbgs_judgment")
    g.add_argument("--jbgs_judgment", default="off", choices=MODES, help="off | P | P0 | I (ORDER section 5)")
    g.add_argument("--jbgs_maps_root", default="", help="inputs/maps root holding <set>/raw_depth/<view>.npy")
    g.add_argument("--jbgs_prior_set", default="", help="prior depth set name, e.g. prior_M_N")
    g.add_argument("--jbgs_tau_set", default="", help="per-pixel width set name, e.g. tau_M")
    g.add_argument("--jbgs_tau_v", type=float, default=float("nan"), help="vertical width tau_v (m) for read-out labels")
    g.add_argument("--jbgs_origin_path", default="", help="origin.npy aligned with the initial point cloud")
    g.add_argument("--jbgs_faces_json", default="", help="faces.json with roof/wall polygon ids")
    g.add_argument("--jbgs_scene", default="N", choices=["N", "B"], help="N nominal | B main roof raised 1 m")
    g.add_argument("--jbgs_injected_face", type=int, default=3396)
    g.add_argument("--jbgs_injected_delta", type=float, default=1.0, help="vertical raise (m) of the injected roof (B)")
    g.add_argument("--jbgs_lambda_mvs", type=float, default=0.05)
    g.add_argument("--jbgs_lambda_prior", type=float, default=0.05)
    g.add_argument("--jbgs_trunc_hi", type=float, default=4.0, help="rho_tau is constant beyond hi*tau")
    g.add_argument("--jbgs_e_interval", type=int, default=500)
    g.add_argument("--jbgs_e_threshold", type=float, default=0.5)
    g.add_argument("--jbgs_e_depth_tol", type=float, default=0.5, help="depth tolerance (m) of the seeing test")
    g.add_argument("--jbgs_e_alpha_min", type=float, default=0.05,
                   help="r6 (1): accumulated opacity below which a rendered pixel occludes nothing")
    g.add_argument("--jbgs_lock_drift_tau_mult", type=float, default=4.0,
                   help="r6 (2): protect only disks within mult x tau_v of their initial disk (4 = end of the prior term's pull)")
    g.add_argument("--jbgs_init_visible_only", type=int, default=1,
                   help="r6 (4): 1 = drop prior points that no training view sees at initialisation")
    g.add_argument("--jbgs_depth_norm", default="pixels", choices=["pixels", "weights"],
                   help="r6 (5): divide both depth terms by the pixel count of the view (pixels) or by their weight sums (weights = r5)")
    # r7: location-based judgments and their propagation (shared module src/phd/prior_propagation_v1)
    g.add_argument("--jbgs_prop_store", default="", help="r7: stage-1 product store (store_<variant>_c<cell>.npz); empty = r6 behaviour")
    g.add_argument("--jbgs_prop_tau_variant", default="spec", choices=["spec", "data"], help="r7: which tolerance variant's states/votes")
    g.add_argument("--jbgs_prop_majority", type=float, default=2.0 / 3.0)
    g.add_argument("--jbgs_prop_min_evidence", type=int, default=5)
    g.add_argument("--jbgs_prop_max_distance", type=float, default=1.0, help="r7: metres along the surface")
    g.add_argument("--jbgs_seat_path", default="", help="r7: seat_surface.npy aligned with the initial cloud (compact surface index, -1 none)")
    g.add_argument("--jbgs_locmap_dir", default="", help="r7: per-view location maps of the product (prior-term gate)")
    g.add_argument("--jbgs_tau_dir", default="", help="r7: per-view tau_p maps (overrides maps_root/tau_set)")
    g.add_argument("--jbgs_tau_roof", type=float, default=float("nan"), help="r7: roof-like tolerance (m) for the drift bound")
    g.add_argument("--jbgs_tau_wall", type=float, default=float("nan"), help="r7: wall-like tolerance (m) for the drift bound")
    g.add_argument("--jbgs_init_plant_conflict", type=int, default=0, help="r7: 1 = plant points of conflict-propagated missing locations")
    g.add_argument("--jbgs_prior_gate", default="propagated", choices=["propagated", "location", "off"],
                   help="r7: prior term off at propagated-conflict pixels (propagated), also at support-conflict pixels (location), never (off)")
    g.add_argument("--jbgs_reread_samples", type=int, default=3, help="r7: n x n samples per cell for the re-read of E")
    g.add_argument("--jbgs_dry_init", type=int, default=0, help="r7: 1 = write monitor/init_report.json after the first E and exit")
    g.add_argument("--jbgs_lock_lr_scale", type=float, default=0.01)
    g.add_argument("--jbgs_lock_opacity_floor", type=float, default=0.5)
    g.add_argument("--jbgs_log_interval", type=int, default=100)
    g.add_argument("--jbgs_readout_interval", type=int, default=1000)
    g.add_argument("--jbgs_snapshot_iterations", type=int, nargs="+", default=[2000, 5000, 10000, 15000, 20000, 30000])
    g.add_argument("--jbgs_dump_iterations", type=int, nargs="+", default=[15000, 30000])
    g.add_argument("--jbgs_monitor_views", nargs="+", default=["DJI_20241217101305_0005_D", "DJI_20241217101343_0024_D"])
    g.add_argument("--jbgs_stop_on_red", type=int, default=1, help="1: a red binding check stops the run (ORDER 4/7)")


# -------------------------------------------------------------------------------------------------------- pure math
def rho_truncated(r, tau, hi=4.0):
    """rho_tau(r) = 0 (|r|<=tau); |r|-tau (tau<|r|<=hi*tau); (hi-1)*tau (|r|>hi*tau). Gradient is 0 beyond hi*tau."""
    a = torch.clamp(torch.abs(r) - tau, min=0.0)
    return torch.minimum(a, (hi - 1.0) * tau)


@torch.no_grad()
def scale_locked_update(param, old_rows, mask, scale):
    """Locked rows keep `scale` of the optimizer's step: p[mask] <- old + scale * (p[mask] - old) (= lr x scale)."""
    param.data[mask] = old_rows + scale * (param.data[mask] - old_rows)


def roof_check(scene, iteration, d, tau, delta=1.0):
    """ORDER section 7 rule for the main roof 3396. Returns (name, status, rule).
    Sign: d = median((D - P) * f), + = prior above the render. Scene B raises the prior by +delta, so a surface that
    follows the photos gives d -> +delta. Rules start at iteration 2000 (status 'pending' before)."""
    if iteration < 2000:
        return ("main_roof_d" if scene == "N" else "injected_roof_moving"), "pending", "rules start at iteration 2000"
    if scene == "N":
        st = "green" if abs(d) < tau else ("red" if abs(d) > 4 * tau else "yellow")
        return "main_roof_d", st, f"green |d|<{tau:.3f}; red |d|>{4 * tau:.3f}"
    if iteration < 15000:
        st = "green" if d > tau else ("red" if d < tau else "yellow")
        return "injected_roof_moving", st, f"green d>+{tau:.3f} (moving toward the photos); red d<{tau:.3f} (not moving or opposite)"
    st = "green" if abs(d - delta) < 4 * tau else ("red" if abs(d - delta) > 0.3 else "yellow")
    return "injected_roof_returned", st, f"green |d-{delta:g}|<{4 * tau:.3f}; red |d-{delta:g}|>0.3"


def weighted_l1(D, T, w, denom=None):
    """sum w|D-T| over pixels where T and D are valid and w > 0, divided by `denom` (r6 (5): the pixel count of the view)
    or, when denom is None, by sum w (r5). Returns (loss, n_valid, n_hole)."""
    valid_t = torch.isfinite(T) & (T > 0) & (w > 0)
    rendered = torch.isfinite(D) & (D > 0)
    valid = valid_t & rendered
    n_hole = int((valid_t & ~rendered).sum())
    n = int(valid.sum())
    if n == 0:
        return torch.zeros((), device=D.device), 0, n_hole
    ww = w[valid]
    den = (ww.sum() + 1e-9) if denom is None else denom
    return (torch.abs(D[valid] - T[valid]) * ww).sum() / den, n, n_hole


def truncated_prior_loss(D, P, tau, w, hi=4.0, denom=None):
    """sum w rho_tau(D-P) over prior pixels (tau finite) with w > 0, divided by `denom` (r6 (5): the pixel count of the
    view) or, when denom is None, by sum w (r5). Returns (loss, n_valid, n_hole, n_beyond)."""
    valid_t = torch.isfinite(P) & (P > 0) & torch.isfinite(tau) & (w > 0)
    rendered = torch.isfinite(D) & (D > 0)
    valid = valid_t & rendered
    n_hole = int((valid_t & ~rendered).sum())
    n = int(valid.sum())
    if n == 0:
        return torch.zeros((), device=D.device), 0, n_hole, 0
    r = D[valid] - P[valid]
    t = tau[valid]
    ww = w[valid]
    n_beyond = int((torch.abs(r) > hi * t).sum())
    den = (ww.sum() + 1e-9) if denom is None else denom
    return (rho_truncated(r, t, hi) * ww).sum() / den, n, n_hole, n_beyond


@torch.no_grad()
def project_points(xyz, camera):
    """Project world points with the camera's own transforms (same convention as the rasterizer:
    p_hom = [x,1] @ full_proj_transform, ndc = p_hom.xy / p_hom.w, pixel = ((ndc+1)*size-1)/2).
    Returns (u, v, z) with z = camera depth."""
    n = xyz.shape[0]
    hom = torch.cat([xyz, torch.ones((n, 1), device=xyz.device, dtype=xyz.dtype)], dim=1)
    pv = hom @ camera.world_view_transform
    pc = hom @ camera.full_proj_transform
    w = pc[:, 3:4]
    w = torch.where(torch.abs(w) < 1e-7, torch.full_like(w, 1e-7), w)
    ndc = pc[:, :2] / w
    u = ((ndc[:, 0] + 1.0) * camera.image_width - 1.0) * 0.5
    v = ((ndc[:, 1] + 1.0) * camera.image_height - 1.0) * 0.5
    return u, v, pv[:, 2]


@torch.no_grad()
def compute_E(xyz, cameras, A_maps, P_maps, depth_tol):
    """E_k over the given (training) cameras with the PRIOR depth as the scene (r5 rule; r6 uses it for the first
    computation and for the initial visibility filter). A seeing view: projection inside the image, prior depth finite
    there, and |z_v - P_v| < depth_tol. E_k = mean of A over seeing views; 0 when no view sees the disk.
    Returns (E [N], n_seeing [N])."""
    n = xyz.shape[0]
    ssum = torch.zeros(n, device=xyz.device)
    cnt = torch.zeros(n, device=xyz.device)
    for cam in cameras:
        A = A_maps.get(cam.image_name)
        P = P_maps.get(cam.image_name)
        if A is None or P is None:
            continue
        H, W = A.shape
        u, v, z = project_points(xyz, cam)
        ui = torch.round(u).long()
        vi = torch.round(v).long()
        inside = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        idx = (vi.clamp(0, H - 1) * W + ui.clamp(0, W - 1))
        Pv = P.reshape(-1)[idx]
        Av = A.reshape(-1)[idx]
        sees = inside & torch.isfinite(Pv) & (torch.abs(z - Pv) < depth_tol)
        ssum[sees] += Av[sees]
        cnt[sees] += 1.0
    E = torch.where(cnt > 0, ssum / cnt.clamp_min(1.0), torch.zeros_like(ssum))
    return E, cnt


@torch.no_grad()
def compute_E_render(xyz, cameras, A_maps, D_maps, alpha_maps, depth_tol, alpha_min):
    """r6 (1): E_k over the given (training) cameras with the CURRENT render as the scene. A view sees the centre when the
    projection is inside the image and in front of the camera and the centre is not more than depth_tol behind the
    rendered expected depth D at its pixel (in front of D, or within depth_tol behind it, counts as seen). A pixel whose
    accumulated opacity is below alpha_min (or whose depth is empty) occludes nothing.
    E_k = mean of A over seeing views; 0 when no view sees the disk.
    Returns (E [N], n_seeing [N], n_empty) with n_empty = number of (disk, view) pairs that landed on empty pixels."""
    n = xyz.shape[0]
    ssum = torch.zeros(n, device=xyz.device)
    cnt = torch.zeros(n, device=xyz.device)
    n_empty = 0
    for cam in cameras:
        A = A_maps.get(cam.image_name)
        D = D_maps.get(cam.image_name)
        AL = alpha_maps.get(cam.image_name)
        if A is None or D is None or AL is None:
            continue
        H, W = A.shape
        u, v, z = project_points(xyz, cam)
        ui = torch.round(u).long()
        vi = torch.round(v).long()
        inside = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        idx = (vi.clamp(0, H - 1) * W + ui.clamp(0, W - 1))
        Dv = D.reshape(-1)[idx]
        av = AL.reshape(-1)[idx]
        Av = A.reshape(-1)[idx]
        empty = ~(av >= alpha_min) | ~torch.isfinite(Dv) | (Dv <= 0)
        behind = ~empty & (z > Dv + depth_tol)
        sees = inside & ~behind
        n_empty += int((inside & empty).sum())
        ssum[sees] += Av[sees]
        cnt[sees] += 1.0
    E = torch.where(cnt > 0, ssum / cnt.clamp_min(1.0), torch.zeros_like(ssum))
    return E, cnt, n_empty


def due_E_iteration(iteration, interval):
    """r6 (1a): iteration 1 and every multiple of interval (called at the start of the iteration, so an E computed at a
    multiple of the opacity-reset interval sees the scene before that iteration's reset)."""
    return iteration == 1 or iteration % interval == 0


def lock_rule_r6(E, drift, is_prior, threshold=0.5, drift_max=0.227):
    """r6 (2): protect prior-origin disks with E < threshold that lie within drift_max of their initial disk (the initial
    disk of the ancestor for split/clone children), whatever the number of seeing views. A disk that left the prior
    by more than drift_max no longer carries prior shape. Returns (lock, far): far = prior disks with E < threshold that
    are farther than drift_max (not protected)."""
    near = torch.isfinite(drift) & (drift <= drift_max)
    low = is_prior & (E < threshold)
    return low & near, low & ~near


@torch.no_grad()
def init_visible_filter(gaussians, cameras, A_maps, P_maps, depth_tol, save_path=None):
    """r6 (4), method 4.2: remove the prior-origin points that no training view sees at initialisation. The scene is the
    prior at this moment, so a view sees a point when it projects inside the image, in front of the camera and within
    depth_tol of the prior depth at its pixel (the seeing test of compute_E). Image-origin points are kept.
    Must run before init_id / init_xyz are taken. Returns a summary dict."""
    prior = gaussians.origin == ORIGIN_PRIOR
    xyz = gaussians.get_xyz.detach()
    _, cnt = compute_E(xyz, cameras, A_maps, P_maps, depth_tol)
    drop = prior & (cnt == 0)
    info = dict(applied=True, rule="prior point kept iff >= 1 training view: inside image, z > 0.01, |z - P| < depth_tol",
                depth_tol=float(depth_tol), n_before=int(prior.shape[0]), n_prior_before=int(prior.sum()),
                n_prior_dropped=int(drop.sum()), n_prior_kept=int((prior & ~drop).sum()), n_image=int((~prior).sum()),
                seeing_views_hist_prior=np.bincount(cnt[prior].long().cpu().numpy(), minlength=14).tolist())
    if save_path is not None:
        np.savez_compressed(save_path, xyz=xyz.cpu().numpy().astype(np.float32), origin=gaussians.origin.cpu().numpy(),
                            n_seeing=cnt.cpu().numpy().astype(np.int16), dropped=drop.cpu().numpy())
    if bool(drop.any()):
        gaussians.prune_points(drop)
    return info


def face_readout(records, tau_v, faces_roof, faces_wall):
    """records: dict face_id -> dict(d=list of tensors, e=..., g=..., n_pixels=int, n_A=int).
    Returns list of dict rows with medians, NMAD and the ORDER labels."""
    rows = []
    groups = [(int(f), [int(f)]) for f in faces_roof]
    if faces_wall:
        groups.append(("wall", [int(f) for f in faces_wall]))

    def med_nmad(chunks):
        if not chunks:
            return float("nan"), float("nan"), 0
        x = torch.cat(chunks).double()
        if x.numel() == 0:
            return float("nan"), float("nan"), 0
        m = x.median()
        nmad = 1.4826 * (x - m).abs().median()
        return float(m), float(nmad), int(x.numel())

    for name, members in groups:
        d_chunks, e_chunks, g_chunks, dall_chunks = [], [], [], []
        n_pix = n_a = 0
        for f in members:
            r = records.get(f)
            if r is None:
                continue
            d_chunks += r["d"]; e_chunks += r["e"]; g_chunks += r["g"]; dall_chunks += r["d_all"]
            n_pix += r["n_pixels"]; n_a += r["n_A"]
        d, d_nmad, nd = med_nmad(d_chunks)
        e, e_nmad, ne = med_nmad(e_chunks)
        gm, g_nmad, ng = med_nmad(g_chunks)
        dall, dall_nmad, ndall = med_nmad(dall_chunks)
        cov = n_a / n_pix if n_pix else float("nan")
        if not (cov == cov) or math.isnan(tau_v):
            label = "other"
        elif cov < 0.5:
            label = "undecided"
        elif not math.isnan(d) and abs(d) < tau_v:
            label = "preserve"
        elif not math.isnan(d) and not math.isnan(e) and abs(e) < tau_v:
            label = "correct"
        else:
            label = "other"
        rows.append(dict(face=name, n_pixels=n_pix, n_A=n_a, cov=cov, d=d, d_nmad=d_nmad, n_d=nd,
                         d_all=dall, d_all_nmad=dall_nmad, n_d_all=ndall,
                         e=e, e_nmad=e_nmad, n_e=ne, g=gm, g_nmad=g_nmad, n_g=ng, label=label))
    return rows


# --------------------------------------------------------------------------------------------------------- loading
def _load_set(root, names, size, device, dtype=np.float32, interpolation=cv2.INTER_NEAREST):
    d = Path(root) / "raw_depth"
    if not d.exists():
        d = Path(root)
    H, W = size
    out = {}
    for n in names:
        p = d / f"{n}.npy"
        if not p.exists():
            continue
        a = np.load(p)
        if a.shape != (H, W):
            a = cv2.resize(a.astype(np.float32), (W, H), interpolation=interpolation)
        a = a.astype(dtype)
        out[n] = torch.from_numpy(np.ascontiguousarray(a)).to(device)
    return out


def colorize_diverging(arr, vmax, nan_bgr=(90, 90, 90)):
    """float [H,W] -> BGR uint8; blue (-vmax) .. white (0) .. red (+vmax); NaN gray."""
    x = np.clip(np.nan_to_num(arr, nan=0.0) / max(vmax, 1e-9), -1, 1)
    r = np.where(x >= 0, 255, 255 * (1 + x)); b = np.where(x <= 0, 255, 255 * (1 - x))
    g = 255 * (1 - np.abs(x))
    img = np.stack([b, g, r], -1).astype(np.uint8)
    img[~np.isfinite(arr)] = nan_bgr
    return img


# --------------------------------------------------------------------------------------------------------- Judgment
class Judgment:
    def __init__(self, args, opt, scene, gaussians, tb_writer=None, render_fn=None, pipe=None, background=None):
        self.mode = args.jbgs_judgment
        assert self.mode in MODES and self.mode != "off"
        self.args = args
        self.tb = tb_writer
        self.render_fn, self.pipe, self.background = render_fn, pipe, background   # r6 (1): E renders the training views
        self.model_path = Path(args.model_path)
        self.mon = self.model_path / "monitor"
        self.mon.mkdir(parents=True, exist_ok=True)
        self.train_cams = scene.getTrainCameras()
        self.test_cams = scene.getTestCameras()
        self.all_cams = self.train_cams + self.test_cams
        self.train_names = {c.image_name for c in self.train_cams}
        H, W = self.all_cams[0].image_height, self.all_cams[0].image_width
        self.size = (H, W)
        names = [c.image_name for c in self.all_cams]
        root = Path(args.jbgs_maps_root)
        self.A = _load_set(root / "conf", names, self.size, "cuda")
        self.M = _load_set(root / "mvs", names, self.size, "cuda")
        self.P = _load_set(root / args.jbgs_prior_set, names, self.size, "cuda") if self.mode in ("P", "P0") else {}
        tau_root = Path(args.jbgs_tau_dir) if getattr(args, "jbgs_tau_dir", "") else root / args.jbgs_tau_set   # r7
        self.TAU = _load_set(tau_root, names, self.size, "cuda") if self.mode == "P" else {}
        self.FACE = _load_set(root / "faceid", names, self.size, "cpu", dtype=np.int32)
        self.FV = _load_set(root / "fvert", names, self.size, "cpu")
        self.G = _load_set(root / "gt", names, self.size, "cpu")
        faces = json.loads(Path(args.jbgs_faces_json).read_text()) if args.jbgs_faces_json else {"roof": [], "wall": []}
        self.faces_roof = [int(f) for f in faces.get("roof", [])]
        self.faces_wall = [int(f) for f in faces.get("wall", [])]
        self.tau_v = float(args.jbgs_tau_v)
        self.lambda_mvs = float(args.jbgs_lambda_mvs)
        self.lambda_prior = float(args.jbgs_lambda_prior) if self.mode in ("P", "P0") else 0.0
        self.lock_drift_max = float(args.jbgs_lock_drift_tau_mult) * self.tau_v   # r6 (2)
        # r7-3: drift bound per surface kind (roof-like / wall-like tolerance); fall back to tau_v
        tr = float(getattr(args, "jbgs_tau_roof", float("nan"))); tw = float(getattr(args, "jbgs_tau_wall", float("nan")))
        self.tau_kind = {1: tr if math.isfinite(tr) else self.tau_v, 2: tw if math.isfinite(tw) else (tr if math.isfinite(tr) else self.tau_v)}
        # origin
        n = gaussians.get_xyz.shape[0]
        if args.jbgs_origin_path:
            origin = np.load(args.jbgs_origin_path).astype(np.int8)
            if origin.shape[0] != n:
                raise ValueError(f"origin.npy length {origin.shape[0]} != initial gaussians {n}")
            gaussians.origin = torch.from_numpy(origin).cuda()
        else:
            gaussians.origin = torch.zeros(n, dtype=torch.int8, device="cuda")
        if gaussians.frozen_mask is None:
            gaussians.frozen_mask = torch.zeros(n, dtype=torch.bool, device="cuda")
        # r6 (4): initial prior points that no training view sees are removed before the initial ids are taken
        self.init_filter = dict(applied=False)
        self.prop = None
        seat_kept = None
        if self.mode in ("P", "P0") and getattr(args, "jbgs_prop_store", ""):
            seat_kept = self.prop_init(args, gaussians)      # r7-1: plants by location state and propagated judgment
        elif self.mode in ("P", "P0") and int(args.jbgs_init_visible_only):
            missing = [nm for nm in self.train_names if nm not in self.P]
            if missing:
                raise ValueError(f"prior maps missing for training views: {missing}")
            self.init_filter = init_visible_filter(gaussians, self.train_cams, self.A, self.P, args.jbgs_e_depth_tol,
                                                   self.mon / "init_filter.npz")
            print(f"[jbgs_judgment] r6 init filter: prior {self.init_filter['n_prior_before']} -> {self.init_filter['n_prior_kept']} "
                  f"(dropped {self.init_filter['n_prior_dropped']} that no training view sees)")
        n = gaussians.get_xyz.shape[0]
        # initial disks: id, position, origin; last iteration at which a disk carrying the id was alive
        gaussians.init_id = torch.arange(n, dtype=torch.int32, device="cuda")
        self.init_xyz = gaussians.get_xyz.detach().clone()
        self.init_origin = gaussians.origin.clone()
        self.last_seen = torch.zeros(n, dtype=torch.int32, device="cuda")
        # r7: surface of every initial disk (compact index, -1 = none); children reach it through init_id
        self.init_surface = seat_kept if seat_kept is not None else torch.full((n,), -1, dtype=torch.long, device="cuda")
        self.g_loc = self.g_J = self.g_located = None
        self.E = None
        self.E_cnt = None
        self.E_how = None
        self.E_calls = 0
        self.keep_maps = False       # set by instrumentation to keep the last E renders in self.last_maps
        self.last_maps = None
        self.last_update = None
        self._saved = None
        self.counters = {"added": 0, "removed": 0}
        self._wrap_counters(gaussians)
        self.scalars = (self.mon / "scalars.jsonl").open("a", buffering=1)
        self.faces_csv = self.mon / "faces.csv"
        if not self.faces_csv.exists():
            self.faces_csv.write_text("iteration,face,n_pixels,n_A,cov,d,d_nmad,n_d,d_all,d_all_nmad,n_d_all,e,e_nmad,n_e,g,g_nmad,n_g,label\n")
        self.started = time.monotonic()
        self.last_stats = {}
        meta = dict(mode=self.mode, revision=REVISION, size=[H, W], views=names, train_views=sorted(self.train_names),
                    maps=dict(A=len(self.A), M=len(self.M), P=len(self.P), TAU=len(self.TAU), FACE=len(self.FACE),
                              FV=len(self.FV), G=len(self.G)),
                    lambda_mvs=self.lambda_mvs, lambda_prior=self.lambda_prior, tau_v=self.tau_v,
                    n_init=n, n_init_prior=int((gaussians.origin == ORIGIN_PRIOR).sum()),
                    n_init_image=int((gaussians.origin == ORIGIN_IMAGE).sum()),
                    faces_roof=self.faces_roof, faces_wall=self.faces_wall, scene=args.jbgs_scene,
                    e_interval=args.jbgs_e_interval, e_threshold=args.jbgs_e_threshold,
                    e_depth_tol=args.jbgs_e_depth_tol, lock_lr_scale=args.jbgs_lock_lr_scale,
                    lock_mechanism="adam update x lock_lr_scale on xyz/rotation/scaling (post-step blend)",
                    lock_opacity_floor=args.jbgs_lock_opacity_floor, trunc_hi=args.jbgs_trunc_hi,
                    injected_face=args.jbgs_injected_face, injected_delta=args.jbgs_injected_delta,
                    sign_convention="d=(D-P)*f, e=(D-M)*f, g=(D-G)*f; + = reference above the rendered surface",
                    dump_depth_dtype="float32",
                    r6=dict(e_schedule="iteration 1 and every multiple of e_interval, start of the iteration",
                            e_first="prior depth, |z - P| < e_depth_tol",
                            e_later="current render: seen unless z > D + e_depth_tol; accumulated opacity < e_alpha_min occludes nothing",
                            e_alpha_min=args.jbgs_e_alpha_min, lock_rule="prior & E < e_threshold & drift <= lock_drift_max",
                            lock_drift_tau_mult=args.jbgs_lock_drift_tau_mult, lock_drift_max=self.lock_drift_max,
                            floor_at_lock=True, depth_norm=args.jbgs_depth_norm, init_filter=self.init_filter))
        (self.mon / "meta.json").write_text(json.dumps(meta, indent=1))
        print(f"[jbgs_judgment] {REVISION} mode={self.mode} maps={meta['maps']} init={n} prior={meta['n_init_prior']} image={meta['n_init_image']} "
              f"lock_drift_max={self.lock_drift_max:.4f} depth_norm={args.jbgs_depth_norm}")
        missing = [nm for nm in self.train_names if nm not in self.A or nm not in self.M]
        if missing:
            raise ValueError(f"A/MVS maps missing for training views: {missing}")
        if self.mode in ("P", "P0"):
            missing = [nm for nm in self.train_names if nm not in self.P]
            if missing:
                raise ValueError(f"prior maps missing for training views: {missing}")
        if self.mode == "P":
            missing = [nm for nm in self.train_names if nm not in self.TAU]
            if missing:
                raise ValueError(f"tau maps missing for training views: {missing}")
        gaussians.jbgs_ply_extra = self.ply_columns   # r7-5
        if int(getattr(args, "jbgs_dry_init", 0)):    # r7-6
            self.dry_init_report(gaussians)
            raise SystemExit(0)

    # ------------------------------------------------------------------------------------------- bookkeeping
    def _wrap_counters(self, gaussians):
        orig_postfix = gaussians.densification_postfix
        orig_prune = gaussians.prune_points
        me = self

        def postfix(*a, **k):
            before = gaussians.get_xyz.shape[0]
            r = orig_postfix(*a, **k)
            me.counters["added"] += gaussians.get_xyz.shape[0] - before
            me._rows_append(gaussians.get_xyz.shape[0] - before)      # r7: new rows get no E / judgment until the next read
            return r

        def prune(*a, **k):
            before = gaussians.get_xyz.shape[0]
            mask = a[0] if a else k.get("mask")
            r = orig_prune(*a, **k)
            me.counters["removed"] += before - gaussians.get_xyz.shape[0]
            if mask is not None:
                me._rows_keep(~mask)                                   # r7: per-row records follow the pruning
            return r

        gaussians.densification_postfix = postfix
        gaussians.prune_points = prune

    ROWS = ("E", "E_cnt", "g_J", "g_loc", "g_located", "_g_surface")
    FILL = {"E": float("nan"), "E_cnt": 0.0, "g_J": -1, "g_loc": -1, "g_located": False, "_g_surface": -1}

    def _rows_append(self, k):
        for name in self.ROWS:
            t = getattr(self, name, None)
            if t is not None and k > 0:
                setattr(self, name, torch.cat([t, torch.full((k,), self.FILL[name], dtype=t.dtype, device=t.device)]))

    def _rows_keep(self, keep):
        for name in self.ROWS:
            t = getattr(self, name, None)
            if t is not None and t.shape[0] == keep.shape[0]:
                setattr(self, name, t[keep])

    # ---------------------------------------------------------------------------------------- r7 propagation
    @torch.no_grad()
    def prop_init(self, args, gaussians):
        """r7-1. Loads the stage-1 product, propagates with the configured values, seats every prior point, plants.
        Returns the compact surface index of every kept point (-1: image point or prior point without a location)."""
        if ppl is None:
            raise RuntimeError("src/phd/prior_propagation_v1 is not importable from the fork root")
        t0 = time.time()
        st = ppl.load_store(args.jbgs_prop_store)
        tag = args.jbgs_prop_tau_variant
        state, vote, E0 = st[f"state_{tag}"], st[f"vote_{tag}"], st[f"E_{tag}"]
        J, (mis, kd, kv) = ppl.propagate(st, state, vote, args.jbgs_prop_majority, args.jbgs_prop_min_evidence, args.jbgs_prop_max_distance)
        J_loc = ppl.location_judgment(state, vote, J)
        dev = "cuda"
        P = dict(store=st, st_t=pps.to_torch(st, dev), state=torch.as_tensor(state, device=dev).long(),
                 vote=torch.as_tensor(vote, device=dev).long(), E0=torch.as_tensor(E0, device=dev).float(),
                 J=torch.as_tensor(J, device=dev).long(), J_loc=torch.as_tensor(J_loc, device=dev).long(), prop_seconds=time.time() - t0)
        self.prop = P
        seat = torch.as_tensor(np.load(args.jbgs_seat_path), device=dev).long()
        xyz = gaussians.get_xyz.detach()
        n = xyz.shape[0]
        if seat.shape[0] != n:
            raise ValueError(f"seat surfaces {seat.shape[0]} != initial points {n}")
        prior = gaussians.origin == ORIGIN_PRIOR
        has = prior & (seat >= 0)
        loc = torch.full((n,), -1, dtype=torch.long, device=dev)
        loc[has] = pps.seat(P["st_t"], seat[has], xyz[has])
        stt = torch.full((n,), -1, dtype=torch.long, device=dev); stt[has] = P["state"][loc[has]]
        Jt = torch.full((n,), ppr.J_NONE, dtype=torch.long, device=dev); Jt[has] = P["J"][loc[has]]
        Eloc = torch.full((n,), float("nan"), device=dev); Eloc[has] = P["E0"][loc[has]]
        E_old, cnt = compute_E(xyz, self.train_cams, self.A, self.P, args.jbgs_e_depth_tol)   # r6 rule (points without a location)
        drop_inv = has & (stt == ppr.ST_INVISIBLE)
        conflict = has & (stt == ppr.ST_MISSING) & (Jt == ppr.J_CONFLICT)
        drop_conf = conflict & (int(args.jbgs_init_plant_conflict) == 0)
        noloc = prior & ~has
        drop_unseen = noloc & (cnt == 0)
        drop = drop_inv | drop_conf | drop_unseen
        reason = torch.zeros(n, dtype=torch.int8, device=dev)
        reason[drop_inv] = 1; reason[drop_conf] = 2; reason[drop_unseen] = 3
        ext = P["st_t"]["surf_ext"]
        surf_ext = torch.full((n,), -1, dtype=torch.long, device=dev); surf_ext[has] = ext[seat[has]]
        np.savez_compressed(self.mon / "unplanted.npz", xyz=xyz[drop].cpu().numpy().astype(np.float32),
                            surface=surf_ext[drop].cpu().numpy(), location=loc[drop].cpu().numpy(), reason=reason[drop].cpu().numpy(),
                            reason_codes=np.array(["kept", "invisible location", "missing location with propagated conflict",
                                                   "no location and no training view sees the centre (r6 rule)"]))
        E_first = torch.where(has, Eloc, E_old)
        np.savez_compressed(self.mon / "init_points.npz", xyz=xyz.cpu().numpy().astype(np.float32), origin=gaussians.origin.cpu().numpy(),
                            seat=seat.cpu().numpy(), surface=surf_ext.cpu().numpy(), location=loc.cpu().numpy(), state=stt.cpu().numpy(),
                            judgment=Jt.cpu().numpy(), E_first=E_first.cpu().numpy(), E_centre_prior_depth=E_old.cpu().numpy(),
                            n_seeing_centre=cnt.cpu().numpy().astype(np.int16), planted=(~drop).cpu().numpy(), reason=reason.cpu().numpy())
        info = dict(applied=True, rule="r7: prior point dropped iff its location is invisible, or missing with a propagated "
                    "conflict (unless jbgs_init_plant_conflict), or it has no location and no training view sees its centre",
                    store=str(args.jbgs_prop_store), tau_variant=tag, majority=args.jbgs_prop_majority,
                    min_evidence=args.jbgs_prop_min_evidence, max_distance=args.jbgs_prop_max_distance,
                    plant_conflict=int(args.jbgs_init_plant_conflict), prop_seconds=round(P["prop_seconds"], 2),
                    n_locations=int(len(state)), n_support=int((state == ppr.ST_SUPPORT).sum()),
                    n_missing=int((state == ppr.ST_MISSING).sum()), n_invisible=int((state == ppr.ST_INVISIBLE).sum()),
                    missing_judgments={ppr.J_NAMES[j]: int((J[state == ppr.ST_MISSING] == j).sum()) for j in ppr.J_NAMES},
                    n_before=int(n), n_prior_before=int(prior.sum()), n_prior_located=int(has.sum()), n_prior_without_location=int(noloc.sum()),
                    n_dropped_invisible=int(drop_inv.sum()), n_conflict_points=int(conflict.sum()), n_dropped_conflict=int(drop_conf.sum()),
                    n_dropped_without_location_unseen=int(drop_unseen.sum()), n_prior_kept=int((prior & ~drop).sum()),
                    n_image=int((~prior).sum()))
        self.init_filter = info
        print(f"[jbgs_judgment] r7 init: prior {info['n_prior_before']} (located {info['n_prior_located']}) -> kept {info['n_prior_kept']}; "
              f"dropped invisible {info['n_dropped_invisible']}, conflict {info['n_dropped_conflict']}, no location unseen "
              f"{info['n_dropped_without_location_unseen']}; missing judgments {info['missing_judgments']}")
        self._gate_init(args)
        if bool(drop.any()):
            gaussians.prune_points(drop)
        return seat[~drop].clone()

    @torch.no_grad()
    def _gate_init(self, args):
        """r7-4: per training view, 0 where the pixel's prior-surface location carries a propagated conflict (or, for the
        'location' variant, a support location's conflict vote), 1 elsewhere; decided once."""
        self.GATE = {}
        self.gate_counts = {}
        if args.jbgs_prior_gate == "off" or not args.jbgs_locmap_dir:
            return
        Jg = self.prop["J"] if args.jbgs_prior_gate == "propagated" else self.prop["J_loc"]
        LM = _load_set(Path(args.jbgs_locmap_dir), sorted(self.train_names), self.size, "cuda", dtype=np.int32)
        for name, lm in LM.items():
            lm = lm.long()
            g = torch.ones(lm.shape, device="cuda")
            ok = lm >= 0
            g[ok] = (Jg[lm[ok]] != ppr.J_CONFLICT).float()
            self.GATE[name] = g
            P = self.P.get(name); A = self.A.get(name)
            if P is not None and A is not None:
                w = torch.isfinite(P) & (P > 0) & (A < 0.5)
                self.gate_counts[name] = dict(prior_term_px=int(w.sum()), on=int((w & (g > 0)).sum()), off_conflict=int((w & (g == 0)).sum()),
                                              located_px=int((w & ok).sum()))

    @torch.no_grad()
    def seat_now(self, gaussians):
        """r7-2: (located mask, compact surface, location) of every Gaussian at its current centre."""
        P = self.prop
        n = gaussians.get_xyz.shape[0]
        ids = gaussians.init_id.long()
        s = torch.full((n,), -1, dtype=torch.long, device="cuda")
        ok = ids >= 0
        s[ok] = self.init_surface[ids[ok]]
        located = (gaussians.origin == ORIGIN_PRIOR) & (s >= 0)
        loc = torch.full((n,), -1, dtype=torch.long, device="cuda")
        if bool(located.any()):
            loc[located] = pps.seat(P["st_t"], s[located], gaussians.get_xyz[located].detach())
        return located, s, loc

    @torch.no_grad()
    def sampled_E(self, loc_ids, D_maps, AL_maps):
        smp = pps.cell_samples(self.prop["st_t"], loc_ids, int(self.args.jbgs_reread_samples))
        return pps.reread_E(smp, self.train_cams, project_points, self.A, D_maps, AL_maps, self.args.jbgs_e_depth_tol,
                            self.args.jbgs_e_alpha_min)

    def ply_columns(self):
        """r7-5: extra PLY columns (int32 / float32, 4-byte fields keep load_ply's strides valid)."""
        if self.prop is None or self.g_located is None:
            return {}
        n = self.g_loc.shape[0]
        ext = torch.full((n,), -1, dtype=torch.long, device="cuda")
        s = self._g_surface_now()
        if s is not None and s.shape[0] == n:
            ok = s >= 0
            ext[ok] = self.prop["st_t"]["surf_ext"][s[ok]]
        return dict(surface_id=ext.cpu().numpy().astype(np.int32), location=self.g_loc.cpu().numpy().astype(np.int32),
                    judgment=self.g_J.cpu().numpy().astype(np.int32), gconf=self.E.cpu().numpy().astype(np.float32))

    def _g_surface_now(self):
        return getattr(self, "_g_surface", None)

    # ------------------------------------------------------------------------------------------------ losses
    def losses(self, cam_name, render_pkg):
        """Returns (mvs_term, prior_term, stats). Both terms are unweighted; multiply by lambdas in train.py.
        r6 (5): with jbgs_depth_norm = pixels both terms divide by the pixel count of the view."""
        D = render_pkg["surf_depth"].squeeze(0)
        zero = torch.zeros((), device=D.device)
        denom = float(D.numel()) if self.args.jbgs_depth_norm == "pixels" else None
        stats = {}
        A = self.A.get(cam_name)
        M = self.M.get(cam_name)
        if A is not None and M is not None:
            mvs, n, hole = weighted_l1(D, M, A, denom)
            stats.update(mvs_n=n, mvs_hole=hole)
        else:
            mvs = zero
        prior = zero
        if self.mode in ("P", "P0"):
            P = self.P.get(cam_name)
            if P is not None:
                if self.mode == "P":
                    w = 1.0 - A
                    gate = getattr(self, "GATE", {}).get(cam_name)   # r7-4: off at propagated-conflict pixels
                    if gate is not None:
                        w = w * gate
                    prior, n, hole, beyond = truncated_prior_loss(D, P, self.TAU[cam_name], w, self.args.jbgs_trunc_hi, denom)
                    stats.update(prior_n=n, prior_hole=hole, prior_beyond=beyond)
                else:
                    prior, n, hole = weighted_l1(D, P, torch.ones_like(P), denom)
                    stats.update(prior_n=n, prior_hole=hole)
        stats.update(n_px=int(D.numel()))
        self.last_stats = stats
        return mvs, prior, stats

    # ---------------------------------------------------------------------------------------- E and locking
    def due_E(self, iteration):
        return self.mode in ("P", "P0") and due_E_iteration(iteration, self.args.jbgs_e_interval)

    @torch.no_grad()
    def render_train_depths(self, gaussians):
        """r6 (1): expected depth (surf_depth, the depth the losses use) and accumulated opacity of the training views."""
        D, AL = {}, {}
        for cam in self.train_cams:
            pkg = self.render_fn(cam, gaussians, self.pipe, self.background)
            D[cam.image_name] = pkg["surf_depth"].squeeze(0).detach()
            AL[cam.image_name] = pkg["rend_alpha"].squeeze(0).detach()
        return D, AL

    @torch.no_grad()
    def floor_now(self, gaussians):
        """r6 (3): opacity floor on the protected disks at the moment the protection mask is set."""
        if self.mode != "P" or gaussians.frozen_mask is None or not bool(gaussians.frozen_mask.any()):
            return
        op = gaussians._opacity
        floor = gaussians.inverse_opacity_activation(torch.tensor(self.args.jbgs_lock_opacity_floor, device=op.device))
        m = gaussians.frozen_mask
        op.data[m] = torch.clamp(op.data[m], min=float(floor))

    @torch.no_grad()
    def update_E(self, iteration, gaussians):
        if self.prop is not None:
            return self.update_E_r7(iteration, gaussians)
        a = self.args
        xyz = gaussians.get_xyz
        extra = {}
        if self.E_calls == 0 or self.render_fn is None:          # r6 (1): first computation, the scene is the prior
            E, cnt = compute_E(xyz, self.train_cams, self.A, self.P, a.jbgs_e_depth_tol)
            how = "prior_depth"
        else:                                                     # later: the current render is the scene
            Dm, ALm = self.render_train_depths(gaussians)
            E, cnt, n_empty = compute_E_render(xyz, self.train_cams, self.A, Dm, ALm, a.jbgs_e_depth_tol, a.jbgs_e_alpha_min)
            how = "render_depth"
            extra["n_empty_pairs"] = int(n_empty)
            self.last_maps = (Dm, ALm) if self.keep_maps else None
            del Dm, ALm
        self.E_calls += 1
        self.E, self.E_cnt, self.E_how = E, cnt, how
        prior = gaussians.origin == ORIGIN_PRIOR
        prev = gaussians.frozen_mask.clone() if gaussians.frozen_mask is not None else torch.zeros_like(prior)
        ids = gaussians.init_id.long()
        drift = torch.full_like(E, float("nan"))
        has = ids >= 0
        drift[has] = (xyz[has] - self.init_xyz[ids[has]]).norm(dim=1)
        lock, far = lock_rule_r6(E, drift, prior, a.jbgs_e_threshold, self.lock_drift_max)
        if self.mode == "P":
            gaussians.set_frozen_mask(lock)
            self.floor_now(gaussians)                             # r6 (3)
        else:
            lock = torch.zeros_like(prior)
        newly, released = lock & ~prev, prev & ~lock
        released_far = released & far
        self.last_update = dict(iteration=iteration, prev=prev, lock=lock, far=far, drift=drift)
        hist_p = torch.histc(E[prior].float(), bins=10, min=0.0, max=1.0).tolist() if prior.any() else [0] * 10
        hist_i = torch.histc(E[~prior].float(), bins=10, min=0.0, max=1.0).tolist() if (~prior).any() else [0] * 10

        def q(x):
            if x.numel() == 0:
                return None
            x = x.float()
            return [float(v) for v in torch.quantile(x, torch.tensor([0.1, 0.5, 0.9], device=x.device))] + [float(x.max())]
        row = dict(iteration=iteration, revision=REVISION, how=how, n=int(xyz.shape[0]), n_prior=int(prior.sum()),
                   n_prior_unseen=int((prior & (cnt == 0)).sum()), n_image_unseen=int((~prior & (cnt == 0)).sum()),
                   n_prior_far=int(far.sum()), lock_drift_max=self.lock_drift_max,
                   prior_drift_q=[float(v) for v in torch.nanquantile(drift[prior].float(), torch.tensor([0.5, 0.9, 0.99], device=drift.device))] if prior.any() else None,
                   E_hist_prior=hist_p, E_hist_image=hist_i, E_mean_prior=float(E[prior].mean()) if prior.any() else None,
                   n_locked=int(lock.sum()), n_newly_locked=int(newly.sum()), n_released=int(released.sum()),
                   n_released_far=int(released_far.sum()), newly_drift_q=q(drift[newly]), locked_drift_q=q(drift[lock]), **extra)
        with (self.mon / "E.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        if self.tb is not None:
            self.tb.add_scalar("judgment/n_locked", row["n_locked"], iteration)
            self.tb.add_scalar("judgment/n_prior_unseen", row["n_prior_unseen"], iteration)
            self.tb.add_scalar("judgment/n_prior_far", row["n_prior_far"], iteration)
            if row["E_mean_prior"] is not None:
                self.tb.add_scalar("judgment/E_mean_prior", row["E_mean_prior"], iteration)
        print(f"[jbgs_judgment] iter {iteration}: E ({how}) prior={row['n_prior']} locked={row['n_locked']} "
              f"(+{row['n_newly_locked']}/-{row['n_released']}, released by distance {row['n_released_far']}) "
              f"unseen prior={row['n_prior_unseen']} far (E<thr, drift>{self.lock_drift_max:.3f} m, not locked)={row['n_prior_far']}")

    @torch.no_grad()
    def update_E_r7(self, iteration, gaussians):
        """r7-2 / r7-3. First call: E of a located prior Gaussian = its location's E from the product (occlusion by the
        prior render); later calls: E of the occupied cells re-measured with the current render (one-sided occlusion).
        Gaussians without a location (image origin, TIN ground points) keep the r6 E of the centre pixel.
        Protection = prior origin & judgment != conflict & E < threshold & drift <= mult x tau of the surface kind."""
        a = self.args
        xyz = gaussians.get_xyz.detach()
        n = xyz.shape[0]
        located, s, loc = self.seat_now(gaussians)
        E = torch.zeros(n, device="cuda"); extra = {}
        if self.E_calls == 0 or self.render_fn is None:
            E_old, cnt = compute_E(xyz, self.train_cams, self.A, self.P, a.jbgs_e_depth_tol)
            E[:] = E_old
            E[located] = self.prop["E0"][loc[located]]
            how = "location E of the product (prior render); centre pixel with the prior depth where no location"
        else:
            Dm, ALm = self.render_train_depths(gaussians)
            E_old, cnt, n_empty = compute_E_render(xyz, self.train_cams, self.A, Dm, ALm, a.jbgs_e_depth_tol, a.jbgs_e_alpha_min)
            E[:] = E_old
            if bool(located.any()):
                u, inv = torch.unique(loc[located], return_inverse=True)
                Eu, _, _ = self.sampled_E(u, Dm, ALm)
                E[located] = Eu[inv]
                extra["n_cells_read"] = int(u.numel())
            how = "cells re-measured with the current render; centre pixel with the current render where no location"
            extra["n_empty_pairs"] = int(n_empty)
            self.last_maps = (Dm, ALm) if self.keep_maps else None
            del Dm, ALm
        self.E_calls += 1
        Jn = torch.full((n,), ppr.J_NONE, dtype=torch.long, device="cuda")
        Jn[located] = self.prop["J"][loc[located]]
        prior = gaussians.origin == ORIGIN_PRIOR
        prev = gaussians.frozen_mask.clone() if gaussians.frozen_mask is not None else torch.zeros_like(prior)
        ids = gaussians.init_id.long()
        drift = torch.full((n,), float("nan"), device="cuda")
        has = ids >= 0
        drift[has] = (xyz[has] - self.init_xyz[ids[has]]).norm(dim=1)
        kind = torch.full((n,), 1, dtype=torch.long, device="cuda")
        kind[located] = self.prop["st_t"]["surf_kind"][s[located]].long()
        dmax = torch.where(kind == 2, torch.tensor(self.tau_kind[2], device="cuda"), torch.tensor(self.tau_kind[1], device="cuda"))
        dmax = dmax * float(a.jbgs_lock_drift_tau_mult)
        near = torch.isfinite(drift) & (drift <= dmax)
        low = prior & (E < a.jbgs_e_threshold)
        conflict = Jn == ppr.J_CONFLICT
        lock = low & near & ~conflict
        far = low & ~near
        if self.mode == "P":
            gaussians.set_frozen_mask(lock)
            self.floor_now(gaussians)
        else:
            lock = torch.zeros_like(prior)
        self.E, self.E_cnt, self.E_how = E, cnt.float(), how
        self.g_J, self.g_loc, self.g_located, self._g_surface = Jn, loc, located, s
        newly, released = lock & ~prev, prev & ~lock
        self.last_update = dict(iteration=iteration, prev=prev, lock=lock, far=far, drift=drift, conflict=conflict, located=located, loc=loc)
        hist_p = torch.histc(E[prior].float(), bins=10, min=0.0, max=1.0).tolist() if prior.any() else [0] * 10
        row = dict(iteration=iteration, revision=REVISION, how=how, n=int(n), n_prior=int(prior.sum()), n_located=int(located.sum()),
                   n_prior_without_location=int((prior & ~located).sum()), n_prior_E_below=int(low.sum()),
                   n_conflict_excluded=int((low & near & conflict).sum()), n_prior_far=int(far.sum()),
                   judgments_located={ppr.J_NAMES.get(j, "none"): int(((Jn == j) & located).sum()) for j in (-1, 0, 1, 2, 3)},
                   E_hist_prior=hist_p, n_locked=int(lock.sum()), n_newly_locked=int(newly.sum()), n_released=int(released.sum()),
                   drift_bound_roof=float(self.tau_kind[1] * a.jbgs_lock_drift_tau_mult),
                   drift_bound_wall=float(self.tau_kind[2] * a.jbgs_lock_drift_tau_mult), **extra)
        with (self.mon / "E.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        if self.tb is not None:
            self.tb.add_scalar("judgment/n_locked", row["n_locked"], iteration)
            self.tb.add_scalar("judgment/n_conflict_excluded", row["n_conflict_excluded"], iteration)
        print(f"[jbgs_judgment] iter {iteration}: E r7 ({how}) prior={row['n_prior']} located={row['n_located']} locked={row['n_locked']} "
              f"(conflict excluded {row['n_conflict_excluded']}, far {row['n_prior_far']})")
        return row

    @torch.no_grad()
    def dry_init_report(self, gaussians):
        """r7-6: the values right before the first iteration, without training."""
        row = self.update_E(1, gaussians)
        rep = dict(revision=REVISION, init=self.init_filter, first_E=row)
        if self.prop is not None:
            located = self.g_located
            prior = gaussians.origin == ORIGIN_PRIOR
            # E of the re-read method (cell samples) with the prior depth as the occluder, against the product's E
            if bool(located.any()):
                u, inv = torch.unique(self.g_loc[located], return_inverse=True)
                D = {k: torch.where(torch.isfinite(v), v, torch.zeros_like(v)) for k, v in self.P.items()}
                AL = {k: torch.isfinite(v).float() for k, v in self.P.items()}
                Es, ns, nsp = self.sampled_E(u, D, AL)
                E0 = self.prop["E0"][u]
                rep["reread_method_vs_product_E"] = dict(n_cells=int(u.numel()), mean_abs_diff=float((Es - E0).abs().mean()),
                                                         same_side_of_threshold=float(((Es < 0.5) == (E0 < 0.5)).float().mean()),
                                                         n_product_below=int((E0 < 0.5).sum()), n_sampled_below=int((Es < 0.5).sum()))
            gc = getattr(self, "gate_counts", {})
            rep["prior_gate"] = dict(rule=self.args.jbgs_prior_gate, per_view=gc,
                                     prior_term_px=sum(v["prior_term_px"] for v in gc.values()), on=sum(v["on"] for v in gc.values()),
                                     off_conflict=sum(v["off_conflict"] for v in gc.values()))
            lk = gaussians.frozen_mask
            rep["protection"] = dict(n_protected=int(lk.sum()) if lk is not None else 0, n_conflict_excluded=row["n_conflict_excluded"],
                                     n_prior=int(prior.sum()), n_located=int(located.sum()))
        if int(self.args.jbgs_dry_init) == 2 and self.prop is not None:
            # evidence for the offline check: the fork's propagated judgments and its prior-term gates (training resolution)
            LM = _load_set(Path(self.args.jbgs_locmap_dir), sorted(self.train_names), self.size, "cpu", dtype=np.int32) if self.args.jbgs_locmap_dir else {}
            np.savez_compressed(self.mon / "gate_check.npz", J=self.prop["J"].cpu().numpy(), J_loc=self.prop["J_loc"].cpu().numpy(),
                                **{f"lm_{k}": v.numpy() for k, v in LM.items()},
                                **{f"gate_{k}": (v > 0).cpu().numpy() for k, v in getattr(self, "GATE", {}).items()})
            rep["reread_test"] = self.reread_test(gaussians)
        (self.mon / "init_report.json").write_text(json.dumps(rep, indent=1, default=float))
        print(f"[jbgs_judgment] r7 dry init report written: {self.mon / 'init_report.json'}")

    @torch.no_grad()
    def reread_test(self, gaussians):
        """r7 test (dry_init 2, no training): move located prior Gaussians a little -- one cell along t1, a tenth of a cell
        along t2, 0.3 m along the surface normal -- and re-read with the renderer. The surface must stay, the cell may
        change, and the values read must be those of the new cell: the judgment of the initial table and E re-measured
        for that cell with the same render. The locations are also found again with numpy on the CPU."""
        located0 = self.g_located.clone(); s0 = self._g_surface.clone(); loc0 = self.g_loc.clone()
        idx = torch.nonzero(located0).squeeze(1)
        if idx.numel() == 0:
            return dict(skipped="no located Gaussians")
        gen = torch.Generator(device="cuda"); gen.manual_seed(0)
        perm = idx[torch.randperm(idx.numel(), generator=gen, device="cuda")]
        k = perm.numel() // 3
        groups = {"one_cell_along_t1": perm[:k], "tenth_cell_along_t2": perm[k:2 * k], "normal_0.3m": perm[2 * k:]}
        st = self.prop["st_t"]; sp = st["sp"]
        xyz = gaussians._xyz.data
        orig = xyz.clone()
        t1 = st["loc_t1"][loc0[groups["one_cell_along_t1"]]]
        t2 = st["loc_t2"][loc0[groups["tenth_cell_along_t2"]]]
        a1 = st["loc_t1"][loc0[groups["normal_0.3m"]]]; a2 = st["loc_t2"][loc0[groups["normal_0.3m"]]]
        nn = torch.cross(a1, a2, dim=1); nn = nn / nn.norm(dim=1, keepdim=True).clamp_min(1e-12)
        xyz[groups["one_cell_along_t1"]] += (sp * t1).float()
        xyz[groups["tenth_cell_along_t2"]] += (0.1 * sp * t2).float()
        xyz[groups["normal_0.3m"]] += (0.3 * nn).float()
        self.keep_maps = True
        self.update_E(2, gaussians)
        Dm, ALm = self.last_maps
        loc1 = self.g_loc
        u, inv = torch.unique(loc1[idx], return_inverse=True)
        Eu, _, _ = self.sampled_E(u, Dm, ALm)
        np_loc = ppl.locate(self.prop["store"], s0[idx].cpu().numpy(), xyz[idx].double().cpu().numpy())
        out = dict(n_moved=int(idx.numel()),
                   surface_unchanged=bool((self._g_surface[idx] == s0[idx]).all()),
                   still_located=bool(self.g_located[idx].all()),
                   cell_changed_share={g: float((loc1[ix] != loc0[ix]).float().mean()) for g, ix in groups.items()},
                   judgment_equals_table_of_new_cell=bool((self.g_J[idx] == self.prop["J"][loc1[idx]]).all()),
                   E_equals_cell_re_measure_max_abs_diff=float((self.E[idx] - Eu[inv]).abs().max()),
                   cpu_numpy_locate_disagreements=int((torch.as_tensor(np_loc, device="cuda") != loc1[idx]).sum()),
                   n_cells_after=int(u.numel()))
        dis = torch.as_tensor(np_loc, device="cuda") != loc1[idx]
        rows = []
        if bool(dis.any()):   # record where the GPU and the CPU lookups differ: position in cell units on the surface's grid
            stn = self.prop["store"]; sp_ = float(stn["sp"])
            for j in torch.nonzero(dis).squeeze(1)[:20].tolist():
                g_ = int(idx[j]); sj = int(s0[g_]); X = xyz[g_].double().cpu().numpy()
                d_ = X - stn["o"][sj]
                uu = float((d_ * stn["e1"][sj]).sum() / sp_); vv = float((d_ * stn["e2"][sj]).sum() / sp_)
                rows.append(dict(gaussian=g_, surface=int(stn["surf_ext"][sj]), loc_gpu=int(loc1[g_]), loc_cpu=int(np_loc[j]), u=uu, v=vv,
                                 dist_to_cell_edge=float(min(abs(uu - round(uu)), abs(vv - round(vv))))))
        out["disagreements"] = rows
        on_edge = all(r["dist_to_cell_edge"] < 1e-6 for r in rows)
        out["cpu_numpy_locate_agreement"] = 1.0 - out["cpu_numpy_locate_disagreements"] / float(idx.numel())   # exact count, float64
        out["passed"] = bool(out["surface_unchanged"] and out["still_located"] and out["judgment_equals_table_of_new_cell"]
                             and out["E_equals_cell_re_measure_max_abs_diff"] == 0.0
                             and (out["cpu_numpy_locate_disagreements"] == 0 or on_edge))
        xyz.copy_(orig)
        print(f"[jbgs_judgment] r7 re-read test: {out}")
        return out

    @torch.no_grad()
    def before_step(self, gaussians):
        """Remember the locked rows of xyz/rotation/scaling right before optimizer.step()."""
        self._saved = None
        if self.mode != "P" or gaussians.frozen_mask is None or not bool(gaussians.frozen_mask.any()):
            return
        m = gaussians.frozen_mask.clone()
        self._saved = (m, {name: getattr(gaussians, name).detach()[m].clone() for name in ("_xyz", "_rotation", "_scaling")})

    @torch.no_grad()
    def after_step(self, gaussians):
        """Locked disks: keep lock_lr_scale of the Adam step on xyz/rotation/scaling, then the opacity floor."""
        if self._saved is not None:
            m, rows = self._saved
            self._saved = None
            if m.shape[0] == gaussians.get_xyz.shape[0]:
                for name, old in rows.items():
                    scale_locked_update(getattr(gaussians, name), old, m, float(self.args.jbgs_lock_lr_scale))
        if self.mode != "P" or gaussians.frozen_mask is None or not bool(gaussians.frozen_mask.any()):
            return
        floor = gaussians.inverse_opacity_activation(torch.tensor(self.args.jbgs_lock_opacity_floor, device="cuda"))
        m = gaussians.frozen_mask
        gaussians._opacity.data[m] = torch.clamp(gaussians._opacity.data[m], min=float(floor))

    def exempt_mask(self, gaussians):
        """Mask passed to reset_opacity: locked disks keep their opacity."""
        if self.mode != "P":
            return None
        return gaussians.frozen_mask

    # ------------------------------------------------------------------------------------------- monitoring
    @torch.no_grad()
    def mark_alive(self, iteration, gaussians):
        ids = gaussians.init_id
        ids = ids[ids >= 0].long()
        if ids.numel():
            self.last_seen[ids] = int(iteration)

    def log_scalars(self, iteration, terms, gaussians):
        self.mark_alive(iteration, gaussians)
        bad = {k: float(v) for k, v in terms.items() if not math.isfinite(float(v))}
        if bad:  # ORDER section 7 'always: loss terms finite' -> red, stop the run
            with (self.mon / "checklist.jsonl").open("a") as f:
                f.write(json.dumps(dict(iteration=iteration, items=[dict(name="loss_terms_finite", status="red", binding=True,
                                                                            value=str(bad), rule="all loss terms finite")])) + "\n")
            raise RuntimeError(f"[jbgs_judgment] non-finite loss terms at iteration {iteration}: {bad}")
        prior = gaussians.origin == ORIGIN_PRIOR
        lock = gaussians.frozen_mask if gaussians.frozen_mask is not None else torch.zeros_like(prior)
        op = gaussians.get_opacity.squeeze(-1)

        def q(mask):
            if not bool(mask.any()):
                return None
            x = op[mask].float()
            return [float(v) for v in torch.quantile(x, torch.tensor([0.1, 0.5, 0.9], device=x.device))]
        row = dict(iteration=iteration, elapsed=time.monotonic() - self.started, n=int(prior.shape[0]),
                   n_prior=int(prior.sum()), n_image=int((~prior).sum()), n_locked=int(lock.sum()),
                   n_prior_free=int((prior & ~lock).sum()), added=self.counters["added"], removed=self.counters["removed"],
                   opacity_q_prior=q(prior), opacity_q_image=q(~prior), opacity_q_locked=q(lock),
                   n_locked_below_floor=int((lock & (op < self.args.jbgs_lock_opacity_floor - 1e-3)).sum()),
                   peak_cuda_gb=torch.cuda.max_memory_allocated() / 1e9, **{k: float(v) for k, v in terms.items()},
                   **{f"px_{k}": v for k, v in self.last_stats.items()})
        self.counters = {"added": 0, "removed": 0}
        self.scalars.write(json.dumps(row) + "\n")
        if self.tb is not None:
            for k, v in terms.items():
                self.tb.add_scalar(f"terms/{k}", float(v), iteration)
            for k in ("n", "n_prior", "n_image", "n_locked", "n_prior_free", "added", "removed", "n_locked_below_floor"):
                self.tb.add_scalar(f"disks/{k}", row[k], iteration)
            for k in ("opacity_q_prior", "opacity_q_image", "opacity_q_locked"):
                if row[k] is not None:
                    self.tb.add_scalar(f"opacity/{k}_median", row[k][1], iteration)

    # --------------------------------------------------------------------------------------------- read-outs
    @torch.no_grad()
    def readout(self, iteration, gaussians, render, pipe, background, snapshot=False, dump=False, stop_check=True):
        records = {}
        faces_all = set(self.faces_roof) | set(self.faces_wall)
        dump_dir = self.model_path / "dump" / f"iteration_{iteration}"
        if dump:
            dump_dir.mkdir(parents=True, exist_ok=True)
        lock = gaussians.frozen_mask
        for cam in self.all_cams:
            name = cam.image_name
            pkg = render(cam, gaussians, pipe, background)
            D = pkg["surf_depth"].squeeze(0)
            alpha = pkg["rend_alpha"].squeeze(0)
            rendered = torch.isfinite(D) & (D > 0)
            A = self.A.get(name)
            M = self.M.get(name)
            P = self.P.get(name)
            F = self.FACE.get(name)
            fv = self.FV.get(name)
            G = self.G.get(name)
            if F is not None and fv is not None:
                Fc = F.cuda(); fvc = fv.cuda()
                Gc = G.cuda() if G is not None else None
                for f in faces_all:
                    fm = Fc == f
                    if not bool(fm.any()):
                        continue
                    r = records.setdefault(f, dict(d=[], e=[], g=[], d_all=[], n_pixels=0, n_A=0))
                    r["n_pixels"] += int(fm.sum())
                    a1 = fm & (A > 0) if A is not None else torch.zeros_like(fm)
                    r["n_A"] += int(a1.sum())
                    if P is not None:
                        pm = fm & rendered & torch.isfinite(P) & (P > 0)
                        r["d_all"].append(((D - P) * fvc)[pm].cpu())
                        r["d"].append(((D - P) * fvc)[pm & a1].cpu())
                    if M is not None:
                        em = a1 & rendered & torch.isfinite(M) & (M > 0)
                        r["e"].append(((D - M) * fvc)[em].cpu())
                    if Gc is not None:
                        gm = fm & rendered & torch.isfinite(Gc) & (Gc > 0)
                        r["g"].append(((D - Gc) * fvc)[gm].cpu())
            if dump:  # float32: float16 spacing at 44 m is 3.1 cm, the size of tau
                np.save(dump_dir / f"{name}_depth.npy", D.cpu().numpy().astype(np.float32))
                np.save(dump_dir / f"{name}_alpha.npy", alpha.cpu().numpy().astype(np.float16))
                rgb = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
                cv2.imwrite(str(dump_dir / f"{name}_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if snapshot and name in set(self.args.jbgs_monitor_views):
                self._snapshot(iteration, cam, pkg, D, gaussians, lock)
        rows = face_readout(records, self.tau_v, self.faces_roof, self.faces_wall)
        if not stop_check:  # evidence pass of a stopping read-out: files only, no second record
            if dump:
                self.dump_gaussians(iteration, gaussians, dump_dir)
            return rows
        (self.mon / f"faces_{iteration}.json").write_text(json.dumps(rows, indent=1))
        with self.faces_csv.open("a") as f:
            for r in rows:
                f.write(",".join(str(r[k]) for k in ["face", "n_pixels", "n_A", "cov", "d", "d_nmad", "n_d", "d_all",
                                                     "d_all_nmad", "n_d_all", "e", "e_nmad", "n_e", "g", "g_nmad",
                                                     "n_g", "label"]).join([f"{iteration},", "\n"]))
        if self.tb is not None:
            for r in rows:
                for k in ("d", "e", "g", "cov"):
                    if r[k] == r[k]:
                        self.tb.add_scalar(f"faces/{r['face']}_{k}", r[k], iteration)
        if dump:
            self.dump_gaussians(iteration, gaussians, dump_dir)
        check = self.checklist(iteration, rows)
        summary = {r["face"]: (round(r["d"], 4) if r["d"] == r["d"] else None, r["label"]) for r in rows}
        print(f"[jbgs_judgment] iter {iteration} read-out: {summary}")
        red = [it for it in check["items"] if it["binding"] and it["status"] == "red"]
        if red and stop_check and self.args.jbgs_stop_on_red:  # ORDER 7: stop, keep the evidence, record the cause
            if not dump:
                self.readout(iteration, gaussians, render, pipe, background, snapshot=True, dump=True, stop_check=False)
            gaussians.save_ply(str(self.model_path / "point_cloud" / f"iteration_{iteration}_stopped" / "point_cloud.ply"))
            with (self.mon / "stop.json").open("w") as f:
                json.dump(dict(iteration=iteration, red=red, scientific_verdict=None), f, indent=1)
            raise RuntimeError(f"[jbgs_judgment] red binding check at iteration {iteration}: {red}")
        return rows

    @torch.no_grad()
    def dump_gaussians(self, iteration, gaussians, dump_dir):
        """Disk records (ORDER 4.5): origin, E at the last update (NaN for disks born after it), opacity, lock,
        init_id and displacement from the initial disk; per initial disk: origin, position and last alive iteration
        (a disk id not alive now was removed between last_seen and last_seen + log interval)."""
        self.mark_alive(iteration, gaussians)
        prior = gaussians.origin == ORIGIN_PRIOR
        n = prior.shape[0]
        E = self.E if (self.E is not None and self.E.shape[0] == n) else torch.full((n,), float("nan"), device=prior.device)
        cnt = self.E_cnt if (self.E_cnt is not None and self.E_cnt.shape[0] == n) else torch.zeros_like(E)
        ids = gaussians.init_id.long()
        disp = torch.full((n, 3), float("nan"), device=prior.device)
        ok = ids >= 0
        disp[ok] = gaussians.get_xyz[ok] - self.init_xyz[ids[ok]]
        np.savez(dump_dir / "gaussians.npz", iteration=iteration, xyz=gaussians.get_xyz.cpu().numpy(),
                 origin=gaussians.origin.cpu().numpy(), init_id=gaussians.init_id.cpu().numpy(), displacement=disp.cpu().numpy(),
                 E=E.cpu().numpy(), E_cnt=cnt.cpu().numpy(), opacity=gaussians.get_opacity.squeeze(-1).cpu().numpy(),
                 locked=(gaussians.frozen_mask.cpu().numpy() if gaussians.frozen_mask is not None else np.zeros(n, bool)),
                 scale=gaussians.get_scaling.cpu().numpy(), init_xyz=self.init_xyz.cpu().numpy(),
                 init_origin=self.init_origin.cpu().numpy(), init_last_seen=self.last_seen.cpu().numpy(),
                 log_interval=self.args.jbgs_log_interval, revision=REVISION,
                 **({} if self.prop is None or self.g_loc is None or self.g_loc.shape[0] != n else dict(
                     init_surface=self.init_surface.cpu().numpy(),
                     init_surface_ext=np.where(self.init_surface.cpu().numpy() >= 0,
                                               self.prop["store"]["surf_ext"][np.maximum(self.init_surface.cpu().numpy(), 0)], -1),
                     location=self.g_loc.cpu().numpy(), judgment=self.g_J.cpu().numpy(), located=self.g_located.cpu().numpy())))

    @torch.no_grad()
    def _snapshot(self, iteration, cam, pkg, D, gaussians, lock):
        name = cam.image_name
        A = self.A.get(name); M = self.M.get(name); P = self.P.get(name)
        rgb = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        Dn = D.cpu().numpy().astype(np.float32); Dn[Dn <= 0] = np.nan
        panels = [("render", bgr)]
        if P is not None:
            panels.append(("D-P (+/-1.5 m, red: prior above)", colorize_diverging(Dn - P.cpu().numpy(), 1.5)))
        if M is not None:
            panels.append(("D-M (+/-1.5 m, red: MVS above)", colorize_diverging(Dn - M.cpu().numpy(), 1.5)))
        if A is not None:
            ov = bgr.copy(); a = A.cpu().numpy() > 0
            ov[a] = (0.5 * ov[a] + 0.5 * np.array([0, 200, 0])).astype(np.uint8)
            panels.append(("A overlay", ov))
        if lock is not None and bool(lock.any()):  # only locked disks lying on this view's rendered surface
            u, v, z = project_points(gaussians.get_xyz[lock], cam)
            H, W = D.shape
            ui, vi = torch.round(u).long(), torch.round(v).long()
            ok = (z > 0) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
            Dz = D.reshape(-1)[(vi.clamp(0, H - 1) * W + ui.clamp(0, W - 1))]
            vis = ok & (torch.abs(z - Dz) < self.args.jbgs_e_depth_tol)
            lk = bgr.copy()
            for uu, vv in zip(ui[vis].cpu().numpy()[::2], vi[vis].cpu().numpy()[::2]):
                cv2.circle(lk, (int(uu), int(vv)), 1, (0, 0, 255), -1)
            panels.append((f"locked disks visible here {int(vis.sum())} / in frame {int(ok.sum())}", lk))
        raw = dict(depth=Dn.astype(np.float16))
        np.savez_compressed(self.mon / f"snap_{iteration}_{name}.npz", **raw)
        scale = 640 / max(bgr.shape[1], 1)
        tiles = []
        for title, img in panels:
            t = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
            cv2.putText(t, title, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(t, title, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
            tiles.append(t)
        while len(tiles) % 3:
            tiles.append(np.zeros_like(tiles[0]))
        rows = [np.concatenate(tiles[i:i + 3], axis=1) for i in range(0, len(tiles), 3)]
        cv2.imwrite(str(self.mon / f"snap_{iteration}_{name}.png"), np.concatenate(rows, axis=0))

    def checklist(self, iteration, rows):
        """ORDER section 7 automatic red/green checks, written to monitor/checklist.jsonl. The roof rules state the
        intent of the method, so they bind (stop-and-record on red) only in mode P; for the ablations they are
        recorded as information (binding=False). Sign convention: see roof_check."""
        by = {r["face"]: r for r in rows}
        inj = by.get(self.args.jbgs_injected_face)
        tau = self.tau_v
        items = []

        def item(name, status, value, rule, binding):
            items.append(dict(name=name, status=status, value=value, rule=rule, binding=binding))
        if inj is not None and inj["d"] == inj["d"] and not math.isnan(tau):
            name, st, rule = roof_check(self.args.jbgs_scene, iteration, inj["d"], tau, self.args.jbgs_injected_delta)
            item(name, st, inj["d"], rule, self.mode == "P")
        n_und = sum(1 for r in rows if r["face"] != "wall" and r["label"] == "undecided")
        n_roof = sum(1 for r in rows if r["face"] != "wall")
        if n_roof:
            item("undecided_roof_faces", "green" if n_und == 0 else "yellow", n_und, "faces with cov<0.5", False)
        row = dict(iteration=iteration, items=items)
        with (self.mon / "checklist.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row


class NullController:
    """Stands in for jbgs_mvs_pgsr.Controller when the MVS-PGSR environment is not requested."""

    def load_mvs_depth_set(self, all_cameras, target_size, *, train_camera_names):
        return {}

    def geometry_loss(self, camera, render_pkg, gaussians, pipe, background, iteration, *, native_normal_loss):
        return native_normal_loss

    def training_trace(self, **kwargs):
        return None

    def after_backward(self, iteration, gaussians):
        return None
