"""Validate requested products and package addendum 9 without extra figures."""
from add9_common import *
from add9_split import MS,NAMES

def finalize_metadata():
 implementations=[proof(p) for p in sorted(Path(__file__).parent.glob('add9_*.py'))]
 inputs={}
 for p in F9.glob('*.json'):
  j=json.loads(p.read_text())
  if 'line_polyline_px' in j and 'line_draw_mask' not in j:
   j['line_draw_mask']=getcase(case('c2'))['annotation_display_mask'] if p.name.startswith('c2_') else [True]*(len(j['line_polyline_px'])-1)
  if 'camera' in j and 'photo' in p.name:
   cam=j['camera'];angle=cam.get('optical_axis_elevation_deg');j['requested_optical_angle_satisfied']=None if angle is None else 30<=angle<=60
  j['final_implementation']=implementations;j['metadata_finalization']='Carry inherited c2 discontinuous-line mask; final replay implementation hashes; original source and producer hashes retained'
  dump(p,j)
  for src in j.get('sources',[]):
   if '/add9_' in src['path']:continue
   inputs[src['path']]=src['sha256']
 for key in ['c1','c3']:
  p=T9/(key+'_case2_split.json');j=json.loads(p.read_text())
  for r in j['rows']:r['small']='적음' if r['n_gt']<1000 else ''
  dump(p,j);csv9(key+'_case2_split',j['rows'])
 for p in T9.glob('*.json'):
  for src in json.loads(p.read_text()).get('sources',[]):inputs[src['path']]=src['sha256']
 for path,h in inputs.items():assert sha(path)==h,path
 dump(D/'verification/addendum9_input_integrity.json',dict(at=now(),status='PASS_ALL_RECORDED_INPUT_BYTES',sources=inputs,final_implementation=implementations,scientific_verdict=None))

