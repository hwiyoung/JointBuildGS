# 자료 읽기

작업: PHD-MAIN-PROCFIG-v1 / 덧붙임1. scientific_verdict: null. 학습 반복 0.

`PH`는 저장소 루트가 아니라 기존 외부 `JointBuildGS-artifacts/phase-payloads/phd` 별칭이다.
아래 숫자·모든 파일은 같은 고정 건물 범위이다. 입력은 원자료이고 가우시안 상태는 0/7000/15000/30000 네 개다.
표의 빈 수치는 해당 없음/빈 모집단이며 0으로 채우지 않았다. 구간 끝은 목표 법선 구간 양 끝 중 가까운 끝에서 0.001m 이내이다.

## gaussians/<회>.npz

|열|뜻|
|---|---|
|xyz|N×3, 지역 XYZ m, float32. EPSG:25832 좌표 = xyz + [690953,5336071,604]|
|normal|N×3 단위 원반 법선. 회전의 세 번째 축|
|rotation|N×4 정규화 쿼터니언 w,x,y,z; 첫 두 축이 원반 접선|
|scale|N×2 활성화 접선 축 반지름 m. 긴/짧은 축은 max/min. 표시 배율은 별도 적용|
|opacity|활성화 sigmoid α, float32|
|origin|불변 출신: 0 SfM 배경, 1 패치 씨앗|
|target_tag|현재 상태: 0 배경, 1 묶임, 2 풀림|
|judgment|현재 묶인 패치 판정: 0 일치, 2 보정, 1 보존, 4 결측. -1 묶이지 않음|
|current_patch|현재 묶인 원래 FINALTRAIN targets 행 번호. -1 묶이지 않음|
|target_index|r23 valid-patch 목록 내부 인덱스. 풀린 행은 과거 값이 남을 수 있어 current_patch로 해석|
|initial_patch|불변 init_id 씨앗의 targets 행 번호. -1 배경|
|init_id|불변 처음 씨앗 행 번호. clone/split 자손에 유지되는 int32. 가우시안 고유 번호가 아님|
|group33|고정 초기 계보 무리: 0 기타, 1 틀린 판정, 2 보정 비교. 처음 범위 밖 씨앗은 0|
|wall|abs(normal dot 고정 gravity up)<0.5|
|full_gaussian_index|해당 저장 상태 전체 배열의 행 번호|
|target_xyz,target_sigma|묶였을 때 현재 목표 XYZ와 σ. 미묶임은 NaN|
|normal_offset|현재 중심−목표를 목표 법선에 투영한 m. 부호 있음|
|target_released_at|풀림 반복 번호, -1 미발생|

0회는 r23의 CUDA 전용 로더 대신 저장 seeds와 불변 초기 scale/normal을 사용했다. 새 위치·새 씨앗·새 제외 규칙을 만들지 않았다.
패치의 quaternion은 seeds 원본이다. 배경의 초기 두 축 scale이 정확히 같음을 확인하고 기존 axes/quat 함수로 같은 원반을 구성했다.
따라서 초기 원반의 위치·형태·법선은 재현하지만 배경 원래 quaternion 바이트나 재개 가능한 전체 훈련 상태를 주장하지 않는다.

## 그림과 단면

색은 일치 #7FA7D9, 보정 #D85A30, 보존 #1D9E75, 결측 #E8B931, 배경/풀림 #B4B2A9, 틀린 판정 계보 #C2378A.
a=0.6배 모두 불투명, b=1배 모두 불투명, c=0.6배 실제 α, d=0.6배 α≥0.1만 불투명(자주 계보에도 적용). 덧붙임1의 d 정의에 맞춘 표시 정정 잠금 display_fix1은 수치 계산과 읽는 기준을 변경하지 않는다.
같은 카메라 번호의 모든 상태·표시판은 동일 정사 투영. 광원은 고정, 원반은 GS 영상 렌더가 아니다.
화소 중심마다 원반 평면 깊이를 계산하고 깊이 순서로 합성한다. 건물·확대 범위 경계에서도 화소 XYZ를 검사해 자른다.
위 지도 NPZ counts[y,x,group]는 0.25m 칸별 지붕 중심 수다. 겹친 칸은 자주→보정→기타 순으로 색만 우선한다. 수치는 각 채널을 모두 보존한다.
단면 JSON states는 배열 열 형식이다. 순서는 각 시점 배열 순서이며 s,z,α,출신,현재판정,계보표시,목표,σ를 보존한다. null은 미묶임 등 실제 미정값이다.
단면 확인 그림은 위에서 0,7000,15000,30000회. 네 패널의 s/Z 범위가 같다. 위치 확인용 가우시안 표식은 불투명이며 실제 α는 JSON에 있다.
카메라 순위는 건물 범위 경우1 참값의 기존 30,000회 결과 메시 가림 검사로 정했다. 이 참값 사용은 발주문 4.1의 표시 시점 선택에 한정된다.

## 계보와 검증

3.3 선택은 기존 참값 행 소유권 row_owner → core.source_index를 그대로 사용했다. patch_id 동일성을 확인했다.
다수는 유일 최빈 경우1이며 동률을 임의로 풀지 않는다. 높이 비교는 원래 prior 위치와 배정 참값 Z 중앙값이다.
처음 건물 범위의 씨앗 무리를 고정하고 이후 같은 범위 안 자손을 집계했다. 범위 밖 자손도 표의 별도 열에 있다.
실제 출신 NPZ attribution_30000은 기존 FINALTRAIN PLY/렌더를 원래 α×T 계보 도구로 재현한 것이다. 표의 분모는 선택 패치에 소유된 건물 범위 참값 행이다.
snapshot/PLY 저장 뒤 한 번 더 경계 투영하는 완전 체크포인트의 단계 차이는 saved_phase_audit.json에 별도로 기록했다. 그림·정량은 완전 체크포인트, 카메라 순위·실제 출신은 기존 최종 결과 계보를 쓴다.
입력 해시 input_lock.json, 개별 확인표 section2_inventory, 독립 검사 verification.json, 오류·보완 issues.md, 설정 잠금 procfig_v1.lock.json을 함께 읽는다.
재실행은 scripts/run.sh cpu freeze.py → torch checkpoints.py → cpu measure.py → cpu schedules.py → cpu render.py → cpu sections.py → gpu attribution.py → cpu attribution_tables.py → cpu phase_audit.py → cpu verify.py → cpu publish.py 순서다.
기존 잠금이 있으면 freeze.py는 재실행을 거부한다. 위 명령은 원래 저장소 scripts/phd/main_procfig_v1/ 위치에서 실행하며 번들 scripts/는 같은 코드의 보관본이다.
