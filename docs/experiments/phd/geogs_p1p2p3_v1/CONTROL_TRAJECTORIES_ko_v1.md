# GeoGS 실현 제어 궤적 보고

- 날짜: 2026-09-08
- 작업: `PHD-GEOGS-P1P2P3-v1`
- 상태: `CONTROL_CURVES_AND_TABLES_READY` — 주18개 실제 실행 기록 검토 완료
- `scientific_verdict: null`

완료 후보 봉인 뒤 **실제로 기록된 prior/DA3 가중치와 Gaussian 수의 궤적**을 출력하는 별도 도구다. [평가 완료 범위 변경](EVALUATION_COMPLETION_AMENDMENT_ko_v2.md)에 따라 실제 주18개를 분석했고 보조 반복은 실패·미실행 상태로 남긴다. 원 학습·renderer·평가·제어 설정을 변경하지 않았다. 합성 준비 당시에는 원 source와 합성 자료만 사용했으며, 아래 실제 실행에서는 봉인된 trace와 학습 영수증만 읽었다.

## 입력 봉인이 가능한 근거

`evaluation/seal_candidates.py:435`는 각 완료 실행의 `model/jbgs_trace.jsonl`을 직접 `bind()`한다. `bind()`는 파일의 SHA256과 byte 수를 전체 candidate seal의 `files` 목록에 저장한다. `train_receipt.json` 역시 같은 seal에 포함된다. 이는 **완료 시점 candidate seal에 직접 기록된 trace 바인딩**이며, 원 학습 receipt의 필수 output validation 목록이 trace까지 검증했다고 주장하는 것은 아니다.

실행은 두 Docker 단계로 나눈다.

1. `contracts/`만 읽기 전용으로 마운트한다. `FinalizationGate.candidate_seal()`로 완료 범위와 필수·선택 추출 상태를 확인하고, 현재18 trace와18 train receipt가 seal 목록에 SHA/bytes와 함께 존재하는지 검사한다. 성공한 `input_gate.json`과 정확한36개 파일의 mount 목록을 만든다. 원 all21 계약의21쌍과 현재 완료 범위의18쌍을 혼용하지 않는다.
2. 그36개 파일만 추가로 읽기 전용 마운트한다. seal·접근 목록의 동일성을 재확인하고 모든 파일의 SHA/bytes를 검증한 뒤 제어 필드를 읽는다. 분석 후 동일 검증을 다시 수행한다. 원 UAS·영상·메시·checkpoint·다른 실행 결과·작업 전체를 마운트하지 않는다.

미봉인 trace는 `UNBOUND_CONTROL_INPUT`으로 중단한다. 새로 읽은 파일을 자기 해시하여 봉인된 것처럼 허용하지 않는다. 이 경우 별도로 검토한 post-seal 바인딩 receipt가 필요하다고 보고하며, 현재 도구에는 이를 자동 우회하는 경로가 없다. 손상·누락·중복 파일이나 변경된 seal도 중단 사유다.

각 train receipt의 `implementation_hashes`가 아래 source와 일치해야 한다. 실제 실행 source가 달라졌는데 같은 trace 의미를 가정하지 않는다.

- `jbgs_state.py`: `7114f78e6f429c9186ce44e81a0c40d18e5087994f99a52d81eeee18ab7fa570`
- 계측·카메라 적용 `train.py`: `08cfab996b144488b1a583bf722b991c627d90136a9031f85f7d33b1cae0c44b`

## 기록된 필드와 기록되지 않은 상태

`jbgs_state.py:168–180`의 `after_step()`에서 다음 필드만 선택해 출력한다. trace 파일에 함께 들어 있는 RGB/prior/DA loss, 사진 이름, 메모리 필드는 분석·그림·제어 CSV에 복사하지 않는다.

