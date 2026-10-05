"""Build the stage-2 GeoGS fork from its parent source (reproducible, stdlib only).

  python build_fork.py --parent <GeoGS-mvs-pgsr-v1> --out <S2>/sources/GeoGS-conf-guided-v1 --provenance <S2>/provenance
                       [--supersede r1] [--repo_commit <sha>]

1. copy the parent tree (without media/, .git, __pycache__) to --out,
2. copy the overlay module jbgs_judgment.py (next to this script) into it,
3. apply patch_geogs_fork.py (anchored edits),
4. write provenance: patches/<file>.diff (unified diff vs parent), patches/<new file>.new, patched_source_sha256.txt
   (changed and new files), fork_source_sha256.txt (every file), build_report.json.
--supersede TAG moves an existing --out to <parent of out>/superseded/<name>_<TAG> and the existing provenance files
to <provenance>/superseded_<TAG>/ instead of refusing (nothing is deleted)."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")

ap = argparse.ArgumentParser()
ap.add_argument("--parent", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--provenance", required=True)
ap.add_argument("--supersede", default="")
ap.add_argument("--repo_commit", default="")
a = ap.parse_args()
parent, out, prov = Path(a.parent), Path(a.out), Path(a.provenance)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def files(root):
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not str(p.relative_to(root)).startswith("media/"))


moved = {}
if out.exists():
    if not a.supersede:
        raise SystemExit(f"{out} exists; pass --supersede TAG to move it aside")
    dst = out.parent / "superseded" / f"{out.name}_{a.supersede}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise SystemExit(f"{dst} exists")
    shutil.move(str(out), str(dst))
    moved["fork"] = str(dst)
old = [p for p in (prov / "patches", prov / "patched_source_sha256.txt", prov / "fork_source_sha256.txt",
                   prov / "build_report.json") if p.exists()]
if old:
    if not a.supersede:
        raise SystemExit(f"provenance files exist: {old}; pass --supersede TAG")
    sdir = prov / f"superseded_{a.supersede}"
    sdir.mkdir(parents=True, exist_ok=False)
    for p in old:
        shutil.move(str(p), str(sdir / p.name))
    moved["provenance"] = str(sdir)

shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
shutil.copy2(HERE / "jbgs_judgment.py", out / "jbgs_judgment.py")
r = subprocess.run([sys.executable, str(HERE / "patch_geogs_fork.py"), str(out)], capture_output=True, text=True)
if r.returncode:
    raise SystemExit(f"patch failed:\n{r.stdout}\n{r.stderr}")

(prov / "patches").mkdir(parents=True, exist_ok=True)
changed = []
for rel in files(out):
    src = parent / rel
    new = (out / rel)
    if not src.exists():
        shutil.copy2(new, prov / "patches" / (str(rel).replace("/", "_") + ".new"))
        changed.append(rel)
    elif sha(src) != sha(new):
        diff = difflib.unified_diff(src.read_text().splitlines(True), new.read_text().splitlines(True),
                                    fromfile=f"parent/{rel}", tofile=f"fork/{rel}")
        (prov / "patches" / (str(rel).replace("/", "_") + ".diff")).write_text("".join(diff))
        changed.append(rel)
(prov / "patched_source_sha256.txt").write_text("".join(f"{sha(out / rel)}  {rel}\n" for rel in changed))
(prov / "fork_source_sha256.txt").write_text("".join(f"{sha(out / rel)}  {rel}\n" for rel in files(out)))
report = dict(built_at=dt.datetime.now(dt.timezone.utc).isoformat(), parent=str(parent), out=str(out),
              overlay_sha256=sha(HERE / "jbgs_judgment.py"), patch_script_sha256=sha(HERE / "patch_geogs_fork.py"),
              build_script_sha256=sha(Path(__file__).resolve()), repo_commit=a.repo_commit or None,
              changed_files=[str(c) for c in changed], patch_report=json.loads(r.stdout), superseded=moved,
              scientific_verdict=None)
(prov / "build_report.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: report[k] for k in ("out", "changed_files", "superseded")}, indent=1))
