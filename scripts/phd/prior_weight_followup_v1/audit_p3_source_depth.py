"""Evaluation-only same-pixel prior/MVS camera-Z comparison at observed P3 roof points."""
import hashlib,json,sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,'/repo/src/phd/geogs_mvs_pgsr_v1')
from mvs_depth import load_view_depth
assert Path('/.dockerenv').exists()
p=Path('/payload');out=Path('/out');cfg=json.loads((out/'config.json').read_text());g=p/cfg['global_root'];files={}
def record(path):files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return path
def stats(x):
 x=np.asarray(x,dtype=float);a=np.abs(x)
 return dict(n=len(x),mae=float(a.mean()),median_abs=float(np.median(a)),p95_abs=float(np.quantile(a,.95)),signed_mean=float(x.mean()),within_50cm=float((a<.5).mean()),over_10m=float((a>10).mean()))
refpath=record(p/cfg['bundle'].rsplit('/attempt.',1)[0]/'verification.jCU13Dtc/P3_paired_surface.npz')
ref=np.load(refpath);x=ref['reference_points'];roof=ref['roi_target_roof'];binding=json.loads(record(g/'inputs_v2/P3/bindings.json').read_text());result=[]
for index in [4,119]:
 c=binding['train'][index];depth,valid,_=load_view_depth(c,verify_rgb=False,depth_path=record(g/'inputs_v2/P3'/c['local_depth']))
 prior_path=record(p/cfg['base_root']/('inputs/P3/prior/raw_depth/'+Path(c['name']).stem+'.npy'))
 prior=cv2.resize(np.load(prior_path),(c['width'],c['height']),interpolation=cv2.INTER_LINEAR)
 xc=x@np.array(c['R']).T+np.array(c['t']);uvh=xc@np.array(c['K']).T;uv=np.rint(uvh[:,:2]/uvh[:,2:]).astype(int)
 inside=(xc[:,2]>0)&(uv[:,0]>=0)&(uv[:,1]>=0)&(uv[:,0]<c['width'])&(uv[:,1]<c['height']);ids=np.flatnonzero(inside)
 pix=uv[ids,1]*c['width']+uv[ids,0];order=np.lexsort((xc[ids,2],pix));ordered=ids[order];sp=pix[order]
 selected=ordered[np.r_[True,sp[1:]!=sp[:-1]]];selected=selected[roof[selected]]
 xx,yy=uv[selected,0],uv[selected,1];ok=valid[yy,xx]&np.isfinite(prior[yy,xx])&(prior[yy,xx]>0)
 selected=selected[ok];xx,yy=uv[selected,0],uv[selected,1];truth=xc[selected,2]
 a=prior[yy,xx]-truth;b=depth[yy,xx]-truth
 result.append(dict(camera=c['name'],n=len(selected),prior=stats(a),mvs=stats(b),
  mvs_better_by_more_than_10cm=float((np.abs(b)+.1<np.abs(a)).mean()),prior_better_by_more_than_10cm=float((np.abs(a)+.1<np.abs(b)).mean())))
 np.savez_compressed(out/('P3_'+Path(c['name']).stem[-6:]+'_source_depth.npz'),reference_raw_rows=ref['reference_raw_rows'][selected],pixels=uv[selected],gt_camera_z=truth,prior_error=a,mvs_error=b)
report=dict(status='PASS_P3_PAIRED_SOURCE_DEPTH_DIAGNOSTIC',scientific_verdict=None,
 scope='GT-selected roof points, rounded RGB pixels; frontmost observed GT per pixel within the reference crop; not complete visibility or original-surface accuracy',
 gt_used_for_weighting=False,views=result,inputs=files,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(out/'p3_source_depth.json').write_text(json.dumps(report,indent=2));print(json.dumps(result,indent=2))
