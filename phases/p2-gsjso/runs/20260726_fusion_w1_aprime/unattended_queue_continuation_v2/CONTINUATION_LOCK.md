# A′ 잔여 20-job 무인 연속 실행 잠금

- task: `FUS-W1-APRIME-QUEUE-CONTINUATION-V2-LOCK-001`
- created_at: `2026-07-27T12:05:28+09:00`
- branch: `exp/fusion-w1`
- authoring_base_head: `b2811bbb60df0f33d211f98060fe87f31b728e24`
- runtime_namespace: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue_continuation_v2/`
- state: `LOCKED_BEFORE_REMAINING_JOB_START`
- scientific_verdict: `null`

## 1. 사용자 승인과 범위

- 2026-07-27 사용자 지시 `그럼 42364609 나머지 진행하자.`를, 이미 성공·고정된 `DEBY_LOD2_42364609 / Aprime / r1`을 제외한 원 queue의 잔여 20 jobs 연속 실행 승인으로 기록한다.
- 실행 범위는 `A′ r1 나머지 8동 + A′ r2 9동 + arm B r1 3동 = 20 jobs`로 고정한다.
- 이미 완료된 `42364609 / Aprime / r1`의 학습·TSDF·Roofer·채점은 재실행하지 않는다.
- 사용자 질의는 `0`회로 고정한다. 시간 cutoff은 없으며(`null`), 종료 조건은 완주 또는 아래 파국 규칙에 의한 단계 중단뿐이다.

## 2. 원 queue·smoke recovery 기준 해시

아래 파일은 읽기 전용 기준이며 이 continuation이 수정·추가·삭제하지 않는다.

| 역할 | 경로 | SHA-256 |
|---|---|---|
| 원 21-job queue plan | `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue/queue_plan.json` | `18e6226cf4d4bcc3f2da6ba8d97964e4b8909c9b96e655884620cef271ee6837` |
| 원 queue stage stop | `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue/stage_stop.json` | `759569f0d5c3b33602e8f67fe3869a9007d936da6a438343cacd58412f7a0774` |
| 원 queue terminal receipt | `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue/complete.json` | `7a37c2ea41edd194169415335f1412408748c24b9f0741d09372b04383f0b1e3` |
| smoke recovery lock v3 | `phases/p2-gsjso/runs/20260727_fusion_w1_aprime_smoke_recovery/recovery_lock_v3.json` | `cdb9361238183653d2ee8836b642c705e9d3c4a82bd966affa01632f8cfa5fa5` |
| smoke recovery completion | `phases/p2-gsjso/runs/20260727_fusion_w1_aprime_smoke_recovery/completed.json` | `9a2bfa641761e2081e49ef7b66f78ee468eb18f5c100951d8f957de4f3eed8c6` |
| smoke recovery measurement report | `phases/p2-gsjso/runs/20260727_fusion_w1_aprime_smoke_recovery/recovery_report.json` | `61d15bd206da9619a1fc9d1c873dcb87c0771f3ba162068faf808a3820575fc5` |
| recovered smoke final checkpoint | `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/training/by_building/DEBY_LOD2_42364609/arm_Aprime/r1/ckpt/final.pt` | `20e1e625b90487201e3574b102dbcc10d559b17ee1de59073b893fc71a0019b9` |

- 원 queue의 종단 상태 `STOPPED_SMOKE_BARRIER_NOT_MEASURED`는 역사 기록으로 그대로 유지한다.
- smoke recovery의 성공 attempt는 `attempt_005`이며, 새 학습 `0`, 다른 queue job 시작 `0`인 상태를 continuation 출발점으로 삼는다.

## 3. 잔여 20-job 고정 순서

원 `queue_plan.json`의 stage/order를 그대로 따르며 수동 ID 추가·재정렬을 금지한다.

| continuation order | building_id | arm | run | seed | role |
|---:|---|---|---|---:|---|
| 1 | `DEBY_LOD2_42364659` | `Aprime` | `r1` | 1001 | dim_failure |
| 2 | `DEBY_LOD2_42364663` | `Aprime` | `r1` | 1001 | dim_failure |
| 3 | `DEBY_LOD2_4907182` | `Aprime` | `r1` | 1001 | dim_failure |
| 4 | `DEBY_LOD2_4907510` | `Aprime` | `r1` | 1001 | dim_failure |
| 5 | `DEBY_LOD2_4908050` | `Aprime` | `r1` | 1001 | dim_failure |
| 6 | `DEBY_LOD2_4908166` | `Aprime` | `r1` | 1001 | dim_failure |
| 7 | `DEBY_LOD2_4908176` | `Aprime` | `r1` | 1001 | dim_failure |
| 8 | `DEBY_LOD2_4908023` | `Aprime` | `r1` | 1001 | textured_control |
| 9 | `DEBY_LOD2_42364609` | `Aprime` | `r2` | 1002 | dim_failure |
| 10 | `DEBY_LOD2_42364659` | `Aprime` | `r2` | 1002 | dim_failure |
| 11 | `DEBY_LOD2_42364663` | `Aprime` | `r2` | 1002 | dim_failure |
| 12 | `DEBY_LOD2_4907182` | `Aprime` | `r2` | 1002 | dim_failure |
| 13 | `DEBY_LOD2_4907510` | `Aprime` | `r2` | 1002 | dim_failure |
| 14 | `DEBY_LOD2_4908050` | `Aprime` | `r2` | 1002 | dim_failure |
| 15 | `DEBY_LOD2_4908166` | `Aprime` | `r2` | 1002 | dim_failure |
| 16 | `DEBY_LOD2_4908176` | `Aprime` | `r2` | 1002 | dim_failure |
| 17 | `DEBY_LOD2_4908023` | `Aprime` | `r2` | 1002 | textured_control |
| 18 | `DEBY_LOD2_42364609` | `B` | `r1` | 1001 | dim_failure |
| 19 | `DEBY_LOD2_42364659` | `B` | `r1` | 1001 | dim_failure |
| 20 | `DEBY_LOD2_4908023` | `B` | `r1` | 1001 | textured_control |

각 job은 `학습 → TSDF/MC → primary Roofer/CityJSON/채점 → legacy alpha 비교 → job complete`를 완료·즉시 저장한 뒤에만 다음 job으로 넘어간다. 학습과 readout, job과 job 사이의 병렬 실행은 금지한다.

## 4. 원본 불변·새 namespace

- `unattended_queue/` 전체, 원 readout attempts 001–003, smoke recovery attempts 004–005, 원 recovery 완료/보고 영수증은 불변이다.
- 새 controller, status, events, action failures, lock quarantine, reports는 전부 `unattended_queue_continuation_v2/` 하위에 발행한다.
- 잔여 20개 고유 job의 training/readout은 원래 잠긴 producer config의 canonical root인 `training/by_building/...`와 `readout/by_building/...`에 최초 발행한다. lock 시점에 존재하지 않는 정확한 20개 identity 경로만 생성하며, 완료된 smoke identity와 원 queue subtree는 건드리지 않는다.
- 기존 preprocess, pose, ALS, 영상, 참조 GML, prereg, targets, T1/T3, 완료 smoke 영수증은 읽기 전용으로만 소비한다.
- 기존 terminal queue를 resume하거나 `complete.json`, `stage_stop.json`, `status.*`, `events.jsonl`을 재작성하지 않는다.
- 각 job 산출물은 append-only며 부분 실패도 보존한다. 성공 receipt가 발행된 job을 재실행하지 않는다.

## 5. GPU·직렬·cachefix 계약

- 물리 GPU는 `GPU 1` 하나로 고정한다. 모든 CUDA 컨테이너에 `CUDA_VISIBLE_DEVICES=1`을 명시한다.
- 한 번에 training 1개 또는 readout 1개만 실행한다. 외부 GPU compute 사용이 관찰되면 새 job을 겹쳐 시작하지 않고 질의 없이 대기·재검사한다.
- 컨테이너는 host `uid=1000`, `gid=1000`, `--network=none`, `--memory=24g`, `--memory-swap=24g`, `--cpus=12`로 실행한다.
- 기존 T2에서 검증한 다음 비-root 캐시를 모든 training/TSDF/legacy-alpha GPU 단계에 명시적으로 바인딩한다.
  - `HOME=/workspace/JointBuildGS/phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env/home`
  - `XDG_CACHE_HOME=/workspace/JointBuildGS/phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env/xdg_cache`
  - `TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env/torch_extensions`
  - compile-only `MAX_JOBS=2`; legacy alpha가 잠금된 원 readout 환경에서 `MAX_JOBS=1`을 반환하면 그 값을 따른다.
- `/.cache` fallback은 금지하고 job 시작 전 UID·소유권·비-symlink·쓰기 가능·gsplat extension 로드를 정량 영수증으로 남긴다.
- 외부 GPU worker가 없다는 독점 가정을 하지 않는다. 실제 시작 전·job 경계마다 GPU PID/VRAM을 기록한다.

## 6. 무인 완주·파국 규칙

- 사용자 prompt: `false`; time cutoff: `null`; 시간 기반 종료: `false`.
- 같은 job에서 같은 error signature가 3회 발생하면 해당 job을 `SKIPPED_SAME_ERROR_THREE_ATTEMPTS`로 고정하고 부분 산출물·스택·해시를 보존한 뒤 다음 job으로 계속한다.
- 같은 error type이 3동 연속으로 발생하면 해당 stage를 `STOPPED_SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS`로 종료하고 그 시점까지의 산출물·상태·issues를 발행한다. 후속 stage는 시작하지 않는다.
- 실패 archive를 쓴 뒤에만 새 attempt를 만들며, 삭제·덮어쓰기·attempt 재사용을 금지한다.
- censored, skipped, not assembled, not measured를 실측값으로 바꾸지 않는다. 과학 판정은 김휘영 검수에 남기고 controller/report에는 수치·관찰만 기록한다.

## 7. T2 감사 중 의도치 않은 재실행 고정

- 원 queue plan이 잠그 당시 바인딩한 T2 receipt SHA는 `6ef49bba0e9cc93251717cf104ab9ec4543402542998857194da08da7bbeda0b`이다.
- T2 감사 과정에서 hash-only 검사가 아닌 실제 rehearsal 경로가 의도치 않게 재실행되어 canonical receipt가 다시 발행되었다.
- 현재 canonical receipt:
  - path: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2/t2_tsdf_rehearsal_receipt.json`
  - bytes: `20518`
  - SHA-256: `393370ef054ae4a5d12b1b95e7ce96f57796cb42bf6cc9ed5963423334f039a7`
  - created_at_utc: `2026-07-27T02:57:33.328189+00:00`
  - execution head: `b2811bbb60df0f33d211f98060fe87f31b728e24`
