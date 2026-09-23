#!/usr/bin/env python3
"""Run the instrumented r6 trainings in Docker and write receipts (host orchestration only, stdlib; PHD-STAGE2-R6-FIX-v1).

  python run_r6.py --gpu 0 N                 # configured length (3,500)
  python run_r6.py --gpu 1 --smoke 700 B --smoke_extra --jbgs_e_interval 250 --opacity_reset_interval 500

Command line = the r5 audit launcher (scripts/phd/stage2_protection_audit_v1/run_audit.py), i.e. run_condition.py for a P
condition, with the r6 audit copy as /source and the stage-2 payload mounted read-only.
Outputs: <R6>/runs/<RUN>/{model/, audit/, receipt.json}, <R6>/logs/train_<RUN>.log"""
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
R6 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R6-FIX-v1"
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
CFG = json.loads((REPO / "configs/phd/stage2_r6_fix_v1/r6.json").read_text())
IMG = CFG["image"]

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gpu", default="0")
ap.add_argument("--smoke", type=int, default=0)
ap.add_argument("--cpus", default="8")
ap.add_argument("--smoke_extra", nargs=argparse.REMAINDER, default=[], help="smoke runs only: extra train.py arguments")
a = ap.parse_args()
if a.smoke_extra and not a.smoke:
    raise SystemExit("--smoke_extra is for smoke runs only")

rc_all = 0
for run in a.runs:
    spec = CFG["runs"][run]
    cond = json.loads((S2 / "runs" / spec["condition"] / "condition.json").read_text())
    its = a.smoke or int(CFG["iterations"])
    name = run if not a.smoke else f"{run}_smoke{its}"
    rdir = R6 / "runs" / name
    if (rdir / "receipt.json").exists() and json.loads((rdir / "receipt.json").read_text()).get("status") == "PASS":
        print(f"{name}: PASS receipt exists, skipped"); continue
    if rdir.exists():
        rdir.rename(R6 / "runs" / f"{name}_interrupted_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    rdir.mkdir(parents=True)
    snap = sorted({i for i in (2000, its) if i <= its})
    saves = sorted({8000, its, *[i for i in spec["save_extra"] if i < its]})
    extra = [x for x in spec["extra"]] if not a.smoke else []
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-s2-r6-{name}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", a.cpus, "--shm-size", "8g",
           "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
           "-e", f"OMP_NUM_THREADS={a.cpus}",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R6}:/r6", "-v", f"{WEIGHTS}:/weights:ro",
           "-v", f"{R6}/sources/GeoGS-conf-guided-v1-r6-audit:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
           "train.py", "-s", f"/s2/runs/{spec['condition']}/scene", "-m", f"/r6/runs/{name}/model", "--eval",
           "--lod_depth_path", f"/s2/runs/{spec['condition']}/none", "--da_depth_path", f"/s2/runs/{spec['condition']}/none",
           "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
           "--jbgs_judgment", cond["mode"], "--jbgs_maps_root", "/s2/inputs/maps",
           "--jbgs_faces_json", "/s2/inputs/maps/faces.json", "--jbgs_scene", cond["scene"],
           "--jbgs_origin_path", cond["origin_path"], "--jbgs_lambda_mvs", "0.05", "--jbgs_lambda_prior", "0.05",
           "--iterations", str(its), "--test_iterations", *map(str, snap), "--save_iterations", *map(str, saves),
           "--jbgs_snapshot_iterations", *map(str, snap), "--jbgs_dump_iterations", *map(str, sorted({min(15000, its), its})),
           "--jbgs_prior_set", cond["prior_set"], "--jbgs_tau_set", cond["tau_set"], "--jbgs_tau_v", str(cond["tau_v"]),
           "--jbgs_audit_dir", f"/r6/runs/{name}/audit",
           "--jbgs_audit_hist_iterations", *map(str, sorted({1, min(500, its), max(1, min(2999, its)), min(3000, its),
                                                              min(3001, its), its})),
           *extra, *a.smoke_extra]
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id=CFG["task_id"], run=name, spec=spec, condition_json=cond, gpu=a.gpu, iterations=its, image=IMG,
               image_id=image_id, repo_commit=commit, command=cmd, started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               build_report=json.loads((R6 / "provenance/build_report_r6.json").read_text()), scientific_verdict=None)
    log = R6 / "logs" / f"train_{name}.log"
    t0 = time.monotonic()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    rec.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), seconds=time.monotonic() - t0, exit_code=rc,
               status="PASS" if rc == 0 else "FAIL", log=str(log.relative_to(R6)))
    (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec[k] for k in ("run", "status", "exit_code", "seconds")}), flush=True)
    rc_all = rc_all or rc
sys.exit(rc_all)
