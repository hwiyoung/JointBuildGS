#!/usr/bin/env python3
"""Frozen five-region image/support census on existing exact-937 inputs, CPU only."""
import argparse
import csv
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
from datetime import datetime, timezone

import numpy as np
from plyfile import PlyData
from scipy import sparse

sys.path.insert(0,'/repo')
from src.stage2.colmap_io import read_cameras_bin,read_images_bin
from src.phd.region_view_support_v1 import (
    sha256,object_basis,region_mask,prism_mask,corners_xy,read_depth,ray_grid,
    rgb_native_indices,backproject,query_points,concentration)


def write_json(path,data):
    path=Path(path)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    tmp.replace(path)


def write_csv(path,rows):
    if not rows:
        return
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def progress(out,stage,**kwargs):
    row=dict(stage=stage,time_utc=datetime.now(timezone.utc).isoformat(),**kwargs)
    write_json(out/'status.json',row)
    print(json.dumps(row),flush=True)


def check_file(path,expected):
    actual=sha256(path)
    if actual!=expected:
        raise ValueError(f'Frozen input hash mismatch: {path}')
    return dict(path=str(path),bytes=Path(path).stat().st_size,sha256=actual)


def make_references(cfg,basis,out):
    progress(out,'READING_FUSED_INPUT')
    record=check_file('/fused/dim_dense.ply',cfg['inputs']['fused_mvs_sha256'])
    vertices=PlyData.read('/fused/dim_dense.ply',mmap='r')['vertex'].data
    stride=cfg['audit']['fused_point_stride']
    original=np.arange(0,len(vertices),stride,dtype=np.int64)
    p=vertices[::stride]
    xyz=np.column_stack((p['x'],p['y'],p['z'])).astype(np.float32)
    uv=xyz[:,:2]@basis.T
    inside=(np.isfinite(xyz).all(axis=1)&(uv[:,0]>=-140)&(uv[:,0]<=330)&
            (uv[:,1]>=-95)&(uv[:,1]<=130)&(xyz[:,2]>=-90)&(xyz[:,2]<80))
    xyz=xyz[inside];original=original[inside]
    _,first=np.unique(np.floor(xyz/cfg['audit']['fused_reference_voxel_m']).astype(np.int32),axis=0,return_index=True)
    first=np.sort(first);xyz=xyz[first];original=original[first]
    refs={}
    for region in cfg['regions']:
        keep=region_mask(xyz,region,basis,cfg['frame']['z_m'])
        refs[region['id']]=dict(xyz=xyz[keep],source_rows=original[keep])
    for name,prism in cfg['legacy_prisms'].items():
        keep=prism_mask(xyz,prism)
        refs['old_'+name]=dict(xyz=xyz[keep],source_rows=original[keep])
    with np.load('/p1_ground/reference_sample_support.npz',allow_pickle=False) as z:
        keep=z['r1_in_original_p1']
        refs['P1_ground']=dict(xyz=z['source_xyz'][keep].astype(np.float64),
                              source_rows=np.flatnonzero(keep),native_pixels=z['source_native_xy'][keep])
    for name,ref in refs.items():
        if not len(ref['xyz']):
            raise ValueError('Empty reference-support set: '+name)
        np.savez_compressed(out/(name+'_reference_points.npz'),**ref)
    return refs,record,xyz


def masks_for(xyz,valid,cfg,basis):
    result={}
    uv=xyz[:,:2]@basis.T
    zvalid=valid&(xyz[:,2]>=cfg['frame']['z_m'][0])&(xyz[:,2]<cfg['frame']['z_m'][1])
    for region in cfg['regions']:
        result[region['id']]=(zvalid&(uv[:,0]>=region['u_m'][0])&(uv[:,0]<region['u_m'][1])&
                             (uv[:,1]>=region['v_m'][0])&(uv[:,1]<region['v_m'][1]))
    for name,prism in cfg['legacy_prisms'].items():
        result['old_'+name]=valid&prism_mask(xyz,prism)
    return result,uv


