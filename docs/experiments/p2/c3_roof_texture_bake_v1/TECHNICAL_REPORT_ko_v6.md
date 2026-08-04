# C1 Roofer / C3 textured mesh 비교판 v6

## 결과

세 건물에 대해 C3-1과 C3-2를 분리한 4열 비교판을 만들었다. 각 조건에는 TOP, OBLIQUE 1, OBLIQUE 2, PRINCIPAL SECTION이 들어간다.

- primary 4행: C1 current UAS LiDAR Roofer, 2022 LoD2 reference, Poisson textured roof mesh, TSDF textured roof mesh
- detail 7행: primary에 2024 RGB + 2022 roofline, Poisson support, TSDF support 추가
- source panel 내부의 긴 제목을 짧은 역할/시점 제목으로 교체해 인접 셀과 겹치지 않게 했다.

## DEBY_LOD2_4907177 C1 복구

기존 C1은 Roofer 실패가 아니라 local ground가 roof level 근처로 잡혀 class 6가 0점이 된 전처리 실패였다. 새 v5 진단에서는 LoD2 GroundSurface native Z 514.27 m에 기존 epoch-to-current shift +45.7 m를 적용해 current ground anchor 559.97 m를 사용했다.

- raw points inside footprint: 16,892
- deterministic 0.2 m class 6 building: 740
- deterministic 0.2 m class 2 terrain: 71
- Roofer invocation: 1
- Roofer exit code: 0
- CityJSONSeq output count: 1

LoD2 RoofSurface XYZ, roof type, final roof model은 Roofer 입력으로 사용하지 않았다. 다만 결과 형상은 낮은 면과 높고 좁은 면으로 분리되어 보이므로, terminal 성공은 형상 품질 성공을 의미하지 않는다. 이 결과는 LoD2 GroundSurface Z oracle diagnostic이며 official honest Stage 3가 아니다.

## DEBY_LOD2_108580336 TSDF 공백

TSDF가 지붕을 임의로 삭제한 것이 아니다. 동일 roof-only multi-view evidence에서 다음과 같이 footprint coverage가 매우 낮다.

| condition | roof consensus points | footprint roof coverage | TSDF largest component | TSDF evidence distance p95 |
|---|---:|---:|---:|---:|
| C3-1 semantic | 833 | 1.23% | 0.378 | 0.301 m |
| C3-2 semantic + depth | 1,191 | 1.50% | 0.666 | 0.304 m |

TSDF는 관측 truncation band 안의 표면만 남겨 희소한 roof evidence를 그대로 보여준다. 반면 Poisson은 비관측 간격을 연결해 더 완성된 면처럼 보일 수 있다. 이번 실행에는 full-scene semantic TSDF 재구성이 포함되지 않았으며 기존 roof-only Poisson/TSDF 결과를 비교했다.

## 실행 경계

- v5: 4907177 C1 Roofer 1회
- v6: 표시 재배열만 수행, Roofer 0회
- 전체: G2 0, GS training 0, metric recomputation 0, Poisson reconstruction 0, TSDF reconstruction 0, C4/C5 access 0
- `scientific_verdict: null`

`scientific_verdict: null`은 기술 산출물과 관찰 수치를 제공했지만 C1/C3 우열, 정확도 합격, 공식 사용 가능 판정을 내리지 않았다는 뜻이다.
