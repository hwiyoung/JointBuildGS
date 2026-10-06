#!/usr/bin/env python3
"""Stage-0 trial trainings of fork r12 with the stop-signal watcher (host orchestration only, stdlib; PHD-MAIN-STAGE0-v1 5.4).

  python3 run_stage0.py --batch 1          # seed of configs stage0_v1.json stage0.batches.1, LoD2 on GPU 0 and ALS on GPU 1 at once
  python3 run_stage0.py --batch 2          # only after batch 1 ended without a stop signal (checked here)
  python3 run_stage0.py --batch 1 --priors ALS --alloc-conf expandable_segments:True --tag rerun
                                           # 2026-10-06 user decision: b1_ALS stopped by GPU out-of-memory at the re-read of
                                           # 15,000; run again with the allocator setting only (no code or method change);
                                           # batch 2 with the same setting

Command = run_fork_v6.command() (r12, rule auto, all switches on, values of r10) with the training schedule of the config
(30,000 iterations, logs every 100, snapshots, dump and saves). The watcher reads each run's monitor/scalars.jsonl every 30 s:
  - progress.md every 1,000 iterations (iteration, seconds per 1,000 iterations since the previous mark, expected end);
  - the stop signals of the config: a non-finite loss term; at a multiple of 1,000 >= 2,000 the prior-origin Gaussians'
    median opacity < 0.05 and share with opacity >= 0.5 < 0.05 -> docker stop of that run, stop.json, progress.md;
  - nvidia-smi memory.used of the run's GPU (peak minus the value before the start) every 30 s.
After a run: an error signal when the exit code != 0 or no point cloud at 30,000. Receipts: stage0/<run>/receipt.json.
Outputs <P>/stage0/<batch>_<prior>/model/..., logs/stage0_<run>.log. scientific_verdict: null."""
import argparse
import datetime as dt
import json
import math
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import progress  # noqa: E402
import run_fork_v6 as rf  # noqa: E402

P, REPO = rf.P, rf.REPO
SC = rf.SCFG["stage0"]
SITE = SC["site"]
INPUTS = "fork_inputs/s61"


def schedule():
    r = SC["records"]
    its = int(SC["iterations"])
    return ["--iterations", str(its), "--test_iterations", *map(str, r["test_iterations"]), "--save_iterations", *map(str, r["save_iterations"]),
            "--jbgs_log_interval", str(r["log_interval"]), "--jbgs_readout_interval", str(r["readout_interval"]),
            "--jbgs_snapshot_iterations", *map(str, r["snapshot_iterations"]), "--jbgs_dump_iterations", *map(str, r["dump_iterations"])]


def gpu_used(gpu):
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", str(gpu)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return float(out.splitlines()[0])
    except Exception:
        return float("nan")


def stop_signal(row):
    """config stage0.stop_signals (nan, opacity_collapse) on one scalars row; None or the reason."""
    for k, v in row.items():
        if k in ("rgb", "mvs", "prior", "normal", "dist", "total") and isinstance(v, (int, float)) and not math.isfinite(v):
            return f"non-finite loss term {k} at {row['iteration']}"
    it = int(row["iteration"])
    if it >= 2000 and it % 1000 == 0:
        q = row.get("opacity_q_prior"); share = row.get("opacity_share_ge05_prior")
        if q is not None and share is not None and q[1] < 0.05 and share < 0.05:
            return f"opacity collapse of prior-origin Gaussians at {it}: median {q[1]:.4f}, share >= 0.5 {share:.4f}"
    return None


