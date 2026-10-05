# 2단계(판정 유도 GS) 실행 인계 v2 — 2026-09-23 23:25 KST

`scientific_verdict: null`. v1의 미결 2건은 해결했고, 본 실행 11조건이 **세션과 분리된 백그라운드**로 돌고 있다. 새 세션은 "4. 끝난 뒤 할 일"부터.

## 1. 지금 도는 것

| 무엇 | 어떻게 | 확인 |
|---|---|---|
| 학습 대기열 GPU 0: P_M_B → P0_M_B → O_M_B → P_L_B → P0_L_B | systemd 사용자 서비스 `jbgs-s2-queue-gpu0` | `systemctl --user status jbgs-s2-queue-gpu0` |
| 학습 대기열 GPU 1: P_M_N → P0_M_N → O_M_N → I → P_L_N → P0_L_N | `jbgs-s2-queue-gpu1` | `logs/queue_gpu{0,1}.jsonl` |
| 대시보드 | 컨테이너 `jbgs-s2-dashboard-updater`(2분마다 생성, 대기열 끝나면 종료) + `jbgs-s2-dashboard-8887` | `http://<호스트>:8887/` |
| TensorBoard | 컨테이너 `jbgs-tensorboard-6006`(`--logdir /s2/runs`) | `http://<호스트>:6006/` |

- 파라미터 고정: 30,000회, λ_mvs = λ_prior = 0.05(예비 실행으로 선택, `logs/lambda_selection.json`), τ_v L 0.0405 / M 0.0568 m, E 문턱 0.5, 잠금 갱신량 ×0.01, 불투명도 하한 0.5, E 갱신 500회.
- 대기열은 조건마다: 학습 → 보정 카메라 평가 렌더(`eval/<조건>/render_30000/`) → 끝에서 `evaluate.py` → `eval/faces_30000.csv`, `compare_conditions_30000.csv`, `appearance.csv`, `gaussians_30000.csv`. 나중에 끝나는 대기열이 전체 표를 쓴다.
- 예상 종료: GPU 0 약 05:00, GPU 1 약 06:00 KST(2026-09-24). 조건당 약 65분(첫 두 조건 실측; O는 진단 기록 57분).
- 주장과 조건별 기대 결과: [CLAIMS_EXPECTATIONS_ko_v1.md](CLAIMS_EXPECTATIONS_ko_v1.md) — 결과 검토는 이 표에 맞춰 한다.
- 첫 점검: P_M_B 2,000~5,000회 주입 지붕 d_F = +0.99~+1.00 m(초록, 렌더가 첫 판독부터 사진 표면에 있음), P_M_N 2,000~3,000회 본지붕 d_F = +0.01 m(초록).
- 읽는 법: d_F = 옛 자료 높이 − 렌더 높이. B 본지붕 d_F ≈ +1.0 = 렌더가 올린 옛 자료보다 1 m 아래 = 사진 표면(같은 면 e_F ≈ 0.00, g_F ≈ +0.07로 N과 같음). 반응이 없었다면 d_F ≈ 0, e_F ≈ −1.0, g_F ≈ −0.93. 1,000회 첫 판독부터 이미 사진 표면이었다(되돌아오는 궤적은 관측되지 않음).
- **B 장면의 이웃 면 오염(발견, 9-23 23:40)**: B 옛 자료 렌더에서 올린 본지붕이 경사 시점 시차로 이웃 소면을 가린다(B 옛 자료가 N보다 0.3 m 넘게 높은 픽셀: 3394 80%, 3389 73%, 3387 40%, 3404 11%; 3394는 그중 32%가 A=0). 그래서 B에서 이 면들의 d_F·라벨은 자기 옛 자료가 아니라 올린 지붕 기준이고, A=0 픽셀의 옛 자료 항이 렌더를 올린 지붕 쪽으로 당긴다. P_M_B 9,000회: 3394 g_F −0.45 m(N +0.01), 3389는 −0.98 → −0.04로 회복. 7절 점검은 B에서 3396만 보므로 초록으로 남는다. Q3(소면)는 N 조건으로만 판단하고, 이 번짐은 보고서에 발견으로 적는다. 잠금과 옛 자료 항의 몫은 P0_M_B와 15,000회 원반 기록으로 가른다.
- 빨간 신호(조건 P의 7절 지붕 규칙)는 그 반복의 덤프·PLY·`monitor/stop.json`을 남기고 그 조건만 멈춘다. 대기열은 다음 조건으로 간다(`logs/issues.jsonl`).

