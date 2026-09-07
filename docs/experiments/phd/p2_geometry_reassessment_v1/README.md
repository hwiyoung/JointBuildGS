# P2 기하 재분석 — 정성적 개선과 전체 F1 감소의 구분

2026-09-09 · `PHD-P2-GEOMETRY-REASSESSMENT-v1` · `scientific_verdict: null`

**P2의 prior 깊이 가중치 완화는 외관뿐 아니라 일부 건물 기하도 개선했다. 첨부와 같은 512 결과에서는 예측 표면의 참조 근접도와 precision@0.5m도 좋아진다. 전체 F1 감소를 건물 기하의 일괄 악화로 해석한 이전 답변을 정정한다.**

같은 참조 점의 거리 자료를 다시 집계하면, 지면 높이와 겹치는 Z=[−44,−42)m 층이 전체 순 recall 감소의 약 80%를 구성한다. 이 수치는 F1 감소의 기여율이나 지면 의미 분류 결과가 아니다. 상단 면 개선과 주변 높이·피복 악화, 반복 지붕의 잔여 차이를 함께 확인했다.

- [재분석 보고서](REASSESSMENT_ko_v1.md)
- [이슈·기술 검증](ISSUES_ko_v1.md)
- [전체 지표 재계산](analysis/global_recomputed.csv), [전체 높이층](analysis/height_strata.csv), [동일 참조의 개선·악화](analysis/paired_reference.csv), [높이별 recall 기여](analysis/paired_reference_height.csv), [전체 XY 셀](analysis/xy_cells.csv)
- [실행 계보·입력 SHA·검사 결과](analysis/receipt.json), [독립 합계 검증·민감도](figures/validation.json)
- [설정](../../../../configs/phd/p2_geometry_reassessment_v1/analysis.json), [분석 스크립트](../../../../scripts/phd/p2_geometry_reassessment_v1/analyze.py), [합계·그림 검증](../../../../scripts/phd/p2_geometry_reassessment_v1/validate_and_present.py), [Docker 실행](../../../../scripts/phd/p2_geometry_reassessment_v1/run.sh)

기존 결과·문서는 보존했다. 새 학습·장면 렌더·메쉬 추출·정합·거리 질의 없이, 저장된 평가 배열을 재집계하고 통계 그림만 생성했다. 기존 그림의 편집본이 아니라 원 거리 표의 새 시각화다. 실행 스크립트는 출력이 이미 있으면 중단하여 덮어쓰기를 막는다.
