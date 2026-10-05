"""Reference-free diagnostics of preserved training attempts, never a quality score."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--end-iteration', type=int, default=14400)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/reference').exists():
        raise RuntimeError('Run in a reference-free Docker container')
    series = {}
    sources = {}
    for attempt, directory in [('original', 'runs'), ('allocator_v2', 'runs_allocator_v2')]:
        for condition in ('D005_Pnative', 'D0005_Pnative'):
            label = f'{attempt}.{condition}'
            path = args.task / directory / 'P1' / condition / 'model/jbgs_trace.jsonl'
            # Read once so a later append cannot alter the snapshot/hash pair.
            raw = path.read_bytes()
            parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
            rows = {row['iteration']: row for row in parsed}
            if len(rows) != len(parsed):
                raise ValueError('Duplicate training trace iteration')
            if max(rows) < args.end_iteration:
                raise ValueError(f'{label} has not reached the preregistered comparison endpoint')
            series[label] = rows
            sources[label] = {'path': str(path.relative_to(args.task)),
                              'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
                              'snapshot_bytes': len(raw), 'snapshot': raw}
    iterations = list(range(8100, args.end_iteration + 1, 100))
    for label, rows in series.items():
        if any(i not in rows for i in iterations):
            raise ValueError(f'Missing common-prefix trace row in {label}')
    reference = series['original.D005_Pnative']
    same_cameras = all(row[i]['camera'] == reference[i]['camera'] for row in series.values() for i in iterations)
    if not same_cameras:
        raise ValueError('Training camera schedule differs within the compared prefix')
    args.output.mkdir(parents=True, exist_ok=False)
    for label, source in sources.items():
        (args.output / (label + '.trace_snapshot.jsonl')).write_bytes(source.pop('snapshot'))
    keys = ('iteration', 'camera', 'gaussians', 'protected', 'rgb_loss', 'lod_loss', 'da_loss',
            'lod_weight', 'da_weight', 'peak_cuda_allocated_bytes', 'peak_cuda_reserved_bytes')
    with (args.output / 'common_prefix.csv').open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=['attempt_condition'] + list(keys))
        writer.writeheader()
        for label, rows in series.items():
            writer.writerows(dict(attempt_condition=label, **{k: rows[i][k] for k in keys}) for i in iterations)
    pairs = {}
    for condition in ('D005_Pnative', 'D0005_Pnative'):
        left, right = series['original.' + condition], series['allocator_v2.' + condition]
        delta = np.array([right[i]['gaussians'] - left[i]['gaussians'] for i in iterations])
        relative = np.abs(delta) / np.array([left[i]['gaussians'] for i in iterations])
        pairs[condition] = {'last_original_gaussians': left[iterations[-1]]['gaussians'],
                            'last_new_gaussians': right[iterations[-1]]['gaussians'],
                            'max_absolute_gaussian_count_difference': int(np.abs(delta).max()),
                            'max_relative_gaussian_count_difference': float(relative.max())}
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    for ax, key, title, divisor in zip(axes.flat,
            ('gaussians', 'rgb_loss', 'peak_cuda_allocated_bytes', 'peak_cuda_reserved_bytes'),
            ('Gaussian population (millions)', 'Sampled training RGB loss',
             'Training-process peak allocation (GiB)', 'Training-process peak reservation (GiB)'),
            (1e6, 1, 2**30, 2**30)):
        for label, rows in series.items():
            ax.plot(iterations, [rows[i][key]/divisor for i in iterations], label=label, linewidth=1.2)
        ax.set(title=title, xlabel='Total iteration')
        ax.grid(alpha=.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('P1 common-prefix execution diagnostics; no UAS or held-out quality scores')
    fig.savefig(args.output / 'common_prefix.png', dpi=160)
    plt.close(fig)
    report = {'scientific_verdict': None, 'status': 'REFERENCE_FREE_PREFIX_DIAGNOSTIC',
              'start_iteration': iterations[0], 'end_iteration': iterations[-1],
              'camera_schedule_exact': same_cameras, 'sources': sources,
              'same_condition_cross_attempt_counts': pairs, 'script_sha256': digest(Path(__file__)),
              'interpretation': 'Exact common anchor does not guarantee an identical later trajectory. These sampled training diagnostics are not geometric/render quality, a noise bound, or a causal estimate of allocator effects. Original native is uninterrupted; new native resumes its exact anchor. Peaks have different process-history windows.'}
    (args.output / 'receipt.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
