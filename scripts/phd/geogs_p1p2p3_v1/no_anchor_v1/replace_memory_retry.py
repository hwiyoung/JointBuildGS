"""Seal a storage-only replacement, then stop only its exact native train child."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, data):
    with Path(p).open('x') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['prepare', 'stop'], required=True)
    p.add_argument('--region', choices=['P1', 'P2'], required=True)
    a = p.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    suffix = '' if a.region == 'P1' else '_P2'
    old = f'no_anchor_sfm_memory_recovery{suffix}_v1'
    new = f'no_anchor_sfm_memory_recovery{suffix}_v2'
    if a.mode == 'prepare':
        root = Path('/task')
        selected = root / new
        fixture_path = root / 'no_anchor_sfm_memory_recovery_v2/validation/runtime_cuda_v1/receipt.json'
        probe_path = root / 'no_anchor_sfm_memory_recovery_v1/validation/adapter_probe_v1/adapter_probe.json'
        fixture = json.loads(fixture_path.read_text())
        probe = json.loads(probe_path.read_text())
        runtime = json.loads((selected / 'source/jbgs_memory_recovery_receipt.json').read_text())
        if fixture['status'] != 'PASS_CUDA_RUNTIME_FIXTURE' or fixture['prepared_source_python_sha256'] != runtime['destination_python_sha256']:
            raise ValueError('Prepared v2 source has no matching CUDA fixture')
        if probe['status'] != 'PASS_BOUNDED_ADAPTER_MEASUREMENT' or not probe['state_bytes_equal']:
            raise ValueError('Storage measurement/state verification failed')
        # Ratio is derived directly from every paired post-warmup cycle.
        import statistics
        paired = {}
        for row in probe['cycles']:
            if not row['warmup']:
                paired.setdefault(row['repeat'], {})[row['mode']] = row['total_seconds']
        ratio = statistics.median(v['v1_pageable'] / v['v2_pinned_reuse'] for v in paired.values())
        if ratio < 2.0:
            raise ValueError('Predeclared storage-only adoption threshold not met')
        if sha(selected / 'config.json') != sha(root / old / 'config.json'):
            raise ValueError('Science configuration differs')
        if Path('/output/receipt.json').exists():
            raise ValueError('Old attempt already closed; do not signal it')
        plan = dict(schema='GEOGS_PINNED_RETRY_ADOPTION_v1', scientific_verdict=None,
            region=a.region, cause='RESOURCE_TRANSFER_OPTIMIZATION', old_attempt=old,
            replacement_attempt=new, created_unix=time.time(),
            fixture=dict(path=str(fixture_path.relative_to(root)), sha256=sha(fixture_path)),
            storage_probe=dict(path=str(probe_path.relative_to(root)), sha256=sha(probe_path)),
            measured_paired_storage_ratio=ratio, whole_training_speed_claim=False,
            old_train_sha256=sha(root / old / 'source/train.py'),
            old_adapter_sha256=sha(root / old / 'source/jbgs_memory_recovery.py'),
            new_runtime_receipt_sha256=sha(selected / 'source/jbgs_memory_recovery_receipt.json'),
            scientific_configuration_sha256=sha(selected / 'config.json'),
            scientific_controls_changed=False, resume=False, fresh_sfm_restart=True,
            additional_capture_iterations=[8000, 15000],
            change='Pinned reusable moment buffers; same model, losses, Adam math, 30000 steps, images and original 32GiB limit.',
            preserved='All old logs, states, native driver receipt and consumed runtime remain in their original paths.',
            limitations=['Loses the unfinished prefix; its cost is recorded separately.',
                        'No whole-trajectory bitwise equality or full-run speed/completion guarantee.',
                        'Host guard estimates checkpoint payload; serialization peaks may exceed the estimate.'],
            controller_sha256=sha(__file__))
        write('/output/replacement_adoption_plan.json', plan)
        write('/replacement/adoption_plan.json', plan)
        print(json.dumps({'status': 'SEALED_BEFORE_INTENTIONAL_STOP', 'region': a.region}))
    else:
        plan_path = Path('/output/replacement_adoption_plan.json')
        plan = json.loads(plan_path.read_text())
        if plan['region'] != a.region or plan['replacement_attempt'] != new or plan['controller_sha256'] != sha(__file__):
            raise ValueError('Adoption plan/controller identity mismatch')
        if sha('/source/train.py') != plan['old_train_sha256'] or sha('/source/jbgs_memory_recovery.py') != plan['old_adapter_sha256']:
            raise ValueError('Active source mismatch')
        if Path('/output/receipt.json').exists():
            raise ValueError('Native driver has already closed')
        expected = json.loads(Path('/output/invocation.json').read_text())['command']
        matches = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdecimal():
                continue
            try:
                cmd = (proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            except (FileNotFoundError, PermissionError):
                continue
            if cmd == expected:
                matches.append(int(proc.name))
        if len(matches) != 1:
            raise ValueError(f'Expected one exact native command, got {matches}')
        intent = dict(schema='GEOGS_RESOURCE_STOP_INTENT_v1', scientific_verdict=None,
            region=a.region, cause='RESOURCE_TRANSFER_OPTIMIZATION', created_unix=time.time(),
            native_pid_in_container=matches[0], native_command=expected,
            replacement_attempt=new, adoption_plan_sha256=sha(plan_path),
            signal='SIGTERM', other_processes_or_services_targeted=False,
            controller_sha256=sha(__file__))
        write('/output/stop_intent.json', intent)
        os.kill(matches[0], signal.SIGTERM)
        write('/output/stop_signal_receipt.json', dict(status='SIGTERM_SENT', **intent))
        print(json.dumps({'status': 'SIGTERM_SENT_TO_EXACT_NATIVE_CHILD', 'region': a.region}))


if __name__ == '__main__':
    main()
