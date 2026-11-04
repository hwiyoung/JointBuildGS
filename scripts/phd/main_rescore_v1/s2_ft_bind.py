"""Bind only completed FINALTRAIN checkpoints; no training or invented cameras."""
from common import *
import sys
from s2_ft_paths import model_path
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
def main(site,prior):
 receipt=FT/'runs'/site/f'ft_{prior}_s0/receipt.json';rr=json.loads(receipt.read_text());assert rr['status']=='TRAINING_COMPLETE_30000';model=model_path(rr,site,prior);p=model/'point_cloud/iteration_30000/point_cloud.ply';assert p.exists()
 v=json.loads((O/'views'/f'{site}.json').read_text());key=f'{site}__{prior}__FINALTRAIN_30000';j=dict(site=site,prior=prior,family='FINALTRAIN_30000',key=key,views=len(v['views']),box=v['box'],ply=str(p),model_sha256=sha(p),training_receipt=str(receipt),training_receipt_sha256=sha(receipt),renderer='/repo/src/phd/forks/GeoGS-conf-guided-v1-r23',image='sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be',cache=str(O/'renders'/key),scientific_verdict=None);dump(O/'jobs'/f'{key}.json',j)
 dump(C/f'addendum3_stage2_{site}_{prior}_model.lock.json',dict(at=now(),job=j,renderer_config=json.loads((R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json').read_text())['renderer'],gpu_authority='User reply: figure6.1 only has no-GPU restriction; stage2 inference allowed',scientific_verdict=None));print('BOUND',key,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
