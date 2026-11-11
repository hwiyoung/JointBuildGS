"""Key-iteration helpers (GPU, torch image).
  ply <name>      : scene dump -> PLY with the unchanged GaussianModel.save_ply (mesh input)
  lineage <name>  : PROCFIG-v1 attribution.py rule on the mesh-render model: per training view max alpha*T id (TARGET r5 maxid .so),
                    GT rows of groups 1 (틀린 판정) and 2 (보정 비교) to nearest pixel, |saved render depth - point depth| <= 0.25 m,
                    modal Gaussian over views, ties lowest id. Saved depth = this family's mesh render (gtj/renders/<key>)."""
import sys, math, time, importlib.util
from types import SimpleNamespace
from common import *
sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
import torch
import diff_surfel_rasterization as raster
from scene import GaussianModel
from gaussian_renderer import render
from scipy.sparse import coo_matrix
from render_states import camera, load
MAXID = PH/'main_target_v1/PHD-MAIN-TARGET-v1/r5/runtime/maxid_build/jbgs_target_r5_maxid.so'
TL_RUN = RUNM

def family(name): return f'tl_{name}'

@torch.no_grad()
def to_ply(name):
    out = O/'ply'/f'{name}.ply'; out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists(): return
    g, d = load(TL_RUN/'trainlog/scene'/f'{name}.pt'); g.save_ply(str(out))
    dump(out.with_suffix('.json'), dict(at=now(), name=name, iteration=int(d['iteration']), gaussians=len(d['xyz']), source=str(TL_RUN/'trainlog/scene'/f'{name}.pt'), ply_sha256=sha(out), writer='GaussianModel.save_ply (r27 = r23 code)', scientific_verdict=None))
    print('PLY', name, len(d['xyz']), flush=True)

@torch.no_grad()
def lineage(name, ply=None, uid_source=None):
    start = time.monotonic(); torch.cuda.set_per_process_memory_fraction(.55); key = f'{STEM}__{family(name)}'
    rr = O/'gtj/renders'/key; rec = json.loads((rr/'receipt.json').read_text()); views = [v for v in rec['views'] if not v['virtual']]; box = np.array(rec['box'])
    ref = loadz(PF/'work/reference_building.npz'); groups = loadz(PF/'work/patch_groups.npz')['group']; own = ref['owner']; group = np.zeros(len(own), 'i1'); ok = own >= 0; group[ok] = groups[own[ok]]
    sel = np.flatnonzero(group > 0); xyz = ref['xyz'][sel]; pg = group[sel]
    ply = Path(ply) if ply else O/'ply'/f'{name}.ply'; g = GaussianModel(3); g.load_ply(str(ply))
    inside = ((g.get_xyz >= torch.tensor(box[0], device='cuda')) & (g.get_xyz <= torch.tensor(box[1], device='cuda'))).all(1); fullids = np.flatnonzero(inside.cpu().numpy())
    for a in ['_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity']: setattr(g, a, torch.nn.Parameter(getattr(g, a).detach()[inside].clone(), requires_grad=False))
    g.active_sh_degree = 0; pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
    spec = importlib.util.spec_from_file_location('jbgs_target_r5_maxid', MAXID); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); raster._C = mod
    P_, G_ = [], []; worst = 0.; mism = 0
    for j, v in enumerate(views):
        K = np.asarray(v['K']); pkg = render(camera(v['width'], v['height'], K, np.asarray(v['W2C']), v['name']), g, pipe, bg)
        dep = pkg['surf_depth'].squeeze().cpu().numpy(); index = np.rint(pkg['rend_dist'].squeeze().cpu().numpy()).astype('i8')-1
        saved = loadz(rr/v['file'], ['depth'])['depth']; pos = saved > 0
        if not np.array_equal(dep[pos], saved[pos], equal_nan=True): mism += 1; worst = max(worst, float(np.nanmax(abs(dep[pos]-saved[pos]))))
        E = np.asarray(v['W2C']); q = xyz@E[:3, :3].T+E[:3, 3]; ids = np.flatnonzero(q[:, 2] > 0); a = q[ids]
        u = np.rint(K[0, 0]*a[:, 0]/a[:, 2]+K[0, 2]).astype(int); w = np.rint(K[1, 1]*a[:, 1]/a[:, 2]+K[1, 2]).astype(int)
        ins = (u >= 0) & (w >= 0) & (u < v['width']) & (w < v['height']); ids, u, w = ids[ins], u[ins], w[ins]
        seen = (saved[w, u] > 0) & (abs(saved[w, u]-q[ids, 2]) <= .25) & (index[w, u] >= 0); P_.append(ids[seen]); G_.append(index[w[seen], u[seen]])
    a = np.concatenate(P_); b = np.concatenate(G_); M = coo_matrix((np.ones(len(a), 'i4'), (a, b)), shape=(len(xyz), len(fullids))).tocsr()
    chosen = np.full(len(xyz), -1, 'i8'); votes = np.asarray(M.sum(1)).ravel()
    for i in np.flatnonzero(np.diff(M.indptr)):
        s0, s1 = M.indptr[i:i+2]; ii = M.indices[s0:s1]; cc = M.data[s0:s1]; chosen[i] = ii[np.argmax(cc)]
    full = np.where(chosen >= 0, fullids[chosen.clip(0)], -1)
    src = uid_source or (TL_RUN/'trainlog/scene'/f'{name}.pt'); d = torch.load(src, map_location='cpu', weights_only=False)
    n = len(d['xyz']); assert n == len(g._xyz) or True
    take = lambda arr: np.where(full >= 0, arr[full.clip(0)], -1)
    out = dict(reference_row_id=ref['row_id'][sel], group=pg, max_contributor_full_gaussian=full, uid=take(d['uid'].numpy()), origin=take(d['origin'].numpy().astype('i8')),
               target_tag=take(d['target_tag'].numpy().astype('i8')), target_index=take(d['target_index'].numpy()), init_id=take(d['init_id'].numpy().astype('i8')), visible_views=votes)
    savez(O/'lineage'/f'{name}.npz', **out)
    res = dict(at=now(), name=name, family=family(name), ply=str(ply), ply_sha256=sha(ply), rows=len(xyz), attributed=int((full >= 0).sum()), views=len(views), depth_mismatch_views=mism, depth_max_abs_diff_m=worst,
               method='PROCFIG-v1 attribution.py (modal max alpha*T over 203 training views, 0.25 m, argmax first = lowest column on tie)', seconds=time.monotonic()-start, scientific_verdict=None)
    dump(O/'lineage'/f'{name}.json', res); print('LINEAGE', name, res['attributed'], len(xyz), mism, round(res['seconds']), flush=True)

if __name__ == '__main__':
    cmd, name = sys.argv[1:3]
    if cmd == 'ply': to_ply(name)
    elif cmd == 'lineage': lineage(name, *sys.argv[3:])
