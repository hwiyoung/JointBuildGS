# C3 Poisson/TSDF 속성판과 GT-footprint oracle hybrid 기술 보고서 v1

## 결과

봉인된 C3 Poisson/TSDF mesh를 다시 복원하지 않고 각 mesh를 다음 네 속성으로 별도
표시했다.

- `RGB`: 원본 PLY vertex RGB
- `SEMANTIC`: roof-only source는 모두 roof, hybrid는 roof/wall/ground source class
- `VIRTUAL_DEPTH`: 동일 네 고정 시점에서 계산한 표시용 view-depth; checkpoint camera
  depth가 아님
- `ABS_NORMAL`: 원본 또는 hybrid mesh의 절대축 vertex normal

건물별 판은 C3-1 네 시점과 C3-2 동일 네 시점을 좌우로 배치한 `16행 × 8열`이다.
행 1–8은 roof-only Poisson/TSDF, 행 9–16은 같은 roof mesh에 GT GroundSurface XY wall과
ground cap을 추가한 oracle hybrid다. 3건물에서 384 panel과 12 hybrid PLY를 생성했다.

## 색상과 geometry 계보

기존 C3 v6 10행 금색과 11행 보라색은 method 구분용 고정색이었다. 이번 RGB 행은 PLY의
실제 vertex RGB를 사용하고 normal도 PLY 속성을 사용한다. 원본 mesh semantic은 roof-only
selection이므로 모든 vertex가 roof로 표시된다. 별도 per-vertex semantic probability를
꾸며내지 않았다.

Hybrid wall은 footprint boundary에서 가까운 roof vertex 높이로 eave top line을 만들고
current local terrain까지 내린 표시용 면이다. wall의 RGB는 가까운 roof-boundary RGB를
아래로 어둡게 전파한 색으로, 관측된 wall texture가 아니다. 따라서 hybrid는 건물처럼
읽히지만 honest Stage-3 output 또는 metric 입력이 아니다. 각 hybrid sidecar는
`GT_FOOTPRINT_ORACLE_HYBRID_VISUALIZATION_NOT_HONEST_STAGE3`, `lod2_z_used: false`,
`official_metric_input: false`를 기록한다.

## 원본 해상도 시각 검토

- `4906975`: Poisson은 연속적으로 메운 roof surface, TSDF는 관측 depth에 가까운 더 얇고
  조각난 surface로 보인다. footprint wall을 붙이면 양쪽 모두 건물 외형이 읽히지만 roof
  품질 차이는 그대로 남는다.
- `108580336`: Poisson hybrid는 외형이 생기지만 넓은 Poisson completion이 footprint와
  어긋난 부분이 보인다. TSDF hybrid는 wall만으로 outline이 명확해질 뿐 roof evidence가
  거의 없는 영역은 채우지 않는다. hybrid가 roof coverage를 개선한 것으로 해석하면 안 된다.
- `4907177`: Poisson은 약한 evidence에서 넓은 면을 메운 모습이고 TSDF는 매우 제한된
  관측 조각만 남긴다. wall 보강은 폐합형 외형을 제공하지만 2024 roof partition의 정확한
  복원을 증명하지 않는다.

## 4907177에서 실제로 잘못된 것

이 건물은 철거되거나 current point가 없는 사례가 아니다.

- 2024 영상에서 지붕이 보인다.
- 2022 LoD2 GroundSurface footprint 내부에 C1 current UAS LiDAR 16,892점과 C2 exact
  common-MVS 1,162점이 있다.
- footprint 내부 Z median은 C1 581.399m, C2 581.613m이며 +45.7m display datum의 LoD2
  roof maximum 580.88m와 각각 0.519m, 0.733m 차이다.

오류는 per-building point 준비의 local-ground 추정이다. 4907177은 더 큰 연속 지붕의
일부라 footprint 바깥 ground ring에도 같은 지붕이 포함된다. cell-minima median estimator가
약 581m의 연속 지붕 높이를 local ground로 채택했고, 이어지는 `ground + 2.5m` class-6
필터가 실제 지붕을 제거했다. 그래서 C1은 class 6이 25점만 남고 C2는 0점이 됐다.

따라서 기존 상태는 `current evidence absence`나 Roofer 실패가 아니라
`GROUND_REFERENCE_FAILURE_BEFORE_ROOFER`다. 다음 재실행은 인접 연속 지붕을 ground 후보에서
제외하거나 더 넓은 실제 terrain support에 ground를 고정한 뒤, 4907177의 C1/C2 Stage-3
eligibility와 Roofer만 다시 확인하는 것이다. C3는 먼저 Stage-3 roof extraction/coverage를
재검증하며 GS 재학습을 바로 수행하지 않는다.

## 실행 계수와 해석 경계

- GS training: 0
- checkpoint render extraction: 0
- Poisson reconstruction: 0
- TSDF reconstruction: 0
- display-only hybrid wall assembly: 12
- Roofer/G2/metric/C4/C5: 모두 0

이 작업은 속성 표시와 oracle hybrid 조립이다. `official_G3_G4_PASS_usable: null`,
`scientific_verdict: null`이며 C3-1/C3-2 우열 또는 usable LoD2 판정을 하지 않는다.

외부 artifact resolver는
[`artifacts/manifests/p2_c3_mesh_attribute_hybrid_v1.json`](../../../../artifacts/manifests/p2_c3_mesh_attribute_hybrid_v1.json)이다.
