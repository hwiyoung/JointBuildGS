"""Tables of PHD-MAIN-TRAINUNIT-v1 with the unchanged GTJUDGE scorer (add2_scores.metric_rows, §3.4 accuracy rule).

  python tu_tables.py all
Writes docs/experiments/phd/main_trainunit_v1/tables/*.csv|json|md and /tu/tables.
"""
import csv
import re
import sys

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import common as gcommon
from tu_common import *

gcommon.O = TU / 'gt'
gcommon.C = Path('/repo/configs/phd/main_gtjudge_v1')
gcommon.D = TU / 'gt/docs'
import add2_scores  # noqa: E402  (binds O/C/D above)
from normal_line import values  # noqa: E402

GD = R / 'docs/experiments/phd/main_gtjudge_v1/tables/addendum2/stage1'
BASE = ['prior', 'mvs', 'fusion', 'baseline_30000', 'GeoGS_30000', '2DGS_30000', 'CDGS_30000']
CASES = [0, 1, 2, 4]
CASE_NAME = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음', 'all': '장면 전체'}
LABEL = {'FINALTRAIN_30000': '기준', 'seed1_s1': '씨앗 반복', 'campus30k': '가', 'cells': '다', 'campus120k': '나'}


def fams(prior):
    return dict(기준='FINALTRAIN_30000', 씨앗반복='seed1_s1', 가=f'campus30k_{prior}_s0', 다=f'cells_{prior}_s0', 나=f'campus120k_{prior}_s0')


