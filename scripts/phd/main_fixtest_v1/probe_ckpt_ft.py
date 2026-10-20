"""PHD-MAIN-FIXTEST-v1 6.4: stage 3's probe (scripts/phd/main_stage3_v1/probe_ckpt_s3.py) for forks r15 and r16 alike, with these
records added (no decision of the fork is changed; every r16 attribute is read with getattr, so r15 runs it too):
  per Gaussian  g_state (the state of the patch the Gaussian sits on, -1 none), g_loc, g_Jl (its patch judgment)
  per view      gw_<view>   pixels whose depth-term weight g_p > 0
                gthi_<view> prior pixels with |D - P| / tau_p > hi (the truncation band)
                wtau_<view> (fix A on) prior pixels with g_p > 0 and w_p < |D - P| <= tau_p (newly pulled by fix A)
                miss_<view> (fix B on) pixels of missing patches (not truncated under fix B)
  totals        on_w_tau (fix A), on_miss_gt_hi and on_miss (fix B) in depth_term
The out-of-memory radii record of stage 3 (r15 only, records) is not run. jointbuildgs:geogs-conf-guided-v1, /source = the fork
read-only, GPU. Stage 3's text follows.

PHD-MAIN-STAGE3-v1 5.3-4: the fix task's probe (scripts/phd/main_fix_v1/probe_ckpt_fix.py, copied unchanged: stage 2's probe plus the
loss values of every training view) for forks r14 and r15 alike, with one record added AFTER the probe's own outputs are written: when the
fork has the r15 out-of-memory record (jbgs_oom_record), its Python screen radii (surfel_radii) are compared with the rasterizer's
returned radii on every training view (<dir>/oom_radii.json; records only). No change to either fork; jointbuildgs:geogs-conf-guided-v1,
/source = the fork read-only, GPU.

  python probe_ckpt.py --probe_out <dir> --probe_ply <point_cloud.ply> --probe_ref_init <init_points.npz> [--probe_iteration 15000]
                       -- <the training command's train.py arguments (the stage-1 command with the switch / value of the run)>

The fork's train.py runs unchanged up to the construction of jbgs_judgment.Judgment (scene, maps, the stage-1 product, propagation,
seating, planting, g_p, i.e. the dry init). Right after it this probe (a wrapper around Judgment.__init__, the class is otherwise
untouched):
  1. loads the checkpoint PLY (positions, colours, opacity, scale, rotation, origin, init_id) into the Gaussians and rebuilds the
     optimizer (training_setup); the checkpoint's init_id (ids of the reference run's planted points, --probe_ref_init = that run's
     monitor/init_points.npz) is mapped to this initialisation's ids through the original point order (a point planted by the
     reference run but not by this one gets -1, counted);
  2. re-reads the Gaussian confidence and the protection exactly as the training does at the start of a re-read iteration
     (Judgment.update_E at --probe_iteration, the current render as the occluder) -> gradient protection = frozen_mask (lr x
     lock_lr_scale, opacity floor, reset exemption), density-control exemption = density_exempt() (r13) / frozen_mask (r12);
  3. renders every training view once and takes the gradient of the prior depth term with respect to the rendered depth
     (Judgment.losses on a leaf copy of surf_depth): pixels where the term acts (gradient != 0), split by |D - P| / tau_p into
     < 1, 1 - hi, > hi (hi = --jbgs_trunc_hi), plus the MVS-term pixels (A > 0 and an MVS depth) as a control;
  4. density decisions: prune candidates by opacity (< opacity_cull, the base rule) and by world size (> 0.1 x extent), and the
     candidates the exemption keeps (screen size and the gradient statistics are not in a checkpoint: not evaluated).
Writes <dir>/probe.npz (masks, packed per-view pixel masks, gradients) and <dir>/probe.json, then exits before training.
scientific_verdict: null."""
import json
import os
import runpy
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/source")
os.chdir("/source")
import torch  # noqa: E402

import jbgs_judgment as JJ  # noqa: E402

ARGS = {}
argv = sys.argv[1:]
cut = argv.index("--")
own, train_argv = argv[:cut], argv[cut + 1:]
for i in range(0, len(own), 2):
    ARGS[own[i].lstrip("-")] = own[i + 1]
