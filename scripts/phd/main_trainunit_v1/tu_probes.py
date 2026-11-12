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
    probes = [
        dict(id=0, name='probe0', role='control: 판 다 pipeline on the B0 region', region_min=lo0.tolist(), region_max=hi0.tolist(),
             area_m2=float(np.prod(hi0 - lo0)), images=base_train, test_images=base_test),
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
    dump(out, dict(at=now(), addendum=5, addendum_sha256=sha(C5), addendum6_sha256=sha(C / 'addendum6.json'), probe2_run=False, base=f'FINALTRAIN {site} ALS', box_source=b['source'],
                   sfm_points_in_region0=int(ins.sum()), probes=probes, scientific_verdict=None))
    for p in probes:
        print('PROBE', p['name'], round(p['area_m2']), len(p['images']), len(p['test_images']), flush=True)


if __name__ == '__main__':
    dict(define=define)[sys.argv[1]](*sys.argv[2:])
