#!/usr/bin/env python3
"""Build the stage-2 fork r12 from the committed fork r11 (stdlib only, reproducible from the repository; PHD-MAIN-STAGE0-v1 5.1).

  python3 build_fork_r12.py [--parent src/phd/forks/GeoGS-conf-guided-v1-r11] [--out src/phd/forks/GeoGS-conf-guided-v1-r12]
                            [--provenance docs/experiments/phd/main_stage0_v1/provenance] [--repo_commit <sha>]

r11 is only read (the committed tree: no submodules/, which are compiled into the image jointbuildgs:geogs-conf-guided-v1 and
never read from /source at run time). r12 = r11 with jbgs_judgment.py and train.py replaced by the files of fork_r12/ next
to this script and the shared module src/phd/prior_propagation_v6 copied from the repository (sha256 checked); v5 and v3 stay
in the tree (unused). Provenance: unified diffs of the changed files, sha256 of every changed or added file, the list of
files that differ (must be exactly the two files plus the added module), build_report_r12.json. scientific_verdict: null."""
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
V6 = ["caps.py", "conversion.py", "faces.py", "locations.py", "orientation.py", "outlines.py", "registration.py", "rule.py", "rules.py",
      "seat.py", "surfaces.py", "switches.py", "tallies.py", "tolerance.py"]
CHANGED = ["jbgs_judgment.py", "train.py"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith(("media/", "submodules/")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", default=str(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r11"))
    ap.add_argument("--out", default=str(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12"))
    ap.add_argument("--provenance", default=str(REPO / "docs/experiments/phd/main_stage0_v1/provenance"))
    ap.add_argument("--repo_commit", default="")
    a = ap.parse_args()
    parent, out, prov = Path(a.parent), Path(a.out), Path(a.provenance)
    if out.exists():
        raise SystemExit(f"{out} exists; move it aside first (nothing is overwritten)")
    shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
    for rel in CHANGED:
        shutil.copy2(HERE / "fork_r12" / rel, out / rel)
    (out / "src/phd/prior_propagation_v6").mkdir(parents=True, exist_ok=True)
    for f in V6:
        shutil.copy2(REPO / "src/phd/prior_propagation_v6" / f, out / "src/phd/prior_propagation_v6" / f)
    shared = {f: dict(repo=sha(REPO / "src/phd/prior_propagation_v6" / f), fork=sha(out / "src/phd/prior_propagation_v6" / f)) for f in V6}
    if any(v["repo"] != v["fork"] for v in shared.values()):
        raise SystemExit("the fork's shared module v6 differs from the repository's v6")
    (prov / "patches").mkdir(parents=True, exist_ok=True)
    changed = {}
    for rel in files(out):
        src, new = parent / rel, out / rel
        if not src.exists() or sha(src) != sha(new):
            changed[rel] = dict(r11=sha(src) if src.exists() else None, r12=sha(new))
            a_txt = src.read_text().splitlines(True) if src.exists() else []
            (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
                "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r11/{rel}", f"r12/{rel}")))
    removed = [rel for rel in files(parent) if not (out / rel).exists()]
    expected = set(CHANGED) | {f"src/phd/prior_propagation_v6/{f}" for f in V6}
    rep = dict(task_id="PHD-MAIN-STAGE0-v1", fork="r12", parent=str(parent.relative_to(REPO)) if parent.is_relative_to(REPO) else str(parent),
               out=str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out), built_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               repo_commit=a.repo_commit, n_files=len(files(out)), changed_or_added=changed, removed=removed, shared_module_v6=shared,
               fork_r12_sources={rel: sha(HERE / "fork_r12" / rel) for rel in CHANGED},
               only_expected_changes=bool(set(changed) == expected and not removed), scientific_verdict=None)
    (prov / "build_report_r12.json").write_text(json.dumps(rep, indent=1))
    print("fork r12 built", out, "files", rep["n_files"], "changed", sorted(changed), "only expected", rep["only_expected_changes"])
    if not rep["only_expected_changes"]:
        raise SystemExit("unexpected differences between r11 and r12")


if __name__ == "__main__":
    main()
