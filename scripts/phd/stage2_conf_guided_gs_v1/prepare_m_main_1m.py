"""Stage-2 input: registered LoD2 mesh with the main roof (3396) raised by 1.0 m + vertical step quads (same
construction as stage-1 verify v2, delta 1.0 instead of 3.0). Writes inputs/lod2_M_biased_main_1m.obj (global coords)."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
V2CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
OUT = Path("/s2/inputs"); OUT.mkdir(parents=True, exist_ok=True)
PZ = np.load(S1 / "inputs/lod2_polygons.npz")
V = PZ["vertices_global"].astype(np.float64).copy(); F = PZ["faces"].astype(np.int64); pot = PZ["poly_of_tri"]
V[:, 2] += V2CFG["registration"]["M_dz_m"]
faces = V2CFG["injection"]["sets"]["main"]["faces"]; dM = 1.0
sel = np.isin(pot, faces); Vb = V.copy(); Vb[np.unique(F[sel]), 2] += dM
edges = Counter()
for tri in F[sel]:
    for a, b in ((0, 1), (1, 2), (2, 0)):
        edges[tuple(sorted((tuple(np.round(V[tri[a]], 6)), tuple(np.round(V[tri[b]], 6)))))] += 1
extraV, extraF = [], []
for (pa, pb), c in edges.items():
    if c != 1: continue
    base = len(Vb) + len(extraV); pa, pb = np.array(pa), np.array(pb)
    extraV += [pa, pb, pb + [0, 0, dM], pa + [0, 0, dM]]; extraF += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
Vb2 = np.vstack([Vb, np.array(extraV)]); Fb2 = np.vstack([F, np.array(extraF, dtype=np.int64)])
def write_obj(path, V_, F_):
    with open(path, "w") as o:
        for vv in V_: o.write("v " + " ".join(f"{x:.9f}" for x in vv) + "\n")
        for ff in F_: o.write("f " + " ".join(str(int(x) + 1) for x in ff) + "\n")
write_obj(OUT / "lod2_M_biased_main_1m.obj", Vb2, Fb2)
write_obj(OUT / "lod2_M_nominal.obj", V, F)
json.dump({"faces": faces, "delta_m": dM, "registration_dz_m": V2CFG["registration"]["M_dz_m"], "step_triangles": len(extraF)}, open(OUT / "lod2_M_biased_main_1m.json", "w"), indent=2)
print("wrote", len(Vb2), "verts", len(Fb2), "faces; step tris", len(extraF))
