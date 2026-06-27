#!/usr/bin/env python3
"""P2 gssem re-qual — qualitative renders of the GSSEM assembled LoD2 models (facet-coloured) for
4906972·4906969·4908023: [D-gssem | D4-gssem | LiDAR | reference]. Run AFTER gssem re-eval (cityjson=gssem).
smrf models are preserved in gssem_requal_backup/perbuilding_smrf.tar. Observation only.
Runs in P0 tools container (matplotlib Agg + laspy) or host if libs present. EPSG:25832.
"""
import glob, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import xml.etree.ElementTree as ET

REPO = "/workspace/JointBuildGS"
RUNS = f"{REPO}/phases/p0-audit/runs/mob_eval"
MOB = f"{REPO}/results/tum_transfer/mob"
GML_FILES = [f"{REPO}/phases/p0-audit/data/raw/lod2/690_5334.gml",
             f"{REPO}/phases/p0-audit/data/raw/lod2/690_5336.gml"]
GNS = "{http://www.opengis.net/gml}"
BUILDINGS = ["4906972", "4906969", "4908023"]
COLS = [("D-gssem", "gs_prior_full_dense"), ("D4-gssem", "gs_d4_dense"),
        ("LiDAR", "raw_lidar"), ("reference", None)]
OUT = f"{REPO}/docs/figs/W_gssem_requal"


def cityjson_polys(jsonl, target_bid):
    lines = [l for l in open(jsonl) if l.strip()]
    meta = json.loads(lines[0]); tr = meta["transform"]
    sc = np.array(tr["scale"]); tl = np.array(tr["translate"])
    roofs, others = [], []
    full = f"DEBY_LOD2_{target_bid}"
    for ln in lines[1:]:
        f = json.loads(ln)
        V = np.array(f["vertices"], dtype=float) * sc + tl
        for cid, o in f["CityObjects"].items():
            if not (cid == full or cid.startswith(full + "-")):
                continue  # target-only (drop neighbours)
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
                    if el.get(GNS + "id") == f"DEBY_LOD2_{bid}":
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


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    for bid in BUILDINGS:
        fig = plt.figure(figsize=(15, 4.2))
        for j, (label, cfg) in enumerate(COLS):
            ax = fig.add_subplot(1, 4, j + 1, projection="3d")
            if label == "reference":
                draw_model(ax, gml_roofs(bid), [], "reference LoD2")
            else:
                g = glob.glob(f"{RUNS}/{cfg}/roofer_DEBY_LOD2_{bid}_orig/*.city.jsonl")
                if g:
                    rf, ot = cityjson_polys(g[0], bid); draw_model(ax, rf, ot, f"{label} LoD2")
                else:
                    draw_model(ax, [], [], f"{label} LoD2")
        fig.suptitle(f"DEBY_LOD2_{bid}  — GSSEM read-out assembled model (roof facets per-colour)  "
                     f"[D-gssem | D4-gssem | LiDAR | reference]", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.93))
        out = f"{OUT}/{bid}.png"; fig.savefig(out, dpi=110); plt.close(fig)
        print(f"[fig] {bid} -> {out}")


if __name__ == "__main__":
    main()
