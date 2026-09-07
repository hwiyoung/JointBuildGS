# allocator_v2 실행·평가 도구 통합 검증

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

최신 runtime layout, 실제 TSDF 로그 검증, supplemental native repeat, 기하/렌더 평가, 요약표, 사례 그림을 함께 검사했다. Docker의 CPU 2·RAM 4GiB·network none에서 **101개 테스트가 9.626초에 통과**했다. GPU는 사용하지 않았다.

```text
python -m unittest discover -s tests/phd/geogs_p1p2p3_v1
```

실행 image는 `jointbuildgs:geogs-official-db40c95-compat-v1`, ID는 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`다. Repo·고정 공식 source·이미 확보한 metric weights는 read-only로 연결했다. Native LPIPS 구현의 CPU 대조도 포함했다. 로그는 외부 task의 `runtime/integration_cpu_allocator_v2.log`에 있다.

검증은 경계 교차 삼각형, 표면 거리와 점 거리의 구별, 참조 부재/빈 복원, 카메라·사진·평가 범위 일치, 실제 추출 파라미터, 원/보조 mesh 계보, 동일 anchor와 반복 계약, 실패/무한대/NA 분모, primary와 반복 집계의 분리를 포함한다.

테스트가 생성한 사진·표면·표·viewer payload는 합성 fixture다. 로그 안의 `TABLES_AND_ACTUAL_VIEWER_DATA_READY` 같은 문구도 합성 fixture의 entrypoint 검사에서 나온 것으로, P1/P2/P3 실제 결과가 준비됐다는 뜻이 아니다. 이 통합 검증에서는 실제 지역 RGB 또는 UAS payload를 읽지 않았다.

학습의 실제 CUDA 검증은 별도 [상태 검증](STATE_VALIDATION_ko_v1.md)과 [allocator 복구 검사](ALLOCATOR_RECOVERY_ko_v2.md)에 있다. 세 지역의 학습 완료·실제 표면·렌더·정량 결과·브라우저 표시는 각각 실제 산출물로 검증해야 한다.

이후 표면 추출의 CPU 메모리 보호를 위해 task-local advisory lock을 추가했다. 실제 읽기 전용 bind의 같은 inode를 두 프로세스가 공유하는 Docker 검사 2개도 통과했다(0.231초). 두 번째 추출은 기다린 뒤 첫 번째의 잠금 해제 후 진행하고, 일반 학습·parity·metrics는 잠금을 열지 않는다. 잠금 파일 내용은 변하지 않았다. 이는 동시 추출을 한 건으로 제한하는 자원 제어이며 native 학습·추출 설정은 바꾸지 않는다. 대기 시간은 실제 phase 시간과 분리하여 영수증과 비용 표에 기록한다.

생산 영수증과 실제 봉인 대상의 연결 검사도 보완했다. `test_evaluation_driver`, `test_runtime_layout`, `test_supplemental_repeat`의 Docker CPU 검사 **30개가 1.487초에 통과**했다. 같은 크기를 유지한 주·보조 raw/post mesh 교체, 영수증 hash 누락·중복, 파일 크기 불일치, 최종 checkpoint와 완료 metadata 변조를 거부한다. 이는 기존 파일이 실제 변조됐다는 관측이 아니라 봉인 검증기의 결함을 예방한 검사다. 실제 21개 실행의 봉인은 아직 별도로 필요하다.
