**SfM no-anchor 최종 발행 준비 감사 — 조건부 실행 안내 v1**

작성일: 2026-09-10. `scientific_verdict: null`.

이 문서는 현재 코드를 읽어 확인한 조건부 실행 안내다. **P2의 학습·22k/30k 추출·평가·최종 발행이 완료됐다는 보고가 아니다.** 작성 당시 root의 최신 관측은 P2 최종 재시도가 약 15,700회까지 진행 중이라는 것이었다. 이 문서를 작성하며 새 학습, 추출, 평가, GPU 작업 또는 테스트를 실행하지 않았다. 기존 코드·설정·문서·payload는 변경하지 않았으며 이 문서만 추가했다.

현재 상태는 [인계 문서의 현재 절](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_HANDOFF_ko_v1.md)을 먼저 읽고 해석했다. P1/P3 최종 재시도는 CUDA OOM으로 닫혔고 추가 학습은 허용된 최종 재시도 횟수를 소진했다. P2의 최종 종료 상태는 아직 확정하지 않는다. 역사적 선택 실행의 보조 8k 결과는 별도 계보이며, 최종 22k/30k 결과를 대신하지 않는다.

**선택과 부분 상태**

고정 최종 실행은 `no_anchor_sfm_gradient_memory_v3_P1`, `no_anchor_sfm_gradient_memory_v3_P2`, `no_anchor_sfm_gradient_memory_v3_P3`이다. `final_retry.py:169–190`은 봉인된 최종 재시도가 있으면 그 실행을 선택하고, 실패해도 이전 실행으로 돌아가지 않는다. `publish_review.sh:35–48`은 선택을 파일로 먼저 고정한 뒤 같은 선택을 viewer와 resource summary에 전달한다.

각 지역은 22k/30k × raw/post의 네 후보를 갖는다. `build_viewer.py:156–210, 426–458, 501–520`에서 확인한 예상 상태는 다음과 같다. 아래 표는 미래 P2 결과에 대한 분기이며 실제 완료 수치가 아니다.

| 최종 P2 상태 | 전체 12개 후보 | 최종 profile의 geometry 상태 |
|---|---|---|
| 학습 진행 중 | P1/P3 8개 failed, P2 4개 pending | `PARTIAL_GEOMETRY_MATRIX` |
| 학습 PASS, 두 예산 추출·기하 평가 완료 | P1/P3 8개 failed, P2 4개 actual | `PARTIAL_GEOMETRY_MATRIX` |
| 학습 FAIL | 12개 failed | `PARTIAL_GEOMETRY_MATRIX` |
| 학습 PASS, 22k export FAIL, 30k 추출·기하 평가 완료 | 22k 2개 export failed, 30k 2개 actual, P1/P3 8개 train failed | `PARTIAL_GEOMETRY_MATRIX` |
| 학습 PASS, export receipt가 아직 없음 | 해당 예산 pending | `PARTIAL_GEOMETRY_MATRIX` |

실패 후보는 `data`, `mesh_data`, `optimizer_updates`가 `null`이고 실제 실패 phase와 receipt SHA를 보존한다. 현재 P1/P3의 로그 오류는 `CUDA_OOM`으로 분류되는 코드 경로다. receipt가 없으면 진행 중·미실행으로 남으며 실패를 추정하지 않는다. 미생성 품질을 F1=0으로 채우지 않는다. 다른 시도의 기존 geometry가 같은 출력 위치에 있으면 계보 불일치로 중단하며 이를 대체 결과로 수용하지 않는다.

부분 표시에 다음 한계가 있다. `COMPLETE_GEOMETRY_MATRIX` 자체는 RGB·summary 완료까지 보증하지 않는다. train/export PASS 이후 평가 작업이 실패했더라도 기하 index가 없으면 `NOT_ASSESSED_EVALUATION_PENDING`으로 남는다. 기하 index가 있고 RGB 평가가 미완료인 경우에는 geometry가 제공될 수 있다. 따라서 최종 보고에서는 평가 단계의 실제 종료 기록과 browser QA를 별도로 확인해야 한다. 선택된 실행의 native `-9`만 있고 확인 가능한 메모리 오류 로그가 없다면 viewer는 일반 `PRODUCER_FAILURE`로 남기며 임의로 cgroup OOM을 확정하지 않는다.

**22k 실패 후 30k 독립 완결**

`run_region.sh:3, 20–32`는 `set -e` 아래에서 22k export → seal → geometry → renders → summary를 끝낸 다음 30k를 처리한다. 따라서 22k의 어느 단계든 실패하면 30k가 자동으로 이어지지 않는다. `run_region.sh`를 다시 호출하면 학습부터 재진입하려 하고 기존 queue도 거부하므로 후속 작업에 사용하지 않는다.

