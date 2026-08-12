# A2 판독 — E7(ALS 단독)·E8(E2∪ALS 단순 합성) 생성과 H3 예비 판정 v1

- task_id: `P2-JOURNAL1-PHASE-A-v1` (stage A2)
- 상태: **DEVELOPMENT_NON_CONFIRMATORY** — 기술 개발 판독. 공식 G3/G4·`PASS_usable`·확증 추론 없음.
- `official_PASS_usable: null` · `scientific_verdict: null` (인간 리뷰어 판정 대기)
- 설계 근거: `JOURNAL1_EXPERIMENT_DESIGN_ko_v1.md` §3(로스터 E7/E8), §4(지표·GT·층화 D-F), §6 Phase A, §8 H3 분기표
- 산출물: `phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/a2/`
  (`work/E7|E8` 체인 산출, `results/`, `assets_roofer_input/E7|E8` 크롭,
  `evaluation_e7e8/`, `evaluation_merged/`, `evaluation_auto_ox/`)

## 1. 무엇을 실행했나 (봉인 체인, fuse 단계만 어댑터 교체)

| 단계 | 내용 | 통제 |
|---|---|---|
| fuse(교체) | **E7** = C4/S2c prior 계보의 정확한 4타일 raw ALS(SHA-256 일치) + 동결 datum z+45.7 m, 재정합 없음. **E8** = 봉인 C2_MVS classified_scene **기하만**(라벨 폐기) ∪ 동일 ALS 바이트 | 학습 0, LoD2 Z/RoofSurface/의미 라벨 입력 없음 |
| 정합 게이트 | C4 `registration_gate` 재검증(현재측 지지 = C2_MVS 장면): signed-z 중앙값 **0.092 m**, XY p95 **0.41 m**, 통과(신뢰도 0.83) | 재정합/ICP 없음 — 정합 혼입 차단 |
| SMRF→overlay | 봉인 어댑터·파라미터 동일 (`common_classification_adapter_v1`, SMRF cell 1.0/slope 0.15/scalar 1.25/threshold 0.5/window 18) | config drift 가드로 바인딩 |
| Roofer | 동일 이미지·defaults·`--jobs 1`·동일 box, 199동 공유 표준 footprint | 재시도 없음 (E7 32 s, E8 127 s, exit 0) |
| 크롭 | footprint+3 m, class 2/6, viewer-local 원점 [690700, 5335700, 550] | A3 크롭 생산 규칙 동일 |
| 평가 | `geometry_eval.py` **파라미터 불변**(run_v2는 arm 추가만) → A3 행과 병합, v22 auto-OX 동일 코드 경로(S3b 패턴) | 두 GT 모두 계산, 층화는 라벨을 따름 |

포인트 수: ALS AOI 내 4,914,860점(≈21 pts/m²) / E8 합집합 48,763,571점.
Roofer 산출: E7·E8 각 179/199동 (미산출 20동은 MISSING으로 명시 기록).

## 2. Stage-3 기술 유효성 (Roofer 단계 자체)

| 조건 | TECHNICAL_VALID_LOD22 | 주요 실패 |
|---|---|---|
| E1 (봉인) | 99/199 | — |
| E2 (봉인) | 103/199 | val3dity·rf 실패 다수 |
| **E7** | **165/199** | missing 20, val3dity 10, unusable 4 |
| **E8** | **164/199** | missing 20, val3dity 11, lod22 누락 4 |

rf_rmse 중앙값은 전 조건 ≈1.44–1.56 m로 유사. **희소(≈19 pts/m²)라도 균질·crisp한
ALS 입력이 Roofer 병목(평면 파편화·무효 솔리드)을 그대로 통과** — A3의 crispness
병목 진단과 정합.

## 3. 기하 판독 (199동, 중앙값; **주 GT=기존 LoD2, e1 병기** — 보고 규칙)

### 3.1 전체 (gt=lod2 | gt=e1)

