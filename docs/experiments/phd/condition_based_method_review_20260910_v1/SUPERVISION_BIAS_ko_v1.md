# 적응적 기하 감독·감독 편향 보정: 조건 중심 검토

- 작성일: 2026-09-10
- 범위: 문헌·공식 코드의 읽기 전용 감사와 방법/최소 비교 설계
- 상태: `EXPLORATORY_DESIGN_ONLY / NO_NEW_EXPERIMENT`
- `scientific_verdict: null`
- 기존 AGENTS.md, 연구 헌장, DEC-P1-025를 읽었다. 기존 계약·실행·계보는 보존한다. 이번 방법 방향은 2026-09-10 사용자 지시를 따르며, ALS·GS·LoD2·단일 소스 선택·동결 confidence를 필수로 삼지 않는다.

## 1. 이 방법군을 선택하는 입력·관측 조건

목표는 영상 파생 depth/normal이 존재하지만 국소적으로 부정확하거나 편향된 상황에서, 유효한 구조를 손상시키지 않고 필요한 기하 수정을 가능하게 하는 것이다. 다음 조건은 데이터에서 확인할 비교 축이며, 이미 관측된 실패라는 뜻은 아니다.

| 조건 | 구분할 현상 | 검토할 기존 원리 | 선별 이유 |
|---|---|---|---|
| 영상에는 경계·얇은 부재가 보이지만 단안 depth/normal이 평활화함 | 정보 존재와 감독 누락의 차이 | DebSDF, ND-SDF, NC-SDF | 감독을 약화하는 것, 보정하는 것, 표본을 늘리는 것, 표현 전달을 고치는 것을 구분할 수 있음 |
| 넓은 무텍스처 면은 prior가 맞고 인접 세부는 prior가 틀림 | 같은 국소 영역의 보존과 수정 | ND-SDF adaptive prior loss, DebSDF adaptive smoothness | 수정 자유도를 무조건 늘릴 때 정확한 평면이 손상되는지 검토 가능 |
| 서로 다른 시점의 단안 예측이 일관되지 않음 | 시선별 감독 편향과 3D 형상 오류의 구분 | NC-SDF, ND-SDF | 입력 맵 자체를 재학습하지 않고 감독과 형상 사이에 보정 변수를 둠 |
| 정확한 감독과 아직 틀린 초기 형상이 충돌함 | 모델 미수렴을 감독 불신으로 해석하는 위험 | GPU-SDF, DebSDF | 모델 잔차와 독립적인 prior 안정성 신호를 비교할 필요 |
| 관측 피복·시차가 낮거나 반사/반복 패턴 때문에 영상의 기하 제약이 약함 | 정보 부족과 최적화 실패의 구분 | ND-SDF 한계, 보정 변수의 제약 설계 | 보정 모듈이 감독 오류뿐 아니라 형상 오류까지 흡수할 수 있는지 확인 |
| rendered depth/normal은 개선됐으나 추출 표면의 세부가 남지 않음 | 감독 선택과 표현/추출 전달의 차이 | DebSDF, D-NeuS | confidence 개선만으로 설명되지 않는 경쟁 원인을 제공 |

이 문헌들의 핵심 입력은 calibrated RGB와 영상에서 추정한 기하 감독이다. 독립적인 LiDAR/LoD/DSM 초기 구조 보존까지 그대로 검증한 논문으로 취급하지 않는다. 그러나 외부 기하를 추가하기 전부터 존재하는 감독 편향·수정 자유도 문제를 다루므로 구성요소 및 기제 경쟁 문헌으로 가깝다.

## 2. 핵심 네 방법의 성공과 부족

### DebSDF — 감독 신뢰도와 표현 전달 편향을 분리하는 근거

