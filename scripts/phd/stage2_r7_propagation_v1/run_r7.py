#!/usr/bin/env python3
"""Dry runs of the fork r7 (no training; host orchestration only, stdlib; PHD-STAGE2-R7-PROPAGATION-v1).

  python run_r7.py --gpu 0 M_N:spec M_N:spec_plant M_N:data ...

Each run starts train.py of the r7 fork on the stage-2 scene of the setting with the r7 inputs and --jbgs_dry_init:
the Judgment plants, computes the first E, writes monitor/init_report.json (+ init_points.npz, unplanted.npz) and exits
before the first iteration. Variants: spec = tolerance with the agency spec lower bound (the order), conflict points not
planted, prior-term gate 'propagated', plus the re-read test (dry_init 2); spec_plant = the same with the conflict points
planted (baseline); spec_loc = gate 'location'; data = tolerance of the data width only.
Outputs: <R7>/runs/<setting>_<variant>/{model/monitor/, receipt.json}, <R7>/logs/dry_<setting>_<variant>.log"""
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
R7 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R7-PROPAGATION-v1"
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
CFG = json.loads((REPO / "configs/phd/stage2_r7_propagation_v1/r7.json").read_text())
IMG = "jointbuildgs:geogs-conf-guided-v1"
VARIANTS = {"spec": dict(tau="spec", plant=0, gate="propagated", dry=2), "spec_plant": dict(tau="spec", plant=1, gate="propagated", dry=1),
            "spec_loc": dict(tau="spec", plant=0, gate="location", dry=1), "data": dict(tau="data", plant=0, gate="propagated", dry=1)}

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+", help="<setting>:<variant>")
ap.add_argument("--gpu", default="0")
ap.add_argument("--cpus", default="8")
a = ap.parse_args()
TOL = json.loads((R7 / "stage1/tolerance.json").read_text())["priors"]
V = CFG["values"]
rc_all = 0
for item in a.runs:
    setting, var = item.split(":")
    vs = VARIANTS[var]
    cond_name = CFG["settings"][setting]["condition"]
    cond = json.loads((S2 / "runs" / cond_name / "condition.json").read_text())
    tv = TOL[setting[0]][vs["tau"]]
    name = f"{setting}_{var}"
    rdir = R7 / "runs" / name
    if rdir.exists():
        rdir.rename(R7 / "runs" / f"{name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    rdir.mkdir(parents=True)
    store = f"/r7/stage1/products/{setting}/store_{'poly' if setting.startswith('M') else 'lod2'}_c{V['cell_m']}.npz"
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-r7-dry-{name}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", a.cpus, "--shm-size", "8g",
           "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
           "-e", f"OMP_NUM_THREADS={a.cpus}",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R7}:/r7", "-v", f"{WEIGHTS}:/weights:ro",
           "-v", f"{R7}/sources/GeoGS-conf-guided-v1-r7:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
           "train.py", "-s", f"/s2/runs/{cond_name}/scene", "-m", f"/r7/runs/{name}/model", "--eval",
           "--lod_depth_path", f"/s2/runs/{cond_name}/none", "--da_depth_path", f"/s2/runs/{cond_name}/none",
           "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
           "--jbgs_judgment", cond["mode"], "--jbgs_maps_root", "/s2/inputs/maps",
           "--jbgs_faces_json", "/s2/inputs/maps/faces.json", "--jbgs_scene", cond["scene"],
           "--jbgs_origin_path", cond["origin_path"], "--jbgs_lambda_mvs", "0.05", "--jbgs_lambda_prior", "0.05",
           "--iterations", "1", "--test_iterations", "1", "--save_iterations", "1",
           "--jbgs_prior_set", cond["prior_set"], "--jbgs_tau_set", cond["tau_set"], "--jbgs_tau_v", str(tv["roof"]["tau"]),
           "--jbgs_prop_store", store, "--jbgs_prop_tau_variant", vs["tau"],
           "--jbgs_prop_majority", str(V["majority"]), "--jbgs_prop_min_evidence", str(V["min_evidence_locations"]),
           "--jbgs_prop_max_distance", str(V["max_distance_m"]), "--jbgs_seat_path", f"/r7/inputs/{setting}/seat_surface.npy",
           "--jbgs_locmap_dir", f"/r7/stage1/products/{setting}/locmap", "--jbgs_tau_dir", f"/r7/inputs/{setting}/tau_{vs['tau']}",
           "--jbgs_tau_roof", str(tv["roof"]["tau"]), "--jbgs_tau_wall", str(tv["wall"]["tau"]),
           "--jbgs_init_plant_conflict", str(vs["plant"]), "--jbgs_prior_gate", vs["gate"], "--jbgs_dry_init", str(vs["dry"])]
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id=CFG["task_id"], run=name, setting=setting, variant=var, spec=vs, condition_json=cond, gpu=a.gpu, image=IMG,
               image_id=image_id, repo_commit=commit, command=cmd, started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               build_report=json.loads((R7 / "provenance/build_report_r7.json").read_text()), scientific_verdict=None)
    log = R7 / "logs" / f"dry_{name}.log"
    t0 = time.monotonic()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and (rdir / "model/monitor/init_report.json").exists()
    rec.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), seconds=time.monotonic() - t0, exit_code=rc,
               status="PASS" if ok else "FAIL", log=str(log.relative_to(R7)))
    (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec[k] for k in ("run", "status", "exit_code", "seconds")}), flush=True)
    rc_all = rc_all or (0 if ok else 1)
sys.exit(rc_all)
