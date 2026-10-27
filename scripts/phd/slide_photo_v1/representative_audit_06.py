"""Input-only representativeness audit, before replacement photography."""
from common import *
from scipy import ndimage

OUT=DOC/'revision_06';CACHE=PAY/'revision_06'

def scan():
    c=load(CFG/'representative_audit_06.json');poses=G.poses(G.DENSE/'triangulated/images.bin');rows=[];scope=[]
    for site in c['scope']:
        with np.load(U/'patch_values'/f'{site}__LoD2__R1.5.npz') as f:z={k:f[k] for k in ['normal','in_eval','roof_like','surf']}
        flat=z['in_eval']&z['roof_like']&(abs(z['normal'][:,2])>=np.cos(np.deg2rad(c['flat_roof_normal_degrees'])));face_total={int(f):int((flat&(z['surf']==f)).sum()) for f in np.unique(z['surf'][flat])};n0=len(rows)
        for name in load(S0/'fork_inputs/s61'/site/'split.json')['train']:
            view=Path(name).stem
            if G.tilt(poses[view])>c['nadir_tilt_degrees']:continue
            ex=S0/'s61/export'/site/'LoD2';path=ex/'locmap'/f'{view}.npy'
            if not path.exists():continue
            lm=np.load(path);inside=lm>=0;idx=lm[inside].astype(int);D=np.load(ex/'mvs'/f'{view}.npy');cf=np.load(ex/'conf'/f'{view}.npy');valid=np.isfinite(D)&(D>0)&(cf>0);face=z['surf'][idx];isflat=flat[idx]
            for f in np.unique(face[isflat]):
                roi=np.zeros(lm.shape,bool);roi[inside]=isflat&(face==f);n=int(roi.sum());missing=roi&~valid;nmiss=int(missing.sum());fraction=len(np.unique(lm[roi]))/face_total[int(f)];component=0
                size_ok=n>=c['minimum_projected_pixels'];share_ok=nmiss/n>=c['minimum_missing_share'];coverage_ok=fraction>=c['minimum_visible_unique_patch_fraction']
                if size_ok and share_ok and coverage_ok:
                    lab,count=ndimage.label(missing);hist=np.bincount(lab.ravel());component=int(hist[1:].max()) if count else 0
                eligible=size_ok and share_ok and coverage_ok and component>=c['minimum_connected_missing_pixels']
                rows.append(dict(site=site,face=int(f),view=view,pixels=n,missing_pixels=nmiss,missing_share=nmiss/n,visible_unique_patch_fraction=fraction,flat_evaluation_patches=face_total[int(f)],largest_missing_component_pixels=component,eligible=bool(eligible)))
        scope.append(dict(site=site,face_view_pairs=len(rows)-n0));print('SCAN',site,len(rows)-n0,flush=True)
    good=sorted([r for r in rows if r['eligible']],key=lambda r:(-r['missing_pixels'],-r['pixels'],r['site'],r['face'],r['view']))
    result=dict(task_id=c['task_id'],scientific_verdict=None,at=now(),config=c,config_sha256=sha(CFG/'representative_audit_06.json'),status='CANDIDATE_FOUND' if good else 'NO_REPRESENTATIVE_CANDIDATE',selected=good[0] if good else None,eligible_count=len(good),scope=scope,rows=rows,old_selection=load(PAY/'selection_a_roof.json')['selected'],old_failure='Ratio-only ranking allowed a 20-pixel projection with no minimum area or visible-face support. This is insufficient for a broad roof failure illustration.')
    dump(OUT/'roof_representativeness_audit.json',result);print(result['status'],result['selected'],'eligible',len(good),flush=True)

def photo():
    from photos import crop_native,models
    from task0_scan import cameras_depth
    from draw_a import native_mask
    audit=load(OUT/'roof_representativeness_audit.json');row=audit['selected'];assert row
    site,face,view=row['site'],row['face'],row['view'];ex=S0/'s61/export'/site/'LoD2'
    with np.load(U/'patch_values'/f'{site}__LoD2__R1.5.npz') as z:idx=np.flatnonzero(z['in_eval']&z['roof_like']&(z['surf']==face)&(abs(z['normal'][:,2])>=np.cos(np.deg2rad(10))));X=z['centre'][idx]
    im,p=crop_native(view,X,aspect=2.33,pad=.22);lm=np.load(ex/'locmap'/f'{view}.npy');roi=np.isin(lm,idx);D=np.load(ex/'mvs'/f'{view}.npy');cf=np.load(ex/'conf'/f'{view}.npy');valid=np.isfinite(D)&(D>0)&(cf>0)
    visibility=load(PAY/'task0/global_visibility/complete.json');assert view in visibility['names'];Z=np.load(PAY/'task0/global_visibility/zbuffer.npy',mmap_mode='r')[visibility['names'].index(view)].reshape(741,1024);known=np.isfinite(Z)
    thresholds=load(REPO/'configs/phd/main_uncert_v1/uncert_v1.json')
    # The existing table distinguishes roof from wall thresholds.
    def find_tau(d):
        if isinstance(d,dict):
            if 'tau_cm' in d:return d['tau_cm']
            for v in d.values():
                r=find_tau(v)
                if r is not None:return r
        return None
    tau=find_tau(thresholds)[site]['roof']/100
    missing=roi&~valid;wrong=roi&valid&known&(abs(D-Z)>tau);lab=np.zeros_like(D,np.uint8);lab[missing&known]=1;lab[wrong]=2;_,cam=cameras_depth();marked=native_mask(im,p,lab,cam)
    n=int(roi.sum());assert n==row['pixels'];assert int(missing.sum())==row['missing_pixels']
    record=dict(site=site,face=face,patch_indices=idx,photo=p,tau_m=tau,tau_source='configs/phd/main_uncert_v1/uncert_v1.json roof threshold',pixels=n,missing_share=float(missing.sum()/n),wrong_share=float(wrong.sum()/n),unknown_gt_share=float((roi&~known).sum()/n),gt_visible_pixels=int((roi&known).sum()),missing_painted_pixels=int((missing&known).sum()),unknown_gt_display='Uncoloured; missing counts all ROI pixels, wrong only where exact reference z-buffer is occupied',source_depth=str(ex/'mvs'/f'{view}.npy'),confidence=str(ex/'conf'/f'{view}.npy'),gt_source=str(PAY/'task0/global_visibility/zbuffer.npy'),visibility='Existing nearest-camera-Z over all 24 public input tiles, no interpolation',denominator='Projected selected flat roof face pixels',source='[이 발주에서 냄] replacement candidate, input-only fixed R6 rule')
    im.save(CACHE/'roof_raw.png');marked.save(CACHE/'roof_marked.png');dump(OUT/'roof_photo_evidence.json',record);print('ROOF',n,'missing',record['missing_share'],'painted',record['missing_painted_pixels'],'unknown',record['unknown_gt_share'],'tau',tau,flush=True)

if __name__=='__main__':
    config();OUT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    (photo if len(sys.argv)>1 and sys.argv[1]=='photo' else scan)()