def summarize_group(names,rows,ref,agreement,chosen,tolerances):
    chosen=np.asarray(chosen,dtype=np.int64)
    weights=np.array([rows[i]['support_mass'] for i in chosen])
    summary=concentration(weights)
    rank=summary.pop('ranking')
    summary['top_views']=[dict(name=names[chosen[j]],fraction=float(weights[j]/weights.sum()),
                                native_pixels=rows[chosen[j]]['native_pixels'],
                                rgb_pixels=rows[chosen[j]]['rgb_pixels']) for j in rank[:15]]
    summary['view_count']=len(chosen)
    summary['native_views_at_least']={str(n):int(sum(rows[i]['native_pixels']>=n for i in chosen)) for n in (1,100,1000)}
    summary['same_point_support']={}
    for k,tol in enumerate(tolerances):
        counts=agreement[k,chosen].sum(axis=0)
        summary['same_point_support'][str(tol)]={
            'samples':len(counts),'zero_fraction':float((counts==0).mean()),
            'exactly_one_fraction':float((counts==1).mean()),'exactly_two_fraction':float((counts==2).mean()),
            'at_least_three_fraction':float((counts>=3).mean()),
            'median_views':float(np.median(counts)),'max_views':int(counts.max()),
            'top_view_name':names[chosen[np.argmax(agreement[k,chosen].sum(axis=1))]] if len(chosen) else None,
            'top_view_support_fraction':float(agreement[k,chosen].sum(axis=1).max()/len(counts)) if len(chosen) else None}
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output);out.mkdir(exist_ok=False)
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker execution required')
    cfg=json.loads(Path(args.config).read_text());start=time.monotonic()
    shutil.copyfile(args.config,out/'config.json')
    basis=object_basis(cfg['frame']['u_axis_angle_degrees_ccw_from_easting'])
    if not np.allclose(basis@basis.T,np.eye(2),atol=1e-12):raise ValueError('Nonorthogonal basis')
    corners={r['id']:corners_xy(r,basis) for r in cfg['regions']}
    for r in cfg['regions']:
        for legacy in r['contains_legacy']:
            p=cfg['legacy_prisms'][legacy]
            c=np.array([[x,y,0] for x in p['x'] for y in p['y']])
            if not region_mask(c,r,basis,cfg['frame']['z_m']).all():raise ValueError('Legacy crop not fully included: '+legacy)
    features=[]
    for r in cfg['regions']:
        world=corners[r['id']]+np.array(cfg['frame']['world_shift_xyz_m'][:2])
        features.append(dict(type='Feature',properties={**r,'crs':'EPSG:25832'},
                             geometry=dict(type='Polygon',coordinates=[world.tolist()])))
    write_json(out/'regions_epsg25832.geojson',dict(type='FeatureCollection',
        crs=dict(type='name',properties=dict(name='urn:ogc:def:crs:EPSG::25832')),features=features))
    files={}
    for name in ('cameras','images'):
        files[name]=check_file('/cameras/sparse/'+name+'.bin',cfg['inputs'][name+'_bin_sha256'])
    files['crosswalk']=check_file('/repo/'+cfg['inputs']['crosswalk_repo_relative'],cfg['inputs']['crosswalk_sha256'])
    members=json.loads(Path('/repo',cfg['inputs']['crosswalk_repo_relative']).read_text())['rows']
    cameras=read_cameras_bin(Path('/cameras/sparse/cameras.bin'));images=read_images_bin(Path('/cameras/sparse/images.bin'))
    members=sorted(members,key=lambda r:r['basename']);names=[r['basename'] for r in members]
    if len(members)!=937 or len(set(names))!=937:raise ValueError('Exact-937 membership failed')
    views=[]
    for member in members:
        im=images[member['colmap_image_id']];cam=cameras[im.camera_id]
        if im.name!=member['basename'] or cam.model!='PINHOLE':raise ValueError('Camera crosswalk failed')
        views.append((im,cam))
    bindings={};bound={}
    for legacy in ('P1','P2','P3'):
        binding=json.loads(Path('/bindings/'+legacy+'.json').read_text());bindings[legacy]=binding
        for v in binding['train']:
            if v['name'] in bound and v!=bound[v['name']]:
                # Region-local annotations vary; camera/depth bytes must not.
                for key in ('R','t','K','width','height','maps','sha256'):
                    if v[key]!=bound[v['name']][key]:raise ValueError('Conflicting frozen camera binding')
            bound[v['name']]=v
    refs,files['fused'],overview=make_references(cfg,basis,out)
    files['p1_ground']=dict(path='/p1_ground/reference_sample_support.npz',sha256=sha256('/p1_ground/reference_sample_support.npz'))
    groups=list(refs);tolerances=cfg['audit']['depth_agreement_tolerances_m'];primary=tolerances.index(.5)
    agreements={k:np.zeros((len(tolerances),937,len(v['xyz'])),dtype=bool) for k,v in refs.items()}
    records={k:[] for k in groups};camera_records=[];cache={};voxel_rows={r['id']:[] for r in cfg['regions']}
    raw_hist={r['id']:[] for r in cfg['regions']};voxel_shape={}
    for r in cfg['regions']:
        voxel_shape[r['id']]=tuple(int(np.ceil((b[1]-b[0])/step)) for b,step in
            zip((r['u_m'],r['v_m'],cfg['frame']['z_m']),(5.,5.,2.)))
    for index,(im,cam) in enumerate(views):
        rgb_path=Path('/cameras/images')/im.name;depth_path=Path('/cameras/stereo/depth_maps')/(im.name+'.geometric.bin')
        depth,meta=read_depth(depth_path);meta['frame']='CAMERA_Z'
        K=cam.K();R=im.R();t=im.tvec
        nk=K.copy();nk[0]*=meta['width']/cam.width;nk[1]*=meta['height']/cam.height
        rgb_sha=sha256(rgb_path)
        if im.name in bound:
            old=bound[im.name]
            for a,b in ((R,old['R']),(t,old['t']),(K,old['K']),(nk,old['maps']['depth']['K'])):
                if not np.allclose(a,b,rtol=0,atol=1e-8):raise ValueError('Frozen camera geometry changed')
            if meta['sha256']!=old['maps']['depth']['sha256'] or rgb_sha!=old['sha256']:raise ValueError('Frozen bytes changed')
        key=(cam.id,meta['width'],meta['height'])
        if key not in cache:
            rays,lookup,in_bounds=rgb_native_indices(K,nk,cam.width,cam.height,meta['width'],meta['height'])
            cache[key]=(ray_grid(nk,meta['width'],meta['height']),rays,lookup,in_bounds)
        nrays,rrays,lookup,in_bounds=cache[key]
        nv=np.isfinite(depth.ravel())&(depth.ravel()>0)
        nxyz=backproject(np.where(nv,depth.ravel(),0),nrays,R,t)
        native_masks,_=masks_for(nxyz,nv,cfg,basis)
        rd=depth.ravel()[lookup];rv=in_bounds&np.isfinite(rd)&(rd>0);denom=int(rv.sum())
        rxyz=backproject(np.where(rv,rd,0),rrays,R,t)
        rgb_masks,uv=masks_for(rxyz,rv,cfg,basis)
        camera_records.append(dict(index=index,image_id=int(im.id),name=im.name,width=cam.width,height=cam.height,
            K=K.tolist(),native_K=nk.tolist(),R=R.tolist(),t=t.tolist(),center=(-R.T@t).tolist(),
            rgb_sha256=rgb_sha,rgb_bytes=rgb_path.stat().st_size,native_depth=meta,
            valid_native_pixels=int(nv.sum()),valid_rgb_pixels=denom,frozen_binding_verified=im.name in bound))
        for group,ref in refs.items():
            frame,has,residual,support=query_points(ref['xyz'],R,t,nk,depth,tolerances)
            agreements[group][:,index]=support
            if group=='P1_ground':
                native_count=int(support[primary].sum());rgb_count=0;mass=0.
                if im.name=='DJI_20241217084553_0100_D.JPG':
                    if not support[0].all() or np.abs(residual).max()>1e-4:raise ValueError('P1 self-projection failed')
            else:
                native_count=int(native_masks[group].sum());rgb_count=int(rgb_masks[group].sum())
                mass=rgb_count/denom if denom else 0.
            records[group].append(dict(index=index,name=im.name,native_pixels=native_count,rgb_pixels=rgb_count,
                full_valid_rgb_pixels=denom,support_mass=mass,reference_points=len(frame),
                projected_reference_points=int(frame.sum()),depth_present_reference_points=int(has.sum()),
                agree_025=int(support[0].sum()),agree_05=int(support[1].sum()),agree_10=int(support[2].sum())))
        for region in cfg['regions']:
            rid=region['id'];m=rgb_masks[rid]
            coords=np.column_stack((np.floor((uv[m,0]-region['u_m'][0])/5),
                                    np.floor((uv[m,1]-region['v_m'][0])/5),
                                    np.floor((rxyz[m,2]-cfg['frame']['z_m'][0])/2))).astype(np.int32)
            flat=np.ravel_multi_index(coords.T,voxel_shape[rid]) if len(coords) else np.zeros(0,dtype=np.int64)
            bins,counts=np.unique(flat,return_counts=True)
            voxel_rows[rid].append((bins,counts.astype(np.uint32)))
        if index%20==0 or index==936:
            progress(out,'SCANNING_CAMERAS',completed=index+1,total=937,elapsed_seconds=round(time.monotonic()-start,1))
    write_json(out/'camera_bindings.json',dict(files=files,cameras=camera_records))
    summary=dict(task_id=cfg['task_id'],status='PASS_INPUT_SUPPORT_AUDIT',scientific_verdict=None,
                 regions={},legacy={},inputs=files,resources=cfg['resources'],elapsed_seconds=time.monotonic()-start,
                 runtime=dict(python=platform.python_version(),numpy=np.__version__),
                 actual_loss_or_gradient_measured=False,training_run_count=0)
    selections={}
    for region in cfg['regions']:
        rid=region['id'];rows=records[rid];nref=len(refs[rid]['xyz'])
        minimum=max(10,int(np.ceil(.01*nref)))
        candidate=np.array([i for i,row in enumerate(rows) if row['projected_reference_points']>=minimum or row['native_pixels']>=100],dtype=int)
        eval_idx=candidate[np.arange(len(candidate))%8==0];train_idx=candidate[np.arange(len(candidate))%8!=0]
        selections[rid]=dict(candidates=candidate.tolist(),train=train_idx.tolist(),evaluation=eval_idx.tolist())
        value=dict(candidate_count=len(candidate),training_candidate_count=len(train_idx),evaluation_candidate_count=len(eval_idx),
                   projected_reference_minimum=minimum,reference_point_count=nref,
                   all_candidates=summarize_group(names,rows,refs[rid],agreements[rid],candidate,tolerances),
                   train=summarize_group(names,rows,refs[rid],agreements[rid],train_idx,tolerances))
        counts_by_camera=voxel_rows[rid];lengths=[len(pair[0]) for pair in counts_by_camera]
        csr=sparse.csr_matrix((np.concatenate([p[1] for p in counts_by_camera]),
                              np.concatenate([p[0] for p in counts_by_camera]),
                              np.r_[0,np.cumsum(lengths)]),shape=(937,int(np.prod(voxel_shape[rid]))))
        sparse.save_npz(out/(rid+'_rgb_voxel_counts.npz'),csr)
        sub=csr[train_idx].astype(np.float64)
        denominators=np.array([max(1,camera_records[i]['valid_rgb_pixels']) for i in train_idx])
        mass=sub.multiply(1/denominators[:,None]).tocsr();total=np.asarray(mass.sum(axis=0)).ravel()
        top=mass.max(axis=0).toarray().ravel();active=total>0
        supported=(sub>=10).sum(axis=0).A.ravel()
        material=supported>0
        value['local_voxels']=dict(shape=voxel_shape[rid],size_m=[5,5,2],active_voxels=int(active.sum()),
            material_voxels=int(material.sum()),one_view_fraction=float((supported[material]==1).mean()),
            two_view_fraction=float((supported[material]==2).mean()),
            top1_mass_ge_80_fraction=float((top[active]/total[active]>=.8).mean()),
            denominator='occupied 5m x 5m x 2m bins; not surface area; endpoints in a bin need not be the same surface')
        summary['regions'][rid]=value
        for i,row in enumerate(rows):
            row['role']='train_candidate' if i in selections[rid]['train'] else ('evaluation_candidate' if i in selections[rid]['evaluation'] else 'not_selected')
        write_csv(out/(rid+'_views.csv'),rows)
        np.savez_compressed(out/(rid+'_local_support.npz'),total=total,top=top,material_views=supported,shape=np.array(voxel_shape[rid]))
    for old,binding in bindings.items():
        group='old_'+old;train_idx=[names.index(v['name']) for v in binding['train']]
        newrid='R2' if old=='P2' else 'R1'
        summary['legacy'][old]=dict(original_train=summarize_group(names,records[group],refs[group],agreements[group],train_idx,tolerances),
            expanded_train=summarize_group(names,records[group],refs[group],agreements[group],selections[newrid]['train'],tolerances))
        write_csv(out/(group+'_views.csv'),records[group])
    if summary['legacy']['P1']['original_train']['native_views_at_least']['1']!=46:
        raise ValueError('Frozen P1 native >0 support did not reproduce 46/98')
    ground=agreements['P1_ground'];oldids=[names.index(v['name']) for v in bindings['P1']['train']]
    ground_summary={}
    for label,ids in [('original_98',oldids),('expanded_R1_train',selections['R1']['train']),('all_937',list(range(937)))]:
        other=[i for i in ids if names[i]!='DJI_20241217084553_0100_D.JPG']
        count=ground[primary,other].sum(axis=0)
        ranked=sorted(ids,key=lambda i:-records['P1_ground'][i]['agree_05'])
        ground_summary[label]=dict(views=len(ids),points=ground.shape[2],
            no_other_view_fraction=float((count==0).mean()),any_other_view_fraction=float((count>0).mean()),
            two_other_views_fraction=float((count>=2).mean()),three_other_views_fraction=float((count>=3).mean()),
            top_views=[dict(name=names[i],support_fraction=records['P1_ground'][i]['agree_05']/ground.shape[2]) for i in ranked[:15]])
    summary['P1_correction_ground']=ground_summary
    write_csv(out/'P1_correction_ground_views.csv',records['P1_ground'])
    write_json(out/'candidate_memberships.json',dict(names=names,regions=selections))
    for group,arr in agreements.items():
        np.savez_compressed(out/(group+'_point_support.npz'),packed=np.packbits(arr,axis=2),
                            point_count=arr.shape[2],tolerances=np.asarray(tolerances),names=np.asarray(names))
    np.savez_compressed(out/'overview_input_points.npz',xyz=overview)
    summary['elapsed_seconds']=time.monotonic()-start
    write_json(out/'summary.json',summary)
    output_files={p.name:dict(sha256=sha256(p),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file() and p.name!='status.json'}
    write_json(out/'receipt.json',dict(status='PASS',scientific_verdict=None,config_sha256=sha256(args.config),
               driver_sha256=sha256(__file__),core_sha256=sha256('/repo/src/phd/region_view_support_v1.py'),
               git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'),output_files=output_files,
               no_training=True,no_reference_data=True))
    progress(out,'COMPLETE',elapsed_seconds=round(time.monotonic()-start,1))
    print(json.dumps({r:{k:v for k,v in x.items() if k.endswith('_count')} for r,x in summary['regions'].items()}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        args=sys.argv
        if '--output' in args:
            output=Path(args[args.index('--output')+1])
            if output.exists():
                write_json(output/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc(),scientific_verdict=None))
        raise
