"""GPU code tests of fork r11 (conf-guided image; /source = r11 fork, /r10src = r10 fork, /repo; one GPU; no training run).
PHD-MAIN-PREP-DISCARD-RULE-v1 5.1.
  A) unchanged from r10, letter for letter: every function and method of jbgs_judgment except the patched ones (register_args,
     Judgment.__init__, prop_init, _g_init, losses, update_E_r8, dry_init_report) and the new helpers; train.py and
     scene/gaussian_model.py byte-identical.
  B) defaults: every --jbgs_sw_* = 1 and --jbgs_rule current (= r10).
  C) penalty function (switch prior_band): test residuals r = -6 tau .. 6 tau; band on = rho_truncated (0 within tau, |r| - tau
     up to 4 tau, constant beyond), off = |r|; the plain prior loss equals the weighted mean |D - P| on a synthetic map.
  D) protection (switch protection) on a synthetic scene of 40 Gaussians (the real GaussianModel): protection_mask on = eq. (7),
     off = empty; one Adam step with the protected rows scaled by lock_lr_scale (before_step / after_step) -> protected rows
     move 1/100 of the free rows, with the switch off every row moves fully; densify_and_prune keeps protected rows that the
     opacity rule would prune, with the switch off they are pruned; reset_opacity keeps the protected opacity, off resets all.
Writes /p/gpu_tests_r11.json and prints GPU R11 TESTS PASSED on success."""
import inspect
import importlib.util
import json
import sys
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

sys.path.insert(0, "/source")
import jbgs_judgment as J  # noqa: E402
from arguments import OptimizationParams  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402
from utils.graphics_utils import BasicPointCloud  # noqa: E402

assert J.REVISION == "r11", J.REVISION
out = {}

# ---------------------------------------------------------------- A) unchanged from r10
spec = importlib.util.spec_from_file_location("jbgs_judgment_r10", "/r10src/jbgs_judgment.py")
R10 = importlib.util.module_from_spec(spec)
sys.modules["jbgs_judgment_r10"] = R10
spec.loader.exec_module(R10)
PATCHED = {"register_args", "__init__", "prop_init", "_g_init", "losses", "update_E_r8", "dry_init_report"}
NEW = {"plain_prior_loss", "rho_plain", "protection_mask"}
diff = []
for name, obj in inspect.getmembers(R10, inspect.isfunction):
    if obj.__module__ != R10.__name__ or name in PATCHED:
        continue
    if inspect.getsource(obj) != inspect.getsource(getattr(J, name)):
        diff.append(name)
for name, obj in inspect.getmembers(R10.Judgment, inspect.isfunction):
    if name in PATCHED:
        continue
    if inspect.getsource(obj) != inspect.getsource(getattr(J.Judgment, name)):
        diff.append("Judgment." + name)
assert not diff, diff
assert NEW <= set(dir(J))
for f in ("train.py", "scene/gaussian_model.py"):
    assert Path("/source", f).read_bytes() == Path("/r10src", f).read_bytes(), f
out["A_unchanged_from_r10"] = dict(functions_checked=len([1 for n, o in inspect.getmembers(R10, inspect.isfunction) if o.__module__ == R10.__name__]),
                                   methods_checked=len(inspect.getmembers(R10.Judgment, inspect.isfunction)), differing=diff, train_and_gaussian_model_identical=True)

