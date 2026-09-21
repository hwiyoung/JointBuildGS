"""Step 4 (jointbuildgs:dev): verification design v2 of the stage-1 products A and tau.
Definitions (configs/phd/stage1_verify_v2/experiment.json): width pool = roof, residual axis = vertical
(camera-Z reported), tau = max(2.5 s2, spec), out-of-width = yes & |r_v - m2_nominal| > tau_nominal.
Scenes per prior: nominal (registered), biased_small, biased_main. A and MVS depth are the stage-1 arrays.
Writes out_v2/: stats_v2.csv, checks_v2.json, figures/, report_v2.md, stage2_config_v2_{L,M}.json."""
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
from PIL import Image

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v1 import conversion as conv  # noqa: E402

for _fp in ["/fonts/NotoSansCJK-Regular.ttc"]:
    if Path(_fp).exists():
        fm.fontManager.addfont(_fp)
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_fp).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
ART = Path("/artifacts/JointBuildGS")
CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
C = CFG["constants"]
S1 = ART / CFG["stage1_relative"]
V2 = Path("/v2")
OUT = V2 / ("out_v2_data" if CFG["definitions"].get("tau_rule_mode", "max") == "data" else "out_v2")
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
SPEC = C["tau_spec_m"]
K, SIG, NMAD = C["k_tolerance"], C["outlier_sigma"], C["nmad_factor"]
SCENES = ["nominal", "biased_small", "biased_main"]
SETS = CFG["injection"]["sets"]
INJ = json.loads((V2 / "injection_v2.json").read_text())
t_start = time.time()


def qvec2R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w],
                     [2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w],
                     [2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y]])


def read_cams_txt(p):
    cams = {}
    for l in Path(p).read_text().splitlines():
        if l.strip() and not l.startswith("#"):
            t = l.split()
            cams[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
    return cams


def read_imgs_txt(p):
    imgs = {}
    for l in Path(p).read_text().splitlines():
        t = l.split()
        if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
            imgs[t[9]] = dict(q=[float(x) for x in t[1:5]], t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))
    return imgs


def two_pass(x):
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return dict(n=0, m=None, s=None, n2=0, m2=None, s2=None, out_frac=None)
    m = float(np.median(x))
    s = float(NMAD * np.median(np.abs(x - m)))
    keep = np.abs(x - m) <= SIG * s if s > 0 else np.ones(x.size, bool)
    m2 = float(np.median(x[keep]))
    s2 = float(NMAD * np.median(np.abs(x[keep] - m2)))
    return dict(n=int(x.size), m=m, s=s, n2=int(keep.sum()), m2=m2, s2=s2, out_frac=float(1 - keep.mean()))


MODE = CFG["definitions"].get("tau_rule_mode", "max")


def tau_of(st, prior):
    td = K * st["s2"] if st["s2"] is not None else None
    if MODE == "data":
        return dict(tau_data=td, tau_spec=SPEC[prior], tau=td if td is not None else SPEC[prior], tau_source="data", error_scale=SPEC[prior])
    return dict(tau_data=td, tau_spec=SPEC[prior], tau=max(td, SPEC[prior]) if td is not None else SPEC[prior], tau_source="data" if (td is not None and td >= SPEC[prior]) else "spec")


cams = read_cams_txt(SPARSE / "cameras.txt")
imgs = read_imgs_txt(SPARSE / "images.txt")
stems = sorted(Path(n).stem for n in (SCENE / "images").iterdir() if n.suffix.lower() == ".jpg")
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
Z = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz")
poly_region_code = Z["poly_region_code"]
poly_normal = np.zeros((len(poly_region_code), 3), np.float32)
for p in PJ["polygons"]:
    poly_normal[p["poly_index"]] = p["normal"]
supplied = SCENE / "lod2_prior/raw_depth"


def load_prior(prior, scene, stem):
    d = np.load(V2 / f"inputs_v2/prior_render/{prior}_{scene}/lod2_prior/raw_depth/{stem}.npy").astype(np.float32)
    ok = np.isfinite(d) & (d > 0) & (d < 1e6)
    return np.where(ok, d, np.nan).astype(np.float32), ok


