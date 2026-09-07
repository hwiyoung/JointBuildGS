# 추가 대조군 원문·공식 구현 감사

- 문서 식별자: `PHD-WU-VALLET-P3-RELATED-METHODS-v1`
- 확인일: 2026-09-07
- 범위: 문헌·공식 공개 저장소 읽기. 본 문서 작성 과정에서 기존 파일 수정, 데이터 가공, 코드 설치, 학습·재현 실행은 수행하지 않았다.
- 연구 상태: 개발 비교 설계이며 `scientific_verdict: null`.
- 우선순위: **Wu–Vallet 2026은 전체 연구의 주 대조군**, **P3는 첫 개발 사례**, P2는 낡은 ALS 배제의 후속 대조 사례다. Wu–Vallet 상세 감사는 이 작업의 별도 문서와 연결한다.
- 이 문서는 기존 `thesis_topic_v1/01_NECESSITY_ko_v1.md`, `02_GAP_ko_v1.md`를 덮어쓰지 않는 추가 기록이다.

## 1. 비교에서 먼저 인정할 기존 성과

과거 기하를 보존하면서 현재 영상으로 갱신하는 것, LiDAR로 영상의 약한 기하를 보완하는 것, 구조 prior와 영상 세부·외관을 결합하는 것, 기존 GS에서 국소 변화만 갱신하는 것은 각각 선행연구가 다룬 기능이다. 따라서 이러한 기능의 조합만으로 신규성이나 성능 우위를 확정할 수 없다. 아래 표는 실제 원입력·원산출물을 먼저 고정하고, 오류·시간차·정합 불확실성이 함께 있는 P3/P2로 옮길 때 남는 검증을 구분한다.

