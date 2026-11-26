"""덧붙임 3 1절: u_M(영상 정밀도)이 빈 까닭(코드 조건 그대로)과 넓이, 몰리는 곳, 그림 fig_d7_uM_missing. 참값은 정답 경우 나누기에만. 판단 바꾸지 않음.
u_M 출처(코드, 커밋 a26e7219 exp/judgecheck-v2):
  JUDGEPROBE p1_build.py 18줄: u_M = JUDGECHECK-v2 geometry/base u_M
  main_judgecheck_v2/s2_calibrate.py 13줄: u = ring/base u_mvs_R1p5
  main_judgecheck_v2/s1_ring.py 56줄: 법선 있는 패치만 셈(ok = normal_defined & 법선 유한), 64줄: 중심이 WIDEN0 와 같으면 WIDEN0 u_mvs(상태 99), 아니면 ring_kernel.one_patch(38줄: 상태 0 일 때만 u)
  inherited/ring_kernel.py one_patch: 153줄 면 없음 -> 상태 1, 176줄 안쪽 원 점 < min_inner(5) 또는 고리 점 < min_ring(20) -> 상태 2, 182줄 LMedS 면 없음 -> 상태 3
  inherited/u_core.py find_face 40~50줄(기둥 점 0개, 또는 0.3 m 층에 20 % 이상 없음 -> 면 없음), lmeds_plane 106~109줄(법선 45° 안 후보 없음 -> None)
  WIDEN0 patch_values: 같은 커널(UNCERT-v1, 바이트 같음)의 mvs_a_status·als_status 와 점 수.
σ_P(항공 LiDAR) = s1_ring.py 71줄 WIDEN0 u_prior -> als_status.
사용: GT_STAGE=ga3 g23_uM_missing.py"""
from common import *
import pandas as pd
import g8_score as G8
from target_check import J4, T4
from scipy.spatial import cKDTree
from g11_figs import save as sv
import matplotlib.pyplot as plt
A3 = json.loads((C/'judgeeval_v1_add3.json').read_text()); assert sha(C/'judgeeval_v1_add3.json') == json.loads((C/'judgeeval_v1_add3.lock.json').read_text())['config_sha256'], 'add3 config changed after lock'
JC = PH/'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'; W0 = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'; TD = D/'tables/바'
COND = {-1: '셈 안 함: 법선 없음 (s1_ring.py 56줄)', 1: '면 못 찾음: 기둥 점 0개 또는 0.3 m 층에 20 % 이상 모인 층 없음 (u_core.find_face 40~50줄)',
        2: '점 부족: 안쪽 원(0.5 m) 점 < 5 또는 고리(0.5~1.5 m) 점 < 20 (ring_kernel.py 176줄)', 3: 'LMedS 면 없음: 법선 45° 안 후보 평면 없음 (u_core.lmeds_plane 106~109줄)',
        0: '상태 0 인데 값 없음', 9: '기록 없음'}
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def widen0(tile, prior):
    parts = []
    for root in [W0/'patch_values', W0/'holdout/patch_values']:
        p = root/f'{tile}__{prior}__R1.5.npz'
        if p.exists(): parts.append(loadz(p, ['patch_id', 'mvs_a_status', 'mvs_a_n_col', 'mvs_a_n_inner_all', 'mvs_a_ring_found', 'mvs_a_ring_level', 'u_mvs', 'mvs_a_u'] + (['als_status', 'u_prior'] if prior == 'ALS' else [])))
    return {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
def sources(prior, idx):
    """패치마다 u_M 상태·σ_P 상태와 점 수(WIDEN0 물려받은 패치만), JC 원래 법선·중심."""
    P = loadz(inp('patches', prior=prior), ['tile', 'local', 'tiles', 'u_M', 'sigma_P']); tiles = list(P['tiles']); N = len(idx)
    out = dict(st=np.full(N, 9, np.int8), inherited=np.zeros(N, bool), n_col=np.full(N, np.nan), n_inner=np.full(N, np.nan), ring_found=np.full(N, np.nan), ring_level=np.full(N, np.nan),
               sp_st=np.full(N, 9, np.int8), u_ring=np.full(N, np.nan), centre=np.full((N, 3), np.nan), onormal=np.full((N, 3), np.nan), tile=P['tile'][idx], w0_u_eq=0, w0_u_n=0)
    for ti in np.unique(P['tile'][idx]):
        r = np.flatnonzero(P['tile'][idx] == ti); loc = P['local'][idx][r]; t = tiles[ti]
        rb = loadz(JC/'ring/base'/f'{t}__{prior}.npz'); g = loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'centre', 'old_normal', 'widen0_same_centre'])
        assert np.array_equal(rb['patch_id'], g['patch_id']); st = rb['status_R1p5'][loc].astype(np.int8); out['u_ring'][r] = rb['u_mvs_R1p5'][loc]
        out['centre'][r] = g['centre'][loc]; out['onormal'][r] = g['old_normal'][loc]
        w = widen0(t, prior); pos = {s: i for i, s in enumerate(w['patch_id'])}; wi = np.array([pos.get(s, -1) for s in g['patch_id'][loc]]); has = wi >= 0
        inh = st == 99; assert (has | ~inh).all(), 'inherited patch missing in WIDEN0'
        st[inh] = w['mvs_a_status'][wi[inh]]; out['inherited'][r] = inh
        for k, kk in [('n_col', 'mvs_a_n_col'), ('n_inner', 'mvs_a_n_inner_all'), ('ring_found', 'mvs_a_ring_found'), ('ring_level', 'mvs_a_ring_level')]: out[k][r[inh]] = w[kk][wi[inh]]
        ok0 = inh & (w['mvs_a_status'][np.maximum(wi, 0)] == 0); out['w0_u_n'] += int(ok0.sum()); out['w0_u_eq'] += int(np.sum(np.isclose(w['u_mvs'][wi[ok0]], w['mvs_a_u'][wi[ok0]], rtol=1e-6)))
        out['st'][r] = st
        if prior == 'ALS': out['sp_st'][r] = np.where(has, w['als_status'][np.maximum(wi, 0)], 9)
    return out, P['u_M'][idx], P['sigma_P'][idx]
