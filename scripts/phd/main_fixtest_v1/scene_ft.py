"""PHD-MAIN-FIXTEST-v1 9.1-6 (전체: scene F1 0.2 m / 0.5 m and the scene Chamfer distance) and 9.1-7 (학습 기록: wall time, GPU memory
peak, Gaussians, PSNR of the evaluation views) (jointbuildgs:dev, CPU; run_step_ft.sh).
  values      metrics json summary of metrics_s2 / metrics_s1 (f1_0.2, f1_0.5, chamfer_mean, chamfer_result_to_gt, chamfer_gt_to_result,
              n_gt, n_result, image_quality.psnr): this task FT/metrics, the method S1/metrics (B173 주변 too), the judgment-only-off method
              S3/metrics, stage 2's band removal S2/metrics
  records     receipt.json (wall_seconds, gpu_memory_used_mib.peak_minus_idle) and model/monitor/scalars.jsonl (last row: n, n_prior) of each
              run: FT/runs, S1/stage1, S0/stage0 (B173 주변 seeds)
Reading (order 9.2, one seed): F1 criterion = max(2.8 |s0 - s1| / sqrt 2, 300 / min(n_gt, n_result)) (%p), Chamfer criterion =
2.8 |s0 - s1| / sqrt 2 (m; no pooled band exists for the scene values). 확인 > 2 x criterion, 가능·근거 불완전 > criterion, else 같음.
  python scene_ft.py
Writes FT/tables/scene_ft.json and scene_ft.md. scientific_verdict: null."""
import json
import math
from pathlib import Path

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S0 = Path("/s0")
S1 = Path("/out")
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
CFG = json.loads(Path("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read_text())
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
CASES = [(s, p) for s in SITES for p in ("LoD2", "ALS")]
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
FIX = (("A", "판 A (읽기 L)"), ("AT", "판 A (읽기 T)"), ("B", "판 B"), ("AB", "함께 켠 판"))
MET = (("f1_0.2", "F1(0.2 m) %"), ("f1_0.5", "F1(0.5 m) %"), ("chamfer_mean", "장면 Chamfer m"))


def jl(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def run_dir(site, res):
    if res.startswith("fix"):
        return FTP / "runs" / site / res
    if res.startswith("nojudge_"):
        return S3 / "runs" / site / res
    if res.startswith("abl_band_"):
        return S2 / "runs" / site / res
    if site == "B173nb_b10" and res.startswith("prop_"):
        return S0 / "stage0" / f"b{1 if res.endswith('s0') else 2}_{'LoD2' if 'LoD2' in res else 'ALS'}"
    return S1 / "stage1" / site / res


def status_of(site, res):
    run = next((r for r in CFG["runs"] if r["site"] == site and r["result"] == res), None)
    if run is not None and not run["train"]:
        return "읽기 L과 같음" if "갈음" in run["why"] else ("관문" if "관문" in run["why"] else "학습 안 함")
    if res.startswith("fix"):
        rc = jl(FTP / "runs" / site / res / "receipt.json")
        if rc is None:
            return "결과 없음"
        if rc.get("status") != "PASS":
            return f"결과 없음({rc.get('status')})"
    return "있음"


def summary(site, res, prior):
    for base in (FTP / "metrics", S3 / "metrics", S1 / "metrics", S2 / "metrics"):
        f = base / site / f"{res}__{prior}.json"
        if f.exists():
            s = json.loads(f.read_text())["summary"]
            return dict(source=str(f).replace(str(PH), "PH").replace("/out", "S1"),
                        **{k: s.get(k) for k in ("f1_0.2", "f1_0.5", "chamfer_mean", "chamfer_result_to_gt", "chamfer_gt_to_result", "n_gt", "n_result")},
                        psnr=(s.get("image_quality") or {}).get("psnr"), ssim=(s.get("image_quality") or {}).get("ssim"))
    return None


def record(site, res):
    R = run_dir(site, res)
    rc = jl(R / "receipt.json")
    out = dict(run=str(R).replace(str(PH), "PH").replace("/out", "S1").replace("/s0", "S0"))
    if rc:
        out.update(wall_minutes=round(rc.get("wall_seconds", 0) / 60.0, 1), gpu_peak_gib=round((rc.get("gpu_memory_used_mib") or {}).get("peak_minus_idle", 0) / 1024.0, 2),
                   status=rc.get("status"), attempt=rc.get("attempt"))
    sc = R / "model/monitor/scalars.jsonl"
    if sc.exists():
        last = None
        for ln in sc.read_text().splitlines():
            if ln.strip():
                try:
                    last = json.loads(ln)
                except json.JSONDecodeError:
                    break
        if last:
            out.update(iteration=last.get("iteration"), gaussians=last.get("n"), gaussians_prior=last.get("n_prior"))
    return out


def read(fx, v0, v1, m, n):
    if fx is None or v0 is None or v1 is None:
        return dict(grade="—")
    share = m.startswith("f1")
    if share:
        fx, v0, v1 = 100 * fx, 100 * v0, 100 * v1
    mean = 0.5 * (v0 + v1)
    terms = {"case": 2.8 * abs(v0 - v1) / math.sqrt(2)}
    if share and n:
        terms["300/n"] = 300.0 / n
    crit = max(terms.values())
    diff = fx - mean
    g = "확인" if abs(diff) > 2 * crit else ("가능·근거 불완전" if abs(diff) > crit else "같음")
    side = "같음" if g == "같음" else ("나음" if (diff > 0) == share else "못함")
    return dict(grade=g, side=side, diff=diff, criterion=crit, terms=terms, mean=mean)


def main():
    E = {}
    for site, prior in CASES:
        res = {"s0": f"prop_{prior}_s0", "s1": f"prop_{prior}_s1", **{c: f"fix{c}_{prior}_s0" for c, _ in FIX}, "nojudge": f"nojudge_{prior}_s0",
               "ablband": {("B173nb_b10", "ALS"): "abl_band_ALS_s0", ("R1rep_b10", "LoD2"): "abl_band_LoD2_s0"}.get((site, prior))}
        e = dict(case=f"{SITE_KO[site]} {PRIOR_KO[prior]}", results={})
        for k, r in res.items():
            if r is None:
                continue
            st = status_of(site, r)
            x = dict(result=r, status=st)
            if st == "있음":
                x["summary"] = summary(site, r, prior)
                x["record"] = record(site, r)
            e["results"][k] = x
        s0, s1 = (e["results"]["s0"].get("summary") or {}), (e["results"]["s1"].get("summary") or {})
        for c, _ in FIX:
            x = e["results"][c]
            if x.get("summary"):
                n = min(x["summary"].get("n_gt") or 0, x["summary"].get("n_result") or 0)
                x["read"] = {m: read(x["summary"].get(m), s0.get(m), s1.get(m), m, n) for m, _ in MET}
        E[f"{site}/{prior}"] = e
    (FTP / "tables").mkdir(parents=True, exist_ok=True)
    (FTP / "tables/scene_ft.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", work="9.1-6, 9.1-7", rule=__doc__.split("\n\n")[0], cases=E,
                                                              scientific_verdict=None), indent=1, ensure_ascii=False, default=float))
    L = ["# 전체 지표와 학습 기록 (9.1의 6, 7) [이 발주에서 냄]", "",
         "칸 = 값 (읽기). F1은 %, Chamfer는 m(결과→참값과 참값→결과의 평균). 읽기는 발주 9.2(씨앗 하나): 기준 = 2.8 × |씨앗 0 − 씨앗 1| ÷ √2, "
         "F1은 300 ÷ min(참값 점, 결과 점)과 큰 쪽. 장면 지표에는 모은 흔들림 폭이 없다.", "",
         "| 경우 | 값 | 본 방법 씨앗 0 | 씨앗 1 | " + " | ".join(lab for _, lab in FIX) + " | 판정만 끈 본 방법 | 허용 구간 없애기 |", "|" + "---|" * (4 + len(FIX) + 2)]
    for u, e in E.items():
        for m, mko in MET:
            def v(k):
                x = e["results"].get(k)
                if x is None:
                    return "—"
                if x["status"] != "있음":
                    return x["status"]
                s = (x.get("summary") or {}).get(m)
                if s is None:
                    return "—"
                txt = f"{100 * s:.1f}" if m.startswith("f1") else f"{s:.3f}"
                rr = (x.get("read") or {}).get(m)
                if rr and rr.get("grade") not in (None, "—", "같음"):
                    txt += f" ({rr['grade']}, {rr['side']})"
                elif rr and rr.get("grade") == "같음":
                    txt += " (같음)"
                return txt
            L.append(f"| {e['case']} | {mko} | {v('s0')} | {v('s1')} | " + " | ".join(v(c) for c, _ in FIX) + f" | {v('nojudge')} | {v('ablband')} |")
    L += ["", "## 학습 기록", "", "| 경우 | 결과 | 걸린 시간 (분) | GPU 메모리 최대 (GiB) | 가우시안 (사전 정보 출신) | 평가 영상 PSNR (dB) |", "|---|---|---:|---:|---|---:|"]
    for u, e in E.items():
        for k in ("s0", "s1") + tuple(c for c, _ in FIX):
            x = e["results"].get(k)
            if not x or x["status"] != "있음":
                continue
            r, s = x.get("record") or {}, x.get("summary") or {}
            g = f"{r['gaussians']:,} ({r['gaussians_prior']:,})" if r.get("gaussians") is not None else "—"
            L.append(f"| {e['case']} | {x['result']} | {r.get('wall_minutes', '—')} | {r.get('gpu_peak_gib', '—')} | {g} | "
                     + (f"{s['psnr']:.2f}" if s.get("psnr") is not None else "—") + " |")
    (FTP / "tables/scene_ft.md").write_text("\n".join(L) + "\n")
    print("scene_ft done")


if __name__ == "__main__":
    main()
