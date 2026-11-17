"""그림 1~4 (발주 3.3, 4, 6절). 모든 셈이 끝난 뒤 한 번. 그림마다 json.
그림 2 의 비스듬한 영상 고르기와 영상 위 칠하기는 JC s10_images.oblique_view / draw_on_view 를 옮겨 씀(깊이 지도 읽기에 캐시만 더함)."""
from common import *
import pandas as pd, zipfile, cv2, collections
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from photo_cameras import Cameras
from obs import observations, OBS_KO, OBS_NO
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 7})
FIG = D/'figures'; TAB = D/'tables'; CC = {'한계 안 두 자료 모두 유효(기준 줄)': '#bbbbbb', '두 자료 모두 유효': '#2ca02c', '사전정보 오류': '#ff7f0e', '영상 깊이 오류': '#1f77b4'}
def save(fig, name, meta):
    FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))
def box(ax, x, r, c, w=.18):
    ax.add_patch(plt.Rectangle((x - w/2, r['q25']), w, r['q75'] - r['q25'], fc=c, ec='k', lw=.3)); ax.plot([x, x], [r['q10'], r['q25']], c='k', lw=.4); ax.plot([x, x], [r['q75'], r['q90']], c='k', lw=.4); ax.plot([x - w/2, x + w/2], [r['q50']]*2, c='k', lw=.8)
def fig1():
    Dd = pd.read_csv(TAB/'ga_distribution.csv'); A = pd.read_csv(TAB/'ga_auc.csv')
    for prior, unit in [('LoD2', 'LoD2_all'), ('ALS', 'ALS_roof')]:
        a = A[(A.unit == unit) & (A.version == '섞인 패치 뺌')].sort_values('rank'); obs = list(a.obs); nc = 6; nr = int(np.ceil(len(obs)/nc))
        fig, axs = plt.subplots(nr, nc, figsize=(12, 2.0*nr), squeeze=False)
        for i, k in enumerate(obs):
            ax = axs[i//nc, i % nc]; q = Dd[(Dd.unit == unit) & (Dd.version == '섞인 패치 뺌') & (Dd.obs == k)]
            for x, g in enumerate(CC):
                r = q[q.group == g]
                if len(r) and np.isfinite(r.iloc[0]['q50']): box(ax, x, r.iloc[0], CC[g])
            rr = a[a.obs == k].iloc[0]; ax.set_xlim(-.5, 3.5); ax.set_xticks([]); ax.autoscale(axis='y')
            ax.set_title(f"{OBS_NO[k]}. {OBS_KO[k]}\nAUC {rr.auc_imgerr_vs_priorerr:.2f} / {rr.auc_imgerr_vs_bothvalid:.2f}", fontsize=6.5)
        for j in range(len(obs), nr*nc): axs[j//nc, j % nc].axis('off')
        fig.legend(handles=[plt.Rectangle((0, 0), 1, 1, fc=c, ec='k', lw=.3) for c in CC.values()], labels=['한계 안 두 자료 모두 유효(기준)', '한계 밖 두 자료 모두 유효', '한계 밖 사전정보 오류', '한계 밖 영상 깊이 오류'], ncol=4, loc='lower center', frameon=False, fontsize=7)
        fig.suptitle(f'그림 1 ({prior}): 후보 관측의 경우별 분포 (상자 25–75 %, 선 10–90 %, 굵은 선 중앙값; 넓이 가중, 섞인 패치 뺌). AUC = 영상 깊이 오류 대 사전정보 오류 / 대 두 자료 모두 유효', fontsize=8)
        fig.tight_layout(rect=[0, .03, 1, .97]); save(fig, f'fig1_distributions_{prior}', dict(prior=prior, unit=unit, source='tables/ga_distribution.csv, ga_auc.csv', order='ranking key descending', obs=obs))
def fig3():
    S = pd.read_csv(TAB/'na_summary.csv'); V = ['본값 판', '판 가 (t_M)', '사전 정보 단독', '영상 단독', '패치 다수결 상한']; col = ['#444', '#d62728', '#ff7f0e', '#1f77b4', '#aaa']
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.2))
    for ax, (prior, sf) in zip(axs, [('LoD2', '모두'), ('ALS', '지붕')]):
        for vi, v in enumerate(V):
            q = S[(S.prior == prior) & (S.surface == sf) & (S.variant == v)]; ys = [q[q.case == CASE[c]].iloc[0]['target_ok_pct'] for c in [0, 1, 2, 4]]
            xs = np.arange(4) + (vi - 2)*.16; ax.bar(xs, ys, .15, color=col[vi], label=v)
            for x, y in zip(xs, ys): ax.text(x, y + 1, f'{y:.1f}', ha='center', fontsize=4.5, rotation=90)
        ax.set_xticks(range(4)); ax.set_xticklabels([CASE[c] for c in [0, 1, 2, 4]]); ax.set_ylim(0, 112); ax.set_ylabel('목표 맞음 %'); ax.set_title(prior)
    axs[0].legend(fontsize=6, ncol=5, loc='upper center', bbox_to_anchor=(1.05, -.1), frameon=False)
    fig.suptitle('그림 3: 경우별 목표 맞음 % — 본값 판과 판 가(s_M 을 t_M 과 비교)', fontsize=8); fig.tight_layout(); save(fig, 'fig3_tM_target_ok', dict(source='tables/na_summary.csv', variants=V))
