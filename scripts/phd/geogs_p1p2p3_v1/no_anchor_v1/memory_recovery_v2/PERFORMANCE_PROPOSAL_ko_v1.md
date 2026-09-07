# Pinned Adam 상태 버퍼 성능 검토 — 실행 중인 v1 변경 없음

`scientific_verdict: null`

이 디렉터리는 성능 측정, CPU 검증, 승인된 새로운 v2 source 복사 generator와 작은 CUDA runtime 검증을 제공한다. 현재 학습 소스·설정·실행 프로세스는 변경하지 않았다. 부모 작업이 수행한 같은 여섯 Adam 그룹의 실제 상태 전송 측정에서 개선을 확인하여, 추가 위임에 따라 새 runtime 준비 기능을 작성했다. 현재 실행 중단·재시작은 부모 작업이 모든 준비 및 CUDA 검증을 확인한 뒤 별도로 처리한다.

## 실제 구현 차이

원 v1 `memory_recovery_v1/memory_adapter.py` SHA256은 `de4ba2a8c6a50efd670b195479b07962052c9cec10efd35d594c3ba9dc69c114`이다. `MomentStorage.offload()`는 각 `exp_avg`/`exp_avg_sq`를 매번 `.to(device="cpu", non_blocking=False)`로 복사한다. 복원 시에는 매번 `.to(parameter.device, non_blocking=False)`를 사용한다.

`pinned_storage.py`는 이 정확한 v1을 hash로 확인하고 상속한다. D2H 목적지만 재사용하는 pinned CPU buffer로 바꾸며, 원 restore 구현·상태/step/parameter 검증은 그대로 사용한다. GPU 파라미터, gradient, step counter, Adam 연산과 모멘트 dtype/shape는 바꾸지 않는다. 버퍼의 여유 capacity는 학습 텐서 shape에 노출하지 않는다. 실제 optimizer.state에는 정확한 shape의 view만 들어간다. `non_blocking=False`를 유지하므로 계산과 전송을 겹쳐 실행하는 새 정책은 없다.

여섯 native 그룹 `xyz`, `f_dc`, `f_rest`, `opacity`, `scaling`, `rotation` 각각에 두 모멘트 슬롯을 둔다. 각 슬롯의 flat CPU capacity는 2의 거듭제곱이다. 성장 시 더 큰 capacity를 만들고, prune 후에는 이전 최대 capacity를 재사용한다. persistent cache는 Parameter/gradient/state dictionary를 키나 값으로 저장하지 않는다. v1의 임시 검증 records는 복원 후 해제되어 optimizer.step 및 파라미터 교체를 넘지 않는다. GPU 복원 후 남는 CPU 데이터는 슬롯당 pinned allocation 하나이며, 별도 pageable 사본을 보존하지 않는다.

## 호스트 메모리와 수명

