#!/usr/bin/env python3
"""P2 Phase B / B1 eval — did the self-supervised multi-view consistency term (L_mvc) pull GS's
FLOATING roof facets toward their real ALS layer heights, WITHOUT breaking the simple controls?

Reuses the Phase-A overseg-faithfulness machinery (face_support / step_aware_levels / z_levels) but
compares TWO arms (baseline gs_d4_dense vs B1 gs_b1_dense) against the SAME raw ALS, and adds the
fairness/sensitivity fixes the Step-0 map flagged:
  (1) --arms comparison (baseline first, B1 second), shared raw-ALS reference per building.
  (2) FIXED-dz protocol: the headline alignment is dz0 = median(ALS_env z) - median(GS_env z) — a
      single deterministic envelope offset computed by the SAME formula for both arms (removes the
      ~1.7m global GS<ALS bias per arm WITHOUT a support-maximising search). The favorable search dz
      (Phase-A metric) is also reported for continuity, but the A/B headline uses fixed dz so the
      k/m delta reflects L_mvc, not a per-arm dz search.
  (3) CONTINUOUS metric: per-facet median|resid| (resid_abs) mean/median + bands <0.5 / <1.0 / <1.5m,
      because the 0.5m binary "supported" cannot see a ±1~2.5m facet being PULLED toward (not onto) its
      level — exactly the sub-defect L_mvc targets.

Qualitative: per building, a [baseline GS height-colored | B1 GS height-colored | raw ALS] panel on a
shared height scale; red edge = ALS-unsupported (fixed-dz). NO retrain / NO reconstruction here — this
reads the trained arms' Roofer Solids. Observation only; verdict = 김휘영. EPSG:25832.

Run (p0-tools container, after run_b1.sh produced mob_eval/gs_b1_*):
  python3 phases/p2-gsjso/scripts/overseg_b1_faithfulness.py --arms gs_d4_dense gs_b1_dense
Out: results/.../overseg_lever/b1_faithfulness.csv + b1_faces_<bid>_<arm>.csv + docs/figs/W_phaseB/<bid>.png
"""
import argparse, csv, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.path import Path as MplPath

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from d6_shape_audit import footprint_paths, read_cloud, roof_envelope, gml_building
from assembly_fidelity import fit_plane
from overseg_analysis import parse_solid_roof
# reuse the Phase-A metric definitions verbatim (single source of truth)
from overseg_faithfulness import face_support, step_aware_levels, z_levels, TOL, MIN_ALS, GEOID

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
FIG = REPO / "docs/figs/W_phaseB"
# canonical + composite (test) and the two simple controls the task names (guardrail)
BLD = [("4906969", "단차평 stepped-flat (canonical)"), ("42364659", "단차 stepped (composite)"),
       ("4907510", "경사복합 sloped-composite"), ("4906972", "단순 박공 gable (control)"),
       ("42364663", "단순 ridge (control)")]
BANDS = [0.5, 1.0, 1.5]   # resid_abs bands (m) for the continuous metric


def fixed_dz(als_env, gs_env):
    """Deterministic envelope offset — same formula for every arm (no favorable search)."""
    if als_env is None or gs_env is None:
        return 0.0
    return float(np.median(als_env[:, 2]) - np.median(gs_env[:, 2]))


def favorable_dz(roof_faces, V, als, dz0):
    """Phase-A metric: dz>=0 in [dz0-3, dz0+3] that MAXIMISES supported faces (reported for continuity)."""
    cand = [z for z in (round(dz0 + d, 2) for d in np.arange(-3, 3.01, 0.25)) if z >= 0]
    if not cand:
        return max(0.0, dz0)
    def score(z):
        ss = face_support(roof_faces, V, als, z)
        k = sum(1 for s in ss if s["supported"])
        tot = sum(s["resid_abs"] for s in ss if s["resid_abs"] is not None)
        return (-k, tot)
    return min(cand, key=score)


def resid_stats(sup):
    """continuous facet-residual summary from a face_support() result."""
    ra = [s["resid_abs"] for s in sup if s["resid_abs"] is not None]
    n = len(ra)
    out = {"n_faces": len(sup), "n_judged": n,
           "resid_abs_mean": round(float(np.mean(ra)), 3) if n else None,
           "resid_abs_med": round(float(np.median(ra)), 3) if n else None}
    for b in BANDS:
        out[f"frac_lt_{b}"] = round(sum(1 for r in ra if r < b) / n, 3) if n else None
    return out


