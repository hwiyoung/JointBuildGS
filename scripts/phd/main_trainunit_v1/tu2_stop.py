"""PHD-MAIN-TRAINUNIT-v2 order 3.5 / 2.1 no. 4-5: stop-cause records from what the runs left (no training).
Run with run2_cpu.sh (/tu = v2 payload, /tu1 = v1 payload read-only, docs = docs/.../v2).

  python tu2_stop.py trace     -> tables/stop_trace_{rows123,densify,elong,memory_limits,config_diff,radius}.*, figures/stop_trend_<group>.png|json
  python tu2_stop.py elong <group>   -> elongation of saved files (point_cloud.ply / jbgs_complete checkpoints) of one group, figure

Row sources: jbgs_trace.jsonl (every 100: gaussians, peak CUDA, peak RSS), family_monitor.jsonl (each densification: count before/after,
rows with elongation <= 0.01), trace1000.jsonl (v2 runs: current RSS/cgroup/CUDA, elongation < 0.01 / < 0.1), command.json, launch.json,
receipt.json, extent_override.json, saved point_cloud.ply and checkpoints (elongation min(scale)/max(scale)).
"""
import csv
import difflib
import glob
import sys

from tu_common import *

TU1 = Path('/tu1')
V1 = TU1 / 'runs'
# group -> (stopped run dir, nearest finished run dir(s)); 'first' = cell0ef (first 15,000 of cellsef cell 0)
GROUPS = {
    'campus30k_ALS_s0': dict(stopped=V1 / 'campus/campus30k_ALS_s0', finished=[V1 / 'ef/campusef30k_ALS_s0']),
    'cells_ALS_s0_cell0': dict(stopped=V1 / 'cells/cells_ALS_s0/cell0', finished=[V1 / 'ef/cell0ef_ALS_s0', V1 / 'ef/cellsef_ALS_s0_cell0']),
    'cells_ALS_s0_cell1': dict(stopped=V1 / 'cells/cells_ALS_s0/cell1', finished=[V1 / 'ef/cellsef_ALS_s0_cell1']),
    'cells_ALS_s0_cell2': dict(stopped=V1 / 'cells/cells_ALS_s0/cell2', finished=[V1 / 'ef/cellsef_ALS_s0_cell2']),
    'cells_ALS_s0_cell3': dict(stopped=V1 / 'cells/cells_ALS_s0/cell3', finished=[V1 / 'ef/cellsef_ALS_s0_cell3']),
    'cellsef_ALS_s0_cell1fix': dict(stopped=V1 / 'ef/cellsef_ALS_s0_cell1fix', finished=[V1 / 'ef/cellsef_ALS_s0_cell1']),
}
GiB = 2 ** 30


def plt_ko():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 9})
    return plt


