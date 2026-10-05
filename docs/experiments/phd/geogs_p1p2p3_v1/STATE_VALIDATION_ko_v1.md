# 같은 anchor의 검증과 수치 궤적 차이

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

**실제로 학습된 동일 checkpoint의 복원 직후 상태와 렌더 배열은 정확히 일치했다. 독립 실행이나 이후100회 학습의 전체 궤적은 정확히 일치하지 않았다.** 이 두 결과를 구분한다.

원본 코드는 기존 확보 경로와 새 pristine clone에 보존했다. 별도 `GeoGS-state-camera-v1`의 학습에는 상태 기록/복원과 명시적 보호 해제만 추가했으며, 지역 카메라는 원 K를 보존하는 opt-in adapter를 사용한다. 원 예제에는 이 adapter가 적용되지 않는다. 모델·native CUDA renderer·optimizer·손실 공식은 유지한다.

## 실제 checkpoint 검사

공식 예제에서8,000회 optimizer·densification·보호 등록이 끝난 상태를 저장했다. 실제 checkpoint는 Gaussian 2,051,247개와 보호 대상103,783개를 포함한다.

`native_example_parity_v1/restore_probe_retry_v2/restore_probe.json`의 상태는 `EXACT_PRESTEP_RESTORE_AND_HOOK_PARITY`다. 새로운 프로세스에서 production `restore_state`를 호출하고 optimizer를 한 번도 실행하기 전에 다음을 대조했다.

- 모델 전체 tensor, Adam 상태, radii/gradient accumulator, SH/lr scale.
- frozen/completed/building mask, controller와 단계 상태.
- Python/NumPy/Torch CPU·CUDA RNG, 학습/평가 카메라 순서와 잔여 stack.
- 실제 설치된 위치·회전·크기 hook에 단위 gradient를 흘렸을 때 보호점의0.01배 감쇠.
- 같은 checkpoint와 그 직후 저장한 PLY의 렌더 관련 파라미터 및 두 실제 평가 카메라에서 RGB·surface depth·alpha·normal 배열.

위 optimizer 실행 전 검사항목은 모두 exact 비교를 통과했고 검사 자체도 RNG를 소모하지 않았다. 이어 공식8,001회 한 step을 실행한 `one_step_probe.json`은 `PASS_ONE_NATIVE_STEP`이다. 예상 회차·카메라/잔여 stack/Python RNG가 같고 각 Adam step counter가 정확히1 증가했으며 Gaussian/보호 개수를 유지하고 loss·모델이 유한했다. **이는 한-step 실행 건전성 검사다. 갱신 후 모델·Adam tensor 전체를 독립 연속 실행의 같은 step과 대조하지 않으므로 한-step bitwise parity나 optimizer 모멘트의 동일성을 증명하지 않는다.**

검사기 실패도 보존했다. 첫 시도는 NumPy uint32 RNG를 torch2.1.2 tensor로 바꾸는 comparator에서 실패했고, 다음 시도는 성공한8,001 step 뒤 보고 변수를 `loss`로 잘못 참조했다. NumPy의 원 dtype 비교와 실제 `total_loss` 보고로 검사기만 고친 후 새 디렉터리에서 재검증했다. 원 checkpoint와 학습 source는 바꾸지 않았다.

## 일치하지 않은 비교

| 비교 | 관찰 | 해석 한계 |
|---|---|---|
| 원본과 상태 기록 추가본을 seed0으로 각각 처음부터 실행 |8,000회 경계 전 Gaussian 수가 약0.35% 다름 | 독립 전체 궤적의 bitwise 동일성은 입증되지 않음 |
| 완전 상태8,000에서 원설정으로100회 재시작 |8,100회 약198만 Gaussian 중23개 차이. 모델/Adam·mask shape와 loss/controller 일부 항목 차이 | 같은 출발 상태라도 이후 densification까지 포함한 수치 궤적은 exact하지 않음 |
| 같은100회 비교의 RNG·카메라 순서·잔여 stack |exact | 난수/카메라 상태 누락으로 설명되는 재시작 결함은 해당 검사에서 발견되지 않음 |

실제 native CUDA gradient 반복 검사에서도 작은 실행 간 차이를 관찰했다. 그러나 독립 장기 궤적 차이 전부의 원인을 그것만으로 확정하지는 않는다. 원 비교 JSON과 구조 차이를 보존하며 사후 수치 허용오차로 exact 판정을 바꾸지 않는다.

따라서 이번6조건은 **정확히 검증된 같은 출발 상태에서의 단일 seed 기술 진단**으로 진행한다. 아주 작은 조건 차이를 수치 실행 변동과 분리한 안정적인 효과라고 주장하지 않는다. 장기 native 반복 및 추가 seed는 작은 차이의 후속 검증에 필요하다. 반복 재판단의 유용성이나 우위도 이번 실험으로 추론하지 않는다.