| arm | f1@0.5 | comp@0.5 | acc(m) | z-spread(m) | normal(°) |
|---|---|---|---|---|---|
| E2 | 0.507 \| 0.909 | 0.629 \| 0.937 | 0.589 \| 0.096 | 0.191 \| 0.187 | 13.8 \| 16.9 |
| E3 | 0.471 \| 0.877 | 0.634 \| 0.906 | 0.670 \| 0.159 | 0.441 \| 0.435 | 22.1 \| 26.3 |
| E4_V2 | 0.470 \| 0.878 | 0.648 \| 0.911 | 0.693 \| 0.168 | 0.485 \| 0.458 | 21.0 \| 25.7 |
| E5_V2 | 0.482 \| 0.872 | 0.662 \| 0.905 | 0.689 \| 0.165 | 0.455 \| 0.452 | 21.2 \| 25.9 |
| **E7** | **0.705** \| 0.898 | 0.952 \| 0.938 | 0.207 \| 0.089 | (7.83)* \| (8.28)* | 2.3 \| 9.4 |
| **E8** | **0.682** \| **0.919** | **0.965** \| **0.982** | 0.358 \| 0.092 | 0.255 \| 0.201 | 8.2 \| 16.9 |

\* E7 z-spread는 해석 불가 아티팩트: ALS 밀도(≈1.2점/셀)로는 셀 최소 5점 요건을
수직 벽면 스택 셀만 충족 → 값이 건물 높이를 반영. 이중 표면 판별기로 쓰지 말 것.

### 3.2 페어드 대비 (f1@0.5, 건물별 paired Wilcoxon)

| 대비 | gt=lod2 | gt=e1 | 방향 일치 |
|---|---|---|---|
| **E8 − E4_V2** | **+0.093** (124W/23L, p≈9e-20) | **+0.040** (107W/17L, p≈2e-14) | **일치 — E8 우위** |
| **E8 − E5_V2** | +0.092 (125W/20L) | +0.038 (109W/15L) | 일치 — E8 우위 |
| E8 − E2 | +0.040 (132W/14L) | +0.007 (101W/23L) | 일치 — E8 우위 (completeness 무패: 134W/0L, 124W/0L) |
| E8 − E7 | −0.012 (44W/116L) | **+0.037** (96W/30L) | **불일치 — 계보 순환 시그니처** (구 GT는 E7, 현재 GT는 E8) |
| E7 − E2 | +0.156 (128W/18L) | **−0.011** (51W/73L) | 불일치 — ALS 단독은 현재 GT에서 열세 |

### 3.3 층화 (자동 후보 라벨, Phase-B 인간 리뷰 전 — 예비)

D-F 규칙: 비변화(C, n=59) → lod2 주 / 변화 후보(A+B, n=68) → e1 주. NA 72동 판정 유보.

| 층 | 주 GT | E2 | E4_V2 | E5_V2 | E7 | E8 |
|---|---|---|---|---|---|---|
| C 일치층 f1@0.5 | lod2 | 0.713 | 0.670 | 0.685 | **0.771** | 0.746 |
| (보조 e1) | e1 | 0.953 | 0.916 | 0.918 | 0.940 | **0.960** |
| A+B 변화 후보층 f1@0.5 | **e1** | 0.773 | 0.712 | 0.696 | **0.655 (최하)** | **0.782 (최상)** |
| (보조 lod2 — 구형 재현 신호) | lod2 | 0.241 | 0.271 | 0.299 | **0.602** | 0.553 |

- **E7 음성 대조 기능 확인**: 변화 후보층 현재 GT에서 E7 최하(0.655), 반대로 구
  LoD2 GT에서는 최고(0.602) — 구형 기하 재현의 전형적 시그니처.
- **E8은 변화 후보층 현재 GT에서도 최상(0.782)**: 합집합의 E2 성분이 현재성을
  방어. 단 acc(e1) 0.185 vs E2 0.129 — 구형 표면 잔류가 정확도를 끌어내리는
  흔적은 있음.

## 4. auto-OX 전이 (v22 기준, O50·noG2, ROOFER_REFERENCE_AUTO_OX_DEVELOPMENT — NOT_OFFICIAL)

