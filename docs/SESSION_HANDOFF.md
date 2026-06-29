# 세션 핸드오프 (rolling) — 새 세션 시작 시 이 문서부터 읽기

> ⚡⚡⚡⚡⚡⚡⚡⚡ **assembly-fidelity (조립 표적 3동 충실도) 완료 (2026-06-29, `feat/p2-fidelity`, 커밋 `9a8772f`, 미푸시)** — 재사용·재구성 없음, 관찰만, 판정=김휘영. 본보고 `docs/W_assembly_fidelity.md`(+G1_package, 그림 6동). 재현 `assembly_fidelity.py`.
> 질문: raw MVS(DIM)가 0면으로 조립 못 한 3동(**42364659·42364663·4907510**)을 GS-JSO가 조립함 — ALS만큼 충실한가(높이·형상·면수·닫힘)? **⚠ 1차 헤드라인이 적대 3-렌즈 재검으로 뒤집혀 정정됨(§0)**: ① **단일 엔벨로프-중앙값 높이는 단차(다층) footprint에서 인공산물** — 42364659 "+7.2m 과건축"·4907510 "−4m 저건축"은 **중앙값이 어느 클러스터에 앉느냐의 산물(점밀도)**, 물리적 과/저건축 아님 → **ridge-top(p95) like-for-like 높이**로 정정: 전 6동 GS−ALS **−2.19~+1.01 m(~±2m 내 ALS 추종)**. ② **full-class6 RMS→ref는 facade 지배(지붕 충실 지표 아님)** → **facade 제거 roof-env RMS 전 행 대칭 적용**. **답(GS vs ALS vs 참조, 정정본)**: ⓐ **위상 승리 실재** = DIM이 못 한 **동별 닫힌 2-다양체 3/3**(35·6·37면)**나 clip-val3dity 1/3**(42364659만)·완전성=coverage(충실 아님). ⓑ **높이 like-for-like ~±2m로 ALS 근사 3/3**(단봉 대조 3동은 일관 ~1.5~2.2m 낮음; 42364663 단봉 중앙값 +0.25=일치, 이 ~−1.7m 편향의 예외). ⓒ **지붕면 충실=진짜 격차** — facade 제거 roof-env RMS는 GS가 ALS 동급 **2/6뿐**(4906972 0.26≈0.27·42364663 1.36≈1.27), **3동 1.7~2.6× 더 거칢**(4907510 2.6×·4908023 2.4×·4906969 1.7×). ⓓ **과분할 4/6**(6v2·6v1·14v3·2v1). **판정표(§5, 기계대입·최종=김휘영)**: **42364663=충실 후보**(높이·표면·면수 ALS급, 유일), **4907510·42364659=부분**(높이 근사·표면 2.6×/판정불가·과분할). **한 줄: "조립됨 ≈ 위상·높이는 근사, 표면·면수는 ALS 미달" — 표적 닫힘 3/3·ridge높이 ~±2m 3/3·facade제거 지붕RMS ALS급 1/3·면수일치 1/3**. 검증=적대 3렌즈(datum/numeric/methodology) 독립 재유도 일치, must-fix 2·should-fix 4 전부 반영. D6-textureless(저편향 평슬랩)와 정합하나 본건은 **중앙값-인공산물을 ridge로 분리**한 점이 핵심 교훈.

