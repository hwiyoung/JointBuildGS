"""Observe native per-pixel gradient addends, without changing the locked acceptance result."""
import sys,gc
sys.path.insert(0,'/source')
import numpy as np,torch
import diff_surfel_rasterization as raster
from gaussian_renderer import render
from common import *
from rfix_measure import load_scene,module_from
from rfix_loss import Loss
ROOT=OUT/'rfix'
def main():
 root=ROOT/'gradient_probe';cfg=json.loads((CFG/'rfix.json').read_text());row=next(r for r in cfg['states'] if r['key']=='r8_LoD2_stop');results=json.loads((ROOT/'gradients/r8_LoD2_stop/result.json').read_text());record=next(r for r in results['rows'] if not r['pass_']);name=record['camera'];ids=list(dict.fromkeys(record['parameters'][k]['worst_rows'][0][1] for k in ['_xyz','_features_dc','viewspace_points']));dest=root/'measurement';dest.mkdir(exist_ok=False)
 dump(dest/'lock.json',dict(at=stamp(),camera=name,ids=ids,selection='first failing view; worst xyz, DC feature and screen-position rows',acceptance_use=False,code_sha256=sha(__file__),scientific_verdict=None))
 g,scene,pipe=load_scene(row);cam=next(v for v in scene.getTrainCameras() if v.image_name==name);loss_fn=Loss(row);data=loss_fn.for_view(cam);ids_t=torch.tensor(ids,dtype=torch.int32,device='cuda');bg=torch.zeros(3,device='cuda');arrays=[];gradients=[]
 for variant in ['original','fixed']:
  mod=module_from(root/variant/'extension'/('jbgs_rfix_probe_'+variant+'.so'),'jbgs_rfix_probe_'+variant);raster._C=mod;terms=torch.zeros((len(ids),18,cam.image_height*cam.image_width),device='cuda');mod.rf_probe_set(ids_t,terms)
  for p in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:getattr(g,p).grad=None
  pkg=render(cam,g,pipe,bg);loss=loss_fn(cam,pkg,data);loss.backward();torch.cuda.synchronize();values=terms.cpu().numpy();arrays.append(values);gradients.append({p:getattr(g,p).grad[ids].detach().cpu().numpy() for p in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']});np.savez_compressed(dest/(variant+'.npz'),ids=np.array(ids),per_pixel_terms=values,**gradients[-1]);del terms,loss,pkg;gc.collect();torch.cuda.empty_cache()
 a,b=arrays;dif=abs(a.astype('f8')-b);out=[]
 for i,ident in enumerate(ids):out.append(dict(id=ident,per_pixel_terms_exact_equal=bool(np.array_equal(a[i],b[i])),max_abs_term_difference=float(dif[i].max()),differing_terms=int(np.count_nonzero(dif[i])),original_sum_float64=a[i].sum(axis=1,dtype='f8').tolist(),fixed_sum_float64=b[i].sum(axis=1,dtype='f8').tolist()))
 dump(dest/'result.json',dict(at=stamp(),camera=name,rows=out,acceptance_use=False,gate='original locked gate remains unchanged',interpretation='No scientific verdict. Per-pixel operands and aggregate gradients are reported separately.',scientific_verdict=None));print('PROBE_COMPLETE',out,flush=True)
if __name__=='__main__':main()
