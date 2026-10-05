# ARSGaussian — 근거 카드

`reviewed_at: 2026-09-09` · `scientific_verdict: null` · 직접 비교 후보: LiDAR+항공영상의 GS 기하/외관. Roofer/CityGML 결과와는 구성요소 비교.

## 원문·버전·확인 범위

- Yao et al., **ARSGaussian: 3D Gaussian Splatting with LiDAR for Aerial Remote Sensing Novel View Synthesis**. 읽은 원문은 [arXiv:2412.18380v2 PDF](https://arxiv.org/pdf/2412.18380v2), 2026-03-10 개정 author accepted manuscript, 24쪽. 출판 정보는 ISPRS JPRS 231 (2026), 288–306, [DOI](https://doi.org/10.1016/j.isprsjprs.2025.10.022). 페이지는 v2 PDF 기준; 출판본 페이지와 직접 치환하지 않는다. [버전 이력](https://arxiv.org/abs/2412.18380)
- **공식 코드 미공개 현재 확인:** `git ls-remote` HEAD `b4007e55ef1fca516ce03b179a5843ad56a7024b`; [고정 README](https://github.com/WenjuanZhang-aircas/ARSGaussian/blob/b4007e55ef1fca516ce03b179a5843ad56a7024b/README.md)는 `Coming soon!`. live 공식 tree는 README·img.jpg·video.gif뿐. 알고리즘 실행 경로는 원문으로 확인하며 원코드 검증했다고 쓰지 않는다.

## 1. 문제와 입출력

높은 촬영 고도·한정된 항공 시점의 floater/과성장·depth 오류를 줄여 NVS와 metric GS 기하를 만든다. 실제 관측=다중 RGB, LiDAR, DGPS/IMU/보정 정보. 외부 geometry=LiDAR; 동시 sensor integration 맥락이며 재사용 자산의 시간 유효성을 추정하는 연구는 아니다. 파생 정보=SfM feature/pose, SOR-filtered LiDAR, Delaunay+ACMH dense depth/normal, Gaussian local tangent guidance. 본체는 pretrained depth를 필수로 하지 않으며 §4.2.6의 pretrained completion은 비교군이다. [§3, Fig4–6, PDF5–9]

정확한 LiDAR·camera calibration과 충분한 LiDAR 지지가 핵심 가정이다. 좌표 변환은 WGS84 ECEF/지역계와 distorted camera model을 포함한다. current imagery가 언제나 LiDAR보다 기하적으로 우월하다고 두지 않고 LiDAR를 강한 metric 기준으로 사용한다.

## 2. 기여의 위치

| 요소 | N=논문 제안 / U=기존 사용 / ?=미확인 |
|---|---|
| 입력·전처리 | **N+U**: AIR-LONGYAN 데이터 구축, 항공 fusion pipeline; GNSS/IMU 처리·strip adjustment·SOR은 기존 절차. §3.2.1,4.1 |
| 좌표·카메라·정합 | **N+U**: distortion-aware alignment 결합 제안; Brown–Conrady 및 COLMAP-PCD progressive BA 사용. §3.2 식7–11 |
| 표현 | **U**: anisotropic 3D Gaussian+SH. §3.1 |
| 관측모형·렌더링 | **N+U**: distorted projection 통합 제안, 3DGS rasterization 사용; 구현 상세는 **?** |
| 증거 사용·감독·제약 | **N+U**: LiDAR-guided depth/normal/scale consistency 결합; Delaunay와 ACMH propagation 사용. §3.3 식12–15 |
| 초기화·최적화·모델 변경 | **N+U**: LiDAR 초기화, anisotropic distance pruning, local-plane guided split; 3DGS gradient/opacity density control 및 VastGaussian 분할 사용. §3.1,4.1.2 |
| 추출·후처리 | **U/?**: 블록 경계 밖 Gaussian 제거·병합, 렌더 및 depth 기하 평가. formal semantic mesh/CityGML 생성 기여는 확인 안 됨 |

## 3. 무엇을 고정하고 무엇을 수정하는가

- **앞단 추정:** DGPS/IMU initial pose→왜곡 모델과 LiDAR/영상 feature reprojection→COLMAP-PCD 3단계 progressive BA. §3.2.2는 camera calibration의 intrinsics/distortion과 LiDAR·feature 좌표를 고정값으로 기술하고 pose를 추정한다. 정합을 무시하는 방법이 아니다. [PDF8–9, Fig6, 식10–11]
- **기하 evidence:** LiDAR/SfM projection으로 초기 plane, 결손 pixel은 Delaunay 보간 후 ACMH/PatchMatch 반복으로 depth/normal을 refinement한다. 따라서 내부 반복과 image-supported depth 수정이 이미 있다. [§3.3 PDF9]
- **GS 추정:** 중심/rotation/scale/opacity/SH와 Gaussian 개체 수. 매 300 iteration LiDAR nearest neighbor를 다시 찾고 planar/elevation 조건 및 opacity로 pruning, local tangent plane 방향으로 split한다. 벽에 LiDAR가 없더라도 수평 support가 있으면 유지하도록 planar/elevation을 구별한다. LiDAR 자체를 지우거나 현시점 유효성으로 갱신하는 규칙은 확인되지 않는다. [§3.1.1–3.1.2 PDF6–7, §4.1.2 PDF10]
- **강한 제약:** LiDAR distance 기반 모델 삭제와 depth/normal 감독. 풀면 미관측 영역의 floater/과성장을 허용할 수 있고, 잘못된 LiDAR의 영향도 줄일 수 있다는 것은 우리 추론이며 조건별 검증 필요.

**정보 흐름:** `LiDAR 전처리 + RGB feature + camera calibration → BA pose → 정합 입력 → Delaunay/ACMH depth·normal → GS 초기화·감독 ↔ 렌더 residual·주기적 LiDAR proximity/split`. 논문 introduction(PDF4)은 training/feedback 통합을 주장하지만 §3.2.3은 BA 결과를 model initialization으로 기술한다. **GS RGB residual→BA 재호출, LiDAR 수정, depth 재생성의 실제 upstream 경로·주기는 미확인**이다. 원코드가 없어 완전 공동/반복 추정이나 완전 단방향으로 단정하지 않는다.

## 4. 실제 검증 범위

- UrbanScene3D Sci-Art(항공 RGB, handheld LiDAR .1–.3pt/m²)와 AIR-LONGYAN(RGB 602장, 약 325,000m², LiDAR 4–8pt/m²). split은 70/15/15 train/validation/test, 30k iteration, A6000, 8 blocks 및 30% overlap. 정확한 image membership·공간 독립성·반복 seed는 확인되지 않는다. [§4.1 PDF10]
- NVS PSNR/SSIM/LPIPS, **LiDAR RMSE**, time/FPS/모델 크기. Table1의 AIR-LONGYAN RMSE .327m vs LetsGO 1.626m, NVS 27.908dB; UrbanScene3D에서는 CityGaussianV2 PSNR 26.874가 ARS 26.747보다 높다. 모든 지표/scene의 보편 우위가 아니다. [Table1 PDF13]
- **참조 독립성 한계:** §4.2.5.2는 RMSE를 LiDAR point 자체로 계산하므로 LiDAR 교란에 비해 visual metric이 더 민감하다고 명시한다. 감독 LiDAR와 독립 current geometry test의 정확도 증거로 확대하지 않는다. [PDF17]
- Table3(PDF14): LiDAR densification/alignment/geoloss 묶음 제거. geoloss 안 depth/normal/scale 효과가 모두 독립적으로 분해된 것은 아니다. Table4는 pruning threshold의 성능/비용; Table5 density; Table6 coordinate noise; Table7 raw/SOR/artificial noise; Table8 glass/asphalt/wall/canopy gap; Table9 depth completion 교체의 downstream NVS 및 시간 비교. 따라서 ‘잡음·오정합·결손·전처리 전달은 기존 방법이 무시’라는 공백은 기각한다.
- currentness·실제 시간차 구조 변화·독립 표면 completeness·eave/ridge 세부·국소 비악화는 평가되지 않는다. Table5 본문 첫 downsample 5%와 표 10%의 불일치, Table8 Whole 값과 Table1 Full 값 차이는 그대로 두고 실행 config 없이는 동일 기준으로 합치지 않는다.

## 5. 남은 오류와 전달 경로

| 조건·잔여 오류 | 사실/해석·상태 | 전달 경로·대안 원인 |
|---|---|---|
| LiDAR 좌표 noise 0→10cm: PSNR 27.908→19.405, RMSE .327→.481 | **관측된 악화**, Table6/PDF17–18 | LiDAR→잘못된 pose alignment 및 depth/normal→GS 오류는 **저자 해석**. 원인별 intervention으로 분리한 결과는 아님 |
| SOR 강화 K=100,σ=1.5에서 성능 저하 | **관측된 악화**, Table7/PDF18; 유효점 제거는 **저자 해석** | 전처리 오배제→geometric support/감독 감소. false removal 위치·양은 미확인 |
| glass/asphalt/canopy 결손, wall 결손은 영향 작음 | **관측된 실패/조건 차이**, Fig15/Table8/PDF19 | glass structure/texture 손실, canopy overstretch; asphalt는 transient objects도 원인 후보라는 **저자 해석** |
| 자체 depth generator의 low-texture 결함 | **저자 보고**, §4.2.6/PDF20 | 보간/patch propagation→고정 감독→복원. ACMMP 대체는 더 좋은 RMSE/PSNR·더 큰 비용을 이미 보임 |
| forest/water, 매우 sparse/low-quality LiDAR | **범위 밖/저자 한계**, §5/PDF21 | 밀도·반사·투과·camera 모델 차이. 관측된 도시 결과만으로 전체 일반화 불가 |

## 6. 연구 공백 후보

**이미 해결:** 정확 정합, LiDAR-directed model growth/pruning, image+LiDAR depth completion, depth/normal/scale 감독, 밀도·오차·피복 변화 분석. ‘전처리→감독 오류 전달’도 저자가 이미 설명한다. 이 현상 자체를 발견으로 주장할 수 없다.

남는 후보는 **불완전하고 정확성이 공간적으로 다른 재사용 자산 조건의 검증 부족**과 **강한 LiDAR 기준의 선택적 완화**다. 가장 가까운 기존 해결은 SOR+정합+ACMH/ACMMP/SDSGM 및 ARS 자신의 anisotropic pruning이다. 최소 비교는 이를 적용한 강한 baseline, 고정 confidence/robust loss, 제안법을 같은 관측·독립 참조·출력에서 비교한다. 유효점 오제거/오류점 잔존이 최종 표면/렌더의 어디에 전달되는지 추적하고 성공 지역 손실도 포함한다. **기각 조건:** 기존 denoise·registration·depth generator 교체로 해소되거나 독립 reference에서 이득이 사라지면 새 판단/반복 모듈의 필요성을 기각한다. GS가 필수라는 근거는 없으므로 같은 evidence의 비GS depth/mesh 결과도 필요하다.
