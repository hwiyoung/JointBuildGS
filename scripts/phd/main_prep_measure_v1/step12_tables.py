"""PHD-MAIN-PREP-MEASURE-v1 step 12 (jointbuildgs:dev, CPU): report tables generated from the step outputs.

  python step12_tables.py [--out tables_v1.md]

Every number of the report tables is read here from the JSON / NPZ outputs (no hand transcription).
Missing inputs are written as '(없음)'. scientific_verdict: null."""
import argparse
import json

import numpy as np

from common import OUT
from src.phd.prior_propagation_v4 import tolerance as tol

RANGES = ["R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"]
KO = {"textureless": "무늬 없음", "shadow": "그림자", "oblique": "비스듬함", "other": "기타"}


def J(p):
    try:
        return json.loads((OUT / p).read_text())
    except FileNotFoundError:
        return None


def f(x, d=3):
    if x is None:
        return "–"
    if isinstance(x, (int, np.integer)):
        return f"{x:,}"
    return f"{x:.{d}f}"


def pct(a, b):
    return "–" if not b else f"{100.0 * a / b:.1f} %"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def sec_stage1(L):
    L.append("## T4.1 찾기 범위 첫째 단계: 정합과 허용 오차\n")
    rows = []
    for rid in RANGES:
        for pr in ("LoD2", "ALS"):
            s = J(f"step03/{rid}/{pr}/summary.json")
            if not s:
                continue
            r = s["registration"]; t = s["tolerance"]
            rs = np.load(OUT / f"step03/{rid}/{pr}/residual_samples.npz")
            sr = tol.robust_width(rs["roof"].astype(np.float64)); sw = tol.robust_width(rs["wall"].astype(np.float64))
            sh = r["shift_applied"]
            acc = ("수평" if r.get("accepted_horizontal") else "") + ("·수직" if r.get("accepted_vertical") else "")
            fc = r.get("final_check", {})
            rows.append([rid, pr, s["views"], f"({sh[0]:+.3f}, {sh[1]:+.3f}, {sh[2]:+.3f})", acc or "없음",
                         ("통과" if fc.get("passed") else "되돌림") if fc else "–", "예" if r["horizontal_estimable"] else "아니오",
                         f"{f(r['building_face_nmad_unregistered'])} → {f(r['building_face_nmad_registered'])}",
                         f(t["roof"]["tau"]), f"{sr['n']:,}", f(sr["median_after"]), f"{f(sr['nmad_before'])} → {f(sr['nmad_after'])}", pct(sr["clipped_share"] * sr["n"], sr["n"]) if sr["n"] else "–",
                         f(t["wall"]["tau"]), (f"{sw['n']:,}" if pr == "LoD2" else "지붕 값"),
                         f"{t['roof'].get('spec')} m: " + ("넘음" if t["roof"].get("exceeds_spec") else "안 넘음")])
    L.append(table(["범위", "사전 정보", "학습 영상", "정합 이동 (x, y, z) m", "받아들임", "전체면 확인", "수평 추정 가능", "건물 면 NMAD 앞→뒤 (m)",
                    "τ 지붕 (m)", "지붕 표본", "정합 뒤 중앙값", "NMAD 걸러내기 앞→뒤", "걸러낸 비율", "τ 벽 (m)", "벽 표본", "지붕 정확도 기준과 견줌"], rows))
    L.append("")


