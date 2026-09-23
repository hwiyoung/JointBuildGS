"""Per-source depth maps of the stage-2 inputs, to look at each source once (jointbuildgs:dev, CPU). scientific_verdict: null.

  python make_depth_qa.py [--views ...] [--width 800]
Mounts: /s2 (payload, rw for dashboard/intent/ and eval/), /artifacts/JointBuildGS (ro).

Per selected view, at the training resolution the table uses (maps resized nearest-neighbour): the camera depth of each
source on one colour scale per view - photo MVS (only where A=1; A=0 in purple), LoD2 prior (normal / +1 m scene), ALS prior
(normal / +1 m), GT (the evaluation cloud projected with a z-buffer: only the pixels a point falls on; magenta = a GT point
more than 0.3 m behind the photo surface, i.e. from a surface hidden behind it) - and each source minus the photo surface in
the table's units (vertical on roofs, face normal on walls, + = the source above / outside; +-0.5 m). Target building pixels
only (6 roof + 12 wall faces); the rest of the photo dimmed.
Outputs: dashboard/intent/depth_<view>_<kind>.jpg and eval/depth_qa_30000.csv (per source over all 15 views: coverage of the
target pixels, median source - photo, share beyond tau, GT points from hidden surfaces)."""
import os
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; OUT = S2 / "dashboard/intent"
PHOTOS = Path("/artifacts/JointBuildGS/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images")
TRAIN = (1600, 1157)
SOURCES = {"lod2_N": ("prior_M_N", "tau_M"), "lod2_B": ("prior_M_B", "tau_M"), "als_N": ("prior_L_N", "tau_L"), "als_B": ("prior_L_B", "tau_L"),
           "gt": (GT_SET, "tau_M")}
ap = argparse.ArgumentParser()
ap.add_argument("--views", nargs="+", default=["DJI_20241217101305_0005_D", "DJI_20241217101313_0009_D", "DJI_20241217101343_0024_D",
                                                "DJI_20241217101359_0032_D", "DJI_20241217101259_0002_D", "DJI_20241217101327_0016_D"])
ap.add_argument("--width", type=int, default=800)
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
faces = json.loads((MAPS / "faces.json").read_text())
TGT = [int(f) for f in faces["roof"] + faces["wall"]]
ALL = sorted(p.stem for p in (MAPS / "conf/raw_depth").glob("*.npy"))


def load(setname, view, dtype=np.float32):
    p = MAPS / setname / "raw_depth" / f"{view}.npy"
    x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
    return cv2.resize(x.astype(np.float32), TRAIN, interpolation=cv2.INTER_NEAREST).astype(dtype)