samples = defaultdict(list)   # (prior, scene, axis, subset) -> arrays
per_view, cov_rows, reg_check = [], [], []
fig_arrays = {}
FV = CFG["figure_view"]
_cnt = {st_: int(np.isin(np.load(V2 / "inputs_v2/faceid_biased_small" / f"{st_}.npy"), SETS["small"]["faces"]).sum()) for st_ in stems}
FV_SMALL = max(_cnt, key=_cnt.get)
FIGVIEWS = {"main": FV, "small": FV_SMALL}
for vi, stem in enumerate(stems):
    t0 = time.time()
    im = imgs[stem + ".JPG"]
    cam = cams[im["cam"]]
    fx, fy, cx, cy = cam["p"]
    W, H = cam["W"], cam["H"]
    R = qvec2R(im["q"])
    A = np.load(S1 / "out/conf" / f"{stem}_conf.npy")
    mvs = np.load(S1 / "inputs/mvs_full" / f"{stem}_depth.npy")
    poly = np.load(V2 / "inputs_v2/faceid" / f"{stem}.npy")
    region = np.where(poly >= 0, poly_region_code[np.maximum(poly, 0)], 0).astype(np.uint8)
    roof = region == 1
    # [PHD-STAGE2-R7-PROPAGATION-v1] one conversion for stage 1 and stage 2: src/phd/prior_propagation_v1/conversion.py
    # (roof-like vertical, wall-like along the normal -- the former |d_z| fallback on walls is gone). This v2 script keeps
    # its own normal input (the nominal LoD2 polygon map); the r7 pipeline passes the scene's own normals.
    d = conv.pixel_rays(fx, fy, cx, cy, R, W, H)
    vfac = conv.factor(poly_normal[np.maximum(poly, 0)], d, has_surface=poly >= 0)
    del d
    inj_fp = {name: np.isin(poly, spec["faces"]) & roof for name, spec in SETS.items()}   # nominal footprint of the injected faces
    inj_seen = {name: np.isin(np.load(V2 / f"inputs_v2/faceid_biased_{name}" / f"{stem}.npy"), spec["faces"]) for name, spec in SETS.items()}  # biased scene: raised face itself visible
    tp_ids = np.array([pp_["poly_index"] for pp_ in PJ["polygons"] if pp_["is_target"] and pp_["region"] == "roof"])
    for prior in "LM":
        pd_n, ok_n = load_prior(prior, "nominal", stem)
        if prior == "M":  # registration check of the nominal v2 render against the author-supplied arrays
            sd = np.load(supplied / f"{stem}.npy").astype(np.float32)
            sok = np.isfinite(sd) & (sd > 0) & (sd < 1e6)
            sel = roof & sok & ok_n & (A == 1)
            reg_check.append(dict(view=stem, roof_px=int(sel.sum()), median_vertical_supplied_minus_v2nominal_m=float(np.median(((sd - pd_n) * vfac)[sel])) if sel.any() else None))
        for scene in SCENES:
            pd, pok = (pd_n, ok_n) if scene == "nominal" else load_prior(prior, scene, stem)
            yes = (A == 1) & pok
            r = np.where(yes, mvs - pd, np.nan).astype(np.float32)
            rv = np.where(yes & roof, r * vfac, np.nan).astype(np.float32)
            pool = yes & roof
            samples[(prior, scene, "vert", "all")].append(rv[pool])
            samples[(prior, scene, "camz", "all")].append(r[pool])
            st = two_pass(rv[pool])
            per_view.append(dict(prior=prior, scene=scene, axis="vert", subset="all", view=stem, **st))
            n_mask = int((pok & roof).sum())
            cov_rows.append(dict(prior=prior, scene=scene, view=stem, n_prior_roof=n_mask, n_yes=int(pool.sum()), coverage=(pool.sum() / n_mask) if n_mask else None))
            if scene == "nominal":
                # per-face right-scene material (vertical residual samples by target roof face)
                for pi in tp_ids:
                    selp = pool & (poly == pi)
                    if selp.any():
                        samples[(prior, "nominal", "vert", f"face{pi}")].append(rv[selp])
            if scene != "nominal":
                name = scene.replace("biased_", "")
                changed = ok_n & pok & (np.abs(pd - pd_n) > 1e-4)
                inj_ref = inj_fp[name] & changed      # reference mask: nominal footprint where the prior moved (includes step faces)
                inj = (inj_seen[name] & pok) if prior == "M" else inj_ref   # M: pixels that see the raised face itself; L: footprint (TIN has no face ids)
                samples[(prior, scene, "vert", "inj_ref")].append(rv[pool & inj_ref] if prior == "M" else rv[pool & inj])
                samples[(prior, scene, "shift_vert", "inj_ref")].append(((pd_n - pd) * vfac)[pool & inj_ref])
                # for pixels that see the raised face outside the nominal footprint, r_v uses the raised face normal (same face) so vfac is valid
                rv_inj = np.where(pool & inj, r * vfac, np.nan).astype(np.float32) if prior == "M" else rv
                samples[(prior, scene, "vert", "inj")].append(rv_inj[pool & inj])
                samples[(prior, scene, "camz", "inj")].append(r[pool & inj])
                samples[(prior, scene, "vert", "excl")].append(rv[pool & ~inj_fp[name] & ~inj])
                samples[(prior, scene, "shift_vert", "inj")].append(((pd_n - pd) * vfac)[pool & inj & ok_n])
                per_view.append(dict(prior=prior, scene=scene, axis="vert", subset="inj", view=stem, **two_pass(rv_inj[pool & inj])))
                per_view[-1]["n_footprint_yes"] = int((pool & inj_fp[name]).sum())
                per_view[-1]["n_footprint_unchanged_yes"] = int((pool & inj_fp[name] & ~changed).sum())
            for tag, fv in FIGVIEWS.items():
                if stem == fv:
                    fig_arrays[f"{tag}|{prior}_{scene}_rv"] = rv.astype(np.float16)
                    fig_arrays[f"{tag}|{prior}_{scene}_r"] = r.astype(np.float16)
                    if scene != "nominal":
                        fig_arrays[f"{tag}|{prior}_{scene}_inj"] = inj
            if scene != "nominal" and prior == "L":
                # variant mask for L: pixels whose TIN surface actually rose by more than tau_L (excludes the eave transition band)
                disp = np.where(ok_n & pok, (pd_n - pd) * vfac, 0)
                samples[(prior, scene, "vert", "inj_disp")].append(rv[pool & inj_fp[name] & (disp > SPEC["L"])])
    for tag, fv in FIGVIEWS.items():
        if stem == fv:
            fig_arrays[f"{tag}|A"] = A
            fig_arrays[f"{tag}|region"] = region
            fig_arrays[f"{tag}|poly"] = poly
            for name in SETS:
                fig_arrays[f"{tag}|fp_{name}"] = inj_fp[name]
    print(f"[{vi+1}/{len(stems)}] {stem} {time.time()-t0:.1f}s", flush=True)

# ---------------------------------------------------------------- overall statistics, widths, checks
overall = {}
for key, lst in samples.items():
    vals = np.concatenate(lst) if lst else np.zeros(0, np.float32)
    samples[key] = vals
    if key[2] == "shift_vert" or key[3].startswith("face") or key[3] == "inj_disp":
        continue
    st = two_pass(vals)
    if key[2] == "vert":
        st.update(tau_of(st, key[0]))
    st["quantiles"] = {f"p{int(q*100):02d}": float(v) for q, v in zip([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99], np.quantile(vals, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]))} if vals.size else {}
    overall[key] = st
