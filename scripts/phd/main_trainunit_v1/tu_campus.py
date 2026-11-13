"""Campus-wide (판 가·나) and cell (판 다) training inputs with the unchanged FINALTRAIN rules.

  python tu_campus.py scene                      # images, split, poses, calibration (shared by priors)
  python tu_campus.py targets <prior>            # /tu/targets/campus__<prior>.npz
  python tu_campus.py seeds <unit> <prior>       # scene_<prior>/sparse/0 points + /tu/stage1/<unit>__<prior>/seeds.npz
  python tu_campus.py maps <unit> <prior> <part> <parts>
  python tu_campus.py index <unit> <prior>
unit = campus | cell<k> (cells defined by tu_cells.py in /tu/cells/cells.json)
"""
import ctypes
import glob
import os
import struct
import subprocess
import sys
import time

import cv2
from plyfile import PlyData

from tu_common import *

ST0 = R / 'scripts/phd/main_stage0_v1'
scope = dict(np=np, struct=struct, json=json, Path=Path)
inherit(ST0 / 'common.py', ['qR', 'read_cameras_bin', 'read_images_bin'], scope)
_fi = dict(np=np, struct=struct, json=json, Path=Path, GRID_W=GRID_W, GRID_H=GRID_H)
inherit(ST0 / 'fork_inputs_v6.py', ['read_points3d_bin', 'write_cameras_bin', 'write_images_bin', 'store_ply'], _fi)
read_points3d_bin, write_cameras_bin, write_images_bin, store_ply = [_fi[k] for k in ['read_points3d_bin', 'write_cameras_bin', 'write_images_bin', 'store_ply']]
read_cameras_bin, read_images_bin = scope['read_cameras_bin'], scope['read_images_bin']

stem = lambda n: n.rsplit('.', 1)[0]
CAMPUS = TU / 'scenes/campus'


def views():
    cams = read_cameras_bin(DENSE / 'sparse/cameras.bin')
    ims = read_images_bin(DENSE / 'sparse/images.bin')
    names = sorted(ims)
    c = cams[ims[names[0]]['cam']]
    assert c['model'] == 1
    fx, fy, cx, cy = c['p']
    sx, sy = GRID_W / c['w'], GRID_H / c['h']
    return ims, np.array([fx * sx, fy * sy, cx * sx, cy * sy])


def scene():
    cfg()
    split = json.loads((WD / 'image_split.json').read_text())
    train, test = list(split['train']), list(split['evaluation'])
    ims, K = views()
    assert all(n in ims for n in train + test)
    img = CAMPUS / 'images'
    img.mkdir(parents=True, exist_ok=True)
    for n in train + test:
        q = img / f'{stem(n)}.jpg'
        if not q.exists():
            a = cv2.imread(str(DENSE / 'images' / n))
            cv2.imwrite(str(q), cv2.resize(a, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 95])
    fx, fy, cx, cy = K
    calib = dict(schema='jointbuildgs.geogs.source_calibration.v1',
                 note='K of the measurement grid with cx - 0.5, cy - 0.5 (fork_inputs_v6 rule)',
                 images={stem(n): dict(width=GRID_W, height=GRID_H, K=[[fx, 0.0, cx - 0.5], [0.0, fy, cy - 0.5], [0.0, 0.0, 1.0]]) for n in train + test})
    recs = [(f'{stem(n)}.jpg', ims[n]['q'], ims[n]['t']) for n in sorted(train + test)]
    dump(CAMPUS / 'split.json', dict(train=[stem(n) for n in train], test=[stem(n) for n in test]))
    (CAMPUS / 'jbgs_calibration.json').write_text(json.dumps(calib, indent=1))
    dump(CAMPUS / 'poses.json', dict(K=K.tolist(), recs=[dict(name=r[0], q=list(map(float, r[1])), t=list(map(float, r[2]))) for r in recs]))
    # identity checks against a FINALTRAIN site scene
    site = S0 / 'fork_inputs/s61/B0_b10'
    sname = sorted(os.listdir(site / 'images'))[0]
    same_pixels = bool(np.array_equal(cv2.imread(str(site / 'images' / sname)), cv2.imread(str(img / sname))))
    same_bytes = sha(site / 'images' / sname) == sha(img / sname)
    site_ims = read_images_bin(site / 'scene_LoD2/sparse/0/images.bin')
    pose_diff = max(float(np.abs(site_ims[k]['q'] - ims[stem(k) + '.JPG']['q']).max() + np.abs(site_ims[k]['t'] - ims[stem(k) + '.JPG']['t']).max()) for k in site_ims)
    site_cal = json.loads((site / 'scene_LoD2/jbgs_calibration.json').read_text())['images']
    k0 = next(iter(site_cal))
    cal_same = site_cal[k0]['K'] == calib['images'][k0]['K']
    dump(CAMPUS / 'scene_receipt.json', dict(at=now(), train=len(train), test=len(test), K=K.tolist(), site_image_same_pixels=same_pixels,
         site_image_same_bytes=same_bytes, site_pose_max_abs_diff=pose_diff, site_calibration_same=cal_same,
         rule='fork_inputs_v6 images/poses/calibration rule; WIDEN0-v2 image_split', scientific_verdict=None))
    print('SCENE', len(train), len(test), same_pixels, same_bytes, pose_diff, cal_same, flush=True)


