"""Order 5, check 1 failed: where are the GT rows that the target mesh misses? (CPU) usage: g1_fail.py <stem> | g1_fail.py figure
Per row: target-mesh state (within tau / surface but outside tau / no surface), whether a GT patch square covers it within tau (patch level),
wall flag, and the method's target mesh (judgment_mesh, addendum11 final_data) on the same rows for the same recipe."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from scipy.spatial import cKDTree

def square_cover(site, X, tau):
    p = loadz(O/'surface'/site/'patches.npz'); tree = cKDTree(p['centre']); d, j = tree.query(X, k=8, distance_upper_bound=1.0, workers=16); best = np.full(len(X), np.inf)
    for q in range(8):
        jj = j[:, q]; v = jj < len(p['centre']); jj = np.where(v, jj, 0); D = X-p['centre'][jj]
        hit = v & (np.abs((D*p['t1'][jj]).sum(1)) <= .145) & (np.abs((D*p['t2'][jj]).sum(1)) <= .145); best = np.where(hit, np.minimum(best, np.abs((D*p['normal'][jj]).sum(1))), best)
    return best <= tau

def main(stem):
    site, prior = stem.split('__'); r = loadz(GT/'scenes'/stem/'rows.npz', ['xyz', 'row_tau_m', 'wall']); X = r['xyz'].astype('f8'); tau = r['row_tau_m']
    m = loadz(O/'meshes'/f'{stem}__gtt_target'/'points.npz', ['reference__within_tau1', 'reference__state']); ok = m['reference__within_tau1'].astype(bool); nos = m['reference__state'].astype(bool)
    cov = square_cover(site, X, tau)
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); pid = A['reference__point_id']; jm = np.zeros(len(X), bool); jm[pid] = A['reference__judgment_mesh__within_tau1'].astype(bool)
    st = np.where(ok, 0, np.where(nos, 2, 1)).astype('i1')
    savez(O/'checks'/f'fail_points_{stem}.npz', xyz=X.astype('f4'), state=st, square_covers=cov, wall=r['wall'], method_target_mesh_within=jm, tau=tau)
    rows = []
    for nm, sel in [('all', np.ones(len(X), bool)), ('wall', r['wall'].astype(bool)), ('roof', ~r['wall'].astype(bool))]:
        n = int(sel.sum())
        if not n: continue
        rows.append(dict(stem=stem, title=TITLE, rows=nm, n=n, target_mesh_within_pct=100*ok[sel].mean(), outside_tau_pct=100*(st[sel] == 1).mean(), no_surface_pct=100*(st[sel] == 2).mean(),
            patch_square_within_pct=100*cov[sel].mean(), missed_but_square_covers_pct=100*(~ok[sel] & cov[sel]).mean(), missed_and_no_square_pct=100*(~ok[sel] & ~cov[sel]).mean(),
            method_target_mesh_within_pct=100*jm[sel].mean()))
    table(f'stage1/fail_{stem}', rows); print('FAIL', json.dumps(rows))

def figure():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    allrows = []
    for stem in STEMS:
        p = O/'checks'/f'fail_points_{stem}.npz'
        if not p.exists(): continue
        z = loadz(p); fig, ax = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True); X = z['xyz']
        for a, sel, ttl in [(ax[0], ~z['wall'].astype(bool), '지붕 행'), (ax[1], z['wall'].astype(bool), '벽 행')]:
            a.scatter(X[sel, 0], X[sel, 1], s=.2, c='#cccccc', rasterized=True)
            for k, col, lab in [(1, '#fdae61', '면은 있으나 τ 밖'), (2, '#d7191c', '면 없음')]:
                m = sel & (z['state'] == k); a.scatter(X[m, 0], X[m, 1], s=1.5, c=col, label=f'{lab} {int(m.sum()):,}', rasterized=True)
            m = sel & (z['state'] > 0) & ~z['square_covers']; a.scatter(X[m, 0], X[m, 1], s=3, c='k', marker='x', label=f'조각 정사각형도 못 덮음 {int(m.sum()):,}', rasterized=True)
            a.set_aspect('equal'); a.set_title(ttl); a.legend(loc='upper right', markerscale=6, fontsize=9); a.set_xlabel('x (m)'); a.set_ylabel('y (m)')
        fig.suptitle(f'{TITLE} · {stem} · 목표 메시가 놓친 참값 행(위에서 본 그림)', fontsize=13)
        out = D/'figures'/f'stage1_fail_{stem}.png'; fig.savefig(out, dpi=100); plt.close(fig); print('FIG', out)

if __name__ == '__main__':
    figure() if sys.argv[1] == 'figure' else main(sys.argv[1])