> ⚡⚡⚡⚡⚡⚡⚡ **D6 textureless-fidelity (무텍스처 4동 충실도) 완료 (2026-06-29, `feat/p2-d6-curved`, 커밋 `7780b5b`, 미푸시)** — 재사용·재구성 없음, 관찰만, 판정=김휘영. 본보고 `docs/W_D6_textureless_fidelity.md`(+G1_package, 그림 4동).
> 질문: GS 조립 무텍스처 4동(42364609·4908050·4908166 평 + 4907182 외쪽)이 충실한가 평슬랩 추정-채움인가. **답(GS vs ALS vs 참조)**: **높이 0/4 충실 — 4동 전부 GS 지붕이 ALS보다 ~2.3~3.1 m 낮음**(저-편향; geoid 동별 ~48 일관→ALS 높이정합, GS만 낮음). **형상 평 3동=GS 평면 충실**(RMS→ref 0.03~0.13≈/<ALS; 단 평슬랩이 평지붕에 우연히 맞음=약한 충실, ~2.5m 낮음). **외쪽 4907182=GS가 ~21° pitch(참조 facet 21.3°·ALS roof-only 21.4°; ALS env 28°/RMS→ref 1.73은 ~6m 가장자리블록 19% 오염값)를 0°·면1로 뭉갬(추정-채움)**. DIM 13~502점, GS valid 1/4. **한 줄: "조립됨 ≠ 충실" — GS 무텍스처=footprint 위 ~2.5m 낮은 평슬랩; 생성(7/8)은 조립·footprint·평탄성만 약하게 받침, 높이·비-평 구조 충실 X**. D6-provenance(희박 MVS+L_sem visual-hull 견인→깊이모호·저편향)와 정합. 재현 `d6_textureless_fidelity.py`. 검증=적대 2검 ok·must-fix 0.

> ⚡⚡⚡⚡⚡⚡ **D6 provenance (단서 출처 코드 점검 A) 완료 (2026-06-29, `feat/p2-d6-curved`, 커밋 `1cf89c7`, 미푸시)** — 읽기 전용 코드 감사, 관찰만, 판정=김휘영. 본보고 `docs/W_D6_prior_provenance.md`(+G1_package 사본).
> **질문**: 무텍스처 회복(GS 7/8)이 "정답(LoD2) 쓴 순환"인가. **답(file:line)**: ① 씨앗=`seed_dense.ply`←`dim_v1.laz`(DIM/MVS); 런타임 carve+**LoD2 높이 band**(`seed_depth_bands.py` HoeheGrund/HoeheDach→bands_file)는 `seed_semantic` 게이트(train.py:313) 하위=depth_release/seed_semantic.yaml 전용, **gs_d4/gs_prior_full 둘 다 미설정→레포 유일 LoD2-z lever도 D-수트 dead code**. ② depth/normal=COLMAP MVS. ③ 구조=GS detach; **의미 L_sem=clean_labels(LoD2 GML 레이캐스트 픽셀 CLASS, z 없음)**, ⚠ **`sem_detach_geometry:false`(gs_d4:62·prior_full:58)라 L_sem이 GS 기하로 역전파**(renderer.py:127-136)→표면이 LoD2 다시점 클래스투영(visual-hull)으로 견인. ④ footprint=crop/log/metrics only. ⑤ read-out/추출=GS 점·GS 의미·ground z=GS데이터; LoD2 z 0.
> **한 줄(판정=김휘영)**: **LoD2 z 값 직접 순환 없음**(씨앗·depth·read-out 비모델; 무텍스처도 MVS 씨앗 99~825점 비-0). **단 표면 기하가 LoD2-레이캐스트 클래스투영 supervision에 부분 결합**(sem_detach_geometry=false, MVS 희박할수록 비중↑=무텍스처 최대) = z 복사 아닌 부분 참조-의존. **D6 shape-audit의 "LoD2-band prior/seeding" 추정 정정**(코드상 band/seeding 없음). 검증=적대 2검 ok·must-fix 0.

