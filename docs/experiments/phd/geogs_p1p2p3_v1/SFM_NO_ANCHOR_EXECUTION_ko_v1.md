# SfM/no-anchor 실행 기록

2026-09-09 · `PHD-GEOGS-SFM-NO-ANCHOR-v1` · `scientific_verdict: null`

상태 갱신: **2026-09-09 16:01:08 UTC(한국시간2026-09-10 01:01:08) 확인 당시 v2 P1(GPU0)·P2(GPU1) native 학습은 계속 실행 중이다. 상위 launcher의 잘못된 종료 신호를 GPU 해제로 해석한 P3가 조기에 GPU0로 들어가 camera 준비 중 CUDA OOM으로 실패했다. P1/P2 native 학습은 유지하고 제어 복구를 준비한다. 새22k/30k 표면·렌더·최종 품질 결과는 아직 없다.** 아래 첫 단계 PASS는 초기화·제어 확인이며 전체 학습 성공을 뜻하지 않는다.

실행 계획은 [SFM_NO_ANCHOR_PLAN_ko_v1.md](SFM_NO_ANCHOR_PLAN_ko_v1.md), 동일 참조점의 지지 전이 집계는 [추가 분석 계약](SFM_NO_ANCHOR_SUPPORT_DIAGNOSTIC_ko_v1.md)이다. Payload는 기존 GeoGS task의 `no_anchor_sfm_v1/`, 평가 출력은 `evaluation/no_anchor_sfm_v1/`로 분리한다.

## 입력·첫 단계 확인

| 지역 | 초기 SfM점 | 최초 보호점 | 첫 단계 | 실행 GPU |
|---|---:|---:|---|---:|
| P1 | 4412 | 519 | PASS_DIRECT_REFINEMENT | 0 |
| P2 | 5665 | 1437 | PASS_DIRECT_REFINEMENT | 1 |
| P3 | 19398 | 3236 | PASS_DIRECT_REFINEMENT | 0 |

신규 SfM점에는 ALS점이 없고, 첫 step 이전 optimizer moment도 없다. 원 prior 근접 matching과 native gradient hooks를 **첫 step 전** 적용한다. 첫 step에서 stage2 활성·anchor 실행0·ALS 가중치 .005·DA3 가중치 .05를 실제 확인했다. Native normal은 원 일정대로 7000 이후 활성화된다. 모든 공개·기계 판독 기록의 scientific verdict는 null이다.

Docker CPU 검증: 원 소스 불변, 두 Python 파일만 추가/변경된 격리 복사, 잘못된 SfM/optimizer/인자 차단, native matching의 `no_grad` 컨텍스트, 보호 gradient .01/비보호1, 초기·첫 step 감사 등 PASS. 초기 double-patch 거부 검사 실패와 보완을 `validation/runtime_cpu_v1/`에 보존했다. 이 CPU 검증은 실제 학습 검증을 대신하지 않으며, 실제 P1/P2/P3 첫 step도 별도 PASS했다.

고정 준비 source:

- `prepare_runtime.py`: `169c922fc2c4caf2096e1c1b0309f81cec6a4a20f4c1dc3916bf55492c140bc8`
- `jbgs_no_anchor.py`: `fab03183aba635ebf2ba161a1576a14f33b628ea582cc861e52791f342f6a01a`
- `train.py`: `3a7124bd9a2cb01fd7004bd5dbd9e35151a1ee3045187c0b77b01303561788ab`
- 원 model·renderer·extractor는 변경하지 않았다. 준비된 source 전체 SHA는 `source/jbgs_no_anchor_runtime_receipt.json`에 있다.

## 실행 명령과 상태 조회

```bash
bash scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/run_region.sh P2 1
bash scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/run_region.sh P1 0
bash scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/run_region.sh P3 0
```

각 명령은 train→22k export/seal/geometry/RGB/summary→30k 동일 후속 처리 순서다. 추출·기하 평가는 `locks/heavy_cpu.lock`으로 직렬화한다. 최대 두 GPU lane만 사용한다. 원 실행·서비스를 중단하거나 재시작하지 않았다.

- `queue/P*/status.txt`: 현재 단계. 최종 성공은 `READY_FOR_VIEWER_AND_REVIEW`, wrapper `exit_code.txt=0`.
- `runs/P*/SFM_noanchor_D005_Pnative/model/jbgs_trace.jsonl`: 100 step 간격의 실제 loss/control/point/resource 기록. 1/22k/30k 완전 상태를 추가 보존한다.
- 같은 run의 `model/jbgs_no_anchor/initialization.json`, `first_step.json`: 실제 초기 상태·제어 확인.
- 같은 run의 `native.log`, `gpu.csv`, `invocation.json`, 종료 후 `receipt.json`: 명령·소스·입력·결과 검증·시간.
- `exports/iteration_{22000,30000}/`: 실제 snapshot에서 만든 공식 렌더·512 TSDF raw/post, 별도 receipt.

기존 경로가 있으면 wrapper는 덮어쓰지 않고 거부한다. 실패 시 기존 로그·미완료 결과를 보존하고 원인과 재실행 경로를 이 문서 및 별도 receipt에 기록한다. 결과에 맞춰 학습 설정을 바꾸지 않는다.

## 최초 시도 실패와 진행 관측