def sec_judgment(L):
    L.append("## T4.2 학습 전 판정 (범위 안 패치, 넓이 m²)\n")
    rows = []
    for rid in RANGES:
        for pr in ("LoD2", "ALS"):
            s = J(f"step03/{rid}/{pr}/summary.json")
            if not s:
                continue
            st = s["states"]; sv = s["support_vote"]; mj = s["missing_judgment"]; pw = s.get("pixels_without_unit") or {}; un = s.get("unplanted") or {}
            tot = sum(st[k]["roof"]["area_m2"] + st[k]["wall"]["area_m2"] for k in st)
            rows.append([rid, pr, f(tot, 0),
                         f"{pct(st['support']['roof']['area_m2'] + st['support']['wall']['area_m2'], tot)}",
                         f"{pct(st['missing']['roof']['area_m2'] + st['missing']['wall']['area_m2'], tot)}",
                         f"{pct(st['invisible']['roof']['area_m2'] + st['invisible']['wall']['area_m2'], tot)}",
                         pct(sv["conflict"]["area_m2"], sv["agree"]["area_m2"] + sv["conflict"]["area_m2"]),
                         " / ".join(f(mj[k]["area_m2"], 0) for k in ("agree", "conflict", "mixed", "insufficient")),
                         f"{pw.get('a0_inherit', '–'):,} / {pw.get('a1_agree', '–'):,} / {pw.get('a1_conflict', '–'):,}" if pw else "–",
                         (f"{un.get('unplanted', 0):,}점 (점 {un.get('points', 0):,})" if pr == "ALS" else f"{un.get('unplanted_patches', 0):,}패치 ({f(un.get('unplanted_area_m2'), 0)} m²)")])
    L.append(table(["범위", "사전 정보", "패치 넓이", "지지", "결측", "비가시", "지지 중 충돌", "결측 전파: 일치/충돌/혼재/근거 부족 (m²)",
                    "패치 없는 픽셀(학습 시점 합): 이어받음/일치/충돌", "심지 않을 점"], rows))
    L.append("")


def sec_gt(L):
    L.append("## T5 참값 정리 (설정 v3: gt_clean 방식 높이 맞춤)\n")
    rows = []
    for rid in RANGES:
        g = J(f"step04/{rid}/gt_summary.json")
        if not g:
            rows.append([rid] + ["(없음)"] * 9); continue
        h = g["height_alignment"]; c = g.get("alignment_check_on_depth_maps", {}); L_ = g["labels"]; ex = g.get("exclusion_cells_in_range") or {}
        lw = L_.get("LoD2", {}); la = L_.get("ALS", {})
        rows.append([rid, f"{g['uls_points']:,}", f"{g['transient']['points_removed']:,}", f"{h['shift_m']:+.3f} ({h.get('v2_survey_cell_shift_m') and format(h['v2_survey_cell_shift_m'], '+.3f')})",
                     f"{f(c.get('ground_median_mvs_minus_gt_m'))} / {f(c.get('building_median_mvs_minus_gt_m'))}",
                     f"{ex.get('trees', 0):,} / {ex.get('transient', 0):,} / {ex.get('prior_side_trees', 0):,}",
                     pct(lw.get("roof", {}).get("with_gt", 0), lw.get("roof", {}).get("units", 0)), f(lw.get("wall_coverage"), 3),
                     f"{lw.get('roof', {}).get('true_conflict', 0):,} / {lw.get('wall', {}).get('true_conflict', 0):,}",
                     f"{la.get('roof', {}).get('true_conflict', 0):,} ({pct(la.get('roof', {}).get('true_conflict', 0), la.get('roof', {}).get('with_gt', 0))})"])
    L.append(table(["범위", "드론 LiDAR 점", "일시 반사 지운 점", "높이 맞춤 (m) (v2 값)", "맞춘 뒤 MVS−참값: 지면 / 건물 (m)", "제외 칸: 나무 / 일시 반사 / 사전 쪽 나무",
                    "LoD2 지붕 참값 덮음", "LoD2 벽 피복", "LoD2 참 충돌 지붕 / 벽", "항공 LiDAR 참 충돌 지붕"], rows))
    L.append("")


