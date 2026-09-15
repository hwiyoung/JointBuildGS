# P1 입력 깊이 가시화 이슈

`PHD-P1-MVS-INPUT-VIS-v1` · `scientific_verdict: null`

| ID | 상태 | 관찰과 조치 |
|---|---|---|
| VIZ-001 | DOCUMENTED | 현재 MVS 입력에는 검증된 confidence map이 없다. finite-positive 입력 존재 지도를 confidence로 부르지 않는다. |
| VIZ-002 | DOCUMENTED | MVS nearest native 조회와 원 prior 반 픽셀 ray가 다르다. 원값을 유지하고 잔차를 저장 픽셀별 입력 차이 진단으로 표시한다. |
| VIZ-003 | CORRECTED_BEFORE_FINAL | 첫 후보 B/C는 투영 bbox 안이지만 기존 P1 평가 prism 밖이었다. native ray 역투영으로 범위를 확인하여 B를 평가 안의 지면으로 옮기고 C는 주변 학습 문맥의 지붕 대조라고 명시했다. 초안 attempt.W0k3Kg는 보존했다. |
| VIZ-004 | DOCUMENTED | 첫 시점은 현행 PGSR graph에 이웃이 없다. 직접 depth 표시는 가능하지만 다시점 검증 완료로 해석하지 않는다. |
| VIZ-005 | CORRECTED_BEFORE_FINAL | 독립 리뷰에서 native ray 표본 수가 실제로는 nearest 조회 후 RGB 격자 표본 수라는 점을 지적했다. 최종 receipt 이름을 valid_rgb_samples_of_native_rays로 수정했다. |
| VIZ-006 | DOCUMENTED | 실제 MVS 생성 이웃·평가 영상 독립성 및 원 datum의 기존 한계는 유지한다. 입력 가시화는 기하 정확도나 현재성 평가가 아니다. |
