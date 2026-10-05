#!/usr/bin/env python3
"""Run one stage-2 condition in Docker and write a receipt (host orchestration only, stdlib).

  python run_condition.py <COND> --gpu 0 [--iterations 30000] [--tag main] [--lambda_mvs 0.05] [--lambda_prior 0.05]
                          [--extra ARG ...]
P/P0/I conditions run the patched fork (sources/GeoGS-conf-guided-v1) in jointbuildgs:geogs-conf-guided-v1.
O conditions run the pristine official GeoGS source of the roof-bias diagnostic in the official image with the
diagnostic's command line, only the scene directory (registered prior arrays) differs.
Outputs: runs/<COND>/model[_<tag>]/, logs/train_<COND>[_<tag>].log, runs/<COND>/receipt[_<tag>].json"""
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
DIAG = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"  # LPIPS AlexNet/VGG (offline)
IMG_JUDG = "jointbuildgs:geogs-conf-guided-v1"
IMG_OFF = "jointbuildgs:geogs-official-db40c95-compat-v1"
SNAP = [2000, 5000, 10000, 15000, 20000, 30000]

ap = argparse.ArgumentParser()
ap.add_argument("cond")
ap.add_argument("--gpu", default="0")
ap.add_argument("--iterations", type=int, default=30000)
ap.add_argument("--tag", default="")
ap.add_argument("--lambda_mvs", type=float, default=0.05)
ap.add_argument("--lambda_prior", type=float, default=0.05)
ap.add_argument("--cpus", default="8")
ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
a = ap.parse_args()

cond = json.loads((S2 / "runs" / a.cond / "condition.json").read_text())
suffix = f"_{a.tag}" if a.tag else ""
model = f"/s2/runs/{a.cond}/model{suffix}"
scene = f"/s2/runs/{a.cond}/scene"
log = S2 / "logs" / f"train_{a.cond}{suffix}.log"
receipt = S2 / "runs" / a.cond / f"receipt{suffix}.json"
host_model = S2 / "runs" / a.cond / f"model{suffix}"
if receipt.exists() and json.loads(receipt.read_text()).get("status") == "PASS":
    raise SystemExit(f"{a.cond}{suffix}: PASS receipt exists; move it aside to rerun")
if host_model.exists() or receipt.exists():  # interrupted or failed attempt: keep it, out of the way (monitor files append)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    dst = S2 / "runs" / a.cond / "interrupted" / f"model{suffix}_{stamp}"
    dst.mkdir(parents=True)
    for p in (host_model, receipt, log):
        if p.exists():
            p.rename(dst / p.name)
    with (S2 / "logs" / "issues.jsonl").open("a") as f:
        f.write(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(timespec="seconds"), condition=a.cond, tag=a.tag,
                                event="previous attempt moved aside before rerun", moved_to=str(dst.relative_to(S2)),
                                scientific_verdict=None)) + "\n")
name = f"jbgs-s2-{a.cond}{suffix}".replace("_", "-").replace(".", "p")
its = a.iterations
snap = [i for i in SNAP if i <= its] or [its]
if its not in snap:
    snap.append(its)
test_iters = [str(i) for i in snap]

base = ["docker", "run", "--rm", "--name", name, "--gpus", f"device={a.gpu}", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", a.cpus, "--shm-size", "8g",
        "-e", "PYTHONUNBUFFERED=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
        "-e", f"OMP_NUM_THREADS={a.cpus}",
        "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S2}:/s2", "-v", f"{WEIGHTS}:/weights:ro"]
if cond["mode"] in ("P", "P0", "I"):
    cmd = base + ["-v", f"{S2}/sources/GeoGS-conf-guided-v1:/source:ro", "-w", "/source", "--entrypoint", "python", IMG_JUDG,
                  "train.py", "-s", scene, "-m", model, "--eval",
                  "--lod_depth_path", f"/s2/runs/{a.cond}/none", "--da_depth_path", f"/s2/runs/{a.cond}/none",
                  "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
                  "--jbgs_judgment", cond["mode"], "--jbgs_maps_root", "/s2/inputs/maps",
                  "--jbgs_faces_json", "/s2/inputs/maps/faces.json", "--jbgs_scene", cond["scene"],
                  "--jbgs_origin_path", cond["origin_path"],
                  "--jbgs_lambda_mvs", str(a.lambda_mvs), "--jbgs_lambda_prior", str(a.lambda_prior),
                  "--iterations", str(its), "--test_iterations", *test_iters, "--save_iterations", "8000", str(its),
                  "--jbgs_capture_iterations", str(its), "--jbgs_snapshot_iterations", *test_iters,
                  "--jbgs_dump_iterations", *[str(i) for i in sorted({min(15000, its), its})]]
    if cond["mode"] in ("P", "P0"):
        cmd += ["--jbgs_prior_set", cond["prior_set"], "--jbgs_tau_set", cond["tau_set"], "--jbgs_tau_v", str(cond["tau_v"])]
    image = IMG_JUDG
else:
    cmd = base + ["-v", f"{DIAG}/sources/GeoGS:/source:ro", "-w", "/source", "--entrypoint", "python", IMG_OFF,
                  "train.py", "-s", scene, "-m", model,
                  "--lod_depth_path", f"{scene}/lod2_prior", "--da_depth_path", f"{scene}/da3_prior",
                  "--lod2_pcd_path", f"{scene}/lod2_pcd.ply", "--eval", "--lod_init", "--freeze_onlybldg", "--protect_bldg",
                  "--dynamic_depth_weight", "--iterations", str(its), "--test_iterations", *test_iters,
                  "--save_iterations", "8000", str(its)]
    image = IMG_OFF
cmd += a.extra

image_id = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True).stdout.strip()
commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
rec = dict(condition=a.cond, tag=a.tag, mode=cond["mode"], gpu=a.gpu, iterations=its, image=image, image_id=image_id,
           repo_commit=commit, command=cmd, started_at=dt.datetime.now(dt.timezone.utc).isoformat(), condition_json=cond,
           lambda_mvs=a.lambda_mvs, lambda_prior=a.lambda_prior, source_hashes="provenance/patched_source_sha256.txt",
           scientific_verdict=None)
log.parent.mkdir(parents=True, exist_ok=True)
t0 = time.monotonic()
with log.open("w") as f:
    f.write(" ".join(cmd) + "\n\n"); f.flush()
    rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
rec.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), seconds=time.monotonic() - t0, exit_code=rc,
           status="PASS" if rc == 0 else "FAIL", log=str(log.relative_to(S2)))
receipt.write_text(json.dumps(rec, indent=1))
print(json.dumps({k: rec[k] for k in ("condition", "tag", "status", "exit_code", "seconds")}))
sys.exit(rc)
