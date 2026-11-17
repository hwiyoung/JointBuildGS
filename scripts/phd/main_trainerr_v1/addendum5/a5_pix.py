"""Pixel-defined groups (addendum5.json places annex_under / south_wall; addendum 4 work da 4.3 definition). GPU (/source = r31).
  build <case>                 : the addendum-4 pixels (2,000 sampled mesh points of the reference 30,000 mesh, up to three views each where the rendered depth is
                                 within 0.1 m of the point) for the problem set and the control set -> payload addendum5/pix/pixels_<case>.npz
                                 annex: wrong (> 1 m from GT) / right_roof (<= 0.2 m, not wall) of B0 x ALS ba-3; south: behind the south wall (> 0.64 m) of
                                 B0 x LoD2 TRAINLOG record, control = long street-side wall GT points (addendum3 long_wall)
  group <run> <case> <state>   : Gaussians giving alpha*T > 1e-3 within the point depth +- 0.5 m at those pixels -> payload addendum5/pix/group_<run>_<case>_<state>.npz
The same pixels (fixed at the reference 30,000 model) are used for every run and stage of the scene."""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
PIX = A5O/'pix'
REF = {'annex': ('B0_b10__ALS', 'ba3_B0_ALS_record'), 'south': ('B0_b10__LoD2', 'tl_B0_b10_LoD2_s0')}

def build(case):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_da as D4
    camera = D4.gpu_setup(); t0 = time.monotonic(); rng = np.random.default_rng(0); stem, run = REF[case]
    if case == 'annex': mesh = A3O/'gtj/meshes/B0_b10__ALS__ba3_30000/final.ply'
    else: mesh = TLC/'gtj/meshes/B0_b10__LoD2__tl_30000/final.ply'
    m = o3d.io.read_triangle_mesh(str(mesh)); V = np.asarray(m.vertices, 'f8'); del m
    G = loadz(GT/'reference/B0_b10/dense.npz', ['xyz', 'wall']); TG = cKDTree(G['xyz'].astype('f8'))
    if case == 'annex':   # same order of rng draws as addendum 4 a4_da.wrong
        b = ANNEX; inb = (V[:, 0] >= b['x'][0]) & (V[:, 0] <= b['x'][1]) & (V[:, 1] >= b['y'][0]) & (V[:, 1] <= b['y'][1]) & (V[:, 2] >= b['z'][0]) & (V[:, 2] <= b['z'][1])
        ii = np.flatnonzero(inb); dg, jg = TG.query(V[ii]); sets = {'problem': V[ii[dg > 1.]], 'control': V[ii[(dg <= .2) & ~G['wall'][jg].astype(bool)]]}
    else:
        sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1'); import a1_common as A1
        a, d, zone = A1.wall_coords(V, 'south'); sets = {'problem': V[np.flatnonzero(zone & (d < -.64))], 'control': place_points5('long_wall')['xyz'].astype('f8')}
    model = RUNS4[run]['model']; S = D4.load_pt(model, '30000'); md, mi = D4.views_of(stem); names = sorted(mi); out = {}
    with torch.no_grad():
        g = D4.gmodel(S); from gaussian_renderer import render; from types import SimpleNamespace
        pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); rd_cache = {}
        for sname, P in sets.items():
            pick = np.sort(rng.choice(len(P), min(2000, len(P)), replace=False)) if len(P) else np.zeros(0, 'i8'); X = P[pick]; recs = []
            for j, nm in enumerate(names):
                mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; zc = Xc[:, 2]; okz = zc > .2
                u = np.floor(K[0, 0]*Xc[:, 0]/np.where(okz, zc, 1)+K[0, 2]).astype('i8'); v = np.floor(K[1, 1]*Xc[:, 1]/np.where(okz, zc, 1)+K[1, 2]).astype('i8')
                with np.load(md/mm['file']) as z: H, W = z['owner'].shape
                ins = okz & (u >= 0) & (u < W) & (v >= 0) & (v < H)
                if not ins.any(): continue
                if nm not in rd_cache: rd_cache[nm] = render(camera(W, H, K, M, nm), g, pipe, torch.zeros(3, device='cuda'))['surf_depth'].squeeze().cpu().numpy()
                rd = rd_cache[nm]; q = np.flatnonzero(ins); dz = np.abs(rd[v[q], u[q]]-zc[q]); q = q[dz <= .1]
                for k_ in q: recs.append((k_, j, abs(rd[v[k_], u[k_]]-zc[k_]), u[k_], v[k_], zc[k_]))
            recs = np.array(recs) if recs else np.zeros((0, 6)); keep = []
            for k_ in np.unique(recs[:, 0]).astype(int) if len(recs) else []:
                r = recs[recs[:, 0] == k_]; keep.extend(r[np.argsort(r[:, 2])[:3]].tolist())
            keep = np.array(keep) if keep else np.zeros((0, 6))
            out[sname] = dict(point=keep[:, 0].astype('i8'), view=keep[:, 1].astype('i8'), u=keep[:, 3].astype('i8'), v=keep[:, 4].astype('i8'), zpt=keep[:, 5], xyz=X[keep[:, 0].astype('i8')] if len(keep) else np.zeros((0, 3)),
                             points_total=np.int64(len(P)), points_sampled=np.int64(len(pick)))
    PIX.mkdir(parents=True, exist_ok=True); savez(PIX/f'pixels_{case}.npz', **{f'{s}__{k}': v for s, o in out.items() for k, v in o.items()}, view_names=np.array(names), reference_run=np.array(run))
    print('PIXBUILD', case, {s: len(o['point']) for s, o in out.items()}, round(time.monotonic()-t0), flush=True)

