# 첫 단계 실험 — 관측 신뢰도 지도·허용 오차·충돌 지도 (PHD-STAGE1-CONF-TOL-CONFLICT-v1)

사용자 발주(2026-09-21)의 학습 없는 첫 단계 측정이다. E1–E6의 새 조건이나 확증 실험이 아니며
`scientific_verdict: null`이다. GeoGS 진단 실험(`GEOGS-ROOF-BIAS-20260921`)의 TUM2TWIN 단일 건물
장면(저자 예제 15시점)을 그대로 쓴다.

- 목적: 영상이 이 건물의 어디를 잴 수 있는가(신뢰도·커버리지), 영상과 prior의 정상 어긋남(허용 오차 τ),
  그 이상 어긋난 자리(충돌 지도)를 prior L(과거 ALS 2.5D TIN)·M(과거 LoD2) × 정상·편향(+1.0 m)의
  네 조건에 같은 절차로 측정하고, 둘째 단계(신뢰도 기반 GS 학습) 설정과 판독 기대치로 연결한다.
- 외부 납품 폴더: `../JointBuildGS-artifacts/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1`
  (`out/` 전체, `report.md`, `viewer.html`, `viewer_README.md`, `stage2_config_{L,M}.json`, `logs/`, `provenance/`).
- 재현: `scripts/phd/stage1_conf_tol_conflict_v1/run_all.sh all` (Docker `jointbuildgs:dev` +
  GeoGS 실행 이미지, CPU 전용). 설정: `configs/phd/stage1_conf_tol_conflict_v1/experiment.json`.
- 시험: `python -m unittest tests.phd.test_stage1_conf_tol_conflict_v1` (dev 이미지).
- 보고서 사본: [REPORT_ko_v1.md](REPORT_ko_v1.md) (외부 `out/report.md`의 승격 사본).
- 뷰어 서빙: http://192.168.10.203:8886/viewer.html (컨테이너 `jbgs-stage1-conf-viewer-8886`, `out/` 읽기 전용).
- 검수(2026-09-23): [INSPECTION_ko_v1.md](INSPECTION_ko_v1.md) 첫 줄 "다시 재야 한다"; 발주서 사본 [ORDER_ko_v1.md](ORDER_ko_v1.md); 재현 스크립트 `scripts/phd/stage1_inspection_v1/`.
- 검증 설계 v2(2026-09-23): [VERIFY_v2_ko.md](VERIFY_v2_ko.md) 첫 줄 "다시 재야 한다"(남은 항목 1: L 정상 장면 폭 밖 7.3%); 부분 주입·연직 축·지붕 풀·정합 반영; `scripts/phd/stage1_verify_v2/`, 설정 `configs/phd/stage1_verify_v2/experiment.json`, 2단계 설정 `out_v2/stage2_config_v2_{L,M}.json`.
- 인계 결정(2026-09-23): 폭 = 실측(2.5·s2), 사양값은 오류 규모로만 → `PHD-STAGE1-VERIFY-v2/out_v2_data/`(τ_L 4.1 cm, τ_M 5.7 cm; 민감도 0.99/1.00; 정상 폭 밖 L 16.6%·M 20.2%). 2단계 설계 초안: `docs/experiments/phd/stage2_conf_guided_gs_v1/DESIGN_ko_v1.md`.
- 문제·예외: 외부 `logs/issues.jsonl`, 보고서 7절.

<!-- END PHD-STAGE1-CONF-TOL-CONFLICT-v1 -->
