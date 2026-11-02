"""Independent rank-sum check by partition plus exported-row and provenance checks."""
import csv,gzip,math
import numpy as np
from common import *
ROOT=OUT/'r8_recorded_continue';H=ROOT/'heavy'
def read(p):return json.loads(Path(p).read_text())
def main():
 c=read(CFG/'r8_heavy.json');summary=read(H/'tables/top_summary.json')['rows'];checked=[]
 for state in c['rows']:
  d=H/'states'/state['key'];a=dict(np.load(d/'arrays.npz'))
  for name in state['cameras']:
   with np.load(d/(name+'.npz')) as v:tiles=v['tiles'].astype('i8').copy()
   n=len(tiles)
   for q in c['top_fractions']:
    k=math.ceil(n*q);part=np.partition(tiles,n-k);expected=int(part[n-k:].sum());r=next(r for r in summary if r['state']==state['key'] and r['camera']==name and r['top_fraction']==q);assert r['selected']==k and r['selected_overlap']==expected and r['total_overlap']==int(tiles.sum())
   # Read each compressed export and compare integer metrics without loading CSV into RAM.
   path=H/'tables'/f'{state["key"]}__{name}__top10.csv.gz';count=0;total=0;one=0;prev=None;seen=set()
   with gzip.open(path,'rt',encoding='utf8') as f:
    for r in csv.DictReader(f):
     j=int(r['row']);t=int(r['tiles']);assert j not in seen;seen.add(j);assert t==tiles[j] and int(r['init_id'])==a['init_id'][j]
     assert r['initial_source']==('SfM' if a['origin'][j]==0 else 'prior_patch');pair=(-t,j);assert prev is None or prev<=pair;prev=pair
     count+=1;total+=t;one+=t*int(r['top1']);assert int(r['rank'])==count and int(r['top1'])==(count<=math.ceil(.01*n))
   rr=[r for r in summary if r['state']==state['key'] and r['camera']==name];assert count==math.ceil(.1*n);assert total==next(r['selected_overlap'] for r in rr if r['top_fraction']==.1);assert one==next(r['selected_overlap'] for r in rr if r['top_fraction']==.01)
   checked.append(dict(state=state['key'],camera=name,rows=count,partition_rank_sums_equal=True,csv_rows_match_original_arrays=True));print('VERIFY_TOP',state['key'],name,count,flush=True)
 assert len(checked)==20
 # Existing independent stop restore audit verifies completed/attempted state boundary.
 boundary=read(ROOT/'verification/stop_boundary/result.json');assert boundary['status']=='PASS_COMPLETE_BEFORE_ATTEMPT_BOUNDARY'
 dump(H/'independent_verification.json',dict(at=stamp(),status='PASS',checks=checked,stop_boundary_status=boundary['status'],optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
