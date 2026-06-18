# 단계 1b — 건물 단위 품질·커버리지 점검 (빌드 A 진입 판단용)

> 📑 **P2 준비 단계** 작업입니다. 통합 명칭과 순서는 [docs/P2_index.md](P2_index.md) 참조. (이전 별칭: 단계 1b / P2-3)

> **일자:** 2026-06-18 · **branch:** `feature/p2-gsjso` · **판정은 사람 — 본 문서는 측정·관찰까지(판정 금지).**
> **목적:** 단계 1(엔진 전이, 장면 전체 PASS) 이후, 빌드 A(GS→분류LAZ→Roofer)가 의존하는 **건물 단위 표면
> 품질**과 **스파이크 대상 커버리지**를 기존 `final.pt`·P0 자산만으로(새 학습 없이) 측정한다.
> **읽기 전용 분석 스크립트만**(엔진 `src/stage2/*` 무변경): `scripts/stage2/tum_qc_dump.py`(GS 컨테이너,
> torch) → `scripts/stage2/tum_qc_analyze.py`(P0 tools 이미지: laspy/ogr2ogr/matplotlib).

## ③ GS ↔ P0 좌표 정합 (선결)

- **결과: 순수 평행이동.** **EPSG:25832 = GS_local + [690953.0, 5336071.0, 604.0]**, scale [1,1,1], swap_xy=false.
  - 근거: `phases/p0-audit/data/work/opf/opf/scene_reference_frame.json`의 `base_to_canonical.shift`,
    적용 코드 `phases/p0-audit/scripts/02_opf2colmap.py:201-211`(`converted = points/scale - shift`).
  - 검증: GS centers(+shift) bbox **X[689885, 691762] Y[5335490, 5336889]**가 footprint/AOI 범위
    (x[689943, 692065] y[5333949, 5338012]) 안에 정확히 안착 → 대상 11동 모두 `in_AOI=yes`.
  - **CRS 주의(추정):** OPF는 EPSG:32632(WGS84/UTM32N) 선언, P0는 25832(ETRS89/UTM32N) — 동일 UTM32N
    수치계, 데이텀 차 ~0.5 m로 본 점검(밀도·커버리지)엔 무시 가능. footprint·ALS는 25832.
- GS는 코드상 CRS를 보존하지 않음(로컬 미터; stage2 epsg/crs grep 0건) — 위 shift가 빌드 A의 공통 선결 변환.

## ① 건물 단위 표면 품질 — GS vs ALS (텍스처 좋은 대표 = 품질 상한)

footprint로 `final.pt` centers(opacity>0.05, +shift) 클립. ALS는 같은 footprint 클립(class 6 우선).
roof density = 지면(+1.5 m) 위 점수/면적, plane RMS = 상부점 SVD 평면 잔차, floater% = roof 기준 +3 m 초과 점 비율.

| building | area_m² | src | n_pts | roof_dens(pts/m²) | roof_plane_RMS(m) | floater% |
|---|---|---|---|---|---|---|
| 4906972 | 371 | **GS** | 644 | **1.48** | **3.20** | **33.5** |
| 4906972 | 371 | ALS | 8012 | 20.16 | 2.65 | 0.0 |
| 4906969 | 173 | **GS** | 55 | **0.32** | **0.72** | 0.0 |
| 4906969 | 173 | ALS | 3407 | 18.20 | 1.71 | 8.2 |
| 4908023 | 22 | **GS** | 2 | **0.09** | n/a | 0.0 |
| 4908023 | 22 | ALS | 448 | 18.48 | 0.24 | 0.0 |

그림(점군 top/side, GS 윗줄 vs ALS 아랫줄):
[4906972](figs/tum_transfer/qc_4906972.png) · [4906969](figs/tum_transfer/qc_4906969.png) · [4908023](figs/tum_transfer/qc_4908023.png).

**관찰(판정 금지):**
- GS(vanilla, 7k, downscale 2) 지붕 점밀도 **0.09–1.48 pts/m²** = ALS(**18–20**, known-good Roofer 입력)의
  **약 1/13 ~ 1/200**. 작은 건물(4908023, 22 m²)은 GS 2점으로 사실상 비어 있음.