최초 P1 시도의 `receipt.json`은 `FAIL`, native/validated exit code는 모두1, driver 구간은 **1573.364406909328초**다. `native.log`의 진행표시는10,780 부근에서 멈추고 `total_loss.backward()` → `rasterize_gaussians_backward`의 CUDA 할당 실패를 기록한다. 마지막100-step trace는 **10,700**, Gaussian **5,845,082개**, 보호 **519개**다. 진행표시와 정규 trace만으로 정확한 최종 optimizer 갱신 수를 만들어 넣지 않는다.

실패 시 CUDA 오류문은 allocated22.21GiB, reserved-but-unallocated468.99MiB, 추가 할당 요청90MiB를 기록한다. 이는 과거 Anchor1024의32GiB CPU TSDF OOM과 별개이며, 현재 새 학습의 GPU backward 실패다. 학습1/22k/30k 중22k와30k 결과를 얻지 못했으므로 P1 완료·추출 성공·품질 결과로 표시하지 않는다. 최초 시도의 로그·초기/첫-step snapshot·실패 receipt는 원 경로에 그대로 남긴다.

14:44 UTC 관측 당시 P2는13,700-step trace(Gaussian6,214,420개, 보호1,437개), P3는6,000-step trace(Gaussian2,998,018개, 보호3,236개)가 마지막이었다. 당시에는 두 지역의 최종 training receipt가 없고 학습 컨테이너가 실행 중이었다. 이 과거 진행 관측은 다음 종료 결과로 갱신되며 완료 예상이나 품질 판단이 아니다.

P2 최초 시도 역시 `FAIL`, native/validated exit code1로 종료했다. driver 구간은 **2739.4172524041496초**, 마지막 정규 trace는 **14,400**, Gaussian **9,264,498개**, 보호 **1,437개**이며 trace의 process elapsed는2733.779562883079초다. `rasterize_gaussians_backward`에서 allocated22.41GiB, reserved-but-unallocated656.37MiB, 추가 요청108MiB로 실패했다. terminal 진행표시의 Gaussian8,769,550개는 정규 trace의9,264,498개와 서로 다른 기록이므로 섞어 쓰지 않는다. 정규 trace는 완료 갱신 수의 하한이며 정확한 실패 step을 뜻하지 않는다.

P3 최초 시도는 `FAIL`, native/validated exit code1, driver 구간 **1374.0863612857647초**다. 마지막 정규 trace는 **8,700**, Gaussian **5,835,785개**, 보호 **3,236개**이며 terminal 진행표시는8,710 부근이다. P3는 backward가 아니라 `rasterize_gaussians` **forward**의13.42GiB 추가 할당에서 실패했다. 오류문은 GPU free13.12GiB, PyTorch allocated8.99GiB, reserved-but-unallocated666.79MiB와 별도 process260MiB를 기록한다. 따라서 세 지역 모두를 동일한 backward 실패로 묶지 않는다. Gaussian 수만으로 각 시점의 renderer 임시 메모리나 실패 원인을 설명하지 않는다.

실패 근거는 외부 기존 GeoGS task 기준 다음 파일이다.

- `no_anchor_sfm_v1/runs/P1/SFM_noanchor_D005_Pnative/receipt.json`: SHA256 `c2ceb2fab89d0807faf14e61e763153db78101b3562ac1d7f37787ed6b381c2b`
- 같은 run의 `native.log`: SHA256 `4c94c0657e6a5dbca99868d600df4d0b2ae90a7941d419679d252297bff2b41c`
- 같은 run의 `model/jbgs_trace.jsonl`, `model/jbgs_no_anchor/initialization.json`, `first_step.json`
- `no_anchor_sfm_v1/runs/P2/SFM_noanchor_D005_Pnative/receipt.json`: SHA256 `0d01c9a37d2afba17e7997de4c6b5e231cdc55cc77a5510b87233d0d2dc66e5b`
- 같은 P2 run의 `native.log`: SHA256 `5dd8632781dfcd6fb38d3667964a2c96fa5ff659a8efdfe421b3fce8d69530e1`
- `no_anchor_sfm_v1/runs/P3/SFM_noanchor_D005_Pnative/receipt.json`: SHA256 `bffaf0a2c5057ba4076b872b1b7e1f324d76f3d52971e9bc1438f6ca2c9e4868`
- 같은 P3 run의 `native.log`: SHA256 `17940aa6a9de231d4c62aabf3c1aad1e24983e16dd1324650a77032c0a6bb3af`

## 메모리 복구 v1의 준비·진행 기록

신규 경로는 기존 GeoGS task의 P1 **`no_anchor_sfm_memory_recovery_v1/`**, P2 **`no_anchor_sfm_memory_recovery_P2_v1/`**, P3 **`no_anchor_sfm_memory_recovery_P3_v1/`**다. 기존 실패 run을 이어 쓰거나 덮어쓰지 않고 SfM 초기화부터 다시 시작한다. 세 경로의 `config.json`은 기존 `no_anchor_sfm_v1/config.json`과 byte-identical이며 공통 SHA256은 `42c741c8682a7830bd53cde3add9a93b41030f1dcb718b9e2f23d78389834c13`이다. 메모리 보관·전송 정책과 구현 변경은 별도 소스·receipt로 기록한다. 변경은 다음 두 가지다.

- prior/DA3 깊이 cache를 CPU에 두고 현재 시점의 두 지도만 CUDA에 복사한다. 지도 값·크기·손실·가중치는 유지한다.
- Adam의 `exp_avg`/`exp_avg_sq`를 forward/backward 동안 CPU에 보관하고, 기존 CUDA optimizer step 직전에 GPU로 되돌린다. 파라미터·gradient·step counter·기존 CUDA 갱신식과 densification 설정은 유지한다.

