"""Verify locked inputs, reuse the FINALTRAIN speed renderer, enter r24."""
import runpy,sys
from common import *
def main():
    site,prior=sys.argv[1:3];c=cfg();runtime=json.loads((C/'runtime.lock.json').read_text())
    assert runtime['config_sha256']==sha(C/'release_v1.json')
    for p,h in runtime['files'].items():assert sha(p)==h,p
    rec=json.loads((FT/'verification'/f'inputs_{site}__{prior}.json').read_text());assert rec['status']=='PASS'
    root=FT/'stage1'/f'{site}__{prior}'
    assert sha(FT/'targets'/f'{site}__{prior}.npz')==rec['target_sha256']
    assert sha(root/'seeds.npz')==rec['seeds_sha256'] and sha(root/'maps/index.json')==rec['index_sha256']
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values():assert sha(root/'maps'/meta['file'])==meta['sha256']
    model=Path(sys.argv[sys.argv.index('-m')+1]);assert not model.exists();stop=int(sys.argv[sys.argv.index('--jbgs_stop_after')+1])
    dump(model.parent/'input_binding.json',dict(at=now(),config_sha256=sha(C/'release_v1.json'),inputs=rec,renderer=c['renderer'],scientific_verdict=None))
    sys.path.insert(0,'/source');sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from renderer import install
    install();sys.argv=['/source/train.py']+sys.argv[3:];runpy.run_path('/source/train.py',run_name='__main__')
    assert (model/f'jbgs_complete/iteration_{stop}/checkpoint.pth').is_file()
    assert (model/f'point_cloud/iteration_{stop}/point_cloud.ply').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json',dict(at=now(),iteration=stop,scientific_verdict=None))
if __name__=='__main__':main()
