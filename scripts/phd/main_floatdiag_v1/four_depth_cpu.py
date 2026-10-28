"""Exact full-mesh first hits on the same full-resolution camera pixel rays."""
import argparse
import json
import csv
import gzip
import numpy as np
import open3d as o3d
import cv2
from common import *
from recount import load_eval

def stats(x):
    v=np.asarray(x);v=v[np.isfinite(v)]
    return dict(n=len(v),mean=float(v.mean()) if len(v) else None,
        q25=float(np.quantile(v,.25)) if len(v) else None,median=float(np.median(v)) if len(v) else None,
        q75=float(np.quantile(v,.75)) if len(v) else None,p90=float(np.quantile(v,.9)) if len(v) else None,
        min=float(v.min()) if len(v) else None,max=float(v.max()) if len(v) else None)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    cases=[c for c in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if c['site']==a.site]
    choices={c['case']:c['main'] for c in json.loads((CFG/f'photos_{a.site}_{a.prior}.json').read_text())['cases']}
    names=sorted({c['view'] for c in choices.values() if c});e,_=load_eval(a.site,a.prior)
    records=[]
    for result in [f'nojudge_{a.prior}_s0',f'lt_dynnow_{a.prior}_s0']:
        source,receipt=mesh_path(a.site,result,a.prior);actual_sha=sha(source)
        assert actual_sha==receipt['mesh_sha256'] if 'mesh_sha256' in receipt else actual_sha==receipt['sha256']
        print('full mesh raycast',a.site,result,flush=True)
        mesh=o3d.io.read_triangle_mesh(str(source));scene=o3d.t.geometry.RaycastingScene(nthreads=8)
        scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh));del mesh
        folder=OUT/'four_depths'/a.site/result;unit_arrays=[]
        for name in names:
            with np.load(folder/(name+'.npz')) as f:raw={k:f[k] for k in f.files}
            H,W=raw['surf_depth'].shape;K=raw['intrinsic'];ext=raw['world_to_camera'];inv=np.linalg.inv(ext)
            yy,xx=np.mgrid[:H,:W];camray=np.stack(((xx-K[0,2])/K[0,0],(yy-K[1,2])/K[1,1],np.ones_like(xx)),axis=-1)
            directions=camray@inv[:3,:3].T
            rays=np.concatenate([np.broadcast_to(inv[:3,3],directions.shape),directions],axis=-1).astype(np.float32)
            cache=folder/(name+'_mesh.npz')
            if cache.exists():
                with np.load(cache) as f:
                    assert np.array_equal(f['world_to_camera'],ext) and np.array_equal(f['intrinsic'],K)
                    hit=f['mesh_first_depth']
            else:
                hit=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy();hit[~np.isfinite(hit)]=np.nan
            finite=np.flatnonzero(np.isfinite(hit.ravel()))
            check_ids=finite[::max(1,len(finite)//1000)]
            flat=rays.reshape(-1,6);pts=flat[check_ids,:3]+hit.ravel()[check_ids,None]*flat[check_ids,3:]
            camz=(pts@ext[:3,:3].T+ext[:3,3])[:,2]
            unit_error=float(np.max(np.abs(camz-hit.ravel()[check_ids]))) if len(check_ids) else None
            mesh_error=float(scene.compute_distance(o3d.core.Tensor(pts.astype(np.float32))).numpy().max()) if len(pts) else None
            assert unit_error is None or unit_error<.001,(name,'camera-Z units',unit_error)
            assert mesh_error is None or mesh_error<.001,(name,'first-hit point not on source mesh',mesh_error)
            save(folder/(name+'_ray_check.json'),dict(view=name,sample_hits=len(check_ids),maximum_camera_z_roundtrip_m=unit_error,
                maximum_hit_to_mesh_m=mesh_error,full_image_hit_pixels=len(finite),scientific_verdict=None))
            np.savez_compressed(folder/(name+'_mesh.npz'),mesh_first_depth=hit,world_to_camera=ext,intrinsic=K)
            with np.load(OUT/'diagnostics'/a.site/f'lt_dynnow_{a.prior}_s0'/(name+'.npz')) as f:d={k:f[k] for k in f.files}
            keep=d['pixel_type']==0;y=d['pixel_y'][keep];x=d['pixel_x'][keep];ids=d['patch_id'][keep]
            # The original per-result diagnostic archive contains only that
            # result's floating/roof pixels. Read the unchanged source maps to
            # retain EVERY dynnow floating pixel, even if nojudge classified it
            # as another type. Sigma and masks are camera/input properties.
            maps={}
            for term,key in [('prior',f'prior_{a.prior}'),('mvs','mvs')]:
                path=S0/'fork_inputs/s61'/a.site/'maps'/key
                if (path/'raw_depth').exists():path=path/'raw_depth'
                target=np.load(path/(name+'.npy')).astype(np.float32)
                if target.shape!=(H,W):target=cv2.resize(target,(W,H),interpolation=cv2.INTER_NEAREST)
                maps[term]=target
            values=dict(pixel_y=y,pixel_x=x,patch_id=ids,surf_depth=raw['surf_depth'][y,x],mesh_first_depth=hit[y,x],
                opacity_05=raw['opacity_05'][y,x],opacity_mean=raw['opacity_mean'][y,x],alpha=raw['alpha'][y,x],
                prior_r_sigma=(raw['surf_depth'][y,x]-maps['prior'][y,x])/d['sigma_prior'][keep],
                mvs_r_sigma=(raw['surf_depth'][y,x]-maps['mvs'][y,x])/d['sigma_mvs'][keep],has_mvs=d['has_mvs'][keep])
            if result.startswith('lt_dynnow'):
                assert np.array_equal(values['prior_r_sigma'],d['prior_r_sigma'][keep])
                assert np.array_equal(values['mvs_r_sigma'],d['mvs_r_sigma'][keep],equal_nan=True)
            values['mvs_r_sigma'][~values['has_mvs']]=np.nan
            values['surf_minus_mesh']=values['surf_depth']-values['mesh_first_depth']
            np.savez_compressed(folder/(name+'_paired.npz'),**values)
            unit_arrays.append(values)
            for c in cases:
                choice=choices[c['id']]
                if choice is None or choice['view']!=name:continue
                b=np.array(c['bbox']);xy=e['centre'][ids,:2]
                take=((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)
                casefolder=OUT/'four_depths/cases'/c['id'];casefolder.mkdir(parents=True,exist_ok=True)
                selected={k:v[take] for k,v in values.items()}
                np.savez_compressed(casefolder/(result+'.npz'),**selected)
                with gzip.open(casefolder/(result+'.csv.gz'),'wt',newline='') as f:
                    writer=csv.writer(f,lineterminator='\n');writer.writerow(selected)
                    for row in zip(*selected.values()):
                        writer.writerow(['' if isinstance(v,(float,np.floating)) and not np.isfinite(v) else v for v in row])
                records.append(summarize(a.site,result,c['id'],name,values,take))
        for c in cases:
            if choices[c['id']] is None:
                records.append(dict(site=a.site,result=result,scope=c['id'],status='UNAVAILABLE',
                    reason='No locked main photo passes 90% visibility; main-view pixels cannot be defined',scientific_verdict=None))
        # Each unique (view,pixel) is counted once; scope is the selected main views only.
        if unit_arrays:
            values={k:np.concatenate([x[k] for x in unit_arrays]) for k in unit_arrays[0]}
            records.append(summarize(a.site,result,'단위·선택된 주 시점','unique main views',values,np.ones(len(values['patch_id']),bool)))
        if (folder/'mesh_receipt.json').exists():
            previous=json.loads((folder/'mesh_receipt.json').read_text());assert previous['sha256']==actual_sha
        else:
            save(folder/'mesh_receipt.json',dict(at=now(),path=str(source),sha256=actual_sha,
                raycast='Open3D full exact scored mesh, no crop or decimation; camera Z depth',scientific_verdict=None))
        del scene
    from reduce_diagnostics import table
    keys=list(dict.fromkeys(k for r in records for k in r))
    records=[{k:r.get(k) for k in keys} for r in records]
    table(DOC/'tables'/f'four_depths_{a.site}_{a.prior}',records,'같은 화소 광선의 네 깊이 · m')
    print(a.site,'four-depth pairing PASS',flush=True)

def summarize(site,result,scope,view,v,m):
    return dict(site=site,result=result,scope=scope,view=view,status='MEASURED',floating_pixels=int(m.sum()),
        patches=int(len(np.unique(v['patch_id'][m]))),sample_status='표본 부족' if len(np.unique(v['patch_id'][m]))<100 else 'PASS',
        mesh_miss=int((m&~np.isfinite(v['mesh_first_depth'])).sum()),
        opacity_05_not_reached=int((m&~np.isfinite(v['opacity_05'])).sum()),
        **{k:stats(v[k][m]) for k in ['surf_depth','mesh_first_depth','opacity_05','opacity_mean','surf_minus_mesh','prior_r_sigma']},
        mvs_r_sigma=stats(v['mvs_r_sigma'][m&v['has_mvs']]),
        abs_surf_minus_mesh=stats(np.abs(v['surf_minus_mesh'][m])),
        mask='dynnow floating patches cells 0..3; case bbox+3m; full unit row uses all dynnow floating pixels in unique selected main views',
        scientific_verdict=None)

if __name__=='__main__':main()
