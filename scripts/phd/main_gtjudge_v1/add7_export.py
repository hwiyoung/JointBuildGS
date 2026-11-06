"""Fixed addendum4 hip-end section and JSON-only projections; no image writes."""
from add6_common import *
from add6_sections import pieces

A7=json.loads((C/'addendum7.json').read_text())
assert sha(C/'addendum7.json')==json.loads((C/'addendum7.lock.json').read_text())['config_sha256']
W7=O/'addendum7';F7=D/'figures/addendum7';T7=D/'tables/addendum7'
for folder in [W7,F7,T7]:folder.mkdir(parents=True,exist_ok=True)

def main():
 c=case('c2');old=getcase(c);s=old['section'];ends=np.array([s['start'],s['end']]);assert np.allclose(ends,A7['requested_rounded_xy'],rtol=0,atol=5e-6)
 length=float(np.linalg.norm(ends[1]-ends[0]));direction=(ends[1]-ends[0])/length;assert abs(length-18.2)<1e-10
 line=np.array(old['annotation_line_xyz']);assert np.allclose(line[:,:2],np.linspace(*ends,len(line)),rtol=0,atol=1e-12)
 root=root_of(c);oldcase=AW/'cases'/f"{c['id']}.json";taupath=R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv';source=[C/'addendum7.json',Path(__file__),Path(__file__).with_name('add6_sections.py'),Path(__file__).with_name('add6_common.py'),Path(__file__).with_name('add4_common.py'),R/'scripts/phd/main_rescore_v1/figures.py',oldcase,root/'rows.npz',root/'stage1_cells.npz',taupath]
 bindings={}
 for method in A7['methods']:
  meta_path=root/'distances'/f'{method}.json';meta=json.loads(meta_path.read_text());mesh=meshpath(c,method);assert proof(mesh)['sha256']==meta['mesh_sha256'];bindings[method]=dict(mesh=proof(mesh),scores=proof(root/'distances'/f'{method}.npz'));source.extend([mesh,meta_path,root/'distances'/f'{method}.npz'])
  cached=AW/'sections'/c['id']/f'{method}.npz'
  if cached.exists():source.extend([cached,AF/c['id']/f'section_{method}.json'])
 for stem in A7['image_stems']:source.extend([F6/(stem+'.png'),F6/(stem+'.json')])
 dump(W7/'input_lock.json',dict(at=now(),config_sha256=sha(C/'addendum7.json'),sources=[proof(p) for p in source],scientific_verdict=None))
 row=loadz(root/'rows.npz');labels=loadz(root/'stage1_cells.npz')['case_id'];ids=np.flatnonzero(section_mask(row['xyz'],s));P=row['xyz'][ids];along=(P[:,:2]-ends[0])@direction;target=labels[ids]==1;metrics={};scores={};surfaces={};projections={};line_methods={'prior':A7['image_stems'][1],'FINALTRAIN_30000':A7['image_stems'][2]};cache_use={}
 print('ADD7_FIXED_STRIP',len(ids),int(target.sum()),length,flush=True)
 for method in A7['methods']:
  mesh=meshpath(c,method);cp=AW/'sections'/c['id']/f'{method}.npz';V=F=None
  if cp.exists():
   oldmeta_path=AF/c['id']/f'section_{method}.json';oldmeta=json.loads(oldmeta_path.read_text());assert oldmeta['section']['start']==s['start'] and oldmeta['section']['end']==s['end'];assert next(x['sha256'] for x in oldmeta['sources'] if x['path']==str(mesh))==bindings[method]['mesh']['sha256'];seg=clip_segments(loadz(cp)['segments'],length);source.extend([cp,oldmeta_path]);cache_use[method]='verified addendum4 exact-line intersections'
  else:
   V,F=read_surface(mesh);seg=clip_segments(section_segments(V,F,s),length);savez(W7/'sections'/f'{method}.npz',segments=seg);cache_use[method]='exact original mesh centre-plane cut; no mesh reconstruction'
  surfaces[method]=pieces(seg);z=loadz(root/'distances'/f'{method}.npz',['row_s'])['row_s'][ids];scores[method]=z;metrics[method]=values(z[target],row['row_tau_m'][ids][target])
  if method in line_methods or method=='mvs':
   if V is None:V,F=read_surface(mesh)
   scene=MeshScene(V,F)
   if method=='mvs':
    stem=A7['image_stems'][0];imeta=json.loads((F6/(stem+'.json')).read_text());uv=pixels(xyuv(line),imeta['bounds_uv'],imeta['size_px']);top=float(V[:,2].max()+10);origin=line.copy();origin[:,2]=top;hit=scene.cast(origin,np.tile([0.,0.,-1.],(len(line),1)));occluded=np.isfinite(hit)&(top-hit>line[:,2]+.15);inside=((uv>=0)&(uv<=imeta['size_px'])).all(1);extra=dict(bounds_uv=imeta['bounds_uv'],original_ortho_depth_available=False,occlusion_rule='MVS vertical-ray proxy; original ortho has no per-pixel depth; hit >0.15m above reference-height annotation')
   else:
    stem=line_methods[method];imeta=json.loads((F6/(stem+'.json')).read_text());cam=imeta['camera'];assert cam==old['camera'];uv,depth=camera_projection(line,cam);origin=np.array(cam['centre']);ray=line-origin;distance=np.linalg.norm(ray,axis=1);ray/=distance[:,None];hit=scene.cast(np.broadcast_to(origin,ray.shape),ray);occluded=np.isfinite(hit)&(hit<distance-.15);inside=(depth>0)&((uv>=0)&(uv<=cam['output_size_px'])).all(1);extra=dict(camera=cam,occlusion_rule='same addendum6 >0.15m foreground-hit rule, on the original rendered mesh; no-hit visibility unknown')
   projections[stem]=dict(case=c['id'],reference_image=proof(F6/(stem+'.png')),reference_image_metadata=proof(F6/(stem+'.json')),size_px=imeta['size_px'],A_px=uv[0].tolist(),Aprime_px=uv[-1].tolist(),line_polyline_px=uv.tolist(),line_xyz=line.tolist(),line_occluded=occluded.tolist(),line_points_inside_image=inside.tolist(),line_visibility_unknown=(~np.isfinite(hit)).tolist(),line_draw_mask=old['annotation_display_mask'],line_drawn=False,new_image_rendered=False,annotation_height_rule='exact addendum4 reference-height annotation and its disconnected-segment mask',occlusion_mesh=proof(mesh),crs='EPSG:25832',local_world_shift=SHIFT.tolist(),config_sha256=sha(C/'addendum7.json'),sources=[proof(p) for p in [oldcase,mesh,Path(__file__)]],scientific_verdict=None,**extra)
   del scene
  del V,F;gc.collect();print('ADD7_METHOD',method,int(target.sum()),metrics[method]['within_pct'],cache_use[method],flush=True)
 gt=[dict(row_id=int(rid),s=float(along[i]),z=float(P[i,2]),case_id=int(labels[rid]),tau_m=float(row['row_tau_m'][rid]),scores={m:dict(status=str(status(np.array([z[i]]),np.array([row['row_tau_m'][rid]]))[0]),signed_distance_m=float(z[i]) if np.isfinite(z[i]) else None) for m,z in scores.items()}) for i,rid in enumerate(ids)]
 with taupath.open() as f:tau=next(x for x in csv.DictReader(f) if x['site']==c['site'] and x['prior']==c['prior'])
 observed=sorted(A7['expected_order'],key=lambda m:-metrics[m]['within_pct']);same=observed==A7['expected_order'];ranking=dict(expected_order=A7['expected_order'],observed_order=observed,matches=same,rule='descending unrounded completeness of case 1 only; fixed line, no candidate selection or ranking tolerance')
 result=dict(case=c['id'],line=dict(A_local_xyz=line[0].tolist(),Aprime_local_xyz=line[-1].tolist(),A_EPSG25832_xy=(ends[0]+SHIFT[:2]).tolist(),Aprime_EPSG25832_xy=(ends[1]+SHIFT[:2]).tolist(),length_m=length,length_definition='horizontal XY distance from south A to ridge-side Aprime',direction='fixed addendum4 hip-end line',direction_unit_xy=direction.tolist(),half_width_m=.5,selection_rank=None,score_sum_abs_pp=None,selected_by='user-fixed addendum4 line; no new candidates',coordinates_rule='retain original addendum4 precision; agrees with requested rounded XY within 5 micrometres',endpoint_z_rule='same inherited reference-height annotation used for all projections',vertical_plane_anchor_z_local_m=old['line_xyz'][0][2]),tau_m={'roof':float(tau['roof_tau_m']),'wall':float(tau['wall_tau_m'])},surfaces=surfaces,gt_points=gt,strip_metrics=metrics,metric_population='case_id=1 only among all saved reference rows within the fixed 1m strip',reference_points_all_cases=len(ids),reference_points_target_case=int(target.sum()),intersection_rule='single vertical centre plane; no strip averaging; disconnected pieces retained; coincident endpoints joined at 1e-6m',surface_sources=bindings,intersection_cache_use=cache_use,ranking=ranking,config_sha256=sha(C/'addendum7.json'),runtime=dict(image=os.environ.get('GTJUDGE_IMAGE'),source_commit=os.environ.get('GTJUDGE_COMMIT'),python=sys.version,numpy=np.__version__),sources=[proof(p) for p in dict.fromkeys(source)],scientific_verdict=None)
 dump(F7/'c2_hip_section_data.json',result)
 for stem,meta in projections.items():dump(F7/('c2_hip_line_'+stem+'.json'),meta)
 rows=[dict(method=m,n_case1=int(target.sum()),completeness_pct=metrics[m]['within_pct'],far_pct=metrics[m]['far_hit_pct'],none_pct=metrics[m]['no_surface_pct']) for m in A7['methods']]
 with (T7/'c2_hip_strip_metrics.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 names={'FINALTRAIN_30000':'본 방법','GeoGS_30000':'GeoGS','fusion':'LGDM','prior':'사전 정보','mvs':'MVS','judgment_mesh':'판단 메시'};text=[f"띠 안 경우 1: {int(target.sum()):,}점. 고정 선 길이 {length:.2f}m, 폭 1m.",'','|방법|경우 1 완전성 (%)|','|---|---:|']
 for m in ['FINALTRAIN_30000','GeoGS_30000','fusion','prior','mvs','judgment_mesh']:text.append(f"|{names[m]}|{metrics[m]['within_pct']:.2f}|")
 text += ['', '방법 차례: '+' > '.join(names[m] for m in observed)+'. 요청한 표의 차례와 '+('같음.' if same else '다름.'),'','덧붙임4 원본 좌표 정밀도를 유지했다. 다섯 기존 교선 캐시를 검증해 재사용하고 판단 메시 교선만 추출했다. 채점값은 모두 단계1 저장값이다. 이미지 생성·수정 없음.','투영 선의 화면 내 비율: '+', '.join(stem.removeprefix(c['id']+'_')+f" {100*np.mean(meta['line_points_inside_image']):.1f}%" for stem,meta in projections.items())+'.','확인 불가: 정사영상 원 깊이는 없어 MVS 연직 광선으로 가림을 대리했다. 원본의 끊긴 선 구간 마스크도 함께 제공했다.','scientific_verdict: null']
 (D/'보고_덧붙임7.md').write_text('\n'.join(text)+'\n');print('ADD7_DONE',json.dumps(ranking),flush=True)

if __name__=='__main__':main()