def group(run, case, state):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_da as D4
    camera = D4.gpu_setup(); t0 = time.monotonic(); z = loadz(PIX/f'pixels_{case}.npz'); stem = REF[case][0]
    model = RUN5[run]; S = D4.load_pt(model, state); md, mi = D4.views_of(stem); names = [str(x) for x in z['view_names']]; out = {}
    with torch.no_grad():
        g = D4.gmodel(S)
        for s in ['problem', 'control']:
            view = z[f'{s}__view']; rows = []; wts = []; pix = []
            for j in np.unique(view):
                sel = np.flatnonzero(view == j); nm = names[j]; mm = mi[nm]
                with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape
                C = D4.contrib(g, camera(W, H, np.asarray(mm['K']), np.asarray(mm['W2C']), nm), z[f'{s}__u'][sel], z[f'{s}__v'][sel])
                if not len(C): continue
                p = C[:, 0].astype('i8'); near = np.abs(C[:, 3]-z[f'{s}__zpt'][sel][p]) <= .5; keep = near & (C[:, 2] > 1e-3)
                rows.append(C[keep, 1].astype('i8')); wts.append(C[keep, 2]); pix.append(sel[p[keep]])
            r = np.concatenate(rows) if rows else np.zeros(0, 'i8'); w = np.concatenate(wts) if wts else np.zeros(0); px = np.concatenate(pix) if pix else np.zeros(0, 'i8')
            ur = np.unique(r); out[s] = dict(uid=S['uid'].numpy()[ur], row=ur, weight_sum=np.bincount(np.searchsorted(ur, r), w, len(ur)), pixel_rows=r, pixel_weight=w, pixel=px)
    PIX.mkdir(parents=True, exist_ok=True); savez(PIX/f'group_{run}_{case}_{state}.npz', **{f'{s}__{k}': v for s, o in out.items() for k, v in o.items()})
    print('PIXGROUP', run, case, state, {s: len(o['uid']) for s, o in out.items()}, round(time.monotonic()-t0), flush=True)

RUN5 = {k: v['model'] for k, v in RUNS4.items()}

if __name__ == '__main__':
    a = sys.argv[1:]
    {'build': build, 'group': group}[a[0]](*a[1:])
