# C3 development Stage 3 기술 반환 보고서 v1

- task: `P2-C3-DEVELOPMENT-STAGE3-v1`
- handoff: `P2-W2C-C3-DEVELOPMENT-STAGE3-v1`
- 상태: `BLOCKED_PRE_PAYLOAD_AUTHORITY_VALIDATION`
- scientific_verdict: `null`

## 무엇을 하려 했는가

R4의 30,000-step C3 checkpoint를 저장된 Stage-2 group 그대로 surface로
변환하고, Roofer를 unique component마다 한 번 실행한 뒤 development 51개 건물에
연결하여 G0--G4, `PASS_usable`, 단계별 수량과 정성 비교판을 만드는 작업이었다.

## 실제로 어디서 멈췄는가

Experiment Host가 고정된 실행 래퍼를 한 번 호출했으나, 래퍼 내부의
`validate_two_host_handoff.py` 호출이 live artifact 검증에 필요한
`--artifact-root`를 전달하지 않았다. 검증기는 의도대로 fail-closed 했다.

이는 데이터·모델·Roofer의 실패가 아니다. checkpoint를 열기 전, development
score cell을 읽기 전, artifact namespace를 만들기 전에 발생한 실행 연결 결함이다.

## 계산 및 산출물 회계

- Stage 3 wrapper 호출: 1회
- checkpoint deserialization: 0회
- development score-cell read: 0회
- adapter: 0회
- Roofer: 0회
- 건물 결과 행: 0개
- 정성 PNG: 0개
- R1 15.7GB 입력, Images.zip, OPF.zip 재해시: 0회

따라서 이번 handoff는 과학적 시도나 실패 건물을 소비하지 않았으며, 목적 결과가
나왔다고 해석할 수 없다.

## 바로잡을 내용

Work Host에서 검증기가 이미 닫힌 이 receipt chain의 두 accepted artifact identity를
재사용하도록 recovery handoff를 묶고, 래퍼가 그 recovery accepted receipt를
검증하도록 경로만 교체한다. 이후 같은 checkpoint와 같은 51개 development 대상에
대해 원래 계획한 Stage 3를 실행한다.

그 실행의 필수 결과는 다음이다.

1. C3 component별 surface와 Roofer CityGML
2. 51개 건물 전부의 G0--G4 상태(평가 불가 사유 포함)
3. G0--G4 단계별 잔존 수와 최종 `PASS_usable` 수
4. C1/C2/C3 동일 건물 정량 비교
5. 대표 성공·경계·실패의 실제 모델 정성 비교판

사람의 과학적 판단 전까지 `scientific_verdict`는 `null`이다.
