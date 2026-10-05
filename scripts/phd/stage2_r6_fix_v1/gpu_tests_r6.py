"""GPU checks of the r6 fork with the real GaussianModel (conf-guided image, /source = r6 fork, one GPU):
  1) lock unchanged from r5: locked rows move lock_lr_scale x the step of an identical unlocked model, free rows equal,
  2) r6 (3) floor_now: protected disks are at >= 0.5 right after the mask is set, others untouched,
  3) r6 (4) init_visible_filter with the real prune_points: origin/init_id/frozen/optimizer tensors stay aligned,
  4) r6 (5) pixel normalisation on CUDA tensors equals the CPU definition.
Prints GPU R6 TESTS PASSED on success."""
import sys
from argparse import ArgumentParser
from types import SimpleNamespace

import numpy as np
import torch
sys.path.insert(0, "/source")
from arguments import OptimizationParams  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402
from utils.graphics_utils import BasicPointCloud, getWorld2View2, getProjectionMatrix, focal2fov  # noqa: E402
import jbgs_judgment as J  # noqa: E402

assert J.REVISION == "r6", J.REVISION
parser = ArgumentParser(); op = OptimizationParams(parser); opt = op.extract(parser.parse_args([]))
N = 1000
rs = np.random.RandomState(0); pts = rs.rand(N, 3) * 0.1; cols = rs.rand(N, 3)


def make(points=pts):
    torch.manual_seed(0)
    m = GaussianModel(3)
    m.create_from_pcd(BasicPointCloud(points=points, colors=cols[:len(points)], normals=np.zeros_like(points)), 1.0)
    m.training_setup(opt)
    return m


def loss(m):
    return ((m._xyz ** 2).sum() + (m._rotation ** 2).sum() + (m._scaling ** 2).sum() + m._opacity.sum()
            + (m._features_dc ** 2).sum() + (m._features_rest ** 2).sum())


# 1) lock unchanged
g, ref = make(), make()
lock = torch.zeros(N, dtype=torch.bool, device="cuda"); lock[:100] = True; g.set_frozen_mask(lock)
judg = SimpleNamespace(mode="P", args=SimpleNamespace(jbgs_lock_lr_scale=0.01, jbgs_lock_opacity_floor=0.5), _saved=None)
names = ("_xyz", "_rotation", "_scaling")
before = {n: getattr(g, n).detach().clone() for n in names}
for m in (g, ref):
    m.optimizer.zero_grad(set_to_none=True)
    loss(m).backward()
J.Judgment.before_step(judg, g)
g.optimizer.step(); ref.optimizer.step()
J.Judgment.after_step(judg, g)
for n in names:
    dg = getattr(g, n).detach() - before[n]; dr = getattr(ref, n).detach() - before[n]
    tol = 0.02 * (0.01 * dr[:100].abs()) + 2 * torch.finfo(torch.float32).eps * before[n][:100].abs()
    assert bool(((dg[:100] - 0.01 * dr[:100]).abs() <= tol).all()), f"{n}: locked rows not scaled to 0.01"
    assert torch.allclose(dg[100:], dr[100:], rtol=1e-5, atol=1e-9), f"{n}: free rows differ"
print("lock unchanged ok")

# 2) floor at the moment of protection
g2 = make()
with torch.no_grad():
    g2._opacity.data[:] = g2.inverse_opacity_activation(torch.full_like(g2._opacity, 0.02))
    g2._opacity.data[900:] = g2.inverse_opacity_activation(torch.full_like(g2._opacity[900:], 0.8))
m2 = torch.zeros(N, dtype=torch.bool, device="cuda"); m2[:50] = True; m2[900:950] = True
g2.set_frozen_mask(m2)
J.Judgment.floor_now(judg, g2)
opn = g2.get_opacity.detach().squeeze(-1)
assert bool((opn[:50] >= 0.5 - 1e-6).all()), "protected low-opacity disks not floored"
assert bool(torch.allclose(opn[900:950], torch.full_like(opn[900:950], 0.8), atol=1e-6)), "protected high opacity changed"
assert bool(torch.allclose(opn[50:900], torch.full_like(opn[50:900], 0.02), atol=1e-6)), "unprotected disks changed"
print("floor at protection ok")

# 3) init filter with the real prune_points
W, H, FX, FY, CX, CY = 160, 120, 200.0, 205.0, 82.3, 58.7
wvt = torch.tensor(getWorld2View2(np.eye(3), np.zeros(3))).transpose(0, 1).cuda()
proj = getProjectionMatrix(znear=0.01, zfar=100.0, fovX=focal2fov(FX, W), fovY=focal2fov(FY, H)).transpose(0, 1)
p = proj.T.clone(); p[0, 0] = 2 * FX / W; p[1, 1] = 2 * FY / H; p[0, 2] = (2 * CX + 1 - W) / W; p[1, 2] = (2 * CY + 1 - H) / H
proj = p.T.contiguous().cuda()
cam = SimpleNamespace(image_name="v0", image_width=W, image_height=H, world_view_transform=wvt, full_proj_transform=wvt @ proj)
pts3 = np.zeros((N, 3)); pts3[:, 2] = 10.0; pts3[:, 0] = rs.uniform(-2, 2, N)
pts3[300:600, 2] = 15.0                         # 5 m behind the prior surface: unseen
pts3[800:, 2] = 15.0                            # image-origin points behind the surface: must be kept anyway
g3 = make(pts3)
g3.origin[:600] = 1                             # 0-299 prior seen, 300-599 prior unseen, 600-999 image (half of them unseen too)
g3.init_id = torch.arange(N, dtype=torch.int32, device="cuda")
g3.frozen_mask = torch.zeros(N, dtype=torch.bool, device="cuda")
Pm = {"v0": torch.full((H, W), 10.0, device="cuda")}
Am = {"v0": torch.ones((H, W), device="cuda")}
info = J.init_visible_filter(g3, [cam], Am, Pm, 0.5)
n3 = g3.get_xyz.shape[0]
assert info["n_prior_dropped"] == 300 and n3 == 700, info
assert g3.origin.shape[0] == n3 and g3.init_id.shape[0] == n3 and g3.frozen_mask.shape[0] == n3, "per-disk length drift"
assert g3.xyz_gradient_accum.shape[0] == n3 and g3.max_radii2D.shape[0] == n3, "density tensors misaligned"
for grp in g3.optimizer.param_groups:
    assert grp["params"][0].shape[0] == n3, grp["name"]
kept = g3.init_id.cpu().numpy()
assert np.array_equal(kept, np.r_[np.arange(300), np.arange(600, 1000)]), "wrong rows kept"
print("init filter ok", info["n_prior_before"], "->", info["n_prior_kept"])

# 4) pixel normalisation
D = torch.rand(H, W, device="cuda") + 5; M = D + 0.1; A = (torch.rand(H, W, device="cuda") > 0.5).float()
l_new, _, _ = J.weighted_l1(D, M, A, float(D.numel()))
assert abs(float(l_new) - float((0.1 * A).sum() / D.numel())) < 1e-6, float(l_new)
print("pixel normalisation ok")
print("GPU R6 TESTS PASSED")
