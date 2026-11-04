"""Validate new artifacts once, then publish a compact, separately sealed stage-2 package."""
from common import *
from PIL import Image
import csv,zipfile,hashlib,platform
from s2_ft_paths import model_path
BASE=Path('/out');D1=Path('/docs/addendum3_stage1');SITES2=['B0_b10','R1rep_b10']
def read(p):return json.loads(Path(p).read_text())
def rows(n):return read(D/'tables'/f'{n}.json')['rows']
def fmt(x,scale=1):return '확인 불가' if x is None else f'{scale*x:.3f}'
def main():
 cfg();assert sha(C/'addendum3_stage2.json')==read(C/'addendum3_stage2.initial.lock.json')['config_sha256'];assert not (C/'addendum3_stage2.final.lock.json').exists()
 checks=[];manifest=[];available=[];unavailable=rows('unavailable')
 for path,expected in read(C/'addendum3_stage2.json')['sources'].items():assert sha(path)==expected,path
 for site in SITES2:
  assert np.all(loadz(JA/'core_points'/f'{site}__ALS.npz',['kind'])['kind']==1)
  for k,n in [(3,23),(4,115),(7,50),(8,23)]:
   rr=rows(site+'_table'+str(k));assert len(rr)==n
   with (D/'tables'/f'{site}_table{k}.csv').open() as f:assert len(list(csv.DictReader(f)))==n
  nviews=len(read(O/'views'/f'{site}.json')['views'])
  assert all(not x['virtual'] for x in read(O/'views'/f'{site}.json')['views'])
  for r in rows(site+'_table3'):
   assert 'r8' not in r['method']
   if r['status']!='PASS':assert r['key'].endswith('__FINALTRAIN_30000') and r['completeness'] is None;continue
   p=Path(r['source']);v=read(p);assert sha(p)==r['source_sha256'];pro=v['provenance']
   reference=read(O/'scores'/f"{site}__{r['prior']}__prior/values.json")
   assert v['scene']['n_gt']==reference['scene']['n_gt']
   assert {x['cell']:x['n_gt'] for x in v['cells']}=={x['cell']:x['n_gt'] for x in reference['cells']}
   assert pro['sampling_density_m2']==400 and pro['sampling_seed']==0 and pro['optimization_steps']==0
   assert pro['cells_sha256']==sha(CELLS/f"{site}__{r['prior']}.npz") and pro['config_sha256']==sha(C/'rescore_v1.json') and v['rule']=='RESCORE_v1_columns'
   if pro.get('tau_assignment') is None:
    assert r['prior']=='ALS' and r['mesh_rule']=='original input surface'
    tau=loadz(CELLS/f'{site}__ALS.npz',['tau_v2_m'])['tau_v2_m'];u=np.unique(tau[np.isfinite(tau)]);assert len(u)==1
    z=loadz(p.parent/'points.npz',['scene_tau_m','sample_tau_m','row_tau_m','row_owner']);owned=z['row_owner']>=0
    assert all(np.allclose(z[k],u[0],rtol=0,atol=1e-7) for k in ['scene_tau_m','sample_tau_m'])
    assert np.allclose(z['row_tau_m'][owned],tau[z['row_owner'][owned]],rtol=0,atol=1e-7,equal_nan=True) and np.isnan(z['row_tau_m'][~owned]).all()
   else:assert pro['tau_assignment']=='reference_surface_kind_v1'
   available.append(r)
   if r['mesh_rule']=='original input surface':continue
   rec=read(Path(v['mesh']).with_suffix('.json'))
   assert rec['views']==nviews and rec['virtual_views']==0 and rec['cluster_to_keep']==50 and rec['voxel_m']==.05 and rec['trunc_m']==.25
   assert rec['mesh_sha256']==v['mesh_sha256'] and rec['final_triangles']>0
   manifest.append(dict(key=r['key'],mesh=v['mesh'],mesh_sha256=v['mesh_sha256'],triangles=rec['final_triangles'],views=nviews,voxel_m=.05,trunc_m=.25,cluster_to_keep=50))
  for prior in ['ALS','LoD2']:
   p=D/'tables'/f'{site}__check_a_judgment_cell_{prior}.json'
   if p.exists():
    ar=read(p)['rows'];assert np.isclose(sum(r['area_m2'] for r in ar),loadz(JA/'core_points'/f'{site}__{prior}.npz',['area'])['area'].sum(),atol=1e-8)
    assert {r['target_sha256'] for r in ar}=={sha(ar[0]['target_source'])}
  lp=O/'lineage'/site/'join.json'
  if lp.exists():
   lin=read(lp);assert lin['attributed_points']+lin['unavailable_points']==lin['far_points'];assert sum(x['points'] for x in rows(site+'__check_b_LoD2_far_point_lineage'))==lin['far_points']
 checks.append(f'{len(available)} stage2 scores, {len(manifest)} primary mesh receipts, eight reused input caches, locked tau/cells/column/sampling')
 for k,n in [(3,69),(4,345),(7,150),(8,69)]:assert len(rows('all_regions_table'+str(k)))==n
 checks.append('tables 3/4/7/8 exact regional and combined row counts, no r8; target/cell area conservation and available lineage accounting')
 f61=read(D/'figures/fig6_1_실험지역.json');old=read(D1/'figures/fig6_1_실험지역.json')
 assert not any(f61[k] for k in ['painted_cells','hatching','B173_only','gpu_used']) and len(f61['evaluation_boundaries_uv'])==3
 assert all(r['selected_cell_area_m2']>=10 for r in f61['labels'] if r['visible'])
 changed={'LoD2 정면 20 cm 밖':'LoD2 정면 바깥','날개 3.5~5 m 위':'날개 3.5~6 m 위'}
 for r in old['labels']:
  if r['text']=='채광창 깊이 틀림':continue
  new=next(x for x in f61['labels'] if x['text']==changed.get(r['text'],r['text']))
  for k,v in r.items():
   if k not in ['text','revision']:assert new[k]==v,(r['text'],k)
 skylight=next(x for x in f61['labels'] if x['text']=='채광창 깊이 틀림');stair=next(x for x in f61['labels'] if x['text']=='계단 가장자리 깊이 틀림')
 assert skylight['prior']=='ALS' and not skylight['fallback_to_LoD2'] and skylight['cluster_rank']==1 and stair['cluster_rank']==1
 reviews={}
 for p in (O/'validation').glob('visual_*.json'):
  r=read(p)
  for x in r.get('rows',[r]):reviews[x['name']]=x
 figures=list((D/'figures').glob('*.png'))
 for p in figures:
  with Image.open(p) as im:assert all(abs(x-300)<.1 for x in im.info['dpi'])
  assert p.with_suffix('.json').exists();review=reviews[p.stem];assert review['review_count']==1 and review['status']=='PASS'
  if p.stem.startswith('R1rep_b10__그림7_3_'):
   assert read(p.with_suffix('.json'))['layout_check']['status']=='PASS'
  if '__그림7_5_' in p.stem:
   meta=read(p.with_suffix('.json'));site=meta['site'];prior=p.stem.rsplit('_',1)[1]
   for place in meta['places']:
    for metric in place['metrics_entire_cell']:
     key=meta['method'] if metric['family']=='method' else f"{site}__{prior}__{metric['family']}"
     whole=next(x for x in read(O/'scores'/key/'values.json')['cells'] if x['cell']==metric['cell'])
     assert metric['value']==whole[metric['metric']] and metric['n_gt']==whole['n_gt']
 checks.append(f'{len(figures)} new figures, 300dpi, one visual review each; figure6.1 unchanged arrows except named edits; sealed figure6.2 and B173 chapter7 reused')
 validation=dict(status='PASS_AVAILABLE_OUTPUTS_WITH_EXPLICIT_MISSING_INPUTS' if unavailable else 'PASS_STAGE2',at=now(),checks=checks,legacy_reproduction='PASS reused; not rerun',training_steps=0,python=platform.python_version(),numpy=np.__version__,scientific_verdict=None)
 dump(O/'validation/stage2.json',validation);dump(D/'validation.json',validation);table('primary_mesh_manifest',manifest)
 elapsed=(dt.datetime.fromisoformat(now())-dt.datetime.fromisoformat(read(C/'addendum3_stage2.initial.lock.json')['at'])).total_seconds()
 timing_rows=[read(p) for p in sorted((O/'timing').glob('*.json'))];table('execution_timing',timing_rows)
 availability=[];ft=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
 for site in SITES2:
  for prior in ['ALS','LoD2']:
   receipt=ft/'runs'/site/f'ft_{prior}_s0/receipt.json';record=read(receipt) if receipt.exists() else None
   model=(model_path(record,site,prior) if record else receipt.parent/'attempt1/model')/'point_cloud/iteration_30000/point_cloud.ply';target=ft/'targets'/f'{site}__{prior}.npz';score=O/'scores'/f'{site}__{prior}__FINALTRAIN_30000/values.json'
   availability.append(dict(site=site,prior=prior,model=str(model),model_present=model.exists(),receipt_status=record['status'] if record else None,target=str(target),target_present=target.exists(),score_present=score.exists(),checked_at=now()))
 table('final_availability',availability)
 report=['| 항목 | 결과 |','|---|---|',f'| 다시 센 판·재사용 | 단계 2 {len(available)-8}개 결과 메시 채점 + 입력 8개 재사용; 본 방법 미수신 {len(unavailable)}개 |','| τ | 기존 새 τ 고정; 아래 표. cells_v2·기둥 규칙·400점/m²·씨앗 0 유지 |','| 재현 확인 | 기존 전체 재현 통과 재사용: 최대 차이 0.049 %p, 거리 0.033 cm; 재실행 없음 |',f'| 확인 불가 | 본 방법 미수신 {len(unavailable)}개; 아래 출처·계보 표에 별도 기재 |','| 장치·시간 | 학습 0회; 메시·채점 CPU, 기존 모델 깊이·계보만 GPU; 그림 6.1 CPU. 단계별 시간·GPU 대기는 progress.md |','','| 지역 | 사전 정보 | 새 τ cm |','|---|---|---:|']
 for x in read(Path('/docs/tables/table1_tau.json'))['rows']:
  report.append(f"| {x['search_region']} | {x['prior']} · {x['kind']} | {100*x['new_tau_m']:.3f} |")
 report+=['',f'- 단계 2 경과 시간: {elapsed/60:.1f}분. [단계별 실측 시간](tables/execution_timing.md); 병행 단계 시간은 서로 겹침.','','| 지역·사전 정보 | 본 방법 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm |','|---|---:|---:|---:|---:|']
 for r in rows('all_regions_table3'):
  if r['key'].endswith('__FINALTRAIN_30000'):report.append('| '+' | '.join([LABELS[r['site']]+' · '+r['prior'],*[fmt(r[k],100) for k in ['completeness','accuracy','gt_mean_m','result_mean_m']]])+' |')
 report+=['','| 본 방법 확인 값 | 목표가 맞는 넓이 / 평가 가능 넓이 m² | 맞음 % | 1 m 초과 점 / 계보 연결 / 연결 불가 |','|---|---:|---:|---|']
 for site in SITES2:
  for prior in ['ALS','LoD2']:
   p=D/'tables'/f'{site}__check_a_judgment_cell_{prior}.json';a=read(p)['rows'] if p.exists() else []
   den=sum(x['valid_target_reference_area_m2'] for x in a);num=sum(x['target_correct_area_m2'] for x in a);linp=O/'lineage'/site/'join.json';lin=read(linp) if linp.exists() else None
   note='해당 없음' if prior=='ALS' else (f"{lin['far_points']:,} / {lin['attributed_points']:,} / {lin['unavailable_points']:,}" if lin else '확인 불가')
   report.append(f"| {LABELS[site]} · {prior} | {f'{num:.3f} / {den:.3f}' if a else '확인 불가'} | {fmt(num/den,100) if den else '확인 불가'} | {note} |")
 report+=['','| LoD2 일치 판단의 틀린 목표 | 패치 수 | 넓이 m² | 사전 정보 절대 오차 평균 cm | 영상 깊이 절대 오차 평균 cm |','|---|---:|---:|---:|---:|']
 for site in SITES2:
  p=D/'tables'/f'{site}__check_c_LoD2_agreement_wrong.json'
  if p.exists():
   c=next(x for x in read(p)['rows'] if x['cell']=='all');report.append(f"| {LABELS[site]} | {c['patches']} | {c['area_m2']:.3f} | {fmt(c['prior_abs_error']['mean_m'],100)} | {fmt(c['image_depth_abs_error']['mean_m'],100)} |")
  else:report.append(f'| {LABELS[site]} | 확인 불가 | 확인 불가 | 확인 불가 | 확인 불가 |')
 report+=['','| 그림 6.1 수정 | 결과 |','|---|---|','| B0 정면 | LoD2 정면 바깥; 원래 화살표 유지 |','| B173 날개 | 날개 3.5~6 m 위; 원래 화살표 유지 |',f"| 채광창 | 항공 LiDAR 칸 2 최대 모임 {skylight['selected_cell_area_m2']:.3f} m²; LoD2 대체 없음 |",f"| R1 계단 가장자리 | 항공 LiDAR 칸 2 최대 모임 {stair['selected_cell_area_m2']:.3f} m²; 초록 이름표 추가 |"]
 for r in f61['labels']:
  if not r['visible']:report.append(f"| 이름표 생략: {r['text']} | {r['selected_cell_area_m2']:.3f} m²; {r['reason']} |")
 report+=['','| 그림 7.3~7.7 | 항공 LiDAR | LoD2 |','|---|---|---|']
 for site in ['B173nb_b10',*SITES2]:
  parts=[]
  for prior in ['ALS','LoD2']:
   if site=='B173nb_b10':parts.append(' / '.join(f'[7.{n}](../addendum3_stage1/figures/그림7_{n}_{prior}.png)' for n in range(3,8)))
   elif (D/'figures'/f'{site}__그림7_3_{prior}.png').exists():parts.append(' / '.join(f'[7.{n}](figures/{site}__그림7_{n}_{prior}.png)' for n in range(3,8)))
   else:parts.append('확인 불가: FINALTRAIN 30,000회 미수신')
  report.append('| '+LABELS[site]+' | '+' | '.join(parts)+' |')
 report+=['','- 메시: 지역의 원래 학습 시점 전부, 가상 시점 0, TSDF 0.05/0.25 m, 큰 덩어리 50개, 평가 범위 자르기. 항공 LiDAR 결합·조합·상한의 MVS 벽 보완판 포함.','- 입력: 원래 삼각형 면과 앞 작업의 MVS 면. [경로·SHA·재사용](tables/input_reuse.md).','- [B0 표 3~8](B0_비교방법_채점.md), [R1 표 3~8](R1_비교방법_채점.md), 세 지역 합본: '+', '.join(f'[표 {k}](tables/all_regions_table{k}.md)' for k in range(3,9))+'.','- [그림 6.1](figures/fig6_1_실험지역.png) · [좌표·출처 JSON](figures/fig6_1_실험지역.json). [그림 6.2](../addendum3_stage1/figures/그림6_2.png)는 이미 요청 문구를 적용한 판 그대로 재사용.','- B0·R1 대표 자리는 기존 입력 단면·STAGE1 단면을 재사용. 그림 7.5·7.6 값은 해당 자리의 맞는 판단 칸 전체 값; 사전 정보별 칸 이름은 별도. 표시 카메라는 기존 -60°/35° 정사 투영 규칙; 메시 만들기에 쓰지 않음.','- 계보: 실제 최대 alpha×T 가우시안 → 깊이 대응 시점 최빈값, 동률은 작은 원래 번호. 0.25 m 깊이 대응이 없는 점은 확인 불가; TSDF 꼭짓점의 유일한 조상을 뜻하지 않음.','- 확인 값 (나)의 1 m는 고정 채점기의 기둥 법선 거리. 확인 값 (가) 분모는 목표·참값을 모두 평가할 수 있는 넓이; (다) 오차 평균은 넓이 가중.','- [미수신 항목](tables/unavailable.md), [실행 문제](issues.md), [시간](progress.md), [검사](validation.json). B173 옛 최종 메시 점수는 [메시 규칙 점검](../addendum3_stage1/tables/mesh_rule_check.md) 그대로 보존.','- 학습·판단·τ·칸·기둥 규칙 변경 없음. 기존 재현 검사와 그림 검토 반복 없음. scientific_verdict: null.']
 for site in SITES2:
  for prior in ['ALS','LoD2']:
   name=f'{site}__check_a_judgment_cell_{prior}'
   if (D/'tables'/f'{name}.json').exists():report.append(f'- 확인 값 (가) {LABELS[site]} {prior}: [교차표](tables/{name}.md).')
  for name,label in [('check_b_LoD2_far_point_lineage','확인 값 (나)'),('check_c_LoD2_agreement_wrong','확인 값 (다)'),('low_cell0_mesh_comparison','칸 0 낮은 비교 방법의 메시 값')]:
   name=site+'__'+name
   if (D/'tables'/f'{name}.json').exists():report.append(f'- {LABELS[site]} {label}: [표](tables/{name}.md).')
 for p in sorted((D/'figures').glob('깊이점검_*.png')):report.append(f'- [대표 학습 시점 깊이 점검: {p.stem.removeprefix("깊이점검_")}](figures/{p.name}).')
 report+=['- 계산·그림 생성은 14:31 종료; 19:44부터 남은 최초 그림 검토와 최종 전달 작업 재개. 경과 시간에는 대기 시간이 포함됨.','- R1 그림 7.3의 최초 검토에서 제목 겹침·하단 글자 잘림을 발견해 두 사전 정보의 배치만 수정. 저장 그림 자료를 재사용하고 300 dpi 글자 경계·겹침 검사 통과; 점수·메시 재계산 없음.','- 덧붙임 5: [6장 구현 확인](../ch6_impl_check.md), [저장 잔차 9조건 비율 CSV](../tables/ch6_tau_residual_ratios.csv). 완료된 구현 확인·검사는 재실행하지 않고 합본에 포함.']
 text='\n'.join(report)+'\n';assert len(text)<15000;(D/'단계2_보고.md').write_text(text)
 progress(('단계 2 완료. ' if not unavailable else '단계 2의 수신된 항목 처리 완료; 결과 없는 본 방법은 확인 불가로 구분. ')+'새 산출물 단일 점검 통과. 계보 미연결 점은 별도 표기; 기존 재현 검사 재실행 없음. 별도 묶음 제출 후 상태 확인 반복 없음.')
 files=sorted((R/'scripts/phd/main_rescore_v1').glob('*.py'))+sorted((R/'scripts/phd/main_rescore_v1').glob('*.sh'))+[R/'scripts/phd/main_rescore_v1'/n for n in ['cleanup.cpp','prism.cpp']]
 dump(C/'addendum3_stage2.final.lock.json',dict(at=now(),config_sha256=sha(C/'addendum3_stage2.json'),scripts={str(p):sha(p) for p in files},validation_sha256=sha(O/'validation/stage2.json'),scientific_verdict=None))
 package={}
 for prefix,folder in [('docs/addendum3_stage2',D),('docs/addendum3_stage1',D1)]:
  for p in folder.rglob('*'):
   if p.is_file() and 'early_delivery_20261104' not in p.relative_to(folder).parts:package[prefix+'/'+str(p.relative_to(folder))]=p
 for p in C.glob('*.json'):package['configs/'+p.name]=p
 for relative in ['ch6_impl_check.md','tables/ch6_tau_residual_ratios.csv','provenance/ch6_impl_check.json']:
  package['docs/'+relative]=Path('/docs')/relative
 package['receipts/ch6_impl_check/colmap_image_undistorter_help.txt']=BASE/'ch6_impl_check/colmap_image_undistorter_help.txt'
 for p in files:package['scripts/'+p.name]=p
 for p in O.glob('scores/*/values.json'):package['receipts/scores/'+p.parent.name+'.json']=p
 for p in O.glob('meshes/*/primary.json'):package['receipts/meshes/'+p.parent.name+'.json']=p
 for sub in ['checks','validation','jobs','views','timing']:
  for p in (O/sub).glob('*'):
   if p.is_file():package[sub+'/'+p.name]=p
 for site in SITES2:
  for name in ['join.json','receipt.json','gaussian_lineage.npz','far_point_attribution.npz']:
   p=O/'lineage'/site/name
   if p.exists():package['lineage/'+site+'/'+name]=p
 info={n:dict(sha256=sha(p),bytes=p.stat().st_size) for n,p in package.items()};dump(O/'package_manifest.json',dict(files=info,large_meshes_included=False,scientific_verdict=None));package['package_manifest.json']=O/'package_manifest.json';out=O/'PHD-MAIN-RESCORE-v1-addendum3-stage2.zip';assert not out.exists()
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for n,p in sorted(package.items()):z.write(p,n)
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  for n,r in info.items():assert hashlib.sha256(z.read(n)).hexdigest()==r['sha256']
 assert out.stat().st_size<400*1024**2
 delivery=dict(at=now(),status=validation['status'],archive=str(out),archive_sha256=sha(out),archive_bytes=out.stat().st_size,members=len(package),CRC='PASS',all_member_sha256='PASS',unavailable_models=len(unavailable),scientific_verdict=None);dump(O/'delivery.json',delivery);dump(D/'delivery.json',delivery);print(json.dumps(delivery,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
