# R1–R5 통합 6화면 비교 및 백그라운드 실행

- Task: `PHD-R1R5-COMPARISON-v1`
- 사용자 지시: 2026-09-17 R2–R5도 R1처럼 구역을 나누고, 기존 네 화면에 DA3 및 보정 구역 prior weight 0을 추가한다. 실험 수행은 토큰 절약을 위해 백그라운드로 실행한다.
- 상태: **기본 15조건의 30k 학습·메쉬·게시 완료 / 추가 R1 원인 대조 실행 중**.
  전체 Z 구역의 [1차 입력 일치도 분석](RESULT_ANALYSIS_20260918_ko.md)을 완료했다.
- `scientific_verdict: null`; 정규 gsplat E1–E6와 구분하는 ALS-adapted GeoGS 개발 비교다.
- 통합 뷰어: <http://127.0.0.1:8913/>. 기존 R1 8912는 보존한다.

### 2026-09-18 확인

20:26 KST: R2 DA3/prior0 복구까지 통과하여 기본 **15/15 완료**.
추가 R1 matched keep이 진행 중이고 matched release는 같은 GPU 0에서 후속 실행한다.
전체 결과 분석은 `result_analysis_20260918T203139_v3/`의 동일 표본 거리 진단이다.
독립 정확도 또는 전체 기하 품질 판정과 구분한다.

18:34 KST 후속: 기존 R4/R5까지 **13/15 조건의 학습·메쉬 완료**.
남은 R2 DA3/prior0는 사용자의 복구 지시에 따라 분할 렌더로 새 실행을 시작했다.
`jbgs-r1r2-causal-recovery-20260918.service`에서 두 조건의 preflight가 PASS했고
GPU 0/1에서 각각 본 학습을 진행한다.
R1 Z06은 168.43m scale Gaussian의 직접 렌더 기여를 확인했으며 같은 GPU의
prior 유지/해제 대조를 뒤에 배치했다. [추적·복구 기록](CAUSAL_RECOVERY_20260918_ko.md).
아래 시점 기록은 당시 상태로 보존한다.

16:54 KST: **최종 학습+추출 완료 9/15, 학습 완료·추출 중/대기 2,
학습 대기 2, 실패 보류 2**다. R2 MVS는 30k 및 메쉬 PASS다. R2 DA3와
국소 prior0는 각각 14,860/14,740회 이후 CUDA OOM으로 실패했다.
R3/R4 DA3는 메쉬까지 PASS, R3 prior0는 학습 PASS·추출 중,
R5 DA3는 학습 PASS·추출 자원 대기, R4/R5 prior0는 대기다.
독립 systemd 서비스는 계속 실행 중이며 실패 조건을 자동 반복하지 않는다.
시점 증거: `sky_crop_audit_20260918/live_status_at_display_fix.json`.

뷰어 v5는 **R1 조건별 geometry 높이 범위 불일치**를 수정했다. 기존 R1
대조군은 Z `[-90,80]`, 신규 DA3/prior0는 MVS camera-fit 범위인
`[-81.285965,-1.835385]`로 잘려 있었다. prior0의 원본 하늘 표본은 여전히
약 66.131m이며 높은 메쉬도 존재한다. 따라서 prior0에서 하늘이 사라졌다는
화면 해석은 잘못됐다. 같은 crop으로 게시한 실제 HTTP mesh의 bytes/hash/높이
검증 PASS, Z06 플로터의 3,450개 표시 정점 hash도 이전과 동일하다.
기존 cache와 원본 모델/메쉬는 보존했고 새 GPU 실험은 추가하지 않았다.
상세: [하늘 진단](R1_SKY_COMPARISON_ko.md), [플로터 진단](R1_Z06_FLOATER_ko.md),
[오류 기록](ISSUES_ko_v1.md). v5 검증은 HTTP geometry 검사이며 전체 브라우저
시각 검사 재수행을 뜻하지 않는다.

15:22 KST: 병렬 관리 명령의 systemd 옵션 호환 오류와 GPU 0 화면 사용률 대기를
확인해 `jbgs-r1r5-parallel-recovery-20260918T062211Z.service`로 복구했다.
완료된 R1 prior0·R4 DA3와 R3 학습은 보존하고 R3 표면 추출부터 재개했다.
상세 경과·검증은 [이슈 기록](ISSUES_ko_v1.md)을 따른다. 아래 11:21의 ETA는
이후 발견된 큐 지연을 포함하지 않은 당시 조건부 예상이다.

