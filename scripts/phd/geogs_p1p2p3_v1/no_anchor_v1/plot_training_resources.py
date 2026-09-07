"""Freeze small training traces and plot a partial resource diagnostic in Docker.

Original attempts and retries are independent series. Baseline trace identities
come from the sealed resource_summary.csv used by summarize_resources.py.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import sys


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Snapshot:
    def __init__(self, out):
        self.out = out
        self.records = []
        self.cache = {}

    def read(self, path, expected=None, trace=False):
        path = Path(path)
        if str(path) in self.cache:
            raw, record = self.cache[str(path)]
            if expected and record['source_read_sha256'] != expected:
                raise ValueError(f'Sealed source identity differs: {path}')
            return raw, record
        started = utc()
        raw = path.read_bytes()
        ended = utc()
        original = raw
        if expected and digest(raw) != expected:
            raise ValueError(f'Sealed source identity differs: {path}')
        # Writers can be appending: freeze only newline-terminated records.
        if trace and raw and not raw.endswith(b'\n'):
            raw = raw[:raw.rfind(b'\n') + 1]
        name = f'{len(self.records):03d}_{path.name}'
        target = self.out / 'snapshots' / name
        target.write_bytes(raw)
        record = dict(source_path=str(path), snapshot_path=str(target.relative_to(self.out)),
                      read_started_utc=started, read_finished_utc=ended,
                      source_read_bytes=len(original), source_read_sha256=digest(original),
                      snapshot_bytes=len(raw), snapshot_sha256=digest(raw),
                      incomplete_trailing_bytes_excluded=len(original) - len(raw),
                      sealed_expected_sha256=expected)
        self.records.append(record)
        self.cache[str(path)] = (raw, record)
        return raw, record

    def json(self, path, expected=None):
        raw, _ = self.read(path, expected)
        return json.loads(raw)

    def trace(self, path, expected=None):
        raw, record = self.read(path, expected, trace=True)
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        previous = 0
        elapsed = -1.0
        for row in rows:
            step = row['iteration']
            if not isinstance(step, int) or isinstance(step, bool) or step <= previous:
                raise ValueError(f'Trace steps are not unique and increasing: {path}')
            for key in ['gaussians', 'protected', 'peak_cuda_allocated_bytes', 'peak_cuda_reserved_bytes']:
                if not isinstance(row[key], int) or isinstance(row[key], bool) or row[key] < 0:
                    raise ValueError(f'Invalid count: {path}: {key}')
            now = float(row['elapsed_seconds'])
            if not math.isfinite(now) or now < elapsed:
                raise ValueError(f'Invalid elapsed sequence: {path}')
            previous, elapsed = step, now
        record['last_recorded_iteration'] = rows[-1]['iteration'] if rows else None
        record['complete_jsonl_records'] = len(rows)
        return rows, record


def safe_task_path(task, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError(f'Expected contained task-relative path: {relative}')
    return task / rel


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row)) or ['status']
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def collect(snap, task, experiment, overrides):
    cfg = snap.json(experiment / 'config.json')
    cfg_sha = snap.cache[str(experiment / 'config.json')][1]['snapshot_sha256']
    raw, _ = snap.read(task / 'evaluation/summary/resource_summary.csv')
    baseline = list(csv.DictReader(io.StringIO(raw.decode())))
    series, availability = [], []
    for region in cfg['regions']:
        rows = [r for r in baseline if r['region'] == region and r['condition'] == 'D005_Pnative']
        selected = [r for r in rows if r['phase'] == 'training_trace']
        anchor = [r for r in rows if r['phase'] == 'shared_anchor_prefix']
        if len(selected) != 1 or len(anchor) != 1:
            raise ValueError('Expected one sealed baseline final trace and anchor lineage')
        r = selected[0]
        traced, src = snap.trace(safe_task_path(task, r['source_path']), r['source_sha256'])
        if not traced or traced[-1]['iteration'] != 30000:
            raise ValueError('Baseline completion trace missing')
        start = int(r['training_start_iteration'])
        if start == 8000:
            a = anchor[0]
            ar, asrc = snap.trace(safe_task_path(task, a['source_path']), a['source_sha256'])
            prefix = [row for row in ar if row['iteration'] <= 8000]
            if not prefix or prefix[-1]['iteration'] != 8000 or traced[0]['iteration'] <= 8000:
                raise ValueError('Invalid anchor/resume boundary')
            series.append(dict(region=region, attempt='vanilla', segment='reused_anchor_prefix',
                               status='REUSED_ANCHOR_PREFIX', start_iteration=0,
                               rows=prefix, source=asrc, receipt=None))
            segment = 'resume_after_anchor_separate_process'
        elif start == 0:
            if traced[0]['iteration'] > 100 or 8000 not in {v['iteration'] for v in traced}:
                raise ValueError('Continuous baseline lacks anchor prefix')
            segment = 'continuous_anchor_and_refinement'
        else:
            raise ValueError('Unsupported baseline start')
        series.append(dict(region=region, attempt='vanilla', segment=segment,
                           status='COMPLETED_30000', start_iteration=start,
                           rows=traced, source=src, receipt=None))
        for attempt, folder in [('sfm_original', experiment), ('sfm_recovery', overrides[region])]:
            snap.json(folder / 'config.json', cfg_sha)
            run = folder / 'runs' / region / cfg['condition_id']
            receipt = snap.json(run / 'receipt.json') if (run / 'receipt.json').is_file() else None
            if receipt and (receipt.get('region'), receipt.get('phase'), receipt.get('condition_id')) != (region, 'train', cfg['condition_id']):
                raise ValueError('Training receipt identity differs')
            status = ('COMPLETED_30000' if receipt['status'] == 'PASS' else 'FAILED') if receipt else 'INCOMPLETE_PREFIX_NO_CLOSED_RECEIPT'
            path = run / 'model/jbgs_trace.jsonl'
            if not path.is_file():
                availability.append(dict(region=region, attempt=attempt, status='NO_TRACE_NOT_STARTED_OR_NOT_YET_RECORDED',
                                         experiment=str(folder), snapshot_utc=utc(), quality_evidence=False))
                continue
            traced, src = snap.trace(path)
            if not traced:
                availability.append(dict(region=region, attempt=attempt, status='NO_COMPLETE_TRACE_RECORDS',
                                         experiment=str(folder), snapshot_utc=utc(), quality_evidence=False))
                continue
            if traced[0]['iteration'] != 1 or (receipt and receipt.get('config_sha256') != cfg_sha):
                raise ValueError('Fresh-SfM iteration/config differs')
            if status == 'COMPLETED_30000' and traced[-1]['iteration'] != 30000:
                raise ValueError('PASS receipt without completed trace')
            series.append(dict(region=region, attempt=attempt, segment='independent_fresh_attempt',
                               status=status, start_iteration=0, rows=traced, source=src,
                               receipt=receipt))
    return cfg, series, availability


def make_tables(series, availability):
    points, summary = [], list(availability)
    for s in series:
        rows, src = s['rows'], s['source']
        shared = dict(region=s['region'], attempt=s['attempt'], segment=s['segment'], status=s['status'],
                      training_start_iteration=s['start_iteration'], trace_snapshot_path=src['snapshot_path'],
                      trace_snapshot_sha256=src['snapshot_sha256'], snapshot_utc=src['read_finished_utc'],
                      scientific_verdict=None)
        summary.append(dict(**shared, first_recorded_iteration=rows[0]['iteration'],
                            last_recorded_iteration=rows[-1]['iteration'], records_used=len(rows),
                            last_gaussians=rows[-1]['gaussians'], last_protected=rows[-1]['protected'],
                            peak_cuda_allocated_through_last_trace_bytes=max(v['peak_cuda_allocated_bytes'] for v in rows),
                            peak_cuda_reserved_through_last_trace_bytes=max(v['peak_cuda_reserved_bytes'] for v in rows),
                            process_elapsed_at_last_trace_seconds=rows[-1]['elapsed_seconds'],
                            driver_wall_seconds=s['receipt'].get('wall_seconds') if s['receipt'] else None,
                            failure_iteration_exactly_measured=False, quality_evidence=False))
        for row in rows:
            points.append(dict(**shared, iteration=row['iteration'], gaussians=row['gaussians'],
                               protected=row['protected'], process_elapsed_seconds=row['elapsed_seconds'],
                               peak_cuda_allocated_bytes=row['peak_cuda_allocated_bytes'],
                               peak_cuda_reserved_bytes=row['peak_cuda_reserved_bytes']))
    return points, summary


def plot(series, out, snapshot_time):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    colors = dict(vanilla='#1965a4', sfm_original='#c63d2f', sfm_recovery='#168565')
    styles = dict(vanilla='-', sfm_original='--', sfm_recovery='-')
    labels = dict(vanilla='Vanilla D005: sealed completed lineage',
                  sfm_original='SfM / no anchor: original failed attempt',
                  sfm_recovery='SfM / no anchor: independent memory retry prefix')
    fig, axes = plt.subplots(2, 3, figsize=(17, 8.4), sharex=True, sharey='row')
    # A shared axis must use all regions before setting limits; setting the first
    # panel's lower bound otherwise disables autoscaling for later, larger data.
    limits = {key: max(v[key] / scale for s in series for v in s['rows']) * 1.12
              for key, scale in [('gaussians', 1e6), ('peak_cuda_allocated_bytes', 2**30)]}
    for col, region in enumerate(['P1', 'P2', 'P3']):
        own = [s for s in series if s['region'] == region]
        axes[0, col].set_title(region, fontweight='bold', fontsize=15)
        for row_index, (metric, scale) in enumerate([('gaussians', 1e6), ('peak_cuda_allocated_bytes', 2**30)]):
            ax = axes[row_index, col]
            ax.axvline(8000, color='#888888', ls=':', lw=1)
            for s in own:
                x = [v['iteration'] for v in s['rows']]
                y = [v[metric] / scale for v in s['rows']]
                ax.plot(x, y, color=colors[s['attempt']], ls=styles[s['attempt']], lw=1.8)
                if s['status'] == 'REUSED_ANCHOR_PREFIX':
                    continue
                marker = 'x' if s['status'] == 'FAILED' else ('s' if s['status'] == 'COMPLETED_30000' else 'o')
                ax.plot(x[-1], y[-1], marker=marker, color=colors[s['attempt']], ms=7, mew=1.5,
                        markerfacecolor='white' if marker == 'o' else colors[s['attempt']])
                if row_index == 0 and s['attempt'] != 'vanilla':
                    offset = (5, 9) if s['attempt'] == 'sfm_recovery' else (5, -15)
                    ax.annotate(f'{x[-1]:,}', (x[-1], y[-1]), xytext=offset,
                                textcoords='offset points', color=colors[s['attempt']], fontsize=9)
            if not any(s['attempt'] == 'sfm_recovery' for s in own):
                ax.text(.97, .95, 'Retry: no trace at snapshot', ha='right', va='top',
                        transform=ax.transAxes, fontsize=9, color=colors['sfm_recovery'])
            ax.grid(alpha=.2)
            ax.set_xlim(0, 31000)
            ax.set_ylim(0, limits[metric])
            ax.set_xticks([0, 8000, 15000, 22000, 30000], ['0', '8k', '15k', '22k', '30k'])
            if row_index == 1:
                ax.set_xlabel('Recorded optimizer iteration (anchor included for vanilla)')
        axes[0, 0].set_ylabel('Gaussian count (million)')
        axes[1, 0].set_ylabel('Process cumulative CUDA allocated peak (GiB)')
    handles = [Line2D([0], [0], color=colors[k], ls=styles[k], lw=2, label=labels[k]) for k in colors]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .928), ncol=3, frameon=False, fontsize=10)
    fig.suptitle('GeoGS resource progress — frozen partial diagnostic, no quality verdict', fontsize=17, y=.99)
    fig.text(.5, .943, f'Snapshots completed: {snapshot_time}', ha='center', fontsize=10)
    fig.text(.055, .065, 'x = last logged point of a failed attempt (not exact OOM step); open circle = unfinished prefix; square = completed trace.', fontsize=10)
    fig.text(.055, .040, 'P1 vanilla: reused anchor <= 8k and a separate resumed process > 8k. Lines and memory counters are not joined across that boundary.', fontsize=10)
    fig.text(.055, .015, '8k dotted line applies to vanilla anchor only. Retries restart at iteration 1. Peaks exclude unlogged failure/save events and are not summed.', fontsize=10)
    fig.subplots_adjust(top=.865, bottom=.145, left=.065, right=.99, hspace=.18, wspace=.13)
    fig.savefig(out / 'training_resource_progress.png', dpi=180)
    fig.savefig(out / 'training_resource_progress.pdf')
    plt.close(fig)
    return matplotlib.__version__


def run(args):
    if not Path('/.dockerenv').is_file():
        raise RuntimeError('Docker-only resource plotting')
    if os.environ.get('NVIDIA_VISIBLE_DEVICES') not in ('none', 'void', ''):
        raise RuntimeError('Set NVIDIA_VISIBLE_DEVICES=void for this CPU-only diagnostic')
    task, experiment, out = args.task.resolve(), args.experiment.resolve(), args.out.absolute()
    overrides = {}
    for value in args.region_experiment:
        region, sep, path = value.partition('=')
        if not sep or region in overrides or region not in ('P1', 'P2', 'P3'):
            raise ValueError('Use one REGION=PATH override per region')
        overrides[region] = Path(path).resolve()
    if set(overrides) != {'P1', 'P2', 'P3'}:
        raise ValueError('Explicit recovery roots required for all three regions')
    if out.exists() or out.is_symlink():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    (out / 'snapshots').mkdir()
    started = utc()
    snap = Snapshot(out)
    cfg, series, availability = collect(snap, task, experiment, overrides)
    snap_finished = utc()
    # Plot only the in-memory rows whose exact bytes have already been copied.
    points, summary = make_tables(series, availability)
    write_csv(out / 'trace_points.csv', points)
    write_csv(out / 'attempt_segments.csv', summary)
    mpl_version = plot(series, out, snap_finished)
    script = Path(__file__).read_bytes()
    (out / 'plot_training_resources_snapshot.py').write_bytes(script)
    receipt = dict(schema='jointbuildgs.geogs.training_resource_progress.v1',
                   status='PASS_PARTIAL_RESOURCE_DIAGNOSTIC', scientific_verdict=None,
                   final_resource_summary=False, quality_evidence=False,
                   started_utc=started, snapshots_finished_utc=snap_finished, finished_utc=utc(),
                   task_id=cfg['task_id'], runtime_image_id=args.runtime_image_id,
                   python_version=sys.version, matplotlib_version=mpl_version,
                   platform=platform.platform(), command=sys.argv, script_sha256=digest(script),
                   gpu_used=False, source_payloads_modified=False, extrapolated=False,
                   regions=['P1', 'P2', 'P3'], attempt_segments=summary, sources=snap.records,
                   scope_notes=[
                       'Each trace was copied before plotting; capture times differ slightly across sources.',
                       'Original failed and retry traces remain separate fresh attempts; never concatenated.',
                       'P1 vanilla uses the sealed shared anchor prefix through8000 from the original failed process, then only the completed resumed process after8000.',
                       'P1 memory counters belong to separate processes and are displayed as separate segments without a connecting line or sum.',
                       'Only P2/P3 vanilla are continuous anchor+refinement processes.',
                       'Iteration is the recorded optimizer iteration; no step0 count or intervening100-step values are invented.',
                       'CUDA allocated is the process PyTorch cumulative peak through each record, not current memory, reserved memory, or whole-GPU usage.',
                       'Last trace peak need not include the failed allocation or a later serialization peak.',
                       'Elapsed time is from instrumentation import including loading/restore/report/save overhead; driver wall already contains it.',
                       'Gaussian counts are representation/resource statistics and do not measure final surface quality.',
                       'Memory transfer, GPU placement/concurrency, initialization and densification population jointly affect cost; no isolated speed attribution.'
                   ])
    receipt['outputs'] = [dict(path=str(p.relative_to(out)), bytes=p.stat().st_size,
                               sha256=digest(p.read_bytes())) for p in sorted(out.iterdir()) if p.is_file()]
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps(dict(status=receipt['status'], snapshots_finished_utc=snap_finished,
                         series=len(series), rows=len(points), scientific_verdict=None)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--region-experiment', action='append', default=[], metavar='REGION=PATH')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runtime-image-id', required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
