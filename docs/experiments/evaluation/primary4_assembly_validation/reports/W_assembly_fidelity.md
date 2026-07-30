# W_assembly_fidelity — 조립 표적 3동 충실도 (기존 산출 재사용, 관찰만·판정 금지)

> **재사용·재구성/학습 없음, 모델 비교만. 관찰만, 판정 = 김휘영.** 브랜치 `feat/p2-fidelity`. EPSG:25832. Docker(p0-tools).
> 질문: raw MVS(DIM)가 **조립 못 한** 3동(**42364659·42364663·4907510**)을 GS-JSO(D4)가 **조립함**. "조립됨 ≠ 충실"이므로 이 GS 모델이 ALS(LiDAR)만큼 충실한가(높이·형상·면수·닫힘) 아니면 그럴듯한 추정-채움인가 — 방법 표적이 작동하나.
> 대조: **4906972**(박공)·**4908023**(평) 충실 기준선(DIM도 조립) + **4906969**(맥락, 단차 평).
> 출처: `assembly_fidelity.py`. 그림 `docs/figs/W_assembly/`. CSV(gitignore) `analysis_pack_d6/assembly_fidelity.csv`. 재사용: GS=`gs_d4_dense`·ALS=`raw_lidar`·DIM=`raw_dense` 점군 + Roofer `*.city.jsonl` + `ref_rms_{raw,d4_gssem}.csv` + `gen_status.csv` + GML.
> ⚠ **datum**: 점군 = 타원체고(geoid_med = +48.165 m = ALS_envz−ref_ortho의 **footprint-내 class6 지붕점 ≥600**(엔벨로프 이전) 4동 중앙값), 참조 GML = 정표고. **높이 1차 지표 = GS vs ALS(둘 다 타원체, 직접 차)**; ortho = ellip−48.165 병기. mob class6=건물 외피→**지붕 top-envelope**(1 m 셀 최상단 1.5 m)만 측정.

## §0 ⚠ 검증으로 정정된 헤드라인 (방법론 함정 → 바로잡음)

**1차 판독(단일 엔벨로프-중앙값 높이)은 틀렸고, 적대 3-렌즈 재검(`datum-integrity`·`numerical-repro`·`methodology`)이 이를 뒤집었다. 본 보고는 정정본이다.**

1. **단일 중앙값 높이는 단차(다층) footprint에서 인공 산물.** 표적 2동(42364659·4907510)은 footprint 안에 **저·고 두 실구조**가 있는데 참조 LoD2가 이를 한 면으로 뭉갠다. `roof_envelope` **중앙값**은 점이 더 많은 클러스터로 떨어지므로, GS는 한 클러스터·ALS는 다른 클러스터에 앉아 `|GS−ALS 중앙값|`이 **±4~7 m로 부풀려진다(점밀도 산물, 물리적 과/저-건축 아님)**. → **ridge-top(p95) 높이**를 like-for-like 1차 지표로 병기(중앙값은 단봉 동에만 신뢰). 두 동 모두 `bimodal_med_artifact=True`(|중앙값차−ridge차|>2 m).
2. **full-class6 RMS→ref는 지붕 충실 지표가 아니다(벽/facade 지배).** class6 = 외피 전체라 GS의 조밀한 벽점(최대 82만점·span 27 m)이 RMS를 부풀린다. → **facade 제거(roof-envelope) 후 동일 metric**(1-DOF dz 정렬 point→최근접 참조평면 RMS, `tum_mob_ref_rms`와 동형)을 **전 행에 대칭 적용**(특정 동만 변호하지 않음).
3. 적대 재검은 geoid 48.165·전 높이·면수·닫힘·facade-제거 RMS를 **독립 재유도로 일치 확인**(아래 값들이 재검 수치). must-fix 2건(중앙값 인공산물·RMS facade)·should-fix 4건 전부 본 정정본에 반영.

## §1 표 (GS-JSO D4 vs ALS vs 참조)

### §1a 조립·위상 (방법 표적의 1차 주장 = "DIM이 못 한 닫힌 모델을 만든다")
| 동 | set | DIM 면수 | DIM 조립 | **GS 닫힘(동별·이웃제거)** | ALS 닫힘 | GS clip-val3dity | GS 완전성(coverage) | ALS 완전성 |
|---|---|---:|---|---|---|---|---:|---:|
| 42364659 | R | 0 | **실패** | **closed**(35면·0 비다양체) | no-solid† | True | 0.97 | 0.58‡ |
| 42364663 | R | 0 | **실패** | **closed**(6면) | closed | False | 1.00 | 1.00 |
| 4907510 | R | 0 | **실패** | **closed**(37면) | closed | False | 0.95 | 1.00 |
| 4906972 | Q | 3 | 조립 | closed(32면) | closed | False | 1.00 | 1.00 |
| 4908023 | Q | 1 | 조립 | closed(12면) | closed | True | 1.00 | 1.00 |
| 4906969 | Q | 17 | 조립 | closed(122면) | closed | False | 1.00 | 1.00 |

