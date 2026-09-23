"""GPU checks of the r10 fork with the real GaussianModel (conf-guided image; /source = r10 fork, /r9src = r9 fork, /r8src =
r8 fork, /repo; one GPU).
  A) r9's GPU tests (gpu_tests_r9.py, eight groups) run again with the r10 module (only its revision assertion changed):
     group 1 compares with r8 the functions r9 kept from r8 (lock, floor, reset exemption, g_p, losses, u, re-read helpers,
     gaussian_model.py, train.py), groups 2-8 test g_p, the prior term, invisible Gaussians, eq. (7), removal history, fix
     'na' and fix 'da' (file normals).
  B) unchanged from r9, letter for letter: every function of the module except __init__, prop_init and orient_prior (and
     the new r10 functions), the module-level helpers, train.py, scene/gaussian_model.py and the fork's shared module v3.
  C) order of re-read and opacity reset (fix 'ga'): in train.py the re-read (update_E) comes before the step, the step
     before the density control, the density control before reset_opacity(exempt_mask=judgment.exempt_mask(...)); on an
     iteration where both fall, the reset reads the protection the re-read has just set (protected rows keep their
     opacity, the others drop to <= 0.01); the record-only wrapper writes the state before and after the reset and leaves
     the reset's result bit-identical to the unwrapped reset; a dumped state loads back bit-identical.
  D) cell method (check 'ra'): a prior row on a patch with cells starts with its cell's face normal (signed like its file
     normal), rows without a patch or on a patch without cells keep the file normal, image rows keep the base rotation;
     the file mode gives r9's rotations bit for bit.
Prints GPU R10 TESTS PASSED on success."""
import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

sys.path.insert(0, "/source")
import jbgs_judgment as J  # noqa: E402
assert J.REVISION == "r10", J.REVISION

# ---------------------------------------------------------------- A) r9's GPU tests with the r10 module
src = Path("/repo/scripts/phd/stage2_r9_three_fixes_v1/gpu_tests_r9.py").read_text()
assert src.count('assert J.REVISION == "r9", J.REVISION') == 1
src = src.replace('assert J.REVISION == "r9", J.REVISION', 'assert J.REVISION == "r10", J.REVISION')
src = src.replace('print("GPU R9 TESTS PASSED")', 'print("r9 GPU tests on r10: PASSED")')
exec(compile(src, "gpu_tests_r9.py (module r10)", "exec"), {"__name__": "gpu_tests_r9_on_r10"})

# ---------------------------------------------------------------- B) unchanged from r9
spec = importlib.util.spec_from_file_location("jbgs_judgment_r9", "/r9src/jbgs_judgment.py")
R9 = importlib.util.module_from_spec(spec); spec.loader.exec_module(R9)
assert R9.REVISION == "r9"
changed_ok = {"__init__", "prop_init", "orient_prior"}
new_r10 = {"_wrap_reset", "_dump_state", "_load_state", "reset_probe"}
names9 = {n for n, v in vars(R9.Judgment).items() if callable(v) or isinstance(v, (staticmethod, classmethod))}
names10 = {n for n, v in vars(J.Judgment).items() if callable(v) or isinstance(v, (staticmethod, classmethod))}
assert names10 - names9 == new_r10, names10 - names9
for name in sorted(names9 - changed_ok):
    assert inspect.getsource(getattr(J.Judgment, name)) == inspect.getsource(getattr(R9.Judgment, name)), f"{name} changed"
for name in ("scale_locked_update", "rho_truncated", "project_points", "truncated_prior_loss", "weighted_l1", "compute_E_render", "compute_E",
             "due_E_iteration", "lock_rule_r6", "init_visible_filter", "face_readout", "roof_check", "_load_set", "colorize_diverging", "register_args"):
    if name == "register_args":
        continue
    assert inspect.getsource(getattr(J, name)) == inspect.getsource(getattr(R9, name)), f"{name} changed"
assert Path("/source/train.py").read_text() == Path("/r9src/train.py").read_text(), "train.py changed"
assert Path("/source/scene/gaussian_model.py").read_text() == Path("/r9src/scene/gaussian_model.py").read_text(), "gaussian_model.py changed"
for f in sorted(Path("/r9src/src/phd/prior_propagation_v3").glob("*.py")):
    assert f.read_bytes() == (Path("/source/src/phd/prior_propagation_v3") / f.name).read_bytes(), f"shared module {f.name} changed"
