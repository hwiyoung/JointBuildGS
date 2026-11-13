"""(copied 2026-11-13 from the session scratchpad, where it ran read-only via launch.command with the scratchpad mounted at /scratch; output in docs figures_concept_v2/floater_check/ring_check_output.txt)
Purpose: answer the user's question; no pass criteria, nothing written."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
from cv2_frames import *
from shapely.geometry import shape
from scipy.spatial import cKDTree
c = cfg(); S = Static(); sj = json.loads((V2/'static.json').read_text()); g0 = S.ground
print('scope keys', list(c['scope'].keys()))
fp_buf = shape(c['scope']['buffered_footprint']); print('buffered footprint area m2', round(fp_buf.area), 'z', c['scope']['z_min'], c['scope']['z_max'])
fp = shape(c['scope']['footprint']) if 'footprint' in c['scope'] else None
if fp is not None: print('footprint area m2', round(fp.area), 'buffer m', c['scope'].get('xy_buffer_m'), 'ground_z', c['scope'].get('ground_z'))
gt = loadz(Path(sj['gt'].replace('/art/', str(ART)+'/')) if not Path(sj['gt']).exists() else Path(sj['gt']))
G = [v for k, v in gt.items() if getattr(v, 'ndim', 0) == 2 and v.shape[1] == 3][0].astype(float); print('GT keys', list(gt.keys())); print('GT points', len(G), 'height above ground 0/2/50/98/100 %', np.round(np.percentile(G[:, 2]-g0, [0, 2, 50, 98, 100]), 2).tolist())
T = cKDTree(G)
def area(V, F): a = V[F[:, 1]]-V[F[:, 0]]; b = V[F[:, 2]]-V[F[:, 0]]; return .5*np.linalg.norm(np.cross(a, b), axis=1)
for key, fam, root in [('ours_30000', 'tl_30000', O/'gtj/scenes'/STEM/'distances'), ('nojudge_30000', 'cmp_nojudge_30000_v203', V2/'gtj/scenes'/STEM/'distances'), ('2dgs_30000', 'cmp_2dgs_30000_v203', V2/'gtj/scenes'/STEM/'distances')]:
    m = loadz(V2/'meshcol'/f'{key}.npz'); V = m['V'].astype(float); F = m['F'].astype('i8'); C = m['C'].astype(float)
    ctr = V[F].mean(1); A = area(V, F); d, _ = T.query(ctr, k=1); h = ctr[:, 2]-g0; bright = C[F].mean((1, 2))
    infp = shapely.contains_xy(fp, ctr[:, 0], ctr[:, 1]) if fp is not None else np.ones(len(F), bool)
    far = d > 1.0; tot = A.sum()
    print(f'== {key}: mesh area {tot:,.0f} m2; >1 m from GT {A[far].sum():,.0f} m2 ({100*A[far].sum()/tot:.1f} %)')
    for name, sel in [('far, outside footprint', far & ~infp), ('far, inside footprint', far & infp)]:
        if not sel.any(): print(f'   {name}: 0'); continue
        hs = h[sel]; w = A[sel]
        print(f'   {name}: {w.sum():,.0f} m2; height above ground: <1 m {w[hs < 1].sum():,.0f}, 1-5 m {w[(hs >= 1) & (hs < 5)].sum():,.0f}, 5-12 m {w[(hs >= 5) & (hs < 12)].sum():,.0f}, >=12 m {w[hs >= 12].sum():,.0f} m2;'
              f' brightness (0-255) area-weighted median {np.median(np.repeat(bright[sel], np.maximum(1, (w/w.mean()).astype(int)))):.0f}; distance to GT median {np.median(d[sel]):.1f} m')
    dark = bright < 50; print(f'   dark faces (mean RGB < 50): {A[dark].sum():,.0f} m2, of which >1 m from GT {100*A[dark & far].sum()/max(A[dark].sum(), 1e-9):.0f} %, outside footprint {100*A[dark & ~infp].sum()/max(A[dark].sum(), 1e-9):.0f} %')
    # scoring: accuracy samples
    ob = loadz(root/f'{fam}_observed.npz'); xyz = loadz(root/f'{fam}_samples.npz', ['xyz'])['xyz'].astype(float); tau = loadz(root/f'{fam}.npz', ['sample_tau'])['sample_tau']
    el = ob['observed'] & ~ob['steep']; ds, _ = T.query(xyz, k=1); fs = ds > 1.0; win = np.abs(ob['sample_s']) <= tau
    print(f'   accuracy samples {len(xyz):,}; >1 m from GT {fs.sum():,} ({100*fs.mean():.1f} %); of those counted in accuracy (observed & not steep) {100*(el & fs).sum()/max(fs.sum(), 1):.1f} %;'
          f' accuracy {100*(el & win).sum()/el.sum():.1f} % (n {el.sum():,}); accuracy if far samples were not there {100*(el & win & ~fs).sum()/(el & ~fs).sum():.1f} %')
