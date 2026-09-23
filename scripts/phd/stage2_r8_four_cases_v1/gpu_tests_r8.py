"""GPU checks of the r8 fork with the real GaussianModel (conf-guided image, /source = r8 fork, /r7src = r7 fork, one GPU):
  1) unchanged from r7: the lock (before_step / after_step / scale_locked_update), the opacity floor (floor_now), the reset
     exemption, rho_truncated, project_points and the density-control exemptions of scene/gaussian_model.py;
  2) g_p maps (decision 1 / 3): _g_init on synthetic unit / mark / confidence maps gives the expected g_p in every case,
     for pixels with and without a judgment unit;
  3) the prior depth term uses g_p: where c_p = 1 and g_p = 1 it pulls (r7 weighted it by 1 - c_p = 0), where g_p = 0 it
     does not, and the MVS term keeps c_p;
  4) invisible Gaussians (decision 7): first confidence 0 -> protected, opacity floor 0.5, kept by the opacity reset and by
     densify_and_prune while the unprotected transparent ones are pruned;
  5) protection rule of eq. (7) with u measured like the residuals: a move along the roof plane keeps the protection, a
     vertical move beyond 4 tau releases it (reason recorded), a propagated conflict excludes, c-bar >= 0.5 releases;
     a Gaussian without a unit uses the vertical offset and the roof tau;
  6) removal history (decision 6): an initial disk whose last Gaussian is pruned gets the iteration and its opacity; a split
     parent whose children carry its id is not removed.
Prints GPU R8 TESTS PASSED on success."""
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
from scene.gaussian_model import GaussianModel  # noqa: E402
from utils.graphics_utils import BasicPointCloud  # noqa: E402
import jbgs_judgment as J  # noqa: E402
from src.phd.prior_propagation_v2 import rule as ppr  # noqa: E402

assert J.REVISION == "r8", J.REVISION
spec = importlib.util.spec_from_file_location("jbgs_judgment_r7", "/r7src/jbgs_judgment.py")
sys.path.insert(0, "/r7src")
R7 = importlib.util.module_from_spec(spec); spec.loader.exec_module(R7)
assert R7.REVISION == "r7"

# 1) unchanged code
for name in ("before_step", "after_step", "floor_now", "exempt_mask"):
    assert inspect.getsource(getattr(J.Judgment, name)) == inspect.getsource(getattr(R7.Judgment, name)), f"{name} changed"
for name in ("scale_locked_update", "rho_truncated", "project_points", "truncated_prior_loss", "weighted_l1"):
    assert inspect.getsource(getattr(J, name)) == inspect.getsource(getattr(R7, name)), f"{name} changed"
gm8 = Path("/source/scene/gaussian_model.py").read_text(); gm7 = Path("/r7src/scene/gaussian_model.py").read_text()
assert gm8 == gm7, "gaussian_model.py changed"
assert Path("/source/train.py").read_text() == Path("/r7src/train.py").read_text(), "train.py changed"
print("lock, floor, reset exemption, losses' helpers, density control and train.py unchanged from r7 ok")

parser = ArgumentParser(); op = OptimizationParams(parser); opt = op.extract(parser.parse_args([]))
dev = "cuda"

# 2) g_p maps
H, W = 4, 6
tmp = Path(tempfile.mkdtemp())
(tmp / "lm").mkdir(); (tmp / "mk").mkdir()
# columns: 0 unit agree (support), 1 unit conflict (support), 2 unit propagated agree, 3 unit propagated conflict,
#          4 unit mixed, 5 no unit;   rows: 0-1 c_p = 1, 2-3 c_p = 0; marks: row 0 agree, row 1 conflict
lm = np.tile(np.array([0, 1, 2, 3, 4, -1], np.int32), (H, 1))
mk = np.full((H, W), ppr.MARK_NONE, np.int8); mk[0, :] = ppr.MARK_AGREE; mk[1, :] = ppr.MARK_CONFLICT
A = np.zeros((H, W), np.float32); A[:2, :] = 1.0
np.save(tmp / "lm" / "v.npy", lm); np.save(tmp / "mk" / "v.npy", mk)
stub = SimpleNamespace(train_names={"v"}, size=(H, W), A={"v": torch.as_tensor(A, device=dev)},
                       P={"v": torch.full((H, W), 10.0, device=dev)},
                       prop=dict(J_loc=torch.tensor([ppr.J_AGREE, ppr.J_CONFLICT, ppr.J_AGREE, ppr.J_CONFLICT, ppr.J_MIXED], device=dev)))
