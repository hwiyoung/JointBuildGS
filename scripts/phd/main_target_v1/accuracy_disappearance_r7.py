"""Read truth only after frozen disappearance decisions; public holdout aggregates only."""
import numpy as np
from common import *
from disappearance_r7 import loadz
from judgment_census import lookup
def summarize(d,a,gt,tau,gt_valid,split,site,prior):
    rows=[];unobs=d['region']==0;truth=gt_valid&np.isfinite(gt)&np.isfinite(tau);near=truth&(abs(gt)<=tau)
    for scope,mask in [('eval',d['in_eval']),('band',~d['in_eval'])]:
        for kind in [1,2]:
            for replacement,sub in [('all',np.ones(len(unobs),bool)),('original',~d['any_replaced']),('replaced',d['any_replaced'])]:
                sel=unobs&mask&(d['kind']==kind)&sub
                for policy,delete in [('r7',a['disappeared']),('reference_tested_patch_u',a['reference_disappeared']),('keep_all',np.zeros(len(sel),bool)),('delete_all',unobs)]:
                    removed=sel&delete;kept=sel&~delete;area=lambda m:float(d['area'][m].sum())
                    wrong=area(removed&near);correct=area(removed&truth&~near);den=wrong+correct
                    rows.append(dict(split=split,site=site,prior=prior,range=scope,kind=kind,replacement=replacement,policy=policy,
                        unobserved_count=int(sel.sum()),unobserved_area_m2=area(sel),deleted_count=int(removed.sum()),deleted_area_m2=area(removed),
                        wrongly_deleted_area_m2=wrong,correctly_deleted_area_m2=correct,deleted_truth_unavailable_area_m2=area(removed&~truth),
                        wrong_deleted_fraction_of_evaluable=wrong/den if den else None,
                        correctly_preserved_area_m2=area(kept&near),wrongly_preserved_area_m2=area(kept&truth&~near),preserved_truth_unavailable_area_m2=area(kept&~truth)))
    return rows
def main():
    rows=[]
    for p in sorted((OUT/'r7/targets').glob('*.npz')):
        site,prior=p.stem.rsplit('_',1);d=loadz(OUT/'r2/targets'/p.name);a=loadz(OUT/'r7/stage0'/f'{p.stem}.votes.npz')
        e=loadz(OUT/'r2/stage0/evaluation'/p.name);assert np.array_equal(e['centre'],d['centre'])
        rows+=summarize(d,a,e['gt_med'],e['tau'],np.isfinite(e['gt_med']),'experiment',site,prior)
    for split,sealed in [('development',False),('holdout',True)]:
        root=OUT/('holdout/r7/stage0' if sealed else 'r7/stage0/development');old=OUT/('holdout/r2/stage0' if sealed else 'r2/stage0/development')
        w=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2';w=w/'holdout' if sealed else w
        for prior in ['ALS','LoD2']:
            assert (root/f'{prior}.complete.json').exists();accum={}
            for p in sorted(old.glob(f'*__{prior}.npz')):
                d=loadz(p);d['in_eval']=np.ones(len(d['region']),bool);a=loadz(root/p.name)
                # This is after the immutable per-patch decision was saved.
                wp=w/'patch_values'/p.name.replace('.npz','__R1.5.npz')
                with np.load(wp) as z:
                    ix=lookup(z['patch_id'],d['patch_id']);assert (ix>=0).all();gt=z['gt_p'][ix];tau=z['tau'][ix];valid=z['gt_status'][ix]==0
                for row in summarize(d,a,gt,tau,valid,split,'aggregate',prior):
                    key=(row['range'],row['kind'],row['replacement'],row['policy'])
                    if key not in accum:accum[key]=row
                    else:
                        for k,v in row.items():
                            if k.endswith('_m2') or k.endswith('_count'):accum[key][k]+=v
            for r in accum.values():
                den=r['wrongly_deleted_area_m2']+r['correctly_deleted_area_m2'];r['wrong_deleted_fraction_of_evaluable']=r['wrongly_deleted_area_m2']/den if den else None;rows.append(r)
    result=dict(at=stamp(),status='COMPLETE_DISAPPEARANCE_ACCURACY',rows=rows,truth_rule='inherited tau; finite measured GT surface only; unavailable truth is not a zero or confirmed empty space',scientific_verdict=None)
    dump(DOC/'tables/disappearance_accuracy_r7.json',result);dump(OUT/'r7/stage0/accuracy_complete.json',dict(at=stamp(),status=result['status'],public_sha256=sha(DOC/'tables/disappearance_accuracy_r7.json'),scientific_verdict=None));print(result['status'],len(rows),flush=True)
if __name__=='__main__':main()
