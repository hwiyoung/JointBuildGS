# PHD-MAIN-JUDGECHECK-v2 진행

- 2026-11-12T13:00:29+09:00: 작업 시작(12:40경 발주 받음). git worktree `../JointBuildGS-wt-judgecheck2`, 브랜치 `exp/judgecheck-v2`(exp/main-experiment 24a4344b에서 땀). 발주문 사본 `configs/phd/main_judgecheck_v2/order_v2.txt`. 학습 없음. scientific_verdict: null.
- 2026-11-12T13:13:07+09:00: 설정 judgecheck_v2.json 첫 잠금(initial.lock.json). 그 전에 건물 목록(s0_inventory.py)만 셈: 범위 151동(LoD2만 있는 3동 제외), 실험 10동, 탐색 지역 밖 61동.
- 2026-11-12T13:19:22+09:00: 기하 셈(s1_geometry.py) 24구역 시작·거의 완료. 고리 R1.5 재현 확인: WIDEN0 시드의 패치 번호는 patch_geometry 차례임을 찾아 s1_ring.py에 반영(실행 전 수정), float32 비교로 6907_53360 MVS 297/297·ALS 97/97 같음. 고리 base 구동(run_ring.sh base 48) 걸어 둠.
- 2026-11-12T13:21:31+09:00: τ(s0_tau.py): 탐색 지역 일곱 + 합친 값. B0·R2·R1은 지금 값과 정확히 같음. 재현 확인(s0_repro.py): 세 지역 × 두 사전 정보 모두 판정 넓이 100 % 같음(L 차이 0, t 같음, 광도 결과 같음). MVS 같은지 확인(s0_mvs_identity.py): 다름 → 본값은 WIDEN0 MVS.
- 2026-11-12T13:40:38+09:00: TSDF 통째 구역 판이 큰 구역 2곳(6908_53359, 6908_53360)에서 16 GB 한도로 두 번 멈춤(기록 없는 OOM). 실행 중인 s1_tsdf.py 는 고치지 않고 같은 규칙의 사분면 판 s1_tsdf_q.py(50 m 사분면 + 12 m 상자)를 새로 만들어 남은 구역을 돌림. 통째로 끝난 4구역은 그대로 씀.