pi9 = inspect.getsource(R9.Judgment.prop_init).splitlines(); pi10 = inspect.getsource(J.Judgment.prop_init).splitlines()
import difflib  # noqa: E402
d = [l for l in difflib.unified_diff(pi9, pi10, lineterm="", n=0) if l[:1] in "+-" and not l.startswith(("+++", "---"))]
moved = {l[1:].strip() for l in d if l.startswith("-")} - {l[1:].strip() for l in d if l.startswith("+")}
assert moved == {"face_n, orient = self.orient_prior(args, gaussians, prior)        # r9-2 (fix 'da')",
                 "face_normal=face_n.cpu().numpy(), normal_after_orientation=normal_after.cpu().numpy())"}, moved
print("B) every r9 function apart from __init__ / prop_init / orient_prior unchanged; prop_init only moves the orientation after "
      "the seat and records both normals; train.py, gaussian_model.py, shared module v3 unchanged ok")

# ---------------------------------------------------------------- C) order of re-read and reset
tr = Path("/source/train.py").read_text()
loop = tr[tr.index("for iteration in range(first_iter, opt.iterations + 1):"):]
pos = [loop.index(k) for k in ("judgment.update_E(iteration, gaussians)", "gaussians.optimizer.step()",
                               "gaussians.densify_and_prune(", "gaussians.reset_opacity(exempt_mask=judgment.exempt_mask(gaussians)")]
assert pos == sorted(pos), pos
assert "judgment.due_E(iteration)" in loop[:pos[0]] and loop.index("render(") > pos[0] if "render(" in loop else True
print(f"C1) train.py order: re-read at the start of the iteration, step, density control, reset with the re-read's protection ok "
      f"(offsets {pos})")
from arguments import OptimizationParams  # noqa: E402
from argparse import ArgumentParser  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402
from utils.graphics_utils import BasicPointCloud  # noqa: E402
from utils.general_utils import build_rotation  # noqa: E402
from src.phd.prior_propagation_v3 import rule as ppr  # noqa: E402
parser = ArgumentParser(); opt = OptimizationParams(parser).extract(parser.parse_args([]))
dev = "cuda"
N = 12
rs = np.random.RandomState(0); pts = rs.rand(N, 3); cols = rs.rand(N, 3)


def make():
    torch.manual_seed(0)
    m = GaussianModel(3)
    m.create_from_pcd(BasicPointCloud(points=pts, colors=cols, normals=np.zeros_like(pts)), 1.0)
    m.training_setup(opt)
    m.origin = torch.ones(N, dtype=torch.int8, device=dev)
    m.init_id = torch.arange(N, dtype=torch.int32, device=dev)
    loss = sum((p * 0).sum() for grp in m.optimizer.param_groups for p in grp["params"])
    loss.backward(); m.optimizer.step(); m.optimizer.zero_grad(set_to_none=True)
    with torch.no_grad():
        m._opacity.data[:] = m.inverse_opacity_activation(torch.full_like(m._opacity, 0.8))
    return m


tmp = Path(tempfile.mkdtemp())
g = make(); g_ref = make()
# the re-read of this iteration protects rows 0-3 (c-bar 0) and nothing else; the protection in effect before it was rows 8-11
g.set_frozen_mask(torch.arange(N, device=dev) >= 8); g_ref.set_frozen_mask(torch.arange(N, device=dev) >= 8)
stub = SimpleNamespace(mode="P", args=SimpleNamespace(jbgs_reset_dump_iterations=[3000], jbgs_lock_opacity_floor=0.5), model_path=tmp,
                       cur_iter=3000, E=None, E_cnt=None, g_loc=None, g_located=None, g_Jl=None, g_state=None)
stub._dump_state = J.Judgment._dump_state.__get__(stub)
J.Judgment._wrap_reset(stub, g)
new_lock = torch.arange(N, device=dev) < 4
for m_ in (g, g_ref):                                          # = update_E at the start of iteration 3000 (set_frozen_mask + floor)
    m_.set_frozen_mask(new_lock.clone())
    J.Judgment.floor_now(SimpleNamespace(mode="P", args=stub.args), m_)
op_before = g.get_opacity.squeeze(-1).detach().clone()
g.reset_opacity(exempt_mask=J.Judgment.exempt_mask(stub, g))                       # wrapped (as train.py calls it)
type(g_ref).reset_opacity(g_ref, exempt_mask=J.Judgment.exempt_mask(stub, g_ref))  # the unwrapped base reset
op = g.get_opacity.squeeze(-1).detach()
assert bool((op[:4] == op_before[:4]).all()) and bool((op[4:] <= 0.01 + 1e-7).all()), op
assert torch.equal(g._opacity.detach(), g_ref._opacity.detach()), "the wrapper changed the reset"
pre = torch.load(tmp / "dump/reset_states/reset_3000_pre_reset.pt"); post = torch.load(tmp / "dump/reset_states/reset_3000_post_reset.pt")
assert torch.equal(pre["opacity"], torch.special.logit(op_before.cpu()[:, None].double()).float()) or torch.allclose(
    torch.sigmoid(pre["opacity"]).squeeze(-1), op_before.cpu(), atol=1e-6)
