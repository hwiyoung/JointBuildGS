# P0 input-substitution audit evidence

완료된 P0 산출물의 의미적 정본 위치다. `w1`부터 `w4`까지 실행 흐름을 따르고, 각 work package 안에서 `reports`, `tables`, `figs`로 산출물 역할을 구분한다.

- `w1-input-diagnostics/`: 입력 준비와 진단
- `w2-reconstruction-audit/`: 재구성 비교와 튜닝 audit
- `w3-quality-integration/`: 품질 지표, 원인 진단, canonical 통합
- `w4-gate-population/`: G1 모집단과 no-points 보강
- `design-and-provenance/`: 사전 설계와 출처 계약

원본 117개 파일은 `phases/p0-audit/docs/`에서 byte-for-byte 이동했으며, phase 실행 이슈는 `phases/p0-audit/issues.md`가 소유한다.
