"""덧붙임 3 고침 1(11/21): 판 '점검' A2(깊이 일치) 와 본 방법의 저장된 광도 결과(JUDGECHECK-v2 본값 판, 패치마다 여덟 가운데 하나)를 함께 씀.
학습·새 광도 점수·새 화소 셈 없음, CPU. 판에는 참값을 쓰지 않음(참값은 처음 상태·채점·그림 표시에만).
판(사전정보 사용으로 바꾸는 패치, 대상 = 차이가 유의한 패치, 출발 = 지금 점군의 구조 하한):
  가 A2만 = A2 되돌림(원통 안 판정용 점 n < 4) / 나 A2 + 구제 = 가 가운데 광도 결과가 반박이 아닌 것 / 다 A2 + 구제 + 추가 = 나 ∪ 광도 결과 지지 / 라 사진 대조만 = 광도 결과 지지.
  참고 판 다″(세션 값): s_P·s_M 둘 다 있을 때 s_M − s_P ≥ 0.1 이고 s_M ≥ 0.3 → 반박, s_P − s_M ≥ 0.1 이고 s_P ≥ 0.3 → 지지; 다와 같은 짜임.
광도 결과 번호(JUDGECHECK-v2 jc2_judge.photo_code): 0 지지, 1 반박, 2 둘 다 낮음, 3 둘 다 높음, 4 MVS 면 없음, 5 조각 부족(= 표본 부족), 6 무늬 없음, 7 사진 부족, 9 셈 안 함.
사용: mf18_addendum3.py tables | figs <prior>"""
import sys, gzip, io
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mf11_check as M11
from mf11_check import *
from jscommon import *
from common import wq, PLACE
import js3_figs as J3
DOCT = Path('/docs/tables'); DOCF = Path('/docs/figures')
PCODE = {0: '지지', 1: '반박', 2: '둘 다 낮음', 3: '둘 다 높음', 4: 'MVS 면 없음', 5: '조각 부족', 6: '무늬 없음', 7: '사진 부족', 9: '셈 안 함'}
PORDER = [1, 0, 7, 6, 4, 5, 2, 3, 9]   # 반박, 지지, 구별 불가 여섯(발주 차례), 셈 안 함
PANELS = [('ga', '판 가. A2만'), ('na', '판 나. A2 + 구제 (묶는 방식 = 세션 판)'), ('da', '판 다. A2 + 구제 + 추가 (묶는 방식 = 세션 판)'), ('ra', '판 라. 사진 대조만'), ('dapp', '참고 판 다″ (점수 차 0.1·0.3 = 세션 값)')]
NEW3 = ['photo_result', 'combo_D_returned', 'combo_D_judgment']
JN = M11.JN
SESSION_DPP = {('LoD2', '모두'): (48.0, 9.3, 19.3), ('항공 LiDAR', '지붕'): (63.4, 3.3, 35.5)}

def base3(prior):
    S = M11.setup(prior); d = S['d']; N = len(d['kind'])
    jd = MC.O/'judge'/prior; b = np.load(jd/'patch_none.npz'); q = np.load(jd/'patch_A2.npz'); sig = b['sig']; lo0 = b['lo']
    flipA2 = sig & (q['n'] >= 0) & (q['n'] < 4)
    # 광도 결과: JUDGECHECK-v2 judge/base(본값 판) 를 구역·패치 차례로 읽고, JP 패치 파일 값과 같은지 대조
    pcode = np.full(N, -1, np.int16); stored = np.zeros(N, bool); sPb = np.full(N, np.nan); sMb = np.full(N, np.nan)
    for ti, t in enumerate(d['tiles']):
        m = np.flatnonzero(d['tile'] == ti); f = JC/'judge/base'/f'{t}__{prior}.npz'
        if not f.exists(): continue
        z = loadz(f, ['patch_id', 'photo_code', 's_P', 's_M']); assert np.array_equal(z['patch_id'], d['patch_id'][m])
        pcode[m] = z['photo_code']; stored[m] = True; sPb[m] = z['s_P']; sMb[m] = z['s_M']
    ck = dict(prior=PN[prior], tiles=len(d['tiles']), patches=N, stored=int(stored.sum()),
              photo_code_equal_JP=int((pcode[stored] == d['photo_code'][stored]).sum()),
              s_equal_JP=int(((np.isnan(sPb) & np.isnan(d['s_P'])) | (sPb == d['s_P']))[stored].sum() + 0),
              sM_equal_JP=int(((np.isnan(sMb) & np.isnan(d['s_M'])) | (sMb == d['s_M']))[stored].sum()))
    pres = np.where(stored, pcode, 9).astype(int)   # 저장되지 않은 패치 = 구별 불가(셈 안 함과 함께 9 로, 수는 따로 적음)
    ck['not_stored_sig'] = int((sig & ~stored).sum()); ck['code9_sig'] = int((sig & (pres == 9)).sum())
    sP, sM = d['s_P'], d['s_M']; fin = np.isfinite(sP) & np.isfinite(sM)
    with np.errstate(invalid='ignore'):
        ref2 = fin & (sM - sP >= .1) & (sM >= .3); sup2 = fin & (sP - sM >= .1) & (sP >= .3)
    F = dict(ga=flipA2, na=flipA2 & (pres != 1), ra=sig & (pres == 0))
    F['da'] = F['na'] | F['ra']; F['dapp'] = (flipA2 & ~ref2) | (sig & sup2)
    return S, d, sig, lo0, flipA2, pres, stored, F, ck

