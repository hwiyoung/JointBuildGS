#!/usr/bin/env python3
"""PHD-REPO-BRANCH-SETUP-v1 3.5: fork r11 dry initialisations from the clean checkout (host orchestration only, stdlib).

  python3 run_fork_check.py --prior LoD2 --gpu 0      # the plan of configs/phd/repo_branch_setup_v1/checks_v1.json for one prior:
                                                      # every box with all switches on, then switch_box with each switch off

The docker command is run_fork.command() of PHD-MAIN-PREP-DISCARD-RULE-v1, unchanged; only where it reads and writes moves:
  /source  = the fork committed in this repository (src/phd/forks/GeoGS-conf-guided-v1-r11), read-only (was the payload's r11)
  /p       = the discard-rule payload, now read-only (inputs fork_inputs/s52 are read from it as before)
  /pv      = this task's payload; the runs go to /pv/fork_runs/<tag>/<run>/model (was /p/fork_runs/s52/<run>/model)
Nothing under the discard-rule payload is written. Outputs <V>/fork_runs/<tag>/<run>/{model/, receipt.json},
<V>/logs/fork_<tag>_<run>.log. scientific_verdict: null."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "scripts/phd/main_prep_discard_rule_v1"))
import run_fork as rf  # noqa: E402  (module of the discard-rule task; reads configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json)

C = json.loads((REPO / "configs/phd/repo_branch_setup_v1/checks_v1.json").read_text())
V = rf.ART / C["payload_relative"]
FORK = REPO / C["fork_in_repo"]


def remount(cmd, name):
    """run_fork.command() with the payload mount read-only, this task's payload at /pv and the committed fork at /source."""
    out, i, done = [], 0, set()
    while i < len(cmd):
        a = cmd[i]
        if a == "-v" and cmd[i + 1] == f"{rf.P}:/p":
            out += ["-v", f"{rf.P}:/p:ro", "-v", f"{V}:/pv"]; done.add("p"); i += 2; continue
        if a == "-v" and cmd[i + 1] == f"{rf.SRC}:/source:ro":
            out += ["-v", f"{FORK}:/source:ro"]; done.add("source"); i += 2; continue
        if a == "--name":
            out += ["--name", f"jbgs-chk-{name}".replace("_", "-").replace(".", "-").lower()[:60]]; done.add("name"); i += 2; continue
        out.append(a); i += 1
    if done != {"p", "source", "name"}:
        raise SystemExit(f"run_fork.command() changed shape; replaced only {sorted(done)}")
    return out


def run(box, prior, switch, gpu, cpus):
    tag = C["tag"]
    name = f"{box}_{prior}" + (f"_sw-{switch}" if switch else "")
    rdir = V / "fork_runs" / tag / name
    if rdir.exists():
        raise SystemExit(f"{rdir} exists; nothing is overwritten")
    rdir.mkdir(parents=True)
    cmd = remount(rf.command(name, box, prior, C["inputs"], f"/pv/fork_runs/{tag}/{name}/model", gpu, cpus, switch, "current"), name)
    log = V / "logs" / f"fork_{tag}_{name}.log"
    t0 = time.monotonic()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and (rdir / "model/monitor/init_report.json").exists()
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", rf.IMG], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id=C["task_id"], run=name, fork="r11 (committed copy)", source=str(FORK), box=box, prior=prior, switch_off=switch,
               rule="current", gpu=gpu, image=rf.IMG, image_id=image_id, command=cmd, seconds=round(time.monotonic() - t0, 1),
               exit_code=rc, status="PASS" if ok else "FAILED", scientific_verdict=None)
    (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
    print(time.strftime("%H:%M:%S"), name, rec["status"], rec["seconds"], flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prior", required=True, choices=C["priors"]); ap.add_argument("--gpu", required=True)
    ap.add_argument("--cpus", default="8")
    a = ap.parse_args()
    (V / "logs").mkdir(parents=True, exist_ok=True)
    plan = [(b, None) for b in C["boxes"]] + [(C["switch_box"], s) for s in C["switches"]]
    bad = [f"{b}_{a.prior}" + (f"_sw-{s}" if s else "") for b, s in plan if not run(b, a.prior, s, a.gpu, a.cpus)]
    print("FAILED", bad if bad else "none", flush=True)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
