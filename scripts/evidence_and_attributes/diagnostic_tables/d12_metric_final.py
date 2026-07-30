#!/usr/bin/env python3
"""D12 metric FINALIZATION (no retrain, recompute over the existing 78-set Roofer Solids + ALS).
Refines the 3-axis defect per the D12 caveats:
  HEIGHT  : COMMON dz (single joint offset across the compared arms d4+b1, NOT per-arm) -> relative
            residual; PLUS absolute height = residual at dz=0 with |best_dz| reported as the global bias.
            (Step0: if a ground/footprint-Z anchor is available use it; else absolute fallback + issues.md.)
  SLOPE   : facet support-GATED (>=MIN_ALS pts AND XY-spread>=1m) ALS-point-WEIGHTED normal angle (already
            in d12_defect.csv slope_deg_wmean; reused) so Roofer slivers / sparse ALS don't dominate.
  HORIZ   : facet-to-facet MATCH RATE reported alongside (matched/unmatched from d12_defect.csv).
Then recompute: textureless(8) vs survivor(71) height, complexity(als_span/levels)-defect corr, B1 vs D4.
Reads d12_defect.csv (slope/horiz/n_als) + Roofer Solids + ALS. NO retrain. Observe only.
Run (p0-tools): python3 scripts/evidence_and_attributes/diagnostic_tables/d12_metric_final.py [--targets-file F]
Out: results/.../overseg_lever/d12_metric_final.csv (+ prints A summary for the report).
"""
import argparse, csv, sys
from pathlib import Path
from collections import defaultdict
import numpy as np
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.geometry_fidelity.d6_shape_audit import footprint_paths, read_cloud
from scripts.evidence_and_attributes.geometry_fidelity.overseg_analysis import parse_solid_roof
from scripts.evidence_and_attributes.geometry_fidelity.overseg_faithfulness import face_support, MIN_ALS

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
DZ = np.round(np.arange(-10.0, 8.01, 0.25), 2)
ISSUES = REPO / "phases/p2-gsjso/docs/issues.md"
MOB_FAIL = {"42364609","42364659","42364663","4907182","4907510","4908050","4908166","4908176"}


def log_issue(msg):
    with open(ISSUES, "a") as f:
        f.write(f"- [d12-metric-final] {msg}\n")


