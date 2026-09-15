# Prior 0.0005 / R1=4 실행

- 승인: 2026-09-16 사용자가 P1/P2/P3 추가 학습 및 기존 뷰어 비교를 요청했다.
- `task_id: PHD-P1P2P3-PRIOR0005-R1A4-v1`, `scientific_verdict: null`.
- 총 3회. 기존 R1=4/prior=.005와 비교하며 .0005 조건만 추가한다.
- 동일 complete Anchor8k→30k, 동일 카메라·마스크·RNG 복원·native 보호,
  MVS .05 고정 및 기존 depth 손실 분모를 유지한다. PGSR 추가 없음.
- P1은 0100_D만 마스크 조작, 다른 97뷰의 기존 depth 감독 유지.
  P2/P3는 기존 57/137개 전체뷰 마스크를 동일하게 사용한다.

## 실행·출력

- Bundle: `phase-payloads/phd/prior_weight_followup_v1/PHD-P1P2P3-PRIOR0005-R1A4-v1/attempt.rNaCh1sO`
- GPU0: P1 사전 검증→학습→추출→개별 등록, 이어서 P3 같은 순서.
- GPU1: P2 사전 검증→학습→추출→개별 등록.
- Unit: `jbgs-prior0005-gpu0-attempt.rnach1so.service`,
  `jbgs-prior0005-gpu1-attempt.rnach1so.service`.
- 독립 systemd user 서비스로 실행한다. 대화나 도구 세션 종료와 분리돼 있다.
- 기존 GPU lock을 공유하며 점유 프로세스를 종료하지 않는다.
- 원래 실험 source/input/output은 그대로 두고 별도 source/config/output을 생성했다.
- 새 source에서 기존과 달라진 파일은 지역별 weight helper 한 개이며,
  prior .005 고정 검사·기록을 .0005로 바꾼 것이다. 기하/손실식은 그대로다.
  변경 전후 SHA와 parent provenance를 preparation.json과 새 source receipt에 기록했다.
- cfg·mask·실행 코드의 시작 전 동결 SHA 확인, 실제 실행의 입력·소스 SHA 검사,
  완전한 Anchor 복원 검사를 재사용한다. 실행 명령은 각 run의 docker_command.sh에 남는다.
- `/reference` 등 평가 형상은 학습·추출 컨테이너에 노출하지 않는다.

## 관측 상태 — 2026-09-16 16:36 KST

- P1 200-step / P2 300-step 사전 검증 PASS.
- 기존 prior .005/R1=4의 첫 카메라·native MVS loss·첫 depth SHA가 정확히 일치.
- 사전 검증 전체 카메라 순서가 기존 학습 prefix와 일치.
- 실제 적용 prior=.0005, MVS=.05, R1=4, 제외 감독=0 및 보호 복원 확인.
- P1/P2 본 학습 실행 확인. 두 GPU 모두 학습 프로세스·메모리·사용률 확인.
- P3는 P1 최종 뷰어 등록 뒤 자동 진행 대기. 아직 사전 검증이나 학습 완료를 주장하지 않는다.

## 뷰어

- 기존 페이지: `http://127.0.0.1:8910/app/weights.html`
- 추가 비교: `http://127.0.0.1:8910/app/weights.html?comparison=prior`
- 원래 0/1/4 세 조건은 유지한다. 추가 비교는 .005/R1=4와 .0005/R1=4 두 조건이다.
- 완료된 각 조건만 receipt·surface·render SHA 검증 후 게시한다. 대기에 대체 결과를 쓰지 않는다.
- 통합 manifest: `viewer_rgb_v1/prior_weights_v1/manifest.json`.
- 60초마다 자동 갱신하고, 수동 새로고침도 가능하다.
- 세 지역 게시가 끝나면 별도 completion-check 서비스가 최종 browser QA를 한 번 실행한다.
  `completion_check/status.txt` 및 `completion_check/browser/receipt.json`이 최종 확인 기록이다.
- 최초 브라우저 검증: CPU Docker Chromium, 51개 PASS. 기존 mesh SHA,
  새 조건 대기, 영역·원사진·mask 연결, 모바일, 원래 세 조건 페이지 유지 확인.
  이는 초기 표시 검증이며 아직 생성되지 않은 .0005 최종 mesh 검증은 아니다.

## 완료 판정과 실패

지역별 status.txt가 `PASS_TRAINED_EXTRACTED_PUBLISHED`이고 train/alpha_4/receipt.json,
해당 viewer의 alpha_4/extraction/receipt.json이 PASS, publication.json이 있어야 완료다.
실패 시 지역 status에 실패 단계와 종료코드를 표시하고 해당 worker를 중단한다.
같은 GPU에 뒤따르는 P3도 실패한 P1을 건너뛰어 실행하지 않는다.
상태·로그가 이후 정본이며 이 문서의 관측 시각은 자동 갱신되지 않는다.

## P1 후처리 복구 및 P3 별도 실행

P1은 30k 학습 PASS 이후 publisher 설정 경로 불일치로 staging에서 중단됐다.
P2는 학습·추출·게시 완료했으며, 같은 GPU0 queue의 P3는 시작 전 대기 중이었다.
P1은 `attempt.rNaCh1sO/recovery.z7tZrFVz`의 별도 driver로 설정 경로만 수정해
완료 checkpoint의 추출·게시를 다시 실행했다. 앞선 mount 복구 실패도
`recovery.f4k4rzVZ`에 보존했다. 원래 동결 source/학습 결과는 변경하지 않았다.
P3는 원래 worker와 설정으로 GPU1에서 preflight PASS 후 본 학습에 진입했다.
세 지역 게시 완료 후 현재 recovery의 `completion_check/`에서 브라우저 검사를 실행한다.
자세한 원인과 실행 상태 확인 기준은 `ISSUES_ko_v1.md`에 기록했다.

## 코드 경로

- Config: `configs/phd/region_weight_v1/prior_0005_v1.json`
- 준비/실행/등록: `scripts/phd/prior_weight_followup_v1/`
- 런타임: `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`
- 브라우저: `sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e`
- 새 데이터 계보를 설명적 개발 실험으로 유지하며 scientific_verdict는 null이다.
