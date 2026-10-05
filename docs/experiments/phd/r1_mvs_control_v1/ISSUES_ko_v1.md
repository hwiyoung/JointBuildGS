# R1 대조군 준비 이슈

- `scientific_verdict: null`
- R1P-001 / SCOPE: 이번 작업은 보정·보존·유보 관찰 구역 초안 및 CPU 입력/설정 준비다. 학습·수동 가중치는 아직 실행하지 않는다.
- R1P-002 / INPUT_LINEAGE: 기존 COLMAP MVS는 평가 카메라가 포함된 생산 계보다. 새 split은 개발용이며 독립 성능 검증을 뜻하지 않는다.
- R1P-003 / LABEL_ROLE: 입력의 prior/MVS 일치는 정확성 증명이 아니다. C1/S1/U1은 관찰 후보이며 미표시 부분은 미검토다. 기존 P1/P3의 R1–R6 수동 마스크 번호와 새 장면 R1을 혼동하지 않는다.
- R1P-004 / NEW_SCENE: 새 영역·영상 목록에는 새 초기 입력과 Anchor8k가 필요하다. 기존 P1/P3 checkpoint는 이어 쓰지 않는다. 실제 GPU 메모리/gradient/restore 검증은 이후 실행 단계에서 확인한다.
- R1P-005 / RESOLVED_SOURCE_MEMBERSHIP: 기존 P3의 `0046_D`를 초기에 열람했으나 새 R1 split에서는 평가 영상이었다. split을 바꾸지 않고 인접 학습 영상 `0045_D`로 S1/U1의 최종 초안을 작성했다. `observation_draft_v1.json`이 `preparation_v1.json`의 미구현 observation_draft 항목만 대체한다. CPU 입력은 해당 항목을 사용하지 않았으며 변경하지 않았다. 평가 영상의 초기 열람 사실과 기존 MVS 생산 계보 때문에 이 split을 미접촉 검증셋으로 주장하지 않는다.
- R1P-006 / OPEN_CONTEXT: 초기 기하는 R1+객체축 방향 25m 문맥 범위이고 RGB loss는 원래 전체 프레임이다. 원경/경계 불일치와 실제 구역별 loss 기여를 GPU 사전 점검에서 확인해야 한다. 입력 지지 영상 수를 실제 gradient 기여 영상 수로 보고하지 않는다.
- R1P-007 / OPEN_CASE_COMPLETENESS: S1은 prior/MVS가 함께 일치하는 보존 후보다. prior가 맞고 MVS가 틀린 어려운 보존 사례까지 확인한 것은 아니다. U1의 큰 차이도 실변화로 분류하지 않는다. 독립 현재 기하로 정확성과 변화 여부를 확인하는 단계가 남아 있다.
