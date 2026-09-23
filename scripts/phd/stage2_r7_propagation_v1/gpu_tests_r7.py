"""GPU checks of the r7 fork with the real GaussianModel (conf-guided image, /source = r7 fork, /r6 = r6 fork, one GPU):
  1) unchanged from r6: the lock (before_step / after_step / scale_locked_update), the opacity floor (floor_now), the
     reset exemption and rho_truncated are the same source text;
  2) per-row records follow densification and pruning (the wrapped densification_postfix / prune_points): new rows get
     no E / judgment, pruned rows disappear, and children reach their parent's surface through init_id;
  3) the protection rule of update_E_r7: a conflict judgment excludes a prior Gaussian with E < threshold; the drift bound
     is mult x tau of the surface kind;
  4) PLY columns: save_ply writes the columns of jbgs_ply_extra and load_ply still restores origin / init_id.
Prints GPU R7 TESTS PASSED on success."""
import importlib.util
import inspect
import sys
import tempfile
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
sys.path.insert(0, "/source")
from arguments import OptimizationParams  # noqa: E402
from plyfile import PlyData  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402
from utils.graphics_utils import BasicPointCloud  # noqa: E402
import jbgs_judgment as J  # noqa: E402
from src.phd.prior_propagation_v1 import rule as ppr  # noqa: E402

assert J.REVISION == "r7", J.REVISION
spec = importlib.util.spec_from_file_location("jbgs_judgment_r6", "/r6/jbgs_judgment.py")
R6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(R6)
assert R6.REVISION == "r6"

# 1) unchanged code
for name in ("before_step", "after_step", "floor_now", "exempt_mask"):
    assert inspect.getsource(getattr(J.Judgment, name)) == inspect.getsource(getattr(R6.Judgment, name)), f"{name} changed"
for name in ("scale_locked_update", "rho_truncated", "compute_E", "compute_E_render", "lock_rule_r6", "project_points"):
    assert inspect.getsource(getattr(J, name)) == inspect.getsource(getattr(R6, name)), f"{name} changed"
print("lock, floor, reset exemption and E functions unchanged from r6 ok")

parser = ArgumentParser(); op = OptimizationParams(parser); opt = op.extract(parser.parse_args([]))
N = 400
rs = np.random.RandomState(0); pts = rs.rand(N, 3); cols = rs.rand(N, 3)


def make():
    torch.manual_seed(0)
    m = GaussianModel(3)
    m.create_from_pcd(BasicPointCloud(points=pts, colors=cols, normals=np.zeros_like(pts)), 1.0)
    m.training_setup(opt)
    return m


# 2) per-row records through densification and pruning
g = make()
g.origin = torch.ones(N, dtype=torch.int8, device="cuda")
fake = SimpleNamespace(counters={"added": 0, "removed": 0})
for k in ("_rows_append", "_rows_keep"):
    setattr(fake, k, getattr(J.Judgment, k).__get__(fake))
fake.ROWS, fake.FILL = J.Judgment.ROWS, J.Judgment.FILL
fake.E = torch.linspace(0, 1, N, device="cuda"); fake.E_cnt = torch.ones(N, device="cuda")
fake.g_J = torch.full((N,), ppr.J_AGREE, dtype=torch.long, device="cuda"); fake.g_loc = torch.arange(N, device="cuda")
fake.g_located = torch.ones(N, dtype=torch.bool, device="cuda"); fake._g_surface = torch.arange(N, device="cuda") % 7
J.Judgment._wrap_counters(fake, g)
init_surface = (torch.arange(N, device="cuda") % 7).long()
g.xyz_gradient_accum = torch.zeros((N, 1), device="cuda"); g.denom = torch.ones((N, 1), device="cuda")
grads = torch.zeros((N, 1), device="cuda"); grads[:30] = 1.0
g.max_radii2D = torch.zeros(N, device="cuda")
g.densify_and_clone(grads, 0.5, 100.0)   # scene extent large enough that every selected disk is "small"
n1 = g.get_xyz.shape[0]
assert n1 == N + 30, n1
assert fake.E.shape[0] == n1 and bool(torch.isnan(fake.E[N:]).all()), "new rows must have no E"
assert bool((fake.g_J[N:] == -1).all()) and bool((fake.g_loc[N:] == -1).all()), "new rows must have no judgment / location"
children = torch.arange(N, n1, device="cuda")
assert bool((g.init_id[children] == g.init_id[:30]).all()), "children must carry the parent's init_id"
assert bool((init_surface[g.init_id[children].long()] == init_surface[:30]).all()), "children must reach the parent's surface"
mask = torch.zeros(n1, dtype=torch.bool, device="cuda"); mask[5:15] = True
kept_E = fake.E[~mask].clone()
g.prune_points(mask)
assert fake.E.shape[0] == n1 - 10 and torch.equal(fake.E[~torch.isnan(fake.E)], kept_E[~torch.isnan(kept_E)]), "pruning misaligned"
assert g.init_id.shape[0] == fake.g_loc.shape[0] == g.get_xyz.shape[0]
print("per-row records follow densification and pruning; children inherit the surface ok")

