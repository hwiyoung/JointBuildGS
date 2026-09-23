"""Stage-2 figures (jointbuildgs:dev, CPU): target-face overview and per-condition height-error maps.

  python make_figures.py [--views DJI_..._0009_D DJI_..._0024_D] [--vmax 0.5]
Mounts: /s2 (payload, rw for eval/figures), /artifacts/JointBuildGS (ro, native images), /fonts (Noto CJK, ro).

faces_<view>.png : photo with the target roof faces coloured and labelled, and the stage-1 observation map A on them
                   (green = photos measure the pixel, red = they do not).
errors_<view>.png: for each condition, height of the final render minus GT height on the target building,
                   (G - D) * f with f = vertical conversion on roofs, surface-normal conversion on walls.
                   Red = render above GT (walls: outward), blue = below; grey background = render; no colour = no GT.
GT is the projected GT cloud (nearest-point z-buffer) min-pooled over the training-resolution pixel footprint, so a sparse
foreground surface is not averaged with points seen through it."""
import os
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2")
MAPS = S2 / "inputs/maps"
NATIVE = Path("/artifacts/JointBuildGS/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images")
OUT = S2 / "eval/figures"
FONT = "/fonts/NotoSansCJK-Medium.ttc"
FACE_INFO = {3396: ("3396 본지붕", (91, 63, 214)), 3394: ("3394 옆 지붕", (0, 121, 140)), 3387: ("3387 소면", (209, 73, 91)),
             3389: ("3389 소면", (237, 174, 73)), 3404: ("3404 급경사 소면", (48, 99, 142)), 3393: ("3393", (141, 106, 159))}
CONDS = [("P_M_N", "P 판정 켬 · LoD2 · 정상"), ("P0_M_N", "P0 판정 끔 · LoD2 · 정상"), ("O_M_N", "O 공식 GeoGS · 정상"),
         ("I", "I 영상 단독"), ("P_M_B", "P 판정 켬 · LoD2 · 본지붕 +1 m"), ("P0_M_B", "P0 판정 끔 · 본지붕 +1 m"),
         ("O_M_B", "O 공식 GeoGS · 본지붕 +1 m"), ("P_L_B", "P 판정 켬 · ALS · 본지붕 +1 m")]

ap = argparse.ArgumentParser()
ap.add_argument("--views", nargs="+", default=["DJI_20241217101313_0009_D", "DJI_20241217101343_0024_D"])
ap.add_argument("--vmax", type=float, default=0.5)
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]


def mload(setname, view):
    p = MAPS / setname / "raw_depth" / f"{view}.npy"
    return np.load(p if p.exists() else MAPS / setname / f"{view}.npy")


def to_size(x, size, interp=cv2.INTER_NEAREST):
    return cv2.resize(x.astype(np.float32), size, interpolation=interp)


def font(sz):
    return ImageFont.truetype(FONT, sz)


def label(img, xy, text, fill=(255, 255, 255), sz=22):
    d = ImageDraw.Draw(img)
    x, y = xy
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            d.text((x + dx, y + dy), text, font=font(sz), fill=(0, 0, 0))
    d.text((x, y), text, font=font(sz), fill=fill)


def diverging(err, vmax):
    x = np.clip(err / vmax, -1, 1)
    r = np.where(x >= 0, 255, 255 * (1 + x)); b = np.where(x <= 0, 255, 255 * (1 - x)); g = 255 * (1 - np.abs(x))
    return np.stack([r, g, b], -1).astype(np.uint8)


