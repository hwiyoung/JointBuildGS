# 세션 핸드오프 (rolling) — 새 세션 시작 시 이 문서부터 읽기

> 갱신 2026-06-24. **현재 작업 브랜치 `feature/p2-seed-protect`**(C 엔진변경+C2+B2). v6/raw는 `feature/p2-semantic-seed`. 사람 검토자=김휘영. 관찰만, 판정=사람.

## 0) ⚡ P2 make-or-break v6 진단 체인 — 전부 완료 (2026-06-24). 미푸시, 로컬 커밋만.
> 질문: "MVS-seed GS 공동최적화가 raw MVS→Roofer를 이기나" + 왜/어디서 막히나. 데이터(`results/`·`phases/p0-audit/data/`)는 gitignore.
> **브랜치**: `feature/p2-semantic-seed`에 v6 빌드·raw·overseg·density·no_points(caa3377→46bd821). `feature/p2-seed-protect`에 C 엔진(c39c15c)·C2(1fc7e1f)·B2(4089036).

| # | 작업 | 결과(관찰, 판정=사람) | 보고서/커밋 |
|---|---|---|---|
| v6 | 8-way(GS-seed vs raw vs LiDAR) | GS-seed **R-solid 2–3/8** vs raw MVS 1–2/8 vs LiDAR 7/8. dense/acmp 씨드가 prune로 226k/281k 붕괴(생성축 오염) | `REPORT_v6.md` / caa3377·e7c721d·19a9edc |
| 과분할 | GS가 raw보다 facet 많음 원인 | (나)Roofer 임계 우세(GS 표면 매끈한데 과분할); 밀도정합해도 facet 유지=**저주파 waviness**(밀도 아님) | `docs/W3_overseg_diagnosis.md` / 81230a3·a520204 |
| no_points | 영상 0점 46동 분해 | **c near-nadir 결손 36** + b5/d3/e2. a(미촬영)0. ALS 46/46 관측 | `phases/p0-audit/docs/W4c_no_points_breakdown.md` / 46bd821 |
| **C** | 씨드보존 재실행(엔진, 승인됨) | 씨드 보존(2.95M, v6 붕괴와 대비)**해도 생성밴드 0/5 미회복**. 보존 씨드 op≈0 | `REPORT_v6_protect.md` / c39c15c·60b52a9 |
| (리뷰) | C 결론 적대검증 | 원 "thin-evidence"=**과장**. 입력엔 점 있음(raw_dense). 진짜 기전=**opacity 붕괴→alpha 게이트 탈락** | (워크플로) |
| **C2** | opacity 진단(alpha 우회) | op median **3.8e-3**(96% 투명). **우회 시 지붕점 회복**(dense 4/5, RMS→ref 0.2~0.5m=위치 정확)나 **조립은 cloud-limited**(raw_dense도 미조립, LiDAR밀도만). densification은 C서 v6 dense **유지(변경X)** | `docs/W_opacity_diag.md` / 1fc7e1f |
| **B2** | 동시취득 데이터 귀속 | no_points 41/46(34/36 near-nadir)= **취득/커버리지 한계**(동시취득 ULS-nadir도 미커버, Bavaria-ALS만 46/46). 내 파이프라인特有 4, MVS일반 1 | `docs/W4d_coacquired_crosscheck.md` / 4089036 |

**종합(판정 재료)**: 영상-유래 실패 = ① **취득**(L2 나디르 커버리지 결손, 동시취득 LiDAR로도 미회복=재촬영/완전측량 필요) + ② **파이프라인**(GS opacity 붕괴→점 안보임[고칠 수 있음] + raw도 미조립하는 cloud/구조화 한계). GS-seed가 raw 약간 상회하나 LiDAR 미달.

**다음 후보(미착수, 판정=사람)**: (a) **opacity floor/detach** 실험(C2가 가리킨 fix; 점은 회복되나 조립엔 L_structure/더 조밀 증거 필요) — 엔진변경, feature/p2-seed-protect. (b) 내 파이프라인特有 4동(Pix4D 복원) 회복. (c) 브랜치 정리/머지·v6 판정(사람). (d) 보류: 무텍스처 신호진단(`wip/textureless-signal`).

**재사용 자산**: 엔진 `SeedProtectStrategy`(densification.py, gsplat fork 없음·state["is_seed"]). bypass `c2_dump_means.py`. B2 번들 `phases/p0-audit/data/raw/tum2twin/`(ULS/Pix4D, EPSG:32632). eval 하네스 `tum_mob_eval.py`(matched)·`tum_mob_ref_rms.py --arms`·`run_mob_v6{,_raw,_protect,_table}.sh`. 8-way 정합용 raw/LiDAR/ref는 `eval_v6_raw.json`·`baselines.json` 재사용.

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
