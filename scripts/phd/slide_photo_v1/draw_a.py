"""Native photos, exact depth-grid masks, and unfilled GT z buffers."""
from common import *
from photos import *
from task0_scan import cameras_depth,points
import cv2
from PIL import ImageOps
def zbuffer(X,pose,cam):
    uv,z=G.project(X,pose,cam);ij=np.floor(np.nan_to_num(uv,nan=-1,posinf=-1,neginf=-1)).astype(np.int64)
    ok=(z>0)&(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741);buf=np.full(741*1024,np.inf)
    np.minimum.at(buf,ij[ok,1]*1024+ij[ok,0],z[ok]);return buf.reshape(741,1024)
def native_mask(im,photo,labels,gridcam):
    """Invert the original FULL_OPENCV lens model; classify, never fill GT."""
    cam=photo['camera'];p=np.array(cam['p']);K=np.array([[p[0],0,p[2]],[0,p[1],p[3]],[0,0,1.]])
    xx,yy=np.meshgrid(np.arange(im.width)+photo['crop_box_px'][0]+.5,np.arange(im.height)+photo['crop_box_px'][1]+.5)
    q=cv2.undistortPoints(np.c_[xx.ravel(),yy.ravel()].astype(np.float64).reshape(-1,1,2),K,p[4:]).reshape(-1,2);fp=gridcam['p'];ij=np.floor(q*fp[:2]+fp[2:]).astype(int)
    ok=(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741);v=np.zeros(len(ij),np.uint8);v[ok]=labels[ij[ok,1],ij[ok,0]];v=v.reshape(im.height,im.width)
    a=np.array(im,dtype=float)
    for k,col in [(1,[211,42,168]),(2,[217,54,54])]:a[v==k]=.48*a[v==k]+.52*np.array(col)
    return Image.fromarray(np.uint8(a))
def legacy_panel(site,face,view,patches=None):
    ex=S0/'s61/export'/site/'LoD2';lm=np.load(ex/'locmap'/f'{view}.npy');unit=np.load(S0/'s61/box'/site/'LoD2/units.npz')
    surf=unit['surf_ext'][unit['loc_surface']]
    if patches is None:
        with np.load(U/'patch_values'/f'{site}__LoD2__R1.5.npz') as z:idx=np.flatnonzero((surf==face)&z['in_eval'])
    else:idx=np.asarray(patches)
    X=unit['loc_center'][idx];im,photo=crop_native(view,X,aspect=1.9,pad=.15)
    D=np.load(ex/'mvs'/f'{view}.npy');cf=np.load(ex/'conf'/f'{view}.npy');roi=np.isin(lm,idx)
    gt=np.load(U/'points'/site/'gt_xyz.npy',mmap_mode='r');poses,cams=models();_,cam=cameras_depth();Z=zbuffer(gt,poses[view],cam)
    tau={'B0_b10':.1975,'B173nb_b10':.176,'R1rep_b10':.7246}[site]
    valid=np.isfinite(D)&(D>0)&(cf>0);missing=roi&~valid;known=np.isfinite(Z);wrong=roi&valid&known&(abs(D-Z)>tau)
    lab=np.zeros_like(D,np.uint8);lab[missing&known]=1;lab[wrong]=2
    marked=native_mask(im,photo,lab,cam)
    n=int(roi.sum());rec=dict(site=site,face=face,patch_indices=idx,photo=photo,tau_m=tau,pixels=n,missing_share=float(missing.sum()/n) if n else None,wrong_share=float(wrong.sum()/n) if n else None,unknown_gt_share=float((roi&~known).sum()/n) if n else None,gt_visible_pixels=int((roi&known).sum()),missing_painted_pixels=int((missing&known).sum()),unknown_gt_display='uncoloured for both missing and wrong; missing count itself uses all ROI pixels',source_depth=str(ex/'mvs'/f'{view}.npy'),confidence=str(ex/'conf'/f'{view}.npy'),gt_source=str(U/'points'/site/'gt_xyz.npy'),denominator='all projected ROI pixels; wrong counted only at occupied exact GT z-buffer pixels; no interpolation')
    return im,marked,rec
