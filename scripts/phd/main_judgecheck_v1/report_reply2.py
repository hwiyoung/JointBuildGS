"""Concise Korean Report A and immutable roof interim, with all detailed tables."""
import json,sys,csv
from preflight import C,D,O,Path,sha,dump,now
from resources_reply2 import main as resource_receipt
BASE=O/'r2';LABEL={'ALS_1':'항공 LiDAR 지붕','LoD2_1':'LoD2 지붕','LoD2_2':'LoD2 벽'}
VAR={'new_clipped':'본 규칙','new_unclipped':'고친 사진·자르지 않음','new_oldphoto':'옛 사진','old_rule':'옛 규칙','always_prior':'늘 사전 정보','always_mvs':'늘 영상'}
ARM={'main':'본 방법','all_oracle':'모두 정답','geometry_oracle':'기하 검사만 정답','cause_oracle':'원인 판별만 정답','always_mix':'늘 섞음','always_prior':'늘 사전 정보','always_mvs':'늘 영상','default_only':'사진 없이 기본 방향','oldphoto':'옛 사진'}
EX='실험 지역과 사진 점을 공유해 뺀 핵심점: 73개, 5.442552935831812 m². 모든 계산의 대상에서 제외했다.'
DX={'u_M_missing':'u_M 없음','u_M_missing_n_lt4':'u_M 없음·0≤n<4','u_M_missing_n_unknown':'u_M 없음·n 확인 불가','u_M_missing_n_ge4_uncountable':'n≥4·u_M 없음(셀 수 없음)','unknown_reason_exclusive:normal_missing':'기하 확인 불가: 법선 없음','unknown_reason_exclusive:prior_height_missing':'기하 확인 불가: 사전 높이 없음','unknown_reason_exclusive:u_M_missing':'기하 확인 불가: u_M 없음','unknown_reason_exclusive:sigma_P_missing':'기하 확인 불가: σ_P 없음'}
TIME={'tile_load_and_tree_seconds':'구역 점군·탐색 구조','per_point_plane_and_visibility_seconds':'점마다 면·사진 선택','prepared_output_seconds':'준비 값 저장','gpu_image_cache_read_and_upload_seconds':'사진 읽기·전송(구역·자료 판마다)','gpu_packed_arithmetic_seconds':'사진 점수·합치기'}
def load(p):return json.loads(p.read_text())
def num(x,d=2):
    if x is None:return '확인 불가'
    value=f'{x:,.{d}f}'
    return value.rstrip('0').rstrip('.') if d else value
