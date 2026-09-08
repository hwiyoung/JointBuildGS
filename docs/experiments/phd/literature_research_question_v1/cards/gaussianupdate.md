# GaussianUpdate — 조명·기하 갱신과 시기별 기억

- 상태: 문헌 감사, 2026-09-09. `scientific_verdict: null`.
- 식별: Zeng et al., *GaussianUpdate: Continual 3D Gaussian Splatting Update for Changing Environments*, ICCV 2025. arXiv **2508.08867v1, 2025-08-12** 및 저자 camera-ready PDF·supplement를 직접 확인.
- 출처: [arXiv 전문](https://arxiv.org/html/2508.08867v1), [저자 camera-ready](https://raw.githubusercontent.com/BoMingZhao/open_access_assets/main/GaussianUpdate/UpdateGaussian2025ICCV_cameraReady.pdf), [supplement](https://raw.githubusercontent.com/BoMingZhao/open_access_assets/main/GaussianUpdate/UpdateGaussian2025ICCV_supp.pdf), [공식 프로젝트](https://zju3dv.github.io/GaussianUpdate/).
- 구현: 공식 프로젝트·저자 연결·제목 검색에서 논문/영상 asset은 확인했으나 **학습 소스 저장소와 commit은 미확인**. 공개 구현이 없다고 단정하지 않는다. 수식과 서술의 동작을 실행으로 검증하지 않았다.
- 확인 PDF SHA-256: camera-ready `af48f95aedb799e904d69d1a368a208e9354dcf2b28f83885cfe49fdd61e8ec8`; supplement `6b97de676b0800eced7b8e5d84fbd6b8abb24961a35bcecc91592a2b72d00edb`. 원문은 임시 열람용이며 저장소에 재배포하지 않았다.
- 비교 지위: 기존 3DGS를 현재 RGB로 갱신하는 직접 비교 후보. 외부 무색 측량기하→표면 복원의 직접 동등 입력은 아니다.

## 1. 문제와 입출력

기존 GS, 신규 다중뷰 RGB·자세, 과거 카메라로 시기별 렌더와 기하 변경을 보존한다. 실제 관측은 RGB이며 MVS 초기점과 신규 SfM 점은 파생 기하다. SAM은 사전학습 정보, replay 영상은 이전 모델의 생성 감독이다. 별도 ALS/LoD는 받지 않는다. 시기 내 영상을 하나의 상태로 취급하고 공통 자세를 입력받는다. [원문 §3, Fig.2, PDF pp.3–5](https://arxiv.org/html/2508.08867v1)

우리 해석: 조명과 배치 변화를 구분할 불변영역, 새 물체의 SfM 지지, 기존 GS가 렌더 가능한 품질이어야 한다. 자세 오류·자산 품질이 통제되지 않은 입력에서의 허용범위는 미확인이다. 미관측부 replay는 과거 지식을 전달하지만 현재성을 새로 관측한 것이 아니다.

## 2. 기여의 위치

| 요소 | 분류 | 확인 내용 |
|---|---|---|
| 입력·전처리 | 새+사용 | SAM instance IoU 기반 layout-invariant mask; SAM·MVS·SfM 사용 |
| 좌표·카메라·정합 | 사용/미확인 | 입력 pose와 COLMAP; 후단으로 camera를 재추정하는 변수는 확인되지 않음 |
| 표현 | 새+사용 | 기존 GS + 4D hash/MLP 외관모델 + 시기별 visibility pool |
| 관측모형·렌더링 | 사용+새 | 표준 GS 합성; 시간 입력으로 scaling·SH 증분을 생성 |
| 증거 사용·감독·제약 | 새+사용 | 불변영역 사진감독, removal factor 정규화, 과거 렌더 replay |
| 초기화·최적화·모델 변경 | 새+사용 | 외관→배치→공동 refinement; SfM 신규점, densification, removal/importance pruning |
| 추출·후처리 | 새/미확인 | 시기별 가시성·변경 시각화; 정확한 surface mesh 추출·평가는 미확인 |

근거: [원문 §3.2–3.3, Eqs.7–15](https://arxiv.org/html/2508.08867v1), [supp. §A–B, p.1](https://raw.githubusercontent.com/BoMingZhao/open_access_assets/main/GaussianUpdate/UpdateGaussian2025ICCV_supp.pdf). 외관모델 출력에 **Gaussian scale**이 포함되므로 '1단계는 색만 바꾼다'고 요약하면 부정확하다.

## 3. 무엇을 고정하고 무엇을 수정하는가

| 단계/상태 | 수정 변수 | 고정·강한 제약 |
|---|---|---|
| 외관 갱신 | hash/MLP, 시간별 scale·SH 증분 | 기존 base GS; layout-invariant mask 밖 사진오차는 제외; densification 닫힘 |
| 배치 갱신 | 기존 점 removal factor, 신규 Gaussian 속성·개수 | 앞서 학습한 외관모델 고정; removal의 이진화를 유도 |
| 공동 refinement | 외관모델+신규 Gaussian 속성 | 이전 제거결정의 완전 재탐색이나 pose 변경은 미확인 |
| 역사 보존 | 시기별 active/inactive, 과거 pose에서 replay | 과거 사진은 저장하지 않음; 이전 모델을 감독원으로 재사용 |

흐름: `이전 GS 렌더 + 현재 RGB → SAM 불변영역 → 외관 fit → [SfM 추가점 + 사진잔차→removal] → 외관↔신규 GS 공동 refinement → visibility/replay`. 학습된 제거변수·렌더 중요도가 모델 개수를 바꾸는 feedback이며, 마지막 단계는 앞단 외관추정도 수정한다. **단계형을 이유로 일방향이라고 분류할 수 없다.** 원영상·camera·SAM feature를 학습 중 새로 관측하는 것은 아니다. [원문 §3.2–3.3](https://arxiv.org/html/2508.08867v1)

고정 이유는 shape/appearance 간섭과 망각 통제다. 이를 풀면 관측부족에서 과거 구조의 변형이나 조명오차를 기하로 설명할 가능성이 있다(우리 추론). 반대로 고정이 잘못된 base 구조를 보존하는 경우의 오차는 실험에서 따로 분리되지 않았다.

## 4. 실제 검증 범위

| 항목 | 확인 범위·한계 |
|---|---|
| 데이터/분할 | WAT 실내외 10장면, Synthetic NeRF 8장면; 후자는 정적 장면의 학습영상을 10개 순차 subset으로 나눈 망각 시험. WAT 정확한 test membership은 본문만으로 미확인 |
| 비교 | replay 없는 자체 baseline, CLNeRF, 4DGS, 모든 과거사진 memory replay인 UB. 4DGS는 모든 시기를 함께 입력하므로 정보 접근 조건이 다름 |
| ablation | removal, sparse addition, 불변 mask 제거; 각자 효과는 확인하나 전체 순차법 대 공동법의 보편 우위는 분리하지 않음 |
| 성과·악화 | WAT 대체로 향상하나 Kitchen PSNR은 CLNeRF 28.40, 본 방법 28.02. SSIM은 본 방법 우세. 과거 시기 렌더의 작은 감소도 남음 |
| 평가 대상 | PSNR/SSIM, 34 FPS, 시기별 변경 시각화. 독립 표면정확도·완전성·기하 손상률·판정 calibration은 미평가 |

근거: [원문 §4, Tables 1–4, Fig.3–5, PDF pp.6–8](https://arxiv.org/html/2508.08867v1). [supp. §F–G, pp.3–5](https://raw.githubusercontent.com/BoMingZhao/open_access_assets/main/GaussianUpdate/UpdateGaussian2025ICCV_supp.pdf)는 Tanks&Temples의 정적 순차분할, 3DGStream 비교, 한 장면 iteration 배분 비교, 점 개수 절약도 보고한다. 단, supp. Table 1 평균(26.31/0.83)과 본문 Table 3 full(26.55/0.844)은 일치하지 않으므로 집계조건 확인 없이 합치지 않는다. 870k 대 1.5M 점은 **점 개수**이며 byte 단위 전체 메모리 비교로 바꾸지 않는다.

## 5. 남은 오류와 전달 경로

| 구분 | 남은 오류·조건 | 전달 경로·대안 원인 |
|---|---|---|
| 저자 보고·관측 실패 서술 | 거울 등 강반사에서 기하·외관 오류 | 반사 영상→표현/관측모형 부적합→갱신 오류. 반사 원인을 통제한 독립 ablation은 없음 |
| 원문 사실·ablation 실패 | 불변 mask 제거 시 사라진 물체가 남음 | 배치변화를 외관으로 먼저 설명→removal 증거 약화. 전체법의 모든 실행이 이 실패를 보인다는 뜻은 아님 |
| 원문 사실·잔여 망각 | Table 4 과거 T1 PSNR 26.92→26.84 | 동일 과거 시기 재평가의 작은 악화; 정확한 원인 분리는 미확인 |
| 우리 추론·미평가 | 기존 모델 오류의 replay 재주입; 저가시성 유효 구조 importance prune | 입력오류→생성 감독 또는 pruning→최종 오류 가능성. 실제 측량 기하 손실은 미측정 |

근거: [원문 §4.3·§5 Limitations, Table 4](https://arxiv.org/html/2508.08867v1). 정합/가림/입력기하 오류와 실제 변화를 동시에 구분하는 성능이 미평가라는 사실을 방법 부재의 증거로 쓰지 않는다.

## 6. 연구 공백 후보

이미 조명·기하 변경 분리, 과거정보 유지, 모델 추가·삭제, 최종 공동 refinement가 있다. **CL-Splats의 전역조명 한계를 채우는 것만으로 공백을 선언할 수 없다.**

남는 후보는 사진합성 성공과 독립 기하 보존/개선이 갈라지는 조건에서 수정 범위를 결정하는 문제다. 우선 지위는 검증 부족이며, 정확도가 다른 외부자산 입력은 적용 조건 차이다. 원문 결과만으로 명시적 source decision이 필요하다고 결론낼 수 없다.

가장 가까운 단순 조합은 강건 정합+GaussianUpdate+현재관측 지지/보수적 pruning이다. 최소 비교는 동일 자산·현재뷰에서 무갱신/정합만/전체 fine-tune/CL/본 방법/이 조합이며, 조명-only·기하오류-only·진짜변경·가림과 혼합 조건을 분리한다. 새 실험은 별도 승인 뒤 수행한다.

기각 조건: 조합으로 유효부 악화와 변경부 결손을 함께 줄이면 추가 공동/판정법 필요성을 기각한다. 미관측 영역은 정답 판정 대상으로 억지로 사용하지 않는다. 렌더 개선만 있고 표면 개선이 없으면 기하 주장 기각, 개선이 오직 더 많은 SfM 지지에서 오면 최적화 방법 기여를 축소한다.
