#!/usr/bin/env python3
"""D12 — per-building / per-facet THREE-AXIS GS defect vs raw ALS (no retrain, reads existing Roofer
Solids + ALS clips produced by run_d12_eval.sh). Observe only; verdict=김휘영. EPSG:25832.

Axes (all GS-facet vs raw ALS points/facets; dz-robust = global vertical offset removed by free sweep):
  HEIGHT   : dz-robust best-fit resid = min over a clamp-free dz sweep of mean_facet median|ALS_z - plane|
             + support k/m (facet supported iff >=MIN_ALS pts AND median|resid|<TOL at best-fit dz).
  SLOPE    : per GS facet, fit ALS points under it -> ALS plane normal; angle(GS normal, ALS normal) deg.
  HORIZ    : facet-to-facet match (GS<->ALS by normal-sim AND centroid-XY proximity); matched horizontal
             centroid-XY offset (m). Approximate (ridge/edge extraction not done); unmatched count flagged.
  PSD      : point-to-surface RMS = RMS of ALS-point to nearest-GS-facet-plane residual at best-fit dz
             (standard combined fidelity). Facet count (GS/ALS/ref) = over-seg readout (NOT position).

Run (p0-tools): docker run --rm --user $(id -u):$(id -g) -v $PWD:/workspace/JointBuildGS -w /workspace/JointBuildGS \
  jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/p2_gsjso/d12_defect.py --arms gs_d4_dense gs_b1_dense [--targets ...]
Out: results/.../overseg_lever/d12_defect.csv + d12_defect_faces.csv.
"""
import argparse, csv, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from d6_shape_audit import footprint_paths, read_cloud, roof_envelope, gml_building
from overseg_analysis import parse_solid_roof
from assembly_fidelity import fit_plane
from overseg_faithfulness import face_support, MIN_ALS, TOL
from matplotlib.path import Path as MplPath

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
DZ = np.round(np.arange(-10.0, 8.01, 0.25), 2)
MERGE_NCOS, MATCH_XY = 0.90, 4.0   # facet-match: |n.n|>0.90 AND centroid-XY within 4m


def best_dz(roof_faces, V, als):
    means = []
    for dz in DZ:
        sup = face_support(roof_faces, V, als, dz=float(dz))
        ra = [s["resid_abs"] for s in sup if s["resid_abs"] is not None]
        means.append(np.mean(ra) if ra else np.inf)
    i = int(np.argmin(means))
    return float(DZ[i]), float(means[i])


def slope_psd(roof_faces, V, als, dz):
    """per-facet GS-vs-ALS normal angle (deg, ALS-support-weighted) + global point-to-surface RMS at dz.

    Returns (per_facet_angles, weights, psd). The aggregate slope reported is the ALS-point-WEIGHTED
    mean so Roofer's near-vertical sliver facets (few ALS pts) don't dominate the building slope error.
    Per-facet angles are still returned (for facet-level analysis) but weighted by ALS support.
    """
    angles, weights, all_resid = [], [], []
    for r in roof_faces:
        n_gs, c = fit_plane(V[r])
        poly = MplPath(V[r][:, :2])
        m = poly.contains_points(als[:, :2])
        Q = als[m]
        if len(Q) < MIN_ALS:
            angles.append(None); weights.append(0); continue
        nz = n_gs[2] if abs(n_gs[2]) > 1e-6 else 1e-6
        zf = (float(n_gs @ c) - n_gs[0] * Q[:, 0] - n_gs[1] * Q[:, 1]) / nz
        all_resid.extend(((Q[:, 2] - dz) - zf).tolist())
        # slope only where the ALS support is 2D (>=8 pts AND XY spread >=1m both dims) so a thin/collinear
        # strip under a sliver facet can't yield a degenerate near-vertical ALS-fit normal.
        if len(Q) < 8 or float(np.ptp(Q[:, 0])) < 1.0 or float(np.ptp(Q[:, 1])) < 1.0:
            angles.append(None); weights.append(0); continue
        Qd = Q.copy(); Qd[:, 2] -= dz
        n_als, _ = fit_plane(Qd)
        ang = float(np.degrees(np.arccos(abs(float(np.clip(n_gs @ n_als, -1, 1)))))) if n_als is not None else None
        angles.append(ang); weights.append(len(Q))
    psd = float(np.sqrt(np.mean(np.square(all_resid)))) if all_resid else None
    return angles, weights, psd


