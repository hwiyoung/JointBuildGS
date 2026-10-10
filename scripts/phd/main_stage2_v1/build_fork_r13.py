#!/usr/bin/env python3
"""Build fork r13 from the committed fork r12 (stdlib only, reproducible from the repository; PHD-MAIN-STAGE2-v1 4.2).

  python3 build_fork_r13.py [--parent src/phd/forks/GeoGS-conf-guided-v1-r12] [--out src/phd/forks/GeoGS-conf-guided-v1-r13]
                            [--provenance docs/experiments/phd/main_stage2_v1/provenance] [--repo_commit <sha>]

r12 is only read. r13 = r12 with jbgs_judgment.py and scene/gaussian_model.py replaced by the files of fork_r13/ next to this script
(three ablation flags, each 0 by default = r12; see the r13 text at the head of jbgs_judgment.py). train.py and the shared module v6
are r12's, byte for byte. Provenance: unified diffs, sha256 of the changed files, the list of files that differ (must be exactly the
two files), build_report_r13.json. scientific_verdict: null."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc", "submodules")
CHANGED = ["jbgs_judgment.py", "scene/gaussian_model.py"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith(("media/", "submodules/")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", default=str(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12"))
    ap.add_argument("--out", default=str(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r13"))
    ap.add_argument("--provenance", default=str(REPO / "docs/experiments/phd/main_stage2_v1/provenance"))
    ap.add_argument("--repo_commit", default="")
    a = ap.parse_args()
    parent, out, prov = Path(a.parent), Path(a.out), Path(a.provenance)
    if out.exists():
        raise SystemExit(f"{out} exists; move it aside first (nothing is overwritten)")
    shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
    for rel in CHANGED:
        shutil.copy2(HERE / "fork_r13" / rel, out / rel)
    (prov / "patches").mkdir(parents=True, exist_ok=True)
    changed = {}
    for rel in files(out):
        src, new = parent / rel, out / rel
        if not src.exists() or sha(src) != sha(new):
            changed[rel] = dict(r12=sha(src) if src.exists() else None, r13=sha(new))
            a_txt = src.read_text().splitlines(True) if src.exists() else []
            (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
                "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r12/{rel}", f"r13/{rel}")))
    removed = [rel for rel in files(parent) if not (out / rel).exists()]
    rep = dict(task_id="PHD-MAIN-STAGE2-v1", fork="r13", parent=str(parent.relative_to(REPO)) if parent.is_relative_to(REPO) else str(parent),
               out=str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out), built_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               repo_commit=a.repo_commit, n_files=len(files(out)), changed_or_added=changed, removed=removed,
               train_py_equal_r12=sha(parent / "train.py") == sha(out / "train.py"),
               fork_r13_sources={rel: sha(HERE / "fork_r13" / rel) for rel in CHANGED},
               only_expected_changes=bool(set(changed) == set(CHANGED) and not removed), scientific_verdict=None)
    (prov / "build_report_r13.json").write_text(json.dumps(rep, indent=1))
    print("fork r13 built", out, "files", rep["n_files"], "changed", sorted(changed), "only expected", rep["only_expected_changes"])
    if not rep["only_expected_changes"]:
        raise SystemExit("unexpected differences between r12 and r13")


if __name__ == "__main__":
    main()
