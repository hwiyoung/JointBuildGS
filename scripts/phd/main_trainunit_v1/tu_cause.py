"""Addendum 5 cause check, read-out (user 2026-11-12 '원인 확인부터'). Facts from saved run records only: no training, no GT.

Part 1  probes against the baseline: does the 판 다 input pipeline (probe0) or a x5 initialised area (probe1) raise the
        Gaussian count of the FINALTRAIN B0 ALS scene?  -> tables/cause_probes.*, figures/cause_probes.png
Part 2  where the count grew, between the saved 7,000 state and the last saved state <= 15,000 of each run, on a 5 m xy
        grid: inside / outside the unit's own region, by the number of training cameras that see the grid cell
        (cell centre at the mean z of its Gaussians projected into the training camera, depth > 0, inside the image;
        no occlusion), by lineage (origin 1 = prior seed family, 0 = image/background family), and by how concentrated
        the growth is (share of growth in the top 1 % / 5 % of grid cells).  -> tables/cause_where.*
Part 3  prior seed families (init_id = initial seed index kept by every clone/split child): growth by judgment region,
        source, kind, seed sigma quartile and building.  -> tables/cause_family*.*
Part 4  the three largest prior families per run: seed, judged patch, family extent.  -> tables/cause_top_families.*
Part 5  the largest family in the saved complete state (checkpoint): frozen share, opacity, size, duplicate positions.
        -> tables/cause_top_family_state.json;  figure of parts 3-4: figures/cause_family.png

  python tu_cause.py
"""
import csv
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager

from tu_common import *
from tu_growth import lineage

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 9})
G = 5.0
VIEW_BINS = [0, 1, 10, 30, 100, 10**9]
VIEW_LABELS = ['0', '1–9', '10–29', '30–99', '≥100']


def ply(p, fields=('x', 'y', 'z', 'origin', 'init_id')):
    with open(p, 'rb') as f:
        hdr = b''
        while not hdr.endswith(b'end_header\n'):
            hdr += f.readline()
    lines = hdr.decode().splitlines()
    assert 'format binary_little_endian 1.0' in lines
    n = int(next(l for l in lines if l.startswith('element vertex')).split()[2])
    props = [l.split() for l in lines if l.startswith('property')]
    kind = {'float': '<f4', 'int': '<i4'}
    mm = np.memmap(p, dtype=np.dtype([(q[2], kind[q[1]]) for q in props]), mode='r', offset=len(hdr), shape=(n,))
    return {k: np.asarray(mm[k]) for k in fields}


def state(model, it):
    for p in [model / f'jbgs_complete/iteration_{it}/point_cloud.ply', model / f'point_cloud/iteration_{it}/point_cloud.ply']:
        if p.exists():
            return p
    raise FileNotFoundError(f'{model} {it}')


def train_cams(model, names):
    cams = [c for c in json.loads((model / 'cameras.json').read_text()) if c['img_name'] in set(names)]
    assert len(cams) == len(set(names)), (model, len(cams), len(set(names)))
    return cams


def views(cams, P):
    n = np.zeros(len(P), int)
    for c in cams:
        Rc = np.asarray(c['rotation'], float)           # camera-to-world rotation (3DGS cameras.json)
        q = (P - np.asarray(c['position'], float)) @ Rc  # world -> camera
        z = q[:, 2]
        ok = z > 0.1
        u = c['fx'] * q[:, 0] / np.where(ok, z, 1) + c['width'] / 2
        v = c['fy'] * q[:, 1] / np.where(ok, z, 1) + c['height'] / 2
        n += ok & (u >= 0) & (u < c['width']) & (v >= 0) & (v < c['height'])
    return n


