"""Deterministic real-state replay for the r28 unit checks (TRAINLOG replay_test.py adapted).
Start: complete state at iteration 200 of a small-example probe (real R1rep_b10 x ALS scene and real targets).
The same deterministic synthetic loss (split into three terms) and density statistics drive the inherited controller and
GaussianModel code (Adam, 100-step reattach, project_bounds, clone/split/prune, opacity reset) for 300 iterations.
  dump <name> <own|gt> <probe>     : FinalTrain of the mounted fork -> verification/replay_<name>/state.pt
  compare <a> <b>                  : byte comparison of two dumps
  record <own|gt> <probe>          : r28 FinalTrain vs r28 TrainLog (region + gradients on) in one process
  switches <probe> <iteration>     : one periodic reattach, each switch on vs off, changed-set check"""
import os, sys, random, copy
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8'); os.environ['JBGS_TRAINLOG_CONFIG'] = '/cfg/trainlog_probe.json'
sys.path.insert(0, '/source')
from argparse import Namespace as NS
from common import *
import torch
from scipy.spatial import cKDTree
from scene import GaussianModel
from jbgs_finaltrain import FinalTrain
try:
    from jbgs_trainlog import TrainLog
except ImportError: TrainLog = None
try:
    from jbgs_trainerr import FinalTrainX
except ImportError: FinalTrainX = None
STEM = 'R1rep_b10__ALS'
def ckpt(probe, it=200): return O/'probe'/probe/f'model/jbgs_complete/iteration_{it}/checkpoint.pth'
def target_file(arm): return (FT/'targets' if arm == 'own' else GT/'targets_gt')/f'{STEM}.npz'

def build(cls, root, ck_path, arm, args=None):
    ck = torch.load(ck_path, map_location='cuda', weights_only=False); opt = NS(**ck['optimization'])
    g = GaussianModel(3); g.restore(ck['model'], opt)
    g.origin = ck['origin'].cuda(); g.init_id = ck['init_id'].cuda()
    for k, v in ck['target_r6']['meta'].items(): setattr(g, k, v.cuda())
    c = cls.__new__(cls); c.trainlog_on = False
    if args is not None and hasattr(c, 'init_intervene'): c.init_intervene(args)
    with np.load(target_file(arm)) as z:  # identical to TargetR6.__init__ target arrays
        c.valid_patch = np.flatnonzero((z['region'] >= 0) & np.isfinite(z['target']).all(1) & np.isfinite(z['normal']).all(1) & np.isfinite(z['sigma']) & (z['sigma'] > 0))
        c.points = np.asarray(z['target'][c.valid_patch], np.float64)
        c.patch_anchor = torch.tensor(c.points, device='cuda', dtype=torch.float32)
        c.patch_normal = torch.tensor(z['normal'][c.valid_patch], device='cuda', dtype=torch.float32)
        c.patch_sigma = torch.tensor(z['sigma'][c.valid_patch], device='cuda', dtype=torch.float32)
        c.patch_region = torch.tensor(z['region'][c.valid_patch], device='cuda', dtype=torch.int8)
    c.tree = cKDTree(c.points); c.mon = root/'target_monitor'; c.mon.mkdir(parents=True); c.iteration = int(ck['iteration']); c.events = []; c.n6000 = None
    c.ready = True; c.last_opacity_reset = -1; c._candidate_cache = None; g.target_r6 = c
    if TrainLog is not None and isinstance(c, TrainLog):
        c.tl_region_file = f'/te/region/{STEM}.json'; c.trainlog_grads_on = True; c.init_log(root, g)
    return g, c, opt, float(ck['model'][11])

