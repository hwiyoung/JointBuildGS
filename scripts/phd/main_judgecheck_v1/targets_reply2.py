"""Add evaluation-only type 3 without changing types 1/2 or calibration."""
import json
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez
BASE=O/'r2';INPUT=O/'r1'

def main():
    rows=[];tiles={};totals={}
    assert len(list((BASE/'truth').glob('*.npz')))==len(list((INPUT/'geometry').glob('*.npz')))
    for p in sorted((INPUT/'photo_targets').glob('*.npz')):
        tile,prior,kind=p.stem.split('__');g=loadz(p);d=loadz(INPUT/'geometry'/f'{tile}__{prior}.npz');e=loadz(BASE/'truth'/f'{tile}__{prior}.npz')
        assert np.array_equal(d['patch_id'],e['patch_id']);idx={pid:i for i,pid in enumerate(g['point_id'])}
        oracle=(d['kind']==int(kind))&(d['n']>=4)&np.isin(e['cell'],[1,2,3]);owner=np.array([idx[pid] for pid in d['photo_point_id'][oracle]],int)
        type3=np.zeros(len(g['point_id']),bool);type3[owner]=True;type3&=g['target_type']!=1
        # Membership can overlap the agreement sample. Keep the type-2 flag for
        # calibration and carry the type-3 flag separately for the oracle arm.
        t1=g['target_type']==1;t2=g['target_type']==2;t3=type3;g.update(target_type1=t1,target_type2=t2,target_type3=t3)
        g['target_type']=np.where(t1,1,np.where(t2,2,np.where(t3,3,0))).astype('u1')
        g['target_type_bits']=t1.astype('u1')+2*t2.astype('u1')+4*t3.astype('u1')
        target=t1|t2|t3;scoreable=target&np.isfinite(g['b_m'])&(g['b_m']>=0)&np.isfinite(g['core_d_median_m'])
        g['sweep_defined']=scoreable
        # Primitive height work estimate before plane availability is known.
        count=np.zeros(len(target),np.int64);count[scoreable]=(2*np.floor(g['b_m'][scoreable]/.02+1e-12)+1).astype(np.int64)
        row=dict(tile=tile,prior=prior,kind=int(kind),type1_count=int(t1.sum()),type2_count=int(t2.sum()),type3_count=int(t3.sum()),
            type2_type3_overlap_count=int((t2&t3).sum()),target_count=int(target.sum()),sweep_defined_count=int(scoreable.sum()),
            sweep_unavailable_count=int((target&~scoreable).sum()),height_hypotheses_both_planes=int(count.sum()*2),
            target_area_m2=float(g['eligible_area_m2'][target].sum()),type3_area_m2=float(g['eligible_area_m2'][t3].sum()))
        rows.append(row);tiles[tile]=tiles.get(tile,0)+row['target_count'];totals[f'{prior}_{kind}']=totals.get(f'{prior}_{kind}',0)+row['target_count']
        savez(BASE/'photo_targets'/p.name,**g)
        print('TARGETS123',tile,prior,kind,row['target_count'],row['type3_count'],flush=True)
    largest=sorted(tiles,key=lambda t:(-tiles[t],t))[0]
    result=dict(at=now(),rows=rows,total_targets=sum(tiles.values()),group_targets=totals,tile_targets=tiles,
        benchmark_tile=largest,benchmark_tile_count=tiles[largest],type3_included=True,
        type3_use='evaluation-only geometry-oracle arm; flags preserved separately; no threshold calibration membership changes',
        excluded_shared_cores=dict(count=73,area_m2=5.442552935831812),scientific_verdict=None)
    dump(BASE/'target_census.json',result);dump(D/'tables/reply2_target_census.json',result)
    dump(C/'targets.reply2.lock.json',dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),source_sha256=sha(Path(__file__)),census_sha256=sha(BASE/'target_census.json'),benchmark_tile=largest,scientific_verdict=None))
    print('BENCHMARK_TILE',largest,tiles[largest],'TOTAL_TARGETS',sum(tiles.values()),totals,flush=True)

if __name__=='__main__':main()
