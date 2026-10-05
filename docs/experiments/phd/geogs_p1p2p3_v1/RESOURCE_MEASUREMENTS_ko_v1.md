# 최종 자원 표의 측정 범위

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

앞부분은 최종 `evaluation/summarize.py` 실행 전에 보완한 보고 메타데이터의 변경·검증 기록이다. 기존 숫자 필드·계산·행 구성·조건·원 영수증을 유지하며, `cost_interpretation`의 `raw child-phase wall time`을 실제 driver clock 구간으로 교정했다. 학습/추출 실행기·기하/렌더 지표·사례 선택·동결 계약을 변경하지 않았다. 문서 끝에는 2026-09-08에 실제 닫힌 영수증에서 집계한 주18개 실행 시간을 별도로 추가했다.

## 표와 정의 파일의 연결

`evaluation/summary/resource_summary.csv`, `supplemental_repeat/resource_summary.csv`, `extraction_attempt_resources.csv`의 각 자원 행에 `resource_measurement_scope`를 추가한다. 원 필드명은 그대로이며 같은 열의 의미는 scope로 구분한다.

정의는 `evaluation/summary/resource_measurement_definitions.json`에 기록한다. summary receipt의 `resource_measurement_definitions_path`가 이 파일을 가리키며, 기존 `summary_files` 목록에도 SHA256·bytes가 포함된다. 기존 finalizer/case exporter가 이 목록을 검증하므로 별도의 해시 예외가 없다. 새 JSON에는 `scientific_verdict: null`, 시간 scope 간 합산으로 전체 파이프라인 비용을 만들지 않는 규칙, 메모리 peak의 비가산성과 phase/variant 중복 합산 금지가 들어 있다.

| scope | 시간 | 기존 `child_peak_rss_bytes` 열 |
|---|---|---|
| `regional_driver_phase_v1` | 일반 train/render/metrics 및 legacy auxiliary의 driver clock | `RUSAGE_CHILDREN`: 종료·회수된 자식 중 가장 큰 RSS |
| `resource_v3_auxiliary_phase_v1` | 추출 잠금 획득 뒤 모든 variant 준비·대기·실행·검증·producer hash를 포함한 driver 구간 | 각 renderer PID의 `wait4` RSS 중 최댓값 |
| `training_process_trace_v1` | 계측 모듈 import부터 마지막 trace까지의 process 누적 시간 | 학습 프로세스 자체 `RUSAGE_SELF`의 기록된 peak |
| `shared_anchor_trace_prefix_v1` | 모듈 import부터 step8000 trace까지; 해당 complete-state 저장 전 | 이 행에 새 RSS 수치를 만들지 않음 |
| `failed_anchor_source_phase_v1` | 원 실패 driver 단계 전체; 8000 이후 실패한 refinement를 포함할 수 있음 | 이 행에 새 RSS 수치를 만들지 않음 |
| `resource_v3_auxiliary_variant_v1` | 해당 renderer의 launch·실행·주기적 관측·종료 감시 구간 | 지정 renderer PID에서 회수한 `wait4` RSS |

일반 단계의 `RUSAGE_CHILDREN` 값에는 clock 시작 전 allocator 검사 자식과 실행 중 `nvidia-smi` 자식도 포함될 수 있다. 이는 동시 process-tree RSS 합계가 아니며 parent driver의 종료 후 Open3D 검증 RSS를 포함하지 않는다. Linux의 `getrusage(2)` 문서와 `run_regional_phase.py:47–48,179–182,249`를 대조했다. 같은 열을 쓰는 training trace의 `RUSAGE_SELF`, resource_v3의 지정 PID `wait4` 값과 구분한다.

## 시간과 메모리의 경계

일반 단계 wall은 `run_regional_phase.py:150–250` 구간이다. invocation 기록·입력 manifest SHA·native 실행·5초 sleep을 포함한 종료 감시·필수 산출물 검증/SHA를 포함한다. allocator 검사, 봉인 입력 전체 파일과 소스 SHA, 초기 snapshot/anchor 검사, 추출 잠금 대기는 clock 이전이다. `raw_phase_wall_seconds`는 같은 값의 별칭이며 추가 시간으로 더하지 않는다.

resource_v3 전체 auxiliary wall은 `run_auxiliary_resource_v3.py:224–251`이다. 개별 variant의 PLY 복사·SHA·headroom 대기·실행·종료 후 검증을 포함한다. 반면 variant wall은 `:87–107`의 구간이며, 복사/SHA·headroom 대기·invocation 기록과 종료 후 표면 검증/출력 SHA는 제외한다. GPU 조회와2초 sleep에 따른 종료 감시 간격은 포함한다. invocation의 `started_unix`와 receipt의 `finished_unix`를 빼면 이 variant wall과 다른 구간이 된다. 기존 `included_within_auxiliary_phase_cost=True`, `additive_to_phase_totals=False`는 유지한다.

