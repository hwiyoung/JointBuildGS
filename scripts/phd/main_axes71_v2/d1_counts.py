"""PHD-MAIN-AXES71-v2 일 1 (정의 확인): the counts and the reproduction checks of order 4 (jointbuildgs:dev, CPU, read only; through
run_cpu_ax.sh). No training, no GPU, no rule of its own: every array is read from the earlier tasks' files and every rule re-applied here is
the earlier code's (file:line in the comments). Output: AX/work/d1/counts.json (unrounded values, sources). scientific_verdict: null.

Per case (B0_b10, B173nb_b10, R1rep_b10 x LoD2, ALS), inside the evaluation range (region file in_eval) unless a key says otherwise:
  codes      patches and area by code_ext_v3
  ga         gt_med = patch median of the label source's 'GT - prior' (s04_gt_v7.py: roof dz = z_GT - z_prior, wall (v . n)); recomputed
             from the ownership rows (s1_common.owner_rows) and compared; = dist71 Unit.ratio * tau (dm_common.py:181)
  na         the image-depth misfit of a patch used for code 3: mvs_minus_gt_at_gt (v2, roof-like, >= 5 values) or mvs_minus_prior - gt_med
             (v1_kept); code 2/3 and 11/12 re-derived (regions.split_v2, regions_v1.py:79-81) and compared with code_ext_v3
  da         premise_value and the split of code 3 (premise.split, K = LoD2 1, ALS 2) re-derived and compared
  ra         obs_masked patches by code, the pre-filter (photometric) misfit v_photo and its branches
  ma         the judgment path of the missing patches (codes 4, 13): borrow file (und_judge.py) + region file; table 2 of the fixtest
             order re-counted; the trained runs' own locations.npz and the fixtest's fix-B records compared
  nogt       patches without a GT row (dist71 has_gt rule: any row of S1/defs/<site>/rows_<prior>.npz) by code, with gt_points / gt_n
  nopatch    scene GT points (dm_common.owner_of_scene_points) without a patch, with a patch outside the range
  excl       exclusion cells (trees, transient; ALS prior-side trees) inside the range, their GT points, the excluded patches
  size       patch area distribution and the median nearest-neighbour centre distance
  depth      the MVS depth maps and the observation confidence mask the training read (one view per site compared with the COLMAP file)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
import dm_common as DMC  # noqa: E402
from s1_common import boxes, in_eval_uv, label_source, owner_rows, SITES as S1SITES  # noqa: E402
from src.phd.metrics_v3 import regions as RG  # noqa: E402
from src.phd.metrics_v3 import premise as PREM  # noqa: E402

PH = Path("/ph")
S1 = Path("/out")
S0 = Path("/s0")
PREP = Path("/prep")
GT3 = S1 / "v3/box_gt"
FL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
FT = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
AX = PH / "main_axes71_v2/PHD-MAIN-AXES71-v2"
OUT = AX / "work/d1"
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
PRIORS = ("LoD2", "ALS")
K_CONFLICT = {"LoD2": 1.0, "ALS": 2.0}          # regions_v3.py:36
CODES = (0, 2, 3, 4, 5, 11, 12, 13, 14)
J_NONE, J_CONFLICT, J_AGREE, J_MIXED, J_INSUFF = -1, 0, 1, 2, 3   # prior_propagation_v6/rule.py:28
ST_INVISIBLE, ST_SUPPORT, ST_MISSING = 0, 1, 2                   # rule.py:25
T0 = time.time()


def log(*a):
    print(f"{time.time() - T0:7.1f}s", *a, flush=True)


def pa(mask, area):
    return dict(patches=int(mask.sum()), area_m2=float(area[mask].sum()))


def by_code(mask, code, area):
    return {str(c): pa(mask & (code == c), area) for c in CODES}


def q(x, qs=(0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)):
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    return dict(n=int(len(x)), mean=float(x.mean()), **{f"q{int(round(100 * v)):02d}": float(np.quantile(x, v)) for v in qs})


def prop_locations(site, prior, seed):
    """the trained result's own pre-training judgment (monitor/locations.npz) of prop_<prior>_s<seed>."""
    if site == "B173nb_b10":
        return S0 / "stage0" / f"b{seed + 1}_{prior}" / "model/monitor/locations.npz"
    return S1 / "stage1" / site / f"prop_{prior}_s{seed}" / "model/monitor/locations.npz"


