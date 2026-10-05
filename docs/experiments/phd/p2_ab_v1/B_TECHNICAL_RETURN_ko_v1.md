# B — 동일 P2 재구성 개발 결과

2026-09-06. 비확증 개발 결과. `scientific_verdict: null`.

**A가 실제 사진에서 만든 conditional 선택을 받아 5개 판단법×4개 재구성의
분리 비교를 실행했고, 추가로 DN-Splatter 원구현의 source-prior adapter 실행을
완료했다.** 기하 고정에서도 외관 오차가 줄었다. 현재 explicit 표면 제약은
RANGE의 모든 기하 갱신을 거부해 fixed GS와 같은 결과를 냈다. 재구성의 추가
이득이나 현재 기하 정확성 개선이 입증되었다고 판단하지 않는다.

## 1. 입력·산출과 범위

공통 `PHD-P2-AB-COMMON-v2`의 64 pilot unit, A-v1 exact 후보 소속,
33 train/11 appearance_eval을 사용했다. 각 후보는 A의 정확한 `candidate_index`
좌표·법선에서 thinning했다. 동일 P2 전체 원입력에서 정한 crop/K/V가 모든
판단법과 DN에서 같다. 초기·최종 Gaussian, expected-depth 추출표면,
eval RGB/depth/alpha·현재영상, 각 unit의 handoff를 저장했다.

| A 실제 conditional 인계 | seed Gaussian | 초기 eval 표면 pixel 합 | B 비교 |
|---|---:|---:|---|
| DISCRETE_RANGE | 96 | 765 | texture / fixed / prior-loss / constrained |
| SCORE_GATE | 97 | 1,171 | 동일 4개 |
| BAYES_GAUSS_UNIFORM | 222 | 3,003 | 동일 4개 |
| FIXED_IMAGE | 3,204 | 50,914 | 동일 4개 |
| FIXED_PRIOR | 2,427 | 32,706 | 동일 4개 + adapted upstream DN |

이 pixel 합은 다뷰 표현 표본 수다. 지붕 면적, 독립 관측 수, 현재 사용이
승인된 면적이 아니다. 모든 strict_current_use_action은 ABSTAIN이며,
`DISCRETE_RANGE_SHARED_SHIFT`의 실제 인계 경로는 **64 unit 보존·0 Gaussian·
`ABSTAIN_NO_GEOMETRY`**를 확인했다. 유보를 빈 결과의 좋은 오차로 바꾸지 않았다.

## 2. 같은 판단 안에서의 재구성 차이

다음 RGB MAE는 `[0,1]` 색의 **각 방법 초기 alpha≥0.5 고정 support**에서
계산한 11뷰 MAE의 평균이다. A가 다르면 support가 다르므로 이 표로 판단법
사이의 외관 우열을 매기지 않는다. A 간 공통 ray-mask 평가는 C에서 분리한다.

| A 인계 | 단순 source texture | fixed GS | prior-loss GS | constrained GS |
|---|---:|---:|---:|---:|
| RANGE | .1910 | .1786 | .1763 | .1786 |
| SCORE | .1547 | .1356 | .1343 | .1356 |
| BAYES | .1977 | .1755 | .1697 | .1755 |
| IMAGE 고정 기준선 | .1975 | .1828 | .1800 | .1828 |
| PRIOR 고정 기준선 | .2098 | .2003 | .1985 | .2003 |

기하를 고정한 외관 적합만으로도 측정 MAE가 줄었다. prior-loss는 이보다 조금
낮은 MAE를 보였지만 표면의 소실·새 footprint·깊이 변화가 함께 생겼다.

| prior-loss GS의 인계 | 초기 support에서 소실 pixel | 새 alpha support pixel | 겹친 ray의 최대 expected-depth 변화(m) |
|---|---:|---:|---:|
| RANGE | 3 | 38 | .0992 |
| SCORE | 8 | 96 | .2846 |
| BAYES | 17 | 233 | .4949 |
| IMAGE 고정 기준선 | 210 | 2,231 | 4.6290 |
| PRIOR 고정 기준선 | 155 | 1,560 | 4.6434 |

이는 **렌더에서 읽은 표면 변화**이며 Gaussian 중심의 이동량이나 현재 UAS
오차가 아니다. alpha·scale과 여러 층의 혼합 때문에 중심의 작은 이동과
expected-depth 표면의 변화는 다를 수 있다. 실제 정확성은 C의 평가 전용
UAS 대응에서 별도로 판단한다.

RANGE의 단위별 유한 높이 budget .375/.125 m에서 보수적으로 .125 m를
사용했다. 예산의 성분에 맞춰 후보별 scene-Z translation만 움직였다.
72/72 geometry proposal이 train-view mask 소실/침범 검사로 거부되었다.
이는 제약 구현이 보존을 강제한 결과이나 **현재 방식이 경계에 너무 엄격해서
유용한 변화도 막을 수 있다는 실패 신호**다. 사후에 검사 문턱을 완화해 결과를
고르지 않았다. 다른 인계는 모든 단위의 budget이 없어서 constrained geometry를
고정했고, fixed GS와 같아야 하는 경로를 그대로 확인했다.

