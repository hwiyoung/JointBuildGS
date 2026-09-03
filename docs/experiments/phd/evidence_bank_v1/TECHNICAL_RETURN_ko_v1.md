# T1 증거 은행 v1 기술 반환 (XY 컬럼 짝 위의 3D-a·3D-b·2D-c, 기대 대 실제)

> 지위: `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`. 작업 ID `PHD-EVIDENCE-BANK-v1`.
> 리뷰어: 김휘영. 생성: 2026-09-02. 사용자 지시(2026-09-03 밤): "T1을 끝까지, 기대 결과와 실제 결과를 비교해 평가".
> 수식 절: 설계 v2 부록 D-3·D-7(실행 전 작성, 기대표 D-3.5 포함).

## 결론

동결 파일럿 prism의 XY 셀 짝(`PHD-PATCH-PAIRING-XY-v1`, 위층 3,600셀)마다 세 증거를 쟀다.
3D-a는 동결 M3C2 관계 core를 셀에 귀속해 집계했고, 3D-b는 prism 8모서리를 모두 담는 exact-937 카메라 **113장**의
자세로 MVS·ALS z-buffer와 타일 전체 MVS 가림 버퍼를 만들어 광선을 AGREE / PENETRATE / BLOCK / MVS_ONLY / NO_LANDING /
OCCLUDED로 분류했으며, 2D-c는 같은 113장 영상의 국소 텍스처·비가림 뷰 수·최적 입사각에서 검정력 플래그와 r을 냈다.
실행 전에 적어 둔 기대표 11항목 중 **8항목 충족**. 증거는 판정이 아니며 책임·가중치·δ·변화는 결정하지 않았다.

## 기대 대 실제

pairing 상태별 실측(위층 셀; 3D-b 비율은 검정 광선 = AGREE+PENETRATE+BLOCK 중):

| 상태 | 면적 m² (거친) | core 수 / d 중앙 m / LoD 중앙 m | 검정 광선 | AGREE / PENETRATE / BLOCK | MVS_ONLY / NO_LANDING / OCCLUDED | 텍스처 / 비가림 뷰 / 최적 입사각° | r 0/1/2/3 셀 |
|---|---:|---|---:|---|---|---|---|
| COMPATIBLE | 310 (25 거친) | 160 / -0.03 / 0.033 | 369,815 | 0.81 / 0.10 / 0.09 | 8,399 / 14,094 / 500,903 | 21.9 / 8 / 12 | 0/77/1034/130 |
| PRIOR_ABOVE | 407 (100 거친) | 256 / 2.31 / 0.070 | 380,467 | 0.06 / 0.91 / 0.03 | 59,226 / 186,082 / 697,399 | 16.1 / 6 / 7 | 0/342/1100/186 |
| CURRENT_ABOVE | 163 (118 거친) | 178 / -0.13 / 0.220 | 448,789 | 0.38 / 0.20 / 0.42 | 87,971 / 53,688 / 712,583 | 23.3 / 21 / 23 | 0/220/353/78 |
| PRIOR_ONLY | 8 (0 거친) | 2 / — / — | 2,626 | 0.09 / 0.82 / 0.09 | 28 / 8,722 / 20,469 | 20.4 / 0 / — | 23/9/2/0 |
| CURRENT_ONLY | 12 (3 거친) | 14 / -0.00 / 0.166 | 24,146 | 0.42 / 0.10 / 0.48 | 8,740 / 1,716 / 51,640 | 24.5 / 8 / 12 | 0/8/30/8 |

기대표(D-3.5, 실행 전) 대 실제:

| 상태 | 검사 | 결과 | 기대(요약) |
|---|---|---|---|
| COMPATIBLE | 3D-a median |d| <= 0.3 | 충족 | median |d| <= 0.3 m · AGREE >= 0.70 of tested · r >= 3 for the majority (planar) |
| COMPATIBLE | 3D-b AGREE >= 0.70 | 충족 | median |d| <= 0.3 m · AGREE >= 0.70 of tested · r >= 3 for the majority (planar) |
| COMPATIBLE | r >= 3 majority | 미충족 | median |d| <= 0.3 m · AGREE >= 0.70 of tested · r >= 3 for the majority (planar) |
| PRIOR_ABOVE | 3D-a median d in [1,5] m | 충족 | median d in [1.0, 5.0] m, >> LoD · PENETRATE >= 0.50 of tested · r >= 3 for the majority (planar) |
| PRIOR_ABOVE | 3D-b PENETRATE >= 0.50 | 충족 | median d in [1.0, 5.0] m, >> LoD · PENETRATE >= 0.50 of tested · r >= 3 for the majority (planar) |
| PRIOR_ABOVE | r >= 3 majority | 미충족 | median d in [1.0, 5.0] m, >> LoD · PENETRATE >= 0.50 of tested · r >= 3 for the majority (planar) |
| CURRENT_ABOVE | 3D-b BLOCK >= PENETRATE | 충족 | mixed · BLOCK >= PENETRATE · r <= 2 for the majority (rough) |
| CURRENT_ABOVE | r <= 2 majority | 충족 | mixed · BLOCK >= PENETRATE · r <= 2 for the majority (rough) |
| PRIOR_ONLY | 3D-b NO_LANDING dominant | 충족 | few cores · NO_LANDING dominant, tested < 20 · r <= 1 |
| PRIOR_ONLY | r <= 1 majority | 충족 | few cores · NO_LANDING dominant, tested < 20 · r <= 1 |
| CURRENT_ONLY | 3D-b MVS_ONLY dominant | 미충족 | class 3 · MVS_ONLY dominant · r n/a |