- GS는 수직 확산(4906972: plane RMS 3.20 m·floater 33.5%; 그림에서 z 스프레드 ~10 m)이 큼 — ALS는 얇고 조밀.
  4906969는 GS RMS 0.72 m로 깨끗하나 55점으로 희박.
- 즉 **현 설정의 GS 건물 점군은 ALS 대비 희박하고 floater가 섞여 거칠다**(밀도·노이즈 동시). "Roofer-gradeable
  인가"는 사람 판정 — 측정만 제시.

## ② 스파이크 대상 커버리지 (8동 실패 + 텍스처 후보)

footprint 중심(ALS 지붕 z 사용)을 937 .bin 포즈로 재투영 → 프레임 내·전방 뷰 수, 그리고 building→camera 시선의
연직 대비 off-nadir 각(near-nadir <20°). 카메라 광축 tilt 분포(진단): p5/50/95 = **0.4°/30.5°/74.9°**(nadir+oblique 혼합).

| building | group | in_AOI | n_views | near-nadir(<20°) | oblique(≥20°) | median off-nadir |
|---|---|---|---|---|---|---|
| 42364609 | fail8 | yes | 140 | 2 | 138 | 72.1 |
| 42364659 | fail8 | yes | 107 | 22 | 85 | 37.9 |
| 42364663 | fail8 | yes | 269 | 12 | 257 | 51.6 |
| 4907182 | fail8 | yes | 142 | 2 | 140 | 68.8 |
| 4907510 | fail8 | yes | 135 | 7 | 128 | 50.4 |
| 4908050 | fail8 | yes | 128 | 1 | 127 | 74.3 |
| 4908166 | fail8 | yes | 141 | 2 | 139 | 72.3 |
| 4908176 | fail8 | yes | 158 | 3 | 155 | 59.1 |
| 4906972 | textured | yes | 226 | 20 | 206 | 56.3 |
| 4908023 | textured | yes | 268 | 21 | 247 | 46.6 |
| 4906969 | textured | yes | 345 | 13 | 332 | 55.5 |

**관찰(판정 금지):**
- **대상 11동 전부 AOI 내**, 동당 107–345 뷰로 커버 — 커버리지 자체는 결손 없음.
- 단 **near-nadir(지붕 평면측량에 유리) 뷰는 희박(1–22/동)**, oblique 지배(median off-nadir 38–74°). 카메라가
  지붕 위 ~31 m로 낮고 oblique 비중이 커 한 건물을 보는 뷰가 대부분 비스듬하다.
- 무텍스처 실패 8동은 텍스처 대표 3동보다 near-nadir가 더 적고 더 비스듬한 경향(예 4907182: near-nadir 2,
  median 68.8° vs 4906972: 20, 56.3°) — 표본 작아 경향만.

## ④ (조건부) 고반복 1동 재학습 — **미실행**

①·②가 애매하지 않아(커버리지 충분, 품질은 현 설정에서 ALS 대비 명확히 희박·거침) 규칙상 생략 가능 →
**미실행**. 단 GS 엔진은 장면 단위 학습이라 "1동 재학습"=전 장면 downscale1·30k 재학습(추정 멀티-시간)이라 비용도
큼. 현 설정 점군이 빌드 A에 부족하다면, "더 긴 반복·고해상·floater/opacity pruning이 ALS 수준 밀도·청결도로
좁히는가 + 건물당 예산"은 사람 판단 후 별도 probe로 권장(여기선 비실행). 새 학습 최소 원칙 준수.

## 재현 (EPSG:25832 · 도커 · 엔진 무변경)

```
# 1) GS centers 덤프 (GS dev 컨테이너, torch)
docker compose run --rm -T dev python scripts/stage2/tum_qc_dump.py
# 2) 품질·커버리지 분석 (P0 tools 이미지, 전체 레포 마운트)
docker run --rm -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS \
  jointbuildgs-p0-tools:t0 python3 scripts/stage2/tum_qc_analyze.py
```
산출(스크래치, gitignore): `results/tum_transfer/analysis/`(gs_centers.npz·geojson·figs). 커밋 산출: 본 문서 +
`docs/figs/tum_transfer/qc_*.png`. 엔진 `src/stage2/*` 무변경, 기존 `final.pt`만 소비.
