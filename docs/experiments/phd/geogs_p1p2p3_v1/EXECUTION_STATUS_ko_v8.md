# 주18개 완료와 세 native 반복 진입

2026-09-08 18:58 KST · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

**주18개 조건의 필수 산출물이 모두 완료됐고, 세 추가 바닐라 반복을 시작했다. 아직 최종 지역 평가·분석 완료 상태가 아니다.** 18:56:58 KST에 primary와 resource_v3 완료 marker가 각각18개임을 확인했다. 이어 P1/P2 `native_repeat_1` 학습 driver가 기동했고, P3는 같은 GPU의 P1 반복 뒤에 실행된다.

## 실제 완료한 범위

세 지역의 각6조건이 최종30,000회 학습, 공식 최종1024 raw/post 표면과 실제 렌더·native metrics, 필수 최종512 raw/post를 완료했다. 공통8,000 anchor의512 raw/post도 지역별로 생성됐다. 동일 anchor·입력·조건·학습량은 유지했다. P1의 주 바닐라도 기존8,000 anchor부터 재개했으며, P2/P3 주 바닐라는 처음부터 학습한 이력을 보존한다.

| 마지막 P3 조건 `D0_Prelease` | 기록 |
|---|---|
| 학습 범위 |8,000→30,000회 |
| 최종 전체 문맥 Gaussian / 보호 대상 |5,721,119 /0 |
| train driver wall |6,509.362133초 |
| render driver wall |319.536705초 |
| metrics driver wall |40.248867초 |
| 필수 최종512 |63.072940초, PASS, native/validated exit0, OOM 증가0 |
| 선택 최종2048 |67.236515초, TECHNICAL_RESOURCE_UNAVAILABLE, native−9,32GiB cgroup OOM kill 증가1 |
| 부모 auxiliary wall |144.373363초; 하위 variant 시간과 중복 합산 금지 |

train/render/metrics와 부모 auxiliary는 모두 PASS·native/validated exit0이다. 원 영수증은 `runs_allocator_v2/P3/D0_Prelease/`와 `extraction_resource_v3/primary/P3/D0_Prelease/`에 있다. 앞선 조건의 실제 시간·실패·상태는 [P1 완료 기록](EXECUTION_STATUS_ko_v5.md), [P3 진입 기록](EXECUTION_STATUS_ko_v6.md), [P3 완료 과정](EXECUTION_STATUS_ko_v7.md)에 보존한다. Gaussian 수는 전체 학습 문맥의 상태이며 표면 품질 지표가 아니다. 시간·RSS·CUDA/cgroup의 범위는 [측정 정의](RESOURCE_MEASUREMENTS_ko_v1.md)를 따른다.

현재 주 조건들의 선택2048과 공통 anchor1024는 모두32GiB 상한에서 확인된 메모리 미가용이다. 실패와 부분 파일을 보존하며 품질0점이나 참조 부재로 치환하지 않는다. 최종 선택 추출 가용성 집계는 반복 세 조건까지 포함한 봉인에서 확정한다. 주1024 결과와 anchor/최종512 비교는 유지한다.

## 현재 실행과 해석 범위

활성 제어기는 `runtime/resource_v3_continuation/attempt.bPR61e/`의 `continue_resource_v3.sh` 실행이다.18:46 KST에도 원 실행 세션이 살아 있음을 확인했고,18:56 이후 로그는 주18개 통과와 반복 진입을 기록했다. 현재 값은 다음 읽기 전용 명령으로 확인한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/runtime/monitor_progress.sh
```

고정된 후속 순서는 GPU0의 P1→P3 반복, GPU1의 P2 반복이다. 각 반복은 해당 지역의 정확한8,000 anchor, seed0, 동일 allocator와 바닐라 제어를 사용하며 새 `native_repeat_allocator_v2/<지역>/D005_Pnative/`에 기록한다. 물리 GPU와 실행 이력·비용도 영수증으로 구분한다. 두 실행의 차이는 제한된 수치 재현성 관찰이며 다중 seed 안정성·잡음 상한·신뢰구간을 제공하지 않는다.

이 시점까지 UAS payload와 실제 지역 품질값을 열어 해석하지 않았다. native producer가 metric 파일을 생성한 것과 사람이 조건 선택·분석에 읽은 것을 구분한다. 현재까지의 수정은 기록된 입력/호환/자원/표시 보완이며, 결과에 맞춘 조건 재조정은 없다. 원 source·기존 실패 시도·Wu–Vallet 산출물·canonical E1–E6는 별도다.

같은 anchor 검증의 exact 범위는 optimizer 실행 전 복원 상태·hook·같은 checkpoint PLY/render다. 한-step은 카메라·Adam step counter·개수·유한성의 실행 건전성 검사이며 갱신 tensor 전체의 bitwise parity를 입증하지 않는다. [상태 검증 기록](STATE_VALIDATION_ko_v1.md)의 세 지역100회 continuation은 모두 exact=false다.

## 남은 실행과 최종 완료 조건

자동 제어기는 반복3개 완료 후 all21 필수 후보와 모든 선택 추출의 가용성을 봉인한다. 그 다음 지역별 UAS 기하 평가·실제 평가 사진의 렌더 평가, summary, 사례 그림을 실행한다. `runtime/finalize_after_all21.sh`에는 runtime layout·repeat·resource 계약이 모두 연결돼 있다. 실제 봉인 상태 `ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED`를 확인해야 한다.

자동 평가 후 다음 별도 작업을 완료한다. 각 실행은 새 출력 경로를 사용하고 기존 산출물을 덮어쓰지 않는다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_factor_contrasts.sh
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_control_trajectories.sh
bash scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.sh full_results_display_v1 \
  'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_v2.json&qa_mode=full'
bash scripts/phd/geogs_p1p2p3_v1/preservation/run_final.sh
```

