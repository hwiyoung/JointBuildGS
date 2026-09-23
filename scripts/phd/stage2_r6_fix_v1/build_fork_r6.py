"""Build the stage-2 fork r6 from the frozen r5 fork (stdlib only, reproducible; PHD-STAGE2-R6-FIX-v1).

  python build_fork_r6.py --parent <S2>/sources/GeoGS-conf-guided-v1 --out <R6>/sources/GeoGS-conf-guided-v1-r6
                          --provenance <R6>/provenance [--repo_commit <sha>]

r5 (the fork of the 11-condition run) is only read. r6 = r5 with
  jbgs_judgment.py  replaced by the r6 module next to this script (the five fixes of the 4.4 audit),
  train.py          one line: the Judgment gets the renderer (render, pipe, background) so that E can render the
                    training views (fix 1).
Provenance: unified diffs r5 -> r6 of the changed files, sha256 of every changed file, the list of files that differ
between the two trees (must be exactly these two), build_report.json."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")
MARK = "# [jbgs_judgment r6]"

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


def files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith("media/"))


TRAIN_EDITS = [
    ("    judgment = jbgs_judgment.Judgment(args, opt, scene, gaussians, tb_writer) if args.jbgs_judgment != \"off\" else None\n",
     "    judgment = jbgs_judgment.Judgment(args, opt, scene, gaussians, tb_writer, render_fn=render, pipe=pipe, background=background) "
     f"if args.jbgs_judgment != \"off\" else None  {MARK} E renders the training views (fix 1)\n"),
]

shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
shutil.copy2(HERE / "jbgs_judgment.py", out / "jbgs_judgment.py")
tp = out / "train.py"
s0 = tp.read_text()
s = s0
for i, (old, new) in enumerate(TRAIN_EDITS):
    if s.count(old) != 1:
        raise SystemExit(f"train.py anchor {i} found {s.count(old)} times:\n{old}")
    s = s.replace(old, new)
tp.write_text(s)

(prov / "patches").mkdir(parents=True, exist_ok=True)
changed = {}
for rel in files(out):
    src, new = parent / rel, out / rel
    if not src.exists() or sha(src) != sha(new):
        changed[rel] = dict(r5=sha(src) if src.exists() else None, r6=sha(new))
        a_txt = src.read_text().splitlines(True) if src.exists() else []
        (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
            "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r5/{rel}", f"r6/{rel}")))
removed = [rel for rel in files(parent) if not (out / rel).exists()]
expected = {"jbgs_judgment.py", "train.py"}
report = dict(built_at=dt.datetime.now(dt.timezone.utc).isoformat(), revision="r6", parent=str(parent), parent_revision="r5",
              out=str(out), changed_files=changed, removed_files=removed,
              only_expected_files_changed=bool(set(changed) == expected and not removed),
              overlay_sha256=sha(HERE / "jbgs_judgment.py"), build_script_sha256=sha(__file__),
              repo_commit=a.repo_commit, fixes=["(1) occlusion by the current render after the first E",
                                                "(1a) E at iteration 1 and every multiple of e_interval, start of iteration",
                                                "(2) protection: E < 0.5 and drift <= 4 tau_v",
                                                "(3) opacity floor at the moment protection is set",
                                                "(4) initial prior points no training view sees are removed",
                                                "(5) both depth terms divided by the pixel count of the view"],
              scientific_verdict=None)
(prov / "build_report_r6.json").write_text(json.dumps(report, indent=1))
(prov / "r6_source_sha256.txt").write_text("".join(f"{sha(out / rel)}  {rel}\n" for rel in files(out)))
print(json.dumps({k: report[k] for k in ("changed_files", "removed_files", "only_expected_files_changed")}, indent=1))
if not report["only_expected_files_changed"]:
    raise SystemExit("unexpected files changed")
