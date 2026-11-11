"""Supplementary to check 3 (not in the order's classes, not used for culprit candidates): group-level vote.
For each seen view the drawer Gaussian's group (같은 패치 / 이웃 패치 / 풀림 / 배경, same rules as 3-가..라); a point gets the group drawing in more
than half of its seen views, else 섞임; no drawer in any view = 없음. Applied to the same points as check 3 (c1/c2 1-라 lost, c3 lost, all control)."""
from common import *
G = ['같은 패치', '이웃 패치', '풀림', '배경', '섞임', '없음']
def main(tag=''):
    rows = []
    for cell in ['c1', 'c2', 'c3']:
        stem = STEMS[cell]
        for arm in ARMS:
            name = f'{stem}__{arm}' + (f'__{tag}' if tag else ''); z = loadz(O/'checks'/f'{name}.npz'); V = loadz(O/'views'/f'{name}.npz', ['point']); Rr = loadz(O/'render'/f'{name}.npz', ['drawer'])
            model = Path(arm_paths(stem, arm)['model']); snap = loadz(model/'target_monitor/snapshot_30000.npz', ['origin', 'target_tag', 'target_index', 'patch_ids'])
            d = Rr['drawer']; ok = d >= 0; dd = np.clip(d, 0, None); tagv = snap['target_tag'][dd]; ori = snap['origin'][dd]; bp = np.where(tagv == 1, snap['patch_ids'][np.clip(snap['target_index'][dd], 0, None)], -1)
            pr = z['patch_row'][V['point']]; grp = np.where(~ok, -1, np.where((tagv == 1) & (bp == pr), 0, np.where(tagv == 1, 1, np.where(ori == 1, 2, 3))))
            n = len(z['cell']); seen = np.bincount(V['point'], minlength=n); cnt = np.stack([np.bincount(V['point'], weights=grp == k, minlength=n) for k in range(4)], 1)
            best = cnt.argmax(1); lab = np.where(seen == 0, 5, np.where(cnt.max(1)*2 > seen, best, 4)); lab[(seen > 0) & (cnt.sum(1) == 0)] = 5
            m = z['cell'] == int(cell[1]); L = m & (z['set'] == 0) & (z['check3'] != '대상 아님'); K = m & (z['set'] == 1)
            for k, g in enumerate(G):
                a = 100*float((lab[L] == k).mean()) if L.any() else None; b = 100*float((lab[K] == k).mean()) if K.any() else None
                rows.append(dict(cell=cell, arm=arm, run=tag or 'stored', group=g, lost_n=int((lab[L] == k).sum()), lost_pct_of_check3_points=a, control_n=int((lab[K] == k).sum()), control_pct=b,
                                 ratio=(a/b if a is not None and b else None), lost_pct_of_all_lost=100*float((lab[L] == k).sum())/max(1, int((m & (z['set'] == 0)).sum()))))
    table('check3_group_vote' + (f'_{tag}' if tag else ''), rows); print('VOTE', len(rows))
if __name__ == '__main__': main(*sys.argv[1:])
