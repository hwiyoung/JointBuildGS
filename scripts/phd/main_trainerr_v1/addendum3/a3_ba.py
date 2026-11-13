"""Work ba (order 7) outputs after the trainings.
  annex     : ba3 (B0 x ALS record): Gaussians inside the annex box per saved state (count, size, opacity, constraint state, origin) and per interval
              deletions by reason, births, range enter/exit -> tables/ba3_annex_states.csv, ba3_annex_windows.csv; 30000 mesh: result points in the box > 1 m from GT
  tables    : ba1/ba2 visible-wall completeness (7000/10000/15000/30000) beside the record run; scene values (all / case rows) beside the record and original runs
  figures   : ba curves in the work-ga format, record run as the light line"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
from a3_ga import REASON_NAMES
BA3 = A3O/'runs/B0_b10/ba3_B0_ALS_record/attempt1/model'
MESH_ITS = ['7000', '10000', '12000', '15000', '30000']   # 12000: ba2 stopped there (issues.md); record run mesh from this addendum (2.3)

def annex():
    c = ccfg()['places']['annex_box']; lo = np.array([c['x'][0], c['y'][0], c['z'][0]]); hi = np.array([c['x'][1], c['y'][1], c['z'][1]]); rows = []; win = []
    E = load_events(BA3, ('delete', 'birth', 'range')); sv = saves(BA3); prev = None
    def inbox(x): return np.all((x >= lo) & (x <= hi), 1)
    for s in sv:
        S = load_state(BA3, s['name'], 'states'); k = inbox(S['xyz']); tg = S['tag'][k]
        r = dict(name=s['name'], iteration=s['iteration'], gaussians=int(k.sum()), size_median_m=med(S['size'][k]), size_p90_m=qs(S['size'][k], (90,))['p90'] if k.any() else None,
                 opacity_median=med(S['opacity'][k]), opacity_ge05_pct=pct(S['opacity'][k] >= .5) if k.any() else None, bound=int((tg == 1).sum()), released=int((tg == 2).sum()), background=int((tg == 0).sum()),
                 prior_origin=int((S['origin'][k] == 1).sum()))
        if prev is not None:
            d = E['delete']; m = (d['seq'] > prev['seq']) & (d['seq'] <= s['seq']) & inbox(d['xyz'].astype('f8'))
            for rc, nm in REASON_NAMES.items(): r[f'deleted_{nm}'] = int((m & (d['reason'] == rc)).sum())
            b = E['birth']; r['born'] = int(((b['seq'] > prev['seq']) & (b['seq'] <= s['seq']) & inbox(b['xyz'].astype('f8'))).sum()) if len(b) else 0
            g = E['range']
            if len(g): w = (g['seq'] > prev['seq']) & (g['seq'] <= s['seq']); r['range_enter'] = int((w & g['enter']).sum()); r['range_exit'] = int((w & ~g['enter']).sum())
        rows.append(r); prev = s
    ctable('ba3_annex_states', rows)
    f = A3O/'meshes/B0_b10__ALS__ba3_30000/points.npz'; mesh = {}
    if f.exists():
        z = loadz(f, ['result__xyz', 'result__s_m', 'result__eligible_new']); k = inbox(z['result__xyz'].astype('f8')); s_ = z['result__s_m'][k]
        mesh = dict(result_points_in_box=int(k.sum()), farther_than_1m=int((np.isfinite(s_) & (np.abs(s_) > 1)).sum()), no_distance=int((~np.isfinite(s_)).sum()), source=str(f))
    dump(A3D/'tables/ba3_annex_mesh.json', dict(at=now(), **mesh, box=c, scientific_verdict=None)); print('BA3_ANNEX', rows[0], rows[-1], mesh, flush=True)

def scene_rows(score_json, label):
    if not Path(score_json).exists(): return []
    out = []
    for x in json.loads(Path(score_json).read_text())['rows']:
        if x['surface'] in ('all', 'wall', 'roof') and str(x['case_id']) in ('all', '0', '1', '2', '3', '4'):
            out.append(dict(source=label, surface=x['surface'], case_id=str(x['case_id']), n_gt=x['n_gt'], completeness_pct=x['completeness_pct'], accuracy_pct=x.get('accuracy_pct'), result_n=x.get('result_n')))
    return out

def tables():
    import csv
    comp = []; scene = []
    for run, short in [('ba1_B0_LoD2_nonormal', 'ba1'), ('ba2_B0_LoD2_noreset', 'ba2')]:
        for it in MESH_ITS:
            f = A3O/'gtj/scenes/B0_b10__LoD2/distances'/f'{short}_{it}.npz'
            if not f.exists(): continue
            rs = loadz(f, ['row_s'])['row_s']; tau = loadz(GT/'scenes/B0_b10__LoD2/rows.npz', ['row_tau_m'])['row_tau_m']
            for p in ['visible_low', 'visible_high', 'visible_side']:
                P = place_points(p); v = rs[P['point_id']]; comp.append(dict(run=run, iteration=int(it), place=p, completeness_pct=100*float((np.isfinite(v) & (np.abs(v) <= tau[P['point_id']])).mean())))
            scene += [dict(run=run, iteration=int(it), **r) for r in scene_rows(A3O/'meshes'/f'B0_b10__LoD2__{short}_{it}/score.json', run)]
    for it in MESH_ITS:   # record run (TRAINLOG meshes; 12000 = the 2.3 mesh of this addendum)
        f = next((q for q in [TLC/'gtj/scenes/B0_b10__LoD2/distances'/f'tl_{it}.npz', A3O/'gtj/scenes/B0_b10__LoD2/distances'/f'tl_{it}.npz'] if q.exists()), TLC/'gtj/scenes/B0_b10__LoD2/distances'/f'tl_{it}.npz')
        if f.exists():
            rs = loadz(f, ['row_s'])['row_s']; tau = loadz(GT/'scenes/B0_b10__LoD2/rows.npz', ['row_tau_m'])['row_tau_m']
            for p in ['visible_low', 'visible_high', 'visible_side']:
                P = place_points(p); v = rs[P['point_id']]; comp.append(dict(run='tl_B0_b10_LoD2_s0', iteration=int(it), place=p, completeness_pct=100*float((np.isfinite(v) & (np.abs(v) <= tau[P['point_id']])).mean())))
        sj = TLC/'meshes'/f'tl_{it}/score.json'
        if not sj.exists(): sj = A3O/'meshes'/f'B0_b10__LoD2__tl_{it}/score.json'
        scene += [dict(run='tl_B0_b10_LoD2_s0', iteration=int(it), **r) for r in scene_rows(sj, 'record')]
    ref = a11_ref('B0_b10__LoD2'); a = np.load(GT/'addendum11/final_data/B0_b10__LoD2.npz'); w = a['reference__FINALTRAIN_30000__within_tau1'].astype(bool); a.close()
    pid_pos = {int(x): i for i, x in enumerate(ref['point_id'])}
    for p in ['visible_low', 'visible_high', 'visible_side']:
        P = place_points(p); ii = np.array([pid_pos[int(x)] for x in P['point_id']]); comp.append(dict(run='FINALTRAIN_ft_LoD2_s0 (original)', iteration=30000, place=p, completeness_pct=100*float(w[ii].mean())))
    with open('/repo/docs/experiments/phd/main_gtjudge_v1/tables/addendum11/full_final.csv') as f:
        for x in csv.DictReader(f):
            if x['site'] == 'B0_b10' and x['prior'] in ('LoD2', 'ALS') and x['method'] == 'FINALTRAIN_30000' and x['surface'] in ('all', 'wall', 'roof') and x['case_id'] in ('all', '0', '1', '2', '3', '4'):
                scene.append(dict(run=f"FINALTRAIN_ft_{x['prior']}_s0 (original)", iteration=30000, source='GTJUDGE addendum11 full_final', surface=x['surface'], case_id=x['case_id'], n_gt=int(x['n_gt']),
                                  completeness_pct=float(x['completeness_pct']), accuracy_pct=float(x['accuracy_pct']) if x['accuracy_pct'] else None, result_n=int(x['result_n']) if x['result_n'] else None))
    scene += [dict(run='ba3_B0_ALS_record', iteration=30000, **r) for r in scene_rows(A3O/'meshes/B0_b10__ALS__ba3_30000/score.json', 'ba3')]
    ctable('ba_visible_wall_completeness', comp); ctable('ba_scene_values', scene); print('BA_TABLES', len(comp), len(scene), flush=True)

def figures():
    plt = korean_plt(); GA = A3O/'ga'; c = ccfg()['work_ga']
    from a3_ga_out import all_rows
    rows = {r: all_rows([r]) for r in ['tl_B0_b10_LoD2_s0', 'ba1_B0_LoD2_nonormal', 'ba2_B0_LoD2_noreset'] if (GA/f'{r}.json').exists()}
    comp = json.loads((A3D/'tables/ba_visible_wall_completeness.json').read_text())['rows'] if (A3D/'tables/ba_visible_wall_completeness.json').exists() else []
    for place in ['visible_low', 'visible_high', 'south_wall']:
        panels = [('bound_per_m2', '목표면에 묶인 가우시안 (참값 1 m²당)'), ('bound_op_ge05_pct', '그중 불투명도 0.5 이상 (%)'), ('front_op_per_m2', '목표면 앞 0.2~3 m 불투명도 합 (참값 1 m²당)'), ('back_op_per_m2', '목표면 뒤 0.2~3 m 불투명도 합 (참값 1 m²당)'), ('completeness_pct', '완전성 (%)')]
        fig, axs = plt.subplots(len(panels), 1, figsize=(10, 13), dpi=110, sharex=True)
        for ax, (k, lab) in zip(axs, panels):
            for run, col, lw, nm in [('tl_B0_b10_LoD2_s0', '#95A5A6', 1., '기록 판'), ('ba1_B0_LoD2_nonormal', '#C0392B', 1.5, '바-1 법선 항 없음'), ('ba2_B0_LoD2_noreset', '#1F5FD6', 1.5, '바-2 7,000회 뒤 재설정 없음')]:
                q = sorted([r for r in rows.get(run, []) if r['place'] == place], key=lambda r: (r['iteration'], 0 if r['pre_reset'] else 1))
                if k == 'completeness_pct' and place != 'south_wall':
                    q2 = sorted([r for r in comp if r['run'] == run and r['place'] == place], key=lambda r: r['iteration'])
                    x = [r['iteration'] for r in q2]; y = [r['completeness_pct'] for r in q2]
                    if run == 'tl_B0_b10_LoD2_s0': x, y = [r['iteration'] for r in q if r.get(k) is not None], [r[k] for r in q if r.get(k) is not None]
                else: x = [r['iteration'] for r in q if r.get(k) is not None]; y = [r[k] for r in q if r.get(k) is not None]
                ax.plot(x, y, color=col, lw=lw, marker='o' if k == 'completeness_pct' else None, ms=3, label=nm)
            for it in c['curve_lines']['opacity_reset']: ax.axvline(it, color='#2C3E50', ls=':', lw=.8)
            ax.axvline(7000, color='#16A085', ls='--', lw=.9); ax.axvline(15000, color='#7D3C98', ls='--', lw=.9); ax.set_ylabel(lab, fontsize=8); ax.grid(alpha=.25)
        axs[0].legend(fontsize=8); axs[-1].set_xlabel('반복 수 (점선: 기록 판의 재설정 3,000·6,000·9,000·12,000 / 초록 7,000 / 보라 15,000)', fontsize=8); axs[0].set_title(PLACE_KO[place], fontsize=10)
        fig.tight_layout(); p = A3D/'figures'/f'ba_curve_{place}.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
        dump(p.with_suffix('.json'), dict(at=now(), figure=p.name, place=place, sources=[str(GA/f'{r}.json') for r in rows], scientific_verdict=None))
    print('BA_FIGURES', flush=True)

if __name__ == '__main__':
    {'annex': annex, 'tables': tables, 'figures': figures}[sys.argv[1]]()
