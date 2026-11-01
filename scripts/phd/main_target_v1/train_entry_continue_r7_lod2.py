"""Resume the frozen r21 state under the explicit 2026-11-01 21:15 decision."""
import runpy,sys
from common import *
def main():
 c=json.loads((CFG/'continue_r7.lod2_r2.json').read_text());lock=json.loads((CFG/'continue_r7.lod2_r2.lock.json').read_text())
 assert sha(CFG/'continue_r7.lod2_r2.json')==lock['config_sha256']
 for name,h in lock['files'].items():assert sha(REPO/name)==h,name
 old=json.loads((CFG/'target_v1.runtime.r7.lock.json').read_text())
 assert sha(CFG/'target_v1.r7.json')==old['config_sha256']
 for name,h in old['files'].items():assert sha(REPO/name)==h,name
 site,prior=sys.argv[1:3];assert site=='B173nb_b10' and prior in c['priors']
 row=c['runs'][prior];checkpoint=Path(sys.argv[sys.argv.index('--jbgs_resume_full')+1]);assert sha(checkpoint)==row['checkpoint_sha256']
 assert not (OUT/'r7_continue/lod2_retry/STOP_BOTH.json').exists()
 root=OUT/'r7/stage1'/f'{site}_{prior}';seed=json.loads((root/'seed_receipt.json').read_text());assert sha(root/'seeds.npz')==seed['seeds_sha256']
 ix=json.loads((root/'maps/index.json').read_text());assert sha(OUT/'r7/targets'/f'{site}_{prior}.npz')==ix['target_sha256']
 for meta in ix['views'].values():assert sha(root/'maps'/meta['file'])==meta['sha256']
 assert json.loads((OUT/'r7/runs'/row['name']/'verification_full_state.json').read_text())['rows'][0]['status']=='PASS_COMPLETE_STATE'
 model=Path(sys.argv[sys.argv.index('-m')+1]);assert model==OUT/'r7_continue/lod2_retry/runs'/row['name']/'model';model.mkdir(parents=True,exist_ok=False)
 dump(model.parent/'input_binding.json',dict(at=stamp(),config_sha256=lock['config_sha256'],checkpoint_sha256=row['checkpoint_sha256'],seed_sha256=seed['seeds_sha256'],maps_index_sha256=sha(root/'maps/index.json'),source_runtime_lock_sha256=sha(CFG/'target_v1.runtime.r7.lock.json'),scientific_verdict=None))
 sys.path.insert(0,'/source')
 # The original checkpoint and live args retain NaN defaults. Only the comparison
 # view excludes pairs independently verified to be the same unspecified value.
 import math,jbgs_target_r6
 original=jbgs_target_r6.restore_complete
 def restore_equal_unspecified(path,state,env):
  saved=state['args'];current=vars(env['args']);keys=[]
  for k,v in saved.items():
   x=current.get(k)
   if isinstance(v,float) and isinstance(x,float) and math.isnan(v) and math.isnan(x):keys.append(k)
  assert set(keys)<=set(['jbgs_tau_v','jbgs_tau_roof','jbgs_tau_wall'])
  view=dict(state);view['args']={k:v for k,v in saved.items() if k not in keys}
  result=original(path,view,env)
  dump(Path(env['args'].model_path)/'restore_comparison_compatibility.json',dict(at=stamp(),equal_unspecified_keys=keys,original_checkpoint_sha256=sha(path),only_argument_comparison_view_changed=True,optimizer_rng_camera_and_method_unchanged=True,scientific_verdict=None))
  return result
 jbgs_target_r6.restore_complete=restore_equal_unspecified
 # Observation-only hook; no resets, random draws, or optimizer changes.
 import torch,jbgs_target_r7
 observe=jbgs_target_r7.TargetR7.observe
 def observe_memory(self,iteration,g,*a,**kw):
  result=observe(self,iteration,g,*a,**kw)
  if iteration%1000==0:
   row=dict(iteration=iteration,gaussians=len(g.get_xyz),tags={str(i):int((g.target_tag==i).sum()) for i in range(3)},cuda_allocated_bytes=torch.cuda.memory_allocated(),cuda_reserved_bytes=torch.cuda.memory_reserved(),peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),at=stamp(),scientific_verdict=None)
   with (Path(self.mon)/'memory_1000.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  return result
 jbgs_target_r7.TargetR7.observe=observe_memory
 sys.argv=['/source/train.py']+sys.argv[3:];runpy.run_path('/source/train.py',run_name='__main__')
if __name__=='__main__':main()
