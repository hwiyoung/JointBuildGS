"""그림 5 (고리가 경계에 걸친 자리), 6 (네 경우 밖 사진 모음), 7 (사진 조각). 실제 영상(원본 JPEG, WIDEN0 학습 카메라) 위에 칠한다. 원인을 적을 자리는 비운다.
비스듬한 학습 영상: 모임 중심을 보는 영상 가운데 시선이 연직에서 35~65 도, MVS 깊이로 가려지지 않고(0.5 m), 투영된 점이 가장 많은 것(같으면 가까운 것)."""
from common import *
import pandas as pd, cv2, zipfile
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import jc2_judge as J
from s10_maps import ortho, background, paint, NINE_C, NINE_N, patch_arrays
sys.path.insert(0, str(HERE/'inherited'))
from photo_cameras import Cameras
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 7})
FIG = D/'figures'; CAM = {}
def cam():
    if 'c' not in CAM: CAM['c'] = Cameras(); CAM['z'] = zipfile.ZipFile(PH.parent/'p0-audit/data/raw/uav/Images.zip')
    return CAM['c']
def rgb_full(j):
    c = cam(); im = cv2.imdecode(np.frombuffer(CAM['z'].read(c.members[j]), np.uint8), cv2.IMREAD_COLOR); return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
def oblique_view(X):
    c = cam(); up = np.array([0, 0, 1.]); ctr = X.mean(0); best = None
    for j in range(len(c.names)):
        v = c.centres[j] - ctr; ang = np.degrees(np.arccos(np.clip(v @ up/np.linalg.norm(v), -1, 1)))
        if not (35 <= ang <= 65): continue
        q = X @ c.M[j, :3, :3].T + c.M[j, :3, 3]; z = q[:, 2]; uv = q[:, :2]/z[:, None]*[c.K[0, 0], c.K[1, 1]] + [c.K[0, 2], c.K[1, 2]]
        ins = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < 1024) & (uv[:, 1] >= 0) & (uv[:, 1] < 741)
        if ins.sum() < max(3, .5*len(X)): continue
        dep = c.depth(j)
        if dep is None: continue
        px = np.clip(np.rint(uv[ins]).astype(int), [0, 0], [1023, 740]); dd = dep[px[:, 1], px[:, 0]]; vis = np.isfinite(dd) & (dd > 0) & (z[ins] <= dd + .5)
        score = (int(vis.sum()), -float(np.linalg.norm(v)))
        if best is None or score > best[0]: best = (score, j)
    return None if best is None else best[1]
def draw_on_view(ax, j, X, colours, pad=60):
    c = cam(); uv, _, ok = c.project(X, j); ok &= (uv[:, 0] >= 0) & (uv[:, 0] < c.w) & (uv[:, 1] >= 0) & (uv[:, 1] < c.h)
    if not ok.any(): ax.text(.5, .5, '투영 없음', ha='center', transform=ax.transAxes); ax.axis('off'); return None
    x0, y0 = np.maximum(0, uv[ok].min(0) - pad).astype(int); x1, y1 = np.minimum([c.w, c.h], uv[ok].max(0) + pad).astype(int); im = rgb_full(j)
    ax.imshow(im[y0:y1, x0:x1], extent=[x0, x1, y1, y0]); ax.scatter(uv[ok, 0], uv[ok, 1], c=np.asarray(colours)[ok], s=1.2, lw=0, alpha=.8); ax.set_xticks([]); ax.set_yticks([])
    return [int(x0), int(y0), int(x1), int(y1)]
def mvs_points_near(tile, lo, hi):
    X = np.load(WI/'points'/tile/'mvs_a_xyz.npy', mmap_mode='r'); out = []
    for b in range(0, len(X), 20_000_000):
        q = np.asarray(X[b:b + 20_000_000], dtype=np.float64); m = (q >= lo).all(1) & (q <= hi).all(1)
        if m.any(): out.append(q[m])
    return np.concatenate(out) if out else np.zeros((0, 3))
