# C3 texture 판 C1 LiDAR·LoD2 reference 확장 보고서 v4

## 결과

기존 C3 current-RGB textured Poisson/TSDF 판에 두 비교 행을 추가했다. 건물별 판은
`7행 × 8열`이다.

1. 2024 current RGB + 2022 roofline 투영
2. C1 current UAS LiDAR Roofer output
3. 2022 LoD2 evaluation reference
4. Poisson textured roof + GT display wall
5. Poisson view support + GT display wall
6. TSDF textured roof + GT display wall
7. TSDF view support + GT display wall

C1과 LoD2는 C3-1/C3-2에 종속되지 않으므로 같은 네 패널을 좌우에 반복했다. 모든 panel은
봉인 source와 SHA-256이 같은 bytes로 복사했다. Roofer, Poisson, TSDF, texture, metric은
재실행하지 않았다.

## 원본 해상도 검토

- `4906975`: current image, C1 Roofer, LoD2와 textured Poisson/TSDF를 같은 판에서 비교할 수
  있다. C1/LoD2는 폐합 구조를 제공하고 TSDF/Poisson은 관측 기반 roof 차이를 보존한다.
- `4907177`: C1 행은 LoD2 GroundSurface Z 보정 전 봉인 결과다. C1의 성긴 점과 LoD2의
  계단형 roof, current texture patch의 위치 차이가 명확하다. 이 행을 보정 완료 결과로
  해석하면 안 된다.
- `108580336`: C1 Roofer와 LoD2 reference는 건물 외형을 보이지만 TSDF에는 roof가 거의
  없다. C1/LoD2를 함께 놓아도 TSDF roof evidence가 생기는 것은 아니며, display wall과
  관측 roof를 분리해서 읽어야 한다.

## 해석 경계

LoD2는 2022 evaluation context이며 current C3 geometry의 생성 입력이 아니다. 4907177은
별도 후속에서 LoD2 `GroundSurface` Z를 diagnostic ground anchor로 사용해 C1/C2 filtering과
Roofer eligibility를 다시 확인한다. current UAS에는 `+45.7m`를 임의로 적용하지 않는다.

총 3 case sheet, 168 visible cells, 132 unique panel PNG를 생성했고 138 artifact record의
hash를 검증했다. `official_G3_G4_PASS_usable: null`, `scientific_verdict: null`이다.

Resolver는
[`artifacts/manifests/p2_c3_roof_texture_c1_lod2_reference_extension_v4.json`](../../../../artifacts/manifests/p2_c3_roof_texture_c1_lod2_reference_extension_v4.json)이다.
