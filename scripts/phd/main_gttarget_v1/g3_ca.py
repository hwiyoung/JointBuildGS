"""Stage 3 (order 8): causes of the lost points of the GT target run, with the TRAINERR addendum 6 rules (code copied, inputs changed; changes listed here).
usage: g3_ca.py state <stem> [run] | track <stem> [run] | pix <stem> [run] (GPU, /source = r28) | labels <stem> [run] | causes <stem> [run] | tables
Inputs: O/points/ga_<stem>.npz (g3_ga.py: selected points = all GTT lost + 20,000 GTT kept), O/runs/<stem>/<run>/model (30,000 ply, target_monitor snapshot,
trainlog scene dumps + events), O/targets/<stem>.npz (GT patches = target rows), O/stage1/<stem>/{seeds.npz, maps/, occl/}, O/meshes/<stem>__<run>_<variant>/points.npz.
Changes from addendum 6 (a6_ga select/track, a6_da pix/labels, a6_ba causes):
  - patch of a point = the GT patch square covering it (g1_cover rule: nearest square centre with in-plane distance <= sqrt(2) x (0.125 + 0.02) m, smallest normal
    distance; -1 = no covering square), instead of the method patch row; valid patches = every GT patch (all pass valid_patch, g1_targets); seeds per patch from
    O/stage1/<stem>/seeds.npz origin 1.
  - state (order 8.1, addendum 6 0.1): 4 = no covering patch, 3 = covering patch with 0 seeds, 2 = a Gaussian (opacity >= 0.1) centre within 0.2 m of the point at
    30,000 (ply), 1 = otherwise.  The addendum 2 'spot' counted the same at 30,000; here computed from this run's ply.
  - view set 'facing' (definition 2): camera centre on the side the GT patch normal points to (the stage-1 normals are oriented to the side the images see, g1_orient.py),
    instead of addendum 3 outward() (LoD2 solid). Definition 1 = every view containing the point (unchanged).
  - occlusion check (order 8.3, added): pairs are also reported without (a) pixels of code 2 in O/stage1/<stem>/occl (order 4 occluded map) and (b) additionally pixels whose
    target depth (maps depth, owner >= 0) is nearer than point depth - tau (the point lies behind another GT patch in that view).
  - recovery uses this run's re-extractions occl / median_depth / occl_median (order 7.1) in place of occl_10 / median_depth / occl_10_median.
  - patch main path: unchanged rule (addendum6.json work_ga), bound = target_tag 1 and target_index == the GT patch."""
import sys, time, math
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from scipy.spatial import cKDTree

CA = O/'ca'
A6 = json.loads((R/'configs/phd/main_trainerr_v1/addendum6.json').read_text())['work_ga']
A6C = json.loads((R/'configs/phd/main_trainerr_v1/addendum6_c.json').read_text())['work_da']
PATHS = ['release', 'retarget', 'reset_delete', 'other_delete', 'split']
PATH_KO = {'release': '풀림', 'retarget': '재할당', 'reset_delete': '재설정 뒤 제거', 'other_delete': '그 밖의 제거', 'split': '분할로 대체'}
L1 = ['이웃이 그린다', '앞이 가려진다', '뚫려 있다', '섞여 있다']
L2 = ['가우시안이 어긋나 있다', '앞으로 당겨진다', '뒤로 밀린다', '영상마다 다르다', '그린 깊이는 맞다', '나뉘지 않음(그 밖)']
KIND4 = ['같은 목표에 묶인 것', '다른 목표에 묶인 것', '풀린 것', '묶이지 않은 것']
CAUSE = ['유효한 조각 없음', '씨앗이 놓이지 않음', '표면 추출에서 없어짐: 가려진 화소', '표면 추출에서 없어짐: 평균 깊이', '가우시안은 있는데 그린 깊이가 벗어남',
         '묶인 가우시안이 풀려 나감', '묶인 가우시안이 재할당으로 나감', '묶인 가우시안이 재설정 뒤 제거됨', '그 밖의 길로 없어짐', '설명되지 않음']
PAIRSETS = ['모든 쌍', '가림 지도(차례 2) 화소 뺌', '가림 지도 + 다른 참값 면 뒤 화소 뺌']
VIEWSETS = ['화면에 드는 모든 영상(정의 1)', '점의 바깥쪽에서 보는 영상(정의 2)']

