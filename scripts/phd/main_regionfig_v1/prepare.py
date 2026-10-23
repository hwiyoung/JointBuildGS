"""Compute frozen cross sections and select native training-source photographs, CPU only."""
import io
import re
import resource
import time
from PIL import Image
from scipy.ndimage import minimum_filter
from common import *

def section(ex,c):
    z,path=pv(ex); p=z['centre']; n=z['normal']; a=np.array(ex['start_xy']);b=np.array(ex['end_xy'])
    length=np.linalg.norm(b-a);direction=(b-a)/length;side=np.array([-direction[1],direction[0]])
    s=(p[:,:2]-a)@direction; d=(p[:,:2]-a)@side
    band=z['in_eval']&z['roof_like']&(s>=0)&(s<=length)&(np.abs(d)<=ex['half_width_m'])
    corr=np.isin(z['cell'],[c['cell_order'].index(k) for k in ex['highlight_cells']])
    zg=p[:,2]+z['gt_p']*n[:,2];zm=p[:,2]+z['mvs_a_p']*n[:,2]
    zm[z['mvs_a_status']!=0]=np.nan
    w=c['section']['bin_m']; nb=int(np.ceil(length/w));bi=np.floor(s/w).astype(int)
    heights=[];counts=[];correction=[]
    for i in range(nb):
        m=band&(bi==i);counts.append(int(m.sum()));correction.append(bool(np.any(m&corr)))
        heights.append([float(np.median(q[m&np.isfinite(q)])) if np.any(m&np.isfinite(q)) else np.nan for q in [p[:,2],zm,zg]])
    heights=np.array(heights);edges=np.minimum(np.arange(nb+1)*w,length);centres=(edges[1:]+edges[:-1])/2
    refzero=np.nanmin(heights[:,2]);mc=band&corr
    values=dict(roof_patches=int(band.sum()),correction_patches=int(mc.sum()),
                prior_minus_gt_cm=float(np.nanmedian((p[:,2]-zg)[mc])*100),
                mvs_minus_gt_cm=float(np.nanmedian((zm-zg)[mc])*100))
    comparisons={k:dict(expected=v,actual=values[k],delta=values[k]-v,
                       pass_check=(values[k]==v if 'patches' in k else abs(values[k]-v)<=.5)) for k,v in ex.get('expected',{}).items()}
    rec=dict(id=ex['id'],region=ex['region'],title=ex['title'],prior_label=ex['prior_label'],site=ex['site'],prior=ex['prior'],
             start_xy=a,end_xy=b,length_m=length,half_width_m=ex['half_width_m'],values=values,comparison=comparisons,
             source=dict(path=str(path),sha256=sha(path),fields=['centre','normal','in_eval','roof_like','cell','gt_p','mvs_a_p','mvs_a_status'],ring_m=1.5),
             bin_edges_m=edges,bin_centres_m=centres,heights_model_m=heights,heights_relative_m=heights-refzero,
             reference_zero_model_m=refzero,bin_patch_counts=counts,correction_bins=correction,
             band_patch_indices=np.flatnonzero(band),correction_patch_indices=np.flatnonzero(mc),
             summary_finite_prior_n=int(np.isfinite((p[:,2]-zg)[mc]).sum()),summary_finite_mvs_n=int(np.isfinite((zm-zg)[mc]).sum()))
    print(ex['id'],'section',values,'checks',all(x['pass_check'] for x in comparisons.values()),flush=True)
    return rec,z

def line_points(rec,c):
    length=rec['length_m'];s=np.linspace(0,length,int(np.ceil(length/c['photo']['visibility_sample_step_m']))+1)
    h=np.array(rec['heights_model_m']);bc=np.array(rec['bin_centres_m']);good=np.isfinite(h[:,2])
    g=np.interp(s,bc[good],h[good,2]);a=np.array(rec['start_xy']);b=np.array(rec['end_xy'])
    X=np.column_stack([a+(b-a)*s[:,None]/length,g])
    return X,s

def visibility(gt,X,pose,cam,c):
    uv,z=project(gt,pose,cam);cell=c['photo']['zbuffer_cell_px']
    w=int(np.ceil(cam['w']/cell));h=int(np.ceil(cam['h']/cell))
    keep=(z>0)&(uv[:,0]>=0)&(uv[:,0]<cam['w'])&(uv[:,1]>=0)&(uv[:,1]<cam['h'])
    ij=np.floor(uv[keep]/cell).astype(int);buf=np.full((h,w),np.inf,np.float32)
    np.minimum.at(buf,(ij[:,1],ij[:,0]),z[keep])
    buf=minimum_filter(buf,size=c['photo']['zbuffer_min_filter_cells'],mode='constant',cval=np.inf)
    q,zq=project(X,pose,cam);ix=np.floor(q/cell).astype(int)
    nearest=buf[np.clip(ix[:,1],0,h-1),np.clip(ix[:,0],0,w-1)]
    known=np.isfinite(nearest);hidden=known&(zq>nearest+c['photo']['depth_tolerance_m'])
    # Each interval uses its midpoint classification, then weighted by horizontal metres.
    return hidden,known,nearest,q,zq

