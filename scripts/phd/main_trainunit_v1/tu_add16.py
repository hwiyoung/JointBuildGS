"""Addendum 16 read-out: the four comparisons of section 0.3 for ALS with every plan under the elongation filter.
Unchanged scorer (add2_scores.metric_rows, section 3.4 accuracy rule), unchanged boundary band rule (2 m, as tu_tables.band).
Runs with whatever exists; a missing plan is written as '결과 없음'.

  python tu_add16.py table   -> tables/add16_summary_ALS.*, add16_comparisons_ALS.*, add16_comparisons_scene_ALS.*,
                                add16_band_ALS.*, add16_runs_ALS.*, add16_methods_ALS.*
  python tu_add16.py cellfix -> tables/add17_R1rep_cell.*, add17_R1rep_case_cell.*, add17_check.*   (addendum 17)
  python tu_add16.py fig     -> figures/add16_comparisons_ALS.png|json, figures/add16_runs_ALS.png|json
Addendum 17 adds the plan 다_칸1고정 (cellsef1fix_ALS_s0: cell 1 with the R1rep single-site scene radius). Its B0_b10 and
B173nb_b10 values are those of 다 by construction (their crop boxes do not reach cell 1) and are marked so.
"""
import re
import sys

import tu_tables as tt   # binds the GTJUDGE common paths as in tu_tables
from tu_common import *
from tu_cause import write

A16 = C / 'addendum16.json'
PRIOR = 'ALS'
PLANS = dict(기준='ef_s0', 씨앗반복='ef_s1', 가='campusef30k_ALS_s0', 나='campusef120k_ALS_s0', 다='cellsef_ALS_s0', 다_칸1고정='cellsef1fix_ALS_s0')
PAIRS = [(1, '씨앗반복', '기준'), (2, '가', '나'), (3, '나', '다'), (4, '다', '기준')]   # section 0.3
EXTRA = [('가', '기준'), ('가', '다'), ('다_칸1고정', '기준'), ('다_칸1고정', '다')]       # not in 0.3: 나 not run; addendum 17 diagnosis
SAME_AS_CELLS = {'B0_b10', 'B173nb_b10'}   # crop boxes do not reach cell 1: 다_칸1고정 = 다 by construction
CASES = [0, 1, 2, 4]
NAME = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음', 'all': '장면 전체'}
MET = [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]


def locked():
    assert sha(A16) == json.loads((C / 'addendum16.lock.json').read_text())['sha256'], 'addendum 16 changed after lock'


def summary():
    out, look_all = [], {}
    for site in SITES:
        stem = f'{site}__{PRIOR}'
        have = [m for m in tt.BASE + list(PLANS.values()) if (TU / 'gt/scenes' / stem / 'distances' / f'{m}.npz').exists()]
        look = {(r['method'], r['surface'], r['case_id']): r for r in tt.add2_scores.metric_rows(site, PRIOR, have)}
        look_all[site] = look
        for plan, fam in PLANS.items():
            status = '있음'
            if plan == '다_칸1고정' and site in SAME_AS_CELLS:
                fam, status = PLANS['다'], '다와 같음(평가 상자가 칸1에 닿지 않음)'
            if (fam, 'all', 'all') not in look:
                out.append(dict(site=site, plan=plan, family=fam, status='하지 않음(덧붙임 17)' if plan == '나' else '결과 없음'))
                continue
            row = dict(site=site, plan=plan, family=fam, status=status)
            for case in CASES + ['all']:
                r = look[(fam, 'all', case)]
                for metric, k in MET:
                    row[f'{metric}_{NAME[case]}'] = r[k]
                row[f'n_gt_{NAME[case]}'] = r['n_gt']
            for metric, k in MET:   # largest gap to the best of the comparison methods and this plan (tu_tables.summary rule)
                gaps = []
                for case in CASES:
                    r = look[(fam, 'all', case)]
                    if r['n_gt'] < 1000 or r[k] is None:
                        continue
                    best = max(v[k] for m in tt.BASE + [fam] if (v := look.get((m, 'all', case))) and v[k] is not None)
                    gaps.append((best - r[k], case))
                g = max(gaps) if gaps else (None, None)
                row[f'최대격차_{metric}_pp'] = g[0]
                row[f'최대격차_{metric}_경우'] = NAME.get(g[1]) if g[1] is not None else None
            out.append(row)
    write('add16_summary_ALS', out, 'addendum 16: ALS, every plan with the elongation filter (기준 ef_s0, 씨앗반복 ef_s1, 가 campusef30k, 나 campusef120k, 다 cellsef): four cases and scene completeness/accuracy (unchanged scorer, section 3.4 rule), n_gt, largest gap to the best comparison method (cases with n_gt >= 1000)')
    return out