class Run:
    def __init__(self, batch, prior, seed, alloc_conf=None):
        self.name = f"b{batch}_{prior}"; self.prior = prior; self.seed = seed
        self.gpu = SC["priors"][prior]["gpu"]
        self.rdir = P / "stage0" / self.name
        if self.rdir.exists():
            self.rdir.rename(self.rdir.parent / f"{self.name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
        self.rdir.mkdir(parents=True)
        self.model = f"/p/stage0/{self.name}/model"
        self.alloc_conf = alloc_conf
        self.cmd = rf.command(f"s0-{self.name}", SITE, prior, INPUTS, self.model, self.gpu, 8, switch=None, rule="auto", schedule=schedule(), seed=seed,
                              alloc_conf=alloc_conf)
        self.log = P / "logs" / f"stage0_{self.name}.log"
        if self.log.exists():       # keep the log of an earlier run of the same name (the first b1_ALS log was overwritten before this)
            self.log.rename(self.log.with_name(f"stage0_{self.name}_old_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.log"))
        self.idle_mem = gpu_used(self.gpu)
        self.peak_mem = self.idle_mem
        self.marks = []                 # (iteration, monotonic time)
        self.n_rows = 0; self.stop = None; self.proc = None

    def start(self):
        self.t0 = time.monotonic(); self.start_at = dt.datetime.now().astimezone().isoformat()
        self.fh = self.log.open("w"); self.fh.write(" ".join(self.cmd) + "\n\n"); self.fh.flush()
        self.proc = subprocess.Popen(self.cmd, stdout=self.fh, stderr=subprocess.STDOUT)
        self.marks.append((0, self.t0))

    def scalars(self):
        f = self.rdir / "model/monitor/scalars.jsonl"
        if not f.exists():
            return []
        lines = f.read_text().splitlines()
        new = lines[self.n_rows:]
        self.n_rows = len(lines)
        out = []
        for l in new:
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                self.n_rows -= 1          # a half-written last line: read it again next time
                break
        return out

    def poll(self, total_its):
        self.peak_mem = max(self.peak_mem, gpu_used(self.gpu))
        for row in self.scalars():
            it = int(row["iteration"])
            reason = stop_signal(row)
            if reason and self.stop is None:
                self.stop = dict(iteration=it, reason=reason, row=row, at=dt.datetime.now().astimezone().isoformat())
                subprocess.run(["docker", "stop", "-t", "30", self.cmd[self.cmd.index("--name") + 1]], capture_output=True)
                (self.rdir / "stop.json").write_text(json.dumps(dict(**self.stop, scientific_verdict=None), indent=1))
                progress.update_training(self.name, it, "-", "멈춤", f"멈춤 신호: {reason}")
                progress_note(f"{self.name} 멈춤 신호: {reason}")
            if it % 1000 == 0 and it > 0 and (not self.marks or it > self.marks[-1][0]):
                now = time.monotonic()
                i0, t0 = self.marks[-1]
                spk = (now - t0) / max(it - i0, 1) * 1000.0
                left = (total_its - it) / 1000.0 * spk
                end = (dt.datetime.now() + dt.timedelta(seconds=left)).strftime("%m-%d %H:%M")
                self.marks.append((it, now))
                note = f"GPU {self.gpu}, 씨앗 {self.seed}, 가우시안 {row['n']:,} (사전 {row['n_prior']:,}, 보호 {row['n_locked']:,}), 사전 불투명도 중앙값 {row['opacity_q_prior'][1]:.2f}"
                progress.update_training(self.name, it, f"{spk:.0f}", end, note)
                if it == 1000:   # order 3: after the first 1,000 iterations re-estimate the 30,000 from that speed
                    hrs = spk * total_its / 1000.0 / 3600.0
                    st_ = progress.load()
                    st_["estimate"] += (f" | {self.name} 첫 1,000회 다시 계산({progress.now()}): 1,000회당 {spk:.0f}초 -> 30,000회 약 {hrs:.1f}시간,"
                                        f" 이 학습 끝 예상 {end}")
                    progress.save(st_)
        return self.proc.poll()

    def finish(self, rc):
        self.fh.close()
        its = int(SC["iterations"])
        pc = self.rdir / f"model/point_cloud/iteration_{its}/point_cloud.ply"
        err = None
        if self.stop is None and (rc != 0 or not pc.exists()):
            err = f"exit code {rc}, point cloud at {its}: {pc.exists()}"
        rec = dict(task_id="PHD-MAIN-STAGE0-v1", run=self.name, fork="r12", source=str(rf.SRC.relative_to(REPO)), site=SITE, prior=self.prior,
                   seed=self.seed, gpu=self.gpu, pytorch_cuda_alloc_conf=self.alloc_conf, image=rf.IMG, image_id=rf.image_id(), command=self.cmd, started_at=self.start_at,
                   finished_at=dt.datetime.now().astimezone().isoformat(), wall_seconds=round(time.monotonic() - self.t0, 1), exit_code=rc,
                   gpu_memory_used_mib=dict(idle_before=self.idle_mem, peak=self.peak_mem, peak_minus_idle=self.peak_mem - self.idle_mem),
                   marks=[dict(iteration=i, seconds=round(t - self.t0, 1)) for i, t in self.marks],
                   stop_signal=self.stop, error=err, status="STOPPED" if self.stop else ("FAILED" if err else "PASS"), scientific_verdict=None)
        (self.rdir / "receipt.json").write_text(json.dumps(rec, indent=1))
        if err:
            (self.rdir / "stop.json").write_text(json.dumps(dict(iteration=None, reason=f"error: {err}", scientific_verdict=None), indent=1))
            progress_note(f"{self.name} 오류로 멈춤: {err}")
        progress.update_training(self.name, self.marks[-1][0] if self.marks else 0, "-", "끝" if rec["status"] == "PASS" else rec["status"],
                                 f"{rec['status']}, 벽시계 {rec['wall_seconds'] / 60:.1f}분")
        return rec


def progress_note(text):
    s = progress.load(); s["notes"].append(f"{progress.now()} {text}"); progress.save(s)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--batch", required=True, choices=["1", "2"])
    ap.add_argument("--priors", nargs="+", default=["LoD2", "ALS"], choices=["LoD2", "ALS"])
    ap.add_argument("--alloc-conf", default=None, help="PYTORCH_CUDA_ALLOC_CONF of the runs (allocator only)")
    ap.add_argument("--tag", default="", help="suffix of the batch record (batch<k>_<tag>.json)")
    a = ap.parse_args()
    seed = int(SC["batches"][a.batch]["seed"])
    if a.batch == "2":
        for pr in ("LoD2", "ALS"):
            r = P / "stage0" / f"b1_{pr}" / "receipt.json"
            if not r.exists() or json.loads(r.read_text())["status"] != "PASS":
                raise SystemExit(f"batch 2 needs batch 1 without a stop signal ({r} missing or not PASS)")
    runs = [Run(a.batch, pr, seed, a.alloc_conf) for pr in a.priors]
    for r in runs:
        r.start()
    progress_note(f"묶음 {a.batch}{(' ' + a.tag) if a.tag else ''} 시작 (씨앗 {seed}{', ' + a.alloc_conf if a.alloc_conf else ''}): " + ", ".join(f"{r.name} GPU {r.gpu}" for r in runs))
    total = int(SC["iterations"])
    live = {r.name: r for r in runs}
    recs = {}
    while live:
        time.sleep(30)
        for nm in list(live):
            rc = live[nm].poll(total)
            if rc is not None:
                live[nm].poll(total)
                recs[nm] = live[nm].finish(rc)
                del live[nm]
    (P / "stage0" / f"batch{a.batch}{('_' + a.tag) if a.tag else ''}.json").write_text(json.dumps(dict(batch=a.batch, seed=seed, alloc_conf=a.alloc_conf,
                                                                         runs={k: v["status"] for k, v in recs.items()}, scientific_verdict=None), indent=1))
    print(json.dumps({k: (v["status"], v["wall_seconds"]) for k, v in recs.items()}))
    raise SystemExit(0 if all(v["status"] == "PASS" for v in recs.values()) else 1)


if __name__ == "__main__":
    main()
