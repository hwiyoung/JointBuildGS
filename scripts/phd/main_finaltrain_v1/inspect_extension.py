"""Record full-scope versus frozen-evaluation differences without changing either."""
import sys
from common import *
site=sys.argv[1];rows=[]
for prior in ['ALS','LoD2']:
    stem=f'{site}__{prior}'
    ev=loadz(JA/'core_points'/f'{stem}.npz',['source_index','region','reason','photo_code','kind','centre','n','geometry','prior_height_m','mvs_mean_m','u_mvs','sigma_P_m'])
    ex=loadz(O/'outside'/site/'method'/f'{stem}.npz')
    ix=np.searchsorted(ex['source_index'],ev['source_index']);assert np.array_equal(ex['source_index'][ix],ev['source_index'])
    bad=np.flatnonzero(ex['judge_region'][ix]!=ev['region'][5])
    details=[]
    for j in bad:
        values={}
        for k in ['photo_code','kind','n','geometry','prior_height_m','mvs_mean_m','u_mvs','sigma_P_m']:
            a,b=ev[k][j].item(),ex[k][ix[j]].item()
            values[k]={'frozen':a if np.isfinite(a) else None,'full_scope':b if np.isfinite(b) else None}
        details.append(dict(source_index=int(ev['source_index'][j]),centre=ev['centre'][j].tolist(),frozen_region=int(ev['region'][5,j]),full_scope_region=int(ex['judge_region'][ix[j]]),fields=values))
    rows.append(dict(site=site,prior=prior,eval_patches=len(ix),decision_mismatches=len(bad),photo_code_mismatches=int((ex['photo_code'][ix]!=ev['photo_code']).sum()),details=details))
dump(O/'verification'/f'extension_judgments_{site}.json',dict(at=now(),rows=rows,training_eval_source='frozen JUDGEAPPLY core_points only',scientific_verdict=None))
dump(D/'tables'/f'extension_judgments_{site}.json',dict(rows=rows,scientific_verdict=None))
print(json.dumps(rows,ensure_ascii=False),flush=True)