11:21 KST: 사용자 속도 개선 요청으로 GPU 0·1 병렬 큐
`jbgs-r1r5-parallel-20260918T022117Z.service`를 시작했다. 실행 중 R3 DA3는
컨테이너를 그대로 인계하고 GPU 0에서 R1 국소 prior 0 사전검증을 시작했다.
학습 조건은 유지하며 RAM 64 GiB 예약 한도 안에서 두 학습을 병행하고 추출은
직렬화한다. 기존 정상 잔여 8조건의 11–14시간 예상은 약 6–8시간으로 갱신한다.
R2 DA3 실패 보류는 이 완료 예상에 포함되지 않는다.
현재 실행 관리·검증·조건부 예상은 [병렬화 기록](ACCELERATION_20260918_ko.md)을 따른다.
아래 단일 GPU 실행과 시간 예상은 전환 전 이력이다.

11:06 KST 추가: R2 DA3 allocator 재실행도 14,860회 이후 CUDA OOM으로 종료했다.
현재 완료 6개 / 진행·대기 8개 / 실패 보류 1개이며 R3 DA3로 넘어갔다. 아래 ETA는
실패 발생 전 조건부 기록이다. 남은 정상 큐의 예상과 실패한 R2까지 포함한 전체
완료 시각은 구분한다. 전체 완료 ETA는 추가 메모리 대응 전에는 확정하지 않는다.

11:04 KST: 최종 조건 6/15 완료, DA3 R2–R5 및 국소 prior 0 R1–R5의 9개 조건이
남았다. R2는 14,460회 실행 중이었다. 지역별 MVS 학습 실측 3,797–4,610초,
R1 DA3/MVS 학습시간 비 1.218, 남은 추출·사전검증·추론 시간을 합산한 운영상
예상 잔여는 약 12.75시간(약 11.5–15.9시간 범위)이다. 중심 예상은 9월18일
23:50 KST이며 추가 실패·재시도·자원 대기는 포함하지 않는다. 완료 보증이 아니다.

구역 표시 v4: R2–R5 검토 지도는 굵은 청록 경계, 흰 외곽선, 큰 Z 라벨과
R1과 같은 표면 판단 색 범례를 사용한다. 가로로 긴 R2/R3/R5는 위아래 배치로
넓혀 표시한다. 좌표·구역·판단 배열·가중치 마스크는 변경하지 않았다.
별도 `review_display_revision_20260918_v3`의 표시 전용 산출물을 게시하며,
원래 검토 지도와 최초 미게시 표시 초안도 보존한다.

10:49 KST 추가: R2 DA3가 14,740회 이후 GPU OOM으로 중단되어
`resource_recovery_20260918T014542Z`에서 allocator만 `cudaMallocAsync`로 변경했다.
8k 완전 복원·8,100회 사전검증 PASS 후 신규 폴더에 R2 본 학습을 재개했다.
독립 조건은 하나가 실패해도 기록하고 다음 조건으로 진행하며 같은 조건을 무한
재시도하지 않는다. 아래의 최초 global fail-stop 큐 설명은 원래 실행 이력이다.
뷰어 v3는 각 R의 판단 지도·CSV 표·원영상 카드를 본문 아래에 자동 표시한다.
Chromium 검사 19개 PASS. R1에는 [하늘 비교 진단](R1_SKY_COMPARISON_ko.md) 그림도 표시한다.

R1–R5 MVS–GeoGS는 모두 30,000회 학습·TSDF 추출·뷰어 게시 완료다.
DA3–GeoGS는 R1 완료, R2에서 카메라 float64/float32 비교 검사 오류로
07:06 KST 중단됐다. 정확한 float32 동일성 검사로 수정하고 실패 배치 추론
PASS를 확인한 뒤 `jbgs-r1r5-recovery-20260918T010840Z.service`로 잔여 큐를
재개했다. 원래 실패 및 모든 완료 산출물은 보존했다.
상세 원인/증거는 [이슈 기록](ISSUES_ko_v1.md), 자료 링크는
[진행현황·검토자료](STATUS_20260918_ko.md)에 있다.

## 1. 영역마다 여섯 화면

