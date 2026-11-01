"""Complete core vote and unit-median recount; public receipt contains aggregates only."""
import numpy as np
from common import *
from verify7000_r7 import loadz
def main():
    rows=[]
    for split in ['development','holdout']:
        sealed=split=='holdout';old=OUT/('holdout/r2/stage0' if sealed else 'r2/stage0/development');root=OUT/('holdout/r7/stage0' if sealed else 'r7/stage0/development')
        for prior in ['ALS','LoD2']:
            receipt=json.loads((root/f'{prior}.complete.json').read_text());assert not receipt['GT_loaded_before_decision'];assert receipt['config_sha256']==sha(CFG/'target_v1.r7.stage0.json')
            for path,h in receipt['input_files'].items():assert sha(Path(path))==h
            units=[];us=[];replaced=[];count=gone=valid=fallback=0;areas=[]
            for p in sorted(old.glob(f'*__{prior}.npz')):
                d=loadz(p);a=loadz(root/p.name);expected=(d['region']==0)&(a['votes'][:,0]>=2)&(2*a['votes'][:,0]>a['votes'][:,:3].sum(1));ref=(d['region']==0)&(a['reference_votes'][:,0]>=2)&(2*a['reference_votes'][:,0]>a['reference_votes'][:,:3].sum(1))
                assert np.array_equal(expected,a['disappeared']) and np.array_equal(ref,a['reference_disappeared']);assert (a['fallback_samples']<=a['valid_samples']).all()
                assert not a['votes'][d['region']!=0].any();units.append(d['building']);us.append(d['u']);replaced.append(d['u_replaced']);count+=len(expected);gone+=int(expected.sum());valid+=int(a['valid_samples'].sum());fallback+=int(a['fallback_samples'].sum());areas.append(float(d['area'][expected].sum()))
            labels,ix=np.unique(np.concatenate(units),return_inverse=True);u=np.concatenate(us);rep=np.concatenate(replaced);assert labels.tolist()==receipt['units']
            for unit,v in receipt['u_median_by_unit'].items():
                sel=(ix==int(unit))&np.isfinite(u)&~rep;assert float(np.median(u[sel]))==v
            assert valid==receipt['valid_samples'] and fallback==receipt['fallback_samples']
            public=json.loads((DOC/'tables'/f'disappearance_{split}_{prior}_r7.json').read_text())['rows'];assert abs(sum(r['disappeared_area_m2'] for r in public if r['replacement']=='all')-sum(areas))<1e-7
            rows.append(dict(split=split,prior=prior,patch_count=count,disappeared_count=gone,disappeared_area_m2=sum(areas),valid_samples=valid,fallback_samples=fallback,fallback_fraction=fallback/valid if valid else None,unit_medians_and_inputs_verified=True))
    record=dict(at=stamp(),status='PASS_CORE_VOTES_UNIT_MEDIANS_AND_PUBLIC_AGGREGATES',rows=rows,scientific_verdict=None);dump(OUT/'r7/verification/core.json',record);dump(DOC/'tables/core_verification_r7.json',record);print(record['status'],flush=True)
if __name__=='__main__':main()