J.Judgment._g_init(stub, SimpleNamespace(jbgs_locmap_dir=str(tmp / "lm"), jbgs_markmap_dir=str(tmp / "mk")))
g = stub.GW["v"].cpu().numpy()
want = np.array([[1, 0, 1, 0, 1, 1],      # c_p 1, mark agree: unit judgment rules; no unit -> own mark agree -> 1
                 [1, 0, 1, 0, 1, 0],      # c_p 1, mark conflict: unit judgment rules (agree unit stays 1); no unit -> 0
                 [1, 0, 1, 0, 1, 1],      # c_p 0: unit judgment rules; no unit -> 1 (inherit)
                 [1, 0, 1, 0, 1, 1]], np.float32)
assert np.array_equal(g, want), g
c = stub.g_counts["v"]
assert c["no_unit_c1_g0"] == 1 and c["no_unit_c1_g1"] == 1 and c["no_unit_c0_g1"] == 2, c
print("g_p maps: unit judgment for every pixel of a unit (vote or propagated alike), c_p and own mark without a unit ok")

# 3) the prior term uses g_p
P = torch.full((H, W), 10.0, device=dev); D = P + 0.5; M = P.clone()
tau = torch.full((H, W), 0.05, device=dev)
lstub = SimpleNamespace(mode="P", A=stub.A, M={"v": M}, P={"v": P}, TAU={"v": tau}, GW=stub.GW,
                        args=SimpleNamespace(jbgs_depth_norm="pixels", jbgs_trunc_hi=4.0), last_stats=None)
mvs, prior, st = J.Judgment.losses(lstub, "v", {"surf_depth": D[None]})
on = (stub.GW["v"] > 0) & torch.isfinite(P)
expect = float((torch.clamp(torch.abs(D - P) - tau, min=0).clamp(max=3 * tau) * on.float()).sum() / (H * W))
assert abs(float(prior) - expect) < 1e-6, (float(prior), expect)
assert st["prior_n"] == int(on.sum()), st
r7w = (1 - stub.A["v"])
assert int(((r7w == 0) & on).sum()) == 7, "c_p = 1 pixels with g_p = 1 are pulled in r8 (r7 weight was 0 there)"
assert abs(float(mvs) - float((torch.abs(D - M) * stub.A["v"]).sum() / (H * W))) < 1e-6
print("prior depth term weighted by g_p (on at c_p = 1 & g_p = 1, off at g_p = 0); MVS term keeps c_p ok")

# helpers for 4-6
N = 12
rs = np.random.RandomState(0); pts = rs.rand(N, 3); cols = rs.rand(N, 3)


def make():
    torch.manual_seed(0)
    m = GaussianModel(3)
    m.create_from_pcd(BasicPointCloud(points=pts, colors=cols, normals=np.zeros_like(pts)), 1.0)
    m.training_setup(opt)
    m.origin = torch.ones(N, dtype=torch.int8, device=dev)
    # one Adam step with zero gradients creates the optimizer state (reset_opacity replaces it; Adam moves nothing)
    loss = sum((p * 0).sum() for grp in m.optimizer.param_groups for p in grp["params"])
    loss.backward(); m.optimizer.step(); m.optimizer.zero_grad(set_to_none=True)
    return m


