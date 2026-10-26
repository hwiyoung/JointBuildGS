"""Exact paired initialization, map and fixed-checkpoint array comparisons."""
import argparse
import json
import numpy as np
from inputs import OUT,save,sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',required=True);ap.add_argument('--site',required=True);ap.add_argument('--prior',required=True)
    a=ap.parse_args();base=OUT/'checks'/a.attempt
    dirs=[base/f'{rev}_{a.site}_{a.prior}' for rev in ['r16','r17']]
    rows=[]
    for path in ['model/monitor/init_points.npz','probe/probe.npz']:
        with np.load(dirs[0]/path,allow_pickle=False) as x,np.load(dirs[1]/path,allow_pickle=False) as y:
            assert set(x.files)==set(y.files)
            for k in x.files:
                xx,yy=x[k],y[k]
                same=xx.shape==yy.shape and np.array_equal(xx,yy,equal_nan=True) if xx.dtype.kind in 'fc' else np.array_equal(xx,yy)
                row=dict(file=path,key=k,shape=list(xx.shape),equal=bool(same))
                if not same and xx.shape==yy.shape and xx.dtype.kind in 'fc':
                    delta=np.abs(xx-yy);row['max_absolute_difference']=float(np.nanmax(delta))
                rows.append(row)
    maps=[json.loads((p/'model/monitor/initial_map_hashes.json').read_text()) for p in dirs]
    map_same=maps[0]==maps[1];passed=map_same and all(r['equal'] for r in rows)
    record=dict(site=a.site,prior=a.prior,status='PASS' if passed else 'STOP',initial_maps_equal=map_same,
        arrays=rows,optimizer_steps=0,scientific_verdict=None)
    save(base/f'comparison_{a.site}_{a.prior}.json',record)
    save(f'/docs/tables/current_{a.site}_{a.prior}.json',record)
    print(a.site,a.prior,record['status'],'arrays',len(rows),'differ',sum(not r['equal'] for r in rows),flush=True)
    assert passed,'6.2 STOP: r16/r17 differ; no training permitted'

if __name__=='__main__':main()
