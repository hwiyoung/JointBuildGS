"""Verify real native-source/depth ray mapping, preserving depth absence and source Z."""
import argparse
from pathlib import Path
import shutil
import time
import numpy as np
from scripts.phd.p2_ab_v2.sample_build import read,write,record,quantiles
from scripts.phd.p2_ab_v2.sample_depth_mapping import read_colmap_array,depth_intrinsics,sample_depth_rays
from src.stage2.colmap_io import read_array as legacy_read_array


def run(config_path):
    started=time.time();cfg=read(config_path);root=Path(cfg['artifact_root'])
    common=root/cfg['common_relative_root'];out=root/cfg['output_relative_root'];out.mkdir(parents=True,exist_ok=False)
    views={v['image_id']:v for v in read(common/'views.json')['views']};native=np.load(common/'native_geometry.npz')
    result=[]
    for iid in cfg['image_ids']:
        view=views[iid];record(view['geometric_depth']['path'],view['geometric_depth']['sha256'])
        depth=read_colmap_array(view['geometric_depth']['path']);assert np.array_equal(depth,legacy_read_array(view['geometric_depth']['path']))
        Kd=depth_intrinsics(view);R=np.array(view['R']);t=np.array(view['t']);K=np.array(view['K'])
        detail={'image_id':iid,'K_depth':Kd.tolist(),'depth_dimensions':list(depth.shape[::-1]),'source':{},
                'depth_reader_bitwise_equal_for_one_channel':True}
        for source in ['mvs','als']:
            xyz=native[source+'_xyz'].astype(np.float64);cam=xyz@R.T+t
            uvh=cam@K.T;uv=uvh[:,:2]/uvh[:,2:3]
            mapped=sample_depth_rays(view,uv,depth=depth)
            direct=cam@Kd.T;direct=direct[:,:2]/direct[:,2:3]
            err=float(np.max(np.abs(direct-mapped['depth_uv'])));assert err<1e-8
            ix=np.floor(mapped['depth_uv']+.5).astype(int);h,w=depth.shape
            valid=(cam[:,2]>0)&(ix[:,0]>=0)&(ix[:,0]<w)&(ix[:,1]>=0)&(ix[:,1]<h)
            zbuf=np.full((h,w),np.inf);np.minimum.at(zbuf,(ix[valid,1],ix[valid,0]),cam[valid,2])
            support=np.isfinite(zbuf);known=support&np.isfinite(depth)&(depth>0)
            # This excludes rear native-source samples sharing a depth-map pixel.
            gap=zbuf[known]-depth[known]
            margin=cfg['foreground_margin_m']
            nearest_known=valid&mapped['nearest_known']
            all4=valid&mapped['all_four_known']
            source_detail={'native_points':len(xyz),'projected_depth_pixels':int(support.sum()),
                           'depth_known_pixels':int(known.sum()),'depth_unknown_pixels':int((support&~known).sum()),
                           'zbuffer_source_minus_global_depth_m':quantiles(gap),
                           'zbuffer_positive_foreground_gap_gt_margin_count':int((gap>margin).sum()),
                           'zbuffer_negative_gap_lt_minus_margin_count':int((gap < -margin).sum()),
                           'zbuffer_abs_gap_le_0p25m_count':int((np.abs(gap)<=.25).sum()),
                           'zbuffer_abs_gap_le_1m_count':int((np.abs(gap)<=1).sum()),
                           'nearest_point_depth_known':int(nearest_known.sum()),
                           'conservative_four_pixel_known_points':int(all4.sum()),
                           'conservative_foreground_points':int((all4&(mapped['footprint_max_z']+margin<cam[:,2])).sum()),
                           'ray_mapping_vs_direct_projection_max_abs_px':err}
            detail['source'][source]=source_detail
            np.savez_compressed(out/f'view_{iid}_{source}_zbuffer.npz',source_camera_z=zbuf.astype(np.float32),
                                global_depth=depth,source_support=support,depth_known=known,K_depth=Kd)
        normal=read_colmap_array(view['geometric_normal']['path']);oldnormal=legacy_read_array(view['geometric_normal']['path'])
        n=np.linalg.norm(normal,axis=-1);oldn=np.linalg.norm(oldnormal,axis=-1);validn=n>1e-4;oldvalid=oldn>1e-4
        detail['normal_channel_audit']={'path':view['geometric_normal']['path'],'sha256':view['geometric_normal']['sha256'],
             'bitwise_identical_to_legacy':bool(np.array_equal(normal,oldnormal)),
             'official_order_norm_on_nonzero':quantiles(n[validn]),'legacy_order_norm_on_nonzero':quantiles(oldn[oldvalid]),
             'official_near_unit_fraction_on_nonzero':float((np.abs(n[validn]-1)<.01).mean()),
             'legacy_near_unit_fraction_on_nonzero':float((np.abs(oldn[oldvalid]-1)<.01).mean())}
        result.append(detail);print(__import__('json').dumps(detail),flush=True)
    write(out/'depth_audit_receipt.json',{'task_id':cfg['task_id'],'scientific_verdict':None,'results':result,
        'status':'PASS_RAY_MAPPING_AND_SINGLE_CHANNEL_LAYOUT; MULTICHANNEL_LEGACY_MISMATCH_RECORDED',
        'reference_accessed':False,'config':record(config_path),'source':record(__file__),
        'mapper_source':record(Path(__file__).with_name('sample_depth_mapping.py')),'common':record(common/'sample_manifest.json'),
        'docker_image_id':cfg['docker_image_id'],'elapsed_seconds':time.time()-started,
        'limits':['Depth shares image/MVS lineage and is not an independent source eligibility test.',
                  'Foreground threshold is a development convention, not a calibrated bound.',
                  'Unknown depth does not reject the prior.',
                  'Native source is bounded to P2; global COLMAP scene may include real foreground outside P2.',
                  'Legacy normal parsing mismatch is demonstrated on these files only; no retrospective result impact is inferred.']})
    for p in [Path(__file__),Path(__file__).with_name('sample_depth_mapping.py'),config_path]:shutil.copyfile(p,out/p.name)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);run(Path(parser.parse_args().config))
