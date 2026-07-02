#!/usr/bin/env python3
"""v3 QA cross-check [6]: compare v3 (unified, 199) vs v2 (population_aux.csv, reused-subset) on the
OVERLAPPING columns (view counts, incidence, lowtex, grad, occlusion). Reports n, Pearson r, Spearman
rho, median bias (v3-v2), and the largest mismatches. Also prints v3 column coverage. Observe only.
Pure-stdlib (runs in tools:t0); no reconstruction.
"""
import csv, math
from pathlib import Path
REPO = Path("/workspace/JointBuildGS")
V3 = REPO / "results/tum_transfer/mob/overseg_lever/population_aux_v3.csv"
V2 = REPO / "results/tum_transfer/mob/overseg_lever/population_aux.csv"


def load(p):
    return {r["building_id"]: r for r in csv.DictReader(open(p))}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pearson(xs, ys):
    n = len(xs)
    if n < 3: return None
    mx, my = sum(xs)/n, sum(ys)/n
    sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
    if sx == 0 or sy == 0: return None
    return sum((x-mx)*(y-my) for x, y in zip(xs, ys))/(sx*sy)


def spearman(xs, ys):
    def rank(a):
        idx = sorted(range(len(a)), key=lambda i: a[i]); r = [0]*len(a)
        i = 0
        while i < len(a):
            j = i
            while j+1 < len(a) and a[idx[j+1]] == a[idx[i]]: j += 1
            avg = (i+j)/2.0
            for k in range(i, j+1): r[idx[k]] = avg
            i = j+1
        return r
    return pearson(rank(xs), rank(ys))


def main():
    v3, v2 = load(V3), load(V2)
    # (v3 col, v2 col, label, v2 source note)
    pairs = [
        ("n_views_total", "n_views_total", "views_total", "v2=T7 view_count (79)"),
        ("n_views_nadir", "n_views_nadir", "views_nadir", "v2=T11/W4c near_nadir (125)"),
        ("n_views_oblique", "n_views_oblique", "views_oblique", "v2=T11/W4c oblique (125)"),
        ("median_incidence_deg", "median_incidence_deg", "incidence_deg", "v2=T7/T11/W4c median incid (87)"),
        ("roof_lowtex_frac", "roof_lowtex_frac", "lowtex_frac", "v2=T11 sharp_low_texture_pixel_ratio (70)"),
        ("roof_grad_p10", "roof_grad_p10", "grad_p10", "v2=T9/T11/W4c gradient_p10 (86)"),
        ("occlusion_frac_approx", "occlusion_frac_approx", "occlusion", "v2=T7 occlusion_risk_view_fraction (79)"),
    ]
    print(f"v3={len(v3)} rows  v2={len(v2)} rows\n")
    print("=== [6] QA cross-check (overlapping buildings with both non-blank) ===")
    for c3, c2, lab, note in pairs:
        xs, ys, bids = [], [], []
        for b, r3 in v3.items():
            r2 = v2.get(b)
            if not r2: continue
            a, c = num(r3.get(c3)), num(r2.get(c2))
            if a is None or c is None: continue
            xs.append(a); ys.append(c); bids.append(b)
        if len(xs) < 3:
            print(f"\n[{lab}] n={len(xs)} (too few) — {note}"); continue
        r = pearson(xs, ys); rho = spearman(xs, ys)
        diffs = [a-c for a, c in zip(xs, ys)]
        med_bias = sorted(diffs)[len(diffs)//2]
        mean_v3 = sum(xs)/len(xs); mean_v2 = sum(ys)/len(ys)
        print(f"\n[{lab}] n={len(xs)}  Pearson r={r:.3f}  Spearman rho={rho:.3f}"
              f"  median(v3-v2)={med_bias:+.3f}  mean v3={mean_v3:.3f} v2={mean_v2:.3f}")
        print(f"   {note}")
        order = sorted(range(len(xs)), key=lambda i: -abs(diffs[i]))[:5]
        print("   top mismatches (bid: v3 vs v2, Δ):")
        for i in order:
            print(f"     {bids[i]}: {xs[i]:.3f} vs {ys[i]:.3f}  (Δ{diffs[i]:+.3f})")
    # v3 coverage
    cols = list(next(iter(v3.values())).keys())[1:]
    print("\n=== v3 column coverage (non-blank / 199) ===")
    for k in cols:
        nb = sum(1 for r in v3.values() if r.get(k) not in ("", None))
        print(f"  {k:26} {nb}/{len(v3)}")


if __name__ == "__main__":
    main()