def comparisons(summ):
    s = {(r['site'], r['plan']): r for r in summ if r['status'] == '있음' or r['status'].startswith('다와 같음')}
    keys = [f'{m}_{NAME[c]}' for c in CASES + ['all'] for m, _ in MET] + [f'최대격차_{m}_pp' for m, _ in MET]
    out, scene = [], []
    for site in SITES:
        for k in keys:
            case = k.split('_', 1)[1] if not k.startswith('최대격차') else None
            b, sd = s.get((site, '기준')), s.get((site, '씨앗반복'))
            n = b.get(f'n_gt_{case}') if b and case else None
            spread = abs(sd[k] - b[k]) if b and sd and b.get(k) is not None and sd.get(k) is not None else None
            row = dict(site=site, metric=k, n_gt=n, n_gt_under_1000=bool(n is not None and n < 1000),
                       **{f'값_{p}': (s.get((site, p)) or {}).get(k) for p in PLANS},
                       흔들림폭_씨앗_pp=spread, 차이기준_pp=max(spread, 2.) if spread is not None else None)
            for idx, a, c in PAIRS:
                ra, rc = s.get((site, a)), s.get((site, c))
                row[f'비교{idx}_{a}-{c}_pp'] = ra[k] - rc[k] if ra and rc and ra.get(k) is not None and rc.get(k) is not None else None
            for a, c in EXTRA:
                ra, rc = s.get((site, a)), s.get((site, c))
                row[f'추가_{a}-{c}_pp'] = ra[k] - rc[k] if ra and rc and ra.get(k) is not None and rc.get(k) is not None else None
            out.append(row)
            if k in ('완전성_장면 전체', '정확성_장면 전체', '최대격차_완전성_pp', '최대격차_정확성_pp'):
                scene.append(row)
    note = ('addenda 16/17: section 0.3 comparisons (ALS, filter): 1 씨앗반복-기준, 2 가-나, 3 나-다, 4 다-기준 (2 and 3 empty: 판 나 not run), '
            'and extra rows 가-기준, 가-다, 다_칸1고정-기준, 다_칸1고정-다, in %p, next to the seed '
            'spread |ef_s1 - ef_s0| and max(seed spread, 2 %p); n_gt from the reference rows of the case; the appendix selection rule '
            'is applied by the user / analysis session, not here')
    write('add16_comparisons_ALS', out, note)
    write('add16_comparisons_scene_ALS', scene, note + '; scene rows and largest gaps only')
    return out


def band():
    segs = json.loads((TU / 'cells/cells.json').read_text())['boundaries']
    out = []
    for site in SITES:
        stem = f'{site}__{PRIOR}'
        row = loadz(TU / 'gt/scenes' / stem / 'rows.npz', ['xyz', 'row_tau_m'])
        xy = row['xyz'][:, :2]
        dist = np.full(len(xy), np.inf)
        for sg in segs:
            lo, hi = np.array(sg['lo']), np.array(sg['hi'])
            dist = np.minimum(dist, np.linalg.norm(xy - np.clip(xy, lo, hi), axis=1))
        m = dist <= 2.
        tau = row['row_tau_m']
        for plan, fam in PLANS.items():
            note = '있음'
            if plan == '다_칸1고정' and site in SAME_AS_CELLS:
                fam, note = PLANS['다'], '다와 같음(평가 상자가 칸1에 닿지 않음)'
            p = TU / 'gt/scenes' / stem / 'distances' / f'{fam}.npz'
            if not p.exists():
                out.append(dict(site=site, plan=plan, status='하지 않음(덧붙임 17)' if plan == '나' else '결과 없음'))
                continue
            s = loadz(p, ['row_s'])['row_s']
            for part, mm in [('띠', m), ('띠 밖', ~m)]:
                if not mm.any():
                    out.append(dict(site=site, plan=plan, part=part, rows=0, status='참값 점 없음'))
                    continue
                v = tt.values(s[mm], tau[mm])
                fl = np.isfinite(s[mm]) & (s[mm] > tau[mm])
                out.append(dict(site=site, plan=plan, part=part, rows=int(mm.sum()), nearest_row_to_boundary_m=float(dist.min()),
                                completeness_pct=v['within_pct'], floating_pct=100. * float(fl.mean()), no_surface_pct=v['no_surface_pct'], status=note))
    write('add16_band_ALS', out, 'addendum 16: reference rows within 2 m (xy) of an original 판 다 cell boundary (띠) and the rest, per plan: completeness, floating (s > tau) and no-surface shares (tu_tables.band rule)')


