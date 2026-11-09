"""Section 2 CPU-only schema, provenance and schedule audit. No optimizer."""
from common import *
import torch, gc
rows=[];hashes={}
cfg()
def metadata_json(v):
 if isinstance(v,dict):return {k:metadata_json(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [metadata_json(x) for x in v]
 if isinstance(v,float) and not np.isfinite(v):return 'NaN' if np.isnan(v) else str(v)
 return v
for it in [7000,15000,30000]:
 p=MODEL/f'jbgs_complete/iteration_{it}/checkpoint.pth'
 if not p.exists():
  issue(f'STOP_SECTION2: {it} checkpoint absent');raise RuntimeError('STOP_SECTION2')
 s=torch.load(p,map_location='cpu',weights_only=False);m=s['model'];meta=s['target_r6']['meta'];n=len(m[1])
 for k in ['init_id','origin']:
  if s[k] is None or len(s[k])!=n:issue(f'STOP_SECTION2: {it} {k} absent');raise RuntimeError('STOP_SECTION2')
 expected=json.loads(p.with_name('receipt.json').read_text());h=sha(p);assert h==expected['checkpoint_sha256'];hashes[str(p)]=h
 rows.append(dict(iteration=it,path=str(p),sha256=h,gaussians=n,centre='model[1]',rotation='model[5] wxyz',scale='exp(model[4]) tangent axes',opacity='sigmoid(model[6])',origin='origin',init_id='init_id',current_patch='target_r6.meta.target_index -> target patch valid index',target_tag='target_r6.meta.target_tag',last_opacity_reset=s['target_r6']['last_opacity_reset']))
 if it==7000:
  dump(O/'work/saved_parameters.json',metadata_json(dict(args=s['args'],optimization=s['optimization'],source_sha256=s['source_sha256'],implementation_hashes=s['implementation_hashes'])))
 # Extract only required fields; later building slicing remains CPU-only.
 savez(O/'work'/f'state_{it}.npz',xyz=m[1].detach().numpy(),rotation=torch.nn.functional.normalize(m[5].detach(),dim=1).numpy(),scale=torch.exp(m[4].detach()).numpy(),opacity=torch.sigmoid(m[6].detach()).numpy().ravel(),origin=s['origin'].numpy(),init_id=s['init_id'].numpy(),**{k:v.numpy() for k,v in meta.items()})
 del s,m,meta;gc.collect();print('CHECKPOINT_OK',it,n,flush=True)
dump(D/'section2_checkpoints.json',dict(rows=rows,hashes=hashes,scientific_verdict=None));table('section2_checkpoints',rows)
