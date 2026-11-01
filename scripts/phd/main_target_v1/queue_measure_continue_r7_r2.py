"""Finite serial measurement queue; no geometry value controls resumed training."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump

def host(path):return Path(path.replace('/ph',str(PH),1))
from readout_resources_r2 import cpu

def main():
 cfg=json.loads((CFG/'scoring_continue_r7.json').read_text());rows=[r for r in cfg['rows'] if r['iteration']==7000 or r['family']=='base'];root=OUT/'r7_continue';assert json.loads((root/'scoring/parity.json').read_text())['status']=='PASS'
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
    subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_axes_continue_r7_resources_r2.sh'),r['key'],kind],check=True);worked=True;break
   if worked:break
  complete=sum((root/'scoring'/r['key']/kind/'values.json').exists() for r in rows for kind in ['current','final'])
  dump(root/'measurement_progress.json',dict(at=stamp(),complete=complete,planned=16,scientific_verdict=None))
  if complete==16:print('ALL_16_MESH_SCORES_COMPLETE',flush=True);return
  if not worked:time.sleep(10)
if __name__=='__main__':main()
