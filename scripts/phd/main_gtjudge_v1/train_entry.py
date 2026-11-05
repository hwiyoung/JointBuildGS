"""Locked r25 diagnostic training, inherited speed renderer and r23 parameters."""
import sys,runpy
from common import *
site,prior=sys.argv[1:3];config=cfg();stage_lock(3);stem=f'{site}__{prior}'
lock=json.loads((C/'runtime.add1.lock.json').read_text())
for path,digest in lock['files'].items():assert sha(path)==digest,('RUNTIME_CHANGED',path)
if sys.argv[sys.argv.index('--jbgs_preserve_freespace')+1]=='on':
    assert json.loads((O/'verification/unit_fs_schedule.json').read_text())['status']=='PASS'
loaded=json.loads((O/'verification'/f'loaded_{stem}.json').read_text());assert loaded['status']=='PASS'
assert json.loads((O/'verification/unit_default.json').read_text())['status']=='PASS_100_STEP_FIXTURE'
rec=json.loads((O/'verification'/f'inputs_{stem}.json').read_text());assert rec['status']=='PASS'
assert sha(O/'targets_gt'/f'{stem}.npz')==rec['target_sha256']
model=Path(sys.argv[sys.argv.index('-m')+1])
dump(model.parent/'input_binding.json',dict(at=now(),config_sha256=sha(C/'gtjudge_v1.add1.json'),runtime_lock_sha256=sha(C/'runtime.add1.lock.json'),inputs=rec,renderer=config['renderer'],diagnostic='정답 판단',scientific_verdict=None))
sys.path.insert(0,'/repo/scripts/phd/main_finaltrain_v1');from renderer import install
install();sys.path.insert(0,'/source');sys.argv=['/source/train.py']+sys.argv[3:]
runpy.run_path('/source/train.py',run_name='__main__')
assert (model/'jbgs_complete/iteration_30000/checkpoint.pth').exists()
assert (model/'point_cloud/iteration_30000/point_cloud.ply').exists()
dump(model.parent/'TRAINING_COMPLETE.json',dict(at=now(),iteration=30000,scientific_verdict=None))