def run(cls, root, ck_path, arm):
    torch.manual_seed(0); torch.cuda.manual_seed_all(0); random.seed(0); np.random.seed(0)
    g, c, opt, extent = build(cls, root, ck_path, arm); log = TrainLog is not None and isinstance(c, TrainLog); trace = []
    if log: c.trainlog_begin(g); c.iteration = 200
    for i in range(201, 501):
        c.iteration = i; g.update_learning_rate(i); g.optimizer.zero_grad(set_to_none=True)
        x = g._xyz.detach(); tgt = x+.02*torch.sin(x*3.1)+torch.rand_like(x)*.01
        push = (x[:, 0] > torch.quantile(x[:, 0], .9)).float()[:, None]
        a = ((g._xyz-tgt)**2).sum(1).mean(); b = 1e-3*(g._opacity*push).sum(); d = 1e-5*(g._scaling.square().sum()+g._features_dc.square().sum()+g._rotation.square().sum())
        loss = a+b+d
        if log: c.trainlog_grads(i, g, dict(photo=a, depth=b, gs2d=d))
        loss.backward()
        with torch.no_grad():
            gn = g._xyz.grad.norm(dim=1, keepdim=True); g.xyz_gradient_accum += .0002*gn/torch.quantile(gn, .98).clamp_min(1e-12); g.denom += 1
            g.max_radii2D = torch.maximum(g.max_radii2D, g.get_scaling.max(1).values*300)
            if i in [250, 350]:
                big = (torch.arange(len(x), device='cuda') % 31) == 0; g._scaling[big] += 1.5 if i == 250 else 3.
        g.optimizer.step()
        if i % 100 == 0: c.reattach(g, 'periodic')
        c.project_bounds(g)
        if i % 100 == 0 and i <= 400: g.densify_and_prune(opt.densify_grad_threshold, .005, extent, 20 if i > 300 else None)
        if i == 300:
            if log: c.trainlog_pre_reset(i, g)
            g.reset_opacity(); c.last_opacity_reset = i
        c.project_bounds(g)
        if log: c.trainlog_end(i, g, dict(rgb=loss, depth=loss, dist=loss, normal=loss, total=loss), 'synthetic')
        if i % 50 == 0: trace.append((i, len(g._xyz), int((g.target_tag == 1).sum()), int((g.target_tag == 2).sum())))
    if log: c.flush()
    m = g.capture(); state = dict(model=[t for t in m[1:10]], adam=m[10]['state'], meta={k: getattr(g, k) for k in ['target_tag', 'target_index', 'target_released_at', 'origin', 'init_id']},
        events=copy.deepcopy(c.events), rng=(random.getstate(), np.random.get_state()[1].tobytes(), torch.get_rng_state(), torch.cuda.get_rng_state()), trace=trace)
    return state, c

def equal(a, b):
    if torch.is_tensor(a): return a.dtype == b.dtype and a.shape == b.shape and bool(torch.equal(a, b))
    if isinstance(a, dict): return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)): return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if isinstance(a, np.ndarray): return np.array_equal(a, b)
    return a == b
PARTS = ['model', 'adam', 'meta', 'events', 'rng', 'trace']

def dump_one(name, arm, probe):
    torch.use_deterministic_algorithms(True); root = O/'verification'/f'replay_{name}'; root.mkdir(parents=True, exist_ok=False)
    st, _ = run(FinalTrain, root/'off', ckpt(probe), arm); torch.save(st, root/'state.pt')
    dump(root/'dump.json', dict(at=now(), name=name, arm=arm, start=str(ckpt(probe)), start_sha256=sha(ckpt(probe)), source=sorted(p.name for p in Path('/source').glob('jbgs_*.py')), trace=st['trace'], scientific_verdict=None))
    print('DUMPED', name, st['trace'], flush=True)

def compare(a, b):
    x = torch.load(O/'verification'/f'replay_{a}/state.pt', weights_only=False); y = torch.load(O/'verification'/f'replay_{b}/state.pt', weights_only=False)
    parts = {k: equal(x[k], y[k]) for k in PARTS}
    res = dict(at=now(), a=a, b=b, parts_byte_equal=parts, status='PASS' if all(parts.values()) else 'FAIL', trace=x['trace'], scientific_verdict=None)
    dump(O/'verification'/f'replay_compare_{a}_{b}.json', res); print(res['status'], parts, flush=True)

