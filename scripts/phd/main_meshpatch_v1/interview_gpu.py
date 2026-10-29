"""Frozen GeoGS virtual-camera inference only; no training or new visibility."""
import argparse,sys,time
from interview_common import *

def gpu_config():
    p=C/'interview_gpu_v1.json'
    assert sha(p)==json.loads(p.with_suffix('.lock.json').read_text())['sha256']
    return json.loads(p.read_text())

def freeze():
    p=C/'interview_gpu_v1.json'
    if p.exists():gpu_config();return
    files=['scripts/phd/main_stage1_v1/gpu_s1.py']
    files += ['src/phd/forks/GeoGS-conf-guided-v1-r17/'+f for f in
        ['render.py','utils/render_utils.py','utils/mesh_utils.py','gaussian_renderer/__init__.py','scene/__init__.py','scene/gaussian_model.py']]
    rows=[]
    for site in SITES:
        region=S1/'regions_v3'/f'regions_ext_v3_{site}_LoD2.npz'
        unseen=S1/'defs'/site/'unseen.npz'
        for prefix in ['nojudge','lt_dynnow']:
            mp=model(site,'LoD2',prefix);root=mp.parent if prefix=='nojudge' else mp.parent.parent
            old=root/'gpu/virtual/mesh_virtual.ply'
            rows.append(dict(site=site,prefix=prefix,model=str(mp),model_input=source(mp/'point_cloud/iteration_30000/point_cloud.ply'),
                existing_mesh=source(old) if old.exists() else None,
                targets=source(unseen if unseen.exists() else region),target_rule='original unseen.centre' if unseen.exists() else 'existing regions_v3 in_eval & kind=2 & code_ext_v3 in [5,14]',
                split=source(S0/'fork_inputs/s61'/site/'split.json')))
    cfg=dict(task_id='PHD-MAIN-MESHPATCH-v1',created_at=now(),scientific_verdict=None,no_training=True,
        source_files={str(R/f):sha(R/f) for f in files},targets=rows,
        algorithm='unchanged gpu_s1.load, box_of, subset, box_mask; original GeoGS render, create_virtual_cameras_for_completion, GaussianExtractor reconstruction/extract_mesh_bounded',
        n_virtual_cams=8,elevation_angles=[.2,.5],distance_scale=1.5,voxel_size=.10,sdf_trunc=.5,depth_trunc=300.,active_sh_degree=0,
        virtual_target_note='Use original unseen.centre where present. Otherwise aim the same camera generator at existing invisible LoD2 wall centres. No new visibility/region calculation; these are rendering targets, not training inputs.',
        training_terminal_sources=['B173nb_b10/fp_prune_dynnow_ALS_s0','B173nb_b10/fp_k5Lprune_dynnow_ALS_s0'])
    dump(p,cfg);dump(p.with_suffix('.lock.json'),dict(sha256=sha(p),created_at=now(),scientific_verdict=None))
    print(json.dumps(dict(status='FROZEN',targets=len(rows),missing_meshes=sum(r['existing_mesh'] is None for r in rows)),ensure_ascii=False))

