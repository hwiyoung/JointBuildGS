#!/usr/bin/env python3
"""P2 v6 over-segmentation diagnosis — is GS roof-splitting (가) GS surface roughness or
(나) Roofer threshold over-sensitivity? Read-only, CPU, no retraining. Observation only.

For 5 buildings (Q3 + control R2) x {GS_dense, GS_acmp, raw_dense, raw_acmp, LiDAR} reads the orig
classified LAS (building class-6 in footprint = exactly what Roofer saw) and computes:
  - plane_rms      : dominant-plane SVD residual (global roughness, reused from p0c_assembly_diag)
  - patch_rms_med  : median within-2m-cell plane RMS  (LOCAL NOISE, facet-structure removed)
  - normal_disp_deg: std of per-2m-cell normal angle vs dominant (between-patch orientation spread)
  - ransac_planes  : sequential RANSAC plane count (data-supported planes; thr 0.15m)
  - roofer_facet   : RoofSurface count from Roofer (orig tag) for the same points
Discriminator: GS patch_rms ≫ raw/LiDAR or GS ransac ≫ raw -> (가) surface. GS patch_rms ≈ raw and
ransac ≈ raw/LiDAR but roofer_facet ≫ ransac -> (나) Roofer threshold.
Runs in jointbuildgs-p0-tools:t0. Out: results/tum_transfer/mob/analysis_pack_v6/overseg_diag.csv
"""
import csv, json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
import numpy as np, laspy
from scripts.input_and_alignment.tum_transfer.p0c_assembly_diag import plane_rms  # verbatim dominant-plane SVD residual

REPO = "/workspace/JointBuildGS"
EVALROOT = f"{REPO}/phases/p0-audit/runs/mob_eval"
OUT = f"{REPO}/results/tum_transfer/mob/analysis_pack_v6"
ARMS = [("GS_dense", "gs_seed_dense"), ("GS_acmp", "gs_seed_acmp"),
        ("raw_dense", "raw_dense"), ("raw_acmp", "raw_acmp"), ("LiDAR", "raw_lidar")]
TARGETS = [("4906969", "Q"), ("4906972", "Q"), ("4908023", "Q"),
           ("42364663", "R"), ("4907510", "R")]


def cell_normals(P, cell=2.0, minpts=8):
    """Per 2m cell: PCA normal (nz>=0) + within-cell plane RMS."""
    g = np.floor(P[:, :2] / cell).astype(np.int64)
    key = g[:, 0] * 100003 + g[:, 1]
    normals, local_rms = [], []
    for k in np.unique(key):
        Q = P[key == k]
        if len(Q) < minpts:
            continue
        c = Q.mean(0)
        _, _, Vt = np.linalg.svd(Q - c, full_matrices=False)
        n = Vt[-1]
        if n[2] < 0:
            n = -n
        normals.append(n)
        local_rms.append(float(np.sqrt((((Q - c) @ Vt[-1]) ** 2).mean())))
    return (np.array(normals) if normals else np.empty((0, 3))), np.array(local_rms)


def ransac_planes(P, thr=0.15, min_frac=0.05, min_abs=30, max_planes=12, iters=120, rng=None):
    """Sequential RANSAC: extract dominant planes, remove inliers, repeat. Count accepted planes."""
    if rng is None:
        rng = np.random.default_rng(0)
    rem = P.copy()
    n0 = len(P)
    min_inl = max(min_abs, int(min_frac * n0))
    planes = 0
    while len(rem) >= min_inl and planes < max_planes:
        best_in, best_mask = 0, None
        for _ in range(iters):
            idx = rng.choice(len(rem), 3, replace=False)
            A = rem[idx]
            v1, v2 = A[1] - A[0], A[2] - A[0]
            nrm = np.cross(v1, v2)
            ln = np.linalg.norm(nrm)
            if ln < 1e-9:
                continue
            nrm = nrm / ln
            d = np.abs((rem - A[0]) @ nrm)
            mask = d < thr
            c = int(mask.sum())
            if c > best_in:
                best_in, best_mask = c, mask
        if best_in < min_inl:
            break
        planes += 1
        rem = rem[~best_mask]
    return planes


def main():
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    # roofer facet (orig tag) from both eval jsons
    facet = {}
    for p in [f"{REPO}/results/tum_transfer/mob/eval_v6.json",
              f"{REPO}/results/tum_transfer/mob/eval_v6_raw.json"]:
        if Path(p).exists():
            for r in json.loads(Path(p).read_text()):
                if r.get("tag") == "orig":
                    facet[(r["config"], r["bid"])] = r.get("roof_surfaces")

    rows = []
    for short, cls in TARGETS:
        bid = f"DEBY_LOD2_{short}"
        for label, arm in ARMS:
            las = Path(f"{EVALROOT}/{arm}/{bid}_orig_classified.las")
            row = {"building": short, "cls": cls, "arm": label, "n_b6": 0,
                   "plane_rms_m": None, "patch_rms_med_m": None, "normal_disp_deg": None,
                   "ransac_planes": None, "roofer_facet": facet.get((arm, bid))}
            if las.exists():
                c = laspy.read(las)
                cl = np.asarray(c.classification)
                P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)])[cl == 6]
                row["n_b6"] = int(len(P))
                if len(P) >= 12:
                    row["plane_rms_m"] = round(plane_rms(P), 3) if plane_rms(P) is not None else None
                    nrm, lrms = cell_normals(P)
                    if len(nrm) >= 2:
                        ndom = nrm.mean(0); ndom /= (np.linalg.norm(ndom) + 1e-12)
                        ang = np.degrees(np.arccos(np.clip(np.abs(nrm @ ndom), 0, 1)))
                        row["normal_disp_deg"] = round(float(ang.std()), 2)
                    if len(lrms):
                        row["patch_rms_med_m"] = round(float(np.median(lrms)), 3)
                    row["ransac_planes"] = ransac_planes(P)
            rows.append(row)

    Path(OUT).mkdir(parents=True, exist_ok=True)
    keys = ["building", "cls", "arm", "n_b6", "plane_rms_m", "patch_rms_med_m",
            "normal_disp_deg", "ransac_planes", "roofer_facet"]
    with open(f"{OUT}/overseg_diag.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

    print(f"{'bld':9}{'c':2}{'arm':10}{'n_b6':>8}{'planeRMS':>9}{'patchRMS':>9}{'nDispDeg':>9}{'ransac':>7}{'roofer':>7}")
    for r in rows:
        print(f"{r['building']:9}{r['cls']:2}{r['arm']:10}{r['n_b6']:>8}"
              f"{str(r['plane_rms_m']):>9}{str(r['patch_rms_med_m']):>9}{str(r['normal_disp_deg']):>9}"
              f"{str(r['ransac_planes']):>7}{str(r['roofer_facet']):>7}")
    print(f"\n[done] -> {OUT}/overseg_diag.csv")


if __name__ == "__main__":
    main()