| 출력 필드 | 원 trace 또는 의미 |
|---|---|
| `global_iteration` | 원 `iteration` |
| `training_start_iteration` | 정확한 runtime layout/repeat와 train receipt의 0 또는 8000 |
| `iterations_since_execution_start` | global iteration에서 시작 iteration을 뺀 값; optimizer 호출 수라는 주장이 아님 |
| `gaussians`, `protected_gaussians` | 원 `gaussians`, `protected` |
| `prior_weight`, `da3_weight` | 원 `lod_weight`, `da_weight`; 실현 값 그대로 |
| `da_controller_phase` | null; `NOT_RECORDED_IN_PINNED_TRACE` |
| `process_elapsed_seconds` | 원 `elapsed_seconds`; 계측 모듈 초기화 뒤 누적 시간 |
| `elapsed_since_previous_logged_sample_seconds` | 직전 기록과의 시간 차이; 첫 표본은 null |
| `logged_iteration_gap` | 두 기록 사이 iteration 수 |
| `per_step_seconds` | null; step 비용으로 환산하지 않음 |

DA controller phase는 complete-state 항목에는 있지만 이 trace에는 기록되지 않는다. 일정한 가중치에서 phase를 추정하거나 이를 얻기 위해 checkpoint를 열지 않는다. 원 source는 매 100회 및 지정 capture 회차를 기록하며 이 실행의 capture 8000/8100/30000도 모두 같은 격자에 속한다. 0 시작은 100–30000, 8000 복원 시작은 8100–30000의 정확한 기록 격자를 요구한다. 누락을 보간하거나 이전 실행의 anchor prefix를 붙이지 않는다. 첫 8100 표본을 복원 직후 8000의 상태로 부르지 않는다.

## 시간과 구조 해석

`STARTED = time.monotonic()`은 계측 모듈을 읽을 때 설정된다. 누적 trace 시간에는 해당 프로세스의 초기화/복원, 이전 보고·저장과 기다림이 포함된다. trace 행은 그 회차의 `jbgs_complete` 저장보다 먼저 기록되므로 마지막 timestamp 뒤에 final complete-state 저장 등이 남을 수 있다. 기록 사이의 차이는 보통 100회 동안의 process 구간이며 순수 optimizer 시간·개별 step 시간·전체 파이프라인 시간이 아니다.

별도 `training_driver_phase_wall_seconds`는 원 train receipt의 `wall_seconds`를 그대로 옮긴다. 원 필드 이름과 train receipt 경로/SHA도 함께 보존한다. `run_regional_phase.py:150`의 `start`부터 `:247–250`의 receipt 작성까지이므로 invocation·입력 manifest SHA, native subprocess 실행, 5초 간격 종료 감시, 종료 뒤 필수 output 확인·SHA 계산을 포함한다. 그보다 앞선 준비나 queue 대기까지 포함하는 전체 시간은 아니다. trace 시간과의 차이를 final capture 단독 비용으로 해석하지 않는다.

Gaussian/protected 수는 **학습 전체 context의 수**이고 평가 ROI의 표면 개수·정확도·완전성이 아니다. 보호 수가 일정해도 외관·opacity와 감쇠된 위치 등은 변할 수 있으므로 가시적 구조가 불변이라는 뜻이 아니다. 순 개수의 증감만으로 clone/split/prune 각각의 실행량·원인이나 구조 손상을 단정하지 않는다. 그림의 8000/15000 선은 동결된 anchor/densification 일정의 안내이며 관측한 개별 위상 변경 사건이 아니다.

원 DA3 adaptive 규칙의 초기값과 코드가 같아도 조건별 loss 이력이 다르면 실제 가중치 궤적이 달라질 수 있다. 이 보고는 그 실현 제어의 기록이다. 가중치 차이가 최종 품질 차이를 단독으로 일으켰다는 인과 판정이나 반복 재판단의 필요성을 자동 도출하지 않는다.

## 실행과 결과 경로

