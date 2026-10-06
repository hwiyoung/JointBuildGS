"""PHD-MAIN-PREP-DISCARD-RULE-v1 5.1: the two changed files of fork r11, made from the frozen r10 files (stdlib only).

  python3 make_fork_r11_files.py --r10 <R10>/sources/GeoGS-conf-guided-v1-r10 --out fork_r11/

r11 = r10 with
  jbgs_judgment.py         the shared module src/phd/prior_propagation_v5 (registration, caps, tallies, rules, switches moved in
                           from the measurement; v3 rules byte-identical for what r10 calls); the discard-rule variants
                           (--jbgs_rule, default 'current' = r10); the seven ablation switches (--jbgs_sw_<name>, default 1 = r10);
                           the dry-init report records the switches, the rule and the MVS-term weights
  scene/dataset_readers.py an explicit train / test split (environment JBGS_SPLIT_JSON = {"train": [...], "test": [...]} of image
                           names); without it the native llffhold split (the box views of the prep measure drop training views
                           without a depth map, which would shift llffhold)
Every replacement is asserted to match exactly once; train.py, gaussian_model.py and the rest of the tree stay r10's.
scientific_verdict: null."""
import argparse
from pathlib import Path

R11_DOC = '''Judgment-guided stage-2 optimization for GeoGS, revision r11 (JointBuildGS PHD-MAIN-PREP-DISCARD-RULE-v1).

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
'''

