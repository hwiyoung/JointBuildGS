"""CPU audit of the actual stored Adam and mutable target state; no resume training."""
import sys
import numpy as np
import torch
from common import *
def main():
 prior=sys.argv[1];model=OUT/'r7_continue/attempt2/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model';rows=[]
 lock=json.loads((CFG/'target_v1.runtime.r7.lock.json').read_text())
 for name,digest in lock['files'].items():assert sha(REPO/name)==digest,name
 for iteration in [15000,30000]:
  root=model/'jbgs_complete'/f'iteration_{iteration}'
  if not (root/'receipt.json').exists():rows.append(dict(iteration=iteration,status='NOT_REACHED_TRAINING_STOPPED' if (model.parent/'receipt.json').exists() else 'NOT_REACHED_OR_NOT_YET_SAVED'));continue
  receipt=json.loads((root/'receipt.json').read_text());assert sha(root/'checkpoint.pth')==receipt['checkpoint_sha256']
  state=torch.load(root/'checkpoint.pth',map_location='cpu');assert state['iteration']==iteration
  assert state['args']['jbgs_target_rev']=='r7' and state['args']['jbgs_target']=='on'
  model_state=state['model'];n=len(model_state[1]);optimizer=model_state[10];assert len(optimizer['param_groups'])==6
  for group in optimizer['param_groups']:
   assert len(group['params'])==1;moment=optimizer['state'][group['params'][0]]
   assert torch.isfinite(moment['exp_avg']).all() and torch.isfinite(moment['exp_avg_sq']).all()
   assert len(moment['exp_avg'])==n and len(moment['exp_avg_sq'])==n
  target=state['target_r6'];curve=[json.loads(x) for x in (model/'target_monitor/curve.jsonl').read_text().splitlines() if json.loads(x)['iteration']<=iteration];assert target['last_opacity_reset']==curve[-1]['last_opacity_reset']
  tag=target['meta']['target_tag'];assert len(tag)==n
  assert ((tag==0)==(state['origin']==0)).all();assert ((tag==1)|(tag==2)|(tag==0)).all()
  for k,v in target['meta'].items():assert len(v)==n
  assert len(state['origin'])==len(state['init_id'])==n and target['n6000']>0
  assert set(state['rng'])=={'python','numpy','torch_cpu','torch_cuda'}
  assert len(state['train_order'])==203 and len(state['train_order'])==len(set(state['train_order']))
  assert state['viewpoint_stack'] is None or set(state['viewpoint_stack'])<=set(state['train_order'])
  for path,digest in state['implementation_hashes'].items():assert sha(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r21'/path)==digest
  rows.append(dict(iteration=iteration,status='PASS_COMPLETE_STATE',gaussians=n,adam_parameter_groups=len(optimizer['param_groups']),
   adam_steps={g['name']:float(optimizer['state'][g['params'][0]]['step']) for g in optimizer['param_groups']},
   checkpoint_sha256=receipt['checkpoint_sha256'],tags={str(i):int((tag==i).sum()) for i in range(3)}))
 result=dict(at=stamp(),status='PASS_R7_COMPLETE_STATE_AUDIT',prior=prior,rows=rows,scientific_verdict=None)
 dump(model.parent/'verification_full_state.json',result);dump(DOC/'tables'/f'continue_r7_full_state_{prior}.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
