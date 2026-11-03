"""Exactly one authorized continuation with immutable method inputs."""
import sys,runpy,traceback
from common import *
def main():
 root=OUT/'rfix_continue';cfg=json.loads((CFG/'rfix_continue.json').read_text());lock=json.loads((CFG/'rfix_continue.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 assert sha(cfg['extension'])==cfg['extension_sha256']
 assert not (root/'STOP_REQUEST.json').exists()
 import torch
 state=torch.load(cfg['checkpoint'],map_location='cpu');assert state['iteration']==14030 and state['recording_stop']['ordinary_resume_ready']
 assert state['model'][10]['state'] and all(k in state for k in ['rng','viewpoint_stack','target_r6']);del state
 target=OUT/'r8/stage1/B173nb_b10_LoD2';seed=json.loads((target/'seed_receipt.json').read_text());assert sha(target/'seeds.npz')==seed['seeds_sha256']
 index=json.loads((target/'maps/index.json').read_text());assert sha(OUT/'r8/targets/B173nb_b10_LoD2.npz')==index['target_sha256']
 for meta in index['views'].values():assert sha(target/'maps'/meta['file'])==meta['sha256']
 model=Path(cfg['model']);assert str(model)==sys.argv[sys.argv.index('-m')+1];model.mkdir(parents=True,exist_ok=False)
 dump(model.parent/'input_binding.json',dict(at=stamp(),checkpoint_sha256=sha(cfg['checkpoint']),extension_sha256=sha(cfg['extension']),seed=seed,map_index_sha256=sha(target/'maps/index.json'),scientific_verdict=None))
 sys.path.insert(0,'/source')
 import rfix_continue_hooks as F
 F.install(cfg)
 sys.argv=[str(root/'runtime/train_recorded.py')]+sys.argv[1:]
 try:runpy.run_path(sys.argv[0],run_name='__main__')
 except Exception as error:
  tb=sys.exc_info()[2]
  try:F.H.save_stop(error,tb)
  except Exception as saving:dump(root/'STOP_SAVE_FAILURE.json',dict(at=stamp(),error=str(error),save_error=str(saving),traceback=traceback.format_exc(),automatic_retry=False,scientific_verdict=None))
  raise
 dump(root/'TRAINING_COMPLETE.json',dict(at=stamp(),iteration=30000,scientific_verdict=None))
if __name__=='__main__':main()