def judgment_stub(gm, first_E, Jprop, Jl, kinds, normals, located):
    jst = SimpleNamespace()
    jst.args = SimpleNamespace(jbgs_e_depth_tol=0.5, jbgs_e_alpha_min=0.05, jbgs_e_threshold=0.5, jbgs_lock_drift_tau_mult=4.0,
                               jbgs_lock_opacity_floor=0.5, jbgs_lock_lr_scale=0.01)
    jst.mode = "P"; jst.render_fn = None; jst.E_calls = 0; jst.keep_maps = False; jst.tb = None
    jst.mon = Path(tempfile.mkdtemp()); jst.train_cams = []; jst.A = {}; jst.P = {}
    jst.CAT_NAMES = J.Judgment.CAT_NAMES
    jst.tau_kind = {1: 0.05, 2: 0.2}
    jst.prop = dict(J=torch.as_tensor(Jprop, device=dev), J_loc=torch.as_tensor(Jl, device=dev))
    jst.init_xyz = gm.get_xyz.detach().clone()
    jst.init_normal = torch.as_tensor(normals, dtype=torch.float32, device=dev)
    jst.init_kind = torch.as_tensor(kinds, device=dev).long()
    jst.init_cat = torch.full((N,), 1, dtype=torch.long, device=dev)
    jst._first = dict(E=torch.as_tensor(first_E, dtype=torch.float32, device=dev), n=torch.ones(N, device=dev))
    loc_ok = torch.as_tensor(located, device=dev)
    jst.seat_now = lambda gg: (loc_ok[: gg.get_xyz.shape[0]], torch.zeros(gg.get_xyz.shape[0], dtype=torch.long, device=dev),
                               torch.where(loc_ok[: gg.get_xyz.shape[0]], torch.arange(gg.get_xyz.shape[0], device=dev), -1))
    jst.floor_now = lambda gg: J.Judgment.floor_now(jst, gg)
    jst.u_offsets = lambda gg: J.Judgment.u_offsets(jst, gg)
    jst.removed_at = torch.full((N,), -1, dtype=torch.int32, device=dev)
    jst.removed_opacity = torch.full((N,), float("nan"), device=dev)
    jst.cur_iter = 0
    jst.counters = {"added": 0, "removed": 0}
    for k in ("_rows_append", "_rows_keep", "_record_removal"):
        setattr(jst, k, getattr(J.Judgment, k).__get__(jst))
    jst.ROWS, jst.FILL = J.Judgment.ROWS, J.Judgment.FILL
    jst.E = jst.E_cnt = jst.g_J = jst.g_Jl = jst.g_loc = jst.g_located = jst._g_surface = None
    gm.init_id = torch.arange(N, dtype=torch.int32, device=dev)
    J.Judgment._wrap_counters(jst, gm)
    return jst


# 4) invisible Gaussians: c-bar 0 -> protected -> kept by the reset and by pruning
g4 = make()
first = np.full(N, 0.9, np.float32); first[:4] = 0.0          # rows 0-3: no seeing view (invisible unit)
jst = judgment_stub(g4, first, [ppr.J_NONE] * N, [ppr.J_NONE] * N, [1] * N, np.tile([0, 0, 1.0], (N, 1)), [True] * N)
row = J.Judgment.update_E_r8(jst, 1, g4)
lock = g4.frozen_mask.cpu().numpy()
assert lock[:4].all() and not lock[4:].any(), lock
assert bool((g4.get_opacity.squeeze(-1)[:4] >= 0.5 - 1e-6).all()), "floor at protection"
g4.reset_opacity(exempt_mask=g4.frozen_mask)
op = g4.get_opacity.squeeze(-1)
assert bool((op[:4] >= 0.5 - 1e-6).all()) and bool((op[4:] < 0.02).all()), op
g4.xyz_gradient_accum = torch.zeros((N, 1), device=dev); g4.denom = torch.ones((N, 1), device=dev); g4.max_radii2D = torch.zeros(N, device=dev)
jst.cur_iter = 600
g4.densify_and_prune(1.0, 0.05, 100.0, None)
assert g4.get_xyz.shape[0] == 4 and bool(g4.init_id.long().eq(torch.arange(4, device=dev)).all()), g4.init_id
ra = jst.removed_at.cpu().numpy()
assert (ra[:4] == -1).all() and (ra[4:] == 600).all(), ra
assert bool((jst.removed_opacity[4:] < 0.05).all()), jst.removed_opacity
print("invisible Gaussians: c-bar 0, protected, kept through the opacity reset and pruning; removal history of the others ok")