현재 완료 계약과 정확히 결합한 주18개 seal 이후 저장소 루트에서 실행한다. summary 생성 완료를 요구하지 않아 지역 평가와 병행 실행했다. 기존 live orchestrator는 변경하지 않았다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_control_trajectories.sh
```

고정 Docker 이미지 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, CPU 2개·RAM 2 GiB, 네트워크·GPU 없음으로 실행한다. 출력은 외부 작업 루트의 새 `evaluation/control_trajectories_v1/attempt.XXXXXX/`다. 재실행도 새 attempt를 사용하며 기존 결과를 덮어쓰지 않는다.

| 산출물 | 내용 |
|---|---|
| `results/primary_control_samples.csv` | 여섯 조건×세 지역; 현행 실행 시작 계보에 따른 4,120개 표본 |
| `results/supplemental_control_status.json` | 반복 실패·미실행 및 품질 변동 미측정; 완료 반복 표본0개 |
| `results/run_control_summary.csv` | 18개 실행의 시작/끝 기록, 제어·수·서로 다른 두 시간 및 입력 계보 |
| `results/P*_primary_six_conditions.png/.pdf` | 지역별 여섯 조건의 actual trace 곡선 |
| `results/figure_index.json` | 그림별 실제 표본 수·iteration·조건·시작 회차 |
| `results/receipt.json` | 입력 seal·파일·소스·명령·이미지 식별자·결과 파일 SHA/bytes, 의미와 제한 |

각 그림은 prior 전체 궤적/실제 refinement 표본 확대, DA3 가중치, 전체 context Gaussian/protected 수, 누적 process 시간을 포함한다. 모든 조건을 표시하며, 같은 값이 겹치는 선을 별도 값처럼 벌리거나 좋은 실행을 선택하지 않는다. 범례에 각 실행의 0/8000 시작을 적고 반복을 명시한다. 선은 100회 표본을 연결한 안내이며 정확한 weight 변경 시점을 복원한 것이 아니다. 두 시작 방식의 누적 시간 곡선을 동일 학습량의 속도 비교로 읽지 않는다.

시작 계보는 P1 주 native도 기존 anchor에서 8000으로 복원하고, P2/P3 주 native는 0부터 실행하며, 다른 조건과 세 반복은 8000에서 복원하는 현행 layout을 그대로 따른다. 반복은 원 조건의 대체·best run·신뢰구간 산출에 사용하지 않는다.

## 합성 검증

```bash
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_control_synthetic_validation.sh
```

실제 task·trace·UAS가 없는 Docker에서 `tests/phd/geogs_p1p2p3_v1/test_control_trajectories.py`를 실행했다. 원 source AST의 기록 필드/시간/저장 순서, 원 all21 gate에 대한 합성 봉인, 미봉인·변경 trace의 거부, 조건/반복 분리, phase 미추정, 결측·시간 역전 거부, 4,120/660개 합성 표본과 여섯 실제 PNG/PDF 파일 생성을 확인했다. 합성 그림에는 `SYNTHETIC VALIDATION`을 표시한다. 이 검증 당시에는 실제 지역 제어 결과를 생성하거나 읽지 않았다.

최종 검증은 `runtime/control_trajectory_validation_v1/attempt.hovGU5/test_receipt.json`에 기록했다. **17/17 PASS, 실패·error·skip 모두 0**, 8.816초, Python 3.10.20이며 두 shell wrapper의 구문 검사를 포함한다. 같은 attempt의 `synthetic_P2_primary_six_conditions.png`와 `synthetic_P2_native_repeat_diagnostic.png`를 직접 열어 실제 표시·범례의 시작 회차·반복 구분·축·refinement 확대를 확인했다. 이는 합성 표시 검증이며 실제 지역 결과의 표시 검증은 후속 실행에 남아 있다.

검증 당시 Git HEAD는 `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`이며, 이번 추가 파일은 커밋하지 않았다. 정확한 실행 소스/설정 사본과 SHA, Docker 명령, 이미지 ID, stdout/stderr, 종료 코드가 attempt에 남는다. 중간 성공 시험은 같은 validation 디렉터리에 보존하며 중복 시험 수를 합산하지 않는다. `git diff --check`도 통과했다.

- 최종 `control_trajectories.py` SHA256: `9360a73b7a1766324329b6b4da8ca64c2f0c22e9de333c1ca21fa95fc44f1ae3`
- 운영 wrapper SHA256: `401d6e1ebf5837fbb18d73bda49b28780d8044423ae948b5b5d9c815641f559c`

## 실제 실행과 확인된 제어 차이

2026-09-08 21:01:32 KST에 `evaluation/control_trajectories_v1/attempt.M6kKT8`가 exit0으로 완료됐다. 현재 source는 완료 범위 변경을 반영한 `control_trajectories.py` SHA `c3cf22cec42b6134247c9404a67d454666d0591456caa701fc76ec5d13fd6334`다. 실행 source·명령·image ID·접근 목록을 attempt에 보존했다.

- 완료 상태: `CONTROL_CURVES_AND_TABLES_READY`;18개 실행, 주4,120개 표본, 보조0개 표본, 지역 그림3개
- `results/receipt.json` SHA: `20c63986b45c1337b7b33cc19eba70ceba122a0b74bb739cb07d8e1b3e417ca2`
- 별도 reviewer가 결과 파일10개의 SHA/bytes를 다시 확인하고 PNG3개를 실제 표시했다. Root도 위 영수증 SHA와 P3 실제 그림을 확인했다.
- P1은 모두8000 재개(각220표본), P2/P3 native는0 시작(각300표본), 그 외는8000 재개(각220표본)다.

아래 Gaussian 수는30000의 **전체 학습 context** 기록이다. ROI 표면 점 수나 품질 점수가 아니다.

| 조건 | P1 | P2 | P3 |
|---|---:|---:|---:|
| .005 native | 6,033,926 | 4,093,957 | 4,799,188 |
| .0005 native | 5,714,579 | 3,105,715 | 4,858,722 |
| 0 native | 4,769,540 | 3,251,669 | 5,332,800 |
| .005 release | 6,154,774 | 4,049,090 | 5,739,772 |
| .0005 release | 5,641,255 | 2,896,797 | 4,447,762 |
| 0 release | 6,271,653 | 3,237,135 | 5,721,119 |

Native 보호 수는 기록된 refinement 구간에서 P1 236,015개, P2 114,521개, P3 226,262개로 일정하며 release는 모두0개다.18조건 모두 마지막 기록된 순개수 변화는14900이고 이후30000까지 일정하다. 큰 순감소는9000→9100 및12000→12100 표본 사이에 공통으로 관측되지만, 이100회 간격의 순개수만으로 clone/split/prune 개별 원인이나 구조 손상을 판정하지 않는다.

Prior refinement 가중치는 모든 표본에서 선언한 .005/.0005/0과 일치했다. DA3는 다음처럼 기록됐다. 회차는 **변경을 처음 관측한 표본**이며 정확한 사건 시각이 아니다.

| 지역 | .05에서 달라진 조건·기록 | 나머지 조건 |
|---|---|---|
| P1 | 0 native:9900에서.0475; .0005 release:9800에서.0475 | refinement 기록에서.05 유지 |
| P2 | .005 release:11600에서.0475 | refinement 기록에서.05 유지 |
| P3 | .005 native:9700에서.0475→10100에서.045125→10500에서.04286875; .0005 native 및0 release:10300에서.0475; .005/.0005 release:9700에서.0475 | 0 native는.05 유지 |

P1 원설정 native와 .0005 native의220개 refinement 기록에서 DA3 가중치는 모두.05로 같았다. 따라서 [실제 P1 검토](P1_REVIEW_ko_v1.md)의 ROI 평균 개선과 가까운 표면 F1 하락을 이 두 조건 사이의 **관측된 DA3 가중치 변화** 때문이라고 설명할 수 없다. 반면 일부 다른 대비는 DA3 궤적도 다르므로 제어 변경이 만든 전체 실행 차이로 해석한다.100회 사이의 기록되지 않은 상태나 controller phase를 새로 추정하지 않는다.

보호 수 고정과 실제 기하 변화·영상 세부 손실이 함께 나타났으며, 보호 수 고정은 가시 구조 불변의 보증이 아니다. 예를 들어 P1 깊이0의 release는 native보다 Gaussian 수가 많지만0.5m 표면 F1은 낮았다. 개수 증가도 표면/렌더 개선을 보증하지 않는다. 이 기록으로 변화의 세부 기작·반복 변동·새 판단 알고리즘의 효과를 확정하지 않는다.

실제 그림은 위 attempt의 `results/P1_primary_six_conditions.png`, `P2_primary_six_conditions.png`, `P3_primary_six_conditions.png`와 같은 이름 PDF다. 원4,120행은 `primary_control_samples.csv`, 실행별 시작·끝·시간 범위는 `run_control_summary.csv`에 있다. 보조 반복의 실패·미실행은 `supplemental_control_status.json`으로 남기며 완료되지 않은 반복 곡선은 생성하지 않았다.
