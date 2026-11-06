"""Check original pixel identity, shading contract, proportions and sealed sources."""
from add8_shaded import *

def main():
 protected=json.loads((W8/'previous_figures_sha256.json').read_text())
 for name,h in protected.items():assert sha(R/name)==h,name
 for src in json.loads((W8/'input_lock.json').read_text())['sources']:assert proof(src['path'])['sha256']==src['sha256']
 lock=json.loads((C/'addendum8.lock.json').read_text());assert sha(Path(__file__).with_name('add8_shaded.py'))==lock['source_sha256']
 checks=[];rows=[];expected_names=set()
 for job in A8['jobs']:
  c,method,stem,mp,original,cache,mesh=binding(job);name=c['id']+'_'+method+'_dist_shaded';expected_names.update([name+'.png',name+'.json']);p=F8/(name+'.png');meta=json.loads(p.with_suffix('.json').read_text());im=Image.open(p);im.load();out=np.asarray(im);assert im.mode=='RGB' and im.info.get('icc_profile');assert list(im.size)==meta['size_px']==original['size_px'];assert meta['camera']==original['camera'];assert meta['mesh']==proof(mesh);assert meta['line_drawn'] is False and meta['text_in_figure'] is False
  z=loadz(cache);ids=z['face_id'];d=z['signed_result_minus_reference_m'] if method=='prior' else z['signed'];tau=z['tau'];visible=ids>=0;finite=np.isfinite(d);masks={'within_tau':visible&finite&(abs(d)<=tau),'above':visible&finite&(d>tau),'below':visible&finite&(d < -tau),'no_reference':visible&~finite};assert sum(int(x.sum()) for x in masks.values())==int(visible.sum())
  saved=loadz(W8/'pixels'/f'{name}.npz');brightness=saved['brightness'];assert brightness.shape==ids.shape;assert brightness[visible].min()>=.55-1e-7 and brightness[visible].max()<=1.;source=np.asarray(Image.open(F6/(stem+'.png')).convert('RGB'));assert np.all(source[~visible]==255) and np.all(out[~visible]==255)
  # Compare against the independently preserved original RGB, not a regenerated palette.
  expected=np.rint(source[visible].astype(float)*brightness[visible,None]).clip(0,255).astype('u1');assert np.array_equal(out[visible],expected);within=out[masks['within_tau']];assert np.array_equal(within[:,0],within[:,1]) and np.array_equal(within[:,1],within[:,2]);assert within.min()>=140 and within.max()<=255
  for k,mask in masks.items():
   assert int(mask.sum())==meta['pixel_counts'][k];assert abs(100*mask.sum()/visible.sum()-meta['pixel_percent_visible_mesh'][k])<1e-10
  for i,key in enumerate(['within_tau','above','below','no_reference'],1):assert np.array_equal(saved['category']==i,masks[key])
  assert meta['pixel_counts']['background']==int((~visible).sum());assert abs(sum(meta['pixel_percent_visible_mesh'].values())-100)<1e-10
  for src in meta['sources']:assert proof(src['path'])['sha256']==src['sha256']
  rows.append(dict(case=c['id'],method=method,image=name+'.png',visible_mesh_pixels=int(visible.sum()),background_pixels=int((~visible).sum()),**{k+'_pct':meta['pixel_percent_visible_mesh'][k] for k in masks},classifications_identical_to_original=True))
  checks.append(dict(image=name+'.png',camera_and_mesh_identical=True,original_pixel_classes_identical=True,RGB_equals_original_times_shading=True,white_background_unchanged=True,brightness_visible_min=float(brightness[visible].min()),brightness_visible_max=float(brightness[visible].max())))
 assert {p.name for p in F8.iterdir()}==expected_names
 with (T8/'pixel_proportions.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 names={'prior':'사전 정보','mvs':'MVS','FINALTRAIN_30000':'본 방법'};report=['배경을 제외한 메시가 보이는 화소 기준(%).','','|자리|면|τ 안|위|아래|참값 없음|','|---|---|---:|---:|---:|---:|']
 for row in rows:report.append('|'+row['case'].split('_')[0]+'|'+names[row['method']]+'|'+'|'.join(f"{row[k+'_pct']:.2f}" for k in ['within_tau','above','below','no_reference'])+'|')
 report+=['','7장 모두 기존 렌더와 화소 분류·비율이 정확히 같다. 저장된 거리값·카메라·크기·메시를 유지하고, 같은 카메라 방향의 음영(0.55+0.45|n·v|)만 곱했다. τ 안은 회색, 나머지는 기존 색에 같은 음영을 곱했으며 배경은 흰색이다.','기존 그림 보존. 새 카메라·단면 선·확인 그림·채점·학습 없음.','scientific_verdict: null'];(D/'보고_덧붙임8.md').write_text('\n'.join(report)+'\n')
 receipt=dict(at=now(),status='PASS_IDENTICAL_PIXEL_CLASSES_AND_REQUESTED_SHADING',checks=checks,protected_previous_figure_files=len(protected),new_shaded_renders=7,new_check_figures=0,new_cameras=0,new_distance_queries=0,training_started=False,training_interrupted=False,scientific_verdict=None);dump(D/'verification/addendum8.json',receipt)
 files=sorted(F8.iterdir())+[T8/'pixel_proportions.csv',D/'보고_덧붙임8.md'];dest=O/'delivery/PHD-MAIN-GTJUDGE-v1_음영거리렌더.zip';assert not dest.exists();members=[dict(member=str(p.relative_to(D)),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p,item in zip(files,members):z.write(p,item['member'])
  z.writestr('manifest.json',json.dumps(dict(task_id=A8['task_id'],addendum=8,config=A8,files=members,verification=receipt,scientific_verdict=None),ensure_ascii=False,indent=2))
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for item in members:assert hashlib.sha256(z.read(item['member'])).hexdigest()==item['sha256']
 dump(D/'verification/addendum8_archive.json',dict(at=now(),status='PASS_ZIP_CRC_AND_MEMBER_SHA256',path=str(dest),sha256=sha(dest),members=len(members)+1,bytes=dest.stat().st_size,scientific_verdict=None));print('ADD8_VERIFIED',len(checks),len(protected),str(dest),flush=True)

if __name__=='__main__':main()