for view in a.views:
    photo = cv2.cvtColor(cv2.imread(str(next(NATIVE.glob(f"{view}.*")))), cv2.COLOR_BGR2RGB)
    W = 1600; H = int(round(photo.shape[0] * W / photo.shape[1]))
    size = (W, H)
    photo = cv2.resize(photo, size, interpolation=cv2.INTER_AREA)
    F = to_size(mload("faceid", view), size).astype(np.int32)
    A = to_size(mload("conf", view), size)
    FV = to_size(mload("fvert", view), size)
    G_full = mload(GT_SET, view)
    ok = np.isfinite(G_full) & (G_full > 0)
    k = int(np.ceil(G_full.shape[1] / W)) + 2
    Gmin = cv2.erode(np.where(ok, G_full, np.inf).astype(np.float32), np.ones((k, k), np.uint8))
    G = cv2.resize(Gmin, size, interpolation=cv2.INTER_NEAREST)
    G[~np.isfinite(G)] = np.nan

    # ---- faces overview: colours + labels | observation map A on the target roof
    over = photo.astype(np.float32).copy()
    for f, (_, col) in FACE_INFO.items():
        m = F == f
        over[m] = 0.45 * over[m] + 0.55 * np.array(col, np.float32)
    wall = np.isin(F, WALL)
    over[wall] = 0.7 * over[wall] + 0.3 * np.array([160, 160, 160], np.float32)
    left = Image.fromarray(over.astype(np.uint8))
    for f, (name, col) in FACE_INFO.items():
        m = (F == f).astype(np.uint8)
        if m.sum() < 300:
            continue
        n, lab, stats, cent = cv2.connectedComponentsWithStats(m)
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        label(left, (int(cent[k][0]) - 40, int(cent[k][1]) - 12), name)
    wm = wall.astype(np.uint8)
    if wm.sum() > 300:
        n, lab, stats, cent = cv2.connectedComponentsWithStats(wm)
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        label(left, (int(cent[k][0]) - 20, int(cent[k][1])), "벽", sz=20)
    right = photo.astype(np.float32).copy() * 0.55
    roof = np.isin(F, ROOF)
    right[roof & (A > 0)] = 0.35 * right[roof & (A > 0)] / 0.55 + 0.65 * np.array([40, 190, 70])
    right[roof & (A <= 0)] = 0.35 * right[roof & (A <= 0)] / 0.55 + 0.65 * np.array([230, 40, 40])
    right = Image.fromarray(right.astype(np.uint8))
    label(right, (16, 12), "대상 지붕 위 관측 지도 A: 초록 = 사진(MVS)이 잼, 빨강 = 못 잼", sz=24)
    label(left, (16, 12), f"대상 건물 면 번호 — {view}", sz=24)
    canvas = Image.new("RGB", (2 * W, H), (0, 0, 0))
    canvas.paste(left, (0, 0)); canvas.paste(right, (W, 0))
    canvas.save(OUT / f"faces_{view}.png")

    # ---- per-condition error maps
    tgt = roof | wall
    tiles = []
    for cond, title in CONDS:
        D = np.load(S2 / "eval" / cond / "render_30000" / f"{view}_depth.npy")
        rgb = cv2.imread(str(S2 / "eval" / cond / "render_30000" / f"{view}_rgb.png"))
        gray = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2RGB).astype(np.float32) * 0.6
        err = (G - D) * FV
        m = tgt & (D > 0) & np.isfinite(err)
        tile = gray.copy()
        tile[m] = diverging(err[m], a.vmax)
        im = Image.fromarray(tile.astype(np.uint8))
        med = {f: float(np.median(err[(F == f) & m])) if ((F == f) & m).sum() > 50 else None for f in (3396, 3394, 3387, 3389, 3404)}
        label(im, (14, 8), title, sz=44)
        txt = "  ".join(f"{f}:{v:+.2f}" for f, v in med.items() if v is not None)
        label(im, (14, H - 62), "중앙값 렌더−GT (m)  " + txt, sz=34)
        tiles.append(np.asarray(im))
    bar = np.zeros((100, W * 4, 3), np.uint8) + 20
    ramp = diverging(np.linspace(-a.vmax, a.vmax, 900)[None, :].repeat(26, 0), a.vmax)
    bar[62:88, 40:940] = ramp
    barim = Image.fromarray(bar)
    label(barim, (40, 8), f"렌더 높이 − GT 높이: 파랑 −{a.vmax} m … 흰색 0 … 빨강 +{a.vmax} m (렌더가 GT보다 위, 벽은 바깥)   · 색 없는 곳 = GT 없음", sz=40)
    grid = np.concatenate([np.concatenate(tiles[i:i + 4], axis=1) for i in range(0, len(tiles), 4)], axis=0)
    full = np.concatenate([np.asarray(barim), grid], axis=0)
    Image.fromarray(full).resize((full.shape[1] // 2, full.shape[0] // 2), Image.LANCZOS).save(OUT / f"errors_{view}.png")
    print(view, "ok")
