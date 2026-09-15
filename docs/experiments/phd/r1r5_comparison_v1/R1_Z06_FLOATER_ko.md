# R1 Z06 지붕 위 플로터와 Z08 prior 해제의 관계

- 확인일: 2026-09-18.
- `scientific_verdict: null`. 입력·실행·기하 연결에 대한 진단이며 정확도/인과 효과 판정이 아니다.
- artifact: 활성 attempt의 `floater_diagnostic_20260918/`.
- 입력, 학습 결과, 마스크 및 뷰어 표시는 변경하지 않았다.

## 2026-09-18 후속: 직접 렌더 기여 확인

최종 prior0의 Gaussian row 1816099가 한 축 scale **168.43472m**로 커져
Z06 관측의 expected depth를 앞쪽으로 끌어당기는 것을 확인했다. 중심은 R1 밖이다.
세 영상의 선택 pixel에서 이 Gaussian 기여만 제외한 재합산 depth는
50.171→56.619m, 45.020→52.442m, 48.560→52.621m로 변했다.
전체 기여 CPU 재합산은 저장 CUDA depth와 최대 0.000312m 차이다.

이는 선택한 플로터 지지 ray의 직접 기여 증거이며, 아래의 과거 '렌더에서 이미
생긴 문제인지 미분리' 상태를 갱신한다. 전체 메쉬에서 해당 Gaussian을 제거한
결과는 아니다. Gaussian이 커진 학습 원인을 찾는 같은 GPU의 prior 유지/해제
실행은 실제 큐에 추가했다. [추적·복구 기록](CAUSAL_RECOVERY_20260918_ko.md)을
최신 상태로 사용하고 아래는 이전 진단 이력으로 보존한다.

## 후속 확인: 가중치 적용 전부터 수치 차이가 기록됨

사용자의 'Z08 가중치만 바꿨는데 Z06이 달라지는 것은 이상하지 않은가' 지적에
따라 실행 동일성을 추가 확인했다. **시선 교차는 가능한 영향 경로이며,
이번 플로터의 생성 원인을 입증한 결과가 아니다.** 아래 공간 진단을 원인
확정으로 해석하지 않는다.

- 같은 Anchor hash, 학습 인수, Docker image, 22,000회 camera 순서,
  image-depth 계수 0.05, 실제 TSDF voxel/truncation 설정은 일치한다.
- 실제 실행은 기존 control의 GPU 1/native allocator와 local prior0의
  GPU 0/cudaMallocAsync로 다르다. prior hook을 포함한 실행 driver도 다르다.
  이 변경들이 플로터를 만들었다고 단정하지는 않는다.
- 8,001–8,014회에 선택된 영상의 mask는 모두 0 pixel이었다. 최초 실제
  prior 해제는 8,015회 `DJI_20241217103101_0007_D`의 7,572 valid pixel이다.
- 그보다 앞선 8,010회 로그에 이미 다음 미세 차이가 있다. 값은 순간 loss가
  아니라 `0.4*current + 0.6*previous`로 기록하는 지수이동평균이다.

| 8,010회 기록 | 기존 MVS control | local prior0 |
|---|---:|---:|
| prior depth loss EMA | 8.03234 | 8.03281 |
| MVS depth loss EMA | 9.81445 | 9.81462 |

따라서 **가중치 해제 전에 수치적 실행 차이가 있었다**는 것은 확인된다.
이 작은 차이가 최종 플로터까지 확대되었는지, mask가 주요 원인인지,
둘의 상호작용인지까지 이 로그로 판정할 수는 없다.

원인 분리에 필요한 다음 대조군은 같은 GPU·allocator·driver의 mask 경로에서
prior 유지 배율 1을 적용한 실행이다. 유지/해제 조건의 짝지은 비교와 유지
조건의 반복 변동을 확인해야 mask 효과와 재현성 문제를 분리할 수 있다.
이번 확인에서는 새 GPU 학습을 시작하지 않았다.

재현: `audit_r1_control_parity.py`, Docker 확인 결과
`floater_diagnostic_20260918/control_parity_docker.json`.

## 확인한 사실

1. R1 mask 588개의 hash와 실제 학습의 mask receipt binding을 확인했다.
   해제한 픽셀은 99개 영상의 총 2,342,258개다. 각 픽셀의 prior 및 MVS depth를
   원래 K/R/t와 ray convention으로 역투영하고 기존 polygon 우선순위로 분류하면
   양쪽 endpoint 모두 전부 Z08이다. Z06 endpoint는 0개다. Z08 전체를 일괄
   해제한 것이 아니라 그 안의 검토한 C1 대응 표면을 관측하는 픽셀을 해제했다.
2. 구현은 선택 픽셀의 prior residual에만 0을 곱한다. 분모는 원래 valid prior
   pixel 수이며 바깥 배율은 1이다. R1 전체 Gaussian 모델, RGB/MVS loss,
   정규화, native protection, densification은 계속 최적화한다. Z06을 비롯한
   바깥 Gaussian을 고정하는 추가 조건은 없다.
3. 원래 대조군과 prior0의 22,000개 camera sampling 순서는 모두 같다.
   두 실행의 기록된 dynamic image-depth 계수는 모두 0.05다. 8,001회의
   camera와 loss 항들도 동일하다. 이후 prior0의 변경된 조건을 학습했다.