def validate():
 checks=[];protected=json.loads((W9/'previous_outputs_sha256.json').read_text())
 for rel,h in protected.items():assert sha(D/rel)==h,rel
 expected={*(k+s+'.png' for k in ['c1','c2','c3','c4'] for s in ['_photo','_photo_cases','_photo_cases_desat']),'c3_case2_split_top.png','c3_closeup_photo.png','c3_edge_closeup_photo.png',*(f'c3_points_{m}.png' for m in ['mvs','FINALTRAIN_30000','GeoGS_30000','judgment_mesh']),*(f'c3_edge_points_{m}.png' for m in ['mvs','FINALTRAIN_30000'])};assert {p.name for p in F9.glob('*.png')}==expected
 for p in F9.glob('*.png'):
  j=json.loads(p.with_suffix('.json').read_text());im=Image.open(p);im.load();assert list(im.size)==j['size_px'] and im.mode=='RGB' and im.info.get('icc_profile');assert j['text_in_figure'] is False and j['line_drawn'] is False and j['box_drawn'] is False
  if 'photo' in p.name:
   cam=j['camera'];assert cam['training_camera'];assert cam['source']['undistorted_valid_pixel_fraction']==1;assert cam['parameters'][4:]==[0.]*8;assert len(j['line_polyline_px'])==len(j['line_occluded'])==len(j['line_points_inside_image']);assert all(j['line_points_inside_image']),p.name
  checks.append(p.name)
 assert sha(F9/'c2_photo.png')==sha(F9/'c3_photo.png')
 for key in ['c1','c3']:
  c=case(key);row,lab=data(c);f=loadz(root_of(c)/'preservation_features.npz');split=json.loads((T9/(key+'_case2_split.json')).read_text());assert sum(r['n_gt'] for r in split['rows'])==int((lab==2).sum())
  for m in MS:
   z=loadz(scorepath(c,m),['row_s'])['row_s']
   for r in split['rows']:
    mask=(lab==2)&(f['quadrant']==r['division_id']);assert int(mask.sum())==r['n_gt'];assert int((np.isfinite(z[mask])&(abs(z[mask])<=row['row_tau_m'][mask])).sum())==r[m+'_n_in']
 for key in ['c3','c3_edge']:
  c=case('c3');row,lab=data(c);reference_ids=None
  for p in F9.glob(key+'_points_*.json'):
   j=json.loads(p.read_text());z=loadz(scorepath(c,j['method']),['row_s'])['row_s'];ids=np.array([r['row_id'] for r in j['points']]);pts=row['xyz'][ids];dr=np.array(j['horizontal_direction_unit_xy']);side=np.array(j['vertical_up_direction_unit_xy']);length,width=j['extent_m'];q=row['xyz'][:,:2]-j['center_local_xy'];mask=(abs(q@dr)<=length/2)&(abs(q@side)<=width/2);assert np.array_equal(ids,np.flatnonzero(mask));assert reference_ids is None or np.array_equal(ids,reference_ids);reference_ids=ids
   states=status(z[ids],row['row_tau_m'][ids]);assert list(states)==[r['status'] for r in j['points']]
   for rid,r in zip(ids,j['points']):assert (r['signed_distance_m'] is None and not np.isfinite(z[rid])) or r['signed_distance_m']==float(z[rid])
   counts={k:int(((lab[ids]==2)&(states==k)).sum()) for k in ['in','far','none']};assert counts==j['case2_state_counts']
 for key,name in [('c3','c3_section_data_with_judgment'),('c3_edge','c3_edge_section_data')]:
  j=json.loads((F9/(name+'.json')).read_text());c=case('c3');row,lab=data(c);s=selected(c)['section'] if key=='c3' else line9(key)['section'];ids=np.flatnonzero(section_mask(row['xyz'],s));assert [int(x) for x in ids]==[r['row_id'] for r in j['gt_points']];assert 'judgment_mesh' in j['surfaces'];assert j['line']['length_m']==s['length_m']
  for m in j['surfaces']:
   z=loadz(scorepath(c,m),['row_s'])['row_s']
   for r in j['gt_points']:
    rid=r['row_id'];v=r['scores'][m]['signed_distance_m'];assert (v is None and not np.isfinite(z[rid])) or v==float(z[rid])
  if key=='c3':
   old=json.loads((F6/f"{c['id']}_section_data.json").read_text());assert all(j['surfaces'][m]==v for m,v in old['surfaces'].items())
 c=case('c4');row,_=data(c);ids=np.flatnonzero(section_mask(row['xyz'],selected(c)['section']));j=json.loads((F9/'c4_section_gt_all.json').read_text());assert list(ids)==[r['row_id'] for r in j['gt_points']];assert j['verification']['all_rows_already_in_addendum6']
 split=json.loads((F9/'c3_case2_split_top.json').read_text());assert split['points_inside_image']==split['n_case2'];cur=json.loads((W9/'current_c3_split.json').read_text());assert cur['n']==49
 edge=json.loads((W9/'edge_selected.json').read_text());assert 3<=edge['section']['length_m']<=6 and edge['selection']['n_case2']>=20 and edge['selection']['n_edge_only']>=20 and edge['selection']['distance_from_current_segment_m']>5
 # Recompute the deterministic winner from the entire saved candidate population.
 allr=json.loads((W9/'edge_candidates.json').read_text())['candidates'];eligible=[r for r in allr if r['eligible']];ranked=[r for r in eligible if r['rank_pass']];best=min(ranked or eligible,key=lambda r:(r['score_sum_abs_pp'],-r['n_case2'],r['candidate_id']));assert best==edge['selection']
 receipt=dict(at=now(),status='PASS_SAVED_VALUES_SCOPE_AND_ARCHIVE_INPUTS',protected_previous_outputs=len(protected),new_images=len(checks),checked_images=checks,photo_pair_c2_c3_identical=True,no_new_scores=True,no_training=True,new_check_figures=0,photo_visibility_status='PARTIAL_NO_STRICT_CAMERA',c4_requested_upper_structure_identity='UNAVAILABLE_EXACT_ID',scientific_verdict=None);dump(D/'verification/addendum9.json',receipt);return receipt

