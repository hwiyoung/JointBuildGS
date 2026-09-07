"""Seal all preregistered outputs before any UAS payload is exposed."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image
from runtime_layout import RuntimeLayout
from supplemental_repeat import SupplementalRepeat
import resource_support as resources


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def bind_completion_amendment(repeat, bind):
    """Sealer-only failure-byte verification; downstream uses the sealed records.

    Logs and device samples are hashed without parsing their contents. Native
    failure receipts/invocations supply operational identity, never quality.
    """
    if not repeat.completion:
        return {}
    completion = repeat.completion
    if bind(completion.path)['sha256'] != completion.digest:
        raise ValueError('Completion contract changed during sealing')
    evidence = []
    for expected in completion.data['failure_evidence']:
        path = repeat.task/expected['path']
        if path.resolve() != repeat.task.resolve()/expected['path']:
            raise ValueError('Failure evidence may not redirect outside its exact task path')
        bound = bind(path)
        if bound['sha256'] != expected['sha256']:
            raise ValueError('Completion failure evidence changed: ' + expected['path'])
        evidence.append(bound)
    for row in repeat.supplemental_availability:
        run = repeat.run(row['region'])
        if not row['attempted']:
            if row['status'] != 'NOT_ATTEMPTED_AFTER_CONTROLLER_FAILURE' or run.exists() or run.is_symlink():
                raise ValueError('Unattempted supplemental output path must remain absent')
            continue
        receipt = json.loads((run/'train_receipt.json').read_text())
        invocation = json.loads((run/'train_invocation.json').read_text())
        if (row['status'] != 'TRAINING_FAILED_CUDA_OOM' or receipt.get('status') != 'FAIL' or
                receipt.get('native_exit_code') != 1 or receipt.get('validated_exit_code') != 1 or
                receipt.get('wall_seconds') != row['train_wall_seconds']):
            raise ValueError('Supplemental failure receipt differs from completion availability')
        for value in (receipt, invocation):
            repeat.require_run_receipt(value, row['region'])
            if (value.get('phase') != 'train' or value.get('config_sha256') != completion.data['scientific_config_sha256'] or
                    value.get('input_manifest_sha256') != sha(repeat.task/'inputs'/row['region']/'input_manifest.json') or
                    value.get('scientific_verdict') is not None):
                raise ValueError('Supplemental failure execution identity differs')
        if any(receipt.get(key) != value for key, value in invocation.items()):
            raise ValueError('Supplemental failed receipt differs from its exact invocation')
        command = invocation['command']
        if (command[:2] != ['python', 'train.py'] or
                command[command.index('--jbgs_resume_full')+1] != '/anchor/checkpoint.pth' or
                '--jbgs_stop_after' in command or '--jbgs_release_protection' in command):
            raise ValueError('Completion evidence is not the original full native repeat invocation')
    return dict(supplemental_availability=repeat.supplemental_availability,
                completion_decision_evidence=evidence)


def bind_evaluation_inputs(task, region, config_sha256, bind):
    """Bind scoring/calibration dependencies to the pre-training input manifest.

    Training drivers validate every input file before every phase. This seal
    additionally revalidates and binds all files actually consumed in evaluation,
    plus all frozen camera calibrations, so later evaluation detects their drift.
    """
    root = task / 'inputs' / region
    manifest_path = root / 'input_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest_record = bind(manifest_path)
    if (manifest['status'] != 'INPUTS_SEALED_FOR_EXECUTION' or manifest['region'] != region
            or manifest['config_sha256'] != config_sha256):
        raise ValueError('Regional input manifest does not match frozen execution')
    frozen = {row['path']: row for row in manifest['files']}
    if len(frozen) != len(manifest['files']):
        raise ValueError('Duplicate frozen input paths')
    def frozen_bind(relative):
        if relative not in frozen:
            raise ValueError(f'Evaluation input absent from pre-training seal: {relative}')
        record = bind(root / relative)
        if record['sha256'] != frozen[relative]['sha256']:
            raise ValueError(f'Evaluation input changed after pre-training seal: {relative}')
        return record
    split_path = manifest['split_path']
    if frozen_bind(split_path)['sha256'] != manifest['split_sha256']:
        raise ValueError('Split identity differs from pre-training input seal')
    split = json.loads((root / split_path).read_text())
    if split['region'] != region:
        raise ValueError('Split region differs')
    names = [row['name'] for role in ('train', 'evaluation') for row in split[role]]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate or overlapping train/evaluation views')
    for relative in frozen:
        parts = Path(relative).parts
        if len(parts) >= 3 and parts[0] == 'scene' and parts[1].startswith('sparse'):
            frozen_bind(relative)
    frozen_bind('surface/als_surface.ply')
    for row in split['evaluation']:
        if frozen_bind('scene/images/' + row['name'])['sha256'] != row['sha256']:
            raise ValueError('Photograph identity differs from frozen split')
    return split, manifest_record['sha256']


def validate_phase_receipt(receipt, region, condition, phase, config_sha256, input_sha256, runtime_layout=None, repeat=None):
    expected = dict(status='PASS', region=region, condition=condition, phase=phase,
                    config_sha256=config_sha256, input_manifest_sha256=input_sha256)
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError(f'Incomplete or differently bound {region}/{condition}/{phase}')
    if runtime_layout is not None:
        runtime_layout.require_receipt(receipt)
        if phase == 'train' and runtime_layout.path:
            expected_start = 8000 if repeat or runtime_layout.starts_from_anchor(region, condition) else 0
            if receipt.get('training_start_iteration') != expected_start:
                raise ValueError('Training start iteration differs from declared runtime anchor provenance')
    if repeat:
        repeat.require_run_receipt(receipt, region)
    elif receipt.get('supplemental_only') or receipt.get('repeat_contract_sha256'):
        raise ValueError('A supplemental run cannot replace a primary condition')


def bind_produced_file(directory, relative, receipt, bind, collection='validation'):
    """Verify current output against its producer, before admitting it to the seal.

    Native phase validation records include SHA and byte count. The existing
    auxiliary per-variant `files` records include SHA only; that exact digest
    still binds all bytes, and the new seal records their actual size.
    """
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or str(path) != relative:
        raise ValueError('Producer artifact must use an unambiguous relative path')
    rows = [row for row in receipt.get(collection, [])
            if row.get('path') == relative and 'sha256' in row]
    if len(rows) != 1:
        raise ValueError('Expected exactly one producer hash for ' + relative)
    row = rows[0]
    existence_key = 'exists_nonempty' if collection == 'validation' else 'exists'
    if row.get(existence_key) is not True or not isinstance(row.get('sha256'), str):
        raise ValueError('Producer did not record a completed artifact: ' + relative)
    record = bind(directory/path)
    if record['sha256'] != row['sha256']:
        raise ValueError('Artifact differs from its producer hash: ' + relative)
    if collection == 'validation' or 'bytes' in row:
        if row.get('bytes') != (directory/path).stat().st_size:
            raise ValueError('Artifact differs from its producer size: ' + relative)
    return record


def bind_phase_outputs(run, receipt, bind):
    required = {
        'train': ['model/jbgs_complete/iteration_30000/checkpoint.pth',
                  'model/jbgs_complete/iteration_30000/point_cloud.ply',
                  'model/point_cloud/iteration_30000/point_cloud.ply'],
        'render': ['model/train/ours_30000/fuse.ply', 'model/train/ours_30000/fuse_post.ply'],
        'metrics': ['model/results.json', 'model/per_view.json'],
        'auxiliary': ['auxiliary_manifest.json'],
    }
    return {relative: bind_produced_file(run, relative, receipt, bind)
            for relative in required[receipt['phase']]}


def bind_final_complete_state(run, produced_train, bind):
    directory = run/'model/jbgs_complete/iteration_30000'
    receipt_record = bind(directory/'receipt.json')
    receipt = json.loads((directory/'receipt.json').read_text())
    checkpoint = produced_train['model/jbgs_complete/iteration_30000/checkpoint.pth']
    point_cloud = produced_train['model/jbgs_complete/iteration_30000/point_cloud.ply']
    if (receipt.get('iteration') != 30000 or receipt.get('after_protection_registration') is not True or
            receipt.get('checkpoint_sha256') != checkpoint['sha256'] or
            receipt.get('ply_sha256') != point_cloud['sha256']):
        raise ValueError('Final complete-state checkpoint/PLY differs from its train producer or state receipt')
    return dict(receipt=receipt_record, checkpoint=checkpoint, point_cloud=point_cloud)


def bind_anchor(layout, region, config_sha256, input_sha256, bind):
    directory = layout.anchor_checkpoint(region)
    receipt = json.loads((directory/'receipt.json').read_text())
    if receipt.get('iteration') != 8000 or receipt.get('after_protection_registration') is not True:
        raise ValueError('Expected an exact completed protected iteration8000 anchor')
    checkpoint, point_cloud = bind(directory/'checkpoint.pth'), bind(directory/'point_cloud.ply')
    if checkpoint['sha256'] != receipt['checkpoint_sha256'] or point_cloud['sha256'] != receipt['ply_sha256']:
        raise ValueError('Anchor checkpoint or PLY differs from its completed-state receipt')
    expected = layout.data['anchors'][region].get('checkpoint_sha256')
    if expected and expected != checkpoint['sha256']:
        raise ValueError('Anchor differs from the runtime revision checkpoint identity')
    baseline = layout.anchor_baseline(region)
    train_path = baseline/'train_receipt.json'
    train = json.loads(train_path.read_text())
    # A source run can fail after producing the complete8000 snapshot. Preserve
    # that status; the exact completed checkpoint, not full-run PASS, is reused.
    if any(train.get(key) != value for key, value in dict(region=region, condition='D005_Pnative', phase='train',
             config_sha256=config_sha256, input_manifest_sha256=input_sha256).items()):
        raise ValueError('Anchor source training inputs/configuration differ')
    return dict(baseline_directory=str(baseline.relative_to(layout.task)),
                checkpoint_directory=str(directory.relative_to(layout.task)), checkpoint=checkpoint, point_cloud=point_cloud,
                receipt=bind(directory/'receipt.json'), source_train_receipt=bind(train_path),
                source_trace=bind(baseline/'model/jbgs_trace.jsonl'), source_run_status=train['status'],
                native_final_starts_from_anchor=layout.starts_from_anchor(region, 'D005_Pnative'))


def bind_auxiliary_anchor(run, anchor, layout, config_sha256, bind, variant='anchor'):
    directory = run/'auxiliary'/variant
    receipt = json.loads((directory/'receipt.json').read_text())
    layout.require_receipt(receipt)
    if (receipt.get('status') != 'PASS' or receipt.get('iteration') != 8000 or
            receipt.get('config_sha256') != config_sha256 or
            receipt.get('source_complete_ply_sha256') != anchor['point_cloud']['sha256'] or
            receipt.get('copied_ply_sha256') != anchor['point_cloud']['sha256']):
        raise ValueError('Auxiliary anchor extraction does not use the exact declared complete anchor')
    copied = bind(directory/'model/point_cloud/iteration_8000/point_cloud.ply')
    if copied['sha256'] != anchor['point_cloud']['sha256']:
        raise ValueError('Auxiliary anchor PLY copy changed')
    return dict(receipt=bind(directory/'receipt.json'), copied_point_cloud=copied)


def validate_realized_extraction(value, log_record, parser_record, region, resolution, num_cluster, seen):
    if (value.get('schema') != 'GEOGS_BOUNDED_TSDF_LOG_PARAMETERS_v1' or value.get('mesh_res') != resolution or
            value.get('num_cluster') != num_cluster or value.get('tsdf_block_count') != 1 or
            value.get('source_log_sha256') != log_record['sha256'] or value.get('parser_sha256') != parser_record['sha256'] or
            value.get('numeric_relationship_policy') != 'EXACT_FLOAT_EQUALITY_FOR_ROUNDTRIP_LOGGED_VALUES'):
        raise ValueError('Realized TSDF metadata/log/parser does not match the fixed extraction')
    depth, voxel, sdf = [value[key] for key in ('depth_trunc_m', 'voxel_size_m', 'sdf_trunc_m')]
    if not all(isinstance(x, (float, int)) and math.isfinite(x) and x > 0 for x in (depth, voxel, sdf)):
        raise ValueError('Finite positive realized TSDF values required')
    if voxel != depth/resolution or sdf != 5*voxel:
        raise ValueError('Realized TSDF values differ from the camera-derived default algebra')
    key, triple = (region, resolution), (depth, voxel, sdf)
    if key in seen and seen[key] != triple:
        raise ValueError('Realized TSDF tuple differs across arms or anchor at the same regional resolution')
    if any(old_region == region and previous[0] != depth for (old_region, _), previous in seen.items()):
        raise ValueError('Regional camera-derived depth truncation differs across extraction resolutions')
    seen[key] = triple
    return value


def bind_repeat_provenance(directory, receipt, repeat, region, bind, phase=None):
    """Bind actual repeat-validator bytes and the same primary anchor gate."""
    repeat.require_run_receipt(receipt, region)
    prefix = phase+'_' if phase else ''
    contract = bind(directory/(prefix+'repeat_contract_snapshot.json'))
    helper = bind(directory/(prefix+'repeat_helper_snapshot.py'))
    if contract['sha256'] != repeat.digest or helper['sha256'] != receipt.get('repeat_helper_sha256'):
        raise ValueError('Supplemental contract/helper snapshot changed')
    anchor_receipt_path = repeat.layout.anchor_checkpoint(region)/'receipt.json'
    anchor = json.loads(anchor_receipt_path.read_text())
    bind(anchor_receipt_path)
    gate_path = repeat.task/repeat.layout.data['parity_directory']/region/'anchor_gate.json'
    gate_record = bind(gate_path)
    gate = json.loads(gate_path.read_text())
    if (gate.get('status') != 'EXACT_COMMON_ANCHOR_VERIFIED' or gate.get('region') != region or
            gate.get('runtime_layout_sha256') != repeat.layout.digest or
            gate.get('checkpoint_sha256') != anchor.get('checkpoint_sha256') or
            receipt.get('repeat_anchor_checkpoint_sha256') != anchor.get('checkpoint_sha256') or
            receipt.get('repeat_anchor_gate_sha256') != gate_record['sha256']):
        raise ValueError('Supplemental repetition does not bind the exact primary anchor gate')


def bind_auxiliary_extraction(run, name, iteration, resolution, cfg_sha, layout, region, num_cluster, seen, source_ply, bind, repeat=None):
    directory = run/'auxiliary'/name
    receipt = json.loads((directory/'receipt.json').read_text())
    invocation = json.loads((directory/'invocation.json').read_text())
    layout.require_receipt(receipt)
    layout.require_receipt(invocation)
    for value in (receipt, invocation):
        if repeat:
            repeat.require_run_receipt(value, region)
            bind_repeat_provenance(directory, value, repeat, region, bind)
        if value.get('config_sha256') != cfg_sha or value.get('iteration') != iteration or value.get('mesh_res') != resolution:
            raise ValueError('Auxiliary extraction identity differs from frozen iteration/resolution')
        if value.get('source_complete_ply_sha256') != source_ply['sha256'] or value.get('copied_ply_sha256') != source_ply['sha256']:
            raise ValueError('Auxiliary extraction source is not the declared complete-state PLY')
    if receipt.get('status') != 'PASS' or receipt.get('command') != invocation.get('command'):
        raise ValueError('Auxiliary extraction did not complete its recorded invocation')
    for filename in ('invocation.json', 'receipt.json'):
        bind(directory/filename)
    cfg_args = bind(directory/'model/cfg_args')
    if any(value.get('render_cfg_args_sha256') != cfg_args['sha256'] for value in (receipt, invocation)):
        raise ValueError('Auxiliary renderer cfg_args identity changed')
    log = bind(directory/'render.log')
    parser = bind(directory/'parse_extraction_snapshot.py')
    copied = bind(directory/f'model/point_cloud/iteration_{iteration}/point_cloud.ply')
    if copied['sha256'] != source_ply['sha256']:
        raise ValueError('Auxiliary extraction PLY copy changed')
    if receipt.get('extraction_helper_snapshot', {}).get('sha256') != parser['sha256']:
        raise ValueError('Auxiliary extraction parser snapshot identity changed')
    for filename in ('fuse.ply', 'fuse_post.ply'):
        bind_produced_file(directory, f'model/train/ours_{iteration}/{filename}', receipt, bind, 'files')
    return validate_realized_extraction(receipt['realized_extraction'], log, parser, region, resolution, num_cluster, seen)


def bind_resource_auxiliary(resource, directory, source_run, region, condition, candidate_id,
                            repeat, input_sha256, anchor, final_ply, bind):
    """Account for every variant using immutable producers, including OOM proof."""
    outer_path = directory/'auxiliary_receipt.json'
    outer = json.loads(outer_path.read_text())
    resource.validate_receipt(outer, region, condition, repeat.identifier if repeat else None)
    if outer.get('input_manifest_sha256') != input_sha256:
        raise ValueError('Resource auxiliary inputs differ from the original frozen training inputs')
    bind(outer_path)
    producers = outer.get('producer_files', [])
    if not producers or len({row['path'] for row in producers}) != len(producers):
        raise ValueError('Resource auxiliary requires an unambiguous executed producer file inventory')
    for row in producers:
        path = Path(row['path'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Resource producer path must remain within its attempt')
        record = bind(directory/path)
        if record['sha256'] != row['sha256'] or record['bytes'] != row['bytes']:
            raise ValueError('Resource producer differs from its recorded bytes: '+str(path))
    for name, field in [('auxiliary_driver_snapshot.py', 'driver_sha256'),
                        ('auxiliary_config_snapshot.json', 'config_sha256'),
                        ('auxiliary_runtime_layout_snapshot.json', 'runtime_layout_sha256'),
                        ('auxiliary_resource_contract_snapshot.json', 'resource_contract_sha256')]:
        if name not in {row['path'] for row in producers} or bind(directory/name)['sha256'] != outer.get(field):
            raise ValueError('Resource executed driver/contract snapshot differs: '+name)
    manifest = bind_produced_file(directory, 'auxiliary_manifest.json', outer, bind)
    aggregate = json.loads((directory/'auxiliary_manifest.json').read_text())
    if aggregate.get('status') != 'PASS' or aggregate.get('variants') != outer.get('variants'):
        raise ValueError('Resource auxiliary manifest differs from accounted phase receipt')
    original_cfg = bind(source_run/'model/cfg_args')
    inventory = []
    for planned in resource.variant_inventory(region, condition, repeat.identifier if repeat else None):
        variant_dir = directory/'auxiliary'/planned['name']
        receipt = json.loads((variant_dir/'receipt.json').read_text())
        invocation = json.loads((variant_dir/'invocation.json').read_text())
        source = anchor['point_cloud'] if planned['iteration'] == 8000 else final_ply
        copied = bind(variant_dir/f'model/point_cloud/iteration_{planned["iteration"]}/point_cloud.ply')
        cfg_args = bind(variant_dir/'model/cfg_args')
        if copied['sha256'] != source['sha256'] or cfg_args['sha256'] != original_cfg['sha256']:
            raise ValueError('Resource extraction model/renderer configuration differs from frozen producer')
        for value in (receipt, invocation):
            resource.require_receipt(value)
            if any(value.get(key) != expected for key, expected in
                   dict(region=region, condition=condition, variant=planned['name'],
                        iteration=planned['iteration'], mesh_res=planned['mesh_res'],
                        config_sha256=resource.data['scientific_config_sha256'],
                        source_complete_ply_sha256=source['sha256'], copied_ply_sha256=source['sha256'],
                        render_cfg_args_sha256=original_cfg['sha256']).items()):
                raise ValueError('Resource variant differs from its exact source/invocation identity')
            if repeat:
                repeat.require_run_receipt(value, region)
            elif value.get('repeat_id') or value.get('supplemental_only'):
                raise ValueError('Primary resource extraction cannot use a supplemental identity')
        if receipt['command'] != invocation['command']:
            raise ValueError('Resource extraction command differs from invocation')
        bind(variant_dir/'invocation.json')
        for field in ('memory_trace', 'source_log'):
            evidence = receipt[field]
            record = bind(variant_dir/evidence['path'])
            if record['sha256'] != evidence['sha256']:
                raise ValueError('Resource extraction memory/log evidence changed')
        inventory.append(dict(region=region, condition=candidate_id, scientific_condition=condition,
            variant=planned['name'], iteration=planned['iteration'], mesh_res=planned['mesh_res'],
            required=planned['required'], export_images=planned['export_images'],
            supplemental_only=bool(repeat), status=receipt['status'],
            producer_directory=str(variant_dir.relative_to(resource.task)),
            receipt=bind(variant_dir/'receipt.json'), source_complete_point_cloud=source,
            render_input_point_cloud=copied, native_exit_code=receipt['native_exit_code'],
            cgroup_oom_kill_delta=receipt.get('cgroup_oom_kill_delta'),
            cgroup_memory_limit_bytes=receipt.get('cgroup_memory_limit_bytes'),
            wall_seconds=receipt.get('wall_seconds'), child_peak_rss_bytes=receipt.get('child_peak_rss_bytes'),
            sampled_peak_memory_current_bytes=receipt.get('sampled_peak_memory_current_bytes'),
            host_headroom_wait_seconds=receipt.get('host_headroom_wait_seconds'),
            **resource.binding(), scientific_verdict=None))
    return inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime-layout', type=Path)
    parser.add_argument('--repeat-contract', type=Path)
    parser.add_argument('--resource-contract', type=Path)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/reference').exists():
        raise RuntimeError('Seal only in Docker without a reference mount')
    cfg_path = args.task / 'contracts/execution_v1.json'
    cfg = json.loads(cfg_path.read_text())
    layout = RuntimeLayout(args.task, args.runtime_layout, cfg['regions'])
    layout.require_scientific_config(cfg_path)
    repeat = SupplementalRepeat(args.task, args.repeat_contract, layout)
    resource = resources.make_resource(args.task, args.resource_contract, layout, repeat)
    if args.output.exists():
        raise FileExistsError(args.output)
    candidates, files, realized_by_region_resolution, extraction_inventory = [], {}, {}, []
    def bind(path):
        relative = str(path.relative_to(args.task))
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Missing completed output {relative}')
        if relative not in files:
            files[relative] = {'path': relative, 'bytes': path.stat().st_size, 'sha256': sha(path)}
        return files[relative]
    if layout.path:
        bind(layout.path)
    if repeat.path:
        bind(repeat.path)
    completion_metadata = bind_completion_amendment(repeat, bind)
    if resource:
        bind(resource.path)
        for relative in resource.data['evidence_paths']:
            bind(args.task/relative)
    for region, spec in cfg['regions'].items():
        split, input_sha256 = bind_evaluation_inputs(args.task, region, sha(cfg_path), bind)
        shared_anchor = bind_anchor(layout, region, sha(cfg_path), input_sha256, bind)
        evaluation = split['evaluation']
        # The native render loader sets shuffle=False and COLMAP eval split is
        # ascending name; enumerate exactly that identity, never filename guesses.
        evaluation = sorted(evaluation, key=lambda row: Path(row['name']).stem)
        if len(evaluation) != spec['expected_test'] or len(split['train']) != spec['expected_train']:
            raise ValueError('Frozen train/evaluation counts differ from execution configuration')
        executions = [(condition['id'], condition['id'], layout.run(region, condition['id']), None)
                      for condition in cfg['conditions']]
        if repeat.evaluation_enabled(region):
            executions.append((repeat.identifier, 'D005_Pnative', repeat.run(region), repeat))
        for candidate_id, condition_id, run, active_repeat in executions:
            anchor = copy.deepcopy(shared_anchor)
            primary_extraction = None
            produced_train = None
            for phase in (('train', 'render', 'metrics') if resource else ('train', 'render', 'metrics', 'auxiliary')):
                receipt_path = run / f'{phase}_receipt.json'
                receipt = json.loads(receipt_path.read_text())
                validate_phase_receipt(receipt, region, condition_id, phase, sha(cfg_path), input_sha256, layout, active_repeat)
                bind(receipt_path)
                produced = bind_phase_outputs(run, receipt, bind)
                if phase == 'train':
                    produced_train = produced
                scheduling = receipt.get('resource_scheduling', {})
                if scheduling.get('serialized_extraction'):
                    helper = bind(run/scheduling['helper_snapshot_path'])
                    if (helper['sha256'] != scheduling['helper_sha256'] or
                            not math.isfinite(scheduling['wait_seconds']) or scheduling['wait_seconds'] < 0 or
                            not scheduling.get('wait_excluded_from_native_phase_wall_seconds')):
                        raise ValueError('Extraction scheduling provenance or timing changed')
                if layout.path:
                    driver = bind(run/f'{phase}_driver_snapshot.py')
                    if driver['sha256'] != receipt['driver_sha256'] or bind(run/f'{phase}_config_snapshot.json')['sha256'] != sha(cfg_path):
                        raise ValueError('Executed phase driver/config snapshots changed')
                    bind(run/f'{phase}_invocation.json')
                if active_repeat:
                    invocation = json.loads((run/f'{phase}_invocation.json').read_text())
                    active_repeat.require_run_receipt(invocation, region)
                    bind_repeat_provenance(run, receipt, active_repeat, region, bind, phase)
                    bind_repeat_provenance(run, invocation, active_repeat, region, bind, phase)
                if phase == 'render':
                    invocation = json.loads((run/'render_invocation.json').read_text())
                    validate_phase_receipt(dict(invocation, status='PASS'), region, condition_id, phase,
                                           sha(cfg_path), input_sha256, layout, active_repeat)
                    actual_ply = bind(run/'model/point_cloud/iteration_30000/point_cloud.ply')
                    actual_cfg = bind(run/'model/cfg_args')
                    for value in (receipt, invocation):
                        renderer_ply = value.get('render_source_ply', {})
                        if (renderer_ply.get('path') != 'model/point_cloud/iteration_30000/point_cloud.ply' or
                                renderer_ply.get('sha256') != actual_ply['sha256'] or
                                value.get('render_cfg_args_sha256') != actual_cfg['sha256']):
                            raise ValueError('Main renderer PLY or cfg_args identity changed')
                    if receipt['command'] != invocation['command']:
                        raise ValueError('Main renderer command differs from its invocation')
                    bind(run/'render_invocation.json')
                    log = bind(run/'render.log')
                    parser = bind(run/'render_extraction_helper_snapshot.py')
                    if receipt.get('extraction_helper_snapshot', {}).get('sha256') != parser['sha256']:
                        raise ValueError('Main extraction parser snapshot identity changed')
                    primary_extraction = validate_realized_extraction(receipt['realized_extraction'], log, parser, region,
                        cfg['extraction']['mesh_res'], cfg['extraction']['num_cluster'], realized_by_region_resolution)
                if phase == 'auxiliary':
                    bind(run/'auxiliary_helper_snapshot.py')
                    bind(run/'auxiliary_extraction_helper_snapshot.py')
                    bind(run/'auxiliary_manifest.json')
            final_complete = bind_final_complete_state(run, produced_train, bind)
            complete_ply = final_complete['point_cloud']
            bind(run/'model/jbgs_trace.jsonl')
            restore = run/'model/jbgs_restore.json'
            if active_repeat or layout.starts_from_anchor(region, condition_id):
                restore_receipt = json.loads(restore.read_text())
                if restore_receipt.get('iteration') != 8000 or restore_receipt.get('checkpoint_sha256') != anchor['checkpoint']['sha256']:
                    raise ValueError('Final run restored a different anchor checkpoint')
                bind(restore)
            elif restore.exists():
                raise ValueError('A declared full-start native run unexpectedly restored a checkpoint')
            variants = [('final', run / 'model', 30000, cfg['extraction']['mesh_res'], True)]
            auxiliary_run = run
            if resource:
                auxiliary_run = resource.aux_run(region, condition_id, active_repeat.identifier if active_repeat else None)
                entries = bind_resource_auxiliary(resource, auxiliary_run, run, region, condition_id,
                    candidate_id, active_repeat, input_sha256, anchor, complete_ply, bind)
                extraction_inventory.extend(entries)
                for entry in entries:
                    if entry['status'] == 'PASS':
                        variants.append((entry['variant'], auxiliary_run/'auxiliary'/entry['variant']/'model',
                                         entry['iteration'], entry['mesh_res'], entry['export_images']))
                anchor['shared_surface_owner'] = 'primary/D005_Pnative'
                anchor['required_extraction_resolution'] = 512
            else:
                variants += [('mesh_' + str(res), run / f'auxiliary/mesh_{res}/model', 30000, res, False)
                             for res in cfg['extraction']['sensitivity_mesh_res']]
                if condition_id == 'D005_Pnative':
                    variants.append(('anchor', run / 'auxiliary/anchor/model', 8000, cfg['extraction']['mesh_res'], True))
                    anchor['extraction'] = bind_auxiliary_anchor(run, anchor, layout, sha(cfg_path), bind)
            for variant, model, iteration, resolution, has_renders in variants:
                realized = primary_extraction if variant == 'final' else bind_auxiliary_extraction(auxiliary_run,
                    variant, iteration, resolution, sha(cfg_path), layout, region,
                    cfg['extraction']['num_cluster'], realized_by_region_resolution,
                    anchor['point_cloud'] if iteration == 8000 else complete_ply, bind,
                    active_repeat)
                render_input_ply = bind(model/f'point_cloud/iteration_{iteration}/point_cloud.ply')
                render_records = []
                if has_renders:
                    directory = model / f'test/ours_{iteration}/renders'
                    if len(list(directory.glob('*.png'))) != spec['expected_test']:
                        raise ValueError('Native heldout render count differs')
                    for index, row in enumerate(evaluation):
                        path = directory / f'{index:05d}.png'
                        bound = bind(path)
                        with Image.open(path) as image:
                            if image.size != (row['width'], row['height']) or image.mode not in ('RGB', 'RGBA'):
                                raise ValueError('Saved render shape/mode differs from frozen camera')
                        gt = model / f'test/ours_{iteration}/gt' / f'{index:05d}.png'
                        gt_bound = bind(gt)
                        photo = args.task / 'inputs' / region / 'scene/images' / row['name']
                        if sha(photo) != row['sha256']:
                            raise ValueError('Frozen photograph bytes changed')
                        with Image.open(photo) as image:
                            original = np.asarray(image.convert('RGB'), dtype=np.uint8)
                        expected_gt = ((original.astype(np.float32) / 255.0) * 255.0).astype(np.uint8)
                        with Image.open(gt) as image:
                            actual_gt = np.asarray(image.convert('RGB'), dtype=np.uint8)
                        if not np.array_equal(expected_gt, actual_gt):
                            raise ValueError(f'Native exported GT pixels do not establish the expected image order: {gt}')
                        render_records.append({'name': row['name'], 'evaluation_index': index,
                                               'image_id': row['image_id'], 'camera_id': row['camera_id'],
                                               'render_path': bound['path'], 'render_sha256': bound['sha256'],
                                               'exported_gt_sha256': gt_bound['sha256'],
                                               'exported_gt_matches_original_pixels': True,
                                               'pose_binding': 'verified frozen COLMAP calibration and native shuffle=False name order; exported GT pixels checked'})
                for kind, filename in [('raw', 'fuse.ply'), ('post', 'fuse_post.ply')]:
                    bound = bind(model / f'train/ours_{iteration}' / filename)
                    candidates.append({'region': region, 'condition': candidate_id, 'scientific_condition':condition_id,
                                       'supplemental_only':bool(active_repeat), 'variant': variant,
                                       'iteration': iteration, 'mesh_res': resolution, 'mesh_kind': kind,
                                       'surface': bound, 'render_records': render_records if kind == 'raw' else [],
                                       'surface_kind': 'official_bounded_TSDF_triangle_mesh',
                                       'run_directory':str(run.relative_to(args.task)), 'anchor_provenance':anchor,
                                       'realized_extraction':realized,
                                       'render_input_point_cloud':render_input_ply,
                                       'final_complete_state':final_complete,
                                       'required': variant in ('final', 'mesh_512', 'anchor_512') if resource else True,
                                       'shared_anchor_surface': bool(resource and iteration == 8000),
                                       **layout.binding(),
                                       **repeat.binding(),
                                       **resources.binding(resource),
                                       'scientific_verdict': None})
    manifest = {'schema': 'JBGS_GEOGS_CANDIDATES_SEALED_v2' if resource else 'JBGS_GEOGS_CANDIDATES_SEALED_v1', 'status': resources.seal_status(resource, repeat),
                'task_id': cfg['task_id'], 'created_unix': time.time(), 'config_sha256': sha(cfg_path),
                'scientific_verdict': None, 'reference_accessed': False,
                **layout.binding(),
                **repeat.binding(),
                **resources.binding(resource),
                **completion_metadata,
                'extraction_inventory': extraction_inventory,
                'resource_decision_evidence': [files[path] for path in resource.data['evidence_paths']] if resource else [],
                'candidates': candidates, 'files': list(files.values()), 'script_sha256': sha(__file__)}
    repeat.require_candidates(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(manifest, f, indent=2, allow_nan=False)
    print(json.dumps({'status': manifest['status'], 'candidates': len(candidates),
                      'files': len(files), 'sha256': sha(args.output)}))


if __name__ == '__main__':
    main()
