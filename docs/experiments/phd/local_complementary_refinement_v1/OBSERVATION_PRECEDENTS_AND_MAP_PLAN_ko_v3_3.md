# 관측 검정의 선행근거와 가중치 지도 전 단계 v3.3

- 작성일: 2026-09-11
- task_id: PHD-LOCAL-SOURCE-WEIGHT-DESIGN-v3
- 상태: LITERATURE_AND_NEXT_DELIVERABLE_SPECIFICATION
- scientific_verdict: null
- 범위: 원문 재확인과 기존 G0–G6 설계의 다음 산출물 구체화. 새 점수/가중치 생성·학습 실행 명세가 아니며 기존 source/결과/서비스를 변경하지 않는다.

후속 [v3.4 normal 활용·AGS 대응](NORMAL_ROLE_AND_AGS_MAPPING_ko_v3_4.md)은 AGS의 filtered depth/normal과 별도 영상 depth/normal의 차이 및 normal을 관측 검사에 추가할 비교 후보를 기록한다.

## 1. 직접 근거와 인접 근거

| 선행연구 | 확인한 원문 동작 | 지금 방식과의 관계·차이 |
|---|---|---|
| Schönberger et al., Pixelwise View Selection for Unstructured Multi-View Stereo, ECCV 2016 | 국소 패치의 photo 비용과 기하 일관성, 픽셀별 view 선택을 사용해 depth/normal을 추정한다. 가림·시차·입사각·해상도를 고려한다. | 패치·후보 depth 비교·유효 view 선정의 직접 근거다. 현재 진단은 고정된 ALS/DA3/MVS 후보를 읽어 비교하며, MVS의 depth 탐색/기하 일관성/가림 추론 전체를 구현한 것은 아니다. |
| Wang et al., NeuRIS, ECCV 2022, §3.2 식 4–6 및 §3.3 식 9 | 현재 재구성에서 얻은 depth/normal의 국소 평면으로 패치를 warp하고 NCC로 normal prior 감독의 사용 여부를 정한다. 기각한 prior는 후속 최적화에서도 사용하지 않는다. | 사진 일관성→국소 감독 선택의 직접 근거다. 현재 진단은 GS가 만든 표면 대신 고정된 두 source의 depth를 각각 ray별로 투영한다. 계획된 정책은 두 depth 감독의 배분과 보류를 다루며 normal prior gate와 구분된다. |
| Ren et al., AGS-Mesh, 검토판 arXiv 2411.19271v2, §4.1–4.3 | DNC: 센서 depth-derived normal과 단안 normal의 불일치로 depth 감독을 필터링. ANR: 현재 렌더 기하에서 얻은 normal과 단안 normal의 불일치로 normal 감독을 필터링. | 불량 기하 감독을 국소적으로 완화하는 인접 근거다. DNC/ANR를 patch NCC 기반의 두 depth 후보 판정이라고 설명하면 틀리다. 과거 ALS/current image 후보를 같은 사진에서 직접 비교하는 현 설계와 검사 대상이 다르다. |

