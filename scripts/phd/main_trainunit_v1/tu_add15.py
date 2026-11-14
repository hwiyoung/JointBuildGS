"""Addendum 15 read-out (no training): where the 판 다 + filter (cellsef_ALS_s0) differs from the filter single-site runs, next to
the seed difference of the single-site runs counted the same way, and the quantities of the appendix rule for R1rep.
Reads only the unchanged GTJUDGE distance/sample files; the accuracy and completeness masks are those of add2_scores.metric_rows.

  python tu_add15.py where   -> tables/add15_where_cell.*, add15_where_band.*, add15_where_case_cell.*, add15_cell_context.*
  python tu_add15.py rule    -> tables/add15_rule_R1rep.*
"""
import sys

import tu_tables as tt   # binds the GTJUDGE common paths as in tu_tables
from tu_common import *
from tu_cause import write

A15 = C / 'addendum15.json'
PRIOR = 'ALS'
RUNS = dict(판다필터='cellsef_ALS_s0', 단일필터_씨앗0='ef_s0', 단일필터_씨앗1='ef_s1')
CASES = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음'}
BANDS = [(0., 2.), (2., 5.), (5., 10.), (10., 20.), (20., np.inf)]


def locked():
    assert sha(A15) == json.loads((C / 'addendum15.lock.json').read_text())['sha256'], 'addendum 15 changed after lock'


def geometry():
    cj = json.loads((TU / 'cells/cells.json').read_text())
    return cj['cells'], cj['boundaries']


def cell_of(xy, cells):
    """original cell id, half-open [min, max) as the merge rule (tu_postcpu.merge)"""
    out = np.full(len(xy), -1, int)
    for c in cells:
        lo, hi = np.array(c['original_min'], float), np.array(c['original_max'], float)
        m = (xy[:, 0] >= lo[0]) & (xy[:, 0] < hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] < hi[1])
        out[m] = c['id']
    return out


def boundary_distance(xy, segs):
    d = np.full(len(xy), np.inf)
    for sg in segs:
        lo, hi = np.array(sg['lo']), np.array(sg['hi'])
        d = np.minimum(d, np.linalg.norm(xy - np.clip(xy, lo, hi), axis=1))
    return d


def site_arrays(site):
    """per run: accuracy samples (s, tau, counted mask, case, xy) and completeness rows (s, tau, case, xy), as metric_rows"""
    stem = f'{site}__{PRIOR}'
    root = TU / 'gt/scenes' / stem
    row = loadz(root / 'rows.npz', ['xyz', 'row_tau_m'])
    labels = loadz(root / 'stage1_cells.npz', ['case_id'])['case_id']
    out = {}
    for lab, fam in RUNS.items():
        p = root / 'distances' / f'{fam}.npz'
        if not p.exists():
            continue
        z = loadz(p)
        ix = z['sample_reference_row']
        ok = ix >= 0
        qc = np.full(len(ix), -1, 'i1')
        qc[ok] = labels[ix[ok]]
        steep = np.abs(tt.add2_scores.normal_z(site, PRIOR, fam)) < .5
        xyz = loadz(root / 'distances' / f'{fam}_samples.npz', ['xyz'])['xyz'].astype(float)
        assert len(xyz) == len(ix), (site, fam, len(xyz), len(ix))
        out[lab] = dict(s=z['sample_s'], tau=z['sample_tau'], counted=z['sample_eligible'] & ~steep, case=qc, xy=xyz[:, :2],
                        row_s=z['row_s'])
    return out, row, labels


def stats(s, tau, mask):
    v = tt.values(s, tau, mask)
    hit = mask & np.isfinite(s)
    n = int(mask.sum())
    return dict(n=n, within_pct=v['within_pct'], outward_pct=100. * int((hit & (s > tau)).sum()) / n if n else None,
                inward_pct=100. * int((hit & (s < -tau)).sum()) / n if n else None, no_surface_pct=v['no_surface_pct'])


def diff(a, b):
    return a - b if a is not None and b is not None else None


