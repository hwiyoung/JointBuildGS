"""Read-only instrumentation of the r6 fork for PHD-STAGE2-R6-FIX-v1 (same records as the r5 audit
PHD-STAGE2-PROTECTION-AUDIT-v1, so r5 numbers can be taken from that audit without rerunning r5).

Copied as jbgs_audit.py into an instrumented copy of the r6 fork (build_audit_fork_r6.py); r6 itself is not touched.
Hooks in train.py are the same as in the r5 audit:
  before_E / after_E   around judgment.update_E     E-update records from the r6 judgment (what it computed and
                                                    protected), the r5 rule applied to the same state for comparison,
                                                    the protection rate of prior disks hidden in every view
  before_step          right before optimizer.step  parameter copies and render-time opacity of the three groups
  mid_step             right after optimizer.step   raw Adam output, before the judgment's lock blend
  post_lock            right after judgment.after_step   step records (|delta| / lr per group) and post-floor opacity
  end_iteration        after densification/reset    end-of-iteration opacity, the gradient analysis of fix 5 at
                                                    --jbgs_audit_grad_iter, final dump
  instance wrappers    densify_and_clone/split/prune, prune_points, reset_opacity (as in the r5 audit)
Groups: prot = prior origin and protected, free = prior origin and not protected, img = image/SfM origin.
Everything runs under torch.no_grad() (the gradient analysis uses torch.autograd.grad on separate renders and never
touches .grad of the parameters), writes only below --jbgs_audit_dir and never draws from the global RNGs.
No model parameter is written (variant A only).
"""
import json
import math
import time
from pathlib import Path

import numpy as np
import torch

import jbgs_judgment as J

GROUPS = ("prot", "free", "img")
QTY = ("xyz", "rot", "scale", "fdc", "frest")
PARAM = {"xyz": "_xyz", "rot": "_rotation", "scale": "_scaling", "fdc": "_features_dc", "frest": "_features_rest"}
LR_GROUP = {"xyz": "xyz", "rot": "rotation", "scale": "scaling", "fdc": "f_dc", "frest": "f_rest"}
FLOOR = 0.5


def register_args(parser):
    g = parser.add_argument_group("jbgs_audit")
    g.add_argument("--jbgs_audit_dir", default="", help="enables the audit; output directory")
    g.add_argument("--jbgs_audit_variant", default="A", choices=["A"])
    g.add_argument("--jbgs_audit_grad_iter", type=int, default=0,
                   help="fix 5 check: at the end of this iteration, per-disk position gradients of the two depth terms (0 = off)")
    g.add_argument("--jbgs_audit_map_iterations", type=int, nargs="+", default=[500, 3000, 3500],
                   help="E updates whose render (depth/alpha of the audit views) is saved")
    g.add_argument("--jbgs_audit_c_scale", type=float, default=0.01, help="variant C: update scale of protected rows")
    g.add_argument("--jbgs_audit_views", nargs="+",
                   default=["DJI_20241217101305_0005_D", "DJI_20241217101343_0024_D"],
                   help="training views whose rendered depth/alpha are saved at E updates and around opacity resets")
    g.add_argument("--jbgs_audit_hist_iterations", type=int, nargs="+", default=[1, 500, 2999, 3000, 3001, 3500],
                   help="iterations whose full per-disk opacity/group arrays are saved (end of iteration)")


def _stats(x):
    """(n, median, mean, p90) of a 1-D tensor; NaN when empty."""
    n = int(x.numel())
    if n == 0:
        return 0, float("nan"), float("nan"), float("nan")
    x = x.float()
    q = torch.quantile(x, torch.tensor([0.5, 0.9], device=x.device)) if n <= 16_000_000 else torch.stack(
        [x.median(), x.kthvalue(max(1, int(0.9 * n)))[0]])
    return n, float(q[0]), float(x.mean()), float(q[1])


def _qs(x, qs=(0.1, 0.5, 0.9, 0.99)):
    if x.numel() == 0:
        return [float("nan")] * len(qs)
    return [float(v) for v in torch.quantile(x.float(), torch.tensor(list(qs), device=x.device))]


