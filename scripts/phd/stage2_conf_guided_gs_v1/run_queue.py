#!/usr/bin/env python3
"""Run stage-2 conditions one after another on one GPU (host orchestration, stdlib only). Resumable and idempotent,
meant to run as a detached systemd user service:

  systemd-run --user --unit jbgs-s2-queue-gpu0 ... python3 run_queue.py --gpu 0 P_M_B P0_M_B ...

For each condition:
  1. a PASS receipt exists                      -> skip training
  2. its container (jbgs-s2-<cond>) is running  -> wait until it ends (a run started elsewhere), then re-check 1
  3. otherwise run_condition.py (it moves an interrupted attempt aside first)
  4. after PASS: evaluation render at the final iteration with the calibrated cameras (render_depths.py), if missing
A failed condition is written to logs/issues.jsonl with the tail of its log and the queue moves on (ORDER section 8).
At the end: evaluate.py over every condition rendered so far (the last queue to finish writes the complete tables).
logs/STOP_QUEUE or logs/STOP_QUEUE_GPU<gpu> stops the queue before its next condition. Progress: logs/queue_gpu<gpu>.jsonl."""
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
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
IMG_JUDG, IMG_DEV = "jointbuildgs:geogs-conf-guided-v1", "jointbuildgs:dev"

ap = argparse.ArgumentParser()
ap.add_argument("conds", nargs="+")
ap.add_argument("--gpu", required=True)
ap.add_argument("--iterations", type=int, default=30000)
ap.add_argument("--lambda_mvs", type=float, default=0.05)
ap.add_argument("--lambda_prior", type=float, default=0.05)
a = ap.parse_args()
LOGS = S2 / "logs"
qlog = LOGS / f"queue_gpu{a.gpu}.jsonl"
lock = LOGS / f"queue_gpu{a.gpu}.lock"


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def note(**kw):
    kw["at"] = now()
    with qlog.open("a") as f:
        f.write(json.dumps(kw) + "\n")


def issue(**kw):
    with (LOGS / "issues.jsonl").open("a") as f:
        f.write(json.dumps(dict(at=now(), scientific_verdict=None, **kw)) + "\n")


def passed(cond):
    r = S2 / "runs" / cond / "receipt.json"
    return r.exists() and json.loads(r.read_text()).get("status") == "PASS"


def running(name):
    out = subprocess.run(["docker", "ps", "-q", "--filter", f"name=^/{name}$"], capture_output=True, text=True).stdout
    return bool(out.strip())


def uid():
    return f"{os.getuid()}:{os.getgid()}"


def render_eval(cond):
    out = S2 / "eval" / cond / f"render_{a.iterations}"
    if (out / "receipt.json").exists():
        return 0
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-s2-render-{cond}".replace("_", "-"), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", uid(), "-e", "HOME=/tmp", "-e", "TORCH_HOME=/weights/torch",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2", "-v", f"{WEIGHTS}:/weights:ro",
           "-v", f"{S2}/sources/GeoGS-conf-guided-v1:/source:ro", "-v", f"{REPO}:/repo:ro", "-w", "/source",
           "--entrypoint", "python", IMG_JUDG, "/repo/scripts/phd/stage2_conf_guided_gs_v1/render_depths.py",
           "--model_dir", f"/s2/runs/{cond}/model", "--iteration", str(a.iterations), "--out", f"/s2/eval/{cond}/render_{a.iterations}"]
    with (LOGS / f"render_{cond}_{a.iterations}.log").open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode


def evaluate():
    cmd = ["docker", "run", "--rm", "--network", "none", "--user", uid(), "-e", "HOME=/tmp", "-v", f"{S2}:/s2",
           "-v", f"{REPO}:/repo:ro", "--entrypoint", "python", IMG_DEV,
           "/repo/scripts/phd/stage2_conf_guided_gs_v1/evaluate.py", "--iteration", str(a.iterations)]
    with (LOGS / f"evaluate_gpu{a.gpu}.log").open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode


if lock.exists():
    pid = int(lock.read_text().split()[0])
    try:
        os.kill(pid, 0)
        raise SystemExit(f"queue for GPU {a.gpu} already running (pid {pid})")
    except ProcessLookupError:
        pass
lock.write_text(f"{os.getpid()} {now()}\n")
try:
    note(event="queue_start", gpu=a.gpu, conds=a.conds, iterations=a.iterations, pid=os.getpid(),
         lambda_mvs=a.lambda_mvs, lambda_prior=a.lambda_prior)
    for cond in a.conds:
        if (LOGS / "STOP_QUEUE").exists() or (LOGS / f"STOP_QUEUE_GPU{a.gpu}").exists():
            note(event="queue_stopped_by_file", next=cond)
            break
        name = f"jbgs-s2-{cond}".replace("_", "-")
        if not passed(cond) and running(name):
            note(event="wait_running", cond=cond, container=name)
            while running(name):
                time.sleep(30)
            time.sleep(10)  # let the launching process write its receipt
            note(event="waited", cond=cond, passed=passed(cond))
        if passed(cond):
            note(event="skip_passed", cond=cond)
        else:
            note(event="start", cond=cond)
            rc = subprocess.run([sys.executable, str(HERE.parent / "run_condition.py"), cond, "--gpu", a.gpu,
                                 "--iterations", str(a.iterations), "--lambda_mvs", str(a.lambda_mvs),
                                 "--lambda_prior", str(a.lambda_prior)]).returncode
            note(event="end", cond=cond, exit_code=rc)
            if rc != 0:
                log = LOGS / f"train_{cond}.log"
                tail = log.read_text(errors="replace").replace("\r", "\n").splitlines()[-12:] if log.exists() else []
                stop = S2 / "runs" / cond / "model" / "monitor" / "stop.json"
                issue(condition=cond, stage="main", exit_code=rc, red_stop=json.loads(stop.read_text()) if stop.exists() else None,
                      log_tail=tail, action="queue continues with the next condition (ORDER 8)")
                continue
        rc = render_eval(cond)
        note(event="render_eval", cond=cond, exit_code=rc)
        if rc != 0:
            issue(condition=cond, stage="render_eval", exit_code=rc, log=f"logs/render_{cond}_{a.iterations}.log")
    rc = evaluate()
    note(event="evaluate", exit_code=rc)
    note(event="queue_end")
finally:
    if lock.exists() and lock.read_text().split()[0] == str(os.getpid()):
        lock.unlink()