OUTD = Path(ARGS["probe_out"])
if ARGS.get("probe_no_floor") == "1":
    # PHD-MAIN-FIXTEST-v1 6.4 (check only): the opacity floor that a re-read applies to the Gaussians it newly protects is switched off, so
    # that the render after the re-read equals the checkpoint's in every variant; the protection and every other decision are unchanged
    JJ.Judgment.floor_now = lambda self, gaussians: None
OUTD.mkdir(parents=True, exist_ok=True)
IT = int(ARGS.get("probe_iteration", 15000))
_orig_init = JJ.Judgment.__init__


def _pack(m):
    return np.packbits(m.detach().cpu().numpy().astype(bool).reshape(-1))


@torch.no_grad()
def _load_ckpt(self, gaussians, opt):
    gaussians.load_ply(ARGS["probe_ply"])
    n = gaussians.get_xyz.shape[0]
    gaussians.max_radii2D = torch.zeros(n, device="cuda")
    gaussians.training_setup(opt)
    ref = np.load(ARGS["probe_ref_init"])
    new = np.load(self.mon / "init_points.npz")
    if len(ref["planted"]) != len(new["planted"]) or not np.array_equal(ref["origin"], new["origin"]):
        raise RuntimeError("the reference initialisation is not the same initial cloud")
    ref_idx = np.nonzero(ref["planted"])[0]
    pos = np.full(len(new["planted"]), -1, np.int64)
    pos[np.nonzero(new["planted"])[0]] = np.arange(int(new["planted"].sum()))
    mapping = pos[ref_idx]
    ids = gaussians.init_id.long().cpu().numpy()
    has = ids >= 0
    if has.any() and ids[has].max() >= len(mapping):
        raise RuntimeError("checkpoint init_id beyond the reference run's planted points")
    out = ids.copy()
    out[has] = mapping[ids[has]]
    gaussians.init_id = torch.as_tensor(out, dtype=torch.int32, device="cuda")
    return dict(n=int(n), n_prior=int((gaussians.origin == JJ.ORIGIN_PRIOR).sum()), n_with_init_id=int(has.sum()),
                n_init_id_unplanted_here=int((has & (out < 0)).sum()), ref_planted=int(ref["planted"].sum()),
                here_planted=int(new["planted"].sum()), same_planted=bool(np.array_equal(ref["planted"], new["planted"])))


