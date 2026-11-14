"""Work ma (order 6): lost points of R1rep_b10__LoD2 and B173nb_b10__LoD2 (own arm) clustered in 3D (addendum4.json work_ma). CPU.
  lost <stem>   : addendum2 group rule on every eligible GT point (judgment mesh within tau and FINALTRAIN 30000 not) -> clusters (link 0.5 m)
                  -> per cluster values -> addendum4/ma/<stem>.npz, tables/ma_clusters_<stem>.csv, figures/ma_map_<stem>.png"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
import time
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
MA = A4O/'ma'
JUDGE = {0: '일치', 1: '보존', 2: '보정', 3: '빈 공간 보정', 4: '결측', 9: '셀 수 없음', -1: '패치 없음'}

def patch_pixels(stem, nrows):
    """per target row: target pixels, front pixels (image depth < target - 1 m, addendum2 class), median (target - image depth) of front pixels."""
    site = stem.split('__')[0]; md = maps_dir(stem, 'own'); idx = json.loads((md/'index.json').read_text())['views']; S0d = Path('/s0/fork_inputs/s61')/site/'maps'
    tot = np.zeros(nrows, 'i8'); fr = np.zeros(nrows, 'i8'); diffs_o, diffs_v = [], []
    for nm, m in sorted(idx.items()):
        with np.load(md/m['file']) as z: own = z['owner']; dep = z['depth']
        mvs = np.load(S0d/'mvs'/f'{nm}.npy'); k = own >= 0; o = own[k]; td = dep[k].astype('f8'); mv = mvs[k].astype('f8')
        tot += np.bincount(o, minlength=nrows); f = np.isfinite(mv) & (mv > 0) & (mv < td-1); fr += np.bincount(o[f], minlength=nrows)
        diffs_o.append(o[f].astype('i4')); diffs_v.append((td-mv)[f].astype('f4'))
    o = np.concatenate(diffs_o); v = np.concatenate(diffs_v); od = np.argsort(o, kind='stable'); o, v = o[od], v[od]; st = np.searchsorted(o, np.arange(nrows+1))
    return tot, fr, o, v, st

def lost(stem):
    t0 = time.monotonic(); c = acfg()['work_ma']; MA.mkdir(parents=True, exist_ok=True); site, prior = stem.split('__')
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool)
    tw = A['reference__judgment_mesh__within_tau1'].astype(bool); rw = A['reference__FINALTRAIN_30000__within_tau1'].astype(bool); w2 = A['reference__2DGS_30000__within_tau1'].astype(bool)
    L = np.flatnonzero(el & tw & ~rw); K = np.flatnonzero(el & tw & rw)
    X = A['reference__xyz'][L].astype('f8'); pid = A['reference__point_id'][L]; wall = A['reference__wall'][L].astype(bool); case = A['reference__case_id'][L]
    tree = cKDTree(X); pairs = tree.query_pairs(c['cluster_link_m'], output_type='ndarray')
    G = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(X), len(X))); nc, lab = connected_components(G, directed=False)
    t = loadz(targets_of(stem, 'own'), ['target', 'normal', 'sigma', 'region', 'judge_region', 'area']); N = len(t['area']); vp = np.flatnonzero(valid_patch(t)); vidx = np.full(N, -1); vidx[vp] = np.arange(len(vp))
    praw = gt_row_patch(stem)[pid]; judge = np.where(praw >= 0, t['judge_region'][np.clip(praw, 0, None)], -1)
    snap = loadz(model_dir(stem, 'own')/'target_monitor/snapshot_30000.npz', ['xyz', 'target_tag', 'target_index', 'opacity'])
    gtree = cKDTree(snap['xyz'].astype('f8')); dg, _ = gtree.query(X, distance_upper_bound=.2); no_g = ~np.isfinite(dg)
    bound_rows = np.zeros(N, bool); bi = snap['target_index'][snap['target_tag'] == 1]; bound_rows[vp[bi]] = True
    no_bound = ~np.where(praw >= 0, bound_rows[np.clip(praw, 0, None)], False)
    tot, fr, fo, fv, st = patch_pixels(stem, N)
    rows = []; order = np.argsort(-np.bincount(lab)); keep = [k for k in order if np.sum(lab == k) > 0]
    gp = A['reference__xyz'][el].astype('f8'); gl = np.zeros(len(gp), bool)
    for rank, k in enumerate(keep):
        m = lab == k; n = int(m.sum())
        if rank >= 50 and n < 20: break
        vox = np.unique(np.floor(X[m]/.25).astype('i8'), axis=0); pr = np.unique(praw[m][praw[m] >= 0])
        tp = int(tot[pr].sum()); fp_ = int(fr[pr].sum()); dv = np.concatenate([fv[st[q]:st[q+1]] for q in pr]) if len(pr) else np.zeros(0)
        jv, jc = np.unique(judge[m], return_counts=True); ctr = X[m].mean(0)
        # 2DGS completeness at the place: share of the cluster's lost points that the photo-only 2DGS has within tau
        rows.append(dict(stem=stem, rank=rank+1, cluster=int(k), points=n, area_m2=len(vox)*.0625, centre_x=float(ctr[0]), centre_y=float(ctr[1]), centre_z=float(ctr[2]),
                         wall_pct=pct(wall[m]), surface='벽' if wall[m].mean() >= .5 else ('바닥(지면)' if ctr[2] < np.quantile(gp[:, 2], .01)+1.5 else '지붕'),
                         judgment=' / '.join(f'{JUDGE.get(int(a), int(a))} {int(b)}' for a, b in sorted(zip(jv, jc), key=lambda x: -x[1])),
                         case=' / '.join(f'{int(a)}:{int(b)}' for a, b in zip(*np.unique(case[m], return_counts=True))),
                         no_gaussian_02m_pct=pct(no_g[m]), no_bound_gaussian_pct=pct(no_bound[m]), target_pixels=tp, image_front_pixel_pct=100*fp_/max(1, tp), front_diff_median_m=med(dv),
                         photo_only_2dgs_completeness_pct=pct(w2[L][m])))
    lab_out = np.full(len(X), -1); rank_of = {r['cluster']: r['rank'] for r in rows}
    for k, r in rank_of.items(): lab_out[lab == k] = r
    savez(MA/f'{stem}.npz', point_id=pid, xyz=X.astype('f4'), cluster_rank=lab_out, wall=wall, judge=judge, no_gaussian_02m=no_g, no_bound=no_bound, kept_xyz=A['reference__xyz'][K].astype('f4'))
    dtable(f'ma_clusters_{stem}', rows)
    dump(MA/f'{stem}.json', dict(at=now(), stem=stem, eligible=int(el.sum()), lost=len(L), kept=len(K), clusters=int(nc), link_m=c['cluster_link_m'], seconds=time.monotonic()-t0,
                                surface_rule='wall share >= 50 % -> wall; else ground when the centre z < 1st percentile of eligible GT z + 1.5 m; else roof (GT has only the wall flag)', rule='lost = eligible, judgment mesh within tau1 and FINALTRAIN_30000 not (addendum2 group rule) on all eligible points; clusters = connected components of lost points within the link distance', scientific_verdict=None))
    print('MA', stem, len(L), nc, rows[:5], flush=True); fig_map(stem, rows)

def fig_map(stem, rows):
    plt = korean_plt(); z = loadz(MA/f'{stem}.npz'); fig, ax = plt.subplots(figsize=(11, 10))
    k = z['kept_xyz']; s = np.random.default_rng(0).choice(len(k), min(len(k), 200000), replace=False)
    ax.scatter(k[s, 0], k[s, 1], s=.2, c='#cccccc', lw=0, rasterized=True, label='지킨 점(참고)')
    x = z['xyz']; ax.scatter(x[:, 0], x[:, 1], s=.6, c='#1f5fd6', lw=0, rasterized=True, label=f'잃은 점 {len(x):,}')
    for r in rows[:5]:
        m = z['cluster_rank'] == r['rank']; ax.scatter(x[m, 0], x[m, 1], s=1.2, c='#d62728', lw=0, rasterized=True)
        ax.annotate(f"{r['rank']}", (r['centre_x'], r['centre_y']), fontsize=16, color='k', weight='bold', ha='center', va='center',
                    bbox=dict(boxstyle='circle', fc='white', ec='#d62728'))
    ax.set_aspect('equal'); ax.set_xlabel('동쪽 (m, 학습 좌표)'); ax.set_ylabel('북쪽 (m)'); ax.legend(loc='upper right', markerscale=10)
    ax.set_title(f'{stem.replace("__", " × ").replace("ALS", "항공 LiDAR")}: 잃은 점(판단 메시는 맞고 학습 결과는 틀린 참값 점)과 큰 덩어리 다섯(빨강, 번호 = 점 수 순위)', fontsize=10)
    fig.tight_layout(); (A4D/'figures').mkdir(parents=True, exist_ok=True); fig.savefig(A4D/'figures'/f'ma_map_{stem}.png', dpi=110)
    dump(A4D/'figures'/f'ma_map_{stem}.json', dict(at=now(), source=str(MA/f'{stem}.npz'), table=f'tables/ma_clusters_{stem}.csv', scientific_verdict=None))

if __name__ == '__main__':
    lost(sys.argv[2]) if sys.argv[1] == 'lost' else None
