"""Surfaces that no photo sees (jointbuildgs:dev, CPU): did each condition keep the prior there? scientific_verdict: null.

  python export_unseen.py [--min_px 500] [--tol 0.3]
Mounts: /s2 (payload, rw for eval/ and dashboard/surfels/), /artifacts/JointBuildGS (ro).

The intent table only counts pixels of the 15 photos, so surfaces that no photo sees are outside it. Here they are read from
the Gaussians themselves. Unseen faces = target LoD2 faces with fewer than --min_px pixels over the 15 views (training
resolution). Region of an unseen roof face = its polygon minus a 2 m band around the seen roof faces (the shared ridge is
seen); of an unseen wall = its along-face extent (minus 1 m at each end) x its height (0.5 m above the base of the front wall
3403 up to the top derived from the face's mean height). A surfel belongs to the region when its centre lies within --tol of
the face plane (roofs: the registered v2 LoD2 mesh the prior maps were rendered from). Coverage = share of the region's 1 m cells that hold an opaque surfel (alpha > 0.5). The start is read from
the condition's input.ply (same test, points taken as opaque). The +1 m scenes raise only the seen main roof 3396, so the
unseen faces keep their normal-scene plane in every setting.
Outputs
  eval/unseen_30000.csv                         per condition and group (unseen roof / unseen walls): area, surfels,
                                                opaque, from prior, locked, coverage at start and at 30,000
  dashboard/surfels/unseen_<setting>_<cond>.bin   magic JBUN3D1, uint32 count, uint32 floats (= 7), float32 records:
                                                xyz, alpha, origin (1 prior, 0 image, -1 unknown), locked, group (1 roof, 2 wall)
  dashboard/surfels/unseen_ref.bin              magic JBUR3D1, uint32 count, uint32 floats (= 4): a 0.5 m grid on the
                                                unseen regions of the LoD2 faces (xyz, group) = where the old surface is
  dashboard/surfels/unseen_index.json           per file: coverage per group and counts; the unseen faces; the section
                                                frame of the viewer (front wall 3403 outward normal and centre, base height)."""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
from plyfile import PlyData
from shapely import vectorized
from shapely.geometry import Polygon
from shapely.ops import unary_union

S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; OUT = S2 / "dashboard/surfels"
ART = Path("/artifacts/JointBuildGS")
POLYS = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json"
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
TRAIN = (1600, 1157)
ap = argparse.ArgumentParser()
ap.add_argument("--min_px", type=int, default=500)
ap.add_argument("--tol", type=float, default=0.3)
a = ap.parse_args()
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
PJ = {p["poly_index"]: p for p in json.loads(POLYS.read_text())["polygons"]}

# which target faces the 15 photos see
seen_px = {f: 0 for f in ROOF + WALL}
for p in sorted((MAPS / "faceid").glob("*.npy")):
    F = cv2.resize(np.load(p).astype(np.float32), TRAIN, interpolation=cv2.INTER_NEAREST).astype(np.int32)
    u, c = np.unique(F, return_counts=True)
    for f, n in zip(u, c):
        if int(f) in seen_px:
            seen_px[int(f)] += int(n)
UNSEEN_ROOF = [f for f in ROOF if seen_px[f] < a.min_px]
UNSEEN_WALL = [f for f in WALL if seen_px[f] < a.min_px]
print("pixels per face:", seen_px); print("unseen roof", UNSEEN_ROOF, "unseen walls", UNSEEN_WALL, flush=True)

# base height = base of the front wall 3403 (as the sections)
f3 = PJ[3403]; r3 = np.array(f3["ring_local_xy"]); n3 = np.array(f3["normal"])[:2]; n3 /= np.linalg.norm(n3)
samples = np.load(S2 / "inputs/points/prior_M_N.npz")["xyz"].astype(np.float64)
rel = samples[:, :2] - r3.mean(0)
Z0 = float(samples[(np.abs(rel @ np.array([-n3[1], n3[0]])) < 20) & (np.abs(rel @ n3) < 0.3), 2].min())