def sec_cases(L):
    L.append("## T2 경우별 집계 (찾기 범위, 범위 허용 오차)\n")
    r1, r2, r3, r4, r5, r8 = [], [], [], [], [], []
    for rid in RANGES:
        c = J(f"step05/{rid}/cases.json")
        if not c:
            continue
        if "case1_LoD2" in c:
            b = c["case1_LoD2"]
            for k in ("roof", "wall"):
                bb = b[k]["bins"]; n = b[k]["units"]
                r1.append([rid, k, f"{n:,}"] + [f"{bb[x]['units']:,} ({pct(bb[x]['units'], n)})" for x in ("<=1", "1-2", "2-4", ">4")])
            t = b["types_true_conflict"]
            r8.append([rid] + [f"{t[x]['units']:,}" for x in ("curved", "wall position", "eave", "rooftop structure", "other")] + [f"{c.get('case8_LoD2', {}).get('units', 0):,}"])
        for pr in ("LoD2", "ALS"):
            k2 = c.get(f"case2_{pr}")
            if k2:
                bj = k2["by_judgment"]
                r2.append([rid, pr, f"{k2['missing_units_on_surfaces_with_support']:,}",
                           f"{bj['conflict']['true_conflict']:,} / {bj['conflict']['true_agree']:,}", f"{bj['agree']['true_agree']:,} / {bj['agree']['true_conflict']:,}",
                           f"{bj['mixed']['units']:,}", f"{bj['insufficient']['units']:,}", f"{k2['right']:,} / {k2['wrong']:,}",
                           " · ".join(f"{KO[n_]} {k2['reasons'][n_]['units']:,}" for n_ in ("textureless", "shadow", "oblique", "other")), f"{k2['surfaces_with_mixed']}/{k2['surfaces']}"])
            k4 = c.get(f"case4_{pr}")
            if k4:
                r4.append([rid, pr, f"{k4['units']:,} ({pct(k4['units'] * 1.0, k4['units'] / max(k4['share'], 1e-9))})", f"{k4['with_gt']:,}", f"{k4['inherit_right']:,} / {k4['inherit_wrong']:,}"])
            k5 = c.get(f"case5_{pr}")
            if k5:
                ab = k5.get("absent_structure", {})
                r5.append([rid, pr, f"{k5['true_conflict']:,}", f"{k5['prior_in_front']:,} ({f(k5['front_area_m2'], 0)} m²)", f"{k5['prior_behind']:,} ({f(k5['behind_area_m2'], 0)} m²)",
                           f"{ab.get('blobs', 0)}개 {f(ab.get('area_m2'), 0)} m²"])
        k3 = c.get("case3")
        if k3:
            n = k3["counts"]
            r3.append([rid, f"{n['a1_px']:,}", f"{n['a1_wrong']:,} ({pct(n['a1_wrong'], n['a1_px'])})", f"{n['a1_wrong_prior_agree']:,} ({pct(n['a1_wrong_prior_agree'], n['a1_wrong'])})",
                       f"{n['a0_photometric_px']:,}", f"{n['a0_photometric_wrong']:,} ({pct(n['a0_photometric_wrong'], n['a0_photometric_px'])})", f"{k3['blobs_a']} / {k3['blobs_b']}"])
        if "case5_LoD2_cause" in c:
            cc = c["case5_LoD2_cause"]
            r5.append([rid, "LoD2 원인", f"지붕 참 충돌 {cc['true_conflict_roof']:,}", f"표현 차이(항공 LiDAR가 참값과 맞음) {cc['als_matches_gt_representation']:,}",
                       f"시간 변화 후보(항공 LiDAR도 다름) {cc['als_also_off_time_change_candidate']:,}", f"항공 LiDAR 없음 {cc['no_als']:,}"])
    L.append("### 경우 1 LoD2 |참값 − 사전 정보| / τ 구간 (패치 수)\n")
    L.append(table(["범위", "면", "참값 있는 패치", "≤1배", "1~2배", "2~4배", ">4배"], r1)); L.append("")
    L.append("### 경우 1 참 충돌의 종류 (자동) 와 경우 8 (1~2배 패치)\n")
    L.append(table(["범위", "곡면", "벽 위치", "처마", "옥상 구조", "기타", "경우 8: 1~2배"], r8)); L.append("")
    L.append("### 경우 2 판정의 전파 (지지 패치가 있는 표면의 결측 패치)\n")
    L.append(table(["범위", "사전 정보", "결측 패치", "충돌 전파: 참 충돌 / 참 일치", "일치 전파: 참 일치 / 참 충돌", "혼재", "근거 부족", "맞음 / 틀림", "결측 까닭(패치 수)", "혼재 있는 표면/표면"], r2)); L.append("")
    L.append("### 경우 3 영상이 틀린 곳 (LoD2 건물 면 픽셀, 참값 깊이 있는 곳)\n")
    L.append(table(["범위", "신뢰도 1 픽셀", "(가) 틀림", "그 가운데 사전 정보 참 일치(잘못 충돌로 읽힘)", "신뢰도 0·광도 깊이 있음", "(나) 틀림", "덩어리 (가)/(나)"], r3)); L.append("")
    L.append("### 경우 4 못 본 곳 (비가시 패치)\n")
    L.append(table(["범위", "사전 정보", "비가시 패치 (범위 패치 중)", "참값 있음", "이어받으면 맞음 / 틀림"], r4)); L.append("")
    L.append("### 경우 5 변화의 방향\n")
    L.append(table(["범위", "사전 정보", "참 충돌", "사전 정보가 앞", "사전 정보가 뒤", "사전 정보에 없는 구조(덩어리)"], r5)); L.append("")


