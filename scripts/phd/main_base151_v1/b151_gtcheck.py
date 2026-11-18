"""PHD-MAIN-BASE151-v1 2.3: scoring materials of the 151 buildings (jointbuildgs:dev, CPU; run_cpu.sh). No mesh, no training.

  python b151_gtcheck.py
Reads JUDGECHECK-v2 stage0/buildings.json (in_scope) and analysis/gt_<prior>.npz (paired GT points with case and tau), the TRAINUNIT-v2
building membership table (넷 판 rows) and TU1 cells.json. Writes docs tables gt_buildings.{csv,json,md}, gt_summary.{csv,json,md},
and /b151/gt/gt151_<prior>.npz (the paired GT rows of the 151 buildings with xyz, normal, wall, case, tau, building, cell of the point,
cell of the building) for the 4.2 scorer.
Case codes (JUDGECHECK-v2 s6_assemble.cases_nine = GTJUDGE normal_line.cases): 0 both valid, 1 prior error (image only correct),
2 image depth error (prior only correct), 4 image depth missing; 3 = outside the four cases. scientific_verdict: null
"""
import csv

import numpy as np

from b151_common import *

T = D / 'tables'
CASES = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 4: '영상 깊이 결측', 3: '네 경우 밖'}


def write(name, rows, note):
    T.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0].keys())
    with (T / f'{name}.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)
    dump(T / f'{name}.json', dict(at=now(), note=note, rows=rows, scientific_verdict=None))
    lines = [f'# {name}', '', note, '', 'scientific_verdict: null', '', '| ' + ' | '.join(keys) + ' |', '|' + '---|' * len(keys)]
    for r in rows:
        lines.append('| ' + ' | '.join('' if r[k] is None else (f'{r[k]:.4g}' if isinstance(r[k], float) else str(r[k])) for k in keys) + ' |')
    (T / f'{name}.md').write_text('\n'.join(lines) + '\n')


def cell_of(xy, cells):
    out = np.full(len(xy), -1, np.int8)
    for c in cells:
        lo, hi = np.array(c['original_min']), np.array(c['original_max'])
        m = (xy[:, 0] >= lo[0]) & (xy[:, 0] < hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] < hi[1])
        out[m] = c['id']
    return out


def main():
    c = cfg()
    cells = c['cells']['per_cell']
    B = {r['building']: r for r in json.loads((JC2 / 'stage0/buildings.json').read_text())['rows'] if r['in_scope']}
    assert len(B) == 151, len(B)
    mem = {}
    with (R / 'docs/experiments/phd/main_trainunit_v1/v2/tables/building_membership.csv').open() as f:
        for r in csv.DictReader(f):
            if r['plan'] == '넷':
                mem[r['building']] = r
    missing_mem = sorted(b for b in B if b not in mem)
    out = {b: dict(building=b, group=B[b]['group'], experiment_sites=','.join(B[b]['experiment_sites']), search_region=B[b]['search_region'],
                   cell=int(mem[b]['cell']) if b in mem else None, centroid_x=float(mem[b]['centroid_x']) if b in mem else None,
                   centroid_y=float(mem[b]['centroid_y']) if b in mem else None,
                   footprint_inside_expanded_cell=mem[b]['footprint_inside_expanded_cell'] == 'True' if b in mem else None) for b in sorted(B)}
    summ = []
    for prior in ['LoD2', 'ALS']:
        z = np.load(JC2 / 'analysis' / f'gt_{prior}.npz')
        bld = z['building']
        paired = z['paired']
        keep = paired & np.isin(bld, list(B))
        ix = np.flatnonzero(keep)
        case = z['case'][ix]
        tau = z['tau'][ix]
        xyz = z['xyz'][ix]
        normal = z['normal'][ix]
        wall = z['patch_kind'][ix] == 2
        names = bld[ix]
        pc = cell_of(xyz[:, :2], cells)
        bc = np.array([out[b]['cell'] if out[b]['cell'] is not None else -1 for b in names], np.int8)
        savez = np.savez_compressed
        (B_OUT := B_ROOT / 'gt').mkdir(parents=True, exist_ok=True)
        savez(B_OUT / f'gt151_{prior}.npz', xyz=xyz, normal=normal, wall=wall, case=case, tau=tau, building=names, point_cell=pc, building_cell=bc,
              src=z['src'][ix], site=z['site'][ix], gt_kind=z['gt_kind'][ix], source_index=ix)
        for b in B:
            m = names == b
            o = out[b]
            o[f'{prior}_gt'] = int(m.sum())
            for k in [0, 1, 2, 4, 3]:
                o[f'{prior}_case{k}'] = int((m & (case == k)).sum())
            o[f'{prior}_outside_own_cell'] = int((m & (pc != bc)).sum())
            o[f'{prior}_small_cases'] = ','.join(str(k) for k in [0, 1, 2, 4] if 0 < o[f'{prior}_case{k}'] < 200)
        n_with = sum(1 for b in B if out[b][f'{prior}_gt'] > 0)
        summ.append(dict(prior=prior, buildings_in_scope=len(B), buildings_with_gt=n_with, buildings_without_gt=len(B) - n_with,
                         gt_points=int(len(ix)), gt_points_file_paired=int(paired.sum()), rows_file=int(len(paired)),
                         **{f'case{k}_{CASES[k]}': int((case == k).sum()) for k in [0, 1, 2, 4, 3]},
                         points_outside_building_cell=int((pc != bc).sum()), tau_min=float(np.nanmin(tau)), tau_max=float(np.nanmax(tau)),
                         tau_nonfinite=int((~np.isfinite(tau)).sum()), source=f'JUDGECHECK-v2 analysis/gt_{prior}.npz', source_sha256=sha(JC2 / 'analysis' / f'gt_{prior}.npz')))
        print('GT', prior, len(ix), n_with, flush=True)
    rows = list(out.values())
    write('gt_buildings', rows, '2.3: the 151 in-scope buildings (JUDGECHECK-v2 stage0/buildings.json), cell = 넷 판 footprint-centroid cell (TRAINUNIT-v2 '
          'building_membership.csv), paired GT points per prior and case (0 both valid, 1 prior error, 2 image depth error, 4 image depth missing, '
          '3 outside the four cases), GT points lying outside the building\'s own original cell, cases with 1-199 points (small)')
    write('gt_summary', summ, '2.3: totals per prior over the 151 buildings; missing membership rows: ' + (', '.join(missing_mem) or 'none'))


B_ROOT = B
if __name__ == '__main__':
    main()