# 3) protection rule of update_E_r7 (conflict excluded, drift bound per kind), on a stub with the real method
n = 6
stub = SimpleNamespace()
stub.args = SimpleNamespace(jbgs_e_depth_tol=0.5, jbgs_e_alpha_min=0.05, jbgs_e_threshold=0.5, jbgs_lock_drift_tau_mult=4.0,
                            jbgs_lock_opacity_floor=0.5)
stub.tau_kind = {1: 0.1, 2: 0.2}
stub.mode = "P"; stub.render_fn = None; stub.E_calls = 0; stub.keep_maps = False; stub.tb = None
stub.mon = Path(tempfile.mkdtemp())
stub.train_cams = []; stub.A = {}; stub.P = {}
store_t = {"surf_kind": torch.tensor([1, 2], dtype=torch.int8, device="cuda")}
stub.prop = dict(st_t=store_t, E0=torch.tensor([0.2, 0.2, 0.2, 0.2, 0.9, 0.2], device="cuda"),
                 J=torch.tensor([ppr.J_AGREE, ppr.J_CONFLICT, ppr.J_INSUFF, ppr.J_MIXED, ppr.J_AGREE, ppr.J_AGREE], device="cuda"))
stub.init_xyz = torch.zeros((n, 3), device="cuda")
s_idx = torch.tensor([0, 0, 0, 1, 0, 1], device="cuda")
stub.seat_now = lambda gg: (torch.ones(n, dtype=torch.bool, device="cuda"), s_idx, torch.arange(n, device="cuda"))
stub.floor_now = lambda gg: None
gs = SimpleNamespace(get_xyz=torch.tensor([[0, 0, 0.3], [0, 0, 0], [0, 0, 0.39], [0, 0, 0.79], [0, 0, 0], [0, 0, 0.81]], device="cuda"),
                     origin=torch.ones(n, dtype=torch.int8, device="cuda"), init_id=torch.arange(n, dtype=torch.int32, device="cuda"),
                     frozen_mask=torch.zeros(n, dtype=torch.bool, device="cuda"))
gs.set_frozen_mask = lambda m: setattr(gs, "frozen_mask", m)
row = J.Judgment.update_E_r7(stub, 1, gs)
want = [True, False, True, True, False, False]   # conflict excluded; E 0.9 free; wall bound 0.8 m: 0.79 in, 0.81 out
assert gs.frozen_mask.cpu().tolist() == want, gs.frozen_mask.cpu().tolist()
assert row["n_conflict_excluded"] == 1, row
print("protection: conflict excluded, E threshold, drift bound per surface kind ok")

# 4) PLY columns
g4 = make()
g4.origin = torch.ones(N, dtype=torch.int8, device="cuda")
ext = {"surface_id": np.arange(N, dtype=np.int32) - 3, "judgment": np.full(N, 2, np.int32), "gconf": np.linspace(0, 1, N).astype(np.float32)}
g4.jbgs_ply_extra = lambda: ext
with tempfile.TemporaryDirectory() as d:
    path = str(Path(d) / "pc.ply")
    g4.save_ply(path)
    el = PlyData.read(path).elements[0]
    for k, v in ext.items():
        assert np.array_equal(np.asarray(el[k]), v), k
    g5 = GaussianModel(3); g5.load_ply(path)
    assert g5.origin is not None and int(g5.origin.sum()) == N and g5.init_id is not None
print("PLY columns written and read ok")
print("GPU R7 TESTS PASSED")
