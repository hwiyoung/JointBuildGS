"""확인 2 (6.1), 3 (6.2), 4 (6.3) 의 표. 참값은 패치 칸(5 % 확인), 정밀도 확인의 잔차, 경우에만 쓴다."""
from common import *
import pandas as pd
import jc2_judge as J
from s7_tables import write, area, CASE, JUD, MATCH, PLACE
SENS = ['base', 'ring_1.0', 'ring_3.0', 'z_1.645', 'z_2.576', 'centre_shift', 'building_r', 'same_face_ring']
SNAME = {'base': '본값', 'ring_1.0': '고리 1.0 m', 'ring_3.0': '고리 3.0 m', 'z_1.645': '배수 1.645', 'z_2.576': '배수 2.576', 'centre_shift': '가운데 옮김', 'building_r': '건물마다 r', 'same_face_ring': '같은 면 고리'}
PCODE = {0: '지지', 1: '반박', 2: '둘 다 낮음', 3: '둘 다 높음', 4: 'MVS 면 없음', 5: '조각 부족', 6: '무늬 없음', 7: '사진 부족', 9: '셈 안 함'}
def patches(prior, variants):
    tiles_ = [p.stem.split('__')[0] for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz'))]; A = []
    tau = json.loads((O/'stage0/tau.json').read_text())['values']
    for t in tiles_:
        g = loadz(O/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'kind', 'area', 'n', 'd_m', 'prior_height_m', 'mvs_mean_m', 'roof_type', 'building', 'region'])
        e = dict(g); e['place'] = loadz(O/'place'/f'{t}__{prior}.npz', ['place'])['place']; e['textureless'] = loadz(O/'texture'/f'{t}__{prior}.npz', ['textureless'])['textureless']
        gp = O/'truth/gt_patch'/f'{t}__{prior}.npz'; e['gt_p'] = loadz(gp, ['gt_p'])['gt_p'].astype(float) if gp.exists() else np.full(len(g['kind']), np.nan)
        e['tau'] = np.array([tau.get(r, tau['none'])[prior + ('_wall' if k == 2 else '_roof')] for r, k in zip(g['region'], g['kind'])]) if prior == 'LoD2' else np.array([tau.get(r, tau['none'])['ALS_roof'] for r in g['region']])
        for v in variants:
            gv = O/'geometry'/v/f'{t}__{prior}.npz'; jv = O/'judge'/v/f'{t}__{prior}.npz'
            if not (gv.exists() and jv.exists()): continue
            c = loadz(gv, ['u_M', 'sigma_P', 'sigma_W', 'r_m', 'L_m', 'geometry', 'd_for_check']); j = loadz(jv, ['region', 'reason', 'photo_code', 's_P', 's_M', 'photo_point'])
            for k, x in c.items(): e[f'{v}:{k}'] = x
            e[f'{v}:region'] = j['region'][J.VARIANTS.index('method')]; e[f'{v}:reason'] = j['reason'][J.VARIANTS.index('method')]; e[f'{v}:photo_code'] = j['photo_code']
            if v == 'base': e['s_P'] = j['s_P']; e['s_M'] = j['s_M']; e['region_all'] = j['region']; e['reason_all'] = j['reason']
        A.append(e)
    keys = set.intersection(*[set(a) for a in A])
    return {k: np.concatenate([a[k] for a in A], axis=1 if k in ('region_all', 'reason_all') else 0) for k in keys}