def report():
 text=[]
 for key,title in [('c3','1. B0 항공 LiDAR 경우 2 나눔'),('c1','B173 항공 LiDAR 경우 2 나눔')]:
  j=json.loads((T9/(key+'_case2_split.json')).read_text());text.extend([title,'',f"경우 2 전체 {j['n_case2']:,}점. 완전성 단위 %. 저장된 preservation.py 결과와 단계 1 row_s를 그대로 집계했다.",'','|칸|점 수|비율 %|prior|MVS|판단 면|정답 판단 면|늘 보존 면|LGDM|GeoGS|본 방법|','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'])
  for r in j['rows']:text.append('|'+r['division']+(' (적음)' if r['n_gt']<1000 else '')+'|'+str(r['n_gt'])+'|'+f"{r['percent']:.2f}"+'|'+ '|'.join(f"{r[m+'_completeness_pct']:.2f}" if r[m+'_completeness_pct'] is not None else '확인 불가' for m in MS)+'|')
  text+=['']
 text+=['무늬 없음: 원본 사진 PIL 회색값/255의 np.gradient 크기 < 0.02137인 관측이 절반 이상. 관측은 고정 지형 중력 위 방향에서 20° 이내인 학습 시선만 사용한다.','꺾이는 곳: 사전 정보 패치 접선 네 방향 0.25m 이웃을 찾고, 0.125m 안에 중심이 없거나 Z 차가 0.5m를 넘는 패치에서 XY 거리 1m 이내. 따라서 이 이름은 높이 턱뿐 아니라 패치 경계·이웃 결측도 포함하는 기존 가장자리 지표다. 두 장면 모두 무늬 확인 불가 0점.','늘 보존 면은 기존 always_keep_mesh(절단 거리 0.25m)이며 0.10m 진단판과 섞지 않았다.','', '2. 고른 사진','']
 for key in ['c1','c2','c3','c4']:
  j=json.loads((F9/(key+'_photo.json')).read_text());cam=j['camera'];inside=100*np.mean(j['line_points_inside_image']);occ=100*np.mean(j['line_occluded']);text.append(f"- {key}: {cam['name']}, 광축 높이각 {cam['optical_axis_elevation_deg']:.2f}°, 건물 외곽 지지점 화면 내 {100*cam['selection']['building_in_image_fraction']:.2f}%, 선 화면 내 {inside:.1f}%, MVS상 선 가림 {occ:.1f}%. 등록된 참값 XYZ로 건물 전체 범위를 확인했다. MVS 지붕 가시 비율 {100*cam['selection']['MVS_roof_visible_fraction']:.1f}%. 엄격 조건 충족 시 점유율 최대, 미충족 시 대상·지붕의 MVS 가시 비율을 우선했다.")
 text+=['','c2·c3는 왜곡 보정과 자르기까지 동일한 사진이다. 사진의 경우 점은 MVS 광선이 0.15m 이상 앞서 닿는 점을 제외했다. MVS에 hit가 없으면 가림 아님으로 처리하되 JSON에 깊이 확인 불가를 따로 기록했다.']
 for key in ['c3','c3_edge']:
  name=key+'_closeup_photo';j=json.loads((F9/(name+'.json')).read_text());cam=j['camera'];sel=cam['selection'];text.append(f"- {key} 확대: {cam['name']}, 원본 자르기 폭 {sel['native_width']:.1f}px → 804px, 선 가로 폭 {100*sel['line_width_fraction']:.1f}%. 전체 사진보다 대상이 크게 찍힌 학습 사진으로 교체.")
 text+=['','3. 점 상태 그림: 범위 안 경우 2 전체','', '|자리|면|τ 안|τ 밖|면 없음|합계|','|---|---|---:|---:|---:|---:|']
 for key in ['c3','c3_edge']:
  for m in ['mvs','FINALTRAIN_30000']+(['GeoGS_30000','judgment_mesh'] if key=='c3' else []):
   j=json.loads((F9/(key+'_points_'+m+'.json')).read_text());n=j['case2_state_counts'];text.append(f"|{key}|{m}|{n['in']}|{n['far']}|{n['none']}|{j['n_case2']}|")
 text+=['','4. 단면 보강',''];j=json.loads((F9/'c3_section_data_with_judgment.json').read_text());text.append(f"c3 전체 선 {j['line']['length_m']:.4f}m, 참값 {j['reference_points_all_cases']:,}점. 기존 다섯 면의 교선을 그대로 두고 judgment_mesh 교선만 추가했다.")
 j=json.loads((F9/'c4_section_gt_all.json').read_text());v=j['verification'];text.append(f"c4 높이 제한 없는 1m 띠의 단계 1 참값 {v['all_reference_rows']:,}점은 모두 덧붙임 6에 이미 포함돼 있었다. 이번 JSON에도 전량 제공한다. 상부 끝 점군 {v['upper_group_count']}점, 지역 Z {v['upper_group_local_z_range'][0]:.4f}~{v['upper_group_local_z_range'][1]:.4f}m, s {v['upper_group_s_range'][0]:.3f}~{v['upper_group_s_range'][1]:.3f}m 역시 전부 포함됐다.");text.append('상부 점군은 Z의 0.5m 초과 공백으로 분리한 기하 그룹이다. 요청한 약 2.7m 위 구조물의 정확한 XY·식별자가 없어 그 구조물과 이 그룹이 같은지는 확인 불가다. 참값 누락 여부는 구조물 이름과 무관하게 전량 비교했다.')
 text+=['','5. 여섯 장면의 경우 점 수','', '|장면|전체|경우 0|경우 1|경우 2|경우 3|경우 4|미분류|사전 면 없음(중복)|','|---|---:|---:|---:|---:|---:|---:|---:|---:|'];j=json.loads((T9/'case_counts.json').read_text())
 for r in j['rows']:text.append('|'+r['site']+' '+r['prior']+'|'+ '|'.join(str(r[k]) for k in ['n_total','case_0','case_1','case_2','case_3','case_4','n_unassigned','prior_surface_absent_total'])+'|')
 text+=['','적음: 참값 1,000점 미만인 칸. 위 점 상태 그림의 두 영역과 두 후보 단면도 모두 적음에 해당한다. 경우 수 표에서는 B173 ALS 경우4, B0 ALS 경우1·3·4가 적음이다.','분모는 15~18쪽 완전성 표와 같은 단계 1 참값 행·경우 분류다. 장면 전체 수와 해당 경우의 완전성 분모는 구별한다. 원래 normal_line.cases는 사전 면 없음도 경우 1 또는 3에 배정하고 별도 중복 플래그로 센다. 따라서 사전 면 없음 수를 경우 0~4 합계에서 다시 빼지 않았다. 미분류 까닭별 수와 경우 비율은 case_counts.csv에 있다.','', '6. 대체 규칙과 제한','', '- 요청한 광축 30~60°에서 엄격 조건을 만족하는 사진이 없으면 70°까지의 경사사진으로 후보를 확장했다(실제 각도는 위 표·JSON에 기록). 건물 전체 화면 포함, MVS에 연직 투영한 같은 XY의 대상 선·지붕 가시 비율 98% 이상 여부, 대상 가시 비율, 지붕 가시 비율, 점유율 순으로 골랐다. 이 투영은 사진 선택에만 썼다. 전달하는 선 XYZ와 경우 점의 0.15m 가림 판정은 원래 참값 높이 그대로다. c3 현재 참값 높이의 선은 원래 30~60° 후보 전부에서 MVS상 가려졌다.','- 진단 정사영상은 덧붙임 6과 같은 원본 래스터를 쓰되, 기존 잘라낸 범위에서 1,450점 중 736점만 들어와 건물과 경우 2 전체를 포함하도록 범위를 넓혔다.','- 사진 범위에 원본 LoD2 Z가 섞인 초기 구도를 발견해 수정했다. LoD2는 GroundSurface XY 건물 식별에만 쓰고 등록된 단계1 참값 XYZ로 구도를 정했다. 사진의 건물 포함 비율은 그 참값의 3D 볼록껍질이 화면 안에 들어오는 비율이며, 실제 보이는 외벽 면적 비율은 아니다. 실제 점 가림 수는 별도 JSON에 있다.','- 점 상태 그림은 모든 요청 점을 보이는 대로가 아니라 XY 범위로 표시한다. 정사영상의 원 깊이가 없어 선 가림은 null로 명시했다.','- 확대 사진 저장 중 numpy.bool_ JSON 직렬화 오류 1회 발생 후 Python bool 변환으로 같은 설정 재실행했다.','', '7. 두 번째 후보 비교','']
 cur=json.loads((W9/'current_c3_split.json').read_text());text.append('현재 자리 49점: '+', '.join(f'{k} {v}점' for k,v in cur['counts'].items())+'.');e=json.loads((W9/'edge_selected.json').read_text());r=e['selection'];text.append(f"두 번째 자리: A 지역 XY ({r['A_x']:.6f}, {r['A_y']:.6f}), A′ ({r['Aprime_x']:.6f}, {r['Aprime_y']:.6f}); EPSG:25832 A {e['A_EPSG25832_xy']}, A′ {e['Aprime_EPSG25832_xy']}; 길이 {r['length_m']}m, 기존 선과 최소 거리 {r['distance_from_current_segment_m']:.3f}m. 경우 2 {r['n_case2']}점 중 꺾이는 곳만 {r['n_edge_only']}점. "+', '.join(f"{m} {r[m+'_completeness_pct']:.2f}%" for m in ['FINALTRAIN_30000','fusion','GeoGS_30000'])+'.');text.append('후보 중심은 꺾이는 곳만 점에서 만들었으며, 이 부분집합도 띠 안 20점 이상인 후보만 남겼다. 같은 가장자리 패치의 2m 이웃 PCA에 수직으로 길이 3·4·5·6m 선을 만들고, 덧붙임 6처럼 띠 안 경우 2 전체로 최소 점 수·순위·표 차이를 계산했다. 이 선도 순수하게 꺾이는 곳만 점으로 구성된 띠는 아니다. 순위 조건을 통과했다.');text+=['','확대 사진은 원본 폭 804px 이상인 후보를 먼저 골랐고, 그런 사진이 없는 현재 c3는 가능한 최대 원본 폭 493.2px를 확대했다. 상세 후보의 원본 해상도·MVS 가림은 JSON에 공개했다.', '학습·재채점·새 메시·추가 확인 그림 없음. scientific_verdict: null']
 (D/'보고_덧붙임9.md').write_text('\n'.join(text)+'\n')

def package():
 paths=sorted(F9.glob('*'))+sorted(T9.glob('*'))+[D/'보고_덧붙임9.md'];archive=O/'delivery/PHD-MAIN-GTJUDGE-v1_사례쪽실사.zip';assert not archive.exists();members={str(p.relative_to(D)):sha(p) for p in paths};manifest=dict(at=now(),files=members,scientific_verdict=None)
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in paths:z.write(p,str(p.relative_to(D)))
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for n,h in members.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
 dump(D/'verification/addendum9_archive.json',dict(at=now(),path=str(archive),sha256=sha(archive),members=len(members)+1,bytes=archive.stat().st_size,status='PASS_ZIP_CRC_AND_MEMBER_SHA256',scientific_verdict=None));print('ADD9_DELIVERED',archive,len(members)+1,flush=True)
if __name__=='__main__':finalize_metadata();validate();report();package()
