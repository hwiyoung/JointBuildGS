# 기록 값 대조 (요청 6절, PHD-MAIN-NUMBERS-v1)

- 만든 때 2026-10-19 02:53:20 KST, 스크립트 `scripts/phd/main_numbers_v1/check6.py`. 반올림은 저장된 값의 사사오입(99.25 → 99.3)이다. 어긋나면 둘 다 적고 고르지 않는다.

| 절 | 항목 | 기록 | 묶음 (반올림 전) | 판단 | 출처 | 비고 |
|---|---|---|---|---|---|---|
| 7.1 | 과거 형상 유입률 · 본 방법 · B0 · LoD2 | 12.0 | 11.9800 (씨앗 12.10, 11.86; 32,880점) | 같음 | S1/metrics/B0_b10/prop_LoD2_s0__LoD2.json: spread.prior_error.main.spread; S1/metrics/B0_b10/prop_LoD2_s1__LoD2.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · 본 방법 · B0 · 항공 LiDAR | 42.8 | 42.7500 (씨앗 47.71, 37.79; 262점) | 같음 | S1/metrics/B0_b10/prop_ALS_s0__ALS.json: spread.prior_error.main.spread; S1/metrics/B0_b10/prop_ALS_s1__ALS.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · 본 방법 · B173 주변 · LoD2 | 6.8 | 6.8100 (씨앗 6.54, 7.08; 119,763점) | 같음 | S1/metrics/B173nb_b10/prop_LoD2_s0__LoD2.json: spread.prior_error.main.spread; S1/metrics/B173nb_b10/prop_LoD2_s1__LoD2.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · 본 방법 · B173 주변 · 항공 LiDAR | 0.0 | 0.0250 (씨앗 0.02, 0.03; 96,117점) | 같음 | S1/metrics/B173nb_b10/prop_ALS_s0__ALS.json: spread.prior_error.main.spread; S1/metrics/B173nb_b10/prop_ALS_s1__ALS.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · 본 방법 · R1 · LoD2 | 7.6 | 7.6350 (씨앗 8.51, 6.76; 54,345점) | 같음 | S1/metrics/R1rep_b10/prop_LoD2_s0__LoD2.json: spread.prior_error.main.spread; S1/metrics/R1rep_b10/prop_LoD2_s1__LoD2.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · 본 방법 · R1 · 항공 LiDAR | 24.9 | 24.8650 (씨앗 27.03, 22.70; 555점) | 같음 | S1/metrics/R1rep_b10/prop_ALS_s0__ALS.json: spread.prior_error.main.spread; S1/metrics/R1rep_b10/prop_ALS_s1__ALS.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · GeoGS(고친 판) · B0 · LoD2 | 42.8 | 42.83 (32,880점) | 같음 | SF/metrics/B0_b10/trust_LoD2_fix1__LoD2.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · GeoGS(고친 판) · B173 주변 · LoD2 | 8.7 | 8.67 (119,763점) | 같음 | SF/metrics/B173nb_b10/trust_LoD2_fix1__LoD2.json: spread.prior_error.main.spread |  |
| 7.1 | 과거 형상 유입률 · GeoGS(고친 판) · R1 · LoD2 | 43.2 | 43.20 (54,345점) | 같음 | SF/metrics/R1rep_b10/trust_LoD2_fix1__LoD2.json: spread.prior_error.main.spread |  |
| 7.1 | 세부 정확도 · 본 방법 · B173 주변 · LoD2 (cm) | 2.2 | 2.180 (씨앗 2.22, 2.14; 32,634점) | 같음 | S2/measure/B173nb_b10/LoD2__prop_LoD2_s0.json: condition3.new.nmad; S2/measure/B173nb_b10/LoD2__prop_LoD2_s1.json: condition3.new.nmad |  |
| 7.1 | 세부 정확도 · 본 방법 · B173 주변 · 항공 LiDAR (cm) | 2.3 | 2.327 (씨앗 2.35, 2.30; 35,345점) | 같음 | S2/measure/B173nb_b10/ALS__prop_ALS_s0.json: condition3.new.nmad; S2/measure/B173nb_b10/ALS__prop_ALS_s1.json: condition3.new.nmad | 저장값 2.35 cm는 반올림 경계라 측정 행에서 반올림 전 값 2.3536 cm를 다시 구해 맞대었다 |
| 7.1 | 세부 정확도 · 본 방법 · R1 · LoD2 (cm) | 5.1 | 5.090 (씨앗 4.91, 5.27; 74,638점) | 같음 | S2/measure/R1rep_b10/LoD2__prop_LoD2_s0.json: condition3.new.nmad; S2/measure/R1rep_b10/LoD2__prop_LoD2_s1.json: condition3.new.nmad |  |
| 7.1 | 세부 정확도 · 학습 전 사전 정보 · B173 주변 · LoD2 (cm) | 2.9 | 2.94 (32,634점) | 같음 | S2/measure/B173nb_b10/LoD2__samepath_LoD2.json: condition3.new.nmad |  |
| 7.1 | 세부 정확도 · 학습 전 사전 정보 · B173 주변 · 항공 LiDAR (cm) | 1.8 | 1.7482 (저장값 1.75; 35,345점) | 어긋남(저장값의 반올림 경계) | S2/measure/B173nb_b10/ALS__samepath_ALS.json: condition3.new.nmad | 저장값 1.75 cm는 반올림 경계라 측정 행에서 반올림 전 값 1.7482 cm를 다시 구해 맞대었다 |
| 7.1 | 세부 정확도 · 학습 전 사전 정보 · R1 · LoD2 (cm) | 17.8 (검토 기록 11절) / 17.85 (1단계 결론 3) | 파일 값 17.85(4자리 m 저장), 반올림 전 17.8476 cm (76,433점) [새로 셈: 측정 행에서 같은 식으로 다시 구함] | 같음 | S2/measure/R1rep_b10/LoD2__samepath_LoD2.json: condition3.new.nmad; S2/measure/R1rep_b10/LoD2__samepath_LoD2.npz: new | 반올림 전 값으로 한 자리 반올림하면 기록 17.8과 같다. 4자리로 저장한 17.85를 다시 반올림하면 17.9가 된다. 저장값 17.85 cm는 반올림 경계라 측정 행에서 반올림 전 값 17.8476 cm를 다시 구해 맞대었다 |
| 7.1 | 세부 정확도 · 결합 · B173 주변 · 항공 LiDAR (cm) | 1.76 | 1.76 (35,345점) | 같음 | SB/measure/B173nb_b10/ALS__mvsfuse_ALS.json: condition3.new.nmad |  |
| 7.1 | 결측 영역 완전성 0.2 m · 본 방법 · B0 · LoD2 | 93.6 | 93.550 (씨앗 94.38, 92.72; 12,433점) | 같음 | S1/metrics/B0_b10/prop_LoD2_s0__LoD2.json: completeness.missing_agreement.all.le_0.2; S1/metrics/B0_b10/prop_LoD2_s1__LoD2.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.1 | 결측 영역 완전성 0.2 m · 본 방법 · B173 주변 · LoD2 | 96.5 | 96.455 (씨앗 96.20, 96.71; 6,314점) | 같음 | S1/metrics/B173nb_b10/prop_LoD2_s0__LoD2.json: completeness.missing_agreement.all.le_0.2; S1/metrics/B173nb_b10/prop_LoD2_s1__LoD2.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.1 | 결측 영역 완전성 0.2 m · 본 방법 · R1 · LoD2 | 50.8 | 50.775 (씨앗 48.88, 52.67; 712점) | 같음 | S1/metrics/R1rep_b10/prop_LoD2_s0__LoD2.json: completeness.missing_agreement.all.le_0.2; S1/metrics/R1rep_b10/prop_LoD2_s1__LoD2.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.1 | 결측 영역 완전성 0.2 m · 본 방법 · R1 · 항공 LiDAR | 31.7 | 31.720 (씨앗 32.11, 31.33; 383점) | 같음 | S1/metrics/R1rep_b10/prop_ALS_s0__ALS.json: completeness.missing_agreement.all.le_0.2; S1/metrics/R1rep_b10/prop_ALS_s1__ALS.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.1 | 결측 영역 완전성 0.2 m · GeoGS · B173 주변 · LoD2 | 93.8 | 93.79 (6,314점) | 같음 | SF/metrics/B173nb_b10/trust_LoD2_fix1__LoD2.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.1 | F1 0.2 m · 본 방법 씨앗 0 · 1 · R1 · LoD2 | 67.4 · 69.1 | 67.44 · 69.06 | 같음 | S1/metrics/R1rep_b10/prop_LoD2_s0__LoD2.json: summary.f1_0.2; S1/metrics/R1rep_b10/prop_LoD2_s1__LoD2.json: summary.f1_0.2 |  |
| 7.1 | F1 0.2 m · 본 방법 씨앗 0 · 1 · B0 · LoD2 | 63.7 · 63.4 | 63.67 · 63.41 | 같음 | S1/metrics/B0_b10/prop_LoD2_s0__LoD2.json: summary.f1_0.2; S1/metrics/B0_b10/prop_LoD2_s1__LoD2.json: summary.f1_0.2 |  |
| 7.1 | 비교 방법 보고서의 답(과거 형상·결측·전체 완전성·관측 오류의 수) | 2DGS보다 과거 형상 낮음 넷; 결합보다 여섯(확인 둘); 결측 2DGS보다 나음 넷, GeoGS 나음 둘·못함 둘, 결합이 더 채움 셋; 전체 완전성 2DGS보다 여섯 모두 높음; 관측 오류 GeoGS·결합보다 여섯 모두, 2DGS보다 넷에서 높음 | 비교 방법 보고서 2절 답 줄과 같음(아래 t71의 셈으로 다시 확인) | 같음 | docs/experiments/phd/main_baselines_v1/본실험_비교방법_보고서_v1.md 78~115행; SB/tables/read.json | t71.md의 '비교 방법 보고서의 읽기' 표가 같은 수를 read.json에서 다시 센다 |
| 7.1 | 2DGS의 관측 오류 행 가운데 결과 면이 어느 쪽에도 없는 몫 · B173 주변 · LoD2 | 28.7 | 28.71 | 같음 | SB/metrics/B173nb_b10/imgonly_2dgs_s0__LoD2.json: spread.observation_error.main.neither |  |
| 7.1 | 2DGS의 관측 오류 행 가운데 결과 면이 어느 쪽에도 없는 몫 · B173 주변 · ALS | 32.6 | 32.64 | 같음 | SB/metrics/B173nb_b10/imgonly_2dgs_s0__ALS.json: spread.observation_error.main.neither |  |
| 7.1 | 결합이 잡은 표현 차이 넓이 몫 · B0 · LoD2 | 1.3 | 1.28 | 같음 | SB/tables/fusion_units/hits_B0_b10_LoD2.json: fusion.lod2_split_8_2.classes.representation.change_share |  |
| 7.1 | 결합이 잡은 표현 차이 넓이 몫 · R1 · LoD2 | 25.6 | 25.58 | 같음 | SB/tables/fusion_units/hits_R1rep_b10_LoD2.json: fusion.lod2_split_8_2.classes.representation.change_share |  |
| 7.1 | 코드 3에서 충돌(결합은 변화)로 본 몫의 범위 · 여섯 경우 | 본 방법 9~96 %, 결합 0.1~43 % | 본 방법(갈아 끼운 변형의 판정 = 학습 전 판정) 9.1~96.2 %, 결합 0.1~42.8 % | 같음 | SB/tables/fusion_units/hits_<지역>_<사전 정보>.json: variant.false.3, fusion.false.3 |  |
| 7.1 | 가상 시점 메시로 센 B173 긴 벽에 결과 면이 선 몫 | 본 방법 92.0 %, 2DGS 22.8 %, GeoGS 22.3 % | 비교 방법 보고서 3.3: 본 방법 92.0 %(씨앗 1: 92.7 %), 2DGS 22.8 %, GeoGS 22.3 %(가상 시점 메시); 92.0은 씨앗 0의 값 | 같음 | SB/figs/wall_presence.json; 비교 방법 보고서 199~202행 |  |
| 7.3 | 과거 형상 유입률 · 판정만 끔 · R1 · LoD2 | 25.5 | 25.45 (54,345점) | 같음 | S3/metrics/R1rep_b10/nojudge_LoD2_s0__LoD2.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 판정만 끔 · B0 · LoD2 | 14.8 | 14.75 (32,880점) | 같음 | S3/metrics/B0_b10/nojudge_LoD2_s0__LoD2.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 영상만 · B0 · LoD2 | 13.3 | 13.290 | 같음 | S1/metrics/B0_b10/imgonly_s0__LoD2.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 영상만 · B0 · 항공 LiDAR | 22.1 | 22.140 | 같음 | S1/metrics/B0_b10/imgonly_s0__ALS.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 영상만 · B173 주변 · LoD2 (평균, 씨앗 0, 씨앗 1) | 7.2 · 7.3 · 7.0 | 7.145 · 7.270 · 7.020 | 어긋남 | S1/metrics/B173nb_b10/imgonly_s0__LoD2.json: spread.prior_error.main.spread; S1/metrics/B173nb_b10/imgonly_s1__LoD2.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 영상만 · B173 주변 · 항공 LiDAR (평균, 씨앗 0, 씨앗 1) | 0.1 (0.04 · 0.07; 1단계 결론 1은 0.0) | 평균 0.055, 씨앗 0.04, 0.07 | 같음 | S1/metrics/B173nb_b10/imgonly_s0__ALS.json: spread.prior_error.main.spread; S1/metrics/B173nb_b10/imgonly_s1__ALS.json: spread.prior_error.main.spread | 1단계 결론 1의 '0.0'은 본 방법 값(0.03 %)을 적은 것으로 보인다(영상만 평균 0.055 %는 한 자리로 0.1) |
| 7.3 | 과거 형상 유입률 · 영상만 · R1 · LoD2 | 13.9 | 13.880 | 같음 | S1/metrics/R1rep_b10/imgonly_s0__LoD2.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 영상만 · R1 · 항공 LiDAR | 22.3 | 22.340 | 같음 | S1/metrics/R1rep_b10/imgonly_s0__ALS.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 사전 정보 신뢰 · B0 · 항공 LiDAR | 54.2 | 54.20 (262점) | 같음 | S1/metrics/B0_b10/trust_ALS__ALS.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 사전 정보 신뢰 · B173 주변 · 항공 LiDAR | 17.9 | 17.94 (96,117점) | 같음 | S1/metrics/B173nb_b10/trust_ALS__ALS.json: spread.prior_error.main.spread |  |
| 7.3 | 과거 형상 유입률 · 사전 정보 신뢰 · R1 · 항공 LiDAR | 47.6 | 47.57 (555점) | 같음 | S1/metrics/R1rep_b10/trust_ALS__ALS.json: spread.prior_error.main.spread |  |
| 7.3 | 세부 정확도 · 영상만 · R1 · LoD2 (cm) | 4.9 | 4.94 (74,553점) | 같음 | S2/measure/R1rep_b10/LoD2__imgonly_s0.json: condition3.new.nmad |  |
| 7.3 | 결측 영역 완전성 0.2 m · 사전 정보 신뢰 · R1 · 항공 LiDAR | 91.9 | 91.91 (383점) | 같음 | S1/metrics/R1rep_b10/trust_ALS__ALS.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · LoD2 세 지역 · 본 방법 씨앗 0 | 93.3 | 93.30 (19,459점, ['B0_b10', 'B173nb_b10', 'R1rep_b10']) | 같음 | S1/tables/final_extra.json: completeness.LoD2/prop_LoD2_s0/missing_agreement |  |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · LoD2 세 지역 · 본 방법 씨앗 1 | 92.5 | 92.55 (19,459점, ['B0_b10', 'B173nb_b10', 'R1rep_b10']) | 어긋남(반올림 방식만) | S1/tables/final_extra.json: completeness.LoD2/prop_LoD2_s1/missing_agreement |  |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · LoD2 세 지역 · 영상만 | 90.1 | 90.10 (19,459점, ['B0_b10', 'B173nb_b10', 'R1rep_b10']) | 같음 | S1/tables/final_extra.json: completeness.LoD2/imgonly_s0/missing_agreement |  |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · 항공 LiDAR 네 지역 · 본 방법 씨앗 0 | 41.6 | 41.62 (692점, ['B0_b10', 'B173nb_b10', 'B173_b0', 'R1rep_b10']) | 같음 | S1/tables/final_extra.json: completeness.ALS/prop_ALS_s0/missing_agreement |  |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · 항공 LiDAR 네 지역 · 본 방법 씨앗 1 | 39.0 | 39.02 (692점, ['B0_b10', 'B173nb_b10', 'B173_b0', 'R1rep_b10']) | 같음 | S1/tables/final_extra.json: completeness.ALS/prop_ALS_s1/missing_agreement |  |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · 항공 LiDAR · 영상만 | 38.8 | 38.75 (671점, ['B0_b10', 'B173nb_b10', 'R1rep_b10']) | 같음 | S1/tables/final_extra.json: completeness.ALS/imgonly_s0/missing_agreement | 표본이 다르다: 영상만은 B173만 결과가 없어 세 지역 671점이다(기록은 '네 지역 692점'의 줄에 함께 적음) |
| 7.3 | 지역을 합친 결측 영역 완전성 0.2 m · 항공 LiDAR 네 지역 · 사전 정보 신뢰 | 86.0 | 85.98 (692점, ['B0_b10', 'B173nb_b10', 'B173_b0', 'R1rep_b10']) | 같음 | S1/tables/final_extra.json: completeness.ALS/trust_ALS/missing_agreement |  |
| 7.3 | 판정만 끔의 관측 오류 유입률(영역 전체) 변화 | 다섯 경우에서 6 %p 안팎, R1 · LoD2에서 12 %p 줄었다 | B0_b10/LoD2 -0.66 (기준 1.57); B0_b10/ALS -5.82 (기준 1.57); B173nb_b10/LoD2 -6.22 (기준 2.67); B173nb_b10/ALS -6.04 (기준 1.57); R1rep_b10/LoD2 -12.17 (기준 1.57); R1rep_b10/ALS -6.32 (기준 1.57) | 말 확인 | S3/tables/sup.json: rows.<단위>.metrics.obs_inflow | 묶음: 줄어든 경우는 다섯이다(넷이 −5.8~−6.3 %p, R1 · LoD2가 −12.2 %p). B0 · LoD2는 −0.7 %p로 기준 안. '다섯 경우에서 6 %p 안팎'과 'R1에서 12 %p'를 따로 세면 여섯이 되므로 '다섯 경우(그 가운데 넷은 6 %p 안팎, R1 · LoD2는 12 %p)'가 묶음과 맞다 |
| 7.3 | 판정만 끔 · R1 · LoD2 결측 영역 완전성 차이 (%p) | +23 %p | +22.97 %p (기준 7.50) | 같음 | S3/tables/sup.json: rows.R1rep_b10/LoD2.metrics.missing_agreement_completeness | 기록은 정수로 적음 |
| 7.3 | 판정만 끔 · R1 · LoD2 결측 영역의 과거 형상 유입률 차이 (%p) | +37 %p | +37.03 %p (기준 0.35) | 같음 | S3/tables/sup.json: rows.R1rep_b10/LoD2.metrics.missing_prior_error_inflow | 기록은 정수로 적음 |
| 7.3 | 판정만 끔 · R1 · 항공 LiDAR 결측 영역은 그대로 | 그대로 | +1.18 %p (기준 3.29; 이 자리에서는 판정 없이도 같았다) | 같음 | S3/tables/sup.json: rows.R1rep_b10/ALS.metrics.missing_agreement_completeness |  |
| 7.3 | 날개에 심긴 점이 지워진 몫 · ALS/prop_ALS_s0 | 99.6 | 99.64 (15,360점) | 같음 | S3/meas8/wing.json: fate.ALS/prop_ALS_s0.shares.removed |  |
| 7.3 | 날개에 심긴 점이 지워진 몫 · ALS/prop_ALS_s1 | 99.4 | 99.41 (15,360점) | 같음 | S3/meas8/wing.json: fate.ALS/prop_ALS_s1.shares.removed |  |
| 7.3 | 날개에 심긴 점이 지워진 몫 · ALS/nojudge_ALS_s0 | 98.4 | 98.37 (15,360점) | 같음 | S3/meas8/wing.json: fate.ALS/nojudge_ALS_s0.shares.removed |  |
| 7.3 | 날개에 심긴 점이 지워진 몫 · ALS/trust_ALS | 95.7 | 95.72 (15,360점) | 같음 | S3/meas8/wing.json: fate.ALS/trust_ALS.shares.removed |  |
| 7.3 | 날개 단면 띠 591점의 과거 형상 유입률 · ALS/prop_ALS_s0 | 0.0 | 0.00 | 같음 | S3/meas8/wing.json: band.ALS/prop_ALS_s0.band_inflow |  |
| 7.3 | 날개 단면 띠 591점의 과거 형상 유입률 · ALS/nojudge_ALS_s0 | 0.0 | 0.00 | 같음 | S3/meas8/wing.json: band.ALS/nojudge_ALS_s0.band_inflow |  |
| 7.3 | 날개 단면 띠 591점의 과거 형상 유입률 · ALS/trust_ALS | 2.4 | 2.37 | 같음 | S3/meas8/wing.json: band.ALS/trust_ALS.band_inflow |  |
| 7.3 | R1 · LoD2 덩어리(16,032점) · 단면 띠(218점) 과거 형상 유입률 · prop_LoD2_s0 | 12.7 · 0.0 | 12.72 · 0.00 | 같음 | S3/meas8/blob.json: rows.results.prop_LoD2_s0.piece_11 / band_11 |  |
| 7.3 | R1 · LoD2 덩어리(16,032점) · 단면 띠(218점) 과거 형상 유입률 · prop_LoD2_s1 | 5.3 · 1.4 | 5.35 · 1.38 | 어긋남(반올림 방식만) | S3/meas8/blob.json: rows.results.prop_LoD2_s1.piece_11 / band_11 |  |
| 7.3 | R1 · LoD2 덩어리(16,032점) · 단면 띠(218점) 과거 형상 유입률 · nojudge_LoD2_s0 | 31.4 · 62.8 | 31.43 · 62.84 | 같음 | S3/meas8/blob.json: rows.results.nojudge_LoD2_s0.piece_11 / band_11 |  |
| 7.3 | R1 · LoD2 덩어리(16,032점) · 단면 띠(218점) 과거 형상 유입률 · trust_LoD2_fix1 | 47.0 · 78.9 | 47.01 · 78.90 | 같음 | S3/meas8/blob.json: rows.results.trust_LoD2_fix1.piece_11 / band_11 |  |
| 7.3 | 판정 빌려 오기 끄기 · B173 주변 LoD2는 본 방법과 같았다 | 같았다 | 결측 영역의 과거 형상 유입률 24.26 대 20.76(기준 4.26), 결측 영역 완전성 96.09 대 96.45(기준 3.29): 둘 다 기준 안 | 같음 | S3/tables/retry.json: rows.B173nb_b10/abl_prop_LoD2_s0 |  |
| 7.3 | 절단 8배 · R1 LoD2: 관문 판단 같음, 작은 오류 구간 보정률이 기준 밖 | 관문 판단이 같았으나 작은 오류 구간의 보정률이 기준 밖 | 관문 조건 1~4 판단 같음; 0~1τ 8배 55.5 % < 기준 띠 59.0~63.6 % | 같음 | S3/tables/retry.json: rows.R1rep_b10/sens_trunc8_LoD2_s0.gate_again; S3/figs/retry_trunc.json |  |
| 7.4 | 영상이 확인하지 못한 넓이 몫 · B0_b10 | 3.2 | 3.193 | 같음 | S3/tables/stage3.json: q3_2.unseen_share.B0_b10 |  |
| 7.4 | 영상이 확인하지 못한 넓이 몫 · B0a15 | 49.4 | 49.412 | 같음 | S3/tables/stage3.json: q3_2.unseen_share.B0a15 |  |
| 7.4 | 영상이 확인하지 못한 넓이 몫 · B0a9 | 53.5 | 53.518 | 같음 | S3/tables/stage3.json: q3_2.unseen_share.B0a9 |  |
| 7.4 | 영상이 확인하지 못한 넓이 몫 · B0a3 | 71.1 | 71.062 | 같음 | S3/tables/stage3.json: q3_2.unseen_share.B0a3 |  |
| 7.4 | 상속률 · 본 방법 · B0a15 | 99.3 | 99.250 (씨앗 99.25) | 같음 | S3/tables/stage3.json: values.inheritance.B0a15 |  |
| 7.4 | 상속률 · 본 방법 · B0a9 | 99.6 | 99.620 (씨앗 99.62) | 같음 | S3/tables/stage3.json: values.inheritance.B0a9 |  |
| 7.4 | 상속률 · 본 방법 · B0a3 | 96.2 | 96.220 (씨앗 96.40, 96.04) | 같음 | S3/tables/stage3.json: values.inheritance.B0a3 |  |
| 7.4 | 저자 3장 과거 형상 유입률 · 본 방법 | 26.3 | 26.250 | 같음 | S3/tables/stage3.json: values.prior_error_inflow.B0a3.method_seeds |  |
| 7.4 | 저자 3장 과거 형상 유입률 · 영상만 | 11.8 | 11.795 | 같음 | S3/tables/stage3.json: values.prior_error_inflow.B0a3.imgonly_seeds |  |
| 7.4 | 저자 3장 과거 형상 유입률 · 고친 GeoGS | 29.8 | 29.750 | 같음 | S3/tables/stage3.json: values.prior_error_inflow.B0a3.geogs |  |
| 7.4 | 저자 3장의 실패가 면 22에 몰린 크기 '코드 11 행의 66 %' | 코드 11 행의 66 % | 3,596 / 5,465 = 65.8 % — 저자 3장 코드 11 행 전체(솎은 주 행)의 몫이다(과거 형상 쪽 행의 몫이 아님) | 같음(뜻 확인) | S3/meas8/where33.json; 3단계 보고서 135행·1246행 |  |
| 7.4 | 학습 전 판정이 면 22의 바뀐 곳 72 %를 일치로 봄 | 72 % | 30.5 / 42.5 m² = 71.8 % | 같음 | 3단계 보고서 1265행(같은 면의 코드 11 패치 판정 표) |  |
| 7.4 | 저자 3장의 틀린 결측 영역(코드 13) 넓이 | 165 m² | 165.25 m² | 같음 | S3/tables/stage3.json: areas.B0a3.area_m2.13 |  |
| 7.4 | 저자 15장(2단계 짝) · 과거 형상 유입률 · 결측 영역 완전성 · F1 | 4.3 · 73.9 · 36.1 | 4.31 · 73.87 · 36.08 | 같음 | S2/metrics/B0a15/prop_LoD2_s0__LoD2.json: spread.prior_error.main.spread; S2/metrics/B0a15/prop_LoD2_s0__LoD2.json: completeness.missing_agreement.all.le_0.2; S2/metrics/B0a15/prop_LoD2_s0__LoD2.json: summary.f1_0.2 |  |
| 7.4 | 영상 전체 · 과거 형상 유입률 · 결측 영역 완전성 · F1 (씨앗 0 · 1) | 12.1·11.9 · 94.4·92.7 · 63.7·63.4 | 12.10 · 11.86 · 94.38 · 92.72 · 63.67 · 63.41 | 같음 | S1/metrics/B0_b10/prop_LoD2_s0·s1__LoD2.json |  |
| 7.4 | 학습 전 판정의 잘못 놓음: 5.8 %에서 영상 두 장 조건의 21.8 %로 | 5.8 → 21.8 | 영상 전체(학습 243장) 5.83 %, 저자 3장(학습 2장) 21.82 %; 연직 포함 2장(학습 2장)은 42.71 % | 같음 | S3/prep/judge5.json: rows.B0_full / B0a3 / B0n2.shares.wrong_release | 5.8 %는 영상 전체(1단계 B0), '두 장 조건'은 학습 영상 2장인 저자 3장이다 |
| 7.4 | 넓이: 243장 → 13장(저자 15장) 지지 일치 · 결측(4+13) · 비가시(5+14) | 3,260 → 1,636 · 130 → 420 · 1,591 새로 | 3260.25 · 1636.25 · 129.9375 · 419.5 · 1591.125 | 같음 | S3/tables/stage3.json: areas |  |
| 7.2 | 학습 전 판정의 잘못 놓음 · 잘못 지킴 · B173 주변 · LoD2 | 3.5 · 9.2 | 3.55 · 9.19 (참 라벨 넓이 4116.1 m²) | 어긋남(반올림 방식만) | S2/prep/workload.json: units.B173nb_b10/LoD2.mask.judgment_default |  |
| 7.2 | 마스크를 끈 판정의 잘못 놓음 · 잘못 지킴 · B173 주변 · LoD2 | 7.1 · 6.8 | 7.11 · 6.77 | 같음 | S2/prep/workload.json: units.B173nb_b10/LoD2.mask.judgment_maskoff |  |
| 7.2 | 학습 전 판정의 잘못 놓음 · 잘못 지킴 · R1 · 항공 LiDAR | 27.9 · 0.45 | 27.88 · 0.45 (참 라벨 넓이 1524.6 m²) | 같음 | S2/prep/workload.json: units.R1rep_b10/ALS.mask.judgment_default |  |
| 7.2 | 마스크를 끈 판정의 잘못 놓음 · 잘못 지킴 · R1 · 항공 LiDAR | 38.8 · 0.24 | 38.84 · 0.24 | 같음 | S2/prep/workload.json: units.R1rep_b10/ALS.mask.judgment_maskoff |  |
| 7.2 | 참 라벨이 있는 평가 범위의 패치 수 · B173nb_b10/LoD2 | 65,858패치(B173 주변 LoD2), 22,948패치(R1 항공 LiDAR) | {'labelled_patches': 65858, 'labelled_area_m2': 4116.1} | 옮김(아래 t72에서 자세히) | S2/figs/maskpre_B173.json |  |
| 7.2 | 참 라벨이 있는 평가 범위의 패치 수 · R1rep_b10/ALS | 65,858패치(B173 주변 LoD2), 22,948패치(R1 항공 LiDAR) | {'labelled_patches': 22948, 'labelled_area_m2': 1524.6} | 옮김(아래 t72에서 자세히) | S2/figs/maskpre_R1.json |  |
| 7.2 | 빌려 온 판정 · R1 · 항공 LiDAR | 88개 모두 충돌, 그 가운데 68개가 참 일치 | 빌려 온 판정 88개: 충돌 88, 일치 0; 충돌 가운데 참 일치 68 | 같음 | S2/prep/workload.json: units.R1rep_b10/ALS.propagation |  |
| 7.2 | 빌려 온 판정 · B173 주변 · LoD2 | 2,749개(일치 1,771, 충돌 978), 참 라벨이 있는 것은 일치 1,216개와 충돌 92개 | 2749 (일치 1771, 충돌 978; 참 라벨 있는 일치 1216, 충돌 92) | 같음 | S2/prep/workload.json: units.B173nb_b10/LoD2.propagation |  |
| 7.2 | B173만 장면 안 값: 정합 · 허용 오차 | 정합 −4.2~−4.6 m, 허용 오차 2.9~3.6 m | LoD2 정합 [0.0, 0.0, -4.231], τ {'roof': 3.647, 'wall': 0.637}; 항공 LiDAR 정합 [0.0, 0.0, -4.618], τ {'roof': 2.857, 'wall': 2.857} | 말 확인 | C6/t5/judge/counts.json: b173_self.<사전 정보>.own_shift / own_tau | LoD2 벽의 τ(0.64 m)는 범위 '2.9~3.6 m' 밖이다(지붕 3.65, 항공 LiDAR 2.86) |
| 7.2 | B173만 장면 안 값의 잘못 지킴 · LoD2 · 항공 LiDAR | LoD2 9.7 → 40.2 %, 항공 LiDAR 0.5 → 89.6 %(채우기 쪽 정의 9.0 → 44.1 %는 대조하지 않음) | 장면 안 값: LoD2 40.20 %, 항공 LiDAR 89.57 %; 고정 값 9.7 · 0.5 %는 6장 보조 보고서 T6 | 같음 | C6/t5/judge/counts.json: b173_self.<사전 정보>.all; docs/experiments/phd/ch6_support_v1/tables/t5_tables.md T6 | 채우기 쪽 정의의 값(9.0 → 44.1 %)은 채우기의 값이라 옮기거나 대조하지 않는다 |
| 7.2 | 거른 영상 오류에서 고르는 곳의 판정이 충돌로 놓은 몫 LoD2 30.3 %, 항공 LiDAR 26.0 % | 30.3 · 26.0 | 채우기(PHD-MAIN-FILL-v1) 일 2·8.4의 값이라 이 요청에서 대조하지 않는다 | 대조하지 않음(채우기의 값) | — |  |
| 7.5 | 전제 위배 넓이 · B0 (LoD2 · 항공 LiDAR, m²) | 211 · 43 | 210.7 · 42.7 | 같음 | C6/t5/judge/counts.json: evaluation.B0_b10/<사전 정보> 'undecidable_passed' 넓이 합 |  |
| 7.5 | 전제 위배 넓이 · B173 주변 (LoD2 · 항공 LiDAR, m²) | 139 · 52 | 139.4 · 51.8 | 같음 | C6/t5/judge/counts.json: evaluation.B173nb_b10/<사전 정보> 'undecidable_passed' 넓이 합 |  |
| 7.5 | 전제 위배 넓이 · R1 (LoD2 · 항공 LiDAR, m²) | 403 · 163 | 402.7 · 163.4 | 같음 | C6/t5/judge/counts.json: evaluation.R1rep_b10/<사전 정보> 'undecidable_passed' 넓이 합 |  |
| 7.5 | 전제 위배 넓이 · B173만 (LoD2 · 항공 LiDAR, m²) | 189 · 71 | 188.9 · 71.2 | 같음 | C6/t5/judge/counts.json: evaluation.B173_b0/<사전 정보> 'undecidable_passed' 넓이 합 |  |
| 7.5 | 유리 채광창에서 결과가 영상을 따른 몫(본 방법 · 본 방법 · 영상만 · 영상만 · 사전 정보) | 61.3 · 59.9 · 58.8 · 59.0 · 6.5 | 61.30 · 59.86 · 58.76 · 59.01 · 6.51 | 같음 | S1/metrics/B173nb_b10/prop_LoD2_s0__LoD2.json: spread.premise_violation_interior.main.spread; S1/metrics/B173nb_b10/prop_LoD2_s1__LoD2.json: spread.premise_violation_interior.main.spread; S1/metrics/B173nb_b10/imgonly_s0__LoD2.json: spread.premise_violation_interior.main.spread; S1/metrics/B173nb_b10/imgonly_s1__LoD2.json: spread.premise_violation_interior.main.spread; S1/metrics/B173nb_b10/samepath_LoD2__LoD2.json: spread.premise_violation_interior.main.spread | 이 값은 B173 주변 · LoD2 전제 위배 영역 전체의 '전제 위배 안 유입률'이다. 1단계 결론별 그림 v2가 그 영역을 유리 채광창(톱니)으로 읽었다(vis2_measures.json sites.B173nb_b10.checks.premise_inflow) |
| 7.5 | 유리 채광창 참값의 첫 층 몫 | 34.3 | 34.30 (지붕 꼴 전제 위배 패치 0.25 m 안의 참값 점) | 같음 | docs/experiments/phd/main_stage1_v1/tables/vis2_measures.json: sites.B173nb_b10.values.gt_layers.top_share |  |
| 7.5 | 전제 위배 둘레 2 m 완전성: 본 방법 − 영상만 | 여섯 경우 모두 0.7~3.2 %p 높고, 그 가운데 셋은 0.94 %p 안 | B0 · LoD2 +0.93; B0 · 항공 LiDAR +0.72; B173 주변 · LoD2 +1.45; B173 주변 · 항공 LiDAR +1.71; R1 · LoD2 +0.77; R1 · 항공 LiDAR +3.17 (범위 0.72~3.17, 0.94 안 3) | 같음 | S1/metrics/<지역>/prop_<p>_s0·s1, imgonly_s0 __<p>.json: completeness.premise_band.all.le_0.2 |  |
| 7.5 | R1 · 항공 LiDAR 둘레 2 m 완전성 본 방법 씨앗 0 · 1 | 97.9 · 96.7 | 97.90 · 96.73 | 같음 | S1/metrics/R1rep_b10/prop_ALS_s0__ALS.json: completeness.premise_band.all.le_0.2; S1/metrics/R1rep_b10/prop_ALS_s1__ALS.json: completeness.premise_band.all.le_0.2 |  |
| 7.5 | 경계 밖 0.25~0.5 m 칸 · 1~2 m 칸 (본 방법 · 영상만, %) | 90.0 · 87.6 / 98.4 · 97.8 | 89.97 · 87.58 / 98.43 · 97.76 | 같음 | docs/experiments/phd/main_stage1_v1/tables/vis2_measures.json: curves (B173 주변 · LoD2만) | 두 칸은 B173 주변 · LoD2 한 경우의 값이다(여섯 경우를 합친 값이 아님). 1~2 m는 0.25 m 칸 넷의 단순 평균, 두 씨앗 평균 |
| 7.5 | B173만 · LoD2 · prior_error_inflow 씨앗 0(r14) · 1 | 5.47 · 5.08 | 5.47 · 5.08 | 같음 | SF/metrics/B173_b0/prop_LoD2_s0__LoD2.json: spread.prior_error.main.spread; S1/metrics/B173_b0/prop_LoD2_s1__LoD2.json: spread.prior_error.main.spread |  |
| 7.5 | B173만 · LoD2 · band_c02 씨앗 0(r14) · 1 | 95.40 · 95.02 | 95.40 · 95.02 | 같음 | SF/metrics/B173_b0/prop_LoD2_s0__LoD2.json: completeness.premise_band.all.le_0.2; S1/metrics/B173_b0/prop_LoD2_s1__LoD2.json: completeness.premise_band.all.le_0.2 |  |
| 7.5 | B173만 · LoD2 · obs_within_inflow 씨앗 0(r14) · 1 | 67.3 · 68.0 | 67.31 · 67.96 | 같음 | SF/metrics/B173_b0/prop_LoD2_s0__LoD2.json: spread.observation_error_within_threshold.main.spread; S1/metrics/B173_b0/prop_LoD2_s1__LoD2.json: spread.observation_error_within_threshold.main.spread |  |
| 7.5 | B173만 · LoD2 · missing_c02 씨앗 0(r14) · 1 | 92.99 · 93.15 | 92.99 · 93.15 | 같음 | SF/metrics/B173_b0/prop_LoD2_s0__LoD2.json: completeness.missing_agreement.all.le_0.2; S1/metrics/B173_b0/prop_LoD2_s1__LoD2.json: completeness.missing_agreement.all.le_0.2 |  |
| 7.5 | B173만 · LoD2 · 상속률 씨앗 0 · 1 | 83.0 · 84.5 | 83.01 · 84.52 | 같음 | SF/metrics/B173_b0/prop_LoD2_s0__LoD2.json: unseen.inheritance_rate_inferred; S1/metrics/B173_b0/prop_LoD2_s1__LoD2.json: unseen.inheritance_rate_inferred |  |
| 7.5 | B173만 · LoD2 · 세부 정확도 씨앗 0 · 1 (cm) | 9.19 · 4.60 | 9.19 · 4.60 | 같음 | SF/measure/B173_b0/LoD2__prop_LoD2_s0.json: condition3.new.nmad; S2/measure/B173_b0/LoD2__prop_LoD2_s1.json: condition3.new.nmad |  |
| 7.5 | B173만 · LoD2 · 고친 GeoGS 과거 형상 유입률 | 20.80 | 20.80 | 같음 | SF/metrics/B173_b0/trust_LoD2_fix1__LoD2.json: spread.prior_error.main.spread |  |

- 줄 111개 가운데 같음 101, 어긋남 5(그 가운데 반올림 방식만 다른 것 3, 저장값의 반올림 경계 1), 말 확인 2, 대조하지 않음 1.