training trace의 CUDA allocated/reserved 필드는 마지막 trace까지 관측된 학습 프로세스의 PyTorch peak counter다. 실제 reset 이력을 새로 추정하거나 무조건 process-lifetime 전체 정점으로 단정하지 않는다. 해당 시점 이후 complete-state capture/save에서 발생한 peak는 이 값으로 보장하지 않는다. 원 trace 숫자·시간·시작0/8000 계보는 그대로다.

`nvidia-smi --query-gpu=...memory.used,utilization.gpu`는 UUID별 장치 전체 표본이다. 다른 장치 사용자도 포함할 수 있으며 native PID/컨테이너 전용 사용량이나 PyTorch allocator peak가 아니다. 일반 단계는5초, resource_v3 variant는2초 sleep에 조회·loop 시간이 더해진 주기로 관측한다. **최종 지역 summary는 이 GPU CSV를 읽지 않는다.** 따라서 새 정의는 이를 raw device 관측 경로로 설명할 뿐, GPU CSV를 최종 표에 새로 읽거나 장치 peak를 계산했다고 표시하지 않는다.

variant의 `sampled_peak_memory_current_bytes`는 before·주기적 표본·after에서 관측한 auxiliary 컨테이너 전체 cgroup `memory.current`의 최댓값이다. 연속 최대값·native RSS·VRAM이 아니다. after 표본은 이번 variant의 종료 후 Open3D 검증/출력 SHA 전에 기록된다. cgroup `memory.max`는 호스트 메모리 cap이며 CUDA cap이 아니다.

raw receipt/trace의 `memory.peak`는 같은 auxiliary 컨테이너의 과거 variant·준비·검증을 포함해 해당 관측 시점까지 누적된 정점이다. before/after 차이를 해당 variant의 peak로 해석하지 않는다. 현재 variant의 종료 후 검증 정점은 그 variant trace에 없으며 다음 관측의 누적 peak에 반영될 수 있다. 누적 peak와 host MemAvailable 표본 최소는 기존 producer receipt/trace에 있고 이번 variant CSV에 새 숫자로 복사하지 않는다. `cgroup_oom_kill_delta`는 같은 variant의 before/after counter 차이를 유지한다.

## 보존과 합성 검증

수정 전 source는 외부 task의 `runtime/resource_measurement_review_v1/attempt.oQnJ8K/before/`에 보존했다. 같은 attempt의 `source/`는 실제 검증에 사용한 수정 후 코드·필요한 테스트·설정 사본이다. `validation_config.json`, `validate.py`, `run_validation.sh`, `command.sh`, stdout/stderr, `tests.log`, `exit_code.txt`와 `validation_receipt.json`을 함께 보존한다. 재검증은 기존 결과를 덮어쓰지 않고 이 입력 사본과 검증 script/config를 새 attempt로 복사한 뒤 실행한다.

