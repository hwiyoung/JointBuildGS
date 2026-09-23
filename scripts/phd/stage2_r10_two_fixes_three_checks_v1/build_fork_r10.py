"""Build the stage-2 fork r10 from the frozen r9 fork (stdlib only, reproducible; PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).

  python build_fork_r10.py --parent <R9>/sources/GeoGS-conf-guided-v1-r9 --out <R10>/sources/GeoGS-conf-guided-v1-r10
                           --provenance <R10>/provenance --repo <repo root> [--repo_commit <sha>]

r9 is only read. r10 = r9 with
  jbgs_judgment.py   replaced by the r10 module next to this script (record-only dumps around the opacity reset, the
                     offline re-read probe of the two reset states, the cell method of the initial direction)
train.py, scene/gaussian_model.py, the shared module src/phd/prior_propagation_v3 and everything else are r9's files (the
order of re-read and reset is already the method's; the LoD2 party-wall cut is an input change).
Provenance: unified diff of the changed file, sha256 of every changed file, the list of files that differ between the
trees (must be exactly jbgs_judgment.py), build_report_r10.json."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")
SHARED_V3 = ["conversion.py", "tolerance.py", "surfaces.py", "outlines.py", "rule.py", "locations.py", "seat.py", "faces.py", "orientation.py"]

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
shared = {f: dict(repo=sha(repo / "src/phd/prior_propagation_v3" / f), fork=sha(out / "src/phd/prior_propagation_v3" / f)) for f in SHARED_V3}
if any(v["repo"] != v["fork"] for v in shared.values()):
    raise SystemExit("the fork's shared module v3 differs from the repository's v3")
(prov / "patches").mkdir(parents=True, exist_ok=True)
changed = {}
for rel in files(out):
    src, new = parent / rel, out / rel
    if not src.exists() or sha(src) != sha(new):
        changed[rel] = dict(r9=sha(src) if src.exists() else None, r10=sha(new))
        a_txt = src.read_text().splitlines(True) if src.exists() else []
        (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
            "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r9/{rel}", f"r10/{rel}")))
removed = [rel for rel in files(parent) if not (out / rel).exists()]
report = dict(built_at=dt.datetime.now(dt.timezone.utc).isoformat(), revision="r10", parent=str(parent), parent_revision="r9",
              out=str(out), changed_files=changed, removed_files=removed, shared_module_v3=shared,
              only_expected_files_changed=bool(set(changed) == {"jbgs_judgment.py"} and not removed),
              overlay_sha256=sha(HERE / "jbgs_judgment.py"), build_script_sha256=sha(__file__), repo_commit=a.repo_commit,
              changes=["r10-1 order of re-read and opacity reset: unchanged (already the method's); record-only dumps around reset_opacity "
                       "(--jbgs_reset_dump_iterations) and the offline probe (--jbgs_dry_init 3)",
                       "r10-2 --jbgs_prior_normal_mode cell: the face normal of the cell a point first sits in (points without a patch: file normal)",
                       "LoD2 party-wall cut: input change only (no code)"],
              scientific_verdict=None)
(prov / "build_report_r10.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: report[k] for k in ("only_expected_files_changed", "removed_files")}), sorted(changed))
if not report["only_expected_files_changed"]:
    raise SystemExit("unexpected file changes")
