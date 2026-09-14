"""Freeze, verify and gate an independently running source-selected 2DGS queue."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())
def write(path,obj):
    path=Path(path)
    with path.open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def now():return datetime.now(timezone.utc).isoformat()


def check_outputs(folder,receipt):
    records=receipt.get('outputs',receipt.get('output_sha256',{}))
    if isinstance(records,dict):rows=[dict(path=p,sha256=h) for p,h in records.items()]
    else:rows=records
    for row in rows:
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Output path escapes receipt owner')
        if sha(folder/relative)!=row['sha256']:raise ValueError('Output hash mismatch: '+str(relative))


def check_receipt(folder):
    p=folder/'receipt.json';r=read(p)
    if not r['status'].startswith('PASS') or r.get('scientific_verdict','missing') is not None:
        raise ValueError('Technical PASS/null verdict required: '+str(p))
    check_outputs(folder,r)
    return r


def freeze(a):
    if a.repo is None or a.git_base is None:raise ValueError('repo and git-base required')
    prepared=check_receipt(a.attempt/'prepared')
    config=a.repo/'configs/phd/source_selected_2dgs_v1/experiment.json'
    cfg=read(config)
    if prepared['status']!='PASS_PREPARED_SOURCES' or prepared['config_sha256']!=sha(config):
        raise ValueError('Prepared sources do not match the launch configuration')
    if prepared['source_sha256']!=sha(a.repo/'scripts/phd/source_selected_2dgs_v1/prepare.py') or prepared['policy_sha256']!=sha(a.repo/'src/phd/source_selected_2dgs_v1/evidence.py'):
        raise ValueError('Preparation source changed after creating inputs')
    compile_receipt=a.attempt/'runtime_preflight_cpu/receipt.json'
    if read(compile_receipt)['status']!='PASS_CPU_CUDA_COMPILE':
        raise ValueError('Pinned stock CUDA compilation is not complete')
    audit_receipt=a.attempt/'preparation_audit/results/receipt.json'
    audit=read(audit_receipt)
    if audit['status']!='PASS_INDEPENDENT_PREPARATION_AUDIT' or audit['preparation_receipt_sha256']!=sha(a.attempt/'prepared/receipt.json'):
        raise ValueError('Independent source preparation audit is not bound to these inputs')
    dst=a.attempt/'source_snapshot';dst.mkdir(exist_ok=False)
    for name in ('src','scripts','configs','tests'):
        shutil.copytree(a.repo/name,dst/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(a.repo/'AGENTS.md',dst/'AGENTS.md')
    shutil.copytree(a.repo/'docs/experiments/phd/source_selected_2dgs_v1',dst/'docs/experiments/phd/source_selected_2dgs_v1')
    records=[dict(path=str(p.relative_to(dst)),sha256=sha(p),bytes=p.stat().st_size)
             for p in sorted(dst.rglob('*')) if p.is_file()]
    write(dst/'source_manifest.json',dict(schema='jbgs.frozen_source.v1',git_base=a.git_base,files=records))
    write(a.attempt/'launch_receipt.json',dict(schema='jbgs.source_selected_2dgs.launch.v1',
        task_id=cfg['task_id'],status='READY_FOR_BACKGROUND_RESOURCE_WAIT',scientific_verdict=None,
        created_at=now(),authorization=cfg['authorization'],git_base=a.git_base,
        source_manifest_sha256=sha(dst/'source_manifest.json'),config_sha256=sha(config),
        prepared_receipt_sha256=sha(a.attempt/'prepared/receipt.json'),
        prepared_manifest_sha256=sha(a.attempt/'prepared/manifest.json'),
        cpu_compile_receipt_sha256=sha(compile_receipt),
        independent_preparation_audit_sha256=sha(audit_receipt),
        parent_result_sha256=cfg['inputs']['parent_technical_manifest_sha256'],
        runtime_image=cfg['resources']['image'],regions=cfg['regions'],arms=cfg['arms'],
        expected_iterations=cfg['training']['iterations'],
        cpu_preparation_complete=True,gpu_fixture_completed=False,training_completed=False,
        reference_available_in_training_container=False,existing_jobs_untouched=True))
    print(json.dumps(dict(status='READY_FOR_BACKGROUND_RESOURCE_WAIT',source_files=len(records))))


def verify(a):
    launch=read(a.attempt/'launch_receipt.json');frozen=a.attempt/'source_snapshot'
    if sha(frozen/'source_manifest.json')!=launch['source_manifest_sha256']:raise ValueError('Frozen manifest differs')
    source=read(frozen/'source_manifest.json')
    for row in source['files']:
        if sha(frozen/row['path'])!=row['sha256']:raise ValueError('Frozen source differs: '+row['path'])
    if sha(a.attempt/'prepared/receipt.json')!=launch['prepared_receipt_sha256']:raise ValueError('Prepared receipt changed')
    if sha(a.attempt/'prepared/manifest.json')!=launch['prepared_manifest_sha256']:raise ValueError('Prepared manifest changed')
    if sha(a.attempt/'preparation_audit/results/receipt.json')!=launch['independent_preparation_audit_sha256']:
        raise ValueError('Independent preparation audit changed')
    if sha(a.attempt/'runtime_preflight_cpu/receipt.json')!=launch['cpu_compile_receipt_sha256']:
        raise ValueError('Pinned compilation record changed')
    check_receipt(a.attempt/'prepared')
    print(json.dumps(dict(status='PASS_FROZEN_SOURCE_AND_INPUTS',files=len(source['files']))))


def gate(a):
    if a.preflight:
        folder=a.attempt/'gpu_preflight/P2_source_selected'
    else:
        if a.region not in ('P1','P2','P3') or a.arm not in ('prior_only','source_selected'):
            raise ValueError('Exact training arm required')
        folder=a.attempt/'training'/a.region/a.arm
    receipt=check_receipt(folder)
    cfg=read(a.attempt/'source_snapshot/configs/phd/source_selected_2dgs_v1/experiment.json')
    expected='PASS_GSPLAT_GPU_PREFLIGHT' if a.preflight else 'PASS_SOURCE_SELECTED_2DGS_TRAIN'
    if receipt['status']!=expected:raise ValueError('Wrong stage receipt status')
    if receipt['config_sha256']!=sha(a.attempt/'source_snapshot/configs/phd/source_selected_2dgs_v1/experiment.json'):
        raise ValueError('Stage config differs from frozen source')
    if not a.preflight:
        if receipt['config_sha256']!=sha(a.attempt/'source_snapshot/configs/phd/source_selected_2dgs_v1/experiment.json'):
            raise ValueError('Training config differs from frozen source')
        if receipt['manifest_sha256']!=sha(a.attempt/'prepared'/a.region/'manifest.json'):
            raise ValueError('Training regional input differs')
        if receipt['iterations']!=cfg['training']['iterations'] or receipt['checkpoints']!=cfg['training']['checkpoints']:
            raise ValueError('Incomplete training schedule')
        if receipt['region']!=a.region or receipt['arm']!=a.arm or not receipt['input_hashes_unchanged']:
            raise ValueError('Training identity or input integrity differs')
        if any(receipt['iteration0_repeat_max_abs'][key]>1e-6 for key in ('rgb','depth','alpha','normal')):
            raise ValueError('Unmodified model rendering is not repeatable')
        invariants=receipt['final_invariants']
        if not all(invariants[k] for k in ('means','quats_raw','log_scales','opacity_raw','finite_parameters')):
            raise ValueError('Protected geometry/finite invariant failed')
        if invariants['maximum_center_displacement_m']>cfg['training']['maximum_center_displacement_m']+3e-5:
            raise ValueError('Training displacement exceeds frozen bound')
        for step in cfg['training']['checkpoints']:
            if not (folder/f'checkpoint_{step:06d}.npz').is_file():raise ValueError('Checkpoint absent')
    print(json.dumps(dict(status='PASS_QUEUE_STAGE',path=str(folder),receipt_sha256=sha(folder/'receipt.json'))))


def complete(a):
    verify(a);receipts=[]
    a.preflight=True;gate(a);a.preflight=False
    for region in ('P1','P2','P3'):
        for arm in ('prior_only','source_selected'):
            a.region=region;a.arm=arm;gate(a)
            folder=a.attempt/'training'/region/arm;check_receipt(folder)
            receipts.append(dict(path=str((folder/'receipt.json').relative_to(a.attempt)),sha256=sha(folder/'receipt.json')))
    check_receipt(a.attempt/'report')
    browser=read(a.attempt/'qa_final/receipt.json')
    if browser['status']!='PASS_ACTUAL_BROWSER' or browser.get('scientific_verdict','missing') is not None:
        raise ValueError('Completed mobile and desktop browser checks required')
    if browser['data_sha256']!=sha(a.attempt/'report/data.json') or browser['html_sha256']!=sha(a.attempt/'report/index.html'):
        raise ValueError('Browser did not check the sealed final report')
    write(a.attempt/'completion_receipt.json',dict(task_id='PHD-SOURCE-SELECTED-2DGS-v1',
        status='PASS_TECHNICAL_EXPERIMENT_AND_REPORT',scientific_verdict=None,completed_at=now(),
        launch_receipt_sha256=sha(a.attempt/'launch_receipt.json'),training_receipts=receipts,
        browser_receipt_sha256=sha(a.attempt/'qa_final/receipt.json'),
        report_receipt_sha256=sha(a.attempt/'report/receipt.json'),scientific_performance_verdict=False))
    print(json.dumps(dict(status='PASS_TECHNICAL_EXPERIMENT_AND_REPORT',arms=6)))


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('freeze','verify','gate','complete'))
    ap.add_argument('--attempt',type=Path,required=True);ap.add_argument('--repo',type=Path)
    ap.add_argument('--git-base');ap.add_argument('--preflight',action='store_true')
    ap.add_argument('--region');ap.add_argument('--arm');a=ap.parse_args()
    globals()[a.action](a)


if __name__=='__main__':main()
