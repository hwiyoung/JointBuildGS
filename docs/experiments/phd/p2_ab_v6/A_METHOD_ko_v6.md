# A v6 — 실제 P2 영상으로 측정한 조건부 법선 변위 구간

이 실행은 기존 22 decision 영상에서 실제 MVS·ALS 후보 평면의 사진 일치도를 측정하고,
현재 MVS Gaussian의 변경 가능 범위를 B에 전달한다. 공동 시스템 오차를 보정한 절대
소스 승인 결과는 아니다. `systematic_error_calibrated: false`,
`absolute_source_authority_status: ABSTAIN_UNCALIBRATED`, `scientific_verdict: null`이다.

## 관측과 계산

기존 33 train 영상은 B, 11 appearance_eval 영상은 결과 비교에 남긴다. A는 별도 22
decision 영상을 두 11뷰 집단으로 나눈다. 다만 MVS·pose의 원영상 계보는 공유하므로
독립 센서나 새 확증 표본이라고 부르지 않는다. UAS·LoD2 참조를 읽지 않는다.

동일 P2 MVS G0 266,361개에서 native patch별 1m voxel의 실제 원점 16,476개를 선택한다.
각 점의 원래 법선을 따라 −0.30~+0.30m, 0.05m 간격의 후보 평면을 평가한다. 각 영상
집단에서 전경 가림·투영 영역·법선 관측각을 확인한 후 시차가 있는 한 영상쌍을 고른다.
영상쌍 선택은 색 잔차를 보기 전에 고정한다. 한 집단의 관측에 영상쌍 하나만 쓰는
국소 진단이며 11뷰 모두의 통합 깊이 최적화가 아니다.

기준 영상의 고정 7×7 pixel 중심에서 각 후보 평면과 ray를 교차시킨 후 상대 영상에
재투영한다. 모든 변위에서 동시에 유효한 동일 pixel을 사용하며 가림으로 좋은 부분만
선택하지 않는다. 기존 fullscene MVS depth는 알려진 전경 제외에만 쓰며 미상은 남긴다.
평가량은 회색조 ZNCC에서 얻은 `(1−ZNCC)/2`이다. 학습된 SH·노출 계수를 맞추지 않으며
국소 평균·표준편차 정규화만 한다. 저텍스처·작은 지지·큰 잔차·다봉·검색 경계·집단
불일치에서는 변위 근거가 없는 것으로 기록한다. 기준값은 config에 사전 기록한 개발
설정이며 센서 오차나 통계적 신뢰수준이 아니다.

각 집단의 최소 비용+0.03 이내인 연결 구간을 구하고 두 집단 구간의 **합집합 외곽**에
격자 반 간격 0.025m를 더한다. 이것이 `observation_low_m/high_m`이다. 사용오차 허용
ε=0.15m를 조건부로 가정하면 후보 변위 s가 구간 어느 위치에 대해서도 ε 이내가 되는
범위는 `[observation_high−ε, observation_low+ε]`다. 이 구간이 비면 갱신하지 않는다.
0이 포함되면 초기 보호 가능, 포함되지 않으면 보정 필요로 별도 표시한다. 이 수식의
보장은 측정 구간이 실제 위치를 포함한다는 전제 아래에서만 성립한다.

ALS 후보는 같은 unit 내 XY 1m 이내 최근접 실제 ALS 원점으로 제안한다. 이것은 물리적
대응을 확정하지 않는다. MVS 기준 영상 pixel과 동일 영상쌍에서 ALS 평면을 별도 평가하고,
두 후보 모두 유효한 pixel의 공통 분모에서 비교한 profile도 저장한다. 대응 없음·가림
없음·낮은 비용만으로 prior의 현재 사용을 자동 승인하거나 두 소스를 평균하지 않는다.

## B 전달과 한계

`mvs_profiles.npz`는 `cost[2,Nanchor,Noffset]`, `valid`, `offsets_m`, 원점 `seed_id`와
실제 영상쌍을 보존한다. `handoff_mvs.npz`는 전체 Gaussian에 원래 `seed_id`, `anchor_id`,
거리, 관측 구간, 후보 허용 구간, 목표 변위와 `observable/initial_eligible/correction_needed`
를 전달한다. 같은 native patch, 거리≤0.75m, 법선 cosine≥0.97인 최근접 anchor만 연결한다.
연결되지 않거나 관측이 불명확하면 `observable=false`다.

공간 전달은 가까운 평행 표면이 법선 변위 profile을 공유한다는 개발 가정이다. 실제
Gaussian별 독립 오차 상한이 아니며, 작은 창·배관의 변위를 검증한 것도 아니다. B는
이 구간과 실제 출력 depth·표면 지지 검사를 함께 사용해야 한다. 이 실행의 근거 범위는
현재 영상에서 얻은 법선 방향 변위 관측이며, 정합·공유 카메라 편향·소스별 시스템
오차를 모두 추정한 A 전체 방법의 완성으로 해석하지 않는다.

- [계산 구현](../../../../src/phd/p2_ab_v6/a_observational_envelope.py)
- [실행 script](../../../../scripts/phd/p2_ab_v6/a_observational_envelope.py)
- [설정](../../../../configs/phd/p2_ab_v6/a_observational_envelope_v1.json)
