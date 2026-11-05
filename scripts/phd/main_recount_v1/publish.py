"""Promote inherited tau=1 values and requested summaries, without resampling."""
from common import *

def main():
    c=cfg();kinds=['judgment_summary','result_by_judgment','offset_bins','wall_check','wall_sensitivity_candidate','unassigned','reproduction']
    merged={k:[] for k in kinds}
    for site in SITES:
        for prior in PRIORS:
            stem=f'{site}__{prior}';assert (O/'scenes'/stem/'complete.json').exists()
            for k in kinds:merged[k]+=json.loads((D/'tables'/stem/(k+'.json')).read_text())['rows']
    triggers=[r for r in merged['wall_check'] if r['exceeds_2pct']]
    for k,rows in merged.items():
        if k!='wall_sensitivity_candidate':table(k,rows)
    if triggers:table('wall_sensitivity',merged['wall_sensitivity_candidate'])
    rows=[r for r in readcsv(c['table4_source']) if r['cell_basis']=='score' and float(r['tau_multiplier'])==1]
    for r in rows:
        for key in ['cell','n_gt','n_result']:r[key]=int(r[key])
        for key in ['completeness','accuracy','gt_mean_m','result_mean_m']:r[key]=float(r[key]) if r[key] else None
        r['tau_multiplier']=float(r['tau_multiplier']);r['case_name']=CASES[r['cell']];r['method_name']=NAMES[r['method']]
        r['role']='참고' if r['method'] in c['best_excludes'] else '최고 후보'
    for r in rows:
        eligible=[s for s in rows if (s['site'],s['prior'],s['cell'])==(r['site'],r['prior'],r['cell']) and s['method'] not in c['best_excludes']]
        for metric in ['completeness','accuracy']:
            vals=[s[metric] for s in eligible if s[metric] is not None];best=max(vals) if vals else None
            r['best_'+metric]=best;r['gap_'+metric+'_pp']=100*(best-r[metric]) if best is not None and r[metric] is not None else None
            r['best_'+metric+'_methods']=';'.join(s['method'] for s in eligible if best is not None and s[metric]==best)
    table('result_accuracy',[r for r in rows if r['cell']!=-1]);table('excluded_case_results',[r for r in rows if r['cell']==-1])
    central=[dict(scene=LABELS[r['site']],site=r['site'],prior=r['prior'],case_id=r['cell'],case_name=r['case_name'],cell_basis='score',method=r['method'],method_name=r['method_name'],completeness_pct=None if r['completeness'] is None else r['completeness']*100,best_pct=None if r['best_completeness'] is None else r['best_completeness']*100,gap_pp=r['gap_completeness_pp'],n_gt=r['n_gt'],small=r['small'],role=r['role']) for r in rows if r['cell']!=-1]
    table('central_figure',central)
    summary=[]
    for scope in ['B173_B0','all_six']:
        for metric in c['summary_metrics']:
            for method in METHODS:
                allmine=[r for r in rows if r['method']==method and r['cell'] in c['summary_cases'] and (scope=='all_six' or r['site']!='R1rep_b10')]
                mine=[r for r in allmine if r['n_gt']>=1000 and r[metric] is not None and r['gap_'+metric+'_pp'] is not None]
                minimum=min(mine,key=lambda r:r[metric]) if mine else None
                worst=max(mine,key=lambda r:r['gap_'+metric+'_pp']) if mine else None
                row=dict(scope=scope,metric=metric,method=method,method_name=NAMES[method],role='참고' if method in c['best_excludes'] else '최고 후보',cell_basis='score',n_cells=len(mine),small_cells_excluded=sum(r['n_gt']<1000 for r in allmine),unavailable_cells=sum(r['n_gt']>=1000 and r[metric] is None for r in allmine),min_pct=minimum[metric]*100 if minimum else None,max_gap_pp=worst['gap_'+metric+'_pp'] if worst else None)
                for prefix,r in [('min',minimum),('max_gap',worst)]:
                    for key in ['site','prior','cell','n_gt']:row[prefix+'_'+key]=r[key] if r else None
                for th in [3,5,10]:row[f'within_{th}pp']=sum(r['gap_'+metric+'_pp']<=th+1e-10 for r in mine)
                row['max_gap_tied_locations']=';'.join(f"{r['site']}|{r['prior']}|{r['cell']}" for r in mine if abs(r['gap_'+metric+'_pp']-row['max_gap_pp'])<1e-10) if worst else ''
                summary.append(row)
    table('method_summary',summary)
    table('tau_values',readcsv(c['tau_source']))
    dump(D/'tables/wall_trigger.json',dict(triggered=bool(triggers),qualifying_cells_methods=len(triggers),criteria=c['wall'],triggers=triggers,scientific_verdict=None))
    # Wide summary keeps constant rules as separate rows per scene.
    wide=[]
    for site in SITES:
        for prior in PRIORS:
            for rule in ['본 방법','늘 보존','늘 보정']:
                mine=[r for r in merged['judgment_summary'] if (r['site'],r['prior'],r['rule'])==(site,prior,rule)]
                row=dict(site=site,prior=prior,rule=rule,cell_basis='score')
                for k in [0,1,2,4,3,'all']:
                    r=next(v for v in mine if v['case_id']==k);name=CASES.get(k,'전체(둘 다 틀림 제외)')
                    row[name+'_pct']=r['accuracy_pct'];row[name+'_n_gt']=r['n_gt'];row[name+'_small']=r['small']
                wide.append(row)
    table('judgment_summary_wide',wide)
    bins=[]
    for site in SITES:
        for prior in PRIORS:
            for k in [1,2]:
                for lo in [0.,.5,1.,2.,4.]:
                    mine=[r for r in merged['offset_bins'] if (r['site'],r['prior'],r['case_id'],r['lower_m'])==(site,prior,k,lo)]
                    first=mine[0];row={key:first[key] for key in ['site','prior','cell_basis','case_id','case_name','distance_source','lower_m','upper_m','lower_inclusive','upper_inclusive','n_gt','small','nonfinite_distance_rows']}
                    for r in mine:row[r['method']+'_completeness_pct']=r['completeness_pct']
                    bins.append(row)
    table('offset_bins_wide',bins)
    print('PUBLISHED',len(rows),'result rows, wall trigger',len(triggers),flush=True)

if __name__=='__main__':main()
