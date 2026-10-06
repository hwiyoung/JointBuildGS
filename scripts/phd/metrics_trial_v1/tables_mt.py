"""PHD-MAIN-METRICS-TRIAL-v1 tables of 4.3-4.5 and 4.7 (jointbuildgs:dev, CPU): markdown from metrics/<result>.json, the rows
files and paths/mvs_points.npz.

  python tables_mt.py          -> /out/tables/metrics_tables.md, /out/tables/spread_seed.json, /out/tables/repetition.json

M1 spread (번짐 몫) per region and result, ambiguous share; M2 mechanism layer; M3 size bins (GT-side share);
M4 accuracy (measured agreement); M5 edge band by slope; M6 completeness; M7 unseen walls (training mesh, Gaussians, virtual
mesh, GT cover); M8 floaters; M9 summary numbers; M10 the five height paths on the common points; M11 seed spread
(seed 1 - seed 0) of every number; M12 seconds per bundle; R repetition input: seed spread next to |training - prior as-is|.
scientific_verdict: null."""
import json

import numpy as np

from mt_common import DR, OUT, jdump
from src.phd.metrics_v1 import stats

RUNS = {"LoD2": ["b1_LoD2", "b2_LoD2"], "ALS": ["b1_ALS", "b2_ALS"]}
REFS = {"LoD2": ["surface_LoD2", "samepath_LoD2"], "ALS": ["surface_ALS", "samepath_ALS"]}
LAB = {"b1_LoD2": "LoD2 씨앗 0", "b2_LoD2": "LoD2 씨앗 1", "surface_LoD2": "LoD2 그대로(표면)", "samepath_LoD2": "LoD2 그대로(같은 길)",
       "b1_ALS": "항공 LiDAR 씨앗 0", "b2_ALS": "항공 LiDAR 씨앗 1", "surface_ALS": "항공 LiDAR 그대로(표면)", "samepath_ALS": "항공 LiDAR 그대로(같은 길)"}
REG = [("prior_wrong", "사전 정보가 틀린 곳"), ("image_wrong", "영상이 틀린 곳"), ("unmeasured_wrong_prior_missing", "못 잰 곳의 틀린 사전 정보(결측)"),
       ("both_wrong_record", "둘 다 틀린 곳 (기록)"), ("wings_11_12_record", "B173 날개 = 11 + 12 (기록)")]


