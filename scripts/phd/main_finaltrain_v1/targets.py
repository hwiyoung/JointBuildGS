"""Build full-scope targets from frozen no-reference decisions only."""
import sys
from common import *

FIELDS=['patch_id','source_index','centre','normal','kind','area','n','u_mvs','sigma_P_m',
        'prior_height_m','mvs_mean_m','photo_code','region','reason','geometry']

def calculate(d,prior):
    region=d['judge_region'].copy();reason=d['reason'].copy()
    hp,hm,sp,um=[d[k] for k in ['prior_height_m','mvs_mean_m','sigma_P_m','u_mvs']]
    undecided=(region==9)&(d['n']>=4)&~np.isfinite(um)&np.isfinite(hm)&np.isfinite(hp)
    region[undecided]=1 if prior=='ALS' else 2;reason[undecided]=2
    region[undecided&(d['photo_code']==0)]=1;reason[undecided&(d['photo_code']==0)]=0
    region[undecided&(d['photo_code']==1)]=2;reason[undecided&(d['photo_code']==1)]=1
    h=np.full(len(hp),np.nan);sigma=h.copy();vp=sp**2;vm=um**2
    agree=region==0;keep=np.isin(region,[1,4]);correct=region==2
    with np.errstate(divide='ignore',invalid='ignore'):
        h[agree]=(hp[agree]*vm[agree]+hm[agree]*vp[agree])/(vm[agree]+vp[agree])
        sigma[agree]=np.sqrt(vp[agree]*vm[agree]/(vp[agree]+vm[agree]))
    h[keep]=hp[keep];sigma[keep]=sp[keep];h[correct]=hm[correct];sigma[correct]=um[correct]
    donors=um[correct&np.isfinite(um)&(um>0)]
    replacement=float(np.median(donors)) if len(donors) else None
    missing=undecided&correct
    if missing.any() and replacement is None:raise ValueError('No finite correction u_M donors; cannot invent sigma')
    if replacement is not None:sigma[missing]=replacement
    valid=np.isfinite(h)&np.isfinite(sigma)&(sigma>0)&np.isfinite(d['normal']).all(1)
    valid&=np.linalg.norm(d['normal'],axis=1)>0
    tg=np.full(len(h),-1,np.int8)
    for ja,old in [(0,1),(1,2),(2,3),(4,0)]:tg[(region==ja)&valid]=old
    tg[region==3]=5
    area=d['area'];active=valid&np.isin(region,[0,1,2,4])
    ref=float(area[active].sum()/np.sum(area[active]/sigma[active]))
    assert np.isfinite(ref) and ref>0
    return dict(region=tg,judge_region=region,reason=reason,h=h,sigma=sigma,
        target=d['centre']+h[:,None]*d['normal'],target_height_m=h,target_sigma_m=sigma,
        undecided_before=undecided,sigma_replaced=missing,surface_exists=active,
        sigma_ref=np.asarray(ref),correction_u_median=np.asarray(replacement if replacement is not None else np.nan))

def replay_eval(site,prior):
    d=loadz(JA/'core_points'/f'{site}__{prior}.npz',FIELDS+['free5','free10'])
    import textwrap
    text=(R/'scripts/phd/main_judgeapply_v1/judgments.py').read_text();a=text.index('      reg=np.full');b=text.index('      fp=PH/',a)
    env=dict(np=np,d=d,N=len(d['n']),prior=prior,free=np.where(d['kind']==1,d['free10'],d['free5']))
    exec(textwrap.dedent(text[a:b]),env)
    assert np.array_equal(env['reg'][5],d['region'][5]),'Frozen judgment replay mismatch'
    assert np.array_equal(env['why'][5],d['reason'][5]),'Frozen reason replay mismatch'
    return dict(count=len(d['n']),decision_mismatches=0,reason_mismatches=0,scope='exact JUDGEAPPLY decision code on frozen inputs; no recalibration')

