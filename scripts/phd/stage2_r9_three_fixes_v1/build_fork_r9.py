"""Build the stage-2 fork r9 from the frozen r8 fork (stdlib only, reproducible; PHD-STAGE2-R9-THREE-FIXES-v1).

  python build_fork_r9.py --parent <R8>/sources/GeoGS-conf-guided-v1-r8 --out <R9>/sources/GeoGS-conf-guided-v1-r9
                          --provenance <R9>/provenance --repo <repo root> [--repo_commit <sha>]

r8 is only read. r9 = r8 with
  jbgs_judgment.py                    replaced by the r9 module next to this script (protection with the patch judgment,
                                      initial direction of prior-origin Gaussians, records)
  src/phd/prior_propagation_v3/*.py   the shared module v3, copied from the repository (sha256 must match)
  src/phd/prior_propagation_v2/       removed (r9 imports v3 only)
train.py, scene/gaussian_model.py and everything else are r8's files (the LoD2 bottom face is an input change).
Provenance: unified diffs of the changed files, sha256 of every changed or added file, the list of files that differ
between the trees (must be exactly these), build_report_r9.json."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")
SHARED = ["conversion.py", "tolerance.py", "surfaces.py", "outlines.py", "rule.py", "locations.py", "seat.py", "faces.py", "orientation.py"]   # namespace package
SHARED_V2 = ["conversion.py", "tolerance.py", "surfaces.py", "outlines.py", "rule.py", "locations.py", "seat.py"]

ap = argparse.ArgumentParser()
ap.add_argument("--parent", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--provenance", required=True)
ap.add_argument("--repo", required=True)
ap.add_argument("--repo_commit", default="")
a = ap.parse_args()
parent, out, prov, repo = Path(a.parent), Path(a.out), Path(a.provenance), Path(a.repo)
if out.exists():
    raise SystemExit(f"{out} exists; move it aside first (nothing is overwritten)")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith("media/"))


shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
shutil.copy2(HERE / "jbgs_judgment.py", out / "jbgs_judgment.py")
shutil.rmtree(out / "src/phd/prior_propagation_v2")
src_dir = repo / "src/phd/prior_propagation_v3"
dst_dir = out / "src/phd/prior_propagation_v3"
dst_dir.mkdir(parents=True, exist_ok=True)
shared = {}
for f in SHARED:
    shutil.copy2(src_dir / f, dst_dir / f)
    shared[f] = dict(repo=sha(src_dir / f), fork=sha(dst_dir / f))
    if shared[f]["repo"] != shared[f]["fork"]:
        raise SystemExit(f"copy of {f} differs")

(prov / "patches").mkdir(parents=True, exist_ok=True)
changed = {}
for rel in files(out):
    src, new = parent / rel, out / rel
    if not src.exists() or sha(src) != sha(new):
        changed[rel] = dict(r8=sha(src) if src.exists() else None, r9=sha(new))
        a_txt = src.read_text().splitlines(True) if src.exists() else []
        (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
            "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r8/{rel}", f"r9/{rel}")))
removed = [rel for rel in files(parent) if not (out / rel).exists()]
expected_changed = {"jbgs_judgment.py"} | {f"src/phd/prior_propagation_v3/{f}" for f in SHARED}
expected_removed = {f"src/phd/prior_propagation_v2/{f}" for f in SHARED_V2}
report = dict(built_at=dt.datetime.now(dt.timezone.utc).isoformat(), revision="r9", parent=str(parent), parent_revision="r8",
              out=str(out), changed_files=changed, removed_files=removed, shared_module=shared,
              only_expected_files_changed=bool(set(changed) == expected_changed and set(removed) == expected_removed),
              overlay_sha256=sha(HERE / "jbgs_judgment.py"), build_script_sha256=sha(__file__), repo_commit=a.repo_commit,
              changes=["r9-1 protection (eq. 7) excludes every Gaussian whose patch judgment is conflict (support vote or propagated)",
                       "r9-2 prior-origin Gaussians start with the disk normal = the outward face normal (--jbgs_prior_normal_path)",
                       "r9-3 LoD2 bottom face: input change only (no code)",
                       "r9-4 records (disk normal, face normal, patch state; release / exclusion by support conflict)"],
              v3_files_identical_to_v2={f: sha(repo / "src/phd/prior_propagation_v2" / f) == sha(src_dir / f) for f in SHARED_V2},
              scientific_verdict=None)
(prov / "build_report_r9.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: report[k] for k in ("only_expected_files_changed", "removed_files")}), sorted(changed))
if not report["only_expected_files_changed"]:
    raise SystemExit("unexpected file changes")
