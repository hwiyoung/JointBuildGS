# 국소 상보 refinement — 진행 결과 보기와 무인 후속 실행

`scientific_verdict: null`. 사용자는 2026-09-11 진행된 결과의 정성·정량 열람, 이전처럼 3D 비교, 에이전트의 반복 감시 없이 남은 실험을 실행하도록 요청했다. 기존 전체18개 목표와 동결 명세는 유지하고, 새 검증 묶음을 운영체제 작업으로 게시한다.

**10:20:33 KST 실제 자동 게시 완료:** P3 `.0005` release까지11조건이 정적/3D 화면에 올라왔다. 독립 작업이 평가→요약→그림/지도→원본 QA→정적/3D 게시→실제 브라우저336검사를 통과했다. 새 그림의 인간 해석은 별도 대기이며 전체18개 완료로 표시하지 않는다. 단위는 `active/running`이고 에이전트 감시 없이 다음 완료 event를 기다린다.

## 결과 열람

- 사진·수치·단면·수정/손상 지도: <http://localhost:8905>
- 3D 비교: <http://localhost:8906> — 동일 위치의 ALS·MVS·Anchor8k·대응 G·LC·UAS 참조.
- 각 화면은 평가 완료 조건만 점수를 제공한다. 모델 완료 수와 평가·그림 검증 완료 수는 별개다. 미완료나 실패를 0점으로 대체하지 않는다.

8905는 불변 `review_site/packets/packet_*`에 각 검토 묶음을 저장한다. 원 수치 CSV, 요약·그림·지도와 독립 원본 대조 receipt를 hash로 결박하고 `current.json`만 원자적으로 갱신한다. 브라우저가 한 묶음을 읽는 동안 나중 묶음의 PNG와 섞이지 않는다. 새 결과는 화면의 **새 검증 결과 보기** 링크로 이동한다. `status.json`은 브라우저가60초마다 읽는 운영 상태이며 LLM 호출이 아니다.

첫 게시10조건은 P1/P2의 `.005/.0005` 네 조건씩과 P3 `.005` 두 조건이다. 대응 G 대비 raw512/0.5m F1은2조건 상승·8조건 하락이다. P3의 F1 상승에도 완전성 하락이 함께 있다. 기존 성공·새 악화와 같은 부위의 수정·손상은 [각 중간 보고](START_HERE_ko_v2.md)와 화면에 함께 남긴다.

3D는 평가에 사용한 raw/post512 표면과 표시용 점을 사용한다. 표시 표본과 화면 색은 새 평가값이나 source 정오 label이 아니다. 사진·수치 탭은3D 인상과 함께 검토한다. GT는 평가 전용이다.

## 실행 소유권

기존 `run_queue_v2.sh` 프로세스와 이미 등록된 P3 `.0005` native GPU1 재시도는 그대로 계속한다. 새 사용자 systemd 단위 `jbgs-lc-v2-automation.service`가 후속 평가와 게시를 맡는다. 에이전트, 예약 LLM 작업, API 호출을 포함하지 않는다. 사용자 manager는 `Linger=yes`이다. 호스트 재부팅이나 Docker 중단 후 자동 학습 재개까지 검증했다는 뜻은 아니다.

1. `PAIR_FINISHED`와 train/render/metrics PASS를 확인하여 새로 완료된 지역 조건만 CPU 부분 평가한다.
2. 요약, 같은 사진/단면, 수정·손상 지도, 독립 원본 pixel/거리 대조를 통과한 묶음을 게시한다.
3. 원 queue가 끝나면 기존 등록 재시도를 기다린다. 추가 원 CUDA OOM은 동일 동결 정책·GPU1·별도 attempt2로 한 번 재시도할 수 있다. 원 실패와 비용은 보존한다. 다른 실패나 재시도 실패는 숨기지 않고 중단 상태를 기록한다.
4. 성공한18개의 phase와 모든 실패 이력을 검증하여 불변 `run_selection_v2.json`을 생성한다. 품질 지표로 실행을 선택하지 않는다.
5. 전체18개 평가, 요약, 사진/지도와 원본 QA, source 층, 전체 행렬, controller trace, A–F 사례, 실패 포함 실행 비용, 정적/3D 검토 묶음을 만든다.

실행 코드의 snapshot과 SHA256 목록을 남기고 매 단계 확인한다. 코드가 바뀌면 자동 작업은 실패를 기록한다. main/retry 프로세스가 완료 표식 없이 사라진 경우에도 조용히 영구 대기하지 않는다. 자동화 자체가 실패하면 원인 검토 후 별도 복구 기록이 필요하며 기존 `started.txt` 위에 중복 재시작하지 않는다. 기존 실행/입력/결과/service와 동결 학습 tuple은 바꾸지 않는다. CPU 분석이 GPU 학습과 겹칠 수 있으므로 비용은 자원 독점 비교가 아니다.

운영 상태와 종료 근거는 외부 task root의 다음 파일이다.

