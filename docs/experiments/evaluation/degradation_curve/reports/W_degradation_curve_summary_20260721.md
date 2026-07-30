# 열화 곡선 측정 요약 (2026-07-21)

> 측정·산출 기록. 판정·해석 없음. 학습 0, 신규 추론 0, 이미지 입력 0.

## 실행 범위

- 완료 상태: `full`
- 모집단: 178동
- 완료 단계: 12/12
- 측정 행: 2136/2136
- 미완 단계: 없음
- Roofer: `3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`
- 설정: `--id-attribute building_id --box 690791.740 5335864.050 691154.650 5336353.850; all reconstruction parameters default`
- 좌표계: `EPSG:25832`

## 단계별 전체 모집단 집계

| 단계 | σ m | 유지율 | LoD2/178 | LoD1 폴백 | val3dity | 지붕면수비 중앙 | RMS 중앙 m | Hausdorff 중앙 m | 완전율 중앙 | 점밀도 중앙 pt/m² |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0.000 | 1.000 | 178/178 | 0 | 163/178 | 1.417 | 0.421 | 2.374 | 0.9999 | 18.234 |
| noise_sigma_0p05 | 0.050 | 1.000 | 178/178 | 0 | 167/178 | 1.333 | 0.501 | 2.585 | 0.9999 | 18.042 |
| noise_sigma_0p10 | 0.100 | 1.000 | 178/178 | 0 | 164/178 | 1.071 | 0.436 | 2.501 | 0.9999 | 18.011 |
| noise_sigma_0p20 | 0.200 | 1.000 | 177/178 | 0 | 155/178 | 1.000 | 0.399 | 2.350 | 0.9999 | 17.536 |
| noise_sigma_0p40 | 0.400 | 1.000 | 173/178 | 3 | 156/178 | 2.000 | 0.659 | 2.710 | 0.9999 | 17.063 |
| noise_sigma_0p80 | 0.800 | 1.000 | 172/178 | 3 | 157/178 | 1.667 | 1.090 | 3.475 | 0.9998 | 16.134 |
| density_retain_1of2 | 0.000 | 0.500 | 178/178 | 0 | 169/178 | 1.000 | 0.387 | 2.406 | 0.9999 | 9.030 |
| density_retain_1of4 | 0.000 | 0.250 | 177/178 | 0 | 168/178 | 1.000 | 0.298 | 1.608 | 0.9999 | 4.452 |
| density_retain_1of10 | 0.000 | 0.100 | 172/178 | 0 | 170/178 | 1.000 | 0.542 | 1.847 | 0.9999 | 1.798 |
| density_retain_1of20 | 0.000 | 0.050 | 160/178 | 0 | 176/178 | 0.500 | 1.614 | 3.837 | 0.9999 | 0.911 |
| combo_sigma_0p20_retain_1of4 | 0.200 | 0.250 | 176/178 | 0 | 164/178 | 1.000 | 0.307 | 1.635 | 0.9999 | 4.330 |
| combo_sigma_0p40_retain_1of10 | 0.400 | 0.100 | 148/178 | 0 | 176/178 | 0.333 | 1.928 | 5.163 | 0.9999 | 1.687 |

## 0단 재현 행

| 범위 | 항목 | 기대 | 측정 | 일치 |
|---|---|---:|---:|---|
| 178동 | LoD2 | 178/178 | 178/178 | true |
| 178동 | RMS 중앙 m | 0.421 | 0.421303923 | true |
| 파일럿10 | LoD2 | 10/10 | 10/10 | true |
| 파일럿10 | val3dity | 9/10 | 9/10 | true |
| 파일럿10 | 면수비 중앙 | 1.875 | 1.875000000 | true |
| 파일럿10 | RMS 중앙 m | 0.337 | 0.337373145 | true |
| 파일럿10 | 완전율 중앙 | 0.9999 | 0.999923703 | true |
| 178동×전 지표 | 불일치 셀 | 0 | 0 | true |

0단은 수락된 정본 CityJSON과 확정 채점행을 재사용했다. 같은 잠금 명령의 별도 진단 재실행 수치는 `phases/p2-gsjso/runs/boundary_and_robustness/20260721_degradation_curve/zero_rerun_diagnostic.json`에 기록했다.

## dense 대조 마커

| 지표 | n | p25 | 중앙 | p75 |
|---|---:|---:|---:|---:|
| local_plane_rms_m | 132 | 0.1163 | 0.1519 | 0.1855 |
| pt_density_m2 | 139 | 16.5169 | 126.2081 | 423.8950 |

## 단조성 감지 행

| 축 | 지표 | 기대 방향 | 기대방향 단조 | 역전 단계 |
|---|---|---|---|---|
| noise | assembly_rate | nonincreasing | true | 없음 |
| noise | val3dity_valid_rate | nonincreasing | false | baseline->noise_sigma_0p05; noise_sigma_0p20->noise_sigma_0p40; noise_sigma_0p40->noise_sigma_0p80 |
| noise | lod1_fallback_rate | nondecreasing | true | 없음 |
| noise | roof_rms_median_m | nondecreasing | false | noise_sigma_0p05->noise_sigma_0p10; noise_sigma_0p10->noise_sigma_0p20 |
| noise | roof_hausdorff_median_m | nondecreasing | false | noise_sigma_0p05->noise_sigma_0p10; noise_sigma_0p10->noise_sigma_0p20 |
| noise | roof_completeness_median | nonincreasing | false | baseline->noise_sigma_0p05; noise_sigma_0p20->noise_sigma_0p40 |
| noise | face_count_ratio_median | not_preregistered | n/a | 없음 |
| density | assembly_rate | nonincreasing | true | 없음 |
| density | val3dity_valid_rate | nonincreasing | false | baseline->density_retain_1of2; density_retain_1of4->density_retain_1of10; density_retain_1of10->density_retain_1of20 |
| density | lod1_fallback_rate | nondecreasing | true | 없음 |
| density | roof_rms_median_m | nondecreasing | false | baseline->density_retain_1of2; density_retain_1of2->density_retain_1of4 |
| density | roof_hausdorff_median_m | nondecreasing | false | density_retain_1of2->density_retain_1of4 |
| density | roof_completeness_median | nonincreasing | false | baseline->density_retain_1of2; density_retain_1of4->density_retain_1of10; density_retain_1of10->density_retain_1of20 |
| density | face_count_ratio_median | not_preregistered | n/a | 없음 |

## 산출 SHA256

| 파일 | SHA256 |
|---|---|
| `docs/degradation_curve_measurements.csv` | `1767c3134771c3b574f2043adb1eb2f573b02c64b82503315b9b8739e7bb79cc` |
| `docs/degradation_curve_summary.csv` | `e12868ad1dd9047ee6ac938b5ca91c5ae06776dc93d433ce2f9dc52b2c59c7de` |
| `docs/figs/degradation_curve/degradation_curve_density.png` | `3c0932d8945d3e0a7c0d4d8048cdaca663c369565ece844b26d48aaa5f0395b5` |
| `docs/figs/degradation_curve/degradation_curve_noise.png` | `031b2ef2799794281d50ed114aa4b4c6223169f522ea0a5097a5e1b885264e2a` |

## 실행 플래그

- `learning_runs_started=0`
- `new_inference_runs=0`
- `image_inputs_used=0`
