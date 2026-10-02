"""PHD-MAIN-PREP-MEASURE-v1 step 01 (jointbuildgs:dev, CPU): search ranges, candidate views and B0 view conditions.

  ranges.json   R1-R5 (regions_v1), B0 (stage-1 crop), SW (three footprints + 15 m), R3E (R3 + 10 m east), B0BLD (target footprint)
  views.json    per range: candidates / training / evaluation (9-15 audit rule re-implemented; R1-R5 must reproduce the
                frozen lists exactly), nadir / oblique counts
  b0.json       author views in the common set, pose-frame differences author vs common, A15 / A9 / A3 / COVER lists
scientific_verdict: null."""
import json

import numpy as np
from matplotlib.path import Path as MPath

from common import (ART, CFG, DENSE, OUT, REPO, SHIFT, SURVEY, GRID_H, GRID_W, Views, global_to_local, inside_range, jdump, log,
                    range_polygon, read_depth_bin, read_fused_rows, read_images_bin, read_cameras_bin, xy_to_uv)

D = OUT / "step01"; D.mkdir(parents=True, exist_ok=True)
rcfg = json.loads((REPO / CFG["ranges"]["regions_config"]).read_text())
ranges = {}
for r in rcfg["regions"]:
    ranges[r["id"]] = dict(id=r["id"], kind="uv_box", u_m=r["u_m"], v_m=r["v_m"], label=r["label_ko"])
pj = json.loads((ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())
sh = pj["shift_global_to_local"]
(x0, y0), (x1, y1) = pj["als_crop_local_xy"]
E0, N0, E1, N1 = x0 - sh[0], y0 - sh[1], x1 - sh[0], y1 - sh[1]
lx0, ly0 = global_to_local(E0, N0); lx1, ly1 = global_to_local(E1, N1)
ranges["B0"] = dict(id="B0", kind="xy_rect", xy_rect_local=[float(lx0), float(ly0), float(lx1), float(ly1)],
                    global_rect=[E0, N0, E1, N1], label="B0 crop (stage 1)")
blds = {b["id"]: b for b in json.loads((SURVEY / "s1/lod2_buildings.json").read_text())}


def footprint_local(bid):
    out = []
    for p in blds[bid]["surfaces"]["ground"]:
        ext = np.asarray(p["ext"], np.float64)
        out.append(np.stack(global_to_local(ext[:, 0], ext[:, 1]), 1))
    return out


uvs = np.concatenate([xy_to_uv(np.concatenate(footprint_local(b))) for b in ("DEBY_LOD2_4907510", "DEBY_LOD2_4907508", "DEBY_LOD2_4907207")])
ranges["SW"] = dict(id="SW", kind="uv_box", u_m=[float(np.floor(uvs[:, 0].min() - 15)), float(np.ceil(uvs[:, 0].max() + 15))],
                    v_m=[float(np.floor(uvs[:, 1].min() - 15)), float(np.ceil(uvs[:, 1].max() + 15))],
                    label="south-west: C05 (4907510), C06 (4907508), C02 (4907207) + 15 m")
ranges["R3E"] = dict(id="R3E", kind="uv_box", u_m=CFG["ranges"]["R3E"]["u_m"], v_m=CFG["ranges"]["R3E"]["v_m"], label="R3 + 10 m east (C04)")
b0fp = max(footprint_local("DEBY_LOD2_4959323"), key=len)
ranges["B0BLD"] = dict(id="B0BLD", kind="polygon", polygon_local=b0fp.tolist(), label="B0 target building footprint (COVER condition)")
for r in ranges.values():
    if r["kind"] != "polygon":
        P = range_polygon(r)
        r["polygon_local"] = P.tolist()
        r["polygon_epsg25832"] = (P + SHIFT[:2]).tolist()
        e = np.ptp(P, 0); r["area_m2"] = float(abs(0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])))
jdump(D / "ranges.json", ranges)
log("ranges", {k: round(v.get("area_m2", 0)) for k, v in ranges.items()})


