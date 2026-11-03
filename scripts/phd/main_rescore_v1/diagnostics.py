"""Select required comparisons from completed scores; no causal interpretation."""
import sys
from common import *
def main(site):
 cfg();jobs=[];rows=[]
 for prior in ['ALS','LoD2']:
  base=O/'scores'/f'{site}__{prior}__baseline_30000/values.json'
  if not base.exists():continue
  b=json.loads(base.read_text());bc=next(r['completeness'] for r in b['cells'] if r['cell']==0)
  for family in ['GeoGS','2DGS','CDGS']:
   key=f'{site}__{prior}__{family}_30000';p=O/'scores'/key/'values.json'
   if not p.exists():continue
   v=json.loads(p.read_text());c=next(r['completeness'] for r in v['cells'] if r['cell']==0);delta=bc-c;trigger=delta>.30
   rows.append(dict(key=key,baseline=bc,completeness=c,baseline_minus_method_pp=100*delta,threshold_pp=30,trigger=trigger,source=str(p),source_tag='[이 발주에서 냄]'))
   if trigger:jobs.append(dict(site=site,prior=prior,key=key,mesh=str(O/'meshes'/key/'train.ply'),score_key=key+'__train',render_key=f'{site}__LoD2__2DGS_30000' if family=='2DGS' else key))
 dump(O/'diagnostics'/f'{site}_jobs.json',dict(jobs=jobs,scientific_verdict=None));table('low_cell0_'+site,rows)
if __name__=='__main__':main(sys.argv[1])
