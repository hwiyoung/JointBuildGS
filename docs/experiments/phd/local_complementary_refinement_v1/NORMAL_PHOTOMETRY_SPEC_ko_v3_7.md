# 고정 사례 depth·normal 관측 비용 진단 v3.7

- task_id: PHD-LOCAL-NORMAL-PHOTOMETRY-v3.7
- 사용자 범위: 기존 관측 비용에 normal을 적용하여 사례별 계산과 관측 지지를 검증한다.
- scientific_verdict: null
- 비용 계산 명세: configs/phd/local_complementary_refinement_v1/normal_photometry_v3_7.json
- 새 GT 없는 CPU 진단이며 기존 학습·결과·서비스를 보존한다. 감독 가중 함수와 새 학습은 이 단계에 포함되지 않는다.

## 비교를 고정하는 방법

v3.2 attempt_20260911T093732Z_WiqKix의 8개 위치와 이웃 사진을 모두 그대로 재사용한다. 부모 receipt SHA256을 config에 고정하고 입력·출력 해시를 검사한다. P1 이웃 2장, P2 이웃 6장이다. 새 관측 점수로 위치나 이웃을 골라내지 않는다.

각 source의 기존 65×65 sampled depth에서 중앙 9×9 유효 3D 점을 역투영한다. 최소 80% 지원 및 유효 중심이 있을 때 TLS/SVD로 국소 평면의 **방향만** 추정한다. normal은 같은 depth의 파생량이며 독립 측정이나 별도 normal 모델이 아니다. 기존 native normal 입력을 사용한 결과로도 부르지 않는다. 시야가 좁거나 깊이 경계가 있는 곳의 평면 적합 잔차와 중심 고정 잔차를 각각 기록한다.

중심 3D 점 X0는 원 depth를 그대로 유지한다. 각 ray r에서 plane depth는 (n·X0)/(n·r)이다. 원 depth가 결손인 ray는 그대로 결손이며 평면으로 채우지 않는다. 유효 normal이 없으면 plane 비용이 미정의이고 다른 source로 자동 선택하지 않는다.

9·17·33픽셀 패치의 raw-depth warp와 plane warp를 비교한다. normal 추정 창 9×9는 세 크기 모두 같다. 각 사진·패치·source pair에서 **두 source × 두 warp의 공통 유효 mask**를 동일하게 사용해 네 비용을 계산한다. 기존 9×9 raw pair 비용은 원래 mask에서 별도 재현해 부모 수치와 비교한다. 비교상대가 없어도 가능한 source 자체의 own-support 비용은 별도로 남긴다.

비용은 기존과 같은 grayscale ZNCC에서 E=(1-ZNCC)/2다. 별도 normal 불일치 항은 추가하지 않는다. 의미는 현재 사진 패턴의 일치도이며 표면 정확성 확률이 아니다.

## 읽기용 사전 수치와 한계

개발 진단의 읽기 보조값은 공통 표본 80% 이상, grayscale std .02 이상, 비용차 .02 초과, 계산 가능한 이웃 최소 2장, 같은 방향 비용차 비율 75%다. std .01/.02/.04의 지원 민감도도 저장한다. 이 값들은 이번 계산 이전에 고정한 **개발 진단용 수치**이며 source 정확도 문턱 또는 loss 가중 정책으로 채택한 값이 아니다. patch-size별 지지 방향과 총 비용을 같이 보고한다. 절대 비용→정확성의 보정은 아직 없다.

사진 내부 투영은 실제 가시성의 증거가 아니므로 visibility는 unknown이다. 8개 케이스는 개발 표본이며 많은 사진에서 동의해도 독립성이나 일반화를 보증하지 않는다. source 생성에 사용한 사진일 수 있어 internal fit이다. prior 반 픽셀 보간과 MVS native nearest의 중복·양자화는 기존 한계로 보존한다. MVS 9×9의 unique native query 수도 기록한다.

## 참조 평가의 별도 단계

비용 계산에는 UAS 참조를 읽지 않는다. 비용과 읽기 규칙을 고정한 출력 뒤에 별도 CPU 평가에서 원래 UAS 점 ID의 동일 집합으로 source 오차를 비교한다. 기존 8개 위치 중 7개는 65×65 문맥에도 지역 참조가 없고, P2_high_disagreement만 겹친다는 지원 감사가 있다. 지원 없는 위치를 정답/오답으로 채우지 않는다. 기존 reference의 datum/CRS 및 regional visibility 한계를 그대로 공개한다. 이 결과로 비용 수치나 케이스를 재선택하지 않는다.

## 완료 산출물

1. Docker 독립 기하·밝기 테스트와 실제 입력 homography/ZNCC/부모 raw 재현 검사.
2. source normal·평면 적합 잔차·결손·raw/plane 패치·공통 mask·이웃별 비용 및 크기별 민감도.
3. 계산 뒤 별도 참조 지원·source 오차 결과와 고정 비용 순위의 관계.
4. 기존 정적 서버의 새 불변 packet과 브라우저 검사. 기존 current.json은 갱신하지 않는다.

선행 근거는 [NeuRIS §3.2](https://arxiv.org/html/2206.13597v2#S3.SS2)의 depth·normal 평면 재투영/NCC다. 본 구현은 그 논문의 현재 SDF normal gate를 복제한 것이 아니며, 두 고정 source의 관측 비용을 같은 방법으로 검사하는 진단이다.
