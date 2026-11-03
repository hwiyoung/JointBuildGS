"""Concise Korean Report A and immutable roof interim, with all detailed tables."""
import json,sys,csv,re
from preflight import C,D,O,Path,sha,dump,now
from resources_reply2 import main as resource_receipt
BASE=O/'r2';LABEL={'ALS_1':'항공 LiDAR 지붕','LoD2_1':'LoD2 지붕','LoD2_2':'LoD2 벽'}
VAR={'new_clipped':'본 규칙','new_unclipped':'고친 사진·자르지 않음','new_oldphoto':'옛 사진','old_rule':'옛 규칙','always_prior':'늘 사전 정보','always_mvs':'늘 영상'}
ARM={'main':'본 방법','all_oracle':'모두 정답','geometry_oracle':'기하 검사만 정답','cause_oracle':'원인 판별만 정답','always_mix':'늘 섞음','always_prior':'늘 사전 정보','always_mvs':'늘 영상','default_only':'사진 없이 기본 방향','oldphoto':'옛 사진'}
STRATUM={'all':'전체','normal_fallback':'2.0 m 대체','normal_rule_met':'규칙 충족'}
PRECISION={'MVS':'MVS / √(u_M²+σ_W²)','prior_sigmaP':'사전 정보 / σ_P','prior_sigmaP_plus_sigmaW':'사전 정보 / √(σ_P²+σ_W²)'}
EX='실험 지역과 사진 점을 공유해 뺀 핵심점: 73개, 5.442552935831812 m². 모든 계산의 대상에서 제외했다.'
DX={'u_M_missing':'u_M 없음','u_M_missing_n_lt4':'u_M 없음·0≤n<4','u_M_missing_n_unknown':'u_M 없음·n 확인 불가','u_M_missing_n_ge4_uncountable':'n≥4·u_M 없음(셀 수 없음)','unknown_reason_exclusive:normal_missing':'기하 확인 불가: 법선 없음','unknown_reason_exclusive:prior_height_missing':'기하 확인 불가: 사전 높이 없음','unknown_reason_exclusive:u_M_missing':'기하 확인 불가: u_M 없음','unknown_reason_exclusive:sigma_P_missing':'기하 확인 불가: σ_P 없음'}
TIME={'tile_load_and_tree_seconds':'구역 점군·탐색 구조','per_point_plane_and_visibility_seconds':'점마다 면·사진 선택','prepared_output_seconds':'준비 값 저장','gpu_image_cache_read_and_upload_seconds':'사진 읽기·전송(구역·자료 판마다)','gpu_packed_arithmetic_seconds':'사진 점수·합치기'}
COMPACT=False
TABLE_SHORT={'항공 LiDAR 지붕':'항공','LoD2 지붕':'LoD지붕','LoD2 벽':'LoD벽',
    '고친 사진·자르지 않음':'안자름','고친 사진':'고친','옛 사진':'옛사진',
    '늘 사전 정보':'늘사전','늘 영상':'늘영상','사진 없이 기본 방향':'기본방향',
    '기하 검사만 정답':'기하정답','원인 판별만 정답':'원인정답',
    '정규화 오차 중앙값':'오차 중앙값','중앙값을 뺀 NMAD':'중심 NMAD',
    '보존(사진 지지)':'보존·사진','보정(사진 반박)':'보정·사진','보존(기본 방향)':'보존·기본','보정(기본 방향)':'보정·기본','보정(빈 공간)':'빈 공간',
    'MVS / √(u_M²+σ_W²)':'MVS','사전 정보 / √(σ_P²+σ_W²)':'사전+W','사전 정보 / σ_P':'사전',
    '기하 확인 불가: ':'불가: ','확인 불가':'불가'}
def compact_cell(value):
    value=str(value).replace('|','/')
    for old,new in TABLE_SHORT.items():value=value.replace(old,new)
    value=value.replace(' / ','/')
    if value in ['0/0','0%']:return '0'
    if re.fullmatch(r'[\d,./%+−-]+',value):value=value.replace(',','')
    return value
def load(p):return json.loads(p.read_text())
def num(x,d=2):
    if x is None:return '확인 불가'
    if COMPACT and d==2:d=1
    value=f'{x:,.{d}f}'
    return value.rstrip('0').rstrip('.') if d else value
def pct(x):return '확인 불가' if x is None else f'{x*100:,.2f}'.rstrip('0').rstrip('.')+'%'
def cell_text(row,key):
    if key not in row:return ''
    value=row[key]
    if value is None:
        if key in ['denominator_count','denominator_area_m2'] or (key=='fraction' and row.get('denominator_area_m2') is None):return '해당 없음'
        return '확인 불가'
    return num(value,6) if isinstance(value,float) else str(value)
def table(headers,rows):
    render=compact_cell if COMPACT else lambda v:str(v).replace('|','/')
    rendered=[list(map(render,r)) for r in rows]
    if COMPACT:
        previous=None
        for row in rendered:
            label=row[0]
            if label==previous:row[0]=''
            previous=label
    if COMPACT:
        # GFM permits single-hyphen separators and optional outer pipes.
        # Keep outer pipes for rows whose first cell is intentionally empty.
        lines=['|'.join(map(render,headers)),'|'.join(['-']*len(headers))]
        lines+=['|'+'|'.join(r)+'|' if not r[0] else '|'.join(r) for r in rendered]
    else:lines=['|'+'|'.join(map(render,headers))+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(r)+'|' for r in rendered]
    footer='실험 지역과 사진 점을 공유해 뺀 핵심점: 항공 73개·5.44 m².'
    if COMPACT:footer=footer.replace(': 항공 ',': ')
    return '\n'.join(lines)+'\n\n'+footer+'\n'
