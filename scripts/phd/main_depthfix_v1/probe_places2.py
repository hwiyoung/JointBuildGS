"""inspection for figure places (prior LoD2 faces and scene image heights only; no GT, no results)."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
jp = loadz(JP/'patch_LoD2.npz', ['centre', 'normal', 'kind', 'building', 'face', 'area', 'surf'])
def scene(stem):
    pi = loadz(O/'patchinfo'/f'{stem}.npz'); t = loadz(O/'families/base/targets'/f'{stem}.npz', ['centre', 'normal', 'in_eval', 'mvs_mean_m', 'kind'])
    r = np.where(pi['joined'], pi['row'], 0); return pi, t, r
pi, t, r = scene('R1rep_b10__LoD2'); b = np.where(pi['joined'], jp['building'][r], '')
# R1 arched/ribbed roof 4906968: principal axes of roof patches, scene image surface height profile across the short axis
m = (b == 'DEBY_LOD2_4906968') & (t['kind'] == 1) & t['in_eval']; xy = t['centre'][m, :2]; c0 = xy.mean(0); U, S, Vt = np.linalg.svd(xy - c0, full_matrices=False)
z = t['centre'][m, 2] + np.where(np.isfinite(t['mvs_mean_m'][m]), t['mvs_mean_m'][m], np.nan)*t['normal'][m, 2]
for ax in [0, 1]:
    s = (xy - c0)@Vt[ax]; bins = np.arange(s.min(), s.max() + .5, .5); k = np.digitize(s, bins)
    prof = [np.nanmedian(z[k == i]) if (k == i).sum() > 5 else np.nan for i in range(1, len(bins))]
    print('R1 roof axis', ax, 'dir', Vt[ax].round(3), 'len', round(s.max()-s.min(), 1), 'profile(0.5 m)', np.round(prof, 2).tolist())
print('R1 roof centre', c0.round(2), 'faces', len(np.unique(jp['face'][r[m]])))
# R1 round building 4906975 walls: direction per wall patch, sorted around the building
m2 = (b == 'DEBY_LOD2_4906975') & (t['kind'] == 2) & t['in_eval']; n2 = t['normal'][m2, :2]; ang = np.degrees(np.arctan2(n2[:, 1], n2[:, 0])); xy2 = t['centre'][m2, :2]
for a in range(-180, 180, 30):
    q = (ang >= a) & (ang < a + 30)
    if q.any(): print('R1 wall dir', a, a+30, 'patches', int(q.sum()), 'xy mean', xy2[q].mean(0).round(1), 'faces', len(np.unique(jp['face'][r[m2][q]])))
f = jp['face'][r[m2]]; uf, cnt = np.unique(f, return_counts=True); print('R1 round wall faces', len(uf), 'median patches/face', np.median(cnt))
# faces with small area and adjacent direction change -> curved part: per face mean direction, area
fa = []
for q in uf:
    mm = f == q; fa.append((int(q), int(mm.sum()), float(np.degrees(np.arctan2(n2[mm, 1].mean(), n2[mm, 0].mean()))), xy2[mm].mean(0).round(1).tolist()))
fa.sort(key=lambda x: x[2]); print('R1 wall faces (id, patches, dir, xy):', fa)
pi, t, r = scene('B173nb_b10__LoD2'); b = np.where(pi['joined'], jp['building'][r], '')
m = (t['kind'] == 1) & t['in_eval'] & pi['joined']; f = jp['face'][r[m]]; uf = np.unique(f); rows = []
for q in uf:
    mm = f == q; a = float(jp['area'][r[m][mm]].sum()); zc = float(t['centre'][m][mm, 2].mean()); xy = t['centre'][m][mm, :2].mean(0)
    rows.append((int(q), b[m][mm][0][-8:], round(a, 1), round(zc, 2), xy.round(1).tolist()))
rows.sort(key=lambda x: x[2]); print('B173 roof faces (id, bld, area, z, xy):', rows)