> ⚡⚡⚡⚡⚡ **D6 shape-audit (11동 형상 눈 검증) 완료 (2026-06-29, `feat/p2-d6-curved`, 커밋 `c316a76`, 미푸시)** — 관찰만, 판정=김휘영. 본보고 `docs/W_D6_shape_audit.md`(+G1_package 사본, 11패널+y-slice). P0 재사용·재구성 무.
> **형상 라벨 대거 정정(눈+측정; 곡면 0동)**: **4906969 "곡면"→단차/계단 평지붕**(반원 footprint, 참조 3 수평레벨 523.7/526.7/530.2; ALS y-slice 3-step RMS 0.54 ≪ 호 1.21 → 곡면은 평면도 곡선, 지붕은 단차 평). 4906972 "평"→**박공**(참조 3100·24/35/35°). 42364659·42364663 "복합"→**평지붕**("복합"=재구성 과분할 거동). 4908023 대조=평. → 눈대중 라벨 재구성 5동 중 4동 오라벨, **곡면(3700) 0동**(survey와 일관). D6 step0 4906969 과분할은 곡면 지붕 아니라 반원가장자리+단차+GS조밀.
> **생성표(캐노니컬 mob, gssem, target-only 현 디스크 재계산)**: R-set raw(DIM) **0/8 → GS-JSO 7/8 → ALS 7/8**(GS 실패=4908176만·ALS=42364659만); GS 무텍스처 5동 중 4동도 조립(prior, D-수트 맥락); valid-solid 클립단위·GS 다수 invalid(위상). **주의: `d5_target_facets.csv` stale(requal 이전)→현 디스크 재계산 사용**(W_D5 §5와 일치).
> **하네스 정합**: survey(w3_2b) vs 캐노니컬(mob) 면수 다름(4906969 ALS 4 vs 5·DIM 11 vs 17)=분류/클립/MVS/Roofer 인스턴스, 하네스 내 비교만. 재현 `d6_shape_audit.py`·`d6_genstatus.py`. 검증=적대 워크플로 3검 ok·must-fix 0.

> ⚡⚡⚡⚡ **D6 survey (곡면 건물 전수 조사) 완료 (2026-06-27, `feat/p2-d6-curved`, 커밋 `1fcd9cd`, 미푸시)** — 관찰만, 판정=김휘영. 본보고 `docs/W_D6_survey.md`(+G1_package 사본). P0 통제 93동 재사용(재구성 무재실행).
> **전제 뒤집힘(중요)**: 참조 `<bldg:roofType>`·LoD2 기하가 관찰 라벨과 불일치 — **4906969(관찰 "곡면")=1000 Flachdach·3 수평면**, 4906972(관찰 "평")=3100 박공, 42364659=1000. **통제 93동에 참조-곡면(3700 Bogendach) 0동** → "곡면 유형 전반" 검증 불가(표본 0). P0 T14도 4906969를 "ALS 4 vs DIM 11, 노이즈"로 규정(곡면 아님) — "곡면"은 P2(D4/D5) 관찰 라벨. issues 기록 `phases/p2-gsjso/docs/issues.md`.
> **과분할 census(93, target-only, w3_2b ALS/DIM)**: 유형분포 평40·경사48·곡면0·복합1·기타4. **광범위·유형무관**: DIM>ref 57/85(4906969=20/85위, 중상위), ALS(LiDAR)>ref 54/92. 참조 대비 초과=영상·LiDAR 공통(coarse 참조)+**DIM 고유 초과**(불일치 52동 DIM>ALS **37 vs 15**·평균 +2.79·4906969 제외 36 vs 15) → 영상이 LiDAR보다 전반적으로 더 쪼갬; **4906969(DIM11·GS13≫ALS/LiDAR4~5)는 그 영상-고유 추세의 꼬리**(=D6 step0 입력측 성분), 고립 아님.
> **한 줄(판정=김휘영)**: 곡면 과분할은 4906969 고립도 "곡면 유형"도 아님 — 참조 대비 과분할은 유형무관 광범위(LiDAR 포함)+DIM 고유 초과. 재현 `d6_survey.py`. 검증=적대 워크플로 3검 ok·must-fix 0.

