"""Verify every delivered array/table, report numbers and seal the archive."""
from add10_common import *
import shutil

def verify_csv(key):
 c=case(key);row,lab=data(c);scores={m:loadz(p,['row_s'])['row_s'] for m,p in stored_scores(c).items()};states={m:status(v,row['row_tau_m']) for m,v in scores.items()};n=0
 with gzip.open(T10/(key+'_reference_rows.csv.gz'),'rt',newline='') as f:
  for r in csv.DictReader(f):
   i=int(r['row_id']);assert i==n;assert int(r['eligible'])==1 and int(r['case_id'])==int(lab[i]);assert r['no_case_reason']=='';assert np.array_equal([float(r[k]) for k in ['x','y','z']],row['xyz'][i]);assert np.array_equal([float(r[k]) for k in ['nx','ny','nz']],row['normal'][i]);assert float(r['E'])==row['xyz'][i,0]+SHIFT[0] and float(r['N'])==row['xyz'][i,1]+SHIFT[1]
   for m,s in scores.items():assert r[m+'_status']==states[m][i] and ((not r[m+'_sd_m'] and not np.isfinite(s[i])) or (r[m+'_sd_m'] and float(r[m+'_sd_m'])==s[i]))
   n+=1
 assert n==len(lab);return n

def selected_pixels(mask):
 good=np.flatnonzero(mask);bad=np.flatnonzero(~mask);return np.r_[good[np.linspace(0,len(good)-1,min(4,len(good))).astype(int)],bad[np.linspace(0,len(bad)-1,min(2,len(bad))).astype(int)]]

def sample_rays(cam,indices):
 W,H=cam['output_size_px'];orig=[];directions=[]
 for i in indices:
  y,x=divmod(int(i),W);o,d=ray_rows(cam,y,y+1);orig.append(o[x]);directions.append(d[x])
 return np.array(orig),np.array(directions)

