import json,hashlib
from run_pilot_r7 import REPO,OUT,CFG,stamp,dump
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not (CFG/'continue_r7.r1.json').exists()
 for prior in ['ALS','LoD2']:
  m=OUT/'r7_continue/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model'
  assert not (m/'target_monitor/curve.jsonl').exists()
  assert "'jbgs_tau_v': [nan, nan]" in (m.parent/'train.log').read_text()
 c=json.loads((CFG/'continue_r7.json').read_text());c.update(at=stamp(),parent_lock_sha256=sha(CFG/'continue_r7.lock.json'),restore_validation_compatibility='Treat both-NaN unused tau argument pairs as equal; original args/checkpoint/optimizer/RNG/algorithm untouched',preflight_failure_attempt='r7_continue/runs: zero optimization steps, original logs retained',model_output='r7_continue/attempt2/runs/<original logical name>/model')
 dump(CFG/'continue_r7.r1.json',c)
 names=['scripts/phd/main_target_v1/'+x for x in ['train_entry_continue_r7_compat.py','run_continue_r7_compat.py','lock_continue_r7_compat.py']]
 dump(CFG/'continue_r7.r1.lock.json',dict(at=stamp(),config_sha256=sha(CFG/'continue_r7.r1.json'),authority_sha256=sha(CFG/c['authority']),source_runtime_lock_sha256=sha(CFG/'target_v1.runtime.r7.lock.json'),files={n:sha(REPO/n) for n in names},scientific_verdict=None))
 (OUT/'r7_continue/attempt2').mkdir();print('CONTINUATION_RESTORE_COMPARISON_LOCKED')
if __name__=='__main__':main()
