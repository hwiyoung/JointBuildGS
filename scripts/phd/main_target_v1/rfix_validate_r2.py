"""Verify current top-five membership and full load table, then saved-evidence audit."""
import rfix_validate as V
from common import *
ROOT=OUT/'rfix';DEST=DOC/'rfix'
def main():
 cfg=json.loads((CFG/'rfix.json').read_text());full=json.loads((DEST/'tables/per_view_full_load.json').read_text())['rows'];assert len(full)==1624;rows=[]
 for state in cfg['states']:
  d=json.loads((ROOT/'states'/state['key']/'result.json').read_text());top=[r['camera'] for r in sorted(d['records'],key=lambda r:(-r['performance'][1]['overlaps'],r['camera']))[:5]];assert top==state['original_top5'];assert set(top)<=set(state['gradient_views'])
  table={r['camera']:r for r in full if r['state']==state['key']}
  for record in d['records']:
   r=table[record['camera']]
   for variant,i in [('original',1),('fixed',2)]:
    p=record['performance'][i]
    for field in ['overlaps','peak_allocated_bytes','peak_reserved_bytes']:assert r[variant+'_'+field]==p[field]
    assert r[variant+'_buffer_bytes']==p['binning_bytes'] and r[variant+'_seconds']==p['seconds_including_accounting']
  rows.append(dict(state=state['key'],current_original_top5=top,locked_top5_equal=True,all_in_gradient_views=True,per_view_load_table_exact=True))
 dump(DEST/'current_top5_validation.json',dict(at=stamp(),rows=rows,scientific_verdict=None));V.main()
if __name__=='__main__':main()
