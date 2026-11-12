"""Development-only geometry. No truth inputs are opened here."""
import json,sys,time,resource
import numpy as np
from scipy.spatial import cKDTree
from preflight import C,D,O,R,Path,sha,dump,now
from cylinder import run
BASE=O/'r1';S=Path(__file__).parent

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def savez(p,**d):
    p.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(p,**d)

def cfg():
    c=json.loads((C/'judgecheck_v1.json').read_text())
    assert sha(C/'judgecheck_v1.json')==json.loads((C/'judgecheck_v1.reply1.lock.json').read_text())['config_sha256']
    assert json.loads((BASE/'input_receipt.json').read_text())['status']=='PASS_SAFE_DEVELOPMENT_INPUTS'
    return c

def lock():
    c=cfg();p=C/'geometry.reply1.lock.json'
    data=dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),source_sha256={f.name:sha(f) for f in [S/'geometry.py',S/'cylinder.py',S/'cylinders.cpp',S/'u_core.py']},
        normal_neighbourhood='3D sphere at original core; abs(z - TIN z)<=1m; orthogonal least-squares PCA; population residual SD',
        normal_fallback='2m plane when no candidate qualifies; fewer than 3 or degenerate points => unavailable, never invent a normal',
        cylinder='unchanged inherited outer face and +/-1m slab; lengths 5 and 10m',
        LoD2_mvs='reuse verified JUDGENUM cached 10m cylinder at identical core/normal/radius; retain 5m comparison',
        als_radius_selection='all development ALS roof cores with valid fitted normal; smallest median count >=20; no forced fallback',
        truth_inputs_opened=False,scientific_verdict=None)
    if not p.exists():dump(p,data)
    else:
        old=json.loads(p.read_text());assert old['source_sha256']==data['source_sha256']
    return c

def fit_normals(points,centres):
    tree=cKDTree(points);N=len(centres);normal=np.full((N,3),np.nan);radius=np.full(N,2.);rough=np.full(N,np.nan);count=np.zeros(N,np.int32);valid=np.zeros(N,bool)
    for start in range(0,N,1024):
        lists=tree.query_ball_point(centres[start:start+1024],2.,workers=1)
        for j,ids in enumerate(lists):
            i=start+j;v=points[np.asarray(ids,int)]-centres[i];v=v[abs(v[:,2])<=1.];dist2=np.sum(v*v,1)
            for r in [.5,.75,1.,1.5,2.]:
                q=v[dist2<=r*r];nn=len(q)
                if nn<3:continue
                cen=q.mean(0);vv=q-cen;evals,evecs=np.linalg.eigh(vv.T@vv)
                if evals[1]<=1e-16:continue
                n=evecs[:,0];n*=1 if n[2]>=0 else -1;sd=float(np.std(vv@n))
                good=nn>=10 and r>=25*sd
                if good or r==2.:
                    normal[i]=n;radius[i]=r;rough[i]=sd;count[i]=nn;valid[i]=good;break
        if start%20000<1024:print('NORMAL',start,N,flush=True)
    return dict(normal=normal,normal_radius_m=radius,normal_roughness_m=rough,normal_point_count=count,normal_rule_met=valid)

