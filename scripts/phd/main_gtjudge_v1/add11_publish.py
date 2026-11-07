"""Compact reports, point-data recount and ordered archive delivery."""
from add11 import *

def readme():
 text='''# 거리 지도 자료

장면마다 압축 NPZ 하나다. 중간은 B0·B173nb·R1rep ALS, B0 LoD2의 다섯 방법이고 끝은 여섯 장면의 열 방법이다. `ALS`는 항공 LiDAR다. 배열 길이는 참값 N 또는 방법별 결과 점 M이며, 점 순서는 기존 저장 배열 순서다. 결과 점은 기존 평가 범위 안의 저장 표본 전부이며 추가 표본이나 메시를 만들지 않았다.

접두사 `reference__`의 공통 배열:
- `point_id`: int64 참값 행 번호. `xyz`: N×3 float32 지역 XYZ m.
- `normal`: N×3 float32 기존 AXES71 방향 법선, 무단위. `wall`: uint8(0 지붕/비벽, 1 벽). ALS는 기존 정의대로 모두 비벽.
- `case_id`: int8, 0 둘 다 맞음 / 1 사전 정보가 틀린 곳 / 2 영상이 틀린 곳 / 3 둘 다 틀림 / 4 영상 없음 / −1 미배정. 단계1 τ=1 분류 그대로.
- `tau_m`: float32 각 행의 기존 지붕·벽 τ, m. `eligible`: uint8 완전성 분모(저장 행 전부 1).
- `reference__<방법>__s_m`: float32, 참값→결과 면의 저장 부호 거리. 지붕 위 방향이 +, 벽은 가까운 학습 카메라 방향이 +. `state`: uint8(0 만남, 1 면 없음), 면 없음 s는 NaN.
- `reference__<방법>__within_tau1`: uint8, float32 반올림 전 저장 거리로 판정한 정확한 τ=1 맞음 비트.

접두사 `result__<방법>__` 배열:
- `point_id`: int64 기존 결과 표본 번호. `xyz`, `normal`: M×3 float32, 지역 m/무단위. 법선은 기존 참값과 방향을 맞춘 저장 삼각형 법선이다.
- `case_id`: int8, 기존 sample_reference_row가 가리키는 참값 행의 경우. `reference_row_id`: int32 그 행, 미배정 −1. 미배정 결과 점도 장면 전체 분모에는 포함한다.
- `wall`: uint8, 원래 결과 채점에서 사용한 지붕/벽 구분. `tau_m`: float32 m.
- `s_m`: float32. 기존 sample_s(참값−결과)의 부호를 뒤집어 결과−참값으로 통일했다. 해당 결과 법선 방향의 축 거리이며, 참값 행의 광선 거리와 동일한 점쌍이라는 뜻은 아니다.
- `state`: uint8. 0 셈에 듦(기존에도 포함·참값 만남), 1 지금 규칙에서만 뺌(새로 포함·참값 만남), 2 두 규칙 모두 참값 관측 없음으로 뺌, 3 ALS 가파른 면이라 뺌, 4 새 분모에 들지만 작은 원기둥에서 참값을 못 찾음.
- 겹치는 상태의 우선순위는 3 → 2 → 4 → 1 → 0. 상태 4도 기존 제외/포함 여부는 아래 비트로 구별한다.
- `eligible_old`, `eligible_new`: uint8, 가파른 면 제외까지 적용한 실제 정확성 분모.
- `observed_old`, `observed_new`: uint8, 가파른 면 제외 전의 3차원 1m / 반지름 1m 법선 원기둥 관측 여부.
- `steep`: uint8, ALS에서 |저장 normal_z|<0.5. LoD2는 0.
- `reference_found`: uint8, 작은 원기둥 거리 유한 여부. `distance_evaluated`: uint8, 거리를 실제 계산한 점인지. 계산하지 않은 제외점의 NaN과 계산했지만 참값이 없는 NaN을 구별한다.
- `within_tau1`: uint8, 반올림 전 거리로 |s|≤기존 τ인 비트. 정확성은 eligible_new & within_tau1의 수 / eligible_new 수. 완전성도 reference의 within_tau1/eligible로 계산한다. 반올림된 s와 tau만으로 경계점을 재판정하는 오차를 피하려고 비트를 함께 제공한다.

모든 부동소수 배열은 float32, 식별자·상태는 정수다. NaN을 0으로 채우지 않는다. 지역 좌표에 [690953,5336071,604]m를 더하면 기존 EPSG:25832 기준 XYZ다.

새 관측 검사는 기존 observed_old=0인 점에만 반지름 1m, 지붕 ±10m/벽 ±5m로 했다. 기존 제외점의 작은 원기둥 거리는 저장되지 않았으므로, 새로 관측되고 가파르지 않은 점의 미계산 거리만 같은 저장 점·법선과 반지름 0.05m 규칙으로 채웠다. 기존 계산값은 바꾸지 않았다. 공간 색인은 물리 지역별 한 번 만들어 두 prior와 모든 방법에 재사용했다. 메시 읽기·학습·렌더·메시 생성 없음.

표의 평균·중앙값·95%는 각 방향에서 실제 만난 점의 |s|만 쓰며 추가 상한·절단을 두지 않는다. 면 없음 비율의 분모는 전체 eligible 점이다. ALS 합산 완전성은 참값 수, 정확성은 규칙별 eligible 결과 점 수, 평균 거리는 유한 거리 점 수로 가중했다. 중앙값·95%는 합쳐진 원래 점 배열의 분위수다. 높은 것이 좋은 완전성·정확성은 1위−해당 값, 낮은 것이 좋은 거리·면 없음 비율은 해당 값−1위로 차이를 기록했다. 개수는 순위가 아닌 분모다.

scientific_verdict: null
'''
 (D/'README_거리지도자료.md').write_text(text)