# ---------------------------------------------------------------- B) defaults
p = ArgumentParser(); J.register_args(p); d = p.parse_args([])
assert all(getattr(d, f"jbgs_sw_{n}") == 1 for n in ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior"))
assert d.jbgs_rule == "current"
out["B_defaults"] = dict(switches_all_on=True, rule="current")

# ---------------------------------------------------------------- C) penalty function
tau = torch.tensor(0.2, device="cuda")
r = torch.linspace(-6, 6, 25, device="cuda") * tau
on = J.rho_truncated(r, tau, 4.0); off = J.rho_plain(r, tau, 4.0)
a = r.abs()
assert torch.allclose(on, torch.where(a <= tau, torch.zeros_like(a), torch.minimum(a - tau, 3 * tau)))
assert torch.allclose(off, a)
D = torch.full((6, 8), 10.0, device="cuda"); Pm = D + torch.linspace(-1, 1, 48, device="cuda").reshape(6, 8)
T = torch.full_like(D, 0.2); w = torch.ones_like(D)
lp, n_, h_, b_ = J.plain_prior_loss(D, Pm, T, w)
assert abs(float(lp) - float((D - Pm).abs().mean())) < 1e-6 and b_ == 0
lt, *_ = J.truncated_prior_loss(D, Pm, T, w, 4.0)
out["C_penalty"] = dict(r_over_tau=(r / tau).tolist(), band_on=(on / tau).tolist(), band_off=(off / tau).tolist(),
                        plain_loss=float(lp), truncated_loss=float(lt), shape_band_on="0 within tau, |r|-tau to 4 tau, 3 tau beyond", shape_band_off="|r|")

# ---------------------------------------------------------------- D) protection on 40 Gaussians
torch.manual_seed(0)
n = 40
pts = np.random.default_rng(0).uniform(-1, 1, (n, 3))
pcd = BasicPointCloud(points=pts, colors=np.full((n, 3), 0.5), normals=np.zeros((n, 3)))
pp = ArgumentParser(); opg = OptimizationParams(pp); opt = opg.extract(pp.parse_args([]))


def fresh():
    g = GaussianModel(3)
    g.create_from_pcd(pcd, 1.0)
    g.training_setup(opt)
    g.origin = torch.ones(n, dtype=torch.int8, device="cuda")
    g.init_id = torch.arange(n, dtype=torch.int32, device="cuda")
    return g


prior = torch.ones(n, dtype=torch.bool, device="cuda")
E = torch.linspace(0, 1, n, device="cuda")
u = torch.zeros(n, device="cuda"); bound = torch.full((n,), 0.8, device="cuda")
pj = torch.full((n,), -1, dtype=torch.long, device="cuda"); pj[:5] = 0      # J_CONFLICT on 5 rows
lock_on, *_ = J.protection_mask(True, prior, E, 0.5, u, bound, pj)
lock_off, *_ = J.protection_mask(False, prior, E, 0.5, u, bound, pj)
ref, *_ = J.ppr.protected(prior, E, 0.5, u, bound, pj)
assert torch.equal(lock_on, ref) and not bool(lock_off.any()) and int(lock_on.sum()) > 0
args = SimpleNamespace(jbgs_lock_lr_scale=0.01, jbgs_lock_opacity_floor=0.5)
res = {}
for tag, lock in (("on", lock_on), ("off", lock_off)):
    g = fresh(); g.set_frozen_mask(lock)
    ctl = SimpleNamespace(mode="P", args=args, _saved=None)
    x0 = g.get_xyz.detach().clone()
    loss = (g.get_xyz ** 2).sum(); loss.backward()
    J.Judgment.before_step(ctl, g); g.optimizer.step(); J.Judgment.after_step(ctl, g); g.optimizer.zero_grad(set_to_none=True)
    mv = (g.get_xyz.detach() - x0).norm(dim=1)
    fr = lock if bool(lock.any()) else torch.zeros(n, dtype=torch.bool, device="cuda")
    ratio = float(mv[fr].mean() / mv[~fr].mean()) if bool(fr.any()) else 1.0
    # density control: every opacity below the cull level
    g2 = fresh(); g2.set_frozen_mask(lock)
    g2._opacity.data[:] = g2.inverse_opacity_activation(torch.full_like(g2._opacity.data, 0.001))
    g2.max_radii2D = torch.zeros(n, device="cuda"); g2.xyz_gradient_accum = torch.zeros((n, 1), device="cuda"); g2.denom = torch.ones((n, 1), device="cuda")
    g2.densify_and_prune(1e9, 0.005, 1.0, None)
    kept = int(g2.get_xyz.shape[0])
    # opacity reset
    g3 = fresh(); g3.set_frozen_mask(lock)
    (g3.get_opacity.sum() + (g3.get_xyz ** 2).sum()).backward(); g3.optimizer.step(); g3.optimizer.zero_grad(set_to_none=True)   # Adam state exists
    g3._opacity.data[:] = g3.inverse_opacity_activation(torch.full_like(g3._opacity.data, 0.9))
    g3.reset_opacity(exempt_mask=g3.frozen_mask)
    op3 = g3.get_opacity.detach().squeeze()
    res[tag] = dict(protected=int(lock.sum()), move_ratio_protected_over_free=ratio, kept_after_prune=kept,
                    reset_kept_opacity=int((op3 > 0.5).sum()))
assert abs(res["on"]["move_ratio_protected_over_free"] - 0.01) < 0.002, res
assert res["off"]["protected"] == 0 and res["off"]["kept_after_prune"] == 0 and res["off"]["reset_kept_opacity"] == 0, res
assert res["on"]["kept_after_prune"] == res["on"]["protected"] and res["on"]["reset_kept_opacity"] == res["on"]["protected"], res
out["D_protection"] = res
Path("/p/gpu_tests_r11.json").write_text(json.dumps(dict(tests=out, scientific_verdict=None), indent=1))
print(json.dumps(res))
print("GPU R11 TESTS PASSED")
