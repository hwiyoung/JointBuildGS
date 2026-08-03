# P2 representative comparison matrix sample v1

## Handoff metadata

- handoff_id: `P2-W2C-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v1`
- task_id: `P2-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v1`
- phase: `P2 technical diagnostic presentation`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `8f70cb81dd73c0fe6b8c008f60198bbc7953313b`
- target_branch: `main`
- research canon: `C1C5_CANON_v2` through `DEC-P1-016`
- user_approval: `GRANTED — proceed with the exact three-building qualitative/quantitative sample`
- independent_review: `PASS — scientific scope/leakage and reproducibility/binding reviews`
- scientific_verdict: `null`

## Goal

이미 봉인된 U_target 199 C1/C2/C3 산출물에서 outcome-free로 고른 독립 reference
3동만 사용해 `DEC-P1-016` 형식의 정성·정량 sample matrix를 만든다. 성능·Roofer·GS를
재실행하지 않고 현재 결과가 건물 단위에서 무엇을 보여주며 왜 실패하는지 사람이
한눈에 확인할 수 있게 한다.

## Exact sample

| 크기 | building_id | group | bbox area |
|---|---|---|---:|
| small | `DEBY_LOD2_4906974` | `GROUP_ca1040234a79aaa8` | 692.182 m² |
| medium | `DEBY_LOD2_4907176` | `GROUP_681774d532569646` | 875.655 m² |
| large | `DEBY_LOD2_4906968` | `GROUP_ccf535781f75c1c0` | 6,763.557 m² |

선택에는 strict independent-reference 여부, bbox 크기, 공간 group과 중심 거리만
사용했다. method metric, gate, PASS와 그림은 사용하지 않았다.

## In scope

1. 각 건물의 서로 다른 current raw image 4장에 UAS roof reference를 투영한다.
2. C1 LiDAR input/output, C2 MVS input/output, C3 rendering/surface/output을
   `TOP/OBLIQUE_1/OBLIQUE_2/PRINCIPAL_SECTION`으로 표시한다.
3. 봉인된 C3 run에 RGB+semantic rendering artifact가 없으면 reference overlay를
   유지한 빈 panel에 `OUTPUT_MISSING`을 표시한다.
4. C4/C5는 실행하지 않고 모든 고정 panel을 `NOT_RUN`으로 표시한다.
5. exact 같은 source/reference/support를 사용한 기존 diagnostic continuous metric과
   nullable G0–G4/PASS를 method block 옆에 표시한다.
6. panel/metric/source/projection receipt manifest와 한글 HTML index/report를 만든다.
7. renderer는 `--offered-commit <exact 40-char SHA>`를 필수로 받고, 실행 HEAD의
   ancestor인지와 renderer/config Git blob SHA가 그 commit과 같은지 검증한다.
   기존 정량 evaluator도 source row의 commit에 있는 implementation/config blob과
   config에 고정된 SHA를 대조한다.

## Out of scope

- C1/C2/C3 Roofer, G2, metric 또는 GS training 재실행
- C4/C5 성능 실행
- building instance split 수정
- G3/G4 threshold, official `PASS_usable`, scientific verdict 결정
- R1 15.7GB input, `Images.zip`, `OPF.zip` 재해시
- 기존 packet/Return/receipt/result namespace 수정

## Required output namespace

`artifact://JointBuildGS/phase-payloads/p2/representative_comparison_matrix_sample_v1/P2-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v1/`

Required:

- `qualitative/index.html`와 건물별 `case.html`
- 모든 required panel PNG와 roof projection receipt
- `manifests/panel_manifest_v1.jsonl`
- `manifests/metric_manifest_v1.jsonl`
- `metrics/sample_building_method_metrics_v1.csv`
- `metrics/sample_quantitative_summary_v1.csv`
- `control/finalized_v1.json`
- Git compact report, artifact manifest와 Return Packet

## Stop conditions

- exact 3동 또는 strict reference binding 불일치
- source metrics/reference/execution-unit bytes 또는 SHA 불일치
- raw camera calibration/reference projection 불가
- source output을 새로 계산해야만 panel을 채울 수 있음
- 기존 namespace 수정 또는 output cap 초과
- `.partial` namespace가 이미 존재함. 자동 삭제·재사용·재실행하지 않고
  `PARTIAL_NAMESPACE_PRESENT`로 중단하며, 별도 recovery 검토가 새 namespace 또는
  정확한 대상 정리를 승인해야 한다.

## Done when

- 세 건물 모두 고정 matrix를 가지며 168개 모든 panel의 projection status가
  `PROJECTED`이다. 하나라도 reference가 없거나 투영 수가 맞지 않으면 완료하지 않는다.
- metric row가 exact panel/source/reference/support hash를 가리킨다.
- C1은 `SELF_REFERENCE_DIAGNOSTIC_ONLY`로 격리하고 그림에
  `SELF_REFERENCE_UPPER_BASELINE` watermark를 붙인다. C2/C3은 strict
  independent-reference diagnostic, C4/C5는 `NOT_RUN`으로 격리한다.
- canonical method ID는 `C4_GS_lidar_prior`, `C5_GS_lod1_prior`를 사용한다.
- official G3/G4/PASS와 `scientific_verdict`는 `null`이다.

## Return packet

`docs/handoffs/returns/P2_C2W_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_RETURN_v1.md`
