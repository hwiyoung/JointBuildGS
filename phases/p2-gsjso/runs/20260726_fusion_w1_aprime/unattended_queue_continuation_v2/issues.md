# A′ 잔여 20-job continuation issues

## FUS-W1-APRIME-CONT-V2-T2-AUDIT-001 — 감사 중 T2 실실행

- observed_at: `2026-07-27T11:57:33+09:00`
- classification: `provenance mutation; scientific artifact hashes unchanged`
- observation: T2 감사에서 hash-only 확인이 아닌 rehearsal 실행 경로가 의도치 않게 호출되어 canonical T2 receipt와 로그가 재발행되었다.
- original_queue_pinned_receipt_sha256: `6ef49bba0e9cc93251717cf104ab9ec4543402542998857194da08da7bbeda0b`
- original_queue_pinned_receipt_archive: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2/receipt_history/t2_tsdf_rehearsal_receipt.20260727T022531444719Z.6ef49bba0e9c.json`
- intermediate_archived_receipt_sha256: `b247794b5a68077f47af6ed89de2dd5c12409b1deee5c42753e8fe5052a190fc`
- current_receipt_path: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2/t2_tsdf_rehearsal_receipt.json`
- current_receipt_sha256: `393370ef054ae4a5d12b1b95e7ce96f57796cb42bf6cc9ed5963423334f039a7`
- current_receipt_bytes: `20518`
- current_receipt_execution_head: `b2811bbb60df0f33d211f98060fe87f31b728e24`
- measured_artifact_effect: current receipt의 8개 geometry/sample artifact SHA는 원 queue plan의 8개 ledger SHA와 일치한다.
- control: 원 queue의 T2 pin을 현재 canonical path로 재해석하지 않는다. 원 receipt archive SHA와 현재 receipt SHA를 동시에 기록한다.
- prevention: continuation 구현 커밋 뒤 exact-HEAD training gate를 만족시키기 위한 정식 T2 재발행을 정확히 1회 수행하고, 그 뒤 queue 완료까지 HEAD를 고정한다. 그 외 후속 감사는 해시·스키마·status 읽기로만 수행한다.
- scientific_verdict: `null`

## FUS-W1-APRIME-CONT-V2-CACHE-001 — 비-root cache 강제

- source_failure: 원 smoke readout attempts 001–003에서 `PermissionError: [Errno 13] Permission denied: '/.cache'`가 동일 signature로 3회 발생했다.
- source_failure_signature: `00fa59bf782c96a81dabb741788c22b6b7a650099188c3192adbf4a15e533012`
- recovery_observation: UID 1000 cache probe와 smoke attempt 005에서 권한 오류는 `0`건이었다.
- required_binding:
  - `HOME=/workspace/JointBuildGS/phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env/home`
  - `XDG_CACHE_HOME=/workspace/JointBuildGS/phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env/xdg_cache`
  - `TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env/torch_extensions`
- control: host UID/GID `1000:1000`, 비-symlink, 쓰기 가능, gsplat extension 로드를 각 job 시작 전 영수증으로 남기고 `/.cache` fallback을 허용하지 않는다.
- disposition: `RESOLVED_IN_CONTINUATION_IMPLEMENTATION`; GPU 1 강제·비-root cache probe·기존 gsplat extension SHA/load/tree 불변 검사를 training 직전과 readout 시작 전에 실행한다.

## FUS-W1-APRIME-CONT-V2-GPU-CONTENTION-001 — 외부 all-GPU worker 충돌 가능성

- audit_observation: 즉시 실행 시점에 JointBuildGS training/TSDF/Roofer CUDA process와 실제 queue lock holder는 `0`이었다.
- selected_device: `physical GPU 1`
- observed_free_vram: `24034 MiB`
- external_workers: aerial-survey-manager 1개와 NBM engine 2개의 Celery worker가 `all GPUs`를 볼 수 있는 상태로 대기 중이었다.
- system_memory: `49 GiB available`; swap `2 GiB / 2 GiB used`.
- control: continuation은 GPU 1에서 한 job씩만 실행하고 job 경계마다 compute PID/VRAM을 기록한다. 외부 compute가 관찰되면 새 job 시작을 보류하고 사용자 질의·시간 cutoff 없이 재검사한다.
- disposition: `CONTROL_IMPLEMENTED_CONDITIONAL_SERIAL_EXECUTION`; job 경계와 각 CUDA action 직전에 GPU 1 compute process를 검사하고, 외부 compute가 있으면 30초 간격으로 무기한 대기한다.

