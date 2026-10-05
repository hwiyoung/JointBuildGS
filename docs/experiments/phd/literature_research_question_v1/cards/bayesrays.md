# Bayes’ Rays — 조건부 공간 불확실성과 오류순위의 의미

- 상태: 문헌 감사, 2026-09-09. `scientific_verdict: null`.
- 식별: Goli et al., *Bayes’ Rays: Uncertainty Quantification for Neural Radiance Fields*, CVPR 2024. 상세 내용은 **arXiv 2309.03185v1, 2023-09-06**, 10쪽을 기준으로 확인했다. CVPR 발표사실은 공식 프로젝트/학회에서 확인했으며 v1과 최종 proceedings의 byte 동등성은 주장하지 않는다.
- 원문: [arXiv 전문](https://arxiv.org/html/2309.03185v1), [저자 PDF](https://www.cs.columbia.edu/~silviasellan/pdf/papers/bayes-rays.pdf), [공식 프로젝트](https://bayesrays.github.io/), [CVPR 프로그램](https://cvpr.thecvf.com/virtual/2024/poster/30344).
- 공식 코드: [BayesRays/BayesRays](https://github.com/BayesRays/BayesRays/tree/edd549e323654c26d52797e43ef17de842befeef), commit `edd549e323654c26d52797e43ef17de842befeef` (2024-02-29), 주요 script·AUSE·README 확인. 실행 없음.
- 확인 저자 PDF SHA-256: `e0c95a27ffabc27a41c7ed1f610749f500389e9f1932842ff16463ade92d53bd`. 해당 파일 표지의 버전은 arXiv v1이다. 원문은 임시 열람용이며 저장소에 재배포하지 않았다.
- 비교 지위: **불확실성 추정/후처리 구성요소**. 외부기하+현재영상의 완전한 재구성 비교군이나 native GS 불확실성법은 아니다.

## 1. 문제와 입출력

학습된 NeRF의 관측부족에 의한 공간 불확실성을 사후 추정한다. 입력은 이미 수렴한 radiance/density 모델과 학습 카메라, 출력은 공간 uncertainty field와 threshold로 정리한 렌더다. 실제 RGB는 원래 NeRF 학습에 사용되며 Hessian 근사 계산 자체에는 원영상 pixel이 필요하지 않다. 외부 측량기하와 사전학습 foundation prior를 추가하지 않고, 작은 공간변형에 Gaussian regularizing prior를 둔다. [원문 §4, pp.4–6](https://arxiv.org/html/2309.03185v1)

가정은 고정된 수렴 모델·카메라, 국소 Laplace/diagonal 근사다. 연구대상은 주로 미관측·가림의 **epistemic** uncertainty다. 현재성 확률, 정합오차, 센서잡음의 분산이 아니다. 저자는 NeRF 외의 GS 표현으로 단순히 옮길 수 없다고 명시한다. [원문 §6, p.8](https://arxiv.org/html/2309.03185v1)

## 2. 기여의 위치

| 요소 | 분류 | 내용 |
|---|---|---|
| 입력·전처리 | 사용 | 기존 NeRF checkpoint·camera; 원영상 재학습 요구 없음 |
| 좌표·카메라·정합 | 고정 사용 | camera·scene 좌표를 조건으로 추정; pose 불확실성은 별도 |
| 표현 | 새+사용 | 기존 NeRF 위의 trilinear spatial perturbation grid |
| 관측모형·렌더링 | 사용+새 | NeRF RGB Jacobian으로 Fisher/Hessian 근사, uncertainty channel 렌더 |
| 증거 사용·감독·제약 | 새+사용 | 작은 변형 Gaussian prior+Laplace/diagonal 근사; 새 관측 감독은 없음 |
| 초기화·최적화·모델 변경 | 새/미확인 | 기존 수렴점에서 사후 covariance 계산; 복원기하 학습 갱신 없음 |
| 추출·후처리 | 새+사용 | uncertainty threshold로 density를 억제한 floater 정리; 측량 mesh 추출은 미확인 |

근거: [원문 §4–5, Fig.3–5](https://arxiv.org/html/2309.03185v1), [공식 uncertainty.py](https://github.com/BayesRays/BayesRays/blob/edd549e323654c26d52797e43ef17de842befeef/bayesrays/scripts/uncertainty.py#L282), [output_uncertainty.py](https://github.com/BayesRays/BayesRays/blob/edd549e323654c26d52797e43ef17de842befeef/bayesrays/scripts/output_uncertainty.py#L33).

## 3. 무엇을 고정하고 무엇을 수정하는가

| 상태 | 실제 대상 | 해석 |
|---|---|---|
| 고정 | 학습된 NeRF·camera·기존 view distribution | 사후 진단이므로 원모델 자체를 다시 fit하지 않음 |
| 추정 | perturbation covariance 및 그 scalar field | 색 오차를 많이 늘리지 않는 공간 자유도의 크기 |
| 제약 | 격자해상도·변형 prior strength·diagonal covariance 근사 | 계산량 감소; 상관을 풀면 메모리/계산 증가 |
| 반복 | ray batch별 Jacobian 누적 | 새 증거 확보가 아니라 고정모델의 민감도 적분 |
| 수정된 출력 | threshold 통과 density와 렌더 support | 거부된 영역을 재구성하는 경로와 다름 |

흐름: `고정 NeRF + 학습 camera → 공간섭동 RGB Jacobian → Hessian/공분산 → uncertainty → 렌더 density filter`. 이 버전에는 uncertainty가 앞단 camera/NeRF 학습을 고치는 경로가 없다. 원리가 학습 pixel을 요구하지 않아도 공개 runner는 Nerfstudio datamanager로 ray batch를 읽는다. **수학적 비의존성과 실행환경이 dataset path를 요구하는 사실을 구별**한다. [코드 uncertainty.py L282–330](https://github.com/BayesRays/BayesRays/blob/edd549e323654c26d52797e43ef17de842befeef/bayesrays/scripts/uncertainty.py#L282)

우리 해석: 표현을 고정하여 빠르게 진단할 수 있지만, 틀린 pose나 bias까지 주변 변형분산 하나로 설명한다고 보장할 수 없다. 이 조건부 분산을 source별 기대 기하오차로 쓰려면 별도 연결 검증이 필요하다.

## 4. 실제 검증 범위

| 항목 | 확인 범위 |
|---|---|
| 데이터/참조 | ScanNet 4장면 각35 train/5 test와 GT depth; Light Field 4장면은 CF-NeRF와 같은 split·pseudo-depth. Nerfbusters 데이터의 후처리 평가 |
| 비교 | CF-NeRF와 10개 모델 ensemble의 depth-error ranking, Nerfbusters의 정리 품질/coverage |
| 효과 분리 | grid resolution, NeRF architecture, filtering threshold 비교. scene별 best threshold는 고정 threshold와 분리된 oracle성 선택 |
| 성과/비용 | AUSE가 CF-NeRF보다 낮고 ensemble에 근접; grid256 설정 약90초/RTX6000. threshold는 렌더 품질과 coverage를 함께 바꿈 |
| 미평가 | 외부기하 source 선택·metric surface mesh 보존·시기 변경 판정·pose correction·현재성 probability calibration |

근거: [원문 §5, pp.6–8, Fig.4–8](https://arxiv.org/html/2309.03185v1). [코드 README](https://github.com/BayesRays/BayesRays/blob/edd549e323654c26d52797e43ef17de842befeef/README.md)는 scale solver가 sparse COLMAP와 GT depth로 평가 scale ambiguity를 해소한다고 설명한다. 이것은 deployment에서 GT 없이 scale을 해결했다는 결과가 아니다.

**AUSE는 오류 순위와 sparsification의 근접성을 평가한다.** [공식 AUSE 코드](https://github.com/BayesRays/BayesRays/blob/edd549e323654c26d52797e43ef17de842befeef/bayesrays/metrics/ause.py#L6)도 error/uncertainty 정렬 후 잔여오차 곡선을 적분한다. 원문의 “calibrated”라는 표현만으로 '90% 구간이 실제 오차를 90% 포함한다'는 절대 calibration이나 시간적 유효성 보정을 입증했다고 읽지 않는다(우리 분석).

## 5. 남은 오류와 전달 경로

| 구분 | 조건·오류 | 경로·대안 원인 |
|---|---|---|
| 원문 사실·관측된 실패 | 시점간 불일치로 생긴 floater인데 낮은 uncertainty | inconsistent training→잘못된 field→epistemic 진단의 놓침. Fig.7, p.8을 PDF 이미지로 확인 |
| 저자 해석·범위 밖 | aleatoric noise/시점 불일치를 추정하지 않음 | 분포 대상의 제한; 낮은 uncertainty가 모든 오류의 부재를 뜻하지 않음 |
| 원문 사실·ablation | 작은 grid에서 uncertainty 과소평가; threshold에 따라 coverage 감소 | 표현해상도→진단→제거. Fig.5·8 |
| 우리 추론·미평가 | 독립 source bias·정합오차를 covariance로 충분히 설명하지 못할 가능성 | 잘못된 조건부 모델→안전성 오판; 실제 ALS/항공 사례 실패는 확인하지 않음 |

근거: [원문 §5.3·§6](https://arxiv.org/html/2309.03185v1). 여기서 실제로 확인한 잔여 오류는 Fig.7의 저불확실성 floater이며, 모든 floaters를 못 지운다는 주장이 아니다. 공간 support를 줄여 품질이 올라가는 것과 결손의 복원은 다르다.

## 6. 연구 공백 후보

이미 해결된 것은 수렴 표현의 공간적 약관측 정도를 빠르게 진단하고 출력에서 고위험 영역을 제외하는 기능이다. 불확실성 지도나 threshold 자체는 신규성 근거가 아니다.

후보는 **관측부족 uncertainty, 측정/정합 bias, prior 오류를 구별한 점수가 실제 복원행동의 손익을 예측하는가**다. 이것은 native GS 이식이나 Bayesian 용어 추가만으로 해결되는 문제가 아니며 아직 검증 가설이다. 가장 가까운 단순 해결책은 기존 기하 차이 신뢰구간+영상 photo-consistency+강건 정합+BayesRays형 약관측 진단의 분리된 조합이다.

최소 비교는 관측 수/각도, photometric residual, 기존 consistency confidence, 이 uncertainty 및 단순 calibrated combination을 동일한 국소 surface-error/수정효과 예측에 평가한다. 방법 입력에서 독립 참조를 배제하고 reference는 평가에만 쓴다. AUSE 외 절대오차 calibration, risk–coverage, 유효영역 악화와 복원 성공률을 함께 본다.

기각 조건: 단순 관측량/기존 confidence가 동일 예산에서 잘 예측하면 새 uncertainty model을 접는다. uncertainty가 오류 순위만 설명하고 source 행동의 손익을 못 설명하면 자동선택 주장을 접고 진단으로 제한한다. 추가 관측 없이는 bias와 변화가 식별되지 않으면 유보를 허용한다.
