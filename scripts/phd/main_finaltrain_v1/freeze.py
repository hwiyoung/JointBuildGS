"""Host-only filesystem/JSON setup. Scientific processing runs in Docker."""
import datetime as dt
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[3]
PH = R.parent / 'JointBuildGS-artifacts/phase-payloads/phd'
O = PH / 'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
C = R / 'configs/phd/main_finaltrain_v1'
D = R / 'docs/experiments/phd/main_finaltrain_v1'
S = R / 'scripts/phd/main_finaltrain_v1'
JA = PH / 'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
TG = PH / 'main_target_v1/PHD-MAIN-TARGET-v1'

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()

def dump(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def main():
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=R, text=True).strip() == 'exp/main-experiment'
    for p in [C, D, O / 'tmp', O / 'logs', O / 'verification', O / 'targets', O / 'stage1']:
        p.mkdir(parents=True, exist_ok=True)
    assert not (C / 'finaltrain_v1.json').exists()
    order = Path('/home/innopam/.codex/attachments/539e1718-7549-45b6-9326-7ef79df683fc/붙여넣은 텍스트.txt')
    shutil.copyfile(order, C / 'order_v1.txt')
    parent = R / 'src/phd/forks/GeoGS-conf-guided-v1-r22'
    fork = R / 'src/phd/forks/GeoGS-conf-guided-v1-r23'
    shutil.copytree(parent, fork, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    bindings = {str(p.relative_to(R)): sha(p) for p in parent.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    dump(C / 'parent_source.lock.json', bindings)
    calib = json.loads((JA / 'calibration.json').read_text())
    thresholds = []
    for site in ['B173nb_b10', 'B0_b10', 'R1rep_b10']:
        p = R / 'docs/experiments/phd/main_judgeapply_v1/tables' / (site + '_photo_thresholds.json')
        thresholds.extend(json.loads(p.read_text())['rows'])
    binary = TG / 'rfix_speed/builds/target/extension/jbgs_rfix_speed_target.so'
    validation = TG / 'rfix_speed/VALIDATION.json'
    assert json.loads(validation.read_text())['status'] == 'PASS'
    assert sha(binary) == json.loads(binary.parent.parent.joinpath('receipt.json').read_text())['extension_sha256']
    config = dict(task_id='PHD-MAIN-FINALTRAIN-v1', scientific_verdict=None,
        created_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip(),
        judgeapply_commit='3962233f', order_sha256=sha(order),
        parent_fork=str(parent.relative_to(R)), fork=str(fork.relative_to(R)),
        sites=['B173nb_b10', 'B0_b10', 'R1rep_b10'], gpu_priors={'0':'ALS', '1':'LoD2'},
        first_pair_delivery_barrier=True, seed=0, iterations=30000,
        checkpoints=[7000,15000,30000], lightweight_log_interval=100,
        renderer=dict(path='/art/phase-payloads/phd/' + str(binary.relative_to(PH)), sha256=sha(binary),
            validation_sha256=sha(validation), binning_guard_fraction=.5),
        frozen_judgment=dict(calibration_sha256=sha(JA/'calibration.json'), sigma_W_m=calib['sigma_W_m'],
            r_rows=calib['r_rows'], photo_thresholds=thresholds, recalibrate=False,
            L='1.96*(sqrt(u_M**2+sigma_P**2+sigma_W**2)+abs(r))', wall_half_length_m=5),
        targets=dict(agreement='(h_P*u_M**2+h_M*sigma_P**2)/(u_M**2+sigma_P**2)',
            agreement_sigma='sqrt(sigma_P**2*u_M**2/(sigma_P**2+u_M**2))',
            preserve_missing='h_P, sigma_P', correct='h_M, u_M', free_space='no target',
            missing_u='photo support->preserve; refute->correct; unknown->ALS preserve / LoD2 correct; correct sigma=scene correction u_M median',
            sigma_W_used=False, r_added=False, outside_timeout_seconds=3600,
            outside_timeout_behavior='unbound background, MVS depth weight 1', GT_used=False),
        weights=dict(power=1, sigma_ref='sum(patch area)/sum(patch area/target sigma)',
            scene_scope='site x prior', clip=[.1,10], background=1, exclude_background_from_sigma_ref=True),
        unchanged=dict(depth_loss='absolute', depth_lambda=.05, reattach_tangent_m=.5,
            reattach_normal_excess_m=.5, band_sigma=1.96, background_bound=False,
            photo_loss=True, two_dgs_terms=True, optimizer=True, density_schedule=True,
            opacity_reset=True, initialization='r8 exact source and exclusion rule'),
        health=dict(iteration=7000, loss_finite=True, prior_descendant_opacity_median_min=.05,
            count_reference=6000, count_growth_max=3, count_check_until=15000,
            other_metrics_record_only=True, independent_arm_stop=True),
        retry=dict(execution_or_oom=1, same_config=True, health=0),
        scorer='PHD-MAIN-RESCORE-v1 when ready, otherwise explicitly provisional r8',
        crs='EPSG:25832', payload_root=str(O), output_paths=[str(p.relative_to(R)) for p in [C,S,D,fork]]+[str(O)],
        docker_images={name:subprocess.check_output(['docker','image','inspect','-f','{{.Id}}',name],text=True).strip()
            for name in ['jointbuildgs:dev','jointbuildgs:geogs-conf-guided-v1']})
    dump(C/'finaltrain_v1.json', config)
    dump(C/'finaltrain_v1.initial.lock.json', dict(at=config['created_at'],config_sha256=sha(C/'finaltrain_v1.json'),scientific_verdict=None))
    (D/'progress.md').write_text('# PHD-MAIN-FINALTRAIN-v1 진행\n\n- '+config['created_at']+': 설정 첫 잠금. r22 사본 r23 생성. B173 주변 먼저. scientific_verdict: null.\n')
    (D/'issues.md').write_text('# 실행 문제 기록\n\n')
    dump(O/'initial_git_status.json',dict(status=subprocess.check_output(['git','status','--porcelain'],cwd=R,text=True),scientific_verdict=None))
    print(json.dumps(dict(config_sha256=sha(C/'finaltrain_v1.json'),fork=str(fork),output=str(O)),indent=2))

if __name__ == '__main__': main()
