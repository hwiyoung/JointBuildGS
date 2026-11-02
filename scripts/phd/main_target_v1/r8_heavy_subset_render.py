"""Inference-only selected top-group RGB; subset tile sums must match full-state ranking."""
import sys,math,gc
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
from cause_r8_render import ObservedRasterizer
ROOT=OUT/'r8_recorded_continue';H=ROOT/'heavy'
@torch.no_grad()
def main():
 lock=json.loads((CFG/'r8_heavy_subset.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 conf=json.loads((CFG/'r8_heavy.json').read_text());row=next(r for r in conf['rows'] if r['key']=='r8_14031_stop');d=H/'subset';d.mkdir(exist_ok=False);name=conf['heavy_camera']
 parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser);args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2'),'-m',row['model'],'--eval','-r','1','--data_device','cpu'])
 safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False);g.load_ply(row['ply']);pipe=pp.extract(args);cam=next(c for c in scene.getTrainCameras() if c.image_name==name);bg=torch.zeros(3,device='cuda');mod=load_extension();obs=ObservedRasterizer(mod);raster._C=obs;mod.jbgs_set_guard(.95)
 full={k:getattr(g,k) for k in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']}
 with np.load(H/'states/r8_14031_stop'/(name+'.npz')) as a:tiles=a['tiles'].astype('i8');order=np.lexsort((np.arange(len(tiles)),-tiles))
 rows=[]
 for q in [.01,.1]:
  ix=order[:math.ceil(q*len(tiles))];gpuix=torch.as_tensor(ix,device='cuda')
  for k,v in full.items():setattr(g,k,torch.nn.Parameter(v[gpuix],requires_grad=False))
  torch.cuda.empty_cache();pkg=render(cam,g,pipe,bg);assert np.array_equal(obs.last['tiles'],tiles[ix]);np.savez_compressed(d/f'top{int(q*100)}.npz',rgb=pkg['render'].cpu().numpy(),alpha=pkg['rend_alpha'].cpu().numpy());rows.append(dict(top_fraction=q,gaussians=len(ix),overlaps=int(obs.last['total']),individual_tiles_match_full_selection=True));del pkg;gc.collect()
 dump(d/'receipt.json',dict(at=stamp(),camera=name,rows=rows,optimization_steps=0,scientific_verdict=None));print('SUBSET_RENDER_PASS',rows,flush=True)
if __name__=='__main__':main()
