"""Path-only adapter to FINALTRAIN's exact seed and target-disc map preparation."""
import sys,types,os,time
import numpy as np
from common import *
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1';TG=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
# Imported modules use this common namespace; outputs remain /gtjudge.
import common
common.np=np;common.S0=S0;common.TG=TG;common.time=time
common.timing=lambda stage,start,**kw: dump(O/'timing'/f'{stage}.json',dict(at=now(),seconds=time.monotonic()-start,**kw))

def main(site,prior):
    cfg();stage_lock(1);stem=f'{site}__{prior}'
    if (O/'stage1'/stem/'ready.json').exists():return
    target=O/'targets_gt'/f'{stem}.npz'
    # Existing reader expects targets/. Link only our exact new diagnostic file.
    link=O/'targets'/target.name;link.parent.mkdir(exist_ok=True)
    if not link.exists():link.symlink_to(target)
    outside=O/'outside'/site;outside.mkdir(parents=True,exist_ok=True)
    receipt=outside/'budget_receipt.json'
    if not receipt.exists():receipt.symlink_to(FT/'outside'/site/'budget_receipt.json')
    src=R/'scripts/phd/main_finaltrain_v1/prepare_inputs.py'
    module=types.ModuleType('gt_prepare');module.__file__=str(src)
    exec(compile(src.read_text(),str(src),'exec'),module.__dict__)
    module.main(site,prior)
    # Exact actual-file and all-map checks, inherited from FINALTRAIN.
    src=R/'scripts/phd/main_finaltrain_v1/verify_inputs.py';sys.argv=[str(src),site,prior]
    exec(compile(src.read_text(),str(src),'exec'),{'__name__':'gt_verify','__file__':str(src)})
if __name__=='__main__':main(*sys.argv[1:])