def horiz_offsets(gs_faces, Vg, als_faces, Va):
    """facet-to-facet (GS<->ALS) match by normal-sim AND centroid-XY; matched horizontal centroid offset."""
    if not als_faces:
        return [], len(gs_faces)
    aprops = [(fit_plane(Va[r])) for r in als_faces]  # (n,c)
    offs, unm = [], 0
    for r in gs_faces:
        ng, cg = fit_plane(Vg[r])
        best, bestd = None, 1e9
        for (na, ca) in aprops:
            if abs(float(ng @ na)) <= MERGE_NCOS:
                continue
            d = float(np.linalg.norm((cg - ca)[:2]))
            if d < bestd:
                bestd, best = d, ca
        if best is not None and bestd < MATCH_XY:
            offs.append(bestd)
        else:
            unm += 1
    return offs, unm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["gs_d4_dense", "gs_b1_dense"])
    ap.add_argument("--targets", nargs="*", default=None)
    ap.add_argument("--targets-file", default=None)
    args = ap.parse_args()
    if args.targets_file:
        bids = Path(args.targets_file).read_text().split()
    elif args.targets:
        bids = args.targets
    else:
        bids = ["42364609","42364659","42364663","4907182","4907510","4908050","4908166","4908176","4906969","4908023","4906972"]
    LEV.mkdir(parents=True, exist_ok=True)
    rows, faces = [], []
    for bid in bids:
        paths = footprint_paths(bid)
        als = read_cloud("raw_lidar", bid, paths)
        if als is None or len(als) < MIN_ALS:
            continue
        rt, ref_roof, _ = gml_building(bid)
        n_ref = len(ref_roof) if ref_roof else 0
        pra = parse_solid_roof("raw_lidar", bid)
        als_faces, Va = (pra if pra else (None, None))
        n_als = len(als_faces) if als_faces else 0
        for arm in args.arms:
            pr = parse_solid_roof(arm, bid)
            if pr is None:
                continue
            gs_faces, Vg = pr
            dz, h_resid = best_dz(gs_faces, Vg, als)
            sup = face_support(gs_faces, Vg, als, dz=dz)
            k = sum(1 for s in sup if s["supported"]); m = len(sup) - k
            angles, weights, psd = slope_psd(gs_faces, Vg, als, dz)
            va = [(a, w) for a, w in zip(angles, weights) if a is not None and w > 0]
            if va:
                aw = np.array([a for a, _ in va]); ww = np.array([w for _, w in va], float)
                slope_wmean = float((aw * ww).sum() / ww.sum()); slope_med = float(np.median(aw))
            else:
                slope_wmean = slope_med = None
            offs, unm = horiz_offsets(gs_faces, Vg, als_faces, Va) if als_faces else ([], len(gs_faces))
            rows.append({
                "bid": bid, "arm": arm, "roofType": rt,
                "n_gs": len(gs_faces), "n_als": n_als, "n_ref": n_ref,
                "height_resid": round(h_resid, 3), "best_dz": round(dz, 2),
                "k_sup": k, "m_flo": m, "support_ratio": round(k / max(1, k + m), 3),
                "slope_deg_wmean": round(slope_wmean, 2) if slope_wmean is not None else None,
                "slope_deg_med": round(slope_med, 2) if slope_med is not None else None,
                "psd_rms": round(psd, 3) if psd is not None else None,
                "horiz_off_med": round(float(np.median(offs)), 2) if offs else None,
                "horiz_matched": len(offs), "horiz_unmatched": unm,
            })
            for i, s in enumerate(sup):
                faces.append({"bid": bid, "arm": arm, "face": i,
                              "n_als": s["n_als"], "resid_abs": s["resid_abs"],
                              "supported": s["supported"],
                              "slope_deg": round(angles[i], 2) if i < len(angles) and angles[i] is not None else None})
    if rows:
        with open(LEV / "d12_defect.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        with open(LEV / "d12_defect_faces.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(faces[0].keys())); w.writeheader(); w.writerows(faces)
        print(f"[done] {len(rows)} (bldg,arm) rows, {len(faces)} facet rows -> {LEV}/d12_defect.csv")
        # quick summary
        import collections
        byarm = collections.defaultdict(list)
        for r in rows:
            byarm[r["arm"]].append(r)
        for arm, rs in byarm.items():
            hv = [r["height_resid"] for r in rs if r["height_resid"] is not None]
            sv = [r["slope_deg_med"] for r in rs if r["slope_deg_med"] is not None]
            print(f"  {arm}: n={len(rs)} | height_resid med={np.median(hv):.2f} | slope_med={np.median(sv):.1f}deg")
    else:
        print("[warn] no rows — check arm Roofer Solids exist on disk")


if __name__ == "__main__":
    main()
