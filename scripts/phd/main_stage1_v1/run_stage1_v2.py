#!/usr/bin/env python3
"""PHD-MAIN-STAGE1-v1 queue runner v2 (host orchestration only, stdlib). The trainings are those of run_stage1.py: its command(),
train() and stop signals are imported unchanged. Only the post steps are scheduled differently, after the post failure of 2026-10-07
16:37 (the TSDF renders of B173nb_b10/imgonly_s0 asked 7 GiB on a GPU shared with a training that had 6.9 GiB free; the first runner
then stopped its queue as designed):
  - the GPU post steps of a run (gpu_s1.py post and run) are done by its GPU worker on its own idle GPU right after the training and
    before the next training there (no GPU shared with a training); a CUDA out-of-memory there is run once more, a second one or any
    other failure stops (logs/STOP_v2.json)
  - the CPU steps (metrics_s1.py on the run's units) go to the post worker under the slot lock (two GPU jobs + one other job at most)
  - a worker takes its next job (pending post steps first, then the next training) only when its GPU is idle (< 2,000 MiB used): the
    trainings left by the first runner finish undisturbed and the first GPU to become idle gets the pending post steps
  - trainings of the first runner still running at the start are adopted (their receipts awaited, then their post steps); an adopted
    run that ends out of memory is trained once more here, any other failure stops
  - pending first: runs with a PASS receipt whose post / run / metrics outputs are missing
  - progress.md end line: '학습 대기열 v2 끝'
  - options added 2026-10-08 for B173_b0 (decided by the user after its two out-of-memory stops; the training computation is unchanged):
    --cpu-images <site>: the training images of that site stay in host memory ('--data_device cpu' appended to the command; ~1.3 GB of
    GPU memory freed), --gpu1 <site>/<result>: those runs only on GPU 1 (no resident desktop process there), --keep-going <site>: a
    second out-of-memory of that site is recorded as 'no result' and the queue goes on instead of stopping

  python3 run_stage1_v2.py [--sites <site> ...] [--only <site>/<result> ...] [--cpu-images <site> ...] [--gpu1 <site>/<result> ...] [--keep-going <site> ...]
scientific_verdict: null."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_stage1 as rs  # noqa: E402

OUT, HERE = rs.OUT, rs.HERE
PENDING, ADOPT, POSTQ = [], [], []
LK = threading.Lock()
DONE = threading.Event()
OPT = dict(cpu_images=set(), gpu1=set(), keep_going=set())
NO_RESULT = []
_command = rs.command


def command_v2(run, gpu):
    """rs.command with '--data_device cpu' for the sites of --cpu-images (rs.train looks rs.command up at call time)."""
    name, cmd = _command(run, gpu)
    return name, (cmd + ["--data_device", "cpu"] if run["site"] in OPT["cpu_images"] else cmd)


rs.command = command_v2


def units_of(run):
    return ["LoD2", "ALS"] if run["method"] == "imgonly" else [run["scene_prior"]]


def rdir(run):
    return OUT / "stage1" / run["site"] / run["result"]


def receipt(run):
    f = rdir(run) / "receipt.json"
    return json.loads(f.read_text()) if f.exists() else None


def gpu_done(run):
    return (rdir(run) / "post/post.json").exists() and (rdir(run) / "gpu/run.json").exists()


def metrics_done(run):
    return all((OUT / "metrics" / run["site"] / f"{run['result']}__{u}.json").exists() for u in units_of(run))


def stop(**kw):
    (OUT / "logs/STOP_v2.json").write_text(json.dumps(dict(at=rs.now(), **kw), indent=1))
    rs.STOP.set()


def wait_idle(g, why):
    noted = False
    while not rs.STOP.is_set():
        u = rs.gpu_used(g)
        if u == u and u < 2000:
            return True
        if not noted:
            rs.write_progress(f"GPU {g}: {why} — GPU가 빌 때까지 기다림 ({u:.0f} MiB 사용 중)")
            noted = True
        time.sleep(60)
    return False


def gpu_post(run, g):
    site, res = run["site"], run["result"]
    for mode in ("post", "run"):
        tag = f"{mode}_{site}_{res}"
        for attempt in (0, 1):
            if not wait_idle(g, f"{site}/{res} 후처리 {mode} 전"):
                return False
            with open(OUT / "logs/tsdf.lock", "a") as tl:                # one TSDF at a time (standing rule), added 2026-10-08
                fcntl.flock(tl, fcntl.LOCK_EX)
                rc = subprocess.run(["bash", str(HERE.parent / "run_gpu.sh"), tag, mode, site, res], env=dict(os.environ, GPU=str(g)),
                                    capture_output=True, text=True).returncode
                fcntl.flock(tl, fcntl.LOCK_UN)
            if rc == 0:
                break
            oom = "out of memory" in (OUT / "logs" / f"{tag}.log").read_text(errors="ignore").lower()
            if oom and attempt == 0:
                rs.write_progress(f"{site}/{res} 후처리 {mode} GPU 메모리 부족 — 한 번 더 돌림 (GPU {g})")
                continue
            rs.write_progress(f"{site}/{res} 후처리 {mode} 실패 (rc {rc}{', 두 번째 메모리 부족' if oom else ''}) — 멈추고 여쭙는다")
            stop(run=f"{site}/{res}", step=tag, rc=rc, oom=oom)
            return False
    return True


def post_worker():
    while not (rs.STOP.is_set() and not POSTQ):
        with LK:
            run = POSTQ.pop(0) if POSTQ else None
        if run is None:
            if DONE.is_set():
                return
            time.sleep(10)
            continue
        site, res = run["site"], run["result"]
        with open(rs.SLOT, "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            ok = True
            for u in units_of(run):
                tag = f"met_{site}_{res}_{u}"
                rc = subprocess.run(["bash", str(HERE.parent / "run_cpu.sh"), tag, "metrics_s1.py", site, u, res], env=dict(os.environ, CPUS="12"),
                                    capture_output=True, text=True).returncode
                if rc != 0:
                    rs.write_progress(f"{site}/{res} 지표 실패: {tag} (rc {rc}) — 멈추고 여쭙는다")
                    stop(run=f"{site}/{res}", step=tag, rc=rc)
                    ok = False
                    break
            fcntl.flock(lk, fcntl.LOCK_UN)
        if ok:
            rs.write_progress(f"{site}/{res} 후처리·지표 끝")


def allowed(run, g):
    return g == 1 or f"{run['site']}/{run['result']}" not in OPT["gpu1"]


def next_job(queue, g=None):
    """('post', run) for pending post steps (adopted runs whose receipt came), ('train', run), ('wait', None) or (None, None).
    A training restricted to GPU 1 (--gpu1) is skipped by the GPU 0 worker; when only such trainings are left that worker ends."""
    with LK:
        for run in list(ADOPT):
            rec = receipt(run)
            if rec is None or rec.get("finished_at") is None:
                continue
            ADOPT.remove(run)
            if rec["status"] == "PASS":
                PENDING.append(run)
            elif rec["status"] == "OOM" and not run.get("_retried"):
                run["_retried"] = True
                queue.insert(0, run)
                rs.write_progress(f"{run['site']}/{run['result']} (첫 실행기) GPU 메모리 부족 — 한 번 더 돌림")
            else:
                stop(run=f"{run['site']}/{run['result']}", reason=f"adopted run {rec['status']}")
                return None, None
        if PENDING:
            return "post", PENDING.pop(0)
        for i, run in enumerate(queue):
            if g is None or allowed(run, g):
                return "train", queue.pop(i)
        if ADOPT:
            return "wait", None
    return None, None          # nothing this GPU may take (only GPU-1 trainings left for the GPU 0 worker): the worker ends


def gpu_worker(g, queue):
    while not rs.STOP.is_set():
        if not wait_idle(g, "다음 일 전"):          # a job is taken only by a worker whose GPU is idle (the first idle GPU gets it)
            return
        kind, run = next_job(queue, g)
        if kind is None:
            return
        if kind == "wait":
            time.sleep(60)
            continue
        if kind == "train":
            rs.RUNNING[g] = f"{run['site']}/{run['result']}"
            st = rs.train(run, g, 1 if run.get("_retried") else 0)
            if st == "OOM" and not run.get("_retried") and not rs.STOP.is_set():
                rs.write_progress(f"{run['site']}/{run['result']} GPU 메모리 부족 — 같은 학습을 한 번 더 돌림")
                st = rs.train(run, g, 1)
            rs.RUNNING[g] = None
            if st == "OOM" and run["site"] in OPT["keep_going"]:
                NO_RESULT.append(f"{run['site']}/{run['result']}")
                rs.write_progress(f"{run['site']}/{run['result']} 두 번째 GPU 메모리 부족 — 결과 없음으로 적고 다음 학습으로(사용자 결정 10-08)")
                continue
            if st != "PASS":
                rs.write_progress(f"{run['site']}/{run['result']} 실행 조건이 깨짐({st}) — 멈추고 여쭙는다")
                stop(run=f"{run['site']}/{run['result']}", reason=st)
                return
        if not gpu_done(run) and not gpu_post(run, g):
            return
        if not metrics_done(run):
            with LK:
                POSTQ.append(run)
        else:
            rs.write_progress(f"{run['site']}/{run['result']} 후처리·지표 끝")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="+", default=None)
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--cpu-images", nargs="+", default=[])
    ap.add_argument("--gpu1", nargs="+", default=[])
    ap.add_argument("--keep-going", nargs="+", default=[])
    a = ap.parse_args()
    OPT.update(cpu_images=set(a.cpu_images), gpu1=set(a.gpu1), keep_going=set(a.keep_going))
    running = set(subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split())
    queue = []
    for r in rs.PLAN["runs"]:
        if r["method"] == "geogs" or (a.sites and r["site"] not in a.sites) or (a.only and f"{r['site']}/{r['result']}" not in a.only):
            continue
        r = dict(r)
        name = f"jbgs-s1t-{r['site']}-{r['result']}".replace("_", "-").lower()[:60]
        rec = receipt(r)
        if name in running:
            ADOPT.append(r)
        elif rec is not None and rec.get("status") == "PASS":
            if not gpu_done(r):
                PENDING.append(r)
            elif not metrics_done(r):
                POSTQ.append(r)
        else:
            queue.append(r)
    rs.write_progress(f"학습 대기열 v2 시작: 학습 {len(queue)}회, 이어받은 학습 {len(ADOPT)} ({', '.join(x['site'] + '/' + x['result'] for x in ADOPT)}), "
                      f"남은 후처리 {len(PENDING)} ({', '.join(x['site'] + '/' + x['result'] for x in PENDING)}), 남은 지표 {len(POSTQ)}")
    pw = threading.Thread(target=post_worker)
    pw.start()
    ws = [threading.Thread(target=gpu_worker, args=(g, queue)) for g in (0, 1)]
    for w in ws:
        w.start()
        time.sleep(60)
    for w in ws:
        w.join()
    DONE.set()
    pw.join()
    rs.write_progress("학습 대기열 v2 끝" + (" (멈춤: logs/STOP_v2.json)" if rs.STOP.is_set() else "") + (f" (결과 없음: {', '.join(NO_RESULT)})" if NO_RESULT else ""))


if __name__ == "__main__":
    main()
