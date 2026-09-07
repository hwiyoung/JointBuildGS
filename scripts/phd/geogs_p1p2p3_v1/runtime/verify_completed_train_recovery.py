"""Docker-only, read-only verification for the two P1 launcher-EOF recoveries."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time

TASK = 'PHD-GEOGS-P1P2P3-v1'
CONFIG = 'b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4'
LAYOUT = '28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5'
INPUT = '3257b3604f630a64948606605c3ae46f2e22d4d5829b5ad49a7d46b342a42112'
IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
EXPECTED = {
    'D005_Pnative': ('d6956aa2b61d5cc48eeba06edf8e7b6f4861049c9952b1be362e8114a17b845b',
                    'b0a3a0ba349dffa47fdb0f62615a7b3b164b9975a238037015e805758b51a4ea'),
    'D0005_Pnative': ('31b89c860747cefc02611a89b18b920fd1202ee64dcb121dfc97f4763a6e48b5',
                     'a8c1ef1b6f0520fb8a726014a4a57f91868f3867a8434a34fcaf3e5e184fec2d'),
}
PHASES = ('train', 'render', 'metrics', 'auxiliary')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def run_file(root, name):
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()), 'Artifact escapes run: ' + name)
    require(path.is_file() and path.stat().st_size > 0, 'Missing nonempty artifact: ' + name)
    return path


def verify_phase(root, condition, phase, source_hashes):
    path = run_file(root, phase + '_receipt.json')
    receipt = json.loads(path.read_text())
    expected = dict(task_id=TASK, region='P1', condition=condition, phase=phase,
                    status='PASS', native_exit_code=0, validated_exit_code=0,
                    config_sha256=CONFIG, input_manifest_sha256=INPUT,
                    runtime_layout_sha256=LAYOUT, runtime_revision='allocator_v2',
                    runtime_image_id=IMAGE, scientific_verdict=None)
    require(all(receipt.get(k) == v for k, v in expected.items()), 'Phase identity/status differs: ' + phase)
    require(not receipt.get('repeat_id'), 'Recovery must retain primary identity')
    require(receipt['implementation_hashes'] == source_hashes, 'Scientific source changed: ' + phase)
    invocation = json.loads(run_file(root, phase + '_invocation.json').read_text())
    require(all(receipt.get(k) == v for k, v in invocation.items()), 'Invocation/receipt differs: ' + phase)
    for name, digest in ((phase + '_driver_snapshot.py', receipt['driver_sha256']),
                         (phase + '_config_snapshot.json', CONFIG),
                         (phase + '_runtime_layout_snapshot.json', LAYOUT)):
        require(sha(run_file(root, name)) == digest, 'Snapshot changed: ' + name)
    extraction = receipt.get('extraction_helper_snapshot')
    if extraction:
        require(sha(run_file(root, extraction['path'])) == extraction['sha256'], 'Extraction helper changed')
    scheduling = receipt.get('resource_scheduling', {})
    if scheduling.get('helper_snapshot_path'):
        require(sha(run_file(root, scheduling['helper_snapshot_path'])) == scheduling['helper_sha256'],
                'Scheduling helper changed')
    require(receipt['environment'].get('PYTORCH_CUDA_ALLOC_CONF') == 'backend:native,max_split_size_mb:128',
            'Allocator changed')
    bound = {}
    for row in receipt['validation']:
        if 'sha256' not in row:
            continue
        artifact = run_file(root, row['path'])
        require(row.get('exists_nonempty') is True and artifact.stat().st_size == row['bytes'],
                'Artifact size differs: ' + row['path'])
        digest = sha(artifact)
        require(digest == row['sha256'], 'Artifact hash differs: ' + row['path'])
        bound[row['path']] = digest
    require(bound, 'No verified phase artifacts: ' + phase)
    if phase == 'train':
        checkpoint, ply = EXPECTED[condition]
        fixed = {'model/jbgs_complete/iteration_30000/checkpoint.pth': checkpoint,
                 'model/jbgs_complete/iteration_30000/point_cloud.ply': ply,
                 'model/point_cloud/iteration_30000/point_cloud.ply': ply}
        require(bound == fixed, 'Completed train bytes differ from the observed successful run')
        meta_path = run_file(root, 'model/jbgs_complete/iteration_30000/receipt.json')
        meta = json.loads(meta_path.read_text())
        require(meta.get('iteration') == 30000 and meta.get('after_protection_registration') is True
                and meta.get('checkpoint_sha256') == checkpoint and meta.get('ply_sha256') == ply
                and meta.get('scientific_verdict') is None, 'Complete-state receipt differs')
        require(receipt.get('training_start_iteration') == 8000, 'Training start differs')
        command = receipt['command']
        require(command[command.index('--jbgs_resume_full') + 1] == '/anchor/checkpoint.pth'
                and command[command.index('--iterations') + 1] == '30000'
                and '--jbgs_release_protection' not in command, 'Training controls differ')
        bound[str(meta_path.relative_to(root))] = sha(meta_path)
    return {'receipt_sha256': sha(path), 'artifacts': bound,
            'started_unix': receipt['started_unix'], 'finished_unix': receipt['finished_unix']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--condition', choices=EXPECTED, required=True)
    parser.add_argument('--mode', choices=('preflight', 'complete'), required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker is required')
    require(not Path('/artifacts/JointBuildGS').exists() and not Path('/reference').exists(),
            'No reference or broad artifact mount is permitted')
    require(sha('/config.json') == CONFIG and sha('/runtime_layout.json') == LAYOUT
            and sha('/input_manifest.json') == INPUT, 'Frozen contracts/input identity differ')
    root = Path('/run')
    source = Path('/source')
    source_hashes = {str(p.relative_to(source)): sha(p) for p in sorted(source.rglob('*.py'))
                     if 'submodules' not in p.parts}
    phases = {}
    for phase in PHASES:
        if (root / (phase + '_receipt.json')).exists():
            phases[phase] = verify_phase(root, args.condition, phase, source_hashes)
        else:
            require(phase != 'train' and args.mode != 'complete', 'Required phase receipt absent: ' + phase)
            require(not list(root.glob(phase + '_*')) and not (root / (phase + '.log')).exists(),
                    'Partial phase artifacts require separate recovery; refusing overwrite: ' + phase)
    require('train' in phases, 'Verified train is required')
    missing = [phase for phase in PHASES if phase not in phases]
    require(missing == list(PHASES[len(phases):]), 'Existing successful phases must form an ordered prefix')
    archive = Path('/launcher_archive')
    launcher = archive / 'run_regional_phase_before_exec.sh'
    stat_text = (archive / 'launcher_stat_before_exec.txt').read_text().strip()
    stat_fields = stat_text.split()
    require(len(stat_fields) == 5 and stat_fields[0].endswith('/run_regional_phase.sh'),
            'Unexpected archived launcher stat format')
    clock = stat_fields[2].split('.')
    timezone = stat_fields[3][:3] + ':' + stat_fields[3][3:]
    iso = stat_fields[1] + 'T' + clock[0] + '.' + clock[1][:6] + timezone
    launcher_mtime = datetime.fromisoformat(iso).timestamp()
    require(int(stat_fields[4]) == launcher.stat().st_size, 'Archived launcher size differs')
    train = phases['train']
    evidence = dict(launcher_sha256=sha(launcher), launcher_mtime_unix=launcher_mtime,
                    original_launcher_stat=stat_text, archived_copy_mtime_unix=launcher.stat().st_mtime,
                    launcher_stat_sha256=sha(archive / 'launcher_stat_before_exec.txt'),
                    launcher_mtime_within_train=(train['started_unix'] < launcher_mtime < train['finished_unix']),
                    explanation='Live launcher mutation is supported; the former shell FD offset was not captured.')
    require(Path('/recovery/original_failed_marker').read_text().strip() == '2', 'Unexpected original exit code')
    original_log = Path('/recovery/original_claim_run.log').read_text()
    require('unexpected EOF while looking for matching' in original_log and '"status": "PASS"' in original_log,
            'Original failure is not the observed post-PASS launcher EOF')
    if args.mode == 'complete':
        before = json.loads(Path('/recovery/preflight.json').read_text())
        require(all(phases[k] == v for k, v in before['phases'].items()),
                'A previously successful phase changed during recovery')
    result = dict(schema='GEOGS_COMPLETED_TRAIN_LAUNCHER_RECOVERY_v1', task_id=TASK,
                  region='P1', condition=args.condition, mode=args.mode, status='PASS',
                  phases=phases, missing_phases=missing, launcher_evidence=evidence,
                  original_failure_sha256=sha('/recovery/original_failed_marker'),
                  original_claim_log_sha256=sha('/recovery/original_claim_run.log'),
                  verifier_sha256=sha(__file__), checked_unix=time.time(), scientific_verdict=None)
    destination = Path('/recovery') / (args.mode + '.json')
    with destination.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(status='PASS', condition=args.condition, mode=args.mode, missing_phases=missing)))


if __name__ == '__main__':
    main()