def table(site, arrs, row, labels, key_fn, keys, name_fn):
    """rows for one site: per key, accuracy (samples) and completeness (reference rows) for each run plus differences"""
    out = []
    rxy = row['xyz'][:, :2].astype(float)
    for key in keys:
        for metric in ['정확성', '완전성']:
            r = dict(site=site, bin=name_fn(key), metric=metric)
            vals = {}
            for lab, a in arrs.items():
                if metric == '정확성':
                    m = a['counted'] & key_fn(a['xy'], a['case'], key)
                    st = stats(a['s'], a['tau'], m)
                else:
                    m = key_fn(rxy, labels, key)
                    st = stats(a['row_s'], row['row_tau_m'], m)
                vals[lab] = st
                r.update({f'{lab}_{k}': v for k, v in st.items()})
            w = {lab: vals.get(lab, {}).get('within_pct') for lab in RUNS}
            r['판다필터-씨앗0_pp'] = diff(w['판다필터'], w['단일필터_씨앗0'])
            r['판다필터-씨앗1_pp'] = diff(w['판다필터'], w['단일필터_씨앗1'])
            r['씨앗1-씨앗0_pp'] = diff(w['단일필터_씨앗1'], w['단일필터_씨앗0'])
            for k in ['outward_pct', 'inward_pct']:
                r[f'판다필터-씨앗0_{k}_pp'] = diff(vals.get('판다필터', {}).get(k), vals.get('단일필터_씨앗0', {}).get(k))
            out.append(r)
    return out


def check(site, arrs, row, labels):
    """bins summed back = metric_rows (scene and cases)"""
    look = {(r['method'], r['case_id']): r for r in tt.add2_scores.metric_rows(site, PRIOR, list(RUNS[l] for l in arrs)) if r['surface'] == 'all'}
    worst = 0.
    for lab, a in arrs.items():
        for case in list(CASES) + ['all']:
            cm = np.ones(len(a['case']), bool) if case == 'all' else a['case'] == case
            acc = stats(a['s'], a['tau'], a['counted'] & cm)['within_pct']
            rm = np.ones(len(labels), bool) if case == 'all' else labels == case
            comp = stats(a['row_s'], row['row_tau_m'], rm)['within_pct']
            ref = look[(RUNS[lab], case)]
            for x, y in [(acc, ref['accuracy_pct']), (comp, ref['completeness_pct'])]:
                if x is None and y is None:
                    continue
                worst = max(worst, abs(x - y))
    assert worst < 1e-9, (site, worst)
    return worst