def f1(v): return '' if v is None or not np.isfinite(v) else f'{v:.1f}'

def tables_mode():
    T = Timer(); RM, OVER, DET, CK, PH, RS, AD, PLC = [], [], [], [], [], [], [], []
    t8 = pd.read_csv(DOCT/'t8_check_mode.csv'); t6 = pd.read_csv(DOCT/'t6_rejudge.csv')
    for prior in ['LoD2', 'ALS']:
        S, d, sig, lo0, flipA2, pres, stored, F, ck = base3(prior); A = S['A']; pc = S['pc']; gp = np.bincount(S['gid'], minlength=len(A)); CK.append(dict(check='광도 결과 읽기(JC judge/base = JP 패치 값)', **ck))
        RM += [dict(r, panel='본 방법') for r in t6[(t6.prior == PN[prior]) & (t6.line == '본 방법 (JUDGESTRUCT-v1)')].to_dict('records')]
        rows, _ = summary(S, prior, lo0, '구조 하한 (지금 점군)', {}); RM += [dict(r, panel='구조 하한') for r in rows]
        up = np.load(MC.JS/prior/'fig_arrays.npz')['up']; up_rows, ok_up = summary(S, prior, up, '구조 상한 (지금, 참값으로)', {}); RM += [dict(r, panel='구조 상한') for r in up_rows]; UPT = {r['surface']: r for r in up_rows}
        LO = {}
        for key, lab in PANELS:
            fl = F[key]; lo = lo0.copy(); lo[fl] = 1; LO[key] = lo; rows, okl = summary(S, prior, lo, lab, {})
            for r, fr in zip(rows, flip_rates(S, prior, sig, fl)): r.update({k: v for k, v in fr.items() if k != 'surface'}); r['panel'] = key
            RM += rows
            for r in rows:
                u = UPT[r['surface']]
                if r['ok_전체'] > u['ok_전체'] + 1e-9 or r['patch_ok_전체'] > u['patch_ok_전체'] + 1e-9:
                    OVER.append(dict(prior=PN[prior], surface=r['surface'], line=lab, point_value=r['ok_전체'], point_upper=u['ok_전체'], patch_value=r['patch_ok_전체'], patch_upper=u['patch_ok_전체']))
                    DET.extend(M11.detail(S, prior, r['surface'], dict(SURF[prior])[r['surface']], up, ok_up, lo, okl, lab))
            if key == 'ga':   # 검산 1
                ref = t8[(t8.prior == PN[prior]) & (t8.method == 'A2') & (t8['mode'] == '점 4개 미만')].set_index('surface'); diffs = {}
                for r in rows:
                    rr = ref.loc[r['surface']]; num = [k for k in r if k not in ('prior', 'surface', 'line', 'panel') and isinstance(r[k], (int, float, np.floating, np.integer))]
                    diffs[r['surface']] = max(abs(float(r[k]) - float(rr[k])) if np.isfinite(float(r[k])) else (0. if not np.isfinite(float(rr[k])) else 1e9) for k in num)
                CK.append(dict(prior=PN[prior], check='검산 1: 판 가의 모든 값 = 묶음 나2 t8_check_mode A2 본 판(점 4개 미만)', max_abs_diff=diffs, passed=bool(max(diffs.values()) < 1e-9)))
        # 2.2 광도 결과 여덟 x 처음 상태
        for sn, kk in SURF[prior]:
            km = np.isin(d['kind'], kk) & sig; tot = A[km].sum(); sm_ = 0.
            for code in PORDER:
                mc = km & (pres == code); sm_ += A[mc].sum()
                r = dict(prior=PN[prior], surface=sn, photo=PCODE[code] + (' (저장 안 된 패치 포함)' if code == 9 else ''), area_m2=float(A[mc].sum()), gt_points=int(gp[mc].sum()), patches=int(mc.sum()),
                         A2_returned_pct=100*A[mc & flipA2].sum()/A[mc].sum() if A[mc].sum() else np.nan)
                for s_ in STATE_ORDER:
                    mm = mc & (pc == s_); r[f'{STATE[s_]}_m2'] = float(A[mm].sum()); r[f'{STATE[s_]}_gt'] = int(gp[mm].sum()); r[f'{STATE[s_]}_A2_returned_pct'] = 100*A[mm & flipA2].sum()/A[mm].sum() if A[mm].sum() else np.nan
                mm = mc & ~np.isin(pc, STATE_ORDER); r['처음 상태 없음_m2'] = float(A[mm].sum())
                PH.append(r)
            CK.append(dict(prior=PN[prior], surface=sn, check='검산 2: 광도 결과 여덟(+셈 안 함)의 넓이 합 = 차이가 유의한 패치 넓이', sum_m2=float(sm_), sig_m2=float(tot), passed=bool(abs(sm_ - tot) < 1e-6)))
            # 구제·추가
            for nm, mk, OUTL in [('구제(판 나: A2 되돌림이었으나 광도 결과 반박이라 그대로)', km & flipA2 & ~F['na'], RS), ('추가(판 다: A2 는 통과였으나 광도 결과 지지라 되돌림)', km & F['da'] & ~flipA2, AD)]:
                r = dict(prior=PN[prior], surface=sn, what=nm, area_m2=float(A[mk].sum()), gt_points=int(gp[mk].sum()), patches=int(mk.sum()))
                for s_ in STATE_ORDER:
                    mm = mk & (pc == s_); r[f'{STATE[s_]}_m2'] = float(A[mm].sum()); r[f'{STATE[s_]}_gt'] = int(gp[mm].sum()); r[f'{STATE[s_]}_den_m2'] = float(A[km & (pc == s_)].sum())
                OUTL.append(r)
            # 자리마다 판 가·다
            plc = loadz(JP/f'patch_{prior}.npz', ['place'])['place']
            for pk, pnm in PLACE.items():
                mp = km & (plc == pk); r = dict(prior=PN[prior], surface=sn, place=pnm)
                for key in ['ga', 'da']:
                    for s_, nm in [(2, 'found'), (1, 'wrong'), (0, 'bothvalid')]:
                        mm = mp & (pc == s_); a = A[mm].sum(); r[f'{key}_{nm}_pct'] = 100*A[mm & F[key]].sum()/a if a else np.nan; r[f'{key}_{nm}_m2'] = float(A[mm & F[key]].sum()); r[f'{key}_{nm}_gt'] = int(gp[mm & F[key]].sum())
                        r[f'den_{nm}_m2'] = float(a); r[f'den_{nm}_gt'] = int(gp[mm].sum())
                PLC.append(r)
        # 검산 2 둘째: JUDGECHECK-v2 확인 3 과 같은 정의(참값 점, 본값 한계 밖 또는 u_M 없음, 점의 경우 x 광도 결과)
        c3 = pd.read_csv(Path('/repo/docs/experiments/phd/main_judgecheck_v2/tables/c3_photo_by_case.csv')); c3 = c3[(c3.prior == prior) & (c3.texture == '모두') & (c3.place == '모든 자리')].set_index('case')
        geom = d['geometry']; nou = (d['n'] >= 4) & (geom == 9) & ~np.isfinite(d['u_M']); scope_p = (geom == 1) | nou; gid, cs = S['gid'], S['cs']; mx = 0.; rows = []
        for c in CASES:
            m = scope_p[gid] & (cs == c); r = dict(prior=PN[prior], case=CASE[c], n_here=int(m.sum()), n_c3=int(c3.loc[CASE[c], 'n']))
            for k, kn in PCODE.items():
                v = 100*float((pres[gid][m] == k).mean()) if m.any() else np.nan; r[kn] = v; r[kn + '_c3'] = float(c3.loc[CASE[c], kn + '_pct']); mx = max(mx, abs(v - r[kn + '_c3']))
            rows.append(r)
        CK.append(dict(prior=PN[prior], check='검산 2 둘째: 처음 상태(점의 경우)마다 광도 결과 비율 = JUDGECHECK-v2 확인 3(c3_photo_by_case, 무늬 모두·모든 자리), 같은 정의', rows=rows, max_abs_diff_pct=mx, n_equal=all(r['n_here'] == r['n_c3'] for r in rows)))
        # 검산 4 와 패치 열 셋
        src = MC.O/'judge'/f'patches2_{prior}.csv.gz'; lines = gzip.open(src, 'rt', newline='').read().split('\n'); assert lines[-1] == ''; lines = lines[:-1]
        pid = pd.read_csv(src, usecols=['patch_id'])['patch_id'].values; assert np.array_equal(pid, d['patch_id'])
        nd = pd.DataFrame(dict(photo_result=[PCODE[int(c)] if s else '저장 안 됨' for c, s in zip(pres, stored)], combo_D_returned=F['da'].astype(int), combo_D_judgment=[JN.get(int(j), str(j)) for j in LO['da']]))
        buf = io.StringIO(); nd.to_csv(buf, index=False); nl = buf.getvalue().split('\n')[:-1]; assert len(nl) == len(lines)
        dst = MC.O/'judge'/f'patches3_{prior}.csv.gz'
        with gzip.open(dst, 'wt', newline='') as w: w.write('\n'.join(a + ',' + b for a, b in zip(lines, nl)) + '\n')
        back = gzip.open(dst, 'rt', newline='').read().split('\n')[:-1]
        CK.append(dict(prior=PN[prior], check='검산 4: 더한 열 셋을 뗀 패치 값 = 묶음 나3(patches2) 바이트까지', rows=len(back) - 1, passed=('\n'.join(','.join(x.split(',')[:-3]) for x in back) == '\n'.join(lines))))
        print('TABLES3', prior, round(T.s()), flush=True)
    # 검산 3
    for (pr, sn), (a, b, c) in SESSION_DPP.items():
        r = [x for x in RM if x['prior'] == pr and x['surface'] == sn and x.get('panel') == 'dapp'][0]; v = (r['found_imgerr_pct'], r['wrong_priorerr_pct'], r['changed_bothvalid_pct'])
        CK.append(dict(prior=pr, surface=sn, check='검산 3: 참고 판 다″ = 덧붙임 3 1절 세션 값 (0.5 %p 안)', here=list(map(float, v)), session=[a, b, c], max_abs_diff_pp=float(max(abs(x - y) for x, y in zip(v, (a, b, c)))), passed=bool(max(abs(x - y) for x, y in zip(v, (a, b, c))) <= .5)))
    tab = lambda rows, name, note: (pd.DataFrame(rows).to_csv(DOCT/f'{name}.csv', index=False), dump(DOCT/f'{name}.json', dict(rows=json.loads(pd.DataFrame(rows).to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None)))
    tab(RM, 't11_combo', '덧붙임 3 2.1절. 본 방법은 t6_rejudge 에서 읽음. 판 나·다의 묶는 방식은 세션 판, 광도 결과는 본 방법 그대로. 참고 판 다″의 0.1·0.3 은 세션 값.')
    tab(PH, 't11_combo_photo', '덧붙임 3 2.2절 첫째: 차이가 유의한 패치를 광도 결과로 나눔, 처음 상태마다 넓이·참값 점·A2 되돌림 비율.')
    tab(RS, 't11_combo_rescued', '덧붙임 3 2.2절 둘째: 판 나에서 구제된 패치, 처음 상태마다.')
    tab(AD, 't11_combo_added', '덧붙임 3 2.2절 셋째: 판 다에서 추가된 패치, 처음 상태마다.')
    tab(PLC, 't11_combo_place', '덧붙임 3 2.2절 넷째: 자리마다 판 가·다의 찾은·잘못 되돌린·유효 바뀜 비율.')
    tab(OVER, 't11_over_upper_lines', '구조 상한보다 전체 목표 맞음이 높은 줄.'); tab(DET, 't11_over_upper', '구조 상한을 넘는 줄을 처음 상태 x 판정으로 나눔(t8_over_upper 와 같은 방식).')
    dump(DOCT/'t11_checks.json', dict(at=now(), checks=CK, seconds=T.s(), scientific_verdict=None))
    for c in CK: print('CHECK', json.dumps(jsafe(c), ensure_ascii=False), flush=True)
    write_md(RM, PH, RS, AD, PLC, OVER, DET, CK); MC.progress(f'mf18 tables(덧붙임 3 2절) 끝, {round(T.s())} 초')

def write_md(RM, PH, RS, AD, PLC, OVER, DET, CK):
    show = lambda r: (r['prior'] == 'LoD2' and r['surface'] in ['지붕', '벽', '모두']) or (r['prior'] == '항공 LiDAR' and r['surface'] == '지붕')
    hdr = ['# t11_combo', '', "덧붙임 3 2.1절. 판 '점검' A2(깊이 일치)와 본 방법의 저장된 광도 결과(JUDGECHECK-v2 본값 판)를 함께 씀. 대상 = 차이가 유의한 패치(지금 점군), 출발 = 지금 점군의 구조 하한, 점군·패치 값은 그대로.", '',
           '- 판 가 = A2 되돌림(원통 안 판정용 점 n < 4). 판 나 = 판 가 가운데 광도 결과가 반박이 아닌 것. 판 다 = 판 나 ∪ 광도 결과 지지. 판 라 = 광도 결과 지지.',
           '- **판 나·다는 두 근거를 묶는 방식을 세션이 정한 것이다.** 광도 결과 자체(기준 t, 사진 고르기, 판정 표의 차례)는 본 방법 본값 그대로다.',
           '- 참고 판 다″: 광도 결과 대신 점수 차(s_P·s_M 둘 다 있을 때 s_M − s_P ≥ 0.1·s_M ≥ 0.3 → 반박, s_P − s_M ≥ 0.1·s_P ≥ 0.3 → 지지). **0.1·0.3 은 본 방법의 값이 아니라 세션 값이다.**',
           '- 본 방법·구조 하한·구조 상한 줄은 판을 바꾸지 않으므로 찾은·잘못 되돌린 칸이 비어 있다. 본 방법 줄은 t6_rejudge(JUDGESTRUCT-v1) 에서 읽음.', '', 'scientific_verdict: null', '',
           '찾은 = 처음 상태 영상 깊이 오류 넓이 가운데 바뀐 %, 잘못 되돌린 = 사전정보 오류 가운데, 유효 바뀜 = 두 자료 모두 유효 가운데. 괄호 = (바뀐 넓이 m², 그 패치들에 속한 네 경우 참값 점 수). 네 경우 차례 = 두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측.', '',
           '| 사전 정보 | 면 | 줄 | 점: 네 경우 · 전체 | 점: 평균·최솟값·격차 | 패치: 네 경우 · 전체 | 패치: 평균·최솟값·격차 | 찾은 % (m², 점) | 잘못 되돌린 % (m², 점) | 유효 바뀜 % (m², 점) | F(JS) % | 바뀐 넓이 m² |', '|---|---|---|---|---|---|---|---|---|---|---|---|']
    L = hdr; seen = set()
    for r in RM:
        if not show(r): continue
        has = r.get('found_imgerr_pct') is not None and np.isfinite(r.get('found_imgerr_pct', np.nan) if r.get('found_imgerr_pct') is not None else np.nan)
        cell = lambda b: f"{f1(r[b + '_pct'])} ({r[b + '_area_m2']:,.0f}, {int(r[b + '_gt_points']):,})"
        if has and (r['prior'], r['surface']) not in seen:
            seen.add((r['prior'], r['surface']))
            L.append(f"| {r['prior']} | {r['surface']} | 분모 (차이가 유의한 패치) | | | | | 영상 깊이 오류 {r['den_found_imgerr_area_m2']:,.0f} m², {int(r['den_found_imgerr_gt_points']):,} 점 | 사전정보 오류 {r['den_wrong_priorerr_area_m2']:,.0f} m², {int(r['den_wrong_priorerr_gt_points']):,} 점 | 두 자료 모두 유효 {r['den_changed_bothvalid_area_m2']:,.0f} m², {int(r['den_changed_bothvalid_gt_points']):,} 점 | | |")
        fl = f"{cell('found_imgerr')} | {cell('wrong_priorerr')} | {cell('changed_bothvalid')} | {f1(r['F_js_pct'])} | {r['changed_area_m2']:,.0f}" if has else ' | | | | '
        L.append(f"| {r['prior']} | {r['surface']} | {r['line']} | " + ' / '.join(f1(r[f'ok_{CASE[c]}']) for c in CASES) + f" · {f1(r['ok_전체'])} | {f1(r['ok_네 경우 평균'])} · {f1(r['ok_최솟값'])} · {f1(r['ok_최대 격차'])} | "
                 + ' / '.join(f1(r[f'patch_ok_{CASE[c]}']) for c in CASES) + f" · {f1(r['patch_ok_전체'])} | {f1(r['patch_ok_네 경우 평균'])} · {f1(r['patch_ok_최솟값'])} · {f1(r['patch_ok_최대 격차'])} | {fl} |")
    L += ['', '## 구조 상한을 넘는 줄', '']
    if not OVER: L.append('없음(점·패치 단위 모두, 표의 모든 면).')
    else:
        L += ['| 사전 정보 | 면 | 줄 | 점: 그 줄 · 상한 | 패치: 그 줄 · 상한 |', '|---|---|---|---|---|'] + [f"| {o['prior']} | {o['surface']} | {o['line']} | {o['point_value']:.2f} · {o['point_upper']:.2f} | {o['patch_value']:.2f} · {o['patch_upper']:.2f} |" for o in OVER]
        for (pr, sn, ln), g in pd.DataFrame(DET).groupby(['prior', 'surface', 'line'], sort=False):
            L += ['', f'### {pr} {sn} · {ln} 대 구조 상한 — 패치 넓이 (처음 상태 x 판정, m²)', '', '| 처음 상태 | 판정 | 상한 | 그 줄 |', '|---|---|---|---|']
            for _, r in g[g.table == '패치 넓이'].iterrows(): L.append(f"| {r.state} | {r.judgment} | {r.upper_area_m2:,.1f} | {r.line_area_m2:,.1f} |")
            L += ['', '| 처음 상태(점) | 판정 | 상한: 점 · 맞음 | 그 줄: 점 · 맞음 |', '|---|---|---|---|']
            for _, r in g[g.table == '점'].iterrows(): L.append(f"| {r.state} | {r.judgment} | {int(r.upper_points):,} · {int(r.upper_ok):,} | {int(r.line_points):,} · {int(r.line_ok):,} |")
    L += ['', '## 검산', ''] + [f"- {c['check']} ({c.get('prior', '')} {c.get('surface', '')}): " + json.dumps(jsafe({k: v for k, v in c.items() if k not in ('check', 'prior', 'surface', 'rows')}), ensure_ascii=False) for c in CK]
    (DOCT/'t11_combo.md').write_text('\n'.join(L) + '\n')
    # t11_combo_photo
    SN = [STATE[s] for s in STATE_ORDER]
    L = ['# t11_combo_photo', '', '덧붙임 3 2.2절. 광도 결과 = JUDGECHECK-v2 본값 판이 패치에 낸 결과(판정 표 차례 그대로). 반박 = s_P < t 이고 s_M ≥ t(사진이 영상 깊이 면을 지지), 지지 = s_P ≥ t 이고 s_M < t(사진이 사전 정보 면을 지지), 나머지 여섯 = 구별 불가. 조각 부족 = 발주의 \'표본 부족\'. 셈 안 함 줄에 저장되지 않은 패치를 함께 넣음(수는 검산에 적음).', '', 'scientific_verdict: null', '',
         '## 1. 차이가 유의한 패치 × 광도 결과, 처음 상태마다', '', '칸 = 넓이 m² (참값 점 수) · 그 가운데 A2 되돌림 넓이 %.', '',
         '| 사전 정보 | 면 | 광도 결과 | 모두 | ' + ' | '.join(SN) + ' |', '|---|---|---|---|' + '---|'*len(SN)]
    pp = lambda v: '—' if not np.isfinite(v) else f'{v:.1f}'
    for r in PH:
        if not show(r): continue
        L.append(f"| {r['prior']} | {r['surface']} | {r['photo']} | {r['area_m2']:,.0f} ({r['gt_points']:,}) · {pp(r['A2_returned_pct'])} | " + ' | '.join(f"{r[s + '_m2']:,.0f} ({r[s + '_gt']:,}) · {pp(r[s + '_A2_returned_pct'])}" for s in SN) + ' |')
    for title, R in [('2. 판 나에서 구제된 패치(A2 되돌림이었으나 광도 결과 반박이라 그대로 둠)', RS), ('3. 판 다에서 추가된 패치(A2 는 통과였으나 광도 결과 지지라 되돌림)', AD)]:
        L += ['', f'## {title}', '', '칸 = 넓이 m² (참값 점 수) / 그 처음 상태의 차이가 유의한 넓이. 사전정보 오류 칸과 영상 깊이 오류 칸을 나란히 둠.', '',
              '| 사전 정보 | 면 | 모두 | 사전정보 오류 | 영상 깊이 오류 | 두 자료 모두 유효 | 영상 깊이 결측 | 네 경우 밖 |', '|---|---|---|---|---|---|---|---|']
        for r in R:
            if not show(r): continue
            L.append(f"| {r['prior']} | {r['surface']} | {r['area_m2']:,.0f} ({r['gt_points']:,}) | " + ' | '.join(f"{r[s + '_m2']:,.0f} ({r[s + '_gt']:,}) / {r[s + '_den_m2']:,.0f}" for s in [CASE[1], CASE[2], CASE[0], CASE[4], STATE[3]]) + ' |')
    L += ['', '## 4. 자리마다 판 가·다', '', '칸 = % (바뀐 넓이 m², 참값 점 수). 분모 = 그 자리의 차이가 유의한 패치 가운데 그 처음 상태.', '',
          '| 사전 정보 | 면 | 자리 | 분모: 영상 오류 / 사전 오류 / 유효 (m², 점) | 가 찾은 | 가 잘못 되돌린 | 가 유효 바뀜 | 다 찾은 | 다 잘못 되돌린 | 다 유효 바뀜 |', '|---|---|---|---|---|---|---|---|---|---|']
    for r in PLC:
        if not show(r): continue
        c_ = lambda k, nm: f"{pp(r[f'{k}_{nm}_pct'])} ({r[f'{k}_{nm}_m2']:,.0f}, {r[f'{k}_{nm}_gt']:,})"
        L.append(f"| {r['prior']} | {r['surface']} | {r['place']} | {r['den_found_m2']:,.0f} ({r['den_found_gt']:,}) / {r['den_wrong_m2']:,.0f} ({r['den_wrong_gt']:,}) / {r['den_bothvalid_m2']:,.0f} ({r['den_bothvalid_gt']:,}) | "
                 + ' | '.join(c_(k, nm) for k in ['ga', 'da'] for nm in ['found', 'wrong', 'bothvalid']) + ' |')
    L += ['', '## 5. 검산 2 둘째: JUDGECHECK-v2 확인 3 과 같은 정의', '', '정의 = 참값 점(네 경우, 짝 있음), 본값 기하 한계 밖 또는 u_M 없는 패치, 점의 경우마다 광도 결과 비율(%). 이 셈 / c3_photo_by_case(무늬 모두·모든 자리).', '',
          '| 사전 정보 | 경우 | 점 수 이 셈 / c3 | ' + ' | '.join(PCODE[k] for k in PCODE) + ' |', '|---|---|---|' + '---|'*len(PCODE)]
    for c in CK:
        if not c['check'].startswith('검산 2 둘째'): continue
        for r in c['rows']: L.append(f"| {r['prior']} | {r['case']} | {r['n_here']:,} / {r['n_c3']:,} | " + ' | '.join(f"{r[PCODE[k]]:.2f} / {r[PCODE[k] + '_c3']:.2f}" for k in PCODE) + ' |')
        L.append(f"| {c['prior']} | 가장 큰 차 | | {c['max_abs_diff_pct']:.4f} %p |" + ' |'*(len(PCODE) - 1))
    (DOCT/'t11_combo_photo.md').write_text('\n'.join(L) + '\n')

def figs_mode(prior):
    """덧붙임 3 3절. 짜임은 fig10_* 와 같음(mf8.examples, c 세 색). 참값은 표시에만."""
    import mf8_figs as F8, mf16_addendum2 as M16
    import matplotlib.pyplot as plt
    T = Timer(); S, d0, sig, lo0, flipA2, pres, stored, F, ck = base3(prior); A = S['A']; pc = S['pc']
    a2 = M16.a2more(prior, d0); frac = a2['c_ge5_frac']; cols = M16.base(prior)[5]; dev = cols['gt_mvs_dist_median_m']
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'tiles', 'centre', 'normal', 'tangent1', 'prior_height_m', 'mvs_mean_m', 'building', 'place', 'kind', 'area'])
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gid', 'case', 'paired', 'gt_kind']); Z = np.load(MC.JS/prior/'fig_arrays.npz'); assert np.array_equal(Z['pc'], pc)
    jd = MC.O/'judge'/prior; Pn = dict(np.load(jd/'patch_none.npz')); Pn['mean'] = d['mvs_mean_m']; Pm = dict(np.load(jd/'patch_A2.npz')); Pm['mean'] = F8.load_mean(prior, 'A2', d)
    sP, sM = d0['s_P'], d0['s_M']
    def xlab(i, bname):
        dv = dev[i]; s_ = lambda v: '—' if not np.isfinite(v) else f'{v:.2f}'
        return (f"{bname} · {PLACE.get(int(d['place'][i]), '')} · c≥5 비율 {frac[i]:.2f} · 광도 {PCODE[int(pres[i])]} · s_P {s_(sP[i])} · s_M {s_(sM[i])} · 참값 거리 " + ('—' if not np.isfinite(dv) else f"{dv:+.2f} m"))
    F8.COLOR_C = True; rescued = sig & flipA2 & ~F['na']; added = sig & F['da'] & ~flipA2
    p_add = F8.groups(added & (pc == 2), d, A, n=4); used = {str(d['building'][m[0]]) for _, m, _ in p_add}
    SETS = [('fig11_rescued', F8.groups(rescued & (pc == 1), d, A, n=6), '판 나에서 구제된 사전정보 오류(맞게 구제: A2 되돌림이었으나 광도 결과 반박이라 그대로)', '넓은 모임 차례, 한 건물에 하나'),
            ('fig11_rescued_wrong', F8.groups(rescued & (pc == 2), d, A, n=6), '판 나에서 구제된 영상 깊이 오류(잘못 구제)', '넓은 모임 차례, 한 건물에 하나; 여섯에 못 미치면 있는 만큼'),
            ('fig11_added', p_add + F8.groups(added & (pc == 1), d, A, n=2, exclude=used), '판 다에서 추가로 되돌림 — 앞 = 찾은 영상 깊이 오류, 뒤 = 잘못 되돌린 사전정보 오류', '영상 깊이 오류 넷 + 사전정보 오류 둘, 넓은 모임 차례, 그림 전체에서 한 건물에 하나; 모자라면 있는 만큼')]
    meta_all = {}
    for name, pick, title, rule in SETS:
        if not pick:
            fig = plt.figure(figsize=(6, 1.2)); fig.text(.5, .5, f'{PN[prior]}: 해당 패치 없음', ha='center', va='center', fontsize=9); J3.save(fig, f'{name}_{prior}', dict(prior=prior, rule=rule, groups=[], note='해당 패치 없음')); meta_all[name] = 0; continue
        fig, meta = F8.examples(prior, 'A2', 'image', d, g, Z, Pn, Pm, f"{PN[prior]} · {title} — 단면의 영상 깊이 점을 c(일치 시점 수, 자기 포함)로 칠함", pick=pick, xlab=xlab)
        for mm_, (cc, mem, area) in zip(meta, pick):
            i = mm_['section_patch_gid']; mm_.update(place=PLACE.get(int(d['place'][i]), ''), c_ge5_frac=float(frac[i]), photo_result=PCODE[int(pres[i])], s_P=float(sP[i]), s_M=float(sM[i]), gt_mvs_dist_median_m=float(dev[i]),
                                                     initial_state=STATE.get(int(pc[i]), ''), A2_returned=bool(flipA2[i]), combo_D_returned=bool(F['da'][i]))
        J3.save(fig, f'{name}_{prior}', dict(prior=prior, rule=rule, colors={lab: col_ for _, col_, lab in F8.C_COL}, groups=meta)); meta_all[name] = len(meta)
    F8.COLOR_C = False
    # fig11_points: fig8_check_curve 에 판 나·다·라(와 참고 판 다″)의 점을 더함
    pn, sn = (PN[prior], '모두' if prior == 'LoD2' else '지붕'); RF = pd.read_csv(DOCT/'t8_check_curve.csv'); RMd = pd.read_csv(DOCT/'t8_check_mode.csv'); C11 = pd.read_csv(DOCT/'t11_combo.csv')
    RF = RF[(RF.prior == pn) & (RF.surface == sn)]; RMd = RMd[(RMd.prior == pn) & (RMd.surface == sn) & (RMd['mode'] == '점 4개 미만')]; C11 = C11[(C11.prior == pn) & (C11.surface == sn)]
    B = pd.read_csv(Path('/repo/docs/experiments/phd/main_judgestruct_v1/tables/t14_boundary.csv')); fig, axs = plt.subplots(1, 2, figsize=(11, 4.6)); meta = dict(prior=prior, surface=sn, curves=[], points=[])
    FM = [m for m in RF.method.unique() if not str(m).startswith('A2d')]
    MK = {'na': ('D', '#e41a1c', '판 나 (A2 + 구제, 세션 판)'), 'da': ('*', '#984ea3', '판 다 (A2 + 구제 + 추가, 세션 판)'), 'ra': ('^', '#ff7f00', '판 라 (사진 대조만)'), 'dapp': ('P', '#777777', '참고 판 다″ (세션 값 0.1·0.3)')}
    for ax, xk, xl in [(axs[0], 'wrong_priorerr_pct', '잘못 되돌린 비율 % (사전정보 오류 넓이 가운데)'), (axs[1], 'F_js_pct', 'F % (JUDGESTRUCT 셈 1-4 분모: 영상 깊이 오류가 아닌 유의 넓이)')]:
        for k, m in enumerate(FM):
            rr = RF[RF.method == m].sort_values('threshold'); col = plt.get_cmap('tab10')(k); ax.plot(rr[xk], rr['found_imgerr_pct'], '-o', ms=3, color=col, lw=.8, label=MC.MNAME[m])
            for _, r in rr.iterrows(): ax.annotate(f"{r['threshold']:g}", (r[xk], r['found_imgerr_pct']), fontsize=5, color=col, xytext=(2, 2), textcoords='offset points')
            pt = RMd[RMd.method == m]
            if len(pt): ax.plot([pt.iloc[0][xk]], [pt.iloc[0]['found_imgerr_pct']], 's', ms=6, mfc='none', color=col)
            if xk == 'wrong_priorerr_pct': meta['curves'].append(dict(method=m, curve=rr[['threshold', 'found_imgerr_pct', 'wrong_priorerr_pct', 'F_js_pct']].to_dict('records')))
        for key, (mk, col, lab) in MK.items():
            r = C11[C11.panel == key].iloc[0]; ax.plot([r[xk]], [r['found_imgerr_pct']], mk, ms=8 if mk == '*' else 6, color=col, mec='k', mew=.4, label=lab, zorder=5)
            if xk == 'wrong_priorerr_pct': meta['points'].append(dict(panel=key, label=lab, found=float(r['found_imgerr_pct']), wrong=float(r['wrong_priorerr_pct']), F_js=float(r['F_js_pct']), bothvalid=float(r['changed_bothvalid_pct'])))
        if xk == 'F_js_pct':
            bb = B[(B.prior == prior) & (B.surface == sn) & (B.unit == '점')].sort_values('F'); ax.plot(100*bb.F.values, 100*bb.R_total_exact.values, 'k--', lw=1, label='JS 셈 1-4 경계 (전체 목표 맞음 > 본 방법, 점)')
        ax.set_xlabel(xl, fontsize=7); ax.set_ylabel('찾은 비율 % (영상 깊이 오류 넓이 가운데)', fontsize=7); ax.set_xlim(left=0); ax.set_ylim(0, 100); ax.tick_params(labelsize=6)
    axs[0].legend(fontsize=5.5, frameon=False, loc='lower right'); axs[1].legend(fontsize=5.5, frameon=False, loc='lower right')
    fig.suptitle(f'{pn} {sn}: 판 점검의 곡선(fig8 과 같음) + 판 나·다·라·참고 판 다″의 점 — 네모 = 점 4개 미만 규칙(판 가 = A2 네모)', fontsize=8); fig.tight_layout(rect=[0, 0, 1, .95])
    J3.save(fig, f'fig11_points_{prior}', meta); meta_all['fig11_points'] = len(meta['points'])
    print('FIGS3', prior, json.dumps(meta_all), round(T.s()), flush=True); MC.progress(f'mf18 figs {prior}(덧붙임 3 3절) 끝, {round(T.s())} 초')

