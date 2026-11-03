"""Original twice and fixed once, frozen trained-model loss, no optimizer or updates."""
import sys,gc,time
sys.path.insert(0,'/source')
import torch,numpy as np
import diff_surfel_rasterization as raster
from gaussian_renderer import render
from common import *
from rfix_measure import load_scene
from rfix_unit import extension
from rfix_loss import Loss
ROOT=OUT/'rfix';PARAMS=['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']
def differences(a,b,c):
 assert a.shape==b.shape==c.shape
 jitter=delta=0.;nl2=dl2=0.;different_rows=0;worst=[];finite_ok=True
 for start in range(0,len(a),65536):
  x,y,z=[v[start:start+65536].reshape(len(v[start:start+65536]),-1) for v in [a,b,c]];finite_ok &= bool(np.array_equal(np.isfinite(x),np.isfinite(y)) and np.array_equal(np.isfinite(x),np.isfinite(z)))
  mask=np.isfinite(x)&np.isfinite(y)&np.isfinite(z);xx=np.where(mask,x,0).astype('f8');yb=np.where(mask,y,0);zc=np.where(mask,z,0);da=abs(xx-yb);dc=abs(xx-zc);jitter=max(jitter,float(da.max()));delta=max(delta,float(dc.max()));nl2+=float((xx*xx).sum());dl2+=float((dc*dc).sum());rowdelta=dc.max(axis=1);different_rows+=int((rowdelta>0).sum());take=np.argsort(rowdelta)[-8:];worst.extend([(float(rowdelta[i]),int(start+i)) for i in take if rowdelta[i]>0])
 return dict(jitter_max_abs=jitter,fixed_max_abs=delta,relative_l2=(dl2/max(nl2,1e-300))**.5,different_rows=different_rows,nonfinite_masks_equal=finite_ok,pass_=finite_ok and delta<=jitter,worst_rows=sorted(worst,reverse=True)[:16])
def main():
 cfg=json.loads((CFG/'rfix.json').read_text());row=next(r for r in cfg['states'] if r['key']==sys.argv[1]);key=row['key'];label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target');dest=ROOT/'gradients'/key;dest.mkdir(parents=True,exist_ok=False);loss_fn=Loss(row);files=[Path(__file__),Path(__file__).with_name('rfix_loss.py'),*loss_fn.files]
 for n in row['gradient_views']:files+=list(loss_fn.input_paths(n).values())
 dump(dest/'lock.json',dict(at=stamp(),files={str(p):sha(p) for p in sorted(set(files))},config_sha256=sha(CFG/'rfix.json'),loss='immutable native functions and original weights; GeoGS dynamic depth locked at0.05 in both original run logs; no GT inputs',scientific_verdict=None))
 g,scene,pipe=load_scene(row);cams={v.image_name:v for v in scene.getTrainCameras()};original=raster._C;fixed=extension(label);bg=torch.zeros(3,device='cuda');rows=[]
 for ni,name in enumerate(row['gradient_views']):
  cam=cams[name];data=loss_fn.for_view(cam);grads=[];losses=[];radii=[]
  for variant,mod in [('a',original),('b',original),('fixed',fixed)]:
   raster._C=mod
   for p in PARAMS:getattr(g,p).grad=None
   torch.cuda.empty_cache();pkg=render(cam,g,pipe,bg);loss=loss_fn(cam,pkg,data);loss.backward();torch.cuda.synchronize();losses.append(float(loss.detach()));radii.append(pkg['radii'].cpu().numpy().copy());values={}
   for p in PARAMS:
    grad=getattr(g,p).grad;assert grad is not None,p;values[p]=grad.detach().cpu().numpy().copy()
   assert pkg['viewspace_points'].grad is not None;values['viewspace_points']=pkg['viewspace_points'].grad.detach().cpu().numpy().copy();grads.append(values)
   del loss,pkg;gc.collect()
  metrics={p:differences(grads[0][p],grads[1][p],grads[2][p]) for p in [*PARAMS,'viewspace_points']};rad=bool(np.array_equal(radii[0],radii[1]) and np.array_equal(radii[0],radii[2]));passed=rad and all(v['pass_'] for v in metrics.values());record=dict(camera=name,losses=losses,radii_equal=rad,parameters=metrics,pass_=passed);rows.append(record)
  if not passed:
   ids=sorted(set(i for v in metrics.values() for _,i in v['worst_rows']));np.savez_compressed(dest/(name+'_differing_rows.npz'),ids=np.array(ids,'i8'),xyz=g._xyz.detach().cpu().numpy()[ids],**{v+'_'+p:grads[j][p][ids] for j,v in enumerate(['original_a','original_b','fixed']) for p in [*PARAMS,'viewspace_points']})
  dump(dest/'progress.json',dict(at=stamp(),completed=ni+1,total=30,last=record,pass_so_far=all(r['pass_'] for r in rows),scientific_verdict=None));print('RFIX_GRAD',key,ni+1,passed,[(p,m['fixed_max_abs'],m['jitter_max_abs']) for p,m in metrics.items() if not m['pass_']],flush=True);del grads,data,radii;gc.collect()
 dump(dest/'result.json',dict(at=stamp(),status='PASS' if all(r['pass_'] for r in rows) else 'FAIL',rows=rows,optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