def write_scene_dir(unit_dir, prior, xyz, rgb, origin, names):
    """scene_<prior>: cameras/images (only listed names) + initial cloud; images and calibration linked to campus."""
    pose = json.loads((CAMPUS / 'poses.json').read_text())
    S = unit_dir / f'scene_{prior}'
    (S / 'sparse/0').mkdir(parents=True, exist_ok=True)
    keep = set(names)
    recs = [(r['name'], np.array(r['q']), np.array(r['t'])) for r in pose['recs'] if stem(r['name']) in keep]
    write_cameras_bin(S / 'sparse/0/cameras.bin', tuple(pose['K']))
    write_images_bin(S / 'sparse/0/images.bin', recs)
    store_ply(S / 'sparse/0/points3D.ply', xyz, rgb)
    np.save(S / 'sparse/0/origin.npy', origin)
    for name in ['images']:
        link = S / name
        if not link.exists():
            os.symlink(os.path.relpath(CAMPUS / name, S), link)
    cal = json.loads((CAMPUS / 'jbgs_calibration.json').read_text())
    cal['images'] = {k: v for k, v in cal['images'].items() if k in keep}
    (S / 'jbgs_calibration.json').write_text(json.dumps(cal, indent=1))
    return S


# ---------------------------------------------------------------- targets

def site_parts(prior):
    out = []
    for i, site in enumerate(SITES):
        t = loadz(FT / 'targets' / f'{site}__{prior}.npz')
        raw = loadz(TG / 'stage0_r1/inputs' / f'{site}_{prior}.npz', ['building', 'mvs_a_u', 'kind', 'centre'])
        assert np.array_equal(raw['centre'], t['centre'])
        out.append((site, t, raw))
    return out