def sec_case6(L):
    c = J("step10/case6.json")
    L.append("## T2.6 경우 6 관측의 양 (B0 대상 건물 + 2 m)\n")
    if not c:
        L.append("(없음)\n"); return
    rows = []
    for k, v in c["conditions"].items():
        for kn in ("roof", "wall"):
            x = v.get(kn)
            if not x:
                continue
            vt = x.get("vs_true", {})
            rows.append([k, kn, v["views"], f(v["tau_roof"]), f(v["tau_wall"]), pct(x["support_share"], 1), pct(x["missing_share"], 1), pct(x["invisible_share"], 1),
                         pct(x["support_conflict_share"], 1), pct(x["inherit_area_share"], 1),
                         f"{vt.get('support_right', '–')} / {vt.get('support_wrong', '–')}", f"{vt.get('propagated_right', '–')} / {vt.get('propagated_wrong', '–')}",
                         f"{vt.get('inherited_true_agree', '–')} / {vt.get('inherited_true_conflict', '–')}"])
    L.append(table(["조건/사전 정보", "면", "학습 영상", "τ 지붕", "τ 벽", "지지", "결측", "비가시", "지지 중 충돌", "이어받는 몫(비가시+미판정)",
                    "지지 표: 맞음/틀림", "전파: 맞음/틀림", "이어받음: 참 일치/참 충돌"], rows))
    L.append("")


def sec_case9(L):
    L.append("## T2.9 경우 9 구역별 정합 (80 m 구역, 관찰만)\n")
    rows = []
    for rid in ("R1", "R4"):
        c = J(f"step10/case9_{rid}.json")
        if not c:
            continue
        for pr, v in c["result"].items():
            for t in v["tiles"]:
                rows.append([rid, pr, str(t["tile"]), f"{t['fit_pixels']:,}", "예" if t["estimable"] else "아니오", f"{t['shift_minus_range_norm_m']:.3f}",
                             f"{f(t['gate_nmad_range_shift'])} → {f(t['gate_nmad_tile_shift'])}", f"{f(t['allface_nmad_range_shift'])} → {f(t['allface_nmad_tile_shift'])}"])
    L.append(table(["범위", "사전 정보", "구역", "맞춤 픽셀", "수평 추정 가능", "구역 이동 − 범위 이동 (m)", "지붕 높이차 NMAD 범위 이동→구역 이동", "전체 건물 면 NMAD 범위 이동→구역 이동"], rows))
    L.append("")


def sec_boxes(L):
    s = J("step06/box_stability.json")
    L.append("## T3 상자 크기 규칙 (지금 MVS)\n")
    if not s:
        L.append("(없음)\n"); return
    rows = []
    for r in s["rows"]:
        rows.append([r["rid"], r["prior"], f"{r['side_m'][0]:.0f} × {r['side_m'][1]:.0f}", r["train_views"], r["eval_views"], f(r["tau_roof"]), f(r["tau_wall"]),
                     "(" + ", ".join(f"{x:+.3f}" for x in r["shift"]) + ")", f"{r['n_roof']:,} / {r['n_wall']:,}"])
    L.append(table(["상자_띠", "사전 정보", "크기 (m)", "학습 영상", "평가 영상", "τ 지붕", "τ 벽", "정합 이동", "표본 지붕/벽"], rows)); L.append("")
    rows = []
    for b, v in s["boxes"].items():
        for pr in ("LoD2", "ALS"):
            for ck in v["per_prior"][pr].get("checks", []):
                rows.append([b, pr, f"{ck['band']} → {ck['next']}", pct(ck["d_tau_roof"], 1), pct(ck["d_tau_wall"], 1), f"{ck['d_shift_m']:.3f}", "예" if ck["stable"] else "아니오"])
    L.append(table(["상자", "사전 정보", "띠 비교 (m)", "τ 지붕 차", "τ 벽 차", "이동 차 (m)", "안정"], rows)); L.append("")


