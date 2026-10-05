"""Paired spatial diagnostic on preserved GeoGS surfaces; no training or correction."""
import csv, hashlib, json, platform, warnings
from pathlib import Path
import numpy as np
import open3d as o3d
from scipy.ndimage import minimum_filter, maximum_filter
from scipy.stats import spearmanr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

T=Path('/task'); O=Path('/out'); cfg=json.loads((O/'config.json').read_text())
sources={}; global_rows=[]; cohort_rows=[]; region_rows=[]; cells_rows=[]; view_rows=[]
def bind(p):
    p=Path(p)
    if str(p) not in sources:
        h=hashlib.sha256()
        with p.open('rb') as f:
            for x in iter(lambda:f.read(2**20),b''):h.update(x)
        sources[str(p)]={'sha256':h.hexdigest(),'bytes':p.stat().st_size}
    return sources[str(p)]['sha256']
def savecsv(name,rows):
    with (O/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for row in rows for k in row)));w.writeheader();w.writerows(rows)
def med(x):
    a=np.asarray(x);a=a[np.isfinite(a)];return float(np.median(a)) if len(a) else None
def load_candidate(rid,name):
    b=T/'evaluation/geometry'/rid/name/'sample0.1_reference0.1';jp=Path(str(b)+'.json');npz=Path(str(b)+'.npz');bind(jp);bind(npz)
    j=json.loads(jp.read_text());a=dict(np.load(npz))
    assert j['seed']==0 and j['surface_sample_spacing_m']==.1 and j['reference_voxel_size_m']==.1
    assert len(a['reference_points'])==len(a['reference_to_triangle_distance'])
    for row in j['thresholds']:
        th=row['threshold_m'];p=float(np.mean(a['prediction_to_reference_distance']<th));r=float(np.mean(a['reference_to_triangle_distance']<th));assert abs(p-row['precision'])<1e-10 and abs(r-row['recall'])<1e-10
    return j,a
def cameras(rid):
    root=T/'inputs'/rid/'scene/train_sparse_txt';intr={};out=[]
    for f in ['cameras.txt','images.txt']:bind(root/f)
    for line in (root/'cameras.txt').read_text().splitlines():
        t=line.split()
        if t and not t[0].startswith('#'):
            assert t[1]=='PINHOLE';intr[t[0]]=(int(t[2]),int(t[3]),np.array(list(map(float,t[4:8]))))
    for line in (root/'images.txt').read_text().splitlines():
        t=line.split()
        if len(t)>=10 and t[9].lower().endswith('.jpg'):
            w,x,y,z=map(float,t[1:5]);tr=np.array(list(map(float,t[5:8])));R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
            W,H,K=intr[t[8]];out.append(dict(name=t[9],R=R,t=tr,K=K,W=W,H=H))
    return out
def project(x,c):
    X=x@c['R'].T+c['t'];z=X[:,2];fx,fy,cx,cy=c['K'];den=np.where(z!=0,z,1)
    return fx*X[:,0]/den+cx,fy*X[:,1]/den+cy,z
def grid(xy,bounds,spacing):
    dims=np.ceil((bounds[:2,1]-bounds[:2,0])/spacing).astype(int)
    ix=np.floor((xy-bounds[:2,0])/spacing).astype(int);assert (ix>=0).all() and (ix<dims).all()
    return ix[:,1]*dims[0]+ix[:,0],int(dims[0]),int(dims[1])
def agg(values,indices,n,fn=np.median):
    out=np.full(n,np.nan);order=np.argsort(indices);idx=indices[order];v=np.asarray(values)[order];starts=np.r_[0,np.flatnonzero(np.diff(idx))+1];ends=np.r_[starts[1:],len(idx)]
    for a,b in zip(starts,ends):
        good=v[a:b][np.isfinite(v[a:b])]
        if len(good):out[idx[a]]=fn(good)
    return out