def arm_eval(arm, bid, paths, als, als_env):
    """Evaluate one arm for one building. Returns dict + (roof_faces, V, sup_fixed) for plotting, or None."""
    pr = parse_solid_roof(arm, bid)
    if pr is None:
        return None
    roof_faces, V = pr
    gs_cloud = read_cloud(arm, bid, paths)
    gs_env = roof_envelope(gs_cloud) if gs_cloud is not None and len(gs_cloud) else None
    dz0 = fixed_dz(als_env, gs_env)
    dz_fav = favorable_dz(roof_faces, V, als, dz0) if als is not None else 0.0
    sup_fix = face_support(roof_faces, V, als, dz=max(0.0, dz0))
    sup_fav = face_support(roof_faces, V, als, dz=dz_fav)
    k_fix = sum(1 for s in sup_fix if s["supported"]); m_fix = len(sup_fix) - k_fix
    k_fav = sum(1 for s in sup_fav if s["supported"]); m_fav = len(sup_fav) - k_fav
    lv_gs, _ = step_aware_levels(roof_faces, V)
    rs = resid_stats(sup_fix)
    row = {"bid": bid, "arm": arm, "GS_faces": len(roof_faces),
           "dz_fixed": round(max(0.0, dz0), 2), "dz_fav": round(dz_fav, 2),
           "k_fixed": k_fix, "m_fixed": m_fix, "k_fav": k_fav, "m_fav": m_fav,
           "GS_levels_stepaware": len(lv_gs),
           "GS_levels_z_ortho": sorted(round(x - GEOID, 1) for x in lv_gs),
           **{kk: rs[kk] for kk in ("resid_abs_mean", "resid_abs_med",
                                    *[f"frac_lt_{b}" for b in BANDS])}}
    return {"row": row, "roof_faces": roof_faces, "V": V, "sup": sup_fix, "lv_gs": lv_gs}


