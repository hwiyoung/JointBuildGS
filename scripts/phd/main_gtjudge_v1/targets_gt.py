"""Stage-1 case basis, exact patch majority, unchanged FINALTRAIN arithmetic."""
import sys
import numpy as np
from common import *
from normal_line import cases,values
from majority import decide,calculate_targets
EXPECTED={0:0,1:2,2:1,4:4}

def main(site,prior):
    cfg();stage_lock(1);stem=f'{site}__{prior}';root=O/'scenes'/stem
    path=O/'targets_gt'/f'{stem}.npz'
    if path.exists() and path.with_suffix('.json').exists():return
    row=loadz(RL/'stage0'/stem/'cells.npz');basis='normal_line';reason=None
    try:
        pp=json.loads((root/'distances/prior.json').read_text());mm=json.loads((root/'distances/mvs.json').read_text())
        if json.loads((O/'stage0_decision.json').read_text())['global_case_basis']!='normal_line':basis='RECOUNT_nearest_fallback';reason='remaining signal after one ray-origin correction'
        else:
            p=loadz(root/'distances/prior.npz')['row_s'];m=loadz(root/'distances/mvs.npz')['row_s']
            labels,absent=cases(p,m,row['row_tau_m'])
    except (OSError,KeyError) as e:basis='RECOUNT_nearest_fallback';reason='stage0 unavailable: '+str(e)
    if basis!='normal_line':labels=row['score_cell_1p0'];absent=labels==-1
    core=loadz(JA/'core_points'/f'{stem}.npz',['source_index','patch_id','area','photo_code'])
    target=loadz(FT/'targets'/f'{stem}.npz');original=target['judge_region'].copy();ix=core['source_index'];assert np.array_equal(target['patch_id'][ix],core['patch_id'])
    owner=row['row_owner'];fullowner=np.full(len(owner),-1,'i8');good=owner>=0;fullowner[good]=ix[owner[good]]
    judgment,counts,corrections=decide(labels,fullowner,original,target['in_eval'],target['u_mvs'],target['mvs_mean_m'])
    target['judge_region']=judgment;new=calculate_targets(target,prior)
    # Oracle changes create a new missing-u_M correction that the old calculate()
    # only encountered while resolving undecided patches. Apply that same 2.2 rule
    # to the new label; raw u_M is left unavailable, never imputed.
    missing=(judgment!=original)&(judgment==2)&~np.isfinite(target['u_mvs'])&np.isfinite(target['mvs_mean_m'])
    donor=float(new['correction_u_median'])
    if missing.any() and np.isfinite(donor) and donor>0:
        for key in ['sigma','target_sigma_m']:new[key][missing]=donor
        new['sigma_replaced'][missing]=True
        valid=missing&np.isfinite(new['h'])&np.isfinite(target['normal']).all(1)&(np.linalg.norm(target['normal'],axis=1)>0)
        new['surface_exists'][valid]=True;new['region'][valid]=3
        issue(stem+f': 정답 판단으로 새로 보정이 된 u_M 결측 {int(missing.sum())}패치에는 FINALTRAIN 2.2 미판정 보정의 같은 장면 u_M 중앙값을 sigma에 적용. 원래 u_M은 NaN 유지.')

    # calculate() also normalizes old undecided patches. Keep inherited outcomes outside
    # the explicit oracle-change set; only the shared sigma_ref is recomputed globally.
    untouched=judgment==original
    for key,val in new.items():
        if key in target and np.asarray(val).ndim and len(val)==len(original):val[untouched]=target[key][untouched]
    target.update(new);target['any_replaced']=target['sigma_replaced']
    active=target['surface_exists'];target['sigma_ref']=np.asarray(target['area'][active].sum()/np.sum(target['area'][active]/target['sigma'][active]))
    assert set(target)==set(loadz(FT/'targets'/f'{stem}.npz'))
    savez(path,**target)
    rowjudge=np.full(len(owner),9,'i1');rowold=rowjudge.copy();rowjudge[good]=target['judge_region'][fullowner[good]];rowold[good]=original[fullowner[good]]
    savez(root/'stage1_cells.npz',case_id=labels,prior_absent=absent,judge_gt=rowjudge,judge_original=rowold,row_owner=owner)
    cross=[];upper=[]
    for a in [0,1,2,4,3,9]:
        for b in [0,1,2,4,3,9]:
            take=(original[ix]==a)&(target['judge_region'][ix]==b)
            cross.append(dict(site=site,prior=prior,unit='judgment patches',original_judgment=a,gt_judgment=b,patches=int(take.sum()),area_m2=float(core['area'][take].sum())))
    for k in [0,1,2,4,3,-1]:
        take=good&(labels==k);n=int(take.sum())
        upper.append(dict(site=site,prior=prior,unit='reference cases vs judgments',case_id=k,case_basis=basis,n_gt=n,small='적음' if n<1000 else '',
            method_correct_pct=100*int((rowold[take]==EXPECTED[k]).sum())/n if n and k in EXPECTED else None,
            majority_upper_pct=100*int((rowjudge[take]==EXPECTED[k]).sum())/n if n and k in EXPECTED else None))
    table('stage1/'+stem+'_cross',cross);table('stage1/'+stem+'_upper',upper)
    dump(path.with_suffix('.json'),dict(at=now(),site=site,prior=prior,diagnostic='정답 판단',case_basis=basis,fallback_reason=reason,
        target_sha256=sha(path),parent_sha256=sha(FT/'targets'/f'{stem}.npz'),changed_patches=int((target['judge_region']!=original).sum()),
        majority_fallbacks=corrections,changed_correction_missing_sigma=int(((judgment!=original)&(judgment==2)&~np.isfinite(target['sigma'])).sum()),field_schema_identical=True,scientific_verdict=None))
    if reason:issue(stem+': '+reason+'; RECOUNT 칸으로 단계 1·2·3 계속.')
    print('GT_TARGET_READY',stem,basis,int((target['judge_region']!=original).sum()),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
