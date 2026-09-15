"""Stage 2: input-only MVS observation maps; no confidence fusion or training."""
import gc
import hashlib
import json
import sys
import time
import traceback
import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,'/repo')
from src.stage2.colmap_io import read_cameras_bin,read_images_bin
from src.phd.region_view_support_v1 import read_depth
from src.phd.mvs_evidence_v1 import project,visibility

P=Path('/payload');O=Path('/out');D=Path('/dense');bound={}
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def record(path,expected=None):
    path=Path(path);h=sha(path)
    if expected is not None: assert h==expected,str(path)
    bound[str(path)]=h;return path
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))
def stats(a):
    a=np.asarray(a);a=a[np.isfinite(a)]
    return dict(n=int(a.size),mean=float(a.mean()),median=float(np.median(a)),p90=float(np.quantile(a,.9))) if a.size else dict(n=0,mean=None,median=None,p90=None)
def median(a):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning);return np.nanmedian(a,axis=0)

def main():
    assert Path('/.dockerenv').exists();started=time.time()
    cfg=json.loads((O/'config.json').read_text());contract=json.loads(record(Path('/repo')/cfg['camera_contract']).read_text())
    cp=record(D/'sparse/cameras.bin',contract['inputs']['cameras_bin_sha256']);ip=record(D/'sparse/images.bin',contract['inputs']['images_bin_sha256'])
    members=json.loads(record(Path('/repo')/contract['inputs']['crosswalk_repo_relative'],contract['inputs']['crosswalk_sha256']).read_text())['rows']
    cams=read_cameras_bin(cp);ims=read_images_bin(ip);allviews=[]
    for member in sorted(members,key=lambda x:x['basename']):
        im=ims[member['colmap_image_id']];cam=cams[im.camera_id];assert im.name==member['basename'] and cam.model=='PINHOLE'
        allviews.append(dict(name=im.name,K=cam.K().tolist(),R=im.R().tolist(),t=im.tvec.tolist(),width=cam.width,height=cam.height))
    assert len(allviews)==937 and len({v['name'] for v in allviews})==937
    cache={};bindings={};masks={};cases=[]
    for region in ['P1','P2','P3']:
        bindings[region]=json.loads(record(P/cfg['global']/'inputs_v2'/region/'bindings.json').read_text())
        b=bindings[region];assert not set(b['evaluation_names'])&{v['name'] for v in b['train']}
        for v in b['train']:
            a=next(x for x in allviews if x['name']==v['name'])
            for k in ['K','R','t']:assert np.allclose(a[k],v[k],atol=1e-8,rtol=0),(v['name'],k)
        if region!='P1':masks[region]=json.loads(record(P/cfg['bundle']/region/'mask/manifest.json').read_text())
    def load(v):
        name=v['name'];path=D/'stereo/depth_maps'/(name+'.geometric.bin')
        if name in cache:return cache[name]
        depth,meta=read_depth(path)
        if str(path) in bound:assert bound[str(path)]==meta['sha256']
        bound[str(path)]=meta['sha256']
        K=np.array(v['K']);Kn=K.copy();Kn[0]*=meta['width']/v['width'];Kn[1]*=meta['height']/v['height']
        enriched={**v,'maps':{'depth':{**meta,'K':Kn.tolist()}}}
        if len(cache)>=32:cache.pop(next(iter(cache)))
        cache[name]=(depth,enriched);return depth,enriched
    display=json.loads(record(P/cfg['global']/'viewer_rgb_v1/prior_weights_v1/manifest.json').read_text())
    for case in cfg['cases']:
        tick=time.time();region=case['region'];b=bindings[region]
        representative=next(x for x in display['regions'] if x['id']==region)
        selected=[x['image_name'] for x in representative['views'] if x['split']=='train' and x['image_name'].endswith(case['suffix'])]
        assert len(set(selected))==1,(case,selected)
        name=selected[0];ref=next(v for v in b['train'] if v['name']==name);raw,full=load(next(v for v in allviews if v['name']==name))
        assert full['maps']['depth']['sha256']==ref['maps']['depth']['sha256']
        stride=cfg['native_pixel_stride'];yy,xx=np.mgrid[0:raw.shape[0]:stride,0:raw.shape[1]:stride];shape=xx.shape
        native_uv=np.stack([xx.ravel(),yy.ravel(),np.ones(xx.size)],1)
        mapped=native_uv@(np.asarray(ref['K'])@np.linalg.inv(np.asarray(ref['maps']['depth']['K']))).T
        uv=mapped[:,:2]/mapped[:,2:];depth=raw[yy,xx].ravel().astype(float);valid=np.isfinite(depth)&(depth>0);depth[~valid]=np.nan
        rgb_uv=np.floor(uv+.5).astype(int);rx=np.clip(rgb_uv[:,0],0,ref['width']-1);ry=np.clip(rgb_uv[:,1],0,ref['height']-1)
        maskpath=P/cfg['bundle']/region/'mask'
        maskpath=maskpath/'r1_mask.npz' if region=='P1' else maskpath/next(x['path'] for x in masks[region]['views'] if x['camera']==Path(name).stem)
        labels=np.load(record(maskpath))['region_id'][ry,rx]
        prior_path=P/cfg['base']/('inputs/'+region+'/prior/raw_depth/'+Path(name).stem+'.npy')
        prior=cv2.resize(np.load(record(prior_path)),(ref['width'],ref['height']),interpolation=cv2.INTER_LINEAR)[ry,rx]
        photo_path=record(P/cfg['base']/('inputs/'+region+'/scene/images/'+name),ref['sha256'])
        photo=np.asarray(Image.open(photo_path).convert('RGB'))[ry,rx].reshape(*shape,3)
        # A 4-neighbor native-depth jump is descriptive; real roof boundaries can have large jumps.
        jump=np.zeros_like(raw);invalid=~np.isfinite(raw)|(raw<=0)
        for axis in [0,1]:
            a=np.diff(raw,axis=axis);bad=np.diff(invalid.astype(int),axis=axis)!=0
            a=np.where(bad,np.nan,np.abs(a))
            if axis==0:jump[:-1]=np.fmax(jump[:-1],a);jump[1:]=np.fmax(jump[1:],a)
            else:jump[:,:-1]=np.fmax(jump[:,:-1],a);jump[:,1:]=np.fmax(jump[:,1:],a)
        jump[invalid]=np.nan
        train_names={v['name'] for v in b['train']};pair_names=[];zs=[];roundtrips=[];angles=[];inside_rows=[];pair_records=[]
        for nb0 in allviews:
            if nb0['name']==name:continue
            q,z,_=project(uv,depth,ref,nb0)
            inside=valid&(z>0)&(q[:,0]>=0)&(q[:,0]<=nb0['width']-1)&(q[:,1]>=0)&(q[:,1]<=nb0['height']-1)
            if not inside.any():continue
            nd,nb=load(nb0);e=visibility(uv,depth,ref,nb,nd,cfg['primary_depth_tolerance_m'])
            known=np.isfinite(e['z_residual']);good=known&(np.abs(e['z_residual'])<=cfg['primary_depth_tolerance_m'])&(e['roundtrip_px']<=cfg['roundtrip_tolerance_rgb_px'])
            pair_names.append(nb['name']);zs.append(e['z_residual'].astype('float32'));roundtrips.append(e['roundtrip_px'].astype('float32'));angles.append(e['parallax_deg'].astype('float32'));inside_rows.append(inside)
            target=(labels==1)&valid
            pair_records.append(dict(name=nb['name'],regional_role='train' if nb['name'] in train_names else ('evaluation' if nb['name'] in b['evaluation_names'] else 'outside_regional_GS'),r1_available=int((known&target).sum()),r1_support=int((good&target).sum()),r1_support_fraction=float((good&target).sum()/max(1,target.sum()))))
        zs=np.asarray(zs);roundtrips=np.asarray(roundtrips);angles=np.asarray(angles);inside_rows=np.asarray(inside_rows)
        assert len(pair_names)==len(set(pair_names)) and name not in pair_names
        pools={};saved={};folder=O/case['id'];folder.mkdir()
        common=dict(native_xy=native_uv[:,:2].astype('int16'),rgb_uv=uv.astype('float32'),shape=np.array(shape),labels=labels,valid=valid,depth=depth.astype('float32'),prior=prior.astype('float32'),boundary_jump=jump[yy,xx].ravel())
        for pool in cfg['source_pools']:
            chosen=np.array([n in train_names for n in pair_names]) if pool=='regional_train' else np.ones(len(pair_names),bool)
            zz=zs[chosen];rt=roundtrips[chosen];aa=angles[chosen];known=np.isfinite(zz);available=known.sum(0)
            maps=dict(available=available,in_frame=inside_rows[chosen].sum(0),median_abs_z=median(np.abs(zz)),median_roundtrip=median(rt))
            for tol in cfg['depth_tolerances_m']:maps['support_'+str(tol)]=(known&(np.abs(zz)<=tol)&(rt<=cfg['roundtrip_tolerance_rgb_px'])).sum(0)
            support=known&(np.abs(zz)<=cfg['primary_depth_tolerance_m'])&(rt<=cfg['roundtrip_tolerance_rgb_px'])
            maps['support']=support.sum(0);maps['occlusion_candidates']=(known&(zz>cfg['primary_depth_tolerance_m'])).sum(0);maps['front_conflicts']=(known&(zz < -cfg['primary_depth_tolerance_m'])).sum(0)
            maps['support_fraction']=np.divide(maps['support'],available,out=np.full(depth.shape,np.nan),where=available>0)
            maps['max_supported_angle']=np.max(np.where(support,aa,-np.inf),axis=0);maps['max_supported_angle'][maps['support']==0]=np.nan
            assert (maps['support_0.1']<=maps['support_0.25']).all() and (maps['support_0.25']<=maps['support_0.5']).all()
            assert (maps['support']<=available).all() and not maps['support'][~valid].any()
            for key,val in maps.items():saved[pool+'__'+key]=val
            subsets={}
            for subset,sel in [('all_valid',valid),('R1',valid&(labels==1)),('R2',valid&(labels==2)),('R3',valid&(labels==3))]:
                subsets[subset]=dict(samples=int(sel.sum()),zero_available_fraction=float((available[sel]==0).mean()) if sel.any() else None,zero_support_fraction=float((maps['support'][sel]==0).mean()) if sel.any() else None,metrics={k:stats(a[sel]) for k,a in maps.items()})
            pools[pool]=dict(source_pool_size=(len(train_names)-1 if pool=='regional_train' else 936),projecting_source_count=int(chosen.sum()),subsets=subsets)
            # Same scales for all cases and both pools; gray is missing and zero counts remain numeric zero.
            panels=[('Current image / R1 cyan, R2 green',photo,None,None,None),('MVS camera-Z (m)',depth,'viridis',None,None),('Available other-view depth count',available,'viridis',0,30),('Consistent other-view count',maps['support'],'viridis',0,20),('Median |depth residual| (m)\nincludes occlusion candidates',maps['median_abs_z'],'magma',0,2),('Max consistent ray angle (degrees)',maps['max_supported_angle'],'viridis',0,60),('Possible occluder count\nother depth is in front',maps['occlusion_candidates'],'magma',0,20),('Native 4-neighbor depth jump (m)',common['boundary_jump'],'magma',0,1),('MVS - prior camera-Z (m)\nnot source authority',np.where(valid&(prior>0),depth-prior,np.nan),'coolwarm',-5,5)]
            fig,axes=plt.subplots(3,3,figsize=(16,13),constrained_layout=True)
            for ax,(title,a,cmap,vmin,vmax) in zip(axes.flat,panels):
                if cmap is None:ax.imshow(a)
                else:
                    col=plt.get_cmap(cmap).copy();col.set_bad('#c6cbd2');mat=np.where(valid,a,np.nan).reshape(shape);im=ax.imshow(mat,cmap=col,vmin=vmin,vmax=vmax);fig.colorbar(im,ax=ax,shrink=.7)
                for label,color in [(1,'cyan'),(2,'lime')]:
                    contour=(labels==label).reshape(shape)
                    if contour.any() and not contour.all():ax.contour(contour,levels=[.5],colors=[color],linewidths=.45)
                ax.set_title(title,fontsize=10);ax.axis('off')
            fig.suptitle(case['id']+' / '+pool+' / native stride '+str(stride)+' / input evidence only',fontsize=14)
            fig.savefig(folder/(pool+'.png'),dpi=125);plt.close(fig)
        assert (saved['regional_train__support']<=saved['all937_context__support']).all()
        np.savez_compressed(folder/'maps.npz',**common,**saved)
        np.savez_compressed(folder/'pairs.npz',source_names=np.array(pair_names),z_residual=zs,roundtrip_rgb_px=roundtrips,ray_angle_deg=angles)
        row={**case,'camera':name,'shape':list(shape),'pools':pools,'top_R1_sources':sorted(pair_records,key=lambda a:(-a['r1_support'],a['name']))[:15],'native_stride':stride,'maps_sha256':sha(folder/'maps.npz'),'wall_seconds':time.time()-tick}
        write(folder/'summary.json',row);cases.append(row)
        print(json.dumps({'case':case['id'],'seconds':row['wall_seconds'],'R1_train':pools['regional_train']['subsets']['R1'],'R1_all':pools['all937_context']['subsets']['R1']},ensure_ascii=False),flush=True)
        del zs,roundtrips,angles,inside_rows,saved;gc.collect()
    write(O/'manifest.json',dict(status='PASS_STAGE2_EVIDENCE_MAPS',scientific_verdict=None,training_runs=0,gt_accessed=False,automatic_weights_generated=False,scope=cfg['scope'],config_sha256=sha(O/'config.json'),script_sha256=sha(__file__),core_sha256=sha('/repo/src/phd/mvs_evidence_v1.py'),runtime=cfg['runtime'],python=sys.version,numpy=np.__version__,inputs=bound,cases=cases,wall_seconds=time.time()-started))

if __name__=='__main__':
    try:main()
    except Exception:
        (O/'failure.txt').write_text(traceback.format_exc());raise
