"""PHD-MAIN-FIXTEST-v1 14-9 (학습이 끝났는지, 걸린 시간과 자원; jointbuildgs:dev, CPU; run_step_ft.sh): one row per run of the configuration
(trained or not), from the configuration (train, why), the receipts of every try (runs/<site>/<result>[_try1_*]/receipt.json: status, wall
seconds, GPU memory peak over idle, attempt), the last monitor row (Gaussians, those from the prior), post_host_memory.json (GPU post seconds,
host memory low), logs/queue.log (the CPU post steps' seconds) and the scene metrics summary (PSNR of the evaluation views).
  python runs_table_ft.py
Writes FT/tables/runs_ft.json and runs_ft.md. scientific_verdict: null."""
import json
import re
from pathlib import Path

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
CFG = json.loads(Path("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read_text())
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
FIX_KO = {"A": "판 A 읽기 L", "AT": "판 A 읽기 T", "B": "판 B", "AB": "함께 켠 판"}
STEPS = ("nan", "met", "meas", "bands", "supp", "fates")


def jl(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def last_row(f):
    last = None
    if f.exists():
        for ln in f.read_text().splitlines():
            if ln.strip():
                try:
                    last = json.loads(ln)
                except json.JSONDecodeError:
                    break
    return last


def main():
    q = (FTP / "logs/queue.log").read_text().splitlines()
    rows = []
    for run in CFG["runs"]:
        site, res, prior = run["site"], run["result"], run["prior"]
        fix = res.split("_")[0][3:]
        e = dict(site=site, result=res, case=f"{SITE_KO[site]} {PRIOR_KO[prior]}", fix=FIX_KO.get(fix, fix), train=run["train"], why=run["why"], tries=[])
        if run["train"]:
            base = FTP / "runs" / site
            dirs = sorted(base.glob(f"{res}_try*")) + [base / res]
            for d in dirs:
                rc = jl(d / "receipt.json")
                if rc is None:
                    continue
                t = dict(dir=d.name, status=rc.get("status"), attempt=rc.get("attempt"), wall_minutes=round(rc.get("wall_seconds", 0) / 60.0, 1),
                         gpu_peak_gib=round((rc.get("gpu_memory_used_mib") or {}).get("peak_minus_idle", 0) / 1024.0, 2), gpu=rc.get("gpu"),
                         started=rc.get("started_at"), finished=rc.get("finished_at"))
                if rc.get("status") == "OOM" and rc.get("oom_record"):
                    o = rc["oom_record"]
                    t["oom"] = dict(iteration=o.get("iteration"), tried_gib=re.findall(r"allocate ([0-9.]+ GiB)", o.get("error", ""))[:1],
                                    n_radius_ge_10000=o.get("n_radius_ge_10000"), radius_max=o.get("radius_max"))
                lr = last_row(d / "model/monitor/scalars.jsonl")
                if lr and rc.get("status") == "PASS":
                    t.update(gaussians=lr.get("n"), gaussians_prior=lr.get("n_prior"),
                             prior_opacity_median=(lr.get("opacity_q_prior") or [None, None])[1])
                pm = jl(d / "post_host_memory.json")
                if pm:
                    t["gpu_post_seconds"] = {k: v.get("seconds") for k, v in pm.items()}
                    t["host_min_available_gb"] = min((v.get("host_min_available_gb") or 1e9) for v in pm.values())
                m = jl(FTP / "metrics" / site / f"{res}__{prior}.json")
                if m and rc.get("status") == "PASS":
                    t["psnr"] = (m["summary"].get("image_quality") or {}).get("psnr")
                if rc.get("status") == "PASS":
                    secs = 0.0
                    for st in STEPS:
                        hits = [ln for ln in q if f" {st}_{site}_{res} rc=" in ln]
                        if hits:
                            mm = re.search(r"rc=(\d+) (\d+)s", hits[-1])
                            if mm:
                                secs += float(mm.group(2))
                    t["cpu_post_minutes"] = round(secs / 60.0, 1)
                e["tries"].append(t)
        rows.append(e)
    (FTP / "tables/runs_ft.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", rows=rows, scientific_verdict=None), indent=1, ensure_ascii=False))
    L = ["# 학습이 끝났는지, 걸린 시간과 자원 [이 발주에서 냄]", "",
         "| 경우 | 판 | 결과 | 학습 (분) | GPU | GPU 메모리 최대 (GiB) | GPU 후처리 (초: post·run) | 지표 단계 (분) | 가우시안 (사전 정보 출신) | 사전 정보 출신 불투명도 중앙값 | 평가 영상 PSNR (dB) |",
         "|---|---|---|---:|---:|---:|---|---:|---|---:|---:|"]
    for e in rows:
        if not e["train"]:
            L.append(f"| {e['case']} | {e['fix']} | 학습 안 함: {e['why']} | — | — | — | — | — | — | — | — |")
            continue
        for t in e["tries"]:
            g = f"{t['gaussians']:,} ({t['gaussians_prior']:,})" if t.get("gaussians") is not None else "—"
            gp = t.get("gpu_post_seconds") or {}
            st = t["status"] + (f" (시도 {t['attempt']})" if (t.get("attempt") or 1) > 1 else "")
            if t.get("oom"):
                st += f": {t['oom']['iteration']:,}회째 메모리 부족({', '.join(t['oom']['tried_gib'])} 요청)"
            L.append(f"| {e['case']} | {e['fix']} | {st} | {t['wall_minutes']} | {t.get('gpu', '—')} | {t['gpu_peak_gib']} | "
                     + (f"{gp.get('post', 0):.0f}·{gp.get('run', 0):.0f}" if gp else "—") + f" | {t.get('cpu_post_minutes', '—')} | {g} | "
                     + (f"{t['prior_opacity_median']:.2f}" if t.get("prior_opacity_median") is not None else "—") + " | "
                     + (f"{t['psnr']:.2f}" if t.get("psnr") is not None else "—") + " |")
    (FTP / "tables/runs_ft.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
