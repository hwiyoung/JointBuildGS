"""Lock photo/crop choices before rendering. New selection never reads gt_p or outcomes."""
from rfcore import *
import io
import zipfile
import hashlib
from PIL import Image

def photo_config():
    c=load('/repo/configs/phd/main_regionfig_v1/regionfig_v1.json')
    return c

def select(ex,d,rawposes,rawcams,trainposes,traincams,train):
    c=photo_config();a=np.array(ex['start_xy']);b=np.array(ex['end_xy']);L=np.linalg.norm(b-a);v=(b-a)/L
    p=d['centre'];normal=d['normal'];along=(p[:,:2]-a)@v;across=(p[:,:2]-a)@[-v[1],v[0]]
    # All selection support comes from the image surface, with the prior filling gaps.
    # Supplied cells, judgments, result values and reference distances are not read here.
    h=p[:,2]+np.where(np.isfinite(d['mvs_p']),d['mvs_p'],0)*normal[:,2]
    band=d['matched']&d['roof_like']&(along>=0)&(along<=L)&(abs(across)<=ex['half_width_m'])
    samples=np.linspace(0,L,int(np.ceil(L/.05))+1)
    med=[];bc=[]
    for x in np.arange(0,L,.25):
        m=band&(along>=x)&(along<min(x+.25,L+1e-8))&np.isfinite(h)
        if m.any():bc.append(min(x+.125,L));med.append(float(np.median(h[m])))
    assert med, f'No image/prior section support for {ex["id"]}'
    line=np.c_[a+samples[:,None]*v,np.interp(samples,bc,med)]
    mid=(line[1:]+line[:-1])/2;ds=np.diff(samples)
    local=d['matched']&np.isfinite(d['mvs_p'])&np.all((p[:,:2]>=np.minimum(a,b)-10)&(p[:,:2]<=np.maximum(a,b)+10),axis=1)
    support=p[local]+d['mvs_p'][local,None]*normal[local]
    candidates=[]
    for stem in train:
        if stem not in rawposes or stem not in trainposes:continue
        pose=rawposes[stem];tp=trainposes[stem];cam=rawcams[pose['cam']];tc=traincams[tp['cam']]
        assert np.max(abs(pose['R']-tp['R']))<1e-8 and np.max(abs(pose['t']-tp['t']))<1e-8
        uv,z=project(line,pose,cam);tu,tz=project(line,tp,tc)
        inside=np.all((z>0)&(uv[:,0]>=0)&(uv[:,0]<cam['w'])&(uv[:,1]>=0)&(uv[:,1]<cam['h']))
        inside=inside and np.all((tz>0)&(tu[:,0]>=0)&(tu[:,0]<tc['w'])&(tu[:,1]>=0)&(tu[:,1]<tc['h']))
        if not inside:continue
        crop,box=old.native_crop_box(line,pose,cam,c)
        if not box['full_4m_margin_inside']:continue
        candidates.append(dict(stem=stem,tilt_deg=geo.tilt(pose),projected_line_length_px=float(np.linalg.norm(np.diff(uv,axis=0),axis=1).sum())))
    assert candidates,f'STOP: no photograph candidate for {ex["id"]}'
    def evaluate(rows):
        for row in rows:
            pose=rawposes[row['stem']];cam=rawcams[pose['cam']]
            hidden,known,*_=old.visibility(support,mid,pose,cam,c)
            row.update(occluded_length_m=float(ds[hidden].sum()),occluded_fraction=float(ds[hidden].sum()/L),unknown_length_m=float(ds[~known].sum()))
        return sorted(rows,key=lambda r:(r['occluded_length_m'],-r['projected_line_length_px'],r['stem']))
    nadir=evaluate([r for r in candidates if r['tilt_deg']<=20])
    fallback=not nadir or nadir[0]['occluded_fraction']>.2
    ordered=evaluate(candidates) if fallback else nadir
    best=ordered[0];pose=rawposes[best['stem']];cam=rawcams[pose['cam']]
    crop,box=old.native_crop_box(line,pose,cam,c)
    # Optional whole-building expansion uses only image/prior geometry.
    building=p+d['normal']*np.where(np.isfinite(d['mvs_p']),d['mvs_p'],0)[:,None]
    uv,z=project(building[d['matched']&d['roof_like']],pose,cam)
    uv=uv[z>0];lo=np.floor(uv.min(0)-20).astype(int);hi=np.ceil(uv.max(0)+20).astype(int)
    expanded=[min(crop[0],int(lo[0])),min(crop[1],int(lo[1])),max(crop[2],int(hi[0])),max(crop[3],int(hi[1]))]
    whole=expanded[0]>=0 and expanded[1]>=0 and expanded[2]<=cam['w'] and expanded[3]<=cam['h']
    if whole:crop=expanded
    hidden,known,*_=old.visibility(support,mid,pose,cam,c)
    q,_=project(line,pose,cam)
    dump(PAY/f'candidates_{ex["id"]}.json',dict(ranked=ordered,eligible=len(candidates),nadir=len(nadir),expanded_to_oblique=fallback,
         selection_uses_reference=False,occlusion_source='supplied MVS positions in section +/-10m; unknown recorded separately',support_points=len(support)))
    return dict(**best,pose=pose,camera=cam,crop_box_px=crop,native_size_px=[cam['w'],cam['h']],
                line_xyz=line,line_pixels=q,line_s_m=samples,line_midpoint_occluded=hidden,line_midpoint_known=known,
                whole_building_expansion=whole,crop_world_box=box,selection_uses_reference=False,
                visibility_source='local supplied image-surface positions; outside occluders unavailable',
                candidate_count=len(candidates),nadir_candidate_count=len(nadir),expanded_to_oblique=fallback)

