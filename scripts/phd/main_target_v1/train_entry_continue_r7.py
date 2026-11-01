"""Resume the frozen r21 state under the explicit 2026-11-01 21:15 decision."""
import runpy,sys
from common import *
def main():
 c=json.loads((CFG/'continue_r7.json').read_text());lock=json.loads((CFG/'continue_r7.lock.json').read_text())
 assert sha(CFG/'continue_r7.json')==lock['config_sha256']
 for name,h in lock['files'].items():assert sha(REPO/name)==h,name
 old=json.loads((CFG/'target_v1.runtime.r7.lock.json').read_text())
 assert sha(CFG/'target_v1.r7.json')==old['config_sha256']
 for name,h in old['files'].items():assert sha(REPO/name)==h,name
 site,prior=sys.argv[1:3];assert site=='B173nb_b10' and prior in c['priors']
 row=c['runs'][prior];checkpoint=Path(sys.argv[sys.argv.index('--jbgs_resume_full')+1]);assert sha(checkpoint)==row['checkpoint_sha256']
 assert not (OUT/'r7_continue/STOP_BOTH.json').exists()
 root=OUT/'r7/stage1'/f'{site}_{prior}';seed=json.loads((root/'seed_receipt.json').read_text());assert sha(root/'seeds.npz')==seed['seeds_sha256']
 ix=json.loads((root/'maps/index.json').read_text());assert sha(OUT/'r7/targets'/f'{site}_{prior}.npz')==ix['target_sha256']
 for meta in ix['views'].values():assert sha(root/'maps'/meta['file'])==meta['sha256']
 assert json.loads((OUT/'r7/runs'/row['name']/'verification_full_state.json').read_text())['rows'][0]['status']=='PASS_COMPLETE_STATE'
 model=Path(sys.argv[sys.argv.index('-m')+1]);assert model==OUT/'r7_continue/runs'/row['name']/'model';model.mkdir(parents=True,exist_ok=False)
 dump(model.parent/'input_binding.json',dict(at=stamp(),config_sha256=lock['config_sha256'],checkpoint_sha256=row['checkpoint_sha256'],seed_sha256=seed['seeds_sha256'],maps_index_sha256=sha(root/'maps/index.json'),source_runtime_lock_sha256=sha(CFG/'target_v1.runtime.r7.lock.json'),scientific_verdict=None))
 sys.path.insert(0,'/source');sys.argv=['/source/train.py']+sys.argv[3:];runpy.run_path('/source/train.py',run_name='__main__')
if __name__=='__main__':main()