동일 Docker 이미지 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`의 PyTorch는 `2.1.2+cu121`이다. 다음 설치 소스를 직접 확인했다.

- `/opt/geogs/lib/python3.10/site-packages/torch/include/ATen/cuda/CachingHostAllocator.h:8`: 해제된 pinned 메모리를 allocator가 재사용하며, `cudaFreeHost`의 동기화를 피한다.
- 같은 파일 `:19`: 큰 pinned allocation을 작은 블록으로 분할하지 않는다.
- 같은 파일 `:33`: cached pinned memory 해제는 별도 C++ `CachingHostAllocator_emptyCache()` 기능이다.
- `/opt/geogs/lib/python3.10/site-packages/torch/_tensor_docs.py:1217`: `copy_`와 `non_blocking`의 동작 정의.

따라서 Python에서 이전 버퍼 참조가 해제됐다는 검증은 실제 pinned RAM이 OS로 반환됐다는 검증이 아니다. 이 prototype은 host cache purge를 사용하지 않는다. 대신 각 슬롯의 capacity가 증가할 때 최소 두 배가 되므로, 그 슬롯의 누적 allocation 요청 합은 최대 capacity의 두 배 미만이다. allocator의 metadata/rounding, 다른 코드에서 할당한 pinned memory와 전체 RSS는 이 산술 상한에 포함되지 않는다.

다음 수치는 58개 float32 파라미터와 두 모멘트의 정확한 크기 산술이다. transfer는 양방향 합계이며 CPU snapshot reserve는 파라미터+두 모멘트 세 벌의 원소 수에 해당한다.

| Gaussian 수 | 실제 두 모멘트 GiB | 매 iteration 왕복 GB | 현재 pinned capacity GiB | 전체 요청 이력 상한 GiB, 미만 | snapshot reserve GiB |
|---:|---:|---:|---:|---:|---:|
| 100,000 | 0.0432 | 0.0928 | 0.0771 | 0.1543 | 0.0648 |
| 1,000,000 | 0.4321 | 0.928 | 0.6172 | 1.2344 | 0.6482 |
| 10,000,000 | 4.3213 | 9.28 | 5.375 | 10.75 | 6.4820 |
| 12,000,000 | 5.1856 | 11.136 | 9.875 | 19.75 | 7.7784 |
| 15,000,000 | 6.4820 | 13.92 | 9.875 | 19.75 | 9.7230 |

성장 시 cgroup v2 `memory.current`와 유한한 `memory.max`를 읽는다. `현재 cgroup RAM + 이번에 필요한 새 capacity 합 + snapshot reserve + 1 GiB`가 `min(기존 container limit, 32 GiB)`를 넘으면 **복사와 lifecycle 상태 변경 전에** `PINNED_HOST_BUDGET_EXCEEDED`로 실패한다. 한도나 Gaussian 수, densification 등 과학 설정을 바꾸지 않는다. 이전 allocator cache가 이미 반환되지 않았다면 그 사용량도 현재 cgroup RAM에 포함된다. allocator가 기존 블록을 재사용할 수 있어도 새 요청 전체를 더하는 보수적 검사다.

이 guard는 모든 미래 native peak를 보장하지 않는다. snapshot serializer 임시 메모리, checkpoint I/O의 page cache, native densification의 GPU/CPU peak는 실제 실행에서 별도 실패할 수 있다. 특히 10M→12M 사이 capacity 증가와 기존 호스트 작업을 고려하면 32 GiB 실행 한도가 후속 병목이 될 수 있다. 다른 서비스를 종료하거나 호스트/컨테이너 한도를 높이지 않는다.

## 측정 범위와 판단

`transfer_probe.py`는 stdlib와 동일 이미지 libcudart만 사용한다. GPU 두 32 MiB buffer와 CPU pageable/pinned 각 32 MiB를 사용하여 2/8/32 MiB 전송을 교대로 측정한다. 자체 stream 복사 완료만 기다리며 optimizer·backward·geometry·render를 실행하지 않는다. 최대 scheduling window는 8초이고 실제 window가 10초를 넘으면 성공으로 기록하지 않는다. CUDA 내부에서 정지한 blocking call은 Python 시간 검사로 선점할 수 없음을 receipt에 적는다. GPU context 메모리는 자체 64 MiB 데이터와 별도다.

부모 작업이 실행한 `no_anchor_sfm_memory_recovery_v1/validation/transfer_probe_v1/transfer_probe.json`은 `PASS_BOUNDED_TRANSFER_MEASUREMENT`였다. GPU0 32 MiB에서 pageable 대비 pinned의 paired 중앙값은 H2D 약 2.99배, D2H 약 2.29배였다. 이 측정은 staging 경로의 개선 가능성만 확인한다. 작은 고정 buffer 측정치에 10M 전송량을 단순 대입하여 전체 학습 속도나 완료 시간을 약속할 수 없다.

`adapter_probe.py`는 동일한 100k synthetic points, 여섯 native Adam 그룹, 하나의 optimizer state로 v1/v2를 번갈아 측정한다. Adam.step과 backward는 호출하지 않는다. 각 모드 두 warmup 다음 네 paired cycle이 기본이며, first-roundtrip hash 검사는 warmup에 포함된다. 최종 파라미터/모멘트/step 바이트, 파라미터 pointer, step object와 gradient 없음이 보존되는지 검사한다. PyTorch device allocator cap은 128 MiB, 실제 파라미터+두 모멘트는 약 66.4 MiB다. Torch import의 host RSS 및 CUDA context는 별도 비용이며, 최소 2 GiB 유한 container RAM이 필요하다.

```bash
/opt/geogs/bin/python /work/adapter_probe.py \
  --device 0 --points 100000 --repeats 4 --max-gpu-seconds 8 \
  --v1-adapter /v1/memory_adapter.py --receipt /out/adapter_probe.json