† 42364659는 ALS도 Roofer solid 실패(그 동만). ‡ 완전성 = footprint 1 m 셀 중 지붕점 점유 비율 = **coverage(비-구멍)일 뿐 충실 아님** — 조밀 점군이면 구조상 ~1(과/저-건축 동도 0.95~0.97). 희박 점군만 분별(ALS 0.58·DIM). **닫힘은 target-only(이웃제거) outer-ring 2-다양체 검사**(구멍 없는 건물 shell에 타당); clip-val3dity는 **클립 단위(이웃 포함)**라 별개 지표.

### §1b 높이 (ellipsoidal 직접차; ortho 병기 = ellip−48.165)
| 동 | roofType | 참조z(ortho) | GS med(ortho) | ALS med(ortho) | **중앙값 GS−ALS** | GS ridge(ortho) | ALS ridge(ortho) | **ridge GS−ALS** | 단차-인공 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| **42364659** | 1000 평 | 516.9 | 524.2 | 517.0 | +7.17 | 526.2 | 527.9 | **−1.70** | **YES** |
| **42364663** | 1000 평 | 530.5 | 530.6 | 530.3 | **+0.25** | 533.2 | 534.5 | −1.36 | no |
| **4907510** | 1000 평 | 518.0 | 514.2 | 518.2 | −3.96 | 522.1 | 521.1 | **+1.01** | **YES** |
| 4906972 | 3100 박공 | 531.8 | 531.0 | 532.9 | −1.85 | 532.7 | 534.9 | −2.19 | no |
| 4908023 | 1000 평 | 518.9 | 517.1 | 518.8 | −1.70 | 517.5 | 519.0 | −1.53 | no |
| 4906969 | 1000 평 | 526.9 | 524.9 | 526.5 | −1.58 | 528.1 | 530.2 | −2.13 | no |

→ **like-for-like(ridge) GS−ALS 범위 = −2.19 ~ +1.01 m**(전 6동 ~±2 m). 중앙값의 ±4~7 m(42364659·4907510)는 §0-1 단차 인공산물. 단봉 대조 3동은 GS가 일관되게 **~1.5~2.2 m 낮음**; 42364663(단봉 ridge)은 중앙값 GS−ALS **+0.25 m**(정상-일치, ridge에선 −1.36 = 최정점만 덜 닿음).

### §1c 지붕면 충실 (facade-제거 roof-env RMS→ref; full-class6 RMS 병기·맥락만)
| 동 | **roof-env RMS GS** | roof-env RMS ALS | GS/ALS 배율 | (참고)full RMS GS/ALS | 지붕면수 GS/ALS/ref | GS 국소경사° | ALS 국소경사° |
|---|---:|---:|---:|---|---|---:|---:|
| 42364659 | 5.26 | 4.85 | 1.08 | 4.80/4.84 | 6/0/2 | 60.7§ | 21.1 |
| 42364663 | **1.36** | 1.27 | **1.07 ≈** | 4.94/2.26 | 1/1/1 | 82.8§ | 78.0§ |
| 4907510 | 3.66 | 1.40 | **2.61** | 3.41/1.33 | 6/4/1 | 20.9 | 28.4 |
| 4906972 | **0.26** | 0.27 | **0.95 ≈** | 2.47/2.41 | 3/3/3 | 35.5 | 32.6 |
| 4908023 | 0.62 | 0.26 | **2.41** | 0.88/0.91 | 2/1/1 | 30.4 | 16.9 |
| 4906969 | 0.76 | 0.46 | **1.67** | 1.13/1.17 | 14/5/3 | 41.9 | 52.3 |

§ 국소경사 60.7°(42364659 GS)·~80°(42364663 GS·ALS)는 `measure_shape`가 "벽 오분류 의심"으로 자동 표시 — **단차의 수직 step + class6 facade 오염**이지 깨끗한 지붕 pitch 아님(높이는 §1b ridge로 판단). 4907510 GS roof-env RMS 3.66 ≥ full 3.41 = **facade 아닌 진짜 지붕 오차**(facade caveat를 여기선 검사 후 기각 = 대칭 적용 확인).

## §2 관찰 (판정 금지)

