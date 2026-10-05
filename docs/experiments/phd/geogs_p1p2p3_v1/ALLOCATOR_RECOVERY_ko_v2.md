# P1 CUDA OOM과 allocator 복구 조건

`PHD-GEOGS-P1P2P3-v1` · 작성 2026-09-08 KST · `scientific_verdict: null`

P1의 원 깊이 가중치 조건과 1/10 가중치 조건이 모두 공식 CUDA 렌더러의 forward 메모리 할당에서 실패했다. 새 native allocator 설정에서는 기존 anchor의 정확한 복원과 한 단계 실행을 확인했다. **기존 실패 구간 이후의 학습 완료는 아직 이 문서의 증거에 포함되지 않는다.** 실패는 성능 결과나 제어 변경의 우열로 해석하지 않는다.

**진행 추가 기록(2026-09-08 03:31 KST):** 새 allocator의 두 P1 실행은 실제 `runs_allocator_v2/P1/*/model/jbgs_trace.jsonl`에서 24,000회 이후까지 진행됨을 확인했다. 따라서 두 기존 실패 구간을 통과한 것은 확인됐지만, 아직 30,000회 학습·최종 렌더·mesh가 완료된 것은 아니다. 아래 최초 probe의 증명 범위와 구분한다.

이 문서의 `$TASK`는 다음 경로다.

```text
/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1
```

## 확인한 실패

두 실행 모두 `train_receipt.json`의 `status=FAIL`, native/validated exit code `1`이다. 오류 위치는 고정 소스의 `train.py:825` → `gaussian_renderer/__init__.py:111` → `_C.rasterize_gaussians`다. 어느 내부 임시 버퍼가 해당 요청을 했는지까지는 오류 기록이 식별하지 않는다.

| 항목 | P1 `D005_Pnative` | P1 `D0005_Pnative` |
|---|---:|---:|
| refinement prior 깊이 가중치 | 0.005 | 0.0005 |
| 시작 방식 | 처음부터 학습 | 같은 P1 완전 상태 8,000회에서 재개 |
| 마지막 진행 표시의 전체 iteration | 14,720 | 14,410 (=8,000+6,410) |
| 마지막 100회 간격 trace iteration | 14,700 | 14,400 |
| 마지막 trace Gaussian 수 | 4,845,783 | 4,890,928 |
| 보호 Gaussian 수 | 236,015 | 236,015 |
| OOM 요청량 | 7.09 GiB | 8.03 GiB |
| 오류 시 device free | 6.30 GiB | 5.36 GiB |
| 오류 시 PyTorch allocated | 7.31 GiB | 7.37 GiB |
| 오류 시 reserved but unallocated | 9.13 GiB | 10.40 GiB |
| 영수증 wall time | 1,419.0693 s | 830.2469 s |
| 마지막 trace의 누적 allocated peak | 15,262,582,784 B | 16,154,414,080 B |
| 마지막 trace의 누적 reserved peak | 22,856,859,648 B | 24,589,107,200 B |
| child peak RSS | 7,911,944,192 B | 8,171,872,256 B |

진행 표시는 10회마다, trace는 100회마다 기록된다. 마지막 표시를 정확한 실패 iteration으로 확정하지 않는다. 재개 실행의 progress bar는 22,000회 중 진행량이므로 6,410을 전체 iteration으로 잘못 읽지 않는다. container 안의 `GPU 0` 표기는 각각 하나씩 노출된 장치의 논리 번호이며, 두 작업이 같은 물리 GPU를 사용했다는 뜻이 아니다. 누적 peak와 오류 시점의 현재 메모리 수치는 다른 측정이다.

원본은 `$TASK/runs/P1/{D005_Pnative,D0005_Pnative}/`의 `train.log`, `train_receipt.json`, `model/jbgs_trace.jsonl`과 완전 checkpoint에 보존한다. 두 시도의 소요시간 합 2,249.3161초는 실패 작업 비용이며, 겹쳐 실행한 구간이 있어 경과시간 합이나 성공 학습 시간으로 사용하지 않는다. 이 두 시도에서 30,000회 최종 결과는 없다.

| 파일 (`$TASK` 상대 경로) | SHA256 |
|---|---|
| `runs/P1/D005_Pnative/train_receipt.json` | `d33132cccc11657a09ba9a71412fdc0eb43311df2ae2313eb718fec43ee56673` |
| `runs/P1/D005_Pnative/train.log` | `407c5b6b1b0ef80a76d9806c3007c5ca131c9b2dca25e34a0d4ad894193529a9` |
| `runs/P1/D0005_Pnative/train_receipt.json` | `b8f53237bf6aa653a8d306d28affda7b5040cf66125934b1c05baa3208b8b4bb` |
| `runs/P1/D0005_Pnative/train.log` | `eec377919a81668fae57e5061c547444e0f89f9db23458916c85ade471e346fd` |

