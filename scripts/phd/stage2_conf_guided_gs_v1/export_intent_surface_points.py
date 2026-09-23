"""Export the rendered surface that the intent table counts as 3D points, together with the two input surfaces (prior and
photo) at the same pixels, for the 3D viewer (jointbuildgs:dev, CPU). scientific_verdict: null.

  python export_intent_surface_points.py [--sample 400000]
Mounts: /s2 (payload, rw).

Per setting (prior x scene) one uniform random sample of the table pixels (target building: 6 roof + 12 wall faces; the 15
cameras at training resolution; classes from the stage-1 inputs only) is drawn once and shared by every condition of the
setting and by the input file: record i of each file is the same pixel. Calibrated K, the renderer's pixel convention
u = fx x/z + cx. Classes (I is read with the setting's prior):
  class    1 agree (A=1, |M-P| <= tau_p) / 2 conflict (A=1, > tau_p) / 3 unobserved (A=0)
surface_<setting>_<cond>.bin   magic JBSP3D2, uint32 count, uint32 floats per point (= 13), float32 records:
  xyz          render depth D of the condition lifted along the pixel ray (NaN where it renders nothing)
  rgb          rendered colour
  class, followed (agree/unobserved |D-P| <= tau_p, conflict |D-M| <= tau_p), herr = (G - D) f (+ = result above GT,
  walls outward; NaN without GT), region (1 roof, 2 wall), view index,
  res_photo = (M - D) f, res_prior = (P - D) f   (+ = result above / outside the photo surface / the prior; metres,
                                                   vertical on roofs, along the face normal on walls; NaN if absent)
inputs_<setting>.bin           magic JBIN3D2, uint32 count, uint32 floats per point (= 14), float32 records:
  prior xyz (P lifted), photo xyz (M lifted; NaN where A=0), prior_photo = (M - P) f (+ = prior above / outside the photo
  surface; NaN where A=0), class, region, stick end xyz = photo point + prior_photo along the table's distance direction
  (vertical on roof-like faces; on wall-like faces the face's horizontal normal turned towards the camera; NaN where A=0),
  photo_gt = (G - M) f, prior_gt = (G - P) f (+ = the input above / outside GT; NaN without GT or photo)
surface_index.json             full-table numbers per file / region / class (n, share, followed, median |D-G| f) over all
                               pixels (not the sample; = eval intent table), plus the input file of each setting.
views.json                     the 15 photo names in view-index order."""
import os
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2")
MAPS = S2 / "inputs/maps"
OUT = S2 / "dashboard/surfels"
SPARSE = Path("/artifacts/JointBuildGS/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt")
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
MAGIC, FPP = b"JBSP3D2\0", 13
MAGIC_IN, FPI = b"JBIN3D2\0", 14
WALL_NZ = 0.5                                                           # as prepare_stage2_inputs --conversion
TRAIN = (1600, 1157)

ap = argparse.ArgumentParser()
ap.add_argument("--sample", type=int, default=400_000)
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


calib = json.loads((S2 / "runs/P_M_N/scene/jbgs_calibration.json").read_text())["images"]
CAMS = {}
for line in (SPARSE / "images.txt").read_text().splitlines():
    t = line.split()
    if len(t) >= 10 and not line.startswith("#") and t[9].lower().endswith(".jpg"):
        name = Path(t[9]).stem
        CAMS[name] = dict(R=q2R([float(v) for v in t[1:5]]), t=np.array([float(v) for v in t[5:8]]), K=np.array(calib[name]["K"]))
VIEWS = sorted(CAMS)
PJ = json.loads(Path("/artifacts/JointBuildGS/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/"
                     "inputs/lod2_polygons.json").read_text())["polygons"]
NORMAL = np.zeros((max(p["poly_index"] for p in PJ) + 2, 3), np.float64)
for pp in PJ:
    NORMAL[pp["poly_index"]] = pp["normal"]


def load(setname, view, dtype=np.float32):
    p = MAPS / setname / "raw_depth" / f"{view}.npy"
    x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
    return cv2.resize(x.astype(np.float32), TRAIN, interpolation=cv2.INTER_NEAREST).astype(dtype)


def lift(view, ys, xs, d):
    cam = CAMS[view]; K = cam["K"]
    Xc = np.stack([(xs - K[0, 2]) / K[0, 0] * d, (ys - K[1, 2]) / K[1, 1] * d, d], 1)
    return (Xc - cam["t"]) @ cam["R"]                                     # R^T (Xc - t)


