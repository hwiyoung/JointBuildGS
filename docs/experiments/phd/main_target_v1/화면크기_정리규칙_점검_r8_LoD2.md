# r8 LoD2 화면 크기 정리 규칙 확인

작성: 2026-11-02T21:00:18.796407+09:00 · `scientific_verdict: null` · 추가 학습 0회 · 학습 소스 변경 없음.

[이 발주에서 냄] 아래 추가 집계·검산·그림은 이번 읽기 전용 점검에서 냈다. 저장 상태와 실제 실행 소스를 읽었다. r8 LoD2는 14,030회 완료 / 14,031회 렌더 직전 중단 상태로 보존했다. 아래는 코드의 실행 순서와 측정값이다. 결론·과학적 해석은 작성하지 않았다.

## 1. 정리 규칙과 실제 코드

r22는 화면 반지름 `>20 px`, 긴 축 `>0.1 × cameras_extent`, 불투명도 `<0.05`를 정리 조건으로 둔다. 밀도 제어는 600~14,900회, 100회마다다. 화면·장면 크기 분기는 `iteration > 3000`이라 3,100회부터 켜진다. 3,000회 자체에는 크기 분기가 꺼져 있으며 이후 불투명도 초기화 주기마다 다시 꺼지는 규칙은 아니다.

저장된 `cameras_extent`는 **272.353813171387 m**, 장면 크기 문턱은 **27.235381317139 m**다. 학습 카메라 중심의 평균으로부터 최대 거리 ×1.1이며, 평가 상자의 크기가 아니다. 실제 실행 6개 줄의 카메라 중심과 범위가 같음을 확인했다. 원래 2DGS 참조·미실행 CDGS에는 실행 범위를 만들어 넣지 않았다.

화면 반지름은 학습 영상에서 보이는 행에 대해 최댓값으로 쌓는다. 하지만 `densify_and_prune`는 **복제 → 분할 → 화면 크기 비교** 순서이고, 복제·분할의 `densification_postfix`가 각각 **모든 행의 `max_radii2D`를 0으로 만든다**. 자식이 0개일 때도 이 함수 호출은 생략되지 않는다. 이 경로의 화면 비교는 0이 된 기록을 읽는다. 장면 크기·불투명도 비교는 별도 값으로 수행한다.

| 구현 / 실제 실행 | 화면 / 켜지는 반복 | 장면 문턱 m | 불투명도 | 초기화 → 화면 비교 코드 줄 |
|---|---|---|---|---|
| 기준선 항공 LiDAR (r15) / 실행 | 20 px / 3,100~14,900 | 27.235381 | 0.05 | [443](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r15/scene/gaussian_model.py:443) → [519](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r15/scene/gaussian_model.py:519) |
| 기준선 LoD2 (r15) / 실행 | 20 px / 3,100~14,900 | 27.235381 | 0.05 | [443](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r15/scene/gaussian_model.py:443) → [519](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r15/scene/gaussian_model.py:519) |
| 2DGS 영상만 / 실행 | 20 px / 3,100~14,900 | 27.235381 | 0.05 | [346](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/2d-gaussian-splatting-adapters-v1/scene/gaussian_model.py:346) → [398](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/2d-gaussian-splatting-adapters-v1/scene/gaussian_model.py:398) |
| GeoGS 항공 LiDAR / 실행 | 20 px / 3,100~14,900 | 27.235381 | 0.05 | [390](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_fix_v1/PHD-MAIN-FIX-v1/geogs/source/GeoGS-official-adapters-v1-fix1/scene/gaussian_model.py:390) → [450](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_fix_v1/PHD-MAIN-FIX-v1/geogs/source/GeoGS-official-adapters-v1-fix1/scene/gaussian_model.py:450) |
| GeoGS LoD2 / 실행 | 20 px / 3,100~14,900 | 27.235381 | 0.05 | [390](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_fix_v1/PHD-MAIN-FIX-v1/geogs/source/GeoGS-official-adapters-v1-fix1/scene/gaussian_model.py:390) → [450](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_fix_v1/PHD-MAIN-FIX-v1/geogs/source/GeoGS-official-adapters-v1-fix1/scene/gaussian_model.py:450) |
| 본 방법 r8 (r22) / 실행 | 20 px / 3,100~14,900 | 27.235381 | 0.05 | [446](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py:446) → [526](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py:526) |
| 원래 2DGS (참조) / 참조만 | 20 px / 3,100~14,900 | 실행 없음 | 0.05 | [346](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/2d-gaussian-splatting/scene/gaussian_model.py:346) → [398](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/2d-gaussian-splatting/scene/gaussian_model.py:398) |
| CDGS (학습 없음) / 준비 중단 | 20 px / 3,100~14,900 | 실행 없음 | 0.005 | [347](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/cdgs-release-adapters-v2/scene/gaussian_model.py:347) → [398](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/cdgs-release-adapters-v2/scene/gaussian_model.py:398) |

