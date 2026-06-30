#!/usr/bin/env python3
"""D12 / gen-8way Step0 — label the P0 failure population (64) into MECHANISM buckets (reuse only).
  ① textureless  = W4c classification b_textureless (5)
  ② assembly     = p0c_verdict reason missing_lod22_geometry (16, ACMP pts exist but unassemblable)
  coverage       = W4c c_nearnadir_gap (36, near-nadir acquisition gap — NOT a method failure)
  impossible/other = W4c d_impossible/e_other_textured + p0c no_planes (~7)
method_relevant (① + ②) get GS execution; coverage/other get baseline+LiDAR only.
Out: results/.../mob/overseg_lever/d12_buckets.csv. NO retrain. Observe only.
"""
import csv, json
from pathlib import Path
REPO = Path("/workspace/JointBuildGS")
MOB = REPO / "results/tum_transfer/mob"
P0V = REPO / "results/tum_transfer/mob_analysis/p0c_step2/eval/p0c_verdict.csv"
W4C = REPO / "phases/p0-audit/docs/W4c_no_points_breakdown.csv"
ISSUES = REPO / "docs/issues.md"

def main():
    if not P0V.exists():
        with open(ISSUES, "a") as f: f.write("- [gen-8way] p0c_verdict.csv missing — cannot label buckets; abort Task B\n")
        print("FATAL: p0c_verdict missing"); return 1
    verdict = {r["bid"]: r for r in csv.DictReader(open(P0V))}
    w4c = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(W4C))} if W4C.exists() else {}
    aoi = set(f["properties"]["building_id"].replace("DEBY_LOD2_", "")
              for f in json.load(open(MOB.parent / "analysis/footprints_aoi.geojson"))["features"])
    rows = []
    for bid, v in verdict.items():
        reason = v.get("reason", "")
        wc = w4c.get(bid, {}).get("classification", "")
        if reason == "missing_lod22_geometry":
            bucket = "2_assembly"
        elif reason == "pointcloud_unusable_no_planes":
            bucket = "4_impossible"
        elif wc == "b_textureless":
            bucket = "1_textureless"
        elif wc == "c_nearnadir_gap":
            bucket = "3_coverage"
        elif wc in ("d_impossible", "e_other_textured"):
            bucket = "4_impossible"
        else:
            bucket = "4_impossible"
        rows.append({"bid": bid, "bucket": bucket,
                     "method_relevant": bucket in ("1_textureless", "2_assembly"),
                     "in_aoi": bid in aoi, "reason": reason, "w4c_class": wc,
                     "acmp_n": v.get("acmp_n"), "verdict": v.get("verdict")})
    out = MOB / "overseg_lever" / "d12_buckets.csv"; out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print("buckets:", dict(Counter(r["bucket"] for r in rows)))
    print("method_relevant (GS):", sum(r["method_relevant"] for r in rows), "| in_aoi:", sum(r["in_aoi"] for r in rows), "/", len(rows))
    print(f"[done] -> {out}")
    return 0

if __name__ == "__main__":
    import sys; sys.exit(main())
