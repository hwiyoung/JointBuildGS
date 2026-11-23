"""Order-intent verification (CPU, read-only on results). usage: tp12_verify.py
Independent re-count from the source files (WT points, pairs, contrib, fill) against the delivered tables, and a checklist of every
item of orders 1-9. Writes /docs/검증_v1.json (machine) and prints a summary. Nothing else is written."""
import sys, csv, zipfile, hashlib
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *

RES = []
def chk(sec, item, ok, detail=''):
    RES.append(dict(section=sec, item=item, ok=(None if ok is None else bool(ok)), detail=str(detail)[:600])); print('CHK', sec, 'OK ' if ok else ('-- ' if ok is None else 'NG '), item, '|', str(detail)[:300], flush=True)

def rows(name): return list(csv.DictReader(open(D/'tables'/f'{name}.csv', encoding='utf-8')))
def f(x): return None if x in ('', None) else float(x)

def main():
    SUP = rows('tp_supervision'); CR = rows('tp_cross'); WR = rows('tp_wrong'); WT_ = rows('tp_weight'); WP = rows('tp_weight_pairs')
    FR = rows('tp_front'); FO = rows('tp_front_other'); HT = rows('tp_height'); SF = rows('tp_seed_fate'); TR = rows('tp_track'); FL = rows('tp_fill')
    # ---- order 1: groups re-picked independently from the WT point files
    for si, stem in enumerate(STEMS):
        w = loadz(WT/'points'/f'wt_{stem}.npz', ['group', 'method_target_ok', 'case_id', 'point_id']); g = w['group']; ok = w['method_target_ok']; c = w['case_id']
        conds = [(c == 2) & ok & (g == 1), (c == 2) & ok & (g == 0), (c == 1) & ~ok & (g == 2), (c == 1) & ~ok & (g == 3), (c == 0) & ok & (g == 1), (c == 0) & ok & (g == 0)]
        caps = [10**9, 5000, 5000, 5000, 5000, 5000]
        P = loadz(O/'points'/f'sel_{stem}.npz', ['group', 'point_id']); bad = []
        for k in range(6):
            want = min(int(conds[k].sum()), caps[k]); got = int((P['group'] == k).sum())
            inside = np.isin(P['point_id'][P['group'] == k], w['point_id'][conds[k]]).all()
            if want != got or not inside: bad.append((GRP[k], want, got, bool(inside)))
        chk('1', f'점 무리 크기·조건 {STEM_KO[stem]}', not bad, bad or {GRP[k]: int((P['group'] == k).sum()) for k in range(6)})
    chk('1', '참값 목표 판 다섯 장면', all((O/'pairs'/f'gtt_{s}.npz').exists() == (s != 'B173nb_b10__LoD2') for s in STEMS), 'B173 주변 × LoD2만 없음')
    # ---- order 2: re-count kinds from pairs, compare with tp_supervision (전체 rows)
    for stem in STEMS:
        P = loadz(O/'points'/f'sel_{stem}.npz', ['group', 'tau']); n = len(P['group'])
        for run in ['ft', 'gtt']:
            p = O/'pairs'/f'{run}_{stem}.npz'
            if not p.exists(): continue
            z = loadz(p, ['pt', 'kind', 'w', 'occ10', 'view'])
            for vs, m0 in [('바깥쪽 모든 영상', np.ones(len(z['pt']), bool)), ('가려지지 않은 영상(10 m 규칙)', ~z['occ10'])]:
                pt = z['pt'][m0]; k = z['kind'][m0]; cnt = np.zeros((n, 5), 'i8'); np.add.at(cnt, (pt, k), 1); nv = cnt.sum(1)
                views = np.zeros(n, 'i8'); np.add.at(views, pt, 1)
                # each (point, view) once
                key = z['pt'][m0].astype('i8')*100000+z['view'][m0].astype('i8'); uniq = len(np.unique(key)) == len(key)
                mism = []
                for gi in range(6):
                    sel = (P['group'] == gi) & (nv > 0); npts = int(sel.sum())
                    r = [x for x in SUP if x['stem'] == STEM_KO[stem] and x['run'] == RUN_KO[run] and x['view_set'] == vs and x['group'] == GRP[gi] and x['point_region'] == '전체']
                    if len(r) != 1: mism.append((GRP[gi], 'row', len(r))); continue
                    r = r[0]
                    if int(r['points']) != npts: mism.append((GRP[gi], 'points', r['points'], npts))
                    fr = cnt[sel]/nv[sel][:, None]
                    k1h = int((fr[:, 0] > .5).sum())
                    if int(r['kind1_half_n']) != k1h: mism.append((GRP[gi], 'k1half', r['kind1_half_n'], k1h))
                    if npts >= 1000:
                        for i in range(5):
                            a = f(r[f'kind{i+1}_share_median']); b = float(np.median(fr[:, i]))
                            if a is None or abs(a-b) > 1e-3 and abs(a-100*b) > 0.06: mism.append((GRP[gi], f'k{i+1}med', a, round(b, 4)))
                    else:
                        if any(f(r[c_]) is not None for c_ in r if c_.endswith('_pct') or 'share' in c_): mism.append((GRP[gi], '1000규칙 위반'))
                chk('2', f'다섯 종류 다시 셈 {STEM_KO[stem]} {run} {vs}', not mism and uniq and (nv == views).all(), mism or 'points·k1half·중앙값 같음, 종류 합 = 본 영상 수, (점, 영상) 겹침 없음')
    # same pairs in both runs
    for stem in STEMS:
        a, b = O/'pairs'/f'ft_{stem}.npz', O/'pairs'/f'gtt_{stem}.npz'
        if not b.exists(): continue
        za = loadz(a, ['pt', 'view', 'px', 'py']); zb = loadz(b, ['pt', 'view', 'px', 'py'])
        same = all(np.array_equal(za[k], zb[k]) for k in za)
        chk('2', f'두 판 같은 (점, 영상, 화소) {STEM_KO[stem]}', same, len(za['pt']))
    # required columns per order 2 bullets
    need = ['kind1_share_median', 'kind1_share_q25', 'kind1_share_q75', 'kind1_half_pct', 'kind23_half_pct', 'occ10_supervised_pct', 'occ1_supervised_pct', 'w_median_kind1', 'w_median_kind23',
            'kind2_target_ok_pct', 'kind2_region_일치_pct', 'kind3_앞_pct', 'kind3_τ 안_pct', 'kind3_뒤_pct', 'kind4_region_보존_pct', 'render_앞_pct', 'render_τ 안_pct', 'render_뒤_pct']
    chk('2', '2절 열(사분위, 절반 넘는 점, 가린 감독, w, 종류 2 판단 영역·맞음, 종류 3 앞·안·뒤, 종류 4 영역, 그린 깊이)', all(c_ in SUP[0] for c_ in need), [c_ for c_ in need if c_ not in SUP[0]])
    regs = sorted({r['point_region'] for r in SUP}); chk('2', '판단 영역으로도 나눔', set(regs) >= {'전체', '일치', '보존', '보정', '결측'}, regs)
    big_all = [r for r in SUP if r['view_set'] == '바깥쪽 모든 영상' and r['point_region'] == '전체' and int(r['points']) >= 1000]
    chk('2', '가려진 화소의 감독 값 있음(바깥쪽 모든 영상, 1,000점 이상 칸)', all(f(r['occ10_supervised_pct']) is not None and f(r['occ1_supervised_pct']) is not None for r in big_all), len(big_all))
    # cross table sums
    bad = []
    for stem in STEMS:
        P = loadz(O/'points'/f'sel_{stem}.npz', ['group', 'group_gtt'])
        for vs in ['바깥쪽 모든 영상', '가려지지 않은 영상(10 m 규칙)']:
            for gi in [0, 1]:
                rr = [r for r in CR if r['stem'] == STEM_KO[stem] and r['view_set'] == vs and r['group'] == GRP[gi]]
                tot = sum(int(r['points']) for r in rr); sub = sum(int(r['gtt_kept'])+int(r['gtt_lost'])+int(r['gtt_target_outside'])+int(r['gtt_no_run']) for r in rr)
                if tot != int((P['group'] == gi).sum()) or sub != tot: bad.append((stem, vs, gi, tot, sub))
    chk('2', '교차표 합 = 무리 점 수, 참값 목표 판 네 칸 합 = 점 수', not bad, bad)
    chk('2', '무리 나 틀린 목표 w·벗어난 크기(τ 배수) 표', len(WR) == 12 and all(f(r['offset_tau_median']) is not None and f(r['w_median']) is not None for r in WR if int(r['wrong_target_pairs']) > 0), len(WR))
    # ---- order 3
    ft_w = [r for r in WT_ if r['run'] == RUN_KO['ft']]; gt_w = [r for r in WT_ if r['run'] == RUN_KO['gtt']]
    chk('3', '본 방법 판 여섯 장면·참값 목표 판 다섯 장면', len(ft_w) == 6 and len(gt_w) == 5, (len(ft_w), len(gt_w)))
    chk('3', 'σ_ref 최소·중앙·최대, 영상별 평균 무게', all(f(r['sigma_ref_min']) is not None and f(r['target_mean_weight_view_median']) is not None for r in ft_w), '')
    chk('3', '10·0.1에 걸린 비율(일치·보존·보정·결측·영상 깊이 목표)', all(all(c_ in r for c_ in ['일치_w10_pct', '보존_w01_pct', '보정_w10_pct', '결측_w10_pct', '영상 깊이 목표_w10_pct']) for r in ft_w), '')
    chk('3', '참값 목표 판 무게 모두 1', all(r['all_weights_one'] in ('True', 'true', '1') for r in gt_w), [r['all_weights_one'] for r in gt_w])
    chk('3', '본 방법 판 무게 식 = clip(σ_ref/σ) (발주문 제곱 식과 다름, issues 1)', all(r['weight_formula'] == 'clip(σ_ref/σ, 0.1, 10)' for r in ft_w), {r['stem']: r['weight_formula'] for r in ft_w})
    chk('3', '대상 점 종류 1의 w=10 비율 잃음·지킴', {r['group'] for r in WP} >= {GRP[0], GRP[1]} and len(WP) == 36, len(WP))
    chk('3', '고친 점 틀린 목표 w=10·0.1 비율, 고치지 못함과 나란히', all('w10_pct' in r and 'w01_pct' in r for r in WR) and {r['group'] for r in WR} == {GRP[2], GRP[3]}, '')
    # ---- order 4
    chk('4', '1위~3위 가우시안 종류(top1·top3 무게 합)', all(f'top3w_{k}_pct' in FR[0] for k in GKIND), '')
    need4 = [f'top{k}_{c_}' for k in (1, 2, 3) for c_ in ['앞_pct', '뒤_pct', 'offset_tau_median', 'opacity_median', 'size_median_m']]
    chk('4', '1~3위 가우시안의 거리(앞·뒤), 불투명도, 긴 축', all(c_ in FR[0] for c_ in need4), [c_ for c_ in need4 if c_ not in FR[0]])
    ftg = {(r['stem'], r['group']) for r in FR if r['run'] == RUN_KO['ft']}
    miss = [(STEM_KO[s], g) for s in STEMS for g in [GRP[0], GRP[2]] if (STEM_KO[s], g) not in ftg]
    chk('4', '본 방법 판 잃은 점·고친 점 여섯 장면', not miss, miss)
    chk('4', '다른 목표 제약의 판단 영역·맞음', all(c_ in FO[0] for c_ in ['other_target_right_pct', 'other_region_일치_pct']), '')
    hg = {(r['stem'], r['group']) for r in HT}
    chk('4', '높이 비교 무리 가, 두 판', all(c_ in HT[0] for c_ in ['ft_height_match_pct', 'gtt_height_match_pct']) and all((STEM_KO[s], GRP[0]) in hg for s in STEMS), sorted(hg))
    chk('4', '고친 점 틀린 목표 조각 씨앗의 자리(허용 구간 안·재할당·해제·제거)', all(c_ in SF[0] for c_ in ['seed_조각 허용 구간 안_n', 'seed_다른 목표로 재할당_n', 'seed_제약 해제_n', 'seed_제거_n']), sorted({(r['stem'], r['group']) for r in SF}))
    chk('4', 'R1 × 항공 LiDAR 나간 길(재할당·재설정 뒤 제거·그 밖, 때) 두 무리', {r['group'] for r in TR} >= {GRP[0], GRP[2]} and 'first_empty_iteration_median' in TR[0], [r['group'] for r in TR])
    for stem in STEMS:   # contrib covers the selected points of groups 가 잃음 / 나 고침
        fp = O/'contrib'/f'ft_{stem}_sub.npz'
        if not fp.exists(): fp = O/'contrib'/f'ft_{stem}_all.npz'
        c = loadz(fp, ['pt']); P = loadz(O/'points'/f'sel_{stem}.npz', ['group']); z = loadz(O/'pairs'/f'ft_{stem}.npz', ['pt'])
        need_pts = np.unique(z['pt'][np.isin(P['group'][z['pt']], [0, 2])]); have = np.unique(c['pt'])
        chk('4', f'기여 셈이 잃은 점·고친 점의 모든 쌍을 덮음 {STEM_KO[stem]}', np.isin(need_pts, have).all(), (len(need_pts), len(have)))
    # ---- order 5
    chk('5', '여섯 장면 × 추출 둘 × 채움 셋', len(FL) == 36 and {(r['stem'], r['extraction'], r['fill']) for r in FL}.__len__() == 36, len(FL))
    need5 = ['patches', 'area_m2', 'completeness_before_pct', 'completeness_after_pct', 'accuracy_before_pct', 'accuracy_after_pct', 'filled_area_within_tau_pct', 'wrong_patches', 'wrong_area_m2',
             'wrong_with_fixed_points', 'wrong_with_fixed_area_m2', 'region_일치_area_pct', 'case_둘 다 맞음_after_pct', 'case_사전 정보가 틀린 곳_after_pct', 'case_영상이 틀린 곳_after_pct', 'case_영상 없음_after_pct']
    empty = [(r['stem'], r['extraction'], r['fill'], c_) for r in FL for c_ in need5 if r.get(c_, '') == '' and int(r['patches'] or 0) > 0]
    chk('5', '낼 값 열 모두 있음', all(c_ in FL[0] for c_ in need5) and not empty, empty[:8])
    nanr = [(r['stem'], r['fill'], r['samples_nan']) for r in FL if int(r['samples_nan'] or 0) > 0]
    chk('5', '채운 원반 표본에 NaN 없음(첫 실행의 번호 오류 재발 없음)', not nanr, nanr)
    src = (R/'scripts/phd/main_targetpath_v1/tp10_fill.py').read_text(); sel_part = src.split('# ---- scoring')[0] if '# ---- scoring' in src else None
    chk('5', '채우는 규칙에 참값 안 씀(정적 확인은 아래 수동 점검)', None, '수동 점검 항목')
    for nm in ['fill_floor_band', 'fill_r1_lod2_wall1', 'fill_b0_visible_wall', 'fill_b173_wing']:
        chk('5', f'그림 {nm}', (D/'figures'/f'{nm}.png').exists() and (D/'figures'/f'{nm}.json').exists(), '')
    # ---- order 6
    for s in STEMS:
        for k in 'ABC':
            chk('6', f'그림 tp_{k} {STEM_KO[s]}', (D/'figures'/f'tp_{k}_{s}.png').exists() and (D/'figures'/f'tp_{k}_{s}.json').exists(), '')
    chk('6', '그림 바닥 띠 두 판', (D/'figures'/'tp_D_R1rep_b10__ALS.png').exists(), '')
    # ---- order 8
    for s in STEMS:
        z = loadz(D/'points'/f'tp_{s}.npz'); need8 = ['group', 'ft_kind_views', 'ft_w_median', 'ft_occ10_supervised_views', 'ft_main_gaussian_kind']
        P = loadz(O/'points'/f'sel_{s}.npz', ['group'])
        chk('8', f'points/tp_{s}.npz 열', all(k in z for k in need8) and len(z['group']) == len(P['group']), [k for k in need8 if k not in z])
    summ = (D/'목표전달셈_요약.md').read_text(encoding='utf-8'); i2 = summ.find('## 1. 화소가 받은 감독'); i3 = summ.find('화소 무게');
    chk('8', '요약 맨 앞이 2절 표와 교차표', i2 > 0 and summ.find('교차표') > i2, (i2, summ.find('교차표')))
    for t in ['tp_supervision', 'tp_weight', 'tp_front', 'tp_fill']: chk('8', f'tables/{t}.csv', (D/'tables'/f'{t}.csv').exists(), '')
    zs = sorted((O/'zips').glob('*.zip'))
    for kind in ['_light.zip', '채움_']:
        zz = [p for p in zs if kind in p.name]
        if not zz: chk('8', f'묶음 {kind}', False, 'none'); continue
        zp = zz[-1]; stale = []
        with zipfile.ZipFile(zp) as Z:
            for nm in Z.namelist():
                rel = nm.split('/', 1)[1]; src_ = (R/'scripts/phd/main_targetpath_v1'/rel.split('/', 1)[1]) if rel.startswith('scripts/') else D/rel
                if src_.name in ('tp12_verify.py',): continue
                if not src_.exists() or hashlib.sha256(Z.read(nm)).hexdigest() != hashlib.sha256(src_.read_bytes()).hexdigest(): stale.append(rel)
        chk('8', f'묶음 {zp.name} = 지금 파일', not stale, stale[:10])
    # ---- order 7/9: run log
    jobs = [json.loads(l) for l in (O/'logs/jobs.jsonl').read_text().splitlines() if l.strip()]
    gpu = [j['script'] for j in jobs if 'NVIDIA_VISIBLE_DEVICES=void' not in j['command'] or '--gpus' in j['command']]
    rw = [j['script'] for j in jobs if any(x.endswith(':/art:rw') or x.endswith(':/repo:rw') for x in j['command'])]
    chk('7', f'모든 실행 GPU 없음 ({len(jobs)}회)', not gpu, gpu)
    chk('7', '원자료·저장소는 읽기 전용으로만 붙임', not rw, rw)
    dump(D/'검증_v1.json', dict(at=now(), title=TITLE, checks=RES, ng=[r for r in RES if r['ok'] is False], scientific_verdict=None))
    print('NG', sum(r['ok'] is False for r in RES), 'of', len(RES), flush=True)

if __name__ == '__main__': main()
