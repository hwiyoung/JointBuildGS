"""PHD-MAIN-AXES71-v2 중간 보고 (order 0.2, 차례 3): /docs/중간보고_v1.md from the tables of 일 1-8 and the text below. scientific_verdict: null."""
import json
import re

from ax_common import CELLS, DOCS, KEY_KO, TAB, jl, now

T = DOCS / "tables"


def block(path, start, stop=None, keep=None):
    """lines of a md file from the line starting with `start` up to (not incl.) the next line starting with `stop`."""
    L = (T / path).read_text().split("\n")
    i = next(n for n, x in enumerate(L) if x.startswith(start))
    j = next((n for n in range(i + 1, len(L)) if stop and L[n].startswith(stop)), len(L))
    out = [("### " + x[3:]) if x.startswith("## ") else x for x in L[i:j]]
    if keep:
        out = [x for x in out if not x.startswith("|") or x.startswith("| 경우") or x.startswith("|---") or x.startswith("| 칸") or x.startswith("| 판정") or x.startswith("| 구간")
               or any(k in x for k in keep)]
    return out


def sums_only(path, title):
    """the 'LoD2 합' and '항공 LiDAR 합' rows of the GT and result tables of one 일 3 cell file."""
    L = (T / path).read_text().split("\n")
    out = []
    for x in L:
        if x.startswith("*본 방법 두 씨앗"):
            break
        if x.startswith("**") and "참값 기준" in x or x.startswith("**") and "결과 기준" in x:
            out += ["", x.replace(title + " — ", ""), ""]
        elif x.startswith("| 경우") or x.startswith("|---"):
            if out and out[-1] == "":
                out.append(x)
            elif out and out[-1].startswith("| 경우"):
                out.append(x)
        elif x.startswith("| LoD2 합") or x.startswith("| 항공 LiDAR 합"):
            out.append(x)
    return out


