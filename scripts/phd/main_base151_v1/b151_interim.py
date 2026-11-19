#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 interim-bundle tables (host, stdlib; request 2026-11-19 '중간 묶음'), from the receipts already written:

  python3 b151_interim.py      -> docs/experiments/phd/main_base151_v1/tables/inputs_sizes.*, method_filter.*, running_status.*
inputs_sizes   (order 2.2) method x prior x cell: views, initial points, prior surface vertices / faces, prior depth maps, protection cloud,
               DA3 maps, LGDM composite depth maps (scene / unit receipts under OUT)
method_filter  (order 1.7) per method: Gaussian form (2 or 3 axes), the elongation filter definition and the file and lines it is in
running_status (request 바) runs not finished: cell, attempt, last trace iteration, Gaussians, start, end estimate (rule written in the row)
scientific_verdict: null
"""
import csv
import datetime as dt
import json

from b151_host import C, OUT, now

D = C.parents[2] / 'docs/experiments/phd/main_base151_v1/tables'
ENTRY = 'scripts/phd/main_base151_v1/b151_entry.py'


def rd(p):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write(name, rows, note):
    D.mkdir(parents=True, exist_ok=True)
    (D / f'{name}.json').write_text(json.dumps(dict(at=now().isoformat(), note=note, rows=rows, scientific_verdict=None), ensure_ascii=False, indent=1))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (D / f'{name}.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    fmt = lambda v: '없음' if v is None else (f'{v:,.2f}' if isinstance(v, float) else (f'{v:,}' if isinstance(v, int) else str(v)))
    with (D / f'{name}.md').open('w') as f:
        f.write(f'# {name}\n\n{note}\n\nscientific_verdict: null\n\n| ' + ' | '.join(fields) + ' |\n|' + '---|' * len(fields) + '\n')
        for r in rows:
            f.write('| ' + ' | '.join(fmt(r.get(k)).replace('|', '/') for k in fields) + ' |\n')


def inputs_sizes():
    rows = []
    for k in range(4):
        sc = rd(OUT / 'scenes/2DGS' / f'cell{k}' / 'scene_receipt.json') or {}
        rows.append(dict(method='2DGS', prior='없음', cell=k, train_views=sc.get('train_views'), test_views=sc.get('test_views'),
                         initial_points=sc.get('initial_points'), note='TU1 cell scene SfM points, origin 0'))
    for p in ['ALS', 'LoD2']:
        for k in range(4):
            pr = (rd(OUT / 'prior' / f'cell{k}' / 'receipt.json') or {}).get(p, {})
            sc = rd(OUT / f'scenes/GeoGS_{p}' / f'cell{k}' / 'scene_receipt.json') or {}
            pc = rd(OUT / 'prep/geogs' / f'{p}_cell{k}' / 'pcd.json') or {}
            da3 = rd(OUT / 'da3/geogs' / f'cell{k}' / 'da3_diag_consec12.json') or {}
            rows.append(dict(method='GeoGS', prior=p, cell=k, train_views=sc.get('train'), test_views=sc.get('test'),
                             prior_cell_mesh_vertices=pr.get('vertices'), prior_cell_mesh_faces=pr.get('faces'),
                             surface_vertices=sc.get('surface_vertices'), surface_faces=sc.get('surface_faces'),
                             prior_depth_maps=sc.get('depth_maps'), protection_cloud_points=sc.get('protection_cloud_points'),
                             initial_points=(pc.get('result') or {}).get('kept'), da3_views=da3.get('train_views'), da3_batches=da3.get('batches'),
                             note='prior depth maps = all cell images (train + test), as the previous GeoGS scenes'))
    for p in ['ALS', 'LoD2']:
        for k in range(4):
            un = rd(OUT / 'scenes/CDGS' / f'cell{k}' / 'units.json') or {}
            sc = rd(OUT / f'scenes/CDGS_{p}' / f'cell{k}' / 'scene_receipt.json') or {}
            rows.append(dict(method='CDGS', prior=p, cell=k, train_views=un.get('train'), test_views=un.get('test'),
                             initial_points=(un.get('points') or {}).get('kept'), prior_depth_maps=sc.get('prior_depth_files'), cdgs_s=sc.get('s'),
                             note='WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell'))
    for p in ['ALS', 'LoD2']:
        rc = rd(OUT / 'lgdm' / f'receipt_{p}.json') or {}
        files = (rc.get('files') or {}).get('depth', {})
        for k in range(4):
            rows.append(dict(method='LGDM', prior=p, cell=k, composite_depth_maps=files.get(f'cell{k}'), change_area_m2=rc.get('change_area_m2'),
                             prior_surface_vertices=(rc.get('prior_surface') or {}).get('vertices'), prior_surface_faces=(rc.get('prior_surface') or {}).get('faces'),
                             note='judge / decide over the campus (819 training views), composite per cell; change area = campus total'))
    write('inputs_sizes', rows, '2.2: input sizes per method x prior x cell, read from the receipts under OUT (scenes/, prior/, prep/geogs/, da3/geogs/, lgdm/); '
          'missing field = 없음')


def method_filter():
    rows = []
    for m, runs in [('2DGS', ['b151_2DGS_s0']), ('GeoGS', ['b151_GeoGS_ALS_s0', 'b151_GeoGS_LoD2_s0']), ('CDGS', ['b151_CDGS_ALS_s0', 'b151_CDGS_LoD2_s0'])]:
        f = None
        for r in runs:
            f = f or rd(OUT / 'runs' / r / 'cell0/attempt1/filter.json')
        if f is None:
            f = rd(OUT / 'tests/smoke_b151_CDGS_ALS_s0/a1/filter.json') if m == 'CDGS' else None
        dim = (f or {}).get('dim')
        rows.append(dict(method=m, gaussian_axes=('2 (납작한 것)' if dim == '2D' else '3 (3차원)' if dim == '3D' else None),
                         definition=(f or {}).get('definition'), comparison=(f or {}).get('comparison'), threshold=(f or {}).get('threshold'),
                         where=f'{ENTRY}: ratio() lines 83-87, densify_and_prune wrapper lines 90-112 (needle = ratio <= 0.01 at line 97, '
                               'xyz_gradient_accum[needle] = 0 at line 101, then the unchanged densify_and_prune at line 105)',
                         method_code_changed='없음 (the method code is not edited; the wrapper is installed by the entry before train.py runs)',
                         record=f'OUT/runs/<run>/cell<k>/attempt<a>/filter.json, densify.jsonl' if f else '없음'))
    rows.append(dict(method='LGDM', gaussian_axes='없음 (가우시안 없음, 학습 없음)', definition='없음', comparison=None, threshold=None, where='없음',
                     method_code_changed='없음', record='없음'))
    write('method_filter', rows, '1.7: Gaussian form and elongation filter per method (order text: ratio < 0.01; the TRAINUNIT code used here is <= 0.01)')


def running_status():
    c = json.loads((C / 'base151_v1.json').read_text())
    rows = []
    done_h = []
    for run in c['training_order']:
        for k in range(4):
            rec = rd(OUT / 'runs' / run / f'cell{k}' / 'receipt.json')
            if rec and rec['status'] == 'TRAINING_COMPLETE':
                done_h.append((run, rec['attempts'][-1]['seconds'] / 3600))
    for run in c['training_order']:
        for k in range(4):
            rec = rd(OUT / 'runs' / run / f'cell{k}' / 'receipt.json')
            if rec and rec['status'] == 'TRAINING_COMPLETE':
                continue
            atts = sorted((OUT / 'runs' / run / f'cell{k}').glob('attempt*'))
            row = dict(run=run, cell=k)
            if atts:
                a = atts[-1]
                lines = [json.loads(x) for x in (a / 'trace1000.jsonl').read_text().splitlines() if x.strip()] if (a / 'trace1000.jsonl').exists() else []
                launch = rd(a / 'launch.json') or {}
                last = lines[-1] if lines else {}
                row.update(state='학습 중', attempt=a.name, started=launch.get('at'), iteration=last.get('iteration'), gaussians=last.get('gaussians'),
                           elong_lt_001=last.get('elong_lt_001'), trace_at=last.get('at'))
                same = [h for (r2, h) in done_h if r2.split('_')[1] == run.split('_')[1]]
                if launch.get('at') and same:
                    t0 = dt.datetime.fromisoformat(launch['at'])
                    row['end_estimate'] = (f"{(t0 + dt.timedelta(hours=min(same))).strftime('%m-%d %H:%M')} ~ {(t0 + dt.timedelta(hours=max(same))).strftime('%m-%d %H:%M')}"
                                           f" (start + the {len(same)} finished cells of this method, {min(same):.2f}-{max(same):.2f} h)")
                elif launch.get('at') and last.get('iteration') and last.get('at'):
                    t0, t1 = dt.datetime.fromisoformat(launch['at']), dt.datetime.fromisoformat(last['at'])
                    end = t0 + (t1 - t0) * (30000 / last['iteration'])
                    row['end_estimate'] = (f"{end.strftime('%m-%d %H:%M')} (no finished cell of this method: start + elapsed to iteration "
                                           f"{last['iteration']} x 30000 / {last['iteration']}; loading and saving not counted)")
            else:
                row.update(state='대기', end_estimate='not started; no finished cell of this method yet' if run.split('_')[1] == 'CDGS' else 'not started')
            rows.append(row)
    for run in c['training_order'] + ['b151_LGDM_ALS', 'b151_LGDM_LoD2']:
        priors = ['ALS', 'LoD2'] if run.split('_')[1] == '2DGS' else [run.split('_')[2]]
        d41 = rd(OUT / 'post' / run / 'done41.json')
        for p in priors:
            sc = OUT / 'gt' / 'score151' / f'{run}__{p}'
            n = len(list(sc.glob('c[0-3]_*.npz'))) if sc.exists() else 0
            rows.append(dict(run=run, prior=p, state='채점', step_41=('끝 (' + d41['at'][:16] + ')') if d41 else '안 끝남',
                             step_42=('끝, 모음 ' + dt.datetime.fromtimestamp((sc / 'summary.json').stat().st_mtime).strftime('%m-%d %H:%M')) if (sc / 'summary.json').exists()
                             else f'{n}/32 단위 채점됨'))
    write('running_status', rows, '바: runs not finished at the time of writing (trace every 1000 iterations; end estimate = start + the range of the finished cells of the same method, or, with none, the trace rate), then the 4.1 / 4.2 state of every run x prior (state = 채점)')


if __name__ == '__main__':
    inputs_sizes()
    method_filter()
    running_status()
    print('INTERIM_TABLES')
