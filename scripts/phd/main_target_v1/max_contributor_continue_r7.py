"""Inference-only instrumented CUDA rendering, exact output replay and pixel ancestry."""
import sys,os
sys.path.insert(0,'/source');os.environ['MAX_JOBS']='2'
from argparse import ArgumentParser
import numpy as np
import torch
from torch.utils.cpp_extension import load
import diff_surfel_rasterization as raster
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}
@torch.no_grad()
def main():
    import importlib.util
    prior=sys.argv[1];iteration=int(sys.argv[2]);library=OUT/'r5/runtime/maxid_build/jbgs_target_r5_maxid.so'
    spec=importlib.util.spec_from_file_location('jbgs_target_r5_maxid',library);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    root=OUT/'r7_continue/failures'/f'{prior}_{iteration}';root.mkdir(parents=True,exist_ok=True);(root/'pixels').mkdir(exist_ok=True)
    model=OUT/'r7_continue/attempt2/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model';parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{prior}'),'-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=iteration,shuffle=False);pipe=pp.extract(args);assert pipe.depth_ratio==0
    bg=torch.zeros(3,device='cuda');snap=loadz(model/f'target_monitor/snapshot_{iteration}.npz');seeds=loadz(OUT/'r7/stage1'/f'B173nb_b10_{prior}/seeds.npz')
    assert np.array_equal(g.init_id.cpu().numpy(),snap['init_id']);initial_patch=seeds['patch'][snap['init_id']];origins=snap['origin'];tags=snap['target_tag'];current_patch=np.full(len(tags),-1,np.int64);attached=tags==1;current_patch[attached]=snap['patch_ids'][snap['target_index'][attached]]
    maps=OUT/'r7/stage1'/f'B173nb_b10_{prior}/maps';ix=json.loads((maps/'index.json').read_text());matrix=np.zeros((2,5),np.int64);original_matrix=np.zeros((2,4),np.int64);bins=np.array([1.96,2,3,5,10,20,50,100,1000,np.inf]);hist=np.zeros((2,len(bins)-1),np.int64)
    totals=dict(prior_pixels=0,outside=0,missing=0);replay=[];values=[]
    for k,cam in enumerate(sorted(scene.getTrainCameras(),key=lambda c:c.image_name)):
        saved=loadz(model/f'check{iteration}/renders'/f'{cam.image_name}.npz');m=loadz(maps/ix['views'][cam.image_name]['file'])
        raster._C=mod;pkg=render(cam,g,pipe,bg);depth=pkg['surf_depth'].squeeze().cpu().numpy();idx=np.rint(pkg['rend_dist'].squeeze().cpu().numpy()).astype('i4')-1
        if not np.array_equal(depth,saved['depth'],equal_nan=True):
            delta=np.nanmax(abs(depth-saved['depth']));dump(root/'replay_failure.json',dict(camera=cam.image_name,max_depth_delta_m=float(delta),status='UNAVAILABLE_REPLAY_MISMATCH'));raise RuntimeError('INSTRUMENTED_DEPTH_MISMATCH')
        replay.append(cam.image_name);assert idx.max()<len(origins)
        good=(m['owner']>=0)&np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0);has=np.isfinite(depth)&(depth>0)
        signed=(depth-m['depth'])/m['sigma'];outside=good&has&(abs(depth-m['depth'])>np.float32(1.96)*m['sigma'])
        direction=np.where(signed<0,0,1);lineage=np.full(idx.shape,4,np.int8);original=np.full(idx.shape,3,np.int8);valid=idx>=0;j=np.maximum(idx,0)
        lineage[valid&(tags[j]==0)]=2;lineage[valid&(tags[j]==2)]=3
        mask=valid&(tags[j]==1);lineage[mask]=np.where(current_patch[j][mask]==m['owner'][mask],0,1)
        original[valid&(origins[j]==0)]=2
        mask=valid&(origins[j]==1);original[mask]=np.where(initial_patch[j][mask]==m['owner'][mask],0,1)
        for d in range(2):
            sel=outside&(direction==d);hist[d]+=np.histogram(abs(signed[sel]),bins=bins)[0]
            for l in range(5):matrix[d,l]+=int((sel&(lineage==l)).sum())
            for l in range(4):original_matrix[d,l]+=int((sel&(original==l)).sum())
        totals['prior_pixels']+=int(good.sum());totals['outside']+=int(outside.sum());totals['missing']+=int((good&~has).sum())
        np.savez_compressed(root/'pixels'/f'{cam.image_name}.npz',max_gaussian=idx,lineage=lineage,initial_lineage=original,front_back=np.where(outside,direction,-1).astype('i1'))
        values.append(dict(camera=cam.image_name,prior_pixels=int(good.sum()),outside=int(outside.sum()),missing=int((good&~has).sum())))
        if k%20==0:print('MAXID',prior,k+1,203,flush=True)
    assert matrix.sum()==totals['outside'] and hist.sum()==totals['outside']
    dump(root/'summary.json',dict(at=stamp(),status='PASS_INDIVIDUAL_MAX_CONTRIBUTOR',iteration=iteration,prior=prior,totals=totals,cross_counts=matrix.tolist(),cross_fraction_of_outside=(matrix/totals['outside']).tolist(),cross_fraction_of_all_prior=(matrix/totals['prior_pixels']).tolist(),direction=['front','behind'],lineage=['same_current_patch','other_current_patch','background','released','unavailable'],initial_lineage=['same_initial_patch','other_initial_patch','background','unavailable'],initial_lineage_cross_counts=original_matrix.tolist(),sigma_hist_bins=[float(x) if np.isfinite(x) else 'inf' for x in bins],sigma_hist_counts=hist.tolist(),views=values,byte_equal_depth_replay_views=replay,optimization_steps=0,method='argmax alpha*T in actual CUDA traversal; first on tie; distortion output repurposed only for diagnostics; all depth arrays byte-equal saved r7',scientific_verdict=None))
if __name__=='__main__':main()
