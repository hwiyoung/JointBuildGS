# P1/P2/P3 MVS·PGSR 방식 기하 loss의 실제 preflight Return

- task_id: `PHD-GEOGS-MVS-PGSR-v1`
- 집계 시각: `2026-09-14T14:40:09.487510Z`
- 상태: `PASS_SIX_TECHNICAL_PREFLIGHTS`
- scientific_verdict: null
- Operator HEAD: `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`

P1/P2/P3의 MVS 교체(M)와 MVS + PGSR 방식 기하 loss(MG), 총 6개 실제
GPU preflight가 모두 통과했다. 각 실행은 prior `.005`, native 보호, 같은 지역의
complete Anchor8000에서 100 step만 진행해 iteration8100 상태를 보존했다.
원 입력·같은 Anchor 복원·감독 교체·기하 gradient·짧은 실행의 자원 사용을 확인한
기술 결과이며 지붕·바닥·변화부의 개선 결과가 아니다.

신규 12회 본 학습과 기존 대조 6개의 최종 비교는 별도다. 이 Return은
백그라운드 큐의 시작·완료나 전체 학습·추출·평가 완료를 선언하지 않는다.

## 원 영수증과 집계의 결박

Payload root는 [resolver](../../../../artifacts/manifests/geogs_mvs_pgsr_v1.yaml)의
`phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1`이다.
그 안의 `preflight_summary_v1.json`이 원 영수증·loss trace·gradient trace·source
snapshot의 SHA, 실제 수치, 실행별 복원 결과와 소프트웨어 버전을 함께 보존한다.

| 항목 | SHA256 |
|---|---|
| `preflight_summary_v1.json` | `6c79daa10e248dff73fd545895b5db38a4ff002d933a1840784eafa4c36c7344` |
| `inputs_v2/experiment.json` / 현행 experiment_v2 설정 | `3555f528c7b2c91941c4f9e4812bcf918351605ec6c793c272be7e42a8785c5c` |
| `inputs_v2/receipt.json` | `9c008994d4827a7f1401bd6d6f9fc77484ad88f49880759e63ad86087a98e475` |
| 신규 source provenance | `62b7b9d97ec48c82c5ef3783ccbde82dbdabd4ed62642efca9abe5224063afe3` |
| 6개 실행의 실제 driver snapshot | `550c17a4da12b96343e8d6fcad83a401a73c52bee370eee1146a03abe44bcecf` |
| 집계 script | `c62a46705d87176ee9d0b76aa430cf18cbbec760a7099d3a5c6ed3b6e0d34a76` |

[summarize_preflight.py](../../../../scripts/phd/geogs_mvs_pgsr_v1/summarize_preflight.py)는
각 run의 실제 설정 snapshot·driver SHA·source provenance·입력 binding·complete restore를
교차 확인하고, loss/gradient trace의8001·8100 endpoint와 유한값을 검사했다.
집계 과정은 GPU를 마운트하지 않은 고정 Docker CPU 실행이었다. 원자료 해시가
집계 전후 일치했다. 재현 명령·script 복사본·로그는
`preflight_summary_preparation_20260914T144006Z_kuLm8L/`에 있다.

## 실행별 완료와 자원

모든 경로는 payload root 아래 `preflight/{지역}/{방법}_0.005/`에 있다.
wall time은 각 driver 영수증의 측정값이다. GPU 수치는 gradient trace에 기록한
PyTorch 누적 peak의 최대값이며 MiB(`2^20` bytes)로 표시했다.

| 지역·방법 | attempt | wall seconds | peak allocated MiB | peak reserved MiB | 복원 exact / endpoint |
|---|---|---:|---:|---:|---|
| P1 M | `attempt.IMIQySUd` | 45.42 | 3,658.74 | 16,546 | true /8100 |
| P1 MG | `attempt.ZdEkuOGJ` | 55.34 | 5,518.46 | 21,054 | true /8100 |
| P2 M | `attempt.V38OnSZZ` | 40.25 | 4,181.04 | 23,046 | true /8100 |
| P2 MG | `attempt.zWaYG9SA` | 60.40 | 6,207.20 | 23,632 | true /8100 |
| P3 M | `attempt.lcfos4FL` | 40.26 | 3,965.98 | 22,418 | true /8100 |
| P3 MG | `attempt.i8DrX4lX` | 80.53 | 5,832.81 | 23,578 | true /8100 |

`allocated`는 실제 tensor 등에 할당한 메모리이고 `reserved`는 allocator가 확보한
공간이다. 둘을 합산하거나 reserved를 전부 활성 tensor로 해석하지 않는다.
`gpu.csv`의 nvidia-smi 값은 장치 전체 값으로 다른 프로세스가 포함될 수 있어 위의
process allocator 수치와 구분한다. 짧은 실행에서 reserved가 크게 증가했으므로
후속 densification과 장시간 실행의 메모리 여유는 아직 입증되지 않았다.
이번 측정으로 22,000 step 소요 시간이나 full-run 성공을 외삽하지 않는다.

## 같은 complete Anchor 복원

6개 실행의 실제 `jbgs_restore.json`에서 model/optimizer, controller,
camera order와 viewpoint stack, RNG가 모두 exact=true이며 protection은
`native_exact`였다. iteration8000, release=false, prior coefficient `.005`도 확인했다.
이는 복원 직후 상태의 일치다. M과 MG의 이후 최적화 궤적 일치를 뜻하지 않는다.