def record(arm, probe):
    torch.use_deterministic_algorithms(True); root = O/'verification'/f'replay_record_{arm}'; root.mkdir(parents=True, exist_ok=False)
    off, _ = run(FinalTrain, root/'off', ckpt(probe), arm); on, c = run(TrainLog, root/'on', ckpt(probe), arm)
    parts = {k: equal(off[k], on[k]) for k in PARTS}
    ev = {}
    for f in sorted((root/'on/trainlog/events').glob('*.npz')): kind = f.name.rsplit('_', 1)[0]; ev[kind] = ev.get(kind, 0)+len(np.load(f)['seq'])
    grads = sorted(int(p.stem) for p in (root/'on/trainlog/grads').glob('*.npz'))
    gz = loadz(root/'on/trainlog/grads'/f'{grads[-1]}.npz') if grads else {}
    res = dict(at=now(), arm=arm, start=str(ckpt(probe)), start_sha256=sha(ckpt(probe)), deterministic_algorithms=True, parts_byte_equal=parts,
        status='PASS' if all(parts.values()) and grads else 'FAIL', trace_off=off['trace'], trace_on=on['trace'], events_recorded=ev, gradient_iterations=grads,
        gradient_columns=sorted(gz), gradient_rows=len(gz.get('uid', [])), scientific_verdict=None)
    dump(O/'verification'/f'replay_record_{arm}.json', res); print(res['status'], parts, ev, grads[:3], flush=True)

def switches(probe, it):
    torch.use_deterministic_algorithms(True); out = []
    for sw in ['jbgs_bind_background', 'jbgs_rebind_released', 'jbgs_reassign_same']:
        root = O/'verification'/f'switch_{sw}_{probe}_{it}'
        g0, c0, _, _ = build(FinalTrain, root/'off', ckpt(probe, it), 'own'); before = {k: getattr(g0, k).clone() for k in ['target_tag', 'target_index']}; x0 = g0._xyz.detach().clone()
        c0.reattach(g0, 'periodic'); c0.project_bounds(g0)
        args = NS(**{k: ('on' if k == sw else 'off') for k in ['jbgs_bind_background', 'jbgs_rebind_released', 'jbgs_reassign_same']})
        g1, c1, _, _ = build(FinalTrainX, root/'on', ckpt(probe, it), 'own', args); c1.reattach(g1, 'periodic'); c1.project_bounds(g1)
        changed = (g0.target_tag != g1.target_tag) | (g0.target_index != g1.target_index) | (g0._xyz != g1._xyz).any(1)
        tag0 = before['target_tag']
        if sw == 'jbgs_bind_background': allowed = (tag0 == 0) & (g0.origin == 0); defined = allowed & (g1.target_tag == 1)
        elif sw == 'jbgs_rebind_released': allowed = (tag0 == 2) | ((tag0 == 1) & (g0.target_tag == 2)); defined = allowed & (g1.target_tag == 1)
        else:
            allowed = tag0 == 1
            # rows whose unconstrained choice already meets the same-judgment / height rule must keep the off decision
            rows = torch.where(tag0 == 1)[0]; cur = before['target_index'][rows]; new = g0.target_index[rows]
            reg = c0.patch_region; same = (reg[new] == reg[cur]) & ((((c0.patch_anchor[new]-c0.patch_anchor[cur]).double()*c0.patch_normal[cur].double()).sum(1).abs()) <= (1.96*c0.patch_sigma[cur]).double())
            keep = rows[same & (g0.target_tag[rows] == 1)]; defined = allowed
        outside = changed & ~allowed
        extra = int((changed[keep]).sum()) if sw == 'jbgs_reassign_same' else 0
        ok = int(outside.sum()) == 0 and extra == 0 and len(g0._xyz) == len(g1._xyz)
        out.append(dict(switch=sw, probe=probe, iteration=it, gaussians=len(g0._xyz), changed=int(changed.sum()), changed_outside_defined_set=int(outside.sum()),
                        kept_rows_changed=extra, defined_set=int(allowed.sum()), bound_after_on=int((g1.target_tag == 1).sum()), bound_after_off=int((g0.target_tag == 1).sum()),
                        released_after_on=int((g1.target_tag == 2).sum()), released_after_off=int((g0.target_tag == 2).sum()), status='PASS' if ok else 'FAIL'))
        print(out[-1], flush=True)
    dump(O/'verification'/f'switches_{probe}_{it}.json', dict(at=now(), rows=out, status='PASS' if all(r['status'] == 'PASS' for r in out) else 'FAIL', scientific_verdict=None))

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'dump': dump_one(a[1], a[2], a[3])
    elif a[0] == 'compare': compare(a[1], a[2])
    elif a[0] == 'record': record(a[1], a[2])
    elif a[0] == 'switches': switches(a[1], int(a[2]))