def where():
    locked()
    cells, segs = geometry()
    by_cell, by_band, by_case_cell, checks = [], [], [], []
    for site in SITES:
        arrs, row, labels = site_arrays(site)
        checks.append(dict(site=site, runs=list(arrs), max_abs_diff_to_metric_rows=check(site, arrs, row, labels)))
        ids = sorted({int(c) for a in arrs.values() for c in np.unique(cell_of(a['xy'][a['counted']], cells))})
        by_cell += table(site, arrs, row, labels, lambda xy, case, k: cell_of(xy, cells) == k, ids, lambda k: f'칸{k}')
        by_band += table(site, arrs, row, labels, lambda xy, case, b: (boundary_distance(xy, segs) >= b[0]) & (boundary_distance(xy, segs) < b[1]),
                         BANDS, lambda b: f'경계에서 {b[0]:g}–{b[1]:g} m')
        keys = [(c, k) for c in CASES for k in ids]
        by_case_cell += table(site, arrs, row, labels, lambda xy, case, ck: (case == ck[0]) & (cell_of(xy, cells) == ck[1]), keys,
                              lambda ck: f'{CASES[ck[0]]} · 칸{ck[1]}')
        print('WHERE', site, list(arrs), flush=True)
    note = ('addendum 15 part B: accuracy (mesh samples, unchanged §3.4 counted mask, located by sample xyz) and completeness (reference rows, '
            'located by their xyz) per {}; within/outward (s > tau)/inward (s < -tau)/no surface %; 판다필터 = cellsef_ALS_s0, 씨앗0/1 = '
            'filter single-site ef_s0/ef_s1; 씨앗1-씨앗0 = seed difference in the same bin; no pass mark')
    write('add15_where_cell', by_cell, note.format('original cell'))
    write('add15_where_band', by_band, note.format('xy distance to the nearest original cell boundary'))
    write('add15_where_case_cell', by_case_cell, note.format('case x original cell'))
    write('add15_where_check', checks, 'addendum 15: bins summed back against add2_scores.metric_rows (accuracy and completeness, scene and cases)')
    # cell context (records only)
    ctx = []
    single = {}
    for name in ['R1repef_ALS_s0', 'B173nbef_ALS_s0', 'B0ef_ALS_s0']:
        rec = json.loads((TU / 'runs/ef' / name / 'receipt.json').read_text())
        single[name] = json.loads((TU / 'runs/ef' / name / f'attempt{rec["attempts"][-1]["attempt"]}' / 'extent_override.json').read_text())
    for c in cells:
        name = f'cellsef_ALS_s0_cell{c["id"]}'
        rec = json.loads((TU / 'runs/ef' / name / 'receipt.json').read_text())
        att = TU / 'runs/ef' / name / f'attempt{rec["attempts"][-1]["attempt"]}'
        ext = json.loads((att / 'extent_override.json').read_text())
        t = [json.loads(l) for l in (att / 'model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()]
        ctx.append(dict(unit=f'칸{c["id"]}', training_images=ext['cameras'], passes_per_image=30000 / ext['cameras'], scene_radius_m=ext['used_radius'],
                        max_gaussians=max(x['gaussians'] for x in t)))
    for name, ext in single.items():
        ctx.append(dict(unit=name, training_images=ext['cameras'], passes_per_image=30000 / ext['cameras'], scene_radius_m=ext['used_radius']))
    write('add15_cell_context', ctx, 'addendum 15: per cell and single-site filter run: training images, passes per image (30,000 / images), scene radius used by the fork, max Gaussians (cells; cell0 from the resumed run); records only')
    for r in by_cell:
        print('CELL', r['site'], r['bin'], r['metric'], {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k.endswith('_pp') or k.endswith('_n')}, flush=True)


def rule():
    locked()
    site = 'R1rep_b10'
    look = {(r['method'], r['case_id']): r for r in tt.add2_scores.metric_rows(site, PRIOR, list(RUNS.values())) if r['surface'] == 'all'}
    out = []
    for case in list(CASES) + ['all']:
        n = (look.get(('ef_s0', case)) or {}).get('n_gt')
        for metric, k in [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]:
            v = {lab: (look.get((m, case)) or {}).get(k) for lab, m in RUNS.items()}
            seed = abs(diff(v['단일필터_씨앗1'], v['단일필터_씨앗0'])) if diff(v['단일필터_씨앗1'], v['단일필터_씨앗0']) is not None else None
            mean = (v['단일필터_씨앗0'] + v['단일필터_씨앗1']) / 2 if v['단일필터_씨앗1'] is not None else None
            out.append(dict(site=site, case=CASES.get(case, '장면 전체'), metric=metric, n_gt=n, n_gt_under_1000=bool(n is not None and n < 1000), **v,
                            **{'판다필터-씨앗0_pp': diff(v['판다필터'], v['단일필터_씨앗0']), '판다필터-씨앗1_pp': diff(v['판다필터'], v['단일필터_씨앗1']),
                               '판다필터-씨앗평균_pp': diff(v['판다필터'], mean), '씨앗차_단일필터_pp': seed,
                               '차이기준_max(씨앗차,2)_pp': max(seed, 2.) if seed is not None else None}))
            print('RULE', out[-1], flush=True)
    write('add15_rule_R1rep', out, 'addendum 15: R1rep ALS, 판 다 + filter against the two filter single-site seeds; 차이기준 = max(|seed1 - seed0|, 2 %p) as in the appendix rule; the rule itself is applied by the user / analysis session')


def seen_by(X, cams):
    """per row: cameras whose image holds the projected row with positive depth (no occlusion test), their median distance,
    and the number of 45-degree azimuth sectors (camera centre around the row) holding at least one of them"""
    n = np.zeros(len(X), int)
    sectors = np.zeros(len(X), np.uint8)
    dist = np.full((len(X), len(cams)), np.nan, np.float32)
    for j, cam in enumerate(cams):
        M = np.asarray(cam['W2C'], float)
        c = X @ M[:3, :3].T + M[:3, 3]
        z = c[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'):
            u = cam['fx'] * c[:, 0] / z + cam['cx']
            v = cam['fy'] * c[:, 1] / z + cam['cy']
        m = (z > 0) & (u >= 0) & (u < cam['W']) & (v >= 0) & (v < cam['H'])
        centre = -M[:3, :3].T @ M[:3, 3]
        n += m
        az = np.arctan2(centre[1] - X[:, 1], centre[0] - X[:, 0])
        sec = (np.floor((az + np.pi) / (np.pi / 4)).astype(int) % 8).astype(np.uint8)
        sectors[m] |= (np.uint8(1) << sec[m]).astype(np.uint8)
        dist[m, j] = np.linalg.norm(X[m] - centre, axis=1)
    with np.errstate(all='ignore'):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            med = np.nanmedian(dist, axis=1)
    nsec = np.unpackbits(sectors[:, None], axis=1).sum(1)
    return n, med, nsec


def views():
    """addendum 15 supplement: training views of the reference rows in each cell's list and in the single-site list"""
    locked()
    assert sha(C / 'addendum15_views.json') == json.loads((C / 'addendum15_views.lock.json').read_text())['sha256'], 'views supplement changed after lock'
    from tu_campus import cameras
    cells, _ = geometry()
    S0P = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61'
    out = []
    for site in SITES:
        X = loadz(TU / 'gt/scenes' / f'{site}__{PRIOR}' / 'rows.npz', ['xyz'])['xyz'].astype(float)
        cid = cell_of(X[:, :2], cells)
        single = json.loads((S0P / site / 'split.json').read_text())['train']
        res = {}
        res['single'] = seen_by(X, cameras(single))
        for k in sorted(set(cid.tolist())):
            train = json.loads((TU / f'scenes/cell{k}/split.json').read_text())['train']
            m = cid == k
            sub = seen_by(X[m], cameras(train))
            ns, ds, ss = res['single']
            r = dict(site=site, cell=f'칸{k}', rows=int(m.sum()), cell_training_images=len(train), single_training_images=len(single),
                     shared_training_images=len(set(train) & set(single)))
            for lab, (n, d, s) in [('칸', sub), ('단일', (ns[m], ds[m], ss[m]))]:
                r.update({f'{lab}_cameras_median': float(np.median(n)), f'{lab}_cameras_p10': float(np.percentile(n, 10)),
                          f'{lab}_rows_under_10_cameras_pct': 100. * float((n < 10).mean()),
                          f'{lab}_distance_median_m': float(np.nanmedian(d)) if np.isfinite(d).any() else None,
                          f'{lab}_sectors_median': float(np.median(s)), f'{lab}_rows_under_4_sectors_pct': 100. * float((s < 4).mean())})
            r['카메라수_칸-단일_median_of_row_difference'] = float(np.median(sub[0] - ns[m]))
            r['rows_with_fewer_cameras_in_cell_pct'] = 100. * float((sub[0] < ns[m]).mean())
            out.append(r)
            print('VIEWS', r, flush=True)
    write('add15_views', out, 'addendum 15 supplement: per original cell part of each site, training cameras whose image holds the projected reference row (no occlusion test) in the cell list (칸) and in the single-site list (단일): median and 10th percentile count, share under 10, median distance, median 45-degree azimuth sectors, share under 4 sectors; no pass mark')
    # radius-scaled quantities (code facts: lr = position_lr_init x radius, clone if max scale <= percent_dense x radius else split, prune if max scale > 0.1 x radius)
    rad = []
    for name in [f'cellsef_ALS_s0_cell{k}' for k in range(4)] + ['R1repef_ALS_s0', 'B173nbef_ALS_s0', 'B0ef_ALS_s0']:
        rec = json.loads((TU / 'runs/ef' / name / 'receipt.json').read_text())
        ext = json.loads((TU / 'runs/ef' / name / f'attempt{rec["attempts"][-1]["attempt"]}' / 'extent_override.json').read_text())
        r = ext['used_radius']
        rad.append(dict(run=name, radius_m=r, position_lr_init=0.00016 * r, clone_split_size_threshold_m=0.01 * r, prune_size_threshold_m=0.1 * r))
    write('add15_radius', rad, 'addendum 15 supplement: scene radius used by the fork and the three quantities it scales (fork r23 scene/gaussian_model.py: position_lr_init 0.00016 x radius; clone if max scale <= percent_dense 0.01 x radius, else split; prune if max scale > 0.1 x radius after the opacity reset); code facts, no training')


if __name__ == '__main__':
    dict(where=where, rule=rule, views=views)[sys.argv[1]](*sys.argv[2:])
