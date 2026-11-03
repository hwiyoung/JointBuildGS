"""Development geometry diagnostics; no parameter fitting or judgment changes."""
import json,csv
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import binary_erosion
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez
from record_setting_reply2 import record as record_setting
BASE=O/'r2';INPUT=O/'r1'
EX=dict(count=73,area_m2=5.442552935831812,label='실험 지역과 사진 점을 공유해 뺀 핵심점')
def stat(d,m):return dict(count=int(m.sum()),area_m2=float(d['area'][m].sum()))
def add(rows,group,metric,d,m,**extra):rows.append(dict(group=group,metric=metric,**stat(d,m),**extra))
def main():
    lock=C/'diagnostics.reply2.lock.json'
    if lock.exists() and not (C/'revisions/r2/diagnostics.initial.lock.json').exists():
        (C/'revisions/r2/diagnostics.initial.lock.json').write_bytes(lock.read_bytes());folder=BASE/'revisions';folder.mkdir(exist_ok=True);(folder/'diagnostics_initial.json').write_bytes((BASE/'diagnostics.json').read_bytes())
    record_setting('reply2_diagnostics','negative_n_is_unknown',True,'Separate n=-1 unavailable sentinel from actual 0<=n<4 in missing-u overlap; seven missing-u cores are affected, with no geometry or judgment change')
    definition='XY global 0.25m occupancy of retained ALS roof core centres per building; boundary occupied cells have an empty four-neighbour; distance from core centre to nearest boundary-cell centre. Proxy for roof-support edge, not reference roof boundary.'
    dump(lock,dict(at=now(),source_sha256=sha(Path(__file__)),edge_definition=definition,edge_bins_m=[0,.25,.5,1,2],edge_near_m=.5,threshold_fitting=False,scientific_verdict=None))
    rows=[];parts=[];offsets=[];cursor=0
    for p in sorted((INPUT/'geometry').glob('*.npz')):
        d=loadz(p);prior=p.stem.split('__')[1];N=len(d['patch_id'])
        for k in np.unique(d['kind']):
            group=f'{prior}_{k}';m=d['kind']==k;missing=~np.isfinite(d['u_mvs']);unknown=d['geometry']==9
            for name,v in [('all',m),('u_M_missing',m&missing),('u_M_missing_n_lt4',m&missing&(d['n']>=0)&(d['n']<4)),('u_M_missing_n_unknown',m&missing&(d['n']<0)),('u_M_missing_n_ge4_uncountable',m&missing&(d['n']>=4)),('geometry_unknown',m&unknown)]:add(rows,group,name,d,v)
            reasons={'normal_missing':~np.isfinite(d['normal']).all(1),'prior_height_missing':~np.isfinite(d['prior_height_m']),
                'MVS_height_missing':~np.isfinite(d['mvs_mean_m']),'u_M_missing':missing,'sigma_P_missing':~np.isfinite(d['sigma_P_m']),
                'sigma_W_or_r_missing':~np.isfinite(d['sigma_W_m'])|~np.isfinite(d['r_m'])}
            remaining=m&unknown
            bits=np.zeros(N,np.int16)
            for j,(reason,v) in enumerate(reasons.items()):
                add(rows,group,'unknown_reason_overlapping:'+reason,d,m&unknown&v)
                add(rows,group,'unknown_reason_exclusive:'+reason,d,remaining&v);remaining=remaining&~v;bits[v]|=1<<j
            add(rows,group,'unknown_reason_exclusive:other',d,remaining)
            for code in np.unique(bits[m&unknown]):add(rows,group,f'unknown_reason_bitset:{code}',d,m&unknown&(bits==code))
        if prior=='ALS':
            parts.append({k:d[k] for k in ['centre','building','area','normal_rule_met','patch_id']});offsets.append((p.name,cursor,cursor+N));cursor+=N
    a={k:np.concatenate([v[k] for v in parts]) for k in parts[0]};distance=np.full(cursor,np.nan)
    for bid in np.unique(a['building']):
        ix=np.flatnonzero(a['building']==bid);xy=a['centre'][ix,:2];cells=np.floor(xy/.25).astype(np.int64);lo=cells.min(0)-1;pos=cells-lo;size=pos.max(0)+2
        occ=np.zeros(tuple(size),bool);occ[pos[:,0],pos[:,1]]=True;edge=occ&~binary_erosion(occ)
        centres=(np.argwhere(edge)+lo+.5)*.25;distance[ix]=cKDTree(centres).query(xy)[0]
    for name,left,right in [('0_to_0.25',0,.25),('0.25_to_0.5',.25,.5),('0.5_to_1',.5,1),('1_to_2',1,2),('over_2',2,np.inf)]:
        for label,m in [('fallback',~a['normal_rule_met']),('rule_met',a['normal_rule_met'])]:add(rows,'ALS_1','edge_'+label+':'+name,a,m&(distance>=left)&(distance<right))
    edge_summary={}
    for label,m in [('fallback',~a['normal_rule_met']),('rule_met',a['normal_rule_met'])]:
        edge_summary[label]=dict(**stat(a,m),near_edge_area_m2=float(a['area'][m&(distance<=.5)].sum()),near_edge_area_fraction=float(a['area'][m&(distance<=.5)].sum()/a['area'][m].sum()),distance_unweighted_quantiles_m=np.quantile(distance[m],[.25,.5,.75]).tolist())
    for name,l,r in offsets:savez(BASE/'edge'/name,patch_id=a['patch_id'][l:r],edge_distance_m=distance[l:r],normal_fallback=~a['normal_rule_met'][l:r])
    # Aggregate tile rows by exact metric/group, retaining unrounded areas.
    aggregate={}
    for r in rows:
        key=(r['group'],r['metric']);v=aggregate.setdefault(key,dict(group=key[0],metric=key[1],count=0,area_m2=0.));v['count']+=r['count'];v['area_m2']+=r['area_m2']
    out=dict(at=now(),rows=list(aggregate.values()),edge_definition=definition,edge_summary=edge_summary,excluded_shared_cores=EX,scientific_verdict=None)
    total=sum(r['count'] for r in out['rows'] if r['metric']=='u_M_missing');assert total==450713,total
    dump(BASE/'diagnostics.json',out);dump(D/'tables/reply2_geometry_diagnostics.json',out)
    with (D/'tables/reply2_geometry_diagnostics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['group','metric','count','area_m2']);w.writeheader();w.writerows(out['rows']);w.writerow(dict(group='ALL',metric=EX['label'],count=73,area_m2=EX['area_m2']))
    print('DIAGNOSTICS_COMPLETE',json.dumps(edge_summary),flush=True)
if __name__=='__main__':main()
