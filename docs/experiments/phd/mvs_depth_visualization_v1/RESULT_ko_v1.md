# P1 MVS 입력 깊이와 수동 가중치 영역 후보

- 작성: 2026-09-15
- task_id: `PHD-P1-MVS-INPUT-VIS-v1`
- 상태: `PASS_INPUT_VISUALIZATION_ONLY`
- scientific_verdict: null
- 범위: 실제 입력 가시화와 수동 실험 후보 제안. 새 학습·추론·GS 렌더·표면 추출 없음.

## 결론

P1의 현재 포장 지면 A에서는 MVS가 prior보다 멀고 낮은 표면을 나타낸다. 첫 수동 실험은
이곳의 MVS 감독을 강화하고 인접 지면 B의 변화도 측정하는 구성이 적합하다.
현재 건물에만 가중치를 높이는 조건은 이 현재 지면을 감독에서 제외할 수 있으므로,
과거 상부면 감소를 검증하는 주 조건으로 삼기 어렵다. 아래 수치는 입력 차이 진단이며
정확도·철거 정답 또는 가중치의 효과를 입증한 결과는 아니다.

## 실제 그림

외부 payload resolver는
[p1_20260915.yaml](../../../../artifacts/manifests/phd/mvs_depth_visualization_v1/p1_20260915.yaml)이다.

![P1 입력 깊이](../../../../../JointBuildGS-artifacts/phase-payloads/phd/mvs_depth_visualization_v1/PHD-P1-MVS-INPUT-VIS-v1/attempt.zI9b4d/figures/P1_train_1/depth_comparison.png)

![영역 후보](../../../../../JointBuildGS-artifacts/phase-payloads/phd/mvs_depth_visualization_v1/PHD-P1-MVS-INPUT-VIS-v1/attempt.zI9b4d/figures/P1_train_1/region_candidates.png)

[입력 높이 비교](../../../../../JointBuildGS-artifacts/phase-payloads/phd/mvs_depth_visualization_v1/PHD-P1-MVS-INPUT-VIS-v1/attempt.zI9b4d/figures/P1_train_1/height_comparison.png) ·
[사선 시점](../../../../../JointBuildGS-artifacts/phase-payloads/phd/mvs_depth_visualization_v1/PHD-P1-MVS-INPUT-VIS-v1/attempt.zI9b4d/figures/P1_train_2/depth_comparison.png)

## 입력과 선정

기존 `viewer_rgb_v1/rgb_diagnostic_v1/attempt.Ym5F9Uzs/selection.json`의 입력 prism
투영 bbox 면적 상위 두 train 카메라를 재사용했다. 현재 UAS나 GS 출력으로 카메라를
재선정하지 않았다. RGB, prior NPY, MVS geometric BIN의 봉인 SHA256을 확인했다.

| 시점 | 원영상 | 동일 RGB crop [x0,y0,x1,y1) | crop 내 MVS 유효 픽셀 |
|---|---|---|---:|
| 수직에 가까운 시점 | DJI_20241217084553_0100_D.JPG | [602,259,1258,915] | 97.06% |
| 사선 시점 | DJI_20241217102955_0023_D.JPG | [484,38,1146,581] | 80.90% |

유효 비율은 finite-positive depth 존재 여부이며 confidence가 아니다. 첫 시점은 기존
PGSR neighbor graph에 이웃이 없다. MVS 생성 이웃 전체를 뜻하는 것은 아니지만,
이번 그림으로 다시점 일관성이 확인됐다고 주장할 수 없다.

Native MVS 1024×741을 현재 학습과 동일한 K 기반 nearest 조회로 RGB 1400×1013에
대응시켰다. 원값·결측을 유지했으며 실제 adapter와 표본·mask가 정확히 일치했다.
Prior는 원래의 Open3D 반 픽셀 ray convention을 유지했다. 차이 그림은 같은 저장
RGB 인덱스에서의 차이이며 MVS nearest 조회와 prior 반 픽셀 때문에 물리 ray는
완전히 같지 않다. 두 source가 동시에 유효한 픽셀에서만 차이를 계산했다.

