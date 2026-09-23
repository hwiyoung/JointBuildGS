"""O-condition prior clouds for the official GeoGS pipeline (freeze matching at 8000):
  M_N: author's lod2_pcd.ply (local frame) with the stage-1 registration shift (+0.1216 m).
  M_B: M_N with every point strictly inside the main-roof ring 3396 (>= 0.05 m from its edges) raised by 1.0 m,
       matching the rendered mesh lod2_M_biased_main_1m.obj. Runs in the official GeoGS image (plyfile)."""
import json
from pathlib import Path
import numpy as np
from plyfile import PlyData
ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
NE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/lod2_pcd.ply"
V2CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
dz = float(V2CFG["registration"]["M_dz_m"])
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
ring = np.array(next(p for p in PJ["polygons"] if p["poly_index"] == 3396)["ring_local_xy"], float)
PZ = np.load(S1 / "inputs/lod2_polygons.npz"); shift = np.array(PJ["shift_global_to_local"], float)
roof_v = PZ["vertices_global"][np.unique(PZ["faces"][PZ["poly_of_tri"] == 3396])] + shift
roof_zmin = float(roof_v[:, 2].min()) + dz   # registered roof; only roof-level points rise (LoD2 GroundSurface samples stay)
if np.allclose(ring[0], ring[-1]): ring = ring[:-1]


def inside_poly(x, y, poly):
    n = len(poly); ins = np.zeros(len(x), bool)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        c = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        ins ^= c; j = i
    return ins


def edge_dist(x, y, poly):
    d = np.full(len(x), np.inf)
    for i in range(len(poly)):
        a = poly[i]; b = poly[(i + 1) % len(poly)]; ab = b - a; L2 = float(ab @ ab)
        t = np.clip(((x - a[0]) * ab[0] + (y - a[1]) * ab[1]) / max(L2, 1e-12), 0, 1)
        d = np.minimum(d, np.hypot(x - (a[0] + t * ab[0]), y - (a[1] + t * ab[1])))
    return d


out = Path("/s2/inputs/o_prior"); rep = {"registration_dz_m": dz, "source": str(NE)}
p = PlyData.read(str(NE)); v = p["vertex"]
x = np.asarray(v["x"], float); y = np.asarray(v["y"], float); z0 = np.asarray(v["z"], float)
rep["points"] = int(len(x)); rep["z_range_before"] = [float(z0.min()), float(z0.max())]
v["z"] = (z0 + dz).astype(v["z"].dtype)
(out / "M_N").mkdir(parents=True, exist_ok=True); p.write(str(out / "M_N/lod2_pcd.ply"))
ins = inside_poly(x, y, ring) & (edge_dist(x, y, ring) > 0.05) & (z0 + dz >= roof_zmin - 0.5)
rep["roof_zmin_registered"] = roof_zmin
zb = z0 + dz; zb[ins] += 1.0
v["z"] = zb.astype(v["z"].dtype)
(out / "M_B").mkdir(parents=True, exist_ok=True); p.write(str(out / "M_B/lod2_pcd.ply"))
rep["raised_points"] = int(ins.sum()); rep["raised_z_range_before"] = [float(z0[ins].min()), float(z0[ins].max())] if ins.any() else None
(out / "report.json").write_text(json.dumps(rep, indent=1)); print(rep)