def targets(prior):
    cfg()
    start = time.monotonic()
    ft_src = R / 'scripts/phd/main_finaltrain_v1/targets.py'
    calculate = inherit(ft_src, ['calculate'], dict(np=np))['calculate']
    sites = site_parts(prior)
    site_b = set()
    for _, _, raw in sites:
        site_b |= set(raw['building'].tolist())
    files = sorted(f for f in glob.glob(str(JC / 'core_points' / f'*__{prior}.npz')) if Path(f).name.count('__') == 1)
    keys = ['patch_id', 'building', 'centre', 'normal', 'kind', 'area', 'n', 'u_mvs', 'sigma_P_m', 'prior_height_m', 'mvs_mean_m',
            'photo_code', 'region', 'reason', 'split']
    parts = [];
    seen = set();
    dropped_site_building = dict(patches=0, area=0., buildings=set());
    dup = 0;
    tiles = []
    for f in files:
        z = loadz(f, keys)
        assert (z['split'] == 'development').all()
        m = ~np.isin(z['building'], list(site_b))
        dropped_site_building['patches'] += int((~m).sum());
        dropped_site_building['area'] += float(z['area'][~m].sum())
        dropped_site_building['buildings'] |= set(z['building'][~m].tolist())
        pid = z['patch_id']
        fresh = np.array([p not in seen for p in pid])
        dup += int((m & ~fresh).sum())
        m &= fresh
        seen |= set(pid[m].tolist())
        parts.append({k: (z[k][:, m] if z[k].ndim == 2 and k in ['region', 'reason', 'photo_code'] else z[k][m]) for k in keys})
        tiles.append(dict(file=Path(f).name, sha256=sha(f), kept=int(m.sum())))
    J = {k: np.concatenate([p[k] for p in parts], axis=1 if k in ['region', 'reason', 'photo_code'] else 0) for k in keys}
    # addendum 1: spatial dedup against site patches (< 1.0 m)
    add = json.loads((C / 'addendum1.json').read_text())
    assert sha(C / 'addendum1.json') == json.loads((C / 'addendum1.lock.json').read_text())['sha256']
    from scipy.spatial import cKDTree
    sc = np.concatenate([t['centre'] for _, t, _ in sites])
    dist, _ = cKDTree(sc).query(J['centre'], workers=8)
    near = dist < 1.0
    spatial_dropped = dict(patches=int(near.sum()), area_m2=float(J['area'][near].sum()), buildings=sorted(set(J['building'][near].tolist())))
    J = {k: (J[k][:, ~near] if k in ['region', 'reason', 'photo_code'] else J[k][~near]) for k in keys}
    d = dict(centre=J['centre'], normal=J['normal'], kind=J['kind'], area=J['area'], n=J['n'], u_mvs=J['u_mvs'], sigma_P_m=J['sigma_P_m'],
             prior_height_m=J['prior_height_m'], mvs_mean_m=J['mvs_mean_m'], photo_code=J['photo_code'][0].astype(np.int8),
             judge_region=J['region'][0].astype(np.int8), reason=J['reason'][0].astype(np.int8))
    v = calculate(d, prior)
    # union: site rows (FINALTRAIN, unchanged) then JUDGECHECK rows
    cols = dict(centre=[], normal=[], kind=[], area=[], h=[], sigma=[], target=[], region=[], judge_region=[], reason=[],
                surface_exists=[], sigma_replaced=[], undecided_before=[], source=[], building=[], patch_id=[], bg_u=[], site_index=[])
    for i, (site, t, raw) in enumerate(sites):
        n = len(t['region'])
        for k in ['centre', 'normal', 'kind', 'area', 'h', 'sigma', 'target', 'region', 'judge_region', 'reason', 'surface_exists', 'sigma_replaced', 'undecided_before']:
            cols[k].append(t[k])
        cols['source'].append(np.full(n, i, np.int8));
        cols['building'].append(raw['building'].astype('U96'))
        cols['patch_id'].append(t['patch_id'].astype('U96'));
        cols['bg_u'].append(raw['mvs_a_u'].astype(float))
        cols['site_index'].append(np.arange(n))
    n = len(d['area'])
    for k, val in [('centre', d['centre']), ('normal', d['normal']), ('kind', d['kind']), ('area', d['area']), ('h', v['h']), ('sigma', v['sigma']),
                   ('target', v['target']), ('region', v['region']), ('judge_region', v['judge_region']), ('reason', v['reason']),
                   ('surface_exists', v['surface_exists']), ('sigma_replaced', v['sigma_replaced']), ('undecided_before', v['undecided_before'])]:
        cols[k].append(val)
    cols['source'].append(np.full(n, 3, np.int8));
    cols['building'].append(J['building'].astype('U96'))
    cols['patch_id'].append(J['patch_id'].astype('U96'));
    cols['bg_u'].append(J['u_mvs'].astype(float));
    cols['site_index'].append(np.full(n, -1))
    U = {k: np.concatenate(x) for k, x in cols.items()}
    act = U['surface_exists']
    ref = float(U['area'][act].sum() / np.sum(U['area'][act] / U['sigma'][act]))
    U['sigma_ref'] = np.asarray(ref)
    U['correction_u_median_judgecheck'] = v['correction_u_median']
    out = TU / 'targets' / f'campus__{prior}.npz'
    savez(out, **U)
    # records
    w = ref / U['sigma'][act]
    mean = float(np.average(w, weights=U['area'][act]))
    assert abs(mean - 1) < 1e-9
    judged = set(U['building'].tolist())
    lb = json.loads((WD / 'inputs/lod2_buildings.json').read_text())
    rows = lb['buildings'] if isinstance(lb, dict) and 'buildings' in lb else lb
    def bid(r):
        return r.get('building') or r.get('id') or r.get('gml_id') if isinstance(r, dict) else str(r)
    def barea(r):
        if not isinstance(r, dict):
            return None
        for k in ['footprint_area_m2', 'area_m2', 'footprint_area']:
            if k in r:
                return float(r[k])
        return None
    all_b = {bid(r): barea(r) for r in rows}
    unjudged = sorted(set(all_b) - judged)
    split_rows = {r['building']: r for r in json.loads((WD / 'building_split.json').read_text())['rows']}
    holdout = sorted(b for b, r in split_rows.items() if r['split'] != 'development')
    regions = []
    for code, label in [(1, '일치'), (2, '보존'), (3, '보정'), (0, '결측'), (5, '보정(빈 공간)'), (-1, '목표 없음')]:
        for src, nm in [(None, 'all'), (3, 'judgecheck')] + [(i, s) for i, s in enumerate(SITES)]:
            m = (U['region'] == code) & (np.ones(len(act), bool) if src is None else U['source'] == src)
            regions.append(dict(region=label, source=nm, patches=int(m.sum()), area_m2=float(U['area'][m].sum())))
    site_ref = {s: float(t['sigma_ref']) for s, t, _ in sites}
    rec = dict(at=now(), prior=prior, seconds=time.monotonic() - start, output=str(out), output_sha256=sha(out), patches=len(act),
               active=int(act.sum()), sigma_ref_campus=ref, sigma_ref_sites=site_ref, unclipped_area_weighted_mean=mean,
               judgecheck=dict(tiles=tiles, rule_row='region[0]=new_clipped, reason[0], photo_code[0]', patches=n,
                               buildings=len(set(J['building'].tolist())), duplicates_dropped=dup,
                               addendum1_spatial_dropped=spatial_dropped, site_building_overlap_dropped=dict(patches=dropped_site_building['patches'], area_m2=dropped_site_building['area'],
                                                                  buildings=sorted(dropped_site_building['buildings'])),
                               correction_u_median=float(v['correction_u_median']) if np.isfinite(v['correction_u_median']) else None,
                               undecided_area_m2=float(d['area'][v['undecided_before']].sum())),
               sites={s: dict(patches=int(len(t['region'])), buildings=len(set(raw['building'].tolist()))) for s, t, raw in sites},
               judged_buildings=len(judged), lod2_buildings_listed=len(all_b), unjudged_buildings=len(unjudged),
               unjudged_footprint_area_m2=float(sum(a for b, a in all_b.items() if b in set(unjudged) and a is not None)),
               unjudged_area_known_for=int(sum(1 for b in unjudged if all_b[b] is not None)),
               holdout_buildings=len(holdout), holdout_in_judged=len(set(holdout) & judged), regions=regions,
               sigma_W_used=False, r_added=False, GT_used=False, scientific_verdict=None)
    dump(out.with_suffix('.json'), rec)
    dump(D / 'tables' / f'targets_campus__{prior}.json', rec)
    print('TARGETS', prior, len(act), int(act.sum()), ref, flush=True)


