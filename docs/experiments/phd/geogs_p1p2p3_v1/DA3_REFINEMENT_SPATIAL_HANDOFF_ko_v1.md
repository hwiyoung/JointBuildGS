# DA3 입력 편차와 refinement 공간 진단 인계

2026-09-10 · `scientific_verdict: null`

사용자 요청은 “DA3의 어떤 오류가 어느 영역의 refinement를 얼마나 개선·악화시키는지 확인”이다. [계획](DA3_REFINEMENT_SPATIAL_PLAN_ko_v1.md)에 따라 기존 공통 Anchor8k와 6조건 final30k raw512를 같은 UAS 참조점에서 분석했고 [실제 결과](DA3_REFINEMENT_SPATIAL_RESULTS_ko_v1.md)를 작성했다. **공간 대응 측정은 완료됐고 DA3 단독 인과 기여량은 아직 측정하지 않았다.** 새 학습·입력 보정·정합·원서비스 변경은 없다.

외부 task는 `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다. 출력은 `evaluation/da3_refinement_spatial_v1/`이며 동일점 지도 보완물은 그 아래 `strict_correspondence_v1/`에 있다. 두 실행 receipt는 PASS/exit0, 각각 script·config·명령·입력/출력 SHA·도구 버전을 보존한다. whole P/R/F1와 오류구간별 보존·회복 CSV, 원 참조 ID를 가진 paired NPZ3개, 고정 단면3개, 동일점 지도/6조건지도6개, cohort 그림과 대표 타일 CSV를 제공한다.

P1 높은 DA3 목표 집합에서 prior 완화는 기존 근접점 보존을77.18→40.85%로 낮추면서 처음 먼 점 회복을12.71→47.16%로 높였다. P2 목표가±0.5m 이내인 처음 먼 점은 두 조건 모두약84.5% 회복했고, 목표가+1m를 넘는 처음 근접점은 보존50.30→12.88%다. P3 목표가−1m보다 낮고 처음 먼 점의 거리변화 중앙값은원설정+0.818m, 완화+1.709m다. 높은 DA3 편차에도 구조가 유지되는 P3 타일 반례도 포함했다. **완화는 prior 깊이.005→.0005이고 DA3 가중치 감소가 아니다.** 비율은0.5m 참조점 근접률이며 건물/면적 보존율이나 F1이 아니다.

주의할 해석은 다음과 같다.

- P1/P2/P3 분석 사진은 각각1/14/8장이고 strict 참조점은전체의39.77/47.07/26.05%다. 외부 가림·다른 사경 영상·벽/하부 표면의 입력 정확성을 인증하지 않는다.
- DA3 편차·초기 상태·최종 오차가 같은 UAS를 공유한다. 원인과 상관을 구분한다. 배치 척도 파손은 확정하지 않는다는 기존 [감사 정정](DA3_AUDIT_INTERPRETATION_CORRECTION_ko_v1.md)을 유지한다.
- main 셀 지도는 strict DA3와 모든 높이의 결과를 집계한 맥락용이다. 본 대응 분석은 `strict_correspondence_v1/`과 원점 cohort/NPZ를 사용한다. 원 로그 셀상관은 사용하지 않는다.
- 동일 Anchor 복원 직후 상태는 확인했지만 이후 exact trajectory와 독립 반복 변동은 확보하지 못했다. 실현 DA3 가중치도 조건별 약.043~.05로 다르다.
- 같은 해상도에서도 expected 렌더 깊이·관측 앞표면·TSDF 추출은 다른 연산이다. P3 내부 띠 감소를 DA3 효과로 바로 귀속하지 않는다.

후속 인과 검증은 같은 complete Anchor에서 DA3 on/off의 동일22k refinement다. 실제 DA3 항을 끄고 first-step weight0을 검사해야 한다. `--lambda_da_depth 0`만으로 dynamic controller를 우회하지 못한다. UAS로 mask/척도/유리한 학습설정을 선택하지 않는다. 이 진단에서 새로운 재판단 알고리즘을 구현하거나 우위를 판정하지 않았다. 이전 SfM-noAnchor fresh 재시도 상한·실패 결과·뷰어는 그대로 보존한다.
