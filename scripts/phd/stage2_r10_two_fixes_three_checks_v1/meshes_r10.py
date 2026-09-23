"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 step 1 (jointbuildgs:dev, CPU): LoD2 meshes without the overlapping parts of
party walls (fix 'na', method 3.1 of 2026-10-02).

  python meshes_r10.py      # mounts: /artifacts (ro), /repo (ro), /p9 (PHD-STAGE2-R9-THREE-FIXES-v1, ro), /p10 (rw)

Input: the r9 meshes (bottom faces already left out; stage1/meshes/{M_N,M_B}.npz with the CityGML type and building of
every triangle) and r9's outward normal of every polygon (faces_<setting>.npz).
  pairs   faces.party_wall_overlaps over the WallSurface polygons: two buildings, outward normals of cosine <= -0.9, the
          intersection of their projections on the common plane inside the strip where the planes lie within 0.1 m.
          Cross-check: the same search with the M_B step quads (r7-made faces of the target building) added.
  cut     faces.cut_triangles: every triangle of a wall that meets an overlap is replaced by the triangles of its remaining
          part; triangles that do not meet one stay as they are (same row of V). r10 mesh = the untouched r9 triangles in
          r9's order, then the new pieces polygon by polygon (new vertices appended to V).
  frames  the grid origin of every remaining polygon = the first vertex of its first r9 triangle and its plane normal =
          r9's area-weighted normal (stage1_products_r9.surfaces_of), so a cut polygon keeps its r9 cell grid.
Writes /p10/stage1/meshes/{M_N,M_B}.npz (V, F, tri_poly, cls, raised, tri_type, tri_building, kept_from_r9 (r9 row of an
untouched triangle, -1 for a piece), source_r9 (the r9 row a triangle comes from)), faces_<setting>.npz (r9 rows of the
remaining polygons, area = remaining area), frames_<setting>.npz (ids, o, normal), cuts_<setting>.json (pairs: frame,
region as WKT in the common-plane coordinates, areas, gaps) and meshes_r10.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v4 import faces as FA  # noqa: E402
from src.phd.prior_propagation_v4 import surfaces as surf  # noqa: E402

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
P9 = Path("/p9"); OUT = Path("/p10/stage1/meshes"); OUT.mkdir(parents=True, exist_ok=True)
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
TARGET = PJ["target_building"]
STEP_BASE = 100000
rep = {"rule": "the part of a wall that overlaps a wall of another building is left out of the prior surface (method 3.1, r9 review)",
       "dmax_m": FA.PARTY_DMAX_M, "cos_opposite": FA.PARTY_COS, "min_area_m2": FA.PARTY_MIN_AREA_M2, "settings": {}}


def polys_of(m, fz, types):
    tp = m["tri_poly"].astype(np.int64)
    nout = {int(p): fz["normal_outward"][i] for i, p in enumerate(fz["ids"])}
    bld = {int(p): str(fz["building"][i]) for i, p in enumerate(fz["ids"])}
    typ = {int(p): str(fz["type"][i]) for i, p in enumerate(fz["ids"])}
    out = []
    for p in sorted(nout):
        if typ[p] not in types:
            continue
        rows = np.nonzero(tp == p)[0]
        out.append(dict(id=p, building=bld[p], normal=nout[p], tris=m["V"][m["F"][rows]], rows=rows))
    return out


