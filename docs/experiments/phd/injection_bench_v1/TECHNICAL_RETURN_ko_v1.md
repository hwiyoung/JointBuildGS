# 주입 벤치 v1 기술 반환 (2026-09-04)

> 지위: `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`. 작업 ID `PHD-INJECTION-BENCH-v1`. 설계: `DESIGN_ko_v1.md`(코드 전, 기대 (a)~(d) 사전 등록).
> 대상 prism 2, 기준 실행 `PHD-*-P2-v1`. 조각 15칸(135 m²) on 양립 평면 셀 1986개. 변형 8종 각각 패치→pairing→T1→T2 를 동결 드라이버로 실행, validator 전부 PASS.

## 기대 대 실제

| 기대 | 결과 |
|---|---|
| (a) V7 BLOCK dominant and delta < 0 | 충족 |
| (a) V8 PENETRATE dominant and delta > 0 | 충족 |
| (b) V5 S_P >= 0.6 | 충족 |
| (b) V5 n_pairs_m = 0 and NO_LANDING dominant | 충족 |
| (c) V1 PENETRATE >= 0.5 and delta > 0 | 미충족 |
| (c) V1 compatible cells read as PRIOR_ABOVE (majority) | 충족 |
| (c) V2 dz coherent (variance <= 0.1, sign >= 0.95) | 충족 |
| (c) V8 outside patches stays compatible (|dz mean| <= 0.15) | 충족 |
| (d) V4 horizontal shift unobservable on ground (|dz| <= 0.15, |delta| <= 0.1) | 충족 |

충족 8 / 9.

## 변형별 실측 (주입 셀 그룹; 대조 = 주입 안 된 양립 평면 셀)

| 변형 | 셀 주입 / 대조 | pairing 최빈 상태 | dz 중앙 | 3D-b A / P / B | 무착지 vs 검정 광선 | 쌍 M / P 중앙 | S_M / S_P | Δ | f(M>P) / f(P>M) | 기준 대비 ΔS_M / ΔS_P | 잠정 판독 적중률 |
|---|---|---|---:|---|---|---|---|---:|---|---|---:|
| V1 als_shift_all | 1986 / 0 | PRIOR_ABOVE | 0.46 | 0.80 / 0.18 / 0.01 | 18953 vs 874466 | 20 / 19 | 0.94 / 0.70 | 0.20 | 0.68 / 0.00 | 0.00 / -0.19 | 0.07 |
| V2 als_shift_all | 1986 / 0 | PRIOR_ABOVE | 0.96 | 0.02 / 0.97 / 0.01 | 33094 vs 905972 | 20 / 18 | 0.94 / 0.50 | 0.40 | 0.85 / 0.00 | 0.00 / -0.37 | 0.78 |
| V3 als_shift_all | 1986 / 0 | PRIOR_ABOVE | 1.96 | 0.02 / 0.97 / 0.01 | 61416 vs 908775 | 20 / 18 | 0.94 / 0.38 | 0.52 | 0.87 / 0.00 | 0.00 / -0.52 | 0.81 |
| V4 als_shift_all | 1986 / 0 | COMPATIBLE | -0.05 | 0.84 / 0.14 / 0.01 | 13798 vs 967150 | 20 / 19 | 0.94 / 0.93 | 0.00 | 0.13 / 0.05 | 0.00 / -0.00 | 0.05 |
| V5 mvs_delete_patches | 539 / 1480 | PRIOR_ONLY | — | 0.00 / 1.00 / 0.00 | 224042 vs 683 | 0 / 22 | 0.92 / 0.94 | -0.01 | 0.04 / 0.15 | -0.01 / 0.00 | 0.59 |
| V6 mvs_noise_patches | 540 / 1480 | CURRENT_ABOVE | -0.31 | 0.68 / 0.01 / 0.31 | 2212 vs 252909 | 24 / 22 | 0.82 / 0.94 | -0.08 | 0.02 / 0.41 | -0.09 / 0.00 | 0.33 |
| V7 mvs_shift_patches | 540 / 1480 | CURRENT_ABOVE | -1.04 | 0.00 / 0.01 / 0.99 | 7573 vs 263081 | 24 / 22 | 0.45 / 0.94 | -0.44 | 0.01 / 0.84 | -0.46 / 0.00 | 0.83 |
| V8 als_shift_patches | 540 / 1480 | PRIOR_ABOVE | 1.96 | 0.02 / 0.96 / 0.02 | 9857 vs 285073 | 24 / 22 | 0.93 / 0.35 | 0.51 | 0.88 / 0.00 | 0.00 / -0.58 | 0.88 |