def validate_points(phase):
 stem='B0_b10__ALS';m='FINALTRAIN_30000';path=W/(phase+'_data')/(stem+'.npz');z=loadz(path,['reference__eligible','reference__case_id','reference__'+m+'__within_tau1','reference__'+m+'__s_m','reference__tau_m','result__'+m+'__eligible_new','result__'+m+'__within_tau1','result__'+m+'__s_m','result__'+m+'__tau_m','result__'+m+'__case_id']);table=list(csv.DictReader((T/('full_'+phase+'.csv')).open()));checks=[]
 for case in ['0','1','2','3','4','all']:
  r=next(r for r in table if r['site']=='B0_b10' and r['prior']=='ALS' and r['method']==m and r['surface']=='all' and str(r['case_id'])==case);g=z['reference__eligible'].astype(bool);q=z['result__'+m+'__eligible_new'].astype(bool)
  if case!='all':g&=z['reference__case_id']==int(case);q&=z['result__'+m+'__case_id']==int(case)
  comp=100*(g&z['reference__'+m+'__within_tau1'].astype(bool)).sum()/g.sum() if g.any() else None;acc=100*(q&z['result__'+m+'__within_tau1'].astype(bool)).sum()/q.sum() if q.any() else None
  assert (comp is None and not r['completeness_pct']) or abs(comp-float(r['completeness_pct']))<1e-10;assert (acc is None and not r['accuracy_new_pct']) or abs(acc-float(r['accuracy_new_pct']))<1e-10
  checks.append(dict(case_id=case,completeness_pct=comp,accuracy_new_pct=acc,n_reference=int(g.sum()),n_result=int(q.sum())))
 # Check data schema and ZIP CRC, without reloading giant methods or recomputing geometry.
 manifests=[]
 for p in sorted((W/(phase+'_data')).glob('*.npz')):
  with zipfile.ZipFile(p) as archive:
   assert archive.testzip() is None;names=archive.namelist();methods=sorted({n.split('__')[1] for n in names if n.startswith('result__')});expected=A['presentation_methods'] if phase=='interim' else A['methods'];assert set(methods)==set(expected)
   for n in names:
    with archive.open(n) as f:
     version=np.lib.format.read_magic(f);shape,fortran,dtype=np.lib.format._read_array_header(f,version)
     assert dtype.kind!='f' or dtype==np.dtype('float32'),(p,n,dtype)
  manifests.append(dict(scene=p.stem,methods=methods,bytes=p.stat().st_size,sha256=sha(p)))
 assert len(manifests)==(4 if phase=='interim' else 6);dump(D/'verification'/('addendum11_'+phase+'.json'),meta(status='PASS_POINT_DATA_RECOUNT_AND_SCHEMAS',recount_scene=stem,recount_method=m,recount=checks,point_data=manifests,mesh_read=False,training=False,rendering=False,mesh_regeneration=False));return manifests

