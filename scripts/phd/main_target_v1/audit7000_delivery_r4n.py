"""Final delivery checks; evidence validity is distinct from the failed scientific gate."""
import ast,re
from common import *

def read(p):return json.loads(p.read_text())
def main():
    config=CFG/'target_v1.stage1.r4n.json';lock=read(CFG/'target_v1.runtime.r4n.lock.json')
    assert sha(config)==lock['config_sha256']==sha(CFG/'target_v1.json')
    checks=0
    for name in ['target_v1.runtime.r4n.lock.json','execution_r4n.code.lock.json']:
        for path,digest in read(CFG/name)['files'].items():assert sha(REPO/path)==digest,path;checks+=1
    rows=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0'
        v=read(run/'verification7000.json');p=read(run/'verification_post7000.json');score=read(run/'post7000/score.json')
        assert v['status']=='PASS_SAVED_EVIDENCE_RECOUNT' and p['status']=='PASS_POST7000_RECOUNT_AND_RAYS'
        assert v['views']==203 and v['coverage']<.8
        assert sha(run/'model/target_monitor/snapshot_7000.npz')==v['snapshot_sha256']
        assert sha(run/'model/check7000/coverage.json')==v['coverage_sha256']
        assert sha(run/'post7000/score.json')==p['score_sha256']
        assert read(run/'receipt.json')['status']=='STOPPED'
        assert not (run/'model/point_cloud/iteration_30000').exists()
        assert read(run/'launch.json')['config_sha256']==lock['config_sha256']
        rows.append(dict(prior=prior,saved_iteration=7000,target_following=v['coverage'],floating=score['floating_fraction_cells_0_3'],
            validation='PASS',pilot_acceptance='FAIL_TARGET_FOLLOWING',scientific_verdict=None))
    figure_pairs=0
    for p in (DOC/'figures').glob('*.png'):
        assert p.with_suffix('.json').exists(),p;read(p.with_suffix('.json'));figure_pairs+=1
    report=DOC/'영역별목표학습_보고_v1.md';body=report.read_text()
    assert len(body)<20000 and len(re.findall(r'^## [1-8]\. ',body,flags=re.M))==8
    for document in [report,DOC/'단계1_7000회_점검_r4n.md',DOC/'중단후_비교진단_r5.md',DOC/'자리별_판단점검_r5.md']:
        for target in re.findall(r'\]\(([^)]+)\)',document.read_text()):
            if '://' not in target and not target.startswith('#'):assert (document.parent/target).exists(),(document,target)
    parsed=0
    for folder in [REPO/'scripts/phd/main_target_v1',REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19']:
        for p in folder.rglob('*.py'):ast.parse(p.read_text());parsed+=1
    visual=read(DOC/'tables/visual_review_7000_r4n.json')
    for row in visual['figures']:assert sha(DOC/'figures'/row['file'])==row['sha256'],row['file']
    r5=read(DOC/'tables/verification_r5.json');assert r5['status']=='PASS_R5_INDEPENDENT_RECOUNT' and r5['place_rows_checked']==1800
    for prior in ['ALS','LoD2']:
        assert read(OUT/'r5'/f'resume_audit_{prior}.json')['status']=='NOT_RUN_NO_OPTIMIZER_STATE'
        assert read(OUT/'r5/failures'/prior/'summary.json')['status']=='PASS_INDIVIDUAL_MAX_CONTRIBUTOR'
        assert read(OUT/'r5/movement'/prior/'summary.json')['origins']['prior']['tangent_over_1m']>0
    for name,digest in read(CFG/'diagnostics_r5.lock.json')['files'].items():assert sha(CFG/name)==digest
    requirements=dict(input_rules_and_targets_locked='PASS',no_gt_parameter_selection='recorded sources and locks',
        target_off_equivalence='PASS_DEFAULT_OFF_AST',initialization_gate='PASS_USER_DECISION_20261101_R3',
        pilot7000='FAIL_TARGET_FOLLOWING_BOTH_STOPPED',large_background_ancestry='RECORDED_NONSTOP',
        initial_opacity='0.1 BOTH_ORIGINS_EQUAL_BASELINE',remaining_six_and_30000='NOT_RUN',
        direct_target_mesh_and_final_comparisons='NOT_RUN_PILOT_STOP',saved_baseline_same_map_comparison='PASS_3_MODELS_4_COMPARISONS',individual_contributor='PASS_406_BYTE_EQUAL_DEPTH_REPLAYS',both_origin_movement='COMPLETE',place_stratification='PASS_1800_ROWS',record_only_continuation='NOT_RUN_NO_OPTIMIZER_STATE',holdout_patch_details='EXCLUDED_FROM_PUBLIC_DELIVERY')
    record=dict(at=stamp(),status='PASS_DELIVERY_AUDIT',experiment_status='STOP_7000_TARGET_COVERAGE',rows=rows,
        requirements=requirements,locked_files_checked=checks,python_files_parsed=parsed,figure_pairs=figure_pairs,
        r5_verification_sha256=sha(DOC/'tables/verification_r5.json'),report_characters=len(body),report_sha256=sha(report),visual_review_sha256=sha(DOC/'tables/visual_review_7000_r4n.json'),scientific_verdict=None)
    dump(OUT/'r4n/final_delivery_audit.json',record);dump(DOC/'tables/final_7000_audit_r4n.json',record)
    print('DELIVERY_AUDIT_PASS',rows,flush=True)

if __name__=='__main__':main()