for setting in ("M_N", "M_B"):
    m = dict(np.load(P9 / "stage1/meshes" / f"{setting}.npz"))
    fz = dict(np.load(P9 / "stage1/meshes" / f"faces_{setting}.npz"))
    V, F, tp = m["V"].astype(np.float64), m["F"].astype(np.int64), m["tri_poly"].astype(np.int64)
    n_tri, a_tri = surf.tri_geometry(V, F)
    walls = polys_of(m, fz, ("WallSurface",))
    ov = FA.party_wall_overlaps(walls)
    # cross-check: step quads (M_B) with the walls
    steps = polys_of(m, fz, ("step",))
    ov_steps = [o for o in FA.party_wall_overlaps(walls + steps) if o["a"] >= STEP_BASE or o["b"] >= STEP_BASE] if steps else []
    by_poly = {}
    for k, o in enumerate(ov):
        for p in (o["a"], o["b"]):
            by_poly.setdefault(p, []).append(k)
    wall_of = {w["id"]: w for w in walls}
    keep_rows = np.ones(len(F), bool)
    newV, newF, new_poly, new_src = [], [], [], []
    nv = len(V)
    per_poly = {}
    for p, ks in sorted(by_poly.items()):
        w = wall_of[p]
        cuts = [(ov[k]["frame"], ov[k]["region"]) for k in ks]
        new, src, touched, info = FA.cut_triangles(w["tris"], cuts)
        keep_rows[w["rows"][touched]] = False
        pieces = src >= 0
        # pieces of touched triangles (untouched triangles come back unchanged in `new`; they keep their r9 row)
        from_touched = touched[src]
        T = new[from_touched]
        k_ = len(T)
        if k_:
            newV.append(T.reshape(-1, 3)); newF.append(nv + np.arange(3 * k_).reshape(-1, 3)); nv += 3 * k_
            new_poly.append(np.full(k_, p)); new_src.append(w["rows"][src[from_touched]])
        a_before = float(a_tri[w["rows"]].sum())
        a_after = float(a_tri[w["rows"][~touched]].sum() + (0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1).sum() if k_ else 0.0))
        per_poly[p] = dict(building=w["building"], target=w["building"] == TARGET, partners=sorted({ov[k]["b"] if ov[k]["a"] == p else ov[k]["a"] for k in ks}),
                           area_r9_m2=a_before, area_r10_m2=a_after, cut_m2=a_before - a_after, triangles_touched=int(touched.sum()),
                           triangles_r9=int(len(w["rows"])), pieces=int(k_), fully_cut=bool(a_after < 1e-6), **info)
    kept = np.nonzero(keep_rows)[0]
    V10 = np.concatenate([V] + newV) if newV else V
    F10 = np.concatenate([F[kept]] + newF) if newF else F[kept]
    tp10 = np.concatenate([tp[kept]] + new_poly) if new_poly else tp[kept]
    src10 = np.concatenate([kept] + new_src) if new_src else kept
    kept_from = np.concatenate([kept, np.full(len(F10) - len(kept), -1)]).astype(np.int64)
    tt = m["tri_type"][src10]; tb = m["tri_building"][src10]
    np.savez_compressed(OUT / f"{setting}.npz", V=V10, F=F10, tri_poly=tp10, cls=m["cls"], raised=m["raised"], tri_type=tt, tri_building=tb,
                        kept_from_r9=kept_from, source_r9=src10.astype(np.int64))
    # faces table of the remaining polygons (r9 rows; area = remaining area) and the r9 grid frames
    remain = np.unique(tp10)
    a10 = np.bincount(np.searchsorted(remain, tp10), weights=surf.tri_geometry(V10, F10)[1], minlength=len(remain))
    rows = np.array([int(np.nonzero(fz["ids"] == p)[0][0]) for p in remain])
    fz10 = {k: v[rows] for k, v in fz.items()}; fz10["area"] = a10
    np.savez_compressed(OUT / f"faces_{setting}.npz", **fz10)
    o_ = np.stack([V[F[np.nonzero(tp == p)[0][0], 0]] for p in remain])
    nrm = []
    for p in remain:
        sel = tp == p
        nn = (n_tri[sel] * a_tri[sel, None]).sum(0); nrm.append(nn / np.linalg.norm(nn))
    np.savez_compressed(OUT / f"frames_{setting}.npz", ids=remain, o=o_, normal=np.array(nrm))
    cuts_json = [dict(a=o["a"], b=o["b"], building_a=wall_of[o["a"]]["building"], building_b=wall_of[o["b"]]["building"],
                      target=TARGET in (wall_of[o["a"]]["building"], wall_of[o["b"]]["building"]), area_m2=o["area"],
                      overlap_before_gap_m2=o["overlap_before_gap"], gap_max_m=o["gap_max"], gap_min_m=o["gap_min"], cos=o["cos"],
                      frame=[np.asarray(x).tolist() for x in o["frame"]], region_wkt=o["region"].wkt) for o in ov]
    (OUT / f"cuts_{setting}.json").write_text(json.dumps(dict(pairs=cuts_json, polygons={str(k): v for k, v in per_poly.items()}), indent=1))
    removed_polys = [p for p, r in per_poly.items() if r["fully_cut"]]
    rep["settings"][setting] = dict(
        wall_polygons=len(walls), pairs=len(ov), polygons_cut=len(per_poly), polygons_fully_cut=len(removed_polys),
        polygons_fully_cut_ids=sorted(removed_polys), target_polygons_cut=sorted(p for p, r in per_poly.items() if r["target"]),
        cut_area_m2=float(sum(r["cut_m2"] for r in per_poly.values())), overlap_area_m2=float(sum(o["area"] for o in ov)),
        target_cut_area_m2=float(sum(r["cut_m2"] for r in per_poly.values() if r["target"])),
        triangles_r9=int(len(F)), triangles_untouched=int(len(kept)), triangles_new=int(len(F10) - len(kept)), triangles_r10=int(len(F10)),
        polygons_r9=int(len(np.unique(tp))), polygons_r10=int(len(remain)),
        gap_max_m=float(max((o["gap_max"] for o in ov), default=0.0)), cos_max=float(max((o["cos"] for o in ov), default=-1.0)),
        sliver_area_dropped_m2=float(sum(r["sliver_area_dropped_m2"] for r in per_poly.values())),
        pieces_with_holes=int(sum(r["pieces_with_holes"] for r in per_poly.values())),
        step_quads_paired=len(ov_steps), area_check_m2=float(a_tri.sum() - surf.tri_geometry(V10, F10)[1].sum()))
    print(setting, json.dumps(rep["settings"][setting]), flush=True)
(OUT / "meshes_r10.json").write_text(json.dumps(rep, indent=1))
