"""PHD-MAIN-METRICS-FIX-v1 tables (jointbuildgs:dev, CPU): markdown from metrics/<result>.json (v2) next to the trial's
metrics/<result>.json (v1, /mt), and the records of 4.5-4.7.

  python tables_mf.py [part ...]      parts: accuracy, all (4.8), seed; default: every part whose inputs exist

writes /out/tables/<part>.md (and seed.json, repetition.json for 'seed'). Names of 2026-10-06. scientific_verdict: null."""
import json
import sys

import numpy as np

from mf_common import MT, OUT, jdump

ORDER = ["b1_LoD2", "b2_LoD2", "surface_LoD2", "samepath_LoD2", "b1_ALS", "b2_ALS", "surface_ALS", "samepath_ALS"]
LAB = {"b1_LoD2": "LoD2 씨앗 0", "b2_LoD2": "LoD2 씨앗 1", "surface_LoD2": "LoD2 그대로(표면)", "samepath_LoD2": "LoD2 그대로(같은 길)",
       "b1_ALS": "항공 LiDAR 씨앗 0", "b2_ALS": "항공 LiDAR 씨앗 1", "surface_ALS": "항공 LiDAR 그대로(표면)", "samepath_ALS": "항공 LiDAR 그대로(같은 길)"}


def cm(x, sign=True):
    return "—" if x is None else (f"{100 * x:+.1f}" if sign else f"{100 * x:.1f}")


def pc(x):
    return "—" if x is None else f"{100 * x:.1f}"


def load(dirp, r):
    p = dirp / "metrics" / f"{r}.json"
    return json.loads(p.read_text()) if p.exists() else None


def part_accuracy():
    out = ["**A1 기하 정확도 (지지 일치 영역, 영역 v2): 편향 / 산포** (cm; 산포 = NMAD · |차 − 중앙값|의 68.3 % · 95 % 분위; 괄호는 점 수)\n",
           "| 결과 | 완만한 지붕(≤17°, 높이 차) | 가파른 지붕(>17°, 법선 거리) | 가장자리 띠(법선 거리) | 벽(법선 거리) | 시험 계산(v1) 지붕: 편향 / NMAD |",
           "|---|---|---|---|---|---|"]
    for r in ORDER:
        v2, v1 = load(OUT, r), load(MT, r)
        if not v2 or "accuracy" not in v2:
            continue
        a = v2["accuracy"]

        def bd(d):
            return "—" if not d["n"] else f"{cm(d['bias'])} / {cm(d['nmad'], False)} · {cm(d['dev_q683'], False)} · {cm(d['dev_q95'], False)} ({d['n']:,})"
        r1 = v1["accuracy"]["roof"] if v1 else None
        out.append(f"| {LAB[r]} | {bd(a['gentle'])} | {bd(a['steep'])} | {bd(a['band'])} | {bd(a['wall'])} | "
                   + ("—" if not r1 else f"{cm(r1['median'])} / {cm(r1['nmad'], False)} ({r1['n']:,})") + " |")
    a0 = load(OUT, "b1_LoD2")["accuracy"]
    a1 = load(OUT, "b1_ALS")["accuracy"]
    out.append("\n**A2 가장자리 띠로 뺀 몫, 사전 정보 면 경사별** (지지 일치 영역의 지붕 점; 시험 계산 v1 → 새 띠 v2, %; 점 수)\n")
    out.append("| 경사 (°) | LoD2 | 항공 LiDAR |")
    out.append("|---|---|---|")
    for i in range(5):
        cells = []
        for a in (a0, a1):
            e = a["by_slope"][i]
            cells.append("—" if not e["roof_points"] else f"{pc(e['band_share_v1'])} → {pc(e['band_share_v2'])} ({e['roof_points']:,})")
        s = a0["by_slope"][i]["slope_deg"]
        out.append(f"| {s[0]}–{min(s[1], 90)} | " + " | ".join(cells) + " |")
    out.append(f"| 전체 | {pc(a0['band_share_v1'])} → {pc(a0['band_share_v2'])} | {pc(a1['band_share_v1'])} → {pc(a1['band_share_v2'])} |")
    out.append("\n**A3 띠 밖 지붕 점, 건물별** (v1 → v2; 괄호는 v2에서 법선 거리로 읽는 가파른 면의 점)\n")
    out.append("| 건물 | LoD2 | 항공 LiDAR |")
    out.append("|---|---|---|")
    for b in a0["by_building"]:
        cells = [f"{a['by_building'][b]['outside_band_v1']:,} → {a['by_building'][b]['outside_band_v2']:,} ({a['by_building'][b]['steep_outside_band_v2']:,})" for a in (a0, a1)]
        out.append(f"| {b}{' (B173)' if b == 'DEBY_LOD2_4959326' else ''} | " + " | ".join(cells) + " |")
    (OUT / "tables").mkdir(exist_ok=True)
    (OUT / "tables/accuracy.md").write_text("\n".join(out) + "\n")
    print("accuracy table")


PARTS = {"accuracy": part_accuracy}

if __name__ == "__main__":
    for p in (sys.argv[1:] or list(PARTS)):
        PARTS[p]()
