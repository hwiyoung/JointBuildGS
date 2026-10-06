"""PHD-MAIN-STAGE0-v1 5.1: inputs of fork r12 for one box from the v6 measurement's box runs (jointbuildgs:dev, CPU) = the
discard task's fork_inputs.py with three changes: the store is the v6 moved store (frame_shift, prior_kind kept; LoD2 prior
points = its centres, which are the registered centres), the product's votes given to the fork are the current rule's
(vote_tau; the fork applies its rule on the tallies and checks the states), and the mask-off sets are optional (only the
switch site has a mask-off run).

  python fork_inputs_v6.py <box> --run-sub s61/box --export-sub s61/export [--maskoff-run-sub s61/box_maskoff
                           --maskoff-export-sub s61/export_maskoff] --out-sub fork_inputs/s61

Training resolution = the measurement grid 1024 x 741 (configs discard_v1 'fork_inputs'):
  images/        training and evaluation views of prep step06/box_views.json resized to the grid (training views without a
                 geometric depth map are left out, as in the measurement); JPEG 95
  scene_<prior>/ sparse/0/cameras.bin (one PINHOLE camera = common.Views.K at the grid), images.bin (937-model poses, no 2-D
                 points), points3D.ply + origin.npy (initial cloud), images -> ../images, jbgs_calibration.json (K with
                 cx - 0.5, cy - 0.5: the rasterizer's pixel i = the measurement's pixel centre i + 0.5)
  split.json     {"train": [...], "test": [...]} image names (fork r11: JBGS_SPLIT_JSON)
  maps/          conf, mvs, conf_photometric, mvs_photometric and per prior prior_<p>, tau_<p>, locmap_<p>, markmap_<p>(_maskoff),
                 markcode_<p>(_maskoff): relative symlinks to the measurement's export directories
  store_<p>.npz  the box run's store + state/vote/E/n_seeing/n_supporting of tag 'data' and 'data_maskoff'
  pairs_<p>(_maskoff).npz, knn_<p>(_maskoff).npz   the run's unit_view_pairs and knn (rule variants)
  seat_<p>.npy, prior_normal_<p>.npy               aligned with scene_<p>/points3D.ply
Initial cloud: image points = sparse points of the box's training-image subset model inside the box range; LoD2 = one point per
patch centre (registered), seat = its surface, normal = the face's Newell normal; ALS = the TIN vertices inside the box range
(registered), seat = vertex_surface, normal = the TIN vertex normal (the fork's cell method overrides it on patches).
scientific_verdict: null."""
import argparse
import json
import os
import struct
from pathlib import Path

import cv2
import numpy as np

from common import DENSE, GRID_H, GRID_W, OUT, PREP, Views, inside_range, jdump, log
from src.phd.prior_propagation_v6 import locations as locs
from src.phd.prior_propagation_v6 import orientation as ori
from src.phd.prior_propagation_v6 import surfaces as surf


def read_points3d_bin(p):
    data = Path(p).read_bytes(); off = 0
    n = struct.unpack_from("<Q", data, off)[0]; off += 8
    xyz = np.zeros((n, 3)); rgb = np.zeros((n, 3), np.uint8)
    for i in range(n):
        off += 8
        xyz[i] = struct.unpack_from("<ddd", data, off); off += 24
        rgb[i] = struct.unpack_from("<BBB", data, off); off += 3
        off += 8
        tl = struct.unpack_from("<Q", data, off)[0]; off += 8 + 8 * tl
    return xyz, rgb


def write_cameras_bin(p, K):
    with open(p, "wb") as f:
        f.write(struct.pack("<Q", 1))
        f.write(struct.pack("<iiQQ", 1, 1, GRID_W, GRID_H))
        f.write(struct.pack("<dddd", *K))


def write_images_bin(p, recs):
    with open(p, "wb") as f:
        f.write(struct.pack("<Q", len(recs)))
        for i, (name, q, t) in enumerate(recs, start=1):
            f.write(struct.pack("<i", i)); f.write(struct.pack("<dddd", *q)); f.write(struct.pack("<ddd", *t))
            f.write(struct.pack("<i", 1)); f.write(name.encode() + b"\x00"); f.write(struct.pack("<Q", 0))


