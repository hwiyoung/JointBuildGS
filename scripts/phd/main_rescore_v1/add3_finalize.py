"""One stage-1 validation, compact report, final lock and a separate portable delivery."""
from common import *
from PIL import Image
import csv,zipfile,hashlib,platform
SITE='B173nb_b10';BASE=Path('/out');FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
def read(p):return json.loads(Path(p).read_text())
def rows(name):return read(D/'tables'/f'{name}.json')['rows']
def fmt(x,scale=1):return '확인 불가' if x is None else f'{x*scale:.3f}'
def main():
 cfg();assert sha(C/'addendum3_stage1.json')==read(C/'addendum3_stage1.initial.lock.json')['config_sha256'];assert not (C/'addendum3_stage1.final.lock.json').exists();checks=[]
 p62=D/'figures/그림6_2.json';meta62=read(p62)
 if meta62.get('mesh_rule')!='original input surfaces; no TSDF':
  meta62['metadata_correction']=dict(field='mesh_rule',previous=meta62.get('mesh_rule'),reason='Chapter 6.2 uses original input surfaces; generic chapter 7 annotation did not apply',script_sha256=sha(__file__),png_unchanged_sha256=sha(p62.with_suffix('.png')))
  meta62['mesh_rule']='original input surfaces; no TSDF';dump(p62,meta62)
 for k,n in [(3,23),(4,115),(5,230),(7,50),(8,23)]:
  rr=rows('b173_table'+str(k));assert len(rr)==n,(k,len(rr));assert all(r['site']==SITE and 'r8' not in r.get('method','') for r in rr)
  with (D/'tables'/f'b173_table{k}.csv').open() as f:assert len(list(csv.DictReader(f)))==n
 checks.append('tables 3/4/5/7/8 exact row counts, JSON/CSV, B173 only, no r8')
 mesh_records=[]
 for r in rows('b173_table3'):
  p=Path(r['source']);v=read(p);assert sha(p)==r['source_sha256'];pro=v['provenance'];assert pro['sampling_density_m2']==400 and pro['sampling_seed']==0;assert pro['cells_sha256']==sha(CELLS/f"{SITE}__{r['prior']}.npz");assert pro['config_sha256']==sha(C/'rescore_v1.json');assert v['rule']=='RESCORE_v1_columns'
  if pro.get('tau_assignment') is None:
   # Earlier ALS input receipts predate this metadata field. The one locked
   # ALS tolerance applies to roof and wall alike; verify saved arrays only.
   assert r['prior']=='ALS' and r['mesh_rule']=='original input surface'
   locked=loadz(CELLS/f'{SITE}__ALS.npz',['tau_v2_m'])['tau_v2_m'];unique=np.unique(locked[np.isfinite(locked)]);assert len(unique)==1
   saved=loadz(p.parent/'points.npz',['scene_tau_m','sample_tau_m','row_tau_m','row_owner'])
   assert all(np.allclose(saved[k],unique[0],rtol=0,atol=1e-7) for k in ['scene_tau_m','sample_tau_m'])
   owned=saved['row_owner']>=0
   assert np.allclose(saved['row_tau_m'][owned],locked[saved['row_owner'][owned]],rtol=0,atol=1e-7,equal_nan=True)
   assert np.isnan(saved['row_tau_m'][~owned]).all()
  else:assert pro['tau_assignment']=='reference_surface_kind_v1'
  assert v['scene']['n_gt']>0 and v['scene']['n_result']>0
  if r['mesh_rule']=='original input surface':continue
  rec=read(Path(v['mesh']).with_suffix('.json'));assert rec['views']==203 and rec['virtual_views']==0 and rec['cluster_to_keep']==50 and rec['voxel_m']==.05 and rec['trunc_m']==.25;assert rec['mesh_sha256']==v['mesh_sha256'];assert rec['final_triangles']>0
  mesh_records.append(dict(key=r['key'],mesh=v['mesh'],mesh_sha256=v['mesh_sha256'],triangles=rec['final_triangles'],views=203,voxel_m=.05,trunc_m=.25,cluster_to_keep=50))
 assert len(mesh_records)==19;checks.append('19 primary meshes: cleanup/scorer SHA agreement, 203 train views, no virtual, fixed .05/.25/top50/crop; four input score caches reused')
 for prior in ['ALS','LoD2']:
  c=loadz(JA/'core_points'/f'{SITE}__{prior}.npz',['area']);a=rows('check_a_judgment_cell_'+prior);assert np.isclose(sum(r['area_m2'] for r in a),c['area'].sum(),atol=1e-8)
  t=rows('target_quality_'+f'{SITE}__{prior}__FINALTRAIN_30000');assert np.isclose(sum(r['area_m2'] for r in t),c['area'].sum(),atol=1e-8)
 checks.append('target/cell cross-table and FINALTRAIN table6 area conservation')
 lin=read(O/'lineage/join.json');a=rows('check_b_LoD2_far_point_lineage');assert sum(r['points'] for r in a)==lin['far_points'];assert lin['attributed_points']+lin['unavailable_points']==lin['far_points'];assert read(O/'lineage/receipt.json')['views_total']==203;checks.append('far-point lineage totals and 203 exact-depth attribution receipts')
 figures=list((D/'figures').glob('*.png'));assert len(figures)==12;reviews=[]
 for name in ['visual_ch6','visual_ch7']:reviews+=read(O/'validation'/f'{name}.json')['rows']
 assert len(reviews)==12 and all(r['review_count']==1 and r['status']=='PASS' for r in reviews)
 for p in figures:
  with Image.open(p) as im:assert all(abs(x-300)<.1 for x in im.info['dpi'])
  assert p.with_suffix('.json').exists()
 f61=read(D/'figures/fig6_1_실험지역.json');assert not any(f61[k] for k in ['painted_cells','hatching','B173_only']);assert len(f61['evaluation_boundaries_uv'])==3;assert all(r['selected_cell_area_m2']>=10 for r in f61['labels'] if r['visible']);f62=read(D/'figures/그림6_2.json');assert f62['legend']==['참값','사전 정보','영상 깊이'] and not f62['large_title'];checks.append('12 figures, 300 dpi, one visual review each; chapter6 typography and no-paint rules')
 validation=dict(status='PASS_STAGE1_AVAILABLE_RESULTS_WITH_EXPLICIT_UNSEEN_LINEAGE',at=now(),checks=checks,legacy_reproduction='Previously passed unchanged scorer/cleanup/merge checks reused, not repeated',python=platform.python_version(),numpy=np.__version__,scientific_verdict=None);dump(O/'validation/stage1.json',validation);dump(D/'validation.json',validation);table('primary_mesh_manifest',mesh_records)
 report=['| 단계 1 | 결과 |','|---|---|','| 범위 | B173 주변 × 항공 LiDAR·LoD2 |','| 메시 | 학습 시점 203개, 가상 시점 0개, TSDF 0.05/0.25 m, 큰 덩어리 50개, 평가 범위 자르기 |','| 표 3~8 | 23개 장면 행 · 115개 판단 칸 행 · 본 방법 FINALTRAIN 30,000회 포함 · r8 제외 |','| 추가 판 | 항공 LiDAR 결합·판단 조합·상한의 MVS 벽 보완판 3개 |','| 그림 | 7.3~7.7 × 두 사전 정보 + 6.1·6.2 = 12개, 300 dpi |','| 검사 | 새 산출물 점검 통과 · 기존 재현 검사 재사용 · 그림별 시각 검토 1회 |','| 단계 2 | B0·R1 채점 미실행; 학습 완료와 명시적 시작 지시 대기; 종료 후 상태 조회 반복 없음 |','| scientific_verdict | null |','','| 본 방법 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm |','|---|---:|---:|---:|---:|']
 for r in rows('b173_table3'):
  if r['key'].endswith('__FINALTRAIN_30000'):report.append('| '+' | '.join([r['prior'],*[fmt(r[k],100) for k in ['completeness','accuracy','gt_mean_m','result_mean_m']]])+' |')
 report+=['','| 확인 값 (가) | 평가 가능 목표 넓이 m² | 맞는 목표 넓이 m² | 목표 맞음 % |','|---|---:|---:|---:|']
 for prior in ['ALS','LoD2']:
  a=rows('check_a_judgment_cell_'+prior);den=sum(r['valid_target_reference_area_m2'] for r in a);n=sum(r['target_correct_area_m2'] for r in a);report.append(f'| {prior} | {den:.3f} | {n:.3f} | {100*n/den:.3f} |')
 report+=['','| 확인 값 (나) · LoD2 보정이 맞는 칸의 1 m 초과 결과 점 | 수 |','|---|---:|',f"| 전체 | {lin['far_points']:,} |",f"| 가우시안 계보 연결 | {lin['attributed_points']:,} |",f"| 확인 불가: 학습 시점에서 0.25 m 이내 깊이 대응 없음 | {lin['unavailable_points']:,} |",'','- 계보: 각 시점의 실제 최대 alpha×T 가우시안 → 깊이 대응 시점들의 최빈 가우시안; 동률은 원래 번호가 작은 것. TSDF 꼭짓점의 유일한 조상이라는 뜻은 아님.','- 판단 영역·초기 계보·현재 묶임별 표: [확인 값 (나)](tables/check_b_LoD2_far_point_lineage.md).',f"- 1 m 초과 점은 모두 보정 판단 영역. 다른 패치 계보이며 현재 풀린 가우시안에 대응한 점: {sum(r['points'] for r in rows('check_b_LoD2_far_point_lineage') if r['initial_lineage']=='다른 패치 계보' and r['current_binding']=='풀림'):,}개."]
 report+=['','| 확인 값 (나) · 판단 영역 | 같은 패치 계보 | 다른 패치 계보 | SfM 배경 | 확인 불가 |','|---|---:|---:|---:|---:|']
 from target_quality import REGIONS
 lineage_rows=rows('check_b_LoD2_far_point_lineage')
 for region in [0,1,2,3,4,9]:
  rr=[r for r in lineage_rows if r['judgment_region']==region]
  counts=[sum(r['points'] for r in rr if r['initial_lineage']==name) for name in ['같은 패치 계보','다른 패치 계보','SfM 배경 계보','확인 불가']]
  report.append('| '+REGIONS[region]+' | '+' | '.join(str(n) for n in counts)+' |')
 c=next(r for r in rows('check_c_LoD2_agreement_wrong') if r['cell']=='all');report+=['','| 확인 값 (다) · LoD2 일치 판단 중 틀린 목표 | 값 |','|---|---:|',f"| 패치 수 | {c['patches']:,} |",f"| 넓이 m² | {c['area_m2']:.3f} |",f"| 사전 정보 절대 오차 평균 cm · 넓이 무게 | {fmt(c['prior_abs_error']['mean_m'],100)} |",f"| 영상 깊이 절대 오차 평균 cm · 넓이 무게 | {fmt(c['image_depth_abs_error']['mean_m'],100)} |",'','| 그림 6.1 생략 이름표 | 해당 자리 새 칸 넓이 m² | 사유 |','|---|---:|---|']
 for r in f61['labels']:
  if not r['visible']:report.append(f"| {r['text']} | {r['selected_cell_area_m2']:.3f} | {r['reason']} |")
 report+=['','| 그림 | 항공 LiDAR | LoD2 |','|---|---|---|']
 for number in [3,4,5,6,7]:report.append(f'| 7.{number} | [PNG](figures/그림7_{number}_ALS.png) | [PNG](figures/그림7_{number}_LoD2.png) |')
 report+=['','- [그림 6.1](figures/fig6_1_실험지역.png), [그림 6.2](figures/그림6_2.png). 각 PNG 옆에 같은 이름의 JSON 출처·좌표·값.']
 report+=['','- [표 3·4](B173주변_비교방법_채점.md), [표 5](tables/b173_table5.md), [표 6](tables/b173_table6.md), [표 7](tables/b173_table7.md), [표 8](tables/b173_table8.md).','- [입력 면 경로·재사용 내역](tables/input_reuse.md), [메시 규칙 점검](tables/mesh_rule_check.md), [실행 문제](issues.md).','- 그림 7.5·7.6의 값은 대표 자리가 속한 맞는 판단 칸 전체의 값. LoD2 채광창은 칸 3.','- τ·cells_v2·기둥·판단·학습 변경 없음. 원래 입력 면과 채점 캐시 재사용; 결과 메시 2DGS는 같은 바이트 공유.','- 이전 최종 메시 점수·원래 설정 잠금·기존 ZIP 보존. 새 결과는 addendum3_stage1에 분리.','- 단계 1 완료 후 종료. 단계 2 시작 지시 전에는 작업·상태 확인 반복 없음.'];text='\n'.join(report)+'\n';assert len(text)<15000;(D/'단계1_보고.md').write_text(text)
 with (D/'단계1_보고.md').open('a') as f:
  f.write('\n- 확인 값 (가) 교차표: [항공 LiDAR](tables/check_a_judgment_cell_ALS.md), [LoD2](tables/check_a_judgment_cell_LoD2.md). 분모는 참값과 목표를 모두 평가할 수 있는 넓이; 확인 불가 넓이는 별도 열.\n')
  f.write('- 확인 값 (나)의 1 m는 고정 채점기의 기둥 법선 거리. 기둥에 배정되지 않거나 참값 대응이 유효하지 않은 점은 포함하지 않음.\n')
  f.write('- 확인 값 (다)의 칸별 평균·중앙값·90백분위: [LoD2 일치 판단의 틀린 목표](tables/check_c_LoD2_agreement_wrong.md).\n')
 progress('덧붙임 3 단계 1 완료. 새 산출물 단일 점검 통과, 이전 재현 검사 재실행 없음. 표·그림·확인 값과 별도 묶음 제출 후 종료; 단계 2 상태 확인 없음.')
 scriptdir=R/'scripts/phd/main_rescore_v1';files=[*scriptdir.glob('add3_*'),*scriptdir.glob('run_add3*')]+[scriptdir/n for n in ['common.py','mesh_pipeline.py','bounded_merge.py','bounded_cleanup.py','cleanup.cpp','score_mesh.py','surface_tau.py','metrics.py','geometry.py','prism.cpp','figures.py','publish_tables.py','target_quality.py']];lock=dict(at=now(),config_sha256=sha(C/'addendum3_stage1.json'),supplement_sha256=sha(C/'addendum3_figures_and_walls.json'),scripts={str(p):sha(p) for p in files if p.is_file()},validation_sha256=sha(O/'validation/stage1.json'),scientific_verdict=None);dump(C/'addendum3_stage1.final.lock.json',lock)
 manifest={};package={}
 for p in D.rglob('*'):
  if p.is_file():package['docs/'+str(p.relative_to(D))]=p
 for p in list(C.glob('addendum3*'))+[C/n for n in ['rescore_v1.json','rescore_v1.initial.lock.json','representatives_v1.json','input_sections_v1.json']]:package['configs/'+p.name]=p
 for p in files:
  if p.is_file():package['scripts/'+p.name]=p
 for p in O.glob('scores/*/values.json'):package['receipts/scores/'+p.parent.name+'.json']=p
 for p in O.glob('meshes/*/primary.json'):package['receipts/meshes/'+p.parent.name+'.json']=p
 for sub in ['checks','validation']:
  for p in (O/sub).glob('*'):
   if p.is_file():package[sub+'/'+p.name]=p
 for name in ['join.json','receipt.json','gaussian_lineage.npz','far_point_attribution.npz']:package['lineage/'+name]=O/'lineage'/name
 for name,p in package.items():manifest[name]=dict(sha256=sha(p),bytes=p.stat().st_size)
 dump(O/'package_manifest.json',dict(files=manifest,large_meshes_included=False,scientific_verdict=None));package['package_manifest.json']=O/'package_manifest.json';out=O/'PHD-MAIN-RESCORE-v1-addendum3-stage1.zip';assert not out.exists()
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,p in sorted(package.items()):z.write(p,name)
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  for name,m in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==m['sha256']
 delivery=dict(at=now(),status='PASS_STAGE1_DELIVERED',archive=str(out),archive_sha256=sha(out),archive_bytes=out.stat().st_size,members=len(package),CRC='PASS',all_member_sha256='PASS',stage2='NOT_STARTED_NO_POLLING',scientific_verdict=None);dump(O/'delivery.json',delivery);dump(D/'delivery.json',delivery);print(json.dumps(delivery,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
