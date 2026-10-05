# R1 보정·보존 관찰 구역 초안과 기본 MVS–GeoGS 대조군 준비

- 작업: `PHD-R1-MVS-CONTROL-PREP-v1`, 2026-09-16
- 상태: **PASS — CPU 입력·구역 초안·실행 설정 준비**. GPU 사전 점검/학습은 미실행.
- `scientific_verdict: null`, 학습 실행 0회, 수동 가중치 배열 0개.
- 순서: **관찰 구역 초안 → 기본 대조군 실행·동작 확인 → 수동 가중치 비교**.

## 1. 이번에 잡은 구역

대상은 승인된 **R1 중앙 안뜰·연결동·곡면지붕**이다. 기존 P1/P3를 포함하며 객체축 기준 `u=[-135,70]m`, `v=[-65,35]m`이다. CRS는 EPSG:25832, local shift는 `[690953,5336071,604]`, u축은 easting에서 반시계 70°다. 초기 기하는 바깥으로 25m 문맥을 포함한다.

| 후보 | 실제 위치와 관찰 목적 | 원본 영상 | 객체축 u/v 범위(m, 표면 점의 외접 범위) |
|---|---|---|---|
| C1 보정 후보 | 중앙 안뜰 지면. 과거 상부 표면에 끌려 남는 구조가 현재 관측에 맞게 보정되는지 | `DJI_20241217084553_0100_D.JPG` | u −38.19~−4.73 / v −12.81~20.34 |
| S1 보존 후보 | 안뜰 옆 긴 곡면지붕의 내부 띠. 입력이 함께 일치하는 지붕이 불필요하게 변형되는지 | `DJI_20241217103039_0045_D.JPG` | u −46.15~−4.25 / v −39.81~−34.63 |
| U1 판단 유보 | 같은 건물 전면 외벽. 희소 ALS의 빈 부분·뒤쪽 표면과 현재 외벽 관측이 섞이는 곳 | 같은 `0045_D` | u −46.34~−3.93 / v −42.27~−39.54 |

이 범위는 **관찰할 표면의 위치**이며 외접 박스 전체에 동일 판단을 부여하지 않는다. 미표시 영역은 미검토다. C1 그림의 외곽선 안에서도 차량·장비 등은 기존 입력 기반 의미 제외를 상속한 실제 점 집합에서 제외된다.

**현재 유효한 초안은 `configs/phd/r1_mvs_control_v1/observation_draft_v1.json`이다.** 초기 준비 설정의 observation_draft 항목은 이 파일로 대체됐다. 기존 P3에서 보던 `0046_D`는 새 R1의 평가 목록에 들어가므로 인접 학습 영상 `0045_D`로 초안을 작성했고, split은 바꾸지 않았다. 초기 평가 영상 열람 사실은 이슈 R1P-005에 남겼다.

## 2. 입력에서 확인한 차이와 지지

MVS와 ALS를 **동일한 native 픽셀 광선**에서 비교했다. 아래는 카메라 Z 깊이 차이로, 수직 높이 오차나 독립 기준 정확도가 아니다.

| 후보 | 선택된 현재 MVS 표면 점 | 그중 prior 깊이 존재 | 깊이 절대차 중앙값 / 90분위 | 두 깊이 차이 ≤0.5m |
|---|---:|---:|---:|---:|
| C1 | 60,438 | 60,438 | 3.779 / 4.840m | 0.00% |
| S1 | 25,932 | 25,932 | 0.042 / 0.169m | 99.96% |
| U1 | 84,723 | 51,791 | 25.410 / 32.822m | 3.09% |

각 후보의 고정 표면 ID에서 균등하게 최대 4,096점을 추출해 **나머지 학습 영상 587장**을 조회했다. 깊이 차이 ≤0.5m와 원본 카메라로 되돌린 오차 ≤2 native pixel을 함께 요구했다.

| 후보 | 점당 다른 지지 영상 수 중앙값 | 다른 지지 영상 3장 이상인 점 |
|---|---:|---:|
| C1 | 23장 | 100% |
| S1 | 49장 | 100% |
| U1 | 52장 | 100% |

이는 **표본의 입력 지지**이며 독립 시점 수, 실제 학습 loss/gradient 기여 수 또는 정확도는 아니다. 전체 점 집합과 표본 ID를 각각 저장했다. 과거 P1의 작은 영역과 같은 표면을 보는 영상이 부족했던 상황을 R1에서 그대로 전제할 필요는 없다.

S1은 우선 **prior와 MVS가 함께 일치하는 쉬운 보존 후보**다. 독립 현재 기준으로 정확성을 확인해야 보존 성능을 말할 수 있다. prior가 맞고 MVS가 틀리는 어려운 보존 사례는 아직 확정하지 않았다. C1도 실제 변화의 원인/시점을 확정한 GT 라벨은 아니다. U1의 큰 차이는 외벽 자체의 25m 오차라는 뜻이 아니다. prior ray가 외벽을 놓쳐 뒤 표면에 닿는 경우가 포함된다.

## 3. 준비된 대조군