def five_percent(prior, P, variants):
    rows = []; ok = (P['n'] >= 4) & np.isfinite(P['gt_p']) & np.isfinite(P['prior_height_m']) & np.isfinite(P['mvs_mean_m'])
    cell0 = ok & (np.abs(P['prior_height_m'] - P['gt_p']) <= P['tau']) & (np.abs(P['mvs_mean_m'] - P['gt_p']) <= P['tau'])
    for v in variants:
        if f'{v}:L_m' not in P: continue
        root = np.sqrt(P[f'{v}:u_M']**2 + P[f'{v}:sigma_P']**2 + P[f'{v}:sigma_W']**2); dd = P[f'{v}:d_for_check']
        cen = v == 'centre_shift'; zs = {'z_1.645': [1.645], 'z_2.576': [2.576]}.get(v, [1.645, 1.96, 2.576])
        for kn, km in ([('지붕', P['kind'] == 1), ('벽', P['kind'] == 2)] if prior == 'LoD2' else [('지붕', P['kind'] == 1)]):
            for pn, pm in [('모든 자리', np.ones(len(P['n']), bool))] + [(PLACE[k], P['place'] == k) for k in PLACE]:
                m = cell0 & km & pm & np.isfinite(root); a = float(P['area'][m].sum())
                for z in zs:
                    L = z*root if cen else z*(root + np.abs(P[f'{v}:r_m'])); out = m & (np.abs(dd) > L)
                    rows.append(dict(prior=prior, variant=SNAME[v], surface=kn, place=pn, z=z, nominal_pct={1.645: 10, 1.96: 5, 2.576: 1}[z], cell0_area_m2=a, outside_area_m2=float(P['area'][out].sum()), outside_pct=100*float(P['area'][out].sum())/a if a else np.nan, cell0_patches=int(m.sum())))
    return pd.DataFrame(rows)
def precision(prior, P):
    rows = []; sw = P['base:sigma_W']
    def add(name, res, mask, pm_name):
        x = res[mask & np.isfinite(res)]
        rows.append(dict(prior=prior, data=name, place=pm_name, n=len(x), median=float(np.median(x)) if len(x) else np.nan, nmad_after_median=float(1.4826*np.median(np.abs(x - np.median(x)))) if len(x) else np.nan, nominal=1.0))
    for pn, pm in [('모든 자리', np.ones(len(P['n']), bool))] + [(PLACE[k], P['place'] == k) for k in PLACE]:
        mv = (P['n'] >= 4) & pm
        for kn, km in ([('지붕', P['kind'] == 1), ('벽', P['kind'] == 2)] if prior == 'LoD2' else [('지붕', P['kind'] == 1)]):
            add(f'MVS sqrt(u_M^2+σ_W^2) {kn}', (P['mvs_mean_m'] - P['gt_p'])/np.sqrt(P['base:u_M']**2 + sw**2), mv & km, pn)
        if prior == 'ALS':
            add('ALS σ_P', (P['prior_height_m'] - P['gt_p'])/P['base:sigma_P'], pm, pn); add('ALS sqrt(σ_P^2+σ_W^2)', (P['prior_height_m'] - P['gt_p'])/np.sqrt(P['base:sigma_P']**2 + sw**2), pm, pn)
        else:
            for rt in sorted(set(P['roof_type'][P['kind'] == 1])): add(f'LoD2 지붕 {rt}', (0 - P['gt_p'])/P['base:sigma_P'], pm & (P['kind'] == 1) & (P['roof_type'] == rt), pn)
            add('LoD2 벽', (0 - P['gt_p'])/P['base:sigma_P'], pm & (P['kind'] == 2), pn)
    return pd.DataFrame(rows)
