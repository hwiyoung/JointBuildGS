#!/usr/bin/env python3
"""P2-D6 generation-status — canonical (mob-harness, gssem-requal) assembly table for the 11.

For each building: raw(DIM->Roofer) / proposed GS-JSO(D4 gssem) / LiDAR(ALS) — assembled? valid-solid?
target-only facets. "assembled" = target building got a roof model (target-only RoofSurface>=1; Roofer
'roofer_ok' alone counts neighbour output, so it is NOT used for assembly). valid-solid = eval val3dity
(CLIP-level — combined cityjson incl. neighbours; caveat). Facets RECOMPUTED from current disk
(d5_target_facets.csv is stale pre-requal). DIM class6 point count = textureless proxy.

Source: phases/p0-audit/runs/mob_eval/<arm>/roofer_*/*.city.jsonl (gssem canonical disk) +
eval_d4_gssem.json / eval_v6_raw.json (val3dity). NOT the w3_2b survey harness. Observation only.
Out: results/tum_transfer/mob/analysis_pack_d6/gen_status.csv
"""
import csv, glob, json
from pathlib import Path
import laspy, numpy as np

REPO = Path("/workspace/JointBuildGS")
EVAL = REPO / "phases/p0-audit/runs/mob_eval"
M = REPO / "results/tum_transfer/mob"
OUT = M / "analysis_pack_d6"
Q = ["4906969", "4906972", "4908023"]
R = ["42364659", "42364663", "4907182", "4907510", "42364609", "4908050", "4908166", "4908176"]
ALLB = Q + R


def tgt_facets(arm, bid):
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVAL / arm / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    n = 0
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if cid == full or cid.startswith(full + "-"):
                for gm in o.get("geometry", []):
                    for s in gm.get("semantics", {}).get("surfaces", []):
                        if s.get("type") == "RoofSurface":
                            n += 1
    return n


def valid_idx(path):
    d = {}
    try:
        for r in json.load(open(path)):
            if r.get("tag") == "orig":
                d[(r["config"], r["bid"])] = r.get("val3dity_valid")
    except FileNotFoundError:
        pass
    return d


def dim_pts(bid):
    f = EVAL / "raw_dense" / f"DEBY_LOD2_{bid}_orig_classified.las"
    if not f.exists():
        return None
    c = laspy.read(f)
    return int((np.asarray(c.classification) == 6).sum())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vd4 = valid_idx(M / "eval_d4_gssem.json")
    vraw = valid_idx(M / "eval_v6_raw.json")
    base = json.loads((M / "baselines.json").read_text())
    rows = []
    for bid in ALLB:
        full = f"DEBY_LOD2_{bid}"
        ref = base.get(full, {}).get("ref_roof_surfaces")
        rawf = tgt_facets("raw_dense", bid)   # DIM
        gsf = tgt_facets("gs_d4_dense", bid)   # GS-JSO D4
        alsf = tgt_facets("raw_lidar", bid)    # ALS
        dpts = dim_pts(bid)
        def asm(f): return "Y" if (f is not None and f >= 1) else "N"
        rows.append({"bid": bid, "set": "Q" if bid in Q else "R", "ref_facets": ref,
                     "DIM_assembled": asm(rawf), "DIM_facets": rawf, "DIM_valid": vraw.get(("raw_dense", full)),
                     "GS_assembled": asm(gsf), "GS_facets": gsf, "GS_valid": vd4.get(("gs_d4_dense", full)),
                     "ALS_assembled": asm(alsf), "ALS_facets": alsf, "ALS_valid": vraw.get(("raw_lidar", full)),
                     "DIM_class6_pts": dpts, "textureless": "Y" if (dpts is not None and dpts < 700) else "N"})
    with open(OUT / "gen_status.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    # console summary
    print(f"{'bid':10}{'set':4}{'ref':>4} | DIM asm/fac/val | GS asm/fac/val | ALS asm/fac/val | DIMpts txless")
    for r in rows:
        print(f"{r['bid']:10}{r['set']:4}{str(r['ref_facets']):>4} | "
              f"{r['DIM_assembled']}/{str(r['DIM_facets']):>2}/{str(r['DIM_valid'])[:1]:>1} | "
              f"{r['GS_assembled']}/{str(r['GS_facets']):>2}/{str(r['GS_valid'])[:1]:>1} | "
              f"{r['ALS_assembled']}/{str(r['ALS_facets']):>2}/{str(r['ALS_valid'])[:1]:>1} | "
              f"{str(r['DIM_class6_pts']):>6} {r['textureless']}")
    rr = [r for r in rows if r["set"] == "R"]
    def cnt(k): return sum(1 for r in rr if r[k] == "Y")
    print(f"\nR-set (8 생성표적): DIM {cnt('DIM_assembled')}/8 -> GS {cnt('GS_assembled')}/8 -> ALS {cnt('ALS_assembled')}/8")
    print("textureless R:", [r["bid"] for r in rr if r["textureless"] == "Y"])
    print(f"[done] -> {OUT}/gen_status.csv")


if __name__ == "__main__":
    main()
