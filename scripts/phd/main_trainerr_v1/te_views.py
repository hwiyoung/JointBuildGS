"""Stage 2 (CPU): seen views of every set point, target-map values at its pixel, and same-ray reference / mesh depths.
argv: <stem> <arm> [trained_mesh_ply] [tag]
Points = lost + control of every cell of the stem (order: cells sorted, lost then control). Output views/<stem>__<arm>[__tag].npz with one row
per (point, seen view): point, view, u, v (exact projection), px, py, z (camera z of the point), facing (<=30 deg), zbuf (reference z-buffer at
the pixel), owner/weight/tdepth/tsigma (the arm's stored target maps), mesh_z (trained-mesh first hit along the pixel ray through the point, camera z).
Seen: c1/c2 reference points z - zbuf <= 0.05 m (reference dense z-buffer; GT mesh not in the repository);
c3 result points: trained-mesh ray from the camera centre first hit >= |X - C| - 0.05 m."""
import open3d as o3d
from common import *

def point_table(stem, arm, sets_root=None):
    sets_root = sets_root or O/'sets'; cells = sorted(k for k, v in STEMS.items() if v == stem); parts = []
    for cell in cells:
        for si, setname in enumerate(['lost', 'control']):
            z = loadz(sets_root/f'{cell}_{arm}_{setname}.npz')
            parts.append(dict(cell=np.full(len(z['point_id']), int(cell[1]), 'i1'), set=np.full(len(z['point_id']), si, 'i1'), row=np.arange(len(z['point_id'])),
                              xyz=z['xyz'], normal=z['normal'], result=np.full(len(z['point_id']), cell == 'c3'), tau=z['tau_m']))
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}

def zbuffer(Pc, z, K, W, H):
    u = np.floor(K[0, 0]*Pc[:, 0]/z+K[0, 2]+.5).astype(np.int64); v = np.floor(K[1, 1]*Pc[:, 1]/z+K[1, 2]+.5).astype(np.int64)
    ok = (z > 0) & (u >= 0) & (v >= 0) & (u < W) & (v < H); lin = v[ok]*W+u[ok]; zz = z[ok]
    buf = np.full(W*H, np.inf, np.float32); order = np.lexsort((zz, lin)); lin, zz = lin[order], zz[order]
    first = np.r_[True, lin[1:] != lin[:-1]]; buf[lin[first]] = zz[first]; return buf.reshape(H, W)

