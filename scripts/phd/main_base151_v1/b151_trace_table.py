#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 3.1 / 3.2 records as tables (host, stdlib; reads only).

  python3 b151_trace_table.py   -> docs/experiments/phd/main_base151_v1/tables/trace1000_all.*, time_check_500.*
Sources: OUT/runs/<run>/cell<k>/attempt<a>/trace1000.jsonl (iteration 1 and every 1000) and time_check_500.json
(written by b151_entry.py at iteration 500 during training). scientific_verdict: null
"""
import json

from b151_host import OUT
from b151_records import GiB, trace, write


def main():
    rows, t500 = [], []
    for adir in sorted(OUT.glob('runs/*/cell*/attempt*')):
        run, cell, att = adir.parts[-3], int(adir.parts[-2][4:]), int(adir.parts[-1][7:])
        for t in trace(adir / 'trace1000.jsonl'):
            g = lambda k: round(t[k] / GiB, 3) if t.get(k) is not None else None
            rows.append(dict(run=run, cell=cell, attempt=att, iteration=t.get('iteration'), at=t.get('at'), seconds=t.get('seconds'),
                             gaussians=t.get('gaussians'), elong_lt_001=t.get('elong_lt_001'), elong_lt_01=t.get('elong_lt_01'),
                             host_rss_GiB=g('rss_bytes'), host_rss_peak_GiB=g('rss_peak_bytes'), cgroup_GiB=g('cgroup_current_bytes'),
                             cuda_reserved_GiB=g('cuda_reserved_bytes'), cuda_peak_reserved_GiB=g('cuda_peak_reserved_bytes'),
                             recorder_error=t.get('recorder_error')))
        p = adir / 'time_check_500.json'
        if p.exists():
            j = json.loads(p.read_text())
            t500.append(dict(run=run, cell=cell, attempt=att, at=j['at'], first_iteration=j['first_iteration'], iteration=j['iteration'],
                             seconds_first_to_500=round(j['seconds_first_to_500'], 2), seconds_per_iteration=round(j['seconds_per_iteration'], 4),
                             gaussians=j['gaussians'], peak_reserved_GiB=round(j['peak_reserved_bytes'] / GiB, 3)))
        else:
            t500.append(dict(run=run, cell=cell, attempt=att, at='없음'))
    write('trace1000_all', rows, '3.2: every trace row (iteration 1 and every 1000): gaussians, share of elongated gaussians (< 0.01, < 0.1), '
          'host RSS / cgroup memory and CUDA reserved memory; time = seconds since the training process began')
    write('time_check_500', t500, '3.1: time per iteration over the first 500 iterations, measured during training (time_check_500.json); '
          'the whole-run estimate was not written to progress.md at the time')
    print('TRACE', len(rows), 'T500', len(t500))


if __name__ == '__main__':
    main()
