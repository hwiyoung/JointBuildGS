"""inspection: buildings, roof types and wall-normal spread of LoD2 patches inside each scene (for choosing figure places; no GT, no results)."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
jp = loadz(JP/'patch_LoD2.npz', ['centre', 'normal', 'kind', 'building', 'roof_type', 'area'])
for stem in ['R1rep_b10__LoD2', 'B173nb_b10__LoD2']:
    pi = loadz(O/'patchinfo'/f'{stem}.npz'); t = loadz(O/'families/base/targets'/f'{stem}.npz', ['centre', 'in_eval'])
    r = pi['row'][pi['joined'] & t['in_eval']]; b = jp['building'][r]
    print(stem, 'box', t['centre'][t['in_eval']].min(0).round(1), t['centre'][t['in_eval']].max(0).round(1))
    for name in np.unique(b):
        m = r[b == name]; k = jp['kind'][m]; rt = np.unique(jp['roof_type'][m[k == 1]], return_counts=True)
        wn = jp['normal'][m[k == 2]][:, :2]; ang = np.degrees(np.arctan2(wn[:, 1], wn[:, 0])) if len(wn) else np.zeros(0)
        nb = len(np.unique(np.round(ang/5))) if len(ang) else 0
        c = jp['centre'][m]
        print(f'  {name} patches {len(m)} roof {dict(zip(*[x.tolist() for x in rt]))} wall_dirs_5deg {nb} xy {c[:,0].min():.1f}-{c[:,0].max():.1f} {c[:,1].min():.1f}-{c[:,1].max():.1f} z {c[:,2].min():.1f}-{c[:,2].max():.1f}')
