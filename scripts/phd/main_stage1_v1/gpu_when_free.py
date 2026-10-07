#!/usr/bin/env python3
"""PHD-MAIN-STAGE1-v1: GPU steps (run_gpu.sh) while the trainings run (host orchestration only, stdlib). Takes the slot lock (at most
two trainings + one other Docker job), then waits for a GPU by the rule of the training runner's post worker (run_stage1.pick_gpu: a
GPU without a training, or one whose training is past 15,500 iterations, with >= 8 GB free; the training of a GPU = the last row of
that GPU in the progress block, finished when its note starts with a status), runs the step there and releases the lock.

  python3 gpu_when_free.py <tag> <mode> <site> <arg> [<tag> <mode> <site> <arg> ...]
scientific_verdict: null."""
import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
OUT = (REPO.parent / "JointBuildGS-artifacts").resolve() / "phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1"
DONE = ("PASS", "FAILED", "OOM", "STOPPED")


def free_mib(g):
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", str(g)], capture_output=True, text=True, timeout=20).stdout
        return float(out.strip().splitlines()[0])
    except Exception:
        return 0.0


def training_iteration(g):
    """None when no training runs on GPU g, else its last logged iteration."""
    txt = (OUT / "progress.md").read_text()
    m = re.search(r"<!-- training -->(.*?)<!-- /training -->", txt, re.S)
    last = None
    for line in (m.group(1).splitlines() if m else []):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 6 and c[1] == str(g) and "/" in c[0]:
            last = c
    if last is None or last[5].startswith(DONE):
        return None
    return int(last[2].replace(",", "") or 0)


def pick():
    while True:
        for g in (0, 1):
            if training_iteration(g) is None and free_mib(g) >= 8000:
                return g
        for g in (0, 1):
            it = training_iteration(g)
            if it is not None and it >= 15500 and free_mib(g) >= 8000:
                return g
        time.sleep(60)


def main(args):
    steps = [args[i:i + 4] for i in range(0, len(args), 4)]
    for tag, mode, site, arg in steps:
        with open(OUT / "logs/slot0.lock", "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            g = pick()
            env = dict(os.environ, GPU=str(g), SLOT="0")
            rc = subprocess.run(["bash", str(HERE.parent / "run_gpu.sh"), tag, mode, site, arg], env=env).returncode
            fcntl.flock(lk, fcntl.LOCK_UN)
        print(tag, "gpu", g, "rc", rc, flush=True)
        if rc != 0:
            sys.exit(rc)


if __name__ == "__main__":
    main(sys.argv[1:])
