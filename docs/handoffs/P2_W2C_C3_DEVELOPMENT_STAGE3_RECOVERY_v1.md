# P2 W2C C3 development Stage 3 recovery v1

## Handoff metadata

- handoff_id: `P2-W2C-C3-DEVELOPMENT-STAGE3-RECOVERY-v1`
- task_id: `P2-C3-DEVELOPMENT-STAGE3-v1`
- phase: `P2 development technical evaluation`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT_NOT_AUTHORITY`
- packet_version: `v1`
- source_commit: `9f223911a38cb40028e974d706dffa2f28937201`
- target_branch: `main`
- research canon: `C1C5_CANON_v2` through `DEC-P1-014`
- result contract: `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- created_at: `2026-08-03`
- user_approval: `NOT_YET_ACTIVATED`
- scientific_verdict: `null`

## 목적

앞선 handoff는 실행 래퍼의 accepted-receipt 연결 오류로 과학 payload를 읽기 전에
종료됐다. 이 recovery는 연구 설계나 입력을 바꾸지 않고 그 연결만 바로잡아, 이미
학습된 C3 seed-0 30k checkpoint의 실제 Stage 3 결과를 만든다.

필수 결과는 다음 다섯 가지다.

1. C3 component별 surface와 Roofer CityGML
2. 동일 development 51개 건물 전부의 G0--G4 상태와 평가 불가 사유
3. G0--G4 단계별 잔존 수와 최종 `PASS_usable` 수
4. 동일 건물에 대한 C1/C2/C3 정량 비교에 결합 가능한 C3 행
5. 실제 C1/C2/C3 Roofer 모델의 성공·경계·실패 정성 비교판을 만들 수 있는 출력

## 고정 입력과 재사용

- R4 C3 `final.pt`: 105,664,220 bytes,
  SHA-256 `bec692b0040b3b2f9226389cfd6d380f0da148b5db6f4912fe68e9d72dbb43f9`
- R3 development score cells: 10,868,613 bytes,
  SHA-256 `de7c02e2a286fa05c34301aae9de625637cf6fb8c07b5f2969141fd20b0d5a59`
- source attestation: handoff `P2-W2C-C3-DEVELOPMENT-STAGE3-v1`, closed commit
  `89342a92895c014bffd4495fe85ea8cdebfa2023`

Experiment Host는 위 closed receipt의 두 artifact identity를
`closed_attestation_reuse`로 인수한다. acceptance와 wrapper 검증에서 payload를
다시 해시하지 않는다. R1 15.7GB 입력, `Images.zip`, `OPF.zip`도 다시 해시하지 않는다.

## 변경점과 불변점

변경점은 실행 래퍼가 이 recovery packet과 recovery `100-accepted`를 읽는 것뿐이다.

다음은 그대로다.

- checkpoint, 저장된 Stage-2 group, semantic mapping, 1 m 격자
- development 51개 대상과 association 규칙
- unique component당 Roofer 1회 및 add-once terminal receipt
- shared/multi-component 건물의 G0/G1 `null` 격리
- G2/G3/G4/`PASS_usable`은 이번 기술 Stage 3에서 `null/PENDING`
- validation 11, held-out 10, C4, C5, Fusion W1, `R_ext` 미접근
- GT roof/height/type/semantic label의 geometry 생성 사용 금지

## 실행 순서

1. 이 DRAFT의 독립 검토 뒤 별도 commit에서만 승인 상태로 바꾼다.
2. Work Host가 immutable `000-offered`를 push한다.
3. Experiment Host가 remote packet·000을 pull 전에 검사하고 ff-only pull한다.
4. Experiment Host는 이전 closed receipt의 exact artifact identity를 재사용한
   `100-accepted`를 push해 writer ownership을 인수한다.
5. 다음 명령을 정확히 한 번 실행한다.

```bash
bash scripts/p2/c3_development_stage3_v1/run_stage3_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  9f223911a38cb40028e974d706dffa2f28937201 \
  P2-C3-DEVELOPMENT-STAGE3-v1
```

6. 결과·한국어 보고서·Return·200과 direct-child 300을 push하고 writer를 반환한다.

## 중단 조건

- checkout/source/packet/receipt identity 불일치
- closed attestation reuse 검증 실패
- checkpoint 구조 불일치
- geometry 봉인 전 score/reference read
- 기존 namespace의 모순되거나 불완전한 실행 흔적
- 금지 입력 또는 새 과학 기준이 필요한 경우

Roofer unit 하나의 실패·timeout은 기록하고 다음 unit과 51개 최종화를 계속한다.
`scientific_verdict`는 사람의 별도 판단 전까지 `null`이다.

## Return packet

`docs/handoffs/returns/P2_C2W_C3_DEVELOPMENT_STAGE3_RECOVERY_RETURN_v1.md`
