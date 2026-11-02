"""Freeze direct user reply 1 before resuming development calculations."""
import json
from preflight import C,O,Path,dump,sha,now

def main():
    dest=C/'judgecheck_v1.reply1.lock.json'
    if dest.exists():
        assert sha(C/'judgecheck_v1.json')==json.loads(dest.read_text())['config_sha256'];return
    p=C/'judgecheck_v1.json';cfg=json.loads(p.read_text());old=sha(p)
    assert old==json.loads((C/'judgecheck_v1.initial.lock.json').read_text())['config_sha256']
    previous=C/'revisions/r0/judgecheck_v1.json';previous.parent.mkdir(parents=True,exist_ok=True)
    assert not previous.exists();previous.write_bytes(p.read_bytes())
    cfg['amendments'].append(dict(at=now(),authority='reply_1.txt',authority_at='2026-11-02T23:10:00+09:00',
        authority_sha256=sha(C/'reply_1.txt'),previous_config_sha256=old,
        reason='Direct user reply: remove shared-photo cores before every calculation and audit all point memberships',
        full_text=(C/'reply_1.txt').read_text()))
    cfg['scope'].update(shared_photo_policy='exclude from ALL calculations before geometry and calibration',
        all_member_ID_audit=True,audit_kinds=['ALS_roof','LoD2_roof','LoD2_wall'],
        stage_a_forbidden_members=['experiment','holdout'],stage_b_forbidden_members=['development','experiment'],
        stage_b_requires_new_user_reply=True,raw_neighbourhood_samples_authorized=True,
        baseline_excluded_core_count=73,baseline_excluded_area_m2=5.442552935831812,
        exclusion_manifest='/out/r1/scope_audit.json')
    cfg['execution'].update(current_payload='/out/r1',
        never_consume_initial_preparation=['/out/inputs','/out/photo_inputs'],
        package_exclude=['initial preparation','source_snapshots/initial_join','initial shared curves'],
        table_exclusion_line_required=True,initial_22_shared_curves_exception_retained=True,
        initial_22_shared_curves_contribute_no_values=True)
    dump(p,cfg);dump(dest,dict(at=now(),config_sha256=sha(p),authority_sha256=sha(C/'reply_1.txt'),
        before_resumed_calculation=True,scientific_verdict=None))
    (O/'r1').mkdir(exist_ok=True)
    print('REPLY1_LOCK',sha(p))

if __name__=='__main__':main()
