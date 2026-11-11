"""Order 6.1 view-group meshes (check6_addendum_v1 c3_view_drop). Container (CPU).
  plan <stem> <arm> <cell>  : views to drop = views that are 'wrong' for more than half of the cell's 4-가 lost points seeing them
                              (c3: 'wrong' = the render reproduces the wrong result surface; c1/c2: |d| > tau)
  apply <stem> <family>     : after the unchanged prepare step, set the dropped views' depth to 0 in final_work/inputs/depth_masked.npy
                              (streamed TSDF integrates only depth > 0, so a zero view adds nothing); recorded with sha256 before/after"""
from common import *
def plan(stem, arm, cell):
    z = loadz(O/'checks'/f'{stem}__{arm}.npz'); pr = loadz(O/'checks'/f'{stem}__{arm}_pairs.npz', ['point', 'view', 'right', 'empty'])
    pts = np.flatnonzero((z['cell'] == int(cell[1])) & (z['set'] == 0) & (z['check4'] == '4-가')); m = np.isin(pr['point'], pts); v = pr['view'][m]
    bad = pr['right'][m] if cell == 'c3' else (~pr['right'][m] & ~pr['empty'][m])
    nviews = len([x for x in json.loads((GT/'views'/f'{stem.split("__")[0]}.json').read_text())['views'] if not x['virtual']])
    nv = np.bincount(v, minlength=nviews); nb = np.bincount(v, weights=bad, minlength=nviews); drop = np.flatnonzero((nv > 0) & (nb*2 > nv))
    fam = f'vdrop_{arm}'; dump(O/'sim'/f'{stem}__{fam}'/'drop_views.json', dict(at=now(), stem=stem, arm=arm, cell=cell, points_4ga=len(pts), views_seen=int((nv > 0).sum()), views=nviews,
        drop=drop.tolist(), rule=cfg()['check6']['view_groups'], addendum='configs/phd/main_trainerr_v1/check6_addendum_v1.json c3_view_drop', scientific_verdict=None))
    print('PLAN', stem, arm, cell, len(pts), int((nv > 0).sum()), len(drop), flush=True)
def apply(stem, family):
    d = json.loads((O/'sim'/f'{stem}__{family}'/'drop_views.json').read_text())['drop']; p = O/'gtj/meshes'/f'{stem}__{family}'/'final_work/inputs/depth_masked.npy'
    before = sha(p); a = np.load(p, mmap_mode='r+'); assert len(d) == 0 or max(d) < len(a)
    for j in d: a[j] = 0
    a.flush(); del a; after = sha(p)
    dump(O/'sim'/f'{stem}__{family}'/'apply.json', dict(at=now(), dropped=d, depth_sha256_before=before, depth_sha256_after=after, rule='depth of dropped views set to 0 after the inherited prepare step', scientific_verdict=None))
    print('APPLIED', stem, family, len(d), flush=True)
if __name__ == '__main__':
    a = sys.argv[1:]; (plan if a[0] == 'plan' else apply)(*a[1:])
