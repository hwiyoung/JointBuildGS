# PHD-MAIN-JUDGEABL-v1 5절 기존 4 결합(전 건물) 진행

- 2026-11-17 22:2x: 작업 폴더 `../JointBuildGS-wt-judgeabl1-fuse`, 브랜치 `exp/judgeabl-v1-fuse` (2a062dd7 에서).
- 입력 조사: 일곱 탐색 지역의 COLMAP 조밀 MVS(/dr/mvs/<지역>, 학습 영상 B0 272·R1 582·R2 221·R3E 311·R4 98·R5 250·SW 266), 메시(/dr/s02/<지역>), 정합 이동(/dr/s52/s03/<지역>/<prior>/summary.json)이 이미 있다 → GPU 단계(COLMAP) 다시 돌리지 않음. 정합 이동은 JC buildings.json 의 als_shift_m 과 일곱 지역 모두 같음(LoD2 는 0).
- 내보내기 지도(s03 v6 --export-fork)는 만들지 않음: 판정에 쓰이는 사전 정보 깊이는 detect.judge 가 원래도 다시 던지고(대조), MVS 깊이는 COLMAP 기하 깊이 지도의 유한·양수 화소(= s03 v6 내보내기 규칙), τ 지도는 색 참고 히스토그램에만 쓰임. 따라서 다른 작업 결과 폴더에 아무것도 쓰지 않음(/res 만).
- 설정 `configs/phd/main_judgeabl_v1/judgeabl_v1_fusion_all.json` 첫 셈 전 잠금(lock: 설정 sha + inherited 세 파일 sha).
- 검산(세 실험 지역 상자 6판): 최종 칸·투표·제거·넓힘·nsee·dz_med 가 BASELINES-v1 저장 칸과 모두 같음, JUDGEAPPLY region[4] 와 넓이 100 % 같음 → 통과. 짝 243/243 같음, 영상 40/40 바이트 같음(B0_b10).
- B0 탐색 지역: 102 초 (영상 8·짝 23·LoD2 24·ALS 45) → 일곱 지역이 3시간 안에 끝날 것으로 보여 잇는다.
- 2026-11-17 22:51: 나머지 여섯 지역 끝(1,035 초, 모두 PASS; R2 ALS 실행기 끝줄 사고는 issues.md).
- 2026-11-17 22:55: 연결 — 격자 밖 패치가 B0 54 % 등으로 많아 설정 v2(격자 밖 = 덮이지 않음)로 고친 뒤 연결(채점 전). 덮인 범위 LoD2 66.1 %, ALS 65.6 % (넓이).
- 2026-11-17 23:0x: a1 LoD2·ALS → a2 → a3 → a8 다시 돌림. 앞서 낸 판의 값 모두 같음(사본 대조). 보고서 결합전건물_보고_v1.md.
- 2026-11-17 22:59: 묶음 라: PHD-MAIN-JUDGEABL-v1_라_1117-2259_light.zip (6.6 MB)
