"""Ordered Korean factual report, less than 20,000 characters."""
import datetime as dt
import json
from pathlib import Path
from lock_config import dump,sha,stamp
from supplement_tables import rows
O=Path('/out');D=Path('/docs');C=Path('/cfg')

def n(v,d=3):return '확인 불가' if v is None else f'{v:,.{d}f}'
def p(v):return '확인 불가' if v is None else f'{100*v:.3f}%'
def prior(v):return '항공 LiDAR' if v=='ALS' else v
def kind(v):return '지붕' if v==1 or v=='roof' else '벽'
def t(v):return '없음' if v is None else f'{v:g} m'
def table(head,items):return ['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,r))+' |' for r in items]
def fig(name,label):return f'![{label}](figures/{name}.png)'

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());cal=json.loads((O/'calibration.json').read_text())['values']
    sample=rows('sample_counts');sel=rows('selected_values');base=[r for r in sel if r['scenario']=='base' and r['group']!='combined']
    scope={v:{'count':max(r['building_count'] for r in sample if r['prior']==v),'cores':sum(r['patch_count'] for r in sample if r['prior']==v),'area':sum(r['area_m2'] for r in sample if r['prior']==v)} for v in ['LoD2','ALS']}
    start=json.loads((O/'holdout/private_config_history/judgenum_v1.r0.lock.json').read_text())['locked_at'];end=stamp()
    minutes=(dt.datetime.fromisoformat(end)-dt.datetime.fromisoformat(start)).total_seconds()/60
    choices=[]
    for r in base:
        k=1 if r['group']=='roof' else 2;v=cal[r['prior']]['base']
        choices.append(f"{prior(r['prior'])} {kind(k)}: r {v['radius'][str(k)]['radius_m']:g} m, A {n(v['A'][str(k)],4)} m², δ {r['delta']:g}/점수 {r['s_min']:g}/문턱 {t(r['threshold2_m'])}")
    text=[f"범위: LoD2 {scope['LoD2']['count']}동, 핵심점 {scope['LoD2']['cores']:,}개, {n(scope['LoD2']['area'])} m².",
      f"범위: 항공 LiDAR {scope['ALS']['count']}동, 핵심점 {scope['ALS']['cores']:,}개, {n(scope['ALS']['area'])} m². 평가 지역 10동 제외.",
      '고른 값: '+'; '.join(choices)+'.',
      '확인 불가: 항공 LiDAR 법선의 25배 규칙, 수치 입력이 없는 판단, 지붕·벽 최소 넓이가 서로 다른 처리를 요구하는 덩어리. 세부 수는 아래 표.',
      f'걸린 시간: 최초 설정 잠금 {start}부터 보고 생성 {end}까지 {minutes:.1f}분. CPU만 사용. scientific_verdict: null.',
      '', '# 판단 숫자 셈 — 보고 v1','',
      '이 보고의 새 계산값은 모두 **[이 발주에서 냄]**이다. 반올림 전 값·표본 수·출처는 같은 이름의 `tables/` JSON·CSV·Markdown에 있다. 값의 채택과 과학적 결론은 내리지 않았다.',
      '', '## 1. 단계 가','',
      '제외 기준은 고정 GroundSurface XY가 평가 범위 넷 중 하나와 닿는 건물 전체다. 제외 번호: '+', '.join(r['building'].removeprefix('DEBY_LOD2_') for r in cfg['scope']['excluded'])+'.',
      '', '목록·외곽에는 건물 번호와 GroundSurface XY만 썼고, 제외 건물의 측정 행은 해석·집계하지 않았다. 압축 배열의 건너뛰기에서 압축 바이트가 풀리는 일은 있을 수 있다. 물리적 디스크 읽기 자체가 전혀 없었다는 뜻은 아니다.', '']
    text+=table(['사전 정보/패치','건물','코어','넓이 m²','칸 1 m² / >1 m² 동 / 상위 3동','칸 2 m² / >1 m² 동 / 상위 3동'],[
      [prior(r['prior'])+' '+kind(r['kind']),r['building_count'],f"{r['patch_count']:,}",n(r['area_m2']),
       f"{n(r['cell1_area_m2'])} / {r['cell1_buildings_gt1m2']} / {p(r['cell1_top3_fraction'])}",f"{n(r['cell2_area_m2'])} / {r['cell2_buildings_gt1m2']} / {p(r['cell2_top3_fraction'])}"] for r in sample])
    text+=['','지붕의 칸 1·2 각각 5동 기준을 통과했다. 항공 LiDAR 벽 패치는 없다. 기존 사진 판단은 설정용 2,631,648개 모두 연결되었다. 새 사진 검사는 하지 않았다.',
      '', '법선은 기존 값 그대로다. 항공 LiDAR는 TIN 삼각형 법선이며, 법선을 만든 평면 맞춤 둘레와 거칠기가 없어 25배 규칙의 미달 수·넓이는 확인 불가다. 법선을 다시 구하지 않았다. [지붕 형태별 법선 표](tables/normal_checks.md).',
      '', '후보별 점 수 중앙값(Q25–Q75). 아래 표의 통계와 <4 비율의 분모는 최대 반지름에서 점이 있는 코어다. 전체 코어·법선이 있는 코어를 분모로 한 <4 비율도 [분모별 표](tables/radius_sample_denominators.md)에 따로 실었다.', '']
    rr=[r for r in rows('radius_candidates') if r['scenario']=='base'];items=[]
    for radius in cfg['cylinder']['radii_m']:
        row=[f'{radius:g}']
        for pr,k in [('LoD2',1),('LoD2',2),('ALS',1)]:
            r=next(r for r in rr if r['prior']==pr and r['kind']==k and r['radius_m']==radius)
            row.append(f"{n(r['median_n'],0)} ({n(r['q25_n'],0)}–{n(r['q75_n'],0)}); <4 {p(r['fraction_n_lt4'])}")
        items.append(row)
    text+=table(['반지름 m','LoD2 지붕','LoD2 벽','항공 LiDAR 지붕'],items)
    text+=['','원통은 ±5 m, 앞 작업의 바깥 첫 면 탐색과 그 중심 ±1 m 점 선택을 그대로 썼다. d는 바깥 +, s는 표본 표준 편차다. DL = 1.96√(s²/n+a²+2.75²+σp²), 단위 cm. a가 없으면 DL에서만 0으로 두고 표시했다. n<4만 상속이며, 법선·σp가 없어 계산할 수 없는 행은 -1로 보존했다.', '']
    area=[r for r in rows('judgment_areas') if r['scenario']=='base' and r['roof_type']=='all' and r['area_m2']>0]
    text+=table(['사전 정보/패치','처리','같음 m²','어긋남 m²','상속 m²','확인 불가 m²'],[[prior(r['prior'])+' '+kind(r['kind']),'전' if r['stage']=='before' else '후',n(r['same_area_m2']),n(r['different_area_m2']),n(r['inherit_area_m2']),n(r['unavailable_area_m2'])] for r in area])
    old=rows('old_rule_comparison')
    text+=['','옛 max(DL, τ) 규칙과 달라진 넓이: '+', '.join(prior(pr)+' '+n(sum(r['changed_area_m2'] for r in old if r['prior']==pr))+' m²' for pr in ['LoD2','ALS'])+'. 옛 규칙은 비교에만 썼다.',
      '', '[지붕 형태별 판단 넓이](tables/judgment_areas.md) · [반지름 표 전체](tables/radius_candidates.md).',
      '',fig('judgment_map_LoD2','LoD2 처리 전후'),'',fig('judgment_map_ALS','항공 LiDAR 처리 전후')]
    for i,sec in enumerate(cfg['figures']['section_coordinates']):text+=['',fig(f"section_{i+1}_{sec['prior']}",f'고정 단면 {i+1}')]
    text+=['','## 2. 최소 넓이','',
      '칸 0만 남긴 어긋남 덩어리의 건물별 최대 넓이에서 95% 값을 구했다. 칸 0이 10 m² 이상인 건물만 썼고, A를 엄격히 넘는 비율이 5% 이하가 되도록 higher 분위수를 사용했다.', '']
    null=[dict(prior=pr,**r) for pr in ['LoD2','ALS'] for r in rows(f'{pr}_base_null_rates') if r['cell0_patches']]
    text+=table(['사전 정보/패치','칸 0 코어 / m²','어긋남 비율','A용 건물','A m²','A 초과 건물 비율','A>1 m²'],[[prior(r['prior'])+' '+kind(r['kind']),f"{r['cell0_patches']:,} / {n(r['cell0_area_m2'])}",p(r['false_different_fraction']),r['buildings_for_A'],n(r['minimum_area_m2']),p(r['fraction_buildings_above_A']),'예' if r['A_gt_1m2'] else '아니오'] for r in null])
    loss=[r for r in rows('lost_different_area') if r['scenario']=='base'];items=[]
    for pr,k in [('LoD2',1),('LoD2',2),('ALS',1)]:items.append([prior(pr)+' '+kind(k)]+[n(next(r['lost_area_m2'] for r in loss if r['prior']==pr and r['kind']==k and r['cell']==c)) for c in range(7)])
    text+=['','작은 덩어리 처리 뒤 어긋남에서 같음·상속으로 빠진 넓이(m²):','']+table(['패치']+[f'칸 {c}' for c in range(7)],items)
    text+=['','칸 1·2의 값은 진짜 어긋남을 잃은 넓이다. -1로 남긴 지붕·벽 혼합 덩어리는 위 손실에 섞지 않았다. [혼합 덩어리 확인 불가](tables/mixed_cutoff_unavailable_by_cell.md), [작은 같음 섬의 칸별 수·넓이](tables/small_same_island_summary.md), [개별 작은 같음 섬](tables/small_same_islands.md), [건물 크기별 A](tables/minimum_area_by_building_size.md). 같음 섬은 처리하지 않았다.']
    for pr,g in [('LoD2','roof'),('LoD2','wall'),('ALS','roof')]:text+=['',fig(f'false_components_{pr}_{g}','우연한 덩어리와 A')]
    text+=['','## 3. 사진 조건과 두 번째 문턱','',
      '기존 사진 판단 15개 × 문턱 9개를 모두 비교했다. 틀린 넓이는 칸 1의 보존 + 칸 2의 보정이며, 비율의 분모는 처리 후 어긋남 중 칸 0·1·2 넓이다. 칸 3·4·5·6은 선택 오차에서 제외하고 교차표에 넓이를 남겼다. 동률은 큰 문턱, 앞선 사진 순서다.', '']
    text+=table(['사전 정보/패치','δ / 최소 점수','문턱','건물 동일 비중: 사진 번호 / 문턱','한 동 제외 시 변경'],[[prior(r['prior'])+' '+kind(r['group']),f"{r['delta']:g} / {r['s_min']:g}",t(r['threshold2_m']),f"{r['building_equal_photo_index']} / {t(r['building_equal_threshold2_m'])}",f"{r['leave_one_out_changed']}/{r['leave_one_out_buildings']}"] for r in base])
    comb=[r for r in sel if r['scenario']=='base' and r['group']=='combined']
    text+=['','지붕·벽 통합 선택: '+', '.join(f"{prior(r['prior'])} 사진 번호 {r['photo_index']}, 문턱 {t(r['threshold2_m'])}" for r in comb)+'. 사진 번호는 0부터 시작한다. [15가지 조건](tables/photo_candidates.md) · [전체 선택값](tables/selected_values.md).',
      '', '한 동 제외에서 바뀐 건물과 새 조합은 각 `*_base_*_leave_one_out.md`에 있다. 건물 동일 비중은 평가 넓이가 있는 건물의 오차 비율 평균이다.', '']
    comparison=rows('selection_comparison')
    text+=table(['패치','방법','문턱','어긋남 m²','평가 넓이 m²','틀림 m² / 비율','칸 1 틀림 / 칸 2 틀림 m²'],[[prior(r['prior'])+' '+kind(r['group']),{'chosen':'고른 값','no_photo':'사진 없음','display_photo':'사진 보기 값'}[r['variant']],t(r['threshold2_m']),n(r['different_area_m2']),n(r['evaluated_area_m2']),n(r['wrong_area_m2'])+' / '+p(r['wrong_fraction']),n(r['cell1_wrong_area_m2'])+' / '+n(r['cell2_wrong_area_m2'])] for r in comparison])
    text+=['','[사진 판단별 넓이·틀린 넓이](tables/selection_comparison.md). 각 방법의 `*_photo_by_cell`과 `*_choice_by_cell` 파일에 사진 판단 × 참값 칸, 처음 선택 × 참값 칸을 따로 실었다.', '']
    for pr,g in [('LoD2','roof'),('LoD2','wall'),('ALS','roof')]:text+=['',fig(f'distance_distributions_{pr}_{g}','사진 모름의 거리'),'',fig(f'choice_heatmap_{pr}_{g}','135개 조합')]
    text+=['','틀린 넓이가 큰 15동(지붕·벽을 각각 고른 실제 선택 합계):','']
    text+=table(['사전 정보','순위','건물','어긋남 m²','틀림 m²','틀림 비율'],[[prior(r['prior']),r['rank'],r['building'].removeprefix('DEBY_LOD2_'),n(r['different_area_m2']),n(r['wrong_area_m2']),p(r['wrong_fraction'])] for r in rows('selected_top15_buildings')])
    text+=['','[모든 건물](tables/selected_all_buildings.md).','', '## 4. 진단 값','']
    quant=[r for r in rows('model_quantiles') if r['roof_type']=='all' and r['n_min'] is None and r['patch_count']]
    text+=table(['패치','유효 코어','68.3%','95%','99%'],[[prior(r['prior'])+' '+kind(r['kind']),r['patch_count'],n(r['q683']),n(r['q95']),n(r['q99'])] for r in quant])
    text+=['','위 값은 |d|/DL×1.96의 코어별 분위수다. [지붕 형태·n 구간별 전체 값](tables/model_quantiles.md).','',fig('model_cdf_LoD2','LoD2 누적 분포'),'',fig('model_cdf_ALS','항공 LiDAR 누적 분포'),'']
    bb=[r for r in rows('bias_diagnostic') if r['patch_count']]
    text+=table(['패치','d 중앙값 cm','NMAD cm','중앙값을 뺀 진단 어긋남 비율'],[[prior(r['prior'])+' '+kind(r['kind']),n(r['median_d_cm']),n(r['nmad_cm']),p(r['false_fraction_after_diagnostic_subtraction'])] for r in bb])
    text+=['','위 중앙값은 실제 판단에서 빼지 않았다. |gt_p| 또는 |mvs_p|가 원통 반길이를 넘는 넓이(m²):','']
    bounds=rows('outside_cylinder');items=[]
    for pr,k in [('LoD2',1),('LoD2',2),('ALS',1)]:
        for cell in [1,2]:items.append([prior(pr)+' '+kind(k),cell]+[n(next(r['area_m2'] for r in bounds if r['prior']==pr and r['kind']==k and r['cell']==cell and r['half_length_m']==h)) for h in [3.,5.,10.]])
    text+=table(['패치','칸','3 m','5 m','10 m'],items)
    text+=['','## 5. 민감도','',
      '한 번에 한 설정만 바꿨다. 0.5 m는 기존 사진 작업별 묶음에서 사전순 첫 패치를 남기고 묶음 넓이를 더했다. 좌표·법선은 그 패치 그대로다. 선택된 패치의 참값 칸을 썼으므로 칸별 넓이는 기본값과 달라질 수 있다. 코어 간격에 따른 덩어리 연결 반지름의 기존 대체 규칙도 적용했다.', '']
    ss=rows('sensitivity');items=[]
    for r in ss:
        idx=r['choice_index'];pp,tt=divmod(idx,9)
        items.append([prior(r['prior'])+' '+kind(r['group']),r['scenario'],f"{p(r['same_fraction'])}/{p(r['different_fraction'])}/{p(r['inherit_fraction'])}",p(r['false_different_fraction']),n(r['minimum_area_m2']),f"{pp}/{t(cfg['initial_choice']['threshold2_m'][tt])}",n(r['wrong_area_m2'])+' / '+p(r['wrong_fraction']),p(r['decided_photo_fraction']),'같음' if r['same_choice_as_base'] else n(r['base_choice_wrong_area_m2'])])
    text+=table(['패치','설정','같음/어긋남/상속','칸 0 어긋남','A m²','사진/문턱','틀림 m² / 비율','사진 판단 비율','기본 조합 / 적용 틀림 m²'],items)
    text+=['','비율 합에서 남는 부분은 확인 불가다. [원값·확인 불가 비율](tables/sensitivity.md), [0.5 m 작업 구분 및 넓이 보존 검사](tables/spacing_group_audit.md).','', '## 6. 발주문의 사전 기대와 계산값','']
    dl=rows('DL_medians');lookup=lambda pr,k,rt:next((r['median_DL_cm'] for r in dl if r['prior']==pr and r['kind']==k and r['roof_type']==rt),None)
    expectations=[['DL 중앙값: 항공 LiDAR 약 8 cm / LoD2 평지붕 약 33 cm / 박공지붕 약 44 cm',f"{n(lookup('ALS',1,'all'))} / {n(lookup('LoD2',1,'1000'))} / {n(lookup('LoD2',1,'3100'))} cm"],
      ['칸 0 어긋남 비율 약 5%', '; '.join(prior(r['prior'])+' '+kind(r['kind'])+' '+p(r['false_different_fraction']) for r in null)],
      ['지붕 A<1 m², 벽 A가 더 큼','; '.join(prior(r['prior'])+' '+kind(r['kind'])+' '+n(r['minimum_area_m2'])+' m²' for r in null)],
      ['항공 LiDAR 옛 규칙과 차이는 |d| 8~12.66 cm, 넓이가 작음',n(sum(r['changed_area_m2'] for r in old if r['prior']=='ALS'))+' m²; |d| '+
        '–'.join(n(next(r[key] for r in rows('old_rule_distance_range') if r['prior']=='ALS' and r['kind']==1)) for key in ['min_changed_abs_d_cm','max_changed_abs_d_cm'])+' cm; 크기 해석 없음'],
      ['사진으로 칸 1 틀림 감소, 칸 2 비슷하거나 조금 증가','3절 두 기준선의 칸별 틀린 넓이와 나란히 표시; 결론 없음']]
    text+=table(['계산 전 기대','이번 계산'],expectations)
    text+=['','[DL 표본 수·중앙값](tables/DL_medians.md).','', '## 7. 원사진 모음','',
      '처음 선택이 틀린 어긋남 코어를 같은 건물·참값 칸으로 연결했다. 넓이 순 20개씩, 건물당 최대 3개다. 원본 학습 사진에 사전 정보의 패치 지지 영역 테두리를 비췄다. 사진은 완전한 덩어리가 화면 안에 있는 후보 중 앞면 패치의 투영 넓이 합이 가장 큰 것으로 정했다. 각 패치 접평면에서 3 m 여백을 주었고 영상 끝에서는 잘랐다. 새 가림 검사·사진 점수·원인 이름은 붙이지 않았다.']
    for pr in ['LoD2','ALS']:
        for page in [1,2]:text+=['',fig(f'wrong_montage_{pr}_{page}',f'{prior(pr)} 원사진 {page}')]
    text+=['','[모음 목록](tables/montage_inventory.md). 사진별 원본 SHA-256, 투영 좌표, 사용 패치는 그림 JSON에 있다.','', '## 8. 확인용 봉인','']
    held=rows('holdout_counts_and_hashes')
    text+=table(['사전 정보','건물','코어','넓이 m²'],[[prior(r['prior']),r['building_count'],f"{r['core_point_count']:,}",n(r['area_m2'])] for r in held])
    text+=['', '설정용에서 고른 값을 그대로 적용했다. 확인용의 값·판단은 전용 holdout 폴더에만 있다. 전달 ZIP에는 넣지 않았다.',
      '', '[확인용 파일별 SHA-256](tables/holdout_counts_and_hashes.json). 이 공개 목록의 SHA-256: `'+sha(D/'tables/holdout_counts_and_hashes.json')+'`.',
      '', '## 9. 변경·확인 불가·시간','']
    text+=table(['패치','값','확인 불가 코어','넓이 m²'],[[prior(r['prior'])+' '+kind(r['kind']),r['value'],r['patch_count'],n(r['area_m2'])] for r in rows('missing_values') if r['patch_count']])
    analysis=json.loads((O/'analysis_complete.json').read_text());repair=json.loads((O/'spacing_replay_receipt.json').read_text());hold=json.loads((O/'holdout/complete.json').read_text())
    text+=['','첫 규칙 잠금 뒤 표본 검사로 단면 좌표를 확정하고 원통 계산 전에 좌표를 잠갔다. 따라서 좌표까지 최초 표본 셈 전에 잠근 것은 아니다. 최소 넓이 시험 실행이 중간 보고 커밋보다 먼저 시작된 순서 오류는 중단 후 중간 보고 커밋 `52e91da1`을 완료해 바로잡았다.',
      '', '수정 기록: 첫 면 탐색 시작 위치, NumPy 문자열 최소값, 최소 넓이 사전 키, cm 내보내기 정밀도, 0.5 m 지붕·벽 사진 작업 이름 충돌. 이전 결과·잠금·실패 로그를 보존했다. 지붕·벽 A가 서로 다른 처리를 요구하는 혼합 덩어리는 -1로 남겼다. [전체 기록](issues.md).',
      '', f"기본·민감도 집계 {analysis['seconds']:.1f}초, 수정한 0.5 m 재집계 {repair['seconds']:.1f}초, 확인용 계산 {hold['seconds']:.1f}초. 원통의 사전 시간 어림은 한 구역 535.93초 × 24 = 3.57시간으로 72시간 기준을 통과했다. 설정용 원통 병렬 실행은 01:45:40–01:55:30 KST였다. 그림·검증·포장 시간은 위 집계 시간에 포함하지 않았다.",
      '', '검증: 전체 기본 코어의 식·단계 가 값 보존, 실제 원통 270개 독립 직접 비교, 135개 조합과 건물 제외 선택의 별도 합계, A의 5% 조건, 앞 작업 잠금, 확인용 공개 제외, 그림 300 dpi. 상세는 [최종 검증](tables/final_validation.json).',
      '', '핵심점 NPZ와 표로 판단·선택·오차 집계를 다시 확인할 수 있다. 원통·사진 투영을 처음부터 다시 계산하려면 잠금 파일이 가리키는 원 MVS·패치·사진 자료가 필요하다. ZIP의 SHA-256과 CRC는 파일 무결성 확인이며 과학적 타당성의 결론이 아니다.',
      '', '`scientific_verdict: null`']
    report='\n'.join(text)+'\n';assert len(report)<20000,len(report)
    (D/'판단숫자셈_보고_v1.md').write_text(report)
    dump(O/'report_receipt.json',{'at':end,'characters':len(report),'sha256':sha(D/'판단숫자셈_보고_v1.md'),'scientific_verdict':None})
    print('FINAL_REPORT_READY',len(report),flush=True)

if __name__=='__main__':main()
