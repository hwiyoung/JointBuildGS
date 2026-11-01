"""Exact config, seed, source and stored camera/RNG differences; no causal conclusion."""
import json,hashlib
import numpy as np,torch
from common import *
from diagnose_als_continue_r7 import load

def flatten(v,p=''):
 if isinstance(v,dict):
  o={}
  for k,x in v.items():o.update(flatten(x,p+'.'+k if p else k))
  return o
 return {p:v}
def main():
 root=OUT/'r7_continue/diagnostics/ALS';raw=json.loads((root/'source_differences.json').read_text());a,b=[flatten(raw['configs'][f'target_v1.{r}.json']['value']) for r in ['r6','r7']];diff=[dict(field=k,r6=a.get(k),r7=b.get(k),r6_present=k in a,r7_present=k in b) for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k) or (k in a)!=(k in b)]
 ss=[load(OUT/r/'stage1/B173nb_b10_ALS/seeds.npz') for r in ['r2','r7']];seedrows=[]
 for k in sorted(set(ss[0])|set(ss[1])):
  x,y=ss[0].get(k),ss[1].get(k);same=x is not None and y is not None and x.shape==y.shape and np.array_equal(x,y,equal_nan=True);seedrows.append(dict(field=k,r6_shape=list(x.shape) if x is not None else None,r7_shape=list(y.shape) if y is not None else None,identical=bool(same)))
 sx,sy=ss;bg=[s['xyz'][s['origin']==0] for s in ss];bg_equal=bg[0].shape==bg[1].shape and np.array_equal(*bg,equal_nan=True)
 # Match prior seeds by unchanged input index and patch ID, preserving all duplicates.
 original=[s['keep_original'] for s in ss];initial_counts={r:dict(all=len(s['xyz']),prior=int((s['origin']==1).sum()),background=int((s['origin']==0).sum())) for r,s in zip(['r6','r7'],ss)}
 orders={};rngdiff=[]
 for rev in ['r6','r7']:
  cp=OUT/rev/'runs'/f'tg_B173nb_b10_ALS_s0_{rev}/model/jbgs_complete/iteration_7000/checkpoint.pth';state=torch.load(cp,map_location='cpu',weights_only=False);orders[rev]=dict(train=state['train_order'],test=state['test_order'],remaining=state['viewpoint_stack'],args_seed={k:v for k,v in state['args'].items() if 'seed' in k.lower()});del state
 camera=dict(train_order_identical=orders['r6']['train']==orders['r7']['train'],test_order_identical=orders['r6']['test']==orders['r7']['test'],remaining_stack_at7000_identical=orders['r6']['remaining']==orders['r7']['remaining'],orders=orders)
 dump(root/'changes_summary.json',dict(at=stamp(),config_differences=diff,code_differences=raw['files'],seed_fields=seedrows,seed_counts=initial_counts,background_positions_byte_equal=bool(bg_equal),camera=camera,full_iteration_camera_sequence='not saved; every-100-step camera logs and checkpoint order/stack retained',same_seed_repeat='not executed; actual resumed overlap is compared separately and is not bit-identical',scientific_verdict=None));print('CHANGES_SUMMARY',len(diff),initial_counts,bg_equal,camera['train_order_identical'],flush=True)
if __name__=='__main__':main()
