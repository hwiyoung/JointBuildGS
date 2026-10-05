"""Post-scoped-seal control curves from immutable traces; never loss/quality analysis."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
STATE_SHA = '7114f78e6f429c9186ce44e81a0c40d18e5087994f99a52d81eeee18ab7fa570'
TRAIN_SHA = '08cfab996b144488b1a583bf722b991c627d90136a9031f85f7d33b1cae0c44b'
TIMING_NOTE = ('Cumulative time since jbgs_state module import; includes initialization/restore, earlier reports/saves and waiting. '
    'Trace is written before its complete-state capture; final capture can occur after the last timestamp. '
    'Logged-interval elapsed is not per-step or isolated optimization cost. Training driver phase wall time is distinct '
    'and includes invocation/input-manifest hashing, child monitoring and post-run required-output validation/hashing.')
CONTROL_NOTE = ('Counts cover the whole training context, not the evaluation ROI surface. Protected count does not imply immutable visible geometry. '
    'The same adaptive DA3 rule may realize different weights by condition. Net count changes do not identify clone/split/prune causes. '
    'Prior initialization/common anchor remain in every condition. Repetition is descriptive and separate; no best-run selection or confidence interval.')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def record(root, path):
    path = Path(path)
    return dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=sha(path))


def safe_relative(value):
    path = Path(value)
    require(isinstance(value, str) and value and not path.is_absolute()
            and '..' not in path.parts and str(path) == value and value != '.', 'Unsafe input path')
    return path


def inventory(task, gate_factory=None):
    """Contracts only: no trace or train receipt payload access before the complete gate."""
    if gate_factory is None:
        from finalization_control import FinalizationGate
        gate_factory = FinalizationGate
    gate = gate_factory(task)
    seal, seal_sha = gate.candidate_seal()
    from resource_support import seal_status
    require(seal.get('schema') == 'JBGS_GEOGS_CANDIDATES_SEALED_v2'
            and seal.get('status') == seal_status(gate.resource)
            and seal.get('scientific_verdict') is None and seal.get('reference_accessed') is False,
            'Actual complete resource-v3 seal in the explicit completion scope is required')
    files = seal['files']
    require(len({item['path'] for item in files}) == len(files), 'Duplicate sealed producer path')
    by_path = {item['path']:item for item in files}
    repeat_regions = gate.repeat.evaluable_regions
    require(repeat_regions in ([], list(gate.cfg['regions'])), 'An arbitrary subset of repetitions is prohibited')
    jobs = []
    for region in gate.cfg['regions']:
        for condition in [row['id'] for row in gate.cfg['conditions']]+([gate.repeat.identifier] if gate.repeat.evaluation_enabled(region) else []):
            repeated = condition == gate.repeat.identifier
            scientific_condition = 'D005_Pnative' if repeated else condition
            run = gate.repeat.run(region) if repeated else gate.layout.run(region, condition)
            controls = next(row for row in gate.cfg['conditions'] if row['id'] == scientific_condition)
            members = {}
            for field, relative in (('trace', 'model/jbgs_trace.jsonl'), ('train_receipt', 'train_receipt.json')):
                name = str((run/relative).relative_to(task))
                require(name in by_path, 'UNBOUND_CONTROL_INPUT: '+name+
                        '; require a separately reviewed post-seal binding receipt; this exporter cannot bypass the seal')
                item = by_path[name]
                safe_relative(item['path'])
                require(type(item.get('bytes')) is int and item['bytes'] > 0
                        and isinstance(item.get('sha256'), str) and len(item['sha256']) == 64,
                        'Trace/receipt lacks exact sealed SHA and byte count')
                members[field] = dict(path=item['path'], bytes=item['bytes'], sha256=item['sha256'])
            jobs.append(dict(region=region, condition=condition, scientific_condition=scientific_condition,
                supplemental_only=repeated, run_directory=str(run.relative_to(task)),
                training_start_iteration=8000 if repeated or gate.layout.starts_from_anchor(region, condition) else 0,
                declared_refinement_prior_weight=controls['lambda_lod_anchor'], protection=controls['protection'],
                anchor_checkpoint_directory=str(gate.layout.anchor_checkpoint(region).relative_to(task)), **members))
    require(len(jobs) == 18 + len(repeat_regions) and sum(job['supplemental_only'] for job in jobs) == len(repeat_regions),
            'Exactly 18 primary and only the explicitly evaluable repetitions required')
    require(len({job[field]['path'] for job in jobs for field in ('trace', 'train_receipt')}) == len(jobs) * 2,
            'Distinct producer trace/receipt inputs required for every declared completed run')
    completion_binding = {key:seal[key] for key in ('completion_contract_sha256', 'evaluation_scope') if key in seal}
    contract_names = ['execution_v1.json', 'runtime_layout_allocator_v2.json', 'supplemental_repeat_v1.json',
                      'extraction_resource_v3.json', 'candidates_sealed_v1.json']
    if seal.get('completion_contract_sha256'):
        contract_names.append('evaluation_completion_v2.json')
    return dict(schema='GEOGS_POSTSEAL_CONTROL_INPUT_INVENTORY_v1', scientific_verdict=None,
        candidate_seal_sha256=seal_sha, **{key:seal[key] for key in
        ('config_sha256', 'runtime_layout_sha256', 'repeat_contract_sha256', 'resource_contract_sha256')},
        jobs=jobs, evaluable_repeat_regions=repeat_regions, **completion_binding,
        supplemental_availability=seal.get('supplemental_availability', []),
        exporter_sha256=sha(__file__), trace_phase_field='NOT_RECORDED_IN_PINNED_TRACE',
        contract_files=[record(task, task/'contracts'/name) for name in contract_names],
        expected_state_instrumentation_sha256=STATE_SHA, expected_instrumented_train_sha256=TRAIN_SHA,
        trace_binding='Direct SHA/bytes binding in the complete candidate seal files inventory; no raw model or reference access')


def verify_inputs(task, access):
    """Verify every scoped sealed input before parsing any trace; never admit an unbound trace."""
    for job in access['jobs']:
        for field in ('trace', 'train_receipt'):
            item = job[field]
            path = task/safe_relative(item['path'])
            require(path.is_file() and record(task, path) == item, 'Sealed control input bytes changed: '+item['path'])
    for item in access['contract_files']:
        require(record(task, task/safe_relative(item['path'])) == item, 'Control contract/seal changed')


def finite(value, name, nonnegative=True):
    require(type(value) in (int, float) and math.isfinite(value)
            and (not nonnegative or value >= 0), 'Invalid finite control field: '+name)
    return float(value)


def parse_trace(text, job, iterations=30000, log_every=100):
    rows, previous = [], None
    for line_number, line in enumerate(text.splitlines(), 1):
        require(bool(line.strip()), 'Blank line in completed trace')
        raw = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON token')))
        require(isinstance(raw, dict), 'Trace row must be an object')
        iteration = raw['iteration']
        require(type(iteration) is int and job['training_start_iteration'] < iteration <= iterations,
                'Trace iteration outside this execution interval')
        require(type(raw['gaussians']) is int and type(raw['protected']) is int
                and 0 <= raw['protected'] <= raw['gaussians'], 'Invalid Gaussian/protected count')
        elapsed = finite(raw['elapsed_seconds'], 'elapsed_seconds')
        lod_weight, da_weight = finite(raw['lod_weight'], 'lod_weight'), finite(raw['da_weight'], 'da_weight')
        if previous:
            require(iteration > previous['global_iteration'] and elapsed >= previous['process_elapsed_seconds'],
                    'Duplicated/reversed iteration or elapsed clock reset')
        row = dict(region=job['region'], condition=job['condition'], scientific_condition=job['scientific_condition'],
            supplemental_only=job['supplemental_only'], training_start_iteration=job['training_start_iteration'],
            global_iteration=iteration, iterations_since_execution_start=iteration-job['training_start_iteration'],
            source_line_number=line_number, gaussians=raw['gaussians'], protected_gaussians=raw['protected'],
            prior_weight=lod_weight, da3_weight=da_weight, da_controller_phase=None,
            da_controller_phase_status='NOT_RECORDED_IN_PINNED_TRACE',
            process_elapsed_seconds=elapsed,
            previous_logged_iteration=previous['global_iteration'] if previous else None,
            logged_iteration_gap=iteration-previous['global_iteration'] if previous else None,
            elapsed_since_previous_logged_sample_seconds=elapsed-previous['process_elapsed_seconds'] if previous else None,
            per_step_seconds=None, trace_source_path=job['trace']['path'], trace_source_sha256=job['trace']['sha256'])
        rows.append(row)
        previous = row
    expected = list(range(job['training_start_iteration']+log_every, iterations+1, log_every))
    require(rows and [row['global_iteration'] for row in rows] == expected,
            'Incomplete fixed 100-iteration trace grid; no gap filling or interpolation is admitted')
    return rows


def run_summary(task, job, rows, access):
    receipt = read(task/job['train_receipt']['path'])
    require(all(receipt.get(key) == value for key, value in dict(region=job['region'],
        condition=job['scientific_condition'], phase='train', status='PASS', scientific_verdict=None,
        native_exit_code=0, validated_exit_code=0, runtime_image_id=IMAGE,
        training_start_iteration=job['training_start_iteration'], config_sha256=access['config_sha256'],
        runtime_layout_sha256=access['runtime_layout_sha256']).items()), 'Train receipt identity/starting state differs')
    if job['supplemental_only']:
        require(receipt.get('repeat_id') == 'native_repeat_1' and receipt.get('supplemental_only') is True
                and receipt.get('repeat_contract_sha256') == access['repeat_contract_sha256'], 'Native repeat receipt differs')
    source = receipt.get('implementation_hashes', {})
    require(source.get('jbgs_state.py') == STATE_SHA and source.get('train.py') == TRAIN_SHA,
            'Trace producer source differs from reviewed state/clock semantics')
    wall = finite(receipt['wall_seconds'], 'training_driver_phase_wall_seconds')
    anchor_rows = [row for row in rows if row['global_iteration'] == 8000]
    return dict(region=job['region'], condition=job['condition'], scientific_condition=job['scientific_condition'],
        supplemental_only=job['supplemental_only'], training_start_iteration=job['training_start_iteration'],
        actual_logged_samples=len(rows), first_logged_global_iteration=rows[0]['global_iteration'],
        last_logged_global_iteration=rows[-1]['global_iteration'],
        declared_refinement_prior_weight=job['declared_refinement_prior_weight'], protection=job['protection'],
        first_logged_gaussians=rows[0]['gaussians'], final_logged_gaussians=rows[-1]['gaussians'],
        first_logged_protected_gaussians=rows[0]['protected_gaussians'], final_logged_protected_gaussians=rows[-1]['protected_gaussians'],
        first_logged_prior_weight=rows[0]['prior_weight'], final_logged_prior_weight=rows[-1]['prior_weight'],
        first_logged_da3_weight=rows[0]['da3_weight'], final_logged_da3_weight=rows[-1]['da3_weight'],
        da_controller_phase_status='NOT_RECORDED_IN_PINNED_TRACE',
        first_logged_process_elapsed_seconds=rows[0]['process_elapsed_seconds'],
        last_logged_process_elapsed_seconds=rows[-1]['process_elapsed_seconds'],
        step8000_logged_process_elapsed_seconds=anchor_rows[0]['process_elapsed_seconds'] if anchor_rows else None,
        training_driver_phase_wall_seconds=wall, training_driver_wall_source_field='wall_seconds',
        driver_phase_wall_minus_last_trace_elapsed_seconds=wall-rows[-1]['process_elapsed_seconds'],
        clock_difference_interpretation='Distinct origins/scopes: invocation/input-manifest hash, pre-import work, monitoring, later capture and output validation/hash; not final-capture-only cost',
        full_pipeline_seconds=None, per_step_seconds=None, timing_interpretation=TIMING_NOTE,
        source_trace=job['trace']['path'], source_trace_sha256=job['trace']['sha256'],
        source_train_receipt=job['train_receipt']['path'], source_train_receipt_sha256=job['train_receipt']['sha256'],
        anchor_checkpoint_directory=job['anchor_checkpoint_directory'], scientific_verdict=None)


def csv_write(path, rows):
    require(bool(rows), 'Empty control export')
    with Path(path).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_region(output, region, rows, cfg, supplemental=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    primary_ids = [item['id'] for item in cfg['conditions']]
    conditions = ['D005_Pnative', 'native_repeat_1'] if supplemental else primary_ids
    selected = [row for row in rows if row['region']==region and row['condition'] in conditions]
    figure, axes = plt.subplots(3, 2, figsize=(13, 10), constrained_layout=True)
    columns = [('prior_weight', 'Prior depth weight - full trace', 1.),
               ('prior_weight', 'Prior depth weight - refinement detail', 1.),
               ('da3_weight', 'Realized DA3 depth weight', 1.),
               ('gaussians', 'Gaussians in whole training context (millions)', 1e6),
               ('protected_gaussians', 'Protected Gaussians in whole context (thousands)', 1e3),
               ('process_elapsed_seconds', 'Cumulative process elapsed (minutes)\nDifferent starts; not matched compute time', 60.)]
    colors = {'D005':'#1b6ca8', 'D0005':'#e38b16', 'D0':'#269c62'}
    plotted = []
    for index, (field, title, scale) in enumerate(columns):
        axis = axes.flat[index]
        for condition in conditions:
            members = [row for row in selected if row['condition']==condition]
            if index == 1:
                members = [row for row in members if row['global_iteration'] > cfg['training']['anchor_end']]
            require(members, 'Declared regional control curve missing')
            color = ('#222222' if condition=='D005_Pnative' else '#9651b0') if supplemental else colors[condition.split('_')[0]]
            style = '--' if condition.endswith('Prelease') or condition=='native_repeat_1' else '-'
            starts = {row['training_start_iteration'] for row in members}
            require(len(starts) == 1, 'Mixed execution starts in one plotted curve')
            start = next(iter(starts))
            label = condition+f' [start {start}'+('; separate repeat]' if condition=='native_repeat_1' else ']')
            axis.plot([row['global_iteration'] for row in members], [row[field]/scale for row in members],
                      color=color, linestyle=style, linewidth=1.4, label=label)
            plotted.append(dict(panel=index, condition=condition, label=label, training_start_iteration=start, sample_count=len(members),
                                source_iterations=[row['global_iteration'] for row in members]))
        axis.axvline(cfg['training']['anchor_end'], color='#555555', linewidth=.7, linestyle=':')
        axis.axvline(cfg['training']['densify_until_iter'], color='#999999', linewidth=.7, linestyle=':')
        axis.set(title=title, xlabel='Global training iteration', xlim=(0, cfg['training']['iterations']))
        axis.grid(alpha=.18)
        if index != 1:
            axis.set_ylim(bottom=0)
        if index == 1:
            axis.set_xlim(cfg['training']['anchor_end']+1, cfg['training']['iterations'])
            weights = [row[field] for row in selected if row['global_iteration'] > cfg['training']['anchor_end']]
            # Show all actual refinement values, including any unexpected excursion.
            upper = max([item['lambda_lod_anchor'] for item in cfg['conditions']]+weights)
            axis.set_ylim(-max(upper*.04, 1e-5), max(upper*1.08, 1e-4))
    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc='outside lower center', ncol=2 if supplemental else 3, fontsize=8)
    kind = 'native_repeat_diagnostic' if supplemental else 'primary_six_conditions'
    fixture = 'SYNTHETIC VALIDATION - ' if cfg.get('synthetic_fixture_only') else ''
    figure.suptitle(fixture+f'{region}: '+('primary native and one separately marked repeat' if supplemental else 'all six primary control trajectories')+
        '\n100-iteration samples; connecting lines are guides, not exact change times. No prefix added to resumed runs.'+
        '\nVertical guides: anchor 8000 / densification boundary 15000; elapsed is cumulative process time, not isolated optimization.', fontsize=10)
    stem = region+'_'+kind
    for extension in ('png', 'pdf'):
        figure.savefig(output/(stem+'.'+extension), dpi=160)
    plt.close(figure)
    return dict(region=region, figure_family=kind, plotted_series=plotted,
        files=[stem+'.png', stem+'.pdf'], no_extrapolated_anchor_prefix=True,
        synthetic_fixture_only=bool(cfg.get('synthetic_fixture_only')),
        fixed_schedule_annotations_only=True, phase_not_inferred=True,
        counts_are_whole_context=True, cumulative_elapsed_not_per_step=True)


def extract(task, output, access, cfg):
    verify_inputs(task, access)
    primary, repeated, summaries = [], [], []
    for job in access['jobs']:
        rows = parse_trace((task/job['trace']['path']).read_text(), job, cfg['training']['iterations'])
        summaries.append(run_summary(task, job, rows, access))
        (repeated if job['supplemental_only'] else primary).extend(rows)
    verify_inputs(task, access)
    output.mkdir(parents=True, exist_ok=False)
    csv_write(output/'primary_control_samples.csv', primary)
    if repeated:
        csv_write(output/'native_repeat_control_samples.csv', repeated)
    csv_write(output/'run_control_summary.csv', summaries)
    figures = []
    for region in cfg['regions']:
        for supplemental in ((False, True) if any(row['region']==region for row in repeated) else (False,)):
            figures.append(plot_region(output, region, primary+repeated, cfg, supplemental))
    if not repeated:
        dump(output/'supplemental_control_status.json', dict(scientific_verdict=None,
            status='NOT_ASSESSED_NO_COMPLETED_SUPPLEMENTAL_EXECUTIONS',
            supplemental_availability=access.get('supplemental_availability', []),
            completed_repeat_curves=0, failed_or_unattempted_trace_payloads_opened=False,
            paired_quality_variation_assessed=False))
    dump(output/'figure_index.json', dict(figures=figures, scientific_verdict=None,
        timing_note=TIMING_NOTE, control_note=CONTROL_NOTE, loss_quality_fields_exported=False))
    return dict(schema='GEOGS_POSTSEAL_CONTROL_TRAJECTORIES_v1', status='CONTROL_CURVES_AND_TABLES_READY',
        scientific_verdict=None, completed_at_utc=datetime.now(timezone.utc).isoformat(),
        candidate_seal_sha256=access['candidate_seal_sha256'], input_inventory=access,
        primary_samples=len(primary), supplemental_samples=len(repeated), completed_runs=len(summaries),
        figures=len(figures), files=[record(output, path) for path in sorted(output.iterdir())],
        control_note=CONTROL_NOTE, timing_note=TIMING_NOTE, da_phase='NOT_RECORDED_IN_PINNED_TRACE',
        loss_quality_fields_exported=False, reference_payload_read=False, checkpoint_loaded=False,
        existing_outputs_modified=False, best_run_selected=False, confidence_interval=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=('inventory', 'extract'))
    parser.add_argument('--task', type=Path, default=Path('/task'))
    parser.add_argument('--attempt', type=Path, default=Path('/out'))
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists()
            and not Path('/artifacts/JointBuildGS').exists(), 'Docker without reference/broad artifact mounts required')
    expected = inventory(args.task)
    if args.mode == 'inventory':
        dump(args.attempt/'input_gate.json', expected)
        with (args.attempt/'mount_relative_paths.txt').open('x') as stream:
            for job in expected['jobs']:
                for field in ('trace', 'train_receipt'):
                    stream.write(job[field]['path']+'\n')
        print(json.dumps(dict(status='DECLARED_CONTROL_INPUTS_BOUND_BEFORE_PAYLOAD_ACCESS', runs=len(expected['jobs']), scientific_verdict=None)))
        return
    require(read(args.attempt/'input_gate.json') == expected, 'Access inventory or seal changed between Docker stages')
    cfg = read(args.task/'contracts/execution_v1.json')
    result = extract(args.task, args.attempt/'results', expected, cfg)
    result.update(runtime_image_id=os.environ.get('EXECUTION_IMAGE_ID'), git_head=os.environ.get('EXECUTION_GIT_HEAD'),
        python_version=platform.python_version(), command_argv=sys.argv,
        source_files=[record(Path(__file__).parent, path) for path in sorted(Path(__file__).parent.rglob('*')) if path.is_file()],
        execution_files=[record(args.attempt, args.attempt/name) for name in
                         ('input_gate.json', 'mount_relative_paths.txt', 'commands.sh', 'image_id.txt', 'git_head.txt', 'launcher_snapshot.sh')])
    import matplotlib
    result['matplotlib_version'] = matplotlib.__version__
    dump(args.attempt/'results/receipt.json', result)
    print(json.dumps({key:result[key] for key in ('status', 'completed_runs', 'primary_samples', 'supplemental_samples', 'scientific_verdict')}))


if __name__ == '__main__':
    main()
