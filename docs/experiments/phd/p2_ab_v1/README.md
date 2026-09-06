# P2 판단·재구성 병행 개발

2026-09-06 사용자 요청으로 A·B 독립 설계와 구현, 같은 P2의 개발 실험, 분리·통합 검증을 수행했다. 기존 r3.7 문서와 입력·결과는 보존했다. `scientific_verdict: null`.

먼저 [통합 기술 결과](TECHNICAL_RETURN_ko_v1.md)를 읽는다. 이어서 [A 판단 설계](A_DESIGN_ko_v1.md), [B 재구성 설계](B_RECONSTRUCTION_DESIGN_ko_v1.md), [공통 샘플](SAMPLE_CONTRACT_ko_v1.md), [C 평가 계약](C_PROTOCOL_ko_v1.md)으로 계산과 범위를 확인한다.

현재 결과는 제안 범위 판단·제약 재구성의 추가 이득을 확인하지 못했다. 기술 실행과 수치 검증, 미완성 연구 가정과 확증의 경계를 결과 문서에 구분했다.

[정성 비교 뷰어](http://127.0.0.1:8893/PHD-P2-AB-C-v2/viewer/) · [통합 artifact manifest](../../../../artifacts/manifests/phd/p2_ab_v1/technical_result_manifest_v1.json)

실행은 `scripts/phd/p2_ab_v1/`의 Docker 드라이버와 `configs/phd/p2_ab_v1/`에 기록한다. 기존 run ID가 있으면 중단하며, 과거 실행의 정확한 코드는 외부 source snapshot으로 보존한다. 정본 E1–E6·역사적 C 계보 및 공식 판정 계약은 변경하지 않았다.
