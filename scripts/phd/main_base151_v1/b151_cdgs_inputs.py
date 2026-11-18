"""PHD-MAIN-BASE151-v1 2.2: CDGS variant (cdgsnofit) cell scenes with the BASELINES/FILL scene rules, the cell as the region
(jointbuildgs:dev, CPU; run_cpu.sh). Rules: configs/phd/main_base151_v1/inputs_CDGS.json.

  python b151_cdgs_inputs.py sparse <cell>              -> /b151/scenes/CDGS/cell<k>/ (sparse/0, split_index.json, jbgs_calibration.json, units.json)
  python b151_cdgs_inputs.py depth <LoD2|ALS> <cell>    -> /b151/priordepth/<prior>/cell<k>/<stem>.npy (training views)
  python b151_cdgs_inputs.py options <LoD2|ALS> <cell>  -> /b151/scenes/CDGS_<prior>/cell<k>/ (template of the per-attempt scene)

sparse (BASELINES cdgs/cdgs_scenes.py build, the WIDEN0 campus model instead of the box model):
  cameras.bin   byte copy of TU1 scenes/cell<k>/scene_ALS/sparse/0/cameras.bin (PINHOLE 1024 x 741)
  images.bin    the cell scene's poses, ids, names and camera in its file order; the training views carry the 2-D observations of the
                WIDEN0 campus model WD/mvs/full/sparse (x * 1024 / 1400, y * 741 / 1013), points not kept -> id -1; test views no observations
  points3D.bin  WD model points with xy inside the expanded cell (TRAINUNIT inside rule) and >= 2 observations by cell training views, tracks
                restricted to those views, ids 1..N in file order
  split_index   train / test = indices into the name-sorted images.bin list (CDGS readColmapSceneInfo); no center.npy
  units         s = median camera-z of the (training view, own observed point) pairs (point seen by >= 2 views, in front, inside the image,
                K = jbgs_calibration.json) / TT (BASELINES cdgs_units.py target_depths; TT = 2.646066780584012)
depth (stage-0 s03_stage1_v6 export 'prior' rule): the cell prior surface (inputs_prior, all faces: LoD2 polygons + caps, ALS full TIN of
  classes 2 and 6) ray cast with open3d RaycastingScene from the camera centre along R^T (x_n, y_n, 1) at the pixel centres (+0.5) of the
  1024 x 741 grid (K of TU1 scenes/campus/poses.json) -> camera-z depth, float32 [741, 1024], no hit = NaN; training views only.
options: FILL jbgs_cdgs_options.json keys (alignment_targets own_observations, depth_unit_divisor_s, TT, alignment identity) without
  v2_reference (no official fit was run here).
scientific_verdict: null
"""
import ast
import shutil
import sys

import numpy as np

from b151_common import *

EXPB = Path('/exp/scripts/phd/main_baselines_v1/cdgs')
sys.path.insert(0, str(EXPB))
import cdgs_io as IO  # noqa: E402

TT = 2.646066780584012
W, H = 1024, 741