**원문 확인:** [arXiv 2308.15536v3](https://arxiv.org/html/2308.15536v3), §III-B–E, §IV-B–D, Table IV–V, Fig.9. RGB/pose와 단안 depth/normal로 SDF와 외관을 복원한다. 불확실성을 학습하여 prior 감독·표본·smoothness를 조절하고, 곡률을 고려한 SDF→density 변환을 추가한다. ScanNet·ICL-NUIM 등의 비교에서 세부와 평면 품질을 개선했다. Fig.9에서 uncertainty/filter/sampling/smoothness만 사용한 중간 모델의 얇은 구조 손상은 최종 변환 모듈로 개선된 **해결된 ablation**이다. 이를 완성법의 미해결 실패라고 인용하지 않는다. §III-B의 부정확한 prior에 낮은 uncertainty, 정확한 prior에 높은 uncertainty 가능성은 **저자 분석**이며 실패 빈도 일반화가 아니다.

**공식 구현 확인:** pin `4580c8e1c9872e65f6cb9fc55607162f57ab7a54`. [code/model/loss.py](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/loss.py#L238) L238–327은 geometry와 uncertainty의 gradient를 따로 detach한다. 높은 uncertainty로 기하 감독을 막아도 uncertainty 학습은 계속된다. [code/model/network.py](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/network.py#L354) L354–408에서 현재 SDF/법선에 따른 uncertainty 렌더링과 곡률 기반 변환을 확인했다. 고정된 입력 맵과 학습되는 기하/외관/uncertainty를 구분한다. 본 감사에서 sampler 전체 호출은 재감사하지 않았다.

**우리 목표에서의 위치:** 구성요소 도입 후보이자 원인 설명 참고. 외부 기하의 정확한 부분/틀린 부분을 같은 영역에서 수정 전후로 평가하는 계약, metric LiDAR/LoD/DSM 보정의 충분성은 이 감사의 확인 범위에서 **미평가**다. uncertainty 이식과 SDF 변환 이식은 별도이다. 후자는 GS에 그대로 복사할 수 없다.

### ND-SDF — 보정 변수 자체에도 제약이 필요하다는 가까운 비교

**원문 확인:** [arXiv 2408.12598v3](https://arxiv.org/html/2408.12598v3), §3.2–3.5, §4.2 Table 6, §5, Appendix B.2/C.4. RGB/pose·단안 depth/normal로 SDF/외관과 normal deflection을 함께 학습한다. 각도에 따라 원래/보정된 normal 감독과 depth 감독·표본·색 손실·일부 unbiased rendering을 조절한다. Table 6의 무제약 deflection(Model A) 평면 주름은 adaptive prior loss(Model B)로 개선한 **해결된 ablation**이다. §5는 낮은 관측 피복에서 모호성 때문에 잘못된 구조/local optimum을 학습할 수 있다는 **완성법의 저자 한계**를 명시한다. Appendix B.2의 normal 각도로 depth 감독을 제어하는 근거는 같은 단안 추정기의 공통 편향과 scale 모호성이다. 독립 metric 기하에 자동 적용되는 가정이 아니다.

**공식 구현 확인:** 현재 pin `f58f29466a5f43e80dedb0cd155f57dae7569347`.

- [models/loss.py](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/loss.py#L302) L302–344에서 원래/보정 normal 손실을 각도에 따라 함께 반영한다. L315–319의 각도 계산은 `no_grad` 블록이며, 이 경로는 loss weight로의 역전파와 형상/보정 변수 학습을 구분한다. L187–190은 별도 adaptive depth loss다.
- [models/system.py](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/system.py#L148) L148–179의 normal field와 partial unbias, L198–227의 quaternion 합성/normal 보정/각도 출력을 확인했다. 입력 prior 맵 재생성은 이 경로가 아니다.
- [exp_runner.py](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/exp_runner.py#L281) L281–350 및 L451에서 누적 angle map이 이후 sampling으로 돌아오는 실제 feedback을 확인했다. `update_train_angle`은 현재 예측과 감쇠된 이전 값을 결합한다. 단계/annealing의 존재가 단방향 최적화를 뜻하지 않는다.

**우리 목표에서의 위치:** 감독 보정과 수정 제약 원리에 대한 강한 구성요소 경쟁 후보. SDF 전체 파이프라인과 GS 이식판은 구분한다. 외부 기하의 normal이 정확해도 depth가 틀릴 수 있고 그 반대도 가능하므로, normal 각도로 독립 기하 depth 가중까지 묶는 것이 충분한지는 별도 질문이다. 낮은 피복에서의 오류는 독립 LiDAR/LoD/DSM 구조를 넣으면 해결될 수도 있고, 그 구조가 틀렸다면 남을 수도 있다. 둘 다 **우리 가설**이다.

### NC-SDF — 신뢰도 가중 이외의 명시적 감독 편향 보정

**원문 확인:** [arXiv 2405.00340v1](https://arxiv.org/html/2405.00340v1), §3.1–3.5, §4.1–4.3 Table 3. RGB/pose와 단안 normal을 사용하며, 시선 의존 회전으로 SDF normal을 보정해 noisy normal 감독에 맞춘다. 원래 normal 맵은 고정이고 geometry·color·compensation 모델을 학습한다. 1단계 초기화 뒤 2단계는 세 모델을 **공동 최적화**하므로 단방향 정제라고 부를 수 없다. Table 3에서 같은 Hybrid+IPS에 compensation을 추가한 행은 F-score 0.749→0.781이며 accuracy와 completeness도 개선됐다. 보정 없는 상태의 부족은 이 논문이 개선한 **ablation**이다. RGB가 geometry를 구속한다는 §3.2의 설명은 저자의 작동 해석이며 저피복/반사 도시 장면에서의 식별성을 보장하지 않는다.

**공식 구현 범위:** arXiv 본문, CVF 원문 색인, 제목·저자 기반 검색을 확인했으나 저자 소유 공식 학습 저장소를 식별하지 못했다. 코드가 없다고 단정하지 않으며 구현 충실도는 `UNVERIFIED_OFFICIAL_IMPLEMENTATION`이다. 단계별 gradient 경로는 원문 수준 확인이다.

**우리 목표에서의 위치:** ND-SDF와 함께 편향 보정 변수의 선행기여를 반드시 대조할 후보. 회전 보정 모듈 자체를 신규성으로 제안할 수 없다. 외부 기하의 위치 오류·결손·위상 변화까지 normal 보정 하나가 해결한다는 근거도 확인하지 않았다. 무텍스처 평면의 유효한 기존 구조와 인접한 잘못된 구조를 동시에 다루는 추가 제약은 설계 후보이지만 그 필요성부터 비교해야 한다.

### GPU-SDF — 감독 기각 후 남는 제약 부족을 겨냥한 최근 후속

**원문 확인:** [arXiv 2602.23926v1](https://arxiv.org/html/2602.23926v1), §III-B–D, §IV Table II–III. ND-SDF를 base로 두고 원본·좌우·상하 flip의 단안 예측 차이로 prior uncertainty를 계산한다. 이를 geometry 손실에 사용하고 edge distance field와 국소 ray consistency를 추가한다. geometry/deflection/edge 표현은 최적화되고 flip uncertainty는 사전 추정 신호다. Table III는 uncertainty 및 보완 제약의 개선을 보고한다. Table II의 `036bce3393` 장면에서는 full method Chamfer 3.6이 ND-SDF 3.4보다 크다. 평균 개선을 모든 장면·지표 개선으로 읽지 않는다. 기각 후 구조 손실이라는 설명은 **저자의 선행 방법 분석**이며 모든 uncertainty법의 공통 실패 증명은 아니다.

**공식 구현 범위:** [공식 repository tree](https://github.com/IRMVLab/GPU-SDF/tree/f0c6f7f7c83bd4c5c525ed3d8de784c23affe8ea), [GitHub tree API](https://api.github.com/repos/IRMVLab/GPU-SDF/git/trees/f0c6f7f7c83bd4c5c525ed3d8de784c23affe8ea?recursive=1)를 현재 조회했다. pin `f0c6f7f7c83bd4c5c525ed3d8de784c23affe8ea`에는 README.md 한 파일만 존재하고 `truncated:false`다. 학습 코드·안정화·정확한 설정 재현은 **미확인**이다. 이는 성능 한계가 아니다.

**우리 목표에서의 위치:** adaptive loss만의 한계와 대체 감독 설계의 후보. flip 안정성은 정답 보장이 아니며 일관된 편향을 놓칠 수 있다는 점은 **우리 추론**이다. RGB edge는 추가 센서 입력은 아니지만 추가 추정기·연산과 감독정보이므로 공정 비교에서 동일하게 제공하거나 별도 정보증가 비교로 둔다. Eq.12–13의 항은 KL에서 착안한 것으로 소개되며, 본문만 보고 정규화된 KL divergence나 calibrated geometric error likelihood라고 가정하지 않는다. 구현 공개 전에는 epsilon/clipping·단위 정규화까지 확정할 수 없다.

## 3. 인용·후속을 따라 확장한 후보와 검토 경계

DebSDF→ND-SDF→GPU-SDF의 본문·인용 관계를 따라, 단순 가중 이외에 감독 편향과 제약 부족을 다루는 방법을 검토했다. ND-SDF Appendix C.4는 NC-SDF를 concurrent work로 비교한다. 그 절의 NC-SDF 비판은 경쟁 논문 저자의 주장으로 구분하며, 이번 문서에서 NC-SDF 완성법의 독립 검증 실패로 승격하지 않는다.

추가 후보 **D-NeuS**는 [WACV 2023 원문 색인](https://openaccess.thecvf.com/content/WACV2023/papers/Chen_Recovering_Fine_Details_for_Neural_Implicit_Surface_Reconstruction_WACV_2023_paper.pdf)과 [공식 구현](https://github.com/fraunhoferhhi/D-NeuS)으로 1차 선별했다. alpha-compositing 표면의 SDF=0 제약과 표면점의 다중뷰 feature consistency를 다루므로, “감독이 있는데 표면으로 전달되지 않는다”는 원인의 참고다. [exp_runner.py](https://github.com/fraunhoferhhi/D-NeuS/blob/main/exp_runner.py#L145) L145–170에서 bias/feature 손실이 RGB/eikonal/mask와 같은 optimizer에 전달되는 것을 확인했다. 전체 PDF 재접속이 403으로 실패하여 논문 실험·ablation 및 renderer 내부까지 감사하지 않았고, 이 문서의 네 핵심 방법과 같은 검증 수준으로 취급하지 않는다. 직접적인 기구축 기하 활용법으로 분류하지도 않는다.

## 4. 우선 원인 가설과 최소 비교

다음은 문헌에서 우리 목표로 옮겨온 **분석·설계**이며 JointBuildGS에서 이미 확인된 원인이 아니다. 정확한 구조/틀린 구조/결손을 평가용으로 나눈 동일 국소 영역 안에서 보정량과 유효구조 손상을 함께 기록한다. 평가 reference는 optimizer·정합·모델 선택에 제공하지 않는다.

| 질문·우선도 | 경쟁 원인 | 최소 비교와 통제 | 기각·축소 조건 |
|---|---|---|---|
| Q1. 국소 confidence만으로 충분한가? 높음 | prior가 틀림 / 아직 모델이 틀림 / camera·visibility 불일치 | 동일 초기 구조와 RGB·감독에서 잘 조정한 고정 가중, robust residual 가중, 독립 예측 안정성 가중 비교. 정합·가시성 통제 전후를 분리 | 고정 가중 또는 robust loss로 보존·수정을 함께 달성하면 별도 confidence 추정 원리의 필요성 축소 |
| Q2. 감독 자체의 편향 보정이 필요한가? 높음 | 랜덤 오류 / 일관된 시선별 편향 / 부정확한 초기 표면 / 보정변수의 과도한 자유도 | 같은 uncertainty·sample 수에서 가중만, NC/ND형 보정만, 기존 보정+adaptive 원본 감독 제약 비교. plane/세부를 함께 포함 | 기존 NC/ND형 보정으로 충분하면 새 보정 네트워크를 기여로 주장하지 않음. 보정이 RGB residual만 줄이고 metric geometry 손상을 늘리면 해당 자유도 축소 |
| Q3. prior 깊이 감독과 구조 보호를 분리해야 하는가? 높음 | 약한 depth 손실 때문 / 독립적인 position·scale·rotation 보호 때문 | 같은 한 영역에서 prior depth 가중 높음/낮음 × 구조 보호 강함/약함 최소 2×2. 보호 범위·위치 변화·세부 생성 가능 범위를 기록 | depth 가중만으로 설명되면 별도 보호 원리의 필요성 축소. 정확한 normal/잘못된 depth 및 그 반대에서 묶음 제어가 충분하면 분리 제어의 우위 기각 |
| Q4. 기각이 정보를 잃게 하는가? 중간 | 감독 제거 / 새 제약 부족 / 실제 관측 불충분 | 같은 신뢰도 맵에서 hard mask, 약한 연속 loss, 동일 RGB-derived edge/consistency 추가를 비교. 모든 arm에 동일 추정기 출력 제공 | 연속 가중만으로 충분하면 보완 모듈 제거. 여러 뷰에도 기하 구속이 부족한 곳은 자동 세부 복원 주장 범위에서 제외 |
| Q5. 올바른 감독이 표면으로 전달되는가? 중간 | representation/renderer bias / extraction 해상도 / sampling 불균형 | 가중·초기화 고정 후 renderer 또는 surface-consistency 제약만 변경. 같은 표면 추출과 같은 rays/예산 사용. rendered depth와 extracted geometry를 각각 평가 | 추출 해상도만으로 현상이 사라지면 학습 원리 주장을 축소. uncertainty 수정 효과가 없고 전달 개선만 유효하면 기여를 그 단일 원리로 재정의 |

추가로 동일 정보·동일 연산 예산 비교와, 추가 depth/normal/edge 추정기를 허용한 전체 시스템 비교를 분리한다. ND/NC/Deb의 전체 SDF 재현과 특정 원리의 다른 표현 이식은 서로 다른 실험이다. prior 종류가 달라졌다는 것만으로 방법 신규성을 주장하지 않는다.

## 5. 새 방법 기여 후보와 판정 경계

도입 가능한 기존 요소는 robust/uncertainty weighting, normal compensation/deflection, adaptive original-prior constraint, biased-rendering 보정, edge/consistency 감독이다. 이 요소의 조합 자체는 신규성 근거가 아니다.

한 가지 구체적 후보는 **감독의 수정과 형상의 수정을 분리하되, 허용되는 보정 자유도를 관측 가능한 기하 방향으로 제한하는 원리**다. 우선 카메라·가시성·기하 표현을 고정하고, 보정 변수가 설명할 수 있는 시선별 잔차와 실제 3D displacement가 설명해야 하는 잔차를 어떤 증거로 구별할지 정한다. 유효한 기존 구조의 손상은 통제하면서 이미지에 근거한 수정이 가능한 방향만 열자는 가설이며, 오류 원인 분류기나 단일 소스 선택 모듈을 요구하지 않는다. 이미 ND-SDF가 보정 자유도와 원래 prior 감독 사이의 균형을 다루므로, 새로운 부분은 기존 adaptive constraint로 설명되지 않는 조건·추정식·효과가 확인될 때만 남는다.

정보 자체가 없는 영역에서는 어떤 weighting/compensation도 관측 가능한 현재 세부를 증명해 복원할 수 없다. 반대로 정보가 존재한다면 전체 평균 F1 외에 accuracy·completeness·coverage·세부·외관·계산량을 분리하여 실제 개선을 판단해야 한다. P1/P2/P3 개발 관찰은 이 가설을 선택할 단서이며 원인 확정이나 일반화의 증거가 아니다.

## 6. 감사 예외·재현 범위

- 학습·추론·렌더·재구성·프로젝트 도구 실행은 하지 않았다. 기존 파일·서비스·산출물은 변경하지 않았다.
- 문헌 원문 HTML의 관련 절·표와 공식 GitHub raw source를 읽었다. 논문 전체 코드의 실행 충실도나 성능을 재현한 감사는 아니다.
- GitHub JSON 출력에 사용하려던 `jq`가 host에 없어 첫 조회가 실패했다. 설치하지 않고 curl 원문/텍스트 필터와 응답 JSON 검토로 복구했다. 출력 절단이 있었던 ND tree는 필요한 raw source 경로를 직접 조회했다.
- NC-SDF CVF HTML 및 D-NeuS PDF 일부 접근은 fetch 오류/403이었다. NC-SDF는 arXiv 본문으로 관련 절을 확인했고, D-NeuS는 1차 선별 수준을 명시했다.
- 인용된 raw 코드에서는 `gt` 변수명이 학습 RGB/단안 pseudo-supervision을 지칭하기도 한다. 이 표기를 우리 연구의 독립 평가 GT 투입 허용으로 해석하지 않는다.