def edge_and_band(d, Pp, face):
    """면 가장자리까지 거리(설정 edge_distance)와 벽 높이 구간(0 아래, 1 가운데, 2 위)."""
    N = len(d.idx); dist = np.full(N, np.nan); band = np.full(N, -1, np.int8); cen = d.centre
    key = pd.Series(list(zip(d.building, face)))
    for _, g in pd.Series(np.arange(N)).groupby(key.values):
        ii = g.values; X = cen[ii]; tr = cKDTree(X); cnt = np.array([len(x) - 1 for x in tr.query_ball_point(X, .36)]); e = cnt < 8
        if e.any(): dist[ii] = cKDTree(X[e]).query(X)[0]
        if (d.kind[ii] == 2).all():
            z = X[:, 2]; lo, hi = z.min(), z.max(); f = (z - lo)/(hi - lo) if hi > lo else np.full(len(z), .5); band[ii] = np.minimum((f*3).astype(int), 2)
    return dist, band
def main():
    c = cfg(); T = Timer(); rows = []; rows_sp = []; rows_w = []; chk = dict(at=now(), scientific_verdict=None, add3_config_sha256=sha(C/'judgeeval_v1_add3.json')); save = {}
    for prior in PRIORS:
        d = G8.Data(prior, c); N = len(d.idx); S, uM, sP = sources(prior, d.idx); S1 = d.S1; assert np.allclose(S1['u_M'], uM, equal_nan=True)
        miss = ~np.isfinite(uM); st = S['st'].copy()
        chk[prior] = dict(patches=N, uM_missing=int(miss.sum()), uM_equals_ring=bool(np.allclose(uM, S['u_ring'], equal_nan=True)), missing_iff_status_nonzero=bool(np.array_equal(miss, st != 0)),
                          widen0_u_mvs_equals_mvs_a_u=f"{S['w0_u_eq']}/{S['w0_u_n']}", status_counts={int(k): int(v) for k, v in zip(*np.unique(st[miss], return_counts=True))})
        assert chk[prior]['uM_equals_ring'], 'u_M differs from ring/base'
        tm = np.array([T4.get(int(x), -1) for x in d.t]); n = S1['n'][:, 2]; Lf = np.isfinite(S1['L_m'])
        Pp = loadz(inp('patches', prior=prior), ['surf', 'face']); face = (Pp['surf'] if prior == 'LoD2' else Pp['face'])[d.idx]
        dist, band = edge_and_band(d, Pp, face)
        cases = [('모든 패치(10동)', np.ones(N, bool))] + [(f'정답 {nm}', tm == k) for k, nm in enumerate(J4)] + [('채점 밖', tm < 0)]
        for sn, sm in [('지붕', d.kind == 1), ('벽', d.kind == 2)]:
            if not sm.any(): continue
            for cn, cm in cases:
                m = sm & cm; mm = m & miss; r = dict(prior=PN[prior], surface=sn, case=cn, area_m2=d.area[m].sum(), patches=int(m.sum()), uM_missing_m2=d.area[mm].sum(), uM_missing_patches=int(mm.sum()),
                                                     uM_missing_pct=100*d.area[mm].sum()/d.area[m].sum() if d.area[m].sum() else np.nan, **{'그중 ① n≥4(값 없음 (ㄷ) 자리) m²': d.area[mm & (n >= 4)].sum()})
                tot = 0
                for k, nm in COND.items():
                    x = mm & (st == k); r[f'{nm} m²'] = d.area[x].sum(); r[f'{nm} 패치'] = int(x.sum()); tot += d.area[x].sum()
                assert np.isclose(tot, r['uM_missing_m2']); rows.append(r)
                if prior == 'ALS':
                    sm_ = m & ~np.isfinite(sP); q = dict(prior=PN[prior], surface=sn, case=cn, area_m2=d.area[m].sum(), sigmaP_missing_m2=d.area[sm_].sum(), sigmaP_missing_patches=int(sm_.sum()), both_missing_m2=d.area[sm_ & miss].sum())
                    t_ = 0
                    for k, nm in COND.items():
                        if k == -1: nm = '셈 안 함/기록 없음'
                        x = sm_ & (S['sp_st'] == k); q[f'{nm} m²'] = d.area[x].sum(); t_ += d.area[x].sum()
                    q['상태 0 아님 합'] = t_; rows_sp.append(q)
            # 상태 2·1 속 나눔(WIDEN0 에서 물려받은 패치만 점 수가 있음)
            for (ccn, ccm), k in [(cc, kk) for cc in [('모든 패치', np.ones(N, bool)), ('정답 영상', tm == 1), ('정답 영상·① n≥4', (tm == 1) & (n >= 4))] for kk in [1, 2]]:
                x = sm & miss & (st == k) & ccm; xi = x & S['inherited']
                r2 = dict(prior=PN[prior], surface=sn, case=ccn, condition=COND[k], area_m2=d.area[x].sum(), inherited_with_counts_m2=d.area[xi].sum(), recomputed_no_counts_m2=d.area[x & ~S['inherited']].sum())
                if k == 1: r2.update({'기둥 점 0개 m²': d.area[xi & (S['n_col'] == 0)].sum(), '기둥 점 있음·층 없음 m²': d.area[xi & (S['n_col'] > 0)].sum(), '기둥 점 수 중앙값': float(np.nanmedian(S['n_col'][xi])) if xi.any() else np.nan})
                else: r2.update({'안쪽 원 < 5 m²': d.area[xi & (S['n_inner'] < 5)].sum(), '안쪽 원 ≥ 5, 고리 < 20 m²': d.area[xi & (S['n_inner'] >= 5)].sum(), '안쪽 원 점 중앙값': float(np.nanmedian(S['n_inner'][xi])) if xi.any() else np.nan, '고리 점 중앙값': float(np.nanmedian(S['ring_found'][xi])) if xi.any() else np.nan})
                r2['① 원통 n 중앙값'] = float(np.median(n[x])) if x.any() else np.nan; rows_w.append(dict(table='조건 속', **r2))
            # 몰리는 곳
            for b in sorted(set(d.building[sm])):
                x = sm & (d.building == b); rows_w.append(dict(table='건물', prior=PN[prior], surface=sn, item=b.replace('DEBY_LOD2_', ''), area_m2=d.area[x].sum(), missing_m2=d.area[x & miss].sum(), missing_pct=100*d.area[x & miss].sum()/d.area[x].sum()))
            for nm, x in [('가장자리 0.5 m 안', sm & (dist <= .5)), ('가장자리 0.5 m 밖', sm & (dist > .5)), ('거리 없음', sm & ~np.isfinite(dist))]:
                rows_w.append(dict(table='가장자리', prior=PN[prior], surface=sn, item=nm, area_m2=d.area[x].sum(), missing_m2=d.area[x & miss].sum(), missing_pct=100*d.area[x & miss].sum()/d.area[x].sum() if d.area[x].sum() else np.nan))
            if sn == '벽':
                for k, nm in enumerate(['아래 1/3', '가운데', '위 1/3']):
                    x = sm & (band == k); rows_w.append(dict(table='벽 높이', prior=PN[prior], surface=sn, item=nm, area_m2=d.area[x].sum(), missing_m2=d.area[x & miss].sum(), missing_pct=100*d.area[x & miss].sum()/d.area[x].sum() if d.area[x].sum() else np.nan))
        save[prior] = dict(d=d, S=S, miss=miss, st=st, uM=uM)
        savez(O/'work'/STAGE/f'uM_status_{prior}.npz', patch_index=d.idx, status=st, inherited=S['inherited'], n_col=S['n_col'], n_inner=S['n_inner'], ring_found=S['ring_found'], sp_status=S['sp_st'], edge_dist=dist, wall_band=band)
    write('t9_uM_conditions', pd.DataFrame(rows), 'u_M 이 빈 까닭(코드 조건, 서로 겹치지 않음)별 넓이·패치 수. 사전 정보 × 지붕·벽 × 경우(모든 패치, 정답 넷, 채점 밖). 조건 합 = 빈 넓이(점검 통과)')
    write('t9_sigmaP_conditions', pd.DataFrame(rows_sp), '항공 LiDAR σ_P 가 빈 까닭(WIDEN0 als_status, 같은 커널 조건)')
    write('t9_uM_where', pd.DataFrame(rows_w), 'u_M 빈 곳: 조건 속 나눔(점 수는 WIDEN0 에서 물려받은 패치만 있음), 건물마다, 면 가장자리 0.5 m 안·밖, 벽 높이 구간')
    dump(TD/'checks_1.json', chk); fig(save['LoD2']); progress(f'덧붙임 3 1절 u_M 빈 까닭: {T.s():.0f} s'); print(json.dumps(jsafe(chk), ensure_ascii=False))
