"""Prove top20 membership despite chunk/top-list truncation in prior gradient reports."""
import sys,collections,datetime
from r8_screen_prepare import *
speed=len(sys.argv)>1 and sys.argv[1]=='speed';root=O/('rfix_speed/addends' if speed else 'rfix_addends');cfg=j(C/('rfix_speed_addends.json' if speed else 'rfix_addends.json'));grad=O/('rfix_speed/gradients' if speed else 'rfix/gradients');rows=[]
for s in cfg['states']:
 upper=0
 for view in j(grad/s['state']/'result.json')['rows']:
  for p in view['parameters'].values():
   w=p['worst_rows'];groups=collections.defaultdict(list)
   for d,i in w:groups[i//65536].append(d)
   upper=max([upper]+([w[-1][0]] if len(w)==16 else [])+[min(v) for v in groups.values() if len(v)==8])
 selected=s['rows'][-1]['max_abs'];rows.append(dict(state=s['state'],selected20th_delta=selected,omitted_upper_bound=upper,strictly_larger=selected>upper))
assert all(r['strictly_larger'] for r in rows),rows
dump(root/'ranking_completeness_r2.json',dict(at=datetime.datetime.now().astimezone().isoformat(),rows=rows,rule='bound both top8-per65536 truncation and final top16 list truncation; selected20th must strictly exceed all omitted bounds',code_sha256=sha(__file__),scientific_verdict=None));print('RANKING_PASS',speed,len(rows))
