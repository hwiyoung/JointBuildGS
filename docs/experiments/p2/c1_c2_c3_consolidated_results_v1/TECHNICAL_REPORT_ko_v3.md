# C1/C2/C3 통합 정성 결과판 v3

## C1/C2 교정

v2의 C1/C2 페이지는 오래된 comparison-matrix v6를 상속했다. input과 output raster hash는 서로 달랐지만 두 행 모두에 큰 녹색 UAS evaluation reference가 겹쳐 실제 input point와 Roofer plane의 차이를 가렸다. 또한 후속 건물별 oracle 결과보다 오래된 계보였다.

v3는 최신 건물별 봉인 source로 교체했다.

- input: 해당 operation의 sealed LAS, class 6 roof는 cyan, class 2 terrain은 magenta
- output: 해당 operation의 sealed CityJSONSeq `RoofSurface` plane 채움면
- orange dashed: GT-footprint oracle context
- `4907177 C1`: 후속 LoD2-ground-Z diagnostic의 740 class-6 input과 2-plane output
- `4907177 C2`: class-6 0점이므로 `NOT RUN`

따라서 input과 output은 같은 자료가 아니며, v3에서는 역할이 시각적으로도 분리된다.

## 4906975 C3-2 semantic과 consensus

5행은 checkpoint의 Gaussian semantic argmax를 현재 고정 시점에서 직접 표시한다. 큰 wall Gaussian의 in-plane scale과 occlusion 때문에 roof가 가려질 수 있다.

6행은 별도 24-view 렌더링에서 다음 조건을 만족한 depth pixel을 3D로 역투영·합의한 결과다.

- rendered semantic class = roof 1
- alpha ≥ 0.5
- finite median depth
- footprint buffer 1 m 내부
- 0.15 m voxel
- 최소 2개 서로 다른 view의 지지

`4906975 C3-2` consensus 44,177점 중 `|normal_z|<0.3`인 wall-like point는 0.75%, `|normal_z|>0.7`인 roof-like point는 90.62%, median `|normal_z|`는 0.977이다. 따라서 6행의 벽처럼 보이는 부분 대부분은 roof-oriented evidence다. 다만 selection에 normal gate는 없으므로 0.75% 정도의 wall/edge semantic leakage는 남는다.

## mesh 입력

Poisson과 TSDF는 같은 roof-only consensus evidence에서 출발한다.

- Poisson: consensus `xyz + averaged normal + RGB`를 Open3D Poisson depth 8로 표면화한 후 footprint/evidence 범위로 crop
- TSDF: 같은 consensus voxel key에 속한 원래 rendered-depth pixel만 되살려 카메라 ray로 재적분; voxel 0.15 m, truncation 0.45 m
- Roofer input LAS: 이 mesh branch와 별개이며 TSDF나 Poisson에서 sampling한 점군이 아님

## principal section locator

상속 panel에는 두 section frame이 섞여 있었다.

- blue dashed legacy E-section: C3 2–5행과 9행, C1/C2 spatial rows
- red solid footprint-PCA section: C3 6–8행과 10–12행
- 1행: 네 번째 열도 camera image이며 geometric section이 아님

v3는 각 페이지 상단에 footprint TOP locator, cut line과 LOOK arrow를 표시했다. 두 frame을 하나처럼 보이게 하지 않았으며, principal 열의 cross-row 직접 비교에는 frame 제한이 있다. 후속 완전 통일판을 만들 경우 모든 source geometry를 한 canonical PCA frame으로 재렌더해야 한다.

## 경계

GS 학습, checkpoint extraction, Poisson, TSDF, Roofer, G2, metric 재계산과 C4/C5 access는 모두 0회다. `official_G3_G4_PASS_usable`와 `scientific_verdict`는 null이다.
