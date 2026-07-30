# P2 인덱스 — 제안 방법 구축·효과 검증 (GS-JSO)

> 이 레포의 GS-JSO 작업은 전체 박사 연구의 **P2**에 해당한다. 그동안 "단계 1 / 1b / 1c" 같은 임시 이름을
> 썼는데, 아래 통일 명칭으로 정돈한다. **기존 문서의 파일명·본문·수치는 그대로** 두고(링크 보존), 이 인덱스와
> 각 문서 상단 배너로만 명칭을 통일한다.

## 연구 단계 (P0~P4)

| 단계 | 내용 | 위치 |
|---|---|---|
| **P0** | 입력 치환 진단 (완료) | `phases/p0-audit/` |
| **P1** | 논문 1·2장 (병렬 진행) | — |
| **P2** | **제안 방법 구축·효과 검증 (여기)** | 레포 루트 GS-JSO 코드 + `phases/p2-gsjso/` |
| **P3** | 다섯 입력 전면 비교 | (예정) |
| **P4** | 외부 확장 | (예정) |

## P2 방법 설계 (근거 문서)

- [docs/experiments/gsjso_loss_audit/reports/GSJSO_loss_audit.md](GSJSO_loss_audit.md) — **P2 방법 설계**: 구현 손실 ↔ 스케치 설계 대조 audit.

## P2 준비 (도구 적합성 점검 — 의미 라벨/prior 켜기 전 단계)

| 순서 | 활동 | 문서 | 이전 별칭 |
|---|---|---|---|
| P2 준비-1 | 엔진 전이 점검 | [docs/experiments/tum_transfer_preflight/reports/TUM_transfer_check.md](TUM_transfer_check.md) | 단계 1 / P2-2 |
| P2 준비-2 | 건물 품질·커버리지 | [docs/experiments/tum_transfer_preflight/reports/TUM_quality_coverage.md](TUM_quality_coverage.md) | 단계 1b / P2-3 |
| P2 준비-3 | TSDF·Roofer 바닥·1동 end-to-end | [docs/experiments/tum_transfer_preflight/reports/TUM_tsdf_roofer_probe.md](TUM_tsdf_roofer_probe.md) | 단계 1c / P2-4 |
| P2 준비-4 | 노이즈 정리 확인 (control 1동, proper settings) | [docs/experiments/tum_transfer_preflight/reports/TUM_noise_check.md](TUM_noise_check.md) | — |

**P2 준비 요지(누적):** 엔진은 TUM에 전이됨(준비-1). GS *센터* 점군은 ALS 대비 희박(준비-2). 표준 depth→TSDF는
밀도·모델생성을 해소해 end-to-end 유효 모델이 나오나, 7k-vanilla depth 노이즈가 Roofer를 과분할시킴(준비-3:
지붕면 32 vs reference 3). 준비-4는 그 노이즈가 *학습 설정*만으로 reference 수준에 가까워지는지 확인한다.

## P2 효과 검증 (make-or-break)

| 순서 | 활동 | 문서 |
|---|---|---|
| 효과검증 (깨끗한 라벨 arm) | sem·mutual·structure ablation (복구·품질·컴포넌트 기여) | [docs/experiments/p2_makeorbreak/reports/P2_makeorbreak_clean.md](P2_makeorbreak_clean.md) · 예전결과 [experiments/p2_mob_past_results.md](experiments/p2_mob_past_results.md) |

## 현재 상태 · 다음 순서 (세션 핸드오프)

- **P2 준비 1~4 완료** → **갈림길 ⓐ(라벨 라인) 실행 완료** = make-or-break 깨끗한 라벨 ablation([P2_makeorbreak_clean.md](P2_makeorbreak_clean.md)).
  관찰(판정 금지): **복구 8동은 어느 구성도 전부 복구 못함 — 5/8 무씨딩**(무텍스처에 프리미티브 미생성, `L_sem` geometry-isolation·mutual/structure는 기존 프리미티브만 정규화),
  **3/8은 재구성되어 sem/structure가 vanilla 0면을 유효 모델로 살림**(일부 ref 일치). **품질축: L_sem·L_structure가 정확도(RMS→ref 4.6→1.1 m)·과분할(17→7/12)·validity를 개선,
  L_mutual·both는 악화, 그러나 reference·ALS엔 미달.** 무회귀(PSNR ~20). 예전 합성결과와 방향 일치.
- **다음 시험 (사람 판단 후):** 원인규명 실험([P2_makeorbreak_clean.md](P2_makeorbreak_clean.md) §7) — 특히 **E-R3 semantic-driven densification**(라벨이 무텍스처 기하를 씨딩; 엔진변경·승인 요청), E-R4 L_sem geometry coupling. 또는 FM(예측) 라벨 arm.
- (대안) **ⓑ 설정 probe 라인** — w_distort scene-scale 재튜닝·depth 일관성·Roofer 평면병합 파라미터.

> **재사용 자산(디스크, gitignore되나 보존):** 7k ckpt `results/tum_transfer/run/ckpt/final.pt`,
> 30k ckpt `results/tum_transfer/run_proper/ckpt/final.pt`, TSDF `results/tum_transfer/analysis/tsdf_{points,proper}.npz`,
> 좌표 변환 **EPSG:25832 = GS_local + [690953,5336071,604]**. 컨테이너: `jointbuildgs:dev`(torch/gsplat/open3d) ·
> `jointbuildgs-p0-tools:t0`(laspy/GDAL·ogr2ogr/pdal/matplotlib; torch·geopandas·scipy·lxml 없음). 재사용 스크립트는
> `scripts/stage2/tum_*`·`_tsdf_to_classified.py`·`_als_decimate.py`. P0 Roofer/classify 호출은
> `phases/p0-audit/scripts/{08_roofer_w2,04_classify}.py`.

> 판정은 사람. 각 준비 문서는 측정·관찰까지(판정 금지).