def in_poly(xy, r):
    if r["kind"] == "polygon":
        return MPath(np.asarray(r["polygon_local"])).contains_points(xy)
    return inside_range(xy, r)


# ---------------------------------------------------------------------------------------------- candidate rule
xyz, rows = read_fused_rows(16)
zb = CFG["ranges"]["z_m"]
ok = np.isfinite(xyz).all(1) & (xyz[:, 2] >= zb[0]) & (xyz[:, 2] < zb[1])
# the audit pre-cut the reference to its R1-R5 window before the voxel step; voxels inside R1-R5 keep the same first row
# either way, and the new ranges need points outside that window
xyz = xyz[ok]
_, first = np.unique(np.floor(xyz / 1.0).astype(np.int32), axis=0, return_index=True)
ref = xyz[np.sort(first)].astype(np.float64)
refs = {rid: ref[in_poly(ref[:, :2], r)] for rid, r in ranges.items()}
log("reference points", {k: len(v) for k, v in refs.items()})
V = Views()
fx, fy, cx, cy = V.K
yy, xx = np.indices((GRID_H, GRID_W), dtype=np.float64)
nrays_cam = np.stack([(xx - cx) / fx, (yy - cy) / fy, np.ones_like(xx)], -1).reshape(-1, 3)   # audit ray_grid: integer pixels
proj = {rid: np.zeros(len(V.names), np.int64) for rid in ranges}
native = {rid: np.zeros(len(V.names), np.int64) for rid in ranges}
for i, n in enumerate(V.names):
    R, t = V.R(n), V.t(n)
    for rid, P in refs.items():
        Xc = P @ R.T + t
        z = Xc[:, 2]; pos = z > 1e-6
        u = np.floor(fx * Xc[:, 0] / np.where(pos, z, 1) + cx + 0.5); v = np.floor(fy * Xc[:, 1] / np.where(pos, z, 1) + cy + 0.5)
        proj[rid][i] = int((pos & (u >= 0) & (u < GRID_W) & (v >= 0) & (v < GRID_H)).sum())
    d = read_depth_bin(DENSE / "stereo/depth_maps" / f"{n}.geometric.bin").ravel()
    nv = np.isfinite(d) & (d > 0)
    X = ((nrays_cam[nv] * d[nv, None]) - t) @ R
    zok = (X[:, 2] >= zb[0]) & (X[:, 2] < zb[1])
    for rid, r in ranges.items():
        native[rid][i] = int((zok & in_poly(X[:, :2], r)).sum())
    if i % 200 == 0:
        log("views", i)
views = {}
tilts = {n: V.tilt(n) for n in V.names}
for rid in ranges:
    nref = len(refs[rid]); minimum = max(10, int(np.ceil(0.01 * nref)))
    cand = [n for i, n in enumerate(V.names) if proj[rid][i] >= minimum or native[rid][i] >= 100]
    ev = [n for k, n in enumerate(cand) if k % 8 == 0]; tr = [n for k, n in enumerate(cand) if k % 8 != 0]
    cnt = lambda L: dict(total=len(L), nadir=int(sum(tilts[n] <= CFG["views"]["nadir_max_tilt_deg"] for n in L)),
                         oblique=int(sum(tilts[n] > CFG["views"]["nadir_max_tilt_deg"] for n in L)))
    views[rid] = dict(candidates=cand, train=tr, evaluation=ev, reference_points=nref, projected_minimum=minimum,
                      counts=dict(candidates=cnt(cand), train=cnt(tr), evaluation=cnt(ev)))
