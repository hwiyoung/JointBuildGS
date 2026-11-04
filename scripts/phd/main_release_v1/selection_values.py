"""Section 6.5 only; old cells with at least 1000 reference points."""
from common import *
def main():
 rows=[]
 for rule in ['pull','delete','mix']:
  values=[];deltas=[];available=True
  for prior in ['ALS','LoD2']:
   key=f'R1rep_b10__{prior}__rl_{rule}_{prior}_s0';p=O/'scores'/key/'values.json'
   if not p.exists():available=False;continue
   v=json.loads(p.read_text());base=json.loads((score_dir('R1rep_b10',prior,'FINALTRAIN_30000')/'values.json').read_text());values.extend(r['completeness'] for r in v['cells'] if r['cell'] in [0,1,2,4] and r['n_gt']>=1000);deltas.append(dict(prior=prior,accuracy_delta_pp=100*(v['scene']['accuracy']-base['scene']['accuracy'])))
  rows.append(dict(rule=rule,available=available,eligible_cells=len(values),minimum_completeness=min(values) if available and values else None,mean_completeness=float(np.mean(values)) if available and values else None,accuracy_deltas=deltas,accuracy_guard_pass=available and all(r['accuracy_delta_pp']>=-3 for r in deltas)))
 complete=[r for r in rows if r['available'] and r['minimum_completeness'] is not None];passed=[r for r in complete if r['accuracy_guard_pass']];pool=passed or complete;selected=None
 if pool:
  best=max(r['minimum_completeness'] for r in pool);tie=[r for r in pool if best-r['minimum_completeness']<=.005+1e-12];selected=max(tie,key=lambda r:r['mean_completeness'])['rule']
 dump(D/'단계3_고른규칙.json',dict(at=now(),selected_rule=selected,cell_basis='original',n_gt_min=1000,tie_band_pp=.5,accuracy_guard_pp=3,all_accuracy_guards_failed=bool(complete) and not passed,results=rows,scientific_verdict=None))
if __name__=='__main__':main()