| 화면 | 조건 |
|---|---|
| ALS prior | 입력 ALS 표면 표본, 중립 회색 |
| 현재 MVS | 기존 fused MVS RGB 표본; 구역 판단 색상도 선택 가능 |
| Anchor8k | 해당 영역에서 새로 만든 8,000회 초기 상태 |
| MVS–GeoGS | 같은 Anchor에서 30,000회까지, prior 0.005 |
| DA3–GeoGS | 같은 Anchor에서 image depth만 DA3로 교체, prior 0.005 |
| 보정 구역 prior 0 | 같은 Anchor와 MVS, 검토한 국소 prior 픽셀의 배율만 0, 나머지 1 |

Anchor 단계의 prior 계수는 0.08이다. 모든 분기는 native protection, RGB loss,
기존 정규화 및 dynamic visual-depth controller를 유지한다. 초기 image-depth 계수는
0.05이며 실제 계수를 trace로 기록한다. 국소 prior 0은 초기화·보호·opacity·Gaussian
삭제를 해제하는 조건이 아니다. 하늘·수증기 마스크는 이번 비교에 새 요인으로 넣지 않는다.

R1의 기존 Anchor와 MVS 최종 결과를 정확한 원본 receipt/hash로 재사용한다. 신규
학습은 Anchor 네 개와 최종 분기 14개다. R2–R5 기본 MVS 조건을 먼저 채우고,
R1–R5 DA3 조건, R1–R5 국소 prior 0 조건 순서로 진행한다. 각 분기 앞에서
별도 100회 복원 점검을 실행하고, 본 학습은 원래의 같은 Anchor에서 다시 시작한다.

## 2. 입력과 DA3

| 영역 | train | evaluation | 검토 구역 수(Z00 잔여 포함) |
|---|---:|---:|---:|
| R1 | 588 | 84 | 14 |
| R2 | 221 | 32 | 9 |
| R3 | 303 | 44 | 8 |
| R4 | 102 | 15 | 11 |
| R5 | 252 | 37 | 9 |

승인된 `R1R5_OBJECT_ALIGNED_v1` 경계와 영상 membership을 사용한다. 신규 prior는
R1과 같은 ALS scan/beam 표면, 25m 문맥, 100,000개 표면 샘플 및 두 train 시점 이상
지지 규칙으로 준비했다. 기존 ALS 수직 datum bridge의 불확실성은 그대로다.
원래 preparation helper의 `vertex_membership.npz/in_R1` 키는 신규 영역에서도
해당 region 내부 membership을 뜻하는 호환 필드명이며 R1 좌표를 사용했다는 뜻이 아니다.

DA3는 고정된 공식 DA3NESTED-GIANT-LARGE 모델과 기존 GeoGS helper를 사용한다.
영상은 각 영역의 정확한 train 집합만, 파일명순 균등 연속 최대 8장 배치로 묶는다.
추론 해상도 840, 입력 pose scale 정렬, 원본 크기 cubic upsampling을 유지한다.
R1/P1 등의 기존 DA3 결과를 다른 배치 문맥의 결과로 재사용하지 않는다. 별도
DA3 receipt와 각 depth hash를 검증한 뒤 실제 target 교체를 기록한다.

## 3. 구역 판단과 국소 해제

각 영역의 전체 input atlas와 첫 여섯 선정 원영상을 직접 검토했다. 객체축 지붕·
접면·중정·도로·잔여 경계를 `review_zones.json`에 기록했다. Z00이 전체를 덮고
후속 polygon이 순서대로 덮어써 미할당 XY 영역이 없다. 기존 R1의 14개 구역과
C1 판단은 원본을 재사용했다.

R2–R5의 보정은 **입력 검토에 따른 prior 해제 가설**이다. 실제 변화, MVS 정확성,
prior 오류의 확정 정답이 아니다. 주황을 자동 source authority로 해석하지 않는다.
수목·통로·관측 부족은 임의로 건물 보정에 포함하지 않고 유보한다.

- 현재 표면: 다중시점 지지와 camera span, 반복 source 관계는 R1 감사와 같은 기준.
- 국소 구조: 각 소스 안에서 20개 이웃의 법선 분산 비율 ≤0.06, 이웃 반경 ≤4m.
- 검토한 building context 안의 일치 표면은 보존 후보, prior 결측/뒤쪽 hit는 보완 후보.
- 지정한 구조 검토 구역 중 prior가 앞에 있는 반복 관계만 보정 가설 후보.
- prior 표면도 별도로 현재가 뒤에 있는 3개 이상 관측과 0.67 이상 비율을 요구한다.
- 실제 prior depth 픽셀은 prior ray의 0.5 pixel-center 관례를 유지해 역투영한다.
  가장 가까운 전체 prior 샘플이 보정 후보이고 거리 ≤0.9m인 경우만 남긴다.
