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
    fams = dict(기준='FINALTRAIN_30000', 씨앗반복='seed1_s1', 필터='ef_s0')
    have = [m for m in fams.values() if (TU / 'gt/scenes' / f'{site}__{prior}' / 'distances' / f'{m}.npz').exists()]
    rows = add2_scores.metric_rows(site, prior, have)
    look = {(r['method'], r['surface'], r['case_id']): r for r in rows}
    names = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음', 'all': '장면 전체'}
    out = []
    for case in [0, 1, 2, 4, 'all']:
        for metric, k in [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]:
            v = {lab: (look.get((m, 'all', case)) or {}).get(k) for lab, m in fams.items()}
            n = (look.get(('FINALTRAIN_30000', 'all', case)) or {}).get('n_gt')
            spread = abs(v['씨앗반복'] - v['기준']) if v['씨앗반복'] is not None and v['기준'] is not None else None
            diff = v['필터'] - v['기준'] if v['필터'] is not None and v['기준'] is not None else None
            out.append(dict(case=names[case], metric=metric, n_gt=n, 기준=v['기준'], 씨앗반복=v['씨앗반복'], 필터=v['필터'],
                            필터_빼기_기준_pp=diff, 씨앗_흔들림폭_pp=spread,
                            흔들림폭_안=(abs(diff) <= spread) if diff is not None and spread is not None else None))
    write('ef_scores_B0_b10__ALS', out, 'addendum 12: GTJUDGE completeness/accuracy (unchanged scorer, §3.4 rule) of the elongation-filter B0 ALS run against the FINALTRAIN seed-0 baseline and the seed-1 repeat; spread = |seed1 - seed0|; no pass mark set')
    for r in out:
        print('SC', r['case'], r['metric'], r['기준'], r['씨앗반복'], r['필터'], r['필터_빼기_기준_pp'], r['씨앗_흔들림폭_pp'], flush=True)


if __name__ == '__main__':
    dict(runs=runs, scores=scores)[sys.argv[1]](*sys.argv[2:])
