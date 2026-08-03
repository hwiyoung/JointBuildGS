# P2 C2W C1 baseline audit Return v1

- handoff_id: `P2-W2C-C1-BASELINE-AUDIT-v1`
- task_id: `P2-C1-BASELINE-AUDIT-v1`
- return state: `DIAGNOSTICS_COMPLETE_SELF_REFERENCE`
- source commit: `ae8288b2206e40949050ae7967c411c7b034449d`
- offered commit: `b4a40b8d6f2d481e8dc26e4564f67222bf79a620`
- accepted commit: `0da711bd4df45ef57009a8527416ac3d91c77d3a`
- scientific_verdict: `null`

C1의 기존 Roofer CityJSONSeq 한 개에 pinned val3dity를 1회 실행했고 G2는 PASS했다.
그러나 development 51동 모두가 이 한 output을 공유하므로 51개의 독립 건물 모델이
성공한 것은 아니다. self-reference G3 후보는 0/51, G4 후보는 2/51이며 공식
G3/G4/PASS는 `null`이다.

한국어 설명서는 `docs/experiments/p2/c1_baseline_audit_v1/TECHNICAL_RETURN_REPORT_v1.md`,
compact manifest는 `artifacts/manifests/p2/c1_baseline_audit_v1/technical_result_manifest_v1.json`이다.
reconstruction/Roofer 재실행, validation/held-out 접근, 대용량 원본 재해시는 모두 0회다.