def inherit(path, names, scope):
    nodes = [x for x in ast.parse(Path(path).read_text()).body if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name in names]
    assert len(nodes) == len(names), (path, names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return [scope[n] for n in names]


_s = dict(np=np, Path=Path, struct=__import__('struct'), NPAR=IO.NPAR)
cdgs_reading, = inherit(EXPB / 'cdgs_scenes.py', ['cdgs_reading'], dict(np=np))
read_cameras_u, read_images_u, read_points_u, qR_u, target_depths = inherit(EXPB / 'cdgs_units.py', ['read_cameras', 'read_images', 'read_points', 'qR', 'target_depths'], _s)
stem = lambda n: n.rsplit('.', 1)[0]


def sparse(k):
    c = cfg()
    cell = c['cells']['per_cell'][k]
    src = TU1 / 'scenes' / f'cell{k}'
    U = B / 'scenes/CDGS' / f'cell{k}'
    (U / 'sparse/0').mkdir(parents=True, exist_ok=True)
    rep = dict(at=now(), cell=k, checks={}, rule=__doc__, scientific_verdict=None)
    ck = rep['checks']
    cam_bytes = (src / 'scene_ALS/sparse/0/cameras.bin').read_bytes()
    cams = IO.read_cameras(src / 'scene_ALS/sparse/0/cameras.bin')
    assert len(cams) == 1
    cid = list(cams)[0]
    assert cams[cid]['model'] == 1 and (cams[cid]['w'], cams[cid]['h']) == (W, H)
    fims = IO.read_images(src / 'scene_ALS/sparse/0/images.bin')
    by_stem = {stem(r['name']): r for r in fims.values()}
    split = json.loads((src / 'split.json').read_text())
    tr, te = list(split['train']), list(split['test'])
    ck['split_names_in_cell_scene'] = set(tr) | set(te) == set(by_stem) and not (set(tr) & set(te))
    WS = WD / 'mvs/full/sparse'
    bcams = IO.read_cameras(WS / 'cameras.bin')
    bims = IO.read_images(WS / 'images.bin')
    bpts = IO.read_points3d(WS / 'points3D.bin')
    bc = list(bcams.values())[0]
    sx, sy = W / bc['w'], H / bc['h']
    bstem = {stem(r['name']): r for r in bims.values()}
    ck['training_views_all_in_campus_model'] = set(tr) <= set(bstem)
    dq, dt, dc = [], [], []
    for s in tr:
        a, b = bstem[s], by_stem[s]
        dq.append(float(np.abs(a['q'] - b['q']).max())); dt.append(float(np.abs(a['t'] - b['t']).max()))
        Ra, Rb = IO.qvec2rotmat(a['q']), IO.qvec2rotmat(b['q'])
        dc.append(float(np.linalg.norm(-Ra.T @ a['t'] + Rb.T @ b['t'])))
    rep['campus_model_vs_cell_poses'] = dict(max_abs_qvec_diff=max(dq), max_abs_tvec_diff_m=max(dt), max_centre_m=max(dc),
                                             identical=bool(max(dq) == 0 and max(dt) == 0))
    lo, hi = np.array(cell['expanded_min'], float), np.array(cell['expanded_max'], float)
    xy = bpts['xyz'][:, :2]
    inside = (xy[:, 0] >= lo[0]) & (xy[:, 0] < hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] < hi[1])
    train_ids = {bstem[s]['id'] for s in tr}
    tid = np.array(sorted(train_ids))
    ntr = np.array([int(np.isin(ti, tid).sum()) for ti in bpts['track_img']])
    keep = inside & (ntr >= 2)
    o0 = np.load(src / 'scene_ALS/sparse/0/origin.npy')
    rep['points'] = dict(campus_model=int(len(inside)), inside_expanded_cell=int(inside.sum()), inside_with_lt2_training_obs=int((inside & (ntr < 2)).sum()),
                         kept=int(keep.sum()), cell_scene_sfm_points_origin0=int((o0 == 0).sum()))
    old_ids = bpts['id'][keep]
    new_of_old = {int(o): i + 1 for i, o in enumerate(old_ids)}
    cell_id_of_campus = {bstem[s]['id']: by_stem[s]['id'] for s in tr}
    trs = set(tr)
    recs, n_obs, n_kept = [], 0, 0
    for iid in fims:
        r = fims[iid]
        s = stem(r['name'])
        if s in trs:
            b = bstem[s]
            pid = np.array([new_of_old.get(int(o), -1) if o >= 0 else -1 for o in b['pid']], np.int64)
            pxy = b['xy'] * np.array([sx, sy])
            n_obs += int((b['pid'] >= 0).sum()); n_kept += int((pid >= 0).sum())
        else:
            pid, pxy = np.zeros(0, np.int64), np.zeros((0, 2))
        recs.append(dict(id=r['id'], q=r['q'], t=r['t'], cam=r['cam'], name=r['name'], xy=pxy, pid=pid))
    rec_of = {r['id']: r for r in recs}
    ti_all, tp_all, consist = [], [], True
    for i in np.nonzero(keep)[0]:
        ti, tp = bpts['track_img'][i], bpts['track_p2d'][i]
        m = np.isin(ti, tid)
        fi = np.array([cell_id_of_campus[int(x)] for x in ti[m]], np.int32)
        pp = tp[m].astype(np.int32)
        for a, b in zip(fi, pp):
            if rec_of[int(a)]['pid'][int(b)] != new_of_old[int(bpts['id'][i])]:
                consist = False
        ti_all.append(fi); tp_all.append(pp)
    ck['tracks_match_observations'] = consist
    tl = np.array([len(x) for x in ti_all])
    rep['observations'] = dict(training_obs=n_obs, training_obs_of_kept=n_kept, track_length_mean=float(tl.mean()), track_length_median=float(np.median(tl)))
    names_sorted = sorted(r['name'] for r in recs)
    train_idx = [i for i, n in enumerate(names_sorted) if stem(n) in trs]
    test_idx = [i for i, n in enumerate(names_sorted) if stem(n) in set(te)]
    ck['split_index_round_trip'] = [stem(names_sorted[i]) for i in train_idx] == sorted(tr) and [stem(names_sorted[i]) for i in test_idx] == sorted(te)
    rep['cdgs_reading'] = cdgs_reading(recs, train_idx, int(keep.sum()))
    ck['cdgs_keeps_all_points'] = rep['cdgs_reading']['points_kept_as_initial_cloud'] == int(keep.sum())
    (U / 'sparse/0/cameras.bin').write_bytes(cam_bytes)
    IO.write_images(U / 'sparse/0/images.bin', recs)
    IO.write_points3d(U / 'sparse/0/points3D.bin', np.arange(1, int(keep.sum()) + 1), bpts['xyz'][keep], bpts['rgb'][keep], bpts['err'][keep], ti_all, tp_all)
    (U / 'split_index.json').write_text(json.dumps(dict(train=train_idx, test=test_idx)))
    shutil.copyfile(src / 'scene_ALS/jbgs_calibration.json', U / 'jbgs_calibration.json')
    i2 = IO.read_images(U / 'sparse/0/images.bin')
    ck['poses_eq_cell_scene'] = all(np.array_equal(i2[q]['q'], fims[q]['q']) and np.array_equal(i2[q]['t'], fims[q]['t']) and i2[q]['name'] == fims[q]['name'] for q in fims)
    cal = json.loads((U / 'jbgs_calibration.json').read_text())['images']
    Kof = lambda n: (cal[stem(n)]['K'][0][0], cal[stem(n)]['K'][1][1], cal[stem(n)]['K'][0][2], cal[stem(n)]['K'][1][2])
    d = target_depths(U / 'sparse/0', keep_image=lambda n: stem(n) in trs, K_of=Kof)
    rep['units'] = dict(d, TT=TT, s=d['median'] / TT)
    rep['train'], rep['test'] = len(tr), len(te)
    rep['files'] = {q: sha(U / q) for q in ('sparse/0/cameras.bin', 'sparse/0/images.bin', 'sparse/0/points3D.bin', 'split_index.json', 'jbgs_calibration.json')}
    dump(U / 'units.json', rep)
    assert all(v for kk, v in ck.items() if isinstance(v, bool)), ck
    print('CDGS_SPARSE', k, rep['points'], rep['units']['s'], rep['campus_model_vs_cell_poses'], flush=True)


