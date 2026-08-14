#!/usr/bin/env python3
"""Qualitative panel: S5 B-rep mesh vs E1 GT point cloud, 3 buildings x 2 views."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

B = "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1"
E1D = ("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
       "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E1")


def read_ply(path):
    with open(path, "rb") as f:
        h = b""
        while not h.endswith(b"end_header\n"):
            h += f.readline()
        n = int([l for l in h.decode().splitlines()
                 if l.startswith("element vertex")][0].split()[-1])
        props = [l.split()[1:] for l in h.decode().splitlines()
                 if l.startswith("property")]
        fmt = {"float": ("f", 4), "uchar": ("B", 1)}
        dt = np.dtype([(nm, "<" + fmt[t][0]) for t, nm in props])
        return np.frombuffer(f.read(n * dt.itemsize), dtype=dt)


CLS_COL = {"roof": "#c05038", "wall": "#b8b0a0"}
RUNS = [("P2-ARRGS-X1-v1/runs/B022_clean", "B022 clean", "B022_DEBY_LOD2_4906965"),
        ("P2-ARRGS-X2-v1/runs/B173_changed", "B173 changed", "B173_DEBY_LOD2_4959326"),
        ("P2-ARRGS-X2-v1/runs/B036_hole", "B036 hole", "B036_DEBY_LOD2_4906982")]

fig = plt.figure(figsize=(15, 10))
for col, (run, label, bkey) in enumerate(RUNS):
    verts, tris = [], []
    cls = "roof"
    for ln in open(f"{B}/{run}/s5_brep.obj"):
        t = ln.split()
        if not t:
            continue
        if t[0] == "v":
            verts.append([float(x) for x in t[1:4]])
        elif t[0] == "g":
            cls = t[1]
        elif t[0] == "f":
            tris.append((cls, [int(x) - 1 for x in t[1:4]]))
    V = np.array(verts)
    e1 = read_ply(f"{E1D}/{bkey}.points.ply")
    P = np.stack([e1["x"], e1["y"], e1["z"]], 1)
    Pc = P[e1["classification"] == 6][::40]
    for row, (elev, azim) in enumerate([(55, -60), (12, -60)]):
        ax = fig.add_subplot(2, 3, row * 3 + col + 1, projection="3d")
        polys = {c: [] for c in CLS_COL}
        for c, tr in tris:
            if c in polys:
                polys[c].append(V[tr])
        for c, pl in polys.items():
            if pl:
                ax.add_collection3d(Poly3DCollection(
                    pl, facecolor=CLS_COL[c], edgecolor="none", alpha=0.9))
        ax.scatter(Pc[:, 0], Pc[:, 1], Pc[:, 2], s=0.3, c="#3070c0", alpha=0.35)
        allp = np.vstack([V, Pc]) if len(V) else Pc
        mid = allp.mean(0)
        r = (allp.max(0) - allp.min(0)).max() / 2
        ax.set_xlim(mid[0] - r, mid[0] + r)
        ax.set_ylim(mid[1] - r, mid[1] + r)
        ax.set_zlim(mid[2] - r, mid[2] + r)
        ax.view_init(elev, azim)
        ax.set_axis_off()
        if row == 0:
            ax.set_title(f"{label}\nred=ARRGS roof, grey=wall, blue=E1 GT", fontsize=9)
fig.tight_layout()
fig.savefig(f"{B}/qual_brep_vs_e1.png", dpi=90, facecolor="white")
print("saved", f"{B}/qual_brep_vs_e1.png")
