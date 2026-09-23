#!/usr/bin/env python3
"""Dry initialisations, short trainings and the reset probes of the fork r10 (host orchestration only, stdlib;
PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1).

  python run_r10.py --gpu 0 --dry M_N L_N L_N_cell      # stop before the first iteration (init report, re-read test)
  python run_r10.py --gpu 0 M_N M_N_nodepth             # trainings of configs/.../r10.json "training.runs"
  python run_r10.py --gpu 0 --probe M_N L_N_vertex      # offline re-read of the two reset states of a training (dry_init 3)

r10 command line = the r9 launcher (run_r9.py) with
  LoD2       the r10 scene (initial cloud without the points on cut parts of party walls), prior depth, product, tau maps,
             seats and prior normals of PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1
  airborne LiDAR   r9's product, tau maps, seats and prior normals (nothing of them changes in r10); --jbgs_prior_normal_mode
             file (vertex method, r9) or cell
  schedule   r9's (3,500 iterations, seed 0, snapshots at 2,000 and the end, dump at the end); M_N and L_N_vertex also dump at
             3,000 / 3,001 / 3,050 and save the states right before and after the opacity reset at 3,000
A dry run 'L_N_cell' / 'L_B_cell' initialises the setting with the cell method. A probe reuses the training's command with
--jbgs_dry_init 3 and --jbgs_reset_probe_dir (model in runs/probe_<run>). Red / green read-out checks do not stop a run.
Outputs: <R10>/runs/<name>/{model/, receipt.json}, <R10>/logs/{dry,train,probe}_<name>.log"""
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
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
CFG = json.loads((REPO / "configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())
IMG = "jointbuildgs:geogs-conf-guided-v1"

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gpu", default="0")
ap.add_argument("--cpus", default="8")
ap.add_argument("--dry", action="store_true", help="initialisation only (dry_init 2); names = settings (+ '_cell')")
ap.add_argument("--probe", action="store_true", help="offline re-read of the reset states of these trainings (dry_init 3)")
a = ap.parse_args()
TOL = json.loads((R10 / "stage1/tolerance.json").read_text())["priors"]
V = CFG["values"]
T = CFG["training"]


def command(name, setting, lam, mode, sched, model_dir):
    cond_name = CFG["settings"][setting]["condition"]
    cond = json.loads((S2 / "runs" / cond_name / "condition.json").read_text())
    tv = TOL[setting[0]]
    lod2 = setting.startswith("M")
    var = "poly" if lod2 else "lod2"
    root = "/p10" if lod2 else "/p9"          # airborne LiDAR: r9's stage-1 product and inputs
    scene = f"/p10/scenes/{setting}" if lod2 else f"/s2/runs/{cond_name}/scene"
    origin = f"/p10/scenes/{setting}/sparse/0/origin.npy" if lod2 else cond["origin_path"]
    prior_set = f"/p10/stage1/prior/{setting}" if lod2 else cond["prior_set"]
    cmd = ["docker", "run", "--rm", "--name", f"jbgs-r10-{name}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
           "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", a.cpus, "--shm-size", "8g",
           "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
           "-e", f"OMP_NUM_THREADS={a.cpus}",
           "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R9}:/p9:ro", "-v", f"{R10}:/p10", "-v", f"{WEIGHTS}:/weights:ro",
           "-v", f"{R10}/sources/GeoGS-conf-guided-v1-r10:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
           "train.py", "-s", scene, "-m", model_dir, "--eval",
           "--lod_depth_path", f"/s2/runs/{cond_name}/none", "--da_depth_path", f"/s2/runs/{cond_name}/none",
           "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
           "--jbgs_judgment", cond["mode"], "--jbgs_maps_root", "/s2/inputs/maps",
           "--jbgs_faces_json", "/s2/inputs/maps/faces.json", "--jbgs_scene", cond["scene"],
           "--jbgs_origin_path", origin, "--jbgs_lambda_mvs", str(V["lambda_mvs"]), "--jbgs_lambda_prior", str(lam),
           *sched,
           "--jbgs_prior_set", prior_set, "--jbgs_tau_set", cond["tau_set"], "--jbgs_tau_v", str(tv["roof"]["tau"]),
           "--jbgs_prop_store", f"{root}/stage1/products/{setting}/store_{var}_c{V['cell_m']}.npz", "--jbgs_prop_tag", "data",
           "--jbgs_prop_majority", str(V["majority"]), "--jbgs_prop_min_evidence", str(V["min_evidence_locations"]),
           "--jbgs_prop_max_distance", str(V["max_distance_m"]), "--jbgs_seat_path", f"{root}/inputs/{setting}/seat_surface.npy",
           "--jbgs_locmap_dir", f"{root}/stage1/products/{setting}/locmap", "--jbgs_markmap_dir", f"{root}/stage1/products/{setting}/markmap",
           "--jbgs_tau_dir", f"{root}/inputs/{setting}/tau", "--jbgs_tau_roof", str(tv["roof"]["tau"]), "--jbgs_tau_wall", str(tv["wall"]["tau"]),
           "--jbgs_prior_normal_path", f"{root}/inputs/{setting}/prior_normal.npy", "--jbgs_prior_normal_mode", mode,
           "--jbgs_e_interval", str(V["reread_interval"]), "--jbgs_e_threshold", str(V["e_threshold"]),
           "--jbgs_lock_lr_scale", str(V["lock_lr_scale"]), "--jbgs_lock_opacity_floor", str(V["lock_opacity_floor"]),
           "--jbgs_lock_drift_tau_mult", str(V["protection_tau_mult"]), "--jbgs_trunc_hi", str(V["truncation_tau_mult"]),
           "--jbgs_stop_on_red", "0"]
    return cmd, cond


rc_all = 0
for item in a.runs:
    if a.dry:
        setting = item.replace("_cell", ""); mode = "cell" if item.endswith("_cell") else "file"
        lam, name, its = V["lambda_prior"], f"dry_{item}", 1
        sched = ["--iterations", "1", "--test_iterations", "1", "--save_iterations", "1", "--jbgs_dry_init", "2"]
        model_dir = f"/p10/runs/{name}/model"
    else:
        spec = T["runs"][item]
        setting, lam, mode = spec["setting"], spec["lambda_prior"], spec["normal_mode"]
        if a.probe:
            name, its = f"probe_{item}", 1
            sched = ["--iterations", "1", "--test_iterations", "1", "--save_iterations", "1", "--jbgs_dry_init", "3",
                     "--jbgs_reset_probe_dir", f"/p10/runs/{item}/model/dump/reset_states"]
        else:
            name, its = item, int(T["iterations"])
            dumps = sorted(set([its] + list(T["extra_dumps"].get(item, []))))
            sched = ["--iterations", str(its), "--test_iterations", "2000", str(its), "--save_iterations", str(its),
                     "--jbgs_snapshot_iterations", "2000", str(its), "--jbgs_dump_iterations", *[str(d) for d in dumps]]
            if item in T["reset_dumps"]:
                sched += ["--jbgs_reset_dump_iterations", *[str(d) for d in T["reset_dumps"][item]]]
        model_dir = f"/p10/runs/{name}/model"
    rdir = R10 / "runs" / name
    if (not a.dry and not a.probe) and (rdir / "receipt.json").exists() and json.loads((rdir / "receipt.json").read_text()).get("status") == "PASS":
        print(f"{name}: PASS receipt exists, skipped"); continue
    if rdir.exists():
        rdir.rename(R10 / "runs" / f"{name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    rdir.mkdir(parents=True)
    cmd, cond = command(name, setting, lam, mode, sched, model_dir)
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id=CFG["task_id"], run=name, fork="r10", setting=setting, lambda_prior=lam, normal_mode=mode, dry=a.dry, probe=a.probe,
               iterations=its, condition_json=cond, gpu=a.gpu, image=IMG, image_id=image_id, repo_commit=commit, command=cmd,
               started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               build_report=json.loads((R10 / "provenance/build_report_r10.json").read_text()), scientific_verdict=None)
    kind = "dry" if a.dry else ("probe" if a.probe else "train")
    log = R10 / "logs" / f"{kind}_{name}.log"
    t0 = time.monotonic()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and ((rdir / "model/monitor/init_report.json").exists() if a.dry else
                      (rdir / "model/monitor/reset_probe.json").exists() if a.probe else
                      (rdir / f"model/point_cloud/iteration_{its}/point_cloud.ply").exists())
    rec.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), seconds=time.monotonic() - t0, exit_code=rc,
               status="PASS" if ok else "FAIL", log=str(log.relative_to(R10)))
    (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec[k] for k in ("run", "status", "exit_code", "seconds")}), flush=True)
    rc_all = rc_all or (0 if ok else 1)
sys.exit(rc_all)
