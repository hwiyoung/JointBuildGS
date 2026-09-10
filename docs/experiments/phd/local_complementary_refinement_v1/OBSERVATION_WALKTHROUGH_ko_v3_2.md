# 관측 점수 단계별 열람 v3.2 — 입력 전체 사용과 평가 역할 재검토

- 작성일: 2026-09-11
- task_id: PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3
- 상태: INTERNAL_FIT_DIAGNOSTIC_COMPLETE / BROWSER_QA_PASS
- scientific_verdict: null
- 이번 사용자의 요청: 사진 제외가 MVS에 미치는 영향과 판정/평가 사진의 필요성을 재검토하고, 실제 관측 점수 계산을 단계별로 정성적으로 확인한다.

후속 [v3.2.2 읽기 안내](WALKTHROUGH_READING_ko_v3_2_2.md)는 선정 기준·흰색 mask·P2 표본 3/6장·투영 표시 없음의 이유를 설명한다. 원 계산은 그대로 유지했고, 설명을 추가한 새 packet을 별도로 게시했다.

## 1. v3.1의 생성/판정 분리를 기본 운용의 필수 조건으로 두지 않는다

사진을 제외하면 MVS의 시차·중복도·가시 표면·결손·정확도가 바뀔 수 있다. 제외 구성이 현재 결과에 얼마나 영향을 주는지 측정하지 않은 상태에서 괜찮다고 가정할 수 없다. 이전 v3.1의 G/V 분리를 모든 MVS 생성의 필수 조건으로 제안한 것은 과도했다.

이번 주경로는 기존 재구성용 입력 사진과 기존 MVS/DA3 bytes를 그대로 활용한다. 기존 최종 평가 사진을 재구성 입력에 새로 넣는다는 뜻은 아니다. 같은 사진에서 후보 적합도를 계산하고 prior와 비교하는 운용 방법은 가능하다. 다만 그 점수는 INTERNAL_FIT_DIAGNOSTIC이며 독립적인 기하 정확성 증거가 아니다.

G/V 분리는 이후 필요할 때 실시할 생성 미사용 view 보조 검사로 둔다. 실시한다면 입력 구성 자체가 달라졌음을 명시하고, 방향/중복도/시차를 유지하도록 사전 구성한 여러 분할에서 깊이·피복·선택 안정성을 비교한다. 적은 사진 결과를 전체 사진 결과와 같은 입력 조건으로 부르지 않는다. 현재 기존 입력을 다시 만들거나 새 분할 실험을 시작하지 않았다.

## 2. 판정용 사진 외에 최종 평가 사진이 필요한 경우

판정용 사진으로 두 후보의 적합도를 비교해 선택하는 것이 방법의 동작이다. 그 동일 점수를 보여주는 것은 선택 이유의 설명이다.

| 목적 | 필요한 별도 검증 |
|---|---|
| 사진 적합도로 source 선택하기 | 같은 사진 기반 방법도 가능; 점수·지원·모호성의 의미를 명시 |
| 선택된 표면이 실제로 더 정확한가 | 별도 기하 reference로 평가; 이 목적만이라면 추가 사진 세트가 필수는 아님 |
| 선택/학습에 쓰지 않은 시점에서도 렌더가 좋은가 | 방법에 사용하지 않은 평가 사진이 필요 |
| MVS가 생성에 쓰지 않은 사진도 설명하는가 | G/V 분리 보조 검사; 최종 평가와 다른 질문 |

기존 held-out 평가 사진은 보존한다. 판정에 사용한 사진을 동시에 미사용 시점의 평가 사진이라고 주장하지 않는다. 사진을 사용해 선택한 뒤 동일 사진 비용이 낮아졌다는 사실을 새로운 성능 증거처럼 계산하지 않는다. GT는 이번 점수 계산에 사용하지 않고, 이후 정확성 평가에만 사용한다.

이 문서는 v3.1의 '새 실행 명세는 항상 G/V 분리' 요구를 위 목적별 구분으로 보완한다. 이전 문서와 결과는 역사로 보존한다.

## 3. 실제 단계별 화면