MESH = np.load(ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2/inputs_v2/lod2_v2_nominal_local.npz")


def roof_plane(f):
    """Plane of a roof face from the registered v2 LoD2 mesh (+0.12 m), the mesh the stage-2 prior maps were rendered from."""
    vv = MESH["vertices_local"][np.unique(MESH["faces"][MESH["poly_of_tri"] == f])]
    n = np.cross(vv[1] - vv[0], vv[2] - vv[0]); n /= np.linalg.norm(n); c = vv.mean(0)
    return lambda x, y: c[2] - (n[0] * (x - c[0]) + n[1] * (y - c[1])) / n[2]


seen_roofs = unary_union([Polygon(PJ[f]["ring_local_xy"]) for f in ROOF if f not in UNSEEN_ROOF])
REG = []                                     # (group, face, test(xyz) -> bool mask, cells(list of cell ids), grid points)
for f in UNSEEN_ROOF:
    poly = Polygon(PJ[f]["ring_local_xy"]).difference(seen_roofs.buffer(2.0))
    if poly.is_empty or poly.area < 1:
        continue
    zf = roof_plane(f)
    gx, gy = np.meshgrid(np.arange(poly.bounds[0], poly.bounds[2], 0.5) + 0.25, np.arange(poly.bounds[1], poly.bounds[3], 0.5) + 0.25)
    gin = vectorized.contains(poly, gx, gy); grid = np.stack([gx[gin], gy[gin], zf(gx[gin], gy[gin])], 1)
    REG.append(dict(group=1, face=f, area=poly.area, poly=poly, zf=zf, grid=grid))
for f in UNSEEN_WALL:
    p = PJ[f]; r = np.array(p["ring_local_xy"]); n = np.array(p["normal"], float)[:2]
    if np.linalg.norm(n) < 0.5:
        continue
    n /= np.linalg.norm(n); al = np.array([-n[1], n[0]]); c = r.mean(0); s = (r - c) @ al
    lo, hi = s.min() + 1.0, s.max() - 1.0
    top = 2 * p["z_local_mean"] - Z0                                     # rectangle from the base: mean height is the middle
    if hi - lo < 1 or top - Z0 < 2:
        continue
    ga, gz = np.meshgrid(np.arange(lo, hi, 0.5) + 0.25, np.arange(Z0 + 0.5, top, 0.5) + 0.25)
    grid = np.stack([c[0] + ga.ravel() * al[0], c[1] + ga.ravel() * al[1], gz.ravel()], 1)
    REG.append(dict(group=2, face=f, area=(hi - lo) * (top - Z0 - 0.5), c=c, n=n, al=al, lo=lo, hi=hi, zlo=Z0 + 0.5, ztop=top, grid=grid))
print("unseen regions:", [(r["face"], round(r["area"])) for r in REG], flush=True)


def members(xyz):
    """For each point: group (0 none) and cell id within its region (for coverage), plus region index."""
    grp = np.zeros(len(xyz), np.int8); cell = np.full(len(xyz), -1, np.int64); rid = np.full(len(xyz), -1, np.int32)
    for i, R in enumerate(REG):
        x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        if R["group"] == 1:
            b = R["poly"].bounds
            m = (x > b[0]) & (x < b[2]) & (y > b[1]) & (y < b[3])
            k = np.flatnonzero(m)
            k = k[vectorized.contains(R["poly"], x[k], y[k]) & (np.abs(z[k] - R["zf"](x[k], y[k])) < a.tol)]
            ci = np.floor(x[k] - b[0]).astype(np.int64) * 100000 + np.floor(y[k] - b[1]).astype(np.int64)
        else:
            rel = xyz[:, :2] - R["c"]; aa, nn = rel @ R["al"], rel @ R["n"]
            k = np.flatnonzero((np.abs(nn) < a.tol) & (aa > R["lo"]) & (aa < R["hi"]) & (z > R["zlo"]) & (z < R["ztop"]))
            ci = np.floor(aa[k] - R["lo"]).astype(np.int64) * 100000 + np.floor(z[k] - R["zlo"]).astype(np.int64)
        grp[k] = R["group"]; cell[k] = ci; rid[k] = i
    return grp, cell, rid


def n_cells(R):
    if R["group"] == 1:
        b = R["poly"].bounds
        gx, gy = np.meshgrid(np.arange(b[0], b[2], 1.0) + 0.5, np.arange(b[1], b[3], 1.0) + 0.5)
        m = vectorized.contains(R["poly"], gx, gy)
        return set((np.floor(gx[m] - b[0]).astype(np.int64) * 100000 + np.floor(gy[m] - b[1]).astype(np.int64)).tolist())
    ga, gz = np.meshgrid(np.arange(R["lo"], R["hi"], 1.0) + 0.5, np.arange(R["zlo"], R["ztop"], 1.0) + 0.5)
    return set((np.floor(ga.ravel() - R["lo"]).astype(np.int64) * 100000 + np.floor(gz.ravel() - R["zlo"]).astype(np.int64)).tolist())


CELLS = [n_cells(R) for R in REG]


def coverage(grp, cell, rid, opaque):
    out = {}
    for g in (1, 2):
        tot = sum(len(CELLS[i]) for i, R in enumerate(REG) if R["group"] == g)
        cov = 0
        for i, R in enumerate(REG):
            if R["group"] != g:
                continue
            m = (rid == i) & opaque
            cov += len(set(cell[m].tolist()) & CELLS[i])
        out[g] = cov / tot if tot else None
    return out


def read_ply(path):
    v = PlyData.read(str(path))["vertex"]; names = [p.name for p in v.properties]
    xyz = np.stack([np.asarray(v[k], np.float64) for k in "xyz"], 1)
    alpha = 1 / (1 + np.exp(-np.asarray(v["opacity"], np.float64))) if "opacity" in names else np.ones(len(xyz))
    origin = np.asarray(v["origin"], np.float32) if "origin" in names else np.full(len(xyz), -1, np.float32)
    return xyz, alpha, origin


OUT.mkdir(parents=True, exist_ok=True)
grid = np.concatenate([np.concatenate([R["grid"], np.full((len(R["grid"]), 1), R["group"])], 1) for R in REG]).astype(np.float32)
with (OUT / "unseen_ref.bin").open("wb") as fh:
    fh.write(b"JBUR3D1\0"); fh.write(np.uint32(len(grid)).tobytes()); fh.write(np.uint32(4).tobytes()); grid.tofile(fh)
index = dict(faces=dict(roof=UNSEEN_ROOF, wall=UNSEEN_WALL), area=dict(roof=sum(R["area"] for R in REG if R["group"] == 1),
             wall=sum(R["area"] for R in REG if R["group"] == 2)), tol_m=a.tol, files={},
             frame=dict(front_normal=n3.tolist(), front_centre=r3.mean(0).tolist(), base_z=Z0))   # section frame for the viewer
rows, done = [], {}
for setting, conds in SETTINGS.items():
    for cond in conds:
        if cond not in done:
            run = S2 / "runs" / cond / "model"
            xyz, alpha, origin = read_ply(run / "point_cloud/iteration_30000/point_cloud.ply")
            locked = np.zeros(len(xyz), np.float32)
            dump = run / "dump/iteration_30000/gaussians.npz"
            if dump.exists():
                L = np.load(dump)["locked"]
                if L.shape[0] == len(xyz):
                    locked = L.astype(np.float32)
            grp, cell, rid = members(xyz)
            cov = coverage(grp, cell, rid, alpha > 0.5)
            ixyz, _, _ = read_ply(run / "input.ply")
            igrp, icell, irid = members(ixyz)
            cov0 = coverage(igrp, icell, irid, np.ones(len(ixyz), bool))
            k = np.flatnonzero(grp > 0)
            rec = np.stack([xyz[k, 0], xyz[k, 1], xyz[k, 2], alpha[k], origin[k], locked[k], grp[k]], 1).astype(np.float32)
            fname = f"unseen_{cond}.bin"
            with (OUT / fname).open("wb") as fh:
                fh.write(b"JBUN3D1\0"); fh.write(np.uint32(len(rec)).tobytes()); fh.write(np.uint32(7).tobytes()); rec.tofile(fh)
            info = dict(file=fname)
            for g, gname in ((1, "roof"), (2, "wall")):
                m = grp == g
                info[gname] = dict(coverage_start=cov0[g], coverage=cov[g], surfels=int(m.sum()), opaque=int((m & (alpha > 0.5)).sum()),
                                   from_prior=int((m & (origin == 1)).sum()), locked=int((m & (locked > 0)).sum()))
                rows.append(dict(condition=cond, group=gname, area_m2=round(index["area"][gname], 1), **info[gname]))
            done[cond] = info
            print(cond, {g: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in info[g].items()} for g in ("roof", "wall")}, flush=True)
        index["files"][f"{setting}/{cond}"] = done[cond]
(OUT / "unseen_index.json").write_text(json.dumps(index, indent=1))
with (S2 / "eval/unseen_30000.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("done")
