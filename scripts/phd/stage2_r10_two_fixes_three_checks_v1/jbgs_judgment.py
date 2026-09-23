"""Judgment-guided stage-2 optimization for GeoGS, revision r10 (JointBuildGS PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).

r10 = r9 + records and one option; the losses, g_p, u_i, the fixed values, the re-read, the protection rule and the density
control are r9's, letter for letter (the shared module stays src/phd/prior_propagation_v3).
  (r10-1) order of re-read and opacity reset (fix 'ga', method 4.2 / 4.6 of 2026-10-02): already r9's order -- the re-read
          runs at the start of the iteration (train.py: update_E before the render, due_E_iteration), the reset at its end
          (after the step and the density control) with exempt_mask = the protection that re-read set. No change; added a
          record-only wrapper around reset_opacity (--jbgs_reset_dump_iterations) that saves the state right before and
          right after the reset, and an offline probe (--jbgs_dry_init 3 --jbgs_reset_probe_dir) that loads both states into
          the initialised fork and re-reads them with update_E_r8, per (patch, view) and (Gaussian without a patch, view).
  (r10-2) initial direction, cell method (check 'ra'): --jbgs_prior_normal_mode cell starts a prior-origin Gaussian on a
          patch with the face normal of the cell it first sits in (t1 x t2 of the cell = the face u_i is measured on, the
          unit normal of prop_init), signed like the file normal (outward / up); points without a patch (or on a patch
          without cells) keep the file normal (vertex method). Default 'file' = r9. Both normals are recorded per point.
  (LoD2 party walls, fix 'na': an input change only.)
--- r9 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r9 (JointBuildGS PHD-STAGE2-R9-THREE-FIXES-v1).

r9 = r8 + the three rules the method document changed after the r8 review (2026-10-01, sections 3.1, 4.2, 4.3, 4.5), with
the shared module src/phd/prior_propagation_v3 (v2 + rule.protected, orientation, faces; copied at build time, sha256
checked). Wording: the state a Gaussian carries is the 'patch judgment' (code J_loc / unit_judgment: a support patch's
vote, a missing patch's propagated judgment); 'propagated judgment' is what a missing patch receives (code J).
  (r9-1) protection (eq. 7): G^X = Gaussians whose patch judgment is conflict, support vote or propagated alike
                             (rule.protected); r8 excluded only the propagated conflict. Releases and exclusions are
                             counted separately for support patches voted conflict.
  (r9-2) initial direction : prior-origin Gaussians start with the disk normal = the outward normal of the prior face of
                             their point (--jbgs_prior_normal_path, orientation.quat_from_normal; first tangent axis = the
                             face's horizontal line). Scale, opacity, colour and the image-origin rotation are the base
                             implementation's.
  (r9-3) LoD2 bottom face  : not part of the prior surface -- an input change only (stage-1 products, prior depth and the
                             initial cloud without it); no code here.
  (r9-4) records           : per Gaussian the disk normal, the face normal of its initial disk and the patch state; per
                             initial point the face normal and the normal after orientation.
--- r8 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r8 (JointBuildGS PHD-STAGE2-R8-FOUR-CASES-v1).

r8 = r7 + the 2026-10-01 method document (chapter 4), all rules in the shared module src/phd/prior_propagation_v2
(copied into the fork at build time, sha256 checked). Code name 'location' = prior patch (사전 정보 패치, earlier 판정 단위); A = observation confidence mask (관측 신뢰도 마스크).
  (r8-1) prior-term weight : the prior depth term (eq. 4) is weighted by g_p instead of 1 - c_p. g_p = 0 where the pixel's
                             unit is judged conflict (a support unit's vote or a missing unit's propagated judgment, read
                             alike), 1 where agree or undetermined; a pixel without a unit (TIN ground, steep triangles):
                             1 where c_p = 0, its own mark where c_p = 1 (agree 1, conflict 0). Decided once at
                             initialisation (per-view unit maps + mark maps of the stage-1 product); the MVS term keeps c_p.
  (r8-2) initialisation    : every prior point is planted except those of missing units with a propagated conflict
                             (support units whatever their vote, invisible units and points without a unit are planted).
  (r8-3) Gaussian confidence: unit -> its E (product at initialisation, re-read of the occupied cells later, as r7);
                             no unit -> share of the views seeing the centre (one-sided occlusion: the prior depth at
                             initialisation, the render later) whose centre pixel has c_p = 1; no seeing view -> 0.
  (r8-4) protection (eq. 7): prior origin & propagated judgment not conflict & E < threshold & u <= mult x tau, u measured
                             like the residuals from the initial position over the initial unit's surface (vertical on
                             roof-like, along the normal on wall-like, vertical without a unit), tau of that surface kind
                             (roof tau without a unit). Invisible Gaussians (E = 0) are protected, hence kept through the
                             opacity reset and pruning; the r7 merge of unplanted invisible pieces is gone.
  (r8-5) records           : per Gaussian origin, initial position, last E, propagated judgment, unit judgment, no-unit flag,
                             u and the 3-D drift; per initial Gaussian the removal iteration and opacity; per unit the reason
                             it is undetermined; per re-read the protected count and the releases by reason.
--- r7 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r7 (JointBuildGS PHD-STAGE2-R7-PROPAGATION-v1).

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

try:  # r9: the shared module is copied into the fork root as src/phd/prior_propagation_v3 (build_fork_r9.py)
    from src.phd.prior_propagation_v3 import conversion as ppc
    from src.phd.prior_propagation_v3 import locations as ppl
    from src.phd.prior_propagation_v3 import orientation as ppo
    from src.phd.prior_propagation_v3 import rule as ppr
    from src.phd.prior_propagation_v3 import seat as pps
except ImportError:  # pragma: no cover - r6 behaviour stays available without the module
    ppc = ppl = ppo = ppr = pps = None

MODES = ("off", "P", "P0", "I")
ORIGIN_IMAGE, ORIGIN_PRIOR = 0, 1
LABELS = ("preserve", "correct", "undecided", "other")
REVISION = "r10"


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
    g.add_argument("--jbgs_prop_tag", default="data", help="r8: key suffix of the product's states / votes (the one tolerance)")
    g.add_argument("--jbgs_prop_majority", type=float, default=2.0 / 3.0)
    g.add_argument("--jbgs_prop_min_evidence", type=int, default=5)
    g.add_argument("--jbgs_prop_max_distance", type=float, default=1.0, help="r7: metres along the surface")
    g.add_argument("--jbgs_seat_path", default="", help="r7: seat_surface.npy aligned with the initial cloud (compact surface index, -1 none)")
    g.add_argument("--jbgs_locmap_dir", default="", help="r7: per-view location maps of the product")
    g.add_argument("--jbgs_markmap_dir", default="", help="r8: per-view agree/conflict marks of the product (g_p of pixels without a unit)")
    g.add_argument("--jbgs_tau_dir", default="", help="r7: per-view tau_p maps (overrides maps_root/tau_set)")
    g.add_argument("--jbgs_prior_normal_path", default="", help="r9: prior_normal.npy aligned with the initial cloud (outward face normal "
                   "of every prior point, NaN rows for image points); empty = the base implementation's random rotation (r8)")
    g.add_argument("--jbgs_prior_normal_mode", default="file", choices=["file", "cell"],
                   help="r10: file = the normals of --jbgs_prior_normal_path (r9); cell = the face normal of the cell a point first sits "
                   "in (points without a patch keep the file normal)")
    g.add_argument("--jbgs_reset_dump_iterations", type=int, nargs="*", default=[],
                   help="r10: save the state right before and right after the opacity reset of these iterations (record only)")
    g.add_argument("--jbgs_reset_probe_dir", default="", help="r10: directory of the reset states for --jbgs_dry_init 3")
    g.add_argument("--jbgs_tau_roof", type=float, default=float("nan"), help="r7: roof-like tolerance (m) for the drift bound")
    g.add_argument("--jbgs_tau_wall", type=float, default=float("nan"), help="r7: wall-like tolerance (m) for the drift bound")
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
        # r8: the initial unit's normal and surface kind (u of eq. 7), the category of every initial disk, removal history
        if getattr(self, "_init_kept", None) is not None:
            k = self._init_kept
            self.init_normal, self.init_kind, self.init_cat = k["normal"], k["kind"], k["cat"]
            self.init_face_normal = k["face_normal"]
            self._init_kept = None
        else:
            self.init_normal = torch.zeros((n, 3), device="cuda"); self.init_normal[:, 2] = 1.0
            self.init_kind = torch.zeros(n, dtype=torch.long, device="cuda")
            self.init_cat = torch.where(gaussians.origin == ORIGIN_PRIOR, 4, 0).long()
            self.init_face_normal = torch.full((n, 3), float("nan"), device="cuda")
        self.removed_at = torch.full((n,), -1, dtype=torch.int32, device="cuda")
        self.removed_opacity = torch.full((n,), float("nan"), device="cuda")
        self.cur_iter = 0
        self.g_loc = self.g_J = self.g_located = None
        self.g_Jl = None
        self.g_state = None
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
        self._wrap_reset(gaussians)          # r10-1: record-only dumps around the opacity reset
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
        if int(getattr(args, "jbgs_dry_init", 0)) == 3:    # r10-1: offline re-read of the reset states
            self.reset_probe(gaussians)
            raise SystemExit(0)
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
            if mask is not None:
                me._record_removal(gaussians, mask)                    # r8: lineages that vanish with this pruning
            r = orig_prune(*a, **k)
            me.counters["removed"] += before - gaussians.get_xyz.shape[0]
            if mask is not None:
                me._rows_keep(~mask)                                   # r7: per-row records follow the pruning
            return r

        gaussians.densification_postfix = postfix
        gaussians.prune_points = prune

    @torch.no_grad()
    def _record_removal(self, gaussians, mask):
        """r8-5: an initial disk is removed when the last Gaussian carrying its id is pruned; records the iteration and the
        largest opacity among the pruned members of the lineage (opacity < opacity_cull: pruned as transparent)."""
        ids = gaussians.init_id
        if ids is None or getattr(self, "removed_at", None) is None:
            return
        ids = ids.long(); mask = mask.bool()
        valid = ids >= 0
        gone_rows = mask & valid
        if not bool(gone_rows.any()):
            return
        n0 = self.removed_at.shape[0]
        alive = torch.zeros(n0, dtype=torch.bool, device=ids.device)
        alive[ids[~mask & valid]] = True
        r_ids = ids[gone_rows]
        op = gaussians.get_opacity.squeeze(-1).detach()[gone_rows].float()
        mx = torch.full((n0,), -1.0, device=ids.device)
        mx.scatter_reduce_(0, r_ids, op, reduce="amax")
        cand = torch.unique(r_ids)
        gone = cand[~alive[cand]]
        self.removed_at[gone] = int(self.cur_iter)
        self.removed_opacity[gone] = mx[gone]

    ROWS = ("E", "E_cnt", "g_J", "g_Jl", "g_loc", "g_located", "_g_surface", "g_state")
    FILL = {"E": float("nan"), "E_cnt": 0.0, "g_J": -1, "g_Jl": -1, "g_loc": -1, "g_located": False, "_g_surface": -1, "g_state": -1}

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

    # ---------------------------------------------------------------------------------- r10-1 reset records
    def _wrap_reset(self, gaussians):
        """record only: at --jbgs_reset_dump_iterations save the state right before and right after reset_opacity (the
        reset itself is the base function, called with the same arguments)."""
        its = set(int(i) for i in (getattr(self.args, "jbgs_reset_dump_iterations", None) or []))
        if not its:
            return
        orig_reset = gaussians.reset_opacity
        me = self

        def reset(*a, **k):
            it = int(me.cur_iter)
            ex = k.get("exempt_mask", a[0] if a else None)
            if it in its:
                me._dump_state(gaussians, it, "pre_reset", ex)
            r = orig_reset(*a, **k)
            if it in its:
                me._dump_state(gaussians, it, "post_reset", ex)
            return r
        gaussians.reset_opacity = reset

    @torch.no_grad()
    def _dump_state(self, gaussians, iteration, tag, exempt):
        d = self.model_path / "dump" / "reset_states"
        d.mkdir(parents=True, exist_ok=True)
        n = gaussians.get_xyz.shape[0]

        def rows(t):
            return t.detach().cpu() if (t is not None and t.shape[0] == n) else None
        st = dict(iteration=int(iteration), tag=tag, revision=REVISION, active_sh_degree=int(gaussians.active_sh_degree),
                  xyz=gaussians._xyz.detach().cpu(), features_dc=gaussians._features_dc.detach().cpu(),
                  features_rest=gaussians._features_rest.detach().cpu(), scaling=gaussians._scaling.detach().cpu(),
                  rotation=gaussians._rotation.detach().cpu(), opacity=gaussians._opacity.detach().cpu(),
                  origin=gaussians.origin.detach().cpu(), init_id=gaussians.init_id.detach().cpu(),
                  frozen_mask=rows(gaussians.frozen_mask), exempt_mask=rows(exempt),
                  E=rows(self.E), E_cnt=rows(self.E_cnt), g_loc=rows(self.g_loc), g_located=rows(self.g_located),
                  g_Jl=rows(self.g_Jl), g_state=rows(self.g_state))
        torch.save(st, d / f"reset_{iteration}_{tag}.pt")
        print(f"[jbgs_judgment] r10 reset state {tag} at {iteration}: {n} Gaussians, protected {int(gaussians.frozen_mask.sum()) if gaussians.frozen_mask is not None else 0}")

    @torch.no_grad()
    def _load_state(self, gaussians, st):
        P_ = torch.nn.Parameter
        for name, key in (("_xyz", "xyz"), ("_features_dc", "features_dc"), ("_features_rest", "features_rest"),
                          ("_scaling", "scaling"), ("_rotation", "rotation"), ("_opacity", "opacity")):
            setattr(gaussians, name, P_(st[key].cuda().clone(), requires_grad=False))
        gaussians.active_sh_degree = st["active_sh_degree"]
        gaussians.origin = st["origin"].cuda().clone(); gaussians.init_id = st["init_id"].cuda().clone()
        gaussians.set_frozen_mask(st["frozen_mask"].cuda().clone())

    @torch.no_grad()
    def reset_probe(self, gaussians):
        """r10-1 (dry_init 3): re-read the two reset states with update_E_r8 (the r9 re-read). Per state: the protection, E,
        and per training view the seeing decision of every occupied patch (seat.reread_E with that one view) and of every
        Gaussian without a patch (seat.centre_E with that one view). Writes monitor/reset_probe.{json,npz}."""
        src = Path(self.args.jbgs_reset_probe_dir)
        files = sorted(src.glob("reset_*_pre_reset.pt"))
        if not files:
            raise FileNotFoundError(f"no reset states in {src}")
        out, arrays = {}, {}
        for fpre in files:
            it = int(fpre.name.split("_")[1])
            res = {}
            for tag in ("pre_reset", "post_reset"):
                st = torch.load(src / f"reset_{it}_{tag}.pt", map_location="cpu")
                self._load_state(gaussians, st)
                eff = gaussians.frozen_mask.clone()
                self.E_calls = 1; self.keep_maps = True
                row = self.update_E_r8(it, gaussians)
                Dm, ALm = self.last_maps
                lock = gaussians.frozen_mask.clone()
                located, loc = self.g_located.clone(), self.g_loc.clone()
                u_, inv = torch.unique(loc[located], return_inverse=True)
                smp = pps.cell_samples(self.prop["st_t"], u_, int(self.args.jbgs_reread_samples))
                prior = gaussians.origin == ORIGIN_PRIOR
                nou = prior & ~located
                xyz = gaussians.get_xyz.detach()
                names = [c.image_name for c in self.train_cams]
                sees_cell = torch.zeros((u_.numel(), len(names)), dtype=torch.bool, device="cuda")
                sees_nou = torch.zeros((int(nou.sum()), len(names)), dtype=torch.bool, device="cuda")
                for j, cam in enumerate(self.train_cams):
                    _, ns, _ = pps.reread_E(smp, [cam], project_points, self.A, Dm, ALm, self.args.jbgs_e_depth_tol, self.args.jbgs_e_alpha_min)
                    sees_cell[:, j] = ns > 0
                    _, cn = pps.centre_E(xyz[nou], [cam], project_points, self.A, Dm, ALm, self.args.jbgs_e_depth_tol, self.args.jbgs_e_alpha_min)
                    sees_nou[:, j] = cn > 0
                al = {nm: ALm[nm] for nm in names}
                res[tag] = dict(row=row, eff=eff, lock=lock, E=self.E.clone(), cnt=self.E_cnt.clone(), cells=u_, sees_cell=sees_cell,
                                nou=nou, sees_nou=sees_nou, D={nm: Dm[nm].clone() for nm in names}, AL=al,
                                opacity=gaussians.get_opacity.squeeze(-1).detach().clone(), n=int(xyz.shape[0]), located=located, loc=loc)
                self.last_maps = None
            a, b = res["pre_reset"], res["post_reset"]
            assert torch.equal(a["cells"], b["cells"]) and torch.equal(a["nou"], b["nou"]), "the two states must hold the same Gaussians"
            thr = float(self.args.jbgs_e_threshold)
            prior = gaussians.origin == ORIGIN_PRIOR
            cross = prior & ((a["E"] < thr) != (b["E"] < thr))
            dcell = a["sees_cell"] != b["sees_cell"]; dnou = a["sees_nou"] != b["sees_nou"]
            names = [c.image_name for c in self.train_cams]
            per_view = {nm: dict(cells_changed=int(dcell[:, j].sum()), cells_seen_pre=int(a["sees_cell"][:, j].sum()), cells_seen_post=int(b["sees_cell"][:, j].sum()),
                                 no_patch_changed=int(dnou[:, j].sum()), no_patch_seen_pre=int(a["sees_nou"][:, j].sum()), no_patch_seen_post=int(b["sees_nou"][:, j].sum()),
                                 alpha_lt_05_pre=float((a["AL"][nm] < 0.5).float().mean()), alpha_lt_05_post=float((b["AL"][nm] < 0.5).float().mean()))
                        for j, nm in enumerate(names)}
            rep_view = max(names, key=lambda nm: per_view[nm]["cells_changed"] + per_view[nm]["no_patch_changed"])
            eff = a["eff"]
            summary = dict(iteration=it, n=a["n"], n_prior=int(prior.sum()), protected_in_effect=int(eff.sum()),
                           opacity_reset_rows=int((~eff).sum()),
                           pre=dict(protected=int(a["lock"].sum()), newly=int((a["lock"] & ~eff).sum()), released=int((eff & ~a["lock"]).sum()),
                                    released_by=a["row"]["released_by"], E_below=int((prior & (a["E"] < thr)).sum()),
                                    no_seeing_view=int((prior & (a["cnt"] == 0)).sum()), row=a["row"]),
                           post=dict(protected=int(b["lock"].sum()), newly=int((b["lock"] & ~eff).sum()), released=int((eff & ~b["lock"]).sum()),
                                     released_by=b["row"]["released_by"], E_below=int((prior & (b["E"] < thr)).sum()),
                                     no_seeing_view=int((prior & (b["cnt"] == 0)).sum()), row=b["row"]),
                           post_not_pre=int((b["lock"] & ~a["lock"]).sum()), pre_not_post=int((a["lock"] & ~b["lock"]).sum()),
                           E_crossed_threshold=int(cross.sum()), E_up=int((cross & (b["E"] >= thr)).sum()), E_down=int((cross & (b["E"] < thr)).sum()),
                           cells=int(a["cells"].numel()), cell_view_pairs=int(dcell.numel()), cell_view_pairs_changed=int(dcell.sum()),
                           cell_view_seen_pre=int(a["sees_cell"].sum()), cell_view_seen_post=int(b["sees_cell"].sum()),
                           cell_view_hidden_to_seen=int((~a["sees_cell"] & b["sees_cell"]).sum()), cell_view_seen_to_hidden=int((a["sees_cell"] & ~b["sees_cell"]).sum()),
                           no_patch_gaussians=int(a["nou"].sum()), no_patch_view_pairs_changed=int(dnou.sum()),
                           no_patch_hidden_to_seen=int((~a["sees_nou"] & b["sees_nou"]).sum()), no_patch_seen_to_hidden=int((a["sees_nou"] & ~b["sees_nou"]).sum()),
                           opacity_reset_check=dict(protected_kept=bool(torch.equal(a["opacity"][eff], b["opacity"][eff])),
                                                    others_max_after=float(b["opacity"][~eff].max()) if bool((~eff).any()) else None),
                           representative_view=rep_view, per_view=per_view)
            out[str(it)] = summary
            j = names.index(rep_view); cam = self.train_cams[j]
            cen = self.prop["st_t"]["loc_center"][a["cells"]].float()
            uu, vv, zz = project_points(cen, cam)
            arrays[f"{it}_view"] = np.array(rep_view)
            for tag, r_ in (("pre", a), ("post", b)):
                arrays[f"{it}_{tag}_depth"] = r_["D"][rep_view].cpu().numpy().astype(np.float32)
                arrays[f"{it}_{tag}_alpha"] = r_["AL"][rep_view].cpu().numpy().astype(np.float16)
                arrays[f"{it}_{tag}_cells_seen"] = r_["sees_cell"][:, j].cpu().numpy()
                arrays[f"{it}_{tag}_lock"] = r_["lock"].cpu().numpy()
                arrays[f"{it}_{tag}_E"] = r_["E"].cpu().numpy().astype(np.float32)
            arrays[f"{it}_cell_uv"] = torch.stack([uu, vv, zz], 1).cpu().numpy().astype(np.float32)
            arrays[f"{it}_cells"] = a["cells"].cpu().numpy()
            arrays[f"{it}_cell_state"] = self.prop["state"][a["cells"]].cpu().numpy().astype(np.int8)
            arrays[f"{it}_eff"] = eff.cpu().numpy()
            arrays[f"{it}_prior"] = prior.cpu().numpy()
            arrays[f"{it}_init_category"] = torch.where(gaussians.init_id >= 0, self.init_cat[gaussians.init_id.long().clamp_min(0)], -1).cpu().numpy().astype(np.int8)
            print(f"[jbgs_judgment] r10 reset probe {it}: " + json.dumps({k: v for k, v in summary.items() if k not in ("per_view", "pre", "post")}))
        (self.mon / "reset_probe.json").write_text(json.dumps(out, indent=1, default=float))
        np.savez_compressed(self.mon / "reset_probe.npz", **arrays)

    # ---------------------------------------------------------------------------------------- r8 propagation
    CAT_NAMES = {0: "image", 1: "support unit", 2: "missing unit", 3: "invisible unit", 4: "prior without a unit"}

    @torch.no_grad()
    def prop_init(self, args, gaussians):
        """r8-1/2/3. Loads the stage-1 product, propagates with the configured values, seats every prior point, plants
        (all but the points of missing units with a propagated conflict), first E, g_p maps.
        Returns the compact surface index of every kept point (-1: image point or prior point without a unit)."""
        if ppl is None:
            raise RuntimeError("src/phd/prior_propagation_v2 is not importable from the fork root")
        t0 = time.time()
        st = ppl.load_store(args.jbgs_prop_store)
        tag = args.jbgs_prop_tag
        state, vote, E0, ns0 = st[f"state_{tag}"], st[f"vote_{tag}"], st[f"E_{tag}"], st[f"n_seeing_{tag}"]
        q, k, r = args.jbgs_prop_majority, int(args.jbgs_prop_min_evidence), float(args.jbgs_prop_max_distance)
        J, (mis, kd, kv) = ppl.propagate(st, state, vote, q, k, r)
        J_loc = ppl.location_judgment(state, vote, J)
        why = ppr.undetermined_why(state, J, kd, mis, k, r)
        within = kd[:, :k] <= r + 1e-9 if len(mis) else np.zeros((0, k), bool)
        got = np.full(len(state), -1, np.int16); ncf = np.full(len(state), -1, np.int16)
        if len(mis):
            got[mis] = within.sum(1); ncf[mis] = ((kv[:, :k] == ppr.V_CONFLICT) & within).sum(1)
        np.savez_compressed(self.mon / "locations.npz", state=state, vote=vote, judgment=J, unit_judgment=J_loc, why=why,
                            why_codes=np.array([ppr.WHY_NAMES[i] for i in sorted(ppr.WHY_NAMES)]), E=E0, n_seeing=ns0,
                            n_supporting=st[f"n_supporting_{tag}"], evidence_within=got, evidence_conflict=ncf,
                            surface_ext=st["surf_ext"][st["loc_surface"]], kind=st["loc_kind"], area=st["loc_area"],
                            center=st["loc_center"].astype(np.float32))
        dev = "cuda"
        P = dict(store=st, st_t=pps.to_torch(st, dev), state=torch.as_tensor(state, device=dev).long(),
                 vote=torch.as_tensor(vote, device=dev).long(), E0=torch.as_tensor(E0, device=dev).float(),
                 ns0=torch.as_tensor(ns0, device=dev).float(), J=torch.as_tensor(J, device=dev).long(),
                 J_loc=torch.as_tensor(J_loc, device=dev).long(), prop_seconds=time.time() - t0)
        # unit normals (u of eq. 7): the cell's in-surface steps t1 x t2; units without cells ('extra') have none
        nrm = torch.cross(P["st_t"]["loc_t1"], P["st_t"]["loc_t2"], dim=1)
        nn = nrm.norm(dim=1, keepdim=True)
        P["unit_normal"] = torch.where(nn > 1e-9, nrm / nn.clamp_min(1e-12), torch.zeros_like(nrm)).float()
        P["unit_kind"] = torch.where(nn.squeeze(1) > 1e-9, P["st_t"]["loc_kind"].long(), torch.zeros_like(P["st_t"]["loc_kind"].long()))
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
        face_n, orient = self.orient_prior(args, gaussians, prior, cell=(has, loc))   # r9-2 (fix 'da'); r10-2 cell method
        normal_after = ppo.normal_of_quat(gaussians._rotation.detach().double()).float()
        stt = torch.full((n,), -1, dtype=torch.long, device=dev); stt[has] = P["state"][loc[has]]
        Jt = torch.full((n,), ppr.J_NONE, dtype=torch.long, device=dev); Jt[has] = P["J"][loc[has]]
        Jl = torch.full((n,), ppr.J_NONE, dtype=torch.long, device=dev); Jl[has] = P["J_loc"][loc[has]]
        # first Gaussian confidence: unit -> the product's E; no unit -> centre, the prior depth as the one-sided occluder
        Dp, ALp = pps.prior_occluder(self.P)
        E_c, cnt_c = pps.centre_E(xyz, self.train_cams, project_points, self.A, Dp, ALp, args.jbgs_e_depth_tol, args.jbgs_e_alpha_min)
        E_first = E_c.clone(); n_first = cnt_c.clone()
        E_first[has] = P["E0"][loc[has]]; n_first[has] = P["ns0"][loc[has]]
        conflict = has & (stt == ppr.ST_MISSING) & (Jt == ppr.J_CONFLICT)
        drop = conflict
        cat = torch.zeros(n, dtype=torch.long, device=dev)
        cat[has & (stt == ppr.ST_SUPPORT)] = 1; cat[has & (stt == ppr.ST_MISSING)] = 2; cat[has & (stt == ppr.ST_INVISIBLE)] = 3
        cat[prior & ~has] = 4
        reason = torch.zeros(n, dtype=torch.int8, device=dev); reason[drop] = 2
        ext = P["st_t"]["surf_ext"]
        surf_ext = torch.full((n,), -1, dtype=torch.long, device=dev); surf_ext[has] = ext[seat[has]]
        np.savez_compressed(self.mon / "unplanted.npz", xyz=xyz[drop].cpu().numpy().astype(np.float32),
                            surface=surf_ext[drop].cpu().numpy(), location=loc[drop].cpu().numpy(), reason=reason[drop].cpu().numpy(),
                            reason_codes=np.array(["kept", "-", "missing unit with a propagated conflict"]))
        np.savez_compressed(self.mon / "init_points.npz", xyz=xyz.cpu().numpy().astype(np.float32), origin=gaussians.origin.cpu().numpy(),
                            seat=seat.cpu().numpy(), surface=surf_ext.cpu().numpy(), location=loc.cpu().numpy(), state=stt.cpu().numpy(),
                            judgment=Jt.cpu().numpy(), unit_judgment=Jl.cpu().numpy(), E_first=E_first.cpu().numpy(),
                            n_seeing_first=n_first.cpu().numpy().astype(np.int16), E_centre_prior_depth=E_c.cpu().numpy(),
                            n_seeing_centre=cnt_c.cpu().numpy().astype(np.int16), category=cat.cpu().numpy().astype(np.int8),
                            category_codes=np.array([self.CAT_NAMES[i] for i in range(5)]),
                            planted=(~drop).cpu().numpy(), reason=reason.cpu().numpy(),
                            face_normal=face_n.cpu().numpy(), normal_after_orientation=normal_after.cpu().numpy(),
                            face_normal_file=self._fn_file.cpu().numpy(), face_normal_cell=self._fn_cell.cpu().numpy())
        info = dict(applied=True, rule="r8: every prior point is planted except those of missing units whose propagated judgment is "
                    "conflict (support units whatever their vote, invisible units and points without a unit are planted)",
                    store=str(args.jbgs_prop_store), tag=tag, majority=q, min_evidence=k, max_distance=r,
                    prop_seconds=round(P["prop_seconds"], 2), n_units=int(len(state)), n_support=int((state == ppr.ST_SUPPORT).sum()),
                    n_missing=int((state == ppr.ST_MISSING).sum()), n_invisible=int((state == ppr.ST_INVISIBLE).sum()),
                    missing_judgments={ppr.J_NAMES[j]: int((J[state == ppr.ST_MISSING] == j).sum()) for j in ppr.J_NAMES},
                    why_undetermined={ppr.WHY_NAMES[w]: int((why == w).sum()) for w in ppr.WHY_NAMES},
                    n_before=int(n), n_prior_before=int(prior.sum()), n_prior_located=int(has.sum()), n_prior_without_unit=int((prior & ~has).sum()),
                    categories={self.CAT_NAMES[c]: int((cat == c).sum()) for c in range(5)},
                    planted_by_category={self.CAT_NAMES[c]: int(((cat == c) & ~drop).sum()) for c in range(5)},
                    n_conflict_points=int(conflict.sum()), n_dropped_conflict=int(drop.sum()), n_prior_kept=int((prior & ~drop).sum()),
                    n_image=int((~prior).sum()), n_extra_units_without_normal=int((P["unit_kind"] == 0).sum()),
                    orientation=orient)
        self.init_filter = info
        print(f"[jbgs_judgment] r8 init: prior {info['n_prior_before']} (with a unit {info['n_prior_located']}) -> kept {info['n_prior_kept']}; "
              f"dropped (missing, propagated conflict) {info['n_dropped_conflict']}; categories {info['categories']}; "
              f"missing judgments {info['missing_judgments']}")
        self._g_init(args)
        keep = ~drop
        u_n = torch.zeros((n, 3), device=dev); u_n[:, 2] = 1.0
        u_k = torch.zeros(n, dtype=torch.long, device=dev)
        u_n[has] = P["unit_normal"][loc[has]]; u_k[has] = P["unit_kind"][loc[has]]
        u_n[u_k == 0] = torch.tensor([0.0, 0.0, 1.0], device=dev)
        self._init_kept = dict(normal=u_n[keep].clone(), kind=u_k[keep].clone(), cat=cat[keep].clone(), face_normal=face_n[keep].clone())
        self._first = dict(E=E_first[keep].clone(), n=n_first[keep].clone())
        if bool(drop.any()):
            gaussians.prune_points(drop)
        return seat[keep].clone()

    @torch.no_grad()
    def orient_prior(self, args, gaussians, prior, cell=None):
        """r9-2 (fix 'da', method 4.3): the rotation of every prior-origin Gaussian with a face normal = the frame of that
        face (orientation.quat_from_normal: disk normal = the face's outward normal, first tangent axis = the face's
        horizontal line). Image-origin rows and prior rows without a normal keep the base implementation's rotation.
        r10-2: cell = (has, loc) of prop_init; with --jbgs_prior_normal_mode cell the face normal of a point on a patch with
        cells is the unit normal of its cell (t1 x t2, signed like its file normal; up where it has none).
        Returns (face normal [N, 3], NaN where none; info)."""
        n = gaussians.get_xyz.shape[0]
        fn = torch.full((n, 3), float("nan"), device="cuda")
        self._fn_file = torch.full((n, 3), float("nan"), device="cuda")
        self._fn_cell = torch.full((n, 3), float("nan"), device="cuda")
        path = getattr(args, "jbgs_prior_normal_path", "")
        if not path:
            return fn, dict(applied=False, rule="base implementation's random rotation (r8)")
        arr = torch.as_tensor(np.load(path), dtype=torch.float32, device="cuda")
        if arr.shape[0] != n:
            raise ValueError(f"prior normals {arr.shape[0]} != initial points {n}")
        ok = prior & torch.isfinite(arr).all(1) & (arr.norm(dim=1) > 0.5)
        fn[ok] = arr[ok] / arr[ok].norm(dim=1, keepdim=True)
        self._fn_file = fn.clone()
        mode = getattr(args, "jbgs_prior_normal_mode", "file")
        cinfo = {}
        if cell is not None and self.prop is not None:
            has, loc = cell
            uk = torch.zeros(n, dtype=torch.long, device="cuda"); uk[has] = self.prop["unit_kind"][loc[has]]
            c_ok = has & (uk > 0)
            c = self.prop["unit_normal"][loc[c_ok]].float()
            ref = self._fn_file[c_ok]
            ref_ok = torch.isfinite(ref).all(1)
            dot = torch.where(ref_ok, (c * torch.nan_to_num(ref)).sum(1), c[:, 2])
            c = torch.where((dot < 0)[:, None], -c, c)
            self._fn_cell[c_ok] = c
            both = c_ok & ok
            if bool(both.any()):
                a_ = self._fn_cell[both].double(); b_ = self._fn_file[both].double()
                ang = torch.rad2deg(torch.atan2(torch.cross(a_, b_, dim=1).norm(dim=1), (a_ * b_).sum(1).abs()))
                cinfo = dict(n_cell_normal=int(c_ok.sum()), n_both=int(both.sum()),
                             angle_cell_vs_file_deg=dict(p50=float(ang.median()), p95=float(torch.quantile(ang.float(), 0.95)), max=float(ang.max())))
            if mode == "cell":
                fn[c_ok] = self._fn_cell[c_ok]
                ok = ok | c_ok
        before = gaussians._rotation.detach().clone()
        gaussians._rotation.data[ok] = ppo.quat_from_normal(fn[ok].double()).to(gaussians._rotation.dtype)
        nq = ppo.normal_of_quat(gaussians._rotation.detach()[ok].double())
        cosv = (nq * fn[ok].double()).sum(1).clamp(-1.0, 1.0)
        ang = torch.rad2deg(torch.atan2(torch.cross(nq, fn[ok].double(), dim=1).norm(dim=1), cosv))
        info = dict(applied=True, rule="disk normal = outward face normal, first axis = the face's horizontal line (orientation.quat_from_normal)",
                    mode=mode, n_prior=int(prior.sum()), n_oriented=int(ok.sum()), n_prior_without_normal=int((prior & ~ok).sum()),
                    max_angle_deg=float(ang.max()) if bool(ok.any()) else None, min_signed_cos=float(cosv.min()) if bool(ok.any()) else None,
                    image_rows_unchanged=bool(torch.equal(before[~prior], gaussians._rotation.detach()[~prior])), cell=cinfo)
        if mode == "cell":
            info["rule"] += "; r10 cell method: points on a patch with cells take the cell's face normal, the others the file normal"
            info["n_from_cell"] = int(torch.isfinite(self._fn_cell).all(1).sum())
        print(f"[jbgs_judgment] r10 orientation: {info}")
        return fn, info

    @torch.no_grad()
    def _g_init(self, args):
        """r8-1: g_p per training view at the training resolution, decided once. Pixel -> unit through the product's unit
        map, its judgment from the unit table (support vote / propagated, alike); pixels without a unit use c_p and their
        own mark. Counts per view: prior pixels by (unit / no unit) x (c_p 1 / 0) x g_p."""
        self.GW, self.g_counts = {}, {}
        if not args.jbgs_locmap_dir or not args.jbgs_markmap_dir:
            raise ValueError("r8 needs --jbgs_locmap_dir and --jbgs_markmap_dir")
        names = sorted(self.train_names)
        LM = _load_set(Path(args.jbgs_locmap_dir), names, self.size, "cuda", dtype=np.int32)
        MK = _load_set(Path(args.jbgs_markmap_dir), names, self.size, "cuda", dtype=np.int32)
        Jl_t = self.prop["J_loc"]
        for name in names:
            lm = LM[name].long(); mk = MK[name].long(); A = self.A[name]; P = self.P.get(name)
            located = lm >= 0
            Jl = torch.full_like(lm, ppr.J_NONE); Jl[located] = Jl_t[lm[located]]
            off = ppr.prior_term_off(located, Jl, A, mk)
            g = (~off).float()
            self.GW[name] = g
            if P is not None:
                pp = torch.isfinite(P) & (P > 0)
                a1 = A > 0.5
                c = {}
                for lname, lmask in (("unit", located), ("no_unit", ~located)):
                    for aname, amask in (("c1", a1), ("c0", ~a1)):
                        base = pp & lmask & amask
                        c[f"{lname}_{aname}_g1"] = int((base & (g > 0)).sum()); c[f"{lname}_{aname}_g0"] = int((base & (g == 0)).sum())
                c["prior_px"] = int(pp.sum())
                for jn, jv in (("agree", ppr.J_AGREE), ("conflict", ppr.J_CONFLICT), ("mixed", ppr.J_MIXED), ("insufficient", ppr.J_INSUFF)):
                    c[f"unit_judgment_{jn}"] = int((pp & located & (Jl == jv)).sum())
                self.g_counts[name] = c
        del LM, MK

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
                    gw = getattr(self, "GW", {}).get(cam_name)        # r8-1: g_p (eq. 4); r6 path: 1 - c_p
                    w = gw if gw is not None else 1.0 - A
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
        self.cur_iter = iteration          # r8-5: called at the start of every iteration
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
            return self.update_E_r8(iteration, gaussians)
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
    def u_offsets(self, gaussians):
        """r8-4: (u [N] like the residuals, 3-D drift [N], tau of the initial surface kind [N]); NaN without an initial disk."""
        xyz = gaussians.get_xyz.detach()
        n = xyz.shape[0]
        ids = gaussians.init_id.long()
        has = ids >= 0
        u = torch.full((n,), float("nan"), device="cuda"); d3 = torch.full((n,), float("nan"), device="cuda")
        kind = torch.zeros(n, dtype=torch.long, device="cuda")
        if bool(has.any()):
            disp = xyz[has] - self.init_xyz[ids[has]]
            kind[has] = self.init_kind[ids[has]]
            u[has] = ppc.offset_metres(disp, self.init_normal[ids[has]], kind[has]).float()
            d3[has] = disp.norm(dim=1)
        tau = torch.where(kind == 2, torch.tensor(self.tau_kind[2], device="cuda"), torch.tensor(self.tau_kind[1], device="cuda"))
        return u, d3, tau, kind

    @torch.no_grad()
    def update_E_r8(self, iteration, gaussians):
        """r8-3 / r8-4. First call: E of a Gaussian on a unit = the unit's E from the product (occlusion by the prior render),
        without a unit = its centre with the prior depth as the one-sided occluder. Later calls: the occupied cells
        re-measured with the current render (r7) and the centres of the Gaussians without a unit with the same render.
        Protection = prior origin & propagated judgment != conflict & E < threshold & u <= mult x tau (eq. 7)."""
        a = self.args
        xyz = gaussians.get_xyz.detach()
        n = xyz.shape[0]
        located, s, loc = self.seat_now(gaussians)
        extra = {}
        if self.E_calls == 0 or self.render_fn is None:
            first = getattr(self, "_first", None)
            if first is not None and first["E"].shape[0] == n:
                E, cnt = first["E"].clone(), first["n"].clone()
            else:   # no product values for these rows (should not happen at iteration 1): centres with the prior depth
                Dp, ALp = pps.prior_occluder(self.P)
                E, cnt = pps.centre_E(xyz, self.train_cams, project_points, self.A, Dp, ALp, a.jbgs_e_depth_tol, a.jbgs_e_alpha_min)
                E[located] = self.prop["E0"][loc[located]]; cnt[located] = self.prop["ns0"][loc[located]]
            how = "unit E of the product (prior render); centre with the prior depth as occluder where no unit"
            self._first = None
        else:
            Dm, ALm = self.render_train_depths(gaussians)
            E, cnt = pps.centre_E(xyz, self.train_cams, project_points, self.A, Dm, ALm, a.jbgs_e_depth_tol, a.jbgs_e_alpha_min)
            if bool(located.any()):
                u_, inv = torch.unique(loc[located], return_inverse=True)
                Eu, nsu, _ = self.sampled_E(u_, Dm, ALm)
                E[located] = Eu[inv].float(); cnt[located] = nsu[inv].float()
                extra["n_cells_read"] = int(u_.numel())
            how = "cells re-measured with the current render; centre with the current render where no unit"
            self.last_maps = (Dm, ALm) if self.keep_maps else None
            del Dm, ALm
        self.E_calls += 1
        Jn = torch.full((n,), ppr.J_NONE, dtype=torch.long, device="cuda")
        Jn[located] = self.prop["J"][loc[located]]
        Jl = torch.full((n,), ppr.J_NONE, dtype=torch.long, device="cuda")
        Jl[located] = self.prop["J_loc"][loc[located]]
        St = torch.full((n,), -1, dtype=torch.long, device="cuda")
        St[located] = self.prop["state"][loc[located]]
        prior = gaussians.origin == ORIGIN_PRIOR
        prev = gaussians.frozen_mask.clone() if gaussians.frozen_mask is not None else torch.zeros_like(prior)
        u, d3, tau_u, kind = self.u_offsets(gaussians)
        bound = tau_u * float(a.jbgs_lock_drift_tau_mult)
        # r9-1 (fix 'na'): eq. (7) excludes every Gaussian whose patch judgment is conflict (support vote or propagated)
        lock, low, near, conflict = ppr.protected(prior, E, a.jbgs_e_threshold, u, bound, Jl)
        far = low & ~near
        conf_sup = conflict & (St == ppr.ST_SUPPORT)
        conf_mis = conflict & (St == ppr.ST_MISSING)
        if self.mode == "P":
            gaussians.set_frozen_mask(lock)
            self.floor_now(gaussians)
        else:
            lock = torch.zeros_like(prior)
        self.E, self.E_cnt, self.E_how = E, cnt.float(), how
        self.g_J, self.g_Jl, self.g_loc, self.g_located, self._g_surface = Jn, Jl, loc, located, s
        self.g_state = St
        newly, released = lock & ~prev, prev & ~lock
        ids = gaussians.init_id.long(); okid = ids >= 0
        cat = torch.full((n,), -1, dtype=torch.long, device="cuda"); cat[okid] = self.init_cat[ids[okid]]
        rel_E = released & (E >= a.jbgs_e_threshold); rel_c = released & conflict; rel_u = released & ~near
        near3 = torch.isfinite(d3) & (d3 <= bound)
        self.last_update = dict(iteration=iteration, prev=prev, lock=lock, far=far, drift=d3, u=u, conflict=conflict, located=located, loc=loc)
        hist_p = torch.histc(E[prior].float(), bins=10, min=0.0, max=1.0).tolist() if prior.any() else [0] * 10
        row = dict(iteration=iteration, revision=REVISION, how=how, n=int(n), n_prior=int(prior.sum()), n_located=int(located.sum()),
                   n_prior_without_unit=int((prior & ~located).sum()), n_prior_E_below=int(low.sum()),
                   n_prior_no_seeing_view=int((prior & (cnt == 0)).sum()),
                   n_conflict_excluded=int((low & near & conflict).sum()), n_prior_far=int(far.sum()),
                   excluded_support_conflict=int((low & near & conf_sup).sum()),
                   excluded_propagated_conflict=int((low & near & conf_mis).sum()),
                   prior_on_support_conflict_unit=int((prior & conf_sup).sum()),
                   judgments_located={ppr.J_NAMES.get(j, "none"): int(((Jn == j) & located).sum()) for j in (-1, 0, 1, 2, 3)},
                   E_hist_prior=hist_p, n_locked=int(lock.sum()), n_newly_locked=int(newly.sum()), n_released=int(released.sum()),
                   released_by=dict(E_at_or_above_threshold=int(rel_E.sum()), propagated_conflict=int((released & conf_mis).sum()),
                                    support_conflict=int((released & conf_sup).sum()),
                                    u_beyond_bound=int(rel_u.sum()), several_reasons=int(((rel_E.int() + rel_c.int() + rel_u.int()) > 1).sum()),
                                    no_reason_found=int((released & ~rel_E & ~rel_c & ~rel_u).sum())),
                   locked_by_initial_category={self.CAT_NAMES[c]: int((lock & (cat == c)).sum()) for c in range(5)},
                   locked_on_support_conflict_unit=int((lock & located & (Jl == ppr.J_CONFLICT)).sum()),
                   u_measure="vertical over the initial unit's surface (roof-like), along its normal (wall-like), vertical without a unit",
                   would_differ_with_3d_distance=dict(protected_now_but_3d_beyond=int((lock & ~near3).sum()),
                                                      not_protected_now_but_3d_within=int((low & ~conflict & ~near & near3).sum())),
                   drift_bound_roof=float(self.tau_kind[1] * a.jbgs_lock_drift_tau_mult),
                   drift_bound_wall=float(self.tau_kind[2] * a.jbgs_lock_drift_tau_mult), **extra)
        with (self.mon / "E.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        if self.tb is not None:
            self.tb.add_scalar("judgment/n_locked", row["n_locked"], iteration)
            self.tb.add_scalar("judgment/n_conflict_excluded", row["n_conflict_excluded"], iteration)
        print(f"[jbgs_judgment] iter {iteration}: E r8 ({how}) prior={row['n_prior']} with unit={row['n_located']} locked={row['n_locked']} "
              f"(+{row['n_newly_locked']}/-{row['n_released']} {row['released_by']}) no seeing view={row['n_prior_no_seeing_view']}")
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
            gc = getattr(self, "g_counts", {})
            keys = sorted({k for v in gc.values() for k in v})
            rep["prior_weight"] = dict(rule="g_p: unit judged conflict (vote or propagated) -> 0, else 1; no unit: c_p = 0 -> 1, c_p = 1 -> own mark",
                                       per_view=gc, totals={k: sum(v.get(k, 0) for v in gc.values()) for k in keys})
            lk = gaussians.frozen_mask
            rep["protection"] = dict(n_protected=int(lk.sum()) if lk is not None else 0, n_conflict_excluded=row["n_conflict_excluded"],
                                     n_prior=int(prior.sum()), n_located=int(located.sum()),
                                     by_initial_category=row["locked_by_initial_category"])
        if int(self.args.jbgs_dry_init) == 2 and self.prop is not None:
            # evidence for the offline check: the fork's propagated judgments and its prior-term gates (training resolution)
            LM = _load_set(Path(self.args.jbgs_locmap_dir), sorted(self.train_names), self.size, "cpu", dtype=np.int32) if self.args.jbgs_locmap_dir else {}
            MK = _load_set(Path(self.args.jbgs_markmap_dir), sorted(self.train_names), self.size, "cpu", dtype=np.int32) if self.args.jbgs_markmap_dir else {}
            np.savez_compressed(self.mon / "gate_check.npz", J=self.prop["J"].cpu().numpy(), J_loc=self.prop["J_loc"].cpu().numpy(),
                                **{f"lm_{k}": v.numpy() for k, v in LM.items()}, **{f"mk_{k}": v.numpy().astype(np.int8) for k, v in MK.items()},
                                **{f"A_{k}": (self.A[k] > 0.5).cpu().numpy() for k in sorted(self.train_names)},
                                **{f"g_{k}": (v > 0).cpu().numpy() for k, v in getattr(self, "GW", {}).items()})
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
                     location=self.g_loc.cpu().numpy(), judgment=self.g_J.cpu().numpy(), located=self.g_located.cpu().numpy(),
                     **self._r8_records(gaussians))))

    @torch.no_grad()
    def _r8_records(self, gaussians):
        """r8-5: records the evaluation reads (not part of the method): per Gaussian the initial position, the unit judgment,
        the no-unit flag, u and the 3-D drift, the initial category; per initial disk the removal iteration and opacity."""
        n = gaussians.get_xyz.shape[0]
        ids = gaussians.init_id.long(); ok = ids >= 0
        init_pos = torch.full((n, 3), float("nan"), device="cuda"); init_pos[ok] = self.init_xyz[ids[ok]]
        cat = torch.full((n,), -1, dtype=torch.long, device="cuda"); cat[ok] = self.init_cat[ids[ok]]
        u, d3, tau_u, kind = self.u_offsets(gaussians)
        prior = gaussians.origin == ORIGIN_PRIOR
        Jl = self.g_Jl if (self.g_Jl is not None and self.g_Jl.shape[0] == n) else torch.full((n,), -1, dtype=torch.long, device="cuda")
        St = self.g_state if (self.g_state is not None and self.g_state.shape[0] == n) else torch.full((n,), -1, dtype=torch.long, device="cuda")
        fnr = torch.full((n, 3), float("nan"), device="cuda"); fnr[ok] = self.init_face_normal[ids[ok]]
        return dict(normal=ppo.normal_of_quat(gaussians._rotation.detach()).float().cpu().numpy(), init_face_normal=fnr.cpu().numpy(),
                    unit_state=St.cpu().numpy(), init_position=init_pos.cpu().numpy(), unit_judgment=Jl.cpu().numpy(),
                    no_unit=(prior & ~self.g_located).cpu().numpy(), u=u.cpu().numpy(), drift_3d=d3.cpu().numpy(),
                    u_bound=(tau_u * float(self.args.jbgs_lock_drift_tau_mult)).cpu().numpy(), init_kind_row=kind.cpu().numpy(),
                    init_category=cat.cpu().numpy(), init_category_codes=np.array([self.CAT_NAMES[i] for i in range(5)]),
                    init_category_of_initial=self.init_cat.cpu().numpy(), init_removed_at=self.removed_at.cpu().numpy(),
                    init_removed_opacity=self.removed_opacity.cpu().numpy())

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