def fig4():
    R = pd.read_csv(TAB/'ra_mde.csv'); fig, axs = plt.subplots(1, 3, figsize=(10, 3))
    for ax, u in zip(axs, UNITS):
        q = R[(R.unit == u) & (R.patches == '모든 패치')]
        for x, p in enumerate(['모든 자리'] + list(PLACE.values())):
            r = q[q.place == p].iloc[0]; box(ax, x, {k[4:]: r[k] for k in ['mde_q10', 'mde_q25', 'mde_q50', 'mde_q75', 'mde_q90']}, '#9ecae1', .4)
            ax.plot([x - .3, x + .3], [r.tau_q50]*2, c='#d62728', lw=1); ax.text(x, r.mde_q90, f"τ보다 큼\n{r.area_mde_gt_tau_pct:.0f} %", ha='center', va='bottom', fontsize=5.5)
        ax.set_xticks(range(4)); ax.set_xticklabels(['모든 자리'] + list(PLACE.values()), fontsize=6); ax.set_ylabel('최소 검출 오류 (m)'); ax.set_title(u)
    fig.suptitle('그림 4: 최소 검출 오류(5 %, 검정력 80 %)의 분포(상자 25–75 %, 선 10–90 %)와 τ(빨간 선 = 넓이 가중 중앙값)', fontsize=8); fig.tight_layout(); save(fig, 'fig4_mde', dict(source='tables/ra_mde.csv'))
# ---- 그림 2 ----
CAM = {}; DEP = collections.OrderedDict()
def cam():
    if 'c' not in CAM: CAM['c'] = Cameras(); CAM['z'] = zipfile.ZipFile(PH.parent/'p0-audit/data/raw/uav/Images.zip')
    return CAM['c']
def depth(j):
    if j not in DEP:
        DEP[j] = cam().depth(j)
        if len(DEP) > 200: DEP.popitem(last=False)
    return DEP[j]
def oblique_view(X):
    """JC s10_images.oblique_view 그대로(깊이 캐시만)."""
    c = cam(); up = np.array([0, 0, 1.]); ctr = X.mean(0); best = None
    for j in range(len(c.names)):
        v = c.centres[j] - ctr; ang = np.degrees(np.arccos(np.clip(v @ up/np.linalg.norm(v), -1, 1)))
        if not (35 <= ang <= 65): continue
        q = X @ c.M[j, :3, :3].T + c.M[j, :3, 3]; z = q[:, 2]; uv = q[:, :2]/z[:, None]*[c.K[0, 0], c.K[1, 1]] + [c.K[0, 2], c.K[1, 2]]
        ins = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < 1024) & (uv[:, 1] >= 0) & (uv[:, 1] < 741)
        if ins.sum() < max(3, .5*len(X)): continue
        dep = depth(j)
        if dep is None: continue
        px = np.clip(np.rint(uv[ins]).astype(int), [0, 0], [1023, 740]); dd = dep[px[:, 1], px[:, 0]]; vis = np.isfinite(dd) & (dd > 0) & (z[ins] <= dd + .5)
        score = (int(vis.sum()), -float(np.linalg.norm(v)))
        if best is None or score > best[0]: best = (score, j)
    return None if best is None else best[1]