PATCHES = [
    ('"""Judgment-guided stage-2 optimization for GeoGS, revision r10 (JointBuildGS PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).',
     '"""' + R11_DOC + 'Judgment-guided stage-2 optimization for GeoGS, revision r10 (JointBuildGS PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).'),
    ('''try:  # r9: the shared module is copied into the fork root as src/phd/prior_propagation_v3 (build_fork_r9.py)
    from src.phd.prior_propagation_v3 import conversion as ppc
    from src.phd.prior_propagation_v3 import locations as ppl
    from src.phd.prior_propagation_v3 import orientation as ppo
    from src.phd.prior_propagation_v3 import rule as ppr
    from src.phd.prior_propagation_v3 import seat as pps
except ImportError:  # pragma: no cover - r6 behaviour stays available without the module
    ppc = ppl = ppo = ppr = pps = None''',
     '''try:  # r11: the shared module is copied into the fork root as src/phd/prior_propagation_v5 (build_fork_r11.py)
    from src.phd.prior_propagation_v5 import conversion as ppc
    from src.phd.prior_propagation_v5 import locations as ppl
    from src.phd.prior_propagation_v5 import orientation as ppo
    from src.phd.prior_propagation_v5 import rule as ppr
    from src.phd.prior_propagation_v5 import rules as pprules
    from src.phd.prior_propagation_v5 import seat as pps
    from src.phd.prior_propagation_v5 import switches as ppsw
except ImportError:  # pragma: no cover - r6 behaviour stays available without the module
    ppc = ppl = ppo = ppr = pps = pprules = ppsw = None'''),
    ('REVISION = "r10"', 'REVISION = "r11"'),
    ('''    g.add_argument("--jbgs_stop_on_red", type=int, default=1, help="1: a red binding check stops the run (ORDER 4/7)")''',
     '''    g.add_argument("--jbgs_stop_on_red", type=int, default=1, help="1: a red binding check stops the run (ORDER 4/7)")
    # r11: discard-rule variants and ablation switches (shared module v5)
    g.add_argument("--jbgs_rule", default="current", help="r11: discard rule (prior_propagation_v5.rules.RULES); current = r10")
    g.add_argument("--jbgs_prop_pairs", default="", help="r11: unit_view_pairs.npz of the stage-1 product (rule variants)")
    g.add_argument("--jbgs_prop_knn", default="", help="r11: knn.npz of the stage-1 product (rule variants)")
    g.add_argument("--jbgs_markcode_dir", default="", help="r11: per-view mark codes (threshold index at which a pixel turns agree)")
    for _n in ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior"):
        g.add_argument(f"--jbgs_sw_{_n}", type=int, default=1, help=f"r11 switch {_n}: 1 = on (the method), 0 = off")'''),
    ('''def truncated_prior_loss(D, P, tau, w, hi=4.0, denom=None):''',
     '''def plain_prior_loss(D, P, tau, w, denom=None):
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


def rho_plain(r, tau, hi=4.0):
    """r11 switch prior_band off: rho(r) = |r| (for the code test of the penalty shape)."""
    return torch.abs(r)


def protection_mask(sw_protection, prior, E, threshold, u, bound, patch_judgment):
    """r11: eq. (7) as r9/r10 (rule.protected), or no protection at all when the switch is off."""
    lock, low, near, conflict = ppr.protected(prior, E, threshold, u, bound, patch_judgment)
    if not sw_protection:
        lock = torch.zeros_like(lock)
    return lock, low, near, conflict


def truncated_prior_loss(D, P, tau, w, hi=4.0, denom=None):'''),
    # switches and sets in __init__
    ('''        self.train_names = {c.image_name for c in self.train_cams}
        H, W = self.all_cams[0].image_height, self.all_cams[0].image_width''',
     '''        self.train_names = {c.image_name for c in self.train_cams}
        self.sw = {n: bool(int(getattr(args, f"jbgs_sw_{n}", 1))) for n in ("confidence_mask", "judgment", "propagation", "prior_band",
                                                                          "protection", "init_exclusion", "prior")}
        self.rule_name = getattr(args, "jbgs_rule", "current")
        if ppsw is not None and tuple(self.sw) != tuple(ppsw.NAMES):
            raise RuntimeError("switch names differ from the shared module")
        H, W = self.all_cams[0].image_height, self.all_cams[0].image_width'''),
    ('''        self.A = _load_set(root / "conf", names, self.size, "cuda")
        self.M = _load_set(root / "mvs", names, self.size, "cuda")''',
     '''        conf_set, mvs_set = ("conf", "mvs") if self.sw["confidence_mask"] else ("conf_photometric", "mvs_photometric")   # r11
        self.A = _load_set(root / conf_set, names, self.size, "cuda")
        self.M = _load_set(root / mvs_set, names, self.size, "cuda")'''),
    ('''        self.lambda_prior = float(args.jbgs_lambda_prior) if self.mode in ("P", "P0") else 0.0''',
     '''        self.lambda_prior = float(args.jbgs_lambda_prior) if (self.mode in ("P", "P0") and self.sw["prior"]) else 0.0   # r11 switch prior'''),
    ('''        self.init_filter = dict(applied=False)
        self.prop = None
        seat_kept = None
        if self.mode in ("P", "P0") and getattr(args, "jbgs_prop_store", ""):''',
     '''        self.init_filter = dict(applied=False)
        self.prop = None
        seat_kept = None
        self.prior_removed = 0
        if not self.sw["prior"]:   # r11 switch prior off: no prior-origin Gaussians (image-only base), no prior term
            pm = gaussians.origin == ORIGIN_PRIOR
            self.prior_removed = int(pm.sum())
            if bool(pm.any()):
                gaussians.prune_points(pm)
            self.init_filter = dict(applied=True, rule="r11 switch prior off: every prior-origin point removed", n_prior_removed=self.prior_removed)
        elif self.mode in ("P", "P0") and getattr(args, "jbgs_prop_store", ""):'''),
    ('''        meta = dict(mode=self.mode, revision=REVISION, size=[H, W], views=names, train_views=sorted(self.train_names),''',
     '''        meta = dict(mode=self.mode, revision=REVISION, switches=self.sw, rule=self.rule_name, size=[H, W], views=names, train_views=sorted(self.train_names),'''),
    ('''        if self.mode in ("P", "P0"):
            missing = [nm for nm in self.train_names if nm not in self.P]
            if missing:
                raise ValueError(f"prior maps missing for training views: {missing}")
        if self.mode == "P":
            missing = [nm for nm in self.train_names if nm not in self.TAU]''',
     '''        if self.mode in ("P", "P0") and self.sw["prior"]:
            missing = [nm for nm in self.train_names if nm not in self.P]
            if missing:
                raise ValueError(f"prior maps missing for training views: {missing}")
        if self.mode == "P" and self.sw["prior"]:
            missing = [nm for nm in self.train_names if nm not in self.TAU]'''),
    # prop_init: tag, rule variants, switches, drop
    ('''        st = ppl.load_store(args.jbgs_prop_store)
        tag = args.jbgs_prop_tag
        state, vote, E0, ns0 = st[f"state_{tag}"], st[f"vote_{tag}"], st[f"E_{tag}"], st[f"n_seeing_{tag}"]
        q, k, r = args.jbgs_prop_majority, int(args.jbgs_prop_min_evidence), float(args.jbgs_prop_max_distance)
        J, (mis, kd, kv) = ppl.propagate(st, state, vote, q, k, r)
        J_loc = ppl.location_judgment(state, vote, J)
        why = ppr.undetermined_why(state, J, kd, mis, k, r)''',
     '''        st = ppl.load_store(args.jbgs_prop_store)
        tag = args.jbgs_prop_tag if self.sw["confidence_mask"] else f"{args.jbgs_prop_tag}_maskoff"   # r11 switch confidence_mask
        state, vote, E0, ns0 = st[f"state_{tag}"], st[f"vote_{tag}"], st[f"E_{tag}"], st[f"n_seeing_{tag}"]
        q, k, r = args.jbgs_prop_majority, int(args.jbgs_prop_min_evidence), float(args.jbgs_prop_max_distance)
        if self.rule_name == "current":
            J, (mis, kd, kv) = ppl.propagate(st, state, vote, q, k, r)
        else:   # r11-1: rule variant from the stage-1 tallies and the gathered support ids (same gathering as propagate)
            sfx = "" if self.sw["confidence_mask"] else "_maskoff"
            pairs = dict(np.load(args.jbgs_prop_pairs.replace(".npz", f"{sfx}.npz")))
            kn = np.load(args.jbgs_prop_knn.replace(".npz", f"{sfx}.npz"))
            mis, kd, kid = kn["mis"], kn["k_dist"], kn["k_id"]
            st_r, vote, J, _ = pprules.apply(pairs, len(state), mis, kd, kid, self.rule_name, q, k, r)
            if not np.array_equal(st_r, state):
                raise RuntimeError("rule tallies give other states than the product")
            kv = np.where(kid >= 0, vote[np.maximum(kid, 0)], ppr.V_NONE)
        vote, J, J_loc = ppsw.judgment_level(state, vote, J, self.sw)   # r11-2: judgment / propagation switches (identity when on)
        why = ppr.undetermined_why(state, J, kd, mis, k, r)'''),
    ('''        conflict = has & (stt == ppr.ST_MISSING) & (Jt == ppr.J_CONFLICT)
        drop = conflict''',
     '''        conflict = has & (stt == ppr.ST_MISSING) & (Jt == ppr.J_CONFLICT)
        drop = conflict if self.sw["init_exclusion"] else torch.zeros_like(conflict)   # r11 switch init_exclusion'''),
    # g_p: judgment switch and rule threshold of pixels without a patch
    ('''        LM = _load_set(Path(args.jbgs_locmap_dir), names, self.size, "cuda", dtype=np.int32)
        MK = _load_set(Path(args.jbgs_markmap_dir), names, self.size, "cuda", dtype=np.int32)
        Jl_t = self.prop["J_loc"]
        for name in names:
            lm = LM[name].long(); mk = MK[name].long(); A = self.A[name]; P = self.P.get(name)
            located = lm >= 0
            Jl = torch.full_like(lm, ppr.J_NONE); Jl[located] = Jl_t[lm[located]]
            off = ppr.prior_term_off(located, Jl, A, mk)''',
     '''        LM = _load_set(Path(args.jbgs_locmap_dir), names, self.size, "cuda", dtype=np.int32)
        sfx = "" if self.sw["confidence_mask"] else "_maskoff"
        t_rule = pprules.RULES[self.rule_name]["t"] if pprules is not None else 1.0
        if t_rule == 1.0:
            MK = _load_set(Path(args.jbgs_markmap_dir + sfx), names, self.size, "cuda", dtype=np.int32)
        else:   # r11-1: own mark of a pixel without a patch at the rule's threshold (mark code <= threshold index -> agree)
            ti = pprules.THRESHOLDS.index(float(t_rule))
            MC = _load_set(Path(args.jbgs_markcode_dir + sfx), names, self.size, "cuda", dtype=np.int32)
            MK = {kk: torch.where(v < 0, torch.full_like(v, ppr.MARK_NONE),
                                  torch.where(v <= ti, torch.full_like(v, ppr.MARK_AGREE), torch.full_like(v, ppr.MARK_CONFLICT))) for kk, v in MC.items()}
        Jl_t = self.prop["J_loc"]
        for name in names:
            lm = LM[name].long(); mk = MK[name].long(); A = self.A[name]; P = self.P.get(name)
            located = lm >= 0
            Jl = torch.full_like(lm, ppr.J_NONE); Jl[located] = Jl_t[lm[located]]
            off = ppr.prior_term_off(located, Jl, A, mk)
            if not self.sw["judgment"]:   # r11 switch judgment off: nothing discarded anywhere
                off = torch.zeros_like(off)'''),
    # losses: prior band and prior switches
    ('''        if self.mode in ("P", "P0"):
            P = self.P.get(cam_name)
            if P is not None:
                if self.mode == "P":
                    gw = getattr(self, "GW", {}).get(cam_name)        # r8-1: g_p (eq. 4); r6 path: 1 - c_p
                    w = gw if gw is not None else 1.0 - A
                    prior, n, hole, beyond = truncated_prior_loss(D, P, self.TAU[cam_name], w, self.args.jbgs_trunc_hi, denom)''',
     '''        if self.mode in ("P", "P0") and self.sw["prior"]:   # r11 switch prior off: no prior term
            P = self.P.get(cam_name)
            if P is not None:
                if self.mode == "P":
                    gw = getattr(self, "GW", {}).get(cam_name)        # r8-1: g_p (eq. 4); r6 path: 1 - c_p
                    w = gw if gw is not None else 1.0 - A
                    if self.sw["prior_band"]:
                        prior, n, hole, beyond = truncated_prior_loss(D, P, self.TAU[cam_name], w, self.args.jbgs_trunc_hi, denom)
                    else:   # r11 switch prior_band off: rho = |r|
                        prior, n, hole, beyond = plain_prior_loss(D, P, self.TAU[cam_name], w, denom)'''),
    # protection switch
    ('''        lock, low, near, conflict = ppr.protected(prior, E, a.jbgs_e_threshold, u, bound, Jl)
        far = low & ~near''',
     '''        lock, low, near, conflict = protection_mask(self.sw["protection"], prior, E, a.jbgs_e_threshold, u, bound, Jl)   # r11 switch protection
        far = low & ~near'''),
    # dry-init report additions
    ('''        rep = dict(revision=REVISION, init=self.init_filter, first_E=row)''',
     '''        rep = dict(revision=REVISION, switches=self.sw, rule=self.rule_name, init=self.init_filter, first_E=row)
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
                                 n_prior_now=int((gaussians.origin == ORIGIN_PRIOR).sum()), n_prior_removed=self.prior_removed)'''),
    ('''        if self.prop is not None:
            located = self.g_located
            prior = gaussians.origin == ORIGIN_PRIOR''',
     '''        if self.prop is not None and self.g_located is not None:
            located = self.g_located
            prior = gaussians.origin == ORIGIN_PRIOR'''),
]

