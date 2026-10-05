# 2단계(판정 유도 GS) 실행 인계 — 2026-09-23 세션 마감

`scientific_verdict: null`. 이 세션의 범위는 발주서(`ORDER_ko_v1.md`, §12 확정)까지였다. 발주서 §6의 1~2단계(소스 분기·입력 준비·판정 모듈·단위 시험)가 부분 진행된 상태에서 멈췄고, **학습 실행(스모크·λ 예비·본 11회)은 시작하지 않았다.** 새 세션은 아래 "미결 2건"부터 시작한다.

## 1. 위치

- 페이로드 `S2 = ../JointBuildGS-artifacts/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1/` (컨테이너 `/s2`, 아티팩트 루트 `/artifacts/JointBuildGS`).
- 소스 분기 `S2/sources/GeoGS-conf-guided-v1/` = `GeoGS-mvs-pgsr-v1` 복제 + 패치. 신규 `jbgs_judgment.py`. 패치 diff `S2/provenance/patches/*.diff`, 해시 `S2/provenance/patched_source_sha256.txt`, 적용 보고 `jbgs_judgment_patch_report.json`.
- 저장소(미커밋): `scripts/phd/stage2_conf_guided_gs_v1/{prepare_m_main_1m, prepare_stage2_inputs(--maps/--points), crop_mesh_rect, prepare_o_priors, patch_geogs_fork, make_scenes, gpu_tests, run_condition}.py`, `tests/phd/test_stage2_conf_guided_gs_v1.py`, `Dockerfile.geogs-conf-guided-v1`(복사본 `S2/`).
- 이미지 `jointbuildgs:geogs-conf-guided-v1` = 공식 compat 이미지 + TensorBoard(오프라인 휠 `S2/wheels/`, numpy 등 기존 패키지 불변).

## 2. 준비 완료 입력 (`S2/inputs/`)

- `maps/<set>/raw_depth/<view>.npy` 15시점 5644×4082 float32(NaN=없음): `conf`(A), `mvs`(A=1인 곳만), `prior_L_N`·`prior_L_B`·`prior_M_N`·`prior_M_B`(M은 ALS 사각형으로 크롭), `tau_L`·`tau_M`(τ_v/f_p), `gt`(GT 점군 z-buffer, 평가 전용), `fvert`(f_p), `faceid`, `faces.json`(지붕 3387·3389·3393·3394·3396·3404, 벽 12). 요약 `prepare_report.json`.
- `points/`: `sfm.npz` 72,028, `prior_L_N/B.npz` 120,333(주입 11,283점 +1 m), `prior_M_N/B.npz` 292k(크롭 메시 표본 `prior_pcd_crop/`, 300k 표본 중 가시 필터 통과).
- `prior_render/M_biased_main_1m/lod2_prior`(정합 메시 + 본지붕 3396 +1.0 m, 계단면 10 삼각형; `lod2_M_biased_main_1m.obj/json`).
- `prior_pcd/{M_nominal,M_biased_main_1m}`: 전체 타일 메시의 공식 표본(51.7k/51.6k) = O 조건 `sparse_lod` 초기화(저자 방식과 동일).
- `o_prior/M_{N,B}/lod2_pcd.ply`: 저자 100만 점군 +0.1216 m 정합; B는 3396 링 안(모서리 0.05 m 제외) 지붕 높이(정합 지붕 최저 −0.5 m 이상) 2,126점만 +1.0 m.
- `runs/<조건>/scene`(11개) + `condition.json` + `runs/conditions_summary.json`: P/P0 초기화 = prior ∪ SfM 192,361점(`origin.npy` 1=prior, 0=SfM), I = SfM 72,028, O = 공식 sparse_lod 51.7k/51.6k. 심볼릭 링크는 컨테이너 경로.

## 3. 검증된 것 / 미검증

- 패치 5파일 컴파일·임포트 확인(학습 이미지). CPU 단위 시험 8건 중 7 통과(ρ_τ 값·기울기, 투영=핀홀, 합성 A·P의 E, 손실 NaN 처리, 판독 라벨). GPU 모델 시험은 실행 순서 문제로 미통과(아래).
- 미검증: 학습 루프 자체(스모크 없음), 렌더 깊이 덤프·스냅샷 PNG, 대시보드, TensorBoard 기록.

## 4. 미결 2건 (새 세션 첫 작업)

