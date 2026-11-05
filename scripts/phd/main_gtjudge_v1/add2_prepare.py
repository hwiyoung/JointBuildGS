import sys,types,time
from add2_common import *
import common

def main(site,prior,mode='prepare'):
    config2();original_O=O;stem=f'{site}__{prior}';base=O/'addendum2/fix_inputs';base.mkdir(parents=True,exist_ok=True);target=target_file(site,prior)
    common.np=np;common.time=time;common.S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1';common.TG=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
    common.O=base;common.D=D/'addendum2';common.timing=lambda stage,start,**kw:dump(base/'timing'/f'{stage}.json',dict(at=now(),seconds=time.monotonic()-start,**kw))
    link=base/'targets'/f'{stem}.npz';link.parent.mkdir(exist_ok=True)
    if not link.exists():link.symlink_to(target)
    assert sha(link)==sha(target)
    outside=base/'outside'/site;outside.mkdir(parents=True,exist_ok=True)
    if not (outside/'budget_receipt.json').exists():(outside/'budget_receipt.json').symlink_to(FT/'outside'/site/'budget_receipt.json')
    root=base/'stage1'/stem;root.parent.mkdir(exist_ok=True)
    if mode=='initialize':
        if (base/'verification'/f'loaded_{stem}.json').exists():return
        src=R/'scripts/phd/main_finaltrain_v1/initialize_check.py';code=src.read_text().replace("'--jbgs_target','on'","'--jbgs_targets',str(O/'targets'/f'{stem}.npz'),'--jbgs_target','on'")
        sys.argv=[str(src),site,prior];exec(compile(code,str(src),'exec'),{'__file__':str(src),'__name__':'initialize_fix'});return
    if not root.exists() and target==FT/'targets'/f'{stem}.npz':root.symlink_to(FT/'stage1'/stem)
    if not (root/'ready.json').exists():
        if root.exists():root.rename(root.with_name(root.name+'_incomplete_'+str(time.time_ns())))
        src=R/'scripts/phd/main_finaltrain_v1/prepare_inputs.py';m=types.ModuleType('fix_prepare');m.__file__=str(src);exec(compile(src.read_text(),str(src),'exec'),m.__dict__);m.main(site,prior)
    if not (base/'verification'/f'inputs_{stem}.json').exists():
        src=R/'scripts/phd/main_finaltrain_v1/verify_inputs.py';sys.argv=[str(src),site,prior];exec(compile(src.read_text(),str(src),'exec'),{'__name__':'verify_fix','__file__':str(src)})
    dump(base/'ready'/f'{stem}.json',dict(at=now(),target=str(target),target_sha256=sha(target),stage1=str(root),original_maps_reused=root.is_symlink(),GT_used=False,scientific_verdict=None));print('FIX_INPUTS_READY',stem,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
