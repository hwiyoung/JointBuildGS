"""GT-free target sets 1/2 and a frozen 200-point timing sample."""
import json
import numpy as np
from preflight import C,D,O,Path,dump,sha,now
from geometry import loadz,savez
BASE=O/'r1'

def main():
    cfg=json.loads((C/'judgecheck_v1.json').read_text());rng=np.random.default_rng(20261102);records=[];allrows=[]
    for p in sorted((BASE/'photo_inputs').glob('*.npz')):
        tile,prior,kind=p.stem.split('__');g=loadz(p);d=loadz(BASE/'geometry'/f'{tile}__{prior}.npz')
        idx={pid:i for i,pid in enumerate(g['point_id'])};sel=np.flatnonzero(d['kind']==int(kind));owners=np.array([idx[pid] for pid in d['photo_point_id'][sel]])
        order=np.argsort(owners,kind='stable');groups=np.split(sel[order],np.flatnonzero(np.diff(owners[order]))+1)
        N=len(g['point_id']);b=np.full(N,np.nan);delta=np.full(N,np.nan);height=np.full(N,np.nan);target=np.zeros(N,np.uint8);area=np.zeros(N)
        for group in groups:
            i=idx[d['photo_point_id'][group[0]]];area[i]=d['area'][group].sum();ll=d['L_m'][group]
            if np.isfinite(ll).any():b[i]=np.median(ll[np.isfinite(ll)])
            vv=d['d_m'][group];height[i]=np.nanmedian(d['prior_height_m'][group]) if np.isfinite(d['prior_height_m'][group]).any() else np.nan
            if np.isfinite(vv).any():delta[i]=np.median(vv[np.isfinite(vv)])
            if (d['geometry'][group]==1).any():target[i]=1
            elif (d['geometry'][group]==0).all():target[i]=2
        g.update(b_m=b,core_d_median_m=delta,core_prior_height_median_m=height,target_type=target,eligible_area_m2=area)
        savez(BASE/'photo_target_base'/p.name,**g)
        for i in range(N):allrows.append((p.name,i,prior,int(kind),int(target[i])))
    # Sample 5,000 separately per prior and roof/wall stratum, as specified.
    chosen=set()
    for prior,kind in [('ALS',1),('LoD2',1),('LoD2',2)]:
        eligible=[(f,i) for f,i,p,k,t in allrows if p==prior and k==kind and t==2]
        take=rng.choice(len(eligible),min(5000,len(eligible)),replace=False)
        chosen.update(eligible[int(i)] for i in take)
    targets=[]
    for p in sorted((BASE/'photo_target_base').glob('*.npz')):
        g=loadz(p);inside=g['target_type']==2;g['target_type'][inside]=0
        for i in range(len(g['point_id'])):
            if (p.name,i) in chosen:g['target_type'][i]=2
        savez(BASE/'photo_targets'/p.name,**g)
        for i in np.flatnonzero(g['target_type']):targets.append(dict(file=p.name,index=int(i),point_id=str(g['point_id'][i]),type=int(g['target_type'][i])))
        records.append(dict(file=p.name,type1_count=int((g['target_type']==1).sum()),type2_count=int((g['target_type']==2).sum()),
            type1_area_m2=float(g['eligible_area_m2'][g['target_type']==1].sum()),type2_area_m2=float(g['eligible_area_m2'][g['target_type']==2].sum())))
    # The type-3 truth-only extension can only increase this target count. A
    # threshold crossed by this strict lower bound is sufficient to stop.
    picked=np.random.default_rng(20261102).choice(len(targets),min(200,len(targets)),replace=False)
    sample=[targets[int(i)] for i in picked]
    result=dict(at=now(),seed=20261102,sample=sample,sample_count=len(sample),
        target_count_lower_bound=len(targets),target_type3_pending=True,rows=records,
        truth_opened=False,scientific_verdict=None)
    dump(BASE/'photo_benchmark_selection.json',result);dump(C/'photo_benchmark_selection.lock.json',dict(at=now(),
        selection_sha256=sha(BASE/'photo_benchmark_selection.json'),config_sha256=sha(C/'judgecheck_v1.json'),
        sample=sample,source_sha256=sha(Path(__file__)),scientific_verdict=None))
    print('PHOTO_BENCH_SAMPLE',len(sample),'TARGET_LOWER_BOUND',len(targets))

if __name__=='__main__':main()