## 판독

**기대표 11항목 중 8 충족.** 방향은 전부 기대대로 갈렸다.

- 철거 지붕 자리(PRIOR_ABOVE, 407 m²): 검정 광선 38만 개 중 **PENETRATE 91 %**, AGREE 6 %. 3D-a core 256개의 부호 거리 중앙값
  +2.31 m(LoD 0.07 m). 패치 짝 수준에서는 옛 지붕면 4·1·5·(66→1)이 MVS 지면 패치 1과 짝지어져 PENETRATE 0.97~0.99, d +0.4~+2.8 m,
  r = 3. 현재 카메라 113장의 광선이 2022 지붕면 높이를 지나 2024 광장 바닥에 닿는다는 뜻이며, "MVS가 지붕을 놓친 것"과는 서명이
  다르다(그 경우 광선은 착지하지 못해 NO_LANDING이 됐을 것).
- 양립(COMPATIBLE, 310 m²): AGREE 81 %, |d| 중앙값 0.03 m. 가장 큰 짝(MVS 지면 1 – ALS 지면 3, 551셀)은 AGREE 0.94, d −0.03, r 3.
- 수목(CURRENT_ABOVE, 163 m², 118 m² 거친): BLOCK 42 % ≥ PENETRATE 20 %, AGREE 38 %; r ≤ 2가 다수. 수관은 세 분류가 섞이는
  것이 정상이며 거친 표시가 그 자리를 알려 준다.
- 수관 아래(PRIOR_ONLY, 8.5 m²): NO_LANDING 8,722 대 검정 광선 2,626, 비가림 뷰 중앙값 0, r ≤ 1(23셀은 r = 0). **관측 불가가
  구조적으로 유보로 나오는 자리**다(R5).

**미충족 3항목과 원인.**

1. COMPATIBLE·PRIOR_ABOVE의 "r ≥ 3 다수"(셀 수준): 3D-a 표본(관계 core)이 2 m 간격이라 0.5 m 셀의 약 85 %에는 core가 없다
   (COMPATIBLE 1,241셀 중 1,096, PRIOR_ABOVE 1,628 중 1,383). 기대표가 셀 수준의 표본 밀도를 무시한 오류이며, 패치 짝 수준
   (core ≥ 3)에서는 큰 짝이 모두 r = 3이다. 2D-a 검정력이 빠진 셀은 대부분 입사각 조건(> 75° 또는 거친 패치의 법선 없음)이다.
2. CURRENT_ONLY의 "MVS_ONLY 우세": 검정 광선 24,146 대 MVS_ONLY 8,740. pairing은 "0.5 m 셀에 ALS 점 2개 미만"을 ALS 없음으로
   보지만 3D-b의 ALS z-buffer는 2 px 스플랫으로 그 틈을 메운다. 두 정의가 다르고, 해당 면적은 12 m²다. 다음 판에서 "ALS 없음"의
   정의를 하나로 맞춘다(스플랫 반경을 셀 크기와 묶거나, pairing의 최소 점 수를 완화).
3. OCCLUDED 광선이 상태마다 50만~70만 개로 크다. 사선 뷰(off-nadir 중앙값 65°)에서 prism 밖 고층 건물이 가리는 광선을 타일
   가림 버퍼가 제거한 결과이며, 검정 광선 수(상태당 2.4만~45만)는 충분하다.

**전체 평가.** 3D-b는 세 상황(철거·양립·수목)을 기대한 방향으로 강하게 가르고, 3D-a는 같은 방향을 독립적으로 확인하며(철거 자리 +2.3 m
대 LoD 0.07 m), 관측 불가 자리는 유보로 나온다. 셀 수준 r은 표본 밀도 때문에 2가 상한이라 단위는 패치 짝(또는 core 간격 이상 셀)이
맞다. 이 결과는 증거 채널의 서명이 설계 §5.2 표와 맞는다는 확인이지, 소스 판정·변화 판정이 아니다.

## 검증·산출물

Docker unittest 4개(광선 분류 D-3a 7사례·z-buffer 최근접·텍스처·기대 검사기) 통과. validator: `cell_consistency`, `determinism_rerun`, `input_hashes_and_upstream_binding`, `output_hashes`, `prohibited_inputs`, `scientific_verdict_null` 전부 PASS
(결정론 재실행 포함). 입력은 pairing·패치 manifest/receipt 결속, 관계 지도, 파티션, cameras/images.bin, exact-937 crosswalk의 SHA-256을
먼저 확인했고, 영상 113장의 SHA-256은 `evidence_views.json`에 기록했다(영상은 2D-c 텍스처에만 사용, 모델 색 없음).
산출물: `evidence_cells.npy`, `evidence_pairs.npy`, `evidence_views.json`, `evaluation.json`, `evidence_preview.png`, `technical_return.json`,
`artifact_manifest.json`, `validation_receipt.json`. SHA-256은 `artifacts/manifests/phd/evidence_bank_v1/technical_result_manifest_v1.json`.

## 결정하지 않은 것과 다음

책임(T4)·가중치·δ·변화 판정 없음. 2D-a(뷰간 warp-NCC, T2)와 잡음 모형(T3)은 미착수. 다음은 T3 보정용 합성 주입과 T2다.
