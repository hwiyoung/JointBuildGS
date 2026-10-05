"""Build the stage-2 fork r7 from the frozen r6 fork (stdlib only, reproducible; PHD-STAGE2-R7-PROPAGATION-v1).

  python build_fork_r7.py --parent <R6>/sources/GeoGS-conf-guided-v1-r6 --out <R7>/sources/GeoGS-conf-guided-v1-r7
                          --provenance <R7>/provenance --repo <repo root> [--repo_commit <sha>]

r6 is only read. r7 = r6 with
  jbgs_judgment.py            replaced by the r7 module next to this script (location-based judgments, propagation,
                              re-read, protection, prior-term gate, attributes, dry run)
  scene/gaussian_model.py     save_ply appends the columns returned by gaussians.jbgs_ply_extra() (4-byte fields)
  src/phd/prior_propagation_v1/*.py  the shared module, copied from the repository (sha256 must match; not edited here)
Provenance: unified diffs of the changed files, sha256 of every changed or added file, the list of files that differ
between the trees (must be exactly these), build_report_r7.json."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("media", ".git", "__pycache__", "*.pyc")
MARK = "# [jbgs_judgment r7]"
SHARED = ["conversion.py", "tolerance.py", "surfaces.py", "outlines.py", "rule.py", "locations.py", "seat.py"]   # namespace package, no __init__

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


GM_EDITS = [
    ("""        else:
            origin_col = None
        elements = np.empty(xyz.shape[0], dtype=dtype_full)
""", f"""        else:
            origin_col = None
        {MARK} extra per-Gaussian columns (surface number, location, judgment, Gaussian confidence), 4-byte fields
        extra_fn = getattr(self, "jbgs_ply_extra", None)
        extra = extra_fn() if callable(extra_fn) else {{}}
        extra = {{k: v for k, v in extra.items() if len(v) == xyz.shape[0]}}
        for k, v in extra.items():
            dtype_full = dtype_full + [(k, 'i4' if np.issubdtype(np.asarray(v).dtype, np.integer) else 'f4')]
        elements = np.empty(xyz.shape[0], dtype=dtype_full)
"""),
    ("""        if origin_col is not None:
            attributes = np.concatenate((attributes, origin_col), axis=1)
        elements[:] = list(map(tuple, attributes))
""", f"""        if origin_col is not None:
            attributes = np.concatenate((attributes, origin_col), axis=1)
        if extra:  {MARK}
            attributes = np.concatenate([attributes] + [np.asarray(v).reshape(-1, 1).astype(np.float32) for v in extra.values()], axis=1)
        elements[:] = list(map(tuple, attributes))
"""),
]

shutil.copytree(parent, out, ignore=IGNORE, symlinks=True)
shutil.copy2(HERE / "jbgs_judgment.py", out / "jbgs_judgment.py")
gp = out / "scene/gaussian_model.py"
s = gp.read_text()
for i, (old, new) in enumerate(GM_EDITS):
    if s.count(old) != 1:
        raise SystemExit(f"gaussian_model.py anchor {i} found {s.count(old)} times")
    s = s.replace(old, new)
gp.write_text(s)
src_dir = repo / "src/phd/prior_propagation_v1"
dst_dir = out / "src/phd/prior_propagation_v1"
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
        changed[rel] = dict(r6=sha(src) if src.exists() else None, r7=sha(new))
        a_txt = src.read_text().splitlines(True) if src.exists() else []
        (prov / "patches" / (rel.replace("/", "_") + ".diff")).write_text(
            "".join(difflib.unified_diff(a_txt, new.read_text().splitlines(True), f"r6/{rel}", f"r7/{rel}")))
removed = [rel for rel in files(parent) if not (out / rel).exists()]
expected = {"jbgs_judgment.py", "scene/gaussian_model.py"} | {f"src/phd/prior_propagation_v1/{f}" for f in SHARED}
report = dict(built_at=dt.datetime.now(dt.timezone.utc).isoformat(), revision="r7", parent=str(parent), parent_revision="r6",
              out=str(out), changed_files=changed, removed_files=removed, shared_module=shared,
              only_expected_files_changed=bool(set(changed) == expected and not removed),
              overlay_sha256=sha(HERE / "jbgs_judgment.py"), build_script_sha256=sha(__file__), repo_commit=a.repo_commit,
              changes=["r7-1 initialisation by location state and propagated judgment", "r7-2 re-read of E every e_interval",
                       "r7-3 protection: judgment not conflict, E < threshold, drift <= mult x tau of the surface kind",
                       "r7-4 prior-term gate at propagated-conflict pixels", "r7-5 attributes (dumps, PLY columns)", "r7-6 dry run"],
              scientific_verdict=None)
(prov / "build_report_r7.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: report[k] for k in ("only_expected_files_changed", "removed_files")}), sorted(changed))
