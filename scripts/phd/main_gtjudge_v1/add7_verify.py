"""Validate fixed-line raw data, exact cached geometry, projections and preservation."""
from add7_export import *

def canonical_edges(seg):
 q=np.rint(np.asarray(seg).reshape(-1,2,2)/1e-6).astype('i8');q=q[(q[:,0]!=q[:,1]).any(1)]
 swap=(q[:,0,0]>q[:,1,0])|((q[:,0,0]==q[:,1,0])&(q[:,0,1]>q[:,1,1]));q[swap]=q[swap,::-1];q=q.reshape(-1,4)
 return q[np.lexsort(q.T[::-1])]

def main():
 c=case('c2');old=getcase(c);data=json.loads((F7/'c2_hip_section_data.json').read_text());s=old['section'];root=root_of(c);row=loadz(root/'rows.npz');labels=loadz(root/'stage1_cells.npz')['case_id'];take=section_mask(row['xyz'],s);ids=np.flatnonzero(take);target=take&(labels==1);assert data['reference_points_target_case']==int(target.sum());assert data['reference_points_all_cases']==len(ids);assert np.array_equal([p['row_id'] for p in data['gt_points']],ids)
 assert set(data['surfaces'])==set(data['strip_metrics'])==set(A7['methods']);assert np.allclose([data['line']['A_local_xyz'][:2],data['line']['Aprime_local_xyz'][:2]],[s['start'],s['end']],rtol=0,atol=1e-12)
 assert np.allclose(data['line']['A_EPSG25832_xy'],np.array(s['start'])+SHIFT[:2],rtol=0,atol=1e-9);assert np.allclose(data['line']['Aprime_EPSG25832_xy'],np.array(s['end'])+SHIFT[:2],rtol=0,atol=1e-9)
 dir=np.asarray(data['line']['direction_unit_xy']);assert abs(np.linalg.norm(dir)-1)<1e-12;assert np.allclose([p['s'] for p in data['gt_points']],(row['xyz'][ids,:2]-s['start'])@dir,rtol=0,atol=1e-10);assert np.array_equal([p['z'] for p in data['gt_points']],row['xyz'][ids,2]);assert np.array_equal([p['case_id'] for p in data['gt_points']],labels[ids])
 methods=[]
 for method in A7['methods']:
  z=loadz(root/'distances'/f'{method}.npz',['row_s'])['row_s'];expected=values(z[target],row['row_tau_m'][target]);assert expected==data['strip_metrics'][method];observed=[p['scores'][method] for p in data['gt_points']];assert np.array_equal([x['status'] for x in observed],status(z[ids],row['row_tau_m'][ids]));assert np.array_equal(np.array([np.nan if x['signed_distance_m'] is None else x['signed_distance_m'] for x in observed]),z[ids],equal_nan=True)
  cp=AW/'sections'/c['id']/f'{method}.npz';cp=cp if cp.exists() else W7/'sections'/f'{method}.npz';segments=clip_segments(loadz(cp)['segments'],data['line']['length_m']);out=np.concatenate([np.stack([np.asarray(p)[:-1],np.asarray(p)[1:]],axis=1) for p in data['surfaces'][method]]) if data['surfaces'][method] else np.empty((0,2,2));assert np.array_equal(canonical_edges(segments),canonical_edges(out)),method
  methods.append(dict(method=method,n=int(target.sum()),completeness_pct=expected['within_pct'],original_intersection_edges_preserved=True))
 frames=[]
 for stem in A7['image_stems']:
  j=json.loads((F7/('c2_hip_line_'+stem+'.json')).read_text());original=json.loads((F6/(stem+'.json')).read_text());line=np.array(j['line_xyz']);assert np.array_equal(line,np.array(old['annotation_line_xyz']));assert j['A_px']==j['line_polyline_px'][0] and j['Aprime_px']==j['line_polyline_px'][-1]
  uv=pixels(xyuv(line),original['bounds_uv'],original['size_px']) if 'top_crop' in stem else camera_projection(line,original['camera'])[0];assert np.allclose(uv,j['line_polyline_px'],rtol=0,atol=1e-9);assert len(j['line_occluded'])==len(j['line_points_inside_image'])==len(line)==257;assert len(j['line_draw_mask'])==256;assert j['line_drawn'] is False and j['new_image_rendered'] is False;assert sha(F6/(stem+'.png'))==j['reference_image']['sha256'];frames.append(dict(image=stem+'.png',line_inside_fraction=float(np.mean(j['line_points_inside_image'])),occluded_n=sum(j['line_occluded']),unknown_visibility_n=sum(j['line_visibility_unknown'])))
 lock=json.loads((C/'addendum7.lock.json').read_text());assert sha(Path(__file__).with_name('add7_export.py'))==lock['source_sha256'];sources=json.loads((W7/'input_lock.json').read_text())['sources']
 for src in sources:assert proof(src['path'])['sha256']==src['sha256']
 protected=json.loads((W7/'previous_figures_sha256.json').read_text())
 for name,h in protected.items():assert sha(R/name)==h,name
 assert {p.name for p in F7.iterdir()}=={'c2_hip_section_data.json',*(('c2_hip_line_'+stem+'.json') for stem in A7['image_stems'])}
 receipt=dict(at=now(),status='PASS_FIXED_LINE_SAVED_SCORES_PROJECTIONS_AND_PRESERVATION',methods=methods,frames=frames,old_figure_files_preserved=len(protected),new_figures=0,new_meshes=0,new_scores=0,new_candidates=0,training_started=False,training_interrupted=False,scientific_verdict=None);dump(D/'verification/addendum7.json',receipt)
 files=sorted(F7.glob('*.json'))+[T7/'c2_hip_strip_metrics.csv',D/'보고_덧붙임7.md'];dest=O/'delivery/PHD-MAIN-GTJUDGE-v1_모임지붕끝단면.zip';assert not dest.exists();members=[dict(member=str(p.relative_to(D)),sha256=sha(p),bytes=p.stat().st_size) for p in files]
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p,item in zip(files,members):z.write(p,item['member'])
  z.writestr('manifest.json',json.dumps(dict(task_id=A7['task_id'],addendum=7,config=A7,files=members,verification=receipt,scientific_verdict=None),ensure_ascii=False,indent=2))
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for item in members:assert hashlib.sha256(z.read(item['member'])).hexdigest()==item['sha256']
 dump(D/'verification/addendum7_archive.json',dict(at=now(),path=str(dest),sha256=sha(dest),bytes=dest.stat().st_size,members=len(members)+1,status='PASS_ZIP_CRC_AND_MEMBER_SHA256',scientific_verdict=None));print('ADD7_VERIFIED',json.dumps(receipt,ensure_ascii=False),str(dest),flush=True)

if __name__=='__main__':main()