class Audit:
    def __init__(self, args, opt, judgment, scene, gaussians, render, pipe, background):
        self.args = args
        self.dir = Path(args.jbgs_audit_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "E").mkdir(exist_ok=True)
        (self.dir / "maps").mkdir(exist_ok=True)
        (self.dir / "hist").mkdir(exist_ok=True)
        self.variant = args.jbgs_audit_variant
        self.c_scale = float(args.jbgs_audit_c_scale)
        self.J = judgment
        self.render, self.pipe, self.bg = render, pipe, background
        self.train_cams = scene.getTrainCameras()
        self.cam_by_name = {c.image_name: c for c in self.train_cams}
        self.views = [v for v in args.jbgs_audit_views if v in self.cam_by_name]
        self.iterations = int(opt.iterations)
        ei = int(args.jbgs_e_interval)
        self.E_iters = [i for i in range(1, self.iterations + 1) if J.due_E_iteration(i, ei)]   # r6 schedule
        judgment.keep_maps = True     # keep the E renders so the audit can save the audit views (no effect on training)
        self.drift_max = float(judgment.lock_drift_max)
        self.grad_iter = int(args.jbgs_audit_grad_iter)
        self.map_iters = set(args.jbgs_audit_map_iterations)
        self.hist_iters = set(args.jbgs_audit_hist_iterations) | {self.iterations}
        self.cur_iter = 0
        self.prev_frozen = None
        self.b = self.m = None
        self.g = None
        self.row_opacity = {}
        self._in_split = False
        self._dp_ctx = None
        self.removed = []          # final-prune removals: (iteration, init_id, origin, reason bits, x, y, z)
        self.events = []
        self.started = time.monotonic()
        self.f_steps = (self.dir / "steps.csv").open("w", buffering=1)
        cols = ["iteration"] + [f"lr_{q}" for q in QTY]
        for g in GROUPS:
            cols.append(f"{g}_n")
            for q in QTY:
                cols += [f"{g}_{q}_med", f"{g}_{q}_mean", f"{g}_{q}_p90", f"{g}_{q}_act_n", f"{g}_{q}_act_med"]
        for q in ("xyz", "rot", "scale"):
            cols += [f"prot_raw_{q}_med", f"prot_raw_{q}_mean", f"prot_raw_{q}_act_med", f"prot_{q}_zero_frac"]
        cols += ["prot_applied_over_raw_xyz_med", "prot_applied_over_raw_xyz_mean", "free_xyz_zero_frac", "img_xyz_zero_frac"]
        self.step_cols = cols
        self.f_steps.write(",".join(cols) + "\n")
        self.f_op = (self.dir / "opacity.csv").open("w", buffering=1)
        self.op_cols = ["iteration", "E_update", "reset", "n_prot_render", "render_min", "render_med", "render_nbelow",
                        "n_newly", "newly_render_min", "newly_render_med", "newly_render_nbelow",
                        "post_min", "post_med", "post_nbelow", "n_prot_end", "end_min", "end_med", "end_nbelow",
                        "free_end_med", "img_end_med", "n_free_end", "n_img_end", "free_end_below005", "img_end_below005"]
        self.f_op.write(",".join(self.op_cols) + "\n")
        self.f_E = (self.dir / "E_updates.csv").open("w", buffering=1)
        self.E_cols = ["iteration", "how", "n", "n_prior", "n_prot", "prot_rate", "n_newly", "n_released", "n_released_far",
                       "n_far", "n_prior_cnt0", "n_hidden_near", "n_hidden_near_prot", "hidden_near_prot_rate",
                       "E_mean_prior", "cnt_med_prior", "prot_drift_p50", "prot_drift_p90", "prot_drift_max",
                       "newly_drift_p10", "newly_drift_p50", "newly_drift_p90", "newly_drift_max", "released_drift_p50",
                       "n_prot_r5rule", "flip_r6_not_r5rule", "flip_r5rule_not_r6", "n_empty_pairs", "seconds"]
        self.f_E.write(",".join(self.E_cols) + "\n")
        self.f_dens = (self.dir / "densify.jsonl").open("w", buffering=1)
        self._wrap(gaussians)
        n = gaussians.get_xyz.shape[0]
        np.savez(self.dir / "init.npz", init_xyz=self.J.init_xyz.cpu().numpy(), init_origin=self.J.init_origin.cpu().numpy())
        meta = dict(variant=self.variant, c_scale=self.c_scale, lock_lr_scale=float(args.jbgs_lock_lr_scale),
                    lock_opacity_floor=float(args.jbgs_lock_opacity_floor), iterations=self.iterations,
                    E_iterations=self.E_iters, views=self.views, n_init=int(n), revision=getattr(J, "REVISION", None),
                    lock_drift_max=self.drift_max, grad_iter=self.grad_iter, init_filter=getattr(judgment, "init_filter", None),
                    opacity_reset_interval=int(opt.opacity_reset_interval), densify_from_iter=int(opt.densify_from_iter),
                    densify_until_iter=int(opt.densify_until_iter), densification_interval=int(opt.densification_interval),
                    opacity_cull=float(opt.opacity_cull), lambda_normal=float(opt.lambda_normal),
                    lambda_dist=float(opt.lambda_dist), depth_ratio=float(pipe.depth_ratio),
                    optimizer=dict(type=type(gaussians.optimizer).__name__,
                                   defaults={k: (list(v) if isinstance(v, tuple) else v)
                                             for k, v in gaussians.optimizer.defaults.items()
                                             if isinstance(v, (int, float, bool, tuple))},
                                   groups={pg["name"]: float(pg["lr"]) for pg in gaussians.optimizer.param_groups}),
                    scientific_verdict=None)
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=1))
        print(f"[jbgs_audit] variant={self.variant} dir={self.dir} E_iterations={self.E_iters[:3]}..{self.E_iters[-1]}")

    # --------------------------------------------------------------------------------------------- groups
    def _groups(self, gs):
        prior = gs.origin == J.ORIGIN_PRIOR
        fr = gs.frozen_mask if (gs.frozen_mask is not None and gs.frozen_mask.shape[0] == prior.shape[0]) \
            else torch.zeros_like(prior)
        return {"prot": prior & fr, "free": prior & ~fr, "img": ~prior}, prior, fr

    def _drift(self, gs):
        ids = gs.init_id.long()
        d = torch.full((ids.shape[0],), float("nan"), device=ids.device)
        ok = ids >= 0
        d[ok] = (gs.get_xyz[ok] - self.J.init_xyz[ids[ok]]).norm(dim=1)
        return d

    # ------------------------------------------------------------------------------------------ E updates
    @torch.no_grad()
    def before_E(self, iteration, gs):
        self.prev_frozen = gs.frozen_mask.clone() if gs.frozen_mask is not None else None

    @torch.no_grad()
    def after_E(self, iteration, gs):
        """Records what the r6 judgment computed at this update; the r5 rule on the same state for comparison."""
        t0 = time.monotonic()
        a = self.args
        J_ = self.J
        groups, prior, fr = self._groups(gs)
        up = J_.last_update
        E, cnt = J_.E, J_.E_cnt
        n = int(prior.shape[0])
        prev, far, drift = up["prev"], up["far"], up["drift"]
        newly, released = fr & ~prev, prev & ~fr
        released_far = released & far
        xyz = gs.get_xyz.detach()
        # r5 rule on the same state: prior-depth two-sided seeing test, off-prior exception
        E_p2, cnt_p2 = J.compute_E(xyz, self.train_cams, J_.A, J_.P, a.jbgs_e_depth_tol)
        prot_r5 = prior & (E_p2 < a.jbgs_e_threshold) & ~((cnt_p2 == 0) & (drift > a.jbgs_e_depth_tol))
        hidden_near = prior & (cnt == 0) & torch.isfinite(drift) & (drift <= self.drift_max)

        def med(x):
            return float(x.float().median()) if x.numel() else float("nan")
        pd_ = drift[fr]
        nd = drift[newly & prior]
        row = dict(iteration=iteration, how=J_.E_how, n=n, n_prior=int(prior.sum()), n_prot=int(fr.sum()),
                   prot_rate=float(fr.sum()) / max(1, int(prior.sum())), n_newly=int(newly.sum()), n_released=int(released.sum()),
                   n_released_far=int(released_far.sum()), n_far=int(far.sum()), n_prior_cnt0=int((prior & (cnt == 0)).sum()),
                   n_hidden_near=int(hidden_near.sum()), n_hidden_near_prot=int((hidden_near & fr).sum()),
                   hidden_near_prot_rate=float((hidden_near & fr).sum()) / max(1, int(hidden_near.sum())),
                   E_mean_prior=float(E[prior].mean()) if prior.any() else float("nan"), cnt_med_prior=med(cnt[prior]),
                   prot_drift_p50=_qs(pd_, (0.5,))[0], prot_drift_p90=_qs(pd_, (0.9,))[0],
                   prot_drift_max=float(pd_.max()) if pd_.numel() else float("nan"),
                   newly_drift_p10=_qs(nd, (0.1,))[0], newly_drift_p50=_qs(nd, (0.5,))[0], newly_drift_p90=_qs(nd, (0.9,))[0],
                   newly_drift_max=float(nd.max()) if nd.numel() else float("nan"), released_drift_p50=med(drift[released & prior]),
                   n_prot_r5rule=int(prot_r5.sum()), flip_r6_not_r5rule=int((fr & ~prot_r5).sum()),
                   flip_r5rule_not_r6=int((prot_r5 & ~fr).sum()), n_empty_pairs=-1, seconds=time.monotonic() - t0)
        try:
            with open(J_.mon / "E.jsonl") as fh:
                last = json.loads(fh.read().strip().splitlines()[-1])
            row["n_empty_pairs"] = last.get("n_empty_pairs", -1)
        except Exception:
            pass
        self.f_E.write(",".join(str(row[c]) for c in self.E_cols) + "\n")
        sel = prior
        np.savez_compressed(self.dir / "E" / f"E_{iteration:05d}.npz", iteration=iteration, how=J_.E_how,
                            row=torch.nonzero(sel).squeeze(1).cpu().numpy().astype(np.int32),
                            xyz=xyz[sel].cpu().numpy().astype(np.float32), init_id=gs.init_id[sel].cpu().numpy(),
                            drift=drift[sel].cpu().numpy().astype(np.float32), E=E[sel].cpu().numpy().astype(np.float32),
                            cnt=cnt[sel].cpu().numpy().astype(np.int16), prot=fr[sel].cpu().numpy(), prev_prot=prev[sel].cpu().numpy(),
                            far=far[sel].cpu().numpy(), opacity=gs.get_opacity.squeeze(-1)[sel].cpu().numpy().astype(np.float32),
                            E_p2=E_p2[sel].cpu().numpy().astype(np.float32), cnt_p2=cnt_p2[sel].cpu().numpy().astype(np.int16),
                            prot_r5rule=prot_r5[sel].cpu().numpy())
        if iteration in self.map_iters and J_.last_maps is not None:
            Dm, ALm = J_.last_maps
            np.savez_compressed(self.dir / "maps" / f"render_E_{iteration:05d}.npz",
                                **{f"depth_{v}": Dm[v].cpu().numpy().astype(np.float32) for v in self.views if v in Dm},
                                **{f"alpha_{v}": ALm[v].cpu().numpy().astype(np.float16) for v in self.views if v in ALm})
        J_.last_maps = None
        self.events.append(dict(iteration=iteration, event="E_update", how=J_.E_how, n_prot=row["n_prot"], n_newly=row["n_newly"],
                                n_released=row["n_released"], n_released_far=row["n_released_far"]))

    # ------------------------------------------------------------------------------------------ step hooks
    @torch.no_grad()
    def before_step(self, iteration, gs):
        self.cur_iter = iteration
        self.g, prior, fr = self._groups(gs)
        self.b = {q: getattr(gs, PARAM[q]).detach().clone() for q in QTY}
        op = gs.get_opacity.squeeze(-1)
        p = self.g["prot"]
        e_upd = iteration in self.E_iters
        up = self.J.last_update
        newly = (up["lock"] & ~up["prev"]) if (e_upd and up is not None and up.get("iteration") == iteration and
                                                up["lock"].shape[0] == fr.shape[0]) else torch.zeros_like(fr)
        po, no = op[p], op[newly]
        self.row_opacity = dict(iteration=iteration, E_update=int(e_upd), reset=0, n_prot_render=int(p.sum()),
                                render_min=float(po.min()) if po.numel() else float("nan"),
                                render_med=float(po.median()) if po.numel() else float("nan"),
                                render_nbelow=int((po < FLOOR - 1e-6).sum()),
                                n_newly=int(newly.sum()),
                                newly_render_min=float(no.min()) if no.numel() else float("nan"),
                                newly_render_med=float(no.median()) if no.numel() else float("nan"),
                                newly_render_nbelow=int((no < FLOOR - 1e-6).sum()))

    @torch.no_grad()
    def mid_step(self, gs):
        self.m = {q: getattr(gs, PARAM[q]).detach().clone() for q in ("xyz", "rot", "scale")}

    @torch.no_grad()
    def post_lock(self, iteration, gs):
        if self.b is None:
            return
        p = self.g["prot"]
        if self.variant == "C" and bool(p.any()) and p.shape[0] == gs.get_xyz.shape[0]:
            for q in ("xyz", "rot", "scale"):
                par = getattr(gs, PARAM[q])
                old = self.b[q][p]
                par.data[p] = old + self.c_scale * (par.data[p] - old)
        lr = {pg["name"]: float(pg["lr"]) for pg in gs.optimizer.param_groups}
        row = {"iteration": iteration}
        for q in QTY:
            row[f"lr_{q}"] = lr[LR_GROUP[q]]
        delta, raw = {}, {}
        for q in QTY:
            cur = getattr(gs, PARAM[q]).detach()
            delta[q] = (cur - self.b[q]).reshape(cur.shape[0], -1).norm(dim=1)
        for q in ("xyz", "rot", "scale"):
            raw[q] = (self.m[q] - self.b[q]).reshape(self.m[q].shape[0], -1).norm(dim=1)
        for g in GROUPS:
            mk = self.g[g]
            row[f"{g}_n"] = int(mk.sum())
            for q in QTY:
                div = row[f"lr_{q}"] if q in ("xyz", "rot", "scale") else 1.0
                x = delta[q][mk] / div
                n_, md, mn, p9 = _stats(x)
                act = (raw[q][mk] > 0) if q in raw else (x > 0)
                xa = x[act]
                row.update({f"{g}_{q}_med": md, f"{g}_{q}_mean": mn, f"{g}_{q}_p90": p9,
                            f"{g}_{q}_act_n": int(xa.numel()), f"{g}_{q}_act_med": _stats(xa)[1]})
        mk = self.g["prot"]
        for q in ("xyz", "rot", "scale"):
            x = raw[q][mk] / row[f"lr_{q}"]
            _, md, mn, _ = _stats(x)
            moving = raw[q][mk] > 0
            zero = moving & (delta[q][mk] == 0)   # Adam moved the row but the applied (blended) update rounded to 0
            row.update({f"prot_raw_{q}_med": md, f"prot_raw_{q}_mean": mn, f"prot_raw_{q}_act_med": _stats(x[x > 0])[1],
                        f"prot_{q}_zero_frac": float(zero.sum()) / max(1, int(moving.sum()))})
        rr = raw["xyz"][mk]
        ok = rr > 0
        rat = delta["xyz"][mk][ok] / rr[ok]
        row["prot_applied_over_raw_xyz_med"] = _stats(rat)[1]
        row["prot_applied_over_raw_xyz_mean"] = _stats(rat)[2]
        for g in ("free", "img"):
            mv = raw["xyz"][self.g[g]] > 0
            row[f"{g}_xyz_zero_frac"] = float((mv & (delta["xyz"][self.g[g]] == 0)).sum()) / max(1, int(mv.sum()))
        self.f_steps.write(",".join(str(row[c]) for c in self.step_cols) + "\n")
        op = gs.get_opacity.squeeze(-1)[mk]
        self.row_opacity.update(post_min=float(op.min()) if op.numel() else float("nan"),
                                post_med=float(op.median()) if op.numel() else float("nan"),
                                post_nbelow=int((op < FLOOR - 1e-6).sum()))
        self.b = self.m = None

    @torch.no_grad()
    def end_iteration(self, iteration, gs):
        groups, prior, fr = self._groups(gs)
        op = gs.get_opacity.squeeze(-1)
        po = op[groups["prot"]]
        r = self.row_opacity
        r.update(n_prot_end=int(groups["prot"].sum()), end_min=float(po.min()) if po.numel() else float("nan"),
                 end_med=float(po.median()) if po.numel() else float("nan"), end_nbelow=int((po < FLOOR - 1e-6).sum()),
                 free_end_med=float(op[groups["free"]].median()) if bool(groups["free"].any()) else float("nan"),
                 img_end_med=float(op[groups["img"]].median()) if bool(groups["img"].any()) else float("nan"),
                 n_free_end=int(groups["free"].sum()), n_img_end=int(groups["img"].sum()),
                 free_end_below005=int((op[groups["free"]] < 0.05).sum()), img_end_below005=int((op[groups["img"]] < 0.05).sum()))
        for c in self.op_cols:
            r.setdefault(c, float("nan"))
        self.f_op.write(",".join(str(r[c]) for c in self.op_cols) + "\n")
        if iteration in self.hist_iters:
            np.savez_compressed(self.dir / "hist" / f"state_{iteration:05d}.npz", iteration=iteration,
                                opacity=op.cpu().numpy().astype(np.float32), origin=gs.origin.cpu().numpy(),
                                prot=fr.cpu().numpy(), init_id=gs.init_id.cpu().numpy(),
                                xyz=gs.get_xyz.detach().cpu().numpy().astype(np.float32),
                                drift=self._drift(gs).cpu().numpy().astype(np.float32))
        if self.grad_iter and iteration == self.grad_iter:
            self.grad_analysis(iteration, gs)
        if iteration == self.iterations:
            self.final(iteration, gs)

    def grad_analysis(self, iteration, gs):
        """Fix 5 check: per view, the position gradient of each depth term (raw sums, same validity as the losses) is
        taken separately with torch.autograd.grad and summed over the 13 training views per disk, once with the r5
        denominators (sum A, sum (1-A) of the view) and once with the r6 one (pixel count). lambda (0.05 for both) is
        common and left out. E of every disk is recomputed on the same renders with the r6 rule."""
        t0 = time.monotonic()
        J_ = self.J
        n = gs.get_xyz.shape[0]
        acc = {k: torch.zeros((n, 3), device="cuda") for k in ("mvs_old", "prior_old", "mvs_new", "prior_new")}
        Dm, ALm, per_view = {}, {}, []
        for cam in self.train_cams:
            name = cam.image_name
            A, M, P, T = J_.A[name], J_.M[name], J_.P[name], J_.TAU[name]
            with torch.enable_grad():
                pkg = self.render(cam, gs, self.pipe, self.bg)
                D = pkg["surf_depth"].squeeze(0)
                rend = torch.isfinite(D) & (D > 0)
                vm = torch.isfinite(M) & (M > 0) & (A > 0) & rend
                s_m = (torch.abs(D[vm] - M[vm]) * A[vm]).sum()
                w = 1.0 - A
                vp = torch.isfinite(P) & (P > 0) & torch.isfinite(T) & (w > 0) & rend
                s_p = (J.rho_truncated(D[vp] - P[vp], T[vp], self.args.jbgs_trunc_hi) * w[vp]).sum()
                g_m = torch.autograd.grad(s_m, gs._xyz, retain_graph=True, allow_unused=True)[0]
                g_p = torch.autograd.grad(s_p, gs._xyz, allow_unused=True)[0]
            g_m = torch.zeros_like(acc["mvs_old"]) if g_m is None else g_m.detach()
            g_p = torch.zeros_like(acc["mvs_old"]) if g_p is None else g_p.detach()
            den_m, den_p, npx = float(A[vm].sum()) + 1e-9, float(w[vp].sum()) + 1e-9, float(D.numel())
            acc["mvs_old"] += g_m / den_m; acc["prior_old"] += g_p / den_p
            acc["mvs_new"] += g_m / npx; acc["prior_new"] += g_p / npx
            Dm[name] = D.detach(); ALm[name] = pkg["rend_alpha"].squeeze(0).detach()
            per_view.append(dict(view=name, n_mvs=int(vm.sum()), n_prior=int(vp.sum()), den_mvs_old=den_m, den_prior_old=den_p, n_px=npx))
            del pkg, D, g_m, g_p
        E, cnt, n_empty = J.compute_E_render(gs.get_xyz.detach(), self.train_cams, J_.A, Dm, ALm, self.args.jbgs_e_depth_tol,
                                             self.args.jbgs_e_alpha_min)
        groups, prior, fr = self._groups(gs)
        np.savez_compressed(self.dir / f"grad_{iteration:05d}.npz", iteration=iteration,
                            **{f"norm_{k}": v.norm(dim=1).cpu().numpy().astype(np.float32) for k, v in acc.items()},
                            E=E.cpu().numpy().astype(np.float32), cnt=cnt.cpu().numpy().astype(np.int16),
                            origin=gs.origin.cpu().numpy(), prot=fr.cpu().numpy(),
                            E_judgment=(J_.E.cpu().numpy().astype(np.float32) if (J_.E is not None and J_.E.shape[0] == n) else np.full(n, np.nan, np.float32)))
        (self.dir / f"grad_{iteration:05d}.json").write_text(json.dumps(dict(iteration=iteration, per_view=per_view, n=n, n_empty_pairs=int(n_empty),
                                                                             seconds=time.monotonic() - t0), indent=1))
        del acc, Dm, ALm
        torch.cuda.empty_cache()

    # ------------------------------------------------------------------------------------ density control
    def _wrap(self, gs):
        me = self
        orig_clone, orig_split = gs.densify_and_clone, gs.densify_and_split
        orig_dap, orig_prune, orig_reset = gs.densify_and_prune, gs.prune_points, gs.reset_opacity

        def counts(mask, groups):
            return {g: int((mask & groups[g]).sum()) for g in GROUPS}

        @torch.no_grad()
        def clone(grads, grad_threshold, scene_extent):
            groups, prior, fr = me._groups(gs)
            sel_nf = (torch.norm(grads, dim=-1) >= grad_threshold) & \
                     (torch.max(gs.get_scaling, dim=1).values <= gs.percent_dense * scene_extent)
            sel = sel_nf & ~fr
            n0 = gs.get_xyz.shape[0]
            par_origin, par_ids = gs.origin[sel].clone(), gs.init_id[sel].clone()
            r = orig_clone(grads, grad_threshold, scene_extent)
            n1 = gs.get_xyz.shape[0]
            ch = slice(n0, n1)
            fr1 = gs.frozen_mask
            ev = dict(iteration=me.cur_iter, event="clone", selected=counts(sel, groups),
                      excluded_protected=int((sel_nf & fr).sum()), n_new=n1 - n0, n_new_matches=bool(n1 - n0 == int(sel.sum())),
                      child_origin_ok=bool(torch.equal(gs.origin[ch], par_origin)),
                      child_init_id_ok=bool(torch.equal(gs.init_id[ch], par_ids)),
                      child_protected=int(fr1[ch].sum()) if fr1 is not None else 0)
            me.f_dens.write(json.dumps(ev) + "\n")
            return r

        @torch.no_grad()
        def split(grads, grad_threshold, scene_extent, N=2):
            groups, prior, fr = me._groups(gs)
            n0 = gs.get_xyz.shape[0]
            padded = torch.zeros((n0,), device="cuda")
            padded[:grads.shape[0]] = grads.squeeze()
            sel_nf = (padded >= grad_threshold) & (torch.max(gs.get_scaling, dim=1).values > gs.percent_dense * scene_extent)
            sel = sel_nf & ~fr
            par_origin = gs.origin[sel].repeat(N).clone()
            par_ids = gs.init_id[sel].repeat(N).clone()
            me._in_split = True
            try:
                r = orig_split(grads, grad_threshold, scene_extent, N)
            finally:
                me._in_split = False
            n1 = gs.get_xyz.shape[0]
            k = int(sel.sum())
            ch = slice(n1 - N * k, n1)
            fr1 = gs.frozen_mask
            ev = dict(iteration=me.cur_iter, event="split", selected=counts(sel, groups),
                      excluded_protected=int((sel_nf & fr).sum()), n_new=N * k, n_net=n1 - n0,
                      n_net_matches=bool(n1 - n0 == (N - 1) * k),
                      child_origin_ok=bool(torch.equal(gs.origin[ch], par_origin)),
                      child_init_id_ok=bool(torch.equal(gs.init_id[ch], par_ids)),
                      child_protected=int(fr1[ch].sum()) if fr1 is not None else 0)
            me.f_dens.write(json.dumps(ev) + "\n")
            return r

        @torch.no_grad()
        def dap(max_grad, min_opacity, extent, max_screen_size):
            me._dp_ctx = dict(min_opacity=float(min_opacity), extent=float(extent),
                              max_screen_size=(float(max_screen_size) if max_screen_size else None))
            try:
                return orig_dap(max_grad, min_opacity, extent, max_screen_size)
            finally:
                me._dp_ctx = None

        @torch.no_grad()
        def prune(mask):
            groups, prior, fr = me._groups(gs)
            if me._in_split:
                ev = dict(iteration=me.cur_iter, event="split_parent_removal", removed=counts(mask, groups))
                me.f_dens.write(json.dumps(ev) + "\n")
                return orig_prune(mask)
            if me._dp_ctx is not None:
                c = me._dp_ctx
                low = (gs.get_opacity < c["min_opacity"]).squeeze(-1)
                big_vs = (gs.max_radii2D > c["max_screen_size"]) if c["max_screen_size"] else torch.zeros_like(low)
                big_ws = (gs.get_scaling.max(dim=1).values > 0.1 * c["extent"]) if c["max_screen_size"] else torch.zeros_like(low)
                cand = low | big_vs | big_ws
                ev = dict(iteration=me.cur_iter, event="prune", removed=counts(mask, groups),
                          removed_low_opacity=counts(mask & low, groups), removed_big_screen=counts(mask & big_vs, groups),
                          removed_big_world=counts(mask & big_ws, groups),
                          excluded_protected=int((cand & fr).sum()), mask_equals_rule=bool(torch.equal(mask, cand & ~fr)))
                me.f_dens.write(json.dumps(ev) + "\n")
                sel = mask & prior
                if bool(sel.any()):
                    xyz = gs.get_xyz.detach()[sel].cpu().numpy()
                    bits = (low[sel].int() + 2 * big_vs[sel].int() + 4 * big_ws[sel].int()).cpu().numpy()
                    ids = gs.init_id[sel].cpu().numpy()
                    for i in range(len(ids)):
                        me.removed.append((me.cur_iter, int(ids[i]), 1, int(bits[i]), *map(float, xyz[i])))
            else:
                ev = dict(iteration=me.cur_iter, event="prune_other", removed=counts(mask, groups))
                me.f_dens.write(json.dumps(ev) + "\n")
            return orig_prune(mask)

        @torch.no_grad()
        def reset(exempt_mask=None):
            it = me.cur_iter
            groups, prior, fr = me._groups(gs)
            op0 = gs.get_opacity.squeeze(-1).clone()
            maps0 = me._render_views(gs)
            r = orig_reset(exempt_mask)
            op1 = gs.get_opacity.squeeze(-1)
            maps1 = me._render_views(gs)
            p = groups["prot"]
            ev = dict(iteration=it, event="opacity_reset", exempt_given=exempt_mask is not None,
                      n_exempt=int(exempt_mask.sum()) if exempt_mask is not None else 0,
                      prot_before=_qs(op0[p], (0.0, 0.5)), prot_after=_qs(op1[p], (0.0, 0.5)),
                      prot_changed=int((op1[p] != op0[p]).sum()),
                      free_before_med=_qs(op0[groups["free"]], (0.5,))[0], free_after_med=_qs(op1[groups["free"]], (0.5,))[0],
                      img_before_med=_qs(op0[groups["img"]], (0.5,))[0], img_after_med=_qs(op1[groups["img"]], (0.5,))[0],
                      n_reset_rows=int((op1 < op0 - 1e-9).sum()))
            me.f_dens.write(json.dumps(ev) + "\n")
            me.row_opacity["reset"] = 1
            np.savez_compressed(me.dir / "maps" / f"reset_{it:05d}.npz",
                                **{f"{k}_before_{v}": maps0[v][k] for v in maps0 for k in maps0[v]},
                                **{f"{k}_after_{v}": maps1[v][k] for v in maps1 for k in maps1[v]})
            return r

        gs.densify_and_clone, gs.densify_and_split = clone, split
        gs.densify_and_prune, gs.prune_points, gs.reset_opacity = dap, prune, reset

    @torch.no_grad()
    def _render_views(self, gs):
        out = {}
        for v in self.views:
            pkg = self.render(self.cam_by_name[v], gs, self.pipe, self.bg)
            out[v] = dict(depth=pkg["surf_depth"].squeeze(0).cpu().numpy().astype(np.float32),
                          alpha=pkg["rend_alpha"].squeeze(0).cpu().numpy().astype(np.float32))
        return out

    # ------------------------------------------------------------------------------------------- final
    @torch.no_grad()
    def final(self, iteration, gs):
        groups, prior, fr = self._groups(gs)
        ids = gs.init_id.long()
        n_init = self.J.init_xyz.shape[0]
        alive = torch.zeros(n_init, dtype=torch.bool, device=ids.device)
        alive[ids[ids >= 0]] = True
        rem = np.array(self.removed, dtype=np.float64).reshape(-1, 7)
        np.savez_compressed(self.dir / "final.npz", iteration=iteration, xyz=gs.get_xyz.detach().cpu().numpy().astype(np.float32),
                            origin=gs.origin.cpu().numpy(), init_id=gs.init_id.cpu().numpy(), prot=fr.cpu().numpy(),
                            opacity=gs.get_opacity.squeeze(-1).cpu().numpy().astype(np.float32),
                            drift=self._drift(gs).cpu().numpy().astype(np.float32),
                            init_xyz=self.J.init_xyz.cpu().numpy(), init_origin=self.J.init_origin.cpu().numpy(),
                            init_alive=alive.cpu().numpy(), impl_last_seen=self.J.last_seen.cpu().numpy(),
                            removed=rem)
        (self.dir / "events.json").write_text(json.dumps(self.events, indent=0))
        (self.dir / "done.json").write_text(json.dumps(dict(iteration=iteration, seconds=time.monotonic() - self.started,
                                                            n_removed_prior_rows=len(self.removed),
                                                            scientific_verdict=None)))
        for f in (self.f_steps, self.f_op, self.f_E, self.f_dens):
            f.flush()