def fig(s):
    d, S, miss, st = s['d'], s['S'], s['miss'], s['st']; wall = d.kind == 2; A = pd.Series(d.area[wall & miss]).groupby(d.building[wall & miss]).sum(); b = A.idxmax()
    mb = d.building == b; ii = np.flatnonzero(mb & wall & miss); k = ii[np.lexsort((d.idx[ii], -d.area[ii]))][0]
    colors = {-1: '#888780', 1: '#E24B4A', 2: '#EF9F27', 3: '#7F77DD', 0: '#444441', 9: '#000000'}
    fig = plt.figure(figsize=(16, 11)); ax = fig.add_subplot(2, 3, 1, projection='3d'); X = d.centre[mb] - d.centre[mb].mean(0)
    ok = ~miss[mb]; ax.scatter(*X[ok].T, s=.3, c='#D3D1C7', label=f'u_M 있음 {d.area[mb][ok].sum():,.0f} m²')
    for kk, cl in colors.items():
        m_ = miss[mb] & (st[mb] == kk)
        if m_.any(): ax.scatter(*X[m_].T, s=1.2, c=cl, label=f"{COND[kk].split(':')[0]} {d.area[mb][m_].sum():,.0f} m²")
    xk = d.centre[k] - d.centre[mb].mean(0); ax.scatter(*xk, s=60, marker='*', c='k', label='단면 패치')
    ax.set_title(f"{b.replace('DEBY_LOD2_', '')} (LoD2) · 빈 벽 {A.max():,.0f} m²", fontsize=8); ax.legend(fontsize=5.5, loc='upper left'); ax.set_box_aspect(np.ptp(X, 0) + 1e-6)
    k2 = None; tm = np.array([T4.get(int(x), -1) for x in d.t]); cand = np.flatnonzero(wall & miss & (st == 1) & (tm == 1) & (d.S1['n'][:, 2] >= 4))
    if len(cand): k2 = cand[np.lexsort((d.idx[cand], -d.area[cand]))][0]
    for row, (kk_, lab) in enumerate([(k, '잠근 규칙: 그 건물 빈 벽 패치 넓이 차례 첫 패치'), (k2, '덧붙인 본보기: 정답 영상·① n≥4·면 못 찾음 LoD2 벽 패치 넓이 차례 첫 패치')]):
        if kk_ is None: continue
        section(fig, 2 + 3*row, kk_, d, S, st, lab)
    fig.suptitle('u_M 이 빈 벽 패치: 건물 패치 지도와 한 패치의 고리 단면(점 = WIDEN0 mvs_a 영상 점, 고리 커널이 쓴 점)', fontsize=8, y=.995); fig.tight_layout(rect=(0, 0, 1, .975))
    sv(fig, 'fig_d7_uM_missing', dict(building=b, patch_index=int(d.idx[k]), status=int(st[k]), extra_patch_index=int(d.idx[k2]) if k2 is not None else None, extra_rule='정답 영상·① n≥4·상태 1 LoD2 벽, 넓이 차례 첫 패치(덧붙인 본보기, 잠근 규칙 밖)'))
