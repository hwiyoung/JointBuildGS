#!/usr/bin/env python3
"""Dry initialisations of fork r11 on the case boxes (host orchestration only, stdlib; PHD-MAIN-PREP-DISCARD-RULE-v1 5.1).

  python3 run_fork.py --gpu 0 --inputs fork_inputs/s52 --tag s52 B0_b10:LoD2 B0_b10:ALS [--switch <name>] [--rule <name>]

A run stops before the first iteration (--iterations 1 --jbgs_dry_init 2): monitor/{meta.json, locations.npz, unplanted.npz,
init_points.npz, init_report.json, gate_check.npz}. --switch <name> sets --jbgs_sw_<name> 0 (all other switches on); --rule
selects a discard rule. Values = configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json 'values' (the r10 trainings').
Outputs <P>/fork_runs/<tag>/<box>_<prior>[_sw-<name>][_rule-<rule>]/{model/, receipt.json}, logs/fork_<tag>_<name>.log."""
import argparse
import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
ART = (REPO.parent / "JointBuildGS-artifacts").resolve()
P = ART / "phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
SRC = P / "sources/GeoGS-conf-guided-v1-r11"
IMG = "jointbuildgs:geogs-conf-guided-v1"
V = json.loads((REPO / "configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())["values"]
SWITCHES = ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior")


def command(name, box, prior, inputs, model_dir, gpu, cpus, switch, rule):
    I = f"/p/{inputs}/{box}"
    fi = json.loads((P / inputs / box / "fork_inputs.json").read_text())[prior]
    split = json.loads((P / inputs / box / "split.json").read_text())
    sw = [x for n in SWITCHES for x in (f"--jbgs_sw_{n}", "0" if n == switch else "1")]
    return ["docker", "run", "--rm", "--name", f"jbgs-r11-{name}".replace("_", "-").replace(".", "-").lower()[:60], "--gpus", f"device={gpu}",
            "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", str(cpus), "--shm-size", "8g",
            "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
            "-e", f"OMP_NUM_THREADS={cpus}", "-e", f"JBGS_SPLIT_JSON={I}/split.json",
            "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{P}:/p", "-v", f"{WEIGHTS}:/weights:ro", "-v", f"{SRC}:/source:ro",
            "-w", "/source", "--entrypoint", "python", IMG,
            "train.py", "-s", f"{I}/scene_{prior}", "-m", model_dir, "--eval", "-r", "1",
            "--lod_depth_path", "/p/fork_none", "--da_depth_path", "/p/fork_none",
            "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
            "--jbgs_judgment", "P", "--jbgs_maps_root", f"{I}/maps", "--jbgs_scene", "N",
            "--jbgs_origin_path", f"{I}/scene_{prior}/sparse/0/origin.npy", "--jbgs_lambda_mvs", str(V["lambda_mvs"]),
            "--jbgs_lambda_prior", str(V["lambda_prior"]),
            "--iterations", "1", "--test_iterations", "1", "--save_iterations", "1", "--jbgs_dry_init", "2",
            "--jbgs_prior_set", f"prior_{prior}", "--jbgs_tau_set", f"tau_{prior}", "--jbgs_tau_v", str(fi["tau_roof"]),
            "--jbgs_prop_store", f"{I}/store_{prior}.npz", "--jbgs_prop_tag", "data",
            "--jbgs_prop_majority", str(V["majority"]), "--jbgs_prop_min_evidence", str(V["min_evidence_locations"]),
            "--jbgs_prop_max_distance", str(V["max_distance_m"]), "--jbgs_seat_path", f"{I}/seat_{prior}.npy",
            "--jbgs_locmap_dir", f"{I}/maps/locmap_{prior}", "--jbgs_markmap_dir", f"{I}/maps/markmap_{prior}",
            "--jbgs_markcode_dir", f"{I}/maps/markcode_{prior}", "--jbgs_prop_pairs", f"{I}/pairs_{prior}.npz", "--jbgs_prop_knn", f"{I}/knn_{prior}.npz",
            "--jbgs_tau_dir", f"{I}/maps/tau_{prior}", "--jbgs_tau_roof", str(fi["tau_roof"]), "--jbgs_tau_wall", str(fi["tau_wall"]),
            "--jbgs_prior_normal_path", f"{I}/prior_normal_{prior}.npy", "--jbgs_prior_normal_mode", "cell",
            "--jbgs_e_interval", str(V["reread_interval"]), "--jbgs_e_threshold", str(V["e_threshold"]),
            "--jbgs_lock_lr_scale", str(V["lock_lr_scale"]), "--jbgs_lock_opacity_floor", str(V["lock_opacity_floor"]),
            "--jbgs_lock_drift_tau_mult", str(V["protection_tau_mult"]), "--jbgs_trunc_hi", str(V["truncation_tau_mult"]),
            "--jbgs_monitor_views", *split["train"][:2], "--jbgs_stop_on_red", "0", "--jbgs_rule", rule, *sw]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("items", nargs="+", help="box:prior")
    ap.add_argument("--gpu", default="0"); ap.add_argument("--cpus", default="8"); ap.add_argument("--inputs", required=True)
    ap.add_argument("--tag", required=True); ap.add_argument("--switch", default=None, choices=SWITCHES); ap.add_argument("--rule", default="current")
    a = ap.parse_args()
    (P / "fork_none").mkdir(exist_ok=True)
    rc_all = 0
    for it in a.items:
        box, prior = it.split(":")
        name = f"{box}_{prior}" + (f"_sw-{a.switch}" if a.switch else "") + (f"_rule-{a.rule}" if a.rule != "current" else "")
        rdir = P / "fork_runs" / a.tag / name
        if rdir.exists():
            rdir.rename(rdir.parent / f"{name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
        rdir.mkdir(parents=True)
        model_dir = f"/p/fork_runs/{a.tag}/{name}/model"
        cmd = command(name, box, prior, a.inputs, model_dir, a.gpu, a.cpus, a.switch, a.rule)
        log = P / "logs" / f"fork_{a.tag}_{name}.log"
        t0 = time.monotonic()
        with log.open("w") as f:
            f.write(" ".join(cmd) + "\n\n"); f.flush()
            rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
        ok = rc == 0 and (rdir / "model/monitor/init_report.json").exists()
        image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip()
        rec = dict(task_id="PHD-MAIN-PREP-DISCARD-RULE-v1", run=name, fork="r11", box=box, prior=prior, switch_off=a.switch, rule=a.rule, gpu=a.gpu,
                   image=IMG, image_id=image_id, command=cmd, seconds=round(time.monotonic() - t0, 1), exit_code=rc,
                   status="PASS" if ok else "FAILED", scientific_verdict=None)
        (rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
        with (P / "logs/queue.log").open("a") as q:
            q.write(f"{time.strftime('%H:%M:%S')} fork_{a.tag}_{name} rc={0 if ok else 1} {int(time.monotonic() - t0)}s\n")
        print(name, rec["status"], rec["seconds"], flush=True)
        rc_all |= 0 if ok else 1
    raise SystemExit(rc_all)


if __name__ == "__main__":
    main()
