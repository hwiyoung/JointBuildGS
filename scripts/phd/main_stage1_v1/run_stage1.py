#!/usr/bin/env python3
"""PHD-MAIN-STAGE1-v1 trainings of fork r12 with the stage-0 watcher (host orchestration only, stdlib; plan = configs main_stage1_v1
train_plan_v1.json). Two GPU workers take the runs of the plan in order (GeoGS runs are skipped: they wait for the user's decision;
runs with a PASS receipt are skipped). After a PASS, the post steps of the run (gpu_s1.py post and run, metrics_s1.py on its units)
are done one at a time by one post worker (slot lock: at most two trainings + one other Docker job).

  python3 run_stage1.py [--sites B173nb_b10 ...] [--only <site>/<result> ...] [--no-post]

Stop signals (stage-0 config): a non-finite loss term; at a multiple of 1,000 >= 2,000 the prior-origin Gaussians' median opacity
< 0.05 and share >= 0.5 < 0.05 (methods with prior-origin Gaussians); exit code != 0 or no point cloud at 30,000. A CUDA out-of-memory
is run once more; a second one, or any other signal, stops the queue (logs/STOP.json) and is reported. progress.md: the block between
the training markers is rewritten every 1,000 iterations. scientific_verdict: null."""
import argparse
import datetime as dt
import fcntl
import json
import math
import os
import subprocess
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
ART = (REPO.parent / "JointBuildGS-artifacts").resolve()
S0 = ART / "phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"
OUT = ART / "phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1"
WEIGHTS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
SRC = REPO / "src/phd/forks/GeoGS-conf-guided-v1-r12"
IMG = "jointbuildgs:geogs-conf-guided-v1"
PLAN = json.loads((REPO / "configs/phd/main_stage1_v1/train_plan_v1.json").read_text())
SCFG = json.loads((REPO / "configs/phd/main_stage0_v1/stage0_v1.json").read_text())["stage0"]
V = SCFG["values_as_r10"]
SWITCHES = ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior")
OFF = {"prop": (), "prop_ALS1x": (), "imgonly": ("prior",), "trust_ALS": ("judgment", "prior_band")}
RULE = {"prop": "auto", "prop_ALS1x": "current", "imgonly": "auto", "trust_ALS": "auto"}
ITS = int(SCFG["iterations"])
LOCK = OUT / "logs/progress.lock"
SLOT = OUT / "logs/slot0.lock"
STATE = {}                 # run key -> status line
STOP = threading.Event()


def now():
    return dt.datetime.now().strftime("%m-%d %H:%M")


def progress_block():
    lines = ["<!-- training -->", f"**학습 현황** (고친 시각 {now()} KST; 1,000회마다 고침)", "", "| 학습 | GPU | 반복 | 1,000회당 초 | 예상 끝 | 메모 |", "|---|---|---:|---:|---|---|"]
    for k, v in STATE.items():
        lines.append(f"| {k} | {v.get('gpu', '')} | {v.get('it', 0):,} | {v.get('spk', '')} | {v.get('end', '')} | {v.get('note', '')} |")
    lines.append("<!-- /training -->")
    return "\n".join(lines)