> ⚡⚡⚡ **D6 step0 (곡면 과분할 청정 재진단) 완료 (2026-06-27, `feat/p2-d6-curved`, 커밋 `105da76`, 미푸시)** — 관찰만, 판정=김휘영. 본보고 `docs/W_D6_overseg_diag.md`(§0 무결성+§2~4 a/b/c+§6 레버 지시). 그림 `docs/figs/W_D6/`.
> **§0 무결성**: v6 과분할 진단(`W3_overseg_diagnosis.md`)은 **SMRF** 분류 지붕점을 읽음(코드증거 8건: `--classifier`는 0e43d37 신설·v6는 `_mob_prep_las.py`=filters.smrf·v6 `gs_seed_*` 미-requal·mtime 06-23<gssem코드 06-25). → 옛 v6 결론 **‘보류’**(단 gssem 청정 재진단이 "GS 안 거침" 정성 방향 재현). matched_rms와 동형 오염.
> **곡면 4906969 격차(GS 10~14 vs LiDAR 5) 분해(gssem 정본·smrf 병기, 대조 42364659·4906972)**: (a) 입력거칠기 GS localRMS 0.30≈LiDAR 0.28(밀도정합 0.26)=**고주파 거칠기 아님**; (b) 밀도 GS **~33×**(638 vs 19/m²), 밀도 솎으면 면수 **14→1 붕괴**(밀도 결합, 단 voxel 과평탄→LiDAR 5 재현 아님=한정증거); (c) Roofer eps 0.2~1.2·min-pts 15~60 전구간 **GS 9에서 바닥(>LiDAR 5)**·격차비율 보존=**분할 임계로 미해소**. 정합 sanity: eps0.3 → GS_dense 14·LiDAR 5(=D5 §5 재현).
> **레버 지시(판정=김휘영)**: 격차 주성분=**입력측(GS 곡률/밀도)**; **Roofer 분할 임계 노브 단독은 비지시**(전역 둔화·정확도 손실·초과분 미제거; 단 GS밀도×Roofer 평면검출 민감성 상호작용 가능성은 미배제). D5 §5 두 후보 중 곡률-G2 쪽 지시. **다음(step1+)**: 곡률 기반 G2/밀도·곡률 인지 read-out 설계, 또는 면-기하 공간중첩(step0 caveat=카운트기반).
> 재현: `bash phases/p2-gsjso/scripts/run_d6_step0.sh`. 검증=적대 워크플로 3검(무결성·수치·방법론) ok·must-fix 0. CSV `analysis_pack_d6/`(gitignore).

> ⚡⚡ **D5 (cp ablation) 완료 (2026-06-27, feature/p2-prior-full)** — 본런 6 arm + gssem 재평가 + §5 cp 판정표 끝. 커밋 "D5".
> 사양·사전등록(LOCKED §5) = `P2_D5_cp_ablation_사양_사전등록_20260626.md`. 본보고 = `docs/W_D5.md`(§0 사전점검 + §2~ cp 판정표 gssem|smrf + §5 기준 대입).
> **판정 (김휘영): (다) 부분 레버** — cp 끄면(D5a) D4 대비 생성·valid-solid 하락(cp 기여 확인=de-noise 단독 기각); 단 세게/일찍의 복합 과분할 감소는 혼재, 곡면 4906969은 cp 강도 무관 9~16면(LiDAR 5 미달)=cp 밖 문제. 함의: cp 유지 + 다음 레버=곡률기반 G2/Roofer 분할 임계.
> **read-out 정합(중요)**: eval이 arm당 gssem→smrf 순차라 per-building las/cityjson/val3dity가 smrf로 덮임 → D·D4·D5 모두 **gssem 재평가**로 정정함(`run_gssem_requal.sh`·`run_d5_gssem_requal.sh`; 디스크 최종=gssem, smrf=`gssem_requal_backup/` 백업, 생성수치 불변 검증). 보고 `W_gssem_requal.md`. matched-n 분석 `W_matched_rms.md`, 결과통합 `W_results_consolidation.md`.
> ⚠ **교훈(다음 적용)**: ① 장시간 학습은 harness `run_in_background` 금지(세션 teardown 시 죽고 docker stdout 파이프 끊겨 train.py 멈춤=로그 동결되나 ckpt는 진행) → **`setsid nohup` detached + ckpt mtime/util로 진척 확인**(로그만 믿지 말 것; 1차 D5b ~20k서 함정). ② **train.py resume 없음** → kill/정전 시 0부터(GPU 양도로 D5b acmp ~24k 손실) → D5 후 full-state ckpt+auto-resume 도입 예정([[project-train-resume-todo]]). ③ requal 백업 tar엔 `.las` 미포함(용량) — smrf 점은 deterministic SMRF로 temp 재생성.


> 갱신 2026-06-26. **현재 작업 브랜치 `feature/p2-prior-full`**(D 전체 prior 수트 + **D4 corrected** 재학습; D4 **커밋됨**, 미푸시). 이전: `feature/p2-seed-protect`(C/C2/B2), v6/raw는 `feature/p2-semantic-seed`. 사람 검토자=김휘영. 관찰만, 판정=사람.

