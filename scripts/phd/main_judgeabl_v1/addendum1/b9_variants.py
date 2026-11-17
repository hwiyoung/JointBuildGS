"""덧붙임 1 확인 9: 기준 t의 분위(1 %, 10 %)와 무늬 세기 문턱(3, 8)을 바꾼 판정 + JC 민감도 일곱 판 읽기.
저장된 점수로 광도 결과만 다시 내고 JC decide·target_height 그대로. 출력 /out/extra_variants_<prior>.npz (a1 이 읽어 같은 채점). 사용: b9_variants.py <prior>"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *
import pandas as pd
SENS = [('ring_1.0', '고리 1.0 m'), ('ring_3.0', '고리 3.0 m'), ('z_1.645', '배수 1.645'), ('z_2.576', '배수 2.576'), ('centre_shift', '가운데 옮김'), ('building_r', '건물마다 r'), ('same_face_ring', '같은 면 고리')]
def code(sP, sM, t, mvs, tex, nsel, thr):
    """J.photo_code 와 같고 무늬 문턱만 매개변수."""
    N = len(sP); c = np.full(N, 9, np.int8); ok = np.isfinite(t)
    with np.errstate(invalid='ignore'):
        c[ok & (sP < t) & (sM >= t)] = 1; c[ok & (sP >= t) & (sM < t)] = 0; c[ok & (sP < t) & (sM < t)] = 2; c[ok & (sP >= t) & (sM >= t)] = 3
    c[ok & ~(np.isfinite(sP) & np.isfinite(sM))] = 5; c[~mvs] = 4
    with np.errstate(invalid='ignore'): c[(tex < thr).all(1)] = 6
    c[(nsel < 3).any(1)] = 7
    return c
def main(prior):
    lock = json.loads((C/'judgeabl_v1_addendum1.lock.json').read_text()); assert sha(C/'judgeabl_v1_addendum1.json') == lock['config_sha256']
    T = Timer(); P = loadz(JP/f'photo_{prior}.npz'); kinds = [1, 2] if prior == 'LoD2' else [1]; TQ = {}; TR = []
    for kind in kinds:
        for reg in REGIONS + ['none']:
            base = (P['kind'] == kind) & P['all_within']; pool = base & (P['region'] == reg) if reg != 'none' else base & (P['region'] != 'none')
            rs = [SEED_T, REGIONS.index(reg) if reg != 'none' else 7, 0 if prior == 'LoD2' else 1, kind]
            t5, _, ch = J.threshold(P['s_P'], P['area'], pool, rs); w = P['area'][ch]
            TQ[(reg, kind)] = {q: J.quantile(P['s_P'][ch], w, q) for q in [.01, .05, .10]}; assert TQ[(reg, kind)][.05] == t5 or (np.isnan(t5) and np.isnan(TQ[(reg, kind)][.05]))
            TR.append(dict(prior=prior, kind='지붕' if kind == 1 else '벽', region=reg, t_1pct=TQ[(reg, kind)][.01], t_5pct_base=t5, t_10pct=TQ[(reg, kind)][.10], sample=len(ch)))
    rk = np.array([r if r in REGIONS else 'none' for r in P['region']]); tq = {q: np.array([TQ[(r, int(k))][q] for r, k in zip(rk, P['kind'])]) for q in [.01, .05, .10]}
    args = lambda t, thr: code(P['s_P'], P['s_M'], t, P['mvs_available'], P['texture'], P['n_selected'], thr)
    pcs = {'base': args(tq[.05], 5), '고정 1 기준 1 %': args(tq[.01], 5), '고정 2 기준 10 %': args(tq[.10], 5), '고정 3 무늬 3': args(tq[.05], 3), '고정 4 무늬 8': args(tq[.05], 8)}
    for k in pcs: pcs[k][~P['scored']] = 9
    keep = (pcs['base'] == 6) & (pcs['고정 3 무늬 3'] == 5); pcs['고정 3 무늬 3'][keep] = 6; kept_area = float(P['area'][keep].sum())
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'kind', 'area', 'n', 'geometry', 'prior_height_m', 'mvs_mean_m', 'normal', 'u_M', 'sigma_P', 'sigma_W', 'photo_code', 'photo_point', 'j_region', 'tiles'])
    ts = list(d['tiles']); N = len(d['kind']); pc = {k: np.full(N, 9, np.int8) for k in pcs}; free = np.zeros(N, bool)
    for ti, t in enumerate(ts):
        m = np.flatnonzero(d['tile'] == ti); pm = np.flatnonzero(P['tile'] == ti); n = int(d['photo_point'][m].max()) + 1
        for k, c in pcs.items(): a = np.full(n, 9, np.int8); a[P['source_index'][pm]] = c[pm]; pc[k][m] = a[d['photo_point'][m]]
        si = loadz(JC/'sight'/f'{t}__{prior}.npz', ['free5', 'free10']); free[m] = np.where(d['kind'][m] == 1, si['free10'], si['free5'])
    mi = J.VARIANTS.index('method'); nok = np.isfinite(d['normal']).all(1); OUT = {}; CHK = []
    CHK.append(dict(prior=prior, check='기준 5 %·무늬 5 로 다시 낸 광도 결과 = 저장된 패치 광도 결과', equal_pct=100*float(np.mean(pc['base'] == d['photo_code']))))
    for k, c in pc.items():
        reg, why = J.decide(prior, d['n'], d['geometry'], d['prior_height_m'], d['mvs_mean_m'], nok, d['u_M'], c, free)
        h = J.target_height(reg[mi], d['prior_height_m'], d['mvs_mean_m'], d['u_M'], d['sigma_P'], d['sigma_W'])
        if k == 'base': CHK.append(dict(prior=prior, check='기준 5 %·무늬 5 로 다시 낸 판정 = 본값', equal_pct=100*float(np.mean(reg[mi] == d['j_region'][:, mi])))); continue
        OUT[k] = (reg[mi], why[mi], h)
    for i, (v, lab) in enumerate(SENS):
        R_, W_, H_ = [], [], []
        for t in ts:
            z = loadz(JC/'judge'/v/f'{t}__{prior}.npz', ['region', 'reason', 'target_h']); R_.append(z['region'][mi]); W_.append(z['reason'][mi]); H_.append(z['target_h'][mi])
        OUT[f'고정 {5 + i} {lab} (JC)'] = (np.concatenate(R_), np.concatenate(W_), np.concatenate(H_))
    names = list(OUT); np.savez(O/f'extra_variants_{prior}.npz', names=np.array(names), region=np.stack([OUT[n][0] for n in names]).astype(np.int8), reason=np.stack([OUT[n][1] for n in names]).astype(np.int8), target_h=np.stack([OUT[n][2] for n in names]))
    # 광도 결과 여덟의 경우별 비율 (한계 밖·u_M 없음 패치의 참값 점)
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case']); pa = g['paired'] & np.isin(g['case'], CASES); gid = g['gid'][pa]; cs = g['case'][pa]
    used = (d['geometry'][gid] == 1) | ((d['geometry'][gid] == 9) & (d['n'][gid] >= 4) & ~np.isfinite(d['u_M'][gid])); rows = []
    for k, c in pc.items():
        cg = c[gid]
        for cc in CASES:
            m = used & (cs == cc); n = int(m.sum()); r = dict(prior=prior, variant='본값' if k == 'base' else k, case=CASE[cc], n=n)
            for j in range(8): r[JPC.PCODE[j] if hasattr(JPC, 'PCODE') else str(j)] = 100*float(np.mean(cg[m] == j)) if n else np.nan
            rows.append(r)
    pd.DataFrame(rows).to_csv(O/f'check9_photo_codes_{prior}.csv', index=False); pd.DataFrame(TR).to_csv(O/f'check9_t_{prior}.csv', index=False)
    dump(O/f'check9_{prior}.json', dict(at=now(), prior=prior, checks=CHK, texture3_kept_base_area_m2=kept_area, texture3_kept_points=int(keep.sum()), photo_code_area_change_m2={k: float(P['area'][c != pcs['base']].sum()) for k, c in pcs.items()}, seconds=T.s(), scientific_verdict=None))
    for c in CHK: print('CHECK', json.dumps(c, ensure_ascii=False), flush=True)
    progress(f'덧붙임 1 확인 9 판 {prior} 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main(sys.argv[1])
