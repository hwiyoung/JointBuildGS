# PHD-MAIN-BASE151-v1 진행 기록

scientific_verdict: null · 시각은 KST.

- 2026-11-19T01:11:50: 설정 잠금 base151_v1.json sha256 8080890226bb9c2a5e02e65c44d42615b73dd6afd6f6a9f25525bf16fb04b294 (저장 01:11:46)
- 2026-11-19T01:13: 2DGS 칸 장면 넷 (b151_scenes.py 2dgs)
- 2026-11-19T01:20: 진입 시험(tests/smoke_2dgs): 100회 멈춤 저장 → 이어 돌림 → 700회, 필터·기록 작동
- 2026-11-19T01:20:44+09:00: 대기열 시작 (pid 3504164)
- 2026-11-19T01:20:44+09:00: b151_2DGS_s0 칸 0 시도 1 시작(GPU 1 남은 24086 MiB, 상한 21.52 GiB)
- 2026-11-19T02:10:18+09:00: GeoGS 초기 점 LoD2 칸 0: 종료 코드 0
- 2026-11-19T01:3x: 칸 사전정보 면 넷(inputs_prior 잠금 4c2c74c9; b151_prior.py): LoD2 4,561~10,014면, 항공 LiDAR TIN 218만~341만 면
- 2026-11-19T01:3x: 이미지 다시 지음: jointbuildgs:geogs-official-db40c95-rtree-v1-b151(FIX geogs_rtree.Dockerfile, compat 바탕), jointbuildgs:cdgs-official-db853c1-v1-b151(원래 freeze로 묶음)
- 2026-11-19T01:4x: GeoGS 입력 규칙 잠금(inputs_GeoGS c89aea15), 장면 여덟(LoD2Depth 깊이 지도, 보호 점구름 100만) 끝 → 초기 점 계산 둘씩(run_geogs_pcd_chain.py)
- 2026-11-19T01:4x: CDGS 입력 규칙 잠금(inputs_CDGS 77ac91c7), sparse 넷(WD 캠퍼스 SfM 자세 = 칸 자세, 차 0; 초기 점 114,970/159,404/165,537/128,020; s 17.03/19.32/21.45/22.66), 사전정보 깊이(학습 영상) 여덟, 장면 틀 여덟
- 2026-11-19T01:48: DA3는 2DGS 칸 0 뒤 학습 없는 틈에 돌림(HOLD_GPU, run_da3_hold.sh); 대기열은 칸 0 뒤 새 코드로 다시 뜸(relaunch_queue.sh); CDGS 300회 GPU 시험도 같은 틈(b151_smoke.py)
- 2026-11-19T02:0x: 4.2 채점 규칙 잠금(score151 fb905e9f); 단위 배치 32개(칸 × 100 m 구역, 넓이 합 20.6만 m², 단위마다 칸 학습 영상 37~315장)
