"""Read six exact technical preflight records and write one add-once summary."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform


ATTEMPTS = {
    ('P1', 'mvs'): 'attempt.IMIQySUd',
    ('P1', 'mvs_pgsr'): 'attempt.ZdEkuOGJ',
    ('P2', 'mvs'): 'attempt.V38OnSZZ',
    ('P2', 'mvs_pgsr'): 'attempt.zWaYG9SA',
    ('P3', 'mvs'): 'attempt.lcfos4FL',
    ('P3', 'mvs_pgsr'): 'attempt.i8DrX4lX',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def json_file(path):
    return json.loads(Path(path).read_text())


def json_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--input-receipt', type=Path, required=True)
    parser.add_argument('--source-provenance', type=Path, required=True)
    parser.add_argument('--operator-head', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker execution required')
    require(not args.output.exists(), 'Summary output already exists')
    import numpy as np
    import torch
    import cv2
    import open3d
    config = json_file(args.config)
    inputs = json_file(args.input_receipt)
    source = json_file(args.source_provenance)
    config_sha, source_sha = sha(args.config), sha(args.source_provenance)
    require(inputs['config_sha256'] == config_sha, 'Input/config binding differs')
    records = []
    input_hashes = {str(p): sha(p) for p in (args.config, args.input_receipt, args.source_provenance)}
    for (region, mode), attempt in ATTEMPTS.items():
        relative = Path(region) / (mode + '_0.005') / attempt
        root = args.preflight / relative
        files = ['receipt.json', 'invocation.json', 'driver_snapshot.py', 'experiment_snapshot.json',
                 'gpu.csv', 'model/jbgs_restore.json', 'model/mvs_pgsr_trace.jsonl',
                 'model/mvs_pgsr_gradient_trace.jsonl', 'model/jbgs_complete/iteration_8100/receipt.json']
        if mode == 'mvs_pgsr':
            files.append('model/geometry_first_step_gradients.json')
        hashes = {name: sha(root / name) for name in files}
        input_hashes.update({str(root / name): digest for name, digest in hashes.items()})
        receipt = json_file(root / 'receipt.json')
        restore = json_file(root / 'model/jbgs_restore.json')
        traces = json_lines(root / 'model/mvs_pgsr_trace.jsonl')
        gradients = json_lines(root / 'model/mvs_pgsr_gradient_trace.jsonl')
        require(receipt['status'] == 'PASS' and receipt['completed'] and receipt['exit_code'] == 0,
                'Preflight was not completed successfully')
        require(receipt['region'] == region and receipt['mode'] == mode and receipt['prior'] == .005,
                'Preflight identity differs')
        require(receipt['final_iteration'] == 8100 and receipt['scientific_verdict'] is None,
                'Preflight endpoint/verdict differs')
        require(receipt['config_sha256'] == config_sha == hashes['experiment_snapshot.json'],
                'Actual configuration snapshot differs')
        require(receipt['source_provenance_sha256'] == source_sha, 'Prepared source differs')
        require(receipt['binding_sha256'] == inputs['regions'][region]['binding_sha256'], 'Input binding differs')
        require(receipt['driver_sha256'] == hashes['driver_snapshot.py'], 'Actual driver snapshot differs')
        require(receipt['runtime_image_id'] == config['runtime_image_id'], 'Runtime image differs')
        require(receipt['restore'] == restore and restore['checkpoint_sha256'] == config['anchors'][region]['sha256'],
                'Parent anchor restore differs')
        equality = restore['restore_equivalence']
        restore_exact = (equality['status'] == 'PASS' and equality['protection'] == 'native_exact'
                         and all(equality[key] is True for key in (
                             'model_optimizer_exact', 'controller_exact', 'camera_order_and_stack_exact', 'rng_exact')))
        require(restore_exact, 'Complete anchor equivalence did not pass')
        require(traces[0]['iteration'] == 8001 and traces[-1]['iteration'] == 8100,
                'Required loss trace endpoints missing')
        require(gradients[0]['iteration'] == 8001 and gradients[-1]['iteration'] == 8100,
                'Required gradient trace endpoints missing')
        for trace in traces:
            require(trace['prior_weight'] == .005 and trace['visual_source'] == 'COLMAP_MVS_CAMERA_Z',
                    'Actual supervision differs')
            require(all(math.isfinite(trace[key]) for key in (
                'prior_loss', 'mvs_loss', 'prior_weight', 'mvs_weight', 'geometry_weighted_total', 'rgb_loss')),
                'Nonfinite logged objective')
        total_gradients_finite = all(v.get('finite') is True for row in gradients
                                     for v in row['total_loss_gradients'].values() if v['present'])
        require(total_gradients_finite, 'Nonfinite logged total gradient')
        per_term = json_file(root / 'model/geometry_first_step_gradients.json') if mode == 'mvs_pgsr' else None
        if per_term is not None:
            require(per_term['iteration'] == 8001 and per_term['protected_hooks_applied'] is True,
                    'Per-term gradient stage differs')
            require(set(per_term['per_term_gradients']) == {'svgeo', 'mvrgb', 'mvgeom'},
                    'Expected three geometry terms')
            for term, variables in per_term['per_term_gradients'].items():
                require(all(v['present'] and v['finite'] and v['nonzero_elements'] > 0 for v in variables.values()),
                        'Geometry term lacks finite nonzero gradients: ' + term)
        records.append(dict(region=region, mode=mode, prior=.005, relative=str(Path('preflight')/relative),
                            status=receipt['status'], wall_seconds=receipt['wall_seconds'],
                            start_iteration=8000, final_iteration=8100, completed_updates=100,
                            restore_exact=restore_exact, restore=restore, config_sha256=config_sha,
                            source_provenance_sha256=source_sha, binding_sha256=receipt['binding_sha256'],
                            runtime_image_id=receipt['runtime_image_id'], driver_sha256=receipt['driver_sha256'],
                            logged_loss_rows=len(traces), first_trace=traces[0], final_trace=traces[-1],
                            logged_gradient_rows=len(gradients), first_total_gradient=gradients[0],
                            final_total_gradient=gradients[-1], total_gradients_finite=total_gradients_finite,
                            first_step_per_term_gradients=per_term,
                            peak_cuda_allocated_bytes=max(row['peak_cuda_allocated_bytes'] for row in gradients),
                            peak_cuda_reserved_bytes=max(row['peak_cuda_reserved_bytes'] for row in gradients),
                            source_file_sha256=hashes,
                            completed_checkpoint_verification=receipt['verified_outputs']))
    for path, digest in input_hashes.items():
        require(sha(path) == digest, 'Input changed during summary: ' + path)
    summary = dict(schema='JBGS_MVS_PGSR_PREFLIGHT_SUMMARY_v1', task_id=config['task_id'],
                   created_utc=datetime.now(timezone.utc).isoformat(), scientific_verdict=None,
                   status='PASS_SIX_TECHNICAL_PREFLIGHTS', operator_head=args.operator_head,
                   runtime_versions_inspected_in_same_pinned_cpu_image=dict(
                       python=platform.python_version(), torch=torch.__version__, torch_cuda_build=torch.version.cuda,
                       numpy=np.__version__, opencv=cv2.__version__, open3d=open3d.__version__),
                   runtime_image_id=config['runtime_image_id'], allocator=config['allocator'],
                   config_sha256=config_sha, input_receipt_sha256=sha(args.input_receipt),
                   source_provenance_sha256=source_sha, source_parent_path=source['parent_path'],
                   source_prepared_path=source['prepared_path'], summarizer_sha256=sha(__file__),
                   arguments=vars(args) | {'preflight':str(args.preflight),'config':str(args.config),
                       'input_receipt':str(args.input_receipt),'source_provenance':str(args.source_provenance),
                       'output':str(args.output)},
                   input_hashes=input_hashes, input_hashes_unchanged=True, records=records,
                   interpretation=dict(scope='100-step integration and resource diagnostic only',
                       scientific_result=False, main_matrix_complete=False,
                       observed_prior_weights=[.005], planned_main_prior_weights=[.005,.0005],
                       unprobed_prior_note='0.0005 changes the existing scalar prior coefficient from the same complete anchor; no 0.0005 preflight result is claimed',
                       memory_note='Maximum recorded PyTorch cumulative allocator peaks at instrumented updates; allocated and reserved differ; nvidia-smi device totals are not process allocations',
                       geometry_counts_note='MVS-only does not apply added PGSR terms, so their counts are unmeasured rather than zero',
                       trace_note='Finite and gradient assertions cover logged iterations; checkpoint endpoint establishes completion, not per-step scientific accuracy'))
    with args.output.open('x') as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status':summary['status'],'output_sha256':sha(args.output),'versions':summary['runtime_versions_inspected_in_same_pinned_cpu_image']}))
    for r in records:
        print(json.dumps({'region':r['region'],'mode':r['mode'],'wall_seconds':r['wall_seconds'],
                          'peak_allocated_mib':r['peak_cuda_allocated_bytes']/2**20,
                          'peak_reserved_mib':r['peak_cuda_reserved_bytes']/2**20,
                          'first_counts':r['first_trace'].get('counts'),'final_counts':r['final_trace'].get('counts'),
                          'first_step_per_term_gradients':r['first_step_per_term_gradients']}))


if __name__ == '__main__':
    main()
