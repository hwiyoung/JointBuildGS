#!/usr/bin/env python3
"""Build fork r16 from the committed fork r15 (stdlib only, reproducible from the repository; PHD-MAIN-FIXTEST-v1 6.1).

  python3 build_fork_r16.py [--parent src/phd/forks/GeoGS-conf-guided-v1-r15] [--out src/phd/forks/GeoGS-conf-guided-v1-r16]
                            [--provenance docs/experiments/phd/main_fixtest_v1/provenance] [--repo_commit <sha>]

r15 is only read. r16 = r15 with jbgs_judgment.py replaced from fork_r16/ next to this script: two switches, both 0 by default
(--jbgs_sw_prior_share_band = fix A, --jbgs_sw_own_depth_release = fix B; see the module's docstring). train.py,
scene/gaussian_model.py and the shared module v6 copy are r15's, byte for byte (the switches are registered by the judgment
module's register_args, which train.py already calls). Provenance: unified diff, sha256, the list of files that differ (must be
exactly jbgs_judgment.py), build_report_r16.json. scientific_verdict: null."""
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
CHANGED = ["jbgs_judgment.py"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith(("media/", "submodules/")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", default=str(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r15"))
    ap.add_argument("--out", default=str(REPO / "src/phd/forks/GeoGS-conf-guided-v1-r16"))
    ap.add_argument("--provenance", default=str(REPO / "docs/experiments/phd/main_fixtest_v1/provenance"))
    ap.add_argument("--repo_commit", default="")
    a = ap.parse_args()
    parent, out, prov = Path(a.parent), Path(a.out), Path(a.provenance)
    if out.exists():
        raise SystemExit(f"{out} exists; move it aside first (nothing is overwritten)")
    shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
    for rel in CHANGED:
        shutil.copy2(HERE / "fork_r16" / rel, out / rel)
    (prov / "patches").mkdir(parents=True, exist_ok=True)
    changed = {}
    for rel in files(out):
        src, new = parent / rel, out / rel
        if not src.exists() or sha(src) != sha(new):
            changed[rel] = dict(r15=sha(src) if src.exists() else None, r16=sha(new))
            a_txt = src.read_text().splitlines(True) if src.exists() else []
            (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
                "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r15/{rel}", f"r16/{rel}")))
    removed = [rel for rel in files(parent) if not (out / rel).exists()]
    keep = ["train.py", "scene/gaussian_model.py"] + [r for r in files(out) if r.startswith("src/phd/prior_propagation_v6/")]
    rep = dict(task_id="PHD-MAIN-FIXTEST-v1", fork="r16", parent=str(parent.relative_to(REPO)) if parent.is_relative_to(REPO) else str(parent),
               out=str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out), built_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               repo_commit=a.repo_commit, n_files=len(files(out)), changed_or_added=changed, removed=removed,
               equal_to_r15={rel: sha(parent / rel) == sha(out / rel) for rel in keep},
               fork_r16_sources={rel: sha(HERE / "fork_r16" / rel) for rel in CHANGED},
               only_expected_changes=bool(set(changed) == set(CHANGED) and not removed), scientific_verdict=None)
    (prov / "build_report_r16.json").write_text(json.dumps(rep, indent=1))
    print("fork r16 built", out, "files", rep["n_files"], "changed", sorted(changed), "only expected", rep["only_expected_changes"],
          "kept equal", all(rep["equal_to_r15"].values()))
    if not rep["only_expected_changes"] or not all(rep["equal_to_r15"].values()):
        raise SystemExit("unexpected differences between r15 and r16")


if __name__ == "__main__":
    main()
