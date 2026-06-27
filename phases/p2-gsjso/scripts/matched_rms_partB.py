#!/usr/bin/env python3
"""P2 — matched-n RMS, PART B (mechanism): does gssem pull wall/edge points into the roof (looser fit)?
For 4906969/4906972/4908023, D4 dense+acmp: roof-classified point count + point->nearest-ref-plane distance
distribution (RMS, median |d|, p90 |d|), gssem (canonical disk) vs smrf (regenerated to temp, deterministic).
READ-ONLY w.r.t. canonical disk (smrf .las read from _matched_smrf_tmp; gssem from mob_eval). Observation only.
Runs in p0-tools (laspy + numpy + matplotlib). Reuses tum_mob_ref_rms plane/dz logic. EPSG:25832.
"""
import json
import numpy as np
import laspy
from pathlib import Path
import xml.etree.ElementTree as ET
from matplotlib.path import Path as MplPath
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/workspace/JointBuildGS"
GML = [f"{REPO}/phases/p0-audit/data/raw/lod2/690_5334.gml", f"{REPO}/phases/p0-audit/data/raw/lod2/690_5336.gml"]
NS = "http://www.opengis.net/gml"
BUILDINGS = ["4906969", "4906972", "4908023"]
ARMS = ["gs_d4_dense", "gs_d4_acmp"]
GSSEM_ROOT = f"{REPO}/phases/p0-audit/runs/mob_eval"
SMRF_ROOT = f"{REPO}/phases/p0-audit/runs/_matched_smrf_tmp"
OUTFIG = f"{REPO}/docs/figs/W_matched_rms"
FRAG = f"{REPO}/results/tum_transfer/mob/_matched_rms_partB.md"


def localname(t): return t.rsplit("}", 1)[-1]
def fit_plane(ring):
    c = ring.mean(0); _, _, Vt = np.linalg.svd(ring - c, full_matrices=False); n = Vt[-1]
    return n / (np.linalg.norm(n) + 1e-12), c
def parse_planes(targets):
    pl = {t: [] for t in targets}
    for gml in GML:
        for _, el in ET.iterparse(gml, events=("end",)):
            if localname(el.tag) == "Building":
                bid = el.get("{%s}id" % NS)
                if bid in pl:
                    for surf in el.iter():
                        if localname(surf.tag) == "RoofSurface":
                            for p in surf.iter("{%s}posList" % NS):
                                if p.text:
                                    a = np.asarray([float(x) for x in p.text.split()]).reshape(-1, 3)
                                    if len(a) >= 3:
                                        pl[bid].append(fit_plane(a[:-1] if np.allclose(a[0], a[-1]) else a))
                el.clear()
    return pl
def ndist(P, planes, dz):
    Q = P.copy(); Q[:, 2] -= dz; d = np.full(len(Q), np.inf)
    for n, c in planes:
        d = np.minimum(d, np.abs((Q - c) @ n))
    return d
def best_dz(P, planes):
    best = (np.inf, None)
    for dz in np.arange(40.0, 56.0, 0.25):
        r = float(np.sqrt((ndist(P, planes, dz) ** 2).mean()))
        if r < best[0]:
            best = (r, float(dz))
    return best[1]
_GEO = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
def ring(bid):
    g = [f for f in _GEO if f["properties"]["building_id"] == bid][0]["geometry"]
    return np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]
def roofpts(root, cfg, bid):
    las = f"{root}/{cfg}/DEBY_LOD2_{bid}_orig_classified.las"
    if not Path(las).exists():
        return None
    c = laspy.read(las); cl = np.asarray(c.classification)
    P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)])
    fp = MplPath(ring(f"DEBY_LOD2_{bid}"))
    return P[(cl == 6) & fp.contains_points(P[:, :2])]