def verify():
 rows={};arrays=0;mesh_samples=0;disc_samples=0
 for key in A10['cases']:
  rows[key]=verify_csv(key);c=case(key);row,_=data(c);P=row['xyz'];N=row['normal'];jobs=camera_jobs(key);rad=json.loads((W10/(key+'_scene.json')).read_text())['radius_m']
  for job in jobs:
   stem=key+'_'+job['id'];cam=job['camera'];W,H=cam['output_size_px'];ref=loadz(F10/(stem+'_refrow.npz'))['row_id'];assert ref.shape==(H,W) and ref.dtype==np.int32 and ref.min()>=-1 and ref.max()<len(P);meta=json.loads((F10/(stem+'_camera.json')).read_text());assert meta['camera']==cam;assert len(meta['line_polyline_px'])==len(meta['line_occluded'])==len(meta['line_points_inside_image']);assert len(meta['box_corners_px'])==len(meta['box_corner_occluded'])==4
   ij=selected_pixels(ref>=0);oo,dd=sample_rays(cam,ij)
   for j,o,d in zip(ij,oo,dd):
    den=N@d;num=np.einsum('ij,ij->i',P-o,N);t=np.divide(num,den,out=np.full(len(P),np.inf),where=abs(den)>1e-12);ok=np.isfinite(t)&(t>0);candidate=np.flatnonzero(ok);delta=o+t[candidate,None]*d-P[candidate];candidate=candidate[(delta*delta).sum(1)<=rad*rad];expected=int(candidate[np.argmin(t[candidate])]) if len(candidate) else -1;assert int(ref.flat[j])==expected,(stem,j,expected,int(ref.flat[j]));disc_samples+=1
  for m in A10['render_methods']+(A10['c4_extra'] if key=='c4' else []):
   V,F=read_surface(meshpath(c,m));scene=MeshScene(V,F);del V,F;gc.collect()
   for job in jobs:
    stem=key+'_'+job['id']+'_'+m;cam=job['camera'];W,H=cam['output_size_px'];ids=loadz(F10/(stem+'_row.npz'))['row_id'];depth=loadz(F10/(stem+'_depth.npz'))['depth_m'];hit=np.asarray(Image.open(F10/(stem+'_hit.png')));shade=np.asarray(Image.open(F10/(stem+'_shade.png')));meta=json.loads((F10/(stem+'.json')).read_text());assert ids.shape==depth.shape==hit.shape==shade.shape==(H,W);assert ids.dtype==np.int32 and ids.min()>=-1 and ids.max()<len(P);assert np.isin(hit,[0,255]).all();mask=hit>0;assert np.array_equal(mask,np.isfinite(depth));assert (ids[~mask]==-1).all();assert (depth[mask]>0).all();assert shade[mask].min()>=140 and shade[mask].max()<=255;assert int(mask.sum())==meta['hit_pixels'];assert int((mask&(ids<0)).sum())==meta['hit_without_reference_row'];arrays+=4
    ij=selected_pixels(mask);oo,dd=sample_rays(cam,ij);rr=np.c_[oo,dd].astype('f4');cast=scene.sc.cast_rays(scene.o3d.core.Tensor(rr));tt=cast['t_hit'].numpy();norm=cast['primitive_normals'].numpy().astype(float)
    for k,j in enumerate(ij):
     assert np.isfinite(tt[k])==bool(mask.flat[j]);mesh_samples+=1
     if not np.isfinite(tt[k]):continue
     assert abs(float(depth.flat[j])-float(tt[k]*np.linalg.norm(rr[k,3:].astype(float))))<1e-4;n=norm[k]/np.linalg.norm(norm[k]);Q=rr[k,:3].astype(float)+tt[k]*rr[k,3:].astype(float);delta=P-Q;ax=delta@n;side=np.linalg.norm(delta-ax[:,None]*n,axis=1);candidate=np.flatnonzero(side<=.3);order=np.lexsort((candidate,abs(ax[candidate]),side[candidate]));expected=int(candidate[order[0]]) if len(candidate) else -1;assert int(ids.flat[j])==expected,(stem,j,int(ids.flat[j]),expected);assert int(shade.flat[j])==round(255*(.55+.45*min(1.,abs(n@dd[k]))))
   del scene;gc.collect()
  print('ADD10_VERIFIED',key,rows[key],flush=True)
 for src in json.loads((W10/'input_lock.json').read_text())['sources']:assert sha(src['path'])==src['sha256'],src['path']
 protected=json.loads((W10/'protected_before.json').read_text())
 for host,h in protected.items():
  rel=host.split('/JointBuildGS-exp/',1)[1];assert sha(R/rel)==h,host
 checks=sorted(F10.glob('*_check.png'));assert len(checks)==2
 for p in checks:im=Image.open(p);im.load();assert im.size==(804,1072) and im.mode=='RGB'
 receipt=record(dict(status='PASS_ALL_EXPORTED_ROWS_ARRAYS_AND_SAMPLED_GEOMETRY',exported_rows=rows,method_arrays=arrays,brute_force_real_mesh_query_samples=mesh_samples,brute_force_real_disc_samples=disc_samples,protected_previous_outputs=len(protected),check_images=2,new_training=False,new_scoring=False,new_mesh=False,GT_triangulated=False));dump(D/'verification/addendum10.json',receipt);return receipt

