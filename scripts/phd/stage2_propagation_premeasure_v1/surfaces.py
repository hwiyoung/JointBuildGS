"""PHD-STAGE2-PROPAGATION-PREMEASURE-v1 step 1 (jointbuildgs:dev, CPU): the prior surfaces of each scene, numbered
from the scene's own prior (never carried over from another scene or from a training result).

  python surfaces.py      # mounts: /artifacts/JointBuildGS (ro), /repo (ro), /out (this task's payload, rw)

Settings (configs/phd/stage2_propagation_premeasure_v1/premeasure.json):
  M_N  LoD2, nominal               render frame = PHD-STAGE1-VERIFY-v2 lod2_v2_nominal_local.npz
  M_B  LoD2, 3396 raised 1 m       + the five vertical step quads of prepare_m_main_1m.py (built here in the local frame)
  L_N  airborne LiDAR TIN, nominal stage-1 als_points.npz + registration dz (0.0186 m)
  L_B  TIN, 3396 footprint +1 m    the raised vertices are read from the stage-1 render mesh of that scene
Surface number:
  LoD2: one polygon = one surface (poly_index); step quads 100000 + quad index (kind 'step', wall-like).
  TIN : gentle triangles (|n_z| >= steep_nz) connected through shared edges = one surface, numbered by decreasing
        area; steep triangles are boundaries (tri_surface = -2).
Writes /out/surfaces/<setting>/mesh.npz (V, F, tri_surface, tri_normal, tri_area) and surfaces.json.
Step 2 (render_ids.py) casts the rays of the prior renders on these meshes and checks the depth against the prior maps."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Polygon
from shapely.ops import unary_union

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
V2 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2"
CFG = json.loads(Path("/repo/configs/phd/stage2_propagation_premeasure_v1/premeasure.json").read_text())
V2CFG = json.loads(Path("/repo/configs/phd/stage1_verify_v2/experiment.json").read_text())
OUT = Path("/out/surfaces")
STEEP_NZ = float(CFG["surface_rules"]["steep_nz"])
STEP_BASE = 100000
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
RECT = np.array(PJ["als_crop_local_xy"], float)
TARGET_ROOF_RINGS = [Polygon(p["ring_local_xy"]) for p in PJ["polygons"] if p["is_target"] and p["citygml_type"] == "RoofSurface"]
TARGET_FOOT = unary_union(TARGET_ROOF_RINGS)


def read_obj_vertices(p):
    return np.array([[float(x) for x in l.split()[1:4]] for l in p.read_text().splitlines() if l.startswith("v ")])


def tri_geometry(V, F):
    cr = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    a2 = np.linalg.norm(cr, axis=1)
    n = cr / np.maximum(a2, 1e-12)[:, None]
    return n.astype(np.float32), (0.5 * a2).astype(np.float64)


def area_normal(n, a):
    m = (n * a[:, None]).sum(0)
    return (m / max(np.linalg.norm(m), 1e-12)).tolist()


def lod2_setting(raise_main):
    z = np.load(V2 / "inputs_v2/lod2_v2_nominal_local.npz")
    P1 = np.load(S1 / "inputs/lod2_polygons.npz")
    V = z["vertices_local"].astype(np.float64).copy()
    F = z["faces"].astype(np.int64)
    pot = z["poly_of_tri"].astype(np.int64)
    labels = P1["labels"]
    bids = P1["building_ids"]
    assert np.array_equal(F, P1["faces"].astype(np.int64)) and np.array_equal(pot, P1["poly_of_tri"])
    n_step = 0
    if raise_main:
        faces = V2CFG["injection"]["sets"]["main"]["faces"]
        sel = np.isin(pot, faces)
        V0 = V.copy()
        V[np.unique(F[sel]), 2] += 1.0
        # boundary edges of the raised polygon (edges used once), keyed by coordinates as in prepare_m_main_1m.py
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
            ext_v += [pa, pb, pb + [0, 0, 1.0], pa + [0, 0, 1.0]]
            ext_f += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
        n_step = len(ext_f) // 2
        V = np.vstack([V, np.array(ext_v)])
        F = np.vstack([F, np.array(ext_f, np.int64)])
        pot = np.concatenate([pot, STEP_BASE + np.repeat(np.arange(n_step), 2)])
        # the stage-2 render mesh of this scene (6 decimals): same geometry and order
        Vr = read_obj_vertices(ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1/inputs/prior_render/M_biased_main_1m/transformed.obj")
        check = dict(render_mesh_vertices=int(len(Vr)), max_abs_vertex_diff_m=float(np.abs(Vr - V).max()))
    else:
        check = {}
    n, a = tri_geometry(V, F)
    kind_of = {"RoofSurface": "roof", "WallSurface": "wall", "GroundSurface": "ground"}
    rows = []
    PJi = {p["poly_index"]: p for p in PJ["polygons"]}
    for s in np.unique(pot):
        m = pot == s
        if s >= STEP_BASE:
            kind, bid, target = "step", "DEBY_LOD2_4959323", True
        else:
            lab = Counter(labels[m[: len(labels)]].tolist()).most_common(1)[0][0]
            kind = kind_of.get(lab, "other")
            bid = Counter(bids[m[: len(bids)]].tolist()).most_common(1)[0][0]
            target = bool(PJi[int(s)]["is_target"]) if int(s) in PJi else (bid == PJ["target_building"])
        rows.append(dict(id=int(s), kind=kind, building=str(bid), target=bool(target), n_tri=int(m.sum()),
                         area_mesh_m2=float(a[m].sum()), normal=area_normal(n[m], a[m]), in_crop_json=int(s) in PJi))
    return V, F.astype(np.int32), pot.astype(np.int32), n, a, rows, dict(n_step_quads=n_step, **check)


def tin_setting(raised_scene):
    als = np.load(S1 / "inputs/als_points.npz")
    V = als["xyz_local"].astype(np.float64).copy()
    V[:, 2] += V2CFG["registration"]["L_dz_m"]
    F = als["triangles"].astype(np.int64)
    cls = als["classification"]
    raised = np.zeros(len(V), bool)
    check = {}
    if raised_scene:
        Vr = read_obj_vertices(V2 / "inputs_v2/prior_render/L_biased_main/transformed.obj")
        dz = Vr[:, 2] - V[:, 2]
        raised = dz > 0.5
        V[raised, 2] += 1.0
        check = dict(n_raised_vertices=int(raised.sum()), max_abs_vertex_diff_m=float(np.abs(Vr - V).max()))
    n, a = tri_geometry(V, F)
    gentle = np.abs(n[:, 2]) >= STEEP_NZ
    # triangle adjacency through shared edges (both triangles gentle)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e.sort(axis=1)
    tri = np.tile(np.arange(len(F)), 3)
    key = e[:, 0] * (len(V) + 1) + e[:, 1]
    order = np.argsort(key, kind="stable")
    ks, ts = key[order], tri[order]
    same = ks[1:] == ks[:-1]
    t1, t2 = ts[:-1][same], ts[1:][same]
    ok = gentle[t1] & gentle[t2]
    G = coo_matrix((np.ones(int(ok.sum())), (t1[ok], t2[ok])), shape=(len(F), len(F)))
    ncomp, lab = connected_components(G, directed=False)
    lab = np.where(gentle, lab, -1)
    comp_area = np.bincount(lab[gentle], weights=a[gentle], minlength=ncomp)
    rank = np.full(ncomp, -1, np.int64)
    present = np.nonzero(comp_area > 0)[0]
    rank[present[np.argsort(-comp_area[present], kind="stable")]] = np.arange(len(present))
    tri_surface = np.where(gentle, rank[np.maximum(lab, 0)], -2).astype(np.int32)
    rows = []
    cent = V[F].mean(1)
    for s in range(len(present)):
        m = tri_surface == s
        vid = np.unique(F[m])
        c6 = float((cls[vid] == 6).mean())
        xy = cent[m][:, :2]
        # share of the surface area whose triangle centroid lies inside the target building's roof footprint (reporting only)
        ins = shapely.contains_xy(TARGET_FOOT, xy[:, 0], xy[:, 1])
        tshare = float((a[m] * ins).sum() / a[m].sum())
        rows.append(dict(id=int(s), kind="building" if c6 >= 0.5 else "ground", class6_share=c6,
                         raised_share=float(raised[vid].mean()), n_tri=int(m.sum()), n_vertices=int(len(vid)),
                         area_mesh_m2=float(a[m].sum()), normal=area_normal(n[m], a[m]), target_footprint_share=tshare,
                         target=bool(c6 >= 0.5 and tshare >= 0.5), z_mean=float(cent[m][:, 2].mean())))
    info = dict(n_tri=int(len(F)), n_steep=int((~gentle).sum()), steep_area_m2=float(a[~gentle].sum()),
                n_surfaces=int(len(present)), **check)
    return V, F.astype(np.int32), tri_surface, n, a, rows, info


summary = {}
for setting in ("M_N", "M_B", "L_N", "L_B"):
    if setting.startswith("M"):
        V, F, ts, n, a, rows, info = lod2_setting(setting == "M_B")
    else:
        V, F, ts, n, a, rows, info = tin_setting(setting == "L_B")
    d = OUT / setting
    d.mkdir(parents=True, exist_ok=True)
    np.savez(d / "mesh.npz", V=V, F=F, tri_surface=ts, tri_normal=n, tri_area=a)
    (d / "surfaces.json").write_text(json.dumps(dict(setting=setting, info=info, surfaces=rows), indent=1))
    kinds = Counter(r["kind"] for r in rows)
    summary[setting] = dict(info=info, kinds=dict(kinds), n_target=int(sum(r["target"] for r in rows)))
    print(setting, summary[setting], flush=True)
(OUT / "summary.json").write_text(json.dumps(summary, indent=1))
