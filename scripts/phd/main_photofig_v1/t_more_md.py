"""PHD-MAIN-PHOTOFIG-v1 [사용자가 더 요청함] tables of figure 7 extra and figure 8 that f3_r1.py does not write: the past-shape inflow rows by
face (B173 주변 LoD2, two-seed mean -> 결측 지키기; p3_after_more.py), the four classes on wall 72, and the bands of figure 8.
Host python (json only).   python3 -I t_more_md.py   -> docs/.../tables/fig7_extra_faces.md|json, fig8_bands.md   scientific_verdict: null"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PF = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"
T = REPO / "docs/experiments/phd/main_photofig_v1/tables"


def main():
    A = json.loads((PF / "prep/places_after_more.json").read_text())["fig7_extra"]
    kind = {1: "지붕", 2: "벽"}
    L = ["# B173 주변 LoD2: 과거 형상 유입 행이 면마다 얼마나 늘었나 — 숫자 [이 발주에서 냄, 결과를 본 뒤]", "",
         f"- 행 = 사전 정보가 틀린 결측의 지표 행(솎은 행, 참값과 사전 정보의 거리 0.2 m 이상) {A['total_rows']}행. 유입 = 결과 면이 사전 정보 쪽이거나 둘 다에 걸린 행.",
         f"- 늘어난 행 = 결측 지키기의 유입 행 − 지금 방법 두 씨앗 유입 행의 평균. 모두 {A['total_rise_rows']:+.1f}행.", "",
         "| 면 | 꼴 | 행 | 지금 방법 씨앗 0 | 지금 방법 씨앗 1 | 결측 지키기 | 늘어난 행 |", "|---:|---|---:|---:|---:|---:|---:|"]
    for r in A["face_rise_table"]:
        if r["inflow_rows_method_s0"] or r["inflow_rows_method_s1"] or r["inflow_rows_fix"]:
            L.append(f"| {r['ext']} | {kind.get(r['kind'], r['kind'])} | {r['rows']} | {r['inflow_rows_method_s0']} | {r['inflow_rows_method_s1']} | {r['inflow_rows_fix']} | {r['rise_rows']:+.1f} |")
    rest = [r for r in A["face_rise_table"] if not (r["inflow_rows_method_s0"] or r["inflow_rows_method_s1"] or r["inflow_rows_fix"])]
    L.append(f"\n- 어느 결과에서도 유입 행이 없는 면 {len(rest)}개({sum(r['rows'] for r in rest)}행)는 표에서 뺐다.")
    F = A["chosen_face_rows"]
    L += ["", f"## 벽 {A['ext']} (덧붙인 자리)의 네 분류", "",
          f"- 참값과 사전 정보 벽의 거리 중앙값 {F['abs_sW_median_m']*100:.1f} cm (10~90 %: {F['abs_sW_p10_p90_m'][0]*100:.1f}~{F['abs_sW_p10_p90_m'][1]*100:.1f} cm). "
          f"분류 창의 반폭 = 그 거리의 절반(최대 0.5 m), 중앙값 {F['window_half_width_median_m']*100:.1f} cm. 행 {F['rows']}.", "",
          "| 결과 | 참값 쪽 | 사전 정보 쪽 | 둘 다 | 둘 다 아님 | 유입(사전 정보 쪽 + 둘 다) |", "|---|---:|---:|---:|---:|---:|"]
    for k, c in F["classes"].items():
        L.append(f"| {k} | {c['참값 쪽']} | {c['사전 정보 쪽']} | {c['둘 다']} | {c['둘 다 아님']} | {c['사전 정보 쪽'] + c['둘 다']} ({(c['사전 정보 쪽'] + c['둘 다']) / F['rows'] * 100:.1f} %) |")
    (T / "fig7_extra_faces.md").write_text("\n".join(L) + "\n")
    (T / "fig7_extra_faces.json").write_text(json.dumps(dict(face_rise_table=A["face_rise_table"], chosen_face=A["ext"], chosen_face_rows=F, total_rows=A["total_rows"],
                                                              total_rise_rows=A["total_rise_rows"], place_rule=A["place_rule"], added=A["added"], scientific_verdict=None), indent=1, ensure_ascii=False))
    M = json.loads((REPO / "configs/phd/main_photofig_v1/photofig_v1_more.json").read_text())["band_values_m"]["fig8"]
    B = json.loads((T / "fig8_r1.json").read_text())["section"]["bands"]
    L = ["# 그림 8: R1 LoD2 벽 19의 허용 구간과 좁힌 폭 — 숫자 [옮긴 값: 고친 판 시험 tables/w_decision_T.json, w_decision_L.json]", "",
         "| 셈 | 벽의 허용 오차 | 벽의 좁힌 폭 | 줄어든 폭 | 지붕의 허용 오차 | 지붕의 좁힌 폭 |", "|---|---:|---:|---:|---:|---:|",
         f"| 기록 셈 | {M['tau_wall']*100:.1f} cm | {M['w_wall_T']*100:.1f} cm | {(M['tau_wall']-M['w_wall_T'])*100:.1f} cm | {M['tau_roof']*100:.1f} cm | {M['w_roof_T']*100:.1f} cm |",
         f"| 주 셈 | {M['tau_wall']*100:.1f} cm | {M['w_wall_L']*100:.1f} cm | {(M['tau_wall']-M['w_wall_L'])*100:.1f} cm | {M['tau_roof']*100:.1f} cm | {M['w_roof_L']*100:.1f} cm |", "",
         f"- 그림의 띠 가운데 = 이 면 패치 중심의 '벽에서 바깥으로' 값의 중앙값 {B['centre_m']*100:+.1f} cm."]
    (T / "fig8_bands.md").write_text("\n".join(L) + "\n")
    print("ok")


if __name__ == "__main__":
    main()
