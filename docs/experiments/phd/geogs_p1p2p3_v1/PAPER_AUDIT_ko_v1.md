# GeoGS 전문 확인과 제어 실험의 해석 범위

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · 원문 및 확보 코드 감사 · `scientific_verdict: null`

이 문서는 전문을 확보한 현재 상태를 추가 기록한다. [이전 기여 감사](../geogs_contribution_v1/CONTRIBUTION_AUDIT_ko_v1.md)의 ‘전문 미확보’는 당시 접근 기록이며, 아래 내용으로 현재 해석이 갱신된다. 이전 문서·접근 영수증·CPU 진단·Wu–Vallet 결과는 수정하지 않는다. 원문 분석은 P1/P2/P3 장면 학습·렌더·메시 결과를 대신하지 않는다.

## 1. 전문의 바이트 식별과 인용

- 제목: **GeoGS: Geometric Prior-Guided Gaussian Splatting for robust urban reconstruction from sparse views**.
- 저자: Qilin Zhang, Olaf Wysocki, Boris Jutzi.
- 게재 정보: *ISPRS Journal of Photogrammetry and Remote Sensing* 240 (2026), 184–201.
- 확보 PDF: `/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf`.
- SHA-256: `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`.
- 검토 방법: 확보 파일을 `pdftotext -layout`으로 읽고 페이지별 본문·표를 대조했다. 본문의 `PDF p`는 1부터 세는 PDF 페이지, `인쇄 p`는 논문에 표시된 페이지다.
- 공식 저장소: <https://github.com/zqlin0521/GeoGS>. 확보 버전: `db40c95c657ec03ff21c83cb99cf39f4e90247a6`.

## 2. 원방법의 동작과 명시된 기본값

GeoGS는 먼저 LoD2 표면을 이용해 건물 구조를 형성하고, 그 구조를 보호하면서 영상에서 얻은 깊이와 RGB로 세부를 복원한다. 구조 깊이 손실은 표면이 prior에서 멀어지지 않도록 요구한다. 구조 보호는 선택된 Gaussian의 이동·방향·크기 변화와 개체 수 변화를 제한한다. 두 제어는 함께 작동하지만 동일한 제어가 아니다.

| 항목 | 전문에서 확인한 내용 | 근거 |
|---|---|---|
| 표현·학습량 | planar 2D Gaussian, 단일 RTX 4090, 총 30,000회 | PDF p9 / 인쇄 p192, §4.3 |
| 초기화 | LoD2 mesh의 면적 비례 표면 샘플링, raycast 가시성, 최소 k뷰 관측 조건 | PDF p4–5 / 인쇄 pp187–188, §3.2, 식5–7 |
| 구조 깊이 | 카메라부터 mesh의 첫 교차점까지 Euclidean ray distance; 교차하지 않는 픽셀 제외 | PDF p5 / 인쇄 p188, §3.3.1, 식8–9 |
| 영상 깊이 | M개 보정 영상과 카메라를 입력으로 하는 pose-conditioned DA3 | PDF p5 / 인쇄 p188, §3.3.2, 식10; PDF p9 / 인쇄 p192, §4.3 |
| anchor | 첫 8,000회, LoD2 깊이 L1 가중치 0.08, 일반 densification/pruning 활성 | PDF p6 / 인쇄 p189, §3.4.1; PDF p9 / 인쇄 p192, §4.3 |
| 보호 집합 | 초기화에 사용한 LoD2 표본과 가장 가까운 거리가 0.2m 미만인 Gaussian | PDF p6 / 인쇄 p189, 식13; PDF p9 / 인쇄 p192, §4.3 |
| 보호 방식 | 위치·회전·크기 gradient에 0.01을 곱하고 해당 primitive의 densification/pruning을 동결 | PDF p6 / 인쇄 p189, 식14; PDF p9 / 인쇄 p192, §4.3 |
| refinement | 남은 반복에서 DA3 깊이를 추가하고 약한 LoD2 깊이 anchor도 유지 | PDF p6–7 / 인쇄 pp189–190, §3.4.2, 식15–19 |
| DA3 가중치 | 초기 0.05, window 200회, 감쇠 계수 0.95 | PDF p9 / 인쇄 p192, §4.3 |
| 적응 감쇠 조건 | visual depth 손실이 불안정하게 증가하지 않으며 RGB 손실이 개선될 때 감쇠 | PDF p6–7 / 인쇄 pp189–190, 식17–19, Fig5 |