checks = {"definitions": CFG["definitions"], "registration": CFG["registration"], "injection": INJ, "per_prior": {}}
for prior in "LM":
    ref = overall[(prior, "nominal", "vert", "all")]
    ref_c = overall[(prior, "nominal", "camz", "all")]
    m2, s2, tau = ref["m2"], ref["s2"], ref["tau"]
    pp = {"nominal": dict(n=ref["n"], m=ref["m"], s=ref["s"], m2=m2, s2=s2, tau_data=ref["tau_data"], tau_spec=ref["tau_spec"], tau=tau, tau_source=ref["tau_source"],
                          camz=dict(m2=ref_c["m2"], s2=ref_c["s2"]), quantiles=ref["quantiles"])}
    # centre (after registration)
    pp["center"] = dict(abs_m2_lt_s2=bool(abs(m2) < s2), m2_over_tau=abs(m2) / tau)
    # right scene
    x = samples[(prior, "nominal", "vert", "all")]
    dev = np.abs(x - m2)
    pp["right_scene"] = dict(out_tau=float((dev > tau).mean()), out_3s=float((dev > SIG * s2).mean()), out_4tau=float((dev > 4 * tau).mean()), n=int(x.size),
                             pass_if_L=bool((dev > tau).mean() <= C["right_scene_pass_L"]))
    # right scene by face (where do the nominal out-of-width pixels sit?)
    pp["right_scene_by_face"] = {}
    for key in list(samples):
        if key[0] == prior and key[1] == "nominal" and key[3].startswith("face"):
            xf = samples[key]
            pp["right_scene_by_face"][key[3][4:]] = dict(n=int(xf.size), out_tau=float((np.abs(xf - m2) > tau).mean()) if xf.size else None,
                                                        median=float(np.median(xf)) if xf.size else None, share_of_out=None)
    tot_out = sum(v["n"] * v["out_tau"] for v in pp["right_scene_by_face"].values() if v["out_tau"] is not None)
    for v in pp["right_scene_by_face"].values():
        if v["out_tau"] is not None and tot_out:
            v["share_of_out"] = float(v["n"] * v["out_tau"] / tot_out)
    # wrong scene per injection set
    for name in SETS:
        scene = f"biased_{name}"
        xi = samples[(prior, scene, "vert", "inj")]
        sh = samples[(prior, scene, "shift_vert", "inj")]
        xr = samples[(prior, scene, "vert", "inj_ref")]
        shr = samples[(prior, scene, "shift_vert", "inj_ref")]
        devi = np.abs(xi - m2)
        st_all = overall[(prior, scene, "vert", "all")]
        st_ex = overall[(prior, scene, "vert", "excl")]
        n_fp = sum(r["n_footprint_yes"] for r in per_view if r["prior"] == prior and r["scene"] == scene and r["subset"] == "inj")
        n_unch = sum(r["n_footprint_unchanged_yes"] for r in per_view if r["prior"] == prior and r["scene"] == scene and r["subset"] == "inj")
        pp[scene] = dict(
            delta_m=CFG["injection"]["delta_m"][prior], delta_over_tau=CFG["injection"]["delta_m"][prior] / tau,
            n_injected_yes=int(xi.size), n_footprint_yes=n_fp, footprint_unchanged_yes=n_unch,
            injected_fraction_of_roof_pool=float(xi.size / max(st_all["n"], 1)),
            shift_vert_median=float(np.median(sh)) if sh.size else None, shift_vert_p05_p95=[float(v) for v in np.quantile(sh, [0.05, 0.95])] if sh.size else None,
            residual_vert_median=float(np.median(xi)) if xi.size else None,
            sensitivity_tau=float((devi > tau).mean()) if xi.size else None, sensitivity_3s=float((devi > SIG * s2).mean()) if xi.size else None,
            sensitivity_pass=bool(xi.size and (devi > tau).mean() >= C["sensitivity_pass"]),
            mask_definition="M: biased-scene face id in set (raised face visible) & yes; L: nominal footprint & prior changed & yes",
            L_variant_displacement_gt_tau=(dict(n=int(samples[(prior, scene, "vert", "inj_disp")].size),
                                                sensitivity_tau=float((np.abs(samples[(prior, scene, "vert", "inj_disp")] - m2) > tau).mean()) if samples[(prior, scene, "vert", "inj_disp")].size else None)
                                           if prior == "L" else None),
            reference_mask=dict(definition="nominal footprint & prior changed & yes (includes step faces / revealed neighbours)", n=int(xr.size),
                                sensitivity_tau=float((np.abs(xr - m2) > tau).mean()) if xr.size else None,
                                shift_vert_median=float(np.median(shr)) if shr.size else None),
            two_scene=dict(tau_nominal=tau, tau_biased_all=st_all["tau"], rel_diff_all=abs(st_all["tau"] - tau) / max(st_all["tau"], tau),
                           tau_biased_excluding_injected=st_ex["tau"], rel_diff_excl=abs(st_ex["tau"] - tau) / max(st_ex["tau"], tau),
                           tau_data_nominal=ref["tau_data"], tau_data_biased_all=st_all["tau_data"], tau_data_biased_excl=st_ex["tau_data"],
                           within_10pct_all=bool(abs(st_all["tau"] - tau) / max(st_all["tau"], tau) <= C["two_scene_rel"]),
                           s2_nominal=s2, s2_biased_all=st_all["s2"], s2_biased_excl=st_ex["s2"], m2_biased_all=st_all["m2"], m2_biased_excl=st_ex["m2"]))
    checks["per_prior"][prior] = pp
checks["registration_check_M"] = dict(per_view=reg_check, median_over_views_m=float(np.median([r["median_vertical_supplied_minus_v2nominal_m"] for r in reg_check if r["median_vertical_supplied_minus_v2nominal_m"] is not None])))
capL = [r["coverage"] for r in cov_rows if r["prior"] == "L" and r["scene"] == "nominal" and r["coverage"] is not None]
checks["capability"] = dict(roof_coverage_pooled=float(sum(r["n_yes"] for r in cov_rows if r["prior"] == "L" and r["scene"] == "nominal") / sum(r["n_prior_roof"] for r in cov_rows if r["prior"] == "L" and r["scene"] == "nominal")),
                            roof_coverage_per_view_median=float(np.median(capL)), roof_coverage_per_view_min=float(np.min(capL)))
