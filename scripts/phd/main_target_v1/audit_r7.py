"""Audit delivered evidence separately from the experimental gate result."""
import ast,re
from common import *
def read(p):return json.loads(p.read_text())
def main():
    count=0
    for name in ['fork_r21_base.json','target_v1.runtime.r7.lock.json']:
        for path,h in read(CFG/name)['files'].items():assert sha(REPO/path)==h,path;count+=1
    for name in ['target_v1.r7','target_v1.r7.stage0']:assert sha(CFG/(name+'.json'))==read(CFG/(name+'.lock.json'))['config_sha256']
    assert sha(CFG/'baseline7k.r7.json')==read(CFG/'baseline7k.r7.lock.json')['sha256']
    for path,h in read(CFG/'baseline7k.r7.json')['source_files'].items():assert sha(REPO/path)==h;count+=1
    for file,status in [('unit','PASS_R7_UNIT'),('runtime','PASS_R7_SOURCE_AND_INPUTS'),('stage0','PASS_DISAPPEARANCE_VOTES_AND_REPLAY'),('core','PASS_CORE_VOTES_UNIT_MEDIANS_AND_PUBLIC_AGGREGATES'),('initial','PASS_R7_INITIALIZATION'),('baseline_source','PASS_HISTORICAL_BASELINE_SOURCE_AND_SEED')]:assert read(OUT/'r7/verification'/(file+'.json'))['status']==status
    rows=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7';base=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0';s=read(run/'post7000/score.json');b=read(base/'post7000/score.json');v=read(run/'verification7000.json');bv=read(base/'verification7000.json')
        assert read(base/'receipt.json')['status']=='COMPLETE_7000' and b['status']=='BASELINE_7000_COMPLETE';assert v['status']=='PASS_R7_SAVED_EVIDENCE_RECOUNT' and bv['status']=='PASS_BASELINE_SAME_R7_PIXEL_TARGETS'
        for k in v['strata']:assert v['strata'][k]['target_pixels']==bv['strata'][k]['target_pixels']
        for root in [base,run]:
            verify=read(root/'verification_post7000.json');assert verify['status']=='PASS_POST7000_RECOUNT_AND_RAYS' and sha(root/'post7000/score.json')==verify['score_sha256']
        assert read(run/'verification_diagnostics.json')['status']=='PASS_R7_DIAGNOSTIC_RECOUNT';assert read(run/'origin_ratio.json')['status']=='PASS_CONTRIBUTION_DENOMINATORS'
        full=read(run/'verification_full_state.json');assert full['rows'][0]['status']=='PASS_COMPLETE_STATE'
        assert s['thresholds']==dict(floating_max=b['floating_fraction_cells_0_3']+.02,agreement_min=b['agreement_within_tau_fraction']-.02,no_surface_max=b['no_surface_fraction_cells_0_3']+.01)
        assert s['status']==('PASS' if all(s['gates'].values()) else 'FAIL');assert read(run/'launch.json')['config_sha256']==sha(CFG/'target_v1.r7.json')
        health=[json.loads(line) for line in (run/'model/target_monitor/curve.jsonl').read_text().splitlines() if json.loads(line)['iteration']<=7000]
        for r in health:assert r['opacity_check_skipped_reset_grace']==(r['last_opacity_reset']>=0 and 0<=r['iteration']-r['last_opacity_reset']<=500)
        rows.append(dict(prior=prior,status=s['status'],gates=s['gates'],thresholds=s['thresholds'],saved_complete_states=[r['iteration'] for r in full['rows'] if r['status']=='PASS_COMPLETE_STATE']))
    figures=[]
    for p in sorted((DOC/'figures').glob('r7_*.png')):
        side=read(p.with_suffix('.json'));assert side['scientific_verdict'] is None;figures.append(dict(file=p.name,sha256=sha(p)))
    assert len(figures)>=50
    visual=read(DOC/'tables/visual_review_r7.json');assert {r['file']:r['sha256'] for r in visual['figures']}=={r['file']:r['sha256'] for r in figures}
    for name in ['단계0_사라짐_점검_r7.md','단계1_7000회_점검_r7.md','초기배경_크기_r7.md','영역별목표학습_보고_v1.md']:
        p=DOC/name
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if '://' not in target and not target.startswith('#'):assert (p.parent/target).exists(),(name,target)
    body=(DOC/'영역별목표학습_보고_v1.md').read_text();assert len(body)<20000 and len(re.findall(r'^## [1-8]\. ',body,re.M))==8
    for root in [REPO/'scripts/phd/main_target_v1',REPO/'src/phd/forks/GeoGS-conf-guided-v1-r21']:
        for p in root.rglob('*.py'):ast.parse(p.read_text())
    passed=all(r['status']=='PASS' for r in rows);stopped=(OUT/'r7/STOP_BOTH.json').exists();state='PASS_R7_7000' if passed else 'STOP_R7_7000'
    if not passed:
        assert stopped
        assert sorted(p.name for p in (OUT/'r7/runs').iterdir() if p.is_dir())==['tg_B173nb_b10_ALS_s0_r7','tg_B173nb_b10_LoD2_s0_r7']
        for prior in ['ALS','LoD2']:assert read(OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7/receipt.json')['status']=='STOPPED'
    if stopped and passed:state='PASS_R7_7000_LATER_TRAINING_STOP'
    result=dict(at=stamp(),status='PASS_R7_DELIVERY_AUDIT',experiment_status=state,rows=rows,locked_files_checked=count,figure_pairs=len(figures),scientific_verdict=None)
    dump(DOC/'tables/final_audit_r7.json',result);dump(OUT/'r7/final_audit.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