1. **조립·위상 = 방법 표적의 실증.** raw MVS(DIM)가 0면으로 조립 못 한 3동을 GS-JSO가 **target-only(이웃제거) 닫힌 2-다양체 solid 3/3**으로 만든다(35·6·37면, 비다양체 간선 0). 이건 DIM이 못 준 것. **단** ⓐ **clip-level val3dity는 1/3**(42364659만 True; 42364663·4907510은 클립 단위 비유효) → 닫힘=동별이지 클립 전체 기하-유효 아님; ⓑ **완전성(0.95~1.0)은 coverage**(조밀 점군이면 구조상 ~1)지 충실 아님.
2. **높이: like-for-like(ridge) ~±2 m로 ALS 추종 — 중앙값의 ±4~7 m는 인공산물.** 단차 표적 2동(42364659·4907510)의 큰 중앙값차는 다층 footprint에서 중앙값이 어느 클러스터에 앉느냐의 산물(§0-1); ridge GS−ALS는 −1.70·+1.01 m로 **ALS 지붕 top과 ~1~2 m 내 일치**(과/저-건축 아님). 42364663은 중앙값 +0.25 m로 일치. 단봉 대조 3동은 GS가 ~1.5~2.2 m 낮음.
3. **낮음-편향은 "대조(단봉)에 한정"이며 전반 일반화 못 함.** 대조 3동 GS−ALS = −1.58·−1.70·−1.85 m(평균 −1.71, std 0.11)로 일관되나, 표적 42364663(+0.25, 단봉·ALS 676점 신뢰)이 이를 깨고, 단차 표적 2동의 큰 값은 편향 아닌 인공산물 → **"체계적 fleet-wide 낮음-편향" 단정 불가**. 42364663의 +0.25 m 일치는 이 ~−1.7 m 편향의 **예외**(편향-상쇄/우연 가능성 포함, 김휘영 판단).
4. **지붕면 충실 = 진짜 격차.** facade 제거 후 GS 지붕은 ALS와 **2동만 동급**(4906972 0.26≈0.27·42364663 1.36≈1.27), **3동은 1.7~2.6× 더 거칢**(4907510 2.6×·4908023 2.4×·4906969 1.7×), 1동은 둘 다 coarse-ref에 부적합(42364659). 즉 **GS는 조립·높이는 근사하나 지붕 표면이 ALS보다 일반적으로 노이지**. (full-class6 RMS의 "GS≈ALS"는 양 arm 공통 facade 지배의 우연 — 충실 근거 아님.)
5. **GS 과분할: 참조 대비 4/6**(6 vs 2·6 vs 1·14 vs 3·2 vs 1); 면수 일치는 42364663(1/1/1)·4906972(3/3/3) 2동.
6. **단서 비순환(metric 한정).** 본 metric 경로에서 참조 GML은 **ortho 변환·면수 baseline·RMS baseline에만** 쓰이고 GS 기하로 들어가지 않음(GS=사전 분류 LAS). ⚠ 단 **학습 시점**엔 `sem_detach_geometry=false`(gs_d4)라 L_sem(LoD2-레이캐스트 클래스투영)이 GS 기하를 부분 견인(D6-provenance) — "비순환"은 **이 metric에 한정**, end-to-end 파이프라인엔 부분 참조-의존 상존.

## §3 그림 (docs/figs/W_assembly/)
[GS-JSO(D4) | ALS | 참조 LoD2] × {top, oblique}, 높이색. 캡션 = 중앙값/ridge GS−ALS·면수·닫힘·roof-env RMS.
- [42364659](figs/W_assembly/42364659.png) — **단차 인공산물 시험**: GS·ALS 모두 저·고 두 레벨, GS oblique의 z-경사 = step(과-건축 아님). ALS 희박(263점)·solid 실패.
- [42364663](figs/W_assembly/42364663.png) — **충실 표적**: GS가 ALS ridge(530.5 ortho)에 정확히 앉음; 면 1/1/1, facade 제거 후 RMS 1.36≈1.27.
- [4907510](figs/W_assembly/4907510.png) — **단차+노이지 지붕**: GS ridge는 ALS와 ~1 m 내(중앙값 낮음=하부 클러스터); 단 roof-env RMS 2.6×·면 6 vs 1.
- [4906972](figs/W_assembly/4906972.png)(박공 충실 기준선: 면 3/3/3·RMS 0.26≈0.27·박공형상 일치, ~1.85 m 낮음) · [4908023](figs/W_assembly/4908023.png) · [4906969](figs/W_assembly/4906969.png).

## §4 한 줄 관찰 (판정 금지)

