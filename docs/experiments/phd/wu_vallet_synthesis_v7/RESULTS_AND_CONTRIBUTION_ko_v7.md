# P1·P2·P3 종합 결과와 연구 기여의 성립 조건

2026-09-07 · `PHD-WU-VALLET-SYNTHESIS-v7` · `scientific_verdict: null`

**Wu–Vallet의 잔여 문제는 연구 질문을 구체화하는 근거다. 그것만으로 문헌 전체의 공백이나 우리 방법의 신규성을 입증하지는 못한다.** 저자의 future work를 구현한다는 사실도 신규성의 증거가 아니다. 기존 연구가 이미 해결한 기능과 강한 조합을 먼저 인정하고, 같은 정보 조건에서 남는 문제와 수정의 실제 추가 효과를 확인한다.

이번에는 완료한 **동등조건 v5**의 세 구역을 다시 분석했다. 새 갱신 실행은 0회이며, 봉인된 점군·판정 마스크·UAS 거리·정량 결과에서 출처별 진단을 검산하고 종합 그림과 CSV를 만들었다. 아래 Wu는 **원문 기반 재구현**이다. 저자 코드·PSMNet·실측 ALS 궤적·정확한 저자 ray predicate와 동일한 전체 재현은 아니다. 다른 논문은 문헌·공식 코드 범위를 검토했으며 이 세 구역에서 새로 실행하지 않았다.

## 1. 같은 조건의 정량 결과

각 지역의 ALS·영상 단독·합집합·Wu는 동일한 원점 입력을 사용했다. 전체 고정 뷰에 같은 영상 메시 XY 지원 최대 규칙을 적용했다(선택 영상 ID / 후보 뷰 수: P1 90 / 113, P2 296 / 66, P3 134 / 157). UAS를 후보 생성·선택·정합·파라미터 결정에 사용하지 않고, 결과 봉인 뒤 세 지역 모두 동일 UAS 참조로 평가했다. 기본 Wu 조건은 작은 변화 영역 1m² 정제다.

아래 F1은 **0.5m 이내 최근접 3D 거리의 precision/recall 조화평균**이다. 출력점 비율과 참조점 비율의 분모가 다르며 원점 밀도의 영향을 받는다. 변화 검출 F1, 건물 성공률, 공식 절대 정확도가 아니다. 거리 평균은 출력→UAS / UAS→출력 순서이며 작을수록 좋다. 후자는 참조 피복을 얼마나 재현하는지에도 영향을 받는다.

| 지역 | 방법 | 거리 F1@0.5m (%) | 평균 거리 정방향 / 역방향 (m) | 참조가 있으나 출력이 없는 0.5m XY 셀 |
|---|---|---:|---:|---:|
| P1 | ALS | 61.84 | 1.082 / 1.297 | 0 / 3,600 |
| P1 | 영상 | 91.89 | 0.068 / 0.314 | 92 / 3,600 |
| P1 | 합집합 | 94.69 | 0.277 / 0.115 | 0 / 3,600 |
| P1 | Wu | **96.95** | **0.119 / 0.151** | 1 / 3,600 |
| P2 | ALS | 52.04 | 1.706 / 1.324 | 12 / 8,799 |
| P2 | 영상 | 90.46 | 0.101 / 0.854 | 1,059 / 8,799 |
| P2 | 합집합 | 92.91 | 0.368 / 0.142 | 0 / 8,799 |
| P2 | Wu | **93.50** | **0.268 / 0.163** | 12 / 8,799 |
| P3 | ALS | 90.14 | 0.136 / 0.309 | 11 / 8,633 |
| P3 | 영상 | 65.59 | 0.310 / 1.270 | 2,077 / 8,633 |
| P3 | 합집합 | 90.44 | 0.265 / 0.251 | 7 / 8,633 |
| P3 | Wu | **86.17** | **0.467 / 0.294** | 166 / 8,633 |

- **P1:** Wu의 F1 증가는 ALS 대비 +35.10%p, 영상 대비 +5.05%p, 합집합 대비 +2.26%p다. 영상 자체의 개선과 선택 갱신의 추가 효과를 구분한다.
- **P2:** 각각 +41.45 / +3.04 / +0.58%p다. 전체 F1은 높지만 영상 단독보다 출력→UAS 평균 편차가 크다. ALS가 영상 결손을 보완하면서 잔여 과거 표면도 남기는 상충이 있다.
- **P3:** ALS 대비 −3.97%p, 합집합 대비 −4.26%p다. 영상 단독보다는 +20.59%p로 보완 효과가 있으나, 기본 설정은 기존 ALS를 악화시킨다. 역방향 평균만 보면 ALS보다 조금 개선되므로 모든 지표가 악화된 것은 아니다.

