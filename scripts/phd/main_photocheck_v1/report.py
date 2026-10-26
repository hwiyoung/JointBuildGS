"""Korean measurement report; no scientific verdict, parameter selection, or causal claims."""
import argparse
from common import *
from evaluate import join
def percent(x):return '확인 불가' if x is None else f'{100*x:.2f}%'
def table(rows,cols):
    out=['| '+' | '.join(label for key,label in cols)+' |','| '+' | '.join(['---']*len(cols))+' |']
    for r in rows:
        vals=[]
        for key,label in cols:
            v=r.get(key)
            if 'fraction' in key:vals.append(percent(v))
            elif v is None:vals.append('확인 불가')
            elif isinstance(v,float):vals.append(f'{v:.4f}')
            else:vals.append(str(v))
        out.append('| '+' | '.join(vals)+' |')
    return '\n'.join(out)
def rows(name,stage):return load(D/'tables'/stage/(name+'.json'))['rows']
def figure_index():
    lines=['# 사진 확인 그림 목록','', '모든 그림은 PNG 300dpi이며 같은 이름의 JSON에 사용한 점·사진·값을 남겼다. [이 발주에서 냄]', '', 'scientific_verdict: null.','']
    for folder,label in [('projection','사진 투영'),('pilot','시범'),('full','전체')]:
        files=sorted((D/'figures'/folder).glob('*.png'));lines += [f'## {label}: {len(files)}장','']
        for file in files:
            relative=file.relative_to(D);lines.append(f'- [{file.stem}]({relative.as_posix()}) · [JSON]({relative.with_suffix(".json").as_posix()})')
        lines.append('')
    (D/'그림목록_v1.md').write_text('\n'.join(lines).rstrip()+'\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);a=ap.parse_args();stage=a.stage;cfg=load(C/'photocheck_v1.json');gate=load(O/'gates/pilot.json')
    lines=[];scope=load(O/'geometry_summary.json')['rows'];wait=sum(float(p.read_text()) for p in (O/'logs').glob('*_gpu_wait_seconds.txt'))
    if stage=='full':sc=load(O/'final_export.json')['rows'];scope=sc
    else:
        sc=[]
        for prior in ['LoD2','ALS']:
            patches,points=join(prior,'pilot');m=patches['kind']==1;totalp=int((points['kind']==1).sum());totalpatch=int(m.sum());area=float(patches['area'][m].sum())
            sc.append(dict(prior=prior,holdout=False,points=totalp,patches=totalpatch,area_m2=area))
    scope_line='; '.join(f'{r["prior"]}: {r["points"]:,}점, {r["patches"]:,}패치, {r["area_m2"]:,.2f}m²' for r in sc if not r['holdout'])
    files=[p for p in (O/'work'/stage).glob('*.json') if not p.stem.endswith('_selection') and '_progress' not in p.stem]
    times=[load(p) for p in files];sec=sum(float(r.get('seconds',0)) for r in times)
    execution=load(O/'execution_summary.json') if stage=='full' and (O/'execution_summary.json').exists() else None
    elapsed=(f'입력 점검부터 보고서 준비까지 {execution["elapsed_from_input_preflight_hours"]:.3f}시간, 유효 곡선 계산 누적 {(execution["completed_full_curve_seconds"]+execution["valid_pilot_curve_seconds"])/3600:.3f}시간(시범 벽 관찰 포함)' if execution else f'이 단계 곡선 {sec/3600:.3f}시간')
    lines += [f'범위: 정하는 곳 {scope_line}. [이 발주에서 냄]',
      '확인 불가: 원본 법선·불확실도가 없거나 사진·무늬가 부족한 점은 해당 사유를 보존했다. 사진과 곡선에서 원인을 붙이지 않았다.',
      f'걸린 시간: {elapsed}, GPU 대기 누적 {wait:.0f}초. 사진 선정·그림·검증은 실행 기록에 따로 남겼다. [이 발주에서 냄]',
      '',f'# 사진 확인 {"중간 보고" if stage=="pilot" else "보고"} v1','',
      '작업: PHD-MAIN-PHOTOCHECK-v1. 학습 없음. scientific_verdict: null. 모든 새 표와 그림은 [이 발주에서 냄]이다.',
      '', '## 설정과 입력','',
      f'학습 사진 819장만 썼다. 원본 5280×3956 사진, FULL_OPENCV 카메라, 세계→카메라 포즈를 사용했다. 넓히기 v2 MVS 입력의 같은 이름 819장과 포즈가 일치했다. 현재 설정 SHA-256: `{sha(C/"photocheck_v1.json")}`.',
      '좌표는 EPSG:25832에서 [690953, 5336071, 604]m를 뺀 값이다. 사전 정보 메시에는 넓히기 v2의 타일별 등록 이동을 그대로 적용했다. 원본 입력과 앞 작업 결과는 읽기 전용이었다.',
      '점은 같은 면의 0.5m 칸으로 묶고 중심은 넓이 가중 평균, 법선은 평균을 단위 길이로 바꾼 값이다. 접선은 원본 격자 벡터를 단위 방향으로 바꿔 썼다. 같은 칸에 건물이 여럿이면 모두 기록하고 패치 표는 원래 건물 번호를 쓴다. 개발·확인용 경계만 나누며 면별 원점은 같다. 빈 기하 정보는 참값으로 채우지 않았다.',
      'MVS와 항공 LiDAR 불확실도에는 2.75cm를 제곱합으로 더했다. LoD2는 평지붕 16.6, 외쪽 9.8, 박공 22.3, 모임 11.4, 둥근 지붕 23.8, 그 밖 11.0cm, 관찰용 벽 14.4cm다. 넓히기 v2 칸과 τ는 그대로다.',
      '사진은 사전 정보 높이에서 한 번 골랐다. 높이별 가려짐은 다시 구하지 않는다. 가려짐은 동일한 등록 메시의 연속 화소 광선 깊이로 구했다. 메시 밖의 표현되지 않은 구조물은 가려짐에 포함되지 않는다.',
      '높이는 기본 141개이며 MVS 높이가 ±5m 밖이면 그 높이와 ±0.1·0.2·0.3m를 더했다. 50cm 정사각형의 25×25 표본을 쌍선형 보간했다. 조각 전체가 사진 밖이면 해당 높이에서만 그 사진을 뺐다. 밝기 분산 0인 조각의 상관은 비웠다.',
      '투영은 64비트, 밝기 보간과 상관은 32비트, 저장 곡선은 16비트다. 뽑은 값과 15가지 판단은 16비트 저장 전 점수에서 구했다. 원래 설정과 정밀도 변경 시각·까닭을 함께 보존했다.',
      '', '## 단계 가: 투영과 시간','',
      f'숫자 점검: 조건을 채운 {gate["eligible_points"]:,}점 가운데 {gate["within_10cm"]:,}점({percent(gate["fraction"])})의 |h_max|가 10cm 안이다. 통과 조건은 100점 이상이며 절반 초과다. 참값을 쓰지 않았다. 결과: {gate["status"]}.',
      f'시간 어림: GPU 한 장 {gate["time_estimate"]["gpu_hours"]:.3f}시간, CPU {gate["time_estimate"]["cpu_hours"]:.3f}시간. 실제 시범 처리율로 다시 구한 전체 어림은 {gate["time_estimate"]["from_actual_pilot_stage_b_gpu_hours"]:.3f}시간이다. 사진 읽기 상태에 따라 달라질 수 있다.',
      '사진 투영 그림은 예 건물 여섯 동×사전 정보 둘×사진 두 장으로 만들었다. 큰 건물은 한 사진에 담긴 부분만 표시하고 표시한 점 수와 전체 점 수를 그림 JSON에 적었다. 사전 정보가 실제 지붕과 다른 부분을 억지로 맞추지 않았다.',
      '', '## 판단 넓이와 참값 점검','',
      '보기 값은 δ=0.10, s_min=0.3이다. 선택한 최종 매개변수가 아니다. 참값 점검은 gt_status=0이고 gt_p와 사전 정보 불확실도가 있는 패치만 쓴다. 맞음은 |gt_p|≤3σ다. 전체 지붕 판단 넓이와 참값이 있는 점검 넓이를 별도 분모로 남겼다.',
      '차가 설명 안 되는 곳은 |mvs_p|>3√(σ사전²+σMVS²)이다. 9절의 원래 u 구간 표시는 원본 u 값이며, 계산의 σ에는 새 바닥값을 적용했다.']
    for prior in ['LoD2','ALS']:
        allrows=rows(prior+'_summary_15',stage);rr=[r for r in allrows if r['scope']=='all_roof'];gt=[r for r in allrows if r['scope']=='gt_known']
        display=next(r for r in rr if r['combination']==4);gtdis=next(r for r in gt if r['combination']==4)
        lines += ['',f'### {prior}','',f'보기 값 넓이: 지지 {display["support_area_m2"]:,.2f}, 반박 {display["refute_area_m2"]:,.2f}, 모름(애매) {display["ambiguous_area_m2"]:,.2f}, 모름(무늬 없음) {display["textureless_area_m2"]:,.2f}, 모름(사진 부족) {display["few_photos_area_m2"]:,.2f}m².',
          f'참값이 있는 넓이의 점검: 지지 중 맞음 {percent(gtdis["support_prior_right_fraction"])}, 반박 중 맞음 {percent(gtdis["refute_prior_right_fraction"])}. 참값·σ가 없어 점검에서 빠진 넓이 {display["missing_gt_or_sigma_area_m2"]:,.2f}m².',
          '',table(rr,[('delta','δ'),('s_min','최소 점수'),('support_area_fraction','지지'),('refute_area_fraction','반박'),('ambiguous_area_fraction','애매'),('textureless_area_fraction','무늬 없음'),('few_photos_area_fraction','사진 부족'),('support_prior_right_fraction','지지 중 맞음'),('refute_prior_right_fraction','반박 중 맞음'),('decided_area_fraction','판단 선 넓이')]),
          '', '칸 교차표, 차가 설명 안 되는 곳의 15가지 표, 지붕 형태·불확실도·시차·사진 수·무늬·MVS 누락·건물별 표는 같은 단계의 tables에 있다. 반올림 전 값과 패치 수·넓이 분모를 JSON·CSV·MD에 남겼다.']
        group=rows(prior+'_groups',stage);bb=sorted([r for r in group if r['dimension']=='building' and r['scope']=='gt_known'],key=lambda r:-r['unexplained_area_m2'])[:30]
        lines += ['', '차가 설명 안 되는 넓이가 큰 건물:', '',table(bb,[('label','건물'),('unexplained_area_m2','설명 안 됨 m²'),('support_area_m2','지지 m²'),('refute_area_m2','반박 m²'),('support_prior_right_fraction','지지 중 맞음'),('refute_prior_right_fraction','반박 중 맞음')])]
        ee=[r for r in rows(prior+'_expectations_15',stage) if r['combination']==4]
        expectation={'prior_wrong_refuted':'절반 초과','image_wrong_supported':'절반 초과','both_right_refuted':'5% 아래'}
        ee=[dict(**r,expectation=expectation[r['measure']]) for r in ee]
        names={'prior_wrong_refuted':'사전 정보만 틀림에서 반박','image_wrong_supported':'영상만 틀림에서 지지','both_right_refuted':'둘 다 맞음에서 반박'}
        ee=[dict(**r,measure_ko=names[r['measure']]) for r in ee]
        lines += ['', '결과 전 기대와 보기 값의 관측값(판정 없음):','',table(ee,[('measure_ko','항목'),('expectation','앞서 적은 기대'),('fraction','관측'),('denominator_area_m2','분모 m²')])]
        lines += [f'2.1의 참값 대응 기대: 지지 중 맞음 98% 위 / 관측 {percent(gtdis["support_prior_right_fraction"])}; 반박 중 맞음 85% 아래 / 관측 {percent(gtdis["refute_prior_right_fraction"])}. 유효 확률의 추정값이 아니며 후보를 선택하지 않았다.']
        ud=next(r for r in allrows if r['scope']=='unexplained_gt_known' and r['combination']==4)
        lines += [f'차가 설명 안 되는 곳만의 같은 대응값: 지지 중 맞음 {percent(ud["support_prior_right_fraction"])}, 반박 중 맞음 {percent(ud["refute_prior_right_fraction"])}. 분모 넓이는 각각 {ud["support_gt_area_m2"]:.2f}, {ud["refute_gt_area_m2"]:.2f}m²다.']
        dist=[r for r in rows('point_distributions',stage) if r['prior']==prior and r['measure'] in ['parallax','selected_count','texture','patch_count']]
        names={'parallax':'시차','selected_count':'고른 사진 수','texture':'무늬의 세기','patch_count':'점당 패치 수'};dist=[dict(**r,measure_ko=names[r['measure']]) for r in dist]
        lines += ['', '지붕 점의 분포(점 개수 기준):','',table(dist,[('measure_ko','값'),('points','점 수'),('missing_points','누락'),('q25','25%'),('median','중앙값'),('q75','75%')])]
        mr=rows(prior+'_mvs_evidence',stage);m=next(x for x in mr if x['dimension']=='all')
        lines += ['',f'MVS 쪽 셈: 사진 지지이면서 차가 설명 안 되는 넓이 {m["area_m2"]:,.2f}m², 그중 넓히기 v2 영상만 틀림 {m["image_wrong_area_m2"]:,.2f}m²({percent(m["image_wrong_fraction"])}). 건물별·원본 u_mvs 구간별 값과 덩어리 목록을 함께 냈다. 유효 확률이나 손실 시험은 구하지 않았다.']
    if stage=='full':
        sites=[('B173 날개','DEBY_LOD2_4959326','ALS','반박, 약 4.7m 아래 봉우리'),('R1 계단 지붕','DEBY_LOD2_4906975','LoD2','반박'),('R1 좁은 틈','R1_gap','LoD2','지지 또는 모름'),('60042 높은 단','DEBY_LOD2_60042','ALS','지지'),('4907519 평지붕','DEBY_LOD2_4907519','LoD2','지지'),('4906993 평지붕','DEBY_LOD2_4906993','LoD2','모름'),('4906968 지붕','DEBY_LOD2_4906968','LoD2','반박 또는 모름'),('4906968 지붕','DEBY_LOD2_4906968','ALS','지지')]
        observed=[]
        for label,building,prior,expectation in sites:
            values=[]
            for index in [1,2]:
                record=load(D/'figures/full'/f'curve_{building}_{prior}_{index}.json');height=record.get('h_out')
                values.append(LABELS[record['judgment']]+' / '+('높이 없음' if height is None else f'{height:.2f}m'))
            observed.append(dict(site=label,prior=prior,expectation=expectation,observed='; '.join(values)))
        lines += ['', '## 예 건물의 기대와 보기점','', '발주문 2.3의 기대와 잠근 좌표에서 고른 보기점 두 개의 관측값이다. 각 값은 판단 / 경쟁 높이 h_out이며, 사용한 점과 사진은 해당 곡선 그림 JSON에 있다. 기대의 성립 여부를 판정하지 않았다. [이 발주에서 냄]','',table(observed,[('site','자리'),('prior','사전 정보'),('expectation','앞서 적은 기대'),('observed','두 점의 관측')])]
    lines += ['', '## 그림 목록','',
      'figures/projection: 건물별 원본 사진 두 장과 사전 정보 테두리.',
      f'figures/{stage}/curve_*: 사전 정보 높이·경쟁 높이의 사진 조각과 전체 곡선. 예 건물은 잠근 단면의 40%·60%에 가까운 점을 사용했다.',
      'R1 좁은 틈은 사전 정보 면과 원본 사진에서 확인한 두 좌표를 추가로 잠갔다. 참값은 점수축 아래에 높이만 점으로 표시했다. 표본 높이 사이가 비어 있는 구간은 곡선을 잇지 않았다.',
      f'figures/{stage}/section_*: 잠근 단면의 점수, 사전 정보, MVS, 참값, 판단과 넓히기 칸.',
      '4906968의 벽 패치 관찰까지 포함한 단면은 figures/pilot/section_DEBY_LOD2_4906968_LoD2에 있다. 전체 단계의 단면은 지붕 점만 사용했다.',
      f'figures/{stage}/map_*: 예 건물의 판단·참값 점검·넓히기 칸. 4906968 비탈 관찰은 figures/pilot/map_DEBY_LOD2_4906968_LoD2_2에 있다. 항공 LiDAR에는 이 건물의 원본 벽 패치가 없었다. 판정 표와 전체 단계에는 벽 패치를 넣지 않았다.']
    if stage=='full':
        figure_index()
        lines += ['figures/full/overall_*: 전체와 차가 설명 안 되는 곳. 확인용은 회색 빗금만 표시했다.','figures/full/montage_*: 거짓 반박, 놓친 반박, 사진 지지·MVS 다름. 사전 정보마다 넓은 덩어리 최대 20개, 한 건물 최대 3개다. 원인은 붙이지 않았다.','[그림 전체 목록과 PNG·JSON 링크](그림목록_v1.md)에 투영·시범·전체 그림을 모두 적었다.']
        for prior in ['LoD2','ALS']:
            montage=rows(prior+'_montage_selection',stage);missing=sum(r['photo']['status']!='PASS' for r in montage);clipped=sum(r['photo'].get('crop_clipped',False) for r in montage)
            lines.append(f'{prior} 모음 그림은 {len(montage)}덩어리다. 사진 확인 불가 {missing}개, 사진 경계에서 3m 여백이 잘린 경우 {clipped}개이며 해당 그림과 JSON에 표시했다. [이 발주에서 냄]')
    lines += ['', '## 확인용','']
    for r in scope:
        if r['holdout']:lines.append(f'- {r["prior"]}: '+(f'{r["buildings"]}동, ' if 'buildings' in r else '')+f'{r["points"]:,}점, {r["patches"]:,}패치, {r["area_m2"]:,.2f}m². [이 발주에서 냄]')
    lines += ['',('확인용 점·패치 값과 판단은 holdout 안에만 있다.' if stage=='full' else '위 확인용 수는 점 묶음의 수다. 확인용의 사진 곡선과 판단은 전체 단계에서 구한다.'),'공개 표·그림·묶음에 확인용 판단 넓이를 넣지 않는다.']
    if stage=='full':lines += ['파일별 SHA-256은 tables/final_scope_and_hashes.json에 있다. 확인용의 수·넓이·파일 해시만 공개했다.']
    if execution:
        lines += ['', '## 실행 시간','',
          f'전체 단계에서 새로 계산한 점은 {execution["new_full_points"]:,}개, 재사용한 시범 지붕 점은 {execution["reused_pilot_roof_points"]:,}개다. 전체 단계의 새 곡선 계산은 {execution["completed_full_curve_seconds"]/3600:.3f}시간, 유효 시범 곡선 계산은 {execution["valid_pilot_curve_seconds"]/3600:.3f}시간이다.',
          f'전체 단계 사진 선정 작업의 합은 {execution["full_selected_photo_seconds"]/3600:.3f}시간이다. CPU 준비와 GPU 계산이 일부 겹치므로 이 합을 실제 경과 시간에 더하지 않는다. GPU가 사용 중일 때 기다렸으며 누적 대기는 {execution["gpu_wait_seconds"]:.0f}초다.',
          f'완료된 곡선 실행에서 기록한 프로세스 최대 메모리는 {execution["peak_completed_curve_process_rss_gib"]:.2f}GiB, 컨테이너 최대 메모리는 {execution["peak_recorded_container_memory_bytes"]/1024**3:.2f}GiB다. 컨테이너 전체 제한은 32GiB다. 시간과 메모리의 원값은 tables/execution_summary.json에 있다.']
    lines += ['', '## 바뀐 것과 확인 불가','',
      '사진 캐시의 동시쓰기 오류로 중단되거나 영향을 받은 첫 시간 측정은 무효 기록으로 보존했다. 임시 파일을 완성한 뒤 이름을 바꾸도록 고쳤다. 이후 256점 CPU·GPU 판단 3,840개가 일치했다. 투영 계산 정밀도 변경은 설정의 amendments에 기록했다.',
      '항공 LiDAR의 같은 면이 여러 건물에 걸친 경우에 건물별 원점을 쓰던 코드를 면별 원점으로 고쳤다. 앞 점 묶음과 항공 LiDAR 시범 값은 무효 기록으로 보존했다. LoD2는 면마다 건물이 하나여서 값이 같다. 두 변경 모두 참값이나 곡선 결과로 규칙을 고른 것이 아니다.',
      'MVS에 가장 가까운 높이의 점수가 없을 때 다른 높이로 건너뛰던 s_mvs 추출을 고쳤다. 시범 48점의 해당 값만 누락으로 보존했으며 곡선·판단·투영 점검 값은 같다.',
      *(['전체 단계의 디스크 읽기가 느려 완료된 7개 파일 26,166점의 SHA-256을 확인한 뒤 해당 실행만 중단하고 재개했다. 원본 JPEG에서 같은 회색 밝기·축소 판을 만드는 최대 20GiB 임시 메모리 캐시를 사용했다. 기존 배열과 다시 만든 배열 8개의 SHA-256이 같았다. 완료된 곡선과 설정은 보존했고, 중단 기록과 재개 기록을 함께 남겼다.'] if stage=='full' else []),
      '무효 측정, GPU 대기, 각 실행의 버전·코드 해시·최대 메모리는 외부 작업 폴더의 logs, benchmark, gates와 실행 JSON에 있다. 새로 물리·통계 정의를 정하거나 기대의 성립 여부를 판단하지 않았다.',
      '사진 후보와 곡선·판단은 참값을 읽지 않는 별도 스크립트에서 구했다. 참값은 단면 자리 선정의 명시된 경우와 이 보고서의 정량 점검·그림 표시에만 썼다.']
    if stage=='full' and (O/'gates/delivery.json').exists() and (O/'gates/visual.json').exists():
        assert load(O/'gates/delivery.json')['status']=='PASS' and load(O/'gates/visual.json')['status']=='PASS'
        lines += ['', '## 보내기 전 점검','',
          '전체 지붕 패치 1,776,181개의 원본 번호·점 연결·넓이와 모든 점의 15가지 판단을 독립적으로 확인했다. 사전 정보마다 요약표 60행의 넓이를 다시 확인했고, 원본 해시와 공개 파일의 확인용 건물 번호 누출 검사도 통과했다. [이 발주에서 냄]',
          '전체 그림 103장을 화면으로 확인했다. 투영 그림 24장과 시범 그림 46장은 중간 보고 전에 확인했다. PNG는 모두 300dpi이며 대응 JSON이 있다. [이 발주에서 냄]',
          '세부 점검은 [보내기 전 점검](보내기전_점검.md), 수치 기록은 tables/validation.json, 화면 확인은 tables/full_visual_review.json에 있다. 전달 ZIP의 파일 해시와 CRC 영수증은 외부 작업 폴더의 handover_manifest.json과 SHA256SUMS에 남긴다.']
    text='\n'.join(lines)+'\n';assert len(text)<20000,len(text)
    name='중간보고_v1.md' if stage=='pilot' else '사진확인_보고_v1.md';(D/name).write_text(text);print(name,len(text))
if __name__=='__main__':main()