def main():
    R2 = jl(T / "일2_영역나눔.json")
    C3 = jl(T / "일3_맞춰볼값.json")["data"]
    A4 = jl(TAB / "a4_axes.json")["checks"]
    M7 = jl(T / "일7_결측.json")["checks"]
    C9 = jl(T / "일9_맞춰볼값.json")["data"]
    o3 = C3["order"]
    bad3 = [c for c in o3 if not c["same"]]
    dt = [c for c in C3["distance_task"] if c["kind"] == "점검"]
    L = ["# 영역을 다시 나누고 두 축으로 보는 7.1 재료 — 중간 보고 v1 (PHD-MAIN-AXES71-v2)", "",
         f"- 만든 때 {now()} · 브랜치 `exp/main-experiment` · scientific_verdict: null · 학습하지 않았고 GPU를 쓰지 않았다(모든 셈 `jointbuildgs:dev` 컨테이너의 CPU).",
         "- 발주문 `본실험_두축평가_발주문_v2.md` 0.2의 차례 3. 결정을 기다리지 않고 차례 4(일 5, 일 8, 일 9의 마무리)로 이어 간다. 일 5·9의 값과 일 8 그림은 이미 나왔고 최종 보고에서 정리한다.",
         "- 설정 `configs/phd/main_axes71_v2/axes71_v2.json`(첫 셈 전 잠금 2026-10-22 20:05, 결과를 보기 전 고침 2건: 결과 선 색, 축 2 값의 정의 — amendments에 시각과 까닭).",
         "- 지표 이름: 참값 기준 재현율 R(τ), 결과 기준 정밀도 P(τ), 참값 기준 평균 거리, 결과 기준 평균 거리. 결과 기준은 셈 마(참값 그 자리 평면까지 법선 방향, 옆 거리 0.5 m 안). "
         "관련 연구(DTU)의 완전성이 참값 기준 평균 거리에, 정확도가 결과 기준 평균 거리에 해당한다. CDGS* = 시점별 크기 맞추기를 생략한 변형.", "",
         "## 0. 맨 앞 — 보이지 않음, 어긋남, 정의 없음", "",
         "| 무엇 | 결과 |", "|---|---|",
         f"| 일 2 참값 점 수 (v4 의도 한눈에) | 6건 가운데 5건 같음. 다듬기 B0 · LoD2 301,688 대 기록 301,740 — 칸이 다름(거른 영상 오류인 코드 2 패치 11개의 행 52개가 보존 · 거름으로 감) |",
         f"| 일 3 발주 6절의 값 | 12개 가운데 {len(o3) - len(bad3)}개 같음. 어긋남: " + "; ".join(f"{KEY_KO[c['cell']]} {c['case']} 본 방법 R(τ) {c['here']:.2f} 대 {c['want']}" for c in bad3) +
         " — 칸이 다름(R1 · 항공 LiDAR의 거른 영상 오류인 코드 2 패치 46개를 다듬기에서 뺌) |",
         f"| 일 3 새 거리 지표와 같은 칸 | 참값 쪽 {sum(c['same'] for c in dt if c['metric'] != 'P_0.2A')}/{len([c for c in dt if c['metric'] != 'P_0.2A'])}칸 반올림 전 값까지 같음. 결과 쪽 P(0.2 m) 셈 가는 기록의 셈 나와 108/108 같음(칸이 참값 행 없는 패치를 '참값 없음'으로 보내기 때문) |",
         f"| 일 3 v4 의도 한눈에 (반올림 전 중앙값) | {sum(c['same'] for c in C3['v4'])}/{len(C3['v4'])} 같음 |",
         f"| 일 4 새 거리 지표 일 5 | {sum(c['same'] for c in A4)}/{len(A4)} 같음 (B0 · LoD2 결합 1~1.5τ 31.8, 1.5~4τ 5.7 (5.65), B173 주변 · 항공 LiDAR 1~4τ 본 방법 86.4, 결합 48.7) |",
         f"| 일 7 고친 판 시험 표 2 | 24/24 같음 |" if all(all(c[k]["same"] for k in ("wrong_release", "from_violation", "right_release", "mixed")) for c in M7) else "| 일 7 고친 판 시험 표 2 | 어긋남 있음 — tables/일7_결측.md |",
         f"| 일 9 고친 판 시험의 값 | {sum(c['same'] for c in C9)}/{len(C9)} 반올림 전 값까지 같음 |",
         "| 그림이 제목대로 읽히는가 (처음 보는 사람 점검, 그림마다 한 번) | V3 보임, V5 일부만 보임(봉우리 숫자와 제목의 치우침 숫자가 다른 값이라 헷갈림), V6 일부만 보임(유리와 둘레를 테두리로만 구별, 칸이 작음). 결측 지도는 결측 패치가 작아 확대 판에서도 작게 보임 |",
         "| 정의 없음 | 비가시 칸의 가상 시점 메시: B0·R1은 메시가 없고 만들려면 GPU 렌더가 필요해 만들지 않음('가상 시점 메시 없음'; 그 칸의 참값 점은 0~45점). MVS 표면은 가우시안이 없어 가상 시점 메시가 없음. "
         "일 9의 3단계 조건: 조건마다 거른 영상 오류 파일이 없어 보존 · 거름, 보존 · 문턱 안, 다듬기, 상속 · 결측(과 그 합)은 정의 없음, 항공 LiDAR 영역 파일이 없어 그 경우 전체가 정의 없음 |",
         "", "## 1. 이 발주에서 정한 것 (발주 2절의 '새로 정하는 것')", "",
         "- **칸의 차례.** 발주 5.1을 영역 파일에 그대로 대면 겹치거나 비는 패치가 있다(일 1 확인). 앞 작업 정의(빈칸 채우기의 '영상이 틀린 곳' = 거른 영상 오류에서 코드 3 전제 위배를 뺀 것 ∪ 코드 3 문턱 안)를 지키도록 "
         "참값 없음 → 한계 → 보존 · 거름 → 보존 · 문턱 안 → 다듬기 → 보정 → 나머지 차례로 넣었다. 그래서 보존 합은 v4의 '영상이 틀린 곳'과 행까지 같고, 다듬기는 거른 영상 오류인 코드 2 패치만큼 작다. "
         "코드 0(GT missing)인데 참값 행이 있는 패치(B0 · LoD2 3,387개 등)는 참값 없음에 넣었다. 설정의 cells.rule만 바꾸면 차례를 바꿔 다시 셀 수 있다.",
         "- **결과 기준 거리(셈 마).** 참값 점 법선은 출처마다 반지름 0.5 m 공분산(10개 미만은 가장 가까운 10개)으로 냈다. 새 거리 지표의 법선과 각도 차 최대 0.03°. 이웃 10개 미만 점은 0.02~0.03 %.",
         "- **결과 점.** 새 거리 지표의 결과 점을 같은 규칙으로 다시 뽑았다(모든 결과에서 점 수 같음, d_r 차 최대 1e-6 m).",
         "- **축 2 값.** 코드 3을 정한 값 = where(v1_kept, mvs_minus_prior − gt_med, mvs_minus_gt_at_gt)(지붕꼴 연직, LoD2 벽꼴 면 법선; 빈칸 채우기 v_geo와 코드 2·3에서 같음). 보존 · 거름은 거르기 전 |v_photo| ÷ τ로 나눈 셋째 선.",
         "- **MVS 표면** [새로 만듦]. 판 가 = 학습이 마스크를 켜고 읽는 깊이(COLMAP 기하 단계). 관측 신뢰도 마스크는 그 깊이의 유효 화소와 똑같아, '마스크만 뺀 같은 깊이'는 판 가와 같다. "
         "그래서 판 나 = 마스크를 끈 학습이 읽는 깊이(광도 단계, 기하 거름 전)로 했다. 1단계 후처리 TSDF(0.05 / 0.25 / 300 m, 다듬기 없음)를 CPU로 옮겨 결합 깊이로 GPU 결과와 맞춰 봄(1 mm 넘게 다른 꼭짓점 6개). "
         "판 가 꼭짓점 B0 16.4 M, B173 주변 19.0 M, R1 24.6 M. 결합은 MVS 표면을 따로 만들지 않았다(셋째 없음).",
         "- **덩어리 잇기.** 이웃 패치 중심 간격의 중앙값 0.25 m(0.18~0.36 안) → 0.36 m로 이음.",
         "", "## 2. 영역 나눔 (일 2) — 사전 정보마다 세 지역 합", "",
         "- 칸 = 넓이 비율 (%) · 영역 행 비율 (%). 경우마다와 장면 점 비율은 숫자표 1절과 tables/일2_영역나눔.md. 넓이 합 100.00 %, 두 칸에 든 패치 0.", "",
         "| 칸 | LoD2 합 | 항공 LiDAR 합 |", "|---|---:|---:|"]
    for k in CELLS + ["s_corr", "s_keep", "s_inh"]:
        a = R2["data"]["합/LoD2"]; b = R2["data"]["합/ALS"]
        f = lambda d: f"{100 * d['cells'][k]['area'] / d['area_total']:.1f} · {100 * d['cells'][k]['rows'] / d['rows_total_in_range']:.1f}"
        L.append(f"| {KEY_KO[k]} | {f(a)} | {f(b)} |")
    L += ["", "## 3. 장면 전체 한눈에 (일 3)", ""] + block("일3_장면전체.md", "**LoD2 합**") + [""]
    L += ["## 4. 두 축 곡선 (일 4) — 그림 A", "", "![그림 A](figures/일4_그림A_두축.png)", "",
          "- 캡션 재료: 무엇 = 칸 패치를 사전 정보 어긋남(축 1)과 영상 깊이 어긋남(축 2)의 τ 배로 나눈 구간마다 참값 기준 재현율 R(τ). 어디서 = 사전 정보마다 세 지역의 참값 행. "
          "색 = 결과(입력 둘은 회색 점선), 축 2의 옅은 선 = 판정이 놓은 한계 칸, 점선 = 보존 · 거름(거르기 전 어긋남), 빈 표지 = 참값 점 1만 미만. 그림 B(경우마다), C(평균 거리), D(축 1 m 단위)는 figures/.", ""]
    L += block("일4_두축.md", "## LoD2 합", "## B0 · 항공 LiDAR") + block("일4_두축.md", "## 항공 LiDAR 합", "## 맞춰 볼 값") + [""]
    L += ["## 5. 보존 · 거름, 보존 · 문턱 안, 한계의 네 값 (일 3) — 사전 정보마다 세 지역 합", "", "- 경우마다는 tables/일3_보존_거름.md, 일3_보존_문턱안.md, 일3_한계.md.", ""]
    for nm, ko in (("일3_보존_거름.md", "보존 · 거름"), ("일3_보존_문턱안.md", "보존 · 문턱 안"), ("일3_한계.md", "한계")):
        L += [f"### {ko}"] + sums_only(nm, ko) + [""]
    L += ["## 6. 결과 기준의 점검 셈 (1.1, 일 8의 일부)", "", "- 전체 · 경우마다 셈 가·다·마·바는 tables/중간_결과기준점검.md, 칸마다는 tables/일3_부록_셈.md. 아래는 동기가 된 B0 · 항공 LiDAR.", ""]
    L += block("중간_결과기준점검.md", "| 경우 |", "| B0 · 항공", keep=None)[:2] + [x for x in (T / "중간_결과기준점검.md").read_text().split("\n") if x.startswith("| B0 · 항공 LiDAR")] + [""]
    L += block("중간_결과기준점검.md", "## 참값 밀도") + [""]
    L += ["## 7. 영역 지도와 덩어리 (일 6)", "", "- 지도: figures/일6_영역지도_<지역>_<사전 정보>.png (위에서 + 비스듬히 둘). 예:", "", "![B173 주변 · 항공 LiDAR](figures/일6_영역지도_B173nb_b10_ALS.png)", "",
          "- 덩어리 표(사전 정보마다 합). 칸 = 덩어리 수 · 넓이 50 % · 90 % · 최대 · 가장 큰 덩어리 % · 1 · 2.5 · 10 m² 미만 덩어리 넓이 % · 경계 패치 넓이 % · 2.5 m² 이상 덩어리 수.", ""]
    L += [x for x in block("일6_덩어리.md", "## 칸마다 덩어리 통계", "## 덩어리 단위") if not x.startswith("| B") and not x.startswith("| R")] + [""]
    L += block("일6_덩어리.md", "## 덩어리 단위 달성률", "## 덩어리 크기별") + [""]
    L += ["## 8. 결측 지도와 결측 표 (일 7)", "", "![R1 · LoD2 결측](figures/일7_결측지도_R1rep_b10_LoD2.png)", ""]
    L += block("일7_결측.md", "## LoD2 합", "## B0 · 항공 LiDAR") + block("일7_결측.md", "## 항공 LiDAR 합", "## 맞춰 볼 값") + [""]
    L += ["## 9. 경계 거리 (일 7)", "", "- 칸 = R(τ) (%) · 참값 기준 평균 거리 (cm). 그림: figures/일7_경계거리_<사전 정보>.png.", ""] + block("일7_경계거리.md", "## LoD2 합") + [""]
    L += ["## 10. 일 1 — 사전 정보 깊이 항과 MVS 깊이 항의 꼴", "", "![두 항의 꼴](figures/일1_두항의꼴.png)", "",
          "- 사전 정보 깊이 항(d = 결과 깊이 − 사전 정보 깊이, τ_p = τ ÷ f로 높이 τ에 해당): 0~τ 손실 0·기울기 0, τ~4τ 손실 λg(|d| − τ)/n_px·기울기 λg/n_px, 4τ 넘음 손실 상수 λg·3τ/n_px·기울기 0. "
          "g = 0은 패치 판정 충돌, 섞임은 g = 1. 판 A는 τ 대신 w에서 시작, 판 B는 결측 화소를 절단하지 않음.",
          "- MVS 깊이 항: 모든 구간 λA|D − M|/n_px, 기울기 λA; 허용 구간·절단·높이 환산 없음. λ_mvs = λ_prior = 0.05, 둘 다 n_px로 나눔(비 1 : 1). 판정 표시는 항공 LiDAR에서 2τ이지만 손실 구간은 τ.",
          "- 코드 줄과 다른 다섯 경우의 τ로 그린 값: tables/일1_정의확인.md 2절, figures/일1_두항의꼴.json.", "",
          "## 11. 걸린 시간 (지금까지)", "",
          "| 단계 | 시간 |", "|---|---|",
          "| 일 1 정의 확인·두 항의 꼴(하위 에이전트) | 20:05~20:31 |",
          "| 참값 법선(세 지역) | 3분 |",
          "| MVS 표면 여섯(판 나는 조각 TSDF) | 20:13~22:49 (판 가 2~4분, 판 나 24~42분) |",
          "| 결과 점 다시 뽑기와 셈 마(세 지역, 메시 81개) | 20:10~23:08(20:36에 고쳐 다시 시작). CDGS 메시 하나 17~45분(결과 점 70 %가 참값에서 1 m 넘게 떠 가장 가까운 참값 점 찾기가 느림) |",
          "| 일 9 거리(학습 67개, 셋으로 나눔) | 20:31~23:05 |",
          "| 일 3~8 셈과 그림 | 22:51~23:21 (일 3 14분) |", "",
          "## 12. 다음 (차례 4)", "",
          "- 일 5 누적 분포, 일 8 점검과 V3·V5·V6, 일 9 표는 값이 나왔다. 최종 보고에서 그림을 점검하고 V5·V6 그림을 고친 뒤 다시 점검한다.",
          "- 숫자표 `두축평가_숫자표_v1*.md`, `앞단계_새지표_숫자표_v1*.md`, 전달 묶음 두 개를 만든다."]
    (DOCS / "중간보고_v1.md").write_text("\n".join(L) + "\n")
    print("interim", len("\n".join(L)))


if __name__ == "__main__":
    main()
