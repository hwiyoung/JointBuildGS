"""PHD-MAIN-PHOTOFIG-v1 [사용자가 더 요청함]: write configs/phd/main_photofig_v1/photofig_v1_more.json = the ways of looking of figures 7 and 8
(results, panels, colours, bands, titles) + the places chosen by p2_more.py from geometry only; then the lock (time, sha256) in
PF/config_lock_more.json. Host python (json only). Run once before figure 7 is drawn; the locked photofig_v1.json is not touched.
  python3 -I c2_config_more.py      scientific_verdict: null"""
import hashlib
import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PF = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"
OUT = REPO / "configs/phd/main_photofig_v1/photofig_v1_more.json"
W = REPO / "docs/experiments/phd/main_fixtest_v1/tables"

LOOK = {
    "task_id": "PHD-MAIN-PHOTOFIG-v1",
    "asked": "사용자 10-20: 'B173 주변 LoD2 결측 지키기의 유입률 상승과 R1 LoD2 폭 좁히기(기록 셈)의 결측 재현율 상승을 같은 꼴의 사진 그림으로 더 그려 줘'",
    "scientific_verdict": None,
    "note": "그림 3과 같은 꼴(사진 두 칸 + 단면 + 숫자 줄, f3_r1.py). 두 경우는 고친 판 시험 최종 보고의 단위 값을 본 뒤 요청되었다. 자리와 사진은 p2_more.py가 영역 파일, 패치 저장소, 카메라 기하만으로 골랐다(PF/prep/places_more.json). 이 파일을 저장하기 전에 두 경우의 결과 파일(메시, 거리, 행 분류)은 열지 않았다.",
    "results": {
        "fig7": {"지금 방법 씨앗 0": "S0/stage0/b1_LoD2 (거리·행: prop_LoD2_s0)", "지금 방법 씨앗 1": "S0/stage0/b2_LoD2 (거리·행: prop_LoD2_s1)",
                 "결측 지키기": "FT/runs/B173nb_b10/fixB_LoD2_s0", "판정만 끈 방법": "S3/runs/B173nb_b10/nojudge_LoD2_s0"},
        "fig8": {"지금 방법 씨앗 0": "S1/stage1/R1rep_b10/prop_LoD2_s0", "지금 방법 씨앗 1": "S1/stage1/R1rep_b10/prop_LoD2_s1",
                 "폭 좁히기(주 셈)": "FT/runs/R1rep_b10/fixA_LoD2_s0", "폭 좁히기(기록 셈)": "FT/runs/R1rep_b10/fixAT_LoD2_s0"}},
    "panels": {"fig7": ["지금 방법 씨앗 0", "결측 지키기"], "fig8": ["지금 방법 씨앗 0", "폭 좁히기(기록 셈)"]},
    "colours": {"폭 좁히기(기록 셈)": "#2ca02c", "폭 좁히기(주 셈)": "#98df8a 점선", "허용 구간": "사전 정보 둘레 옅은 회색 띠 #d9d9d9",
                "좁힌 폭(기록 셈)": "옅은 초록 띠 #c7e9c0", "좁힌 폭(주 셈)": "옅은 초록 점선 #98df8a", "나머지": "photofig_v1.json colours와 같음"},
    "bands": {"fig8": "벽 단면에 사전 정보 벽 둘레로 허용 구간(± 허용 오차), 좁힌 폭(기록 셈)의 띠, 좁힌 폭(주 셈)의 점선. 값 = 고친 판 시험 tables/w_decision_T.json, w_decision_L.json의 R1rep_b10/LoD2 벽 값(tau_wall, w_wall). 띠의 가운데 = 이 단면에서 사전 정보 벽 선의 가운데 값",
              "fig7": "띠 없음(그림 3과 같음)"},
    "titles": {"fig7": "결측 지키기가 B173 주변 벽의 결측 패치를 채웠는가, 옛 모양은 어디에 남았나 — 사전 정보가 틀린 결측이 가장 많은 면",
               "fig8": "폭 좁히기(기록 셈)가 R1 벽의 결측 패치를 채웠는가 — 사전 정보가 맞는 결측이 가장 많은 면"},
    "files": {"fig7": "photo_fig7_b173nb.png|pdf|json, tables/fig7_b173nb.md|json", "fig8": "photo_fig8_r1.png|pdf|json, tables/fig8_r1.md|json"},
    "check": "단위 전체 값이 고친 판 시험 최종 보고와 같은지 본다: B173 주변 LoD2 유입률 지금 방법 두 씨앗 평균 20.75 %, 결측 지키기 27.49 %; R1 LoD2 결측 재현율(0.2 m) 지금 방법 평균 50.77 %, 주 셈 55.06 %, 기록 셈 63.62 %",
    "patch_rule": "photofig_v1.json colour_ranges.fig3_patch와 같음(f3_r1.py 머리글)",
}


def main():
    places = json.loads((PF / "prep/places_more.json").read_text())
    wT = json.loads((W / "w_decision_T.json").read_text())["cases"]["R1rep_b10/LoD2"]
    wL = json.loads((W / "w_decision_L.json").read_text())["cases"]["R1rep_b10/LoD2"]
    band_vals = {"fig8": dict(tau_wall=wT["tau_wall"], w_wall_T=wT["w_wall"], w_wall_L=wL["w_wall"], tau_roof=wT["tau_roof"], w_roof_T=wT["w_roof"], w_roof_L=wL["w_roof"])}
    cfg = dict(LOOK, band_values_m=band_vals, places={k: v for k, v in places.items() if k in ("fig7", "fig8")}, place_rule=places["place_rule"], places_added=places["added"])
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    b = OUT.read_bytes()
    lock = dict(config=str(OUT.relative_to(REPO)), sha256=hashlib.sha256(b).hexdigest(), saved_at=time.strftime("%Y-%m-%d %H:%M:%S KST"),
                places_sha256=hashlib.sha256((PF / "prep/places_more.json").read_bytes()).hexdigest(),
                note="그림 7 전 잠금. 두 경우의 결과 파일을 열기 전에 저장", scientific_verdict=None)
    (PF / "config_lock_more.json").write_text(json.dumps(lock, indent=1, ensure_ascii=False))
    print(lock)


if __name__ == "__main__":
    main()
