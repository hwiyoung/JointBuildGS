# Fusion W1 WIP disposition — 2026-07-30

## 결론

Fusion W1 WIP는 폐기하거나 그대로 방치하지 않았다. 현재 상태는
**기술적으로 재현 가능한 handoff, 과학적으로는 미승격**이다.

- 재사용 가능한 코드·설정·테스트는 현재 의미 구조로 통합하고 Docker gate를 통과시켰다.
- 완료 산출물은 외부 artifact storage에 유지하고 선언된 45개 파일을 다시 해시했다.
- 완료 receipt가 가리키는 당시 소스 40개는 별도 source-lock v4에 정확한 바이트로 동결했다.
- superseded V2의 수동 QA 문서 1개는 Git 정본으로 올리지 않고, 복구 검증된 원 WIP snapshot에만 보존했다.
- 어떤 항목에도 과학적 판정이나 정본 evidence 승격을 부여하지 않았다.

기계 판독 정본은
[`fusion_w1_wip_disposition_20260730.json`](../../../artifacts/manifests/fusion_w1_wip_disposition_20260730.json)이다.

## 왜 세 종류로 나눴는가

| 구분 | 검토 엔트리 | 처리 | 의미 |
|---|---:|---|---|
| C1 — 공용 구현 | 11 | 현재 구조에 통합 | projection, TIN, 정책처럼 다른 실험도 재사용 가능한 코드 |
| C2 — Fusion 연속 작업 | 35 | 의미 경로로 재배치 후 gate | 현재 코드로 계속 개발할 수 있는 config, wrapper, test |
| C3 — receipt/result 결박 | 9 | 과거본 source-lock + 현재 연속 작업 분리 | 완료 결과의 당시 바이트를 현재 코드로 몰래 대체하지 않음 |

55는 staged/unstaged/untracked의 검토 레이어 수다. 원 checkout의 고유 변경 경로는 42개다.

## 복구와 원본 보존

원 `exp/fusion-w1` checkout의 상태는 작업 전 다음과 같이 동결했다.

- staged 19, unstaged 20, untracked 16, 고유 경로 42
- 외부 snapshot: `wip-snapshots/fusion_w1/20260730-pre-work-readiness`
- receipt: [`fusion_w1_local_wip_snapshot_20260730.json`](../../../artifacts/manifests/fusion_w1_local_wip_snapshot_20260730.json)
- disposable clone 복구 rehearsal: status byte-identical, `git diff --check` 통과

이 snapshot은 복구 수단이지 연구 정본이나 durable backup이라는 주장은 아니다.

## 완료 산출물의 상태

외부 payload를 직접 재해시한 결과는
[`fusion_w1_completed_visuals_20260730.json`](../../../artifacts/manifests/fusion_w1_completed_visuals_20260730.json)에 있다.

| 집합 | 완료 receipt | 검증 출력 | 상태 |
|---|---:|---:|---|
| Dense qualitative V5 | 1 | 35 | integrity verified, unpromoted |
| A′ panel V6 | 1 | 1 | integrity verified, unpromoted |
| A′ panel V7 | 9 | 9 | integrity verified, unpromoted |
| 합계 | 11 | 45 | scientific verdict 없음 |

완료 결과의 구현 provenance는
[`fusion_w1_receipt_source_lock_20260730.json`](../../../artifacts/manifests/fusion_w1_receipt_source_lock_20260730.json)이 가리키는 source-lock v4가 소유한다.
현재 worktree 파일을 완료 당시 소스로 대신 사용하면 안 된다.

## 재현성 gate

| Gate | 통과 | 실패 |
|---|---:|---:|
| 공용 projection·TIN·활성 진입점 정책 | 21 | 0 |
| Dense qualitative V2–V5 wrapper | 56 | 0 |
| A′ panel V6–V7 wrapper | 20 | 0 |
| Fusion readout wrapper | 60 | 0 |
| 합계 | 157 | 0 |

이 gate는 현재 `Dockerfile`로 새로 빌드한 정본 `jointbuildgs:dev`에서 같은 10개
`tests.fusion_w1` 모듈을 한 번에 실행해 확인했다. 재현에 필요한
`laspy[lazrs]==2.6.1`과 `cjio==0.10.1`은 Dockerfile과 `requirements.txt`에 모두
명시했다. 활성 qualitative V3 config의 `locked_inputs.requirements.content_migration`은
기존 requirements 해시와 현재 해시를 함께 기록하며, 완료 receipt 당시 바이트는 source-lock
v4가 계속 소유한다.

readout에서는 단순 해시 갱신을 하지 않았다. 과거 trainer는 source-lock의 정확한 바이트로 검증하고,
현재 실행 파일은 JSON·CSV·Python에 허용된 경로 치환과 치환 횟수가 모두 맞을 때만 통과한다.

## 승격하지 않은 항목

`fusion_w1_dense_baseline_qualitative_v2_manual_qa_20260728.md`는 V2 payload가
superseded cleanup 계약으로 제거된 뒤 작성된 수동 검토 문서다. 이를 현재 보고서로 승격하면 존재하지 않는
payload에 권위를 부여하므로, 외부 WIP snapshot에서만 복구 가능하게 유지했다.

## 다음 작업 규칙

1. 현재 코드 수정은 새 task/config/receipt로 진행한다.
2. 완료 V5–V7을 재현할 때는 source-lock v4의 정확한 소스를 사용한다.
3. 외부 payload가 없는 ChatGPT Work checkout에서는 코드·문서 검토만 가능하며 결과 재생성을 주장하지 않는다.
4. 과학적 정본 승격은 별도 승인 문서가 생길 때만 수행한다.
