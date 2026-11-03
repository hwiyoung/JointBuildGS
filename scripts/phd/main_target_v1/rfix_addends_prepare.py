"""Lock twenty distinct worst Gaussian rows per state using sealed gradient results."""
from r8_screen_prepare import *
import datetime
root=O/'rfix_addends';root.mkdir(exist_ok=False);cfg=j(C/'rfix.json');states=[];files={}
for row in cfg['states']:
 p=O/'rfix/gradients'/row['key']/'result.json';files[docker(p)]=sha(p);data=j(p);candidates=[]
 for view in data['rows']:
  for name,metrics in view['parameters'].items():
   candidates += [dict(id=int(i),camera=view['camera'],parameter=name,max_abs=float(d)) for d,i in metrics['worst_rows']]
 candidates.sort(key=lambda r:(-r['max_abs'],r['id'],r['camera'],r['parameter']));selected=[];seen=set()
 for x in candidates:
  if x['id'] in seen:continue
  seen.add(x['id']);selected.append(x)
  if len(selected)==20:break
 assert len(selected)==20
 states.append(dict(state=row['key'],rows=selected))
c=dict(at=datetime.datetime.now().astimezone().isoformat(),selection='20 distinct Gaussian rows per state, descending largest recorded absolute gradient difference over30 views and7 parameters; tie row, camera,parameter; probe each at its maximum-difference view',states=states,chunk_size=4,criterion='all18 native per-pixel atomic addends byte equal',on_difference='/out/rfix_continue/STOP_REQUEST.json',optimization_steps=0,scientific_verdict=None)
dump(C/'rfix_addends.json',c);files[docker(C/'rfix_addends.json')]=sha(C/'rfix_addends.json');dump(C/'rfix_addends.lock.json',dict(at=c['at'],files=files,scientific_verdict=None));print('LOCKED',len(states)*20)
