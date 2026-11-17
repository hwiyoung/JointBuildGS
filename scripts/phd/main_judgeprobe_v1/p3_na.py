"""확인 나 (발주 4절): t_M = s_M 의 한계 안 아래 5 % (t 와 같은 규칙·씨앗), 판 가 = s_P 는 t, s_M 은 t_M 과 비교. 나머지 규칙은 JC 본값 그대로.
검산: 저장 값으로 다시 낸 본값 판정 = JC judge/base (100 %), 본값 목표 맞음 = JC c1_case_summary."""
from common import *
from tables import write
import pandas as pd
SEED = 20261112
def photo_code2(s_P, s_M, t, tM, mvs_available, texture, n_selected):
    """J.photo_code 와 같고, s_M 만 tM 과 비교."""
    N = len(s_P); code = np.full(N, 9, np.int8); ok = np.isfinite(t) & np.isfinite(tM)
    with np.errstate(invalid='ignore'):
        p, m = s_P, s_M
        code[ok & (p < t) & (m >= tM)] = 1; code[ok & (p >= t) & (m < tM)] = 0; code[ok & (p < t) & (m < tM)] = 2; code[ok & (p >= t) & (m >= tM)] = 3
    code[ok & ~(np.isfinite(p) & np.isfinite(m))] = 5; code[~mvs_available] = 4
    with np.errstate(invalid='ignore'): code[(texture < 5).all(1)] = 6
    code[(n_selected < 3).any(1)] = 7
    return code
