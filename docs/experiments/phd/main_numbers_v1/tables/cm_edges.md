# 반올림 경계의 cm 값 (PHD-MAIN-NUMBERS-v1)

- 만든 때 2026-10-19 02:53:21 KST, 스크립트 `scripts/phd/main_numbers_v1/cm_edges.py`.
- 측정 파일은 NMAD와 치우침을 m 단위 소수 넷째 자리로 저장한다. 그래서 x.x5 cm로 저장된 값은 소수 첫째 자리에서 어느 쪽으로도 반올림될 수 있다. 이런 값은 측정 행(같은 이름의 .npz)에서 같은 식(치우침 = 중앙값, NMAD = 1.4826 × |x − 중앙값|의 중앙값)으로 반올림 전 값을 다시 구했고, 표와 숫자표는 그 값을 쓴다[새로 셈].
- 값 23개 가운데 소수 첫째 자리가 저장값과 달라지는 것은 16개다.

| 출처 (측정 파일: 키) | 저장값 (cm) | 반올림 전 (cm) | 측정 행 | 첫째 자리: 저장값 → 반올림 전 | 쓰인 표 |
|---|---:|---:|---:|---|---|
| S2/measure/B0_b10/ALS__prop_ALS_s1.json: condition3.new.nmad | 4.65 | 4.6467 | 4,443 | 4.7 → 4.6 (달라짐) | t71, t73 |
| S2/measure/B0_b10/LoD2__samepath_LoD2.json: condition3.new.nmad | 1.45 | 1.4498 | 514 | 1.5 → 1.4 (달라짐) | t71 |
| S2/measure/B173_b0/ALS__prop_ALS_s1.json: condition3.new.nmad | 8.95 | 8.9464 | 2,469 | 9.0 → 8.9 (달라짐) | t75 |
| S2/measure/B173nb_b10/ALS__prop_ALS_s0.json: condition3.new.nmad | 2.35 | 2.3536 | 35,345 | 2.4 → 2.4 | t71, t73 |
| S2/measure/B173nb_b10/ALS__prop_ALS_s1.json: condition3.new.bias | 6.85 | 6.8510 | 35,345 | 6.9 → 6.9 | t71, t73 |
| S2/measure/B173nb_b10/ALS__samepath_ALS.json: condition3.new.nmad | 1.75 | 1.7482 | 35,345 | 1.8 → 1.7 (달라짐) | t71 |
| S2/measure/B173nb_b10/LoD2__prop_LoD2_s0.json: condition3.new.bias | 7.05 | 7.0458 | 32,634 | 7.1 → 7.0 (달라짐) | t71, t73 |
| S2/measure/R1rep_b10/ALS__prop_ALS_s0.json: condition3.new.nmad | 4.45 | 4.4455 | 79,262 | 4.5 → 4.4 (달라짐) | t71, t73 |
| S2/measure/R1rep_b10/LoD2__samepath_LoD2.json: condition3.new.nmad | 17.85 | 17.8476 | 76,433 | 17.9 → 17.8 (달라짐) | t71 |
| SB/measure/B0_b10/ALS__geogs_ALS_fix1.json: condition3.new.nmad | 14.75 | 14.7545 | 4,424 | 14.8 → 14.8 | t71 |
| SB/measure/B0_b10/ALS__imgonly_2dgs_s0.json: condition3.new.nmad | 16.25 | 16.2465 | 4,167 | 16.3 → 16.2 (달라짐) | t71 |
| SB/measure/B173_b0/ALS__geogs_ALS_fix1.json: condition3.new.nmad | 11.85 | 11.8503 | 2,469 | 11.9 → 11.9 | t75 |
| SB/measure/B173nb_b10/LoD2__judgefuse_LoD2.json: condition3.new.bias | 9.65 | 9.6489 | 32,634 | 9.7 → 9.6 (달라짐) | t73 |
| SB/measure/B173nb_b10/LoD2__judgefuse_LoD2.json: condition3.new.nmad | 2.95 | 2.9514 | 32,634 | 3.0 → 3.0 | t73 |
| SB/measure/B173nb_b10/LoD2__mvsfuse_LoD2.json: condition3.new.nmad | 2.95 | 2.9493 | 32,634 | 3.0 → 2.9 (달라짐) | t71 |
| SB/measure/R1rep_b10/LoD2__judgefuse_LoD2.json: condition3.new.nmad | 17.65 | 17.6477 | 75,749 | 17.7 → 17.6 (달라짐) | t73 |
| SF/measure/B0_b10/LoD2__trust_LoD2_fix1.json: condition3.new.bias | 28.25 | 28.2503 | 514 | 28.3 → 28.3 | t71 |
| SF/measure/B0_b10/LoD2__trust_LoD2_fix1.json: condition3.new.nmad | 12.25 | 12.2485 | 514 | 12.3 → 12.2 (달라짐) | t71 |
| SF/measure/B173_b0/LoD2__prop_LoD2_s0.json: condition3.new.bias | 5.05 | 5.0520 | 781 | 5.1 → 5.1 | t75 |
| SF/measure/R1rep_b10/LoD2__trust_LoD2_fix1.json: condition3.new.bias | 0.05 | 0.0454 | 74,501 | 0.1 → 0.0 (달라짐) | t71 |
| SL/measure/B173_b0/LoD2__cdgsnofit_LoD2_s0.json: condition3.new.nmad | 62.05 | 62.0486 | 4 | 62.1 → 62.0 (달라짐) | t75 |
| SL/measure/B173nb_b10/LoD2__cdgsnofit_LoD2_s0.json: condition3.new.nmad | 39.65 | 39.6474 | 18,543 | 39.7 → 39.6 (달라짐) | t71 |
| SL/measure/R1rep_b10/ALS__cdgsnofit_ALS_s0.json: condition3.new.nmad | 76.15 | 76.1460 | 18,885 | 76.2 → 76.1 (달라짐) | t71 |
