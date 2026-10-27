"""Independent patch-array accounting and same-source checks for eight-arm handover."""
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np

from inputs import OUT, save, sha
from eight_arm_report import SITES, REPORT, VARS, DOC


def read(path):return json.loads(Path(path).read_text())


def main(sites=None, report_name=REPORT, prefix='eight_arm', expected_scored=8, expected_stopped=0):
    sites=list(SITES if sites is None else sites)
    data=read(DOC/f'tables/{prefix}_values.json')
    thresholds=read(DOC/f'tables/{prefix}_thresholds.json')['rows']
    assert data['core_scored_arms']==expected_scored
    assert len(data['paired_patch_rows'])==expected_scored*10 and len(data['side_rows'])==expected_scored*3
    assert len(thresholds)==len(sites)*21 and len(data['overview'])==len(sites)*9
    available={site:list(VARS) for site in sites}
    stopped=data.get('stopped',[])
    assert len(stopped)==expected_stopped
    stop_files=[]
    if expected_stopped:
        scope=data['scope']
        assert {(r['site'],r['variant']) for r in scope}=={(s,v) for s in sites for v in VARS}
        assert len(scope)==len(sites)*4 and len(scope)==expected_scored+expected_stopped
        available={s:[r['variant'] for r in scope if r['site']==s and r['status']=='CORE_SCORED'] for s in sites}
        assert sum(map(len,available.values()))==expected_scored
        for row in stopped:
            source=Path(row['source']);receipt=read(source)
            assert sha(source)==row['sha256'] and receipt==row['receipt']
            assert receipt['status']=='STOPPED_BY_FROZEN_CRITERION'
            assert not (source.parent/'PASS.json').exists()
            assert not (OUT/'patch_z'/f"{row['site']}__ALS__{row['variant']}_ALS_s0.npz").exists()
            archived=DOC/row['report_source'];assert read(archived)==receipt;stop_files.append(archived)
            c=receipt['criterion_record']
            assert c['iterations_after_reset']==100 and c['whole_opacity_median']<.05
            assert c['stop']=='whole-population opacity median < 0.05 after reset+100'
        assert len(data['unscored_analytic_rows'])==expected_stopped*10
        assert all(r['trained'] is None and r['status']=='HEALTH_STOPPED' for r in data['unscored_analytic_rows'])
    arrays={};domains={};masks={}
    for site in sites:
        root=OUT/'direct_stage1_v2'/f'{site}__ALS'
        with np.load(root/'evaluation.npz') as e:
            domain={k:e[k] for k in ['area','cell','in_eval','scoring_allowed','has_mvs','p_mvs','p_gt','tau']}
        with np.load(root/'values.npz') as v:
            unexplained=np.abs(domain['p_mvs'])/np.sqrt(v['sigma_prior'].astype(float)**2+v['sigma_mvs'].astype(float)**2)>3
        ok=domain['in_eval']&domain['scoring_allowed'];both=ok&domain['has_mvs']&(domain['cell']<4)
        masks[site]={'all_0_3':both,'unexplained':both&unexplained}
        masks[site].update({f'cell_{i}':ok&(domain['cell']==i) for i in range(6)})
        masks[site].update({f'unexplained_cell_{i}':both&unexplained&(domain['cell']==i) for i in [1,2]})
        domains[site]=domain
        for result in [v+'_ALS_s0' for v in available[site]]+['prop_ALS_s0','prop_ALS_s1']:
            path=OUT/'patch_z'/f'{site}__ALS__{result}.npz'
            with np.load(path) as z:arrays[(site,result)]={k:z[k] for k in ['z','side','patch_id']}
            assert len(arrays[(site,result)]['z'])==len(domain['area'])
            if result.startswith('lt_'):
                r=read(path.with_suffix('.json'));assert r['status']=='PASS' and sha(path)==r['patch_z_sha256']
                assert sha(Path(r['path']))==r['mesh_sha256']
                split=read(DOC/'tables/fate_cell_split'/site/f'ALS__{result}.json')
                assert split['partition_counts_equal_combined'] and set(split['regions'])=={'cell_0','cell_2'}
                parent=read(DOC/'tables/fates'/site/f'ALS__{result}.json')['regions']['prior_correct_0_2']
                assert sum(r['seeds_planted'] for r in split['regions'].values())==parent['seeds_planted']
                for category in parent['counts']:
                    assert sum(r['counts'][category] for r in split['regions'].values())==parent['counts'][category]
        reference_ids=arrays[(site,'prop_ALS_s0')]['patch_id']
        for key,value in arrays.items():
            if key[0]==site:assert np.array_equal(value['patch_id'],reference_ids)
    for row in data['paired_patch_rows']:
        site=row['site'];d=domains[site];m=masks[site][row['subset']]
        z=arrays[(site,row['variant']+'_ALS_s0')]['z'];r=row['trained'];A=float(d['area'][m].sum())
        hit=np.abs(z-d['p_gt'])<=d['tau'];missing=~np.isfinite(z)
        assert int(m.sum())==r['patches'] and A==r['area_m2']
        assert float(d['area'][m&hit].sum())==r['successful_area_m2']
        assert float(d['area'][m&missing].sum())==r['no_surface_area_m2']
        assert r['within_tau_percent']==(100*r['successful_area_m2']/A if A else None)
        assert r['no_surface_percent']==(100*r['no_surface_area_m2']/A if A else None)
        errors=np.abs(z-d['p_gt']);observed=m&np.isfinite(errors)
        assert r['error_observed_patches']==int(observed.sum())
        assert r['error_patch_median_m']==(float(np.median(errors[observed])) if observed.any() else None)
    for row in data['side_rows']:
        site=row['site'];mask=masks[site][row['subset']];d=domains[site]
        result=row['variant']+'_ALS_s0';actual=arrays[(site,result)]
        path=OUT/'patch_z'/f"{site}__ALS__analytic_{VARS[row['variant']][1]}.npz"
        with np.load(path) as z:
            assert np.array_equal(z['patch_id'],actual['patch_id'])
            same=actual['side']==z['side']
        area=float(d['area'][mask].sum());same_area=float(d['area'][mask&same].sum())
        assert row['denominator_patches']==int(mask.sum()) and row['denominator_area_m2']==area
        assert row['same_side_area_m2']==same_area
        assert row['same_side_percent']==(100*same_area/area if area else None)
    for row in thresholds:
        site=row['site'];d=domains[site];m=masks[site][row['subset']];metric=row['metric'];values=[];counts=[]
        for seed in [0,1]:
            result=f'prop_ALS_s{seed}';z=arrays[(site,result)]['z'];err=np.abs(z-d['p_gt'])
            source=row['seed_sources'][seed]
            assert sha(Path(source['source']))==source['sha256']
            if metric=='error_patch_median_m':
                valid=m&np.isfinite(err);N=int(valid.sum());value=float(np.median(err[valid])) if N else None
            else:
                N=int(m.sum());area=float(d['area'][m].sum())
                hit=err<=d['tau'] if metric=='within_tau_percent' else ~np.isfinite(z)
                value=100*float(d['area'][m&hit].sum())/area if area else None
            assert N==source['N'] and value==row[f'seed_{seed}']
            values.append(value);counts.append(N)
        case=2.8*abs(values[0]-values[1])/math.sqrt(2) if all(v is not None for v in values) else None
        three=None if metric=='error_patch_median_m' or not min(counts) else 300/min(counts)
        assert row['N']==min(counts) and row['case_spread']==case and row['three_points']==three
        parts=[x for x in [row['pooled'],case,three] if x is not None]
        assert row['threshold']==(max(parts) if parts else None)
    figure_files=[]
    for site in sites:
        for figure_prefix in ['map','side_map','fates']:
            path=DOC/'figures'/f'{figure_prefix}_{site}_ALS.json';meta=read(path)
            assert meta['visual_review']=='PASS',path
            assert meta['reviewed_image_sha256']==sha(path.with_suffix('.png')),path
            if figure_prefix=='map':
                assert {r['variant'] for r in meta['panels']}==set(available[site])|{'analytic'}
                for p in meta['panels']:assert sha(Path(p['source']))==p['sha256']
            figure_files.extend([path,path.with_suffix('.png')])
    section=DOC/'figures/section_B173nb_b10_ALS_0.json';meta=read(section)
    assert meta['visual_review']=='PASS' and set(meta['panels'])==set(VARS)
    for variant,panel in meta['panels'].items():
        assert panel['mesh_sha256']==read(OUT/'patch_z'/f'B173nb_b10__ALS__{variant}_ALS_s0.json')['mesh_sha256']
    figure_files.extend([section,section.with_suffix('.png')])
    report=DOC/report_name
    links=re.findall(r'\]\(([^)]+)\)',report.read_text())
    assert all((report.parent/link).is_file() for link in links if '://' not in link)
    files=[report,DOC/f'tables/{prefix}_values.json',DOC/f'tables/{prefix}_thresholds.json',
           DOC/f'tables/{prefix}_patch_scores.csv',*figure_files,*stop_files]
    record=dict(status='PASS_TWELVE_CONDITION_INTERIM' if expected_stopped else 'PASS_EIGHT_ARM_INTERIM',at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
         intended_arms=len(sites)*4,core_scored_arms=expected_scored,health_stopped_arms=expected_stopped,
         paired_patch_rows=len(data['paired_patch_rows']),threshold_rows=len(thresholds),side_rows=len(data['side_rows']),
         direct_patch_recomputation=True,mesh_hashes_verified=True,cell_0_and_cell_2_separate=True,
         figures_visually_reviewed=len(sites)*3+1,report_local_links=len(links),scientific_verdict=None,
         files=[dict(path=str(p),sha256=sha(p)) for p in files])
    save(DOC/f'tables/{prefix}_verification.json',record)
    check_root='twelve_condition_delivery_v1' if expected_stopped else 'analysis_delivery_priority_v1'
    save(OUT/'checks'/check_root/'verification.json',record)
    print(json.dumps(record,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
