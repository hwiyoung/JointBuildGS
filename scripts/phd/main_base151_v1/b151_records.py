#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 3.2 / 3.3 tables (host, stdlib): per run x cell x attempt training records and the stop-cause table.

  python3 b151_records.py      -> docs/experiments/phd/main_base151_v1/tables/run_records.*, stops.*
Sources: OUT/runs/<run>/cell<k>/receipt.json (queue receipt), attempt<a>/trace1000.jsonl (entry trace every 1000 iterations), the training
log (the official '[ITER n] Evaluating test / train: L1 .. PSNR ..' lines), OUT/control (queue state). Stops after training (mesh / score
steps of 4.1 / 4.2) are listed from POST_STOPS below (each with its log). scientific_verdict: null
"""
import csv
import json
import re

from b151_host import C, OUT, now

D = C.parents[2] / 'docs/experiments/phd/main_base151_v1/tables'
GiB = 2 ** 30
POST_STOPS = [
    dict(at='2026-11-19T11:29', step='4.2 mesh merge', run='b151_2DGS_s0', unit='c1_6907_53360', attempts=2,
         cause='RESCORE bounded_merge AssertionError: in the one tile, two Open3D vertices got one reconstructed global edge code (coordinates differ by 2.8e-14 m, colours equal; meshcheck/dup_*.json)',
         kind='code (edge-code rule at one vertex pair)', handling='GTJUDGE recovery_merge rule: same-tile collisions keep their own Open3D vertices (b151_units.merge_keep_open3d); tile files, TSDF values unchanged; rerun 13:40',
         log='logs/post42/c1_6907_53360__ALS__b151_2DGS_s0.log'),
    dict(at='2026-11-19T13:26', step='4.2 mesh plan', run='b151_LGDM_ALS', unit='c1_6909_53363', attempts=2,
         cause='streamed_tsdf.plan: e_lat 0.5008 m >= 0.5 m (the margin argument for proxy depths at tile seams); the only unit of 32 over 0.5 m (meshcheck/elat.json), the same for every method',
         kind='code (check that applies to tile seams only)', handling='one-tile layout only: check passed over, proxy pixels checked 0 before the merge (else stop); more tiles -> stop; rerun 13:40',
         log='logs/post42/c1_6909_53363__ALS__b151_LGDM_ALS.log'),
    dict(at='2026-11-19T17:45~18:06', step='4.2 render', run='b151_2DGS_s0', unit='c2_6909_53361, c2_6910_53359~53361, c3_6909_53361~53363, c3_6910_53361~53363, c3_6911_53361 (11)',
         attempts=2, cause="image jointbuildgs:2dgs-official-f3e3b9f-v1-b151 not on the host ('pull access denied'); the b151 images of 2DGS, CDGS and GeoGS-rtree and the build cache "
                           'were removed from the host (not by this task)', kind='environment',
         handling='rebuilt from the same Dockerfile, sources and build arguments (2DGS b97ade3c0050 18:11, CDGS cb11b4e1870e 18:20, 47 packages = pins); held by stopped containers '
                  'jbgs-b151-keep-2dgs / -cdgs; units rerun by the restarted watcher (18:12)', log='logs/post42/<unit>__ALS__b151_2DGS_s0.log, logs/build_*_r2.log'),
    dict(at='2026-11-19T18:12 / 18:46', step='4.2 score / tile (watcher handover)', run='b151_2DGS_s0', unit='c2_6909_53360 (18:12), c3_6909_53363 and c3_6910_53361 (18:46)',
         attempts=2, cause='docker name conflict: the step container started by the stopped watcher was still running when the new watcher started the same step '
                           '(the wait before the restart read an empty docker ps)', kind='operation (this task)',
         handling='the running step finished by itself; the unit counted done when its score files exist (c2_6909_53360) or finished by hand (19:00); sh() now waits while a '
                  'container of the same name exists (b151_post41.name_busy)', log='logs/post42/<unit>__ALS__b151_2DGS_s0.log'),
    dict(at='2026-11-19T20:28 (found 2026-11-20T22:10)', step='4.1 mesh merge', run='b151_GeoGS_LoD2_s0', unit='R1rep_b10 (LoD2)', attempts=2,
         cause='RESCORE bounded_merge AssertionError (copies of one edge code differ), the same stop as 2DGS c1_6907_53360; the 4.1 path (GTJUDGE mesh_job.py merge) '
               'has no same-tile repair, done41.json ok=false, not seen until b151_figs.py printed NO_RESULT on 11-20',
         kind='code (edge-code rule), operation (stop not reported)', handling='2026-11-20 22:1x: b151_units.py mesh <key> merge (bounded_merge, on its AssertionError the '
         'same merge_keep_open3d rule), then GTJUDGE mesh_job.py finish and score_new.py as in 4.1; tile files unchanged',
         log='logs/post41_mesh_R1rep_b10__LoD2__b151_GeoGS_LoD2_s0.log'),
    dict(at='2026-11-20T02:02~10:26', step='4.2 / 4.1 mesh tiles', run='b151_CDGS_ALS_s0, b151_CDGS_LoD2_s0',
         unit='CDGS ALS c0_6909_53359 tile 8, c0_6908_53359 tile 18; CDGS LoD2 B0_b10 tile 4', attempts=1,
         cause='no progress for 8 h: docker-workloads.slice memory.high 60 GiB exceeded (65.3 GB with other work) -> reclaim wait (D, mem_cgroup_handle_over_high); '
               'the watcher gate reads host MemAvailable only', kind='environment (shared memory slice)',
         handling='user decision: docker stop to tile 8, which had finished by itself before (rc 0); values unchanged, nothing rerun', log='issues.md 11/20 10:25'),
    dict(at='2026-11-20T10:37~10:45', step='4.2 mesh tile / merge, 4.1 mesh tile', run='b151_CDGS_ALS_s0, b151_CDGS_LoD2_s0',
         unit='CDGS ALS c0_6909_53359, c0_6908_53359, c1_6908_53361 (merge), c1_6908_53360 (tile 10); CDGS LoD2 B0_b10 (tile 8)', attempts=2,
         cause='OSError ENOSPC: the NVMe work folder disk (/) full', kind='environment (disk)',
         handling='POST_STOP; user decision: TRAINLOG NVMe folder 224 GB removed after an HDD copy (receipt), uv / pip caches removed; watchers restarted 10:52, '
                  'failed steps rerun from their saved tiles', log='logs/post42/<unit>__ALS__b151_CDGS_ALS_s0.log, logs/post41_mesh_B0_b10__LoD2__b151_CDGS_LoD2_s0.log'),
    dict(at='2026-11-19T23:44 ~ 2026-11-20T11:02', step='4.2 score', run='b151_CDGS_ALS_s0', unit='c0_6907_53359', attempts=4,
         cause='geometry_add1.sample_normals IndexError: no triangle of the unit mesh has its centre in a 0.5 m sample cell or area > 0.01 m2 (GT rows of the unit 80; '
               'GeoGS ALS 3,110, 2DGS 1,102, CDGS ALS 0 triangles in sample cells)', kind='code (zero samples not handled)',
         handling="user decision '표본 없음': b151_score151.py lines 132-137 / 148, zero kept triangles -> zero accuracy samples, completeness rows unchanged (80 rows: "
                  'within tau 0, no surface 78, surface outside tau 2); rescored 16:2x; no other unit of the eight runs has zero samples',
         log='logs/post42/c0_6907_53359__ALS__b151_CDGS_ALS_s0.score_empty_1120.log'),
]


def psnr(log):
    out = {}
    try:
        for line in open(log, errors='replace'):
            m = re.search(r'\[ITER (\d+)\] Evaluating (test|train): L1 ([0-9.eE+-]+) PSNR ([0-9.eE+-]+)', line)
            if m:
                out[(int(m.group(1)), m.group(2))] = float(m.group(4))
    except FileNotFoundError:
        pass
    return out


def trace(p):
    rows = []
    try:
        for line in open(p):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def write(name, rows, note):
    D.mkdir(parents=True, exist_ok=True)
    (D / f'{name}.json').write_text(json.dumps(dict(at=now().isoformat(), note=note, rows=rows, scientific_verdict=None), ensure_ascii=False, indent=1))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (D / f'{name}.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    fmt = lambda v: '' if v is None else (f'{v:.2f}' if isinstance(v, float) else str(v))
    with (D / f'{name}.md').open('w') as f:
        f.write(f'# {name}\n\n{note}\n\nscientific_verdict: null\n\n| ' + ' | '.join(fields) + ' |\n|' + '---|' * len(fields) + '\n')
        for r in rows:
            f.write('| ' + ' | '.join(fmt(r.get(k)).replace('|', '/') for k in fields) + ' |\n')


def main():
    c = json.loads((C / 'base151_v1.json').read_text())
    rows, stops = [], []
    for run in c['training_order']:
        parts = run.split('_')
        method, prior = parts[1], ('ALS + LoD2 (one model)' if parts[1] == '2DGS' else parts[2])
        for k in range(4):
            rp = OUT / 'runs' / run / f'cell{k}' / 'receipt.json'
            if not rp.exists():
                rows.append(dict(run=run, method=method, prior=prior, cell=k, attempt=None, status='NO_RECEIPT (running or waiting)'))
                continue
            rec = json.loads(rp.read_text())
            for a in rec['attempts']:
                tr = trace(OUT / 'runs' / run / f'cell{k}' / f'attempt{a["attempt"]}' / 'trace1000.jsonl')
                ps = psnr(a.get('log') or '')
                last = tr[-1] if tr else (a.get('last_trace') or {})
                mx = lambda key: max((t.get(key) or 0) for t in tr) if tr else (last.get(key))
                row = dict(run=run, method=method, prior=prior, cell=k, attempt=a['attempt'], status=a['status'], exit_code=a.get('exit_code'),
                           hours=round(a['seconds'] / 3600, 2) if a.get('seconds') else None, last_iteration=last.get('iteration'),
                           gaussians_final=last.get('gaussians'), gaussians_max=mx('gaussians'),
                           elong_lt_001_final=last.get('elong_lt_001'), cap_GiB=a.get('cap_GiB'), gpu_free_MiB_at_launch=a.get('gpu_free_MiB_at_launch'),
                           cuda_peak_reserved_GiB=round(mx('cuda_peak_reserved_bytes') / GiB, 2) if mx('cuda_peak_reserved_bytes') else None,
                           host_rss_peak_GiB=round(mx('rss_peak_bytes') / GiB, 2) if mx('rss_peak_bytes') else None,
                           cgroup_peak_GiB=round(mx('cgroup_peak_bytes') / GiB, 2) if mx('cgroup_peak_bytes') else None,
                           min_gpu1_free_MiB=a.get('min_gpu_free_MiB'), min_host_available_GiB=round(a['min_host_available_GiB'], 1) if a.get('min_host_available_GiB') else None,
                           psnr_test_30000=ps.get((30000, 'test')), psnr_train_30000=ps.get((30000, 'train')),
                           pause=a.get('pause'), resume_from=a.get('resume_from'), host_guard=a.get('host_guard'), gpu_pause=a.get('gpu_pause'), gpu_kill=a.get('gpu_kill'))
                rows.append(row)
                if a['status'] != 'TRAINING_COMPLETE':
                    stops.append(dict(at=a.get('at'), step='training', run=run, unit=f'cell{k}', attempts=a['attempt'], cause=a.get('error') or a['status'],
                                      kind='(3.3 check)', handling='', log=a.get('log')))
    write('run_records', rows, '3.2: per run x cell x attempt (queue receipt, entry trace every 1000 iterations, PSNR of the official log at 30000; '
          '2DGS = one model scored with both priors)')
    write('stops', stops + POST_STOPS, '3.3: every stop (training attempts not TRAINING_COMPLETE; mesh / score steps), cause first, then the handling')
    print('RECORDS', len(rows), 'STOPS', len(stops) + len(POST_STOPS))


if __name__ == '__main__':
    main()
