"""PHD-MAIN-TRAINUNIT-v2 order 5.1 tables (run2_cpu.sh). Unchanged scorer: add2_scores.metric_rows (section 3.4 accuracy rule)
through tu_tables (GTJUDGE common bound to /tu/gt = the v2 mirror, which links the v1 scores of finished runs).
Writes whatever exists; a missing plan is written as '결과 없음'.

  python tu2_tables.py all   -> tables/v2_scores.*, v2_compare_ALS.*, v2_compare_LoD2.*, v2_band.*, v2_runs.*
"""
import re
import sys

import tu_tables as tt
from tu_common import *
from tu2_stop import write

TU1 = Path('/tu1')
SKIP9 = json.loads((Path(__file__).resolve().parents[3] / 'configs/phd/main_trainunit_v1/trainunit_v2_skip.json').read_text())['skip_cells9']
CASES = [0, 1, 2, 4]
NAME = {0: '둘 다 맞음', 1: '영상만 맞음', 2: '사전 정보만 맞음', 4: '영상 없음', 'all': '장면 전체'}
MET = [('완전성', 'completeness_pct'), ('정확성', 'accuracy_pct')]
# 필터없음 = existing building-unit runs without the elongation filter (seed 0 FINALTRAIN_30000, seed 1 v1 seed1_s1); user decision
# 2026-11-17: no new LoD2 building-unit runs, the no-filter runs are the LoD2 reference; ALS shows filter vs no filter at building scale
PLANS = {'ALS': {'건물단위_s0': 'ef_s0', '건물단위_s1': 'ef_s1', '전체': 'campusef30k_ALS_s0', '넷': 'cellsef_ALS_s0', '아홉': 'cells9ef_ALS_s0',
                 '건물단위_s0_필터없음': 'FINALTRAIN_30000', '건물단위_s1_필터없음': 'seed1_s1'},
         'LoD2': {'건물단위_s0_필터없음': 'FINALTRAIN_30000', '건물단위_s1_필터없음': 'seed1_s1'}}
SHORT = dict(B0_b10='B0', R1rep_b10='R1rep', B173nb_b10='B173nb')


def scores():
    out = []
    for prior, plans in PLANS.items():
        for site in SITES:
            stem = f'{site}__{prior}'
            have = [f for f in plans.values() if (TU / 'gt/scenes' / stem / 'distances' / f'{f}.npz').exists()]
            look = {(r['method'], r['surface'], r['case_id']): r for r in tt.add2_scores.metric_rows(site, prior, have)} if have else {}
            for plan, fam in plans.items():
                if (fam, 'all', 'all') not in look:
                    out.append(dict(prior=prior, site=site, plan=plan, family=fam, status='결과 없음'))
                    continue
                row = dict(prior=prior, site=site, plan=plan, family=fam, status='있음')
                for case in CASES + ['all']:
                    r = look[(fam, 'all', case)]
                    for m, k in MET:
                        row[f'{m}_{NAME[case]}'] = r[k]
                    row[f'n_gt_{NAME[case]}'] = r['n_gt']
                out.append(row)
    write('v2_scores', out, 'order v2 5.1: plan x prior x site: completeness and accuracy (section 3.4 rule) of the four cases and the scene, n_gt per case; unchanged scorer')
    return out


def compare(sc):
    s = {(r['prior'], r['site'], r['plan']): r for r in sc if r['status'] == '있음'}
    keys = [f'{m}_{NAME[c]}' for c in CASES + ['all'] for m, _ in MET]
    for prior, plans in PLANS.items():
        out = []
        for site in SITES:
            for k in keys:
                case = k.split('_', 1)[1]
                base = '건물단위_s0' if '건물단위_s0' in plans else '건물단위_s0_필터없음'
                b0, b1 = s.get((prior, site, base)), s.get((prior, site, base.replace('s0', 's1')))
                row = dict(site=site, metric=k, n_gt=(b0 or {}).get(f'n_gt_{case}'))
                for plan in plans:
                    row[plan] = (s.get((prior, site, plan)) or {}).get(k)
                row['씨앗차_s1-s0_pp'] = b1[k] - b0[k] if b0 and b1 and b0.get(k) is not None and b1.get(k) is not None else None
                for plan in plans:
                    if plan.startswith('건물단위'):
                        continue
                    row[f'{plan}-건물단위_s0_pp'] = row[plan] - row['건물단위_s0'] if row.get(plan) is not None and row.get('건물단위_s0') is not None else None
                for sd in ['s0', 's1']:
                    a, b = row.get(f'건물단위_{sd}'), row.get(f'건물단위_{sd}_필터없음')
                    if f'건물단위_{sd}' in plans:
                        row[f'필터있음-필터없음_{sd}_pp'] = a - b if a is not None and b is not None else None
                out.append(row)
        write(f'v2_compare_{prior}', out, f'order v2 5.1: {prior}: plans side by side per site and metric (%), seed difference of the building unit (s1 - s0; LoD2: the no-filter runs) and plan minus building unit s0 (%p); ALS: filter minus no filter per seed (%p); 필터없음 = existing runs without the elongation filter (LoD2 reference, user decision 2026-11-17); n_gt of the case; no selection or reading')


