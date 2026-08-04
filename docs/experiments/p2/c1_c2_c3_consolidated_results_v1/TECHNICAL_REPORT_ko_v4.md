# C1/C2/C3 통합 정성 결과판 v4

## 변경 목적

v3는 principal-section 절단선의 계보 차이를 표시했지만, 행마다 Z축 범위가 달라 높이 형상을 직접 비교하기 어려웠다. 또한 C1/C2 Roofer output은 plane별 채움면으로는 확인할 수 있었지만 C3 Poisson·TSDF mesh와 동일한 surface-mesh 관점의 표시가 별도로 없었다.

## LoD2 기준 공통 principal section

v4는 건물별 비교 전용 `COMMON_PCA_PRINCIPAL_SECTION` 페이지를 추가했다.

- 절단면: footprint PCA principal axis
- 관측 방향: PCA cross axis
- Z 기준: 2022 LoD2의 모든 semantic surface에 `+45.7 m` display datum 적용
- Z 범위: LoD2 최소·최대에 상하 `2 m` padding
- 열: C1 LiDAR, C2 MVS, C3-1 semantic, C3-2 semantic+depth
- 행: input/roof evidence, Roofer output surface mesh, Poisson, TSDF, LoD2 reference

고정 범위는 다음과 같다.

- `DEBY_LOD2_4907177`: `557.97–582.88 m`
- `DEBY_LOD2_4906975`: `557.48–578.84 m`
- `DEBY_LOD2_108580336`: `556.414–595.796 m`

기존 C3 context 페이지의 inherited principal column은 문맥 확인용으로 보존했다. 높이 직접 비교에는 공통 PCA 페이지를 사용해야 한다.

## C1/C2 output mesh의 의미

C1/C2 페이지에는 Roofer output을 두 방식으로 표시했다.

1. plane model: RoofSurface·WallSurface 경계와 plane 구성을 표시
2. surface mesh: 같은 봉인 CityJSON surface를 표시 목적으로 삼각분할하여 채움면으로 표시

두 행은 서로 다른 재구성 결과가 아니다. surface mesh는 동일 Roofer output의 표시 변환이며 새로운 meshing, plane growing 또는 Roofer 실행이 아니다. C1/C2에는 Poisson·TSDF branch가 없으므로 공통 비교 페이지에서 해당 칸은 `N/A`로 표시한다.

## 기술 경계

이번 작업은 봉인 geometry의 presentation-only rendering이다. GS 학습, checkpoint extraction, Poisson, TSDF, Roofer, G2, metric 재계산과 C4/C5 access는 모두 0회다. `scientific_verdict`와 official G3/G4/`PASS_usable`은 null이다.
