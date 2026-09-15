"""CPU replay of native surfel alpha/depth compositing for selected floater rays.

The saved CUDA depth is the numerical validation oracle. This identifies final
render contributors; a subsequent paired optimization isolates the intervention.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from plyfile import PlyData


def read(p):return json.loads(Path(p).read_text())


def columns(v, fields):return np.column_stack([v[k] for k in fields]).astype(np.float64)


def replay(path, view, pixel):
    verts=PlyData.read(path,mmap='r')['vertex'].data
    R=np.array(view['R']);t=np.array(view['t']);K=np.array(view['K']);width,height=view['width'],view['height']
    fx,fy=K[0,0],K[1,1];cx,cy=K[0,2],K[1,2];xpix,ypix=pixel
    grid=np.ceil(np.array([width,height])/16);pieces=[]
    for start in range(0,len(verts),200000):
        vv=verts[start:start+200000];xyz=columns(vv,'xyz');center=xyz@R.T+t
        q=columns(vv,['rot_0','rot_1','rot_2','rot_3']);q/=np.linalg.norm(q,axis=1)[:,None];w,x,y,z=q.T
        scale=np.exp(columns(vv,['scale_0','scale_1']))
        a=np.column_stack([1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)])*scale[:,0,None]
        b=np.column_stack([2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)])*scale[:,1,None]
        a=a@R.T;b=b@R.T
        Tw=np.column_stack([a[:,2],b[:,2],center[:,2]])
        Tu=np.column_stack([fx*a[:,0],fx*b[:,0],fx*center[:,0]])+cx*Tw
        Tv=np.column_stack([fy*a[:,1],fy*b[:,1],fy*center[:,1]])+cy*Tw
        with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
            f=np.array([9,9,-1])/(Tw*Tw@np.array([9,9,-1]))[:,None]
            p=np.column_stack([(f*Tu*Tw).sum(1),(f*Tv*Tw).sum(1)])
            extent=np.sqrt(np.maximum(1e-4,p*p-np.column_stack([(f*Tu*Tu).sum(1),(f*Tv*Tv).sum(1)])))
            radius=np.ceil(np.maximum(extent.max(1),3*.707106))
            low=np.clip(np.trunc((p-radius[:,None])/16),0,grid)
            high=np.clip(np.trunc((p+radius[:,None]+15)/16),0,grid)
            tile=np.array([xpix//16,ypix//16]);valid=(center[:,2]>.2)&np.isfinite(radius)&((tile>=low)&(tile<high)).all(1)
        ids=np.flatnonzero(valid)
        if not len(ids):continue
        Tu,Tv,Tw,p,center=Tu[ids],Tv[ids],Tw[ids],p[ids],center[ids]
        cross=np.cross(xpix*Tw-Tu,ypix*Tw-Tv)
        with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
            s=cross[:,:2]/cross[:,2,None];rho3d=(s*s).sum(1);rho2d=2*((p-np.array(pixel))**2).sum(1)
            depth=(s*Tw[:,:2]).sum(1)+Tw[:,2]
            opacity=1/(1+np.exp(-np.clip(vv['opacity'][ids],-80,80)))
            alpha=np.minimum(.99,opacity*np.exp(-.5*np.minimum(rho3d,rho2d)))
        ok=np.isfinite(depth)&np.isfinite(alpha)&(depth>=.2)&(alpha>=1/255)&(cross[:,2]!=0)
        if ok.any():
            pieces.append(np.column_stack([ids[ok]+start,center[ok,2],depth[ok],alpha[ok],rho3d[ok],rho2d[ok],radius[ids[ok]]]))
    assert pieces
    samples=np.concatenate(pieces);samples=samples[np.argsort(samples[:,1],kind='stable')]
    counterfactuals=[]
    for excluded in cfg.get('counterfactual_ids',[]):
        cf=samples[samples[:,0]!=excluded];cf=cf[np.cumprod(1-cf[:,3])>=.0001]
        cw=np.concatenate([[1.],np.cumprod(1-cf[:-1,3])])*cf[:,3]
        counterfactuals.append(dict(disabled_gaussian_id=excluded,expected_depth=float(cw@cf[:,2]/cw.sum()),
                                   accumulated_alpha=float(cw.sum()),contributors=len(cf)))
    following=np.cumprod(1-samples[:,3]);keep=following>=.0001;samples=samples[keep]
    trans=np.concatenate([[1.],np.cumprod(1-samples[:-1,3])]);weights=trans*samples[:,3];normalized=weights/weights.sum()
    estimated=float(normalized@samples[:,2]);median=float(samples[np.flatnonzero(trans>.5)[-1],2])
    top=np.argsort(normalized)[::-1][:20];top_ids=samples[top,0].astype(int)
    theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
    pos=columns(verts[top_ids],'xyz');display=pos.copy();display[:,:2]=pos[:,:2]@basis.T;display[:,1]*=-1
    rows=[dict(id=int(i),weight=float(normalized[k]),alpha=float(samples[k,3]),intersection_depth=float(samples[k,2]),
               center_depth=float(samples[k,1]),screen_radius=float(samples[k,6]),filter_dominant=bool(samples[k,5]<samples[k,4]),
               center_display=display[j].tolist(),scale=np.exp(columns(verts[[i]],['scale_0','scale_1']))[0].tolist())
          for j,(k,i) in enumerate(zip(top,top_ids))]
    return dict(expected_depth=estimated,median_depth=median,accumulated_alpha=float(weights.sum()),contributors=len(samples),
                depth_quantiles=np.quantile(samples[:,2],[0,.1,.5,.9,1]).tolist(),top=rows,
                top20_weight=float(normalized[top].sum()),
                weighted_depth_std=float(np.sqrt(normalized@((samples[:,2]-estimated)**2))),counterfactuals=counterfactuals)


cfg=read('/config.json');root=Path(cfg['root']);legacy=Path(cfg['r1run']);out=Path('/out')
support=read('/support/depth_support.json');rows=[]
paths={'mvs':legacy/'refinement/model/jbgs_complete/iteration_30000/point_cloud.ply',
       'local_prior0':root/'R1/local_prior0/model/jbgs_complete/iteration_30000/point_cloud.ply',
       'da3':root/'R1/da3/model/jbgs_complete/iteration_30000/point_cloud.ply'}
for view in support['selected'][:cfg.get('max_views',3)]:
    for branch,path in paths.items():
        if branch not in cfg.get('branches',paths):continue
        replayed=replay(path,view['camera'],view['pixel']);reference=view['depth'][branch]
        error=abs(replayed['expected_depth']-reference)
        row=dict(camera=view['name'],pixel=view['pixel'],branch=branch,saved_cuda_depth=reference,
                 absolute_replay_error_m=error,parity_pass=error<cfg['depth_parity_tolerance_m'],**replayed)
        rows.append(row);(out/'partial.json').write_text(json.dumps(rows,indent=2))
        print(view['name'],branch,'saved',reference,'replayed',replayed['expected_depth'],'error',error,flush=True)
result=dict(status='PASS_CPU_SAVED_DEPTH_PARITY' if all(r['parity_pass'] for r in rows) else 'PARTIAL_CPU_REPLAY_PARITY',
            scientific_verdict=None,rows=rows,config=cfg,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            limitation='Final-frame splat contribution attribution only; counterfactual training attribution is separate.')
(out/'receipt.json').write_text(json.dumps(result,indent=2))