![세 지역 정량 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_synthesis_v7/PHD-WU-VALLET-SYNTHESIS-v7-r2/run/three_region_summary.png)

[전체 CSV](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_synthesis_v7/PHD-WU-VALLET-SYNTHESIS-v7-r2/run/metrics.csv) · [그림 PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_synthesis_v7/PHD-WU-VALLET-SYNTHESIS-v7-r2/run/three_region_summary.pdf).

현재 제작계열이 다른 OpenMVS 문맥 자료의 F1은 P1 93.40/P2 90.59/P3 87.22%다. 뷰어에서 참고할 수 있지만, 이를 위 표의 동일 영상 입력 대조군과 바꿔 쓰지 않는다.

### 정제 설정 민감도

| 작은 변화영역 기준 | P1 F1 (%) | P2 F1 (%) | P3 F1 (%) |
|---|---:|---:|---:|
| 0m² | 96.74 | 93.57 | 83.70 |
| 0.25m² | 96.85 | 93.53 | 84.79 |
| 1m² | 96.95 | 93.50 | 86.17 |
| 4m² | 97.04 | 93.53 | **90.07** |
| 1m² + 새 점은 changed만 허용 | 95.99 | 86.77 | 85.18 |

P3는 4m²에서 **F1이** ALS 90.14%에 근접한다. 그러나 출력→UAS 평균은 0.196m로 ALS의 0.136m보다 크고, 빈 XY 셀도 125개로 ALS의 11개보다 많다. 전체 품질이 회복됐다고 요약하지 않는다. 이것은 정제 민감도의 증거이며, UAS를 보고 최적값을 고른 독립 성능 주장이 아니다. 단순히 새 single을 금지하면 P2 피복도 크게 나빠진다. “작은 영역 필터를 강화/추가하면 해결된다”, “비관측은 모두 버리면 된다”는 주장을 먼저 검증해야 한다. 원문에서 명시하지 않은 정확한 면적값·연결 규칙은 우리의 공개된 구현 선택이다.

## 2. 출처와 단면으로 본 개선·잔여 문제

| 진단값 (기본 1m²) | P1 | P2 | P3 |
|---|---:|---:|---:|
| ALS 유지 / 삭제 | 12,937 / 7,252 | 32,553 / 13,433 | 45,542 / 7,220 |
| 영상점 추가 | 34,844 | 147,592 | 32,196 |
| UAS>2m인 ALS: 갱신 전 → 유지 | 4,923 → 411 | 17,941 → **7,724** | 312 → 129 |
| 유지 ALS 중 UAS>2m 비율 | 3.18% | **23.73%** | 0.28% |
| 삭제 ALS 중 UAS≤0.5m 점수 | 1,051 | 1,723 | **6,394** |
| 추가 영상점 중 UAS≤0.5m 비율 | 98.68% | 96.67% | 71.62% |
| 추가 영상점 중 UAS>2m 점수 | 27 | 1 | **5,285** |

이 거리 그룹은 사후 진단이다. 참조 가까운 점을 삭제했어도 다른 점이 대신 표현할 수 있으므로 삭제 오류라고 자동 판정하지 않는다. 먼 점도 가림·참조 미관측·시기·좌표 오차를 검토하기 전 변화 오탐 정답으로 사용할 수 없다.