def top_height(a,xy,ceiling):
    scene=o3d.t.geometry.RaycastingScene();mesh=o3d.t.geometry.TriangleMesh(o3d.core.Tensor(a['clipped_vertices'].astype(np.float32)),o3d.core.Tensor(a['clipped_triangles'].astype(np.uint32)))
    scene.add_triangles(mesh);rays=np.c_[xy,np.full(len(xy),ceiling),np.zeros((len(xy),2)),np.full(len(xy),-1)].astype(np.float32)
    d=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy();return np.where(np.isfinite(d),ceiling-d,np.nan)
def pair_row(rid,condition,label,mask,d0,d1,initial='all'):
    m=mask.copy()
    if initial=='anchor_near':m&=d0<.5
    elif initial=='anchor_far':m&=d0>=.5
    a,b=d0[m],d1[m];row=dict(region=rid,condition=condition,cohort=label,initial=initial,reference_count=int(m.sum()),anchor_distance_median_m=med(a),final_distance_median_m=med(b),paired_distance_change_median_m=med(b-a),paired_distance_change_mean_m=float(np.mean(b-a)) if len(a) else None)
    for th in cfg['paired_distance_thresholds_m']:
        key=str(th);near0=a<th;near1=b<th;row.update({f'anchor_recall_{key}':float(near0.mean()) if len(a) else None,f'final_recall_{key}':float(near1.mean()) if len(a) else None,f'gained_{key}':int((~near0&near1).sum()),f'lost_{key}':int((near0&~near1).sum())})
    return row

