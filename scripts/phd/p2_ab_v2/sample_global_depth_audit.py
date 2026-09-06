"""Global current-MVS front-depth diagnostic, without external reference access."""
import argparse
from pathlib import Path
import shutil
import time
import numpy as np
from scripts.phd.p2_ab_v2.sample_build import read,write,record,quantiles
from scripts.phd.p2_ab_v2.sample_depth_mapping import read_colmap_array,depth_intrinsics
from scripts.phd.mvs_als_source_relation_v1.run import parse_binary_ply_vertices


def run(config_path):
    started=time.time();cfg=read(config_path);root=Path(cfg['artifact_root'])
    out=root/cfg['output_relative_root'];out.mkdir(parents=True,exist_ok=False)
    source=root/cfg['global_native_relative_path'];source_record=record(source,cfg['global_native_sha256'])
    raw,_,_=parse_binary_ply_vertices(source)
    rows={v['image_id']:v for v in read(root/cfg['common_relative_root']/'views.json')['views']}
    views=[]
    for iid in cfg['image_ids']:
        view=rows[iid];depth=read_colmap_array(view['geometric_depth']['path'])
        views.append({'row':view,'depth':depth,'zbuf':np.full(depth.shape,np.inf),'Kd':depth_intrinsics(view),
                      'R':np.array(view['R']),'t':np.array(view['t'])})
    for begin in range(0,len(raw),cfg['chunk_points']):
        chunk=raw[begin:begin+cfg['chunk_points']];xyz=np.column_stack([chunk[k] for k in ['x','y','z']]).astype(np.float64)
        for v in views:
            camera=xyz@v['R'].T+v['t'];p=camera@v['Kd'].T
            uv=p[:,:2]/p[:,2:3];ix=np.floor(uv+.5).astype(np.int64);h,w=v['depth'].shape
            inside=(camera[:,2]>0)&(ix[:,0]>=0)&(ix[:,0]<w)&(ix[:,1]>=0)&(ix[:,1]<h)
            np.minimum.at(v['zbuf'],(ix[inside,1],ix[inside,0]),camera[inside,2])
        if begin%10000000==0:print(f'global native points {min(begin+len(chunk),len(raw))}/{len(raw)}',flush=True)
    result=[]
    for v in views:
        iid=v['row']['image_id'];prior=np.load(root/cfg['p2_depth_audit_relative_root']/f'view_{iid}_mvs_zbuffer.npz')
        p2support=prior['source_support'];sourcez=prior['source_camera_z'];z=v['zbuf'];depth=v['depth']
        known=p2support&np.isfinite(z)&np.isfinite(depth)&(depth>0)
        gap=z[known]-depth[known]
        globalfront=known&(sourcez-z>1)
        yy,xx=np.nonzero(globalfront);ray=np.column_stack([xx,yy,np.ones(len(xx))])@np.linalg.inv(v['Kd']).T
        world=(ray*z[globalfront,None]-v['t'])@v['R']
        insidep2=(world[:,0]>=110)&(world[:,0]<158)&(world[:,1]>=86)&(world[:,1]<132)&(world[:,2]>=-49.386)&(world[:,2]<-17.679)
        entry={'image_id':iid,'p2_projected_pixel_count':int(p2support.sum()),'global_mvs_and_depth_known_pixels':int(known.sum()),
               'global_mvs_z_minus_colmap_depth_m':quantiles(gap),'abs_gap_le_0p25m_count':int((np.abs(gap)<=.25).sum()),
               'abs_gap_le_1m_count':int((np.abs(gap)<=1).sum()),'global_mvs_front_of_p2_by_gt1m_count':int(globalfront.sum()),
               'global_foreground_backprojection_xyz_quantiles':quantiles(world),'global_foreground_outside_p2_count':int((~insidep2).sum())}
        result.append(entry);print(__import__('json').dumps(entry),flush=True)
        np.savez_compressed(out/f'view_{iid}_global_comparison.npz',global_mvs_z=z.astype(np.float32),colmap_z=depth,p2_mvs_z=sourcez,
                            p2_support=p2support,global_and_colmap_known=known,K_depth=v['Kd'])
    write(out/'global_depth_audit_receipt.json',{'task_id':cfg['task_id'],'scientific_verdict':None,'results':result,
           'source':source_record,'native_point_count':len(raw),'reference_accessed':False,'config':record(config_path),
           'script':record(__file__),'mapper':record(Path(__file__).with_name('sample_depth_mapping.py')),
           'docker_image_id':cfg['docker_image_id'],'elapsed_seconds':time.time()-started,
           'interpretation':'Same-lineage full-scene MVS numerical cross-check; evidence of foreground support is not a calibrated currentness or metric-accuracy guarantee.'})
    for p in [Path(__file__),config_path]:shutil.copyfile(p,out/p.name)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);run(Path(parser.parse_args().config))
