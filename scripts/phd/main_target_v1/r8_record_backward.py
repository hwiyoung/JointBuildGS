"""Read-only saved-model backward parity; no optimizer is created or stepped."""
import sys
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
import diff_surfel_rasterization as raster
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *
from r8_record_hooks import load_extension
def main():
    root=OUT/'r8_recorded_continue';dest=root/'verification/backward';dest.mkdir(exist_ok=False)
    dump(dest/'lock.json',dict(at=stamp(),script_sha256=sha(__file__),runtime_lock_sha256=sha(CFG/'r8_record_runtime.lock.json'),optimization_steps=0,scientific_verdict=None))
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2'),'-m',str(OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/model'),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False);pipe=pp.extract(args);bg=torch.zeros(3,device='cuda')
    cams=sorted(scene.getTrainCameras(),key=lambda c:c.image_name);original=raster._C;modified=load_extension();modified.jbgs_set_guard(.5)
    params=['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity'];rows=[]
    for ci in [0,101,202]:
        gradients=[]
        for mod in [original,original,modified]:
            for name in params:getattr(g,name).grad=None
            raster._C=mod;pkg=render(cams[ci],g,pipe,bg)
            loss=pkg['render'].mean()+.01*pkg['surf_depth'].nan_to_num().mean()+.001*pkg['rend_dist'].mean()+.001*pkg['rend_normal'].mean()
            loss.backward();gradients.append({name:getattr(g,name).grad.detach().cpu().numpy().copy() for name in params});del pkg,loss
        for name in params:
            a,b,c=[v[name] for v in gradients];assert np.isfinite(a).all() and np.isfinite(b).all() and np.isfinite(c).all()
            def metrics(x,y):
                delta=x.astype('f8')-y;return dict(byte_equal=bool(np.array_equal(x,y)),max_abs=float(abs(delta).max()),relative_l2=float(np.linalg.norm(delta.ravel())/max(np.linalg.norm(x.astype('f8').ravel()),1e-30)),allclose=bool(np.allclose(x,y,atol=1e-7,rtol=1e-4)))
            repeat=metrics(a,b);changed=metrics(a,c);assert repeat['allclose'] and changed['allclose'],(name,repeat,changed)
            rows.append(dict(camera=cams[ci].image_name,parameter=name,original_repeat=repeat,recording_vs_original=changed))
        print('BACKWARD_PARITY',cams[ci].image_name,flush=True)
    dump(dest/'result.json',dict(at=stamp(),status='PASS',rows=rows,absolute_tolerance=1e-7,relative_tolerance=1e-4,reason='float32 CUDA atomic accumulation; original repeat reported separately',optimization_steps=0,scientific_verdict=None))
    print('PASS_BACKWARD_PARITY',flush=True)
if __name__=='__main__':main()
