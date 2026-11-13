"""Addendum 12 read-out (elongation filter): each filter run next to its original run, and the B0 baseline scores.

  python tu_ef.py runs      -> tables/ef_runs.*, figures/ef_runs.png
  python tu_ef.py scores    -> tables/ef_scores_B0_b10__ALS.*   (after tu_post.py run ef_B0_b10_ALS)
No GT is read by `runs`; `scores` reads only the GTJUDGE distance files through the unchanged add2_scores.metric_rows.
"""
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

from tu_common import *
from tu_cause import ply, runs as cause_runs, state, write
from tu_growth import lineage

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 9})

PAIRS = [  # (filter run, original run key, original attempt dirs, label)
    ('B0ef_ALS_s0', 'base_s0', '기준 B0 ALS (FINALTRAIN 씨앗 0)'),
    ('cell0ef_ALS_s0', 'cell0', '판 다 칸 0'),
    ('probe3ef_ALS_s0', 'probe3', 'probe3 지붕 A 작은 판'),
    ('probe4ef_ALS_s0', 'probe4', 'probe4 지붕 B 작은 판'),
]


def original_atts(key):
    if key in ('probe3', 'probe4'):
        run = TU / 'runs/probes' / f'{key}_ALS_s0'
        return sorted(run.glob('attempt*'), key=lambda p: int(p.name[7:]))
    return cause_runs_by_key()[key]['atts']


def cause_runs_by_key():
    return {r['key']: r for r in cause_runs()}


def ef_atts(name):
    run = TU / 'runs/ef' / name
    return sorted(run.glob('attempt*'), key=lambda p: int(p.name[7:]))


def last_state(atts):
    best = None
    for a in atts:
        m = a / 'model'
        for d in ['jbgs_complete', 'point_cloud']:
            for p in (m / d).glob('iteration_*'):
                it = int(p.name.split('_')[1])
                if (p / 'point_cloud.ply').exists() and (best is None or it > best[0]):
                    best = (it, m)
    return best


def describe(atts, receipt=None):
    its, g, peak = lineage(atts)
    at = dict(zip(its, g))
    ls = last_state(atts)
    row = dict(last_iteration=max(at) if at else None, gaussians_6000=at.get(6000), gaussians_7000=at.get(7000), gaussians_12000=at.get(12000),
               gaussians_15000=at.get(15000), max_gaussians_7000_last=max([v for t, v in at.items() if t >= 7000] or [None]) if at else None,
               peak_reserved_GiB=peak / 2**30 if peak else None)
    if ls:
        it, m = ls
        l = ply(state(m, it), ('scale_0', 'scale_1', 'init_id'))
        s0, s1 = np.exp(l['scale_0']), np.exp(l['scale_1'])
        needle = (np.minimum(s0, s1) / np.maximum(s0, s1)) <= .01
        cnt = np.bincount(l['init_id'][l['init_id'] >= 0])
        i = int(np.argmax(cnt))
        fam = l['init_id'] == i
        row |= dict(state_iteration=it, gaussians_state=len(s0), needle_share=float(needle.mean()), largest_family=int(cnt[i]),
                    largest_family_share=float(cnt[i] / len(s0)), largest_family_needle_share=float(needle[fam].mean()))
    if receipt and receipt.exists():
        r = json.loads(receipt.read_text())
        row['status'] = r.get('status')
        row['hours'] = sum(a.get('seconds', 0) for a in r.get('attempts', [])) / 3600 if r.get('attempts') else None
    return row, (its, g)


