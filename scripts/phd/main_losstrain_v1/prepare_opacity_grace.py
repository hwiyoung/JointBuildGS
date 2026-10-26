"""Freeze the user-authorized monitoring change and exact historical comparison values."""
import json
from pathlib import Path
from inputs import OUT,PH,SITES,PRIORS,save,sha

def main():
    root=OUT/'checks/opacity_grace_v1'
    approval=json.loads((root/'approval.json').read_text());assert approval['status']=='AUTHORIZED'
    medians={}
    for site in SITES:
        for prior in PRIORS:
            p=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/('nojudge_'+prior+'_s0')/'model/monitor/scalars.jsonl'
            rows=[json.loads(x) for x in p.read_text().splitlines()]
            values={str(x['iteration']):x['opacity_q_prior'][1] for x in rows if x['iteration'] in [3100,6100,9100,12100]}
            assert len(values)==4
            obj=dict(site=site,prior=prior,source=str(p),source_sha256=sha(p),medians=values,
                observation_phase='after optimizer and opacity floors, before density/reset',scientific_verdict=None)
            save(root/'nojudge'/f'{site}__{prior}.json',obj);medians[site+'__'+prior]=obj
    save('/docs/tables/opacity_reset_nojudge.json',medians)
    config=Path('/config/losstrain_v1.json');cfg=json.loads(config.read_text())
    amendment=dict(approved=True,grace_offsets_inclusive=[1,99],resume_check_offset=100,
        median_stop_below=.05,trigger='actual periodic reset only',nonfinite_and_other_errors='immediate stop',
        observation_phase='after optimizer and opacity floors, before density/reset',
        comparison='same unit nojudge at each reset +100 iteration',restart='two stopped arms from seed 0',
        source_approval_sha256=sha(root/'approval.json'),calibration_reused=True,lambda_unchanged=.0025)
    assert cfg.get('opacity_reset_amendment',amendment)==amendment
    cfg['opacity_reset_amendment']=amendment
    save(config,cfg);lock=json.loads(Path('/config/losstrain_v1.lock.json').read_text());lock['sha256']=sha(config)
    lock['amendment']='user-approved opacity reset grace v1';save('/config/losstrain_v1.lock.json',lock)
    receipts=json.loads((OUT/'checks/mesh_baselines.json').read_text())['results'];assert len(receipts)==30
    for r in receipts:
        p=OUT/'patch_z'/(r['site']+'__'+r['prior']+'__'+r['result']+'.npz')
        assert sha(p)==r['patch_z_sha256'],p
    save(root/'baseline_completion.json',dict(status='PASS',mesh_results=30,
        fates_results=sum(json.loads(p.read_text())['status']=='PASS' for p in (OUT/'fates').rglob('*.json')),
        wrapper_log_failure='Old running shell was edited while awaiting Docker; trailing shell fragment failed. All 30 mesh outputs and hashes verified; no computation rerun.',scientific_verdict=None))
    print('opacity grace frozen; 24 historical comparison values; 30 mesh outputs verified')

if __name__=='__main__':main()
