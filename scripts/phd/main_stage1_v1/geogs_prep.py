"""PHD-MAIN-STAGE1-v1 GeoGS (always-trust LoD2) inputs of one site with the official preprocessing (jointbuildgs:geogs-official-db40c95-v1,
CPU; /source = the untouched official checkout db40c95 (ro), /s0 stage-0 payload (ro), /dr discard payload (ro), /out this payload).

  python geogs_prep.py <site>      -> /out/geogs/<site>/scene/, /out/geogs/<site>/prep.json

The scene has the same images, poses, camera model, training views and LoD2 surface as the proposed method's LoD2 scene:
  images/                         copies of the fork scene images (1024 x 741 = the method's training resolution, '-r 1')
  sparse/0/                       cameras.bin, images.bin of the fork scene (all views; the split = JBGS_SPLIT_JSON) and an empty
                                  points3D.bin (the official DA3 script reads one)
  sparse_txt/                     the same cameras and images as COLMAP text (input of the official preprocessing)
  jbgs_calibration.json           the fork scene's file (camera adapter: principal point, decided 2026-10-07)
  lod2.obj                        the method's LoD2 prior surface: s02_box lod2_mesh.npz + the registration shift of the stage-0 box run,
                                  faces of type != 2 (as defs_s1.prior_mesh and the fork inputs), local frame
  reference_frame_identity.json   scale 1, shift 0, no swap, with --z_offset 0: the mesh is already in the scene frame
  sparse_lod/0/                   official data/generate_pcd.py (author defaults: 100,000 samples, 2..15 observations; random / numpy
                                  seed 0 as the earlier work's seeded wrapper), cameras.txt (= sparse_txt) and points3D.ply (the
                                  official reader's own conversion of points3D.txt, done here so the scene can be mounted read-only)
  lod2_prior/                     official LoD2Depth/main.py --generate_maps (every image of the scene; raw_depth = Open3D t_hit)
  lod2_pcd.ply                    the official protection / matching cloud: the LoD2 surface sampled uniformly by area, 1,000,000
                                  points with their face normals (seed 0); the author's example used a CloudCompare sampling of ~1,000,000
Check written to prep.json: the official LoD2 depth against the fork's LoD2 depth maps (maps/prior_LoD2) of the training views.
scientific_verdict: null."""
import hashlib
import json
import os
import runpy
import shutil
import struct
import sys
import time
from pathlib import Path

import numpy as np

S0, DR, OUT, SRC = Path("/s0"), Path("/dr"), Path("/out"), Path("/source")
sys.path.insert(0, str(SRC))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Quiet:
    """stdout filter: the official generate_pcd.py prints one warning per (point, camera) when its trimesh visibility check falls
    back (the official behaviour, kept); those lines are counted instead of written. Logging only."""
    KEY = "Warning: Trimesh visibility check failed, falling back"

    def __init__(self, out):
        self.out, self.count, self.buf = out, 0, ""

    def write(self, x):
        self.buf += x
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.startswith(self.KEY):
                self.count += 1
            else:
                self.out.write(line + "\n")

    def flush(self):
        self.out.flush()


def run_official(script, argv, extra_path):
    """the official script as __main__ with the given argv; random / numpy seeded 0 first. Returns the count of filtered warnings."""
    import random
    random.seed(0)
    np.random.seed(0)
    old_argv, old_path, old_cwd, old_out = sys.argv, list(sys.path), os.getcwd(), sys.stdout
    sys.argv = [str(script)] + [str(a) for a in argv]
    sys.path[:0] = [str(Path(script).parent), str(extra_path)]          # as 'python <script>' would (its own folder first)
    os.chdir(extra_path)
    q = Quiet(old_out)
    sys.stdout = q
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.stdout = old_out
        sys.argv, sys.path[:] = old_argv, old_path
        os.chdir(old_cwd)
    print(f"[geogs_prep] {Path(script).name}: {q.count:,} visibility-fallback warnings counted (not written)", flush=True)
    return q.count


