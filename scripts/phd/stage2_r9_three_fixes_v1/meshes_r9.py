"""PHD-STAGE2-R9-THREE-FIXES-v1 step 1 (jointbuildgs:dev, CPU): LoD2 meshes without the bottom faces (fix 'ra') and the
outward normal of every remaining LoD2 face (fix 'da').

  python meshes_r9.py      # mounts: /artifacts (ro), /repo (ro), /r7 (PHD-STAGE2-R7-PROPAGATION-v1, ro), /p9 (rw)

Input: the render-frame meshes of r7/r8 (stage1/meshes/M_N.npz, M_B.npz: nominal LoD2 registered +0.1216 m; M_B with
polygon 3396 raised 1 m and its vertical step quads) and the CityGML type and building of every triangle
(stage-1 lod2_polygons.npz; the first 14,388 triangles of both meshes).
  bottom faces  faces.excluded_by_type: GroundSurface (and ClosureSurface; none in this scene). Cross-check: the rule for
                LoD2 without types (downward winding normal at the building's lowest height) on the same meshes.
  outward       CityGML polygons: the winding normal (CityGML orients polygons outward). Checked: roof-like faces n_z > 0;
                walls with faces.outward_side_outside against the building's footprint (its GroundSurface triangles) --
                counted as consistent / inward / undetermined (walls above the footprint interior, e.g. between two roof
                levels), not flipped. Step quads of M_B (made by r7, no CityGML winding): oriented away from polygon
                3396 with the same footprint test.
Writes /p9/stage1/meshes/{M_N,M_B}.npz (V, F, tri_poly, cls, raised of the kept triangles + tri_type, tri_building,
kept_from_r8), faces_{M_N,M_B}.npz (per remaining polygon: winding and outward normal, type, building, area, centroid)
and meshes_r9.json (counts, checks)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v3 import faces as FA  # noqa: E402

ART = Path("/artifacts/JointBuildGS")
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
R7 = Path("/r7"); OUT = Path("/p9/stage1/meshes"); OUT.mkdir(parents=True, exist_ok=True)
PZ = np.load(S1 / "inputs/lod2_polygons.npz")
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
TARGET = PJ["target_building"]
STEP_BASE = 100000
rep = {"rule": "LoD2 bottom faces (GroundSurface, ClosureSurface) are left out of the prior surface (method 3.1 / 4.3, r8 review)",
       "settings": {}}
for setting in ("M_N", "M_B"):
    m = dict(np.load(R7 / "stage1/meshes" / f"{setting}.npz"))
    V, F, tp = m["V"], m["F"].astype(np.int64), m["tri_poly"].astype(np.int64)
    nl = len(PZ["labels"])
    ttype = np.array(["step"] * len(F), dtype=object); tbld = np.array([TARGET] * len(F), dtype=object)
    ttype[:nl] = PZ["labels"].astype(str); tbld[:nl] = PZ["building_ids"].astype(str)
    assert (tp[nl:] >= STEP_BASE).all() and (tp[:nl] < STEP_BASE).all()
    drop_t = FA.excluded_by_type(ttype.astype(str))
    # polygon table of the full mesh (cross-check of the untyped rule; footprints)
    T = FA.polygon_table(V, F, tp)
    pid = T["ids"]; pidx = {int(p): i for i, p in enumerate(pid)}
    ptype = np.array([ttype[np.nonzero(tp == p)[0][0]] for p in pid]).astype(str)
    pbld = np.array([tbld[np.nonzero(tp == p)[0][0]] for p in pid]).astype(str)
    typed = FA.excluded_by_type(ptype)
    zmin_b = {b: T["zmin"][(pbld == b) & (ptype != "step")].min() for b in np.unique(pbld)}
    untyped = FA.bottom_faces_untyped(T["normal"][:, 2], T["zmax"], np.array([zmin_b[b] for b in pbld]))
    cross = dict(typed_bottom_polygons=int(typed.sum()), untyped_rule_polygons=int(untyped.sum()),
                 both=int((typed & untyped).sum()), typed_only=[int(p) for p in pid[typed & ~untyped]],
                 untyped_only=[int(p) for p in pid[~typed & untyped]],
                 closure_surfaces=int((ptype == "ClosureSurface").sum()))
    # outward normals of the remaining polygons
    keep_p = ~typed
    nw = T["normal"].copy(); nout = nw.copy()
    roof_like = np.abs(nw[:, 2]) >= 0.5
    flips = dict(roof_down_flipped=0, wall_inward_not_flipped=0, wall_undetermined=0, wall_consistent=0, step_consistent=0,
                 step_flipped=0, step_undetermined=0)
    for i in np.nonzero(keep_p & roof_like)[0]:
        if nw[i, 2] < 0:
            nout[i] = -nw[i]; flips["roof_down_flipped"] += 1
    walls = np.nonzero(keep_p & ~roof_like)[0]
    for b in np.unique(pbld[walls]):
        wi = walls[pbld[walls] == b]
        is_step = ptype[wi] == "step"
        foot_polys = pid[(pbld == b) & typed] if not is_step.all() else np.array([], np.int64)
        foot = V[F[np.isin(tp, foot_polys)]][:, :, :2]
        step_foot = V[F[tp == 3396]][:, :, :2]
        for sel, fp, key in ((~is_step, foot, "wall"), (is_step, step_foot, "step")):
            ii = wi[sel]
            if len(ii) == 0:
                continue
            plus, minus = FA.outward_side_outside(T["centroid"][ii], nw[ii], fp)
            inward = minus & ~plus
            if key == "step":                         # constructed quads: oriented by the test
                nout[ii[inward]] = -nw[ii[inward]]
            flips[f"{key}_{'flipped' if key == 'step' else 'inward_not_flipped'}"] += int(inward.sum())
            if key == "wall" and inward.any():
                flips.setdefault("wall_inward_polygons", []).extend([[int(pid[i]), str(b), round(float(T["area"][i]), 3)] for i in ii[inward]])
            flips[f"{key}_consistent"] += int((plus & ~minus).sum())
            flips[f"{key}_undetermined"] += int((plus == minus).sum())
    # meshes without the bottom faces
    kt = np.nonzero(~drop_t)[0]
    np.savez_compressed(OUT / f"{setting}.npz", V=V, F=F[kt], tri_poly=tp[kt], cls=m["cls"], raised=m["raised"],
                        tri_type=ttype[kt].astype(str), tri_building=tbld[kt].astype(str), kept_from_r8=kt)
    kp = np.nonzero(keep_p)[0]
    np.savez_compressed(OUT / f"faces_{setting}.npz", ids=pid[kp], normal_winding=nw[kp], normal_outward=nout[kp],
                        type=ptype[kp], building=pbld[kp], area=T["area"][kp], centroid=T["centroid"][kp], zmin=T["zmin"][kp], zmax=T["zmax"][kp])
    tgt = typed & (pbld == TARGET)
    rep["settings"][setting] = dict(
        triangles_r8=int(len(F)), triangles_r9=int(len(kt)), triangles_removed=int(drop_t.sum()),
        polygons_r8=int(len(pid)), polygons_removed=int(typed.sum()), polygons_r9=int(keep_p.sum()),
        removed_area_m2=float(T["area"][typed].sum()), target_bottom_polygons=[int(p) for p in pid[tgt]],
        target_bottom_area_m2=float(T["area"][tgt].sum()), untyped_cross_check=cross, outward=flips,
        bottom_faces_by_building={b: int(((pbld == b) & typed).sum()) for b in np.unique(pbld[typed])})
    print(setting, json.dumps({k: v for k, v in rep["settings"][setting].items() if k != "bottom_faces_by_building"}), flush=True)
(OUT / "meshes_r9.json").write_text(json.dumps(rep, indent=1))