def case(site, prior, gt):
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    code = R["code_ext_v3"].astype(np.int64)
    ie = R["in_eval"].astype(bool)
    area = R["area"].astype(np.float64)
    kind = R["kind"].astype(np.int64)
    tau = R["tau"].astype(np.float64)
    gtm = R["gt_med"].astype(np.float64)
    L = len(code)
    e = dict(n_patches_file=L, in_eval=pa(ie, area), codes=by_code(ie, code, area),
             codes_by_kind={("roof" if kv == 1 else "wall"): by_code(ie & (kind == kv), code, area) for kv in (1, 2)})
    e["tau_values_m"] = {("roof" if kv == 1 else "wall"): sorted(set(np.round(tau[ie & (kind == kv)], 9).tolist())) for kv in (1, 2) if (ie & (kind == kv)).any()}

    # ---------------------------------------------------------------- (가) gt_med
    rows = owner_rows(GT3, site, prior, label_source(GT3, site, prior, L))
    pa_all = np.concatenate([r[2] for r in rows])
    va_all = np.concatenate([r[3].astype(np.float64) for r in rows])
    med, cnt = RG.patch_median(pa_all, va_all, L)
    has_med = np.isfinite(gtm)
    d = np.abs(med[has_med] - gtm[has_med])
    U = DMC.Unit(site, prior, gt)
    e["ga"] = dict(
        rule="gt_med = 패치의 소유 참값 점 'GT − prior'의 중앙값 (지붕꼴 연직 z_GT − z_prior, 벽꼴 (X − 벽 위 최근접점)·n)",
        patches_with_gt_med=int(has_med.sum()), recomputed_nan_equal=bool(np.array_equal(np.isfinite(med), has_med)),
        recomputed_max_abs_diff_m=float(d.max()) if len(d) else 0.0, recomputed_over_1e6=int((d > 1e-6).sum()),
        count_equals_gt_n=bool(np.array_equal(cnt, R["gt_n"].astype(np.int64))),
        count_equals_gt_points=bool(np.array_equal(cnt, R["gt_points"].astype(np.int64))),
        dist71_ratio_equals=bool(np.array_equal(U.ratio, np.abs(gtm) / tau, equal_nan=True)),
        sign_in_eval_code11=dict(positive=int((ie & (code == 11) & (gtm > 0)).sum()), negative=int((ie & (code == 11) & (gtm < 0)).sum())),
        label_rule_equal=int((ie & np.isin(code, (2, 3, 4, 5)) & ~(np.abs(gtm) <= tau)).sum()) == 0 and int((ie & np.isin(code, (11, 12, 13, 14)) & ~(np.abs(gtm) > tau)).sum()) == 0,
        min_points_label=int(R["gt_n"][ie & (code != 0)].min()) if (ie & (code != 0)).any() else None)

    # ---------------------------------------------------------------- (나) the image-depth misfit used for code 3
    kept = R["v1_kept"].astype(bool)
    dmg = R["mvs_minus_gt_at_gt"].astype(np.float64)
    nmg = R["n_mvs_at_gt"].astype(np.int64)
    mvp = R["mvs_minus_prior"].astype(np.float64)
    v1 = mvp - gtm                                          # regions_v1.py:79 (MVS - prior) - (GT - prior)
    img_mis = np.where(kept, v1, dmg)
    s23 = ie & np.isin(code, (2, 3))
    s1112 = ie & np.isin(code, (11, 12))
    off = ~(np.abs(img_mis) <= tau)                          # NaN -> off (regions_v1.py:81, regions.py:37-40)
    Z = np.load(FL / "work/obs_masked" / f"region_{site}_{prior}.npz")
    vgeo = Z["v_geo"].astype(np.float64)
    usable = (kind == 1) & (nmg >= 5) & np.isfinite(dmg)     # regions.py:36 (split & roof & n >= 5 & finite)
    e["na"] = dict(
        v2_patches_code23=pa(s23 & ~kept, area), v1_kept_patches_code23=pa(s23 & kept, area),
        v1_kept_by_kind_code23={("roof" if kv == 1 else "wall"): int((s23 & kept & (kind == kv)).sum()) for kv in (1, 2)},
        code3_reproduced=int((s23 & (off == (code == 3))).sum()), code23=int(s23.sum()),
        code12_reproduced=int((s1112 & (off == (code == 12))).sum()), code1112=int(s1112.sum()),
        kept_equals_not_usable_on_split=bool(np.array_equal(kept[s23 | s1112], ~usable[s23 | s1112])),
        fill_v_geo_equal=dict(max_abs_diff_m=float(np.nanmax(np.abs(vgeo[s23] - img_mis[s23]))) if s23.any() else 0.0,
                              nan_equal=bool(np.array_equal(np.isnan(vgeo[s23]), np.isnan(img_mis[s23])))),
        code3_misfit_over_tau=q(np.abs(img_mis[ie & (code == 3)]) / tau[ie & (code == 3)]),
        code3_no_mvs_value=int((ie & (code == 3) & ~np.isfinite(img_mis)).sum()),
        code3_sign=dict(mvs_above=int((ie & (code == 3) & (img_mis > 0)).sum()), mvs_below=int((ie & (code == 3) & (img_mis < 0)).sum())))

    # ---------------------------------------------------------------- (다) premise value and the split of code 3
    pv = R["premise_value"].astype(np.float64)
    viol, within, band = PREM.split(code, pv, tau, K_CONFLICT[prior], R["centre"], radius=2.0)
    c3 = ie & (code == 3)
    e["da"] = dict(
        k=K_CONFLICT[prior], rule="viol = 코드 3 ∧ |premise_value| > kτ (premise.py:15); within = 코드 3 ∧ ¬viol (NaN 포함)",
        premise_value_rule="v1_kept면 mvs_minus_prior, 아니면 지붕 참값 점의 (z_MVS − z_GT) + (z_GT − z_prior) 패치 중앙값 (regions_v3.py:174, 178, 286)",
        violation_equal=bool(np.array_equal(viol, R["premise_violation"].astype(bool))),
        within_equal=bool(np.array_equal(within, R["obs_within_threshold"].astype(bool))),
        band_equal=bool(np.array_equal(band, R["premise_band"].astype(bool))),
        disjoint=int((R["premise_violation"].astype(bool) & R["obs_within_threshold"].astype(bool)).sum()) == 0,
        union_is_code3=bool(np.array_equal(R["premise_violation"].astype(bool) | R["obs_within_threshold"].astype(bool), code == 3)),
        violation=pa(c3 & viol, area), within=pa(c3 & within, area), within_no_value=pa(c3 & within & ~np.isfinite(pv), area),
        premise_over_tau_violation=q(np.abs(pv[c3 & viol]) / tau[c3 & viol]),
        premise_over_tau_within=q(np.abs(pv[c3 & within]) / tau[c3 & within]),
        premise_kept_rows=dict(v1_kept=int((c3 & kept).sum()), v2=int((c3 & ~kept).sum())))

    # ---------------------------------------------------------------- (라) obs_masked
    obs = Z["obs"].astype(bool)
    vph = Z["v_photo"].astype(np.float64)
    br = Z["branch"].astype(np.int64)
    mp = Z["med_pix"].astype(np.float64)
    e["ra"] = dict(
        obs_outside_eval=int((obs & ~ie).sum()), obs=pa(obs & ie, area), obs_by_code=by_code(obs & ie, code, area),
        obs_by_kind={("roof" if kv == 1 else "wall"): pa(obs & ie & (kind == kv), area) for kv in (1, 2)},
        obs_and_violation=pa(obs & ie & R["premise_violation"].astype(bool), area),
        obs_and_within=pa(obs & ie & R["obs_within_threshold"].astype(bool), area),
        obs_code4=pa(obs & ie & (code == 4), area),
        rule_reproduced=bool(np.array_equal(obs, Z["dom"].astype(bool) & np.isfinite(vph) & (np.abs(vph) > tau) &
                                            (Z["pix_sum"] > 0) & (2 * Z["a1_sum"].astype(np.int64) < Z["pix_sum"].astype(np.int64)))),
        dom_equals=bool(np.array_equal(Z["dom"].astype(bool), ie & np.isin(code, (2, 3, 4, 5)))),
        branch=dict(gt_points=int((obs & ie & (br == 1)).sum()), pixels=int((obs & ie & (br == 2)).sum()), none=int((obs & ie & (br == 0)).sum())),
        v_photo_over_tau=q(np.abs(vph[obs & ie]) / tau[obs & ie]),
        v_photo_m=q(vph[obs & ie]),
        v_photo_sign=dict(photo_above_gt=int((obs & ie & (vph > 0)).sum()), photo_below_gt=int((obs & ie & (vph < 0)).sum())),
        med_pix_finite=int((obs & ie & np.isfinite(mp)).sum()),
        pix_branch_equals=float(np.nanmax(np.abs(vph[obs & ie & (br == 2)] - (-mp[obs & ie & (br == 2)] - gtm[obs & ie & (br == 2)])))) if (obs & ie & (br == 2)).any() else None,
        mask_share_a1=q(Z["a1_sum"][obs & ie].astype(np.float64) / np.maximum(Z["pix_sum"][obs & ie].astype(np.float64), 1)),
        geo_misfit_of_obs=dict(has_value=int((obs & ie & np.isfinite(vgeo)).sum()), within_tau=int((obs & ie & (np.abs(vgeo) <= tau)).sum())))

    # ---------------------------------------------------------------- (마) the judgment path of the missing patches
    B = np.load(FL / "work/undecidable" / f"borrow_{site}_{prior}.npz")
    st_file = R["state"].astype(np.int64)
    J = B["J"].astype(np.int64)
    Jl = B["J_loc"].astype(np.int64)
    mis = B["mis"].astype(np.int64)
    bor = B["borrowed"].astype(np.int64)
    viol_f = R["premise_violation"].astype(bool)
    from_viol = np.zeros(L, bool)
    from_viol[mis] = ((bor >= 0) & viol_f[np.maximum(bor, 0)]).any(1)
    n_viol_nb = np.zeros(L, np.int64)
    n_viol_nb[mis] = ((bor >= 0) & viol_f[np.maximum(bor, 0)]).sum(1)
    m413 = ie & np.isin(code, (4, 13))
    path = {}
    for cc in (4, 13):
        for nm, m in (("all", ie & (code == cc)), ("obs", ie & (code == cc) & obs), ("not_obs", ie & (code == cc) & ~obs)):
            path[f"code{cc}_{nm}"] = dict(
                all=pa(m, area), direct=pa(m & (B["state"] == ST_SUPPORT), area),
                borrowed_agree=pa(m & (B["state"] == ST_MISSING) & (J == J_AGREE), area),
                borrowed_conflict=pa(m & (B["state"] == ST_MISSING) & (J == J_CONFLICT), area),
                mixed=pa(m & (B["state"] == ST_MISSING) & (J == J_MIXED), area),
                undetermined_insufficient=pa(m & (B["state"] == ST_MISSING) & (J == J_INSUFF), area),
                none=pa(m & (J == J_NONE), area),
                borrowed_conflict_from_premise=pa(m & (J == J_CONFLICT) & from_viol, area),
                mixed_from_premise=pa(m & (J == J_MIXED) & from_viol, area))
    t2 = dict(wrong_release_code4=int((ie & (code == 4) & (J == J_CONFLICT)).sum()),
              of_which_from_premise=int((ie & (code == 4) & (J == J_CONFLICT) & from_viol).sum()),
              correct_release_code13=int((ie & (code == 13) & (J == J_CONFLICT)).sum()),
              mixed=int((m413 & (J == J_MIXED)).sum()))
    dry = np.load(S3 / "checks/dry" / f"r14_{site}_{prior}" / "model/monitor/locations.npz")
    chk = dict(state_borrow_equals_region=bool(np.array_equal(B["state"], st_file)),
               state_borrow_equals_dry=bool(np.array_equal(B["state"], dry["state"])),
               J_equals_dry=bool(np.array_equal(B["J"], dry["judgment"])), J_loc_equals_dry=bool(np.array_equal(B["J_loc"], dry["unit_judgment"])),
               codes_4_13_all_missing=bool((st_file[ie & np.isin(code, (4, 13))] == ST_MISSING).all()),
               J_mis_equals_J=bool(np.array_equal(B["J_mis"], B["J"][mis])))
    runs = {}
    for seed in (0, 1):
        p = prop_locations(site, prior, seed)
        if p.exists():
            z = np.load(p)
            runs[f"prop_{prior}_s{seed}"] = dict(file=DMC.short(p), state_equal=bool(np.array_equal(z["state"], B["state"])),
                                                judgment_equal=bool(np.array_equal(z["judgment"], B["J"])),
                                                unit_judgment_equal=bool(np.array_equal(z["unit_judgment"], B["J_loc"])))
        else:
            runs[f"prop_{prior}_s{seed}"] = dict(file=DMC.short(p), exists=False)
    fb = FT / "runs" / site / f"fixB_{prior}_s0" / "model/monitor/locations.npz"
    fixb = None
    if fb.exists():
        z = np.load(fb)
        if "judgment_before_own_depth" in z.files:
            jb = z["judgment_before_own_depth"].astype(np.int64)
            ch = z["own_depth_changed"].astype(bool)
            fixb = dict(file=DMC.short(fb), before_equals_borrow_J=bool(np.array_equal(jb, J)),
                        changed_in_eval_code4_conflict=int((ch & ie & (code == 4) & (jb == J_CONFLICT)).sum()),
                        changed_in_eval_code13_conflict=int((ch & ie & (code == 13) & (jb == J_CONFLICT)).sum()),
                        changed_in_eval_mixed_4_13=int((ch & m413 & (jb == J_MIXED)).sum()), changed_all=int(ch.sum()),
                        changed_in_eval_other_codes=int((ch & ie & ~np.isin(code, (4, 13))).sum()))
    e["ma"] = dict(file="SL/work/undecidable/borrow_<site>_<prior>.npz (mis, borrowed, borrowed_dist, borrowed_vote, J_mis, state, vote, J, J_loc)",
                   path=path, table2=t2, checks=chk, trained_runs=runs, fixB=fixb,
                   from_premise_neighbours_median=float(np.median(n_viol_nb[ie & (code == 4) & (J == J_CONFLICT) & from_viol])) if (ie & (code == 4) & (J == J_CONFLICT) & from_viol).any() else None)

    # ---------------------------------------------------------------- patches without GT
    r = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    rp = r["patch"].astype(np.int64)
    has = np.zeros(L, bool)
    has[np.unique(rp)] = True
    assert np.array_equal(has, U.has_gt)
    gtp = R["gt_points"].astype(np.int64)
    gtn = R["gt_n"].astype(np.int64)
    th = r["thin"].astype(bool)
    rows_all = np.bincount(rp, minlength=L)
    rows_thin = np.bincount(rp[th], minlength=L)
    e["nogt"] = dict(
        rule="has_gt = rows_<prior>.npz의 patch에 한 번이라도 나옴 (dm_common.py:196-197; 솎기 전 모든 행)",
        no_rows=pa(ie & ~has, area), no_rows_by_code=by_code(ie & ~has, code, area),
        gt_points_zero=pa(ie & (gtp == 0), area), gt_points_zero_by_code=by_code(ie & (gtp == 0), code, area),
        no_rows_but_gt_points=pa(ie & ~has & (gtp > 0), area), rows_but_gt_points_zero=pa(ie & has & (gtp == 0), area),
        no_rows_by_code_nonzero_gt_points={str(c): int((ie & ~has & (gtp > 0) & (code == c)).sum()) for c in CODES},
        gt_n_equals_gt_points=bool(np.array_equal(gtn, gtp)),
        rows_in_eval=dict(all=int(rows_all[ie].sum()), thinned=int(rows_thin[ie].sum())),
        thinned_rows_by_code={str(c): int(rows_thin[ie & (code == c)].sum()) for c in CODES},
        all_rows_by_code={str(c): int(rows_all[ie & (code == c)].sum()) for c in CODES},
        code0_split=dict(lt5_points=pa(ie & (code == 0) & (gtn < 5), area)))

    # ---------------------------------------------------------------- scene GT points without a patch
    own = DMC.owner_of_scene_points(site, prior, gt)
    n_sc = len(own)
    has_o = own >= 0
    in_ie = np.zeros(n_sc, bool)
    in_ie[has_o] = ie[own[has_o]]
    Xs = gt.Gb
    bx = boxes()[S1SITES[site]]
    e["nopatch"] = dict(
        rule="장면 참값 점(건물 표면 칸의 드론 LiDAR 점, dm_common.SiteGT.bs_idx) 가운데 1단계 소유 파일(B0는 gt_owner_uls)에 패치가 없는 점 (dm_common.py:217-229)",
        scene_points=n_sc, scene_points_in_eval_box=int(in_eval_uv(Xs, bx).sum()),
        scene_points_use=int(gt.G["use_gt_points"][gt.bs_idx].sum()),
        no_patch=int((~has_o).sum()), with_patch=int(has_o.sum()), with_patch_in_eval=int(in_ie.sum()), with_patch_outside_eval=int((has_o & ~in_ie).sum()),
        with_patch_by_code={str(c): int((in_ie & (code[np.maximum(own, 0)] == c)).sum()) for c in CODES},
        no_patch_vertical=int((~has_o & gt.G["vert_gt_points"][gt.bs_idx]).sum()))

    # ---------------------------------------------------------------- exclusion cells, their GT points, excluded patches
    ex = np.load(GT3 / site / "exclusion_cells.npz")
    Lb = np.load(GT3 / site / f"labels_{prior}.npz")
    exc = Lb["excluded"].astype(bool)
    ext = Lb["excluded_trees_transient"].astype(bool)
    exp_ = Lb["excluded_prior_trees"].astype(bool)
    if site.startswith("B0") and (GT3 / site / f"labels_uls_{prior}.npz").exists():   # regions_v1.py:49-53 (B0: ULS label where primary has none)
        Gu = np.load(GT3 / site / f"labels_uls_{prior}.npz")
        use_u = (Lb["label"] < 0) & (Gu["label"] >= 0)
        exc = exc | (use_u & Gu["excluded"].astype(bool))
    e["excl_patches"] = dict(excluded=pa(ie & exc, area), excluded_by_code=by_code(ie & exc, code, area),
                             trees_transient=pa(ie & ext, area), prior_side_trees=pa(ie & exp_, area),
                             prior_side_trees_only=pa(ie & exp_ & ~ext, area),
                             code0_excluded=pa(ie & (code == 0) & exc, area), code0_lt5_not_excluded=pa(ie & (code == 0) & ~exc & (gtn < 5), area),
                             code0_other=pa(ie & (code == 0) & ~exc & (gtn >= 5), area))
    return e, ex


