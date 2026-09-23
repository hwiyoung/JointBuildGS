#!/usr/bin/env python3
"""Dry initialisations and short trainings of the fork r9, and the control run of the r8 fork (host orchestration only,
stdlib; PHD-STAGE2-R9-THREE-FIXES-v1).

  python run_r9.py --gpu 0 --dry M_N L_N             # stop before the first iteration (init report, unit table, re-read test)
  python run_r9.py --gpu 0 M_N M_N_noprior L_N        # trainings of configs/.../r9.json "training.runs"
  python run_r9.py --gpu 1 ctrl_M_N_r8                # the r8 fork and r8 inputs as they are, 3,050 iterations (fix 'ra' check)
  python run_r9.py --gpu 0 r8rep_M_N M_N_noorient      # extra runs of r9.json "training.extra_runs" (attribution)

r9 command line = the r8 launcher (run_r8.py) with the r9 inputs: the stage-1 product store, unit maps, mark maps, tau
maps, seats and prior normals of PHD-STAGE2-R9-THREE-FIXES-v1; for LoD2 the r9 scene (initial cloud without the points on
bottom faces) and the r9 prior depth (absolute --jbgs_prior_set path; the fork joins it onto maps_root, which an absolute
path replaces). The schedule is r8's (3,500 iterations, seed 0, snapshots at 2,000 and the end, dump at the end); M_N also
dumps at 3,000 / 3,001 / 3,050 (the state before and after the opacity reset at 3,000). The red / green read-out checks
are recorded but do not stop the run (--jbgs_stop_on_red 0).
The control run reuses r8's own M_N command (runs/M_N/receipt.json of PHD-STAGE2-R8-FOUR-CASES-v1) with the r8 payload
mounted read-only and only the schedule changed (3,050 iterations, dumps at 3,000 / 3,001 / 3,050, model in the r9 payload).
Outputs: <R9>/runs/<name>/{model/, receipt.json}, <R9>/logs/{dry,train}_<name>.log"""
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
R9 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R9-THREE-FIXES-v1"
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
CFG = json.loads((REPO / "configs/phd/stage2_r9_three_fixes_v1/r9.json").read_text())
IMG = "jointbuildgs:geogs-conf-guided-v1"

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gpu", default="0")
ap.add_argument("--cpus", default="8")
ap.add_argument("--dry", action="store_true", help="initialisation only (dry_init 2), settings instead of runs")
a = ap.parse_args()
TOL = json.loads((R9 / "stage1/tolerance.json").read_text())["priors"]
V = CFG["values"]
T = CFG["training"]


def control_command(name, setting="M_N", ctl=None):
    """r8's own command of a setting with the r8 payload read-only, the model in the r9 payload and the given schedule
    (the control run: M_N to 3,050; an r8 repeat: the r8 schedule)."""
    rc8 = json.loads((R8 / "runs" / setting / "receipt.json").read_text())
    cmd = list(rc8["command"])
    ctl = T["control"] if ctl is None else ctl
    its = int(ctl["iterations"])
    i = cmd.index(f"{R8}:/p8"); cmd[i] = f"{R8}:/p8:ro"; cmd[i + 1:i + 1] = ["-v", f"{R9}:/p9"]
    cmd[cmd.index("--name") + 1] = f"jbgs-r9-{name}".replace("_", "-").lower()
    cmd[cmd.index("--gpus") + 1] = f"device={a.gpu}"
    cmd[cmd.index("-m") + 1] = f"/p9/runs/{name}/model"

    def set_list(flag, values):
        k = cmd.index(flag); j = k + 1
        while j < len(cmd) and not cmd[j].startswith("--"):
            j += 1
        cmd[k + 1:j] = [str(v) for v in values]
    set_list("--iterations", [its]); set_list("--test_iterations", [2000, its]); set_list("--save_iterations", [its])
    set_list("--jbgs_snapshot_iterations", [2000, its]); set_list("--jbgs_dump_iterations", list(ctl["dumps"]))
    assert "/source:ro" in " ".join(cmd) and f"{R8}/sources/GeoGS-conf-guided-v1-r8:/source:ro" in cmd, "r8 fork"
    return cmd, its, setting, float(V["lambda_prior"])


