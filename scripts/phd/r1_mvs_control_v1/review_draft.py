#!/usr/bin/env python3
"""CPU-only source observation draft. Never generates training weight arrays."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import open3d as o3d
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as Polygon
from matplotlib.patches import Polygon as Patch
from PIL import Image
sys.path.insert(0, '/repo')
from src.phd.region_view_support_v1 import sha256, object_basis, region_mask, ray_grid, read_depth, query_points


def write(path, value):
    with path.open('x') as f: json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def projected(points, view, native=True):
    K=np.array(view['maps']['depth']['K'] if native else view['K'])
    cam=points@np.array(view['R']).T+view['t']; q=cam@K.T
    return q[:,:2]/np.maximum(q[:,2:3],1e-9)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args()
    out=Path(args.output);out.mkdir(exist_ok=False)
    cfgpath=Path('/repo/configs/phd/r1_mvs_control_v1/observation_draft_v1.json')
    cfg=json.loads(cfgpath.read_text());write(out/'config.json',cfg)
    rc=json.loads(Path('/repo',cfg['region_config']).read_text());frame=rc['frame']
    region=next(r for r in rc['regions'] if r['id']=='R1');basis=object_basis(frame['u_axis_angle_degrees_ccw_from_easting'])
    root=Path('/input');split=json.loads((root/'scene/split_manifest.json').read_text());views={v['name']:v for v in split['train']}
    assert len(views)==588 and len(split['evaluation'])==84
    assert not set(views)&{v['name'] for v in split['evaluation']}
    assert all(a['name'] in views for a in cfg['areas'])
    assert sha256('/p1_source.npz')==cfg['source_point_sha256']
    old=np.load('/p1_source.npz');mesh=np.load(root/'surface/mesh_arrays.npz')
    scene=o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(mesh['xyz'].astype(np.float32)),o3d.core.Tensor(mesh['faces'].astype(np.uint32)))
    rows=[];sets={};panels={};colors={'C1':'#f6a623','S1':'#27b4dc','U1':'#ca6ee9'}
    for area in cfg['areas']:
        view=views[area['name']];depth,_=read_depth(root/'mvs'/view['local_depth'])
        h,w=depth.shape;K=np.array(view['maps']['depth']['K']);R=np.array(view['R']);t=np.array(view['t'])
        rays=ray_grid(K,w,h).astype(np.float64);rgb=(rays@np.array(view['K']).T)[:,:2]
        poly=Polygon(np.array(area['rgb_polygon']));inpoly=poly.contains_points(rgb).reshape(h,w)
        current=(rays*depth.reshape(-1,1)-t)@R
        valid=np.isfinite(depth)&(depth>0)
        inregion=region_mask(current,region,basis,frame['z_m']).reshape(h,w)
        if area['id']=='C1':
            mask=np.asarray(old['whole_r1'],bool)&region_mask(old['source_xyz'],region,basis,frame['z_m'])
            xyz=old['source_xyz'][mask];xy=old['source_native_xy'][mask]
            source_ids=np.flatnonzero(mask)
            selected=np.zeros((h,w),bool);selected[xy[:,1].astype(int),xy[:,0].astype(int)]=True
        else:
            selected=inpoly&valid&inregion;source_ids=np.flatnonzero(selected)
            xyz=current[source_ids];xy=np.column_stack(np.unravel_index(source_ids,(h,w)))[:,::-1]
        center=-R.T@t;directions=rays@R
        cast=np.column_stack((np.broadcast_to(center,directions.shape),directions)).astype(np.float32)
        prior=scene.cast_rays(o3d.core.Tensor(cast))['t_hit'].numpy().reshape(h,w)
        pv=np.isfinite(prior)&(prior>0);both=selected&pv&valid
        delta=depth[both]-prior[both];absolute=np.abs(delta)
        row=dict(id=area['id'],role=area['role'],source=area['name'],source_membership='train',source_points=len(xyz),
            polygon_pixels=int(inpoly.sum()),polygon_mvs_valid_pixels=int((inpoly&valid).sum()),
            selected_prior_valid=int(both.sum()),agreement_le_0_5m=float((absolute<=cfg['depth_agreement_m']).mean()) if len(delta) else None,
            signed_current_minus_prior_q10_q50_q90_m=np.quantile(delta,[.1,.5,.9]).tolist() if len(delta) else None,
            absolute_q50_q90_m=np.quantile(absolute,[.5,.9]).tolist() if len(delta) else None,
            local_xyz_bounds=[xyz.min(0).tolist(),xyz.max(0).tolist()],object_uv_bounds=[(xyz[:,:2]@basis.T).min(0).tolist(),(xyz[:,:2]@basis.T).max(0).tolist()])
        idx=np.unique(np.linspace(0,len(xyz)-1,min(cfg['audit_max_points_per_area'],len(xyz)),dtype=int))
        sets[area['id']]=dict(xyz=xyz,source_native_xy=xy,source_ids=source_ids,audit_ids=idx)
        row['audit_points']=len(idx);rows.append(row)
        panels[area['name']]=dict(view=view,depth=depth,prior=prior)
    # Same source-point IDs; source camera excluded; nearest native depth + round trip.
    for row in rows: row['other_view_histogram']=[]
    count={k:np.zeros(len(v['audit_ids']),np.uint16) for k,v in sets.items()}
    for i,view in enumerate(views.values()):
        depth,_=read_depth(root/'mvs'/view['local_depth'])
        K=np.array(view['maps']['depth']['K']);R=np.array(view['R']);t=np.array(view['t'])
        for row in rows:
            if view['name']==row['source']: continue
            item=sets[row['id']];xyz=item['xyz'][item['audit_ids']]
            _,_,_,support=query_points(xyz,R,t,K,depth,[cfg['depth_agreement_m']]);ok=support[0]
            ids=np.flatnonzero(ok)
            if len(ids):
                uv=np.floor(projected(xyz[ids],view)+.5).astype(int)
                z=depth[uv[:,1],uv[:,0]];r=np.column_stack((uv,np.ones(len(uv))))@np.linalg.inv(K).T
                recovered=(r*z[:,None]-t)@R
                back=projected(recovered,views[row['source']]);original=item['source_native_xy'][item['audit_ids'][ids]]
                ok[ids]&=np.linalg.norm(back-original,axis=1)<=cfg['roundtrip_native_px']
            count[row['id']]+=ok
        if i%100==0:print(json.dumps(dict(stage='DRAFT_SAME_POINT_SUPPORT',completed=i,total=len(views))),flush=True)
    for row in rows:
        n=count[row['id']];row.update(no_other_view_fraction=float((n==0).mean()),ge3_other_views_fraction=float((n>=3).mean()),
            other_view_q10_q50_q90=np.quantile(n,[.1,.5,.9]).tolist(),other_view_histogram=np.bincount(n).tolist())
        np.savez_compressed(out/(row['id']+'_source_points.npz'),**sets[row['id']],other_view_count=n)
    # Raw inputs and manually drawn source polygons; no output-derived selection.
    fig,axes=plt.subplots(1,2,figsize=(16,7))
    for ax,(name,panel) in zip(axes,panels.items()):
        ax.imshow(Image.open(root/'scene/images'/name));ax.axis('off');ax.set_title(name,fontsize=10)
        for area in cfg['areas']:
            if area['name']!=name:continue
            polygon=np.array(area['rgb_polygon']);color=colors[area['id']]
            ax.add_patch(Patch(polygon,closed=True,fill=True,facecolor=color,alpha=.15))
            ax.add_patch(Patch(polygon,closed=True,fill=False,edgecolor=color,linewidth=2))
            x,y=polygon.mean(0);ax.text(x,y,area['id'],color='white',fontsize=16,weight='bold',bbox=dict(facecolor=color,alpha=.9,edgecolor='none'))
    fig.suptitle('R1 input observation draft | C1 correction / S1 preservation / U1 unresolved\nCandidates only: not accuracy labels or training weights',fontsize=14)
    fig.tight_layout();fig.savefig(out/'R1_observation_draft.png',dpi=160);fig.savefig(out/'R1_observation_draft.pdf');plt.close(fig)
    fig,axes=plt.subplots(len(panels),3,figsize=(15,8),squeeze=False)
    for axs,(name,panel) in zip(axes,panels.items()):
        d=panel['depth'];p=panel['prior'];valid=np.isfinite(d)&(d>0);pv=np.isfinite(p)&(p>0)
        lo,hi=np.percentile(d[valid],[2,98])
        for ax,arr,title in zip(axs,[np.where(valid,d,np.nan),np.where(pv,p,np.nan),np.where(valid&pv,d-p,np.nan)],['MVS camera-Z','ALS camera-Z, same native rays','MVS minus ALS [m]']):
            diff='minus' in title;im=ax.imshow(arr,cmap='coolwarm' if diff else 'viridis',vmin=-3 if diff else lo,vmax=3 if diff else hi)
            for area in cfg['areas']:
                if area['name']==name:
                    poly=np.column_stack((area['rgb_polygon'],np.ones(len(area['rgb_polygon']))))@(np.array(panel['view']['maps']['depth']['K'])@np.linalg.inv(panel['view']['K'])).T
                    ax.add_patch(Patch(poly[:,:2]/poly[:,2:3],closed=True,fill=False,edgecolor=colors[area['id']],linewidth=1.5))
            ax.set_title(title+'\n'+name,fontsize=9);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.03)
    fig.tight_layout();fig.savefig(out/'R1_input_depth_diagnostic.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,7));xyz=mesh['xyz'][::8];uv=xyz[:,:2]@basis.T
    ax.scatter(uv[:,0],uv[:,1],s=.2,c='#969ca3',alpha=.5)
    u0,u1=region['u_m'];v0,v1=region['v_m'];ax.plot([u0,u1,u1,u0,u0],[v0,v0,v1,v1,v0],c='black',lw=2,label='R1 boundary')
    for area in cfg['areas']:
        xyz=sets[area['id']]['xyz'][::8];uv=xyz[:,:2]@basis.T
        ax.scatter(uv[:,0],uv[:,1],s=2,c=colors[area['id']],label=area['id']+' '+area['label'])
    ax.set_xlim(u0-27,u1+27);ax.set_ylim(v1+27,v0-27);ax.set_aspect('equal');ax.legend(loc='upper left',fontsize=8)
    ax.set_xlabel('Object u [m]');ax.set_ylabel('Object v [m]');ax.set_title('R1 object-aligned frame; gray: ALS input context; colored: source MVS points')
    fig.tight_layout();fig.savefig(out/'R1_plan_draft.png',dpi=170);plt.close(fig)
    write(out/'receipt.json',dict(status='PASS_INPUT_OBSERVATION_DRAFT',scientific_verdict=None,areas=rows,
        config_sha256=sha256(cfgpath),input_manifest_sha256=sha256(root/'input_manifest.json'),script_sha256=sha256(__file__),
        source_point_sha256=sha256('/p1_source.npz'),annotation_sources_train_only=True,
        evaluation_exposure=cfg['source_correction'],training_weights_created=False,reference_geometry_accessed=False,
        support_policy='At most 4096 evenly spaced fixed source IDs; other train view native depth <=0.5m and source roundtrip <=2px. No independent-view or correctness claim.',
        comparison_policy='Input disagreement at identical integer native rays; separate from original u+0.5 prior depth used in control.',
        files={p.name:sha256(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(status='COMPLETE',areas=[{k:v for k,v in r.items() if k!='other_view_histogram'} for r in rows])),flush=True)


if __name__=='__main__':main()
