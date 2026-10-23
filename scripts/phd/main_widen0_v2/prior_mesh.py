"""PHD-MAIN-PREP-DISCARD-RULE-v1 s02 (jointbuildgs:dev, CPU): prior meshes and judgment-unit stores of a range = the prep
measure step02_meshes.py with the party-wall caps moved into the shared module (prior_propagation_v5.caps); everything
else unchanged (equivalence check 1 compares the outputs with the prep payload).

  python s02_meshes.py <range_id> [--ranges-file /prep/step01/ranges.json] [--out-sub s02] [--margin m]

LoD2 (method 4.1): RoofSurface + WallSurface polygons of the buildings whose footprint meets the range + margin
(GroundSurface / ClosureSurface left out), triangulated in their plane; party-wall overlaps cut from both walls
(prior_propagation_v4.faces, r10); the open edges of every cut region closed by thin cap quads (new, order 5.7);
the cut regions themselves kept apart as probe faces (render-only, to count rays that would enter a gap).
ALS (method 4.1): Delaunay TIN of the class 2 / 6 points inside the range + margin; surface numbers = r10's second outline
source ('cls2': building triangle = >= 2 vertices of class 6; steep triangles split; non-building and steep carry none).
Stores: locations.build_plane_store (LoD2 polygons, cell grid origin = first exterior vertex of the polygon) and
locations.build_tin_store (ALS building surfaces), cell 0.25 m, rectangle = XY bounding box of range + margin.
scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import Polygon

from common import CFG, OUT, SHIFT, SURVEY, ZB, global_to_local, jdump, log, read_als, widen, range_polygon, inside_range
from src.phd.prior_propagation_v5 import caps as capm
from src.phd.prior_propagation_v5 import faces as fc
from src.phd.prior_propagation_v5 import locations as locs
from src.phd.prior_propagation_v5 import surfaces as surf
from src.phd.prior_propagation_v5.conversion import ROOF_NZ

T_ROOF, T_WALL, T_CAP = 0, 1, 2
CAP_BASE = capm.CAP_BASE


def newell(ring):
    r = np.asarray(ring, np.float64)
    n = np.zeros(3)
    for a, b in zip(r, np.roll(r, -1, axis=0)):
        n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    L = np.linalg.norm(n)
    return n / L if L > 0 else np.array([0, 0, 1.0])


def plane_axes(n):
    e1 = np.cross([0.0, 0.0, 1.0], n)
    e1 = e1 / np.linalg.norm(e1) if np.linalg.norm(e1) > 1e-6 else np.array([1.0, 0.0, 0.0])
    e2 = np.cross(n, e1)
    return e1, e2 / np.linalg.norm(e2)


def triangulate(ext, holes):
    """triangles [k, 3, 3] of a planar polygon (exterior + holes), winding along the Newell normal of the exterior.
    Original 3-D vertices are kept exactly (shared edges of neighbouring polygons stay closed); only vertices created by
    the hole split are lifted onto the polygon plane."""
    ext = np.asarray(ext, np.float64)
    if np.allclose(ext[0], ext[-1]):
        ext = ext[:-1]
    holes = [np.asarray(q, np.float64)[:-1] if np.allclose(q[0], q[-1]) else np.asarray(q, np.float64) for q in holes]
    n = newell(np.vstack([ext, ext[:1]]))
    e1, e2 = plane_axes(n)
    o = ext[0].copy()
    to2 = lambda R: np.stack([(R - o) @ e1, (R - o) @ e2], 1)
    h = float(np.median((ext - o) @ n))
    allv = np.vstack([ext] + holes) if holes else ext
    all2 = to2(allv)
    poly = Polygon(to2(ext), [to2(q) for q in holes]).buffer(0)
    out = []
    for g in getattr(poly, "geoms", [poly]):
        if g.geom_type != "Polygon" or g.area < 1e-8:
            continue
        for piece in fc._no_holes(g):
            xy = np.asarray(piece.exterior.coords)[:-1]
            d2 = ((xy[:, None, :] - all2[None, :, :]) ** 2).sum(-1)
            j = d2.argmin(1); exact = d2[np.arange(len(xy)), j] < 1e-12
            P3 = np.where(exact[:, None], allv[j], o + xy[:, :1] * e1 + xy[:, 1:2] * e2 + h * n)
            for (i0, i1, i2) in fc.ear_clip(xy):
                T = P3[[i0, i1, i2]]
                if np.dot(np.cross(T[1] - T[0], T[2] - T[0]), n) < 0:
                    T = T[[0, 2, 1]]
                if 0.5 * np.linalg.norm(np.cross(T[1] - T[0], T[2] - T[0])) > 1e-10:
                    out.append(T)
    return np.array(out).reshape(-1, 3, 3), n, o


def lod2_mesh(rng, blds):
    wide = widen(rng, CFG["ranges"]["prior_margin_m"])
    P = Polygon(range_polygon(wide))
    polys = []          # dict(pid, building, type, normal, tris, o)
    for b in blds:
        fps = [np.stack(global_to_local(np.asarray(p["ext"])[:, 0], np.asarray(p["ext"])[:, 1]), 1) for p in b["surfaces"]["ground"]]
        if not fps or not any(Polygon(f).buffer(0).intersects(P) for f in fps if len(f) >= 4):
            continue
        for typ, key in ((T_ROOF, "roof"), (T_WALL, "wall")):
            for p in b["surfaces"][key]:
                ext = np.asarray(p["ext"], np.float64)
                if len(ext) < 4:
                    continue
                loc = lambda R: np.stack(global_to_local(R[:, 0], R[:, 1], R[:, 2] + ZB), 1)
                tris, n, o = triangulate(loc(ext), [loc(np.asarray(h, np.float64)) for h in p["holes"]])
                if len(tris):
                    polys.append(dict(pid=len(polys), gml=p["id"], building=b["id"], type=typ, normal=n, tris=tris, o=o))
    walls = [dict(id=q["pid"], building=q["building"], normal=q["normal"], tris=q["tris"]) for q in polys if q["type"] == T_WALL]
    ov = fc.party_wall_overlaps(walls)
    cuts = {}
    for k, r in enumerate(ov):
        cuts.setdefault(r["a"], []).append((r["frame"], r["region"])); cuts.setdefault(r["b"], []).append((r["frame"], r["region"]))
    cut_info = dict(overlaps=len(ov), walls_cut=len(cuts), area_cut_m2=float(sum(r["area"] for r in ov)) * 2)
    for pid, cl in cuts.items():
        new, _, touched, info = fc.cut_triangles(polys[pid]["tris"], cl)
        polys[pid]["tris_uncut"] = polys[pid]["tris"]; polys[pid]["tris"] = new
    # caps and probes (moved into prior_propagation_v5.caps, unchanged)
    caps, probes, cap_rec, cap_ov, probe_ov = capm.caps_and_probes(polys, ov)
    # assemble the prior mesh (polygons + caps) and the probe mesh
    tri_list, tri_surf, tri_type, tri_bld = [], [], [], []
    bnames = sorted({q["building"] for q in polys})
    bidx = {b: i for i, b in enumerate(bnames)}
    for q in polys:
        if len(q["tris"]) == 0:
            continue
        tri_list.append(q["tris"]); tri_surf.append(np.full(len(q["tris"]), q["pid"])); tri_type.append(np.full(len(q["tris"]), q["type"]))
        tri_bld.append(np.full(len(q["tris"]), bidx[q["building"]]))
    T_all = np.concatenate(tri_list); S_all = np.concatenate(tri_surf); Y_all = np.concatenate(tri_type); B_all = np.concatenate(tri_bld)
    n_before = len(T_all)
    if caps:
        C = np.array(caps)
        T_cap = np.concatenate([T_all, C]); S_cap = np.concatenate([S_all, CAP_BASE + np.arange(len(C)) // 2])
        Y_cap = np.concatenate([Y_all, np.full(len(C), T_CAP)]); B_cap = np.concatenate([B_all, np.full(len(C), -1)])
    else:
        T_cap, S_cap, Y_cap, B_cap = T_all, S_all, Y_all, B_all
    to_vf = lambda T: (T.reshape(-1, 3), np.arange(len(T) * 3).reshape(-1, 3))
    V, F = to_vf(T_cap)
    PV, PF = to_vf(np.array(probes)) if probes else (np.zeros((0, 3)), np.zeros((0, 3), np.int64))
    table = []
    for q in polys:
        if len(q["tris"]) == 0:
            continue
        ar = 0.5 * np.linalg.norm(np.cross(q["tris"][:, 1] - q["tris"][:, 0], q["tris"][:, 2] - q["tris"][:, 0]), axis=1).sum()
        table.append(dict(ext=q["pid"], gml=q["gml"], building=q["building"], type="roof" if q["type"] == T_ROOF else "wall",
                          kind=1 if abs(q["normal"][2]) >= ROOF_NZ else 2, normal=q["normal"].tolist(), o=q["o"].tolist(),
                          area_m2=float(ar), cut=q["pid"] in cuts))
    return dict(V=V, F=F, tri_surface=S_cap, tri_type=Y_cap, tri_building=B_cap, n_poly_tris=n_before, PV=PV, PF=PF,
                building_names=np.array(bnames), cap_overlap=np.array(cap_ov, np.int64), probe_overlap=np.array(probe_ov, np.int64)), table, cut_info, cap_rec


def als_mesh(rng):
    wide = widen(rng, CFG["ranges"]["prior_margin_m"])
    P = range_polygon(wide); lo, hi = P.min(0), P.max(0)
    xyz, cls, multi = read_als(lo, hi, classes=(2, 6))
    key = np.round(xyz[:, :2] * 1000).astype(np.int64)
    _, keep = np.unique(key, axis=0, return_index=True)
    keep = np.sort(keep)
    xyz, cls, multi = xyz[keep], cls[keep], multi[keep]
    c = xyz[:, :2].mean(0)
    tri = Delaunay(xyz[:, :2] - c)
    F = tri.simplices.astype(np.int64)
    bt = (cls[F] == 6).sum(1) >= 2
    ts, n_tri, a_tri = surf.tin_surfaces(xyz, F, 0.5, building=bt)
    # orient normals upward (Delaunay in XY: counter-clockwise -> +z)
    flip = n_tri[:, 2] < 0
    F[flip] = F[flip][:, [0, 2, 1]]; n_tri[flip] *= -1
    table = []
    for s in np.unique(ts[ts >= 0]):
        sel = ts == s
        nn = (n_tri[sel] * a_tri[sel, None]).sum(0); nn /= np.linalg.norm(nn)
        table.append(dict(ext=int(s), type="tin", kind=1, normal=nn.tolist(), area_m2=float(a_tri[sel].sum()), n_tri=int(sel.sum())))
    return dict(V=xyz, F=F, cls=cls, multi=multi, tri_surface=ts, tri_normal=n_tri, tri_area=a_tri, building_tri=bt), table, (lo, hi)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("range_id"); ap.add_argument("--ranges-file", default="/prep/step01/ranges.json")
    ap.add_argument("--out-sub", default="s02"); ap.add_argument("--margin", type=float, default=None,
                                                                        help="prior margin beyond the range (boxes: 0, the context band is part of the range)")
    a = ap.parse_args()
    if a.margin is not None:
        CFG["ranges"]["prior_margin_m"] = a.margin
    rngs = json.loads(Path(a.ranges_file).read_text()) if a.ranges_file.startswith("/") else json.loads((OUT / a.ranges_file).read_text())
    rng = rngs[a.range_id]
    D = OUT / a.out_sub / a.range_id; D.mkdir(parents=True, exist_ok=True)
    blds = json.loads((SURVEY / "s1/lod2_buildings.json").read_text())
    sp = CFG["judgment"]["cell_m"]
    wide = widen(rng, CFG["ranges"]["prior_margin_m"]); Pw = range_polygon(wide)
    rect = np.array([Pw.min(0), Pw.max(0)])
    # LoD2
    m, table, cut_info, cap_rec = lod2_mesh(rng, blds)
    np.savez_compressed(D / "lod2_mesh.npz", **m)
    srf = [dict(ext=r["ext"], normal=r["normal"], o=r["o"]) for r in table]
    st = locs.build_plane_store(m["V"], m["F"], m["tri_surface"], srf, rect, sp)
    locs.save_store(D / "lod2_store.npz", st)
    jdump(D / "lod2_surfaces.json", dict(surfaces=table, party_wall=cut_info, caps=cap_rec, n_caps=int((m["tri_type"] == T_CAP).sum() // 2),
                                         n_probe_tris=int(len(m["PF"])), rect=rect.tolist()))
    log(a.range_id, "LoD2 polygons", len(table), "buildings", len(m["building_names"]), "party overlaps", cut_info, "caps", len(cap_rec),
        "units", len(st["loc_area"]))
    # footprints (LoD2 GroundSurface rings) of the buildings meeting range + margin: reporting units only
    Pc = Polygon(range_polygon(rng)) if rng["kind"] != "polygon" else Polygon(rng["polygon_local"])
    fps = []
    for b in blds:
        if b["id"] not in set(m["building_names"].tolist()):
            continue
        for p in b["surfaces"]["ground"]:
            ring = np.stack(global_to_local(np.asarray(p["ext"])[:, 0], np.asarray(p["ext"])[:, 1]), 1)
            if len(ring) < 4:
                continue
            pg = Polygon(ring).buffer(0)
            fps.append(dict(building=b["id"], ring_local=ring.tolist(), area_m2=float(pg.area),
                            inside_share=float(pg.intersection(Pc).area / pg.area) if pg.area > 0 else 0.0))
    jdump(D / "footprints.json", dict(footprints=fps))
    jdump(D / "range.json", rng)
    # ALS
    t, ttable, _ = als_mesh(rng)
    np.savez_compressed(D / "als_mesh.npz", **t)
    st2 = locs.build_tin_store(t["V"], t["F"], t["tri_surface"], t["tri_normal"], t["tri_area"], [dict(ext=r["ext"]) for r in ttable], rect, sp)
    locs.save_store(D / "als_store.npz", st2)
    jdump(D / "als_surfaces.json", dict(surfaces=ttable, n_points=int(len(t["V"])), n_tri=int(len(t["F"])),
                                        class_counts={int(k): int(v) for k, v in zip(*np.unique(t["cls"], return_counts=True))}, rect=rect.tolist()))
    log(a.range_id, "ALS points", len(t["V"]), "tris", len(t["F"]), "surfaces", len(ttable), "units", len(st2["loc_area"]))


if __name__ == "__main__":
    main()