각 지역에서도 실제8,000 anchor에 동일한 복원/hook/PLY-render/한-step 검사를 실시하고100회 비교를 별도 저장한다. `EXACT_COMMON_ANCHOR_VERIFIED`는 이 출발 상태 gate이며 ‘학습 궤적 전체가 exact’라는 뜻이 아니다. RNG·카메라/설정·source 불일치나 복원 실패가 있으면 분기 실행을 막는다.

## 검증 범위의 source/metadata 재확인 — 2026-09-08

`probe_actual_restore.py`의 [복원 직후 비교](../../../../scripts/phd/geogs_p1p2p3_v1/runtime/probe_actual_restore.py:30)는 optimizer step 전에 checkpoint의 상태와 복원 상태를 대조하고, 보호 hook·같은 checkpoint의 PLY 파라미터/렌더·검사 중 RNG 보존을 확인한다. [한-step 검사](../../../../scripts/phd/geogs_p1p2p3_v1/runtime/probe_actual_restore.py:109)는 회차, 카메라/잔여 stack/Python RNG, Adam step counter, 모델/loss 유한성과 Gaussian/보호 개수만 판정한다. 이 함수에는 갱신된 tensor 전체의 연속/재개 쌍 비교가 없다. [gate의 해석](../../../../scripts/phd/geogs_p1p2p3_v1/seal_anchor_gate.py:80)도 같은 제한을 명시한다.

현행 `parity_allocator_v2/<지역>/anchor_gate.json`과 gate가 결박한 `restore_probe/restore_probe.json`, `restore_probe/one_step_probe.json`, `continuation_comparison.json`을 개별 읽기 전용 파일로 Docker에 연결해 상태·비교 boolean·개수·SHA만 확인했다. 세 gate 모두 `EXACT_COMMON_ANCHOR_VERIFIED`이며, 각 지역의 세 검증 파일 SHA가 gate 선언과 일치했다(9/9). 복원 직후 상태·PLY/렌더·RNG 비교와 hook 검사는 모두 exact이고, 한-step은8,001회에서 명시된 실행 조건을 통과했다. 세 gate의 `independent_trajectory_parity_claim`은 모두 false다.

| 지역 | gate SHA256 | 복원 직후 상태 불일치 | 한-step 상태 |100회 continuation |
|---|---|---:|---|---|
| P1 | `4af6cd7db3456fe155080dfa20b70d9f906b45103adaf7468d128ef0686a657a` |0 | `PASS_ONE_NATIVE_STEP` | exact=false, 불일치121항목 |
| P2 | `0f2559c2637cd394cba36dd08dbf1bf7ba29a948acbf1a82c868b1917feecc0a` |0 | `PASS_ONE_NATIVE_STEP` | exact=false, 불일치120항목 |
| P3 | `9a496765ac2519fc66ef69b28674a0598f90e010544e51ce824e1a031b3996bc` |0 | `PASS_ONE_NATIVE_STEP` | exact=false, 불일치119항목 |

모든 restore receipt의 검사 소스 SHA는 현재 `probe_actual_restore.py`의 `4691701596fb04f7447177a35d628e3795be4ec57f3efb2822cef0b8331d2e26`, 모든 gate의 소스 SHA는 현재 `seal_anchor_gate.py`의 `a2c10d5200bfb8b5e1f38965eef456df812bdfae67596b8aff83a10cfb8644d2`와 일치한다. 이 재확인은 기존 검증의 범위를 읽은 것이며 모델/checkpoint·메시·렌더·UAS·지역 점수 또는 loss 값을 열어 다시 비교한 작업이 아니다. 기존 영수증·실행 소스·조건과 historical `EXECUTION_STATUS` 문서는 변경하지 않았다.

## 실행 경로 gate

추가적인 원 예제8,000 PLY의 공식 `render.py → GaussianExtractor.extract_mesh_bounded → post_process_mesh → metrics.py` 실행은 성공했다. Raw7,873,043개 / post6,087,173개 삼각형이 유한·양의 면적 표면으로 확인됐다. 이 PLY는 원본의 경계 전 artifact이므로 지역의 공유 anchor로 사용하지 않는다.

이 경로 검사를 먼저 마친 뒤 공식 예제30,000회 실행과 P1 바닐라를 병렬 진행한다. 최종 예제 학습/렌더/평가는 계속 완료하며, 예제 수치를 세 지역 성능으로 전용하지 않는다. 조건·입력·학습량 변경은 없다.

## 지역 gate 후속 기록 — P2, 2026-09-08 08:36 KST

