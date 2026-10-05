# 새 세션 시작 — 국소 상보 가중 refinement 계획 검토와 실행

- 작성일: 2026-09-10
- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- 상태: `PLAN_REVIEW / MAIN_EXPERIMENT_NOT_STARTED`
- scientific_verdict: null

**현재 세션은 계획 정리로 마무리한다. 실험은 새 세션에서 진행한다.** 사용자는 새 실험의 실행 의사와 완료 시각 제한 해제를 밝혔지만, 현재 세션에서 바로 실행하라는 뜻이 아니었다고 정정했다. 이 문서가 있는 것만으로 자동 실행하지 않는다.

## 현재 계획

기존 P1/P2/P3의 complete Anchor8k를 재사용한다. 기존 전역 제어의 18개 결과를 대조군으로 두고, 새 국소 상보 가중을 적용한 18개 refinement를 계획한다. 새 실험은 지역별 prior 전역 계수 `.005/.0005/0` × 구조 보호 `native/release`의 6조건이다. O/X 네 분류는 평가 층이며 학습 횟수를 네 배로 늘리지 않는다.

같은 ray의 두 유효 target 차이 `|prior depth − DA3 depth|`로 국소 배율을 정하고, prior loss에 `1−a`, 영상 depth loss에 `a`를 곱한다. 기존 전역 lambda와 source별 유효 pixel 수 분모는 별도로 남는다. 고정 Anchor·DA3 입력에서 가중의 역할부터 비교하며, depth 교체나 추가 normal·다중 시점 모듈은 이번 18개에 포함하지 않는다. 보호 유지·해제도 별도 요인이다.

**문턱은 본 실험용으로 아직 확정하지 않았다.** 고정 `tau0=0.5m, tau1=2m`는 검토할 후보이며, prior/영상의 정오나 노이즈 경계라는 뜻이 아니다. 입력 분위수로 얻은 약 `30.83m/138.23m`는 입력 진단과 아래 기술 probe에서 사용한 값이다. 이를 본 실험의 최종 설정으로 자동 재사용하지 않는다.

먼저 읽을 자료는 다음이면 충분하다. 과거 탐색 문서를 모두 읽거나 오래된 문구 목록을 다시 점검할 필요는 없다.

1. [실험계획](EXPERIMENT_PLAN_ko_v1.md): 목적, loss, 비교 조건, 미확정 사항, 평가·기각 조건.
2. [기여 검토](PHD_CONTRIBUTION_REVIEW_ko_v1.md): 기존 설계와 겹치는 부분, 원인 가설, 방법 신규성과 검증 기여의 경계.
3. [재사용·자원 근거](RESOURCE_AND_REUSE_REVIEW_ko_v1.md): 정확한 Anchor·기존 run 경로와 예산. 실행 시 이 파일과 실제 receipt를 대조한다.

AGENTS.md의 운영·보존·Docker 지침을 따르고 연구 헌장·DEC-P1-025는 역사 맥락으로 읽는다. 최신 사용자 연구 방향을 과거 E1–E6 프로그램으로 덮어쓰지 않는다. GT는 평가 전용이며 `scientific_verdict: null`이다.

## 현재 실제 작업 상태

본 실험 18개, 실행 큐, 새 full refinement·렌더·mesh 추출·실제 참조 기반 평가는 시작하지 않았다. 현재 이 작업의 실행 컨테이너·큐 프로세스도 없다.

현재 세션에서 범위를 넓게 해석하여 다음 준비·기술 검증을 이미 수행했다. 이는 본 실험 결과가 아니며 삭제하지 않고 보존한다.

- 봉인 입력·Anchor hash 확인과 train target의 차이 통계 계산. GT는 사용하지 않았다.
- 새 local loss의 CPU 검증 16개 통과, 원본 source의 별도 복사·패치.
- **P2 `.005 native` 한 조건에서 Anchor8k를 복원하고 iteration8001 한 step을 수행**했다. 본 실험의 22,000 step refinement가 아니다. 당시 사용한 문턱은 `30.826555252075195m / 138.23462524414063m`이다.
- 평가 코드의 합성 배열·삼각형 CPU smoke. 실제 참조 평가 및 전체 통합 검증은 미실행이다.

새 payload root:
`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`

- 입력 통계·결박: `contracts/input_binding.json`, `contracts/threshold_diagnostics.json`
- 실제 기술 검증: `preflight/P2_LC_D005_Pnative/probe_receipt.json`
- 별도 복사본: `source/`
- 구현 초안: 저장소의 `scripts/phd/local_complementary_refinement_v1/`

현재 `configs/phd/local_complementary_refinement_v1/experiment_v1.json`과 payload의 `contracts/experiment_v1.json`은 **분위수 정책을 쓴 준비·probe의 명세**다. 본 실험 명세로 확정된 파일이 아니다. 최종 문턱과 실행 명세는 새 버전으로 작성하여 이 계보를 보존한다. Queue·평가 연결 및 자원 gate 검토도 남아 있으므로 현재 초안을 바로 실행하지 않는다.

## 새 세션에 전달할 프롬프트

```text
JointBuildGS 국소 상보 depth refinement 실험을 이어가자.
저장소: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator

AGENTS.md와 다음 인계의 실험계획·기여 검토·재사용 근거를 읽어라.
docs/experiments/phd/local_complementary_refinement_v1/START_HERE_ko_v1.md

먼저 미확정인 문턱·loss reduction·기존 결과 재사용·평가와 자원 명세를
실험계획에 맞춰 구체화한 뒤, 구현 보완·검증·실행·평가를 진행하라.
기존 complete Anchor8k와 대조군18개를 재사용하고 새 국소 상보 가중만
P1/P2/P3 × prior 계수 .005/.0005/0 × native/release로 비교한다.
전체18개를 완료까지 진행할 수 있으며 아침 종료 시각 제한은 없다.

현재 configs의 분위수 설정과 이미 수행한 P2 1step probe는 준비 이력이다.
0.5m/2m는 검토 후보이며 본 실험 문턱이 확정되었다고 가정하지 말라.
새 명세를 별도 버전으로 남기고 실제 실행은 그 명세와 결박하라.
현재 run queue·평가 코드는 검증이 끝나지 않은 초안이다.

박사학위의 문제 차별성·원인 설명·방법 신규성·검증 기여를 구분하라.
기존 방법의 성공과 새 방법의 악화, 같은 부위의 수정·손상을 함께 보고하라.
현재 첫18개에는 평균 배율 전역 대조·controller replay·반복이 없으므로
공간 배분 고유 효과나 작은 차이의 재현성까지 확정하지 말라.
GT는 평가 전용, scientific_verdict는 null이며 기존 코드·입력·결과·
진행 작업·서비스는 보존한다. 프로젝트 도구는 Docker로 실행한다.
```
