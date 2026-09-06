# A — 판단 비교·개발 검증 결과

> 2026-09-06. `PHD-P2-AB-A-v1`. 기술 실행·계보 검사 완료, 비확증 개발 진단. `scientific_verdict: null`.
> [계산 전 프로토콜](A_DESIGN_ko_v1.md) · [이슈와 미결](A_ISSUES_ko_v1.md) · [실행 설정](../../../../configs/phd/p2_ab_v1/a_p2_v1.json)

## 1. 확인한 결과

**이 P2 개발 표본과 기본 설정에서는 finite-range 판단이 score gate나 Bayesian 비교법보다 유리하지 않았다.** 같은 64개 단위 중 range는 2개를 조건부 채택했지만 1개가 UAS 근접성 기준에 미달했다. score gate는 같은 채택 수 2개에서 미달 0개였고, 카메라쌍을 분리한 Bayesian 변형은 4개에서 미달 0개였다. 공유 위치오차 ±0.5m를 range에 넣은 조건은 전수 유보했다. 이 결과는 추가 계산으로 결정이 달라진 사실과 실제 유용성이 다를 수 있음을 보여 준다.

아래의 ‘미달/오채택’은 **현재 UAS와 legacy 수치좌표를 그대로 연결한 조건부 점군 진단**이다. EPSG:32632 UAS와 EPSG:25832 프로젝트의 datum·epoch 관계 및 참조 정확도를 보정하지 못했으므로 확정적 현재 참오차나 정식 PASS로 읽지 않는다. 모든 strict current-use 행동은 64/64 `ABSTAIN`이다. 판단법/문턱은 UAS 평가 결과를 보기 전에 동결했다.

기본 설정은 τ0.3, ε0.5m다. 조건부 참조 판별은 sampled 후보점 모두의 XY 0.5m 이내 UAS 지지와 prediction→reference nearest-3D p90≤ε를 요구한다. 기본 REAL의 모든 채택은 이 조건에서 참조 피복을 얻었다.

| 판단법 | 조건부 채택/64 | 기준 미달/평가된 채택 | 미달 비율 | 쓸 수 있는 후보가 있지만 유보/해당 단위60 |
|---|---:|---:|---:|---:|
| IMAGE 고정 | 63 | 9/63 | 14.3% | 1/60 |
| PRIOR 고정 | 50 | 25/50 | 50.0% | 11/60 |
| 사진 score gate | 2 | 0/2 | 0.0% | 58/60 |
| Bayesian, 카메라쌍 분리 | 4 | 0/4 | 0.0% | 56/60 |
| Bayesian, 모든 중복쌍 | 5 | 3/5 | 60.0% | 57/60 |
| Finite range | 2 | 1/2 | 50.0% | 59/60 |
| Finite range + 공유 위치 범위 | 0 | 0/0 | **null** | 60/60 |

0/2와 0/4는 적은 개발 채택에서 관측한 수치이며 오판 확률이 0이라는 보장은 아니다. Bayesian의 중복쌍 arm과 분리 arm의 차이도 이 단위들에 대한 관측이다. 쌍 분리의 일반적인 우월성이나 독창성을 주장하지 않는다. 실제 남은 카메라·정합 공통오차는 분리 arm에도 존재한다.

## 2. 무엇을 구현·실행했나

P2 전체 552개 2m XY 단위에서 공통 manifest가 먼저 고른 **동일 64개**를 사용했다. native source의 dominant planar patch만 후보화했고, IMAGE 63·PRIOR 50·파생 FUSION 39로 총 152개 후보, 9,005개 sampled 후보점을 만들었다. 선택한 단위 안의 다른 층과 patch는 공통 자료에 보존했으며 `excluded_layers.json`에 제한 범위를 남겼다. 선택 단위를 다른 좋은 단위로 교체하지 않았다.

새 decision 22개 영상에서 원후보와 33개 scene-Z 높이를 측정했다. 기하 조건을 만족한 뷰쌍 128개에서 후보별 동일한 all-height 지지를 유지했다. 7개 판단법×8개 실제/통제 조건×4개 τ×3개 ε×64개 단위로 **43,008행**을 저장했다. 이는 **64개 단위를 반복한 설정 행 수**이며 독립 표본 수가 아니다. 기본 설정의 방법·통제별 인계 3,584행이 B에 제공된다.