planes = parse_planes({f"DEBY_LOD2_{b}" for b in BUILDINGS})
recs = []
for cfg in ARMS:
    for b in BUILDINGS:
        pl = planes[f"DEBY_LOD2_{b}"]
        rec = {"arm": cfg, "bid": b, "gssem": None, "smrf": None}
        for cls, root in [("gssem", GSSEM_ROOT), ("smrf", SMRF_ROOT)]:
            P = roofpts(root, cfg, b)
            if P is None or len(P) < 10:
                continue
            dz = best_dz(P, pl); d = ndist(P, pl, dz)
            rec[cls] = {"n": int(len(P)), "rms": float(np.sqrt((d ** 2).mean())),
                        "median": float(np.median(d)), "p90": float(np.percentile(d, 90)), "dz": dz}
        recs.append(rec)

L = ["## PART B — 메커니즘: gssem이 벽/가장자리 점을 지붕에 넣나 (관찰만)", "",
     "> 지붕분류 점(class=6, footprint 내) → 최근접 ref 지붕면 수직거리 분포. gssem=현 디스크(canonical), "
     "smrf=재생성(원본 .las가 백업에 없어 deterministic SMRF로 temp 재생성=원본과 동일). 단위 m. tag=orig.",
     "", "| arm | bid | cls | n_roof | RMS | median\\|d\\| | p90\\|d\\| |",
     "|---|---|---|---:|---:|---:|---:|"]
def fr(x, k): return f"{x[k]:.3f}" if x else "-"
def fn(x): return str(x["n"]) if x else "-"
for r in recs:
    for cls in ["gssem", "smrf"]:
        x = r[cls]
        L.append(f"| {r['arm']} | {r['bid']} | {cls} | {fn(x)} | {fr(x,'rms')} | {fr(x,'median')} | {fr(x,'p90')} |")
L += ["", "관찰: 위 표에서 gssem n_roof·median·p90 vs smrf 비교(점 더 많고 분포 더 퍼지면 '벽 포함→느슨한 적합' 신호; 판정/해석은 사람).",
      "출처: gssem `runs/mob_eval/<cfg>/<bid>_orig_classified.las`(현 디스크) · smrf `runs/_matched_smrf_tmp/...`(재생성). 거리=tum_mob_ref_rms 동일 평면·dz 로직.", ""]
Path(FRAG).write_text("\n".join(L))
print("\n".join(L))

# ---- figure: 4906969 roof points top(xy) + side(xz), gssem vs smrf ----
import os
os.makedirs(OUTFIG, exist_ok=True)
for b in ["4906969"]:
    pl = planes[f"DEBY_LOD2_{b}"]
    Pg = roofpts(GSSEM_ROOT, "gs_d4_dense", b); Ps = roofpts(SMRF_ROOT, "gs_d4_dense", b)
    if Pg is None or Ps is None:
        print(f"[fig] {b}: missing las (gssem={Pg is not None} smrf={Ps is not None})"); continue
    def sub(P, k=40000):
        return P if len(P) <= k else P[np.random.default_rng(0).choice(len(P), k, replace=False)]
    Pg2, Ps2 = sub(Pg), sub(Ps)
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    ax[0].scatter(Ps2[:, 0], Ps2[:, 1], s=0.5, c="tab:blue", label=f"smrf (n={len(Ps)})", alpha=0.5)
    ax[0].scatter(Pg2[:, 0], Pg2[:, 1], s=0.5, c="tab:red", label=f"gssem (n={len(Pg)})", alpha=0.5)
    ax[0].set_title(f"{b} roof pts — TOP (xy)"); ax[0].set_aspect("equal"); ax[0].legend(markerscale=8); ax[0].set_xticks([]); ax[0].set_yticks([])
    ax[1].scatter(Ps2[:, 0], Ps2[:, 2], s=0.5, c="tab:blue", alpha=0.5)
    ax[1].scatter(Pg2[:, 0], Pg2[:, 2], s=0.5, c="tab:red", alpha=0.5)
    ax[1].set_title(f"{b} roof pts — SIDE (xz): gssem(red) vs smrf(blue)"); ax[1].set_xticks([]); ax[1].set_yticks([])
    fig.suptitle(f"DEBY_LOD2_{b} (D4 dense) roof-classified points: gssem vs smrf — top & side", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95)); out = f"{OUTFIG}/{b}_roofpts.png"; fig.savefig(out, dpi=120); plt.close(fig)
    print(f"[fig] {b} -> {out}")
