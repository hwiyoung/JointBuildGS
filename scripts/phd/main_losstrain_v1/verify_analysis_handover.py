"""Recompute the delivered core tables using only bytes inside the full ZIP."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile

import numpy as np


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('archive',type=Path)
    ap.add_argument('--receipt',type=Path,required=True)
    a=ap.parse_args()
    with zipfile.ZipFile(a.archive) as z:
        assert z.testzip() is None
        def obj(name):return json.loads(z.read(name))
        def arrays(name):
            with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as v:
                return {k:v[k] for k in v.files}
        for line in z.read('SHA256SUMS').decode().splitlines():
            h,name=line.split('  ',1)
            assert hashlib.sha256(z.read(name)).hexdigest()==h,name
        status=obj('STATUS.json');inventory=obj('run_inventory.json')
        data=obj('docs/tables/twelve_arm_values.json')
        assert len(inventory)==24 and status['requested_interim_verified']==11
        available=[r for r in inventory if r['requested_interim_verified']]
        assert len(available)==11 and all(r['patch_score_available'] for r in available)
        assert {s:sum(r['site']==s for r in available) for s in ['B0_b10','B173nb_b10','R1rep_b10']}=={
            'B0_b10':4,'B173nb_b10':4,'R1rep_b10':3}
        assert len(data['stopped'])==1 and len(data['unscored_analytic_rows'])==10
        assert all(r['trained'] is None for r in data['unscored_analytic_rows'])
        brief=status['analysis_brief'];assert brief in z.namelist()
        for target in re.findall(r'\]\(([^)]+)\)',z.read(brief).decode()):
            if '://' not in target:
                assert str(PurePosixPath(brief).parent/target) in z.namelist(),target
        domains,masks,cache={},{},{}
        def result(site,name):
            key=site,name
            if key not in cache:
                cache[key]=arrays(f'patch_z/{site}__ALS__{name}.npz')
                expected=np.array([f'stage1:{site}:ALS:{i}' for i in range(len(domains[site]['area']))])
                assert np.array_equal(cache[key]['patch_id'],expected),key
            return cache[key]
        for site in ['B0_b10','B173nb_b10','R1rep_b10']:
            root=f'direct_stage1_v2/{site}__ALS/'
            receipt=obj(root+'receipt.json')
            for name in ['evaluation','values']:
                assert hashlib.sha256(z.read(root+name+'.npz')).hexdigest()==receipt[name+'_sha256']
            e=arrays(root+'evaluation.npz');v=arrays(root+'values.npz');domains[site]=e
            eligible=e['in_eval']&e['scoring_allowed']
            both=eligible&e['has_mvs']&(e['cell']<4)
            conflict=np.abs(e['p_mvs'])/np.sqrt(v['sigma_prior'].astype(float)**2+v['sigma_mvs'].astype(float)**2)>3
            m={'all_0_3':both,'unexplained':both&conflict}
            m.update({f'cell_{i}':eligible&(e['cell']==i) for i in range(6)})
            m.update({f'unexplained_cell_{i}':both&conflict&(e['cell']==i) for i in [1,2]})
            masks[site]=m
        checks=0
        for row in data['paired_patch_rows']:
            site=row['site'];e=domains[site];m=masks[site][row['subset']]
            for phase in ['analytic','trained']:
                r=row[phase];q=result(site,r['variant']);depth=q['z']
                area=float(e['area'][m].sum());hit=np.abs(depth-e['p_gt'])<=e['tau'];missing=~np.isfinite(depth)
                assert r['patches']==int(m.sum()) and r['area_m2']==area
                assert r['successful_area_m2']==float(e['area'][m&hit].sum())
                assert r['no_surface_area_m2']==float(e['area'][m&missing].sum())
                assert r['within_tau_percent']==(100*r['successful_area_m2']/area if area else None)
                assert r['no_surface_percent']==(100*r['no_surface_area_m2']/area if area else None)
                valid=m&np.isfinite(depth-e['p_gt'])
                assert r['error_observed_patches']==int(valid.sum())
                assert r['error_patch_median_m']==(float(np.median(np.abs(depth[valid]-e['p_gt'][valid]))) if valid.any() else None)
                checks+=1
        analytic={'lt_fixgt':'fixed_gt','lt_dyngt':'dyn_gt','lt_dynsoft':'dyn_soft','lt_dynnow':'dyn_now'}
        for row in data['side_rows']:
            site=row['site'];e=domains[site];m=masks[site][row['subset']]
            same=result(site,row['variant']+'_ALS_s0')['side']==result(site,'analytic_'+analytic[row['variant']])['side']
            area=float(e['area'][m].sum());matched=float(e['area'][m&same].sum())
            assert row['denominator_patches']==int(m.sum()) and row['denominator_area_m2']==area
            assert row['same_side_area_m2']==matched and row['same_side_percent']==(100*matched/area if area else None)
        thresholds=obj('docs/tables/twelve_arm_thresholds.json')['rows']
        for row in thresholds:
            site=row['site'];e=domains[site];m=masks[site][row['subset']];values=[];ns=[]
            for seed in [0,1]:
                depth=result(site,f'prop_ALS_s{seed}')['z'];err=np.abs(depth-e['p_gt'])
                if row['metric']=='error_patch_median_m':
                    valid=m&np.isfinite(err);n=int(valid.sum());value=float(np.median(err[valid])) if n else None
                else:
                    n=int(m.sum());area=float(e['area'][m].sum())
                    hit=err<=e['tau'] if row['metric']=='within_tau_percent' else ~np.isfinite(depth)
                    value=100*float(e['area'][m&hit].sum())/area if area else None
                assert value==row[f'seed_{seed}'];values.append(value);ns.append(n)
            case=2.8*abs(values[0]-values[1])/math.sqrt(2) if all(v is not None for v in values) else None
            three=None if row['metric']=='error_patch_median_m' or not min(ns) else 300/min(ns)
            assert row['N']==min(ns) and row['case_spread']==case and row['three_points']==three
            parts=[v for v in [row['pooled'],case,three] if v is not None]
            assert row['threshold']==(max(parts) if parts else None)
        assert checks==220 and len(data['side_rows'])==33 and len(thresholds)==63
        receipt=dict(status='PASS_ANALYSIS_HANDOVER',archive=str(a.archive),
            archive_sha256=hashlib.sha256(a.archive.read_bytes()).hexdigest(),
            CRC='PASS',member_hashes='PASS',required_runs=24,verified_scored_arms=11,
            four_variant_units=['B173nb_b10__ALS','B0_b10__ALS'],three_variant_unit='R1rep_b10__ALS',
            stage1_source_receipt_hashes='PASS',recomputed_analytic_and_trained_rows=checks,
            recomputed_same_side_rows=33,recomputed_threshold_rows=63,
            recomputation_inputs='archive bytes only; no live payloads or mesh computation',
            brief_links='PASS',scientific_verdict=None)
    a.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
