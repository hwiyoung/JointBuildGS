# SRDM 두 단계 재구현 대응과 사전 선택

2026-09-08 · `PHD-SRDM-P1P2P3-v1` · `scientific_verdict: null`

본 구현은 공식 저자 코드가 아닌 논문 기반 재구현이다. 아래 설정은 실제 지역의 SRDM 기하 결과·UAS 점수를 보기 전에 정했다. 판정·최종 결과에 따라 지역별 설정을 고르지 않는다.

## 원문과 구현의 대응

| 원문 | 구현 |
|---|---|
| §3.1 ALS의 epipolar 시차 투영, 충돌 시 가까운 점 선택 | 보정된 두 카메라 정류, 양뷰 원 ALS z-buffer, 원 점/파일 ID 대응. 과거 ALS만으로 current visibility를 추정했다고 해석하지 않음 |
| 식6 Census+HOG | 5×5 Census, Sobel 방향의 12-bin·5×5 count histogram, 각각 절단·정규화한 비용의 가중 결합 |
| 식11·13–17 improved INM / non-local paths | 시차 ±1 이동 허용, 영상 밝기 기반 전파, 네 방향의 직교 양방향 전파와 중복 비용 보정 |
| 식18·19 약한 prior 유도와 불일치 제거 | 동일 정합기, 약한 prior 비용, 좌우 일관성이 있는 매칭에서 시차 차이 2px를 넘는 ALS 표시 |
| 식21·22 강한 prior 복원 | 유사 밝기 이웃 ALS에서 탐색 구간 생성, 남은 prior의 절단 비용 적용, quadratic subpixel 추정과 좌우 일관성 검사 |

원문 출처: [SRDM2018](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf), [인용된 HOG 논문2016 §2.1](https://isprs-annals.copernicus.org/articles/III-3/67/2016/isprs-annals-III-3-67-2016.pdf).

## 원형 전체와 동일하지 않은 부분

- 원논문이 인용한 별도 카메라–LiDAR 재정합은 이번에 수행하지 않는다. 기존 봉인 카메라/ALS 좌표를 유지하는 입력 변형이다. 잔여 정합 오차와 시간차를 이 구현이 자동으로 분리하지 않는다.
- 별도로 인용된 histogram blunder 전처리는 첫 적용에서 재구현하지 않았다. 모든 조건에 같은 원 ALS를 공급한다. 이를 포함한 원형 전체 재현으로 부르지 않는다.
- HOG2016은 histogram 정규화를 서술하나 SRDM2018은 5×5 histogram 최대50의 60%인 절단값30을 제시한다. `count_l1`는 후자의 비용 스케일에 맞춘 해석이며 저자 구현과 동일함을 확인한 값이 아니다. 이 모호성이 실제 결과의 한계다.
- 약한 단계의 피라미드 축소는 1배로 두어 원해상도에서 판단한다. 2px는 실제 계산 영상의 픽셀이다. 최종 optional TIN 보간은 세 조건 모두 끈다. 관측된 정합점과 보간으로 채운 점의 혼동을 피하고, 원형에서 선택 가능한 보간의 추가 효과는 이번에 측정하지 않는다.
- 좌우 일관성 검사를 통과하지 못한 ALS 픽셀은 `unassessed`로 표시하고 후단 감독에서 제외한다. 원문은 mismatch/occlusion 제거를 기술하지만 이 상태의 정확한 상속 규칙은 명시하지 않는다. 따라서 `FILTER_OFF → SRDM_NATIVE`는 2px 불일치 제거와 판정 불가 감독 제외를 합친 효과다. 2px 문턱 단독 효과로 해석하지 않는다.
- `unassessed`는 소스 선택의 완성된 유보 알고리즘이 아니라 이번 stereo pair에서 판정하지 못했다는 상태다. 이를 실제로 틀린 ALS나 시기 변화로 분류하지 않는다.
- 우영상 prior는 같은 ALS 점의 실제 우영상 투영으로 생성한다. 반올림한 좌영상 픽셀을 다시 옮겨 생기는 1px 차이를 피한다. 두 영상에서 약한 매칭·좌우 검사를 통해 생존 여부는 각각 계산하며, 이 `view-local decisions` 정책은 원문에 상세히 명시되지 않은 재구현 선택이다.
- 한 쌍의 stereo, native 크기의 정류, 고정 3D ROI에 기반한 전역 탐색 범위를 사용한다. 영상만 조건도 같은 실험 영역/카메라 범위를 받으며 ALS 점 시차로 탐색 범위를 정하지 않는다. 기존 ROI 자체의 역사적 계보는 유지한다.

## 설정 출처

원문에 기술된 값은 penalty0.4, 전파 sigma10, Census/HOG 가중0.5, 절단값15/30, 불일치2px, 네 방향0/45/90/135이다. 원문에 명시되지 않은 값은 weak sigma2px, 탐색 반경15px, 밝기 차이 허용10(0–255), 탐색 확장/절단 gamma2px, 좌우 허용차1px로 공통 고정했다. 경계 밖·정류 무효·특징 지원 부족 픽셀을 제외하고 그 경계를 가로지르는 경로는 재시작한다. 수치 안정화를 위한 label-independent 최소값 제거는 argmin을 보존한다.

실제 설정은 각 지역의 `execution_config.json` 및 `receipt.json/core_metadata`와 실행 source snapshot에 기록한다. `SRDM_NATIVE`는 이 두 단계 재구현을 식별하는 내부 조건명이며 저자 공식 원결과라는 뜻이 아니다. 오류가 관찰되어도 원 SRDM의 일반적 실패라고 확대하지 않는다.

저장 자원 복구: P1/P2는6개 비용 배열을 RAM에 두고, P3는2개 사진 비용을 읽기용 파일·4개 반복 DP 배열을 RAM에 둔다. 동일 float32 산술과 C++ backend를 사용하며 합성 입력에서 세 저장 방식의 전체 최종 배열이 byte-exact였다. 실제 지역의 모든 저장 방식 비교를 수행한 것은 아니다. 첫 memmap 실행 중단은 이슈 기록과 별도 보존 attempt에 남긴다.
