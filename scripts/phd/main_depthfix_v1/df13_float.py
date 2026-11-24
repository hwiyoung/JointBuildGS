"""Order 5.2 floating surface (October definition: FLOATDIAG v3.1 §3.1, LOSSTRAIN mesh_score + FLOATDIAG recount.classes, unchanged rules), CPU.
Patches = LOSSTRAIN direct_stage1_v2/<stem>/evaluation.npz, in_eval & scoring_allowed & cell 0~3. z = first outer-to-inner hit on the run's base-extraction mesh
(from max(6, p_M + .5, p_G + .5) to min(−6, p_M − .5, p_G − .5)); side 0 prior / 1 MVS / 2 neither within 3σ; floating = hit, |z − p_G| > τ, side 2, z > p_G + τ.
value = floating area share. usage: df13_float.py <stem> <run> [...]   writes /df/float/<stem>__<run>.json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import open3d as o3d
LT = PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'

def main(stem, *runs):
    root = LT/'direct_stage1_v2'/stem
    with np.load(root/'evaluation.npz') as e_, np.load(root/'values.npz') as v_:
        e = {k: e_[k] for k in ['area', 'in_eval', 'cell', 'scoring_allowed', 'p_gt', 'p_mvs', 'tau', 'centre', 'normal']}; e.update({k: v_[k].astype('f8') for k in ['sigma_prior', 'sigma_mvs']})
    c, n = e['centre'], e['normal']; D = np.nan_to_num(e['p_mvs'], nan=0.); G = np.nan_to_num(e['p_gt'], nan=0.)
    start = np.maximum(6., np.maximum(D + .5, G + .5)); end = np.minimum(-6., np.minimum(D - .5, G - .5))
    ids = np.flatnonzero(e['in_eval'] & e['scoring_allowed']); all03 = e['in_eval'] & e['scoring_allowed'] & (e['cell'] >= 0) & (e['cell'] <= 3)
    for run in runs:
        mesh = O/'gtj/meshes'/f'{stem}__df_{run}_base'/'final.ply'
        if not mesh.exists(): print('NO_MESH', stem, run, flush=True); continue
        m = o3d.io.read_triangle_mesh(str(mesh)); sc = o3d.t.geometry.RaycastingScene(nthreads=8); sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m)); del m
        z = np.full(len(c), np.nan)
        for off in range(0, len(ids), 50000):
            q = ids[off:off+50000]; rays = np.c_[c[q] + start[q, None]*n[q], -n[q]].astype('f4')
            hit = sc.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy().astype('f8'); ok = np.isfinite(hit) & (hit <= start[q] - end[q]); z[q[ok]] = start[q[ok]] - hit[ok]
        dp = np.abs(z)/e['sigma_prior']; dm = np.abs(z - e['p_mvs'])/e['sigma_mvs']
        side = np.where(~np.isfinite(z), 3, np.where((dp <= 3) & ((dm > 3) | ~np.isfinite(dm) | (dp <= dm)), 0, np.where(dm <= 3, 1, 2)))
        good = np.isfinite(z); within = good & (np.abs(z - e['p_gt']) <= e['tau']); floating = good & ~within & (side == 2) & (z > e['p_gt'] + e['tau'])
        A = e['area']; r = dict(stem=stem, run=run, patches=int(all03.sum()), area_m2=float(A[all03].sum()), floating_area_m2=float(A[all03 & floating].sum()),
                                floating_pct=100*float(A[all03 & floating].sum()/A[all03].sum()), within_tau_pct=100*float(A[all03 & within].sum()/A[all03].sum()),
                                no_surface_pct=100*float(A[all03 & ~good].sum()/A[all03].sum()), rule=__doc__, scientific_verdict=None)
        dump(O/'float'/f'{stem}__{run}.json', r); print('FLOAT', stem, run, round(r['floating_pct'], 3), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
