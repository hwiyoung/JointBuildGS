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

- [docs/GSJSO_loss_audit.md](GSJSO_loss_audit.md) — **P2 방법 설계**: 구현 손실 ↔ 스케치 설계 대조 audit.

## P2 준비 (도구 적합성 점검 — 의미 라벨/prior 켜기 전 단계)

| 순서 | 활동 | 문서 | 이전 별칭 |
|---|---|---|---|
| P2 준비-1 | 엔진 전이 점검 | [docs/TUM_transfer_check.md](TUM_transfer_check.md) | 단계 1 / P2-2 |
| P2 준비-2 | 건물 품질·커버리지 | [docs/TUM_quality_coverage.md](TUM_quality_coverage.md) | 단계 1b / P2-3 |
| P2 준비-3 | TSDF·Roofer 바닥·1동 end-to-end | [docs/TUM_tsdf_roofer_probe.md](TUM_tsdf_roofer_probe.md) | 단계 1c / P2-4 |
| P2 준비-4 | 노이즈 정리 확인 (control 1동, proper settings) | [docs/TUM_noise_check.md](TUM_noise_check.md) | — |

**P2 준비 요지(누적):** 엔진은 TUM에 전이됨(준비-1). GS *센터* 점군은 ALS 대비 희박(준비-2). 표준 depth→TSDF는
밀도·모델생성을 해소해 end-to-end 유효 모델이 나오나, 7k-vanilla depth 노이즈가 Roofer를 과분할시킴(준비-3:
지붕면 32 vs reference 3). 준비-4는 그 노이즈가 *학습 설정*만으로 reference 수준에 가까워지는지 확인한다.

## 다음 순서

1. **노이즈 정리 확인** (P2 준비-4, 진행) — 설정으로 노이즈가 잡히는지.
2. **라벨 단계** — 의미 라벨(roof/wall/terrain) 소스 마련 (실데이터엔 부재; `GSJSO_loss_audit.md` §3).
3. **효과 검증** — 의미·기하-의미 prior(`L_sem`·`L_mutual`·`L_structure`) 켜고 ablation으로 효과 격리.

> 판정은 사람. 각 준비 문서는 측정·관찰까지(판정 금지).