def runs():
    probes = {p['name']: p for p in json.loads((TU / 'probes/probes.json').read_text())['probes']}
    cells = {c['id']: c for c in json.loads((TU / 'cells/cells.json').read_text())['cells']}
    b0 = probes['probe0']
    ft_train = json.loads((S0 / 'fork_inputs/s61/B0_b10/split.json').read_text())['train']
    pr = TU / 'runs/probes'
    cr = TU / 'runs/cells/cells_ALS_s0'
    return [
        dict(key='base_s0', label='기준 B0 ALS 씨앗 0', atts=[FT / 'runs/B0_b10/ft_ALS_s0/attempt1'], train=ft_train,
             lo=b0['region_min'], hi=b0['region_max'], region='B0 상자', late=15000),
        dict(key='base_s1', label='씨앗 B0 ALS 씨앗 1', atts=[TU / 'runs/B0_b10/seed1_ALS/attempt1'], train=ft_train,
             lo=b0['region_min'], hi=b0['region_max'], region='B0 상자', late=15000),
        dict(key='probe0', label='probe0 (다 입력, B0 상자)', atts=[pr / 'probe0_ALS_s0/attempt1'], train=probes['probe0']['images'],
             lo=b0['region_min'], hi=b0['region_max'], region='B0 상자', late=15000),
        dict(key='probe1', label='probe1 (다 입력, 넓이 ×5)', atts=[pr / 'probe1_ALS_s0/attempt1'], train=probes['probe1']['images'],
             lo=probes['probe1']['region_min'], hi=probes['probe1']['region_max'], region='×5 영역', late=15000),
        dict(key='cell0', label='다 칸 0', atts=[cr / 'cell0/attempt1', cr / 'cell0/attempt2', cr / 'cell0/attempt3'], late_att=cr / 'cell0/attempt2', train=cells[0]['images'],
             stop='GPU 메모리로 13,800회에서 멈춤',
             lo=cells[0]['original_min'], hi=cells[0]['original_max'], region='원래 칸 경계', late=13200),
        dict(key='cell2', label='다 칸 2', atts=[cr / 'cell2/attempt1'], train=cells[2]['images'],
             lo=cells[2]['original_min'], hi=cells[2]['original_max'], region='원래 칸 경계', late=15000),
        dict(key='cell3', label='다 칸 3', atts=[cr / 'cell3/attempt1'], train=cells[3]['images'],
             lo=cells[3]['original_min'], hi=cells[3]['original_max'], region='원래 칸 경계', late=10600, stop='판 다 중단으로 10,600회까지'),
    ]


def inside(x, y, lo, hi):
    return (x >= lo[0]) & (x < hi[0]) & (y >= lo[1]) & (y < hi[1])


def part1(R):
    rows, curves = [], {}
    for r in R:
        its, g, peak = lineage(r['atts'])
        at = dict(zip(its, g))
        m0 = r['atts'][0] / 'model'
        init = json.loads((m0 / 'target_monitor/initialization.json').read_text())
        mx = max(v for i, v in at.items() if 7000 <= i <= 15000)
        e = ply(state(m0, 7000), ('x', 'y'))
        ins = inside(e['x'], e['y'], r['lo'], r['hi'])
        occ = len(np.unique(np.stack([np.floor(e['x'][ins]), np.floor(e['y'][ins])], 1), axis=0))
        lo, hi = np.maximum(r['lo'], -1e6), np.minimum(r['hi'], 1e6)
        rows.append(dict(key=r['key'], label=r['label'], train_images=len(r['train']), iterations_per_image=30000 / len(r['train']),
                         region=r['region'], region_area_m2=float(np.prod(np.array(hi) - np.array(lo))) if r['key'][:4] != 'cell' else None,
                         seeds=init['seeds'], prior_seeds=init['prior_seeds'], background_seeds=init.get('background_seeds'),
                         gaussians_6000=at.get(6000), gaussians_12000=at.get(12000), gaussians_15000=at.get(15000),
                         max_gaussians_7000_15000=mx, at_iteration=max(i for i, v in at.items() if v == mx and 7000 <= i <= 15000),
                         ratio_max_to_6000=mx / at[6000], growth_12500_to_last_per_500=(at[max(at)] - at[12500]) / ((max(at) - 12500) / 500)
                         if 12500 in at and max(at) > 12500 else None, last_iteration=max(at),
                         peak_reserved_GiB=peak / 2**30 if peak else None, occupied_m2_in_region_7000=occ, stop=r.get('stop'),
                         gaussians_per_occupied_m2_in_region_7000=float(ins.sum()) / occ if occ else None,
                         share_in_region_7000=float(ins.mean())))
        curves[r['key']] = dict(label=r['label'], iterations=its, gaussians=g)
        print('P1', r['key'], at.get(6000), mx, flush=True)
    return rows, curves


