"""Expanded native atomic-addend audit; no optimizer steps; signal live training on difference."""
import sys,gc
sys.path.insert(0,'/source')
from common import *
import torch,numpy as np
import diff_surfel_rasterization as raster
from gaussian_renderer import render
from rfix_measure import load_scene,module_from
from rfix_loss import Loss
ROOT=OUT/'rfix_speed/rank_refinement/addends'
def main():
 key=sys.argv[1];cfg=json.loads((CFG/'rfix_speed_rank_addends.json').read_text());selection=next(s for s in cfg['states'] if s['state']==key)['rows'];row=next(r for r in json.loads((CFG/'rfix.json').read_text())['states'] if r['key']==key)
 label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target');dest=ROOT/key;dest.mkdir(exist_ok=False)
 # All three renderer variants have identical native forward/backward kernels and ABI.
 # Bind that fact to the source bytes before reusing the observation-only target probe.
 for file in ['cuda_rasterizer/forward.cu','cuda_rasterizer/backward.cu','cuda_rasterizer/auxiliary.h','cuda_rasterizer/config.h','rasterize_points.cu']:
  assert sha(OUT/'rfix/inventory'/label/'source'/file)==sha(OUT/'rfix/inventory/target/source'/file),(label,file)
 mods={'original':module_from(OUT/'rfix/gradient_probe/original/extension/jbgs_rfix_probe_original.so','jbgs_rfix_probe_original'),'fixed':module_from(OUT/'rfix_speed/gradient_probe/fixed/extension/jbgs_rfix_speed_probe_fixed.so','jbgs_rfix_speed_probe_fixed')}
 dump(dest/'lock.json',dict(at=stamp(),rows=selection,code_sha256=sha(__file__),probe_binaries={v:sha(m.__file__) for v,m in mods.items()},native_source_equality=True,scientific_verdict=None))
 g,scene,pipe=load_scene(row);cams={c.image_name:c for c in scene.getTrainCameras()};loss_fn=Loss(row);bg=torch.zeros(3,device='cuda');results=[]
 for name in sorted(set(r['camera'] for r in selection)):
  cam=cams[name];selected=[r for r in selection if r['camera']==name];data=loss_fn.for_view(cam)
  for start in range(0,len(selected),cfg['chunk_size']):
   batch=selected[start:start+cfg['chunk_size']];ids=[r['id'] for r in batch];ids_t=torch.tensor(ids,dtype=torch.int32,device='cuda');arrays=[]
   for variant in ['original','fixed']:
    mod=mods[variant];raster._C=mod;terms=torch.zeros((len(ids),18,cam.image_height*cam.image_width),device='cuda');mod.rf_probe_set(ids_t,terms)
    for p in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:getattr(g,p).grad=None
    pkg=render(cam,g,pipe,bg);loss=loss_fn(cam,pkg,data);loss.backward();torch.cuda.synchronize();arr=terms.cpu().numpy();arrays.append(arr)
    for i,ident in enumerate(ids):
     raw=arr[i].reshape(-1).view('u4');nz=np.flatnonzero(raw);np.savez_compressed(dest/f'{ident}_{variant}.npz',shape=np.array(arr[i].shape),index=nz,values_uint32=raw[nz])
    del terms,loss,pkg;gc.collect();torch.cuda.empty_cache()
   a,b=arrays
   for i,r in enumerate(batch):
    equal=bool(np.array_equal(a[i].view('u4'),b[i].view('u4')));record=dict(r,byte_equal=equal,differing_terms=int(np.count_nonzero(a[i].view('u4')!=b[i].view('u4'))),max_abs=float(np.max(np.abs(a[i].astype('f8')-b[i]))));results.append(record)
    if not equal:dump(OUT/'rfix_speed/REJECTED_ADDENDS.json',dict(at=stamp(),reason='per_pixel_addend_difference',state=key,row=record,scientific_verdict=None))
   dump(dest/'progress.json',dict(at=stamp(),rows=results,scientific_verdict=None));print('ADDENDS',key,len(results),all(r['byte_equal'] for r in results),flush=True)
   del arrays,a,b,arr;gc.collect()
 dump(dest/'result.json',dict(at=stamp(),status='PASS' if all(r['byte_equal'] for r in results) else 'FAIL',rows=results,optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
