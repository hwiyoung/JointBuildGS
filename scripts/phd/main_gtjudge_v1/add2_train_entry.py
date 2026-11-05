import sys,runpy
from add2_common import *
site,prior=sys.argv[1:3];config2();stem=f'{site}__{prior}';base=O/'addendum2/fix_inputs'
assert json.loads((O/'verification/unit_r26.json').read_text())['status']=='PASS'
lock=json.loads((C/'runtime.add2.lock.json').read_text())
for path,digest in lock['files'].items():assert sha(path)==digest,('R26_RUNTIME_CHANGED',path)
assert json.loads((base/'verification'/f'loaded_{stem}.json').read_text())['status']=='PASS'
inputs=json.loads((base/'verification'/f'inputs_{stem}.json').read_text());target=target_file(site,prior)
assert inputs['status']=='PASS' and inputs['target_sha256']==sha(target)
assert sys.argv[sys.argv.index('--jbgs_targets')+1]==str(target)
fs=O/'freespace_targets'/f'{stem}.json';f=json.loads(fs.read_text());assert f['target_sha256']==sha(target)
assert f['patch_file_sha256']==sha(fs.with_suffix('.npz')) and f['GT_used'] is False
if prior=='LoD2':assert (O/'queue/addendum2/selection_commit.json').exists()
model=Path(sys.argv[sys.argv.index('-m')+1]);dump(model.parent/'input_binding.json',dict(at=now(),inputs=inputs,free_space=f,runtime_lock_sha256=sha(C/'runtime.add2.lock.json'),GT_used_for_training=False,scientific_verdict=None))
sys.path.insert(0,str(R/'scripts/phd/main_finaltrain_v1'));from renderer import install
install();sys.path.insert(0,'/source');sys.argv=['/source/train.py']+sys.argv[3:];runpy.run_path('/source/train.py',run_name='__main__')
assert (model/'jbgs_complete/iteration_30000/checkpoint.pth').exists() and (model/'point_cloud/iteration_30000/point_cloud.ply').exists()
dump(model.parent/'TRAINING_COMPLETE.json',dict(at=now(),iteration=30000,scientific_verdict=None))