def write_progress(note=None):
    p = OUT / "progress.md"
    with open(LOCK, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        s = p.read_text()
        blk = progress_block()
        if "<!-- training -->" in s:
            a, b = s.index("<!-- training -->"), s.index("<!-- /training -->") + len("<!-- /training -->")
            s = s[:a] + blk + s[b:]
        else:
            s = s.replace("## 예상 시간", blk + "\n\n## 예상 시간", 1) if "## 예상 시간" in s else s + "\n" + blk + "\n"
        if note:
            s = s.rstrip("\n") + f"\n- {dt.datetime.now().strftime('%H:%M')} {note}\n"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(s)
        os.replace(tmp, p)
        fcntl.flock(lk, fcntl.LOCK_UN)


def queue_log(text):
    with open(OUT / "logs/queue.log", "a") as q:
        q.write(f"{time.strftime('%H:%M:%S')} {text}\n")


def schedule():
    r = SCFG["records"]
    return ["--iterations", str(ITS), "--test_iterations", *map(str, r["test_iterations"]), "--save_iterations", *map(str, r["save_iterations"]),
            "--jbgs_log_interval", str(r["log_interval"]), "--jbgs_readout_interval", str(r["readout_interval"]),
            "--jbgs_snapshot_iterations", *map(str, r["snapshot_iterations"]), "--jbgs_dump_iterations", *map(str, r["dump_iterations"])]


def command(run, gpu):
    """the stage-0 command (run_fork_v6.command) with the stage-0 payload read-only (/p) and the model in this payload (/o)."""
    site, prior, method = run["site"], run["scene_prior"], run["method"]
    I = f"/p/fork_inputs/s61/{site}"
    fi = json.loads((S0 / "fork_inputs/s61" / site / "fork_inputs.json").read_text())[prior]
    split = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())
    sw = [x for n in SWITCHES for x in (f"--jbgs_sw_{n}", "0" if n in OFF[method] else "1")]
    name = f"jbgs-s1t-{site}-{run['result']}".replace("_", "-").lower()[:60]
    model = f"/o/stage1/{site}/{run['result']}/model"
    return name, ["docker", "run", "--rm", "--name", name, "--gpus", f"device={gpu}", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                  "--cpus", "8", "--shm-size", "8g",
                  "-e", "PYTHONUNBUFFERED=1", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "MPLCONFIGDIR=/tmp/mpl", "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp",
                  "-e", "OMP_NUM_THREADS=8", "-e", f"JBGS_SPLIT_JSON={I}/split.json", "-e", "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
                  "-v", f"{ART}:/artifacts/JointBuildGS:ro", "-v", f"{S0}:/p:ro", "-v", f"{OUT}:/o", "-v", f"{WEIGHTS}:/weights:ro", "-v", f"{SRC}:/source:ro",
                  "-w", "/source", "--entrypoint", "python", IMG,
                  "train.py", "-s", f"{I}/scene_{prior}", "-m", model, "--eval", "-r", "1",
                  "--lod_depth_path", "/p/fork_none", "--da_depth_path", "/p/fork_none",
                  "--stage_switch_iter", "0", "--lambda_lod_init", "0.0", "--lambda_lod_anchor", "0.0", "--lambda_da_depth", "0.0",
                  "--jbgs_judgment", "P", "--jbgs_maps_root", f"{I}/maps", "--jbgs_scene", "N",
                  "--jbgs_origin_path", f"{I}/scene_{prior}/sparse/0/origin.npy", "--jbgs_lambda_mvs", str(V["lambda_mvs"]),
                  "--jbgs_lambda_prior", str(V["lambda_prior"]), *schedule(),
                  "--jbgs_prior_set", f"prior_{prior}", "--jbgs_tau_set", f"tau_{prior}", "--jbgs_tau_v", str(fi["tau_roof"]),
                  "--jbgs_prop_store", f"{I}/store_{prior}.npz", "--jbgs_prop_tag", "data",
                  "--jbgs_prop_majority", str(V["majority"]), "--jbgs_prop_min_evidence", str(V["min_evidence"]),
                  "--jbgs_prop_max_distance", str(V["max_distance_m"]), "--jbgs_seat_path", f"{I}/seat_{prior}.npy",
                  "--jbgs_locmap_dir", f"{I}/maps/locmap_{prior}", "--jbgs_markmap_dir", f"{I}/maps/markmap_{prior}",
                  "--jbgs_markcode_dir", f"{I}/maps/markcode_{prior}", "--jbgs_prop_pairs", f"{I}/pairs_{prior}.npz", "--jbgs_prop_knn", f"{I}/knn_{prior}.npz",
                  "--jbgs_tau_dir", f"{I}/maps/tau_{prior}", "--jbgs_tau_roof", str(fi["tau_roof"]), "--jbgs_tau_wall", str(fi["tau_wall"]),
                  "--jbgs_prior_normal_path", f"{I}/prior_normal_{prior}.npy", "--jbgs_prior_normal_mode", "cell",
                  "--jbgs_e_interval", str(V["reread_interval"]), "--jbgs_e_threshold", str(V["e_threshold"]),
                  "--jbgs_e_depth_tol", str(V["e_depth_tol_m"]), "--jbgs_e_alpha_min", str(V["e_alpha_min"]), "--jbgs_reread_samples", str(V["reread_samples"]),
                  "--jbgs_depth_norm", V["depth_norm"],
                  "--jbgs_lock_lr_scale", str(V["lock_lr_scale"]), "--jbgs_lock_opacity_floor", str(V["lock_opacity_floor"]),
                  "--jbgs_lock_drift_tau_mult", str(V["protection_tau_mult"]), "--jbgs_trunc_hi", str(V["truncation_tau_mult"]),
                  "--jbgs_monitor_views", *split["train"][:2], "--jbgs_stop_on_red", "0", "--jbgs_rule", RULE[method],
                  "--jbgs_prior_kind", prior, "--jbgs_prior_shift", *[repr(float(x)) for x in fi["shift"]], "--jbgs_seed", str(run["seed"]), *sw]


