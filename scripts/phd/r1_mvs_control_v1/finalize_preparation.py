#!/usr/bin/env python3
"""Validate sealed CPU inputs and materialize a non-executing runtime plan."""
import argparse
import ast
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from plyfile import PlyData
sys.path.insert(0,'/repo')
from src.phd.region_view_support_v1 import sha256
from src.phd.geogs_mvs_pgsr_v1.mvs_depth import read_colmap_depth, resample_depth_to_camera
from scripts.phd.geogs_p1p2p3_v1.input.prepare import read_pose_metadata, qvec_rotation


def write(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--config',default='/repo/configs/phd/r1_mvs_control_v1/runtime_v1.json');args=ap.parse_args()
    out=Path(args.output);out.mkdir(exist_ok=False)
    root=Path('/input');manifest=json.loads((root/'input_manifest.json').read_text());total=0
    for row in manifest['files']:
        p=root/row['path'];assert p.stat().st_size==row['bytes'] and sha256(p)==row['sha256'],row['path'];total+=row['bytes']
    print('Sealed inputs verified',len(manifest['files']),flush=True)
    split=json.loads((root/'scene/split_manifest.json').read_text());views=split['all'];train=split['train'];evaluation=split['evaluation']
    cfgpath=Path(args.config);cfg=json.loads(cfgpath.read_text())
    expected=cfg.get('expected_counts',dict(all=672,train=588,evaluation=84))
    assert (len(views),len(train),len(evaluation))==(expected['all'],expected['train'],expected['evaluation'])
    assert cfg['regions']==[split['region']]
    assert sorted(views,key=lambda v:v['name'])[::8]==evaluation
    cameras,poses=read_pose_metadata(root/'scene')
    for v in views:
        p=poses[v['image_id']];assert p['name']==v['name']
        assert np.allclose(qvec_rotation(p['qvec']),v['R'],atol=1e-12,rtol=0)
        assert np.array_equal(p['tvec'],v['t'])
        c=cameras[p['camera_id']];fx,fy,cx,cy=c['params']
        assert np.array_equal([[fx,0,cx],[0,fy,cy],[0,0,1]],v['K'])
    for i,v in enumerate(train):
        depth=read_colmap_depth(root/'mvs'/v['local_depth'],v['maps']['depth'])
        d,_=resample_depth_to_camera(depth,v['maps']['depth']['K'],v['K'],v['width'],v['height'])
        actual=np.load(root/'mvs_rgb/raw_depth'/(Path(v['name']).stem+'.npy'),allow_pickle=False)
        assert np.array_equal(d,actual),v['name']
    print('All',len(train),'MVS resampling maps match',flush=True)
    init=root/'initialization/lod2_pcd.ply'
    assert sha256(init)==sha256(root/'scene/sparse_lod/0/points3D.ply')==sha256(root/'scene/sparse/0/points3D.ply')
    samples=np.load(root/'initialization/sample_membership.npz');ids=samples['retained_ids']
    assert np.array_equal(ids,np.flatnonzero(samples['train_support_count']>=2))
    support=np.unpackbits(samples['packed_support'],axis=0)[:len(train)]
    assert np.array_equal(support.sum(axis=0),samples['train_support_count'])
    p=PlyData.read(str(init))['vertex'];xyz=np.column_stack([p[k] for k in 'xyz'])
    assert np.array_equal(xyz,samples['sample_xyz'][ids].astype(np.float32)) and np.isfinite(xyz).all()
    # Exact source snapshots, no patch or training invocation.
    provenance=json.loads(Path('/refinement_source/mvs_pgsr_source_provenance.json').read_text())
    for role,source,key in [('anchor',Path('/anchor_source'),'parent_implementation_hashes'),('refinement',Path('/refinement_source'),'prepared_implementation_hashes')]:
        for relative,digest in provenance[key].items():assert sha256(source/relative)==digest,(role,relative)
        shutil.copytree(source,out/(role+'_source'),ignore=shutil.ignore_patterns('__pycache__','.git'))
        for path in (out/(role+'_source')).rglob('*.py'):
            if 'submodules' not in path.parts:ast.parse(path.read_text(),filename=str(path))
    write(out/'runtime.json',cfg)
    binding=json.loads((root/'mvs/bindings.json').read_text());binding['config_sha256']=sha256(out/'runtime.json')
    binding['note']='Final basic MVS binding; supersedes provisional input/mvs/bindings.json. No PGSR graph used.'
    binding['neighbor_graph']['graph']={v['name']:{'selected':[]} for v in train}
    for v in binding['train']:v['local_depth']='../input/mvs/'+v['local_depth'];v['camera_model']='PINHOLE'
    write(out/'mvs_bindings.json',binding)
    shared=['python','train.py','-s','/input/scene','-m','/output/model','--lod_depth_path','/input/prior','--da_depth_path','/input/mvs_rgb',
        '--lod2_pcd_path','/input/initialization/lod2_pcd.ply','--eval','--lod_init','--freeze_onlybldg','--protect_bldg',
        '--dynamic_depth_weight','-r','1','--port','0','--iterations','30000','--stage_switch_iter','8000',
        '--lambda_lod_init','0.08','--lambda_lod_anchor','0.005','--lambda_da_depth','0.05','--data_device','cpu',
        '--jbgs_input_manifest','/input/input_manifest.json']
    env={'PYTORCH_CUDA_ALLOC_CONF':cfg['allocator'],'LD_PRELOAD':'/opt/geogs/lib/libstdc++.so.6',
        'PYTHONDONTWRITEBYTECODE':'1','TORCH_HOME':'/weights/torch','MPLCONFIGDIR':'/tmp/mpl','OMP_NUM_THREADS':'8','OPENBLAS_NUM_THREADS':'8'}
    mv={'JBGS_MVS_PGSR_MODE':'mvs','JBGS_MVS_REGION':split['region'],'JBGS_MVS_CONFIG':'/runtime/runtime.json',
        'JBGS_MVS_CONFIG_SHA256':sha256(out/'runtime.json'),'JBGS_MVS_BINDING':'/runtime/mvs_bindings.json',
        'JBGS_MVS_BINDING_SHA256':sha256(out/'mvs_bindings.json')}
    write(out/'execution_plan.json',dict(status='PREPARATION_ONLY_NO_PROCESS_STARTED',scientific_verdict=None,
        runtime_image_id=cfg['runtime_image_id'],container=dict(network='none',cpus=8,memory='32g',shm_size='4g',gpu='resolve before future execution',working_directory='/source'),
        common_mounts_readonly={'/input':'../../result/input','/runtime':'.','/weights':'existing GeoGS runtime/weights; resolve and bind before execution'},
        writable_mounts={'/output':'fresh attempt per stage; never overwrite'},
        anchor=dict(source_mount='anchor_source -> /source',environment=env,argv=shared+['--jbgs_stop_after','8000','--jbgs_capture_iterations','8000'],
            expected_output='model/jbgs_complete/iteration_8000/checkpoint.pth'),
        refinement=dict(source_mount='refinement_source -> /source',environment={**env,**mv},
            anchor_mount='new R1 anchor model/jbgs_complete/iteration_8000 -> /anchor (readonly)',anchor_sha256=None,
            argv=shared+['--jbgs_resume_full','/anchor/checkpoint.pth','--jbgs_capture_iterations','30000'],
            preflight_override=['--jbgs_stop_after','8100','--jbgs_capture_iterations','8100'],
            preflight_scope='separate disposable continuation from same Anchor8k; full continuation restarts from same Anchor8k'),
        pending_runtime_checks=cfg['future_run_checks']))
    write(out/'receipt.json',dict(status='PASS_CPU_VALIDATION_AND_RUNTIME_PREPARATION',scientific_verdict=None,
        validated_input_files=len(manifest['files']),validated_input_bytes=total,mvs_resampling_exact_views=len(train),
        train=len(train),evaluation=len(evaluation),initial_points=len(xyz),minimum_initial_support=2,
        native_projection_checks=len(train)*128,initialization_protection_ply_identical=True,source_parent_and_prepared_hashes_verified=True,
        input_manifest_sha256=sha256(root/'input_manifest.json'),config_sha256=sha256(cfgpath),script_sha256=sha256(__file__),
        runtime_files={p.name:sha256(p) for p in out.iterdir() if p.is_file()},training_runs=0,gpu_preflight='NOT_RUN',manual_weights=None))
    print(json.dumps(dict(status='PASS',validated_files=len(manifest['files']),initial_points=len(xyz),training_runs=0)),flush=True)


if __name__=='__main__':main()
