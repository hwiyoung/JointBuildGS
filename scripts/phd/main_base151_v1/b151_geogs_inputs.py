"""PHD-MAIN-BASE151-v1 2.2: GeoGS cell scenes with the previous scene rules, the cell as the region
(jointbuildgs:geogs-official-db40c95-rtree-v1-b151, CPU, /opt/geogs/bin/python; run_geogs_cpu.sh).

  python b151_geogs_inputs.py scene <LoD2|ALS> <cell>   -> /b151/scenes/GeoGS_<prior>/cell<k>/ (everything but sparse_lod and da3_prior)
  python b151_geogs_inputs.py pcd <LoD2|ALS> <cell> [--workers 24]   -> .../sparse_lod/0 (initial points)

Rules (configs/phd/main_base151_v1/inputs_GeoGS.json):
  images/, sparse/0, sparse_txt, jbgs_calibration.json   stage-1 geogs_prep.py: copies of the cell scene's images (TU1 campus images, train +
                    test of the cell), cameras.bin / images.bin of TU1 scenes/cell<k>/scene_ALS, empty points3D.bin, COLMAP text export
  surface           LoD2: /b151/prior/cell<k>/lod2_mesh.npz faces of tri_type != 2 -> lod2.obj (6 decimals, stage-1 writer);
                    ALS: /b151/prior/cell<k>/als_mesh.npz faces with >= 1 vertex of class 6 (BASELINES als_rule.py v1) -> als_building.obj
                    (shortest round-trip floats, BASELINES writer). Every vertex written, the selected faces only.
  lod2_pcd.ply      1,000,000 points uniform by area with face normals, numpy default_rng(0) (geogs_prep.py lines 134-150)
  lod2_prior/       official LoD2Depth/main.py --generate_maps --z_offset 0 on every image of the scene (fix1 source = official file)
  sparse_lod/0      the official data/generate_pcd.py of the fix1 source (100,000 samples, 2..15 observations, 5 cm visibility, random /
                    numpy seed 0) with BASELINES als_pcd.py's parallel order of work (run_parallel, 'pieces' broad phase; decisions equal to
                    the official function, checked on the first 300 points against the official generate_point_cloud in a separate process)
scientific_verdict: null
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import runpy
import shutil
import struct
import sys
import time
from pathlib import Path

import numpy as np

from b151_common import B, TU1, now, sha, dump, cfg

SRC = Path('/source')
EXPS = Path('/exp/scripts/phd')
sys.path[:0] = [str(EXPS / 'main_baselines_v1/geogs_als'), str(SRC / 'data'), str(SRC)]
OBJ = {'LoD2': 'lod2.obj', 'ALS': 'als_building.obj'}
TRANS = {'LoD2': ('lod2_transformed.obj', 'lod2_transformed_building.obj'), 'ALS': ('als_building_transformed.obj', 'als_building_transformed_building.obj')}


class Quiet:
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
    """stage-1 geogs_prep.py run_official (unchanged)."""
    random.seed(0)
    np.random.seed(0)
    old_argv, old_path, old_cwd, old_out = sys.argv, list(sys.path), os.getcwd(), sys.stdout
    sys.argv = [str(script)] + [str(a) for a in argv]
    sys.path[:0] = [str(Path(script).parent), str(extra_path)]
    os.chdir(extra_path)
    q = Quiet(old_out)
    sys.stdout = q
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.stdout = old_out
        sys.argv, sys.path[:] = old_argv, old_path
        os.chdir(old_cwd)
    return q.count


def surface(prior, k):
    if prior == 'LoD2':
        m = np.load(B / 'prior' / f'cell{k}' / 'lod2_mesh.npz')
        V, F = m['V'].astype(np.float64), m['F'][m['tri_type'] != 2].astype(np.int64)
        rule = 'cell LoD2 faces of tri_type != 2'
    else:
        import als_rule
        m = np.load(B / 'prior' / f'cell{k}' / 'als_mesh.npz')
        mask, _ = als_rule.building_mask(dict(cls=m['cls'], F=m['F']))
        V, F = m['V'].astype(np.float64), m['F'][mask].astype(np.int64)
        rule = 'cell ALS ' + als_rule.RULE_TEXT
    return V, F, rule


def scene(prior, k):
    t0 = time.time()
    c = cfg()
    cell = c['cells']['per_cell'][k]
    S = B / 'scenes' / f'GeoGS_{prior}' / f'cell{k}'
    if (S / 'lod2_prior').exists():
        raise SystemExit(f'{S} done already')
    split = json.loads((TU1 / 'scenes' / f'cell{k}' / 'split.json').read_text())
    for d in ('images', 'sparse/0', 'sparse_txt', 'sparse_lod/0', 'da3_prior'):
        (S / d).mkdir(parents=True, exist_ok=True)
    names = sorted(split['train'] + split['test'])
    for n in names:
        if not (S / 'images' / f'{n}.jpg').exists():
            shutil.copyfile(TU1 / 'scenes/campus/images' / f'{n}.jpg', S / 'images' / f'{n}.jpg')
    for f in ('cameras.bin', 'images.bin'):
        shutil.copyfile(TU1 / 'scenes' / f'cell{k}' / 'scene_ALS/sparse/0' / f, S / 'sparse/0' / f)
        assert sha(S / 'sparse/0' / f) == cell['sparse'][f]['sha256']
    (S / 'sparse/0/points3D.bin').write_bytes(struct.pack('<Q', 0))
    shutil.copyfile(TU1 / 'scenes' / f'cell{k}' / 'scene_ALS/jbgs_calibration.json', S / 'jbgs_calibration.json')
    shutil.copyfile(TU1 / 'scenes' / f'cell{k}' / 'split.json', S / 'split.json')
    from scene.colmap_loader import read_extrinsics_binary, read_intrinsics_binary
    ext = read_extrinsics_binary(str(S / 'sparse/0/images.bin'))
    intr = read_intrinsics_binary(str(S / 'sparse/0/cameras.bin'))
    with open(S / 'sparse_txt/cameras.txt', 'w') as f:
        f.write('# Camera list with one line of data per camera:\n#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n')
        for i in sorted(intr):
            q = intr[i]
            f.write(f'{q.id} {q.model} {q.width} {q.height} ' + ' '.join(repr(float(x)) for x in q.params) + '\n')
    with open(S / 'sparse_txt/images.txt', 'w') as f:
        f.write('# Image list with two lines of data per image:\n#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n#   POINTS2D[] as (X, Y, POINT3D_ID)\n')
        for i in sorted(ext):
            e = ext[i]
            f.write(f'{e.id} ' + ' '.join(repr(float(x)) for x in e.qvec) + ' ' + ' '.join(repr(float(x)) for x in e.tvec) + f' {e.camera_id} {e.name}\n\n')
    (S / 'sparse_txt/points3D.txt').write_text('# 3D point list with one line of data per point:\n')
    assert {e.name for e in ext.values()} == {f'{n}.jpg' for n in names}, 'images.bin and the image list differ'
    V, F, rule = surface(prior, k)
    with open(S / OBJ[prior], 'w') as f:
        f.write(f'# PHD-MAIN-BASE151-v1 cell{k} {prior} prior surface ({rule}), local frame, /b151/prior/cell{k}\n')
        if prior == 'LoD2':
            for v in V:
                f.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        else:
            for v in V:
                f.write(f'v {v[0]!r} {v[1]!r} {v[2]!r}\n')
        for t in F:
            f.write(f'f {t[0] + 1} {t[1] + 1} {t[2] + 1}\n')
    (S / 'reference_frame_identity.json').write_text(json.dumps({"base_to_canonical": {"scale": [1.0, 1.0, 1.0], "shift": [0.0, 0.0, 0.0], "swap_xy": False}}, indent=1))
    from LoD2Depth.mesh_loader import load_obj
    Vr, Fr, _, _ = load_obj(str(S / OBJ[prior]))
    readback = dict(vertices=int(len(Vr)), faces=int(len(Fr)), faces_equal=bool(np.array_equal(np.asarray(Fr, np.int64), F)),
                    max_abs_vertex_diff_m=float(np.abs(np.asarray(Vr, np.float64) - V).max()))
    t1 = time.time()
    # protection / matching cloud (geogs_prep.py lines 134-150, unchanged)
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
    el = np.empty(len(P), dtype=[(q, 'f4') for q in ('x', 'y', 'z', 'nx', 'ny', 'nz')])
    for q, a in zip(('x', 'y', 'z'), P.T):
        el[q] = a
    for q, a in zip(('nx', 'ny', 'nz'), nf[fi].T):
        el[q] = a
    PlyData([PlyElement.describe(el, 'vertex')]).write(str(S / 'lod2_pcd.ply'))
    t2 = time.time()
    nwarn = run_official(SRC / 'LoD2Depth/main.py', ['--mesh_path', S / OBJ[prior], '--reference_frame_path', S / 'reference_frame_identity.json',
                                                     '--reference_frame_path_building', S / 'reference_frame_identity.json', '--z_offset', '0',
                                                     '--colmap_dir', S / 'sparse_txt', '--building_name', f'cell{k}', '--generate_maps',
                                                     '--subset_images_dir', S / 'images', '--output_path', S / TRANS[prior][0],
                                                     '--output_building_path', S / TRANS[prior][1], '--depth_normal_dir', S / 'lod2_prior'], SRC / 'LoD2Depth')
    t3 = time.time()
    maps = sorted((S / 'lod2_prior/raw_depth').glob('*.npy'))
    hit = []
    for p in maps[::10]:
        a = np.load(p)
        hit.append(float((np.isfinite(a) & (a > 0)).mean()))
    rec = dict(at=now(), method='GeoGS', prior=prior, cell=k, rule=__doc__, surface_rule=rule, images=len(names), train=len(split['train']), test=len(split['test']),
               surface_vertices=int(len(V)), surface_faces=int(len(F)), surface_area_m2=float(area.sum()), obj_readback=readback,
               protection_cloud_points=1_000_000, depth_maps=len(maps), depth_hit_share_mean_every10th=float(np.mean(hit)) if hit else None,
               visibility_fallback_warnings=nwarn,
               files={q: sha(S / q) for q in (OBJ[prior], 'lod2_pcd.ply', 'jbgs_calibration.json', 'sparse/0/cameras.bin', 'sparse/0/images.bin', 'sparse_txt/images.txt')},
               official_scripts={q: sha(SRC / q) for q in ('data/generate_pcd.py', 'LoD2Depth/main.py', 'LoD2Depth/raycasting.py')},
               seconds=dict(copy_obj=round(t1 - t0, 1), pcd_cloud=round(t2 - t1, 1), lod2_depth=round(t3 - t2, 1)), scientific_verdict=None)
    dump(S / 'scene_receipt.json', rec)
    print('GEOGS_SCENE', prior, k, len(names), len(F), len(maps), round(t3 - t0), flush=True)


def pcd(prior, k, workers):
    """als_pcd.py main() with the cell scene: the official sampling chain, the parallel run, the verify on the first 300 points."""
    import als_pcd as AP
    t0 = time.time()
    S = B / 'scenes' / f'GeoGS_{prior}' / f'cell{k}'
    O = S / 'sparse_lod/0'
    if (O / 'points3D.ply').exists():
        raise SystemExit(f'{O} done already')
    det = B / 'prep/geogs' / f'{prior}_cell{k}'
    det.mkdir(parents=True, exist_ok=True)
    logf = det / 'pcd_log.txt'

    def log(msg):
        line = f"[{now()}] {msg}"
        print(line, flush=True)
        with open(logf, 'a') as f:
            f.write(line + '\n')

    GP = AP.GP
    random.seed(0); np.random.seed(0)
    _, V, F, _, _ = GP.load_and_transform_mesh(str(S / OBJ[prior]), str(S / 'reference_frame_identity.json'), 0.0)
    cameras = GP.load_cameras(str(S / 'sparse_txt/cameras.txt'))
    images = GP.load_images(str(S / 'sparse_txt/images.txt'))
    points, face_indices = GP.sample_points_from_mesh(V, F, AP.NUM)
    _, _, rule = surface(prior, k)
    from LoD2Depth.mesh_loader import load_obj
    Vm, Fm, _, _ = load_obj(str(S / OBJ[prior]))                      # the OBJ as read back (LoD2: 6-decimal text)
    Vm, Fm = np.asarray(Vm, np.float64), np.asarray(Fm, np.int64)
    np.random.seed(0)
    pm, fm = GP.sample_points_from_mesh(Vm, Fm, AP.NUM)
    dmax, bmin, bmax = AP.on_face(points, face_indices, np.asarray(V, np.float64), np.asarray(F, np.int64))
    rep = dict(task_id='PHD-MAIN-BASE151-v1', step='GeoGS initial points', prior=prior, cell=k, rule=__doc__, surface_rule=rule,
               source_generate_pcd_sha256=sha(SRC / 'data/generate_pcd.py'), als_pcd_sha256=sha(EXPS / 'main_baselines_v1/geogs_als/als_pcd.py'),
               obj_sha256=sha(S / OBJ[prior]), images=len(images), faces=int(len(F)), samples=int(len(points)),
               arguments=dict(num_points=AP.NUM, min_observations=AP.MIN_OBS, max_observations=AP.MAX_OBS, z_offset=0.0, broad='pieces', piece_m=1.0,
                              workers=workers, chunk=32),
               sample_check=dict(official_chain_equals_in_memory=bool(np.array_equal(points, pm) and np.array_equal(face_indices, fm)),
                                 max_plane_distance_m=dmax, barycentric_min=bmin, barycentric_max=bmax))
    log(json.dumps(rep['sample_check']))
    if not rep['sample_check']['official_chain_equals_in_memory']:
        dump(det / 'pcd_FAILED.json', rep)
        raise SystemExit('sample check failed')
    vfile = det / 'verify_official.npy'
    k_ver = 300
    vp = mp.get_context('fork').Process(target=AP._official, args=(V, F, points[:k_ver], face_indices[:k_ver], cameras, images, str(vfile)))
    vp.start()
    a = argparse.Namespace(workers=workers, chunk=32, broad='pieces', piece=1.0)
    random.seed(0)
    pc, n_obs, st = AP.run_parallel(V, F, points, cameras, images, a, log)
    vp.join()
    ref = list(np.load(vfile, allow_pickle=True))
    secs = ref.pop()['seconds']
    mine = [p for p in pc if p['id'] < k_ver]
    why = 'equal'
    if len(ref) != len(mine):
        why = f'lengths {len(ref)} vs {len(mine)}'
    else:
        for x, y in zip(ref, mine):
            oy = [tuple(float(v) if q >= 2 else int(v) for q, v in enumerate(o)) for o in y['observations']]
            if x['id'] != y['id'] or not np.array_equal(x['xyz'], y['xyz']) or x['observations'] != oy:
                why = f"point {x['id']} / {y['id']}"
                break
    rep['verify'] = dict(points=k_ver, official_kept=len(ref), parallel_kept=len(mine), equal=why == 'equal', detail=why, official_seconds=round(secs, 1))
    log('[verify] ' + json.dumps(rep['verify']))
    if why != 'equal':
        dump(det / 'pcd_FAILED.json', rep)
        raise SystemExit('the parallel run differs from the official function')
    O.mkdir(parents=True, exist_ok=True)
    GP.write_points3D_file(pc, str(O / 'points3D.txt'))
    GP.update_images_with_points2D(images, pc, str(O / 'images.txt'))
    shutil.copyfile(S / 'sparse_txt/cameras.txt', O / 'cameras.txt')
    from scene.colmap_loader import read_points3D_text
    from scene.dataset_readers import storePly
    xyz, rgb, _ = read_points3D_text(str(O / 'points3D.txt'))
    storePly(str(O / 'points3D.ply'), xyz, rgb)
    kept = np.zeros(len(points), bool)
    kept[[p['id'] for p in pc]] = True
    np.savez_compressed(det / 'pcd.npz', points=points, kept=kept, n_obs=n_obs, face_index=face_indices)
    rep['result'] = dict(kept=int(kept.sum()), dropped=int((~kept).sum()),
                         n_obs_quantiles=dict(zip(('q10', 'q50', 'q90'), map(float, np.quantile(n_obs, [0.1, 0.5, 0.9])))),
                         mean_track=float(np.mean([len(p['observations']) for p in pc])) if pc else 0.0,
                         **{q: v for q, v in st.items() if not isinstance(v, np.ndarray)})
    rep['files'] = {q: sha(O / q) for q in ('points3D.txt', 'points3D.ply', 'images.txt', 'cameras.txt')}
    rep['seconds'] = round(time.time() - t0, 1)
    rep['scientific_verdict'] = None
    (det / 'pcd.json').write_text(json.dumps(rep, indent=1, default=float, ensure_ascii=False))
    log(json.dumps(dict(prior=prior, cell=k, kept=rep['result']['kept'], seconds=rep['seconds'])))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['scene', 'pcd'])
    ap.add_argument('prior', choices=['LoD2', 'ALS'])
    ap.add_argument('cell', type=int)
    ap.add_argument('--workers', type=int, default=24)
    x = ap.parse_args()
    if x.step == 'scene':
        scene(x.prior, x.cell)
    else:
        pcd(x.prior, x.cell, x.workers)