`parity_allocator_v2/P2/anchor_gate.json`은 `EXACT_COMMON_ANCHOR_VERIFIED`다. P2의 새 allocator0→8,000회 anchor checkpoint SHA256은 `91bc9ad74b115c37d4ae35ec4eb197832e730be165d36f52ebe4bb291f1ebcfd`이며, 경계 trace의 Gaussian 수는1,625,820개, 보호 대상은114,521개다. 복원 직후 상태·보호 hook·같은 anchor PLY/실제 렌더와 native 한-step 검사를 통과한 뒤 `D0005_Pnative` 분기를 시작했다.

P2의100회 continuation 비교는 `continuation_exact: false`, 불일치 항목120개다. 이후 CUDA RNG 배열은 일치하지만 이것이 모델 전체 궤적의 동일성을 뜻하지 않는다. 원인은 이 비교만으로 확정하지 않는다. 한-step 검사는 카메라 순서·Adam step 증가·유한 모델/loss·개수를 확인하며, 갱신 후 모든 tensor byte의 동일성까지 증명하는 검사는 아니다.

현재 gate 정책은 `INITIAL_RESTORE_STRICT_LATER_CUDA_RNG_DIAGNOSTIC_v2`다. **복원 직후** RNG·카메라/설정/source·모델/optimizer·보호 상태는 엄격히 확인한다. 이후100회 CUDA RNG 값의 변화는 별도 진단이며 출발 상태 gate와 혼합하지 않는다. 실제 차이와 검사 hash를 원 JSON에 그대로 남긴다.

장기 바닐라 반복은 이제 [사전 등록 계약](../../../../configs/phd/geogs_p1p2p3_v1/supplemental_repeat_v1.json)에 따라 각 지역 한 번씩, 주18개 완료 후 실행할 예정이다. 이 시점에는 아직 반복 결과가 없으며, 같은 seed/anchor의 두 실행은 다중 seed 안정성이나 잡음 상한을 제공하지 않는다.

## 공식 예제의 최종 경로 완료 확인

위 실행 경로 gate 절의 예제 진행 중 상태는 과거 시점이다. `native_example_retry_compat_v1/output/{train,render,metrics}_receipt.json`을 다시 확인한 결과 세 단계 모두 native/validated exit0, `PASS`다. 원본 `train.py` SHA256은 `4c09f6a117d7f4a13e3bd3c5d9eb49b1830e428950a53c0f86be4001637c7a10`이며,30,000회 PLY와8,000/8,100/30,000회 원 checkpoint가 실제로 생성됐다. native 학습3,472.5297초, 최종 렌더/표면 추출64.2634초, metrics15.0954초다.

공식 예제의 원본 학습→최종 표면→렌더/metric 산출 경로가 실제 실행됐다는 근거다. 예제의 제공 DA3 membership과 원 FoV-only 카메라 한계는 그대로 남으며, 저자 논문 성능 수치의 동일 재현이나 P1/P2/P3 성능 결과를 뜻하지 않는다. 지역에는 동일하게 적용한 ALS 입력 변환과 명시적 K adapter가 있어 별도 조건으로 설명한다.

## 지역 gate 후속 기록 — P3, 2026-09-08 12:51 KST

`parity_allocator_v2/P3/anchor_gate.json`도 `EXACT_COMMON_ANCHOR_VERIFIED`로 완료됐다. 새 allocator0→8,000회 checkpoint SHA256은 `3b0de04d99435e36d05ffca49951976352bd663192cce14e59f2bddb58bdf567`이다. 당시 Gaussian은1,235,876개, 보호 대상은226,262개였다. 이 공통 anchor의 복원 직후 모델/optimizer·보호 hook·RNG·카메라 상태, 같은 anchor PLY/실제 렌더 및 한 native step 검사를 통과한 뒤 `D0005_Pnative` 분기를 시작했다.

P3의100회 continuation은 `continuation_exact: false`, 불일치 항목119개다. 이후 CUDA RNG 배열은 일치했지만 모델 전체 궤적의 exact parity나 차이의 원인이 확정된 것은 아니다. 같은 `INITIAL_RESTORE_STRICT_LATER_CUDA_RNG_DIAGNOSTIC_v2` 정책을 유지한다. 한-step 검사는 모든 갱신 tensor의 byte 동일성까지 증명하지 않는다.

gate에 결박된 검증 파일 SHA256은 restore `b69f5fbacd412d4f4ebbaff9d235e629be07123a6964cb80a92ca9a94839ca93`, one-step `7c84c6923846209fd386ba310d6cc2ee3cd16e34f098c09a20b8cc8c6673089d`, continuation `2cdf581209677525310667d3445b3ac15426aa2848d919fafeaf48bb7e6075da`다. 세 지역 모두 출발 상태 gate를 통과했지만 P3 최종 결과와 장기 native 반복·UAS 평가는 이 시점에 아직이다.