| 조건 | O50 O | 현재-UAS 앵커층 O | LoD2 폴백층 O |
|---|---|---|---|
| E1 29 · E2 31 · E3 23 · E4_V2 25 · E5_V2 22 | — | E2 31 · E4_V2 24 · E5_V2 22 | E2 0 |
| **E7** | **73** | 34 | 39 |
| **E8** | **74** | 36 | 38 |

- E2→E8 rescue 44 / regress 1 (net +43); E2→E7 rescue 46 / regress 4.
- **순환 경고(사전 등록 §7 위험의 실현)**: rescue의 층별 분해 = NA 34 / A+B 8 / C 2.
  E1 부재 폴백층(72동)에서는 G3·G4가 모두 **기존 LoD2** 기준 → ALS 계보(동일
  2022 원천)와의 자기일치라 현재 기하 증거가 아님. 현재-UAS 앵커층으로 좁히면
  우위는 **E8 36 vs E2 31 (+5)** 로 완만해짐. 그래도 GS 융합(E4_V2 24)보다는 위.
- E7↔E8: O 67 공유, E7만 O 6, E8만 O 7 — auto-OX 레벨에서 합집합의 증분은 미미.

## 5. H3 예비 판정 (조기 kill-risk 확인 — Phase A의 목적)

**설계 §8의 H3-지지 시나리오("E8은 completeness만 좋고 z-spread·노멀 악화 →
종합 F1·LoD2에서 E4/E5 우위")는 실측에서 성립하지 않았다.**

1. E8의 z-spread 악화는 미미(+0.010~0.012 m; ALS 밀도가 MVS 대비 낮아 셀 지배
   불가)하고, 종합 F1은 두 GT 모두에서 E4_V2/E5_V2를 크게 이김(§3.2, p<1e-13).
2. Stage-3 통과율(165/164 vs 103)과 auto-OX 현재-앵커층(36 vs 24)에서도 같은 방향.
3. 변화 후보층에서도 E8이 현재 GT 최상 — GS 융합이 이겨야 할 무대에서도 열세.

→ **H3 예비 기각 방향**: 현 구현의 GS 재합성 융합(E4/E5)은 단순 합성(E8)에
명백히 뒤진다. 설계 분기표(§8)에 따르면 이 결과가 Phase-B 확정 라벨에서도
유지되면 **"합성 기반 conflict-aware 융합으로 방법 피벗"** 이 지정 경로다.

단서(판정을 예비에 묶는 이유):
- 층화 라벨이 자동 후보(Phase-B 인간 리뷰 전).
- 장면의 실제 변화가 희소해 보임(ALS↔현재 z 중앙 잔차 0.092 m) → M1/M2 충돌
  중재의 이론적 시장 자체가 작은 표본. GS 융합의 가치 주장 무대가 부재했을
  가능성과, 그 무대 자체가 좁다는 발견을 구분해야 함.
- E7 단독이 현재 GT 전체에서 E2에 열세(−0.011)이고 변화 후보층에서 최하 —
  "기존 자산 단독 재사용은 불충분, 현재 증거와의 결합이 필수"라는 최소 주장은
  방어됨. 융합의 가치를 기하 증분이 아니라 **현재성 보증(conflict 맵 인증)과
  무결 합집합**으로 재프레이밍하는 피벗과 정합.
- 불변식 12: 변화 건물에서 E7/E8의 구형 재현은 현재 기하로 주장 불가 — 시간성
  기록 필수. auto-OX NA 폴백층 수치는 현재성 근거로 사용 금지.

## 6. 재현

```bash
bash scripts/p2/journal1_phase_a_v1/a2_run_host.sh <ARTIFACT_ROOT>
# 이후 (artifacts ro + a2 rw 중첩 마운트, jointbuildgs:dev):
python -B scripts/p2/journal1_phase_a_v1/geometry_eval.py \
  --config configs/p2/journal1_phase_a_v1/run_v2_e7e8.json --arms E7,E8
python -B -m scripts.p2.journal1_phase_a_v1.a2_merge_eval
python -B -m scripts.p2.journal1_phase_a_v1.a2_auto_ox
```

CRS EPSG:25832. 도커 이미지 identity는 `a2_run_host.sh`가 검증. 실패·미산출은
전부 receipt에 명시 기록(위 §2). `scientific_verdict: null`.