def run(site,prefix):
    cfg=gpu_config();config()
    for path,digest in cfg['source_files'].items():assert sha(path)==digest,path
    row=next(r for r in cfg['targets'] if (r['site'],r['prefix'])==(site,prefix))
    for key in ['model_input','targets','split']:assert sha(row[key]['path'])==row[key]['sha256'],key
    check=IDOC/'checks/virtual_baseline.json';assert json.loads(check.read_text())['status']=='PASS'
    if row['existing_mesh']:
        assert sha(row['existing_mesh']['path'])==row['existing_mesh']['sha256'];return
    job=f'gpu-{SHORT[site].lower()}-{prefix}';dest=IOUT/'virtual'/site/f'{prefix}_LoD2_s0';dest.mkdir(parents=True,exist_ok=True)
    output=dest/'mesh_virtual.ply'
    if output.exists():
        receipt=json.loads((dest/'receipt.json').read_text());assert receipt['mesh_sha256']==sha(output);return
    far=PH/'main_farpull_v1/PHD-MAIN-FARPULL-v1/runs'
    training=[]
    for name in cfg['training_terminal_sources']:
        root=far/name
        terminal=next((root/f for f in ['PASS.json','STOP_final.json'] if (root/f).exists()),None)
        assert terminal is not None,'FARPULL training still active or completion unverified'
        training.append(source(terminal))
    import torch,open3d as o3d
    from types import SimpleNamespace
    sys.path.insert(0,str(R/'scripts/phd/main_stage1_v1'))
    import gpu_s1 as G
    start=time.monotonic();record(job,status='RUNNING',training_terminal=training)
    with np.load(row['targets']['path']) as f:
        centres=f['centre']
        if row['target_rule']!='original unseen.centre':centres=centres[f['in_eval']&(f['kind']==2)&np.isin(f['code_ext_v3'],[5,14])]
    if not len(centres):record(job,status='UNAVAILABLE',reason='기존 자료에 비가시 벽 카메라 표적 없음');return
    dataset,pipe,g,scene=G.load(site,'LoD2',Path(row['model']),its=30000)
    train=scene.getTrainCameras();box=G.box_of(site)
    with torch.no_grad():
        c=torch.as_tensor(centres,device='cuda').float()
        target=SimpleNamespace(completed_mask=torch.ones(len(c),dtype=torch.bool,device='cuda'),get_xyz=c)
        virtual=G.create_virtual_cameras_for_completion(target,train,n_virtual_cams=cfg['n_virtual_cams'],distance_scale=cfg['distance_scale'],elevation_angles=cfg['elevation_angles'])
        assert len(virtual)==16
        xyz=g.get_xyz.detach();inside=((xyz>=torch.as_tensor(box[0],device='cuda').float())&(xyz<=torch.as_tensor(box[1],device='cuda').float())).all(1)
        rendered=G.subset(dataset,g,inside);extractor=G.GaussianExtractor(rendered,G.render,pipe,bg_color=[0,0,0])
        extractor.gaussians.active_sh_degree=cfg['active_sh_degree'];extractor.reconstruction(train+virtual)
        for i,cam in enumerate(extractor.viewpoint_stack):cam.gt_alpha_mask=G.box_mask(cam,extractor.depthmaps[i],box).cpu()
        mesh=extractor.extract_mesh_bounded(voxel_size=cfg['voxel_size'],sdf_trunc=cfg['sdf_trunc'],depth_trunc=cfg['depth_trunc'])
        for cam in extractor.viewpoint_stack:cam.gt_alpha_mask=None
    assert len(mesh.triangles)>0,'empty virtual mesh'
    tmp=dest/'mesh_virtual.partial.ply';assert o3d.io.write_triangle_mesh(str(tmp),mesh)
    receipt=dict(status='PASS',site=site,prefix=prefix,mesh_sha256=sha(tmp),source_binding=row,gpu_config_sha256=sha(C/'interview_gpu_v1.json'),
        train_views=len(train),virtual_views=len(virtual),target_centres=len(centres),gaussians_rendered=int(inside.sum()),box=box,
        virtual_cameras=[dict(name=c.image_name,centre=c.camera_center.cpu().numpy(),world_to_camera=c.world_view_transform.T.cpu().numpy()) for c in virtual],
        vertices=len(mesh.vertices),triangles=len(mesh.triangles),seconds=time.monotonic()-start,created_at=now(),scientific_verdict=None)
    dump(dest/'receipt.json',receipt);tmp.replace(output);record(job,mesh=str(output),mesh_sha256=receipt['mesh_sha256'],seconds=receipt['seconds'])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('site',nargs='?');ap.add_argument('prefix',nargs='?');a=ap.parse_args()
    freeze() if a.freeze else run(a.site,a.prefix)
