# 세션 핸드오프 (rolling) — 새 세션 시작 시 이 문서부터 읽기

> 갱신 2026-06-23. 직전 작업 브랜치 `feature/p2-semantic-seed`. 사람 검토자=김휘영.

## 0) ⚡ 진행 중 백그라운드 (2026-06-23, P2 make-or-break v6 "MVS-seed가 raw MVS→Roofer를 이기나")
> 커밋 `caa3377`(빌드)·`e7c721d`(raw arm)·`19a9edc`(Phase4 tooling), 모두 `feature/p2-semantic-seed`.
- **GS arm** (`run_mob_v6.sh`, GPU, ~5–6h): gs_seed_{sparse,dense,acmp} 학습→TSDF→eval. 완료=`results/tum_transfer/mob/V6_PIPELINE_DONE`. log=`mob/v6.log`·`mob/train_gs_seed_*.log`.
- **raw arm** (`run_mob_v6_raw.sh`, CPU, ~1h): raw {sparse,dense,acmp,lidar}→동일 tum_mob_eval. 완료=`mob/V6_RAW_DONE`. log=`mob/v6_raw.log`.
- **Phase 4 (둘 다 끝난 뒤 1줄)**: `bash phases/p2-gsjso/scripts/run_mob_v6_table.sh matched` → `mob/REPORT_v6.md`(8-way: RoofSurface·RMS→ref·val3dity·solid)+`table_v6.csv`.
- 설계 핵심: 씨드=concat(SfM 372k + AOI MVS ~3M, voxel0.40); **geoid: dim −604(타원체)·acmp −556(정사고)**; raw arm은 ellipsoidal로 통일(acmp/als +48). Phase2 pre-check PASS(detach 해제 grad≠0). 관찰만, 판정=사람.

---
> (이전) 직전 작업 브랜치 `feature/p2-semantic-seed`(origin 동기화됨). 사람 검토자=김휘영.
> 영속 메모리(`MEMORY.md` + `project_*.md`)는 세션 시작 시 자동 로드됨 — 이 문서는 그 위의 **진행상태·다음할일** 인계.
> 규칙: 관찰·수치까지만, 합/불·결론은 사람. EPSG:25832 · Docker(`jointbuildgs:dev` 학습 / `jointbuildgs-p0-tools:t0`·`3dgi/roofer` 진단).

## 1) 이번 세션 산출 (전부 커밋·푸시됨)
| 작업 | 결과 | 커밋 |
|---|---|---|
| P0 완전성 재검증 | 생성-실패 64동 중 **ACMP MVS로 20/64 회복**(cloud lever; Roofer-param 단독=0). 44 미회복 | `ec58090` |
| P0 조립실패 원인 진단 | **Roofer 백엔드 무죄**(ALS@동일Roofer 64/64). 실패=입력측: SMRF가 ACMP 지붕 ground로 먹음(force-build 17→**42/64**) + 잔여 ~22 cloud-limited(dens~4) | `fcb79fe` |
| repo 정리 (재현성) | 루트 `env/versions.md`·Dockerfile.acmp·P2 issues.md·자산 커밋 + main/feature push | `e28705b d70250f 605b692` |
| repo 정리 (정돈) | phase1/2/3 추적그림 111개 ~390MB 추적해제(history 무변경) + 참조無 구단계 3개 archive | `ac822e5 0fa16bb` |
| 무텍스처 신호진단(보류) | 스크립트 분리 보존 | `21054f4` @ `wip/textureless-signal` |

상세 보고: `docs/experiments/p0_completeness_reverification.md`, `docs/experiments/p0_assembly_failure_cause.md`.
데이터(gitignore): `results/tum_transfer/mob_analysis/p0c_step2/eval/*`.

## 2) 미결·보류 (다음 후보)
- **무텍스처 신호진단 C 마무리** — geoid 보고방식 결정 대기(사람). 스크립트는 `wip/textureless-signal` 브랜치. 재개 시 거기서 이어감.
- **P0c 후속 (택1)**: (a) force-build를 footprint-aware 분류로 정식화해 64동 재측정 / (b) cloud-limited ~22동에 full-res ACMP·다른 MVS / (c) full-res SMRF로 no_points 회복 천장 확정(~35min+).
- **repo 정리 잔여**: 참조 있는 19개 구단계 archive는 보류(옮기면 scripts 출력경로 깨짐=별건). 잔존 추적 PNG 15개(~9MB, FC_S6*/stage3_typed_readout/synthetic_a) 미처리.
- **P2 본류 복귀**: make-or-break 이후 GS-JSO 효과검증(L_mutual/L_structure/L_sem) — 메모리 [[p2-makeorbreak-run]]·[[p2-semantic-seed-impl]] 참조.

## 3) P2 재사용 자산 (경로)
- 엔진: `src/stage2/{train,renderer,semantic_seed,model}.py` (renderer `sem_detach_geometry` 플래그)
- configs: `configs/tum_mob/*.yaml`(vanilla/baseline/mutual/structure/both/seed_semantic/depth_release_{range,oracle}), `configs/tum_gravity.json`
- P0c 어댑터(재사용): `phases/p2-gsjso/scripts/p0c_{run_roofer.sh,roofer_eval.py,assembly_diag.py,acmp_*,als_aoi}` — 임의 클라우드를 P0 동일 Roofer/val3dity harness에 투입
- 라벨/클라우드(gitignore): `results/tum_transfer/clean_labels_geoidfix/semantic`, `…/p0c_step2/{acmp_classified,als_aoi,acmp_forcebuild}.laz`
- 이미지 digest: `env/versions.md`(GS-JSO·acmp), `phases/p0-audit/env/versions.md`(colmap/roofer/tools)

## 4) 핵심 좌표계/datum 메모 (재확인 필수)
- GS-local = EPSG:25832 − [690953, 5336071, 604] (ELLIPSOIDAL). Munich geoid ≈ +48 m.
- ortho-UTM 변환: `z_ortho = z_local + 556`(=604−48) → ground ~514(=LoD2 HoeheGrund). 생성률은 geoid-불변.

## 5) 진행 방법
- **이 핸드오프 + 메모리**로 충분; 더 깊은 맥락은 `docs/experiments/p0_*.md`·`phases/p2-gsjso/docs/issues.md` Read.
- 전체 verbatim 필요 시 직전 세션 resume(transcript jsonl). 새 작업 지시 시 이 문서 갱신할 것.