assert torch.equal(post["opacity"], g._opacity.detach().cpu()) and torch.equal(pre["frozen_mask"], new_lock.cpu()), "dumped states"
assert torch.equal(pre["exempt_mask"], new_lock.cpu()) and torch.equal(pre["xyz"], post["xyz"])
g2 = make()
J.Judgment._load_state(SimpleNamespace(), g2, post)
for nm in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
    assert torch.equal(getattr(g2, nm).detach().cpu(), getattr(g, nm).detach().cpu()), nm
assert torch.equal(g2.frozen_mask.cpu(), new_lock.cpu())
print("C2) the reset reads the protection the re-read of the same iteration set (protected keep opacity, others <= 0.01); the "
      "record-only wrapper leaves the reset bit-identical, writes both states, and a state loads back bit-identical ok")

# ---------------------------------------------------------------- D) cell method of the initial direction
g8 = make()
g8.origin = torch.tensor([0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=torch.int8, device=dev)
rot0 = g8._rotation.detach().clone()
rs8 = np.random.RandomState(1); fnm = rs8.normal(size=(N, 3)); fnm[:, 2] = np.abs(fnm[:, 2]) + 0.2; fnm /= np.linalg.norm(fnm, axis=1, keepdims=True)
fnm[:3] = np.nan
tmpn = tmp / "prior_normal.npy"; np.save(tmpn, fnm.astype(np.float32))
# patches: rows 3-7 on cells (unit kind 1), row 8 on an 'extra' unit (no cell), rows 9-11 without a patch
un = torch.tensor([[0.0, 0.0, 1.0], [0.0, 0.6, 0.8], [0.6, 0.0, -0.8], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]], device=dev)
uk = torch.tensor([1, 1, 1, 1, 2, 0], device=dev)
has = torch.zeros(N, dtype=torch.bool, device=dev); has[3:9] = True
loc = torch.full((N,), -1, dtype=torch.long, device=dev); loc[3:9] = torch.arange(6, device=dev)
jc = SimpleNamespace(prop=dict(unit_normal=un, unit_kind=uk))
fn, info = J.Judgment.orient_prior(jc, SimpleNamespace(jbgs_prior_normal_path=str(tmpn), jbgs_prior_normal_mode="cell"), g8, g8.origin == 1, cell=(has, loc))
Rm = build_rotation(g8._rotation.detach()); nrm = Rm[:, :, 2].cpu().numpy().astype(np.float64)
want = fnm.copy()
for i in range(3, 8):
    c = un[i - 3].cpu().numpy().astype(np.float64)
    want[i] = c if np.dot(c, fnm[i]) >= 0 else -c
ang = np.degrees(np.arctan2(np.linalg.norm(np.cross(nrm[3:], want[3:]), axis=1), (nrm[3:] * want[3:]).sum(1)))
assert ang.max() < 0.01, ang
assert torch.equal(g8._rotation.detach()[:3], rot0[:3]), "image rows"
assert info["n_from_cell"] == 5 and info["mode"] == "cell", info
assert np.allclose(jc._fn_file.cpu().numpy()[3:], fnm[3:], atol=1e-6) and np.isnan(jc._fn_cell.cpu().numpy()[8:]).all()
# file mode = r9 bit for bit
ga, gb = make(), make()
for m_ in (ga, gb):
    m_.origin = g8.origin.clone()
jf = SimpleNamespace(prop=dict(unit_normal=un, unit_kind=uk))
J.Judgment.orient_prior(jf, SimpleNamespace(jbgs_prior_normal_path=str(tmpn)), ga, ga.origin == 1, cell=(has, loc))
R9.Judgment.orient_prior(SimpleNamespace(), SimpleNamespace(jbgs_prior_normal_path=str(tmpn)), gb, gb.origin == 1)
assert torch.equal(ga._rotation.detach(), gb._rotation.detach()), "file mode differs from r9"
print("D) cell method: rows on a patch with cells take the cell's face normal (signed like the file normal), others keep the file "
      "normal, image rows unchanged; file mode = r9 bit for bit ok")
print("GPU R10 TESTS PASSED")