결맞음(정합 오차의 식별 근거; dz 통계):

| 변형 | 주입 셀 dz 평균 | 분산 | 부호 일치 | 대조 셀 dz 평균 | 대조 분산 |
|---|---:|---:|---:|---:|---:|
| V1 | 0.44 | 0.010 | 1.00 | — | — |
| V2 | 0.94 | 0.010 | 1.00 | — | — |
| V3 | 1.94 | 0.010 | 1.00 | — | — |
| V4 | 0.36 | 3.991 | 0.81 | — | — |
| V5 | — | — | — | -0.05 | 0.012 |
| V6 | -0.47 | 2.373 | 0.98 | -0.05 | 0.012 |
| V7 | -1.21 | 1.966 | 1.00 | -0.05 | 0.012 |
| V8 | 1.75 | 2.424 | 0.99 | -0.05 | 0.014 |

잠정 판독(D-7 손 규칙 + Δ 부호) 혼동:

| 변형 | 목표 판독 | 주입 셀 판독 분포 | 대조 셀 판독 분포 |
|---|---|---|---|
| V1 | PRIOR_WRONG_OR_DELTA | ABSTAIN 7 / H_C 202 / OTHER 1640 / PRIOR_WRONG_OR_DELTA 137 |  |
| V2 | PRIOR_WRONG_OR_DELTA | ABSTAIN 5 / OTHER 433 / PRIOR_WRONG_OR_DELTA 1548 |  |
| V3 | PRIOR_WRONG_OR_DELTA | ABSTAIN 5 / OTHER 371 / PRIOR_WRONG_OR_DELTA 1610 |  |
| V4 | PRIOR_WRONG_OR_DELTA | ABSTAIN 21 / H_C 1632 / OTHER 240 / PRIOR_WRONG_OR_DELTA 93 |  |
| V5 | H_M_missing | ABSTAIN 219 / H_M_missing 317 / OTHER 3 | ABSTAIN 4 / H_C 1315 / OTHER 124 / PRIOR_WRONG_OR_DELTA 37 |
| V6 | H_C | ABSTAIN 3 / H_C 177 / H_M_biased 102 / OTHER 258 | ABSTAIN 4 / H_C 1315 / OTHER 124 / PRIOR_WRONG_OR_DELTA 37 |
| V7 | H_M_biased | ABSTAIN 3 / H_M_biased 446 / OTHER 91 | ABSTAIN 4 / H_C 1315 / OTHER 124 / PRIOR_WRONG_OR_DELTA 37 |
| V8 | PRIOR_WRONG_OR_DELTA | ABSTAIN 1 / OTHER 63 / PRIOR_WRONG_OR_DELTA 476 | ABSTAIN 6 / H_C 1320 / OTHER 113 / PRIOR_WRONG_OR_DELTA 41 |

## 판독

**기대 8/9 충족. 미충족 1건은 문턱의 자리표 문제다.**

1. **(a) MVS 편향과 옛 표면 소실은 두 채널 모두에서 부호가 갈린다 — 기여 1 의 핵심이 통제 표본에서 성립.** V7(MVS +1 m)은 3D-b 차단 0.99·Δ −0.44
   (S_M 0.45 대 S_P 0.94, 사진이 P 지지), V8(ALS +2 m)은 관통 0.96·Δ +0.51(사진이 M 지지). 잔차 크기(|dz| 1.0 대 2.0)로는 같은 처방이 나올 자리에서
   광선의 방향(차단/관통)과 사진의 편(P/M)이 함께 갈린다. 잠정 손 규칙의 적중률 83 %·88 %.
