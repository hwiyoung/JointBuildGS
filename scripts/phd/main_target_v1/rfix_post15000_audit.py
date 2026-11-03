"""Verify complete saves, unchanged method settings and the recorded exception after15000."""
import math,random,gc
import numpy as np
import torch
from common import *
ROOT=OUT/'rfix_continue';RUN=ROOT/'attempt2';MODEL=RUN/'runs/r8_LoD2_rfix/model'
def same(a,b):
 if torch.is_tensor(a):return torch.is_tensor(b) and torch.equal(a,b)
 if isinstance(a,np.ndarray):return isinstance(b,np.ndarray) and a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
 if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
 if isinstance(a,(tuple,list)):return type(a)==type(b) and len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
 if isinstance(a,float) and math.isnan(a):return isinstance(b,float) and math.isnan(b)
 return a==b
def jl(p):return [json.loads(l) for l in p.read_text().splitlines()]
def main():
 assert (RUN/'TRAINING_COMPLETE.json').exists()
 cfg=json.loads((CFG/'rfix_finish.json').read_text());rows=jl(MODEL/'recording/rfix_100.jsonl');counts=jl(MODEL/'recording/after_iteration_100.jsonl');forward=jl(MODEL/'recording/forward_100.jsonl');expected=list(range(15100,30001,100))
 for seq in [rows,counts,forward]:assert [r['iteration'] for r in seq]==expected
 for r in counts:assert np.asarray(r['counts']).sum()+r['invalid_position_count']==r['gaussians'] and r['invalid_position_count']==0
 assert all(r['gaussians']==6178972 for r in counts)
 for r in forward:assert np.asarray(r['overlaps_by_cell']).sum()==r['overlaps'] and r['binning_bytes']<=r['guard_limit_bytes']
 receipts=[];verified_files={}
 for it in range(16000,30001,1000):
  d=MODEL/f'jbgs_complete/iteration_{it}';p=d/'receipt.json';v=json.loads(p.read_text());assert v['iteration']==it and v['gaussians']==6178972
  for file,key in [('checkpoint.pth','checkpoint_sha256'),('point_cloud.ply','ply_sha256')]:
   p=d/file;assert sha(p)==v[key],str(p);stat=p.stat();verified_files[str(p)]=dict(sha256=v[key],bytes=stat.st_size,mtime_ns=stat.st_mtime_ns)
  receipts.append(dict(iteration=it,path=str(d),**{k:v[k] for k in ['gaussians','checkpoint_sha256','ply_sha256']}))
 old=torch.load(cfg['checkpoint'],map_location='cpu');final=torch.load(MODEL/'jbgs_complete/iteration_30000/checkpoint.pth',map_location='cpu')
 assert old['target_r6']['n6000']==final['target_r6']['n6000']==cfg['count_at_6000']
 for key in ['optimization','implementation_hashes','source_sha256','train_order','test_order','origin','init_id']:assert same(old[key],final[key]),key
 assert final['iteration']==30000 and final['model'][10]['state'] and final['rfix_health_override']['disabled_check']=='count_gt_3x_6000'
 allowed={'model_path','save_iterations','jbgs_capture_iterations','jbgs_resume_full'};diff=[k for k,v in old['args'].items() if not same(v,final['args'][k])];assert set(diff)<=allowed,diff
 rng=random.Random();rng.setstate(old['rng']['python']);stack=list(old['viewpoint_stack'] or old['train_order']);first=stack.pop(rng.randint(0,len(stack)-1));actual=next((v for v in rows[0]['view_maxima'] if v['iteration']==15001),None)
 if actual is not None:assert actual['camera']==first,(first,actual)
 override=final['rfix_health_override'];del old,final;gc.collect()
 for p,h in json.loads((CFG/'rfix_finish.lock.json').read_text())['files'].items():assert sha(p)==h,p
 dump(ROOT/'validation/post15000.json',dict(at=stamp(),status='PASS',completed_iteration=30000,count_all_100_records=6178972,recorded_100_intervals=len(rows),checkpoints=receipts,verified_files=verified_files,first_resumed_camera=actual,first_resumed_camera_from_rng=first,first_camera_unavailable_reason=None if actual else '100-iteration per-camera maximum record may replace the first occurrence',count_override=override,allowed_argument_changes=diff,method_settings_unchanged=True,optimizer_present=True,scientific_verdict=None));print('POST15000_AUDIT_PASS')
if __name__=='__main__':main()