| 방법 | 정확한 식별 | 원입력·전제 | 원산출물 | 이번 비교에서의 위치 |
|---|---|---|---|---|
| Zhou 등, LEAD-Matching | **LiDAR-guided dense matching for detecting changes and updating of buildings in Airborne LiDAR data**, ISPRS JPRS 162, 200–213, **2020**. DOI [10.1016/j.isprsjprs.2020.02.005](https://doi.org/10.1016/j.isprsjprs.2020.02.005) | 과거 ALS, 보정된 항공 near-nadir stereo와 내·외부표정. 실험 후처리는 NIR NDVI와 BAG/도로·하천 지도도 사용 | 변화 구역의 영상 3D점으로 해당 ALS를 교체한 **갱신 점군**, 변화 지도. 논문에 mesh 시각화도 있음 | Wu와 함께 비GS 기하 갱신 계열을 비교. 기존 MVS 점군을 섞는 것만으로 원방법 재현이라고 부르지 않음 |
| ARSGaussian, Yao 등 | **ARSGaussian: 3D Gaussian Splatting with LiDAR for aerial remote sensing novel view synthesis**, ISPRS JPRS 231, 288–306, **2026**. DOI [10.1016/j.isprsjprs.2025.10.022](https://doi.org/10.1016/j.isprsjprs.2025.10.022) | 항공 다중시점 RGB와 정합·품질관리를 거친 LiDAR. 왜곡 카메라 모델/자세 정합과 LiDAR 기하 기준 사용 | 3DGS 장면, 새로운 시점 RGB와 깊이·기하 추정 | ALS 기반 재구성의 강한 관련 대조. 코드 공개 여부가 즉시 재현 가능성을 제한 |
| GeoGS, Zhang·Wysocki·Jutzi | **GeoGS: Geometric Prior-Guided Gaussian Splatting for Robust Urban Reconstruction from Sparse Views**, ISPRS JPRS 240, 184–201, **2026**. DOI [10.1016/j.isprsjprs.2026.07.011](https://doi.org/10.1016/j.isprsjprs.2026.07.011) | 공통 좌표의 CityGML **LoD2 mesh**, 희소 RGB, 알려진 카메라 자세, pose-conditioned DA3 깊이 | GS 장면, 새로운 시점 렌더, 추출 mesh | 구조 보호·세부 정제의 우선 B 대조. ALS로 prior를 바꾸면 별도 입력 변경 실험 |
| GS4Buildings, Zhang·Wysocki·Jutzi | **GS4Buildings: Prior-Guided Gaussian Splatting for 3D Building Reconstruction**, ISPRS Annals X-4/W6-2025, 249–256, **2025**. DOI [10.5194/isprs-annals-X-4-W6-2025-249-2025](https://doi.org/10.5194/isprs-annals-X-4-W6-2025-249-2025) | 정합 LoD2 mesh, UAV RGB, 카메라 자세; mesh raycasting 깊이·법선·유효 마스크 | 2DGS 장면, 렌더, TSDF/Marching Cubes mesh | GeoGS 이전 단계와 prior 감독의 구성요소 대조 |
| CL-Splats, Ackermann 등 | **CL-Splats: Continual Learning of Gaussian Splatting with Local Optimization**, ICCV **2025**. [CVF 원문](https://openaccess.thecvf.com/content/ICCV2025/papers/Ackermann_CL-Splats_Continual_Learning_of_Gaussian_Splatting_with_Local_Optimization_ICCV_2025_paper.pdf), [arXiv:2506.21117v2](https://arxiv.org/abs/2506.21117v2) | **기존 3DGS**와 국소 변화 주변 신규 RGB; 신규 자세를 기존 좌표계에 정합 | 갱신 GS, 변화 마스크, 새로운 시점 렌더, 과거 상태 복구 | A–B 연결과 보존·갱신의 관련 비교. 무색 ALS를 바로 입력하는 원방법은 아님 |

ARSGaussian은 arXiv v1이 2024-12-24, v2가 2026-03-10이며 정식 권호는 2026년이다. DOI 문자열의 `2025`를 권호 연도로 사용하지 않는다. 이 문서의 GeoGS는 Zhang 등의 LoD2 prior 논문이다. CVPRW 2026의 위성영상 **Geospatial Gaussian Splatting** 및 GeoGS-SLAM 등 동명 연구와 혼합하지 않는다. [ARSGaussian 저자 원고 기록](https://arxiv.org/abs/2412.18380), [GeoGS 출판사](https://www.sciencedirect.com/science/article/pii/S0924271626003588)

## 2. 공개 코드·라이선스와 재현 상태

다음 `main` commit은 확인일에 `git ls-remote`로 읽은 원격 상태다. 저장소 공개와 실행 검증은 별개이며, 아래 방법은 이번 감사에서 실행하지 않았다. 라이선스는 공개 파일에서 확인한 분류이고 하위 구성요소의 조건은 실제 도입 시 함께 보존한다.

| 방법 | 공식 저장소와 확인 commit | 현재 실제 공개물 | 라이선스 확인 | 재현 상태 |
|---|---|---|---|---|
| Zhou 2020 | 원문·대학 저장소·정확 제목 검색에서 저자 공식 실행 저장소를 **찾지 못함** | 원문은 C++ OpenCV/GDAL/libLAS, Twente surface growing, UGM alpha expansion 사용을 명시 | 구현 라이선스 미확인. 논문 원고의 CC BY-NC-ND와 코드 라이선스는 별개 | 논문 기반 재구현 조건을 정해야 함. 공식 코드가 존재하지 않는다고 단정하지 않음 |
| ARSGaussian | [공식 repo](https://github.com/WenjuanZhang-aircas/ARSGaussian/tree/b4007e55ef1fca516ce03b179a5843ad56a7024b), `b4007e55ef1fca516ce03b179a5843ad56a7024b` | root/API 확인 결과 `README.md`, `img.jpg`, `video.gif` 세 파일. README는 **“Coming soon!”** | 해당 tree에 LICENSE·실행 코드 없음 | **공식 코드 실행 불가**. 논문의 dataset/code 공개 예고를 실제 제공으로 간주하지 않음 |
| GeoGS | [공식 repo](https://github.com/zqlin0521/GeoGS/tree/db40c95c657ec03ff21c83cb99cf39f4e90247a6), `db40c95c657ec03ff21c83cb99cf39f4e90247a6` | 전처리·학습·렌더·mesh·2D/3D 평가 코드. README에 15 UAV뷰 example 다운로드/실행 경로 | [Gaussian-Splatting 비상업 연구 라이선스](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/LICENSE.md); 하위 모듈 별도 | 코드 기반 재현 후보. example 실제 바이트와 전처리/학습 재현은 아직 미검증 |
| GS4Buildings | [공식 repo](https://github.com/zqlin0521/GS4Buildings/tree/f0be3e257ee6f58e42d1aa3258810c7b78866a7d), `f0be3e257ee6f58e42d1aa3258810c7b78866a7d` | LoD2 초기화·깊이/법선 생성·학습·렌더·평가 코드. GeoGS example 재사용 시 normal 재생성 지침 | [Gaussian-Splatting 비상업 연구 라이선스](https://github.com/zqlin0521/GS4Buildings/blob/f0be3e257ee6f58e42d1aa3258810c7b78866a7d/LICENSE.md); 하위 모듈 별도 | 코드 기반 재현 후보. image/pose/prior 계보 동결 필요 |
| CL-Splats | [공식 repo](https://github.com/jan-ackermann/cl-splats/tree/587fffc207f9c7cbb348f35e6d1d223d007eab69), `587fffc207f9c7cbb348f35e6d1d223d007eab69` | pip package, gsplat backend, 전처리·변화 검출·학습·평가·history, [공식 HF dataset](https://huggingface.co/datasets/ackermannj/cl-splats-dataset) 링크 | [원 기여 MIT](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/LICENSE), 3DGS 파생물은 별도 `3DGS_LICENSE.md` | **저자 공개 재구현** 실행 후보. 논문 당시 구현과 동등성은 별도 검증 |

GeoGS와 GS4Buildings 공식 구현은 원 2DGS의 `diff-surfel-rasterization`을 사용한다. JointBuildGS 자체 개발의 gsplat 원칙에 맞추어 이식한 구현은 **gsplat 이식본**으로 기록해야 하며 원코드 재현과 동일 표기를 쓰지 않는다. 이번에는 정적 감사만 수행했으므로 이 사항은 Wu 원재현·P3 개발 전체를 중단하는 사유가 아니다.

CL-Splats README는 현재 공개본을 **“public reimplementation”**으로 부르고 원논문 구현과 차이가 있을 수 있음을 명시한다. 현재 README의 Depth-Anything V2 lifting/gsplat 구성과 논문 §3의 majority voting/HDBSCAN 구역/local optimization 설명 간 대응을 먼저 감사해야 한다. 공개 코드의 실행 성공만으로 원논문 수치 재현을 선언할 수 없다. [고정 README](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/README.md)

## 3. 원문에서 해결한 것과 이 설정에서 남는 검증

### Zhou 2020 — 이미 시기 간 LiDAR 갱신을 다룬다

[저자 원고 PDF](https://repository.tudelft.nl/file/File_5e70c9f8-1674-49ab-b4a5-fa3085f3dd77)의 §3은 LiDAR plane으로 최대 세 DSM 후보를 만들고 disparity 탐색을 제한한 뒤 영상의 경계 단서로 높이를 고른다. 처음 찾은 부분 변화를 계층 dense matching으로 확장하여 갱신한다. 짧은 원문 근거는 **“preserve LiDAR data in unchanged areas”**다. §3.3의 native endpoint는 변화 영역을 영상점으로 교체한 점군이며 GS나 텍스처 mesh 학습을 요구하지 않는다.

§4.1에서 Assen은 ALS 2012/영상 2018의 실제 시간차 사례다. Amersfoort는 ALS·영상 모두 2010이고 2008 BAG로 이전 상태를 모사하므로 두 사례의 증거 성격을 분리한다. 원문은 ALS 경계의 mixed return, 그림자·저텍스처, 일부 잘못된 ALS 높이의 사례도 논의한다. 따라서 오류나 시간차를 전혀 다루지 않았다고 쓰면 안 된다.

P3 적용에서 남는 것은 평면 후보가 실제 사용 가능한지, 영상 표정·가림 조건을 만족하는지, NIR·지도 후처리 없이 동일 범위를 재현할 수 있는지다. 부족한 입력을 대체하면 그 차이를 기록한다. 판정과 점군 갱신의 이득을 먼저 측정하고, 구조·외관 확장은 후속 별도 산출물로 비교한다.

### ARSGaussian — 정합과 LiDAR 기하 감독도 기존 기여다

[저자 원고 v2 PDF](https://arxiv.org/pdf/2412.18380v2)의 §3은 LiDAR 기반 densification, 왜곡을 포함한 카메라·기하 정합, depth/normal/scale 제약을 다룬다. 원문 근거 **“high-precision depth priors”**는 LiDAR를 기하 기준으로 사용하는 설정을 나타낸다. LiDAR 구멍·영상 희소 시점과 정합 문제를 다루므로 단순히 이상적 센서 결합으로 축소해서는 안 된다.

남는 검증은 P3 ALS의 오류와 현재 적합성을 모르는 상태에서 기하 감독이 언제 유리하고 언제 잘못된 구조를 유지하는가이다. 논문에서 우리의 시간차/오류 혼합 조건의 검증을 확인하지 못한 것이며, 방법이 반드시 실패한다는 뜻은 아니다. native output은 GS/영상·깊이로 기록하고 정식 textured mesh 산출 계약은 확인된 것으로 쓰지 않는다. 공식 코드 미공개 상태라 이번 우선순위는 원문 대응 명세까지다.

### GeoGS — 구조 보호·세부 정제·적응 가중은 이미 제안되었다

[출판사 초록](https://www.sciencedirect.com/science/article/pii/S0924271626003588)과 [고정 공식 README](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/README.md)는 LoD2 초기화, proximity 기반 구조 보호, DA3와 LoD2 깊이를 쓰는 anchoring/refinement 및 dual-gated 가중을 설명한다. 원문 근거 **“recovering as-built details”**는 세부 복원 자체가 이 논문의 목표임을 보여준다.

공식 코드의 알려진 자세·정합 LoD2 전제와 원산출물을 먼저 재현해야 한다. ALS 점군을 LoD2 대신 넣는 것은 prior 표현과 품질을 바꾼 실험이다. depth/RGB 손실에 따른 가중 조절을 곧바로 ALS의 국소 현재성 판정과 동일시하지 않는다. 남는 것은 잘못된 prior 보호, 정합 오차와 실제 변화의 혼동, 양호한 구조의 유지 및 관측 가능한 세부 복원의 실측이다.

출판사 전문은 이번 접근에서 안정적으로 확보하지 못했다. 원리의 상세 구현은 저자 공식 코드와 README 근거이며 논문 전체 실험의 모든 조건을 확인했다는 주장은 하지 않는다.

### GS4Buildings — prior 감독의 강점과 실제 논문 한계를 함께 읽는다

[원문 §3.1–3.3·§4.4](https://arxiv.org/html/2508.07355v1)는 LoD2 초기화, raycasting 깊이·법선, 유효 교차 마스크와 시간에 따라 변하는 2단 loss schedule을 사용한다. 구조 완전성과 외관·mesh 재구성은 기존 성과다. 원문은 강한 prior 감독이 충분히 관측된 세부를 평활화할 수 있음을 논의하며 **“attenuate fine-grained geometric details”**라고 명시한다.

이를 전 구간 고정 가중 때문이라고 재해석하지 않는다. GeoGS는 이 계열의 후속이며 공식 GS4Buildings README도 이를 안내한다. P3에서는 LoD2 prior와 ALS prior의 입력 차이를 유지한 채 구조/세부 trade-off를 평가한다. 현재 UAS는 평가 참조로 분리하고, LoD3-derived 완전성 참조와 current geometry 정확성의 의미도 나눈다.

### CL-Splats — 보존과 갱신·렌더의 연결은 직접 관련 있다

[원문 §3·§6·§7·§9.2](https://arxiv.org/html/2506.21117v2)는 기존 GS 렌더와 신규 영상의 DINOv2 특징 차이, 다중뷰 투표, 3D 국소 구역 최적화로 기존 영역을 보존한다. 새 물체의 sampling 및 과거 상태 복구도 포함한다. 원문 한계에는 **“does not handle global illumination variations”**와 가는 구조에서 변화 구역을 과소추정한 사례가 있다.

무색 ALS만으로는 기존 RGB GS의 비교 렌더가 주어지지 않는다. 따라서 원방법 재현은 공식 benchmark의 기존 GS→갱신 GS로 수행하고, ALS에 맞추는 변화는 별도 adapter로 기록한다. A의 마스크·구역 판정 품질과 B의 기하/렌더 영향을 연결하되 독립 평가한다. 얇은 구조 사례가 있다는 이유로 P3/P2의 실패를 미리 가정하지 않는다.

## 4. 재현과 개발 비교의 순서

1. **Wu–Vallet 원방법부터 GS 없이 갱신 점군까지 재현한다.** 전체 연구의 주 대조군 역할을 유지한다. P3에서 ALS 재사용이 실제로 유효한지 먼저 살피고 P2는 후속 배제 사례로 둔다.
2. **Zhou의 재현 입력을 구체화한다.** stereo/카메라/ALS plane/NIR·지도 의존성을 공통 입력 명세와 대조한다. 코드가 없는 상태에서 간략한 점군 합성을 원방법 재현이라고 보고하지 않는다.
3. **B의 구현 가능한 우선 후보는 GeoGS다.** 원 LoD2 example 재현과 ALS 입력 변경 실험을 분리한다. GS4Buildings를 감독·schedule 차이의 보조 비교로 연결한다. 원 2DGS 재현과 gsplat 이식 여부는 실행 manifest에서 구별한다.
4. **ARSGaussian은 우선 관련 방법으로 유지하되 공식 코드 공개를 확인하고 실행 후보를 정한다.** 현재 공개 미디어는 원재현 결과가 아니다. 원문 기반 별도 재구현을 선택하면 구현 대응표와 차이를 남긴다.
5. **CL-Splats는 보존·갱신·렌더 연결의 보조 재현 후보다.** 공개 재구현과 논문 당시 구현의 대응을 먼저 감사한 후 bare ALS adapter 범위를 정한다.

각 비교는 `연구 필요성 → 기존 방법의 해결 범위 → 남는 검증 → 구체적 수정 → 기대 효과 → 실제 결과`를 한 줄 계보로 잇는다. 기대 효과 칸은 가설이며 결과 칸을 대신하지 않는다. native output에는 원점/출처 지도를 추가 표시할 수 있으나, 원방법에 없는 authority 판정값을 사후 임의로 만들어 원출력으로 기록하지 않는다.

공통 제시는 source-native 기하와 갱신 점군, 원 membership을 보존한 출처 지도, 같은 위치의 단면, 실제 카메라 렌더, 독립 평가 기하·영상 지표를 포함한다. A는 source 채택·보류/변화 판단, B는 고정된 판단 조건에서의 구조·텍스처·세부 복원을 비교하고, 전체 결과에서 둘의 오류 전파를 연결한다. ALS가 MVS보다 상대적으로 좋아 보이는 것과 ALS 자체의 현재 사용 가능성을 구분한다. 영상 MVS 기하가 없거나 쓸 수 없으면 `PRIOR` 또는 `ABSTAIN`만 검토한다.

## 5. 확인 범위와 남은 항목

| 항목 | 상태 |
|---|---|
| 다섯 논문 식별, 원입력/원산출물, 공식 repo 현황 | 확인. GeoGS 전문 세부는 공개 초록·코드 수준으로 제한 |
| Zhou·ARSGaussian·GS4Buildings·CL-Splats 원문 | 저자 원고/학회 원문 접근 및 관련 방법·실험 절 확인 |
| Zhou 공식 실행 코드 | 찾지 못함; 존재 부정 아님 |
| ARSGaussian 공식 실행 코드·dataset 링크 | 고정 tree에 미공개; README 예고만 확인 |
| GeoGS/GS4Buildings/CL-Splats 설치·실행·수치 재현 | 이 문헌 감사에서는 미실행 |
| 저자에게 코드 요청·연락 | 수행하지 않음 |
| JointBuildGS·선행 방법의 성능 우위/실패 일반화 | 판정하지 않음 |

이 문서의 공개 상태는 위 확인일과 commit의 스냅샷이다. 실제 재현을 시작할 때는 고정 commit의 재귀 submodule, 입력·모델 weight checksum, Docker 환경, 원명령/변경점, 산출물 경로와 실행 실패를 함께 기록한다.
