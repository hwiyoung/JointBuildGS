"""Package verified local receipts and source hashes; never declare scientific success."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil

REPO=Path(__file__).resolve().parents[3]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def main(args):
    cfg=json.loads(args.config.read_text())
    base=Path('/artifacts/JointBuildGS')
    links={}
    for name, relative in cfg['receipts'].items():
        p=base/relative
        value=json.loads(p.read_text())
        if value.get('scientific_verdict') is not None:
            raise ValueError(f'Unexpected scientific verdict in technical receipt: {p}')
        links[name]=dict(artifact_relative_path=relative,sha256=sha(p),bytes=p.stat().st_size)
    source_paths=[]
    for relative in ['configs/phd/p2_ab_v2','scripts/phd/p2_ab_v2','src/phd/p2_ab_v2',
                     'src/apps/p2_ab_inspector_v2','docs/experiments/phd/p2_ab_v2']:
        source_paths.extend(p for p in (REPO/relative).rglob('*') if p.is_file())
    source_paths.extend((REPO/'tests/phd').glob('test_p2_ab_v2_*.py'))
    source_paths=[p for p in source_paths if '__pycache__' not in p.parts]
    audit=base/'phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-ROOT-AUDIT-v1'
    preservation=json.loads((audit/'preservation_receipt.json').read_text())
    if preservation['status']!='PASS': raise ValueError('Preservation check must pass')
    result=dict(
        schema='jointbuildgs.phd.p2_ab.technical_result_manifest.v2', task_id='PHD-P2-AB-v2',
        status='A_DESIGN_B_DEVELOPMENT_AND_C_VALIDATION_COMPLETE', scientific_verdict=None,
        authorization='Direct user: proceed with A literature/design and B same-P2 Gaussian reconstruction development, preserve existing work',
        research_scope=cfg['research_scope'], limitations=cfg['limitations'],
        promoted_results=links, existing_work_preservation=preservation,
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in sorted(set(source_paths))},
        git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'), container_image=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        validation_environment=dict(python=platform.python_version(), packages={
            name:importlib.metadata.version(name) for name in ['numpy','scipy','torch','opencv-python']}),
        committed=False, reproduction='Use exact per-run source/config/input snapshots; Git HEAD alone excludes dirty task files',
        artifact_root_container=str(base), local_storage_is_not_durable_backup=True,
        viewer=cfg['viewer'], excluded_runs=cfg['excluded_runs'])
    args.output.mkdir(parents=True,exist_ok=False)
    with (args.output/'technical_receipt.json').open('x') as f:
        json.dump(result,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')
    shutil.copyfile(args.config,args.output/'execution_config.json')
    shutil.copyfile(__file__,args.output/'source_snapshot.py')
    args.manifest.parent.mkdir(parents=True,exist_ok=True)
    with args.manifest.open('x') as f:
        json.dump(result,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')
    print(json.dumps({'status':result['status'],'receipts':len(links),'source_files':len(source_paths)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    main(parser.parse_args())