def draw_on_view(ax, j, X, colour, pad=60):
    c = cam(); uv, _, ok = c.project(X, j); ok &= (uv[:, 0] >= 0) & (uv[:, 0] < c.w) & (uv[:, 1] >= 0) & (uv[:, 1] < c.h)
    if not ok.any(): ax.text(.5, .5, '투영 없음', ha='center', transform=ax.transAxes); ax.axis('off'); return None
    x0, y0 = np.maximum(0, uv[ok].min(0) - pad).astype(int); x1, y1 = np.minimum([c.w, c.h], uv[ok].max(0) + pad).astype(int)
    im = cv2.cvtColor(cv2.imdecode(np.frombuffer(CAM['z'].read(c.members[j]), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    ax.imshow(im[y0:y1, x0:x1], extent=[x0, x1, y1, y0]); ax.scatter(uv[ok, 0], uv[ok, 1], c=colour, s=1.5, lw=0, alpha=.8); ax.set_xticks([]); ax.set_yticks([])
    return [int(x0), int(y0), int(x1), int(y1)]
def mvs_near(tile, lo, hi):
    X = np.load(WI/'points'/tile/'mvs_a_xyz.npy', mmap_mode='r'); out = []
    for b in range(0, len(X), 20_000_000):
        q = np.asarray(X[b:b + 20_000_000], dtype=np.float64); m = (q >= lo).all(1) & (q <= hi).all(1)
        if m.any(): out.append(q[m])
    return np.concatenate(out) if out else np.zeros((0, 3))
def comps(P, building, idx):
    out = []
    for b in np.unique(building[idx]):
        ii = idx[building[idx] == b]; pr = cKDTree(P[ii]).query_pairs(.36, output_type='ndarray')
        n, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(ii), len(ii))), directed=False)
        for k in range(n): out.append((b, ii[lab == k]))
    return out
