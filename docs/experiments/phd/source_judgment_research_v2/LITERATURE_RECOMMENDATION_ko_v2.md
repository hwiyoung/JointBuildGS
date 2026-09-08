# 소스 사용성 판단 선행연구 재검토

2026-09-08 · 문헌 검토와 설계 추천 · 사용자 채택 전 후보 · `scientific_verdict: null`

## 1. 이번 검토의 기준

판단 후보는 기존 현재영상 MVS와 과거 ALS다. 판단 근거에는 원영상, 내부표정과 pose,
관측 대응, 가시성, 소스 품질과 정합 정보를 포함할 수 있다. 두 점군의 거리 비교만으로
입력을 제한하지 않는다. MVS와 원영상은 생성 계보를 공유하므로 독립 센서 두 개처럼
증거를 중복 계수하지 않는다. 평가 참조를 판단 입력으로 쓰지 않는다.

P1/P2의 현재 영상 기하 채택과 P3의 유효 ALS 보존은 검증할 기대 행동이다.
이를 방법 입력이나 정답을 강제하는 지역별 규칙으로 사용하지 않는다. 특히
영상으로 두 후보를 구별하지 못하는 것과 ALS의 현재 유효성을 확인한 것은 다르다.

기존 SRDM 결과의 구현·입력 적격성 한계와 해석 철회는
[재검토 v3](../srdm_p1p2p3_v1/IMPLEMENTATION_VALIDITY_REVIEW_ko_v3.md)를 따른다.
이 한계로 원 SRDM의 능력 자체가 실패했다고 결론 내리지 않는다.

## 2. 추천의 중심

**목적에 가장 직접적인 출발 문헌으로 Taneja, Ballan & Pollefeys (2015)의
기존 기하–현재 영상 검정을 추천한다.** 원영상과 pose로 주어진 기하의 설명력을
검사한다는 점이 이번 판단 문제에 가깝다. 공식 코드 기반의 관측 선택 비교 후보는
Schönberger et al. (2016), 관측 불확실성과 미확인 상태를 다루는 대안은
Meyer et al. (2023)이다. 세 방법을 한꺼번에 조합하자는 결정은 아니다.

이번 확인 범위에서, 과거 ALS와 기존 MVS 및 현재 다중 영상을 받아 P1/P2/P3의
소스 사용성을 수정 없이 출력한다고 추천할 수 있는 완성 방법은 확인하지 못했다.
각 문헌의 검증된 기능과 우리 입력에 필요한 변경을 아래에서 구분한다.

## 3. 우선 검토할 세 연구

### 3.1 Taneja, Ballan & Pollefeys, TPAMI 2015

**Geometric Change Detection in Urban Environments using Images**

- 입력: 기존 도시 3D 모델, 현재 파노라마 영상과 초기 pose.
- 판단: 모델을 통해 현재 영상 사이를 재투영하고 영상·건물 윤곽의 불일치를 검사한다.
  pose 정합, 모델의 작은 기하 부정확성, 넓은 baseline에서의 영상 샘플링 차이를 다룬다.
- 출력: 기하 변화의 영상·공간적 불일치 정보. ALS/MVS 소스 선택 라벨 자체가 아니다.
- 실제 검증: 지상 도시 영상의 작은 장면과 도시 규모 자료. 항공 ALS/MVS 양방향
  소스 선택이나 금속 지붕 보존의 검증으로 확대하지 않는다.
- 우리 변경: ALS와 MVS 각각을 기하 가설로 평가하고, 두 결과의 비교 및 미판정 출력을
  별도로 정의해야 한다. 파노라마·건물 벽 기반 처리를 항공 지붕 기하에 옮기는 것도 변경이다.
- 구현 상태: 이번 검색에서 공식 공개 구현을 확인하지 못했다. 논문 기반 재구현은
  원문 결과와 대응하는 검증이 필요하며, 곧바로 P1/P2/P3 장시간 실행을 권하지 않는다.