원문: [COLMAP 저자 논문](https://demuc.de/papers/schoenberger2016mvs.pdf), [저자 포스터](https://www.microsoft.com/en-us/research/uploads/prod/2019/09/P-2A-41.pdf), [NeuRIS §3.2](https://arxiv.org/html/2206.13597v2#S3.SS2), [AGS-Mesh §4](https://arxiv.org/html/2411.19271v2#S4).

이번 COLMAP PDF 직접 open은 도구의 Internal Error로 실패했으나 같은 저자 PDF의 검색 색인과 Microsoft의 원 포스터를 확인했다. NeuRIS와 AGS-Mesh는 버전이 명시된 원문 HTML을 확인했다. AGS-Mesh 출판본과 arXiv v2의 byte 동일성은 주장하지 않는다.

이 근거들은 국소 관측 검사와 선택적 감독의 타당한 출발점을 제공한다. 현재 항공 영상/과거 ALS에서 점수가 정답 source를 판별한다거나 9×9·0.5m/2m·특정 가중식이 유효하다는 증거는 아니다.

## 2. 현재의 구별점과 아직 입증하지 않은 기여

- 문제 차별성: 과거 ALS의 재사용 가능한 구조와 현재 영상의 갱신·결손·오류를 함께 다룬다. 실내 장면을 항공으로 바꿨다는 사실만으로 방법 신규성을 주장하지 않는다.
- 원인 설명: depth 자체의 오류, 카메라/가림 오류, 잘못된 source 선택, 감독 총강도 변화, GS 최적화/추출 영향을 분리한다. 특정 결과를 DA3 단독 원인으로 단정하지 않는다.
- 방법 후보: 고정된 두 source를 동일 관측에서 대칭 비교하고, 배분과 총강도를 구분하며, 관측 부족이면 증폭 없는 prior fallback을 적용한다. 각각이 선행 아이디어와 겹치므로 조합의 유용성·신규성은 미확인이다. 고정 source라도 MVS 생성에 같은 사진이 쓰였으면 독립 관측이 아니다.
- 검증 기여 후보: 같은 위치에서 성공 유지·새 수정·새 손상·미수정과 보류를 함께 측정하고, 단순 prior 약화 및 단순 photo gate와 비교한다. 첫 LC 18개만으로 공간 배분 고유 효과나 작은 차이의 재현성을 확정하지 않는다.

## 3. 패치와 전체 사진 피복은 별개의 선택이다

패치는 한 위치의 주변 밝기 패턴을 비교하는 단위다. 한 픽셀의 색만으로는 대응이 모호할 수 있고, 사진 전체를 하나의 비용으로 집계하면 위치별 차이가 섞인다. 예를 들어 큰 변하지 않은 면의 양호한 정합이 작은 변화 부위의 오류를 가릴 수 있다. 이는 국소 목적함수에 관한 설명이며 '전체 사진을 재투영할 수 없다'는 뜻이 아니다.

전체 사진의 각 위치에 작은 창을 옮겨 비용을 따로 계산하면 전체 비용 지도를 만들 수 있다. 패치 기반 방법과 전체 범위 검사는 양립한다. 지금 8개 위치만 계산한 것은 기술 진단 범위였기 때문이며 최종 방법의 피복 설계가 아니다. 현재 64픽셀 간격은 사례 선정용이고, 9×9는 임시 비교 창이다. 65×65는 표시 문맥이다. 어느 값도 최적 크기로 검증하지 않았다.

## 4. 다음 산출물: 관측·판정 지도를 거쳐 후보 가중치 지도

기존 [v3 G0–G6](SOURCE_WEIGHT_POLICY_DESIGN_ko_v3.md)의 순서를 유지한다. 최종적으로 사진별 전체 위치를 다루되 첫 개발 범위는 기존 계획의 P1/P2·지역별 최대 6 reference·stride 8 표본 후보에서 시작한다. 이 후보를 현재 64 간격 진단과 혼동하지 않는다. 카메라 명단·창 크기 후보·계산 해상도·stride·타일 경계·이웃 선정·메모리 한계는 별도 실행 config로 먼저 결박해야 한다.

1. **G1 관측 지도:** 각 source의 비용, 동일 view의 대응 비용차, depth 유효성, 사진 안 지원, 실제 가시성의 근거/unknown, 대비·무늬 모호성, 유효 이웃 수를 함께 저장한다. 카메라가 가까운 것과 패치가 관측 가능한 것을 구분한다. 범위 밖과 실제 mismatch를 같은 상태로 처리하지 않는다.
2. **G1 민감도와 recipe 고정:** 소수의 사전 명시 패치 크기·시점 묶음·pose 교란에서 판단 안정성과 지원량을 비교한다. GT 없이 관측 판정 규칙을 먼저 고정한다. 9×9를 확대된 영상으로 보여주는 것은 크기 민감도 검사가 아니다.
3. **G2 후보 선택 지도 평가:** IMAGE_SUPPORTED / PRIOR_SUPPORTED / OBSERVED_AGREEMENT / UNRESOLVED / SOURCE_MISSING을 보존한다. 원 source가 어느 쪽이 더 정확한지 별도 평가 reference로 검사하고, 선택 오류와 보류 피복을 함께 보고한다. GT는 점수·가중치 생성에 투입하지 않는다. GT를 본 뒤 수정하면 별도 개발 revision으로 남긴다.
4. **G3 후보 가중치 지도:** 검증할 정책의 q·총계수 s·실제 prior/image 계수 kP/kI를 별도로 만든다. 미계산 위치를 안전성 확인 없이 채우거나 희소 표본을 무조건 보간하지 않는다. 희소 개발 진단과 사진 전체의 학습 지도를 구분한다. 분모·결손·동일 depth·zero-lambda·gradient 검산을 수행한다.
5. **G4 이후 실제 GS 연결:** 동일 Anchor/optimizer/RNG/camera/controller/보호에서 weight→gradient→update를 추적한 뒤 제한된 최적화를 비교한다. 좋은 색상의 가중치 지도가 최종 표면 개선을 입증하지 않는다.

즉 다음 큰 산출물은 가중치 지도지만, 바로 최저 비용을 가중치로 변환하여 학습하는 것이 다음 동작은 아니다. 먼저 사진 범위에 걸친 관측 지도와 후보 판정의 지원 범위를 보여줘야 한다. 판단 근거가 부족하면 지도에 그 상태가 남아야 하며 전체를 억지로 image/prior 승자로 채우지 않는다.

이번 문서 작성에서 새 계산 또는 학습을 시작하지 않았다. 원래 실행 중인 작업과 게시된 진단 packet은 보존한다.