def slice_mesh(V, F, p0, nrm, lo, hi):
    s = (V - p0) @ nrm; sv = s[F]; cross = (np.sign(sv).min(1) < 0) & (np.sign(sv).max(1) > 0); segs = []
    for f, ss in zip(F[cross], sv[cross]):
        pts = []
        for a, b in [(0, 1), (1, 2), (2, 0)]:
            if ss[a]*ss[b] < 0: t = ss[a]/(ss[a] - ss[b]); pts.append(V[f[a]] + t*(V[f[b]] - V[f[a]]))
        if len(pts) == 2 and ((np.array(pts) >= lo - .5).all() and (np.array(pts) <= hi + .5).all()): segs.append(pts)
    return np.array(segs)
FTMESH = {'B0_b10': 'addendum3_stage2', 'B173nb_b10': 'addendum3_stage1', 'R1rep_b10': 'addendum3_stage2'}
def fig6gt():
    """그림 6 덧붙임(사용자 결정 11/13): 참값 점 모임만 놓고 같은 규칙(넓이 큰 20개, 한 건물 둘까지). 유형마다 하나 더함은 없음. 규칙 판(fig6_outside_clusters_*)은 그대로 둠."""
    fig6(only_gt=True)
def fig6(only_gt=False):
    C = pd.read_csv(O/'analysis/clusters.csv'); O_ = ortho()
    stem = 'fig6_gt_clusters' if only_gt else 'fig6_outside_clusters'
    rule = '20 largest truth-point clusters (<=2 per building), added by user decision 2026-11-13' if only_gt else '20 largest clusters (<=2 per building) + largest remaining per geometry type'
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/'analysis'/f'gt_{prior}.npz'); P = patch_arrays(prior); look = {}; tiles_ = []
        for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            z = loadz(p, ['patch_id']); t = p.stem.split('__')[0]
            for i, s in enumerate(z['patch_id']): look[s] = len(look)
        mi = J.VARIANTS.index('method'); TH = np.concatenate([loadz(O/'judge/base'/p.name, ['target_h'])['target_h'][mi] for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz'))])
        ptile = np.concatenate([np.full(len(loadz(p, ['kind'])['kind']), p.stem.split('__')[0]) for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz'))])
        c = C[(C.prior == prior) & (C['size'] == '1 m2 이상')].sort_values('area_m2', ascending=False); chosen = []; perb = {}
        if only_gt: c = c[c.cluster_source == '참값 점']
        for _, r in c.iterrows():
            if len(chosen) >= 20: break
            if perb.get(r.building, 0) >= 2: continue
            chosen.append(int(r.cluster_id)); perb[r.building] = perb.get(r.building, 0) + 1
        for tname in ([] if only_gt else sorted(set(c['geometry_type'].dropna()))):
            x = c[(c.geometry_type == tname) & ~c.cluster_id.isin(chosen)]
            if len(x): chosen.append(int(x.iloc[0].cluster_id))
        meta = []; pages = [chosen[i:i+6] for i in range(0, len(chosen), 6)]
        for pg, ids in enumerate(pages):
            fig, axs = plt.subplots(len(ids), 3, figsize=(11, 3.3*len(ids)), squeeze=False)
            for r, cid in enumerate(ids):
                row = C[C.cluster_id == cid].iloc[0]
                if row.cluster_source == '참값 점': mem = np.array([int(x) for x in str(row.member_rows).split(',') if x != '']); X = d['xyz'][mem]; col = [NINE_C[int(k)] for k in d['nine'][mem]]
                else:
                    pids = str(row.member_patches).split(','); pix = np.array([look[s] for s in pids if s in look]); X = P['centre'][pix] + np.nan_to_num(P['prior_height_m'][pix])[:, None]*np.nan_to_num(P['normal'][pix]); col = ['#ffe600']*len(X)
                lo = X.min(0) - 2; hi = X.max(0) + 2; ext = [lo[0], hi[0], lo[1], hi[1]]
                ax = axs[r, 0]; background(ax, ext, O_); inside = d['paired'] & (d['xyz'][:, 0] >= lo[0]) & (d['xyz'][:, 0] <= hi[0]) & (d['xyz'][:, 1] >= lo[1]) & (d['xyz'][:, 1] <= hi[1]) & (d['gt_kind'] != 2)
                paint(ax, d['xyz'][inside, :2], d['nine'][inside], dict(enumerate(NINE_C)), ext)
                if row.cluster_source != '참값 점': ax.scatter(X[:, 0], X[:, 1], s=1, c='#ffe600', lw=0)
                ax.set_title(f'({chr(44032 + 0)}) 모임 {cid} 아홉 조합', fontsize=7)
                j = oblique_view(X); ax = axs[r, 1]; crop = draw_on_view(ax, j, X, col) if j is not None else None
                if j is None: ax.text(.5, .5, '비스듬한 영상 없음', ha='center', transform=ax.transAxes); ax.axis('off')
                ax.set_title(f'(나) 비스듬한 학습 영상 {cam().names[j] if j is not None else "-"}', fontsize=7)
                # 단면
                ax = axs[r, 2]; ctr = X.mean(0); xy = X[:, :2] - ctr[:2]
                if row.gt_kind == '벽' and len(X) > 2:
                    u, s_, vt = np.linalg.svd(xy, full_matrices=False); dirn = np.r_[vt[1], 0]
                else:
                    u, s_, vt = (np.linalg.svd(xy, full_matrices=False) if len(X) > 2 else (None, None, np.array([[1, 0], [0, 1.]]))); dirn = np.r_[vt[0], 0]
                nrm = np.cross(dirn, [0, 0, 1.]); band = lambda Q: np.abs((Q - ctr) @ nrm) <= .25
                g = d['paired'] & (np.abs(d['xyz'][:, 0] - ctr[0]) < 30) & (np.abs(d['xyz'][:, 1] - ctr[1]) < 30); gb = np.flatnonzero(g)[band(d['xyz'][g])]
                ax.scatter((d['xyz'][gb] - ctr) @ dirn, d['xyz'][gb, 2], s=1, c='#777', lw=0, label='참값')
                pm = (np.abs(P['centre'][:, 0] - ctr[0]) < 30) & (np.abs(P['centre'][:, 1] - ctr[1]) < 30); pq = P['centre'] + np.nan_to_num(P['prior_height_m'])[:, None]*np.nan_to_num(P['normal']); pb = np.flatnonzero(pm)[band(pq[pm])]
                ax.scatter((pq[pb] - ctr) @ dirn, pq[pb, 2], s=1.5, c='#ff7f0e', lw=0, label='사전 정보')
                tq = P['centre'][pb] + TH[pb][:, None]*np.nan_to_num(P['normal'][pb]); okt = np.isfinite(TH[pb]); ax.scatter(((tq - ctr) @ dirn)[okt], tq[okt, 2], s=2, marker='x', c='k', lw=.4, label='목표')
                tl = ptile[pb[0]] if len(pb) else None
                if tl is not None:
                    M = mvs_points_near(tl, np.r_[ctr[:2] - 8, ctr[2] - 15], np.r_[ctr[:2] + 8, ctr[2] + 15]); M = M[band(M)]
                    if len(M) > 6000: M = M[np.random.default_rng(1).choice(len(M), 6000, replace=False)]
                    ax.scatter((M - ctr) @ dirn, M[:, 2], s=.4, c='#1f77b4', lw=0, alpha=.5, label='MVS')
                sites = set(d['site'][mem]) - {''} if row.cluster_source == '참값 점' else set()
                for site in sites:
                    mp = RS/FTMESH[site]/'meshes'/f'{site}__{prior}__FINALTRAIN_30000/primary.ply'
                    if mp.exists():
                        import open3d as o3d
                        m3 = o3d.io.read_triangle_mesh(str(mp)); seg = slice_mesh(np.asarray(m3.vertices), np.asarray(m3.triangles), ctr, nrm, lo, hi)
                        for sg in seg: ax.plot(((sg - ctr) @ dirn), sg[:, 2], c='#2ca02c', lw=.6)
                        ax.plot([], [], c='#2ca02c', lw=.6, label='학습 뒤 면')
                ax.set_xlim(((lo - ctr)[:2] @ dirn[:2]) - 2, ((hi - ctr)[:2] @ dirn[:2]) + 2) if False else None
                span = max(np.ptp((X - ctr) @ dirn), 2); ax.set_xlim(-span/2 - 3, span/2 + 3); ax.set_ylim(X[:, 2].min() - 6, X[:, 2].max() + 6); ax.set_aspect('equal', adjustable='datalim')
                ax.set_title('(다) 단면 ±0.25 m', fontsize=7); ax.legend(fontsize=5, loc='upper right', markerscale=4, frameon=False)
                txt = f"{row.geometry_type} · {str(row.building).replace('DEBY_LOD2_', '')} · {row.area_m2:.1f} m² · {row.gt_kind}"
                if row.cluster_source == '참값 점': txt += f"\n사전 정보 {row.prior_state} {row.s_P_median_m:+.2f} m · 영상 깊이 {row.image_state} {row.s_M_median_m:+.2f} m · 윤곽 밖 {row.outside_footprint_pct:.0f} %"
                else: txt += f"\n참값 없는 패치, 안쪽에 참값 있는 패치 {row.inner_truth_patches_pct:.0f} %"
                fm = lambda v, f: '-' if not np.isfinite(v) else format(v, f)
                txt += f"\n무늬 세기 {fm(row.texture_median, '.1f')} · 포화 {fm(row.saturated_pct, '.1f')} %"
                axs[r, 0].set_xlabel(txt + '   원인: ________', fontsize=6.5, loc='left')
                meta.append(dict(cluster_id=cid, page=pg, view=None if j is None else cam().names[j], crop=crop, section_direction=dirn.tolist(), section_band_m=.25, sites=sorted(sites)))
            fig.legend(handles=[Patch(color=cc, label=n) for cc, n in zip(NINE_C, NINE_N)], ncol=9, fontsize=6, loc='lower center', frameon=False)
            head = '네 경우 밖 참값 점 모임(덧붙임)' if only_gt else '네 경우 밖 모임'
            fig.suptitle(f'{prior}: {head} — 아홉 조합, 비스듬한 학습 영상, 단면 ({pg + 1}/{len(pages)})', fontsize=9); fig.tight_layout(rect=[0, .02, 1, .98])
            name = f'{stem}_{prior}_{pg + 1}'; fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig)
            dump(FIG/f'{name}.json', dict(prior=prior, clusters=[m for m in meta if m['page'] == pg], rule=rule, scientific_verdict=None))
        print('FIG6', stem, prior, len(chosen), flush=True)
def components(P, r):
    pairs = cKDTree(P).query_pairs(r, output_type='ndarray'); g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(P), len(P))); return connected_components(g, directed=False)
def fig5():
    import ring_kernel as K, s1_ring as SR
    for prior in ['LoD2', 'ALS']:
        A = []
        for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            g = loadz(p, ['patch_id', 'centre', 'normal', 'old_normal', 'roof_like', 'kind', 'building', 'n', 'mvs_mean_m', 'prior_height_m', 'tangent1', 'tangent2', 'area', 'raw_centre'])
            g['tile'] = np.full(len(g['kind']), p.stem.split('__')[0]); b = loadz(O/'geometry/base'/p.name, ['u_M', 'sigma_W']); g.update(b)
            gp = O/'truth/gt_patch'/p.name; g['gt_p'] = loadz(gp, ['gt_p'])['gt_p'] if gp.exists() else np.full(len(g['kind']), np.nan); g['place'] = loadz(O/'place'/p.name, ['place'])['place']
            pg = loadz(WI/'patch_geometry'/f"{p.stem.split('__')[0]}_{prior}.npz", ['patch_id']); pos = {s: i for i, s in enumerate(pg['patch_id'])}; g['widen0_index'] = np.array([pos[s] for s in g['patch_id']]); A.append(g)
        P = {k: np.concatenate([a[k] for a in A]) for k in A[0]}
        res = (P['mvs_mean_m'] - P['gt_p'])/np.sqrt(P['u_M']**2 + P['sigma_W']**2); big = np.flatnonzero((P['n'] >= 4) & np.isfinite(res) & (np.abs(res) > 3))
        cands = []
        for b in sorted(set(P['building'][big])):
            ix = big[P['building'][big] == b]
            if len(ix) < 2: continue
            k, lab = components(P['centre'][ix], .6)
            for c in range(k):
                m = ix[lab == c]; pl = np.bincount(np.maximum(P['place'][m], 0), minlength=3).argmax(); cands.append(dict(building=b, place=int(pl), area=float(P['area'][m].sum()), members=m))
        sel = []
        for pl, k in [(1, 2), (2, 2)]:
            sel += sorted([c for c in cands if c['place'] == pl], key=lambda c: -c['area'])[:k]
        fig, axs = plt.subplots(len(sel), 2, figsize=(9, 3.2*max(len(sel), 1)), squeeze=False); meta = []
        for r, c in enumerate(sel):
            m = c['members']; ctr = P['centre'][m].mean(0); i = int(m[np.argmin(np.linalg.norm(P['centre'][m] - ctr, axis=1))]); tile = P['tile'][i]
            n = P['old_normal'][i]; cc = P['centre'][i]; e1, e2 = (P['tangent1'][i], P['tangent2'][i]) if prior == 'LoD2' else (np.cross(n, [0, 1., 0]) / np.linalg.norm(np.cross(n, [0, 1., 0])), None)
            if e2 is None: e2 = np.cross(n, e1)
            SR.setup(tile, 'mvs_a'); K.G.update(radii=[1.5], pset=prior, c=P['centre'][[i]], n=P['old_normal'][[i]], roof=P['roof_like'][[i]], original_index=P['widen0_index'][[i]], data='mvs_a', site=tile)
            idx, t, rho, H = K.column(0); o, runs, M_ = K.C.find_face(t, H, K.D); inner = idx[np.abs(t - o) <= 1] if o is not None else idx[:0]
            ridx, L, lev, found = K.ring_points(0, o, 1.5, len(inner)) if o is not None else (idx[:0], None, 0, 0)
            X = K.G['X']; Q = X[inner]; R = X[ridx]
            rng = np.random.default_rng([K.U.CFG['seed'], K.U.SITE_ID[tile], K.U.SET_ID[prior], 0, 1, int(P['widen0_index'][i])]); pl = K.C.lmeds_plane(R - cc, n, rng, K.D) if len(R) >= 20 else None
            K.G.clear()
            ang = np.linspace(0, 2*np.pi, 100); circ = cc + 1.5*(np.cos(ang)[:, None]*e1 + np.sin(ang)[:, None]*e2); sq = cc + .125*np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]) @ np.stack([e1, e2])
            j = oblique_view(circ); ax = axs[r, 0]
            if j is not None:
                crop = draw_on_view(ax, j, np.r_[circ, sq], ['#ffe600']*len(circ) + ['#ff0000']*len(sq), pad=80)
            else: ax.axis('off'); crop = None
            ax.set_title(f"(가) {str(c['building']).replace('DEBY_LOD2_', '')} {['면 안쪽', '면 경계', '건물 가장자리'][c['place']]} · 패치(빨강)와 고리 1.5 m(노랑)", fontsize=7)
            ax = axs[r, 1]; s1 = (R - cc) @ e1; tr = (R - cc) @ n; s0 = (Q - cc) @ e1; ti = (Q - cc) @ n
            ax.scatter(s1, tr, s=.6, c='#1f77b4', lw=0, label='고리 점'); ax.scatter(s0, ti, s=.8, c='#ff7f0e', lw=0, label='안쪽 점')
            xs = np.linspace(-1.6, 1.6, 50)
            if pl is not None:
                pn = pl['normal']; pp = pl['point']; den = pn @ n; zz = ((pp @ pn) - (xs[:, None]*e1) @ pn)/den if abs(den) > 1e-9 else xs*np.nan; ax.plot(xs, zz, c='k', lw=.8, label='고리 평면')
            ax.axhline(np.nan_to_num(P['prior_height_m'][i]), c='#d62728', lw=.8, label='사전 정보'); ax.axhline(P['gt_p'][i], c='#2ca02c', lw=.8, ls='--', label='참값의 자리')
            ax.axhline(P['mvs_mean_m'][i], c='#9467bd', lw=.6, ls=':', label='MVS 높이')
            ax.set_xlabel('패치 접선 방향 거리 (m)'); ax.set_ylabel('법선 방향 (m)'); ax.legend(fontsize=5.5, frameon=False, markerscale=4); ax.set_ylim(np.nanmin([tr.min() if len(tr) else 0, P['gt_p'][i]]) - .3, np.nanmax([tr.max() if len(tr) else 0, P['gt_p'][i]]) + .3)
            ax.set_title(f"(나) 고리 점 단면 · u_M {P['u_M'][i]*100:.1f} cm · 잔차/정밀도 {res[i]:+.1f}", fontsize=7)
            meta.append(dict(building=c['building'], place=c['place'], area_m2=c['area'], patch_id=P['patch_id'][i], tile=tile, view=None if j is None else cam().names[j], crop=crop, ring_points=int(len(R)), inner_points=int(len(Q))))
        fig.suptitle(f'{prior}: 정밀도 잔차가 큰 면 경계·건물 가장자리 자리의 고리', fontsize=9); fig.tight_layout()
        fig.savefig(FIG/f'fig5_ring_boundary_{prior}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig)
        dump(FIG/f'fig5_ring_boundary_{prior}.json', dict(prior=prior, rule='|MVS 잔차/정밀도| > 3 인 패치를 0.6 m 로 이은 모임, 자리 다수(면 경계 둘, 건물 가장자리 둘), 넓이 큰 차례', items=meta, scientific_verdict=None))
        print('FIG5', prior, len(sel), flush=True)
def pieces(cc, e1, e2, j):
    c = cam(); uvg = np.stack(np.meshgrid(np.arange(25)*.02 - .24, np.arange(25)*.02 - .24, indexing='xy'), -1).reshape(625, 2)
    X = cc + uvg[:, :1]*e1 + uvg[:, 1:]*e2; uv, _, ok = c.project(X, j)
    if not ok.all(): return None
    g = c.gray_pyramid(j, [0])[0]; return cv2.remap(g, uv[:, 0].astype(np.float32).reshape(25, 25), uv[:, 1].astype(np.float32).reshape(25, 25), cv2.INTER_LINEAR)
def fig7():
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/'analysis'/f'gt_{prior}.npz', ['gid', 'paired', 'case', 'patch_majority_case']); A = []
        for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            t = p.stem.split('__')[0]; g = loadz(p, ['patch_id', 'centre', 'building', 'kind', 'area']); j = loadz(O/'judge/base'/p.name, ['photo_code', 'photo_point', 's_P', 's_M', 't', 'region'])
            tx = loadz(O/'texture'/p.name, ['textureless'])['textureless']; gb = loadz(O/'geometry/base'/p.name, ['geometry', 'u_M']); nn = loadz(p, ['n'])['n']
            # 확인 3과 같은 범위(11/15 고침): 한계 밖이거나 u_M 없는 패치(광도 결과가 판정에 쓰이는 곳)
            scope = (gb['geometry'] == 1) | ((nn >= 4) & (gb['geometry'] == 9) & ~np.isfinite(gb['u_M']))
            A.append(dict(g, photo_code=j['photo_code'], photo_point=j['photo_point'], s_P=j['s_P'], s_M=j['s_M'], t=j['t'], region=j['region'][J.VARIANTS.index('method')], textureless=tx, tile=np.full(len(tx), t), scope=scope))
        P = {k: np.concatenate([a[k] for a in A]) for k in A[0]}; N = len(P['kind']); P['photo_code'] = np.where(P['scope'], P['photo_code'], -1)
        maj = np.full(N, -1); has = d['paired']; cnt = np.zeros((N, 5)); np.add.at(cnt, (d['gid'][has], np.clip(d['case'][has], 0, 4)), 1); hm = cnt.sum(1) > 0; maj[hm] = cnt[hm].argmax(1)
        cats = [('틀린 지지', (P['photo_code'] == 0) & (maj == 1), 4), ('틀린 반박', (P['photo_code'] == 1) & (maj == 2), 4), ('무늬 없음 둘 다 높음', (P['photo_code'] == 3) & (P['textureless'] == 1), 2), ('영상 깊이 오류 둘 다 낮음', (P['photo_code'] == 2) & (maj == 2), 2)]
        items = []
        for name, mask, k in cats:
            ix = np.flatnonzero(mask); cc = []
            for b in sorted(set(P['building'][ix])):
                bi = ix[P['building'][ix] == b]
                if len(bi) == 1: cc.append((float(P['area'][bi].sum()), b, bi)); continue
                nk, lab = components(P['centre'][bi], .36)
                for c in range(nk): cc.append((float(P['area'][bi[lab == c]].sum()), b, bi[lab == c]))
            cc.sort(key=lambda x: -x[0]); perb = {}; got = 0
            for a, b, m in cc:
                if got >= k: break
                if perb.get(b, 0) >= 2: continue
                perb[b] = perb.get(b, 0) + 1; got += 1; ctr = P['centre'][m].mean(0); items.append((name, b, a, int(m[np.argmin(np.linalg.norm(P['centre'][m] - ctr, axis=1))])))
        fig, axs = plt.subplots(len(items), 1, figsize=(10, 1.9*max(len(items), 1)), squeeze=False); meta = []
        for r, (name, b, a, i) in enumerate(items):
            t = P['tile'][i]; q = loadz(O/'photo_prepared'/f'{t}.npz', ['prior', 'source_index', 'centres', 'tangent1', 'tangent2', 'selected_images']); m = np.flatnonzero((q['prior'] == prior) & (q['source_index'] == P['photo_point'][i]))
            ax = axs[r, 0]; ax.axis('off')
            if not len(m): ax.text(0, .5, f'{name}: 사진 점 없음', fontsize=7); continue
            k = int(m[0]); tiles_img = []; labels = []
            for plane in [0, 1]:
                for jv in q['selected_images'][k, plane][:5]:
                    if jv < 0: continue
                    pc = pieces(q['centres'][k, plane], q['tangent1'][k, plane], q['tangent2'][k, plane], int(jv))
                    if pc is not None: tiles_img.append(pc); labels.append(('사전' if plane == 0 else 'MVS') + f' {cam().names[int(jv)][-9:-4]}')
            for c, (im, lb) in enumerate(zip(tiles_img, labels)):
                ins = ax.inset_axes([c*.08, .15, .075, .8]); ins.imshow(im, cmap='gray', vmin=0, vmax=255); ins.set_xticks([]); ins.set_yticks([]); ins.set_title(lb, fontsize=4.5)
            bx = ax.inset_axes([.84, .2, .14, .7]); bx.barh([1, 0], [P['s_P'][i], P['s_M'][i]], color=['#ff7f0e', '#1f77b4']); bx.axvline(P['t'][i], c='k', lw=.8); bx.set_yticks([1, 0]); bx.set_yticklabels(['s_P', 's_M'], fontsize=6); bx.set_xlim(-.2, 1); bx.tick_params(labelsize=5); bx.set_title(f't = {P["t"][i]:.2f}', fontsize=5.5)
            ax.text(0, 0, f"{name} · {str(b).replace('DEBY_LOD2_', '')} · 경우(패치 다수) {['두 자료 모두 유효', '사전정보 오류', '영상 깊이 오류', '그 밖', '영상 깊이 결측'][maj[i]]} · 판정 {['일치', '사전정보 사용', '영상 깊이 사용', '제거', '결측'][P['region'][i]] if P['region'][i] < 5 else '미판정'} · 모임 {a:.1f} m²   까닭: ________", fontsize=6.5, transform=ax.transAxes)
            meta.append(dict(category=name, building=b, area_m2=a, patch_id=P['patch_id'][i], tile=t, s_P=float(P['s_P'][i]), s_M=float(P['s_M'][i]), t=float(P['t'][i]), views=labels))
        fig.suptitle(f'{prior}: 사진 조각 — 틀린 지지·틀린 반박·무늬 없음 둘 다 높음·영상 깊이 오류 둘 다 낮음', fontsize=9); fig.tight_layout()
        fig.savefig(FIG/f'fig7_photo_pieces_{prior}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig)
        dump(FIG/f'fig7_photo_pieces_{prior}.json', dict(prior=prior, rule='한계 밖·u_M 없는 패치(확인 3 범위)에서, 같은 범주·건물 0.36 m 로 이은 패치 넓이 큰 차례, 건물마다 둘까지; 경우 = 패치 다수결', items=meta, scientific_verdict=None))
        print('FIG7', prior, len(items), flush=True)
if __name__ == '__main__':
    for f in sys.argv[1:]: globals()[f]()