RGB는 공식 현재 코드에서도 이미 CPU에 보관되어 있어 신규 GPU 절감분으로 계산하지 않는다. P1의 전체 depth cache는1.035508513GiB이며, 현재 시점 두 지도를 제외한 약1.025GiB를 GPU에서 덜 유지할 수 있는 계산이다. Gaussian5,845,082개일 때 두 Adam moment의 배열 크기는약2.526GiB다. 이 숫자는 보관 위치 변경의 잠재적 여유이며 실제 절감 peak나30k 완주 결과가 아니다. custom backward의 다른 working set, 이후 Gaussian 변화 및 전송/복원 순간의 필요 메모리가 남는다.

세 복구 source의 `source/jbgs_memory_recovery_receipt.json`은 `PASS_MEMORY_RECOVERY_RUNTIME_PREPARED`, SHA256 `4e26e64482737538aa29d13e5be2191d440a33e2bdc992a9c6f1cfdd99673cf0`이다. 원 소스는 그대로 보존하며 격리 복사의 `train.py`와 추가 `jbgs_memory_recovery.py`만 메모리 정책에 맞춘다. 원 no-anchor source 전체 hash와 파일 목록, parent receipt, 새 source 전체 hash를 실행 전에 검증한다. 준비 receipt의 `training_launched:false`는 source 준비 시점의 기록이며 이후 실제 실행 상태는 run trace·컨테이너·종료 receipt로 확인한다.

**실행 이슈 — 최초 GPU fixture 실패:** `torch.cuda.set_per_process_memory_fraction`에 index 없는 `torch.device('cuda')`를 넘겨 `ValueError: Expected a torch.device with a specified index or an integer, but got:cuda`가 발생했다. fixture 연산과 GeoGS 학습 전에 실패했고, 검증 스크립트만 `cuda:0`으로 고쳤다. runtime adapter/generator는 이 수정으로 바뀌지 않았다. [첫 실패 receipt](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/no_anchor_sfm_memory_recovery_v1/validation/equivalence_v1/failure_receipt.json)의 SHA256은 `df69e16f1ce1ea010abfb7d88f3a096c9e9239ffb5efff38d63843e8d6618685`다. 이 receipt는 exec session82452의 반환 오류를 후속 구조화한 기록이며 당시 raw stdout/stderr 파일인 것처럼 취급하지 않는다. 실패한 원 검증 파일은 `no_anchor_sfm_memory_recovery_v1/preparation_runtime/verify_memory_recovery.py`, SHA256 `f1e8643db1658747c714d6eb57403d8c9eaf1a9fc942c4d0142957ad51016b2d`로 보존했다.

수정한 작은 CUDA fixture에서는6-step parameter/gradient/moment/counter bitwise 동등성, 동적 parameter 교체, depth byte 보존, 상태 전이 차단을 확인했다. [두 번째 CUDA 검증 결과](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/no_anchor_sfm_memory_recovery_v1/validation/equivalence_v2/cuda.json)는 `PASS_CUDA_TOY_EQUIVALENCE`, SHA256 `48a69608a68928a87b6765656939b74b4d62505c67fe55af79193f9922d1f748`이며 allocator peak는64,512byte다. 같은 `equivalence_v2/`에 실제 `stdout.log`, `stderr.log`와 수정한 검증 source snapshot을 보존했다. 이 작은 검증은 실제 GeoGS 학습을 실행하지 않았고 전 학습의 bitwise 동등성·GPU 최대 절감량·30k 완주를 입증하지 않는다. 동일 준비 runtime을 사용하는 P2/P3 amendment는 이 검증을 재사용한다.

14:58:35 UTC에 P1 복구 컨테이너 `jbgs-geogs-no_anchor_sfm_memory_recovery_v1-P1-train`(GPU1)과 P2 복구 컨테이너 `jbgs-geogs-no_anchor_sfm_memory_recovery_P2_v1-P2-train`(GPU0)의 실행을 확인했다. 당시 P1은2,100-step trace(Gaussian131,921개, 보호519개), P2는800-step trace(Gaussian12,467개, 보호1,437개)가 마지막이었다. 두 run의 `model/jbgs_no_anchor/first_step.json`은 `PASS_FIRST_STEP_DIRECT_REFINEMENT`, `model/jbgs_memory_recovery/initialization.json`은 `PASS_MEMORY_RECOVERY_INITIALIZED`, `first_depth_transfer.json`은 `PASS_SELECTED_DEPTH_TRANSFER`다. P3 복구 run은 아직 시작하지 않았다. 완료 receipt가 없으므로 복구 성공이나 품질 결과로 표시하지 않는다.

실행 전 봉인된 각 `amendment.json`의 SHA256은 P1 `75dfc9d77ce3adaba47f0666f828eb2a8577d7511798f3625eff06ebdd55d1b5`, P2 `92638422758bd2988997e5c2a000f94d04c28467cbc2f4e439d5fdb285f848a3`, P3 `fc3ce9cb7eb9dcee08f4321107cd9126de36154c7b08c44ab5e3d1244d9d6901`이다. 원 실패 receipt/log, 공통 science config, 준비 source 및 CUDA fixture의 hash를 연결한다. 설정을 낮춰 완주한 실험으로 바꾸지 않으며, anchor 생략의 단독 효과·소스 변경의 우위·복구 성공에 대한 scientific verdict는 계속 null이다.

