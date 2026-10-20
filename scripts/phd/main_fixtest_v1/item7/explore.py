"""PHD-MAIN-FIXTEST-v1 일 7, first look (prints only): the LoD2 face 53 of B173nb_b10 in the stage-0 unit store, the unseen set and
the region file. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

PH = Path("/ph")
S0 = PH / "main_stage0_v1/PHD-MAIN-STAGE0-v1"
S1 = PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1"
SL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
SITE = "B173nb_b10"

w = json.loads((S1 / "defs/fig_views_v1.json").read_text())["sites"][SITE]["unseen_face"]
un = np.load(S1 / "defs" / SITE / "unseen.npz")
U = np.load(S0 / "s61/box" / SITE / "LoD2/units.npz")
R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{SITE}_LoD2.npz")
ST = np.load(S0 / "fork_inputs/s61" / SITE / "store_LoD2.npz")
print("unseen keys", {k: (un[k].shape, un[k].dtype) for k in un.files})
print("units n_loc", len(U["loc_center"]), "n_surf", len(U["surf_ext"]), "sp", U["sp"])
print("store n_loc", len(ST["loc_center"]), "same centres", np.array_equal(ST["loc_center"], U["loc_center"]))
print("regions n", len(R["centre"]), {k: (R[k].shape, R[k].dtype) for k in R.files})
se = U["surf_ext"][U["loc_surface"]]
sidx = np.nonzero(U["surf_ext"] == 53)[0]
print("store surfaces with ext 53:", sidx, "o", U["o"][sidx], "e1", U["e1"][sidx], "e2", U["e2"][sidx], "i0 j0 ni nj", U["i0"][sidx], U["j0"][sidx], U["ni"][sidx], U["nj"][sidx])
f53 = np.nonzero(se == 53)[0]
print("locations of ext 53:", len(f53), "kind", np.unique(U["loc_kind"][f53], return_counts=True), "extra", U["loc_extra"][f53].sum())
print("state of ext 53:", np.unique(U["state"][f53], return_counts=True))
print("in_eval of ext 53:", np.unique(R["in_eval"][f53], return_counts=True))
print("unseen_label_inferred of ext 53:", np.unique(R["unseen_label_inferred"][f53], return_counts=True))
face = un["surf_ext"] == 53
pu = un["patch"][face]
print("unseen face patches", face.sum(), "subset of f53", np.isin(pu, f53).all(), "li", np.unique(un["label_inferred"][face], return_counts=True))
print("centre dtype", un["centre"].dtype, "max |unseen centre - store centre|", float(np.abs(un["centre"][face].astype(np.float64) - U["loc_center"][pu]).max()))
print("region centre vs store", float(np.abs(R["centre"][f53].astype(np.float64) - U["loc_center"][f53]).max()), "area", np.unique(np.round(R["area"][f53], 6), return_counts=True))
c0, t = np.asarray(w["centre"], float), np.asarray(w["t"], float)
X = U["loc_center"][f53]
s, z = (X - c0) @ t, X[:, 2]
o, e1, e2 = U["o"][sidx[0]], U["e1"][sidx[0]], U["e2"][sidx[0]]
u = (X - o) @ e1 / U["sp"]
v = (X - o) @ e2 / U["sp"]
print("frac u", np.unique(np.round(u - np.floor(u), 4))[:10], "frac v", np.unique(np.round(v - np.floor(v), 4))[:10])
print("e1.t", float(e1 @ t), "e2.z", float(e2[2]))
print("s range", s.min(), s.max(), "z range", z.min(), z.max())
# state in the s,z plane: print a coarse ASCII map (1 m blocks: share invisible)
st = U["state"][f53]
for zz in np.arange(-25, -45, -1.0):
    row = ""
    for ss in np.arange(-40, 31, 1.0):
        m = (s >= ss) & (s < ss + 1) & (z <= zz) & (z > zz - 1)
        if not m.any():
            row += " "
            continue
        fr = (st[m] == 0).mean()
        row += "#" if fr > 0.9 else ("+" if fr > 0.6 else ("." if fr > 0.3 else "o"))
    print(f"{zz:6.1f} {row}")
print("n_seeing of ext 53 (invisible / other):", np.unique(U["n_seeing"][f53], return_counts=True))
for k in ("pix_sum", "a1_sum", "agree_sum", "conflict_sum", "n_supporting", "E", "J_loc", "why", "loc_in_range"):
    if k in U.files:
        a = U[k]
        print(k, a.shape, a.dtype)
