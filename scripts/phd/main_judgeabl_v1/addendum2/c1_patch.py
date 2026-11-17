"""덧붙임 2 확인 10 (패치 단위 채점)·확인 11 (점 단위가 100 %에 못 미치는 까닭). 저장된 판정·점 채점만 읽는다. 사용: c1_patch.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *
import pandas as pd
TAB = D/'tables/addendum2'; TAB.mkdir(parents=True, exist_ok=True); A2 = O/'addendum2'; A2.mkdir(exist_ok=True)
CN = [CASE[c] for c in CASES]; PL = {0: '면 안쪽', 1: '면 경계', 2: '건물 가장자리'}
def write(name, df, note=''):
    df.to_csv(TAB/f'{name}.csv', index=False); (TAB/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    lines = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)]
    for r in df.itertuples(index=False): lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.2f}' if isinstance(x, float) else str(x)) for x in r) + ' |')
    (TAB/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(lines) + '\n')
def patch_case(cnt):
    tot = cnt.sum(1); mx = cnt.max(1); nwin = (cnt == mx[:, None]).sum(1); pc = np.full(len(cnt), -2, np.int8)
    single = (tot > 0) & (nwin == 1); pc[single] = cnt.argmax(1)[single]; tie0 = (tot > 0) & (nwin > 1) & (cnt[:, 0] == mx); pc[tie0] = 0
    pc[tot == 0] = -9; pc[(tot > 0) & (tot < 3)] = -3
    with np.errstate(invalid='ignore', divide='ignore'): share = np.where(tot > 0, mx/tot, np.nan)
    return pc, tot, share
def main():
    lock = json.loads((C/'judgeabl_v1_addendum2.lock.json').read_text()); assert sha(C/'judgeabl_v1_addendum2.json') == lock['config_sha256']
    T = Timer(); SA = pd.read_csv(D/'tables/s_all_variants.csv'); SA = SA[SA.scope == '전체']
    PU, PC, MX, GS, GD, CHK = [], [], [], [], [], []
    for prior in ['LoD2', 'ALS']:
        z = np.load(O/f'okbits_{prior}.npz'); names = [str(x) for x in z['names']]; n = int(z['n']); keep = z['keep']
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['gid', 'case', 'place', 'patch_kind', 'target_ok_v', 'target_distance_v'])
        gid = g['gid'][keep]; cs = g['case'][keep]; ci = np.searchsorted(CASES, cs); kind = g['patch_kind'][keep]; ppl = g['place'][keep]
        po = g['target_ok_v'][0][keep]; io = g['target_ok_v'][1][keep]; dpo = np.abs(g['target_distance_v'][0][keep]); dio = np.abs(g['target_distance_v'][1][keep]); del g
        cnt = loadz(JC/'analysis'/f'patches_{prior}.npz', ['majority_counts'])['majority_counts']; pc, tot, share = patch_case(cnt)
        d = loadz(JP/f'patch_{prior}.npz', ['area', 'kind', 'place', 'region', 'tiles']); A = d['area']; NP = len(A)
        assert len(cnt) == NP
        pid = np.concatenate([loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id'])['patch_id'] for t in d['tiles']]); pos = {s: i for i, s in enumerate(pid)}
        # 패치 판정 (variants npz → JC gid 차례)
        REG = None; vnames = None
        for r in REGIONS + ['none']:
            p = O/'variants'/f'{r}__{prior}.npz'
            if not p.exists(): continue
            with np.load(p) as v:
                if REG is None: vnames = [str(x) for x in v['variants']]; REG = np.full((len(vnames), NP), 9, np.int8)
                assert [str(x) for x in v['variants']] == vnames
                ii = np.array([pos[s] for s in v['patch_id']]); REG[:, ii] = v['region']
        same = cs == pc[gid]; valid_pc = np.isin(pc, CASES)
        # 패치 수 표
        for kk, kn in [(1, '지붕'), (2, '벽')] if prior == 'LoD2' else [(1, '지붕')]:
            km = (d['kind'] == kk) & (tot > 0); row = dict(prior=prior, surface=kn, patches_with_gt=int(km.sum()), area_with_gt_m2=float(A[km].sum()))
            for c in CASES: m = km & (pc == c); row[f'n_{CASE[c]}'] = int(m.sum()); row[f'area_{CASE[c]}'] = float(A[m].sum())
            row['n_네 경우 밖'] = int((km & (pc == 3)).sum()); row['n_동률'] = int((km & (pc == -2)).sum()); row['n_점 3개 미만 뺌'] = int((km & (pc == -3)).sum())
            row['check_sum'] = row['patches_with_gt'] == sum(row[f'n_{CASE[c]}'] for c in CASES) + row['n_네 경우 밖'] + row['n_동률'] + row['n_점 3개 미만 뺌']; PC.append(row)
            for c in CASES + [3]:
                for pl in [-1, 0, 1, 2]:
                    m = km & (pc == c) & ((d['place'] == pl) if pl >= 0 else True)
                    for lo, hi, lab in [(1.0, 1.01, '100 %'), (.8, 1.0, '80~100 %'), (.5, .8, '50~80 %'), (0, .5, '50 % 아래')]:
                        mm = m & (share >= lo) & (share < hi)
                        MX.append(dict(prior=prior, surface=kn, patch_case=CASE.get(c, '네 경우 밖'), place='모든 자리' if pl < 0 else PL[pl], majority_share=lab, patches=int(mm.sum()), area_m2=float(A[mm].sum()), area_pct=100*A[mm].sum()/A[m].sum() if A[m].sum() else np.nan))
        # 판마다
        for v in names:
            ok = np.unpackbits(z['bits'][names.index(v)])[:n].astype(bool)
            if v.startswith('기존 4'): continue
            num = np.bincount(gid[same], weights=ok[same], minlength=NP); den = np.bincount(gid[same], minlength=NP); pok = (den > 0) & (num/np.maximum(den, 1) >= .5)
            reg = REG[vnames.index(v)]; exp_ = np.full(NP, -1); exp_[valid_pc] = np.array([MATCH[int(c)] for c in pc[valid_pc]]); pname = reg == exp_
            for sn, kk in ([('지붕', [1]), ('벽', [2]), ('모두', [1, 2])] if prior == 'LoD2' else [('지붕', [1])]):
                row = dict(prior=prior, surface=sn, variant=v); km = np.isin(d['kind'], kk); kp = np.isin(kind, kk)
                for c in CASES:
                    m = km & (pc == c); a = A[m].sum(); row[f'patch_ok_{CASE[c]}'] = 100*A[m & pok].sum()/a if a else np.nan; row[f'patch_name_{CASE[c]}'] = 100*A[m & pname].sum()/a if a else np.nan
                    row[f'patches_{CASE[c]}'] = int(m.sum()); mp = kp & (cs == c); row[f'point_ok_{CASE[c]}'] = 100*ok[mp].mean() if mp.any() else np.nan
                m = km & valid_pc; row['patch_ok_전체'] = 100*A[m & pok].sum()/A[m].sum(); mp = kp; row['point_ok_전체'] = 100*ok[mp].mean()
                PU.append(row)
                s = SA[(SA.prior == prior) & (SA.surface == sn) & (SA.variant == v)]
                if len(s):
                    for c in CN: CHK.append(dict(prior=prior, surface=sn, variant=v, case=c, point_ok=row[f'point_ok_{c}'], s_all_variants=float(s.iloc[0][f'ok_{c}']), equal=bool(abs(row[f'point_ok_{c}'] - s.iloc[0][f'ok_{c}']) < 1e-9)))
            if v in ('패치 다수결 상한', '본 방법'):
                wrong = ~ok; mok = np.where(ci == 0, po | io, np.where(ci == 1, io, po)); mdist = np.where(ci == 0, np.fmin(dpo, dio), np.where(ci == 1, dio, dpo))
                excl = ~valid_pc[gid] & (pc[gid] != 3)
                cat = np.full(n, '', object); cat[wrong & ~same] = '가'; cat[wrong & same & ~mok] = '나'; cat[wrong & same & mok] = '다'
                for sn, kk in ([('지붕', [1]), ('벽', [2]), ('모두', [1, 2])] if prior == 'LoD2' else [('지붕', [1])]):
                    kp = np.isin(kind, kk)
                    for c in CASES:
                        for pl in [-1, 0, 1, 2]:
                            m = kp & (cs == c) & wrong & ((ppl == pl) if pl >= 0 else True); nw = int(m.sum()); tot_c = int((kp & (cs == c) & ((ppl == pl) if pl >= 0 else True)).sum())
                            r = dict(prior=prior, surface=sn, variant=v, case=CASE[c], place='모든 자리' if pl < 0 else PL[pl], points=tot_c, wrong_points=nw, wrong_pct=100*nw/tot_c if tot_c else np.nan)
                            for k_ in ['가', '나', '다']:
                                mk = m & (cat == k_); r[f'{k_}_points'] = int(mk.sum()); r[f'{k_}_pct_of_wrong'] = 100*mk.sum()/nw if nw else np.nan
                            r['가_of_which_patch_excluded'] = int((m & (cat == '가') & excl).sum())
                            mb = m & (cat == '나'); r['나_dist_q50_m'] = float(np.nanmedian(mdist[mb])) if mb.any() else np.nan; r['나_dist_q90_m'] = float(np.nanquantile(mdist[mb], .9)) if mb.any() else np.nan
                            r['check_sum'] = r['가_points'] + r['나_points'] + r['다_points'] == nw; GS.append(r)
        # 상한 판의 패치 판정 이름 맞음 100 %인지 (정의 검산)
        reg = REG[vnames.index('패치 다수결 상한')]; e = np.full(NP, -1); e[valid_pc] = [MATCH[int(c)] for c in pc[valid_pc]]; bad = valid_pc & (reg != e)
        why = pd.Series([f"{JUD.get(int(x), x)}→{JUD.get(int(y), y)}" for x, y in zip(e[bad], reg[bad])]).value_counts().to_dict() if bad.any() else {}
        GD.append(dict(prior=prior, check='상한 판 패치 판정 이름 맞음', patches=int(valid_pc.sum()), not_equal_patches=int(bad.sum()), not_equal_area_m2=float(A[bad].sum()), why=json.dumps(why, ensure_ascii=False)))
        np.savez(A2/f'patch_case_{prior}.npz', pc=pc, tot=tot, share=share)
        print('PATCH', prior, round(T.s()), flush=True)
    # 기존 4 (세 실험 지역): JUDGEAPPLY 패치 단위
    FU = []
    for prior in ['LoD2', 'ALS']:
        z = np.load(O/f'okbits_{prior}.npz'); names = [str(x) for x in z['names']]; n = int(z['n']); keep = z['keep']; ok = np.unpackbits(z['bits'][names.index('기존 4 결합(세 실험 지역)')])[:n].astype(bool)
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['src', 'site', 'case', 'paired'])
        for site in SITES:
            allrows = np.flatnonzero((g['src'] == 1) & (g['site'] == site)); tz = loadz(JC/'truth/exp'/f'{site}__{prior}.npz', ['current_patch_id']); cp = tz['current_patch_id']
            dec = loadz(JA/'decisions'/f'{site}__{prior}.npz', ['patch_id', 'region', 'area']); look = {s: i for i, s in enumerate(dec['patch_id'])}
            pj = np.array([look.get(s, -1) for s in cp]); cs_all = g['case'][allrows]; has = (pj >= 0) & g['paired'][allrows]
            cnt = np.zeros((len(dec['patch_id']), 5), np.int64); m = has & (cs_all >= 0) & (cs_all <= 4); np.add.at(cnt, (pj[m], cs_all[m]), 1); pc, tot, share = patch_case(cnt)
            kr = np.searchsorted(keep, allrows); inkeep = (kr < len(keep)) & (keep[np.minimum(kr, len(keep) - 1)] == allrows)
            okr = np.zeros(len(allrows), bool); okr[inkeep] = ok[kr[inkeep]]
            same = inkeep & has & (cs_all == pc[np.maximum(pj, 0)])
            num = np.bincount(pj[same], weights=okr[same], minlength=len(pc)); den = np.bincount(pj[same], minlength=len(pc)); pok = (den > 0) & (num/np.maximum(den, 1) >= .5)
            reg = dec['region'][4]; Ad = dec['area']
            for c in CASES:
                mm = pc == c; FU.append(dict(prior=prior, site=site, case=CASE[c], patches=int(mm.sum()), patch_ok_pct=100*Ad[mm & pok].sum()/Ad[mm].sum() if Ad[mm].sum() else np.nan,
                                         patch_name_pct=100*Ad[mm & (reg == MATCH[c])].sum()/Ad[mm].sum() if Ad[mm].sum() else np.nan))
    pu = pd.DataFrame(PU)
    write('p_patch_unit', pu, '확인 10: 패치 단위 목표 맞음·판정 이름 맞음 % (넓이 가중; 패치 넓이가 같지 않음), 점 단위 목표 맞음 % 나란히. 패치의 경우 = JC 다수결 규칙(동률에 두 자료 모두 유효가 있으면 그것, 다른 동률은 뺌), 참값 점 3개 미만 뺌. 패치 목표 맞음 = 다수 경우 참값 점의 절반 이상이 τ 안.')
    write('p_patch_counts', pd.DataFrame(PC), '확인 10: 경우별 패치 수·넓이, 네 경우 밖, 동률, 점 3개 미만으로 뺀 패치. check_sum = 합이 참값 점 있는 패치 수와 같음.')
    write('p_mixed', pd.DataFrame(MX), '확인 10: 다수 경우 점 비율(다섯 경우 모두로 셈) 구간마다 패치 수·넓이, 패치의 경우·자리마다.')
    write('p_gap_split', pd.DataFrame(GS), '확인 11: 틀린 참값 점의 원인 — 가 패치 안 섞임(점의 경우 ≠ 패치의 경우; 뺀 패치의 점 포함, 그 수 따로), 나 자료의 한계(맞는 자료의 목표도 τ 밖; 사전정보 오류 → 영상 단독, 영상 깊이 오류·결측 → 사전 정보 단독, 두 자료 모두 유효 → 둘 다 τ 밖), 다 판정. 나의 거리 = 맞는 자료 목표까지 |거리|(m).')
    write('p_fusion3_patch', pd.DataFrame(FU), '확인 10: 기존 4(세 실험 지역)를 JUDGEAPPLY 패치에서 패치 단위로. 다른 판과 패치 짜임이 다름.')
    write('p_checks', pd.DataFrame(CHK + GD), '검산: 점 단위 값 = s_all_variants (판 x 경우), 상한 판의 패치 판정 이름 맞음.')
    ck = pd.DataFrame(CHK); print('CHECK point = s_all_variants', int(ck.equal.sum()), len(ck), flush=True)
    progress(f'덧붙임 2 확인 10·11 표 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
