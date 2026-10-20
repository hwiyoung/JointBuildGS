"""PHD-MAIN-B0REF-v1 일 2 selection of one cloud (jointbuildgs:dev, CPU): the two wall selections of 3.3 and the roof space, on the
B0-box crop in the raw comparison frame (config wall_selection, locked before 일 2).

  python s2_select.py <name> [...]     name = a crop of c1_crop.py (geogs, uls_nadir, uls_manual, photogrammetry, ...)
  -> /b0/sel/<name>.npz:
     ev          point XY in the evaluation range
     wall_any    in the wall space of at least one target-building wall face (and ev)
     wall_face   ext of the first such face (-1 none); wall_h = z - lowest z of that face; wall_d = signed outward horizontal distance
                 to that face's plane; wall_s = along-wall coordinate
     face_<ext>  indices of the points in that face's wall space (and ev)   (table 2; a corner point can be in two faces)
     roof_any    in the roof space of at least one target-building roof face (and ev)
     vert        the study's vertical-surface test (s04_gt_v7.vertical_points) on the whole crop, all returns
     rule_face   ext of the target-building wall face that owns the point by the study's wall rule (vert, closest wall triangle of the
                 box LoD2 within 2 m, foot inside the face), -1 none; rule = rule_face >= 0 and ev
     rclass      return class (0 single, 1 first of many, 2 middle, 3 last; -1 = no return numbers)
[이 요청에서 냄] scientific_verdict: null."""
import json
import sys
import time

import numpy as np

from b0_common import B0, BLD, BOX, DR, S0, in_rect, jdump, jl, load_crop, lod2_faces, log, now, return_class, roof_space, vertical_points, wall_space

CH = 2_000_000


def rule_owner(X, vert, faces):
    """s04_gt_v7.py:272-295: closest wall triangle of the box LoD2 (|n_z| < 0.5, no bottom faces, any building), dist <= 2 m and the
    foot inside the face (along >= 0.999 dist - 1e-4); returns the owning face ext when it belongs to the target building."""
    import open3d as o3d
    m = np.load(DR / "s02_box" / BOX / "lod2_mesh.npz")
    sh = np.asarray(jl(S0 / "s61/box" / BOX / "LoD2/summary.json")["registration"]["shift_applied"], np.float64)
    V = m["V"] + sh; F = m["F"]; ts = m["tri_surface"]; ttype = m["tri_type"]
    tab = {r["ext"]: r for r in jl(DR / "s02_box" / BOX / "lod2_surfaces.json")["surfaces"]}
    n_tri = np.zeros((len(F), 3))
    for e, r in tab.items():
        n_tri[ts == e] = r["normal"]
    okt = (ttype != 2) & (ts >= 0)
    wall_tri = np.nonzero(okt & (np.abs(n_tri[:, 2]) < 0.5))[0]
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F[wall_tri].astype(np.uint32)))
    target = {f["ext"] for f in faces if f["kind"] == 2}
    own = np.full(len(X), -1, np.int32)
    iv = np.nonzero(vert)[0]
    for b0 in range(0, len(iv), CH):
        ii = iv[b0:b0 + CH]
        Xc = X[ii]
        r = sc.compute_closest_points(o3d.core.Tensor(Xc.astype(np.float32)))
        cp = r["points"].numpy().astype(np.float64); prim = r["primitive_ids"].numpy().astype(np.int64)
        tw = wall_tri[prim]
        v = Xc - cp
        dist = np.linalg.norm(v, axis=1)
        along = np.abs((v * n_tri[tw]).sum(1))
        ok = (dist <= 2.0) & (along >= 0.999 * dist - 1e-4)
        e = ts[tw]
        ok &= np.isin(e, list(target))
        own[ii[ok]] = e[ok]
    return own


def main(name):
    t0 = time.time()
    C = load_crop(name)
    X = C["xyz"]
    faces = lod2_faces()
    ev = in_rect(X[:, :2])
    out = dict(ev=ev)
    wall_any = np.zeros(len(X), bool); wface = np.full(len(X), -1, np.int32)
    wh = np.full(len(X), np.nan, np.float32); wd = np.full(len(X), np.nan, np.float32); wsv = np.full(len(X), np.nan, np.float32)
    roof_any = np.zeros(len(X), bool)
    for f in faces:
        if f["kind"] == 2:
            m, d, s = wall_space(f, X)
            m &= ev
            out[f"face_{f['ext']}"] = np.nonzero(m)[0].astype(np.int64)
            new = m & (wface < 0)
            wface[new] = f["ext"]; wh[new] = X[new, 2] - f["tris"][..., 2].min(); wd[new] = d[new]; wsv[new] = s[new]
            wall_any |= m
        else:
            roof_any |= roof_space(f, X)[0] & ev
    log(name, "space done", int(wall_any.sum()), int(roof_any.sum()), f"{time.time() - t0:.0f}s")
    vert = vertical_points(X)
    log(name, "vertical done", int(vert.sum()), f"{time.time() - t0:.0f}s")
    own = rule_owner(X, vert, faces)
    log(name, "rule done", int(((own >= 0) & ev).sum()), f"{time.time() - t0:.0f}s")
    rc = return_class(C["return_number"], C["number_of_returns"]) if "return_number" in C else np.full(len(X), -1, np.int8)
    out.update(wall_any=wall_any, wall_face=wface, wall_h=wh, wall_d=wd, wall_s=wsv, roof_any=roof_any, vert=vert, rule_face=own,
               rule=(own >= 0) & ev, rclass=rc)
    (B0 / "sel").mkdir(exist_ok=True)
    np.savez(B0 / "sel" / f"{name}.npz", **out)
    jdump(B0 / "sel" / f"{name}.json", dict(name=name, points=int(len(X)), ev=int(ev.sum()), wall_space=int(wall_any.sum()), roof_space=int(roof_any.sum()),
                                            vert=int(vert.sum()), rule=int(out["rule"].sum()), seconds=round(time.time() - t0, 1), made=now(),
                                            building=BLD, scientific_verdict=None))
    log(name, "saved", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        main(nm)
