#!/usr/bin/env python3
"""P2 v6 density-match figure — Roofer facet vs roof point density (log x), per GS arm, with the
ref/raw facet line and the flat control. Shows over-seg survives density-matching (waviness-driven).
p0-tools matplotlib Agg. Out: docs/figs/tum_transfer/v6_density_match.png. Observation only.
"""
import csv
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/workspace/JointBuildGS"
PACK = f"{REPO}/results/tum_transfer/mob/analysis_pack_v6"


def main():
    series = defaultdict(list)   # (bid,arm) -> [(density, facet, nDisp)]
    for r in csv.DictReader(open(f"{PACK}/density_match.csv")):
        try:
            fac = int(r["roofer_facet"])
        except (ValueError, TypeError):
            continue
        series[(r["building"], r["arm"])].append(
            (float(r["density_pps_m2"]), fac, r["normal_disp_deg"]))

    fig, ax = plt.subplots(figsize=(8, 5.2))
    style = {("4906972", "gs_seed_dense"): ("o-", "C3"), ("4906972", "gs_seed_acmp"): ("s-", "C1"),
             ("42364663", "gs_seed_dense"): ("o--", "C0"), ("42364663", "gs_seed_acmp"): ("s--", "C9")}
    for key, pts in series.items():
        pts.sort()
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        st, col = style.get(key, ("o-", "gray"))
        bid, arm = key
        nd = pts[-1][2]
        ax.plot(xs, ys, st, color=col, label=f"{bid} {arm.replace('gs_seed_','GS_')} (nDisp~{nd})")
    ax.axhline(3, color="green", ls=":", lw=1.5, label="ref/raw/LiDAR facet = 3 (4906972) / 1 (42364663)")
    ax.set_xscale("log")
    ax.set_xlabel("roof point density (pts/m^2, log)  — LiDAR ~16-21  /  raw_dense ~400-2300  /  GS orig ~1800-5700")
    ax.set_ylabel("Roofer RoofSurface facet count")
    ax.set_title("v6 density-match: facet vs density. 4906972 stays 13-19 across 2 decades of density\n"
                 "(waviness-driven), control 42364663 stays 1-3. Observation only.", fontsize=10)
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    out = Path(f"{REPO}/docs/figs/tum_transfer/v6_density_match.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"[done] -> {out}")


if __name__ == "__main__":
    main()
