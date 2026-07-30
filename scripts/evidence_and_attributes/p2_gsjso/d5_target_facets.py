#!/usr/bin/env python3
"""P2-D5 — TARGET-ONLY roof-facet counts (the pre-registered §6 over-seg measurement; verdict=human).

The eval JSON roof_surfaces counts EVERY RoofSurface in the clip cityjson, so neighbour buildings inflate
it (W_D4 §7: 4906972 clip=8 vs target=3). This script counts ONLY the target building's facets by keeping
the CityObjects whose id is the target id or a Roofer LoD child of it (DEBY_LOD2_<bid> / DEBY_LOD2_<bid>-N),
dropping neighbours. VALIDATED: reproduces W_D4's published target-only column for gs_d4_dense
(4906972=3, 4907182=0, 4906969=13, 4908023=2, 4907510=0, 42364659=5).

Reads phases/p0-audit/runs/mob_eval/<config>/roofer_DEBY_LOD2_<bid>_orig/*.city.jsonl.
Prints the cp-ladder over-seg table and writes results/tum_transfer/mob/d5_target_facets.csv.
"""
import csv, glob, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVALROOT = REPO / "phases/p0-audit/runs/mob_eval"
M = REPO / "results/tum_transfer/mob"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
COMPOSITE = ["42364663", "42364659"]; CURVED = ["4906969"]; FLAT = ["4906972", "4907182"]; CTRL = ["4908023"]

# cp ladder + baselines.  (label, config, density-tag for display)
ARMS = [
    ("off",   "gs_d5a_dense"), ("fair", "gs_d4_dense"), ("early", "gs_d5c_dense"), ("hard", "gs_d5b_dense"),
    ("offAc", "gs_d5a_acmp"),  ("fairAc", "gs_d4_acmp"), ("earlyAc", "gs_d5c_acmp"), ("hardAc", "gs_d5b_acmp"),
    ("v6",    "gs_seed_dense_protect"), ("img", "raw_dense"), ("LiD", "raw_lidar"),
]


def target_roofs(config, bid):
    """Target-only RoofSurface count for one (config, bid); None if no roofer output (not assembled)."""
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVALROOT / config / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    n = 0
    for ln in open(g[0]):
        if not ln.strip():
            continue
        feat = json.loads(ln)
        for cid, o in feat.get("CityObjects", {}).items():
            if not (cid == full or cid.startswith(full + "-")):
                continue  # drop neighbour buildings in the clip
            for geom in o.get("geometry", []):
                for s in geom.get("semantics", {}).get("surfaces", []):
                    if s.get("type") == "RoofSurface":
                        n += 1
    return n


def main():
    base = json.loads((M / "baselines.json").read_text())
    rows = []  # csv
    lines = []
    def out(s=""):
        lines.append(s); print(s)

    out("# P2-D5 — TARGET-ONLY roof facets (cp ladder; 관찰만, 판정=사람)")
    out("# focus: composite{42364663,42364659} curved{4906969} flat{4906972,4907182} control{4908023}\n")
    hdr = f"{'bid':>9} {'set':>5} {'ref':>3} | " + " ".join(f"{lbl:>6}" for lbl, _ in ARMS)
    out(hdr); out("-" * len(hdr))

    def setof(t):
        return ("comp" if t in COMPOSITE else "curv" if t in CURVED else
                "flat" if t in FLAT else "ctrl" if t in CTRL else "rec")

    order = COMPOSITE + CURVED + FLAT + CTRL + [t for t in TARGETS if t not in COMPOSITE + CURVED + FLAT + CTRL]
    for t in order:
        ref = base[f"DEBY_LOD2_{t}"]["ref_roof_surfaces"]
        cells = []
        rec = {"bid": t, "set": setof(t), "ref": ref}
        for lbl, cfg in ARMS:
            n = target_roofs(cfg, t)
            rec[lbl] = "" if n is None else n
            cells.append("-" if n is None else str(n))
        out(f"{t:>9} {setof(t):>5} {ref:>3} | " + " ".join(f"{c:>6}" for c in cells))
        rows.append(rec)

    csv_path = M / "d5_target_facets.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bid", "set", "ref"] + [lbl for lbl, _ in ARMS])
        w.writeheader(); w.writerows(rows)
    out(f"\n[done] -> {csv_path}")
    (M / "REPORT_D5_facets.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
