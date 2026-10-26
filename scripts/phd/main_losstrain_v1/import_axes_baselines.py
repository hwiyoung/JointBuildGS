"""Reuse AXES71 a3/a9 tables; preserve redundant verification outputs as audit history."""
import json
import math
from pathlib import Path
from inputs import PH,OUT,SITES,PRIORS,save,sha

def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        out=[]
        for k in a:out+=differences(a[k],b[k],path+'/'+k) if k in b else [dict(path=path+'/'+k,kind='missing')]
        return out
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return [] if math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-7) else [dict(path=path,new=a,original=b)]
    return [] if a==b else [dict(path=path,new=a,original=b)]

def main():
    source=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/tables'
    a3=json.loads((source/'a3_metrics.json').read_text())['data'];a9=json.loads((source/'a9_metrics.json').read_text())['values']
    rows=[];checks=[];dest=Path('/docs/tables/axes');dest.mkdir(exist_ok=True)
    for site in SITES:
        for prior in PRIORS:
            key=site+'/'+prior;result='nojudge_'+prior+'_s0';data=a9[key+'/'+result]
            assert data['all']['status'].startswith('있음')
            path=dest/(site+'__'+prior+'__'+result+'.json')
            if path.exists():
                own=json.loads(path.read_text());diff=differences(own['values'],data);assert not diff,diff[:5]
                checks.append(dict(case=key,differences=0,absolute_and_relative_tolerance=1e-7,recomputed_file_sha256=sha(path)))
                hist=Path('/docs/history/recomputed_axes');hist.mkdir(exist_ok=True)
                path.rename(hist/path.name)
            save(path,dict(site=site,prior=prior,result=result,values=data,source=str(source/'a9_metrics.json'),
                source_sha256=sha(source/'a9_metrics.json'),source_key=key+'/'+result,origin='기존 AXES71 일9 표에서 옮김',scientific_verdict=None))
            for method in ['prior','mvs','method']:
                for res,values in a3[key][method]['values'].items():
                    rows.append(dict(site=site,prior=prior,result=res,values=values,source_key=key+'/'+method+'/values/'+res))
    save('/docs/tables/axes_baselines_existing.json',dict(rows=rows,source=str(source/'a3_metrics.json'),source_sha256=sha(source/'a3_metrics.json'),
        original_nojudge_source=str(source/'a9_metrics.json'),verification=checks,scientific_verdict=None))
    save(OUT/'checks/axes_baseline_reuse.json',dict(status='PASS',verified_cases=checks,
        redundant_job_stopped='B0_b10/ALS: intentionally stopped after locating a9 existing values; original/partial outputs retained',scientific_verdict=None))
    with Path('/docs/issues.md').open('a') as f:f.write('\nLT-008 RESOLVED: AXES71 a9 already contains all six nojudge tables. Three redundantly recomputed cases matched every field within 1e-7; their records are preserved under history/recomputed_axes. The B0 ALS duplicate CPU job was intentionally stopped; remaining baseline values are imported from a9. Stage-1 patch scoring remains a new required calculation.\n')
    print('existing AXES baseline tables reused; verified duplicates',len(checks),flush=True)

if __name__=='__main__':main()