## 2. 멈추기·다시 걸기

- 다음 조건부터 멈춤: `touch $S2/logs/STOP_QUEUE`(또는 `STOP_QUEUE_GPU0`). 지금 조건까지 즉시 멈춤: 서비스 중지 후 `docker stop jbgs-s2-<조건>`.
- 다시 걸기(재개 가능 — PASS 영수증은 건너뛰고, 같은 조건 컨테이너가 돌고 있으면 기다리고, 중단본은 `runs/<조건>/interrupted/`로 옮긴 뒤 다시 돈다):

```bash
cd /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator
S2=$(realpath ../JointBuildGS-artifacts/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1)
systemd-run --user --unit=jbgs-s2-queue-gpu0 --collect --working-directory="$PWD" --setenv=PATH=/usr/local/bin:/usr/bin:/bin --setenv=HOME="$HOME" -p StandardOutput=append:$S2/logs/queue_gpu0.out -p StandardError=append:$S2/logs/queue_gpu0.out /usr/bin/python3 scripts/phd/stage2_conf_guided_gs_v1/run_queue.py --gpu 0 P_M_B P0_M_B O_M_B P_L_B P0_L_B
```

- **실행 중에는 바꾸지 말 것**: 포크 `sources/GeoGS-conf-guided-v1`(빌드 r5, `provenance/build_report.json`), `run_condition.py`, `render_depths.py`, `evaluate.py`. 다음 조건부터 영향을 준다.
- 23:12·23:16에 시작한 P_M_B·P_M_N은 이 세션의 셸에서 띄운 것을 서비스가 넘겨받아 기다리는 중이다. 세션 종료로 그 둘이 중단되면 서비스가 처음부터 다시 돌린다(약 1시간 손실).

## 3. 이 세션에서 한 일 (발주서 13절에 정정 11건)

1. 미결 1(부호): 1단계 규약 유지(식 그대로, + = 옛 자료가 위) → 발주서 3.5·7절 주입 지붕 기대치를 +1.0으로, 점검 규칙·시험 기대 부호 통일.
2. 미결 2(GPU 시험 순서): backward → Adam step → 재설정 순서로 재작성, 6항목 통과.
3. 실행 전 발견·수정: 잠금이 기울기 ×0.01이면 Adam에서 무효(실측 98.7%) → 갱신량 ×0.01(1.08%); 벽 f_p 발산(τ_p 6.5×10⁻⁸ m) → 벽은 법선 방향 환산; 옛 자료 표면을 떠난 자유 원반이 "못 봄"으로 잠기던 문제 → 잠금 예외; 덤프 float16(3.1 cm 간격) → float32; 출처 int8 PLY가 `load_ply`를 깨뜨림 → int32; 원반 초기 id·이동량·제거 시점 기록 추가; LPIPS 가중치 오프라인 마운트; 빨간 신호 정지.
4. 저장소 원본화: `jbgs_judgment.py`를 저장소로 옮기고 `build_fork.py`가 부모 소스에서 포크를 재현 빌드(r1~r4는 `sources/superseded/`, `provenance/superseded_r*/`).
5. 시험: CPU 14건·GPU 6건 통과, 스모크 700회 PASS, 정지 경로 시험(τ 0.001) 확인, 평가 렌더 = 학습 중 덤프(최대 차 0.0 m), 평가 표 = 학습 중 판독(지붕 6면 소수 넷째 자리 일치).
6. TensorBoard 6006 교체(사용자 허가). 이전 설정은 `logs/replaced_container_jbgs-tensorboard-6006.inspect.json`.

## 4. 끝난 뒤 할 일 (다음 세션)

1. `logs/issues.jsonl`·대시보드에서 빨간 정지·실패 확인 → 있으면 원인 기록, 8절 범위(λ 0.02~0.10, 밀집화 문턱, 학습률) 안에서 조정하고 그 조건군을 다시 돈다.
2. 표 검토: `eval/faces_30000.csv`, `compare_conditions_30000.csv`(P−P0 판정 효과, P0−O 골격 효과(주점 효과 섞임), P−I 옛 자료 효과).
3. 보고서 `report.md`(사실 + "의미" 절 Q1~Q4 + 조정 기록), 그림(면 라벨 지도 전·후, 감시 시점 잔차 시계열, 본지붕·소면 단면, E·불투명도 분포), 매니페스트 `artifacts/manifests/stage2_conf_guided_gs_v1.yaml`, README.
4. 보고서에 적을 것: O의 `attenuate_*_lr`(기울기 방식)은 Adam에서 학습률 감쇠로 거의 작동하지 않는다; O는 주점 중심 가정·전체 타일 prior; M prior 원반 67%가 반복 1에 잠김(대부분 13시점이 못 보는 벽·뒷면).