def write(path, magic, fpp, rec):
    with path.open("wb") as f:
        f.write(magic); f.write(np.uint32(rec.shape[0]).tobytes()); f.write(np.uint32(fpp).tobytes())
        rec.astype(np.float32).tofile(f)


rng = np.random.default_rng(0)
index = {}
for setting, conds in SETTINGS.items():
    prior, scene = setting.split("_")
    pset, tset = f"prior_{prior}_{scene}", f"tau_{prior}"
    inp = {}                                                              # per view: maps of the inputs
    cand = []
    for vi, view in enumerate(VIEWS):
        A, M, P, T, G, FV = (load(s, view) for s in ("conf", "mvs", pset, tset, GT_SET, "fvert"))
        F = load("faceid", view, np.int32)
        region = np.where(np.isin(F, ROOF), 1, np.where(np.isin(F, WALL), 2, 0)).astype(np.int8)
        base = (region > 0) & np.isfinite(P) & (P > 0) & np.isfinite(T)
        hasM = np.isfinite(M) & (M > 0)
        cls = np.zeros(F.shape, np.int8)
        cls[base & (A > 0) & hasM & (np.abs(M - P) <= T)] = 1
        cls[base & (A > 0) & hasM & (np.abs(M - P) > T)] = 2
        cls[base & (A <= 0)] = 3
        inp[view] = dict(A=A, M=M, P=P, T=T, G=G, FV=FV, region=region, cls=cls, hasM=hasM, F=F)
        ys, xs = np.nonzero(cls > 0)
        cand.append(np.stack([np.full(ys.size, vi), ys, xs], 1))
    cand = np.concatenate(cand)
    sel = cand[np.sort(rng.choice(cand.shape[0], size=min(a.sample, cand.shape[0]), replace=False))]
    by_view = {vi: sel[sel[:, 0] == vi] for vi in range(len(VIEWS))}

    # input surfaces at the sampled pixels
    rec = []
    for vi, view in enumerate(VIEWS):
        s = by_view[vi]; ys, xs = s[:, 1], s[:, 2]; m = inp[view]
        P, M, FV = m["P"][ys, xs], m["M"][ys, xs], m["FV"][ys, xs]
        meas = (m["A"][ys, xs] > 0) & m["hasM"][ys, xs]
        r = np.full((ys.size, FPI), np.nan, np.float32)
        r[:, 0:3] = lift(view, ys, xs, P)
        r[meas, 3:6] = lift(view, ys[meas], xs[meas], M[meas])
        r[meas, 6] = ((M - P) * FV)[meas]
        r[:, 7] = m["cls"][ys, xs]; r[:, 8] = m["region"][ys, xs]
        # stick: from the photo point, the prior's distance along the table's direction (vertical / wall normal to the camera)
        n = NORMAL[np.clip(m["F"][ys, xs], 0, NORMAL.shape[0] - 1)]
        wall = np.abs(n[:, 2]) < WALL_NZ
        nh = n[:, :2] / np.maximum(np.linalg.norm(n[:, :2], axis=1, keepdims=True), 1e-9)
        cam_c = -CAMS[view]["R"].T @ CAMS[view]["t"]
        to_cam = cam_c[None, :2] - r[:, 3:5]
        nh *= np.where((nh * np.nan_to_num(to_cam)).sum(1, keepdims=True) < 0, -1, 1)
        dirv = np.where(wall[:, None], np.concatenate([nh, np.zeros((ys.size, 1))], 1), np.array([[0.0, 0.0, 1.0]]))
        r[meas, 9:12] = r[meas, 3:6] + r[meas, 6:7] * dirv[meas]
        G = m["G"][ys, xs]; hasG = np.isfinite(G) & (G > 0)
        r[meas & hasG, 12] = ((G - M) * FV)[meas & hasG]
        r[hasG, 13] = ((G - P) * FV)[hasG]
        rec.append(r)
    write(OUT / f"inputs_{setting}.bin", MAGIC_IN, FPI, np.concatenate(rec))
    # the table's class shares and source errors over all pixels (not the sample), for the 1:1 read-out of the viewer
    itab = {}
    for reg, rname in ((1, "roof"), (2, "wall")):
        tot = sum(int(((inp[v]["region"] == reg) & (inp[v]["cls"] > 0)).sum()) for v in VIEWS)
        for k, kname in ((1, "agree"), (2, "conflict"), (3, "unobserved")):
            n_, eph, epr = 0, [], []
            for v in VIEWS:
                m = inp[v]; mm = (m["region"] == reg) & (m["cls"] == k); g = mm & np.isfinite(m["G"]) & (m["G"] > 0)
                n_ += int(mm.sum())
                epr.append((np.abs(m["P"] - m["G"]) * m["FV"])[g]); eph.append((np.abs(m["M"] - m["G"]) * m["FV"])[g & m["hasM"]])
            med = lambda x: float(np.median(np.concatenate(x))) if sum(len(y) for y in x) else None  # noqa: E731
            itab.setdefault(rname, {})[kname] = dict(n=n_, share=n_ / tot if tot else None, err_photos=med(eph), err_prior=med(epr))
    index[f"{setting}/_inputs"] = dict(file=f"inputs_{setting}.bin", total=int(cand.shape[0]), table=itab)

    for cond in conds:
        rec, stats = [], {}
        for vi, view in enumerate(VIEWS):
            D = np.load(S2 / "eval" / cond / "render_30000" / f"{view}_depth.npy")
            rgb = cv2.cvtColor(cv2.imread(str(S2 / "eval" / cond / "render_30000" / f"{view}_rgb.png")), cv2.COLOR_BGR2RGB)
            m = inp[view]; A, M, P, T, G, FV, cls = m["A"], m["M"], m["P"], m["T"], m["G"], m["FV"], m["cls"]
            # full-table statistics (all pixels; the table's base also needs a rendered depth)
            ok = (cls > 0) & (D > 0)
            fol_all = np.where(cls == 2, np.abs(D - M) <= T, np.abs(D - P) <= T)
            err_all = np.abs(G - D) * FV
            for reg in (1, 2):
                for k in (1, 2, 3):
                    mm = ok & (m["region"] == reg) & (cls == k)
                    st = stats.setdefault(f"{reg}_{k}", dict(n=0, fol=0, err=[]))
                    st["n"] += int(mm.sum()); st["fol"] += int((mm & fol_all).sum())
                    e = err_all[mm & np.isfinite(G) & (G > 0)]; st["err"].append(e[np.isfinite(e)])
            # sampled pixels
            s = by_view[vi]; ys, xs = s[:, 1], s[:, 2]
            d = D[ys, xs]; c = cls[ys, xs]; rend = d > 0
            r = np.full((ys.size, FPP), np.nan, np.float32)
            r[rend, 0:3] = lift(view, ys[rend], xs[rend], d[rend])
            r[:, 3:6] = rgb[ys, xs] / 255.0
            r[:, 6] = c
            r[:, 7] = np.where(rend, np.where(c == 2, np.abs(d - M[ys, xs]) <= T[ys, xs], np.abs(d - P[ys, xs]) <= T[ys, xs]), 0)
            g = G[ys, xs]
            r[:, 8] = np.where(rend & np.isfinite(g) & (g > 0), (g - d) * FV[ys, xs], np.nan)
            r[:, 9] = m["region"][ys, xs]; r[:, 10] = vi
            mp = rend & (A[ys, xs] > 0) & m["hasM"][ys, xs]
            r[mp, 11] = ((M[ys, xs] - d) * FV[ys, xs])[mp]
            r[rend, 12] = ((P[ys, xs] - d) * FV[ys, xs])[rend]
            rec.append(r)
        fname = f"surface_{setting}_{cond}.bin"
        rec = np.concatenate(rec)
        write(OUT / fname, MAGIC, FPP, rec)
        table = {}
        for reg, rname in ((1, "roof"), (2, "wall")):
            tot = sum(stats[f"{reg}_{k}"]["n"] for k in (1, 2, 3))
            for k, kname in ((1, "agree"), (2, "conflict"), (3, "unobserved")):
                st = stats[f"{reg}_{k}"]; e = np.concatenate(st["err"]) if st["err"] else np.zeros(0)
                table.setdefault(rname, {})[kname] = dict(n=st["n"], share=st["n"] / tot if tot else None,
                                                          followed=st["fol"] / st["n"] if st["n"] else None,
                                                          err=float(np.median(e)) if e.size else None)
        index[f"{setting}/{cond}"] = dict(file=fname, inputs=f"inputs_{setting}.bin", points=int(rec.shape[0]),
                                          total=int(cand.shape[0]), table=table)
        print(setting, cond, rec.shape[0], "of", cand.shape[0],
              {rr: {k: round(v["followed"], 3) for k, v in t.items() if v["followed"] is not None} for rr, t in table.items()}, flush=True)
(OUT / "surface_index.json").write_text(json.dumps(index, indent=1))
(OUT / "views.json").write_text(json.dumps(VIEWS))                          # view index -> photo name
print("wrote", OUT)