def sensitivity(prior, P, d, variants):
    rows = []; base = P['base:region']
    for v in variants:
        if f'{v}:region' not in P: continue
        r = P[f'{v}:region']; ch = r != base
        for pn, pm in [('모든 자리', np.ones(len(base), bool))] + [(PLACE[k], P['place'] == k) for k in PLACE]:
            m = ch & pm; tr = {f'{JUD[int(a)]}→{JUD[int(b)]}': float(P['area'][m & (base == a) & (r == b)].sum()) for a in JUD for b in JUD if a != b and (m & (base == a) & (r == b)).any()}
            rows.append(dict(prior=prior, variant=SNAME[v], place=pn, kind='패치', changed_area_m2=float(P['area'][m].sum()), area_m2=float(P['area'][pm].sum()), transitions=json.dumps(tr, ensure_ascii=False)))
        key = 'sens_' + v + '_target_ok'; rk = 'sens_' + v + '_region'
        for pn, pm in [('모든 자리', np.ones(len(d['src']), bool))] + [(PLACE[k], d['place'] == k) for k in PLACE]:
            for c in [0, 1, 2, 4]:
                m = d['paired'] & pm & (d['case'] == c); n = int(m.sum())
                if v == 'base': ok = d['target_ok_v'][J.VARIANTS.index('method')][m]; nm = d['region_v'][J.VARIANTS.index('method')][m] == MATCH[c]
                elif key in d: ok = d[key][m]; nm = d[rk][m] == MATCH[c]
                else: continue
                rows.append(dict(prior=prior, variant=SNAME[v], place=pn, kind='참값 점', case=CASE[c], n=n, target_ok_pct=100*float(ok.mean()) if n else np.nan, name_ok_pct=100*float(nm.mean()) if n else np.nan))
    for pn, pm in [('모든 자리', np.ones(len(d['src']), bool))] + [(PLACE[k], d['place'] == k) for k in PLACE]:
        for c in [0, 1, 2, 4]:
            m = d['paired'] & pm & (d['case'] == c) & (d['src'] == 1) & (d['current_region'] >= 0); n = int(m.sum())
            rows.append(dict(prior=prior, variant='세 지역 지금 판', place=pn, kind='참값 점(세 지역)', case=CASE[c], n=n, target_ok_pct=100*float(d['current_target_ok'][m].mean()) if n else np.nan, name_ok_pct=100*float((d['current_region'][m] == MATCH[c]).mean()) if n else np.nan))
    return pd.DataFrame(rows)
def gt_patch_cols(d, P, prior, keys):
    look = {s: i for i, s in enumerate(P['patch_id'])}; gi = np.array([look.get(s, -1) for s in d['patch_id']]); ok = gi >= 0
    out = {}
    for k in keys:
        a = P[k]; z = np.full(len(gi), np.nan if a.dtype.kind == 'f' else -1, a.dtype if a.dtype.kind != 'f' else float); z[ok] = a[gi[ok]]; out[k] = z
    return out, ok
def photo_checks(prior, d, P):
    rows = []; q = []; cols, ok = gt_patch_cols(d, P, prior, ['base:geometry', 'base:photo_code', 'n', 'base:u_M', 's_P', 's_M']); geom = cols['base:geometry']; pc = cols['base:photo_code']
    nou = (cols['n'] >= 4) & (geom == 9) & ~np.isfinite(cols['base:u_M'])
    tex = np.full(len(d['src']), np.nan); look = {s: i for i, s in enumerate(P['patch_id'])}
    scope = d['paired'] & ok & ((geom == 1) | nou)
    for tn, tm in [('모두', np.ones(len(d['src']), bool)), ('무늬 없음', d['textureless'] == 1), ('무늬 있음', d['textureless'] == 0)]:
        for pn, pm in [('모든 자리', np.ones(len(d['src']), bool))] + [(PLACE[k], d['place'] == k) for k in PLACE]:
            for c in [0, 1, 2, 4]:
                m = scope & tm & pm & (d['case'] == c); n = int(m.sum())
                r = dict(prior=prior, texture=tn, place=pn, case=CASE[c], n=n)
                for k, kn in PCODE.items(): r[kn + '_pct'] = 100*float((pc[m] == k).mean()) if n else np.nan
                rows.append(r)
            base = scope & tm & pm; ref = base & (pc == 1); sup = base & (pc == 0)
            q.append(dict(prior=prior, texture=tn, place=pn, refute_n=int(ref.sum()), refute_prior_error_pct=100*float((d['case'][ref] == 1).mean()) if ref.any() else np.nan, support_n=int(sup.sum()), support_image_error_pct=100*float((d['case'][sup] == 2).mean()) if sup.any() else np.nan))
    return pd.DataFrame(rows), pd.DataFrame(q), cols, scope, nou