def runs():
    cfg()
    rows, curves = [], {}
    for name, key, label in PAIRS:
        ea = ef_atts(name)
        if not ea:
            print('EF', name, 'not started', flush=True)
            continue
        r_ef, c_ef = describe(ea, TU / 'runs/ef' / name / 'receipt.json')
        oa = original_atts(key)
        orec = (TU / 'runs/probes' / f'{key}_ALS_s0' / 'receipt.json') if key.startswith('probe') else None
        r_or, c_or = describe(oa, orec)
        rows.append(dict(pair=label, run='원래', name=key) | r_or)
        rows.append(dict(pair=label, run='필터', name=name) | r_ef)
        curves[label] = (c_or, c_ef)
        print('EF', name, r_ef.get('status'), r_ef.get('last_iteration'), r_ef.get('max_gaussians_7000_last'), r_ef.get('largest_family'),
              '| orig', r_or.get('max_gaussians_7000_last'), r_or.get('largest_family'), flush=True)
    write('ef_runs', rows, 'addendum 12: each elongation-filter run next to its original run: counts, peak GPU memory, needle share (elongation <= 0.01), largest family at the last saved state; no GT')
    fig, ax = plt.subplots(1, len(curves), figsize=(4.4 * len(curves), 3.8), squeeze=False)
    for a, (label, (co, ce)) in zip(ax[0], curves.items()):
        a.plot(co[0], np.array(co[1]) / 1e6, color='0.45', ls='--', lw=1.3, label='원래')
        a.plot(ce[0], np.array(ce[1]) / 1e6, color='#d62728', lw=1.7, label='길쭉함 필터 (η ≤ 0.01 복제·쪼개기 제외)')
        a.set(title=label, xlabel='반복', ylabel='가우시안 수 (백만)', xlim=(0, 30500 if 'B0' in label else 15500))
        a.grid(alpha=.3)
        a.legend(fontsize=7.5, loc='upper left')
    fig.tight_layout()
    p = D / 'figures/ef_runs.png'
    fig.savefig(p, dpi=150)
    dump(p.with_suffix('.json'), dict(at=now(), pairs=list(curves), scientific_verdict=None))
    print('FIG', p, flush=True)


def scores():
    sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
    import common as gcommon
    gcommon.O = TU / 'gt'
    gcommon.C = Path('/repo/configs/phd/main_gtjudge_v1')
    gcommon.D = TU / 'gt/docs'
    import add2_scores
    site, prior = 'B0_b10', 'ALS'
    fams = dict(필터없음_씨앗0='FINALTRAIN_30000', 필터없음_씨앗1='seed1_s1', 필터_씨앗0='ef_s0', 필터_씨앗1='ef_s1')   # addendum 13: four runs
    have = [m for m in fams.values() if (TU / 'gt/scenes' / f'{site}__{prior}' / 'distances' / f'{m}.npz').exists()]
    rows = add2_scores.metric_rows(site, prior, have)
    look = {(r['method'], r['surface'], r['case_id']): r for r in rows}
    names = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음', 'all': '장면 전체'}
    d = lambda a, b: a - b if a is not None and b is not None else None
    out = []
    for case in [0, 1, 2, 4, 'all']:
        for metric, k in [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]:
            v = {lab: (look.get((m, 'all', case)) or {}).get(k) for lab, m in fams.items()}
            n = (look.get(('FINALTRAIN_30000', 'all', case)) or {}).get('n_gt')
            row = dict(case=names[case], metric=metric, n_gt=n) | v
            row['씨앗차_필터없음_pp'] = abs(d(v['필터없음_씨앗1'], v['필터없음_씨앗0'])) if d(v['필터없음_씨앗1'], v['필터없음_씨앗0']) is not None else None
            row['씨앗차_필터_pp'] = abs(d(v['필터_씨앗1'], v['필터_씨앗0'])) if d(v['필터_씨앗1'], v['필터_씨앗0']) is not None else None
            row['필터효과_씨앗0_pp'] = d(v['필터_씨앗0'], v['필터없음_씨앗0'])
            row['필터효과_씨앗1_pp'] = d(v['필터_씨앗1'], v['필터없음_씨앗1'])
            ok = [x for x in [v['필터_씨앗0'], v['필터_씨앗1']] if x is not None], [x for x in [v['필터없음_씨앗0'], v['필터없음_씨앗1']] if x is not None]
            row['필터효과_평균_pp'] = (sum(ok[0]) / len(ok[0]) - sum(ok[1]) / len(ok[1])) if len(ok[0]) == 2 and len(ok[1]) == 2 else None
            out.append(row)
    write('ef_scores_B0_b10__ALS', out, 'addenda 12/13: GTJUDGE completeness/accuracy (unchanged scorer, §3.4 rule) of B0 ALS with and without the elongation filter, seeds 0 and 1; seed difference = |seed1 - seed0| per setting; filter effect = filter - no filter per seed and of the two-seed means; no pass mark set')
    for r in out:
        print('SC', r['case'], r['metric'], r['n_gt'], [None if r[k] is None else round(r[k], 2) for k in fams], 'seeddiff', r['씨앗차_필터없음_pp'], r['씨앗차_필터_pp'], 'effect', r['필터효과_씨앗0_pp'], r['필터효과_씨앗1_pp'], r['필터효과_평균_pp'], flush=True)