def report():
 den=json.loads((T10/'denominator_check.json').read_text());t=['1. 분모 확인','',f"네 자리 {sum(x['rows'] for x in den['scenes']):,}행 전부 내보냈다. eligible=1 행으로 경우별 완전성을 다시 집계한 {sum(x['checked_method_case_pairs'] for x in den['scenes'])}개 방법×경우 조합은 단계 1 저장 표와 일치하며 최대 차이는 0%p다. 미분류 행 0개. 사전 정보 면 없음은 기존 경우 1·3과 겹치는 표시이므로 경우에서 제외하지 않았다.",'','2. 화소 지도 크기와 원반 반지름','','|자리|카메라|크기 px|원반 반지름 m|','|---|---|---:|---:|']
 for key in A10['cases']:
  info=json.loads((W10/(key+'_scene.json')).read_text())
  for job in camera_jobs(key):W,H=job['camera']['output_size_px'];t.append(f"|{key}|{job['id']} / {job['camera']['name']}|{W}×{H}|{info['radius_m']:.9f}|")
 t+=['','원반 반지름은 각 장면 저장 참값 행의 3차원 최근접 이웃 간격 중앙값이다. 원반은 저장 법선에 수직이며, 광선과 원반 평면의 정확한 교점으로 가장 앞 원반을 골랐다. 참값은 삼각화하지 않았다.','깊이 NPZ 키는 depth_m(단위 광선 방향 거리 m, hit 없음 +inf), 행 NPZ와 refrow NPZ 키는 row_id(int32, 없음 −1)이다. hit PNG는 0/255, shade PNG는 8비트 단일 채널이다. 화소 중심은 (x+0.5,y+0.5), 원점은 왼쪽 위다. 음영은 round(255×(0.55+0.45|n·v|))이며, v는 해당 카메라 광선 단위 방향이다.','각 면 JSON에 단계 1 메시 경로·SHA256과 저장 채점 파일이 있다. 2DGS/CDGS 열 이름은 원래 파일명인 2DGS_30000/CDGS_30000을 썼다. fusion은 LGDM이다. A2·fix·alt_na·alt_da 및 늘 보존 0.10m 진단판도 저장값이 있는 장면만 추가했다. 요청한 최소 방법의 누락은 없다. signed distance는 저장된 법선 방향의 결과 면−참값 변위이며, 지붕은 위가 +, 벽은 가장 가까운 학습 카메라 쪽이 +다. none의 sd는 빈 CSV 필드다.','','3. 위에서 본 정사 투영과 맞춘 1칸 그림','']
 for key in ['c1','c2','c4']:
  j=next(j for j in camera_jobs(key) if j['id']=='b_top');t.append(f"- {key}: {Path(j['matched_image']).name}; bounds_uv={j['camera']['bounds_uv']}.")
 t+=['c2는 덧붙임 7 모임지붕 끝 투영 JSON이 참조한 덧붙임 6 top_crop_noline 그림이다. 단면은 모임지붕 끝 그대로이고, 끊긴 선 표시 마스크를 JSON에 유지했다. c4 a_render와 c_photo는 원래 카메라·자르기가 같아 두 이름으로 같은 자료를 냈다.','건물 윤곽은 네 자리 모두 LoD2 GroundSurface의 XY만 사용했다. 1칸 자리 상자는 덧붙임 9 photo.json의 네 모서리를 그대로 옮겼다. scene_bounds는 저장 참값 행 전체의 XY 최소·최대이며 실험 지역 경계도 별도 키에 실었다. GeoJSON은 지역 XY m이고 EPSG:25832로 바꾸는 평행이동을 명시했다.','','4. 가운데 면의 확인용 합성 화소 비율','','c3 (가) 804×1072의 단면 s=23.2~24.7m, ±0.5m 띠를 참값 높이 중앙값에서 투영한 다각형 안의 화소 중심을 분모로 삼았다. JSON에는 저장 참값 행으로 영역을 고른 보조 집계도 있다.','','|방법|영역 화소|in %|far %|none %|참값 행 없음 %|배경 %|','|---|---:|---:|---:|---:|---:|---:|']
 for r in json.loads((T10/'c3_middle_composite_pixels.json').read_text())['checks']:
  p=r['percent_all_region'];t.append(f"|{r['method']}|{r['central_region_pixels']}|"+'|'.join(f'{p[k]:.6f}' for k in ['in','far','none','unmapped_mesh','background'])+'|')
 t+=['','사진 배경·글자·선·상자 없는 확인용 합성 두 장만 만들었다. 색은 in #2EAA5A, far #D83730, none #3A3A3A이며, hit인데 row_id=−1이면 #DCDCDC에 음영을 곱했다.','','5. c3 숫자 진단','','5.1 유리창 참값 선택','', '덧붙임 9 add9_detail.panels는 현재 3m 선 주위 길이 7m·폭 4.4m XY 사각형의 모든 참값 행을 JSON에 넣고, 경우 2만 상태 색·반경 3.2px로, 다른 경우는 회색·반경 1.8px로 그렸다. 덧붙임 6 add6_sections는 전체 26.933m 선의 폭 1m 띠에서 모든 경우를 gt_points에 넣었다. 두 JSON 모두 경우 2만으로 행을 거르거나 사진 가림으로 행을 빼지 않았다.','유리창 실측 경계는 없다. 기존 확대 사진의 유리 안쪽 여섯 다각형을 고정했고 좌표를 c3_windows.json에 넣었다. 사진에 실제 XYZ를 투영해 안에 들어오는 점을 셌다. 면적은 s=22.6~25.6m·폭 4.4m 참값에 맞춘 평면으로 다각형을 역투영한 값이다. XY 역투영 영역의 별도 점 수도 JSON에 제공한다.','','|유리 영역|XY 면적 m²|원 드론 점|원 드론 점/m²|단계1 행|단계1 행/m²|경우 0/1/2/3/4/미분류|덧붙임9 포함 행|덧붙임6 포함 행|','|---|---:|---:|---:|---:|---:|---|---:|---:|']
 win=json.loads((T10/'c3_windows.json').read_text())
 for r in win['regions']:
  t.append(f"|{r['region']}|{r['plan_area_m2']:.6f}|{r['raw_drone_points']}|{r['raw_drone_points_per_plan_m2']:.3f}|{r['stage1_rows']}|{r['stage1_rows_per_plan_m2']:.3f}|"+'/'.join(str(r['case_counts'][str(k)]) for k in [0,1,2,3,4,-1])+f"|{r['ids_in_add9_points']}|{r['ids_in_add6_section']}|")
 t += ['',f"원 드론 원본 {win['raw_lidar']['header']['point_count']:,}점을 읽어 모든 반환을 셌으며 use/excl/thin 필터는 적용하지 않았다. 지역 Z에는 기존 단계 1 ULS 정렬량 {win['raw_lidar']['z_shift_to_stage1_m']:.12f}m를 적용했다. B0 별도 gt_primary 원 점군의 수·면적당 수도 JSON에 구별해 실었다. 해당 유리 영역의 미분류 행은 0개이고 no_case_reason은 빈 값이다.",'','|유리 영역|분모 화소|prior 면 %|MVS 면 %|본 방법 면 %|','|---|---:|---:|---:|---:|']
 for r in json.loads((T10/'c3_window_mesh_pixels.json').read_text())['rows']:t.append(f"|{r['region']}|{r['roi_pixels']}|{r['prior_hit_pct']:.6f}|{r['mvs_hit_pct']:.6f}|{r['FINALTRAIN_30000_hit_pct']:.6f}|")
 t+=['','5.2 가운데 면의 높이 퍼짐','','|띠 폭 m|행 수|높이 폭 m|높이 표준편차 m|경우 0/1/2/3/4|평면 잔차 표준편차 m|선 방향 기울기|폭 방향 기울기|','|---:|---:|---:|---:|---|---:|---:|---:|']
 mid=json.loads((T10/'c3_middle_strip.json').read_text())
 for r in mid['strips']:
  p=r['plane_fit'];t.append(f"|{r['width_m']}|{r['z']['n']}|{r['z']['range_m']:.6f}|{r['z']['std_m']:.6f}|"+'/'.join(str(r['case_counts'][str(k)]) for k in range(5))+f"|{p['residual']['std_m']:.6f}|{p['slope_along']:.6f}|{p['slope_across']:.6f}|")
 t+=['','기울기는 z=상수+기울기_s·(s−평균_s)+기울기_t·(t−평균_t)의 최소제곱 계수다. 표준편차는 ddof=0. 0.5m 구간의 점 수·높이, 좁은 띠의 0.1m 구간 높이, 선 방향만 맞춘 잔차와 2방향 평면 잔차를 c3_middle_strip.json에 실었다. 실제 판 골·이음매의 별도 실측 구분값은 없다.','','6. 명시하지 않은 부분에 쓴 규칙과 예외','', '- 행 선택 원기둥은 반지름 0.3m, 축 방향 제한 없이 해당 장면 저장 행 전체에서 옆 거리를 최소화했다. 옆 거리가 정확히 같으면 축 거리 절댓값, 그다음 작은 row_id 순이다. 3차원 최근접 거리를 목적값으로 쓰지 않았다.','- 원반은 반지름으로 장면별 저장 행 간격 중앙값을 그대로 썼다. 광선이 원반 평면과 평행이면 hit 없음, 원반이 겹치면 가장 앞의 양의 깊이, 깊이가 같으면 작은 row_id다.','- 사진 카메라는 색을 가져오지 않고 광선 기하만 사용했다. c3 두 배 버전은 원본 자르기를 유지하고 화소 중심을 새 해상도에서 계산했다.','- 위 정사 투영은 기존 bounds_uv와 크기를 그대로 사용하고, 모든 저장 참값보다 100m 위에서 지역 Z 아래 방향으로 광선을 쐈다. 별도 투영 근점·원점 높이는 JSON에 있다.','- 단면 선과 1칸 상자의 가려짐은 기존과 같은 MVS 광선, 0.15m 앞선 hit 기준이다. MVS hit가 없는 경우 unknown을 따로 제공했다.','- 유리창의 정확한 실측 경계와 판 골·이음매의 실측 구분은 확인 불가다. 유리 안쪽 고정 사진 다각형·참값 평면 면적을 대체 정의로 기록했고, 높이 퍼짐은 수치만 제공했다.','- 유리창 진단 JSON 저장의 중복 scientific_verdict 키 오류를 고친 뒤 같은 설정으로 진단을 재실행했다.','- 큰 NPZ/CSV.gz 원자료는 외부 artifact 폴더에도 보존하고 Git에는 SHA256·경로 목록을 남겼다. ZIP에는 원자료가 모두 들어 있다.','', '학습·재채점·새 메시·새 단면 선·지도 그림 없음. scientific_verdict: null.']
 (D/'보고_덧붙임10.md').write_text('\n'.join(t)+'\n')