def native_crop_box(X,pose,cam,c):
    pad=c['photo']['crop_margin_m'];lo=X[:,:2].min(0)-pad;hi=X[:,:2].max(0)+pad
    corners=np.array([[x,y,z] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [X[:,2].min(),X[:,2].max()]])
    uv,_=project(corners,pose,cam)
    p=np.floor(uv.min(0)).astype(int);q=np.ceil(uv.max(0)).astype(int)
    unclipped=[int(p[0]),int(p[1]),int(q[0]),int(q[1])]
    margin_inside=bool(np.all(p>=0) and q[0]<=cam['w'] and q[1]<=cam['h'])
    for j,limit in enumerate([cam['w'],cam['h']]):
        size=max(q[j]-p[j],c['photo']['minimum_crop_side_px']);mid=(p[j]+q[j])/2
        p[j]=max(0,min(int(np.floor(mid-size/2)),limit-size));q[j]=min(limit,p[j]+size)
    return [int(p[0]),int(p[1]),int(q[0]),int(q[1])],dict(xy_min=lo,xy_max=hi,z_min=float(X[:,2].min()),z_max=float(X[:,2].max()),unclipped_box_px=unclipped,full_4m_margin_inside=margin_inside)

def pixel_to_plane(uv,zheight,pose,cam):
    p=cam['p'];xd=(uv[:,0]-p[2])/p[0];yd=(uv[:,1]-p[3])/p[1];x=xd.copy();y=yd.copy()
    k1,k2,p1,p2,k3,k4,k5,k6=p[4:]
    for _ in range(30):
        r=x*x+y*y;rad=(1+k1*r+k2*r*r+k3*r*r*r)/(1+k4*r+k5*r*r+k6*r*r*r)
        dx=2*p1*x*y+p2*(r+2*x*x);dy=p1*(r+2*y*y)+2*p2*x*y
        x,y=(xd-dx)/rad,(yd-dy)/rad
    ray=np.column_stack([x,y,np.ones(len(x))])@pose['R'];C=-pose['R'].T@pose['t']
    return C+ray*((zheight-C[2])/ray[:,2])[:,None]

