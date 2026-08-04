# C3 roof-only Poisson/TSDF current-RGB texture 기술 보고서 v2

## 결과

봉인된 C3-1/C3-2 roof-only Poisson mesh와 TSDF mesh 각각에 2024 exact-current RGB를
실제 투영해 planar UV texture를 만들었다. 세 건물, 두 C3 조건, 두 mesh 방법의 조합은
12개이며 각 조합마다 다음을 생성했다.

- 768 × 768 RGBA roof texture atlas
- view-support atlas
- UV와 material을 가진 textured OBJ/MTL
- `TOP / OBLIQUE_1 / OBLIQUE_2 / PRINCIPAL_SECTION` texture panel과 support panel

벽과 지면은 생성하거나 texture하지 않았다. 원 mesh에서 padded GT-footprint atlas를 향한
top-down ray에 실제로 맞은 상부 triangle만 textured OBJ에 남겼다. GT footprint는 atlas
범위와 표시 outline에만 썼으며 source mesh를 다시 복원하거나 지붕 형태를 보정하지 않았다.

## texture 계산

건물별 shared 24-view plan 가운데 상위 12개의 exact-current RGB와 해당 COLMAP camera를
사용했다. 각 roof texel은 mesh self-z-buffer, image bounds, 입사각 제한을 통과해야 하며,
MVS depth가 있는 pixel에서는 뒤쪽 surface를 occlusion으로 제외했다. 통과한 색은
`incidence²` 가중 평균으로 합쳤다. 관측되지 않은 texel은 회색/투명 `UNOBSERVED`로 남겼고
inpainting하지 않았다.

따라서 이 결과는 이전 속성판의 PLY vertex RGB 전달이나 임의 method 색상이 아니라 실제
current image texture다. 동시에 texture는 geometry를 개선하지 않는다. 잘못 메운 Poisson
surface나 지나치게 작은 TSDF surface는 그 상태로 드러난다.

## roof surface 조건부 texture coverage

아래 비율은 **현재 존재하는 mesh top-surface texel 중 RGB가 하나 이상 투영된 비율**이다.
footprint 전체 roof coverage나 geometry 정확도가 아니다. `max views`는 한 texel을 지지한
최대 current RGB view 수다.

| 건물 | 조건 | mesh | RGB 관측 비율 | max views | surface texel |
|---|---|---:|---:|---:|---:|
| 4906975 | C3-1 | Poisson | 99.30% | 12 | 463,483 |
| 4906975 | C3-1 | TSDF | 99.53% | 12 | 329,576 |
| 4906975 | C3-2 | Poisson | 98.80% | 12 | 478,427 |
| 4906975 | C3-2 | TSDF | 99.12% | 12 | 326,223 |
| 4907177 | C3-1 | Poisson | 94.64% | 8 | 379,096 |
| 4907177 | C3-1 | TSDF | 100.00% | 9 | 14,793 |
| 4907177 | C3-2 | Poisson | 99.88% | 9 | 195,663 |
| 4907177 | C3-2 | TSDF | 100.00% | 9 | 13,340 |
| 108580336 | C3-1 | Poisson | 44.35% | 7 | 503,124 |
| 108580336 | C3-1 | TSDF | 54.76% | 5 | 1,523 |
| 108580336 | C3-2 | Poisson | 38.64% | 7 | 301,282 |
| 108580336 | C3-2 | TSDF | 45.19% | 5 | 2,204 |

## 원본 해상도 시각 검토

- `4906975`: Poisson과 TSDF 모두 실제 곡면 지붕의 어두운 중앙부, 밝은 곡선 띠와 외곽
  캐노피 무늬가 연속적으로 보인다. 두 방법의 texture 관측 비율도 98.8–99.5%다. 이
  사례에서는 texture가 정상 동작하며 geometry 차이를 읽을 수 있다.
- `4907177`: Poisson에는 image texture가 넓게 붙지만 그 surface가 orange reference
  footprint/roof partition과 맞는지는 별도 문제다. TSDF의 100%는 좋은 roof coverage라는
  뜻이 아니라, 남아 있는 극소수 surface texel만 모두 관측됐다는 뜻이다. TSDF surface
  texel은 13–15천으로 Poisson의 196–379천보다 훨씬 적다.
- `108580336`: Poisson은 넓지만 footprint와 어긋난 surface와 회색 `UNOBSERVED`가 많이
  남는다. TSDF는 footprint 안의 roof mesh가 거의 없어 texture할 표면 자체가 매우 작다.
  Roofer 형상이 그럴듯하다는 사실과 GS-derived roof mesh evidence가 충분하다는 주장은
  분리해야 한다.

## render recovery

첫 v1 texture atlas와 textured OBJ는 정상 생성됐지만 preview가 42,000 face를 넘는 mesh의
triangle을 간격 샘플링해 TSDF 판에 거짓 흰 구멍을 만들었다. v1은 수정하지 않고 보존했다.
이 v2 recovery는 preview에서 모든 roof triangle을 그린 canonical 표시판이다. 재학습이나
Poisson/TSDF 재생성으로 고친 것이 아니다.

## 실행 계수와 해석 경계

- GS training: 0
- checkpoint render extraction: 0
- Poisson reconstruction: 0
- TSDF reconstruction: 0
- roof texture bake: 12
- Roofer/G2/metric/C4/C5: 모두 0

이 작업의 수치는 texture 투영 QA이며 공식 geometry metric이 아니다.
`official_G3_G4_PASS_usable: null`, `scientific_verdict: null`이다. C3-1/C3-2, Poisson/TSDF의
과학적 우열이나 usable LoD2 판정을 하지 않는다.

외부 artifact resolver는
[`artifacts/manifests/p2_c3_roof_texture_bake_render_recovery_v2.json`](../../../../artifacts/manifests/p2_c3_roof_texture_bake_render_recovery_v2.json)이다.