| 지역 | 실제 복원 checkpoint SHA256 |
|---|---|
| P1 | `c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274` |
| P2 | `91bc9ad74b115c37d4ae35ec4eb197832e730be165d36f52ebe4bb291f1ebcfd` |
| P3 | `3b0de04d99435e36d05ffca49951976352bd663192cce14e59f2bddb58bdf567` |

각 endpoint의 complete-state producer 영수증과 실행 driver가 검증한 checkpoint/PLY
SHA도 집계 JSON에 보존했다. 이번 작은 집계에서는 큰 checkpoint를 다시 읽지 않고,
실행 시점의 검증 영수증을 결박했다.

`.0005`는 본 실행에서 같은 complete Anchor를 복원한 뒤 기존 scalar prior 계수만
바꾸는 허용된 비교다. 이번 preflight는 `.005`만 실행했으므로 `.0005` preflight가
통과했다고 쓰지 않는다. prior 계수의 선형 변경과 달리 full optimization 궤적·controller
반응은 선형이라고 가정하지 않는다.

## 실제 기하 loss의 유효 표본

아래는 MG에서 관측한 표본이다. `ref`는 reference valid, `sv`는 single-view valid,
`projected`는 이웃으로 투영 가능한 표본, `mv`는 왕복 검사 통과, `NCC`는 patch
photometric 검사 통과 표본이다. 입력 depth 전체 유효 비율과 다른 실행 중 mask다.

| 지역 | iteration | ref | sv | sampled | projected | mv | NCC |
|---|---:|---:|---:|---:|---:|---:|---:|
| P1 |8001|1,406,277|1,395,215|4,096|2,100|962|511|
| P1 |8100|1,413,416|1,406,107|4,096|1,867|533|278|
| P2 |8001|1,404,578|1,392,247|4,096|3,145|2,857|1,311|
| P2 |8100|1,413,013|1,404,950|4,096|2,578|557|266|
| P3 |8001|1,387,113|1,374,430|4,096|1,351|600|187|
| P3 |8100|1,401,405|1,392,425|4,096|3,438|2,190|1,272|

M은 추가 PGSR 항을 적용하지 않아 위 count와 per-term gradient가 기록되지 않는다.
이를 zero-support 실패로 바꾸지 않았다. 모든 실행의8001·8100 loss/total gradient는
유한했으며, 기록된 시점의 MVS 계수는 `.05`, prior 계수는 `.005`였다.
중간 모든 step의 표본과 gradient가 이 Return에 기록된 것은 아니다.

neighbor가 없는 P1/P2/P3의1/2/1카메라는 기존30°·거리깊이비1조건을 유지한 채
single-view-only와 skip 기록을 적용한다. 위 두 endpoint에 실제 MV 지원이 있다는
사실이 모든 카메라에서 MV 지원을 보장하지 않는다.

## 첫 step의 항별 gradient

MG iteration8001에서 svgeo/mvrgb/mvgeom 각각에 대해 xyz·rotation·scaling gradient가
존재하고 유한하며 nonzero element가 있었다. 아래 값은 **loss 계수를 곱하기 전**
개별 항의 최대 절대 gradient이고 native 보호 hook이 적용된 결과다.
계수 또는 optimizer update 크기와 같은 값으로 해석하지 않는다.

| 지역 | 항 | xyz max abs | rotation max abs | scaling max abs |
|---|---|---:|---:|---:|
| P1 |svgeo|0.00292096|0.0480066|0.00550544|
| P1 |mvrgb|0.00858204|0.0353458|0.00367484|
| P1 |mvgeom|0.460478|0.500884|0.241392|
| P2 |svgeo|0.00135857|0.00623138|0.00130507|
| P2 |mvrgb|0.00279516|0.00294103|0.00134478|
| P2 |mvgeom|0.00393601|0.0126699|0.00328496|
| P3 |svgeo|0.00471500|0.0707100|0.0108865|
| P3 |mvrgb|0.00731938|0.0663507|0.0120054|
| P3 |mvgeom|0.0639224|0.103798|0.0479834|

정확한 nonzero count와 원 precision은 각 run의
`model/geometry_first_step_gradients.json` 및 집계 JSON에 있다. gradient가 전달된다는
확인은 필요한 기하가 올바른 방향으로 보정됐다는 검증과 다르다.

## 실행 환경과 해석 경계

6개 영수증의 runtime image ID는 모두
`sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`와 일치했다.
같은 고정 이미지를 GPU 없이 읽어 확인한 버전은 Python3.10.20,
PyTorch2.1.2+cu121(CUDA build12.1), NumPy1.26.4, OpenCV4.8.1,
Open3D0.19.0이다. allocator는 `backend:native,max_split_size_mb:128`이다.

현재 source는 기존 GeoGS expected depth에서 PGSR 방식 기하 loss를 구현한
adaptation이다. 입력 MVS depth와 prior 자체의 scale·정합·시간적 유효성을 공동으로
추정한 결과가 아니다. 실제 RGB/기하 평가, 동일 참조점에서 보정과 손상의 동시 보고,
P1바닥 회복·P2지붕 변화·P3구조 보존의 판정은 본 학습 후의 별도 작업으로 남는다.
최종 과학적 판정은 계속 `null`이다.
