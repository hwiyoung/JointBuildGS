"""First-batch interim, including preservation and absent-surface area explicitly."""
import csv
import json
import math
from pathlib import Path
from inputs import OUT,save,sha

DOC=Path('/docs');SITE='B173nb_b10';PRIOR='ALS'
VARS={'lt_fixgt':('판 1 고정·참값','fixed_gt'),'lt_dyngt':('판 2 다이내믹·참값','dyn_gt'),
    'lt_dynsoft':('판 3 다이내믹·약한 참값','dyn_soft'),'lt_dynnow':('판 4 다이내믹·평균값','dyn_now')}
SUBSETS={'all_0_3':'전체 칸 0~3','cell_0':'다듬기','cell_1':'보정','cell_2':'보존','cell_3':'이중 오류',
    'unexplained':'차가 설명 안 됨','unexplained_cell_1':'설명 안 됨·보정','unexplained_cell_2':'설명 안 됨·보존','cell_4':'MVS 없음·사전 맞음','cell_5':'MVS 없음·사전 틀림'}
def load(name,default=None):
    p=DOC/'tables'/name
    return json.loads(p.read_text()) if p.exists() else default
def fmt(x):return '확인 불가' if x is None else f'{x:.5f}'

def main():
    scores=load('patch_scores_all.json')['rows'];lookup={(r['variant'],r['subset']):r for r in scores if r['site']==SITE and r['prior']==PRIOR}
    runtime=load('runtime.json');complete=[v for v in VARS if (OUT/'runs'/SITE/(v+'_ALS_s0')/'measure_PASS.json').exists()]
    training_complete=[v for v in VARS if (OUT/'runs'/SITE/(v+'_ALS_s0')/'PASS.json').exists()]
    lines=['# 손실 학습 시험 — B173 항공 LiDAR 중간 보고','',
        f"앞 묶음 30,000회 학습 완료 {len(training_complete)}/4, 채점 완료 {len(complete)}/4. 상태 {runtime['status']}. λ=0.0025. scientific_verdict: null.",'',
        '후처리 메시·채점이 없는 값은 확인 불가로 둔다. 학습 완료와 채점 완료를 구분한다. 1단계 패치로 센다. 면 없음도 τ 밖이며, 100패치 미만은 표본 부족이다.','',
        '## 8.1 패치 값: 보존과 면 없음 포함','',
        '| 판 | 범위 | N | 넓이 m² | 학습 없음 τ 안 % | 학습 τ 안 % | 면 없음 m² | 면 없음 % |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    paired=[]
    for var,(label,analytic) in VARS.items():
        for subset,name in SUBSETS.items():
            a=lookup[('analytic_'+analytic,subset)];r=lookup.get((var+'_ALS_s0',subset))
            paired.append(dict(variant=var,subset=subset,analytic=a,trained=r))
            n=a['patches'];name+=(' · 표본 부족' if n<100 else '')
            lines.append(f"| {label} | {name} | {n} | {fmt(a['area_m2'])} | {fmt(a['within_tau_percent'])} | {fmt(r['within_tau_percent'] if r else None)} | {fmt(r['no_surface_area_m2'] if r else None)} | {fmt(r['no_surface_percent'] if r else None)} |")
    lines+=['','기존 비교 결과와 여섯 단위 전체 표: [패치 채점](tables/patch_scores_all.md). 반올림 전 값·분모·출처는 같은 이름의 JSON·CSV.','',
        '## 8.4 지표별 달라짐 문턱','',
        '[이 발주에서 냄]. 아래 씨앗 0·1은 1단계 본 방법 prop_ALS_s0·prop_ALS_s1을 같은 1단계 평가 패치, 바깥에서 처음 만난 면, 같은 τ로 다시 센 값이다. 단위 변동 폭은 2.8 × |씨앗 0 − 씨앗 1| / √2이다. 비율의 값은 %, 문턱은 %p이며 거리 중앙값과 그 문턱은 m이다.','',
        '이 새 패치 지표와 정의가 같은 기존 모은 변동 폭은 없어 자료 없음으로 표시한다. 다른 두 축 지표의 폭을 대신 넣지 않는다. 최댓값은 적용 가능한 값 중 가장 큰 값이다. 300/N은 비율 지표에만 적용하며, 거리 중앙값에는 적용하지 않는다. N이 100 미만이면 표본 부족으로 읽지 않는다.','',
        '| 범위 | 지표 | N | 씨앗 0 | 씨앗 1 | 모은 폭 | 단위 폭 | 300/N | 최댓값 |',
        '|---|---|---:|---:|---:|---|---:|---:|---:|']
    noise_path=DOC/'tables/noise_thresholds.json';noise=load('noise_thresholds.json')['rows']
    thresholds=[]
    metrics={'within_tau_percent':'τ 안 넓이 비율','no_surface_percent':'면 없음 넓이 비율','error_patch_median_m':'참값 거리 중앙값'}
    for subset,name in SUBSETS.items():
        for metric,label in metrics.items():
            if metric=='error_patch_median_m' and subset!='cell_0':continue
            found=[r for r in noise if (r['kind'],r['site'],r['prior'],r['subset'],r['metric'])==('stage1_patch',SITE,PRIOR,subset,metric)]
            assert len(found)==1;row=dict(found[0]);seed_sources=[]
            for seed in [0,1]:
                s=lookup[(f'prop_ALS_s{seed}',subset)]
                assert s[metric]==row[f'seed_{seed}']
                seed_sources.append(dict(result=f'prop_ALS_s{seed}',source=s['source'],sha256=s['source_sha256'],
                    N=s['error_observed_patches'] if metric=='error_patch_median_m' else s['patches']))
            assert row['N']==min(x['N'] for x in seed_sources)
            expected=2.8*abs(row['seed_0']-row['seed_1'])/math.sqrt(2) if row['seed_0'] is not None and row['seed_1'] is not None else None
            assert row['case_spread']==expected
            parts=[row[k] for k in ['pooled','case_spread','three_points'] if row[k] is not None]
            assert row['threshold']==(max(parts) if parts else None)
            row.update(seed_sources=seed_sources,value_unit='m' if metric=='error_patch_median_m' else '%',
                threshold_unit='m' if metric=='error_patch_median_m' else '%p',
                three_points_status='not applicable to distance' if metric=='error_patch_median_m' else 'available' if row['N'] else 'N=0',
                sample_status='표본 부족' if row['N']<100 else 'PASS')
            thresholds.append(row)
            number=lambda x:'확인 불가' if x is None else f'{x:.9f}'
            pooled=number(row['pooled']) if row['pooled'] is not None else '자료 없음'
            three='적용 없음' if metric=='error_patch_median_m' else number(row['three_points'])
            scope=name+(' · 표본 부족' if row['N']<100 else '')
            lines.append(f"| {scope} | {label} | {row['N']} | {number(row['seed_0'])} | {number(row['seed_1'])} | {pooled} | {number(row['case_spread'])} | {three} | {number(row['threshold'])} |")
    threshold_note=dict(formula='max(available pooled spread, 2.8*abs(prop_s0-prop_s1)/sqrt(2), 300/N for percentage metrics)',
        source=str(noise_path),source_sha256=sha(noise_path),same_stage1_patch_scoring=True,scientific_verdict=None)
    save(DOC/'tables/interim_thresholds.json',dict(rows=thresholds,**threshold_note))
    with (DOC/'tables/interim_thresholds.csv').open('w') as f:
        flat=[{**r,'seed_sources':json.dumps(r['seed_sources'],ensure_ascii=False)} for r in thresholds]
        writer=csv.DictWriter(f,list(flat[0]),lineterminator='\n');writer.writeheader();writer.writerows(flat)
    distance_row=next(r for r in thresholds if r['metric']=='error_patch_median_m')
    lines+=['',f"비율의 N은 같은 평가 패치 수다. 거리 중앙값은 면을 만난 패치만 사용했다(씨앗 0 N={distance_row['seed_sources'][0]['N']}, 씨앗 1 N={distance_row['seed_sources'][1]['N']}); 위 표의 N은 두 수의 최솟값이다. 거리에 300/N을 쓰지는 않는다.",'',
        '차이의 절댓값이 최댓값의 두 배를 넘을 때만 수치 차이 확인, 최댓값 초과부터 두 배 이하는 가능·근거 불완전이다. 새 학습 면이 없으면 차이 구간은 확인 불가다. 반올림 전 문턱과 두 씨앗의 패치 파일·SHA-256은 [문턱 기록](tables/interim_thresholds.json)과 같은 이름 CSV에 있다.','',
        '## 8.2 도착점과 같은 쪽','',
        '| 판 | 범위 | N | 넓이 m² | 같은 쪽 % |','|---|---|---:|---:|---:|']
    sides=load('sides_all.json',{'rows':[]})['rows'];selected=[r for r in sides if r['site']==SITE and r['prior']==PRIOR]
    seen=set()
    for r in selected:
        key=(r['variant'],r['subset'])
        if key in seen:continue
        seen.add(key);lines.append(f"| {VARS[r['variant']][0]} | {SUBSETS[r['subset']]} | {r['denominator_patches']} | {fmt(r['denominator_area_m2'])} | {fmt(r['same_side_percent'])} |")
    if not selected:lines.append('| 학습 채점 미완료 | 확인 불가 | — | — | — |')
    lines+=['','전체 넓이 교차표: [쪽 교차표](tables/sides_all.md).','',
        '## 8.5 심긴 점의 운명','',
        '| 결과 | 참값 칸 | 심긴 N | 지워짐 % | 옛 자리 % | 지금 면 % | 둘 다 아님 % |',
        '|---|---|---:|---:|---:|---:|---:|']
    fates=[]
    for p in sorted(list((DOC/'tables/fates'/SITE).glob('ALS__*.json'))+list((DOC/'tables/fate_cell_split'/SITE).glob('ALS__*.json'))):
        r=json.loads(p.read_text());fates.append(r)
        for key,g in r['regions'].items():
            vals=[fmt(None if g['shares'][k] is None else 100*g['shares'][k]) for k in ['removed','old_place','current_surface','neither']]
            lines.append(f"| {r['result']} | {key} | {g['seeds_planted']} | "+' | '.join(vals)+' |')
    lines+=['','## 추가 불투명도와 PSNR 기록','',
        '새 시점별 표와 저장 모델 15,000·30,000회의 nojudge 비교: [관측 표](tables/monitor_v2_observations.md). 과거 생성 표식이나 해당 시점 기록이 없으면 기록 없음이다. nojudge는 재학습하지 않았다.','',
        '판 1의 이미 실행된 부분은 남은 로그·모델에서 복구했다. 새 PSNR 중단 비교는 같은 다섯 영상의 7,000·15,000·30,000회만 사용한다. 전체 학습 영상 PSNR과 평가 영상 지표는 [사진 표](tables/photo.md)에 별도 표시한다.','',
        '## B173 날개 단면','']
    figure=DOC/'figures/section_B173nb_b10_ALS_0.png'
    if figure.exists():lines+=['![B173 날개 단면](figures/'+figure.name+')','']
    else:lines+=['확인 불가: 새 학습의 후처리 메시와 패치 채점이 아직 없다. 고정한 단면 시작 (146.68, 96.32), 끝 (136.63, 99.34), 폭 ±0.6 m는 그대로다.','']
    lines+=['## 바꾼 것과 중단 기록','',
        '패치 연결 대신 직접 규칙, 불투명도 기록 전용 전환, 전체 붕괴·세 시점 PSNR 기준, 과거 누락 처리 등 사용자 승인 변경은 본 보고서와 provenance/monitor_v2_approval.json에 있다. 5 cm·18 cm 연결 실패, 3,001회 초기화 직후 중단 두 건, 9,100회 사전 불투명도 중단은 기록으로 보존한다. 추가 기록 코드의 카메라 이름 충돌은 최적화 0회에 중단되어 수정·검증했으며 별도 중단 보고에 남겼다.','',
        '판 1의 이전 TSDF 두 시도는 호스트 메모리 부족으로 종료됐다. 이후 사용자 승인에 따라 후처리 자원 중단은 학습 중단에서 제외하고, 64 GiB 이상 60초의 시작 조건·48 GiB 한도에서 재개한다. 같은 조건의 자원 부족은 최초 시도 뒤 최대 두 번 재시도한다. 판 1·2는 재학습하지 않고 저장 모델을 쓴다. 판 3·4 뒤 나머지 20회 학습은 채점과 독립적으로 이어 간다. 이전 중단의 근거는 [후처리 중단 보고](중단보고_후처리메모리_v1.md)에 보존했다. 칸 0·칸 2 운명은 기존 0·2 묶음의 점별 분류를 나눴으며 두 칸의 합이 원래 수와 같은지 확인했다.','',
        '요청에 따라 8.1 지표 21행의 문턱 세 항과 최댓값, 두 씨앗 값·N·출처를 8.4에 추가했다. 두 패치별 결과 배열에서 직접 재계산한 검증의 최대 차이는 0이다. 거리에는 300/N을 적용하지 않고, 없는 기존 모은 변동 폭은 다른 지표에서 대신 가져오지 않았다.','',
        '이 문서는 측정값만 나란히 둔다. 과학적 판정은 하지 않는다.']
    dest=DOC/'중간보고_v1.md';dest.write_text('\n'.join(lines)+'\n')
    (DOC/'tables/interim_thresholds.md').write_text('\n'.join(lines[lines.index('## 8.4 지표별 달라짐 문턱'):lines.index('## 8.2 도착점과 같은 쪽')])+'\n')
    save(DOC/'tables/interim_values.json',dict(paired_patch_rows=paired,threshold_rows=thresholds,side_rows=selected,fates=fates,runtime_status=runtime['status'],scientific_verdict=None))
    figures_ok=figure.exists() and json.loads(figure.with_suffix('.json').read_text())['visual_review']=='PASS'
    status='PASS' if len(complete)==4 and figures_ok and runtime['status']!='STOPPED_PARTIAL' else 'PARTIAL'
    save(OUT/'checks/interim.json',dict(status=status,completed=complete,report_sha256=sha(dest),figure_review_pass=figures_ok,scientific_verdict=None))
    print('interim',status,'completed',len(complete),flush=True)

if __name__=='__main__':main()