반면 `run_phase.py:211–227`의 export는 **학습 PASS와 지정한 iteration의 complete snapshot**을 직접 읽는다. 22k export PASS를 요구하지 않는다. `evaluate.py:264–324`도 해당 iteration의 export와 snapshot을 봉인하므로 30k만 독립적으로 완료할 수 있다.

아래 명령은 다음 조건을 모두 확인한 뒤 root가 실행할 수 있는 안내다. 현재 진행 중인 P2에 실행한 명령이 아니다.

- 선택된 P2의 `runs/P2/SFM_noanchor_D005_Pnative/receipt.json`이 실제로 닫힌 PASS이고, 30k complete snapshot이 producer 검증을 통과했다.
- 해당 P2 학습과 기존 worker가 종료됐고 **GPU 0의 사용 소유권과 실제 해제**를 확인했다. 여기서는 기존 P2 lane인 GPU 0을 유지한다. GPU 1로 임의 이동하지 않는다. `run_phase.sh` 자체는 다른 작업의 GPU 점유를 자동으로 판정하지 않는다.
- 30k export와 해당 평가 단계의 출력이 아직 없다. 기존 실패·부분 출력이 있으면 삭제하거나 덮어쓰지 않는다. 아래 명령은 깨끗한 미실행 30k 경로용이다.
- 추출과 기하 평가는 기존 `no_anchor_sfm_v1/locks/heavy_cpu.lock`을 사용한다. 이 lock은 GPU 예약을 대신하지 않는다.

```bash
set -euo pipefail
geogs_review_code=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1
geogs_review_task=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1
geogs_review_attempt=no_anchor_sfm_gradient_memory_v3_P2

test ! -e "$geogs_review_task/$geogs_review_attempt/runs/P2/SFM_noanchor_D005_Pnative/exports/iteration_30000"
for geogs_review_stage in seal geometry renders summary; do
  test ! -e "$geogs_review_task/evaluation/no_anchor_sfm_v1/execution/P2/R30000/$geogs_review_stage"
done

flock "$geogs_review_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
  bash "$geogs_review_code/run_phase.sh" P2 export 0 30000 "$geogs_review_attempt"
bash "$geogs_review_code/evaluate.sh" P2 30000 seal 0 "$geogs_review_attempt"
flock "$geogs_review_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
  bash "$geogs_review_code/evaluate.sh" P2 30000 geometry 0 "$geogs_review_attempt"
bash "$geogs_review_code/evaluate.sh" P2 30000 renders 0 "$geogs_review_attempt"
bash "$geogs_review_code/evaluate.sh" P2 30000 summary 0 "$geogs_review_attempt"
```

이 경로는 학습을 재시작하거나 resume하지 않는다. export는 기존 공식 `render.py --iteration 30000 --mesh_res 512 --num_cluster 50`을 사용한다. GPU를 쓰는 export와 RGB 평가, CPU 평가의 자원·mount·출력 검증은 기존 wrapper가 유지한다. UAS reference는 기하 평가 단계의 evaluation-only 입력이며 학습·공식 export 입력이 아니다. 단계별 실패 시 원래 receipt/log/exit code를 보존하고 다음 단계의 성공을 추정하지 않는다.

**리소스 비용: 보존되는 이력과 중복 없는 합산 범위**

실제 최종 amendment의 연결은 다음과 같다. 이는 실행 결과의 우열 선택이 아니라 고정 재시도 비용 계보다.

| 지역 | 원 SfM 실행 외에 연결된 실행 |
|---|---|
| P1 | `no_anchor_sfm_memory_recovery_v1` 의도중단 → `no_anchor_sfm_memory_recovery_v2` 실패 → 최종 `no_anchor_sfm_gradient_memory_v3_P1` |
| P2 | `no_anchor_sfm_memory_recovery_P2_v1` 의도중단 → `no_anchor_sfm_memory_recovery_P2_v2` cgroup OOM predecessor → 최종 `no_anchor_sfm_gradient_memory_v3_P2` |
| P3 | `no_anchor_sfm_memory_recovery_P3_v2` 초기화 scheduling 실패 → `no_anchor_sfm_memory_recovery_P3_v3` 실패 → 최종 `no_anchor_sfm_gradient_memory_v3_P3` |

`summarize_resources.py:225–307`은 명시적으로 봉인된 연결만 따라가며 attempt folder를 key로 중복 제거한다. P2 predecessor의 cgroup OOM 분류는 봉인된 별도 자원 증거에 근거한다. 의도중단은 `RESOURCE_TRANSFER_OPTIMIZATION` + native `-15`, 초기화 scheduling 실패는 그 별도 receipt/log와 first-step 부재에 근거하며 학습 CUDA OOM과 구분한다.

