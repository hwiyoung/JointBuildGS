# R1 대조군 실행 이슈

## R1R-003 — 하늘이 유한 depth와 TSDF 표면에 포함됨

- 문제: 최종 RGB mesh에 하늘색 면이 보인다.
- 확인: 단색 viewer 배경과 별개로 native Gaussian RGB·depth에 하늘 표현이 있다. 실제 sky-only 402,500픽셀 표본에서 prior 양수 depth 0개, MVS 2개, 8k/30k 렌더는 모두 유한 양수다. 30k 표본의 66.33%가 TSDF depth range 이내다. MVS supervision 이전 8k에도 존재하므로 MVS refinement의 단독 원인으로 설명할 수 없다.
- 구현 경로: 전체 RGB loss와 alpha 없는 JPEG 입력, 제공된 alpha mask만 적용하는 TSDF 추출. 렌더 alpha·MVS 유효성에 의한 추출 제외는 없다.
- 조치: 기존 산출물은 보존하고 Docker CPU 진단 및 RGB/depth 대조 그림을 생성했다. 자세한 수치·계보·대응 제안은 `SKY_DIAGNOSTIC_ko_v1.md`.
- 해결 여부: **진단 확인 / 수정 미실행**. 모든 triangle의 ray별 기여 또는 전체 하늘 픽셀 비율을 측정한 것은 아니다.
- 남은 작업: 검토된 sky mask로 별도 추출 비교, 향후 학습의 배경 처리 통제. training/mesh를 이번 진단에서 바꾸지 않았다.

## R1R-002 — 최종 표면 추출의 RAM 한도 초과, 2026-09-17 확인

- 문제: 학습은 30,000회 PASS였으나 `extract_final`의 자식 프로세스가 exit -9로 끝났다. 최초 뷰어에는 검증된 8k/30k Gaussian 중심점만 표시되었다.
- 확인된 원인: 2026-09-17 01:01:11 KST 커널 로그의 `CONSTRAINT_MEMCG`, `Memory cgroup out of memory` 및 PID 1599461 종료 기록. CPU RGB/depth map을 누적하는 추출 과정이 컨테이너 RAM 32GiB 한도를 넘었다. GPU OOM이나 학습 실패가 아니다.
- 조치: 실패 산출물·receipt·원래 status를 보존했다. 동일 `phase.py`, 동일 native `render.py`, 동일 checkpoint/입력/TSDF512 설정을 사용하며 RAM만 56GiB, swap 상한 포함 56GiB로 설정한 별도 복구 attempt를 시작했다. 학습 재실행은 0회다. future queue에도 추출 단계 RAM 56GiB 및 시작 전 가용 메모리 대기를 반영했다.
- 복구 경로: `mesh_recovery_20260917T022937Z_ODNcoWVm`, 실행 service `jbgs-r1-mesh_recovery_20260917T022937Z_ODNcoWVm.service`. 원래 학습 attempt의 `mesh_recovery.json`은 이 경로를 가리키는 resolver다.
- 해결 여부: **추출 복구 PASS**. 최종30k와 Anchor8k 모두 RGB 표면 추출, 기하 유한성, 84개 evaluation RGB 순서 검증을 마쳤다. recovery status는 COMPLETE다. 뷰어에서도 최종 RGB 삼각형 메쉬를 실제 로드·표시했으며 Chromium 검사 9개가 PASS했다.
- 뷰어: publisher v3가 원래 학습 결과와 새 복구 추출 결과를 연결한다. 서버/앱 v2는 그대로 유지하며, 가시적 상태는 복구 attempt를 따른다. 새 표면은 receipt와 PLY hash 검증 뒤에만 표시한다.
- 남은 위험: 메쉬의 추출·표시 성공은 기하 정확도 판정이 아니다. 하늘 표면 유입은 별도 R1R-003에서 다룬다.

커널 증거는 복구 디렉터리 `original_oom_evidence.log`에 보존했다.

2026-09-16 착수 기록: 봉인 입력 검증 PASS, Anchor 학습 진행 및 유한 loss/gradient 확인. 기록 시점까지 학습 실패는 관측되지 않았다. 단계별 실제 실패는 외부 attempt의 `status.txt`, 해당 단계 `receipt.json`, `driver.log`와 `process.log`에 남는다. systemd 또는 컨테이너 외부 종료로 receipt를 쓰지 못할 경우 service/journal과 Docker 종료 상태도 확인해야 한다.

## R1R-001 — 뷰어 표시 개선

초기 브라우저 QA는 PASS였으나, 4개 창을 가로로 비교하기 쉬운 배치와 객체축 표시 문구를 개선했다. 새 표면이 준비되었을 때 자동 기본 선택을 적용하고 수동 선택은 유지한다. publisher 갱신 오류는 화면 상태에도 표시하도록 추가했다. source v1과 QA v1은 보존하고 source v2 / QA v2를 별도로 기록했다. 이 변경은 학습 입력이나 실행에 영향을 주지 않는다.

## R1R-004 — 완료 후 브라우저 QA 실행 인자 오류

2026-09-17 `qa_complete_20260917_1m84bokz`는 node entrypoint 이미지에 `node`를 다시 전달해 `/qa/node` 모듈을 찾지 못하고 브라우저 시작 전에 종료했다. failure receipt를 보존하고 새 QA attempt에서 `--entrypoint node`를 명시했다. 학습·추출·viewer 서비스에는 영향이 없다. 새 `qa_complete_20260917_9MJo27dY`는 9개 검사 PASS이며 양쪽 mesh의 실제 표시도 확인했다. **해결 PASS**.
