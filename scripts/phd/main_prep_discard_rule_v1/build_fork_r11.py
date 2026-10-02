"""Build the stage-2 fork r11 from the frozen r10 fork (stdlib only, reproducible; PHD-MAIN-PREP-DISCARD-RULE-v1 5.1).

  python3 build_fork_r11.py --parent <R10>/sources/GeoGS-conf-guided-v1-r10 --out <P>/sources/GeoGS-conf-guided-v1-r11
                            --provenance <P>/provenance --repo <repo root> [--repo_commit <sha>]

r10 is only read. r11 = r10 with jbgs_judgment.py and scene/dataset_readers.py replaced by the files of make_fork_r11_files.py
(fork_r11/ next to this script) and the shared module src/phd/prior_propagation_v5 copied from the repository (sha256 checked).
Provenance: unified diffs, sha256 of every changed or added file, the list of files that differ (must be exactly the two files
plus the added module), build_report_r11.json. scientific_verdict: null."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")
V5 = ["conversion.py", "tolerance.py", "surfaces.py", "outlines.py", "rule.py", "locations.py", "seat.py", "faces.py", "orientation.py",
      "registration.py", "caps.py", "tallies.py", "rules.py", "switches.py"]
CHANGED = ["jbgs_judgment.py", "scene/dataset_readers.py"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith("media/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", required=True); ap.add_argument("--out", required=True); ap.add_argument("--provenance", required=True)
    ap.add_argument("--repo", required=True); ap.add_argument("--repo_commit", default="")
    a = ap.parse_args()
    parent, out, prov, repo = Path(a.parent), Path(a.out), Path(a.provenance), Path(a.repo)
    if out.exists():
        raise SystemExit(f"{out} exists; move it aside first (nothing is overwritten)")
    shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
    for rel in CHANGED:
        shutil.copy2(HERE / "fork_r11" / rel, out / rel)
    (out / "src/phd/prior_propagation_v5").mkdir(parents=True, exist_ok=True)
    for f in V5:
        shutil.copy2(repo / "src/phd/prior_propagation_v5" / f, out / "src/phd/prior_propagation_v5" / f)
    shared = {f: dict(repo=sha(repo / "src/phd/prior_propagation_v5" / f), fork=sha(out / "src/phd/prior_propagation_v5" / f)) for f in V5}
    if any(v["repo"] != v["fork"] for v in shared.values()):
        raise SystemExit("the fork's shared module v5 differs from the repository's v5")
    (prov / "patches").mkdir(parents=True, exist_ok=True)
    changed = {}
    for rel in files(out):
        src, new = parent / rel, out / rel
        if not src.exists() or sha(src) != sha(new):
            changed[rel] = dict(r10=sha(src) if src.exists() else None, r11=sha(new))
            a_txt = src.read_text().splitlines(True) if src.exists() else []
            (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
                "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r10/{rel}", f"r11/{rel}")))
    removed = [rel for rel in files(parent) if not (out / rel).exists()]
    expected = set(CHANGED) | {f"src/phd/prior_propagation_v5/{f}" for f in V5}
    rep = dict(task_id="PHD-MAIN-PREP-DISCARD-RULE-v1", fork="r11", parent=str(parent), out=str(out), built_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               repo_commit=a.repo_commit, changed_or_added=changed, removed=removed, shared_module_v5=shared,
               only_expected_changes=bool(set(changed) == expected and not removed), scientific_verdict=None)
    (prov / "build_report_r11.json").write_text(json.dumps(rep, indent=1))
    print("fork r11 built", out, "changed", sorted(changed), "only expected", rep["only_expected_changes"])
    if not rep["only_expected_changes"]:
        raise SystemExit("unexpected differences between r10 and r11")


if __name__ == "__main__":
    main()
