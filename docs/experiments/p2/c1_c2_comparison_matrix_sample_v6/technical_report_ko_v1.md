# P2 C1/C2 대표 3동 정성·정량 비교판 v6 기술 보고서

## 결과

- task: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v6`
- status: `TECHNICAL_DIAGNOSTIC_SAMPLE_COMPLETE`
- case sheets: `3` (`3180x3070`)
- panel PNG: `60` (RAW 12, C1 24, C2 24)
- quantitative source rows: `6`
- display methods: `C1_L_upper`, `C2_MVS`
- exact renderer source commit: `da0e106bd2d4b087f028febdd5ae508c01f9e245`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

v6는 봉인된 C1/C2 input, Roofer output과 기존 정량 source만 읽어 3개 건물의
비교판을 완성했다. Roofer, G2, GS training과 metric을 다시 실행하지 않았다.
v1–v5의 final/partial namespace는 삭제·수정·재사용하지 않았다.

## 표시 계약

각 case sheet는 5행 x 4열이다.

1. current RGB raw 4장: 평가 전용 2022 LoD2 `RoofSurface` roofline을 노란색으로 투영
2. C1 current UAS LiDAR input: 주황 점선 footprint/roofprint와 독립 UAS 평가 cell
3. C1 봉인 Roofer output: 출력 roof surface/edge와 독립 UAS 평가 cell
4. C2 current-image MVS input: 동일 표시 계약
5. C2 봉인 Roofer output: 동일 표시 계약

공간 panel은 `TOP / OBLIQUE_1 / OBLIQUE_2 / PRINCIPAL_SECTION` 순서다. current
UAS LiDAR와 동일 획득 드론 RGB에는 수직 이동 `0 m`를 적용했다. `45.7 m`는
2022 orthometric LoD2 roofline을 current RGB에 평가용으로 투영할 때만 한 번 적용했다.

## Artifact

- absolute root:
  `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_comparison_matrix_sample_v6/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v6`
- artifact URI:
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v6/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v6`
- files: `132`
- bytes: `389717562`
- tree SHA-256: `27f7bf0f94fde17633b26b773a2e45e8bba592ae4ca72f4bc62d4571e41bb324`

주요 진입점은 `qualitative/index.html`, `metrics/sample_quantitative_summary_v1.csv`,
`metrics/sample_building_method_metrics_v1.csv`, `control/finalized_v1.json`이다.

## 정량 source 6행

아래 값은 새 계산이 아니라 봉인된 source row의 표시용 전사다.

| building | method | association | reference role | cells | height MAE m | RMSZ m | surface RMSE m | P95 m | G0/G1/G2 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| DEBY_LOD2_4907177 | C1 | SHARED_AND_MULTI_COMPONENT | SELF_REFERENCE_DIAGNOSTIC_ONLY | 15 | 11.5535 | 11.5556 | 11.5556 | 11.9770 | F/F/F |
| DEBY_LOD2_4907177 | C2 | SHARED_AND_MULTI_COMPONENT | UAS_PATCH_CANDIDATE_SCORE_ONLY | 15 | 12.2415 | 12.2435 | 12.2435 | 12.6650 | F/F/F |
| DEBY_LOD2_4906975 | C1 | SHARED_AND_MULTI_COMPONENT | SELF_REFERENCE_DIAGNOSTIC_ONLY | 805 | 4.4178 | 5.3815 | 5.3815 | 11.7682 | F/F/F |
| DEBY_LOD2_4906975 | C2 | SHARED_COMPONENT | UAS_PATCH_CANDIDATE_SCORE_ONLY | 805 | 4.9023 | 5.7643 | 5.7643 | 12.4562 | F/F/F |
| DEBY_LOD2_108580336 | C1 | SHARED_AND_MULTI_COMPONENT | SELF_REFERENCE_DIAGNOSTIC_ONLY | 2568 | 7.9758 | 10.2041 | 10.2041 | 17.9838 | F/F/F |
| DEBY_LOD2_108580336 | C2 | SHARED_AND_MULTI_COMPONENT | UAS_PATCH_CANDIDATE_SCORE_ONLY | 2568 | 7.7763 | 10.1081 | 10.1081 | 18.6718 | F/F/F |

`G0/G1/G2=false`는 봉인 source가 기록한 shared/multi-component association의 건물
단위 기술 상태다. 이 표만으로 C1/C2 우열이나 사용 가능성을 판정하지 않는다.

## Hash와 binding 검증

- finalized: `case_count=3`, `panel_count=60`
- panel artifact hash: `60/60 PASS`
- projection receipt 존재 및 hash: `60/60 PASS`
- metric binding의 panel/reference/support hash: `66/66 PASS`
- exact quantitative rows: `6/6 PASS`
- required panel visible reference: `60/60 PASS`, minimum visible count `15`
- prohibited C3/C4/C5 method artifact access: `0`

| building | reference subset SHA-256 | evaluation support SHA-256 |
|---|---|---|
| DEBY_LOD2_4907177 | `2c8f3f7bf092b3ffb0357e1c10eea5029fbe3ab783178c4f7bdb38d584e8473e` | `1e43dc84d0eba17abed979567ad76f079a57573aa7d9bc9cc4ef6953f9977554` |
| DEBY_LOD2_4906975 | `81756af3ec9a294aa6a518fdaa72798b4becab90a55c787db249e3ef2ab11375` | `607968dde762b2721bc33f6982b4b9f3369c924a809dd0bd94d25d5093dff8f3` |
| DEBY_LOD2_108580336 | `ac84f1173c89c77d649756b0a1e081078f3f937c0e07c0e2bbbc7d8c444be432` | `dbe13c263f82c113372da2571511a4d273226730607c9c6cce74317a30183657` |

## 원본 해상도 시각 검토

- `DEBY_LOD2_4906975`: RGB roofline, input support와 Roofer output의 대상 건물이
  육안으로 식별되며 C1/C2 차이를 동일한 네 시점에서 읽을 수 있다.
- `DEBY_LOD2_108580336`: 넓은 복합 지붕에서 input/output과 독립 UAS 평가 cell을
  구분할 수 있다. green cell이 넓지만 출력 edge와 색·범례가 분리돼 있다.
- `DEBY_LOD2_4907177`: 렌더링 누락이나 Roofer 실패가 아니다. 2024 RGB의 현재 지붕과
  2022 LoD2 roofline/ID가 일치하지 않는 것으로 보여 `REFERENCE/ID ALIGNMENT REVIEW`로
  유지한다. 이 case의 수치와 시각 overlay는 정합 확인 전 과학 해석에 쓰지 않는다.

C1의 정량은 `SELF_REFERENCE_DIAGNOSTIC_ONLY`이고, green overlay는 독립 current UAS
평가 cell이다. 두 역할은 제목·범례·색으로 분리했다. C2의 green overlay도 같은 독립
current UAS 평가 support이며 Roofer 출력 자체를 뜻하지 않는다.

## 실행 계수와 해석 경계

| 항목 | 횟수 |
|---|---:|
| comparison renderer | 1 |
| Roofer invocation | 0 |
| G2 invocation | 0 |
| GS training | 0 |
| metric recomputation | 0 |
| C3/C4/C5 method-artifact access | 0 |

`scientific_verdict: null`은 이 비교판이 재현 가능한 기술 관찰·검토 산출물이라는
뜻이며 C1/C2의 과학적 우열, 일반화, 최신성 판정 또는 `PASS_usable` 승인이 아니다.