| 항목 | 준비 내용 |
|---|---|
| 조건 | `R1_MVS_D005_Pnative`, ALS를 적용한 GeoGS 개발 대조군 |
| 영상 | 전체 672장 = 학습 588장 + 평가 84장, 기존 R1 목록 유지 |
| 영상 깊이 | 학습 영상의 기존 COLMAP geometric MVS, metric camera-Z, 깊이 배율 맞춤/구멍 보간 없음 |
| ALS 표면 | 원본 ALS 4개 파일에서 R1+25m 문맥 재구축; 801,770점, 1,284,340삼각형 |
| 초기 점군 | ALS 표면 샘플 100,000개 중 학습 영상 2장 이상에서 보이는 96,106개. 초기화와 보호 점군은 동일 바이트 |
| 스케줄 | 새 R1 초기화 → 8,000회 완전 상태 저장 → 동일 상태에서 30,000회까지 기본 MVS refinement |
| prior 계수 | 초기 0.08, refinement 0.005 |
| MVS 계수 | 초기 설정 0.05, 기존 동적 제어 유지. 실제 계수는 실행 trace로 확인 |
| 보호·정규화 | 기존 GeoGS 보호 및 normal regularizer 유지 |
| 추가 기능 | PGSR·수동 가중치·추가 Gaussian completion 없음 |
| 카메라 규모 | radius 221.025m, `percent_dense=.01`의 clone/split 경계 2.210m |

이 조건은 이미지 전용 조건이 아니며 공식 GeoGS 논문의 원본 재현도 아니다. 정규 gsplat E1–E6 정의는 변경하지 않는다. 기존 P1/P3 checkpoint는 새 R1에 재사용하지 않는다.

초기화는 원 GeoGS 면적 비례 샘플러와 5px 영상 여유, 0.05m 최근접 ray 가시성, 최소 2개 학습 영상 규칙을 썼다. projection을 벡터화하고 75,264개 검사에서 원 함수와 일치시켰다. GeoGS가 읽는 PLY에는 영향을 주지 않는 합성 COLMAP track 조립은 생략했다. ALS 수직 이동 45.7m는 기존 입력 변환을 상속하며 새 수직 기준 검증은 아니다.

실행 설정은 `runtime_v1.json`, 실제 바인딩과 명령 배열은 외부 payload의 `runtime/execution_plan.json`에 있다. 실행을 시작하는 코드는 호출하지 않았다. `/weights`는 다음 기존 로컬 디렉터리를 읽기 전용으로 연결하면 된다:

`phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights`

## 4. 검증 결과와 남은 실행 확인

CPU Docker에서 다음 검사를 통과했다.

- 봉인 입력 2,473개, 총 9,192,551,927 bytes의 크기/SHA256 일치.
- 실제 COLMAP 카메라 자세·내부 표정, 588/84 분리 및 every-eighth 평가 규칙 일치.
- 588개 MVS RGB-grid 깊이 배열이 원본 native 깊이로부터 다시 변환한 값과 전부 정확히 일치.
- 초기화/보호/scene PLY 동일, retained point ID와 최소 2-view 가시성 bitset 일치.
- anchor/refinement source가 기존 source provenance의 부모/준비 해시와 일치, Python 구문 검사 통과.
- 구역 초안 C1/S1/U1의 최종 원본 영상이 전부 학습 목록에 포함됨.

**GPU 메모리·유한 loss/gradient·실제 카메라 sampling·Anchor 완전 상태 복원은 아직 확인하지 않았다.** RGB는 원래 전체 프레임이고 기하는 유한한 25m 문맥이므로 경계/원경 불일치를 사전 실행에서 점검해야 한다. 입력의 유효 영상 수를 실제 구역 loss 기여 영상 수로 바꾸어 말하지 않는다. 학습을 실행할 때 이를 관찰하고, 기본 결과를 보정과 보존으로 나눠 확인한 뒤 수동 가중치를 정한다.

기존 MVS 생산에는 평가 영상이 포함돼 있다. 이번 split/초안/대조군은 개발용이고 독립 정확도 평가나 과학적 결론이 아니다. UAS/LoD2 reference geometry는 이번 준비 컨테이너에 제공하지 않았다.

## 5. 결과 위치와 재현

Resolver: `artifacts/manifests/phd/r1_mvs_control_v1/manifest_v1.yaml`.

외부 task root:

`../JointBuildGS-artifacts/phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1/attempt_20260916T130151Z_jm4gu7vc`

| 상대 경로 | 내용 |
|---|---|
| `result/input/` | 봉인된 scene, MVS, ALS prior, 초기화 입력 |
| `review_20260916T131111Z_U24q6NUr/result/R1_observation_draft.png` | 영상 위 C1/S1/U1 초안 |
| 같은 디렉터리 `R1_plan_draft.png` | 객체축 R1 배치도 |
| 같은 디렉터리 `R1_input_depth_diagnostic.png` | MVS/prior/차이 그림 |
| 같은 디렉터리 `C1_source_points.npz`, `S1_source_points.npz`, `U1_source_points.npz` | 정확한 표면 점·원본 픽셀·관찰 표본 ID |
| `finalize_20260916T131410Z_ZpnUStaZ/runtime/` | source 복사본, 최종 MVS 바인딩, 실행 명령 배열, 검증 receipt |

재현은 저장된 각 `command.sh`와 `source/`를 기준으로 한다. 신규 시도는 저장된 결과를 덮어쓰지 않고 아래 CPU 준비 드라이버로 만들 수 있다.

```bash
bash scripts/phd/r1_mvs_control_v1/run_prepare.sh
bash scripts/phd/r1_mvs_control_v1/run_review.sh <새 preparation attempt 절대경로>
bash scripts/phd/r1_mvs_control_v1/run_finalize.sh <새 preparation attempt 절대경로>
```

수동 가중치 전에는 이 관찰 초안을 고정해 기본 대조군의 보정·보존 실패를 확인한다. 이후 가중치 비교에는 같은 R1 입력, 같은 Anchor8k, 같은 보호 규칙과 반복 수를 사용한다.