| 지역 | 실제 단면에서 확인한 개선 | 남은 현상과 판정 경로 |
|---|---|---|
| **P1: 변화 구역** | X=−8 단면에서 과거 ALS의 Z≈−37m 경사 상부면을 대부분 제거하고, 영상·UAS의 Z≈−41.8m 평면으로 갱신한다. | Y=−6, X≈−8~−4에 옛 경사 조각이 남는다. 잔여 먼 ALS 411점 중 405점은 `raw_single` 경로다. 사진상 수목으로 추정되는 군집의 하부 연결도 UAS만큼 연속적으로 보이지 않는다. |
| **P2: 변화 구역** | Y=109 단면에서 과거 상부층을 상당수 제거하고, 현재 UAS와 맞는 낮은 단차·반복 곡면 및 일부 수직 연결을 추가한다. | X=134, Y≈114~120 및 Y=109, X≈145~152에 옛 상부 조각이 남아 이중층을 이룬다. 먼 ALS 7,724점은 `raw_single` 5,436 + `filtered` 469 + `unassessed` 1,819다. 현재 영상 기하가 없는 곳의 ALS 유지와, 현재 낮은 면이 보이는데 옛 면이 남는 경우를 나눠야 한다. |
| **P3: ALS 재사용 가능성을 검증하는 구역** | ALS가 영상 기하의 큰 결손을 보완한다. 전체 영상점만 쓰는 것보다 곡면 지붕의 피복이 개선된다. | 원래 연속적인 ALS 곡면의 일부가 빠지고 영상 유래 지붕 아래 조각이 들어온다. 추가 먼 점 5,285개 중 5,107개는 `accepted_changed`, 178개는 `raw_single`이다. 그와 별도로 정제로 제외된 영상점에도 먼 점 1,473개가 있다. 정제가 작동하지만 큰 편차를 가진 변경 후보 일부가 통과한다. |

좌표는 scene-local m이고 고정 단면 폭은 0.5m다. 수목 해석은 사진 기반 추정이며 의미 정답이 아니다.

