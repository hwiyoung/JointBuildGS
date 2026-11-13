"""Work ga outputs: tables (values per place x state, events per window, largest drops) and figures (curves, section strips) from addendum3/ga/<run>.json/_strips.npz.
  tables | figures"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
from a3_ga import REASON_NAMES
plt = korean_plt()
GA = A3O/'ga'; FIG = A3D/'figures'
WINDOWS = [(0, 1000), (1000, 3000), ('3000', 'reset'), (3000, 6000), ('6000', 'reset'), (6000, 7000), (7000, 9000), ('9000', 'reset'), (9000, 12000), ('12000', 'reset'), (12000, 15000), (15000, 30000)]
SCOL = {'same_patch': '#1F5FD6', 'other_patch': '#8E44AD', 'released': '#E67E22', 'background': '#7F8C8D'}

GA_RUNS = [r for r in RUNS if 'short' not in RUNS[r]]   # work ga record runs only (work ba runs have their own outputs)
def all_rows(runs=None):
    rows = []
    for run in (runs or GA_RUNS):
        f = GA/f'{run}.json'
        if f.exists(): rows += json.loads(f.read_text())['rows']
    for r in rows:   # per GT area (places differ in size; the control side wall is ~6x the visible wall 0-5 m)
        for k in ['front_op', 'back_op', 'front_n', 'back_n']: r[f'{k}_per_m2'] = r[k]/r['area_m2'] if r.get(k) is not None and r.get('area_m2') else None
    return rows

def order_key(r): return (r['iteration'], 0 if r['pre_reset'] else 1)

def tables():
    rows = all_rows(); ctable('ga_values', rows); ev = []; drops = []
    for place in dict.fromkeys(r['place'] for r in rows):
        q = sorted([r for r in rows if r['place'] == place], key=order_key)
        RES = {3000, 6000, 9000, 12000}
        def k_(r): return (r['iteration'], 0 if r['pre_reset'] else 1)
        def at(key): return next((r for r in q if k_(r) == key), None)
        for w in WINDOWS:
            if w[1] == 'reset':
                it = int(w[0]); lo, hi = (it, 0), (it, 1); label = f'{it} 재설정 순간'
            else:
                lo = (w[0], 1); hi = (w[1], 0) if w[1] in RES else (w[1], 1); label = f'{w[0]}–{w[1]}'
            sel = [r for r in q if lo < k_(r) <= hi]; e = dict(place=place, run=q[0]['run'], window=label, counted_from=q[0]['counted_from'])
            for k in ['deleted', 'released', 'retarget_out', 'retarget_in', 'born']+[f'deleted_{nm}' for nm in REASON_NAMES.values()]:
                e[k] = int(sum(r.get(k) or 0 for r in sel))
            ra, rb = at(lo), at(hi)
            if ra and rb:
                for k in ['bound_n', 'bound_per_m2', 'bound_op_ge05_pct', 'bound_op_median', 'front_op', 'back_op', 'front_op_per_m2', 'back_op_per_m2', 'completeness_pct']: e[f'{k}_start'] = ra.get(k); e[f'{k}_end'] = rb.get(k)
            ev.append(e)
        for excl in [False, True]:
            best = {}
            for a, b in zip(q[:-1], q[1:]):
                if excl and b['pre_reset'] is False and a['pre_reset'] and a['iteration'] == b['iteration']: continue
                for k in ['bound_n', 'bound_op_ge05_pct']:
                    if a.get(k) is None or b.get(k) is None: continue
                    dv = b[k]-a[k]
                    if k not in best or dv < best[k][0]: best[k] = (dv, a, b)
            for k, (dv, a, b) in best.items():
                drops.append(dict(place=place, value=k, reset_instants_excluded=excl, start=a['name'], end=b['name'], start_value=a[k], end_value=b[k], change=dv,
                                  **{f'interval_{x}': b.get(x) for x in ['deleted', 'released', 'retarget_out', 'retarget_in', 'born']+[f'deleted_{nm}' for nm in REASON_NAMES.values()]}))
    ctable('ga_events_windows', ev); ctable('ga_largest_drop', drops); print('GA_TABLES', len(rows), len(ev), len(drops), flush=True)

def figures():
    FIG.mkdir(parents=True, exist_ok=True); rows = all_rows(); c = ccfg()['work_ga']
    for place, ctrl in CONTROL_OF.items():
        q = sorted([r for r in rows if r['place'] == place], key=order_key); qc = sorted([r for r in rows if r['place'] == ctrl], key=order_key)
        if not q: continue
        panels = [('bound_per_m2', '목표면에 묶인 가우시안 (참값 1 m²당)'), ('bound_op_ge05_pct', '그중 불투명도 0.5 이상 (%)'), ('front_op_per_m2', '목표면 앞 0.2~3 m 불투명도 합 (참값 1 m²당)'),
                  ('back_op_per_m2', '목표면 뒤 0.2~3 m 불투명도 합 (참값 1 m²당)'), ('completeness_pct', '완전성 (%)')]
        fig, axs = plt.subplots(len(panels), 1, figsize=(10, 13), dpi=110, sharex=True)
        for ax, (k, lab) in zip(axs, panels):
            for data, col, lw, nm in [(q, '#C0392B', 1.6, PLACE_KO[place]), (qc, '#95A5A6', 1.0, PLACE_KO[ctrl])]:
                x = [r['iteration'] for r in data if r.get(k) is not None]; y = [r[k] for r in data if r.get(k) is not None]
                ax.plot(x, y, color=col, lw=lw, marker='o' if k == 'completeness_pct' else None, ms=3, label=nm)
            for it in c['curve_lines']['opacity_reset']: ax.axvline(it, color='#2C3E50', ls=':', lw=.8)
            ax.axvline(c['curve_lines']['normal_on'], color='#16A085', ls='--', lw=.9); ax.axvline(c['curve_lines']['densify_end'], color='#7D3C98', ls='--', lw=.9)
            ax.set_ylabel(lab, fontsize=8); ax.grid(alpha=.25)
        axs[0].legend(fontsize=8, loc='upper right'); axs[-1].set_xlabel('반복 수 (점선: 불투명도 재설정 3,000·6,000·9,000·12,000 / 초록: 7,000 법선 항 / 보라: 15,000 늘리기 끝)', fontsize=8)
        fig.tight_layout(); p = FIG/f'ga_curve_{place}.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
        dump(p.with_suffix('.json'), dict(at=now(), figure=str(p.name), place=place, control=ctrl, run=q[0]['run'], counted_from=q[0]['counted_from'], source=str(GA/f"{q[0]['run']}.json"), panels=[k for k, _ in panels], scientific_verdict=None))
    for run in GA_RUNS:
        f = GA/f'{run}_strips.npz'
        if not f.exists(): continue
        Z = loadz(f)
        for place in RUNS[run]['places']:
            if place.endswith('control') or place in ('visible_side', 'long_wall'): continue
            times = c['strip_times']; fig, axs = plt.subplots(2, 4, figsize=(18, 9), dpi=110, sharex=True, sharey=True); fr = Z[f'{place}__frame']; win = fr[9:13]; srcs = {}
            for ax, nm in zip(axs.ravel(), times):
                gt = Z[f'{place}__gt']; ax.scatter(gt[:, 0], gt[:, 1], s=.6, c='#BDBDBD', lw=0, rasterized=True)
                for sg in Z[f'{place}__target']: ax.plot(sg[:, 0], sg[:, 1], color='#1F5FD6', lw=1.2)
                k = f'{place}__{nm}__mesh'
                if k in Z:
                    for sg in Z[k]: ax.plot(sg[:, 0], sg[:, 1], color='#D62728', lw=.9)
                    srcs[nm] = str(Z[f'{place}__{nm}__mesh_path'])
                g = Z.get(f'{place}__{nm}__g')
                if g is not None and len(g):
                    for si, sn in enumerate(STATE_NAMES):
                        m = g[:, 3] == si; ax.scatter(g[m, 0], g[m, 1], s=2+28*g[m, 2], c=SCOL[sn], alpha=.8, lw=0, rasterized=True)
                ax.set_title(nm, fontsize=10); ax.set_xlim(win[0], win[1]); ax.set_ylim(win[2], win[3]); ax.set_aspect('equal')
            hs = [plt.Line2D([], [], color=SCOL[s], marker='o', ls='', label=STATE_KO[s]) for s in STATE_NAMES]+[plt.Line2D([], [], color='#BDBDBD', marker='o', ls='', label='참값'),
                  plt.Line2D([], [], color='#1F5FD6', label='목표면'), plt.Line2D([], [], color='#D62728', label='메시')]
            fig.legend(handles=hs, loc='lower center', ncol=7, fontsize=9); fig.tight_layout(rect=(0, .05, 1, 1)); p = FIG/f'ga_strip_{place}.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
            dump(p.with_suffix('.json'), dict(at=now(), figure=p.name, place=place, run=run, section=dict(origin=fr[0:3].tolist(), h_axis=fr[3:6].tolist(), slab_normal=fr[6:9].tolist(), window_h_z=win.tolist(), thickness_m=0.5),
                 times=times, meshes=srcs, colours='state relative to the place patch set (bound to a place patch / other patch / released / background); marker size = opacity', scientific_verdict=None))
    print('GA_FIGURES done', flush=True)

if __name__ == '__main__':
    {'tables': tables, 'figures': figures}[sys.argv[1]]()
