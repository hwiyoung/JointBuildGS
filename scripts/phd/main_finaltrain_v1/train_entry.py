"""Verify frozen preflight and inputs, then invoke unchanged r8 train.py in r23."""
import runpy,sys
from common import *

def main():
    site,prior=sys.argv[1:3];c=cfg();lock=json.loads((C/'runtime.lock.json').read_text())
    assert lock['config_sha256']==sha(C/'finaltrain_v1.json')
    for p,h in lock['files'].items():assert sha(p)==h,p
    for name in ['unit_math.json','unit_default.json']:
        assert json.loads((O/'verification'/name).read_text())['status']=='PASS'
    stem=f'{site}__{prior}';root=O/'stage1'/stem;rec=json.loads((O/'verification'/f'inputs_{stem}.json').read_text());assert rec['status']=='PASS'
    for p in ['ALS','LoD2']:assert json.loads((O/'verification'/f'loaded_{site}__{p}.json').read_text())['status']=='PASS'
    assert sha(O/'targets'/f'{stem}.npz')==rec['target_sha256'];assert sha(root/'seeds.npz')==rec['seeds_sha256'];assert sha(root/'maps/index.json')==rec['index_sha256']
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values():assert sha(root/'maps'/meta['file'])==meta['sha256']
    model=Path(sys.argv[sys.argv.index('-m')+1]);assert not model.exists()
    dump(model.parent/'input_binding.json',dict(at=now(),config_sha256=sha(C/'finaltrain_v1.json'),runtime_sha256=sha(C/'runtime.lock.json'),
        inputs=rec,renderer=c['renderer'],scientific_verdict=None))
    sys.path.insert(0,'/source')
    from renderer import install
    install()
    sys.argv=['/source/train.py']+sys.argv[3:];runpy.run_path('/source/train.py',run_name='__main__')
    assert (model/'jbgs_complete/iteration_30000/checkpoint.pth').is_file()
    assert (model/'point_cloud/iteration_30000/point_cloud.ply').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json',dict(at=now(),iteration=30000,scientific_verdict=None))
if __name__=='__main__':main()