def model_of(stem, run): return O/'runs'/stem/run/'model'
def ply_read(p):
    with open(p, 'rb') as f:
        h = b''
        while not h.endswith(b'end_header\n'): h += f.readline()
        n = int(h.split(b'element vertex ')[1].split()[0]); props = [l.split()[-1].decode() for l in h.split(b'\n') if l.startswith(b'property')]
        a = np.frombuffer(f.read(n*4*len(props)), 'f4').reshape(n, len(props))
    return {k: a[:, i] for i, k in enumerate(props)}
def cover(site, X):
    p = loadz(O/'surface'/site/'patches.npz', ['centre', 'normal']); C = p['centre'].astype('f8'); Nn = p['normal'].astype('f8'); tree = cKDTree(C); h = .125+.02
    d, j = tree.query(X, k=8, distance_upper_bound=1.0, workers=16); best = np.full(len(X), np.inf); cov = np.full(len(X), -1)
    for q in range(8):
        jj = j[:, q]; v = jj < len(C); jj = np.where(v, jj, 0); r = X-C[jj]; dn = (r*Nn[jj]).sum(1); w = np.abs(dn); ip = np.linalg.norm(r-dn[:, None]*Nn[jj], axis=1)
        ok = v & (ip <= np.sqrt(2)*h) & (w < best); best = np.where(ok, w, best); cov = np.where(ok, jj, cov)
    return cov
def sel_of(stem): return loadz(O/'points'/f'ga_{stem}.npz')

# ---------------- 8.1 state ----------------
def state(stem, run='gtt_s0'):
    t0 = time.monotonic(); site = stem.split('__')[0]; P = sel_of(stem); X = P['xyz'].astype('f8'); v = cover(site, X)
    sd = loadz(O/'stage1'/stem/'seeds.npz', ['origin', 'patch']); N = len(loadz(O/'targets'/f'{stem}.npz', ['area'])['area'])
    seeds = np.bincount(sd['patch'][(sd['origin'] == 1) & (sd['patch'] >= 0)], minlength=N)
    g = ply_read(model_of(stem, run)/'point_cloud/iteration_30000/point_cloud.ply'); G = np.c_[g['x'], g['y'], g['z']].astype('f8'); op = 1/(1+np.exp(-g['opacity']))
    s = loadz(model_of(stem, run)/'target_monitor/snapshot_30000.npz', ['xyz', 'target_tag', 'target_index']); assert len(s['xyz']) == len(G) and np.abs(s['xyz']-G).max() < 1e-4
    vis = np.flatnonzero(op >= .1); tree = cKDTree(G[vis]); near = tree.query_ball_point(X, .2, workers=16); spot = np.array([len(q) for q in near])
    kin = np.zeros((len(X), 4), 'i4')
    for i, q in enumerate(near):
        if q: r = vis[np.asarray(q)]; tg = s['target_tag'][r]; ti = s['target_index'][r]; kin[i] = np.bincount(np.where(tg == 1, np.where(ti == v[i], 0, 1), np.where(tg == 2, 2, 3)), minlength=4)
    st = np.where(v < 0, 4, np.where(seeds[np.clip(v, 0, None)] == 0, 3, np.where(spot > 0, 2, 1))).astype('i1')
    savez(CA/f'state_{stem}_{run}.npz', v=v.astype('i8'), seeds=seeds[np.clip(v, 0, None)]*(v >= 0), spot_n=spot, spot_kind=kin, state=st)
    print('CA_STATE', stem, run, np.bincount(st, minlength=5).tolist(), round(time.monotonic()-t0), flush=True)

