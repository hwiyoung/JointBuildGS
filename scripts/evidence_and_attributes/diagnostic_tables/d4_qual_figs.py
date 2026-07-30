#!/usr/bin/env python3
"""P2-D4 qualitative figures — point cloud (top) + assembled LoD2 (bottom) for
[D4 (gssem) | image (raw_dense MVS) | LiDAR | reference], roof facets coloured per-facet.
Buildings: flat {4906972, 4907182} + curved {4906969} + control {4908023}. Per building 2x4 PNG.
Goal: see whether the D4 numbers (e.g. 4906972 RMS→LiDAR 2.41=LiDAR, over-seg 12→8; curved 4906969
RMS 0.76 = not over-flattened) look that way too. Runs in P0 tools container (matplotlib Agg + laspy).
EPSG:25832. Z normalised per-panel (ellipsoidal GS vs orthometric GML comparable).
"""
import glob, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import laspy
import xml.etree.ElementTree as ET

REPO = "/workspace/JointBuildGS"
RUNS = f"{REPO}/phases/p0-audit/runs"
MOB = f"{REPO}/results/tum_transfer/mob"
GML_FILES = [f"{REPO}/phases/p0-audit/data/raw/lod2/690_5334.gml",
             f"{REPO}/phases/p0-audit/data/raw/lod2/690_5336.gml"]
ALS = f"{REPO}/results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz"
D4_NPZ = f"{MOB}/tsdf_gs_d4_dense.npz"
GNS = "{http://www.opengis.net/gml}"
BUILDINGS = ["4906972", "4907182", "4906969", "4908023"]
OUT = f"{REPO}/docs/figs/W_D4_qual"


def bbox(bid):
    return json.load(open(f"{MOB}/baselines.json"))[bid]["bbox_utm"]


def clip(P, bb, buf=6.0):
    x0, y0, x1, y1 = bb
    m = (P[:, 0] >= x0 - buf) & (P[:, 0] <= x1 + buf) & (P[:, 1] >= y0 - buf) & (P[:, 1] <= y1 + buf)
    return P[m]


def cloud_npz(path, bb):
    d = np.load(path, allow_pickle=True)
    return clip(d["P_utm_clean"], bb)


def cloud_laz(path, bb):
    las = laspy.read(path)
    return clip(np.c_[np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)], bb)


def cityjson_polys(jsonl):
    lines = [l for l in open(jsonl) if l.strip()]
    meta = json.loads(lines[0]); tr = meta["transform"]
    sc = np.array(tr["scale"]); tl = np.array(tr["translate"])
    roofs, others = [], []
    for ln in lines[1:]:
        f = json.loads(ln)
        V = np.array(f["vertices"], dtype=float) * sc + tl
        for o in f["CityObjects"].values():
            for g in o.get("geometry", []):
                gt = g.get("type"); sem = g.get("semantics", {})
                surfs = sem.get("surfaces", []); vals = sem.get("values")
                if gt == "Solid":
                    shells, valsh = g["boundaries"], vals
                elif gt == "MultiSurface":
                    shells, valsh = [g["boundaries"]], [vals]
                else:
                    continue
                for si, shell in enumerate(shells):
                    vv = valsh[si] if valsh else None
                    for fi, surf in enumerate(shell):
                        ring = surf[0] if surf and isinstance(surf[0], list) else surf
                        poly = V[np.array(ring, dtype=int)]
                        typ = None
                        if vv is not None and fi < len(vv) and vv[fi] is not None and vv[fi] < len(surfs):
                            typ = surfs[vv[fi]].get("type")
                        (roofs if typ == "RoofSurface" else others).append(poly)
    return roofs, others


def gml_roofs(bid):
    roofs = []
    for gml in GML_FILES:
        try:
            for _, el in ET.iterparse(gml, events=("end",)):
                if el.tag.rsplit("}", 1)[-1] == "Building":
                    if el.get(GNS + "id") == bid:
                        for surf in el.iter():
                            if surf.tag.rsplit("}", 1)[-1] == "RoofSurface":
                                for pl in surf.iter(GNS + "posList"):
                                    if pl.text:
                                        a = np.array(pl.text.split(), float)
                                        if a.size % 3 == 0:
                                            roofs.append(a.reshape(-1, 3))
                    el.clear()
        except FileNotFoundError:
            pass
    return roofs


