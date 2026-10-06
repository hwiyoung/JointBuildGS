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


def part_all():
    """4.8: every metric of the eight results under the names of 2026-10-06, v2 next to the trial (v1)."""
    M2 = {r: load(OUT, r) for r in ORDER}
    M1 = {r: load(MT, r) for r in ORDER}
    out = ["**B1 오류 유입률** (%, 본 숫자 = |W − 참값| ≥ 0.2 m인 점; 괄호는 시험 계산 v1(모든 점, 영역 v1); 판별 불가 비율은 아래 줄)\n",
           "| 영역 | " + " | ".join(LAB[r] for r in ORDER) + " |", "|---|" + "---:|" * len(ORDER)]
    v1k = {"prior_error": "prior_wrong", "observation_error": "image_wrong", "missing_prior_error": "unmeasured_wrong_prior_missing",
           "double_error_record": "both_wrong_record", "wings_11_12_record": "wings_11_12_record"}
    names = {"prior_error": "사전 정보 오류 영역", "observation_error": "관측 오류 영역", "missing_prior_error": "결측 사전 정보 오류 영역 (기록)",
             "double_error_record": "이중 오류 영역 (기록)", "wings_11_12_record": "B173 날개 (기록)"}
    for k, nm in names.items():
        cells = []
        for r in ORDER:
            e2 = M2[r]["spread"][k]
            e1 = M1[r]["spread"].get(v1k[k]) if M1[r] else None
            cells.append(f"{pc(e2['main']['spread'])} ({pc(e1['all']['spread']) if e1 else '—'})")
        out.append(f"| {nm} | " + " | ".join(cells) + " |")
        out.append(f"| — 점 수 · 판별 불가 비율 | " + " | ".join(f"{M2[r]['spread'][k]['main']['points']:,} · {pc(M2[r]['spread'][k]['indeterminable_share'])}" for r in ORDER) + " |")
    out.append("\n**B2 어긋남 크기별 보정률** (사전 정보 오류 영역, 본 숫자의 점; 1만 점 아래 구간은 위 구간과 합침; %, 씨앗 0 / 씨앗 1; 사전 정보 그대로는 모두 0~0.03 %)\n")
    for p in ("LoD2", "ALS"):
        a, b = M2[f"b1_{p}"]["spread"]["size_curve"], M2[f"b2_{p}"]["spread"]["size_curve"]
        out.append(f"*{p}* (τ 지붕 {a['tau_roof']:.3f} m; 보정 경계 {a['boundary_tau']}τ = {a['boundary_roof_m']} m / {b['boundary_tau']}τ = {b['boundary_roof_m']} m)\n")
        out.append("| 구간 (τ 배수) | 합친 구간 | 점 수 | 패치 수 | 판별 불가 비율 | 보정률 씨앗 0 / 1 |")
        out.append("|---|---|---:|---:|---:|---|")
        for x, y in zip(a["bins"], b["bins"]):
            lo, hi = x["bin"]
            nm = f"[{lo:g}, {hi:g})" if hi is not None else f"{lo:g} 이상"
            mg = "—" if not x.get("merged_from") else ", ".join(f"[{m_[0]:g}, {'∞' if m_[1] is None else f'{m_[1]:g}'})" for m_ in x["merged_from"])
            out.append(f"| {nm}{' (따로)' if x.get('separate') else ''} | {mg} | {x['points']:,} | {x['patches']:,} | {pc(x.get('indeterminable_share'))} | {pc(x['correction_rate'])} / {pc(y['correction_rate'])} |")
        out.append("")
    out.append("**B3 과거 형상 잔존율** (%; W가 참값에서 0.5 m 넘게 떨어진 패치; 관측 오류 영역은 출신을 가리지 않음; 괄호는 v1 기제 층(모든 패치))\n")
    tr = [r for r in ORDER if r.startswith("b")]
    out.append("| 영역 (패치 수 LoD2 / 항공 LiDAR) | " + " | ".join(LAB[r] for r in tr) + " |")
    out.append("|---|" + "---:|" * len(tr))
    pk = {"prior_error": ("사전 정보 오류 영역", "prior_wrong", "prior_origin_share"), "double_error_record": ("이중 오류 영역 (기록)", "both_wrong_record", "prior_origin_share"),
          "missing_prior_error": ("결측 사전 정보 오류 영역 (기록)", "unmeasured_wrong_prior_missing", "prior_origin_share"),
          "invisible_prior_error": ("비가시 사전 정보 오류 영역 (기록)", "unmeasured_wrong_prior_invisible", "prior_origin_share"),
          "observation_error_any_origin": ("관측 오류 영역 (출신 무관)", "image_wrong", "any_origin_share_record")}
    for k, (nm, k1, f1) in pk.items():
        np_ = f"{M2['b1_LoD2']['spread']['past_shape'][k]['patches']:,} / {M2['b1_ALS']['spread']['past_shape'][k]['patches']:,}"
        cells = []
        for r in tr:
            e2 = M2[r]["spread"]["past_shape"][k]
            e1 = M1[r]["spread"]["mechanism"].get(k1, {}) if M1[r] else {}
            cells.append(f"{pc(e2['rate'])} ({pc(e1.get(f1))})")
        out.append(f"| {nm} ({np_}) | " + " | ".join(cells) + " |")
    out.append("\n**B4 비가시 영역 (B173 비가시 벽, 지금 지붕 기준 추정 라벨)** (%)\n")
    out.append("| 지표 | " + " | ".join(LAB[r] for r in ORDER) + " |")
    out.append("|---|" + "---:|" * len(ORDER))
    out.append("| 상속률 (가우시안 수준, 비가시 일치 영역(추정)) | " + " | ".join(pc(M2[r]["unseen"].get("inheritance_rate_inferred")) for r in ORDER) + " |")
    out.append("| 과거 형상 잔존율 (가우시안 수준, 비가시 오류 영역(추정)) | " + " | ".join(pc(M2[r]["unseen"].get("past_shape_invisible_inferred")) for r in ORDER) + " |")
    out.append("| 메시 수준(학습 시점 메시): 비가시 일치(추정) 0.5 m 안 | " + " | ".join(pc(M2[r]["unseen"]["mesh_within"]["invisible_agreement_inferred"]["le_0.5"]) for r in ORDER) + " |")
    out.append("| 메시 수준(가상 시점 메시, 고른 안): 비가시 일치(추정) 0.5 m 안 | " + " | ".join(pc(M2[r].get("virtual", {}).get("below_roof_within_0_5")) for r in ORDER) + " |")
    out.append("| 메시 수준(가상 시점 메시, 고른 안): 비가시 오류(추정) 0.2 m 안 | " + " | ".join(pc(M2[r].get("virtual", {}).get("above_roof_within_0_2")) for r in ORDER) + " |")
    out.append("\n**B5 결측 일치 영역 · 비가시 일치 영역의 완전성 (한 지역 안이라 기록)** (0.2 / 0.5 m 안 %, 점 수)\n")
    out.append("| 영역 | " + " | ".join(LAB[r] for r in ORDER) + " |")
    out.append("|---|" + "---|" * len(ORDER))
    for k, nm in (("missing_agreement", "결측 일치 영역"), ("invisible_agreement", "비가시 일치 영역")):
        out.append(f"| {nm} | " + " | ".join(f"{pc(M2[r]['completeness'][k]['all']['le_0.2'])} / {pc(M2[r]['completeness'][k]['all']['le_0.5'])} ({M2[r]['completeness'][k]['all']['n']:,})" for r in ORDER) + " |")
    out.append("\n**B6 부유 가우시안** (불투명도 0.5 이상, 참값 최고 표면 위; 개수, 괄호는 사전 정보 가우시안)\n")
    out.append("| 학습 | 3~20 m | 20 m 넘게 | 평가 시점 픽셀 몫(두 띠 함께) |")
    out.append("|---|---|---|---|")
    for r in tr:
        f = M2[r]["floating"]
        out.append(f"| {LAB[r]} | {f['near_3_20m']:,} ({f['near_prior']:,}) | {f['above_20m']:,} ({f['above_20m_prior']:,}) | {100 * f['pixel_share_all']:.3f} % |")
    out.append("\n**B7 기록: 요약 숫자 (정의 그대로, 시험 계산 값을 옮김)** (Chamfer 평균 m; F1 @0.2 · @0.5 m %; M3C2 중앙값 / NMAD cm)\n")
    out.append("| 결과 | Chamfer 평균 | F1 @0.2 / @0.5 | M3C2 |")
    out.append("|---|---:|---|---|")
    for r in ORDER:
        s_ = M2[r]["summary"]
        out.append(f"| {LAB[r]} | {s_['chamfer_mean']:.3f} | {pc(s_['f1_0.2'])} / {pc(s_['f1_0.5'])} | {cm(s_['m3c2']['median'])} / {cm(s_['m3c2']['nmad'], False)} |")
    (OUT / "tables/all.md").write_text("\n".join(out) + "\n")
    print("all table")


