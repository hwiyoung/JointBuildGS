# GS 엔진 TUM 전이 점검 — vanilla 2DGS (P2-2)

> 📑 **P2 준비 단계** 작업입니다. 통합 명칭과 순서는 [docs/P2_index.md](../../../P2_index.md) 참조. (이전 별칭: 단계 1 / P2-2)

> **일자:** 2026-06-18 · **branch:** `feature/p2-gsjso` · **판정은 사람.**
> **목적:** GS 학습 코드가 **TUM 항공 데이터에서 수렴해 멀쩡한 3D 표면을 내는지**를 새 코드(어댑터·config만)
> 없이 가장 싸게 확인. 코드는 합성(MatrixCity)·성수동에서만 검증됐고 TUM은 미검증 — 이게 통과해야 빌드 A/B 투자.
> **범위:** vanilla(의미·mutual·structure OFF, photo+nc만). "엔진이 건물을 만드나"만 본다 — 무텍스처 복구(나중) 아님.
> 그래서 **텍스처 있는 장면**으로 보며 성공해야 정상.

## 1. 설정 (어댑터·config만, 엔진 로직 무변경)

- **데이터:** P0 TUM 자산의 undistorted COLMAP-dense 워크스페이스
  (`phases/p0-audit/data/work/mvs/colmap_dense/`, image_undistorter 산출 = PINHOLE).
  **937 뷰 · 1 PINHOLE 카메라(1400×1013, fx≈922) · 371,808 init points.**
  `.bin` 포즈가 이미 존재 → **.txt→.bin 변환 불요.** 단일 AOI(TUM 캠퍼스, 텍스처 있는 건물 다수 포함).
- **어댑터:** `scripts/stage2/prep_tum_smoke.sh` — 상대 symlink로 `ColmapDataset` 기대 레이아웃
  (`data_root/images/` + `data_root/sparse/0/{cameras,images,points3D}.bin`) 구성. 소스 읽기 전용,
  stereo/frames/rigs 미스테이징(순수 vanilla). Docker bind-mount에서 호스트·컨테이너 동일 해석.
- **config:** `configs/input_and_alignment/tum_vanilla_smoke.yaml` — `matrixcity_vanilla.yaml` 미러. `w_photo=1.0, w_nc=0.05`,
  `w_depth=w_normal=w_distort=w_sem=w_mutual=w_structure=0`, `load_semantic=false`(기본),
  `downscale=2.0`(700×506), `max_iter=7000`(3DGS 표준 조기 수렴 체크포인트), `reset_every=3000`.
- **실행:** `docker compose run --rm -T dev python -m src.stage2.train --config configs/input_and_alignment/tum_vanilla_smoke.yaml`
  (GPU1 RTX 3090, gsplat 1.4.0). **§4: 도커 기반·재현 가능(스크립트+config)·한 커밋.**

## 2. 결과 (기존 출력만 — 새 export 없음)

**수렴 로그.** 7000 iter / **29.4 분** / 3.8–4.0 it/s / 종료 rc=0 / 최종 N=252,059 Gaussians.
손실 0.55→0.21. eval PSNR(테스트뷰 평균, TensorBoard `eval/psnr`):

| iter | 1000 | 2000 | 3000 | 4000 | 5000 | 6000 | 7000 |
|------|------|------|------|------|------|------|------|
| eval PSNR | 14.74 | 15.59 | **7.44** | 15.14 | 16.14 | **6.59** | **17.08** |

→ 단조 상승. it-3000·6000의 급락은 **`reset_every=3000` opacity reset**과 정확히 일치(3DGS 정상 동작,
직후 회복). 최종(회복 후) **eval PSNR = 17.08**. 참고: 학습 tqdm의 `psnr=14.52`는 단일뷰 노이즈값(평가 아님).

**렌더 PNG** (`<out>/renders/`, 1000 iter마다 4뷰, 총 28장):
- [it1000 v0](../../../figs/tum_transfer/render_it1000_v0.png) → [it7000 v0](../../../figs/tum_transfer/render_it7000_v0.png),
  [it7000 v2](../../../figs/tum_transfer/render_it7000_v2.png).
- 장면(건물·지붕·식생)이 알아볼 만하게 렌더됨. 단 **soft/blurry + 대각 needle floater**(저반복·downscale2의
  미수렴 2DGS 전형).

**점군 스냅샷** (`final.pt` Gaussian centers, opacity>0.05 필터 179,846점, p1–p99 클립):
- [centers_top_side.png](../../../figs/tum_transfer/centers_top_side.png).
- **TOP view(x-y): TUM 캠퍼스 건물 footprint가 또렷이 식별** — 직각 건물 블록·중정·벽/지붕 모서리.
- SIDE view(x-z): 지면+건물의 일관된 수평 밴드 + 소수 고-z floater(렌더의 needle 동일 원인).
- p1–p99 extent ≈ X 574 m · Y 548 m · Z 167 m (캠퍼스 AOI 합당; 전체 bbox의 z=467 outlier는 floater).

## 3. 판정 (한 단락)

**엔진 TUM 전이 OK (PASS).** vanilla 2DGS가 TUM 실항공 데이터에서 **수렴**(eval PSNR 14.7→17.08, opacity reset
딥 제외 단조 상승, 크래시·NaN·OOM 없음)하고, **인식 가능한 건물 구조를 형성**한다 — 점군 top-view가 캠퍼스 건물
footprint를 명확히 그려내고 렌더가 장면처럼 보인다. **데이터 포맷·포즈·intrinsic 전이에 문제 없음**(.bin 포즈 직접
적재, PINHOLE undistorted 정합). 한계: PSNR 17은 modest이고 렌더는 blurry + floater가 있으나, 이는 **7k iter ·
downscale 2 · prior 없는 vanilla**라는 의도된 최저비용 설정의 품질 이슈이지 전이 실패가 아니다(30k·downscale 1·
floater pruning이면 선명해질 사안). **게이트: 쓰레기·미수렴 아님 → 빌드 A/B 진행 가능.** 실제 실험 학습은 더 긴
반복·고해상으로 권장.

## 4. 변경분 (재현)

- 추가: `scripts/stage2/prep_tum_smoke.sh`(어댑터), `configs/input_and_alignment/tum_vanilla_smoke.yaml`(config),
  `docs/experiments/input-and-alignment/tum_transfer_preflight/reports/TUM_transfer_check.md`(본 문서) + `docs/figs/tum_transfer/*.png`(증거 4장).
- `.gitignore`에 `results/tum_transfer/`(스크래치 산출·symlink) 추가.
- **엔진 로직(`src/stage2/*`) 무변경.** 출력·체크포인트는 기존 경로 그대로 사용(새 export 없음).
- 재현: `bash scripts/stage2/prep_tum_smoke.sh` → 위 `docker compose run …` 명령.
