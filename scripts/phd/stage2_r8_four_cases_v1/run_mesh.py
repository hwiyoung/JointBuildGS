#!/usr/bin/env python3
"""Launch mesh_r8.py for trained runs (host orchestration only, stdlib; PHD-STAGE2-R8-FOUR-CASES-v1).
  python run_mesh.py --gpu 0 M_N M_N_noprior L_N
Outputs: <R8>/mesh/<run>/..., <R8>/logs/mesh_<run>.log and .receipt.json"""
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
R8 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R8-FOUR-CASES-v1"
IMG = "jointbuildgs:geogs-conf-guided-v1"
ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gpu", default="0")
a = ap.parse_args()
rc_all = 0
for run in a.runs:
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-r8-mesh-{run}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "8", "--shm-size", "8g",
           "-e", "PYTHONUNBUFFERED=1", "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp/mpl",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R8}:/p8", "-v", f"{REPO}:/repo:ro",
           "-v", f"{R8}/sources/GeoGS-conf-guided-v1-r8:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
           "/repo/scripts/phd/stage2_r8_four_cases_v1/mesh_r8.py", run]
    log = R8 / "logs" / f"mesh_{run}.log"
    t0 = time.monotonic(); start = dt.datetime.now(dt.timezone.utc).isoformat()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and (R8 / "mesh" / run / "mesh.json").exists()
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    (R8 / "logs" / f"mesh_{run}.receipt.json").write_text(json.dumps(dict(run=run, image=IMG, image_id=image_id, command=cmd, started_at=start,
                                                                         seconds=time.monotonic() - t0, exit_code=rc,
                                                                         status="PASS" if ok else "FAIL", scientific_verdict=None), indent=1))
    print(run, "PASS" if ok else "FAIL", rc, flush=True)
    rc_all = rc_all or (0 if ok else 1)
sys.exit(rc_all)