rc_all = 0
EX = T.get("extra_runs", {})
for item in a.runs:
    control = item == T["control"]["name"] or (item in EX and EX[item].get("fork") == "r8")
    if a.dry:
        setting, lam, name = item, V["lambda_prior"], f"dry_{item}"
        its = 1
    elif control:
        name = item
    else:
        spec = T["runs"][item] if item in T["runs"] else EX[item]
        setting, lam, name = spec["setting"], spec["lambda_prior"], item
        its = int(T["iterations"])
    rdir = R9 / "runs" / name
    if (not a.dry) and (rdir / "receipt.json").exists() and json.loads((rdir / "receipt.json").read_text()).get("status") == "PASS":
        print(f"{name}: PASS receipt exists, skipped"); continue
    if rdir.exists():
        rdir.rename(R9 / "runs" / f"{name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    rdir.mkdir(parents=True)
    if control:
        cmd, its, setting, lam = control_command(name, *((EX[item]["setting"], EX[item]) if item in EX else ()))
        cond = json.loads((S2 / "runs" / CFG["settings"][setting]["condition"] / "condition.json").read_text())
        fork = "r8"
    else:
        cond_name = CFG["settings"][setting]["condition"]
        cond = json.loads((S2 / "runs" / cond_name / "condition.json").read_text())
        tv = TOL[setting[0]]
        var = "poly" if setting.startswith("M") else "lod2"
        lod2 = setting.startswith("M")
        scene = f"/p9/scenes/{setting}" if lod2 else f"/s2/runs/{cond_name}/scene"
        origin = f"/p9/scenes/{setting}/sparse/0/origin.npy" if lod2 else cond["origin_path"]
        prior_set = f"/p9/stage1/prior/{setting}" if lod2 else cond["prior_set"]
        dumps = sorted(set([its] + [d for d in T["extra_dumps"].get(item, [])])) if not a.dry else []
        sched = (["--iterations", "1", "--test_iterations", "1", "--save_iterations", "1", "--jbgs_dry_init", "2"] if a.dry else
                 ["--iterations", str(its), "--test_iterations", "2000", str(its), "--save_iterations", str(its),
                  "--jbgs_snapshot_iterations", "2000", str(its), "--jbgs_dump_iterations", *[str(d) for d in dumps]])
        cmd = ["docker", "run", "--rm", "--name", f"jbgs-r9-{name}".replace("_", "-").lower(), "--gpus", f"device={a.gpu}",
               "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", a.cpus, "--shm-size", "8g",
               "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
               "-e", f"OMP_NUM_THREADS={a.cpus}",
               "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2:ro", "-v", f"{R9}:/p9", "-v", f"{WEIGHTS}:/weights:ro",
               "-v", f"{R9}/sources/GeoGS-conf-guided-v1-r9:/source:ro", "-w", "/source", "--entrypoint", "python", IMG,
               "train.py", "-s", scene, "-m", f"/p9/runs/{name}/model", "--eval",
               "--lod_depth_path", f"/s2/runs/{cond_name}/none", "--da_depth_path", f"/s2/runs/{cond_name}/none",
               "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
               "--jbgs_judgment", cond["mode"], "--jbgs_maps_root", "/s2/inputs/maps",
               "--jbgs_faces_json", "/s2/inputs/maps/faces.json", "--jbgs_scene", cond["scene"],
               "--jbgs_origin_path", origin, "--jbgs_lambda_mvs", str(V["lambda_mvs"]), "--jbgs_lambda_prior", str(lam),
               *sched,
               "--jbgs_prior_set", prior_set, "--jbgs_tau_set", cond["tau_set"], "--jbgs_tau_v", str(tv["roof"]["tau"]),
               "--jbgs_prop_store", f"/p9/stage1/products/{setting}/store_{var}_c{V['cell_m']}.npz", "--jbgs_prop_tag", "data",
               "--jbgs_prop_majority", str(V["majority"]), "--jbgs_prop_min_evidence", str(V["min_evidence_locations"]),
               "--jbgs_prop_max_distance", str(V["max_distance_m"]), "--jbgs_seat_path", f"/p9/inputs/{setting}/seat_surface.npy",
               "--jbgs_locmap_dir", f"/p9/stage1/products/{setting}/locmap", "--jbgs_markmap_dir", f"/p9/stage1/products/{setting}/markmap",
               "--jbgs_tau_dir", f"/p9/inputs/{setting}/tau", "--jbgs_tau_roof", str(tv["roof"]["tau"]), "--jbgs_tau_wall", str(tv["wall"]["tau"]),
               *(["--jbgs_prior_normal_path", f"/p9/inputs/{setting}/prior_normal.npy"] if (EX.get(item, {}).get("orient", True)) else []),
               "--jbgs_e_interval", str(V["reread_interval"]), "--jbgs_e_threshold", str(V["e_threshold"]),
               "--jbgs_lock_lr_scale", str(V["lock_lr_scale"]), "--jbgs_lock_opacity_floor", str(V["lock_opacity_floor"]),
               "--jbgs_lock_drift_tau_mult", str(V["protection_tau_mult"]), "--jbgs_trunc_hi", str(V["truncation_tau_mult"]),
               "--jbgs_stop_on_red", "0"]
        fork = "r9"
    image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    bp = (R8 / "provenance/build_report_r8.json") if fork == "r8" else (R9 / "provenance/build_report_r9.json")
    rec = dict(task_id=CFG["task_id"], run=name, fork=fork, setting=setting, lambda_prior=lam, dry=a.dry, iterations=its, condition_json=cond,
               gpu=a.gpu, image=IMG, image_id=image_id, repo_commit=commit, command=cmd,
               started_at=dt.datetime.now(dt.timezone.utc).isoformat(), build_report=json.loads(bp.read_text()), scientific_verdict=None)
    log = R9 / "logs" / f"{'dry' if a.dry else 'train'}_{name}.log"
    t0 = time.monotonic()
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and ((rdir / "model/monitor/init_report.json").exists() if a.dry else
                      (rdir / f"model/point_cloud/iteration_{its}/point_cloud.ply").exists())
    rec.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), seconds=time.monotonic() - t0, exit_code=rc,
               status="PASS" if ok else "FAIL", log=str(log.relative_to(R9)))
    (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec[k] for k in ("run", "status", "exit_code", "seconds")}), flush=True)
    rc_all = rc_all or (0 if ok else 1)
sys.exit(rc_all)