def resid_at(roof_faces, V, als, dz):
    sup = face_support(roof_faces, V, als, dz=float(dz))
    ra = [s["resid_abs"] for s in sup if s["resid_abs"] is not None]
    return (float(np.mean(ra)) if ra else None), sup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets-file", default=None)
    ap.add_argument("--arms", nargs="+", default=["gs_d4_dense", "gs_b1_dense"])
    args = ap.parse_args()
    bids = Path(args.targets_file).read_text().split() if args.targets_file else \
        sorted({r["bid"] for r in csv.DictReader(open(LEV / "d12_defect.csv"))})
    # reuse slope/horiz from d12_defect.csv (already support-gated / match-rate)
    dd = defaultdict(dict)
    for r in csv.DictReader(open(LEV / "d12_defect.csv")):
        dd[r["bid"]][r["arm"]] = r
    rows = []
    for bid in bids:
        paths = footprint_paths(bid)
        als = read_cloud("raw_lidar", bid, paths)
        if als is None or len(als) < MIN_ALS:
            log_issue(f"{bid}: no/short ALS -> skip metric-final"); continue
        # per-arm dz sweep curves
        curves, V_of, rf_of = {}, {}, {}
        for arm in args.arms:
            pr = parse_solid_roof(arm, bid)
            if pr is None:
                continue
            rf, V = pr; rf_of[arm] = rf; V_of[arm] = V
            curves[arm] = np.array([resid_at(rf, V, als, dz)[0] if resid_at(rf, V, als, dz)[0] is not None else np.inf for dz in DZ])
        if not curves:
            continue
        # COMMON dz = joint argmin over arms (single offset). absolute = dz=0.
        joint = np.zeros(len(DZ))
        for arm in curves:
            joint = joint + np.where(np.isfinite(curves[arm]), curves[arm], np.nan)
        common_dz = float(DZ[int(np.nanargmin(joint))]) if np.any(np.isfinite(joint)) else 0.0
        i0 = int(np.argmin(np.abs(DZ - 0.0)))
        for arm in curves:
            ic = int(np.argmin(np.abs(DZ - common_dz)))
            h_common = curves[arm][ic] if np.isfinite(curves[arm][ic]) else None
            h_abs = curves[arm][i0] if np.isfinite(curves[arm][i0]) else None
            best_dz = float(DZ[int(np.argmin(curves[arm]))])
            sup = resid_at(rf_of[arm], V_of[arm], als, common_dz)[1]
            k = sum(1 for s in sup if s["supported"]); m = len(sup) - k
            d = dd.get(bid, {}).get(arm, {})
            rows.append({"bid": bid, "arm": arm,
                "height_common": round(h_common, 3) if h_common is not None else None,
                "height_abs": round(h_abs, 3) if h_abs is not None else None,
                "global_bias_dz": round(best_dz, 2), "common_dz": round(common_dz, 2),
                "k_sup": k, "m_flo": m, "support_ratio": round(k / max(1, k + m), 3),
                "slope_deg_wmean": d.get("slope_deg_wmean"), "psd_rms": d.get("psd_rms"),
                "horiz_matched": d.get("horiz_matched"), "horiz_unmatched": d.get("horiz_unmatched"),
                "n_als": d.get("n_als"), "roofType": d.get("roofType")})
    keys = list(rows[0].keys())
    with open(LEV / "d12_metric_final.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

    # ---- analysis summary (printed for the report) ----
    d4 = {r["bid"]: r for r in rows if r["arm"] == "gs_d4_dense"}
    b1 = {r["bid"]: r for r in rows if r["arm"] == "gs_b1_dense"}
    def med(ids, k, src=d4):
        v = [float(src[b][k]) for b in ids if b in src and src[b].get(k) not in (None, "", "None")]
        return round(float(np.median(v)), 2) if v else None
    fail = [b for b in d4 if b in MOB_FAIL]; surv = [b for b in d4 if b not in MOB_FAIL]
    print("=== D12 metric-final (common-dz + absolute) ===")
    print(f"rows={len(rows)} | d4 bldgs={len(d4)} b1={len(b1)}")
    print(f"[textureless-failure {len(fail)}] height_common={med(fail,'height_common')} height_abs={med(fail,'height_abs')} slope={med(fail,'slope_deg_wmean')} support={med(fail,'support_ratio')}")
    print(f"[survivor {len(surv)}]            height_common={med(surv,'height_common')} height_abs={med(surv,'height_abs')} slope={med(surv,'slope_deg_wmean')} support={med(surv,'support_ratio')}")
    # B1 vs D4 (common-dz height + support), paired
    pairs_h = [(float(d4[b]["height_common"]), float(b1[b]["height_common"])) for b in d4 if b in b1 and d4[b]["height_common"] is not None and b1[b]["height_common"] is not None]
    pairs_s = [(float(d4[b]["support_ratio"]), float(b1[b]["support_ratio"])) for b in d4 if b in b1]
    if pairs_h:
        dh = np.median([b - a for a, b in pairs_h]); ds = np.mean([b - a for a, b in pairs_s])
        print(f"[B1 vs D4 common-dz, n={len(pairs_h)}] median dHeight(b1-d4)={dh:+.3f} | mean dSupport={ds:+.3f}")
    # horiz match rate
    mr = [int(d4[b]["horiz_matched"]) / max(1, int(d4[b]["horiz_matched"]) + int(d4[b]["horiz_unmatched"]))
          for b in d4 if d4[b].get("horiz_matched") not in (None, "", "None")]
    print(f"[horiz match-rate] median={round(float(np.median(mr)),2) if mr else None} (n={len(mr)}) — low = facet-to-facet matching mostly fails (GS over-seg vs ALS)")
    print(f"[done] -> {LEV}/d12_metric_final.csv")


if __name__ == "__main__":
    main()
