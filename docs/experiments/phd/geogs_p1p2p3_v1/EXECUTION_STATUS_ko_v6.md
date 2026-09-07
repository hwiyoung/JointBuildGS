# P3 진입 시점의 실행 인계

2026-09-08 12:24 KST 시점 기록 · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

**진행 중이며 완료 보고가 아니다.** 주 조건11/18개의 필수 학습·1024 표면·실제 렌더·native metrics·512 보조 표면이 완료됐다. P1은 여섯 조건 전부, P2는 아래 다섯 조건이다. P3는 원 제어 조건의 학습 container를 시작했다. 지역 UAS와 조건별 품질 평가값은 아직 분석에 사용하지 않았다. 세 지역의 추가 native 반복도 아직 실행 전이다.

| P2 완료 조건 | 학습 시작 → 끝 회차 | 최종 Gaussian 수 | 기록된 train 단계 wall (초) |
|---|---:|---:|---:|
| D005_Pnative | 0 → 30000 | 4,093,957 | 5,614.205473 |
| D0005_Pnative | 8000 → 30000 | 3,105,715 | 4,353.701754 |
| D0_Pnative | 8000 → 30000 | 3,251,669 | 4,292.658162 |
| D005_Prelease | 8000 → 30000 | 4,049,090 | 5,031.463338 |
| D0005_Prelease | 8000 → 30000 | 2,896,797 | 4,137.764682 |

이 수는 학습 context의 Gaussian 수이며 추출 표면의 정확도·완전성 수치가 아니다. wall은 해당 단계 driver의 기록·종료 감시·산출물 확인 등을 포함하며 순수 최적화 시간이나 동일 학습량의 속도 비교가 아니다. 원값은 외부 task의 `runs_allocator_v2/P2/<condition>/train_receipt.json`과 `model/jbgs_trace.jsonl`에 있다. [시간 정의](EVALUATION_REVIEW_ko_v1.md)를 따른다.

P2의 `D0_Prelease`는 당시24,000회였고, GPU1에서는 `P3/D005_Pnative`를 시작했다. 최신 값은 다음으로 확인한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/runtime/monitor_progress.sh
```

## 현재 실행과 보존

원 orchestrator `runtime/resource_v3_continuation/attempt.bPR61e/`가 주18개 → 추가 반복3개 → 정확한 후보 봉인 → 지역 기하/렌더 평가 → summary/실제 사례 그림을 이어서 실행한다. root의 실행 session은53747이다. 현재 동작 중인 launcher/controller/공식 실행 source를 수정하지 않는다. 과거 live Bash 파일 수정 뒤 발생한 EOF 사건과 기존 실패 시도는 보존돼 있다.

공식 확보 커밋, 계측·카메라 adapter source, 고정 Docker image, `execution_v1.json`, allocator_v2/repeat/resource_v3 계약은 유지한다. 모든 조건에 prior 초기화와 anchor 영향이 남는다. 새 알고리즘·반복 재판단 구현은 없다.

필수 최종1024와512, 공통 anchor512는 성공해야 한다. P1과 현재 완료한 P2 조건의 선택 final2048 및 각 공통 anchor1024는 실제 시도에서32GiB cgroup OOM을 확인했다. 개별 SIGKILL/OOM counter·메모리 trace·영수증을 그대로 보존하고 `TECHNICAL_RESOURCE_UNAVAILABLE`로 기록한다. 이를 표면 성공이나 참조 부재·복원 실패0점으로 바꾸지 않는다. [자원 계약](EXTRACTION_RESOURCE_AMENDMENT_ko_v3.md), [이슈 기록](ISSUES_ko_v1.md)을 따른다.

P2 첫 두 조건의6개 보조 추출 영수증/trace 연결은 `preservation/after_p2_first_resource_jobs_v1/`에서 재검증했다. 필수3개 PASS, 선택3개 확인된 OOM이다. 당시 기존 서비스62개의 현재 식별 정보도 기준과 모두 일치했다. 주기적 host MemAvailable 최솟값은 약23.03GiB이며 순간 최저값·무중단·브라우저 건강·전체 payload 보존 증명은 아니다. 12:23 KST 디스크 점검에서는 외부 저장소의 여유 공간 약2.1TiB를 확인했다. 최종 파일 바이트 검사는 봉인 후 별도 실행한다.

## 봉인 후 수동으로 이어갈 단계

orchestrator의 summary/cases 완료 문구만으로 사용자 요청이 끝나지 않는다. 아래 명령은 아직 실행 전이며, 해당 gate를 통과한 뒤 수행한다. 기존 출력이 있으면 검증하고 별도 attempt를 사용한다.

```bash
# all21 봉인 이후: 실제 제어 기록 및 source/입력 SHA를 연결한 그림·CSV
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_control_trajectories.sh

# all21 봉인과 summary 이후: 고정된 9개 요인 대비
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_factor_contrasts.sh

# 실제 manifest와 사례 그림 생성 이후: 세 지역 실제 브라우저 QA
bash scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.sh full_results_display_v1 \
  'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_v2.json&qa_mode=full'

# all21 봉인 이후: 보류한 payload 바이트를 포함한 기존6471파일·서비스 최종 검사
bash scripts/phd/geogs_p1p2p3_v1/preservation/run_final.sh
```

- [요인 대비](FACTOR_CONTRASTS_ko_v1.md): 별도 Docker 합성28/28 PASS. 기존 evaluator CSV, 실제 all21 gate에 대한 합성 inventory, 결측·무한대·동일 사진 식별을 검증했다. 실제 점수 실행 전이다.
- [제어 궤적](CONTROL_TRAJECTORIES_ko_v1.md): 별도 Docker 합성17/17 PASS. 정확한42개 trace/receipt 바인딩, 원 source의 기록 의미와 그림 출력을 확인했다. root도 최종 합성 P2 primary 그림을 직접 열어 확인했다. 실제 지역 그림 검토는 남아 있다.
- [삼각면 표시](DISPLAY_VALIDATION_ko_v1.md): CPU58개, 합성 browser433개, root 결합130 PASS/3 SKIP 등의 기존 검증을 유지한다. 중복 검사를 합산하지 않는다. 실제 지역의 삼각면·렌더·단면 화면과 큰 payload의 브라우저 동작은 아직 검증 전이다.

모든 실제 정량표와 native 반복 차이, 양방향 거리·밀도/임계값 민감도·raw/post·실제 평가 사진을 함께 읽어야 한다. 지역별 개선·유지·악화·판단 불가 사례를 실제 사진·동일 단면·거리 지도와 대조하고 선택 근거를 남긴다. 관찰 → 입력/구현/제어 영향 → 원문과의 관계 → 추가 수정 필요성 → 후속 검증 질문 순으로 결과 분석과 최종 인계 문서를 작성한다. 가중치 완화의 효과를 반복 재판단의 필요성으로 확대하지 않는다. 실제 viewer 접근 주소·사용법·표시 검증, 기계 판독 원자료, 실패/편차와 보존 검사까지 제공해야 완료다.

외부 task 경로는 [resolver](../../../../artifacts/manifests/geogs_p1p2p3_v1.yaml)를 따른다. 이전 Wu–Vallet 산출물과 GeoGS 결과를 혼동하지 않는다. 현재 비교 화면 서비스는 `127.0.0.1:8902`에 한정되며 LAN 검증이나 내구성 있는 백업을 선언하지 않는다.
