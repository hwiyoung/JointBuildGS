#!/usr/bin/env python3
"""R1-wide source availability and source-surface relation audit, never weights."""
import argparse
import csv
import json
from pathlib import Path
import sys
import time
import numpy as np
import open3d as o3d
from PIL import Image
from plyfile import PlyData
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
sys.path.insert(0,'/repo')
from src.phd.region_view_support_v1 import sha256,object_basis,region_mask,ray_grid,read_depth,query_points


def write(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def progress(out,stage,**kw):
    value=dict(stage=stage,unix=time.time(),**kw);(out/'status.json').write_text(json.dumps(value)+'\n');print(json.dumps(value),flush=True)


def project(xyz,v):
    cam=xyz@np.array(v['R']).T+v['t'];z=cam[:,2];q=cam@np.array(v['maps']['depth']['K']).T
    uv=q[:,:2]/np.maximum(z[:,None],1e-9)
    meta=v['maps']['depth'];frame=(z>0)&(uv[:,0]>=2)&(uv[:,1]>=2)&(uv[:,0]<meta['width']-2)&(uv[:,1]<meta['height']-2)
    return z,uv,frame


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--output',required=True);args=ap.parse_args()
    started=time.time();cfg=json.loads(Path(args.config).read_text());out=Path(args.output);out.mkdir(exist_ok=False)
    write(out/'config.json',cfg);root=Path('/input');audit=Path('/audit')
    assert sha256(root/'input_manifest.json')==cfg['input_manifest_sha256']
    assert sha256(audit/'receipt.json')==cfg['audit_receipt_sha256']
    oldreceipt=json.loads((audit/'receipt.json').read_text());validated={}
    for name in ('R1_reference_points.npz','R1_point_support.npz','candidate_memberships.json','config.json'):
        actual=sha256(audit/name);assert actual==oldreceipt['output_files'][name]['sha256'];validated[name]=actual
    manifest=json.loads((root/'input_manifest.json').read_text());bound={r['path']:r for r in manifest['files']}
    for name in ('scene/split_manifest.json','surface/mesh_arrays.npz','initialization/sample_membership.npz'):
        actual=sha256(root/name);assert actual==bound[name]['sha256'];validated[name]=actual
    oldcfg=json.loads((audit/'config.json').read_text());assert sha256('/fused.ply')==oldcfg['inputs']['fused_mvs_sha256']
    views=json.loads((root/'scene/split_manifest.json').read_text())['train'];assert len(views)==588
    basis=object_basis(cfg['frame']['u_axis_angle_degrees_ccw_from_easting']);region=cfg['region'];zb=cfg['frame']['z_m']
    ref=np.load(audit/'R1_reference_points.npz');mxyz=ref['xyz'];vertex=PlyData.read('/fused.ply',mmap='r')['vertex'].data
    sampled=vertex[ref['source_rows']];rgb=np.column_stack([sampled[k] for k in ('red','green','blue')])
    assert np.array_equal(np.column_stack([sampled[k] for k in 'xyz']).astype(np.float32),mxyz)
    prior_samples=np.load(root/'initialization/sample_membership.npz')['sample_xyz'];pids=np.flatnonzero(region_mask(prior_samples,region,basis,zb));pxyz=prior_samples[pids]
    xyz=np.concatenate((mxyz,pxyz));nm=len(mxyz);np_=len(pxyz);n=len(xyz)
    mesh=np.load(root/'surface/mesh_arrays.npz');scene=o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(mesh['xyz'].astype(np.float32)),o3d.core.Tensor(mesh['faces'].astype(np.uint32)))
    archive=np.load(audit/'R1_point_support.npz');indices={str(name):i for i,name in enumerate(archive['names'])}
    selected=np.array([indices[v['name']] for v in views]);packed=archive['packed'][1,selected]
    supports=np.unpackbits(packed,axis=1)[:,:nm].astype(bool)
    gaps=np.full((588,nm),np.nan,np.float32);pvisible=np.zeros((588,np_),bool);pcurr=np.zeros((588,np_),np.uint8)
    # Current-surface relation: 0 unsupported,1 compatible,2 prior closer,3 prior farther,4 no hit,5 transition/mixed.
    rel=np.zeros((588,nm),np.uint8)
    camera_min=np.full((n,3),np.inf);camera_max=np.full((n,3),-np.inf)
    cell=cfg['xy_coverage_cell_m'];nu=int(round((region['u_m'][1]-region['u_m'][0])/cell));nv=int(round((region['v_m'][1]-region['v_m'][0])/cell));nc=nu*nv
    mcover=np.zeros((588,nc),bool);pcover=np.zeros_like(mcover);mcount=np.zeros(nc,np.uint64);pcount=np.zeros(nc,np.uint64)
    zmin=np.full(nc,np.inf,np.float32);zmax=np.full(nc,-np.inf,np.float32);cache={}
    def coverage(depth,K,R,t,half,coverage_row,total):
        key=(depth.shape,half,tuple(np.array(K).ravel()))
        if key not in cache:
            h,w=depth.shape;y,x=np.indices((h,w),dtype=np.float32)
            cache[key]=np.column_stack((x.ravel()+half,y.ravel()+half,np.ones(h*w)))@np.linalg.inv(K).T
        valid=np.isfinite(depth.ravel())&(depth.ravel()>0)
        points=(cache[key][valid]*depth.ravel()[valid,None]-t)@R
        points=points[region_mask(points,region,basis,zb)];uv=points[:,:2]@basis.T
        ij=np.floor((uv-np.array([region['u_m'][0],region['v_m'][0]]))/cell).astype(int)
        flat=ij[:,1]*nu+ij[:,0];coverage_row[np.unique(flat)]=True
        bins,counts=np.unique(flat,return_counts=True);total[bins]+=counts.astype(np.uint64)
        if half==0:np.minimum.at(zmin,flat,points[:,2]);np.maximum.at(zmax,flat,points[:,2])
    for i,v in enumerate(views):
        R=np.array(v['R']);t=np.array(v['t']);center=-R.T@t;K=np.array(v['maps']['depth']['K'])
        depth,meta=read_depth(root/'mvs'/v['local_depth']);assert meta['sha256']==v['maps']['depth']['sha256']
        z,uv,frame=project(xyz,v)
        # Exact source point ray, so prior and MVS hypotheses refer to the same ray.
        active=np.r_[supports[i],frame[nm:]];ids=np.flatnonzero(active)
        directions=(xyz[ids]-center)/z[ids,None];rays=np.column_stack((np.broadcast_to(center,directions.shape),directions)).astype(np.float32)
        hit=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy();hitfull=np.full(n,np.inf,np.float32);hitfull[ids]=hit
        mids=np.flatnonzero(supports[i]);delta=z[mids]-hitfull[mids];finite=np.isfinite(delta)
        gaps[i,mids]=np.where(finite,delta,np.nan)
        r=np.full(len(mids),5,np.uint8);r[~finite]=4;r[finite&(np.abs(delta)<=.5)]=1
        r[finite&(delta>cfg['large_disagreement_m'])]=2;r[finite&(delta<-cfg['large_disagreement_m'])]=3;rel[i,mids]=r
        pv=frame[nm:]&np.isfinite(hitfull[nm:])&(np.abs(hitfull[nm:]-z[nm:])<=cfg['minimum_prior_visibility_tolerance_m']);pvisible[i]=pv
        _,present,residual,agreement=query_points(pxyz,R,t,K,depth,[cfg['primary_depth_agreement_m']])
        pr=np.zeros(np_,np.uint8);pr[pv&~present]=4;pr[pv&present]=5;pr[pv&agreement[0]]=1
        pr[pv&present&(residual>cfg['large_disagreement_m'])]=2 # current behind this visible prior surface
        pr[pv&present&(residual<-cfg['large_disagreement_m'])]=3 # current in front; prior occluded, not disproved
        pcurr[i]=pr
        trusted=np.r_[supports[i],pv&agreement[0]]
        camera_min[trusted]=np.minimum(camera_min[trusted],center);camera_max[trusted]=np.maximum(camera_max[trusted],center)
        coverage(depth,K,R,t,0,mcover[i],mcount)
        priorpath=root/'prior/raw_depth'/(Path(v['name']).stem+'.npy');assert sha256(priorpath)==bound[str(priorpath.relative_to(root))]['sha256']
        pd=np.load(priorpath,allow_pickle=False);coverage(pd,np.array(v['K']),R,t,.5,pcover[i],pcount)
        if i%20==0:progress(out,'FULL_R1_SOURCE_RELATIONS_AND_COVERAGE',completed=i+1,total=588)
    span=np.where(np.isfinite(camera_min).all(1),np.max(camera_max-camera_min,axis=1),0)
    mns=supports.sum(0);mcounts=np.stack([(rel==k).sum(0) for k in range(6)],axis=1)
    dominant=np.argmax(mcounts[:,1:],axis=1)+1;purity=mcounts[np.arange(nm),dominant]/np.maximum(1,mns)
    sufficient=(mns>=cfg['minimum_support_views'])&(span[:nm]>=cfg['minimum_camera_span_m'])
    label=np.where(sufficient&(purity>=cfg['dominant_relation_fraction']),dominant,5).astype(np.uint8);label[mns==0]=0
    np.savez_compressed(out/'surface_evidence.npz',mvs_xyz=mxyz,mvs_rgb=rgb,mvs_source_rows=ref['source_rows'],mvs_view_count=mns,
        mvs_relation_counts=mcounts,mvs_relation=label,mvs_dominant_fraction=purity,mvs_camera_span_m=span[:nm],
        prior_xyz=pxyz,prior_sample_ids=pids,prior_visible_views=pvisible.sum(0),prior_relation_counts=np.stack([(pcurr==k).sum(0) for k in range(6)],axis=1),
        prior_mvs_camera_span_m=span[nm:],names=np.array([v['name'] for v in views]))
    np.savez_compressed(out/'per_view_relations.npz',mvs=rel,prior=pcurr,mvs_depth_gap=gaps,names=np.array([v['name'] for v in views]))
    coverage_state=(mcover.any(0).astype(np.uint8)+2*pcover.any(0).astype(np.uint8)).reshape(nv,nu)
    np.savez_compressed(out/'coverage_grid.npz',state=coverage_state,mvs_views=mcover.sum(0).reshape(nv,nu),prior_views=pcover.sum(0).reshape(nv,nu),
        mvs_pixel_observations=mcount.reshape(nv,nu),prior_pixel_observations=pcount.reshape(nv,nu),mvs_z_min=zmin.reshape(nv,nu),mvs_z_max=zmax.reshape(nv,nu),
        mvs_view_membership_packed=np.packbits(mcover,axis=0),prior_view_membership_packed=np.packbits(pcover,axis=0))
    # View set chosen for visibility coverage, before object judgments.
    uncovered=np.ones(nm,bool);chosen=[]
    for _ in range(cfg['inspection_view_count']):
        scores=(supports[:,uncovered]).sum(1).astype(float)
        if chosen:scores[chosen]=-1
        best=int(np.argmax(scores))
        if scores[best]<=0: # additional distinct useful views even after set coverage saturates
            scores=supports.sum(1).astype(float);scores[chosen]=-1;best=int(np.argmax(scores))
        chosen.append(best);uncovered[supports[best]]=False
    for name in ('DJI_20241217084553_0100_D.JPG','DJI_20241217103039_0045_D.JPG'):
        idx=next(i for i,v in enumerate(views) if v['name']==name)
        if idx not in chosen:chosen.append(idx)
    write(out/'inspection_views.json',[dict(index=i,name=views[i]['name'],supported_points=int(supports[i].sum())) for i in chosen])
    inspect=out/'views';inspect.mkdir()
    for i in chosen:
        name=views[i]['name'];img=Image.open(root/'scene/images'/name);img.save(inspect/(Path(name).stem+'.png'))
    font_manager.fontManager.addfont('/font.ttf');plt.rcParams['font.family']=font_manager.FontProperties(fname='/font.ttf').get_name()
    uv=mxyz[:,:2]@basis.T;puv=pxyz[:,:2]@basis.T
    limits=[region['u_m'][0],region['u_m'][1],region['v_m'][1],region['v_m'][0]]
    fig,axs=plt.subplots(2,2,figsize=(19,11))
    axs[0,0].scatter(uv[:,0],uv[:,1],s=2,c=rgb/255);axs[0,0].set_title('현재 MVS 전체 표본 RGB · 높이가 다른 표면은 겹쳐 보임')
    colors=['#777777','#267db3','#e69f00','#ab65cf','#d65b73','#b9a98b'];names=['현재 깊이 지지 없음','prior와 일치','prior가 더 앞','prior가 더 뒤','prior ray 결측','혼합·관측 약함']
    for k in range(6):
        m=label==k;axs[0,1].scatter(uv[m,0],uv[m,1],s=2,c=colors[k],label=names[k])
    axs[0,1].legend(loc='upper left',fontsize=8);axs[0,1].set_title('MVS 표면별 입력 관계 · 정확성/변화 판정 아님')
    im=axs[1,0].imshow(coverage_state,extent=limits,origin='upper',interpolation='nearest',cmap=matplotlib.colors.ListedColormap(['#272c32','#36a1d4','#c18352','#669b78']),vmin=-.5,vmax=3.5)
    cb=fig.colorbar(im,ax=axs[1,0],ticks=[0,1,2,3],fraction=.03);cb.ax.set_yticklabels(['양쪽 없음','MVS만','prior만','양쪽 존재']);axs[1,0].set_title('588장 depth의 R1 내부 0.5m XY 도착 셀 · 표면 높이 일치와 별개')
    im=axs[1,1].scatter(puv[:,0],puv[:,1],s=2,c=pvisible.sum(0),vmin=0,vmax=80,cmap='viridis');fig.colorbar(im,ax=axs[1,1],fraction=.03);axs[1,1].set_title('별도 ALS 표면 표본 · prior가 가리지 않는 train 시점 수')
    for ax in axs.ravel():
        ax.set_xlim(limits[:2]);ax.set_ylim(limits[2:]);ax.set_aspect('equal');ax.set_xlabel('객체축 u [m]');ax.set_ylabel('객체축 v [m]');ax.grid(alpha=.15)
    fig.suptitle('R1 전체 입력 감사 — 후속 구역 판단을 위한 관측 근거',fontsize=18);fig.tight_layout();fig.savefig(out/'R1_full_input_atlas.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(20,10));ax.scatter(uv[:,0],uv[:,1],s=5,c=rgb/255);ax.set_xlim(limits[:2]);ax.set_ylim(limits[2:]);ax.set_aspect('equal')
    ax.set_xticks(np.arange(-130,71,10));ax.set_yticks(np.arange(-60,36,10));ax.grid(alpha=.4);ax.set_title('R1 전체 현재 MVS RGB 표본 · 객체축 좌표');fig.tight_layout();fig.savefig(out/'R1_rgb_plan.png',dpi=150);plt.close(fig)
    for start in range(0,len(chosen),6):
        fig,axs=plt.subplots(2,3,figsize=(18,9))
        for ax,i in zip(axs.ravel(),chosen[start:start+6]):
            v=views[i];ax.imshow(Image.open(root/'scene/images'/v['name']));ax.set_title(v['name'],fontsize=9);ax.axis('off')
        for ax in axs.ravel()[len(chosen[start:start+6]):]:ax.axis('off')
        fig.tight_layout();fig.savefig(out/f'views_{start//6+1}.png',dpi=130);plt.close(fig)
    summary=dict(status='PASS_INPUT_EVIDENCE_NOT_SOURCE_TRUTH',scientific_verdict=None,mvs_samples=nm,prior_samples=np_,train_views=588,
        coverage_cell_m=cell,coverage_state_counts={str(k):int((coverage_state==k).sum()) for k in range(4)},
        coverage_state_labels={'0':'NO_DEPTH_ENDPOINT_IN_CELL','1':'MVS_ONLY','2':'PRIOR_ONLY','3':'BOTH_SOURCES_PRESENCE_NOT_SURFACE_AGREEMENT'},
        mvs_relation_counts={str(k):int((label==k).sum()) for k in range(6)},mvs_relation_labels=dict(enumerate(names)),
        config_sha256=sha256(args.config),input_manifest_sha256=cfg['input_manifest_sha256'],validated_inputs=validated,
        script_sha256=sha256(__file__),elapsed_seconds=time.time()-started,training_runs=0,manual_weights=None,
        files={p.name:sha256(p) for p in out.iterdir() if p.is_file() and p.name!='status.json'})
    write(out/'receipt.json',summary);progress(out,'COMPLETE',elapsed_seconds=time.time()-started)


if __name__=='__main__':main()
