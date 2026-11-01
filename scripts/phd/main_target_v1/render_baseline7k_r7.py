"""Render saved 7k baseline, no optimization, for shared CPU TSDF and r7 scoring."""
import sys
sys.path.insert(0,'/source')
import numpy as np,torch
from argparse import ArgumentParser
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *
@torch.no_grad()
def main():
    prior=sys.argv[1];root=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0';model=root/'model';dest=model/'check7000';dest.mkdir();(dest/'renders').mkdir()
    assert json.loads((root/'receipt.json').read_text())['status']=='COMPLETE_7000'
    p=ArgumentParser();lp=ModelParams(p);pp=PipelineParams(p);args=p.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{prior}'),'-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False);pipe=pp.extract(args);bg=torch.zeros(3,device='cuda')
    index=json.loads((OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps/index.json').read_text());views=[];cameras=sorted(scene.getTrainCameras(),key=lambda x:x.image_name)
    assert {c.image_name for c in cameras}==set(index['views'])
    for i,cam in enumerate(cameras):
        package=render(cam,g,pipe,bg);meta=index['views'][cam.image_name];assert np.allclose(cam.world_view_transform.T.cpu().numpy(),meta['W2C'],atol=2e-5)
        path=dest/'renders'/f'{cam.image_name}.npz';np.savez_compressed(path,depth=package['surf_depth'].squeeze().cpu().numpy(),rgb=(package['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1'),alpha=package['rend_alpha'].squeeze().cpu().numpy())
        views.append(dict(camera=cam.image_name,K=meta['K'],W2C=meta['W2C'],sha256=sha(path)))
        if i%40==0:print('BASE7K_RENDER',prior,i+1,len(cameras),flush=True)
    dump(dest/'coverage.json',dict(at=stamp(),iteration=7000,status='RENDER_COMPLETE_COVERAGE_PENDING_R7_MAPS',views=views,ply_sha256=sha(model/'point_cloud/iteration_7000/point_cloud.ply'),optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
