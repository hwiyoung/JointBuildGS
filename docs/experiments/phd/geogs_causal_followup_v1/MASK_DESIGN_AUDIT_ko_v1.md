# GeoGS 보호·수정 제어와 업데이트 마스크의 경계

- 작성: 2026-09-10. 읽기 전용 공식 소스·기존 실행 receipt·원문 확인.
- `scientific_verdict: null`
- 대상 질문: P1/P2의 다른 수정 결과를 설명할 때, GeoGS에 유지·수정 제어가 없는가? 업데이트 마스크를 추가하면 해결되는가?
- 기존 논문 카드는 탐색 색인으로만 사용했다. 공식 소스와 원문을 이번에 직접 확인했다. 새 학습·추론·장면 렌더·메쉬 추출·방법 실험을 실행하지 않았다.

**GeoGS에는 이미 보호 마스크와 수정 억제가 있다. 현재 관측으로 prior의 유효성을 확인한 마스크는 아니다.** 따라서 추가 연구를 ‘마스크가 없는 방법에 마스크를 넣는다’고 설명하면 부정확하다. 가능한 연구 질문은 어떤 증거가 어느 변수의 변경을 허용하거나 제한해야 하는가이다. 이것이 P1/P2의 원인이라는 결론은 아직 아니다.

## 1. 확인한 버전과 실행

공식 소스는 `db40c95c657ec03ff21c83cb99cf39f4e90247a6`이며 이번 확인 시 로컬 checkout의 tracked/untracked status는 깨끗했다. 실행된 adapter 소스의 SHA와 공식 소스를 혼동하지 않는다. 실행 receipt는 별도로 instrumented `train.py`, `jbgs_state.py`, camera adapter 등의 SHA를 기록한다.

- [공식 train.py 고정 버전](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py)
- [공식 Gaussian model 고정 버전](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/scene/gaussian_model.py)
- [P1 실제 실행 receipt](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runs_allocator_v2/P1/D005_Pnative/train_receipt.json)
- [P2 실제 실행 receipt](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runs_allocator_v2/P2/D005_Pnative/train_receipt.json)
- [실행 당시 조건 snapshot](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runs_allocator_v2/P2/D005_Pnative/train_config_snapshot.json)

ALS 적용의 `building` 플래그는 의미적 건물 판별이 아니다. 초기화에 사용한 visibility-retained ALS 표면점과의 근접성을 뜻하며, context 바닥 등도 포함될 수 있다. 정확한 건물 부위만 선별했다는 해석은 금지한다.

## 2. 이미 존재하는 제어

| 제어 | 근거와 실제 동작 | 이것으로 확인하지 않는 것 |
|---|---|---|
| 구조 보호 대상 | `train.py:368–393, 1139–1166`: stage switch 때 Gaussian 중심과 prior 점의 최근접 거리 `<0.2m`로 mask 생성 | prior의 현재 유효성, 정확도, 새 영상이 해당 위치의 수정을 요구하는지 |
| 기하 변화 억제 | `train.py:603–638`: 해당 mask의 xyz·rotation·scale gradient에 기본 0.01 곱함 | 좌표 완전 고정이나 최종 표면 오차의 상한. Adam의 실제 변위가 정확히 1/100이라는 뜻도 아님 |
| 개수 변경 제한 | `gaussian_model.py:396–463`: 보호 대상을 clone/split/prune와 densification gradient 집계에서 제외 | 모든 위치에 부족한 세부가 생길 수 있다는 보장 |
| 색·불투명도 | 위 gradient attenuation의 대상은 xyz·rotation·scale임 | 보호 mask가 SH·opacity까지 완전 고정한다는 해석. `freeze_gaussians` 함수의 존재를 해당 실행 경로와 혼동하지 않음 |
| 구조 깊이 감독 | `train.py:278–324, 805–815, 873–877, 955–961`: 유한 양수 prior 깊이와 렌더 표면 깊이의 L1; anchor 0.08, refinement 0.005/0.0005/0 | 현재 관측과 상충하는 prior 픽셀을 유효성 판정으로 제거하는 기능 |
| 영상 깊이 감독 | 같은 표면 깊이에 DA3 깊이 L1을 적용. refinement에서 활성 | RGB를 사용했다는 것과 동일하지 않음. DA3 추정치 오류가 최종 오류의 유일한 원인이라는 뜻도 아님 |
| RGB 감독 | `train.py:817–819, 955–965`: 전 영상 L1+SSIM과 다른 손실을 합쳐 같은 모델 최적화 | 잔차가 특정 기하 변수로만 흘러간다는 보장 |
| DA3 동적 가중치 | `train.py:879–953`: 깊이·RGB 손실 이력에 따른 scalar 제어 | 픽셀/표면별 prior 정확도나 현재성 판정 |
| DA3 confidence | `train.py:710, 725–727, 792–795, 1259–1260`: 선택적으로 영상 깊이 손실을 confidence 가중 | P1/P2 native primary 실행에서의 사용: 실제 command에 `--use_confidence`, `--da_conf_path`가 없고 기본값은 False이므로 비활성 |

