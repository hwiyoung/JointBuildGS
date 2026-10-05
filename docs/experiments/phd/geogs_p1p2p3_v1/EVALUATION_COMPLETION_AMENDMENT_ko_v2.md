# P1/P2/P3 주 실험 평가 시작 조건 변경

- task_id: `PHD-GEOGS-P1P2P3-v1`
- 결정 시점: 2026-09-08 19:34:11 KST, 지역별 정량 결과와 UAS 평가를 열기 전
- scientific_verdict: null
- 설정: `configs/phd/geogs_p1p2p3_v1/evaluation_completion_v2.json`
- SHA256: `3e200db7de4cc171158b08deccffd3869bfd2d30c2a5b89805b86ad1903112c6`

주 실험 18개는 학습, 공식 렌더, native metrics, 필수 최종 1024/512 raw/post 표면과 지역별 공통 anchor512를 완료했다. 그런데 보조 native 반복의 첫 P1·P2 실행이 CUDA OOM으로 실패했고, 제어기가 종료되어 P3 반복은 시작하지 않았다. 보조 반복 3개의 성공을 주 실험 평가의 선행 조건으로 묶은 진행 설계 때문에 완료된 결과의 분석이 지연되었다.

이 변경은 **완료된 고정 주 실험 18개를 먼저 평가**하도록 평가 시작 조건만 바꾼다. 기존 `supplemental_repeat_v1.json`의 “Seal all3 repeats before UAS evaluation” 일정 규칙을 이 범위에서 대체한다. 기존 계약 파일은 수정하지 않는다. 영상·카메라·입력·seed·anchor·18개 조건·학습량·추출 규칙·평가 지표와 임계값·대표 사례 선택법은 그대로 유지한다. 일부 양호한 조건만 선택하는 방식이 아니며, 주 실험 18개의 필수 산출물 중 하나라도 불완전하면 평가는 계속 차단한다.

| 지역 | 보조 반복의 실제 상태 | 학습 driver 시간 | 품질 비교 |
|---|---|---:|---|
| P1 | CUDA OOM 실패, 마지막 기록 iteration14500 | 991.7963771820068 s | 평가 불가 |
| P2 | CUDA OOM 실패, 첫 densification 부근, after-step 기록 없음 | 20.131426334381104 s | 평가 불가 |
| P3 | 앞선 제어기 실패로 미실행 | null | 평가 불가 |

P1·P2의 receipt, invocation, native log, GPU 기록 총 8개 파일을 정확한 SHA로 결합한다. P3의 미실행 상태도 별도 행으로 남긴다. 실패·미실행 반복에 기하·렌더 점수를 만들지 않으며, 참조 부재나 ROI 복원 실패로 바꾸어 해석하지 않는다. 실패한 학습의 비용은 성공한 주 실험 비용과 별도로 보고한다.

이번 완료 범위에서는 추가 메모리 진단·실패 경로 이동·재시도를 실행하지 않는다. 준비해 둔 진단 및 보존 유틸리티는 실행 결과가 아니다. 특히 archive 소스 검토에서 발견한 `os.walk` 읽기 오류 처리와 조상 symlink 경계 문제는 아직 수정하지 않았으며, 해당 도구는 실행 가능 판정을 받지 않았다. 기존 실패 폴더와 제어기 종료 기록은 경로와 바이트를 보존한다.

주 실험 효과는 각 조건의 한 번의 실현 결과에 대한 개발 진단이다. 동일 조건의 실제 품질 변동은 측정하지 못했으므로 작은 차이가 재현 가능하다고 단정하거나 통계적 우위를 주장하지 않는다. anchor 복원 직전 상태의 정확한 일치와 이후 최적화 궤적의 일치는 별개다. 향후 보조 반복을 다시 수행한다면 고정 설정을 유지하고 별도 seal·보고서로 연결하며, 주 실험 결과에 맞춘 설정 변경이나 기존 결과 대체에 사용하지 않는다.

최초 seal-only 실행은 `scripts/phd/geogs_p1p2p3_v1/runtime/finalize_primary18_v2.sh`, 후속 전체 평가는 별도 `scripts/phd/geogs_p1p2p3_v1/runtime/finalize_primary18_inputs_v2.sh`로 기록한다. 새 seal의 상태는 `PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE`이며, 원래 all21 완료 상태를 사용하지 않는다. 이 문서 작성 시점에는 변경 구현 검토 중이며, UAS 평가·실제 분석·최종 viewer 검증은 아직 시작하지 않았다.

19:44 KST 무렵 `--seal-only` 실행을 시작했다. `runtime/finalization_primary18_v2/attempt.mLvO9B`에 72개 필수 phase PASS와 실제 명령·코드 사본을 기록한다. 이 실행은 UAS를 mount하지 않으며, 시작 시점 코드 사본을 유지한다. Core Docker 합성/호환성 17개 검사 PASS 영수증은 `runtime/completion_amendment_validation_v1/attempt.WnMXDv/validation_receipt.json`이고 SHA는 `60dc76da97e8aa033d035c0b98c2177b54a941744d87b824bac7f0b92d435833`이다. 시작한 core 사본 네 파일이 검증 사본과 동일함도 확인했다.