[관측 점수 따라보기](http://localhost:8905/packets/packet_photometry_v3_2_20260911T094838_338420Z/index.html)

1. **위치:** 원사진의 고정 패치 위치, prior/DA3/MVS의 중심 camera-Z.
2. **재투영:** 같은 이웃 사진에서 두 후보가 예측한 위치를 다각형으로 표시.
3. **패치:** 실제 점수의9×9 패치와 위치를 이해하는65×65 문맥을 분리 표시.
4. **유효 표본:** 각 source의 수치적 유효/투영 mask와 비교쌍의 공통 mask.
5. **밝기 정규화:** 공통 표본의 평균·표준편차로 정규화한 패치, 정규화 잔차.
6. **점수:** 모든 선정 이웃의 ZNCC·비용·공통 픽셀 수·미정의 상태를 함께 표시.

Prior↔DA3와 Prior↔MVS를 전환할 수 있다. 서로 다른 비교쌍의 공통 mask는 다를 수 있으므로 두 쌍의 source 비용을 직접 순위화하지 않는다. 각 쌍의 중앙값은 두 비용이 모두 정의된 동일 이웃 집합에서 계산한다. 작은 비용은 해당 사진 패턴의 적합도이며 실제 source의 정답 판정이 아니다.

그림을 누르면 확대된다. 모든 사례와 이웃을 유지하며, 첫 화면은 사용 편의를 위한 P2 낮은 불일치 위치와 공통 표본이 있는 첫 이웃이다. 이는 계산/평가 표본 선정에 영향을 주지 않는다.

실제 점수 식은 다음과 같다. 비교쌍의 공통 유효 픽셀 집합을 Ω, 원 패치 밝기를 x, 후보 depth로 가져온 이웃 패치 밝기를 y라고 한다. 밝기는 RGB를 .299R+.587G+.114B로 바꾼 [0,1] 값이다.

    zx = (x − meanΩ(x)) / stdΩ(x)
    zy = (y − meanΩ(y)) / stdΩ(y)
    ZNCC = meanΩ(zx · zy)
    cost = (1 − ZNCC) / 2

ZNCC가 클수록, cost가 작을수록 해당 패치의 밝기 패턴이 비슷하다. 두 후보 모두 같은 Ω와 같은 원사진을 사용한다. 이 비용에는 가림 판정이나 기하 신뢰도가 아직 들어 있지 않다. 공통 표본 부족과 수치적으로 상수인 패치는 점수를 미정의로 남긴다. 약한 무늬를 신뢰할 수 있는지 판단하는 문턱은 아직 정하지 않았다.

## 4. 실제 입력과 계산 범위

- 기준 사진: P1 DJI_20241217084553_0100_D.JPG, P2 DJI_20241217084505_0076_D.JPG. 기존 개발 문맥의 사진 선택이며 새 독립 표본이 아니다.
- 각 사진에서4개 격자 사례: prior–DA3 낮은 불일치, 높은 불일치, prior 결손, MVS 결손.
- Patch 중심은 RGB/점수를 읽기 전에 입력 depth/mask와 row-major 격자로 정했다. RGB를 mount하지 않는 plan 단계의 manifest를 계산 단계에서 다시 검증했다. .5/2m는 기존 LC 문맥을 나누는 표시용 strata이며 신뢰도 문턱이 아니다.
- MVS 결손 사례는 기존 선택과 독립적으로 추가한 첫 격자다. MVS가 일부라도 비고 prior/DA3가 모두 유효한 패치를 선택했다.
- 실제 이웃은 P1 2장, P2 6장이다. train 카메라 중심 거리와 광축 조건만으로 정했으며 사진 적합도·앞가림·공통 투영 지원으로 최적 이웃을 고른 결과가 아니다.
- MVS 생성의 실제 최종 이웃 membership은 복구되지 않았다. DA3의 기준 사진별8장 batch는 확인했다. 생성과 분리된 관측이라고 주장하지 않는다.
- 원사진/DA3/기존 prior는1400×1013, MVS는1024×741이다.
- 기존 RGB/GS·DA3의 정수 ray를 기준으로 prior는 u−.5,v−.5에서4개 depth 모두 유효할 때 bilinear 조회했다. MVS는 native K로 변환 후 nearest 조회하여 구멍을 유지했다. 이는 별도 진단 조회이며 원 학습 target을 변경하지 않았다.
- Prior 경계의 보간 혼합, MVS 양자화와 과거 producer binary/반 픽셀 민감도 미확인은 한계로 기록했다.

사진 밖인지/숫자가 유효한지 검사한 것과 실제 같은 표면의 가시성은 다르다. 이번 visibility는 unknown이다. 특히 P1에서 기준 잔디·수목 부위가 이웃의 지붕으로 투영되는 사례가 있다. 가림, 후보 기하 오류, 좌표/pose 문제를 구분해야 하며 그 점수로 source 우선권을 부여하지 않는다.

## 5. 계산·게시 검증

최종 계산 attempt:

    JBGS_ARTIFACT_ROOT/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1/main_v2/photometric_walkthrough_v3_2/attempt_20260911T093732Z_WiqKix

- 계산 receipt: PASS_INTERNAL_FIT_DIAGNOSTIC.
- 실제8개 위치, 점수128행, 독립 수치 검사195개 PASS.
- 실제 투영의 별도 행렬 계산 대비 최대 절대 오차2.27e−12px, 독립 ZNCC 오차5.55e−16, 중심 bilinear RGB 오차0.
- 이 숫자는 구현 수치의 일치이며 실제 기하·pose 정확도가 아니다.
- 출력909파일 해시와 입력 전후 해시 일치.
- Docker CPU 계산65.38초, 최대 RSS235,786,240bytes. 새 depth 생성·학습·GPU·GT 사용 없음.
- Receipt SHA256: 9a45f274843a0e0525b4e57efa1d3501b13e8df3bf47315011dbe27ad69cd5e0.
- P1 MVS 결손 사례는 prior–DA3 공통81개, prior–MVS66개. P2 MVS 결손 사례의 투영 가능한 세 이웃은 각각81개와0개다. MVS 결손 때문에 prior–DA3 비교가 사라지지 않음을 확인했다.
- 새 불변 packet을 기존 정적 서버에 추가했다. 기존 current.json과 자동 갱신 작업을 변경하지 않았다. Browser QA는 별도 receipt로 기록한다.
- 최종 브라우저 검사: `browser_qa/attempt_20260911T095151Z_X0a8kG/receipt.json`, 8개 사례·500개 실제 화면 상태·4,411개 검사·801개 HTTP 자료 해시 일치. 모바일 점수표의 수평 스크롤과 작은 패치 확대를 육안으로도 확인했다. Receipt SHA256: 62f9fd690835c5e4166915239f4171d22e5638bf262d49400cbf4746eca2c885.
- 게시 receipt의 `browser_qa: PENDING`은 게시 시점의 상태로 보존한다. 이후 완료 상태의 근거는 위 별도 브라우저 receipt와 `manual_visual_review.json`이다. 기술 검증 완료를 source 선택 정책이나 과학적 성능 검증으로 해석하지 않는다.

추가 카메라 감사는 별도 `camera_audit/attempt_20260911T095004Z_Wgh5fA`에 봉인했다. P1/P2 train 155개 카메라의 K/R/t를 원 COLMAP 자료와 비교한 최대 절대 차이는 0이다. 실제 선택된 10개 사진에서 순서대로 200개씩 취한 SfM 대응점 2,000개의 재투영 잔차는 사진별 중앙값 0.116–0.237px였다. 이는 카메라 읽기/투영 규약의 검증이며, 독립 GT 평가나 후보 depth 정확도 검증은 아니다. 회전 전치나 local/global 좌표 혼동의 증거는 없었지만, 앞서 보인 P1 투영의 가림과 depth 오류는 아직 구분되지 않았다. 입력·코드·명령·표본 CSV·출력 해시는 별도 receipt에 보존했다.

## 6. 재현과 보존

- [계산 코드](../../../../scripts/phd/local_complementary_refinement_v1/photometric_walkthrough_v3_2.py)
- [계산 실행기](../../../../scripts/phd/local_complementary_refinement_v1/run_photometric_walkthrough_v3_2.sh)
- [계산 설정](../../../../configs/phd/local_complementary_refinement_v1/photometric_walkthrough_v3_2.json)
- [게시 실행기](../../../../scripts/phd/local_complementary_refinement_v1/build_photometric_walkthrough_v3_2.sh)
- [카메라 감사 실행기](../../../../scripts/phd/local_complementary_refinement_v1/run_walkthrough_camera_audit_v3_2.sh)
- [브라우저 검사 실행기](../../../../scripts/phd/local_complementary_refinement_v1/browser_photometric_walkthrough_v3_2.sh)
- [화면 구현](../../../../src/apps/lc_photometry_v3_2/index.html)
- [예외 기록](ISSUES_PHOTOMETRIC_WALKTHROUGH_ko_v3_2.md)

실제 값·mask·투영좌표·world/camera 좌표·sampling weights·정규화 배열은 각 이웃의 numeric_arrays.npz와 case.json에 보존했다. 점수와 가중치의 혼동을 피하기 위해 이번 화면은 winner/q를 계산하지 않는다. v3의 신뢰도 gate나 Gaussian 전달 검증을 완료한 결과로 취급하지 않는다.
