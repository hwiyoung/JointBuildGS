"""CPU checkpoint, schedule and provenance audit; no model changes."""
import math,torch,numpy as np
from common import *
ROOT=OUT/'rfix_continue'
def equal(a,b):
 if torch.is_tensor(a):return torch.is_tensor(b) and a.shape==b.shape and a.dtype==b.dtype and torch.equal(a,b)
 if isinstance(a,np.ndarray):return isinstance(b,np.ndarray) and a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
 if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
 if isinstance(a,(list,tuple)):return type(a)==type(b) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 if isinstance(a,float) and math.isnan(a):return isinstance(b,float) and math.isnan(b)
 return a==b
def main():
 cfg=json.loads((CFG/'rfix_continue.json').read_text());ep=json.loads((CFG/'rfix_endpoint.json').read_text());lock=json.loads((CFG/'rfix_continue.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 checkpoint=Path(ep['state']['checkpoint']);state=torch.load(checkpoint,map_location='cpu');it=ep['state']['iteration'];assert state['iteration']==it and state['model'][10]['state'];n=len(state['model'][1]);assert n==len(state['init_id']);model=ROOT/'runs/r8_LoD2_rfix/model';other=model/f'jbgs_complete/iteration_{it}/checkpoint.pth';fields=[]
 if other.exists() and other!=checkpoint:
  scheduled=torch.load(other,map_location='cpu')
  for key in ['model','origin','init_id','target_r6','rng','viewpoint_stack','train_order','test_order','optimization','implementation_hashes']:
   assert equal(state[key],scheduled[key]),key;fields.append(key)
  del scheduled
 assert state['target_r6']['n6000']==cfg['count_at_6000']
 h=json.loads((ROOT/'acceptance_amendment.json').read_text());assert all(r['pass_relative_l2'] for r in h['reassessment']);assert not (ROOT/'STOP_REQUEST.json').exists()
 records=[json.loads(l) for l in (model/'recording/rfix_100.jsonl').read_text().splitlines()];counts=[json.loads(l) for l in (model/'recording/after_iteration_100.jsonl').read_text().splitlines()];expected=list(range(14100,it+1,100));assert [r['iteration'] for r in records]==expected;assert [r['iteration'] for r in counts]==expected
 for r in counts:assert int(np.asarray(r['counts']).sum())+r['invalid_position_count']==r['gaussians']
 first=next(v for v in records[0]['view_maxima'] if v['iteration']==14031);assert first['camera']=='DJI_20241217102535_0020_D' and first['overlaps']==1986099 and first['binning_bytes']==72047487
 assert not any(v['binning_bytes']>.5*v['free_bytes'] for r in records for v in r['view_maxima'])
 result=dict(at=stamp(),status='PASS',iteration=it,gaussians=n,count_at6000=state['target_r6']['n6000'],count_multiple=n/state['target_r6']['n6000'],checkpoint_sha256=sha(checkpoint),original_checkpoint_preserved=True,optimizer_present=True,scheduled_vs_stop_exact_fields=fields,first_forward=first,recorded_100_iterations=expected,original_training_method_hashes=state['implementation_hashes'],scientific_verdict=None)
 dump(ROOT/'validation/checkpoint_and_recording.json',result);print('CHECKPOINT_RECORDING_PASS',it,n)
if __name__=='__main__':main()
