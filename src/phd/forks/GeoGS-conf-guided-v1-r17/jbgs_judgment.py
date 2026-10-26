"""Judgment-guided stage-2 optimization for GeoGS, revision r16 (JointBuildGS PHD-MAIN-FIXTEST-v1).

r16 = r15 (= r14 + the out-of-memory record of train.py; this module was r14's byte for byte) + two switches, each 0 by default;
with both at 0 every decision is r15's (same code path: the switches only add branches; REVISION and the new records differ).
  (r16-A) --jbgs_sw_prior_share_band 1 (fix A, order 2.2 / 6.2): the tolerance band of the prior depth term ends at w instead of
          tau, w = the prior's own share of the tolerance (2.5 x sqrt(NMAD^2 - sigma_image^2), at most tau), read per view and
          pixel from --jbgs_prior_width_dir (the same depth conversion as the tau maps: w_px / max(f, 1e-3)). The pull band is
          w .. hi tau; the truncation (beyond hi tau), the judgments, the conflict thresholds (marks of the stage-1 product),
          the protection bound (4 tau of the surface kind) and every other use of tau are unchanged.
  (r16-B) --jbgs_sw_own_depth_release 1 (fix B, order 2.2 / 6.3): a missing patch (state 2: seen, without enough
          confidence-1 MVS pixels, its judgment borrowed from support patches) whose borrowed judgment is conflict (0) or
          mixed (2) is read as agree (1) -- the propagated table J and the patch table J_loc are rewritten once, right after
          the judgment-level switches, so every path that reads them (initialisation, the depth-term weight g_p, the
          protection of eq. 7 with its opacity floor and reset exemption, density control through the protection mask, the
          re-read) treats it like a borrowed agree; insufficient (3) and none (-1) stay. In the prior depth term the pixels of
          missing patches (any judgment) are not truncated: the pull of the pull band continues beyond hi tau. Support
          patches, invisible patches and pixels without a patch are unchanged.
  Records: meta.json / init_report.json 'fixes'; locations.npz adds judgment_before_own_depth and own_depth_changed (fix B);
  init_report.json adds the per-view pixel counts of the two fixes; scalars.jsonl adds px_prior_w_to_tau (fix A: valid prior
  pixels with w < |r| <= tau) and px_prior_beyond_kept (fix B: missing-patch pixels beyond hi tau, pulled).
--- r14 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r14 (JointBuildGS PHD-MAIN-FIX-v1).

r14 = r13 with the per-view maps of this module kept in pinned host memory instead of on the GPU (order 4.1, memory only):
  (r14-1) the observation confidence A, the MVS depth M, the prior depth P and the tolerance TAU of every view (train and test
          views, as r13 loaded them) and the judgment weight g_p (GW, decided once in _g_init) sit in HostMaps: reading a view
          ([name], .get, .items(), .values()) returns a CUDA copy of the stored tensor, bit for bit; nothing writes into a map
          after it is built (checked: every reader indexes and compares only). Every computation, its order and the random state
          are r13's.
  (r14-2) _g_init reads the location / mark / mark-code maps of one view at a time from host memory (r13 put every view's on the GPU
          at once and built the thresholded marks of all views on the GPU); g_p is computed on the GPU per view and stored on the host.
  (r14-3) records only: --jbgs_memlog_from / _to / _every (default 0 = off) write monitor/memlog.jsonl every _every iterations in
          [_from, _to]: Gaussians, the screen radius (99th percentile, maximum) and the tiles the visible Gaussians cover (re-counted
          from the radii and the projected centres as the rasterizer's getRect, 16 x 16 tiles), torch allocated / reserved / peak and
          the device's used memory (torch.cuda.mem_get_info = nvidia-smi's used). Reads the render outputs only.
  The images were already kept on the CPU by scene/cameras.py (r13 too) and moved per iteration by train.py; r14 does not change that.
  The re-read render (the depth and opacity of every training view at each re-read) stays on the GPU as r13.
--- r13 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r13 (JointBuildGS PHD-MAIN-STAGE2-v1).

r13 = r12 + three ablation flags of the stage-2 order (4.2), each 0 by default; with all three at 0 every decision is r12's
(same code path; the flags only add a branch). Module v6 unchanged.
  (r13-1) --jbgs_ablate_loss_judgment 1   : the prior depth term does not read the judgment: g_p = 1 on every prior pixel (also
                                            where the patch judgment or the pixel's own mark is conflict); the band split of the
                                            term (tolerance / pull / truncation) is kept. Initialisation, protection (eq. 7) and
                                            density control read the judgment as r12.
  (r13-2) --jbgs_ablate_density_judgment 1: density control does not read the judgment: split, clone and prune leave alone (and
                                            the densification statistics skip) every prior-origin Gaussian with E < threshold and
                                            u <= mult x tau (eq. 7 without its judgment term), also on a patch judged conflict.
                                            The gradient protection (lr x lock_lr_scale), the opacity-reset exemption and the
                                            opacity floor stay eq. 7 with the judgment (frozen_mask, r12).
  (r13-3) --jbgs_ablate_tolerance_band 1  : the prior term has no tolerance band: rho(r) = min(|r|, hi tau) -- pulled like the
                                            pull band from 0 up to hi tau, released beyond hi tau (truncation kept). g_p as r12.
                                            (The r11 switch prior_band 0 = rho |r| without truncation, a different change.)
  Records: meta.json / init_report.json 'ablations'; with r13-2 on, E.jsonl adds n_density_exempt and its conflict part.
--- r12 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r12 (JointBuildGS PHD-MAIN-STAGE0-v1).

r12 = r11 calling the shared module src/phd/prior_propagation_v6 (= v5 + locations.move_store + rules.default_rule), plus
  (r12-1) rule default  : --jbgs_rule auto (new default) = rules.default_rule(prior kind): LoD2 current, ALS / DSM
                          margin_all_2 (user decision 2026-10-06). The prior kind comes from --jbgs_prior_kind or the
                          store's 'prior_kind' (v6 measurement); both given -> they must agree. With the stage-1 tallies and
                          the gathered support ids (--jbgs_prop_pairs, --jbgs_prop_knn) every rule, 'current' included, is
                          read through rules.apply (the gathering of the measurement: in-surface distances of the unmoved
                          store); the states must equal the product's, and for 'current' the votes too. Without them only
                          'current' runs (r11 path).
  (r12-2) moved store   : the product store of the v6 measurement is moved with the registered prior (frame_shift); seating,
                          the re-read cell samples and the recorded centres therefore sit on the registered prior. With
                          --jbgs_prior_shift the store's frame_shift must equal it (else the run stops).
  (r12-3) seed          : --jbgs_seed (default 0 = r11: safe_state's seed 0); another value re-seeds random, numpy and torch
                          right after safe_state (train.py calls apply_seed), before the scene is read.
  (r12-4) records       : seconds of the initialisation (meta / init_report), of every re-read (E.jsonl 'seconds', cuda-
                          synchronised) and of every read-out (monitor/timing.jsonl); scalars.jsonl adds the share of prior-
                          origin and image-origin Gaussians with opacity >= 0.5 and torch.cuda.max_memory_reserved.
  Losses, g_p, u_i, protection, density control, the seven switches and the base optimisation are r11's.
--- r11 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r11 (JointBuildGS PHD-MAIN-PREP-DISCARD-RULE-v1).

r11 = r10 calling the shared module src/phd/prior_propagation_v5 (the one implementation of the measurement and the training:
registration, party-wall caps and fixed runs moved in from the prep measure; the rules r10 calls are v3's, byte-identical), plus
  (r11-1) discard rule  : --jbgs_rule (rules.RULES, default 'current' = r10). Variants other than 'current' read the stage-1
                          per-(patch, view) tallies (--jbgs_prop_pairs) and the gathered support ids (--jbgs_prop_knn); pixels
                          without a patch take their own mark at the rule's threshold from the mark-code maps
                          (--jbgs_markcode_dir); the loss band stays at tau.
  (r11-2) switches      : --jbgs_sw_<name> 1/0 for switches.NAMES (default 1 = the method, r10 behaviour):
                          confidence_mask 0 -> A and M from <maps_root>/conf_photometric, mvs_photometric; the product's states
                          and votes of the tag '<tag>_maskoff' and the mark maps '<markmap_dir>_maskoff';
                          judgment 0 -> every patch judgment agree and g_p = 1 everywhere; propagation 0 -> missing patches
                          'insufficient'; prior_band 0 -> rho = |r|; protection 0 -> no protection mask; init_exclusion 0 ->
                          points of missing patches judged conflict are planted; prior 0 -> no prior-origin Gaussians and no
                          prior depth term.
  (r11-3) records       : meta.json and init_report.json carry the switches and the rule; init_report adds the MVS-term
                          weight check (A at the pixels with an MVS depth) and the prior-term presence.
--- r10 text follows ---
Judgment-guided stage-2 optimization for GeoGS, revision r10 (JointBuildGS PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).

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

try:  # r12: the shared module is copied into the fork root as src/phd/prior_propagation_v6 (build_fork_r12.py)
    from src.phd.prior_propagation_v6 import conversion as ppc
    from src.phd.prior_propagation_v6 import locations as ppl
    from src.phd.prior_propagation_v6 import orientation as ppo
    from src.phd.prior_propagation_v6 import rule as ppr
    from src.phd.prior_propagation_v6 import rules as pprules
    from src.phd.prior_propagation_v6 import seat as pps
    from src.phd.prior_propagation_v6 import switches as ppsw
except ImportError:  # pragma: no cover - r6 behaviour stays available without the module
    ppc = ppl = ppo = ppr = pps = pprules = ppsw = None

MODES = ("off", "P", "P0", "I")
ABLATIONS = {   # r13 (stage-2 order 4.2): name -> what 1 changes
    "loss_judgment": "the prior depth term ignores the judgment (g_p = 1 on every prior pixel); bands kept",
    "density_judgment": "split / clone / prune exemption = prior & E < threshold & u <= bound, judgment not read; gradient protection keeps it",
    "tolerance_band": "rho(r) = min(|r|, hi tau): no tolerance band, truncation beyond hi tau kept",
}
FIXES = {   # r16 (PHD-MAIN-FIXTEST-v1): name -> what 1 changes (0 = r15)
    "prior_share_band": "the prior depth term's tolerance band ends at w (--jbgs_prior_width_dir) instead of tau; pull band w .. hi tau",
    "own_depth_release": "missing patches read a borrowed conflict / mixed judgment as agree in every path; their pixels are not truncated",
}
ORIGIN_IMAGE, ORIGIN_PRIOR = 0, 1
LABELS = ("preserve", "correct", "undecided", "other")
REVISION = "r17"


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
    # r11: discard-rule variants and ablation switches (shared module v5)
    g.add_argument("--jbgs_rule", default="auto", help="r12: discard rule: auto (default of the prior kind, prior_propagation_v6.rules.default_rule) "
                   "or a rules.RULES name; r11's default was current")
    g.add_argument("--jbgs_prior_kind", default="", choices=["", "LoD2", "ALS", "DSM"], help="r12: prior kind (default: the store's prior_kind)")
    g.add_argument("--jbgs_prior_shift", type=float, nargs=3, default=None, help="r12: the registration shift of the product; the store's frame_shift must equal it")
    g.add_argument("--jbgs_seed", type=int, default=0, help="r12: 0 = safe_state's seed (r11); other values re-seed random / numpy / torch after safe_state")
    g.add_argument("--jbgs_prop_pairs", default="", help="r11: unit_view_pairs.npz of the stage-1 product (rule variants)")
    g.add_argument("--jbgs_prop_knn", default="", help="r11: knn.npz of the stage-1 product (rule variants)")
    g.add_argument("--jbgs_markcode_dir", default="", help="r11: per-view mark codes (threshold index at which a pixel turns agree)")
    for _n in ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior"):
        g.add_argument(f"--jbgs_sw_{_n}", type=int, default=1, help=f"r11 switch {_n}: 1 = on (the method), 0 = off")
    for _n, _h in ABLATIONS.items():   # r13: ablation flags, 0 = r12
        g.add_argument(f"--jbgs_ablate_{_n}", type=int, default=0, choices=[0, 1], help=f"r13 ablation {_n}: {_h} (0 = r12)")
    g.add_argument("--jbgs_memlog_from", type=int, default=0, help="r14-3: first iteration of monitor/memlog.jsonl (0 = off)")
    g.add_argument("--jbgs_memlog_to", type=int, default=0, help="r14-3: last iteration of monitor/memlog.jsonl")
    g.add_argument("--jbgs_memlog_every", type=int, default=100, help="r14-3: interval of monitor/memlog.jsonl")
    for _n, _h in FIXES.items():   # r16: fixes A and B, 0 = r15
        g.add_argument(f"--jbgs_sw_{_n}", type=int, default=0, choices=[0, 1], help=f"r16 switch {_n}: {_h} (0 = r15)")
    g.add_argument("--jbgs_prior_width_dir", default="", help="r16-A: per-view maps of the band end w (metres of camera depth, "
                   "converted like the tau maps); required with --jbgs_sw_prior_share_band 1")

    # r17: opt-in depth-only experiment. The default executes the r16 path.
    g.add_argument("--jbgs_sw_depth_loss", choices=["current", "fixed", "dynamic"], default="current")
    g.add_argument("--jbgs_vfile_dir", default="")
    g.add_argument("--jbgs_vfile_vprior", choices=["now", "gt", "soft"], default="now")
    g.add_argument("--jbgs_depth_lambda", type=float, default=0.0025)


def apply_seed(args):
    """r12-3: called by train.py right after safe_state (which seeds 0). Seed 0 leaves that state as it is (r11)."""
    seed = int(getattr(args, "jbgs_seed", 0))
    if seed != 0:
        import random
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    print(f"[jbgs_judgment] r12 seed {seed}" + (" (safe_state's)" if seed == 0 else " (re-seeded after safe_state)"))
    return seed


def resolve_rule(args):
    """r12-1: (rule name, prior kind, source) from --jbgs_rule, --jbgs_prior_kind and the store's prior_kind."""
    kind_arg = getattr(args, "jbgs_prior_kind", "") or ""
    kind_store = ""
    sp = getattr(args, "jbgs_prop_store", "")
    if sp:
        with np.load(sp, allow_pickle=False) as z:
            kind_store = str(z["prior_kind"]) if "prior_kind" in z.files else ""
    if kind_arg and kind_store and kind_arg != kind_store:
        raise RuntimeError(f"--jbgs_prior_kind {kind_arg} differs from the store's prior_kind {kind_store}")
    kind = kind_arg or kind_store
    name = getattr(args, "jbgs_rule", "auto")
    if name in ("", "auto", None):
        if not kind:
            if sp:
                raise RuntimeError("--jbgs_rule auto needs the prior kind (--jbgs_prior_kind or the store's prior_kind)")
            return "current", kind, "auto without a product store: nothing to apply (current)"
        return pprules.default_rule(kind), kind, f"auto: default of {kind} (prior_propagation_v6.rules.DEFAULT_BY_PRIOR)"
    return pprules.resolve(name, kind or "LoD2"), kind, "given"


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


