"""8.1 stage-1-patch first outer-to-inner mesh hit, including missing surfaces."""
import argparse
import csv
from pathlib import Path
import numpy as np
import open3d as o3d
from inputs import OUT,PH,S0,S1,SITES,PRIORS,save,sha
from analytic_tables import summarize

def source_mesh(site,prior,result):
    if result=='mvs_a':return PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/mvs'/site/'mesh_mvs_a.ply'
    if result=='prior':
        if site=='B173nb_b10':return PH/'metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1/gpu'/f'samepath_{prior}/mesh.ply'
        return S1/'stage1'/site/f'samepath_{prior}/mesh.ply'
    if result.startswith('prop_'):
        if site=='B173nb_b10':return S0/'stage0'/f'b{int(result[-1])+1}_{prior}/post/mesh_tsdf.ply'
        return S1/'stage1'/site/result/'post/mesh_tsdf.ply'
    if result.startswith('nojudge_'):
        root=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site
        finite=root/(result+'.finite')
        return (finite if finite.exists() else root/result)/'post/mesh_tsdf.ply'
    return OUT/'runs'/site/result/'post/mesh_tsdf.ply'

def score(site,prior,result):
    dest=OUT/'patch_z'/f'{site}__{prior}__{result}.npz'
    assert not dest.exists(),f'refuse overwrite {dest}'
    path=source_mesh(site,prior,result)
    if not path.is_file():return dict(site=site,prior=prior,result=result,status='UNAVAILABLE',path=str(path),why='mesh absent')
    root=OUT/'direct_stage1_v2'/(site+'__'+prior)
    with np.load(root/'evaluation.npz') as e,np.load(root/'values.npz') as v:
        r={k:e[k] for k in ['area','in_eval','cell','scoring_allowed','has_mvs','p_gt','p_mvs','tau']}
        r.update({k:v[k].astype(np.float64) for k in ['sigma_prior','sigma_mvs']})
        c=e['centre'];n=e['normal']
    mesh=o3d.io.read_triangle_mesh(str(path));assert len(mesh.triangles)>0
    scene=o3d.t.geometry.RaycastingScene(nthreads=8)
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh));del mesh
    D=np.nan_to_num(r['p_mvs'],nan=0.);G=np.nan_to_num(r['p_gt'],nan=0.)
    start=np.maximum(6.,np.maximum(D+.5,G+.5));end=np.minimum(-6.,np.minimum(D-.5,G-.5))
    z=np.full(len(c),np.nan);ids=np.flatnonzero(r['in_eval']&r['scoring_allowed'])
    for offset in range(0,len(ids),50000):
        q=ids[offset:offset+50000];rays=np.c_[c[q]+start[q,None]*n[q],-n[q]].astype(np.float32)
        hit=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy().astype(np.float64)
        valid=np.isfinite(hit)&(hit<=start[q]-end[q]);z[q[valid]]=start[q[valid]]-hit[valid]
    dp=np.abs(z)/r['sigma_prior'];dm=np.abs(z-r['p_mvs'])/r['sigma_mvs']
    side=np.where(~np.isfinite(z),3,np.where((dp<=3)&((dm>3)|~np.isfinite(dm)|(dp<=dm)),0,np.where(dm<=3,1,2))).astype(np.int8)
    pid=np.array([f'stage1:{site}:{prior}:{i}' for i in range(len(c))])
    np.savez_compressed(dest,patch_id=pid,z=z,no_surface=~np.isfinite(z),side=side,in_eval=r['in_eval'],scoring_allowed=r['scoring_allowed'])
    r['z_'+result]=z;rows=summarize(site,prior,r)
    for row in rows:row['result_type']='mesh';row['mesh_source']=str(path)
    missing=r['in_eval']&r['scoring_allowed']&~np.isfinite(z)
    receipt=dict(site=site,prior=prior,result=result,status='PASS',path=str(path),mesh_sha256=sha(path),patch_z_sha256=sha(dest),
        scored_patches=len(ids),no_surface_patches=int(missing.sum()),no_surface_area_m2=float(r['area'][missing].sum()),
        rule='outward normal first mesh hit from max(6,p_M+.5,p_G+.5) to min(-6,p_M-.5,p_G-.5); absent is tau failure',
        rows=rows,scientific_verdict=None)
    save(dest.with_suffix('.json'),receipt);return receipt

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',choices=SITES);ap.add_argument('--prior',choices=PRIORS);ap.add_argument('--result')
    a=ap.parse_args();receipts=[]
    assert not a.result or (a.site and a.prior),'a result requires an exact site and prior'
    tag=f'{a.site}__{a.prior}__{a.result}' if a.result else 'baselines'
    for site in [a.site] if a.site else SITES:
        for prior in [a.prior] if a.prior else PRIORS:
            results=[a.result] if a.result else [f'nojudge_{prior}_s0',f'prop_{prior}_s0',f'prop_{prior}_s1','mvs_a','prior']
            for res in results:
                r=score(site,prior,res);receipts.append(r);print(site,prior,res,r['status'],flush=True)
                save(OUT/'checks'/f'mesh_{tag}.json',dict(results=receipts,scientific_verdict=None))
    rows=[row for r in receipts for row in r.get('rows',[])]
    save(f'/docs/tables/mesh_{tag}_stage1.json',dict(rows=rows,receipts=[{k:v for k,v in r.items() if k!='rows'} for r in receipts],scientific_verdict=None))
    if rows:
        with Path(f'/docs/tables/mesh_{tag}_stage1.csv').open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

if __name__=='__main__':main()