def score_dist(prior, d, P):
    """두 점수의 분포: 패치(사진 점 대표)마다, 경우는 패치 다수결."""
    rows = []; look = {s: i for i, s in enumerate(P['patch_id'])}
    tiles_ = [p.stem.split('__')[0] for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz'))]; tex = []
    for t in tiles_:
        grp = loadz(O/'photo_groups'/f'{t}__{prior}.npz', ['patch_point']); Pn = int(grp['patch_point'].max()) + 1; tx = np.full(Pn, np.nan); pp = O/'photo_prepared'/f'{t}.npz'; sc = O/'photo_scores'/t/'scores.npz'
        if pp.exists() and sc.exists():
            q = loadz(pp, ['prior', 'source_index', 'point_id']); s = loadz(sc, ['texture', 'point_id']); m = q['prior'] == prior
            if m.any() and np.array_equal(s['point_id'], q['point_id']): tx[q['source_index'][m]] = np.nanmax(s['texture'][m], 1)
        tex.append(tx[grp['patch_point']])
    TX = np.concatenate(tex); cols, ok = gt_patch_cols(d, P, prior, ['base:geometry', 's_P', 's_M']); gtex = np.full(len(d['src']), np.nan); gi = np.array([look.get(s, -1) for s in d['patch_id']]); gtex[gi >= 0] = TX[gi[gi >= 0]]
    fin = np.isfinite(gtex) & d['paired']; qs = np.nanpercentile(gtex[fin], [25, 50, 75]) if fin.any() else [np.nan]*3
    qi = np.digitize(gtex, qs)
    groups = {'한계 안 두 자료 모두 유효': (cols['base:geometry'] == 0) & (d['case'] == 0), '사전정보 오류': (cols['base:geometry'] == 1) & (d['case'] == 1), '영상 깊이 오류': (cols['base:geometry'] == 1) & (d['case'] == 2)}
    for gn, gm in groups.items():
        for k in range(4):
            m = d['paired'] & gm & fin & (qi == k) & np.isfinite(cols['s_P']) & np.isfinite(cols['s_M']); n = int(m.sum())
            r = dict(prior=prior, case_group=gn, texture_quartile=k+1, texture_bounds=json.dumps([float(x) for x in qs]), n=n)
            for nm, x in [('s_P', cols['s_P'][m]), ('s_M', cols['s_M'][m])]:
                for p in [10, 50, 90]: r[f'{nm}_p{p}'] = float(np.percentile(x, p)) if n else np.nan
            rows.append(r)
    inl = d['paired'] & (cols['base:geometry'] == 0) & np.isfinite(cols['s_P'])
    bh = []
    for tn, tm in [('무늬 없음', d['textureless'] == 1), ('무늬 있음', d['textureless'] == 0)]:
        m = inl & tm; pcc = gt_patch_cols(d, P, prior, ['base:photo_code'])[0]['base:photo_code']
        bh.append(dict(prior=prior, texture=tn, in_limit_n=int(m.sum()), both_high_pct=100*float((pcc[m] == 3).mean()) if m.any() else np.nan))
    return pd.DataFrame(rows), pd.DataFrame(bh)
def error_rules(prior, d, P, cols, nou):
    pc = cols['base:photo_code']; geom = cols['base:geometry']; mi = J.VARIANTS.index('method'); reg = d['region_v'][mi]; why = d['reason_v'][mi]
    four = d['paired'] & np.isin(d['case'], [0, 1, 2, 4]); match = np.array([MATCH.get(int(c), -9) for c in d['case']]); name_wrong = four & (reg != match); tgt_wrong = ~d['target_ok_v'][mi]
    rule = np.full(len(d['src']), '', dtype='<U40')
    rule[(geom == 0) & (reg == 0)] = '한계 안 일치'; rule[why == 1] = '반박'; rule[why == 0] = '지지'
    dm = why == 2
    for k, kn in PCODE.items(): rule[dm & (pc == k)] = f'기본 판정: {kn}'
    rule[nou] = 'u_M 없음'; rule[np.isin(reg, [3, 4])] = '가시성 검사'; rule[reg == 9] = '미판정'
    mixed = d['patch_majority_case'] != d['case']
    rows = []
    for gn, gm in [('전체', np.ones(len(d['src']), bool)), ('세 실험 지역', d['group'] == 'experiment'), ('나머지', d['group'] == 'rest')]:
        for pn, pm in [('모든 자리', np.ones(len(d['src']), bool))] + [(PLACE[k], d['place'] == k) for k in PLACE]:
            for c in [0, 1, 2, 4]:
                base = four & gm & pm & (d['case'] == c); te = base & name_wrong & tgt_wrong; nt = base & name_wrong & ~tgt_wrong
                for rn in sorted(set(rule[base & name_wrong])):
                    m = te & (rule == rn); m2 = nt & (rule == rn)
                    rows.append(dict(prior=prior, group=gn, place=pn, case=CASE[c], rule=rn, case_n=int(base.sum()), true_error_n=int(m.sum()), true_error_pct_of_case=100*m.sum()/max(base.sum(), 1), true_error_mixed_patch_n=int((m & mixed).sum()), name_wrong_target_ok_n=int(m2.sum())))
    # 기본 판정의 원리 점검: 기본 판정 패치(reason 2)의 참값 점에서 사전정보 오류 / (사전정보 오류 + 영상 깊이 오류)
    pr = []; dflt = d['paired'] & (why == 2) & np.isin(reg, [1, 2]); outL = d['paired'] & ((geom == 1) | nou)
    cols2, _ = gt_patch_cols(d, P, prior, ['roof_type'])
    def ratio(m):
        a = int((m & (d['case'] == 1)).sum()); b = int((m & (d['case'] == 2)).sum()); return a, b, (100*a/(a + b) if a + b else np.nan)
    for scope_name, sm in [('기본 판정 패치', dflt), ('한계 밖 패치 전체', outL)]:
        splits = [('전체', '', np.ones(len(d['src']), bool))]
        splits += [('지붕·벽', 'wall' if k == 2 else 'roof', d['patch_kind'] == k) for k in ([1, 2] if prior == 'LoD2' else [1])]
        splits += [('지붕 형태', str(rt), (d['patch_kind'] == 1) & (d['roof_type'] == rt)) for rt in sorted(set(d['roof_type'][d['paired'] & (d['patch_kind'] == 1)]))]
        splits += [('무늬', {1: '무늬 없음', 0: '무늬 있음', -1: '확인 불가'}[t], d['textureless'] == t) for t in [1, 0, -1]]
        splits += [('자리', PLACE[k], d['place'] == k) for k in PLACE] + [('구별 불가의 종류', PCODE[k], pc == k) for k in [2, 3, 4, 5, 6, 7, 9]]
        for sname, sval, mm in splits:
            a, b, r = ratio(sm & mm); pr.append(dict(prior=prior, scope=scope_name, split=sname, value=sval, prior_error_n=a, image_error_n=b, prior_wrong_share_pct=r))
    bd = []
    for bld in sorted(set(d['building'][dflt])):
        a, b, r = ratio(dflt & (d['building'] == bld)); bd.append(dict(prior=prior, building=bld, group=d['group'][d['building'] == bld][0], prior_error_n=a, image_error_n=b, prior_wrong_share_pct=r))
    return pd.DataFrame(rows), pd.DataFrame(pr), pd.DataFrame(bd)
def misalignment():
    c = json.loads((O/'calib/base.json').read_text()); sw = c['sigma_W_m']; rows = [dict(r, beyond_2sigma_W=abs(r['residual_m']) > 2*sw) for r in c['building_rows'] if r['agreement_count'] >= 100]
    return pd.DataFrame(rows), sw
def main():
    cfg(); T = Timer(); allv = [v for v in SENS if (O/'judge'/f'{v}.json').exists()]
    F5 = []; PR = []; SE = []; PH1 = []; PH2 = []; SD = []; BH = []; ER = []; PRN = []; BDN = []
    for prior in (sys.argv[1:] or ['LoD2', 'ALS']):
        d = loadz(O/'analysis'/f'gt_{prior}.npz'); P = patches(prior, allv)
        F5.append(five_percent(prior, P, allv)); PR.append(precision(prior, P)); SE.append(sensitivity(prior, P, d, allv))
        a, b, cols, scope, nou = photo_checks(prior, d, P); PH1.append(a); PH2.append(b)
        s1, s2 = score_dist(prior, d, P); SD.append(s1); BH.append(s2)
        e1, e2, e3 = error_rules(prior, d, P, cols, nou); ER.append(e1); PRN.append(e2); BDN.append(e3)
        print('CHECKS', prior, round(T.mark(prior)), flush=True)
    cat = lambda L: pd.concat(L, ignore_index=True)
    write('c2_five_percent', cat(F5), note='확인 2: 패치 칸 0(두 자료 모두 유효, 패치 참값의 자리와 τ) 넓이 가운데 한계 밖 비율. 명목 10/5/1 %.', md_rows=lambda x: x[(x.variant == '본값') & (x.place == '모든 자리')], md_cols=['prior', 'surface', 'z', 'nominal_pct', 'cell0_area_m2', 'outside_pct'])
    write('c2_precision', cat(PR), note='확인 2: (자료 높이 - 참값의 자리) / 정밀도 의 중앙값을 뺀 NMAD (명목 1).', md_rows=lambda x: x[x.place == '모든 자리'], md_cols=['prior', 'data', 'n', 'median', 'nmad_after_median'])
    mis, sw = misalignment(); write('c2_building_misalignment', mis, note=f'건물마다 일치하는 곳의 d 중앙값 - 탐색 지역 r. 2σ_W = {2*sw:.4f} m 넘는 건물 표시.', md_rows=lambda x: x[x.beyond_2sigma_W].sort_values('residual_m'), md_cols=['building', 'prior', 'kind', 'region', 'agreement_count', 'residual_m'])
    write('c2_sensitivity', cat(SE), note='확인 2 민감도: 판마다 경우별 목표 맞음·판정 이름 맞음(참값 점), 본값과 판정이 달라진 넓이와 바뀐 방향(패치).', md_rows=lambda x: x[(x.place == '모든 자리') & (x.kind != '패치')], md_cols=['prior', 'variant', 'case', 'n', 'target_ok_pct', 'name_ok_pct'])
    write('c3_photo_by_case', cat(PH1), note='확인 3: 본값 한계 밖·u_M 없는 패치의 참값 점, 경우 x 광도 결과(줄 안 비율).', md_rows=lambda x: x[(x.texture == '모두') & (x.place == '모든 자리')])
    write('c3_photo_correct', cat(PH2), note='확인 3: 반박 가운데 사전정보 오류 비율, 지지 가운데 영상 깊이 오류 비율.', md_rows=lambda x: x[x.place == '모든 자리'])
    write('c3_score_distribution', cat(SD), note='확인 3: 두 점수의 10·50·90 % 값 (무늬 세기 = 두 조각 무늬 세기의 큰 값, 사분위 구간).', md_cols=['prior', 'case_group', 'texture_quartile', 'n', 's_P_p10', 's_P_p50', 's_P_p90', 's_M_p10', 's_M_p50', 's_M_p90'])
    write('c3_both_high_in_limit', cat(BH), note='확인 3: 한계 안 참값 점에서 광도 결과 둘 다 높음 비율.')
    write('c4_error_rules', cat(ER), note='확인 4: 진짜 판정 오류(이름이 맞는 짝과 다르고 목표도 τ 밖)를 생긴 규칙으로 나눔. 패치 안 경우 섞임은 따로 셈.', md_rows=lambda x: x[(x.group == '전체') & (x.place == '모든 자리')].sort_values('true_error_n', ascending=False).head(24),
          md_cols=['prior', 'case', 'rule', 'case_n', 'true_error_n', 'true_error_pct_of_case', 'true_error_mixed_patch_n', 'name_wrong_target_ok_n'])
    write('c4_default_principle', cat(PRN), note='확인 4: 기본 판정 패치(와 한계 밖 패치 전체)에서 사전 정보가 틀린 비율 = 사전정보 오류 / (사전정보 오류 + 영상 깊이 오류), 참값 점 수 기준.')
    write('c4_default_principle_buildings', cat(BDN), note='건물마다의 같은 비율.', md_rows=lambda x: x.head(0))
    dump(O/'analysis/checks.json', dict(at=now(), variants=allv, seconds=T.mark('end'), scientific_verdict=None))
if __name__ == '__main__': main()
