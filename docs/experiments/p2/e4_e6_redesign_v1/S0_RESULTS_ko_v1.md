# E4/E5/E6 재설계 S0 검증 결과 v1 (학습 비용 0)

- 상태: `TECHNICAL RESULT RECORD — NON-CONFIRMATORY`
- task_id: `P2-E4-E6-REDESIGN-S0-v1` / 계획: `E4_E5_E6_REDESIGN_PLAN_ko_v1.md` §8
- 실행: 2026-08-12, Docker `jointbuildgs:dev`, `--network none`, 아티팩트 rw 마운트
- receipt 루트: `/artifacts/JointBuildGS/phase-payloads/p2/e4_e6_redesign_s0_v1/P2-E4-E6-REDESIGN-S0-v1/`
- `official_PASS_usable: null`, `scientific_verdict: null` — 임계 `NOT_FROZEN` 캐비앳 유지.

## S0-a — 같은 계보 E3의 v22 판정: 대시보드 서사가 뒤집힘

레거시 techdev `E3_GS_IMAGE`(assembled.city.json, sha `edce3a62…`)를 봉인된 v22
기준(참조·임계·코드 동일)으로 199동 전량 판정. val3dity 2.6.0이 현재 이미지에
없어 비교 통계는 `O_noG2`(G0∧G1∧G3∧G4)로 통일 — 봉인 조건들의 O vs O_noG2 차이는
경미(E3/E4/E5 동일, E2 29→31).

| O50, noG2 | E3_LEGACY | E4(레거시) | E5(레거시) | E3(신형) | E2 | E1 |
|---|---|---|---|---|---|---|
| O / 199 | **5** | **13** | **13** | 23 | 31 | 29 |

같은 계보 페어드 전이(O50, noG2):

| 대비 | rescue X→O | 역전 O→X | net |
|---|---|---|---|
| legacy E3 → E4 | **12** | 4 | **+8** |
| legacy E3 → E5 | **12** | 4 | **+8** |
| legacy E3 → E2 | 27 | 1 | +26 |

**판독**: 같은 베이스 위에서는 — 오염된 합성 ALS, confidence≡1, 차폐 무시 투영,
시드 오염이라는 최악 조건에서도 — 프라이어가 Roofer O를 5→13으로 **개선**했다
(net +8). 대시보드의 "E4/E5(13) < E3(23)"은 전부 계보 효과다: 신형 E3 레시피가
같은 조건에서 5→23을 만든 것이지, 프라이어가 23을 13으로 깎은 것이 아니다.
역전 4동은 E5 비열화 목표(H3b)의 실측 기준선이 된다.

- 산출: `s0a/legacy_e3_summary_v1.json`, `s0a/legacy_e3_building_condition_v1.csv`
- v22 건물별 CSV sha: summary JSON에 기록. 레거시 E3 실패 프로파일(O50):
  `G3_PLANE_RECALL_LOW` 110, `G3_PLANE_PRECISION_LOW` 108, `G4_RMSZ_HIGH` 95,
  `G0_OUTPUT_MISSING` 56 — 신형 E3(G0 84 중심)과 실패 구조도 다르다.

## S0-b — 누출 전수조사 + 차폐 인지 투영 QA: 3게이트 전부 통과

Part 1 (레거시 프라이어 937뷰 전수, 3,430만 px / MVS 지원 2,610만 px):

| 지표 | 값 |
|---|---|
| \|prior−MVS\| > 2 m 비율(전체) | **70.5 %** |
| 뷰별 중앙값의 중앙값 | 1.75 m |
| 뷰별 >2m 비율 중앙값 | 49.5 % |

Part 2 (재설계 §4.2 프로토타입: 실제 raw ALS class 2+6 → 0.5 m DSM TIN
427만 점/205만 삼각형 → 레이캐스트, 동일 15뷰 표본):

| QA 지표 | 값 | 목표 | 판정 |
|---|---|---|---|
| 중앙값 \|Δ\| | **0.105 m** | ≤ 1.0 m | PASS |
| >2 m 비율 | **10.7 %** | ≤ 25 % | PASS |
| 대 점-투영 비율 | **0.143** (74.8 %→10.7 %) | ≤ 0.5 | PASS |

**판독**: 2022 ALS는 올바르게 투영하면 2024 MVS와 중앙값 10 cm로 일치한다 —
"데이터는 정답에 가깝고, 점 z-buffer 투영이 오답을 대량 생산했다"가 전수
규모로 확정. 잔여 10.7 %는 실제 시간 변화·MVS 잡음·TIN 경계 평활을 포함하므로
§4.4 임계(D5)의 합리적 하한 근거가 된다.

- 산출: `s0b/leak_and_projection_qa_v1.json`, `s0b/legacy_leak_per_view_v1.csv`

## S0-c — 절제 이상 감사: 노멀 항이 하중 지지 부재

세 arm(동일 7000분기)의 봉인 TB 스칼라·effective config·three_arm_metrics 대조:

| | control | ALS depth만 | E4(depth+normal) |
|---|---|---|---|
| loss/depth(MVS) 최종 | 0.271 | 1.197 | 1.227 |
| ALS normal 1−\|dot\| 최종 | (0.085 분기값) | **0.210 악화** | **0.147 개선** |
| Roofer 입력 참조 노멀 중앙 오차 | 2.52° | **11.51°** | **0.55°** |
| roofer f-score(0.5 m) | 0.105 | 0.059 | **0.985** |

**판독**: ALS depth 항은 표면을 MVS·ALS 사이 절충점으로 끌며(p2plane
0.042→0.25 m) 단독으로는 프리미티브 방위를 흐트러뜨려(노멀 오차 2.5°→11.5°)
Roofer 평면 추출을 무너뜨린다. sign-invariant 노멀 항이 방위를 ALS 평면에
고정할 때(0.55°)에만 Stage-3 판독이 성립한다(f-score 0.985). depth와 normal은
분리 불가한 짝으로 취급해야 하며(D7), 노멀 항 제거 절제는 유해 조합으로 기록.

- 산출: `s0c/ablation_audit_v1.json`

## 재설계 결정 항목에의 입력

- D2(conflict): 페어드 역전 4동 목록이 E5 비열화 검증의 실측 대상.
- D5(누출 QA 임계): 프로토타입 실측(중앙값 0.105 m, >2 m 10.7 %) 기준으로
  제안 임계(≤1.0 m / ≤25 % / 비율 ≤0.5) 유지 타당.
- D7(가중): depth+normal 짝 유지 필수(S0-c). depth-only 구성 금지.
- D9(빈 픽셀): TIN 투영은 hit 비율 중앙값 0.867의 준-dense 맵을 주므로
  alpha-gate 선택지(A)의 실효 커버리지 손실이 작음 — S1에서 A/B 비교 유지.
- S0-a의 계보 분해로 §7 평가 계획의 "같은 계보 6조건 한 표" 원칙이 재확인됨.