# 5) protection rule (eq. 7) with u like the residuals
g5 = make()
roof_n = np.array([0.0, 0.6, 0.8]); wall_n = np.array([1.0, 0.0, 0.0])
normals = np.stack([roof_n, roof_n, roof_n, roof_n, wall_n, wall_n, [0, 0, 1.0], [0, 0, 1.0], roof_n, roof_n, roof_n, roof_n])
kinds = [1, 1, 1, 1, 2, 2, 0, 0, 1, 1, 1, 1]
first = np.full(N, 0.2, np.float32); first[8] = 0.6
Jp = [ppr.J_NONE] * N; Jp[9] = ppr.J_CONFLICT
Jl = list(Jp); Jl[10] = ppr.J_CONFLICT                         # row 10: a support unit voted conflict (not propagated)
jst = judgment_stub(g5, first, Jp, Jl, kinds, normals, [True] * 6 + [False, False] + [True] * 4)
along = np.cross(roof_n, [1.0, 0, 0]); along /= np.linalg.norm(along)
with torch.no_grad():
    d = torch.zeros((N, 3), device=dev)
    d[0] = torch.as_tensor(0.5 * along, device=dev)              # along the plane: u 0, 3-D 0.5 m
    d[1] = torch.tensor([0.0, 0.0, 0.19], device=dev)            # vertical 0.19 m over the plane (u 0.19 <= 0.2)
    d[2] = torch.tensor([0.0, 0.0, 0.21], device=dev)            # u 0.21 > 4 x 0.05
    d[4] = torch.tensor([0.79, 0.3, 0.0], device=dev)            # wall: along the normal 0.79 <= 0.8
    d[5] = torch.tensor([0.81, 0.0, 0.0], device=dev)            # 0.81 > 0.8
    d[6] = torch.tensor([0.5, 0.5, 0.19], device=dev)            # no unit: vertical 0.19 <= 0.2
    d[7] = torch.tensor([0.0, 0.0, 0.21], device=dev)            # no unit: vertical 0.21 > 0.2
    g5._xyz.data += d
row = J.Judgment.update_E_r8(jst, 1, g5)
lock = g5.frozen_mask.cpu().numpy().tolist()
want = [True, True, False, True, True, False, True, False, False, False, True, True]
assert lock == want, (lock, want)
assert row["n_conflict_excluded"] == 1 and row["locked_on_support_conflict_unit"] == 1, row
assert row["would_differ_with_3d_distance"]["protected_now_but_3d_beyond"] >= 1, row
# release reasons at the next computation: move row 3 up (u), give row 1 c-bar 0.7, row 0 stays
jst.E_calls = 1; jst.render_fn = None
jst._first = dict(E=torch.as_tensor(np.where(np.arange(N) == 1, 0.7, first), dtype=torch.float32, device=dev), n=torch.ones(N, device=dev))
jst.E_calls = 0
with torch.no_grad():
    g5._xyz.data[3] += torch.tensor([0.0, 0.0, 0.3], device=dev)
row2 = J.Judgment.update_E_r8(jst, 500, g5)
rb = row2["released_by"]
assert rb["E_at_or_above_threshold"] == 1 and rb["u_beyond_bound"] == 1 and rb["no_reason_found"] == 0, rb
print("protection: u like the residuals (plane slide kept, vertical / wall-normal bounds, vertical without a unit), conflict "
      "excluded, release reasons recorded ok")

# 6) split parent with children is not a removal
g6 = make()
jst = judgment_stub(g6, np.full(N, 0.9, np.float32), [ppr.J_NONE] * N, [ppr.J_NONE] * N, [1] * N, np.tile([0, 0, 1.0], (N, 1)), [True] * N)
J.Judgment.update_E_r8(jst, 1, g6)
g6.xyz_gradient_accum = torch.zeros((N, 1), device=dev); g6.denom = torch.ones((N, 1), device=dev); g6.max_radii2D = torch.zeros(N, device=dev)
grads = torch.zeros((N, 1), device=dev); grads[:3] = 1.0
jst.cur_iter = 700
g6.densify_and_split(grads, 0.5, 0.0)                            # every selected disk counts as large (extent 0)
assert g6.get_xyz.shape[0] == N - 3 + 6
assert (jst.removed_at.cpu().numpy() == -1).all(), "split parents carried on by their children are not removals"
print("split parents carried on by children are not removals ok")
print("GPU R8 TESTS PASSED")