def save(img, name):
    h = int(round(img.shape[0] * a.width / img.shape[1]))
    cv2.imwrite(str(OUT / name), cv2.cvtColor(cv2.resize(img, (a.width, h), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 88])


def diverging(err, vmax=0.5):
    x = np.clip(err / vmax, -1, 1)
    r = np.where(x >= 0, 255, 255 * (1 + x)); b = np.where(x <= 0, 255, 255 * (1 - x)); g = 255 * (1 - np.abs(x))
    return np.stack([r, g, b], -1).astype(np.uint8)


stats = {k: dict(tgt=0, valid=0, diff=[], beyond=0, nd=0, hidden=0, ng=0) for k in list(SOURCES) + ["mvs"]}
for view in ALL:
    A, M, FV = load("conf", view), load("mvs", view), load("fvert", view)
    F = load("faceid", view, np.int32); tgt = np.isin(F, TGT)
    meas = tgt & (A > 0) & np.isfinite(M) & (M > 0)
    s = stats["mvs"]; s["tgt"] += int(tgt.sum()); s["valid"] += int(meas.sum())
    maps = {k: (load(src, view), load(tau, view)) for k, (src, tau) in SOURCES.items()}
    for k, (X, T) in maps.items():
        s = stats[k]; ok = tgt & np.isfinite(X) & (X > 0)
        s["tgt"] += int(tgt.sum()); s["valid"] += int(ok.sum())
        both = ok & meas
        d = ((M - X) * FV)[both]
        s["diff"].append(d); s["nd"] += int(both.sum())
        s["beyond"] += int((np.abs(M - X) > T)[both].sum()) if k != "gt" else 0
        if k == "gt":
            s["ng"] += int(both.sum()); s["hidden"] += int((((X - M) * FV)[both] > 0.3).sum())
    if view not in a.views:
        continue
    photo = cv2.resize(cv2.cvtColor(cv2.imread(str(next(PHOTOS.glob(f"{view}.*")))), cv2.COLOR_BGR2RGB), TRAIN, interpolation=cv2.INTER_AREA)
    base = (cv2.cvtColor(photo, cv2.COLOR_RGB2GRAY)[..., None].repeat(3, -1) * 0.35).astype(np.float32)
    lo, hi = np.percentile(M[meas], [2, 98]) if meas.any() else (0, 1)

    def depth_img(X, mask, extra=None):
        img = base.copy()
        v = np.clip((X - lo) / max(hi - lo, 1e-6), 0, 1)
        col = cv2.cvtColor(cv2.applyColorMap((255 * (1 - v)).astype(np.uint8), cv2.COLORMAP_TURBO), cv2.COLOR_BGR2RGB)
        img[mask] = col[mask]
        if extra is not None:
            for m, c in extra:
                img[m] = c
        return img.astype(np.uint8)

    save(depth_img(M, meas, [(tgt & ~meas, (156, 39, 176))]), f"depth_{view}_mvs.jpg")
    for k, (X, T) in maps.items():
        ok = tgt & np.isfinite(X) & (X > 0)
        extra = None
        if k == "gt":
            hid = ok & meas & (((X - M) * FV) > 0.3)
            big = cv2.dilate(ok.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0          # sparse points: 2 px for visibility
            Xd = cv2.dilate(np.where(ok, X, 0).astype(np.float32), np.ones((2, 2), np.uint8))
            hidd = cv2.dilate(hid.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0
            save(depth_img(Xd, big & tgt, [(hidd & tgt, (255, 0, 255))]), f"depth_{view}_{k}.jpg")
            dimg = base.copy(); dm = big & tgt & (cv2.dilate(meas.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0)
            Md = cv2.dilate(np.where(meas, M, 0).astype(np.float32), np.ones((2, 2), np.uint8))
            dimg[dm] = diverging(((Md - Xd) * FV)[dm]); dimg[hidd & tgt] = (255, 0, 255)
            save(dimg.astype(np.uint8), f"depth_{view}_d_{k}.jpg")
            continue
        save(depth_img(X, ok), f"depth_{view}_{k}.jpg")
        dimg = base.copy(); both = ok & meas
        dimg[both] = diverging(((M - X) * FV)[both]); dimg[tgt & ok & ~meas] = (156, 39, 176)
        save(dimg.astype(np.uint8), f"depth_{view}_d_{k}.jpg")
    print("images", view, flush=True)

rows = []
for k, s in stats.items():
    d = np.concatenate(s["diff"]) if s["diff"] else np.zeros(0)
    rows.append(dict(source=k, target_pixels=s["tgt"], coverage=s["valid"] / max(s["tgt"], 1),
                     median_source_minus_photo_cm=round(float(np.median(d)) * 100, 1) if d.size else None,
                     share_beyond_tau=(s["beyond"] / s["nd"]) if (s["nd"] and k not in ("gt", "mvs")) else None,
                     gt_hidden_surface_share=(s["hidden"] / s["ng"]) if k == "gt" and s["ng"] else None))
    print(rows[-1], flush=True)
with (S2 / "eval/depth_qa_30000.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
(OUT / "depth_qa.js").write_text("window.DEPTHQA = " + json.dumps(dict(rows=rows, views=a.views)) + ";\n")
print("done")