def depth(prior, k):
    import open3d as o3d
    t0 = time.time()
    c = cfg()
    src = TU1 / 'scenes' / f'cell{k}'
    split = json.loads((src / 'split.json').read_text())
    K = json.loads((TU1 / 'scenes/campus/poses.json').read_text())['K']
    fx, fy, cx, cy = K
    m = np.load(B / 'prior' / f'cell{k}' / ('lod2_mesh.npz' if prior == 'LoD2' else 'als_mesh.npz'))
    V, F = m['V'].astype(np.float32), m['F'].astype(np.uint32)
    sc = o3d.t.geometry.RaycastingScene(nthreads=8)
    sc.add_triangles(o3d.core.Tensor(V), o3d.core.Tensor(F))
    ims = {stem(r['name']): r for r in IO.read_images(src / 'scene_ALS/sparse/0/images.bin').values()}
    xn = ((np.arange(W) + 0.5 - cx) / fx)[None, :]
    yn = ((np.arange(H) + 0.5 - cy) / fy)[:, None]
    out = B / 'priordepth' / prior / f'cell{k}'
    out.mkdir(parents=True, exist_ok=True)
    share = []
    for n in split['train']:
        r = ims[n]
        R = IO.qvec2rotmat(r['q'])
        C = -R.T @ r['t']
        D = np.stack([(R[0, j] * xn + R[1, j] * yn + R[2, j]).astype(np.float32) for j in range(3)], -1)
        rays = np.concatenate([np.broadcast_to(C.astype(np.float32), (H, W, 3)), D], -1).reshape(-1, 6)
        t = sc.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy().reshape(H, W)
        d = np.where(np.isfinite(t), t, np.nan).astype(np.float32)
        np.save(out / f'{n}.npy', d)
        share.append(float(np.isfinite(d).mean()))
    rec = dict(at=now(), prior=prior, cell=k, views=len(split['train']), faces=int(len(F)), hit_share=dict(min=float(np.min(share)), median=float(np.median(share)),
               max=float(np.max(share))), K=K, mesh=str(B / 'prior' / f'cell{k}'), seconds=round(time.time() - t0, 1),
               rule='stage-0 s03_stage1_v6 export prior: camera-z ray cast, pixel centres +0.5, NaN no hit, training views', scientific_verdict=None)
    dump(out / 'receipt.json', rec)
    print('PRIOR_DEPTH', prior, k, rec['views'], rec['hit_share'], rec['seconds'], flush=True)


