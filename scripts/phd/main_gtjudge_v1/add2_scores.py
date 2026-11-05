import sys
from add2_common import *
from normal_line import values

def normal_z(site,prior,method):
    root=O/'scenes'/f'{site}__{prior}'/'distances';p=root/f'{method}_samples.npz'
    if p.exists():return loadz(p,['normal'])['normal'][:,2]
    meta=json.loads((root/f'{method}.json').read_text())
    return loadz(O/'shared'/site/meta['mesh_sha256']/('cylinder_roof.npz' if prior=='ALS' else 'cylinder.npz'),['sample_normal'])['sample_normal'][:,2]

def metric_rows(site,prior,methods=None,split=True):
    config2();stem=f'{site}__{prior}';root=O/'scenes'/stem;row=loadz(root/'rows.npz');cells=loadz(root/'stage1_cells.npz');labels=cells['case_id'];out=[]
    methods=methods or METHODS+['gt_judgment_mesh','alt_na','alt_da','A1','A2','fix','seed1_ft','seed1_base']
    for method in methods:
        actual='judgment_mesh' if method=='alt_ga' else method;p=root/'distances'/f'{actual}.npz'
        if not p.exists():continue
        z=loadz(p);ix=z['sample_reference_row'];ok=ix>=0;qc=np.full(len(ix),-1,'i1');qc[ok]=labels[ix[ok]]
        qw=np.zeros(len(ix),bool);qw[ok]=row['wall'][ix[ok]];steep=abs(normal_z(site,prior,actual))<.5 if prior=='ALS' else np.zeros(len(ix),bool)
        for surface in (['all','roof','wall'] if split and prior=='LoD2' else ['all']):
            surf=np.ones(len(labels),bool) if surface=='all' else row['wall'] if surface=='wall' else ~row['wall']
            qs=np.ones(len(ix),bool) if surface=='all' else (ok&qw if surface=='wall' else ok&~qw)
            for case in [0,1,2,4,3,'all','prior_absent']:
                mask=surf&(np.ones(len(labels),bool) if case=='all' else cells['prior_absent'] if case=='prior_absent' else labels==case)
                qm=qs&(np.ones(len(ix),bool) if case=='all' else np.where(ok,cells['prior_absent'][ix.clip(0)],False) if case=='prior_absent' else qc==case)
                v=values(z['row_s'][mask],row['row_tau_m'][mask]);before=values(z['sample_s'][qm],z['sample_tau'][qm],z['sample_eligible'][qm]);after=values(z['sample_s'][qm],z['sample_tau'][qm],(z['sample_eligible']&~steep)[qm])
                out.append(dict(site=site,prior=prior,method=method,surface=surface,case_id=case,n_gt=v['n'],small='적음' if v['n']<1000 else '',completeness_pct=v['within_pct'],accuracy_before_pct=before['within_pct'],accuracy_pct=after['within_pct'],accuracy_excluded_steep_total=int((qm&steep).sum()),accuracy_excluded_steep_additional=int((qm&steep&z['sample_eligible']).sum()),accuracy_excluded_no_reference_1m=int((qm&~z['sample_eligible']).sum()),**{'gt_'+k:v for k,v in v.items()},**{'result_'+k:v for k,v in after.items()}))
    return out