def draw_cloud(ax, P, title):
    ax.set_title(title, fontsize=9)
    if P is None or len(P) == 0:
        ax.text(0.5, 0.5, "no cloud", ha="center", va="center", transform=ax.transAxes); ax.axis("off"); return
    if len(P) > 60000:
        P = P[np.random.default_rng(0).choice(len(P), 60000, replace=False)]
    z = P[:, 2] - P[:, 2].min()
    ax.scatter(P[:, 0], P[:, 1], c=z, s=0.4, cmap="viridis", linewidths=0)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])


def draw_model(ax, roofs, others, title):
    ax.set_title(title, fontsize=9)
    if not roofs and not others:
        ax.text2D(0.5, 0.5, "not assembled", ha="center", va="center", transform=ax.transAxes); ax.set_axis_off(); return
    allpts = np.vstack(roofs + others) if (roofs or others) else np.zeros((1, 3))
    zmin = allpts[:, 2].min()
    def shift(p): q = p.copy(); q[:, 2] -= zmin; return q
    if others:
        ax.add_collection3d(Poly3DCollection([shift(p) for p in others], facecolor="0.8",
                                             edgecolor="0.5", linewidths=0.2, alpha=0.35))
    cmap = plt.cm.tab20
    rc = [cmap(i % 20) for i in range(len(roofs))]
    ax.add_collection3d(Poly3DCollection([shift(p) for p in roofs], facecolor=rc,
                                         edgecolor="k", linewidths=0.4, alpha=0.95))
    mn = allpts.min(0); mx = allpts.max(0); ctr = (mn + mx) / 2
    r = max((mx - mn)[:2].max(), 1.0) / 2
    ax.set_xlim(ctr[0] - r, ctr[0] + r); ax.set_ylim(ctr[1] - r, ctr[1] + r)
    ax.set_zlim(0, max((mx[2] - mn[2]) * 1.1, 1.0))
    ax.view_init(elev=28, azim=-58); ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
    ax.set_box_aspect((1, 1, 0.5))
    ax.text2D(0.02, 0.93, f"{len(roofs)} roof", transform=ax.transAxes, fontsize=8, color="darkred")


def get_cloud(col, bid, bb):
    if col == "D4":
        return cloud_npz(D4_NPZ, bb)
    if col == "image":
        las = f"{RUNS}/mob_eval/raw_dense/DEBY_LOD2_{bid}_orig_classified.las"
        return cloud_laz(las, bb) if glob.glob(las) else None
    if col == "LiDAR":
        return cloud_laz(ALS, bb)
    return None


MODEL_CFG = {"D4": "mob_eval/gs_d4_dense", "image": "mob_eval/raw_dense", "LiDAR": "mob_eval/raw_lidar"}
TITLES = {"D4": "D4 (gssem)", "image": "image (raw_dense MVS)", "LiDAR": "LiDAR", "reference": "reference"}


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    cols = ["D4", "image", "LiDAR", "reference"]
    for bid in BUILDINGS:
        full = f"DEBY_LOD2_{bid}"; bb = bbox(full)
        fig = plt.figure(figsize=(15, 7.5))
        for j, col in enumerate(cols):
            axt = fig.add_subplot(2, 4, j + 1)
            if col == "reference":
                rr = gml_roofs(full)
                if rr:
                    cmap = plt.cm.tab20
                    for i, p in enumerate(rr):
                        axt.fill(p[:, 0], p[:, 1], facecolor=cmap(i % 20), edgecolor="k", lw=0.4, alpha=0.9)
                    axt.set_aspect("equal")
                axt.set_title("reference (GT roof polys)", fontsize=9)
                axt.set_xticks([]); axt.set_yticks([])
            else:
                draw_cloud(axt, get_cloud(col, bid, bb), f"{TITLES[col]} cloud")
            axb = fig.add_subplot(2, 4, j + 5, projection="3d")
            if col == "reference":
                draw_model(axb, gml_roofs(full), [], "reference LoD2")
            else:
                g = glob.glob(f"{RUNS}/{MODEL_CFG[col]}/roofer_DEBY_LOD2_{bid}_orig/*.city.jsonl")
                if g:
                    rf, ot = cityjson_polys(g[0]); draw_model(axb, rf, ot, f"{TITLES[col]} LoD2")
                else:
                    draw_model(axb, [], [], f"{TITLES[col]} LoD2")
        fig.suptitle(f"{full}  (top: point cloud | bottom: assembled LoD2, roof facets per-colour)  "
                     f"[D4 | image | LiDAR | reference]", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        out = f"{OUT}/{bid}.png"; fig.savefig(out, dpi=110); plt.close(fig)
        print(f"[fig] {bid} -> {out}")


if __name__ == "__main__":
    main()
