"""Join wall view counts and report fixed-condition ranking, including unknowns."""
from common import *
from visibility import wall_data
from measure import component
from scipy.spatial import cKDTree

def outside_reference(d,ids):
    # Reuse WIDEN's saved normal-line face offsets and inner-cylinder support.
    # Union raw point identities across overlapping patches; no new case labels.
    points=[];distance=[];sources=[]
    for tile in np.unique(d['tile'][ids]):
        ii=ids[d['tile'][ids]==tile];bids=set(d['building'][ii]);look={}
        for base in [W/'patch_values',W/'holdout/patch_values']:
            p=base/f'{tile}__LoD2__R1.5.npz';a=loadz(p,['patch_id','gt_o']);look.update(zip(a['patch_id'],a['gt_o']))
        offs=np.array([look[x] for x in d['patch_id'][ii]]);valid=np.isfinite(offs);ii=ii[valid];offs=offs[valid]
        if not len(ii):continue
        p=W/'holdout/internal/points'/tile/'gt_xyz.npy';X=np.load(p,mmap_mode='r');cent=d['xyz'][ii];N=d['normal'][ii];c=cent+offs[:,None]*N
        low=c.min(0)-1.2;high=c.max(0)+1.2;keep=np.all((X>=low)&(X<=high),axis=1);P=np.asarray(X[keep]);tree=cKDTree(P);seen={}
        for start in range(0,len(c),1000):
            groups=tree.query_ball_point(c[start:start+1000],np.hypot(.5,1.)+1e-8,workers=4)
            for j,g in enumerate(groups,start):
                q=np.asarray(g,int)
                if not len(q):continue
                delta=P[q]-cent[j];t=delta@N[j];rho2=np.sum(delta*delta,axis=1)-t*t;ok=(rho2<=.25+1e-9)&(abs(t-offs[j])<=1+1e-9)
                for index,dd in zip(q[ok],t[ok]):seen.setdefault(int(index),float(abs(dd)))
        if seen:
            ix=np.array(list(seen));points.append(P[ix]);distance.append(np.array(list(seen.values())))
        sources.append(dict(path=str(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns))
    if not points:return 0,None,sources
    P=np.concatenate(points);dd=np.concatenate(distance);_,ix=np.unique(P,axis=0,return_index=True);dd=dd[ix]
    return len(ix),float(np.mean(dd<=.2)),sources

def enrich(stem):
    out=O/'metrics_final'/f'{stem}.json'
    if out.exists():return json.loads(out.read_text())['rows']
    rows=json.loads((O/'metrics'/f'{stem}.json').read_text())['rows'];site,prior=stem.split('__')
    if prior=='ALS':return rows
    d=loadz(O/'data'/f'{stem}.npz');z=loadz(O/'zones'/f'{stem}.npz');w=wall_data(stem);vis=loadz(O/'visibility'/f'{stem}.npz');counts=vis['count'];c4mask=np.zeros(len(w['kind']),bool);c1mask=np.zeros(len(d['kind']),bool);records=[]
    for r in rows:
        bid=r['building'];wall=(w['building']==bid)&(w['kind']==2);measured=wall&(counts>=0)
        if not measured.any():
            if not wall.any():r.update(c1_wall_m2=0.,c4_m2=0.,visibility_measured=True,c4_reference_n=0,c4_prior_tau_fraction=None,c4_reference_note='참값 부족')
            continue
        assert measured.sum()==wall.sum()
        rc=counts if site=='outside' else counts[np.maximum(d['owner'],0)]
        good=np.ones(len(rc),bool) if site=='outside' else d['owner']>=0
        m=(d['building']==bid)&(d['kind']==2)&(d['case']==0)&good&(rc>=2);c1mask|=m
        r.update(c1_wall_m2=float(d['area'][m].sum()),visibility_measured=True)
        face=w['surf'].astype(str) if site!='outside' else z['face']
        best=0.;chosen=np.zeros(0,int);win=None
        for f in np.unique(face[wall]):
            ix=np.flatnonzero(wall&(face==f)&(counts==0));a,sel=component(w['centre'][ix],w['area'][ix],.6 if site!='outside' else .36)
            if a>best:best=a;chosen=ix[sel];win=str(f)
        r['c4_m2']=best;r['c4_face']=win;c4mask[chosen]=True
        if win is None:n=0;fraction=None
        elif site!='outside':
            mask=(d['building']==bid)&(d['kind']==2)&(d['surf']==int(win));n=int(mask.sum());fraction=float(np.mean(np.isfinite(d['prior_s'][mask])&(abs(d['prior_s'][mask])<=d['tau'][mask]))) if n else None
        else:
            ids=np.flatnonzero((d['building']==bid)&(d['kind']==2)&(z['face']==win));n,fraction,ss=outside_reference(d,ids);records.extend(ss)
        r.update(c4_reference_n=n,c4_prior_tau_fraction=fraction,c4_reference_note='참값 부족' if n<100 else '')
        print('WALL_METRIC',bid,round(r['c1_wall_m2'],2),round(best,2),n,flush=True)
    savez(O/'wall_highlights'/f'{stem}.npz',c1=c1mask,c4=c4mask)
    dump(out,dict(rows=rows,reference_sources=records,scientific_verdict=None));return rows

def flags(r,relaxed=()):
    a=lambda k:2 if k in relaxed else 4
    roof=r['c1_roof_m2']>=a('c1')
    c1=roof if r['prior']=='ALS' else False if not roof else None if r['c1_wall_m2'] is None else r['c1_wall_m2']>=a('c1')
    return dict(c1=c1,c2=r['c2_m2']>=a('c2'),c3a=r['c3a_m2']>=a('c3a'),c3b=r['c3b_m']>=(1.5 if 'c3b' in relaxed else 3),c4=None if r['prior']=='ALS' or r['c4_m2'] is None else r['c4_m2']>=a('c4'))

def main():
    cfg();rows=[]
    for p in sorted((O/'metrics').glob('*.json')):rows.extend(enrich(p.stem))
    lod=[r for r in rows if r['prior']=='LoD2'];als={(r['building'],r['site']):r for r in rows if r['prior']=='ALS'}
    relaxed=[]
    for key in ['c1','c2','c3a','c3b','c4']:
        values=[flags(r)[key] for r in lod]
        if not any(v is True for v in values) and not any(v is None for v in values):relaxed.append(key)
    # The initial strict pass has a success for each condition in this task;
    # fail visibly if a new input revision requires the one-pass relaxed views.
    if 'c4' in relaxed:raise RuntimeError('c4 needs a separately cached <=1-view component pass')
    for r in lod:
        f=flags(r,relaxed);r['conditions']=f;r['count']=sum(x is True for x in f.values());r['unknown_conditions']=[k for k,v in f.items() if v is None];r['count_upper']=r['count']+len(r['unknown_conditions'])
        aa=als.get((r['building'],r['site']));r['als_count']=sum(v is True for k,v in flags(aa,relaxed).items() if k!='c4') if aa else None
        areas={'c1':min(r['c1_roof_m2'],r['c1_wall_m2']) if r['c1_wall_m2'] is not None else 0,'c2':r['c2_m2'],'c3a':r['c3a_m2'],'c3b':r['c3b_m'],'c4':r['c4_m2'] or 0}
        r['minimum_satisfied_area_m2']=min((areas[k] for k,v in f.items() if v),default=0)
    groups={'실험 지역 안':0,'개발용':1,'확인용':2}
    lod.sort(key=lambda r:(-r['count'],groups[r['group']],-r['minimum_satisfied_area_m2'],r['building']))
    top=[r for r in lod if r['top5_eligible']][:5]
    summary=dict(at=now(),buildings=len(lod),all_five=sum(r['count']==5 for r in lod),all_five_experiment=sum(r['count']==5 and r['experiment'] for r in lod),relaxed=relaxed,top5=top,
        top5_unmeasured_competitors=[r['building'] for r in lod if r['unknown_conditions'] and r['top5_eligible'] and r['count_upper']>=top[-1]['count']],scientific_verdict=None)
    summary.update(spatial_scope='saved roof and wall cases only; ground cases unavailable',all_five_full_spatial_scope=None)
    dump(O/'ranking.json',dict(rows=lod,**summary))
    public=[]
    for rank,r in enumerate(lod,1):
        public.append(dict(rank=rank,building=r['building'],group=r['group'],scene=r['scene'],top5_eligible=r['top5_eligible'],case_source=r['case_source'],
            **{k:('확인 불가' if v is None else '채움' if v else '미충족') for k,v in r['conditions'].items()},c1_roof_m2=r['c1_roof_m2'],c1_wall_m2=r['c1_wall_m2'],c2_m2=r['c2_m2'],c3a_m2=r['c3a_m2'],c3b_m=r['c3b_m'],c4_m2=r['c4_m2'],count_LoD2=r['count'],count_ALS=r['als_count'],footprint_m2=r['footprint_m2'],long_m=r['long_m'],short_m=r['short_m']))
        if r['group']=='확인용' and r['building'] not in {t['building'] for t in top}:
            for field in ['scene','top5_eligible','case_source','long_m','short_m']:public[-1][field]=None
    table('전체_순위',public);table('상위_다섯',[r for r in public if r['building'] in {t['building'] for t in top}])
    counts=[]
    for group in groups:
        subset=[r for r in lod if r['group']==group]
        for k in ['c1','c2','c3a','c3b','c4']:
            counts.append(dict(group=group,condition=k,buildings=len(subset),satisfied=sum(r['conditions'][k] is True for r in subset),not_satisfied=sum(r['conditions'][k] is False for r in subset),not_measured=sum(r['conditions'][k] is None for r in subset),relaxed=k in relaxed,scope='저장 벽 경우만; 바닥 없음' if k=='c3b' else '저장 경우'))
    table('조건별_건물_수',counts);dump(D/'summary.json',summary)
    print(json.dumps(dict(all_five=summary['all_five'],all_five_experiment=summary['all_five_experiment'],relaxed=relaxed,top=[(r['building'],r['count'],r['conditions']) for r in top],unknown_competitors=summary['top5_unmeasured_competitors']),ensure_ascii=False))
if __name__=='__main__':main()
