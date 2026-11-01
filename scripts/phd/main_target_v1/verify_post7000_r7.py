"""Independent area arithmetic and a deterministic ray subset from the saved pilot mesh."""
import sys
import numpy as np
import open3d as o3d
from common import *

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def main():
    prior=sys.argv[1];baseline='--baseline' in sys.argv;site='B173nb_b10';run=OUT/'r7'/('baselines' if baseline else 'runs')/(f'base7k_{site}_{prior}_s0' if baseline else f'tg_{site}_{prior}_s0_r7');wd=run/'post7000'
    score=json.loads((wd/'score.json').read_text());z=loadz(wd/'patch_z.npz');attr=None if baseline else loadz(wd/'origin_attribution.npz')
    binding=json.loads((wd/'inputs/binding.json').read_text())
    for name,digest in binding['files'].items():assert sha(wd/'inputs'/name)==digest,name
    merged=json.loads((wd/'merged.json').read_text());settings=merged['tsdf']
    assert settings['voxel_m']==.05 and settings['sdf_trunc_m']==.25 and settings['depth_trunc_m']==300 and settings['views']==203
    lt=PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'{site}__{prior}';e=loadz(lt/'evaluation.npz')
    task=loadz(OUT/'r2/stage0/evaluation'/f'{site}_{prior}.npz');t=loadz(OUT/'r7/targets'/f'{site}_{prior}.npz')
    assert np.array_equal(z['cell'],task['cell']) and np.array_equal(z['region'],t['region'])
    assert np.array_equal(z['any_replaced'],t['any_replaced'])
    eligible=e['in_eval']&e['scoring_allowed'];finite=np.isfinite(z['z'])&~z['no_surface']
    within=finite&(np.abs(z['z']-e['p_gt'])<=e['tau']);floating=finite&~within&(z['side']==2)&(z['z']>e['p_gt']+e['tau'])
    assert np.array_equal(floating,z['category']==1) and np.array_equal(within,z['category']==0)
    select=eligible&np.isin(task['cell'],[0,1,2,3]);den=float(e['area'][select].sum());num=float(e['area'][select&floating].sum())
    assert abs(num/den-score['floating_fraction_cells_0_3'])<1e-12
    for row in score['rows']:
        mask=eligible if row['cell']=='전체' else select if row['cell']=='0~3' else eligible&(task['cell']==int(row['cell']))
        assert row['patches']==int(mask.sum()) and abs(row['area_m2']-e['area'][mask].sum())<1e-8
        assert abs(row['floating_area_m2']-e['area'][mask&floating].sum())<1e-8
        assert abs(row['within_tau_area_m2']-e['area'][mask&within].sum())<1e-8
    for row in score['result_vs_target']:
        mask=eligible&(t['region']==row['region'])
        if row['replacement']!='all':mask &= t['any_replaced'] if row['replacement']=='replaced' else ~t['any_replaced']
        den2=float(e['area'][mask].sum());assert abs(den2-row['area_m2'])<1e-8
        if den2:
            assert abs(e['area'][mask&within].sum()/den2-row['result_within_tau_fraction'])<1e-12
            if row['region']==5:assert row['target_within_tau_fraction'] is None
            else:assert abs(e['area'][mask&(abs(t['h']-e['p_gt'])<=e['tau'])].sum()/den2-row['target_within_tau_fraction'])<1e-12
            assert abs(e['area'][mask&floating].sum()/den2-row['floating_fraction'])<1e-12
            assert abs(e['area'][mask&z['no_surface']].sum()/den2-row['no_surface_fraction'])<1e-12
    assert abs(float(e['area'][select&z['no_surface']].sum()/den)-score['no_surface_fraction_cells_0_3'])<1e-12
    if not baseline:
        base=json.loads((OUT/'r7/baselines'/f'base7k_{site}_{prior}_s0/post7000/score.json').read_text())
        expected=[score['floating_fraction_cells_0_3']<=base['floating_fraction_cells_0_3']+.02,score['agreement_within_tau_fraction']>=base['agreement_within_tau_fraction']-.02,score['no_surface_fraction_cells_0_3']<=base['no_surface_fraction_cells_0_3']+.01]
        assert (score['status']=='PASS')==(all(expected) and score['gates']['health'])
    # Independently construct a fixed evenly spaced subset of the original first-hit rays.
    mesh=o3d.io.read_triangle_mesh(str(wd/'merged.ply'));assert len(mesh.vertices)==score['mesh_vertices'] and len(mesh.triangles)==score['mesh_faces']
    sc=o3d.t.geometry.RaycastingScene(nthreads=2);sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    ids=np.flatnonzero(eligible);ids=ids[np.linspace(0,len(ids)-1,min(2048,len(ids)),dtype=int)]
    dm=np.nan_to_num(e['p_mvs'][ids],nan=0.);dg=np.nan_to_num(e['p_gt'][ids],nan=0.)
    start=np.maximum(6.,np.maximum(dm+.5,dg+.5));end=np.minimum(-6.,np.minimum(dm-.5,dg-.5))
    rays=np.column_stack([e['centre'][ids]+start[:,None]*e['normal'][ids],-e['normal'][ids]]).astype('f4')
    distance=sc.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy().astype('f8');valid=np.isfinite(distance)&(distance<=start-end)
    expect=np.full(len(ids),np.nan);expect[valid]=start[valid]-distance[valid]
    assert np.array_equal(np.isfinite(expect),np.isfinite(z['z'][ids]))
    ray_error=float(np.max(abs(expect[valid]-z['z'][ids][valid]),initial=0));assert ray_error<1e-5
    assert sha(wd/'merged.ply')==score['mesh_sha256']
    for p,digest in score['scorer_sources'].items():assert sha(REPO/p)==digest
    areas=[]
    if not baseline:
        assert np.array_equal(attr['category'],z['category']) and np.array_equal(attr['in_eval'],eligible)
        assert np.array_equal(attr['background_dominant'],(attr['views']>0)&(attr['mean_fraction'][:,0]>=.5))
        assert np.array_equal(attr['released_dominant'],(attr['views']>0)&(attr['mean_fraction'][:,1]>=.5))
        for label,mask in [('all_floating',eligible&floating),('cell_0_3_floating',select&floating)]:
            area=float(e['area'][mask].sum());areas.append(dict(group=label,area_m2=area,
                background_dominant_area_m2=float(e['area'][mask&attr['background_dominant']].sum()),
                released_dominant_area_m2=float(e['area'][mask&attr['released_dominant']].sum()),
                origin_unavailable_area_m2=float(e['area'][mask&(attr['views']==0)].sum())))
    record=dict(at=stamp(),status='PASS_POST7000_RECOUNT_AND_RAYS',prior=prior,floating_area_m2=num,evaluation_area_m2=den,
        floating_fraction=num/den,ray_samples=len(ids),max_ray_difference_m=ray_error,origin_areas=areas,
        mesh_sha256=score['mesh_sha256'],score_sha256=sha(wd/'score.json'),patch_z_sha256=sha(wd/'patch_z.npz'),
        attribution_sha256=None if baseline else sha(wd/'origin_attribution.npz'),scientific_verdict=None)
    dump(run/'verification_post7000.json',record);dump(DOC/'tables'/(f'verification_post7000_{prior}_r7'+('_baseline' if baseline else '')+'.json'),record)
    print('POST7000_VERIFIED',prior,num/den,flush=True)

if __name__=='__main__':main()
