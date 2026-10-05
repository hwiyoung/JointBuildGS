"""Build the instrumented copy of the r6 fork for PHD-STAGE2-R6-FIX-v1 (stdlib only, reproducible).

  python build_audit_fork_r6.py --parent <R6>/sources/GeoGS-conf-guided-v1-r6 --out <R6>/sources/GeoGS-conf-guided-v1-r6-audit
                                --provenance <R6>/provenance/audit [--repo_commit <sha>]

The parent (r6 fork) is only read. The copy gets jbgs_audit_r6.py as jbgs_audit.py and six anchored
insertions in train.py (import, construction, around update_E, around optimizer.step, end of iteration, arguments).
No method line is changed: every inserted line is guarded by `audit is not None`, and without --jbgs_audit_dir the copy
runs the parent's code path. Provenance: unified diff of train.py, sha256 of changed/new files, build_report.json."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")
MARK = "# [jbgs_audit]"

ap = argparse.ArgumentParser()
ap.add_argument("--parent", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--provenance", required=True)
ap.add_argument("--repo_commit", default="")
a = ap.parse_args()
parent, out, prov = Path(a.parent), Path(a.out), Path(a.provenance)
if out.exists():
    raise SystemExit(f"{out} exists; move it aside first (nothing is overwritten)")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


EDITS = [
    ("import jbgs_judgment  # [jbgs_judgment]\n",
     "import jbgs_judgment  # [jbgs_judgment]\n"
     f"import jbgs_audit  {MARK}\n"),
    ("    judgment = jbgs_judgment.Judgment(args, opt, scene, gaussians, tb_writer, render_fn=render, pipe=pipe, background=background) if args.jbgs_judgment != \"off\" else None  # [jbgs_judgment r6] E renders the training views (fix 1)\n",
     "    judgment = jbgs_judgment.Judgment(args, opt, scene, gaussians, tb_writer, render_fn=render, pipe=pipe, background=background) if args.jbgs_judgment != \"off\" else None  # [jbgs_judgment r6] E renders the training views (fix 1)\n"
     f"    audit = jbgs_audit.Audit(args, opt, judgment, scene, gaussians, render, pipe, background) if (judgment is not None and args.jbgs_audit_dir) else None  {MARK}\n"),
    ("        if judgment is not None and judgment.due_E(iteration):  # [jbgs_judgment] E at 0 and every e_interval\n"
     "            judgment.update_E(iteration, gaussians)\n",
     "        if judgment is not None and judgment.due_E(iteration):  # [jbgs_judgment] E at 0 and every e_interval\n"
     f"            if audit is not None: audit.before_E(iteration, gaussians)  {MARK}\n"
     "            judgment.update_E(iteration, gaussians)\n"
     f"            if audit is not None: audit.after_E(iteration, gaussians)  {MARK}\n"),
    ("        if judgment is not None:  # [jbgs_judgment] remember locked rows before the Adam step\n"
     "            judgment.before_step(gaussians)\n"
     "        gaussians.optimizer.step()\n"
     "        if judgment is not None:  # [jbgs_judgment] locked disks keep lock_lr_scale of the step; opacity floor\n"
     "            judgment.after_step(gaussians)\n",
     f"        if audit is not None: audit.before_step(iteration, gaussians)  {MARK}\n"
     "        if judgment is not None:  # [jbgs_judgment] remember locked rows before the Adam step\n"
     "            judgment.before_step(gaussians)\n"
     "        gaussians.optimizer.step()\n"
     f"        if audit is not None: audit.mid_step(gaussians)  {MARK}\n"
     "        if judgment is not None:  # [jbgs_judgment] locked disks keep lock_lr_scale of the step; opacity floor\n"
     "            judgment.after_step(gaussians)\n"
     f"        if audit is not None: audit.post_lock(iteration, gaussians)  {MARK} variant C blend, then step records\n"),
    ("            if iteration in checkpoint_iterations:\n",
     f"            if audit is not None: audit.end_iteration(iteration, gaussians)  {MARK}\n"
     "            if iteration in checkpoint_iterations:\n"),
    ("    jbgs_judgment.register_args(parser)  # [jbgs_judgment]\n",
     "    jbgs_judgment.register_args(parser)  # [jbgs_judgment]\n"
     f"    jbgs_audit.register_args(parser)  {MARK}\n"),
]

shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
shutil.copy2(HERE / "jbgs_audit_r6.py", out / "jbgs_audit.py")
tp = out / "train.py"
s0 = tp.read_text()
s = s0
for i, (old, new) in enumerate(EDITS):
    if s.count(old) != 1:
        raise SystemExit(f"train.py anchor {i} found {s.count(old)} times:\n{old}")
    s = s.replace(old, new)
tp.write_text(s)
(prov / "patches").mkdir(parents=True, exist_ok=True)
diff = "".join(difflib.unified_diff(s0.splitlines(True), s.splitlines(True), "parent/train.py", "audit/train.py"))
(prov / "patches" / "train.py.diff").write_text(diff)
shutil.copy2(out / "jbgs_audit.py", prov / "patches" / "jbgs_audit.py.new")
changed = {"train.py": sha(tp), "jbgs_audit.py": sha(out / "jbgs_audit.py")}
unchanged_check = {rel: sha(parent / rel) == sha(out / rel)
                   for rel in ("jbgs_judgment.py", "scene/gaussian_model.py", "gaussian_renderer/__init__.py",
                               "jbgs_state.py", "jbgs_mvs_pgsr.py", "utils/camera_utils.py", "jbgs_camera_adapter.py")}
report = dict(built_at=dt.datetime.now(dt.timezone.utc).isoformat(), parent=str(parent), out=str(out),
              parent_train_sha256=sha(parent / "train.py"), parent_judgment_sha256=sha(parent / "jbgs_judgment.py"),
              changed_sha256=changed, method_files_identical_to_parent=unchanged_check,
              n_inserted_lines=sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")),
              n_removed_lines=sum(1 for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")),
              build_script_sha256=sha(__file__), audit_module_sha256=sha(HERE / "jbgs_audit_r6.py"),
              repo_commit=a.repo_commit, scientific_verdict=None)
(prov / "build_report.json").write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
if not all(unchanged_check.values()):
    raise SystemExit("a method file differs from the parent")