## 3. 강한 기존법의 실제 구현 연결

DN-Splatter pinned `97588b4290128ce7ba6fdbfaac3020b42b17de4c`를 Docker
`jointbuildgs:dn-splatter-upstream-97588b4`에서 원코드 수정 없이 96 step 실행했다.
PRIOR-v2의 exact 2,427 source point와 같은 33/11 crop를 제공하고 source GS 초기
expected depth를 prior-depth로 사용했다. 현재 UAS/LoD2 참조 입력은 없다.

DN은 자체 3DGS 표현·초기 opacity/scale·source-PCA normal·기본 optimizer와
depth/normal regularization을 사용하므로 같은 source 입력의 원구현 adapter
비교다. 본 B solver와 동일한 초기 Gaussian이라고 부르지 않는다. 별도 seed0/config
초기 모델을 만들어 초기표면도 추출했다. SH0 경로의 upstream API 실패는 v1에
보존하고, official SH3 default로 v2를 완주했다. 96 step은 degree 증가 전이며
학습 수렴이나 논문 성능 재현은 평가하지 않았다.

DN의 초기표면은 6,898 pixel, 최종은 25,976 pixel이다. 자기 초기 support에서
590 pixel이 사라지고 19,668 pixel이 새로 생겼으며, 겹친 ray 최대 깊이 변화는
13.522 m였다. 자기 초기 support의 최종 11뷰 평균 MAE는 .2097이다. 초기 표현과
분모가 달라 위 B 표와 직접 우열을 매기지 않는다. C의 고정 공통 mask·현재 UAS
오차·누락을 함께 보아야 한다.

C-v2의 별도 UAS 평가에서는 DN의 reference-neighborhood coverage가
초기 .3022186에서 최종 .3018947로 바뀌었다. 출력 unit은 49/64이고 15개는
누락으로 남았다. 대응 49개 unit의 p90 기하오차 변화 평균은 +.021471 m였으며,
1 mm 표시 구간에서 13개 개선·35개 열화였다. 이 구간은 표시용 구분이며 과학적
합격 문턱이 아니다. 공통 ray-mask에서는 DN의 PSNR이 9.902 dB, 2D PRIOR fixed GS가
8.008 dB였지만, 해당 mask의 최종 표면 존재율은 각각 34.22%와 46.91%였다.
외관 숫자의 개선과 기하/완전성 변화가 함께 있으므로 전체 우월성으로 결론 내리지 않는다.

## 4. 산출·검증·남은 작업

신규 외부 결과의 부모 경로는
`/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/`다.

| 새 run | 용도 |
|---|---|
| `PHD-P2-AB-B-{RANGE,SCORE,BAYES,IMAGE}-v1` | 5×4 분리 비교 중 4개 A 인계 |
| `PHD-P2-AB-B-PRIOR-v2` | 공통 crop를 정렬한 PRIOR 4개 arm |
| `PHD-P2-AB-B-SHARED-SHIFT-v1` | 모든 unit의 ABSTAIN 전파·seed0 검사 |
| `PHD-P2-AB-B-DN-v2/dn_splatter_original_v2` | 공통 B 스키마로 연결된 upstream 초기/최종 surface·RGB |
| `B_VERIFICATION_v2.json` | Docker 테스트·최종 코드/설정/본문 hash·단위/카메라/표면/target identity 검증 |

8개 계약 테스트는 점→면 권한 누출, 유보와 FUSION exact geometry, source group
보존, affine gauge, 표면 소실·침범·최대변형 규칙을 검증한다. actual artifact 검사로
공통 crop/K/V·역할 44개, 현재 target pixel 동일성, finite surface 좌표,
strict 채택0, shared-shift64 유보를 확인했다. DN target11개는 byte identity까지
확인했다. 이전 native payload와 protected E/C 산출·기존 문서는 수정하지 않았다.

**아직 확보하지 못한 것:** 점 지지의 면 지원 승인, 가림·공유 카메라 오차의
보수적 상한, 새로운 세부/접합/증감 권한, 연속 표면 인증·최종 triangle mesh,
강한 방법의 수렴·resource-matched 성능 비교와 독립 장면 일반화다. 표면 연결과
Gaussian 증감은 authority가 없어 v1 main에서 꺼 두었다. 구조/detail 분해가
기여라는 결론이나 수식만으로 세부 복원을 검증했다는 결론은 내리지 않는다.
현재 완료한 것은 이 미결을 숨기지 않고 실제 conditional 판단을 재구성·검증까지
추적하는 실행 가능한 개발 비교다.

재현은 기존 run을 재사용해 덮어쓰지 않고 새 output ID에서 수행한다. 일반 B는
`b_run_docker.sh <b_config> <new_run_id>`, DN은 `b_dn_run.sh <new_DN_run_id>` 후
`b_dn_evaluate_docker.sh <same_new_DN_run_id>`를 쓴다. 원 실행의 code/CLI와
후속 schema/검증 보완을 구분하며, manifest의 source hashes는 검증 시점 최종
재현 코드 snapshot이다. 공식 DN checkpoint config.yml은 실행 당시 실제 설정으로 보존되어 있다.
