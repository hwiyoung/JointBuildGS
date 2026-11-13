"""(copied 2026-11-13 from the session scratchpad, where it ran read-only via launch.command with the scratchpad mounted at /scratch; output in docs figures_concept_v2/floater_check/ring_check_output.txt)
Read-only (prints only): what the far mesh pieces of this method are made of. No pass criteria."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
from cv2_frames import *
from shapely.geometry import shape
from scipy.spatial import cKDTree
c = cfg(); S = Static(); sj = json.loads((V2/'static.json').read_text()); g0 = S.ground
fp = shape(c['scope']['footprint']); fpb = shape(c['scope']['buffered_footprint']); cx, cy = fp.centroid.x, fp.centroid.y
print('xy buffer m', c['scope']['xy_buffer_m'], 'scope z above ground', round(c['scope']['z_min']-g0, 2), round(c['scope']['z_max']-g0, 2))
gt = loadz(Path(sj['gt'])); G = [v for k, v in gt.items() if getattr(v, 'ndim', 0) == 2 and v.shape[1] == 3][0].astype(float); T = cKDTree(G)
def area(V, F): a = V[F[:, 1]]-V[F[:, 0]]; b = V[F[:, 2]]-V[F[:, 0]]; return .5*np.linalg.norm(np.cross(a, b), axis=1)
for key in ['ours_7000', 'ours_15000', 'ours_30000']:
    m = loadz(V2/'meshcol'/f'{key}.npz'); V = m['V'].astype(float); F = m['F'].astype('i8'); C = m['C'].astype(float); nv = m['nview'].astype(float)
    ctr = V[F].mean(1); A = area(V, F); d, _ = T.query(ctr, k=1); far = d > 1.0
    infp = shapely.contains_xy(fp, ctr[:, 0], ctr[:, 1]); inb = shapely.contains_xy(fpb, ctr[:, 0], ctr[:, 1])
    out = far & ~infp; near = d <= .2
    print(f'== {key}: area {A.sum():,.0f} m2, >1 m from GT {100*A[far].sum()/A.sum():.1f} %; face centroids inside buffered footprint {100*inb.mean():.1f} %')
    if key != 'ours_30000': continue
    dist_edge = shapely.distance(fp.exterior, shapely.points(ctr[out, 0], ctr[out, 1]))
    ang = np.degrees(np.arctan2(ctr[out, 1]-cy, ctr[out, 0]-cx)) % 360
    print(f'   far-outside faces: distance outside the footprint edge median {np.median(dist_edge):.2f} m, 95 % {np.percentile(dist_edge, 95):.2f} m, max {dist_edge.max():.2f} m')
    print(f'   direction from footprint centre (deg, 0=+x east, 90=+y north): area share per 90 deg sector ' +
          ', '.join(f'{a0}-{a0+90}: {100*A[out][(ang >= a0) & (ang < a0+90)].sum()/A[out].sum():.0f} %' for a0 in (0, 90, 180, 270)))
    vf = nv[F].mean(1)
    print(f'   views per vertex (of 203) median: far-outside {np.median(vf[out]):.0f}, near GT (<=0.2 m) {np.median(vf[near]):.0f}')
    print(f'   colour brightness median: far-outside {np.median(C[F][out].mean((1, 2))):.0f}, near GT {np.median(C[F][near].mean((1, 2))):.0f}')
    dz = loadz(V2/'discs'/'ours_30000.npz'); P = dz['xyz'].astype(float); op = dz['opacity'].astype(float); TD = cKDTree(P)
    for name, sel in [('far-outside', out), ('near GT', near)]:
        idx = np.random.default_rng(0).choice(np.flatnonzero(sel), min(20000, sel.sum()), replace=False)
        nb = TD.query_ball_point(ctr[idx], r=.5); ops = np.concatenate([op[n] for n in nb if len(n)]) if any(len(n) for n in nb) else np.array([])
        cnt = np.array([len(n) for n in nb])
        print(f'   Gaussians within 0.5 m of {name} faces: faces with none {100*(cnt == 0).mean():.0f} %, opacity median {np.median(ops) if len(ops) else float("nan"):.2f}, share opacity < 0.1 {100*(ops < .1).mean() if len(ops) else float("nan"):.0f} %')
