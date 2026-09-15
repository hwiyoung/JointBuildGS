#!/usr/bin/env python3
"""Materialize an isolated R1 control input package, with CPU work only."""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import sys
import time
import traceback
import laspy
import numpy as np
from plyfile import PlyData, PlyElement
sys.path.insert(0,'/repo')
from src.phd.region_view_support_v1 import sha256, object_basis, region_mask
from src.phd.geogs_mvs_pgsr_v1.mvs_depth import read_colmap_depth, resample_depth_to_camera
from scripts.phd.geogs_p1p2p3_v1.input.prepare import read_pose_metadata, write_colmap
from scripts.phd.geogs_p1p2p3_v1.input.prior_native import official_module
from src.phd.wu_vallet_p3_v2.acquisition import group_pulses, recover_scan_coordinates
from scripts.phd.wu_vallet_p3_v2.update_points import build_old


def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def progress(out,stage,**kw):
    value=dict(stage=stage,unix=time.time(),**kw)
    (out/'status.json').write_text(json.dumps(value)+'\n');print(json.dumps(value),flush=True)


def frozen(path,expected):
    got=sha256(path)
    if got!=expected:raise ValueError('Input changed: '+str(path))
    return got


def raw_values(points):
    return dict(gps_time=np.asarray(points.gps_time),strip=np.asarray(points.point_source_id),
        return_number=np.asarray(points.return_number),number_of_returns=np.asarray(points.number_of_returns),
        scan_angle_rank=np.asarray(points.scan_angle_rank),xyz_raw=np.column_stack((points.x,points.y,points.z)))


def prepare_als(cfg,region,basis,frame,out):
    spec=json.loads(Path('/repo',cfg['als_source_config']).read_text())['inputs']['existing_als']
    paths=[Path('/als',name) for name in sorted(spec['files'])]
    shift=np.array(frame['world_shift_xyz_m']);bridge=np.array([0,0,spec['z_shift_m']])
    context={**region,'u_m':[region['u_m'][0]-cfg['context_buffer_uv_m'],region['u_m'][1]+cfg['context_buffer_uv_m']],
             'v_m':[region['v_m'][0]-cfg['context_buffer_uv_m'],region['v_m'][1]+cfg['context_buffer_uv_m']]}
    windows={};crop_counts={};input_files=[]
    for path in paths:
        frozen(path,spec['files'][path.name]);n=0
        with laspy.open(path) as h:
            for points in h.chunk_iterator(1_000_000):
                xyz=np.column_stack((points.x,points.y,points.z))+bridge-shift
                keep=region_mask(xyz,context,basis,frame['z_m']);n+=int(keep.sum())
                if not keep.any():continue
                times=np.asarray(points.gps_time)[keep];strips=np.asarray(points.point_source_id)[keep]
                for sid in np.unique(strips):
                    t=times[strips==sid];old=windows.get(int(sid),[np.inf,-np.inf])
                    windows[int(sid)]=[min(old[0],float(t.min())),max(old[1],float(t.max()))]
        crop_counts[path.name]=n;input_files.append(dict(name=path.name,sha256=spec['files'][path.name],bytes=path.stat().st_size))
        progress(out,'ALS_CONTEXT_PASS',file=path.name,points=n)
    pad=cfg['acquisition']['time_padding_seconds'];windows={k:[v[0]-pad,v[1]+pad] for k,v in windows.items()}
    arrays={}
    for fi,path in enumerate(paths):
        offset=0
        with laspy.open(path) as h:
            for points in h.chunk_iterator(1_000_000):
                times=np.asarray(points.gps_time);strips=np.asarray(points.point_source_id);keep=np.zeros(len(points),bool)
                for sid,(lo,hi) in windows.items():keep|=(strips==sid)&(times>=lo)&(times<=hi)
                if keep.any():
                    row=raw_values(points[keep]);row['original_row']=np.flatnonzero(keep).astype(np.int64)+offset
                    row['original_file_index']=np.full(int(keep.sum()),fi,np.int16)
                    for k,v in row.items():arrays.setdefault(k,[]).append(v.copy())
                offset+=len(points)
        progress(out,'ALS_TIME_CONTEXT_PASS',file=path.name)
    a={k:np.concatenate(v) for k,v in arrays.items()};a['xyz']=a.pop('xyz_raw')+bridge-shift
    pulse=group_pulses(a['gps_time'],a['strip'],a['return_number'],a['number_of_returns'],a['xyz'])
    n=len(pulse['pulse_gps_time']);scans=[]
    for key,dtype in [('scan_id',np.int32),('beam_coordinate',np.float64),('complete_scan',bool)]:
        pulse['pulse_'+key]=np.empty(n,dtype)
    for sid in sorted(windows):
        ids=np.flatnonzero(pulse['pulse_strip']==sid)
        scan=recover_scan_coordinates(pulse['pulse_gps_time'][ids],a['scan_angle_rank'][pulse['pulse_first_context_row'][ids]],
            cfg['acquisition']['scan_reset_degrees'],cfg['acquisition']['minimum_scan_boundaries'])
        for key in ('scan_id','beam_coordinate','complete_scan'):pulse['pulse_'+key][ids]=scan[key]
        scans.append(dict(strip=sid,report=scan['report']))
    acq={'context_'+k:v for k,v in a.items()};acq.update(pulse)
    ids=np.flatnonzero(region_mask(a['xyz'],context,basis,frame['z_m']))
    xyz,faces,audit=build_old(acq,ids,cfg['als_surface'])
    if len(xyz)!=sum(crop_counts.values()) or not len(faces):raise ValueError('ALS crop recovery failed')
    # Exact original membership is preserved; no GT classification or source arbitration.
    surface=out/'input/surface';surface.mkdir()
    represented=np.zeros(len(xyz),bool);represented[np.unique(faces)]=True
    np.savez_compressed(surface/'mesh_arrays.npz',xyz=xyz,faces=faces)
    np.savez_compressed(surface/'vertex_membership.npz',original_file_index=a['original_file_index'][ids],
        original_row=a['original_row'][ids],represented_in_surface=represented,
        in_R1=region_mask(xyz,region,basis,frame['z_m']))
    with (surface/'als_surface.obj').open('x') as f:
        f.write('# ALS scan/beam surface; local EPSG25832; no evaluation input\n')
        np.savetxt(f,xyz,fmt='v %.9f %.9f %.9f');np.savetxt(f,faces+1,fmt='f %d %d %d')
    write(surface/'receipt.json',dict(status='PASS',scientific_verdict=None,context=context,z_m=frame['z_m'],
        counts=dict(vertices=len(xyz),triangles=len(faces),omitted_vertices=int((~represented).sum())),
        input_files=input_files,time_windows=windows,scan_reports=scans,mesh_audit=audit,
        z_bridge_m=spec['z_shift_m'],datum_calibration_verified=False))
    return xyz,faces


