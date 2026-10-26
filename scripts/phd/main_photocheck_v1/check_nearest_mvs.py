"""Preserve an unavailable nearest-height score instead of skipping to another height."""
from common import *
def main():
    rows=[];changed=0
    for f in sorted((O/'work/pilot').glob('*__*.npz')):
        if f.stem.endswith('_selection'):continue
        p=npz(f);valid=np.isfinite(p['mvs_p']);dist=np.abs(p['heights']-p['mvs_p'][:,None]);dist[~np.isfinite(dist)]=np.inf
        nearest=np.argmin(dist,axis=1);missing=valid&~np.isfinite(p['curve'][np.arange(len(nearest)),nearest]);wrong=missing&np.isfinite(p['s_mvs'])
        changed+=int(wrong.sum());rows.append(dict(file=f.name,changed_points=int(wrong.sum())))
        if wrong.any():
            dump(O/'inspection/s_mvs_before'/f.with_suffix('.json').name,dict(point_id=p['point_id'][wrong],previous_s_mvs=p['s_mvs'][wrong],nearest_height=p['heights'][np.flatnonzero(wrong),nearest[wrong]],reason='Nearest sampled-height score is missing. Preserve missing; do not skip to another height. No curve or judgment change.'))
            p['s_mvs'][wrong]=np.nan;temporary=f.with_name(f.stem+'.repaired.npz');np.savez_compressed(temporary,**p);temporary.replace(f);rec=load(f.with_suffix('.json'));rec['file_sha256']=sha(f);rec['s_mvs_missing_repair']=dict(at=now(),points=int(wrong.sum()),no_curve_or_judgment_change=True);dump(f.with_suffix('.json'),rec)
    dump(O/'gates/nearest_mvs.json',dict(status='PASS',at=now(),changed_points=changed,rows=rows,source=env()));print('nearest MVS score check PASS; missing-value repairs',changed)
if __name__=='__main__':main()
