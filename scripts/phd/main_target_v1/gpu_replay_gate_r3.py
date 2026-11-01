"""Independent replay of all-view r3 gate using float64 CPU differences and median."""
import sys
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.general_utils import safe_state
from gaussian_renderer import render
import jbgs_target

@torch.no_grad()
def main():
    site,prior=sys.argv[1:3];cfg,lock=locked_r3()
    root=OUT/'r3/replay_v2'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(root/'model'),'--eval','-r','1','--data_device','cpu'])
    (root/'model').mkdir();safe_state(False);args.jbgs_target='on';args.jbgs_target_dir=str(OUT/'r3/prior_only'/f'{site}_{prior}')
    args.jbgs_target_lambda=.05;args.jbgs_judgment='off';args.jbgs_appearance='off';args.jbgs_mv_consistency='off'
    g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g);pipe=pp.extract(args)
    control=jbgs_target.create(args,scene,g,render,pipe);reference=json.loads((OUT/'r3/preflight'/f'{site}_{prior}/initial_render.json').read_text())
    by={r['camera']:r for r in reference['views']};errors=[];missing=0;total=0;rows=[]
    for cam in scene.getTrainCameras():
        depth=render(cam,g,pipe,torch.zeros(3,device='cuda'))['surf_depth'].squeeze().cpu().numpy().astype(np.float64)
        m=control.maps[cam.image_name];target=m['depth'].numpy().astype(np.float64);owner=m['owner'].numpy()
        eligible=(owner>=0)&np.isfinite(target)&(target>0);valid=eligible&np.isfinite(depth)&(depth>0)
        e=np.abs(depth[valid]-target[valid]);median=float(np.median(e)) if len(e) else None
        row=by[cam.image_name];assert int(valid.sum())==row['rendered_target_pixels']
        assert (median is None and row['absolute_depth_error_median_m'] is None) or (median is not None and row['absolute_depth_error_median_m'] is not None and abs(median-row['absolute_depth_error_median_m'])<1e-5),(cam.image_name,len(e),median,row['absolute_depth_error_median_m'])
        errors.append(e);total+=int(eligible.sum());missing+=int((eligible&~valid).sum())
        rows.append(dict(camera=cam.image_name,pixels=len(e),median_m=median))
    pooled=np.concatenate(errors);median=float(np.median(pooled))
    assert abs(median-reference['pooled_median_m'])<1e-5 and len(pooled)==reference['pooled_pixels']
    assert (median<=.05)==(reference['status']=='PASS')
    # Persist the pooled exact error vector so the median is recomputable without another GPU run.
    np.save(root/'absolute_errors_float64.npy',pooled)
    result=dict(at=stamp(),status='PASS_INDEPENDENT_GATE_REPLAY',site=site,prior=prior,views=len(rows),pooled_pixels=len(pooled),
        median_m=median,reference_median_m=reference['pooled_median_m'],missing_pixels=missing,target_pixels=total,
        error_vector_sha256=sha(root/'absolute_errors_float64.npy'),rows=rows,training_steps=0,scientific_verdict=None)
    dump(root/'verification.json',result);print('R3_REPLAY_PASS',site,prior,median,flush=True)

if __name__=='__main__':main()