def sec_box_final(L):
    L.append("## T1 상자와 물음 (사용자 결정 23:02: 상자 = 평가 범위 + 10 m, τ·정합은 찾기 범위 값 고정, 상자 MVS는 학습 영상만)\n")
    q = J("step06/box_questions_box.json")
    if not q:
        L.append("(없음)\n"); return
    rows = []
    for b, v in q["boxes"].items():
        lo, al = v["LoD2"], v["ALS"]
        rows.append([b, v["search_range"],
                     " / ".join(f"{lo['q1_bins'][k]:,}" for k in ("<=1", "1-2", "2-4", ">4")),
                     f"{lo['q2']['right']:,}/{lo['q2']['wrong']:,} (충돌→맞음 {lo['q2']['conflict_moved_right']:,}, 일치→맞음 {lo['q2']['agree_moved_right']:,}, 혼재 {lo['q2']['mixed']:,})",
                     f"{al['q2']['right']:,}/{al['q2']['wrong']:,}",
                     f"{v.get('q3_blobs_a', {}).get('blobs', 0)}개 {f(v.get('q3_blobs_a', {}).get('area_m2'), 0)} m²",
                     f"LoD2 {lo['q4']['inherit_right']:,}/{lo['q4']['inherit_wrong']:,} · 항공 {al['q4']['inherit_right']:,}/{al['q4']['inherit_wrong']:,}",
                     f"LoD2 앞 {lo['q5']['prior_in_front']:,} 뒤 {lo['q5']['prior_behind']:,} · 항공 앞 {al['q5']['prior_in_front']:,} 뒤 {al['q5']['prior_behind']:,}",
                     f"{lo['q8_1to2tau']['roof']:,} / {lo['q8_1to2tau']['wall']:,}",
                     "B0 네 조건" if v.get("q6") else "", "대부분 변한 장면" if v.get("q7") else "", {"R1rep": "R1 80 m 구역", "R4weak": "R4 80 m 구역"}.get(b, "")])
    L.append(table(["상자", "실행", "물음 1: LoD2 |차|/τ ≤1/1~2/2~4/>4", "물음 2: LoD2 전파 맞음/틀림", "물음 2: 항공 전파 맞음/틀림", "물음 3: 신뢰도 1 오측정 덩어리(지붕형)",
                    "물음 4: 비가시 이어받음 맞음/틀림", "물음 5: 참 충돌 방향", "물음 8: 1~2배 지붕/벽", "물음 6", "물음 7", "물음 9"], rows))
    L.append("")
    rows = []
    for rid in ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"):
        for pr in ("LoD2", "ALS"):
            s = J(f"step06/box_stage1/{rid}/{pr}/summary.json")
            if not s:
                continue
            fx = s.get("fixed") or {}
            tb = fx.get("tolerance_box", {}); rb = fx.get("registration_box", {})
            col = J(f"mvs/box_{rid}/colmap_receipt.json") or {}
            rows.append([rid, pr, s["views"], len(s.get("views_without_depth_map", [])), f"{col.get('seconds', '–')}",
                         f"{f(s['tolerance']['roof']['tau'])} / {f(s['tolerance']['wall']['tau'])}", "(" + ", ".join(f"{x:+.3f}" for x in s["registration"]["shift_applied"]) + ")",
                         f"{f(tb.get('roof', {}).get('tau'))} / {f(tb.get('wall', {}).get('tau'))}", "(" + ", ".join(f"{x:+.3f}" for x in rb.get("shift_applied", [0, 0, 0])) + ")",
                         pct(s["support_vote"]["conflict"]["area_m2"], s["support_vote"]["agree"]["area_m2"] + s["support_vote"]["conflict"]["area_m2"])])
    L.append(table(["상자", "사전 정보", "학습 영상(깊이 지도 있음)", "깊이 지도 없는 영상", "MVS 시간 (s)", "쓴 τ 지붕/벽 (찾기 범위)", "쓴 정합 이동",
                    "상자 자체 τ 지붕/벽 (참고)", "상자 자체 정합 (참고)", "지지 중 충돌"], rows))
    L.append("")
    c7 = J("step10/case7.json")
    if c7:
        L.append("### 경우 7 대부분이 변한 장면 (B173만)\n")
        rows = []
        for k, v in c7["result"].items():
            rows.append([k, v["views"], f"{f(v['tau_roof'])} / {f(v['tau_wall'])}", "(" + ", ".join(f"{x:+.2f}" for x in v["shift"]) + ")",
                         pct(v["roof_record"]["clipped_share"] or 0, 1), pct(v["support_conflict_share"], 1), pct(v.get("true_conflict_share", 0) or 0, 1),
                         f"{v.get('support_vs_true', {}).get('right', '–')}/{v.get('support_vs_true', {}).get('wrong', '–')}",
                         f"{v.get('propagated_vs_true', {}).get('right', '–')}/{v.get('propagated_vs_true', {}).get('wrong', '–')}"])
        L.append(table(["실행/사전 정보", "학습 영상", "τ 지붕/벽", "정합 이동", "걸러낸 비율(지붕)", "지지 중 충돌", "참 충돌 비율", "지지 표 맞음/틀림", "전파 맞음/틀림"], rows))
        L.append("")
    rows = []
    for b in ("B173nb", "B0"):
        c = J(f"step06/consecutive15_{b}.json")
        if c and c.get("views"):
            rows.append([b, f"{c['views'][0][4:19]} ~ {c['views'][-1][4:19]}", c["windows_ok"], f"{c['share_current_mvs']:.3f}", f"{c.get('share_rebuilt_13', float('nan')):.3f}",
                         ", ".join(x[-12:-4] for x in c["test"])])
    if rows:
        L.append("### 연속 15장 후보\n")
        L.append(table(["상자", "15장 (촬영 순서)", "규칙을 만족한 창 수", "마스크 1 비율: 지금 MVS", "마스크 1 비율: 학습 13장 MVS", "평가로 뗀 2장"], rows))
        L.append("")