**"조립됨 ≈ 위상·높이는 근사, 표면·면수는 ALS 미달".** GS-JSO는 raw MVS가 0면으로 실패한 3동을 **동별 닫힌 2-다양체로 조립(3/3, 위상 승리)**하고, **like-for-like(ridge) 높이를 ALS와 ~±2 m 내로 맞춘다**(단일-중앙값의 ±4~7 m 격차는 단차 footprint의 인공산물로 정정됨 — 과/저-건축 아님). **그러나** ⓐ clip-level val3dity 1/3, ⓑ facade 제거 지붕 RMS는 GS가 ALS와 동급인 동이 **2/6뿐**(나머지 1.7~2.6× 더 거칢), ⓒ 참조 대비 과분할 4/6. 즉 **방법 표적은 "raw가 못 한 닫힌 모델 + 근사 높이"까지 받쳐지나, "ALS급 지붕 표면·면수 충실"로는 받쳐지지 않는다**. (충실 판정 = 김휘영.)

## §5 판정표 (동별, §5 규칙 대입 → 충실/부분/속빔; 최종 k/3 = 김휘영)

> 규칙(대입): **속빔**=닫힘 실패/빈 채움 · **충실**=닫힘+높이(ALS 상대)+지붕면 RMS·면수 ALS급 · **부분**=조립됨이나 높이/표면/면수 중 실질 미달. 절대 높이오차 영상-norm(~0.5 m) = 문헌 맥락만(대조 충실 기준선도 ~1.7 m 낮아 0.5 m는 GS 미달성, 실 기준=ALS 상대).

| 표적 | 닫힘(동별) | 높이(ridge, ALS상대) | 지붕면 RMS(facade제거) | 면수 | 0.5 m norm? | **기계대입(잠정, 판정=김휘영)** |
|---|---|---|---|---|---|---|
| **42364663** | closed | +0.25 m(med)/−1.36(ridge) ≈ALS | 1.36 ≈ ALS 1.27 | 1=1=ref | NO(±0.25~1.4) | **충실 후보**(높이·표면·면수 모두 ALS급; 유일) |
| **4907510** | closed | ridge +1.01 m ≈ALS | 3.66 = ALS 1.40 ×2.6 | 6 vs ref 1 | NO | **부분**(높이 근사·표면 2.6× 노이지·과분할) |
| **42364659** | closed(ALS는 no-solid) | ridge −1.70 m(고레벨) | 5.26 ≈ ALS 4.85(둘 다 coarse-ref) | 6 vs ref 2 | NO | **부분**(높이 근사·표면 판정불가(ref/ALS 희박)·과분할) |

- **조립 표적 충실도(잠정 집계, 판정=김휘영)**: 동별 닫힘 **3/3** · ridge 높이 ALS와 ~±2 m **3/3** · 영상-norm 0.5 m **0/3** · facade-제거 지붕 RMS ALS급 **1/3**(42364663) · 면수 참조일치 **1/3**(42364663). → **"높이·위상 근사 3/3, 표면·면수 충실 1/3"**. 최종 "k/3 충실" = 김휘영.
- 대조 보정: 충실 기준선조차 GS −1.7 m·표면 일부 노이지(4908023 2.4×) → GS의 도달 가능 충실 상한 = "박공/평 형상·면수 일치 + ~1.7 m 낮음 + 표면 ≤2× 노이즈"(4906972가 최선).

## §6 재현 / 출처 / 검증
- `docker run … jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/p2_gsjso/assembly_fidelity.py` (read-only 재사용). 점군 GS/ALS/DIM=`mob_eval/{gs_d4_dense,raw_lidar,raw_dense}`. 닫힘=Roofer `*.city.jsonl` target Solid outer-ring 2-다양체. roof-env RMS=`tum_mob_ref_rms`와 동형(roof-envelope 한정). full RMS/면수/valid/DIM점=`ref_rms_*.csv`·`gen_status.csv`(D6). 참조 z·면=GML.
- **검증**: 적대 워크플로 3렌즈(`datum-integrity`·`numerical-repro`·`methodology`)가 raw LAS/jsonl/GML에서 독립 재유도 — geoid 48.165·전 높이(중앙값/ortho)·facade-제거 RMS(0.26/0.27·1.36/1.27 등)·닫힘·면수 전부 일치, neighbour-leak 무(42364659 GS xy ⊂ 9.35×13.33 m footprint). must-fix 2(중앙값-인공산물·RMS-facade)·should-fix 4 전부 반영(본 정정본). 잔여 nit = closedness outer-ring-only(구멍無 shell 타당)·표기.
- EPSG:25832 · Docker · 재구성/학습/data 무변경 · 관찰만. G1_package 사본 포함.
