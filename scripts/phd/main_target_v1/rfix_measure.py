"""Eight saved-state render parity, per-view burst identities and load; no optimization."""
import sys,os,time,gc,importlib.util,math
sys.path.insert(0,'/source')
import torch,numpy as np
from argparse import ArgumentParser
import diff_surfel_rasterization as raster
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *
from rfix_unit import extension
from screen_sim_render_r3 import Observer
ROOT=OUT/'rfix'
def module_from(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Diagnostic(Observer):
 def rasterize_gaussians(self,*args):
  v=super().rasterize_gaussians(*args);N=args[1].shape[0];H,W=int(args[12]),int(args[13]);self.rawmaps=v[2].detach();self.tiles=None
  if self.account:
   burst=v[3]>math.hypot(W,H);ids=burst.nonzero().flatten();geom=v[4];off=0;values={}
   for name,size,dim,dt in [('depth',4,1,torch.float32),('clamped',3,3,None),('radius',4,1,torch.int32),('xy',8,2,torch.float32),('mat',36,9,torch.float32),('no',16,4,torch.float32),('color',12,3,torch.float32),('tiles',4,1,torch.int32)]:
    off=(off+127)//128*128
    if name in ['mat','xy','tiles']:values[name]=geom[off:off+N*size].view(dt).reshape(N,dim)[ids].cpu().numpy()
    off+=N*size
   values['id']=ids.cpu().numpy();values['radius']=v[3][ids].cpu().numpy();values['sum_w']=self.sum[ids].cpu().numpy();values['max_w']=self.maximum[ids].cpu().numpy();self.burst=values
  return v
def load_scene(row):
 parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser);args=parser.parse_args(['-s','/scene','-m',row['model'],'--eval','-r','1','--data_device','cpu']);safe_state(False);g=GaussianModel(args.sh_degree);dataset=lp.extract(args)
 if row['family']=='geogs':dataset.sparse_dir_name='sparse_lod'
 scene=Scene(dataset,g,load_iteration=row['scene_iteration'],shuffle=False);g.load_ply(row['ply']);return g,scene,pp.extract(args)
def compare(a,b,c):
 rows={}
 for k in a:
  x,y,z=a[k],b[k],c[k];assert x.shape==y.shape==z.shape
  if x.dtype.kind in 'biu':eq=bool(np.array_equal(x,z));rows[k]=dict(max_abs=0 if eq else int(np.max(np.abs(x.astype('i8')-z))),jitter_max_abs=0,pass_=eq);continue
  finite=np.isfinite(x)&np.isfinite(y)&np.isfinite(z);same=bool(np.array_equal(np.isnan(x),np.isnan(y)) and np.array_equal(np.isnan(x),np.isnan(z)) and np.array_equal(np.isposinf(x),np.isposinf(z)) and np.array_equal(np.isneginf(x),np.isneginf(z)))
  jitter=float(np.max(np.abs(x[finite].astype('f8')-y[finite]))) if finite.any() else 0.;delta=float(np.max(np.abs(x[finite].astype('f8')-z[finite]))) if finite.any() else 0.
  rows[k]=dict(max_abs=delta,jitter_max_abs=jitter,nonfinite_masks_equal=same,nonfinite_count=int((~finite).sum()),pass_=same and delta<=jitter)
 return rows
