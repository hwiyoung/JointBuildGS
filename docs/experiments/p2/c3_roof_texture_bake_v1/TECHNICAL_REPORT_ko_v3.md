# C3 roofline context + textured roof + GT-footprint display wall 기술 보고서 v3

## 판 구성

건물별 판을 `5행 × 8열`로 구성했다. 왼쪽 네 열은 C3-1, 오른쪽 네 열은 C3-2이며
시점은 `TOP / OBLIQUE_1 / OBLIQUE_2 / PRINCIPAL_SECTION`으로 고정했다.

1. 이전에 봉인된 `2024 current RGB + 2022 LoD2 roofline` 투영
2. Poisson current-RGB textured roof + 중립 GT-footprint display wall
3. 같은 Poisson roof의 distinct-view support + 같은 display wall
4. TSDF current-RGB textured roof + 중립 GT-footprint display wall
5. 같은 TSDF roof의 distinct-view support + 같은 display wall

첫 행 원본은 기존 v13 panel과 SHA-256이 같은 bytes로 복사했다. 따라서 mesh부터 갑자기
보는 대신 current image에서 어느 건물·어느 시기 roofline을 비교하는지 먼저 확인할 수 있다.

## 옆면의 의미

옆면은 GT footprint XY boundary를 local ground에서 가까운 roof-boundary 높이까지 올린
중립 회색 삼각형 strip이다. wall texture와 ground cap은 만들지 않았다. 각 hybrid OBJ는
두 material을 분리한다.

- `observed_roof_texture`: current RGB가 투영된 Poisson/TSDF roof
- `gt_footprint_display_wall`: texture 없는 중립 회색 oracle display geometry

이 wall은 `GT_FOOTPRINT_DISPLAY_WALL_NOT_HONEST_STAGE3`이며 C3가 복원한 wall, Roofer 입력,
official metric input 또는 roof coverage 개선으로 해석하면 안 된다. 특히 roof mesh와
footprint가 어긋나면 wall 상단도 깔끔하게 접합되지 않는데, 이는 숨겨야 할 렌더링 결함이
아니라 입력 geometry/reference 불일치다.

## 원본 해상도 검토

- `4906975`: roofline context와 textured Poisson/TSDF가 같은 곡면 지붕을 가리킨다. 중립
  wall을 붙이면 지붕이 공중에 떠 보이는 문제는 줄지만 Poisson/TSDF surface 차이는 유지된다.
- `4907177`: current image와 2022 roofline의 partition 불일치가 첫 행에서 보인다. Poisson은
  제한된 textured patch 위에 높은 wall이 붙고 TSDF roof는 극히 작다. wall이 형상을
  정상 복원한 것으로 보아서는 안 된다.
- `108580336`: image context에는 건물이 보이지만 Poisson은 footprint 밖 completion과
  `UNOBSERVED`가 많고 TSDF roof는 거의 없다. wall만 남은 부분은 roof evidence 부재를
  오히려 명확히 드러낸다.

## 다음 C3 surface 설계

장기적으로는 roof pixel만 먼저 잘라 Poisson/TSDF를 만드는 단일 경로보다 다음 구조가
적합하다.

1. depth-supported full-scene geometry를 보존한다.
2. RGB, semantic posterior, normal, distinct-view support를 fusion 중 surface에 함께 누적한다.
3. roof/wall/ground 경계를 유지한 class-aware surface를 만든다.
4. 그 뒤 roof class와 building component를 추출해 Roofer/read-out에 전달한다.

TSDF는 이 all-class semantic fusion의 주 경로로 적합하다. 반면 Poisson에 roof·wall·ground
point를 무차별로 함께 넣으면 서로 다른 class 사이를 면으로 메울 수 있으므로, Poisson은
class/component별 보조 비교로 두는 편이 안전하다. semantic을 geometry가 끝난 뒤 단순히
색칠만 하는 것이 아니라 fusion 단계부터 확률·support 속성으로 보존해야 한다.

## 실행 및 해석 경계

- GS training / checkpoint extraction: 0
- Poisson / TSDF reconstruction: 0
- Roofer / G2 / metric / C4/C5: 0
- current-RGB roof texture bake: 12
- display-only GT-footprint wall assembly: 12

총 3 case sheet, 120 visible cells, 108 unique panel PNG를 생성했고 artifact 198개 record의
hash를 검증했다. `official_G3_G4_PASS_usable: null`, `scientific_verdict: null`이며 우열이나
usable LoD2 판정을 하지 않는다.

Resolver는
[`artifacts/manifests/p2_c3_roof_texture_context_hybrid_v3.json`](../../../../artifacts/manifests/p2_c3_roof_texture_context_hybrid_v3.json)이다.
