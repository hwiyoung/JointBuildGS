"""Concept figure (2026-11-12): the meshes seen from the same real training camera as concept_prep.py (train1 = DJI_20241217091247_0146_D). CPU, no training.
Pinhole ray cast (Open3D RaycastingScene) through every pixel centre of the 1024 x 741 camera (pixel i centre at u = i, the renderer's convention); saves per pixel
the z-depth along the camera axis, the world normal of the hit face and the signed distance of that face to the GT dense reference (colouring only).
  this run (part A): analysis/mesh_<state>.npz (gtj pipeline final.ply, building scope, vertex_error_m already computed by frames.prep_mesh)
  part B, the same mesh rule (TSDF of the 203 real views, voxel 0.05 m, trunc 0.25 m, the shared-edge component cleanup) from main_rescore_v1:
    image-only 2DGS = meshes/B173nb_b10__LoD2__2DGS_30000/final.ply (the image-only run has no prior; its ALS train.json reuses the same TSDF, sha 177e468a)
    GeoGS ALS       = meshes/B173nb_b10__ALS__GeoGS_30000/final.ply
  both cropped to the same building scope (derive_states.scope_mask), signed distance as frames.prep_mesh (GT dense, z range +-1 m, normal up).
scientific_verdict: null"""
import sys, time
from common import *
from derive_states import scope_mask
from scipy.spatial import cKDTree
import open3d as o3d
OUTC = O/'concept'; A = O/'analysis'; RSM = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1/meshes'
OURS = ['0', '300', '1000', '2000', '10000', '30000']
COMP = {'imgonly_2dgs': RSM/'B173nb_b10__LoD2__2DGS_30000/final.ply', 'geogs_als': RSM/'B173nb_b10__ALS__GeoGS_30000/final.ply'}

def cast(V, F, K, W2C, W, H):
    sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(V.astype('f4')); tm.triangle.indices = o3d.core.Tensor(F.astype('i4')); sc.add_triangles(tm)
    R = W2C[:3, :3]; t = W2C[:3, 3]; C = -R.T@t; u, v = np.meshgrid(np.arange(W, dtype=float), np.arange(H, dtype=float))
    dc = np.stack([(u-K[0, 2])/K[0, 0], (v-K[1, 2])/K[1, 1], np.ones_like(u)], -1); d = dc@R   # world direction whose camera-z component is 1, so t_hit = z-depth
    r = sc.cast_rays(o3d.core.Tensor(np.concatenate([np.broadcast_to(C, d.shape), d], -1).reshape(-1, 6).astype('f4')))
    th = r['t_hit'].numpy().reshape(H, W); hit = np.isfinite(th); pid = r['primitive_ids'].numpy().reshape(H, W).astype('i8'); nrm = r['primitive_normals'].numpy().reshape(H, W, 3)
    return hit, np.where(hit, th, np.nan).astype('f4'), pid, nrm

def main():
    c = cfg(); z = loadz(OUTC/'inputs.npz', ['K', 'W2C', 'W', 'H']); K, W2C, W, H = z['K'].astype(float), z['W2C'].astype(float), int(z['W']), int(z['H']); rec = dict(at=now(), rule=__doc__, meshes={}, scientific_verdict=None)
    g = loadz(GT/'reference'/SITE/'dense.npz', ['xyz', 'normal']); gm = scope_mask(g['xyz'].astype(float), dict(scope=dict(c['scope'], z_min=c['scope']['z_min']-1, z_max=c['scope']['z_max']+1)))
    gx = g['xyz'][gm].astype(float); gn = g['normal'][gm].astype(float); gn[gn[:, 2] < 0] *= -1; gtree = cKDTree(gx)
    jobs = [(f'ours_{n}', None, n) for n in OURS]+[(k, p, None) for k, p in COMP.items()]
    for key, ply, n in jobs:
        if (OUTC/f'mesh_{key}.npz').exists(): print('SKIP', key, flush=True); continue
        t0 = time.monotonic()
        if n is not None:
            m = loadz(A/f'mesh_{n}.npz', ['vertices', 'faces', 'vertex_error_m']); V = m['vertices'].astype(float); F = m['faces'].astype('i8'); verr = m['vertex_error_m'].astype(float); src = str(A/f'mesh_{n}.npz')
        else:
            mesh = o3d.io.read_triangle_mesh(str(ply)); V = np.asarray(mesh.vertices, float); F = np.asarray(mesh.triangles).astype('i8'); del mesh
            keep = scope_mask(V[F].mean(1), c); F = F[keep]; used = np.unique(F); remap = np.full(len(V), -1); remap[used] = np.arange(len(used)); V = V[used]; F = remap[F]; verr = None; src = str(ply)
        hit, dep, pid, nrm = cast(V, F, K, W2C, W, H); fi = np.unique(pid[hit])
        if verr is None:
            vi = np.unique(F[fi]); dist, idx = gtree.query(V[vi], workers=8); e = np.full(len(V), np.nan); e[vi] = np.sign(((V[vi]-gx[idx])*gn[idx]).sum(1))*dist; verr = e
        ferr = np.full(len(F), np.nan, 'f4'); ferr[fi] = verr[F[fi]].mean(1); err = np.where(hit, ferr[pid.clip(0, len(F)-1)], np.nan).astype('f4')
        savez(OUTC/f'mesh_{key}.npz', hit=hit, depth=dep, normal=nrm.astype('f2'), error_m=err)
        rec['meshes'][key] = dict(source=src, faces_in_scope=int(len(F)), hit_pixels=int(hit.sum()), seconds=round(time.monotonic()-t0, 1)); print('MESH', key, rec['meshes'][key], flush=True)
    old = OUTC/'concept_mesh.json'
    if old.exists(): prev = json.loads(old.read_text()); prev['meshes'].update(rec['meshes']); rec = dict(prev, at_update=rec['at'])
    dump(OUTC/'concept_mesh.json', rec); print('DONE', flush=True)

if __name__ == '__main__': main()