[저자 원문](https://lucaballan.altervista.org/pdfs/PAMI15.pdf),
[저자 출판 목록](https://people.inf.ethz.ch/marc.pollefeys/publications.html).
§3.4.1의 모델 오차 처리는 작은 벽 이동 가설을 비교하는 방식이며, 정합 불확실성의
완전한 확률적 추정이라고 부르지 않는다. §3.4.2는 넓은 baseline의 blur를 맞춰 비교한다.
§4.3은 강한 반사와 segmentation 오류에 의한 오탐을 직접 보고한다. 따라서 P3 금속
지붕까지 원방법이 해결한다고 추천하는 것이 아니다. 원영상으로 기하를 검정하는
출발점으로 추천하며, 반사로 생긴 불일치를 어떻게 유보할지는 남은 설계 문제다.

### 3.2 Schönberger et al., ECCV 2016 / COLMAP

**Pixelwise View Selection for Unstructured Multi-View Stereo**

- 입력: 여러 원영상, 카메라 내부표정·pose, 기하 추정 상태.
- 판단: 깊이·법선 가설의 영상 패치 일관성과 픽셀별 관측 뷰의 사용 가능성을 교대 추정한다.
  삼각측량각, 입사각, 영상 해상도 및 기하 일관성을 반영한다.
- 출력: 깊이·법선 추정과 관측 선택 정보. 관측 선택 확률은 ALS 정답 확률이 아니다.
- 우리 변경: 기존 ALS/MVS 가설을 외부 입력으로 넣고 소스 ID를 보존하는 평가 경로,
  두 후보의 공정한 비교와 유보 출력을 추가해야 한다. 전체 COLMAP 재실행은
  기존 두 소스를 검정하는 실험과 다르다.
- 구현 상태: 공식 비용·관측 선택 구현을 읽어 확인했다. 이번 세션에서 실행하지 않았다.

[저자 원문](https://demuc.de/papers/schoenberger2016mvs.pdf),
[공식 구현](https://github.com/colmap/colmap/blob/main/src/colmap/mvs/patch_match_cuda.cu).
확인한 함수는 `ComposeHomography`, `PhotoConsistencyCostComputer`,
`LikelihoodComputer::ComputeSelProb`, `ComputeTriProb`, `ComputeIncProb`,
`ComputeResolutionProb`, `ComputeGeomConsistencyCost`다. main의 현재 코드 검토이며
원 논문 당시 커밋의 재현 인증은 아니다.

무텍스처의 낮은 영상 설명력은 두 후보 모두에 생길 수 있다. 현재 MVS 깊이만을
기하 일관성 기준으로 삼으면 MVS 후보를 스스로 지지하는 비교가 되므로 주의해야 한다.

### 3.3 Meyer, Brunn & Stilla, ISPRS JPRS 2023 / Pho-to-BIM

**Geometric BIM verification of indoor construction sites by photogrammetric point clouds and evidence theory**

- 입력: 정향된 영상의 대응점·광선, sparse 점의 불확실성, dense photogrammetric
  점군, 검정할 BIM과 모델 정확도 정보.
- 판단: 해당 위치가 점유됨·비어 있음·정보 부족이라는 근거를 결합하고 모델 기하를 검정한다.
  sparse 점과 dense 점의 정확도 정보 차이를 명시적으로 구분한다.
- 출력: 모델 기하를 관측이 확인하는 정도. 완성된 ALS/MVS 선택기는 아니다.
- 실제 검증: 세 실내 공사 현장. 항공 금속 지붕과 과거 ALS의 현재성 검증은 확인되지 않았다.
- 우리 변경: BIM을 ALS/MVS 표면 가설로 바꾸고, 사용 가능한 관측의 불확실성과
  의존성을 다룰 필요가 있다. RGB 패치를 직접 재투영 비교하는 방법으로 소개하면 안 된다.
- 구현 상태: 공식 공개 구현을 이번 검색에서 확인하지 못했다.

[출판사](https://www.sciencedirect.com/science/article/pii/S092427162200329X),
[저자 기관 기록](https://portal.fis.tum.de/de/publications/geometric-bim-verification-of-indoor-construction-sites-by-photog/),
[저자 학위논문 5장](https://mediatum.ub.tum.de/doc/1690787/1690787.pdf).
학위논문 §5.1.2–5.1.3, §5.4를 직접 읽었다. dense 점의 원 관측 광선이 없으면
빈 공간 근거를 만들 수 없다는 제한이 명시되어 있다. 광선 지지는 신뢰할 수 있는
대응·기하를 전제로 하며, 임의의 MVS 오류를 자동 교정하는 증거라고 확대하지 않는다.

## 4. 소스 간 신뢰도를 직접 다루지만 첫 적용 우선순위가 낮은 연구

**Sandström et al., ECCV 2022, Learning Online Multi-Sensor Depth Fusion (SenFuNet)**는
센서별 기하·특징을 보존하고 학습된 상대 신뢰도로 융합하며 이상점을 제거한다.
복수 센서의 기하 오차·이상점 차이를 직접 다룬다는 점에서 단순 감독 마스크보다
소스 활용 판단에 가깝다. 그러나 학습과 TSDF 표현을 필요로 하고, 실내 depth stream의
오류 처리를 과거 ALS의 시간적 부적합 식별로 옮길 근거는 없다. 동기화가 불필요하다는
설명을 실제 장면이 다른 두 시기의 자료를 처리한다고 해석하면 안 된다.

[학회 원문](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920088.pdf),
[공식 코드](https://github.com/eriksandstroem/SenFuNet).

**Zhang et al. (2019)**는 old ALS-DSM, new DIM-DSM, RGB 정사영상으로 변화 여부를
학습한다. 입력 종류는 가깝지만 변화/비변화 출력이 소스별 사용성은 아니다.
[기관 원문](https://ris.utwente.nl/ws/files/171142510/remotesensing_11_02417.pdf),
[공식 코드](https://github.com/Zhenchaolibrary/PointCloud2PointCloud-Change-Detection).

**Du et al. (2016)**는 LiDAR 기하를 원영상들에 투영해 영상 간 상관과 DSM 차이를
사용한다. 다만 old images/new LiDAR라는 반대 시점이며 두 소스의 대등한 검정이 아니다.
[원문](https://www.mdpi.com/2072-4292/8/12/1030).

기존 **Wu et al. (2023)**의 품질 선택은 변화 없음으로 남은 부분에서 적용된다.
new와 충돌한 old를 먼저 제외한 뒤의 품질 선택을 P3 오류 원인 검정으로 재추천하지 않는다.
기존 Wu–Vallet 구현·평가와 SRDM의 연구상 위치는 보존한다.
[Wu 원문 §III-C·IV-A](https://arxiv.org/html/2303.07182v1).

## 5. 기존 작업과 겹치는 부분 및 남는 판단 문제

이미 [warp-NCC 코드](../../../../scripts/phd/warp_ncc_v1/run.py)는 현재 영상·pose로
MVS와 ALS 후보의 영상 일관성, 후보별 가림, 공통 영상쌍 통계, 보조 경계 비교를 계산한다.
따라서 원영상 재투영 자체를 이번에 처음 도입하는 기능으로 부르지 않는다.
NCC 함수만 COLMAP 것으로 교체하는 것도 새 판단 방법이 아니다.

문헌을 실제 시험으로 옮길 때 명확히 해야 할 추가 대상은 다음과 같다.

1. 후보의 영상 점수가 낮은 이유를 잘못된 기하와 사용할 수 없는 관측으로 구분하는 절차.
2. 후보마다 유리한 관측만 골라 이기는 것을 막는 비교 규칙과 실제 지지 관측 기록.
3. 작은 정합·모델 오차로 설명되는 차이와 큰 구조 부적합을 구별하는 검정.
4. 두 후보 모두 부적합하거나 구별 불가능할 때의 출력.

이는 아직 결정·구현·검증된 JointBuildGS 방법이 아니다. Taneja 원문의 판단 절차를
기준으로 기존 관측 진단과의 실질적인 차이를 대조하는 것이 추천하는 다음 설계 작업이다.
P3에서 잘못된 MVS의 사용을 막은 결과와 ALS의 현재 유효성을 확인한 결과를 별도로
평가한다. 관측 부족으로 ALS를 잠정 유지한 경우 이를 적극적 ALS 정답 판정으로 세지 않는다.

## 6. 확인 범위와 보존

목적에 맞춘 표적 문헌 검토이며 체계적 검색의 완전성·SOTA·신규성을 주장하지 않는다.
원문, 저자·기관 페이지와 공개 공식 코드를 사용했다. Taneja 저자 PDF의 직접 다운로드는
시간 제한으로 완료되지 않았으며, 저자 PDF의 검색 추출 본문과 관련 절을 확인했다.
전체 수식·코드 충실도 감사가 완료됐다는 뜻은 아니다. Meyer 학위논문은 임시 파일로
확보하여 해당 장을 텍스트로 읽었다. 문헌 열람 이외의 새 정합·MVS·SRDM·GS 실행은 없다.
기존 연구 계약·결정·코드·실험 산출물은 수정하지 않았다. 이 문서는 추천 후보의 추가 기록이다.