- 같은 영상 MVS target이 prior보다 1m 이상 뒤에 있고, MVS endpoint도 별도
  보정 후보 표면에서 ≤1.2m이어야 한다. MVS는 기존 integer RGB ray 관례를 유지한다.
- loss는 원래 valid prior 픽셀 수로 나눈다. 해제한 픽셀 때문에 나머지 픽셀의
  gradient가 커지도록 재정규화하지 않는다.

| 영역 | prior 해제 픽셀 합계 | 하나 이상 적용되는 train 영상 |
|---|---:|---:|
| R1 | 2,342,258 | 99 |
| R2 | 1,193,651 | 46 |
| R3 | 82 | 5 |
| R4 | 2,329 | 30 |
| R5 | 1 | 1 |

이는 저장된 mask의 관측 픽셀 수이며 독립 표면 개수나 실제 loss/gradient 기여
영상 수가 아니다. 실제 sampling과 유효 render depth는 실행 trace에서 따로 확인한다.
특히 R3/R5는 개입이 매우 작아 국소 prior 해제 효과를 보여주는 주 사례로 보기 어렵다.
이 사실을 숨기기 위해 구역이나 threshold를 확대하지 않았다. 모든 조건은 요청대로
큐에 포함하되 적용량을 뷰어에 노출한다.

## 4. 백그라운드 실행과 검증

독립 systemd 사용자 서비스 `jbgs-r1r5-execution-attempt_20260917T132641Z_aa9r3kak`
가 GPU 1 작업을 순차 실행한다. Codex 응답을 종료해도 계속된다. GPU와 RAM이
부족하면 기다리고, 단계 실패 시 로그와 실패 상태를 보존하고 큐를 중지한다.
실패한 실험을 자동 재시도하거나 조건을 자동 완화하지 않는다.

학습은 Docker에서만 실행하고, UAS/LoD2 평가 기하는 학습·마스크·DA3 컨테이너에
제공하지 않는다. MVS의 역사적 producer가 evaluation 영상을 사용한 제약 때문에
독립 정확도 또는 일반화 실험으로 해석하지 않는다.

검증:

- R2–R5 봉인 입력의 hash, 카메라 pose/K, train/evaluation split, native MVS
  resampling, 초기화 표본, upstream source hashes 검증 통과.
- 각 영역의 전체 관측 관계/coverage 감사 receipt 생성 완료.
- 국소 prior loss의 선택 픽셀 gradient 0, 나머지 gradient 불변, Anchor 및 다른
  조건의 native loss 유지에 대한 Docker 단위 검사 2개 통과.
- Chromium 실브라우저 검사 v2 14개 통과: 다섯 영역, 여섯 패널, 실제 prior/MVS
  buffers, 기존 R1 메쉬 표시, Z08 확대, 판단 색상, 패널 확대, 모바일 폭, HTTP/JS 오류 없음.
- 전체 mask의 hash, 정확한 train membership, 배열 형식 및 finite-positive depth
  조건은 별도 `mask_validation/receipt.json`에 기록한다.
- 앞으로 각 단계는 8k 완전 상태의 model/optimizer/RNG/camera order/보호 복원과
  실제 depth 출처·계수·finite gradient를 검사한 뒤 30k/TSDF 결과를 게시한다.

학습/추출 성공과 UI 검사는 기하 정확성 판정이 아니다. 완료 여부는 실행 상태와
receipt를 기준으로 한다. 수동 채팅 모니터링이나 자동 채팅 알림은 설정하지 않았다.

## 5. 재현 및 위치

Resolver: `artifacts/manifests/phd/r1r5_comparison_v1/manifest_v1.yaml`.
준비·감사·리뷰·실행·뷰어 소스는 attempt 안에 각각 snapshot으로 보존한다.
진행 파일은 `execution/status.json`, 원본 모델은 `<R>/anchor|mvs|da3|local_prior0`,
추출은 `<R>/extract_*`, 실제 관측은 `camera_sampling.jsonl`과
`local_prior_trace.jsonl`, 뷰어 상태는 `viewer/data/status.json`이다.

신규 task 구성 driver는 `scripts/phd/r1r5_comparison_v1/`에 있다. 초기 launcher는
현재 task 디렉터리를 다시 실행하거나 덮어쓰는 resume 도구가 아니다. 장애 수정은
원인과 이전 attempt를 보존한 별도 bounded recovery로 수행한다.