논문의 ‘geometry stability’는 최적화 중 visual-depth 손실 추세에 대한 설명이다. 독립 참조로 prior의 현재성·절대 정확성을 판단하는 검정이 아니다. 또한 gradient를 0.01배로 만드는 것과 Adam의 실제 위치 갱신을 정확히 1/100로 만드는 것은 다르다. 이 구현 의미는 이전 CPU 진단에서 이미 구분했다.

### 원문 수치와 코드 수치를 구분한다

확보 로컬 원본은 `../JointBuildGS-artifacts/phase-payloads/phd/geogs_contribution_v1/PHD-GEOGS-CONTRIBUTION-v1/sources/GeoGS/`다. 이 문서 작성 시 `train.py` SHA-256은 `4c09f6a117d7f4a13e3bd3c5d9eb49b1830e428950a53c0f86be4001637c7a10`이며 기존 probe 설정과 일치했다. 전체 source-tree 동일성은 별도 버전 감사에서 확인한다.

- `train.py:1267–1268`은 anchor `--lambda_lod_init=0.08`, refinement `--lambda_lod_anchor=0.005`를 기본값으로 선언한다. **0.005는 확보 코드로 확인한 수치**다. 전문 §4.3은 refinement LoD2 계수를 수치로 명시하지 않는다.
- `train.py:603–638`의 hook은 위치·회전·크기 gradient를 감쇠한다. SH·opacity를 모두 고정하는 제어라고 표현하지 않는다.
- `scene/gaussian_model.py:63–98`의 `capture/restore`는 model tensor·optimizer 등을 보존하지만 `frozen_mask`, `completed_mask`, gradient hook, 전체 trainer/RNG 상태를 포함하는 완전 실행 상태 저장 계약은 아니다. 기본 checkpoint만으로 동일 anchor 이후 실험이 보장된다고 주장하지 않는다.
- 논문은 seed·훈련 영상 해상도·표면 표본 수·TSDF voxel/truncation 설정을 충분히 수치화하지 않는다. 확보 코드·예제·실제 실행 config에서 명시해야 한다.

## 3. 오류·부분 결손 prior 실험은 이미 수행됐다

**PDF p16 / 인쇄 p199, §5.5 및 Table7**은 TUM2TWIN Region1의 학습 13뷰 조건에서 다음을 검사한다. 아래는 논문에 보고된 수치이며 이번 프로젝트의 측정치가 아니다. 3D 지표는 TSDF로 추출한 mesh에서 계산했다.

| LoD2 조건 | PSNR ↑ | SSIM ↑ | LPIPS ↓ | M3C2 m ↓ | F1@0.2m ↑ | F1@0.5m ↑ |
|---|---:|---:|---:|---:|---:|---:|
| Nominal | 16.654 | 0.527 | 0.266 | 0.378 | 0.469 | 0.788 |
| 높이 +0.25m | 16.617 | 0.521 | 0.382 | 0.384 | 0.447 | 0.787 |
| 높이 +0.50m | 16.312 | 0.519 | 0.385 | 0.387 | 0.448 | 0.785 |
| 높이 +1.00m | 15.866 | 0.510 | 0.395 | 0.387 | 0.451 | 0.787 |
| 수평 이동 0.50m | 15.733 | 0.508 | 0.391 | 0.383 | 0.457 | 0.788 |
| 부분 결손 | 16.488 | 0.519 | 0.384 | 0.380 | 0.457 | 0.785 |

부분 결손은 대상 영역의 일부 building surface를 수동 제거해서 만든다. 구조를 변형한 뒤 **초기점과 구조 깊이를 다시 생성**하므로, 같은 anchor 이후 refinement 제어만 달리한 실험은 아니다. 제거 면의 정확한 목록·비율은 본문에서 확인되지 않는다. pose 실험은 중심 translation σ=0.10m, random-axis rotation σ=0.50° 및 둘의 조합이며, 내참수는 유지하고 pose에 의존하는 prior를 다시 생성한다.

저자의 해석은 시험 범위에서 건물 규모 3D 구조가 비교적 안정적이나, prior 오류가 커지면 외관과 국소 정합이 더 악화한다는 것이다. 위 결과는 GeoGS가 불완전·부정확한 prior를 전혀 다루지 않았다는 주장을 배제한다. 한편 실제 시간차의 철거·신축·과거 구조 잔존을 구역별로 확인한 결과이거나, raw ALS 변환의 강건성 결과라고 확대할 수도 없다.

