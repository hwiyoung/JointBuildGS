"""Order 5 'more': share of record-run lost points within tau on every key-iteration mesh (when are they lost; c3 = a surface already exists at the wrong result-point location), and per saved state the
in-range counts of the check-3/6 groups (bound, released, background unbound). No culprit candidate exists (order 4.5), so all groups are listed."""
import glob
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from common import *
from te_check5 import model_of
from te_sets_tl import RUNS
KEYS = ['0', '100', '300', '1000', '2000', '3000_pre_reset', '3000', '5000', '7000', '10000', '15000', '20000', '30000']
def it_of(n): return int(n.split('_')[0])+(-.5 if n.endswith('pre_reset') else 0)
def main():
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    rows, pops = [], []
    fig, axes = plt.subplots(1, 4, figsize=(18, 4), sharey=True)
    for ax, run in zip(axes, RUNS):
        stem, arm = RUNS[run]
        for name in KEYS:
            if name == '30000':
                for cell in sorted(k for k, v in STEMS.items() if v == stem):
                    for setname in ['lost', 'control']:
                        z = loadz(O/'sets_tl'/f'{cell}_{arm}_{setname}.npz', ['trained_s_m', 'tau_m']); w = np.isfinite(z['trained_s_m']) & (np.abs(z['trained_s_m']) <= z['tau_m'])
                        if cell == 'c3': w = np.ones(len(w), bool)  # c3 points lie on the record 30000 mesh: a surface exists there by construction
                        rows.append(dict(run=run, name=name, iteration=30000, cell=cell, set=setname, n=len(w), within_tau_pct=100*float(w.mean()) if len(w) else None,
                                         note='definition (record 30000 mesh)' + ('; c3 = surface present at the result point' if cell == 'c3' else '')))
                continue
            j = json.loads((O/'curves'/f'{run}__{name}.json').read_text())
            for r in j['rows']: rows.append(dict(run=run, name=name, iteration=it_of(name), cell=r['cell'], set=r['set'], n=r['n'], within_tau_pct=r['within_tau_pct'], no_surface_pct=r['no_surface_pct']))
        for cell in sorted(set(r['cell'] for r in rows if r['run'] == run)):
            for setname, ls in [('lost', '-'), ('control', ':')]:
                rr = sorted([r for r in rows if r['run'] == run and r['cell'] == cell and r['set'] == setname], key=lambda r: r['iteration'])
                ax.plot([max(r['iteration'], 1) for r in rr], [r['within_tau_pct'] for r in rr], ls, marker='o', ms=3, label=f'{cell} {"잃은 점" if setname == "lost" else "대조 점"}')
        ax.set_xscale('log'); ax.set_title(run, fontsize=9); ax.set_xlabel('반복'); ax.legend(fontsize=7)
        m = model_of(run)
        for f in sorted(glob.glob(str(m/'trainlog/states/*.npz'))):
            nm = Path(f).stem; st = np.load(f); tag = st['target_tag']; ori = st['origin']
            pops.append(dict(run=run, state=nm, iteration=it_of(nm), in_range=len(tag), bound=int((tag == 1).sum()), released=int((tag == 2).sum()), background_unbound=int(((ori == 0) & (tag != 1)).sum()),
                             patch_lineage=int((ori == 1).sum())))
    axes[0].set_ylabel('주요 반복 메시에서 τ 안 (%)'); (D/'figures').mkdir(exist_ok=True); fig.savefig(D/'figures/check5_curves.png', dpi=180, bbox_inches='tight'); plt.close(fig)
    dump(D/'figures/check5_curves.json', dict(source='te/curves/<run>__<name>.json + sets_tl', rule='normal-line measure of the record-run lost/control points on each key-iteration mesh', scientific_verdict=None))
    table('check5_curves', rows); table('check5_group_counts_by_state', sorted(pops, key=lambda r: (r['run'], r['iteration']))); print('CURVES', len(rows), len(pops))
if __name__ == '__main__': main()
