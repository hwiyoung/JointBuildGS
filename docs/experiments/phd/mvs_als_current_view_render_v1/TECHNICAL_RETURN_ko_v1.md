# MVS–Existing ALS exact current-view 렌더 파일럿 기술 반환 v1

## 결론

exact-937의 current camera 세 개에서 frozen MVS와 Existing ALS를 source별 독립
z-buffer로 실제 렌더했다. raw exact-point projection, 2 px connected display proxy,
current RGB/edge, 공통 depth residual, frozen 5관계 및 surface-patch overlay를
생성했다.

실행 결과는 두 가지를 동시에 보여준다.

1. **current-view 비교는 실행 가능하다.** TOP과 서로 다른 두 oblique view에서
   source별 silhouette/depth/edge와 raw/patch 관계를 현재 RGB 위에 재현했다.
2. **보기 좋은 연결화가 곧 판정 가능한 표면은 아니다.** 2 px display proxy는
   raw mask의 연결요소를 크게 줄였지만 공통 coverage와 depth residual도 바꿨다.
   따라서 proxy나 patch core를 source truth·temporal validity·최종 렌더 geometry로
   사용할 수 없다.

상태는 `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`다. source 선택·가중치·융합·GS
최적화는 수행하지 않았고 `scientific_verdict: null`이다.

## 동결 파일럿

- scene-local half-open prism: `X[-23,7), Y[-21,9), Z[-44.272,-25.962)` m
- frozen source tile: `x003_y004`
- prism 안 exact source point: MVS 139,033, Existing ALS 20,189
- prism 안 relation core: 610
- current image/camera:
  - TOP: COLMAP 90, `DJI_20241217084551_0099_D.JPG`
  - OBLIQUE_A: COLMAP 840, `DJI_20241217102957_0024_D.JPG`
  - OBLIQUE_B: COLMAP 659, `DJI_20241217101453_0037_D.JPG`

카메라와 crop은 relation/source geometry로 먼저 고정했다. current UAS LiDAR,
LoD2 Ground/Roof/Z, stable building ID, 평가 roster는 읽지 않았다.

## raw와 connected display proxy 비교

raw는 exact source point를 각 camera의 nearest camera-Z에 넣은 결과다. proxy는 raw
유효 픽셀을 source별로 독립적인 반경 2 px disk로 확장해 min-depth를 취한
**전시 전용 표현**이다. mesh, 새 표면관측, Gaussian reconstruction이 아니다.

| view | raw MVS/ALS component | proxy MVS/ALS component | raw common coverage | proxy common coverage | raw/proxy abs depth median (m) |
|---|---:|---:|---:|---:|---:|
| TOP | 33 / 634 | 4 / 3 | 10.11% | 24.47% | 1.918 / 0.949 |
| OBLIQUE_A | 47 / 310 | 3 / 2 | 8.29% | 17.83% | 1.231 / 0.757 |
| OBLIQUE_B | 20 / 20 | 4 / 3 | 13.56% | 17.72% | 1.077 / 1.119 |

proxy는 연결성을 개선하지만 support domain을 넓히면서 잔차 통계까지 바꾼다.
특히 이 depth residual은 실제 변화, 정합오차, sampling 차이, MVS 오류를 모두
포함할 수 있는 **source 간 불일치**이지 어느 source의 정확도 오차가 아니다.

current RGB와 geometry edge를 겹친 패널에서는 두 source 모두 일부 관측 경계를
설명하지만, MVS는 더 조밀하고 ALS raw projection은 view에 따라 파편화가 크다.
raw geometry-edge의 RGB-edge 거리 중앙값도 TOP에서는 ALS 2.865 px / MVS
4.234 px였지만, OBLIQUE_A에서는 MVS 0.955 px / ALS 1.369 px, OBLIQUE_B에서는
MVS 1.369 px / ALS 1.910 px로 방향이 바뀌었다. 게다가 source별 edge pixel 수가
크게 달라 point sampling 경계가 실제 물체 경계처럼 세어질 수 있다.
이 정성 결과만으로 MVS 또는 ALS winner를 만들지 않았다. source 판정에는
가시성/free-space, registration uncertainty, multi-view persistence, source quality,
temporal validity를 별도 cue로 추가하고 calibration해야 한다.

## relation/patch를 current image에 투영한 결과

각 relation core는 `core_source`에 해당하는 **독립 raw source z-buffer**와 camera-Z
차이가 ±0.75 m일 때만 보이는 것으로 표시했다. 이 gate는 overlay의 occlusion
진단일 뿐 source decision threshold가 아니다.

| view | 가시 relation core |
|---|---:|
| TOP | 506 |
| OBLIQUE_A | 401 |
| OBLIQUE_B | 368 |

각 view에 current RGB, raw 5관계, patch-aggregated 관계, patch UID, source family,
patch status의 6패널을 만들었다. patch overlay를 추가하기 전후의 source z-buffer,
`view_metrics.csv`, source comparison panel SHA-256은 동일하다. 즉 patch는 이
실행에서 display-only였고 source 렌더나 수치에 되먹임되지 않았다.

overlay는 raw core가 영상의 실제 roof/ground/object boundary 주변에 어떻게
배치되는지와, patch 뒤 candidate-safe fail-closed가 어디서 발생하는지를 보여준다.
그러나 core spacing은 2 m이고 patch는 연결·집계 단위이므로 점 사이를 면으로
채우지 않는다. 최종 GS 입력에는 patch membership을 원 source point/mesh/Gaussian에
전파하는 별도 resolver가 필요하다.

## 렌더링 비교에서 반드시 고정할 항목

다음 단계의 공정 비교에서는 최소한 아래를 고정·분리해야 한다.

- 같은 camera, crop, resolution, occlusion 및 visibility 정의
- exact point-splat raw와 connected display proxy
- source-native mesh first-hit 또는 surface proxy와 point-splat의 표현 편향
- GS expected/median depth와 point/mesh depth의 정의 차이
- source별 depth, normal, silhouette, boundary, image-edge proximity
- 학습 view와 held-out current view
- benign 영역 보존, stale-prior contamination, abstention risk–coverage

raw point projection은 계보 감사 기준이고, display proxy는 정성 확인용이다.
source decision 학습이나 weight 계산에 어느 하나를 쓰려면 representation별
calibration과 강한 sequential comparator를 먼저 고정해야 한다.

## 검증과 산출물

Docker unit test 9개와 21개 산출물 hash validator를 통과했다. 검증 항목은 exact
입력·세 camera, source 독립 raw/proxy, own-source raw-Z overlay visibility,
patch overlay의 source metric 비간섭, source decision/융합/GS 미수행, 금지 입력
비접근, `scientific_verdict: null`이다.

Canonical external root:

```text
$JBGS_ARTIFACT_ROOT/phase-payloads/phd/mvs_als_current_view_render_v1/
  PHD-MVS-ALS-CURRENT-VIEW-RENDER-PILOT-v1/
```

주요 파일은 view별 `comparison_panel.png`, `edge_comparison_panel.png`,
`relation_patch_projection_panel.png`, `source_independent_projections.npz`,
`metrics.json`과 전체 `view_metrics.csv`, `technical_return.json`,
`validation_receipt.json`이다. 정확한 SHA-256은
`artifacts/manifests/phd/mvs_als_current_view_render_v1/technical_result_manifest_v1.json`에
고정했다.