4. 뷰어의 hash 검증된 geometry buffer를 같은 Z06 XY 범위로 잘라 위/옆에서
   비교했다. prior0 TSDF에서 지붕 위 약 3–7m에 조각들이 보이고, 기존 MVS–GeoGS의
   해당 위치에는 같은 조각들이 거의 없다. `Z06_geometry_comparison.png`는
   실제 mesh vertex 투영이다. 가우시안 렌더 캡처 또는 정확도 지표는 아니다.

## 2D 마스크와 다른 3D 위치가 연결되는 실제 경로

플로터가 보이는 객체 좌표 상자 `u=[-40,-10], -v=[24,42], z=[-18,-12]`를
읽기 전용 진단 범위로 잡았다. 이 안에 세 꼭짓점이 모두 들어오는 표시 mesh는
3,441 정점 / 6,198 삼각형이다. 모든 masked pixel의 시선을 이 삼각형들에
raycast하면 다음과 같다.

| 시선 관례 | 교차하는 masked pixel | 해당 영상 | prior target보다 앞에서 교차 |
|---|---:|---:|---:|
| prior 생성의 +0.5 pixel | 16,336 | 11 | 16,336 |
| 정수 pixel 민감도 확인 | 16,435 | 10 | 16,435 |

즉 `카메라 → Z06 상공의 조각 → Z08 prior 대응점`으로 연결되는 시선이 실제로
있다. 마스크 생성은 입력 depth endpoint가 검토된 Z08 표면에 대응하는지를
확인했다. 손실 적용은 그 영상 픽셀의 **렌더 depth 전체**에 적용되므로 그
endpoint에 있는 Gaussian만 선택해서 prior를 끄는 동작이 아니다.

이 교차는 두 공간을 연결하는 기하 경로의 증거다. 최종 mesh의 교차만으로
학습 중 해당 Gaussian의 기여도·gradient 또는 원인별 효과 크기가 증명되지는 않는다.
이를 인과적으로 분리하려면 실제 render contribution 및 동일 실행 조건의
무개입 반복 비교가 추가로 필요하다.

## 가우시안 중심과 TSDF 표면의 구별

위 진단 상자 안의 전체 Gaussian 중심은 Anchor, 원래 MVS, prior0 모두 0개였다.
따라서 표시된 조각을 그대로 '그 위치에 새로 생긴 Gaussian 중심 덩어리'로
설명할 수 없다. Gaussian은 중심 밖까지 크기·회전·불투명도로 렌더에 기여한다.
또한 현재 `depth_ratio=0` 경로의 `surf_depth`는 누적 깊이를 alpha로 나눈
expected depth이고, TSDF는 이 깊이를 융합한다. 여러 기여가 섞인 깊이가
실제 Gaussian 중심이 없는 공간에서 표면을 만들 가능성이 있다.

이는 코드와 산출물에 부합하는 설명 후보이며, TSDF만의 오류인지 Gaussian
렌더에서 이미 생긴 깊이 문제인지까지 분리한 것은 아니다. 기존 R1 control은
GPU 1/native allocator, prior0는 GPU 0/cudaMallocAsync에서 실행했다는
실행 차이도 보존한다. 이 두 결과만으로 모든 변화가 mask 하나 때문이라고
단정하지 않는다.

## 해석

### 하늘 소실과 플로터를 분리

2026-09-18 추가 감사에서 prior0의 하늘 소실은 조건별 viewer Z crop 불일치로
확인됐다. 원본의 같은 하늘 표본 중앙값은 MVS 68.854m, prior0 66.131m이며
prior0 원본에도 높은 표면이 남아 있다. [하늘 진단](R1_SKY_COMPARISON_ko.md) 및
`sky_crop_audit_20260918/receipt.json`을 따른다. publisher v5는 기존 R1과
같은 Z `[-90,80]`을 적용한다. Z06 진단 상자의 Z `[-18,-12]`는 이전/수정
범위에 모두 들어가므로, 하늘 crop 오류가 낮은 플로터 생성 원인은 아니다.
`viewer/crop_validation_v5/receipt.json`은 기존/신규 표시의 해당 정점들을 비교한다.

**관측 픽셀의 국소 가중치와 최적화되는 3D 구조의 국소 범위는 다르다.**
Z08 endpoint만 선택했다고 해서 Z06 구조가 자동으로 보존되지는 않는다.
현재 비교는 전체 장면에서 국소 prior loss를 해제했을 때 보정과 부작용을 함께
관찰하는 실험이다. 이 플로터는 보존 구역도 평가해야 하는 구체적인 사례다.
원인을 감추기 위한 후처리 삭제나 학습 조건 변경은 하지 않았다.

재현 스크립트: `audit_r1_mask_extent.py`, `plot_z06_floater.py`, `audit_floater_rays.py`.
각 실행의 script snapshot/config/Docker command는 위 artifact에 있다.
mask endpoint의 최종 결과는 `audit_v2/mask_extent.json`, 실제 mesh 교차는
`floater_rays.json`을 사용한다. 최초 보조 진단 오류·브라우저 캡처 제한은
[이슈 기록](ISSUES_ko_v1.md)에 보존했다.
