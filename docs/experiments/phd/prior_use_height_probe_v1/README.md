# Prior-only height-use probe

현재 영상과 원 ALS 표본을 사용하여 **원후보 사진 점수 → 남는 사용 판단 문제 → 이산 높이 대안 계산 → 조건부 판단 변화**를 대조한 비확증 개발 실험이다.

- [결과와 방법 설계에 반영할 내용](TECHNICAL_RETURN_ko_v1.md)
- [측정 전 설계와 v2 수정](DESIGN_ko_v1.md)
- [48개 감도 설정 전체 결과](SENSITIVITY_ko_v1.md)
- [v1 관측 선정 실패 기록](ISSUES_ko_v1.md)
- [외부 payload 위치와 해시](../../../../artifacts/manifests/phd/prior_use_height_probe_v1/technical_result_manifest_v1.json)

현재 가림·정합 불확실성·연속 기하 범위를 확인하지 않은 구성요소 실험이다. 조건부 지지를 실제 `PRIOR`로 승격하지 않으며 `full_current_use_action`과 `scientific_verdict`는 `null`이다. 기존 r4 전체와의 성능 비교나 GS 재구성 실험은 포함하지 않는다.