## 고정한 복구 조건과 근거

새 실행은 아래 값을 프로세스 시작 전 설정한다. PyTorch import 후 backend를 바꾸는 방식이 아니다.

```text
PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
```

PyTorch 2.1.2 문서는 큰 미사용 분할 블록이 있는 OOM의 마지막 수단으로 `max_split_size_mb`를 설명한다. 128 MiB보다 큰 native allocator 블록의 분할을 제한하며, 속도 영향이 있을 수 있다. 같은 문서에서 `cudaMallocAsync`는 CUDA 11.4 이상을 요구하고 이 분할 설정을 무시한다. `expandable_segments`는 실험 기능이다. 이번 조건은 native/128 하나이며 대안들을 동시에 적용하지 않는다. [PyTorch v2.1.2 CUDA memory management](https://raw.githubusercontent.com/pytorch/pytorch/v2.1.2/docs/source/notes/cuda.rst)

정확한 v2.1.2 구현은 `max_split_size_mb`가 20 MiB보다 커야 한다고 검사하고, backend를 모듈 초기화 때 환경에서 선택한다. 설치된 2.1.2+cu121의 실제 CUDA probe에서 native backend와 `max_split_size=134217728`을 확인했다. [v2.1.2 allocator 구현, 850–863·3299–3322행](https://github.com/pytorch/pytorch/blob/v2.1.2/c10/cuda/CUDACachingAllocator.cpp#L850)

두 OOM 모두 요청량보다 큰 reserved-but-unallocated가 있어 단편화가 개입했을 가능성은 높다. 그러나 실패 순간의 inactive-split 상세 통계나 memory snapshot은 없으므로 **단편화를 유일한 원인으로 확정하지 않는다.** 128은 OOM과 공식 동작 설명을 근거로 정한 첫 복구값이며, 결과를 보고 탐색한 최적값이 아니다. 대규모 Gaussian과 관측별 임시 렌더 버퍼가 실제 가용 메모리를 넘으면 이 설정도 실패할 수 있다.

이미지는 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, PyTorch `2.1.2+cu121`, driver `580.82.07`을 유지한다. 공식 GeoGS 기반 commit은 `db40c95c657ec03ff21c83cb99cf39f4e90247a6`이며 지역 학습은 이미 감사한 `GeoGS-state-camera-v1` 소스를 그대로 사용한다. allocator 복구로 학습 소스·입력·해상도·iteration·Gaussian 제한·손실·보호 제어를 바꾸지 않는다. 평가 참조와 성능 결과를 설정 선택에 사용하지 않았다.

[runtime_layout_allocator_v2.json](../../../../configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json)은 새 `runs_allocator_v2`, `parity_allocator_v2`, `queue_allocator_v2` 경로와 동일 allocator를 고정한다. P1의 모든 새 조건은 아래 기존 8,000회 anchor를 공유하며 원설정 조건도 이 anchor에서 재개한다. P2/P3의 anchor 생성과 이후 비교는 새 allocator에서 시작한다. 따라서 P1은 원래 allocator에서 만든 anchor를 사용하는 이력이 있고, 새 원설정 결과를 처음부터 새 allocator로 학습한 결과라고 부르지 않는다. 옛 실패 시도와 새 allocator 조건을 섞어 주 비교표를 구성하지 않는다.

```text
P1 checkpoint SHA256: c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274
scientific config SHA256: b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4
P1 input manifest SHA256: 3257b3604f630a64948606605c3ae46f2e22d4d5829b5ad49a7d46b342a42112
```

## 실제 allocator probe의 증명 범위

실행 driver는 [run_allocator_probe.sh](../../../../scripts/phd/geogs_p1p2p3_v1/runtime/run_allocator_probe.sh), 감사 wrapper는 [probe_allocator_restore.py](../../../../scripts/phd/geogs_p1p2p3_v1/runtime/probe_allocator_restore.py)다. 실제 명령은 `bash scripts/phd/geogs_p1p2p3_v1/runtime/run_allocator_probe.sh 0`이었다. 입력·학습 소스·원 invocation·anchor·metric weights를 read-only로 mount하고 평가 참조는 mount하지 않았다. 출력은 `$TASK/runtime/allocator_recovery_v2/P1_native128/`; 동일 경로 재실행은 기존 증거 보호를 위해 거부한다.

| 검사 | 실제 결과 |
|---|---|
| runtime allocator 설정 | native, 128 MiB 적용 확인 |
| 첫 난수 추출/optimizer step 전 복원 | 모델·Adam·보호 상태·controller·전체 RNG·카메라 순서·설정·소스 일치, 차이 0 |
| 실제 보호 hook | 단위 gradient의 xyz/rotation/scale 0.01 감쇠 일치 |
| 같은 anchor PLY | render 관련 parameter와 실제 RGB/depth/alpha/normal 배열 일치 |
| 감사 자체 RNG 소비 | 없음 |
| 실제 native iteration 8,001 | 카메라·남은 stack·Python RNG·Adam +1 일치, 유한 모델/손실, Gaussian·보호 수 유지 |
| 기존 allocator의 한 단계 영수증과 비교 | 모든 기록 필드 일치; loss `9.535420417785645` |
| probe 소요시간 | 12.2475 s |
| probe allocated / reserved / inactive-split peak | 3,687,002,112 / 8,466,202,624 / 530,499,072 B |

`allocator_probe_receipt.json` SHA256은 `4efbbf01c4448573e890c219ae6d07ee334921e94cacf016c4b56c42006f65bc`다. 설정·checkpoint·probe script hash와 전체 allocator 통계는 이 영수증 및 `probe_config.json`, `restore_probe.json`, `one_step_probe.json`에서 확인한다.

한 단계 검사는 업데이트 후 모든 모델 tensor byte를 이전 실행과 비교한 것이 아니다. 초기 상태·동일 anchor 렌더의 정확성, 실제 한 단계의 기록된 동작을 확인했다. probe의 메모리 peak에는 복원·추가 PLY 로딩·비교용 렌더가 포함되므로 일반 학습 peak로 사용하지 않는다. 더 큰 모델에서 일어난 기존 OOM의 해결, 30,000회 완료, 기하·영상 품질 또는 우열은 이 probe가 증명하지 않는다.

## 초기 복원과 이후 CUDA 난수 상태의 구분

공식 `scene/gaussian_model.py:396–410`의 split은 gradient·scale·보호 mask로 점을 선택하고, 선택 수의 6배 요소를 가진 `torch.normal` tensor를 생성한다. `train.py:1076–1078`은 15,000회 전 100회마다 densification을 수행한다. PyTorch 2.1.2는 난수 tensor 크기와 실행 grid로 Philox counter 증가량을 결정한다. 따라서 초기 상태를 정확히 복원해도 이후 수치 차이가 split 선택 수를 바꾸면 CUDA RNG 진행량이 달라질 수 있다. [v2.1.2 CUDA DistributionTemplates.h, 48–61·121–134행](https://github.com/pytorch/pytorch/blob/v2.1.2/aten/src/ATen/native/cuda/DistributionTemplates.h#L48)

[seal_anchor_gate.py](../../../../scripts/phd/geogs_p1p2p3_v1/seal_anchor_gate.py)의 v2 정책은 초기 복원/한 단계 PASS와 동일 checkpoint를 계속 요구한다. 100회 후 Python·NumPy·CPU RNG, iteration, 카메라 순서/stack, optimization, source는 정확히 같아야 한다. 이후 CUDA RNG tensor의 **값** 차이는 `UNRESOLVED_BRANCH_DYNAMICS`로 보존하며 원인을 확정하지 않는다. CUDA RNG key·device-list 길이·tensor shape/dtype 손상은 계속 실패다. gate는 자체 script와 선택적 runtime layout의 hash도 기록한다.

기존 P1의 100회 재개 비교는 CUDA RNG를 포함한 RNG와 카메라 순서가 이미 모두 같았으며, 최종 Gaussian 수 1,125,500 대 1,125,535와 총 120개 모델/상태 항목이 달랐다. 따라서 이번 정책 변경은 그 비교를 불일치에서 일치로 승격한 것이 아니다. 새 allocator와 옛 8,100회 checkpoint 간 비교도 실행 환경 차이가 포함된 후속 수치 진단으로 기록한다. split 때의 실제 난수 tensor 크기를 대조하지 않은 CUDA RNG 차이를 단순히 정상적인 현상이라고 판정하지 않는다.

문서 작성 중 정식 새 P1 gate도 `$TASK/parity_allocator_v2/P1/anchor_gate.json`에서 `EXACT_COMMON_ANCHOR_VERIFIED`를 확인했다. 새 allocator의 100회 재개와 옛 연속 8,100회 상태는 121항목이 달라 `continuation_exact=false`이고, CUDA RNG는 실제 일치한다. runtime layout SHA256은 `28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5`, gate script SHA256은 `a2c10d5200bfb8b5e1f38965eef456df812bdfae67596b8aff83a10cfb8644d2`로 영수증과 현재 파일이 일치한다. 이 gate 또한 이후 OOM 해결을 증명하지 않는다.

`test_anchor_gate.py`의 8개 Docker 테스트가 값 차이의 진단 처리와 구조·초기 상태·한 단계·CPU 난수·카메라·설정 변경의 차단을 검증했다. 실제 재시도의 완료 여부와 이후 정량·정성 분석은 별도 실행 영수증과 결과표로 갱신해야 한다. `scientific_verdict: null`을 유지한다.
