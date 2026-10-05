"""Read-only instrumentation for the method-document 4.4 audit (PHD-STAGE2-PROTECTION-AUDIT-v1).

Copied next to jbgs_judgment.py in an instrumented copy of the stage-2 fork (build_audit_fork.py); the frozen r5 fork
is not touched. Hooks inserted into train.py:

  before_E / after_E   around judgment.update_E     E-update records; alternative E definitions (no occlusion, occlusion
                                                    by the current render) computed on the same centres
  before_step          right before optimizer.step  parameter copies and render-time opacity of the three groups
  mid_step             right after optimizer.step   raw Adam output, before the judgment's lock blend
  post_lock            right after judgment.after_step
                                                    variant C only: scale the applied update of protected rows by
                                                    --jbgs_audit_c_scale (independent post-step blend); then the step
                                                    records (|delta| / lr per group) and the post-floor opacity
  end_iteration        after densification/reset    end-of-iteration opacity, final dump
  instance wrappers    densify_and_clone/split/prune, prune_points, reset_opacity: per-group counts, removal log,
                       opacity and rendered depth right before / after each opacity reset

Groups (recomputed at every hook from the current state): prot = prior origin and protected (frozen_mask),
free = prior origin and not protected, img = image/SfM origin.

Everything runs under torch.no_grad(), writes only below --jbgs_audit_dir and never draws from the global RNGs.
Variants A and B never write model parameters; variant C writes only the xyz/rotation/scaling rows of protected disks.
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
    g.add_argument("--jbgs_audit_variant", default="A", choices=["A", "B", "C"])
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
        self.E_iters = [i for i in range(1, self.iterations + 1) if (i - 1) % ei == 0]
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
        self.E_cols = ["iteration", "n", "n_prior", "n_prot", "n_newly", "n_released", "n_prior_cnt0", "n_off_prior",
                       "E_mean_prior", "cnt_med_prior", "n_prot_doc", "n_prot_rend", "n_prot_rendrule",
                       "flip_impl_not_doc", "flip_doc_not_impl", "flip_impl_not_rend", "flip_rend_not_impl",
                       "dE_doc_mean", "dE_rend_mean", "n_dE_rend_gt0", "n_dE_rend_gt025", "n_dE_doc_gt0",
                       "cnt_doc_med", "cnt_rend_med", "n_cnt_doc0", "n_cnt_rend0",
                       "newly_drift_p10", "newly_drift_p50", "newly_drift_p90", "newly_drift_max",
                       "released_drift_p50", "prot_drift_p50", "seconds"]
        self.f_E.write(",".join(self.E_cols) + "\n")
        self.f_dens = (self.dir / "densify.jsonl").open("w", buffering=1)
        self._wrap(gaussians)
        n = gaussians.get_xyz.shape[0]
        np.savez(self.dir / "init.npz", init_xyz=self.J.init_xyz.cpu().numpy(), init_origin=self.J.init_origin.cpu().numpy())
        meta = dict(variant=self.variant, c_scale=self.c_scale, lock_lr_scale=float(args.jbgs_lock_lr_scale),
                    lock_opacity_floor=float(args.jbgs_lock_opacity_floor), iterations=self.iterations,
                    E_iterations=self.E_iters, views=self.views, n_init=int(n),
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
    def _E_variant(self, xyz, occluders, tol):
        """E over the training cameras with the implementation's projection and centre-pixel lookup; the seeing test
        uses `occluders` (dict view -> depth map) or none (occluders=None: every in-image, in-front view counts)."""
        n = xyz.shape[0]
        ssum = torch.zeros(n, device=xyz.device)
        cnt = torch.zeros(n, device=xyz.device)
        for cam in self.train_cams:
            A = self.J.A.get(cam.image_name)
            if A is None:
                continue
            H, W = A.shape
            u, v, z = J.project_points(xyz, cam)
            ui, vi = torch.round(u).long(), torch.round(v).long()
            inside = (z > 0.01) & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
            idx = vi.clamp(0, H - 1) * W + ui.clamp(0, W - 1)
            Av = A.reshape(-1)[idx]
            if occluders is None:
                sees = inside
            else:
                Dv = occluders[cam.image_name].reshape(-1)[idx]
                sees = inside & torch.isfinite(Dv) & (Dv > 0) & (torch.abs(z - Dv) < tol)
            ssum[sees] += Av[sees]
            cnt[sees] += 1.0
        E = torch.where(cnt > 0, ssum / cnt.clamp_min(1.0), torch.zeros_like(ssum))
        return E, cnt

    @torch.no_grad()
    def _render_train_depths(self, gs):
        out = {}
        for cam in self.train_cams:
            pkg = self.render(cam, gs, self.pipe, self.bg)
            out[cam.image_name] = pkg["surf_depth"].squeeze(0).detach().clone()
        return out

    @torch.no_grad()
    def after_E(self, iteration, gs):
        t0 = time.monotonic()
        a = self.args
        groups, prior, fr = self._groups(gs)
        E, cnt = self.J.E, self.J.E_cnt
        n = int(prior.shape[0])
        prev = self.prev_frozen if (self.prev_frozen is not None and self.prev_frozen.shape[0] == n) else torch.zeros_like(fr)
        newly, released = fr & ~prev, prev & ~fr
        drift = self._drift(gs)
        xyz = gs.get_xyz.detach()
        E_doc, cnt_doc = self._E_variant(xyz, None, a.jbgs_e_depth_tol)
        D = self._render_train_depths(gs)
        E_rend, cnt_rend = self._E_variant(xyz, D, a.jbgs_e_depth_tol)
        lock_rend, _ = J.lock_rule(E_rend, cnt_rend, drift, prior, a.jbgs_e_threshold, a.jbgs_e_depth_tol)
        prot_doc = prior & (E_doc < a.jbgs_e_threshold)
        prot_rend_plain = prior & (E_rend < a.jbgs_e_threshold)
        off_prior = prior & (cnt == 0) & (drift > a.jbgs_e_depth_tol)
        pr = prior
        dE_doc = (E - E_doc).abs()[pr]
        dE_rend = (E - E_rend).abs()[pr]

        def med(x):
            return float(x.float().median()) if x.numel() else float("nan")
        nd = drift[newly & prior]
        row = dict(iteration=iteration, n=n, n_prior=int(prior.sum()), n_prot=int(fr.sum()), n_newly=int(newly.sum()),
                   n_released=int(released.sum()), n_prior_cnt0=int((prior & (cnt == 0)).sum()),
                   n_off_prior=int(off_prior.sum()), E_mean_prior=float(E[pr].mean()) if pr.any() else float("nan"),
                   cnt_med_prior=med(cnt[pr]), n_prot_doc=int(prot_doc.sum()), n_prot_rend=int(lock_rend.sum()),
                   n_prot_rendrule=int(prot_rend_plain.sum()),
                   flip_impl_not_doc=int((fr & ~prot_doc).sum()), flip_doc_not_impl=int((prot_doc & ~fr).sum()),
                   flip_impl_not_rend=int((fr & ~lock_rend).sum()), flip_rend_not_impl=int((lock_rend & ~fr).sum()),
                   dE_doc_mean=float(dE_doc.mean()) if dE_doc.numel() else float("nan"),
                   dE_rend_mean=float(dE_rend.mean()) if dE_rend.numel() else float("nan"),
                   n_dE_rend_gt0=int((dE_rend > 1e-6).sum()), n_dE_rend_gt025=int((dE_rend > 0.25).sum()),
                   n_dE_doc_gt0=int((dE_doc > 1e-6).sum()),
                   cnt_doc_med=med(cnt_doc[pr]), cnt_rend_med=med(cnt_rend[pr]),
                   n_cnt_doc0=int((pr & (cnt_doc == 0)).sum()), n_cnt_rend0=int((pr & (cnt_rend == 0)).sum()),
                   newly_drift_p10=_qs(nd, (0.1,))[0], newly_drift_p50=_qs(nd, (0.5,))[0],
                   newly_drift_p90=_qs(nd, (0.9,))[0], newly_drift_max=float(nd.max()) if nd.numel() else float("nan"),
                   released_drift_p50=med(drift[released & prior]), prot_drift_p50=med(drift[fr]),
                   seconds=time.monotonic() - t0)
        self.f_E.write(",".join(str(row[c]) for c in self.E_cols) + "\n")
        # per-disk arrays of prior-origin disks (index = row among prior disks at this update)
        sel = prior
        np.savez_compressed(self.dir / "E" / f"E_{iteration:05d}.npz", iteration=iteration,
                            row=torch.nonzero(sel).squeeze(1).cpu().numpy().astype(np.int32),
                            xyz=xyz[sel].cpu().numpy().astype(np.float32),
                            init_id=gs.init_id[sel].cpu().numpy(), drift=drift[sel].cpu().numpy().astype(np.float32),
                            E=E[sel].cpu().numpy().astype(np.float32), cnt=cnt[sel].cpu().numpy().astype(np.int16),
                            E_doc=E_doc[sel].cpu().numpy().astype(np.float32), cnt_doc=cnt_doc[sel].cpu().numpy().astype(np.int16),
                            E_rend=E_rend[sel].cpu().numpy().astype(np.float32), cnt_rend=cnt_rend[sel].cpu().numpy().astype(np.int16),
                            prot=fr[sel].cpu().numpy(), prev_prot=prev[sel].cpu().numpy(),
                            prot_rend=lock_rend[sel].cpu().numpy(), prot_doc=prot_doc[sel].cpu().numpy(),
                            off_prior=off_prior[sel].cpu().numpy(),
                            opacity=gs.get_opacity.squeeze(-1)[sel].cpu().numpy().astype(np.float32))
        if iteration in (self.E_iters[0], self.E_iters[-1]):
            np.savez_compressed(self.dir / "maps" / f"render_depth_E_{iteration:05d}.npz",
                                **{k: D[k].cpu().numpy().astype(np.float32) for k in D})
        self.events.append(dict(iteration=iteration, event="E_update", n_prot=row["n_prot"], n_newly=row["n_newly"],
                                n_released=row["n_released"]))
        del D

    # ------------------------------------------------------------------------------------------ step hooks
    @torch.no_grad()
    def before_step(self, iteration, gs):
        self.cur_iter = iteration
        self.g, prior, fr = self._groups(gs)
        self.b = {q: getattr(gs, PARAM[q]).detach().clone() for q in QTY}
        op = gs.get_opacity.squeeze(-1)
        p = self.g["prot"]
        e_upd = iteration in self.E_iters
        newly = (fr & ~self.prev_frozen) if (e_upd and self.prev_frozen is not None and
                                             self.prev_frozen.shape[0] == fr.shape[0]) else torch.zeros_like(fr)
        if e_upd and iteration == self.E_iters[0]:
            newly = fr.clone()          # first update: every protected disk is newly protected
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
        if iteration == self.iterations:
            self.final(iteration, gs)

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
