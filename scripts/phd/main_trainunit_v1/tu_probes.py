"""Addendum 5 probes (원인 확인): regions and image lists of probe0/1/2 around FINALTRAIN B0_b10. Writes /tu/probes/probes.json.

  python tu_probes.py define
The seeds/maps/index steps reuse tu_campus.py unchanged (unit = probe<k>; tu_campus.unit_members reads probes.json).
"""
import sys

from tu_common import *
from tu_campus import CAMPUS, cameras, read_points3d_bin
from tu_cells import boxes, coverage

C5 = C / 'addendum5.json'


def define():
    cfg()
    assert sha(C5) == json.loads((C / 'addendum5.lock.json').read_text())['sha256'], 'addendum 5 changed after lock'
    site = 'B0_b10'
    b = boxes()[site]
    lo0 = np.array(b['min'][:2], float); hi0 = np.array(b['max'][:2], float)
    c = (lo0 + hi0) / 2; h = (hi0 - lo0) / 2
    lo1 = c - np.sqrt(5) * h; hi1 = c + np.sqrt(5) * h
    ft_split = json.loads((S0 / 'fork_inputs/s61' / site / 'split.json').read_text())
    campus = json.loads((CAMPUS / 'split.json').read_text())
    allnames = set(campus['train']) | set(campus['test'])
    base_train, base_test = sorted(ft_split['train']), sorted(ft_split['test'])
    assert all(n in allnames for n in base_train + base_test), 'FINALTRAIN B0 images missing from the campus scene'
    sfm, _ = read_points3d_bin(WD / 'mvs/full/sparse/points3D.bin')
    ins = (sfm[:, 0] >= lo0[0]) & (sfm[:, 0] < hi0[0]) & (sfm[:, 1] >= lo0[1]) & (sfm[:, 1] < hi0[1])
    z0, z1 = np.percentile(sfm[ins, 2], [.5, 99.5])
    cams = {x['name']: x for x in cameras(campus['train'])}
    cov = {n: coverage(cams[n], np.r_[lo0, z0], np.r_[hi0, z1]) for n in campus['train'] if n not in set(base_train) | set(base_test)}
    added = sorted(n for n, f in cov.items() if f >= .25)
    # addendum 6: probe1 images by the 판 다 rule on the x5 region (position, then >= 25 % projected coverage)
    assert sha(C / 'addendum6.json') == json.loads((C / 'addendum6.lock.json').read_text())['sha256'], 'addendum 6 changed after lock'
    centre = {n: -np.asarray(cams[n]['W2C'], float)[:3, :3].T @ np.asarray(cams[n]['W2C'], float)[:3, 3] for n in cams}
    ins1 = (sfm[:, 0] >= lo1[0]) & (sfm[:, 0] < hi1[0]) & (sfm[:, 1] >= lo1[1]) & (sfm[:, 1] < hi1[1])
    z10, z11 = np.percentile(sfm[ins1, 2], [.5, 99.5])
    pos1 = [n for n in campus['train'] if n not in set(base_test) and lo1[0] <= centre[n][0] < hi1[0] and lo1[1] <= centre[n][1] < hi1[1]]
    cov1 = {n: coverage(cams[n], np.r_[lo1, z10], np.r_[hi1, z11]) for n in campus['train'] if n not in set(pos1) | set(base_test)}
    vis1 = sorted(n for n, f in cov1.items() if f >= .25)
    images1 = sorted(pos1 + vis1)
    # addendum 7: probe0 keeps only the B0 training images that are WIDEN0 training images (the 판 다 image rule)
    assert sha(C / 'addendum7.json') == json.loads((C / 'addendum7.lock.json').read_text())['sha256'], 'addendum 7 changed after lock'
    images0 = sorted(n for n in base_train if n in set(campus['train']))
    probes = [
        dict(id=0, name='probe0', role='control: 판 다 pipeline on the B0 region', region_min=lo0.tolist(), region_max=hi0.tolist(),
             area_m2=float(np.prod(hi0 - lo0)), images=images0, test_images=base_test, base_images_dropped_widen0_evaluation=len(base_train) - len(images0)),
        dict(id=1, name='probe1', role='cell-like unit of x5 area centred on B0 (addendum 6)', region_min=lo1.tolist(), region_max=hi1.tolist(),
             area_m2=float(np.prod(hi1 - lo1)), images=images1, test_images=base_test, position_selected=len(pos1), visibility_added=len(vis1),
             base_images_included=len(set(images1) & set(base_train)), projection_box_min=[*lo1.tolist(), float(z10)],
             projection_box_max=[*hi1.tolist(), float(z11)]),
        dict(id=2, name='probe2', role='images added by the 판 다 visibility rule', region_min=lo0.tolist(), region_max=hi0.tolist(),
             area_m2=float(np.prod(hi0 - lo0)), images=sorted(base_train + added), test_images=base_test, images_added=len(added),
             projection_box_min=[*lo0.tolist(), float(z0)], projection_box_max=[*hi0.tolist(), float(z1)],
             coverage_quantiles_of_candidates=np.quantile(list(cov.values()), [.1, .5, .9]).tolist()),
    ]
    out = TU / 'probes/probes.json'
    dump(out, dict(at=now(), addendum=5, addendum_sha256=sha(C5), addendum6_sha256=sha(C / 'addendum6.json'), addendum7_sha256=sha(C / 'addendum7.json'), probe2_run=False, base=f'FINALTRAIN {site} ALS', box_source=b['source'],
                   sfm_points_in_region0=int(ins.sum()), probes=probes, scientific_verdict=None))
    for p in probes:
        print('PROBE', p['name'], round(p['area_m2']), len(p['images']), len(p['test_images']), flush=True)