def write(name, rows, note):
    out = D / 'tables' / name
    out.parent.mkdir(parents=True, exist_ok=True)
    dump(out.with_suffix('.json'), dict(note=note, rows=rows, scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    enc = lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
    with out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows([{k: enc(v) for k, v in r.items()} for r in rows])
    fmt = lambda v: '' if v is None else (f'{v:.4g}' if isinstance(v, float) else str(enc(v)))
    with out.with_suffix('.md').open('w') as f:
        f.write(f'{note}\n\n| ' + ' | '.join(fields) + ' |\n| ' + ' | '.join('---' for _ in fields) + ' |\n')
        for r in rows:
            f.write('| ' + ' | '.join(fmt(r.get(k)) for k in fields) + ' |\n')


def jl(p):
    p = Path(p)
    if not p.exists():
        return []
    out = []
    for l in p.read_text().splitlines():
        if l.strip():
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                pass
    return out


def attempts(run):
    """(label, attempt dir, receipt) of a run dir: attempt<k> folders, receipts from the run receipt when missing."""
    run = Path(run)
    rr = json.loads((run / 'receipt.json').read_text()) if (run / 'receipt.json').exists() else {}
    byk = {a['attempt']: a for a in rr.get('attempts', [])}
    out = []
    for a in sorted(run.glob('attempt*'), key=lambda p: int(p.name[7:]) if p.name[7:].isdigit() else 0):
        if not a.name[7:].isdigit():
            continue
        k = int(a.name[7:])
        rec = json.loads((a / 'receipt.json').read_text()) if (a / 'receipt.json').exists() else byk.get(k, {})
        out.append((f'{run.name}/a{k}', a, rec))
    return out


def final_attempt(run):
    a = attempts(run)
    rr = json.loads((Path(run) / 'receipt.json').read_text())
    if rr.get('attempts'):
        k = rr['attempts'][-1]['attempt']
        return [x for x in a if x[1].name == f'attempt{k}'][0]
    return a[-1]


def rows123(label, att, rec, role):
    t = jl(att / 'model/jbgs_trace.jsonl')
    fm = jl(att / 'family_monitor.jsonl')
    t1k = jl(att / 'trace1000.jsonl')
    needle = {r['iteration']: r['needle_total'] / r['n_before'] for r in fm if r.get('n_before')}
    k1 = {r['iteration']: r for r in t1k if 'gaussians' in r}
    rows = []
    for r in t:
        it = r['iteration']
        if it % 1000 and r is not t[-1]:
            continue
        near = [i for i in needle if i <= it]
        x = k1.get(it, {})
        rows.append(dict(run=label, role=role, iteration=it, gaussians=r['gaussians'],
                         needle_le_001_share_at_last_densify=needle[max(near)] if near else None, last_densify_iteration=max(near) if near else None,
                         elong_lt_001=x.get('elong_lt_001'), elong_lt_01=x.get('elong_lt_01'),
                         rss_now_GiB=x['rss_bytes'] / GiB if x.get('rss_bytes') else None, cgroup_now_GiB=x['cgroup_current_bytes'] / GiB if x.get('cgroup_current_bytes') else None,
                         cuda_alloc_now_GiB=x['cuda_allocated_bytes'] / GiB if x.get('cuda_allocated_bytes') is not None else None,
                         peak_rss_GiB=r.get('peak_rss_bytes', 0) / GiB, peak_cuda_reserved_GiB=r['peak_cuda_reserved_bytes'] / GiB,
                         elapsed_s=r['elapsed_seconds'], last_row=r is t[-1], status=rec.get('status')))
    dens = [dict(run=label, role=role, iteration=r['iteration'], n_before=r['n_before'], n_after=r['n_after'], added=r['n_after'] - r['n_before'],
                 clone=r['clone_total'], split=r['split_total'], needle_le_001=r['needle_total'], filter_excluded=r['filter_excluded_total'],
                 extent=r['extent'], clone_scale_threshold=r['clone_scale_threshold']) for r in fm]
    if not fm and t:   # no monitor (pre-filter runs): change of the count between trace rows (every 100 = densification interval)
        dens = [dict(run=label, role=role, iteration=b['iteration'], n_before=a['gaussians'], n_after=b['gaussians'], added=b['gaussians'] - a['gaussians'],
                     source='jbgs_trace difference (no family monitor)') for a, b in zip(t, t[1:]) if b['iteration'] <= 15000]
    return rows, dens, t


def stage_of_growth(t):
    """Row 4: where the recorded peak RSS rose (trace every 100): before the first row (loading), at save/eval iterations, elsewhere."""
    if not t:
        return None
    ev = {7000, 15000, 30000}
    first = t[0].get('peak_rss_bytes', 0)
    at_ev, other = 0, 0
    steps = []
    for a, b in zip(t, t[1:]):
        d = b.get('peak_rss_bytes', 0) - a.get('peak_rss_bytes', 0)
        if d <= 0:
            continue
        if any(a['iteration'] < e <= b['iteration'] for e in ev):
            at_ev += d
        else:
            other += d
        if d > .25 * GiB:
            steps.append([a['iteration'], b['iteration'], round(d / GiB, 2)])
    last = t[-1].get('peak_rss_bytes', 0)
    return dict(rss_at_first_row_GiB=first / GiB, first_row_iteration=t[0]['iteration'], rss_last_GiB=last / GiB,
                rise_across_save_eval_GiB=at_ev / GiB, rise_elsewhere_GiB=other / GiB, steps_over_025GiB=steps[:20])


def cmd_of(att):
    p = att / 'command.json'
    return json.loads(p.read_text()) if p.exists() else None


def memory_limit(cmd):
    if not cmd or '--memory' not in cmd:
        return None
    return cmd[cmd.index('--memory') + 1]


def norm_cmd(cmd):
    """Command lines with the run/attempt names masked so that only setting differences remain."""
    out = []
    for x in cmd:
        x = str(x)
        for a in ['attempt1', 'attempt2', 'attempt3', 'attempt4']:
            x = x.replace(a, 'attemptN')
        out.append(x)
    return out


def data_load(att, prior_dir_guess=None):
    """Row 5: images (float32 3 x H x W on the CPU, --data_device cpu) and pinned target maps (jbgs_target.py: depth, sigma, weight, owner)."""
    cmd = cmd_of(att) or []
    scene = cmd[cmd.index('-s') + 1] if '-s' in cmd else None
    tdir = cmd[cmd.index('--jbgs_target_dir') + 1] if '--jbgs_target_dir' in cmd else None
    split = next((e.split('=', 1)[1] for e in cmd if isinstance(e, str) and e.startswith('JBGS_SPLIT_JSON=')), None)
    def host(p):
        if p is None:
            return None
        for a, b in [('/tu/', '/tu1/'), ('/p/', str(S0) + '/'), ('/ft/', str(FT) + '/')]:
            if p.startswith(a):
                return Path(b + p[len(a):])
        return Path(p)
    sp = host(split)
    sj = json.loads(sp.read_text()) if sp and sp.exists() else {}
    ntr, nte = len(sj.get('train', [])), len(sj.get('test', []))
    td = host(tdir)
    owner_bytes, map_bytes = None, None
    if td and (td / 'maps/index.json').exists():
        idx = json.loads((td / 'maps/index.json').read_text())
        f = td / 'maps' / next(iter(idx['views'].values()))['file']
        with np.load(f) as z:
            map_bytes = sum(z[k].nbytes for k in ['depth', 'sigma', 'weight', 'owner'])
            owner_bytes = z['owner'].dtype.itemsize
    img = 3 * GRID_H * GRID_W * 4
    return dict(train_images=ntr, test_images=nte, resolution=f'{GRID_W}x{GRID_H}', image_bytes_each=img, owner_itemsize=owner_bytes,
                map_bytes_each=map_bytes, images_all_GiB=(ntr + nte) * img / GiB, pinned_maps_GiB=ntr * map_bytes / GiB if map_bytes else None,
                loading='all training+test images loaded once to CPU float32 (--data_device cpu, scene/cameras.py:39); all training-view target maps loaded once and pinned (jbgs_target.py:96-100)')


def radius_of(att):
    p = att / 'extent_override.json'
    if p.exists():
        e = json.loads(p.read_text())
        return dict(source='extent_override.json', fork_radius_m=e['fork_radius'], used_radius_m=e['used_radius'], fixed=e['fixed'])
    fm = jl(att / 'family_monitor.jsonl')
    if fm:
        return dict(source='family_monitor extent', used_radius_m=fm[0]['extent'])
    return None


def trace():
    allrows, alldens, stage, mem, diffs, rad, loads = [], [], [], [], [], [], []
    groups = dict(GROUPS)
    # v2 runs (finished or not) appear with their own attempts; their nearest finished run for the 2 x 2 / building unit
    for run in sorted((TU / 'runs').glob('*')):
        if run.name.startswith(('cells9ef', 'B0ef', 'R1repef', 'B173nbef')) and list(run.glob('attempt*')):
            groups[run.name] = dict(stopped=run, finished=[], v2=True)
    for g, spec in groups.items():
        series = []
        for label, att, rec in attempts(spec['stopped']):
            r, d, t = rows123(label, att, rec, 'v2' if spec.get('v2') else 'stopped')
            allrows += r; alldens += d
            series.append((label, 'stopped' if rec.get('status') != 'TRAINING_COMPLETE' else 'finished', r))
            s = stage_of_growth(t) or {}
            last = t[-1] if t else {}
            stage.append(dict(group=g, run=label, status=rec.get('status'), exit_code=rec.get('exit_code'), last_iteration=last.get('iteration'),
                              gaussians_at_stop=last.get('gaussians'), peak_rss_at_stop_GiB=last.get('peak_rss_bytes', 0) / GiB if last else None,
                              peak_cuda_reserved_at_stop_GiB=last.get('peak_cuda_reserved_bytes', 0) / GiB if last else None,
                              host_available_at_guard_GiB=(rec.get('host_guard') or {}).get('available_GiB'),
                              min_host_available_GiB=rec.get('min_host_available_GiB'), error=((rec.get('error') or {}).get('error') or '')[:200], **s))
            loads.append(dict(group=g, run=label, **data_load(att)))
            rad.append(dict(group=g, run=label, role='stopped' if spec.get('stopped') else '', **(radius_of(att) or dict(source='없음'))))
        for fin in spec['finished']:
            label, att, rec = final_attempt(fin)
            r, d, t = rows123(label, att, rec, 'finished')
            allrows += r; alldens += d
            series.append((label, 'finished', r))
            rad.append(dict(group=g, run=label, role='finished', **(radius_of(att) or dict(source='없음'))))
        if spec['finished'] and attempts(spec['stopped']):
            fl, fa, _ = final_attempt(spec['finished'][-1])
            fc = cmd_of(fa)
            for label, att, rec in attempts(spec['stopped']):
                c = cmd_of(att)
                if not c or not fc:
                    diffs.append(dict(group=g, run=label, nearest=fl, differences='command.json 없음'))
                    continue
                dl = [x for x in difflib.unified_diff(norm_cmd(fc), norm_cmd(c), lineterm='', n=0) if not x.startswith(('---', '+++', '@@'))]
                diffs.append(dict(group=g, run=label, nearest=fl, differences=dl))
        fig_trend(g, series)
    # memory limits and maxima of every run of v1 and v2 (order 2.1 no. 4)
    for rp in sorted(list(V1.glob('**/attempt*/command.json')) + list((TU / 'runs').glob('*/attempt*/command.json'))):
        att = rp.parent
        rec = json.loads((att / 'receipt.json').read_text()) if (att / 'receipt.json').exists() else {}
        t = jl(att / 'model/jbgs_trace.jsonl')
        k1 = jl(att / 'trace1000.jsonl')
        base = TU / 'runs' if str(att).startswith('/tu/') else V1
        mem.append(dict(run=str(att.relative_to(base)), payload='v2' if str(att).startswith('/tu/') else 'v1',
                        container_memory_limit=memory_limit(cmd_of(att)), peak_rss_GiB=max([x.get('peak_rss_bytes', 0) for x in t] or [0]) / GiB if t else None,
                        cgroup_peak_GiB=max([x.get('cgroup_peak_bytes') or 0 for x in k1] or [0]) / GiB if k1 else None,
                        status=rec.get('status'), last_iteration=t[-1]['iteration'] if t else None))
    write('stop_trace_rows123', allrows, 'order v2 3.5 rows 1-3 every 1,000 iterations (and the last row): gaussians; share of rows with elongation <= 0.01 at the last densification (family monitor, filter runs only; pre-filter runs have no monitor); v2 runs: elongation < 0.01 / < 0.1 and current RSS / cgroup / CUDA (trace1000); peak RSS and peak CUDA reserved (jbgs_trace, running maxima)')
    write('stop_trace_densify', alldens, 'order v2 3.5 row 1: gaussians added at each densification (family monitor) or, without monitor, change of the count between trace rows every 100 iterations (= densification interval)')
    write('stop_trace_stage', stage, 'order v2 3.5 rows 3-4: values at the stop; where the recorded peak RSS rose: before the first trace row (loading of images and maps), across the save/eval iterations 7,000/15,000/30,000, elsewhere (training and densification steps; trace every 100 cannot separate them)')
    write('stop_trace_dataload', loads, 'order v2 3.5 row 5: images and target maps loaded once (sizes from the split and one map file)')
    write('stop_trace_config_diff', diffs, 'order v2 3.5 row 6: command.json of the stopped attempt against the final attempt of the nearest finished run, line by line (run and attempt names masked); entry-level differences are in the report')
    write('stop_trace_radius', rad, 'order v2 3.5 row 7: scene radius used (fork getNerfppNorm or fixed); clone/split threshold = 0.01 r, big-Gaussian prune = 0.1 r')
    write('memory_limits', mem, 'order v2 2.1 no. 4: every attempt of v1 and v2: container memory limit (--memory of command.json), recorded peak RSS (jbgs_trace), cgroup peak (v2 trace1000)')
    print('TRACE', len(allrows), len(alldens), len(stage), len(mem), flush=True)


def fig_trend(g, series):
    plt = plt_ko()
    fig, ax = plt.subplots(1, 4, figsize=(18, 4))
    cols = plt.rcParams['axes.prop_cycle'].by_key()['color']
    data = {}
    for i, (label, kind, rows) in enumerate(series):
        if not rows:
            continue
        it = [r['iteration'] for r in rows]
        ls = '-' if kind == 'stopped' else '--'
        c = cols[i % len(cols)]
        ax[0].plot(it, [r['gaussians'] / 1e6 for r in rows], ls, color=c, label=f'{label} ({kind})')
        nd = [(r['iteration'], r['needle_le_001_share_at_last_densify']) for r in rows if r['needle_le_001_share_at_last_densify'] is not None]
        if nd:
            ax[1].plot(*zip(*nd), ls, color=c)
        e = [(r['iteration'], r['elong_lt_001']) for r in rows if r.get('elong_lt_001') is not None]
        if e:
            ax[1].plot(*zip(*e), ls, color=c, marker='.')
        ax[2].plot(it, [r['peak_rss_GiB'] for r in rows], ls, color=c)
        ax[3].plot(it, [r['peak_cuda_reserved_GiB'] for r in rows], ls, color=c)
        last = rows[-1]
        if kind == 'stopped':
            for a, k in zip(ax[[0, 2, 3]], ['gaussians', 'peak_rss_GiB', 'peak_cuda_reserved_GiB']):
                a.plot([last['iteration']], [last[k] / (1e6 if k == 'gaussians' else 1)], 'x', color=c, ms=10)
        data[label] = dict(kind=kind, rows=rows)
    for a, t in zip(ax, ['가우시안 수 (백만)', '길쭉함 ≤ 0.01 비율 (밀도 제어 때)', '호스트 RSS 최대 (GiB)', 'GPU 예약 최대 (GiB)']):
        a.set_title(t); a.set_xlabel('반복'); a.grid(alpha=.3)
    ax[0].legend(fontsize=7)
    fig.suptitle(f'{g}: 멈춘 시도(실선, x = 멈춘 곳)와 가장 가까운 끝난 판(점선)')
    fig.tight_layout()
    out = D / 'figures' / f'stop_trend_{g}'
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix('.png'), dpi=110)
    plt.close(fig)
    dump(out.with_suffix('.json'), dict(group=g, series=data, scientific_verdict=None))


def scales_of(path):
    """log-scales of a saved model: point_cloud.ply scale_* or the _scaling tensor of a jbgs_complete checkpoint."""
    path = Path(path)
    if path.suffix == '.ply':
        from plyfile import PlyData
        v = PlyData.read(str(path))['vertex']
        names = sorted(n for n in v.data.dtype.names if n.startswith('scale_'))
        return np.stack([np.asarray(v[n], np.float32) for n in names], 1)
    import torch
    ck = torch.load(str(path), map_location='cpu', weights_only=False)
    if isinstance(ck, dict) and isinstance(ck.get('model'), tuple) and len(ck['model']) > 4:
        return ck['model'][4].detach().float().numpy()   # JBGS_GEOGS_COMPLETE_STATE_v1: GaussianModel.capture() -> index 4 = _scaling (log)
    found = []
    def walk(o, depth=0):
        if depth > 6 or found:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ('_scaling', 'scaling') and hasattr(v, 'shape') and len(v.shape) == 2:
                    found.append(v)
                    return
                walk(v, depth + 1)
        elif isinstance(o, (list, tuple)):
            for v in o:
                if hasattr(v, 'shape') and len(getattr(v, 'shape', ())) == 2 and v.shape[1] in (2, 3) and v.dtype == torch.float32 and v.shape[0] > 1000:
                    pass
                walk(v, depth + 1)
    walk(ck)
    if not found:
        return None
    return found[0].detach().float().numpy()


def elong(g):
    spec = GROUPS.get(g) or dict(stopped=TU / 'runs' / g, finished=[])
    plt = plt_ko()
    runs = [(l, a, 'stopped') for l, a, _ in attempts(spec['stopped'])] + [(final_attempt(f)[0], final_attempt(f)[1], 'finished') for f in spec['finished']]
    rows, hist = [], {}
    bins = np.linspace(-5, 0, 51)
    for label, att, kind in runs:
        plys = sorted(glob.glob(str(att / 'model/point_cloud/iteration_*/point_cloud.ply')))
        have = {Path(f).parent.name for f in plys}
        files = plys + [f for f in sorted(glob.glob(str(att / 'model/jbgs_complete/iteration_*/checkpoint.pth'))) if Path(f).parent.name not in have]
        for f in files:
            it = int(Path(f).parent.name.split('_')[1])
            try:
                s = scales_of(f)
            except Exception as e:
                rows.append(dict(group=g, run=label, kind=kind, iteration=it, file=Path(f).name, status=f'읽지 못함: {type(e).__name__}: {e}'[:200]))
                continue
            if s is None:
                rows.append(dict(group=g, run=label, kind=kind, iteration=it, file=Path(f).name, status='스케일 없음'))
                continue
            sc = np.exp(s)
            ar = sc.min(1) / sc.max(1)
            h, _ = np.histogram(np.log10(np.clip(ar, 1e-5, 1)), bins)
            hist[f'{label}@{it}:{Path(f).name}'] = (h / max(1, len(ar))).tolist()
            rows.append(dict(group=g, run=label, kind=kind, iteration=it, file=Path(f).name, gaussians=int(len(ar)),
                             elong_lt_001=float((ar < .01).mean()), elong_lt_01=float((ar < .1).mean()),
                             elong_q01_q10_q50=np.quantile(ar, [.01, .1, .5]).tolist(), status='있음'))
            del s, sc, ar
    write(f'stop_elong_{g}', rows, f'order v2 3.5 row 2: elongation min(scale)/max(scale) of every saved file of {g} (point_cloud.ply and jbgs_complete checkpoints), shares < 0.01 and < 0.1')
    fig, ax = plt.subplots(figsize=(9, 5))
    for k, h in hist.items():
        ax.plot((bins[:-1] + bins[1:]) / 2, h, label=k)
    ax.axvline(-2, color='k', lw=.8, ls=':'); ax.axvline(-1, color='k', lw=.8, ls=':')
    ax.set_xlabel('log10(짧은 축 / 긴 축)'); ax.set_ylabel('비율'); ax.set_title(f'{g}: 저장 파일마다 길쭉함 분포 (점선 0.01, 0.1)')
    ax.legend(fontsize=6); ax.grid(alpha=.3)
    fig.tight_layout()
    out = D / 'figures' / f'stop_elong_{g}'
    fig.savefig(out.with_suffix('.png'), dpi=110)
    plt.close(fig)
    dump(out.with_suffix('.json'), dict(group=g, bins_log10=bins.tolist(), hist=hist, scientific_verdict=None))
    print('ELONG', g, len(rows), flush=True)


if __name__ == '__main__':
    dict(trace=trace, elong=elong)[sys.argv[1]](*sys.argv[2:])