checks["capability"]["hold_upper_bound_pooled"] = 1 - checks["capability"]["roof_coverage_pooled"]
# verdict (mechanical, prompt rules; primary injection set = small, main reported too)
pp = checks["per_prior"]
fails = []
for prior in "LM":
    for name in SETS:
        if not pp[prior][f"biased_{name}"]["sensitivity_pass"]:
            fails.append(f"틀린 장면 검사 {prior}({name})")
    if not pp[prior]["center"]["abs_m2_lt_s2"]:
        fails.append(f"중심 {prior}")
    if not pp[prior]["biased_small"]["two_scene"]["within_10pct_all"]:
        fails.append(f"두 장면 τ {prior}")
if not pp["L"]["right_scene"]["pass_if_L"]:
    fails.append("맞는 장면 검사 L")
verdict = "넘길 수 있다" if not fails else "다시 재야 한다"
checks["quality_failures"] = fails
checks["verdict_first_line"] = verdict
sep_tau = abs(pp["L"]["nominal"]["tau"] - pp["M"]["nominal"]["tau"]) / max(pp["L"]["nominal"]["tau"], pp["M"]["nominal"]["tau"])
checks["handover"] = dict(tau_L=pp["L"]["nominal"]["tau"], tau_M=pp["M"]["nominal"]["tau"], four_tau_L=4 * pp["L"]["nominal"]["tau"], four_tau_M=4 * pp["M"]["nominal"]["tau"],
                          tau_source=dict(L=pp["L"]["nominal"]["tau_source"], M=pp["M"]["nominal"]["tau_source"]),
                          m_ignorable=dict(L=pp["L"]["center"]["abs_m2_lt_s2"], M=pp["M"]["center"]["abs_m2_lt_s2"]),
                          separate_arms=bool(sep_tau >= 0.2), rel_diff_tau=sep_tau, one_m_over_tau=dict(L=1 / pp["L"]["nominal"]["tau"], M=1 / pp["M"]["nominal"]["tau"]),
                          injection_multiple_used=dict(L=pp["L"]["biased_small"]["delta_over_tau"], M=pp["M"]["biased_small"]["delta_over_tau"]))
