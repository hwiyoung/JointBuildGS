# P2 C1/C2 대표 3동 정성·정량 비교판 v4 기술 보고서

## 결과

- task: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v4`
- status: `TECHNICAL_DIAGNOSTIC_SAMPLE_COMPLETE`
- case sheets: `3`
- PNG panels: `60`
- quantitative source rows: `6`
- display methods: `C1_L_upper`, `C2_MVS`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

v4는 봉인된 C1/C2 input, Roofer output 및 기존 정량 source만 읽어 요청한 3개
case sheet를 완성했다. Roofer, G2, GS training 및 metric을 다시 실행하지 않았다.
v1/v2 partial과 다른 representative partial은 수정·삭제·재사용하지 않았다.

## Artifact

- absolute root:
  `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_comparison_matrix_sample_v4/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v4`
- artifact URI:
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v4/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v4`
- files: `129`
- bytes: `146317538`
- tree SHA-256: `98c126710aebe76137d5dbede7cc0cef37c6f7ca78e4bc93d9b9b0fa0003c885`

주요 진입점:

- qualitative index: `qualitative/index.html`
- exact six rows: `metrics/sample_building_method_metrics_v1.csv`
- quantitative summary: `metrics/sample_quantitative_summary_v1.csv`
- finalized record: `control/finalized_v1.json`

## 정량 source 6행

아래 값은 새 계산이 아니라 봉인된 source row의 표시용 전사다.

| building | size | method | association | reference role | cells | height MAE m | RMSZ m | surface RMSE m | P95 m | G0/G1/G2 |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| DEBY_LOD2_4907177 | small | C1 | SHARED_AND_MULTI_COMPONENT | SELF_REFERENCE_DIAGNOSTIC_ONLY | 15 | 11.5535 | 11.5556 | 11.5556 | 11.9770 | F/F/F |
| DEBY_LOD2_4907177 | small | C2 | SHARED_AND_MULTI_COMPONENT | UAS_PATCH_CANDIDATE_SCORE_ONLY | 15 | 12.2415 | 12.2435 | 12.2435 | 12.6650 | F/F/F |
| DEBY_LOD2_4906975 | medium | C1 | SHARED_AND_MULTI_COMPONENT | SELF_REFERENCE_DIAGNOSTIC_ONLY | 805 | 4.4178 | 5.3815 | 5.3815 | 11.7682 | F/F/F |
| DEBY_LOD2_4906975 | medium | C2 | SHARED_COMPONENT | UAS_PATCH_CANDIDATE_SCORE_ONLY | 805 | 4.9023 | 5.7643 | 5.7643 | 12.4562 | F/F/F |
| DEBY_LOD2_108580336 | large | C1 | SHARED_AND_MULTI_COMPONENT | SELF_REFERENCE_DIAGNOSTIC_ONLY | 2568 | 7.9758 | 10.2041 | 10.2041 | 17.9838 | F/F/F |
| DEBY_LOD2_108580336 | large | C2 | SHARED_AND_MULTI_COMPONENT | UAS_PATCH_CANDIDATE_SCORE_ONLY | 2568 | 7.7763 | 10.1081 | 10.1081 | 18.6718 | F/F/F |

`G0/G1/G2=false`는 source가 기록한 shared/multi-component association의 건물 단위
기술 상태다. 이 표에서 C1/C2의 우열이나 사용 가능성을 판정하지 않는다.

## Hash와 binding 검증

- finalized: `case_count=3`, `panel_count=60`
- method panel counts: RAW `12`, C1 `24`, C2 `24`
- panel artifact hash: `60/60 PASS`
- projection receipt 존재 및 hash: `60/60 PASS`
- metric binding: `66/66 PASS`
- exact quantitative CSV와 source row: `6/6 PASS`
- summary rows: `6/6 PASS`
- required panel visible reference: `60/60 PASS`, minimum visible count `15`
- prohibited C3/C4/C5 method ID in case HTML: `0`

건물별 reference subset과 evaluation support hash는 모든 panel/receipt/metric binding에서
일치했다.

| building | reference subset SHA-256 | evaluation support SHA-256 |
|---|---|---|
| DEBY_LOD2_4907177 | `2c8f3f7bf092b3ffb0357e1c10eea5029fbe3ab783178c4f7bdb38d584e8473e` | `2be4f07d08bdb9e7116aebab6688be11c37e54fd9297a09776d1720a83f51bd0` |
| DEBY_LOD2_4906975 | `81756af3ec9a294aa6a518fdaa72798b4becab90a55c787db249e3ef2ab11375` | `da50ec7375d7efe38591cf972f7d9770f1192eb1596d03e97b0c63815089ac35` |
| DEBY_LOD2_108580336 | `ac84f1173c89c77d649756b0a1e081078f3f937c0e07c0e2bbbc7d8c444be432` | `6f78cde9d7116428aa964c180fdf1f12bfdeb4cf53a4ee5d7b56a938bf4f21c1` |

## 원본 해상도 시각 검토

세 case HTML을 각각 `2400x3600`으로 렌더링해 직접 확인했다.

- small: 15개 reference cell이 4개 raw crop과 모든 spatial/section panel에 보인다.
  일부 raw crop은 reference가 작아 매우 타이트하지만 누락 panel은 없다.
- medium: 805개 reference cell이 복합 지붕 영역과 reference-centered section에 보인다.
- large: 2568개 reference cell이 넓은 복합 영역과 principal section에 보인다.
- 모든 case에서 C1은 `METRIC: SELF_REFERENCE_DIAGNOSTIC_ONLY`와
  `GREEN OVERLAY: STRICT_INDEPENDENT_UAS`를 분리 표시한다.
- C2는 metric과 green overlay 모두 독립 UAS reference 역할로 표시한다.

## 실행 계수

| 항목 | 횟수 |
|---|---:|
| comparison renderer | 1 |
| Roofer invocation | 0 |
| G2 invocation | 0 |
| GS training | 0 |
| metric recomputation | 0 |
| C3/C4/C5 method-artifact access | 0 |

## 해석 경계

`scientific_verdict: null`은 이 비교판이 기술적 관찰·검토용 산출물이며 C1/C2의 과학적
우열, 일반화 또는 `PASS_usable`을 승인하지 않았다는 뜻이다. 공식 G3/G4/PASS는 모두
null로 유지된다.
