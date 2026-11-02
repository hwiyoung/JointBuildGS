"""One authorized continuation, with immutable r8 inputs and no automatic retry."""
import runpy,sys,traceback
from common import *
def main():
    root=OUT/'r8_recorded_continue'
    for name in ['r8_record_prepare.lock.json','r8_record_runtime.lock.json']:
        lock=json.loads((CFG/name).read_text())
        for p,h in lock['files'].items():assert sha(p)==h,p
    assert json.loads((root/'verification/result.json').read_text())['status']=='PASS'
    cfg=json.loads((CFG/'r8_record_continue.json').read_text())
    target=OUT/'r8/stage1/B173nb_b10_LoD2';seed=json.loads((target/'seed_receipt.json').read_text())
    assert sha(target/'seeds.npz')==seed['seeds_sha256']
    index=json.loads((target/'maps/index.json').read_text())
    assert sha(OUT/'r8/targets/B173nb_b10_LoD2.npz')==index['target_sha256']
    for meta in index['views'].values():assert sha(target/'maps'/meta['file'])==meta['sha256']
    model=Path(cfg['model']);assert str(model)==sys.argv[sys.argv.index('-m')+1];model.mkdir(parents=True,exist_ok=False)
    dump(model.parent/'input_binding.json',dict(at=stamp(),checkpoint_sha256=sha(cfg['checkpoint']),seed=seed,map_index_sha256=sha(target/'maps/index.json'),scientific_verdict=None))
    sys.path.insert(0,'/source')
    import r8_record_hooks as H
    H.install(cfg)
    sys.argv=[str(root/'runtime/train_recorded.py')]+sys.argv[1:]
    try:runpy.run_path(sys.argv[0],run_name='__main__')
    except Exception as error:
        tb=sys.exc_info()[2]
        try:H.save_stop(error,tb)
        except Exception as saving:
            dump(root/'STOP_SAVE_FAILURE.json',dict(at=stamp(),error=str(error),save_error=str(saving),traceback=traceback.format_exc(),automatic_retry=False,scientific_verdict=None))
        raise
if __name__=='__main__':main()
