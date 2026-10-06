#!/usr/bin/env python3
"""PHD-MAIN-STAGE0-v1 5.4 report tables (host, stdlib): markdown tables from the stage-0 receipts, monitor files, post.json and
the quick GT check.

  python3 tables_54.py > <payload>/tables/stage0_tables.md

T1 run outcome and time per run (wall, initialisation, re-reads, read-outs, the loop), GPU memory (torch peak allocated,
   max reserved, nvidia-smi peak minus idle), evaluation-view PSNR / SSIM / LPIPS (training_report, metric.txt)
T2 the scene at 30,000: Gaussians by origin, protected, opacity of prior-origin Gaussians, TSDF size
T3 quick GT check per run and split (roof dz median / NMAD, shares within 0.2 / 0.5 m), unseen-patch records
T4 spread: seed 1 minus seed 0 per prior and split
scientific_verdict: null."""
import json
from pathlib import Path

HERE = Path(__file__).resolve()
P = (HERE.parents[3].parent / "JointBuildGS-artifacts/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1").resolve()
RUNS = ["b1_LoD2", "b1_ALS", "b2_LoD2", "b2_ALS"]
KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
PARTS = [("all", "전체"), ("roof", "지붕"), ("wall", "벽"), ("changed", "바뀐 곳 (B173 날개)"), ("agreement", "일치 영역"),
         ("agreement_measured", "잰 일치"), ("agreement_unmeasured", "못 잰 일치"), ("unseen", "못 본 곳 (옛 벽 윗부분)")]


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def lab(r):
    b, p = r.split("_")
    return f"{KO[p]} · 씨앗 {0 if b == 'b1' else 1}"


def f(x, nd=3):
    return "—" if x is None else (f"{x:,.{nd}f}" if isinstance(x, float) else f"{x:,}")


