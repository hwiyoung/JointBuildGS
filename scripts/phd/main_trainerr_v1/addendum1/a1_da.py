"""Addendum 1 work 다 (order 5): R1 floor strip, bound Gaussians below the floating surface. CPU container (the refsim render is a separate GPU job).
Uses v1 checks/views/render (v1 visibility) and the check-6 refsim render (render/R1rep_b10__ALS__<arm>__refsim.npz)."""
from a1_common import *
STEM = 'R1rep_b10__ALS'
def main():
    c = acfg(); t = Timer('a1_da'); rows = []; tabs = {'order': [], 'refsim': []}; site = 'R1rep_b10'
    views = train_views(site); Es = np.array([v['W2C'] for v in views]); Ks = np.array([v['K'] for v in views])
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    pts_out = {}
    for arm in ARMS:
        z = loadz(O/'checks'/f'{STEM}__{arm}.npz'); m = z['cell'] == 2; X = z['xyz']; Nn = z['normal']; tau = z['tau']; prow = z['patch_row']
        snap = loadz(arm_paths(STEM, arm)['model']/'target_monitor/snapshot_30000.npz', ['xyz', 'opacity', 'target_tag', 'target_index', 'patch_ids'])
        bt = np.flatnonzero(snap['target_tag'] == 1); bp = snap['patch_ids'][snap['target_index'][bt]]; o = np.argsort(bp, kind='stable'); bps, bts = bp[o], bt[o]
        lo = np.searchsorted(bps, prow, 'left'); hi = np.searchsorted(bps, prow, 'right'); n = len(X)
        remain = np.zeros(n, bool); omax = np.full(n, np.nan); members = {}
        for i in np.flatnonzero(m & (prow >= 0) & (hi > lo)):
            g = bts[lo[i]:hi[i]]; near = g[np.abs((snap['xyz'][g]-X[i])@Nn[i]) <= tau[i]]
            if len(near): remain[i] = True; omax[i] = float(snap['opacity'][near].max()); members[i] = near
        # order: per seen v1 view, is the drawer closer to the camera than the nearest remaining bound Gaussian?
        V = loadz(O/'views'/f'{STEM}__{arm}.npz', ['point', 'view']); Rr = loadz(O/'render'/f'{STEM}__{arm}.npz', ['drawer'])
        closer = np.zeros(n); judged = np.zeros(n); self_draw = np.zeros(n)
        sel = np.flatnonzero(np.isin(V['point'], list(members)) & (Rr['drawer'] >= 0))
        for q in sel:
            i = V['point'][q]; j = V['view'][q]; E = Es[j]; dr = Rr['drawer'][q]; mem = members[i]
            if dr in set(mem.tolist()): self_draw[i] += 1; judged[i] += 1; continue
            zb = (snap['xyz'][mem]@E[:3, :3].T+E[:3, 3])[:, 2].min(); zd = (snap['xyz'][dr]@E[:3, :3].T+E[:3, 3])[2]
            judged[i] += 1; closer[i] += zd < zb
        share = np.where(judged > 0, closer/np.maximum(judged, 1), np.nan)
        for setname, s in [('lost', m & (z['set'] == 0)), ('control', m & (z['set'] == 1))]:
            ob = np.where(~remain[s], '없음', np.where(omax[s] < .1, '<0.1', np.where(omax[s] < .5, '0.1-0.5', '>=0.5')))
            r = dict(arm=arm, set=setname, n=int(s.sum()), remain_pct=100*float(remain[s].mean()), none_pct=100*float((~remain[s]).mean()))
            for k in ['<0.1', '0.1-0.5', '>=0.5']: r[f'remain_opacity_{k}_pct_of_set'] = 100*float((ob == k).mean())
            ss = share[s & remain]; r.update(order_points=int(np.isfinite(ss).sum()), drawer_closer_share_median=float(np.nanmedian(ss)) if np.isfinite(ss).any() else None,
                                              drawer_closer_share_mean=float(np.nanmean(ss)) if np.isfinite(ss).any() else None, drawn_by_remaining_bound_views=int(self_draw[s].sum()), judged_views=int(judged[s].sum()))
            rows.append(r)
        # refsim render classes for lost-point seen views (v1 rule)
        rf = A1O/'render'/f'{STEM}__{arm}__refsim.npz'
        if rf.exists():
            RS_ = loadz(rf, ['rdepth', 'ralpha']); Vv = loadz(O/'views'/f'{STEM}__{arm}.npz', ['point', 'view', 'u', 'v']); L = np.flatnonzero(m & (z['set'] == 0)); pm = np.isin(Vv['point'], L)
            K = Ks[Vv['view'][pm]]; E = Es[Vv['view'][pm]]; D_ = RS_['rdepth'][pm].astype(float); xc = np.c_[(Vv['u'][pm]-K[:, 0, 2])/K[:, 0, 0]*D_, (Vv['v'][pm]-K[:, 1, 2])/K[:, 1, 1]*D_, D_]
            Xw = np.einsum('nji,nj->ni', E[:, :3, :3], xc-E[:, :3, 3]); p_ = Vv['point'][pm]; dv = np.einsum('ij,ij->i', Nn[p_], Xw-X[p_])
            empty = ~(RS_['ralpha'][pm] >= .5) | ~np.isfinite(D_) | (D_ <= 0); floor = ~empty & (np.abs(dv) <= tau[p_]); other = ~empty & ~floor
            tabs['refsim'].append(dict(arm=arm, lost_points=len(L), pairs=int(pm.sum()), floor_pct=100*float(floor.mean()), other_surface_pct=100*float(other.mean()), empty_pct=100*float(empty.mean()),
                                       render=str(rf), model=f'sim/{STEM}__refsim_{arm}_bg/point_cloud.ply'))
        else: tabs['refsim'].append(dict(arm=arm, status='확인 불가', why='refsim render not found'))
        pts_out[arm] = dict(xyz=X[m], set=z['set'][m], remain=remain[m], remain_opacity_max=omax[m].astype('f4'), drawer_closer_share=share[m].astype('f4'), point_id=z['point_id'][m])
        L = m & (z['set'] == 0); fig, ax = plt.subplots(figsize=(8, 7)); ax.scatter(X[m & (z['set'] == 1), 0], X[m & (z['set'] == 1), 1], s=.3, c='#dddddd', lw=0)
        for lab, s_, col in [('묶인 것이 남음', L & remain, '#2ca02c'), ('없음', L & ~remain, '#d62728')]: ax.scatter(X[s_, 0], X[s_, 1], s=2, c=col, lw=0, label=lab)
        ax.set_aspect('equal'); ax.legend(markerscale=4, fontsize=8); ax.set_title(f'② R1 × 항공 LiDAR · {"본 방법 판정" if arm == "own" else "정답 판정"}', fontsize=9)
        (A1D/'figures').mkdir(parents=True, exist_ok=True); fig.savefig(A1D/'figures'/f'da_map_{arm}.png', dpi=180, bbox_inches='tight'); plt.close(fig)
        dump(A1D/'figures'/f'da_map_{arm}.json', dict(arm=arm, source=f'checks/{STEM}__{arm}.npz + snapshot_30000', scientific_verdict=None))
    atable('da_remaining_bound', rows); atable('da_refsim_render', tabs['refsim'])
    for arm, d in pts_out.items(): savez(A1O/'points'/f'da_{arm}.npz', **d)
    aprogress(f'일 다 계산 ({t.done():.0f} s)'); print('DA', rows, tabs['refsim'], flush=True)
if __name__ == '__main__': main()