plt.rcParams.update({'font.size':10,'axes.titlesize':11,'figure.facecolor':'white'})
for rid in cfg['regions']:
    aj,A=load_candidate(rid,'D005_Pnative.anchor_512.raw');R=A['reference_points'];ids=A['reference_original_indices'];d0=A['reference_to_triangle_distance'];bounds=np.array(aj['bounds_half_open']);N=len(R)
    flat,nx,ny=grid(R[:,:2],bounds,cfg['spatial_cell_m']);ncell=nx*ny;cellxy=np.c_[bounds[0,0]+(np.arange(ncell)%nx+.5)*cfg['spatial_cell_m'],bounds[1,0]+(np.arange(ncell)//nx+.5)*cfg['spatial_cell_m']]
    fine,fx,fy=grid(R[:,:2],bounds,cfg['top_envelope_xy_m']);ztop=np.full(fx*fy,-np.inf);np.maximum.at(ztop,fine,R[:,2]);top=R[:,2]>=ztop[fine]-cfg['top_envelope_tolerance_m']
    views=cameras(rid);selected=[c for c in views if c['R'][2,2]<=cfg['nadir_view_direction_z_max']];assert selected
    rawpath=Path('/references')/rid/'reference.npz';bind(rawpath);full=np.load(rawpath)['uas_xyz']
    recpath=T/'inputs'/rid/'da3/receipt.json';bind(recpath);receipt=json.loads(recpath.read_text());indexed={r['name']:r for r in receipt['images']}
    E=np.full((len(selected),N),np.nan,np.float32);L=E.copy();cameraE=E.copy()
    for vi,c in enumerate(selected):
        W,H=c['W'],c['H'];B=cfg['projection_block_px'];gx=(W+B-1)//B;gy=(H+B-1)//B;zbuf=np.full(gx*gy,np.inf)
        for start in range(0,len(full),250000):
            u,v,z=project(full[start:start+250000].astype(float),c);ok=(z>0)&(u>=0)&(u<W)&(v>=0)&(v<H);ii=(v[ok]//B).astype(int)*gx+(u[ok]//B).astype(int);np.minimum.at(zbuf,ii,z[ok])
        zb=zbuf.reshape(gy,gx);finite=np.isfinite(zb);size=cfg['image_neighborhood_px_blocks'];covered=minimum_filter(finite.astype(np.uint8),size=size,mode='constant',cval=0).astype(bool);low=minimum_filter(zb,size=size,mode='constant',cval=np.inf);high=maximum_filter(np.where(finite,zb,-np.inf),size=size,mode='constant',cval=-np.inf);stable=covered&((high-low)<=cfg['strict_depth_range_m'])
        u,v,z=project(R,c);ok=(z>0)&(u>=0)&(u<W)&(v>=0)&(v<H)&top;ii=np.flatnonzero(ok);bx=(u[ii]//B).astype(int);by=(v[ii]//B).astype(int);vis=z[ii]<=zb[by,bx]+cfg['visibility_depth_tolerance_m'];ii=ii[vis];bx=bx[vis];by=by[vis]
        name=Path(c['name']).stem;path=T/'inputs'/rid/'da3/raw_depth'/f'{name}.npy';assert bind(path)==indexed[c['name']]['files'][f'raw_depth/{name}.npy']['sha256'];D=np.load(path);assert D.shape==(H,W)
        uu=np.clip(np.rint(u[ii]).astype(int),0,W-1);vv=np.clip(np.rint(v[ii]).astype(int),0,H-1);da=D[vv,uu];valid=np.isfinite(da)&(da>0);ii,da,bx,by=ii[valid],da[valid],bx[valid],by[valid]
        C=-c['R'].T@c['t'];qz=(R[ii,2]-C[2])/z[ii];err=(da-z[ii])*qz;L[vi,ii]=err
        strict=stable[by,bx];si=ii[strict];E[vi,si]=err[strict];cameraE[vi,si]=da[strict]-z[si]
        # Exact ray algebra check independent of DA3 values.
        probe=R[ii[:100]];up,vp,zp=project(probe,c);fxp,fyp,cxp,cyp=c['K'];q=np.c_[(up-cxp)/fxp,(vp-cyp)/fyp,np.ones(len(probe))]@c['R'];assert np.allclose(C+q*zp[:,None],probe,atol=1e-8)
        view_rows.append(dict(region=rid,name=c['name'],batch=indexed[c['name']]['batch_id'],direction_z=float(c['R'][2,2]),relaxed_points=int(len(ii)),strict_points=int(len(si)),strict_target_z_error_median_m=med(err[strict]),strict_camera_z_error_median_m=med(da[strict]-z[si])))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning);e=np.nanmedian(E,axis=0);el=np.nanmedian(L,axis=0);n=np.isfinite(E).sum(axis=0);mad=np.nanmedian(np.abs(E-e),axis=0);viewrange=np.nanmax(E,axis=0)-np.nanmin(E,axis=0)
    mad[n<2]=np.nan;viewrange[n<2]=np.nan;strict=np.isfinite(e);relaxed=np.isfinite(el)
    ec=agg(e,flat,ncell);nc=agg(n.astype(float),flat,ncell);mcell=agg(mad,flat,ncell);refz=agg(R[:,2],flat,ncell,np.max);zmin=agg(R[:,2],flat,ncell,np.min);zspan=refz-zmin
    anchor_height=top_height(A,cellxy,float(bounds[2,1]+10));d0cell=agg(d0,flat,ncell);group=np.digitize(e,cfg['signed_target_height_bins_m'])-1;group[~strict]=-1
    classes={"ALL_REFERENCE":np.ones(N,bool),"STRICT_SUPPORT":strict,"RELAXED_SUPPORT":relaxed,"NO_STRICT_SUPPORT":~strict,"STRICT_MULTIVIEW_SPREAD_GT1":strict&(n>=3)&(viewrange>1)}
    edges=cfg['signed_target_height_bins_m']
    for k in range(len(edges)-1):classes[f'target_z_{edges[k]:g}_to_{edges[k+1]:g}m']=strict&(group==k)
    classes['STRICT_TARGET_ABOVE_1M']=strict&(e>1);classes['STRICT_TARGET_BELOW_MINUS1M']=strict&(e< -1);classes['STRICT_TARGET_WITHIN_0.5M']=strict&(np.abs(e)<=.5)
    payload={'reference_points':R,'reference_original_indices':ids,'reference_to_anchor_distance':d0,'top_envelope_mask':top,'strict_target_world_z_error_median':e,'relaxed_target_world_z_error_median':el,'strict_view_count':n,'strict_view_mad':mad,'strict_view_range':viewrange,'strict_per_view_target_world_z_error':E,'strict_per_view_camera_z_error':cameraE,'selected_view_names':np.array([c['name'] for c in selected]),'xy_cell_index':flat,'xy_cell_centres':cellxy,'reference_top_z_cell':refz,'reference_z_span_cell':zspan,'anchor_top_z_cell':anchor_height}
    outcome_maps={};height_maps={};dist_maps={}
    for condition in cfg['conditions']:
        j,a=load_candidate(rid,condition+'.mesh_512.raw');assert j['bounds_half_open']==aj['bounds_half_open'];assert np.array_equal(a['reference_original_indices'],ids) and np.array_equal(a['reference_points'],R)
        d1=a['reference_to_triangle_distance'];payload[condition+'_reference_distance']=d1;dz=d1-d0;dc=agg(dz,flat,ncell);outcome_maps[condition]=dc;dist_maps[condition]=agg(d1,flat,ncell);height=top_height(a,cellxy,float(bounds[2,1]+10));height_maps[condition]=height;payload[condition+'_top_z_cell']=height
        row=pair_row(rid,condition,'ALL_REFERENCE',np.ones(N,bool),d0,d1)
        for th in cfg['paired_distance_thresholds_m']:
            r0=next(x for x in aj['thresholds'] if x['threshold_m']==th);r1=next(x for x in j['thresholds'] if x['threshold_m']==th)
            for metric in ['precision','recall','f1']:row[f'anchor_{metric}_{th}']=r0[metric];row[f'final_{metric}_{th}']=r1[metric]
        global_rows.append(row)
        for label,mask in classes.items():
            for initial in ['all','anchor_near','anchor_far']:cohort_rows.append(pair_row(rid,condition,label,mask,d0,d1,initial))
        cs=np.isfinite(ec)&np.isfinite(dc);rho=spearmanr(ec[cs],dc[cs]).statistic if cs.sum()>3 else np.nan
        for ci in range(ncell):
            cells_rows.append(dict(region=rid,condition=condition,cell_id=ci,x=float(cellxy[ci,0]),y=float(cellxy[ci,1]),reference_top_z_m=float(refz[ci]),reference_z_span_m=float(zspan[ci]),da3_target_world_z_error_median_m=float(ec[ci]),median_strict_views=float(nc[ci]),da3_view_mad_m=float(mcell[ci]),anchor_distance_median_m=float(d0cell[ci]),final_distance_median_m=float(dist_maps[condition][ci]),paired_distance_change_median_m=float(dc[ci]),anchor_top_surface_z_m=float(anchor_height[ci]),final_top_surface_z_m=float(height[ci])))
        print(rid,condition,'strict=',int(strict.sum()),'DA3targetbias=',med(e),'pairedmedian=',med(dz[strict]),'cell_spearman=',rho,flush=True)
    region_rows.append(dict(region=rid,train_views=len(views),nadir_views=len(selected),reference_points=N,top_points=int(top.sum()),strict_points=int(strict.sum()),strict_fraction=float(strict.mean()),relaxed_points=int(relaxed.sum()),strict_target_z_median_m=med(e),relaxed_target_z_median_m=med(el),strict_multi3_points=int((n>=3).sum()),strict_multi3_range_gt1_points=int(((n>=3)&(viewrange>1)).sum())))
    np.savez_compressed(O/(rid+'.paired.npz'),**payload)
    extent=[bounds[0,0],bounds[0,1],bounds[1,0],bounds[1,1]]
    def show(ax,values,title,lim,cmap='RdBu_r'):
        cm=plt.get_cmap(cmap).copy();cm.set_bad('#e2e4e8');im=ax.imshow(values.reshape(ny,nx),origin='lower',extent=extent,cmap=cm,vmin=-lim if cmap=='RdBu_r' else 0,vmax=lim,interpolation='nearest');ax.set_title(title);ax.set_xlabel('Local X (m)');ax.set_ylabel('Local Y (m)');plt.colorbar(im,ax=ax,shrink=.8,label='m' if cmap=='RdBu_r' else 'views',extend='both')
    fig,ax=plt.subplots(2,3,figsize=(15,9),constrained_layout=True);fig.suptitle(f'{rid} | DA3 target error and paired refinement change\nMatched raw512 surfaces; spatial association, not DA3-only causation',fontsize=14)
    show(ax[0,0],ec,'DA3 target world-height error\nPositive = above observed reference',3)
    show(ax[0,1],nc,'Median qualifying near-nadir views\nGrey/no support is not a reconstruction failure',max(1,len(selected)),cmap='viridis')
    show(ax[0,2],outcome_maps['D005_Pnative'],'Anchor -> native: surface-distance change\nPositive = farther from reference',1)
    show(ax[1,0],outcome_maps['D0005_Pnative'],'Anchor -> 1/10 prior depth weight\nPositive = farther from reference',1)
    show(ax[1,1],dist_maps['D0005_Pnative']-dist_maps['D005_Pnative'],'1/10 weight minus native distance\nPositive = worse proximity',1)
    show(ax[1,2],height_maps['D005_Pnative']-anchor_height,'Native minus Anchor top-surface height\nFirst vertical hit; not point correspondence',3)
    fig.savefig(O/(rid+'.spatial_maps.png'),dpi=135);plt.close(fig)
    fig,ax=plt.subplots(2,3,figsize=(15,9),constrained_layout=True);fig.suptitle(rid+' | Each condition minus Anchor: paired distance change (m)\nSame reference, cells and colour scale; red farther / blue closer',fontsize=14)
    for a,condition in zip(ax.ravel(),cfg['conditions']):show(a,outcome_maps[condition],condition,1)
    fig.savefig(O/(rid+'.six_conditions.png'),dpi=135);plt.close(fig)
    # Fixed central sections inherited from the regional ROI; slab width0.5m.
    fig,axes=plt.subplots(2,1,figsize=(13,8),constrained_layout=True);fig.suptitle(rid+' | Fixed central sections, common raw512 surfaces\nDA3 target HEIGHT assigned to reference XY for diagnosis; not a reconstructed DA3 surface',fontsize=13)
    for axis,ax in enumerate(axes):
        centre=float(bounds[axis].mean());horizontal=1-axis;slab=np.abs(R[:,axis]-centre)<.25;ax.scatter(R[slab,horizontal],R[slab,2],s=1,c='black',label='UAS observed')
        for name,colour,label in [('D005_Pnative.anchor_512.raw','#8b7aa5','Anchor8k'),('D005_Pnative.mesh_512.raw','#2878b5','Native30k'),('D0005_Pnative.mesh_512.raw','#d97706','Prior depth1/10')]:
            _,a=load_candidate(rid,name);p=a['prediction_surface_samples'];m=np.abs(p[:,axis]-centre)<.25;ax.scatter(p[m,horizontal],p[m,2],s=.5,c=colour,alpha=.5,label=label)
        dm=slab&strict;ax.scatter(R[dm,horizontal],R[dm,2]+e[dm],s=2,c='#c32e5a',alpha=.5,label='DA3 target Z (strict support)')
        ax.set(xlabel='Local '+('Y' if horizontal==1 else 'X')+' (m)',ylabel='Local Z (m)',title=f'{"X" if axis==0 else "Y"}={centre:g}m, width0.5m',xlim=bounds[horizontal],ylim=bounds[2]);ax.legend(loc='upper right',fontsize=8,markerscale=3);ax.grid(alpha=.2)
    fig.savefig(O/(rid+'.fixed_sections.png'),dpi=150);plt.close(fig)

savecsv('global_stage_metrics.csv',global_rows);savecsv('error_cohort_transitions.csv',cohort_rows);savecsv('region_support.csv',region_rows);savecsv('per_view_support.csv',view_rows);savecsv('spatial_cells.csv',cells_rows)
receipt={'schema':'DA3_REFINEMENT_SPATIAL_DIAGNOSTIC_v1','status':'PASS_PAIRED_ASSOCIATION_ONLY','scientific_verdict':None,'config':cfg,'region_support':region_rows,'sources':sources,'versions':{'python':platform.python_version(),'numpy':np.__version__,'open3d':o3d.__version__,'matplotlib':matplotlib.__version__},'limitations':cfg['definitions'],'outputs':{p.name:{'sha256':bind(p),'bytes':p.stat().st_size} for p in O.iterdir() if p.suffix in ['.csv','.npz','.png']}}
(O/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(region_rows),flush=True)
