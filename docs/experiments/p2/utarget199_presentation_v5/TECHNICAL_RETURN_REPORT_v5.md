# U_target=199 full-resolution presentation v5 기술 Return

- task: `P2-UTARGET199-PRESENTATION-v5`
- artifact: `artifact://JointBuildGS/phase-payloads/p2/utarget199_presentation_v5/P2-UTARGET199-PRESENTATION-v5`
- technical state: `COMPLETE_199_FULL_RESOLUTION_PAGES_AND_GALLERY`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

## 산출물

- 199동 전부에 대해 기존 C1/C2 contract sheet와 C3-1/C3-2 sheet를 원본 pixel
  크기로 유지한 full-resolution PNG 199장과 HTML gallery를 생성했다.
- source에서 `MISSING`, `UNASSOCIATED`, `NOT_RUN`으로 표시된 행을 삭제하지 않았다.
  C4와 C5는 이 산출 시점에 각각 `NOT_RUN`으로 남겼다.
- 기존 C1/C2/C3 597행 metric JSONL은 byte-for-byte 재사용했다. source와 재사용본의
  SHA-256은 모두
  `13728f8e56ddfa502fea9d6345bb38b29931737f8e33d73d40b1b3b8171f6c8e`다.
- 기존 597행 acceptance-gate CSV도 source와 재사용본이
  `f99f931ffde7943f65cabcdd682ee03ec00fe095945af6e5e609342ace748bd3`로 같다.

## reference와 binding

597개 행마다 exact metric-row, sealed output 또는 명시적 output-null reason,
current-UAS reference ledger, building-local UAS support, 2022 LoD2 files, support
record와 evaluator config hash를 기록했다. C1은 `SELF_REFERENCE_DIAGNOSTIC`,
C4-vs-LoD2 열은 `PRIOR_RELATED_REFERENCE_DIAGNOSTIC_ONLY`로 분리했다.

LoD2 상태는 2024 RGB 투영 가능성, current-UAS cell 수, LoD2 RoofSurface에 +45.7 m
datum shift를 적용한 뒤의 absolute Z residual을 공개된 rule로 계산했다. 분류 수는
`UNCHANGED_CONFIDENT=47`, `TEMPORAL_CHANGE_SUSPECTED=6`,
`REFERENCE_ID_ALIGNMENT_UNCERTAIN=146`이다. support가 부족하거나 모호하면 마지막
상태로 보수적으로 남겼으며 이 분류는 scientific verdict가 아니다.

## 실행 경계

이 task는 sealed result 조립과 reference diagnostic만 수행했다. Roofer, G2, GS
training, C4/C5 실행 또는 기존 metric 재계산은 수행하지 않았다. 사람 검토 전까지
우열·사용 가능성·일반화 결론을 내리지 않는다.