## 메모리 전송 진단과 v2 교체 검토 — 15:43 UTC 기록

메모리를 CPU로 옮기는 v1의 전송 비용을 줄일 수 있는지 실제 GPU0에서 작은 진단 두 개를 수행했다. 두 학습 process는 유지했고 각 진단 전에 `resource_deviation_before_probe.json`을 남겼다. **짧은 추가 GPU context 하나가 기존 두 학습과 겹쳤으므로 계획의 GPU process 수 제한에 대한 명시적 편차이며, 같은 GPU·PCIe를 사용한 구간의 학습·진단 시간에는 간섭 가능성이 있다.** 진단에는 실제 학습 입력·UAS 참조를 연결하지 않았고 optimizer step·렌더·기하 처리는 하지 않았다.

- `no_anchor_sfm_memory_recovery_v1/validation/transfer_probe_v1/transfer_probe.json`: `PASS_BOUNDED_TRANSFER_MEASUREMENT`, SHA256 `777d3dda816b123bb6a85a38389db15dcbcee741e92191eeac157fc3ea99be04`. 2/8/32MiB의 pageable/pinned H2D·D2H를 각6회 측정했다. transfer 측정 구간은0.092356613초, process 작업 시간은0.343202688초다. 명시적 GPU buffer는64MiB이며 CUDA context는 이 수치 밖이다. 사전 편차 기록 SHA256은 `1bf3d491aeeed2258bd957156290989a35753cdba06a8e0381d5d9908257417e`다.
- `no_anchor_sfm_memory_recovery_v1/validation/adapter_probe_v1/adapter_probe.json`: `PASS_BOUNDED_ADAPTER_MEASUREMENT`, SHA256 `f2aae02cc95eade727efbceed41b388896738d49f82c960eb52d20f1f7ed2ad9`. 고정100,000점의 Adam 상태 왕복에서 parameter·step·moment bytes 동일성을 확인했고, 반복쌍별 v1/v2 전송 cycle 시간비의 중앙값은 **2.220508배**였다. 이는 작은 storage cycle 결과이며 전체 학습속도 개선 배수가 아니다. warmup 포함 측정 구간은0.569006499초, torch import를 제외한 전체 작업은6.710939977초다. peak CUDA allocated는71,922,688byte, peak process RSS는635,183,104byte였으며 둘은 서로 다른 메모리 종류다. 사전 편차 기록 SHA256은 `86719484e852a466bc121d76c8ff37db5d74b313cf2bf8d3fa34ed24d09e8741`이다.

두 진단은 `exit_code.txt=0`이고 같은 폴더에 launcher/source·stdout/stderr·GPU 전후 기록이 있다. Adapter 진단 전에 정한 교체 검토 기준은 정확한 상태 확인과 paired cycle 비율≥2.0이었으며 이 작은 진단에서 충족했다. 실제 v2 runtime의 전체 검증·학습 완주를 대신하지 않는다.

15:43:27 UTC 조회 때 v1 P1/P2의 종료 receipt와 `stop_intent.json`은 아직 없었다. 검토 중인 새 경로는 P1 `no_anchor_sfm_memory_recovery_v2/`, P2 `no_anchor_sfm_memory_recovery_P2_v2/`, P3 `no_anchor_sfm_memory_recovery_P3_v2/`다. 교체를 실제 진행하면 우리 v1 native child만 SIGTERM으로 닫고 driver의 원 `FAIL`/native exit−15와 `stop_intent.json`의 `RESOURCE_TRANSFER_OPTIMIZATION`을 함께 보존한다. 이것을 CUDA OOM이나 복원 품질 실패로 바꾸어 기록하지 않는다. 이 문단은 아직 종료·v2 학습 시작을 확인한 기록이 아니다.

**15:50:11 UTC 실제 종료 확인:** 위 검토 후 P1/P2 v1의 native child에만 SIGTERM을 보내 종료했다. 두 training receipt는 원 상태 `FAIL`, native/validated exit−15이며 원 JSON·로그·trace를 보존한다. 목적은 `stop_intent.json`의 `RESOURCE_TRANSFER_OPTIMIZATION`이고 `stop_signal_receipt.json`은 실제 신호 전송을 기록한다. OOM 또는 학습 품질 실패로 분류하지 않는다.

| 의도적으로 종료한 v1 | driver 시간(초) | 마지막 정규 trace | Gaussian 수 | receipt SHA256 | stop intent SHA256 |
|---|---:|---:|---:|---|---|
| P1 | 3145.2078836071305 | 7800 | 2659155 | `26dc8376de5ef81b1ded880b6d07c983110812078beababf39996b480f2378d4` | `1b0e6e3767ef0de0505c14e439c5ebc3c42b1d34ab1fc69b1952bde43b3f9637` |
| P2 | 3084.8690470117144 | 9100 | 1388507 | `cba1c7e66471e7aae7688cda88fbf28c7b81785399cbe085cdb236db9fcaaeea` | `2ebbf7598d844a82ada6d6c8e764903329a1a26c9307f20648c9d7ef88d6dffa` |

