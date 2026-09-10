# 고정 사례의 normal 관측 비용 검증 결과 v3.7

- task_id: PHD-LOCAL-NORMAL-PHOTOMETRY-v3.7
- scientific_verdict: null
- 상태: 계산·별도 참조 평가·브라우저 및 육안 검증 완료
- [실행 전 명세](NORMAL_PHOTOMETRY_SPEC_ko_v3_7.md)
- [사례별 새 뷰어](http://localhost:8905/packets/packet_normal_photometry_v3_7_20260911T113326_160982Z/index.html)

## 확인된 결과

기존 8개 위치의 계산은 정상적으로 재현되지만 **normal 추가만으로 비용이 더 정확한 source를 지지하도록 바뀌지는 않았다.** 독립 기하·밝기 단위 검사 6개, 실제 입력의 부모 raw9 재현·homography·ZNCC 등 수치 검사 519개가 통과했다. 이는 구현 검증이다. 정확한 source를 판별했다는 뜻은 아니다.

가장 중요한 실제 반례는 P2_high_disagreement, 기준 사진 DJI_20241217084505_0076_D.JPG의 중심 (1249,737)이다. 비용은 각 크기에서 동일 공통 표본·수치 요건을 충족한 5개 이웃의 중앙값이다. 참조 오차는 각 패치에서 두 source와 raw/plane 네 조건 모두가 공유하는 원 UAS 점 ID의 camera-Z 절대오차 중앙값이다.

| 패치 | raw Prior / DA3 비용 | normal 평면 Prior / DA3 비용 | 사진 비용 해석 | 동일 참조 ID 수 | raw Prior / DA3 참조 오차 |
|---|---|---|---|---:|---|
| 9×9 | .3715 / .5247 | .3637 / .5235 | 두 방식 모두 Prior를 지지 | 34 | 3.351m / .368m |
| 17×17 | .4805 / .5195 | .5001 / .5095 | 시점에 따른 차이·작은 차이로 유보 | 124 | 3.346m / .372m |
| 33×33 | .6544 / .1342 | .6557 / .1276 | 두 방식 모두 DA3를 지지 | 428 | 3.352m / .397m |

평면 가설의 참조 오차도 9×9에서 Prior 3.360m / DA3 .371m, 33×33에서 3.419m / .394m다. **9×9의 비용 지지는 참조 근접성 순위와 반대**이며 normal을 넣어도 유지된다. 33×33에서는 같은 방향이다. 이는 이 사례에서 패치 문맥이 판별에 영향을 주었다는 근거다. 33×33을 새 최적 패치 크기로 채택하거나 큰 패치가 항상 옳다고 결론 내리지 않는다. 크기가 달라지면 평가 표면 범위와 참조 ID 집합도 달라진다.

## 8개 케이스를 함께 읽기

아래 지지는 사전 개발 수치(공통 지원 80%, std .02, 비용차 .02, 최소 2장, 방향 일치 75%)의 **사진 비용 방향**이다. 정답 판정이나 가중치 정책이 아니다. normal 추정 창은 9×9로 고정했고 점수 창만 9/17/33으로 바꿨다.

| 케이스 | Prior–DA3 평면 비용의 크기별 해석 | Prior–MVS 평면 비용의 크기별 해석 | 참조 검증 |
|---|---|---|---|
| P1 가까운 depth | DA3 지지 유지 | 시점·작은 차이 → MVS → MVS | 범위 밖 |
| P1 큰 depth 차이 | Prior 지지 유지 | Prior 지지 유지 | 범위 밖 |
| P1 Prior 결손 | 비교 불가 | 비교 불가 | 범위 밖 |
| P1 MVS 결손 | 시점·작은 차이 → DA3 → DA3 | Prior → 시점·작은 차이 → 지원 부족 | 범위 밖 |
| P2 가까운 depth | Prior 지지 유지 | Prior → Prior → 시점·작은 차이 | 범위 밖 |
| P2 큰 depth 차이 | Prior → 유보 → DA3 | MVS normal/지원 부족 | 위 반례, 크기 의존 |
| P2 Prior 결손 | 비교 불가 | 비교 불가 | 범위 밖 |
| P2 MVS 결손 | Prior 지지 유지 | 비교 불가 | 범위 밖 |

P1의 비용 상당수는 .4–.6 부근으로, 더 낮은 쪽도 사진을 잘 설명한다고 보기 어렵다. 상대 순위의 안정성과 절대 적합도는 다르며, 이 값으로 높은 감독 강도를 주는 근거는 확보되지 않았다. P2 가까운 depth에서는 Prior 비용이 낮고, 33×33에서 raw .1491→plane .0617로 개선되지만 해당 영역은 참조 범위 밖이라 정확성 개선으로 부르지 않는다.

MVS 결손은 비용 0이나 무한대가 아니며, Prior가 자동으로 정답이 되는 것도 아니다. 공통 비교가 불가능해도 해당 source 자체에서 계산할 수 있는 own-support 비용과 투영은 별도로 표시했다. 원 depth 결손을 평면으로 채우지 않았다.

## 현재 설계와 AGS-Mesh의 관계

현재 설계의 목표는 source별 적합도 값에서 두 depth의 감독 가중치를 정하는 것이다. 이번 단계는 그 앞부분의 비용 계산을 검사한다. 평면 가설은 비용을 위한 투영 기하이며 기존 학습 target을 교체하지 않았다.

AGS-Mesh DNC는 sensor depth에서 얻은 normal과 단안 예측 normal의 불일치로 depth 감독을 필터링하고, ANR는 예측 normal과 현재 GS normal의 불일치로 normal 감독을 필터링한다. 남긴 target 값은 원래 값을 유지한다. 따라서 학습 관점에서는 국소 0/1 감독 마스크에 가깝고, 자동으로 다른 source의 depth로 바꾸는 방법이 아니다. [AGS-Mesh §4.1–4.2](https://arxiv.org/html/2411.19271v2#S4.SS1)

본 점수의 normal은 같은 depth의 파생 방향으로, AGS의 별도 단안 예측 normal과 같은 독립 근거가 아니다. 높이만 다른 평행 평면은 normal 차이로 구분되지 않는 반면, 사진 비용은 그 위치 차이를 감지할 가능성이 있다. 그러나 이번 반례는 작은 사진 패치도 잘못된 후보를 지지할 수 있음을 보여준다. AGS와 현재 설계 어느 쪽이 더 낫다는 비교 실험은 수행하지 않았다.

## 다음 설계에 반영할 근거

1. raw-depth warp가 이미 국소 형상을 반영하므로 normal 평면을 무조건 대체 경로로 삼지 않는다. 평면 근사로 비용이 좋아지거나 나빠지는 위치를 함께 보존한다.
2. 비용 순위가 크기·시점에 따라 뒤집히는 위치를 높은 신뢰도로 취급하지 않는 규칙을 후보로 검토한다. 단일 크기 선택은 현재 근거로 확정하지 않는다.
3. 상대 우열과 절대 사진 적합도, 가시성·경계 혼합·관측 부족을 분리한 뒤 가중치 함수를 검증한다. 이번 std/지원 문턱은 이 문제들을 해결한 인증값이 아니다.
4. 실제 변경부·고정부의 참조 지원 사례를 별도 사전 명세로 늘려야 한다. 현재 8개 격자는 이전 진단의 기술 표본이며 일반적인 판별 정확도를 추정할 표본이 아니다.

## 산출물과 보존

기본 경로: `JBGS_ARTIFACT_ROOT/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1/main_v2/normal_photometry_v3_7`

- 계산: `attempt_20260911T112157Z_IE48tV/receipt.json` — PASS_INTERNAL_FIT_DIAGNOSTIC, 88.39초, 출력 1,708개 해시. 원본 8개 위치×이웃 32개×2쌍×3크기=192 비교 기록, 각 기록에 raw/plane 두 source 비용 4개.
- 참조 평가: `evaluation_20260911T112438Z_M1x7Qj/payload/receipt.json` — PASS_TECHNICAL_REFERENCE_EVALUATION. 별도 Docker에서 완료된 점수를 read-only로 읽고 원 UAS ID를 평가했다.
- 최종 브라우저: `browser_qa/attempt_20260911T113404Z_ba7CYd/receipt.json` — PASS_ACTUAL_NORMAL_PHOTOMETRY_BROWSER. 12,037검사, 192개 데스크톱 조합+3개 모바일=195상태, 1,669 HTTP 자료 해시 검증. root가 확대창·모바일 표·P2 33×33 패치를 육안으로 확인했다. source receipt의 게시 시점 browser_qa:PENDING은 보존하며 이 별도 receipt가 이후 검증의 근거다.
- 원 입력, parent receipt·기존 9×9 비용, 학습, 결과, 서비스 및 current.json 보존. 새로운 GS 실행이나 가중치 적용 없음.
- Referencing: 기존 UAS strict 지원은 DA3 유효성에 조건부다. regional visibility 및 header EPSG:32632/working EPSG:25832·datum/정합의 기존 불확실성이 남아 있으며, 위 숫자는 보정된 절대 정확도가 아닌 동일 참조에 대한 수치적 불일치다.
- 반복 실험·공간 가중 고유효과·박사 방법 신규성의 확정 근거로 사용하지 않는다.
