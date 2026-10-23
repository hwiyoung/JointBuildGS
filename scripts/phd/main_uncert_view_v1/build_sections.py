"""Replay original CPU code and seeds; downsample only the displayed cross-sections."""
import gc
import multiprocessing as mp
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *
from build_data import js, encode
import u2_run as R
import u_core as C

CONF=None

def axes(n):
    h=np.cross([0.,0.,1.],n)
    if np.linalg.norm(h)<1e-8: h=np.array([1.,0.,0.])
    h=h/np.linalg.norm(h)
    return h,np.cross(n,h)

def display(indices,i,cap,seed_tag,membership=None):
    ids=np.asarray(indices,dtype=np.int64)
    c,n=R.G['c'][i],R.G['n'][i];h,t=axes(n)
    q=R.G['X'][ids]-c
    keep=np.abs(q@t)<=CONF['samples']['display']['strip_width_m']/2
    ids=ids[keep];q=q[keep]
    if membership is not None: membership=np.asarray(membership)[keep]
    if len(ids)>cap:
        rng=np.random.default_rng([CONF['seed'],U.SITE_ID[R.G['site']],U.SET_ID[R.G['pset']],U.DATA_ID[R.G['data']],int(i),seed_tag])
        sel=np.sort(rng.choice(len(ids),cap,replace=False));ids=ids[sel];q=q[sel]
        if membership is not None:membership=membership[sel]
    return dict(x=(q@h).tolist(),y=(q@n).tolist(),source_indices=ids.tolist(),rings=None if membership is None else membership.tolist())

def one(i):
    data=R.G['data'];rows=R.one_patch(int(i))
    idx,t,rho,H=R.column(i);o,_,_=C.find_face(t,H,U.D)
    section=dict(rows=rows,horizontal_axis=axes(R.G['n'][i])[0].tolist(),strip_width_m=.5)
    if o is None:return int(i),section
    inn=idx[np.abs(t-o)<=U.D['slab_half_m']]
    if data=='gt':
        section['points']=display(inn,i,CONF['samples']['display']['gt'],9)
        return int(i),section
    if data.startswith('mvs') and len(inn)>U.D['mvs_cap_inner']:
        inn=np.sort(inn)[:U.D['mvs_cap_inner']]
    allids={}
    for bit,r in enumerate(CONF['radii']):
        ri,_,_,_=R.ring_points(i,o,r,int((np.abs(t-o)<=U.D['slab_half_m']).sum()))
        for j in ri:allids[int(j)]=allids.get(int(j),0)|(1<<bit)
    if data=='als':
        for j in inn:allids[int(j)]=allids.get(int(j),0)|8
        ii=sorted(allids)
        section['points']=display(ii,i,CONF['samples']['display']['als'],8,[allids[j] for j in ii])
    else:
        section['inner']=display(inn,i,CONF['samples']['display']['inner'],7)
        ii=sorted(allids)
        section['ring']=display(ii,i,CONF['samples']['display']['ring'],8,[allids[j] for j in ii])
    return int(i),section

def main():
    global CONF
    CONF=load(CFG/'view_v1.json');index=load(OUT/'sample_index.json')
    allchecks=[];exceptions=[];missing=[]
    for site,prior in U.CASES:
        ident=site+'__'+prior;ids=index[ident]['indices'];sections={str(i):{} for i in ids}
        originals={r:pv(site,prior,r) for r in CONF['radii']}
        for data in ['gt']+list(L.DATAS[prior]):
            try:
                R.G.clear();gc.collect();R.build(site,prior,data,CONF['radii'])
            except FileNotFoundError as e:
                missing.append(dict(case=ident,data=data,reason=str(e)));continue
            with mp.get_context('fork').Pool(8) as pool:
                results=pool.map(one,ids,chunksize=3)
            metrics={r:dict(case=ident,data=data,R=r,selected=len(ids),matched=0,status_mismatch=0,max_difference_m={f:0. for f in ['u','a','s','q','p']},over_tolerance=[]) for r in CONF['radii']}
            for i,sec in results:
                sections[str(i)][data]=sec
                if data=='gt':continue
                for r,row in sec['rows'].items():
                    m=metrics[r];z=originals[r];same=row['status']==int(z[data+'_status'][i]);good=same
                    if not same:m['status_mismatch']+=1
                    diffs={}
                    for f in ['u','a','s','q','p']:
                        old=float(z[data+'_'+f][i]);new=float(row.get(f,np.nan))
                        if np.isfinite(old) and np.isfinite(new):
                            diff=abs(old-new);m['max_difference_m'][f]=max(m['max_difference_m'][f],diff)
                            if diff>.001:good=False;diffs[f]=dict(original=old,replay=new,difference_m=diff)
                        elif np.isfinite(old)!=np.isfinite(new):good=False;diffs[f]=dict(original=old,replay=new)
                    if good:m['matched']+=1
                    else:
                        m['over_tolerance'].append(i);exceptions.append(dict(case=ident,data=data,R=r,patch=i,status_same=same,values=diffs))
            if data!='gt':allchecks+=list(metrics.values())
            print(ident,data,len(ids),'sections',flush=True)
        for patch in sections.values():
            for sec in patch.values():
                sec['rows']={r:{k:v for k,v in row.items() if k in ('status','o','nx','ny','nz','h')} for r,row in sec['rows'].items()}
                for field in ('inner','ring','points'):
                    if field not in sec:continue
                    for k,v in sec[field].items():
                        if v is not None:sec[field][k]=encode(np.asarray(v,dtype=np.float64 if k in ('x','y') else np.int32))
        js(OUT/'web/sections'/f'{ident}.js','UNCERT_SECTIONS',dict(id=ident,patches=sections,scientific_verdict=None))
        del originals;R.G.clear();gc.collect()
    dump(DOC/'tables/section_replay.json',dict(made=now(),rows=allchecks,exceptions=exceptions,missing_points=missing,
        method='original u2_run.one_patch, column, ring_points, original seeds/caps, before display thinning',scientific_verdict=None))
    progress(f'일 3 완료: 단면 재현 {sum(x["selected"] for x in allchecks)}건 중 {sum(x["matched"] for x in allchecks)}건 허용차 안. 0.1 cm 초과·상태 차이 {len(exceptions)}건; 점 파일 없음 {len(missing)}건.')

if __name__=='__main__':main()
