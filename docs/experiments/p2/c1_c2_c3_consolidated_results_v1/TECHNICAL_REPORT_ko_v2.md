# C1/C2/C3 통합 정성 결과판 v2

## 결과

대표 3건물의 봉인 결과를 한 PDF로 다시 조합했다. 건물별 순서는 `C1/C2 기존판 → C3-1 → C3-2`이며 총 9쪽이다. C3-1과 C3-2를 각각 4열로 분리해 기존 8열 판보다 글자와 시점을 확대했다.

단일 PDF:

`phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v2/reports/C1_C2_C3_qualitative_results_v2_filled_c1_roofer.pdf`

## C3 12행

1. 2024 RGB + 2022 roofline projection
2. GS 3D Gaussian RGB
3. GS 3D Gaussian world-Z depth proxy
4. GS 3D Gaussian normal
5. GS 3D Gaussian semantic
6. 24-view roof-only consensus fused points
7. 실제 C3 Roofer input LAS
8. GS Roofer output
9. C1 Roofer output — filled CityJSON roof-plane surfaces
10. textured Poisson roof mesh
11. textured TSDF roof mesh
12. 2022 LoD2 reference

3행은 camera-depth raster가 아니라 Gaussian 중심의 world-Z 높이 표현이다. 6행은 Poisson/TSDF 진단 입력이고, 7행의 실제 Roofer LAS와 동일하지 않다. 9행은 C1 LiDAR 원시 입력이 아니라 봉인된 C1 Roofer CityJSONSeq 출력이다.

## C1 Roofer 표시 교정

초기 통합 v1의 9행은 실제 C1 Roofer output을 사용했지만 renderer가 polygon 경계선 위주로 표시해 plane의 합으로 읽히지 않았다. v2는 동일 CityJSONSeq의 `RoofSurface` polygon을 plane별 색으로 채우고 `WallSurface`는 회색 반투명으로 낮췄다. orange dashed line은 GT footprint context다.

CityJSON의 roof-plane 수는 다음과 같다.

- `DEBY_LOD2_4907177`: 2
- `DEBY_LOD2_4906975`: 13
- `DEBY_LOD2_108580336`: 29

따라서 4907177의 낮은 큰 면과 높고 좁은 면은 renderer 착시가 아니라 봉인된 Roofer 출력 형상 자체다.

## 검증

- case: 3
- PDF page: 9
- C1/C2 inherited page: 3
- corrected C3 page: 6
- filled C1 Roofer panel: 12
- 대표 3건물의 filled-plane panel과 C3 page를 original resolution으로 직접 검토
- artifact `200-verified` 및 `300-closed` 완료

## 실행 및 해석 경계

GS 학습, checkpoint extraction, Poisson, TSDF, Roofer, G2, metric 재계산, C4/C5 access는 모두 0회다. 이번 작업은 봉인된 결과의 표시 조합과 PDF 작성만 수행했다.

`scientific_verdict: null`은 C1/C2/C3의 과학적 우열, 모집단 일반화, 공식 G3/G4/`PASS_usable` 판정을 하지 않았다는 뜻이다.
