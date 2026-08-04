# P2 C1/C2/C3 통합 정성 결과판 v4 — closure

## 닫힌 결과

- task: `P2-C1-C2-C3-CONSOLIDATED-RESULTS-v4`
- status: `300-CLOSED_LOCAL_LOD2_SCALED_SECTIONS_AND_BASELINE_MESH`
- result root: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v4`
- PDF: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v4/reports/C1_C2_C3_qualitative_results_v4_lod2_scaled_sections_and_baseline_mesh.pdf`
- PDF SHA-256: `675e20b076fb79791c7a05342f5e844a7fa2703357b7cc289f059dcd2582097f`
- 구성: 대표 3건물 × (`C1/C2 + mesh`, `C3-1 context`, `C3-2 context`, `common PCA section`) = 12쪽
- common PCA section: 3쪽, 60 panel
- `scientific_verdict: null`

## 해석 규칙

1. 높이 비교는 `COMMON_PCA_PRINCIPAL_SECTION` 페이지만 사용한다.
2. 모든 비교 열은 같은 footprint-PCA cut과 같은 건물별 LoD2-derived Z축을 사용한다.
3. C1/C2 surface mesh는 같은 Roofer CityJSON output의 display triangulation이며 별도 reconstruction이 아니다.
4. C1/C2에는 Poisson·TSDF branch가 없으므로 해당 셀은 `N/A`다.
5. 기존 C3 context 페이지의 inherited section은 높이 직접 비교용이 아니다.
6. GS/Roofer/Poisson/TSDF/G2/metric 재실행은 0회이며 C4/C5는 접근하지 않았다.
