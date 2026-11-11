"""Deterministic real-state replay (stage-1 supplement to order 2.5 '결정 불변').

Start: complete state of probe r27_off_a at iteration 200 (real B173nb_b10 x ALS scene, real FINALTRAIN targets).
Same deterministic synthetic loss/densification statistics drive the unchanged r23 controller + GaussianModel code
(Adam, 100-step reattach, project_bounds, clone/split/prune with opacity/world/screen culls, opacity reset) for 300
iterations, once with FinalTrain (recording off) and once with TrainLog (recording on, all hooks called).
PASS = model, Adam state, density statistics, target metadata, controller events and RNG states byte-identical."""
import os, sys, random, copy
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8'); os.environ['JBGS_TRAINLOG_CONFIG'] = '/tl/probe/trainlog_probe.json'
sys.path.insert(0, '/source')
from argparse import Namespace as NS
from common import *
import torch
from scipy.spatial import cKDTree
from scene import GaussianModel
from jbgs_finaltrain import FinalTrain
try:
    from jbgs_trainlog import TrainLog
except ImportError:  # r23 has no recording module
    TrainLog = None
CK = O/'probe/r27_off_a/model/jbgs_complete/iteration_200/checkpoint.pth'

def build(cls, root):
    ck = torch.load(CK, map_location='cuda', weights_only=False); opt = NS(**ck['optimization'])
    g = GaussianModel(3); g.restore(ck['model'], opt)
    g.origin = ck['origin'].cuda(); g.init_id = ck['init_id'].cuda()
    for k, v in ck['target_r6']['meta'].items(): setattr(g, k, v.cuda())
    c = cls.__new__(cls); c.trainlog_on = False
    with np.load(FT/'targets'/f'{STEM}.npz') as z:  # identical to TargetR6.__init__ target arrays
        c.valid_patch = np.flatnonzero((z['region'] >= 0) & np.isfinite(z['target']).all(1) & np.isfinite(z['normal']).all(1) & np.isfinite(z['sigma']) & (z['sigma'] > 0))
        c.points = np.asarray(z['target'][c.valid_patch], np.float64)
        c.patch_anchor = torch.tensor(c.points, device='cuda', dtype=torch.float32)
        c.patch_normal = torch.tensor(z['normal'][c.valid_patch], device='cuda', dtype=torch.float32)
        c.patch_sigma = torch.tensor(z['sigma'][c.valid_patch], device='cuda', dtype=torch.float32)
        c.patch_region = torch.tensor(z['region'][c.valid_patch], device='cuda', dtype=torch.int8)
    c.tree = cKDTree(c.points); c.mon = root/'target_monitor'; c.mon.mkdir(parents=True); c.iteration = 200; c.events = []; c.n6000 = None
    c.ready = True; c.last_opacity_reset = -1; c._candidate_cache = None; g.target_r6 = c
    if cls is TrainLog: c.init_log(root, g)
    return g, c, opt, float(ck['model'][11])

def run(cls, root):
    torch.manual_seed(0); torch.cuda.manual_seed_all(0); random.seed(0); np.random.seed(0)
    g, c, opt, extent = build(cls, root); log = cls is TrainLog; trace = []
    if log: c.trainlog_begin(g); c.iteration = 200
    for i in range(201, 501):
        c.iteration = i; g.update_learning_rate(i); g.optimizer.zero_grad(set_to_none=True)
        x = g._xyz.detach(); tgt = x+.02*torch.sin(x*3.1)+torch.rand_like(x)*.01
        push = (x[:, 0] > torch.quantile(x[:, 0], .9)).float()[:, None]
        loss = ((g._xyz-tgt)**2).sum(1).mean()+1e-3*(g._opacity*push).sum()+1e-5*(g._scaling.square().sum()+g._features_dc.square().sum()+g._rotation.square().sum())
        loss.backward()
        with torch.no_grad():
            gn = g._xyz.grad.norm(dim=1, keepdim=True); g.xyz_gradient_accum += .0002*gn/torch.quantile(gn, .98).clamp_min(1e-12); g.denom += 1
            g.max_radii2D = torch.maximum(g.max_radii2D, g.get_scaling.max(1).values*300)
            if i in [250, 350]:  # deterministic enlargement so split, world-size and screen-size paths run
                big = (torch.arange(len(x), device='cuda') % 31) == 0; g._scaling[big] += 1.5 if i == 250 else 3.
        g.optimizer.step()
        if i % 100 == 0: c.reattach(g, 'periodic')
        c.project_bounds(g)
        if i % 100 == 0 and i <= 400:
            g.densify_and_prune(opt.densify_grad_threshold, .005, extent, 20 if i > 300 else None)
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

def dump_off(name):
    torch.use_deterministic_algorithms(True); root = O/'verification'/f'replay_{name}'; root.mkdir(parents=True, exist_ok=False)
    st, _ = run(FinalTrain, root/'off'); torch.save({k: v for k, v in st.items()}, root/'state.pt'); print('DUMPED', name, st['trace'], flush=True)

def compare_dumps(a, b):
    x = torch.load(O/'verification'/f'replay_{a}/state.pt', weights_only=False); y = torch.load(O/'verification'/f'replay_{b}/state.pt', weights_only=False)
    parts = {k: equal(x[k], y[k]) for k in ['model', 'adam', 'meta', 'events', 'rng', 'trace']}
    res = dict(at=now(), a=a, b=b, parts_byte_equal=parts, status='PASS' if all(parts.values()) else 'FAIL', trace=x['trace'], scientific_verdict=None)
    dump(O/'verification'/f'replay_compare_{a}_{b}.json', res); print(json.dumps(res, default=str), flush=True)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'dump': return dump_off(sys.argv[2])
    if len(sys.argv) > 1 and sys.argv[1] == 'compare': return compare_dumps(sys.argv[2], sys.argv[3])
    torch.use_deterministic_algorithms(True)
    root = O/'verification/replay'; root.mkdir(parents=True, exist_ok=False)
    off, _ = run(FinalTrain, root/'off'); on, c = run(TrainLog, root/'on')
    parts = {k: equal(off[k], on[k]) for k in ['model', 'adam', 'meta', 'events', 'rng', 'trace']}
    ev = {}
    for f in sorted((root/'on/trainlog/events').glob('*.npz')):
        kind = f.name.rsplit('_', 1)[0]; ev[kind] = ev.get(kind, 0)+len(np.load(f)['seq'])
    dele = {}
    for f in sorted((root/'on/trainlog/events').glob('delete_*.npz')):
        for r, n in zip(*np.unique(np.load(f)['reason'], return_counts=True)): dele[int(r)] = dele.get(int(r), 0)+int(n)
    births = {}
    for f in sorted((root/'on/trainlog/events').glob('birth_*.npz')):
        for r, n in zip(*np.unique(np.load(f)['how'], return_counts=True)): births[int(r)] = births.get(int(r), 0)+int(n)
    res = dict(at=now(), start=str(CK), start_sha256=sha(CK), iterations=[201, 500], deterministic_algorithms=True, parts_byte_equal=parts,
        status='PASS' if all(parts.values()) else 'FAIL', trace_off=off['trace'], trace_on=on['trace'], events_recorded=ev, delete_reasons=dele, birth_how=births,
        controller_events=len(off['events']), extent=float(torch.load(CK, map_location='cpu', weights_only=False)['model'][11]), scientific_verdict=None)
    dump(O/'verification/replay_test.json', res); print(json.dumps(res, default=str)[:3000], flush=True)
if __name__ == '__main__': main()
