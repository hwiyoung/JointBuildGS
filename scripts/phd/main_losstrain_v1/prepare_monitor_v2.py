"""Freeze the user's latest monitoring policy; host stdlib, no training."""
import json
from train_calibration import OUT,REPO,save,sha,now

def main():
    root=OUT/'checks/monitor_v2'
    approval=json.loads((root/'approval.json').read_text())
    if approval['status']!='AUTHORIZED':
        save(root/'approval_before_clarification.json',approval)
    approval.update(status='AUTHORIZED',clarified_at=now(),
        psnr_gate_iterations=[7000,15000,30000],psnr_views='same historical five cameras and CHW calculation',
        nojudge_retraining=False,nojudge_saved_model_comparisons=[15000,30000],
        nojudge_other_iterations='기록 없음',fixed_inflight='continue; recover available logs and saved models; mark missing',
        recording_choice='same historical five training cameras at every new diagnostic observation; all-training-view final readout remains separate',
        missing_birth_tags='historical models and inflight fixed have lineage tags only; three-way birth statistics unavailable, retain exact lineage and GT-group summaries',
        user_no_further_format_questions=True,
        superseded_stops={str(p.relative_to(OUT)):sha(p) for p in [OUT/'checks/full_STOP.json',OUT/'checks/full_grace_STOP.json']})
    save(root/'approval.json',approval)
    save(REPO/'docs/experiments/phd/main_losstrain_v1/provenance/monitor_v2_approval.json',approval)
    inventory=json.loads((root/'baseline_inventory.json').read_text())
    for r in inventory['rows']:
        save(root/'nojudge'/(r['site']+'__'+r['prior']+'.json'),r)
    path=REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json'
    cfg=json.loads(path.read_text())
    cfg['monitor_v2_amendment']=dict(source_approval_sha256=sha(root/'approval.json'),
        prior_opacity='record only',whole_opacity_threshold=.05,whole_opacity_check='each iteration at or after actual periodic reset +100',
        psnr_drop_stop_strictly_above_db=3.,psnr_gate_iterations=[7000,15000,30000],
        diagnostic_psnr='legacy fixed five training views, identical historical calculation',
        nojudge_retrained=False,diagnostic_GT='CPU sidecar only; never used by loss or stop',
        lambda_unchanged=.0025,calibration_reused=True)
    save(path,cfg);lock=json.loads(path.with_suffix('.lock.json').read_text())
    lock.update(sha256=sha(path),amendment='user-approved whole-population and legacy-five-view monitor v2')
    save(path.with_suffix('.lock.json'),lock)
    print('monitor v2 approval, six nojudge references and config frozen')

if __name__=='__main__':main()