def phase1(tile=None):
    c=lock();w=Path(c['sources']['widen']);jn=Path(c['sources']['judgenum'])
    files=sorted((BASE/'inputs').glob(f'{tile or "*"}__*.npz'))
    for p in files:
        dest=BASE/'geometry_raw'/p.name
        if dest.exists():continue
        t0=time.monotonic();d=loadz(p);tile,prior=p.stem.split('__');pts=w/'holdout/internal/points'/tile
        if prior=='ALS':
            normpath=BASE/'normal'/p.name
            if normpath.exists():norm=loadz(normpath)
            else:
                points=np.load(pts/'als_xyz.npy');norm=fit_normals(points,d['centre']);savez(normpath,**norm);del points
            d['old_normal']=d['normal'];d.update(norm)
            rad=c['geometry']['als_cylinder_radii_m'];raw=BASE/'cylinder_data'/f'{tile}__ALS_prior.bin'
            if raw.with_suffix('.json').exists():a=np.memmap(raw,mode='r',dtype='<f8',shape=(len(d['centre']),2,len(rad),7))
            else:a=run(pts/'als_xyz.npy',d['centre'],d['normal'],rad,raw)
            d['als_candidates']=np.asarray(a).copy();del a
            raw=BASE/'cylinder_data'/f'{tile}__ALS_mvs.bin'
            if raw.with_suffix('.json').exists():a=np.memmap(raw,mode='r',dtype='<f8',shape=(len(d['centre']),2,1,7))
            else:a=run(pts/'mvs_a_xyz.npy',d['centre'],d['normal'],[.075],raw)
            d['mvs_cylinder']=np.asarray(a[:,:,0,:]).copy();del a
        else:
            meta=json.loads((jn/'cylinders'/f'{tile}.complete.json').read_text());part=next(r for r in meta['parts'] if Path(r['file']).name==p.name)
            with np.load(jn/'inputs'/p.name) as z:
                index={pid:i for i,pid in enumerate(z['patch_id'])};ix=np.array([index[pid] for pid in d['patch_id']])
                assert np.array_equal(d['centre'],z['centre'][ix]) and np.array_equal(d['normal'],z['normal'][ix])
            total=max(r['start']+r['count'] for r in meta['parts']);raw=jn/'cylinders'/f'{tile}.bin'
            source_meta=json.loads(raw.with_suffix('.json').read_text());assert source_meta['half_lengths_m']==[5.,3.,10.]
            assert source_meta['radii_m'][1]==.075 and source_meta['radii_m'][3]==.125
            assert sha(raw)==source_meta['output_sha256']
            cache=np.memmap(raw,mode='r',dtype='<f8',shape=(total,3,10,7));rr=np.where(d['kind']==1,1,3)
            d['mvs_cylinder']=np.stack([cache[part['start']+ix,h,rr,:] for h in [0,2]],1);del cache
            d['normal_radius_m']=np.full(len(ix),np.nan);d['normal_roughness_m']=np.full(len(ix),np.nan)
            d['normal_point_count']=np.zeros(len(ix),np.int32);d['normal_rule_met']=np.ones(len(ix),bool)
        savez(dest,**d)
        dump(dest.with_suffix('.receipt.json'),dict(at=now(),seconds=time.monotonic()-t0,count=len(d['centre']),
            source_sha256=sha(p),output_sha256=sha(dest),truth_opened=False,peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,scientific_verdict=None))
        print('GEOMETRY_RAW',tile,prior,len(d['centre']),time.monotonic()-t0,flush=True)

