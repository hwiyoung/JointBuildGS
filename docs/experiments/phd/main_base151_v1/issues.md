# PHD-MAIN-BASE151-v1 문제 기록

scientific_verdict: null

- 2026-11-19T01:0x: jointbuildgs:2dgs-official-f3e3b9f-v1, jointbuildgs:cdgs-official-db853c1-v1, 바탕 jointbuildgs:geogs-official-db40c95-v1 이미지가 호스트에 없음 → 저장소 Dockerfile로 다시 지음(2DGS = compat 바탕, CDGS = 원래 freeze로 판 고정). 새 태그 *-b151.
- 2026-11-19T09:49:47+09:00: GPU 1 05:13~09:5x 쉼: 2DGS 끝 뒤 GeoGS READY 표시를 사람이 걸게 되어 있었는데 걸지 못함(세션 쉼). 대기열 규칙 문제 아님
- 2026-11-19T11:29:01+09:00: 4.1 후처리 명령 2회 실패: -B -u /b151s/b151_units.py mesh c1_6907_53360__ALS__b151_2DGS_s0 merge (기록 /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1/logs/post42/c1_6907_53360__ALS__b151_2DGS_s0.log)
- 2026-11-19T11:29:47+09:00: 4.2 단위 실패: ('b151_2DGS_s0', 'c1_6907_53360')
- 2026-11-19T13:26:14+09:00: 4.1 후처리 명령 2회 실패: -B -u /b151s/b151_units.py mesh c1_6909_53363__ALS__b151_LGDM_ALS plan (기록 /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1/logs/post42/c1_6909_53363__ALS__b151_LGDM_ALS.log)
- 2026-11-19T13:26:56+09:00: 4.2 단위 실패: ('b151_LGDM_ALS', 'c1_6909_53363')
- 2026-11-19T13:40:37+09:00: 4.2 단위 두 곳 원인(같은 설정 2회 모두 같은 자리에서 멈춤 = 결정적): (가) b151_2DGS_s0 c1_6907_53360 merge = bounded_merge 단언 실패, 한 칸 안 Open3D 꼭짓점 1쌍이 같은 모서리 번호, 좌표 차 2.8e-14 m, 색 같음 → GTJUDGE recovery_merge.py 규칙(같은 칸 충돌 꼭짓점은 모서리 정체를 미정으로 두고 bounded_merge 그대로; 칸 파일·꼭짓점·면·TSDF 값 불변) 적용(b151_units.merge_keep_open3d). (나) b151_LGDM_ALS c1_6909_53363 plan = streamed_tsdf e_lat 0.5008 m >= 0.5 m. e_lat는 칸 경계의 대리 깊이 근거에만 쓰임; 칸 하나 배치면 상자 안 점은 모두 E_t 안 → 칸 깊이 = 깊이 → 칸 하나일 때만 검사 건너뜀, 합치기 전 대리 화소 0 확인(아니면 멈춤). 32 단위 중 e_lat >= 0.5는 이 단위 하나(meshcheck/elat.json, 모든 방법 같은 단위). 코드 고침 = 3.3 설정·코드 오류 갈래
