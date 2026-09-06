# A v6 관측 곡선 유효성 수정

다중 영상쌍 v2의 원본 profile 감사에서 기하적으로 가능한 104,424 anchor–쌍 중
82,947개는 36pixel 이상의 고정 지지를 가졌으나 texture 기준을 통과한 것은 22,118개였다.
코드는 **13개 모든 후보 변위의 target patch가 전부 texture를 가져야** 전체 곡선을
남겼다. 따라서 틀린 변위 하나가 평평한 patch를 가리키면, 다른 변위의 실제 일치
관측까지 버렸다. 두 집단 모두 2쌍 이상 pixel 지지가 있는 anchor는 5,317개였지만 이
texture 처리 후 699개만 남았다. 이를 곧바로 P2의 물리적 관측 불가라고 할 수 없다.

별도 v3에서는 기준 patch의 texture 조건을 유지하고, 후보별 target contrast의
분모만 기존 최소 texture norm으로 제한한다. 완전히 평평한 target은 상관 0, 비용
0.5의 중립값이 되고 실제 textured 후보는 기존 ZNCC 값을 유지한다. 모든 target
변위가 평평하거나 기준 patch 자체가 평평하면 여전히 곡선 전체를 미상으로 둔다.
이것은 특정 좋은 후보를 고르기 위한 최소 비용 선택이 아니라 정의되지 않은 NCC
분모를 일관되게 처리하는 수정이다. 후보별 약한 contrast는 원래 NCC보다 상관을
약하게 만든다.

같은 표면 texture가 영상 간 관측된다는 국소 광도 대응 가정은 남는다. 중립 비용은
현재 기하 부적격의 확률이나 절대 오차 증거가 아니다. 가림·반사·공유 pose 편향을
완전히 보정하지 않았으므로 최종 구간은 계속 조건부 개발 관측으로만 사용한다.

원본 영상·두 11뷰 집단·모든 영상쌍·36pixel·texture threshold0.015·변위 격자·
ε0.15m·구간 slack0.03·그룹 일치 기준은 그대로다. 수정 전후 texture 이유를 실제
입력에 대해 동시에 세어 `texture_validity_audit.json`에 기록한다. v1/v2 실행과
원본 코드는 보존하며 B 최종 지표나 UAS를 사용하지 않았다.

평평한 틀린 후보/정답 후보/역상 후보가 함께 있을 때 각각 비용0.5/0/1이 되고 곡선이
유지되는 경우, 모든 후보가 평평한 경우, 기준 patch가 평평한 경우를 단위검산한다.

- [수정 NCC](../../../../src/phd/p2_ab_v6/a_texture_profile.py)
- [v3 설정](../../../../configs/phd/p2_ab_v6/a_observational_envelope_v3.json)
- [v3 실행](../../../../scripts/phd/p2_ab_v6/a_observational_envelope_texture_docker.sh)
