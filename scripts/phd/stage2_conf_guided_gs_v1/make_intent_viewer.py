"""Intent viewer data (jointbuildgs:dev, CPU): judgment-class maps, 'followed?' maps, height-error maps and the class table
for every prior (LoD2 M, ALS L) x scene (N, B) setting, written to /s2/dashboard/intent/ for the page intent.html
(served by the existing dashboard server, port 8887). scientific_verdict: null.

  python make_intent_viewer.py [--views ...] [--width 800]

Judgment classes (stage-1 inputs only, target roof + wall pixels, per condition's prior; I is read with each setting's prior):
  agree      A=1 and |M-P| <= tau_p   intended: keep the prior (photos agree)
  conflict   A=1 and |M-P| >  tau_p   intended: follow the photos
  unobserved A=0                      intended: keep the prior, right or wrong (the GT error there is the prior's own)
Followed: agree/unobserved |D-P| <= tau_p, conflict |D-M| <= tau_p (D = final render depth, camera depth).
Errors: |D-G|, |M-G|, |P-G| medians in metres (vertical on roofs, surface normal on walls), all 15 views; maps show the
signed render-minus-GT height with GT min-pooled over the pixel footprint (visual only), and the size of the disagreement
prior - photo (vertical / normal, + = prior above / outside) where the photos measured (A=1; A=0 in the unobserved colour)."""
import os
import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2")
MAPS = S2 / "inputs/maps"
OUT = S2 / "dashboard/intent"
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
TEST_VIEWS = {"DJI_20241217101259_0002_D", "DJI_20241217101327_0016_D"}
CLASS_RGB = {"agree": (66, 133, 244), "conflict": (255, 152, 0), "unobserved": (156, 39, 176)}

ap = argparse.ArgumentParser()
ap.add_argument("--views", nargs="+", default=["DJI_20241217101305_0005_D", "DJI_20241217101313_0009_D",
                                                "DJI_20241217101343_0024_D", "DJI_20241217101359_0032_D",
                                                "DJI_20241217101259_0002_D", "DJI_20241217101327_0016_D"])
ap.add_argument("--width", type=int, default=800)
ap.add_argument("--vmax", type=float, default=0.5)
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
ALL_VIEWS = sorted(p.stem for p in (MAPS / "conf/raw_depth").glob("*.npy"))
cache = {}


def load(setname, view, size, dtype=np.float32):
    key = (setname, view, size)
    if key not in cache:
        p = MAPS / setname / "raw_depth" / f"{view}.npy"
        x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
        cache[key] = cv2.resize(x.astype(np.float32), size, interpolation=cv2.INTER_NEAREST).astype(dtype)
    return cache[key]


def gt_minpool(view, size):
    key = ("gtmin", view, size)
    if key not in cache:
        p = MAPS / GT_SET / "raw_depth" / f"{view}.npy"
        g = np.load(p)
        ok = np.isfinite(g) & (g > 0)
        k = int(np.ceil(g.shape[1] / size[0])) + 2
        gm = cv2.resize(cv2.erode(np.where(ok, g, np.inf).astype(np.float32), np.ones((k, k), np.uint8)), size,
                        interpolation=cv2.INTER_NEAREST)
        gm[~np.isfinite(gm)] = np.nan
        cache[key] = gm
    return cache[key]


def classes(P, M, A, T, D):
    base = np.isfinite(P) & (P > 0) & np.isfinite(T)
    hasM = np.isfinite(M) & (M > 0)
    return {"agree": base & (A > 0) & hasM & (np.abs(M - P) <= T),
            "conflict": base & (A > 0) & hasM & (np.abs(M - P) > T),
            "unobserved": base & (A <= 0)}, hasM