각 파일 위치는 P1 `no_anchor_sfm_memory_recovery_v1/runs/P1/SFM_noanchor_D005_Pnative/`, P2 `no_anchor_sfm_memory_recovery_P2_v1/runs/P2/SFM_noanchor_D005_Pnative/`다. 같은 폴더의 `native.log` SHA256은 P1 `560bec56c5b6ead3c4556904778dfdadefbfe7e866eaf3d162c42f5ae4cca176`, P2 `5d4e72e35f31e757a7e7e2b42ec3fdf1a01f3147aa762776a22bcc5c8b54dbfa`다. 마지막 trace는 정확한 최종 optimizer 갱신 수가 아니라 기록된 하한이다. v1 P3는 학습하지 않았으므로 이전 학습 비용을 만들어 넣지 않는다.

v2의 실제 준비 source를 사용한 `no_anchor_sfm_memory_recovery_v2/validation/runtime_cuda_v1/receipt.json`은 `PASS_CUDA_RUNTIME_FIXTURE`, SHA256 `fd129940942571ebc506a3d6e4f28843066df1ecc4fa1df65c97059e79ed67b7`다. 합성 optimizer8-step의 상태 동등성 등을 확인했고 fixture 구간은0.824793707초, 최대 CUDA allocated는44,544byte이며 실제 장면 학습은 수행하지 않았다. 봉인 도구는 실제 source 전체 Python 파일·SHA와 runtime map·검증 map을 비교하고 generator/runtime adapter/pinned storage SHA도 확인한다. 같은 source bytes를 쓰는 P2/P3는 P1의 검증을 재사용할 수 있다. v2의 추가8k/15k 완전 상태 저장은 별도 amendment metadata로 기록하며 학습 설정 변경과 구분하고 저장 시간·메모리 비용을 측정한다.

## v2 실제 봉인·시작과 이전 시도 비용

15:51:22 UTC에 `jbgs-geogs-no_anchor_sfm_memory_recovery_v2-P1-train`(GPU0)과 `jbgs-geogs-no_anchor_sfm_memory_recovery_P2_v2-P2-train`(GPU1) 컨테이너 실행, 두 run의 `model/jbgs_no_anchor/first_step.json`의 `PASS_FIRST_STEP_DIRECT_REFINEMENT`, 메모리 초기화 PASS를 확인했다. 당시 마지막 trace는 P1 **600**(Gaussian5,066개·보호519개), P2 **900**(Gaussian15,895개·보호1,437개)였다. v2 P3는 준비·봉인 상태이며 학습 trace는 없었다. 세 봉인 모두 추가 완전 상태 저장 `[8000,15000]`을 기록하며 원 과학 config는 변경하지 않는다.

| 지역 | v2 amendment 경로(task 상대) | SHA256 | 이전 자원 시도 연결 |
|---|---|---|---|
| P1 | `no_anchor_sfm_memory_recovery_v2/amendment.json` | `7292398bbd7bf36b39a3012d9329e1f8e1ad4b29faf23ec299415b6688a9790c` | 의도적으로 종료한 P1 v1 1건 |
| P2 | `no_anchor_sfm_memory_recovery_P2_v2/amendment.json` | `cf72dfcfc7d776cc1dac1423b752a4445e2361816ee77c4e8703a26f74cff5b7` | 의도적으로 종료한 P2 v1 1건 |
| P3 | `no_anchor_sfm_memory_recovery_P3_v2/amendment.json` | `038e955e48b96f411e655be97dc3da39352ef8ffb01039d20f2c91fdc8bfc00c` | 없음; P3 v1은 학습하지 않음 |

현재 닫힌 신규 학습 시도들의 driver 작업시간만 더하면 최초3지역 OOM 시도 **5686.868020599242초**, 의도적으로 교체한 v1 P1/P2 **6230.076930618845초**, 합계 **11916.944951218087초**다. 겹쳐 실행한 시도를 합친 자원 작업시간이며 실제 달력 경과시간이 아니다. 진행 중 v2, 준비·입력 변환·진단 probe 및 기존 바닐라 비용은 이 합계에 포함하지 않았다. trace 시간은 driver 구간에 이미 포함되며 메모리 peak는 더하지 않는다. 이 종료 이력을 원 실패·의도적 교체로 나누어 보존하고 품질 실패 건수로 합치지 않는다. v1 worker의 종료값241은 native/validated−15가 shell 종료 코드로 전달된 결과이며 원 producer receipt의−15를 유지한다.

## 상위 launcher 종료·P3 조기 시작 사건