def part_seed():
    """seed 1 - seed 0 of every v2 number and the repetition input table."""
    M = {r: load(OUT, r) for r in ORDER}
    flat = {}

    def walk(d, pre=""):
        if isinstance(d, dict):
            for k, v in d.items():
                walk(v, f"{pre}.{k}" if pre else k)
        elif isinstance(d, list):
            for i, v in enumerate(d):
                walk(v, f"{pre}[{i}]")
        elif isinstance(d, (int, float)) and not isinstance(d, bool):
            flat[pre] = d
    seed = {}
    for p in ("LoD2", "ALS"):
        fa, fb = {}, {}
        flat.clear(); walk({k: M[f"b1_{p}"][k] for k in M[f"b1_{p}"] if k not in ("seconds", "result", "prior", "site")}); fa = dict(flat)
        flat.clear(); walk({k: M[f"b2_{p}"][k] for k in M[f"b2_{p}"] if k not in ("seconds", "result", "prior", "site")}); fb = dict(flat)
        seed[p] = {k: fb[k] - fa[k] for k in fa if k in fb and not k.endswith((".n", ".points", ".patches", "patches_all"))}
    keys = [("spread.prior_error.main.spread", "오류 유입률: 사전 정보 오류 영역", 100, "%p"), ("spread.observation_error.main.spread", "오류 유입률: 관측 오류 영역", 100, "%p"),
            ("spread.size_curve.bins[1].correction_rate", "보정률: 첫 구간(1~1.5τ)", 100, "%p"), ("spread.past_shape.prior_error.rate", "과거 형상 잔존율: 사전 정보 오류 영역", 100, "%p"),
            ("accuracy.gentle.bias", "기하 정확도 편향: 완만한 지붕", 100, "cm"), ("accuracy.gentle.nmad", "기하 정확도 산포(NMAD): 완만한 지붕", 100, "cm"),
            ("accuracy.steep.bias", "기하 정확도 편향: 가파른 지붕", 100, "cm"), ("accuracy.steep.nmad", "기하 정확도 산포: 가파른 지붕", 100, "cm"),
            ("accuracy.wall.bias", "기하 정확도 편향: 벽", 100, "cm"), ("unseen.inheritance_rate_inferred", "상속률(비가시 일치, 추정)", 100, "%p"),
            ("virtual.below_roof_within_0_5", "가상 시점 메시: 비가시 일치 0.5 m", 100, "%p"), ("summary.chamfer_mean", "기록: Chamfer 평균", 100, "cm"),
            ("summary.f1_0.2", "기록: F1 @0.2 m", 100, "%p")]
    out = ["**C1 반복 간 변동과 반복 수 입력** (변동 = |씨앗 1 − 씨앗 0|, 차이 = |두 학습의 평균 − 사전 정보 그대로(표면)|, 비 = 변동 / 차이)\n",
           "| 지표 | 단위 | LoD2 변동 | LoD2 차이 | LoD2 비 | 항공 LiDAR 변동 | 항공 LiDAR 차이 | 항공 LiDAR 비 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    rep = {}
    for key, nm, sc, unit in keys:
        cells = []
        for p in ("LoD2", "ALS"):
            def val(r):
                flat.clear()
                walk(M[r])
                return flat.get(key)
            va, vb, vr = val(f"b1_{p}"), val(f"b2_{p}"), val(f"surface_{p}")
            if va is None or vb is None:
                cells += ["—"] * 3
                continue
            s_ = abs(vb - va) * sc
            d_ = abs(0.5 * (va + vb) - vr) * sc if vr is not None else None
            ratio = s_ / d_ if d_ else None
            rep.setdefault(p, {})[key] = dict(variation=s_, difference=d_, ratio=ratio, unit=unit)
            cells += [f"{s_:.2f}", "—" if d_ is None else f"{d_:.2f}", "—" if ratio is None else f"{ratio:.3f}"]
        out.append(f"| {nm} | {unit} | " + " | ".join(cells) + " |")
    big = []
    for p in ("LoD2", "ALS"):
        for k, v in seed[p].items():
            if any(t in k for t in ("rate", "spread", "gt_side", "share", "le_0")) and abs(v) >= 0.05:
                big.append((p, k, round(v, 4)))
    jdump(OUT / "tables/seed.json", dict(rule="seed 1 (batch 2) minus seed 0 (batch 1), every v2 number", seed=seed, large_share_differences=big, scientific_verdict=None))
    jdump(OUT / "tables/repetition.json", dict(rule="ratio = variation / |mean of the two trainings - prior surface as-is|", rows=rep, scientific_verdict=None))
    out.append("\n**C2 5 %p 넘게 흔들린 몫** (씨앗 1 − 씨앗 0)\n")
    out.append("| 사전 정보 | 숫자 | 변동 |")
    out.append("|---|---|---:|")
    for p, k, v in big:
        out.append(f"| {p} | `{k}` | {100 * v:+.1f} %p |")
    (OUT / "tables/seed.md").write_text("\n".join(out) + "\n")
    print("seed tables", len(big))


PARTS = {"accuracy": part_accuracy, "all": part_all, "seed": part_seed}

if __name__ == "__main__":
    for p in (sys.argv[1:] or list(PARTS)):
        PARTS[p]()
