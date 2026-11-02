"""Read-only saved-state forward. Original raster math, no training/optimizer."""
import sys,gc
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
from plyfile import PlyData
from scipy.special import expit
import diff_surfel_rasterization as raster
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *
from r8_record_hooks import load_extension
from cause_r8_render import ObservedRasterizer
from cause_r8_spatial import bins
ROOT=OUT/'r8_recorded_continue';DEST=ROOT/'heavy'
@torch.no_grad()
def main():
 family=sys.argv[1];conf=json.loads((CFG/'r8_heavy.json').read_text());lock=json.loads((CFG/'r8_heavy.lock.json').read_text())
 assert sha(__file__)==lock['files'][__file__];assert sha(CFG/'r8_heavy.json')==lock['files']['/cfg/r8_heavy.json']
 b=json.loads(Path(conf['boundaries']).read_text());rows=[r for r in conf['rows'] if r['family']==family];first=rows[0]
 parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
 args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2'),'-m',first['model'],'--eval','-r','1','--data_device','cpu'])
 safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=first['scene_iteration'],shuffle=False)
 pipe=pp.extract(args);bg=torch.zeros(3,device='cuda');cams={c.image_name:c for c in scene.getTrainCameras()};assert len(cams)==203
 mod=load_extension();obs=ObservedRasterizer(mod);raster._C=obs;mod.jbgs_set_guard(conf['readout_capacity_fraction'])
 if family=='r8':
  with np.load(OUT/'r8/stage1/B173nb_b10_LoD2/seeds.npz') as seed:seed_origin=seed['origin'].copy()
 else:seed_origin=np.load(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2/sparse/0/origin.npy')
 for row in rows:
  dest=DEST/'states'/row['key'];dest.mkdir(parents=True,exist_ok=False)
  for k in ['ply','snapshot','checkpoint']:
   if row[k]:assert sha(row[k])==lock['files'][row[k]],row[k]
  g.load_ply(row['ply']);v=PlyData.read(row['ply'])['vertex'].data;xyz=np.column_stack([v[k] for k in ['x','y','z']]);ids=v['init_id'].astype('i8');origin=seed_origin[ids].astype('i1');assert np.array_equal(origin,v['origin'])
  if row['snapshot']:
   with np.load(row['snapshot']) as s:
    assert np.array_equal(s['xyz'],xyz) and np.array_equal(s['init_id'],ids);tag=s['target_tag'].copy();released=s['target_released_at'].copy()
  elif row['checkpoint']:
   cp=torch.load(row['checkpoint'],map_location='cpu');assert np.array_equal(cp['model'][1].detach().numpy(),xyz);assert np.array_equal(cp['init_id'].numpy(),ids)
   meta=cp['target_r6']['meta'];tag=meta['target_tag'].numpy().copy();released=meta['target_released_at'].numpy().copy();del cp,meta
  else:tag=origin.copy();released=np.full(len(ids),-1,dtype='i4')
  fine=tag.astype('i1');fine[(tag==2)&(released!=100)]=3;x,h=bins(xyz,b);group=fine.astype('i4')*16+x*4+h
  arrays=dict(xyz=xyz,init_id=ids,origin=origin,tag=tag,released_at=released,group=group,longest_axis=np.exp(np.column_stack([v['scale_0'],v['scale_1']])).max(1),opacity=expit(v['opacity']))
  np.savez_compressed(dest/'arrays.npz',**arrays);del v,arrays;gc.collect()
  views=[]
  for name in row['cameras']:
   torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();cam=cams[name];pkg=render(cam,g,pipe,bg);stats=mod.jbgs_get_guard();tiles=obs.last['tiles'];radius=pkg['radii'].cpu().numpy();assert len(tiles)==len(ids) and int(tiles.astype('i8').sum())==stats[1]
   parity=None
   if row['key']=='r8_14031_stop':parity=ROOT/'stop_diagnostic/renders/tiles'/(name+'.npz')
   if family=='base':parity=OUT/'r8_lod2_cause/renders/base_LoD2_30000/tiles'/(name+'.npz')
   if parity:
    with np.load(parity) as prev:assert np.array_equal(tiles,prev['tiles'])
   np.savez_compressed(dest/(name+'.npz'),tiles=tiles,radius=radius,rgb=pkg['render'].cpu().numpy(),camera_center=cam.camera_center.cpu().numpy())
   rec=dict(camera=name,gaussians=len(ids),overlaps=int(stats[1]),binning_bytes=int(stats[2]),positive_overlap_gaussians=int(np.count_nonzero(tiles)),camera_center=cam.camera_center.cpu().tolist(),replay_individual_tiles_equal=True if parity else None,peak_allocated=torch.cuda.max_memory_allocated(),peak_reserved=torch.cuda.max_memory_reserved(),full_forward=True,optimization_steps=0)
   views.append(rec);print('HEAVY_RENDER',row['key'],name,stats[1],flush=True);del pkg,tiles,radius;gc.collect()
  dump(dest/'render.json',dict(state=row,views=views,scientific_verdict=None))
 dump(DEST/(family+'_render_complete.json'),dict(at=stamp(),states=len(rows),optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
