"""5절 표(t5_survival, t5_survival_splits)와 6절 표(t6_rejudge, t6_initial_state, t6_transitions), 패치 값 parquet. mf4 결과만 읽는다.
살아남은 비율 = 원통(JC 와 같은 반지름·길이) 안 지금 점 가운데 그 방법이 지우지 않은 점의 비율 (면 찾기 전 원통 안 모든 점, raw_n 의 비).
'높이 중앙값이 참값에서 τ 안' = |원통 면 가까이 점의 높이 중앙값 - gt_p| <= τ (gt_p 있는 패치 넓이 가운데).
사용: mf7_tables.py <method> [<method> ...]   (none 은 늘 함께)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *
import a1_variants as A1
import pandas as pd
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mfcommon as MC
MN = MC.MNAME
f1 = lambda v: '' if v is None or not np.isfinite(v) else f'{v:.1f}'

def survival_rows(prior, methods):
    d = A1.load(prior); x = loadz(JP/f'patch_{prior}.npz', ['place']); A = d['area']; N = len(A)
    pc = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz')['pc'].astype(int)
    P = {m: np.load(MC.O/'judge'/prior/f'patch_{m}.npz') for m in ['none'] + methods}
    b = P['none']; rn0 = b['raw_n']; valid = np.isfinite(d['prior_height_m']) & np.isfinite(d['normal']).all(1)
    sets = [('차이가 유의한 패치', b['sig']), ('한계 안(일치)', valid & (b['n'] >= 4) & (b['geom'] == 0)), ('영상 깊이 점 4개 미만', valid & (b['n'] >= 0) & (b['n'] < 4))]
    gtp = d['gt_p']; taup = d['tau_p']
    within = lambda med: np.isfinite(gtp) & np.isfinite(med) & (np.abs(med - gtp) <= taup)
    w0 = within(b['med'])
    splits = [('전체', '전체', np.ones(N, bool))] + [('자리', PLACE[k], x['place'] == k) for k in [0, 1, 2]]
    surfs = SURF[prior]
    ROWS = []
    for m in methods:
        q = P[m]
        with np.errstate(invalid='ignore', divide='ignore'): ratio = np.where(rn0 > 0, q['raw_n']/np.maximum(rn0, 1), np.nan)
        few = (q['n'] >= 0) & (q['n'] < 4); w1 = within(q['med'])
        for setname, S in sets:
            states = [(STATE[s_], pc == s_) for s_ in STATE_ORDER] + [('모두', np.ones(N, bool))] if setname == '차이가 유의한 패치' else [('모두', np.ones(N, bool))]
            for sn, kk in surfs:
                km = np.isin(d['kind'], kk)
                for spn, spv, spm in splits:
                    for stn, stm in states:
                        mm = S & km & spm & stm; a = A[mm].sum(); ok = mm & np.isfinite(ratio); wa = A[ok]
                        r = dict(prior=PN[prior], method=MN[m], set=setname, state=stn, surface=sn, split=spn, split_value=spv, patches=int(mm.sum()), area_m2=float(a))
                        if ok.sum():
                            for qq in [.1, .5, .9]: r[f'survive_q{int(qq*100)}_pct'] = 100*wq(ratio[ok], wa, qq)
                            r['survive_mean_pct'] = 100*float(np.sum(ratio[ok]*wa)/wa.sum())
                        r['lt4_after_area_pct'] = 100*A[mm & few].sum()/a if a else np.nan
                        g_ = mm & np.isfinite(gtp); ag = A[g_].sum(); r['gt_area_m2'] = float(ag)
                        r['median_within_tau_before_pct'] = 100*A[g_ & w0].sum()/ag if ag else np.nan; r['median_within_tau_after_pct'] = 100*A[g_ & w1].sum()/ag if ag else np.nan
                        ROWS.append(r)
    return ROWS

def patch_table(prior, methods):
    d = A1.load(prior); pc = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz')['pc'].astype(int)
    out = dict(patch_id=d['patch_id'], kind=d['kind'], area=d['area'], initial_state=pc)
    for m in ['none'] + methods:
        q = np.load(MC.O/'judge'/prior/f'patch_{m}.npz')
        out[f'{m}_cyl_points'] = q['raw_n']; out[f'{m}_n'] = q['n']; out[f'{m}_judgment'] = q['lo']; out[f'{m}_significant'] = q['sig']
    df = pd.DataFrame(out); df.insert(0, 'patch_index', np.arange(len(df)))
    df.to_csv(MC.O/'judge'/f'patches_{prior}.csv.gz', index=False, compression='gzip'); return len(df)   # parquet 라이브러리(pyarrow·fastparquet)가 어느 이미지에도 없음

def main(methods):
    MC.cfg(); T = Timer(); methods = [m for m in methods if m != 'none']; allm = ['none'] + methods
    # ---- 5절
    R5 = []
    for prior in ['LoD2', 'ALS']: R5 += survival_rows(prior, allm)
    S = pd.DataFrame(R5)
    def md5(q):
        q = q[(q.set == '차이가 유의한 패치') & (q.split == '전체') & (q.surface.isin(['모두', '지붕']) if True else True)]
        q = q[((q.prior == 'LoD2') & (q.surface == '모두')) | ((q.prior == '항공 LiDAR') & (q.surface == '지붕'))]
        out = q[['prior', 'method', 'state', 'patches', 'area_m2']].copy()
        out['살아남은 비율 10·50·90 % / 평균'] = [f"{f1(r.get('survive_q10_pct'))} · {f1(r.get('survive_q50_pct'))} · {f1(r.get('survive_q90_pct'))} / {f1(r.get('survive_mean_pct'))}" for _, r in q.iterrows()]
        out['점 4개 미만 된 넓이 %'] = [f1(v) for v in q.lt4_after_area_pct]
        out['중앙값 τ 안 넓이 % 앞 → 뒤'] = [f"{f1(a)} → {f1(b)}" for a, b in zip(q.median_within_tau_before_pct, q.median_within_tau_after_pct)]
        return out
    MC_D = MC.D/'tables'; MC_D.mkdir(parents=True, exist_ok=True)
    wr = lambda name, df, note, md=None: _write(MC_D, name, df, note, md)
    wr('t5_survival', S, '5절. 차이가 유의한 패치(지금 점군, JUDGESTRUCT-v1 과 같음)의 처음 상태마다, 방법마다 원통 안 지금 점이 살아남은 비율(넓이 가중 10·50·90 % 값과 평균), 살아남은 점이 4개 미만이 된 넓이 %, 면 가까이 점 높이 중앙값이 참값 gt_p 에서 τ 안인 넓이 %(앞 = 지금 점군, 뒤 = 그 방법). LoD2 = 지붕+벽, 항공 LiDAR = 지붕. 나눔(지붕·벽·자리, 일치·점 4개 미만 패치)은 t5_survival_splits. 지금 점군 줄은 비율 100 %(검산).', md5)
    wr('t5_survival_splits', S, '5절 나눔 전체(csv 와 같음). set = 차이가 유의한 패치 / 한계 안(일치) / 영상 깊이 점 4개 미만(지금 점군 기준).', None)
    # ---- 6절
    rows = []
    for prior in ['LoD2', 'ALS']:
        js = pd.read_csv(MC.JS/prior/'rows.csv')
        for v in ['본 방법', '구조 하한', '구조 상한']:
            for _, r in js[js.variant == v].iterrows():
                e = dict(prior=prior, surface=r.surface, line=f'{v} (JUDGESTRUCT-v1)' if v != '구조 상한' else '구조 상한 (지금 점군, 참값으로; JUDGESTRUCT-v1)')
                for c in CN + ['전체']: e[f'ok_{c}'] = r[f'ok_{c}']; e[f'patch_ok_{c}'] = r[f'patch_ok_{c}']
                rows.append(e)
        mine = pd.read_csv(MC.O/'judge'/prior/f'rows_none_{"_".join(methods)}.csv') if (MC.O/'judge'/prior/f'rows_none_{"_".join(methods)}.csv').exists() else pd.concat([pd.read_csv(f) for f in sorted((MC.O/'judge'/prior).glob('rows_*.csv'))])
        mine = mine.drop_duplicates(subset=['surface', 'method'], keep='last')
        for m in allm:
            for _, r in mine[mine.method == m].iterrows():
                e = dict(prior=prior, surface=r.surface, line=f'구조 하한 ({MN[m]})' + (' — 이 셈에서 다시 냄' if m == 'none' else ''))
                for c in CN + ['전체']: e[f'ok_{c}'] = r[f'ok_{c}']; e[f'patch_ok_{c}'] = r[f'patch_ok_{c}']
                e['sig_area_m2'] = r.sig_area_m2; rows.append(e)
    R6 = pd.DataFrame(rows)
    for lv in ['ok', 'patch_ok']:
        V = R6[[f'{lv}_{c}' for c in CN]].to_numpy(float); R6[f'{lv}_네 경우 평균'] = V.mean(1); R6[f'{lv}_최솟값'] = V.min(1); R6[f'{lv}_최대 격차'] = V.max(1) - V.min(1)
    R6['prior'] = R6['prior'].map(PN)
    def md6(q):
        out = q[['prior', 'surface', 'line']].copy()
        for lv, lab in [('ok', '점'), ('patch_ok', '패치')]:
            out[f'{lab}: 유효/사전오류/영상오류/결측 · 전체'] = [' / '.join(f1(r[f'{lv}_{c}']) for c in CN) + f" · {f1(r[f'{lv}_전체'])}" for _, r in q.iterrows()]
            out[f'{lab}: 평균·최솟값·최대 격차'] = [f"{f1(r[f'{lv}_네 경우 평균'])} · {f1(r[f'{lv}_최솟값'])} · {f1(r[f'{lv}_최대 격차'])}" for _, r in q.iterrows()]
        return out
    wr('t6_rejudge', R6, '6절. 네 경우 목표 맞음 %(점 단위 = 참값 점, 패치 단위 = 처음 상태 넓이 가중). 앞의 셋은 JUDGESTRUCT-v1 값을 읽음. 구조 하한(방법) = 그 방법에서 살아남은 점만으로 n·높이·u_M·L·d·가시성을 다시 내고 JUDGESTRUCT-v1 구조 하한 규칙으로 판정(r·σ_W·σ_P·τ·광도 결과는 그대로). 구조 상한은 참값을 씀.', md6)
    IS = pd.concat([pd.read_csv(f) for p in ['LoD2', 'ALS'] for f in sorted((MC.O/'judge'/p).glob('initial_*.csv'))], ignore_index=True)
    IS = IS.drop_duplicates(subset=['prior', 'surface', 'method'], keep='last'); IS['prior'] = IS['prior'].map(PN); IS['method'] = IS['method'].map(MN)
    SN = [STATE[s] for s in STATE_ORDER]
    def mdis(q):
        out = q[['prior', 'surface', 'method', 'patches', 'area_m2']].copy()
        out['넓이 % (유효/사전 오류/영상 오류/결측/네 경우 밖)'] = [' / '.join(f1(r[f'area_pct_{s}']) for s in SN) for _, r in q.iterrows()]
        return out
    wr('t6_initial_state', IS, '6절. 방법마다 다시 낸 차이가 유의한 패치(= 변화가 탐지된 패치)의 넓이와 처음 상태 넓이 비율(분모 = 처음 상태가 있는 넓이). JUDGESTRUCT-v1 셈 1-1 과 같은 정의; 처음 상태는 지금 점군 기준 값 그대로.', mdis)
    TR = pd.concat([pd.read_csv(f) for p in ['LoD2', 'ALS'] for f in sorted((MC.O/'judge'/p).glob('transitions_*.csv')) if f.stat().st_size > 2], ignore_index=True)
    if len(TR):
        TR = TR.drop_duplicates(subset=['prior', 'surface', 'method', 'before', 'after'], keep='last'); TR['prior'] = TR['prior'].map(PN); TR['method'] = TR['method'].map(MN)
        TR = TR.sort_values(['prior', 'surface', 'method', 'area_m2'], ascending=[True, True, True, False])
    wr('t6_transitions', TR, '6절. 구조 하한(지금 점군) → 구조 하한(그 방법)으로 판정이 바뀐 패치의 수와 넓이(면 넓이 가운데 %).', None)
    for prior in ['LoD2', 'ALS']: patch_table(prior, methods)
    MC.progress(f'mf7 표 {allm} 끝, {round(T.s())} 초')

def _write(T_, name, df, note, md):
    df.to_csv(T_/f'{name}.csv', index=False)
    (T_/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    m = df if md is None else md(df)
    lines = ['| ' + ' | '.join(map(str, m.columns)) + ' |', '|' + '---|'*len(m.columns)]
    for r in m.itertuples(index=False):
        lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x))) for x in r) + ' |')
    (T_/f'{name}.md').write_text(f'# {name}\n\n' + (note + '\n\n' if note else '') + 'scientific_verdict: null\n\n' + '\n'.join(lines) + '\n')

if __name__ == '__main__': main(sys.argv[1:])
