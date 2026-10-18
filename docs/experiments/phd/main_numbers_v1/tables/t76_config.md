# 실험 구성표 (PHD-MAIN-NUMBERS-v1)

- 만든 때 2026-10-19 02:53:20 KST, 스크립트 `scripts/phd/main_numbers_v1/common_cfg.py`. 칸 = 학습 시도 수 · 마지막 상태 · 코드 판. 영상만과 2DGS는 한 학습을 두 사전 정보 단위에서 세었으므로 두 칸에 같은 수가 적힌다.
- 출처: 1단계 S1/tables/final_extra.json times(B173 주변 본 방법은 0단계 학습), 2단계 S2/tables/final_runs.json, 고침 SF/tables/fix_runs.json·fix_r14_status.json, 3단계 S3/tables/times.json, 비교 방법 SB/tables/status.json.
- CDGS(덧붙임 10-19): 빈칸 채우기의 대기열 상태 SL/jobs/state.json과 학습 영수증 SL/runs/<지역>/<결과>/receipt.json. 변형(크기 맞추기 생략)의 칸이고, B0 · LoD2에는 공식 확인 판을 함께 적었다. debug는 10-18 15:42부터 끔(사용자 결정, 채우기 설정 바꿈 #4), 후처리 TSDF는 조각으로(10-18 사용자 결정 (가), #3).

| 방법 | B0 · LoD2 | B0 · 항공 LiDAR | B173 주변 · LoD2 | B173 주변 · 항공 LiDAR | R1 · LoD2 | R1 · 항공 LiDAR | B173만 · LoD2 | B173만 · 항공 LiDAR | 영상 수 조건 (B0 · LoD2) |
|---|---|---|---|---|---|---|---|---|---|
| 본 방법 (prop, 씨앗 0 · 1) | 2회 · 끝남 · r12 | 2회 · 끝남 · r12 | 2회 · 끝남 · 0단계 학습(r12) | 2회 · 끝남 · 0단계 학습(r12) | 2회 · 끝남 · r12 | 2회 · 끝남 · r12 | 6회(그 가운데 메모리 부족 4) · 끝남 · r12, r14(고침) | 2회 · 끝남 · r12 | 9회(그 가운데 메모리 부족 2) · 끝남 · r13(2단계 짝), r15, r15 + cull3 래스터라이저 |
| 영상만 (imgonly; 한 학습을 두 사전 정보 단위에서 셈) | 2회(그 가운데 메모리 부족 1) · 끝남 · r12 | 2회(그 가운데 메모리 부족 1) · 끝남 · r12 | 2회 · 끝남 · r12 | 2회 · 끝남 · r12 | 1회 · 끝남 · r12 | 1회 · 끝남 · r12 | 3회(그 가운데 메모리 부족 3) · 결과 없음 · r12, r14(고침) | 3회(그 가운데 메모리 부족 3) · 결과 없음 · r12, r14(고침) | 7회 · 끝남 · r15 |
| 사전 정보 신뢰 (trust_ALS) | — | 1회 · 끝남 · r12(판정·구간 끔) | — | 1회 · 끝남 · r12(판정·구간 끔) | — | 1회 · 끝남 · r12(판정·구간 끔) | — | 1회 · 끝남 · r12(판정·구간 끔) | — |
| 항공 LiDAR 1배 (prop_ALS1x_s0) | — | 1회 · 끝남 · r12 | — | — | — | 1회 · 끝남 · r12 | — | — | — |
| 판정만 끈 본 방법 (nojudge) | 1회 · 끝남 · r15 | 1회 · 끝남 · r15 | 1회 · 끝남 · r15 | 1회 · 끝남 · r15 | 1회 · 끝남 · r15 | 1회 · 끝남 · r15 | — | — | — |
| 갈아 끼운 결합 (judgefuse; 학습 없음) | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | 학습 없음 · 끝남 · judgefuse | — |
| 장치를 끈 학습과 값을 바꾼 학습 (2단계, 고침, 3단계 다시 시도) | 1회 · 끝남 · r13(abl_densj_LoD2_s0) | — | 8회(그 가운데 메모리 부족 3) · 끝남 · r13(abl_mask_LoD2_s0), r13(abl_prop_LoD2_s0), r13(abl_prot_LoD2_s0), r13(sens_e1000_LoD2_s0), r13(sens_e250_LoD2_s0), r13(sens_enone_LoD2_s0), r14(고침: abl_prop_LoD2_s0), r15(3단계 다시 시도: abl_prop_LoD2_s0) | 1회 · 끝남 · r13(abl_band_ALS_s0) | 6회(그 가운데 메모리 부족 2) · 끝남 · r13(abl_band_LoD2_s0), r13(abl_lossj_LoD2_s0), r13(sens_trunc2_LoD2_s0), r13(sens_trunc8_LoD2_s0), r14(고침: sens_trunc8_LoD2_s0), r15(3단계 다시 시도: sens_trunc8_LoD2_s0) | 3회(그 가운데 메모리 부족 1) · 끝남 · r13(abl_initx_ALS_s0), r13(abl_mask_ALS_s0), r13(abl_prop_ALS_s0) | — | — | 3회 · 끝남 · r13(abl_prop_LoD2_s0), r13(abl_prot_LoD2_s0), r13(sens_dist05_LoD2_s0) |
| 2DGS (imgonly_2dgs_s0; 한 학습을 두 단위에서 셈) | 1회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 | 1회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 | 1회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 | 1회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 | 1회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 | 1회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 | 2회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 · 첫 시도 메모리 부족 뒤 2번째에 끝남 | 2회 · 끝남 · 2DGS f3e3b9f + 어댑터 v1 · 첫 시도 메모리 부족 뒤 2번째에 끝남 | — |
| GeoGS LoD2 1단계 판 (trust_LoD2) | 1회 · 끝남 · GeoGS db40c95 + 어댑터 둘 | — | 1회 · 끝남 · GeoGS db40c95 + 어댑터 둘 | — | 1회 · 끝남 · GeoGS db40c95 + 어댑터 둘 | — | 1회 · 끝남 · GeoGS db40c95 + 어댑터 둘 | — | — |
| GeoGS LoD2 고친 판 (trust_LoD2_fix1) | 1회 · 끝남 · 고친 GeoGS(fix1) | — | 1회 · 끝남 · 고친 GeoGS(fix1) | — | 1회 · 끝남 · 고친 GeoGS(fix1) · 후처리는 3단계 5.0에서 혼자 다시 함 | — | 1회 · 끝남 · 고친 GeoGS(fix1) | — | 6회 · 끝남 · 고친 GeoGS(fix1) |
| GeoGS 항공 LiDAR (geogs_ALS_fix1) | — | 1회 · 끝남 · 고친 GeoGS(fix1) | — | 1회 · 끝남 · 고친 GeoGS(fix1) | — | 1회 · 끝남 · 고친 GeoGS(fix1) | — | 1회 · 끝남 · 고친 GeoGS(fix1) | — |
| 결합 (mvsfuse; 학습 없음) | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | 학습 없음 · 끝남 · Zhou 외 2020 재현 | — |
| CDGS | 1회 · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 켬(공식 기본값); 후처리 조각 TSDF · 공식 확인 1회 · 끝남(어댑터 v2, 크기 맞추기) | 1회 · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; 후처리 조각 TSDF | 2회(일부러 멈춤 1) · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; debug 켠 첫 판을 일부러 멈춤 1; 후처리 조각 TSDF | 2회(일부러 멈춤 1) · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; debug 켠 첫 판을 일부러 멈춤 1; 후처리 조각 TSDF | 1회 · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; 후처리 조각 TSDF | 1회 · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; 후처리 조각 TSDF | 1회 · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; 후처리 조각 TSDF | 1회 · 끝남 · CDGS db853c1 + 어댑터 v3(크기 맞추기 생략) · debug 끔; 후처리 조각 TSDF | — |

- 장치를 끈 학습과 값을 바꾼 학습의 칸에는 그 자리에서 돈 모든 일감을 함께 적었다(무엇인지는 코드 판의 괄호).
- 3단계 연직 포함 13장 본 방법은 세 번째 시도에 래스터라이저 고침(cull3)으로 끝났다(r15 + cull3).

