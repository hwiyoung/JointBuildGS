# RETRACTED — 4907182 A′ r1 panel v5 first-row locator

> 기록일: 2026-07-28
> 산출물 보존: 기존 `panel.png`와 `complete.json` 삭제·수정·덮어쓰기 금지

v5 첫 행은 승인 GroundSurface XY를 한 개의 median roof height에 올려 투영했다. 이 평면 locator는
실제 경사·단차 지붕의 3D 경계가 아니므로 사진–지붕 정합 근거로 사용하지 않는다. 학습·TSDF·Roofer·점수
산출물은 이 회수의 대상이 아니며, v5는 시각 backfill 기록으로만 보존한다.

대체 산출물은 별도 namespace
`review_v6_roof_boundary/by_building/DEBY_LOD2_4907182/arm_Aprime/r1/`에 있다. v6는 실제 ALS
class-6 supervision TIN의 incidence-one 3D boundary와 k≥3 시드를 공통 datum-safe projector로
표시한다. 다만 v6도 RGB 독립 semantic/occlusion gate를 실행하지 않았으므로 해당 패널의 첫 행은
`REVIEW_NEEDED` 관찰로 취급한다.