def _probe(self, args, opt, scene, gaussians):
    t0 = time.time()
    info = dict(revision=JJ.REVISION, switches=self.sw, ablations=getattr(self, "ab", None), fixes=getattr(self, "fix", None), rule=self.rule_name,
                no_floor=ARGS.get("probe_no_floor") == "1",
                probe_iteration=IT, ply=ARGS["probe_ply"], ref_init=ARGS["probe_ref_init"], trunc_hi=float(args.jbgs_trunc_hi),
                e_interval=int(args.jbgs_e_interval), max_distance=float(args.jbgs_prop_max_distance))
    info["checkpoint"] = _load_ckpt(self, gaussians, opt)
    # 2. the re-read of a re-read iteration (render as occluder)
    self.E_calls = max(self.E_calls, 1)
    self.cur_iter = IT
    row = self.update_E(IT, gaussians)
    lock = gaussians.frozen_mask.clone() if gaussians.frozen_mask is not None else torch.zeros(gaussians.get_xyz.shape[0], dtype=torch.bool, device="cuda")
    dens = gaussians.density_exempt() if hasattr(gaussians, "density_exempt") else gaussians.frozen_mask
    dens = dens.clone() if dens is not None else torch.zeros_like(lock)
    reset_ex = self.exempt_mask(gaussians)
    reset_ex = reset_ex.clone() if reset_ex is not None else torch.zeros_like(lock)
    prior = gaussians.origin == JJ.ORIGIN_PRIOR
    op = gaussians.get_opacity.squeeze(1)
    cand_op = op < float(opt.opacity_cull)
    cand_ws = gaussians.get_scaling.max(dim=1).values > 0.1 * float(scene.cameras_extent)
    cand = cand_op | cand_ws
    Jl = self.g_Jl if self.g_Jl is not None else torch.full_like(prior, -1, dtype=torch.long)
    conflict = Jl == JJ.ppr.J_CONFLICT
    info["re_read"] = {k: row[k] for k in ("n", "n_prior", "n_located", "n_locked", "n_prior_E_below", "n_conflict_excluded", "n_prior_far") if k in row}
    info["decisions"] = dict(
        gradient_protected=int(lock.sum()), gradient_protected_on_conflict=int((lock & conflict).sum()),
        density_exempt=int(dens.sum()), density_exempt_on_conflict=int((dens & conflict).sum()), density_exempt_not_protected=int((dens & ~lock).sum()),
        reset_exempt=int(reset_ex.sum()), prune_candidates=int(cand.sum()), prune_candidates_opacity=int(cand_op.sum()),
        prune_kept_by_exemption=int((cand & dens).sum()), prune_kept_by_exemption_on_conflict=int((cand & dens & conflict).sum()),
        floor_rows=int(lock.sum()))
    # 3. the prior depth term's pixels
    views, packs, gsum = [], {}, {}
    losses_mvs, losses_prior = {}, {}
    tot = dict(prior_px=0, on=0, on_lt1=0, on_1_hi=0, on_gt_hi=0, off_w0=0, off_lt1=0, off_gt_hi=0, mvs_px=0)
    hi = float(args.jbgs_trunc_hi)
    for cam in self.train_cams:
        nm = cam.image_name
        with torch.no_grad():
            pkg = self.render_fn(cam, gaussians, self.pipe, self.background)
        D = pkg["surf_depth"].detach().clone().requires_grad_(True)
        mvs, prior_t, st = self.losses(nm, {"surf_depth": D})
        if prior_t.requires_grad:
            g, = torch.autograd.grad(prior_t, D, allow_unused=True)
            g = torch.zeros_like(D) if g is None else g
        else:
            g = torch.zeros_like(D)
        g = g.squeeze(0)
        Dd = D.detach().squeeze(0)
        P, TAU = self.P.get(nm), self.TAU.get(nm)
        w = getattr(self, "GW", {}).get(nm)
        on = g != 0
        if P is not None and TAU is not None:
            pp = torch.isfinite(P) & (P > 0) & torch.isfinite(TAU) & torch.isfinite(Dd) & (Dd > 0)
            ratio = torch.where(pp, (Dd - P).abs() / TAU.clamp_min(1e-9), torch.full_like(Dd, float("nan")))
            wpos = (w > 0) if w is not None else torch.ones_like(pp)
            tot["prior_px"] += int(pp.sum()); tot["on"] += int(on.sum())
            tot["on_lt1"] += int((on & (ratio < 1)).sum()); tot["on_1_hi"] += int((on & (ratio >= 1) & (ratio <= hi)).sum())
            tot["on_gt_hi"] += int((on & (ratio > hi)).sum())
            tot["off_w0"] += int((pp & ~wpos).sum()); tot["off_lt1"] += int((pp & wpos & ~on & (ratio < 1)).sum())
            tot["off_gt_hi"] += int((pp & wpos & ~on & (ratio > hi)).sum())
            # PHD-MAIN-FIXTEST-v1 records
            packs[f"gw_{nm}"] = _pack(pp & wpos)
            packs[f"gthi_{nm}"] = _pack(pp & (ratio > hi))
            fx = getattr(self, "fix", None) or {}
            if fx.get("prior_share_band"):
                Wm = self.W[nm]
                adiff = (Dd - P).abs()
                wt = pp & wpos & torch.isfinite(Wm) & (adiff > Wm) & (adiff <= TAU)
                packs[f"wtau_{nm}"] = _pack(wt)
                tot["wtau"] = tot.get("wtau", 0) + int(wt.sum()); tot["on_w_tau"] = tot.get("on_w_tau", 0) + int((on & wt).sum())
            if fx.get("own_depth_release"):
                ms = self.NOTRUNC.get(nm)
                ms = ms if ms is not None else torch.zeros_like(pp)
                packs[f"miss_{nm}"] = _pack(ms)
                tot["on_miss"] = tot.get("on_miss", 0) + int((on & ms).sum())
                tot["on_miss_gt_hi"] = tot.get("on_miss_gt_hi", 0) + int((on & ms & (ratio > hi)).sum())
        A, M = self.A.get(nm), self.M.get(nm)
        if A is not None and M is not None:
            tot["mvs_px"] += int(((A > 0) & torch.isfinite(M) & (M > 0) & torch.isfinite(Dd) & (Dd > 0)).sum())
        views.append(nm)
        packs[f"on_{nm}"] = _pack(on)
        gsum[nm] = float(g.abs().sum())
        losses_mvs[nm] = float(mvs); losses_prior[nm] = float(prior_t)     # fix-v1: the two unweighted terms of the view
        del pkg, D, g
    info["depth_term"] = tot
    info["loss_sums"] = dict(mvs=float(sum(losses_mvs.values())), prior=float(sum(losses_prior.values())), views=len(views))
    info["seconds"] = round(time.time() - t0, 1)
    np.savez_compressed(OUTD / "probe.npz", lock=lock.cpu().numpy(), dens=dens.cpu().numpy(), reset_ex=reset_ex.cpu().numpy(),
                        prune_cand=cand.cpu().numpy(), prior=prior.cpu().numpy(), conflict=conflict.cpu().numpy(),
                        init_id=gaussians.init_id.cpu().numpy(), E=self.E.cpu().numpy() if self.E is not None else np.zeros(0),
                        g_state=self.g_state.cpu().numpy() if self.g_state is not None else np.zeros(0),
                        g_loc=self.g_loc.cpu().numpy() if self.g_loc is not None else np.zeros(0),
                        g_Jl=self.g_Jl.cpu().numpy() if self.g_Jl is not None else np.zeros(0),
                        views=np.array(views), grad_abs_sum=np.array([gsum[v] for v in views]),
                        mvs_loss=np.array([losses_mvs[v] for v in views]), prior_loss=np.array([losses_prior[v] for v in views]), **packs)
    (OUTD / "probe.json").write_text(json.dumps(info, indent=1, default=float))
    print("[probe] done", json.dumps(dict(decisions=info["decisions"], depth_term=tot, seconds=info["seconds"])))


