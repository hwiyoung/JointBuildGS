"""Independent delivery checks on cached inputs and outputs; no new scoring."""
from add2_common import *

def main():
    config2();handoff=json.loads((O/'queue/addendum2/handoff.json').read_text())
    for path,digest in handoff['r25_hashes'].items():assert sha(R/'src/phd/forks/GeoGS-conf-guided-v1-r25'/path)==digest
    assert sha(R/'scripts/phd/main_gtjudge_v1/run_queue.py')==handoff['queue_script_sha256']
    assert json.loads((O/'verification/unit_r26.json').read_text())['status']=='PASS'
    assert (O/'queue/addendum2/selection_commit.json').exists()
    alt=[]
    for site in SITES:
        orig=loadz(FT/'targets'/f'{site}__LoD2.npz');core=loadz(JA/'core_points'/f'{site}__LoD2.npz',['source_index','reason']);ix=core['source_index'];allowed=np.zeros(len(orig['patch_id']),bool);allowed[ix]=(orig['judge_region'][ix]==2)&(core['reason'][5]==2)
        for variant in ['alt_na','alt_da']:
            new=loadz(target_file(site,'LoD2',variant));changed=new['judge_region']!=orig['judge_region'];assert not (changed&~allowed).any()
            if variant=='alt_na':assert np.array_equal(changed,allowed)
            assert (new['judge_region'][changed]==1).all();assert np.array_equal(new['target_height_m'][changed],orig['prior_height_m'][changed],equal_nan=True)
            assert np.array_equal(new['target_sigma_m'][changed],orig['sigma_P_m'][changed],equal_nan=True)
            for key in new:
                if new[key].ndim and len(new[key])==len(changed):
                    a=new[key][~changed];b=orig[key][~changed];assert np.array_equal(a,b,equal_nan=True) if a.dtype.kind in 'fc' else np.array_equal(a,b),(site,variant,key)
            alt.append(dict(site=site,variant=variant,changed=int(changed.sum()),outside_editable_unchanged=True))
        for prior in PRIORS:
            target=loadz(target_file(site,prior));expected=target['surface_exists']&np.isfinite(target['prior_height_m'])&np.isfinite(target['sigma_P_m'])&(target['sigma_P_m']>=0)&(abs(target['target_height_m']-target['prior_height_m'])<=1.96*target['sigma_P_m'])
            assert np.array_equal(loadz(O/'freespace_targets'/f'{site}__{prior}.npz')['patch_id'],target['patch_id'][expected])
            assert (D/'tables/addendum2'/f'feature_comparison_{site}__{prior}.json').exists()
            for stage in ['stage0','stage1']:assert (D/'tables/addendum2'/stage/f'{site}__{prior}.json').exists()
            before=json.loads((D/'tables/stage1'/f'{site}__{prior}_metrics.json').read_text())['rows']
            after=json.loads((D/'tables/addendum2/stage1'/f'{site}__{prior}.json').read_text())['rows']
            lookup={(x['method'],x['case_id']):x for x in after if x['surface']=='all'}
            for old in before:
                if (old['method'],old['case_id']) not in lookup:continue
                new=lookup[(old['method'],old['case_id'])]
                assert new['completeness_pct']==old['completeness_pct'] and new['n_gt']==old['n_gt']
                assert new['accuracy_before_pct']==old['accuracy_pct']
                if prior=='LoD2':assert new['accuracy_pct']==old['accuracy_pct']
    selected=json.loads((D/'판고르기.json').read_text());summary=[]
    for variant in ['alt_na','alt_da']:
        checks=[c for c in selected['checks'] if c['variant']==variant];guards=[c for c in checks if c['case_id'] in [0,1,4] and c['n_gt']>=1000];gain=[c['variant_pct']-c['ga_pct'] for c in checks if c['case_id']==2]
        passed=all(c['variant_pct']>=c['ga_pct']-2 for c in guards);worst=max([max(0,c['ga_pct']-c['variant_pct']) for c in guards],default=0)
        if passed:summary.append((variant,sum(gain)/3,worst))
    if not summary:winner='alt_ga'
    elif len(summary)==1:winner=summary[0][0]
    elif abs(summary[0][1]-summary[1][1])<=1:winner=min(summary,key=lambda x:(x[2],x[0]!='alt_na'))[0]
    else:winner=max(summary,key=lambda x:x[1])[0]
    assert winner==selected['selected']
    for site in ['B173nb_b10','B0_b10']:
        for kind in ['textureless1','textureless2','edge1','edge2']:
            assert (D/'figures'/f'{site}__LoD2_stage2_{kind}.png').exists(),('missing repaired stage2 figure',site,kind)
    receipt=dict(at=now(),status='PASS',r25_and_running_old_queue_unchanged=True,selection_independent_reduction=True,selected=winner,alternative_target_checks=alt,freespace_files_verified=6,scientific_verdict=None)
    dump(D/'verification/addendum2_cpu.json',receipt);dump(O/'verification/addendum2_cpu.json',receipt);print('PASS_ADDENDUM2_CPU_DELIVERY',winner,flush=True)
if __name__=='__main__':main()
