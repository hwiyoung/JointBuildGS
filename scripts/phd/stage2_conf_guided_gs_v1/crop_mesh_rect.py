"""Crop the two stage-2 LoD2 meshes (global coords) to the stage-1 ALS rectangle so the official sampler
(generate_pcd.py) spends its samples on the target block. Faces are kept when their centroid lies inside the
rectangle; points outside are filtered later in prepare_stage2_inputs.py."""
import json
from pathlib import Path
import numpy as np
S1 = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1")
S2 = Path("/s2")
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
rect = np.array(PJ["als_crop_local_xy"], float); shift = np.array(PJ["shift_global_to_local"], float)
assert shift[0] < -690000 and shift[1] < -5336000, shift          # local = global + shift
grect = rect - shift[:2]
rep = {"rect_local": rect.tolist(), "rect_global": grect.tolist(), "shift_global_to_local": shift.tolist()}
for name in ["lod2_M_nominal", "lod2_M_biased_main_1m"]:
    V, F = [], []
    for l in (S2 / f"inputs/{name}.obj").read_text().splitlines():
        t = l.split()
        if not t: continue
        if t[0] == "v": V.append([float(x) for x in t[1:4]])
        elif t[0] == "f": F.append([int(x.split("/")[0]) - 1 for x in t[1:4]])
    V = np.array(V); F = np.array(F)
    c = V[F].mean(1)
    keep = (c[:, 0] >= grect[0, 0]) & (c[:, 0] <= grect[1, 0]) & (c[:, 1] >= grect[0, 1]) & (c[:, 1] <= grect[1, 1])
    used = np.unique(F[keep]); remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))
    out = S2 / f"inputs/{name}_crop.obj"
    with out.open("w") as o:
        for vv in V[used]: o.write("v " + " ".join(f"{x:.9f}" for x in vv) + "\n")
        for ff in remap[F[keep]]: o.write("f " + " ".join(str(int(x) + 1) for x in ff) + "\n")
    rep[name] = {"faces_in": int(len(F)), "faces_kept": int(keep.sum()), "verts_kept": int(len(used))}
    print(name, rep[name])
(S2 / "inputs/crop_mesh_report.json").write_text(json.dumps(rep, indent=1))