# ---------------- 8.3 patch course (copy of a6_ga.track; dumps read here) ----------------
def track(stem, run='gtt_s0'):
    import torch
    c = A6; t0 = time.monotonic(); m = model_of(stem, run); names = sorted([p.stem for p in (m/'trainlog/scene').glob('*.pt')], key=lambda n: (int(n.split('_')[0]), 0 if n.endswith('pre_reset') else 1))
    Z = {}
    for n in names:
        s = torch.load(m/'trainlog/scene'/f'{n}.pt', map_location='cpu', weights_only=False)
        Z[f'{n}__uid'] = s['uid'].numpy(); Z[f'{n}__tag'] = s['target_tag'].numpy().astype('i1'); Z[f'{n}__tidx'] = s['target_index'].numpy(); Z[f'{n}__iteration'] = int(s['iteration']); del s
    it = np.array([Z[f'{n}__iteration'] for n in names]); post = np.array([(not n.endswith('pre_reset')) and int(n) in c['resets'] for n in names])
    S = loadz(CA/f'state_{stem}_{run}.npz', ['v']); nP = len(loadz(O/'targets'/f'{stem}.npz', ['area'])['area']); P = np.unique(S['v'][S['v'] >= 0]); interest = np.zeros(nP, bool); interest[P] = True
    def ev(k):
        parts = [loadz(f) for f in sorted((m/'trainlog/events').glob(f'{k}_*.npz')) if f.stem.rsplit('_', 1)[0] == k]
        return {f: np.concatenate([p[f] for p in parts]) for f in parts[0]} if parts else {}
    de, re, lk = ev('delete'), ev('release'), ev('link')
    del_by = {int(u): (int(r), int(i)) for u, r, i in zip(de['uid'], de['reason'], de['iteration'])} if de else {}
    rel_uid = re['uid'] if re else np.zeros(0, 'i8'); rel_it = re['iteration'] if re else np.zeros(0, 'i4')
    split_par = lk['parent_uid'][lk['how'] == 3] if lk else np.zeros(0, 'i8'); split_it = lk['iteration'][lk['how'] == 3] if lk else np.zeros(0, 'i4'); split_ch = lk['uid'][lk['how'] == 3] if lk else np.zeros(0, 'i8')
    so = np.argsort(split_par, kind='stable'); split_par, split_it, split_ch = split_par[so], split_it[so], split_ch[so]
    ro = np.lexsort((rel_it, rel_uid)); rel_uid, rel_it = rel_uid[ro], rel_it[ro]
    counts = np.zeros((len(names), len(P)), 'i4'); pidx = np.full(nP, -1, 'i8'); pidx[P] = np.arange(len(P)); ex = {k: [] for k in ['patch', 'pair', 'path', 'sub', 'new_patch', 'reason']}
    def bound(k):
        tag = Z[f'{names[k]}__tag']; ti = Z[f'{names[k]}__tidx']; b = (tag == 1) & (ti >= 0) & (ti < nP); b[b] &= interest[ti[b]]; return np.flatnonzero(b), ti
    for k in range(len(names)):
        rows, ti = bound(k); counts[k] = np.bincount(pidx[ti[rows]], minlength=len(P))
    for k in range(len(names)-1):
        ra, ta = bound(k); ua = Z[f'{names[k]}__uid'][ra]; pa = ta[ra]; ub = Z[f'{names[k+1]}__uid']; tb = Z[f'{names[k+1]}__tag']; ib = Z[f'{names[k+1]}__tidx']
        ob = np.argsort(ub); pos = np.clip(np.searchsorted(ub[ob], ua), 0, len(ub)-1); found = ub[ob][pos] == ua; jb = ob[pos]
        stay = found & (tb[jb] == 1) & (ib[jb] == pa); ia_, ib_ = it[k], it[k+1]
        for q in np.flatnonzero(~stay):
            u = int(ua[q]); p = int(pa[q]); sub = ''; npat = -1; rs = -1
            if found[q]:
                j = jb[q]; path = 'retarget' if tb[j] == 1 else 'release'; npat = int(ib[j]) if tb[j] == 1 else -1
            else:
                a = np.searchsorted(split_par, u); b = np.searchsorted(split_par, u, 'right')
                if any(ia_ < split_it[e] <= ib_ for e in range(a, b)): path = 'split'
                elif u in del_by and ia_ < del_by[u][1] <= ib_:
                    rs, di = del_by[u]; path = 'reset_delete' if rs == 1 and any(di == x+c['check_after'] for x in c['resets']) else 'other_delete'; sub = 'event' if path == 'reset_delete' else f'event_reason_{rs}'
                elif post[k]: path = 'reset_delete'; sub = 'no_event'
                else: path = 'other_delete'; sub = 'no_event_window_with_reset' if any(ia_ < x+c['check_after'] <= ib_ for x in c['resets']) else 'no_event'
            ex['patch'].append(p); ex['pair'].append(k); ex['path'].append(PATHS.index(path)); ex['sub'].append(sub); ex['new_patch'].append(npat); ex['reason'].append(rs)
        print('CA_TRACK', stem, run, names[k], len(ex['patch']), round(time.monotonic()-t0), flush=True)
    exa = {k: np.asarray(v_) for k, v_ in ex.items()}; exa['sub'] = exa['sub'].astype('U40')
    first0 = np.full(len(P), -1, 'i8'); refill = np.full(len(P), -1, 'i8')
    for i in range(len(P)):
        z0 = np.flatnonzero(counts[:, i] == 0)
        if len(z0):
            first0[i] = z0[0]; r = np.flatnonzero(counts[z0[0]:, i] > 0)
            if len(r): refill[i] = z0[0]+r[0]
    npath = np.zeros((len(P), len(PATHS)), 'i4')
    if len(exa['patch']): np.add.at(npath, (pidx[exa['patch']], exa['path']), 1)
    main = np.where(npath.sum(1) > 0, npath.argmax(1), -1)
    savez(CA/f'patch_{stem}_{run}.npz', patches=P, names=np.array(names), iterations=it, counts=counts, first_empty=first0, refill=refill, path_counts=npath, main_path=main, **{f'exit__{k}': v_ for k, v_ in exa.items()})
    print('CA_TRACK_DONE', stem, run, len(P), len(exa['patch']), round(time.monotonic()-t0), flush=True)