def report(phase):
 presentation=json.loads((T/'presentation.json').read_text())['rows'];tau=json.loads((T/'tau_summary.json').read_text())['rows'];lines=['발표표: 완전성/바꾼 정확성(%). 열은 본 방법/LGDM/GeoGS/2DGS/CDGS. 평균·중앙값·95%·면 없음과 각 값의 1위 차이는 presentation.csv.','','|장면·경우|본|LGDM|GeoGS|2DGS|CDGS|','|---|---:|---:|---:|---:|---:|']
 for group in ['ALS_pooled','B0_LoD2']:
  for k in A['presentation_cases']:
   part=[next(r for r in presentation if r['group']==group and r['case_id']==k and r['method']==m) for m in A['presentation_methods']];lines.append('|'+('ALS합산' if group=='ALS_pooled' else 'B0 LoD2')+' '+str(k)+'|'+'|'.join(f"{r['completeness_pct']:.1f}/{r['accuracy_new_pct']:.1f}" if r['accuracy_new_pct'] is not None else 'NA' for r in part)+'|')
 lines+=['','τ 요약: 8칸에서 1위와의 최대 차이, 완전성/정확성(%p). 가=경우 고정, 나=경우 재분류.','','|판·τ|본|LGDM|GeoGS|2DGS|CDGS|','|---|---:|---:|---:|---:|---:|']
 for mode in ['fixed_cases','reclassified_cases']:
  for f in A['tau_multipliers']:
   part=[next(r for r in tau if r['mode']==mode and r['tau_multiplier']==f and r['method']==m) for m in A['presentation_methods']];lines.append('|'+('가' if mode=='fixed_cases' else '나')+' '+str(f)+'|'+'|'.join(f"{r['completeness_pct_worst_gap_pp']:.1f}/{r['accuracy_new_pct_worst_gap_pp']:.1f}" for r in part)+'|')
 checks=list(csv.DictReader((T/'old_rule_checks.csv').open()));maximum=max(float(r['difference_pp']) for r in checks);diag=json.loads((T/'rule_diagnostic_numbers.json').read_text())['rows'];lines+=['',f'τ=1 기존 규칙 대조 {len(checks)}개 값, 최대 차이 {maximum:.6f}%p. B0 ALS 본 방법의 점별 자료로 경우별·전체 완전성/정확성을 재집계해 표와 일치했다.','ALS 합산 가중: 완전성=참값 수, 정확성=각 규칙의 포함 결과 점 수, 평균 거리=유한 거리 점 수. 중앙값·95%는 합친 점 배열에서 계산했다. 미배정 결과는 장면 전체에 포함한다.','기존 거리는 그대로 썼다. 이전 1m 밖 점은 작은 원기둥 거리가 미계산 NaN이라 새로 들어온 비가파른 점의 거리만 보충했다. 큰 원기둥 검사는 이전 제외점에만, 공간 색인은 지역별 1회로 prior·방법 간 재사용했다.','']
 for r in diag:lines.append(f"{r['figure_method']}: 새로 든 경우1 {r['newly_included_case1_n']:,}점, τ 밖(면 없음 포함) {r['newly_included_case1_bad_pct']:.2f}%; 계속 제외 중 가파른 면 {r['both_excluded_steep_pct']:.2f}%. 유리창 비율 확인 불가(실측 경계 없음).")
 lines+=['','파일: presentation.csv, tau_summary.csv, tau_presentation_cells.csv, full_'+phase+'.csv, tau_all_'+phase+'.csv; distance_data/<장면>.npz; README_거리지도자료.md; rule_top.png, rule_section_and_tau.png. 두 장 제한에 따라 τ 선 그림을 단면 아래에 합쳤다. 수치 표는 면 없음 비율·제외 수를 함께 제공한다.','학습·렌더·메시 읽기/생성 없음. scientific_verdict: null.'];text='\n'.join(lines)+'\n';assert len(text)<=3000,len(text);path=D/'보고_덧붙임11.md';path.write_text(text);return path