def main():
    assert not (CFG/'regionfig_v2.lock.json').exists(), 'Never overwrite a locked configuration'
    rawposes=poses(DENSE/'triangulated/images.bin');rawcams=cameras(DENSE/'triangulated/cameras.bin')
    trainposes=poses(W/'mvs/full/sparse/images.bin');traincams=cameras(W/'mvs/full/sparse/cameras.bin')
    train=[Path(x).stem for x in load(W/'image_split.json')['train']]
    previous=load(V1/'prepared.json');oldphotos={r['id']:r['photo'] for r in previous['examples']}
    exs=examples()
    with zipfile.ZipFile(RAW) as archive:
        members={Path(n).stem:n for n in archive.namelist() if n.upper().endswith('.JPG')}
        for ex in exs:
            d=data(ex['prior'],ex['building'])
            if ex['fixed_v1_photo']:
                photo=oldphotos[ex['fixed_v1_photo']].copy()
                photo['selection_reused_from_v1']=True
                photo['selection_uses_reference']='historical v1 occlusion uses reference; fixed photo reused without reselection'
                photo['whole_building_expansion']=False
            else:
                photo=select(ex,d,rawposes,rawcams,trainposes,traincams,train)
            pose={k:np.array(v) if k in ['R','t'] else v for k,v in photo['pose'].items()}
            cam=dict(photo['camera']);cam['p']=np.array(cam['p'])
            # Displayed section alone uses reference height, allowed by the work order.
            sec=sections(ex,d);h=np.array(sec['heights_model_m']);bc=np.array(sec['bin_centres_m']);valid=np.isfinite(h[:,2])
            s=np.asarray(photo['line_s_m']);a=np.array(ex['start_xy']);b=np.array(ex['end_xy']);L=sec['length_m']
            if valid.any():
                display=np.c_[a+(b-a)*s[:,None]/L,np.interp(s,bc[valid],h[valid,2])]
                q,z=project(display,pose,cam)
                photo['display_line_xyz']=display;photo['display_line_pixels']=q
            else:
                photo['display_line_xyz']=photo['line_xyz'];photo['display_line_pixels']=photo['line_pixels']
            mid=np.asarray(photo['line_xyz'])[len(photo['line_xyz'])//2]
            north,_=project(np.array([mid,mid+[0,1,0]]),pose,cam);du,dv=north[1]-north[0]
            photo['display_rotation_degrees']=float(np.degrees(np.pi/2-np.arctan2(-dv,du)))
            member=members[photo['stem']];raw=archive.read(member)
            im=Image.open(io.BytesIO(raw));assert im.size==(5280,3956)
            crop=im.crop(photo['crop_box_px']).convert('RGB');assert min(crop.size)>=600
            path=DOC/f'figures/crops/{ex["id"]}_원본.png';path.parent.mkdir(parents=True,exist_ok=True)
            crop.save(path)
            photo.update(original_member=member,original_sha256=hashlib.sha256(raw).hexdigest(),crop_size_px=list(crop.size),
                         crop_sha256=sha(path),original_archive=str(RAW))
            ex['photo']=photo;dump(PAY/f'section_{ex["id"]}.json',sec)
            print('prepared',ex['id'],photo['stem'],photo['crop_box_px'],photo['display_rotation_degrees'],flush=True)
    cfg=dict(task_id='PHD-MAIN-REGIONFIG-v2',scientific_verdict=None,prepared_at=now(),examples=exs,
             frame=dict(crs='EPSG:25832',subtract_xyz_m=[690953,5336071,604],north='+y'),
             photo=dict(alpha=.45,rank=['minimum occluded length','maximum projected section length','stem'],
                        nadir_max_deg=20,minimum_crop_side_px=600,margin_m=4,reference_height_for_overlay=True),
             section=dict(bin_m=.25,summary='median of centre_z + supplied distance * normal_z',strip='area-dominant category per bin'),
             colors=dict(regions=dict(zip(REGIONS,REGION_COLORS)),judgments=dict(zip(JUDGMENTS,JUDGE_COLORS)),
                         right='#2171b5',wrong='#e31a1c',prior='#222222',mvs='#d08a2e',reference='#2e8b57',category='#888888',check='#2171b5'),
             layout=dict(rows=2,columns=3,inches=[22,14],dpi=300),
             crop_population='projected centre inside native box; finite reference uses centre+gt_p*normal; missing reference uses prior centre only to count unpainted area',
             photo_region_population='all supplied matched patches with finite reference and projected centre inside crop',
             result_population='same roof_like finite-reference patches in both result panels',
             patch_shape='tangent square; side sqrt(supplied area)',
             resource_policy=load(CFG/'resource_approval.json'),
             amendments=[dict(at=now(),reason='New photo selection must not read reference: v1 projection/ranking retained, visibility uses supplied image surface; fixed v1 photos reused for figures 2 and 3.',changes_values=False),
                         dict(at=now(),reason='Figure text uses 영상의 면 for MVS and 사전 정보 for LoD2 to meet the no-abbreviation rule.',changes_values=False)])
    dump(CFG/'regionfig_v2.json',cfg)
    dump(CFG/'regionfig_v2.lock.json',dict(locked_at=now(),config_sha256=sha(CFG/'regionfig_v2.json'),before_first_figure=True,
                                         input_receipt_sha256=sha(PAY/'input_receipt.json'),environment=environment(),scientific_verdict=None))
    print('LOCKED',sha(CFG/'regionfig_v2.json'),environment(),flush=True)

if __name__=='__main__':main()
