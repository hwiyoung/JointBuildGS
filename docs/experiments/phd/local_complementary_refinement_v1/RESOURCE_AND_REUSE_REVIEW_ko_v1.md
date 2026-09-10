# 국소 상보 가중 refinement — 자원과 기존 상태 재사용 검토

- 검토일: 2026-09-10 22:17–22:24 KST
- 상태: `READ_ONLY_RESOURCE_REVIEW / NEW_METHOD_RUNTIME_UNMEASURED`
- scientific_verdict: null
- 범위: 완료된 기존 상태·입력·작은 영수증/CSV·현재 자원의 읽기 전용 확인. 이 검토에서는 학습·추론·렌더·재구성·GPU 계산을 실행하지 않았다. CPU 전용 Docker에서 기존 자원 CSV만 집계했고 이 문서만 새로 작성했다.
- 사용자 최신 실행 승인은 상위 작업이 처리한다. 이 문서는 기존 실행을 재시작하거나 기존 경로에 쓰는 실행기가 아니다.

## 1. 결론과 우선순위

세 지역의 complete Anchor8k와 원 입력·공식 실행 이미지가 존재한다. 사용자는 후속 답변에서 "완료까지 진행해도 됨"으로 전체18조건 진행을 허용했다. 신규 상보 가중의 `.005 × native/release × P1/P2/P3` 여섯 조건을 먼저 닫고, `.0005` 여섯 조건, 마지막으로 `0` 여섯 조건을 진행하는 순서가 적절하다. 첫 여섯 조건 안에서는 상대적으로 자원 부담이 낮고 회복·손상이 함께 관찰된 P2의 native/release 대응 쌍, P1 대응 쌍, P3 대응 쌍 순서를 제안한다. 이는 실행 우선순위이며 유리한 결과만 선택하는 규칙이 아니다.

기존 18개 학습 driver 합 28.198845시간의 대부분은 이미 Anchor 재사용이다. 새 계획이 Anchor를 재사용한다고 이 합에서 8/30을 일괄 빼면 안 된다. 기존 P2/P3 원설정에만 포함된 초기 prefix를 빼면 약 27.875346시간이며, 두 GPU의 이상적 병렬 하한은 약 13.94시간이다. 새 가중에 의한 개수·계산 변화는 미측정이다.

| 신규 범위 | 대응하는 기존 refinement 근사 합 | 두 GPU 이상적 합/2 | 계획용 학습·준비 여유 범위 |
|---|---:|---:|---:|
| `.005` 여섯 조건 | 9.711834 h | 4.855917 h | 약 6–7 h |
| `.0005` 추가 여섯 조건 | 9.155041 h | 4.577521 h | 약 5.5–6.5 h |
| `0` 추가 여섯 조건 | 9.008471 h | 4.504236 h | 약 5.5–6.5 h |
| 전체 18조건 | 27.875346 h | 13.937673 h | 약 17–20 h |

여유 범위는 관측된 새 방법 시간이 아니라 약 20–40%의 계획 여유를 둔 추정이다. native/release를 지역별 동시 쌍으로 처리하면 `.005` 여섯 조건의 기존 시간상 하한은 쌍의 더 느린 시간을 합쳐 약 5.06시간이다. 입력 확인·새 구현 검증·가중 맵 준비·대기·실패 재시도·마지막 상태 저장·추출·평가까지 포함한 완료 시각을 보장하지 않는다. 기존 18조건의 렌더/필수1024 추출·영상 지표·보조 추출 driver는 별도로 합 2.228905시간이었고, UAS 기하 평가·viewer 등은 여기에 포함되지 않았다. 과거 선택 고해상도 OOM 비용도 이 과거 부가 비용 안에 있으므로 새 계획에서 그대로 반복할 필요는 없다.

## 2. 정확한 재사용 경로

기존 task root의 실제 절대 경로는 다음과 같다.

`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`

아래 상대 경로는 모두 이 task root 기준이다. 경로·작은 receipt·선언 hash를 확인했으며, 이 검토에서 큰 checkpoint를 로드하거나 전부 재해시하지 않았다.

| 지역 | complete Anchor 디렉터리 | receipt에 기록된 checkpoint SHA256 | 초기 Gaussian 수 |
|---|---|---|---:|
| P1 | `runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000` | `c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274` | 1,136,384 |
| P2 | `runs_allocator_v2/P2/D005_Pnative/model/jbgs_complete/iteration_8000` | `91bc9ad74b115c37d4ae35ec4eb197832e730be165d36f52ebe4bb291f1ebcfd` | 1,625,820 |
| P3 | `runs_allocator_v2/P3/D005_Pnative/model/jbgs_complete/iteration_8000` | `3b0de04d99435e36d05ffca49951976352bd663192cce14e59f2bddb58bdf567` | 1,235,876 |