def save(img, name):
    h = int(round(img.shape[0] * a.width / img.shape[1]))
    cv2.imwrite(str(OUT / name), cv2.cvtColor(cv2.resize(img, (a.width, h), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 88])


def diverging(err, vmax):
    x = np.clip(err / vmax, -1, 1)
    r = np.where(x >= 0, 255, 255 * (1 + x)); b = np.where(x <= 0, 255, 255 * (1 - x)); g = 255 * (1 - np.abs(x))
    return np.stack([r, g, b], -1).astype(np.uint8)


data = {"settings": {}, "views": [dict(name=v, test=v in TEST_VIEWS) for v in a.views], "vmax": a.vmax}
for setting, conds in SETTINGS.items():
    prior, scene = setting.split("_")
    pset, tset = f"prior_{prior}_{scene}", f"tau_{prior}"
    table = {}
    for cond in conds:
        rdir = S2 / "eval" / cond / "render_30000"
        acc = {}
        for v in ALL_VIEWS:
            D = np.load(rdir / f"{v}_depth.npy"); size = (D.shape[1], D.shape[0])
            A, M, P, T = load("conf", v, size), load("mvs", v, size), load(pset, v, size), load(tset, v, size)
            G, FV, F = load(GT_SET, v, size), load("fvert", v, size), load("faceid", v, size, np.int32)
            cls, hasM = classes(P, M, A, T, D)
            rend = D > 0
            for region, rm in (("roof", np.isin(F, ROOF)), ("wall", np.isin(F, WALL))):
                for k, m in cls.items():
                    m = m & rm & rend
                    r = acc.setdefault((region, k), dict(n=0, ok=0, dg=[], mg=[], pg=[]))
                    r["n"] += int(m.sum())
                    good = (np.abs(D - M) <= T) if k == "conflict" else (np.abs(D - P) <= T)
                    r["ok"] += int((m & good).sum())
                    g = m & np.isfinite(G) & (G > 0)
                    r["dg"].append((np.abs(D - G) * FV)[g]); r["pg"].append((np.abs(P - G) * FV)[g])
                    r["mg"].append((np.abs(M - G) * FV)[g & hasM])
        for (region, k), r in acc.items():
            med = lambda x: round(float(np.median(np.concatenate(x))), 4) if sum(len(y) for y in x) else None  # noqa: E731
            t = table.setdefault(region, {}).setdefault(k, {"n": r["n"], "err_photos": med(r["mg"]), "err_prior": med(r["pg"]), "cond": {}})
            t["cond"][cond] = {"followed": round(r["ok"] / r["n"], 4) if r["n"] else None, "err": med(r["dg"])}
        print(setting, cond, "table done", flush=True)
    for region, t in table.items():
        tot = sum(x["n"] for x in t.values())
        for x in t.values():
            x["share"] = round(x["n"] / tot, 4) if tot else None
    data["settings"][setting] = {"conds": conds, "table": table}

    # ---- images for the selected views
    for v in a.views:
        photo = cv2.cvtColor(cv2.imread(str(S2 / "eval" / conds[0] / "render_30000" / f"{v}_rgb.png")), cv2.COLOR_BGR2RGB)
        H, W = photo.shape[:2]; size = (W, H)
        native = next(Path("/artifacts/JointBuildGS/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images").glob(f"{v}.*"))
        photo = cv2.resize(cv2.cvtColor(cv2.imread(str(native)), cv2.COLOR_BGR2RGB), size, interpolation=cv2.INTER_AREA)
        A, M, P, T = load("conf", v, size), load("mvs", v, size), load(pset, v, size), load(tset, v, size)
        F, FV = load("faceid", v, size, np.int32), load("fvert", v, size)
        tgt = np.isin(F, ROOF + WALL)
        D0 = np.load(S2 / "eval" / conds[0] / "render_30000" / f"{v}_depth.npy")
        cls, hasM = classes(P, M, A, T, D0)
        img = photo.astype(np.float32) * 0.45
        for k, m in cls.items():
            m = m & tgt
            img[m] = 0.35 * photo[m] + 0.65 * np.array(CLASS_RGB[k], np.float32)
        save(img.astype(np.uint8), f"{setting}_{v}_classes.jpg")
        # size of the disagreement: prior - photo (+ = prior above the photo surface, walls: outside), where the photos measured
        spm = (M - P) * FV
        meas = tgt & (A > 0) & hasM & np.isfinite(P) & (P > 0)
        sz = photo.astype(np.float32).mean(-1, keepdims=True).repeat(3, -1) * 0.45
        sz[meas] = diverging(spm[meas], a.vmax)
        blind = tgt & (A <= 0)
        sz[blind] = 0.35 * sz[blind] + 0.65 * np.array(CLASS_RGB["unobserved"], np.float32)
        save(sz.astype(np.uint8), f"{setting}_{v}_size.jpg")
        G = gt_minpool(v, size)
        for cond in conds:
            D = np.load(S2 / "eval" / cond / "render_30000" / f"{v}_depth.npy")
            rgb = cv2.cvtColor(cv2.imread(str(S2 / "eval" / cond / "render_30000" / f"{v}_rgb.png")), cv2.COLOR_BGR2RGB)
            gray = np.repeat(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)[..., None], 3, -1).astype(np.float32) * 0.45
            fol = gray.copy()
            rend = D > 0
            for k, m in cls.items():
                m = m & tgt & rend
                good = (np.abs(D - M) <= T) if k == "conflict" else (np.abs(D - P) <= T)
                fol[m & good] = (46, 160, 67)
                fol[m & ~good] = (220, 38, 38)
            save(fol.astype(np.uint8), f"{setting}_{v}_{cond}_followed.jpg")
            err = (G - D) * FV
            em = tgt & rend & np.isfinite(err)
            e = gray.copy(); e[em] = diverging(err[em], a.vmax)
            save(e.astype(np.uint8), f"{setting}_{v}_{cond}_error.jpg")
        print(setting, v, "images done", flush=True)

(OUT / "data.js").write_text("window.INTENT = " + json.dumps(data, separators=(",", ":")) + ";\n")
shutil.copy2(Path(__file__).resolve().parent / "intent_viewer.html", S2 / "dashboard/intent.html")
print("wrote", OUT)
