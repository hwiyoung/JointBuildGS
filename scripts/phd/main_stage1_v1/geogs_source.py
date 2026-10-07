#!/usr/bin/env python3
"""PHD-MAIN-STAGE1-v1 GeoGS (always-trust LoD2) source copy with the two input adapters decided by the user on 2026-10-07 (host, stdlib).

The official GeoGS checkout (zqlin0521/GeoGS db40c95, phase payload geogs_p1p2p3_v1 sources/GeoGS, untouched) is copied without .git to
<payload>/geogs/source/GeoGS-official-adapters-v1. Two files are replaced by their fork-r12 versions, whose only differences from the
official files are the adapters (checked here hunk by hunk), and the adapter module is added:
  utils/camera_utils.py     loadCam returns maybe_calibrate_camera(...): the principal point from <-s>/jbgs_calibration.json (the
                            camera adapter of the earlier GeoGS work; scenes without the file keep the official behaviour)
  scene/dataset_readers.py  JBGS_SPLIT_JSON (train / test names) instead of the every-8th split when the variable is set
  jbgs_camera_adapter.py    the adapter module (byte-identical to fork r12 and to the earlier work's copy)
Nothing else differs from the official code. Writes source_manifest.json (sha256 of every file, the unified diff of the two files).

  python3 geogs_source.py
scientific_verdict: null."""
import difflib
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
ART = (REPO.parent / "JointBuildGS-artifacts").resolve()
SRC = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/sources/GeoGS"
FORK = REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12"
OUT = ART / "phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1/geogs/source/GeoGS-official-adapters-v1"
COMMIT = "db40c95c657ec03ff21c83cb99cf39f4e90247a6"
REPLACED = ["utils/camera_utils.py", "scene/dataset_readers.py"]
ADDED = ["jbgs_camera_adapter.py"]
ALLOWED = {  # the only lines the fork versions may add (stripped), per file
    "utils/camera_utils.py": {"from jbgs_camera_adapter import maybe_calibrate_camera", "camera = Camera(colmap_id=cam_info.uid, R=cam_info.R, T=cam_info.T,",
                              "return maybe_calibrate_camera(camera, args, cam_info)"},
    "scene/dataset_readers.py": None,      # the split hunk, checked by its markers below
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    head = (SRC / ".git/HEAD").read_text().strip()
    ref = (SRC / ".git" / head.split()[1]).read_text().strip() if head.startswith("ref:") else head
    assert ref == COMMIT, f"official checkout is at {ref}, expected {COMMIT}"
    if OUT.exists():
        raise FileExistsError(f"{OUT} exists; a new copy needs a new name")
    shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns(".git"))
    diffs = {}
    for rel in REPLACED:
        a, b = (SRC / rel).read_text().splitlines(), (FORK / rel).read_text().splitlines()
        d = list(difflib.unified_diff(a, b, f"official/{rel}", f"fork_r12/{rel}", lineterm="", n=1))
        added = [l[1:].strip() for l in d if l.startswith("+") and not l.startswith("+++")]
        removed = [l[1:].strip() for l in d if l.startswith("-") and not l.startswith("---")]
        if rel == "utils/camera_utils.py":
            assert set(added) <= ALLOWED[rel] and removed == ["return Camera(colmap_id=cam_info.uid, R=cam_info.R, T=cam_info.T,"], (rel, added, removed)
        else:
            assert removed == ["if eval:"] and any("JBGS_SPLIT_JSON" in l for l in added) and added[-1] == "elif eval:", (rel, added, removed)
        shutil.copy2(FORK / rel, OUT / rel)
        diffs[rel] = "\n".join(d)
    for rel in ADDED:
        shutil.copy2(FORK / rel, OUT / rel)
    files = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
    man = dict(task_id="PHD-MAIN-STAGE1-v1", official_commit=COMMIT, official_source=str(SRC.relative_to(ART)), fork=str(FORK.relative_to(REPO)),
               replaced=REPLACED, added=ADDED, diffs=diffs, files=files, rule=__doc__, scientific_verdict=None)
    (OUT.parent / "source_manifest.json").write_text(json.dumps(man, indent=1))
    print("copied", len(files), "files;", {k: len(v.splitlines()) for k, v in diffs.items()}, "diff lines")


if __name__ == "__main__":
    main()
