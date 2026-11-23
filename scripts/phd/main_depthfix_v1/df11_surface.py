"""Order 5.2 (two-layer patches) and 5.3 (판 5~8: where the result surface sits on the split patches), CPU. usage: df11_surface.py <stem> <run> [...]
Split patches = switch 라 target patches of the stem (same set for every arm). For every run (also 판 0 / 판 1, for comparison):
  result surface height h_r = first hit of a ray from centre + (max(h_P, h_M) + 3 m)·n towards −n on the base-extraction mesh (final.ply), within 20 m;
  class: within τ of the prior face (h_P) / within τ of the image face (h_M) (both -> prior face first, as WRONGTARGET 3.4) / between the faces / outside both / no surface;
  area shares per c bin (0~0.2, 0.2~0.5, 0.5~1; c of κ assumed, 판 7 κ 1).
  two-layer patch: at 30,000 iterations at least one Gaussian with opacity >= 0.5 inside the patch disc (tangential distance <= radius) within τ of the prior face
  AND one within τ of the image face. τ = the patch kind's τ (roof / wall of the scene).
writes /df/surface/<stem>__<run>.json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import open3d as o3d
from plyfile import PlyData
from scipy.spatial import cKDTree
BINS = [(0, .2, '0~0.2'), (.2, .5, '0.2~0.5'), (.5, 1.0001, '0.5~1')]; CLS = ['사전 정보 면', '영상 깊이 면', '두 면 사이', '두 면 바깥', '면 없음']

def main(stem, *runs):
    pi = loadz(O/'patchinfo'/f'{stem}.npz'); tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['centre', 'normal', 'area', 'prior_height_m', 'mvs_mean_m', 'in_eval'])
    sp = np.flatnonzero(pi['split'] & tb['in_eval']); n = tb['normal'][sp]/np.linalg.norm(tb['normal'][sp], axis=1)[:, None]; c0 = tb['centre'][sp]
    hP, hM = tb['prior_height_m'][sp], tb['mvs_mean_m'][sp]; tau = pi['tau'][sp]; A = tb['area'][sp]; r = np.sqrt(A/np.pi); typ0 = pi['type'][sp]
    for run in runs:
        key = f'{stem}__df_{run}_base'; mesh = O/'gtj/meshes'/key/'final.ply'
        if not mesh.exists(): print('NO_MESH', key, flush=True); continue
        arm = run.rsplit('_s', 1)[0]; cc = (pi['c_k1'] if arm == 'p7' else pi['c_kA'])[sp]
        m = o3d.t.io.read_triangle_mesh(str(mesh)); sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(m)
        top = np.maximum(hP, hM) + 3.; org = c0 + top[:, None]*n
        rays = o3d.core.Tensor(np.c_[org, -n].astype('f4')); hit = sc.cast_rays(rays)['t_hit'].numpy().astype('f8')
        hr = np.where(np.isfinite(hit) & (hit <= 20), top - hit, np.nan)
        lo_, hi_ = np.minimum(hP, hM), np.maximum(hP, hM)
        cls = np.full(len(sp), 4); cls[np.isfinite(hr)] = 3
        cls[np.isfinite(hr) & (hr > lo_ + tau) & (hr < hi_ - tau)] = 2
        cls[np.abs(hr - hM) <= tau] = 1; cls[np.abs(hr - hP) <= tau] = 0
        rows = []
        for a, b, lab in BINS + [(0, 1.0001, '모두')]:
            for t_, tn in [(None, '모두'), (2, '판 0 되돌림'), (1, '판 0 영상 깊이')]:
                mk = (cc >= a) & (cc < b) & (True if t_ is None else (typ0 == t_))
                rows.append(dict(c_bin=lab, p0_type=tn, patches=int(mk.sum()), area_m2=float(A[mk].sum()), **{f'{k}_area_pct': (100*float(A[mk & (cls == i)].sum()/A[mk].sum()) if mk.any() else None) for i, k in enumerate(CLS)}))
        # two-layer patches
        ply = O/'runs'/stem/run/'model/point_cloud/iteration_30000/point_cloud.ply'; two = None
        if ply.exists():
            v = PlyData.read(str(ply))['vertex']; X = np.c_[v['x'], v['y'], v['z']].astype('f8'); op = 1/(1 + np.exp(-np.asarray(v['opacity'], 'f8'))); X = X[op >= .5]
            tree = cKDTree(X); mid = c0 + ((hP + hM)/2)[:, None]*n; rad = np.sqrt(r**2 + ((hi_ - lo_)/2 + tau)**2)
            lists = tree.query_ball_point(mid, rad, workers=16); twoL = np.zeros(len(sp), bool)
            for i, L in enumerate(lists):
                if not L: continue
                d = X[L] - c0[i]; h = d@n[i]; tang = np.linalg.norm(d - h[:, None]*n[i], axis=1); ok = tang <= r[i]
                twoL[i] = bool((ok & (np.abs(h - hP[i]) <= tau[i])).any() and (ok & (np.abs(h - hM[i]) <= tau[i])).any())
            two = dict(patches=int(len(sp)), two_layer_patches=int(twoL.sum()), two_layer_area_pct=100*float(A[twoL].sum()/A.sum()), gaussians_opacity_ge_05=int(len(X)))
        dump(O/'surface'/f'{stem}__{run}.json', dict(stem=stem, run=run, split_patches_in_eval=int(len(sp)), classes=rows, two_layer=two,
             rule=__doc__, scientific_verdict=None)); print('SURFACE', stem, run, json.dumps(two), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
