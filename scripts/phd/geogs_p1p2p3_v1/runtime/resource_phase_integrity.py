"""Docker-only resume/readiness checks; auxiliary ownership follows resource_v3."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent.parent
for directory in (BASE, BASE/'evaluation'):
    sys.path.insert(0, str(directory))
from resource_contract import ResourceContract, sha, require
from runtime_layout import RuntimeLayout
from supplemental_repeat import SupplementalRepeat

IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'


def context(task):
    task = Path(task)
    cfg_path = task/'contracts/execution_v1.json'
    cfg = json.loads(cfg_path.read_text())
    layout = RuntimeLayout(task, task/'contracts/runtime_layout_allocator_v2.json', cfg['regions'])
    repeat = SupplementalRepeat(task, task/'contracts/supplemental_repeat_v1.json', layout)
    resource = ResourceContract(task, task/'contracts/extraction_resource_v3.json', layout, repeat)
    return cfg, layout, repeat, resource


def validate_regular(run, phase, region, condition, cfg_sha, input_sha, layout, repeat=None, verify_files=True):
    path = run/(phase+'_receipt.json')
    value = json.loads(path.read_text())
    expected = dict(status='PASS',phase=phase,region=region,condition=condition,config_sha256=cfg_sha,
                    input_manifest_sha256=input_sha,runtime_layout_sha256=layout.digest,
                    native_exit_code=0,validated_exit_code=0,runtime_image_id=IMAGE,scientific_verdict=None)
    require(all(value.get(k) == v for k,v in expected.items()), 'Completed phase identity/status differs: '+str(path))
    if repeat:
        repeat.require_run_receipt(value,region)
    else:
        require(not value.get('repeat_id'), 'Primary phase cannot substitute supplemental execution')
    if phase == 'train':
        start = 8000 if repeat or layout.starts_from_anchor(region,condition) else 0
        require(value.get('training_start_iteration') == start, 'Training start differs from frozen anchor plan')
    invocation = json.loads((run/(phase+'_invocation.json')).read_text())
    require(all(value.get(k) == v for k,v in invocation.items()), 'Invocation/receipt differs')
    for name,digest in ((phase+'_driver_snapshot.py',value['driver_sha256']),
                        (phase+'_config_snapshot.json',cfg_sha),
                        (phase+'_runtime_layout_snapshot.json',layout.digest)):
        require(sha(run/name) == digest,'Phase snapshot differs: '+name)
    required = {'train':['model/jbgs_complete/iteration_30000/checkpoint.pth',
                         'model/jbgs_complete/iteration_30000/point_cloud.ply',
                         'model/point_cloud/iteration_30000/point_cloud.ply'],
                'render':['model/train/ours_30000/fuse.ply','model/train/ours_30000/fuse_post.ply'],
                'metrics':['model/results.json','model/per_view.json']}[phase]
    for name in required:
        rows = [row for row in value['validation'] if row.get('path') == name and 'sha256' in row]
        require(len(rows) == 1 and rows[0].get('exists_nonempty') is True, 'Producer output is not uniquely recorded: '+name)
        artifact = run/name
        require(artifact.is_file() and artifact.stat().st_size == rows[0]['bytes'], 'Producer output size differs: '+name)
        if verify_files:
            require(sha(artifact) == rows[0]['sha256'],'Producer output hash differs: '+name)
    return value


def phase_action(task, region, condition, phase, family='primary', verify_files=True):
    cfg,layout,repeat,resource = context(task)
    repeat_id = None if family == 'primary' else family
    run = repeat.run(region) if repeat_id else layout.run(region,condition)
    output = resource.aux_run(region,condition,repeat_id) if phase == 'auxiliary' else run
    path = output/(phase+'_receipt.json')
    if not path.exists():
        if phase in ('train','auxiliary'):
            require(not output.exists(), 'Partial stage directory exists; preserving it: '+str(output))
        else:
            require(not list(output.glob(phase+'_*')) and not (output/(phase+'.log')).exists(),
                    'Partial phase artifacts exist; preserving them: '+str(output))
        return 'RUN', None
    if phase == 'auxiliary':
        receipt = json.loads(path.read_text())
        resource.validate_receipt(receipt,region,condition,repeat_id)
        for item in receipt['producer_files']:
            relative = Path(item['path'])
            require(not relative.is_absolute() and '..' not in relative.parts, 'Resource producer path must remain in its attempt')
            artifact = output/item['path']
            require(artifact.is_file() and artifact.stat().st_size == item['bytes'] and sha(artifact) == item['sha256'],
                    'Resource producer file changed: '+str(artifact))
    else:
        receipt = validate_regular(run,phase,region,condition,sha(Path(task)/'contracts/execution_v1.json'),
                                  sha(Path(task)/'inputs'/region/'input_manifest.json'),layout,repeat if repeat_id else None,verify_files)
    return 'SKIP', dict(path=str(path.relative_to(task)),sha256=sha(path),bytes=path.stat().st_size)


def readiness(task, include_repeats=False):
    cfg,layout,repeat,resource = context(task)
    rows = []
    for region in cfg['regions']:
        jobs = [(condition['id'],'primary') for condition in cfg['conditions']]
        if include_repeats:
            jobs.append(('D005_Pnative','native_repeat_1'))
        for condition,family in jobs:
            for phase in ('train','render','metrics','auxiliary'):
                action,record = phase_action(task,region,condition,phase,family,verify_files=False)
                require(action == 'SKIP','All required phases must finish before downstream work')
                rows.append(record)
    return dict(status='ALL_21_RESOURCE_PHASES_READY' if include_repeats else 'ALL_PRIMARY_RESOURCE_PHASES_READY',
                phase_receipts=len(rows),files=rows,scientific_verdict=None,
                **layout.binding(),**repeat.binding(),**resource.binding())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task',type=Path,default=Path('/task'))
    parser.add_argument('--mode',choices=('phase','job_complete','primary_ready','all_ready'),required=True)
    parser.add_argument('--region',choices=('P1','P2','P3'))
    parser.add_argument('--condition')
    parser.add_argument('--phase',choices=('train','render','metrics','auxiliary'))
    parser.add_argument('--run-family',choices=('primary','native_repeat_1'),default='primary')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists(),'Use Docker without raw reference')
    if args.mode == 'phase':
        print(phase_action(args.task,args.region,args.condition,args.phase,args.run_family)[0])
        return
    if args.mode == 'job_complete':
        records = []
        for phase in ('train','render','metrics','auxiliary'):
            action,item = phase_action(args.task,args.region,args.condition,phase,args.run_family)
            require(action == 'SKIP','Job has unfinished phase')
            records.append(item)
        result = dict(status='ALL_FOUR_RESOURCE_PHASES_VERIFIED',region=args.region,condition=args.condition,
                      run_family=args.run_family,files=records,scientific_verdict=None,resource_contract_sha256=context(args.task)[3].digest,
                      integrity_helper_sha256=sha(__file__))
    else:
        result = readiness(args.task,args.mode == 'all_ready')
    if args.output:
        with args.output.open('x') as stream:
            json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
