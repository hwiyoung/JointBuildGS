# SfM refinement memory placement amendment v1

`scientific_verdict: null`

이 변경은 실패한 시도의 입력·과학적 설정·산출물을 수정하지 않고, 별도의 새 runtime과 새 실행 디렉터리를 만드는 저장 위치 변경이다. P1/P2/P3의 새 SfM 시작만 지원한다. 기존 완전 state의 resume 제한은 유지한다.

## 변경 범위

- 원래 `load_depth_set`의 `cv2.resize(..., INTER_LINEAR)`는 CPU 연산이다. 그 코드와 float32 변환은 유지하고, 두 depth dictionary의 tensor device만 CPU로 바꾼다.
- 매 iteration에서 선택된 LoD/DA3 map만 동일 dtype으로 blocking CUDA 복사한다. 첫 iteration에서 실제 복사 후 bytes를 검사한다. None map의 의미도 유지한다.
- 현재 optimizer의 최신 parameter/state를 매 iteration 다시 찾는다. `exp_avg`와 `exp_avg_sq`만 forward/backward 전에 CPU로 옮긴다. Parameter, gradient, step counter, hyperparameter는 이동하거나 수정하지 않는다.
- backward 뒤 기존 CUDA `optimizer.step()` 바로 전에 moments를 원래 parameter device로 되돌린다. 첫 populated cycle의 실제 왕복 bytes와 매 cycle의 step object/value를 검사한다.
- native optimizer step, densification/pruning, 보호 hook 재등록, native save와 complete capture의 순서를 유지한다. 이 구간에서는 moments가 CUDA에 있다. 이전 generation의 tensor나 gradient를 감사 기록에 남겨 메모리를 붙잡지 않는다.
- zero_grad 위치, CUDA Adam/foreach 계산, camera 순서, RNG 호출, loss·schedule·밀도화 설정은 바꾸지 않는다. 중간 checkpoint 추가는 기존 CLI의 capture 목록으로 별도 지정할 수 있으며 이 패치가 기본값을 바꾸지는 않는다.

## 예상 효과와 한계

P1 실패 시 5,845,082 Gaussians 기준 두 Adam moments는 약 2.526 GiB다. 98장×2종의 1400×1013 float32 depth cache를 선택 view 두 장만 CUDA로 옮기면 약 1.025 GiB를 추가 확보한다. 합계 약 3.551 GiB는 당시 크기에 대한 backward headroom 추정이며, 전체 실행의 최대 메모리나 30k 완주 보장은 아니다.

추가 CPU 메모리와 매 iteration 전송 시간이 필요하다. CUDA 계산과 float32 입력값을 보존하지만 전체 Gaussian CUDA trajectory의 bitwise 동일성은 별도 검증 없이 주장하지 않는다. CPU fixture는 작은 Adam 상태의 배치·수명·값 보존을 검증한다. 선택적인 `--device cuda` fixture는 여유 GPU에서만 실행한다. 이 테스트의 PyTorch allocator 상한은 64 MiB이며 CUDA driver context는 그 상한에 포함되지 않는다.

OOM이나 예외로 moments가 CPU 또는 복원 중인 상태에 남으면 lifecycle receipt는 INCOMPLETE다. 그 상태를 완전 CUDA checkpoint나 resume 가능 산출물로 선언하지 않는다. SIGKILL은 atexit 기록을 막을 수 있으므로 외부 runner의 종료 기록이 최종 실패 근거다.

## 계보와 사용

원본 runtime receipt SHA256: `3f2347bc4728c3c1026aef52fda8d6860baf1302996424871a0d791c75a6ae1c`.

원본 `train.py` SHA256: `3a7124bd9a2cb01fd7004bd5dbd9e35151a1ee3045187c0b77b01303561788ab`.

Docker에서 `prepare_runtime.py --source /original --destination /out/source`를 실행한다. `/original`은 기존 `no_anchor_sfm_v1/source`의 읽기 전용 mount다. 이 명령은 학습을 시작하지 않는다.

새 source의 `jbgs_memory_recovery_receipt.json`은 원본 전체 Python hash, 수정 후 전체 Python hash, 부모 receipt hash와 변경 목록을 기록한다. 기존 `jbgs_no_anchor_runtime_receipt.json` bytes는 그대로 보존한다. 학습 args와 기존 science config는 runner가 동일하게 전달한다. 학습 시작 뒤 `model/jbgs_memory_recovery/`에 초기 배치, 선택 depth 복사, 단계별 저장 위치, 최종 lifecycle receipt가 기록된다.