현재 선택 계보에서 중복 없는 producer work 합산 집합은 다음과 같다.

```text
unique_by(source_path, source_sha256)(
    new_phase_resources
    UNION new_failed_training_attempts
)
```

`new_phase_resources`는 선택된 PASS 학습과 그 학습 뒤에 닫힌 export PASS/FAIL 비용을 포함한다. `new_failed_training_attempts`는 원실행·봉인된 과거 실행·최종 실패를 포함한다. **코드는 grand-total 숫자를 직접 출력하지 않는다.** `new_prior_resource_attempts`, `new_final_retry_predecessors`, `new_prior_initialization_failures`는 같은 기록의 계보 보기이므로 위 집합에 다시 단순 합산하면 중복된다. 이 구분은 `summarize_resources.py:456–480, 503–519`에 명시돼 있다.

서로 다른 producer의 driver work seconds는 합산할 수 있지만, 이는 동시 실행을 포함한 총 작업량이며 실제 달력 경과 시간이 아니다. driver wall에 이미 포함된 trace elapsed를 더하거나, 원래 전체 phase에 그 phase의 anchor prefix를 더하거나, 여러 실행의 메모리 peak를 더하면 안 된다. 이 집합은 학습·export producer 비용이며 모든 평가·browser QA·실험 외 작업을 합친 전 시스템 비용은 아니다. CPU moment offload, Gaussian 수, fresh densification 일정, snapshot I/O, GPU 동시 점유가 함께 영향을 주므로 순수 Anchor 생략 속도 효과로 해석하지 않는다.

P2 학습 PASS일 때 resource summary 상태는 `COMPLETED_REGIONS_SUMMARIZED`, 포함 지역은 P2이며 실패한 P1/P3 비용은 실패 이력 표에 남는다. 전부 학습 FAIL이면 `NO_COMPLETED_TRAINING_REGIONS`이며 실패 비용 표는 유지한다. 앞의 상태는 mesh/RGB 완료나 과학적 성공 판정이 아니다. 완료 지역에 대해서만 baseline 비교 표를 구성하므로 P1/P3 baseline 행의 부재를 비용 0으로 해석하지 않는다.

**부분 발행과 실제 browser QA**

선택된 P2의 학습 및 실행할 export/평가가 닫힌 후, 반드시 새 profile ID와 `partial`을 사용한다. 기본 `complete`는 누락 배열 때문에 실패할 수 있고, 그 전에 생성된 profile/resources는 남는다. 실패한 발행을 같은 ID로 덮어쓰지 않는다. 아래 `main_final_partial_v1`도 실제 실행 전에 미사용 ID인지 확인한다.

```bash
geogs_review_profile=main_final_partial_v1
geogs_review_qa=main_final_partial_v1_actual_v1
test ! -e "$geogs_review_task/evaluation/no_anchor_sfm_v1/publication/$geogs_review_profile"
test ! -e "$geogs_review_task/evaluation/no_anchor_sfm_v1/profiles/$geogs_review_profile"
test ! -e "$geogs_review_task/no_anchor_sfm_v1/validation/browser_qa/$geogs_review_qa"

bash "$geogs_review_code/publish_review.sh" "$geogs_review_profile" partial \
  --region-experiment P1=/task/no_anchor_sfm_gradient_memory_v3_P1 \
  --region-experiment P2=/task/no_anchor_sfm_gradient_memory_v3_P2 \
  --region-experiment P3=/task/no_anchor_sfm_gradient_memory_v3_P3
bash "$geogs_review_code/browser_qa.sh" "$geogs_review_profile" "$geogs_review_qa" 8902 --allow-partial
```

발행은 기존 Docker CPU 경로이며 학습 GPU를 추가로 사용하지 않는다. browser QA는 기존 software GL browser image를 사용하고 서비스 재시작을 하지 않는다. 발행 receipt의 `ADDITIVE_PROFILE_CREATED`는 실제 browser QA를 대신하지 않는다. 별도 QA는 actual mesh·명시적 실패/대기·원래 baseline·실제 RGB/미제공 상태를 확인하며, 누락 결과가 있으면 기술 검사가 통과해도 `PARTIAL_NO_ANCHOR_BROWSER_QA`다. exit 0을 전체 실험 출력의 존재로 읽지 않는다.