def ply_points(path,xyz):
    data=np.zeros(len(xyz),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('nx','<f4'),('ny','<f4'),('nz','<f4'),('red','u1'),('green','u1'),('blue','u1')])
    for i,k in enumerate('xyz'):data[k]=xyz[:,i]
    for k in ('red','green','blue'):data[k]=128
    PlyData([PlyElement.describe(data,'vertex')],text=False).write(str(path))


def prepare_prior(cfg,xyz,faces,views,out):
    import open3d as o3d
    module=official_module(Path('/geogs_original'))
    from LoD2Depth.raycasting import create_mesh_scene,generate_depth_normal_maps
    scene=create_mesh_scene(xyz,faces);policy=cfg['initialization'];np.random.seed(cfg['seed']);random.seed(cfg['seed'])
    samples,face_ids=module.sample_points_from_mesh(xyz,faces,policy['num_points'])
    initial=out/'input/initialization';initial.mkdir();prior=out/'input/prior/raw_depth';prior.mkdir(parents=True)
    count=np.zeros(len(samples),np.uint16);visible=np.zeros((len(views),len(samples)),bool);prior_rows=[]
    # Projection is vectorized; the visibility rule and sampled points are inherited.
    parity_ids=np.linspace(0,len(samples)-1,128,dtype=int)
    for index,v in enumerate(views):
        R=np.array(v['R']);t=np.array(v['t']);K=np.array(v['K']);E=np.eye(4);E[:3,:3]=R;E[:3,3]=t
        camera=samples@R.T+t;z=camera[:,2];pixel=(camera/np.where(z>0,z,1)[:,None])@K.T
        frame=(z>0)&(pixel[:,0]>=5)&(pixel[:,0]<v['width']-5)&(pixel[:,1]>=5)&(pixel[:,1]<v['height']-5)
        for j in parity_ids:
            expected=module.project_point_to_camera(samples[j],E,K,v['width'],v['height'])
            if bool(expected is not None)!=bool(frame[j]):raise ValueError('Native FOV parity failed')
            if expected is not None and not np.allclose(expected,pixel[j,:2],rtol=0,atol=1e-8):raise ValueError('Native projection parity failed')
        center=-R.T@t;delta=samples-center;distance=np.linalg.norm(delta,axis=1)
        rays=np.column_stack((np.broadcast_to(center,samples.shape),delta/distance[:,None])).astype(np.float32)
        hit=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy()
        visible[index]=frame&np.isfinite(hit)&(np.abs(hit-distance)<policy['visibility_tolerance_m']);count+=visible[index]
        depth,_,_=generate_depth_normal_maps(scene,K,E,v['width'],v['height'])
        path=prior/(Path(v['name']).stem+'.npy');np.save(path,depth.astype(np.float32),allow_pickle=False)
        valid=np.isfinite(depth)&(depth>0)
        prior_rows.append(dict(name=v['name'],valid_pixels=int(valid.sum()),sha256=sha256(path)))
        if index%20==0 or index==len(views)-1:progress(out,'PRIOR_DEPTH_AND_INITIAL_VISIBILITY',completed=index+1,total=len(views))
    retained=np.flatnonzero(count>=policy['min_observations']);xyz_kept=samples[retained]
    if not len(retained):raise ValueError('No train-visible ALS initialization samples')
    ply_points(initial/'lod2_pcd.ply',xyz_kept)
    np.savez_compressed(initial/'sample_membership.npz',sample_xyz=samples,face_ids=face_ids,retained_ids=retained,train_support_count=count,
        packed_support=np.packbits(visible,axis=0),train_names=np.array([v['name'] for v in views]))
    # GeoGS reads the PLY and ignores tracks. Record this bounded vectorization explicitly.
    for sparse in ('sparse/0','sparse_lod/0'):
        shutil.copyfile(initial/'lod2_pcd.ply',out/'input/scene'/sparse/'points3D.ply')
    write(initial/'receipt.json',dict(status='PASS',scientific_verdict=None,sampled=len(samples),retained=len(retained),
        min_observations=policy['min_observations'],train_views=len(views),source_sampling_sha256=sha256('/geogs_original/data/generate_pcd.py'),
        native_projection_checks=len(views)*len(parity_ids),color_rgb=[128,128,128],protection_equals_initialization=True,
        adaptation='Vectorized all-camera FOV and nearest-ray visibility with inherited 5px margin, 0.05m ray tolerance and >=2 train views; native area sampler. Track assembly omitted because GeoGS PLY reader ignores tracks; no geometry/selection change.'))
    write(out/'input/prior/receipt.json',dict(status='PASS',scientific_verdict=None,rows=prior_rows,
        depth_frame='CAMERA_Z_METERS',pixel_centers='original Open3D u+0.5,v+0.5',misses='original nonfinite misses retained',train_only=True))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/reference').exists():raise RuntimeError('Isolated CPU Docker required')
    cfg=json.loads(Path(args.config).read_text());out=Path(args.output);out.mkdir(exist_ok=False);(out/'input').mkdir()
    started=time.monotonic();shutil.copyfile(args.config,out/'preparation_config.json')
    frozen('/audit/result/receipt.json',cfg['audit_receipt_sha256'])
    receipt=json.loads(Path('/audit/result/receipt.json').read_text())
    for key in ('config.json','camera_bindings.json','candidate_memberships.json'):
        frozen(Path('/audit/result',key),receipt['output_files'][key]['sha256'])
    oldcfg=json.loads(Path('/audit/result/config.json').read_text());frame=oldcfg['frame'];basis=object_basis(frame['u_axis_angle_degrees_ccw_from_easting'])
    region=next(r for r in oldcfg['regions'] if r['id']==cfg['region']);members=json.loads(Path('/audit/result/candidate_memberships.json').read_text())
    records=json.loads(Path('/audit/result/camera_bindings.json').read_text())['cameras'];selected=members['regions'][cfg['region']]
    for key,count in [('candidates','all'),('train','train'),('evaluation','evaluation')]:
        if len(selected[key])!=cfg['expected_counts'][count]:raise ValueError(cfg['region']+' camera membership changed')
    cameras,poses=read_pose_metadata('/cameras');scene=out/'input/scene';scene.mkdir();(scene/'images').mkdir()
    native=out/'input/mvs/native';native.mkdir(parents=True);rgb_depth=out/'input/mvs_rgb/raw_depth';rgb_depth.mkdir(parents=True)
    views=[];train_ids=set(selected['train'])
    for index in selected['candidates']:
        r=records[index];pose=poses[r['image_id']];camera=cameras[pose['camera_id']]
        src=Path('/cameras/images')/r['name'];frozen(src,r['rgb_sha256']);shutil.copyfile(src,scene/'images'/r['name'])
        v=dict(image_id=r['image_id'],camera_id=pose['camera_id'],name=r['name'],width=r['width'],height=r['height'],K=r['K'],R=r['R'],t=r['t'],
            path='/input/scene/images/'+r['name'],sha256=r['rgb_sha256'],role='train' if index in train_ids else 'evaluation',
            maps={'depth':{**r['native_depth'],'K':r['native_K'],'path':'/input/mvs/native/'+r['name']+'.geometric.bin'}})
        if v['role']=='train':
            depth_path=Path('/cameras/stereo/depth_maps')/(r['name']+'.geometric.bin');meta=v['maps']['depth']
            depth=read_colmap_depth(depth_path,meta);shutil.copyfile(depth_path,native/depth_path.name)
            projected=resample_depth_to_camera(depth,np.array(r['native_K']),np.array(r['K']),r['width'],r['height'])
            # The legacy DA argument is a path convention only; these bytes are COLMAP MVS.
            if isinstance(projected,tuple):projected=projected[0]
            np.save(rgb_depth/(Path(r['name']).stem+'.npy'),np.asarray(projected,dtype=np.float32),allow_pickle=False)
            v['local_depth']='native/'+depth_path.name
        views.append(v)
        if len(views)%50==0:progress(out,'COPY_BOUND_CAMERAS_AND_MVS',completed=len(views),total=len(selected['candidates']))
    train=[v for v in views if v['role']=='train'];evaluation=[v for v in views if v['role']=='evaluation']
    fullposes=[poses[v['image_id']] for v in views];trainposes=[poses[v['image_id']] for v in train]
    for name,subset in [('sparse/0',fullposes),('sparse_lod/0',fullposes),('sparse_txt',fullposes),('train_sparse_txt',trainposes)]:
        write_colmap(scene/name,cameras,subset,empty_points=True)
    split=dict(schema='jointbuildgs.geogs.region_split.v1',region=cfg['region'],all=views,train=train,evaluation=evaluation,llffhold=8,
        scientific_verdict=None,actual_visual_source='COLMAP_MVS_CAMERA_Z',independent_confirmatory=False)
    write(scene/'split_manifest.json',split)
    write(scene/'scene_reference_frame.json',dict(base_to_canonical=dict(scale=1.,shift=[0.,0.,0.],swap_xy=False)))
    write(scene/'jbgs_calibration.json',dict(schema='jointbuildgs.geogs.source_calibration.v1',scientific_verdict=None,
        source_split_manifest_sha256=sha256(scene/'split_manifest.json'),images={Path(v['name']).stem:{k:v[k] for k in ('width','height','K')} for v in views}))
    centers=np.array([-np.array(v['R']).T@v['t'] for v in train]);radius=1.1*np.linalg.norm(centers-centers.mean(axis=0),axis=1).max()
    write(out/'region.json',dict(region=region,frame=frame,context_buffer_uv_m=cfg['context_buffer_uv_m'],camera_radius_m=float(radius),
        percent_dense=.01,effective_clone_split_boundary_m=float(.01*radius),scientific_verdict=None))
    xyz,faces=prepare_als(cfg,region,basis,frame,out)
    prepare_prior(cfg,xyz,faces,train,out)
    inputroot=out/'input';files=[dict(path=str(p.relative_to(inputroot)),bytes=p.stat().st_size,sha256=sha256(p)) for p in sorted(inputroot.rglob('*')) if p.is_file()]
    manifest=dict(task_id=cfg['task_id'],status='CPU_INPUTS_PREPARED_NOT_GPU_VALIDATED',region=cfg['region'],scientific_verdict=None,
        config_sha256=sha256(args.config),split_sha256=sha256(scene/'split_manifest.json'),files=files,
        training_paths=dict(prior_depth='prior',da3_depth='mvs_rgb',protection_pcd='initialization/lod2_pcd.ply'),
        visual_source='COLMAP_MVS_CAMERA_Z',reference_accessed=False,manual_weights_applied=False)
    write(inputroot/'input_manifest.json',manifest)
    write(inputroot/'mvs/bindings.json',dict(schema='JBGS_MVS_PGSR_INPUT_v1',region=cfg['region'],scientific_verdict=None,
        parent_input_manifest_sha256=sha256(inputroot/'input_manifest.json'),train=train,evaluation_names=[v['name'] for v in evaluation],
        neighbor_graph=dict(graph={Path(v['name']).stem:dict(selected=[]) for v in train}),
        config_sha256=None,note='Basic MVS mode does not use PGSR neighbors. Runtime config binding is finalized by the preparation review.'))
    write(out/'receipt.json',dict(status='PASS_CPU_INPUT_PREPARATION',scientific_verdict=None,counts=cfg['expected_counts'],
        config_sha256=sha256(args.config),input_manifest_sha256=sha256(inputroot/'input_manifest.json'),
        script_sha256=sha256(__file__),training_runs=0,manual_weight_arrays=0,elapsed_seconds=time.monotonic()-started))
    progress(out,'COMPLETE_CPU_INPUT_PREPARATION',elapsed_seconds=time.monotonic()-started)


if __name__=='__main__':
    try:main()
    except Exception as e:
        traceback.print_exc()
        if '--output' in sys.argv:
            out=Path(sys.argv[sys.argv.index('--output')+1])
            if out.exists():(out/'failure.json').write_text(json.dumps(dict(error=repr(e),traceback=traceback.format_exc(),scientific_verdict=None)))
        raise
