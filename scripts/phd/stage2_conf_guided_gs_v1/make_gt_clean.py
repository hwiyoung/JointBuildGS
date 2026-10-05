"""Cleaned GT depth maps for the stage-2 evaluation (jointbuildgs:dev, CPU). scientific_verdict: null.

  python make_gt_clean.py [--k 9] [--behind 0.3]
Mounts: /s2 (payload, rw for inputs/maps/gt_clean/), /artifacts/JointBuildGS (ro).

prepare_stage2_inputs.py projects the GT evaluation cloud into each view with a per-pixel z-buffer. Two defects were measured
on 2026-09-25 (eval/anatomy_photo_vs_gt_30000.csv and the see-through check):
  1. hidden points - about 21 % of the roof pixels with a GT value take a point of a surface hidden behind the roof
     (courtyard, far walls; median 12 m behind): at full resolution the cloud is sparse, so a pixel no roof point falls on
     takes whatever point projects there;
  2. a vertical offset between the GT cloud and the scene frame (photo surface - GT: roof agree -9.4 cm, open ground -6.6 cm,
     wall horizontal -2 to -4 cm).
Here, (a) visibility: a GT depth is dropped when it lies more than --behind m behind the nearest GT depth within a --k x --k
window (full resolution); (b) datum: the cloud is shifted vertically by the median photo - GT height on open ground (no LoD2
face, photo-measured, the photo point within [-1.5, 1.0] m of the front-wall base), estimated with (a) applied. The ground is
not part of the evaluated building, so the shift does not use the surfaces under evaluation. The shifted cloud is projected
again with (a).
Outputs: inputs/maps/gt_clean/raw_depth/<view>.npy (full resolution, camera depth, NaN = no GT) and
inputs/maps/gt_clean/receipt.json (shift, parameters, per-view counts, checks)."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d

S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; OUT = MAPS / "gt_clean"
ART = Path("/artifacts/JointBuildGS")
COND = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions"
SPARSE, GTPLY = COND / "B+1.0/scene/sparse_txt", COND / "N/evaluation/gt_cropped.ply"
PJ = {p["poly_index"]: p for p in json.loads((ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/"
                                                       "inputs/lod2_polygons.json").read_text())["polygons"]}
TRAIN = (1600, 1157)
ap = argparse.ArgumentParser()
ap.add_argument("--k", type=int, default=9)
ap.add_argument("--behind", type=float, default=0.3)
a = ap.parse_args()
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


cams = {}
for line in (SPARSE / "cameras.txt").read_text().splitlines():
    t = line.split()
    if t and not line.startswith("#"):
        cams[t[0]] = dict(W=int(t[2]), H=int(t[3]), p=[float(v) for v in t[4:8]])
VIEWS = {}
for line in (SPARSE / "images.txt").read_text().splitlines():
    t = line.split()
    if len(t) >= 10 and not line.startswith("#") and t[9].lower().endswith(".jpg"):
        VIEWS[Path(t[9]).stem] = dict(R=q2R([float(v) for v in t[1:5]]), t=np.array([float(v) for v in t[5:8]]), cam=t[8])
gt0 = np.asarray(o3d.io.read_point_cloud(str(GTPLY)).points)


def project(gt, stem):
    """Per-pixel z-buffer, as prepare_stage2_inputs.py, then the visibility filter. Returns (raw, filtered)."""
    v = VIEWS[stem]; c = cams[v["cam"]]; fx, fy, cx, cy = c["p"]; W, H = c["W"], c["H"]
    Xc = gt @ v["R"].T + v["t"]; z = Xc[:, 2]
    u = np.floor(fx * Xc[:, 0] / z + cx).astype(np.int64); vv = np.floor(fy * Xc[:, 1] / z + cy).astype(np.int64)
    ins = (z > 0) & (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
    d = np.full((H, W), np.inf, np.float32)
    np.minimum.at(d.reshape(-1), vv[ins] * W + u[ins], z[ins].astype(np.float32))
    near = cv2.erode(d, np.ones((a.k, a.k), np.uint8))                     # nearest GT depth in the window (inf = none)
    keep = np.isfinite(d) & (d <= near + a.behind)
    raw = np.where(np.isfinite(d), d, np.nan).astype(np.float32)
    return raw, np.where(keep, d, np.nan).astype(np.float32)


def small(x):
    return cv2.resize(x, TRAIN, interpolation=cv2.INTER_NEAREST)


def load(setname, stem, dtype=np.float32):
    p = MAPS / setname / "raw_depth" / f"{stem}.npy"
    return small(np.load(p if p.exists() else MAPS / setname / f"{stem}.npy").astype(np.float32)).astype(dtype)


calib = json.loads((S2 / "runs/P_M_N/scene/jbgs_calibration.json").read_text())["images"]
samples = np.load(S2 / "inputs/points/prior_M_N.npz")["xyz"].astype(np.float64)
r3 = np.array(PJ[3403]["ring_local_xy"]); n3 = np.array(PJ[3403]["normal"])[:2]; n3 /= np.linalg.norm(n3); c3 = r3.mean(0)
rel = samples[:, :2] - c3
Z0 = float(samples[(np.abs(rel @ np.array([-n3[1], n3[0]])) < 20) & (np.abs(rel @ n3) < 0.3), 2].min())


def photo_minus_gt(gtmaps):
    """Median photo - GT (m) on open ground (vertical), target roof agree pixels (vertical) and the front wall (normal)."""
    out = {"ground": [], "roof_agree": [], "wall": [], "hidden": [0, 0]}
    for stem in VIEWS:
        G = small(gtmaps[stem]); A, M, P, T, FV = (load(s, stem) for s in ("conf", "mvs", "prior_M_N", "tau_M", "fvert"))
        F = load("faceid", stem, np.int32)
        v = VIEWS[stem]; K = np.array(calib[stem]["K"])
        hasM, hasG = np.isfinite(M) & (M > 0), np.isfinite(G) & (G > 0)
        ys, xs = np.mgrid[0:TRAIN[1], 0:TRAIN[0]]
        r = np.stack([(xs - K[0, 2]) / K[0, 0], (ys - K[1, 2]) / K[1, 1], np.ones(xs.shape)], -1)
        rw = r @ v["R"]                                                   # world direction per unit camera depth (R^T r)
        Xw = rw * np.where(hasM, M, 0)[..., None] + (-v["R"].T @ v["t"])   # photo point = camera centre + depth * direction
        zrel = Xw[..., 2] - Z0
        g = (F < 0) & (A > 0) & hasM & hasG & (zrel > -1.5) & (zrel < 1.0)
        out["ground"].append(((G - M) * np.abs(rw[..., 2]))[g])
        agree = np.isin(F, ROOF) & (A > 0) & hasM & hasG & np.isfinite(P) & (np.abs(M - P) <= T)
        out["roof_agree"].append(((G - M) * FV)[agree])
        w = (F == 3403) & (A > 0) & hasM & hasG
        out["wall"].append(((G - M) * FV)[w])
        roof = np.isin(F, ROOF) & (A > 0) & hasM & hasG
        out["hidden"][0] += int(roof.sum()); out["hidden"][1] += int((((G - M) * FV)[roof] > 0.3).sum())
    res = {k: float(np.median(np.concatenate(v))) for k, v in out.items() if k != "hidden"}
    res["roof_gt_behind_30cm_share"] = out["hidden"][1] / max(out["hidden"][0], 1)
    return res


# pass 1: visibility only, to estimate the datum shift on open ground
raw, filt = {}, {}
for stem in VIEWS:
    raw[stem], filt[stem] = project(gt0, stem)
    print("pass 1", stem, "GT px", int(np.isfinite(raw[stem]).sum()), "kept", int(np.isfinite(filt[stem]).sum()), flush=True)
before = photo_minus_gt(raw)
vis_only = photo_minus_gt(filt)
shift = vis_only["ground"]                               # photo - GT on the ground: move the cloud by this much in z
print("photo - GT before:", before, "| with visibility:", vis_only, "| shift the cloud by %+.4f m in z" % shift, flush=True)

# pass 2+: shifted cloud, visibility filter; re-projecting moves points between pixels, so the ground residual is measured
# again and added to the shift until it is below 2 mm (at most 4 rounds)
(OUT / "raw_depth").mkdir(parents=True, exist_ok=True)
history = []
for it in range(4):
    gt1 = gt0.copy(); gt1[:, 2] += shift
    final, counts = {}, {}
    for stem in VIEWS:
        r_, f_ = project(gt1, stem)
        final[stem] = f_
        counts[stem] = dict(gt_px=int(np.isfinite(r_).sum()), kept_px=int(np.isfinite(f_).sum()))
    after = photo_minus_gt(final)
    history.append(dict(shift=shift, after=after))
    print(f"round {it + 1}: shift {shift:+.4f} m ->", after, flush=True)
    if abs(after["ground"]) < 0.002:
        break
    shift += after["ground"]
for stem, f_ in final.items():
    np.save(OUT / "raw_depth" / f"{stem}.npy", f_)
(OUT / "receipt.json").write_text(json.dumps(dict(
    schema="jointbuildgs.stage2.gt_clean.v1", scientific_verdict=None, source=str(GTPLY), k_px=a.k, behind_m=a.behind,
    datum_shift_z_m=shift, datum_reference="median photo - GT height on open ground (no LoD2 face, A=1, within [-1.5, 1.0] m of the front-wall base), visibility applied",
    front_wall_base_z=Z0, photo_minus_gt_m=dict(before=before, visibility_only=vis_only, after=after), rounds=history, views=counts), indent=1))
print("done")
