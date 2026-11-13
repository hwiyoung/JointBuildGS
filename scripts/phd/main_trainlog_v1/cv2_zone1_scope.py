"""(copied 2026-11-13 from the session scratchpad; ran read-only via launch.command with the scratchpad at /scratch; output in docs figures_concept_v2/zone1_find/scope_check_output.txt)
Read-only: the zone1_find overall counts, restricted to patches inside the building scope (footprint + 1 m, z >= ground + 0.3 m), where GT dense covers the surface."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
from cv2_frames import *
from scipy.spatial import cKDTree
S = Static(); sj = json.loads((V2/'static.json').read_text()); c = cfg()
G = loadz(Path(sj['gt']), ['xyz'])['xyz'].astype(float); T = cKDTree(G)
tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'normal', 'sigma', 'judge_region', 'region', 'centre', 'mvs_mean_m'])
valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0) & np.isin(tg['judge_region'], [0, 1, 2, 4])
iv = np.flatnonzero(valid); J = tg['judge_region']; mv = np.isfinite(tg['mvs_mean_m']); MP = tg['centre']+tg['normal']*np.where(mv, tg['mvs_mean_m'], 0.)[:, None]
dm = np.full(len(J), np.nan); q = iv[mv[iv]]; dm[q], _ = T.query(MP[q], k=1); dt = np.full(len(J), np.nan); dt[iv], _ = T.query(tg['target'][iv], k=1)
insc = np.zeros(len(J), bool); insc[iv] = scope_mask(tg['target'][iv], c); iw = np.nan_to_num(dm, nan=0) > .5
for name, m in [('all valid', valid), ('inside building scope', valid & insc), ('outside building scope', valid & ~insc)]:
    print(f'== {name}: {m.sum()}')
    for j in (0, 2, 1, 4):
        k = m & (J == j)
        if k.sum(): print(f'   {JN[j]:2s} n={k.sum():6d} image wrong {100*(k & iw).sum()/k.sum():5.1f} %  target <= tau {100*(k & (dt <= TAU)).sum()/k.sum():5.1f} %  target > 0.5 m {100*(k & (dt > .5)).sum()/k.sum():5.1f} %  | image wrong & target right {(k & iw & (dt <= TAU)).sum()}  image right & target > 0.5 m {(k & ~iw & (dt > .5)).sum()}  target-GT median {np.nanmedian(dt[k]):.2f} m')