def main(stem, arms='own,gt', meshes='', tag='', sets_root=''):
    """arms: comma list; meshes: comma list of trained meshes (default the arm's stored trained mesh); one z-buffer per view shared by the arms."""
    arms = arms.split(','); meshes = meshes.split(',') if meshes else [''] * len(arms); site, prior = stem.split('__')
    t = Timer(f'views_{stem}_{"_".join(arms)}{"_"+tag if tag else ""}')
    views = [v for v in json.loads((GT/'views'/f'{site}.json').read_text())['views'] if not v['virtual']]
    ref = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype(np.float64); cos30 = np.cos(np.radians(30.)); A = []
    for arm, mesh in zip(arms, meshes):
        ap = arm_paths(stem, arm); pts = point_table(stem, arm, Path(sets_root) if sets_root else None); mesh = Path(mesh) if mesh else ap['trained_mesh']
        m = o3d.io.read_triangle_mesh(str(mesh)); sc = o3d.t.geometry.RaycastingScene(nthreads=16); sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m)); del m
        A.append(dict(arm=arm, ap=ap, X=pts['xyz'], N=pts['normal']/np.linalg.norm(pts['normal'], axis=1)[:, None], result=pts['result'], mesh=mesh, scene=sc,
                      index=json.loads((ap['target_dir']/'maps/index.json').read_text())['views'], inimg=np.zeros(len(pts['xyz']), np.int32), kmax=0.,
                      out={k: [] for k in ['point', 'view', 'u', 'v', 'px', 'py', 'z', 'facing', 'zbuf', 'owner', 'weight', 'tdepth', 'tsigma', 'mesh_z']}))
    for j, vw in enumerate(views):
        K = np.asarray(vw['K'], float); E = np.asarray(vw['W2C'], float); W, H = vw['width'], vw['height']; C = -E[:3, :3].T@E[:3, 3]
        Rc = ref@E[:3, :3].T+E[:3, 3]; ZB = zbuffer(Rc, Rc[:, 2], K, W, H); del Rc
        for a in A:
            X, N, result, out = a['X'], a['N'], a['result'], a['out']; mi = a['index'][vw['name']]
            a['kmax'] = max(a['kmax'], float(np.abs(np.asarray(mi['K'])-K).max()), float(np.abs(np.asarray(mi['W2C'])-E).max()))
            Pc = X@E[:3, :3].T+E[:3, 3]; z = Pc[:, 2]
            with np.errstate(divide='ignore', invalid='ignore'):
                u = K[0, 0]*Pc[:, 0]/z+K[0, 2]; v = K[1, 1]*Pc[:, 1]/z+K[1, 2]
            px = np.floor(np.nan_to_num(u, nan=-1e9)+.5).astype(np.int64); py = np.floor(np.nan_to_num(v, nan=-1e9)+.5).astype(np.int64)
            ins = (z > 0) & (px >= 0) & (py >= 0) & (px < W) & (py < H); ii = np.flatnonzero(ins); a['inimg'][ii] += 1
            if not len(ii): continue
            zb = ZB[py[ii], px[ii]]; d = X[ii]-C; dist = np.linalg.norm(d, axis=1); dirn = d/dist[:, None]
            rays = o3d.core.Tensor(np.c_[np.broadcast_to(C, (len(ii), 3)), dirn].astype(np.float32)); th = a['scene'].cast_rays(rays)['t_hit'].numpy().astype(np.float64)
            mz = np.where(np.isfinite(th), th*(dirn@E[2, :3]), np.nan)
            seen = np.where(result[ii], ~np.isfinite(th) | (th >= dist-.05), (z[ii]-zb) <= .05); k = ii[seen]
            if not len(k): continue
            with np.load(a['ap']['target_dir']/'maps'/mi['file']) as mp: own, wt, td, ts = (mp[q][py[k], px[k]] for q in ['owner', 'weight', 'depth', 'sigma'])
            fac = np.abs(np.einsum('ij,ij->i', -dirn[seen], N[k])) >= cos30
            for key, val in [('point', k), ('view', np.full(len(k), j)), ('u', u[k]), ('v', v[k]), ('px', px[k]), ('py', py[k]), ('z', z[k]), ('facing', fac), ('zbuf', zb[seen]),
                             ('owner', own), ('weight', wt), ('tdepth', td), ('tsigma', ts), ('mesh_z', mz[seen])]: out[key].append(val)
        if j % 50 == 0: print('VIEW', j, len(views), flush=True)
    dt_ = dict(point='i4', view='i2', u='f4', v='f4', px='i2', py='i2', z='f4', facing='u1', zbuf='f4', owner='i4', weight='f4', tdepth='f4', tsigma='f4', mesh_z='f4')
    sec = t.done()
    for a in A:
        arr = {k: np.concatenate(v).astype(dt_[k]) for k, v in a['out'].items()}; name = f'{stem}__{a["arm"]}' + (f'__{tag}' if tag else '')
        savez(O/'views'/f'{name}.npz', **arr, in_image=a['inimg'], view_names=np.array([v['name'] for v in views]))
        dump(O/'views'/f'{name}.json', dict(at=now(), stem=stem, arm=a['arm'], points=len(a['X']), pairs=len(arr['point']), views=len(views), mesh=str(a['mesh']), mesh_sha256=sha(a['mesh']),
             sets_root=sets_root or str(O/'sets'), map_camera_max_abs_diff=a['kmax'], seen_rule=cfg()['visibility'], seconds_all_arms=sec, scientific_verdict=None))
        print('VIEWS_DONE', name, len(a['X']), len(arr['point']), a['kmax'], flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