1. **부호 규약 충돌.** 1단계 연직 잔차 = (MVS 깊이 − prior 깊이)×f, "+ = prior가 MVS보다 높음"(REPORT §2). 발주서 §4⑤ d_F = median((D−P)·f)는 같은 규약이라 **주입 지붕(prior가 위)에서 +1.0**이 나오는데, §3.5·§7 기대치는 −1.0으로 적혀 있다(발주서 내부 불일치). 모듈은 식을 그대로 구현했고 `checklist()`는 −1.0을 기대하므로 B 조건에서 오판한다. 권고: 1단계 규약 유지(식 그대로, + = prior/기준이 렌더보다 위) → 발주서 §3.5·§7 문구를 +1.0·"d_F > +τ 이동 시작"으로 고치고 `jbgs_judgment.checklist`와 CPU 시험 `TauConversionTests` 기대 부호를 맞춘다. 결정 후 CPU 시험 재실행.
2. **GPU 시험 순서.** `reset_opacity`는 Adam 상태가 있어야 하므로(실학습에서는 항상 있음) `gpu_tests.py`에서 hook 시험(backward)→`optimizer.step()`→reset 순으로 바꾼다.

## 5. 발주서에 없어서 준비 중 정한 것 (보고서에 기록할 것)

- M prior 점: 크롭 메시 표본 292k를 L 점 수 120,333에 맞춰 시드 0 균일 부표본(`make_scenes.py`; `condition.json.prior_subsample`).
- 학습 해상도 = 진단과 같은 −1 기본 = 1600×1157. 지도는 최근접 리샘플(NaN 번짐 방지).
- P/P0/I는 `jbgs_calibration.json`(1단계 PINHOLE K를 1600×1157로 축척, 주점 복원)을 쓰고 O는 공식 그대로(주점 중심 가정) → P0−O 차이에 주점 보정 효과가 섞인다.
- O 조건 = 진단 원본 소스(`GEOGS-ROOF-BIAS-20260921/sources/GeoGS`)를 공식 이미지에서 진단 명령 그대로(`--eval --lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight`), 옛 자료 배열만 v2 정합본. 렌더 깊이 덤프용 `render_depths.py`는 미작성.
- E 갱신 시점 = 반복 1, 501, 1001, …(반복 시작 시). 잠금 = `frozen_mask` 재사용(분할·복제·제거·통계 제외), 기울기 훅은 파라미터 교체를 감지해 재등록, 불투명도 하한은 매 반복 step 뒤, 재설정 면제는 `reset_opacity(exempt_mask)`.
- 스모크는 700회 권장(밀집화 600·700회 통과). 트레이스 캡처는 마지막 반복만(`--jbgs_capture_iterations`).

## 6. 다음 명령

```bash
# 1) 미결 2건 반영 후
docker run --rm --network none --user "$(id -u):$(id -g)" -e HOME=/tmp -e JBGS_S2_FORK=/s2/sources/GeoGS-conf-guided-v1 \
  -v "$S2:/s2:ro" -v "$PWD:/repo:ro" -w /repo --entrypoint python jointbuildgs:dev -m unittest -v tests.phd.test_stage2_conf_guided_gs_v1
docker run --rm --network none --gpus '"device=1"' --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$S2/sources/GeoGS-conf-guided-v1:/source:ro" -v "$PWD:/repo:ro" -w /source --entrypoint python jointbuildgs:geogs-conf-guided-v1 \
  /repo/scripts/phd/stage2_conf_guided_gs_v1/gpu_tests.py
# 2) 스모크(P M-N, 700회)
python3 scripts/phd/stage2_conf_guided_gs_v1/run_condition.py P_M_N --gpu 0 --iterations 700 --tag smoke700 \
  --extra --jbgs_e_interval 100 --jbgs_readout_interval 100 --jbgs_log_interval 50
# 3) λ 예비 2회(2000회, λ_prior 0.02·0.05) → 고정 → 본 11회(GPU 0/1) → 평가·대시보드·보고서
```

미작성: `evaluate.py`, `make_dashboard.py`, `render_depths.py`, `artifacts/manifests/stage2_conf_guided_gs_v1.yaml`, README, 대시보드 서빙(제안 8887).

## 7. TensorBoard 포트 6006 (사용자 허가, 2026-09-23)

현재 6006은 컨테이너 `jbgs-tensorboard-6006`(`jointbuildgs:dev`, `--logdir_spec e1e6_s2:/curated,arrgs_anchor:/anchor`)가 점유한다. 사용자: "이거 다 밀고 새로 사용해도 돼" → 새 세션에서 이 컨테이너를 내리고 2단계용으로 6006을 다시 띄운다. GeoGS `SummaryWriter`는 `model_path`에 기록하므로 `--logdir /s2/runs`(런 이름 = `<조건>/model[_태그]`)로 충분하다.

```bash
docker rm -f jbgs-tensorboard-6006
docker run -d --name jbgs-tensorboard-6006 --user "$(id -u):$(id -g)" -p 6006:6006 -v "$S2/runs:/s2/runs:ro" \
  jointbuildgs:geogs-conf-guided-v1 tensorboard --host 0.0.0.0 --port 6006 --reload_interval 60 --logdir /s2/runs
```
