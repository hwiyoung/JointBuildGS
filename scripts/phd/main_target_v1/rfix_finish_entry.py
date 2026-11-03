"""Exact scheduled15000 resume with one explicit health-rule exception."""
import sys,runpy,traceback,importlib.util
from common import *
def main():
 root=OUT/'rfix_continue/attempt2';cfg=json.loads((CFG/'rfix_finish.json').read_text());lock=json.loads((CFG/'rfix_finish.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 assert json.loads((root/'tests/result.json').read_text())['status']=='PASS'
 import torch
 state=torch.load(cfg['checkpoint'],map_location='cpu');assert state['iteration']==15000 and state['model'][10]['state'];del state
 model=Path(cfg['model']);assert str(model)==sys.argv[sys.argv.index('-m')+1];model.mkdir(parents=True,exist_ok=False)
 sys.path.insert(0,'/source')
 import jbgs_target_r8,jbgs_state
 spec=importlib.util.spec_from_file_location('rfix_count_override',root/'runtime/count_override.py');override=importlib.util.module_from_spec(spec);spec.loader.exec_module(override);jbgs_target_r8.TargetR8.observe=override.TargetR8.observe
 original_capture=jbgs_state.capture_state
 def capture(env):
  value=original_capture(env);value['rfix_health_override']=dict(cfg['count_override'],config_sha256=sha(CFG/'rfix_finish.json'),override_sha256=sha(root/'runtime/count_override.py'));return value
 jbgs_state.capture_state=capture
 import rfix_continue_hooks as F
 F.ROOT=root;F.install(cfg)
 dump(model.parent/'input_binding.json',dict(at=stamp(),checkpoint_sha256=sha(cfg['checkpoint']),extension_sha256=sha(cfg['extension']),count_override=cfg['count_override'],scientific_verdict=None))
 sys.argv=[str(root/'runtime/train_recorded.py')]+sys.argv[1:]
 try:runpy.run_path(sys.argv[0],run_name='__main__')
 except Exception as error:
  tb=sys.exc_info()[2]
  try:F.H.save_stop(error,tb)
  except Exception as saving:dump(root/'STOP_SAVE_FAILURE.json',dict(at=stamp(),error=str(error),save_error=str(saving),traceback=traceback.format_exc(),automatic_retry=False,scientific_verdict=None))
  raise
 dump(root/'TRAINING_COMPLETE.json',dict(at=stamp(),iteration=30000,scientific_verdict=None))
if __name__=='__main__':main()