Bayesian 비교는 원논문 Gaussian+uniform likelihood 식 (1)–(2)의 bounded full height×inlier-rate posterior를 구현하고, 고정 후보의 ε 안 사후질량과 예상 절대오차로 네 행동에 대응시킨 변형이다. 원논문의 Gaussian×Beta 실시간 시스템·전체 MVS·독립 정합 알고리즘 재현이 아니다. 두 소스의 roughness와 조건부 삼각측량 분산을 각각 반영하지만 보정된 소스/정합 공분산은 아직 없다. [정확한 원출력·변형·행동 대응](A_DESIGN_ko_v1.md)

추가 range 계산은 모든 적합 이산 높이, 경계 설명, 후보별 B/U와 공유 이동 민감도를 남긴다. 기본 REAL 152후보의 상태는 적합 집합 없음 102, 조건부 반대 22, 모호 12, 이산 조건부 지지 3, 검색 경계 미확정 13이었다. 3개의 지지 후보 중 하나는 FUSION 부모 조건을 충족하지 못했으므로 실제 행동은 IMAGE 2개가 됐다. **적합 집합 없음 102개를 현재 기하 오류 102개로 해석하지 않는다.**

## 3. 유지·실패·유보를 같은 ID로 추적

| 단위와 의미 | 측정과 결정 | UAS 조건부 근접성·해석 |
|---|---|---|
| `P2_X062_Y065`: 서로 다른 선택이 모두 사용할 수 있는 사례 | score는 PRIOR(ci54), Bayes/range는 IMAGE(ci53). range의 U_height=0.125m, 조건부 Z 예산0.375m | IMAGE NN3d p90=0.050810m, PRIOR=0.056258m, FUSION=0.051489m. 단일 정답 출처 라벨로 score를 오답 처리하지 않음 |
| `P2_X066_Y043`: range의 조건부 오채택 | IMAGE(ci71)에 남은 높이는 −0.375·−0.25m; U_height=0.375m, 예산0.125m. 원점수 약0.008로 score/Bayes는 유보 | NN3d p90=0.781789m; nearestXY |ΔZ| p90=0.904119m, signed ΔZ median=−0.661812m. 이 좁은 이산 집합을 현재오차 보장으로 사용할 수 없음 |
| `P2_X055_Y051`: Bayesian 조건부 구제 | score/range는 유보, 카메라쌍 분리 Bayesian은 IMAGE(ci2) | IMAGE NN3d p90 약0.087m. 낮은 중앙사진점수와 여러 쌍 peak 분포의 다른 판단 결과이며 원인 식별/일반화 증거는 아님 |
| `P2_X078_Y056`: 실제 자연 MVS 결손 | raw MVS=0, raw ALS=160. PRIOR 후보(ci148)만 있고 모든 관측 판단법은 유보. 고정 prior는 선택 | PRIOR NN3d p90=0.079277m. 현재 구현이 유효한 prior 후보를 자동 활용하지 못한 사례이며, 전수 MVS제외 통제와 구별 |

높이범위 U는 **후보 전체를 Z로 옮긴 이산 설명**의 최대 이동이다. NN3d p90는 다른 지표이고 nearestXY 높이차도 동일 표면 대응이 보장되지 않는다. 위 실패는 현재 범위가 절대오차 보장을 확보하지 못했다는 개발 증거지만, 두 지표를 직접 나누어 확률적 coverage나 엄밀한 bound 위반율로 보고하지 않는다. 가림·반복 질감·공유 위치오차·격자/표면모형 실패 중 원인은 분리되지 않았다.

## 4. 실제와 통제 조건 결과

아래 셀은 **채택 수 / 그중 조건부 기준 미달 수**다. 모든 조건의 전체 분모는 64이며 미달률은 채택 중 평가가능한 수를 분모로 한다. 기본 설정에서 이 표의 채택은 모두 참조 지지를 얻었다. 전수 유보 `0/0`의 미달률은 null이다. 전체 방법·유효후보 유보 분모는 그림과 JSON/CSV에 보존했다.

| 조건 | Score | Bayes 분리 | Finite range |
|---|---:|---:|---:|
| 실제 입력 | 2 / 0 | 4 / 0 | 2 / 1 |
| MVS 입력 제외 | 1 / 0 | 2 / 0 | 0 / 0 |
| MVS 사용불가 표기 통제 | 1 / 0 | 2 / 0 | 0 / 0 |
| PRIOR +1m | 3 / 2 | 4 / 0 | 3 / 2 |
| IMAGE +1m | 3 / 2 | 2 / 0 | 4 / 3 |
| 둘 다 +1m | 4 / 4 | 0 / 0 | 4 / 3 |
| 관측 1쌍 제한 | 0 / 0 | 0 / 0 | 0 / 0 |
| 사전 지정 교대 단위 PRIOR +1m | 4 / 2 | 4 / 0 | 3 / 2 |

