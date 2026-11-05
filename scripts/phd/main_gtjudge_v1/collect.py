"""Stage gate and tables from cached distances, without repeating measurement."""
import sys
import numpy as np
from common import *
from normal_line import values

def gate():
    records=[]
    for site in SITES:
        for prior in PRIORS:
            stem=f'{site}__{prior}'
            for method in ['prior','mvs']:
                path=O/'scenes'/stem/'distances'/f'{method}.json'
                if path.exists():records.append(json.loads(path.read_text()))
                else:records.append(dict(site=site,prior=prior,method=method,unavailable=True,remaining_signal=None))
    fallback=any(r.get('unavailable') or r['remaining_signal'] for r in records)
    rec=dict(at=now(),status='RECOUNT_FALLBACK_CONTINUE' if fallback else 'PASS_NORMAL_LINE',
        global_case_basis='RECOUNT_nearest_fallback' if fallback else 'normal_line',checks=records,
        threshold_pct=90,minimum_old_both_correct_n=1000,scientific_verdict=None)
    dump(D/'단계0_판정.json',rec);dump(O/'stage0_decision.json',rec)
    if fallback:issue('단계 0 일부 이상 신호/계산 불가: 여섯 장면 모두 RECOUNT 칸으로 단계 1·2·3 계속. 거리는 법선/원기둥으로 채점.')
    print(rec['status'],flush=True)

def metrics(site,prior):
    stem=f'{site}__{prior}';root=O/'scenes'/stem;row=loadz(root/'rows.npz');cells=loadz(root/'stage1_cells.npz');labels=cells['case_id'];out=[]
    basis=json.loads((O/'targets_gt'/f'{stem}.json').read_text())['case_basis']
    methods=METHODS+['gt_judgment_mesh','A1','A2','seed1_ft','seed1_base']
    for method in methods:
        path=root/'distances'/f'{method}.npz'
        if not path.exists():continue
        z=loadz(path);idx=z['sample_reference_row'];qc=np.full(len(idx),-1,'i1');ok=idx>=0;qc[ok]=labels[idx[ok]]
        for case in [0,1,2,4,3,-1,'all','prior_absent']:
            if case=='prior_absent':
                mask=cells['prior_absent'];qm=np.zeros(len(idx),bool);qm[ok]=mask[idx[ok]]
            else:
                mask=labels==case if case!='all' else np.ones(len(labels),bool)
                qm=qc==case if case!='all' else np.ones(len(qc),bool)
            v=values(z['row_s'][mask],row['row_tau_m'][mask]);q=values(z['sample_s'][qm],z['sample_tau'][qm],z['sample_eligible'][qm])
            out.append(dict(site=site,prior=prior,method=method,case_id=case,unit='reference cases',case_basis=basis,distance='normal_line_and_cylinder',n_gt=v['n'],
                small='적음' if v['n']<1000 else '',completeness_pct=v['within_pct'],accuracy_pct=q['within_pct'],
                **{'gt_'+k:a for k,a in v.items()},**{'result_'+k:a for k,a in q.items()}))
    table('stage1/'+stem+'_metrics',out)
if __name__=='__main__':
    if sys.argv[1]=='gate':gate()
    else:metrics(*sys.argv[1:])