def plain_prior_loss(D, P, tau, w, denom=None):
    """r11 switch prior_band off: sum w |D-P| over the prior pixels (tau finite) with w > 0 -- no band, no truncation.
    Returns (loss, n_valid, n_hole, n_beyond = 0)."""
    valid_t = torch.isfinite(P) & (P > 0) & torch.isfinite(tau) & (w > 0)
    rendered = torch.isfinite(D) & (D > 0)
    valid = valid_t & rendered
    n_hole = int((valid_t & ~rendered).sum())
    n = int(valid.sum())
    if n == 0:
        return torch.zeros((), device=D.device), 0, n_hole, 0
    ww = w[valid]
    den = (ww.sum() + 1e-9) if denom is None else denom
    return (torch.abs(D[valid] - P[valid]) * ww).sum() / den, n, n_hole, 0


def rho_noband(r, tau, hi=4.0):
    """r13-3: rho(r) = |r| (|r| <= hi*tau), hi*tau beyond: the pull band widened to start at 0; gradient 0 beyond hi*tau."""
    return torch.minimum(torch.abs(r), hi * tau)


def rho_plain(r, tau, hi=4.0):
    """r11 switch prior_band off: rho(r) = |r| (for the code test of the penalty shape)."""
    return torch.abs(r)


def protection_mask(sw_protection, prior, E, threshold, u, bound, patch_judgment):
    """r11: eq. (7) as r9/r10 (rule.protected), or no protection at all when the switch is off."""
    lock, low, near, conflict = ppr.protected(prior, E, threshold, u, bound, patch_judgment)
    if not sw_protection:
        lock = torch.zeros_like(lock)
    return lock, low, near, conflict


