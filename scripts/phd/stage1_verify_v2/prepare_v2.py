"""Step 1 (jointbuildgs:dev): registered nominal meshes and partially injected biased meshes for both priors.
Reads only stage-1 inputs; writes V2/inputs_v2/*.obj (global coords, same writer format as stage 1)."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon

ART = Path("/artifacts/JointBuildGS")
CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
S1 = ART / CFG["stage1_relative"]
V2 = Path("/v2")
INP = V2 / "inputs_v2"
INP.mkdir(parents=True, exist_ok=True)
PZ = np.load(S1 / "inputs/lod2_polygons.npz")
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
ALS = np.load(S1 / "inputs/als_points.npz")
shift = PZ["shift"]
polys = {p["poly_index"]: p for p in PJ["polygons"]}
dzL, dzM = CFG["registration"]["L_dz_m"], CFG["registration"]["M_dz_m"]
dL, dM = CFG["injection"]["delta_m"]["L"], CFG["injection"]["delta_m"]["M"]


def write_obj(path, V, F):
    with open(path, "w") as o:
        for vv in V:
            o.write("v " + " ".join(f"{x:.9f}" for x in vv) + "\n")
        for ff in F:
            o.write("f " + " ".join(str(int(x) + 1) for x in ff) + "\n")


meta = {"task_id": CFG["task_id"], "scientific_verdict": None, "registration": CFG["registration"], "delta_m": CFG["injection"]["delta_m"], "sets": {}}
# ---------------- M (LoD2): registered nominal + injected sets with step faces
V = PZ["vertices_global"].astype(np.float64).copy()
F = PZ["faces"].astype(np.int64)
pot = PZ["poly_of_tri"]
V[:, 2] += dzM
write_obj(INP / "lod2_v2_nominal.obj", V, F)
np.savez(INP / "lod2_v2_nominal_local.npz", vertices_local=V + shift, faces=F, poly_of_tri=pot, poly_region_code=PZ["poly_region_code"])
# ---------------- L (ALS): registered nominal + injected sets
P = ALS["xyz_global"].astype(np.float64).copy()
P[:, 2] += dzL
T = ALS["triangles"]
write_obj(INP / "als_v2_nominal.obj", P, T)
P_local_xy = (P + shift)[:, :2]
for name, spec in CFG["injection"]["sets"].items():
    faces = spec["faces"]
    # --- M: raise the triangles of the selected polygons, add vertical quads on the boundary edges
    sel_tri = np.isin(pot, faces)
    Vb = V.copy()
    raised_rows = np.unique(F[sel_tri])
    Vb[raised_rows, 2] += dM
    edges = Counter()
    for tri in F[sel_tri]:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            pa, pb = tuple(np.round(V[tri[a]], 6)), tuple(np.round(V[tri[b]], 6))
            edges[tuple(sorted((pa, pb)))] += 1
    boundary = [e for e, c in edges.items() if c == 1]
    extraV, extraF = [], []
    for (pa, pb) in boundary:
        base = len(Vb) + len(extraV)
        pa, pb = np.array(pa), np.array(pb)
        extraV.extend([pa, pb, pb + [0, 0, dM], pa + [0, 0, dM]])
        extraF.extend([[base, base + 1, base + 2], [base, base + 2, base + 3]])
    Vb2 = np.vstack([Vb, np.array(extraV)]) if extraV else Vb
    Fb2 = np.vstack([F, np.array(extraF, dtype=np.int64)]) if extraF else F
    write_obj(INP / f"lod2_v2_biased_{name}.obj", Vb2, Fb2)
    pot_b = np.concatenate([pot, np.full(len(extraF), -2, pot.dtype)]) if extraF else pot
    np.savez(INP / f"lod2_v2_biased_{name}_local.npz", vertices_local=Vb2 + shift, faces=Fb2, poly_of_tri=pot_b, poly_region_code=PZ["poly_region_code"])
    # --- L: raise ALS points inside the XY footprints of the selected faces
    inside = np.zeros(len(P), bool)
    for pi in faces:
        ring = Polygon(polys[pi]["ring_local_xy"])
        bb = ring.bounds
        cand = np.where((P_local_xy[:, 0] >= bb[0]) & (P_local_xy[:, 0] <= bb[2]) & (P_local_xy[:, 1] >= bb[1]) & (P_local_xy[:, 1] <= bb[3]))[0]
        for i in cand:
            if ring.covers(Point(P_local_xy[i])):
                inside[i] = True
    Pb = P.copy()
    Pb[inside, 2] += dL
    write_obj(INP / f"als_v2_biased_{name}.obj", Pb, T)
    meta["sets"][name] = {"faces": faces, "face_area_m2": {str(pi): polys[pi]["area_m2"] for pi in faces}, "M_triangles_raised": int(sel_tri.sum()),
                          "M_boundary_edges": len(boundary), "M_step_triangles": len(extraF), "L_points_raised": int(inside.sum()),
                          "L_points_by_class": {str(k): int(v) for k, v in Counter(ALS["classification"][inside].tolist()).items()}}
    print(name, meta["sets"][name])
(V2 / "injection_v2.json").write_text(json.dumps(meta, indent=2))
print("prepared", sorted(x.name for x in INP.iterdir()))