def rates_mode():
    """대조 뒤 채움: 본 방법·구조 하한·구조 상한 줄의 '찾은·잘못 되돌린·유효 바뀜'. 정의 = 차이가 유의한 패치 가운데 그 줄의 판정이 사전정보 사용(1)인 넓이 비율(판 가~다와 같은 분모·같은 셈 flip_rates).
    본 방법 판정 = JUDGECHECK-v2 본값 판 j_region(method), 구조 상한 = JUDGESTRUCT-v1 fig_arrays up, 구조 하한 = 지금 점군 하한(유의 패치는 모두 영상 깊이 사용이라 0)."""
    T = Timer(); R = []; mi = J.VARIANTS.index('method')
    for prior in ['LoD2', 'ALS']:
        S = M11.setup(prior); d = S['d']; b = np.load(MC.O/'judge'/prior/'patch_none.npz'); sig = b['sig']; up = np.load(MC.JS/prior/'fig_arrays.npz')['up']
        for lab, j in [('본 방법 (JUDGECHECK-v2 본값 판정)', d['j_region'][:, mi]), ('구조 하한 (지금 점군)', b['lo']), ('구조 상한 (지금, 참값으로)', up)]:
            for fr in flip_rates(S, prior, sig, sig & (j == 1)): R.append(dict(prior=PN[prior], line=lab, **fr))
    pd.DataFrame(R).to_csv(DOCT/'t11_combo_line_rates.csv', index=False); dump(DOCT/'t11_combo_line_rates.json', dict(rows=json.loads(pd.DataFrame(R).to_json(orient='records', force_ascii=False)), note=rates_mode.__doc__, scientific_verdict=None))
    show = lambda r: (r['prior'] == 'LoD2') or (r['surface'] == '지붕')
    cell = lambda r, b: f"{f1(r[b + '_pct'])} ({r[b + '_area_m2']:,.0f}, {int(r[b + '_gt_points']):,})"
    L = ['', '## 본 방법·구조 하한·구조 상한 줄의 찾은·잘못 되돌린 비율 (대조 뒤 채움)', '', '정의 = 차이가 유의한 패치 가운데 그 줄의 판정이 사전정보 사용인 넓이 비율(판 가~다와 같은 분모). 본 방법 판정 = JUDGECHECK-v2 본값 판 j_region(method), 구조 상한 = JUDGESTRUCT-v1 fig_arrays `up`. 위 표의 목표 맞음 값은 바뀌지 않음.', '',
         '| 사전 정보 | 면 | 줄 | 찾은 % (m², 점) | 잘못 되돌린 % (m², 점) | 유효 바뀜 % (m², 점) | F(JS) % | 사전정보 사용 넓이 m² |', '|---|---|---|---|---|---|---|---|']
    for r in R:
        if show(r): L.append(f"| {r['prior']} | {r['surface']} | {r['line']} | {cell(r, 'found_imgerr')} | {cell(r, 'wrong_priorerr')} | {cell(r, 'changed_bothvalid')} | {f1(r['F_js_pct'])} | {r['changed_area_m2']:,.0f} |")
    t = (DOCT/'t11_combo.md').read_text(); k = t.find('\n## 본 방법·구조 하한'); t = t if k < 0 else t[:k + 1]
    (DOCT/'t11_combo.md').write_text(t.rstrip('\n') + '\n' + '\n'.join(L) + '\n')
    for r in R: print('RATES', json.dumps(jsafe({k: r[k] for k in ['prior', 'surface', 'line', 'found_imgerr_pct', 'wrong_priorerr_pct', 'changed_bothvalid_pct']}), ensure_ascii=False), flush=True)
    MC.progress(f'mf18 rates(덧붙임 3 대조 뒤 채움) 끝, {round(T.s())} 초')

if __name__ == '__main__':
    MC.cfg()
    {'tables': lambda: tables_mode(), 'rates': lambda: rates_mode(), 'figs': lambda: figs_mode(sys.argv[2])}[sys.argv[1]]()
