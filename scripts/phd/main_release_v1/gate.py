"""Prespecified section 5; original cells only."""
from common import *
def main():
 rows=json.loads((D/'tables/stage1/R1rep_b10__ALS_attribution.json').read_text())['rows'];evidence=[]
 for cell in [2,4]:
  counts={label:sum(r['n_gt'] for r in rows if r['cell_basis']=='original' and r['cell']==cell and r['judgment_region']==-1 and r['result_type'] in [1,2,3] and r['binding']==label) for label in range(5)}
  evidence.append(dict(cell=cell,counts=counts,released_largest=counts[2]>max(v for k,v in counts.items() if k!=2),tie_policy='strictly more than every other label, including unavailable'))
 condition1=any(r['released_largest'] for r in evidence);simulation=[]
 for sim in ['delete_released','pull_released']:
  p=O/'scores'/f'R1rep_b10__ALS__sim_{sim}'/'values.json'
  if p.exists():
   z=json.loads(p.read_text());v=json.loads((score_dir('R1rep_b10','ALS','FINALTRAIN_30000')/'values.json').read_text())
   for cell in [2,4]:
    a=next(r for r in z['cells'] if r['cell']==cell);b=next(r for r in v['cells'] if r['cell']==cell);delta=100*(a['completeness']-b['completeness']);simulation.append(dict(simulation=sim,cell=cell,improvement_pp=delta,above_10pp=delta>10))
 condition2=any(r['above_10pp'] for r in simulation)
 if not condition1 and len(simulation)<4:
  dump(O/'stage1/gate_pending.json',dict(condition1=condition1,evidence=evidence,reason='wait for both simulations',scientific_verdict=None));print('GATE_PENDING_SIMULATIONS');return
 assert not (D/'단계3_판정.json').exists()
 dump(D/'단계3_판정.json',dict(at=now(),stage3_authorized=condition1 or condition2,cell_basis='original',condition1=condition1,condition1_evidence=evidence,condition2=condition2 if len(simulation)==4 else None,condition2_evidence=simulation,condition2_status='not needed for OR gate' if condition1 and len(simulation)<4 else 'complete',source_sha256=sha(D/'tables/stage1/R1rep_b10__ALS_attribution.json'),scientific_verdict=None))
 print('GATE',condition1 or condition2)
if __name__=='__main__':main()