def excl_cells(site, gt):
    """cells (0.5 m survey grid, s04_gt_v6.Grid: e0 690700, n0 5335820) whose centre is inside the evaluation rectangle, and the GT points
    inside the evaluation rectangle in each kind of excluded cell (gt_classes: use = in range & not 'any'; defs_s1.py:52-61)."""
    ex = np.load(GT3 / site / "exclusion_cells.npz")
    ny, nx = ex["any"].shape
    e0, n0, res = 690700.0, 5335820.0, 0.5
    iy, ix = np.mgrid[0:ny, 0:nx]
    cx = e0 + (ix + 0.5) * res - 690953.0
    cy = n0 + (iy + 0.5) * res - 5336071.0
    bx = boxes()[S1SITES[site]]
    inr = in_eval_uv(np.column_stack([cx.ravel(), cy.ravel()]), bx).reshape(ny, nx)
    out = dict(cell_m=res)
    for k in ("trees", "transient", "any", "prior_side_trees"):
        m = ex[k].astype(bool) & inr
        out[k] = dict(cells=int(m.sum()), area_m2=float(m.sum() * res * res))
    m = ex["prior_side_trees"].astype(bool) & ~ex["any"].astype(bool) & inr
    out["prior_side_trees_not_any"] = dict(cells=int(m.sum()), area_m2=float(m.sum() * res * res))
    pts = {}
    for nm, X in gt.X.items():
        src = "gt_points" if nm == 0 else "gt_primary"
        G = gt.G
        inev = in_eval_uv(X, bx)
        excl = G[f"excl_{src}"].astype(bool)
        e0_, n0_ = 690700.0, 5335820.0
        jx = np.floor((X[:, 0] + 690953.0 - e0_) / res).astype(np.int64)
        jy = np.floor((X[:, 1] + 5336071.0 - n0_) / res).astype(np.int64)
        ok = (jx >= 0) & (jx < nx) & (jy >= 0) & (jy < ny)
        pst = np.zeros(len(X), bool)
        pst[ok] = ex["prior_side_trees"][jy[ok], jx[ok]]
        pts[src] = dict(in_eval_box=int(inev.sum()), in_any_cells=int((inev & excl).sum()), use=int(G[f"use_{src}"].sum()),
                        use_equals_box_and_not_any=bool(np.array_equal(G[f"use_{src}"].astype(bool), inev & ~excl)),
                        in_prior_side_trees_not_any=int((inev & pst & ~excl).sum()))
        if nm == 0:
            pts[src]["scene_points_in_any_cells"] = int(excl[gt.bs_idx].sum())
    out["gt_points"] = pts
    return out