2. **(b) MVS 결손은 "관측 불가 + 사진이 P 를 부정하지 않음"으로 나온다.** V5 에서 주입 셀의 M 쌍 0, 무착지 광선이 검정 광선보다 많고, P 로 옮긴 NCC 는
   S_P 0.94 로 기준 실행의 S_M(0.94)과 같다. 즉 MVS 가 비어도 사진은 옛 표면을 그대로 설명한다 — H_M 결손에서 prior 에 권위를 줄 근거가 사진에 있다.
   적중률 59 %: 조각 경계 셀은 2 m 창이 이웃 MVS 를 끌어와 S_M 이 생기므로 규칙이 유보·기타로 읽는다(창 크기의 해상도 한계, 기록).
3. **(c) 정합 오차 δ_z 는 0.5 m 부터 순차 판독을 "옛 것이 위"로 뒤집는다.** V1(0.5 m): 양립 셀의 90 % 가 PRIOR_ABOVE, 사진 Δ +0.20·f(M>P) 0.68 — 그러나
   광선은 아직 일치 0.80(허용 τ = 0.5 m 와 같은 크기라 경계). 미충족 1건이 이것이다: 관통 문턱 0.5 는 δ 0.5 에서 못 넘는다(자리표 문제, 기록).
   V2(1 m)·V3(2 m): 관통 0.97, Δ +0.40·+0.52 — 셀 단위로는 변화(V8)와 **구분 불가**. 그러나 dz 결맞음이 가른다: δ 변형은 dz 분산 0.010·부호 일치 1.00
   (건물 전체가 같은 벡터), V8 은 조각 안만 +2 m 이고 조각 밖 대조 셀의 dz 평균은 ≤ 0.15 m(국소). **은행은 δ 를 식별할 정보를 담는다** — 3D-c 결맞음
   채널이 T3·T6 에 필요한 이유이며, 셀 단위 채널만 쓰는 순차 판독은 0.5 m 정합 오차에서 prism 전체를 변화로 오독한다.
4. **(d) 수평 1 m 는 수평면에서 보이지 않는다.** V4: dz −0.05·Δ 0.00, 양립 88 % 유지; 경사·모서리에서만 dz 분산이 튄다(3.99). §7 의 관측성 진술 확인.
5. **V6 잡음(σ 0.3 m)은 품질 비대칭 서명이다.** 광선 일치 0.68·차단 0.31(잡음이 위아래로 흩어짐), S_M 0.82 < S_P 0.94, Δ −0.08 — prism 3 지붕에서 본 것과
   같은 방향이고 약하다. pairing 의 위층이 잡음의 윗봉우리를 잡아 dz −0.31 로 기울며(상태 CURRENT_ABOVE 로 새는 셀 발생), 손 규칙 적중률 33 % — 잡음은
   손 규칙이 아니라 T3 의 우도(σ 비대칭 + 사진 P 우세)가 맡아야 한다.

**반복 필요성에 대한 뜻.** 이 벤치가 답한 절반은 "정합 오차가 0.5 m 이상이면 셀 단위 순차 판독이 틀리고, 그 오류를 되돌릴 정보(결맞은 dz)가 은행에 있다"
이다. 남은 절반 — 그 정보를 쓰는 δ 추정이 판정 루프 **안**에 있어야 하는가(양립 책임에서 δ̂), 아니면 판정 **앞**의 강건 정합 한 번으로 충분한가(선행
L2M-Reg 식) — 는 T6 이 있어야 잰다. 지금 실측으로는 변화 면적이 국소(V8: 135 m² / 2,208 m²)일 때 강건 정합 한 번이 전역 δ 를 잡을 가능성이 크고,
반복이 꼭 필요한 조건은 "변화 면적이 커서 양립 셀을 먼저 골라야 δ 를 잴 수 있는 경우"로 좁혀진다.

**한계.** 조각 15칸(135 m²)·prism 2 한 곳·수직 δ 3단계뿐이며, 3D-a 는 동결 core 라 벤치에서 재계산되지 않았다(pairing dz 로 대신). 잡음 변형의
pairing 위층 편향은 D-1/pairing 의 "위층 = 최고 패치" 규칙의 부작용으로 기록한다.

## 산출물

`PHD-INJECTION-BENCH-v1/Vk/` 주입 파티션·진실 플래그·manifest(해시 동결), 하위 워크스트림 `*-BENCH-Vk-v1` 4 × 8, `bench_evaluation.json`. Git manifest `artifacts/manifests/phd/injection_bench_v1/`.