# ---------------- 8.3 rendered depth at the point (copy of a6_da.pix with a4_da.contrib / per_pixel) ----------------
def camera(W, H, K, W2C, name):  # TRAINLOG render_states.camera (unchanged copy of te_render.camera)
    import torch
    from types import SimpleNamespace
    zn, zf = .01, 2000.
    P = np.zeros((4, 4), 'f4'); P[0, 0] = 2*K[0, 0]/W; P[1, 1] = 2*K[1, 1]/H; P[0, 2] = (2*K[0, 2]-(W-1))/W; P[1, 2] = (2*K[1, 2]-(H-1))/H; P[2, 2] = zf/(zf-zn); P[2, 3] = -zf*zn/(zf-zn); P[3, 2] = 1.
    w = torch.tensor(np.asarray(W2C), device='cuda', dtype=torch.float32).T; p = torch.tensor(P, device='cuda').T
    return SimpleNamespace(image_width=W, image_height=H, image_name=name, FoVx=2*math.atan(W/(2*K[0, 0])), FoVy=2*math.atan(H/(2*K[1, 1])), znear=zn, zfar=zf,
                           world_view_transform=w, projection_matrix=p, full_proj_transform=w@p, camera_center=w.inverse()[3, :3])
def _a4():
    import ast
    p = R/'scripts/phd/main_trainerr_v1/addendum4/a4_da.py'; tree = ast.parse(p.read_text()); env = dict(np=np)
    exec(compile(ast.Module(body=[x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in ('contrib', 'per_pixel')], type_ignores=[]), str(p), 'exec'), env)
    return env['contrib'], env['per_pixel']

