"""All training-view PSNR and compatible-depth diagnostic, no reference geometry."""
import json
import runpy
import sys
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,'/source')
import jbgs_judgment as JJ
from utils.image_utils import psnr

cut=sys.argv.index('--');own=sys.argv[1:cut];train=sys.argv[cut+1:]
ARGS={own[i].lstrip('-'):own[i+1] for i in range(0,len(own),2)}
original=JJ.Judgment.__init__

def wrapped(self,args,opt,scene,gaussians,*a,**kw):
    original(self,args,opt,scene,gaussians,*a,**kw)
    gaussians.load_ply(ARGS['readout_ply'])
    # Deliberately no update_E/floor call: evaluate the saved checkpoint bytes.
    rows=[];residuals=[]
    with torch.no_grad():
        for cam in self.train_cams:
            name=cam.image_name;pkg=self.render_fn(cam,gaussians,self.pipe,self.background)
            im=pkg['render'].clamp(0,1);target=cam.original_image.to(im.device).clamp(0,1)
            score=float(psnr(im[None],target[None]).mean())
            D=pkg['surf_depth'].squeeze(0);P,M,A=self.P[name],self.M[name],self.A[name]
            loc=self.lt_locations[name].long();tab=self.lt_values
            on=(loc>=0)&(loc<len(tab['v_prior']))&torch.isfinite(P)&(P>0)
            yy,xx=torch.where(on);ids=loc[on]
            proj=cam.projection_matrix.T;H,W=D.shape
            fx,fy=proj[0,0]*W/2,proj[1,1]*H/2
            cx,cy=proj[0,2]*W/2+(W-1)/2,proj[1,2]*H/2+(H-1)/2
            ray=torch.stack(((xx-cx)/fx,(yy-cy)/fy,torch.ones_like(xx,dtype=D.dtype)),1)
            ray=torch.nn.functional.normalize(ray@cam.world_view_transform.inverse()[:3,:3],dim=1)
            co=(ray*tab['normal'][ids].to(D.dtype)).sum(1).abs().clamp_min(.25)
            sp=tab['sigma_prior'][ids]/co;sm=tab['sigma_mvs'][ids]/co
            obs=torch.isfinite(M[on])&(M[on]>0)&(A[on]>0)&torch.isfinite(tab['v_mvs'][ids])
            explained=obs&((P[on]-M[on]).abs()<=3*torch.sqrt(sp.square()+sm.square()))
            if bool(explained.any()):
                p,m,sp1,sm1=P[on][explained],M[on][explained],sp[explained],sm[explained]
                precision=sp1.reciprocal().square()+sm1.reciprocal().square()
                mean=(p/sp1.square()+m/sm1.square())/precision
                sigma_mean=precision.rsqrt()
                normalized=(D[on][explained]-mean).abs()/sigma_mean
                assert torch.isfinite(normalized).all()
                residuals.append(normalized.cpu().numpy())
            rows.append(dict(view=name,psnr_db=score,compatible_pixels=int(explained.sum())))
    x=np.concatenate(residuals) if residuals else np.zeros(0)
    timing={}
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
        ev=EventAccumulator(str(Path(ARGS['readout_ply']).parents[2]),size_guidance={'scalars':0});ev.Reload()
        samples=ev.Scalars('iter_time')
        vals=np.array([x.value for x in samples],np.float64)
        timing=dict(samples=len(vals),mean_ms=float(vals.mean()),median_ms=float(np.median(vals)),
            p95_ms=float(np.percentile(vals,95)),definition='inherited CUDA iter_start to iter_end; excludes logging, checkpoint and readout; includes opt-in gradient observation on final 100 iterations')
    except (ImportError,KeyError) as exc:
        timing=dict(status='UNAVAILABLE',reason=str(exc))
    record=dict(training_psnr_mean_db=float(np.mean([r['psnr_db'] for r in rows])),views=rows,iteration_time=timing,
        compatible_pixels=len(x),compatible_depth_normalized_abs_median=float(np.median(x)) if len(x) else None,
        definition='compatible: |Dp-Dm| <= 3*sqrt(sp_ray^2+sm_ray^2); mean precision weights 1/s^2; normalization sqrt(1/(1/sp_ray^2+1/sm_ray^2)); all compatible training pixels',
        psnr_definition='stage-1 postprocessing definition: per-image PSNR from RGB mean squared error, then arithmetic mean across every training camera',
        GT_geometry_used=False,checkpoint_modified=False,scientific_verdict=None)
    Path(ARGS['readout_json']).write_text(json.dumps(record,indent=2)+'\n')
    print('calibration all-view metrics',record['training_psnr_mean_db'],record['compatible_depth_normalized_abs_median'],flush=True)
    raise SystemExit(0)

JJ.Judgment.__init__=wrapped
sys.argv=['train.py']+train;runpy.run_path('/source/train.py',run_name='__main__')
