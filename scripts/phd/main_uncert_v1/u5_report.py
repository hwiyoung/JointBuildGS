"""PHD-MAIN-UNCERT-v1 최종 보고서 (order 10) from answers.json, the tables and figure json of the chosen ring radius, the 일 1 tables, the
logs. Values only, no interpretation.

  python u5_report.py   -> /docs/본실험_불확실도지도_보고_v1.md   scientific_verdict: null."""
import json
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u3_lib as L  # noqa: E402
import u5_final as F  # noqa: E402
import uc_common as U  # noqa: E402
from u3_lib import fmt, md_table  # noqa: E402

S, T, FIGR = F.S, F.T, F.FIGR
FD = U.DOCS / FIGR


def fj(name):
    p = FD / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def fig(name, label, caption):
    j = fj(name)
    if j is None:
        return f"**{label}.** 그림 없음.\n"
    return f"**{label}.** {j.get('footer', '')}\n\n![{label}]({FIGR}/{name}.png)\n\n- 캡션 재료: {caption}\n"


def main():
    a = json.loads((U.DOCS / "tables/answers.json").read_text())["answers"]
    A_ = F.answers()
    out = []
    out.append("# 영역마다 세 자료의 불확실도 지도 — 최종 보고\n")
    out.append(f"- 작업: PHD-MAIN-UNCERT-v1 · 발주문 v2(2026-10-23, `본실험_불확실도지도_발주문_v2.md`) · 학습 없음 · GPU 없음 · 브랜치 `exp/main-experiment`")
    out.append(f"- 쓴 때: {U.now()} · 설정 잠금 sha256 4044e9b8…(01:41), 자리 둘째 잠금(01:54) · 고리 크기 {L.rlabel(S)}")
    out.append("- 중간 보고: `중간보고_v1.md`(고리 1.5 m, 커밋 62429912) · 숫자표: `불확실도지도_숫자표_v1*.md`")
    out.append("- scientific_verdict: null\n")
    # 1
    out.append("## 1. 물음과 답\n")
    out.append(md_table(["물음", "답", "볼 값"], F.ans_rows(A_), left=True))
    out.append("\n- 등급은 발주 10절의 기준을 그대로 썼다. 물음 1~3, 9는 세 지역을 합한 패치 묶음(LoD2 패치, 항공 LiDAR 패치)마다 판정하고 둘을 합쳤다. "
               "물음 1·2의 '가능·근거 불완전'은 발주 글대로 '순위 상관 0.3 이상이거나 커지지 않는 구간이 하나'다. 물음 4는 경우마다 보정 두 칸 가운데 큰 쪽의 비율로 판정했다.")
    out.append("- 물음 9의 규칙: 패치 묶음마다 세 실제 오차 가운데 둘 이상에서 순위 상관이 0.05 넘게 높고 틀린 점으로 정한 곡선 아래 넓이(두 자리)도 높으면 그 쪽 '확인', "
               "한 조건만 맞고 다른 쪽은 아무것도 이기지 않으면 '가능·근거 불완전', 그 밖은 '비슷함'.\n")
    # 2
    rc = json.loads((U.DOCS / "tables/ring_choice.json").read_text())["values"]
    out.append("## 2. 일 1의 확인과 맞춰 보기, 고른 고리 크기\n")
    out.append("**찾은 것.** 자세한 표는 [tables/u1_found.md](tables/u1_found.md), [tables/u1_checks.md](tables/u1_checks.md).\n")
    out.append(md_table(["물음", "적은 것"], [
        ["MVS 깊이 지도", "`S0/fork_inputs/s61/<지역>/maps/mvs`(→ `S0/s61/export/<지역>/LoD2/mvs`, COLMAP 기하 단계 깊이, NaN = 없음), 관측 신뢰도 마스크 `maps/conf`(0/1; 깊이가 있는 화소와 같음). "
         "학습 영상 " + ", ".join(f"{U.SITE_KO[x]} {json.loads((U.PTS / x / 'mvs_a.json').read_text())['views']}장" for x in U.SITES) + ". 깊이 = 광축 방향 깊이(아래 확인). 마스크 전 깊이(판 나): B173 주변 `S0/s61/export_maskoff/B173nb_b10/LoD2`, B0·R1 `S2/s61/export_maskoff/<지역>/LoD2`(광도 단계 깊이)"],
        ["카메라", "`S0/fork_inputs/s61/<지역>/scene_LoD2/sparse/0`(images.bin, cameras.bin) + `jbgs_calibration.json` K(cx, cy는 0.5 뺀 값), 937장 COLMAP 모델 좌표(EPSG:25832 − world shift, 축척 1). "
         "두 축 평가 mvs_surface.cameras 그대로. 사전 정보 렌더 깊이와 같은 카메라: 렌더 깊이를 같은 식으로 풀면 LoD2 면에서 0.03 mm 안"],
        ["원래 항공 LiDAR 점", "P0 `raw/als/{690_5335,690_5336,691_5335,691_5336}.laz`, 분류 2(지면)·6(건물), 실험 지역 + 3 m 안 9.1만~11.5만 점. 좌표 = 사전 정보 면과 같은 다리(+45.7 m)와 정합 이동. "
         "원래 점의 자리 p_A는 사전 정보 면에서 중앙값 0.0 cm(TIN이 그 점을 지남)"],
        ["LoD2", "P0 `raw/lod2/690_5336.gml`(CityGML 1.0), 면 = `DR/s02_box/<지역>/lod2_surfaces.json`의 ext와 패치 surf_ext. 지붕 형태 `bldg:roofType` 있음(B0 1000·3100·3200, B173 주변 1000·3100·9999, R1 1000·3900)"],
        ["패치", "영역 파일에 법선이 없어 `defs_s1.patch_geometry`의 법선(접선 외적, 위가 바깥; LoD2 벽은 면 법선)을 씀. LoD2 벽 법선은 바닥 윤곽으로 점검해 B173 주변 면 132(13패치)만 뒤집음"],
        ["칸", "두 축 평가의 잠근 칸 규칙을 다시 셈. 여섯 경우 모두 두 축 평가가 저장한 칸과 패치마다 같음"],
        ["참값", "`S1/defs/<지역>/gt_classes.npz` xyz_gt_points(B0는 주 참값 xyz_gt_primary 더함)에서 뺀 칸(나무, 일시 물체) 제외, 지역마다 650만~980만 점"]], left=True))
    c = json.loads((U.DOCS / "tables/u1_checks.json").read_text())["values"]
    out.append("\n**맞춰 보기.**\n")
    rows = []
    for k, v in c.items():
        if k.endswith(("지붕꼴", "벽꼴")):
            s, p, fn = k.rsplit("_", 2)
            rows.append([U.case_ko(s, p), fn, fmt(v["patches"], "int"), fmt(v["p_M_med_cm"], "v", v["patches"]), fmt(v["p_M_nmad_cm"], "v", v["patches"]),
                         f"{v['tau_over_2_5_cm']:.1f}", v["flag"] if v["patches"] >= 30 else "표본 부족"])
    out.append(md_table(["경우", "면", "다듬기 패치", "p_M 중앙값 (cm)", "p_M NMAD (cm)", "τ ÷ 2.5", "NMAD와 τ ÷ 2.5"], rows))
    out.append("\n- 2.8 멈춤 점검: 항공 LiDAR 경우 다듬기 패치(무작위 3,000개)에서 p_M 중앙값은 B0 1.1, B173 주변 8.1, R1 1.7 cm(기준 10 cm 안). "
               "영상 하나의 점으로 구한 값은 영상 사이에서 18.1, 18.7, 76.5 cm 벌어져 멈춤 조건이 걸렸다. 깊이 뜻(광축 깊이)과 좌표를 확인했고(렌더 깊이 0.03 mm 안, 광선 거리로 읽으면 15~40 cm), "
               "같은 패치의 짝지은 차의 크기는 중앙값 1.3~2.0 cm, 벗어난 영상(B0 4, B173 주변 6, R1 25장)은 R1에서 지붕을 멀리서(113~207 m) 스치듯 본 비스듬한 영상이다. "
               "여쭈었고 사용자 결정(10월 23일 09:31) '그대로 진행'.")
    out.append("\n**고른 고리 크기 (1.7).** " + json.loads((U.DOCS / "tables/ring_choice.json").read_text())["note"] + "\n")
    rows = []
    for s, v in rc["per_site"].items():
        for R_ in U.D["ring_radii_m"]:
            x = v["per_R"][str(R_)]
            rows.append([U.SITE_KO[s], "+".join(U.SITE_KO[b] for b in v["bands_used"]), f"{R_:g}", fmt(x["n_mvs"], "int"), fmt(x["rho_mvs"], "rank"), fmt(x["n_als"], "int"),
                         fmt(x["rho_als"], "rank"), fmt(x["criterion"], "rank"), "고름" if float(v["pick"]) == R_ else ""])
    out.append(md_table(["지역", "띠", "R (m)", "MVS 패치", "ρ_MVS", "항공 LiDAR 패치", "ρ_항공 LiDAR", "잣대", ""], rows))
    out.append(f"\n- 평가 범위의 표와 그림은 {L.rlabel(S)}로 냈다. 다른 크기의 표는 `tables/R1.0`, `tables/R1.5`, `tables/R3.0`에 있다.\n")
    # 3
    out.append("## 3. 일 2~5의 표와 그림\n")
    out.append("### 3.1 일 2: 값이 있는 비율과 불확실도의 분포\n")
    t1 = F.jv("t1_value_share")
    rows = [[r["case"], r["data"], fmt(r["patches"], "int"), fmt(r["value"], "pct", r["patches"]), fmt(r["no_face"], "pct", r["patches"]), fmt(r["short"], "pct", r["patches"]),
             fmt(r["one_sided"], "pct", r["patches"]), fmt(r["weak_final"], "pct", r["patches"]), "해당 없음" if r["thinned"] is None else fmt(r["thinned"], "pct", r["patches"])]
            for r in t1 if r.get("face") == "전체"]
    out.append("표 1 (평가 범위, 모든 면; 지붕꼴·벽꼴과 칸마다는 [표 폴더](" + f"tables/{F.FOLDER}/t1_value_share.md" + "))\n")
    out.append(md_table(["경우", "자료", "패치", "값 있음", "면 없음", "점 부족", "한쪽 고리*", "지지 약함(다시 맞춘 평면)*", "솎음*"], t1 and rows))
    out.append("\n- \\* 값이 있는 패치 가운데. 발주 글 그대로의 '지지 약함'(고른 평면의 잔차가 2.5 s₀ 안인 고리 점이 절반 미만)은 만들어지는 꼴상 늘 0이다. 후보 없음(45° 안 평면이 없음)은 표 폴더에 있다.\n")
    t2 = F.jv("t2_u_distribution")
    rows = [[r["case"], r["data"], r["face"], fmt(r["u"]["n"], "int"), fmt(r["inner_points"], "int")] + [fmt(r["u"][k], "v", r["u"]["n"]) for k in ("p50", "p25", "p75", "p90")]
            + [fmt(r["a"]["p50"], "v", r["u"]["n"]), fmt(r["s"]["p50"], "v", r["u"]["n"])] for r in t2 if "face" in r and r["data"] != "MVS 판 나"]
    out.append("표 2 (cm; 칸마다와 판 나는 표 폴더)\n")
    out.append(md_table(["경우", "자료", "면", "패치", "안쪽 원 점", "u 중앙값", "25 %", "75 %", "90 %", "어긋남 중앙값", "흩어짐 중앙값"], rows))
    out.append("\n### 3.2 일 3: 지도\n")
    cap_u = "평가 범위를 위에서 본 정사영(북쪽 위, 0.1 m 화소, 높은 패치가 위). 색 0~50 cm(viridis), 50 cm 넘음 = 50 cm 색 위 점 무늬, 빗금 = 값 없음, 흰색 = 그 묶음의 패치 없음. 검은 테두리 = 5.2의 자리"
    for s in U.SITES:
        out.append(fig(f"A_{s}", f"그림 A — {U.SITE_KO[s]}", "(가) MVS 판 가 u를 LoD2 패치에, (나) 원래 항공 LiDAR 점의 u를 항공 LiDAR 패치에, (다) LoD2 20 cm를 LoD2 패치에. " + cap_u))
    for s in U.SITES:
        for az in ("225", "45"):
            out.append(fig(f"A_oblique_{s}_az{az}", f"그림 A-비스듬 — {U.SITE_KO[s]}, 방위 {az}°",
                           "그림 A와 같은 칸을 연직에서 45°, 방위 " + az + "°에서 본 원근(두 축 평가 9.1과 같은 시점 규칙), 패치마다 5 × 5 점, 가까운 점이 보임. 색은 그림 A와 같음"))
    for s in U.SITES:
        out.append(fig(f"B_{s}", f"그림 B — {U.SITE_KO[s]}", "MVS 무게 비율 w_M = u_사전² ÷ (u_M² + u_사전²) (판 가). 주황 0 = 사전 정보가 이끎, 흰색에 가까움 0.5, 파랑 1 = MVS가 이끎, "
                                                              "회색 = 둘 다 값 없음. 한 자료만 값이 있으면 그 끝 색. (가) MVS와 항공 LiDAR(항공 LiDAR 패치), (나) MVS와 LoD2(LoD2 패치)"))
    for s in U.SITES:
        out.append(fig(f"C_{s}", f"그림 C — {U.SITE_KO[s]}", "(가) 어긋남, (나) 흩어짐. MVS 판 가, LoD2 패치. 색은 그림 A와 같음"))
    for s in U.SITES:
        for p in U.PRIORS:
            out.append(fig(f"D_{s}_{p}", f"그림 D — {U.SITE_KO[s]}, {'MVS(LoD2 패치)' if p == 'LoD2' else '항공 LiDAR(항공 LiDAR 패치)'}",
                           "(가) 고리 1.0 m, (나) 1.5 m, (다) 3.0 m. 색은 그림 A와 같음"))
    cap_e = ("위 = 자리와 둘레 2 m를 키운 지도((가) MVS u, (나) 사전 정보 u, (다) MVS 무게 비율; 검은 테두리 = 자리). 아래 = 자리의 가장 큰 덩어리(0.36 m로 이음)를 그 긴 축(수평 주성분)으로 자른 단면, "
             "띠 폭 0.5 m, 덩어리 끝에서 2 m까지. 회색 = 띠 안 MVS 점(1 m마다 400점까지), 검정 = 참값 점, 주황 = 단면선 0.125 m 안 사전 정보 패치, 청록 = 단면선 위 패치(1 m마다 하나)의 안쪽 원 점, "
             "점선 = 그 패치의 고리 평면, 보라 막대 = 무게 평균의 자리. 세로 늘림 배율은 축 이름에")
    pl = json.loads((U.WORK / "places.json").read_text())["places"]
    for p in ["glass_strip", "glass_dome", "flat_roof", "b173_wing", "r1_step_roof"] + sorted(k for k in pl if k.startswith("chosen_") and "status" not in pl[k]):
        ko = pl.get(p, {}).get("ko") or {"b173_wing": "B173 날개"}.get(p, p)
        out.append(fig(f"E_{p}", f"그림 E — {ko}", cap_e + ("; (마) = 판 나(마스크 전)" if p.startswith("glass") else "")))
    out.append("### 3.3 일 4: 참값으로 점검\n")
    out.append("**6.1 불확실도가 실제 오차를 따라가는가.**\n")
    J = F.jv("t61_u_vs_error")
    rows = []
    for b in J["bins_u"]:
        if b["data"] == "MVS 판 나" or not b["unit"].startswith("세 지역"):
            continue
        for x in b["rows"]:
            rows.append([b["unit"].replace("세 지역 합 · ", "") + " 패치", b["data"], x["bin"], fmt(x["n"], "int"), fmt(x["area_m2"]), fmt(x["p50"], "v", x["n"]),
                         fmt(x["p25"], "v", x["n"]), fmt(x["p75"], "v", x["n"]), fmt(x["p90"], "v", x["n"])])
    out.append(md_table(["패치 묶음(세 지역 합)", "자료", "u 구간 (cm)", "패치", "넓이 m²", "e 중앙값", "25 %", "75 %", "90 %"], rows))
    rows = []
    for r in J["rank"]:
        if r["data"] == "MVS 판 나":
            continue
        f = r["faces"]
        n = f["전체"]["n"]
        rows.append([r["unit"], r["data"], fmt(n, "int"), fmt(f["전체"]["rho_u_e"], "rank", n), fmt(f["지붕꼴"]["rho_u_e"], "rank", f["지붕꼴"]["n"]), fmt(f["벽꼴"]["rho_u_e"], "rank", f["벽꼴"]["n"]),
                     fmt(f["전체"]["rho_a_bias"], "rank", n), fmt(f["전체"]["rho_s_spread"], "rank", n), fmt(f["전체"]["med_e_over_u"], "rank", n)]
                    + [fmt(r["u_q_vs_three"][k], "rank", n) for k in ("u_e", "u_qe", "u_f", "q_e", "q_qe", "q_f")])
    out.append("\n" + md_table(["단위", "자료", "패치", "ρ(u,e)", "지붕꼴", "벽꼴", "ρ(어긋남, 치우침 크기)", "ρ(흩어짐, 퍼짐)", "e ÷ u", "u–e", "u–실제 68.3 %", "u–틀린 점", "q–e",
                                   "q–실제 68.3 %", "q–틀린 점"], rows))
    out.append("\n- 흩어짐과 퍼짐은 같은 안쪽 원 점의 NMAD이고 기준 평면(고리 평면, 참값 평면)만 다르다. 반쯤 틀린 패치와 판 나, q 구간 표는 [표 폴더](" + f"tables/{F.FOLDER}/t61_u_vs_error.md).\n")
    out.append(fig("F_ga_u_vs_e", "그림 F-가", "가로 = u 구간, 세로 = 실제 오차 e(로그). 상자 25~75 %, 가로선 중앙값, 수염 10~90 %. 옅은 회색 띠 = e가 그 u 구간 안. 짙은 파랑 = LoD2 패치, 옅은 파랑 = 항공 LiDAR 패치. 세 지역 합"))
    for s in U.SITES:
        out.append(fig(f"F_ba_half_{s}", f"그림 F-바 — {U.SITE_KO[s]}", "반쯤 틀린 패치(틀린 점 30~50 %)만 (가) u, (나) q로 칠함(색은 그림 A와 같음), 회색 = 그 밖의 값 있는 패치, 황갈 = 참값 평면 없음. LoD2 패치, MVS 판 가"))
    out.append("**6.2 영상이 틀린 패치를 잡는가.**\n")
    Rr = F.jv("t62_roc")
    rows = [[r["unit"], r["data"], r["positives"], fmt(r["scores"]["u"]["n_pos"], "int"), fmt(r["scores"]["u"]["n_neg"], "int")]
            + [fmt(r["scores"][k]["auc"], "rank", min(r["scores"]["u"]["n_pos"], r["scores"]["u"]["n_neg"])) for k in ("u", "어긋남", "흩어짐", "q")]
            + [fmt(r["scores"]["u"]["fpr_half"], "pct", r["scores"]["u"]["n_pos"])] for r in Rr["cells"] if r["unit"].startswith("세 지역")]
    out.append(md_table(["단위", "자료", "양성", "양성 패치", "음성 패치", "AUC u", "어긋남", "흩어짐", "q", "양성 절반 문턱의 잘못 잡음(u)"], rows))
    rows = [[r["unit"], r["data"], fmt(r["scores"]["u"]["n_pos"], "int"), fmt(r["scores"]["u"]["n_neg"], "int")]
            + [fmt(r["scores"][k]["auc"], "rank", min(r["scores"]["u"]["n_pos"], r["scores"]["u"]["n_neg"])) for k in ("u", "어긋남", "흩어짐", "q")] for r in Rr["by_f"] if r["unit"].startswith("세 지역")]
    out.append("\n틀린 점의 비율로 정한 판(30 % 넘음 양성, 10 % 미만 음성):\n\n" + md_table(["단위", "자료", "양성", "음성", "AUC u", "어긋남", "흩어짐", "q"], rows))
    out.append("\n- 경우마다 값은 [표 폴더](" + f"tables/{F.FOLDER}/t62_roc.md).\n")
    out.append(fig("F_na_roc", "그림 F-나", "ROC 곡선, MVS 판 가, 세 지역 합. 선 넷 = u, 어긋남, 흩어짐, q; 오른쪽 아래 숫자 = 곡선 아래 넓이. 양성 = 보존 · 문턱 안, 한계, 이중 오류; 음성 = 다듬기, 보정 두 칸"))
    out.append("**6.3 바뀐 곳에서 MVS는 어떤가.**\n")
    rows = [[r["case"], r["cell"], fmt(r["u"]["n"], "int"), fmt(r["u"]["p50"], "v", r["u"]["n"]), fmt(r["u"]["p75"], "v", r["u"]["n"]), fmt(r["u"]["p90"], "v", r["u"]["n"]),
             fmt(r["w_over_half_area_share"], "pct", r["patches"])] for r in F.jv("t63_changed") if r["data"] == "MVS 판 가"]
    out.append(md_table(["경우", "칸", "u 있는 패치", "u_M 중앙값", "75 %", "90 %", "MVS 무게 비율 0.5 넘는 넓이"], rows))
    out.append("\n**6.4 LoD2 20 cm는 자료와 맞는가.**\n")
    rows = [[r["site"], r["group"], r["basis"], fmt(r["n"], "int")] + [fmt(r.get(k), "v", r["n"]) for k in ("med_cm", "nmad_cm", "q68_cm", "q95_cm")]
            + [fmt(r.get("within20"), "pct", r["n"]), fmt(r.get("within30"), "pct", r["n"]), f"{r['tau_over_2_5_cm']:.1f}"] for r in F.jv("t64_lod2")]
    out.append(md_table(["지역", "줄", "기준", "패치", "중앙값", "NMAD", "차 크기 68 %", "95 %", "20 cm 안", "30 cm 안", "τ ÷ 2.5"], rows))
    out.append("\n" + fig("F_da_lod2", "그림 F-다", "LoD2 지붕꼴 패치(평가 범위). 파랑 = 믿을 만한 MVS(u_M 5 cm 이하 실선, 10 cm 이하 점선)의 p_M 크기 누적 분포, 검정 = 참값 p_G 크기(보정 · 4τ 넘음 뺌). 점선 = 20, 30 cm"))
    out.append("**6.5 놓친 곳과 가장자리.**\n")
    M = F.jv("t65_missed_edge")
    rows = [[r["case"], r["data"], fmt(r["patches"], "int"), fmt(r["missed"], "int"), fmt(r["missed_area_m2"]), fmt(r["share"], "pct", r["patches"]), fmt(r["area_share"], "pct", r["patches"])]
            for r in M["missed"] if r["cell"] == "전체" and r["data"] != "MVS 판 나"]
    out.append(md_table(["경우", "자료", "값·참값 있는 패치", "놓친 패치", "놓친 넓이 m²", "패치 비율", "넓이 비율"], rows))
    rows = [[r["case"], r["data"], r["flag"], r["bin"], fmt(r["u"]["n"], "int"), fmt(r["u"]["p50"], "v", r["u"]["n"]), fmt(r["e"]["p50"], "v", r["u"]["n"])]
            for r in M["edge"] if r["data"] != "MVS 판 나" and r["flag"] == "모든 값"]
    out.append("\n" + md_table(["경우", "자료", "표시", "다른 면까지 (m)", "패치", "u 중앙값", "e 중앙값"], rows))
    out.append("\n- 칸마다 놓친 패치, 한쪽 고리·지지 약함 표시 패치의 가장자리 값은 [표 폴더](" + f"tables/{F.FOLDER}/t65_missed_edge.md).\n")
    for s in U.SITES:
        out.append(fig(f"F_ra_missed_{s}", f"그림 F-라 — {U.SITE_KO[s]}", "빨강 = 놓친 패치(e > 20 cm 그리고 e > 2u), 회색 = 그 밖의 값·참값 있는 패치, 빗금 = 값 없음, 황갈 = 참값 평면 없음. "
                                                                     "(가) MVS 판 가(LoD2 패치), (나) MVS 판 가(항공 LiDAR 패치), (다) 항공 LiDAR"))
    out.append(fig("F_ma_edge", "그림 F-마", "가로 = 다른 면 번호의 패치까지 거리 구간, 세로 = 중앙값(cm). 파랑 u, 검정 e. 세 지역 합"))
    out.append("### 3.4 일 5: 누가 이끄는가, 무게 평균 미리 보기\n")
    rows = [[r["case"], r["cell"], fmt(r["patches"], "int"), fmt(r["w_med"], "rank", r["patches"]), fmt(r["mvs_leads"], "pct", r["patches"]), fmt(r["prior_only"], "pct", r["patches"]),
             fmt(r["mvs_only"], "pct", r["patches"]), fmt(r["none"], "pct", r["patches"])] for r in F.jv("t71_who_leads") if r["data"] == "MVS 판 가"
            and r["cell"] in ("전체", "다듬기", "보정 · 1~4τ", "보정 · 4τ 넘음", "보존 · 거름", "보존 · 문턱 안", "한계", "상속 · 결측", "상속 · 비가시")]
    out.append("**7.1 누가 이끄는가 (넓이 비율, 판 가; 모든 칸은 표 폴더).**\n\n" + md_table(["경우", "칸", "패치", "무게 비율 중앙값", "MVS가 이끎", "사전 정보만", "MVS만", "둘 다 없음"], rows))
    rows = [[r["case"], r["cell"], fmt(r["patches"], "int")] + sum([[fmt(r[k]["med_cm"], "v", r[k]["n"]), fmt(r[k]["within20"], "pct", r[k]["n"])] for k in ("mvs", "prior", "weighted")], [])
            + [fmt(r["z"]["med"], "rank", r["z"]["n"]), fmt(r["z"]["over"], "pct", r["z"]["n"])] for r in F.jv("t72_weighted_preview") if r["data"] == "MVS 판 가"
            and r["cell"] in ("전체", "다듬기", "보정 · 1~4τ", "보정 · 4τ 넘음", "보존 · 거름", "보존 · 문턱 안", "한계", "상속 · 결측")]
    out.append("\n**7.2 무게 평균 미리 보기 — 학습 없음, 미리 보기 (자리의 오차 cm, 판 가).**\n\n"
               + md_table(["경우", "칸", "패치", "MVS만", "20 cm 안", "사전 정보만", "20 cm 안", "무게 평균", "20 cm 안", "z 중앙값", "z > 2.5"], rows))
    out.append("\n- 정성은 그림 E 단면의 보라 막대(무게 평균의 자리)로 보인다.\n")
    # 4
    out.append("## 4. 자리마다의 값\n")
    out.append(F.places_table()[0])
    out.append("\n- 자리 패치 수가 0인 줄(R1 계단 지붕의 항공 LiDAR 쪽 등)은 다른 사전 정보의 패치가 0.25 m 안에 없는 경우다.\n")
    # 5
    out.append("## 5. 바꾼 것, 확인 불가, 결과를 본 뒤 더한 것\n")
    out.append("- **2.8 멈춤 → 사용자 결정 '그대로 진행'.** 영상 사이 벌어짐(18~77 cm)으로 멈춤 조건이 걸렸고 확인 뒤 여쭈었다(2절). 답을 기다리는 동안 1.5 m 셈을 미리 돌렸고(01:54~02:32), 답에 따라 그대로 썼다.")
    out.append("- **'지지 약함'.** 발주 글 그대로(고른 평면의 잔차)는 만들어지는 꼴상 늘 0이라, 다시 맞춘 최소 제곱 평면의 잔차로 센 비율을 옆 열과 6.5에 함께 냈다(셈 전 잠근 설정에 적음).")
    out.append("- **정의 세부(셈 전 잠금).** 층은 양 끝 포함, '여러 층' = 20 % 넘는 층이 끊겨 두 묶음 이상, 사분면 = n에 수직인 두 축의 부호, 점 부족 = 솎기 전 수, MVS 영상 수 = 솎기 전 안쪽 원 점. "
               "q = numpy quantile 선형 보간.")
    out.append("- **셈의 세부(결과 같음).** 최소 중앙 제곱의 가장 작은 중앙값 찾기를 가지치기로 빠르게 함(모의 300벌에서 원래 셈과 같음). MVS 솎기는 열쇠 차례 저장으로 정확히 같은 2,000·8,000점. "
               "고리 점은 열쇠 앞부분(4^-k)에서 찾되 8,000점이 안 되면 더 촘촘한 부분으로.")
    out.append("- **그리는 법만 바꿈.** 그림 E 단면은 자리의 가장 큰 덩어리의 긴 축으로 자름(유리 띠는 떨어진 채광창 여러 개). 확대 지도는 0.05 m 화소에 패치마다 9 × 9 점. 단면의 사전 정보 선은 단면선 0.125 m 안 패치만.")
    out.append("- **확인 불가.** R1 고르게 낮은 평지붕: 앞 작업에 R1 상자의 그런 자리가 없다(기록된 20~30 cm 평지붕은 탐색 지역 R4·R3E, 빈칸 채우기 준비 보고는 R1 상자에 없다고 적음). "
               "유리 띠의 '마스크 통과 90.1 %'는 화소 단위 값이라 이 셈(패치)과 정의가 다르다. 참고로 자리 패치 안쪽 원 점 수의 비율(판 가 ÷ 판 나)을 4절에 적었다.")
    out.append("- **자리.** R1 계단 지붕은 0.25 m 안 항공 LiDAR 패치가 없다. 지역마다 고른 자리는 B0 항공 LiDAR(보정 합, 보존 합), R1 항공 LiDAR(보정 합)에서 2.5 m² 넘는 한 층 덩어리가 없어 '없음'.")
    out.append("- **처음 보는 사람 점검(8.7).** 제목을 자른 그림 13장(그림 꼴마다 하나)을 하위 에이전트 한 번에 보였다. 13장 모두에서 짐작한 물음이 설정의 제목과 같거나 가까웠다"
               "(PH/main_uncert_v1/PHD-MAIN-UNCERT-v1/work/blind/answers_round1.md). 지적에 따라 그리는 법만 고쳤다: 색 막대 이름에 빗금·흰색·검은 테두리의 뜻, 비스듬한 그림은 패치마다 9 × 9 점, "
               "자리 이름 표지를 칸 안으로, 그림 E 단면의 세로 범위를 그 자리 구간의 참값·자리 사전 정보·안쪽 원 점으로, 그림 E (다)의 설명을 칸 제목으로, F-가의 마지막 띠는 100 cm까지, "
               "F-나 칸 제목을 줄이고 수는 아래 줄로, F-다·F-라·F-마 아래 줄에 기준과 뜻, F-마 세 칸의 세로축을 같게. F-바의 두 칸이 비슷해 보인다는 지적은 발주의 꼴(칸 둘, 같은 색 범위) 그대로 두었다. "
               "2회차 점검은 아래 줄.")
    b2 = U.WORK / "blind/answers_round2.md"
    if b2.exists():
        out.append("- **점검 2회차.** " + " ".join(l.strip() for l in b2.read_text().splitlines()[1:] if l.strip())[:900])
    out.append("- **결과를 본 뒤 더함.** 없음(표와 그림의 꼴은 모두 설정과 발주에서 정함). 그림 배치(여백, 색 막대 자리)만 첫 그림을 보고 고쳤다.\n")
    # 6
    q = (U.LOG / "queue.log").read_text().splitlines()
    secs = {}
    for line in q:
        parts = line.split()
        if len(parts) >= 5 and parts[3].startswith("rc=0"):
            secs[parts[2]] = int(parts[4].rstrip("s"))
    grp = [("MVS 점 만들기(여섯 판)", lambda k: k.startswith("u1_mvs")), ("항공 LiDAR·참값 점", lambda k: k == "u1_other"), ("패치 표", lambda k: k == "u1_patches"),
           ("참값 평면(여섯 묶음)", lambda k: k.startswith("u2_gt")), ("2.8 점검과 진단", lambda k: k.startswith(("u2_check", "u2_diag"))), ("자리 풀기", lambda k: k == "u1_places"),
           ("고리 1.5 m 셈(15단계)", lambda k: k.endswith("R1.5") and k.startswith("u2_")), ("고리 1.0·3.0 m 셈(15단계, 두 크기 함께)", lambda k: k.endswith("R1.0_3.0")),
           ("값 모으기", lambda k: k.startswith("u2_merge")), ("표", lambda k: k.startswith(("u3_", "u1_facts"))), ("그림(다시 그린 것 포함)", lambda k: k.startswith("u4"))]
    out.append("## 6. 걸린 시간과 자원\n")
    out.append(md_table(["단계", "초(성공한 실행의 합)"], [[g, sum(v for k, v in secs.items() if f(k))] for g, f in grp]))
    rows = []
    for site in U.SITES:
        sec, pts = 0.0, {}
        for f in sorted(x for x in U.WORK.glob(f"run_*{site}_*.json") if "limit" not in x.name):
            j = json.loads(f.read_text())
            sec += j.get("seconds_loop", 0) + j.get("seconds_build", 0)
            pts[j["data"]] = j["points"]
        rows.append([U.SITE_KO[site], f"{sec:,.0f}"] + [f"{pts.get(k, 0):,}" for k in ("mvs_a", "mvs_b", "als", "gt")])
    out.append("\n지역마다(셈 단계의 트리 만들기와 패치 셈, 세 고리 크기와 참값 평면의 합):\n\n" + md_table(["지역", "초", "MVS 판 가 점", "MVS 판 나 점", "항공 LiDAR 점", "참값 점"], rows))
    out.append("\n- 셈은 CPU 48개(nice 19), 메모리 40 GB 상한의 컨테이너(jointbuildgs:dev, MVS 점은 jointbuildgs:geogs-conf-guided-v1). GPU와 학습 없음. 점 파일 약 3.5 GB(지역마다 MVS 1,900만~2,700만 점 두 판, 참값 650만~980만 점), 패치마다 값 약 0.46 GB.")
    out.append("- 사용자 답을 기다린 시간(01:5x~09:31)은 위 합에 들지 않는다.\n")
    # 7
    out.append("## 7. 검토 기록에 붙일 요약\n")
    s7 = [f"- 세 자료의 불확실도를 같은 꼴(고리 평면에서 안쪽 원 점까지 거리의 어긋남·흩어짐)로 구했다. 고리 크기는 띠 패치로 골랐다({L.rlabel(S)}).",
          f"- 물음 1(MVS 불확실도가 실제 오차를 따라감): {A_['1'][0]}. 물음 2(항공 LiDAR): {A_['2'][0]}. 물음 3(영상이 틀린 패치를 잡음): {A_['3'][0]}.",
          f"- 물음 4(바뀐 곳의 MVS u가 다듬기만큼 작음): {A_['4'][0]}. 물음 5(LoD2 20 cm): {A_['5'][0]}.",
          f"- 물음 9(지금 식과 68.3 % 값): {A_['9'][0]}.",
          "- 놓친 패치(e > 20 cm, e > 2u)와 가장자리, 무게 평균 미리 보기는 6.5, 7.2의 값으로 답했다.",
          "- 2.8 멈춤 조건(영상 사이 벌어짐)이 걸려 확인 뒤 여쭈었고, 사용자 결정으로 그대로 진행했다.",
          "- 학습·GPU 없음. 설정은 첫 셈 전에 잠갔고, 자리는 불확실도 셈 전에 둘째 잠금."]
    out += s7
    (U.DOCS / "본실험_불확실도지도_보고_v1.md").write_text("\n".join(out) + "\n")
    U.log("report", len("\n".join(out)))


if __name__ == "__main__":
    main()
