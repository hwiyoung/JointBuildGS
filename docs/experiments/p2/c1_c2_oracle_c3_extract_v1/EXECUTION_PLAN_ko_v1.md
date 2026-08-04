# C1/C2 건물별 oracle 진단 재실행 및 C3 결과 재추출 계획 v1

## 목적과 해석 경계

이 작업은 잘못 연결된 공용 C1/C2 component 출력과 C3의 unfiltered Gaussian quad
시각화를 교정한다. C1/C2는 세 대표 건물을 각각 독립된 Roofer operation으로 다시
실행한다. 단, LoD2 `GroundSurface` XY를 Roofer footprint로 쓰므로 이 결과는 정본
no-external-roofprint Stage 3가 아니라 **GT-footprint oracle diagnostic**이다. 공식
honest-arm 성능, G3/G4/PASS, 과학 판정으로 승격하지 않는다.

C3는 학습을 다시 하지 않는다. 성공한 exact checkpoint 두 개를 열어 모든 Gaussian
파라미터를 보존한 3D PLY, 별도의 명시적 display proxy, rendered median-depth 다중시점
융합 point cloud를 만든다. 최종 mesh는 fused point 전체가 아니라 semantic class
`1=roof`이면서 GT GroundSurface XY 1 m buffer 안에 있는 점만 사용해 Poisson surface로
만든다. 선택점이 100점 미만이면 mesh를 생성하지 않고 증거 부족으로 기록한다. 기존의 Gaussian당
4개 꼭짓점·2개 삼각형 quad 파일은 surface mesh로 재사용하지 않는다.

추가 비교 read-out은 각 C3 condition의 fused roof-semantic point를 class 6, exact common-image
C2 MVS terrain을 공유 class 2로 사용한다. 동일 GT GroundSurface XY footprint를 적용한
oracle diagnostic이며 official honest Stage 3가 아니다. RoofSurface XYZ는 입력하지 않는다.

## 고정 실행 단위

- 건물: `DEBY_LOD2_4907177`, `DEBY_LOD2_4906975`, `DEBY_LOD2_108580336`
- C1: 2024 current UAS nadir LAZ 원점군을 1회 순차 읽기
- C2: Gate-S0 exact common-base `dim_dense.ply` 원점군을 1회 순차 읽기
- footprint: 동일 건물의 LoD2 `GroundSurface` exterior/interior XY만 사용
- C1/C2 Roofer: `4906975`, `108580336`의 건물 2 × 방법 2 = 정확히 4회
- `4907177`: C1 class-6 25점, C2 class-6 0점이므로 2개 method 모두
  `PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE`; Roofer를 실행하지 않음
- C3 checkpoint: `C3_1_SEM seed0`, `C3_2_SEM_DEPTH seed0`
- C3 학습: 0회
- C3 oracle Roofer: `4906975`, `108580336` × 두 condition = 정확히 4회
- `4907177` C3-1/C3-2: class-6 기준 미달로 2개 pre-Roofer insufficient-evidence record
- G2/metric/C4/C5: 모두 0회/0 access

## 이전 결과와의 단절

이 작업은 다음 항목을 입력 또는 결과로 재사용하지 않는다.

- 1 m C1/C2 class-2/6 grid component
- 세 건물이 공유했던 C1/C2 operation output
- `COMPLETED_REUSED_EXACT` Roofer output
- Gaussian마다 무조건 4 corner/2 triangle을 만든 `native_gaussian_surfel_mesh_v1.ply`
- 이전 qualitative case sheet 또는 panel PNG

재사용하는 것은 원 데이터, exact camera base, C3 exact checkpoint뿐이며 각각 config의
크기와 SHA-256으로 고정한다.

## C1/C2 point cloud 준비

