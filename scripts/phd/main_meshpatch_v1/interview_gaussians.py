"""No-surface patch columns at iteration 30000 and saved visibility pairs."""
import argparse
from scipy.spatial import cKDTree
from interview_common import *

def saved_visibility(site,prior,e,ids):
    root=S0/'s61/box'/site/prior;up=root/'units.npz';pp=root/'unit_view_pairs.npz'
    quality=FD/'renders'/site/'nojudge_ALS_s0/iteration_30000/quality.json'
    if not pp.exists() or not quality.exists():return None,None,dict(status='UNAVAILABLE',reason='기존 패치·학습 사진 가시성 쌍 또는 카메라 기록 없음')
    with np.load(up) as f:
        assert np.array_equal(f['loc_center'],e['centre']), 'stored visibility patch centres differ'
        original=f['n_seeing']
    with np.load(pp) as f:loc=f['loc'];view=f['view'];names=f['views'];npix=f['npix']
    assert (npix>0).all()
    assert np.array_equal(np.bincount(loc,minlength=len(e['area'])),original)
    cams={c['view']:np.array(c['camera_center']) for c in json.loads(quality.read_text())['train']}
    normalize=lambda n:Path(str(n)).stem
    assert all(normalize(n) in cams for n in names),'saved visibility includes an unverified training camera'
    cc=np.array([cams[normalize(n)] for n in names]);selected=np.zeros(len(e['area']),bool);selected[ids]=True
    use=selected[loc];ll=loc[use];vv=view[use];delta=cc[vv]-e['centre'][ll]
    delta/=np.linalg.norm(delta,axis=1)[:,None]
    angles=np.degrees(np.arcsin(np.clip(np.abs(np.sum(delta*e['normal'][ll],axis=1)),0,1)))
    order=np.argsort(ll,kind='stable');ll=ll[order];angles=angles[order];out=np.full(len(e['area']),np.nan)
    boundaries=np.r_[0,np.flatnonzero(np.diff(ll))+1,len(ll)]
    for a,b in zip(boundaries[:-1],boundaries[1:]):
        if b>a:out[ll[a]]=np.median(angles[a:b])
    return original[ids],out[ids],dict(status='PASS',pairs=source(pp),units=source(up),cameras=source(quality),
        definition='Original stage-1 visible prior-surface pixel pairs, unique patch/view; no new visibility. Angle between centre-to-camera sightline and patch plane: grazing=0, normal=90 degrees.',
        limitation='Visibility is the frozen pretraining prior-surface visibility, not a new visibility computation on the learned Gaussian model.')

def column_counts(xyz,opacity,origin,centres,normals,t1,t2,tau):
    tree=cKDTree(xyz);counts=np.zeros(len(centres),np.int64);prior=np.zeros(len(centres),np.int64)
    med=np.full(len(centres),np.nan);opaque=np.zeros(len(centres),bool)
    radius=np.sqrt(tau**2+2*.125**2)+1e-8
    for i,c in enumerate(centres):
        ix=np.asarray(tree.query_ball_point(c,radius[i]),np.int64)
        if not len(ix):continue
        delta=xyz[ix]-c
        yes=(np.abs(delta@t1[i])<=.125+1e-8)&(np.abs(delta@t2[i])<=.125+1e-8)&(np.abs(delta@normals[i])<=tau[i]+1e-8)
        ix=ix[yes];counts[i]=len(ix)
        if len(ix):prior[i]=int((origin[ix]==1).sum());med[i]=np.median(opacity[ix]);opaque[i]=bool((opacity[ix]>=.5).any())
    return counts,prior,med,opaque

def main():
    ap=argparse.ArgumentParser();ap.add_argument('site');ap.add_argument('prefix',choices=['nojudge','lt_dynnow']);a=ap.parse_args();config()
    site=a.site;prior='LoD2';result=f'{a.prefix}_{prior}_s0';job=f'gaussians-{SHORT[site].lower()}-{a.prefix}'
    e,v,base=evaluation(site,prior);z,zp=patch_values(site,prior,result,e)
    mask=eligible(e)&np.isin(e['cell'],[2,4])&z['no_surface'];ids=np.flatnonzero(mask)
    mp=model(site,prior,a.prefix);gp=mp/'dump/iteration_30000/gaussians.npz'
    if not gp.exists():record(job,status='UNAVAILABLE',reason='30000회 가우시안 배열 없음');return
    with np.load(gp) as f:
        assert int(f['iteration'])==30000;xyz=f['xyz'].astype(float);op=f['opacity'].astype(float);org=f['origin']
    assert np.isfinite(xyz).all() and np.isfinite(op).all() and ((op>=0)&(op<=1)).all()
    up=S0/'s61/box'/site/prior/'units.npz'
    with np.load(up) as f:
        assert np.array_equal(f['loc_center'],e['centre'])
        t1=f['loc_t1'][ids].astype(float);t2=f['loc_t2'][ids].astype(float)
    t1/=np.linalg.norm(t1,axis=1)[:,None];t2/=np.linalg.norm(t2,axis=1)[:,None]
    assert np.all(np.abs(np.sum(t1*t2,axis=1))<1e-6)
    assert np.all(np.abs(np.sum(np.cross(t1,t2)*e['normal'][ids],axis=1))>1-1e-6)
    count,nprior,median,opaque=column_counts(xyz,op,org,e['centre'][ids],e['normal'][ids],t1,t2,e['tau'][ids])
    views,angle,vr=saved_visibility(site,prior,e,ids);rows=[]
    for j,idx in enumerate(ids):
        rows.append(dict(site=site,prior=prior,result=result,patch=int(idx),cell=int(e['cell'][idx]),area_m2=float(e['area'][idx]),
            gaussians=int(count[j]),opacity_median=float(median[j]) if np.isfinite(median[j]) else None,prior_origin_gaussians=int(nprior[j]),
            opaque_present=bool(opaque[j]),category='진한 가우시안 있음' if opaque[j] else '흐린 가우시안만' if count[j] else '가우시안 없음',
            visible_train_photos=int(views[j]) if views is not None else None,
            view_surface_angle_median_deg=float(angle[j]) if angle is not None and np.isfinite(angle[j]) else None))
    groups=[]
    category=np.where(opaque,0,np.where(count>0,1,2))
    for cell in [2,4]:
        subset=e['cell'][ids]==cell;den=float(e['area'][ids[subset]].sum())
        for k,label in enumerate(['진한 가우시안 있음','흐린 가우시안만','가우시안 없음']):
            m=subset&(category==k);area=float(e['area'][ids[m]].sum())
            groups.append(dict(site=site,prior=prior,result=result,cell=cell,category=label,patches=int(m.sum()),area_m2=area,
                no_surface_area_m2=den,pct=100*area/den if den else None))
        assert not den or np.isclose(sum(r['pct'] for r in groups if r['cell']==cell),100)
    write_table(job+'_patches',rows,['0.25 m 정사각형은 원본 loc_t1/loc_t2 방향. 법선으로 사전 면 ±τ. 진함=중앙값이 아니라 한 개 이상 opacity>=0.5.'])
    write_table(job,groups,[vr['definition'] if vr['status']=='PASS' else vr['reason']])
    dump(IDOC/'checks'/(job+'.json'),dict(status='PASS',sources=[source(gp),source(up),source(zp),source(base/'evaluation.npz')],visibility=vr,scientific_verdict=None))
    record(job,status='PASS' if vr['status']=='PASS' else 'PARTIAL',patches=len(ids),visibility_status=vr['status'])

if __name__=='__main__':main()