def gpu_used(gpu):
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", str(gpu)], capture_output=True, text=True, timeout=20).stdout
        return float(out.strip().splitlines()[0])
    except Exception:
        return float("nan")


def stop_signal(row, has_prior):
    for k, v in row.items():
        if k in ("rgb", "mvs", "prior", "normal", "dist", "total") and isinstance(v, (int, float)) and not math.isfinite(v):
            return f"non-finite loss term {k} at {row['iteration']}"
    it = int(row["iteration"])
    if has_prior and it >= 2000 and it % 1000 == 0:
        q, share = row.get("opacity_q_prior"), row.get("opacity_share_ge05_prior")
        if q is not None and share is not None and q[1] < 0.05 and share < 0.05:
            return f"opacity collapse of prior-origin Gaussians at {it}: median {q[1]:.4f}, share >= 0.5 {share:.4f}"
    return None


def train(run, gpu, attempt):
    key = f"{run['site']}/{run['result']}"
    R = OUT / "stage1" / run["site"] / run["result"]
    if R.exists() and any(R.iterdir()):
        R.rename(R.parent / f"{run['result']}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    R.mkdir(parents=True, exist_ok=True)
    name, cmd = command(run, gpu)
    log = OUT / "logs" / f"train_{run['site']}_{run['result']}.log"
    if log.exists():
        log.rename(log.with_name(f"{log.stem}_old_{dt.datetime.now().strftime('%H%M%S')}.log"))
    idle = gpu_used(gpu)
    peak = idle
    t0 = time.monotonic()
    start_at = dt.datetime.now().astimezone().isoformat()
    STATE[key] = dict(gpu=gpu, it=0, spk="", end="", note=f"시작 {now()}, 씨앗 {run['seed']}" + (f", 다시 {attempt}" if attempt else ""))
    write_progress()
    with log.open("w") as fh:
        fh.write(" ".join(cmd) + "\n\n")
        fh.flush()
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        marks = [(0, t0)]
        nrows, stop = 0, None
        has_prior = run["method"] != "imgonly"
        sc = R / "model/monitor/scalars.jsonl"
        while True:
            rc = proc.poll()
            peak = max(peak, gpu_used(gpu))
            if sc.exists():
                lines = sc.read_text().splitlines()
                for l in lines[nrows:]:
                    try:
                        row = json.loads(l)
                    except json.JSONDecodeError:
                        break
                    nrows += 1
                    it = int(row["iteration"])
                    reason = stop_signal(row, has_prior)
                    if reason and stop is None:
                        stop = dict(iteration=it, reason=reason)
                        subprocess.run(["docker", "stop", "-t", "30", name], capture_output=True)
                    if it % 1000 == 0 and it > marks[-1][0]:
                        tn = time.monotonic()
                        i0, t_ = marks[-1]
                        spk = (tn - t_) / max(it - i0, 1) * 1000.0
                        end = (dt.datetime.now() + dt.timedelta(seconds=(ITS - it) / 1000.0 * spk)).strftime("%m-%d %H:%M")
                        marks.append((it, tn))
                        n_pr = row.get("n_prior", 0)
                        STATE[key].update(it=it, spk=f"{spk:.0f}", end=end, note=f"가우시안 {row.get('n', 0):,} (사전 {n_pr:,})")
                        write_progress()
            if rc is not None:
                break
            time.sleep(30)
    pc = R / f"model/point_cloud/iteration_{ITS}/point_cloud.ply"
    text = log.read_text(errors="ignore")
    oom = ("out of memory" in text.lower()) or ("OutOfMemoryError" in text)
    status = "STOPPED" if stop else ("PASS" if rc == 0 and pc.exists() else ("OOM" if oom else "FAILED"))
    rec = dict(task_id="PHD-MAIN-STAGE1-v1", site=run["site"], result=run["result"], method=run["method"], scene_prior=run["scene_prior"], seed=run["seed"],
               switches_off=list(OFF[run["method"]]), rule=RULE[run["method"]], gpu=gpu, attempt=attempt, fork="r12", source=str(SRC.relative_to(REPO)), image=IMG,
               image_id=subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG], capture_output=True, text=True).stdout.strip(),
               pytorch_cuda_alloc_conf="expandable_segments:True", command=cmd, started_at=start_at, finished_at=dt.datetime.now().astimezone().isoformat(),
               wall_seconds=round(time.monotonic() - t0, 1), exit_code=rc, gpu_memory_used_mib=dict(idle_before=idle, peak=peak, peak_minus_idle=peak - idle),
               marks=[dict(iteration=i, seconds=round(t - t0, 1)) for i, t in marks], stop_signal=stop, status=status, scientific_verdict=None)
    (R / "receipt.json").write_text(json.dumps(rec, indent=1))
    queue_log(f"train_{run['site']}_{run['result']} {status} {int(time.monotonic() - t0)}s")
    STATE[key].update(note=f"{status}, {rec['wall_seconds'] / 60:.0f}분, GPU 최대 {(peak - idle) / 1024:.1f} GB")
    write_progress(f"{key} 학습 {status} ({rec['wall_seconds'] / 60:.0f}분, GPU {gpu}){' 멈춤 신호: ' + stop['reason'] if stop else ''}")
    return status


