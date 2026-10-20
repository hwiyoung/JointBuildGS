#!/usr/bin/env python3
"""PHD-MAIN-FIXTEST-v1 training queue (host orchestration only, stdlib) = stage 3's run_s3.py rules on this task's 14 trainings (order 8.2):
two lanes (GPU 0 = fix A and A + B of B173 주변 항공 LiDAR, GPU 1 = fix B and A + B of R1 항공 LiDAR, in the order of the table); a GPU whose
lane is empty takes the next training of the other lane. A worker takes its next training only when its GPU is idle (< 2,000 MiB).
After a PASS the GPU worker does stage 3's GPU post steps on its own GPU (gpu_ft.py post, run; one TSDF at a time; an R1 post holds the
CPU slot as well, so it runs alone), the CPU steps go to the post worker (ft_step.py: nan_clean_s3, metrics_s2, measure_s2, bands_s2,
support_s2, fates_s2).

Only the trainings that the saved configuration (configs/phd/main_fixtest_v1/fixtest_v1.json, its sha256 written at saving and checked
here) lists under runs[*].train = true run; a fix-A training also needs its w maps (prep/wmaps/<site>/<prior>/summary.json written).
  python3 run_ft.py [--only <site>/<result> ...] [--gpus 0 1]

Stop signals (order 3.8): an exit code != 0, a non-finite loss term, the prior-origin Gaussians' median opacity < 0.05 at a multiple of
1,000 >= 2,000 -> that training stops, is recorded (receipt, progress.md, logs/STOP_<run>.json) and left for the user; the others go on.
A CUDA out-of-memory: the same command once more; if it stops again: '학습이 끝까지 돌지 못함', the queue goes on without asking. A post
GPU out-of-memory: once more at once; a host out-of-memory kill (rc 137): once more at the end, alone; again -> '후처리가 끝까지 돌지 못함'.
After the first two trainings of each lane (the first four) logs/MID_READY.json is written (the middle report). scientific_verdict: null."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ft_plan as P  # noqa: E402

FT, ITS = P.FT, P.ITS
CFG = P.REPO / "configs/phd/main_fixtest_v1/fixtest_v1.json"
LOCK, SLOT, TSDF = FT / "logs/progress.lock", FT / "logs/slot0.lock", FT / "logs/tsdf.lock"
STATE, NO_RESULT, POSTQ, POST_LATER, FINISHED = {}, [], [], [], []
LK = threading.Lock()
DONE = threading.Event()
POST_NEED_GB = {"post": 50.0, "run": 25.0}
IDLE_MIB = 2000.0


def now():
    return dt.datetime.now().strftime("%m-%d %H:%M")


def progress_block():
    lines = ["<!-- training -->", f"**학습 현황** (고친 시각 {now()} KST; 1,000회마다 고침)", "", "| 학습 | GPU | 반복 | 1,000회당 초 | 예상 끝 | 메모 |", "|---|---|---:|---:|---|---|"]
    for k, v in STATE.items():
        lines.append(f"| {k} | {v.get('gpu', '')} | {v.get('it', 0):,} | {v.get('spk', '')} | {v.get('end', '')} | {v.get('note', '')} |")
    lines.append("<!-- /training -->")
    return "\n".join(lines)


def write_progress(note=None):
    p = FT / "progress.md"
    with open(LOCK, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        s = p.read_text()
        blk = progress_block()
        if "<!-- training -->" in s:
            a, b = s.index("<!-- training -->"), s.index("<!-- /training -->") + len("<!-- /training -->")
            s = s[:a] + blk + s[b:]
        else:
            s = s.rstrip("\n") + "\n\n## 학습\n\n" + blk + "\n"
        if note:
            s = s.rstrip("\n") + f"\n- {dt.datetime.now().strftime('%m-%d %H:%M')} {note}\n"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(s)
        os.replace(tmp, p)
        fcntl.flock(lk, fcntl.LOCK_UN)


def queue_log(text):
    with open(FT / "logs/queue.log", "a") as q:
        q.write(f"{time.strftime('%m-%d %H:%M:%S')} {text}\n")


def gpu_used(gpu):
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", str(gpu)], capture_output=True, text=True, timeout=20).stdout
        return float(out.strip().splitlines()[0])
    except Exception:
        return float("nan")


def host_available_gb():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 ** 2
    return float("nan")


def stop_signal(row):
    for k, v in row.items():
        if k in ("rgb", "mvs", "prior", "normal", "dist", "total") and isinstance(v, (int, float)) and not math.isfinite(v):
            return f"non-finite loss term {k} at {row['iteration']}"
    it = int(row["iteration"])
    if it >= 2000 and it % 1000 == 0:
        q = row.get("opacity_q_prior")
        if q is not None and q[1] < 0.05:
            return f"opacity collapse of prior-origin Gaussians at {it}: median {q[1]:.4f}"
    return None


def rdir(run):
    return FT / "runs" / run["site"] / run["result"]


def key_of(run):
    return f"{run['site']}/{run['result']}"


def train_once(run, gpu, attempt):
    key = key_of(run)
    R = rdir(run)
    if R.exists() and any(R.iterdir()):
        R.rename(R.parent / f"{run['result']}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    R.mkdir(parents=True, exist_ok=True)
    name, cmd = P.command(run, gpu)
    log = FT / "logs" / f"train_{run['site']}_{run['result']}.log"
    if log.exists():
        log.rename(log.with_name(f"{log.stem}_old_{dt.datetime.now().strftime('%H%M%S')}.log"))
    idle = gpu_used(gpu)
    peak = idle
    t0 = time.monotonic()
    start_at = dt.datetime.now().astimezone().isoformat()
    STATE[key] = dict(gpu=gpu, it=0, spk="", end="", note=f"시작 {now()}, {run['what']}" + (f", 시도 {attempt}" if attempt > 1 else ""))
    write_progress()
    marks, nrows, stop = [(0, t0)], 0, None
    with log.open("w") as fh:
        fh.write(" ".join(cmd) + "\n\n")
        fh.flush()
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        sc = R / "model/monitor/scalars.jsonl"
        while True:
            rc = proc.poll()
            peak = max(peak, gpu_used(gpu))
            it, note = None, None
            if sc.exists():
                for l in sc.read_text().splitlines()[nrows:]:
                    try:
                        row = json.loads(l)
                    except json.JSONDecodeError:
                        break
                    nrows += 1
                    reason = stop_signal(row)
                    if reason and stop is None:
                        stop = dict(iteration=int(row["iteration"]), reason=reason)
                        subprocess.run(["docker", "stop", "-t", "30", name], capture_output=True)
                    it, note = int(row["iteration"]), f"가우시안 {row.get('n', 0):,} (사전 {row.get('n_prior', 0):,})"
            if it is not None and it // 1000 * 1000 > marks[-1][0]:
                k = it // 1000 * 1000
                tn = time.monotonic()
                i0, t_ = marks[-1]
                spk = (tn - t_) / max(k - i0, 1) * 1000.0
                end = (dt.datetime.now() + dt.timedelta(seconds=(ITS - k) / 1000.0 * spk)).strftime("%m-%d %H:%M")
                marks.append((k, tn))
                STATE[key].update(it=k, spk=f"{spk:.0f}", end=end, note=note)
                write_progress()
            if rc is not None:
                break
            time.sleep(30)
    pc = R / f"model/point_cloud/iteration_{ITS}/point_cloud.ply"
    text = log.read_text(errors="ignore")
    oom = ("out of memory" in text.lower()) or ("OutOfMemoryError" in text)
    status = "STOPPED" if stop else ("PASS" if rc == 0 and pc.exists() else ("OOM" if oom else "FAILED"))
    oomrec = R / "model/monitor/oom_record.json"
    rec = dict(task_id="PHD-MAIN-FIXTEST-v1", site=run["site"], result=run["result"], what=run["what"], fix=run["fix"], order=run["order"], lane=run["lane"],
               scene_prior=run["prior"], seed=run["seed"], attempt=attempt, gpu=gpu, image=P.IMG,
               image_id=subprocess.run(["docker", "inspect", "--format", "{{.Id}}", P.IMG], capture_output=True, text=True).stdout.strip(),
               source=str(P.SRC["r16"]), fork="r16", pytorch_cuda_alloc_conf="expandable_segments:True", command=cmd, started_at=start_at,
               finished_at=dt.datetime.now().astimezone().isoformat(), wall_seconds=round(time.monotonic() - t0, 1), exit_code=rc,
               gpu_memory_used_mib=dict(idle_before=idle, peak=peak, peak_minus_idle=peak - idle),
               marks=[dict(iteration=i, seconds=round(t - t0, 1)) for i, t in marks], stop_signal=stop, status=status,
               oom_record=json.loads(oomrec.read_text()) if oomrec.exists() else None, config_sha256=CONFIG_SHA, scientific_verdict=None)
    (R / "receipt.json").write_text(json.dumps(rec, indent=1))
    queue_log(f"train_{run['site']}_{run['result']} {status} {int(time.monotonic() - t0)}s gpu{gpu} attempt{attempt}")
    STATE[key].update(note=f"{status}, {rec['wall_seconds'] / 60:.0f}분, GPU 최대 {(peak - idle) / 1024:.1f} GiB" + (f", 시도 {attempt}" if attempt > 1 else ""))
    msg = f"{key} ({run['what']}) 학습 {status} ({rec['wall_seconds'] / 60:.0f}분, GPU {gpu}, 시도 {attempt})" + (f" 멈춤 신호: {stop['reason']}" if stop else "")
    write_progress(msg)
    return status


def train(run, gpu):
    st = train_once(run, gpu, 1)
    if st == "OOM":
        R = rdir(run)
        R.rename(R.parent / f"{run['result']}_try1_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
        write_progress(f"{key_of(run)} GPU 메모리 부족 — 3절 8번대로 같은 설정으로 한 번 더 돌림")
        wait_idle(gpu, f"{key_of(run)} 두 번째 시도 전")
        st = train_once(run, gpu, 2)
    return st


def wait_idle(g, why):
    noted = False
    while True:
        u = gpu_used(g)
        if u == u and u < IDLE_MIB:
            return True
        if not noted:
            write_progress(f"GPU {g}: {why} — GPU가 빌 때까지 기다림 ({u:.0f} MiB 사용 중)")
            noted = True
        time.sleep(60)


def wait_host(need, why):
    noted = False
    while True:
        a = host_available_gb()
        if a == a and a >= need:
            return
        if not noted:
            write_progress(f"{why} — 호스트에 쓸 수 있는 메모리 {a:.0f} GB < {need:.0f} GB, 빌 때까지 기다림")
            noted = True
        time.sleep(60)


def gpu_step(run, g, mode, mem="72g"):
    """one GPU post step under the TSDF lock (an R1 step also under the CPU slot: alone); returns (rc, oom, host min GB, seconds)."""
    site, res = run["site"], run["result"]
    tag = f"{mode}_{site}_{res}"
    wait_idle(g, f"{site}/{res} 후처리 {mode} 전")
    wait_host(POST_NEED_GB[mode], f"{site}/{res} 후처리 {mode} 전")
    lows, stop_s = [], threading.Event()

    def sampler():
        while not stop_s.is_set():
            lows.append(host_available_gb())
            stop_s.wait(5)
    alone = site == "R1rep_b10"
    with open(TSDF, "a") as tl, open(SLOT, "a") as sl:
        fcntl.flock(tl, fcntl.LOCK_EX)
        if alone:
            fcntl.flock(sl, fcntl.LOCK_EX)
        th = threading.Thread(target=sampler); th.start()
        t0 = time.monotonic()
        rc = subprocess.run(["bash", str(HERE / "run_gpu_ft.sh"), tag, "gpu_ft.py", mode, site, res], env=dict(os.environ, GPU=str(g), MEM=mem),
                            capture_output=True, text=True).returncode
        stop_s.set(); th.join()
        if alone:
            fcntl.flock(sl, fcntl.LOCK_UN)
        fcntl.flock(tl, fcntl.LOCK_UN)
    oom = "out of memory" in (FT / "logs" / f"{tag}.log").read_text(errors="ignore").lower()
    return rc, oom, (min(lows) if lows else None), round(time.monotonic() - t0, 1)


def gpu_post(run, g):
    site, res = run["site"], run["result"]
    rec = {}
    for mode in ("post", "run"):
        for attempt in (1, 2):
            rc, oom, low, sec = gpu_step(run, g, mode)
            rec[mode] = dict(rc=rc, oom=oom, host_min_available_gb=low, seconds=sec, attempt=attempt)
            if rc == 0:
                break
            if oom and attempt == 1:
                write_progress(f"{site}/{res} 후처리 {mode} GPU 메모리 부족 — 한 번 더 돌림 (GPU {g})")
                continue
            if rc == 137:
                write_progress(f"{site}/{res} 후처리 {mode} 강제 종료(rc 137, 호스트 메모리 부족일 수 있음) — 대기열 끝에서 혼자 한 번 더 함")
                with LK:
                    POST_LATER.append(run)
            else:
                write_progress(f"{site}/{res} 후처리 {mode} 실패 (rc {rc}) — 이 학습의 후처리를 멈추고 기록")
            (FT / "logs" / f"STOP_post_{site}_{res}.json").write_text(json.dumps(dict(at=now(), step=f"{mode}_{site}_{res}", rc=rc, oom=oom), indent=1))
            (rdir(run) / "post_host_memory.json").write_text(json.dumps(rec, indent=1))
            return False
    (rdir(run) / "post_host_memory.json").write_text(json.dumps(rec, indent=1))
    write_progress(f"{site}/{res} GPU 후처리 끝 (post {rec['post']['seconds']:.0f}초·호스트 여유 최소 {rec['post']['host_min_available_gb']:.0f} GB, "
                   f"run {rec['run']['seconds']:.0f}초)")
    return True


def cpu_steps(run):
    site, res, pr = run["site"], run["result"], run["prior"]
    return [(f"nan_{site}_{res}", ["nan_clean_s3.py", site, res]), (f"met_{site}_{res}", ["metrics_s2.py", site, pr, res]),
            (f"meas_{site}_{res}", ["measure_s2.py", site, res]), (f"bands_{site}_{res}", ["bands_s2.py", site, pr, res]),
            (f"supp_{site}_{res}", ["support_s2.py", site, pr, res]), (f"fates_{site}_{res}", ["fates_s2.py", site, pr, res])]


def post_worker():
    while True:
        with LK:
            run = POSTQ.pop(0) if POSTQ else None
        if run is None:
            if DONE.is_set():
                return
            time.sleep(10)
            continue
        site, res = run["site"], run["result"]
        with open(SLOT, "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            ok = True
            t0 = time.monotonic()
            for tag, args in cpu_steps(run):
                rc = subprocess.run(["bash", str(HERE / "run_step_ft.sh"), tag, "ft_step.py", *args], env=dict(os.environ, CPUS="12", MEM="40"),
                                    capture_output=True, text=True).returncode
                if rc != 0:
                    write_progress(f"{site}/{res} 지표 실패: {tag} (rc {rc}) — 기록, 다음으로")
                    ok = False
                    break
            fcntl.flock(lk, fcntl.LOCK_UN)
        if ok:
            write_progress(f"{site}/{res} 후처리·지표 끝 ({(time.monotonic() - t0) / 60:.0f}분)")
        with LK:
            FINISHED.append(key_of(run))
            mid = MID_RUNS
            if all(k in FINISHED or k in [x.split(" ")[0] for x in NO_RESULT] for k in mid) and not (FT / "logs/MID_READY.json").exists():
                (FT / "logs/MID_READY.json").write_text(json.dumps(dict(at=now(), runs=mid, finished=FINISHED, no_result=NO_RESULT), indent=1))
                write_progress("차례 2까지의 네 학습과 후처리 끝 — 중간 보고 자료 준비됨 (logs/MID_READY.json)")


def ready(run):
    if run["fix"].startswith("A"):
        s = P.wmap_dir(run["site"], run["prior"], container=False, reading=P.reading_of(run["fix"])) / "summary.json"
        return s.exists() and json.loads(s.read_text()).get("written") is True
    return True


def gpu_worker(g, lanes):
    noted = set()
    while True:
        wait_idle(g, "다음 학습 전")
        with LK:
            own, other = lanes[g], lanes[1 - g]
            pick = next((r for r in own if ready(r)), None) or next((r for r in other if ready(r)), None)
            if pick is not None:
                (own if pick in own else other).remove(pick)
            left = own + other
        if pick is None:
            if not left:
                return
            key = tuple(key_of(r) for r in left)
            if key not in noted:
                write_progress(f"GPU {g}: 준비된 학습이 없음({', '.join(key)}) — 기다림")
                noted.add(key)
            time.sleep(60)
            continue
        run = pick
        st = train(run, g)
        if st != "PASS":
            NO_RESULT.append(f"{key_of(run)} ({st})")
            (FT / "logs" / f"STOP_{run['site']}_{run['result']}.json").write_text(json.dumps(dict(at=now(), run=key_of(run), status=st), indent=1))
            if st == "OOM":
                write_progress(f"{key_of(run)} 학습이 끝까지 돌지 못함(GPU 메모리 부족) — 3절 8번대로 기록하고 넘어감")
            else:
                write_progress(f"{key_of(run)} 멈춤({st}) — 3절 8번대로 기록하고 여쭙는다. 나머지 학습은 이어 감")
            continue
        if gpu_post(run, g):
            with LK:
                POSTQ.append(run)


def config_runs():
    """the trainings the saved configuration allows, with its sha256 check."""
    cfg_bytes = CFG.read_bytes()
    sha = hashlib.sha256(cfg_bytes).hexdigest()
    rec = json.loads((CFG.parent / "fixtest_v1.sha256.json").read_text())
    if rec["sha256"] != sha:
        raise SystemExit(f"the configuration changed after saving ({rec['sha256'][:12]} != {sha[:12]}): record the change first")
    cfg = json.loads(cfg_bytes)
    allowed = {(r["site"], r["result"]) for r in cfg["runs"] if r.get("train")}
    return allowed, sha


ALL_RUNS = []
MID_RUNS = []          # the middle report (order 8.2): the first two trainings of each lane that the configuration trains
CONFIG_SHA = None


def main():
    global IDLE_MIB, ALL_RUNS, CONFIG_SHA, MID_RUNS
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--gpus", nargs="+", type=int, default=[0, 1])
    ap.add_argument("--idle-mib", type=float, default=2000.0)
    a = ap.parse_args()
    IDLE_MIB = a.idle_mib
    allowed, CONFIG_SHA = config_runs()
    lanes = {0: [], 1: []}
    skipped = []
    for r in sorted(P.RUNS, key=lambda x: x["order"]):
        if a.only and key_of(r) not in a.only:
            continue
        if (r["site"], r["result"]) not in allowed:
            skipped.append(key_of(r))
            continue
        f = rdir(r) / "receipt.json"
        if f.exists() and json.loads(f.read_text()).get("status") == "PASS":
            continue
        lanes[r["lane"]].append(dict(r))
    ALL_RUNS = [dict(r) for r in P.RUNS if (r["site"], r["result"]) in allowed]
    MID_RUNS = [key_of(r) for g in (0, 1) for r in [x for x in ALL_RUNS if x["lane"] == g][:2]]
    write_progress(f"학습 대기열 시작: GPU 0 {len(lanes[0])}회, GPU 1 {len(lanes[1])}회 (설정 sha256 {CONFIG_SHA[:12]}) — "
                   + "; ".join(f"GPU {g}: " + ", ".join(key_of(r) for r in lanes[g]) for g in (0, 1))
                   + (f" — 설정이 학습하지 않는 것(관문): {', '.join(skipped)}" if skipped else ""))
    pw = threading.Thread(target=post_worker)
    pw.start()
    if len(a.gpus) == 1:                       # one GPU: it takes both lanes in order
        g0 = a.gpus[0]
        lanes = {g0: sorted(lanes[0] + lanes[1], key=lambda x: (x["order"], x["lane"])), 1 - g0: []}
    ws = [threading.Thread(target=gpu_worker, args=(g, lanes)) for g in a.gpus]
    for w in ws:
        w.start()
        time.sleep(60)
    for w in ws:
        w.join()
    for run in list(POST_LATER):
        with open(SLOT, "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            write_progress(f"{key_of(run)} 후처리를 혼자 한 번 더 함(호스트 메모리)")
            ok = True
            for mode in ("post", "run"):
                rc, oom, low, sec = gpu_step(run, 0, mode)
                if rc != 0:
                    write_progress(f"{key_of(run)} 후처리가 끝까지 돌지 못함 ({mode} rc {rc}) — 기록하고 넘어감")
                    ok = False
                    break
            fcntl.flock(lk, fcntl.LOCK_UN)
        if ok:
            with LK:
                POSTQ.append(run)
    DONE.set()
    pw.join()
    write_progress("학습 대기열 끝" + (f" — 결과 없음: {', '.join(NO_RESULT)}" if NO_RESULT else ""))
    (FT / "logs" / "QUEUE_DONE.json").write_text(json.dumps(dict(at=now(), no_result=NO_RESULT, finished=FINISHED), indent=1))


if __name__ == "__main__":
    main()
