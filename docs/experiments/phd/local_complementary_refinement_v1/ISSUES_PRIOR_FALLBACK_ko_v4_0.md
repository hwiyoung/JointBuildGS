# v4.0 보완 이슈

- scientific_verdict: null
- 실행 예외/검사 실패: 관측 r1/r2 및 가중 프로브 모두 없음.
- 후속 receipt hash 재검사 첫 호출은 Docker 작업 디렉터리 누락으로 상대 config 경로를 찾지 못해 `FileNotFoundError`가 발생했다. `-w /repo`를 명시해 다시 실행했고 현재 코드/config 및 두 최종 receipt의 모든 output hash 일치를 확인했다. 실험 데이터나 비용을 바꾸지 않은 검증 호출 오류다.

| ID | 상태 | 내용과 닫기 위한 근거 |
|---|---|---|
| PF40-01 | OPEN | 비용곡선에서 실제 q를 만드는 함수와 수치 보정 미완료. 합성 q를 실제 지도라고 부르지 않는다. |
| PF40-02 | OPEN | 단일 최저점은 정확성 보장이 아님. 가림 모사에서 10m 대신 약 8.35m 최소. 비용 절대 적합도/시점/정합 검사 필요. |
| PF40-03 | OPEN | 제한된 sweep이 반복무늬 대안을 숨김. 범위/격자 민감도를 보존해야 함. |
| PF40-04 | OPEN | q/s 상한 후보에서 중간 q의 감독이 약해짐. ratio100/q=.9에서 image 9%, 동일 target/q=.5에서 총강도 1.98%. 본실험 채택 전 강도 정책 별도 검증. |
| PF40-05 | OPEN | P2 실제 패치 크기별 우열 역전 및 유효 image 감독 제거는 새 실제 관측으로 재검증하지 않음. |
| PF40-06 | OPEN | 현재 source별 normal은 depth 파생량; 독립 정확성 증거로 중복 계상 금지. |
| PF40-07 | OPEN | Prior 없는 곳의 image admission은 별도 검증 필요. q를 단독 source 신뢰도로 대용하지 않음. |
| PF40-08 | OPEN | dense weight map 및 GS gradient/optimizer 검증 미실행. 컴포넌트 PASS가 최종 기하 개선을 뜻하지 않음. |

사용자가 승인한 모호성→Prior 기본 사용은 이슈 PF40-01의 해결을 기다리며 뒤집는 원칙이 아니다. 실제 모호성의 판별과 비모호한 image 수정의 충분성을 함께 검증하는 것이 남은 작업이다.
