# 저널1 실험 설계 개정 기록 v2 (PLANNING RECORD)

- 상태: **개정안 — 실행 권한 없음, 사용자/교수 확정 대기**
- 기준 문서: `JOURNAL1_EXPERIMENT_DESIGN_ko_v1.md` (커밋 bae9eb73/11a5de71) — 본 문서는
  v1 전면 재작성이 아니라 **A2 실측(2026-08-12) 이후의 변경점 대비표**다.
- 근거 데이터: A2 판독(`A2_E7_E8_READOUT_ko_v1.md`), 확정 모집단
  (`labels/selection_confirm_v1.json`, 93동), Phase D 설계
  (`PHASE_D_DELTA_SHIFT_DESIGN_ko_v1.md`). 비확증 · `scientific_verdict: null`.

## 1. 유지되는 것 (v1 불변)

| 항목 | 내용 |
|---|---|
| 목적 앵커 | "자동 LoD2 범위 확대" (헌장) · 직접 산출물(point cloud) 평가 주 무대 |
| 로스터 | E1(참조)·E2(제품 기준)·E3(ablation)·E4/E5(GS 융합)·E7(음성 대조)·E8(핵심 반사실) |
| 평가 체계 | 봉인 Stage-3 체인 · 9지표 × 2 GT(lod2 주·e1 병기) · per-building paired Wilcoxon |
| 통제 | E1 무접촉(평가 전용) · 공유 표준 footprint(DEC-P1-019) · 학습 0 arm의 fuse 어댑터 원칙 |
| Phase D | δ-shift 파일럿(코리도 55뷰) — v1에 있던 항목, 우선순위만 상승 |
| 지위 | 전 산출물 비확증·NOT_OFFICIAL·인간 리뷰어 판정 대기 |

## 2. 변경·신설 (A2 실측이 강제한 것)

### 2.1 주장 구조: "융합 증분" 단일 주장 → Claim A/B 2단

- v1: E2→E4/E5, E8→E4/E5 증분이 주 주장. **A2 실측으로 H3 예비 기각**
  (E8이 E4/E5를 두 GT·Stage-3·auto-OX 전 레벨에서 우위) → 단일 주장 유지 불가.
- v2 구조:
  - **Claim A (prior 결합의 가치, 방법 불문)**: 불변·정합 양호 영역에서 image-only의
    관측 공백을 충전. 증명 = E8 vs E2. **진술 형태 = 1차 평가변수(completeness/
    coverage, 확정 93에서 무패) + 가드레일 비열화(acc·rmsd 불변, precision/outlier/
    normal/z-spread 사전 정의 한계 내 미세 비용)**. 전 지표 개선 주장 아님.
    lod2-acc 개선분은 계보 순환 성분 — 주 근거 금지.
  - **Claim B (결합 방식의 가치 = GS)**: union은 "현재 관측과의 일치 제약 부재"
    라는 한 뿌리에서 세 실패 모드를 갖는다 — ① 시간(변화 미중재·stale),
    ② 공간(정합 잔차 미흡수·이중 표면), ③ 외관(채움 영역 무근거 텍스처·사후
    투영의 기하 의존성). GS 재합성은 **미분 가능 렌더링이라는 단일 최적화
    파이프(렌더→현재 관측과 비교→역전파)** 안에서 세 잔차 채널로 셋을 동시에
    다룬다: **위치는 깊이 잔차**(현재 MVS depth 감독 + prior depth 손실
    + depth-잔차 기반 current-consistency 게이트 = 변화·정합 중재의 주 신호),
    **방향은 노멀 손실**(sign-invariant prior normal + normal consistency),
    **외관은 광도(RGB) 손실**. photometric 단독으로는 위치·방향이 정해지지
    않으며(shape–radiance 모호성), 세 채널이 같은 파이프를 공유한다는 것이
    "한 기제" 주장의 정확한 형태다. — 입증 대상 가설(현 구현은 코어에서
    union에 뒤짐을 명기).

### 2.2 평가 모집단: 199 전수 → **확정 93** (평가 가능성 마스크)

- E1 커버리지 규칙(내부 전부 + 경계 80%) + 수동 오버라이드 5건, 동결:
  `labels/selection_confirm_v1.json` (sha f7124b72…). 전 조건 동일 적용,
  성과 분류·파라미터 입력 아님.