1. `GroundSurface` XY로 polygon을 만들고 8 m 문맥을 포함해 원점군을 자른다.
2. polygon 외부 ring의 1 m cell 저점들로 local ground를 구한다.
3. polygon 내부에서 local ground + 2.5 m 이상인 관측점을 class 6으로 둔다.
4. 외부 ground ring에서 local ground + 0.75 m 이하인 관측점을 class 2로 둔다.
5. plane-growing에 충분한 국소 구조를 유지하면서 중복 밀도만 제한하도록 0.2 m
   deterministic 3D voxel당 1점을 보존한다.
6. class-6가 100점 이상인 입력 LAS와 footprint GeoJSON을 먼저 봉인한 후 Roofer를
   한 번씩 실행한다. 미만이면 Roofer 실패가 아닌 pre-Roofer reference alignment
   failure로 그대로 보존한다.

RoofSurface XYZ, roof type, LoD2 높이와 final model은 이 분류와 Roofer 입력에 쓰지 않는다.

## C3 결과 추출

exact checkpoint의 모든 primitive에 대해 center, quaternion, scale, opacity, SH DC color,
semantic logits/class를 full PLY에 기록한다. display proxy의 opacity/scale/AOI 필터는
시각화 역할이며 full PLY를 대체하지 않는다.

surface는 대표 건물 주소로 선택한 최대 24개 current view에서 median depth, alpha,
rendered normal, semantic을 함께 꺼내 0.15 m voxel로 융합한다. 서로 다른 view 2개 이상이
관측한 voxel만 유지한다. 그중 roof class 1만 GroundSurface XY 1 m buffer로 선택한 뒤
Poisson reconstruction을 적용한다. footprint는 이 bounded extraction의 주소와 mesh
공간 선택에만 쓰며 학습, loss, Gaussian 이동에 사용하지 않는다.

## 시각 판 구성

C1/C2 case sheet는 4열 고정시점과 다음 6행으로 구성한다.

1. current RGB + 2022 LoD2 roofline
2. C1 raw-derived point cloud + GT GroundSurface XY footprint
3. C1 Roofer output
4. C2 exact common-MVS point cloud + 동일 footprint
5. C2 Roofer output
6. LoD2 epoch context only

roofline은 1행과 별도 6행에서만 보인다. C1/C2 입력·출력 행에는 footprint만 보인다.
`4907177`은 2022/2024 epoch 또는 ID alignment 문제 가능성을 `REFERENCE/ID ALIGNMENT
REVIEW`로 명시하고 C1/C2 실패로 부르지 않는다.

C3는 건물별 12행×4열 한 장으로 구성한다. 첫 행은 current RGB+2022 roofline, 다음 다섯
행은 C3-1 Gaussian RGB/semantic, fused points, roof mesh, oracle Roofer, 다음 다섯 행은
C3-2의 동일 결과, 마지막 행은 2022 LoD2 epoch context다. 이 배치로 condition 사이와
LoD2 맥락을 별도 파일 왕복 없이 비교한다.

## 완료 조건

- C1/C2 building/method record 6개가 서로 다른 ID와 입력 hash를 가지며, 그중 유효한
  Roofer operation 4개가 서로 다른 output hash를 가짐
- `4907177`의 2개 record는 output을 꾸며내지 않고 pre-Roofer alignment failure임
- 각 입력의 class 6과 class 2가 모두 비어 있지 않음
- Roofer invocation count 정확히 4, pre-Roofer alignment failure 2,
  GS training/G2/metric/C4/C5 count 0
- C3 full Gaussian PLY 두 개와 condition/building별 fused point cloud가 존재하고, roof 선택점
  100점 이상인 5개 조합에는 roof-only Poisson mesh가 존재함
- `4907177/C3-2`는 선택 roof point 1점을 기록하고 명시적 insufficient-evidence panel을 표시함
- C3 exact checkpoint hash와 모든 추출물 lineage가 연결됨
- 대표 C1/C2 3장과 C3 condition/building 결과를 original resolution으로 직접 검토
- C3 oracle Roofer invocation 4, insufficient-evidence pre-failure 2, C3 primary sheet 3장/144 panels
- 모든 기술 문서와 receipt의 `scientific_verdict`는 `null`
