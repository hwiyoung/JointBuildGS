# FUS-W1-APRIME-PREREG-001 — arm A′ 결과 열람 전 잠금

- 잠금 시각: 2026-07-26 21:00 KST
- 브랜치: `exp/fusion-w1`
- run: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/`
- 기계 정본: `phases/p2-gsjso/configs/fusion_w1_aprime_prereg_lock_20260726.json`
- 판정자: 김휘영. 이 run은 수치·관찰·권고만 기록하고 자동 판정을 만들지 않는다.
- 용어: 공개 코드가 없는 구성 차이 실험이므로 **GS4B 이식판**으로만 부른다.

## 고정 질문과 범위

질문은 “GS4B 이식판으로 ALS 기반 GS가 지붕을 유지하고, 그 출력이
CityGML 조립까지 성립하는가”다. GS4B의 LoD2 mesh prior를 ALS class 6
측정점/TIN으로만 치환한다. 학습 시드는 class 6뿐이며 class 2와 SfM 점은
들어가지 않는다. 원본 ALS class 2는 학습이 끝난 뒤 Roofer 입력에만 합류한다.

## 공개 원문에서 확인된 부분과 별도 채택값

GS4B 원문에서 확인된 부분은 mesh surface seed, 첫 ray–mesh 교차 기반 가시성,
뷰별 `D_j/N_j/M_j`, 각 prior 손실의 `1/|M_j|`, 2단계 loss scheduling,
30k, TSDF fusion + Marching Cubes다. 공개 원문은 `k`, 전환 iteration,
prior weight, 감쇠 함수, α 산출법을 제공하지 않는다.

별도 채택값은 다음과 같다.

- visibility: `epsilon=0.05 m`, `k=3`
- phase split: `0..14999` / `15000..29999`
- depth prior: phase 1 `0.5`, phase 2 exponential decay to `0.05`
- normal prior: phase 1 `0.05`, phase 2 exponential decay to `0.005`
- normal consistency: phase 1 `0`, phase 2 first 5k linear ramp to `0.05`
- distortion: phase 1 `0`, phase 2 first 5k linear ramp to the existing
  meter-frame port setting `100/scene_scale^2`
- depth α: valid `M_j`에서 detached least-squares scalar를 매 iteration 계산,
  clip 없음, 비유한/0 분모는 fail-closed
- seed protection: 모든 lineage 보호 off
- gsplat default dynamics: opacity `0.1`, prune `0.005`, grow grad `0.0002`,
  refine `500..14999`, every `100`, reset every `3000`

λ depth `0.5`와 normal `0.05`는 GS4B 수치가 아니다. 본 run에서 전자는
CityGaussianV2 계열, 후자는 DN-Splatter 계열 범위를 이식 근거로 기록한다.
distortion `100/scene_scale^2`는 새 문헌 귀속값이 아니라 기존 W1의
EPSG meter-frame 2DGS port 설정을 유지한 값이다.

## P7 분기 잠금

공개 GS4Buildings 저장소와 논문에는 9개 subset의 좌표, footprint, 이미지 명단,
`DEBY_LOD2_*` crosswalk가 없다. 겹침은 `0`이 아니라 `unknown`이다. 따라서 P7의
사전 선언 fallback을 적용한다. 대상은 기존 178동 정본에서
`priority_bucket == 01_p0_dim_failure`인 8행과
`selection_reason`이 `textured_positive_control_anchor:`로 시작하는 1행을
기계 조인한 9동이다. 정본은 `aprime_targets.csv`; 손입력 ID 목록은 없다.

실행 큐는 A′ r1 전 9동, A′ r2 전 9동, B r1은 첫 실패 2동과 textured control
1동이다. r1/r2 seed는 1001/1002다.

## Preflight와 본선 진입문

T1, T2, T3가 모두 PASS일 때만 30k 학습을 시작한다.

- T1: 기존 arm A 실측 + 600-iter 압축 스케줄 mini smoke. 전환 후 distortion과
  normal-consistency 각각 raw/effective/weighted/gradient/share가 모두 양수이고,
  보호 off와 실제 prune 양수를 확인한다.
- T2: 기존 arm A `final.pt`로 Open3D TSDF volume과 MC mesh 경로를 실행한다.
  품질 기대나 판정에는 쓰지 않는다.
- T3: 새 visibility-filtered class 6 seed와 원본 class 2의 학습 0 Roofer/채점값을
  대상 전 9동에 만든다.
- T4: 기존 smoke full-state 0/5k/10k/15k/20k/25k/30k에서 opacity proxy를
  재구성해 30분 안에 그림 1장을 고정한다.
- T5: 전 9동 `M_j` pixel fraction과 seed before/after/vote 통계를 집계한다.

같은 오류 3회는 그 동을 스킵하고, 같은 오류 유형이 3동 연속이면 그 단계를
중단한다. 사용자 질의와 시각 cutoff는 없다. 동별 완료 즉시 영수증을 저장한다.

## Readout 잠금

주 readout은 2DGS surface depth를 exact `M_j`로 마스킹해 Open3D
`ScalableTSDFVolume`에 적분한다. alpha threshold는 두지 않는다. voxel은
`0.05 m`, SDF truncation은 `0.25 m`, depth truncation은
`max(2*minimum_camera_radius, max_prior_depth+1 m)`로 계산해 실제값을 기록한다.
MC mesh에서 50 triangle 미만 component만 제거하고 `0.1 m` spacing으로 표면을
샘플한다. 샘플은 class 6, 원본 20 m buffer ALS ground는 class 2로 합류한다.
좌표/수직 datum 변환은 한 번만 한다.

기존 W1 alpha-point readout(`alpha=0.5`, `voxel=0.05`, `min_obs=3`)도 병행하되
비교 기록에만 사용한다.

## 금지

- 이전 arm A seed/supervision cache 재사용
- 보정 pose transform 재적용
- 학습 seed 또는 감독에 ground, wall, SfM, GT roof/final model 투입
- seed opacity/prune 보호 개입
- 개수로 명단 대체, censored 값을 실측처럼 기재, 자동 판정 문장
