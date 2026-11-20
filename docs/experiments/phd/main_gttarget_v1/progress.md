# PHD-MAIN-GTTARGET-v1 진행 기록

scientific_verdict: null · 참값 목표 판(진단용)

## 예상 시간 (발주문 6.2, 첫 판 전에 적음)

FINALTRAIN 30,000회의 실제 걸린 시간으로 어림했다. TRAINERR 기록 판(tl_*)은 FINALTRAIN과 거의 같았다(B0 × LoD2 6,709 s 대 6,659 s).

| 차례 | 판 | FINALTRAIN 걸린 시간 | 누적 |
|---|---|---:|---:|
| 1 | R1 × 항공 LiDAR | 4,958 s (1.4 h) | 1.4 h |
| 2 | R1 × LoD2 | 6,584 s (1.8 h) | 3.2 h |
| 3 | B0 × LoD2 | 6,659 s (1.8 h) | 5.0 h |
| 4 | B173 주변 × LoD2 | 7,854 s (2.2 h) | 7.2 h |
| 5 | B173 주변 × 항공 LiDAR | 5,263 s (1.5 h) | 8.7 h |
| 6 | B0 × 항공 LiDAR | 4,478 s (1.2 h) | 9.9 h |
| 7, 8 | R1 두 판 씨앗 1 | 11,542 s (3.2 h) | 13.1 h |

- 판마다 표면 추출 네 가지(렌더 + TSDF + 채점)는 판당 약 1시간으로 본다. 학습과 겹쳐 CPU에서 돈다.
- GPU는 한 대(1번)만 쓴다.

## 기록
- 2026-11-19T02:03:29+09:00: 1단계 시작. 사용자 결정 둘(평면 나누기 뒤 LoD2 규칙, 0.25 m). 참값 조각 세 지역, 목표 파일·씨앗 여섯 장면, 목표 깊이 지도 첫 판 → 법선 부호 고침(issues.md) → 다시 만듦.
- 2026-11-19T09:50:40+09:00: 1단계 목표 메시 채점에서 5절 기준(99 %) 미달 다섯 장면 → 멈춤, 사용자에게 물음. 나머지 점검(깊이·가림·범위·씨앗) 계산 중.
- 2026-11-19T10:33:59+09:00: 사용자 결정(조각 원판으로 학습). 2단계 잠금. 300회 시험(R1 × 항공 LiDAR, 215 s, loaded_targets PASS) — GPU 1에서 본 실험(b151)과 잠깐 겹침, 이후 GPU 0만 씀. 대기열 시작.
- 2026-11-20T15:39:07.921191+09:00: g3_ga: tables ga_size/ga_scene/ga_edge/na_cross/na_seed/da_cells/da_places, absent ['B173nb_b10__LoD2'], 144 s
- 2026-11-20T15:48:49.067296+09:00: g3_tables8: scenes ['R1rep_b10__ALS'], absent ['R1rep_b10__LoD2', 'B0_b10__LoD2', 'B173nb_b10__LoD2', 'B173nb_b10__ALS', 'B0_b10__ALS']
- 2026-11-20T16:16:09.185471+09:00: g3_tables8: scenes ['R1rep_b10__ALS', 'R1rep_b10__LoD2', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B0_b10__ALS'], absent ['B173nb_b10__LoD2']
- 2026-11-20T16:18:39.516301+09:00: g3_tables8: scenes ['R1rep_b10__ALS', 'R1rep_b10__LoD2', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B0_b10__ALS'], absent ['B173nb_b10__LoD2']
- 2026-11-20T16:40+09:00: 3단계 끝. 표 ga_size·ga_scene·ga_edge·na_cross·na_seed·da_cells·da_places·ca_state·ra_share·ma_state·da_labels·da_front·ga_course·ba_causes·ba_unexplained·check8·check11·cmd_diff·ga_reference, 그림 lostmap·ra_bars·cells_map·unexplained_map·case_*(여섯), 보고.md, 점검_11절.md. B173 × LoD2 결과 없음(멈춤 3회).
- 2026-11-20T18:01:50+09:00: 발주문 대조 뒤 채움 — case_unexpl, case_cell1~3, da_annex, 뜬 면 그림 다시, 보고.md·점검_11절.md 고침.
- 2026-11-20T18:38:03+09:00: 두 번째 발주문 대조 — 1단계_보고.md, 판 이름 반복 수, case_edge_annex.
- 2026-11-20T18:39:06.200009+09:00: g3_ga: tables ga_size/ga_scene/ga_edge/na_cross/na_seed/da_cells/da_places, absent ['B173nb_b10__LoD2'], 75 s
- 2026-11-20T18:39:15.130811+09:00: g3_tables8: scenes ['R1rep_b10__ALS', 'R1rep_b10__LoD2', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B0_b10__ALS'], absent ['B173nb_b10__LoD2']
