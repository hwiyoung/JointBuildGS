# main_v2 CUDA OOM 재시도 계획과 보존

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- scientific_verdict: null
- 상태: `P3_D0005_NATIVE_RETRY_PENDING_AFTER_MAIN_QUEUE`
- 기존 18조건 완료 지시 안의 실패 복구이며 조건·학습량 축소가 아니다.

2026-09-11 08:25:53 KST P3 `LC_D0005_Pnative`의 첫 train이 CUDA OOM으로 종료했다. 마지막 JSON trace는14900, 마지막 진행표시는 Anchor 이후6950step(총14950)이다. 정확한 실패 iteration은 exception에 기록되지 않았으므로14950으로 확정하지 않는다. 최종 complete30000은 없다. 실패 receipt의 `iteration:30000`은 요청 목표값이며 완료값이 아니다.

`total_loss.backward()` → `diff_surfel_rasterization`의 CUDA backward에서1.17GiB를 요청했으나 GPU0 여유가1.07GiB였다. 마지막 표시 Gaussian은6,563,992개, 당시 PyTorch allocated21.04GiB, reserved-but-unallocated666.07MiB다. Process636240이22.03GiB를 사용했고 별도 desktop process72937이260MiB를 사용했다. 확인된 직접 원인은 CUDA 메모리 부족이며 host RAM 부족이나 평가 CPU 작업의 인과는 확인되지 않았다. 기록된 driver wall1253.120720초, child peak RSS6,439,198,720bytes를 버리지 않는다.

실패 run의 원 위치 `main_v2/runs/P3/LC_D0005_Pnative/`와 queue 로그는 그대로 보존한다. 후속 queue가 실패 train에 대해 시도하는 render는 worker의 train-PASS 검증에서 거부되며 이것도 원 기록으로 남긴다. 진행 중 release와 나머지 조건은 기존 queue에 따라 계속한다. 현재 queue와 재시도를 겹쳐 추출/학습 격리를 깨지 않는다.

현재 queue 종료 후 GPU1에서 `main_v2/retries/P3_LC_D0005_Pnative_attempt2/`를 새로 생성한다. 원 complete Anchor8k, source/config/binding/gate/helper/image, native allocator `backend:native,max_split_size_mb:128`, CPU8/RAM32GiB/no swap, 8001–30000의22000step을 그대로 사용한다. GPU1은 같은 RTX3090이며 관측된 desktop 점유가 GPU0보다 작다. 이것이 이후 peak까지 충분하다는 보장은 아니므로 새 시도의 실제 성공 여부로 판단한다. 기존 서비스·desktop을 종료하지 않는다.

08:37:23 KST `retry_after_queue_v2.sh P3 LC_D0005_Pnative P3_LC_D0005_Pnative_attempt2`를 실제 대기 상태로 시작했다. 실패 status는 Docker로 확인했고, main queue의 동일 `owner.lock`을 획득한 뒤 종료 receipt·두 GPU idle·host RAM38GiB·disk100GiB 조건을 확인하도록 한다. 재시도 학습은 아직 시작하지 않았다. 요청·driver snapshot·후속 phase 로그는 `main_v2/retry_queue/P3_LC_D0005_Pnative_attempt2/`에 보존한다.

실행 진입점은 동결 `run_phase_v2.sh`의 기존 다섯 번째 output 경로 인수다. 새 학습 성공 뒤 같은 새 경로에서 render/metrics를 실행한다. 원 실패 run을 덮어쓰거나 이동하지 않는다. 두 시도의 wall·실패 비용을 따로 보고하고 유효한 최종18조건에는 첫 성공 시도만 한 번 포함한다. 실패 시도의 중간 trace를 독립 반복으로 간주하지 않는다.

성공 후 평가에는 원 실패 경로와 선택한 retry 경로·각 receipt hash·선택 사유를 적은 별도 불변 run-selection manifest를 연결한다. 평가/그림/trace가 모두 같은 선택을 읽도록 분석 resolver를 검증한다. 이는 분석·산출물 경로 계보의 보완이며 동결 학습 config/source/runtime helper는 변경하지 않는다. 아직 새 성공 결과가 없으므로 현재 모델 성공은10/18개, 실패1개, 진행1개다.

