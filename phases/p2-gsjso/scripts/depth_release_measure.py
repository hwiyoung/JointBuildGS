#!/usr/bin/env python3
"""P2 impl ② measurement — do textureless seed columns converge to the reference roof height?

For the 5 textureless + 3 control buildings, report roof-class Gaussian height (median + [p5,p95])
at (prior-init = condition-A carve) / (A after) / (B after), and Δ vs reference roof. Observation only.
Runs in dev container (torch). Frame: GS-local z = H_ortho + geoid(48) - 604.
"""
import json, csv, sys
from pathlib import Path
import numpy as np, torch
from matplotlib.path import Path as MplPath
sys.path.insert(0, "/workspace/JointBuildGS")
from src.stage2.semantic_seed import build_semantic_seeds, cameras_from_colmap

REPO = "/workspace/JointBuildGS"
SHIFT = np.array([690953.0, 5336071.0, 604.0]); GEOID = 48.0
NOSEED = ["42364609", "4907182", "4908050", "4908166", "4908176"]
CTRL = ["42364659", "42364663", "4907510"]
ALLB = NOSEED + CTRL
geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
refh = {r["building_id"]: r for r in csv.DictReader(open(f"{REPO}/results/tum_transfer/mob_analysis/ref_roof_heights.csv"))}


def ring_local(bid):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    co = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return np.asarray(co)[:, :2] - SHIFT[:2]


def stats(xyz, is_roof, bid):
    fp = MplPath(ring_local(bid))
    m = fp.contains_points(xyz[:, :2]) & is_roof
    z = xyz[m, 2]
    if len(z) < 3:
        return None
    return dict(n=int(len(z)), med=round(float(np.median(z)), 2),
                p5=round(float(np.percentile(z, 5)), 2), p95=round(float(np.percentile(z, 95)), 2))


# prior-init = condition-A seeds (band A), roof-class
cams = cameras_from_colmap(f"{REPO}/results/tum_transfer/data_geoidfix/sparse")
bandsA = json.loads(Path(f"{REPO}/results/tum_transfer/mob_analysis/seed_bands_range.json").read_text())
seeds = build_semantic_seeds(
    cameras=cams, semantic_dir=f"{REPO}/results/tum_transfer/clean_labels_geoidfix/semantic",
    footprints_path=f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson",
    buildings=[f"DEBY_LOD2_{b}" for b in ALLB], scene_rgb=[0.5, 0.5, 0.5],
    bands=bandsA, voxel=1.0, tau=0.6, min_obs=5, verbose=False)
init_xyz, init_roof = seeds.xyz, (seeds.sem == 1)


def load(cond):
    sd = torch.load(f"{REPO}/results/tum_transfer/mob/depth_release_{cond}/ckpt/final.pt",
                    map_location="cpu", weights_only=False)["state_dict"]
    return sd["means"].numpy(), (sd["sem_logits"].numpy().argmax(1) == 1)


A_m, A_r = load("range"); B_m, B_r = load("oracle")

rows = []
print(f"{'building':20} {'cls':8} {'refRoof':8} {'prior_med':9} {'A_med':7} {'A_Δ':6} {'B_med':7} {'B_Δ':6}")
for b in ALLB:
    bid = f"DEBY_LOD2_{b}"
    rr = round(float(refh[bid]["h_roof"]) + GEOID - 604.0, 2)
    pi, a, bb = stats(init_xyz, init_roof, bid), stats(A_m, A_r, bid), stats(B_m, B_r, bid)
    row = dict(bid=bid, klass=("no-seed" if b in NOSEED else "control"), ref_roof_local=rr,
               prior=pi, A=a, B=bb,
               A_delta=(round(a["med"] - rr, 2) if a else None),
               B_delta=(round(bb["med"] - rr, 2) if bb else None))
    rows.append(row)
    print(f"{bid:20} {row['klass']:8} {rr:<8} "
          f"{(pi['med'] if pi else '-'):<9} {(a['med'] if a else '-'):<7} {str(row['A_delta']):<6} "
          f"{(bb['med'] if bb else '-'):<7} {str(row['B_delta']):<6}")

out = f"{REPO}/results/tum_transfer/mob_analysis/depth_release_convergence"
json.dump(rows, open(out + ".json", "w"), indent=2)
with open(out + ".csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["building", "class", "ref_roof_local", "prior_med", "prior_p5", "prior_p95",
                "A_med", "A_p5", "A_p95", "A_delta", "B_med", "B_p5", "B_p95", "B_delta"])
    for r in rows:
        pi, a, bb = r["prior"], r["A"], r["B"]
        w.writerow([r["bid"], r["klass"], r["ref_roof_local"],
                    pi and pi["med"], pi and pi["p5"], pi and pi["p95"],
                    a and a["med"], a and a["p5"], a and a["p95"], r["A_delta"],
                    bb and bb["med"], bb and bb["p5"], bb and bb["p95"], r["B_delta"]])

def conv(key, tol=2.0):
    return sum(1 for r in rows if r["klass"] == "no-seed" and r[key] is not None and abs(r[key]) <= tol)
kA, kB = conv("A_delta"), conv("B_delta")
cA = sum(1 for r in rows if r["klass"] == "control" and r["A_delta"] is not None and abs(r["A_delta"]) <= 2.0)
print(f"\nOBS: textureless within reference ±2 m — A(honest)={kA}/5, B(oracle ceiling)={kB}/5; control A={cA}/3.")
print(f"[done] -> {out}.csv/.json")
