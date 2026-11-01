"""Verify the authorized locked pilot, then execute the unchanged r19 training entry."""
import runpy,sys
from common import *

def main():
    lock=json.loads((CFG/'target_v1.runtime.r4n.lock.json').read_text())
    assert sha(CFG/'target_v1.stage1.r4n.json')==lock['config_sha256']
    assert json.loads((OUT/'r4n/preflight_acceptance.json').read_text())['status']=='PASS_BY_USER_DECISION'
    assert json.loads((OUT/'r4n/verification/bounds.json').read_text())['status']=='PASS_CORRECTED_RUNTIME_BOUNDS'
    assert json.loads((OUT/'r4n/verification/runtime.json').read_text())['status']=='PASS_DEFAULT_OFF_AST'
    assert not (OUT/'r4n/STOP_BOTH.json').exists()
    for name,digest in lock['files'].items():assert sha(REPO/name)==digest,name
    site,prior=sys.argv[1:3];root=OUT/'r2/stage1'/f'{site}_{prior}'
    seed=json.loads((root/'seed_receipt.json').read_text());assert sha(root/'seeds.npz')==seed['seeds_sha256']
    assert json.loads((OUT/'r2/verification'/f'stage1_{site}_{prior}.json').read_text())['status']=='PASS_STAGE1_INPUTS'
    model=Path(sys.argv[sys.argv.index('-m')+1]);model.mkdir(parents=True,exist_ok=False)
    dump(model.parent/'input_binding.json',dict(at=stamp(),seed=seed,map_index_sha256=sha(root/'maps/index.json'),
        config_sha256=lock['config_sha256'],runtime_lock_sha256=sha(CFG/'target_v1.runtime.r4n.lock.json'),scientific_verdict=None))
    sys.path.insert(0,'/source');sys.argv=['/source/train.py']+sys.argv[3:]
    runpy.run_path('/source/train.py',run_name='__main__')

if __name__=='__main__':main()