def size(site, prior):
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    ie = R["in_eval"].astype(bool)
    area = R["area"].astype(np.float64)
    kind = R["kind"].astype(np.int64)
    C = R["centre"].astype(np.float64)
    out = dict(area_all=q(area[ie]))
    for kn, kv in (("roof", 1), ("wall", 2)):
        m = ie & (kind == kv)
        if m.any():
            out[f"area_{kn}"] = q(area[m])
    idx = np.nonzero(ie)[0]
    dd, _ = cKDTree(C[idx]).query(C[idx], k=2)
    out["nn_centre_3d_m"] = q(dd[:, 1])
    for kn, kv in (("roof", 1), ("wall", 2)):
        k_ = np.nonzero(ie & (kind == kv))[0]
        if len(k_) > 1:
            d2, _ = cKDTree(C[k_]).query(C[k_], k=2)
            out[f"nn_centre_3d_{kn}_m"] = q(d2[:, 1])
    dxy, _ = cKDTree(C[idx, :2]).query(C[idx, :2], k=2)
    out["nn_centre_xy_m"] = q(dxy[:, 1])
    out["area_share_eq_0p0625"] = float((np.abs(area[ie] - 0.0625) < 1e-9).mean())
    return out


def depth_maps(site):
    """the maps the training read (fork maps root) and one view compared with the COLMAP file (s03_stage1_v6.py:376-378)."""
    from common import read_depth_bin
    root = S0 / "fork_inputs/s61" / site / "maps"
    out = dict(maps_root=DMC.short(root), sets={})
    for k in ("mvs", "conf", "mvs_photometric", "conf_photometric", "prior_LoD2", "prior_ALS", "tau_LoD2", "tau_ALS"):
        d = root / k
        out["sets"][k] = dict(exists=d.exists(), files=len(list(d.glob("*.npy"))) if d.exists() else 0,
                              resolves_to=DMC.short(d.resolve()) if d.exists() else None)
    views = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())["train"]
    n = sorted(views)[len(views) // 2]
    G = read_depth_bin(PREP / "mvs" / f"box_{site}" / "stereo/depth_maps" / f"{n}.JPG.geometric.bin")
    M = np.load(root / "mvs" / f"{n}.npy")
    A = np.load(root / "conf" / f"{n}.npy")
    vg = np.isfinite(G) & (G > 0)
    out["check_view"] = dict(view=n, conf_equals_geometric_valid=bool(np.array_equal(A > 0.5, vg)),
                             mvs_equals_geometric_where_valid=bool(np.array_equal(M[vg], G[vg])), mvs_nan_elsewhere=bool(np.isnan(M[~vg]).all()),
                             conf_values=sorted(np.unique(A).tolist()), valid_share=float(vg.mean()))
    if (root / "mvs_photometric").exists():
        P = read_depth_bin(PREP / "mvs" / f"box_{site}" / "stereo/depth_maps" / f"{n}.JPG.photometric.bin")
        Mp = np.load(root / "mvs_photometric" / f"{n}.npy")
        vp = np.isfinite(P) & (P > 0)
        out["check_view"]["mvs_photometric_equals_file_where_valid"] = bool(np.array_equal(Mp[vp], P[vp]))
    out["train_views"] = len(views)
    return out


def main():
    res = dict(task_id="PHD-MAIN-AXES71-v2", item="일 1 정의 확인 (수와 넓이)", written=DMC.now(), script="scripts/phd/main_axes71_v2/d1_counts.py",
               scope="평가 범위(영역 파일 in_eval) 안. 넓이 m², 반올림 전", cases={}, sites={}, scientific_verdict=None)
    for site in SITES:
        gt = DMC.SiteGT(site)
        res["sites"][site] = dict(exclusion_cells=excl_cells(site, gt), depth=depth_maps(site))
        log(site, "site done")
        for prior in PRIORS:
            e, _ = case(site, prior, gt)
            e["size"] = size(site, prior)
            res["cases"][f"{site}/{prior}"] = e
            log(site, prior, "done", json.dumps(e["ma"]["table2"]), e["ra"]["obs"])
        del gt
    res["seconds"] = round(time.time() - T0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    DMC.jdump(OUT / "counts.json", res)
    print("written", OUT / "counts.json", res["seconds"])


if __name__ == "__main__":
    main()
