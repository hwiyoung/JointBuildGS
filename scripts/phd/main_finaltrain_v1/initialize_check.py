"""Instantiate the real scene/controller and check loaded arrays before training."""
import sys
from argparse import ArgumentParser
from common import *
sys.path.insert(0,'/source')
import torch
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.general_utils import safe_state
import jbgs_target
from gaussian_renderer import render

site,prior=sys.argv[1:];stem=f'{site}__{prior}';folder=O/'verification/initial'/stem
folder.mkdir(parents=True,exist_ok=False)
p=ArgumentParser();lp=ModelParams(p);pp=PipelineParams(p);jbgs_target.register_args(p)
args=p.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(folder),'--eval','-r','1','--data_device','cpu',
    '--jbgs_target','on','--jbgs_target_rev','r8','--jbgs_finaltrain','on','--jbgs_target_dir',str(O/'stage1'/stem)])
args.jbgs_judgment='off';args.jbgs_appearance='off';args.jbgs_mv_consistency='off'
safe_state(False);dataset=lp.extract(args);g=GaussianModel(args.sh_degree);scene=Scene(dataset,g,shuffle=True)
control=jbgs_target.create(args,scene,g,render,pp.extract(args))
loaded=json.loads((folder/'target_monitor/loaded_targets.json').read_text());assert loaded['status']=='PASS'
target=loadz(O/'targets'/f'{stem}.npz',['sigma']);total=0
for name,m in control.maps.items():
    patch=m['owner']>=0;ids=m['owner'][patch].numpy()
    assert np.array_equal(m['sigma'][patch].numpy(),target['sigma'][ids].astype('f4'))
    assert np.array_equal(m['weight'][patch].numpy(),np.clip(control.sigma_ref/m['sigma'][patch].numpy(),.1,10))
    total+=int(patch.sum())
dump(O/'verification'/f'loaded_{stem}.json',dict(at=now(),status='PASS',scene_gaussians=len(g._xyz),targets=loaded['targets'],views=len(control.maps),checked_patch_pixels=total,optimizer_steps=0,scientific_verdict=None))
print('PASS_ACTUAL_LOADER',stem,len(g._xyz),flush=True)
