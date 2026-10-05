"""Read-only gate audit of sealed dense masks; never reruns or changes selection."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def quantiles(v):
    v=np.asarray(v);v=v[np.isfinite(v)]
    return dict(n=int(len(v)),q10_q50_q90=[round(float(x),5) for x in np.quantile(v,[.1,.5,.9])]) if len(v) else dict(n=0,q10_q50_q90=None)


def analyze(file, cfg):
    with np.load(file,allow_pickle=False) as z:
        full_decision=z['decision']; roi=z['roi']; mask=z['candidate'] & roi; n=int(mask.sum()); roi_count=int(roi.sum())
        keys=['decision','photo_examined','profiled','admitted_neighbors','mvs_support','prior_support',
              'profile_support','profile_mvs_support','profile_prior_support','profile_cost','profile_width',
              'profile_spacing','profile_modes','profile_edge','profile_boundary','profile_best','prior_depth','mvs_depth']
        a={k:z[k][mask] for k in keys}
        pself=z['prior_self_status'][:,mask]==3; mself=z['mvs_self_status'][:,mask]==3
        parallax=z['parallax_min_deg'][:,mask]>=cfg['minimum_patch_parallax_degrees']
        bothself=(pself&mself)
    count=lambda v:int(np.count_nonzero(v))
    d=a['decision']; prof=a['profiled']; complete=prof & (a['profile_support']>=cfg['minimum_joint_views'])
    mwin=(a['profile_mvs_support']>=cfg['minimum_joint_views'])&(a['profile_mvs_support']>a['profile_prior_support'])
    pwin=(a['profile_prior_support']>=cfg['minimum_joint_views'])&(a['profile_prior_support']>a['profile_mvs_support'])
    majority=complete&(mwin|pwin)
    checks={
        'absolute_cost_le_0p2':np.isfinite(a['profile_cost'])&(a['profile_cost']<=cfg['profile_maximum_cost']),
        'near_cost_width_le_0p5m':a['profile_width']<=cfg['profile_maximum_width_m'],
        'sample_spacing_le_0p25m':a['profile_spacing']<=cfg['profile_maximum_spacing_m'],
        'single_interval':a['profile_modes']==1,
        'minimum_not_at_endpoint':a['profile_edge']==0,
        'near_cost_interval_not_at_endpoint':a['profile_boundary']==0,
        'winner_source_within_0p5m':(mwin&(np.abs(a['profile_best']-a['mvs_depth'])<=cfg['profile_maximum_source_offset_m']))|
                                    (pwin&(np.abs(a['profile_best']-a['prior_depth'])<=cfg['profile_maximum_source_offset_m']))}
    accepted=majority&np.logical_and.reduce(list(checks.values())); stored=(d==5)|(d==6)
    # Persist any float32 snapshot-boundary mismatch instead of concealing it.
    mismatch=count(accepted!=stored)
    drop={}
    for key in checks:
        reduced=majority&np.logical_and.reduce([v for k,v in checks.items() if k!=key])
        drop[key]=dict(failed_among_finite_majority=count(majority&~checks[key]),
                       additionally_pass_if_only_this_check_removed=count(reduced&~stored))
    funnel={'candidate_pixels':n,'both_self_compatible_in_2_views':count(bothself.sum(0)>=2),
            'both_self_and_parallax_in_2_views':count((bothself&parallax).sum(0)>=2),
            'comparable_photo_neighbors_ge_2':count(a['admitted_neighbors']>=2),
            'at_least_2_same_source_photo_support_profiled':count(prof),
            'complete_profiles_in_2_views':count(complete),'majority_after_complete_profiles':count(majority),
            'all_gates_reconstructed':count(accepted),'stored_selected':count(stored)}
    partition={
        'insufficient_comparable_neighbors':count(a['admitted_neighbors']<2),
        'no_two_supporters_despite_comparable_neighbors':count((a['admitted_neighbors']>=2)&~prof),
        'complete_profile_support_lost':count(prof&~complete),
        'no_source_majority_after_complete_profile':count(complete&~majority),
        'final_profile_or_source_distance_gates':count(majority&~stored),
        'selected':count(stored)}
    if sum(partition.values())!=n:raise ValueError('Candidate partition does not sum')
    if count(d==3) or not np.all(a['photo_examined']):raise ValueError('Camera not finished')
    spacing_only=majority&np.logical_and.reduce([v for k,v in checks.items() if k!='sample_spacing_le_0p25m'])&~checks['sample_spacing_le_0p25m']
    examples=[]
    yy,xx=np.where(mask)
    for i in np.flatnonzero(spacing_only)[:3]:
        examples.append(dict(x=int(xx[i]),y=int(yy[i]),prior_depth=float(a['prior_depth'][i]),
                             mvs_depth=float(a['mvs_depth'][i]),profile_best=float(a['profile_best'][i]),
                             profile_cost=float(a['profile_cost'][i]),profile_width=float(a['profile_width'][i]),
                             profile_spacing=float(a['profile_spacing'][i]),
                             mvs_support=int(a['profile_mvs_support'][i]),prior_support=int(a['profile_prior_support'][i])))
    return dict(region=file.parent.parent.name,view=file.parent.name,candidate_pixels=n,
                abstain=count(d==4),mvs_selected=count(d==5),prior_selected=count(d==6),
                abstain_pct=round(100*count(d==4)/n,4) if n else None,
                total_roi=roi_count,
                funnel=funnel,disjoint_candidate_partition=partition,gate_failures=drop,
                finite_profile_quantiles={k:quantiles(a[k][complete]) for k in ('profile_cost','profile_width','profile_spacing')},
                absolute_discrepancy_by_profile_cohort=quantiles(np.abs(a['prior_depth'][complete]-a['mvs_depth'][complete])),
                spacing_only_failure_examples=examples,reconstructed_decision_mismatches=mismatch)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path,required=True);ap.add_argument('--config',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    cfg=json.loads(args.config.read_text());receipt=json.loads((args.evidence/'receipt.json').read_text())
    seals={r['path']:r['sha256'] for r in receipt['outputs']}
    rows=[];bindings=[]
    for file in sorted(args.evidence.glob('P*/view_*/arrays.npz')):
        digest=sha(file)
        if digest!=seals[str(file.relative_to(args.evidence))]:raise ValueError('Sealed array mismatch')
        row=analyze(file,cfg);rows.append(row);bindings.append(dict(path=str(file),sha256=digest))
        print(json.dumps(row,ensure_ascii=False),flush=True)
    if len(rows)!=9:raise ValueError('Expected9 completed views')
    summary=[]
    for region in ('P1','P2','P3'):
        rr=[r for r in rows if r['region']==region]
        item=dict(region=region,**{k:sum(r[k] for r in rr) for k in ('candidate_pixels','abstain','mvs_selected','prior_selected','reconstructed_decision_mismatches')})
        item['abstain_pct']=round(100*item['abstain']/item['candidate_pixels'],3)
        for name in ('funnel','disjoint_candidate_partition'):
            item[name]={k:sum(r[name][k] for r in rr) for k in rr[0][name]}
        item['gate_failures']={k:{kk:sum(r['gate_failures'][k][kk] for r in rr) for kk in rr[0]['gate_failures'][k]} for k in rr[0]['gate_failures']}
        summary.append(item)
    args.output.mkdir(parents=True,exist_ok=False)
    result=dict(status='COMPLETE_READ_ONLY_GATE_AUDIT',scientific_verdict=None,created_utc=datetime.now(timezone.utc).isoformat(),
                summary=summary,views=rows,inputs=bindings,config_sha256=sha(args.config),source_sha256=sha(__file__),
                parent_receipt_sha256=sha(args.evidence/'receipt.json'),
                limitations=['Counts are repeated camera observations, not unique area or independent samples.',
                             'Removing one final gate is a saved-score diagnostic; no recalculation, improved accuracy, or valid replacement mask is implied.',
                             'Complete-profile failure conflates source-patch holes, failed normal fits, visibility and texture over the whole search. Saved arrays cannot distinguish those internal reasons.',
                             'Final gate failure counts overlap. Exclusive funnel depends on ordering.'])
    (args.output/'audit.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
    print('REGIONAL_SUMMARY '+json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