## 0″) ⭐ D4 — 정규화 재학습 (corrected, "cp만 정규화") — 완료 (2026-06-26, `feature/p2-prior-full`, **커밋 "D4"**, 미푸시).
> 질문: "손실 균형을 바로잡으면(노이즈 depth/normal 제거 + cp 탈-지배) GS 지붕이 펴지고 과분할↓되, 생성 7/8·무열화는 유지되나 — 품질을 GS 방법으로."
> **본보고**: `docs/W_D4.md`(2축 8-way + §6 판정 패키지). **사양·사전등록(LOCKED)**: `P2_D4_사양서_사전등록_20260625.md`(§6 판정기준·§7 cp 사다리). 그림 `docs/figs/W_D4_qual/`.

- **config = corrected cp-only normalization** (엔진 무변경, 가중만): cp eff **0.08→0.01**(탈-지배, cp share 68%→31%≈photo)·depth **0.1→0.03**(de-noise CV 1.74)·normal **0.15→0**(노이즈 제거); **photo 1.0·nc 0.05·sem 0.1·na 0.08 = D 유지**(건강항). `configs/tum_mob/gs_d4_{dense,acmp}.yaml`. ⚠ 초기 D4는 전-항 정규화(photo 5.6·nc 2.1) 과적용→photo 열세→김휘영 정정(config 오류 정정, 골대이동 아님).
- **학습**: `run_d4.sh`(2-GPU 병렬, idempotent skip-train→extract→eval), 30k 완료, **PSNR 20.08/20.15**(D 19.87/19.99 무회귀). commit 5dd26cc 시점.
- **결과(관찰, 판정=사람)**: ① 품질↑ — 평지붕 4906972 **면 3=ref**(target-only)·**RMS→LiDAR 수렴**(2.41=2.41 vs D 2.79); **RMS→ref 개선**(dense 2.83→**2.25**·acmp 2.53→**1.65**, acmp가 v6 1.89 상회·LiDAR 1.40 접근 = **D-수트 최초 LiDAR 방향 이동**); 곡면 4906969 19→13면 **비-과평탄**(RMS 0.76, 곡선 보존). ② 생성 **7/8 유지**(=D=LiDAR, 깊이 0.03에도). ③ 무열화 OK(제어 RMS↓·PSNR≥D). **④ 대가 = valid-solid(dense) 4→2 회귀**(위상; acmp 3=3). cp는 발화했으나 펴짐 동력은 **depth-denoise**(cp 압력 아님).
- **메트릭 주의(내가 발견)**: eval over-seg 메트릭 = **클립-이웃 건물 오염**(4906972 eval 8/12 vs target-only 3). W_D4는 target-only 사용. D 보고(W_D_prior_full) 합산 수치와 직접 비교 시 유의.
- **⚡ NEXT = 판정(김휘영)**: 사전등록 §6 성공조건 1–5 **충족방향** but valid-solid-dense 회귀 = **부분지지** 신호 → 성공 vs 부분지지 판정. 부분지지면 §7 cp 사다리(cp 이미 발화→불발동) 또는 **valid-solid/위상 후속**(roofer 1.0.0 위상수리 플래그 無). **커밋 "D4" 완료**(`feature/p2-prior-full`, 미푸시; P2_D4_사양서·configs gs_d4_*·run_d4.sh·d4_table.py·d4_qual_figs.py·docs/W_D4.md·figs/W_D4_qual/. results/ data는 gitignore=재생성).
- **재사용**: 표 `d4_table.py`→`REPORT_D4.md`; 그림 `d4_qual_figs.py`; RMS `tum_mob_ref_rms.py --arms gs_d4_{dense,acmp}`→`ref_rms_d4.csv`; eval `eval_d4_{gssem,smrf}.json`. baseline 재사용: `eval_prior_full_gssem.json`(D)·`eval_v6_{protect,raw}.json`·`baselines.json`·`ref_rms_{D,v6,raw}.csv`.

---