## 5. 위치

- 페이로드 `S2 = ../JointBuildGS-artifacts/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1/` — `runs/<조건>/{model, receipt.json}`, `eval/`, `dashboard/`, `logs/`, `provenance/`, `inputs/maps/superseded_r1/`(교정 전 fvert·τ).
- 예비 실행: `runs/P_M_N/model_{smoke700, lam002, lam005, stoptest}`, 실패본 `runs/P_M_N/failed/`.
- 저장소(미커밋): `scripts/phd/stage2_conf_guided_gs_v1/` (+ `jbgs_judgment.py`, `build_fork.py`, `run_queue.py`, `render_depths.py`, `evaluate.py`, `make_dashboard.py`, `dashboard_index.html`), `tests/phd/test_stage2_conf_guided_gs_v1.py`, 발주서 13절.

## 6. 결과 확인 (9-24 추가)

- 11조건 모두 PASS(9-24 05:15), 빨간 정지 없음. 주 평가는 **판정 칸별 '따랐나·맞았나'**: `eval/intent_30000.csv`(`eval_intent.py`), 화면 `http://<호스트>:8887/intent.html`(`make_intent_viewer.py` → `dashboard/intent/`; 옛 자료·장면·시점 선택, 주소 `#prior=M&scene=B&view=...`로 공유).
- 칸 정의(1단계 입력만): 일치(A=1, |M−P|≤τ) → 옛 자료 유지, 충돌(A=1, >τ) → 사진 따름, 못 잼(A=0) → 옛 자료 유지(맞든 틀리든; 사용자 확인 9-24). 못 잼 칸의 GT 오차는 옛 자료 자체의 품질이다.
- 면별 표(`faces_30000.csv`)는 보조. 3393은 학습 해상도 3픽셀이라 해석에서 뺀다. 그림 `eval/figures/`(`make_figures.py`).
- O는 건물 전체가 약 0.3 m 위로 치우침 → 공식 구현의 주점 중심 가정(세로 7.6 px ≈ 0.4° ≈ 44 m에서 0.3 m)이 유력. 확인은 O를 같은 카메라 어댑터(주점 복원)로 다시 학습(2회).
- **가우시안 3D 보기** `http://<호스트>:8887/surfels.html`(앱 `src/apps/stage2_conf_guided_viewer_v1/surfels.html`, 데이터 `export_intent_surfels.py` → `dashboard/surfels/*.bin`+`index.json`, three.js는 `gs3d_4way_viewer` 번들 복사): 옛 자료·장면별로 P·P0·O·I 네 화면, 카메라 동기, 사진 0009·0024·0005·위 시점, 색 = 실제 색/판정 칸/판정대로?/GT 높이 차/출처·잠금. 원반 색은 그 원반이 만드는 렌더 표면(표의 픽셀)의 판정 — 표와 같은 규칙, 수치는 원반 기준이라 픽셀 표와 조금 다름. 회색 = 어느 사진에서도 표면으로 드러나지 않는 원반(표에 안 들어감). 조건당 대상 건물 영역 원반 최대 20만(판정과 다른 원반·잠긴 원반은 전부, 나머지 XY 고르게), 하늘은 표면 높이대 ±3 m 밖이라 제외.
- 3D 보기에 **렌더 표면(표의 픽셀)** 모드 추가(기본값, `export_intent_surface_points.py` → `surfels/surface_*.bin`+`surface_index.json`): 점 하나 = 15장 사진의 대상 건물 픽셀 하나를 결과 렌더 깊이에 놓은 것 = 의도 점검 표의 표본(조건당 전체 약 911만 픽셀 중 40만 무작위). 영역(지붕/벽)·칸(일치/충돌/못 잼)을 고르면 표의 그 줄이 되고 화면 아래 수치가 표와 같다. 가우시안 원반 모드는 그 표면을 만든 원반 낱개.