@torch.no_grad()
def main():
 key=sys.argv[1];cfg=json.loads((CFG/'rfix.json').read_text());assert sha(CFG/'rfix.json')==json.loads((CFG/'rfix.lock.json').read_text())['config_sha256'];row=next(r for r in cfg['states'] if r['key']==key);label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target');assert json.loads((ROOT/'units'/label/'result.json').read_text())['status']=='PASS'
 dest=ROOT/'states'/key;dest.mkdir(parents=True,exist_ok=False);(dest/'bursts').mkdir();(dest/'fixed_views').mkdir();dump(dest/'lock.json',dict(at=stamp(),files={str(p):sha(p) for p in [Path(__file__),Path(__file__).with_name('rfix_unit.py'),Path(__file__).with_name('screen_sim_render_r3.py'),ROOT/'builds'/label/'extension'/('jbgs_rfix_'+label+'.so')]},scientific_verdict=None))
 g,scene,pipe=load_scene(row);cams=sorted(scene.getTrainCameras(),key=lambda x:x.image_name);assert [x.image_name for x in cams]==cfg['views'];N=len(g._xyz);bg=torch.zeros(3,device='cuda');original=raster._C;fixed=extension(label)
 weights_path=OUT/'screen_sim/states'/key/'account_build/screen_sim_weights.so';weights=module_from(weights_path,'screen_sim_weights');obs=Diagnostic(original,weights,N);obs.tolerance=1e-5;obs.sum=torch.zeros(N,device='cuda',dtype=torch.float64);obs.roi_sum=torch.zeros_like(obs.sum);obs.maximum=torch.zeros(N,device='cuda')
 groups=dict(np.load(OUT/'screen_sim/states'/key/'groups.npz',allow_pickle=False));xyz=g._xyz.detach().cpu().numpy();xyz_t=g._xyz.detach();records=[];allpass=True
 for vi,cam in enumerate(cams):
  roi=torch.zeros(cam.image_height,cam.image_width,dtype=torch.bool,device='cuda');obs.roi=roi;copies=[];perf=[];rawburst=None
  for variant,mod in [('original_a',original),('original_b',original),('fixed',fixed)]:
   obs.original=mod;obs.account=variant=='original_a';obs.sum.zero_();obs.roi_sum.zero_();obs.maximum.zero_();raster._C=obs;torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.monotonic();pkg=render(cam,g,pipe,bg);torch.cuda.synchronize();elapsed=time.monotonic()-start
   perf.append(dict(variant=variant,**obs.last,seconds_including_accounting=elapsed,peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved()));data={k:v.detach().cpu().numpy().copy() for k,v in pkg.items() if torch.is_tensor(v) and k!='viewspace_points'};data['raw_auxiliary_maps']=obs.rawmaps.cpu().numpy().copy();copies.append(data)
   if variant=='original_a':rawburst=obs.burst
   obs.rawmaps=None;del pkg;gc.collect()
  diffs=compare(*copies);passed=all(v['pass_'] for v in diffs.values());allpass &= passed
  if not passed:np.savez_compressed(dest/(cam.image_name+'_parity_failure.npz'),**{variant+'_'+k:v for variant,data in zip(['a','b','fixed'],copies) for k,v in data.items()})
  ids=rawburst['id'];T=rawburst.pop('mat').reshape(-1,3,3);Tw=T[:,2,:];depth_span=3*np.sqrt(Tw[:,0]**2+Tw[:,1]**2);d=(9*Tw[:,0]**2+9*Tw[:,1]**2)-Tw[:,2]**2
  hom=torch.cat([xyz_t[ids],torch.ones((len(ids),1),device='cuda')],1);camcoords=hom@cam.world_view_transform;clip=hom@cam.full_proj_transform;proj=((clip[:,:2]/clip[:,3:4]+1)*torch.tensor([cam.image_width,cam.image_height],device='cuda')-1)/2;proj=proj.cpu().numpy();depth=camcoords[:,2].cpu().numpy();delta=np.maximum(np.maximum(-proj,proj-np.array([cam.image_width-1,cam.image_height-1])),0);outside=np.linalg.norm(delta,axis=1);dist=np.linalg.norm(xyz[ids]-cam.camera_center.cpu().numpy(),axis=1)
  rawburst.update(center_depth=depth,center_pixel=proj,outside_distance_px=outside,center_inside=(outside==0),disc_nearest_depth=Tw[:,2]-depth_span,disc_farthest_depth=Tw[:,2]+depth_span,aabb_d=d,tag=groups['tag'][ids],xy_bin=groups['xy'][ids],height_bin=groups['height'][ids],camera_distance_m=dist,within_camera30=dist<=30,nearest_camera_distance_m=groups['nearest_camera_distance_m'][ids]);np.savez_compressed(dest/'bursts'/(cam.image_name+'.npz'),**rawburst)
  grouped=[];code=rawburst['tag'].astype('i8')*32+rawburst['xy_bin']*8+rawburst['height_bin']*2+rawburst['within_camera30'].astype('i8')
  for value in np.unique(code):
   mask=code==value;ix=np.flatnonzero(mask)[0];grouped.append(dict(tag=int(rawburst['tag'][ix]),xy=int(rawburst['xy_bin'][ix]),height=int(rawburst['height_bin'][ix]),camera30=bool(rawburst['within_camera30'][ix]),pairs=int(mask.sum()),overlaps=int(rawburst['tiles'][mask].astype('i8').sum()),color_contributing=int((rawburst['sum_w'][mask]>0).sum()),sum_w=float(rawburst['sum_w'][mask].sum())))
  rec=dict(camera=cam.image_name,width=cam.image_width,height=cam.image_height,pairs=len(ids),burst_overlaps=int(rawburst['tiles'].astype('i8').sum()),burst_color_contributors=int((rawburst['sum_w']>0).sum()),burst_grouped=grouped,performance=perf,comparison=diffs,pass_=passed);records.append(rec)
  if cam.image_name in ['DJI_20241217102535_0020_D','DJI_20241217091133_0109_D']:np.savez_compressed(dest/'fixed_views'/(cam.image_name+'.npz'),before=copies[0]['render'],after=copies[2]['render'],gt=cam.original_image.cpu().numpy())
  dump(dest/'progress.json',dict(at=stamp(),completed=vi+1,views=len(cams),render_pass_so_far=allpass,last=rec,scientific_verdict=None));print('RFIX_RENDER',key,vi+1,len(cams),perf[0]['overlaps'],perf[2]['overlaps'],passed,flush=True)
  del copies,rawburst,hom,camcoords,clip,proj,roi;gc.collect()
 before=sum(r['performance'][0]['overlaps'] for r in records);after=sum(r['performance'][2]['overlaps'] for r in records)
 dump(dest/'result.json',dict(at=stamp(),status='PASS' if allpass and after<before else 'FAIL',records=records,gaussians=N,original_overlaps=before,fixed_overlaps=after,optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
