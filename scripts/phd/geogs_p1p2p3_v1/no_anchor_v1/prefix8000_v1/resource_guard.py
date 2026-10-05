"""CPU-only boundary gate for an exact preserved desktop process; no GPU work."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import time

DESKTOP = dict(gpu=0, pid=72937, start_ticks=60213,
               executable='/usr/libexec/gnome-remote-desktop-daemon', comm='gnome-remote-de',
               maximum_used_memory_mib=512)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_rows(text):
    rows = []
    for row in csv.reader(io.StringIO(text)):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != 3:
            raise ValueError('Unexpected nvidia compute row shape')
        pid, name, memory = [value.strip() for value in row]
        if not pid.isdecimal() or not memory.isdecimal() or int(pid) <= 0:
            raise ValueError('Unknown process or GPU memory accounting')
        rows.append(dict(pid=int(pid), executable=name, used_memory_mib=int(memory)))
    if len({row['pid'] for row in rows}) != len(rows):
        raise ValueError('Duplicate GPU process identity')
    return rows


def admit(gpu, text, stat='', comm='', executable=''):
    if gpu not in (0, 1):
        raise ValueError('Unsupported GPU')
    rows = parse_rows(text)
    for row in rows:
        if (gpu != DESKTOP['gpu'] or row['pid'] != DESKTOP['pid']
                or row['executable'] != DESKTOP['executable']
                or row['used_memory_mib'] > DESKTOP['maximum_used_memory_mib']):
            raise ValueError('Another compute process is active; export must not start')
        prefix, separator, rest = stat.strip().rpartition(') ')
        pid, opening, name = prefix.partition(' (')
        fields = rest.split()
        if (not separator or not opening or pid != str(DESKTOP['pid'])
                or name != DESKTOP['comm'] or len(fields) <= 19
                or fields[0] in ('Z', 'X', 'x') or not fields[19].isdecimal()
                or int(fields[19]) != DESKTOP['start_ticks']
                or comm.strip() != DESKTOP['comm'] or executable.strip() != DESKTOP['executable']):
            raise ValueError('Preserved desktop PID was reused or its process identity changed')
    return dict(gpu=gpu, process_rows=rows, desktop_allowance_used=bool(rows),
                all_other_compute_processes_absent=True, exact_desktop_allowance=DESKTOP)


def observe(root, phase, gpu):
    required = ['compute.csv', 'gpu.csv', 'nvidia_exit.txt', 'gpu_query_exit.txt',
                'proc_stat.txt', 'proc_comm.txt', 'proc_exe.txt']
    records = {}
    for suffix in required:
        path = root / (phase + '_' + suffix)
        records[path.name] = dict(filename=path.name, bytes=path.stat().st_size, sha256=sha(path))
    if (root / (phase + '_nvidia_exit.txt')).read_text().strip() != '0' or (
            root / (phase + '_gpu_query_exit.txt')).read_text().strip() != '0':
        raise ValueError('GPU observation failed; fail closed')
    gpu_rows = list(csv.reader(io.StringIO((root / (phase + '_gpu.csv')).read_text())))
    if (len(gpu_rows) != 1 or len(gpu_rows[0]) != 5 or gpu_rows[0][0].strip() != str(gpu)
            or not gpu_rows[0][1].strip().startswith('GPU-')):
        raise ValueError('GPU state identity is missing or differs from requested lane')
    result = admit(gpu, (root / (phase + '_compute.csv')).read_text(),
        (root / (phase + '_proc_stat.txt')).read_text(),
        (root / (phase + '_proc_comm.txt')).read_text(),
        (root / (phase + '_proc_exe.txt')).read_text())
    return dict(result, observations=records)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    parser.add_argument('--gpu', type=int, choices=[0, 1], required=True)
    parser.add_argument('--region', choices=['P1', 'P2', 'P3'], required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--export-root', type=Path)
    parser.add_argument('--wrapper-exit', type=int)
    args = parser.parse_args()
    if not Path('/.dockerenv').is_file():
        raise RuntimeError('Run the guard in CPU-only Docker')
    payload = dict(schema='GEOGS_PREFIX_RESOURCE_BOUNDARY_v1', scientific_verdict=None,
        region=args.region, gpu=args.gpu, phase=args.phase, observed_unix=time.time(),
        reference_accessed=False, guard_gpu_work_launched=False, guard_source_sha256=sha(__file__),
        exact_desktop_allowance=DESKTOP, policy_changed=False, same_gpu_training_overlap_allowed=False,
        observation_scope='Before/after boundary snapshots and shared GPU lane lock; not a continuous process census')
    try:
        payload.update(observe(args.root, args.phase, args.gpu), status='PASS_RESOURCE_BOUNDARY')
    except Exception as error:
        payload.update(status='FAIL_RESOURCE_BOUNDARY', error_type=type(error).__name__, error=str(error))
    boundary = args.root / (args.phase + '_receipt.json')
    with boundary.open('x') as stream:
        json.dump(payload, stream, indent=2); stream.write('\n')
    if args.phase == 'after':
        before = args.root / 'before_receipt.json'
        previous = json.loads(before.read_text())
        result = dict(payload, schema='GEOGS_PREFIX_EXPORT_RESOURCE_EXECUTION_v1',
            wrapper_exit_code=args.wrapper_exit, before_receipt_sha256=sha(before),
            after_receipt_sha256=sha(boundary), before=previous, after=payload,
            source_export_receipt=None, export_success_inferred_from_resource_guard=False)
        if previous.get('status') != 'PASS_RESOURCE_BOUNDARY':
            result['status'] = 'FAIL_RESOURCE_BOUNDARY'
        producer = args.export_root / 'receipt.json'
        if producer.is_file():
            value = json.loads(producer.read_text())
            result['source_export_receipt'] = dict(path='receipt.json', bytes=producer.stat().st_size,
                sha256=sha(producer), status=value.get('status'), native_exit_code=value.get('native_exit_code'))
        with (args.export_root / 'resource_execution_receipt.json').open('x') as stream:
            json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps({key: payload[key] for key in ('status', 'region', 'gpu', 'phase')}))
    return 0 if payload['status'] == 'PASS_RESOURCE_BOUNDARY' else 3


if __name__ == '__main__':
    raise SystemExit(main())
