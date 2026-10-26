"""First-batch interim, including preservation and absent-surface area explicitly."""
import json
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
    lines=['# 손실 학습 시험 — B173 항공 LiDAR 중간 보고','',
        f"앞 묶음 채점 완료 {len(complete)}/4. 상태 {'COMPLETE' if len(complete)==4 else 'PARTIAL'}. λ=0.0025. scientific_verdict: null.",'',
        '학습과 채점이 없는 칸은 확인 불가로 둔다. 1단계 패치로 센다. 면 없음도 τ 밖이며, 100패치 미만은 표본 부족이다.','',
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
    for p in sorted((DOC/'tables/fates'/SITE).glob('ALS__*.json')):
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
        '이 문서는 측정값만 나란히 둔다. 과학적 판정은 하지 않는다.']
    dest=DOC/'중간보고_v1.md';dest.write_text('\n'.join(lines)+'\n')
    save(DOC/'tables/interim_values.json',dict(paired_patch_rows=paired,side_rows=selected,fates=fates,runtime_status=runtime['status'],scientific_verdict=None))
    figures_ok=figure.exists() and json.loads(figure.with_suffix('.json').read_text())['visual_review']=='PASS'
    status='PASS' if len(complete)==4 and figures_ok and runtime['status']!='STOPPED_PARTIAL' else 'PARTIAL'
    save(OUT/'checks/interim.json',dict(status=status,completed=complete,report_sha256=sha(dest),figure_review_pass=figures_ok,scientific_verdict=None))
    print('interim',status,'completed',len(complete),flush=True)

if __name__=='__main__':main()
