"""Addendum 16 read-out: the four comparisons of section 0.3 for ALS with every plan under the elongation filter.
Unchanged scorer (add2_scores.metric_rows, section 3.4 accuracy rule), unchanged boundary band rule (2 m, as tu_tables.band).
Runs with whatever exists; a missing plan is written as '결과 없음'.

  python tu_add16.py table   -> tables/add16_summary_ALS.*, add16_comparisons_ALS.*, add16_comparisons_scene_ALS.*,
                                add16_band_ALS.*, add16_runs_ALS.*
"""
import re
import sys

import tu_tables as tt   # binds the GTJUDGE common paths as in tu_tables
from tu_common import *
from tu_cause import write

A16 = C / 'addendum16.json'
PRIOR = 'ALS'
PLANS = dict(기준='ef_s0', 씨앗반복='ef_s1', 가='campusef30k_ALS_s0', 나='campusef120k_ALS_s0', 다='cellsef_ALS_s0')
PAIRS = [(1, '씨앗반복', '기준'), (2, '가', '나'), (3, '나', '다'), (4, '다', '기준')]
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
            if (fam, 'all', 'all') not in look:
                out.append(dict(site=site, plan=plan, family=fam, status='결과 없음'))
                continue
            row = dict(site=site, plan=plan, family=fam, status='있음')
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
    s = {(r['site'], r['plan']): r for r in summ if r['status'] == '있음'}
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
            out.append(row)
            if k in ('완전성_장면 전체', '정확성_장면 전체', '최대격차_완전성_pp', '최대격차_정확성_pp'):
                scene.append(row)
    note = ('addendum 16: section 0.3 comparisons (ALS, filter): 1 씨앗반복-기준, 2 가-나, 3 나-다, 4 다-기준, in %p, next to the seed '
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
            p = TU / 'gt/scenes' / stem / 'distances' / f'{fam}.npz'
            if not p.exists():
                out.append(dict(site=site, plan=plan, status='결과 없음'))
                continue
            s = loadz(p, ['row_s'])['row_s']
            for part, mm in [('띠', m), ('띠 밖', ~m)]:
                if not mm.any():
                    out.append(dict(site=site, plan=plan, part=part, rows=0, status='참값 점 없음'))
                    continue
                v = tt.values(s[mm], tau[mm])
                fl = np.isfinite(s[mm]) & (s[mm] > tau[mm])
                out.append(dict(site=site, plan=plan, part=part, rows=int(mm.sum()), nearest_row_to_boundary_m=float(dist.min()),
                                completeness_pct=v['within_pct'], floating_pct=100. * float(fl.mean()), no_surface_pct=v['no_surface_pct'], status='있음'))
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
        return dict(plan=plan, unit=unit, run=name, status='결과 없음', train_images=n_train, iterations=iters, passes_per_image=iters / n_train)
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
    return dict(plan=plan, unit=unit, run=name, status=r['status'], attempts=len(r['attempts']), host_guard_stops=r.get('host_guard_stops', 0),
                hours=hours, stopped_attempt_hours=sum(a.get('seconds') or 0 for a in r['attempts'][:-1]) / 3600,
                last_iteration=t[-1]['iteration'] if t else None, final_gaussians=g[-1] if g else None, max_gaussians=max(g) if g else None,
                peak_reserved_GiB=peak, peak_rss_GiB=rss, train_images=n_train, iterations=iters, passes_per_image=iters / n_train,
                psnr_train_5views=ptr, psnr_test=pte, min_host_available_GiB=last.get('min_host_available_GiB'),
                count_rule_records=len([l for l in ov.read_text().splitlines() if l.strip()]) if ov.exists() else 0)


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
    ch = [c['hours'] for c in cells if c.get('hours')]
    out.append(dict(plan='다', unit='칸 넷 합', run='cellsef_ALS_s0', status='합' if len(ch) == 4 else '일부',
                    hours=sum(ch), hours_two_gpus=max(sum(ch) / 2, max(ch)) if ch else None,
                    max_gaussians=max(c.get('max_gaussians') or 0 for c in cells), peak_reserved_GiB=max(c.get('peak_reserved_GiB') or 0 for c in cells),
                    peak_rss_GiB=max(c.get('peak_rss_GiB') or 0 for c in cells)))
    write('add16_runs_ALS', out, 'addendum 16: per run (ALS, filter): status, GPU hours of the attempt that produced the result (cell 0 includes cell0ef to 15,000; stopped attempts apart), gaussians final/max, GPU reserved max, host RSS max, training images, passes per image, training PSNR (5 views) and test PSNR at the last iteration, minimum host MemAvailable, count-rule records; last row: 판 다 sums (two GPUs = max(sum/2, longest cell))')
    return out


def table():
    cfg()
    locked()
    summ = summary()
    comparisons(summ)
    band()
    runs()
    print('ADD16_TABLE_DONE', flush=True)


if __name__ == '__main__':
    dict(table=table)[sys.argv[1]](*sys.argv[2:])