def band():
    out = []
    for plan, fam, cj in [('넷', 'cellsef_ALS_s0', TU1 / 'cells/cells.json'), ('아홉', 'cells9ef_ALS_s0', TU / 'cells/cells.json')]:
        segs = json.loads(cj.read_text())['boundaries']
        for site in SITES:
            stem = f'{site}__ALS'
            row = loadz(TU / 'gt/scenes' / stem / 'rows.npz', ['xyz', 'row_tau_m'])
            xy = row['xyz'][:, :2]
            dist = np.full(len(xy), np.inf)
            for sg in segs:
                lo, hi = np.array(sg['lo']), np.array(sg['hi'])
                dist = np.minimum(dist, np.linalg.norm(xy - np.clip(xy, lo, hi), axis=1))
            m = dist <= 2.
            p = TU / 'gt/scenes' / stem / 'distances' / f'{fam}.npz'
            if not p.exists():
                out.append(dict(plan=plan, site=site, status='결과 없음'))
                continue
            s = loadz(p, ['row_s'])['row_s']
            tau = row['row_tau_m']
            for part, mm in [('띠(경계 2 m 안)', m), ('띠 밖', ~m)]:
                if not mm.any():
                    out.append(dict(plan=plan, site=site, part=part, rows=0, status='없음'))
                    continue
                v = tt.values(s[mm], tau[mm])
                fl = np.isfinite(s[mm]) & (s[mm] > tau[mm])
                out.append(dict(plan=plan, site=site, part=part, rows=int(mm.sum()), completeness_pct=v['within_pct'], floating_pct=100. * float(fl.mean()),
                                no_surface_pct=v['no_surface_pct'], status='있음'))
    write('v2_band', out, 'order v2 3.4 / 5.1: reference rows within 2 m (xy) of an original cell boundary of the plan, and the rest: completeness, floating share (s > tau), no-surface share (tu_tables.band rule); 넷 = v1 cells.json, 아홉 = v2 cells.json')


def psnr(att, iters=30000):
    out = {}
    log = att / 'train.log'
    if log.exists():
        txt = log.read_bytes().decode('utf-8', 'replace').replace('\r', '\n')
        for mm in re.finditer(r'\[ITER (\d+)\] Evaluating (train|test): L1 ([0-9.eE+-]+) PSNR ([0-9.eE+-]+)', txt):
            if int(mm.group(1)) == iters:
                out[mm.group(2)] = float(mm.group(4))
    return out.get('train'), out.get('test')