factor는 all21 봉인과 summary, control과 최종 보존은 all21 봉인, 실제 브라우저 QA는 최종 manifest/사례 그림이 필요하다. 전체 기존6471개 파일 바이트 대조는 이 마지막 보존 감사에서 수행한다. 중간 서비스 식별 정보·메모리 표본 감사는 그 범위의 점검이며 전체 payload·무중단·LAN 접근·내구성 있는 백업 증거로 확대하지 않는다.

최종 `RESULTS`와 `HANDOFF`에는 세 지역 조건별 양방향 거리·정확도/완전성/F1·임계값/밀도 민감도, raw/post와 같은512 anchor/최종, 독립 평가 사진 지표, 반복 간 차이, 실제 자원 비용과 실패를 함께 해석한다. 원자료 CSV/JSON/NPZ와 실제 단면·거리 지도·동일 사진 렌더·비교 화면의 경로와 사용법을 제공하고 root/검토자가 실제 그림을 열어 확인한다. 개선·유지·악화·판단 불가의 선택 근거와 제한을 남기고, 원문이 이미 보인 prior 오류/결손 대응을 인정한다. 제약 완화의 효과를 반복 재판단의 우위로 확대하지 않는다.

외부 task는 [resolver](../../../../artifacts/manifests/geogs_p1p2p3_v1.yaml)를 따른다. 현재 뷰어 주소는 작업 호스트의 `127.0.0.1:8902`이며 실제 최종 지역 화면 검증은 아직이다. **계획·문헌·예제·합성 검증과 주18개 완료만으로 전체 작업이 끝난 것은 아니다.**

## 19:00 KST 이후 — P2 반복 실패 진단

P2 반복은18:59 KST에 첫 densification 부근 CUDA OOM으로 종료됐다. 주18개와 P1 반복은 유지하고 실패 영수증/로그를 보존한다. [REPEAT-001](ISSUES_ko_v1.md)에 실패 위치·20.131426초 비용·같은 설정/GPU에서 성공한100회 parity와의 대조를 기록했다. 새로운 계측 진단은 별도 경로에서 준비하며, 실패 해결이나 반복 완료를 선언한 상태가 아니다.

원 controller는 P1→P3 worker가 끝난 뒤 P2 worker의 기존 exit1을 확인하므로, 위 자동 all21 최종화 경로는 현재 실패 때문에 그대로 완료될 수 없다. 진행 중 controller·학습 source를 편집하지 않는다. P2의 복구와 모든 실제 결과 검증 후 별도의 최종화 진입을 기록해야 한다. UAS·평가 렌더 품질값은 아직 열지 않았다.

19:16 KST 후속 확인에서 P1 반복도14,500회 이후 CUDA OOM으로 종료됐고, 원 controller는 `repeat_exit_codes.txt: 1 1`과 전체 exit1을 남겼다. P3 반복은 시작하지 않았다. [REPEAT-002](ISSUES_ko_v1.md)에991.796377초 비용·원 메모리 오류·실패 해시를 기록했다. P2 계측 진단과 두 실패의 보존 및 같은 설정의 제한된 재시도 절차를 준비한다. 이 시점에는 재시도/복구가 아직 실행되지 않았다.

앞선18:57:41 KST의 [P3 전체 보존 감사](PRESERVATION_AFTER_P3_ko_v1.md)는14개 보조 추출 연결·58개 감사 입력·닫힌 증거33/33·기존 서비스62/62 식별 정보를 확인했다. root도 정본/원자원/서비스/닫힌증거 영수증 네 해시를 재확인했다. 이후 반복 실패와 전체 all21 최종 보존 감사는 별도다.
