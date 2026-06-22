#!/usr/bin/env python3
"""P0 assembly-failure diagnosis — recovery-ladder figure (ACMP-SMRF / ACMP-forcebuild / ALS) by bucket."""
import csv, json
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
R = "/workspace/JointBuildGS/results/tum_transfer/mob_analysis"
verdict = {r["bid"]: r for r in csv.DictReader(open(f"{R}/p0c_step2/eval/p0c_verdict.csv"))}
def load(p): return {r["building_id"].split("_")[-1]: r for r in csv.DictReader(open(p))}
fb = load(f"{R}/p0c_step2/eval/acmp_forcebuild_status.csv")
al = load(f"{R}/p0c_step2/eval/als_canon_status.csv")
def lod(r): return bool(r) and r.get("has_lod22") == "True"
buckets = ["pointcloud_unusable_no_points", "missing_lod22_geometry", "pointcloud_unusable_no_planes"]
blab = ["no_points (46)", "missing_lod22 (16)", "no_planes (2)"]
tgt = list(verdict.keys())
def count(pred):
    return [sum(1 for b in tgt if verdict[b]["reason"] == bk and pred(b)) for bk in buckets]
step2 = count(lambda b: verdict[b]["verdict"] == "recoverable")
forceb = count(lambda b: lod(fb.get(b)))
als = count(lambda b: lod(al.get(b)))
tot = [sum(1 for b in tgt if verdict[b]["reason"] == bk) for bk in buckets]
x = np.arange(len(buckets)); w = 0.25
fig, ax = plt.subplots(figsize=(9, 5.2))
ax.bar(x - w, step2, w, label=f"ACMP @ SMRF-classified (Step2): {sum(step2)}/64", color="#1f77b4")
ax.bar(x, forceb, w, label=f"ACMP @ force-build roof kept: {sum(forceb)}/64", color="#2ca02c")
ax.bar(x + w, als, w, label=f"ALS @ same Roofer: {sum(als)}/64", color="#7f7f7f")
for i, t in enumerate(tot):
    ax.text(i, t + 0.4, f"/{t}", ha="center", fontsize=8, color="#555")
ax.set_xticks(x); ax.set_xticklabels(blab)
ax.set_ylabel("buildings recovering LoD2.2")
ax.set_title("P0 assembly-failure: recovery by cloud×classification (same Roofer+config)\n"
             "ALS=backend exonerated; SMRF roof-eating costs +22; residual=cloud-limited (observation)")
ax.legend(fontsize=8); ax.set_ylim(0, max(tot) + 4); fig.tight_layout()
fig.savefig("/workspace/JointBuildGS/docs/figs/tum_transfer/p0c_assembly_recovery.png", dpi=130)
print("[fig] docs/figs/tum_transfer/p0c_assembly_recovery.png")