def rho_band(r, tau, hi, lo=None, notrunc=None):
    """r16: rho with the band end lo (fix A; None = tau) and without truncation where notrunc (fix B):
    rho = 0 (|r| <= lo); |r| - lo (lo < |r| <= hi tau); hi tau - lo beyond hi tau, except on notrunc where |r| - lo continues.
    With lo None the capped value is the r12 expression (hi - 1) tau, so the pixels outside notrunc equal rho_truncated."""
    b = tau if lo is None else lo
    a = torch.clamp(torch.abs(r) - b, min=0.0)
    cap = (hi - 1.0) * tau if lo is None else hi * tau - b
    capped = torch.minimum(a, cap)
    return capped if notrunc is None else torch.where(notrunc, a, capped)


def truncated_prior_loss(D, P, tau, w, hi=4.0, denom=None, rho=None, lo=None, notrunc=None, extra=None):
    """sum w rho_tau(D-P) over prior pixels (tau finite) with w > 0, divided by `denom` (r6 (5): the pixel count of the
    view) or, when denom is None, by sum w (r5). Returns (loss, n_valid, n_hole, n_beyond). r13: rho = rho_noband for the
    ablation of the tolerance band (None = rho_truncated, r12). r16: lo = per-pixel band end map (fix A), notrunc = per-pixel
    bool map of pixels that are not truncated (fix B); both None = the r15 path (the same expressions). extra (dict) receives
    the r16 pixel counts when a fix is on."""
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
    if lo is None and notrunc is None:   # r15 path
        return ((rho_truncated if rho is None else rho)(r, t, hi) * ww).sum() / den, n, n_hole, n_beyond
    if rho is not None:
        raise RuntimeError("r16 fixes and the r13 tolerance-band ablation cannot be combined")
    lv = lo[valid] if lo is not None else None
    nt = notrunc[valid] if notrunc is not None else None
    if extra is not None:
        ar = torch.abs(r)
        if lv is not None:   # fix A: pixels pulled now that r15 left inside its band (w < |r| <= tau), all weights
            extra["prior_w_to_tau"] = int(((ar > lv) & (ar <= t) & (ww > 0)).sum())
        if nt is not None:   # fix B: missing-patch pixels beyond hi tau (r15 released them)
            extra["prior_beyond_kept"] = int((nt & (ar > hi * t)).sum())
    return (rho_band(r, t, hi, lv, nt) * ww).sum() / den, n, n_hole, n_beyond


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