def main():
    runs = [r for r in RUNS if (P / "stage0" / r / "receipt.json").exists()]
    out = []
    out.append("**T1 학습 한 번의 결과, 시간, 자원**\n")
    out.append("| 학습 | 결과 | 벽시계 (분) | 학습 고리 (분) | 다시 읽기 (분, 횟수) | 기록용 렌더 (분) | 초기화 (초) | 그 밖 (분) | GPU 메모리: 할당 최대 / 예약 최대 / nvidia-smi (GB) | 평가 시점 PSNR / SSIM / LPIPS |")
    out.append("|---|---|---:|---:|---|---:|---:|---:|---|---|")
    for r in runs:
        R = P / "stage0" / r; M = R / "model/monitor"
        rec = json.loads((R / "receipt.json").read_text()); meta = json.loads((M / "meta.json").read_text())
        E = jl(M / "E.jsonl"); T = jl(M / "timing.jsonl"); S = jl(M / "scalars.jsonl")
        ree = sum(e.get("seconds", 0) for e in E[1:]); ro = sum(t["seconds"] for t in T)
        loop = S[-1]["elapsed"] - ree - ro
        rest = rec["wall_seconds"] - S[-1]["elapsed"] - meta["init_seconds"]
        met = (R / "model/metric.txt").read_text().split() if (R / "model/metric.txt").exists() else []
        last = [m for m in met if m.startswith("30000_")]
        ps = last[0].split("_")[1:] if last else None
        mem = rec["gpu_memory_used_mib"]
        out.append(f"| {lab(r)} | {rec['status']} | {rec['wall_seconds'] / 60:.1f} | {loop / 60:.1f} | {ree / 60:.1f} ({len(E) - 1}) | {ro / 60:.1f} | {meta['init_seconds']:.1f} | {rest / 60:.1f} | "
                   f"{max(x['peak_cuda_gb'] for x in S):.1f} / {max(x.get('max_reserved_gb', 0) for x in S):.1f} / {mem['peak_minus_idle'] / 1024:.1f} | "
                   + (f"{float(ps[0]):.2f} / {float(ps[1]):.3f} / {float(ps[2]):.3f} |" if ps else "— |"))
    out.append("\n**T2 30,000회의 장면**\n")
    out.append("| 학습 | 가우시안 | 사전 정보 출신 | 관측 출신 | 보호 대상 | 사전 정보 출신 불투명도 10 / 50 / 90 % | 그 가운데 0.5 이상 | TSDF 삼각형 |")
    out.append("|---|---:|---:|---:|---:|---|---:|---:|")
    for r in runs:
        S = jl(P / "stage0" / r / "model/monitor/scalars.jsonl"); x = S[-1]
        pj = P / "stage0" / r / "post/post.json"
        tri = json.loads(pj.read_text())["tsdf"]["triangles"] if pj.exists() else None
        q = x["opacity_q_prior"]
        out.append(f"| {lab(r)} | {x['n']:,} | {x['n_prior']:,} | {x['n_image']:,} | {x['n_locked']:,} | {q[0]:.3f} / {q[1]:.3f} / {q[2]:.3f} | {x['opacity_share_ge05_prior']:.2f} | {f(tri)} |")
    qs = {r: json.loads((P / "quick" / f"quick_{r}.json").read_text()) for r in runs if (P / "quick" / f"quick_{r}.json").exists()}
    if qs:
        out.append("\n**T3 참값과 간단히 견주기 (점검용)**\n")
        out.append("| 나눔 | " + " | ".join(f"{lab(r)}" for r in qs) + " |")
        out.append("|---|" + "---|" * len(qs))
        for k, nm in PARTS:
            cells = []
            for r, q in qs.items():
                v = q["parts"][k]
                dz = v["roof_dz"]; w = v["within"]
                cells.append(f"{f(dz['median'])} / {f(dz['nmad'])}; {f(w['le_0_2'], 2)} / {f(w['le_0_5'], 2)} ({v['points']:,})")
            out.append(f"| {nm} | " + " | ".join(cells) + " |")
        out.append("\n(칸 = 지붕 점의 높이 차 z결과 − z참값 중앙값 / NMAD (m); 결과 표면 0.2 m / 0.5 m 안의 몫 (참값 점 수). 일치 영역은 사전 정보마다 자기 영역이라 점 수가 다르다.)")
        out.append("\n| 못 본 패치 (B173 벽, 비가시) | " + " | ".join(lab(r) for r in qs) + " |")
        out.append("|---|" + "---|" * len(qs))
        out.append("| 패치 중심이 결과 메시 0.2 / 0.5 m 안 | " + " | ".join(f"{q['unseen_patch_centres']['within']['le_0_2']:.2f} / {q['unseen_patch_centres']['within']['le_0_5']:.2f}" for q in qs.values()) + " |")
        out.append("| 0.25 m 안에 사전 정보 출신 가우시안(불투명도 0.5 이상)이 있는 몫 | " + " | ".join(f"{q['unseen_patch_gaussians'].get('prior_opacity_ge_0.5', {}).get('share_of_patches_with_one', 0):.2f}" for q in qs.values()) + " |")
        out.append("| 0.25 m 안에 관측 출신 가우시안(불투명도 0.5 이상)이 있는 몫 | " + " | ".join(f"{q['unseen_patch_gaussians'].get('image_opacity_ge_0.5', {}).get('share_of_patches_with_one', 0):.2f}" for q in qs.values()) + " |")
    sp = P / "quick" / "spread.json"
    if sp.exists():
        S = json.loads(sp.read_text())["spread"]
        out.append("\n**T4 흔들림 (씨앗 1 − 씨앗 0)**\n")
        out.append("| 나눔 | LoD2: 높이 차 중앙값 / NMAD (cm) | LoD2: 0.2 / 0.5 m 안 (%p) | 항공 LiDAR: 높이 차 중앙값 / NMAD (cm) | 항공 LiDAR: 0.2 / 0.5 m 안 (%p) |")
        out.append("|---|---|---|---|---|")
        for k, nm in PARTS:
            c = []
            for p in ("LoD2", "ALS"):
                v = S[p][k]
                c.append(("—" if v["roof_dz_median"] is None else f"{100 * v['roof_dz_median']:+.1f} / {100 * v['roof_dz_nmad']:+.1f}"))
                c.append(("—" if v["le_0_2"] is None else f"{100 * v['le_0_2']:+.1f} / {100 * v['le_0_5']:+.1f}"))
            out.append(f"| {nm} | " + " | ".join(c) + " |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
