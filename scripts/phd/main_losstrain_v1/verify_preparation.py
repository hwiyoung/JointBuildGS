"""Close the preparation gate using completed receipts, without rerunning trainings."""
import json
from pathlib import Path
from inputs import OUT,SITES,PRIORS,save,sha

def main():
    checks={}
    for site in SITES:
        for prior in PRIORS:
            current=OUT/f'checks/current_direct_v1/comparison_{site}_{prior}.json'
            depth=OUT/f'checks/depth_direct_v2/{site}_{prior}/probe/depth_masks.json'
            c=json.loads(current.read_text());d=json.loads(depth.read_text())
            assert c['status']=='PASS' and d['status']=='PASS' and d['optimizer_steps']==0
            checks[site+'/'+prior]=dict(current_sha256=sha(current),depth_sha256=sha(depth))
    cfg=Path('/config/losstrain_v1.json');config=json.loads(cfg.read_text())
    assert sha(cfg)==json.loads(cfg.with_suffix('.lock.json').read_text())['sha256']
    for path,key in [('direct_stage1_v2/gates.json','gate'),('checks/loss_cpu.json','gate'),('checks/direct_stage1/monitor_check.json','status'),('checks/lambda_selection.json','status'),('checks/rebuild_final_r17/docs/rebuild.json','status')]:
        assert json.loads((OUT/path).read_text())[key]=='PASS',path
    assert config['lambda_selection']['selected_lambda'] is not None
    assert not (OUT/'checks/calibration_STOP.json').exists()
    start=json.loads((OUT/'checks/calibration_start.json').read_text())
    for source,digest in start['source_sha256'].items():assert sha(Path('/repo')/source)==digest,source
    source_root=Path('/repo/src/phd/forks');r16=source_root/'GeoGS-conf-guided-v1-r16';r17=source_root/'GeoGS-conf-guided-v1-r17'
    files=lambda root:sorted(p.relative_to(root) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    assert files(r16)==files(r17)
    changed=[str(p) for p in files(r17) if sha(r16/p)!=sha(r17/p)]
    assert changed==['jbgs_judgment.py','train.py'],changed
    result=dict(status='PASS',units=checks,config_sha256=sha(cfg),calibration_runs=4,selected_lambda=config['lambda_selection']['selected_lambda'],
        changed_fork_files=changed,fork_file_count=len(files(r17)),fork_hashes={str(p):sha(r17/p) for p in files(r17)},
        gradient_limitation='zero-inclusive medians both zero; ratio undefined; recorded frozen direct inequality applied',
        scientific_verdict=None)
    save(OUT/'checks/preparation_PASS.json',result);save('/docs/provenance/preparation_PASS.json',result)
    save('/docs/provenance/rebuild_final_r17.json',json.loads((OUT/'checks/rebuild_final_r17/docs/rebuild.json').read_text()))
    print('preparation PASS',len(checks),'units;',4,'short runs; lambda',result['selected_lambda'],flush=True)

if __name__=='__main__':main()
