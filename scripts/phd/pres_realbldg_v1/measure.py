"""Building conditions from stored cases. No new case classification."""
from common import *
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from zones import eaves

def component(P,area,radius):
    if not len(P):return 0.,np.zeros(0,bool)
    Q,inv=np.unique(P,axis=0,return_inverse=True);weights=np.bincount(inv,weights=area)
    pairs=cKDTree(Q).query_pairs(radius,output_type='ndarray')
    graph=coo_matrix((np.ones(len(pairs),'u1'),(pairs[:,0],pairs[:,1])),shape=(len(Q),len(Q))).tocsr()
    _,labels=connected_components(graph,directed=False);totals=np.bincount(labels,weights=weights);k=int(np.argmax(totals))
    return float(totals[k]),labels[inv]==k

def longest(passmask,lengths):
    if not passmask.any():return 0.,[]
    if passmask.all():return float(lengths.sum()),list(range(len(lengths)))
    start=int(np.flatnonzero(~passmask)[0]);best=0.;current=0.;indices=[];chosen=[]
    for k in (start+np.arange(1,len(passmask)+1))%len(passmask):
        if passmask[k]:current+=lengths[k];indices.append(int(k))
        else:current=0.;indices=[]
        if current>best:best=current;chosen=indices.copy()
    return best,chosen

def edge_measure(d,z,b,ids,unit):
    best=0.;selection=np.zeros(len(ids),bool);records=[]
    for ri,ring in enumerate(b['rings']):
        length=float(np.linalg.norm(np.diff(np.asarray(ring),axis=0),axis=1).sum());n=int(np.ceil(length/.5));lengths=np.minimum(.5,length-np.arange(n)*.5)
        ss=z['along'][ids];seg=np.clip(np.floor(np.nan_to_num(ss)/.5).astype(int),0,n-1);same=z['ring'][ids]==ri;cc=d['case'][ids]
        outer=same&z['outer'][ids];inner=same&z['inner'][ids]
        # Reference rows retain their saved multiplicity; no new resampling.
        no=np.bincount(seg[outer],minlength=n);ni=np.bincount(seg[inner],minlength=n)
        prior=np.bincount(seg[outer&(cc==2)],minlength=n);bo=np.bincount(seg[outer&(cc==3)],minlength=n);bi=np.bincount(seg[inner&(cc==3)],minlength=n)
        ok=(no>=(5 if unit=='reference' else 2))&(2*prior>=no)&(5*bo<no)&((ni==0)|(5*bi<ni))
        val,chosen=longest(ok,lengths)
        records.append(dict(ring=ri,length_m=length,outside_count=no.tolist(),inside_count=ni.tolist(),prior_only_count=prior.tolist(),both_wrong_outer=bo.tolist(),both_wrong_inner=bi.tolist(),passes=ok.tolist(),longest_m=val,chosen=chosen))
        if val>best:best=val;selection=same&np.isin(seg,chosen)&(outer|inner)
    return best,selection,records

def main(stem):
    cfg();out=O/'metrics'/f'{stem}.json'
    if out.exists():return
    d=loadz(O/'data'/f'{stem}.npz');z=loadz(O/'zones'/f'{stem}.npz');tx=loadz(O/'texture'/f'{stem}.npz');d['texture']=tx['texture'];meta=json.loads((O/'data'/f'{stem}.json').read_text());blds=json.loads((O/'buildings.json').read_text());rows=[]
    unit=meta['unit'];rad=.6 if unit=='reference' else .36;site=meta['site'];prior=meta['prior'];highlight=np.zeros((len(d['case']),4),bool)
    for bid in sorted(set(d['building'])&set(blds)):
        b=blds[bid]
        if site=='outside' and b['experiment']:continue
        ids=np.flatnonzero(d['building']==bid);cc=d['case'][ids];P=d['xyz'][ids];a=d['area'][ids];kind=d['kind'][ids]
        c1=(cc==0)&z['interior'][ids]&(d['texture'][ids]==0);a1=float(a[c1].sum());highlight[ids,0]=c1
        c2=(cc==1)&np.isin(kind,[1,2]);ii=np.flatnonzero(c2);a2,take=component(P[ii],a[ii],rad);chosen2=ii[take];highlight[ids[chosen2],1]=True
        c3=(cc==2)&z['interior'][ids]&(d['texture'][ids]==1);ii=np.flatnonzero(c3);a3,take=component(P[ii],a[ii],rad);highlight[ids[ii[take]],2]=True
        length,selected,edge=edge_measure(d,z,b,ids,unit);highlight[ids,3]=selected
        delta=None;type2='확인 불가'
        if len(chosen2):
            if unit=='patch':v=d['gt_p'][ids[chosen2]]*d['normal'][ids[chosen2],2]
            else:
                normal=loadz(G/'scenes'/stem/'rows.npz',['normal'])['normal'];v=-d['prior_s'][ids[chosen2]]*normal[ids[chosen2],2]
            v=v[np.isfinite(v)];delta=float(np.median(v)) if len(v) else None
            if delta is not None:
                if a2>=20 and abs(delta)>1:type2='높이가 바뀐 동'
                elif a2<20 and delta>0:type2='지붕 위 구조물'
                else:type2='두 기준에 해당 없음'
        coverage=b['coverage'].get(site,0.);group='실험 지역 안' if site!='outside' else '확인용' if b['split']=='holdout' else '개발용'
        r=dict(building=bid,scene=stem,site=site,prior=prior,group=group,experiment=site!='outside',coverage=coverage,top5_eligible=site=='outside' or coverage>=.8,
            case_source=meta['case_source'],footprint_m2=b['footprint_m2'],long_m=b['long_m'],short_m=b['short_m'],c1_roof_m2=a1,c2_m2=a2,c3a_m2=a3,c3b_m=length,
            c2_type=type2,c2_reference_minus_prior_z_m=delta,texture_unavailable_m2=float(a[z['interior'][ids]&np.isin(cc,[0,2])&(d['texture'][ids]<0)].sum()),c1_wall_m2=None,c4_m2=None,visibility_measured=False,
            case_areas={str(k):float(a[cc==k].sum()) for k in [-1,0,1,2,3,4]})
        rows.append(r);dump(O/'edges'/stem/f'{bid}.json',edge)
        print('MEASURED',stem,bid,round(a1,2),round(a2,2),round(a3,2),round(length,2),flush=True)
    savez(O/'highlights'/f'{stem}.npz',mask=highlight)
    dump(out,dict(rows=rows,scientific_verdict=None))
if __name__=='__main__':main(sys.argv[1])