고정 Docker image `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, CPU2·RAM4GiB·network none·GPU 없음으로 **9/9 PASS, 실패/error/skip 모두0**, Python3.10.20, 테스트1.120508초를 기록했다. 실제 task·UAS·지역 품질·모델·GPU/native trace를 마운트하지 않았다.

- 새 메타데이터 helper/열/정의 JSON 출력/receipt 경로와 허용한 설명 문자열만 제거하면, 수정 전후 **전체 summary AST가 동일**하다. 계산·분기·선택·원 출력 행 로직의 동일성을 확인했다.
- 일반 start0/8000, legacy/v3 auxiliary, 별도 반복, shared anchor/실패 비용의 실제 resource helper를 합성 영수증/trace로 호출하여 원 필드와 숫자·행을 대조했다.
- 기존 세 지역 summary 진입점 fixture를 수정 전후 실행했다.26개 CSV의 원 행·필드와 viewer manifest를 대조했고, 선택 OOM과 반복을 포함한48개 extraction 자원 행의 수치·비가산성을 유지했다. 이 기존 통합 fixture의 phase resource helper는 빈 목록 mock이므로, phase/trace의 실제 helper 검증은 앞의 별도 검사로 수행했다.
- 새 정의 파일의 SHA/bytes와 summary receipt 경로 연결을 확인했다. 기존 정의 없는 snapshot과 비교한 합성 CSV·정의 JSON·receipt는 `synthetic_evidence/`에 남겼다.
- 다른 evaluation Python 파일과 runtime 계측 source 및 동결 설정17건의 SHA가 보존 사본과 일치했다. source/schema 검토에서 추가 자원 열이나 unique summary file을 거부하는 downstream 고정 guard는 발견하지 못했다. `git diff --check`와 검증 wrapper 구문 검사도 통과했다.

| 검증 식별자 | SHA256 |
|---|---|
| 수정 전 `summarize.py` | `0d7d71bef3bdbdfb8e30f7e9d7ac2ff7d56e51aa7eb1503495dba27079a7e48b` |
| 수정 후 `summarize.py` | `ef536619c08d1a6092e749ea5ac89e4de607d407fbb3315a438a0ee63b52c2f1` |
| `validation_receipt.json` | `869be3fa81d32cc08865731fb7450f81908010f453d754f9d2ed5d2f958430c7` |
| 합성 정의 JSON | `d7ad95a1f5d8ad12a0a4830a012b13828e03a7605df4315449843c1f1a6cd4f7` |

이 검증 당시에는 all21 봉인을 전제했다. 현재 실행 범위는 [평가 시작 조건 변경](EVALUATION_COMPLETION_AMENDMENT_ko_v2.md)에 따라 주18개 봉인과 보조 반복 불완료의 명시적 기록으로 바뀌었다. 실제 summary 출력은 해당 자동 finalizer가 생성하며, 위 합성 검증을 실제 지역 메모리·시간 분석이나 최종 실행 완료로 취급하지 않는다.

## 실제 주18개 실행 시간 — 2026-09-08 20:47 KST 검토

아래는 완료된 `train`, `render`, `metrics`, resource-v3 `auxiliary`의 **driver 측정 구간 합계**다. 지역마다6조건이며 단위는 초다. 각 단계의 시간 경계는 앞의 정의를 따른다. 두 GPU에서 병행했으므로 이 합계는 실제 달력 경과 시간이나 GPU busy hours가 아니다.

| 지역 | 학습 | 렌더·필수1024 추출 | 기존 영상 지표 | 보조 추출 driver | 합계 |
|---|---:|---:|---:|---:|---:|
| P1 | 35,787.663414 | 1,510.645128 | 176.158612 | 1,103.168540 | 38,577.635694 |
| P2 | 27,611.786609 | 795.566228 | 120.924455 | 750.078887 | 29,278.356180 |
| P3 | 38,116.392736 | 1,976.659130 | 278.076031 | 1,312.778830 | 41,683.906727 |
| 주18개 합계 | 101,515.842759 | 4,282.870486 | 575.159098 | 3,166.026257 | 109,539.898601 |

전체 합계는30.427750시간이며 이 중 학습은28.198845시간이다. 보조 추출42개 variant의 renderer 실행·종료 감시 구간 합계2,817.582753초는 보조 추출 driver 안에 포함되어 **다시 더하지 않는다**. 그 안에서 선택 추출의 OOM21건은1,491.986664초(24.866444분)다. 공통 anchor1024 세 건462.371133초와 최종2048 열여덟 건1,029.615531초로 나뉜다. 이 OOM은32GiB 컨테이너 호스트 메모리 한계의 기록이며 CUDA 학습 실패와 구분한다.

주18개 밖의 보조 native 반복 학습은 P1 991.796377초, P2 20.131426초에 실패했다. 합계1,011.927804초(16.865463분)는 위 주18개 표에 포함되지 않는다. 표와 이 두 실패만 더하면110,551.826404초(30.708841시간)다. P3 보조 반복은 미실행이므로 실행 시간을 만들어 넣지 않는다.

이 집계에는 P1 최초 anchor를 남긴 이전 실패 실행, 과거 보조 추출 실패·메모리 probe, 입력·환경 준비, 각 driver clock 이전 검사·queue 대기, 이후 UAS 기하 평가·독립 렌더 평가·viewer 검증이 포함되지 않는다. 따라서 전체 실험 비용이나 지연 전체의 원인별 합계로 확대하지 않는다. 메모리 정점도 시간처럼 합산하지 않는다.

근거는 외부 task 기준 다음 닫힌 JSON116개(총1,059,483 bytes)다.

- `runs_allocator_v2/{P1,P2,P3}/{조건}/{train,render,metrics}_receipt.json`:54개
- `extraction_resource_v3/primary/{지역}/{조건}/auxiliary_receipt.json`:18개
- 같은 경로의 `auxiliary/{variant}/receipt.json`:42개
- `native_repeat_allocator_v2/{P1,P2}/D005_Pnative/train_receipt.json`:2개

별도 reviewer가 이 작은 JSON만 개별 read-only mount한 Docker(CPU1·RAM2GiB·network none·GPU 없음)에서 집계했다.116개 모두 읽기 전후 SHA/bytes가 같고, aggregate→variant SHA 연결42개가 일치했다. 기존 영수증과 큰 모델·참조·품질 데이터는 변경하지 않았다. 위 집계는 닫힌 생산 영수증의 수동 검토이며, 최종 기계 판독 표는 `evaluation/summary/resource_summary.csv`, `extraction_attempt_resources.csv`, `supplemental_repeat/failed_attempt_resources.csv`와 scope 정의 파일을 사용한다.