def specular_panel(row):
    photo=row['photos'][0];X=np.asarray(row['gt_representative']);view=photo['view'];im,photo=crop_native(view,X,aspect=1/1.9 if not row['roof'] else 1.9,pad=.12);poses,cam=cameras_depth();pose=poses[view]
    Q=np.asarray(row['centre']);uv,z=G.project(Q,pose,cam);hull=ConvexHull(uv);roi=np.zeros((741,1024),np.uint8);cv2.fillPoly(roi,[np.round(uv[hull.vertices]).astype(np.int32)],1);roi=roi.astype(bool)
    meta=load(PAY/'task0/global_visibility/complete.json');Z=np.load(PAY/'task0/global_visibility/zbuffer.npy',mmap_mode='r')[meta['names'].index(view)].reshape(741,1024)
    dp=W/'mvs/full/stereo/depth_maps'/f'{pose["name"]}.geometric.bin';D=depth(dp);valid=np.isfinite(D)&(D>0);known=np.isfinite(Z);missing=roi&~valid;wrong=roi&valid&known&(abs(D-Z)>row['tau_m'])
    lab=np.zeros_like(D,np.uint8);lab[missing&known]=1;lab[wrong]=2;marked=native_mask(im,photo,lab,cam);n=int(roi.sum())
    if not row['roof']:im=im.transpose(Image.Transpose.ROTATE_90);marked=marked.transpose(Image.Transpose.ROTATE_90);photo['display_rotation_deg']=90
    return im,marked,dict(component_id=row['component_id'],photo=photo,tau_m=row['tau_m'],pixels=n,missing_share=float(missing.sum()/n),wrong_share=float(wrong.sum()/n),unknown_gt_share=float((roi&~known).sum()/n),gt_visible_pixels=int((roi&known).sum()),missing_painted_pixels=int((missing&known).sum()),unknown_gt_display='uncoloured for both missing and wrong; missing count itself uses all ROI pixels',source_depth=str(dp),confidence='COLMAP geometric depth finite and >0',denominator='component projected hull, all pixels; unknown GT is not called wrong',mask_support='convex hull of component patch centres')
def main():
    c=config();roof=load(PAY/'selection_a_roof.json')['selected'];selected=load(DOC/'figures/task0_specular_candidates.json')['selected'];assert selected
    # Exact missing columns of PHOTOFIG fig3, only used for this fixed place.
    with np.load(S1/'regions_v3/regions_ext_v3_R1rep_b10_LoD2.npz') as z:ix=np.flatnonzero(z['in_eval']&(z['surf_ext']==19)&np.isin(z['code_ext_v3'],[4,13]))
    panels=[legacy_panel(roof['site'],roof['face'],roof['view']),legacy_panel('R1rep_b10',19,'DJI_20241217101317_0011_D',ix),specular_panel(selected)]
    labels=['무늬 없는 지붕','그늘진 벽',selected['material_ko']]
    plt=plot_setup(55);fig=plt.figure(figsize=(27,12),dpi=100)
    for col,((raw,marked,rec),label) in enumerate(zip(panels,labels)):
        x=.005+col/3
        for y,im in [(.53,raw),(.10,marked)]:
            ax=fig.add_axes([x,y,.323,.36]);ax.imshow(im);ax.axis('off')
        fig.text(x+.1615,.98,label,ha='center',va='top',fontsize=55)
        fig.text(x+.1615,.035,f'깊이 없음 {100*rec["missing_share"]:.0f}% · 틀림 {100*rec["wrong_share"]:.0f}%',ha='center',va='center',fontsize=55)
    p=DOC/'figures/figS_a_image_limits.png';fig.savefig(p,dpi=100,facecolor='white');plt.close(fig)
    dump(p.with_suffix('.json'),dict(task_id=c['task_id'],scientific_verdict=None,panels=[r for _,_,r in panels],source='[이 발주에서 냄]',colour=dict(missing=c['colours']['missing'],wrong=c['colours']['wrong']),reference='UAS LiDAR in inherited aligned frame, not independent ground truth claim'))
    print('DRAW a',[(r['pixels'],r['missing_share'],r['wrong_share'],r['unknown_gt_share']) for _,_,r in panels],flush=True)
if __name__=='__main__':main()
