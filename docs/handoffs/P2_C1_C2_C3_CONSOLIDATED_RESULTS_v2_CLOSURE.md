# P2 C1/C2/C3 통합 정성 결과판 v2 — 새 세션 handoff

## 닫힌 결과

- task: `P2-C1-C2-C3-CONSOLIDATED-RESULTS-v2`
- status: `300-CLOSED_LOCAL_FILLED_C1_ROOFER_DISPLAY`
- artifact root: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts`
- result root: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v2`
- PDF: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v2/reports/C1_C2_C3_qualitative_results_v2_filled_c1_roofer.pdf`
- PDF SHA-256: `1773578512a2748e79cc6ea9188c960dab539ce60751af3ea0941a1ecafdab7f`
- 구성: 대표 3건물 × (`C1/C2 기존판`, `C3-1 12행`, `C3-2 12행`) = 9쪽
- C1 Roofer 9행: 봉인 CityJSONSeq `RoofSurface` plane을 채움면으로 표시
- `scientific_verdict: null`

## 재실행 경계

이번 결과는 봉인된 source만 다시 조합·렌더했다. 다음 항목은 모두 0회다.

- GS training / checkpoint extraction
- Poisson / TSDF
- Roofer / G2
- metric recomputation
- C4/C5 access

## 다음 세션에 붙여 넣을 요청

```text
먼저 root AGENTS.md를 전부 읽고 준수해.

직전 C1/C2/C3 통합 정성 결과는 아래에서 300-closed까지 완료됐다.
- handoff: docs/handoffs/P2_C1_C2_C3_CONSOLIDATED_RESULTS_v2_CLOSURE.md
- resolver: artifacts/manifests/p2_c1_c2_c3_consolidated_results_v2.json
- PDF: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v2/reports/C1_C2_C3_qualitative_results_v2_filled_c1_roofer.pdf

PDF는 건물별 C1/C2 기존판, C3-1 12행, C3-2 12행의 총 9쪽이다. C3 행은 RGB+roofline, GS 3D RGB, world-Z depth proxy, normal, semantic, roof-only fused points, 실제 Roofer input LAS, GS Roofer, C1 Roofer filled plane surfaces, textured Poisson, textured TSDF, LoD2 reference 순서다.

C1 Roofer row는 점군이나 wireframe이 아니라 봉인 CityJSONSeq의 RoofSurface plane을 채움면으로 표시한다. 4907177의 2개 plane 이상형상은 renderer 오류가 아니라 출력 자체다. 기존 artifact를 덮어쓰거나 재실행하지 말고 이 닫힌 결과를 출발점으로 다음 작업을 진행해. scientific_verdict와 official G3/G4/PASS_usable은 계속 null로 유지해.
```
