# C4/C5 12행 확장 및 textured hybrid mesh 제작 계획 v1

## 문서 상태와 경계

- 상태: `PLANNING RECORD — NOT C4/C5 EXECUTION AUTHORITY`
- 목적: C3 12행 complete-lineage 판의 해석 구조를 C4/C5에 그대로 확장하고,
  Poisson/TSDF의 실제 RGB·normal 속성과 폐합형 건물 시각화를 혼동 없이 제시한다.
- 이 문서는 C4/C5 학습, surface extraction, Roofer, G2 또는 metric 실행을 활성화하지
  않는다. 별도 실행 결정과 exact input/checkpoint/config 봉인이 필요하다.
- 모든 기술 Return은 `official_G3_G4_PASS_usable: null`, `scientific_verdict: null`을
  유지한다.

## 1. C4/C5 비교판의 고정 구성

C4와 C5를 한 건물당 한 장에 좌우로 둔다. C4의 4시점을 왼쪽, C5의 동일 4시점을
오른쪽에 배치하여 건물당 `12행 × 8열 = 96 visible cells`로 만든다.

| 행 | 표시 | 계보와 역할 |
|---:|---|---|
| 1 | 2024 RGB + 2022 roofline | 공통 영상·시기·정합 context |
| 2 | GS 3D Gaussian RGB | exact checkpoint의 oriented Gaussian 표현 |
| 3 | GS 3D Gaussian semantic | roof/wall/terrain 전체 semantic context |
| 4 | GS 3D Gaussian world-Z | 높이 proxy; camera depth가 아님 |
| 5 | GS 3D Gaussian normal | Gaussian plane normal |
| 6 | rendered-depth direct-fusion point cloud | RGB·semantic·normal을 가진 관측 surface points |
| 7 | 실제 Roofer input LAS | class 6 roof evidence + class 2 terrain support + 입력 footprint 계보 |
| 8 | Roofer output | Stage-3 결과; honest와 oracle을 명시적으로 구분 |
| 9 | multi-view roof-only consensus | Poisson/TSDF의 동일 입력 evidence |
| 10 | Poisson roof mesh | 같은 roof evidence의 oriented-point completion |
| 11 | TSDF roof mesh | 같은 depth/camera ray 기반 surface |
| 12 | 2022 LoD2 | epoch/reference context only |

시점은 C3와 동일하게 `TOP / OBLIQUE_1 / OBLIQUE_2 / PRINCIPAL_SECTION`을 사용한다.
동일 건물에서는 C3/C4/C5의 camera IDs, crop, 축 범위, footprint 표시, display datum을
같게 고정한다. C4와 C5 사이에서 보기 좋은 카메라를 별도로 고르지 않는다.

## 2. C4/C5 조건 차이의 봉인

- C4는 C3와 동일한 `B_current`에 `ALS_EXISTING` 하나만 추가한다.
- C5는 같은 `B_current`에 independent existing LoD1 prior 하나만 추가한다.
- C4에 LoD1을, C5에 ALS를 넣지 않으며 두 prior를 결합한 arm을 만들지 않는다.
- 공통 image-derived seed, training schedule, semantic/depth loss, densification, stopping,
  extraction threshold와 Stage-3 adapter는 prior 항목을 제외하고 같아야 한다.
- primary checkpoint/seed는 결과를 본 뒤 고르지 않는다. 실행 packet에서 미리 고정하고,
  복수 seed가 있으면 seed별 판을 별도로 생성한 뒤 preregistered aggregation만 허용한다.
- 각 panel은 checkpoint, camera, rendered depth, semantic, mesh, Roofer input/output의
  bytes와 SHA-256 계보를 가진다.

## 3. 현재 C3 Poisson/TSDF 색상의 의미

현재 C3 12행 v6의 10행 금색과 11행 보라색은 geometry source에서 계산한 semantic,
depth 또는 normal 색이 아니다. renderer가 방법을 구분하기 위해 각각 고정한
`#d5a021`과 `#7c3aed` 표시색이다.

원본 Poisson/TSDF PLY에는 `x/y/z`, `nx/ny/nz`, `red/green/blue` vertex property가
존재한다. TSDF는 RGB8 color volume으로 적분했고 Poisson도 RGB를 가진 oriented roof
consensus point에서 생성했다. 그러나 현재 판의 mesh renderer는 이 vertex RGB와 normal을
사용하지 않고 전체 mesh를 단색으로 그린다.

- RGB: 원본 PLY에 존재하지만 현재 10·11행에서 표시하지 않음
- normal: 원본 PLY에 존재하지만 현재 10·11행에서 표시하지 않음
- depth: mesh vertex 위치를 만든 source evidence이지 별도 vertex 색 속성이 아님
- semantic: roof class로 선택한 뒤 만든 mesh이므로 mesh 전체가 roof-only라는 선택 의미만
  남고, 현재 PLY에는 per-vertex semantic class/confidence field가 없음

## 4. C4/C5 mesh의 표시 개선

기본 12행의 행 수는 유지한다. 10·11행은 단색 대신 vertex RGB를 기본 surface color로
사용하고, Poisson/TSDF 구분은 제목·테두리·범례로 한다. 별도 HTML/원본 panel variant에는
다음 네 display modes를 제공한다.