원래 2DGS는 로컬 고정 커밋 `f3e3b9fa67bbd1c75e05167ff37391d8dab2a678`의 [공식 소스](https://github.com/hbb1/2d-gaussian-splatting/blob/f3e3b9fa67bbd1c75e05167ff37391d8dab2a678/scene/gaussian_model.py#L390)를 확인했다. CDGS의 불투명도 문턱은 호출부의 0.005이며 실행된 결과로 취급하지 않았다.

r22의 줄별 근거: [화면 반지름 누적](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/train.py:1173), [20 px와 호출](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/train.py:1179), [복제·분할 먼저 호출](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py:521), [반지름 0 초기화](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py:446), [불투명도·화면·장면 정리](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/gaussian_model.py:524), [장면 범위 계산](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/forks/GeoGS-conf-guided-v1-r22/scene/dataset_readers.py:271).

최초 생성 때는 `gaussian_model.py:159` 및 목표 초기화 코드에서 0을 둔다. 완전 상태 복구 때 저장 반지름을 읽고(`gaussian_model.py:98`), 행 삭제 때는 남은 행으로 좁힌다(`:386`). 불투명도 되돌리기 함수(`:244`) 자체는 반지름을 비우지 않는다. 밀도 제어가 끝나는 15,000회 이후에는 이 누적 분기도 수행되지 않는다. 각 구현의 누적·초기화·검사 줄 전부는 `rule_evidence.json`에 있다.

## 2. 출신별 적용과 보호 마스크

| 구현 | 적용 / 예외 |
|---|---|
| 기준선 항공 LiDAR (r15) | density_exempt: density_mask 있으면 그것, 아니면 frozen_mask; protection=1, judgment=0 실제 실행 |
| 기준선 LoD2 (r15) | density_exempt: density_mask 있으면 그것, 아니면 frozen_mask; protection=1, judgment=0 실제 실행 |
| 2DGS 영상만 | 정리 예외 마스크 없음 |
| GeoGS 항공 LiDAR | 8000회 이후 building frozen_mask 정리 제외; freeze_onlybldg=1로 나머지 밀도 제어 지속 |
| GeoGS LoD2 | 8000회 이후 building frozen_mask 정리 제외; freeze_onlybldg=1로 나머지 밀도 제어 지속 |
| 본 방법 r8 (r22) | 현재 배경·패치·풀림 꼬리표별 예외 없음; 저장 frozen_mask 모두0 |
| 원래 2DGS (참조) | 정리 예외 마스크 없음 |
| CDGS (학습 없음) | 정리 예외 마스크 없음 |

r8 저장 상태 8,000~14,000회 직후 7개와 중단 상태의 `frozen_mask`는 모두 0이다. 배경·패치·풀림마다 정리 문턱을 달리 적용하는 분기는 없다. 기준선은 실제 실행 인자에서 `judgment=0`, `protection=1`이었다. 기준선 30,000회의 보호 행은 항공 LiDAR 20,992개, LoD2 41,204개다. GeoGS는 8,000회 이후 건물 보호 행을 제외하며, `freeze_onlybldg` 분기로 나머지 밀도 제어는 계속된다.

## 3. 0020 상위 1%와 저장 상태

상위 1%는 매 저장 상태의 전체 행 수를 분모로 `ceil(0.01 × N)`개를, 0020 타일 겹침 내림차순·행 번호 오름차순으로 선택했다. 중단 상태의 상위 1%와 같은 처음 씨앗 5개를 공유하는 모든 자손도 별도 줄로 냈다. 저장된 직접 부모 ID가 없으므로 과거 상태의 정확한 부모 계보를 추정하지 않았다.

**8,000~14,000회 밀도 제어 직전에는 `max_radii2D`가 저장되지 않았다.** 직전 PLY·목표 스냅숏·기울기 NPZ 모두 해당 필드가 없다. 아래 ‘없음’은 0이 아니다. 직후 완전 상태 7개에는 값이 있으며 전부 0이었다. 현재 저장 모델을 0020으로 다시 그린 반지름을 별도 참고 열에 두었다.

| 반복 / 시점 | 상위 1% 수 | 직전 저장 max 반지름 | 0020 재렌더 중앙값 px | 긴 축 중앙값 m / 문턱 비 | 장면 문턱 초과 | 그중 직후 원행 생존 |
|---|---|---|---|---|---|---|
| 8,000 직전 | 13,825 | 없음 | 1,462 | 1.6136 / 0.0592 | 21 | 0 |
| 9,000 직전 | 18,081 | 없음 | 1,994 | 1.5406 / 0.0566 | 10 | 0 |
| 10,000 직전 | 14,220 | 없음 | 165 | 1.6134 / 0.0592 | 11 | 0 |
| 11,000 직전 | 19,783 | 없음 | 3,481 | 1.5592 / 0.0573 | 6 | 0 |
| 12,000 직전 | 27,436 | 없음 | 7,210 | 1.4795 / 0.0543 | 5 | 0 |
| 13,000 직전 | 20,139 | 없음 | 7,781 | 1.4890 / 0.0547 | 2 | 0 |
| 14,000 직전 | 32,638 | 없음 | 6,935 | 1.4377 / 0.0528 | 2 | 0 |
| 14,031 중단 | 35,049 | 20 px 초과 30,151 | 6,836 | 1.4336 / 0.0526 | 2 | 다음 상태 없음 |

원행 생존은 같은 반복의 **직전 → 직후**를 비교했다. 저장 기울기·크기·불투명도와 원래 분할/정리 조건으로 남는 원행의 순서를 만들고, 직후 행 앞부분의 `init_id`를 전부 대조했다. 배경·풀림의 XYZ·원시 크기도 바이트 단위로 같았다. 패치 행은 목표 재투영이 있으므로 XYZ 동일성으로 검사하지 않았다. 분할된 부모는 원행 생존에 포함하지 않으며 자손 생존으로 바꿔 세지 않았다.

저장된 화면 기록을 기준으로 ‘20 px 초과 및 생존’인 수는 직전 값이 없어서 확인 불가다. 재렌더 반지름 >20인 원행의 직후 생존 수는 8,000회부터 차례로 13,281 / 17,303 / 13,324 / 18,319 / 25,506 / 19,775 / 32,385개다. 이 값은 과거 학습에서 쌓인 최대 반지름의 대체값이 아니다.

14,001~14,030회 구간에서 0019·0020·0043의 선택 횟수는 각각 0회다. 중단 상태는 그 30회 동안 쌓인 화면 기록을 보존했다. 상위 1%의 저장 반지름 중앙값 44 px, 20 px 초과 30,151개, 최댓값 34,204,976 px다. 14,031회 시도의 0020 반지름은 이 저장 기록에 포함되지 않는다. 다음 학습 상태는 없다.

## 4. 100회 구간 영상 선택

7,001~14,030회 영상 순서는 저장된 Python 난수 상태·남은 영상 목록·203장 순서로 재생했다. 각 1,000회 체크포인트와 마지막 중단 상태에서 다음 난수 상태와 남은 목록이 정확히 같았고, 100회마다 저장된 실제 영상 이름 70개도 모두 같았다. 학습을 재실행한 값이 아니다.

각 100회 구간의 0019·0020·0043 선택 횟수 전체는 [camera_counts_100.csv](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/tables/camera_counts_100.csv)와 같은 이름 JSON에 있다. 마지막 14,001~14,030은 30회 부분 구간이다.

해당 영상이 뽑히지 않은 구간에는 그 영상에서 나온 반지름으로 누적하지 않는다. 다른 학습 영상도 같은 가우시안의 반지름을 갱신할 수 있다. 따라서 세 영상의 미선택만으로 그 무리의 저장 반지름이 0이라고 판단할 수 없다. 100회 직전의 반지름 배열이 없어 구간별 직접 대조는 확인 불가다.

## 5. 카메라 배치와 30 m 안 가우시안

카메라 203장 중 평가 상자에서 XY 거리 50 m 초과 104장, 100 m 초과 65장, 200 m 초과 41장이다. 세 수는 중첩 누계다. 카메라 둘레 가우시안 수는 각 중심에서 **3차원 거리 30 m 이하**로 세었다. 서로 겹치는 구에 들어간 행은 카메라마다 센다.


### 기준선 LoD2 30,000 — 많은 카메라 10장

| 순위 | 카메라 | 30 m 안 가우시안 | 상자까지 XY 거리 m |
|---|---|---|---|
| 1 | DJI_20241217102537_0021_D | 99,106 | 251.756 |
| 2 | DJI_20241217102535_0020_D | 84,129 | 245.535 |
| 3 | DJI_20241217102533_0019_D | 81,787 | 241.869 |
| 4 | DJI_20241217101136_0017_D | 48,562 | 0.000 |
| 5 | DJI_20241217101140_0019_D | 48,539 | 0.000 |
| 6 | DJI_20241217101138_0018_D | 48,536 | 0.000 |
| 7 | DJI_20241217101134_0016_D | 48,514 | 0.000 |
| 8 | DJI_20241217101142_0020_D | 45,110 | 0.000 |
| 9 | DJI_20241217101128_0013_D | 43,670 | 7.504 |
| 10 | DJI_20241217093907_0027_D | 37,451 | 178.140 |

### r7 LoD2 30,000 — 많은 카메라 10장

| 순위 | 카메라 | 30 m 안 가우시안 | 상자까지 XY 거리 m |
|---|---|---|---|
| 1 | DJI_20241217102533_0019_D | 93,067 | 241.869 |
| 2 | DJI_20241217102537_0021_D | 86,516 | 251.756 |
| 3 | DJI_20241217102535_0020_D | 80,409 | 245.535 |
| 4 | DJI_20241217101138_0018_D | 43,543 | 0.000 |
| 5 | DJI_20241217101134_0016_D | 43,528 | 0.000 |
| 6 | DJI_20241217101140_0019_D | 43,527 | 0.000 |
| 7 | DJI_20241217101136_0017_D | 43,520 | 0.000 |
| 8 | DJI_20241217101142_0020_D | 40,464 | 0.000 |
| 9 | DJI_20241217101128_0013_D | 40,440 | 7.504 |
| 10 | DJI_20241217101144_0021_D | 31,459 | 0.000 |

### r8 항공 LiDAR 30,000 — 많은 카메라 10장

| 순위 | 카메라 | 30 m 안 가우시안 | 상자까지 XY 거리 m |
|---|---|---|---|
| 1 | DJI_20241217102537_0021_D | 117,891 | 251.756 |
| 2 | DJI_20241217102535_0020_D | 103,227 | 245.535 |
| 3 | DJI_20241217102533_0019_D | 100,930 | 241.869 |
| 4 | DJI_20241217101138_0018_D | 42,217 | 0.000 |
| 5 | DJI_20241217101136_0017_D | 42,188 | 0.000 |
| 6 | DJI_20241217101140_0019_D | 42,185 | 0.000 |
| 7 | DJI_20241217101134_0016_D | 42,122 | 0.000 |
| 8 | DJI_20241217101128_0013_D | 39,758 | 7.504 |
| 9 | DJI_20241217101142_0020_D | 39,022 | 0.000 |
| 10 | DJI_20241217103003_0027_D | 32,024 | 137.856 |

### r8 LoD2 중단 (14,030 완료) — 많은 카메라 10장

| 순위 | 카메라 | 30 m 안 가우시안 | 상자까지 XY 거리 m |
|---|---|---|---|
| 1 | DJI_20241217102533_0019_D | 997,080 | 241.869 |
| 2 | DJI_20241217102535_0020_D | 844,152 | 245.535 |
| 3 | DJI_20241217102537_0021_D | 563,448 | 251.756 |
| 4 | DJI_20241217101140_0019_D | 36,377 | 0.000 |
| 5 | DJI_20241217101136_0017_D | 36,376 | 0.000 |
| 6 | DJI_20241217101138_0018_D | 36,373 | 0.000 |
| 7 | DJI_20241217101134_0016_D | 36,360 | 0.000 |
| 8 | DJI_20241217101128_0013_D | 33,753 | 7.504 |
| 9 | DJI_20241217101142_0020_D | 33,707 | 0.000 |
| 10 | DJI_20241217101144_0021_D | 26,793 | 0.000 |

전체 4 × 203행은 `camera_near_gaussians.csv/json`에 있다. 독립 검산으로 상태마다 두 카메라를 전체 행과 직접 거리 비교했고 공간 트리 결과와 같았다. 상자 거리도 다른 선분 거리식으로 대조했다.

## 6. 검게 보인 무리의 깊이와 실제 색 기여

중단 상태 0020 상위 1% 35,049개의 카메라 좌표 중심 Z는 최소 0.200098 m, 중앙값 1.351868 m, 95백분위 3.950757 m, 최대 73.418910 m다. 중심이 카메라 뒤 또는 같은 깊이에 있는 수 0개, 카메라 앞 near(0~0.2 m) 안에 있는 수 0개다. 이 중심 Z와 앞서 보고한 3차원 중심 거리 중앙값 약 18 m는 다른 값이다.

원래 CUDA forward의 정렬된 타일 목록·사영 계수·불투명도·색을 읽고, 실제 합성식 `w = alpha × T`를 화소별로 재생했다. 전체 장면/선택 무리 렌더의 RGB·알파와 최대 절대 오차 2.24×10⁻⁷ 이내로 일치했다(사전 허용 오차 10⁻⁴). CUDA 코드와 학습 소스는 고치지 않았다. 전체 렌더 RGB는 앞선 저장 렌더와 바이트 단위로 같았다.

**가우시안별 최대 알파 기여가 0인 수 35,048개, 0 초과인 수 1개다.** 중앙값·95·99백분위는 모두 0이고 최댓값은 0.005350421이다. 이 1개가 453화소에서 기여했다. 무리만 그린 RGB의 최댓값은 0.001355879이다. 검게 보이는 영상이 수치적으로 전부 0인 것은 아니다.

원래 렌더러는 중심의 near 검사와 화소 광선/원반 교차 깊이의 near 검사를 따로 한다. `alpha < 1/255`는 합성하지 않고, 남은 투과율이 0.0001 미만이 되는 항부터 종료한다. 화면 타일 겹침 수는 이 최종 합성 기여와 별도로 센다. 개별 행의 중간 탈락 이유는 이번 요청의 중심 Z와 최대 기여로 대신 추정하지 않았다.

실제 코드: [중심 near 검사](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1/r8_recorded_continue/runtime/rasterizer/cuda_rasterizer/auxiliary.h:200), [교차 깊이 near 검사](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1/r8_recorded_continue/runtime/rasterizer/cuda_rasterizer/forward.cu:372), [알파 문턱과 투과율](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1/r8_recorded_continue/runtime/rasterizer/cuda_rasterizer/forward.cu:388). 전체 분포·오차는 `black_render.json`, `alpha_measure.json`, 개별 최대 기여는 외부 `alpha_replay.npz`에 있다. 초기 `black_render.json`의 ‘개별 기여 미저장’ 상태는 후속 `alpha_measure.json`의 검증된 재생 결과로 보완했다. 초기 파일의 조건부 all-zero 설명은 관측 결론으로 사용하지 않았다.

## 7. 그림


![구현별 규칙](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/figures/rule_comparison.png)


![반복별 반지름과 크기](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/figures/size_thresholds.png)


![100회 구간 영상 선택](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/figures/camera_selection_100.png)


![카메라와 평가 상자](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/figures/camera_distance.png)


![카메라 둘레 가우시안 수](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/figures/camera_near_counts.png)


![중심 깊이와 최대 알파 기여](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/screen_prune_r8_lod2/figures/depth_alpha.png)

## 8. 검증과 재계산 경계

잠금된 입력·소스 115개 SHA-256을 다시 확인했다. 원래 7,000회와 중단 상태를 보존했다. GPU는 저장 모델의 읽기 전용 forward 1회에만 사용했고 최적화 호출은 없다. 관측한 정렬 버퍼는 7,796,493,183바이트, 렌더 최대 CUDA 할당은 9,840,448,512바이트였다.

처음 범위 검산은 camera JSON을 float64로 계산해 원래 float32 행렬 역산 결과와 약 9.8 μm 달라 중단했다. 분석 드라이버 r1에서 원래 카메라 정규화의 연산 순서를 재현해 저장 범위와 정확히 일치함을 확인했다. 학습값이나 정리 문턱은 바꾸지 않았다. 실패한 첫 분석 드라이버와 잠금도 남겼다.

직전 반지름 기록, 구간별 역사 반지름, 중단 이후 상태는 확인 불가로 남겼다. 정리 코드 수정과 학습 재실행, 나머지 여섯 판 실행은 하지 않았다. ZIP에는 표·그림·JSON·분석 스크립트·설정·해시를 넣으며 대형 체크포인트·PLY는 경로와 해시로 연결한다. 패키지 무결성 검사는 과학적 판정이 아니다.
