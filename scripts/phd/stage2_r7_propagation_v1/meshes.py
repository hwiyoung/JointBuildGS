"""PHD-STAGE2-R7-PROPAGATION-v1 step 1 (jointbuildgs:dev): render-frame meshes of every setting.

  M_N  LoD2 nominal                       PHD-STAGE1-VERIFY-v2 lod2_v2_nominal_local.npz (registered +0.1216 m)
  M_B  LoD2, polygon 3396 raised 1 m       + vertical step quads on its boundary edges (as prepare_m_main_1m.py)
  M_C  LoD2, polygon 3394 raised 1 m       (optional scene of this order: the shaded roof end has many missing locations)
  L_N  airborne LiDAR TIN nominal         stage-1 als_points.npz + registration dz 0.0186 m
  L_B  TIN, points inside the 3396 footprint raised 1 m (the raised vertices are read from the stage-1 render mesh)
Writes /p7/stage1/meshes/<setting>.npz: V, F, tri_poly (LoD2 polygon index, 100000 + quad for step quads; -1 for the
TIN), cls (TIN vertex class), raised (vertex flag), and meshes.json (checks against the stage-2 render meshes)."""
import json
from collections import Counter
from pathlib import Path

import numpy as np

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
V2 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2"
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
V2CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
OUT = Path("/p7/stage1/meshes"); OUT.mkdir(parents=True, exist_ok=True)
STEP_BASE = 100000


def read_obj_vertices(p):
    return np.array([[float(x) for x in l.split()[1:4]] for l in p.read_text().splitlines() if l.startswith("v ")])


def lod2(raise_polys, delta=1.0):
    z = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz")
    V = z["vertices_local"].astype(np.float64).copy(); F = z["faces"].astype(np.int64); pot = z["poly_of_tri"].astype(np.int64)
    if not raise_polys:
        return V, F, pot
    sel = np.isin(pot, raise_polys)
    V0 = V.copy()
    V[np.unique(F[sel]), 2] += delta
    edges = Counter()
    for tri in F[sel]:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((tuple(np.round(V0[tri[a]], 6)), tuple(np.round(V0[tri[b]], 6)))))] += 1
    ext_v, ext_f = [], []
    for (pa, pb), c in edges.items():
        if c != 1:
            continue
        base = len(V) + len(ext_v)
        pa, pb = np.array(pa), np.array(pb)
        ext_v += [pa, pb, pb + [0, 0, delta], pa + [0, 0, delta]]
        ext_f += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    nq = len(ext_f) // 2
    V = np.vstack([V, np.array(ext_v)]); F = np.vstack([F, np.array(ext_f, np.int64)])
    pot = np.concatenate([pot, STEP_BASE + np.repeat(np.arange(nq), 2)])
    return V, F, pot


def tin(raised_scene):
    als = np.load(S1 / "inputs/als_points.npz")
    V = als["xyz_local"].astype(np.float64).copy(); V[:, 2] += V2CFG["registration"]["L_dz_m"]
    raised = np.zeros(len(V), bool)
    if raised_scene:
        Vr = read_obj_vertices(V2 / "inputs_v2/prior_render/L_biased_main/transformed.obj")
        raised = (Vr[:, 2] - V[:, 2]) > 0.5
        V[raised, 2] += 1.0
    return V, als["triangles"].astype(np.int64), als["classification"].astype(np.int8), raised


rep = {}
for setting in ("M_N", "M_B", "M_C", "L_N", "L_B"):
    if setting.startswith("M"):
        V, F, pot = lod2({"M_N": [], "M_B": [3396], "M_C": [3394]}[setting])
        np.savez(OUT / f"{setting}.npz", V=V, F=F, tri_poly=pot, cls=np.zeros(0, np.int8), raised=np.zeros(0, bool))
        r = dict(n_vertices=int(len(V)), n_triangles=int(len(F)), n_step_quads=int((pot >= STEP_BASE).sum() // 2))
        if setting == "M_B":   # the stage-2 render mesh of this scene (6 decimals)
            Vr = read_obj_vertices(S2 / "inputs/prior_render/M_biased_main_1m/transformed.obj")
            r["max_abs_vertex_diff_vs_stage2_render_mesh_m"] = float(np.abs(Vr - V).max())
    else:
        V, F, cls, raised = tin(setting == "L_B")
        np.savez(OUT / f"{setting}.npz", V=V, F=F, tri_poly=np.full(len(F), -1, np.int64), cls=cls, raised=raised)
        r = dict(n_vertices=int(len(V)), n_triangles=int(len(F)), n_raised=int(raised.sum()))
    rep[setting] = r
    print(setting, r, flush=True)
(OUT / "meshes.json").write_text(json.dumps(rep, indent=1))
