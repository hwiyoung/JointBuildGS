#!/usr/bin/env python3
"""PHD-MAIN-FIXTEST-v1 6.4 GPU checks (host orchestration, stdlib), two GPUs, one job per GPU = stage 3's checks_s3.py with this task's
variants (all with stage 3's records of every r15 training: --data_device cpu, memory record, out-of-memory record):
  r15     fork r15 default (the reference)
  r16d    fork r16, both switches at their default 0          -> must equal r15 (dry and probe)
  r16B    fork r16, --jbgs_sw_own_depth_release 1             (판 B)
  r16A    fork r16, --jbgs_sw_prior_share_band 1 + w maps    (판 A; needs prep/wmaps)
  r16AB   both                                                 (함께 켠 판; B173 주변 항공 LiDAR, R1 항공 LiDAR)
  dry    the dry initialisation (--jbgs_dry_init 2: no training) at the six stage-1 units
  probe  one re-read + one render-and-gradient pass at the fixed 15,000 state of each stage-1 unit (seed 0; B173 주변: stage 0's b1),
         probe_ckpt_ft.py
  python3 checks_ft.py dry|probe|all [--var r15 r16d ...] [--only <tag-prefix> ...] [--gpus 0 1]
Outputs FT/checks/<kind>/<tag>/{model/, probe/, nvsmi.jsonl, receipt.json}, logs/check_<tag>.log, logs/queue.log. scientific_verdict: null."""
import argparse
import datetime as dt
import json
import queue
import subprocess
import threading
import time

import ft_plan as P

FT = P.FT
VARIANTS = {"r15": ("r15", ""), "r16d": ("r16", ""), "r16B": ("r16", "B"), "r16A": ("r16", "A"), "r16AT": ("r16", "AT"), "r16AB": ("r16", "AB"),
            "r16dNF": ("r16", ""), "r16BNF": ("r16", "B")}      # NF: probe without the opacity floor of the re-read (check only)
AB_UNITS = [("B173nb_b10", "ALS"), ("R1rep_b10", "ALS")]
UNITS_OF = {}          # --units restricts the fix-A variants to the cases a reading trains (set in main)


def J(tag, kind, var, site, prior, ckpt=None):
    fork, fix = VARIANTS[var]
    return dict(tag=tag, kind=kind, var=var, fork=fork, fix=fix, site=site, prior=prior, seed=0, ckpt=ckpt)


def jobs_of(what, variants):
    out = []
    for kind in (("dry", "probe") if what == "all" else (what,)):
        for v in variants:
            units = UNITS_OF.get(v) or (AB_UNITS if v == "r16AB" else P.UNITS6)
            for s, p in units:
                if kind == "dry":
                    out.append(J(f"{v}_{s}_{p}", "dry", v, s, p))
                else:
                    out.append(J(f"{v}_{s}_{p}_s0", "probe", v, s, p, P.ckpt_of(s, p, 0)))
    return out


def command(job, gpu):
    d = FT / "checks" / job["kind"] / job["tag"]
    model = f"/o/checks/{job['kind']}/{job['tag']}/model"
    name = f"jbgs-ftc-{job['tag']}".replace("_", "-").replace(".", "-").lower()[:60]
    if job["kind"] == "dry":
        entry = ["train.py", *P.train_args(job["site"], job["prior"], model, job["fix"], schedule=P.SP.SCHEDULE_DRY), *P.RECORDS]
    else:
        ply, ref = job["ckpt"]
        args = P.train_args(job["site"], job["prior"], model, job["fix"], schedule=P.SP.SCHEDULE_PROBE)
        entry = ["/repo/scripts/phd/main_fixtest_v1/probe_ckpt_ft.py", "--probe_out", f"/o/checks/probe/{job['tag']}/probe", "--probe_ply", P.to_container(ply),
                 "--probe_ref_init", P.to_container(ref), "--probe_iteration", "15000", *(["--probe_no_floor", "1"] if job["var"].endswith("NF") else []),
                 "--", *args, *P.RECORDS]
    return d, P.docker(name, gpu, job["fork"], job["site"], entry)


def nvsmi(gpu):
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", str(gpu)], capture_output=True, text=True, timeout=20).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return -1


def run_job(job, gpu):
    d, cmd = command(job, gpu)
    if d.exists():
        d.rename(d.parent / f"{d.name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    d.mkdir(parents=True)
    (FT / "logs").mkdir(parents=True, exist_ok=True)
    log = FT / "logs" / f"check_{job['tag']}.log"
    idle = nvsmi(gpu)
    t0 = time.monotonic()
    samples = []
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n\n"); f.flush()
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        while p.poll() is None:
            samples.append(dict(t=round(time.monotonic() - t0, 1), mib=nvsmi(gpu)))
            time.sleep(2)
        rc = p.returncode
    (d / "nvsmi.jsonl").write_text("\n".join(json.dumps(s) for s in samples) + "\n")
    out = {"dry": d / "model/monitor/init_report.json", "probe": d / "probe/probe.json"}[job["kind"]]
    ok = rc == 0 and out.exists()
    peak = max([s["mib"] for s in samples] or [idle])
    rec = dict(task_id="PHD-MAIN-FIXTEST-v1", check={k: (list(map(str, v)) if k == "ckpt" and v else v) for k, v in job.items()}, gpu=gpu, image=P.IMG,
               command=cmd, seconds=round(time.monotonic() - t0, 1), exit_code=rc, status="PASS" if ok else "FAILED",
               gpu_memory_used_mib=dict(idle_before=idle, peak=peak, peak_minus_idle=peak - idle), scientific_verdict=None)
    (d / "receipt.json").write_text(json.dumps(rec, indent=1))
    with (FT / "logs/queue.log").open("a") as q:
        q.write(f"{time.strftime('%m-%d %H:%M:%S')} check_{job['tag']} rc={0 if ok else 1} {int(time.monotonic() - t0)}s gpu{gpu}\n")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["dry", "probe", "all"])
    ap.add_argument("--var", nargs="+", default=["r15", "r16d", "r16B"])
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--gpus", nargs="+", default=["0", "1"])
    ap.add_argument("--units", nargs="*", default=None, help="variant=site/prior,... e.g. r16A=B0_b10/ALS,R1rep_b10/ALS")
    a = ap.parse_args()
    for spec in a.units or []:
        v, lst = spec.split("=", 1)
        UNITS_OF[v] = [tuple(x.split("/")) for x in lst.split(",") if x]
    jobs = jobs_of(a.what, a.var)
    if a.only:
        jobs = [j for j in jobs if any(j["tag"].startswith(o) for o in a.only)]
    q = queue.Queue()
    for j in jobs:
        q.put(j)
    res = {}

    def worker(g):
        while True:
            try:
                j = q.get_nowait()
            except queue.Empty:
                return
            res[j["tag"]] = run_job(j, g)

    ts = [threading.Thread(target=worker, args=(g,)) for g in a.gpus]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    print(json.dumps(res, indent=1))
    with (FT / "logs/queue.log").open("a") as q:
        q.write(f"{time.strftime('%m-%d %H:%M:%S')} checks_{a.what} {' '.join(a.var)} done {sum(res.values())}/{len(res)}\n")


if __name__ == "__main__":
    main()
