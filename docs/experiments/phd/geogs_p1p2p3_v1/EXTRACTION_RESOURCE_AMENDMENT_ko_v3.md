# 추출 자원 한계와 동일 해상도 anchor 비교 보완

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

주 정량 비교는 기존 최종1024 표면으로 유지한다. Anchor→refinement 비교는 양쪽 모두 사전 등록된512 해상도로 수행한다. 기존 선택 추출의 확인된 메모리 실패는 품질0점이나 참조 부재로 바꾸지 않고 별도 기술적 가용성 결과로 기록한다. 학습·입력·제어 조건·30,000회·seed·같은8,000회 anchor는 바꾸지 않는다.

## 변경 근거와 적용 시점

P1 바닐라와 깊이 가중치0.0005 조건은 각각30,000회 학습·최종1024 raw/post mesh·실제 렌더·공식 지표 파일 생성을 완료했다. 후속 보조 추출에서 바닐라 anchor1024와 가중치0.0005 조건의 final2048이32GiB 컨테이너 메모리 상한으로 종료됐다. 커널의 `CONSTRAINT_MEMCG`와 해당 컨테이너 ID로 원인을 확인했다.

동일 공식 anchor1024의 별도48GiB 시험도98/98 시점 TSDF 적분 뒤 메시화 중 실패했다. 205.55초, cgroup peak48GiB, `oom_kill=1`, Docker `OOMKilled=true`이며 관측된 최소 host 가용 메모리는11.10GiB였다.48GiB를 성공한 복구 조건으로 채택하지 않는다.

이미 등록된512 해상도의 별도 anchor 시험은32GiB 안에서 공식 학습 시점98장·평가 시점15장 렌더, raw/post 표면 생성과 유효 삼각형 검사를 완료했다. 실행162.71초, cgroup peak16.84GiB, OOM0이었다. 실제 voxel 간격은0.33862341181331673m이며,1024의0.16931170590665837m와 다른 추출 조건이다. 이는 자원 실행 가능성의 증거이며 표면 품질 개선의 증거가 아니다.

이 보완은 **지역별 최종 품질 결과를 검토하거나 UAS payload를 열기 전** 결정했다. 공식 metric 파일은 실행 산출물로 생성됐지만 설정 선택에 읽어 사용하지 않았다. 실제 메모리 종료와 파일 생성 가능성을 근거로 하며, 결과가 좋아지는 해상도를 고른 변경이 아니다.

## 고정된 완료 계약

| 산출물 | 적용 범위 | 처리 |
|---|---|---|
| 최종1024 raw/post | 주18개 + 바닐라 반복3개 | 모든 조건에 필수. 실패를 면제하지 않음 |
| 최종512 raw/post | 주18개 + 바닐라 반복3개 | 모든 조건에 필수.1024 주 비교와 별도 해상도 결과 |
| 동일 anchor512 raw/post와 실제 렌더 | 각 지역의 primary 바닐라가 한 번 생성 | 지역 공통 anchor로 모든 조건·반복에서 공유 |
| 원래 anchor1024 raw/post | 각 지역 primary 바닐라 | 동일한32GiB 한도로 실제 시도·가용성 확정. 확인된 메모리 실패만 별도 기술적 불가 |
| 원래 최종2048 raw/post | 주18개 + 반복3개 | 모든 조건 동일한 실제 시도 규칙. 확인된 메모리 실패만 별도 기술적 불가 |

확인된 메모리 실패는 native SIGKILL과 해당 cgroup의 OOM kill 증거가 함께 있어야 한다. 원인 불명 종료·소스/계약 불일치·비정상 표면·파일 누락을 이 상태로 완화하지 않는다. 선택 variant의 raw/post 중 일부 파일이 남아도 해당 실패 variant는 원자료로 보존하고 완성된 쌍으로 승격하지 않는다.

필수 산출물은 모두 성공해야 한다. 선택 산출물도 계획 inventory에서 조용히 빠지지 않고 성공 또는 확인된 자원 실패로 확정돼야 UAS gate를 통과한다. 별도 가용성 CSV에서 `TECHNICAL_RESOURCE_UNAVAILABLE`와 근거를 기록하고 거리·precision·recall·F1은 null로 둔다. 참조가 있는데 실제 복원 영역이 비어 있는 `RECONSTRUCTION_FAILURE`나 참조가 없는 상태와 구분한다.

## 비교와 그림

- 조건별 주 정량 비교와 사례 선택은 최종1024 기준을 유지한다.
- Anchor→refinement의 기하·단면 비교는 anchor512와 final512끼리 수행한다.512 anchor와1024 final을 같은 추출 조건의 개선으로 해석하지 않는다.
- Viewer는 주1024 결과와 공통512 결과를 구분하고, 같은 선택 해상도의 anchor/native/변경 결과를 표시한다. 해당 해상도의 anchor가 기술적으로 불가능하면 그 상태를 명시한다.
- 선택2048 결과는 실제 가용성을 모두 제시한다. 일부 성공만으로 전체 조건 평균·전체 반복 차이를 계산하거나 더 좋은 해상도를 고르지 않는다.
- 과거 ALS와 영상 기하의 원점군·파생 표면 구분, 동일 UAS/평가 사진, 거리 임계값과 밀도 민감도, 실패 사례 포함 원칙은 유지한다.

## 계보와 구현 경계

고정 추가 계약은 [extraction_resource_v3.json](../../../../configs/phd/geogs_p1p2p3_v1/extraction_resource_v3.json), SHA256 `804f371b9db70b089daccdba2052df8c71b54b5d20acba2ea2f5c6d3d7eb7efa`다. 외부 `contracts/extraction_resource_v3.json`과 바이트가 같다. 원 과학·분석·allocator·반복 계약을 덮어쓰지 않는다.

새 추출은 외부 task의 `extraction_resource_v3/{primary|native_repeat_1}/{P1|P2|P3}/{condition}/`에 기록한다. 기존 `runs_allocator_v2/`의 학습·렌더·지표·성공512 및 실패한 auxiliary 파일·영수증·로그는 현재 경로와 바이트로 보존한다. 새 resolver가 생산 영수증·소스·입력·원 모델·추출 계약을 연결한다. 이전 FAIL 영수증을 PASS로 고치지 않는다.

근거는 `runtime/host_memory_recovery_v1/`의 커널 기록과 `anchor_mem48_probe/`, `anchor_mesh512_mem32_probe/`의 실제 source/command/메모리/GPU/영수증이다.512 probe 자체를 주 실험 결과로 자동 승격하지 않는다. 새 계약의 실제 실행·봉인·정량/정성 분석 완료는 각각 별도로 검증해야 한다.

이 문서 작성 시점에는 새 계약의 실행·평가 연결을 구현 중이며 주18개와 반복3개의 전체 완료를 주장하지 않는다. 추가 자원 한계 또는 구현 실패도 같은 이슈 기록에 남긴다.
