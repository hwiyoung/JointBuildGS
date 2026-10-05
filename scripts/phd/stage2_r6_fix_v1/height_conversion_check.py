"""Section 5 of PHD-STAGE2-R6-FIX-v1 (jointbuildgs:dev, CPU, no training): is the height conversion that stage 1 used to
measure the tolerance the same as the stage-2 conversion f_p, and what tolerance does each give on the same samples?

  python height_conversion_check.py      # mounts: /s1 (stage-1 folder, ro), /s2 (stage-2 payload, ro), /r6 (rw)

Samples = the stage-1 tolerance pool of scripts/phd/stage1_verify_v2/verify_v2.py (nominal scene, 15 views, full
resolution): A = 1, prior depth valid, target-roof pixels (region code 1 of the face-id render); r = MVS - prior (camera Z).
Conversion 1 (stage 1, verify_v2.py:127-133): vfac = |n.d| / |n_z| on LoD2 faces with |n_z| > 1e-6, |d_z| elsewhere.
Conversion 2 (stage 2): the saved per-pixel map inputs/maps/fvert (prepare_stage2_inputs.py:65-72: |n.d|/|n_z| if
|n_z| >= 0.5, |n.d| on wall-like faces, |d_z| off LoD2 faces).
Tolerance = 2.5 x s2 of the two-pass NMAD statistics (verify_v2.py two_pass, k = 2.5, 3-sigma cut). Also reported: the
largest |vfac - fvert| on the pool and on the wall pixels (outside the pool)."""
import json
from pathlib import Path

import numpy as np

S1, S2, OUT = Path("/s1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"), Path("/s2"), Path("/r6/height_check")
V2 = Path("/s1/PHD-STAGE1-VERIFY-v2")
OUT.mkdir(parents=True, exist_ok=True)
SPARSE = Path("/artifacts/JointBuildGS/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt")
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
Z = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz")
region_code = Z["poly_region_code"]
poly_normal = np.zeros((len(region_code), 3), np.float32)
for p in PJ["polygons"]:
    poly_normal[p["poly_index"]] = p["normal"]


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


def two_pass(x, k=2.5, sig=3.0, nmad=1.4826):
    x = np.asarray(x, np.float64); x = x[np.isfinite(x)]
    m = float(np.median(x)); s = float(nmad * np.median(np.abs(x - m)))
    keep = np.abs(x - m) <= sig * s
    m2 = float(np.median(x[keep])); s2 = float(nmad * np.median(np.abs(x[keep] - m2)))
    return dict(n=int(x.size), m2=m2, s2=s2, tau=k * s2)


cams = {}
for l in (SPARSE / "cameras.txt").read_text().splitlines():
    if l.strip() and not l.startswith("#"):
        t = l.split(); cams[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(v) for v in t[4:]])
imgs = {}
for l in (SPARSE / "images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        imgs[Path(t[9]).stem] = dict(q=[float(v) for v in t[1:5]], cam=int(t[8]))
stems = sorted(imgs)
res = {}
for prior in ("L", "M"):
    rv1, rv2 = [], []
    dmax_pool, dmax_wall, n_wall = 0.0, 0.0, 0
    for stem in stems:
        cam = cams[imgs[stem]["cam"]]; fx, fy, cx, cy = cam["p"]; W, H = cam["W"], cam["H"]; R = q2R(imgs[stem]["q"])
        A = np.load(S1 / "out/conf" / f"{stem}_conf.npy")
        mvs = np.load(S1 / "inputs/mvs_full" / f"{stem}_depth.npy")
        poly = np.load(V2 / "inputs_v2/faceid" / f"{stem}.npy")
        roof = np.where(poly >= 0, region_code[np.maximum(poly, 0)], 0) == 1
        xn = (np.arange(W) + 0.5 - cx) / fx; yn = (np.arange(H) + 0.5 - cy) / fy
        d = [(R[0, k] * xn[None, :] + R[1, k] * yn[:, None] + R[2, k]).astype(np.float32) for k in range(3)]
        nrm = poly_normal[np.maximum(poly, 0)]
        nd = np.abs(nrm[..., 0] * d[0] + nrm[..., 1] * d[1] + nrm[..., 2] * d[2]); nz = np.abs(nrm[..., 2])
        vfac = np.where((poly >= 0) & (nz > 1e-6), nd / np.maximum(nz, 1e-6), np.abs(d[2])).astype(np.float32)
        fvert = np.load(S2 / "inputs/maps/fvert/raw_depth" / f"{stem}.npy").astype(np.float32)
        pd = np.load(V2 / f"inputs_v2/prior_render/{prior}_nominal/lod2_prior/raw_depth/{stem}.npy").astype(np.float32)
        ok = np.isfinite(pd) & (pd > 0) & (pd < 1e6)
        pool = (A == 1) & ok & roof
        r = (mvs - pd)[pool]
        rv1.append(r * vfac[pool]); rv2.append(r * fvert[pool])
        dmax_pool = max(dmax_pool, float(np.abs(vfac[pool] - fvert[pool]).max()) if pool.any() else 0.0)
        wall = (poly >= 0) & (nz < 0.5)
        if wall.any():
            dmax_wall = max(dmax_wall, float(np.abs(vfac[wall] - fvert[wall]).max())); n_wall += int(wall.sum())
        del A, mvs, poly, d, nrm, nd, nz, vfac, fvert, pd
    s1, s2 = two_pass(np.concatenate(rv1)), two_pass(np.concatenate(rv2))
    res[prior] = dict(stage1_conversion=s1, stage2_conversion=s2, tau_rel_diff=abs(s1["tau"] - s2["tau"]) / s1["tau"],
                      max_abs_factor_diff_pool=dmax_pool, max_abs_factor_diff_wall_pixels=dmax_wall, wall_pixels=n_wall,
                      handover_tau=json.loads((S2 / "inputs/prepare_report.json").read_text())["tau_v"][prior])
    print(prior, json.dumps(res[prior]), flush=True)
(OUT / "height_conversion_check.json").write_text(json.dumps(dict(results=res, pool="A=1, prior valid, target roof (region code 1), nominal, 15 views, full resolution",
                                                                  scientific_verdict=None), indent=1))