POSTQ = []
POST_LOCK = threading.Lock()
RUNNING = {0: None, 1: None}        # gpu -> key of the training on it


def gpu_free(gpu):
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", str(gpu)], capture_output=True, text=True, timeout=20).stdout
        return float(out.strip().splitlines()[0])
    except Exception:
        return 0.0


def pick_gpu():
    """a GPU for a post step: one without a training, or one whose training is past 15,500 iterations (densification over) with
    >= 8 GB free; otherwise wait."""
    while True:
        for g in (0, 1):
            k = RUNNING[g]
            if k is None and gpu_free(g) >= 8000:
                return g
        for g in (0, 1):
            k = RUNNING[g]
            if k is not None and STATE.get(k, {}).get("it", 0) >= 15500 and gpu_free(g) >= 8000:
                return g
        time.sleep(60)


def post_worker(no_post):
    while not (STOP.is_set() and not POSTQ):
        if not POSTQ:
            if all_done.is_set():
                return
            time.sleep(10)
            continue
        run = POSTQ.pop(0)
        if no_post:
            continue
        site, res = run["site"], run["result"]
        units = ["LoD2", "ALS"] if run["method"] == "imgonly" else [run["scene_prior"]]
        steps = [["bash", str(HERE.parent / "run_gpu.sh"), f"post_{site}_{res}", "post", site, res],
                 ["bash", str(HERE.parent / "run_gpu.sh"), f"run_{site}_{res}", "run", site, res]]
        for u in units:
            steps.append(["bash", str(HERE.parent / "run_cpu.sh"), f"met_{site}_{res}_{u}", "metrics_s1.py", site, u, res])
        with open(SLOT, "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            for st in steps:
                g = pick_gpu() if st[3] in ("post", "run") else 0
                env = dict(os.environ, GPU=str(g), CPUS="12")
                rc = subprocess.run(st, env=env, capture_output=True, text=True).returncode
                if rc != 0:
                    write_progress(f"{site}/{res} 후처리 실패: {st[2]} (rc {rc}) — 평가의 길 오류로 보고 멈춤")
                    (OUT / "logs/STOP.json").write_text(json.dumps(dict(at=now(), run=f"{site}/{res}", step=st[2], rc=rc), indent=1))
                    STOP.set()
                    break
            fcntl.flock(lk, fcntl.LOCK_UN)
        if not STOP.is_set():
            write_progress(f"{site}/{res} 후처리·지표 끝")


all_done = threading.Event()


def gpu_worker(gpu, queue):
    while not STOP.is_set():
        with POST_LOCK:
            if not queue:
                return
            run = queue.pop(0)
        RUNNING[gpu] = f"{run['site']}/{run['result']}"
        st = train(run, gpu, 0)
        if st == "OOM" and not STOP.is_set():
            write_progress(f"{run['site']}/{run['result']} GPU 메모리 부족 — 같은 학습을 한 번 더 돌림")
            st = train(run, gpu, 1)
            if st == "OOM":
                (OUT / "logs/STOP.json").write_text(json.dumps(dict(at=now(), run=f"{run['site']}/{run['result']}", reason="second out-of-memory"), indent=1))
                write_progress(f"{run['site']}/{run['result']} 두 번째 GPU 메모리 부족 — 멈추고 여쭙는다")
                STOP.set()
                return
        if st != "PASS":
            (OUT / "logs/STOP.json").write_text(json.dumps(dict(at=now(), run=f"{run['site']}/{run['result']}", reason=st), indent=1))
            write_progress(f"{run['site']}/{run['result']} 실행 조건이 깨짐({st}) — 멈추고 여쭙는다")
            STOP.set()
            return
        RUNNING[gpu] = None
        run["_gpu"] = gpu
        POSTQ.append(run)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="+", default=None)
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--no-post", action="store_true")
    a = ap.parse_args()
    queue = []
    for r in PLAN["runs"]:
        if r["method"] == "geogs":
            continue
        if a.sites and r["site"] not in a.sites:
            continue
        if a.only and f"{r['site']}/{r['result']}" not in a.only:
            continue
        rec = OUT / "stage1" / r["site"] / r["result"] / "receipt.json"
        if rec.exists() and json.loads(rec.read_text()).get("status") == "PASS":
            continue
        queue.append(dict(r))
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    write_progress(f"학습 대기열 시작: {len(queue)}회 ({', '.join(r['site'] + '/' + r['result'] for r in queue[:4])} ...)")
    pw = threading.Thread(target=post_worker, args=(a.no_post,))
    pw.start()
    ws = [threading.Thread(target=gpu_worker, args=(g, queue)) for g in (0, 1)]
    for w in ws:
        w.start()
        time.sleep(60)            # the two starts one minute apart (host memory at the initialisation)
    for w in ws:
        w.join()
    all_done.set()
    pw.join()
    write_progress("학습 대기열 끝" + (" (멈춤: logs/STOP.json)" if STOP.is_set() else ""))


if __name__ == "__main__":
    main()
