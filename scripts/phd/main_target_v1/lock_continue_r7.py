"""Freeze the direct continuation authorization and exact existing complete states."""
import hashlib,json,subprocess
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 assert not (CFG/'continue_r7.json').exists()
 r=OUT/'r7_continue';r.mkdir(exist_ok=False);(r/'runs').mkdir()
 old=json.loads((CFG/'target_v1.runtime.r7.lock.json').read_text())
 for p,h in old['files'].items():assert sha(REPO/p)==h,p
 runs={}
 for prior in ['ALS','LoD2']:
  name=f'tg_B173nb_b10_{prior}_s0_r7';root=OUT/'r7/runs'/name;cp=root/'model/jbgs_complete/iteration_7000/checkpoint.pth';h=sha(cp)
  receipt=json.loads(cp.with_name('receipt.json').read_text());assert h==receipt['checkpoint_sha256'];assert json.loads((root/'model/target_monitor/health_7000.json').read_text())['status']=='PASS_HEALTH'
  runs[prior]=dict(name=name,checkpoint=str(cp.relative_to(OUT)),checkpoint_sha256=h,original_command_sha256=sha(root/'command.json'))
 c=dict(at=stamp(),authority='decision_20261101_2115_continue_r7.md',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),revision='r7',priors=['ALS','LoD2'],runs=runs,start_iteration=7000,end_iteration=30000,checkpoints=[15000,30000],original_stop_sha256=sha(OUT/'r7/STOP_BOTH.json'),geometry_is_record_only=True,health='unchanged frozen r7 including 500-step scheduled opacity reset grace; inherited joint stop on health or execution failure',other_six='NOT_AUTHORIZED',model_output='r7_continue/runs/<original logical name>/model; preserve initial r7 stopped files and post-7000 trajectory separately',method_changes=[],image_id=subprocess.check_output(['docker','image','inspect','-f','{{.Id}}','jointbuildgs:geogs-conf-guided-v1'],text=True).strip(),scientific_verdict=None)
 dump(CFG/'continue_r7.json',c)
 names=['scripts/phd/main_target_v1/'+x for x in ['train_entry_continue_r7.py','run_continue_r7.py','lock_continue_r7.py']]
 dump(CFG/'continue_r7.lock.json',dict(at=stamp(),config_sha256=sha(CFG/'continue_r7.json'),authority_sha256=sha(CFG/c['authority']),source_runtime_lock_sha256=sha(CFG/'target_v1.runtime.r7.lock.json'),files={n:sha(REPO/n) for n in names},scientific_verdict=None));print('CONTINUATION_LOCKED',flush=True)
if __name__=='__main__':main()
