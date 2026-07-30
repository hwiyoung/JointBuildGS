# P7 — GS4Buildings 9개 subset 겹침 조사

- 재조회: 2026-07-26 20:51:35 KST
- 결론 필드: `overlap_status=unknown`; `overlap_count=null`
- P7 분기: fallback 적용

## 공개 자료

- arXiv: <https://arxiv.org/abs/2508.07355>, v1, 2025-08-10
- 공식 저장소: <https://github.com/zqlin0521/GS4Buildings>
- 조회한 `main` HEAD: `1d25dac38d44a72cbf60a0bab730eed7f9e3663a`
- 공개 파일: `README.md`, `docs/GS4Buildings_Overview.png`
- README 상태: `Code coming soon!`

논문은 TUM2TWIN UAV 1,179장, 70동 이상, `Scene 1..9`의 서로 다른 cluster,
subset당 약 10–30장까지만 공개한다. scene별 좌표, footprint, 건물명,
Bavaria `DEBY_LOD2_*` ID, 이미지 명단은 없다. arXiv source 그림 내부명
`building1/4/6/10`도 canonical ID나 scene crosswalk가 아니다.

TUM2TWIN과 이 repo가 공통 LoD2 tile `690_5334/690_5336`을 쓰는 것은 확인되지만,
9개 cluster의 동별 membership을 178동 정본에 exact join할 자료가 아니다.
형상 눈대중 ID 추론은 P7 계약상 금지한다.

따라서 “겹침 없음”이 아니라 “식별 불가/unknown”으로 기록한다. fallback 9동은
`fusion_w1_aprime_targets_20260726.py`가 기존 `w1_targets.csv`의 semantic field를
조인해 만들었다. 출력은 `aprime_targets.csv`와 `aprime_targets_manifest.json`이다.

## GS4B 레시피 공개 범위

- LoD2 mesh face-area-weighted surface sampling, SfM seed 미사용
- first ray–mesh intersection과 expected depth 차이로 visibility 계산;
  `epsilon=5 cm`는 예시, `k`는 미공개
- raycast `D_j`, `N_j`, `M_j`
- depth/normal prior 모두 `1/|M_j|`; α는 scale adjustment factor라고만 기재
- phase 1 prior 강조, phase 2 prior 감쇠 + distortion/normal consistency 활성
- 30k, TSDF fusion + Marching Cubes
- prior weight, phase transition, α 계산법은 미공개

따라서 이 run의 `k=3`, 15k split, λ 0.5/0.05, α estimator는 모두
사전등록된 이식판 선택값이며 GS4B 공개 수치로 귀속하지 않는다.
