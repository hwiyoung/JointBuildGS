"""CPU-only proof: only the count stop changes; other health failures still raise."""
import sys,importlib.util,copy
sys.path.insert(0,'/source')
import torch
from types import SimpleNamespace
from common import *
ROOT=OUT/'rfix_continue/attempt2'
def main():
 import jbgs_target_r8
 p=ROOT/'runtime/count_override.py';spec=importlib.util.spec_from_file_location('rfix_count_override',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 for name in ['memory_allocated','memory_reserved','max_memory_allocated','max_memory_reserved']:setattr(torch.cuda,name,lambda:0)
 torch.cuda.mem_get_info=lambda:(10**9,2*10**9)
 dest=ROOT/'tests_r2';dest.mkdir(exist_ok=False);rows=[]
 for case in ['count','low_opacity','nan_position','nan_loss','normal_excess']:
  for version,cls in [('original',jbgs_target_r8.TargetR8),('exception',m.TargetR8)]:
   mon=dest/(case+'_'+version);mon.mkdir();g=SimpleNamespace(_xyz=torch.zeros(6,3),origin=torch.ones(6,dtype=torch.int64),target_tag=torch.zeros(6,dtype=torch.int64),target_index=torch.zeros(6,dtype=torch.int64),get_opacity=torch.full((6,1),.5));loss=torch.tensor(.1)
   control=SimpleNamespace(mon=mon,n6000=1,opacity_grace=lambda i:False,patch_anchor=torch.zeros(1,3),patch_normal=torch.tensor([[0.,0.,1.]]),patch_sigma=torch.tensor([.01]))
   if case=='low_opacity':g.get_opacity[:]=.01
   if case=='nan_position':g._xyz[0,0]=float('nan')
   if case=='nan_loss':loss.fill_(float('nan'))
   if case=='normal_excess':g.target_tag[:]=1;g._xyz[:,2]=.1
   got=None
   try:cls.observe(control,16000,g,loss,torch.tensor(.1),torch.tensor(.1),'synthetic')
   except RuntimeError as e:got=str(e)
   expected={'count':None if version=='exception' else 'TARGET_STOP_count_gt_3x_6000','low_opacity':'TARGET_STOP_prior_seed_lineage_opacity_median_below_0.05','nan_position':'TARGET_STOP_nonfinite_position_or_loss','nan_loss':'TARGET_STOP_nonfinite_position_or_loss','normal_excess':'TARGET_STOP_normal_bound_violation'}[case]
   assert got==expected,(case,version,got,expected);rows.append(dict(case=case,version=version,error=got,pass_=True))
 dump(dest/'result.json',dict(at=stamp(),status='PASS',rows=rows,source_sha256=sha(p),optimization_steps=0,scientific_verdict=None));receipt=json.loads((dest/'result.json').read_text());receipt['test_script_sha256']=sha(__file__);receipt['test_harness_revision']='r2: scalar NaN injection only';dump(ROOT/'tests/result.json',receipt);print('COUNT_EXCEPTION_UNIT_PASS')
if __name__=='__main__':main()