def pix(stem, run='gtt_s0'):
    import torch
    sys.path.insert(0, '/source'); from scene import GaussianModel; from utils.general_utils import build_rotation
    contrib, per_pixel = _a4(); t0 = time.monotonic(); P = sel_of(stem); S = loadz(CA/f'state_{stem}_{run}.npz'); sel = np.flatnonzero(np.isin(S['state'], [1, 2]))
    X = P['xyz'][sel].astype('f8'); tau = P['tau'][sel].astype('f8'); v = S['v'][sel]; T = loadz(O/'targets'/f'{stem}.npz', ['normal']); nrm = np.where((v >= 0)[:, None], T['normal'][np.clip(v, 0, None)], np.nan)
    m = model_of(stem, run); ply = m/'point_cloud/iteration_30000/point_cloud.ply'
    with ply.open('rb') as f:
        names = []
        while True:
            line = f.readline().decode('ascii').strip()
            if line == 'end_header': break
            if line.startswith('property') and 'f_rest_' in line: names.append(line)
    g = GaussianModel(round(math.sqrt(len(names)/3+1)-1)); g.load_ply(str(ply))
    for a in ['_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity']: setattr(g, a, torch.nn.Parameter(getattr(g, a).detach(), requires_grad=False))
    s = loadz(m/'target_monitor/snapshot_30000.npz', ['xyz', 'target_tag', 'target_index']); assert len(s['xyz']) == len(g._xyz) and np.abs(s['xyz']-g._xyz.detach().cpu().numpy()).max() < 1e-4
    tag, tidx = s['target_tag'], s['target_index']; size = torch.exp(g._scaling).max(1).values.cpu().numpy(); op = torch.sigmoid(g._opacity[:, 0]).cpu().numpy()
    md = O/'stage1'/stem/'maps'; mi = json.loads((md/'index.json').read_text())['views']; vn = sorted(mi)
    recs = {k: [] for k in ['pt', 'view', 'zp', 'acc', 'mean', 'median', 'w3', 'wk', 'front_off', 'size_front', 'occl2', 'behind_gt', 'facing']}
    with torch.no_grad():
        for j, nm in enumerate(vn):
            mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; okz = z > .2
            with np.load(md/mm['file']) as zz: owner = zz['owner']; tdep = zz['depth']
            with np.load(O/'stage1'/stem/'occl'/mm['file']) as zz: code = zz['code']
            H, W = owner.shape
            uu = K[0, 0]*Xc[:, 0]/np.where(okz, z, 1)+K[0, 2]; vv = K[1, 1]*Xc[:, 1]/np.where(okz, z, 1)+K[1, 2]; ins = np.flatnonzero(okz & (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H))
            if not len(ins): continue
            px = np.floor(uu[ins]).astype('i8'); py = np.floor(vv[ins]).astype('i8')
            C = contrib(g, camera(W, H, K, M, nm), px, py); n = len(ins)
            acc, mean, med_ = per_pixel(C, n) if len(C) else (np.zeros(n), np.full(n, np.nan), np.full(n, np.nan))
            p = C[:, 0].astype('i8'); gi = C[:, 1].astype('i8'); w = C[:, 2]; dep = C[:, 3]; zp = z[ins][p]; tl = tau[ins][p]
            b = np.where(dep < zp-tl, 0, np.where(dep > zp+tl, 2, 1)); vp = v[ins][p]; kd = np.where(tag[gi] == 1, np.where(tidx[gi] == vp, 0, 1), np.where(tag[gi] == 2, 2, 3))
            w3 = np.zeros((n, 3)); np.add.at(w3, (p, b), w); wk = np.zeros((n, 3, 4)); np.add.at(wk, (p, b, kd), w)
            fo = np.bincount(p, w*(zp-dep)*(b == 0), n)/np.maximum(w3[:, 0], 1e-12)
            sf = np.full(n, np.nan); q = np.flatnonzero(b == 0)
            if len(q):
                o = np.lexsort((size[gi][q], p[q])); pq = p[q][o]; vq = size[gi][q][o]; wq = w[q][o]; cs = np.cumsum(wq); st = np.searchsorted(pq, np.arange(n+1))
                for i in np.flatnonzero(st[1:] > st[:-1]):
                    a_, e_ = st[i], st[i+1]; c0 = cs[a_-1] if a_ else 0.; kk = np.searchsorted(cs[a_:e_]-c0, .5*(cs[e_-1]-c0)); sf[i] = vq[a_+min(kk, e_-a_-1)]
            cam = -M[:3, :3].T@M[:3, 3]; fac = ((cam[None]-X[ins])*nrm[ins]).sum(1) > 0
            occ2 = code[py, px] == 2; bgt = (owner[py, px] >= 0) & (tdep[py, px] > 0) & (tdep[py, px] < z[ins]-tau[ins])
            for k_, val in [('pt', sel[ins]), ('view', np.full(n, j, 'i2')), ('zp', z[ins]), ('acc', acc), ('mean', mean), ('median', med_), ('w3', w3), ('wk', wk), ('front_off', fo),
                            ('size_front', sf), ('occl2', occ2), ('behind_gt', bgt), ('facing', fac)]: recs[k_].append(np.asarray(val))
            if j % 20 == 0: print('CA_PIX', stem, run, j, len(vn), n, round(time.monotonic()-t0), flush=True)
    out = {k: np.concatenate(v_) for k, v_ in recs.items()}
    vis = np.flatnonzero(op >= .1); xyz = g._xyz.detach().cpu().numpy().astype('f8'); tree = cKDTree(xyz[vis]); within = tree.query_ball_point(X, tau); cnt = np.array([len(q) for q in within])
    savez(CA/f'pix_{stem}_{run}.npz', **out, sel=sel, within_n=cnt, views=np.int32(len(vn)))
    print('CA_PIX_DONE', stem, run, len(sel), len(out['pt']), round(time.monotonic()-t0), flush=True)