READER_PATCH = (
    '''    if eval:
        train_cam_infos = [c for idx, c in enumerate(cam_infos) if idx % llffhold != 0]
        test_cam_infos = [c for idx, c in enumerate(cam_infos) if idx % llffhold == 0]''',
    '''    _split = os.environ.get("JBGS_SPLIT_JSON", "")   # r11 (PHD-MAIN-PREP-DISCARD-RULE-v1): explicit train / test names
    if _split:
        import json as _json
        _sp = _json.loads(open(_split).read())
        _tr, _te = set(_sp["train"]), set(_sp.get("test", []))
        train_cam_infos = [c for c in cam_infos if c.image_name in _tr]
        test_cam_infos = [c for c in cam_infos if c.image_name in _te] if eval else []
        if len(train_cam_infos) != len(_tr):
            raise ValueError(f"split: {len(_tr) - len(train_cam_infos)} training names not in the scene")
    elif eval:
        train_cam_infos = [c for idx, c in enumerate(cam_infos) if idx % llffhold != 0]
        test_cam_infos = [c for idx, c in enumerate(cam_infos) if idx % llffhold == 0]''')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--r10", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); (out / "scene").mkdir(parents=True, exist_ok=True)
    s = (Path(a.r10) / "jbgs_judgment.py").read_text()
    for old, new in PATCHES:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"patch target found {n} times: {old[:90]!r}")
        s = s.replace(old, new)
    (out / "jbgs_judgment.py").write_text(s)
    t = (Path(a.r10) / "scene/dataset_readers.py").read_text()
    if t.count(READER_PATCH[0]) != 1:
        raise SystemExit("dataset_readers patch target not found once")
    (out / "scene/dataset_readers.py").write_text(t.replace(READER_PATCH[0], READER_PATCH[1]))
    print("r11 files written", out)


if __name__ == "__main__":
    main()