## 4. 보호 완화의 이득을 미리 가정하지 않는다

**PDF p15 / 인쇄 p198, §5.4 및 Table6 PartB**의 Region1 결과다.

| 조건 | PSNR ↑ | SSIM ↑ | LPIPS ↓ | M3C2 m ↓ | F1@0.2m ↑ | F1@0.5m ↑ |
|---|---:|---:|---:|---:|---:|---:|
| Full GeoGS | 16.654 | 0.527 | 0.266 | 0.378 | 0.469 | 0.788 |
| w/o LoD Depth Prior | 16.436 | 0.518 | 0.279 | 0.390 | 0.451 | 0.780 |
| w/o Geometry Protection | 16.165 | 0.516 | 0.271 | 0.389 | 0.451 | 0.775 |

이 장면에서는 깊이 prior 제거와 보호 제거 모두 악화했다. 원문의 이득을 인정하면서 우리 시간차·ALS 변환 조건에서 수정 필요한 구조와 유지할 구조를 따로 확인한다. 원문은 이 ablation이 동일한 완전 anchor checkpoint에서 분기했는지 명시하지 않으므로, 우리의 분기 실험과 같다고 하지 않는다.

Table6 PartD에는 기본 F1@0.2m가 0.459로 기재되어 같은 표 다른 Part의 0.469와 불일치한다. 새 실험의 기준값·허용오차로 이 값을 무비판적으로 복사하지 않는다.

## 5. 평가와 한계에 관한 원문 근거

PDF p9 / 인쇄 p192, §4.2는 독립 평가 시점의 PSNR·SSIM·LPIPS, 양방향 Chamfer distance, M3C2, F1@0.2/0.5m를 사용한다. PDF p11 / 인쇄 p194, §5.2는 **Gaussian 중심점과 TSDF 표면을 따로** 평가한다. Fig9는 동일 지역의 원사진·LiDAR·점군·mesh·M3C2 지도를 함께 제공한다. 좋은 2D 결과만으로 좋은 3D 구조를 보장할 수 없다는 논의는 PDF p16 / 인쇄 p199, §6에 명시되어 있다.

DA3 식10은 전체 M개 영상 입력을 기술하지만 실제 train/eval membership을 제공하지 않는다. 전문만으로 평가 영상의 DA3 입력 포함 여부를 확정하거나 저자의 평가 누출을 단정하지 않는다. 새 실험은 RGB 학습·평가뿐 아니라 초기화 가시성·DA3·영상 기하 생성의 이미지 ID와 실제 바이트를 명시한다.

PDF p17 / 인쇄 p200, §6의 명시적 한계는 다음과 같다.

- 큰 pose 오차와 강하게 오정합된 LoD2는 부정확한 depth anchoring과 최적화 저하를 일으킬 수 있다. joint pose refinement와 adaptive LoD2 correction을 후속 방향으로 제안한다.
- 건물 외 ground·vegetation·street furniture·차량 등은 LoD2 초기화와 구조 보호를 받지 않아 덜 완전하거나 artifact가 남을 수 있다.
- 분산 city-scale 실행과 체계적인 시간·메모리 평가는 후속 과제다. Table5의 Region1 36분14초는 우리 P1/P2/P3의 예상 시간이나 상한이 아니다.

## 6. 이번 실험에서 허용되는 연결

먼저 같은 anchor에서 깊이 계수와 구조 보호를 별도로 달리하여 실제 표면·외관의 개선·유지·악화를 관찰한다. 다음으로 ALS 표면 변환, 초기화와 anchor, refinement 제어, 추출 표면의 영향을 구분한다. 그 관찰을 위 원문 성과·한계와 대조한 뒤 추가 수정이 필요한지를 논의한다.

refinement prior 깊이를 0으로 만들더라도 초기화·anchor와 보호의 prior 영향은 남을 수 있다. 모든 refinement 보호를 해제해도 이미 형성된 anchor의 영향은 남는다. 어느 경우도 image-only라고 이름 붙이지 않는다. 제약 완화로 회복했다는 관찰은 반복 재판단의 필요성이나 추가 효과를 입증하지 않는다. 그 주장은 향후 동일 판단을 한 번만 적용한 조건과 별도로 비교할 문제다.