[SFM-QUEUE-001 상세 근거](ISSUES_ko_v1.md#sfm-queue-001--상위-launcher-종료-기록을-gpu-lane-해제로-오인한-p3-조기-시작)에 원인·미확인 부분·원 파일 SHA를 기록했다. 15:57:55 UTC에 두 P1/P2 queue의 exit0이 생겼지만 status는 `TRAINING`, train receipt는 없고 native 컨테이너는 계속 실행되었다. P3 대기 source는 이 파일의 존재만 확인해15:58:03 UTC에 같은 GPU0로 시작했다. P3는 첫 trace 전에 camera의 CUDA 준비에서 OOM으로 실패했고 native driver 구간은 **5.029073881916702초**다. 기존 native 학습과 GPU 사용이 겹친 기술 실패이며 모델의 복원 성능 실패가 아니다.

16:01:08 UTC의 마지막 정규 trace는 P1 **5800**(Gaussian2,351,740개·보호519개), P2 **6700**(Gaussian947,333개·보호1,437개)였다. root가 관측한 exec session49373/75332 exit143과 EXIT trap의0 기록은 상위 shell의 SIGTERM 가능성과 부합하지만, 신호를 보낸 주체는 확인하지 못했다. 기존 종료 파일·실패 run은 그대로 보존한다. 지속 supervisor의 복구 성공·P3 새 실행을 이 관측만으로 선언하지 않는다.

후속으로 `orchestration_recovery_v1/P1/`, `P2/`의 독립 supervisor(PID1764349/1764368, 16:02:25 UTC 시작)가 기존 native 학습을 유지하면서 종료 receipt·컨테이너 해제를 기다리는 것을 확인했다. P3 새 경로 `no_anchor_sfm_memory_recovery_P3_v3/`에는 동일 storage v2 코드·과학 config를 사용하며 조기 v2 초기화 실패를 `prior_initialization_failure` receipt/log/cause로 바인드하는 봉인 기능을 추가했다. P3 새 대기 source는 producer 종료·supervisor 실제 종료·GPU0 compute 부재·P1 container 부재를 함께 확인한다. 이 제어 복구 기록은 P3 새 학습 시작·완료를 대신하지 않는다.

## 자원 표의 지역별 시도 선택

[고정 접두부 자원 그림](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_v1/resource_progress_v2/training_resource_progress.png)은 **2026-09-09 15:20:02 UTC(한국시간2026-09-10 00:20:02)**에 복사한 trace snapshot으로 만들었다. 바닐라 D005, 최초 SfM 실패, 별도 복구의 Gaussian 수와 process 누적 CUDA allocated peak를 지역별로 비교한다. 이때 복구 P1은5,400, P2는6,800까지 기록되었고 P3 복구 trace는 없었다. 원 실패 시도와 복구를 이어 붙이지 않았고, P1 바닐라 anchor≤8000과 복원 process>8000도 서로 다른 구간·메모리 counter로 유지했다. 최종 자원 표나 복구 성능 결과가 아닌 부분 진행 진단이다.

같은 `resource_progress_v2/`에 PDF, `trace_points.csv`(1,365행), `attempt_segments.csv`, 원본 접두부 `snapshots/`, 생성 script snapshot, `receipt.json`, 실제 Docker 명령 `docker_invocation.json`, 실제 그림 표시 확인 `visual_qa.json`을 보존했다. 생성은 CPU2개·RAM1GiB·network none·GPU 비노출 Docker에서 수행했다. 첫 `resource_progress_v1/` 그림은 공통 y축 설정으로 다른 지역의 큰 값이 잘리는 표시 오류가 있어 `visual_qa.json`에 실패를 기록하고 보존했다. v2는 모든 지역의 최대값으로 범위를 정해 다시 생성했으며 실제 표시를 확인했다. 원 trace와 CSV의 수치는 이 표시 오류로 변경되지 않았다.

[자원 집계 스크립트](../../../../scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/summarize_resources.py)는 기본적으로 원 실험 경로를 읽고, 지역별 별도 복구 경로를 선택할 수 있다. 실제 표 생성은 학습 종료 뒤 수행한다.

```bash
python summarize_resources.py \
  --task /task \
  --experiment /task/no_anchor_sfm_v1 \
  --region-experiment P1=/task/no_anchor_sfm_memory_recovery_v2 \
  --region-experiment P2=/task/no_anchor_sfm_memory_recovery_P2_v2 \
  --region-experiment P3=/task/no_anchor_sfm_memory_recovery_P3_v2 \
  --out /out/resources
```

지역 override를 생략하면 해당 지역은 원 실험 경로를 유지한다. 지정한 복구 경로에 닫힌 PASS training receipt와1/100/22k/30k trace가 없으면 해당 지역은 완료 표에서 제외하고 미완료 상태를 표시한다. 준비만 한 P3를 실행·완료로 표시하지 않는다. 원 P1/P2/P3 실패 비용은 **`new_failed_training_attempts.csv`**에 별도로 남긴다. 서로 다른 실제 시도의 driver 작업시간은 자원 사용량으로 합산할 수 있지만, 중첩 실행의 달력 경과시간이나 메모리 정점을 더하지 않는다. 마지막100-step trace의 iteration은 완료 갱신 수의 하한이며 정확한 실패 step이 아니다. trace 시간과 이를 포함하는 driver 시간을 중복 합산하지 않는다.

선택한 v2 `amendment.json`에 `prior_resource_attempts[{receipt:{path,sha256},stop_intent:{path,sha256}}]`가 있으면 자원 집계는 이전 시도의 receipt·stop intent를 SHA와 지역에 맞춰 검증하고 비용을 보존한다. `RESOURCE_TRANSFER_OPTIMIZATION`과 실제 native exit−15가 함께 있어야 **의도적 자원 구현 교체**로 분류하며, OOM은 hash를 기록한 native log에서 CUDA OOM 오류를 확인한 경우만 분류한다. `new_prior_resource_attempts.csv`는 이전 시도의 계보 표이고 `new_failed_training_attempts.csv`와 같은 시도 행을 공유할 수 있으므로 두 표를 더하지 않는다. 비용 합산 시 receipt 경로·SHA로 중복을 제거한다. v2 경로는 같은 `--region-experiment` 인자로 지정하며 v2 시작·완료 여부를 이 기능만으로 추정하지 않는다.

P3 새 경로의 `prior_initialization_failure:{receipt:{path,sha256},log:{path,sha256},cause:"RESOURCE_SCHEDULING_ERROR"}`는 조기 초기화 실패5.029073881916702초를 별도로 보존한다. first-step audit가 없고 native exit1·동일 지역/condition·원 generic CUDA OOM 로그가 확인되어야 이 분류를 허용한다. `cuda_oom_observed_in_log:true`와 `counted_as_training_cuda_oom:false`를 구분하며 `new_prior_initialization_failures.csv`는 같은 비용의 계보 보기로서 다른 시도 표와 더하지 않는다. 이전 의도적 종료·OOM 비용을 누락하거나 새 quality0으로 바꾸지 않는다.

## 아직 남은 일

세 지역 전체의 학습·추출·기하/RGB 평가, 같은512 새 viewer profile 표시 검증, 고정 단면·실제 사진의 수동 검토, 지지 전이와 자원 표 집계, 결과 해석·인계가 남았다. 기존 과거 Anchor1024 OOM과 현재 신규 실험 상태를 섞지 않는다.

## 최종 자원 구현 v3와 P2 준비 오류 복구 — 2026-09-09 17:18:24 UTC

고정 정책 `contracts/sfm_final_resource_retry_v1.json`의 SHA256은 `edf3f4312c622059a3506c6ca1c07d2b1c90e234fb672cc592ea3ea7e28f5a9a`다. 선택한 이전 실행이 실제 자원 실패로 닫혔을 때만 지역당 추가 fresh 학습1회를 허용한다. 새 경로는 `no_anchor_sfm_gradient_memory_v3_P1/P2/P3`이며 `resource_recovery_version:3`, `storage_version:2`다. 과학 config SHA256 `42c741c8682a7830bd53cde3add9a93b41030f1dcb718b9e2f23d78389834c13`과 SfM/카메라/깊이 입력을 유지한다. 이전 gradient를 다음 forward 전에 해제하고 PLY를 동일61개 float32 필드·순서·바이트로 나누어 저장한다. fullstate resume는 추가하지 않는다. `[1,8000,15000,22000,30000]` capture와 원 학습 일정은 유지한다.

P2 이전 storage-v2 실행은 native/validated−9로 닫혔다. `resource_observations_sfm_final_v1/P2/20260909T170815170028144/resource_failure_receipt.json`(SHA256 `f4c53f61d6144a94903b06540ec562059c875239647c45b9935528d1b88fcb24`)은 커널 `CONSTRAINT_MEMCG`, 정확한 Docker container ID, victim PID1710624,32GiB cgroup 제한 도달을 연결한다. 이는 확인된 **host RAM cgroup OOM kill**이며 CUDA OOM과 구분한다. `.Name`은 초기 inspect stdout에 없었으므로 실제 inspect 명령의 대상 이름을 별도 증거로 보존했다. container 자동 제거 후의 unavailable cgroup 읽기와 빈 Docker events는 원인 증거가 아니다. 15k `checkpoint.pth`만 남고 PLY/완전 상태 receipt가 없으므로15k 완전 checkpoint로 간주하지 않는다.

P2 최종 자원 구현 준비의 첫 preflight는 원인 증거3개 외 추가 관측·실패 로그도 포함한 전체 `evidence[]`를 허용하지 않아 `Unexpected cgroup evidence role or duplicate`로 종료1이었다. **config·source·학습 생성 전에 발생한 검증 구현 오류**다. 모든 증거의 SHA/bytes 검사는 유지하고, 원인 교차검증에는 `kernel_journal`, `docker_inspect`, `docker_inspect_command`만 사용하도록 보완했다. 이전 `preparation_runtime/` 전체는 같은 새 P2 root의 `failed_preflight_v1/`로 이동해 원 byte를 보존했다. 명시적 `retry_preflight_v1` gate는 이 정확한 P2 실패·빈 input 디렉터리·미생성 config/source/runs/amendment만 허용한다. 새 학습을 한 번 더 수행한 것으로 계산하지 않는다.

P2 CPU 재준비와 봉인은 PASS했다. `no_anchor_sfm_gradient_memory_v3_P2/amendment.json` SHA256은 `f563709dccc11e56fbe95e612c6b0922d795bacdba9bfaf7bae367139ffeb586`, `source/jbgs_memory_recovery_receipt.json`은 `522c1347f7bc7c0fdb7936e06a6e6342dda3fb1105a8fcce9dbc01727a34c06d`다. `preparation_runtime/preparation_retry.json`(SHA256 `a67c5a5e9d2cc1c3926064b7dfab66d8b0dcb0d5f15758ab50a32b6f51561a23`)은 보존한 실패 파일별 SHA와 `training_attempts_started:0`을 기록한다. CUDA 증거는 동일 source의 P1 `validation/runtime_cuda_v1/receipt.json`을 재사용했고, sealer가 source map·검증 소스 SHA·8-step CUDA 상태 동등성 및 PLY 바이트 동등성 기록을 확인했다. 실제 P1/P2 봉인 bundle의 CPU 재검증과 신규/기존13개 회귀 검사도 PASS했다.

학습 컨테이너는 task 전체 대신 `final_retry_evidence/`의 한정된 read-only 복사만 읽는다. 정책, CUDA 검증, 이전 training FAIL·first step·amendment, 원 OOM·의도 중단·초기화 실패 계보를 확인한다. v3 최종 PASS에는 `resource_recovery_version:3`, 이전 gradient 해제30000회, 원 backward 전 zero_grad 유지, 각 complete snapshot의 streamed PLY SHA를 요구한다. 상속된 v2 lifecycle receipt만으로 PASS를 선언할 수 없다. 이 기록의17:18:24 UTC 확인 범위는 **P2 준비·봉인·읽기 검증**이며, P2 신규 GPU 학습 시작이나 완주·품질 결과를 의미하지 않는다. `scientific_verdict: null`.

## P1 마지막 자원 재시도 종료와 P2/P3 실행

P1 `no_anchor_sfm_gradient_memory_v3_P1/runs/P1/SFM_noanchor_D005_Pnative/`는 실제 FAIL, native1, driver3254.0149105349556초로 닫혔다. 메모리 lifecycle의 마지막 완료 iteration은10608이며 다음10609의 Gaussian renderer backward에서1.16GiB 추가 CUDA 할당이 실패했다. 오류 당시 보고된 가용 메모리는10.38MiB, PyTorch allocated22.93GiB다. 마지막 정규 trace10600의 Gaussian 수는6,495,677이며 실제 마지막 갱신 횟수와 구분한다. 이전 gradient 해제10609회와8k streamed PLY 저장은 실행됐지만30k 완료 조건을 충족하지 못했다. 기존 desktop이 없는 GPU1에서도 발생했으므로 이 실패를 desktop 메모리만의 영향으로 설명하지 않는다. 전체 source trajectory 동등성 또는 Anchor 필요성을 이 실패만으로 주장하지 않는다.

원 receipt·native log·8k 완전 상태·amendment를 보존한다. 고정 상한에 따라 P1의 추가 학습은 종료하며22k/30k 결과를 미제공으로 표시한다. 사전에 선택한 역사적 storage-v2 8k 보조 진단은 이 새8k로 교체하지 않는다.

P3의 역사적8k 공식 추출 PASS와 GPU0 해제를 확인한 뒤 P2 마지막 재시도를 GPU0에서 시작했다. 이후 P1 마지막 시도의 native·독립 supervisor 종료, exit1, GPU1 compute 목록 부재를 확인하고 P3 마지막 재시도를 GPU1에서 시작했다. `launch_final_retry.sh`와 각 `detached_run_v1/`에 실제 명령·GPU 시작 관측·상태를 보존한다. GPU lane lock과 기존 서비스는 유지한다.

P3의 마지막 시도 역시 `no_anchor_sfm_gradient_memory_v3_P3/runs/P3/SFM_noanchor_D005_Pnative/receipt.json`에서 FAIL/native1, driver2354.3413484441116초로 닫혔다. 마지막 완료는8541, 다음8542의 `diff_surfel_rasterization` backward에서1.33GiB 할당이 실패했고 오류가 보고한 가용량은1.18GiB였다. 마지막 정규8500 trace의 Gaussian 수는7,424,205, peak CUDA allocated24,406,710,784byte, peak RSS15,364,325,376byte다. 내부 CUDA0 표시는 컨테이너에 노출된 host GPU1을 가리킨다. 정확한 host GPU는 invocation·GPU UUID로 확인한다. `detached_run_v1/exit_code.txt=1`과 실제 GPU1 compute 부재도 확인했다.8k 완전 상태는 보존하지만 고정 역사적8k 비교 상태로 대체하지 않는다. 지역별 추가 fresh1회 상한에 따라 P3를 다시 실행하지 않으며22k/30k는 미제공이다.

## P2 종료와 주 비교 미제공 — 2026-09-09 21:51 UTC

P2 마지막 시도도 `FAIL`/native·validated1로 종료했다. driver13,834.020002713893초, peak child RSS14,222,950,400byte다.22,000번째 optimizer 반환 뒤 정기 평가 renderer가11.04GiB 요청/free8.62GiB의 CUDA OOM을 기록했다. 전체 iteration 경계의 마지막 완료21999, 마지막 일반 trace21900, N10,334,149·보호1,437을 구분한다. source의 정기 평가가 일반 PLY/complete capture보다 먼저이므로22k 상태는 저장되지 않았다. 마지막 완전 상태15k와 부분 정기 평가 PNG만 남는다. 실패 원문·보관 상태·정확한 SHA는 [SFM-FINAL-REPORT-OOM-001](ISSUES_ko_v1.md#sfm-final-report-oom-001--p2-정기-평가-실패로22k-저장-미도달)에 있다.

이후 export/evaluation은 train PASS gate 때문에 시작하지 않았다. 고정22k RGB preview도22100 trace와22k PLY가 없어 실행하지 않았다. 별도 driver/gallery 개발 파일은 보존하고 GPU 렌더를 재시도하지 않았다. 세 지역의 마지막 native·독립 supervisor가 모두 실패 종료했으며 추가 fresh 학습은 하지 않는다. 오래 남은 status.txt 단계 문구를 실행 중으로 해석하지 않는다.

주22k/30k12후보는 실제 train 실패를 담은 `evaluation/no_anchor_sfm_v1/profiles/main_final_partial_v1/`로 발행한다. 별도 역사적8k의3지역 공식 RGB·TSDF512 raw/post·정량·정성·browser 검증 결과는 `evaluation/no_anchor_sfm_prefix8000_v1/`에 있다. 실제 발행 명령·비용 합산·최종 QA는 인계의 종료 절과 산출물 receipt를 따른다. 기존 baseline·서비스·원 실패·dirty 연구 문서는 보존한다. `scientific_verdict: null`.