def compact_prose(text):
    # Report-only wording. Detailed tables, numbers, source records and the
    # committed roof interim remain intact.
    replacements={
      '보고서의 건물 번호는 공통 접두사 DEBY_LOD2_를 생략한다. 표의 제외 행은 발주 전체 공통이다.':'건물 번호의 DEBY_LOD2_는 생략했다. 제외 행은 발주 공통이며 표 첫 열의 빈칸은 윗줄과 같다.',
      '기하 검사와 시선 검사의 나머지 확인 불가는 아래에 수·넓이·까닭을 적었다.':'나머지 수·넓이·까닭은 아래 표에 있다.',
      '각 칸은 m²/%다. 분모는 참값이 있고 기하 검사가 가능한':'칸=m²/%. 참값·기하 가능 분모',
      ' m²이며 각 판의 합은 100%다. 별도: ':' m², 판마다 합 100%. 별도: ',
      '처음 연결에서 읽은 공유 곡선 22개에서 나온 값은 이 보고의 어떤 표·그림·설정에도 들어가지 않았다. 처음 준비 파일은 재현 기록으로만 보존하며 전달 묶음에 넣지 않는다.':'처음 읽은 공유 곡선 22개의 값은 표·그림·설정에 쓰지 않았다. 처음 준비 파일은 재현 기록이며 전달에서 제외했다.',
      'LoD2 지붕의 5% 확인은 참고값이다. 정밀도 확인에는 참값의 오차 크기로 고른 부분을 쓰지 않았다.':'LoD2 지붕의 5% 확인은 참고다. 정밀도 표본은 참값 오차로 고르지 않았다.',
      '원인별 수는 위에서부터 정상 법선 없음 → 사전 높이 없음 → MVS 높이 없음 → u_M 없음 → σ_P 없음 → σ_W/r 없음 순서로 한 번만 센 값이다. 원인이 겹치는 수와 넓이도 JSON/CSV에 별도로 남겼다.':'기하 불가 원인은 법선→사전 높이→MVS 높이→u_M→σ_P→σ_W/r 순서로 한 번만 셌다. 겹침은 JSON/CSV에 있다.',
      '최대 구역 전체의 float64 CPU/GPU 일치와 기존 200점 중 공통 27점의 점수·면·법선·사진·마스크 일치 기록을 남겼다.':'최대 구역 전체 CPU/GPU 일치와 기존 표본 공통 27점의 점수·면·법선·사진·마스크 일치 확인.',
      'LoD2 지붕의 남은 독립 구역은 CPU 두 작업으로 나눴다(각 4 CPU·28 GiB·nice 19, 시작 전 가용 36 GiB 확인). NPY 캐시 준비는 공통 잠금으로 직렬화했으며 따로 계측하지 않은 잠금 대기도 포함된다. 두 작업 완료 뒤 판단했다. 실행 시간 합은 병렬 작업의 경과 시간과 다르다.':'지붕의 남은 구역은 CPU 2작업(각 4 CPU·28 GiB·nice 19, 시작 전 가용≥36 GiB)으로 계산했다. NPY 준비에는 잠금 대기도 포함된다. 두 작업 완료 뒤 판단했다. 실행 시간 합과 병렬 경과 시간은 다르다.',
      '벽은 GPU의 다른 연구 사용을 확인한 뒤 같은 한도의 CPU 두 작업으로 끝까지 계산했다. 각 작업의 JPEG 캐시는 독립적이며, 공통 잠금은 축소 단계 번호 준비에만 걸었다. 두 작업이 모두 끝난 뒤 판단·집계했다.':'벽도 같은 CPU 2작업으로 계산했다. JPEG 캐시는 독립적이고 축소 단계 번호 준비만 잠갔다. 모두 완료 뒤 판단했다.',
      '대상 3은 7절의 평가 전용이다. 대상 2와 겹쳐도 원래 일치 표본의 소속을 바꾸지 않았다.':'대상 3은 7절 전용이며 대상 2 소속은 그대로다.',
      't는 참값을 쓰지 않은 원래 일치 표본의 자른 사전 정보 면 점수에서 구했다. 자르지 않은 판에도 같은 t를 써서 자르기의 차이를 표시했다.':'t는 참값 없이 원래 일치 표본의 자른 사전 면 점수에서 구했다. 안자름에도 같은 t를 썼다.',
      '6절의 고친 사진 진단은 대상 1·2만, 일치 표본 행은 원래 대상 2만 썼다. 대상 3만의 값은 7절 전용이다. 각도는 중복을 뺀 사진 점의 분포이며 넓이 가중 분포도 상세 표에 있다.':'6절은 대상 1·2, 일치 표본은 원래 대상 2다. 각도는 중복 없는 사진 점 분포이며 넓이 가중값은 상세 표에 있다.',
      '분모는 새 한계 밖의 칸 0·1·2다. 옛 규칙만 자기 한계와 옛 칸을 썼다. 칸 1에서 보정하지 않음과 칸 2에서 보정함을 틀림으로 셌다. 전체 넓이 대비의 분모는 사전 높이·법선이 있는':'분모: 새 한계 밖 칸0·1·2(옛 규칙은 옛 한계·칸). 틀림: 칸1 미보정+칸2 보정. 전체 분모: 사전 높이·법선이 있는',
      '오차 평균·중앙값은 넓이 가중이다. 면 없음은 참값 면이 있는 곳에서 틀림이며 높이 오차 통계에서 빼고 넓이를 적었다. 참값 없는 칸 6은 빈 공간의 정답으로 보지 않았다. 칸 0~5별 값은 상세 표에 있다.':'오차는 넓이 가중이다. 면 없음은 참값 면이 있으면 틀림, 높이 오차에서는 제외다. 칸6은 빈 공간 정답이 아니다. 칸0~5별 표는 별첨이다.',
      '그림별 JSON에 점·사진·값이 있다. 지도는 사전 정보 면의 5 cm 격자에 학습 영상을 투영하고 가림을 검사했다. 빨간 경계는 판단이 해를 끼친 이웃 칸이다. 수동 까닭은 빈칸이다. 1 m² 미만·자리 부족은 아래에 적었다.':'그림별 JSON에 점·사진·값이 있다. 지도는 사전 면의 5 cm 격자에 학습 영상을 투영·가림 검사했다. 빨강은 해를 끼친 이웃 칸이며 수동 까닭은 빈칸이다.',
      '회신 1의 공통 제외와 전체 소속 검사, 회신 2의 구역/사진 묶음 계산과 대상 3을 적용했다. 사진 점 번호는 지붕과 벽에서 겹칠 수 있어 (구역, 사전 정보, 지붕/벽, 점 번호)를 연결 키로 쓴다. 옛 곡선은 다시 계산하지 않았다.':'회신 1·2를 적용했다. 사진 연결 키는 (구역, 사전 정보, 지붕/벽, 점 번호)다. 옛 곡선은 재계산하지 않았다.',
      '원시 이웃 점/화소의 실험 지역 포함은 회신 1에서 허용한 범위다. 실험 지역의 패치·핵심점·사진 곡선·판단·참값은 이 결과의 대상에 포함하지 않았다. 확인용은 전체 소속 검사에서 건물 번호만 확인했다.':'원시 이웃 점·화소는 회신 1의 허용 범위다. 실험 지역 소속 값은 제외했고 확인용은 소속 번호만 검사했다.',
      '시선 검사에 원래 불확실도 제공점이 없는 건물은 대체값을 만들지 않았다. 해당 검사는 확인 불가이며 빈 공간 보정의 근거로 쓰지 않았다. 사진 선택이 3장 미만이면 발주문 순서상 MVS 면 없음보다 사진 부족이 먼저 적용된다.':'원래 불확실도 제공점 없는 시선 검사는 불가로 두었다. 사진<3장은 발주 순서상 MVS 면 없음보다 먼저 적용된다.',
      'GPU는 시작 전·실행 중 5초 간격으로 검사했다. 다른 연구를 발견하면 자체 계산을 정지했다. 최초 발견 전 겹침 가능성, 첫 정지 기록 지연과 중단 표본의 종료 시각 누락은 issues.md에 남겼다. 대기는 닫힌 구간과 연속 관측으로 확인한 최소값이며 미기록 시간을 추정하지 않았다.':'GPU는 시작 전·실행 중 5초마다 검사하고 다른 연구 발견 시 자체 계산을 정지했다. 발견 전 겹침 가능성·정지 기록 지연·중단 종료 시각 누락은 issues.md에 있다. 대기는 관측된 최소값이다.',
      '앞선 캐시 준비 중단, 독립 검사 연결 키 수정과 실패 로그는 issues.md에 보존했다. 설정의 각 변경 시각·까닭·이전 SHA-256은 설정 이력에 있다.':'중단·수정·실패 로그는 issues.md, 설정 변경 시각·까닭·이전 SHA-256은 설정 이력에 있다.',
      '실행별 Docker·Git·자원 원장은 11월 3일 13:58부터 수집했다. 이전 컨테이너 값은 추정하지 않았다. 코드·입출력 SHA-256과 환경 버전은 잠금 기록에 있다.':'Docker·Git·자원 원장은 11월 3일 13:58부터다. 이전 값은 추정하지 않았다. 코드·입출력·환경은 잠금 기록에 있다.'}
    for old,new in replacements.items():text=text.replace(old,new)
    return re.sub(r'\n{3,}','\n\n',text)
