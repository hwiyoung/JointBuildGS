"""Host stdlib: lock r7 stage-0 and training rules before any new judgment."""
import datetime as dt,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'configs/phd/main_target_v1';O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat();assert not (C/'target_v1.r7.json').exists()
    base=R/'src/phd/forks/GeoGS-conf-guided-v1-r20';new=base.with_name('GeoGS-conf-guided-v1-r21');shutil.copytree(base,new,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    put(C/'fork_r21_base.json',dict(at=at,base_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),files={str(p.relative_to(R)):sha(p) for p in sorted(base.rglob('*')) if p.is_file() and '__pycache__' not in p.parts},scientific_verdict=None))
    spec=dict(at=at,revision='r7',authority='decision_20261101_r7.md and direct user pixel uncertainty reply',
        parent_config='revisions/r2/target_v1.json',parent_config_sha256=sha(C/'revisions/r2/target_v1.json'),
        unchanged=['T2','detection limit','photo judgment','all non-unobserved labels/targets/sigma','GT evaluation only'],
        eligible_region=0,new_region=5,new_region_name='disappeared',new_target_valid=False,
        projection=dict(views='training only, inherited calibrated MVS pixel grid',depth_range_m=[.2,300.],window=[3,3],pixel_rounding='nearest integer, np.rint',edge='valid in-image samples only',
            depth='median finite positive confidence-masked MVS depths in window',uncertainty='median per-valid-pixel sigma_M in same window',empty='no evidence'),
        pixel_uncertainty=dict(query='unproject each valid MVS pixel using its own depth and K/W2C; nearest stage-0 registered patch centre in same unit/prior',radius_m=1.,ties='lowest patch index',
            u='nearest patch frozen u only if not replaced and finite',fallback='median finite original frozen u over same unit/prior; no cross-unit transfer',floor_m=.0275,
            sigma_m='sqrt(u*u+0.0275**2)',sigma_p='tested patch frozen sigma_p',margin='1.96*sqrt(sigma_M**2+sigma_P**2)',
            fallback_records=['valid window samples','no neighbour','replaced neighbour','missing u','patch-view windows using any fallback'],
            reference_only='tested patch frozen u; identical depth/window/vote rule, not used for decisions'),
        vote=dict(through='D_M > D_P + m',occluded='D_M < D_P - m',surface='abs(D_M-D_P)<=m',required_through=2,through_fraction_strictly_greater_than=.5),
        output=dict(remove=['target point','seed','disc'],background='unchanged existing MVS seeds and scope; uncovered pixels use inherited MVS target',
            accuracy='GT within inherited tau of prior surface; unavailable truth stays unavailable; all-keep and all-delete comparisons',holdout='only count/area/ratio public'),scientific_verdict=None)
    put(C/'target_v1.r7.stage0.json',spec);put(C/'target_v1.r7.stage0.lock.json',dict(at=at,config_sha256=sha(C/'target_v1.r7.stage0.json'),authority_sha256=sha(C/'decision_20261101_r7.md'),scientific_verdict=None))
    d=json.loads((C/'target_v1.r6.json').read_text());d['revision']='r7';d['created_at']=at
    d['training'].update(base_candidate=base.name,new_fork=new.name,switch='--jbgs_target on --jbgs_target_rev r7')
    d['r7']=dict(stage0_config_sha256=sha(C/'target_v1.r7.stage0.json'),supersedes=['r6 nearest_target Euclidean radius','r6 fixed geometry gates','r6 reset opacity monitoring'],
        candidate=dict(tangent_max_m=.5,normal_distance_beyond_width_max_m=.5,width='1.96*sigma',order=['tangent distance','normal excess beyond width','original patch index'],precision='float64',projection_max_m=.5,roundoff_m=3e-5),
        cadence='clone/split/prune immediately and every100 through30000',eligible='current patch only; released permanent',
        opacity_grace='actual periodic reset iteration and following 500 iterations inclusive; do not skip NaN/count/memory checks',
        gates=dict(health='inherited with opacity grace',floating_max='same-prior base7k+0.02',agreement_min='same-prior base7k-0.02',no_surface_max='same-prior base7k+0.01',both_required=True),
        baseline_config_sha256=sha(C/'baseline7k.r7.json'),full_state_iterations=[7000,15000,30000],
        wait_at_7000_if_baseline_missing=True,continue_while_scoring_if_baseline_ready=True,
        result_names=['tg_B173nb_b10_ALS_s0_r7','tg_B173nb_b10_LoD2_s0_r7'],scientific_verdict=None)
    d['amendments'].append(dict(at=at,previous_config_sha256=sha(C/'target_v1.r6.json'),reason='User r7 and pixel uncertainty decision; historical sections retained, r7 explicitly overrides conflicts'))
    put(C/'target_v1.r7.json',d);put(C/'target_v1.r7.lock.json',dict(at=at,config_sha256=sha(C/'target_v1.r7.json'),stage0_config_sha256=sha(C/'target_v1.r7.stage0.json'),base_manifest_sha256=sha(C/'fork_r21_base.json'),scientific_verdict=None))
    for p in ['r7/verification','r7/stage0','r7/targets','r7/stage1','holdout/r7/stage0']:(O/p).mkdir(parents=True,exist_ok=True)
    print('R7_LOCKED',at,sha(C/'target_v1.r7.stage0.json'),sha(C/'target_v1.r7.json'))
if __name__=='__main__':main()
