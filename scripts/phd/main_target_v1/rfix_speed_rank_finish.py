"""Seal exact row selections and check native operands; read-only saved states."""
import sys,time,subprocess,fcntl,datetime,collections
from r8_screen_prepare import *
root=O/'rfix_speed/rank_refinement';keys=j(C/'rfix_speed_rank_full.json')['states']
while not all((root/'execution'/(k+'_receipt.json')).exists() for k in keys):time.sleep(15)
assert all(j(root/'execution'/(k+'_receipt.json'))['exit_code']==0 for k in keys)
states=[];files={};rank_rows=[]
for key in keys:
 p=root/'gradients'/key/'result.json';data=j(p);assert data['status']=='PASS';files[docker(p)]=sha(p);candidates=[]
 for view in data['rows']:
  for name,m in view['parameters'].items():
   assert len(m['worst_rows'])<=64
   assert len(m['worst_rows'])==64 or m['first_omitted_row'] is None
   assert m['ranking'].startswith('exact global64')
   candidates += [dict(id=int(i),camera=view['camera'],parameter=name,max_abs=float(d)) for d,i in m['worst_rows']]
 candidates.sort(key=lambda r:(-r['max_abs'],r['id'],r['camera'],r['parameter']));selected=[];seen=set()
 for v in candidates:
  if v['id'] in seen:continue
  seen.add(v['id']);selected.append(v)
  if len(selected)==20:break
 assert len(selected)==20
 # Every omitted row is behind64 distinct rows in its own view/parameter;
 # therefore it cannot enter the global top20 distinct rows under the same tie rule.
 rank_rows.append(dict(state=key,status='PASS_EXACT_GLOBAL64',selected20th=selected[-1],proof='Every omitted row has64 distinct rows ahead under delta descending / row ascending; union of per-parameter top64 contains global top20.'))
 states.append(dict(state=key,rows=selected))
for state in j(C/'rfix_speed_addends.json')['states']:
 if state['state'] in keys:continue
 upper=0.
 for view in j(O/'rfix_speed/gradients'/state['state']/'result.json')['rows']:
  for m in view['parameters'].values():
   w=m['worst_rows'];groups=collections.defaultdict(list)
   for d,i in w:groups[i//65536].append(d)
   upper=max([upper]+([w[-1][0]] if len(w)==16 else [])+[min(v) for v in groups.values() if len(v)==8])
 assert state['rows'][-1]['max_abs']>upper
 rank_rows.append(dict(state=state['state'],status='PASS_STRICT_OMITTED_BOUND',selected20th_delta=state['rows'][-1]['max_abs'],omitted_upper_bound=upper))
dest=root/'addends';dest.mkdir(exist_ok=False)
cfg=dict(at=datetime.datetime.now().astimezone().isoformat(),states=states,chunk_size=4,criterion='all18 native per-pixel atomic addends byte equal',selection='exact top20 distinct rows from repeat gradient experiment; same frozen30 views and loss; old results preserved',optimization_steps=0,scientific_verdict=None)
dump(C/'rfix_speed_rank_addends.json',cfg)
for p in [C/'rfix_speed_rank_addends.json',R/'scripts/phd/main_target_v1/rfix_speed_rank_addends.py']:files[docker(p)]=sha(p)
dump(C/'rfix_speed_rank_addends.lock.json',dict(at=cfg['at'],files=files,scientific_verdict=None));dump(root/'ranking_complete.json',dict(at=cfg['at'],status='PASS',rows=rank_rows,scientific_verdict=None))
handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/photo_gpu_0.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
active=subprocess.check_output(['nvidia-smi','-i','0','--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
for key in keys:
 cmd=j(O/'rfix/execution'/('gradient_'+key+'_command.json'));cmd[cmd.index('--name')+1]='jbgs-rfix-rank-addends-'+key;cmd[cmd.index('--gpus')+1]='device=0';old=next(v for v in cmd if v in ['/repo/scripts/phd/main_target_v1/rfix_gradient.py','/repo/scripts/phd/main_target_v1/rfix_gradient_fast.py']);cmd[cmd.index(old)]='/repo/scripts/phd/main_target_v1/rfix_speed_rank_addends.py'
 dump(root/'execution'/(key+'_addends_command.json'),cmd)
 with (root/'execution'/(key+'_addends.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(root/'execution'/(key+'_addends_receipt.json'),dict(exit_code=rc,at=datetime.datetime.now().astimezone().isoformat(),scientific_verdict=None));assert rc==0
print('EXACT_RANK_ADDENDS_COMPLETE',flush=True)
