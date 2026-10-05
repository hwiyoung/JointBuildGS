# 서로 다른 기하 증거의 적응 융합: 보정 원리의 가까운 선행

- 검토일: 2026-09-10
- 범위: 원문·공식 구현의 읽기와 설계 검토. 새 학습·추론·렌더·추출 없음.
- `scientific_verdict: null`
- 판정 용어: **사실**=원문/코드에서 확인, **저자 해석**=저자가 설명한 원인, **우리 추론**=도시 prior 문제에 대한 해석, **미확인**=검증하지 못함.
- 두 논문 모두 **구성요소 경쟁 문헌**이다. 원 논문의 입력 계약을 변경하지 않고 ALS/LoD/DSM+현재 RGB의 직접 비교 방법으로 부르지 않는다.

## 1. SenFuNet — Learning Online Multi-Sensor Depth Fusion

근거 버전: ECCV 2022 정식 [본문 PDF](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920088.pdf), 방법 pp.4–7; 보충을 포함한 [arXiv:2204.03353v2](https://arxiv.org/html/2204.03353v2), §3–4, Appendix J/Fig.17. 공식 코드 pin `43c1682e29c700df4577d9dcf0ac3b8ebdd8f496`; 아래 고정 URL의 실내용을 이번에 재확인했다. 버전 간 표 번호는 같다고 가정하지 않는다.

### 1.1 문제·입출력

**사실:** 알려진 내·외부표정의 다중 depth stream→융합 TSDF/mesh. ToF는 측정, MVS/PSMNet은 영상 파생 깊이이며, GT TSDF로 특징·가중망을 지도학습한다. 비동기는 센서 sampling 차이이다. (§3, Fig.2, 식3–5)

### 1.2 기여 위치

아래에서 `새`는 논문이 제안한 요소라는 뜻이며 본 검토의 독립적 신규성 판정은 아니다.

| 요소 | 구분·내용 |
|---|---|
| 입력·전처리 | 기존: depth/MVS, 선택적 denoising |
| 좌표·카메라·정합 | 기존: 주어진 pose·보정 |
| 표현 | 기존 TSDF + 새 센서별 특징·형상 분리 구성 |
| 관측모형·렌더링 | 기존: 역투영; 외관 렌더 학습 없음 |
| 증거·감독·제약 | 새: 국소 α 및 단일센서 outlier 감독 |
| 초기화·최적화·변경 | 새: 특징·가중망 공동학습; 기존 이동평균 |
| 추출 | 기존: marching cubes |
| 후처리 | 새: 단일센서 복셀의 α 기반 기각 |

### 1.3 고정·수정과 피드백

**사실:** 센서별 TSDF·특징·관측횟수를 누적하고 α로 상대 기여를 산정한다. 이는 외부 pose나 원 MVS를 재추정하지 않는다. (§3)

**코드 사실:** [filtering_net.py L132–224](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/modules/filtering_net.py#L132)는 sigmoid α와 1−α의 TSDF 결합을 구현한다. [CoRBS 설정 L6–58](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/configs/fusion/corbs.yaml#L6)은 일반 TSDF 누적, 학습하는 특징·가중망, 단일센서 α 감독을 지정한다. [pipeline.py L27–102](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/modules/pipeline.py#L27)의 training은 누적 후 필터 학습이며, `test()`는 depth 반복 종료 후 scene별 필터를 호출한다. 최종 융합 TSDF가 다음 센서별 TSDF를 수정하는 경로는 이 호출에서 확인되지 않는다. 온라인 방법과 이 평가 호출의 출력 주기를 구분한다.

### 1.4 검증 범위

**사실:** Replica 7 train/3 test, CoRBS desk→human, Scene3D. TSDF 오차·F/P/R, 단일센서·TSDF·RoutedFusion·DI-Fusion·Early Fusion, denoising/비동기 비교를 제시한다. (§4)

### 1.5 남은 실패와 전달

**관측된 실패/저자 해석:** 매끄럽지만 덜 정확한 소스 선택, 경계·반복 무늬에서 선택 대신 평균화, 두 센서가 겹쳐 만든 outlier 잔류를 보고한다. 마지막 원인은 기각이 단일센서 복셀에 제한되기 때문이다. (Appendix J, Fig.17)

**미평가/범위 밖:** 다른 시기의 실제 철거·증축, LoD의 의도적 생략, 외관 최적화, 우리 P1/P2/P3는 이 근거로 판정하지 않는다.

### 1.6 연구 질문으로 연결 — 우리 추론

이 논문은 “소스별 국소 타당성을 학습해 가중하면 된다”를 이미 상당히 구체화했다. 동시에 **평활함이 정확함의 대리변수가 되거나, 양쪽의 오류가 일치하면 적응 융합도 틀릴 수 있음**을 직접 보여준다. 이 점이 구현의 빈칸보다 강한 연구 시작점이다.

- **방법론 후보:** prior의 구조적 매끄러움과 실제 정확성을 구분하는 감독·관측 증거, 양쪽 기하의 일치와 독립적인 현재 영상 지지의 차이. 단순히 α를 새로 예측하는 것과 구분해야 한다.
- **조건 차이:** ALS/LoD/DSM을 depth stream으로 변환하면 가시성, 관측횟수, 누락의 의미까지 센서 depth와 같아지는 것은 아니다. 이는 적용 전제 차이이며 곧바로 신규성이 아니다.
- **최소 비교:** 동일 변환·동일 학습정보에서 전역 융합, SenFuNet식 국소 결합, 관측 지지 추가를 비교한다. 매끄럽지만 위치가 틀린 prior / 거칠지만 위치가 맞는 영상 기하를 함께 포함하고, 두 소스가 모두 유효한 성공 영역도 보존한다.
- **기각 조건:** 기존 국소 규칙의 재학습·보정으로 같은 효과가 나거나, 추가 규칙이 구조 손상을 줄이지 못하면 해당 차별성 가설은 기각한다. GT TSDF가 없는 제안과 GT 지도학습 baseline은 학습정보 차이를 별도 보고해야 한다.
- **주의:** 최적 α를 준 진단으로도 올바른 형상이 나오지 않으면 상대 가중치보다 후보 기하·표현·갱신 범위가 병목일 수 있다. 이것은 본 논문의 실험 결과가 아니라 다음 검증 설계다.

## 2. RoutedFusion — Learning Real-Time Depth Map Fusion

근거 버전: CVPR 2020, [arXiv:2001.04388v2](https://arxiv.org/html/2001.04388v2), §3.2–3.7, §4.1–4.4, Fig.2·6, Table 1–2. [공식 저장소](https://github.com/weders/RoutedFusion)는 공개 구현을 논문 이후 개선 구현으로 표시한다. 현재 HEAD를 읽기 전용 `git ls-remote`로 확인한 pin은 `dc6e0f582654ffcbd227c95e9a63e9654d45fa77`; 원 논문과 바이트 동일 실행이라는 뜻은 아니다.

### 2.1 문제·입출력

**사실:** 알려진 pose의 noisy depth→온라인 TSDF. routing은 깊이·confidence, fusion은 기존 volume과 신규 깊이에서 갱신값을 예측한다. GT 깊이와 GT TSDF로 별도 학습한다. (§3.2–3.7)

### 2.2 기여 위치

| 요소 | 구분·내용 |
|---|---|
| 입력·전처리 | 새: depth routing·confidence |
| 좌표·카메라·정합 | 기존: pose·역투영 |
| 표현 | 기존: TSDF·누적 weight |
| 관측모형·렌더링 | 기존: 시선 정렬 local extraction; 외관 학습 없음 |
| 증거·감독·제약 | 새 구성: depth·TSDF 감독, confidence 기각 |
| 초기화·최적화·변경 | 새: 현재 volume을 고려한 비선형 갱신 예측 |
| 추출 | 기존: 등위면 추출 |
| 후처리 | 기존: 누적 weight 기반 outlier filtering |

### 2.3 고정·수정과 피드백

**사실:** routing을 먼저 학습·고정하고 fusion을 학습한다. 공동 정제가 개선되지 않았다고 보고한다. 새 관측을 통합하면서 기존의 유용한 표면정보를 손상시키지 않는 것을 갱신 목표로 명시한다. (§3.7, §4.1)

**코드 사실:** [pipeline.py L110–172](https://github.com/weders/RoutedFusion/blob/dc6e0f582654ffcbd227c95e9a63e9654d45fa77/modules/pipeline.py#L110)는 이전 volume을 읽어 수정한 뒤 다음 프레임에 재사용한다. [L195–260](https://github.com/weders/RoutedFusion/blob/dc6e0f582654ffcbd227c95e9a63e9654d45fa77/modules/pipeline.py#L195)는 fusion 학습에서 routing을 `no_grad`로 실행하고 volume을 detach 저장한다. 즉 **순차 단계가 있지만 지도 상태의 반복 피드백은 존재**한다. 과거 프레임의 routing/pose까지 역전파하는 구조와는 다르다.

### 2.4 검증 범위

**사실:** ShapeNet/ModelNet 공식 train/test에서 합성 잡음을 평가하고 routing ablation을 둔다. 실제 3D Scene 평가는 전 프레임 TSDF의 denoised mesh를 참조로, 매 10번째 프레임의 복원을 비교한다. 정확도·세부·계산량을 제시한다. (§4, Table 1–2)

### 2.5 남은 실패와 전달

**관측된 실패/저자 해석:** Roadsign 결과의 낮은 완전성을 미학습 stereo 잡음·outlier 및 형상 분포와 연결한다. (Fig.6)

**미확인:** 실제 도시 prior에 대한 손상·철거 갱신 실패는 검증되지 않았다. 실제 장면의 위 참조는 독립된 완전 GT가 아니다.

### 2.6 연구 질문으로 연결 — 우리 추론

“기존 형상을 유지할지 바꿀지 원인별 분류 없이 학습 과정에서 보정한다”는 개념은 이미 존재한다. 따라서 연구 목적이 복원에서 보호·수정으로 바뀐다기보다 **복원 과정의 갱신을 무엇으로 정당화할지 구체화한다**고 표현하는 편이 맞다.

- **가까운 비교:** depth confidence만 조절한 GeoGS와, 기존 상태를 조건으로 갱신을 정하는 규칙을 비교한다. 후자를 새 모듈 이름만으로 차별화하지 않는다.
- **방법론 후보:** 참조 감독으로 학습한 센서 오류 통계와 다른 prior 오류·표현 차이가 들어올 때, 현재 관측으로 수정의 타당성을 보완할 수 있는가.
- **최소 비교:** 기존 갱신 규칙, 입력 confidence 교정, 제안한 상태 의존 제어를 같은 초기 구조·영상·갱신 자유도 아래 비교한다. 정확한 구조+불완전 영상과 틀린 구조+충분 영상 모두 필요하다.
- **기각 조건:** 입력 깊이 교정만으로 보존·수정을 동시에 해결하거나, 상태 의존 제어의 이득이 추가 학습정보·표현 자유도에서만 나오면 새 갱신 원리라는 주장은 기각한다.

## 3. 두 선행이 남기는 핵심 비교

| 질문 | SenFuNet | RoutedFusion | 우리에게 남는 검증 질문 |
|---|---|---|---|
| 국소 가중을 이미 쓰는가 | 센서별 상대 α | 관측 confidence와 volume 조건부 갱신 | 가중/갱신 자체를 신규성에서 제외 |
| 오류 원인의 명시 분류가 필수인가 | 원인별 검출기 없이 지도학습 | 원인별 검출기 없이 지도학습 | 분류 생략 자체를 신규성에서 제외 |
| 보존과 수정이 복원 안에 있는가 | 선택·혼합·기각의 결과 | 갱신 목표에 명시 | 목적 확장보다 보정 원리 구체화 |
| 적응 제어 뒤 남는 오류가 확인됐는가 | 잘못된 선택·평균화·겹친 outlier | 분포 차이가 있는 thin scene의 완전성 | 같은 실패가 우리 입력에서 발생하는지 확인 |

위 표의 마지막 열은 연구 설계이며 과학적 결론이 아니다. 이 문헌의 잔여 오류를 GeoGS의 P1/P2/P3 원인으로 복사하지 않는다. 현재성·표현·정합 차이 중 실제로 기존 제어의 근거가 무너지는 조건을 찾아야 한다.

## 4. 검토 기록과 인계

- ECVA PDF 재개 요청에서 일시적 fetch timeout이 발생했다. 처음 확보한 PDF와 보충 포함 arXiv v2 HTML로 계속 확인했다.
- RoutedFusion CVF PDF 주소는 tool fetch 실패였다. arXiv v2 본문과 공식 코드로 확인했으며 PDF 특정 페이지 번호는 추가로 만들지 않았다.
- 이전 문서·memory는 검색 색인으로만 사용했다. 특히 SenFuNet GT 요구와 공식 code pin은 이번 원문·코드에서 재확인했다.
- 다음 검토는 SenFuNet Appendix J의 세 실패를 현재의 prior/RGB 감독 관계와 연결할 수 있는지다. 우선 지표 평균보다 동일 표면에서 **선택이 잘못됐는지, 후보가 이미 틀렸는지, 수정 자유도가 막혔는지**를 구분한다.
- 실제 방법 실행·학습 요청으로 해석하지 않는다. `scientific_verdict: null`.
