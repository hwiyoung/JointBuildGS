"""Finite serial measurement queue; no geometry value controls resumed training."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump

def host(path):return Path(path.replace('/ph',str(PH),1))
def cpu(tag,script,args,heavy=False):
 handle=None
 if heavy:
  handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
  stable=0
  while stable<15:
   lines=Path('/proc/meminfo').read_text().splitlines();gb=int(next(x.split()[1] for x in lines if x.startswith('MemAvailable:')))/(1024**2)
   stable=stable+5 if gb>=56 else 0;time.sleep(5)
 env=dict(os.environ,TARGET_LANE='continue_measure',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='40' if heavy else '8',CPUS='6' if heavy else '2')
 subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_cpu.sh'),tag,script]+args,env=env,check=True)
 if handle:handle.close()
def main():
 cfg=json.loads((CFG/'scoring_continue_r7.json').read_text());rows=cfg['rows'];root=OUT/'r7_continue';assert json.loads((root/'scoring/parity.json').read_text())['status']=='PASS'
 while True:
  worked=False
  # New checkpoint records take precedence as soon as their complete renders exist.
  for r in rows:
   if r['family']!='r7' or r['iteration']==7000:continue
   it=r['iteration'];model=host(r['model']);coverage=model/f'check{it}/coverage.json'
   if not coverage.exists():continue
   if not (model.parent/f'verification{it}.json').exists():cpu('verify-'+r['key'],'verify_continue_r7.py',[r['prior'],str(it)]);worked=True;break
   mesh=host(r['current_mesh'])
   if not mesh.exists():cpu('post-'+r['key'],'post_continue_r7.py',['run',r['key']],heavy=True);worked=True;break
  if worked:continue
  # The two already-stored baseline virtual meshes and completed new renders.
  for r in rows:
   folder=root/'meshes'/r['key']
   if (folder/'receipt.json').exists():continue
   if not r['existing_virtual'] and not (folder/'render/receipt.json').exists():continue
   cpu('fuse-'+r['key'],'fuse_final_continue_r7.py',[r['key']],heavy=True);worked=True;break
  if worked:continue
  for r in rows:
   for kind in ['current','final']:
    if r['key']=='r6_ALS_7000' and kind=='current':continue # separately launched first worker owns this row
    result=root/'scoring'/r['key']/kind/'values.json';mesh=host(r['current_mesh']) if kind=='current' else root/'meshes'/r['key']/'final.ply'
    if result.exists() or not mesh.exists():continue
    subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_axes_continue_r7.sh'),r['key'],kind],check=True);worked=True;break
   if worked:break
  complete=sum((root/'scoring'/r['key']/kind/'values.json').exists() for r in rows for kind in ['current','final'])
  dump(root/'measurement_progress.json',dict(at=stamp(),complete=complete,planned=24,scientific_verdict=None))
  if complete==24:print('ALL_24_MESH_SCORES_COMPLETE',flush=True);return
  if not worked:time.sleep(10)
if __name__=='__main__':main()