def sec_checks(L):
    c = J("step11/checks.json")
    L.append("## T6 구현 확인\n")
    if not c:
        L.append("(없음)\n"); return
    rows = [[k, v["views"], v["party_wall_pairs"], v["caps"], f"{v['rays_before']:,}", f"{v['rays_after']:,}", v["views_with_before"], v["views_with_after"]] for k, v in c["gaps"].items()]
    L.append(table(["범위", "시점", "맞댄 벽 겹침", "덮개 수", "틈 시선 막기 전", "막은 뒤", "틈 있는 시점 앞", "뒤"], rows)); L.append("")
    rows = []
    for k, v in c["als_orientation"].items():
        cm = v.get("cell_method", {})
        a_ = cm.get("angle_initial_vs_patch_face_deg", {}); b_ = cm.get("angle_vertex_vs_patch_face_deg", {})
        rows.append([k, f"{v['points']:,}", f"{v['seated']:,}", f"{v['unseated']:,}", f"{v['unseated_by_class']['2 ground']:,} / {v['unseated_by_class']['6 building']:,}",
                     f"{a_.get('max', float('nan')):.1e}", f"{f(b_.get('p50'), 1)} / {f(b_.get('p95'), 1)}"])
    L.append(table(["범위", "항공 LiDAR 점", "패치에 앉은 점", "앉지 않은 점", "앉지 않은 점: 분류 2 / 6", "처음 방향−패치 법선 최대 (°)", "비교: 꼭짓점 법선−패치 법선 중앙값/95 % (°)"], rows))
    L.append("")


def sec_geogs(L):
    g = J("step08/geogs_regions.json")
    L.append("## T7 GeoGS 그림 6(a) 영역 (근사)\n")
    if not g:
        L.append("(없음)\n"); return
    rows = []
    for k, r in g["regions"].items():
        ov = ", ".join(f"{n} {v['share_of_region'] * 100:.0f} %" for n, v in r["overlaps"].items() if not n.startswith("box ") and v["share_of_region"] >= 0.05)
        rows.append([k, f"{r['extent_u_m']:.0f} × {r['extent_v_m']:.0f}", f(r["area_m2"], 0), ov])
    L.append(table(["영역", "크기 u × v (m)", "넓이 (m²)", "겹침(영역 넓이 중 5 % 이상)"], rows)); L.append("")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="tables_v1.md")
    a = ap.parse_args()
    L = ["# PHD-MAIN-PREP-MEASURE-v1 표 (자동 생성, step12_tables.py)\n"]
    for fn in (sec_box_final, sec_stage1, sec_judgment, sec_gt, sec_cases, sec_case6, sec_case9, sec_boxes, sec_checks, sec_geogs):
        try:
            fn(L)
        except Exception as e:  # visible failure, the other tables still written
            L.append(f"\n({fn.__name__} 실패: {type(e).__name__}: {e})\n")
    (OUT / a.out).write_text("\n".join(L))
    print("tables", OUT / a.out)


if __name__ == "__main__":
    main()
