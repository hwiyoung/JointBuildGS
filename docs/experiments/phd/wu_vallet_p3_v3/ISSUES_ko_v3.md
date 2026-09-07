# Wu–Vallet P3 v3 이슈

`scientific_verdict: null` · 2026-09-07

| ID | 상태 | 문제·원인 | 조치·남은 범위 |
|---|---|---|---|
| WV3-001 | FIXED_IN_ADDITIVE_V3 | v2가 작은 CHANGED 면을 SINGLE로 바꾸고 새 SINGLE을 재허용. 기존 시험도 재유입을 기대함. | v2 보존. v3에서 filtered/raw_single 분리, 새 회귀시험 10개 PASS. 직접 비교에서 4,333점 제외, old 마스크 동일. |
| WV3-002 | RECOVERED | 평가 중 연결군마다 NPZ를 다시 압축 해제하여 실행 지연. | 본인 평가 컨테이너만 중단. 배열 일괄 로드, 별도 평가 snapshot/중단 receipt 보존. 봉인 후보·해시 불변. |
| WV3-003 | OPEN_REPRODUCTION_LIMIT | 저자 코드 비공개/404, PSMNet·재학습·다중 시점 전방교차와 다른 COLMAP depth 입력. | 입력 계보 감사와 필터 영향을 분리. 원저자 성능/원문 완전 재현 주장 보류. |
| WV3-004 | OPEN_DIAGNOSTIC_LIMIT | raw_single이 가림·미검출·피복 미확정을 포함. 큰 참조 편차점도 연결 면으로 남음. | 원시 SINGLE과 탈락 CHANGED를 분리; CHANGED만 추가하는 민감도와 고정 SOR 별도 실행. 참조 거리로 알고리즘을 변경하지 않음. |
| WV3-005 | OPEN_REFERENCE_LIMIT | UAS 헤더 EPSG:32632, 작업 EPSG:25832. datum/epoch 및 실제 관측 차이를 미보정. | 동일 고정 참조를 사후 진단에만 사용. >2m를 오류/변화 정답 또는 절대 정확도로 해석하지 않음. |