보고서·제어 궤적·요인 대비·보존 gate의 완료 범위 연결은 Docker 115개 검사 PASS, failure/error/skip 0으로 확인했다. 영수증은 `runtime/primary18_downstream_validation_v1/attempt.hB43Xj/test_receipt.json`, SHA `5e43430ba6f13d736a3c34c59494875110d2df5d42f32b9c625f5c1d23fc2185`이다. 이 검증은 실제 UAS·품질·실패 payload를 mount하지 않았으며, 실제 결과 분석을 대신하지 않는다. 지역별 보조 실행 상태는 viewer의 notes와 다운로드에 표시하고, 완료된 표면처럼 선택 목록에 넣지 않는다.

19:47:59 KST 파일 크기 점검에서는 봉인 대상 대형 파일만 843개·158.664 GiB였다. 기존 `load_seal`이 여섯 평가 단계마다 전체 모델·optimizer·보조 PLY까지 재해시하면 최소 951.983 GiB를 추가로 읽는다. 실제 세 지역 geometry 표면은 합계 약17.000 GiB, 렌더/평가 사진은 약0.494 GiB였다. 이는 파일 크기와 소스 호출 횟수에서 계산한 I/O 추정이며 실제 벽시계 시간 측정값이 아니다.

이에 후속 runner는 명시적인 `--verify-stage-inputs`로 해당 지역·단계가 실제 소비하는 봉인 표면/렌더/평가 사진을 SHA와 byte 수로 검증한다. geometry의 원 baseline과 UAS 참조는 기존의 별도 SHA 검사를 유지한다. 최초 seal은 모든 부모 모델·checkpoint를 포함해 전체 바이트를 검증하며, 최종 보존 감사도 전체 봉인 파일을 다시 검증한다. 중간 제어기의 seal 재사용/완료 확인은 완전한 후보 목록과 계약을 검증하고, 각 geometry/render 영수증의 `REGIONAL_CONSUMED_INPUTS_v1` 검증 증거를 요구한다. 기본 all21/명시적 옵션 없는 경로의 전체 재해시 동작은 유지한다. 최초에는 `attempt.mLvO9B`의 seal 직후 전체 재검사도 유지하려 했지만, 실제 최초 봉인 완료 후 중복 읽기만 명시적으로 중단했다. 완료 봉인과 중단 경계는 [실행 상태 v9](EXECUTION_STATUS_ko_v9.md)에 기록한다.

각 geometry job은 같은 mesh를 한 번 읽어 다섯 sensitivity를 평가하므로 source SHA도 job당 한 번 산출해 재사용한다. 표본화·거리·렌더 품질 계산·선택 조건은 변경하지 않는다. 새 운영 검증 경로의 정확한 입력 집합, hash와 검증 크기는 실제 단계별 영수증으로 남긴다. 진행 중인 snapshot은 수정하지 않으며 후속 full runner는 새 검증을 마친 코드 사본을 사용한다.

후속 경로 검증은 `runtime/stage_input_verification_validation_v1/attempt.MvgNSI/validation_receipt.json`에 기록했다(SHA `0f1f573a2c5ebfb6421a64d18f3a8dcf99039173f1b9fe5dbcb909e5edfcd90a`). Docker 검사 31 PASS·기존 native source/weights 필요 parity 3 SKIP·실패0이며, 기존 native source/weights를 실제 mount했던 선행 검증을 대체하지 않는다. 기하 계산 호출과 관련 함수의 AST 동일, 렌더 코드는 운영 메타데이터 허용 키 3개 외 AST 동일을 확인했다. root가 runner·finalization gate·기하/렌더 평가 코드의 실제 파일이 이 검증 사본과 일치함을 재확인했다. 영수증 gate는 단순한 양수 count만 허용하지 않고, 완전한 seal에서 해당 지역의 실제 소비 경로를 재구성하여 파일 목록·SHA·크기·개수·합계와 canonical manifest hash까지 검증한다.

20:02:32 KST에 root가 launcher 관리 오류를 발견했다. Docker에서 사용하는 helper 사본은 고정되어 있었지만, Bash 자체는 repo의 `finalize_primary18_v2.sh`를 열고 있었는데 root가 여기에 후속 검증 옵션을 추가했다. 실제 PID3314274의 fd255는 같은 inode78071905, 읽기 위치6184였고 실행 당시 파일은6335 bytes, 수정판은6458 bytes였다. 따라서 남은 tail의 읽기 위치가 어긋날 위험이 있었다. 현재 native seal이 P3 파일을 처리하는 동안, 수정판을 별도 `finalize_primary18_inputs_v2.sh`로 보존하고 실행 중인 원 파일은 `attempt.mLvO9B/launcher_snapshot.sh`의6335 bytes로 정확히 복원했다. 복원판 SHA `613ea2dc5791d3d016fc7b8218ecdc66034367f47774349aa6007249cfdca163`, 후속판 SHA `748d4a3a84d58bc37529b6d35218fc5154d5671e52eca740c402e90872c0d226`이며 각각 실행 당시/검증 당시 사본과 cmp 일치를 확인했다. native 작업이나 서비스를 중단하지 않았고 helper 사본도 수정하지 않았다. 현재까지 이 오류에 의한 실행 실패는 관찰되지 않았지만, “실행 중 launcher를 전혀 수정하지 않았다”는 주장은 하지 않는다. 후속 실행은 별도 파일을 사용하며 실행 종료 전 수정하지 않는다.