각 디렉터리에 `checkpoint.pth`, `point_cloud.ply`, `receipt.json`이 있으며, 세 receipt 모두 iteration8000·`after_protection_registration: true`다. 정확한 복원은 checkpoint의 모델/optimizer·보호·controller·RNG·카메라 stack을 사용해야 하며 PLY만으로 대신하지 않는다.

| 재사용 대상 | task root 내 경로 / 저장소 경로 | 역할 |
|---|---|---|
| 지역 scene | `inputs/{P1,P2,P3}/scene` | 기존 영상·카메라 scene; 세 경로 존재 확인 |
| 봉인 입력 | `inputs/{지역}/input_manifest.json` | 원 실행 config SHA `b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4`에 결박 |
| 감독·보호 입력 | `inputs/{지역}/prior`, `inputs/{지역}/da3`, `inputs/{지역}/initialization/lod2_pcd.ply` | manifest의 `training_paths`; 새 target 생성 없이 동일 bytes를 재사용할 출처 |
| 원 공식 source | `sources/GeoGS` | 공식 commit `db40c95c657ec03ff21c83cb99cf39f4e90247a6`의 보존 출처 |
| 기존 실제 실행 source | `sources/GeoGS-state-camera-v1` | 완전 상태·카메라 adapter가 추가된 기존 실행본; `train.py`, `jbgs_state.py` 존재 확인 |
| 검증 gate | `parity_allocator_v2/{지역}/anchor_gate.json` | 복원 직후 상태 확인의 기존 계보; 이후 궤적 bitwise 동일성의 증거가 아님 |
| 공식 환경 | `jointbuildgs:geogs-official-db40c95-compat-v1` | 로컬 image ID가 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`와 일치 |
| 기존 지역 launcher | `scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh` | Docker mount·CPU8/RAM32GiB·단일 GPU 설정의 재사용 설계 참고 |
| 기존 지역 driver | `scripts/phd/geogs_p1p2p3_v1/run_regional_phase.py` | 입력 seal 확인, `--jbgs_resume_full`, release 설정, receipt 생성의 참고 |
| 경로 resolver | `artifacts/manifests/geogs_p1p2p3_v1.yaml`, `configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json` | 기존 task 및 P1 예외 Anchor 위치를 정의 |

기존 launcher는 원 6조건 ID·원 execution contract·기존 출력 경로에 묶여 있고 이미 존재하는 학습 경로를 거부한다. 원 driver도 입력 manifest의 원 config hash 일치를 요구한다. 따라서 새 가중 조건은 이 파일을 그대로 실행하거나 원 contract를 바꾸는 방식이 아니라, 새 task source/config/output의 별도 launcher에서 원 입력 seal과 새 변경 계보를 함께 결박해야 한다. 기존 source·input·Anchor는 read-only로 연결하고 새 출력만 별도 경로에 쓴다. 학습 컨테이너에 broad artifact root나 평가 참조를 마운트하지 않는다.

## 3. Anchor 비용 분리의 근거

기존 `evaluation/summary/resource_summary.csv`의 `FINAL_RUN_PHASE/train` 18행을 집계했다. P1 여섯 조건은 모두 iteration8000에서 재개했고, P2/P3 각 원설정만 iteration0에서 시작했다. 따라서 전체 driver 합에서 빼는 것은 P2 584.142659초와 P3 580.454742초의 Anchor trace prefix뿐이다.

`(101515.842759 - 584.142659 - 580.454742) / 3600 = 27.875346 h`

P1 Anchor prefix 533.829170초는 기존 주18개 합 밖의 원 실패 시도에 들어 있으므로 다시 빼지 않는다. 이 prefix는 process import부터 step8000 trace까지이고 Anchor 직렬화 비용은 빠져 있다. driver wall과 trace prefix의 차감은 새 refinement 예산을 위한 근사이며 순수 GPU 시간이나 exact refinement 비용으로 이름 붙이지 않는다. 기존 실행의 반복 실패 비용도 새 성공 시간 추정에 합산하지 않는다.

| 지역 | 기존 여섯 조건의 refinement 근사 합 | 기존 `.005` native/release 각각의 근사 |
|---|---:|---:|
| P1 | 9.941018 h | 1.754643 / 1.730874 h |
| P2 | 7.507679 h | 1.397240 / 1.397629 h |
| P3 | 10.426649 h | 1.520199 / 1.911249 h |

새 국소 가중은 Gaussian 생성·삭제와 controller 반응을 바꿀 수 있으므로 실제 첫 대응 쌍의 trace로 나머지 예산을 갱신해야 한다. 같은 step 수를 같은 wall time 또는 같은 primitive 연산량이라고 부르지 않는다. `.0` 수준에서는 prior depth 항은 0이지만 상보 a는 영상 depth 항을 여전히 조절하고 Anchor·보호 이력도 남는다.

## 4. 현재 자원 표본과 보존할 작업

2026-09-10 22:17 KST의 읽기 전용 표본이다. 이후 가용성을 예약하거나 계속 보장한 결과가 아니다.

| 항목 | 확인 값 | 실행 계획상의 의미 |
|---|---|---|
| GPU0 | RTX3090 24576MiB, used466MiB, free23657MiB, util0% | remote desktop PID72937의 compute 메모리260MiB가 있음; 해당 프로세스 유지 |
| GPU1 | RTX3090 24576MiB, used91MiB, free24034MiB, util0% | 조회 시 다른 compute app 없음 |
| 호스트 RAM | total125GiB, available 약70GiB | 기존 32GiB cap 두 학습의 상한 합은64GiB; 실제 사용·가용량을 재확인하고 RAM을 더 쓰는 추출을 함께 겹치지 않도록 계획 |
| swap | 2GiB 사용, 가용0 | swap 여유를 신규 작업의 메모리 확보 수단으로 가정하지 않음 |
| 외부 HDD | 약2.0TiB 가용 | 새 출력은 외부 task 경로에 저장 |
| Docker root가 있는 SSD | 약24GiB 가용 | 기존 이미지 재사용; 모델·결과를 container writable layer에 남기지 않음 |
| 기존 CPU 작업 | Chrome/SwiftShader 장기 프로세스 두 개가 ps에서 높은 CPU 사용률; loadavg 약24 | 기존 프로세스를 종료하거나 재시작하지 않음; 동일 CPU cap이어도 과거 wall time과 달라질 수 있음 |

`docker ps`에는 기존 viewer·플랫폼·DB 등 서비스가 있었고 학습 컨테이너는 관측되지 않았다. 이것을 모든 시스템의 유휴·health 확인으로 확대하지 않는다. 현재 GPU 조회에서 학습 compute app도 관측되지 않았다. 기존 서비스·브라우저·remote desktop은 그대로 둔다.

기존 성공 학습의 child RSS 표본 최대는 약22.29GiB, PyTorch peak allocated는 약22.55GiB였고 reserved는 약23.12GiB까지 기록됐다. P1 release의 VRAM 여유가 작았으며 보조 반복 P1/P2 CUDA OOM 계보도 있다. 새 loss에 필요한 전체 해상도 tensor를 추가해도 동일 메모리로 끝난다고 보장하지 않는다. 이 보고는 batch/해상도/학습량/생성삭제 정책을 줄이라고 제안하지 않으며, 변경이 필요하면 별도 실행 편차로 명시해야 한다.

기존 `runs_allocator_v2/{P1,P2,P3}`의 현지 디스크 사용량은 합 165,197,900KiB, 약157.55GiB다. 원 입력·공통 Anchor를 복제하지 않는 새 18조건의 저장 계획은 우선 약0.2TiB와 별도 진단/추출 여유를 잡을 수 있지만, 이는 기존 run 경로를 기준으로 한 근사다. 생성 개수나 저장 checkpoint 수가 늘면 확대된다. 기존 파일·실패 경로·서비스를 삭제하여 공간을 확보하지 않았다.

## 5. 검토 재현 정보와 한계

- 자원 CSV SHA256: `596ad629b5ab3d723a5ff89817deecccb063bf315924c422f7af63bc7988d11b`.
- 기존 launcher SHA256: `d644ff6a4a773587076ca60808c879a78a934f94879db72aecb7384ef97c99ac`.
- 기존 Python driver SHA256: `5ef37fd3a9da418a76019b6adcb93cea5050466f6d2e624171472d6966aafa9a`.
- CSV 집계는 고정 공식 이미지의 `python`에서 CPU1·RAM512MiB·network none·read-only root로 실행했으며 CSV 단일 파일만 `/resource_summary.csv:ro`에 연결했다. GPU 장치를 요청하지 않았고 torch/native project module을 import하지 않았다.
- 집계 원리: `csv.DictReader` → `phase=train, cost_category=FINAL_RUN_PHASE` 18행 선택 → region별 `shared_anchor_prefix` 조회 → `training_start_iteration=0`인 두 행에서만 해당 prefix 차감 → 지역·계수별 합. 입력 CSV를 수정하지 않았다.
- 시스템 표본 명령: `nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free,utilization.gpu --format=csv`, compute-app 조회, `free -h`, `df -h`, `docker ps`, `ps`, `/proc/loadavg`. 서비스 제어 명령은 실행하지 않았다.
- 경로 확인 중 아직 생성되지 않은 새 문서 디렉터리의 `ls`는 exit2를 반환했다. 기존 payload 접근 실패가 아니라 새 보고 경로가 아직 없다는 확인이었으며, 이후 이 문서를 해당 새 경로에 작성했다.

기존 문헌·인계 파일에 남은 계획-only 문구가 사용자 최신 실행 승인을 취소하지 않는다. 다만 이 독립 자원 검토 자체는 실행을 시작하지 않으며, 새 구현·조건·실제 입력/상태 결박·자원 gate는 상위 작업의 새 실험 계보에서 처리한다.
