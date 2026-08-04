# P2 C1/C2/C3 통합 정성 결과판 v3 — 새 세션 handoff

## 닫힌 결과

- task: `P2-C1-C2-C3-CONSOLIDATED-RESULTS-v3`
- status: `300-CLOSED_LOCAL_LATEST_C1_C2_AND_SECTION_LOCATORS`
- result root: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v3`
- PDF: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v3/reports/C1_C2_C3_qualitative_results_v3_lineage_section_locator.pdf`
- PDF SHA-256: `07797e2aecb34a89a218c8c5ba928aa805facbfa40fb76a0847d2d1f1887a057`
- 구성: 대표 3건물 × (`최신 건물별 C1/C2`, `C3-1`, `C3-2`) = 9쪽
- section locator: 9개
- `scientific_verdict: null`

## 핵심 교정

1. 오래된 C1/C2 v6 overlay 판을 최신 건물별 LAS/CityJSON 계보로 교체했다.
2. input은 point cloud, output은 filled Roofer planes로 분리했다.
3. 4907177 C2는 실제 상태대로 `NOT RUN`이다.
4. principal section의 legacy E-frame과 footprint-PCA frame을 TOP locator에서 분리 표시했다.
5. 4906975 C3-2 consensus normal 진단과 Poisson/TSDF 입력 정의를 index/report에 기록했다.

## 다음 세션 요청

```text
먼저 root AGENTS.md를 전부 읽고 준수해.

직전 통합 정성 결과는 아래 v3에서 300-closed까지 완료됐다.
- handoff: docs/handoffs/P2_C1_C2_C3_CONSOLIDATED_RESULTS_v3_CLOSURE.md
- resolver: artifacts/manifests/p2_c1_c2_c3_consolidated_results_v3.json
- PDF: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v3/reports/C1_C2_C3_qualitative_results_v3_lineage_section_locator.pdf

v3는 최신 건물별 C1/C2 input LAS와 Roofer CityJSON output을 분리 표시하고, principal section의 두 inherited frame을 locator로 명시한다. 기존 artifact를 덮어쓰거나 재실행하지 말고 이 결과를 출발점으로 진행해. 모든 principal section을 한 canonical PCA frame으로 통일하려면 봉인 geometry를 presentation-only로 다시 렌더해야 하며, 이것을 GS/Roofer/mesh 재실행으로 세지 않는다. scientific_verdict와 official G3/G4/PASS_usable은 계속 null이다.
```
