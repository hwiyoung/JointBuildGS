"""Verify r8 source, frozen seeds/maps, and unit gates before starting the new pilot."""
import runpy,sys
from common import *
def main():
    lock=json.loads((CFG/'target_v1.runtime.r8.lock.json').read_text())
    assert sha(CFG/'target_v1.r8.json')==lock['config_sha256']
    assert json.loads((OUT/'r8/verification/unit.json').read_text())['status']=='PASS_R8_UNIT'
    assert json.loads((OUT/'r8/verification/runtime.json').read_text())['status']=='PASS_R8_SOURCE_AND_INPUTS'
    for name,digest in lock['files'].items():assert sha(REPO/name)==digest,name
    site,prior=sys.argv[1:3];root=OUT/'r8/stage1'/f'{site}_{prior}'
    seed=json.loads((root/'seed_receipt.json').read_text());assert sha(root/'seeds.npz')==seed['seeds_sha256']
    index=json.loads((root/'maps/index.json').read_text())
    assert sha(OUT/'r8/targets'/f'{site}_{prior}.npz')==index['target_sha256']
    for meta in index['views'].values():assert sha(root/'maps'/meta['file'])==meta['sha256']
    assert json.loads((OUT/'r8/verification/initial'/prior/'result.json').read_text())['status']=='PASS_R8_INITIALIZATION'
    model=Path(sys.argv[sys.argv.index('-m')+1]);model.mkdir(parents=True,exist_ok=False)
    dump(model.parent/'input_binding.json',dict(at=stamp(),seed=seed,map_index_sha256=sha(root/'maps/index.json'),
        config_sha256=lock['config_sha256'],runtime_lock_sha256=sha(CFG/'target_v1.runtime.r8.lock.json'),scientific_verdict=None))
    sys.path.insert(0,'/source');sys.argv=['/source/train.py']+sys.argv[3:];runpy.run_path('/source/train.py',run_name='__main__')
if __name__=='__main__':main()
