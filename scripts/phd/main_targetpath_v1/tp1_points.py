"""Order 1: point groups per scene (CPU). usage: tp1_points.py <stem>
Source: wrong-target point files (WT points/wt_<stem>.npz; point_id = GTJUDGE addendum11 row).
  가 (target points: case_id 2 = image depth outside tau and prior inside, method target ok): 잃음 all, 지킴 5,000 (fixed rng; all if fewer)
  나 (case_id 1, method target wrong): 고침 5,000, 고치지 못함 all (5,000 if more)
  대조 (case_id 0, method target ok): 잃음 all (5,000 if more), 지킴 5,000
rng = numpy default_rng(SEED + scene index in STEMS), choice without replacement, sorted.
Per point also: oriented normal (GT target square covering the point, GTTARGET g1_cover rule + oriented stage-1 normal; fallback addendum11
normal flipped toward the majority of training cameras), GTT group (target / result meshes of gtt_s0, GTTARGET g3_ga rule), method patch
correctness (share of WT points of the method patch whose method target is ok)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from scipy.spatial import cKDTree

def cover(site, X):  # copy of GTTARGET g3_ca.cover (g1_cover rule)
    p = loadz(GTT/'surface'/site/'patches.npz', ['centre', 'normal']); C = p['centre'].astype('f8'); Nn = p['normal'].astype('f8'); tree = cKDTree(C); h = .125+.02
    d, j = tree.query(X, k=8, distance_upper_bound=1.0, workers=16); best = np.full(len(X), np.inf); cov = np.full(len(X), -1)
    for qq in range(8):
        jj = j[:, qq]; v = jj < len(C); jj = np.where(v, jj, 0); r = X-C[jj]; dn = (r*Nn[jj]).sum(1); w = np.abs(dn); ip = np.linalg.norm(r-dn[:, None]*Nn[jj], axis=1)
        ok = v & (ip <= np.sqrt(2)*h) & (w < best); best = np.where(ok, w, best); cov = np.where(ok, jj, cov)
    return cov

def main(stem):
    t0 = time.monotonic(); site, prior = stem.split('__'); w = loadz(WT/'points'/f'wt_{stem}.npz'); n = len(w['point_id'])
    rng = np.random.default_rng(SEED+STEMS.index(stem)); g = w['group']; ok = w['method_target_ok']; c = w['case_id']
    def pick(m, k):
        i = np.flatnonzero(m); return np.sort(rng.choice(i, k, replace=False)) if len(i) > k else i
    sets = [pick((c == 2) & ok & (g == 1), 10**9), pick((c == 2) & ok & (g == 0), SAMPLE), pick((c == 1) & ~ok & (g == 2), SAMPLE),
            pick((c == 1) & ~ok & (g == 3), SAMPLE), pick((c == 0) & ok & (g == 1), SAMPLE), pick((c == 0) & ok & (g == 0), SAMPLE)]
    full = {'target': int(((c == 2) & ok).sum()), 'target_lost': int(((c == 2) & ok & (g == 1)).sum()), 'c1_fixed': int(((c == 1) & ~ok & (g == 2)).sum()),
            'c1_both': int(((c == 1) & ~ok & (g == 3)).sum()), 'c0_lost': int(((c == 0) & ok & (g == 1)).sum()), 'c0_kept': int(((c == 0) & ok & (g == 0)).sum())}
    rows = np.concatenate(sets); grp = np.concatenate([np.full(len(s), k, 'i1') for k, s in enumerate(sets)])
    pid = w['point_id'][rows]; X = w['xyz'][rows].astype('f8')
    A = gt_reference(stem); assert np.abs(A['reference__xyz'][pid]-X).max() < 1e-3
    # oriented normal
    v = cover(site, X); gt = loadz(GTT/'targets'/f'{stem}.npz', ['normal']); nrm = np.where((v >= 0)[:, None], gt['normal'][np.clip(v, 0, None)], np.nan)
    n11 = A['reference__normal'][pid].astype('f8'); idx = json.loads((maps_of(stem, 'ft')/'index.json').read_text())['views']
    side = np.zeros(len(X))
    for vv in idx.values():
        K = np.asarray(vv['K']); M = np.asarray(vv['W2C']); u, y, z, okz = project(X, K, M); inn = okz & (u >= 0) & (u < 1024) & (y >= 0) & (y < 741)
        side += np.where(inn, np.sign(((cam_centre(M)[None]-X)*n11).sum(1)), 0)
    n11 = n11*np.where(side < 0, -1., 1.)[:, None]; fb = ~np.isfinite(nrm[:, 0]); nrm[fb] = n11[fb]
    agree = np.einsum('ij,ij->i', nrm[~fb], n11[~fb]) if (~fb).any() else np.zeros(0)
    # GTT group (g3_ga rule): 0 kept, 1 lost, 2 target outside & result inside, 3 both outside; -1 = no GTT run
    gg = np.full(len(X), -1, 'i1'); gtt_t = GTT/'meshes'/f'{stem}__gtt_target/points.npz'; gtt_b = GTT/'meshes'/f'{stem}__gtt_s0_base/points.npz'
    if gtt_t.exists() and gtt_b.exists():
        tw = loadz(gtt_t, ['reference__within_tau1'])['reference__within_tau1'].astype(bool)[pid]; rw = loadz(gtt_b, ['reference__within_tau1'])['reference__within_tau1'].astype(bool)[pid]
        gg = np.where(tw, np.where(rw, 0, 1), np.where(rw, 2, 3)).astype('i1')
    # method patch correctness from every WT point of the patch
    pr = w['patch_row']; m = pr >= 0; N = int(pr.max())+1; cnt = np.bincount(pr[m], minlength=N); okc = np.bincount(pr[m], ok[m], minlength=N)
    patch_ok_share = np.where(cnt > 0, okc/np.maximum(cnt, 1), np.nan)
    out = dict(point_id=pid, wt_row=rows, group=grp, xyz=X.astype('f4'), normal=nrm.astype('f4'), normal_from_gt_square=~fb, gt_square=v.astype('i8'),
               tau=w['tau'][rows], case_id=c[rows], method_region=w['method_region'][rows], patch_row=pr[rows], method_target_ok=ok[rows],
               s_mvs=w['s_mvs'][rows], s_prior=w['s_prior'][rows], s_result=w['s_result'][rows], wall=w['wall'][rows], group_gtt=gg, group_occl=w['group_occl'][rows],
               patch_ok_share_all=patch_ok_share.astype('f4'))
    savez(O/'points'/f'sel_{stem}.npz', **out)
    rec = dict(at=now(), stem=stem, title=TITLE, counts_full=full, selected={GRP[k]: int((grp == k).sum()) for k in range(6)},
               normal_from_gt_square_pct=pct(~fb), normal_agree_with_addendum11_median=float(np.median(agree)) if len(agree) else None,
               gtt_group_of_target_lost=({k: int(((grp == 0) & (gg == k)).sum()) for k in range(-1, 4)}), rng=f'default_rng({SEED}+{STEMS.index(stem)})',
               seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(O/'points'/f'sel_{stem}.json', rec); print('TP1', json.dumps(rec, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(sys.argv[1])