def main(site):
    t0 = time.time()
    times = {}
    G = OUT / "geogs" / site
    S = G / "scene"
    if S.exists():
        raise FileExistsError(f"{S} exists")
    FS = S0 / "fork_inputs/s61" / site / "scene_LoD2"
    split = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())
    for d in ("images", "sparse/0", "sparse_txt", "sparse_lod/0"):
        (S / d).mkdir(parents=True)
    imgs = sorted((FS / "images").iterdir())
    for p in imgs:
        shutil.copyfile(p, S / "images" / p.name)
    for f in ("cameras.bin", "images.bin"):
        shutil.copyfile(FS / "sparse/0" / f, S / "sparse/0" / f)
    (S / "sparse/0/points3D.bin").write_bytes(struct.pack("<Q", 0))
    shutil.copyfile(FS / "jbgs_calibration.json", S / "jbgs_calibration.json")
    times["copy"] = round(time.time() - t0, 1)
    # COLMAP text of the same cameras and images
    from scene.colmap_loader import read_extrinsics_binary, read_intrinsics_binary
    ext = read_extrinsics_binary(str(S / "sparse/0/images.bin"))
    intr = read_intrinsics_binary(str(S / "sparse/0/cameras.bin"))
    with open(S / "sparse_txt/cameras.txt", "w") as f:
        f.write("# Camera list with one line of data per camera:\n#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        for k in sorted(intr):
            c = intr[k]
            f.write(f"{c.id} {c.model} {c.width} {c.height} " + " ".join(repr(float(x)) for x in c.params) + "\n")
    with open(S / "sparse_txt/images.txt", "w") as f:
        f.write("# Image list with two lines of data per image:\n#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        for k in sorted(ext):
            e = ext[k]
            f.write(f"{e.id} " + " ".join(repr(float(x)) for x in e.qvec) + " " + " ".join(repr(float(x)) for x in e.tvec) + f" {e.camera_id} {e.name}\n\n")
    (S / "sparse_txt/points3D.txt").write_text("# 3D point list with one line of data per point:\n")
    names = {e.name for e in ext.values()}
    assert names == {p.name for p in imgs}, "images.bin and the image folder differ"
    assert {n.rsplit(".", 1)[0] for n in names} >= set(split["train"]) | set(split["test"]), "split names missing from the scene"
    # the method's LoD2 surface
    m = np.load(DR / "s02_box" / site / "lod2_mesh.npz")
    sh = np.asarray(json.loads((S0 / "s61/box" / site / "LoD2/summary.json").read_text())["registration"]["shift_applied"], np.float64)
    V = m["V"].astype(np.float64) + sh
    F = m["F"][m["tri_type"] != 2].astype(np.int64)
    with open(S / "lod2.obj", "w") as f:
        f.write(f"# PHD-MAIN-STAGE1-v1 {site} LoD2 prior surface (local frame, registration shift {sh.tolist()}), faces of type != 2\n")
        for v in V:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in F:
            f.write(f"f {t[0] + 1} {t[1] + 1} {t[2] + 1}\n")
    (S / "reference_frame_identity.json").write_text(json.dumps({"base_to_canonical": {"scale": [1.0, 1.0, 1.0], "shift": [0.0, 0.0, 0.0], "swap_xy": False}}, indent=1))
    # LoD2 protection / matching cloud: uniform by area, face normals, seed 0
    rng = np.random.default_rng(0)
    T3 = V[F]
    cr = np.cross(T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 0])
    area = 0.5 * np.linalg.norm(cr, axis=1)
    nf = cr / np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-12)
    fi = rng.choice(len(F), 1_000_000, p=area / area.sum())
    r1, r2 = rng.random(1_000_000), rng.random(1_000_000)
    s1 = np.sqrt(r1)
    P = (1 - s1)[:, None] * T3[fi, 0] + (s1 * (1 - r2))[:, None] * T3[fi, 1] + (s1 * r2)[:, None] * T3[fi, 2]
    from plyfile import PlyData, PlyElement
    el = np.empty(len(P), dtype=[(k, "f4") for k in ("x", "y", "z", "nx", "ny", "nz")])
    for k, a in zip(("x", "y", "z"), P.T):
        el[k] = a
    for k, a in zip(("nx", "ny", "nz"), nf[fi].T):
        el[k] = a
    PlyData([PlyElement.describe(el, "vertex")]).write(str(S / "lod2_pcd.ply"))
    times["inputs"] = round(time.time() - t0, 1)
    # official LoD2 initialisation points
    nwarn = run_official(SRC / "data/generate_pcd.py", ["--mesh_path", S / "lod2.obj", "--reference_frame_path", S / "reference_frame_identity.json", "--z_offset", "0",
                                                "--colmap_dir", S / "sparse_txt", "--output_dir", S / "sparse_lod/0"], SRC)
    shutil.copyfile(S / "sparse_txt/cameras.txt", S / "sparse_lod/0/cameras.txt")
    from scene.colmap_loader import read_points3D_text
    from scene.dataset_readers import storePly
    xyz, rgb, _ = read_points3D_text(str(S / "sparse_lod/0/points3D.txt"))
    storePly(str(S / "sparse_lod/0/points3D.ply"), xyz, rgb)
    times["generate_pcd"] = round(time.time() - t0, 1)
    # official LoD2 depth / normal maps
    run_official(SRC / "LoD2Depth/main.py", ["--mesh_path", S / "lod2.obj", "--reference_frame_path", S / "reference_frame_identity.json",
                                             "--reference_frame_path_building", S / "reference_frame_identity.json", "--z_offset", "0",
                                             "--colmap_dir", S / "sparse_txt", "--building_name", site, "--generate_maps", "--subset_images_dir", S / "images",
                                             "--output_path", S / "lod2_transformed.obj", "--output_building_path", S / "lod2_transformed_building.obj",
                                             "--depth_normal_dir", S / "lod2_prior"], SRC / "LoD2Depth")
    times["lod2_depth"] = round(time.time() - t0, 1)
    # check: the official LoD2 depth against the fork's LoD2 depth maps of the training views
    chk = []
    for n in split["train"]:
        a = np.load(S / "lod2_prior/raw_depth" / f"{n}.npy").astype(np.float64)
        fb = S0 / "fork_inputs/s61" / site / "maps/prior_LoD2" / f"{n}.npy"
        if not fb.exists():
            continue
        b = np.load(fb).astype(np.float64)
        if b.shape != a.shape:
            chk.append(dict(view=n, shape_official=list(a.shape), shape_fork=list(b.shape)))
            continue
        fa, fbm = np.isfinite(a) & (a > 0), np.isfinite(b) & (b > 0)
        both = fa & fbm
        chk.append(dict(view=n, hit_official=float(fa.mean()), hit_fork=float(fbm.mean()), both=int(both.sum()), only_official=int((fa & ~fbm).sum()),
                        only_fork=int((~fa & fbm).sum()), median_abs_diff_m=float(np.median(np.abs(a[both] - b[both]))) if both.any() else None,
                        p95_abs_diff_m=float(np.quantile(np.abs(a[both] - b[both]), 0.95)) if both.any() else None))
    ok = [c for c in chk if c.get("median_abs_diff_m") is not None]
    rep = dict(task_id="PHD-MAIN-STAGE1-v1", site=site, rule=__doc__, scene=str(S.relative_to(OUT)), images=len(imgs), train=len(split["train"]), test=len(split["test"]),
               lod2_vertices=int(len(V)), lod2_faces=int(len(F)), registration_shift=sh.tolist(), lod2_area_m2=round(float(area.sum()), 1),
               init_points=int(len(xyz)), visibility_fallback_warnings=nwarn, lod2_depth_maps=len(list((S / "lod2_prior/raw_depth").glob("*.npy"))),
               lod2_depth_check=dict(views=len(chk), median_of_median_abs_diff_m=float(np.median([c["median_abs_diff_m"] for c in ok])) if ok else None,
                                     max_of_p95_abs_diff_m=float(np.max([c["p95_abs_diff_m"] for c in ok])) if ok else None,
                                     mean_hit_official=float(np.mean([c["hit_official"] for c in ok])) if ok else None,
                                     mean_hit_fork=float(np.mean([c["hit_fork"] for c in ok])) if ok else None, per_view=chk),
               files={k: sha(S / k) for k in ("lod2.obj", "lod2_pcd.ply", "jbgs_calibration.json", "sparse/0/cameras.bin", "sparse/0/images.bin",
                                                "sparse_lod/0/points3D.txt", "sparse_lod/0/points3D.ply", "sparse_lod/0/images.txt", "sparse_lod/0/cameras.txt")},
               official_scripts={k: sha(SRC / k) for k in ("data/generate_pcd.py", "LoD2Depth/main.py", "LoD2Depth/raycasting.py")},
               seconds=times, scientific_verdict=None)
    (G / "prep.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("site", "images", "train", "test", "lod2_faces", "init_points", "lod2_depth_maps")}),
          json.dumps({k: v for k, v in rep["lod2_depth_check"].items() if k != "per_view"}))


if __name__ == "__main__":
    main(sys.argv[1])