def _radii_check(self, gaussians):
    """PHD-MAIN-STAGE3-v1: r15's Python radii against the rasterizer's on every training view (after the probe; records only)."""
    try:
        import jbgs_oom_record as OR
    except ImportError:
        return
    rows = []
    for cam in self.train_cams:
        with torch.no_grad():
            pkg = self.render_fn(cam, gaussians, self.pipe, self.background)
        ras = pkg["radii"].int()
        py, tiles = OR.surfel_radii(gaussians, cam)
        vr, vp = ras > 0, py > 0
        both = vr & vp
        d = (ras[both] - py[both]).abs()
        rows.append(dict(view=cam.image_name, visible_rasterizer=int(vr.sum()), visible_python=int(vp.sum()), visible_both=int(both.sum()),
                         radius_equal=int((d == 0).sum()), radius_diff_1=int((d == 1).sum()), radius_diff_gt1=int((d > 1).sum()),
                         radius_q99_rasterizer=float(torch.quantile(ras[vr].float(), 0.99)) if vr.any() else 0.0,
                         radius_q99_python=float(torch.quantile(py[vp].float(), 0.99)) if vp.any() else 0.0,
                         radius_max_rasterizer=int(ras.max()), radius_max_python=int(py.max()), tiles_python=int(tiles.sum())))
        del pkg
    tot = {k: sum(r[k] for r in rows) for k in ("visible_rasterizer", "visible_python", "visible_both", "radius_equal", "radius_diff_1", "radius_diff_gt1")}
    tot["equal_share"] = tot["radius_equal"] / max(tot["visible_both"], 1)
    (OUTD / "oom_radii.json").write_text(json.dumps(dict(rule=_radii_check.__doc__, total=tot, views=rows), indent=1))
    print("[radii] python vs rasterizer", json.dumps(tot))


def _init(self, args, opt, scene, gaussians, *a, **k):
    _orig_init(self, args, opt, scene, gaussians, *a, **k)
    _probe(self, args, opt, scene, gaussians)
    raise SystemExit(0)


JJ.Judgment.__init__ = _init
sys.argv = ["train.py"] + train_argv
runpy.run_path("/source/train.py", run_name="__main__")