def building_label(value):return value.removeprefix('DEBY_LOD2_')
def readtable(g,k):return load(D/'tables'/f'{g}_{k}.json')['rows']
def main(mode='full'):
    global COMPACT
    preview=mode=='preview_roofs';COMPACT=mode in ['full','preview_roofs']
    if preview:mode='roofs'
    if not preview:resource_receipt()
    resources=load(BASE/'resource_receipt.json')
    groups=['ALS_1','LoD2_1']+(['LoD2_2'] if mode=='full' else []);summary={g:load(BASE/'metrics'/f'{g}.json') for g in groups};cal=load(O/'r1/geometry_calibration.json');diagnostics=load(BASE/'diagnostics.json');timing=load(BASE/'timing_estimate.json');s=[]
    ranges=[];errors=[];ab=[];uncountable_u=sum(r['count'] for r in diagnostics['rows'] if r['group'] in groups and r['metric']=='u_M_missing_n_ge4_uncountable')
    for g,r in summary.items():
        buildings=122 if g=='ALS_1' else 125;ranges.append(f"{LABEL[g]} {buildings}동, {r['core_count']:,}개, {r['area_m2']:,.2f} m²")
        a={x['variant']:x for x in r['accuracy'] if x['stratum']=='all'};errors.append(LABEL[g]+': '+ '/'.join(pct(a[v]['fraction']) for v in ['new_clipped','always_prior','always_mvs']))
        aa={x['arm']:x for x in r['ablation']};ab.append(LABEL[g]+': '+pct(aa['main']['within_tau_fraction'])+' / '+pct(aa['all_oracle']['within_tau_fraction']))
    s+=['# 판단 검증 — '+('지붕 중간 보고' if mode=='roofs' else '보고 가'),'', '범위: '+'; '.join(ranges)+'.','판단이 틀린 비율(본 규칙 / 늘 사전 정보 / 늘 영상): '+'; '.join(errors)+'.','7절 τ 안 비율(본 방법 / 모두 정답): '+'; '.join(ab)+'.',
        f'확인 불가: n≥4인데 u_M이 없는 {uncountable_u:,}개는 셀 수 없음이다. 기하 검사와 시선 검사의 나머지 확인 불가는 아래에 수·넓이·까닭을 적었다.',f"시간: 회신 2 시작 후 {resources['elapsed_seconds']/3600:.2f}시간 경과, 기록으로 확인된 GPU 대기 최소 {resources['gpu_wait_recorded_minimum_seconds']/3600:.2f}시간. 캐시 수정 전 전체 어림 GPU {timing['estimated_hours']:.2f}시간, CPU {timing['cpu_estimated_hours']:.2f}시간(25% 여유 포함).",
        '',('상태: 지붕의 6~8절 중간 보고다. 이 보고를 커밋한 뒤 벽을 계속한다.' if mode=='roofs' else '상태: 개발용 단계 가를 마쳤다. 이 보고 뒤 멈추며, σ_W와 r의 단계 나 적용값은 다음 회신에서 잠근다.'),
        '학습 없음. 확인용 곡선·값 미개방. scientific_verdict: null. 새 값은 모두 [이 발주에서 냄]. 보고서의 건물 번호는 공통 접두사 DEBY_LOD2_를 생략한다. 표의 제외 행은 발주 전체 공통이다.',EX,
        '처음 연결에서 읽은 공유 곡선 22개에서 나온 값은 이 보고의 어떤 표·그림·설정에도 들어가지 않았다. 처음 준비 파일은 재현 기록으로만 보존하며 전달 묶음에 넣지 않는다.',
        '', '## 기하 검사 (6.5)',f"σ_W={cal['sigma_W_m']*100:.6f} cm. 사용 건물 {cal['building_count']}동, 건물 중앙값의 10·90% 값 {num(cal['building_median_q10_q90_m'][0]*100,4)}, {num(cal['building_median_q10_q90_m'][1]*100,4)} cm. 참값은 이 값과 r을 구하는 데 쓰지 않았다."]
    if COMPACT:s.append('약칭: 항공=항공 LiDAR 지붕, LoD=LoD2, 안자름=자르지 않은 고친 판. 기하/원인정답=해당 단계만 정답. 정밀도: MVS=√(u_M²+σ_W²), 사전=σ_P, 사전+W=√(σ_P²+σ_W²). 불가=확인 불가. 넓이 1자리, 비율 2자리(교차표 1자리) 반올림. 정확한 값은 JSON/CSV에 있다. 교차표 0=0 m²/0%.')
    rows=[]
    for g in groups:
        gg=readtable(g,'6_5_geometry');limits={r['q']:r['value_m'] for r in gg if r['metric']=='limit_quantile'};ref=next(r['value_m'] for r in gg if r['metric']=='r_reference_cell0_median')
        rows.append([LABEL[g],num(cal['r_m'][g]*100,4),num(ref*100,4) if ref is not None else '확인 불가',' / '.join(num(limits[q]*100,3) if limits[q] is not None else '확인 불가' for q in [.25,.5,.75])])
    s.append(table(['자료','r(cm)','칸0 d 중앙값(cm, 참고)','L 25/50/75%(cm)'],rows))
    rows=[]
    for g in groups:
        for r in readtable(g,'6_5_precision'):rows.append([LABEL[g],PRECISION[r['source']],'전체' if r['roof_type']=='all' else r['roof_type'],r['count'],num(r['normalized_median'],3),num(r['normalized_centered_NMAD'],3)])
    s.append(table(['자료','정밀도 식','지붕 형태','표본 수','정규화 오차 중앙값','중앙값을 뺀 NMAD'],rows))
    rows=[]
    for g in groups:
        for r in readtable(g,'6_5_geometry'):
            if r['metric']=='five_percent_check':rows.append([LABEL[g],r['z'],num(r['denominator_area_m2']),num(r['area_m2']),pct(r['fraction'])])
    s.append(table(['자료','계수','칸0 분모(m²)','한계 밖(m²)','비율'],rows));s.append('LoD2 지붕의 5% 확인은 참고값이다. 정밀도 확인에는 참값의 오차 크기로 고른 부분을 쓰지 않았다.')
    rows=[[r['radius_m'],num(r['q25']),num(r['median']),num(r['q75'])] for r in cal['als_radius_candidates']];s.append(table(['LiDAR 원통 반지름(m)','점 수 25%','중앙값','75%'],rows));s.append('선택한 원통 반지름은 0.75 m다.')
    gg=readtable('ALS_1','6_5_geometry');normal_rows=[r for r in gg if r['metric']=='normal_radius']
    s.append(table(['법선 반지름(m)','핵심점 수','핵심점 비율','넓이(m²)'],[[r['radius_m'],r['count'],pct(r['core_fraction']),num(r['area_m2'])] for r in normal_rows]))
    missing_prior=next(r for r in gg if r['metric']=='prior_height_missing');height_changes=[r for r in gg if r['metric']=='TIN_to_new_axis_height_quantile']
    s.append(f"사전 정보 높이 없음 {missing_prior['count']:,}개·{num(missing_prior['area_m2'])} m². TIN에서 새 축 높이까지 차이의 넓이 가중 10/25/50/75/90% 값(cm): "+'/'.join(num(r['value_m']*100,3) if r['value_m'] is not None else '확인 불가' for r in height_changes)+'.')
    rows=[]
    for g in groups:
        gg=readtable(g,'6_5_geometry');values={(r['half_length_m'],r['metric']):r for r in gg if 'half_length_m' in r}
        rows.append([LABEL[g]]+[num(values[length,metric]['area_m2']) for length in [5,10] for metric in ['missing_after_sight','free_space']])
    s.append(table(['시선 검사 뒤 넓이(m²)','5 m 결측','5 m 빈 공간','10 m 결측','10 m 빈 공간'],rows));s.append('옛 칸과 새 칸의 전체 교차표는 6.5 상세 표에 있다.')
    rows=[]
    for r in diagnostics['rows']:
        if r['group'] in groups and (r['metric'].startswith('u_M_missing') or (r['metric'].startswith('unknown_reason_exclusive') and r['count'])):rows.append([LABEL[r['group']],DX.get(r['metric'],r['metric']),r['count'],num(r['area_m2'])])
    s.append(table(['자료','확인 불가의 까닭/겹침','핵심점 수','넓이(m²)'],rows));s.append('원인별 수는 위에서부터 정상 법선 없음 → 사전 높이 없음 → MVS 높이 없음 → u_M 없음 → σ_P 없음 → σ_W/r 없음 순서로 한 번만 센 값이다. 원인이 겹치는 수와 넓이도 JSON/CSV에 별도로 남겼다.')
    e=diagnostics['edge_summary'];s.append(f"법선 규칙 미충족 66,552개(4,798.977724 m²)에서 지원점 경계 0.5 m 이내 넓이 비율은 {pct(e['fallback']['near_edge_area_fraction'])}, 나머지는 {pct(e['rule_met']['near_edge_area_fraction'])}다. 66,552개 중 194개는 법선 자체가 없다. 경계는 같은 건물의 남은 핵심점으로 만든 0.25 m XY 격자에서 빈 이웃 칸과 맞닿는 칸으로 정했다. 참값 지붕선과의 거리가 아니다. 이 정의는 집계 전에 잠갔다.")
    s+=['','## 사진 확인 (6.4)',f"대상 1·2·3 합계 {timing['all_targets']:,}점. 최대 구역 {timing['benchmark_tile']}의 {timing['benchmark_points']:,}점을 통째로 계산했다. 공통 비용을 점당 시간에 곱하지 않았다.",table(['전체 시간 어림의 항','시간(시)'],[[TIME.get(k,k),num(v/3600,3)] for k,v in timing['components_seconds'].items()]),'최대 구역 전체의 float64 CPU/GPU 일치와 기존 200점 중 공통 27점의 점수·면·법선·사진·마스크 일치 기록을 남겼다.']
    rows=[]
    for label,key in [('GPU 한 장','measured_scoring'),('CPU 2개 제한','measured_cpu_scoring')]:
        m=timing[key];rows.append([label,m['points'],m['camera_count'],num(m['image_cache_total_seconds']),num(m['upload_seconds']),num(m['arithmetic_and_reduction_seconds']-m['upload_seconds']),num(m['total_seconds'])])
    if not COMPACT:s.append(table(['최대 구역 실측','점','사진','읽기(초)','전송(초)','점수·합치기(초)','전체(초)'],rows))
    else:s.append('최대 구역 실측 GPU/CPU: '+num(timing['measured_scoring']['total_seconds'])+'/'+num(timing['measured_cpu_scoring']['total_seconds'])+'초. [항별 원값](tables/reply2_time_estimate.json).')
    s.append(f"전송에는 배열 변환·복사도 포함된다. 구역·자료 판 {timing['image_passes']}회마다 최대 구역의 사진 공통 비용을 보수적으로 넣었다. 시작 전 GPU 대기는 계산 시간에서 분리했다.")
    actual=resources['measurement_totals']['photo_scores']['by_device'];s.append('완료된 사진 계산의 실행 시간(최대 구역 GPU 측정 포함, 별도 CPU 비교 측정 제외): '+'; '.join(('GPU' if k=='cuda' else 'CPU')+f" {v['seconds']/3600:.3f}시간·{v['points']:,}점" for k,v in actual.items())+'. 다른 발주의 GPU 사용 중에는 검증을 마친 동일한 float64 CPU 셈을 사용했다.')
    if (C/'photo_stream.reply2.lock.json').exists():
        supply=load(BASE/'image_supply_benchmark.json');verification=load(BASE/'stream_verification/complete.json')
        applied='후속 계산 설정으로 잠갔다' if mode=='roofs' else '남은 벽 계산에 적용했다'
        if COMPACT:s.append(f"JPEG·4 GiB 캐시·프로세스 내부 큰 페이지 요청 해제를 적용했다. 같은 200점의 전체 곡선 차이는 {verification['max_curve_difference']:.3g}이다. 식·완료 값·호스트 설정은 그대로다. 비교 측정은 [기록](issues.md)에 있다. JPEG 해독은 전송 시간에 포함된다.")
        else:s.append(f"사진 공급 병목: 같은 8장 NPY 읽기·복사 {supply['total_npy_read_seconds']:.3f}초, JPEG 해독 {supply['total_jpeg_decode_seconds']:.3f}초, 픽셀 동일. 읽기·복사에는 메모리 할당도 포함된다. 별도 큰 페이지 요청 on/off/off/on 복사는 10.839/0.068/0.061/0.552초이며 바이트가 같았다. 동시 부하의 부분 측정으로 전체 속도 비율이 아니다. 200점 전체 곡선 차이 {verification['max_curve_difference']:.3g} 확인 뒤 JPEG·4 GiB 캐시·프로세스 내부 큰 페이지 요청 해제를 {applied}. 완료 결과·float64 식·호스트 설정은 그대로다. 이후 JPEG 해독은 아래 배열 공급·전송 시간에 포함된다. 위 어림은 앞 캐시의 측정 기록이다.")
    if (BASE/'cpu_cohorts').exists():
        if COMPACT:s.append('지붕·벽의 독립 구역은 CPU 2작업(각 4 CPU·28 GiB·nice 19, 시작 전 가용≥36 GiB)으로 계산하고 모두 완료 뒤 판단했다. NPY 준비에는 잠금 대기가 포함된다. 실측 합은 병렬 경과 시간과 다르다.')
        else:s.append('LoD2 지붕의 남은 독립 구역은 CPU 두 작업으로 나눴다(각 4 CPU·28 GiB·nice 19, 시작 전 가용 36 GiB 확인). NPY 캐시 준비는 공통 잠금으로 직렬화했으며 따로 계측하지 않은 잠금 대기도 포함된다. 두 작업 완료 뒤 판단했다. 실행 시간 합은 병렬 작업의 경과 시간과 다르다.')
    if not COMPACT and (BASE/'cpu_cohorts/group2/plan.json').exists():s.append('벽은 GPU의 다른 연구 사용을 확인한 뒤 같은 한도의 CPU 두 작업으로 끝까지 계산했다. 각 작업의 JPEG 캐시는 독립적이며, 공통 잠금은 축소 단계 번호 준비에만 걸었다. 두 작업이 모두 끝난 뒤 판단·집계했다.')
    if 'group2' in resources.get('cpu_cohort_elapsed',{}):
        w=resources['cpu_cohort_elapsed']['group2'];s.append(f"수정 후 남은 벽 {w['points']:,}점: CPU {w['workers']}작업의 실제 경과 {w['elapsed_seconds']/60:.2f}분.")
    s.append(table(['완료된 사진 계산 실측 합(시)','캐시 준비(대기 포함)','배열 변환·복사/전송','점수·합치기'],[[('GPU' if k=='cuda' else 'CPU')]+[num(v[field]/3600,3) for field in ['image_cache_seconds','upload_seconds','arithmetic_excluding_upload_seconds']] for k,v in actual.items()]))
    census=load(BASE/'target_census.json');targetrows=[]
    for g in groups:
        rr=[r for r in census['rows'] if r['prior']+'_'+str(r['kind'])==g];targetrows.append([LABEL[g]]+[sum(r[k] for r in rr) for k in ['type1_count','type2_count','type3_count','type2_type3_overlap_count','target_count']]+[num(sum(r['target_area_m2'] for r in rr))])
    s.append(table(['자료','대상1','대상2','대상3','2·3 겹침','중복 뺀 합','대상 넓이(m²)'],targetrows));s.append('대상 3은 7절의 평가 전용이다. 대상 2와 겹쳐도 원래 일치 표본의 소속을 바꾸지 않았다.')
    rows=[]
    for g in groups:
        t=load(C/f'photo_threshold.{g}.reply2.lock.json');rows.append([LABEL[g],num(t['t'],6),num(t['t10'],6),t['finite_score_points'],num(t['finite_score_area_m2'])])
    s.append(table(['자료','t(아래5%)','아래10%(참고)','유효 일치 표본 점','넓이(m²)'],rows));s.append('t는 참값을 쓰지 않은 원래 일치 표본의 자른 사전 정보 면 점수에서 구했다. 자르지 않은 판에도 같은 t를 써서 자르기의 차이를 표시했다.')
    for g in groups:
        rows=[]
        for vi in ['new_oldphoto','new_unclipped','new_clipped']:
            rr=[r for r in readtable(g,'6_4_photos') if r['variant']==vi]
            for label in dict.fromkeys(r['stratum'] for r in rr):
                vals=[r for r in rr if r['stratum']==label];pp={r['photo']:r for r in vals};den=vals[0]['denominator_area_m2'];percentages=[pct(pp[k]['fraction']) for k in ['지지','반박','옛 판 애매','애매(둘 다 낮음)','애매(둘 다 높음)','애매(MVS 면 없음)','애매(조각 부족)','무늬 없음','사진 부족','미계산/범위 없음']]
                if COMPACT:percentages=[p.removesuffix('%') for p in percentages]
                rows.append([VAR[vi],label.replace('일치 표본 한계 안 칸0','일치 표본').replace('한계 밖 ','밖 '),num(den)]+percentages)
        s.append('### '+LABEL[g]+' 사진 판단'+(' (지지~셀 수 없음은 %)' if COMPACT else ''));s.append(table(['판','부분','분모(m²)','지지','반박','옛 애매','둘 낮음','둘 높음','면 없음','조각 부족','무늬 없음','사진 부족','셀 수 없음'],rows))
    rows=[]
    for g in groups:
        rr=readtable(g,'6_4_planes');missing=next(x for x in rr if x['metric']=='MVS 면 없음');angles=[x for x in rr if x['metric']=='angle_photo_point_quantile'];rows.append([LABEL[g],missing['count'],num(missing['area_m2']),' / '.join(num(x['value_deg'],2) for x in angles)])
    s.append(table(['자료','MVS 면 없음(핵심점)','넓이(m²)','두 면 각 10/25/50/75/90%(°)'],rows));s.append('6절의 고친 사진 진단은 대상 1·2만, 일치 표본 행은 원래 대상 2만 썼다. 대상 3만의 값은 7절 전용이다. 각도는 중복을 뺀 사진 점의 분포이며 넓이 가중 분포도 상세 표에 있다.')
    s+=['','## 판단 (6.1~6.3)']
    if COMPACT:s.append('교차표에서 세미콜론으로 이은 영역은 반올림 전 값이 같다. 각 영역에 같은 값을 적용한다. 보존·사진=사진 지지, 보정·사진=사진 반박, 기본=기본 방향이다.')
    for g in groups:
        cross=readtable(g,'6_1_cross');rows=[];exact_rows={}
        for variant,panel,prefix in [('new_clipped','geometry','기하'),('new_clipped','judgment','고친 사진'),('new_oldphoto','judgment','옛 사진')]:
            rr=[x for x in cross if x['variant']==variant and x['panel']==panel and x['cell']<6]
            for label in dict.fromkeys(x['label'] for x in rr):
                cc={x['cell']:x for x in rr if x['label']==label}
                values=[num(cc[i]['area_m2'],1)+'/'+num(cc[i]['fraction']*100,1) if cc[i]['fraction'] is not None else '확인 불가' for i in range(6)]
                exact=tuple((cc[i]['area_m2'],cc[i]['fraction']) for i in range(6))
                if COMPACT and exact in exact_rows:rows[exact_rows[exact]][0]+='; '+prefix+' '+label
                else:exact_rows[exact]=len(rows);rows.append([prefix+' '+label]+values)
        denominator=next(x['denominator_area_m2'] for x in cross if x['cell']<6)
        separate=[x for x in cross if x['variant']=='new_clipped' and x['panel']=='geometry' and x['cell']>=6]
        s.append('### '+LABEL[g]+' 기하·판단과 칸 교차');s.append(f"각 칸은 m²/%다. 분모는 참값이 있고 기하 검사가 가능한 {num(denominator)} m²이며 각 판의 합은 100%다. 별도: "+'; '.join(x['label']+' '+num(x['area_m2'])+' m²' for x in separate)+'.')
        s.append(table(['판·영역','칸0','칸1','칸2','칸3','칸4','칸5'],rows))
        r=summary[g];rows=[[VAR[x['variant']],STRATUM[x['stratum']],num(x['denominator_area_m2']),num(x['area_m2']),pct(x['fraction']),pct(x['whole_roof_fraction'])] for x in r['accuracy']]
        s.append('### '+LABEL[g]+' 판단 정확도');s.append(table(['판','부분','분모(m²)','틀린 넓이(m²)','틀린 비율','전체 넓이 대비'],rows))
        s.append(f"분모는 새 한계 밖의 칸 0·1·2다. 옛 규칙만 자기 한계와 옛 칸을 썼다. 칸 1에서 보정하지 않음과 칸 2에서 보정함을 틀림으로 셌다. 전체 넓이 대비의 분모는 사전 높이·법선이 있는 {num(r['prior_height_valid_area_m2'])} m²다(법선 부분별 행에도 동일).")
        rows=[[building_label(x['building']),num(x['denominator_area_m2']),num(x['area_m2']),pct(x['fraction'])] for x in r['top15']];s.append(table(['틀린 넓이가 큰 15동','분모(m²)','틀린 넓이(m²)','틀린 비율'],rows))
        causes=readtable(g,'6_3_causes');rows=[]
        for v in ['new_clipped','new_unclipped','new_oldphoto']:
            rr=[x for x in causes if x['variant']==v];values={x['reason']:x['area_m2'] for x in rr};default=sum(x['area_m2'] for x in rr if x['reason'].startswith('기본 방향:'))
            rows.append([VAR[v],num(values['사진이 틀리게 지지']),num(values['사진이 틀리게 반박']),num(default),num(values['빈 공간 보정이 틀림(6.2 분모 밖)']),num(values['한계 밖 둘 다 틀림']),num(values['한계 안 사진 반박(전체 한계 안 분모)'])])
        s.append(table(['틀림의 까닭(m²)','틀린 지지','틀린 반박','기본 방향','빈 공간(분모 밖)','밖·둘 다 틀림','안·사진 반박'],rows))
    s.append('참값 없음·기하 확인 불가와 모름별 기본 방향 오류는 상세 표에 있다. 한계 안 반박은 대상 1·2에서 확인한 최소 비율이며, 계산한 부분을 분모로 한 값도 적었다.')
    s+=['','## 단계별 바꿔 끼우기 (7절)']
    for g in groups:
        rows=[[ARM[r['arm']],pct(r['within_tau_fraction']),num(r['mean_abs_error_m'],4),num(r['median_abs_error_m'],4),num(r['within_tau_difference_pp'],3 if COMPACT else 2),num(r['uncountable_area_m2'])] for r in summary[g]['ablation']]
        main=next(r for r in summary[g]['ablation'] if r['arm']=='main')
        s.append('### '+LABEL[g]);s.append(f"τ 채점 분모 {num(main['scored_area_m2'])} m², 유한 높이 오차 분모 {num(main['finite_error_area_m2'])} m². 아홉 판의 채점 분모는 같다.");s.append(table(['판','τ 안 비율','평균 오차(m)','중앙값(m)','본 방법과 차(%p)','셀 수 없음(m²)'],rows))
    s.append('오차 평균·중앙값은 넓이 가중이다. 면 없음은 참값 면이 있는 곳에서 틀림이며 높이 오차 통계에서 빼고 넓이를 적었다. 참값 없는 칸 6은 빈 공간의 정답으로 보지 않았다. 칸 0~5별 값은 상세 표에 있다.')
    s+=['','## 그림 (8절)']
    for p in sorted((D/'figures').glob('그림*.png')):
        if mode=='roofs' and '_all_' in p.name:continue
        if mode=='full' and p.name.startswith('그림2_LoD2_roofs_'):continue
        meta=load(p.with_suffix('.json'));prior_label='항공 LiDAR' if meta['prior']=='ALS' else 'LoD2'
        if p.name.startswith('그림1'):
            title=f"{prior_label} {building_label(meta['building'])}의 {meta['variant']} 판단을 참값과 비교한다."
            values='틀린 비율: 본 판 '+meta['wrong_rates'][0]+' / 늘 사전 정보 '+meta['wrong_rates'][1]+' / 늘 영상 '+meta['wrong_rates'][2]+'.'
        else:
            title=f"{prior_label} {building_label(meta['building'])} {'지붕' if meta['kind']==1 else '벽'}의 {meta['reason']}를 사진에서 확인한다."
            values=f"넓이 {num(meta['area_m2'])} m² / s_P {num(meta['s_P'],3)} / s_M {num(meta['s_M'],3)} / t {num(meta['threshold'],3)}."
        if COMPACT:
            title=title.replace('항공 LiDAR','항공').replace(' 판단을 참값과 비교한다.','과 참값을 비교한다.').replace('를 사진에서 확인한다.','의 사진을 본다.')
            if p.name.startswith('그림1'):
                title=f"{'항공' if meta['prior']=='ALS' else 'LoD2'} {building_label(meta['building'])}의 {meta['variant'].replace(' 사진','')} 판단과 참값이다."
                values='틀림%(본 판/늘사전/늘영상): '+'/'.join(meta['wrong_rates'])+'.'
        s.append(f"- [{title}](figures/{p.name})")
        s.append('  '+values)
    s.append('그림별 JSON에 점·사진·값이 있다. 지도는 사전 정보 면의 5 cm 격자에 학습 영상을 투영하고 가림을 검사했다. 빨간 경계는 판단이 해를 끼친 이웃 칸이다. 수동 까닭은 빈칸이다. 1 m² 미만·자리 부족은 아래에 적었다.')
    for prior in ['ALS','LoD2']:
        scope='all' if prior=='LoD2' and mode=='full' else 'roofs';sel=load(C/f'figure2.{prior}.{scope}.selection.reply2.json')
        s.append(f"{'항공 LiDAR' if prior=='ALS' else 'LoD2'} 사진 조각 {sel['selected_count']}/4자리. 1 m² 미만 {sel['below_1m2_count']}개·{num(sel['below_1m2_area_m2'])} m² 제외, 남은 후보 {sel['available_candidates']}개, 채우지 못한 자리 {sel['unfilled_slots']}개.")
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
        'GPU는 시작 전·실행 중 5초 간격으로 검사했다. 다른 연구를 발견하면 자체 계산을 정지했다. 최초 발견 전 겹침 가능성, 첫 정지 기록 지연과 중단 표본의 종료 시각 누락은 issues.md에 남겼다. 대기는 닫힌 구간과 연속 관측으로 확인한 최소값이며 미기록 시간을 추정하지 않았다.',
        '앞선 캐시 준비 중단, 독립 검사 연결 키 수정과 실패 로그는 issues.md에 보존했다. 설정의 각 변경 시각·까닭·이전 SHA-256은 설정 이력에 있다.',
        '실행별 Docker·Git·자원 원장은 11월 3일 13:58부터 수집했다. 이전 컨테이너 값은 추정하지 않았다. 코드·입출력 SHA-256과 환경 버전은 잠금 기록에 있다.',
        f"현재 설정 SHA-256: `{sha(C/'judgecheck_v1.json')}`.",
        f"첫 설정 이후 총 경과는 {resources['task_elapsed_seconds']/3600:.2f}시간이며, 사용자 회신 대기를 포함한다. 회신 2 이후의 경과와 GPU 대기 최소값은 첫 다섯 줄에 따로 적었다.",
        '수치·출처는 tables/*.json, *.csv, 보기용 표는 *.md다. 구역 완료·시선 검사 기록도 보존했다. 과학적 결론은 내리지 않는다.']
    text='\n\n'.join(s)+'\n'
    if COMPACT:
        text=compact_prose(text)
        boundary='## 바꾼 것·확인 불가·시간'
        text=text.split(boundary,1)[0]+boundary+'\n\n'+(
            '회신 1·2 적용. 사진 연결 키는 (구역, 사전 정보, 지붕/벽, 점 번호)다. 옛 곡선은 재계산하지 않았다. 원시 이웃 점·화소는 허용 범위이며 실험 지역 소속 값은 제외했다. 확인용은 소속 번호만 검사했다.\n\n'
            '제공점 없는 시선 검사는 불가로 두었다. GPU 검사 사이 겹침 가능성·정지 시각 누락·실패와 수정은 [기록](issues.md)에 있다. 대기는 관측된 최소값이다. 4 GiB 캐시의 퇴출 뒤 사진 재해독은 발생했다. 원장에 사진 수와 해독 횟수를 따로 적었다.\n\n'
            'Docker·Git·자원 원장은 11월 3일 13:58부터다. 이전 값은 추정하지 않았다. 변경 시각·까닭·이전 SHA-256은 설정 이력, 코드·입출력·환경은 잠금 기록에 있다.\n\n'
            f"설정 SHA-256: `{sha(C/'judgecheck_v1.json')}`. 최초 잠금 이후 {resources['task_elapsed_seconds']/3600:.2f}시간(회신 대기 포함). 회신 2 이후 경과와 GPU 대기는 첫머리에 있다.\n\n"
            '반올림 전 값·표본 수·출처는 tables의 JSON/CSV, 보기용은 MD다. 과학적 결론은 내리지 않는다.\n')
    if preview:
        (BASE/'reports/compact_roofs_preview.md').write_text(text)
        print('PREVIEW_ONLY',len(text),flush=True)
        for section in text.split('## '):print(section.splitlines()[0],len(section),flush=True)
        return
    assert len(text)<=20000,len(text)
    name='판단검증_지붕중간보고_v1.md' if mode=='roofs' else '판단검증_보고가_v1.md';(D/name).write_text(text)
    # Every durable table also has a Markdown view with its exclusion line.
    COMPACT=False
    for p in (D/'tables').glob('*.json'):
        obj=load(p);rows=obj.get('rows')
        if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict):continue
        fields=list(dict.fromkeys(k for r in rows for k in r if not isinstance(r[k],(list,dict))))
        content=table(fields,[[cell_text(r,k) for k in fields] for r in rows]);p.with_suffix('.md').write_text('[이 발주에서 냄]\n\n'+f'[반올림 전 값과 출처]({p.name})\n\n'+content)
    dump(BASE/'reports'/f'{mode}.json',dict(at=now(),report=name,characters=len(text),sha256=sha(D/name),scientific_verdict=None));print('REPORT_WRITTEN',name,len(text),flush=True)
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'full')
