"""Reproduce supplied Track-A analysis units; retain source precision in exports."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
import numpy as np
from scipy.spatial import cKDTree
from column_store import Columns,unpack_npz

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'track_a'))
import common as tc
import planeseg as ps
from units_lib import union_mask

O=Path('/out'); D=Path('/docs'); C=Path('/config')
W=Path('/ph/main_widen0_v2/PHD-MAIN-WIDEN0-v2/patch_values')
CACHE=O/'cache/track_a'; CACHE.mkdir(parents=True,exist_ok=True); tc.W=str(CACHE)
TABLE=D/'tables'; TABLE.mkdir(parents=True,exist_ok=True)
SOURCE_FIELDS=['patch_id','centre','raw_centre','normal','area','building','roof_type','kind','roof_like','face_ext','cell','holdout','source_patch','surf','tau','gt_status','gt_p','mvs_a_status','mvs_p','u_mvs','u_prior','signed_difference_over_uncertainty','mvs_a_nx','mvs_a_ny','mvs_a_nz','mvs_a_e','mvs_a_s']
TYPE_NAMES=['MVS 없음','벽','흩어진 MVS','작게 솟은 면','작은 조각','평평한 지붕','기운 지붕']

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def dump(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=lambda o:o.tolist() if isinstance(o,np.ndarray) else o.item() if isinstance(o,np.generic) else str(o))+'\n');t.replace(p)

def log(prior,stage,**kw):
    x=dict(task_id='PHD-MAIN-MESHPATCH-v1',prior=prior,stage=stage,updated_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),scientific_verdict=None,**kw)
    dump(O/'status'/f'patch_{prior}.json',x);print(json.dumps(x,ensure_ascii=False),flush=True)

def locked():
    cfg=json.loads((C/'meshpatch_v1.json').read_text());lock=json.loads((C/'meshpatch_v1.lock.json').read_text())
    assert sha(C/'meshpatch_v1.json')==lock['sha256']
    return cfg

def prepare(prior,cfg):
    cached=CACHE/f'{prior}_source.npz'
    columns=CACHE/f'{prior}_source_columns'
    if (columns/'columns.json').exists():return Columns(columns)
    if cached.exists():return unpack_npz(cached,columns)
    fs=sorted(W.glob(f'*__{prior}__R1.5.npz')); manifest={x['path']:x['sha256'] for x in cfg['inputs']}
    inventory=[];n=0
    for k,f in enumerate(fs):
        assert sha(f)==manifest[str(f)],f
        with np.load(f) as z:
            count=len(z['cell']);n+=count
            assert not z['holdout'].any()
            inventory.append(dict(tile=f.name.split('__')[0],patches=count,area_m2=float(z['area'].sum()),sha256=manifest[str(f)]))
        log(prior,'reading',completed_files=k+1,total_files=len(fs))
    columns.mkdir(exist_ok=True)
    for key in SOURCE_FIELDS+['tile']:
        if key=='tile':shape=(n,);dtype=np.dtype('int16')
        else:
            with np.load(fs[0]) as z:shape=(n,)+z[key].shape[1:];dtype=z[key].dtype
        out=np.lib.format.open_memmap(columns/(key+'.npy'),mode='w+',shape=shape,dtype=dtype);start=0
        for k,f in enumerate(fs):
            count=inventory[k]['patches']
            with np.load(f) as z:out[start:start+count]=k if key=='tile' else z[key]
            start+=count
        out.flush();del out
    dump(columns/'columns.json',SOURCE_FIELDS+['tile']);dump(CACHE/f'{prior}_inventory.json',inventory)
    return Columns(columns)

def track_data(src):
    d={k:src[k] for k in ['centre','normal','roof_like','area','cell','gt_p','tau','mvs_a_status','mvs_p','u_mvs','u_prior','signed_difference_over_uncertainty','face_ext','surf','mvs_a_nx','mvs_a_ny','mvs_a_nz','mvs_a_e','mvs_a_s','holdout','tile']}
    d['bld']=np.unique(src['building'],return_inverse=True)[1].astype(np.int32)
    d['z']=d.pop('signed_difference_over_uncertainty')
    for k in list(d):
        if d[k].dtype==np.float64 and k!='centre':d[k]=d[k].astype(np.float32)
    d['mvs_n']=np.stack([d.pop('mvs_a_nx'),d.pop('mvs_a_ny'),d.pop('mvs_a_nz')],1).astype(np.float32)
    return d

def units(prior,d):
    n=len(d['cell']);C0=d['centre'].astype(np.float64);N=d['normal'].astype(np.float64)
    ep=CACHE/f'{prior}_edges.npy'
    if ep.exists():E=np.load(ep)
    else:
        log(prior,'graph',patches=n)
        E=cKDTree(C0).query_pairs(r=.36,output_type='ndarray').astype(np.int32);np.save(ep,E)
    hasm=(d['mvs_a_status']==0)&np.isfinite(d['z'])&np.isfinite(d['mvs_n'][:,0])
    P=C0+N*np.where(hasm,d['mvs_p'],0)[:,None]
    MN=np.where(hasm[:,None],d['mvs_n'],0).astype(np.float64);MN/=np.maximum(np.linalg.norm(MN,axis=1,keepdims=True),1e-12)
    cp=CACHE/f'{prior}_curv.npy'
    if cp.exists():curv=np.load(cp)
    else:
        curv=np.full(n,np.inf);ids=np.flatnonzero(hasm);tr=cKDTree(P[ids])
        for st in range(0,len(ids),200000):
            sl=ids[st:st+200000];dd,nb=tr.query(P[sl],k=16);nb=ids[nb]
            same=d['bld'][nb]==d['bld'][sl][:,None]
            X=P[nb]-P[sl][:,None,:];X=np.where(same[:,:,None],X,0)
            cnt=same.sum(1)[:,None,None];mu=X.sum(1,keepdims=True)/cnt
            Y=np.where(same[:,:,None],X-mu,0);Cv=np.einsum('nki,nkj->nij',Y,Y)/cnt
            ev=np.linalg.eigvalsh(Cv);curv[sl]=ev[:,0]/np.maximum(ev.sum(1),1e-12)
            log(prior,'curvature',completed_mvs_points=min(st+200000,len(ids)),mvs_points=len(ids))
        np.save(cp,curv)
    up=CACHE/f'{prior}_units.npz'
    if up.exists():return E,dict(np.load(up)),hasm
    i,j=E[:,0],E[:,1];sameb=d['bld'][i]==d['bld'][j]
    indptr,indices=ps.csr(n,E[sameb&hasm[i]&hasm[j]])
    cth=float(np.percentile(curv[hasm],90));order=np.argsort(np.where(hasm,curv,np.inf),kind='stable')
    log(prior,'roofer_region_growing',edges=len(E))
    lab=ps.rg_plane(n,indptr,indices,P,MN,curv,order,cth,.75,np.full(n,.3),15)
    out,left=ps.finish(lab,d,E,hasm)
    # Exact units_min.py mvsshape_10 definition, independent of Roofer labels.
    hm=(d['mvs_a_status']==0)&np.isfinite(d['z']);mn=d['mvs_n'].astype(np.float64)
    P=C0+N*np.where(hm,d['mvs_p'],0)[:,None];u=np.where(hm,d['u_mvs'],np.nan).astype(np.float64)
    okn=hm[i]&hm[j]&np.isfinite(mn[i,0])&np.isfinite(mn[j,0])
    ca=np.abs((mn[i]*mn[j]).sum(1));off=np.abs(((P[j]-P[i])*mn[i]).sum(1))
    dt=np.maximum(2*np.sqrt(u[i]**2+u[j]**2),.02);nomvs=(~hm[i])&(~hm[j])
    shape=union_mask(n,E,sameb&((okn&(ca>np.cos(np.radians(10)))&(off<dt))|nomvs))
    U=dict(roofer_def=out,mvsshape_10=shape,plane_raw=lab,leftover=left)
    np.savez_compressed(up,**U)
    return E,U,hasm

def types(d,E,labels):
    a=d['area'].astype(float);hm=(d['mvs_a_status']==0)&np.isfinite(d['z'])
    _,lab=np.unique(labels,return_inverse=True);K=lab.max()+1
    ea=np.bincount(lab,weights=a,minlength=K);nm=np.bincount(lab,weights=hm.astype(float),minlength=K)
    mn=d['mvs_n'].astype(float);mnu=np.where(hm[:,None]&np.isfinite(mn),mn,0);M=np.zeros((K,3,3))
    for p in range(3):
        for q in range(p,3):
            v=np.bincount(lab,weights=a*mnu[:,p]*mnu[:,q],minlength=K);M[:,p,q]=v;M[:,q,p]=v
    M[:,2,2]+=1e-12;en=np.linalg.eigh(M)[1][:,:,2];tilt=np.degrees(np.arccos(np.clip(np.abs(en[:,2]),0,1)))
    sc=d['mvs_a_s'].astype(float);ls=np.bincount(lab[hm],weights=np.log(np.maximum(sc[hm],1e-4))*a[hm],minlength=K)/np.maximum(np.bincount(lab[hm],weights=a[hm],minlength=K),1e-9)
    esc=np.exp(ls);thr=2*np.median(sc[hm]);i,j=E[:,0],E[:,1];sb=d['bld'][i]==d['bld'][j]
    pz=d['centre'][:,2].astype(float)+d['normal'][:,2].astype(float)*np.where(hm,d['mvs_p'],0)
    be=sb&(lab[i]!=lab[j])&hm[i]&hm[j];dz=(pz[i]-pz[j])[be];li=lab[i][be];lj=lab[j][be]
    up=np.bincount(li,weights=(dz>.3),minlength=K)+np.bincount(lj,weights=(-dz>.3),minlength=K)
    nb=np.bincount(li,minlength=K)+np.bincount(lj,minlength=K);frac=up/np.maximum(nb,1)
    et=np.full(K,6,np.int8);et[tilt<10]=5;et[ea<1]=4;et[(ea<10)&(frac>.6)&(tilt<60)&(nb>=4)]=3
    et[esc>thr]=2;et[tilt>=60]=1;et[nm==0]=0
    bd=sb&(lab[i]!=lab[j]);b0=np.zeros(len(a),bool);b0[i[bd]]=True;b0[j[bd]]=True
    s1=sb&(lab[i]==lab[j])&(b0[i]!=b0[j]);edge=b0.copy();edge[i[s1]]=True;edge[j[s1]]=True
    return dict(pt=et[lab],edge=edge,et=et,lab=lab,tilt=tilt,escat=esc,frac_up=frac,earea=ea,scatter_threshold=float(thr))

def check(prior,d,E,U):
    ref=json.loads((O/'received/track_a_v3/results'/f'{prior}_evalseg.json').read_text())
    cases=json.loads((O/'received/track_a_v3/results/cases.json').read_text())[prior]
    T=tc.truth_comp(d,E);a=d['area'].astype(float);roof=d['roof_like'];results={};allok=True
    for key in ['roofer_def','mvsshape_10']:
        log(prior,'benchmark',method=key)
        _,lab=np.unique(U[key],return_inverse=True);K=lab.max()+1;s,_=tc.score(lab,d,T,cases)
        ra=np.bincount(lab,weights=a*roof,minlength=K);ta=np.bincount(lab,weights=a,minlength=K)
        vals=dict(faces_per100=s['per100'],mix_face=s['mix'],split_face=s['split'],roofwall_join=float(a[(np.minimum(ra,ta-ra)/ta)[lab]>.2].sum()/a.sum()),area_in_faces_ge1m2=float(a[ta[lab]>=1].sum()/a.sum()),cases=s['cases'])
        expected_count=round(ref[key]['faces_per100']*a.sum()/100)
        ratios={k:100*(v-ref[key][k]) for k,v in vals.items() if k not in ['cases','faces_per100']}
        density_error=abs(vals['faces_per100']-ref[key]['faces_per100'])
        ok=K==expected_count and density_error<1e-8 and all(abs(v)<=.5 for v in ratios.values()) and vals['cases']=={k:tuple(v) for k,v in ref[key]['cases'].items()}
        results[key]=dict(status='PASS' if ok else 'FAIL',groups=int(K),expected_groups=expected_count,observed=vals,expected=ref[key],difference_pp=ratios,density_difference=density_error,area_quantiles_m2=np.quantile(ta,[0,.25,.5,.75,.9,.95,.99,1]).tolist(),area_distribution_reference='Only area_in_faces_ge1m2 is supplied; full quantile equality cannot be checked.')
        allok &= ok
    result=dict(prior=prior,status='PASS' if allok else 'STOP',rows=len(a),area_tracka_float32_m2=float(a.sum()),checks=results,scientific_verdict=None,provenance='[이 발주에서 냄]')
    dump(TABLE/f'patch_{prior}_tracka_check.json',result)
    lines=[f'# {prior} 면 번호 대조','', '[이 발주에서 냄]', '', '| 분할 | 면 수 | 기준 면 수 | 1 m² 이상 넓이 비율 | 기준 | 상태 |','|---|---:|---:|---:|---:|---|']
    for k,r in results.items():lines.append(f"| {k} | {r['groups']} | {r['expected_groups']} | {r['observed']['area_in_faces_ge1m2']:.10f} | {r['expected']['area_in_faces_ge1m2']:.10f} | {r['status']} |")
    lines+=['','전체 면 수에는 MVS 없는 연결 성분이 포함된다. 납품 MVS 면 번호는 그 패치에서 비운다. 원래 분석 단위 번호를 별도 열로 보존한다.','기준 JSON에는 전체 넓이 분위수 분포가 없다. 1 m² 이상 넓이 비율을 대조했다.']
    (TABLE/f'patch_{prior}_tracka_check.md').write_text('\n'.join(lines)+'\n')
    return bool(allok)

def main():
    p=argparse.ArgumentParser();p.add_argument('prior',choices=['ALS','LoD2']);args=p.parse_args();t=time.monotonic()
    cfg=locked();src=prepare(args.prior,cfg);d=track_data(src);E,U,hm=units(args.prior,d)
    ok=check(args.prior,d,E,U)
    for key in ['roofer_def','mvsshape_10']:
        log(args.prior,'element_types',method=key);r=types(d,E,U[key]);np.savez_compressed(CACHE/f'{args.prior}_{key}_types.npz',**r)
    log(args.prior,'units_complete' if ok else 'benchmark_stop',patches=len(src['cell']),area_m2=float(src['area'].sum()),seconds=time.monotonic()-t,benchmark_passed=ok)
    if not ok:raise SystemExit(2)

if __name__=='__main__':main()