def gmed(key, val, n):
    out = np.full(n, np.nan); ok = np.isfinite(val); k = key[ok]; v = val[ok]
    if not len(k): return out
    o = np.lexsort((v, k)); k = k[o]; v = v[o]; st = np.searchsorted(k, np.arange(n+1)); c = st[1:]-st[:-1]; h = np.flatnonzero(c)
    out[h] = .5*(v[st[h]+(c[h]-1)//2]+v[st[h]+c[h]//2]); return out

def labels_of(z, k, n, tau, use):   # copy of a6_da.labels_of (addendum6_c work_da half / split_share)
    kk = k[use]; tl = tau[kk]; d = (z['mean']-z['zp'])[use]
    M = {nm: gmed(kk, z['w3'][use, i], n) for i, nm in enumerate(['front', 'within', 'behind'])}; M['acc'] = gmed(kk, z['acc'][use], n); M['mean_off'] = gmed(kk, d, n)
    vf = np.isfinite(d) & (d < -tl); vb = np.isfinite(d) & (d > tl); vw = np.isfinite(d) & ~vf & ~vb; nv = np.bincount(kk, minlength=n).astype(float)
    sf = np.bincount(kk, vf, n)/np.maximum(nv, 1); sb = np.bincount(kk, vb, n)/np.maximum(nv, 1); sw = np.bincount(kk, vw, n)/np.maximum(nv, 1)
    h = A6C['half']; sp = A6C['split_share']
    l1 = np.where(M['within'] >= h, 0, np.where(M['front'] >= h, 1, np.where((M['behind'] >= h) | (M['acc'] < h), 2, 3)))
    l2 = np.where(z['within_n'] == 0, 0, np.where((M['mean_off'] < -tau) & (M['front'] > M['within']), 1, np.where((M['mean_off'] > tau) & (M['behind'] > M['within']), 2,
                  np.where((sf >= sp) & (sb >= sp) & (sw < h), 3, np.where(sw >= h, 4, 5)))))
    nov = nv == 0; l1 = np.where(nov, -1, l1); l2 = np.where(nov & (z['within_n'] > 0), -1, l2)
    return l1, l2, M, nv

def labels(stem, run='gtt_s0'):
    P = sel_of(stem); z = loadz(CA/f'pix_{stem}_{run}.npz'); sel = z['sel']; n = len(sel); pos = np.full(len(P['xyz']), -1, 'i8'); pos[sel] = np.arange(n); k = pos[z['pt']]; tau = P['tau'][sel].astype('f8')
    out = {}
    for vi, vs in enumerate(['all', 'facing']):
        base = np.ones(len(k), bool) if vs == 'all' else z['facing'].astype(bool)
        for pi, ps in enumerate(['all', 'no_occl2', 'no_occl2_no_behind_gt']):
            use = base & (np.ones(len(k), bool) if ps == 'all' else (~z['occl2'].astype(bool) if ps == 'no_occl2' else ~(z['occl2'].astype(bool) | z['behind_gt'].astype(bool))))
            l1, l2, M, nv = labels_of(z, k, n, tau, use)
            out[f'{vs}__{ps}__l1'] = l1.astype('i1'); out[f'{vs}__{ps}__l2'] = l2.astype('i1'); out[f'{vs}__{ps}__views'] = nv.astype('i4')
            for nm in ['front', 'within', 'behind', 'acc']: out[f'{vs}__{ps}__{nm}'] = M[nm].astype('f4')
            # kinds of the Gaussians in front (share of the front weight by kind, pooled over the used pairs of the point)
            wf = z['wk'][use, 0, :]; kf = np.zeros((n, 4)); np.add.at(kf, k[use], wf); out[f'{vs}__{ps}__front_kind_w'] = kf.astype('f4')
            fo = np.where(np.isfinite(z['front_off'][use]) & (z['w3'][use, 0] > 0), z['front_off'][use], np.nan); out[f'{vs}__{ps}__front_off_med'] = gmed(k[use], fo, n).astype('f4')
            out[f'{vs}__{ps}__front_size_med'] = gmed(k[use], z['size_front'][use], n).astype('f4')
    savez(CA/f'labels_{stem}_{run}.npz', sel=sel, **out); print('CA_LABELS', stem, run, n, flush=True)

# ---------------- 8.2 / 8.4 recovery and one cause per point (copy of a6_ba.causes) ----------------
def causes(stem, run='gtt_s0'):
    P = sel_of(stem); S = loadz(CA/f'state_{stem}_{run}.npz'); G = loadz(CA/f'patch_{stem}_{run}.npz', ['patches', 'main_path']); D = loadz(CA/f'labels_{stem}_{run}.npz'); n = len(P['xyz'])
    W = {}
    for var in ['base', 'occl', 'median_depth', 'occl_median']:
        z = loadz(O/'meshes'/f'{stem}__{run}_{var}'/'points.npz', ['reference__within_tau1']); W[var] = z['reference__within_tau1'].astype(bool)[P['a11_row']]
    grp = P['group_gtt'] if run == 'gtt_s0' else P['group_gtt_s1']
    st = S['state']; occ = W['occl'] | W['occl_median']; medw = W['median_depth']
    pos = np.full(int(max(G['patches'].max(), S['v'].max()))+2, -1, 'i8'); pos[G['patches']] = np.arange(len(G['patches'])); vq = np.clip(S['v'], 0, len(pos)-1)
    mp = np.where((S['v'] >= 0) & (pos[vq] >= 0), G['main_path'][np.clip(pos[vq], 0, None)], -1)
    c = np.full(n, 9, 'i1')
    c = np.where(st == 2, np.where(occ, 2, np.where(medw, 3, 4)), c)
    c = np.where(st == 1, np.select([mp == 0, mp == 1, mp == 2, (mp == 3) | (mp == 4)], [5, 6, 7, 8], 9), c)
    c = np.where(st == 3, 1, c); c = np.where(st == 4, 0, c)
    rec = np.where(occ, 0, np.where(medw, 1, 2)).astype('i1')   # table ra: 0 back with occl (or occl_median), 1 back only with median_depth, 2 not back
    dpos = np.full(n, -1, 'i8'); dpos[D['sel']] = np.arange(len(D['sel'])); has = dpos >= 0
    sec = {}
    for key in [k[:-4] for k in D if k.endswith('__l1')]:
        l1 = np.where(has, D[f'{key}__l1'][np.clip(dpos, 0, None)], -2); l2 = np.where(has, D[f'{key}__l2'][np.clip(dpos, 0, None)], -2); sec[f'{key}__l1'] = l1; sec[f'{key}__l2'] = l2
    L1m, L2m = sec['facing__all__l1'], sec['facing__all__l2']   # main labels: definition 2 (order 8.3), all pairs
    unexpl = (rec == 2) & (((st == 2) & np.isin(L2m, [4, 5])) | ((st == 1) & (L1m == 0)))
    savez(CA/f'causes_{stem}_{run}.npz', a11_row=P['a11_row'], point_id=P['point_id'], xyz=P['xyz'], group=grp, group_method=P['group_method'], state=st, cause=c, recovery=rec,
          back_occl=W['occl'], back_median=W['median_depth'], back_occl_median=W['occl_median'], main_path=mp, unexplained=unexpl, **sec)
    print('CA_CAUSES', stem, run, int((grp == 1).sum()), np.bincount(c[grp == 1], minlength=10).tolist(), int(unexpl[grp == 1].sum()), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]; CA.mkdir(parents=True, exist_ok=True)
    {'state': state, 'track': track, 'pix': pix, 'labels': labels, 'causes': causes}[a[0]](*a[1:])