def package():
 report();paths=sorted(F10.glob('*'))+sorted(T10.glob('*'))+[D/'보고_덧붙임10.md'];paths=[p for p in paths if p.is_file() and not p.name.startswith('.')];members={str(p.relative_to(D)):sha(p) for p in paths};external=[]
 for p in paths:
  if p.suffix=='.npz' or p.name.endswith('.csv.gz'):
   q=W10/'delivered_data'/p.relative_to(D);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);assert sha(q)==members[str(p.relative_to(D))];external.append(dict(repository_local_path=str(p.relative_to(R)) if p.is_relative_to(R) else 'docs/experiments/phd/main_gtjudge_v1/'+str(p.relative_to(D)),artifact_relative_path='phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/'+str(q.relative_to(O)),container_path=str(q),bytes=p.stat().st_size,sha256=sha(q)))
 dump(D/'verification/addendum10_payload_manifest.json',record(dict(backend='JBGS_ARTIFACT_ROOT',local_sibling='../JointBuildGS-artifacts',files=external,repository_copies='untracked local delivery copies; authoritative external copies and archive retained')))
 (F10/'.gitignore').write_text('*.npz\n');(T10/'.gitignore').write_text('*.csv.gz\n')
 archive=O/'delivery/PHD-MAIN-GTJUDGE-v1_결과면렌더.zip';assert not archive.exists()
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in paths:z.write(p,str(p.relative_to(D)))
  z.writestr('manifest.json',json.dumps(record(dict(files=members)),ensure_ascii=False,indent=2))
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for n,h in members.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
 dump(D/'verification/addendum10_archive.json',record(dict(status='PASS_ZIP_CRC_AND_MEMBER_SHA256',path=str(archive),members=len(members)+1,bytes=archive.stat().st_size,sha256=sha(archive))))
 print('ADD10_DELIVERED',archive,len(members)+1,archive.stat().st_size,flush=True)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='package':package()
 else:verify();package()
