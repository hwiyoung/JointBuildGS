#!/usr/bin/env python3
"""Dry initialisations and short trainings of the fork r8 (host orchestration only, stdlib; PHD-STAGE2-R8-FOUR-CASES-v1).

  python run_r8.py --gpu 0 --dry M_N L_N             # stop before the first iteration (init report, unit table, re-read test)
  python run_r8.py --gpu 0 M_N M_N_noprior L_N        # trainings of configs/.../r8.json "training.runs"

Command line = the r6 / r7 launchers (run_condition.py of a P condition) with the r8 inputs: the stage-1 product store
(states / votes of the one tolerance), unit maps, mark maps, tau maps and seats of PHD-STAGE2-R8-FOUR-CASES-v1. The
schedule is the last training experiment's (r6: 3,500 iterations, seed 0, snapshots at 2,000 and the end, dump at the
end). The red / green read-out checks are recorded but do not stop the run (--jbgs_stop_on_red 0), so that every run
reaches the end of the schedule.
Outputs: <R8>/runs/<name>/{model/, receipt.json}, <R8>/logs/{dry,train}_<name>.log"""
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
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
CFG = json.loads((REPO / "configs/phd/stage2_r8_four_cases_v1/r8.json").read_text())
IMG = "jointbuildgs:geogs-conf-guided-v1"

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gpu", default="0")
ap.add_argument("--cpus", default="8")
ap.add_argument("--dry", action="store_true", help="initialisation only (dry_init 2), settings instead of runs")
a = ap.parse_args()
TOL = json.loads((R8 / "stage1/tolerance.json").read_text())["priors"]
V = CFG["values"]
rc_all = 0
for item in a.runs:
    if a.dry:
        setting, lam, name = item, V["lambda_prior"], f"dry_{item}"
        its = 1
    else:
        spec = CFG["training"]["runs"][item]
        setting, lam, name = spec["setting"], spec["lambda_prior"], item
        its = int(CFG["training"]["iterations"])
    cond_name = CFG["settings"][setting]["condition"]
    cond = json.loads((S2 / "runs" / cond_name / "condition.json").read_text())
    tv = TOL[setting[0]]
    rdir = R8 / "runs" / name
    if (not a.dry) and (rdir / "receipt.json").exists() and json.loads((rdir / "receipt.json").read_text()).get("status") == "PASS":
        print(f"{name}: PASS receipt exists, skipped"); continue
    if rdir.exists():
        rdir.rename(R8 / "runs" / f"{name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    rdir.mkdir(parents=True)
    var = "poly" if setting.startswith("M") else "lod2"
    sched = (["--iterations", "1", "--test_iterations", "1", "--save_iterations", "1", "--jbgs_dry_init", "2"] if a.dry else
             ["--iterations", str(its), "--test_iterations", "2000", str(its), "--save_iterations", str(its),
              "--jbgs_snapshot_iterations", "2000", str(its), "--jbgs_dump_iterations", str(its)])
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-r8-{name}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", a.cpus, "--shm-size", "8g",
           "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
           "-e", f"OMP_NUM_THREADS={a.cpus}",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R8}:/p8", "-v", f"{WEIGHTS}:/weights:ro",
           "-v", f"{R8}/sources/GeoGS-conf-guided-v1-r8:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
           "train.py", "-s", f"/s2/runs/{cond_name}/scene", "-m", f"/p8/runs/{name}/model", "--eval",
           "--lod_depth_path", f"/s2/runs/{cond_name}/none", "--da_depth_path", f"/s2/runs/{cond_name}/none",
           "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
           "--jbgs_judgment", cond["mode"], "--jbgs_maps_root", "/s2/inputs/maps",
           "--jbgs_faces_json", "/s2/inputs/maps/faces.json", "--jbgs_scene", cond["scene"],
           "--jbgs_origin_path", cond["origin_path"], "--jbgs_lambda_mvs", str(V["lambda_mvs"]), "--jbgs_lambda_prior", str(lam),
           *sched,
           "--jbgs_prior_set", cond["prior_set"], "--jbgs_tau_set", cond["tau_set"], "--jbgs_tau_v", str(tv["roof"]["tau"]),
           "--jbgs_prop_store", f"/p8/stage1/products/{setting}/store_{var}_c{V['cell_m']}.npz", "--jbgs_prop_tag", "data",
           "--jbgs_prop_majority", str(V["majority"]), "--jbgs_prop_min_evidence", str(V["min_evidence_locations"]),
           "--jbgs_prop_max_distance", str(V["max_distance_m"]), "--jbgs_seat_path", f"/p8/inputs/{setting}/seat_surface.npy",
           "--jbgs_locmap_dir", f"/p8/stage1/products/{setting}/locmap", "--jbgs_markmap_dir", f"/p8/stage1/products/{setting}/markmap",
           "--jbgs_tau_dir", f"/p8/inputs/{setting}/tau", "--jbgs_tau_roof", str(tv["roof"]["tau"]), "--jbgs_tau_wall", str(tv["wall"]["tau"]),
           "--jbgs_e_interval", str(V["reread_interval"]), "--jbgs_e_threshold", str(V["e_threshold"]),
           "--jbgs_lock_lr_scale", str(V["lock_lr_scale"]), "--jbgs_lock_opacity_floor", str(V["lock_opacity_floor"]),
           "--jbgs_lock_drift_tau_mult", str(V["protection_tau_mult"]), "--jbgs_trunc_hi", str(V["truncation_tau_mult"]),
           "--jbgs_stop_on_red", "0"]
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id=CFG["task_id"], run=name, setting=setting, lambda_prior=lam, dry=a.dry, iterations=its, condition_json=cond,
               gpu=a.gpu, image=IMG, image_id=image_id, repo_commit=commit, command=cmd,
               started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               build_report=json.loads((R8 / "provenance/build_report_r8.json").read_text()), scientific_verdict=None)
    log = R8 / "logs" / f"{'dry' if a.dry else 'train'}_{name}.log"
    t0 = time.monotonic()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and ((rdir / "model/monitor/init_report.json").exists() if a.dry else
                      (rdir / f"model/point_cloud/iteration_{its}/point_cloud.ply").exists())
    rec.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), seconds=time.monotonic() - t0, exit_code=rc,
               status="PASS" if ok else "FAIL", log=str(log.relative_to(R8)))
    (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec[k] for k in ("run", "status", "exit_code", "seconds")}), flush=True)
    rc_all = rc_all or (0 if ok else 1)
sys.exit(rc_all)
