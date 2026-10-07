#!/usr/bin/env python3
"""PHD-MAIN-STAGE1-v1 GeoGS (always-trust LoD2) runs of the training plan (method 'geogs'), after the 23-run queue of run_stage1.py
(host orchestration only, stdlib). Decided by the user 2026-10-07: the official code with the author settings, DA3 in batches with a
scale check against MVS, the camera adapter (principal point) and the split adapter (split.json).

Steps (each skipped when its output exists):
  1. wait until progress.md has the queue runner v2's '학습 대기열 v2 끝' line (its trainings and post steps are done; run_stage1.py was
     replaced by run_stage1_v2.py after the post failure of 16:37); a stopped queue ('멈춤') stops here (--no-wait skips the wait)
  2. inputs (run_geogs_prep.sh: official generate_pcd.py and LoD2Depth) of the sites without geogs/<site>/prep.json
  3. DA3 (geogs_da3.py, jointbuildgs:geogs-da3-3d835ec-v1) of every site, one per GPU at a time (a GPU with >= 20 GB free)
  4. the scale check against MVS (geogs_scale.py, CPU)
  5. trainings, one per GPU, in plan order: the official train.py of the adapters copy (geogs/source/GeoGS-official-adapters-v1) in
     jointbuildgs:geogs-official-db40c95-compat-v1 (the earlier work's image: matplotlib 3.9.2, libstdc++ preload), the author flags
     --lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight (30,000 iterations, stage switch 8,000, lambda_lod_init 0.08,
     lambda_lod_anchor 0.005 as the earlier work passed them; other values the defaults), -r 1, --eval, JBGS_SPLIT_JSON = split.json,
     PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True (order: every training). A CUDA out-of-memory is run once more; a second one or any
     other failure stops (logs/STOP_geogs.json).
  6. after each PASS, under the slot lock: gpu_s1.py post and run (the fork's renderer on the same cameras), metrics_s1.py <site> LoD2 trust_LoD2
progress.md: the training block keeps its rows and gets one row per GeoGS run, rewritten every 1,000 iterations (read from the log).

  python3 run_geogs.py [--sites <site> ...] [--no-wait]
scientific_verdict: null."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
ART = (REPO.parent / "JointBuildGS-artifacts").resolve()
PH = ART / "phase-payloads/phd"
S0 = PH / "main_stage0_v1/PHD-MAIN-STAGE0-v1"
OUT = PH / "main_stage1_v1/PHD-MAIN-STAGE1-v1"
T = PH / "geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
WEIGHTS = T / "runtime/weights"
DA3W = T / "sources/DA3NESTED-GIANT-LARGE"
OFFICIAL_DA3 = T / "sources/GeoGS/preprocessing/get_da3_depth_with_colmap.py"
SOURCE = OUT / "geogs/source/GeoGS-official-adapters-v1"
IMG_TRAIN, IMG_DA3, IMG_DEV = "jointbuildgs:geogs-official-db40c95-compat-v1", "jointbuildgs:geogs-da3-3d835ec-v1", "jointbuildgs:dev"
PLAN = json.loads((REPO / "configs/phd/main_stage1_v1/train_plan_v1.json").read_text())
ITS = 30000
FLAGS = ["--lod_init", "--freeze_onlybldg", "--protect_bldg", "--dynamic_depth_weight", "-r", "1", "--port", "0", "--iterations", str(ITS),
         "--stage_switch_iter", "8000", "--lambda_lod_init", "0.08", "--lambda_lod_anchor", "0.005"]
LOCK, SLOT = OUT / "logs/progress.lock", OUT / "logs/slot0.lock"
STATE, ROWS0 = {}, []
STOP = threading.Event()
GPU_LOCK = threading.Lock()
BUSY = {0: False, 1: False}


def now():
    return dt.datetime.now().strftime("%m-%d %H:%M")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_progress(note=None):
    p = OUT / "progress.md"
    with open(LOCK, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        s = p.read_text()
        a, b = s.index("<!-- training -->"), s.index("<!-- /training -->") + len("<!-- /training -->")
        if not ROWS0:
            ROWS0.extend(l for l in s[a:b].splitlines() if l.startswith("| ") and not l.startswith("| 학습 "))
        lines = ["<!-- training -->", f"**학습 현황** (고친 시각 {now()} KST; 1,000회마다 고침)", "", "| 학습 | GPU | 반복 | 1,000회당 초 | 예상 끝 | 메모 |",
                 "|---|---|---:|---:|---|---|", *ROWS0]
        for k, v in STATE.items():
            lines.append(f"| {k} | {v.get('gpu', '')} | {v.get('it', 0):,} | {v.get('spk', '')} | {v.get('end', '')} | {v.get('note', '')} |")
        lines.append("<!-- /training -->")
        s = s[:a] + "\n".join(lines) + s[b:]
        if note:
            s = s.rstrip("\n") + f"\n- {dt.datetime.now().strftime('%H:%M')} {note}\n"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(s)
        os.replace(tmp, p)
        fcntl.flock(lk, fcntl.LOCK_UN)


def queue_log(text):
    with open(OUT / "logs/queue.log", "a") as q:
        q.write(f"{time.strftime('%H:%M:%S')} {text}\n")


def nvsmi(gpu, field):
    try:
        out = subprocess.run(["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits", "-i", str(gpu)], capture_output=True, text=True, timeout=20).stdout
        return float(out.strip().splitlines()[0])
    except Exception:
        return float("nan")


def take_gpu(min_free):
    while not STOP.is_set():
        with GPU_LOCK:
            for g in (0, 1):
                if not BUSY[g] and nvsmi(g, "memory.free") >= min_free:
                    BUSY[g] = True
                    return g
        time.sleep(30)
    return None


def give_gpu(g):
    with GPU_LOCK:
        BUSY[g] = False


def docker_base(name, gpu=None):
    b = ["docker", "run", "--rm", "--name", name, "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}"]
    return b + (["--gpus", f"device={gpu}"] if gpu is not None else [])


def run_logged(cmd, log, tag):
    t0 = time.monotonic()
    with open(log, "w") as fh:
        fh.write(" ".join(map(str, cmd)) + "\n\n")
        fh.flush()
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
    queue_log(f"{tag} rc={rc} {int(time.monotonic() - t0)}s")
    return rc


def stop(reason, **kw):
    (OUT / "logs/STOP_geogs.json").write_text(json.dumps(dict(at=now(), reason=reason, **kw), indent=1))
    write_progress(f"GeoGS 멈춤: {reason} — 멈추고 여쭙는다")
    STOP.set()


# ------------------------------------------------------------------------------------------------ steps 3-4
def da3(site):
    if (OUT / "geogs" / site / "scene/da3_prior/receipt.json").exists():
        return 0
    g = take_gpu(20000)
    if g is None:
        return 1
    try:
        S = OUT / "geogs" / site / "scene"
        cmd = docker_base(f"jbgs-s1-geogs-da3-{site.lower().replace('_', '-')}", g) + [
            "--cpus", "8", "--memory", "32g", "--shm-size", "2g", "-e", "PYTHONUNBUFFERED=1", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "HOME=/tmp",
            "-e", "HF_HUB_OFFLINE=1", "-v", f"{DA3W}:/model:ro", "-v", f"{OFFICIAL_DA3}:/official.py:ro", "-v", f"{S}:/scene",
            "-v", f"{S0}/fork_inputs/s61/{site}/split.json:/split.json:ro", "-v", f"{REPO}:/repo:ro", "-w", "/repo/scripts/phd/main_stage1_v1",
            "--entrypoint", "python", IMG_DA3, "geogs_da3.py", site]
        rc = run_logged(cmd, OUT / "logs" / f"geogs_da3_{site}.log", f"geogs_da3_{site}")
    finally:
        give_gpu(g)
    write_progress(f"GeoGS DA3 {site} rc={rc} (GPU {g})")
    return rc


def scale(sites):
    cmd = ["bash", str(HERE.parent / "run_cpu.sh"), "geogs_scale", "geogs_scale.py", *sites]
    return subprocess.run(cmd, env=dict(os.environ, SLOT="1", CPUS="8")).returncode


# ------------------------------------------------------------------------------------------------ step 5
def train(site, gpu, attempt):
    res = "trust_LoD2"
    key = f"{site}/{res}"
    R = OUT / "stage1" / site / res
    if R.exists() and any(R.iterdir()):
        R.rename(R.parent / f"{res}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    R.mkdir(parents=True, exist_ok=True)
    S = OUT / "geogs" / site / "scene"
    name = f"jbgs-s1t-{site}-{res}".replace("_", "-").lower()[:60]
    args = ["train.py", "-s", "/scene", "-m", "/o/model", "--lod_depth_path", "/scene/lod2_prior", "--da_depth_path", "/scene/da3_prior",
            "--lod2_pcd_path", "/scene/lod2_pcd.ply", "--eval", *FLAGS]
    cmd = docker_base(name, gpu) + [
        "--cpus", "8", "--shm-size", "8g", "-e", "PYTHONUNBUFFERED=1", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "MPLCONFIGDIR=/tmp/mpl",
        "-e", "TORCH_HOME=/weights/torch", "-e", "HOME=/tmp", "-e", "OMP_NUM_THREADS=8", "-e", "LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6",
        "-e", "JBGS_SPLIT_JSON=/split.json", "-e", "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
        "-v", f"{SOURCE}:/source:ro", "-v", f"{S}:/scene:ro", "-v", f"{S0}/fork_inputs/s61/{site}/split.json:/split.json:ro", "-v", f"{R}:/o",
        "-v", f"{WEIGHTS}:/weights:ro", "-w", "/source", "--entrypoint", "python", IMG_TRAIN, *args]
    log = OUT / "logs" / f"train_{site}_{res}.log"
    if log.exists():
        log.rename(log.with_name(f"{log.stem}_old_{dt.datetime.now().strftime('%H%M%S')}.log"))
    idle = nvsmi(gpu, "memory.used")
    peak = idle
    t0 = time.monotonic()
    start_at = dt.datetime.now().astimezone().isoformat()
    STATE[key] = dict(gpu=gpu, it=0, note=f"GeoGS 시작 {now()}" + (f", 다시 {attempt}" if attempt else ""))
    write_progress()
    marks = [(0, t0)]
    with log.open("w") as fh:
        fh.write(" ".join(cmd) + "\n\n")
        fh.flush()
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        while True:
            rc = proc.poll()
            peak = max(peak, nvsmi(gpu, "memory.used"))
            try:
                with open(log, "rb") as f:
                    f.seek(max(0, log.stat().st_size - 8192))
                    tail = f.read().decode("utf-8", "ignore")
                its = [int(x) for x in re.findall(r"(\d+)/" + str(ITS) + r" \[", tail)]
                pts = re.findall(r"Points=(\d+)", tail)
            except OSError:
                its, pts = [], []
            if its:
                it = (max(its) // 1000) * 1000
                if it > marks[-1][0]:
                    tn = time.monotonic()
                    i0, t_ = marks[-1]
                    spk = (tn - t_) / max(it - i0, 1) * 1000.0
                    marks.append((it, tn))
                    end = (dt.datetime.now() + dt.timedelta(seconds=(ITS - it) / 1000.0 * spk)).strftime("%m-%d %H:%M")
                    STATE[key].update(it=it, spk=f"{spk:.0f}", end=end, note=f"GeoGS, 가우시안 {int(pts[-1]):,}" if pts else "GeoGS")
                    write_progress()
            if rc is not None:
                break
            time.sleep(30)
    pc = R / f"model/point_cloud/iteration_{ITS}/point_cloud.ply"
    text = log.read_text(errors="ignore")
    oom = "out of memory" in text.lower() or "OutOfMemoryError" in text
    status = "PASS" if rc == 0 and pc.exists() else ("OOM" if oom else "FAILED")
    man = json.loads((OUT / "geogs/source/source_manifest.json").read_text())
    rec = dict(task_id="PHD-MAIN-STAGE1-v1", site=site, result=res, method="geogs", scene_prior="LoD2", seed=0, gpu=gpu, attempt=attempt,
               official_commit=man["official_commit"], source=str(SOURCE.relative_to(OUT)), source_manifest_sha256=sha(OUT / "geogs/source/source_manifest.json"),
               adapters=dict(camera="jbgs_calibration.json of the scene (principal point)", split="JBGS_SPLIT_JSON = split.json"),
               image=IMG_TRAIN, image_id=subprocess.run(["docker", "inspect", "--format", "{{.Id}}", IMG_TRAIN], capture_output=True, text=True).stdout.strip(),
               scene=str(S.relative_to(OUT)), pytorch_cuda_alloc_conf="expandable_segments:True", command=cmd, started_at=start_at,
               finished_at=dt.datetime.now().astimezone().isoformat(), wall_seconds=round(time.monotonic() - t0, 1), exit_code=rc,
               gpu_memory_used_mib=dict(idle_before=idle, peak=peak, peak_minus_idle=peak - idle), marks=[dict(iteration=i, seconds=round(t - t0, 1)) for i, t in marks],
               status=status, scientific_verdict=None)
    (R / "receipt.json").write_text(json.dumps(rec, indent=1))
    queue_log(f"train_{site}_{res} {status} {int(time.monotonic() - t0)}s")
    STATE[key].update(note=f"GeoGS {status}, {rec['wall_seconds'] / 60:.0f}분, GPU 최대 {(peak - idle) / 1024:.1f} GB")
    write_progress(f"{key} GeoGS 학습 {status} ({rec['wall_seconds'] / 60:.0f}분, GPU {gpu})")
    return status


def post(site, gpu):
    res = "trust_LoD2"
    steps = [["bash", str(HERE.parent / "run_gpu.sh"), f"post_{site}_{res}", "post", site, res],
             ["bash", str(HERE.parent / "run_gpu.sh"), f"run_{site}_{res}", "run", site, res],
             ["bash", str(HERE.parent / "run_cpu.sh"), f"met_{site}_{res}_LoD2", "metrics_s1.py", site, "LoD2", res]]
    with open(SLOT, "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        for st in steps:
            rc = subprocess.run(st, env=dict(os.environ, GPU=str(gpu), CPUS="12", MEM="72g"), capture_output=True, text=True).returncode   # 72g: the GeoGS TSDF passed 46 GB (03:40)
            if rc != 0:
                fcntl.flock(lk, fcntl.LOCK_UN)
                stop(f"{site}/{res} 후처리 실패 {st[2]} (rc {rc})", run=f"{site}/{res}", step=st[2], rc=rc)
                return rc
        fcntl.flock(lk, fcntl.LOCK_UN)
    write_progress(f"{site}/{res} GeoGS 후처리·지표 끝")
    return 0


def worker(queue, qlock):
    while not STOP.is_set():
        with qlock:
            if not queue:
                return
            site = queue.pop(0)
        g = take_gpu(20000)
        if g is None:
            return
        try:
            st = train(site, g, 0)
            if st == "OOM" and not STOP.is_set():
                write_progress(f"{site}/trust_LoD2 GeoGS GPU 메모리 부족 — 같은 학습을 한 번 더 돌림")
                st = train(site, g, 1)
            if st != "PASS":
                stop(f"{site}/trust_LoD2 GeoGS 학습 {st}" + (" (두 번째 메모리 부족)" if st == "OOM" else ""), run=f"{site}/trust_LoD2", status=st)
                return
            post(site, g)
        finally:
            give_gpu(g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="+", default=None)
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()
    sites = [r["site"] for r in PLAN["runs"] if r["method"] == "geogs" and (not a.sites or r["site"] in a.sites)]
    write_progress(f"GeoGS 실행기 시작: {', '.join(sites)} (대기열 v2가 끝나기를 기다림)" if not a.no_wait else f"GeoGS 실행기 시작: {', '.join(sites)}")
    while not a.no_wait:
        s = (OUT / "progress.md").read_text()
        if "학습 대기열 v2 끝" in s:
            if "학습 대기열 v2 끝 (멈춤" in s:
                stop("23회 대기열이 멈춤 신호로 끝남")
                return
            break
        time.sleep(120)
    for site in sites:
        if not (OUT / "geogs" / site / "prep.json").exists():
            rc = subprocess.run(["bash", str(HERE.parent / "run_geogs_prep.sh"), site], env=dict(os.environ, SLOT="1")).returncode
            if rc != 0:
                stop(f"GeoGS 입력 {site} 실패 (rc {rc})", site=site)
                return
    ths = []
    for site in sites:
        th = threading.Thread(target=lambda s=site: (da3(s) == 0) or stop(f"GeoGS DA3 {s} 실패", site=s))
        th.start()
        ths.append(th)
        time.sleep(20)
    for th in ths:
        th.join()
    if STOP.is_set():
        return
    rc = scale(sites)
    write_progress(f"GeoGS DA3 척도 점검 rc={rc} (tables/geogs_da3_scale.md)")
    queue, qlock = [s for s in sites if not ((OUT / "stage1" / s / "trust_LoD2/receipt.json").exists()
                                             and json.loads((OUT / "stage1" / s / "trust_LoD2/receipt.json").read_text()).get("status") == "PASS")], threading.Lock()
    ws = [threading.Thread(target=worker, args=(queue, qlock)) for _ in (0, 1)]
    for w in ws:
        w.start()
        time.sleep(60)
    for w in ws:
        w.join()
    write_progress("GeoGS 실행기 끝" + (" (멈춤: logs/STOP_geogs.json)" if STOP.is_set() else ""))


if __name__ == "__main__":
    main()