# ---------------------------------------------------------------- seeds

def unit_members(unit, prior, U, sfm_xyz):
    """Patch mask, SfM mask and image names of a unit."""
    split = json.loads((CAMPUS / 'split.json').read_text())
    if unit == 'campus':
        return np.ones(len(U['area']), bool), np.ones(len(sfm_xyz), bool), split['train'], split['test']
    if unit.startswith('probe'):
        # addendum 5: probe regions and image lists from /tu/probes/probes.json (tu_probes.py)
        # addendum 8: probe3/probe4 (runaway roofs) from /tu/probes/probes_add8.json
        src = 'probes.json' if unit in ('probe0', 'probe1', 'probe2') else 'probes_add8.json'
        p = next(x for x in json.loads((TU / 'probes' / src).read_text())['probes'] if x['name'] == unit)
        lo, hi = np.array(p['region_min'], float), np.array(p['region_max'], float)
        inside = lambda xy: (xy[:, 0] >= lo[0]) & (xy[:, 0] < hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] < hi[1])
        return inside(U['centre'][:, :2]), inside(sfm_xyz[:, :2]), p['images'], p['test_images']
    cells = json.loads((TU / 'cells/cells.json').read_text())
    c = next(x for x in cells['cells'] if f'cell{x["id"]}' == unit)
    lo, hi = np.array(c['expanded_min'], float), np.array(c['expanded_max'], float)
    inside = lambda xy: (xy[:, 0] >= lo[0]) & (xy[:, 0] < hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] < hi[1])
    tr = c['images']
    te = [n for n in split['test'] if n in set(c.get('test_images', []))]
    return inside(U['centre'][:, :2]), inside(sfm_xyz[:, :2]), tr, te


