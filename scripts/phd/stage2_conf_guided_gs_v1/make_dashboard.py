"""Stage-2 progress dashboard (ORDER_ko_v1 section 7): static index.html + data.js regenerated from the run monitors.
Stdlib only; run in jointbuildgs:dev with the payload at /s2:

  python make_dashboard.py [--loop 120]        # --loop: regenerate every N s until both queues have ended

Reads runs/<COND>/{condition.json, receipt.json, model/monitor/*, model/metric.txt}, logs/train_<COND>.log (progress of
the official O runs, which have no monitor) and logs/queue_gpu*.jsonl. Writes dashboard/{index.html, data.js, snaps/}
(snapshot PNGs are hard-linked). Serve only dashboard/ (port 8887). scientific_verdict: null."""
import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import time
from pathlib import Path

S2 = Path("/s2")
OUT = S2 / "dashboard"
CONDS = ["P_M_B", "P_M_N", "P_L_B", "P_L_N", "P0_M_B", "P0_M_N", "P0_L_B", "P0_L_N", "O_M_B", "O_M_N", "I"]
PROG = re.compile(r"Training progress:\s+\d+%\|[^|]*\|\s*(\d+)/(\d+)")


def jl(p):
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def num(x):
    try:
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def log_progress(cond):
    p = S2 / "logs" / f"train_{cond}.log"
    if not p.exists():
        return None, None
    with p.open("rb") as f:
        f.seek(max(0, p.stat().st_size - 20000))
        tail = f.read().decode(errors="replace")
    m = PROG.findall(tail)
    return (int(m[-1][0]), int(m[-1][1])) if m else (None, None)


def link(src, dst):
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def condition(cond, queue_state):
    run = S2 / "runs" / cond
    c = json.loads((run / "condition.json").read_text())
    mon = run / "model" / "monitor"
    d = dict(name=cond, mode=c["mode"], prior=c.get("prior"), scene=c["scene"], tau_v=c.get("tau_v"),
             queue=queue_state.get(cond, {}))
    rc = run / "receipt.json"
    d["receipt"] = json.loads(rc.read_text()) if rc.exists() else None
    if d["receipt"]:
        d["receipt"] = {k: d["receipt"].get(k) for k in ("status", "exit_code", "seconds", "started_at", "finished_at", "gpu")}
    it, total = log_progress(cond)
    d["iteration"], d["total"] = it, total
    started = d["queue"].get("started_at")
    if it and total and started and not d["receipt"]:
        el = (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(started)).total_seconds()
        d["elapsed_s"] = el
        d["eta_s"] = el / max(it, 1) * (total - it)
    sc = jl(mon / "scalars.jsonl")
    keep = ("iteration", "rgb", "mvs", "prior", "total", "n", "n_prior", "n_image", "n_locked", "n_prior_free", "added",
            "removed", "n_locked_below_floor", "peak_cuda_gb")
    d["scalars"] = [{k: r.get(k) for k in keep} for r in sc if r.get("iteration", 0) % 500 == 0 or r.get("iteration") == 1]
    d["E"] = [{k: r.get(k) for k in ("iteration", "n", "n_prior", "n_locked", "n_prior_unseen", "n_prior_off_prior",
                                     "n_newly_locked", "n_released", "E_mean_prior")} for r in jl(mon / "E.jsonl")]
    faces = {}
    fp = mon / "faces.csv"
    if fp.exists():
        with fp.open() as f:
            for r in csv.DictReader(f):
                faces.setdefault(r["face"], []).append(dict(it=int(r["iteration"]), cov=num(r["cov"]), d=num(r["d"]),
                                                            e=num(r["e"]), g=num(r["g"]), g_nmad=num(r["g_nmad"]), label=r["label"]))
    d["faces"] = faces
    d["checklist"] = jl(mon / "checklist.jsonl")
    stop = mon / "stop.json"
    d["stop"] = json.loads(stop.read_text()) if stop.exists() else None
    mt = run / "model" / "metric.txt"
    d["metrics"] = []
    if mt.exists():
        for tok in mt.read_text().split():
            p = tok.split("_")
            if len(p) == 4:
                d["metrics"].append(dict(it=int(p[0]), psnr=num(p[1]), ssim=num(p[2]), lpips=num(p[3])))
    snaps = {}
    for png in sorted(mon.glob("snap_*.png")) if mon.exists() else []:
        m = re.match(r"snap_(\d+)_(.+)\.png", png.name)
        if m:
            rel = Path("snaps") / cond / png.name
            link(png, OUT / rel)
            snaps.setdefault(m.group(1), []).append(dict(view=m.group(2), src=str(rel)))
    d["snaps"] = snaps
    return d


def queue_states():
    st = {}
    for q in sorted((S2 / "logs").glob("queue_gpu*.jsonl")):
        gpu = q.stem.replace("queue_gpu", "")
        for r in jl(q):
            c = r.get("cond")
            if not c:
                continue
            s = st.setdefault(c, {"gpu": gpu})
            ev = r.get("event")
            if ev == "start":
                s.update(state="running", started_at=r["at"])
            elif ev == "wait_running":
                s.update(state="running", started_at=s.get("started_at") or r["at"])
            elif ev == "end":
                s.update(state="done" if r.get("exit_code") == 0 else "failed", ended_at=r["at"])
            elif ev in ("skip_passed", "waited"):
                s.update(state="done" if (ev == "skip_passed" or r.get("passed")) else "failed", ended_at=r["at"])
            elif ev == "render_eval":
                s.update(render_eval=r.get("exit_code"))
    return st


def queue_active():
    return any((S2 / "logs" / f"queue_gpu{g}.lock").exists() for g in (0, 1))


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    qs = queue_states()
    # first start time of a condition = the earliest start among its queue events (runs adopted by a later queue)
    for q in sorted((S2 / "logs").glob("queue_gpu*.jsonl")):
        for r in jl(q):
            if r.get("event") == "start" and r.get("cond") in qs:
                s = qs[r["cond"]]
                s["started_at"] = min(s.get("started_at") or r["at"], r["at"])
    data = dict(generated_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"), queue_active=queue_active(),
                conditions=[condition(c, qs) for c in CONDS if (S2 / "runs" / c / "condition.json").exists()],
                lambda_selection=json.loads((S2 / "logs/lambda_selection.json").read_text())
                if (S2 / "logs/lambda_selection.json").exists() else None,
                issues=jl(S2 / "logs" / "issues.jsonl")[-20:])
    tmp = OUT / "data.js.tmp"
    tmp.write_text("window.S2DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    tmp.replace(OUT / "data.js")
    src = Path(__file__).resolve().parent / "dashboard_index.html"
    shutil.copy2(src, OUT / "index.html")
    return data


ap = argparse.ArgumentParser()
ap.add_argument("--loop", type=int, default=0)
a = ap.parse_args()
while True:
    d = build()
    print(d["generated_at"], "conditions", len(d["conditions"]), "queue_active", d["queue_active"], flush=True)
    if not a.loop or not d["queue_active"]:
        break
    time.sleep(a.loop)