# reproduction of the frozen R1-R5 lists
exp = ART / CFG["ranges"].get("exports", "phase-payloads/phd/region_view_support_v1/PHD-R1R5-VIEW-SUPPORT-v1/attempt_20260915T130845Z_TkeMtl/exports")
repro = {}
for rid in ("R1", "R2", "R3", "R4", "R5"):
    frozen = [l.strip() for l in open(exp / f"{rid}_candidates_names.txt") if l.strip()]
    repro[rid] = dict(frozen=len(frozen), recomputed=len(views[rid]["candidates"]), identical=frozen == views[rid]["candidates"],
                      only_frozen=sorted(set(frozen) - set(views[rid]["candidates"]))[:10],
                      only_recomputed=sorted(set(views[rid]["candidates"]) - set(frozen))[:10])
    if frozen != views[rid]["candidates"]:      # the frozen lists rule; recomputation is a check
        views[rid]["recomputed_candidates"] = views[rid]["candidates"]
        views[rid]["candidates"] = frozen
        views[rid]["evaluation"] = [n for k, n in enumerate(frozen) if k % 8 == 0]
        views[rid]["train"] = [n for k, n in enumerate(frozen) if k % 8 != 0]
log("reproduction", json.dumps({k: (v["frozen"], v["recomputed"], v["identical"]) for k, v in repro.items()}))
jdump(D / "views.json", dict(views=views, reproduction_R1_R5=repro, tilts=tilts, rule=CFG["views"]["candidate_rule"]))

# ---------------------------------------------------------------------------------------------- B0 conditions
ex = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
aim = read_images_bin(ex / "sparse/0/images.bin")
acam = read_cameras_bin(ex / "sparse/0/cameras.bin")
names15 = sorted(aim)
diff = {}
for n in names15:
    a = aim[n]; c = V.ims[n]
    Ra, Rc = a["R"], c["R"]
    ang = float(np.degrees(np.arccos(np.clip((np.trace(Ra @ Rc.T) - 1) / 2, -1, 1))))
    Ca = -Ra.T @ a["t"]; Cc = -Rc.T @ c["t"]
    diff[n] = dict(rotation_deg=ang, centre_author_minus_common=(Ca - Cc).tolist())
dc = np.array([v["centre_author_minus_common"] for v in diff.values()])
idx9 = np.round(np.linspace(0, 14, 9)).astype(int); idx3 = np.round(np.linspace(0, 14, 3)).astype(int)
sub = lambda idx: [names15[i] for i in idx]
cond = {}
for key, L in (("A15", names15), ("A9", sub(idx9)), ("A3", sub(idx3))):
    if key == "A15":   # r5-r10 / GeoGS llffhold 8: positions 0 and 8 (0002, 0016)
        test = [n for k, n in enumerate(L) if k % 8 == 0]; train = [n for k, n in enumerate(L) if k % 8 != 0]
    else:              # order: 8 + 1 and 2 + 1 -> the first view (0002, GeoGS position 0) is the one test view
        test = L[:1]; train = L[1:]
    cond[key] = dict(all=L, train=train, test=test)
cover = views["B0BLD"]
cond["COVER"] = dict(all=cover["candidates"], train=cover["train"], test=cover["evaluation"])
for k, c in cond.items():
    c["nadir_train"] = int(sum(tilts[n] <= 20 for n in c["train"])); c["oblique_train"] = len(c["train"]) - c["nadir_train"]
b0 = dict(author_views_in_common=all(n in V.ims for n in names15), author_names=names15,
          author_camera={k: dict(model=v["model"], w=v["w"], h=v["h"], p=v["p"].tolist()) for k, v in acam.items()},
          pose_difference=dict(per_view=diff, max_rotation_deg=float(max(v["rotation_deg"] for v in diff.values())),
                               centre_shift_mean=dc.mean(0).tolist(), centre_shift_std=dc.std(0).tolist()),
          conditions=cond)
jdump(D / "b0.json", b0)
log("B0", b0["author_views_in_common"], "rot max", round(b0["pose_difference"]["max_rotation_deg"], 6), "shift", np.round(dc.mean(0), 4), np.round(dc.std(0), 5),
    {k: (len(v["train"]), len(v["test"])) for k, v in cond.items()})
log("counts", {k: v["counts"]["train"] for k, v in views.items()})
