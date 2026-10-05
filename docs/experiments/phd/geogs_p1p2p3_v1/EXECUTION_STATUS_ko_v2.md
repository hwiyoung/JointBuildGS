# 실행 중 인계 지점 — allocator_v2

2026-09-08 02:41 KST 기준 중간 기록. 완료 보고서가 아니다. `scientific_verdict: null`.

- `$TASK` = `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`.
- 공식 예제의 30k 학습·실제 렌더·raw/post mesh·공식 지표는 완료했다. 경로는 `native_example_retry_compat_v1/output/`; 세 crop 결과가 아니다.
- 세 crop 입력은 각각 `inputs/Px/input_manifest.json`으로 봉인했다. 과학 설정은 `contracts/execution_v1.json`, 분석 설정은 `contracts/evaluation_analysis_v1.json`이다. 기존 입력 바이트는 변경하지 않는다.
- 기존 P1 두 학습은 CUDA OOM으로 종료되어 `runs/`, `parity/`, `queue/`에 남아 있다. [복구 기록](ALLOCATOR_RECOVERY_ko_v2.md)을 따른다.
- 새 primary 실행은 `runs_allocator_v2/`, `parity_allocator_v2/`, `queue_allocator_v2/`이다. 경로/allocator 계약은 `contracts/runtime_layout_allocator_v2.json`, SHA256 `28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5`.
- GPU0의 P1 `D005_Pnative`와 GPU1의 P1 `D0005_Pnative`가 각각 약 15900/15800회로 실행 중이다. 두 경우 모두 기존 OOM 구간을 넘었으나 30000회는 아직 완료하지 않았다. 당시 Gaussian 수는 6033926/5714579다.
- 두 primary worker는 `JBGS_RUNTIME_REVISION=allocator_v2 bash scripts/phd/geogs_p1p2p3_v1/run_matrix_worker.sh 0` 및 마지막 인자 `1`로 시작했다. 기존 worker/컨테이너가 실행 중이면 중복 실행하지 않는다. 각 GPU의task-local flock과 `queue_allocator_v2/claims/`가 소유권 기록이다.
- P1의 새 바닐라를 포함한 모든 조건은 `runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000/`의 정확한 기존 anchor를 쓴다. P2/P3는 새 바닐라에서 anchor를 생성한다. 실제 P1 새 복원 gate는 `parity_allocator_v2/P1/anchor_gate.json`으로 통과했다.
- 같은 조건의 원 시도/새 allocator 학습 prefix 차이는 `runtime/p1_common_prefix_14400_v1/`의 CSV·trace snapshot·실제 PNG·receipt에 있다. 이는 품질 점수가 아니다.
- UAS 평가 전에 각 지역 동일 allocator·동일 8000 anchor 바닐라 반복 1회를 추가하기로 결정했다. 여섯 primary 조건을 대체하지 않는다. 별도 `supplemental_repeat_v1.json` 계약과 `native_repeat_allocator_v2/Px/D005_Pnative/` 경로를 사용하는 runner/evaluation 연결 작업이 진행 중이다. 실제 반복 GPU 실행은 아직 없다.
- 공식 renderer source는 불변이다. 기록용 driver만 실제 TSDF 값·로그·source PLY/cfg_args·parser snapshot/hash를 검증하도록 보완했다. 각 실행이 사용한 driver snapshot을 보존한다.
- 평가 entrypoint는 `scripts/phd/geogs_p1p2p3_v1/evaluation/{seal_candidates,run_evaluation,summarize,case_figures}.py`. 새 실행은 명시적으로 `--runtime-layout /task/contracts/runtime_layout_allocator_v2.json`을 넘긴다. 반복 계약 연결 후 해당 flag도 반드시 사용한다.
- **UAS payload는 아직 읽지 않았다.** primary 18개와 추가 반복 3개의 고정 결과를 봉인한 뒤 UAS 기하 평가와 실제 렌더 평가, 표·사례·viewer 최종 QA를 수행한다. 기술적 실패를 참조 부재로 바꾸거나 조건을 누락하지 않는다.
- 현재 viewer는 `http://127.0.0.1:8902/app/index.html?manifest=/task/viewer_preflight/manifest.json`의 입력 검증용이다. 아직 GeoGS 최종 결과 화면이 아니다. 실제 결과 manifest와 브라우저 검증이 남아 있다.
- [보존 중간 점검](PRESERVATION_INTERIM_ko_v2.md)은 기존 소스/문서 해시와 서비스 62개 식별 정보 일치를 확인했다. 참조 가능 binary 3126개 byte hash는 평가 접근 gate 후 최종 확인한다. 범위 밖 새 문서는 건드리지 않는다.

다음 필수 작업은 primary/반복 학습 완료, 공식 최종·anchor·512/2048 추출, 후보 봉인, 세 지역 UAS/실제 사진 평가, primary와 반복을 구분한 분석표, 실제 사례 그림·viewer 표시 검증, 최종 보존 검증, 결과 분석과 최종 인계다. 실행 중 기록이나 계획 문서로 완료를 대신하지 않는다.

## 후속 준비 완료 기록

위 인계 지점 이후 반복 실행기·평가·요약표 연결을 완료했다. `contracts/supplemental_repeat_v1.json` SHA256은 `3c62494f13de96dba33b1c36cbadf58e555305fee01ce641dd41f560bdfacafc`다. primary 18개가 네 phase를 모두 완료한 뒤 다음 명령을 사용한다. 각 반복은 primary worker와 같은 GPU flock을 사용한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/run_native_repeat.sh P1 0
```

P2/P3도 지역과 실제 비어 있는 GPU를 명시한다. 평가의 네 Python entrypoint에는 `--runtime-layout /task/contracts/runtime_layout_allocator_v2.json --repeat-contract /task/contracts/supplemental_repeat_v1.json`을 모두 전달한다. 계약이 존재하는데 반복 flag를 빠뜨리면 평가가 거부된다. 반복 표는 `evaluation/summary/supplemental_repeat/`, viewer 식별자는 `native_repeat_1`이다. 더 좋은 바닐라를 골라 primary 결과를 교체하지 않는다.

지역 렌더·보조 추출은 `resource_schedule.py`가 한 건씩 실행한다. 공유 잠금은 task의 `runtime/weights/.geogs_extraction.lock`이며 이미 생성했다. `runtime/prepare_execution_lock.sh`가 이 inode를 교체하지 않고 준비한다. 기존 weight 바이트는 그대로다. 잠금 대기는 실제 phase 시간과 별도로 기록한다. 현재 실행 중인 Bash launcher를 수정하지 않고 Python phase driver만 보완했다.

[도구 검증](VALIDATION_ko_v2.md)의 통합101개와 실제 읽기 전용 공유 잠금 검사2개가 통과했다. 잠금 추가 후 반복·평가·요약 관련45개 검사도 통과했다. 모두 실제 지역 성능 결과와 구분한다. 추가 sub-agent 호출은 thread limit으로 거부되어 이후 해당 보완은 부모가 직접 수행했다.
