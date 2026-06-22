#!/usr/bin/env python3
"""P0 completeness re-verification (Step 2) — per-building recoverability verdict.

Combines the cell grid into a per-building verdict for the 64 generation-failure targets:
  cell1 = DIM @ Roofer-canonical (baseline = canonical w2_1; all 64 fail by construction)
  cell2 = DIM @ Roofer-tuned        (Roofer-param lever, same DIM cloud)
  cell3 = ACMP @ Roofer-canonical   (cloud lever, default params)
  cell4 = ACMP @ Roofer-tuned       (cloud + param lever)

Verdict per building (observation only; human judges):
  recoverable(roofer)  : recovers LoD2.2 under cell2 (same cloud, tuned params)   -> lever=Roofer
  recoverable(cloud)   : recovers under cell3/4 but NOT cell2                      -> lever=cloud(ACMP)
  recoverable(both)    : recovers only under cell4 (needs denser cloud AND tuning) -> lever=both
  fundamental          : no cell yields LoD2.2 (ACMP cloud present but unassemblable)
  fundamental(no-signal): also ACMP point-absent (<1 pt in footprint)             -> Pass-2 candidate
Runs in jointbuildgs-p0-tools (host python ok; stdlib + matplotlib). EPSG:25832.
"""
import csv, json, glob, os
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path("/workspace/JointBuildGS")
EVAL = REPO / "results/tum_transfer/mob_analysis/p0c_step2/eval"
CENSUS = json.load(open(REPO / "results/tum_transfer/mob_analysis/p0_census.json"))
PROBE = json.load(open(REPO / "results/tum_transfer/mob_analysis/acmp_clip_probe.json"))
W2 = REPO / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv"


def load_status(path):
    if not Path(path).exists():
        return {}
    return {r["building_id"]: r for r in csv.DictReader(open(path))}


def lod(r):  # has LoD2.2 geometry
    return bool(r) and r.get("has_lod22") == "True"


def valid(r):
    return bool(r) and r.get("status") == "success"


def main():
    tgt = {o["bid"]: o["dim_reason"] for o in CENSUS["targets"]}
    cell1 = {r["building_id"]: r for r in csv.DictReader(open(W2)) if r["input"] == "DIM"}
    cell2 = load_status(EVAL / "dim_tuned_status.csv")
    cell3 = load_status(EVAL / "acmp_canon_status.csv")
    cell4a = load_status(EVAL / "acmp_tuned_status.csv")
    cell4b = load_status(EVAL / "acmp_loose_status.csv")

    rows = []
    for bid, reason in tgt.items():
        c1, c2, c3 = cell1.get(bid), cell2.get(bid), cell3.get(bid)
        # cell4 = best of any tuned ACMP variant (tuned 0.30/15/0.888 or loose 0.45/10/0.65)
        c4 = c4a if lod(c4a := cell4a.get(bid)) else (cell4b.get(bid))
        acmp_n = PROBE.get(bid, {}).get("acmp_n", None)
        l1, l2, l3, l4 = lod(c1), lod(c2), lod(c3), (lod(cell4a.get(bid)) or lod(cell4b.get(bid)))
        # verdict + lever
        if l2:
            verdict, lever = "recoverable", "Roofer(params)"
        elif l3:
            verdict, lever = "recoverable", "cloud(ACMP)"
        elif l4:
            verdict, lever = "recoverable", "both(cloud+params)"
        elif acmp_n is not None and acmp_n < 1:
            verdict, lever = "fundamental(no-signal)", "none(ACMP=0pts)"
        else:
            verdict, lever = "fundamental(assembly)", "none(ACMP pts unassemblable)"
        any_valid = valid(c2) or valid(c3) or valid(cell4a.get(bid)) or valid(cell4b.get(bid))
        rows.append(dict(bid=bid.split("_")[-1], reason=reason, acmp_n=acmp_n,
                         lod_c2=l2, lod_c3=l3, lod_c4=l4, valid=any_valid,
                         verdict=verdict, lever=lever))

    rows.sort(key=lambda r: (r["reason"], r["verdict"], r["bid"]))
    out = EVAL / "p0c_verdict.json"
    json.dump(rows, open(out, "w"), indent=1)
    with open(EVAL / "p0c_verdict.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    # summaries
    from collections import Counter, defaultdict
    print("\n##### PER-BUILDING RECOVERABILITY VERDICT (64 targets) #####")
    print(f"{'bid':12s} {'bucket':26s} acmp_n  c2 c3 c4 valid  verdict / lever")
    for r in rows:
        print(f"{r['bid']:12s} {r['reason']:26s} {str(r['acmp_n']):>6s}  "
              f"{int(r['lod_c2'])}  {int(r['lod_c3'])}  {int(r['lod_c4'])}   {int(r['valid'])}    {r['verdict']} / {r['lever']}")
    print("\n##### verdict counts by bucket #####")
    bybkt = defaultdict(Counter)
    for r in rows:
        bybkt[r["reason"]][r["verdict"]] += 1
    for bkt, c in sorted(bybkt.items()):
        print(f"  {bkt}: {dict(c)}")
    print("\n##### lever counts (recovered only) #####")
    lev = Counter(r["lever"] for r in rows if r["verdict"] == "recoverable")
    print(f"  {dict(lev)}")
    nrec = sum(1 for r in rows if r["verdict"] == "recoverable")
    print(f"\n  recovered LoD2.2: {nrec}/64 | valid(success): {sum(1 for r in rows if r['valid'])}/64 | "
          f"fundamental: {sum(1 for r in rows if r['verdict'].startswith('fundamental'))}/64")

    # figure: stacked verdict by bucket
    buckets = ["pointcloud_unusable_no_points", "missing_lod22_geometry", "pointcloud_unusable_no_planes"]
    verds = ["recoverable", "fundamental(assembly)", "fundamental(no-signal)"]
    colors = {"recoverable": "#2ca02c", "fundamental(assembly)": "#ff7f0e", "fundamental(no-signal)": "#d62728"}
    fig, ax = plt.subplots(figsize=(9, 5))
    import numpy as np
    bottom = np.zeros(len(buckets))
    for v in verds:
        vals = [bybkt[b][v] for b in buckets]
        ax.bar([b.replace("pointcloud_unusable_", "") for b in buckets], vals, bottom=bottom,
               label=v, color=colors[v])
        bottom += np.array(vals)
    ax.set_ylabel("buildings"); ax.set_title("P0 completeness: recoverability of 64 generation-failure targets\n(cloud=ACMP / Roofer-param levers; observation only)")
    ax.legend(); fig.tight_layout()
    figp = REPO / "docs/figs/tum_transfer/p0c_recoverability.png"
    figp.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figp, dpi=130); plt.close(fig)
    print(f"[done] {out} + {figp}")


if __name__ == "__main__":
    main()