출력은 task 아래 `evaluation/no_anchor_sfm_v1/profiles/PROFILE/{manifest.json,availability.json,receipt.json}`, `resources_PROFILE`, `support_PROFILE`이고 QA는 `no_anchor_sfm_v1/validation/browser_qa/QA_ID`다. 위 예시 profile의 URL은 [최종 부분 profile 예정 주소](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_v1/profiles/main_final_partial_v1/manifest.json&color=height)다. 이 링크는 **이 문서 작성 시 실제 발행·접속 확인한 결과가 아니다.** 기본 선택은 R22000이므로 22k 실패·30k 성공 조합에서는 R30000을 명시적으로 선택해 확인한다. 역사적 보조 8k viewer와 합치거나 바꾸지 않는다.

**부분 support와 성공 지역 그림**

`compare_reference_support.py:154–202, 221–239, 282–302`는 전체 24개 비교 × 6개 임계값의 144행을 유지한다. unavailable 행의 근접 전이 수·비율·recall은 `null`이고 실제 실패 receipt를 연결한다. 데이터가 없는 후보에 배열이 존재하면 stale 상태로 간주해 중단한다. 일부 비교만 가능하면 `PARTIAL_REFERENCE_PROXIMITY_TRANSITIONS`이며, 실제 reference 근접 전이와 미평가 행을 구분한다. 이 값은 temporal validity 또는 obsolete asset 판정이 아니다.

`publish_review.sh`의 partial 모드는 그림을 자동 생성하지 않는다. **P2의 22k와 30k가 모두 완료된 경우에만**, 같은 발행 snapshot의 `figures.py --regions P2`로 기존 CLI를 사용해 P2 그림을 별도 생성할 수 있다. 아래 명령은 새 scoring을 수행하지 않고 저장된 section PNG·support NPZ를 읽는 조건부 안내다. 두 예산의 raw/post section, 두 baseline과의 support NPZ가 모두 있어야 한다.

```bash
geogs_review_figures="figures_${geogs_review_profile}_P2"
test ! -e "$geogs_review_task/evaluation/no_anchor_sfm_v1/$geogs_review_figures"
flock "$geogs_review_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
  docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2 \
  --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --mount "type=bind,src=$geogs_review_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_review_task/evaluation/no_anchor_sfm_v1,dst=/out" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python "/out/publication/$geogs_review_profile/code/figures.py" \
  --task /task --out /out --regions P2 \
  --support-relative "support_$geogs_review_profile" \
  --output-relative "$geogs_review_figures"
```

실행 시에는 기존 증거 보존 방식으로 exact command/image ID/종료 로그를 새 출력 증거에 함께 남겨야 한다. 위 2 CPU/2 GiB 그림 명령은 이 문서 작성 중 실행하거나 용량 검증하지 않았다. 실패하면 부분 출력·로그를 보존하고 완료 그림으로 제시하지 않는다. 생성 후 실제 이미지를 열어 라벨·범위·패널을 확인해야 한다.

한 예산만 성공하면 `figures.py:48–49, 72`가 22k/30k를 모두 요구하므로 기존 CLI로 해당 지역의 합성 그림을 만들 수 없다. 그때의 수정 없는 제공 경로는 성공 예산의 기존 `viewer/P2/SFM_noanchor_D005_Pnative_R30000.mesh_512.{raw,post}.{sections,distance}.png`, 해당 support NPZ와 CSV다. 실패 예산을 역사적 8k나 다른 예산으로 채우지 않는다.

**감사한 소스의 고정 SHA-256**

아래 파일은 모두 `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/` 아래다. 이 값은 코드 읽기 감사의 버전을 특정하며 미래 실행 결과를 인증하지 않는다.

| 파일 | SHA-256 |
|---|---|
| `publish_review.sh` | `b927eb61fb5e5c5f46650a1aa5e36cd1208f7f0353ffd40737e7f821e7f1e725` |
| `summarize_resources.py` | `3c2f4d38d13d14cac226bace635ac6aa19f27b386c06e5ed5d16b94981b808ad` |
| `build_viewer.py` | `b4815a7372eddc8ea3c7b540e9421c6cb8d6efd1d223689e3665550572ab6e62` |
| `run_phase.sh` | `f8854574c23dd86b5e6fe02c75ec7afd6ee961007514bc5dc819e5a97f011d6f` |
| `run_phase.py` | `55b365cb14f0896196c32cdb4342ebbfe20fd9ea5c73f04b9dd861492186fb98` |
| `evaluate.sh` | `5ae36d95f04f70193b87b7a05d32e1e71bdf3790ce8dfee7a0a3cbbbb1351e17` |
| `evaluate.py` | `8442c2dd09813cf45a5f21420de45a2e5cfd8f4783a981fe299f3032ed5fac85` |
| `figures.py` | `dba661858394d2a13ae98812aa2faf7083218e3e342af7ae81640b79b9a49602` |
| `final_retry.py` | `68f05379939690fe56f1162395019246aafc5761a68a64c911309a75ac890774` |