def main(site,prior):
    cfg();stem=f'{site}__{prior}';raw=loadz(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz')
    N=len(raw['centre']);receipt=json.loads((O/'outside'/site/'budget_receipt.json').read_text())
    assert receipt['status'] in ['PASS','TIME_LIMIT_BACKGROUND_FALLBACK']
    ev=loadz(JA/'core_points'/f'{stem}.npz',FIELDS);ii=ev['source_index'];assert np.array_equal(raw['centre'][ii],ev['centre'])
    d={k:raw[k].copy() for k in ['centre','normal','kind','area','in_eval']}
    d.update(source_index=np.arange(N),patch_id=np.array([f'{prior}:{site}:{i}' for i in range(N)]),
        n=np.full(N,-1),u_mvs=np.full(N,np.nan),sigma_P_m=np.full(N,np.nan),prior_height_m=np.full(N,np.nan),mvs_mean_m=np.full(N,np.nan),photo_code=np.full(N,9,np.int8),judge_region=np.full(N,9,np.int8),reason=np.full(N,9,np.int8))
    extended_diff=None
    if receipt['status']=='PASS':
        ex=loadz(O/'outside'/site/'method'/f'{stem}.npz');ix=ex['source_index']
        for k in d:
            if k in ex:d[k][ix]=ex[k]
        lookup={int(k):j for j,k in enumerate(ix)};jj=np.array([lookup[int(k)] for k in ii])
        extended_diff=int((ex['judge_region'][jj]!=ev['region'][5]).sum())
    for k in ['centre','normal','kind','area','n','u_mvs','sigma_P_m','prior_height_m','mvs_mean_m','photo_code']:
        d[k][ii]=ev[k]
    d['judge_region'][ii]=ev['region'][5];d['reason'][ii]=ev['reason'][5]
    values=calculate(d,prior);result={**d,**values, 'any_replaced':values['sigma_replaced']}
    save=O/'targets'/f'{stem}.npz';savez(save,**result)
    active=values['surface_exists'];s=values['sigma'];region=values['judge_region'];w=values['sigma_ref']/s[active];area=d['area']
    mean=float(np.average(w,weights=area[active]));assert abs(mean-1)<1e-12
    outside=np.ones(N,bool);outside[ii]=False
    comparison=dict(status='확인 전')
    rp=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1/targets_v2'/f'{stem}.npz'
    if rp.exists():
        rt=loadz(rp,['source_index','target_height_m']);jj=rt['source_index'];a=values['h'][jj];b=rt['target_height_m']
        assert np.array_equal(np.isfinite(a),np.isfinite(b));diff=np.abs(a[np.isfinite(a)]-b[np.isfinite(b)]);maximum=float(diff.max()) if len(diff) else 0.
        assert maximum<=.001
        comparison=dict(status='PASS',max_height_difference_m=maximum,sha256=sha(rp))
    sources=[TG/'stage0_r1/inputs'/f'{site}_{prior}.npz',JA/'core_points'/f'{stem}.npz',JA/'calibration.json',O/'outside'/site/'budget_receipt.json']
    if receipt['status']=='PASS':sources.append(O/'outside'/site/'method'/f'{stem}.npz')
    rec=dict(at=now(),site=site,prior=prior,output_sha256=sha(save),patches=N,
        source_files={str(p):sha(p) for p in sources},
        eval_replay=replay_eval(site,prior),extended_eval_decision_mismatches=extended_diff,
        frozen_eval_always_used=True,outside_status=receipt['status'],outside_patches=int(outside.sum()),outside_area_m2=float(area[outside].sum()),
        sigma_ref=float(values['sigma_ref']),unclipped_area_weighted_mean=mean,correction_u_median=float(values['correction_u_median']) if np.isfinite(values['correction_u_median']) else None,
        unassigned_target_area_m2=float(area[~active&(region!=3)].sum()),
        regions=[dict(region=int(r),patches=int((region==r).sum()),area_m2=float(area[region==r].sum()),
            sigma_q10_q50_q90=np.quantile(s[(region==r)&active],[.1,.5,.9]).tolist() if ((region==r)&active).any() else None,
            undecided_area_m2=float(area[(region==r)&values['undecided_before']].sum())) for r in [0,1,2,3,4,9]],
        rescore_comparison=comparison,sigma_W_used=False,r_added=False,GT_used=False,scientific_verdict=None)
    dump(save.with_suffix('.json'),rec);dump(D/'tables'/f'targets_{stem}.json',rec)
    print('TARGETS_COMPLETE',stem,'sigma_ref',float(values['sigma_ref']),flush=True)

if __name__=='__main__':main(*sys.argv[1:])
