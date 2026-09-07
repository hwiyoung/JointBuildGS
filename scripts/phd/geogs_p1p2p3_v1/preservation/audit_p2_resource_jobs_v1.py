"""Read-only all-P2 receipt/cgroup audit; no model, metric or reference payloads."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

CONDITIONS = ('D005_Pnative', 'D0005_Pnative', 'D0_Pnative', 'D005_Prelease', 'D0005_Prelease', 'D0_Prelease')
IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
BINDING = dict(config_sha256='b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4',
    runtime_layout_sha256='28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5',
    resource_contract_sha256='804f371b9db70b089daccdba2052df8c71b54b5d20acba2ea2f5c6d3d7eb7efa',
    input_manifest_sha256='6493c602332144510526a54f31700c28cb31eb648250e690d6528fcffe5162a2')
CAP = 32*1024**3
SPEC = dict(schema='GEOGS_P2_ALL_RESOURCE_MEMORY_AUDIT_v1', region='P2', conditions=list(CONDITIONS),
    variants=14, memory_limit_bytes=CAP, expected_original_services=62, runtime_image_id=IMAGE,
    scientific_verdict=None, binding=BINDING)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def plans(condition):
    result = [('anchor_512', 8000, 512, True), ('anchor', 8000, 1024, False)] if condition=='D005_Pnative' else []
    return result+[('mesh_512', 30000, 512, True), ('mesh_2048', 30000, 2048, False)]


def resource_audit():
    start = time.monotonic()
    root, output = Path('/resource'), Path('/out')
    cfg = read(output/'audit_config.json')
    require(cfg['specification'] == SPEC, 'Audit specification differs')
    inputs, jobs, outer_by_condition = [], [], {}
    # Establish every completion before inspecting any variant memory trace.
    for condition in CONDITIONS:
        marker = Path('/queue_done')/('P2_'+condition)
        completion_path = Path('/completion')/(condition+'.json')
        target = os.path.normpath(marker.read_text().strip())
        prefix = cfg['task_host_root']+'/queue_allocator_v2/resource_v3/claims/P2_'+condition+'/'
        require(target.startswith(prefix) and target.endswith('/complete.json')
                and len(Path(target[len(prefix):]).parts)==2
                and Path(target).parent.name.startswith('attempt.'), 'Completion marker target differs')
        completion = read(completion_path)
        require(all(completion.get(key)==value for key, value in dict(
            status='ALL_FOUR_RESOURCE_PHASES_VERIFIED', region='P2', condition=condition,
            run_family='primary', scientific_verdict=None,
            resource_contract_sha256=BINDING['resource_contract_sha256']).items()), 'P2 completion receipt incomplete')
        outer_path = root/condition/'auxiliary_receipt.json'
        outer = read(outer_path)
        require(all(outer.get(key)==value for key, value in dict(region='P2', condition=condition,
            phase='auxiliary', run_family='primary', status='PASS', native_exit_code=0, validated_exit_code=0,
            scientific_verdict=None, runtime_image_id=IMAGE, **BINDING).items()), 'P2 aggregate auxiliary identity differs')
        completed = [item for item in completion['files'] if item['path']==f'extraction_resource_v3/primary/P2/{condition}/auxiliary_receipt.json']
        require(len(completed)==1 and completed[0]['bytes']==outer_path.stat().st_size
                and completed[0]['sha256']==sha(outer_path), 'Aggregate receipt differs from completed job')
        expected_names = {row[0] for row in plans(condition)}
        require(len(outer['variants'])==len(expected_names) and {row['name'] for row in outer['variants']}==expected_names,
                'Aggregate variant inventory incomplete or duplicated')
        outer_by_condition[condition] = outer
        inputs.extend(map(record, (marker, completion_path, outer_path)))
        jobs.append(dict(condition=condition, completion_target_host_path=target,
            completion_receipt_sha256=sha(completion_path), done_marker_sha256=sha(marker),
            auxiliary_receipt_sha256=sha(outer_path), status=completion['status']))
    rows = []
    for condition in CONDITIONS:
        for variant, iteration, mesh_res, required in plans(condition):
            directory = root/condition/'auxiliary'/variant
            path = directory/'receipt.json'
            receipt = read(path)
            require(all(receipt.get(key)==value for key, value in dict(region='P2', condition=condition,
                phase='auxiliary_variant', run_family='primary', variant=variant, iteration=iteration,
                mesh_res=mesh_res, required=required, scientific_verdict=None, runtime_image_id=IMAGE,
                **BINDING).items()), 'Variant identity/control binding differs: '+condition+'/'+variant)
            declared = next(row for row in outer_by_condition[condition]['variants'] if row['name']==variant)
            require(declared['receipt_path']==f'auxiliary/{variant}/receipt.json'
                    and declared['receipt_sha256']==sha(path) and declared['status']==receipt['status'],
                    'Variant differs from completed auxiliary receipt')
            require(receipt['memory_trace']['path']=='memory.jsonl', 'Unexpected memory trace path')
            trace_path = directory/'memory.jsonl'
            require(sha(trace_path)==receipt['memory_trace']['sha256'], 'Memory trace hash differs')
            trace = [json.loads(line) for line in trace_path.read_text().splitlines()]
            require(trace and trace[0]==receipt['memory_before'] and trace[-1]==receipt['memory_after'],
                    'Memory before/after differs from trace endpoints')
            require(receipt['cgroup_memory_limit_bytes']==CAP and all(int(sample['memory_max'])==CAP for sample in trace),
                    'Every memory sample must retain the exact 32GiB cap')
            for sample in trace:
                require(all(type(sample[key]) is int and sample[key]>=0 for key in
                    ('memory_current_bytes', 'memory_peak_bytes', 'host_mem_available_bytes'))
                    and math.isfinite(sample['unix']), 'Invalid memory sample value')
            delta = trace[-1]['memory_events']['oom_kill']-trace[0]['memory_events']['oom_kill']
            require(delta==receipt['cgroup_oom_kill_delta'], 'OOM delta differs from receipt')
            if receipt['status']=='TECHNICAL_RESOURCE_UNAVAILABLE':
                require(not required and receipt['native_exit_code']==-9 and delta==1,
                        'Optional unavailability lacks exact native -9 / OOM-kill delta1 proof')
            else:
                require(receipt['status']=='PASS' and receipt['native_exit_code']==0
                        and receipt['validated_exit_code']==0 and delta==0, 'Required/PASS variant did not complete without OOM')
            require(not required or receipt['status']=='PASS', 'Required extraction is unavailable')
            minimum = min(sample['host_mem_available_bytes'] for sample in trace)
            peak = max(sample['memory_current_bytes'] for sample in trace)
            require(minimum==receipt['sampled_min_host_mem_available_bytes']
                    and peak==receipt['sampled_peak_memory_current_bytes'], 'Recorded sampled extrema differ')
            inputs.extend(map(record, (path, trace_path)))
            rows.append(dict(condition=condition, variant=variant, iteration=iteration, mesh_res=mesh_res,
                required=required, status=receipt['status'], memory_limit_bytes=CAP,
                trace_samples=len(trace), cgroup_oom_kill_before=trace[0]['memory_events']['oom_kill'],
                cgroup_oom_kill_after=trace[-1]['memory_events']['oom_kill'], cgroup_oom_kill_delta=delta,
                native_exit_code=receipt['native_exit_code'], validated_exit_code=receipt['validated_exit_code'],
                sampled_peak_memory_current_bytes=peak, cgroup_lifetime_peak_bytes=trace[-1]['memory_peak_bytes'],
                sampled_min_host_mem_available_bytes=minimum, sampled_min_host_mem_available_gib=minimum/1024**3,
                first_sample_unix=trace[0]['unix'], last_sample_unix=trace[-1]['unix'],
                receipt_wall_seconds=receipt['wall_seconds'], receipt_source_path=str(path), receipt_sha256=sha(path),
                memory_trace_sha256=sha(trace_path), scientific_verdict=None))
    require(len(rows)==14, 'Exactly all14 P2 variants required')
    # Closed input metadata and traces must remain unchanged during this audit.
    require(all(record(item['path'])==item for item in inputs), 'Audit input changed during inspection')
    result = dict(schema=SPEC['schema'], status='PASS_RECEIPT_AND_CGROUP_TRACE_BINDINGS', scientific_verdict=None,
        completed_at_utc=datetime.now(timezone.utc).isoformat(), audit_wall_seconds=time.monotonic()-start,
        region='P2', completed_primary_jobs=len(jobs), completion_jobs=jobs, variants=len(rows), rows=rows,
        required_passes=sum(row['required'] and row['status']=='PASS' for row in rows),
        optional_passes=sum(not row['required'] and row['status']=='PASS' for row in rows),
        confirmed_optional_ooms=sum(row['status']=='TECHNICAL_RESOURCE_UNAVAILABLE' for row in rows),
        minimum_sampled_host_available_bytes=min(row['sampled_min_host_mem_available_bytes'] for row in rows),
        source_sha256=sha(__file__), config_sha256=sha(output/'audit_config.json'), input_files=inputs,
        runtime_image_id=IMAGE, python_version=platform.python_version(), command_argv=sys.argv,
        reference_accessed=False, regional_quality_accessed=False, model_or_mesh_payload_accessed=False,
        limitation='Periodic host-memory samples are not continuous minima. Cgroup lifetime peak is cumulative within an auxiliary container. Receipts/trace binding is not surface-quality, payload-preservation or service-health evidence.')
    dump(output/'resource_memory_audit.json', result)
    print(json.dumps({key:result[key] for key in ('status', 'completed_primary_jobs', 'variants', 'required_passes',
                                              'optional_passes', 'confirmed_optional_ooms', 'minimum_sampled_host_available_bytes')}))


def finalize(receipt_name):
    output = Path('/out')
    resource = read(output/'resource_memory_audit.json') if (output/'resource_memory_audit.json').exists() else {}
    service = read(output/'service_receipt.json') if (output/'service_receipt.json').exists() else {}
    passes = (resource.get('status')=='PASS_RECEIPT_AND_CGROUP_TRACE_BINDINGS'
              and resource.get('completed_primary_jobs')==6 and resource.get('variants')==14
              and service.get('status')=='PASS' and service.get('baseline_count')==62 and service.get('identity_pass_count')==62)
    previous = None
    if receipt_name == 'audit_receipt_v2.json':
        prior_path = output/'audit_receipt.json'
        prior = read(prior_path)
        differences = [dict(recorded=item, actual=record(item['path'])) for item in prior['evidence_files']
                       if record(item['path']) != item]
        require(all(Path(item['recorded']['path']).name in ('finalize_stdout.log', 'finalize_stderr.log')
                    for item in differences), 'An original closed resource/service input changed during bookkeeping correction')
        previous = dict(receipt=record(prior_path), differences=differences,
                        correction='Only active finalizer stream hashing is superseded; original resource/service results and all original evidence are preserved')
    # Current stdout/stderr are still open. Hashing them here produces stale hashes.
    finalizer_streams = [path for path in output.iterdir() if path.is_file()
                         and path.name.startswith('finalize') and path.suffix=='.log']
    excluded = {path.name for path in finalizer_streams}|{'overall_exit_code.txt'}
    result = dict(status='PASS_P2_RESOURCE_BINDINGS_AND_CURRENT_SERVICE_IDENTITIES' if passes else 'DIFFERENCE_OR_FAILURE_REQUIRES_REVIEW',
        scientific_verdict=None, completed_at_utc=datetime.now(timezone.utc).isoformat(),
        bookkeeping_revision='CLOSED_EVIDENCE_FILES_v2', superseded_log_bookkeeping=previous,
        resource_status=resource.get('status'), service_status=service.get('status'),
        original_services=service.get('baseline_count'), identity_matches=service.get('identity_pass_count'),
        git_head=(output/'git_head.txt').read_text().strip(), runtime_image_id=(output/'image_id.txt').read_text().strip(),
        sources=[record(path) for path in sorted(Path('/code').iterdir()) if path.is_file()],
        evidence_files=[record(path) for path in sorted(output.iterdir()) if path.is_file() and path.name not in excluded],
        intentionally_unhashed_finalizer_streams=sorted(str(path) for path in finalizer_streams),
        reference_accessed=False, regional_quality_accessed=False, deferred_baseline_payloads_hashed=False,
        limitation='Only current original62 service ID/name/default-image-descriptor/ports/running identity; no never-restarted, browser health, data-byte or durable-backup claim.')
    dump(output/receipt_name, result)
    print(json.dumps({key:result[key] for key in ('status', 'original_services', 'identity_matches', 'scientific_verdict')}))
    return 0 if passes else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=('resource', 'finalize'))
    parser.add_argument('--final-receipt-name', choices=('audit_receipt.json', 'audit_receipt_v2.json'), default='audit_receipt.json')
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists()
            and not Path('/artifacts/JointBuildGS').exists(), 'Scoped Docker audit without reference required')
    try:
        if args.mode=='resource':
            resource_audit()
        else:
            raise SystemExit(finalize(args.final_receipt_name))
    except Exception as error:
        dump(Path('/out')/(args.mode+'_failure_receipt.json'), dict(status='FAIL', error=repr(error),
            scientific_verdict=None, source_sha256=sha(__file__), checked_at_utc=datetime.now(timezone.utc).isoformat()))
        raise


if __name__ == '__main__':
    main()