## 0′) ⭐ D 전체 prior 수트 + 후속 진단(D2/D3/D4) — 완료 (2026-06-25, `feature/p2-prior-full`, 미푸시).
> 3 레버 ON(L1 depth/normal 감독 + L2 structure-G2 + L3 GS-의미 분류) vs v6(prior off). 엔진 변경 격리.
> **보고서**: `docs/W_D_prior_full.md`(본보고·2축·G1) · `W_D_loss_audit.md` · `W_D_followup_audit.md` · `W_D2_D3.md` · `W_D4_precheck.md`. 그림 `docs/figs/W_D_qual/`.
> **커밋**: `0e43d37`(전체 prior 수트=엔진+config+W_D_prior_full/loss_audit) + 후속 진단 커밋(D2/D3/D4 doc·figs·스크립트).

- **⚡ NEXT STEP (사용자 지시): weight 조정 D 재실험** — D4 사전점검 근거로 가중 재조정 후 `gs_prior_full_{dense,acmp}` 재학습. **D4 권고(판정=사람)**:
  · **법선 타깃 노이즈**(MVS PatchMatch 1024px, 유효 33–90%, 렌더는 매끈) → **w_normal 빼거나 대폭↓**.
  · **depth 신뢰 최하**(CV 1.74=std>mean, 노이즈 MVS에 핀) → **w_depth ↓**(현 0.1 → O(1)정합 ~0.03 / photo정합 ~0.006).
  · **structure magnitude 지배**(cp=18 m², CV 0.11 안정) → CV가중은 magnitude 못고침; **mean/길이스케일 고정정규**(cp÷s²·depth÷s, s=voxel 2.0m) 또는 w_structure 추가↓. 단 곡면(4906969 15k점그룹 4.13m잔차) 과병합 주의.
  · CV 자동가중: 인프라 無, ~20–35줄 신규 가능(4함정 처리, `cv_autoweight` 기본 off) — 단 scale엔 고정정규가 정답(W_D4 §2·3).
  · 재학습=엔진 무변경(가중은 config만). `run_prior_full.sh`(맵 이미 staged) 또는 새 config 복제. ~4h/2arm.

- **결과 귀속(정정됨)**: 조립안됨 8동 → D-gssem **7/8(=LiDAR)** vs v6 2/8. **D2(재추출)로 정정**: 회복은 read-out 단독 아니라 **분류+학습 초가산적 시너지**(분류만=v6+gssem 3–5/8, 학습만=D-smrf 2–3/8, 둘다=7/8). valid-solid 4/8<LiDAR 7/8(위상 잔여).
- **품질/위상(D3)**: 과분할 net 미감소(3.5 vs v6 3.0)·RMS→ref 2.8m로 LiDAR 1.4m 미수렴·PSNR 19.9 무회귀. 무효 4동=**Roofer shell 위상**(302비폐합·306/405방향·303비-다양체; roofer 1.0.0 **위상수리 플래그 無**, 전부 default). 4906969 19면=**곡면 지붕×default epsilon 0.3** 분할(라벨 잡음 아님).
- **엔진(0e43d37)**: train.py(`_ramp_weight_scale` depth/normal warm-up→ramp + `structure_grouping g1|g2` 디스패처 + silent-zero 가드); `tum_mob_tsdf_extract.py`(의미 voxel-히스토그램→P_class); `_mob_prep_las_gssem.py`(SMRF 대체+ground 합성); `tum_mob_eval.py --classifier {gssem,smrf}`. configs `gs_prior_full_{dense,acmp}.yaml`. 맵 `prior_full_stereo.sh`(COLMAP 1024px, `data_geoidfix/stereo` 상대심링크 staged).
- **재사용 자산/재현**: 학습 `run_prior_full.sh`; 표 `d_prior_full_table.py`→`REPORT_D.md`; RMS `tum_mob_ref_rms.py --arms gs_prior_full_{dense,acmp}`; 그림 `d_qual_figs.py`·`d4_normal_check.py`. 비교 baseline 재사용: `eval_v6_protect.json`(v6)·`eval_v6_raw.json`(raw/LiDAR)·`baselines.json`(ref). D2 재추출 npz `tsdf_v6sem_*`(gitignore).

---

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
