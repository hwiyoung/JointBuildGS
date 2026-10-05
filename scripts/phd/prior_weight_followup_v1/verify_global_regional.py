"""Same-point UAS and same-pixel MVS comparison of completed global/regional runs."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
import cv2
import open3d as o3d
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as Polygon

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def metrics(x):
    x=np.asarray(x,dtype=float);finite=np.isfinite(x);a=np.abs(x[finite])
    if not len(a):return dict(n=len(x),finite=0)
    return dict(n=len(x),finite=int(finite.sum()),mean_abs=float(a.mean()),median_abs=float(np.median(a)),
        p95_abs=float(np.quantile(a,.95)),signed_mean=float(x[finite].mean()),
        within_10cm=float((np.abs(x)<=.1).mean()),within_20cm=float((np.abs(x)<=.2).mean()),
        within_50cm=float((np.abs(x)<=.5).mean()),over_1m=float((np.abs(x)>1).mean()))
def select_roi(x,roi):
    return Polygon(roi['xy']).contains_points(x[:,:2],radius=1e-8)&(x[:,2]>=roi['z'][0])&(x[:,2]<roi['z'][1])

def main():
    assert Path('/.dockerenv').exists()
    ap=argparse.ArgumentParser();ap.add_argument('--config',default='/out/config.json');args=ap.parse_args()
    cfg=read(args.config);p=Path('/payload');out=Path('/out');v=p/cfg['viewer'];b=p/cfg['bundle']
    sys.path.insert(0,'/repo/scripts/phd/geogs_p1p2p3_v1/evaluation')
    from geometry import voxel_reference
    sys.path.insert(0,'/repo/src/phd/geogs_mvs_pgsr_v1')
    from mvs_depth import load_view_depth
    result=dict(scientific_verdict=None,scope=cfg['scope'],script_sha256=sha(__file__),config_sha256=sha(args.config),
                runtime=cfg['runtime'],inputs={},regions={},python=sys.version,numpy=np.__version__,open3d=o3d.__version__)
    def record(path):result['inputs'][str(path)]=sha(path);return path
    manifest=read(record(v/'prior_weights_v1/manifest.json'))
    for region in ['P1','P2','P3']:
        print('BEGIN',region,flush=True)
        display=next(r for r in manifest['regions'] if r['id']==region)
        global_ex=p/cfg['global_extractions']/(region+'.mvs.D0005_Pnative')
        new_ex=v/'prior_weights_v1'/region/'alpha_4/extraction'
        old_ex=v/('p1_weights_v1/alpha_4/extraction' if region=='P1' else 'p2p3_weights_v1/'+region+'/alpha_4/extraction')
        exs={'global_0005':global_ex,'regional_0005':new_ex,'regional_005':old_ex}
        receipts={k:read(record(x/'receipt.json')) for k,x in exs.items()}
        assert all(x['status']=='PASS' for x in receipts.values())
        for key in ['mesh_res','voxel_size_m','sdf_trunc_m','depth_trunc_m','frozen_render_controls']:
            assert receipts['global_0005']['realized_extraction'][key]==receipts['regional_0005']['realized_extraction'][key],key
        refpath=record(p/cfg['reference_root']/region/'reference.npz');raw=np.load(refpath)
        ref,ids=voxel_reference(raw['uas_xyz'],cfg['reference_voxel_m']);raw_ids=raw['uas_raw_rows'][ids]
        assert len(np.unique(raw_ids))==len(raw_ids)
        rois={'all_reference':np.ones(len(ref),dtype=bool)}
        rois.update({k:select_roi(ref,r) for k,r in cfg['rois'][region].items()})
        rr=dict(reference_count=len(ref),rois={k:dict(reference_count=int(s.sum()),surface={},vertical_top={}) for k,s in rois.items()},views=[])
        arrays=dict(reference_points=ref,reference_raw_rows=raw_ids,reference_array_indices=ids)
        for key,s in rois.items():arrays['roi_'+key]=s
        # Use original native meshes, not display buffers or Gaussian centers.
        for role,root in exs.items():
            meta=receipts[role]['surfaces']['raw'];path=record(root/meta['path']);assert sha(path)==meta['sha256']
            mesh=o3d.io.read_triangle_mesh(str(path));vertices=np.asarray(mesh.vertices);tri=np.asarray(mesh.triangles)
            # Full native surface: do not let a display crop alter nearest-surface distances.
            hi=np.array(display['bounds']['max'])+5
            vertices=vertices.astype(np.float32);tri=tri.astype(np.uint32)
            scene=o3d.t.geometry.RaycastingScene(nthreads=2);scene.add_triangles(o3d.core.Tensor(vertices),o3d.core.Tensor(tri))
            distance=scene.compute_distance(o3d.core.Tensor(ref.astype(np.float32)),nthreads=2).numpy();arrays[role+'_distance']=distance
            origin=ref.astype(np.float32).copy();origin[:,2]=hi[2]
            rays=np.column_stack([origin,np.tile([0,0,-1],(len(ref),1))]).astype(np.float32)
            hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy();zerror=origin[:,2]-hit-ref[:,2]
            arrays[role+'_top_z_error']=zerror
            for key,s in rois.items():
                rr['rois'][key]['surface'][role]=metrics(distance[s]);rr['rois'][key]['vertical_top'][role]=metrics(zerror[s])
            print(region,role,'triangles',len(tri),'GT mean',float(distance.mean()),flush=True)
            del scene,mesh,vertices,tri
        np.savez_compressed(out/(region+'_paired_surface.npz'),**arrays)
        for key,s in rois.items():
            delta=arrays['regional_0005_distance'][s]-arrays['global_0005_distance'][s]
            rr['rois'][key]['paired_difference']=dict(metrics(delta),improved_gt_distance_over_10cm=float((delta<-.1).mean()),worsened_gt_distance_over_10cm=float((delta>.1).mean()))
        fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
        for ax,role in zip(axes,['global_0005','regional_0005','delta']):
            values=arrays['regional_0005_distance']-arrays['global_0005_distance'] if role=='delta' else arrays[role+'_distance']
            h=ax.scatter(ref[:,0],ref[:,1],c=values,s=.5,cmap='coolwarm' if role=='delta' else 'viridis',vmin=-.5 if role=='delta' else 0,vmax=.5)
            for key,roi in cfg['rois'][region].items():
                poly=np.array(roi['xy']+[roi['xy'][0]]);ax.plot(poly[:,0],poly[:,1],lw=.8,color='black');ax.text(*poly[:4].mean(0),key,fontsize=6,color='black')
            ax.set_aspect('equal');ax.set_title(region+' '+role);fig.colorbar(h,ax=ax,label='UAS-to-mesh distance (m)' if role!='delta' else 'New - global distance (m)')
        fig.savefig(out/(region+'_gt_comparison.png'),dpi=150);plt.close(fig)
        # Input-fit comparison on exact same representative image/depth pixel identities.
        bp=p/cfg['global_root']/'inputs_v2'/region;binding=read(record(bp/'bindings.json'))
        masks=None if region=='P1' else read(record(b/region/'mask/manifest.json'))
        for view in display['views']:
            if view['split']!='train':continue
            name=view['image_name'];index=next(i for i,x in enumerate(binding['train']) if x['name']==name);camera=binding['train'][index]
            target,valid,_=load_view_depth(camera,verify_rgb=False,depth_path=record(bp/camera['local_depth']))
            labelpath=b/region/'mask/r1_mask.npz' if region=='P1' else b/region/'mask'/next(x['path'] for x in masks['views'] if x['camera']==Path(name).stem)
            labels=np.load(record(labelpath))['region_id'];pred={}
            for role,root in exs.items():
                path=record(root/f'model/train/ours_30000/vis/depth_{index:05d}.tiff');pred[role]=np.asarray(Image.open(path),dtype=np.float32)
                if role!='global_0005':
                    key='prior_0005_alpha4' if role=='regional_0005' else 'alpha_4';assert sha(path)==view['conditions'][key]['source_depth_sha256']
            common=valid&np.logical_and.reduce([np.isfinite(x)&(x>0) for x in pred.values()])
            subsets={'R'+str(i):labels==i for i in [1,2,3]}
            if region=='P1':
                yy,xx=np.indices(target.shape);rays=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@np.linalg.inv(np.array(camera['K'])).T
                xyz=(rays*target[...,None]-np.array(camera['t']))@np.array(camera['R'])
                for key,roi in cfg['rois'][region].items():subsets[key]=select_roi(xyz.reshape(-1,3),roi).reshape(target.shape)
            vr=dict(camera=name,index=index,subsets={})
            for key,s in subsets.items():
                selected=s&common;vr['subsets'][key]=dict(n=int(selected.sum()),input_valid=int((s&valid).sum()),
                    fit_mvs={k:metrics(x[selected]-target[selected]) for k,x in pred.items()},
                    global_to_regional_change=metrics(pred['regional_0005'][selected]-pred['global_0005'][selected]))
            rr['views'].append(vr)
            fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
            axes[0].imshow(Image.open(v/view['original']['url'].removeprefix('/data/')))
            axes[0].contour(labels==1,levels=[.5],colors='red',linewidths=.5);axes[0].set_title(region+' '+Path(name).stem[-6:]+' / R1')
            delta=pred['regional_0005']-pred['global_0005'];err=np.abs(pred['regional_0005']-target)-np.abs(pred['global_0005']-target)
            for ax,a,title in zip(axes[1:],[delta,err],['Regional - global depth (m)','Change in MVS residual (blue = smaller)']):
                h=ax.imshow(np.where(common,a,np.nan),vmin=-.5,vmax=.5,cmap='coolwarm');ax.set_title(title);fig.colorbar(h,ax=ax,shrink=.7)
            for ax in axes:ax.axis('off')
            fig.savefig(out/(region+'_'+Path(name).stem[-6:]+'_depth_comparison.png'),dpi=140);plt.close(fig)
        result['regions'][region]=rr
        (out/'metrics.partial.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    result['status']='PASS_EXISTING_RESULT_DIAGNOSTIC'
    (out/'metrics.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print('PASS',flush=True)

if __name__=='__main__':main()