def run_row(plan, prior, name, run, n_train, first=None):
    rec = run / 'receipt.json'
    if not rec.exists():
        return dict(plan=plan, prior=prior, run=name, status='결과 없음', train_images=n_train)
    r = json.loads(rec.read_text())
    last = r['attempts'][-1]
    att = run / f'attempt{last["attempt"]}'
    t = [json.loads(l) for l in (att / 'model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()] if (att / 'model/jbgs_trace.jsonl').exists() else []
    hours = (last.get('seconds') or 0) / 3600
    g = [x['gaussians'] for x in t]
    gpu = max([x['peak_cuda_reserved_bytes'] for x in t] or [0]) / 2 ** 30
    rss = max([x.get('peak_rss_bytes', 0) for x in t] or [0]) / 2 ** 30
    if first is not None:
        ff = json.loads((first / 'receipt.json').read_text())
        t0 = [json.loads(l) for l in (first / 'attempt1/model/jbgs_trace.jsonl').read_text().splitlines() if l.strip()]
        hours += ff['attempts'][0]['seconds'] / 3600
        g = [x['gaussians'] for x in t0] + g
        gpu = max(gpu, max(x['peak_cuda_reserved_bytes'] for x in t0) / 2 ** 30)
        rss = max(rss, max(x.get('peak_rss_bytes', 0) for x in t0) / 2 ** 30)
    # seconds per iteration, 100 -> 500 of the first attempt that started from 0 (0-100 includes loading)
    sp = None
    for a in r['attempts']:
        ta = run / f'attempt{a["attempt"]}' / 'model/jbgs_trace.jsonl'
        if not ta.exists():
            continue
        tt_ = {x['iteration']: x['elapsed_seconds'] for x in (json.loads(l) for l in ta.read_text().splitlines() if l.strip())}
        if 100 in tt_ and 500 in tt_:
            sp = (tt_[500] - tt_[100]) / 400
            break
    ptr, pte = psnr(att)
    return dict(plan=plan, prior=prior, run=name, status=r['status'], attempts=len(r['attempts']), hours_result=hours,
                hours_all_attempts=sum(a.get('seconds') or 0 for a in r['attempts']) / 3600 + (hours - (last.get('seconds') or 0) / 3600),
                final_gaussians=g[-1] if g else None, max_gaussians=max(g) if g else None, peak_gpu_reserved_GiB=gpu, peak_host_rss_GiB=rss,
                sec_per_iter_100_500=sp, psnr_train=ptr, psnr_test=pte, train_images=n_train)


def runs():
    out = []
    for prior in ['ALS', 'LoD2']:
        for site, short in SHORT.items():
            n = len(json.loads((S0 / 'fork_inputs/s61' / site / 'split.json').read_text())['train'])
            for seed in [0, 1]:
                if prior == 'LoD2':
                    out.append(dict(plan=f'건물단위_s{seed}', prior=prior, run=f'{short}ef_{prior}_s{seed}', train_images=n,
                                    status='결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1)'))
                    continue
                run = TU1 / 'runs/ef' / f'{short}ef_{prior}_s{seed}'
                out.append(run_row(f'건물단위_s{seed}', prior, f'{short}ef_{prior}_s{seed}', run, n))
    # existing building-unit runs without the elongation filter (LoD2 reference by user decision 2026-11-17; ALS for the filter contrast)
    for prior in ['ALS', 'LoD2']:
        for site, short in SHORT.items():
            n = len(json.loads((S0 / 'fork_inputs/s61' / site / 'split.json').read_text())['train'])
            out.append(run_row('건물단위_s0_필터없음', prior, f'FINALTRAIN {site} ft_{prior}_s0', FT / 'runs' / site / f'ft_{prior}_s0', n))
            out.append(run_row('건물단위_s1_필터없음', prior, f'v1 {site} seed1_{prior}', TU1 / 'runs' / site / f'seed1_{prior}', n))
    out.append(run_row('전체', 'ALS', 'campusef30k_ALS_s0', TU1 / 'runs/ef/campusef30k_ALS_s0', 819))
    for k in range(4):
        n = len(json.loads((TU1 / f'scenes/cell{k}/split.json').read_text())['train'])
        out.append(run_row('넷', 'ALS', f'cellsef_ALS_s0_cell{k}', TU1 / f'runs/ef/cellsef_ALS_s0_cell{k}', n, first=TU1 / 'runs/ef/cell0ef_ALS_s0' if k == 0 else None))
    for k in range(9):
        p = TU / f'scenes/cell{k}/split.json'
        n = len(json.loads(p.read_text())['train']) if p.exists() else None
        if k in SKIP9:
            out.append(dict(plan='아홉', prior='ALS', run=f'cells9ef_ALS_s0_cell{k}', status='결과 없음(학습 안 함: 평가 상자 밖, 사용자 결정 2026-11-17)', train_images=n))
            continue
        out.append(run_row('아홉', 'ALS', f'cells9ef_ALS_s0_cell{k}', TU / f'runs/cells9ef_ALS_s0_cell{k}', n))
    for plan in ['넷', '아홉']:
        cs = [r for r in out if r['plan'] == plan and r.get('hours_result')]
        if cs:
            out.append(dict(plan=plan, prior='ALS', run=f'칸 {len(cs)}개 합' + (' (칸 3·0·2 학습 안 함)' if plan == '아홉' else ''), status='합', hours_result=sum(r['hours_result'] for r in cs),
                            max_gaussians=max(r['max_gaussians'] or 0 for r in cs), peak_gpu_reserved_GiB=max(r['peak_gpu_reserved_GiB'] for r in cs),
                            peak_host_rss_GiB=max(r['peak_host_rss_GiB'] for r in cs)))
    write('v2_runs', out, 'order v2 5.1: per run: status, hours of the attempt with the result (넷 cell 0 includes cell0ef to 15,000) and of all attempts, gaussians final/max, GPU reserved max, host RSS max, s/iteration 100->500 of the first attempt from 0, PSNR train (5 views) / test at 30,000; 필터없음 rows = existing runs without the elongation filter (FINALTRAIN ft_<prior>_s0, v1 seed1_<prior>)')


def all_():
    sc = scores()
    compare(sc)
    band()
    runs()
    print('TABLES', len(sc), flush=True)


if __name__ == '__main__':
    dict(all=all_, scores=scores, band=band, runs=runs)[sys.argv[1]](*sys.argv[2:])
