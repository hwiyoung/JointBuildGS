"""Read only the first two resource receipts and their cgroup traces, in Docker."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert Path('/.dockerenv').exists()
    assert not Path('/reference').exists()
    root = Path('/resource')
    cap = 32 * 1024**3
    rows = []
    for condition, variants in (
        ('D005_Pnative', ('anchor_512', 'anchor', 'mesh_512', 'mesh_2048')),
        ('D0005_Pnative', ('mesh_512', 'mesh_2048')),
    ):
        for variant in variants:
            directory = root/condition/'auxiliary'/variant
            path = directory/'receipt.json'
            receipt = json.loads(path.read_text())
            trace_path = directory/receipt['memory_trace']['path']
            trace = [json.loads(line) for line in trace_path.read_text().splitlines()]
            assert sha(trace_path) == receipt['memory_trace']['sha256']
            assert trace[0] == receipt['memory_before'] and trace[-1] == receipt['memory_after']
            assert all(int(sample['memory_max']) == cap for sample in trace)
            delta = trace[-1]['memory_events']['oom_kill'] - trace[0]['memory_events']['oom_kill']
            assert delta == receipt['cgroup_oom_kill_delta']
            if receipt['status'] == 'TECHNICAL_RESOURCE_UNAVAILABLE':
                assert not receipt['required'] and receipt['native_exit_code'] == -9 and delta >= 1
            else:
                assert receipt['status'] == 'PASS' and receipt['native_exit_code'] == 0 and delta == 0
            minimum = min(sample['host_mem_available_bytes'] for sample in trace)
            assert minimum == receipt['sampled_min_host_mem_available_bytes']
            assert receipt['scientific_verdict'] is None
            rows.append(dict(condition=condition, variant=variant, status=receipt['status'],
                required=receipt['required'], memory_limit_bytes=cap, cgroup_oom_kill_delta=delta,
                sampled_peak_memory_current_bytes=max(s['memory_current_bytes'] for s in trace),
                cgroup_lifetime_peak_bytes=trace[-1]['memory_peak_bytes'],
                sampled_min_host_mem_available_bytes=minimum,
                native_wall_seconds=receipt['wall_seconds'], native_exit_code=receipt['native_exit_code'],
                receipt_path=str(path.relative_to(root)), receipt_sha256=sha(path),
                memory_trace_sha256=sha(trace_path)))
    report = dict(status='PASS_RECEIPT_AND_CGROUP_TRACE_BINDINGS', rows=rows,
        required_passes=sum(row['required'] and row['status']=='PASS' for row in rows),
        confirmed_optional_ooms=sum(row['status']=='TECHNICAL_RESOURCE_UNAVAILABLE' for row in rows),
        minimum_sampled_host_available_bytes=min(row['sampled_min_host_mem_available_bytes'] for row in rows),
        scientific_verdict=None, source_sha256=sha(Path(__file__)), reference_accessed=False,
        regional_quality_accessed=False,
        limitation='Memory samples are periodic; cgroup lifetime peak is cumulative within each auxiliary container. No model, metric or UAS payload is opened.')
    with Path('/out/resource_memory_audit.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({key:report[key] for key in ('status','required_passes','confirmed_optional_ooms','minimum_sampled_host_available_bytes')}))


if __name__ == '__main__':
    main()
