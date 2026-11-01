"""Verify camera/depth provenance and independently aggregate baseline stratum counts."""
import numpy as np
from common import *
from diagnose_als_continue_r7 import load

def main():
 rows=[]
 for prior in ['ALS','LoD2']:
  root=OUT/'r5/baselines'/f'depth_{prior}';old=json.loads((root/'coverage.json').read_text());now=json.loads((OUT/'r7_continue/post'/f'base_{prior}_30000/coverage.json').read_text());oldix=json.loads((OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps/index.json').read_text());newix=json.loads((OUT/'r7/stage1'/f'B173nb_b10_{prior}/maps/index.json').read_text());assert set(oldix['views'])==set(newix['views'])=={r['camera'] for r in old['views'][prior]}=={r['camera'] for r in now['views']};bind=json.loads((root/'binding.json').read_text());ply=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{prior}_s0/model/point_cloud/iteration_30000/point_cloud.ply';assert sha(ply)==old['model_sha256']==bind[str(ply)];comparisons=[]
  for name,m in newix['views'].items():
   a=oldix['views'][name]
   for k in ['K','W2C']:assert np.array_equal(np.asarray(a[k]),np.asarray(m[k])),(name,k)
   comparisons.append(name)
  s=now['strata'];assert s['all']['inside']==sum(r['inside'] for r in now['views']);assert s['all']['target_pixels']==sum(r['target_pixels'] for r in now['views']);assert s['all']['missing']==sum(r['missing'] for r in now['views'])
  for field in ['target_pixels','inside','missing']:
   assert s['prior'][field]==s['prior_roof'][field]+s['prior_wall'][field]
   assert s['prior'][field]==s['prior_original'][field]+s['prior_replaced'][field]
   assert s['prior'][field]==sum(s['region_'+str(i)][field] for i in [0,5,1,2,3])
  for r in s.values():assert r['inside']+r['missing']<=r['target_pixels']
  rows.append(dict(prior=prior,cameras=len(comparisons),W2C_and_K_exact=True,model_sha256=old['model_sha256'],stratum_partition_conservation=True,coverage_sha256=sha(OUT/'r7_continue/post'/f'base_{prior}_30000/coverage.json')))
 result=dict(at=stamp(),status='PASS_BASELINE_CAMERA_LINEAGE_AND_PARTITIONS',rows=rows,scientific_verdict=None);dump(OUT/'r7_continue/post/baseline_coverage_verification.json',result);dump(DOC/'tables/continue_r7_baseline_coverage_verification.json',result);print('BASELINE_CAMERA_LINEAGE_PASS',flush=True)
if __name__=='__main__':main()