def psnr(att, iters):
    log = att / 'train.log'
    out = {}
    if log.exists():
        txt = log.read_bytes().decode('utf-8', 'replace').replace('\r', '\n')
        for mm in re.finditer(r'\[ITER (\d+)\] Evaluating (train|test): L1 ([0-9.eE+-]+) PSNR ([0-9.eE+-]+)', txt):
            if int(mm.group(1)) == iters:
                out[mm.group(2)] = float(mm.group(4))
    return out.get('train'), out.get('test')


def run_rows(name, plan, unit, n_train, iters, first=None):
    rec = TU / 'runs/ef' / name / 'receipt.json'
    if not rec.exists():
        return dict(plan=plan, unit=unit, run=name, status='하지 않음(덧붙임 17)' if plan == '나' else '결과 없음', train_images=n_train,
                    iterations=iters, passes_per_image=iters / n_train)
    r = json.loads(rec.read_text())
    last = r['attempts'][-1]
    att = rec.parent / f'attempt{last["attempt"]}'
    t = [json.loads(l) for l in (att / 'model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()] if (att / 'model/jbgs_trace.jsonl').exists() else []
    hours = (last.get('seconds') or 0) / 3600
    g = [x['gaussians'] for x in t]
    peak = max([x['peak_cuda_reserved_bytes'] for x in t] or [0]) / 2 ** 30
    rss = max([x.get('peak_rss_bytes', 0) for x in t] or [0]) / 2 ** 30
    if first is not None:   # cell 0: first half was cell0ef to 15,000
        f = TU / 'runs/ef' / first
        t0 = [json.loads(l) for l in (f / 'attempt1/model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()]
        hours += json.loads((f / 'receipt.json').read_text())['attempts'][0]['seconds'] / 3600
        g = [x['gaussians'] for x in t0] + g
        peak = max(peak, max(x['peak_cuda_reserved_bytes'] for x in t0) / 2 ** 30)
        rss = max(rss, max(x.get('peak_rss_bytes', 0) for x in t0) / 2 ** 30)
    ptr, pte = psnr(att, iters)
    ov = att / 'model/target_monitor/health_override.jsonl'
    ext = json.loads((att / 'extent_override.json').read_text()) if (att / 'extent_override.json').exists() else {}
    return dict(plan=plan, unit=unit, run=name, status=r['status'], attempts=len(r['attempts']), host_guard_stops=r.get('host_guard_stops', 0),
                hours=hours, stopped_attempt_hours=sum(a.get('seconds') or 0 for a in r['attempts'][:-1]) / 3600,
                last_iteration=t[-1]['iteration'] if t else None, final_gaussians=g[-1] if g else None, max_gaussians=max(g) if g else None,
                peak_reserved_GiB=peak, peak_rss_GiB=rss, train_images=n_train, iterations=iters, passes_per_image=iters / n_train,
                psnr_train_5views=ptr, psnr_test=pte, min_host_available_GiB=last.get('min_host_available_GiB'),
                count_rule_records=len([l for l in ov.read_text().splitlines() if l.strip()]) if ov.exists() else 0,
                scene_radius_m=ext.get('used_radius'), scene_radius_fork_m=ext.get('fork_radius'), scene_radius_fixed=ext.get('fixed'))


def runs():
    out = []
    single = dict(B0_b10='B0', R1rep_b10='R1rep', B173nb_b10='B173nb')
    for site, short in single.items():
        n = len(json.loads((S0 / 'fork_inputs/s61' / site / 'split.json').read_text())['train'])
        out.append(run_rows(f'{short}ef_ALS_s0', '기준', site, n, 30000))
        out.append(run_rows(f'{short}ef_ALS_s1', '씨앗반복', site, n, 30000))
    nc = len(json.loads((TU / 'scenes/campus/split.json').read_text())['train'])
    out.append(run_rows('campusef30k_ALS_s0', '가', 'campus', nc, 30000))
    out.append(run_rows('campusef120k_ALS_s0', '나', 'campus', nc, 120000))
    cells = []
    for k in range(4):
        n = len(json.loads((TU / f'scenes/cell{k}/split.json').read_text())['train'])
        cells.append(run_rows(f'cellsef_ALS_s0_cell{k}', '다', f'cell{k}', n, 30000, first='cell0ef_ALS_s0' if k == 0 else None))
    out += cells
    n1 = len(json.loads((TU / 'scenes/cell1/split.json').read_text())['train'])
    out.append(run_rows('cellsef_ALS_s0_cell1fix', '다_칸1고정', 'cell1', n1, 30000))   # addendum 17
    ch = [c['hours'] for c in cells if c.get('hours')]
    out.append(dict(plan='다', unit='칸 넷 합', run='cellsef_ALS_s0', status='합' if len(ch) == 4 else '일부',
                    hours=sum(ch), hours_two_gpus=max(sum(ch) / 2, max(ch)) if ch else None,
                    max_gaussians=max(c.get('max_gaussians') or 0 for c in cells), peak_reserved_GiB=max(c.get('peak_reserved_GiB') or 0 for c in cells),
                    peak_rss_GiB=max(c.get('peak_rss_GiB') or 0 for c in cells)))
    write('add16_runs_ALS', out, 'addendum 16: per run (ALS, filter): status, GPU hours of the attempt that produced the result (cell 0 includes cell0ef to 15,000; stopped attempts apart), gaussians final/max, GPU reserved max, host RSS max, training images, passes per image, training PSNR (5 views) and test PSNR at the last iteration, minimum host MemAvailable, count-rule records; last row: 판 다 sums (two GPUs = max(sum/2, longest cell))')
    return out


def methods():
    out = []
    for site in SITES:
        have = [m for m in tt.BASE if (TU / 'gt/scenes' / f'{site}__{PRIOR}' / 'distances' / f'{m}.npz').exists()]
        look = {(r['method'], r['surface'], r['case_id']): r for r in tt.add2_scores.metric_rows(site, PRIOR, have)}
        for m in have:
            row = dict(site=site, method=m)
            for case in CASES + ['all']:
                r = look[(m, 'all', case)]
                for metric, k in MET:
                    row[f'{metric}_{NAME[case]}'] = r[k]
            out.append(row)
    write('add16_methods_ALS', out, 'addendum 16: comparison methods (ALS boxes) with the same scorer, four cases and scene; the reference of the largest-gap column')


def locked17():
    assert sha(C / 'addendum17.json') == json.loads((C / 'addendum17.lock.json').read_text())['sha256'], 'addendum 17 changed after lock'


def table():
    cfg()
    locked()
    locked17()
    summ = summary()
    comparisons(summ)
    band()
    runs()
    methods()
    print('ADD16_TABLE_DONE', flush=True)


def cellfix():
    """addendum 17: R1rep by original cell and case x cell (addendum 15 part B counting) for 다, 다_칸1고정 and the two filter seeds"""
    cfg()
    locked17()
    import tu_add15 as a15
    a15.RUNS = dict(판다필터='cellsef_ALS_s0', 판다_칸1고정='cellsef1fix_ALS_s0', 단일필터_씨앗0='ef_s0', 단일필터_씨앗1='ef_s1')
    cells, _ = a15.geometry()
    site = 'R1rep_b10'
    arrs, row, labels = a15.site_arrays(site)
    worst = a15.check(site, arrs, row, labels)
    by_cell = a15.table(site, arrs, row, labels, lambda xy, case, k: a15.cell_of(xy, cells) == k, [1, 2], lambda k: f'칸{k}')
    by_case = a15.table(site, arrs, row, labels, lambda xy, case, ck: (case == ck[0]) & (a15.cell_of(xy, cells) == ck[1]),
                        [(c, k) for c in a15.CASES for k in [1, 2]], lambda ck: f'{a15.CASES[ck[0]]} · 칸{ck[1]}')
    for r in by_cell + by_case:
        w = {lab: r.get(f'{lab}_within_pct') for lab in a15.RUNS}
        r['칸1고정-씨앗0_pp'] = a15.diff(w['판다_칸1고정'], w['단일필터_씨앗0'])
        r['칸1고정-씨앗1_pp'] = a15.diff(w['판다_칸1고정'], w['단일필터_씨앗1'])
        r['칸1고정-판다필터_pp'] = a15.diff(w['판다_칸1고정'], w['판다필터'])
    note = ('addendum 17: R1rep_b10 ALS by original cell (and case x cell), addendum 15 part B counting: 판다필터 = cellsef_ALS_s0, '
            '판다_칸1고정 = cellsef1fix_ALS_s0 (cell 1 with the R1rep single-site scene radius), 씨앗0/1 = ef_s0/ef_s1; within/outward/inward/no surface %')
    write('add17_R1rep_cell', by_cell, note)
    write('add17_R1rep_case_cell', by_case, note)
    write('add17_check', [dict(site=site, runs=list(arrs), max_abs_diff_to_metric_rows=worst)], 'addendum 17: bins summed back against add2_scores.metric_rows')
    for r in by_cell:
        print('CELLFIX', r['bin'], r['metric'], {k: round(v, 2) for k, v in r.items() if k.endswith('_pp') and v is not None}, flush=True)


def fig():
    """comparison figure (scene completeness/accuracy differences next to the criterion band) and run figure (hours, memory)"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 9})
    rows = json.loads((D / 'tables/add16_comparisons_scene_ALS.json').read_text())['rows']
    cols = [k for k in rows[0] if k.startswith('비교') or k.startswith('추가')]
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.5), sharey='row')
    for j, site in enumerate(SITES):
        for i, metric in enumerate(['완전성_장면 전체', '정확성_장면 전체']):
            ax = axes[i][j]
            r = next(x for x in rows if x['site'] == site and x['metric'] == metric)
            vals = [r[c] for c in cols]
            crit = r['차이기준_pp']
            xs = np.arange(len(cols))
            ax.bar(xs, [0 if v is None else v for v in vals], color=['#4B2E8A' if c.startswith('비교') else '#009e73' for c in cols])
            for x, v in zip(xs, vals):
                if v is None:
                    ax.text(x, 0, '없음', ha='center', va='bottom', fontsize=7, color='0.4')
            if crit is not None:
                ax.axhspan(-crit, crit, color='0.85', zorder=0)
            ax.axhline(0, color='0.3', lw=.6)
            ax.set_xticks(xs, [c.replace('_pp', '').replace('_', ' ') for c in cols], rotation=60, ha='right', fontsize=7)
            ax.set_title(f'{site} · {metric.replace("_", " ")}' + (f' · 회색 띠 = ±{crit:.2f} %p' if crit is not None else ' · 씨앗 흔들림 없음'))
            if j == 0:
                ax.set_ylabel('차 (%p)')
    fig.suptitle('항공 LiDAR · 모든 판 길쭉함 필터 · 0.3의 비교(보라)와 추가 비교(초록) · 회색 띠 = max(씨앗 흔들림, 2 %p)')
    fig.subplots_adjust(bottom=.2, top=.9, hspace=.9, wspace=.08)
    out = D / 'figures/add16_comparisons_ALS'
    fig.savefig(out.with_suffix('.png'), dpi=180, facecolor='white')
    plt.close(fig)
    dump(out.with_suffix('.json'), dict(at=now(), source='tables/add16_comparisons_scene_ALS.json', columns=cols, script_sha256=sha(__file__), scientific_verdict=None))
    runs_ = [r for r in json.loads((D / 'tables/add16_runs_ALS.json').read_text())['rows'] if r.get('hours') and r.get('unit') != '칸 넷 합']
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.8))
    lab = [f'{r["plan"]} · {r["unit"]}' for r in runs_]
    for a, key, t in zip(ax, ['hours', 'peak_reserved_GiB', 'peak_rss_GiB'], ['학습 시간 (GPU 시간)', 'GPU 예약 최대 (GiB)', '호스트 RSS 최대 (GiB)']):
        a.barh(range(len(runs_)), [r.get(key) or 0 for r in runs_], color='#4B2E8A')
        a.set_yticks(range(len(runs_)), lab if a is ax[0] else [''] * len(runs_), fontsize=7)
        a.invert_yaxis()
        a.set_title(t)
    fig.suptitle('항공 LiDAR · 판별 시간과 메모리 (결과를 낸 시도)')
    fig.subplots_adjust(left=.16, wspace=.08)
    out = D / 'figures/add16_runs_ALS'
    fig.savefig(out.with_suffix('.png'), dpi=180, facecolor='white')
    plt.close(fig)
    dump(out.with_suffix('.json'), dict(at=now(), source='tables/add16_runs_ALS.json', script_sha256=sha(__file__), scientific_verdict=None))
    print('ADD16_FIG_DONE', flush=True)


if __name__ == '__main__':
    dict(table=table, cellfix=cellfix, fig=fig)[sys.argv[1]](*sys.argv[2:])
