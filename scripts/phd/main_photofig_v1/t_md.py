"""PHD-MAIN-PHOTOFIG-v1: md tables of figures 1 and 4 from their json (host python, json only).  python3 -I t_md.py   scientific_verdict: null"""
import json
from pathlib import Path

T = Path(__file__).resolve().parents[3] / "docs/experiments/phd/main_photofig_v1/tables"


def cm(x, s=True):
    return "—" if x is None else (f"{x*100:+.1f}" if s else f"{x*100:.1f}")


def fig1():
    d = json.loads((T / "fig1_glass.json").read_text())
    g, ia, pv, ps, mt = d["gt_on_glass"], d["image_depth_on_glass_all_views"], d["photo_vertical"], d["photo_side"], d["mirror_test"]
    av = pv["agreeing_views_approx"]
    L = ["# 그림 1 숫자: 유리 채광창 (B173 주변 · 항공 LiDAR) [이 발주에서 냄]", "",
         "| 값 | 수 | 표본 |", "|---|---|---|",
         f"| 유리(사례 영역) 넓이 | {d['case_area_m2']:.2f} m² | 패치 {d['case_patches']} |",
         f"| 맞는 자료를 판단할 수 없는 패치 | 유리 {d['premise_violation_patches']['case']}, 둘레 2 m {d['premise_violation_patches']['band']} | 둘레 패치 {d['band_patches']} |",
         f"| 결측 패치 | 유리 {d['missing_patches']['case']}, 둘레 2 m {d['missing_patches']['band']} (사전 정보가 맞는 {d['missing_patches']['band_code4']}, 틀린 {d['missing_patches']['band_code13']}) | |",
         f"| 관측 신뢰도 검사를 통과한 몫(학습 영상 모두) | {ia['pass_share']*100:.1f} % | 유리 화소 {ia['pixels']:,} (패치 저장소 합 {d['pass_share_store']['pixels']:,}, 같음) |",
         f"| 같은 몫(연직 영상 · 비스듬히 본 영상) | {pv['pass_share']*100:.1f} % · {ps['pass_share']*100:.1f} % | {pv['glass_pixels']:,} · {ps['glass_pixels']:,} 화소 |",
         f"| 검사가 요구하는 동의 시점 수 | 2 (COLMAP filter_min_num_consistent) | PREP/mvs/box_B0_b10/patch_match.log |",
         f"| 동의 시점 수 [근사, 다시 구함] | 중앙값 {av['median']:.0f}, 2 이상 {av['share_ge_2']*100:.1f} %, 분포 {av['distribution']} | 연직 영상의 통과 화소 {pv['passed']:,} |",
         f"| 영상 깊이 − 참값(학습 영상 모두) | 중앙값 {cm(ia['minus_gt_median_m'])} cm, NMAD {cm(ia['minus_gt_nmad_m'], False)} cm; 20 cm 넘게 아래 {ia['share_below_gt_0_2m']*100:.1f} %, 20 cm 넘게 위 {ia['share_above_gt_0_2m']*100:.1f} % | {ia['n_with_gt']:,} 화소 |",
         f"| 영상 깊이 − 참값(연직 · 비스듬히) | {cm(pv['minus_gt_median_m'])} · {cm(ps['minus_gt_median_m'])} cm | {pv['passed']:,} · {ps['passed']:,} |",
         f"| 떨어진 화소의 사진 깊이 − 참값(연직 · 비스듬히) | {cm(pv['failed_minus_gt_median_m'])} · {cm(ps['failed_minus_gt_median_m'])} cm | {pv['failed_with_photometric_depth']} · {ps['failed_with_photometric_depth']} |",
         f"| 유리 위 참값 | {g['per_m2']:.0f} 점/m², 여러 반사 {g['multi_return_share']*100:.2f} %, 층 {g['layers_vs_lod2']['n_layers_ge_5pct']} (0.5 m 넘는 틈 기준) | {g['points']:,} 점 |",
         f"| 참값 − LoD2 지붕면(유리) | 중앙값 {cm(g['minus_lod2']['median_m'])} cm (5~95 분위 {cm(g['minus_lod2']['p05'])} ~ {cm(g['minus_lod2']['p95'])}) | 같은 점 |",
         f"| 참값 − 항공 LiDAR 면 | 중앙값 {cm(g['minus_als']['median_m'])} cm | 같은 점 |",
         f"| 항공 LiDAR − 참값(영역 파일 gt_med) | 중앙값 {cm(d['als_minus_gt_median_m'])} cm | 패치 {d['als_minus_gt_patches']} |",
         f"| 수동 비행 점(유리 위) | {d['manual_on_glass']['points']} 점 | 이 자리에 없음 |",
         f"| 수동 비행 − 연직 비행 높이 차 | 확인 불가(수동 비행 점 없음) | 0.5 m 칸 {d['manual_minus_nadir_on_glass']['cells_0_5m']} |",
         f"| 거울 셈(20 cm 넘게 아래인 점을 유리면에 비춤) | 비춘 점 → 참값 중앙값 {mt['mirrored_to_gt_median_m']*100:.0f} cm (0.3 m 안 {mt['mirrored_within_0_3m_share']*100:.0f} %), 비추기 전 {mt['itself_to_gt_median_m']*100:.0f} cm | {mt['mirrored']:,} 점 |"]
    (T / "fig1_glass.md").write_text("\n".join(L) + "\n")


