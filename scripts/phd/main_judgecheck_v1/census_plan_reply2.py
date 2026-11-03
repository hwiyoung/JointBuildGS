"""Require completed whole-tile timing gate before the full photo census."""
import json
from preflight import O
BASE=O/'r2'
def main():
    t=json.loads((BASE/'timing_estimate.json').read_text());assert t['status']=='PASS_CONTINUE_STAGE_A' and t['estimated_hours']<=48
    c=json.loads((BASE/'target_census.json').read_text());tiles=sorted(c['tile_targets'],key=lambda v:(-c['tile_targets'][v],v));(BASE/'census_tiles.txt').write_text('\n'.join(tiles)+'\n')
    for i,(prior,kind) in enumerate([('ALS',1),('LoD2',1),('LoD2',2)]):
        has={r['tile'] for r in c['rows'] if r['prior']==prior and r['kind']==kind and r['target_count']>0};(BASE/f'census_group{i}_tiles.txt').write_text('\n'.join(v for v in tiles if v in has)+'\n')
    print('CENSUS_PLAN_AUTHORIZED',c['total_targets'],t['estimated_hours'])
if __name__=='__main__':main()