보호 mask는 stage switch에서 정해진 membership을 이후 모델 개수와 함께 관리한다. 새 Gaussian에는 비보호 항목을 추가하고 pruning 때 배열을 함께 줄인다. densification으로 Parameter가 바뀌면 gradient hook을 재등록한다. 이는 매 반복 현재 관측으로 보호 타당성을 재판정하는 경로와 다르다. [공식 model:324–394](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/scene/gaussian_model.py#L324), [train:1050](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L1050)

따라서 **틀린 prior 가까이 있는 Gaussian도 보호될 수 있고, 정확한 prior의 골도 opacity·가시성·주변 Gaussian·깊이 합성·추출에 의해 최종 표면에 충분히 나타나지 않을 수 있다.** 이는 소스에서 도출한 가능한 경로다. P1 또는 P2에서 그 경로가 발생했다는 관측 사실로 올리지 않는다.

## 3. refinement 문제와 DA3 문제를 나누기

refinement는 DA3 단독 처리 단계가 아니다. 구조 깊이·RGB·표면 regularization·DA3 깊이가 합쳐지고, 보호된 변수와 자유로운 변수가 함께 갱신된다. 원인 판별은 아래처럼 나뉜다.

| 기존 자료에서 확인할 관계 | 원인 후보 | mask가 직접 해결하는지 |
|---|---|---|
| 해당 ray의 DA3 자체가 현재 기하와 다름 | DA3 예측, batch/scale 정렬, 가림, 저해상도 또는 관측 부족 | 나쁜 감독을 약화할 후보이나 맞는 형상을 새로 제공하지는 않음 |
| DA3에는 수정할 형상이 있으나 학습 표면 깊이는 prior 쪽에 남음 | prior 감독 충돌, 보호, 표현/opacity, 국소 최적화 | 감독·변수·연산별 제한 조절 후보. 정확한 gradient·membership 추적 필요 |
| 학습 표면 깊이는 맞는데 raw mesh는 틀림 | TSDF와 가시성/깊이 합성·추출 | 학습 update mask가 우선 해법은 아님 |
| raw에는 유효 표면이 있으나 post에서 사라짐 | 연결요소 필터 등 후처리 | 기존 필터/출력 선택부터 검토 |
| P1/P2의 동일해 보이는 구조에 실제 학습 관측 조건이 다름 | 시야각, 가림, 이미지 footprint, 표본 밀도, DA3 batch 구성 | 관측 없는 곳을 update 허용하는 것만으로 해결되지 않음 |

P1과 P2는 사용자가 지적한 ‘바뀌어야 할 큰 지붕이 다르게 반영된 사례’로 먼저 대응해야 한다. P2 골의 보존 문제는 추가로 확인할 별도 요구다. 둘을 하나의 고정된 원인으로 합치지 않는다.

## 4. 업데이트 마스크를 고려한다면 무엇을 마스킹할 것인가

아래는 설계 선택지를 명확히 하기 위한 분해이며, 구현 필요성이나 신규성 판정은 아니다.

| 조정 대상 | 의도 | 하나의 변경/비변경 마스크만 쓸 때의 문제 |
|---|---|---|
| prior 깊이 감독 | 현재 증거와 상충하는 prior의 당김을 풀기 | 기하 변수만 풀고 잘못된 prior 깊이 loss를 남기면 충돌 지속 |
| 영상 깊이 감독 | 국소적으로 부정확한 DA3의 영향 제한 | prior가 틀린 곳까지 DA3를 끄면 수정 증거도 제거 |
| 위치·법선·크기 | 유효 구조 유지, 잘못된 형상 수정 | 영역을 모두 고정하면 같은 면의 필요한 미세 형상 보완도 금지 |
| opacity·SH/색 | 현재 외관 맞춤, 불필요한 기여 제거 | geometry와 같이 고정하면 외관 갱신이 막히고, 자유롭게 두면 잘못된 형상을 외관으로 흡수할 가능성 |
| 생성·삭제·분할 | 결손 생성, 사라진 구조 제거, 세부 표현 능력 확보 | 이동만 허용한다고 결손과 사라짐이 모두 해결되지는 않음 |

사용자의 ‘정확한 구조는 남기고 틀린 것은 바꾼다’는 결과 요구는 타당하다. 다만 실제 알고리즘에는 정답 마스크가 주어지지 않는다. 그 요구를 반드시 원인 분류기나 한 번의 이진 영역 판별로 구현할 필요도 없다. 다중뷰 지지, 깊이·사진 일관성, 가시성, 제안된 수정의 일관된 오차 감소를 이용해 수정의 강도와 방향을 연속적으로 제한하는 방식도 후보다. 이것을 제안하기 전에 기존 제어와 정보 흐름에서 실패 위치를 확인한다.

## 5. 가장 가까운 선행 해결책

**CL-Splats**는 이미 기존 3DGS와 현재 영상의 DINOv2 차이로 변경 mask를 만들고 3D 투표·국소 최적화를 수행하며 비변경 Gaussian을 고정한다. 따라서 국소 mask 갱신·기존 영역 보존이라는 기능 자체는 새롭지 않다. 저자는 얇은 구조에서 영역을 과소 검출하면 필요한 수정이 막히는 실패를 명시한다. 새 mask가 복원을 보장하지 않는 직접 사례다. 단, 외관을 렌더할 수 있는 기존 GS가 입력이며 무색 ALS/LoD를 직접 받는 조건과 다르다. [원문 v2 §3.1–3.3, §9.2·Fig.12](https://arxiv.org/html/2506.21117v2), [프로젝트](https://cl-splats.github.io/)

**GaussianUpdate**는 배치 불변 mask에서 먼저 외관을 조정하고, 기존 Gaussian의 학습 가능한 removal factor와 새 점 초기화로 기하를 갱신한 뒤 공동 정제한다. mask를 빼면 사라진 물체의 차이를 외관 단계에서 설명해 제거가 실패할 수 있다는 ablation을 제시한다. 따라서 외관·기하 갱신 자유도 분리와 제거·추가도 선행 해결책이다. 기존 렌더 가능한 3DGS·현재 RGB를 이용한 갱신 및 렌더 평가이며, 우리 외부 prior의 측량 표면 보존·현재화 성능은 별도 검증 대상이다. 공식 학습 구현 commit은 이번 범위에서 확인하지 않았다. [원문 v1 §3.2, §4.3·Fig.3·Table 3](https://arxiv.org/html/2508.08867v1), [공식 프로젝트](https://zju3dv.github.io/GaussianUpdate/)

무색 기존 자산을 영상으로 이미 정제한 뒤 그 렌더와 같은 현재 사진을 비교하는 경우, 구조 오류가 있어도 학습된 외관이 차이를 줄였을 가능성이 있다. 그러므로 CL-Splats/SAM mask를 단순 이식하면 과거 사진과 현재 사진의 진짜 장면 변화 검출과 같은 문제가 된다고 가정할 수 없다. 이는 입력 차이로부터의 우리 추론이며 해당 논문들의 관측 실패가 아니다.

## 6. 최소 비교와 기각 조건

현재 실행을 추가하지 않는다. 다음 원인 분석 후 방법 설계가 필요할 때의 비교 순서다.

1. 기존 6개 조건에서 P1 수정 대상·P2 큰 변화 대상·P2 보존 대상의 정확한 train ray, prior/DA3 깊이, frozen mask, anchor/final 깊이, raw/post를 대응한다. 평균 수치나 참조의 존재만으로 입력 충분성을 확정하지 않는다.
2. 감독 입력이 틀린 문제이면 정렬·confidence·기존 depth 가중치로 해결되는지 먼저 비교한다. 추출 단계 문제이면 기존 출력/필터 조정부터 비교한다.
3. 제한 경로가 병목이라는 근거가 남으면 전체 가중치/전체 보호 해제와 국소 제어를 비교한다. 보존부 악화와 수정부 개선을 같은 표면 집합에서 동시에 평가한다.
4. 국소 제어가 필요해도 기존 CL-Splats식 갱신 또는 GaussianUpdate식 외관/추가/제거 분리와의 차이를 평가한다. 단순 조합의 성공을 포함한다.

기각 조건: 기존 입력 보정·전체 제어·추출 설정이 보존과 수정을 함께 충족하면 별도 mask 방법 필요성을 낮춘다. 이상적인 수정 영역을 알려줘도 개선되지 않는다면 영역 선택을 핵심 병목으로 보지 않는다. 실제 mask가 필요한 영역을 놓치거나 유효부를 해치면 정답 mask 성능으로 방법 기여를 대신 주장하지 않는다. 렌더만 개선되면 독립 표면 복원 기여를 주장하지 않는다.

이번 기록은 **이미 있는 제어, 아직 없는 유효성 확인, 가능한 원인, 후보 설계를 분리한 정적 감사**다. P1 잔존과 P2 수정의 인과 결론은 해당 위치의 실제 감독·학습·추출 자료를 대조한 종합 문서에 둔다.
