"""Common input-only fixed ROI and camera metadata, before any saved-model simulation."""
import itertools
import numpy as np
from scipy.spatial import ConvexHull
from matplotlib.path import Path as MPath
from common import *
ROOT=OUT/'screen_sim'
def main():
 c=json.loads((CFG/'screen_sim.json').read_text());lock=json.loads((CFG/'screen_sim_inputs.lock.json').read_text())
 for p,h in lock['files'].items():assert sha(p)==h,p
 b=json.loads(Path(c['boundaries']).read_text());index=json.loads(Path(c['camera_index']).read_text());box=json.loads((OUT/'r8/runs/tg_B173nb_b10_ALS_s0_r8/post30000/inputs/meta.json').read_text())['box'];base=S0/'fork_inputs/s61/B173nb_b10';dest=ROOT/'inputs';dest.mkdir(exist_ok=False)
 uv=np.array(list(itertools.product(*zip(b['lo'],b['hi']))));xy=uv@np.array(b['basis']);corners=np.array([[p[0],p[1],z] for p in xy for z in [box[0][2],box[1][2]]]);records=[]
 for name in c['views']:
  meta=index['views'][name];d=np.load(base/'maps/mvs'/(name+'.npy'));conf=np.load(base/'maps/conf'/(name+'.npy'));H,W=d.shape;K=np.array(meta['K']);M=np.array(meta['W2C']);y,x=np.indices(d.shape);q=np.stack([(x-K[0,2])/K[0,0]*d,(y-K[1,2])/K[1,1]*d,d],-1);world=(q-M[:3,3])@M[:3,:3];p=world[...,:2]@np.array(b['basis']).T;raw=np.isfinite(d)&(d>0);valid=raw&(conf>0);inside=(p>=b['lo']).all(-1)&(p<=b['hi']).all(-1)&(world[...,2]>=box[0][2])&(world[...,2]<=box[1][2]);roi=valid&inside
  cs=corners@M[:3,:3].T+M[:3,3];pts=list(cs[cs[:,2]>=.2])
  for a in range(8):
   for bb in range(a+1,8):
    if np.count_nonzero(corners[a]!=corners[bb]) not in [1,2]:continue
    # All crossing corner segments are inside the convex prism; extra diagonals
    # cannot enlarge its near-clipped convex hull.
    if (cs[a,2]>=.2)!=(cs[bb,2]>=.2):pts.append(cs[a]+(.2-cs[a,2])/(cs[bb,2]-cs[a,2])*(cs[bb]-cs[a]))
  projected=np.zeros(d.shape,bool)
  if len(pts)>=3:
   pts=np.array(pts);screen=pts[:,:2]/pts[:,2:3];screen=screen*np.array([K[0,0],K[1,1]])+np.array([K[0,2],K[1,2]]);hull=screen[ConvexHull(screen).vertices];projected=MPath(np.r_[hull,hull[:1]]).contains_points(np.c_[x.ravel(),y.ravel()],radius=1e-8).reshape(d.shape)
  total=int(projected.sum());missing=int((projected&~valid).sum());r=dict(camera=name,width=W,height=H,K=meta['K'],W2C=meta['W2C'],roi_pixels=int(roi.sum()),projected_box_pixels=total,missing_usable_mvs_pixels=missing,missing_usable_mvs_fraction=missing/total if total else None,raw_depth_missing_pixels=int((projected&~raw).sum()),confidence_rejected_pixels=int((projected&raw&~(conf>0)).sum()),valid_mvs_outside_box_pixels=int((projected&valid&~inside).sum()),roi_outside_projected_pixels=int((roi&~projected).sum()));assert r['roi_outside_projected_pixels']==0
  np.savez_compressed(dest/(name+'.npz'),roi=roi,projected=projected);records.append(r)
 selected=min(records,key=lambda r:(-r['roi_pixels'],r['camera']))['camera'];dump(dest/'index.json',dict(at=stamp(),views=records,mesh_box=box,roi_prism_corners=corners.tolist(),fixed_views=[c['figures']['fixed_heavy_view'],selected],scientific_verdict=None));dump(CFG/'screen_sim_inputs.result.lock.json',dict(at=stamp(),files={str(p):sha(p) for p in sorted(dest.iterdir())},scientific_verdict=None));print('SIM_INPUTS',selected,len(records),flush=True)
if __name__=='__main__':main()