def compare_panel(bid, kind, arm_results, als, als_env, lv_als, lv_ref):
    """[arm0 GS | arm1 GS | ... | raw ALS] height-colored, shared clim. red edge = ALS-unsupported (fixed dz)."""
    FIG.mkdir(parents=True, exist_ok=True)
    arms = list(arm_results.keys())
    czs = [arm_results[a]["V"][r][:, 2] for a in arms for r in arm_results[a]["roof_faces"]]
    if als_env is not None and len(als_env):
        czs.append(als_env[:, 2])
    cz_all = np.concatenate(czs) if czs else np.array([0.0, 1.0])
    vmin, vmax = float(cz_all.min()), float(cz_all.max())
    ncol = len(arms) + 1
    fig = plt.figure(figsize=(5.0 * ncol, 5.2))
    sm = cm.ScalarMappable(cmap="viridis"); sm.set_clim(vmin, vmax)
    for ci, a in enumerate(arms):
        ax = fig.add_subplot(1, ncol, ci + 1)
        rf, V, sup = arm_results[a]["roof_faces"], arm_results[a]["V"], arm_results[a]["sup"]
        for i, r in enumerate(rf):
            poly = V[r][:, :2]; zc = float(V[r][:, 2].mean())
            ax.fill(poly[:, 0], poly[:, 1], color=sm.to_rgba(zc), alpha=0.85,
                    edgecolor=("k" if sup[i]["supported"] else "red"),
                    lw=(0.4 if sup[i]["supported"] else 1.4))
        k = sum(1 for s in sup if s["supported"]); m = len(sup) - k
        ra = [s["resid_abs"] for s in sup if s["resid_abs"] is not None]
        ramean = np.mean(ra) if ra else float("nan")
        ax.set_aspect("equal"); ax.set_axis_off()
        ax.set_title(f"{a}\n{len(rf)} faces  k={k}/m={m}  resid_abs̄={ramean:.2f}m\n(red=ALS-unsupported, fixed dz)",
                     fontsize=8)
    axA = fig.add_subplot(1, ncol, ncol)
    if als is not None and len(als):
        E = roof_envelope(als)
        axA.scatter(E[:, 0], E[:, 1], c=E[:, 2], cmap="viridis", s=6, vmin=vmin, vmax=vmax)
    axA.set_aspect("equal"); axA.set_axis_off()
    axA.set_title(f"raw ALS roof pts (n={0 if als is None else len(als)})\nALS levels={len(lv_als)} ref={len(lv_ref)}",
                  fontsize=8)
    fig.suptitle(f"B1 faithfulness {bid} — {kind}   [baseline → B1 → ALS]", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fp = FIG / f"{bid}.png"; fig.savefig(fp, dpi=105); plt.close(fig); return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["gs_d4_dense", "gs_b1_dense"],
                    help="arms to compare, baseline first (read from mob_eval/<arm>/)")
    ap.add_argument("--bids", nargs="*", default=None, help="override building list")
    args = ap.parse_args()
    bld = [(b, "") for b in args.bids] if args.bids else BLD
    LEV.mkdir(parents=True, exist_ok=True)
    rows, face_rows = [], []
    for bid, kind in bld:
        paths = footprint_paths(bid)
        als = read_cloud("raw_lidar", bid, paths)
        als_env = roof_envelope(als) if als is not None and len(als) else None
        rt, roof, wall = gml_building(bid)
        lv_als = z_levels(als_env[:, 2] if als_env is not None else None)
        lv_ref = sorted({round(float(r[:, 2].mean()), 1) for r in roof}) if roof else []
        arm_results = {}
        for arm in args.arms:
            res = arm_eval(arm, bid, paths, als, als_env)
            if res is None:
                print(f"  [skip] {bid} arm={arm} (no Roofer Solid found)")
                continue
            arm_results[arm] = res
            for i, s in enumerate(res["sup"]):
                face_rows.append({"bid": bid, "arm": arm, "face": i,
                                  "face_z_ortho": round(float(res["V"][res["roof_faces"][i]][:, 2].mean()) - GEOID, 2),
                                  "n_als": s["n_als"], "resid_med": s["resid_med"],
                                  "resid_abs": s["resid_abs"], "supported": s["supported"]})
        # SHARED-dz control (fairness fix flagged by adversarial verification): the per-arm fixed_dz
        # re-centers each arm against ALS, so a per-facet "gain" can be a bulk vertical re-registration.
        # Score every arm at ONE shared offset = the BASELINE arm's (args.arms[0]) dz_fixed, so the
        # L_mvc effect is isolated from global re-centering. Reported alongside the per-arm numbers.
        if arm_results:
            base = next((a for a in args.arms if a in arm_results), None)
            shared_dz = arm_results[base]["row"]["dz_fixed"] if base else 0.0
            for arm, res in arm_results.items():
                sup_sh = face_support(res["roof_faces"], res["V"], als, dz=shared_dz)
                rs = resid_stats(sup_sh)
                k_sh = sum(1 for s in sup_sh if s["supported"])
                res["row"]["shared_dz"] = round(shared_dz, 2)
                res["row"]["k_shared"] = k_sh
                res["row"]["resid_abs_mean_shared"] = rs["resid_abs_mean"]
                res["row"]["frac_lt_1.0_shared"] = rs["frac_lt_1.0"]
                rows.append(res["row"])
        if arm_results:
            fp = compare_panel(bid, kind, arm_results, als, als_env, lv_als, lv_ref)
            line = f"{bid} {kind:30}"
            for arm in args.arms:
                if arm in arm_results:
                    r = arm_results[arm]["row"]
                    line += (f" | {arm}: {r['GS_faces']}f k={r['k_fixed']} "
                             f"resid̄(own dz={r['dz_fixed']})={r['resid_abs_mean']} "
                             f"resid̄(shared {r.get('shared_dz')})={r.get('resid_abs_mean_shared')} <1.0sh={r.get('frac_lt_1.0_shared')}")
            print(line + f" -> {fp.name}")
    if rows:
        keys = list(rows[0].keys())
        with open(LEV / "b1_faithfulness.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
        with open(LEV / "b1_faithfulness_faces.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(face_rows[0].keys())); w.writeheader(); w.writerows(face_rows)
        print(f"\n[done] -> {LEV}/b1_faithfulness.csv (+ _faces.csv) ; figs {FIG}/")
    else:
        print("[warn] no arm produced any building — check that mob_eval/<arm>/ artifacts exist.")


if __name__ == "__main__":
    main()
