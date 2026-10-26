"""Independent checks of supplied numbers, exact native crop pixels, and delivery figures."""
from rfcore import *
import io
import zipfile
from PIL import Image

def main():
    cfg=load(CFG/'regionfig_v2.json');lock=load(CFG/'regionfig_v2.lock.json');checks=[]
    def check(name,value,details=None):
        checks.append(dict(name=name,passed=bool(value),details=details))
        if not value:print('FAIL',name,details,flush=True)
    check('frozen config SHA256',sha(CFG/'regionfig_v2.json')==lock['config_sha256'])
    for k,prefix in [('ALS_sites.npz','2209c54db0112710'),('LoD2_sites.npz','d769ece96663c34e'),('sites_summary.json','f28aa9906054fe0f')]:
        check('input '+k,sha(PAY/'input'/k).startswith(prefix))
    inputs={}
    for prior in ['ALS','LoD2']:
        with np.load(PAY/'input'/f'{prior}_sites.npz',allow_pickle=False) as z:inputs[prior]={k:z[k] for k in z.files}
    nativeposes=poses(DENSE/'triangulated/images.bin');tcams=cameras(W/'mvs/full/sparse/cameras.bin');tp=poses(W/'mvs/full/sparse/images.bin')
    with zipfile.ZipFile(RAW) as archive:
        for ex in cfg['examples']:
            ident=ex['id'];path=DOC/f'figures/영역표본_{ident}_{ex["slug"]}.png';rec=load(path.with_suffix('.json'));photo=ex['photo']
            with Image.open(path) as im:
                check(ident+' dimensions',im.size==(6600,4200),im.size)
                check(ident+' 300 dpi',all(abs(x-300)<.02 for x in im.info['dpi']),im.info['dpi'])
            check(ident+' figure hash',sha(path)==rec['figure_sha256'])
            check(ident+' lock before render',lock['locked_at']<rec['environment']['at'])
            raw=archive.read(photo['original_member']);check(ident+' original hash',hashlib.sha256(raw).hexdigest()==photo['original_sha256'])
            with Image.open(io.BytesIO(raw)) as original:
                expected=np.asarray(original.crop(photo['crop_box_px']).convert('RGB'))
            with Image.open(DOC/f'figures/crops/{ident}_원본.png') as crop:
                actual=np.asarray(crop.convert('RGB'));check(ident+' exact native crop pixels',np.array_equal(actual,expected));check(ident+' min native side',min(crop.size)>=600)
            sizes=[]
            for label in ['영역','사진검사','범주별','검사기반']:
                with Image.open(DOC/f'figures/crops/{ident}_{label}.png') as im:sizes.append(im.size)
            check(ident+' equal four photo canvases',len(set(sizes))==1,sizes)
            source=inputs[ex['prior']];lookup={s:i for i,s in enumerate(source['patch_id'])}
            ids=np.array([lookup[s] for s in rec['result_patch_ids']]);a=source['area'][ids].astype(float);gt=source['gt_p'][ids].astype(float);tau=source['tau'][ids].astype(float)
            check(ident+' result population valid',source['roof_like'][ids].all() and np.isfinite(gt).all())
            check(ident+' no duplicated result patches',len(np.unique(ids))==len(ids))
            den=sum(float(x) for x in a)
            check(ident+' result denominator',abs(den-rec['metrics']['result_area_m2'])<1e-8)
            for key in ['category','check']:
                result=source['z_'+key][ids].astype(float)
                num=sum(float(weight) for weight,zz,gg,tt in zip(a,result,gt,tau) if abs(zz-gg)<=tt)
                check(ident+' supplied '+key+' area rate',abs(100*num/den-rec['metrics']['ok_'+key+'_pct'])<1e-9)
            missing=~np.isfinite(source['mvs_p'][ids]);check(ident+' inheritance unchanged',np.all(source['z_category'][ids][missing]==0) and np.all(source['z_check'][ids][missing]==0))
            d=data(ex['prior'],ex['building']);index={s:i for i,s in enumerate(d['patch_id'])};ci=np.array([index[s] for s in rec['crop_patch_ids']]);cc=d['centre'][ci]+np.nan_to_num(d['gt_p'][ci])[:,None]*d['normal'][ci]
            pu,pz=project(cc,tp[photo['stem']],tcams[tp[photo['stem']]['cam']]);camera=tcams[tp[photo['stem']]['cam']]
            check(ident+' cropped centres in calibrated field',np.all((pz>0)&(pu[:,0]>=0)&(pu[:,0]<camera['w'])&(pu[:,1]>=0)&(pu[:,1]<camera['h'])))
            q=np.array(photo['display_line_pixels']);x0,y0,x1,y1=photo['crop_box_px']
            check(ident+' entire displayed section in crop',np.all((q[:,0]>=x0)&(q[:,0]<=x1)&(q[:,1]>=y0)&(q[:,1]<=y1)))
            start=np.array(ex['start_xy']);end=np.array(ex['end_xy']);length=float(np.linalg.norm(end-start));along=(d['centre'][:,:2]-start)@(end-start)/length
            across=(d['centre'][:,:2]-start)@np.array([-(end-start)[1],(end-start)[0]])/length
            band=d['roof_like']&d['matched']&(along>=0)&(along<=length)&(abs(across)<=ex['half_width_m'])
            check(ident+' independent section membership',set(d['patch_id'][band])==set(rec['section']['band_patch_ids']))
            rawh=np.array(rec['section']['heights_model_m'],float);edges=np.array(rec['section']['bin_edges_m'])
            for k,field in enumerate([None,'mvs_p','gt_p','z_category','z_check']):
                values=d['centre'][:,2] if field is None else d['centre'][:,2]+d[field]*d['normal'][:,2]
                med=[]
                for i in range(len(edges)-1):
                    include=band&(along>=edges[i])&(along<edges[i+1] if i<len(edges)-2 else along<=edges[i+1])&np.isfinite(values)
                    ordered=sorted(float(v) for v in values[include]);n=len(ordered)
                    med.append((ordered[n//2]+ordered[(n-1)//2])/2 if n else np.nan)
                check(ident+' section median '+str(field),np.allclose(med,rawh[:,k],atol=1e-9,equal_nan=True))
            if ex['fixed_v1_photo']:
                oldphoto=next(q['photo'] for q in load(V1/'prepared.json')['examples'] if q['id']==ex['fixed_v1_photo'])
                check(ident+' exact v1 photo and box',photo['stem']==oldphoto['stem'] and photo['crop_box_px']==oldphoto['crop_box_px'])
            check(ident+' scientific verdict null',rec['scientific_verdict'] is None)
    joined=load(DOC/'tables/input_validation.json')
    check('all 261281 patches joined',sum(x['patches'] for x in joined['joins'])==261281 and all(x['unmatched']==0 for x in joined['joins']))
    check('all seven summary rate pairs match',all(x['rate_matches'] for x in joined['summary_checks']))
    dump(DOC/'tables/verification.json',dict(status='PASS' if all(x['passed'] for x in checks) else 'FAIL',checks=checks,environment=environment(),scientific_verdict=None))
    print('VERIFIED',sum(x['passed'] for x in checks),'/',len(checks),environment())
    if not all(x['passed'] for x in checks):raise SystemExit(1)

if __name__=='__main__':
    import hashlib
    main()