Depth 두 패널은 각 시점 crop의 두 source를 합친 2–98 백분위로 공통 색 범위를
정했다. 범위 밖은 색만 포화하며 원값과 실제 min/max는 NPZ·receipt에 남겼다.
서로 다른 시점의 depth 색 범위는 다르다. 별도 높이 그림은 두 시점 모두
로컬 Z −50…−20m를 사용한다. CRS와 world shift는 원 입력의 EPSG:25832 계보를
유지하며, 기존의 절대 높이 datum 미확인 한계도 유지한다.

## 첫 영역 후보

모든 사각형은 첫 시점 crop의 RGB·MVS·prior 그림만 보고 선택했다.
표시와 입력 통계용이며 학습 mask·자동 분할·다시점 대응이 아니다.

| 후보 | 의미 | crop 내 bbox | MVS−prior 중앙값 | MVS 유효 비율 | 범위 |
|---|---|---|---:|---:|---|
| A | 현재 지면, prior와 큰 차이 | [180,225,260,345] | +4.316m | 100% | 기존 P1 평가 안 |
| B | 인접 지면 대조 | [160,425,230,465] | +0.011m | 100% | 기존 P1 평가 안 |
| C | 현재 주변 지붕 대조 | [360,535,470,605] | −0.020m | 98.19% | 기존 P1 평가 밖, 학습 문맥 안 |
| D | 수목 관측 제외 검토 | [390,255,470,320] | −0.425m | 95.12% | 기존 P1 평가 안 |

중앙값이 작아도 영역 전체가 일치하거나 정확하다는 뜻은 아니다. 예를 들어 C는
차이 분포의 2백분위가 약 −3.82m이며 경계·국소 차이가 존재한다. D의 유효 비율이
높아도 건물 감독에 적절한 관측이라는 뜻은 아니다. 각 source의 픽셀 수는 RGB
격자 표본 수이며 nearest 조회에 따른 native 픽셀 중복이 있다.

A에서 MVS 로컬 높이 중앙값은 −41.783m, prior는 −37.463m다.
각 영역의 전체 분포와 정확한 통계는 receipt가 정본이다.

## 다음 실험 제안

1. A의 MVS 배율만 0 / 0.25 / 1 / 4로 변경하고 B·주변 영역의 정책은 동일하게 유지한다.
2. 같은 checkpoint, prior 계수·보호, 학습량, camera 순서, 기하 항과 실제 전역 계수를 통제한다.
3. A의 현재면 회복과 과거 상부면 감소를 분리하고, B의 이동·손상을 함께 측정한다.
4. 강한 MVS에도 과거면이 남으면 같은 A에서 prior 유지/완화 × MVS 기본/강화를 비교한다.
5. C를 건물 보존 대조로 쓰려면 기존 P1 평가와 별도인 주변 진단 범위를 명시한다.

배율은 탐색 예시다. 이 문서는 학습을 실행하거나 자동 가중치·분할을 확정하지 않는다.

## 검증과 재현

- CPU 2개·메모리 4GiB, 고정 Docker image, GPU 미노출, 네트워크 없음.
- Reference·전체 artifact root 미마운트. 입력은 읽기 전용, 출력은 신규 attempt 한 곳.
- 봉인 입력 해시, camera metadata, crop, prior shape와 실제 MVS adapter 표본·결측 동일성 PASS.
- 원본 입력 재해시 PASS. 표시 그림 직접 확인 및 독립 코드/기하 검토 완료.
- 보존된 초기 그림 attempt: `rmd0yX`; 후보 초안 `W0k3Kg`; 공간 범위 검토 `PQ5CZx`;
  최종 표시/receipt 표현 보정 `zI9b4d`. 기존 attempt는 변경하지 않았다.
- 최종 `figures/receipt.json` SHA256:
  `0b87c2ec7f6fcdf3a09087a486da6b6aec6ee30150c041abcf17c860618a910d`.

재현 driver: `bash scripts/phd/mvs_depth_visualization_v1/run_p1.sh`.
각 attempt는 정확한 command, source/config snapshot, commit, package version, input/output hash를 남긴다.