## FUS-W1-APRIME-CONT-V2-SOURCE-IMMUTABILITY-001 — terminal queue는 resume 대상이 아님

- original_queue_state: `STOPPED_SMOKE_BARRIER_NOT_MEASURED`
- original_queue_complete_sha256: `7a37c2ea41edd194169415335f1412408748c24b9f0741d09372b04383f0b1e3`
- recovered_smoke_state: `COMPLETE`
- recovered_smoke_complete_sha256: `9a2bfa641761e2081e49ef7b66f78ee468eb18f5c100951d8f957de4f3eed8c6`
- control: 원 queue의 terminal receipt/status/events와 smoke recovery attempts 004–005는 읽기 전용으로 고정한다. 잔여 20 jobs의 controller·training·readout·report는 `unattended_queue_continuation_v2/`에서만 발행한다.
- disposition: `NEW_NAMESPACE_ONLY`

## FUS-W1-APRIME-CONT-V2-PRESTART-AUDIT-001 — 무인 queue 재개 결함 사전 차단

- observed_at: `2026-07-27T12:57:00+09:00`
- scope: 잔여 20 jobs 시작 전 controller·cachefix·정성 관문 읽기/회귀 감사.
- observations:
  - 원 controller는 `ARCHIVE_TRAINING` 자체의 동일 action 오류가 3회 누적돼도 skip 검사보다 archive를 먼저 반환할 수 있었다.
  - 원 queue verifier는 readout completion의 `artifact_ledger` 전체 SHA/bytes와 실제 attempt 파일 집합의 exact coverage를 재검증하지 않았다.
  - readout wrapper의 활성 attempt는 `ERR` 외 `TERM`/`INT` 중단에서 failure receipt 없이 남을 수 있었다.
  - training 직전에는 공유 gsplat cache의 exact extension load/reuse-only 확인이 없었다.
- controls:
  - 동일 `ARCHIVE_TRAINING` action signature 3회는 해당 job의 `RECORD_SKIPPED`로 먼저 전환한다.
  - 완료 readout은 ledger 전 항목 SHA/bytes, 중복, attempt 내부 exact file coverage, symlink/special file 부재, 성공 attempt의 failure 부재를 재검증한다.
  - 활성 readout attempt는 `ERR`/`TERM`/`INT`에서 one-shot failure receipt를 발행하고 기존 failure 또는 authoritative complete와의 중복·모순 기록을 억제한다.
  - 각 training launch 직전 cache probe로 non-root HOME/XDG/TORCH, pinned gsplat extension SHA/load, cache tree 불변을 확인한다. 이후 readout probe가 같은 singleton receipt/tree를 다시 대조한다.
- regression: Docker 단위시험 `61/61` 통과(정성 9 + cachefix 17 + continuation 35); 새 학습·TSDF·Roofer 실행 `0`.
- disposition: `RESOLVED_BEFORE_FIRST_REMAINING_JOB`
- scientific_verdict: `null`

## FUS-W1-APRIME-CONT-V2-GPU-MAPPING-001 — physical GPU 1 표기 명확화

- locked_device: `physical GPU 1`.
- training_mapping: host `NVIDIA_VISIBLE_DEVICES=1` 뒤 container `CUDA_VISIBLE_DEVICES=0`으로 physical GPU 1을 logical GPU 0에 remap한다.
- readout_mapping: host all-visible 컨테이너에서 `CUDA_VISIBLE_DEVICES=1`로 physical GPU 1을 선택한다.
- observation: 두 경로 모두 같은 physical GPU 1을 사용한다. training에 readout의 container index 표기를 기계 적용하지 않는다.
- scientific_verdict: `null`
