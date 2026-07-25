# Fusion W1 06:30 부분 종료 기록 — 2026-07-26

문서 역할: 수치·산출물·미완 단계 기록. 해석 및 사람 판정은 포함하지 않는다.

- 생성 시각(UTC): `2026-07-25T22:57:59.421101+00:00`
- cutoff(KST): `2026-07-26T06:30:00+09:00`
- run: `20260724_fusion_w1`

## R1 검증 표

| 항목 | 기록값 |
|---|---|
| R1 status | `PASSED` |
| 카메라 / 변환 적용 | `937` / `1` |
| source images.bin SHA256 | `dfc779496ee3b13f8df5dd28fae465746ce0adf4aca7922d38cbed275a2fd951` |
| corrected images.bin SHA256 | `28b38383a0b6d82656108e8f0e5e79711dcda93948ab2e89c1cd8f47215962a5` |
| roundtrip R max | `1.6653345369377348e-15` |
| roundtrip t max (m) | `1.4210854715202004e-14` |
| projection max | `5.115907697472721e-13` |
| camera-center max (m) | `3.694822225952521e-13` |
| 대응 가능 / 기준 충족 | `132/178` / `132/132` |
| 핵심군 대응 가능 / 기준 충족 | `24/28` / `24/24` |
| 동별 중앙의 중앙 (m) | `0.07236711717994171` |
| T5 총 잔차 (m) | `0.004186004000697177` |

## R2 관문 A v2 및 오버레이

| 항목 | 기록값 |
|---|---|
| Gate A v2 | `PASS` |
| n* | `40` |
| 대응 가능 / 기준 충족 | `132/178` / `132/132` |
| 핵심군 | `24/24` |
| 대응 불가 표면/높이/윤곽 | `2/11/33` |
| 오버레이 | `28` PNG · [index](resume_v2/r2_overlay_index.csv) · [directory](resume_v2/w1_align_overlays_v2/) |

## 눈금 1–4

| 눈금 | 항목 | 상태 | 값 | 근거 수량 |
|---:|---|---|---|---|
| 1 | `assembly_establishment` | `NOT_MEASURED` | — | `2-run n=0` |
| 2 | `seed_retention` | `NOT_MEASURED` | — | `2-run n=0` |
| 3 | `textured_boundary_improvement` | `NOT_MEASURED` | — | `2-run n=0` |
| 4 | `supervision_removal_control` | `NOT_MEASURED` | — | `2-run n=0` |

## 대상·전처리·P0′ 수량

| 단계 | 기록값 |
|---|---|
| target queue | `178`동; resolved core lower bound `28`; provisional extension `150`; core_priority_complete=`false` |
| target 층 | surface `114`, height `23`, outline `41` |
| preprocess | `1`동; core `1/28`; status `PARTIAL` |
| preprocess 첫 동 | `DEBY_LOD2_42364609`; views `30`; points `7993`; class2/class6 `7644/349` |
| P0′ | `1/178`동; assembly LoD2 `1`; val3dity valid `1`; state `PARTIAL` |
| P0′ 첫 동 지표 | plane F1 `1.000000000`; RMS `0.089892857 m`; completeness `0.999715443`; face ratio `1.000000000` |
| P0′ vs P0 Ref-L | assembly match `true`; RMS delta `-0.000623414 m`; completeness delta `0.000012621`; face-ratio delta `0.000000000` |
| post-learning fusion learning/readout/Section5 Roofer/scoring | `0/0/0/0` |
| 30k 학습 1런 처리율 | `NOT_MEASURED`; 30k learning started/completed=`0/0` |
| 층별 placeholder | [w1_summary.csv](w1_summary.csv); `12`행, `NOT_MEASURED` `12`행 |

## 정성 패널

- P0′ pre-learning: [DEBY_LOD2_42364609__p0prime.png](w1_panels/DEBY_LOD2_42364609__p0prime.png) · [receipt](w1_panels/DEBY_LOD2_42364609__p0prime.receipt.json) SHA256 `d1ca6d459d3ed2ed2b164fb540c269a984942f3838e796ce3a1fcfcdbaea6b1a`
- fusion arm/run panel: `0`

## 고정 산출물

| 산출물 | 상태 | 행/파일 |
|---|---|---:|
| `w1_align_residuals.csv` | `PRESENT_EXACT_COPY` | `178` |
| `w1_seed_stats.csv` | `PRESENT` | `1` |
| `w1_seed_p0prime_scores.csv` | `PRESENT_MEASURED` | `1` |
| `w1_loss_shares.csv` | `HEADER_ONLY` | `0` |
| `w1_scores_building.csv` | `HEADER_ONLY` | `0` |
| `w1_summary.csv` | `PLACEHOLDER_NOT_MEASURED` | `12` |
| `w1_panels/` | `P0PRIME_ONLY` | `1` |
| `w1_manifest.json` | `ATOMIC_REPLACE_AFTER_REPORT` | — |

## issues

- [issues.md](issues.md) SHA256 `b69cd1a4956dedd91326763bd6cc1ec5716d91e2d6b82b90745651576d8e301e`; headings `18`.
- `FUS-W1-PF-001 — canonical source document missing`
- `FUS-W1-TGT-001 — root-owned provisional target artifacts`
- `FUS-W1-ALIGN-DEV-001 — direct-residual proxy rejected before measurement`
- `FUS-W1-ALIGN-DEV-002 — concurrent stale draft writer isolated`
- `FUS-W1-ALIGN-DEV-003 — primary direction and metre conversion corrected`
- `FUS-W1-ALIGN-RUN-001 — logical image-path aggregate restored`
- `FUS-W1-ALIGN-RUN-002 — unregistered azimuth-bin hard gate removed`
- `FUS-W1-ALIGN-RUN-003 — predicted uncertainty retained as ranking, not exclusion`
- `FUS-W1-ALIGN-RUN-004 — core Gate A stopped after the third consecutive building error`
- `FUS-W1-ALIGN-DEV-004 — terminal building checkpoint now precedes stage-stop raise`
- `FUS-W1-COREG-LOCK-001 — ALS-fixed camera co-registration preregistered`
- `FUS-W1-COREG-RUN-001 — lock1 stopped before trigger residual evaluation`
- `FUS-W1-COREG2-RUN-001 — no transform satisfied the frozen trigger contract`
- `FUS-W1-COREGDIAG-001 — Gate A 사전등록 초과 구현 확인`
- `FUS-W1-COREGDIAG-002 — 지지율 요구의 범주 오류 확정`
- `FUS-W1-COREG-ADOPT-001 — 전역 SE(3) 채택 재판정 기록`
- `FUS-W1-PREPROCESS-001 — 투영 TIN 화면 토폴로지 구현 오류`
- `FUS-W1-CUTOFF-001 — 06:30 컷 시점 신규 학습 미착수`

## 미완 단계

- preprocess: completed `1`, remaining `177`.
- P0′: completed `1`, remaining `177`.
- P0′ current namespace: `PARTIAL` final manifest published (`manifest_written_last=true`); remaining 177 require a new approved namespace or reopen contract under the locked driver guard.
- smoke arm A r1 30k training: `NOT_STARTED`.
- core arm A r1/r2 training: `NOT_STARTED`.
- arm B 감독 제거 training: `NOT_STARTED`.
- extension training: `NOT_STARTED`.
- fusion pointcloudification/classification/Roofer/scoring: `NOT_STARTED`.
- fusion arm/run panels: `NOT_PRODUCED`.
- 눈금 1–4: `NOT_MEASURED`.
