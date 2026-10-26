"""Geometry-only per-view join coverage, including exact prior-depth XY crop."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from inputs import OUT, PH, S0, SITES, PRIORS, sha, save

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--revision', choices=['join','join_v2'], default='join')
    revision=parser.parse_args().revision
    source=Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r16/scene/colmap_loader.py')
    spec=importlib.util.spec_from_file_location('lt_colmap', source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frame=json.loads(Path('/repo/configs/phd/main_prep_measure_v1/prep_v5.json').read_text())['frame']
    boxes=json.loads((PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/box_ranges.json').read_text())
    angle=np.deg2rad(frame['u_axis_angle_degrees_ccw_from_easting'])
    basis=np.array([[np.cos(angle),np.sin(angle)],[np.sin(angle),-np.cos(angle)]])
    rows=[]
    for site in SITES:
        I=S0/'fork_inputs/s61'/site; sc=I/'scene_LoD2'
        split=json.loads((I/'split.json').read_text())
        ext=module.read_extrinsics_binary(str(sc/'sparse/0/images.bin'))
        by={Path(e.name).stem:e for e in ext.values()}
        cal=json.loads((sc/'jbgs_calibration.json').read_text())
        for prior in PRIORS:
            with np.load(OUT/'checks'/revision/f'{site}__{prior}.npz') as z:
                joined=z['joined'];ev=z['in_eval']
            views=[]
            for name in split['train']:
                lf=I/f'maps/locmap_{prior}'/f'{name}.npy'
                pf=I/f'maps/prior_{prior}'/f'{name}.npy'
                if not pf.exists():pf=I/f'maps/prior_{prior}/raw_depth'/f'{name}.npy'
                loc=np.load(lf);depth=np.load(pf)
                assert loc.shape==depth.shape==(741,1024)
                assert np.equal(loc,loc.astype(np.int64)).all()
                has=(loc>=0)&(loc<len(joined));valid=np.isfinite(depth)&(depth>0)
                assert not (loc>=len(joined)).any()
                yy,xx=np.nonzero(valid)
                q=cal['images'][name];K=np.array(q['K']);H,W=depth.shape
                assert (q['height'],q['width'])==(H,W)
                f=np.float32
                fx=f(f(W/2)*f(2*K[0,0]/W));fy=f(f(H/2)*f(2*K[1,1]/H))
                cx=f(f(f(W/2)*f((2*K[0,2]+1-W)/W))+f((W-1)/2))
                cy=f(f(f(H/2)*f((2*K[1,2]+1-H)/H))+f((H-1)/2))
                e=by[name];w2c=np.eye(4,dtype=np.float32)
                w2c[:3,:3]=module.qvec2rotmat(e.qvec);w2c[:3,3]=e.tvec
                c2w=np.linalg.inv(w2c).astype(np.float64)
                d=depth[yy,xx].astype(np.float64)
                xyz=np.stack([(xx-cx)/fx*d,(yy-cy)/fy*d,d],1)@c2w[:3,:3].T+c2w[:3,3]
                uv=xyz[:,:2]@basis.T;b=boxes[site]
                inside=(uv[:,0]>=b['eval_u'][0])&(uv[:,0]<b['eval_u'][1])&(uv[:,1]>=b['eval_v'][0])&(uv[:,1]<b['eval_v'][1])
                crop=np.zeros_like(valid);crop[yy,xx]=inside
                mapped=np.zeros_like(valid);mapped[has]=joined[loc[has].astype(np.int64)]
                centre_eval=np.zeros_like(valid);centre_eval[has]=ev[loc[has].astype(np.int64)]
                views.append(dict(view=name,pixels=int(depth.size),valid_prior_depth_pixels=int(valid.sum()),
                    patch_depth_pixels=int((valid&has).sum()),joined_depth_pixels=int((valid&has&mapped).sum()),
                    fallback_depth_pixels=int((valid&has&~mapped).sum()),no_patch_depth_pixels=int((valid&~has).sum()),
                    eval_prior_depth_pixels=int((valid&crop).sum()),eval_patch_depth_pixels=int((valid&crop&has).sum()),
                    eval_joined_depth_pixels=int((valid&crop&has&mapped).sum()),
                    eval_fallback_depth_pixels=int((valid&crop&has&~mapped).sum()),
                    eval_no_patch_depth_pixels=int((valid&crop&~has).sum()),
                    centre_eval_patch_pixels=int((valid&has&centre_eval).sum()),
                    centre_eval_joined_pixels=int((valid&has&centre_eval&mapped).sum()),
                    locmap_sha256=sha(lf),prior_depth_sha256=sha(pf)))
            counts={k:sum(v[k] for v in views) for k in views[0] if k.endswith('pixels')}
            ratios=dict(eval_joined_over_all_depth=counts['eval_joined_depth_pixels']/counts['eval_prior_depth_pixels'],
                eval_joined_over_patch_depth=counts['eval_joined_depth_pixels']/counts['eval_patch_depth_pixels'],
                fallback_over_patch_depth=counts['fallback_depth_pixels']/counts['patch_depth_pixels'])
            row=dict(site=site,prior=prior,views=len(views),**counts,**ratios,
                pixel_gate='PASS' if ratios['eval_joined_over_all_depth']>=.95 else 'STOP',
                evaluation_crop='backproject finite positive prior depth with inherited float32 camera projection; frozen XY uv box',
                scientific_verdict=None)
            rows.append(row)
            suffix='' if revision=='join' else '_v2'
            save(OUT/'checks'/('pixels'+suffix)/f'{site}__{prior}.json',dict(summary=row,per_view=views))
            save('/docs/tables/pixel_join'+suffix+'.json',dict(rows=rows,scientific_verdict=None))
            print(site,prior,ratios,row['pixel_gate'],flush=True)

if __name__=='__main__':main()
