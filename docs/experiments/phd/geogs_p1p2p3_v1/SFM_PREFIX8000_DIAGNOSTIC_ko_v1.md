# 동일8k 상태의 조건부 보조 진단

2026-09-10 · `scientific_verdict: null`

P1/P2의 선택된 새 학습이 진행 중이고 새22k/30k 품질을 아직 보지 않은 시점에 보조 분석 규칙을 고정한다. [설정](../../../../configs/phd/geogs_p1p2p3_v1/sfm_prefix8000_diagnostic_v1.json)이 실행 조건과 경로를 소유한다. 원30k 학습과22k/30k 평가 계획은 유지한다.

선택된 P1 v2·P2 v2·P3 v3 작업이 닫힌 뒤, 학습 또는 추출 실패 때문에 원 계획의 결과가 하나라도 제공되지 못하면 **세 지역 모두 동일8,000회 상태**를 별도 진단한다. 지역별로 마지막으로 남은 상태나 품질이 좋은 상태를 고르지 않는다. 8k가 없으면 미제공이며, 기존 결과나 다른 iteration으로 대신하지 않는다.

주 비교는 기존 ALS 초기화·Anchor8000과 SfM 초기화·refinement8000이다. 원 final30000은 처리량이 다른 추가 맥락으로 표시한다. 같은8k라도 초기화·감독·보호 대상·일정이 다르므로 Anchor 하나의 인과적 효과로 해석하지 않는다. ALS 감독과 보호가 남아 있으므로 image-only도 아니다.

원 train receipt가 실패였다는 사실은 보존한다. 별도 validator가 고정 입력·source·명령·초기/첫 step 제어·8k trace·완전 checkpoint와PLY의 SHA·점 수·유한값·optimizer 이후 저장 계보를 확인한 뒤에만 prefix 검증 receipt를 만든다. 이것은 전체30k 학습 PASS가 아니다. 실제 공식 렌더·512 TSDF raw/post가 성공해야 표면 품질을 평가한다.

평가는 원 UAS·범위·표본화·임계값·사진과 동일하며, 기존 Anchor RGB는 `anchor_512` 단계 결과를 그대로 재사용한다. 뷰어와 표에는 ‘8k 중간 진단’과 ‘전체 실행 상태’를 함께 표시한다. UAS나 렌더 점수로 checkpoint 또는 설정을 선택하지 않는다. GPU가 실제 해제된 뒤 추출하며, 추출 실패도 별도로 보존한다.

새 생산물은 task의 `completed_prefix8000_v1/`, 평가는 `evaluation/no_anchor_sfm_prefix8000_v1/`에 분리한다. 이 문서는 실행 결과가 아니며, 보조 결과가 생성되어도22k/30k 완료나 최종 수렴을 대신하지 않는다.
