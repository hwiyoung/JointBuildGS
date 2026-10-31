"""Independent scalar formulas and conservation checks on frozen stage-0 bytes."""
import math
import numpy as np
from common import *

c,lock=locked();t2=json.loads((OUT/'stage0_r1/T2.json').read_text());checks=[]
for name,fit in t2['fits'].items():
    x=math.log10(fit['T2_m']);mu=fit['means_log10'];sd=fit['sd_log10'];w=fit['area_weights']
    def odds(v):return math.log(w[1]/w[0])+math.log(sd[0]/sd[1])-.5*((v-mu[1])/sd[1])**2+.5*((v-mu[0])/sd[0])**2
    assert abs(odds(x))<1e-9 and odds(x-1e-6)<0 and odds(x+1e-6)>0
    assert w[1]>=.05 and x>mu[0] and abs(sum(w)-1)<1e-10
    assert all(b['log_likelihood']+1e-10>=a['log_likelihood'] for a,b in zip(fit['history'],fit['history'][1:]))
    checks.append(dict(check='mixture_boundary_and_monotonic_likelihood',variant=name,status='PASS'))
rng=np.random.default_rng(20261101)
for site in c['sites']+c['deferred_sites']:
    for prior in c['priors']:
        f=OUT/'targets'/f'{site}_{prior}.npz'
        with np.load(f) as z:d={k:z[k] for k in z.files}
        meta=json.loads(f.with_suffix('.json').read_text());assert sha(f)==meta['target_sha256']
        assert (d['u'][d['u_replaced']]>0).all() and (d['sigma_p'][d['sigma_p_replaced']]>0).all()
        valid=d['region']>=0;assert np.isfinite(d['target'][valid]).all() and (d['sigma'][valid]>0).all()
        assert np.isnan(d['target'][~valid]).all()
        idx=rng.choice(len(valid),min(512,len(valid)),replace=False)
        for i in idx:
            u,sp,n,dist,sd=(float(d[k][i]) for k in ['u','sigma_p','n','d','s_sample'])
            normal=d['normal'][i];lab=-1;h=sig=float('nan')
            if np.isfinite(normal).all() and abs(np.linalg.norm(normal)-1)<1e-6 and math.isfinite(u) and math.isfinite(sp):
                sm2=u*u+.0275**2
                if n<4:lab=0;h=0.;sig=sp
                elif all(math.isfinite(v) for v in [dist,sd]):
                    limit=1.96*math.sqrt(sd*sd/n+sm2+sp*sp)
                    assert abs(limit-d['DL'][i])<1e-10
                    if abs(dist)<=limit:lab=1;h=dist*sp*sp/(sm2+sp*sp);sig=math.sqrt(sm2*sp*sp/(sm2+sp*sp))
                    elif abs(dist)>t2['fits']['main_u']['T2_m'] or d['photo'][i]==1:lab=3;h=dist;sig=math.sqrt(sm2)
                    else:lab=2;h=0.;sig=sp
            assert lab==d['region'][i]
            if lab>=0:
                assert abs(h-d['h'][i])<1e-10 and abs(sig-d['sigma'][i])<1e-10
                assert np.allclose(d['target'][i],d['centre'][i]+h*normal,rtol=0,atol=1e-10)
        ev=d['in_eval'];fraction=float(d['area'][ev&~valid].sum()/d['area'][ev].sum());assert fraction<=.1
        checks.append(dict(check='independent_scalar_target',site=site,prior=prior,sampled=len(idx),status='PASS',
            patches=len(valid),unavailable_eval_fraction=fraction,target_sha256=sha(f)))
for filename in ['experimental_r1.json','experimental_deferred_r1.json']:
    data=json.loads((DOC/'tables'/filename).read_text())
    for r in data['areas']:
        assert abs(sum(r[x+'_area_m2'] for x in ['unavailable','unobserved','agreement','preservation','correction'])-r['area_m2'])<1e-7
    for r in data['accuracy']:
        assert abs(sum(v for k,v in r.items() if k.startswith('cell') and k.endswith('_area_m2'))-r['area_m2'])<1e-7
        assert 0<=r['wrong_area_m2']<=r['denominator_area_m2']+1e-9
checks.append(dict(check='experimental_area_conservation',status='PASS'))
for f in (OUT/'stage0_r1').rglob('*.npz'):
    assert 'holdout' not in str(f.relative_to(OUT/'stage0_r1'))
result=dict(status='PASS_STAGE0_INDEPENDENT_CHECKS',at=stamp(),checks=checks,scientific_verdict=None,
    public_holdout_boundary='aggregate counts, areas, fractions only; per-patch files exclusively under /out/holdout',
    config_sha256=lock['config_sha256'])
dump(DOC/'tables/stage0_verification_r1.json',result);dump(OUT/'stage0_r1/verification.json',result)
print(result['status'],len(checks),flush=True)