def choose_photo(ex,rec,c,rawposes,rawcams,zfile,members):
    scene=S0/'fork_inputs/s61'/ex['site']/f"scene_{ex['prior']}"
    model=scene/'sparse/0';sp=load(scene.parent/'split.json');train=sp['train']
    trainposes=poses(model/'images.bin');traincams=cameras(model/'cameras.bin')
    X,s=line_points(rec,c);mid=(X[1:]+X[:-1])/2;ds=np.diff(s)
    gtpath=S1/'v3/box_gt'/ex['site']/'gt_points.npz'
    gt,gtinfo=gt_crop(gtpath,np.array(ex['start_xy']),np.array(ex['end_xy']),c['photo']['gt_crop_margin_m'])
    print(ex['id'],'local GT',gtinfo['kept'],'of',gtinfo['total'],flush=True)
    candidates=[];pose_error=0.;camchecks=[]
    for stem in train:
        stem=Path(stem).stem;tp=trainposes[stem];rp=rawposes[stem]
        delta=max(np.max(np.abs(tp['R']-rp['R'])),np.max(np.abs(tp['t']-rp['t'])))
        pose_error=max(pose_error,float(delta));assert delta<1e-8,(stem,delta)
        cam=rawcams[rp['cam']];q,zq=project(X,tp,cam)
        # FULL_OPENCV's radial polynomial folds outside the calibrated field.
        # Require the line in the real PINHOLE training image first, preventing
        # out-of-field points that the polynomial maps spuriously inside the raw image.
        tc=traincams[tp['cam']];tq,tz=project(X,tp,tc)
        training_inside=np.all((tz>0)&(tq[:,0]>=0)&(tq[:,0]<tc['w'])&(tq[:,1]>=0)&(tq[:,1]<tc['h']))
        inside=training_inside and np.all((zq>0)&(q[:,0]>=0)&(q[:,0]<cam['w'])&(q[:,1]>=0)&(q[:,1]<cam['h']))
        if inside:
            _,crop_check=native_crop_box(X,tp,cam,c)
            if not crop_check['full_4m_margin_inside']:
                continue
            candidates.append(dict(stem=stem,tilt_deg=tilt(tp),projected_line_length_px=float(np.linalg.norm(np.diff(q,axis=0),axis=1).sum())))
    def evaluate(cs):
        for item in cs:
            tp=trainposes[item['stem']];cam=rawcams[rawposes[item['stem']]['cam']]
            hidden,known,_,_,_=visibility(gt,mid,tp,cam,c)
            item.update(occluded_fraction=float(ds[hidden].sum()/s[-1]),unknown_fraction=float(ds[~known].sum()/s[-1]))
        return sorted(cs,key=lambda r:(r['occluded_fraction'],-r['projected_line_length_px'],r['stem']))
    nadir=evaluate([r for r in candidates if r['tilt_deg']<=c['photo']['nadir_max_deg']])
    fallback=not nadir or nadir[0]['occluded_fraction']>c['photo']['max_nadir_occluded_fraction']
    if fallback:
        oblique=evaluate([r for r in candidates if r['tilt_deg']>c['photo']['nadir_max_deg']])
        ordered=sorted(nadir+oblique,key=lambda r:(r['occluded_fraction'],-r['projected_line_length_px'],r['stem']))
    else: ordered=nadir
    assert ordered,'No complete training view'
    best=ordered[0];stem=best['stem'];pose=trainposes[stem];cam=rawcams[rawposes[stem]['cam']]
    hidden,known,depth,qmid,zq=visibility(gt,mid,pose,cam,c);q,_=project(X,pose,cam)
    crop,box=native_crop_box(X,pose,cam,c)
    raw=zfile.read(members[stem]);im=Image.open(io.BytesIO(raw));assert im.size==(cam['w'],cam['h'])
    utc=re.search(rb'drone-dji:UTCAtExposure="([^"]*)"',raw[:250000])
    pitch=re.search(rb'drone-dji:GimbalPitchDegree="([^"]*)"',raw[:250000])
    assert utc,'UTCAtExposure absent'
    image_crop=im.crop(crop).convert('RGB')
    assert min(image_crop.size)>=600
    image_crop.save(DOC/f"figures/crops/{ex['id']}_원본.png")
    # Export a source training-resolution crop too; native original is the plotted source.
    training_path=scene/'images'/f'{stem}.jpg';assert training_path.exists()
    qt,_=project(X,pose,traincams[pose['cam']])
    trainim=Image.open(training_path)
    # Camera headers may retain original native dimensions; check calibration file explicitly.
    calibration=load(scene/'jbgs_calibration.json')
    x0,y0,x1,y1=crop
    uv=np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]],float)
    foot=pixel_to_plane(uv,float(np.median(X[:,2])),pose,cam)
    rec['photo']=dict(best,original_member=members[stem],original_archive=str(RAW),original_sha256=hashlib.sha256(raw).hexdigest(),
                     utc_at_exposure=utc.group(1).decode(),xmp_gimbal_pitch_deg=float(pitch.group(1)) if pitch else None,
                     native_size_px=list(im.size),training_size_px=list(trainim.size),crop_box_px=crop,crop_size_px=list(image_crop.size),
                     native_source_of_training_image=True,training_image=str(training_path),training_image_sha256=sha(training_path),
                     scene=str(scene),scene_calibration=calibration,pose_max_absolute_difference=pose_error,
                     camera=cam,pose=pose,candidate_count_full_line=len(candidates),nadir_candidate_count=len(nadir),expanded_to_oblique=fallback,
                     gt_crop=dict(gtinfo,path=str(gtpath),sha256=sha(gtpath)),crop_world_box=box,
                     crop_footprint_xyz=foot,crop_footprint_plane_z_m=float(np.median(X[:,2])),
                     line_s_m=s,line_xyz=X,line_pixels=q,line_midpoint_occluded=hidden,line_midpoint_known=known,
                     nearest_gt_camera_z=depth,line_midpoint_camera_z=zq,unknown_length_m=float(ds[~known].sum()),
                     occluded_length_m=float(ds[hidden].sum()),line_missing_gt_bins=int(np.isnan(np.array(rec['heights_model_m'])[:,2]).sum()))
    dump(PAY/f"candidates_{ex['id']}.json",dict(candidates=candidates,ranked_evaluated=ordered,chosen=best,rule=c['photo']))
    print(ex['id'],'selected',best,'crop',crop,flush=True)
    return rec

def main():
    start=time.time();c=load(CFG/'regionfig_v1.json');lock=load(CFG/'regionfig_v1.lock.json')
    assert sha(CFG/'regionfig_v1.json')==lock['config_sha256']
    rawposes=poses(DENSE/'triangulated/images.bin');rawcams=cameras(DENSE/'triangulated/cameras.bin')
    records=[]
    with zipfile.ZipFile(RAW) as zfile:
        members={Path(n).stem:n for n in zfile.namelist() if n.upper().endswith('.JPG')}
        for ex in c['examples']:
            rec,_=section(ex,c)
            records.append(choose_photo(ex,rec,c,rawposes,rawcams,zfile,members))
    result=dict(task_id=c['task_id'],prepared_at=now(),config_sha256=lock['config_sha256'],amendments=[load(p) for p in sorted(CFG.glob('amendment*.json'))],scientific_verdict=None,examples=records,
                resource=dict(seconds=time.time()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
    dump(PAY/'prepared.json',result);dump(DOC/'tables/영역예시_보정_숫자.json',result)
    print('DONE',result['resource'])

if __name__=='__main__':main()