def store_ply(path, xyz, rgb):
    hdr = ("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\n"
           "property float nx\nproperty float ny\nproperty float nz\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n") % len(xyz)
    dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    el = np.zeros(len(xyz), dt)
    el["x"], el["y"], el["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    el["red"], el["green"], el["blue"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with open(path, "wb") as f:
        f.write(hdr.encode()); f.write(el.tobytes())


def rel_link(target, link):
    link = Path(link)
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(os.path.relpath(target, link.parent), link)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("box")
    ap.add_argument("--run-sub", required=True); ap.add_argument("--export-sub", required=True)
    ap.add_argument("--maskoff-run-sub", default=None); ap.add_argument("--maskoff-export-sub", default=None)
    ap.add_argument("--out-sub", required=True)
    a = ap.parse_args()
    box = a.box
    O = OUT / a.out_sub / box; O.mkdir(parents=True, exist_ok=True)
    bv = json.loads((PREP / "step06/box_views.json").read_text())["views"][box]
    rng = json.loads((PREP / "step06/box_ranges.json").read_text())[box]
    s_l = json.loads((OUT / a.run_sub / box / "LoD2" / "summary.json").read_text())
    dropped = set(s_l["views_without_depth_map"])
    train = [v for v in bv["train"] if v not in dropped]; test = list(bv["evaluation"])
    stem = lambda n: n.rsplit(".", 1)[0]
    V = Views()
    rep = dict(box=box, train=len(train), test=len(test), dropped_training_views=sorted(dropped), resolution=[GRID_W, GRID_H])
    # images
    (O / "images").mkdir(exist_ok=True)
    for n in train + test:
        q = O / "images" / f"{stem(n)}.jpg"
        if not q.exists():
            img = cv2.imread(str(DENSE / "images" / n))
            cv2.imwrite(str(q), cv2.resize(img, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 95])
    fx, fy, cx, cy = V.K
    calib = dict(schema="jointbuildgs.geogs.source_calibration.v1",
                 note="K of the measurement grid with cx - 0.5, cy - 0.5 (the rasterizer's pixel i = the measurement's pixel centre i + 0.5)",
                 images={stem(n): dict(width=GRID_W, height=GRID_H, K=[[fx, 0.0, cx - 0.5], [0.0, fy, cy - 0.5], [0.0, 0.0, 1.0]]) for n in train + test})
    recs = [(f"{stem(n)}.jpg", V.ims[n]["q"], V.ims[n]["t"]) for n in sorted(train + test)]
    jdump(O / "split.json", dict(train=[stem(n) for n in train], test=[stem(n) for n in test]))
    # maps (relative symlinks to the measurement's exports)
    M = O / "maps"; M.mkdir(exist_ok=True)
    EX = {p: OUT / a.export_sub / box / p for p in ("LoD2", "ALS")}
    MO = bool(a.maskoff_run_sub and a.maskoff_export_sub)
    EXM = {p: OUT / a.maskoff_export_sub / box / p for p in ("LoD2", "ALS")} if MO else {}
    rel_link(EX["LoD2"] / "conf", M / "conf"); rel_link(EX["LoD2"] / "mvs", M / "mvs")
    if MO:
        rel_link(EXM["LoD2"] / "conf", M / "conf_photometric"); rel_link(EXM["LoD2"] / "mvs", M / "mvs_photometric")
    rep["maskoff"] = MO
    # sparse points of the box's training subset (box MVS workspace)
    mvs_dir = Path(s_l["mvs"])
    ixyz, irgb = read_points3d_bin(mvs_dir / "sparse/points3D.bin")
    ik = inside_range(ixyz[:, :2], rng)
    ixyz, irgb = ixyz[ik], irgb[ik]
    rep["image_points"] = int(len(ixyz))
    for pr in ("LoD2", "ALS"):
        run = OUT / a.run_sub / box / pr; runm = OUT / a.maskoff_run_sub / box / pr if MO else None
        summ = json.loads((run / "summary.json").read_text())
        shift = np.asarray(summ["registration"]["shift_applied"], np.float64)
        U = locs.load_store(run / "units.npz"); Um = locs.load_store(runm / "units.npz") if MO else None
        if not np.array_equal(locs.frame_shift(U), shift):
            raise RuntimeError(f"{run}: the store is not the v6 moved store (frame_shift {locs.frame_shift(U).tolist()}, shift {shift.tolist()})")
        st_keys = [k for k in U if not k.startswith(("state", "vote", "E", "J", "why", "loc_in_range", "n_seeing", "n_supporting", "agree_", "conflict_",
                                                     "pix_sum", "a1_sum", "mvs_", "rule"))]
        store = {k: U[k] for k in st_keys}
        store["rule_of_measurement"] = U["rule"]
        for tag, src in (("data", U), ("data_maskoff", Um)):
            if src is None:
                continue
            for k in ("state", "E", "n_seeing", "n_supporting"):
                store[f"{k}_{tag}"] = src[k]
            store[f"vote_{tag}"] = src["vote_tau"]          # the current rule's votes; the fork applies its own rule
        np.savez_compressed(O / f"store_{pr}.npz", **store)
        for nm, src in (("pairs", "unit_view_pairs.npz"), ("knn", "knn.npz")):
            rel_link(run / src, O / f"{nm}_{pr}.npz")
            if MO:
                rel_link(runm / src, O / f"{nm}_{pr}_maskoff.npz")
        for sub in ("prior", "tau", "locmap", "markmap", "markcode"):
            rel_link(EX[pr] / sub, M / f"{sub}_{pr}")
        for sub in ("markmap", "markcode"):
            if MO:
                rel_link(EXM[pr] / sub, M / f"{sub}_{pr}_maskoff")
        # prior points
        meshp = Path(summ["mesh_dir"])
        if pr == "LoD2":
            tab = {r["ext"]: r for r in json.loads((meshp / "lod2_surfaces.json").read_text())["surfaces"]}
            pxyz = U["loc_center"].astype(np.float64)          # v6: the moved store's centres = the registered centres
            seat = U["loc_surface"].astype(np.int64)
            ext = U["surf_ext"][seat]
            pnrm = np.stack([np.asarray(tab[int(e)]["normal"], np.float64) for e in ext]).astype(np.float32)
        else:
            m = dict(np.load(meshp / "als_mesh.npz"))
            Vv = m["V"].astype(np.float64) + shift; F = m["F"].astype(np.int64); ts = m["tri_surface"].astype(np.int64)
            tabA = {r["ext"]: r for r in json.loads((meshp / "als_surfaces.json").read_text())["surfaces"]}
            eligible = np.zeros(int(ts.max()) + 2, bool)
            for e in tabA:
                eligible[e] = True
            vs = surf.vertex_surface(F, ts, eligible)
            inr = inside_range(Vv[:, :2], rng)
            seat_all = np.where(vs >= 0, locs.compact_index(U, np.maximum(vs, 0)), -1)
            vn, _ = ori.tin_vertex_normals(Vv, F, ts, vs)
            pxyz, seat, pnrm = Vv[inr], seat_all[inr], vn[inr].astype(np.float32)
            np.save(O / f"als_vertex_index_{pr}.npy", np.nonzero(inr)[0].astype(np.int64))
        xyz = np.concatenate([ixyz, pxyz]); rgb = np.concatenate([irgb, np.full((len(pxyz), 3), 128, np.uint8)])
        origin = np.concatenate([np.zeros(len(ixyz), np.int8), np.ones(len(pxyz), np.int8)])
        seat_full = np.concatenate([np.full(len(ixyz), -1, np.int64), seat])
        nrm_full = np.concatenate([np.full((len(ixyz), 3), np.nan, np.float32), pnrm])
        S = O / f"scene_{pr}"; (S / "sparse/0").mkdir(parents=True, exist_ok=True)
        write_cameras_bin(S / "sparse/0/cameras.bin", (fx, fy, cx, cy))
        write_images_bin(S / "sparse/0/images.bin", recs)
        store_ply(S / "sparse/0/points3D.ply", xyz, rgb)
        np.save(S / "sparse/0/origin.npy", origin)
        rel_link(O / "images", S / "images")
        (S / "jbgs_calibration.json").write_text(json.dumps(calib, indent=1))
        np.save(O / f"seat_{pr}.npy", seat_full); np.save(O / f"prior_normal_{pr}.npy", nrm_full)
        rep[pr] = dict(prior_points=int(len(pxyz)), seated=int((seat >= 0).sum()), shift=shift.tolist(), rule_of_measurement=str(U["rule"]),
                       tau_roof=summ["tolerance"]["roof"]["tau"], tau_wall=summ["tolerance"]["wall"]["tau"], n_points=int(len(xyz)))
    jdump(O / "fork_inputs.json", dict(rule=__doc__.split("\n\n")[2], **rep, scientific_verdict=None))
    log(box, "fork inputs", json.dumps({k: v for k, v in rep.items() if k in ("train", "test", "image_points")}), rep.get("LoD2", {}).get("prior_points"), rep.get("ALS", {}).get("prior_points"))


if __name__ == "__main__":
    main()
