# P2 C1/C2 대표 3동 정성·정량 비교판 v2 기술 보고서

## 결과

- task: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
- technical state: `BLOCKED_BEFORE_FIRST_PANEL`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

이번 v2 시도는 C1/C2 방법 결과나 Roofer 실패가 아니라, 비교판 renderer를 띄운
Docker 컨테이너에 projection datum config의 절대경로 `/configs` mount가 없어서 첫
raw-image camera projection 전에 중단됐다. C1/C2 봉인 결과와 정량 source에는 변경이
없고, 새 정량값도 계산하지 않았다.

## 실행 전 통과 항목

- Git: clean `main`, `HEAD == origin/main == 3fa337fd707e3b069182688c8dff481fef93b993`
  에서 activation 시작
- image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- Docker focused renderer tests: `14/14 PASS`
- agent-instruction validator: `PASS`
- agent-instruction sync tests: `13/13 PASS`
- exact C1/C2 quantitative source rows: `6`
- unique sealed operation units: `2`
- C1/C2 terminal status: 모두 `COMPLETED_REUSED_EXACT`
- renderer `reference_for()` 기반 principal-section visible count:
  - `DEBY_LOD2_4907177`: `15`
  - `DEBY_LOD2_4906975`: `332`
  - `DEBY_LOD2_108580336`: `677`
- 실행 직전 v2 final/partial namespace: 모두 없음

## 단일 renderer 시도

accepted commit `1c398211a0862456ed2935676ea15d04fafa48fa` 뒤 renderer를 정확히
한 번 호출했다. 호출은 output partial directory를 만든 다음 첫 panel을 쓰기 전에 아래
경로에서 중단됐다.

```text
FileNotFoundError: [Errno 2] No such file or directory:
'/configs/input_and_alignment/projection_datum.json'
```

repository는 `/workspace`에 정상 mount됐지만, `src/geospatial/projection_datum.py`의
기본 절대 config root인 `/configs`가 별도로 mount되지 않았다. 따라서 이 문제는
reference JSONL schema, principal-section anchor, C1/C2 geometry 또는 Roofer output의
문제가 아니다.

## namespace 보존

- final:
  `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_comparison_matrix_sample_v2/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
  — 없음
- partial:
  `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_comparison_matrix_sample_v2/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v2.partial`
  — 빈 디렉터리, 그대로 보존
- 생성 PNG: `0`
- 생성 case sheet: `0`
- 생성 quantitative row: `0`

빈 partial도 삭제·수정·재사용하지 않는다. 따라서 mount만 보완해 같은 namespace를
재실행하지 않았다.

## 실행 계수

| 항목 | 횟수 |
|---|---:|
| comparison renderer attempt | 1 |
| Roofer invocation | 0 |
| G2 invocation | 0 |
| GS training | 0 |
| metric recomputation | 0 |
| C3/C4/C5 method-artifact access | 0 |

## 실패 가시성

`100-accepted` committed receipt를 처음 검증할 때 closed-attestation reuse receipt에
금지된 `--artifact-root` 옵션을 붙여 validator가 호출을 거부했다. receipt를 변경하지
않고 옵션을 제거해 재실행했고 `PASS`했다. 이후 renderer mount 실패는 위와 같이 별도
기술 block으로 기록했다.

## 다음 recovery 조건

새 task/handoff/output namespace를 사용하고, exact renderer command 환경에 repository
`configs/`를 `/configs:ro`로 추가한 뒤 namespace 생성 전 camera-projection preflight까지
같은 컨테이너 명령으로 확인해야 한다. 이번 v2 partial은 recovery input으로 사용하지
않는다.

이 보고서는 기술 실행 기록이다. `scientific_verdict: null`은 C1/C2의 상대 성능이나
사용 가능성을 승인·기각하지 않았다는 뜻이다.
