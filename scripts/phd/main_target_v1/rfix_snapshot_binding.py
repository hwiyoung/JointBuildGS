"""Bind endpoint PLY rows to full-state metadata without relaxing coordinate equality."""
import numpy as np,torch
from common import *
def main():
 cfg=json.loads((CFG/'rfix_snapshot_binding.json').read_text())
 for p,h in json.loads((CFG/'rfix_snapshot_binding.lock.json').read_text())['files'].items():assert sha(p)==h,p
 row=json.loads((CFG/'rfix_final.json').read_text())['state'];cp=torch.load(row['checkpoint'],map_location='cpu');s=np.load(row['snapshot']);g=np.load(OUT/'rfix_continue/final_endpoint/gaussians.npz');xyz=cp['model'][1].numpy();assert np.array_equal(xyz,g['xyz'])
 checks={}
 for name in ['origin','init_id']:
  checks[name]=bool(np.array_equal(cp[name].numpy(),s[name]));assert checks[name],name
 for name,value in cp['target_r6']['meta'].items():
  checks[name]=bool(np.array_equal(value.numpy(),s[name]));assert checks[name],name
 old=s['xyz'];delta=xyz.astype('f8')-old;changed=np.any(delta!=0,axis=1);tag=cp['target_r6']['meta']['target_tag'].numpy()
 # Only the final projection between diagnostic snapshot and complete capture can
 # move rows here; density control is off, and all row IDs and metadata match.
 assert np.array_equal(xyz[tag!=1],old[tag!=1])
 assert cp['iteration']==30000 and len(xyz)==6178972
 dest=OUT/'rfix_continue/validation';dest.mkdir(exist_ok=True)
 np.savez_compressed(dest/'complete_metadata_30000.npz',target_tag=tag)
 result=dict(at=stamp(),status='PASS_EXACT_CHECKPOINT_PLY_ROW_BINDING',gaussians=len(xyz),checkpoint_render_xyz_byte_equal=True,metadata_equal=checks,snapshot_changed_rows=int(changed.sum()),snapshot_max_abs_m=float(np.max(abs(delta))),snapshot_max_norm_m=float(np.linalg.norm(delta,axis=1).max()),changed_by_tag={str(t):int((changed&(tag==t)).sum()) for t in [0,1,2]},authority='complete checkpoint and its PLY; diagnostic snapshot retained unchanged',code_order='r22 train.py:1165 snapshot;1314 project_bounds;1317 after_step complete capture',files=json.loads((CFG/'rfix_snapshot_binding.lock.json').read_text())['files'],scientific_verdict=None)
 dump(dest/'snapshot_binding_30000.json',result);print('SNAPSHOT_BINDING_PASS',result['snapshot_changed_rows'],result['snapshot_max_abs_m'])
if __name__=='__main__':main()
