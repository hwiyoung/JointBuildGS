# P2 W2C C3 development Stage 3 v1

## Handoff metadata

- handoff_id: `P2-W2C-C3-DEVELOPMENT-STAGE3-v1`
- task_id: `P2-C3-DEVELOPMENT-STAGE3-v1`
- phase: `P2 development technical evaluation`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT`
- packet_version: `v1`
- source_commit: `48d0f359c56b5fb8e958a5b84a72119649205102`
- target_branch: `main`
- research canon: `C1C5_CANON_v2` through `DEC-P1-011`
- result contract: `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- created_at: `2026-08-03`
- user_approval: `GRANTED_FOR_BOUNDED_C3_DEVELOPMENT_EXECUTION`
- scientific_verdict: `null`

## 목적

이미 완료된 C3 seed-0 30k 체크포인트를 다시 학습하지 않고, 개발 51동에 대해
`S_extracted -> P_Roofer -> H_LoD2 -> G0/G1 기술 결과표`를 실제로 생성한다.
건물 하나씩 분리됐는지는 component multiplicity로 먼저 드러내며, 여러 건물이
한 성분을 공유하면 이를 성공 건물 수로 해석하지 않는다.

## 입력

| 입력 | 고정 식별자 | 역할 |
|---|---|---|
| R4 C3 `final.pt` | 105,664,220 bytes; SHA-256 `bec692b0040b3b2f9226389cfd6d380f0da148b5db6f4912fe68e9d72dbb43f9` | 저장된 Stage-2 그룹과 Gaussian 중심/semantic/opacity 읽기 |
| R3 개발 score cells | 10,868,613 bytes; SHA-256 `de7c02e2a286fa05c34301aae9de625637cf6fb8c07b5f2969141fd20b0d5a59` | 모든 C3 geometry와 `R_derived`를 봉인한 뒤 51동 ID에 평가용으로 연결 |
| C1/C2 동결 Stage 3 설정 | `configs/p2_baselines/c1_c2_feasibility_pilot_v1/pilot_v1.json` | 동일 1 m 격자, footprint-free component, LAS 2/6, Roofer image/args |

R4 체크포인트는 닫힌 attestation과 byte count를 재사용하고 전수 재해시하지 않는다.
R3 score-cell 파생물만 geometry 봉인 뒤 한 번 읽고 해시한다. R1 15.7 GB 입력,
`Images.zip`, `OPF.zip`, 원본 MVS는 열거나 해시하지 않는다.

## 실행 범위

1. 정확한 R4 checkpoint 구조를 `it=30000`, primitives `406337`, Stage-2 groups
   `812`, grouped primitives `319698`로 fail-closed 확인한다.
2. 저장된 group ID를 재계산하지 않고, semantic 1/2를 LAS class 6, semantic 3을
   class 2로 바꾸며 semantic 0은 제외한다.
3. 동결 1 m 셀에서 building max-Z, terrain min-Z와 셀 중심 XY를 사용한다.
   opacity threshold는 새로 만들지 않고 분포만 진단값으로 기록한다.
4. score/reference를 열기 전에 모든 C3 component, LAS, `R_derived`와 Roofer job을
   add-once로 봉인한다.
5. 그 뒤에만 개발 51동 score-cell을 열어 component association과 건물 공유 수를
   기록한다.
6. 연결된 고유 component에 대해서만 Roofer를 한 번씩 실행한다. 완료 marker가
   검증되면 재실행하지 않는다.
7. 51행 `development_technical_results_v1.jsonl`과 `stage_counts_v1.csv`를 만든다.
   G0/G1만 기술 진단으로 채우고, G2/G3/G4/`PASS_usable`은 `null/PENDING`으로 둔다.

## 실행 금지

- C1/C2 재실행 또는 결과 수정
- C3 재학습, semantic 재추론, common MVS 재생성
- C4/C5, validation 11동, held-out 10동, Fusion W1, `R_ext`
- GT footprint, LoD2 RoofSurface/Z/roof type/semantic label을 geometry 생성에 사용
- opacity나 품질 결과를 본 뒤 parameter 변경 또는 quality-driven retry
- G0/G1 행 수를 독립 건물 성공 수 또는 `PASS_usable`로 표현

## 실행 명령

Experiment Host의 clean accepted checkout에서만 다음을 실행한다.

```bash
bash scripts/p2/c3_development_stage3_v1/run_stage3_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  48d0f359c56b5fb8e958a5b84a72119649205102 \
  P2-C3-DEVELOPMENT-STAGE3-v1
```

## 필수 결과

- external namespace:
  `artifact://JointBuildGS/phase-payloads/p2/c3_development_stage3_v1/P2-C3-DEVELOPMENT-STAGE3-v1/`
- component multiplicity와 건물별 association
- 고유 component별 exact LAS, `R_derived`, Roofer output/log
- 개발 51행 기술 결과와 단계별 집계
- 실행 횟수, 중복 방지, 입력 read/hash 횟수
- 한글 기술 보고서와 Return Packet
- `scientific_verdict: null`

## 중단 조건

- checkout/source/receipt/입력 identity 불일치
- checkpoint 구조 수 불일치
- geometry 봉인 전 score/reference 내용 read
- 기존 task namespace에 불완전하거나 모순된 실행 흔적 존재
- validation/held-out/C4/C5 또는 금지 입력이 필요함
- 새로운 과학 기준이나 threshold 결정이 필요함

## 완료 기준

Roofer 작업과 51행 G0/G1 기술 결과표가 add-once로 닫히고, 건물별 분리 여부가
component multiplicity로 명시되며, 기술 Return과 `200-verified` 또는 원인 있는
`200-blocked`, direct-child `300-closed`가 push되어 writer가 Work Host로 돌아온다.

## Return packet

`docs/handoffs/returns/P2_C2W_C3_DEVELOPMENT_STAGE3_RETURN_v1.md`