- 원 queue-pinned receipt는 `receipt_history/t2_tsdf_rehearsal_receipt.20260727T022531444719Z.6ef49bba0e9c.json`에 SHA `6ef49bba...beda0b`로 보존되어 있다. 중간 receipt SHA `b247794b5a68077f47af6ed89de2dd5c12409b1deee5c42753e8fe5052a190fc`도 `receipt_history/t2_tsdf_rehearsal_receipt.20260727T025727297495Z.b247794b5a68.json`에 보존되어 있다.
- 현재 T2의 8개 geometry/sample artifact SHA는 원 queue plan ledger의 각 SHA와 일치한다. 다만 canonical receipt SHA는 달라졌으므로 원 queue를 현재 path 기준으로 resume하지 않는다.
- continuation은 현재 SHA `393370ef...f039a7`과 아카이브된 원 SHA `6ef49bba...beda0b`를 둘 다 기록한다.
- training gate가 T2 receipt HEAD와 launch HEAD의 정확한 일치를 요구하므로, continuation 구현 전체를 커밋한 직후 T2를 **정식으로 정확히 1회** 재발행한다. 이 실행은 사전 선언된 필수 gate 갱신이며 기존 `393370ef...f039a7` receipt를 history에 보존한다.
- 그 T2 발행 뒤 queue 완료까지 git HEAD를 고정한다. 추가 T2 실행과 구현 커밋은 금지하고, 후속 확인은 파일 해시·스키마·status 읽기로만 수행한다.

## 8. 발행 계약

- 각 job이 끝나면 학습 completion, TSDF receipt, primary/legacy score, job complete, artifact ledger를 즉시 발행한다.
- queue 시작 전 smoke recovery attempt 005의 입력 crop, A′ seed top, TSDF filtered mesh top, TSDF surface top/section, Roofer CityJSON, reference GML, opacity trajectory를 한 패널로 재생성한다. 필수 칸이 placeholder이면 continuation 시작 관문을 통과시키지 않는다.
- queue status는 atomic snapshot + append-only event와 함께 유지한다.
- 마지막에만 continuation `complete.json`을 쓴다. 파국 중단이면 별도 terminal stop receipt를 쓰고 complete로 위장하지 않는다.
- 정량 표와 정성 패널을 함께 발행하고, 해석·판정 문장은 쓰지 않는다.
