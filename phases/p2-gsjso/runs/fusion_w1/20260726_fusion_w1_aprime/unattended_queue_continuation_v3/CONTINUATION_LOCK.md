# A′ continuation v3 운영 잠금

- task: `FUS-W1-APRIME-QUEUE-CONTINUATION-V3-001`
- recorded: `2026-07-27T14:32:24+09:00`
- branch: `exp/fusion-w1`
- source HEAD: `598eff0805e315b7f2e05da1041afa745b9f8a8b`
- 범위: 이미 완료된 `DEBY_LOD2_42364659 / A′ / r1`을 보존하고, 나머지 19개 학습 job을 2-GPU 병렬 continuation으로 완주한다.
- 판정: 없음. 이 문서는 스케줄·산출·실패 계약만 잠근다.

## 1. v2 인계 경계

v2 직렬 큐는 첫 job의 학습→TSDF/MC→Roofer→정량 채점이 완료된 직후, 다음 job을 materialize하기 전에 정지했다.

| 항목 | 값 |
|---|---|
| v2 계획 | `queue_plan.json` / `ead4e563a3a86f9595ff289f6550ad209886be585c7381f7abec5a7086e7c253` |
| v2 상태 | `MEASURED=1`, `MISSING=19`, `FAILED=0`, `SKIPPED=0` |
| v2 상태 해시 | `fcdf856fc8caf40bd52ac11008d07180c71e605866fc3feda7c882d193e7ad66` |
| 완료 stage record | `DEBY_LOD2_42364659 / Aprime / r1` / `2fc876f94a3c5a618504edb9529f61aa7fec5facf9abea9c935a3b0a8fc63a97` |
| 학습 receipt | `9911510f3365e8b8471ae40ef77fdb6ad5f0a81fed6fd6d97b8d0354efb7445b` |
| readout receipt | `80a66f0aafba8000eae44e2a037e588ceb3fa4c261499d2ecaf9ee8ad4192477` |
| 다음 job | `DEBY_LOD2_42364663 / Aprime / r1`; 미 materialize |

v3는 위 완료 job의 학습·readout을 재실행하지 않고, 개정 정성 패널만 추가한 뒤 v3 terminal receipt를 쓴다. v2 파일은 수정하지 않는다.

## 2. 병렬 자원 계약

- 학습 동시성은 최대 2: 독립 job 하나를 physical GPU 0, 다른 하나를 physical GPU 1에 고정한다.
- 각 lane은 서로 다른 training lock, runtime HOME/XDG/TORCH cache, Docker container name을 쓴다.
- 상태·학습 config·seed·iteration·loss·densification 등 과학 레시피는 v2와 동일하다. 변경은 job 외부 스케줄링뿐이다.
- 같은 stage의 연속 두 job을 한 pair로 학습한다. pair 두 학습이 terminal이 된 후 readout으로 넘어간다.
- TSDF/MC·Roofer·채점·정성 패널은 전역 직렬이며 학습과 겹치지 않는다. 특히 readout은 24 GiB cgroup 제약을 유지한다.
- stage 순서 `A′ r1 → A′ r2 → B r1`은 바꾸지 않는다. stage 경계를 넘어 pair하지 않는다.
- 검증 중 GPU 0의 desktop 사용량은 관찰하되 메모리 초과·다른 compute process 충돌가 있으면 해당 pair를 시작하지 않는다.

## 3. 잠긴 pair 순서

| stage | pair | GPU 0 | GPU 1 |
|---|---:|---|---|
| A′ r1 | 1 | `42364663` | `4907182` |
| A′ r1 | 2 | `4907510` | `4908050` |
| A′ r1 | 3 | `4908166` | `4908176` |
| A′ r1 | 4 | `4908023` | — |
| A′ r2 | 1 | `42364609` | `42364659` |
| A′ r2 | 2 | `42364663` | `4907182` |
| A′ r2 | 3 | `4907510` | `4908050` |
| A′ r2 | 4 | `4908166` | `4908176` |
| A′ r2 | 5 | `4908023` | — |
| B r1 | 1 | `42364609` | `42364659` |
| B r1 | 2 | `4908023` | — |

## 4. job terminal 계약

하나의 job은 아래가 모두 receipt로 존재해야 `MEASURED`다.

1. 30k 학습 `completed.json`
2. TSDF fusion + Marching Cubes mesh·surface samples
3. class 6 surface samples + 원본 ALS class 2 입력으로 Roofer 조립
4. canonical Roofer CityJSON 2.0, LoD2/val3dity 상태, 사전등록 정량 score
5. legacy alpha readout 비교 receipt
6. A–I 3×3 `panel.png`, `opacity.csv`, 정성 `complete.json`

원 발주 P5의 조립 정본은 Roofer CityJSON이다. 현재 pinned image의 `cjio 0.10.1`은 XML CityGML export를 제공하지 않고 repo에도 검증된 CityJSON→CityGML serializer가 없다. 따라서 임의 `.gml`을 만들지 않고, job receipt에 XML CityGML을 `CENSORED/UNAVAILABLE` 및 사유 코드로 기록한다. 향후 출처·버전·검증이 잠긴 serializer가 추가될 때만 derived `.gml`을 추가한다. 이 상태는 canonical CityJSON 조립 성공/실패를 대체하지 않는다.

## 5. 정성 패널 계약

`A`원본 전체 + 대상 `M_j` 경계/확대 상자, `B`확대 RGB + 유효 `M_j`, `C`학습 전 A′ ALS class-6 시드, `D`TSDF mesh, `E`표면 sample, `F`주축 단면, `G`Roofer CityJSON, `H`출력-참조 중첩(평가 전용), `I`지붕 seed-lineage opacity 궤적 순서를 고정한다. 각 tile은 문자·제목·범례를 갖고, `MEASURED` job에 placeholder를 허용하지 않는다.

## 6. 실패·서비스·보존

- 같은 오류 signature 3회에 해당 job을 `SKIPPED`로 종료하고, 같은 오류 type 3동 연속이면 해당 stage를 중단한다.
- 부분 산출·실패 로그·receipt는 즉시 저장하며 덮어쓰거나 삭제하지 않는다.
- v3는 user-systemd service로 실행하여 Codex PTY 종료와 분리한다. 고정 HEAD·branch·tracked implementation hash를 시작 및 재시작마다 검증한다.
- Codex 세션을 닫는 것은 허용하되 OS 전체 logout/reboot 지속성은 별개다. `loginctl` linger를 자동 변경하지 않는다.
- 완주 전에 canonical preprocess v2, training/readout/review, v2/v3 control receipt, smoke recovery, pilot 의존 산출을 정리·삭제하지 않는다. 정리는 완주 후 의존성 감사→quarantine→receipt 순서로 별도 수행한다.