def options(prior, k):
    U0 = B / 'scenes/CDGS' / f'cell{k}'
    u = json.loads((U0 / 'units.json').read_text())
    U = B / 'scenes' / f'CDGS_{prior}' / f'cell{k}'
    (U / 'sparse/0').mkdir(parents=True, exist_ok=True)
    for q in ('sparse/0/cameras.bin', 'sparse/0/images.bin', 'sparse/0/points3D.bin', 'split_index.json', 'jbgs_calibration.json'):
        shutil.copyfile(U0 / q, U / q)
    opt = dict(alignment_targets='own_observations', depth_unit_divisor_s=u['units']['s'], site_median_target_depth_m=u['units']['median'], TT=TT,
               decision='BASELINES user 10-15 option 나 (own observations, s = median target depth / TT), recomputed for the cell', scientific_verdict=None,
               alignment='identity', task_id_variant='PHD-MAIN-BASE151-v1',
               variant='FILL order 5.1 2 (user decision 10-15): per-view fit skipped, scale 1, shift 0; L_align and 0.6 exp(-150 L_align) in place; '
                       'supervision depth and confidence from the prior render depth in metres (adapter v3); no v2_reference')
    (U / 'jbgs_cdgs_options.json').write_text(json.dumps(opt, indent=1))
    pd = B / 'priordepth' / prior / f'cell{k}'
    split = json.loads((TU1 / 'scenes' / f'cell{k}' / 'split.json').read_text())
    missing = [n for n in split['train'] if not (pd / f'{n}.npy').exists()]
    assert not missing, missing[:5]
    dump(U / 'scene_receipt.json', dict(at=now(), prior=prior, cell=k, template_files={q: sha(U / q) for q in ('sparse/0/images.bin', 'sparse/0/points3D.bin', 'jbgs_cdgs_options.json')},
                                         prior_depth=str(pd), prior_depth_files=len(split['train']), s=opt['depth_unit_divisor_s'],
                                         per_attempt='the host copies this folder into <attempt>/scene and links images -> /ro_images, prior_depth -> /ro_prior',
                                         scientific_verdict=None))
    print('CDGS_OPTIONS', prior, k, opt['depth_unit_divisor_s'], flush=True)


import time  # noqa: E402

if __name__ == '__main__':
    step = sys.argv[1]
    if step == 'sparse':
        sparse(int(sys.argv[2]))
    elif step == 'depth':
        depth(sys.argv[2], int(sys.argv[3]))
    elif step == 'options':
        options(sys.argv[2], int(sys.argv[3]))