def pct(x):return '확인 불가' if x is None else num(x*100,2)+'%'
def table(headers,rows):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(str(v).replace('|','/') for v in r)+'|' for r in rows])+'\n\n실험 지역과 사진 점을 공유해 뺀 핵심점: 항공 LiDAR 73개·5.442553 m²(발주 전체).\n'
def readtable(g,k):return load(D/'tables'/f'{g}_{k}.json')['rows']
def main(mode='full'):
    resource_receipt();resources=load(BASE/'resource_receipt.json')
    groups=['ALS_1','LoD2_1']+(['LoD2_2'] if mode=='full' else []);summary={g:load(BASE/'metrics'/f'{g}.json') for g in groups};cal=load(O/'r1/geometry_calibration.json');diagnostics=load(BASE/'diagnostics.json');timing=load(BASE/'timing_estimate.json');s=[]
    ranges=[];errors=[];ab=[];uncountable_u=sum(r['count'] for r in diagnostics['rows'] if r['group'] in groups and r['metric']=='u_M_missing_n_ge4_uncountable')
    for g,r in summary.items():
        buildings=122 if g=='ALS_1' else 125;ranges.append(f"{LABEL[g]} {buildings}동, {r['core_count']:,}개, {r['area_m2']:,.2f} m²")
        a={x['variant']:x for x in r['accuracy'] if x['stratum']=='all'};errors.append(LABEL[g]+': '+ '/'.join(pct(a[v]['fraction']) for v in ['new_clipped','always_prior','always_mvs']))
        aa={x['arm']:x for x in r['ablation']};ab.append(LABEL[g]+': '+pct(aa['main']['within_tau_fraction'])+' / '+pct(aa['all_oracle']['within_tau_fraction']))
    s+=['# 판단 검증 — '+('지붕 중간 보고' if mode=='roofs' else '보고 가'),'', '범위: '+'; '.join(ranges)+'.','판단이 틀린 비율(본 규칙 / 늘 사전 정보 / 늘 영상): '+'; '.join(errors)+'.','7절 τ 안 비율(본 방법 / 모두 정답): '+'; '.join(ab)+'.',
        f'확인 불가: n≥4인데 u_M이 없는 {uncountable_u:,}개는 셀 수 없음이다. 기하 검사와 시선 검사의 나머지 확인 불가는 아래에 수·넓이·까닭을 적었다.',f"시간: 회신 2 시작 후 {resources['elapsed_seconds']/3600:.2f}시간 경과, 기록으로 확인된 GPU 대기 최소 {resources['gpu_wait_recorded_minimum_seconds']/3600:.2f}시간. 전체 계산 어림 GPU {timing['estimated_hours']:.2f}시간, CPU {timing['cpu_estimated_hours']:.2f}시간(25% 여유 포함).",
        '',('상태: 지붕의 6~8절 중간 보고다. 이 보고를 커밋한 뒤 벽을 계속한다.' if mode=='roofs' else '상태: 개발용 단계 가를 마쳤다. 이 보고 뒤 멈추며, σ_W와 r의 단계 나 적용값은 다음 회신에서 잠근다.'),
        '학습 없음. 확인용 곡선·값 미개방. scientific_verdict: null. 새 값은 모두 [이 발주에서 냄].',EX,
        '처음 연결에서 읽은 공유 곡선 22개에서 나온 값은 이 보고의 어떤 표·그림·설정에도 들어가지 않았다. 처음 준비 파일은 재현 기록으로만 보존하며 전달 묶음에 넣지 않는다.',
        '', '## 기하 검사 (6.5)',f"σ_W={cal['sigma_W_m']*100:.6f} cm. 사용 건물 {cal['building_count']}동, 건물 중앙값의 10·90% 값 {num(cal['building_median_q10_q90_m'][0]*100,4)}, {num(cal['building_median_q10_q90_m'][1]*100,4)} cm. 참값은 이 값과 r을 구하는 데 쓰지 않았다."]
    rows=[]
    for g in groups:
        gg=readtable(g,'6_5_geometry');limits={r['q']:r['value_m'] for r in gg if r['metric']=='limit_quantile'};ref=next(r['value_m'] for r in gg if r['metric']=='r_reference_cell0_median')
        rows.append([LABEL[g],num(cal['r_m'][g]*100,4),num(ref*100,4) if ref is not None else '확인 불가',' / '.join(num(limits[q]*100,3) if limits[q] is not None else '확인 불가' for q in [.25,.5,.75])])
    s.append(table(['자료','r(cm)','칸0 d 중앙값(cm, 참고)','L 25/50/75%(cm)'],rows))
    rows=[]
    for g in groups:
        for r in readtable(g,'6_5_precision'):rows.append([LABEL[g],r['source'],r['roof_type'],r['count'],num(r['normalized_median'],3),num(r['normalized_centered_NMAD'],3)])
    s.append(table(['자료','정밀도 식','지붕 형태','표본 수','정규화 오차 중앙값','중앙값을 뺀 NMAD'],rows))
    rows=[]
    for g in groups:
        for r in readtable(g,'6_5_geometry'):
            if r['metric']=='five_percent_check':rows.append([LABEL[g],r['z'],num(r['denominator_area_m2']),num(r['area_m2']),pct(r['fraction'])])
    s.append(table(['자료','계수','칸0 분모(m²)','한계 밖(m²)','비율'],rows));s.append('LoD2 지붕의 5% 확인은 참고값이다. 정밀도 확인에는 참값의 오차 크기로 고른 부분을 쓰지 않았다.')
    rows=[[r['radius_m'],num(r['q25']),num(r['median']),num(r['q75'])] for r in cal['als_radius_candidates']];s.append(table(['LiDAR 원통 반지름(m)','점 수 25%','중앙값','75%'],rows));s.append('선택한 반지름은 0.75 m다. 법선 반지름 분포, TIN과 새 높이 차, 5·10 m 결측/빈 공간 넓이와 옛 칸·새 칸 교차는 6.5 상세 표에 있다.')
    rows=[]
    for r in diagnostics['rows']:
        if r['group'] in groups and (r['metric'].startswith('u_M_missing') or (r['metric'].startswith('unknown_reason_exclusive') and r['count'])):rows.append([LABEL[r['group']],DX.get(r['metric'],r['metric']),r['count'],num(r['area_m2'])])
    s.append(table(['자료','확인 불가의 까닭/겹침','핵심점 수','넓이(m²)'],rows));s.append('원인별 수는 위에서부터 정상 법선 없음 → 사전 높이 없음 → MVS 높이 없음 → u_M 없음 → σ_P 없음 → σ_W/r 없음 순서로 한 번만 센 값이다. 원인이 겹치는 수와 넓이도 JSON/CSV에 별도로 남겼다.')
    e=diagnostics['edge_summary'];s.append(f"법선 규칙 미충족 66,552개(4,798.977724 m²)에서 지원점 경계 0.5 m 이내 넓이 비율은 {pct(e['fallback']['near_edge_area_fraction'])}, 나머지는 {pct(e['rule_met']['near_edge_area_fraction'])}다. 66,552개 중 194개는 법선 자체가 없다. 경계는 같은 건물의 남은 핵심점으로 만든 0.25 m XY 격자에서 빈 이웃 칸과 맞닿는 칸으로 정했다. 참값 지붕선과의 거리가 아니다. 이 정의는 집계 전에 잠갔다.")
    s+=['','## 사진 확인 (6.4)',f"대상 1·2·3 합계 {timing['all_targets']:,}점. 최대 구역 {timing['benchmark_tile']}의 {timing['benchmark_points']:,}점을 통째로 계산했다. 공통 비용을 점당 시간에 곱하지 않았다.",table(['전체 시간 어림의 항','시간(시)'],[[TIME.get(k,k),num(v/3600,3)] for k,v in timing['components_seconds'].items()]),'최대 구역 전체의 float64 CPU/GPU 일치와 기존 200점 중 공통 27점의 점수·면·법선·사진·마스크 일치 기록을 남겼다.']
    rows=[]
    for label,key in [('GPU 한 장','measured_scoring'),('CPU 2개 제한','measured_cpu_scoring')]:
        m=timing[key];rows.append([label,m['points'],m['camera_count'],num(m['image_cache_total_seconds']),num(m['upload_seconds']),num(m['arithmetic_and_reduction_seconds']-m['upload_seconds']),num(m['total_seconds'])])
    s.append(table(['최대 구역 실측','점','사진','읽기(초)','전송(초)','점수·합치기(초)','전체(초)'],rows));s.append(f"전송에는 배열 변환·복사도 포함된다. 구역·자료 판 {timing['image_passes']}회마다 최대 구역의 사진 공통 비용을 보수적으로 넣었다. 시작 전 GPU 대기는 계산 시간에서 분리했다.")
    actual=resources['measurement_totals']['photo_scores']['by_device'];s.append('완료된 사진 계산의 실행 시간(최대 구역 GPU 측정 포함, 별도 CPU 비교 측정 제외): '+'; '.join(('GPU' if k=='cuda' else 'CPU')+f" {v['seconds']/3600:.3f}시간·{v['points']:,}점" for k,v in actual.items())+'. 다른 발주의 GPU 사용 중에는 검증을 마친 동일한 float64 CPU 셈을 사용했다.')
    census=load(BASE/'target_census.json');targetrows=[]
    for g in groups:
        rr=[r for r in census['rows'] if r['prior']+'_'+str(r['kind'])==g];targetrows.append([LABEL[g]]+[sum(r[k] for r in rr) for k in ['type1_count','type2_count','type3_count','type2_type3_overlap_count','target_count']])
    s.append(table(['자료','대상1','대상2','대상3','2·3 겹침','중복 뺀 합'],targetrows));s.append('대상 3은 7절의 평가 전용이다. 대상 2와 겹쳐도 원래 일치 표본의 소속을 바꾸지 않았다.')
    rows=[]
    for g in groups:
        t=load(C/f'photo_threshold.{g}.reply2.lock.json');rows.append([LABEL[g],num(t['t'],6),num(t['t10'],6),t['finite_score_points'],num(t['finite_score_area_m2'])])
    s.append(table(['자료','t(아래5%)','아래10%(참고)','유효 일치 표본 점','넓이(m²)'],rows));s.append('t는 참값을 쓰지 않은 원래 일치 표본의 자른 사전 정보 면 점수에서 구했다. 자르지 않은 판에도 같은 t를 써서 자르기의 차이를 표시했다.')
    for g in groups:
        rows=[]
        for vi in ['new_oldphoto','new_unclipped','new_clipped']:
            rr=[r for r in readtable(g,'6_4_photos') if r['variant']==vi]
            for label in dict.fromkeys(r['stratum'] for r in rr):
                vals=[r for r in rr if r['stratum']==label];pp={r['photo']:r for r in vals};den=vals[0]['denominator_area_m2'];rows.append([VAR[vi],label.replace('일치 표본 한계 안 칸0','일치 표본').replace('한계 밖 ','밖 '),num(den)]+[pct(pp[k]['fraction']) for k in ['지지','반박','옛 판 애매','애매(둘 다 낮음)','애매(둘 다 높음)','애매(MVS 면 없음)','애매(조각 부족)','무늬 없음','사진 부족','미계산/범위 없음']])
        s.append('### '+LABEL[g]+' 사진 판단');s.append(table(['판','부분','분모(m²)','지지','반박','옛 애매','둘 낮음','둘 높음','면 없음','조각 부족','무늬 없음','사진 부족','셀 수 없음'],rows))
    rows=[]
    for g in groups:
        rr=readtable(g,'6_4_planes');missing=next(x for x in rr if x['metric']=='MVS 면 없음');angles=[x for x in rr if x['metric']=='angle_photo_point_quantile'];rows.append([LABEL[g],missing['count'],num(missing['area_m2']),' / '.join(num(x['value_deg'],2) for x in angles)])
    s.append(table(['자료','MVS 면 없음(핵심점)','넓이(m²)','두 면 각 10/25/50/75/90%(°)'],rows));s.append('일치 표본 행은 원래 대상 2만 사용했다. 각도는 중복을 뺀 사진 점의 분포다. 넓이 가중 핵심점 분포는 6.4 상세 표에 있다.')
    s+=['','## 판단 (6.1~6.3)']
    for g in groups:
        cross=readtable(g,'6_1_cross');rows=[]
        for variant,panel,prefix in [('new_clipped','geometry','기하'),('new_clipped','judgment','고친 사진'),('new_oldphoto','judgment','옛 사진')]:
            rr=[x for x in cross if x['variant']==variant and x['panel']==panel and x['cell']<6]
            for label in dict.fromkeys(x['label'] for x in rr):
                cc={x['cell']:x for x in rr if x['label']==label};rows.append([prefix+' '+label]+[num(cc[i]['area_m2'],1)+'/'+num(cc[i]['fraction']*100,1) if cc[i]['fraction'] is not None else '확인 불가' for i in range(6)])
        s.append('### '+LABEL[g]+' 기하·판단과 칸 교차');s.append('각 칸은 넓이(m²)/전체 유효 참값 넓이 대비 %다. 각 판의 여섯 열과 모든 영역의 비율 합은 100%다.');s.append(table(['판·영역','칸0','칸1','칸2','칸3','칸4','칸5'],rows))
        r=summary[g];rows=[[VAR[x['variant']],x['stratum'],num(x['denominator_area_m2']),num(x['area_m2']),pct(x['fraction']),pct(x['whole_roof_fraction'])] for x in r['accuracy']]
        s.append('### '+LABEL[g]+' 판단 정확도');s.append(table(['판','부분','분모(m²)','틀린 넓이(m²)','틀린 비율','전체 넓이 대비'],rows))
        s.append('분모는 새 한계 밖의 칸 0·1·2다. 옛 규칙만 자기 한계와 옛 칸을 썼다. 칸 1에서 보정하지 않음과 칸 2에서 보정함을 틀림으로 셌다.')
        rows=[[x['building'],num(x['denominator_area_m2']),num(x['area_m2']),pct(x['fraction'])] for x in r['top15']];s.append(table(['틀린 넓이가 큰 15동','분모(m²)','틀린 넓이(m²)','틀린 비율'],rows))
        causes=readtable(g,'6_3_causes');rows=[]
        for v in ['new_clipped','new_unclipped','new_oldphoto']:
            rr=[x for x in causes if x['variant']==v];values={x['reason']:x['area_m2'] for x in rr};default=sum(x['area_m2'] for x in rr if x['reason'].startswith('기본 방향:'))
            rows.append([VAR[v],num(values['사진이 틀리게 지지']),num(values['사진이 틀리게 반박']),num(default),num(values['빈 공간 보정이 틀림(6.2 분모 밖)']),num(values['한계 밖 둘 다 틀림']),num(values['한계 안 사진 반박(전체 한계 안 분모)'])])
        s.append(table(['틀림의 까닭(m²)','틀린 지지','틀린 반박','기본 방향','빈 공간(분모 밖)','밖·둘 다 틀림','안·사진 반박'],rows))
    s.append('참값 없음과 기하 확인 불가는 별도 행으로 남겼다. 모름의 종류별 기본 방향 오류와 한계 안 사진 반박 비율은 6.3 상세 표에 있다.')
    s+=['','## 단계별 바꿔 끼우기 (7절)']
    for g in groups:
        rows=[[ARM[r['arm']],pct(r['within_tau_fraction']),num(r['mean_abs_error_m'],4),num(r['median_abs_error_m'],4),num(r['within_tau_difference_pp']),num(r['uncountable_area_m2'])] for r in summary[g]['ablation']]
        s.append('### '+LABEL[g]);s.append(table(['판','τ 안 비율','평균 오차(m)','중앙값(m)','본 방법과 차(%p)','셀 수 없음(m²)'],rows))
    s.append('높이 오차의 평균·중앙값은 넓이 가중이다. 면 없음은 참값 면이 있는 곳에서 틀림이다. 참값 자체가 없는 칸 6을 빈 공간의 정답으로 간주하지 않았다. 면 없음은 높이 오차 평균·중앙값에서 제외하고 넓이를 따로 적었다. 칸 0~5 표와 계산 가능한 넓이는 상세 표에 있다.')
    s+=['','## 그림 (8절)']
    for p in sorted((D/'figures').glob('그림*.png')):
        if mode=='roofs' and '_all_' in p.name:continue
        if mode=='full' and p.name.startswith('그림2_LoD2_roofs_'):continue
        meta=load(p.with_suffix('.json'));title=(f"{meta['building']} · {meta['variant']}의 기하·판단·참값" if p.name.startswith('그림1') else f"{meta['building']} · {meta['reason']} {meta['area_m2']:.2f} m²")
        s.append(f"- [{title}](figures/{p.name})")
    s.append('그림마다 같은 이름의 JSON에 쓴 점·사진·값을 남겼다. 지도는 사전 정보 면의 5 cm 격자에 학습 영상을 투영하고 그 면으로 가림을 검사했다. 빨간 테두리는 판단이 해를 끼친 같은 면의 이웃 칸이다. 사진 조각의 수동 까닭은 비워 두었다. 1 m² 미만과 선택 가능한 자리 부족은 그림 2 선택 기록에 남겼다.')
    s+=['','## 발주 전 기대와 나란히 놓기 (결론 없음)']
    measured={}
    for g in ['ALS_1','LoD2_1']:
        geometry=readtable(g,'6_5_geometry');precision=readtable(g,'6_5_precision');a={r['variant']:r for r in summary[g]['accuracy'] if r['stratum']=='all'}
        measured[g]={'r':num(cal['r_m'][g]*100,3),'L':num(next(r['value_m'] for r in geometry if r['metric']=='limit_quantile' and r['q']==.5)*100,3),
            'MVS':num(next(r['normalized_centered_NMAD'] for r in precision if r['source']=='MVS'),3),'5%':pct(next(r['fraction'] for r in geometry if r['metric']=='five_percent_check' and r['z']==1.96)),
            **{v:pct(a[v]['fraction']) for v in ['new_oldphoto','always_prior','always_mvs']}}
    rows=[['σ_W(cm)·건물 수','2.4·86',num(cal['sigma_W_m']*100,3)+f"·{cal['building_count']}",'같은 값','같은 값']]
    for label,key,ex1,ex2 in [('r(cm)','r','+1.7','+5.1'),('L 중앙값(cm)','L','12.3','46.0'),('MVS 정밀도 NMAD','MVS','1.11','1.11'),('5% 확인','5%','2.3%','참고만'),('틀린 비율·옛 사진','new_oldphoto','12.1%','10.4%'),('틀린 비율·늘 사전','always_prior','12.0%','90.4%'),('틀린 비율·늘 영상','always_mvs','57.2%','7.8%')]:rows.append([label,ex1,measured['ALS_1'][key],ex2,measured['LoD2_1'][key]])
    aps=next(r['normalized_centered_NMAD'] for r in readtable('ALS_1','6_5_precision') if r['source']=='prior_sigmaP_plus_sigmaW');rows.append(['사전 정밀도 NMAD(σ_W 포함)','1.12',num(aps,3),'—','—'])
    s.append(table(['값','항공 기대','항공 이번','LoD2 기대','LoD2 이번'],rows));rows=[]
    for g,label,expected in [('ALS_1','사진이 틀리게 반박',120),('LoD2_1','사진이 틀리게 지지',260),('LoD2_1','영상만 틀린 곳의 보정',250)]:
        source=readtable(g,'6_3_causes');values=[]
        for variant in ['new_oldphoto','new_clipped']:
            keep=[r for r in source if r['variant']==variant];area=sum(r['area_m2'] for r in keep if (r['reason']=='사진이 틀리게 반박' or r['reason'].startswith('기본 방향:'))) if label=='영상만 틀린 곳의 보정' else next(r['area_m2'] for r in keep if r['reason']==label);values.append(num(area))
        rows.append([LABEL[g]+' '+label,f'약 {expected}']+values)
    s.append(table(['틀린 넓이(m²)','발주 전','이번 옛 사진','이번 고친 사진'],rows));s.append('발주 전 값은 TIN 기준·개발용 지붕의 미리 계산한 값이다. 이번 항공 LiDAR는 원통 높이와 새 법선을 썼다. 발주 전 잘못된 반박의 MVS 봉우리 비율 53%·77%는 재분류의 허용 폭이 이 발주에 정해져 있지 않아 새 비교값을 만들지 않았다.')
    s+=['','## 바꾼 것·확인 불가·시간','회신 1의 공통 제외와 전체 소속 검사, 회신 2의 구역/사진 묶음 계산과 대상 3을 적용했다. 사진 점 번호는 지붕과 벽에서 겹칠 수 있어 (구역, 사전 정보, 지붕/벽, 점 번호)를 연결 키로 쓴다. 옛 곡선은 다시 계산하지 않았다.',
        '원시 이웃 점/화소의 실험 지역 포함은 회신 1에서 허용한 범위다. 실험 지역의 패치·핵심점·사진 곡선·판단·참값은 이 결과의 대상에 포함하지 않았다. 확인용은 전체 소속 검사에서 건물 번호만 확인했다.',
        '시선 검사에 원래 불확실도 제공점이 없는 건물은 대체값을 만들지 않았다. 해당 검사는 확인 불가이며 빈 공간 보정의 근거로 쓰지 않았다. 사진 선택이 3장 미만이면 발주문 순서상 MVS 면 없음보다 사진 부족이 먼저 적용된다.',
        '다른 발주가 GPU를 쓰는 것이 확인되면 사진 계산을 일시 정지하고 기다렸다. 프로세스 검사·정지·재개 시각은 대기 기록에 남겼다. 시작 전 검사와 실행 중 5초 간격 검사를 구분하며, 처음 실행 중 발견 전의 겹침 가능성도 숨기지 않는다. 대기 시간은 닫힌 정지·재개 구간과 연속 사용 중 관측 구간을 합친 최소값이다. 첫 수동 정지의 기록 지연과 중단한 표본의 마지막 정지 종료 시각 누락은 추정으로 채우지 않았다.',
        '앞선 캐시 준비 중단, 독립 검사 연결 키 수정과 실패 로그는 issues.md에 보존했다. 설정의 각 변경 시각·까닭·이전 SHA-256은 설정 이력에 있다.',
        f"현재 설정 SHA-256: `{sha(C/'judgecheck_v1.json')}`.",
        f"첫 설정 이후 총 경과는 {resources['task_elapsed_seconds']/3600:.2f}시간이며, 사용자 회신 대기를 포함한다. 회신 2 이후의 경과와 GPU 대기 최소값은 첫 다섯 줄에 따로 적었다.",
        '원본 수치와 출처는 tables/*.json 및 *.csv, 보기용 표는 *.md에 있다. 구역별 완료 기록과 시선 검사 기록도 보존했다. 이 보고는 과학적 결론을 내리지 않는다.']
    text='\n\n'.join(s)+'\n';assert len(text)<=20000,len(text)
    name='판단검증_지붕중간보고_v1.md' if mode=='roofs' else '판단검증_보고가_v1.md';(D/name).write_text(text)
    # Every durable table also has a Markdown view with its exclusion line.
    for p in (D/'tables').glob('*.json'):
        obj=load(p);rows=obj.get('rows')
        if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict):continue
        fields=list(dict.fromkeys(k for r in rows for k in r if not isinstance(r[k],(list,dict))))
        content=table(fields,[[num(r.get(k),6) if isinstance(r.get(k),float) else str(r.get(k,'')) for k in fields] for r in rows]);p.with_suffix('.md').write_text('[이 발주에서 냄]\n\n'+content)
    dump(BASE/'reports'/f'{mode}.json',dict(at=now(),report=name,characters=len(text),sha256=sha(D/name),scientific_verdict=None));print('REPORT_WRITTEN',name,len(text),flush=True)
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'full')