def main():
    cfg(); T = Timer(); jt = {(r['region'], r['prior'], r['kind']): r['t'] for r in json.loads((JC/'judge/base.json').read_text())['t_rows']}
    TROWS, SUM, PC, TR, CHK = [], [], [], [], []
    for prior in ['LoD2', 'ALS']:
        P = loadz(O/f'photo_{prior}.npz'); kinds = [1, 2] if prior == 'LoD2' else [1]
        tv, tmv = {}, {}
        for kind in kinds:
            for reg in REGIONS + ['none']:
                base = (P['kind'] == kind) & P['all_within']; pool = base & (P['region'] == reg) if reg != 'none' else base & (P['region'] != 'none')
                rs = [SEED, REGIONS.index(reg) if reg != 'none' else 7, 0 if prior == 'LoD2' else 1, kind]
                t, t10, ch = J.threshold(P['s_P'], P['area'], pool, rs); tm, tm10, ch2 = J.threshold(P['s_M'], P['area'], pool, rs)
                assert np.array_equal(ch, ch2); tv[(reg, kind)] = t; tmv[(reg, kind)] = tm
                same = (np.isnan(t) and np.isnan(jt[(reg, prior, kind)])) or t == jt[(reg, prior, kind)]
                TROWS.append(dict(prior=prior, kind='지붕' if kind == 1 else '벽', region=reg, t=t, t_M=tm, t_minus_t_M=t - tm, t10=t10, t_M10=tm10, pool_count=int(pool.sum()), sample_count=len(ch), t_equals_JC=bool(same)))
                assert same, (prior, kind, reg, t, jt[(reg, prior, kind)])
        rk = np.array([r if r in REGIONS else 'none' for r in P['region']])
        tt = np.array([tv[(r, int(k))] for r, k in zip(rk, P['kind'])]); ttm = np.array([tmv[(r, int(k))] for r, k in zip(rk, P['kind'])])
        c0 = J.photo_code(P['s_P'], P['s_M'], tt, P['mvs_available'], P['texture'], P['n_selected']); c0[~P['scored']] = 9
        c1 = photo_code2(P['s_P'], P['s_M'], tt, ttm, P['mvs_available'], P['texture'], P['n_selected']); c1[~P['scored']] = 9
        d = loadz(O/f'patch_{prior}.npz', ['tile', 'local', 'kind', 'area', 'n', 'geometry', 'prior_height_m', 'mvs_mean_m', 'normal', 'u_M', 'sigma_P', 'sigma_W', 'photo_code', 'photo_point', 'j_region', 'j_reason', 'target_h', 'centre', 'case', 'tiles'])
        ts = list(d['tiles']); N = len(d['kind'])
        pc0 = np.full(N, 9, np.int8); pc1 = np.full(N, 9, np.int8); free = np.zeros(N, bool)
        for ti, t in enumerate(ts):
            m = np.flatnonzero(d['tile'] == ti); pm = np.flatnonzero(P['tile'] == ti)
            grp_n = int(d['photo_point'][m].max()) + 1; a0 = np.full(grp_n, 9, np.int8); a1 = a0.copy(); a0[P['source_index'][pm]] = c0[pm]; a1[P['source_index'][pm]] = c1[pm]
            pc0[m] = a0[d['photo_point'][m]]; pc1[m] = a1[d['photo_point'][m]]
            si = loadz(JC/'sight'/f'{t}__{prior}.npz', ['free5', 'free10']); free[m] = np.where(d['kind'][m] == 1, si['free10'], si['free5'])
        assert np.array_equal(pc0, d['photo_code']), 'base photo code differs'
        mi = J.VARIANTS.index('method'); nok = np.isfinite(d['normal']).all(1)
        r0, w0 = J.decide(prior, d['n'], d['geometry'], d['prior_height_m'], d['mvs_mean_m'], nok, d['u_M'], pc0, free)
        r1, w1 = J.decide(prior, d['n'], d['geometry'], d['prior_height_m'], d['mvs_mean_m'], nok, d['u_M'], pc1, free)
        same = float((r0[mi] == d['j_region'][:, mi]).mean()); CHK.append(dict(prior=prior, check='본값 판정 다시 냄 = JC judge/base 본 방법', equal_pct=100*same)); assert same == 1.0
        h1 = J.target_height(r1[mi], d['prior_height_m'], d['mvs_mean_m'], d['u_M'], d['sigma_P'], d['sigma_W'])
        h0 = d['target_h'][:, mi]; changed = (r1[mi] != r0[mi]); hc = changed | ~((h1 == h0) | (np.isnan(h1) & np.isnan(h0)))
        # 바뀐 판정 넓이
        for a in [0, 1, 2, 3, 4, 9]:
            for b in [0, 1, 2, 3, 4, 9]:
                m = changed & (r0[mi] == a) & (r1[mi] == b)
                if m.any():
                    for kind in kinds: mk = m & (d['kind'] == kind); TR.append(dict(prior=prior, kind='지붕' if kind == 1 else '벽', from_judgment=JUD[a], to_judgment=JUD[b], patches=int(mk.sum()), area_m2=float(d['area'][mk].sum())))
        # 참값 점
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind', 'tau', 'target_ok_v', 'region_v', 'patch_kind', 'photo_code'])
        pa = g['paired']; gid = g['gid']; ok_base = g['target_ok_v'][mi].copy(); ok_new = ok_base.copy()
        sel = np.flatnonzero(pa & hc[np.maximum(gid, 0)]); pg = gid[sel]
        dist = plane_distance(g['xyz'][sel], g['normal'][sel], d['centre'][pg], d['normal'][pg], h1[pg], g['gt_kind'][sel] == 2); ok_new[sel] = np.abs(dist) <= g['tau'][sel]
        reg_new = g['region_v'][mi].copy(); reg_new[pa] = r1[mi][gid[pa]]
        assert np.array_equal(g['region_v'][mi][pa], r0[mi][gid[pa]])
        pcg0 = np.full(len(pa), 9, np.int8); pcg1 = pcg0.copy(); pcg0[pa] = pc0[gid[pa]]; pcg1[pa] = pc1[gid[pa]]
        used = np.zeros(len(pa), bool); used[pa] = np.isin(d['geometry'][gid[pa]], [1]) | ((d['geometry'][gid[pa]] == 9) & (d['n'][gid[pa]] >= 4) & ~np.isfinite(d['u_M'][gid[pa]]))
        SURF = {'지붕': g['patch_kind'] == 1, '벽': g['patch_kind'] == 2, '모두': np.ones(len(pa), bool)} if prior == 'LoD2' else {'지붕': g['patch_kind'] == 1}
        V = {'본값 판': (ok_base, g['region_v'][mi]), '판 가 (t_M)': (ok_new, reg_new), '사전 정보 단독': (g['target_ok_v'][0], g['region_v'][0]), '영상 단독': (g['target_ok_v'][1], g['region_v'][1]), '패치 다수결 상한': (g['target_ok_v'][7], g['region_v'][7])}
        for sn, sm in SURF.items():
            for vn, (ok, rg) in V.items():
                for c in [0, 1, 2, 4]:
                    m = pa & sm & (g['case'] == c); n = int(m.sum())
                    SUM.append(dict(prior=prior, surface=sn, variant=vn, case=CASE[c], n=n, target_ok_pct=100*ok[m].mean() if n else np.nan, name_ok_pct=100*(rg[m] == MATCH[c]).mean() if n else np.nan))
            for vn, pcg in [('본값 판', pcg0), ('판 가 (t_M)', pcg1)]:
                for c in [0, 1, 2, 4]:
                    m = pa & sm & used & (g['case'] == c); n = int(m.sum()); row = dict(prior=prior, surface=sn, variant=vn, case=CASE[c], n=n)
                    for k in range(8): row[PCODE[k]] = 100*(pcg[m] == k).mean() if n else np.nan
                    PC.append(row)
        # JC 요약표와 대조
        c1t = pd.read_csv(R/f'docs/experiments/phd/main_judgecheck_v2/tables/c1_case_summary_{prior}.csv')
        for sn in SURF:
            q = c1t[(c1t['group'] == '전체') & (c1t['place'] == '모든 자리') & (c1t['surface'] == sn) & (c1t['variant'] == '본 방법')]
            for c in [0, 1, 2, 4]:
                mine = [r for r in SUM if r['prior'] == prior and r['surface'] == sn and r['variant'] == '본값 판' and r['case'] == CASE[c]][0]
                jc = q[q['case'] == CASE[c]].iloc[0]
                CHK.append(dict(prior=prior, check=f'본값 목표 맞음 {sn} {CASE[c]}', mine=mine['target_ok_pct'], JC=float(jc['target_ok_pct']), equal_pct=100.0*(abs(mine['target_ok_pct'] - jc['target_ok_pct']) < 1e-9 and mine['n'] == jc['n'])))
        savez(O/f'na_{prior}.npz', region_new=r1[mi], reason_new=w1[mi], target_h_new=h1, photo_code_new=pc1)
        print('NA', prior, round(T.s()), int(changed.sum()), flush=True)
    note = '확인 나. t_M = 한계 안 사진 점(구성 패치 모두 한계 안, 본값)의 s_M 넓이 가중 아래 5 %, t 와 같은 표본(5000개, 같은 씨앗). 판 가는 비교 줄이며 본값을 바꾸지 않는다.'
    write('na_t_tM', pd.DataFrame(TROWS), note=note)
    write('na_summary', pd.DataFrame(SUM), note=note + ' 목표 맞음·판정 이름 맞음 = 참값 점 비율(JC s7 규칙).')
    write('na_photo_codes', pd.DataFrame(PC), note=note + ' 광도 결과를 쓰는 패치(한계 밖, u_M 없음)의 참값 점, 경우마다 광도 결과 비율 %.')
    write('na_transitions', pd.DataFrame(TR), note=note + ' 판정이 바뀐 패치의 넓이 (본값 -> 판 가).')
    write('na_check', pd.DataFrame(CHK), note='검산: 본값을 저장 값으로 다시 낸 판정과 목표 맞음이 JC 와 같은가.')
    progress(f'확인 나 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
