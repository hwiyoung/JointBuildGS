# dense baseline qualitative v2 — 사진 오버레이 육안 QA

> 기록일: 2026-07-28
> 대상: `runs/20260728_fusion_w1_dense_baseline_qualitative_v2/panels/*.png` 9개
> 범위: 첫 행의 사진–actual class-6 TIN boundary/point overlay 관찰만
> 과학적 판정: 없음 (`scientific_verdict: null`)

## 자동 계약

- corrected binary COLMAP pose를 추가 변환 없이 사용한다.
- EPSG:25832 orthometric XYZ에 geoid 45.7 m를 한 번만 적용한다.
- corrected camera와 동일한 1400×1013 COLMAP-bound 이미지가 아니면 중단한다.
- 단일 높이 footprint나 reference roof geometry를 첫 행에 투영하지 않는다.
- 실제 DIM/MVS class 6 XYZ의 필터 TIN incidence-one 3D boundary와 class 6 점만 표시한다.
- 위 계약은 좌표·출처 오류를 fail-closed 처리하지만, RGB만으로 독립 확인하는 semantic alignment
  gate나 장면 전체 occlusion depth-test를 대신하지 않는다.

## 전수 관찰

`PASS`는 bulk overlay가 동일 대상 건물/지붕에 놓이고 세 사진에서 대상을 식별할 수 있다는
패널 관찰이다. `REVIEW_NEEDED`는 datum 오류를 뜻하지 않으며, 가림 또는 source class-6/TIN
성분 때문에 패널만으로 대상을 오해할 수 있음을 뜻한다.

| building | 관찰 태그 | 첫 행 관찰 |
|---|---|---|
| DEBY_LOD2_104583447 | PASS | 세 뷰 모두 좁고 긴 회색 지붕 위에 경계와 점이 놓이며 동일 대상을 식별할 수 있다. |
| DEBY_LOD2_4907023 | PASS | 세 뷰의 bulk overlay가 큰 주황색 지붕과 맞는다. 일부 class-6 점은 같은 건물 측면으로 내려간다. |
| DEBY_LOD2_4907207 | PASS | 1·3뷰에서 두 블록/L자 복합 지붕을 확인할 수 있다. 2뷰는 가림과 입면 때문에 복잡하다. |
| DEBY_LOD2_4908178 | PASS | 골판 지붕 위 점과 실제 불규칙 TIN support 경계가 놓인다. 2·3뷰에서 대상 식별이 명확하다. |
| DEBY_LOD2_4908353 | REVIEW_NEEDED | 1뷰 경계는 대상 지붕에 놓이나 2·3뷰의 일부 cyan 점이 전경 붉은 지붕에 겹쳐 보인다. 장면 occlusion 미처리 관찰이다. |
| DEBY_LOD2_4959461 | PASS | 세 근수직 뷰 모두 큰 회색 지붕과 bulk overlay가 맞는다. boundary component가 많아 원본 texture를 많이 가린다. |
| DEBY_LOD2_4959753 | REVIEW_NEEDED | 2·3뷰에서 class-6/TIN 성분이 수목·지면·인접 지붕 방향으로 퍼져 target outline이 불명확하다. row 2에도 분리·수직 성분이 관찰된다. |
| DEBY_LOD2_60042 | PASS | 매우 사선인 세 뷰에서도 긴 L자형 지붕 복합체를 따라 bulk overlay가 놓인다. 입면 성분과 가림이 함께 보인다. |
| DEBY_LOD2_60097 | REVIEW_NEEDED | 큰 붉은 지붕 전체가 아니라 우측의 좁은 strip에 support가 모이고 하단 입면 방향 성분이 이어져, overlay만으로 대상 형상을 식별하기 어렵다. |

집계는 `PASS 6`, `REVIEW_NEEDED 3`이다. 좌표계 전체가 한 방향으로 이동한 형태는 9개에서
관찰되지 않았다. 독립 RGB semantic gate는 실행하지 않았으므로 `PASS`도 해당 gate의 대체값이 아니다.

## 나머지 행 의미 확인

- 2행: raw DIM/MVS class-6 point cloud의 네 방향과 주축 단면
- 3행: canonical P0 DIM Roofer CityJSON의 네 방향과 요약
- 4행: Roofer output과 evaluation-only reference의 중첩

9개 패널 모두 위 행 의미를 유지한다. LiDAR 행이나 reference-only 행으로 바뀐 패널은 없다.