1. `RGB`: PLY vertex RGB 또는 current RGB multi-view texture
2. `NORMAL`: mesh vertex normal을 절대축 RGB로 인코딩
3. `WORLD_Z`: 동일 건물 공통 범위의 높이 색상
4. `SUPPORT`: consensus distinct-view count 또는 nearest observed-evidence distance

semantic은 모든 mesh vertex를 임의로 roof 색으로 칠하는 대신 `roof-only selection`을
범례와 manifest에 기록한다. 실제 per-vertex semantic probability를 보이려면 consensus
point에서 mesh vertex로 class probability와 support를 명시적으로 전파하고 그 알고리즘과
hash를 별도 artifact로 봉인한다.

## 5. GT footprint로 옆면을 보강한 textured building

기술적으로 가능하다. 다음과 같이 `roof surface + footprint wall skirt`의 폐합형 hybrid
mesh를 만들 수 있다.

1. 관측 기반 Poisson 또는 TSDF roof mesh를 유지한다.
2. footprint boundary에서 roof mesh/roof plane과 교차하는 eave top line을 구한다.
3. class-2 terrain으로 boundary별 bottom Z를 정한다.
4. top line과 bottom line 사이를 삼각형 wall strip으로 연결한다.
5. current RGB 카메라 중 가시성, 입사각, 거리, 폐색과 exposure를 고려해 roof와 wall의
   texture atlas를 만든다.
6. roof와 wall의 source를 face attribute로 구분하여 `OBSERVED_ROOF`,
   `EXTRUDED_WALL`, `UNOBSERVED/LOW_SUPPORT`를 보존한다.

이렇게 하면 Roofer와 비슷한 폐합형 건물 형태에 current RGB texture를 입힌 결과를 만들
수 있다. 다만 벽면은 관측된 Poisson/TSDF surface가 아니라 footprint와 ground/eave에서
외삽한 면이므로 지붕 관측 품질이 좋아진 것은 아니다.

### 5.1 honest 결과와 oracle 결과의 분리

- evaluation-only GT footprint를 사용한 폐합 mesh는
  `GT-FOOTPRINT ORACLE HYBRID VISUALIZATION`으로만 기록한다.
- 이것을 C4/C5의 honest Stage-3 출력, mesh accuracy 결과 또는 prior 효과 증거로 사용하지
  않는다.
- honest 폐합 mesh가 필요하면 GS semantic/depth에서 building boundary를 추정하거나,
  no-external-roofprint Roofer read-out이 예측한 boundary를 사용해야 한다.
- C5가 LoD1 prior를 학습에 사용하더라도 평가용 GT footprint를 후처리에 직접 쓰면 별도의
  oracle 개입이다. prior와 evaluation reference의 계보를 합치지 않는다.

따라서 primary 12행에는 관측 기반 roof-only Poisson/TSDF와 정본 Stage-3 Roofer를 유지하고,
textured closed mesh는 case HTML의 별도 `HYBRID` 탭 또는 부록 행으로 둔다.

## 6. 권장 산출물

각 C4/C5 condition/building/checkpoint 조합에 대해 다음을 보존한다.

- full Gaussian PLY와 display-filter receipt
- Gaussian RGB/semantic/world-Z/normal 4시점
- rendered-depth direct-fusion PLY: RGB, normal, semantic, support 포함
- actual Roofer input LAS와 footprint provenance
- Roofer output CityJSONSeq 및 panel 4시점
- roof-only multi-view consensus PLY: RGB, normal, view count, semantic probability
- Poisson 및 TSDF 원본 PLY
- Poisson/TSDF `RGB / NORMAL / WORLD_Z / SUPPORT` panel variants
- optional oracle hybrid PLY/OBJ 또는 glTF: observed/extruded face labels와 texture atlas 포함
- case sheet, case HTML, artifact manifest, technical Return, 200-verified, 300-closed

## 7. 검증 조건

- C3/C4/C5는 같은 건물·카메라·시점·축·datum으로 비교됨
- C4와 C5의 유일한 학습 조건 차이는 각각 ALS prior와 LoD1 prior임
- row 9가 row 10/11의 exact 같은 입력임을 hash로 입증함
- row 7/8의 Roofer 계보와 row 9/10/11의 mesh 계보를 연속 pipeline으로 오인하지 않게 표시함
- mesh RGB가 고정 method color가 아니라 PLY/texture source와 연결됨
- normal/world-Z/support variant의 색상 범위와 정의가 condition 간 동일함
- observed roof face와 footprint-extruded wall face가 face attribute와 범례에서 분리됨
- oracle hybrid는 공식 metric과 Roofer 입력으로 재투입되지 않음
- C4/C5 실행 전 별도 승인·packet·resource plan이 존재함
- `official_G3_G4_PASS_usable`와 `scientific_verdict`는 null임

## 결정 요약

C4/C5는 C3 v6와 동일한 12행 complete-lineage 형식으로 제작한다. Poisson/TSDF 행은
실제 RGB를 기본으로 개선하고 normal/world-Z/support는 별도 panel variant로 제공한다.
GT footprint를 이용한 textured wall 보강은 가능하지만, 관측 기반 roof mesh와 외삽 wall을
구분한 oracle hybrid 시각화로만 제공한다. honest C4/C5 결과 및 과학 판정과 합치지 않는다.