def section(fig, pos, k, d, S, st, lab):
    tl = list(loadz(inp('patches', prior='LoD2'), ['tiles'])['tiles'])[int(S['tile'][k])]; Xp = np.load(PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/holdout/internal/points'/tl/'mvs_a_xyz.npy', mmap_mode='r')
    c0 = S['centre'][k]; nn = S['onormal'][k]; box = (np.abs(Xp[:, 0] - c0[0]) < 3.5) & (np.abs(Xp[:, 1] - c0[1]) < 3.5) & (np.abs(Xp[:, 2] - c0[2]) < 3.5); Q = np.asarray(Xp[box], float) - c0
    t = Q@nn; lat = Q - t[:, None]*nn; rho = np.linalg.norm(lat, axis=1); e1 = np.cross(nn, [0, 0, 1.]); e1 = e1/np.linalg.norm(e1) if np.linalg.norm(e1) > 1e-6 else np.array([1., 0, 0]); e2 = np.cross(nn, e1)
    m = (rho <= 1.5) & (np.abs(t) <= 3.); ax = fig.add_subplot(2, 3, pos); ax.scatter(rho[m], t[m], s=1, c='#639922', lw=0); ax.axvline(.5, c='k', lw=.6, ls='--'); ax.axvline(1.5, c='k', lw=.6)
    ax.axhline(3, c='#5F5E5A', lw=.5, ls=':'); ax.axhline(-3, c='#5F5E5A', lw=.5, ls=':'); ax.set_xlim(0, 1.55); ax.set_xlabel('옆 거리 ρ (m) · 점선 안쪽 원 0.5 / 실선 고리 1.5'); ax.set_ylabel('법선 거리 t (m, 패치 중심 = 0) · 기둥 ±3 m')
    ci = (rho <= .5) & (np.abs(t) <= 3); nin = int(ci.sum())
    if nin:
        ts = np.sort(t[ci]); tops = 3 - .05*np.arange(int(round((6 - .3)/.05)) + 1); cnt = np.searchsorted(ts, tops + 1e-9, 'right') - np.searchsorted(ts, tops - .3 - 1e-9, 'left'); best = cnt.max()/nin
        jt = tops[int(np.argmax(cnt))]; ax.axhspan(jt - .3, jt, xmin=0, xmax=.33, color='#E24B4A', alpha=.3, label=f'가장 많은 0.3 m 층: 기둥 점의 {100*best:.0f} % (문턱 20 %)'); ax.legend(fontsize=6, loc='lower right')
    ax.set_title(f"{lab}\n패치 {int(d.idx[k])} · {d.building[k].replace('DEBY_LOD2_', '')} · 상태: {COND[int(st[k])].split(':')[0]} · 기둥(0.5 m) 점 {nin} · 고리 점 {int(((rho > .5) & m).sum())} · ① 원통 n {int(d.S1['n'][k, 2])}", fontsize=6.5)
    ax = fig.add_subplot(2, 3, pos + 1); a = lat@e1; b_ = lat@e2; sc = ax.scatter(a[m], b_[m], s=1, c=t[m], cmap='coolwarm', vmin=-3, vmax=3, lw=0); plt.colorbar(sc, ax=ax, label='t (m)')
    for R in [.5, 1.5]: ax.add_patch(plt.Circle((0, 0), R, fill=False, lw=.7))
    ax.set_aspect('equal'); ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.6, 1.6); ax.set_xlabel('면 안 가로 (m)'); ax.set_ylabel('면 안 세로 (m)'); ax.set_title('고리 영역(면 위에서 봄, 색 = 법선 거리)', fontsize=7)
if __name__ == '__main__': main()