- 효과: NA 72동 전원 및 서베이-가장자리 아티팩트 성격의 A-티어 26동 제거.
  Phase C 본판독·모든 후속 집계는 93 모집단으로 재정의.
- 함의(정직 보고): 코어 93에서 prior 이득은 얇고(comp +2~3%p 무패, Roofer·OX 동률
  ±수 동, rescue 5 vs 신규 실패 7), 큰 이득은 검증-불가 확장 구역에 있었음 →
  **"prior의 시장 = 현재 조사의 여집합"** 명제와 verification 필요성(§2.5).

### 2.3 층화·라벨: Phase B 인간 3분류 → 당분간 보류, 대체 경로

- 변화/비변화 인간 라벨링은 보류(사용자 결정 2026-08-12). 대체: 확정 93 내
  **A-티어 23동 = 변화 후보 풀**(커버리지 정상 + 강한 불일치)로 M1 사례 채굴을
  국소 수행. 전면 층화 집계는 라벨 확정 시 재개(D-F 규칙 자체는 유지).

### 2.4 사전 등록 추가 (측정 해석 규칙)

- **정합 스코프 3단**: 기지 datum 변환=전처리(주장 아님) / 지오레퍼런싱 후 fine
  잔차(실측 z 0.092 m·xy p95 0.41 m)=M2 흡수 주장 구간 / ≥1 m 계통=흡수 금지,
  conflict 맵의 탐지 대상.
- **이득/비용 채널 분리 판독**: completeness/coverage는 OR-집계+τ 버퍼로 무딘
  이득 지표(E2 성분이 보험) — δ·변화에서 높게 유지되는 것이 union 강건의 증거가
  될 수 없음. 비용 채널(z-spread·precision·normal·Roofer)이 1차 판독. τ 민감도
  (0.1/0.25) 교차 확인. (Phase D 문서 §1·§3-5와 상호 참조)

### 2.5 Verification 지위 승격: 선택적 피벗 → Claim A의 필수 동반

- 확장 구역(제외 105)은 현재 참조가 없어 Claim A의 큰 이득을 증명할 수 없음 →
  prior 재사용의 안전 인증(conflict/currentness 맵)이 범위-확대 주장의 완결
  조건. E5 conflict confidence의 건물별 집계 → 변화 후보 판별력(ROC) 실험 신설
  (H-V). 불변식 12(변화 건물 temporal status) 준수.

### 2.6 텍스처: 별첨 → Claim B 제3 실패 모드(외관 일관성)

- 표현 경계: union도 사후 투영 텍스처는 가능 — 주장은 "불가"가 아니라
  "채움 영역은 색 근거가 없고, 투영 품질이 기하 정확도에 종속되어 이중 표면·
  stale에서 고스팅·가림 오류를 물려받으며, 별도 메싱+매핑 공정이 필요한 사후
  처리"다. GS는 외관이 기하와 공동 최적화된 네이티브 산출물(기존 시맨틱 텍스처
  메시 계약 인용).
- 근거 계획: **bounded 정성 데모** — 소수 건물(ALS-채움 영역 포함)에서 union
  메시+현재 영상 투영 vs GS 텍스처 메시 병렬 패널(기존 texture bake 기계 재사용,
  별도 승인).

## 3. 실행 순서 v2 (승인 후)

1. **Phase D** δ-shift 파일럿 (설계 확정, D1 union CPU 반나절 → D2 코리도 GPU 하룻밤 → D3 판정)
2. **M1 사례 채굴**: A-티어 23동에서 E8 stale-혼입 vs GS 중재 사례 정성+정량
3. **H-V**: E5 conflict 맵 → 변화 후보 ROC (verification 산출물화)
4. **텍스처 데모**: bounded 정성 패널
5. Phase C 본판독(93 모집단 재집계) + 교수 보고

## 4. 미결정 (사용자/교수 확정 필요)

- E5 F1 conflict 게이트의 Phase D 확장 여부(현 코리도는 e4-계열 confidence 게이트)
- GS(δ) 풀신 확장(코리도에서 효과 확인 시)
- E9(합성+Poisson) 유지/폐기
- 텍스처 데모 범위(건물 수·비교 조건)
- 본 개정의 v1 본문 반영 방식(v2 전면 개정판 발행 vs 본 대비표 유지)
