"""Complete the ordered report using recorded r2 gate and diagnostic evidence."""
import re
import numpy as np
from common import *
from report_stage0 import plt,save,read,SITES

def main():
    cfg,lock=locked_r2();state=read(OUT/'r2/stage1_status.json');failed=state['status']=='STOP_STAGE1_INITIAL_RENDER_DEPTH'
    report=DOC/'영역별목표학습_보고_r2.md';text=report.read_text()
    parts=re.split(r'^## [1-8]\. [^\n]+\n',text,flags=re.M);assert len(parts)==9
    rows=[]
    for p in sorted((OUT/'r2/diagnose').glob('*/diagnosis.json')):
        d=read(p)
        for row in d['rows']:
            prioronly=row['decomposition']['prior_only']
            rows.append(dict(site=d['site'],prior=d['prior'],representative=row['representative'],
                full_prior_median_m=row['strata']['prior']['error']['quantiles'][2],
                prior_only_median_m=prioronly['prior_error']['quantiles'][2],
                full_on_identical_pixels_median_m=prioronly['full_error_on_same_pixels']['quantiles'][2],
                prior_only_valid_pixels=prioronly['prior_error']['count'],prior_only_coverage=prioronly['prior_depth_coverage'],
                plane_control_median_m=row['analytic_plane_control']['quantiles'][2],
                normal_max_error=d['quaternion_normal_max_error'],largest_disk=d['largest_initial_disk']))
    dump(DOC/'tables/r2_stage1_diagnosis.json',dict(rows=rows,scientific_verdict=None))
    diagnostic=[]
    if rows:
        fig,axes=plt.subplots(1,2,figsize=(12,4.3));x=np.arange(len(rows));names=[f"자리 {r['representative']} {r['prior']}" for r in rows]
        axes[0].bar(x-.16,[r['full_on_identical_pixels_median_m'] for r in rows],width=.32,label='전체 초기 장면',color='#438bb6')
        axes[0].bar(x+.16,[r['prior_only_median_m'] for r in rows],width=.32,label='진단: 사전 씨앗만',color='#d59d3c')
        axes[0].axhline(.05,ls='--',color='black');axes[0].set(ylabel='깊이 절대 오차 중앙값 (m)',title='두 렌더가 모두 있는 같은 화소');axes[0].legend(fontsize=8)
        axes[1].bar(x,[100*r['prior_only_coverage'] for r in rows],color='#d59d3c');axes[1].set(ylim=(0,105),ylabel='화소 비율 (%)',title='사전 씨앗만 남겼을 때 깊이 범위')
        for ax in axes:ax.set_xticks(x,names,rotation=25)
        fig.subplots_adjust(top=.79,bottom=.25,wspace=.3)
        save(fig,'r2_stage1_diagnosis','같은 화소에서 전체 장면과 사전 씨앗만의 깊이를 비교했다',rows,
             '학습 없는 원인 진단 · 초기화나 통과 값으로 사용하지 않음 · 오른쪽 분모: 전체 초기 장면의 사전 화소')
        diagnostic=['### 초기 렌더 진단','',
            '합성 카메라 깊이 50 m 평면의 오차 중앙값은 모든 진단에서 1 mm 안이다. 목표 점·법선과 카메라 연결을 별도로 확인했다. 아래의 배경 제외 렌더는 원인 확인용이며 실제 초기화나 5 cm 통과에 사용하지 않았다.','',
            '| 자리·사전 정보 | 전체 장면, 같은 화소 (m) | 사전 씨앗만 (m) | 남은 깊이 화소 (%) |','|---|---:|---:|---:|']
        for r in rows:diagnostic.append(f"| {r['representative']} · {r['prior']} | {r['full_on_identical_pixels_median_m']:.6f} | {r['prior_only_median_m']:.6f} | {100*r['prior_only_coverage']:.2f} |")
        diagnostic+=['','![분해 렌더 진단](figures/r2_stage1_diagnosis.png)','',
            '기준선 렌더는 가우시안 투명도 가중 평균 깊이를 쓴다. 목표 지도는 가장 가까운 원반 깊이를 쓴다. 두 계산은 목표 중심에서 시작하더라도 항상 일치하지 않는다. 남은 오차의 정도는 위 실측으로 구분하며, 5 cm 기준은 바꾸지 않았다.','']
    for p in sorted((OUT/'r2/diagnose').glob('*/background_geometry.json')):
        g=read(p);key=f"{g['site']}_{g['prior']}"
        diagnostic += [f"{SITES[g['site']]} {g['prior']}의 최대 배경 원반은 원본 MVS 신뢰도 {g['source_confidence']:.6g}인 점에서 생겼다. 원본 깊이 {g['source_depth_m']:.6f} m, 초기 크기 {g['gpu_scale_m']:.6f} m다. 가까운 세 점으로 CPU에서 크기를 다시 구한 값은 {g['cpu_nearest_neighbor_scale_m']:.6f} m이며 GPU 값과 일치한다. 법선 없음은 연직 위, u 없음은 같은 단위·면 종류 중앙값으로 처리한 점이다. 사용자 지정 규칙대로 신뢰도 통과 점을 유지했고, 고립점 제외나 크기 제한을 임의로 추가하지 않았다.",
            '',f'![고립 MVS 점의 원본과 초기 크기](figures/r2_background_geometry_{key}.png)','']
    receipts=[]
    for folder in ['preflight_commands','diagnose_commands']:
        for p in sorted((OUT/'r2'/folder).glob('*/receipt.json')):receipts.append(dict(path=str(p.relative_to(OUT)),**read(p)))
    started=dt.datetime.fromisoformat(read(CFG/'target_v1.r2.lock.json')['at']);end=dt.datetime.fromisoformat(stamp())
    timing=dict(started_at=started.isoformat(),as_of=end.isoformat(),elapsed_minutes=(end-started).total_seconds()/60,
        gpu_invocation_receipts=receipts,training_iterations=0,scientific_verdict=None)
    dump(DOC/'tables/r2_stage1_timing.json',timing)
    accuracy=read(DOC/'tables/judgment_accuracy_r2.json')['rows'];short=[]
    for split in ['development','holdout']:
        rs=[r for r in accuracy if r['split']==split and r['prior']=='ALS' and r['kind']==1 and r['replacement']=='all' and r['variant']=='main']
        den=sum(r['denominator_area_m2'] for r in rs);wrong=sum(r['wrong_area_m2'] for r in rs)
        short.append(f'{100*wrong/den:.2f}%')
    stage1=parts[6];repstart=stage1.index('![B173') if '![B173' in stage1 else len(stage1)
    mechanics,repfigures=stage1[:repstart],stage1[repstart:]
    front=['# 영역별 목표 학습 보고 v1 · r2','',
        f'판단 정확도: 항공 LiDAR 지붕의 틀린 넓이 비율은 개발용 {short[0]}, 확인용 {short[1]}. LoD2와 실험 지역·대체 패치의 값은 단계 0 표에 있다.',
        '7,000회 점검: '+('3.5 초기 깊이 기준 미충족으로 미실행. 최적화 0회.' if failed else '3.5 통과. 이어서 실행할 대상이며 아직 결과 없음.'),
        '8판의 네 값: 학습과 메시가 없어 아직 계산하지 않았다.',
        'GS와 목표로 바로 만든 메시 비교: 아직 실행하지 않았다.',
        f'확인 불가: 학습 효과·최종 메시·채점. r2 설정 잠금부터 약 {timing["elapsed_minutes"]:.1f}분. scientific_verdict: null.','',
        '## 1. 현재 상태','', '단계 0 재계산과 독립 점검을 통과했다. '+('단계 1은 초기 렌더 깊이 5 cm 기준에서 중단했다.' if failed else '단계 1의 학습 전 점검을 통과했다.'),
        '결과를 본 뒤 문턱, 면 찾기, 대표 자리, 씨앗 수·크기 규칙을 다시 고르지 않았다. [이 발주에서 냄].','',
        '## 2. 단계 0: 판단과 목표','', '### 설정과 관측 없음 원인',parts[1],'### 둘째 문턱',parts[2],
        '### 영역 넓이와 지도',parts[3],'### 판단 정확도',parts[4],
        '## 3. 단계 1: 구현과 점검','',mechanics,
        '소스 변경과 줄은 [변경 기록](tables/r19_changes_r2.json), [train.py 차이](tables/r19_train_r2.patch)에 있다. 기본 끔 경로는 TARGET 부분을 제거한 구문 트리가 r18과 정확히 같다. 현재 잠금은 `target_v1.stage1.r2.lock.json`이며 코드 110개 파일을 묶었다.','',
        '11/1 결정에 따라 배경도 목표 폭에 묶이므로, 건강 점검의 불투명도 모집단은 모든 목표 씨앗의 자손이다. r1 구현은 사전 씨앗만 셌다. 이 차이를 첫 r2 렌더 전에 기록했고, 0.05 기준은 그대로다. 사전 씨앗만의 중앙값도 별도로 기록하도록 구현했다.','',
        *diagnostic,
        '## 4. 단계 2: 본 학습과 채점','',parts[7],
        '8판의 네 값, 칸·영역별 τ 안 비율, 판단 맞음·틀림 및 폭 안·밖, 결과와 목표, 목표로 바로 만든 메시 비교는 미실행이다. 미실행을 0이나 성공으로 채우지 않았다.','',
        '## 5. 비교 방법','',
        '기존 비교 방법은 다시 학습하지 않았다. 이번 학습 결과가 없으므로 같은 메시 방식의 성능 비교 표를 아직 작성하지 않았다. CDGS의 메모리 보류 상태를 완료로 바꾸지 않았다. 배경 씨앗이 기준선의 SfM 희소점에서 신뢰도 통과 MVS 점으로 바뀐 차이는 단계 1 비교 표에 명시했다.','',
        '## 6. 대표 자리 그림','',parts[5],repfigures,
        '## 7. 미리 정한 물음과 현재 증거','',
        '| 물음 | 현재 증거 |','|---|---|',
        '| 판단이 한 자료만 믿을 때보다 틀린 곳을 줄이는가 | 영역·판단 정확도 표에 본 규칙, 사전 정보만, MVS만의 비교 줄을 함께 기록 |',
        '| 학습이 목표를 따르며 참값에 가까워지는가 | 학습 전이므로 확인 불가 |',
        '| 작은 판단 오류를 학습이 다듬는가 | 학습 전이므로 확인 불가 |',
        '| GS가 목표만으로 만든 메시보다 나은가 | 두 메시가 없어 확인 불가 |',
        '| 비교 방법보다 나은가 | 이번 결과 없음 |',
        '| B173 날개에 뜬 면이 남는가 | r1·r2 목표 단면만 있으며 결과 메시의 뜬 면은 아직 셀 수 없음 |','',
        '## 8. 바꾼 것·출처·확인 불가·시간','',parts[8],
        '새 배경 씨앗은 점마다 자체 고리 불확실도를 구했다. 원반 밖 목표 지도 화소의 불확실도는 r1에 잠근 같은 단위의 지붕 패치 중앙값 대체를 유지하며, 지도 인덱스에 대체로 표시한다. 씨앗의 점별 불확실도와 지도 화소의 대체값을 같은 자료라고 표시하지 않았다.','',
        f'초기 렌더·진단 GPU 호출 시간의 합은 {sum(r["seconds"] for r in receipts if r["exit_code"]==0)/60:.1f}분이다. 병렬 호출이 포함되므로 전체 경과 시간과 다르다. 호출별 값은 [시간 기록](tables/r2_stage1_timing.json)에 있다. 원자료와 r1 잠금·결과·기존 ZIP은 보존했다. 확인용은 수·넓이·비율만 공개하며 상세 패치는 외부 holdout/r2에 둔다.','']
    body='\n'.join(front).replace('과학적 판정','과학적 판단')
    assert len(body)<20000 and len(re.findall(r'^## [1-8]\. ',body,re.M))==8
    report.write_text(body);(DOC/'영역별목표학습_보고_v1.md').write_text(body)
    print('R2_REPORT_FINISHED',len(body),state['status'],flush=True)

if __name__=='__main__':main()