def part2(R):
    rows, maps = [], {}
    for r in R:
        m0, m1 = r['atts'][0] / 'model', r.get('late_att', r['atts'][-1]) / 'model'
        e = ply(state(m0, 7000))
        l = ply(state(m1, r['late']))
        cams = train_cams(m0, r['train'])
        ke = np.stack([np.floor(e['x'] / G), np.floor(e['y'] / G)], 1).astype(np.int64)
        kl = np.stack([np.floor(l['x'] / G), np.floor(l['y'] / G)], 1).astype(np.int64)
        keys, inv = np.unique(np.r_[ke, kl], axis=0, return_inverse=True)
        inv = inv.ravel()
        ie, il = inv[:len(ke)], inv[len(ke):]
        ne = np.bincount(ie, minlength=len(keys)); nl = np.bincount(il, minlength=len(keys))
        zs = np.bincount(il, weights=l['z'], minlength=len(keys)) + np.bincount(ie, weights=e['z'], minlength=len(keys))
        zc = zs / np.maximum(nl + ne, 1)
        cx, cy = (keys[:, 0] + .5) * G, (keys[:, 1] + .5) * G
        nv = views(cams, np.c_[cx, cy, zc])
        grow = nl - ne
        tot = int(len(l['x']) - len(e['x']))
        ins = inside(cx, cy, r['lo'], r['hi'])
        pos = np.clip(grow, 0, None)
        order = np.sort(pos)[::-1]
        k1, k5 = max(1, int(round(.01 * len(keys)))), max(1, int(round(.05 * len(keys))))
        vb = np.digitize(nv, VIEW_BINS[1:-1])
        lin = {o: int((l['origin'] == o).sum() - (e['origin'] == o).sum()) for o in (0, 1)}
        row = dict(key=r['key'], label=r['label'], early_iteration=7000, late_iteration=r['late'], gaussians_early=len(e['x']),
                   gaussians_late=len(l['x']), growth=tot, grid_cells=len(keys), grid_m=G,
                   growth_in_region=int(grow[ins].sum()), growth_outside_region=int(grow[~ins].sum()),
                   share_growth_outside_region=float(grow[~ins].sum()) / tot if tot else None,
                   share_positive_growth_top1pct_cells=float(order[:k1].sum()) / pos.sum() if pos.sum() else None,
                   share_positive_growth_top5pct_cells=float(order[:k5].sum()) / pos.sum() if pos.sum() else None,
                   growth_prior_lineage=lin[1], growth_image_lineage=lin[0],
                   train_cameras=len(cams))
        for b, lab in enumerate(VIEW_LABELS):
            s = vb == b
            row[f'growth_views_{lab}'] = int(grow[s].sum())
            row[f'area_m2_views_{lab}'] = float(s.sum() * G * G)
            row[f'growth_per_m2_views_{lab}'] = float(grow[s].sum()) / (s.sum() * G * G) if s.any() else None
        # Gaussians per m2 at late in the busiest 1 % of cells, and their camera views (median)
        top = np.argsort(pos)[::-1][:k1]
        row['late_per_m2_top1pct_median'] = float(np.median(nl[top]) / (G * G))
        row['views_top1pct_median'] = float(np.median(nv[top]))
        row['views_all_cells_with_late_gaussians_median'] = float(np.median(nv[nl > 0]))
        rows.append(row)
        maps[r['key']] = dict(cx=cx, cy=cy, grow=grow, nv=nv, lo=r['lo'], hi=r['hi'], label=r['label'], late=r['late'],
                              cams=np.array([c['position'][:2] for c in cams]))
        print('P2', r['key'], tot, row['share_growth_outside_region'], row['share_positive_growth_top1pct_cells'], flush=True)
    return rows, maps