만약 같은 GPU1 재시도도 OOM이면 해당 실패를 보존하고 자원/실행 명세의 별도 revision을 검토한다. 해상도·학습 step·Gaussian 정책을 숨겨 줄이거나 실패를 참조 부재로 바꾸지 않는다. 과학적 판정은 null로 유지한다.

## 분석 선택의 검증 — 2026-09-11 08:56 KST

`run_selection_v2.py`는 전체18개 identity, 세 phase의 PASS/receipt hash, config/input binding/runtime identity를 검사한다. Retry는 원 실패부터 선택 직전까지 모든 시도의 순서와 OOM log hash를 요구한다. 같은 command/environment/Anchor/source/driver/시작·종료 iteration인지 확인하며, 지표를 이용한 시도 선택은 금지한다. 원 run·실패를 이동하지 않는다. 평가 receipt에 선택 경로와 세 phase hash를 복사하고, 그림/독립 그림 QA는 그 receipt에 결박된 경로를 읽는다. 이후 manifest가 달라져도 과거 그림의 원본 경로를 바꾸지 않는다.

Trace launcher의 `--selection`은 먼저 Docker에서 같은 검증기를 실행한다. 검증 container에는 config/binding/선택문서와 각 시도의 phase receipt/log만 읽기 전용으로 제공한다. 분석 container에는 선택된 trace/receipt/invocation만 기존 논리 경로에 제공한다. 모델·이미지·GT payload를 마운트하지 않는다. 실패 비용은 별도 원 receipt에서 보고한다.

새 테스트14개와 기존 전체 테스트를 포함한138개가 skip 없이 PASS했다. 첫 전체 호출의 tmpfs 실행 오류는 [issue](ISSUES_ko_v2.md)에 보존했다. 검증 receipt는 `main_v2/analysis_revisions/run_selection_v2_1/validation_retry_exec_tmp/receipt.json`이다. 같은 첫6개 평가에서 재생성한18개 PNG는 이전 결과와 byte hash가 모두 같았고, v2.2 독립 원본 픽셀·PSNR·단면 검증6개도 PASS했다. 새 그림은 `main_v2/figures/attempt_20260910T235325_550691Z/`, QA는 `main_v2/figures_review/attempt_20260910T235520_652224Z/`다. 당시 원 trace 분석도 PASS10/FAIL1/PARTIAL1/NOT_STARTED6을 정확히 구분했다.

`run_selection_v2.json`은 아직 생성하지 않았다. 재시도까지 모든18개가 성공한 후 Docker에서 `run_selection_v2.py build --task /task/main_v2 --config /task/contracts/main_v2/experiment_v2.json --binding /task/contracts/main_v2/input_binding.json --selection /task/main_v2/run_selection_v2.json --retry P3/LC_D0005_Pnative=retries/P3_LC_D0005_Pnative_attempt2`로 검증 후 배타 생성한다. 이미 존재하는 선택문서는 덮어쓰지 않는다. 최종 evaluation/trace에 이 경로를 명시하고, 중간 평가의 기본 원 run 조회는 그대로 보존한다. 실제 retry 경로를 이용한 전체18개 분석 검증은 성공 후 수행해야 한다.

`run_attempt_costs_v2.sh`는 같은 전체18개 선택문서와 원 실패 receipt/log/GPU 표본만 읽어 phase 비용을 별도 집계한다. 성공한 학습18개, 실패 학습, 실패 뒤 거부된 render 비용을 구분하며 완료/실패의 driver wall·child peak RSS를 공개한다. 병렬 wall 합, 최초–최종 phase 경과, phase 구간 합집합은 서로 다른 값이다. 5초 간격 GPU 표본은 desktop을 포함한 장치 전체 관측 peak이며 프로세스의 정확한 peak로 부르지 않는다. 준비 probe·CPU 평가·과거 G/Anchor 생산 비용은별도다.

시간 중첩·결측/비유한 GPU 표본 등5개 테스트와 합성 전체18개+실패1개/55phase 비용 집계가 PASS했다. 합성 자료에서 wall 합550초와 실제 구간 합집합10초를 구분했고, 동일 manifest 재생성 거부도 확인했다. `main_v2/analysis_revisions/attempt_costs_v2_1/`의 이 검증은 실험 측정이 아니다. 실제 전체 비용 집계는 모델18개 성공 후 남아 있다. 첫 단위 호출의 파일 핸들 ResourceWarning은 `with`로 수정하고 해당 경고를 error로 처리한 재검증에서 통과했다.