```

부모 작업이 실제 GPU0에서 실행한 `no_anchor_sfm_memory_recovery_v1/validation/adapter_probe_v1/adapter_probe.json`은 `PASS_BOUNDED_ADAPTER_MEASUREMENT`였다. 네 paired cycle의 중앙값 비율은 전체 offload+restore **2.2205배**였다. 전체 시간 중앙값은 v1 37.63 ms, v2 17.43 ms이며, D2H paired 비율은 1.9477, restore는 2.1318이었다. 최종 parameter/moment/step 바이트와 pointer/counter object가 보존됐다. peak CUDA allocated는 71,922,688 bytes, reserved는 83,886,080 bytes였다. Torch import를 포함한 host peak RSS는 약 606 MiB로, CUDART-only probe의 256 MiB RSS 범위와 다르다.

이 하위 작업은 GPU 코드를 직접 실행하지 않았다. 실제 probe는 부모 작업이 자원을 확인하고 수행했다. native 전체 step 중 상태 전송의 비율은 이 작은 fixture만으로 알 수 없으므로, 새 실행을 택할 때에는 별도 실행 계보와 실제 step 시간 확인이 필요하다. v1 대비 trajectory bitwise 일치 또는 최종 30k 완주는 주장하지 않는다.

## CPU 검증 근거

`verify_pinned_storage.py`를 동일 Docker 이미지, network none, GPU 노출 없이 실행했다. `pin_memory=False`의 CPU 대체 버퍼로 다음 9개 검사를 통과했다.

1. 첫 iteration의 비어 있는 Adam 상태 보존.
2. 여덟 CPU Adam step의 파라미터·모멘트·counter 값 완전 일치.
3. 성장과 prune을 모사한 현재 파라미터 교체.
4. 이전 파라미터와 gradient 참조 해제.
5. 이름으로 고정된 12개 cache 슬롯.
6. restore 전후 같은 CPU allocation 하나 유지.
7. 전체 요청 이력의 최대 capacity 두 배 미만 상한.
8. 1,024개 점진적 크기 요청과 prune 이후 재사용.
9. host memory 부족 시 상태 변경 전 실패 및 충분한 여유 시 통과.

검증 receipt는 외부 artifact의 `no_anchor_sfm_memory_recovery_v1/validation/pinned_storage_cpu_v2/receipt_v2.json`, 실행·image·source hash는 `execution_v2.json`, 정확한 코드 사본은 `source_v2/`에 있다. 최초 8개 검사 receipt도 `receipt.json`으로 보존했다. 실제 CUDA pinned allocation과 큰 크기 성능은 CPU 검증에 포함되지 않는다.

## 새 source 준비와 runtime 검증

`prepare_runtime.py`는 원 `no_anchor_sfm_v1/source` 전체 Python hash 및 원 no-anchor receipt를 검증한다. v1 preparer와 v1 adapter도 각각 frozen SHA로 확인한다. 새 목적지에 복사한 뒤 다음 네 Python 파일만 변경·추가한다.

- `train.py`: v1 recovery와 완전히 같은 SHA `1680d6e357877a03811c912804d211fe7c4b77562ecf24999d573fb4897450cb`.
- `jbgs_memory_recovery_v1_base.py`: v1 adapter의 byte-identical 사본.
- `jbgs_pinned_storage.py`: 실제 adapter probe에서 검증한 pinned cache 구현.
- `jbgs_memory_recovery.py`: v1 lifecycle을 상속하고 cache policy/trace/final receipt를 추가하는 wrapper.

`jbgs_no_anchor_runtime_receipt.json`의 원 바이트를 보존한다. `jbgs_memory_recovery_receipt.json`은 기존 schema와 `PASS_MEMORY_RECOVERY_RUNTIME_PREPARED` 상태, `parent_runtime_receipt_sha256`, `original_source_python_sha256`, `destination_python_sha256`, `science_config_unchanged` 필드를 유지하고 `storage_version: 2`와 추가 모듈 hash를 기록한다. initializer, stage2/보호 적용, full/first-step capture, optimizer.step/densification 순서는 같은 train.py로 고정된다. 완전 checkpoint resume 지원은 추가하지 않는다.

```bash
/opt/geogs/bin/python /work/memory_recovery_v2/prepare_runtime.py \
  --source /original --destination /out/source \
  --v1-directory /work/memory_recovery_v1

/opt/geogs/bin/python /work/memory_recovery_v2/verify_runtime.py \
  --prepared-source /source --v1-directory /work/memory_recovery_v1 \
  --device cuda --receipt /out/receipt.json
```

`verify_runtime.py --source /original --device cpu`의 실제 원본 복사 검사 및 synthetic 8-step wrapper 검증이 `PASS_CPU_RUNTIME_FIXTURE`로 통과했다. receipt는 `no_anchor_sfm_memory_recovery_v1/validation/runtime_cpu_v2/receipt.json`이다. 이 검증은 source hash/원 receipt 보존, 동일 train 위치, 여덟 Adam step의 parameter/moment/counter 완전 일치, 성장·prune 후 GPU 경계 대응, 이전 parameter/gradient 참조 해제, 첫 왕복 byte hash, wrapper policy/trace/final receipt를 포함한다. CPU 모드는 storage만 명시적으로 CPU 대체하며 실제 CUDA/pinning 검증은 포함하지 않는다.

CUDA 모드는 원 wrapper 그대로 사용하고 64 MiB device allocator cap 아래 동일 작은 여덟 step을 실행한다. actual CUDA pinned allocation, selected-depth byte roundtrip, growth/prune와 lifecycle receipt를 검증한다. 실제 GeoGS scene·renderer·학습 입력은 로드하지 않는다. 관측 fixture window가 10초를 넘으면 PASS하지 않는다. 준비 완료 시점에서 CUDA runtime fixture 실행은 부모 작업에 넘겼다.
