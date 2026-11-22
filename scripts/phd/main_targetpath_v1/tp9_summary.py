"""Writes /docs/목표전달셈_요약.md from the tables (orders 2-4; order 5 is appended when its table exists) and /docs/관찰.md (hand-written,
facts only). usage: tp9_summary.py. Cells with fewer than 1,000 GT points show counts only (ratio cells '·')."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
VS = ['가려지지 않은 영상(10 m 규칙)', '바깥쪽 모든 영상']
RUNS = {RUN_KO['ft']: '본 방법', RUN_KO['gtt']: '참값 목표'}

def rd(name):
    p = D/'tables'/f'{name}.csv'
    return list(csv.DictReader(p.open())) if p.exists() else []
def f(v, d=1, pctv=False):
    if v in (None, ''): return '·'
    x = float(v); x = x*100 if pctv else x
    return f'{x:.{d}f}'
def md(head, rows): return '\n'.join(['| '+' | '.join(head)+' |', '|'+'---|'*len(head)]+['| '+' | '.join(r)+' |' for r in rows])

def main():
    S = rd('tp_supervision'); out = [f'# 목표 전달 셈 요약 (PHD-MAIN-TARGETPATH-v1)', '',
        f'- 만든 때: {now()}. 학습하지 않았다. 저장된 모델·목표 지도·점 자료를 읽기만 했다(GPU 쓰지 않음). `scientific_verdict`: null.',
        '- 판은 둘이다. **본 방법** = FINALTRAIN-v1 30,000회, **참값 목표** = GTTARGET-v1 씨앗 0, 30,000회(진단용, B173 주변 × LoD2는 학습 결과 없음).',
        '- 무리: 가 = 영상 깊이 면이 틀리고 사전 정보 면이 맞으며 본 방법의 목표가 맞는 참값 점(잃음 / 지킴), 나 = 사전 정보가 틀리고 영상이 맞으며 본 방법의 목표가 틀린 참값 점(고침 / 고치지 못함), 대조 = 두 자료 모두 맞고 목표가 맞는 점.',
        '- 참값 점이 1,000개에 못 미치는 칸은 비율을 싣지 않았다(·). 그 칸의 수는 `tables/*.csv`에 있다. 정의는 `issues.md`.', '']
    out += ['## 1. 화소가 받은 감독 (2절)', '',
            '점마다 그 점을 바깥쪽에서 보는 학습 영상의 화소가 받은 깊이 목표를 다섯 종류로 나눈 뒤, 점마다의 비율의 **중앙값(%)**. '
            '종류 1 = 소유 조각이 있고 목표가 점의 τ 안, 2 = 소유 조각이 있고 τ 넘게 앞, 3 = 소유 조각 없이 영상 깊이 목표, 4 = 소유 조각이 있고 τ 넘게 뒤, 5 = 무게 0. '
            '"1>½" = 종류 1이 본 영상의 절반 넘는 점의 비율(%), "2+3>½" 같은 뜻. "가린 감독" = 가려진 화소(10 m 규칙)에서 종류 1~4의 감독을 받은 쌍의 비율(%). w는 무게 중앙값.', '']
    for vs in VS:
        out += [f'### 1.{VS.index(vs)+1} {vs}', '']
        rows = []
        for r in S:
            if r['view_set'] != vs or r['point_region'] != '전체': continue
            rows.append([r['stem'], RUNS[r['run']], r['group'], r['points']]+[f(r[f'kind{i}_share_median'], 0, True) for i in range(1, 6)]+
                        [f(r['kind1_half_pct']), f(r['kind23_half_pct']), f(r['occ10_supervised_pct']) if vs == VS[1] else '', f(r['w_median_kind1'], 2), f(r['w_median_kind23'], 2)])
        out += [md(['장면', '판', '무리', '점', '1', '2', '3', '4', '5', '1>½', '2+3>½', '가린 감독', 'w(1)', 'w(2·3)'], rows), '']
    C = rd('tp_cross')
    out += ['### 1.3 교차표 (무리 가): 본 방법 판의 주된 종류 × 참값 목표 판에서 지킴·잃음', '',
            '같은 점, 같은 영상. 주된 종류 = 점의 본 영상에서 가장 많은 종류. 참값 목표 판의 무리는 그 판의 목표가 맞고 결과도 맞으면 지킴, 목표가 맞는데 결과가 틀리면 잃음.', '']
    for vs in VS:
        rows = [[r['stem'], r['group'], r['method_main_kind'], r['points'], r['gtt_kept'], r['gtt_lost'], r['gtt_target_outside'], f(r['gtt_lost_pct'])] for r in C if r['view_set'] == vs and int(r['gtt_no_run']) == 0]
        out += [f'**{vs}**', '', md(['장면', '본 방법 무리', '본 방법의 주된 종류', '점', '참값 목표 판 지킴', '참값 목표 판 잃음', '참값 목표 판 목표 밖', '잃음 %'], rows), '']
    Wr = rd('tp_wrong')
    out += ['### 1.4 무리 나: 고친 점과 고치지 못한 점에 걸린 틀린 목표(종류 2·4)', '', md(['장면', '무리', '점', '틀린 목표 쌍', '쌍 비율 %', 'w 중앙', 'w 사분위', '벗어난 크기(τ배) 중앙', '사분위', 'w=10 %', 'w=0.1 %'],
            [[r['stem'], r['group'], r['points'], r['wrong_target_pairs'], f(r['wrong_target_pairs_pct']), f(r['w_median'], 2), r['w_q25_q75'], f(r['offset_tau_median']), r['offset_tau_q25_q75'], f(r['w10_pct'], 2), f(r['w01_pct'], 2)] for r in Wr]), '']
    T = rd('tp_weight'); TP = rd('tp_weight_pairs')
    out += ['## 2. 화소 무게의 자리 (3절)', '', '실제 무게 식은 **clip(σ_ref ÷ σ, 0.1, 10)** 이다(제곱 아님, `issues.md` 1). σ_ref는 장면마다 값 하나다.', '',
            md(['장면', '판', '영상', '식', 'σ_ref (m)', '목표 화소 평균 무게(영상별 최소/중앙/최대)', '일치 w=10 % / 0.1 % / 평균', '보존', '보정', '결측', '영상 깊이 목표'],
               [[r['stem'], RUNS[r['run']], r['views'], r['weight_formula'], f(r['sigma_ref_median'], 4), f"{f(r['target_mean_weight_view_min'], 2)} / {f(r['target_mean_weight_view_median'], 2)} / {f(r['target_mean_weight_view_max'], 2)}"]+
                [f"{f(r[f'{k}_w10_pct'], 2)} / {f(r[f'{k}_w01_pct'], 2)} / {f(r[f'{k}_w_mean'], 2)}" for k in ['일치', '보존', '보정', '결측', '영상 깊이 목표']] for r in T]), '',
            '점 자리(본 방법 판, 바깥쪽 모든 영상)의 종류 1 화소 무게:', '',
            md(['장면', '무리', '점', '종류 1 쌍', 'w=10 쌍', 'w=0.1 쌍', 'w=10 %', 'w=0.1 %', 'w 중앙'],
               [[r['stem'], r['group'], r['points'], r['kind1_pairs'], r['kind1_w10_n'], r['kind1_w01_n'], f(r['kind1_w10_pct'], 2), f(r['kind1_w01_pct'], 2), f(r['kind1_w_median'], 2)] for r in TP]), '']
    F = rd('tp_front'); FO = rd('tp_front_other'); HT = rd('tp_height'); SF = rd('tp_seed_fate'); TR = rd('tp_track')
    out += ['## 3. 면을 누가 그리나 (4절)', '', '점을 바깥쪽에서 보는 영상의 그 화소에서 무게가 가장 큰 가우시안(1위)의 종류·자리. CPU에서 2DGS 합성을 다시 셌다(저장된 렌더 깊이와 중앙 차 1 mm 안, `checks.json`).', '',
            md(['영상', '장면', '판', '무리', '점', '쌍', '같은 목표 %', '다른 목표 %', '해제 %', '제약 없음 %', '앞 %', 'τ 안 %', '뒤 %', '불투명도', '긴 축 (m)'],
               [[r['view_set'][:6], r['stem'], RUNS[r['run']], r['group'], r['points'], r['pairs']]+[f(r[f'top1_{k}_pct']) for k in GKIND+POS3]+[f(r['top1_opacity_median'], 2), f(r['top1_size_median_m'], 2)] for r in F]), '',
            '1위가 다른 목표에 위치 제약된 가우시안일 때, 그 목표의 판단 영역과 목표가 맞는지(본 방법 판):', '',
            md(['영상', '장면', '무리', '점', '가우시안 수(쌍×3 안)', '그 목표가 맞음 %', '일치 %', '보존 %', '보정 %', '결측 %'],
               [[r['view_set'][:6], r['stem'], r['group'], r['points'], r['other_target_splats'], f(r['other_target_right_pct']), f(r.get('other_region_일치_pct')), f(r.get('other_region_보존_pct')), f(r.get('other_region_보정_pct')), f(r.get('other_region_결측_pct'))] for r in FO if r['run'] == RUN_KO['ft']]), '',
            '무리 가: 1위 가우시안 중심 높이가 점에서 수평 1~3 m 안의 참값 면 높이와 τ 안에서 같은 쌍의 비율(양옆 면이 이어져 걸친 것인지 보기 위함):', '',
            md(['영상', '장면', '무리', '점', '본 방법 %', '본 방법 쌍', '참값 목표 %', '참값 목표 쌍'], [[r['view_set'][:6], r['stem'], r['group'], r['points'], f(r.get('ft_height_match_pct')), r.get('ft_pairs', ''), f(r.get('gtt_height_match_pct')), r.get('gtt_pairs', '')] for r in HT]), '',
            '무리 나: 점의 (틀린) 목표 조각에 처음 놓인 씨앗의 30,000회 자리. 점마다 가장 앞선 자리(구간 안 > 같은 목표 구간 밖 > 재할당 > 해제 > 그 밖 > 제거)의 점 수:', '',
            md(['장면', '무리', '점', '씨앗 있는 점', '씨앗']+['구간 안', '같은 목표 구간 밖', '재할당', '해제', '그 밖', '제거'],
               [[r['stem'], r['group'], r['points'], r['points_with_seeds'], r['seeds']]+[r[f'point_best_{k}_n'] for k in ['조각 허용 구간 안', '같은 목표, 구간 밖', '다른 목표로 재할당', '제약 해제', '그 밖(제약 없음)', '제거']] for r in SF]), '',
            'R1 × 항공 LiDAR: 점의 목표 조각에 위치 제약된 가우시안이 나간 길(학습 기록 판 = 같은 처방을 다시 학습하며 장면 전체를 13번 저장한 판; FINALTRAIN 모델 자체가 아니다):', '',
            md(['무리', '점', '추적된 점', '나감', '해제 %', '재할당 %', '재설정 뒤 제거 %', '그 밖의 제거 %', '분할로 대체 %', '30,000회까지 빈 조각 %', '처음 빈 반복(중앙)'],
               [[r['group'], r['points'], r['points_with_track'], r['exits'], f(r['exit_제약 해제_pct']), f(r['exit_재할당_pct']), f(r['exit_재설정 뒤 제거_pct']), f(r['exit_그 밖의 제거_pct']), f(r['exit_분할로 대체_pct']), f(r['empty_by_30000_pct']), f(r['first_empty_iteration_median'], 0)] for r in TR]), '']
    FL = rd('tp_fill')
    if FL: out += ['## 4. 보지 못하는 곳에 목표 면 채우기 (5절, 모의)', '', (D/'채움_요약.md').read_text() if (D/'채움_요약.md').exists() else '', '']
    obs = D/'관찰.md'
    if obs.exists(): out += [obs.read_text(), '']
    figs = sorted((D/'figures').glob('tp_*.json'))
    if figs:
        out += ['## 그림 (6절)', '', '칸 넷: 사진 / 그 영상의 목표 지도(바탕 = 화소 소유, 점 = 그 영상에서 점의 종류) / 화소 무게 / 단면(참값, 목표 면과 ±1.96σ, 영상 깊이 면, 결과 면, 무게 1위 가우시안 중심). '
                'A = 잃은 점·가려지지 않은 영상에서 종류 2·3이 주된 모임, B = 잃은 점·종류 1이 주된 모임, C = 고친 점의 가장 넓은 모임, D = R1 바닥 띠(본 방법 판과 참값 목표 판, 같은 영상).', '']
        out += [md(['그림', '장면', '본보기', '참값 점', '영상'], [[f'`figures/{json.loads(p.read_text())["figure"]}`', json.loads(p.read_text())['scene'], json.loads(p.read_text())['case'], str(json.loads(p.read_text())['points']), json.loads(p.read_text())['view']] for p in figs]), '']
    ch = json.loads((D/'checks.json').read_text()) if (D/'checks.json').exists() else {}
    out += ['## 점검 (9절)', '', f"- 0절의 대상 점·잃은 점·참값 목표 판에서도 잃는 점: {'모두 같음' if all(v['equal'] for v in ch.get('order0', {}).values()) else '다름 있음'} ({', '.join(STEM_KO[k] + ' ' + str(v['got']) for k, v in ch.get('order0', {}).items())}).",
            f"- 다섯 종류의 합 = 점마다 본 영상 수: {'모두 같음' if all(v['equal'] for v in ch.get('kinds_sum', {}).values()) else '다름 있음'}.",
            f"- 본 방법 판과 참값 목표 판은 같은 점·같은 (점, 영상) 쌍: {ch.get('same_pairs')}.",
            '- CPU 합성 깊이와 저장된 렌더 깊이: ' + '; '.join(f"{k} 중앙 {v['abs_median_m']*1000:.2f} mm, 5 cm 안 {v['within_5cm_pct']} %" for k, v in ch.get('contrib_vs_render', {}).items()), '']
    jobs = [json.loads(l) for l in (O/'logs/jobs.jsonl').read_text().splitlines()]
    agg = {}
    for j in jobs:
        if j['exit_code'] == 0: agg[j['script']] = agg.get(j['script'], 0)+j['seconds']
    out += ['## 실행 시간 (성공한 실행만, 초)', '', md(['스크립트', '합'], [[k, f'{v:.0f}'] for k, v in agg.items()]), '']
    (D/'목표전달셈_요약.md').write_text('\n'.join(out)+'\n'); print('TP9', len(out), flush=True)

if __name__ == '__main__': main()