def seeds(unit, prior):
    cfg()
    start = time.monotonic()
    sys.path.insert(0, str(R))
    from src.phd.prior_propagation_v6.orientation import quat_from_normal
    U = loadz(TU / 'targets' / f'campus__{prior}.npz')
    sfm_xyz, sfm_rgb = read_points3d_bin(WD / 'mvs/full/sparse/points3D.bin')
    pmask, smask, train, test = unit_members(unit, prior, U, sfm_xyz)
    act = U['surface_exists'] & pmask
    # prior seeds: site rows from FINALTRAIN seeds (unchanged), others one per active patch
    P = dict(orig=[], xyz=[], normal=[], sigma=[], quat=[], region=[], patch=[], repl=[])
    offset = 0
    for i, site in enumerate(SITES):
        n_site = int((U['source'] == i).sum())
        sd = loadz(FT / 'stage1' / f'{site}__{prior}/seeds.npz')
        o = sd['origin'] == 1
        pid = sd['patch'][o] + offset
        take = act[pid]
        P['orig'].append(sd['original_xyz'][sd['keep_original']][take].astype(float))
        P['xyz'].append(sd['xyz'][o][take]);
        P['normal'].append(sd['normal'][o][take]);
        P['sigma'].append(sd['sigma'][o][take])
        P['quat'].append(sd['quaternion'][o][take]);
        P['region'].append(sd['region'][o][take]);
        P['patch'].append(pid[take]);
        P['repl'].append(sd['uncertainty_replaced'][o][take])
        offset += n_site
    jc = np.flatnonzero(act & (U['source'] == 3))
    P['orig'].append(U['centre'][jc]);
    P['xyz'].append(U['target'][jc].astype('f4'));
    P['normal'].append(U['normal'][jc].astype('f4'))
    P['sigma'].append(U['sigma'][jc].astype('f4'));
    P['quat'].append(quat_from_normal(U['normal'][jc]).astype('f4'))
    P['region'].append(U['region'][jc]);
    P['patch'].append(jc);
    P['repl'].append(U['sigma_replaced'][jc])
    P = {k: np.concatenate(v) for k, v in P.items()}
    npri = len(P['patch'])
    n_site_seeds = int((P['patch'] < offset).sum())
    # exclusion of SfM points by the unchanged cylinder rule over all patches of the unit
    c2 = json.loads((R / 'configs/phd/main_target_v1/revisions/r2/target_v1.json').read_text())
    radius = np.array([c2['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan if str(int(k)) in c2['inherited_radius'][prior] else np.nan for k in U['kind']])
    root = TU / 'stage1' / f'{unit}__{prior}'
    root.mkdir(parents=True, exist_ok=True)
    cm = pmask
    cores = root / 'cylinders.bin'
    np.c_[U['centre'][cm], U['normal'][cm], np.where(U['kind'][cm] == 1, 10., 5.), radius[cm]].astype('<f8').tofile(cores)
    sidx = np.flatnonzero(smask)
    np.save(root / 'sfm_original_xyz.npy', sfm_xyz[sidx].astype('f4'))
    cpp = R / 'scripts/phd/main_target_v1/exclude_cylinders_r2.cpp'
    binary = TU / 'tmp' / f'exclude_cylinders_{unit}_{prior}'
    subprocess.run(['g++', '-O3', '-std=c++17', str(cpp), '-o', str(binary)], check=True)
    with (root / 'sfm_original_xyz.npy').open('rb') as f:
        version = np.lib.format.read_magic(f);
        np.lib.format._read_array_header(f, version);
        off = f.tell()
    subprocess.run([str(binary), str(root / 'sfm_original_xyz.npy'), str(off), str(len(sidx)), str(cores), str(int(cm.sum())), str(root / 'excluded.bin')], check=True)
    excluded = np.fromfile(root / 'excluded.bin', dtype=np.uint8).astype(bool)
    bg = sidx[~excluded]
    nb = len(bg)
    donors = U['bg_u'][(U['kind'] == 1) & np.isfinite(U['bg_u'])]
    assert len(donors) and np.median(donors) > 0
    bg_sigma = float(np.hypot(np.median(donors), .0275))
    # scene cloud: prior originals then the unit's SfM points; float32 positions as read by the fork
    xyz = np.r_[P['orig'], sfm_xyz[sidx]]
    rgb = np.r_[np.full((npri, 3), 128, np.uint8), sfm_rgb[sidx]]
    origin = np.r_[np.ones(npri, np.int8), np.zeros(len(sidx), np.int8)]
    S = write_scene_dir(TU / 'scenes' / unit, prior, xyz, rgb, origin, train + test)
    v = PlyData.read(str(S / 'sparse/0/points3D.ply'))['vertex']
    oxyz = np.c_[v['x'], v['y'], v['z']].astype('f4')
    orgb = np.c_[v['red'], v['green'], v['blue']].astype('f4') / 255
    bg_rows = npri + np.flatnonzero(~excluded)
    normal = np.r_[P['normal'], np.tile(np.array([0., 0., 1.], 'f4'), (nb, 1))].astype('f4')
    pos = np.r_[P['xyz'], oxyz[bg_rows]].astype('f4')
    sigma = np.r_[P['sigma'], np.full(nb, bg_sigma, 'f4')].astype('f4')
    assert np.isfinite(pos).all() and np.isfinite(sigma).all() and (sigma > 0).all()
    q_all = quat_from_normal(normal.astype(float)).astype('f4')
    q_site_diff = float(np.abs(q_all[:npri] - P['quat']).max()) if npri else 0.
    if unit == 'campus':
        split_unit = dict(train=train, test=test)
    else:
        split_unit = dict(train=train, test=test)
    dump(TU / 'scenes' / unit / 'split.json', split_unit)
    if unit != 'campus':
        remap = np.full(len(pmask), -1, np.int64)
        remap[pmask] = np.arange(int(pmask.sum()))
        P['patch'] = remap[P['patch']]
        assert (P['patch'] >= 0).all()
    savez(root / 'seeds.npz', original_xyz=oxyz, keep_original=np.arange(npri), xyz=pos, target=pos, normal=normal, sigma=sigma,
          quaternion=np.r_[P['quat'], q_all[npri:]].astype('f4'), origin=np.r_[np.ones(npri, 'i1'), np.zeros(nb, 'i1')],
          region=np.r_[P['region'], np.full(nb, 4, 'i1')].astype('i1'), patch=np.r_[P['patch'], np.full(nb, -1, 'i8')].astype('i8'),
          background_rgb=orgb[bg_rows], background_original=bg_rows, uncertainty_replaced=np.r_[P['repl'], np.ones(nb, bool)])
    # the fork reads targets/<unit>__<prior>.npz next to stage1: cells get the subset file with cell-local patch indices
    if unit != 'campus':
        sub = {k: (U[k][pmask] if np.ndim(U[k]) and len(U[k]) == len(pmask) else U[k]) for k in U}
        sub['campus_index'] = np.flatnonzero(pmask)
        savez(TU / 'targets' / f'{unit}__{prior}.npz', **sub)
    rec = dict(at=now(), unit=unit, prior=prior, seconds=time.monotonic() - start, train_images=len(train), test_images=len(test),
               prior_seeds=npri, prior_seeds_site=n_site_seeds, prior_seeds_judgecheck=npri - n_site_seeds,
               unit_patches=int(pmask.sum()), unit_active_patches=int(act.sum()), sfm_points_in_unit=len(sidx), background_kept=nb,
               background_sigma=bg_sigma, site_quaternion_max_abs_diff=q_site_diff, seeds_sha256=sha(root / 'seeds.npz'),
               ply_sha256=sha(S / 'sparse/0/points3D.ply'), exclusion_code_sha256=sha(cpp), background_bound=False,
               initialization='FINALTRAIN r8 rule: prior seeds at targets with patch-normal quaternion, SfM background after cylinder exclusion',
               scientific_verdict=None)
    dump(root / 'seed_receipt.json', rec)
    print('SEEDS', unit, prior, npri, nb, flush=True)


# ---------------------------------------------------------------- maps

def read_depth(p):
    b = Path(p).read_bytes()
    i = 0
    parts = []
    for _ in range(3):
        j = b.index(b'&', i)
        parts.append(int(b[i:j]))
        i = j + 1
    w, h, c = parts
    a = np.frombuffer(b[i:], np.float32).reshape((w, h, c), order='F')
    return np.transpose(a, (1, 0, 2)).squeeze()


def cameras(names):
    """Inherited judgeapply Cameras K/W2C rule on the campus poses and calibration."""
    pose = json.loads((CAMPUS / 'poses.json').read_text())
    by = {stem(r['name']): r for r in pose['recs']}
    cal = json.loads((CAMPUS / 'jbgs_calibration.json').read_text())['images']
    qR = scope['qR']
    out = []
    for n in names:
        r = by[n]
        R_ = qR(np.array(r['q']))
        M = np.eye(4, dtype='f4')
        M[:3, :3] = R_
        M[:3, 3] = r['t']
        k = np.array(cal[n]['K'])
        f32 = np.float32
        fx = float(f32(f32(512) * f32(2 * k[0, 0] / 1024)))
        fy = float(f32(f32(741 / 2) * f32(2 * k[1, 1] / 741)))
        cx = float(f32(f32(f32(512) * f32((2 * k[0, 2] + 1 - 1024) / 1024)) + f32(1023 / 2)))
        cy = float(f32(f32(f32(741 / 2) * f32((2 * k[1, 2] + 1 - 741) / 741)) + f32(740 / 2)))
        out.append(dict(name=n, H=741, W=1024, W2C=M, fx=fx, fy=fy, cx=cx, cy=cy))
    return out


def maps(unit, prior, part, parts):
    cfg()
    part, parts = int(part), int(parts)
    U = loadz(TU / 'targets' / f'{unit}__{prior}.npz', ['target', 'normal', 'area', 'sigma', 'surface_exists', 'centre', 'sigma_ref'])
    root = TU / 'stage1' / f'{unit}__{prior}'
    rec = json.loads((root / 'seed_receipt.json').read_text())
    sd = loadz(root / 'seeds.npz', ['origin', 'patch'])
    split = json.loads((TU / 'scenes' / unit / 'split.json').read_text())
    src = R / 'scripts/phd/main_target_v1/prepare_maps_r7.py'
    env = dict(np=np, ctypes=ctypes, subprocess=subprocess, Path=Path, __file__=str(src), OUT=TU / 'tmp' / f'maps_{unit}_{prior}_{part}')
    (env['OUT'] / 'tmp').mkdir(parents=True, exist_ok=True)
    inherit(src, ['rasterizer', 'draw'], env)
    fn = env['rasterizer']()
    ids = np.flatnonzero(U['surface_exists'])
    points = np.c_[U['target'][ids], U['normal'][ids], np.sqrt(U['area'][ids] / np.pi), ids].astype(float)
    ref = float(U['sigma_ref'])
    bg_sigma = rec['background_sigma']
    dest = root / 'maps'
    dest.mkdir(exist_ok=True)
    names = sorted(split['train'])[part::parts]
    for j, cam in enumerate(cameras(names)):
        name = cam['name']
        p = dest / f'{name}.npz'
        if p.exists():
            continue
        depth, owner, K, M = env['draw'](fn, points, cam)
        has = owner >= 0
        sigma = np.full(depth.shape, np.nan, 'f4')
        sigma[has] = U['sigma'][owner[has]]
        mvs = read_depth(WD / 'mvs/full/stereo/depth_maps' / f'{name}.JPG.geometric.bin')
        conf = (np.isfinite(mvs) & (mvs > 0)).astype('f4')
        bg = (~has) & np.isfinite(mvs) & (mvs > 0) & (conf > 0)
        depth[bg] = mvs[bg]
        sigma[bg] = bg_sigma
        weight = np.zeros(depth.shape, 'f4')
        weight[has] = np.clip(ref / sigma[has], .1, 10)
        weight[bg] = 1
        tmp = dest / f'.{name}.tmp.npz'
        np.savez_compressed(tmp, depth=depth, sigma=sigma, weight=weight, owner=owner)
        os.replace(tmp, p)
        meta = dict(file=p.name, sha256=sha(p), sigma_ref=ref, prior_pixels=int(has.sum()), background_pixels=int(bg.sum()), K=K.tolist(), W2C=M.tolist(),
                    mvs_input=f'{name}.JPG.geometric.bin', weights_low=int((weight[has] <= np.float32(.1)).sum()), weights_high=int((weight[has] >= 10).sum()))
        dump(dest / f'.{name}.meta.json', meta)
        if (j + 1) % 25 == 0:
            print('MAPS', unit, prior, part, j + 1, len(names), flush=True)
    print('MAPS_DONE', unit, prior, part, len(names), flush=True)


def index(unit, prior):
    cfg()
    root = TU / 'stage1' / f'{unit}__{prior}'
    split = json.loads((TU / 'scenes' / unit / 'split.json').read_text())
    U = loadz(TU / 'targets' / f'{unit}__{prior}.npz', ['sigma_ref'])
    views = {}
    tot = low = high = 0
    samples = []
    for name in sorted(split['train']):
        meta = json.loads((root / 'maps' / f'.{name}.meta.json').read_text())
        assert sha(root / 'maps' / meta['file']) == meta['sha256']
        low += meta.pop('weights_low');
        high += meta.pop('weights_high');
        tot += meta['prior_pixels']
        views[name] = meta
    for name in sorted(split['train'])[::20]:
        z = loadz(root / 'maps' / f'{name}.npz', ['weight', 'owner'])
        samples.append(z['weight'][z['owner'] >= 0])
    w = np.concatenate(samples) if samples else np.zeros(0)
    idx = dict(at=now(), unit=unit, prior=prior, sigma_ref=float(U['sigma_ref']), weight_power=1, background_weight=1,
               target_sha256=sha(TU / 'targets' / f'{unit}__{prior}.npz'), views=views, scientific_verdict=None)
    dump(root / 'maps/index.json', idx)
    rec = dict(at=now(), unit=unit, prior=prior, sigma_ref=float(U['sigma_ref']), views=len(views), patch_pixels=tot,
               weight_q01_q10_q50_q90_q99_every20th_view=np.quantile(w, [.01, .1, .5, .9, .99]).tolist() if len(w) else None,
               clip_low_fraction=low / tot if tot else None, clip_high_fraction=high / tot if tot else None,
               map_index_sha256=sha(root / 'maps/index.json'), seeds_sha256=sha(root / 'seeds.npz'), scientific_verdict=None)
    dump(root / 'ready.json', rec)
    dump(D / 'tables' / f'pixel_weights_{unit}__{prior}.json', rec)
    print('READY', unit, prior, len(views), flush=True)


if __name__ == '__main__':
    mode = sys.argv[1]
    dict(scene=scene, targets=targets, seeds=seeds, maps=maps, index=index)[mode](*sys.argv[2:])
