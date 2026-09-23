#!/usr/bin/env python3
"""Launch mesh_r10.py for trained runs, one at a time (host memory; stdlib; PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).
  python run_mesh_r10.py --gpu 1 M_N M_N_rep L_N_cell
Outputs: <R10>/mesh/<run>/..., <R10>/logs/mesh_<run>.log and .receipt.json"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
ART = (REPO.parent / "JointBuildGS-artifacts").resolve()
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
R9 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R9-THREE-FIXES-v1"
R10 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1"
R8 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R8-FOUR-CASES-v1"
IMG = "jointbuildgs:geogs-conf-guided-v1"
ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gpu", default="0")
a = ap.parse_args()
rc_all = 0
for run in a.runs:
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-r10-mesh-{run}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "8", "--shm-size", "8g",
           "-e", "PYTHONUNBUFFERED=1", "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp/mpl",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R9}:/p9:ro", "-v", f"{R10}:/p10", "-v", f"{R8}:/r8:ro",
           "-v", f"{REPO}:/repo:ro", "-v", f"{R10}/sources/GeoGS-conf-guided-v1-r10:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
           "/repo/scripts/phd/stage2_r10_two_fixes_three_checks_v1/mesh_r10.py", run]
    tag = run
    log = R10 / "logs" / f"mesh_{tag}.log"
    t0 = time.monotonic(); start = dt.datetime.now(dt.timezone.utc).isoformat()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and (R10 / "mesh" / tag / "mesh.json").exists()
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    (R10 / "logs" / f"mesh_{tag}.receipt.json").write_text(json.dumps(dict(run=run, image=IMG, image_id=image_id, command=cmd, started_at=start,
                                                                         seconds=time.monotonic() - t0, exit_code=rc,
                                                                         status="PASS" if ok else "FAIL", scientific_verdict=None), indent=1))
    print(run, "PASS" if ok else "FAIL", rc, flush=True)
    rc_all = rc_all or (0 if ok else 1)
sys.exit(rc_all)