일치한 두 후보를 함께 이동한 조건에서도 무조건 선택은 남고, 사진검정법 역시 잘못된 선택을 남길 수 있었다. 이를 자연 변화 검출 정확도로 부르지 않는다. 부모 한쪽을 이동한 FUSION compatibility는 정확한 이동후 거리 대신 `원래 최대거리+상대 이동 크기`의 보수적 상한을 사용하여 더 유보할 수 있다. 이 제한은 [이슈](A_ISSUES_ko_v1.md)에 명시했다.

τ·ε의 모든 설정을 [위험–채택 범위 PNG](../../../../../JointBuildGS-artifacts/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-A-FIGURES-v2/risk_coverage.png)와 [3페이지 PDF](../../../../../JointBuildGS-artifacts/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-A-FIGURES-v2/A_decision_validation.pdf)에 담았다. 차트의 중복 좌표는 같은 결과의 반복 설정이며 독립 관측을 의미하지 않는다. 0채택 설정은 숫자 축의 위험0에 놓지 않고 별도로 표시했다.

## 5. B·C 연결과 실행 검증

`candidates.npz`의 native rows와 실제 파생 평균을 인계했으며, B는 동일 `unit_id`와 `candidate_index`를 읽는다. 기본 range의 실제 두 IMAGE 후보 및 Z성분 예산, Bayes와 score의 다른 조건부 후보를 분리 비교할 수 있다. strict 유보 출력과 실제 관측에 의한 조건부 개발 재구성을 구분한다. 학습·표면추출 후의 결과는 B/C 기록이 별도로 판단한다.

- Docker 판단 단위검사 13개 PASS: 공통쌍·분리쌍·다봉 높이·검색경계·빈집합·공유편향·Bayesian 대칭·flat 비용·FUSION 부모·MVS없음·미확정 계약·유보/참조 분모.
- 실행 후 strict API의 부정형 사유 flag와 긍정형 인증계약을 분리하고 오용방지 검사를 추가하여 현재 source 14검사 PASS. 실행본 source snapshot은 보존하며 실제 default 행동은 바뀌지 않는다. [A-008](A_ISSUES_ko_v1.md)
- native 후보 113개가 공통 원좌표·원행·unit·patch와 정확히 일치하고, FUSION 39개의 좌표가 명시한 두 native 소스 점의 산술평균과 정확히 일치함을 독립 재검사했다.
- 기본 인계 3,584행의 후보/단위/이동/예산, 카메라쌍 중복 제거, strict 유보를 검사했다. 원입력 및 실행 snapshot 소스 해시 불변 PASS.
- A 본 실행은 약18.1초, `jointbuildgs:dev` 고정 image `sha256:251f83…`의 CPU4·memory6GiB·network none에서 완료했다. 비교 계산의 전용 run이며 이전 실행 폴더를 덮어쓰지 않았다.
- 전체 posterior mass·실제 선택쌍·조건표·다른 층 제외표·그림을 additive 분석 폴더에 남겼다. 그 뒤 참조에 맞춰 A의 문턱이나 후보를 바꾸지 않았다.

주요 외부 산출물은 다음과 같다.

| 위치 (`../JointBuildGS-artifacts/phase-payloads/phd/p2_ab_v1/` 아래) | 역할 |
|---|---|
| `PHD-P2-AB-A-v1/` | 사전설정·source snapshot·measurement·후보·43,008행 판단·3,584행 인계·기술영수증 |
| `PHD-P2-AB-A-ANALYSIS-v1/` | 원점/평균 검산, 원 Bayesian posterior·쌍 목록, 다른 층 제외 수, 결정 전이와 관측곡선 |
| `PHD-P2-AB-C-A-v1/` | A가 읽지 않은 UAS를 사용한 reference-only 후보·판단 평가; 전체 risk–coverage와 같은 ID의 결합표 |
| `PHD-P2-AB-A-FIGURES-v2/` | 최종 static PDF/PNG, 모든 기본 조건 분모, illustrative 실패·유지·구제, 실제 source availability 보충표 |

**현재 기술 결론:** 판단 비교와 실제 입력 기반 A→B 인계를 구현·실행했다. 이 제한된 finite-range 구현의 강한 Bayesian 변형 대비 이득은 확인되지 않았고, 높은 유보와 1개 조건부 오채택을 실제로 남겼다. 다음 설계에서 보완할 것은 유리한 문턱 찾기가 아니라 미검증 관측/공유오차·연속설명 포함·점→면 인계 계약이다. 완전한 기존 시스템 재현·보정된 현재 참오차·확증 성능은 완료되지 않았다.
