# P2 C1/C2/C3 U_target=199 기술 Return v1

- task_id: `P2-C1-C2-C3-UTARGET199-v1`
- writer: Experiment Host
- return direction: Experiment Host to Work Host
- return state: `TECHNICAL_COMPLETE`
- scientific_verdict: `null`

## 반환 요약

C1/C2 3동 비교판과 정량 6행, C3-1/C3-2 seed-0 30k checkpoint, C3 199동
native point cloud/surfel mesh, 398 building-condition rows, actual gsplat 8 panels,
199 case sheets와 qualitative index를 반환한다.

C3 학습은 정상 완료됐지만 건물별 Stage-3 read-out은 C3-1 16동, C3-2 18동만
component와 연결됐고 building G0는 두 조건 모두 0동이다. 따라서 official
G3/G4/PASS와 scientific verdict는 판단하지 않고 `null`로 유지한다.

## 실행 회계

- C1/C2 Roofer/G2/GS/metric 재실행: 각각 0
- C3 GS 학습: 2회, 각 30,000 iteration, restart/OOM 0
- C3 unique Roofer operation: 25회
- C3 result row: 398행; recovery metric recomputation: 0
- C4/C5 access: 0

## 반환 위치

- manifest:
  `artifacts/manifests/p2/c1_c2_c3_utarget199_v1/technical_result_manifest_v1.json`
- report:
  `docs/experiments/p2/c1_c2_c3_utarget199_v1/TECHNICAL_RETURN_REPORT_v1.md`
- C1/C2 artifact:
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v6/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v6`
- C3 paired checkpoint artifact:
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_c3_utarget199_v1/P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1`
- C3 complete postprocess artifact:
  `artifact://JointBuildGS/phase-payloads/p2/c3_utarget199_postprocess_render_recovery_v1/P2-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1`

이 Return은 기술적 write turn만 Work Host에 되돌린다. 과학적 승인, C4/C5 실행 권한,
공식 PASS 또는 일반화 결론을 포함하지 않는다.