[비교 뷰어](http://127.0.0.1:8901/)에서 지역 P1/P2/P3를 선택하고 **ALS / 영상 / Wu / UAS**를 같은 카메라로 본다. URL query로 지역을 자동 선택하지 않는다. 원점 단면에는 합집합과 별도 MVS 문맥도 있다. 화면의 점 표시 감축은 시각화 전용이며 정량은 전체 원점이다. 현재 화면은 점군 가시화이며 GS·텍스처 렌더 결과가 아니다.

- P1: [4패널](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-BROWSER-QA-v5/desktop_P1_before_after_reference.png) · [원점 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P1/cross_sections.png) · [출처 지도](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P1/source_maps.png)
- P2: [4패널](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-BROWSER-QA-v5/desktop_P2_before_after_reference.png) · [원점 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P2/cross_sections.png) · [출처 지도](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P2/source_maps.png)
- P3: [4패널](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-BROWSER-QA-v5/desktop_P3_before_after_reference.png) · [원점 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P3/cross_sections.png) · [출처 지도](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P3/source_maps.png)

**원인 해석의 한계:** 예전 filtered 점이 다시 추가되던 오류는 v3에서 수정됐고 v5는 그 수정과 동일조건 실행을 검증했다. 위 P3 통과점은 그 버그의 잔재로 집계된 것이 아니다. 그러나 현재의 영상 메시 생산기, 추정 궤적, 광선 근사, 연결·영역 크기 선택의 영향을 저자 원방법과 분리한 실험은 끝나지 않았다. “모양을 갖춘 매칭 오류가 변화로 받아들여질 수 있다”는 기전 가설은 타당하지만, Wu 원알고리즘 고유의 실패나 간단한 기존 정제의 무효를 입증하지 않는다.

## 3. Wu–Vallet의 향후 발전과 연결할 수 있는 것

[Wu & Vallet 2026 §5, pp.389–390](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf)은 영상 메시 품질·가림·수목에 따른 오류를 현재 한계로 보고하고 다음 방향을 명시한다.

| 저자가 명시한 향후 방향 | 이번 결과와 연결 | 신규성으로 바로 주장할 수 없는 이유 |
|---|---|---|
| 변화 정답 주석과 갱신 품질 평가 | P1/P2 개선과 P3 손상, P2의 높은 총점과 잔여 과거면을 함께 평가 | UAS 기하 평가만으로 변화 정답을 갖춘 것은 아니다. 평가는 검증 기반이며, 세 crop만으로 일반적인 benchmark 기여가 되지 않는다. |
| Full mesh 기반 갱신 | P2 이중층·P3 구멍이 최종 표면에서 어떻게 나타나는지 검사 | Wu 2023은 이미 선택 mesh 접합을 수행했다. 점군을 mesh로 바꾸는 기능 자체는 신규성이 아니다. |
| 의미정보로 수목 오탐 감소와 실제 검출 보존 | 건물·지면·수목 및 관측/비관측별로 잔존과 오갱신을 분석 | 의미 클래스만으로 점의 현재 적합성이 결정되지 않는다. Zhou의 NDVI/지도 후처리 등도 대조해야 한다. |
| 높은 반복 관측 빈도의 UAV 영상 | 영상 지원이 부족한 영역에 관측 방향·시점 수가 주는 효과 검증 | UAV 영상 적용 자체가 새로운 개념은 아니다. UAS LiDAR를 참조로 사용한 것은 UAV 영상 입력 평가를 대신하지 않는다. |

**GS·현재 텍스처·관측 세부 복원은 우리의 B 확장 구상이며 2026 원문의 명시적 future로 인용하지 않는다.** Wu 2023은 별도로 texture stitching을 future로 언급한다. 따라서 저자 계열 전체에 외관 확장 생각이 없었다는 설명도 피한다.

## 4. 다른 연구가 이미 해결한 부분을 반영한 공백 재검토

| 방법과 직접 근거 | 원입력 → 산출물 | 기존 해결 범위 / 우리 주장과의 중복 | 공정한 비교와 아직 확인할 부분 |
|---|---|---|---|
| [Zhou 등 2020, §3–4](https://repository.tudelft.nl/file/File_5e70c9f8-1674-49ab-b4a5-fa3085f3dd77) | 과거 ALS + 보정 항공 stereo; NIR·지도 후처리 → 변화 및 갱신 점군 | ALS 평면의 복수 시차 후보, 영상 경계 선택, 변화 시 ALS를 배제한 두 번째 매칭을 수행한다. 2012 ALS→2018 영상의 실제 시간차 사례가 있다. | “낡은 ALS를 항상 강제한다”는 비판은 틀린다. 잘못된 ALS 높이의 오탐도 보고한다. 유도 매칭부터 재현해야 하며 기존 MVS union으로 대신할 수 없다. 공식 실행 코드 미확인; 입력 부재에 따른 변형을 기록한다. |
| [Wu·Vallet·Demonceaux 2023, §III–VI](https://arxiv.org/html/2303.07182v1) | 정합된 시계열 센서 mesh·시점 → 변화·품질 선택·접합 mesh | 비관측 구분, 미변화 품질 우선/변화 최신성 우선, 다중 시기 지속성, QPBO 선택 및 mesh stitching이 이미 있다. 품질에 정밀도·확실성을 포함할 가능성도 제시한다. | “품질 대신 사용 가능성”이라는 이름만 바꿔 차별화할 수 없다. 독립 현재 관측 검증이 어떤 추가 오류를 줄이는지 대조해야 한다. 공식 실행 코드 미확인. |
| [ARSGaussian, 원문 v2](https://arxiv.org/pdf/2412.18380v2) | 항공 RGB·정합 LiDAR → GS·신규 시점 렌더·깊이 기하 | LiDAR 희소도·결손 보완과 정합·기하 감독을 다룬다. **밀도·정합 민감도 및 raw/SOR·합성 LiDAR 잡음 평가도 있다.** 일반적인 “오류 LiDAR를 다루지 않는다”는 공백은 성립하지 않는다. | 잡음 처리와 오래된 실제 건물 구조의 유지·삭제·교체 판정을 구분한다. 이 세 구역에서의 동일조건 성능은 미실행이다. [공식 repo](https://github.com/WenjuanZhang-aircas/ARSGaussian)는 확인일 기준 Coming soon이며 실행 코드가 없다. 코드 부재는 방법의 무능력 근거가 아니다. |
| [GS4Buildings, §4.4](https://arxiv.org/html/2508.07355v1) | 정합 LoD2 + UAV RGB → 2DGS·렌더·mesh | 가림 보완·구조 보존·외관 복원. 강한 prior가 처마·창·문을 평활화하는 한계와 국소 가중의 필요도 이미 논의한다. | 후속 GeoGS를 제외하고 이 한계만 신규성 근거로 삼으면 안 된다. 원 LoD2 조건과 ALS adaptation을 구분한다. |
| [GeoGS 공식 repo](https://github.com/zqlin0521/GeoGS), [출판사 초록](https://www.sciencedirect.com/science/article/pii/S0924271626003588) | 정합 LoD2 + 희소 RGB/pose + DA3 깊이 → GS·렌더·mesh | 구조 anchoring, 근접도 보호, 영상 깊이 정제와 dual-gated 적응 가중을 명시한다. **구조 보존과 영상 세부의 균형 자체가 직접 겹친다.** | 전문 접근 실패: 초록·README·공식 코드 근거를 논문 전체 검토로 확대하지 않는다. 현재 LoD2 RoofSurface/Z를 입력하면 ALS-only와 정보 조건이 달라진다. ALS로 만든 prior 변형은 별도 adaptation이다. |
| [CL-Splats, §3–4](https://arxiv.org/html/2506.21117v2) | 기존 색상 GS + 새 국소 RGB → 갱신 GS·변화 영역·렌더·과거 상태 | 정적부 보존, 변화 검출, 새 물체 추가, 국소 최적화를 연결한다. 마스크 recall과 재구성 품질의 연결도 이미 평가한다. | 무색 ALS가 native 입력은 아니다. 과거 GS 제작 자료·비용을 포함하고, 현재 영상으로 먼저 prior 외관을 만든 뒤 변화 판단하는 정보 중복을 피한다. [공개 코드](https://github.com/jan-ackermann/cl-splats)는 저자가 원논문과 차이 가능한 재구현으로 표기한다. |

ARSGaussian의 [§4.2.5](https://arxiv.org/pdf/2412.18380v2#page=16)는 점별 오프셋·밀도·대기/시스템/이동체 잡음·표면 결손을 검증한다. 이동체 streak/jitter 실험을 오래된 건물의 존치·철거·신축 판정과 동일시하지 않는다. [§5.2](https://arxiv.org/pdf/2412.18380v2#page=21)는 단기간 취득 조건을 명시한다. LiDAR–Gaussian RMSE가 감독에 쓰인 LiDAR를 기준으로 한다는 한계도 저자가 설명한다. 따라서 독립 현재 UAS 평가와의 차이는 의미 있지만, 그 차이만으로 우리 방법의 우위를 입증하지는 않는다.

여기서 **“해당 조건의 평가를 확인하지 못함”과 “그 방법으로 해결할 수 없음”은 다르다.** 정합, 이상치 제거, 다중 뷰 검증, LiDAR 유도 매칭, 변화 검출, prior GS를 합리적으로 조합했을 때 문제가 해소될 수 있다. 그 경우 기여는 새 판단 알고리즘보다 적용·통합 또는 조건별 검증으로 다시 정해야 한다.

## 5. 연구 필요성에서 검증 가능한 기여 후보까지

연구 필요성은 다음처럼 표현할 수 있다. **과거 구조가 유용한 곳과 낡아서 해로운 곳이 함께 있고, 현재 영상도 결손·오류가 있을 때, 사용 가능한 구조를 살리면서 현재 관측을 복원할 필요가 있다.** P1/P2는 교체의 이득과 잔여 과거면을, P3는 보완의 이득과 해로운 교체를 함께 관찰하는 개발 사례다. 이 필요성이 기존 기술로 충분히 충족되는지까지가 연구 질문이다.

| 관찰된 문제 → 기존 해결 | 실제로 남는지 검증할 질문 | 우리의 수정 후보 | 기대 효과 / 성립을 위한 대조 |
|---|---|---|---|
| P2의 잔여 과거면, P3의 영상 오류 수용 → Wu 품질·가시성 선택, Zhou 유도 매칭, ARSG 잡음·정합 처리 | 기존 품질 처리 후에도 유지·교체 결정이 해로운 영역이 남는가? | **A:** 후보 각각의 현재 사용 근거와 관측 가능성을 독립 현재 영상으로 검증하고, 지지 부족은 미판정으로 전달 | P1/P2의 실제 변화 복원을 유지하면서 P3의 불필요한 삭제·오류 추가 감소. Wu 2023 품질 선택과 같은 영상 근거를 쓰는 강한 순차 대조보다 추가 이득이 있어야 한다. |
| 선택 점군 이후의 구조·세부·외관 → GS4Buildings/GeoGS, CL-Splats, 기존 mesh+texture | 동일하게 선택된 기하에서 구조 보존과 관측 가능한 세부가 함께 개선되는가? | **B:** 선택 기하와 허용 범위에 맞춘 GS 보정·세부 추가, 최종 추출 표면을 다시 검증 | 동일 A를 고정하고 GeoGS 계열·공통 표면+텍스처와 비교. 실제 렌더, UAS 표면 편차, 구멍·중복면·경계 보존을 함께 측정한다. 중심 고정만으로 최종 표면 안정성을 가정하지 않는다. |
| 총 F1이 잔여 문제를 가림 → 기존 기하/변화/렌더 평가 | 성공·실패 조건이 재현 가능하게 구분되는가? | **평가 기반:** 실제 변화 주석, 출처별 유지/삭제/추가, 관측 범위, 위험–피복 및 정합·오류 민감도를 함께 기록 | 독립 사례와 공통 입력의 재현 가능한 평가가 완성되면 경험적 기여 후보가 된다. 현재 세 개발 crop과 UAS 거리만으로 완성된 benchmark·일반화 기여라고 부르지 않는다. |

**기여 채택 조건:** (1) 구현·입력 대체 영향을 분리한다. (2) 가장 가까운 선행 방법과 합리적인 조합으로도 남는 문제를 확인한다. (3) 새 요소만 바꾼 대조에서 변화 복원과 재사용 구조의 비악화를 함께 보인다. (4) 기존에 평가한 P1/P2/P3 외의 독립 사례에서도 확인한다. 기존 조합이 같거나 더 좋으면 새 알고리즘의 필요성을 주장하지 않는다.

## 6. 다음 비교의 우선순위와 이번에 완료한 것

1. **Wu를 전체 연구의 주 대조군으로 유지한다.** 원래 갱신 점군 품질과 그 점군을 동일 B로 확장한 최종 표면·렌더를 모두 비교한다. A에만 가두지 않는다.
2. **A에 가까운 강한 대조를 보강한다.** Wu 2023의 품질 선택, Zhou의 유도 매칭, 정제·다중 뷰 확인을 우선한다. 현재 매칭 대체 효과와 판단 규칙 효과를 분리한다. 같은 기하에서 A를 비교하는 트랙과 원래 매칭부터 수행하는 전체 파이프라인 트랙을 구분한다.
3. **B는 같은 선택 결과에서 비교한다.** GeoGS와 GS4Buildings의 native 예제부터 검증하고, 현재 참조를 넣지 않는 ALS adaptation의 입력 변환을 명시한다. ARSG는 공식 코드 상태와 원문 재현 범위를 기록한다. CL은 필요한 과거 GS가 있는 native 조건과 무색 ALS 조건을 구분한다.
4. **기존 조합을 최종 대조군에 포함한다.** 정합→기존 유도 매칭/정제→변화·품질 선택→기존 표면/GS의 강한 순차 조합과 우리 전체 결과를 같은 정보·출력·평가 예산에서 비교한다. 전체 성능과 A/B 각각의 추가 효과를 함께 보고한다.

이번 완료 범위는 **동결 v5 세 지역 재집계·검산, 원점 단면 재확인, 종합 PNG/PDF/CSV, 원문 기반 기여 중복 감사, 인계문 추가**다. 새 GS 학습·다른 방법 재현·새 source-selection 실험은 이번 종합에서 실행하지 않았다. 이미 완료한 Wu 실행을 문서 검토만으로 대체한 것은 아니다.

검증 평가: **Share with caveats**. Docker에서 15개 입력 해시, 원점–선택 마스크 대응, 출처별 잔여점 수, 출력 평균의 합계, 모든 보고 arm/거리 임계값의 F1 분자·분모를 검산했다. 생성 그림의 축·범례·수치와 세 지역 원점 단면을 직접 확인했다. 기존 v5의 핵심 59검사·평가/동등조건 18검사 완료 기록은 재사용하며 이번 단순 종합을 위해 같은 갱신을 반복하지 않았다.

남은 해석 제약은 저자 전체 파이프라인과의 차이, 개발 사례의 선택, 원점 밀도 및 참조 가림, 기존 좌표 처리다. 작업 EPSG:25832에 대해 UAS header는 EPSG:32632이고, 기존 shift/ALS Z bridge를 유지했다. 새 datum/epoch/정합 교정은 하지 않았으므로 수치를 보정 완료된 절대 정확도로 주장하지 않는다. 참조는 전 구역 평가 전용이며 `scientific_verdict: null`이다.

[분석 영수증](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_synthesis_v7/PHD-WU-VALLET-SYNTHESIS-v7-r2/run/receipt.json) · [공통 v5 프로토콜](../wu_vallet_matched_v5/PROTOCOL_ko_v5.md) · [v5 실행·검증](../wu_vallet_matched_v5/TECHNICAL_RETURN_ko_v5.md) · [v6 P1/P2 상세](../wu_vallet_p1p2_analysis_v6/ANALYSIS_AND_FUTURE_WORK_ko_v6.md) · [이번 준비 이슈](ISSUES_ko_v7.md).
