# GeoGS 지붕 편향 진단 — GEOGS-ROOF-BIAS-20260921

사용자 발주 범위의 GeoGS 공식 방법 진단이다. E1–E6의 새 조건이나 확증 실험으로 승격하지 않는다. `scientific_verdict: null`.

외부 납품 폴더: `../JointBuildGS-artifacts/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921`.

- 실행 상태: `status.json`; 독립 감독 프로세스: `logs/supervisor.log`.
- 납품: `report.md`, `tables/table_A.csv`부터 `table_D.csv`, `figures/figure_1_*.png`부터 `figure_4_*.png`.
- 모델: `conditions/<조건>/model/point_cloud/iteration_8000/point_cloud.ply` 및 `iteration_30000/point_cloud.ply`.
- 재현 드라이버: `scripts/phd/geogs_roof_bias_v1/`와 외부 폴더의 실행 당시 복사본.
- 문제·예외: [ISSUES.md](ISSUES.md) 및 외부 `logs/issues.jsonl`.

현재 보고서와 표는 실행 상태에 따라 갱신된다. `PENDING`과 빈 수치는 측정값이 아니다. 모든 조건 종료 후에도 복구 메시와 제공 초기화의 차이, 논문 기대값 부재, 실제 렌더 기여도 미측정은 해석의 한계로 남는다.

<!-- END GEOGS-ROOF-BIAS-20260921 -->
