#!/usr/bin/env python3
"""D12 A/C/D — observability↔defect correlation (A), B1 life/death 2 criteria (C), generation logistic (D).
Reads d12_defect.csv (3-axis GS defect, d4+b1) + P0 observability CSVs (T7 coverage, T9/T11 texture) +
complexity_metric.csv (als_span/levels). Stats via scipy/sklearn -> run in the dev container.
NO retrain. Observe only; verdict=김휘영. EPSG:25832.

Run: docker compose run --rm -T dev python scripts/evidence_and_attributes/diagnostic_tables/d12_analysis.py
Out: results/.../overseg_lever/d12_analysis.json (+ prints tables) + docs/figs/W_D12/*.png
"""
import csv, json, sys
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy import stats
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
P0 = REPO / "phases/p0-audit/docs"
FIG = REPO / "docs/figs/W_D12"; FIG.mkdir(parents=True, exist_ok=True)


def rd(p):
    return list(csv.DictReader(open(p)))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def partial_corr(x, y, Z):
    """Pearson partial correlation of x,y controlling columns of Z (list of arrays). Returns (r,p,n)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    for z in Z:
        mask &= np.isfinite(np.asarray(z, float))
    x, y = x[mask], y[mask]
    if mask.sum() < 5:
        return None, None, int(mask.sum())
    if Z:
        A = np.column_stack([np.ones(mask.sum())] + [np.asarray(z, float)[mask] for z in Z])
        rx = x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
        ry = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
    else:
        rx, ry = x - x.mean(), y - y.mean()
    if np.std(rx) < 1e-9 or np.std(ry) < 1e-9:
        return None, None, int(mask.sum())
    r, p = stats.pearsonr(rx, ry)
    return float(r), float(p), int(mask.sum())


def main():
    # ---- defect (d12_defect.csv): pivot to per-building d4/b1 ----
    defect = defaultdict(dict)
    for r in rd(LEV / "d12_defect.csv"):
        defect[r["bid"]][r["arm"]] = {k: fnum(r[k]) for k in
            ("height_resid", "slope_deg_wmean", "psd_rms", "support_ratio", "k_sup", "m_flo", "n_gs", "n_als", "n_ref")}
        defect[r["bid"]][r["arm"]]["roofType"] = r["roofType"]
    # ---- observability ----
    t7 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in rd(P0 / "W3_failure_diagnosis_building_metrics.csv")}
    t11 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in rd(P0 / "W3_survivor_texture_refine_building_metrics.csv")}
    t9 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in rd(P0 / "W3_failure_surface_cause_building_metrics.csv")}
    # ---- controls (als span/levels) — complexity_survey.csv covers the 93 control set incl the 71 survivors
    cm = {}
    csv_survey = LEV / "complexity_survey.csv"
    if csv_survey.exists():
        for r in rd(csv_survey):
            cm[r["bid"]] = {"als_span": fnum(r.get("als_span_true")) or fnum(r.get("als_span_cj")),
                            "als_levels": fnum(r.get("als_levels_true")) or fnum(r.get("als_levels_cj"))}
    for r in rd(LEV / "complexity_metric.csv"):
        cm.setdefault(r["bid"], {"als_span": fnum(r["als_span_m"]), "als_levels": fnum(r["als_levels"])})

    # build unified per-building table over buildings that have d4 defect
    rows = []
    for bid, d in defect.items():
        if "gs_d4_dense" not in d:
            continue
        d4 = d["gs_d4_dense"]; b1 = d.get("gs_b1_dense", {})
        cov = t7.get(bid, {})
        tex = t11.get(bid) or t9.get(bid) or {}
        # texture: T11 sharp_low_texture_pixel_ratio (survivor) OR T9 1-norm proxy; deficit higher=worse
        tx_lowratio = fnum(tex.get("sharp_low_texture_pixel_ratio"))
        tx_grad_p10 = fnum(tex.get("sharp_gradient_p10")) or fnum(tex.get("near_nadir_texture_gradient_p10"))
        rows.append({
            "bid": bid, "roofType": d4.get("roofType"),
            # defect axes (gs_d4)
            "height": d4["height_resid"], "slope": d4["slope_deg_wmean"], "psd": d4["psd_rms"],
            "support": d4["support_ratio"],
            "b1_height": b1.get("height_resid"), "b1_support": b1.get("support_ratio"),
            # observability
            "view_count": fnum(cov.get("view_count")), "incidence": fnum(cov.get("median_incidence_deg")),
            "occlusion": fnum(cov.get("occlusion_risk_view_fraction")), "dim_density": fnum(cov.get("dim_density_pts_m2")),
            "hole_ratio": fnum(cov.get("dim_hole_ratio")),
            "tex_lowratio": tx_lowratio, "tex_grad_p10": tx_grad_p10,
            # controls
            "area": fnum(cov.get("footprint_area_m2")), "als_span": cm.get(bid, {}).get("als_span"),
            "als_levels": cm.get(bid, {}).get("als_levels"),
            "in_t11": bid in t11, "in_t9": bid in t9,
        })
    print(f"[n] buildings with d4 defect: {len(rows)} (T11-texture {sum(r['in_t11'] for r in rows)}, T9 {sum(r['in_t9'] for r in rows)})")
    col = lambda k: [r[k] for r in rows]
    ctrl = [col("area"), col("als_span"), col("als_levels")]
    out = {"n": len(rows), "A_partial_corr": {}, "C_criteria": {}, "D_logistic": {}}

    # ===== A: each defect axis vs each observability variable (Pearson + partial controlling area/span/levels) =====
    AX = {"height": col("height"), "slope": col("slope"), "psd": col("psd")}
    OBS = {"view_count": col("view_count"), "incidence": col("incidence"), "occlusion": col("occlusion"),
           "dim_density": col("dim_density"), "hole_ratio": col("hole_ratio"),
           "tex_lowratio": col("tex_lowratio"), "tex_grad_p10": col("tex_grad_p10")}
    print("\n=== A: defect-axis vs observability (r_raw / r_partial[ctrl area,span,levels] , p_partial, n) ===")
    for ax, av in AX.items():
        out["A_partial_corr"][ax] = {}
        for ob, ov in OBS.items():
            r0, p0, n0 = partial_corr(av, ov, [])
            rp, pp, n = partial_corr(av, ov, ctrl)
            out["A_partial_corr"][ax][ob] = {"r_raw": r0, "p_raw": p0, "n_raw": n0, "r_partial": rp, "p_partial": pp, "n_partial": n}
            if r0 is not None:
                pstr = f"r_part={rp:+.2f} p={pp:.3f} n={n}" if rp is not None else "r_part=NA"
                print(f"  {ax:7} ~ {ob:13}: r_raw={r0:+.2f} p_raw={p0:.3f} n_raw={n0} | {pstr}")

    # ===== C: B1 life/death =====
    # Criterion 1 (support): paired d4 vs b1 support_ratio (Wilcoxon) + facet-flip McNemar
    pairs = [(r["support"], r["b1_support"]) for r in rows if r["support"] is not None and r["b1_support"] is not None]
    d4s = np.array([a for a, b in pairs]); b1s = np.array([b for a, b in pairs])
    delta = float(np.mean(b1s - d4s))
    try:
        w_stat, w_p = stats.wilcoxon(b1s, d4s)
    except ValueError:
        w_stat, w_p = None, None
    # facet-level McNemar from d12_defect_faces.csv (paired by bid+face)
    faces = defaultdict(dict)
    for r in rd(LEV / "d12_defect_faces.csv"):
        faces[(r["bid"], r["face"])][r["arm"]] = (r["supported"] == "True")
    b = c = 0
    for k, v in faces.items():
        if "gs_d4_dense" in v and "gs_b1_dense" in v:
            if v["gs_d4_dense"] and not v["gs_b1_dense"]: b += 1   # lost support
            if not v["gs_d4_dense"] and v["gs_b1_dense"]: c += 1   # gained support
    mcn_p = stats.binomtest(min(b, c), b + c, 0.5).pvalue if (b + c) > 0 else None
    crit1_pass = (w_p is not None and w_p < 0.05 and delta >= 0.10)
    crit1_fail = (w_p is None or w_p >= 0.05) and delta < 0.05
    out["C_criteria"]["crit1_support"] = {"n_pairs": len(pairs), "delta_support": round(delta, 3),
        "wilcoxon_p": w_p, "mcnemar_lost": b, "mcnemar_gained": c, "mcnemar_p": mcn_p,
        "verdict": "PASS" if crit1_pass else ("FAIL" if crit1_fail else "MIXED")}
    # Criterion 2 (texture): partial corr of B1 height IMPROVEMENT (d4-b1) vs texture, controlling baseline (d4 height)
    imp = [(r["height"] - r["b1_height"]) if (r["height"] is not None and r["b1_height"] is not None) else None for r in rows]
    for txn in ("tex_lowratio", "tex_grad_p10"):
        rp, pp, n = partial_corr(imp, col(txn), [col("height")])
        crit2_pass = (rp is not None and pp < 0.05 and abs(rp) >= 0.30)
        crit2_fail = (rp is not None and abs(rp) < 0.10)
        out["C_criteria"][f"crit2_texture_{txn}"] = {"r_partial": rp, "p": pp, "n": n,
            "verdict": "PASS" if crit2_pass else ("FAIL" if crit2_fail else "MIXED")}
    print("\n=== C: B1 life/death ===")
    print(f"  crit1 support: delta={delta:+.3f} wilcoxon_p={w_p} mcnemar(lost {b}/gained {c}) p={mcn_p} -> {out['C_criteria']['crit1_support']['verdict']}")
    for txn in ("tex_lowratio", "tex_grad_p10"):
        cc = out["C_criteria"][f"crit2_texture_{txn}"]
        print(f"  crit2 texture[{txn}]: r_part={cc['r_partial']} p={cc['p']} n={cc['n']} -> {cc['verdict']}")

    # ===== D: generation logistic (texture/coverage -> GS gen success) over T7 79 set =====
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        # GS gen success per building: chunk eval jsons (eval_d12c_*.json, 71 survivors) + mob-11 eval (8 failures)
        import glob as _glob
        gen = {}
        files = sorted(_glob.glob(str(REPO / "results/tum_transfer/mob/eval_d12c_*.json"))) + \
                [str(REPO / "results/tum_transfer/mob/eval_d4_gssem.json")]
        for fp in files:
            if Path(fp).exists():
                for r in json.load(open(fp)):
                    if r.get("tag") == "orig" and r.get("config") == "gs_d4_dense":
                        bid = str(r["bid"]).replace("DEBY_LOD2_", "")
                        gen[bid] = bool(r.get("roofer_ok") and (r.get("roof_surfaces") or 0) > 0)
        # features = texture(T9/T11) + coverage(T7), label = gen
        X, yv = [], []
        for bid in set(list(t9) + list(t11)):
            cov = t7.get(bid, {}); tex = t11.get(bid) or t9.get(bid) or {}
            tl = fnum(tex.get("sharp_low_texture_pixel_ratio"))
            vc = fnum(cov.get("view_count")); inc = fnum(cov.get("median_incidence_deg")); occ = fnum(cov.get("occlusion_risk_view_fraction"))
            if None in (tl, vc, inc, occ) or bid not in gen:
                continue
            X.append([tl, vc, inc, occ]); yv.append(1 if gen[bid] else 0)
        X = np.array(X); yv = np.array(yv)
        if len(set(yv)) == 2 and len(yv) >= 10:
            lr = LogisticRegression(max_iter=1000).fit(X, yv)
            auc = roc_auc_score(yv, lr.predict_proba(X)[:, 1])
            out["D_logistic"] = {"n": int(len(yv)), "n_success": int(yv.sum()), "n_fail": int((yv == 0).sum()),
                "features": ["tex_lowratio", "view_count", "incidence", "occlusion"],
                "coef": [round(float(c), 3) for c in lr.coef_[0]], "auc": round(float(auc), 3)}
            print(f"\n=== D: generation logistic n={len(yv)} (succ {yv.sum()}/fail {(yv==0).sum()}) AUC={auc:.3f} coef={out['D_logistic']['coef']} ===")
        else:
            out["D_logistic"] = {"note": f"insufficient class balance (n={len(yv)}, pos={int(yv.sum())})"}
            print(f"\n=== D: insufficient (n={len(yv)} pos={int(yv.sum())}) — most/all GS succeeded; see note ===")
    except Exception as e:
        out["D_logistic"] = {"error": str(e)}

    (LEV / "d12_analysis.json").write_text(json.dumps(out, indent=2))
    # scatter: each axis vs the strongest texture/coverage (height vs tex_lowratio, height vs occlusion)
    for ax in ("height", "slope", "psd"):
        fig, axs = plt.subplots(1, 2, figsize=(11, 4.4))
        for j, ob in enumerate(("tex_lowratio", "occlusion")):
            xv = np.array(col(ob), float); yv2 = np.array(col(ax), float)
            mk = np.isfinite(xv) & np.isfinite(yv2)
            axs[j].scatter(xv[mk], yv2[mk], s=22, c=["red" if r["in_t9"] else "tab:blue" for r, m in zip(rows, mk) if m])
            axs[j].set_xlabel(ob); axs[j].set_ylabel(f"{ax} defect (gs_d4)")
            rr = out["A_partial_corr"][ax][ob]
            axs[j].set_title(f"{ax} ~ {ob}  r_part={rr['r_partial']} p={rr['p_partial']} n={rr['n_partial']}", fontsize=8)
            axs[j].grid(alpha=0.3)
        fig.suptitle(f"D12 A: {ax} defect vs observability (red=T9 textureless-failure)", fontsize=10)
        fig.tight_layout(); fig.savefig(FIG / f"A_{ax}.png", dpi=105); plt.close(fig)
    print(f"\n[done] -> {LEV}/d12_analysis.json ; figs {FIG}/")


if __name__ == "__main__":
    main()
