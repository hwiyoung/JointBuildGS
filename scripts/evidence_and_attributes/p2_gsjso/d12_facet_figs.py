#!/usr/bin/env python3
"""D12 B (qualitative) — within-building per-facet DEFECT panels for facet-rich buildings.
Per building (gs_d4_dense): [GS facets by height-resid | GS facets by slope-deg | raw ALS pts] — shows
whether the defect VARIES facet-to-facet within a building (some facets float/tilt while others sit).
Reads d12_defect_faces.csv (per-facet resid_abs/slope_deg/supported) + parse_solid_roof geometry + ALS.
Runs in p0-tools. NO retrain. Observe only.
Out: docs/figs/W_D12/facet_<bid>.png
"""
import csv, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from d6_shape_audit import footprint_paths, read_cloud, roof_envelope
from overseg_analysis import parse_solid_roof

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
FIG = REPO / "docs/figs/W_D12"; FIG.mkdir(parents=True, exist_ok=True)


def main():
    bids = sys.argv[1:] or None
    faces = defaultdict(dict)   # (bid,face) -> {resid,slope,supported}
    nf = defaultdict(int)
    for r in csv.DictReader(open(LEV / "d12_defect_faces.csv")):
        if r["arm"] != "gs_d4_dense":
            continue
        faces[r["bid"]][int(r["face"])] = {
            "resid": float(r["resid_abs"]) if r["resid_abs"] not in ("", "None", None) else None,
            "slope": float(r["slope_deg"]) if r["slope_deg"] not in ("", "None", None) else None,
            "sup": r["supported"] == "True"}
        nf[r["bid"]] += 1
    if not bids:
        bids = [b for b, _ in sorted(nf.items(), key=lambda kv: -kv[1])[:6]]   # top facet-rich
    for bid in bids:
        pr = parse_solid_roof("gs_d4_dense", bid)
        if pr is None:
            continue
        rf, V = pr
        paths = footprint_paths(bid)
        als = read_cloud("raw_lidar", bid, paths)
        ae = roof_envelope(als) if als is not None and len(als) else None
        fdat = faces.get(bid, {})
        fig, axs = plt.subplots(1, 3, figsize=(16, 5.2))
        for col, key, lab, cmap, vlim in [(0, "resid", "height resid (m)", "Reds", (0, 2.5)),
                                          (1, "slope", "slope err (deg)", "plasma", (0, 60))]:
            sm = cm.ScalarMappable(cmap=cmap); sm.set_clim(*vlim)
            for i, r in enumerate(rf):
                v = fdat.get(i, {}).get(key)
                poly = V[r][:, :2]
                color = sm.to_rgba(v) if v is not None else (0.8, 0.8, 0.8, 1)
                sup = fdat.get(i, {}).get("sup", False)
                axs[col].fill(poly[:, 0], poly[:, 1], color=color, alpha=0.9,
                              edgecolor=("k" if sup else "lime"), lw=(0.4 if sup else 1.6))
            axs[col].set_aspect("equal"); axs[col].set_axis_off()
            axs[col].set_title(f"GS facets by {lab}\n(green edge=floating/unsupported)", fontsize=9)
            fig.colorbar(sm, ax=axs[col], fraction=0.04)
        if ae is not None:
            s = axs[2].scatter(ae[:, 0], ae[:, 1], c=ae[:, 2], cmap="viridis", s=6)
            fig.colorbar(s, ax=axs[2], fraction=0.04)
        axs[2].set_aspect("equal"); axs[2].set_axis_off(); axs[2].set_title(f"raw ALS roof pts (n={0 if als is None else len(als)})", fontsize=9)
        rv = [d["resid"] for d in fdat.values() if d.get("resid") is not None]
        sv = [d["slope"] for d in fdat.values() if d.get("slope") is not None]
        rr = (max(rv) - min(rv)) if rv else 0; sr = (max(sv) - min(sv)) if sv else 0
        fig.suptitle(f"D12 within-building defect {bid}: {len(rf)} GS facets | resid range {rr:.1f}m | slope range {sr:.0f}deg", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(FIG / f"facet_{bid}.png", dpi=105); plt.close(fig)
        print(f"  {bid}: {len(rf)} facets, resid range {rr:.2f}m, slope range {sr:.0f}deg -> facet_{bid}.png")
    print(f"[done] figs -> {FIG}/")


if __name__ == "__main__":
    main()