def f(x, nd=3, pct=False, sign=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    if pct:
        return f"{100 * x:{'+' if sign else ''}.1f}"
    return f"{x:{'+' if sign else ''},.{nd}f}" if isinstance(x, float) else f"{x:,}"


def span(m):
    """'lo–hi' of a bin in metres ('lo–' when open)."""
    if m[0] is None:
        return "—"
    return f"{m[0]:.2f}–" + ("" if m[1] is None else f"{m[1]:.2f}")


def get(d, path):
    for k in path:
        if d is None:
            return None
        d = d.get(k) if isinstance(d, dict) else (d[k] if isinstance(d, list) and isinstance(k, int) and k < len(d) else None)
    return d


def main():
    M = {p.stem: json.loads(p.read_text()) for p in sorted((OUT / "metrics").glob("*.json"))}
    order = [r for p in ("LoD2", "ALS") for r in RUNS[p] + REFS[p] if r in M]
    out = []
    # ---------------------------------------------------------------- M1 spread
    out.append("**M1 번짐 몫** (칸 = 번짐 몫 % · 참값 쪽 % · 틀린 자료 쪽 % · 둘 다 % · 둘 다 아님 %; 점 수; 가르기 모호 %)\n")
    out.append("| 영역 | " + " | ".join(LAB[r] for r in order) + " |")
    out.append("|---|" + "---|" * len(order))
    for k, nm in REG:
        cells = []
        for r in order:
            e = M[r]["spread"].get(k)
            a = e["all"] if e else None
            cells.append("—" if not a or not a["points"] else
                         f"**{f(a['spread'], pct=True)}** · {f(a['gt_side'], pct=True)} · {f(a['wrong_side'], pct=True)} · {f(a['both'], pct=True)} · {f(a['neither'], pct=True)}; {a['points']:,}; 모호 {f(e['ambiguous_share'], pct=True)}")
        out.append(f"| {nm} | " + " | ".join(cells) + " |")
    out.append("\n(번짐 몫 = (틀린 자료 쪽 + 둘 다) / 전체. 가르기 모호 = |W − 참값| < 0.2 m 인 점의 몫. '기록'은 정의 밖 측정으로, 목적은 패치 MVS 대리값이 가른 11·12의 경계를 보는 것이다.)\n")
    out.append("**M1b 가르기 모호를 뺀 번짐 몫** (|W − 참값| ≥ 0.2 m 인 점만; %, 점 수)\n")
    out.append("| 영역 | " + " | ".join(LAB[r] for r in order) + " |")
    out.append("|---|" + "---|" * len(order))
    for k, nm in REG:
        cells = []
        for r in order:
            e = M[r]["spread"].get(k)
            a = e["non_ambiguous"] if e else None
            cells.append("—" if not a or not a["points"] else f"{f(a['spread'], pct=True)}; {a['points']:,}")
        out.append(f"| {nm} | " + " | ".join(cells) + " |")
    # ---------------------------------------------------------------- M2 mechanism layer
    tr = [r for p in ("LoD2", "ALS") for r in RUNS[p] if r in M]
    out.append("\n**M2 기제 층** (패치마다 W 중심 0.25 m 안에 불투명도 0.5 이상의 사전 정보 출신 가우시안이 있는 몫, %; 패치 수)\n")
    out.append("| 영역 | " + " | ".join(LAB[r] for r in tr) + " |")
    out.append("|---|" + "---|" * len(tr))
    for k, nm in [("prior_wrong", "사전 정보가 틀린 곳"), ("image_wrong", "영상이 틀린 곳"), ("unmeasured_wrong_prior_missing", "못 잰 곳의 틀린 사전 정보(결측)"),
                  ("unmeasured_wrong_prior_invisible", "못 잰 곳의 틀린 사전 정보(비가시)"), ("both_wrong_record", "둘 다 틀린 곳 (기록)")]:
        cells = []
        for r in tr:
            e = M[r]["spread"]["mechanism"][k]
            cells.append("—" if not e["patches"] else f"{f(e['prior_origin_share'], pct=True)}; {e['patches']:,}")
        out.append(f"| {nm} | " + " | ".join(cells) + " |")
    out.append("| 영상이 틀린 곳: 출신을 가리지 않음 (기록) | " + " | ".join(f(M[r]["spread"]["mechanism"]["image_wrong"].get("any_origin_share_record"), pct=True) for r in tr) + " |")
    # ---------------------------------------------------------------- M3 size bins
    out.append("\n**M3 차이 크기별 따른 몫** (사전 정보가 틀린 곳; 칸 = 참값 쪽 % · 번짐 몫 %; 점 수)\n")
    for p in ("LoD2", "ALS"):
        rs = [r for r in RUNS[p] + REFS[p] if r in M]
        if not rs:
            continue
        c0 = M[rs[0]]["spread"]["size_curve_prior_wrong"]
        out.append(f"\n*{p}*\n")
        out.append("| 구간 (τ 배수) | 지붕 m | 벽 m | " + " | ".join(LAB[r] for r in rs) + " |")
        out.append("|---|---|---|" + "---|" * len(rs))
        for i, b in enumerate(c0):
            lo_b, hi_b = b["bin"]
            nm = f"[{lo_b:g}, {hi_b:g})" if hi_b is not None else f"{lo_b:g} 이상"
            rm, wm = (span(b["roof_m"]), span(b["wall_m"]))
            cells = []
            for r in rs:
                a = M[r]["spread"]["size_curve_prior_wrong"][i]["all"]
                cells.append("—" if not a["points"] else f"{f(a['gt_side'], pct=True)} · {f(a['spread'], pct=True)}; {a['points']:,}")
            out.append(f"| {nm} | {rm} | {wm} | " + " | ".join(cells) + " |")
    # ---------------------------------------------------------------- M4 accuracy
    out.append("\n**M4 정확도 (잰 일치)** (m; 지붕 = 가장자리 띠를 뺀 지붕 점의 높이 차, 띠·벽 = 사전 정보 면 법선 방향 거리)\n")
    out.append("| 결과 | 지붕 점 (띠 뺀 몫) | 지붕 부호 중앙값 / NMAD | 지붕 \\|차\\| 중앙값 / 68.3 % / 95 % | 띠 중앙값 / NMAD (2 m 안 없음) | 벽 중앙값 / NMAD (2 m 안 없음) |")
    out.append("|---|---|---|---|---|---|")
    for r in order:
        a = M[r]["accuracy"]
        ro, b, w = a["roof"], a["edge_band"], a["wall"]
        out.append(f"| {LAB[r]} | {ro['n']:,} ({f(ro['edge_band_share'], pct=True)} %) | {f(ro['median'], sign=True)} / {f(ro['nmad'])} | {f(ro['abs_median'])} / {f(ro['abs_q683'])} / {f(ro['abs_q95'])} | "
                   f"{f(b['median'], sign=True)} / {f(b['nmad'])} ({b['no_crossing_within_2m']:,}) | {f(w['median'], sign=True)} / {f(w['nmad'])} ({w['no_crossing_within_2m']:,}) |")
    # ---------------------------------------------------------------- M4b where the accuracy roof points lie (record: which roofs the 'wide roof' reads)
    from matplotlib.path import Path as MPath
    fp = json.loads((DR / "s02_box" / "B173nb_b10" / "footprints.json").read_text())["footprints"]
    Gc = np.load(OUT / "defs/gt_classes.npz")
    Xg = Gc["xyz"]
    out.append("\n**M4b 정확도 지붕 점이 놓인 건물** (잰 일치의 지붕 점; 띠 밖 점 수 / 띠 안 점 수; 기록: '넓은 지붕'이 어느 지붕을 읽는지)\n")
    out.append("| 건물 | LoD2: 띠 밖 / 띠 안 | 항공 LiDAR: 띠 밖 / 띠 안 |")
    out.append("|---|---|---|")
    cnt = {}
    for p in ("LoD2", "ALS"):
        rws = np.load(OUT / "defs" / f"rows_{p}.npz")
        m = (rws["code"] == 2) & (rws["kind"] == 1)
        pt = rws["point"][m]
        inb = Gc["in_band"][pt]
        for fpr in fp:
            inside = MPath(np.asarray(fpr["ring_local"])).contains_points(Xg[pt, :2])
            cnt.setdefault(fpr["building"], {})[p] = (int((inside & ~inb).sum()), int((inside & inb).sum()))
    for b, v in cnt.items():
        out.append(f"| {b}{' (B173)' if b == 'DEBY_LOD2_4959326' else ''} | " + " | ".join(f"{v[p][0]:,} / {v[p][1]:,}" if p in v else "—" for p in ("LoD2", "ALS")) + " |")
    # ---------------------------------------------------------------- M5 band by slope
    out.append("\n**M5 가장자리 띠로 빠진 몫, 사전 정보 면 경사별** (잰 일치의 지붕 점; %, 점 수)\n")
    out.append("| 경사 (°) | LoD2 | 항공 LiDAR |")
    out.append("|---|---|---|")
    for i in range(5):
        cells = []
        for p in ("LoD2", "ALS"):
            r = next((x for x in RUNS[p] + REFS[p] if x in M), None)
            e = M[r]["accuracy"]["band_by_slope"][i] if r else None
            cells.append("—" if not e or not e["roof_points"] else f"{f(e['band_share'], pct=True)}; {e['roof_points']:,}")
        e0 = M[order[0]]["accuracy"]["band_by_slope"][i]
        out.append(f"| {e0['slope_deg'][0]}–{e0['slope_deg'][1] if e0['slope_deg'][1] < 90 else 90} | " + " | ".join(cells) + " |")
    # ---------------------------------------------------------------- M6 completeness
    out.append("\n**M6 완전성 (못 잰 일치)** (참값 점이 결과 0.2 m / 0.5 m 안에 있는 몫 %; 점 수)\n")
    out.append("| 영역 | " + " | ".join(LAB[r] for r in order) + " |")
    out.append("|---|" + "---|" * len(order))
    for k, nm in (("unmeasured_agreement_missing", "못 잰 일치(결측)"), ("unmeasured_agreement_invisible", "못 잰 일치(비가시)")):
        cells = []
        for r in order:
            a = M[r]["completeness"][k]["all"]
            cells.append("—" if not a["n"] else f"{f(a['le_0.2'], pct=True)} / {f(a['le_0.5'], pct=True)}; {a['n']:,}")
        out.append(f"| {nm} | " + " | ".join(cells) + " |")
    # ---------------------------------------------------------------- M7 unseen walls
    out.append("\n**M7 못 본 곳 (B173 비가시 벽 패치)** (%; 패치 수는 머리 줄)\n")
    g0 = M[order[0]]["unseen"]["centres_within"]
    keys = ["below_current_roof (inferred agreement)", "above_current_roof (inferred conflict)", "true agreement (label)", "true conflict (label)"]
    kn = {"below_current_roof (inferred agreement)": "지금 지붕 아래 (추정 일치)", "above_current_roof (inferred conflict)": "지금 지붕 위 (추정 충돌)",
          "true agreement (label)": "참 일치 (라벨)", "true conflict (label)": "참 충돌 (라벨)"}
    out.append("| 측정 | 결과 | " + " | ".join(f"{kn[k]} ({g0[k]['n']:,})" for k in keys) + " |")
    out.append("|---|---|" + "---|" * len(keys))
    for r in order:
        u = M[r]["unseen"]
        out.append(f"| 패치 중심이 학습 시점 메시 0.2 / 0.5 m 안 | {LAB[r]} | " + " | ".join(f"{f(u['centres_within'][k]['le_0.2'], pct=True)} / {f(u['centres_within'][k]['le_0.5'], pct=True)}" for k in keys) + " |")
    for r in tr:
        u = M[r]["unseen"]
        out.append(f"| 0.25 m 안 사전 정보 출신 가우시안(불투명도 0.5 이상) | {LAB[r]} | " + " | ".join(f(u['prior_origin_gaussians'][k]['share_with_one'], pct=True) for k in keys) + " |")
    for r in tr:
        v = M[r].get("virtual")
        if v:
            out.append(f"| 패치 중심이 가상 시점 메시 0.2 / 0.5 m 안 | {LAB[r]} | " + " | ".join(f"{f(v['virtual']['centres_within'][k]['le_0.2'], pct=True)} / {f(v['virtual']['centres_within'][k]['le_0.5'], pct=True)}" for k in keys) + " |")
    v0 = next((M[r].get("virtual") for r in tr if M[r].get("virtual")), None)
    if v0:
        out.append("| 참값 피복: 소유 참값 점이 있는 패치 / 라벨이 있는 패치 | (학습과 무관) | " + " | ".join(f"{f(v0['gt_cover'][k]['with_owned_gt_point'], pct=True)} / {f(v0['gt_cover'][k]['with_label'], pct=True)}" for k in keys) + " |")
    out.append("\n| 못 본 곳의 참값 점 (359) | " + " | ".join(LAB[r] for r in tr) + " |")
    out.append("|---|" + "---|" * len(tr))
    out.append("| 학습 시점 메시 0.2 / 0.5 m 안 | " + " | ".join(f"{f(M[r]['unseen']['gt_points']['le_0.2'], pct=True)} / {f(M[r]['unseen']['gt_points']['le_0.5'], pct=True)}" for r in tr) + " |")
    out.append("| 가상 시점 메시 0.2 / 0.5 m 안 | " + " | ".join("—" if not M[r].get("virtual") else f"{f(M[r]['virtual']['virtual']['gt_points']['le_0.2'], pct=True)} / {f(M[r]['virtual']['virtual']['gt_points']['le_0.5'], pct=True)}" for r in tr) + " |")
    out.append("| 메시 꼭짓점의 LoD2 벽면까지 거리 5 / 50 / 95 % (가상 시점, m) | " + " | ".join("—" if not M[r].get("virtual") or not M[r]['virtual']['virtual']['vertices_at_unseen_walls']['q'] else
                                                                                        " / ".join(f"{x:+.2f}" for x in np.array(M[r]['virtual']['virtual']['vertices_at_unseen_walls']['q'])[[0, 2, 4]]) for r in tr) + " |")
    out.append("| 같은 것, 학습 시점 메시 | " + " | ".join("—" if not M[r].get("virtual") or not M[r]['virtual']['training']['vertices_at_unseen_walls']['q'] else
                                                     " / ".join(f"{x:+.2f}" for x in np.array(M[r]['virtual']['training']['vertices_at_unseen_walls']['q'])[[0, 2, 4]]) for r in tr) + " |")
    out.append("| 그 꼭짓점 수: 가상 시점 / 학습 시점 | " + " | ".join("—" if not M[r].get("virtual") else f"{M[r]['virtual']['virtual']['vertices_at_unseen_walls']['n']:,} / {M[r]['virtual']['training']['vertices_at_unseen_walls']['n']:,}" for r in tr) + " |")
    # ---------------------------------------------------------------- M8 floaters
    out.append("\n**M8 떠 있는 조각** (평가 범위, 참값 최고 표면보다 3 m 넘게 위, 불투명도 0.5 이상)\n")
    out.append("| 학습 | 가우시안 수 (사전 정보 출신) | 평가 시점 픽셀 몫 (픽셀 수) | 최고 표면 위 높이 중앙값 / 95 % / 최대 (m) |")
    out.append("|---|---|---|---|")
    for r in tr:
        fl = M[r].get("floaters") or {}
        h = fl.get("height_over_top_m") or {}
        ps = fl.get("pixel_share")
        pst = "—" if ps is None else f"{100 * ps:.3f} %"
        out.append(f"| {LAB[r]} | {f(fl.get('count'))} ({f(fl.get('prior_origin'))}) | {pst} ({f(fl.get('floater_pixels'))}) | "
                   f"{f(h.get('p50'), 2)} / {f(h.get('p95'), 2)} / {f(h.get('max'), 2)} |")
    # ---------------------------------------------------------------- M9 summary numbers
    out.append("\n**M9 요약 숫자 (건물 표면)** (m 또는 %)\n")
    out.append("| 결과 | Chamfer 결과→참값 / 참값→결과 / 평균 | 정밀도 / 완전성 / F1 @0.2 m | 같은 것 @0.5 m | M3C2 중앙값 / NMAD (거리 있는 몫) |")
    out.append("|---|---|---|---|---|")
    for r in order:
        s = M[r]["summary"]
        out.append(f"| {LAB[r]} | {f(s['chamfer_result_to_gt'])} / {f(s['chamfer_gt_to_result'])} / {f(s['chamfer_mean'])} | "
                   f"{f(s['precision_0.2'], pct=True)} / {f(s['completeness_0.2'], pct=True)} / {f(s['f1_0.2'], pct=True)} | {f(s['precision_0.5'], pct=True)} / {f(s['completeness_0.5'], pct=True)} / {f(s['f1_0.5'], pct=True)} | "
                   f"{f(s['m3c2']['median'], sign=True)} / {f(s['m3c2']['nmad'])} ({f(s['m3c2']['share_with_distance'], pct=True)} %) |")
    # ---------------------------------------------------------------- M10 height paths
    out.append("\n**M10 지붕 높이 치우침의 다섯 길** (잰 일치의 넓은 지붕 점 = 가장자리 띠 밖; 모든 길에 값이 있는 같은 점; z길 − z참값, m)\n")
    mv = np.load(OUT / "paths/mvs_points.npz")
    paths_json = {}
    G = np.load(OUT / "defs/gt_classes.npz")
    zg = G["xyz"][:, 2].astype(np.float64)
    order_mv = np.argsort(mv["point"])
    mpt, mz = mv["point"][order_mv], mv["z"][order_mv].astype(np.float64)
    out.append("| 사전 정보 | 공통 점 | 1 결과 메시 (씨앗 0 / 1) | 2 결과 렌더 점 (씨앗 0 / 1) | 3 사전 정보 표면 | 4 같은 길 메시 | 5 MVS 신뢰도 1 점 |")
    out.append("|---|---:|---|---|---|---|---|")
    for p in ("LoD2", "ALS"):
        need = RUNS[p] + REFS[p]
        if not all(r in M for r in need):
            continue
        R = {r: np.load(OUT / "metrics" / f"{r}_rows.npz") for r in need}
        rws = np.load(OUT / "defs" / f"rows_{p}.npz")
        base = ~np.isnan(R[RUNS[p][0]]["dz"])
        pt = rws["point"]
        i5 = np.searchsorted(mpt, pt)
        ok5 = (i5 < len(mpt))
        ok5[ok5] &= mpt[i5[ok5]] == pt[ok5]
        z5 = np.full(len(pt), np.nan)
        z5[ok5] = mz[i5[ok5]]
        d5 = z5 - zg[pt]
        vals = {"1": [R[r]["dz"] for r in RUNS[p]], "2": [R[r]["path2"] if "path2" in R[r].files else np.full(len(pt), np.nan) for r in RUNS[p]],
                "3": [R[REFS[p][0]]["dz"]], "4": [R[REFS[p][1]]["dz"]], "5": [d5]}
        common = base.copy()
        for vs in vals.values():
            for v in vs:
                common &= np.isfinite(v)
        cells, pj = [], {}
        for k in ("1", "2", "3", "4", "5"):
            ss = [stats.robust(v[common]) for v in vals[k]]
            pj[k] = ss
            cells.append(" / ".join(f"{f(s['median'], sign=True)} ({f(s['nmad'])})" for s in ss))
        own = {k: [stats.robust(v[base & np.isfinite(v)]) for v in vals[k]] for k in vals}
        paths_json[p] = dict(common_points=int(common.sum()), on_common=pj, on_own_points=own)
        out.append(f"| {p} | {int(common.sum()):,} | " + " | ".join(cells) + " |")
    out.append("\n(칸 = 부호 있는 중앙값 (NMAD). 1·2는 학습 둘, 3·4는 사전 정보, 5는 학습 영상 MVS. 1 − 2 = 메시를 만드는 길의 몫, 4 − 3 = 같은 길이 알려진 표면에 더하는 몫, 3과 5 = 참값과 두 자료의 높이 맞춤.)")
    # ---------------------------------------------------------------- M11 seed spread
    seed = {}
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
    for p in ("LoD2", "ALS"):
        a, b = RUNS[p]
        if a in M and b in M:
            flat.clear()
            walk({k: M[a][k] for k in ("spread", "accuracy", "completeness", "unseen", "floaters", "summary", "path2", "virtual") if k in M[a]})
            fa = dict(flat)
            flat.clear()
            walk({k: M[b][k] for k in ("spread", "accuracy", "completeness", "unseen", "floaters", "summary", "path2", "virtual") if k in M[b]})
            fb = dict(flat)
            seed[p] = {k: fb[k] - fa[k] for k in fa if k in fb and not k.endswith((".n", ".points", ".patches")) and "seconds" not in k}
    jdump(OUT / "tables/spread_seed.json", dict(rule="seed 1 (batch 2) minus seed 0 (batch 1), every number of metrics/<run>.json", seed=seed, paths=paths_json,
                                               scientific_verdict=None))
    # ---------------------------------------------------------------- R repetition input
    keys_r = [("spread.prior_wrong.all.spread", "번짐 몫: 사전 정보가 틀린 곳", 100, "%p"), ("spread.image_wrong.all.spread", "번짐 몫: 영상이 틀린 곳", 100, "%p"),
              ("spread.unmeasured_wrong_prior_missing.all.spread", "번짐 몫: 못 잰 곳의 틀린 사전 정보(결측)", 100, "%p"),
              ("accuracy.roof.median", "정확도: 지붕 높이 차 중앙값", 100, "cm"), ("accuracy.roof.nmad", "정확도: 지붕 NMAD", 100, "cm"),
              ("accuracy.roof.abs_median", "정확도: 지붕 |차| 중앙값", 100, "cm"), ("accuracy.wall.median", "정확도: 벽 거리 중앙값", 100, "cm"),
              ("completeness.unmeasured_agreement_missing.all.le_0.5", "완전성: 못 잰 일치(결측) 0.5 m", 100, "%p"),
              ("unseen.centres_within.below_current_roof (inferred agreement).le_0.5", "못 본 곳: 지붕 아래 패치 중심 0.5 m (학습 메시)", 100, "%p"),
              ("summary.chamfer_mean", "요약: Chamfer 평균", 100, "cm"), ("summary.f1_0.2", "요약: F1 @0.2 m", 100, "%p"), ("summary.f1_0.5", "요약: F1 @0.5 m", 100, "%p"),
              ("summary.m3c2.median", "요약: M3C2 중앙값", 100, "cm"), ("summary.m3c2.nmad", "요약: M3C2 NMAD", 100, "cm")]
    rep = {}
    out.append("\n**R 반복 수 입력** (씨앗 사이 흔들림 |씨앗 1 − 씨앗 0|, 같은 자리의 |학습 평균 − 사전 정보 그대로(표면)|, 비 = 흔들림 / 차이)\n")
    out.append("| 지표 | 단위 | LoD2 흔들림 | LoD2 차이 | LoD2 비 | 항공 LiDAR 흔들림 | 항공 LiDAR 차이 | 항공 LiDAR 비 |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for key, nm, sc_, unit in keys_r:
        cells = []
        for p in ("LoD2", "ALS"):
            a, b = RUNS[p]
            ref = REFS[p][0]
            if not all(x in M for x in (a, b, ref)):
                cells += ["—"] * 3
                continue
            def val(r):
                flat.clear()
                walk(M[r])
                return flat.get(key)
            va, vb, vr = val(a), val(b), val(ref)
            if va is None or vb is None:
                cells += ["—"] * 3
                continue
            s = abs(vb - va) * sc_
            dlt = abs(0.5 * (va + vb) - vr) * sc_ if vr is not None else None
            ratio = s / dlt if dlt else None
            rep.setdefault(p, {})[key] = dict(spread=s, difference=dlt, ratio=ratio, unit=unit)
            cells += [f"{s:.2f}", "—" if dlt is None else f"{dlt:.2f}", "—" if ratio is None else f"{ratio:.3f}"]
        out.append(f"| {nm} | {unit} | " + " | ".join(cells) + " |")
    jdump(OUT / "tables/repetition.json", dict(rule="ratio = |seed 1 - seed 0| / |mean of the two trainings - prior surface as-is|", rows=rep, scientific_verdict=None))
    # ---------------------------------------------------------------- M12 seconds
    out.append("\n**M12 지표 묶음별 계산 시간** (초, 결과 하나; 누적 시각의 차)\n")
    bks = ["load", "inputs", "spread", "accuracy", "completeness", "unseen", "floaters", "summary", "paths", "virtual"]
    out.append("| 결과 | " + " | ".join(bks) + " | 합 |")
    out.append("|---|" + "---:|" * (len(bks) + 1))
    for r in order:
        s = M[r]["seconds"]
        prev, cells = 0.0, []
        for k in bks:
            cells.append(f"{s[k] - prev:.0f}" if k in s else "—")
            prev = s.get(k, prev)
        out.append(f"| {LAB[r]} | " + " | ".join(cells) + f" | {prev:.0f} |")
    (OUT / "tables").mkdir(exist_ok=True)
    (OUT / "tables/metrics_tables.md").write_text("\n".join(out) + "\n")
    print("tables done", len(M))


if __name__ == "__main__":
    main()
