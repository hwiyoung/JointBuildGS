"""Lock the renderer-only task before model measurements; preserve all prior work."""
import sys,subprocess,datetime,shutil
from r8_screen_prepare import R,A,PH,O,C,j,sha,local,docker,dump
ROOT=O/'rfix'
def main():
 ROOT.mkdir(exist_ok=False);(ROOT/'inventory').mkdir()
 old=j(C/'screen_sim.json');states=old['states'];bindings=[]
 for r in states:
  summary=j(O/'screen_sim/states'/r['key']/'before/summary.json')
  top=[x['camera'] for x in sorted(summary['views'],key=lambda x:(-x['overlaps'],x['camera']))[:5]]
  chosen=list(dict.fromkeys(top+['DJI_20241217102535_0020_D','DJI_20241217091133_0109_D']))
  chosen+= [n for n in old['views'] if n not in chosen][:30-len(chosen)]
  r['gradient_views']=chosen;r['original_top5']=top
 config=dict(task_id='PHD-MAIN-TARGET-v1',at=datetime.datetime.now().astimezone().isoformat(),authority='2026-11-03 10:40 renderer box correction order v1',states=states,views=old['views'],comparison=dict(forward='all eight states x203 views; original A, original B, fixed; every raw float output map, derived maps, radii',backward='same training loss at saved iteration, all six Gaussian parameters and retained screen-position gradient;30 locked views each state',gate='for each view and output/parameter: max_abs(original_A-fixed) <= max_abs(original_A-original_B), no added tolerance; finite/nonfinite masks identical; radii byte identical; total overlaps strictly decrease each state',jitter='two original forwards/backwards with identical model and loss, no optimizer',on_failure='save differing view/row details; no training; report failed gate; do not relax criterion'),fix=dict(method='keep original preprocess/radii and pixel math; exact per-tile potential alpha/depth predicate before scan and duplication, outward-rounded interval rejection then original pixel predicate on uncertain tiles',potential='exists in-image integer pixel in original native tile rectangle with original depth >=near and alpha >=1/255, irrespective of transmittance; no new pixel/tile support added',screen_cleanup='unchanged and five prior simulation patches unapplied'),training=dict(label='r8_LoD2_rfix',source='/repo/src/phd/forks/GeoGS-conf-guided-v1-r22',checkpoint=j(O/'r8_recorded_continue/STOP_LoD2.json')['stop_dir']+'/checkpoint.pth',expected_completed_iteration=14030,stop_iteration=30000,save_every=1000,save_required=[15000,30000],record_every=100,guard_fraction=.5,automatic_retry=False,health='r8 unchanged including n6000 factor3 and opacity grace',other_six='NOT_STARTED'),figures=old['figures'],boundaries=old['boundaries'],roi='/out/screen_sim/inputs/index.json',scoring=old['scoring'],mesh=old['mesh'],scientific_verdict=None)
 cfg=C/'rfix.json';assert not cfg.exists();dump(cfg,config)
 files={str(cfg):sha(cfg),str(C/'screen_sim.json'):sha(C/'screen_sim.json'),str(local(config['training']['checkpoint'])):sha(local(config['training']['checkpoint']))}
 for r in states:
  for k in ['ply','checkpoint','snapshot']:
   if r.get(k):files[str(local(r[k]))]=sha(local(r[k]))
 # Existing immutable input locks retained wholesale; actual GeoGS text cameras additionally locked now.
 for name in ['screen_sim.lock.json','screen_sim_render.lock.json','screen_sim_render_r3.lock.json']:
  p=C/name
  if p.exists():
   for path,h in j(p)['files'].items():
    q=local(path);assert sha(q)==h,str(q);files[str(q)]=h
 for r in states:
  for p in local(r['scene']).glob('sparse_lod/0/*.txt'):files[str(p)]=sha(p)
 order=__import__('pathlib').Path('/home/innopam/.codex/attachments/1d511c94-e9f9-4fa4-8b22-2bc82627c2fb/붙여넣은 텍스트.txt')
 shutil.copyfile(order,ROOT/'order_v1.txt');files[str(ROOT/'order_v1.txt')]=sha(ROOT/'order_v1.txt')
 dump(C/'rfix.lock.json',dict(at=config['at'],config_sha256=sha(cfg),files=files,scientific_verdict=None));print('LOCKED',len(files),sha(cfg),flush=True)
 # Extract build provenance, without calculations on model data.
 seen={}
 for row in states:
  image=row['image_id']
  if image in seen:continue
  label={'r8':'target','r7':'target','r6':'target','baseline':'target','image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target');seen[image]=label
  code="""import pathlib,shutil,hashlib,json,sys,torch
import diff_surfel_rasterization as r
root=pathlib.Path('/inv');srcs=list(pathlib.Path('/opt').glob('**/diff-surfel-rasterization/cuda_rasterizer/forward.cu'))
assert srcs, 'renderer source absent'
src=srcs[0].parents[1];dst=root/'source';shutil.copytree(src,dst,ignore=shutil.ignore_patterns('build','*.so','__pycache__','.git'))
h=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
json.dump(dict(source=str(src),candidates=list(map(str,srcs)),extension=r._C.__file__,extension_sha256=h(r._C.__file__),torch=torch.__version__,cuda=torch.version.cuda,source_files={str(p.relative_to(dst)):h(p) for p in dst.rglob('*') if p.is_file()}),open(root/'manifest.json','w'),indent=2)
"""
  dest=ROOT/'inventory'/label;dest.mkdir()
  cmd=['docker','run','--rm','--read-only','--network','none','--user',f'{__import__("os").getuid()}:{__import__("os").getgid()}','-e','PYTHONDONTWRITEBYTECODE=1','-e','LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6','-v',f'{dest}:/inv:rw','--entrypoint','python',image,'-B','-c',code]
  result=subprocess.run(cmd,text=True,capture_output=True);(dest/'extract.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
  bindings.append(dict(label=label,image_id=image,**j(dest/'manifest.json')))
 dump(ROOT/'inventory/builds.json',bindings)
if __name__=='__main__':main()
