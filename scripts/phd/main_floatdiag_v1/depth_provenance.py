"""Trace training and TSDF depth selection through original commands and code."""
import json
from common import *
root=Path('/repo');files=[];commands=[]
for rev in ['r14','r15','r17']:
    for name in ['arguments/__init__.py','gaussian_renderer/__init__.py','utils/mesh_utils.py']:
        p=root/'src/phd/forks'/('GeoGS-conf-guided-v1-'+rev)/name
        files.append(dict(revision=rev,file=str(p),sha256=sha(p)))
for name in ['arguments/__init__.py','gaussian_renderer/__init__.py','utils/mesh_utils.py']:
    assert len({x['sha256'] for x in files if x['file'].endswith('/'+name)})==1
for site in SITES:
    p=S3/'runs'/site/'nojudge_ALS_s0/receipt.json';r=json.loads(p.read_text());command=r['command']
    assert '--depth_ratio' not in command
    commands.append(dict(site=site,result='nojudge_ALS_s0',receipt=str(p),sha256=sha(p),training_source=r['source'],depth_ratio_override=False))
    for result in ['lt_dyngt_ALS_s0','lt_dynnow_ALS_s0']:
        p=model_path(site,result).parent/'command.json';command=json.loads(p.read_text());assert '--depth_ratio' not in command
        commands.append(dict(site=site,result=result,receipt=str(p),sha256=sha(p),depth_ratio_override=False))
for name in ['scripts/phd/main_stage1_v1/gpu_s1.py','scripts/phd/main_stage3_v1/gpu_s3.py','scripts/phd/main_losstrain_v1/gpu_post.py','scripts/phd/main_losstrain_v1/tiled_post.py']:
    p=root/name;files.append(dict(file=str(p),sha256=sha(p)))
rendered=[json.loads((OUT/'four_depths'/site/'gpu_receipt.json').read_text()) for site in SITES]
assert all(r['exact_surf_equals_mean'] and r['exact_cached_surf_depth'] for site in rendered for r in site['rows'])
save(DOC/'provenance/mesh_depth_source.json',dict(at=now(),status='PASS',files=files,commands=commands,runtime=rendered,
    conclusion='TSDF input is (1) surf_depth, which equals (4) opacity-weighted mean at depth_ratio=0.0. It is not (3) cumulative opacity 0.5 depth or (2) already-extracted mesh first hit.',
    training='PipelineParams depth_ratio=0.0; exact commands have no override; surf_depth=(1-depth_ratio)*expected+depth_ratio*median',
    post='gpu_s1.load and gpu_s3.load create default PipelineParams. GaussianExtractor.reconstruction reads render_pkg[surf_depth]. LT tiled_post replaces only extract_mesh_bounded; saved depths and integration are unchanged.',
    median='CUDA forward.cu stores current depth while pre-contribution transmittance T>0.5; valid only if final accumulated alpha>=0.5. Uses renderer contribution order, no between-surfel interpolation.',
    limitation='TSDF integration, voxel extraction and visibility can make extracted-mesh first-hit depth differ from its input mean depth; difference is measured, not assumed zero.',scientific_verdict=None))
print('TSDF depth source (1) = (4), command/code/runtime verification PASS')