checks["runtime_s"] = time.time() - t_start
checks["scientific_verdict"] = None
(OUT / "checks_v2.json").write_text(json.dumps(checks, indent=1, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else (o.item() if hasattr(o, "item") else str(o))))
with (OUT / "stats_v2.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["prior", "scene", "axis", "subset", "view", "n", "m", "s", "n2", "m2", "s2", "out_frac", "tau_data", "tau_spec", "tau", "tau_source"])
    for (prior, scene, axis, subset), st in sorted(overall.items()):
        w.writerow([prior, scene, axis, subset, "ALL", st["n"], st["m"], st["s"], st["n2"], st["m2"], st["s2"], st["out_frac"], st.get("tau_data", ""), st.get("tau_spec", ""), st.get("tau", ""), st.get("tau_source", "")])
    for r in per_view:
        w.writerow([r["prior"], r["scene"], r["axis"], r["subset"], r["view"], r["n"], r["m"], r["s"], r["n2"], r["m2"], r["s2"], r["out_frac"], "", "", "", ""])
with (OUT / "coverage_v2.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(cov_rows[0].keys()))
    w.writeheader()
    w.writerows(cov_rows)
np.savez_compressed(OUT / "fig_arrays_v2.npz", **fig_arrays)

# ---------------------------------------------------------------- stage-2 config v2
for prior in "LM":
    n_ = pp[prior]["nominal"]
    cfg = {"prior": prior, "conf_dir": "../PHD-STAGE1-CONF-TOL-CONFLICT-v1/out/conf", "conf_files": "{view}_conf.npy (uint8 0/1, 4082x5644); unchanged from stage 1",
           "tau": n_["tau"], "tau_spec": n_["tau_spec"], "tau_data": n_["tau_data"], "tau_axis": "vertical (roof faces); convert per pixel to camera-Z with |n.d|/|n_z| of the prior face normal",
           "tau_pool": "roof", "cap": 3 * n_["tau"], "seed_distance": n_["tau"], "conf_threshold_E": 0.5, "lr_scale_low": 0.01, "opacity_floor": 0.5, "E_refresh_iters": 500,
           "registration": {"dz_m": CFG["registration"][f"{prior}_dz_m"], "note": CFG["registration"][f"{prior}_source"]},
           "expected": {"roof_coverage": checks["capability"]["roof_coverage_pooled"], "undetermined_upper": checks["capability"]["hold_upper_bound_pooled"],
                        "right_scene_out_of_width_tau": pp[prior]["right_scene"]["out_tau"],
                        "sensitivity_small_injection": pp[prior]["biased_small"]["sensitivity_tau"], "sensitivity_main_injection": pp[prior]["biased_main"]["sensitivity_tau"],
                        "injection_delta_m": CFG["injection"]["delta_m"][prior], "residual_vert_median_injected_small": pp[prior]["biased_small"]["residual_vert_median"]},
           "flags": {"registration_ok": pp[prior]["center"]["abs_m2_lt_s2"], "bias_verified": bool(pp[prior]["biased_small"]["sensitivity_pass"] and pp[prior]["biased_main"]["sensitivity_pass"]),
                     "tolerance_source": n_["tau_source"], "run_both_priors": checks["handover"]["separate_arms"], "conflict_sane": pp[prior]["biased_small"]["sensitivity_pass"],
                     "two_scene_tau_stable": pp[prior]["biased_small"]["two_scene"]["within_10pct_all"]},
           "provenance": {"task_id": CFG["task_id"], "verdict_first_line": verdict, "scientific_verdict": None}}
    (OUT / f"stage2_config_v2_{prior}.json").write_text(json.dumps(cfg, indent=2))

# ---------------------------------------------------------------- figures (same view and colour scales as stage 1)
KO = {"nominal": "정상(정합 후)", "biased_small": "편향 소면 3개", "biased_main": "편향 본지붕", "L": "L(ALS)", "M": "M(LoD2)"}
HR = [-3.0, 4.0]
edges = np.linspace(HR[0], HR[1], int(round((HR[1] - HR[0]) / C["hist_bin_m"])) + 1)
centers = 0.5 * (edges[:-1] + edges[1:])
fig, axs = plt.subplots(2, 3, figsize=(16, 7), dpi=110, sharex=True)
for i, prior in enumerate("LM"):
    ref = overall[(prior, "nominal", "vert", "all")]
    for j, scene in enumerate(SCENES):
        ax = axs[i, j]
        for subset, col, lab in [("all", "#1f5fbf" if scene == "nominal" else "#c62828", "지붕 전체"), ("inj", "#e6781e", "주입 면")]:
            if (prior, scene, "vert", subset) not in samples:
                continue
            v = samples[(prior, scene, "vert", subset)]
            h, _ = np.histogram(v[np.isfinite(v)], bins=edges)
            ax.plot(centers, h / max(h.sum(), 1), color=col, lw=1.2, label=lab)
        for kk, ls in [(1, "-"), (4, ":")]:
            for sgn in (-1, 1):
                ax.axvline(ref["m2"] + sgn * kk * ref["tau"], color="#444", lw=1.6 if kk == 1 else 1.0, ls=ls)
        ax.axvline(ref["m2"], color="k", lw=0.8)
        st = overall[(prior, scene, "vert", "all")]
        ax.set_title(f"{KO[prior]} {KO[scene]} — 연직 잔차, n={st['n']:,} m2={st['m2']:.3f} s2={st['s2']:.3f} τ(정상)={ref['tau']:.3f}", fontsize=8.5)
        ax.set_xlim(*HR)
        ax.grid(alpha=0.3)
        if i == 0 and j == 1:
            ax.legend(fontsize=8)
for ax in axs[1]:
    ax.set_xlabel("r_v = (MVS − prior) 연직 환산 (m)")
fig.suptitle("그림 1(v2): 연직 잔차 히스토그램 — 지붕 풀; 굵은 세로선 ±τ, 점선 ±4τ(정상 장면 기준), 주황 = 주입 면의 예 픽셀", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "fig1_v2_hist.png")
plt.close(fig)
# width-out maps: main/nominal on the stage-1 figure view, small injection on the view that sees the small faces best
for scene in ["biased_small", "biased_main", "nominal"]:
    tag = "small" if scene == "biased_small" else "main"
    fv = FIGVIEWS[tag]
    img = Image.open(S1 / "out/viewer_png/views" / f"{fv}_image.png")
    vw, vh = img.size
    A0 = fig_arrays[f"{tag}|A"]
    Hf, Wf = A0.shape
    ys = np.minimum(((np.arange(vh) + 0.5) * Hf / vh).astype(int), Hf - 1)
    xs = np.minimum(((np.arange(vw) + 0.5) * Wf / vw).astype(int), Wf - 1)
    small = lambda a: a[np.ix_(ys, xs)]
    roof0 = fig_arrays[f"{tag}|region"] == 1
    fig, axs = plt.subplots(2, 3, figsize=(16, 8.4), dpi=100)
    for i, prior in enumerate("LM"):
        ref = overall[(prior, "nominal", "vert", "all")]
        rv = fig_arrays[f"{tag}|{prior}_{scene}_rv"].astype(np.float32)
        yes = np.isfinite(rv)
        out = yes & (np.abs(rv - ref["m2"]) > ref["tau"])
        rgb = np.full(rv.shape + (3,), 150, np.uint8)
        rgb[yes] = 255
        rgb[out] = (220, 30, 30)
        rgb[~roof0] = 70
        axs[i, 0].imshow(img)
        axs[i, 0].set_title(f"{KO[prior]} {KO[scene]} — 영상 ({fv[-6:-2]})", fontsize=9)
        axs[i, 1].imshow(small(rgb))
        axs[i, 1].set_title(f"폭 밖(|r_v−m2|>τ={ref['tau']:.2f} m) 빨강 · 예 흰색 · 아니오 회색 · 지붕 밖 진회색", fontsize=9)
        rr = np.where(roof0, rv, np.nan)
        im2 = axs[i, 2].imshow(small(rr), cmap="RdBu_r", vmin=-1.5, vmax=1.5)
        axs[i, 2].set_title("연직 잔차 r_v (−1.5…+1.5 m, 지붕만)", fontsize=9)
        if scene != "nominal":
            m = small(fig_arrays[f"{tag}|{prior}_{scene}_inj"])
            cont = np.zeros_like(m)
            cont[1:, :] |= m[1:, :] != m[:-1, :]
            cont[:, 1:] |= m[:, 1:] != m[:, :-1]
            yy, xx = np.where(cont)
            axs[i, 1].plot(xx, yy, ".", ms=0.5, color="#00c000")
            axs[i, 2].plot(xx, yy, ".", ms=0.5, color="#00c000")
        for ax in axs[i]:
            ax.axis("off")
    fig.suptitle(f"그림 2(v2) {KO[scene]}: 폭 밖 픽셀 지도 — 초록 윤곽 = 참값 기반 주입 마스크(정상 발자국 ∧ prior 깊이 변화)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / f"fig2_v2_widthout_{scene}.png")
    plt.close(fig)
# cross-sections through the injected faces (each on its own figure view)
fig, axs = plt.subplots(2, 2, figsize=(15, 7), dpi=100)
for j, prior in enumerate("LM"):
    ref = overall[(prior, "nominal", "vert", "all")]
    for i, (name, scene) in enumerate([("small", "biased_small"), ("main", "biased_main")]):
        tag = name
        mask = fig_arrays[f"{tag}|{prior}_{scene}_inj"]
        roof0 = fig_arrays[f"{tag}|region"] == 1
        rows = mask.sum(1)
        row = int(np.argmax(rows))
        ax = axs[i, j]
        xsel = np.where(roof0[row] | mask[row])[0]
        for sc, col in [("nominal", "#1f5fbf"), (scene, "#c62828")]:
            rv = fig_arrays[f"{tag}|{prior}_{sc}_rv"].astype(np.float32)[row]
            ax.plot(xsel, rv[xsel], ".", ms=1.5, color=col, alpha=0.7, label=KO[sc])
        xin = np.where(mask[row])[0]
        if xin.size:
            ax.axvspan(xin.min(), xin.max(), color="#00c000", alpha=0.12, label="주입 마스크")
        ax.axhspan(ref["m2"] - ref["tau"], ref["m2"] + ref["tau"], color="#999", alpha=0.25, label=f"허용 구간 ±τ={ref['tau']:.2f}")
        ax.axhline(ref["m2"] + CFG["injection"]["delta_m"][prior], color="k", lw=0.6, ls="--", label=f"m2+Δ({CFG['injection']['delta_m'][prior]} m)")
        ax.set_ylim(-1.5, CFG["injection"]["delta_m"][prior] + 1.5)
        ax.set_title(f"{KO[prior]} — {KO[scene]}, 시점 {FIGVIEWS[tag][-6:-2]} 이미지 행 {row}", fontsize=9)
        ax.grid(alpha=0.3)
        if i == 0 and j == 0:
            ax.legend(fontsize=7, markerscale=4, loc="upper left")
axs[1, 0].set_xlabel("열 (픽셀)")
axs[1, 1].set_xlabel("열 (픽셀)")
fig.suptitle("그림 3(v2): 주입 면을 가로지르는 연직 잔차 단면 — 정상(파랑)은 허용 구간 안, 편향(빨강)은 Δ만큼 위", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "fig3_v2_cross_sections.png")
plt.close(fig)

# ---------------------------------------------------------------- report v2
f_ = lambda x, d=3: "NA" if x is None else (f"{x:.{d}f}" if isinstance(x, (int, float)) else str(x))
pct = lambda x: "NA" if x is None else f"{100*x:.1f}%"
yn = lambda b: "통과" if b else "미달"
L = []
A_ = L.append
A_(verdict + ".")
A_("")
A_("# 1단계 산출물 검증 설계 v2 보고서 — PHD-STAGE1-VERIFY-v2")
A_("")
A_("## 0. 무엇을 바꿨나")
A_("")
A_("- 측정(관측 신뢰도 지도 A, MVS 깊이, 정상 장면)은 그대로다. 바꾼 것은 검증 장면과 정의다: (1) 주입을 옛 자료 전체가 아니라 지붕면 일부로(참값 기반 마스크 있음), (2) 주입량을 각 prior의 폭의 3배 이상으로(L 1.0 m = 8.3τ_L, M 3.0 m = 3.0τ_M), (3) 폭의 픽셀 풀 = 지붕(1단계 발주서 7절: L 벽면은 참고값), (4) 잔차 축 = 연직(사양과 같은 축; 2단계는 픽셀별 면 법선으로 환산), (5) 두 prior의 블록 정합 이동 반영(L +1.9 cm, M 복구 메시 +12.2 cm로 저자 배열 프레임에 맞춤).")
A_(f"- M 정합 확인: 정합 후 정상 M 렌더와 저자 제공 배열의 지붕 연직 차 중앙값 = {f_(checks['registration_check_M']['median_over_views_m'])} m (정합 전 −0.122 m).")
A_(f"- 주입 집합: 소면 3개(3387·3389·3404, 177 m², 지붕 예 픽셀의 {pct(pp['L']['biased_small']['injected_fraction_of_roof_pool'])}), 본지붕(3396, 620 m², {pct(pp['L']['biased_main']['injected_fraction_of_roof_pool'])}). M은 올린 면의 경계에 수직 단면을 붙여 틈이 없게 했고, L은 면 발자국 안의 ALS 점을 올렸다(소면 {INJ['sets']['small']['L_points_raised']}점, 본지붕 {INJ['sets']['main']['L_points_raised']}점). 주입 마스크 = 정상 발자국 ∧ prior 깊이가 실제로 변한 픽셀(처마 띠 효과 제거).")
A_(f"- 실행: 15시점, {checks['runtime_s']:.0f} s, 상수 k={K}, 3s 제외, 사양 L {SPEC['L']} / M {SPEC['M']} m.")
A_("")
A_("## 1. 산출물 ② 허용 오차 τ (지붕 풀, 연직 축)")
A_("")
A_("| 값 | L | M |")
A_("|---|---:|---:|")
for k, name in [("n", "표본 수"), ("m2", "m2"), ("s2", "s2"), ("tau_data", "2.5·s2"), ("tau_spec", "사양"), ("tau", "τ"), ("tau_source", "살아남은 쪽")]:
    A_(f"| {name} | " + " | ".join((f"{pp[p]['nominal'][k]:,}" if k == "n" else f_(pp[p]['nominal'][k])) for p in "LM") + " |")
A_(f"| 카메라 Z 축 참고 m2 / s2 | {f_(pp['L']['nominal']['camz']['m2'])} / {f_(pp['L']['nominal']['camz']['s2'])} | {f_(pp['M']['nominal']['camz']['m2'])} / {f_(pp['M']['nominal']['camz']['s2'])} |")
A_("")
A_("| 확인 | L | M |")
A_("|---|---|---|")
A_(f"| 중심 \\|m2\\| < s2 (정합 후) | {f_(pp['L']['nominal']['m2'])} vs {f_(pp['L']['nominal']['s2'])} → {yn(pp['L']['center']['abs_m2_lt_s2'])} (m/τ {pct(pp['L']['center']['m2_over_tau'])}) | {f_(pp['M']['nominal']['m2'])} vs {f_(pp['M']['nominal']['s2'])} → {yn(pp['M']['center']['abs_m2_lt_s2'])} |")
for p in "LM":
    ts = pp[p]["biased_small"]["two_scene"]
    A_(f"| 두 장면(소면 주입, 주입 제외 없이) {p} | τ 정상 {f_(ts['tau_nominal'])} vs 편향 {f_(ts['tau_biased_all'])} (상대차 {pct(ts['rel_diff_all'])}; 2.5s2 {f_(ts['tau_data_nominal'])} vs {f_(ts['tau_data_biased_all'])}) → {yn(ts['within_10pct_all'])}; 주입 제외 시 τ {f_(ts['tau_biased_excluding_injected'])} | |")
A_("")
A_("## 2. 산출물 ① 관측 신뢰도 지도 A")
A_("")
A_("| 검사 | L | M | 기준 |")
A_("|---|---:|---:|---|")
for name in ["small", "main"]:
    sc = f"biased_{name}"
    A_(f"| 틀린 장면 민감도, {KO[sc]} (Δ = L {CFG['injection']['delta_m']['L']} / M {CFG['injection']['delta_m']['M']} m) | {f_(pp['L'][sc]['sensitivity_tau'])} ({pp['L'][sc]['n_injected_yes']:,} px) | {f_(pp['M'][sc]['sensitivity_tau'])} ({pp['M'][sc]['n_injected_yes']:,} px) | ≥ 0.9 → L {yn(pp['L'][sc]['sensitivity_pass'])}, M {yn(pp['M'][sc]['sensitivity_pass'])} |")
    A_(f"| 같은 값, 참고 3s 기준 | {f_(pp['L'][sc]['sensitivity_3s'])} | {f_(pp['M'][sc]['sensitivity_3s'])} | 참고 |")
    A_(f"| 주입 면의 연직 잔차 중앙값 / prior 이동 중앙값 | {f_(pp['L'][sc]['residual_vert_median'])} / {f_(pp['L'][sc]['shift_vert_median'])} m | {f_(pp['M'][sc]['residual_vert_median'])} / {f_(pp['M'][sc]['shift_vert_median'])} m | Δ 복원 |")
    A_(f"| 발자국 안에서 prior가 안 변한 예 픽셀(제외됨) | {pp['L'][sc]['footprint_unchanged_yes']:,} / {pp['L'][sc]['n_footprint_yes']:,} | {pp['M'][sc]['footprint_unchanged_yes']:,} / {pp['M'][sc]['n_footprint_yes']:,} | 기록 |")
A_(f"| L 변형 마스크(TIN 표면이 τ_L보다 실제로 올라간 픽셀만) 민감도, 소면 / 본지붕 | {f_(pp['L']['biased_small']['L_variant_displacement_gt_tau']['sensitivity_tau'])} / {f_(pp['L']['biased_main']['L_variant_displacement_gt_tau']['sensitivity_tau'])} | — | 참고 |")
A_(f"| 맞는 장면 폭 밖 비율(정상, τ 기준) | {pct(pp['L']['right_scene']['out_tau'])} (3s {pct(pp['L']['right_scene']['out_3s'])}, 4τ {pct(pp['L']['right_scene']['out_4tau'])}) | {pct(pp['M']['right_scene']['out_tau'])} | L ≤ 5% → {yn(pp['L']['right_scene']['pass_if_L'])}; M 기록 |")
for p in "LM":
    rf = pp[p]["right_scene_by_face"]
    A_(f"| 맞는 장면 폭 밖의 면별 분해 {p} (면: 비율 / 전체 폭 밖 중 몫) | " + "; ".join(f"{k}: {pct(v['out_tau'])} / {pct(v['share_of_out'])}" for k, v in sorted(rf.items(), key=lambda kv: -(kv[1]['share_of_out'] or 0))) + " | | 기록 |")
for name in ["small", "main"]:
    sc = f"biased_{name}"
    A_(f"| 참고 마스크(정상 발자국 ∧ prior 변화; 단면·드러난 이웃 포함) 민감도 / prior 이동 중앙값, {KO[sc]} | {f_(pp['L'][sc]['reference_mask']['sensitivity_tau'])} / {f_(pp['L'][sc]['reference_mask']['shift_vert_median'])} m | {f_(pp['M'][sc]['reference_mask']['sensitivity_tau'])} / {f_(pp['M'][sc]['reference_mask']['shift_vert_median'])} m | 참고 |")
rsf = V2 / "out_v2/right_scene_facts_v2.json"
if rsf.exists():
    RS = json.loads(rsf.read_text())
    for p in "LM":
        q = RS[p]
        A_(f"| 맞는 장면 폭 밖 픽셀의 정체 {p} | 면 경계 {q['edge_band_px']}px 띠 {pct(q['edge_band_share'])}, 작은 면 내부 {pct(q['small_faces_share'])}, 본지붕 내부 {pct(q['main_interior_share'])}(본지붕 예 픽셀 대비 {pct(q['main_interior_fraction_of_yes'])}); MVS가 prior보다 가까움 {pct(q['mvs_nearer_share'])} | | 기록 |")
A_(f"| 능력: 지붕 커버리지 합산 / 사진별 중앙값(최소) | {pct(checks['capability']['roof_coverage_pooled'])} / {pct(checks['capability']['roof_coverage_per_view_median'])} ({pct(checks['capability']['roof_coverage_per_view_min'])}) | 같음 | 보류 상한 {pct(checks['capability']['hold_upper_bound_pooled'])} |")
A_("")
A_("## 3. 판정")
A_("")
A_(f"- 미달 항목: {', '.join(fails) if fails else '없음'}.")
A_(f"- 첫 줄 규칙: 품질 검사 전부 통과면 '넘길 수 있다', 하나라도 미달이면 '다시 재야 한다'. → **{verdict}**.")
if fails == ["맞는 장면 검사 L"]:
    A_("- 유일한 미달은 정상 장면에서 L의 지붕 예 픽셀 중 τ_L(0.12 m) 밖 비율이 '수 %'의 검수자 해석(≤5%)을 넘는 것이다. 이 값은 시험 설계가 아니라 데이터(2022년 ALS TIN 대 2024년 영상)의 성질이므로 다시 재도 바뀌지 않는다. 위 '정체' 행이 그 픽셀이 면 경계 띠와 작은 면(지붕 위 구조물)에 몰려 있는지, 본지붕 내부에 흩어져 있는지를 말해 준다. 검수 프롬프트의 실패 해석('예 안에 엉터리 깊이')은 후자일 때 성립한다. '수 %'의 수치 확정은 사용자 몫이다.")
A_("")
A_("## 4. 인계값(2단계)")
A_("")
h = checks["handover"]
A_(f"- A: 1단계 `out/conf/{{view}}_conf.npy` 그대로. 지붕 커버리지 {pct(checks['capability']['roof_coverage_pooled'])}, 보류 상한 {pct(checks['capability']['hold_upper_bound_pooled'])}.")
A_(f"- τ_L = {f_(h['tau_L'])} m ({h['tau_source']['L']}), 4τ_L = {f_(h['four_tau_L'])} m; τ_M = {f_(h['tau_M'])} m ({h['tau_source']['M']}), 4τ_M = {f_(h['four_tau_M'])} m. 축 = 연직(지붕 면 법선 기준); 2단계 손실이 카메라 Z에서 돌면 픽셀별로 |n·d|/|n_z|로 나눠 쓴다.")
A_(f"- m 무시 가능: L {yn(h['m_ignorable']['L'])}, M {yn(h['m_ignorable']['M'])} (정합 이동 L +{CFG['registration']['L_dz_m']:.4f} m, M +{CFG['registration']['M_dz_m']:.4f} m 적용 후).")
A_(f"- L·M 분리: {'분리' if h['separate_arms'] else '분리 불필요'} (τ 상대차 {pct(h['rel_diff_tau'])}). 1 m ÷ τ_L = {h['one_m_over_tau']['L']:.2f}, 1 m ÷ τ_M = {h['one_m_over_tau']['M']:.2f}. 이번 검증의 주입 배수: L {h['injection_multiple_used']['L']:.1f}τ, M {h['injection_multiple_used']['M']:.1f}τ. 2단계에서 일부러 넣을 틀림도 같은 배수 이상을 권한다.")
A_("- 설정 파일: `out_v2/stage2_config_v2_L.json`, `out_v2/stage2_config_v2_M.json` (1단계 설정에 축·풀·정합·v2 기대치를 덧붙인 판).")
A_("")
A_("## 5. 그림")
A_("")
A_("- `figures/fig1_v2_hist.png` 연직 잔차 히스토그램(정상·편향 소면·편향 본지붕 × L·M, ±τ·±4τ 선, 주입 면 별도 곡선).")
A_("- `figures/fig2_v2_widthout_biased_small.png`, `..._biased_main.png`, `..._nominal.png` 폭 밖 지도(시점 0005, 초록 = 주입 마스크 윤곽).")
A_("- `figures/fig3_v2_cross_sections.png` 주입 면을 지나는 단면.")
A_("- 표: `out_v2/stats_v2.csv`(ALL·시점별), `out_v2/coverage_v2.csv`, `out_v2/checks_v2.json`.")
A_("")
A_("## 6. 남는 한계")
A_("")
A_("- 이 검증은 1단계 작성자와 같은 세션이 설계하고 계산했다. 검수 프롬프트 6절의 독립 재현은 별도 세션이 `out_v2/stats_v2.csv`를 원 배열에서 다시 만들어야 한다(입력: 1단계 `out/conf`, `inputs/mvs_full`, v2 `inputs_v2/prior_render`, `inputs_v2/faceid`).")
A_("- 주입 마스크: M은 편향 메시의 면 id 렌더로 '올린 지붕면 자체가 보이는 픽셀'(참값 기반), L은 TIN에 면 id가 없어 정상 발자국 ∧ prior 변화 픽셀. 참고로 M도 후자로 계산한 값을 병기했는데, 3 m 단면과 드러난 이웃 면이 들어가 민감도가 낮게 나온다.")
A_("- 두 장면 검사는 소면 주입(지붕 풀의 수 %)에서만 설계대로 평가된다. 본지붕 주입은 풀의 대부분을 바꾸므로 민감도만 본다.")
A_("- L 본지붕 주입의 처마 띠: ALS 점은 LoD2 발자국 다각형 안에서만 올렸는데 실제 처마는 그 다각형 밖으로 나가므로, TIN이 올린 점과 안 올린 처마 점 사이를 보간해 발자국 가장자리 한 점 간격 폭에서 이동량이 0에서 Δ로 기운다. 시점 0005의 처마 근처 행이 그 띠와 거의 나란해 단면에 경사로 보인다. 변형 마스크 행이 그 띠를 뺀 값이다.")
A_("- M 소면 주입(Δ 3 m)은 작은 면을 자기 발자국 밖으로 옮겨(시차) '올린 면이 보이는' 픽셀 대부분에서 MVS가 다른 표면(뒤의 본관 벽·지면)을 본다. 그래서 잔차 중앙값이 Δ가 아니라 더 크다. 이 검사는 '틀린 옛 자료가 켜지는가'를 재는 것이고, Δ 복원은 본지붕 주입(중앙값 3.006 m)이 보여 준다.")
A_("")
A_(f"<!-- END {CFG['task_id']} -->")
(OUT / "report_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[:1]), "| fails:", fails, "| runtime", round(checks["runtime_s"]), "s")
for p in "LM":
    print(p, "nominal m2 %.4f s2 %.4f tau %.3f (%s) | small sens %.3f shift %.3f | main sens %.3f | right %.3f | two-scene rel %.3f" % (
        pp[p]["nominal"]["m2"], pp[p]["nominal"]["s2"], pp[p]["nominal"]["tau"], pp[p]["nominal"]["tau_source"], pp[p]["biased_small"]["sensitivity_tau"] or -1,
        pp[p]["biased_small"]["shift_vert_median"] or -1, pp[p]["biased_main"]["sensitivity_tau"] or -1, pp[p]["right_scene"]["out_tau"], pp[p]["biased_small"]["two_scene"]["rel_diff_all"]))