```text
main_v2/automation_v2/systemd_launch.txt
main_v2/automation_v2/events.log
main_v2/automation_v2/analysis_*/<stage>.log
main_v2/automation_v2/executing_source_sha256.txt
main_v2/automation_v2/completion.json
main_v2/automation_v2/exit_code.txt
main_v2/queue/events.log
main_v2/retry_queue/P3_LC_D0005_Pnative_attempt2/
```

`completion.json`은 전체18개 기술 평가와 모든 필수 후속 receipt가 검증된 뒤에만 생성한다. 새 그림의 수동 해석은 `PENDING_HUMAN_REVIEW`로 남긴다. 자동 게시를 인간의 과학적 판정이나 전체 연구의 완료로 바꾸지 않는다. 원인 설명·방법 신규성·검증 기여는 분리하며, 첫18개에 없는 평균 배율 전역 대조·controller replay·독립 반복의 결론을 추가하지 않는다.

## 검증 기록

기존 분석·재시도 선택 통합 검증147개는 `main_v2/validation/integration_after_attempt_selection_v2/receipt.json`에서 전체 PASS다. 이 결과는 독립 학습 반복이 아니다.

정적 실제 Chromium 검증은 `main_v2/review_browser_qa/attempt_20260911T010648Z_21907/receipt.json`에서230개 PASS했다. receipt SHA256은 `942c3ac302146e7dcb99666895e2e3e584754b332783fb42b081de09d5af1dcd`다. 10조건의 네 PNG, raw/post×6문턱의 실제 F1 표시, 지역 선택, 확대, CSV, 불변 주소, 경로 차단과 모바일 폭을 확인했다. desktop/photo/mobile PNG를 실제 열어 확인했다. 이 QA가 보는 묶음은 `packet_20260911T010022_043722Z`이며 이후 새 묶음의 과학적 해석까지 대신하지 않는다.

3D의10조건×raw/post512 실제306개 브라우저 검증은 `main_v2/review_3d/browser_qa/attempt_20260911T011502_28577/receipt.json`에서 PASS다. 최신 정적 묶음 `packet_20260911T011426_098166Z`와 3D 묶음 `packet_20260911T011430_492036Z`를 정확히 결박했다. 20개 표면의 모든 vertex/triangle binary와 원 평가 NPZ의 동일성도 다시 검사했다. P1/P3의 실제 여섯 패널 화면을 열어 확인했다. 3D의 **최신 결과** 링크로 나중 게시 묶음에 이동한다.

무인 완료 판정은 `main_v2/validation/automation_completion_final_20260911T011515_KJ1lvT/receipt.json`에서17개 집중 Docker 검사 PASS다. 실제10조건·3지역의 부분 묶음을 모두 조회하고, 전체18개 완료로 통과시키지 않음을 확인했다. 전체 trace3960개, A–F72행, 원 실패 포함 비용, 36개3D와 같은 packet의 실제 브라우저 검증까지 완료 조건으로 결박한다.

systemd 단위는2026-09-11 10:15:44 KST, PID1156243으로 실제 시작했다. parent PID5265는 사용자 systemd manager이며 Codex 프로세스의 자식이 아니다. 기존 main queue PID2724692와 등록 retry PID761377은 유지했다. 첫 자동 후속 작업은 새 P3 `.0005` release를 포함한 부분 평가다. 당시 모델11개 완료·2개 학습 진행·원 실패1개이며 게시된 검토는10개다.

시작 시 systemd의 PATH에 Codex 제공 `rg`가 없어 목록 생성 두 process substitution이127을 반환했지만 parent coordinator는 진행했다. 실행 중인 코드·평가·학습을 중단하지 않고 원 guard와 오류 marker를 `main_v2/automation_v2/source_guard_repair_v2_1/`에 보존했다. 기존71개 source hash가 그대로임을 확인한 뒤 누락234개를 더한305개 guard를 원자적으로 적용하고 실제 전체 hash 일치를 확인했다. 추가 파일은 **복구 시점부터 감시**되며 시작 시 검증되었다고 소급하지 않는다. 실제 프로세스 종료가 아닌 초기 subshell의127 marker도 복구 증거로 보존했다. 원 동결 학습 명세는 그대로다. 현재 실행 코드는 수정하지 않았다.

이 PATH 차이를 반복하지 않는 별도 `start_automation_v2_1.sh`는 실행 unit에만 명시적 PATH와 파일 목록 사전 확인을 제공한다. 현재 task에는 `started.txt`가 있으므로 다시 실행하지 않는다. 새 launcher로 기존 진행 중 단위를 교체했다는 뜻은 아니다.

첫 실제 자동 연쇄의 평가 receipt는 `main_v2/evaluation/attempt_20260911T011547_079887Z/receipt.json`이며 P3 세 조건의 부분 평가다. 다른 지역의 앞선 검증 묶음과 합쳐11개를 게시했다. 정적 packet은 `packet_20260911T011902_643929Z`, 3D는 `packet_20260911T011905_382772Z`, 실제336개 브라우저 QA는 `main_v2/review_3d/browser_qa/attempt_20260911T011913_21589/receipt.json`이다. 종료 전305개 실행 source hash의 전체 일치와 active/running을 재확인했으며 전체 완료/종료 파일은 아직 없음을 확인했다.
