#!/usr/bin/env python3
"""P2 complexity-survey PART 1 — dz-ROBUST faithfulness metric (no retrain, observe-only).

Fixes the per-arm dz confound the B1 adversarial verification exposed: overseg_b1_faithfulness's
fixed_dz = max(0, median(ALS)-median(GS)) is (a) per-arm (re-centers each arm separately) and
(b) clamped to >=0 (so an arm whose GS sits ABOVE ALS — e.g. gs_d4_dense 42364659 ~7m high — is
pinned at a huge residual it could remove with a negative offset). That manufactured the bogus
"42364659 4.58->0.95 (4.8x)" headline.

This metric is dz-ROBUST and clamp-free:
  - resid_abs_mean(dz) is swept over a wide dz range (TWO-sided, no clamp).
  - BEST-FIT resid = min over the sweep (each arm at its own optimal vertical registration) = the
    dz-invariant "how faithful CAN these facets be to the real ALS levels".
  - SHARED-dz resid = both arms scored at one JOINT dz* = argmin_dz [resid_d4(dz)+resid_b1(dz)]
    (single offset for all compared arms) = isolates the L_mvc effect from global re-registration.
  - DOMINANCE verdict: arm A is more faithful than B only if resid_A(dz) <= resid_B(dz) across the
    whole sweep (curves do not cross); crossing => UNDECIDABLE (the honest 4906969 outcome).
  - Continuous resid_abs (->0) is the PRIMARY metric; the 0.5m binary support k/m is secondary.

Reuses (read-only): raw ALS (mob_eval/raw_lidar), GS Roofer solids (gssem read-out on disk, BOTH arms
must be gssem — run gssem-requal first if smrf overwrote), LoD2 ref. NO retrain / NO Roofer re-run.
Output: results/.../overseg_lever/complexity_metric.csv + docs/figs/W_complexity/<bid>_dzcurve.png.
Run (p0-tools): docker run --rm --user $(id -u):$(id -g) -v $PWD:/workspace/JointBuildGS -w /workspace/JointBuildGS \
                  jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/complexity_metric.py
"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from d6_shape_audit import footprint_paths, read_cloud, roof_envelope, gml_building
from overseg_analysis import parse_solid_roof
from overseg_faithfulness import face_support, z_levels, step_aware_levels, GEOID, MIN_ALS

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
FIG = REPO / "docs/figs/W_complexity"
# all 11 mob GS buildings (baselines.json); kind from observation/ref where known
MOB = ["42364609", "42364659", "42364663", "4907182", "4907510",
       "4908050", "4908166", "4908176", "4906969", "4908023", "4906972"]
DZ_LO, DZ_HI, DZ_STEP = -10.0, 8.0, 0.25
BANDS = [0.5, 1.0, 1.5]


def resid_curve(roof_faces, V, als, dzs):
    """resid_abs_mean(dz) over the sweep; returns (means[list|None], frac1[list]) aligned to dzs."""
    means, frac1 = [], []
    for dz in dzs:
        sup = face_support(roof_faces, V, als, dz=float(dz))
        ra = [s["resid_abs"] for s in sup if s["resid_abs"] is not None]
        if ra:
            means.append(float(np.mean(ra)))
            frac1.append(sum(1 for r in ra if r < 1.0) / len(ra))
        else:
            means.append(None); frac1.append(None)
    return means, frac1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["gs_d4_dense", "gs_b1_dense"])
    ap.add_argument("--bids", nargs="*", default=MOB)
    args = ap.parse_args()
    LEV.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    dzs = np.round(np.arange(DZ_LO, DZ_HI + 1e-9, DZ_STEP), 2)
    rows = []
    for bid in args.bids:
        paths = footprint_paths(bid)
        als = read_cloud("raw_lidar", bid, paths)
        if als is None or len(als) < MIN_ALS:
            print(f"  [skip] {bid}: no/short ALS"); continue
        als_env = roof_envelope(als)
        rt, roof, wall = gml_building(bid)
        lv_als = z_levels(als_env[:, 2]); n_lv_als = len(lv_als)
        als_span = float(als_env[:, 2].max() - als_env[:, 2].min())
        # per-arm curves
        curves = {}
        for arm in args.arms:
            pr = parse_solid_roof(arm, bid)
            if pr is None:
                continue
            rf, V = pr
            means, frac1 = resid_curve(rf, V, als, dzs)
            valid = [(d, m, f) for d, m, f in zip(dzs, means, frac1) if m is not None]
            if not valid:
                continue
            mvals = np.array([m for _, m, _ in valid]); dvals = np.array([d for d, _, _ in valid])
            i_min = int(np.argmin(mvals))
            curves[arm] = {"rf": rf, "V": V, "dzs": dvals, "means": mvals,
                           "frac1": np.array([f for _, _, f in valid]),
                           "min_resid": float(mvals[i_min]), "argmin_dz": float(dvals[i_min]),
                           "n_faces": len(rf)}
        if len(curves) < 1:
            print(f"  [skip] {bid}: no arm solids"); continue
        # joint dz (shared offset minimizing sum of arms' resid on the common dz grid)
        common = sorted(set.intersection(*[set(np.round(c["dzs"], 2)) for c in curves.values()])) if len(curves) > 1 else list(curves.values())[0]["dzs"]
        joint_dz, shared = None, {}
        if len(curves) >= 2 and common:
            def at(c, dz):
                idx = int(np.argmin(np.abs(c["dzs"] - dz))); return c["means"][idx], c["frac1"][idx]
            sums = [(dz, sum(at(c, dz)[0] for c in curves.values())) for dz in common]
            joint_dz = float(min(sums, key=lambda t: t[1])[0])
            for arm, c in curves.items():
                m, f = at(c, joint_dz); shared[arm] = (float(m), float(f))
        # dominance (2-arm only): does arm[1] (B1) <= arm[0] (D4) across the whole common sweep?
        dominance = ""
        if len(curves) == 2 and common:
            a0, a1 = args.arms[0], args.arms[1]
            if a0 in curves and a1 in curves:
                def vec(c): return np.array([c["means"][int(np.argmin(np.abs(c["dzs"] - dz)))] for dz in common])
                v0, v1 = vec(curves[a0]), vec(curves[a1])
                if np.all(v1 <= v0 + 1e-6): dominance = f"{a1}_dominates"
                elif np.all(v0 <= v1 + 1e-6): dominance = f"{a0}_dominates"
                else: dominance = "cross_undecidable"
        # rows
        for arm, c in curves.items():
            lv_gs, _ = step_aware_levels(c["rf"], c["V"])
            sh = shared.get(arm, (None, None))
            rows.append({
                "bid": bid, "arm": arm, "roofType": rt, "n_faces": c["n_faces"],
                "als_levels": n_lv_als, "als_span_m": round(als_span, 2),
                "gs_stepaware_levels": len(lv_gs),
                "bestfit_resid": round(c["min_resid"], 3), "bestfit_dz": round(c["argmin_dz"], 2),
                "joint_dz": round(joint_dz, 2) if joint_dz is not None else None,
                "shared_resid": round(sh[0], 3) if sh[0] is not None else None,
                "shared_frac1": round(sh[1], 3) if sh[1] is not None else None,
                "dominance": dominance,
            })
        # plot
        fig, ax = plt.subplots(figsize=(7, 4.6))
        for arm, c in curves.items():
            ax.plot(c["dzs"], c["means"], label=f"{arm} (best {c['min_resid']:.2f}@dz{c['argmin_dz']:.1f})", lw=1.8)
            ax.scatter([c["argmin_dz"]], [c["min_resid"]], s=30, zorder=5)
        if joint_dz is not None:
            ax.axvline(joint_dz, color="gray", ls="--", lw=1, label=f"joint dz={joint_dz:.2f}")
        ax.set_xlabel("dz (m, GS↑ALS offset; no clamp)"); ax.set_ylabel("resid_abs_mean (m)")
        ax.set_title(f"{bid}  roofType={rt}  ALS levels={n_lv_als} span={als_span:.1f}m  | {dominance}", fontsize=9)
        ax.legend(fontsize=7); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(FIG / f"{bid}_dzcurve.png", dpi=105); plt.close(fig)
        line = f"{bid} rt={rt} ALSlv={n_lv_als}(span {als_span:.1f}m) | "
        for arm in args.arms:
            if arm in curves:
                c = curves[arm]; sh = shared.get(arm, (None, None))
                line += f"{arm}: best={c['min_resid']:.2f}@{c['argmin_dz']:.1f} shared={sh[0] if sh[0] is None else round(sh[0],2)} | "
        print(line + f"=> {dominance}")
    if rows:
        with open(LEV / "complexity_metric.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        print(f"\n[done] -> {LEV}/complexity_metric.csv ; curves {FIG}/")


if __name__ == "__main__":
    main()