class HostMaps:
    """r14-1: per-view maps in pinned host memory; reading a view returns a CUDA copy of the stored tensor (values unchanged).
    Writing (self.GW[name] = g) stores a host copy. Readers only index and compare (r13 had the same tensors on the GPU)."""

    def __init__(self, maps=None, device="cuda"):
        self._h, self._dev = {}, device
        for k, v in (maps or {}).items():
            self[k] = v

    def __setitem__(self, k, v):
        v = v.detach()
        if v.is_cuda:
            v = v.cpu()
        self._h[k] = v.pin_memory() if torch.cuda.is_available() else v

    def __getitem__(self, k):
        return self._h[k].to(self._dev, non_blocking=True)

    def get(self, k, default=None):
        return self[k] if k in self._h else default

    def __contains__(self, k):
        return k in self._h

    def __len__(self):
        return len(self._h)

    def __iter__(self):
        return iter(self._h)

    def keys(self):
        return self._h.keys()

    def items(self):
        return ((k, self[k]) for k in self._h)

    def values(self):
        return (self[k] for k in self._h)

    def host_bytes(self):
        return int(sum(v.numel() * v.element_size() for v in self._h.values()))


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
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        self._t_init0 = time.time()                                   # r12-4
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
        self.sw = {n: bool(int(getattr(args, f"jbgs_sw_{n}", 1))) for n in ("confidence_mask", "judgment", "propagation", "prior_band",
                                                                          "protection", "init_exclusion", "prior")}
        self.ab = {n: bool(int(getattr(args, f"jbgs_ablate_{n}", 0))) for n in ABLATIONS}   # r13: all False = r12
        self.fix = {n: bool(int(getattr(args, f"jbgs_sw_{n}", 0))) for n in FIXES}          # r16: all False = r15
        self.own_info = None
        self.rule_name, self.prior_kind, self.rule_source = resolve_rule(args)          # r12-1
        self.timing = (Path(args.model_path) / "monitor" / "timing.jsonl")
        if ppsw is not None and tuple(self.sw) != tuple(ppsw.NAMES):
            raise RuntimeError("switch names differ from the shared module")
        H, W = self.all_cams[0].image_height, self.all_cams[0].image_width
        self.size = (H, W)
        names = [c.image_name for c in self.all_cams]
        root = Path(args.jbgs_maps_root)
        conf_set, mvs_set = ("conf", "mvs") if self.sw["confidence_mask"] else ("conf_photometric", "mvs_photometric")   # r11
        self.A = HostMaps(_load_set(root / conf_set, names, self.size, "cpu"))          # r14-1: host, read as CUDA copies
        self.M = HostMaps(_load_set(root / mvs_set, names, self.size, "cpu"))
        self.P = HostMaps(_load_set(root / args.jbgs_prior_set, names, self.size, "cpu")) if self.mode in ("P", "P0") else {}
        tau_root = Path(args.jbgs_tau_dir) if getattr(args, "jbgs_tau_dir", "") else root / args.jbgs_tau_set   # r7
        self.TAU = HostMaps(_load_set(tau_root, names, self.size, "cpu")) if self.mode == "P" else {}
        self.W, self.w_info = {}, None                                                  # r16-A: band-end maps
        if self.fix["prior_share_band"]:
            if self.mode != "P" or not self.sw["prior_band"] or self.ab["tolerance_band"] or not self.sw["prior"]:
                raise RuntimeError("r16 fix A needs mode P with the prior term, the prior band switch on and no tolerance-band ablation")
            if not getattr(args, "jbgs_prior_width_dir", ""):
                raise RuntimeError("r16 fix A needs --jbgs_prior_width_dir")
            self.W = HostMaps(_load_set(Path(args.jbgs_prior_width_dir), names, self.size, "cpu"))
            self.w_info = self._check_width_maps(args)
        if self.fix["own_depth_release"] and (self.mode != "P" or not getattr(args, "jbgs_prop_store", "")):
            raise RuntimeError("r16 fix B needs mode P with the stage-1 product store (patch states and judgments)")
        self.NOTRUNC = HostMaps()                                                       # r16-B: filled by _g_init
        self.FACE = _load_set(root / "faceid", names, self.size, "cpu", dtype=np.int32)
        self.FV = _load_set(root / "fvert", names, self.size, "cpu")
        self.G = _load_set(root / "gt", names, self.size, "cpu")
        faces = json.loads(Path(args.jbgs_faces_json).read_text()) if args.jbgs_faces_json else {"roof": [], "wall": []}
        self.faces_roof = [int(f) for f in faces.get("roof", [])]
        self.faces_wall = [int(f) for f in faces.get("wall", [])]
        self.tau_v = float(args.jbgs_tau_v)
        self.lambda_mvs = float(args.jbgs_lambda_mvs)
        self.lambda_prior = float(args.jbgs_lambda_prior) if (self.mode in ("P", "P0") and self.sw["prior"]) else 0.0   # r11 switch prior
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
        self.prior_removed = 0
        if not self.sw["prior"]:   # r11 switch prior off: no prior-origin Gaussians (image-only base), no prior term
            pm = gaussians.origin == ORIGIN_PRIOR
            self.prior_removed = int(pm.sum())
            if bool(pm.any()):
                gaussians.prune_points(pm)
            self.init_filter = dict(applied=True, rule="r11 switch prior off: every prior-origin point removed", n_prior_removed=self.prior_removed)
        elif self.mode in ("P", "P0") and getattr(args, "jbgs_prop_store", ""):
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
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        self.init_seconds = time.time() - self._t_init0               # r12-4 (to here: maps, product, seats, first E, g_p)
        self.init_filter["init_seconds"] = round(self.init_seconds, 2)
        if getattr(args, "jbgs_sw_depth_loss", "current") != "current":
            lt_initialize(self)
        meta = dict(mode=self.mode, revision=REVISION, switches=self.sw, ablations=self.ab, rule=self.rule_name, rule_source=self.rule_source, prior_kind=self.prior_kind,
                    fixes=self.fix, prior_width=self.w_info, own_depth=self.own_info,                 # r16 records
                    seed=int(getattr(args, "jbgs_seed", 0)), init_seconds=round(self.init_seconds, 2),
                    store_frame_shift=(self.prop["frame_shift"] if self.prop is not None else None),
                    size=[H, W], views=names, train_views=sorted(self.train_names),
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
        if self.mode in ("P", "P0") and self.sw["prior"]:
            missing = [nm for nm in self.train_names if nm not in self.P]
            if missing:
                raise ValueError(f"prior maps missing for training views: {missing}")
        if self.mode == "P" and self.sw["prior"]:
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

    @torch.no_grad()
    def _check_width_maps(self, args):
        """r16-A: the band-end maps cover every training view, are finite exactly where the tau maps are and never exceed tau."""
        missing = [nm for nm in sorted(self.train_names) if nm not in self.W]
        if missing:
            raise ValueError(f"r16 w maps missing for {len(missing)} training views, e.g. {missing[:3]}")
        n_px = n_lt = n_finite_diff = n_excess = 0
        rmin, rmax = float("inf"), float("-inf")
        for nm in sorted(self.train_names):
            Wv, Tv = self.W._h[nm], self.TAU._h[nm]
            fw, ft = torch.isfinite(Wv), torch.isfinite(Tv)
            n_finite_diff += int((fw != ft).sum())
            both = fw & ft
            wv, tv = Wv[both].double(), Tv[both].double()
            n_px += int(both.sum()); n_lt += int((wv < tv).sum()); n_excess += int((wv > tv * (1 + 1e-6)).sum())
            if wv.numel():
                rr = wv / tv
                rmin, rmax = min(rmin, float(rr.min())), max(rmax, float(rr.max()))
        info = dict(dir=str(args.jbgs_prior_width_dir), views=len(self.W), train_views=len(self.train_names), prior_pixels=n_px,
                    narrowed_pixels=n_lt, finite_mismatch_pixels=n_finite_diff, w_above_tau_pixels=n_excess,
                    ratio_w_over_tau_min=rmin, ratio_w_over_tau_max=rmax)
        if n_finite_diff or n_excess:
            raise RuntimeError(f"r16 w maps do not match the tau maps: {info}")
        print(f"[jbgs_judgment] r16 fix A band-end maps: {info}")
        return info

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
        fshift = ppl.frame_shift(st)                                   # r12-2: the moved store of the v6 measurement
        if getattr(args, "jbgs_prior_shift", None) is not None and not np.array_equal(fshift, np.asarray(args.jbgs_prior_shift, np.float64)):
            raise RuntimeError(f"store frame_shift {fshift.tolist()} != --jbgs_prior_shift {list(args.jbgs_prior_shift)}")
        tag = args.jbgs_prop_tag if self.sw["confidence_mask"] else f"{args.jbgs_prop_tag}_maskoff"   # r11 switch confidence_mask
        state, vote, E0, ns0 = st[f"state_{tag}"], st[f"vote_{tag}"], st[f"E_{tag}"], st[f"n_seeing_{tag}"]
        q, k, r = args.jbgs_prop_majority, int(args.jbgs_prop_min_evidence), float(args.jbgs_prop_max_distance)
        if args.jbgs_prop_pairs and args.jbgs_prop_knn:   # r12-1: every rule through the tallies and the gathered support ids
            sfx = "" if self.sw["confidence_mask"] else "_maskoff"
            pairs = dict(np.load(args.jbgs_prop_pairs.replace(".npz", f"{sfx}.npz")))
            kn = np.load(args.jbgs_prop_knn.replace(".npz", f"{sfx}.npz"))
            mis, kd, kid = kn["mis"], kn["k_dist"], kn["k_id"]
            st_r, vote_r, J, _ = pprules.apply(pairs, len(state), mis, kd, kid, self.rule_name, q, k, r)
            if not np.array_equal(st_r, state):
                raise RuntimeError("rule tallies give other states than the product")
            if self.rule_name == "current" and not np.array_equal(vote_r, vote):
                raise RuntimeError("the current rule on the tallies gives other votes than the product")
            vote = vote_r
            kv = np.where(kid >= 0, vote[np.maximum(kid, 0)], ppr.V_NONE)
        elif self.rule_name == "current":
            J, (mis, kd, kv) = ppl.propagate(st, state, vote, q, k, r)
        else:
            raise RuntimeError(f"rule {self.rule_name} needs --jbgs_prop_pairs and --jbgs_prop_knn")
        vote, J, J_loc = ppsw.judgment_level(state, vote, J, self.sw)   # r11-2: judgment / propagation switches (identity when on)
        own_rec = {}
        if self.fix["own_depth_release"]:   # r16-B: a borrowed conflict / mixed of a missing patch is read as agree, in every path
            J_before = np.asarray(J).copy()
            changed = (np.asarray(state) == ppr.ST_MISSING) & np.isin(J_before, (ppr.J_CONFLICT, ppr.J_MIXED))
            J = np.where(changed, ppr.J_AGREE, J_before).astype(J_before.dtype)
            J_loc = ppl.location_judgment(state, vote, J)
            own_rec = dict(judgment_before_own_depth=J_before, own_depth_changed=changed)
            self.own_info = dict(rule="missing patch (state 2) with a borrowed conflict (0) or mixed (2) -> agree (1); insufficient (3) and "
                                 "none (-1) unchanged; support / invisible patches unchanged; missing-patch pixels of the prior depth term not truncated",
                                 n_missing=int((np.asarray(state) == ppr.ST_MISSING).sum()), n_changed=int(changed.sum()),
                                 n_changed_from_conflict=int((changed & (J_before == ppr.J_CONFLICT)).sum()),
                                 n_changed_from_mixed=int((changed & (J_before == ppr.J_MIXED)).sum()),
                                 area_changed_m2=float(np.asarray(st["loc_area"])[changed].sum()))
            print(f"[jbgs_judgment] r16 fix B: {self.own_info}")
        why = ppr.undetermined_why(state, J, kd, mis, k, r)
        within = kd[:, :k] <= r + 1e-9 if len(mis) else np.zeros((0, k), bool)
        got = np.full(len(state), -1, np.int16); ncf = np.full(len(state), -1, np.int16)
        if len(mis):
            got[mis] = within.sum(1); ncf[mis] = ((kv[:, :k] == ppr.V_CONFLICT) & within).sum(1)
        np.savez_compressed(self.mon / "locations.npz", state=state, vote=vote, judgment=J, unit_judgment=J_loc, why=why,
                            why_codes=np.array([ppr.WHY_NAMES[i] for i in sorted(ppr.WHY_NAMES)]), E=E0, n_seeing=ns0,
                            n_supporting=st[f"n_supporting_{tag}"], evidence_within=got, evidence_conflict=ncf,
                            surface_ext=st["surf_ext"][st["loc_surface"]], kind=st["loc_kind"], area=st["loc_area"],
                            center=st["loc_center"].astype(np.float32), **own_rec)
        dev = "cuda"
        st_num = {kk: vv for kk, vv in st.items() if np.asarray(vv).dtype.kind not in ("U", "S", "O")}   # r12: v6 stores carry text keys (prior_kind)
        P = dict(store=st, st_t=pps.to_torch(st_num, dev), state=torch.as_tensor(state, device=dev).long(),
                 vote=torch.as_tensor(vote, device=dev).long(), E0=torch.as_tensor(E0, device=dev).float(),
                 ns0=torch.as_tensor(ns0, device=dev).float(), J=torch.as_tensor(J, device=dev).long(),
                 J_loc=torch.as_tensor(J_loc, device=dev).long(), prop_seconds=time.time() - t0, frame_shift=fshift.tolist())
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
        drop = conflict if self.sw["init_exclusion"] else torch.zeros_like(conflict)   # r11 switch init_exclusion
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
                    store=str(args.jbgs_prop_store), tag=tag, majority=q, min_evidence=k, max_distance=r, discard_rule=self.rule_name,
                    rule_source=self.rule_source, prior_kind=self.prior_kind, store_frame_shift=fshift.tolist(),
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
        if own_rec:   # r16-B record: the propagated judgments before the rewrite
            jb = own_rec["judgment_before_own_depth"]
            info["missing_judgments_before_own_depth"] = {ppr.J_NAMES[j]: int((jb[state == ppr.ST_MISSING] == j).sum()) for j in ppr.J_NAMES}
            info["own_depth"] = self.own_info
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
        self.GW, self.g_counts = HostMaps(), {}          # r14-1: g_p kept on the host
        if not args.jbgs_locmap_dir or not args.jbgs_markmap_dir:
            raise ValueError("r8 needs --jbgs_locmap_dir and --jbgs_markmap_dir")
        names = sorted(self.train_names)
        LM = HostMaps(_load_set(Path(args.jbgs_locmap_dir), names, self.size, "cpu", dtype=np.int32))   # r14-2: one view at a time
        if getattr(args, "jbgs_sw_depth_loss", "current") != "current":
            self.lt_locations = LM  # r17: retain the existing host maps; patch values alone live on GPU
        sfx = "" if self.sw["confidence_mask"] else "_maskoff"
        t_rule = pprules.RULES[self.rule_name]["t"] if pprules is not None else 1.0
        if t_rule == 1.0:
            MK = HostMaps(_load_set(Path(args.jbgs_markmap_dir + sfx), names, self.size, "cpu", dtype=np.int32))
            mark_of = MK.__getitem__
        else:   # r11-1: own mark of a pixel without a patch at the rule's threshold (mark code <= threshold index -> agree)
            ti = pprules.THRESHOLDS.index(float(t_rule))
            MC = HostMaps(_load_set(Path(args.jbgs_markcode_dir + sfx), names, self.size, "cpu", dtype=np.int32))
            MK = MC

            def mark_of(kk):   # r14-2: r13's thresholded mark of one view (the same torch.where), on the GPU
                v = MC[kk]
                return torch.where(v < 0, torch.full_like(v, ppr.MARK_NONE),
                                   torch.where(v <= ti, torch.full_like(v, ppr.MARK_AGREE), torch.full_like(v, ppr.MARK_CONFLICT)))
        Jl_t = self.prop["J_loc"]
        st_t = self.prop["state"]
        for name in names:
            lm = LM[name].long(); mk = mark_of(name).long(); A = self.A[name]; P = self.P.get(name)
            located = lm >= 0
            Jl = torch.full_like(lm, ppr.J_NONE); Jl[located] = Jl_t[lm[located]]
            if self.fix["own_depth_release"]:   # r16-B: pixels of missing patches (any judgment) are not truncated
                miss = torch.zeros_like(located)
                miss[located] = st_t[lm[located]] == ppr.ST_MISSING
                self.NOTRUNC[name] = miss
            off = ppr.prior_term_off(located, Jl, A, mk)
            if not self.sw["judgment"]:   # r11 switch judgment off: nothing discarded anywhere
                off = torch.zeros_like(off)
            if self.ab["loss_judgment"]:   # r13-1: the depth term alone ignores the judgment (the patch tables stay)
                off = torch.zeros_like(off)
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
                if self.fix["own_depth_release"]:   # r16-B records
                    c["missing_px"] = int((pp & miss).sum()); c["missing_px_g1"] = int((pp & miss & (g > 0)).sum())
                if self.fix["prior_share_band"] and name in self.W:   # r16-A records: prior pixels whose band end narrowed
                    Wv, Tv = self.W[name], self.TAU.get(name)
                    if Tv is not None:
                        c["w_lt_tau_px"] = int((pp & torch.isfinite(Wv) & torch.isfinite(Tv) & (Wv < Tv)).sum())
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
        if getattr(self.args, "jbgs_sw_depth_loss", "current") != "current":
            return lt_losses(self, cam_name, render_pkg)
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
        if self.mode in ("P", "P0") and self.sw["prior"]:   # r11 switch prior off: no prior term
            P = self.P.get(cam_name)
            if P is not None:
                if self.mode == "P":
                    gw = getattr(self, "GW", {}).get(cam_name)        # r8-1: g_p (eq. 4); r6 path: 1 - c_p
                    w = gw if gw is not None else 1.0 - A
                    if self.sw["prior_band"]:
                        lo = self.W[cam_name] if self.fix["prior_share_band"] else None                      # r16-A
                        nt = self.NOTRUNC.get(cam_name) if self.fix["own_depth_release"] else None          # r16-B
                        ex = {} if (lo is not None or nt is not None) else None
                        prior, n, hole, beyond = truncated_prior_loss(D, P, self.TAU[cam_name], w, self.args.jbgs_trunc_hi, denom,
                                                                      rho=rho_noband if self.ab["tolerance_band"] else None,   # r13-3
                                                                      lo=lo, notrunc=nt, extra=ex)
                        if ex:
                            stats.update(ex)
                    else:   # r11 switch prior_band off: rho = |r|
                        prior, n, hole, beyond = plain_prior_loss(D, P, self.TAU[cam_name], w, denom)
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
        torch.cuda.synchronize()
        self._t_e0 = time.time()                                      # r12-4: seconds of this re-read (E.jsonl)
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
        torch.cuda.synchronize()
        row["seconds"] = time.time() - self._t_e0
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
        lock, low, near, conflict = protection_mask(self.sw["protection"], prior, E, a.jbgs_e_threshold, u, bound, Jl)   # r11 switch protection
        far = low & ~near
        conf_sup = conflict & (St == ppr.ST_SUPPORT)
        conf_mis = conflict & (St == ppr.ST_MISSING)
        if self.mode == "P":
            gaussians.set_frozen_mask(lock)
            self.floor_now(gaussians)
        else:
            lock = torch.zeros_like(prior)
        dens = None
        if self.ab["density_judgment"] and self.mode == "P":   # r13-2: density control's own exemption, eq. 7 without the judgment
            dens = (low & near) if self.sw["protection"] else torch.zeros_like(lock)
            gaussians.set_density_mask(dens)
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
        if dens is not None:   # r13-2 records
            row["n_density_exempt"] = int(dens.sum()); row["n_density_exempt_conflict"] = int((dens & conflict).sum())
            row["n_density_exempt_not_protected"] = int((dens & ~lock).sum())
        torch.cuda.synchronize()
        row["seconds"] = time.time() - self._t_e0                      # r12-4
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
        rep = dict(revision=REVISION, switches=self.sw, ablations=self.ab, rule=self.rule_name, rule_source=self.rule_source, prior_kind=self.prior_kind,
                   fixes=self.fix, prior_width=self.w_info, own_depth=self.own_info,                 # r16 records
                   seed=int(getattr(self.args, "jbgs_seed", 0)), init_seconds=round(self.init_seconds, 2), init=self.init_filter, first_E=row)
        # r11: MVS-term weight check (A at the pixels with an MVS depth) and the prior term's presence
        wa = dict(pixels_with_mvs_depth=0, of_them_A1=0, A1_without_mvs_depth=0)
        for nm in sorted(self.train_names):
            Mv, Av = self.M.get(nm), self.A.get(nm)
            if Mv is None or Av is None:
                continue
            hasd = torch.isfinite(Mv) & (Mv > 0); a1 = Av > 0.5
            wa["pixels_with_mvs_depth"] += int(hasd.sum()); wa["of_them_A1"] += int((hasd & a1).sum()); wa["A1_without_mvs_depth"] += int((a1 & ~hasd).sum())
        rep["mvs_term_weight"] = wa
        rep["prior_term"] = dict(lambda_prior=self.lambda_prior, prior_maps=len(self.P), switch_prior=self.sw["prior"],
                                 n_prior_now=int((gaussians.origin == ORIGIN_PRIOR).sum()), n_prior_removed=self.prior_removed)
        if self.prop is not None and self.g_located is not None:
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

    @torch.no_grad()
    def memlog(self, iteration, camera, gaussians, render_pkg):
        """r14-3: records only (default off). The tiles the visible Gaussians cover are re-counted from the returned radii and the
        projected centres (project_points, as the rasterizer) with the rasterizer's getRect over 16 x 16 tiles."""
        a = self.args
        lo, hi, ev = int(getattr(a, "jbgs_memlog_from", 0)), int(getattr(a, "jbgs_memlog_to", 0)), max(int(getattr(a, "jbgs_memlog_every", 100)), 1)
        if lo <= 0 or iteration < lo or iteration > hi or (iteration - lo) % ev:
            return
        radii = render_pkg["radii"]
        vis = radii > 0
        r = radii[vis].float()
        W, H = int(camera.image_width), int(camera.image_height)
        gx, gy = (W + 15) // 16, (H + 15) // 16
        u, v, _ = project_points(gaussians.get_xyz[vis].detach(), camera)
        rr = radii[vis].to(u.dtype)
        x0 = torch.clamp(torch.floor((u - rr) / 16).long(), 0, gx); x1 = torch.clamp(torch.floor((u + rr + 15) / 16).long(), 0, gx)
        y0 = torch.clamp(torch.floor((v - rr) / 16).long(), 0, gy); y1 = torch.clamp(torch.floor((v + rr + 15) / 16).long(), 0, gy)
        tiles = int(((x1 - x0).clamp_min(0) * (y1 - y0).clamp_min(0)).sum())
        free, total = torch.cuda.mem_get_info()
        rec = dict(iteration=iteration, view=camera.image_name, n=int(gaussians.get_xyz.shape[0]), visible=int(vis.sum()),
                   radius_q99=float(torch.quantile(r, 0.99)) if r.numel() else 0.0, radius_max=float(r.max()) if r.numel() else 0.0,
                   tiles_covered=tiles, allocated_gib=torch.cuda.memory_allocated() / 2 ** 30, reserved_gib=torch.cuda.memory_reserved() / 2 ** 30,
                   max_allocated_gib=torch.cuda.max_memory_allocated() / 2 ** 30, device_used_gib=(total - free) / 2 ** 30)
        with (self.mon / "memlog.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")

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
                   opacity_share_ge05_prior=float((op[prior] >= 0.5).float().mean()) if bool(prior.any()) else None,      # r12-4
                   opacity_share_ge05_image=float((op[~prior] >= 0.5).float().mean()) if bool((~prior).any()) else None,
                   max_reserved_gb=torch.cuda.max_memory_reserved() / 1e9,
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
        """r12-4: the r11 read-out (_readout_r11) timed (monitor/timing.jsonl; record keeping, not the method)."""
        torch.cuda.synchronize(); t0 = time.time()
        try:
            return self._readout_r11(iteration, gaussians, render, pipe, background, snapshot=snapshot, dump=dump, stop_check=stop_check)
        finally:
            torch.cuda.synchronize()
            with self.timing.open("a") as f:
                f.write(json.dumps(dict(kind="readout", iteration=iteration, snapshot=bool(snapshot), dump=bool(dump), seconds=time.time() - t0)) + "\n")

    @torch.no_grad()
    def _readout_r11(self, iteration, gaussians, render, pipe, background, snapshot=False, dump=False, stop_check=True):
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
                self._readout_r11(iteration, gaussians, render, pipe, background, snapshot=True, dump=True, stop_check=False)
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


# ---------------- PHD-MAIN-LOSSTRAIN-v1 r17 opt-in depth terms ----------------
"""Source appended to r16 jbgs_judgment.py by build_r17.py; not imported at runtime.

Inputs are a reviewed, stage-1-indexed values.npz plus manifest.json. The
manifest must explicitly pass both coverage gates. GT surfaces/labels and
precomputed optimum z are never loaded by these training functions.
"""

def lt_term(depth, target, sigma, validity, mode):
    """Unweighted one-source pixel loss; autograd follows depth only."""
    target, sigma, validity = target.detach(), sigma.detach(), validity.detach()
    residual = (depth - target) / sigma
    if mode == "fixed":
        return 0.5 * validity * residual.square()
    if mode != "dynamic":
        raise ValueError(mode)
    log_in = torch.log(validity) - torch.log(sigma) - 0.5 * math.log(2 * math.pi) - 0.5 * residual.square()
    log_out = torch.log1p(-validity) + math.log(0.1)
    return -torch.logaddexp(log_in, log_out)


def lt_initialize(j):
    """Load one array per patch; retain the existing host pixel-to-patch maps."""
    import hashlib
    a = j.args
    if j.mode != "P" or j.sw["judgment"] or not j.sw["prior"] or a.jbgs_depth_norm != "pixels":
        raise ValueError("LOSSTRAIN needs mode P, judgment=0, prior=1 and pixels normalization")
    if any(j.ab.values()) or any(j.fix.values()):
        raise ValueError("LOSSTRAIN must retain the nojudge ablation/fix defaults")
    root = Path(a.jbgs_vfile_dir)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("patch_join_gate") != "PASS" or manifest.get("pixel_join_gate") != "PASS":
        raise RuntimeError("LOSSTRAIN_STOP: patch/pixel connection below the frozen gate")
    values = root / "values.npz"
    digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if digest(values) != manifest["values_sha256"] or digest(a.jbgs_prop_store) != manifest["store_sha256"]:
        raise RuntimeError("LOSSTRAIN_STOP: linked values or stage-1 store hash changed")
    with np.load(values, allow_pickle=False) as z, np.load(a.jbgs_prop_store, allow_pickle=False) as st:
        if not np.array_equal(z["centre"], st["loc_center"]):
            raise RuntimeError("LOSSTRAIN_STOP: stage-1 patch order changed")
        fallback = ~z["joined"].astype(bool)
        vp = z["v_prior_" + a.jbgs_vfile_vprior].copy()
        vp[fallback] = z["v_prior_now"][fallback]
        arrays = {k: z[k] for k in ("sigma_prior", "sigma_mvs", "v_mvs", "normal")}
        arrays["v_prior"] = vp
        arrays["fallback"] = fallback
    n = len(vp)
    if any(len(x) != n for x in arrays.values()):
        raise ValueError("LOSSTRAIN values length mismatch")
    j.lt_values = {k: torch.as_tensor(x, device="cuda") for k, x in arrays.items()}
    j.lt_cameras = {c.image_name: c for c in j.all_cams}
    j.lambda_mvs = j.lambda_prior = float(a.jbgs_depth_lambda)
    if not math.isfinite(j.lambda_prior) or j.lambda_prior <= 0:
        raise ValueError("LOSSTRAIN lambda must be finite and positive")
    (j.mon / "losstrain_inputs.json").write_text(json.dumps(dict(
        mode=a.jbgs_sw_depth_loss, vprior=a.jbgs_vfile_vprior, depth_lambda=j.lambda_prior,
        manifest=manifest, fallback_patches=int(fallback.sum()), scientific_verdict=None), indent=2))


def lt_losses(j, cam_name, render_pkg):
    D = render_pkg["surf_depth"].squeeze(0)
    P, M, A = j.P[cam_name], j.M[cam_name], j.A[cam_name]
    loc = j.lt_locations[cam_name].long()
    table = j.lt_values
    has = (loc >= 0) & (loc < len(table["v_prior"]))
    eligible = has & torch.isfinite(P) & (P > 0)
    if bool((eligible & ~torch.isfinite(D)).any()):
        raise RuntimeError("LOSSTRAIN_STOP: nonfinite rendered prior-patch depth")
    yy, xx = torch.where(eligible)
    ids = loc[eligible]
    zero = D.reshape(-1)[:0].sum()  # differentiable zero, including an empty view
    if not len(ids):
        stats = dict(n_px=D.numel(), prior_n=0, mvs_n=0, prior_hole=0, mvs_hole=0, prior_beyond=0)
        j.last_stats = stats
        return zero, zero, stats
    cam = j.lt_cameras[cam_name]
    proj = cam.projection_matrix.T
    H, W = D.shape
    fx, fy = proj[0, 0] * W / 2, proj[1, 1] * H / 2
    cx, cy = proj[0, 2] * W / 2 + (W - 1) / 2, proj[1, 2] * H / 2 + (H - 1) / 2
    ray_cam = torch.stack(((xx - cx) / fx, (yy - cy) / fy, torch.ones_like(xx, dtype=D.dtype)), 1)
    ray_world = ray_cam @ cam.world_view_transform.inverse()[:3, :3]
    ray_world = torch.nn.functional.normalize(ray_world, dim=1)
    normal = table["normal"][ids].to(D.dtype)
    good_normal = torch.isfinite(normal).all(1) & (torch.abs(normal.norm(dim=1) - 1) < 1e-4)
    if not bool(good_normal.all()):
        raise RuntimeError("LOSSTRAIN_STOP: missing/nonunit patch normal; no imputation")
    cos = (ray_world * normal).sum(1).abs().clamp_min(0.25)
    sp = table["sigma_prior"][ids].to(D.dtype) / cos
    vp = table["v_prior"][ids].to(D.dtype)
    if not bool((torch.isfinite(sp) & (sp > 0) & torch.isfinite(vp) & (vp > 0) & (vp < 1)).all()):
        raise RuntimeError("LOSSTRAIN_STOP: invalid prior sigma or validity")
    mode = j.args.jbgs_sw_depth_loss
    prior = lt_term(D[eligible], P[eligible], sp, vp, mode).sum() / D.numel()
    vm = table["v_mvs"][ids].to(D.dtype)
    sm = table["sigma_mvs"][ids].to(D.dtype) / cos
    obs = torch.isfinite(M[eligible]) & (M[eligible] > 0) & (A[eligible] > 0) & torch.isfinite(vm)
    if bool(obs.any()) and not bool((torch.isfinite(sm[obs]) & (sm[obs] > 0) & (vm[obs] > 0) & (vm[obs] < 1)).all()):
        raise RuntimeError("LOSSTRAIN_STOP: invalid available MVS sigma or validity")
    mvs = lt_term(D[eligible][obs], M[eligible][obs], sm[obs], vm[obs], mode).sum() / D.numel() if bool(obs.any()) else zero
    stats = dict(n_px=int(D.numel()), prior_n=int(eligible.sum()), mvs_n=int(obs.sum()),
                 prior_hole=int((D[eligible] <= 0).sum()), mvs_hole=int((D[eligible][obs] <= 0).sum()),
                 prior_beyond=0, fallback_n=int(table["fallback"][ids].sum()))
    j.last_stats = stats
    return mvs, prior, stats