def deliver(phase):
 readme();manifests=validate_points(phase);report_path=report(phase);state=json.loads((W/(phase+'_state.json')).read_text());diff=max(r['difference_pp'] for r in state['checks']);assert diff<=.1
 protected=json.loads((W/'protected_before.json').read_text())
 for rel,h in protected.items():assert sha(D/rel)==h,rel
 if phase=='final':
  interim=O/'delivery/PHD-MAIN-GTJUDGE-v1_네값_중간.zip';assert interim.exists();receipt=json.loads((D/'verification/addendum11_interim_archive.json').read_text());assert sha(interim)==receipt['sha256']
 selections=[(report_path,'보고_덧붙임11.md'),(D/'README_거리지도자료.md','README_거리지도자료.md')]
 for name in ['presentation.csv','presentation.json','tau_summary.csv','tau_summary.json','tau_presentation_cells.csv','rule_diagnostic_numbers.json','old_rule_checks.csv','full_'+phase+'.csv','tau_all_'+phase+'.csv']:selections.append((T/name,'tables/addendum11/'+name))
 selections.extend((p,'figures/addendum11/'+p.name) for p in sorted(F.glob('*')) if p.is_file());selections.extend((p,'distance_data/'+p.name) for p in sorted((W/(phase+'_data')).glob('*.npz')));selections.extend((p,'configs/'+p.name) for p in [C/'addendum11.json',C/'addendum11.lock.json'])
 hashes={name:sha(p) for p,name in selections};archive=O/'delivery'/('PHD-MAIN-GTJUDGE-v1_네값_중간.zip' if phase=='interim' else 'PHD-MAIN-GTJUDGE-v1_네값.zip');assert not archive.exists()
 with zipfile.ZipFile(archive,'w',allowZip64=True) as z:
  for p,name in selections:z.write(p,name,compress_type=zipfile.ZIP_STORED if p.suffix=='.npz' else zipfile.ZIP_DEFLATED,compresslevel=4 if p.suffix!='.npz' else None)
  z.writestr('SHA256SUMS',''.join(h+'  '+name+'\n' for name,h in hashes.items()))
  z.writestr('manifest.json',json.dumps(meta(phase=phase,files=hashes,point_manifests=manifests,protected_previous_outputs=len(protected),old_rule_maximum_difference_pp=diff),ensure_ascii=False,indent=2))
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for name,h in hashes.items():
   hh=hashlib.sha256()
   with z.open(name) as f:
    for chunk in iter(lambda:f.read(8<<20),b''):hh.update(chunk)
   assert hh.hexdigest()==h,name
 dump(D/'verification'/('addendum11_'+phase+'_archive.json'),meta(status='PASS_ZIP_CRC_AND_MEMBER_SHA256',phase=phase,path=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,members=len(selections)+2,point_sources=manifests));print('ADD11_ARCHIVE',phase,archive.name,archive.stat().st_size,flush=True)

if __name__=='__main__':deliver(sys.argv[1])
