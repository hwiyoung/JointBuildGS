"""Compare actual resumed trajectory with the already-stored pre-stop trajectory."""
import torch,numpy as np
from common import *
def digest_obj(x):
 import hashlib,pickle
 if isinstance(x,torch.Tensor):return dict(dtype=str(x.dtype),shape=list(x.shape),sha256=hashlib.sha256(x.cpu().numpy().tobytes()).hexdigest())
 if isinstance(x,np.ndarray):return dict(dtype=str(x.dtype),shape=list(x.shape),sha256=hashlib.sha256(x.tobytes()).hexdigest())
 if isinstance(x,dict):return {str(k):digest_obj(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [digest_obj(v) for v in x]
 return x

def main():
 out=OUT/'r7_continue/diagnostics';out.mkdir(exist_ok=True);rng={}
 for rev in ['r6','r7']:
  p=OUT/rev/'runs'/f'tg_B173nb_b10_ALS_s0_{rev}/model/jbgs_complete/iteration_7000/checkpoint.pth';state=torch.load(p,map_location='cpu',weights_only=False)
  keys=[k for k in state if any(s in k.lower() for s in ['rng','camera','stack','iteration'])];rng[rev]=dict(checkpoint_sha256=sha(p),keys=list(state),saved={k:digest_obj(state[k]) for k in keys},seed_args={k:v for k,v in state['args'].items() if 'seed' in k.lower()});del state
 comparisons=[]
 for prior in ['ALS','LoD2']:
  old=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model';new=OUT/'r7_continue/attempt2/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model';restore=json.loads((new/'jbgs_restore.json').read_text());assert restore['iteration']==7000 and all(restore[k] for k in ['target_state','optimizer_state','rng_and_camera_state'])
  load=lambda p:{r['iteration']:r for r in [json.loads(s) for s in p.read_text().splitlines()]};a,b=load(old/'target_monitor/curve.jsonl'),load(new/'target_monitor/curve.jsonl');common=sorted(set(a)&set(b));assert all(i>7000 for i in common);rows=[]
  for i in common:
   keys=sorted(set(a[i])|set(b[i]));different=[k for k in keys if a[i].get(k)!=b[i].get(k)];rows.append(dict(iteration=i,byte_equivalent_logged_fields=not different,different_fields=different,camera_equal=a[i]['camera']==b[i]['camera'],count_equal=a[i]['gaussians']==b[i]['gaussians'],loss_abs_delta=abs(a[i]['loss']-b[i]['loss'])))
  comparisons.append(dict(prior=prior,restore=restore,rows=rows,full_model_byte_replay='not checked: original trajectory has no matching complete state after 7000',same_seed_fresh_training='not performed; no guarantee inferred from resume'))
 dump(out/'resume_and_rng.json',dict(at=stamp(),rng=rng,comparisons=comparisons,scientific_verdict=None));print('RESUME_AUDIT',[(r['prior'],len(r['rows']),sum(v['byte_equivalent_logged_fields'] for v in r['rows'])) for r in comparisons],flush=True)
if __name__=='__main__':main()