def cells():
    """addendum 14: 판 다 ALS cells with the filter (merged) against single-site runs with and without the filter, the cell
    boundary band, and per-cell time/count/memory. Unchanged scorer (add2_scores.metric_rows) and band rule (tu_tables.band)."""
    import tu_tables as tt   # binds the GTJUDGE common paths as in tu_tables
    assert sha(C / 'addendum14.json') == json.loads((C / 'addendum14.lock.json').read_text())['sha256']
    prior = 'ALS'
    F = dict(판다필터='cellsef_ALS_s0', 단일필터_씨앗0='ef_s0', 단일필터_씨앗1='ef_s1', 단일_씨앗0='FINALTRAIN_30000', 단일_씨앗1='seed1_s1')
    names = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음', 'all': '장면 전체'}
    d = lambda a, b: a - b if a is not None and b is not None else None
    out = []
    for site in SITES:
        stem = f'{site}__{prior}'
        have = [m for m in F.values() if (TU / 'gt/scenes' / stem / 'distances' / f'{m}.npz').exists()]
        look = {(r['method'], r['surface'], r['case_id']): r for r in tt.add2_scores.metric_rows(site, prior, have)}
        for case in [0, 1, 2, 4, 'all']:
            for metric, k in [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]:
                v = {lab: (look.get((m, 'all', case)) or {}).get(k) for lab, m in F.items()}
                n = (look.get(('FINALTRAIN_30000', 'all', case)) or {}).get('n_gt')
                row = dict(site=site, case=names[case], metric=metric, n_gt=n, n_gt_under_1000=bool(n is not None and n < 1000)) | v
                row['판다필터-단일필터_씨앗0_pp'] = d(v['판다필터'], v['단일필터_씨앗0'])
                row['판다필터-단일필터_평균_pp'] = d(v['판다필터'], (v['단일필터_씨앗0'] + v['단일필터_씨앗1']) / 2) if v['단일필터_씨앗1'] is not None and v['단일필터_씨앗0'] is not None else None
                row['판다필터-단일_씨앗0_pp'] = d(v['판다필터'], v['단일_씨앗0'])
                row['씨앗차_단일_pp'] = abs(d(v['단일_씨앗1'], v['단일_씨앗0'])) if d(v['단일_씨앗1'], v['단일_씨앗0']) is not None else None
                row['씨앗차_단일필터_pp'] = abs(d(v['단일필터_씨앗1'], v['단일필터_씨앗0'])) if d(v['단일필터_씨앗1'], v['단일필터_씨앗0']) is not None else None
                row['단일필터-단일_씨앗0_pp'] = d(v['단일필터_씨앗0'], v['단일_씨앗0'])
                out.append(row)
    write('cellsef_scores_ALS', out, 'addendum 14: GTJUDGE completeness/accuracy (unchanged scorer, section 3.4 rule) of the merged 판 다 ALS cells with the elongation filter (판다필터) against single-site runs with the filter (seed 0; B0 also seed 1) and without (FINALTRAIN seed 0, seed-1 repeat); seed differences |seed1-seed0|; no pass mark')
    for r in out:
        print('CS', r['site'], r['case'], r['metric'], r['n_gt'], [None if r[x] is None else round(r[x], 2) for x in F], 'cell-single_f', r['판다필터-단일필터_씨앗0_pp'], 'seeddiff', r['씨앗차_단일_pp'], r['씨앗차_단일필터_pp'], flush=True)
    # boundary band (trainunit_v1 cells.boundary_band rule, as tu_tables.band)
    segs = json.loads((TU / 'cells/cells.json').read_text())['boundaries']
    band = []
    for site in SITES:
        stem = f'{site}__{prior}'
        row = loadz(TU / 'gt/scenes' / stem / 'rows.npz', ['xyz', 'row_tau_m'])
        xy = row['xyz'][:, :2]
        dist = np.full(len(xy), np.inf)
        for sg in segs:
            lo, hi = np.array(sg['lo']), np.array(sg['hi'])
            dist = np.minimum(dist, np.linalg.norm(xy - np.clip(xy, lo, hi), axis=1))
        m = dist <= 2.
        for lab, fam in F.items():
            p = TU / 'gt/scenes' / stem / 'distances' / f'{fam}.npz'
            if not p.exists():
                continue
            s = loadz(p, ['row_s'])['row_s']
            tau = row['row_tau_m']
            for part, mm in [('띠', m), ('띠 밖', ~m)]:
                if not mm.any():
                    band.append(dict(site=site, run=lab, part=part, rows=0))
                    continue
                v = tt.values(s[mm], tau[mm])
                fl = np.isfinite(s[mm]) & (s[mm] > tau[mm])
                band.append(dict(site=site, run=lab, part=part, rows=int(mm.sum()), nearest_row_to_boundary_m=float(dist.min()), completeness_pct=v['within_pct'],
                                 floating_pct=100. * float(fl.mean()), no_surface_pct=v['no_surface_pct']))
    write('cellsef_boundary_band_ALS', band, 'addendum 14: reference rows within 2 m (xy) of an original cell boundary (띠) and the rest (띠 밖): completeness, floating (s > tau) and no-surface shares per run')
    # per-cell and single-site run records
    stats = []
    for name in [f'cellsef_ALS_s0_cell{k}' for k in range(4)] + ['R1repef_ALS_s0', 'B173nbef_ALS_s0', 'B0ef_ALS_s0', 'B0ef_ALS_s1']:
        rec = TU / 'runs/ef' / name / 'receipt.json'
        if not rec.exists():
            stats.append(dict(run=name, status='없음'))
            continue
        r = json.loads(rec.read_text())
        hrs = r['attempts'][-1].get('seconds', 0) / 3600   # the attempt that produced the result; host-guard stops (machine, not partition) apart
        lost = sum(a.get('seconds', 0) for a in r['attempts'][:-1]) / 3600
        att = TU / 'runs/ef' / name / f'attempt{r["attempts"][-1]["attempt"]}'
        t = [json.loads(l) for l in (att / 'model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()] if (att / 'model/jbgs_trace.jsonl').exists() else []
        gmax = max([x['gaussians'] for x in t] or [0])
        peak = max([x['peak_cuda_reserved_bytes'] for x in t] or [0]) / 2 ** 30
        if name.endswith('cell0'):   # first half = cell0ef to 15,000
            t0 = [json.loads(l) for l in (TU / 'runs/ef/cell0ef_ALS_s0/attempt1/model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()]
            hrs += json.loads((TU / 'runs/ef/cell0ef_ALS_s0/receipt.json').read_text())['attempts'][0]['seconds'] / 3600
            gmax, peak = max(gmax, max(x['gaussians'] for x in t0)), max(peak, max(x['peak_cuda_reserved_bytes'] for x in t0) / 2 ** 30)
        ov = att / 'model/target_monitor/health_override.jsonl'
        stats.append(dict(run=name, status=r['status'], attempts=len(r['attempts']), hours=hrs, stopped_attempt_hours=lost,
                          host_guard_stops=r.get('host_guard_stops', 0), max_gaussians=gmax, peak_reserved_GiB=peak,
                          count_rule_records=len([l for l in ov.read_text().splitlines() if l.strip()]) if ov.exists() else 0))
    cells_h = sum(s.get('hours') or 0 for s in stats if s['run'].startswith('cellsef_'))
    single_h = sum(s.get('hours') or 0 for s in stats if s['run'] in ('R1repef_ALS_s0', 'B173nbef_ALS_s0', 'B0ef_ALS_s0'))
    stats.append(dict(run='합: 칸 넷 대 단일 필터 셋(씨앗 0)', hours=cells_h, single_site_hours=single_h))
    write('cellsef_runs_ALS', stats, 'addendum 14: per-cell status, GPU hours of the attempt that produced the result (cell0 includes cell0ef to 15,000; hours of host-guard-stopped attempts apart), max gaussians, peak reserved memory and count-rule records; single-site filter runs alongside; last row: hour sums')
    for s in stats:
        print('RUN', s, flush=True)


if __name__ == '__main__':
    dict(runs=runs, scores=scores, cells=cells)[sys.argv[1]](*sys.argv[2:])
