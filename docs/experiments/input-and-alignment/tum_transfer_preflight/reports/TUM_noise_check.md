# P2 준비-4 — 노이즈 정리 확인 (control 4906972, proper settings)

> 📑 **P2 준비 단계** 작업입니다. 통합 명칭과 순서는 [docs/P2_index.md](../../../P2_index.md) 참조. (P2 준비-3=1c의 후속)
> **일자:** 2026-06-18 · **branch:** `feature/p2-gsjso` · **판정은 사람 — 측정·관찰까지(판정 금지).**

**목적.** P2 준비-3([TUM_tsdf_roofer_probe.md](TUM_tsdf_roofer_probe.md))에서 7k-vanilla TSDF가 Roofer를
과분할시켰다(4906972: 지붕면 **32** vs reference **3**, plane RMS 3.46 m). 이게 *학습 설정*(더 길게·고해상·
densification/pruning·라벨 불요 기하 정규화)만으로 reference 수준(≈3면)에 가까워지는지 control 1동으로 확인.
**의미 라벨·의미 prior(sem·mutual·structure)는 끄고 설정 레버만 시험.** 엔진 로직 무변경(config·분석 스크립트만).

## 설정 (1c와 데이터·범위 동일, *설정만* 변경)

| 레버 | 7k-vanilla (1c) | proper (이번) | 근거 |
|---|---|---|---|
| downscale | 2.0 (700×506) | **1.0 (1400×1013)** | depth 선명화 |
| max_iter | 7000 | **30000** | 수렴 |
| densification stop | 7000 | **25000** | 완전성 (`configs/input_and_alignment/tum_vanilla_proper.yaml:refine_stop_iter`) |
| opacity reset/prune | on | on | floater 억제 |
| w_nc (normal consistency) | 0.05 | 0.05 | 자기지도 평면화 |
| w_distort (2DGS distortion) | 0 | **0 (비활성)** | w=100 시 TUM에서 붕괴(PSNR 4.5) — 큰 metric depth로 distortion(~depth²) 폭주(MatrixCity는 ~단위스케일이라 100 OK). scene-scale 튜닝 필요, 보류(추정). |
| sem/mutual/structure | off | off | 라벨 단계 전 |
| TSDF min-obs(다중뷰 합의) | 1 | **3** | floater 추가 억제 (`tum_tsdf_extract.py --min-obs`) |

- 학습: `configs/input_and_alignment/tum_vanilla_proper.yaml`, 30000 iter / 43.6 분 / **PSNR ~14.5→~20.0** / final **N 252k→1.02M**.
- 점추출: median depth(`renderer.py:67,92`) + opacity>0.5, downscale 1, **min-obs≥3**(43.0M→9.2M voxel, 희소관측=floater 80% 제거) + SOR.
- end-to-end: 동일 경로(P0 SMRF+overlay 분류 `04_classify.py:193-224` → P0 Roofer `08_roofer_w2.py:86-105` → val3dity). EPSG:25832.

## ① before/after 비교표 (control 4906972)

| 지표 | 7k-vanilla (준비-3) | **proper (이번)** | ALS→Roofer | reference LoD2 |
|---|---|---|---|---|
| **Roofer RoofSurface 수** | **32** | **13** | 3 | **3** |
| val3dity | valid | **valid** | valid | (기준) |
| plane RMS (m) | 3.46 | **1.88** | 2.65 | — |
| floater % | 24.6 | **7.8** | 0.0 | — |
| roof 점밀도 (pts/m²) | 2923 | 1288 | 20.2 | — |
| 학습 PSNR(per-image) | ~14.5 | ~20.0 | — | — |

그림(점군 7k vs proper, top/side): [noise_4906972.png](../../../figs/tum_transfer/noise_4906972.png) — proper의 side-view가 더
얇음(수직 노이즈↓), 잔존 floater 소수.

## ② 관찰 (한 줄, 판정 금지)

설정만으로 **노이즈·과분할이 크게 감소**했다 — 지붕면 **32 → 13**, plane RMS **3.46 → 1.88 m**, floater **24.6 → 7.8%**
(val3dity는 계속 valid). **그러나 reference(3)·ALS→Roofer(3)에는 아직 못 미친다(13 vs 3)** — 설정만으로는 reference
수준 완전 수렴엔 부족.

## 판정 안내 (사람)

- 지붕면이 reference 수준(≈3)으로 내려왔으면 → 노이즈는 설정으로 잡힘 → 도구 준비 완료 → 라벨 단계.
- **이번 결과는 32→13로 크게 줄었으나 3에는 미달** → 설계상의 판정 안내대로 "**설정만으로는 부족**" 쪽. 다음은
  사람 판단: ⓐ 의미/기하-의미 prior(`L_mutual`/`L_structure`, `GSJSO_loss_audit.md`)가 면 정규화로 과분할을 더
  줄이는지(=라벨 단계 동기) 또는 ⓑ 더 깊은 원인(예: w_distort 재활성·scene-scale 튜닝, depth 일관성, Roofer 평면
  병합 파라미터)인지 진단. 측정만 제시 — 판정은 검토자.

## 재현 (EPSG:25832 · 도커 · 엔진 무변경)
```
docker compose run --rm -T dev python -m src.stage2.train --config configs/input_and_alignment/tum_vanilla_proper.yaml
docker compose run --rm -T dev python scripts/stage2/tum_tsdf_extract.py \
  --ckpt results/tum_transfer/run_proper/ckpt/final.pt --downscale 1.0 --voxel 0.05 --min-obs 3 \
  --out results/tum_transfer/analysis/tsdf_proper.npz
docker run … jointbuildgs-p0-tools:t0 python3 scripts/stage2/_tsdf_to_classified.py \
  --bid DEBY_LOD2_4906972 --tsdf …/tsdf_proper.npz --outdir phases/p0-audit/runs/tum_e2e_proper
# + compose roofer + val3dity on the proper classified LAS
```
산출(gitignore 스크래치): `results/tum_transfer/run_proper/`, `…/analysis/tsdf_proper.npz`,
`phases/p0-audit/runs/tum_e2e_proper/`(classified LAS·CityJSON·val3dity). 커밋: 본 문서 + `configs/input_and_alignment/tum_vanilla_proper.yaml`
+ `docs/figs/tum_transfer/noise_4906972.png` + 스크립트 보강(`--ckpt/--min-obs/--tsdf`). 엔진 `src/stage2/*` 무변경.
