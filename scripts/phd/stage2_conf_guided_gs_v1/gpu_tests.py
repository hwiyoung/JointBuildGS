"""GPU checks of the patched GaussianModel and the judgment lock (needs the conf-guided image and a GPU), in the order
of a training iteration:
  1) backward + Adam step with the lock: locked rows move lock_lr_scale x the step of an identical unlocked model,
     free rows move exactly like it (xyz, rotation, scaling),
  2) opacity floor of locked disks,
  3) opacity-reset exemption (needs the Adam state created by the step in 1, as in real training),
  4) clone/split: origin and init_id inherited by children, locked disks excluded,
  5) prune keeps origin/init_id/frozen aligned,
  6) PLY round trip of origin and init_id.
Prints GPU TESTS PASSED on success."""
import sys
from argparse import ArgumentParser
from types import SimpleNamespace
import numpy as np
import torch
sys.path.insert(0, "/source")
from arguments import OptimizationParams
from scene.gaussian_model import GaussianModel
from utils.graphics_utils import BasicPointCloud
import jbgs_judgment as J

parser = ArgumentParser(); op = OptimizationParams(parser); opt = op.extract(parser.parse_args([]))
N = 1000
# small coordinates: a locked xyz step (lr 1.6e-4 x 0.01) must span many float32 steps of the coordinate itself
rs = np.random.RandomState(0); pts = rs.rand(N, 3) * 0.1; cols = rs.rand(N, 3)


def make():
    torch.manual_seed(0)  # create_from_pcd draws random rotations
    m = GaussianModel(3)
    m.create_from_pcd(BasicPointCloud(points=pts, colors=cols, normals=np.zeros_like(pts)), 1.0)
    m.training_setup(opt)
    return m


def loss(m):
    return ((m._xyz ** 2).sum() + (m._rotation ** 2).sum() + (m._scaling ** 2).sum() + m._opacity.sum()
            + (m._features_dc ** 2).sum() + (m._features_rest ** 2).sum())


g, ref = make(), make()
assert torch.equal(g._rotation, ref._rotation), "reference model differs"
assert g.origin is not None and g.origin.shape[0] == N, "origin not initialised by create_from_pcd"
assert g.init_id is not None and torch.equal(g.init_id.cpu(), torch.arange(N, dtype=torch.int32)), "init_id not initialised"
g.origin[:400] = 1
init_origin = g.origin.clone()
lock = torch.zeros(N, dtype=torch.bool, device="cuda"); lock[:100] = True; g.set_frozen_mask(lock)
judg = SimpleNamespace(mode="P", args=SimpleNamespace(jbgs_lock_lr_scale=0.01, jbgs_lock_opacity_floor=0.5), _saved=None)
names = ("_xyz", "_rotation", "_scaling")

# 1) locked Adam step
before = {n: getattr(g, n).detach().clone() for n in names}
for m in (g, ref):
    m.optimizer.zero_grad(set_to_none=True)
    loss(m).backward()
J.Judgment.before_step(judg, g)
g.optimizer.step(); ref.optimizer.step()
J.Judgment.after_step(judg, g)
for n in names:
    dg = getattr(g, n).detach() - before[n]; dr = getattr(ref, n).detach() - before[n]
    assert float(dr[:100].abs().max()) > 0, f"{n}: reference did not move"
    tol = 0.02 * (0.01 * dr[:100].abs()) + 2 * torch.finfo(torch.float32).eps * before[n][:100].abs()
    assert bool(((dg[:100] - 0.01 * dr[:100]).abs() <= tol).all()), f"{n}: locked rows not scaled to 0.01"
    assert torch.allclose(dg[100:], dr[100:], rtol=1e-5, atol=1e-9), f"{n}: free rows differ from the reference"
print("lock (Adam update x0.01) ok")

# 2) opacity floor
with torch.no_grad():
    g._opacity.data[:] = g.inverse_opacity_activation(torch.full_like(g._opacity, 0.05))
J.Judgment.after_step(judg, g)
op_now = g.get_opacity.detach().squeeze(-1)
assert bool((op_now[:100] >= 0.5 - 1e-5).all()) and bool((op_now[100:] < 0.06).all()), "opacity floor wrong"
print("opacity floor ok")

# 3) opacity reset exemption
before_op = g.get_opacity.detach().clone()
g.reset_opacity(exempt_mask=g.frozen_mask)
after_op = g.get_opacity.detach()
assert torch.allclose(after_op[:100], before_op[:100], atol=1e-6), "locked opacities changed by reset"
assert bool((after_op[100:] <= 0.01 + 1e-6).all()), "unlocked opacities not reset"
print("reset exemption ok")

# 4) clone/split: each selected parent nets +1 disk of its own origin and init_id; locked parents excluded
g.xyz_gradient_accum[:] = 0.0; g.denom[:] = 1.0
with torch.no_grad():  # extent 10 -> split above max scale 0.1, clone below: exercise both
    g._scaling.data[:] = float(np.log(0.01))
    g._scaling.data[200:250] = float(np.log(0.5)); g._scaling.data[500:550] = float(np.log(0.5))
g.xyz_gradient_accum[0:50] = 1.0       # locked prior: must be excluded
g.xyz_gradient_accum[200:300] = 1.0    # free prior
g.xyz_gradient_accum[500:600] = 1.0    # image
n_prior0, n_img0 = int((g.origin == 1).sum()), int((g.origin == 0).sum())
g.densify_and_prune(0.5, 0.0, 10.0, None)
n1 = g.get_xyz.shape[0]
assert g.origin.shape[0] == n1 and g.frozen_mask.shape[0] == n1 and g.init_id.shape[0] == n1, "per-disk length drift"
assert int((g.origin == 1).sum()) == n_prior0 + 100, (n_prior0, int((g.origin == 1).sum()))
assert int((g.origin == 0).sum()) == n_img0 + 100, (n_img0, int((g.origin == 0).sum()))
assert int(g.frozen_mask.sum()) == 100, "locked disks were split/cloned or lost"
assert bool(g.origin[g.frozen_mask].eq(1).all()), "locked disks are not prior-origin after densify"
ids, counts = torch.unique(g.init_id.long(), return_counts=True)
expect = torch.ones(N, dtype=torch.long, device="cuda"); expect[200:300] = 2; expect[500:600] = 2
assert int(ids.min()) >= 0 and ids.numel() == N and torch.equal(counts, expect), "init_id not inherited one-to-one"
assert torch.equal(g.origin, init_origin[g.init_id.long()]), "origin and init_id disagree"
print("inheritance ok", n1)

# 5) prune alignment
mask = torch.zeros(n1, dtype=torch.bool, device="cuda"); mask[150:170] = True
o_b, f_b, i_b = g.origin[~mask].clone(), g.frozen_mask[~mask].clone(), g.init_id[~mask].clone()
g.prune_points(mask)
assert torch.equal(g.origin, o_b) and torch.equal(g.frozen_mask, f_b) and torch.equal(g.init_id, i_b), "prune misaligned"
print("prune alignment ok")

# 6) PLY round trip
g.save_ply("/tmp/jbgs_test.ply")
g2 = GaussianModel(3); g2.load_ply("/tmp/jbgs_test.ply")
assert torch.equal(g2.origin.cpu(), g.origin.cpu()), "origin lost in PLY round trip"
assert torch.equal(g2.init_id.cpu(), g.init_id.cpu()), "init_id lost in PLY round trip"
print("ply round trip ok")
print("GPU TESTS PASSED")
