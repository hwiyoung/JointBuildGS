"""8.7: factual values beside frozen expectations, without scientific verdicts."""
import csv
import json
from pathlib import Path
import numpy as np
from inputs import OUT,SITES,PRIORS,save

def main():
    tab=Path('/docs/tables');scores=json.loads((tab/'patch_scores_all.json').read_text())['rows']
    sides=json.loads((tab/'sides_all.json').read_text())['rows'] if (tab/'sides_all.json').exists() else []
    photos=json.loads((tab/'photo.json').read_text())['rows']
    changes=json.loads((tab/'numerical_changes.json').read_text())['rows']
    lookup={(r['site'],r['prior'],r['variant'],r['subset']):r for r in scores}
    rows=[];wing=[]
    def add(label,site,prior,metric,variant,value,N,source,criterion=None):
        rows.append(dict(expectation=label,site=site,prior=prior,metric=metric,variant=variant,value=value,N=N,
            criterion=criterion,source=source,status='측정값' if value is not None else '확인 불가: 해당 학습·채점 미완료',verdict=None))
    for site in SITES+['three_units_pooled']:
        for prior in PRIORS:
            for var in ['lt_fixgt','lt_dyngt','lt_dynsoft','lt_dynnow']:
                name=var+'_'+prior+'_s0';r=lookup.get((site,prior,name,'unexplained'))
                add('가',site,prior,'unexplained_within_tau_percent',var,r['within_tau_percent'] if r else None,r['patches'] if r else None,'patch_scores_all.json')
                if var=='lt_dyngt':
                    add('나',site,prior,'analytic_minus_trained_pp',var,r['analytic_minus_trained_pp'] if r else None,r['patches'] if r else None,'patch_scores_all.json',10.)
                    s=next((x for x in sides if x['site']==site and x['prior']==prior and x['variant']==var and x['subset']=='unexplained'),None)
                    add('다',site,prior,'same_side_area_percent',var,s['same_side_percent'] if s else None,s['denominator_patches'] if s else None,'sides_all.json',80.)
                if site not in SITES:continue
                for label,subset,metric in [('라','cell_0','error_patch_median_m'),('라','cell_0','within_tau_percent'),('바','cell_4','within_tau_percent')]:
                    r=lookup.get((site,prior,name,subset));b=lookup.get((site,prior,'nojudge_'+prior+'_s0',subset))
                    c=next((x for x in changes if x['kind']=='stage1_patch' and x['site']==site and x['prior']==prior and x['variant']==name and x['reference'].startswith('nojudge') and x['subset']==subset and x['metric']==metric),None)
                    value=r[metric]-b[metric] if r and b and r[metric] is not None and b[metric] is not None else None
                    add(label,site,prior,subset+'_'+metric+'_minus_nojudge',var,value,r['patches'] if r else None,'patch_scores_all.json; numerical_changes.json',c['threshold'] if c else None)
                p=next((x for x in photos if x['site']==site and x['prior']==prior and x['result']==name),None)
                add('사',site,prior,'eval_psnr_minus_nojudge_db',var,p['eval_psnr_minus_nojudge_db'] if p else None,p['eval_views'] if p else None,'photo.json',1.)
    # Frozen B173 wing strip, stage-1 patch areas, no outcome-driven recropping.
    site='B173nb_b10';prior='ALS';root=OUT/'direct_stage1_v2'/(site+'__'+prior)
    ex=json.loads(Path('/config/losstrain_v1.json').read_text())['figures']['sections'][0]
    with np.load(root/'evaluation.npz') as e,np.load(root/'values.npz') as v:
        a=np.array(ex['start']);b=np.array(ex['end']);t=(b-a)/np.linalg.norm(b-a);xy=e['centre'][:,:2]-a
        along=xy@t;cross=xy@np.array([-t[1],t[0]])
        m=(along>=0)&(along<=np.linalg.norm(b-a))&(np.abs(cross)<=ex['half_width'])&e['in_eval']&e['scoring_allowed']&e['has_mvs']&(e['cell']<4)
        clean=m&(e['u_prior']<.01)
        for var in ['lt_dyngt','lt_dynnow']:
            p=OUT/'patch_z'/f'{site}__{prior}__{var}_{prior}_s0.npz'
            for label,q in [('wing_all',m),('wing_clean_q0',clean)]:
                N=int(q.sum());A=float(e['area'][q].sum());ratio=None;old=None
                if p.exists():
                    with np.load(p) as z:
                        ok=np.abs(z['z']-e['p_gt'])<=e['tau'];side=z['side']
                        ratio=float(100*e['area'][q&ok].sum()/A) if A else None
                        old=float(100*e['area'][q&(side==0)].sum()/A) if A else None
                add('마',site,prior,label+'_within_tau_percent',var,ratio,N,str(p),80. if var=='lt_dyngt' and label=='wing_all' else None)
                add('마',site,prior,label+'_prior_side_percent',var,old,N,str(p))
                wing.append(dict(site=site,prior=prior,variant=var,subset=label,patches=N,area_m2=A,
                    fraction_of_full_strip_area=A/float(e['area'][m].sum()) if m.any() else None,within_tau_percent=ratio,prior_side_percent=old))
    save(tab/'expectations.json',dict(rows=rows,wing=wing,section=ex,interpretation='values only; no expectation verdict',scientific_verdict=None))
    with (tab/'expectations.csv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 기대와 측정값을 나란히','','기대의 판정은 하지 않는다. 미완료 판은 확인 불가이며 원래 기준은 그대로 둔다.','',
        '| 기대 | 단위 | 사전 | 판 | 값의 정의 | N | 값 | 기준 |','|---|---|---|---|---|---:|---:|---:|']
    fmt=lambda x:'확인 불가' if x is None else f'{x:.6f}'
    for r in rows:
        lines.append(f"| {r['expectation']} | {r['site']} | {r['prior']} | {r['variant']} | {r['metric']} | {r['N'] if r['N'] is not None else '확인 불가'} | {fmt(r['value'])} | {fmt(r['criterion'])} |")
    (tab/'expectations.md').write_text('\n'.join(lines)+'\n')
    print('expectation values',len(rows),flush=True)

if __name__=='__main__':main()
