"""Quick-look maps for the analyst (not a deliverable): whole-domain difference maps
with LoD2 footprints, R boxes and R1 zones, to locate change areas before the
figure step.  Reads s1/s2 outputs only.  scientific_verdict: null."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

out = Path(sys.argv[1])
cfg = json.loads(Path(sys.argv[2]).read_text())
D = np.load(out / 'derived.npz')
regs = json.loads((out / 'regions.json').read_text())
g = cfg['grid']
ext = [g['e_min'], g['e_max'], g['n_min'], g['n_max']]
z08 = [[690916.7665713681, 5336041.620778608], [690932.4994979611, 5336084.846639165], [690977.6047437588, 5336068.429672285], [690961.8718171659, 5336025.203811728]]
pairs = [('uls', 'als', 'ULS(2024) - ALS(2022)'), ('uls', 'lod', 'ULS(2024) - LoD2'), ('mvs', 'als', 'MVS(2024) - ALS(2022)'),
         ('mvs', 'lod', 'MVS(2024) - LoD2'), ('als', 'lod', 'ALS(2022) - LoD2')]
fig, axs = plt.subplots(2, 3, figsize=(30, 22))
for ax, (a, b, t) in zip(axs.ravel(), pairs):
    d = D[a].astype(float) - D[b].astype(float)
    im = ax.imshow(d, origin='lower', extent=ext, cmap='RdBu_r', vmin=-5, vmax=5, interpolation='nearest')
    ax.set_title(t, fontsize=18)
    for rid, r in regs.items():
        c = np.array(r['corners_epsg25832'] + [r['corners_epsg25832'][0]])
        ax.plot(c[:, 0], c[:, 1], 'k-', lw=1.5)
        ax.text(c[:, 0].mean(), c[:, 1].mean(), rid, fontsize=16, weight='bold')
    z = np.array(z08 + [z08[0]]); ax.plot(z[:, 0], z[:, 1], 'm-', lw=2)
    fp = D['fid'] >= 0
    ax.contour(np.linspace(ext[0], ext[1], fp.shape[1]), np.linspace(ext[2], ext[3], fp.shape[0]), fp.astype(float), [0.5], colors='g', linewidths=0.5)
    plt.colorbar(im, ax=ax, fraction=0.03)
ax = axs.ravel()[-1]
ax.imshow(D['rgb_uls'], origin='lower', extent=ext)
ax.set_title('ULS colours (mean RGB per cell)', fontsize=18)
for rid, r in regs.items():
    c = np.array(r['corners_epsg25832'] + [r['corners_epsg25832'][0]])
    ax.plot(c[:, 0], c[:, 1], 'y-', lw=1.5)
fig.tight_layout()
fig.savefig(out / 'qa' / 'quicklook_diffs.png', dpi=60)
print('ok')