def all_tables(site,prior):
    table('addendum2/stage1/'+site+'__'+prior,metric_rows(site,prior))
    # Copy stage 0, preserving every completeness/case value and replacing only result metrics.
    old=json.loads((D/'tables/stage0'/f'{site}__{prior}.json').read_text())['rows'];root=O/'scenes'/f'{site}__{prior}';labels=loadz(root/'rows.npz',['score_cell_1p0'])['score_cell_1p0'];cache={}
    for row in old:
        method=row['method']
        if method not in cache:cache[method]=(loadz(root/'distances'/f'{method}.npz'),abs(normal_z(site,prior,method))<.5 if prior=='ALS' else None)
        z,steep=cache[method];ix=z['sample_reference_row'];qc=np.full(len(ix),-1,'i1');ok=ix>=0;qc[ok]=labels[ix[ok]];mask=qc==row['case_id'] if row['case_id']!='all' else np.ones(len(ix),bool)
        nearest=row['distance']=='nearest_comparison';eligible=z['sample_old_eligible'] if nearest else z['sample_eligible'];new=eligible if steep is None else eligible&~steep
        val=values(z['sample_nearest_signed' if nearest else 'sample_s'][mask],z.get('sample_nearest_tau',z['sample_tau'])[mask] if nearest else z['sample_tau'][mask],new[mask])
        row.update(accuracy_before_pct=row['accuracy_pct'],accuracy_pct=val['within_pct'],accuracy_excluded_steep_total=int((mask&steep).sum()) if steep is not None else 0,accuracy_excluded_steep_additional=int((mask&steep&eligible).sum()) if steep is not None else 0,**{'result_'+k:v for k,v in val.items()})
    table('addendum2/stage0/'+site+'__'+prior,old)

def choose():
    v=config2();rule=v['selection'];lock=json.loads((C/'addendum2.lock.json').read_text());allrows=[]
    for site in SITES:allrows.extend(metric_rows(site,'LoD2',['alt_ga','alt_na','alt_da','gt_judgment_mesh','FINALTRAIN_30000','baseline_30000','fusion'],True))
    table('addendum2/alternative_metrics',allrows)
    lookup={(r['site'],r['method'],r['case_id']):r for r in allrows if r['surface']=='all'};results=[];checks=[]
    for variant in ['alt_na','alt_da']:
        drops=[];gains=[];passed=True
        for site in SITES:
            for case in rule['cases']:
                a=lookup[(site,'alt_ga',case)];b=lookup[(site,variant,case)];guard=case in rule['guard_cases'] and a['n_gt']>=rule['minimum_gt'];delta=None if a['completeness_pct'] is None or b['completeness_pct'] is None else b['completeness_pct']-a['completeness_pct']
                good=not guard or (delta is not None and delta>=-rule['maximum_drop_pp']);passed&=good
                if guard:drops.append(max(0.,-delta) if delta is not None else None)
                if case==rule['objective_case']:gains.append(delta)
                checks.append(dict(site=site,variant=variant,case_id=case,n_gt=a['n_gt'],ga_pct=a['completeness_pct'],variant_pct=b['completeness_pct'],delta_pp=delta,used_for_guard=guard,pass_guard=good))
        gain=float(np.mean(gains)) if all(x is not None for x in gains) else None
        results.append(dict(variant=variant,passes=bool(passed and gain is not None),mean_gain_pp=gain,worst_guard_drop_pp=max(drops,default=0) if all(x is not None for x in drops) else None))
    eligible=[x for x in results if x['passes']];winner='alt_ga';reason='no alternative satisfies all eligible guard cells'
    if len(eligible)==1:winner=eligible[0]['variant'];reason='only eligible alternative'
    elif len(eligible)==2:
        a,b=eligible
        if abs(a['mean_gain_pp']-b['mean_gain_pp'])<=rule['tie_within_pp']:
            winner=min(eligible,key=lambda x:(x['worst_guard_drop_pp'],x['variant']!='alt_na'))['variant'];reason='within 1pp mean gain; smallest worst guard loss; fixed order on exact secondary tie'
        else:winner=max(eligible,key=lambda x:x['mean_gain_pp'])['variant'];reason='largest mean preservation-case gain among eligible alternatives'
    dump(D/'판고르기.json',dict(at=now(),selected=winner,reason=reason,checks=checks,alternatives=results,rule_sha256=lock['selection_sha256'],GT_used_for_selection=True,GT_used_for_variant_targets=False,scientific_verdict=None));print('SELECTED',winner,flush=True)
if __name__=='__main__':
    if sys.argv[1]=='choose':choose()
    elif sys.argv[1]=='metrics':table('addendum2/stage1/'+sys.argv[2]+'__'+sys.argv[3],metric_rows(sys.argv[2],sys.argv[3]))
    else:all_tables(*sys.argv[1:])