def fig2():
    A = pd.read_csv(TAB/'ga_auc.csv'); TH = pd.read_csv(TAB/'ga_thresholds.csv')
    for prior, unit in [('LoD2', 'LoD2_all'), ('ALS', 'ALS_roof')]:
        d = loadz(O/f'patch_{prior}.npz'); o = observations(d); ts = list(d['tiles'])
        Ph = loadz(O/f'photo_{prior}.npz', ['tile', 'row', 'centre_M', 'normal_M']); key_pp = Ph['tile'].astype(np.int64)*10**7 + Ph['row']; order = np.argsort(key_pp)
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz']); gtree = cKDTree(g['xyz'][:, :2])
        top = list(A[(A.unit == unit) & (A.version == '섞인 패치 뺌')].sort_values('rank').obs[:2])
        base = (d['geometry'] == 1) & (d['case'] == 2) & ~d['mixed']; X0 = d['centre'] + np.nan_to_num(d['prior_height_m'])[:, None]*np.nan_to_num(d['normal'])
        for k in top:
            lo = np.full(len(base), np.nan); hi = lo.copy()
            for u in [x for x in UNITS if UNITS[x][0] == prior]:
                um = d['kind'] == UNITS[u][1]; th = TH[(TH.unit == u) & (TH.obs == k)].set_index('region')
                for r in REGIONS + ['none']:
                    m = um & (d['region'] == r)
                    if m.any() and r in th.index: lo[m] = th.loc[r, 'lo5']; hi[m] = th.loc[r, 'hi95']
            x = o[k]; rej = (x < lo) | (x > hi); fin = np.isfinite(x)
            sets = {}
            for name, m in [('기각됨', base & fin & rej), ('기각 안 됨', base & fin & ~rej)]:
                cs = comps(d['centre'], d['building'], np.flatnonzero(m)); cs.sort(key=lambda c: -d['area'][c[1]].sum()); pick, perb = [], {}
                for b, ii in cs:
                    if len(pick) >= 6: break
                    if perb.get(b, 0) >= 2: continue
                    pick.append((b, ii)); perb[b] = perb.get(b, 0) + 1
                sets[name] = pick
            fig, axs = plt.subplots(6, 4, figsize=(12, 15), squeeze=False); meta = []
            for col, name in enumerate(sets):
                for r_ in range(6):
                    axA, axB = axs[r_, 2*col], axs[r_, 2*col + 1]
                    if r_ >= len(sets[name]): axA.axis('off'); axB.axis('off'); continue
                    b, ii = sets[name][r_]; P = X0[ii]; ctr_i = ii[np.argmin(np.linalg.norm(d['centre'][ii] - d['centre'][ii].mean(0), axis=1))]
                    j = oblique_view(P); crop = draw_on_view(axA, j, P, '#ffe600') if j is not None else None
                    if j is None: axA.text(.5, .5, '비스듬한 영상 없음', ha='center', transform=axA.transAxes); axA.axis('off')
                    axA.set_title(f"({name}) 가. {cam().names[j][-12:-4] if j is not None else '-'}", fontsize=6)
                    c0 = d['centre'][ctr_i]; n = d['normal'][ctr_i]; t1 = d['tangent1'][ctr_i]; t2 = np.cross(n, t1); t2 /= np.linalg.norm(t2)
                    sec = lambda Q: (np.abs((Q - c0) @ t2) <= .15) & (np.abs((Q - c0) @ t1) <= 3) & (np.abs((Q - c0) @ n) <= 3)
                    gi = gtree.query_ball_point(c0[:2], 4.5); G = g['xyz'][gi]; G = G[sec(G)]
                    M = mvs_near(ts[d['tile'][ctr_i]], c0 - 4.5, c0 + 4.5); M = M[sec(M)]
                    if len(M) > 5000: M = M[np.random.default_rng(1).choice(len(M), 5000, replace=False)]
                    axB.scatter((M - c0) @ t1, (M - c0) @ n, s=.5, c='#1f77b4', lw=0, alpha=.5, label='영상 깊이 점')
                    axB.scatter((G - c0) @ t1, (G - c0) @ n, s=.8, c='#333', lw=0, label='참값')
                    aa = np.linspace(-3, 3, 2); hp = np.nan_to_num(d['prior_height_m'][ctr_i]); axB.plot(aa, [hp, hp], c='#ff7f0e', lw=1, label='사전 정보')
                    if np.isfinite(d['mvs_mean_m'][ctr_i]): axB.plot([-.15, .15], [d['mvs_mean_m'][ctr_i]]*2, c='#d62728', lw=1.5, label='원통 평균 높이')
                    pr = d['pp_row'][ctr_i]
                    if pr >= 0:
                        kk = d['tile'][ctr_i].astype(np.int64)*10**7 + pr; p = order[np.searchsorted(key_pp[order], kk)]
                        cM, nM = Ph['centre_M'][p], Ph['normal_M'][p]
                        if np.isfinite(cM).all() and abs(n @ nM) > 1e-6:
                            bb = (((cM - c0) @ nM) - aa*(t1 @ nM))/(n @ nM); axB.plot(aa, bb, c='#1f77b4', lw=1, ls='--', label='영상 깊이 면')
                    axB.set_xlim(-3, 3); axB.set_ylim(-3, 3); axB.set_aspect('equal'); axB.tick_params(labelsize=5); axB.set_title('나. 단면 ±0.15 m (가로 t1, 세로 법선)', fontsize=6)
                    if r_ == 0 and col == 0: axB.legend(fontsize=4.5, loc='lower left', markerscale=3, frameon=False)
                    axA.set_xlabel(f"{b.replace('DEBY_LOD2_', '')} · {d['area'][ii].sum():.1f} m² · {OBS_KO[k]} {x[ctr_i]:.3g} · 기준 {lo[ctr_i]:.3g}–{hi[ctr_i]:.3g}", fontsize=5.5, loc='left')
                    meta.append(dict(set=name, building=b, patches=len(ii), area_m2=float(d['area'][ii].sum()), centre_patch=int(ctr_i), view=None if j is None else cam().names[j], crop=crop, value=float(x[ctr_i]), lo5=float(lo[ctr_i]), hi95=float(hi[ctr_i])))
            fig.suptitle(f'그림 2 ({prior}, {OBS_NO[k]}. {OBS_KO[k]}): 한계 밖 영상 깊이 오류 패치 — 왼쪽 기각된 자리 여섯, 오른쪽 기각되지 않은 자리 여섯', fontsize=8)
            fig.tight_layout(rect=[0, 0, 1, .98]); save(fig, f'fig2_sites_{prior}_{k}', dict(prior=prior, unit=unit, obs=k, rule='image-depth-error outside-limit patches excluding mixed; connected within 0.36 m per building; area descending; <= 2 per building', panels=meta))
            print('FIG2', prior, k, flush=True)
if __name__ == '__main__':
    cfg(); T = Timer(); fig1(); fig3(); fig4(); print('FIG134', round(T.s()), flush=True); fig2(); progress(f'그림 1~4 끝 ({round(T.s())} 초)')