def fig4():
    d = json.loads((T / "fig4_roof.json").read_text())
    L = ["# 그림 4 숫자: B173 주변 · 항공 LiDAR 면 1의 완만한 지붕 [이 발주에서 냄]", "",
         f"- 지붕 = 고친 판 시험 그림 1의 참값 행 {d['rows']:,}(패치 {d['patches']:,}). 값 = 참값에서 각 면까지의 부호 있는 거리(바깥 +), 영상 깊이는 그 참값 점의 영상 깊이 높이 − 참값 높이.", "",
         "| 대상 − 참값 | 중앙값 (cm) | NMAD (cm) | 행 |", "|---|---:|---:|---:|"]
    for k, v in d["minus_gt"].items():
        L.append(f"| {k} | {cm(v['median_m'])} | {cm(v['nmad_m'], False)} | {v['n']:,} |")
    L += ["", f"30,000회 덤프, 연직 영상 {d['dump_vs_prior_on_photo']['view']}의 지붕 화소: |결과 − 사전 정보|(높이)", "",
          "| 결과 | 화소 | 좁힌 폭(5.61 cm) 안 | 좁힌 폭 ~ 허용 오차(14.70 cm) | 허용 오차 밖 | 결과 − 사전 정보 중앙값 (cm) |", "|---|---:|---:|---:|---:|---:|"]
    for k, v in d["dump_vs_prior_on_photo"]["runs"].items():
        L.append(f"| {k} | {v['pixels']:,} | {v['within_narrowed']*100:.1f} % | {v['between']*100:.1f} % | {v['beyond_tolerance']*100:.1f} % | {cm(v['median_minus_prior_m'])} |")
    sm = d["site_map"]
    L += ["", "B173 주변 평가 범위의 영상 깊이 − 참값", "", "| 곳 | 칸 수 | 중앙값 (cm) | NMAD (cm) |", "|---|---:|---:|---:|",
          f"| 두 자료가 모두 맞는 지붕 패치 모두 | {sm['roof_patches']:,} 패치 | {cm(sm['roof_median_m'])} | {cm(sm['roof_nmad_m'], False)} |",
          f"| 맨땅 칸(0.5 m, 연구의 맨땅 정의) | {sm['ground_cells']:,} 칸 ({sm['ground_points']:,} 점) | {cm(sm['ground_median_m'])} | {cm(sm['ground_nmad_m'], False)} |"]
    for e, v in sorted(sm["faces"].items(), key=lambda kv: -kv[1]["patches"]):
        L.append(f"| 지붕 면 {e} | {v['patches']:,} 패치 | {cm(v['median_m'])} | {cm(v['nmad_m'], False)} |")
    c = d["copied"]
    L += ["", f"- 옮긴 값: 두 자료가 모두 맞는 곳의 치우침 지금 방법 +6.2 cm, 학습 전 사전 정보 −1.4 cm({c['bias_cm']['source']}); 2단계 고운 자 지금 방법 6.88 cm, 허용 구간 없애기 2.55 cm({c['stage2_fine_ruler_cm']['source']}); 탐색 지역 R2의 잔차(사전 정보 − 영상 깊이) 중앙값 −6.2 cm({c['r2_residual_median_cm']['source']})."]
    (T / "fig4_roof.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    fig1(); fig4(); print("ok")