C8 = C / 'addendum8.json'
ROOFS = dict(probe3=('roof A', 'DEBY_LOD2_4906972', (-5.0464, -138.9285)), probe4=('roof B', 'DEBY_LOD2_4959327', (112.5560, 228.3277)))


def define8():
    """addendum 8: small units around the two runaway roofs, 판 다 image rule on a square of the probe0 area."""
    cfg()
    assert sha(C8) == json.loads((C / 'addendum8.lock.json').read_text())['sha256'], 'addendum 8 changed after lock'
    area = float(json.loads((TU / 'probes/probes.json').read_text())['probes'][0]['area_m2'])
    half = np.sqrt(area) / 2
    campus = json.loads((CAMPUS / 'split.json').read_text())
    train, test = list(campus['train']), list(campus['test'])
    sfm, _ = read_points3d_bin(WD / 'mvs/full/sparse/points3D.bin')
    cams = {x['name']: x for x in cameras(train + test)}
    centre = {n: -np.asarray(cams[n]['W2C'], float)[:3, :3].T @ np.asarray(cams[n]['W2C'], float)[:3, 3] for n in cams}
    probes = []
    for name, (label, building, c) in ROOFS.items():
        c = np.array(c, float)
        lo, hi = c - half, c + half
        ins = (sfm[:, 0] >= lo[0]) & (sfm[:, 0] < hi[0]) & (sfm[:, 1] >= lo[1]) & (sfm[:, 1] < hi[1])
        z0, z1 = np.percentile(sfm[ins, 2], [.5, 99.5])
        blo, bhi = np.r_[lo, z0], np.r_[hi, z1]
        inside = lambda n: lo[0] <= centre[n][0] < hi[0] and lo[1] <= centre[n][1] < hi[1]
        pos = [n for n in train if inside(n)]
        cov = {n: coverage(cams[n], blo, bhi) for n in train if n not in set(pos)}
        vis = sorted(n for n, f in cov.items() if f >= .25)
        tst = [n for n in test if inside(n)]
        tst_cov = []
        if len(tst) < 5:
            tst_cov = sorted(n for n in test if n not in set(tst) and coverage(cams[n], blo, bhi) >= .25)
        probes.append(dict(id=int(name[5:]), name=name, role=f'{label} {building}: runaway family roof alone, 판 다 pipeline (addendum 8)',
                           region_min=lo.tolist(), region_max=hi.tolist(), area_m2=float(np.prod(hi - lo)), centre=c.tolist(),
                           images=sorted(pos + vis), test_images=sorted(tst + tst_cov), position_selected=len(pos), visibility_added=len(vis),
                           test_position=len(tst), test_coverage_added=len(tst_cov), projection_box_min=blo.tolist(), projection_box_max=bhi.tolist(),
                           sfm_points_in_region=int(ins.sum()),
                           coverage_quantiles_of_others=np.quantile(list(cov.values()), [.1, .5, .9]).tolist()))
    out = TU / 'probes/probes_add8.json'
    dump(out, dict(at=now(), addendum=8, addendum_sha256=sha(C8), base='판 다 pipeline (campus targets, campus SfM, WIDEN0 MVS background), ALS',
                   probes=probes, scientific_verdict=None))
    for p in probes:
        print('PROBE', p['name'], round(p['area_m2']), len(p['images']), p['position_selected'], p['visibility_added'], len(p['test_images']), flush=True)


def watch(unit):
    """addendum 8: the unit's prior seeds (init_id = seeds.npz row) whose campus patch is the seed patch of a cell top-3 family."""
    cfg()
    assert sha(C8) == json.loads((C / 'addendum8.lock.json').read_text())['sha256'], 'addendum 8 changed after lock'
    p = next(x for x in json.loads((TU / 'probes/probes_add8.json').read_text())['probes'] if x['name'] == unit)
    lo, hi = np.array(p['region_min']), np.array(p['region_max'])
    fam = json.loads((D / 'tables/cause_top_families.json').read_text())
    fam = fam['rows'] if isinstance(fam, dict) else fam
    sd = loadz(TU / 'stage1' / f'{unit}__ALS/seeds.npz', ['origin', 'patch'])
    ci_unit = loadz(TU / 'targets' / f'{unit}__ALS.npz', ['campus_index'])['campus_index']
    rows = []
    for r in fam:
        if not r['key'].startswith('cell'):
            continue
        x, y = r['seed_xyz'][:2]
        if not (lo[0] <= x < hi[0] and lo[1] <= y < hi[1]):
            continue
        ci_cell = loadz(TU / 'targets' / f'{r["key"]}__ALS.npz', ['campus_index'])['campus_index']
        campus_patch = int(ci_cell[r['patch']])
        hit = np.flatnonzero((sd['origin'] == 1) & (sd['patch'] >= 0) & (ci_unit[np.maximum(sd['patch'], 0)] == campus_patch))
        rows.append(dict(cell=r['key'], rank=r['rank'], cell_init_id=r['init_id'], cell_family_late=r['family_late'], building=r['patch_building'],
                         campus_patch=campus_patch, unit_init_ids=hit.tolist()))
    out = TU / 'stage1' / f'{unit}__ALS/watch.json'
    dump(out, dict(at=now(), unit=unit, addendum=8, families=rows, scientific_verdict=None))
    for w in rows:
        print('WATCH', unit, w['cell'], w['rank'], w['campus_patch'], w['unit_init_ids'], flush=True)


if __name__ == '__main__':
    dict(define=define, define8=define8, watch=watch)[sys.argv[1]](*sys.argv[2:])