def write(name, rows, note):
    out = D / f'tables/{name}'
    dump(out.with_suffix('.json'), dict(rows=rows, note=note, scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    with out.with_suffix('.md').open('w') as f:
        f.write('| ' + ' | '.join(fields) + ' |\n| ' + ' | '.join('---' for _ in fields) + ' |\n')
        for r in rows:
            f.write('| ' + ' | '.join('' if r.get(k) is None else (f'{r[k]:.3f}' if isinstance(r.get(k), float) else str(r[k])) for k in fields) + ' |\n')


STY = dict(base_s0=('0.35', '-'), base_s1=('0.6', '-'), probe0=('#0072b2', '-'), probe1=('#d55e00', '-'),
           cell0=('#009e73', '--'), cell2=('#cc79a7', '--'), cell3=('#e69f00', '--'))


def fig1(rows, curves):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for k, cv in curves.items():
        c, ls = STY[k]
        it, g = np.array(cv['iterations']), np.array(cv['gaussians'])
        m = it <= 15000
        ax[0].plot(it[m], g[m] / 1e6, color=c, ls=ls, lw=1.6 if k.startswith('probe') else 1.1, label=cv['label'])
    ax[0].axhline(9.578396, color='#009e73', lw=0.5, ls=':')
    ax[0].set(xlabel='반복', ylabel='가우시안 (백만)', xlim=(0, 15000), title='가우시안 수 (15,000회까지)')
    ax[0].legend(fontsize=8)
    lab = [r['label'] for r in rows]
    mx = [r['max_gaussians_7000_15000'] / 1e6 for r in rows]
    cols = [STY[r['key']][0] for r in rows]
    y = np.arange(len(rows))[::-1]
    ax[1].barh(y, mx, color=cols)
    for yi, r, v in zip(y, rows, mx):
        a = r['region_area_m2']
        txt = f'{v:.2f} M · 영상 {r["train_images"]}' + (f' · 넓이 {a/1e3:.1f}천 m²' if a else ' · 경계 밖으로 열린 칸') + \
              (f' · {r["stop"]}' if r.get('stop') else '')
        ax[1].text(v + 0.1, yi, txt, va='center', fontsize=8)
    ax[1].set_yticks(y, lab)
    ax[1].set(xlim=(0, 14), xlabel='7,000~15,000회 최대 가우시안 (백만)', title='넓이를 5배로 늘려도 최대 수는 그대로')
    fig.tight_layout()
    png = D / 'figures/cause_probes.png'
    fig.savefig(png, dpi=130)
    dump(png.with_suffix('.json'), dict(figure=png.name, table='tables/cause_probes.json',
         curves={k: dict(label=v['label'], iterations=v['iterations'], gaussians=v['gaussians']) for k, v in curves.items()},
         scientific_verdict=None))


def fig_family(R):
    """One question: did the cells grow everywhere, or did one seed family run away?"""
    fam = json.loads((D / 'tables/cause_family.json').read_text())['rows']
    top = {r['key']: r for r in json.loads((D / 'tables/cause_top_families.json').read_text())['rows'] if r['rank'] == 1}
    byk = {r['key']: r for r in R}
    keys = ['base_s0', 'probe0', 'probe1', 'cell0', 'cell2', 'cell3']
    fig = plt.figure(figsize=(16, 5.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1, 1])
    a = fig.add_subplot(gs[0])
    y = np.arange(len(keys))[::-1]
    for yi, k in zip(y, keys):
        t, f = top[k], next(x for x in fam if x['key'] == k)
        c = STY[k][0]
        a.barh(yi + .18, t['family_7000'], height=.34, color=c, alpha=.45)
        a.barh(yi - .18, t['family_late'], height=.34, color=c)
        tot = t['family_late'] / (f['prior_lineage_late'] + f['background_lineage_late'])
        a.text(t['family_late'] * 1.15, yi - .18, f'{t["family_late"]:,} ({100*tot:.0f} %)', va='center', fontsize=8)
    a.set_xscale('log')
    a.set_yticks(y, [byk[k]['label'] for k in keys])
    a.set(xlim=(100, 3e8), xlabel='가장 큰 사전 정보 씨앗 계보의 가우시안 수 (로그; 옅은 막대 = 7,000회, 진한 막대 = 마지막 저장, 괄호 = 그 판 전체 중 몫)',
          title='한 씨앗의 자손이 수백만 개로 불어남 (칸 0·2·3만)')
    a.xaxis.label.set_size(8)
    ext = dict(cell0=(-28, 14, -152, -124), cell2=(-28, 14, -152, -124))
    for j, k in enumerate(['cell0', 'cell2']):
        b = fig.add_subplot(gs[j + 1])
        t = top[k]
        l = ply(state(byk[k].get('late_att', byk[k]['atts'][-1]) / 'model', byk[k]['late']), ('x', 'y', 'init_id'))
        x0, x1, y0, y1 = ext[k]
        s = l['init_id'] == t['init_id']
        bins = [np.arange(x0, x1 + .5, .5), np.arange(y0, y1 + .5, .5)]
        H, _, _ = np.histogram2d(l['x'][s], l['y'][s], bins=bins)
        O, _, _ = np.histogram2d(l['x'][~s], l['y'][~s], bins=bins)
        b.imshow(np.log10(1 + O.T / .25), origin='lower', extent=(x0, x1, y0, y1), cmap='Greys', vmin=0, vmax=4, alpha=.6)
        im = b.imshow(np.ma.masked_equal(H.T, 0) / .25, origin='lower', extent=(x0, x1, y0, y1), cmap='magma_r', norm=colors.LogNorm(vmin=10, vmax=1e6))
        sx, sy = t['seed_xyz'][:2]
        b.scatter([sx], [sy], marker='*', s=160, color='#00b4ff', ec='k', lw=.6, zorder=4)
        for kk, mk in [('cell0', 'o'), ('cell2', 's')]:
            if kk != k:
                ox, oy = top[kk]['seed_xyz'][:2]
                b.scatter([ox], [oy], marker=mk, s=50, facecolor='none', ec='#00b4ff', lw=1.2, zorder=4)
        b.axvline(-3.79, color='k', lw=.8, ls='--')
        b.text(-3.5, y1 - 1, '칸 0 | 칸 2 경계', fontsize=7, va='top')
        b.set(xlim=(x0, x1), ylim=(y0, y1), aspect='equal', xlabel='x (m)', ylabel='y (m)',
              title=f'{byk[k]["label"]}, {byk[k]["late"]:,}회: 그 계보의 밀도')
    fig.colorbar(im, ax=fig.axes[1:], shrink=.8, label='그 계보의 가우시안 / m² (0.5 m 칸)')
    fig.text(.62, -.02, f'별 = 그 판에서 불어난 씨앗, 빈 표시 = 다른 칸 판에서 불어난 씨앗(둘 다 건물 {top["cell0"]["patch_building"]}의 판정 일치 패치), '
             '회색 = 다른 가우시안, 점선 = 칸 0 | 칸 2 경계', ha='center', fontsize=8)
    png = D / 'figures/cause_family.png'
    fig.savefig(png, dpi=130, bbox_inches='tight')
    dump(png.with_suffix('.json'), dict(figure=png.name, tables=['tables/cause_family.json', 'tables/cause_top_families.json'],
         note='largest prior seed family (init_id) per run; maps: 0.5 m grid of that family in the saved state; no training, no GT', scientific_verdict=None))


REGION = {1: '일치', 2: '보존', 3: '보정', 0: '결측', 5: '보정(빈 공간)', -1: '목표 없음', 4: '배경'}
SOURCE = {0: 'B0 판', 1: 'R1 판', 2: 'B173 판', 3: 'JUDGECHECK 행'}


def part3(R):
    """Part 3: which prior seed families grew (init_id = index of the initial seed, kept by every descendant)."""
    rows, groups, buildings = [], [], []
    for r in R:
        if r['key'] == 'base_s1':
            continue
        m0, m1 = r['atts'][0] / 'model', r.get('late_att', r['atts'][-1]) / 'model'
        if r['key'].startswith('base'):
            sd = loadz(FT / 'stage1/B0_b10__ALS/seeds.npz', ['origin', 'patch', 'sigma'])
            T = loadz(FT / 'targets/B0_b10__ALS.npz', ['region', 'kind', 'sigma', 'area'])
            T['source'] = np.zeros(len(T['region']), np.int8)
            T['building'] = loadz(TG / 'stage0_r1/inputs/B0_b10_ALS.npz', ['building'])['building'].astype('U96')
        else:
            unit = r['key'] if r['key'].startswith('probe') else r['key']
            sd = loadz(TU / f'stage1/{unit}__ALS/seeds.npz', ['origin', 'patch', 'sigma'])
            T = loadz(TU / f'targets/{unit}__ALS.npz', ['region', 'kind', 'sigma', 'area', 'source', 'building'])
        e, l = ply(state(m0, 7000), ('origin', 'init_id')), ply(state(m1, r['late']), ('origin', 'init_id'))
        ns = len(sd['origin'])
        assert l['init_id'].max() < ns and np.array_equal(sd['origin'][l['init_id']], l['origin'].astype('i1')), r['key']
        fe = np.bincount(e['init_id'], minlength=ns); fl = np.bincount(l['init_id'], minlength=ns)
        pri = sd['origin'] == 1
        pidx = np.flatnonzero(pri)
        patch = sd['patch'][pidx]
        size = fl[pidx]
        g = (fl - fe)[pidx]
        top = np.sort(size)[::-1]
        k1 = max(1, int(round(.01 * len(pidx))))
        rows.append(dict(key=r['key'], label=r['label'], late_iteration=r['late'], prior_seeds=len(pidx),
                         prior_lineage_late=int(size.sum()), prior_lineage_growth=int(g.sum()),
                         share_prior_lineage_late_in_top1pct_families=float(top[:k1].sum() / max(size.sum(), 1)),
                         largest_family=int(top[0]), families_ge_100=int((size >= 100).sum()), families_ge_1000=int((size >= 1000).sum()),
                         background_lineage_late=int(fl[~pri].sum()), background_lineage_growth=int((fl - fe)[~pri].sum())))
        reg = T['region'][patch]; src = T['source'][patch]; kind = T['kind'][patch]; sig = sd['sigma'][pidx]
        for name, lab in [('region', np.vectorize(REGION.get)(reg)), ('source', np.vectorize(SOURCE.get)(src)), ('kind', kind.astype(str))]:
            for v in np.unique(lab):
                s = lab == v
                groups.append(dict(key=r['key'], by=name, value=str(v), seeds=int(s.sum()), late=int(size[s].sum()), growth=int(g[s].sum()),
                                   growth_per_seed=float(g[s].sum() / s.sum()), share_of_prior_growth=float(g[s].sum() / g.sum()) if g.sum() else None,
                                   sigma_median_m=float(np.median(sig[s]))))
        q = np.quantile(sig, [.25, .5, .75])
        bins = np.digitize(sig, q)
        for b in range(4):
            s = bins == b
            groups.append(dict(key=r['key'], by='sigma_quartile', value=f'Q{b+1}', seeds=int(s.sum()), late=int(size[s].sum()), growth=int(g[s].sum()),
                               growth_per_seed=float(g[s].sum() / max(s.sum(), 1)), share_of_prior_growth=float(g[s].sum() / g.sum()) if g.sum() else None,
                               sigma_median_m=float(np.median(sig[s])) if s.any() else None))
        bld = T['building'][patch]
        ub, inv = np.unique(bld, return_inverse=True)
        gb = np.bincount(inv, weights=g); nb = np.bincount(inv)
        for i in np.argsort(gb)[::-1][:10]:
            s = inv == i
            regs = {REGION[int(k)]: int((reg[s] == k).sum()) for k in np.unique(reg[s])}
            buildings.append(dict(key=r['key'], building=str(ub[i]), seeds=int(nb[i]), growth=int(gb[i]),
                                  share_of_prior_growth=float(gb[i] / g.sum()) if g.sum() else None, largest_family=int(size[s].max()),
                                  source=SOURCE[int(np.bincount(src[s]).argmax())], regions=json.dumps(regs, ensure_ascii=False),
                                  kinds=json.dumps({str(k): int((kind[s] == k).sum()) for k in np.unique(kind[s])}),
                                  sigma_median_m=float(np.median(sig[s]))))
        print('P3', r['key'], rows[-1]['prior_lineage_growth'], rows[-1]['largest_family'], flush=True)
    write('cause_family', rows, 'prior seed families (init_id) between the saved 7,000 state and the last saved state; no training, no GT')
    write('cause_family_groups', groups, 'prior lineage growth by judgment region, source, patch kind and seed sigma quartile')
    write('cause_family_buildings', buildings, 'top 10 buildings by prior lineage growth per run (building = id of the judged patch)')


def part4(R):
    """Part 4: the three largest prior seed families of each run: their seed, judged patch and where the family sits."""
    rows = []
    for r in R:
        if r['key'] == 'base_s1':
            continue
        m0, m1 = r['atts'][0] / 'model', r.get('late_att', r['atts'][-1]) / 'model'
        if r['key'].startswith('base'):
            sdp, tp = FT / 'stage1/B0_b10__ALS/seeds.npz', FT / 'targets/B0_b10__ALS.npz'
        else:
            sdp, tp = TU / f'stage1/{r["key"]}__ALS/seeds.npz', TU / f'targets/{r["key"]}__ALS.npz'
        sd = loadz(sdp, ['origin', 'patch', 'sigma', 'xyz', 'normal', 'region'])
        T = loadz(tp)
        e = ply(state(m0, 7000), ('origin', 'init_id'))
        l = ply(state(m1, r['late']), ('x', 'y', 'z', 'opacity', 'origin', 'init_id'))
        ns = len(sd['origin'])
        fe = np.bincount(e['init_id'], minlength=ns); fl = np.bincount(l['init_id'], minlength=ns)
        fl_p = np.where(sd['origin'] == 1, fl, -1)
        for rank, i in enumerate(np.argsort(fl_p)[::-1][:3]):
            s = l['init_id'] == i
            p = int(sd['patch'][i])
            x, y, z = l['x'][s], l['y'][s], l['z'][s]
            q = lambda a: [float(v) for v in np.quantile(a, [.01, .5, .99])]
            cells5 = len(np.unique(np.stack([np.floor(x / 5), np.floor(y / 5)], 1), axis=0))
            row = dict(key=r['key'], rank=rank + 1, init_id=int(i), family_7000=int(fe[i]), family_late=int(fl[i]), late_iteration=r['late'],
                       seed_xyz=[float(v) for v in sd['xyz'][i]], seed_normal=[float(v) for v in sd['normal'][i]], seed_sigma_m=float(sd['sigma'][i]),
                       seed_region=REGION.get(int(sd['region'][i])), patch=p,
                       family_x_p01_p50_p99=q(x), family_y_p01_p50_p99=q(y), family_z_p01_p50_p99=q(z),
                       family_occupied_5m_cells=cells5, family_opacity_p50=float(np.median(l['opacity'][s])))
            for k in ['building', 'kind', 'area', 'region', 'judge_region', 'reason', 'source', 'surface_exists', 'h', 'sigma', 'sigma_replaced', 'undecided_before']:
                if k in T and np.ndim(T[k]) and len(T[k]) > p:
                    v = T[k][p]
                    row[f'patch_{k}'] = v.item() if hasattr(v, 'item') else str(v)
            for k in ['centre', 'normal', 'target']:
                if k in T and np.ndim(T[k]) == 2 and len(T[k]) > p:
                    row[f'patch_{k}'] = [float(v) for v in T[k][p]]
            rows.append(row)
            print('P4', r['key'], rank + 1, int(i), int(fe[i]), int(fl[i]), row.get('patch_building'), row.get('patch_area'), flush=True)
    write('cause_top_families', rows, 'three largest prior seed families per run: seed, judged patch, family extent at the last saved state; no training, no GT')


def part5(R):
    """Part 5: the largest family in the saved complete state (checkpoint.pth, CPU): share exempt from density control and
    opacity reset (frozen_mask), opacity, size, duplicate positions and accumulated view-space gradient against the rest."""
    import torch
    top = {r['key']: r for r in json.loads((D / 'tables/cause_top_families.json').read_text())['rows'] if r['rank'] == 1}
    rows = []
    for r in R:
        if r['key'] not in top:
            continue
        ck = r.get('late_att', r['atts'][-1]) / f'model/jbgs_complete/iteration_{r["late"]}/checkpoint.pth'
        st = torch.load(ck, map_location='cpu', weights_only=False)
        mdl = st['model']
        xyz, scal, opa, acc, den = (t.detach() for t in (mdl[1], mdl[4], mdl[6], mdl[8], mdl[9]))
        fid = top[r['key']]['init_id']
        ii = st['init_id'].long()
        fam = (ii == fid).numpy()
        fr = st['frozen_mask'].bool().numpy() if st['frozen_mask'] is not None else np.zeros(len(fam), bool)
        op = torch.sigmoid(opa[:, 0].float()).numpy()
        sc = torch.exp(scal.float()).max(1).values.numpy()
        g = (acc[:, 0].float() / den[:, 0].float().clamp(min=1)).numpy()
        X = xyz.float().numpy()
        def stats(m):
            u = len(np.unique(np.round(X[m] * 1000).astype(np.int64), axis=0)) if m.any() else 0
            q = lambda a: [float(v) for v in np.quantile(a[m], [.1, .5, .9])] if m.any() else None
            return dict(n=int(m.sum()), frozen_share=float(fr[m].mean()) if m.any() else None, distinct_positions_1mm=u,
                        opacity_p10_p50_p90=q(op), max_scale_m_p10_p50_p90=q(sc), mean_grad_p10_p50_p90=q(g))
        rest = ~fam
        row = dict(key=r['key'], iteration=st['iteration'], init_id=fid, family=stats(fam), family_frozen=stats(fam & fr),
                   family_not_frozen=stats(fam & ~fr), others=stats(rest), others_frozen_share=float(fr[rest].mean()),
                   all_gaussians=int(len(fam)), densify_grad_threshold=st['optimization'].get('densify_grad_threshold'))
        rows.append(row)
        print('P5', r['key'], row['family']['n'], row['family']['frozen_share'], row['family']['distinct_positions_1mm'], flush=True)
        del st, mdl
    dump(D / 'tables/cause_top_family_state.json', dict(rows=rows, note='largest prior family in the saved complete state; frozen_mask = exempt from clone/split/prune and from opacity reset (fork gaussian_model.py); no training, no GT', scientific_verdict=None))


def main():
    cfg()
    R = runs()
    if sys.argv[1:] == ['fig']:
        fig_family(R)
        print('DONE', flush=True)
        return
    if sys.argv[1:] == ['state']:
        part5(R)
        print('DONE', flush=True)
        return
    if sys.argv[1:] == ['family']:
        part3(R)
        print('DONE', flush=True)
        return
    if sys.argv[1:] == ['top']:
        part4(R)
        print('DONE', flush=True)
        return
    r1, cv = part1(R)
    write('cause_probes', r1, 'addendum 5 probes vs FINALTRAIN B0 ALS and 판 다 cells; counts from target_monitor/curve.jsonl; no training, no GT')
    fig1(r1, cv)
    r2, mp = part2(R)
    write('cause_where', r2, 'growth between the saved 7,000 state and the last saved state <= 15,000, 5 m xy grid; no training, no GT')
    part3(R)
    part4(R)
    part5(R)
    fig_family(R)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
