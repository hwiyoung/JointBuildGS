"""Observe the unchanged rasterizer auxiliary maps; no optimizer or parameter edits."""
import argparse
import json
import sys
import numpy as np
import torch
from common import *
from render_gpu import load,matrices
import gaussian_renderer as GR
import diff_surfel_rasterization as DR

def main():
    p=argparse.ArgumentParser();p.add_argument('--site',required=True);p.add_argument('--prior',default='ALS');a=p.parse_args()
    selected=json.loads((CFG/f'photos_{a.site}_{a.prior}.json').read_text())['cases']
    names=sorted({c['main']['view'] for c in selected if c['main']})
    observed={};original=DR.GaussianRasterizer.forward
    def forward(self,*args,**kwargs):
        output=original(self,*args,**kwargs);observed['allmap']=output[2];return output
    DR.GaussianRasterizer.forward=forward
    kernel=Path('/opt/geogs-source/submodules/diff-surfel-rasterization/cuda_rasterizer/forward.cu')
    assert 'if (T > 0.5)' in kernel.read_text()
    receipt=[]
    for result in [f'nojudge_{a.prior}_s0',f'lt_dynnow_{a.prior}_s0']:
        pipe,g,scene,model=load(a.site,a.prior,result,30000)
        assert pipe.depth_ratio==0.0
        folder=OUT/'four_depths'/a.site/result;folder.mkdir(parents=True,exist_ok=False)
        cams={c.image_name:c for c in scene.getTrainCameras()}
        with torch.no_grad():
            for name in names:
                cam=cams[name];pkg=GR.render(cam,g,pipe,torch.zeros(3,device='cuda'));raw=observed.pop('allmap')
                surf=pkg['surf_depth'][0].cpu().numpy();alpha=raw[1].cpu().numpy()
                mean=torch.nan_to_num(raw[0]/raw[1],nan=0.,posinf=0.,neginf=0.).cpu().numpy()
                median=raw[5].cpu().numpy();valid=(alpha>=.5)&np.isfinite(median)&(median>0)
                cache=np.load(OUT/'renders'/a.site/result/'iteration_30000/train'/(name+'.npz'))
                assert np.array_equal(surf,cache['depth']) and np.array_equal(surf,mean)
                ext,K=matrices(cam)
                np.savez_compressed(folder/(name+'.npz'),surf_depth=surf,opacity_mean=mean,
                    opacity_05=np.where(valid,median,np.nan),opacity_05_raw=median,opacity_05_valid=valid,
                    alpha=alpha,world_to_camera=ext,intrinsic=K)
                receipt.append(dict(result=result,view=name,depth_ratio=pipe.depth_ratio,
                    exact_cached_surf_depth=True,exact_surf_equals_mean=True,
                    opacity_05_reached=int(valid.sum()),pixels=int(valid.size),
                    model_sha256=sha(model/'point_cloud/iteration_30000/point_cloud.ply')))
                del pkg,raw
        del g,scene;torch.cuda.empty_cache()
    save(OUT/'four_depths'/a.site/'gpu_receipt.json',dict(at=now(),site=a.site,prior=a.prior,rows=receipt,
        kernel_path=str(kernel),kernel_sha256=sha(kernel),extension_sha256=sha(DR._C.__file__),
        renderer_sha256=sha('/source/gaussian_renderer/__init__.py'),
        opacity_05_definition='First accepted contribution where accumulated opacity reaches 0.5 in the unchanged rasterizer integration order; alpha below 0.5 is unavailable. No interpolation between discrete surfels.',
        depth_units='camera Z metres; unnormalized camera ray has z=1',optimizer_steps=0,scientific_verdict=None))
    print(a.site,'four depth renderer observation PASS',flush=True)

if __name__=='__main__':main()