def table(name, rows):
    out = D / 'tables' / name
    out.parent.mkdir(parents=True, exist_ok=True)
    dump(out.with_suffix('.json'), dict(rows=rows, scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    with out.with_suffix('.md').open('w') as f:
        f.write('| ' + ' | '.join(fields) + ' |\n| ' + ' | '.join('---' for _ in fields) + ' |\n')
        for r in rows:
            f.write('| ' + ' | '.join('' if r.get(k) is None else (f'{r[k]:.3f}' if isinstance(r.get(k), float) else str(r[k])) for k in fields) + ' |\n')


def metrics():
    allrows = []
    checks = []
    for site in SITES:
        for prior in PRIORS:
            stem = f'{site}__{prior}'
            have = [m for m in BASE + ['FINALTRAIN_30000'] + list(fams(prior).values())[1:]
                    if (TU / 'gt/scenes' / stem / 'distances' / f'{m}.npz').exists()]
            have = list(dict.fromkeys(have))
            rows = add2_scores.metric_rows(site, prior, have)
            allrows += rows
            # verification against the published GTJUDGE table (same function, same inputs)
            ref = {(r['method'], r['surface'], r['case_id']): r for r in csv.DictReader((GD / f'{stem}.csv').open())}
            bad = 0
            n = 0
            for r in rows:
                key = (r['method'], r['surface'], str(r['case_id']))
                if key in ref and r['method'] in BASE + ['FINALTRAIN_30000']:
                    n += 1
                    for k in ['completeness_pct', 'accuracy_pct']:
                        a, b = r[k], ref[key][k]
                        if (a is None) != (b in ['', 'None']) or (a is not None and abs(a - float(b)) > 1e-9):
                            bad += 1
            checks.append(dict(site=site, prior=prior, compared_rows=n, mismatches=bad))
            table(f'metrics_{stem}', rows)
    dump(D / 'tables/verify_baseline_rows.json', dict(at=now(), checks=checks, source=str(GD), scientific_verdict=None))
    return allrows


def summary(allrows):
    look = {(r['site'], r['prior'], r['method'], r['surface'], r['case_id']): r for r in allrows}
    out = []
    for site in SITES:
        for prior in PRIORS:
            for label, fam in fams(prior).items():
                if (site, prior, fam, 'all', 'all') not in look:
                    out.append(dict(site=site, prior=prior, run=label, method=fam, status='결과 없음'))
                    continue
                row = dict(site=site, prior=prior, run=label, method=fam, status='있음')
                for case in CASES + ['all']:
                    r = look[(site, prior, fam, 'all', case)]
                    row[f'완전성_{CASE_NAME[case]}'] = r['completeness_pct']
                    row[f'정확성_{CASE_NAME[case]}'] = r['accuracy_pct']
                    row[f'n_gt_{CASE_NAME[case]}'] = r['n_gt']
                for metric, key in [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]:
                    gaps = []
                    for case in CASES:
                        r = look[(site, prior, fam, 'all', case)]
                        if r['n_gt'] < 1000 or r[key] is None:
                            continue
                        best = max(v[key] for m in BASE + [fam] if (v := look.get((site, prior, m, 'all', case))) and v[key] is not None)
                        gaps.append((best - r[key], case))
                    g = max(gaps) if gaps else (None, None)
                    row[f'최대격차_{metric}_pp'] = g[0]
                    row[f'최대격차_{metric}_경우'] = CASE_NAME.get(g[1]) if g[1] is not None else None
                out.append(row)
    table('summary_runs', out)
    # comparison methods alongside (same four cases)
    comp = []
    for site in SITES:
        for prior in PRIORS:
            for m in BASE:
                if (site, prior, m, 'all', 'all') not in look:
                    continue
                row = dict(site=site, prior=prior, method=m)
                for case in CASES + ['all']:
                    r = look[(site, prior, m, 'all', case)]
                    row[f'완전성_{CASE_NAME[case]}'] = r['completeness_pct']
                    row[f'정확성_{CASE_NAME[case]}'] = r['accuracy_pct']
                comp.append(row)
    table('summary_comparison_methods', comp)
    return out


def comparisons(summ):
    s = {(r['site'], r['prior'], r['run']): r for r in summ}
    keys = [k for k in summ[0] if k.startswith('완전성_') or k.startswith('정확성_')] if summ else []
    keys = sorted(set(k for r in summ for k in r if k.startswith('완전성_') or k.startswith('정확성_') or k.startswith('최대격차_') and k.endswith('_pp')))
    pairs = [(1, '씨앗반복', '기준'), (2, '가', '나'), (3, '나', '다'), (4, '다', '기준')]
    out = []
    for site in SITES:
        for prior in PRIORS:
            for k in keys:
                row = dict(site=site, prior=prior, metric=k)
                b, sd = s.get((site, prior, '기준')), s.get((site, prior, '씨앗반복'))
                spread = abs(sd[k] - b[k]) if b and sd and b.get(k) is not None and sd.get(k) is not None else None
                row['흔들림폭_씨앗'] = spread
                for idx, a, c in pairs:
                    ra, rc = s.get((site, prior, a)), s.get((site, prior, c))
                    if ra and rc and ra.get(k) is not None and rc.get(k) is not None:
                        row[f'비교{idx}_{a}-{c}'] = ra[k] - rc[k]
                    else:
                        row[f'비교{idx}_{a}-{c}'] = None
                out.append(row)
    table('comparisons', out)


def band():
    cells = json.loads((TU / 'cells/cells.json').read_text())
    segs = cells['boundaries']
    out = []
    for site in SITES:
        for prior in PRIORS:
            stem = f'{site}__{prior}'
            row = loadz(TU / 'gt/scenes' / stem / 'rows.npz', ['xyz', 'row_tau_m', 'wall'])
            xy = row['xyz'][:, :2]
            d = np.full(len(xy), np.inf)
            for sg in segs:
                lo, hi = np.array(sg['lo']), np.array(sg['hi'])
                cl = np.clip(xy, lo, hi)
                d = np.minimum(d, np.linalg.norm(xy - cl, axis=1))
            m = d <= 2.
            out.append(dict(site=site, prior=prior, run='(참값 점)', part='경계까지 가장 가까운 참값 점', rows=int(len(d)), nearest_reference_row_to_boundary_m=float(d.min()),
                            rows_within_2m=int(m.sum()), rows_within_5m=int((d <= 5).sum()), status='기록'))
            for label, fam in fams(prior).items():
                p = TU / 'gt/scenes' / stem / 'distances' / f'{fam}.npz'
                if not p.exists():
                    out.append(dict(site=site, prior=prior, run=label, band_rows=int(m.sum()), status='결과 없음'))
                    continue
                s = loadz(p, ['row_s'])['row_s']
                tau = row['row_tau_m']
                for part, mm in [('띠', m), ('띠 밖', ~m)]:
                    v = values(s[mm], tau[mm])
                    fl = np.isfinite(s[mm]) & (s[mm] > tau[mm])
                    out.append(dict(site=site, prior=prior, run=label, part=part, rows=int(mm.sum()), completeness_pct=v['within_pct'],
                                    floating_pct=100. * float(fl.mean()) if mm.any() else None, no_surface_pct=v['no_surface_pct'], status='있음'))
    table('cells_boundary_band', out)


def run_stats():
    out = []
    def stats(name, model, iters, n_train):
        tr = model / 'jbgs_trace.jsonl'
        rows = [json.loads(l) for l in tr.read_text().splitlines() if l.strip()] if tr.exists() else []
        log = (model.parent / 'train.log')
        psnr_train = psnr_test = None
        if log.exists():
            txt = log.read_bytes().decode('utf-8', 'replace').replace('\r', '\n')
            for line in txt.splitlines():
                mm = re.search(r'\[ITER (\d+)\] Evaluating (train|test): L1 ([0-9.eE+-]+) PSNR ([0-9.eE+-]+)', line)
                if mm and int(mm.group(1)) == iters:
                    if mm.group(2) == 'train':
                        psnr_train = float(mm.group(4))
                    else:
                        psnr_test = float(mm.group(4))
        mt = model / f'metrics_{iters:05d}.txt'
        if psnr_test is None and mt.exists():
            mm = re.search(r'PSNR: ([0-9.]+)', mt.read_text())
            psnr_test = float(mm.group(1)) if mm else None
        g = [r['gaussians'] for r in rows]
        mon = model / 'target_monitor/curve.jsonl'
        if mon.exists():
            cg = [json.loads(l)['gaussians'] for l in mon.read_text().splitlines() if l.strip()]
            g = g + cg
        return dict(run=name, last_iteration=rows[-1]['iteration'] if rows else None, final_gaussians=g[-1] if g else None, max_gaussians=max(g) if g else None,
                    peak_reserved_GiB=max(r['peak_cuda_reserved_bytes'] for r in rows) / 2**30 if rows else None,
                    train_seconds=rows[-1]['elapsed_seconds'] if rows else None, iterations=iters, train_images=n_train,
                    iterations_per_image=iters / n_train if n_train else None, psnr_train_5views=psnr_train, psnr_test=psnr_test)
    for site in SITES:
        n = len(json.loads((S0 / 'fork_inputs/s61' / site / 'split.json').read_text())['train'])
        for prior in PRIORS:
            out.append(dict(unit=site, prior=prior, label='기준', **stats(f'FINALTRAIN ft_{prior}_s0', FT / 'runs' / site / f'ft_{prior}_s0/attempt1/model', 30000, n)))
            rec = TU / 'runs' / site / f'seed1_{prior}' / 'receipt.json'
            if rec.exists():
                r = json.loads(rec.read_text())
                if r['attempts']:
                    a = r['attempts'][-1]['attempt']
                    out.append(dict(unit=site, prior=prior, label='씨앗 반복', status=r['status'], **stats(f'seed1_{site}_{prior}', rec.parent / f'attempt{a}/model', 30000, n)))
    split = json.loads((TU / 'scenes/campus/split.json').read_text())
    def add(unit, prior, label, name, rec, n):
        if not rec.exists():
            return
        r = json.loads(rec.read_text())
        if not r['attempts']:
            out.append(dict(unit=unit, prior=prior, label=label, status=r['status'], reason=r.get('reason'), run=name, train_images=n,
                            iterations_per_image=30000 / n))
            return
        for att in r['attempts']:
            a = att['attempt']
            row = dict(unit=unit, prior=prior, label=label, status=r['status'], attempt=a, attempt_status=att['status'], exit_code=att.get('exit_code'),
                       **stats(name, rec.parent / f'attempt{a}/model', 30000, n))
            dl = rec.parent / f'attempt{a}' / 'DEADLINE_STOP.json'
            if dl.exists():
                row['stopped_at_iteration'] = json.loads(dl.read_text())['iteration']
            mon = rec.parent / f'attempt{a}' / 'model/target_monitor'
            if (mon / 'STOP.json').exists():
                s = json.loads((mon / 'STOP.json').read_text())
                row.update(health_stop_reason=s.get('reason'), health_stop_iteration=s.get('iteration'), health_stop_gaussians=s.get('gaussians'),
                           health_stop_count_at_6000=s.get('count_at_6000'))
            if (mon / 'health_override.jsonl').exists():
                ov = [json.loads(l) for l in (mon / 'health_override.jsonl').read_text().splitlines() if l.strip()]
                row['health_override_iterations'] = [o['iteration'] for o in ov]  # addendum 4: count rule recorded, not enforced
            ckpt = att.get('resume_from')
            row['resume_iteration'] = int(ckpt.split('iteration_')[1].split('/')[0]) if ckpt else None
            row['attempt_seconds'] = att.get('seconds')
            out.append(row)
        if len(r['attempts']) > 1:
            # chained attempts (stop -> resume): one total row per unit; time = sum of attempt wall time (includes map loading)
            last = r['attempts'][-1]['attempt']
            tot = dict(unit=unit, prior=prior, label=label, status=r['status'], attempt='합계', run=name, train_images=n, iterations=30000,
                       iterations_per_image=30000 / n, attempts=len(r['attempts']),
                       wall_seconds_sum=sum(a.get('seconds') or 0 for a in r['attempts']),
                       **{k: v for k, v in stats(name, rec.parent / f'attempt{last}/model', 30000, n).items()
                          if k in ('last_iteration', 'final_gaussians', 'psnr_train_5views', 'psnr_test')})
            out.append(tot)
    for prior in PRIORS:
        add('campus', prior, '가', f'campus30k_{prior}_s0', TU / 'runs/campus' / f'campus30k_{prior}_s0' / 'receipt.json', len(split['train']))
        cells = json.loads((TU / 'cells/cells.json').read_text())['cells'] if (TU / 'cells/cells.json').exists() else []
        for c in cells:
            add(f'cell{c["id"]}', prior, '다', f'cells_{prior}_s0/cell{c["id"]}', TU / 'runs/cells' / f'cells_{prior}_s0' / f'cell{c["id"]}' / 'receipt.json', len(c['images']))
    table('run_stats', out)


if __name__ == '__main__':
    cfg()
    rows = metrics()
    summ = summary(rows)
    comparisons(summ)
    band()
    run_stats()
    print('TABLES_DONE', flush=True)