def calibrate():
    c=lock();files=sorted((BASE/'geometry_raw').glob('*.npz'));assert len(files)==len(list((BASE/'inputs').glob('*.npz')))
    candidate=[]
    for p in files:
        if p.stem.endswith('__ALS'):
            with np.load(p) as z:
                a=z['als_candidates'];valid=np.isfinite(z['normal']).all(1);candidate.append(a[valid,1,:,0])
    a=np.concatenate(candidate);quant=np.quantile(a,[.25,.5,.75],axis=0);rad=c['geometry']['als_cylinder_radii_m'];chosen=np.flatnonzero(quant[1]>=20)
    radius=rad[int(chosen[0])] if len(chosen) else None
    rows=[dict(radius_m=r,count=len(a),q25=float(quant[0,i]),median=float(quant[1,i]),q75=float(quant[2,i])) for i,r in enumerate(rad)]
    dump(BASE/'als_radius.json',dict(at=now(),rows=rows,selected_radius_m=radius,scientific_verdict=None))
    if radius is None:raise RuntimeError('No ALS radius reaches median 20; retain unavailable, no guessed radius')
    rid=rad.index(radius);agree_by_building={};groupdiff={};prepared=[]
    for p in files:
        d=loadz(p);prior=p.stem.split('__')[1];a=d['mvs_cylinder'][:,1];d.update(n=a[:,0].astype(int),mvs_mean_m=a[:,1],mvs_median_m=a[:,2],mvs_sd_m=a[:,3],n5=d['mvs_cylinder'][:,0,0].astype(int))
        if prior=='ALS':
            a=d['als_candidates'][:,1,rid];d['prior_n']=a[:,0].astype(int);hp=a[:,1].copy();hp[d['prior_n']<4]=np.nan;sp=d['u_prior'].astype(float)
        else:
            hp=np.zeros(len(a));sp=np.array([c['geometry']['prior_sigma_m']['LoD2_roof'].get(str(k),.11) for k in d['roof_type']]);sp[d['kind']==2]=.144
            d['prior_n']=np.full(len(a),-1,int)
        d['prior_height_m']=hp;d['sigma_P_m']=sp;d['d_m']=d['mvs_mean_m']-hp
        good=(d['n']>=4)&np.isfinite(d['d_m'])&np.isfinite(d['u_mvs'])&np.isfinite(sp)
        agree=good&(abs(d['d_m'])<=1.96*np.hypot(d['u_mvs'],sp));d['agreement_for_calibration']=agree
        for k in np.unique(d['kind']):groupdiff.setdefault(f'{prior}_{k}',[]).append(d['d_m'][agree&(d['kind']==k)])
        if prior=='ALS':
            for bid in np.unique(d['building'][agree]):agree_by_building.setdefault(str(bid),[]).append(d['d_m'][agree&(d['building']==bid)])
        dest=BASE/'geometry_base'/p.name;savez(dest,**d);prepared.append(dest)
    med=[];buildrows=[]
    for bid,parts in sorted(agree_by_building.items()):
        vv=np.concatenate(parts)
        if len(vv)>=100:med.append(float(np.median(vv)));buildrows.append(dict(building=bid,n=len(vv),median_m=float(np.median(vv))))
    med=np.array(med);sigmaW=float(1.4826*np.median(abs(med-np.median(med)))) if len(med) else None
    rr={k:(float(np.median(np.concatenate(v))) if sum(map(len,v)) else None) for k,v in groupdiff.items()}
    calibration=dict(at=now(),sigma_W_m=sigmaW,r_m=rr,buildings=buildrows,building_count=len(med),
        building_median_q10_q90_m=np.quantile(med,[.1,.9]).tolist() if len(med) else None,
        als_selected_radius_m=radius,als_radius_candidates=rows,
        truth_opened=False,config_sha256=sha(C/'judgecheck_v1.json'),scientific_verdict=None)
    dump(BASE/'geometry_calibration.json',calibration);dump(D/'tables/geometry_calibration_interim.json',calibration)
    for p in prepared:
        d=loadz(p);prior=p.stem.split('__')[1];reg=np.array([np.nan if rr[f'{prior}_{k}'] is None else rr[f'{prior}_{k}'] for k in d['kind']])
        d['r_m']=reg;d['sigma_W_m']=np.full(len(reg),np.nan if sigmaW is None else sigmaW)
        d['L_m']=1.96*(np.sqrt(d['u_mvs']**2+d['sigma_P_m']**2+d['sigma_W_m']**2)+abs(reg))
        d['geometry']=np.full(len(reg),9,np.int8);good=(d['n']>=4)&np.isfinite(d['d_m'])&np.isfinite(d['L_m'])
        d['geometry'][d['n']>=0]=2;d['geometry'][(d['n']>=4)&~good]=9
        d['geometry'][good&(abs(d['d_m'])<=d['L_m'])]=0;d['geometry'][good&(abs(d['d_m'])>d['L_m'])]=1
        savez(BASE/'geometry'/p.name,**d)
    print('CALIBRATION',json.dumps({k:v for k,v in calibration.items() if k not in ['buildings','als_radius_candidates']},ensure_ascii=False))

if __name__=='__main__':
    if sys.argv[1]=='phase1':phase1(sys.argv[2] if len(sys.argv)>2 else None)
    elif sys.argv[1]=='calibrate':calibrate()
