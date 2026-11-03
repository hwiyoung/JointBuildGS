from common import *
from score_mesh import score
import sys

def main(site,prior,family):
 path=S1/'defs'/site/f'prior_{prior}.npz' if family=='prior' else PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/mvs'/site/'mesh_mvs_a.ply'
 key=f'{site}__{prior}__{family}';v=score(site,prior,key,path);v['input_surface']=dict(source=str(path),sha256=sha(path),mode='fresh inherited 400/m2 seed0 sample and geometric distances; new column assignment',source_code='scripts/phd/main_stage1_v1/metrics_s1.py:load_result(surface_),summary; scripts/phd/main_axes71_v2/ax_common.py:mesh_of(mvs_a)',new_surface_created=False,user_authority='input_surface_clarification.json');dump(O/'scores'/key/'values.json',v)
if __name__=='__main__':main(*sys.argv[1:])
